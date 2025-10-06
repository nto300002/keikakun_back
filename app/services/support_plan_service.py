import logging
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID

from app import crud
from app.schemas.support_plan import PlanDeliverableCreate

logger = logging.getLogger(__name__)

import datetime
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app import crud
from app.models.support_plan_cycle import SupportPlanCycle, SupportPlanStatus, PlanDeliverable
from app.models.enums import DeliverableType, SupportPlanStep
from app.schemas.support_plan import PlanDeliverableCreate

logger = logging.getLogger(__name__)

# deliverable_typeとstep_typeのマッピング
DELIVERABLE_TO_STEP_MAP = {
    DeliverableType.assessment_sheet: SupportPlanStep.assessment,
    DeliverableType.draft_plan_pdf: SupportPlanStep.draft_plan,
    DeliverableType.staff_meeting_minutes: SupportPlanStep.staff_meeting,
    DeliverableType.final_plan_signed_pdf: SupportPlanStep.final_plan_signed,
    DeliverableType.monitoring_report_pdf: SupportPlanStep.monitoring,
}

# ステップの順序
STEP_ORDER = [
    SupportPlanStep.assessment,
    SupportPlanStep.draft_plan,
    SupportPlanStep.staff_meeting,
    SupportPlanStep.final_plan_signed,
    SupportPlanStep.monitoring, # モニタリングはサイクルの最後かつ次のサイクルの最初
]

class SupportPlanService:
    @staticmethod
    async def _reset_future_cycles(
        db: AsyncSession,
        welfare_recipient_id: UUID,
        current_cycle_number: int
    ):
        """
        指定されたサイクル番号より大きいサイクルを削除し、
        最新のサイクルを再定義する
        """
        # 現在のサイクル番号より大きいサイクルを削除
        stmt = select(SupportPlanCycle).where(
            SupportPlanCycle.welfare_recipient_id == welfare_recipient_id,
            SupportPlanCycle.cycle_number > current_cycle_number
        ).options(selectinload(SupportPlanCycle.statuses))

        result = await db.execute(stmt)
        future_cycles = result.scalars().all()

        for cycle in future_cycles:
            # 関連するステータスを削除
            for status in cycle.statuses:
                await db.delete(status)
            # サイクルを削除
            await db.delete(cycle)

        # 最新のサイクルを再定義
        latest_stmt = select(SupportPlanCycle).where(
            SupportPlanCycle.welfare_recipient_id == welfare_recipient_id
        ).order_by(SupportPlanCycle.cycle_number.desc())

        latest_result = await db.execute(latest_stmt)
        latest_cycle = latest_result.scalars().first()

        if latest_cycle:
            latest_cycle.is_latest_cycle = True

        await db.flush()

    @staticmethod
    async def _create_new_cycle_from_final_plan(
        db: AsyncSession,
        old_cycle: SupportPlanCycle,
        final_plan_completed_at: datetime.datetime
    ):
        """最終計画書アップロード時に新しいサイクルを作成する"""
        # 1. 現在のサイクルを「最新ではない」に更新 (呼び出し元で実施)
        old_cycle.is_latest_cycle = False

        # 2. 新しいサイクルを作成
        today = datetime.date.today()
        new_cycle = SupportPlanCycle(
            welfare_recipient_id=old_cycle.welfare_recipient_id,
            plan_cycle_start_date=today,
            next_renewal_deadline=today + datetime.timedelta(days=180),
            is_latest_cycle=True,
            cycle_number=old_cycle.cycle_number + 1
        )
        db.add(new_cycle)
        await db.flush() # 新しいサイクルのIDを確定させる

        # 3. 新しいサイクル用のステータスを作成 (モニタリングから開始)
        new_steps = [
            SupportPlanStep.monitoring,
            SupportPlanStep.draft_plan,
            SupportPlanStep.staff_meeting,
            SupportPlanStep.final_plan_signed,
        ]
        for i, step_type in enumerate(new_steps):
            due_date = None
            monitoring_deadline = None

            if step_type == SupportPlanStep.monitoring and i == 0:
                # モニタリング期限のデフォルトは7日
                monitoring_deadline = 7
                due_date = (final_plan_completed_at + datetime.timedelta(days=monitoring_deadline)).date()

            new_status = SupportPlanStatus(
                plan_cycle_id=new_cycle.id,
                step_type=step_type,
                is_latest_status=(i == 0),  # 最初のステップ(monitoring)を最新にする
                monitoring_deadline=monitoring_deadline,
                due_date=due_date
            )
            db.add(new_status)

    @staticmethod
    async def handle_deliverable_upload(
        db: AsyncSession,
        *,
        deliverable_in: PlanDeliverableCreate,
        uploaded_by_staff_id: UUID
    ) -> PlanDeliverable:
        """成果物のアップロードを処理し、関連するステップを更新する"""

        logger.info(f"[DELIVERABLE_UPLOAD] Starting upload - deliverable_type: {deliverable_in.deliverable_type}, plan_cycle_id: {deliverable_in.plan_cycle_id}")

        # 既存のdeliverableがあるか確認（再アップロードの場合）
        existing_deliverable_stmt = select(PlanDeliverable).where(
            PlanDeliverable.plan_cycle_id == deliverable_in.plan_cycle_id,
            PlanDeliverable.deliverable_type == deliverable_in.deliverable_type
        )
        existing_result = await db.execute(existing_deliverable_stmt)
        existing_deliverable = existing_result.scalar_one_or_none()

        if existing_deliverable:
            # 再アップロードの場合は、既存のdeliverableを更新
            logger.info(f"[DELIVERABLE_UPLOAD] Existing deliverable found - id: {existing_deliverable.id}. Updating...")
            existing_deliverable.file_path = deliverable_in.file_path
            existing_deliverable.original_filename = deliverable_in.original_filename
            existing_deliverable.uploaded_at = datetime.datetime.now(datetime.timezone.utc)
            existing_deliverable.uploaded_by = uploaded_by_staff_id

            await db.commit()
            await db.refresh(existing_deliverable)

            return existing_deliverable

        target_step_type = DELIVERABLE_TO_STEP_MAP.get(deliverable_in.deliverable_type)
        if not target_step_type:
            from app.core.exceptions import InvalidStepOrderError
            logger.error(f"Invalid deliverable_type: {deliverable_in.deliverable_type}")
            raise InvalidStepOrderError(f"無効な成果物タイプです: {deliverable_in.deliverable_type}")

        logger.info(f"[DELIVERABLE_UPLOAD] Target step_type: {target_step_type}")

        stmt = select(SupportPlanCycle).where(SupportPlanCycle.id == deliverable_in.plan_cycle_id).options(selectinload(SupportPlanCycle.statuses))
        result = await db.execute(stmt)
        cycle = result.scalar_one_or_none()

        if not cycle:
            from app.core.exceptions import NotFoundException
            logger.error(f"Plan cycle not found: {deliverable_in.plan_cycle_id}")
            raise NotFoundException(f"計画サイクルID {deliverable_in.plan_cycle_id} が見つかりません。")

        logger.info(f"[DELIVERABLE_UPLOAD] Cycle found - id: {cycle.id}, cycle_number: {cycle.cycle_number}")

        latest_status = next((s for s in cycle.statuses if s.is_latest_status), None)
        if not latest_status:
            from app.core.exceptions import InvalidStepOrderError
            logger.error(f"Latest status not found for cycle: {cycle.id}")
            raise InvalidStepOrderError(f"サイクル {cycle.id} の最新ステータスが見つかりません。")

        logger.info(f"[DELIVERABLE_UPLOAD] Latest status - step_type: {latest_status.step_type}, is_latest_status: {latest_status.is_latest_status}")

        # 全ステータスの状態をログ出力
        for status in cycle.statuses:
            logger.info(f"[DELIVERABLE_UPLOAD] Status - step_type: {status.step_type}, is_latest_status: {status.is_latest_status}, completed: {status.completed}")

        if latest_status.step_type != target_step_type:
            from app.core.exceptions import InvalidStepOrderError
            logger.error(f"[DELIVERABLE_UPLOAD] Step order error - current: {latest_status.step_type.value}, expected: {target_step_type.value}")
            raise InvalidStepOrderError(
                f"現在のステップは {latest_status.step_type.value} です。{target_step_type.value} の成果物はアップロードできません。"
            )

        # サイクル開始日と更新期限を設定する
        # 対象: アセスメント or モニタリングの成果物, かつ、サイクル開始日が未設定の場合
        if (target_step_type in [SupportPlanStep.assessment, SupportPlanStep.monitoring] and
                cycle.plan_cycle_start_date is None):
            today = datetime.date.today()
            cycle.plan_cycle_start_date = today
            # 6ヶ月後を期限とする（簡易的に180日）
            cycle.next_renewal_deadline = today + datetime.timedelta(days=180)

        current_status = next((s for s in cycle.statuses if s.step_type == target_step_type), None)
        if not current_status:
            from app.core.exceptions import NotFoundException
            logger.error(f"Target status not found for step: {target_step_type}")
            raise NotFoundException(f"ステップ {target_step_type.value} のステータスが見つかりません。")

        # ステータスを更新
        current_status.completed = True
        current_status.completed_at = datetime.datetime.now(datetime.timezone.utc)
        current_status.is_latest_status = False
        current_status.completed_by = uploaded_by_staff_id

        if deliverable_in.deliverable_type == DeliverableType.final_plan_signed_pdf:
            # cycle_numberが現在のサイクルより大きいサイクルがあるか確認
            future_cycle_stmt = select(SupportPlanCycle).where(
                SupportPlanCycle.welfare_recipient_id == cycle.welfare_recipient_id,
                SupportPlanCycle.cycle_number > cycle.cycle_number
            )
            future_cycle_result = await db.execute(future_cycle_stmt)
            has_future_cycles = future_cycle_result.scalar_one_or_none() is not None

            # 既に次のサイクルが存在する場合は、未来のサイクルを削除して再定義
            if has_future_cycles:
                await SupportPlanService._reset_future_cycles(
                    db,
                    welfare_recipient_id=cycle.welfare_recipient_id,
                    current_cycle_number=cycle.cycle_number
                )

            # 新しいサイクルを作成
            await SupportPlanService._create_new_cycle_from_final_plan(
                db, old_cycle=cycle, final_plan_completed_at=current_status.completed_at
            )
        else:
            # 次のステップを最新にする
            # サイクル内のステップ順序を決定
            if cycle.cycle_number == 1:
                cycle_steps = [
                    SupportPlanStep.assessment,
                    SupportPlanStep.draft_plan,
                    SupportPlanStep.staff_meeting,
                    SupportPlanStep.final_plan_signed,
                ]
            else:
                cycle_steps = [
                    SupportPlanStep.monitoring,
                    SupportPlanStep.draft_plan,
                    SupportPlanStep.staff_meeting,
                    SupportPlanStep.final_plan_signed,
                ]

            try:
                current_index = cycle_steps.index(target_step_type)
                if current_index < len(cycle_steps) - 1:
                    next_step_type = cycle_steps[current_index + 1]
                    next_status = next((s for s in cycle.statuses if s.step_type == next_step_type), None)
                    if next_status:
                        next_status.is_latest_status = True
            except (ValueError, IndexError):
                pass

        # 成果物レコードを作成
        new_deliverable = PlanDeliverable(
            plan_cycle_id=deliverable_in.plan_cycle_id,
            deliverable_type=deliverable_in.deliverable_type,
            file_path=deliverable_in.file_path,
            original_filename=deliverable_in.original_filename,
            uploaded_by=uploaded_by_staff_id
        )
        db.add(new_deliverable)

        await db.commit()
        await db.refresh(new_deliverable)

        return new_deliverable

    @staticmethod
    async def handle_deliverable_update(
        db: AsyncSession,
        *,
        deliverable_id: int,
        new_file_path: str,
        new_filename: str
    ) -> PlanDeliverable:
        """成果物の更新（再アップロード）を処理する"""

        logger.info(f"[DELIVERABLE_UPDATE] Starting update - deliverable_id: {deliverable_id}")

        # 成果物を取得
        stmt = select(PlanDeliverable).where(PlanDeliverable.id == deliverable_id)
        result = await db.execute(stmt)
        deliverable = result.scalar_one_or_none()

        if not deliverable:
            from app.core.exceptions import NotFoundException
            logger.error(f"Deliverable not found: {deliverable_id}")
            raise NotFoundException(f"成果物ID {deliverable_id} が見つかりません。")

        logger.info(f"[DELIVERABLE_UPDATE] Found deliverable - type: {deliverable.deliverable_type}")

        # ファイル情報を更新
        deliverable.file_path = new_file_path
        deliverable.original_filename = new_filename
        deliverable.updated_at = datetime.datetime.now(datetime.timezone.utc)

        # 署名済みPDFの場合は、重複サイクルが作成されないようにする
        # （既に完了しているので、ステータス更新はスキップ）
        # 新サイクルも既に作成されているので何もしない

        await db.commit()
        await db.refresh(deliverable)

        logger.info(f"[DELIVERABLE_UPDATE] Update completed - deliverable_id: {deliverable_id}")

        return deliverable

    @staticmethod
    async def handle_deliverable_delete(
        db: AsyncSession,
        *,
        deliverable_id: int
    ):
        """成果物の削除を処理し、関連するステップを未完了に戻す"""

        logger.info(f"[DELIVERABLE_DELETE] Starting delete - deliverable_id: {deliverable_id}")

        # 成果物を取得
        stmt = select(PlanDeliverable).where(PlanDeliverable.id == deliverable_id)
        result = await db.execute(stmt)
        deliverable = result.scalar_one_or_none()

        if not deliverable:
            from app.core.exceptions import NotFoundException
            logger.error(f"Deliverable not found: {deliverable_id}")
            raise NotFoundException(f"成果物ID {deliverable_id} が見つかりません。")

        deliverable_type = deliverable.deliverable_type
        plan_cycle_id = deliverable.plan_cycle_id

        logger.info(f"[DELIVERABLE_DELETE] Found deliverable - type: {deliverable_type}, cycle_id: {plan_cycle_id}")

        # 対応するステップタイプを取得
        target_step_type = DELIVERABLE_TO_STEP_MAP.get(deliverable_type)
        if not target_step_type:
            from app.core.exceptions import InvalidStepOrderError
            logger.error(f"Invalid deliverable_type: {deliverable_type}")
            raise InvalidStepOrderError(f"無効な成果物タイプです: {deliverable_type}")

        # サイクルとステータスを取得
        cycle_stmt = select(SupportPlanCycle).where(
            SupportPlanCycle.id == plan_cycle_id
        ).options(selectinload(SupportPlanCycle.statuses))
        cycle_result = await db.execute(cycle_stmt)
        cycle = cycle_result.scalar_one_or_none()

        if not cycle:
            from app.core.exceptions import NotFoundException
            logger.error(f"Plan cycle not found: {plan_cycle_id}")
            raise NotFoundException(f"計画サイクルID {plan_cycle_id} が見つかりません。")

        # 対象ステータスを未完了に戻す
        target_status = next((s for s in cycle.statuses if s.step_type == target_step_type), None)
        if target_status:
            target_status.completed = False
            target_status.completed_at = None
            target_status.completed_by = None
            target_status.is_latest_status = True
            logger.info(f"[DELIVERABLE_DELETE] Reverted status - step_type: {target_step_type}")

        # 次のステップを最新ではなくする
        # サイクル内のステップ順序を決定
        if cycle.cycle_number == 1:
            cycle_steps = [
                SupportPlanStep.assessment,
                SupportPlanStep.draft_plan,
                SupportPlanStep.staff_meeting,
                SupportPlanStep.final_plan_signed,
            ]
        else:
            cycle_steps = [
                SupportPlanStep.monitoring,
                SupportPlanStep.draft_plan,
                SupportPlanStep.staff_meeting,
                SupportPlanStep.final_plan_signed,
            ]

        try:
            current_index = cycle_steps.index(target_step_type)
            # 次以降のステップをis_latest_status=Falseにする
            for i in range(current_index + 1, len(cycle_steps)):
                next_step_type = cycle_steps[i]
                next_status = next((s for s in cycle.statuses if s.step_type == next_step_type), None)
                if next_status:
                    next_status.is_latest_status = False
                    logger.info(f"[DELIVERABLE_DELETE] Set is_latest_status=False for step: {next_step_type}")
        except (ValueError, IndexError):
            pass

        # 成果物を削除
        await db.delete(deliverable)

        await db.commit()

        logger.info(f"[DELIVERABLE_DELETE] Delete completed - deliverable_id: {deliverable_id}")


support_plan_service = SupportPlanService()
