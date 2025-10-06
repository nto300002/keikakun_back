from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status, Form, File, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
import datetime
import io
import uuid as uuid_lib

from app import crud, models, schemas
from app.api import deps
from app.core import storage
from app.schemas.support_plan import DeliverableType
from app.models.support_plan_cycle import SupportPlanCycle, PlanDeliverable
from app.models.welfare_recipient import OfficeWelfareRecipient
from app.services.support_plan_service import support_plan_service
from app.core.exceptions import NotFoundException, ForbiddenException

router = APIRouter()


@router.get(
    "/{recipient_id}/cycles",
    response_model=schemas.support_plan.SupportPlanCyclesResponse,
)
async def get_support_plan_cycles(
    recipient_id: UUID,
    db: AsyncSession = Depends(deps.get_db),
    current_staff: models.Staff = Depends(deps.get_current_user),
):
    """
    指定された利用者のすべての支援計画サイクルを取得します。
    """
    # 1. 利用者の存在確認
    from app.models.welfare_recipient import WelfareRecipient

    stmt = select(WelfareRecipient).where(WelfareRecipient.id == recipient_id)
    result = await db.execute(stmt)
    recipient = result.scalar_one_or_none()

    if not recipient:
        raise NotFoundException(f"Welfare recipient with ID {recipient_id} not found.")

    # 2. 権限チェック: ユーザーがこの利用者の情報にアクセスする権限を持っているかチェック
    user_office_ids = [assoc.office_id for assoc in current_staff.office_associations]

    recipient_office_stmt = select(OfficeWelfareRecipient).where(
        OfficeWelfareRecipient.welfare_recipient_id == recipient_id
    )
    recipient_office_result = await db.execute(recipient_office_stmt)
    recipient_office_assoc = recipient_office_result.scalar_one_or_none()

    if not recipient_office_assoc or recipient_office_assoc.office_id not in user_office_ids:
        raise ForbiddenException("You do not have permission to access this welfare recipient's support plan.")

    # 3. サイクル一覧を取得
    cycles = await crud.support_plan.get_cycles_by_recipient(db=db, recipient_id=recipient_id)

    if not cycles:
        return schemas.support_plan.SupportPlanCyclesResponse(cycles=[])

    # 4. 【パフォーマンス最適化】全サイクルのdeliverableを一括取得（N+1問題を解決）
    from app.core.config import settings
    from app.models.enums import SupportPlanStep

    cycle_ids = [cycle.id for cycle in cycles]

    # 全サイクルのdeliverableを一度に取得
    deliverables_stmt = (
        select(PlanDeliverable)
        .where(PlanDeliverable.plan_cycle_id.in_(cycle_ids))
    )
    deliverables_result = await db.execute(deliverables_stmt)
    all_deliverables = deliverables_result.scalars().all()

    # deliverableをマッピング: (cycle_id, deliverable_type) -> deliverable
    deliverables_map = {
        (d.plan_cycle_id, d.deliverable_type): d
        for d in all_deliverables
    }

    # step_typeをdeliverable_typeにマッピング
    step_to_deliverable_map = {
        SupportPlanStep.assessment: DeliverableType.assessment_sheet,
        SupportPlanStep.monitoring: DeliverableType.monitoring_report_pdf,
        SupportPlanStep.draft_plan: DeliverableType.draft_plan_pdf,
        SupportPlanStep.staff_meeting: DeliverableType.staff_meeting_minutes,
        SupportPlanStep.final_plan_signed: DeliverableType.final_plan_signed_pdf,
    }

    # 5. 各サイクルとステータスにPDF情報を付与
    cycles_response = []
    for cycle in cycles:
        statuses_with_url = []
        for status in cycle.statuses:
            pdf_url = None
            pdf_filename = None

            if status.completed:
                deliverable_type_value = step_to_deliverable_map.get(status.step_type)

                if deliverable_type_value:
                    # マッピングからdeliverableを取得（DBクエリなし）
                    deliverable = deliverables_map.get((cycle.id, deliverable_type_value))

                    if deliverable and deliverable.file_path:
                        # S3パスから署名付きURLを生成
                        object_name = deliverable.file_path.replace(f"s3://{settings.S3_BUCKET_NAME}/", "")
                        pdf_url = await storage.create_presigned_url(
                            object_name=object_name,
                            expiration=3600,
                            inline=True
                        )
                        pdf_filename = deliverable.original_filename

            # Pydanticモデルに変換してpdf_urlとpdf_filenameを含める
            status_response = schemas.support_plan.SupportPlanStatusResponse(
                id=status.id,
                plan_cycle_id=status.plan_cycle_id,
                step_type=status.step_type,
                is_latest_status=status.is_latest_status,
                completed=status.completed,
                completed_at=status.completed_at,
                monitoring_deadline=status.monitoring_deadline,
                due_date=status.due_date,
                pdf_url=pdf_url,
                pdf_filename=pdf_filename
            )
            statuses_with_url.append(status_response)

        # サイクル情報もPydanticモデルに変換
        cycle_response = schemas.support_plan.SupportPlanCycleRead(
            id=cycle.id,
            welfare_recipient_id=cycle.welfare_recipient_id,
            plan_cycle_start_date=cycle.plan_cycle_start_date,
            final_plan_signed_date=cycle.final_plan_signed_date,
            next_renewal_deadline=cycle.next_renewal_deadline,
            is_latest_cycle=cycle.is_latest_cycle,
            cycle_number=cycle.cycle_number,
            statuses=statuses_with_url
        )
        cycles_response.append(cycle_response)

    return schemas.support_plan.SupportPlanCyclesResponse(cycles=cycles_response)


@router.post(
    "/plan-deliverables",
    response_model=schemas.support_plan.PlanDeliverable,
    status_code=status.HTTP_201_CREATED,
)
async def upload_plan_deliverable(
    plan_cycle_id: int = Form(...),
    deliverable_type: str = Form(...),
    file: UploadFile = File(...),
    db: AsyncSession = Depends(deps.get_db),
    current_user: models.Staff = Depends(deps.get_current_user),
):
    """
    個別支援計画の成果物（PDF）のアップロード
    """
    # 1. ファイル検証
    if not file.content_type == "application/pdf":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="アップロードできるファイルはPDF形式のみです。"
        )

    # 2. plan_cycleの存在確認と権限チェック
    stmt = (
        select(SupportPlanCycle)
        .where(SupportPlanCycle.id == plan_cycle_id)
        .options(selectinload(SupportPlanCycle.welfare_recipient))
    )
    result = await db.execute(stmt)
    plan_cycle = result.scalar_one_or_none()

    if not plan_cycle:
        raise NotFoundException(f"計画サイクルID {plan_cycle_id} が見つかりません。")

    user_office_ids = [assoc.office_id for assoc in current_user.office_associations]
    recipient_office_stmt = select(OfficeWelfareRecipient).where(
        OfficeWelfareRecipient.welfare_recipient_id == plan_cycle.welfare_recipient_id
    )
    recipient_office_result = await db.execute(recipient_office_stmt)
    recipient_office_assoc = recipient_office_result.scalar_one_or_none()

    if not recipient_office_assoc or recipient_office_assoc.office_id not in user_office_ids:
        raise ForbiddenException("この利用者の個別支援計画にアクセスする権限がありません。")

    # 3. ファイル内容を読み取る
    file_content = await file.read()

    # 4. ファイル名の衝突を避けるためにUUIDを付与
    unique_filename = f"{uuid_lib.uuid4()}_{file.filename or 'unknown.pdf'}"
    object_name = f"plan-deliverables/{plan_cycle_id}/{deliverable_type}/{unique_filename}"

    # 5. ファイルをBinaryIOに変換してS3にアップロード
    file_like = io.BytesIO(file_content)
    s3_url = await storage.upload_file(file=file_like, object_name=object_name)

    if not s3_url:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="ファイルのアップロードに失敗しました。"
        )

    # 6. サービス層を呼び出して、成果物の登録とステータス更新を行う
    deliverable_create = schemas.support_plan.PlanDeliverableCreate(
        plan_cycle_id=plan_cycle_id,
        deliverable_type=DeliverableType(deliverable_type),
        file_path=s3_url,
        original_filename=file.filename or "unknown.pdf"
    )

    deliverable = await support_plan_service.handle_deliverable_upload(
        db=db,
        deliverable_in=deliverable_create,
        uploaded_by_staff_id=current_user.id
    )

    return deliverable


@router.get("/deliverables/{deliverable_id}/download", response_model=schemas.support_plan.PlanDeliverableDownloadResponse)
async def download_plan_deliverable(
    deliverable_id: int,
    db: AsyncSession = Depends(deps.get_db),
    current_user: models.Staff = Depends(deps.get_current_user),
):
    """
    個別支援計画の成果物（PDF）をダウンロードするための署名付きURLを取得
    """
    # 1. deliverableを取得
    stmt = (
        select(PlanDeliverable)
        .where(PlanDeliverable.id == deliverable_id)
        .options(
            selectinload(PlanDeliverable.plan_cycle).selectinload(SupportPlanCycle.welfare_recipient)
        )
    )
    result = await db.execute(stmt)
    deliverable = result.scalar_one_or_none()

    if not deliverable:
        raise NotFoundException(f"成果物ID {deliverable_id} が見つかりません。")

    # 2. 利用者へのアクセス権限を確認
    user_office_ids = [assoc.office_id for assoc in current_user.office_associations]

    recipient_office_stmt = select(OfficeWelfareRecipient).where(
        OfficeWelfareRecipient.welfare_recipient_id == deliverable.plan_cycle.welfare_recipient_id
    )
    recipient_office_result = await db.execute(recipient_office_stmt)
    recipient_office_assoc = recipient_office_result.scalar_one_or_none()

    if not recipient_office_assoc or recipient_office_assoc.office_id not in user_office_ids:
        raise ForbiddenException("この成果物にアクセスする権限がありません。")

    # 3. S3署名付きURLを生成
    from app.core.config import settings

    object_name = deliverable.file_path.replace(f"s3://{settings.S3_BUCKET_NAME}/", "")

    presigned_url = await storage.create_presigned_url(object_name=object_name, expiration=3600, inline=True)

    if not presigned_url:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="署名付きURLの生成に失敗しました。"
        )

    return schemas.support_plan.PlanDeliverableDownloadResponse(presigned_url=presigned_url)


@router.put("/deliverables/{deliverable_id}", response_model=schemas.support_plan.PlanDeliverable)
async def update_plan_deliverable(
    deliverable_id: int,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(deps.get_db),
    current_user: models.Staff = Depends(deps.get_current_user),
):
    """
    個別支援計画の成果物（PDF）を再アップロード（更新）
    """
    # 1. ファイル検証
    if not file.content_type == "application/pdf":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="アップロードできるファイルはPDF形式のみです。"
        )

    # 2. deliverableを取得
    stmt = (
        select(PlanDeliverable)
        .where(PlanDeliverable.id == deliverable_id)
        .options(
            selectinload(PlanDeliverable.plan_cycle).selectinload(SupportPlanCycle.welfare_recipient)
        )
    )
    result = await db.execute(stmt)
    deliverable = result.scalar_one_or_none()

    if not deliverable:
        raise NotFoundException(f"成果物ID {deliverable_id} が見つかりません。")

    # 3. 権限チェック
    user_office_ids = [assoc.office_id for assoc in current_user.office_associations]
    recipient_office_stmt = select(OfficeWelfareRecipient).where(
        OfficeWelfareRecipient.welfare_recipient_id == deliverable.plan_cycle.welfare_recipient_id
    )
    recipient_office_result = await db.execute(recipient_office_stmt)
    recipient_office_assoc = recipient_office_result.scalar_one_or_none()

    if not recipient_office_assoc or recipient_office_assoc.office_id not in user_office_ids:
        raise ForbiddenException("この成果物を更新する権限がありません。")

    # 4. ファイル内容を読み取る
    file_content = await file.read()

    # 5. ファイル名の衝突を避けるためにUUIDを付与
    unique_filename = f"{uuid_lib.uuid4()}_{file.filename or 'unknown.pdf'}"
    object_name = f"plan-deliverables/{deliverable.plan_cycle_id}/{deliverable.deliverable_type.value}/{unique_filename}"

    # 6. ファイルをBinaryIOに変換してS3にアップロード
    file_like = io.BytesIO(file_content)
    s3_url = await storage.upload_file(file=file_like, object_name=object_name)

    if not s3_url:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="ファイルのアップロードに失敗しました。"
        )

    # 7. サービス層を呼び出して成果物を更新
    updated_deliverable = await support_plan_service.handle_deliverable_update(
        db=db,
        deliverable_id=deliverable_id,
        new_file_path=s3_url,
        new_filename=file.filename or "unknown.pdf"
    )

    return updated_deliverable


@router.delete("/deliverables/{deliverable_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_plan_deliverable(
    deliverable_id: int,
    db: AsyncSession = Depends(deps.get_db),
    current_user: models.Staff = Depends(deps.get_current_user),
):
    """
    個別支援計画の成果物（PDF）を削除し、対応するステータスを未完了に戻す
    """
    # 1. deliverableを取得
    stmt = (
        select(PlanDeliverable)
        .where(PlanDeliverable.id == deliverable_id)
        .options(
            selectinload(PlanDeliverable.plan_cycle).selectinload(SupportPlanCycle.welfare_recipient)
        )
    )
    result = await db.execute(stmt)
    deliverable = result.scalar_one_or_none()

    if not deliverable:
        raise NotFoundException(f"成果物ID {deliverable_id} が見つかりません。")

    # 2. 権限チェック
    user_office_ids = [assoc.office_id for assoc in current_user.office_associations]
    recipient_office_stmt = select(OfficeWelfareRecipient).where(
        OfficeWelfareRecipient.welfare_recipient_id == deliverable.plan_cycle.welfare_recipient_id
    )
    recipient_office_result = await db.execute(recipient_office_stmt)
    recipient_office_assoc = recipient_office_result.scalar_one_or_none()

    if not recipient_office_assoc or recipient_office_assoc.office_id not in user_office_ids:
        raise ForbiddenException("この成果物を削除する権限がありません。")

    # 3. サービス層を呼び出して成果物を削除
    await support_plan_service.handle_deliverable_delete(db=db, deliverable_id=deliverable_id)
