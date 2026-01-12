from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from datetime import timedelta
import logging

from app.api import deps
from app.models.staff import Staff
from app.models.support_plan_cycle import SupportPlanStatus, SupportPlanCycle
from app.models.welfare_recipient import OfficeWelfareRecipient
from app.models.enums import SupportPlanStep, ResourceType, ActionType
from app.schemas.support_plan import SupportPlanCycleUpdate, SupportPlanStatusResponse
from app.core.exceptions import NotFoundException, ForbiddenException
from app.messages import ja

logger = logging.getLogger(__name__)

router = APIRouter()


@router.patch("/{status_id}", response_model=SupportPlanStatusResponse)
async def update_next_plan_start_date(
    status_id: int,
    update_data: SupportPlanCycleUpdate,
    db: AsyncSession = Depends(deps.get_db),
    current_user: Staff = Depends(deps.get_current_user),
):
    """
    次回計画開始期限の日数を更新する

    - **status_id**: 更新するステータスのID
    - **next_plan_start_date**: 次回計画開始期限（日数）

    処理:
    1. ステータスの存在確認
    2. モニタリングステータスであることを確認
    3. 利用者へのアクセス権限確認
    4. next_plan_start_dateを更新
    5. due_dateを再計算（final_plan_completed_at + next_plan_start_date）
    """
    # 1. ステータスを取得
    stmt = (
        select(SupportPlanStatus)
        .where(SupportPlanStatus.id == status_id)
        .options(
            selectinload(SupportPlanStatus.plan_cycle)
            .selectinload(SupportPlanCycle.welfare_recipient)
        )
    )
    result = await db.execute(stmt)
    plan_status = result.scalar_one_or_none()

    if not plan_status:
        raise NotFoundException(ja.SUPPORT_PLAN_STATUS_NOT_FOUND.format(status_id=status_id))

    # 2. モニタリングステータスであることを確認
    if plan_status.step_type != SupportPlanStep.monitoring:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ja.SUPPORT_PLAN_MONITORING_ONLY
        )

    # 3. 利用者へのアクセス権限を確認
    user_office_ids = [assoc.office_id for assoc in current_user.office_associations]

    recipient_office_stmt = select(OfficeWelfareRecipient).where(
        OfficeWelfareRecipient.welfare_recipient_id == plan_status.plan_cycle.welfare_recipient_id
    )
    recipient_office_result = await db.execute(recipient_office_stmt)
    recipient_office_assoc = recipient_office_result.scalar_one_or_none()

    if not recipient_office_assoc or recipient_office_assoc.office_id not in user_office_ids:
        raise ForbiddenException(ja.SUPPORT_PLAN_NO_ACCESS)

    # 4. Employee restriction check
    employee_request = await deps.check_employee_restriction(
        db=db,
        current_staff=current_user,
        resource_type=ResourceType.support_plan_status,
        action_type=ActionType.update,
        resource_id=None,  # status_id は int なので None
        request_data={
            "status_id": status_id,
            "next_plan_start_date": update_data.next_plan_start_date
        }
    )

    if employee_request:
        # Employee case: return request created response
        return JSONResponse(
            status_code=status.HTTP_202_ACCEPTED,
            content={
                "message": "Request created and pending approval",
                "request_id": str(employee_request.id)
            }
        )

    # 5. 前のサイクルのfinal_plan_signed完了日を取得
    # 現在のサイクルの前のサイクルを取得
    prev_cycle_stmt = (
        select(SupportPlanCycle)
        .where(
            SupportPlanCycle.welfare_recipient_id == plan_status.plan_cycle.welfare_recipient_id,
            SupportPlanCycle.cycle_number == plan_status.plan_cycle.cycle_number - 1
        )
        .options(selectinload(SupportPlanCycle.statuses))
    )
    prev_cycle_result = await db.execute(prev_cycle_stmt)
    prev_cycle = prev_cycle_result.scalar_one_or_none()

    final_plan_completed_at = None
    if prev_cycle:
        # 前のサイクルのfinal_plan_signedステータスを取得
        final_plan_status = next(
            (s for s in prev_cycle.statuses if s.step_type == SupportPlanStep.final_plan_signed),
            None
        )
        if final_plan_status and final_plan_status.completed_at:
            final_plan_completed_at = final_plan_status.completed_at.date()

    # 6. next_plan_start_dateを更新 (SupportPlanCycleに設定)
    plan_status.plan_cycle.next_plan_start_date = update_data.next_plan_start_date

    # 7. due_dateを再計算
    if final_plan_completed_at:
        plan_status.due_date = final_plan_completed_at + timedelta(days=update_data.next_plan_start_date)

    await db.commit()
    await db.refresh(plan_status)

    logger.info(f"次回計画開始期限を更新: status_id={status_id}, next_plan_start_date={update_data.next_plan_start_date}")

    return SupportPlanStatusResponse(
        id=plan_status.id,
        plan_cycle_id=plan_status.plan_cycle_id,
        step_type=plan_status.step_type,
        is_latest_status=plan_status.is_latest_status,
        completed=plan_status.completed,
        completed_at=plan_status.completed_at,
        next_plan_start_date=plan_status.plan_cycle.next_plan_start_date,
        due_date=plan_status.due_date,
        pdf_url=None,
        pdf_filename=None
    )
