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

logger = logging.getLogger(__name__)

router = APIRouter()


@router.patch("/{status_id}", response_model=SupportPlanStatusResponse)
async def update_monitoring_deadline(
    status_id: int,
    update_data: SupportPlanCycleUpdate,
    db: AsyncSession = Depends(deps.get_db),
    current_user: Staff = Depends(deps.get_current_user),
):
    """
    モニタリング期限の日数を更新する

    - **status_id**: 更新するステータスのID
    - **monitoring_deadline**: モニタリング期限（日数）

    処理:
    1. ステータスの存在確認
    2. モニタリングステータスであることを確認
    3. 利用者へのアクセス権限確認
    4. monitoring_deadlineを更新
    5. due_dateを再計算（final_plan_completed_at + monitoring_deadline）
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
        raise NotFoundException(f"ステータスID {status_id} が見つかりません。")

    # 2. モニタリングステータスであることを確認
    if plan_status.step_type != SupportPlanStep.monitoring:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="モニタリング期限はモニタリングステータスのみ設定できます。"
        )

    # 3. 利用者へのアクセス権限を確認
    user_office_ids = [assoc.office_id for assoc in current_user.office_associations]

    recipient_office_stmt = select(OfficeWelfareRecipient).where(
        OfficeWelfareRecipient.welfare_recipient_id == plan_status.plan_cycle.welfare_recipient_id
    )
    recipient_office_result = await db.execute(recipient_office_stmt)
    recipient_office_assoc = recipient_office_result.scalar_one_or_none()

    if not recipient_office_assoc or recipient_office_assoc.office_id not in user_office_ids:
        raise ForbiddenException("このステータスにアクセスする権限がありません。")

    # 4. Employee restriction check
    employee_request = await deps.check_employee_restriction(
        db=db,
        current_staff=current_user,
        resource_type=ResourceType.support_plan_status,
        action_type=ActionType.update,
        resource_id=None,  # status_id は int なので None
        request_data={
            "status_id": status_id,
            "monitoring_deadline": update_data.monitoring_deadline
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

    # 6. monitoring_deadlineを更新 (SupportPlanCycleに設定)
    plan_status.plan_cycle.monitoring_deadline = update_data.monitoring_deadline

    # 7. due_dateを再計算
    if final_plan_completed_at:
        plan_status.due_date = final_plan_completed_at + timedelta(days=update_data.monitoring_deadline)

    await db.commit()
    await db.refresh(plan_status)

    logger.info(f"モニタリング期限を更新: status_id={status_id}, monitoring_deadline={update_data.monitoring_deadline}")

    return SupportPlanStatusResponse(
        id=plan_status.id,
        plan_cycle_id=plan_status.plan_cycle_id,
        step_type=plan_status.step_type,
        is_latest_status=plan_status.is_latest_status,
        completed=plan_status.completed,
        completed_at=plan_status.completed_at,
        monitoring_deadline=plan_status.plan_cycle.monitoring_deadline,
        due_date=plan_status.due_date,
        pdf_url=None,
        pdf_filename=None
    )
