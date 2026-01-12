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
from app.models.enums import DeliverableType, SupportPlanStep, CYCLE_STEPS
from app.schemas.support_plan import PlanDeliverableCreate
from app.services.calendar_service import calendar_service

logger = logging.getLogger(__name__)

# deliverable_typeとstep_typeのマッピング
DELIVERABLE_TO_STEP_MAP = {
    DeliverableType.assessment_sheet: SupportPlanStep.assessment,
    DeliverableType.draft_plan_pdf: SupportPlanStep.draft_plan,
    DeliverableType.staff_meeting_minutes: SupportPlanStep.staff_meeting,
    DeliverableType.final_plan_signed_pdf: SupportPlanStep.final_plan_signed,
    DeliverableType.monitoring_report_pdf: SupportPlanStep.monitoring,
}

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
    async def _create_new_cycle_from_monitoring(
        db: AsyncSession,
        old_cycle: SupportPlanCycle,
        monitoring_completed_at: datetime.datetime
    ):
        """モニタリングアップロード時に新しいサイクルを作成する"""
        # MissingGreenletエラーを防ぐため、old_cycleの全属性をロード
        await db.refresh(old_cycle)

        # 1. 現在のサイクルを「最新ではない」に更新 (呼び出し元で実施)
        old_cycle.is_latest_cycle = False

        # 2. 新しいサイクルを作成
        today = datetime.date.today()
        new_cycle = SupportPlanCycle(
            welfare_recipient_id=old_cycle.welfare_recipient_id,
            office_id=old_cycle.office_id,
            plan_cycle_start_date=today,
            next_renewal_deadline=today + datetime.timedelta(days=180),
            is_latest_cycle=True,
            cycle_number=old_cycle.cycle_number + 1
        )

        db.add(new_cycle)
        await db.flush() # 新しいサイクルのIDを確定させる
        await db.refresh(new_cycle)  # MissingGreenletエラーを防ぐため全属性をロード

        logger.info(f"Created new cycle {new_cycle.id} for recipient {new_cycle.welfare_recipient_id}")

        # 3. 新しいサイクル用のステータスを作成 (アセスメントから開始)
        monitoring_status = None
        for i, step_type in enumerate(CYCLE_STEPS):
            due_date = None

            if step_type == SupportPlanStep.monitoring:
                # 次回計画開始期限のデフォルトは7日
                next_plan_start_date = 7
                new_cycle.next_plan_start_date = next_plan_start_date
                due_date = (monitoring_completed_at + datetime.timedelta(days=next_plan_start_date)).date()

            new_status = SupportPlanStatus(
                plan_cycle_id=new_cycle.id,
                welfare_recipient_id=old_cycle.welfare_recipient_id,
                office_id=old_cycle.office_id,
                step_type=step_type,
                is_latest_status=(i == 0),  # 最初のステップ(assessment)を最新にする
                due_date=due_date
            )
            db.add(new_status)

            if step_type == SupportPlanStep.monitoring:
                monitoring_status = new_status

        await db.flush()  # ステータスのIDを確定させる

        # MissingGreenletエラーを防ぐため、monitoring_statusの全属性をロード
        if monitoring_status:
            await db.refresh(monitoring_status)

        # 4. カレンダーイベントを作成
        # MissingGreenletエラーを防ぐため、必要な属性を事前に変数に保存
        cycle_id = new_cycle.id
        office_id = new_cycle.office_id
        welfare_recipient_id = new_cycle.welfare_recipient_id
        next_renewal_deadline = new_cycle.next_renewal_deadline
        cycle_start_date = new_cycle.plan_cycle_start_date
        cycle_number = new_cycle.cycle_number
        monitoring_status_id = monitoring_status.id if monitoring_status else None

        try:
            logger.info(f"Creating calendar events for cycle {cycle_id}")

            # 更新期限イベントを作成（150日目～180日目の1イベント）
            renewal_event_ids = await calendar_service.create_renewal_deadline_events(
                db=db,
                office_id=office_id,
                welfare_recipient_id=welfare_recipient_id,
                cycle_id=cycle_id,
                next_renewal_deadline=next_renewal_deadline
            )

            if renewal_event_ids:
                logger.info(f"Created renewal deadline calendar event for cycle {cycle_id}")

            # モニタリング期限イベントを作成（cycle_number >= 2の場合、1日目9:00～7日目18:00の1イベント）
            monitoring_event_ids = await calendar_service.create_next_plan_start_date_events(
                db=db,
                office_id=office_id,
                welfare_recipient_id=welfare_recipient_id,
                cycle_id=cycle_id,
                cycle_start_date=cycle_start_date,
                cycle_number=cycle_number,
                status_id=monitoring_status_id
            )
            if monitoring_event_ids:
                logger.info(f"Created monitoring deadline calendar events for cycle {cycle_id}")

        except Exception as e:
            # カレンダーイベント作成に失敗してもサイクル作成は継続
            logger.warning(f"Failed to create calendar events for cycle {cycle_id}: {str(e)}")

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

        logger.info(f"[STATUS_UPDATE] BEFORE - status_id={current_status.id}, step={current_status.step_type}, completed={current_status.completed}, is_latest={current_status.is_latest_status}")

        # ステータスを更新
        current_status.completed = True
        current_status.completed_at = datetime.datetime.now(datetime.timezone.utc)
        # monitoringの場合は、サイクルの最終ステップなのでis_latest_status=Trueのまま維持
        if target_step_type != SupportPlanStep.monitoring:
            current_status.is_latest_status = False
        current_status.completed_by = uploaded_by_staff_id

        logger.info(f"[STATUS_UPDATE] AFTER - status_id={current_status.id}, step={current_status.step_type}, completed={current_status.completed}, is_latest={current_status.is_latest_status}")

        # カレンダーイベント削除フック
        from app.services.calendar_service import calendar_service
        from app.models.enums import CalendarEventType

        # final_plan_signed完了時: 更新期限イベントを削除
        if target_step_type == SupportPlanStep.final_plan_signed:
            logger.info(f"[CALENDAR_EVENT] Deleting renewal deadline event for cycle_id={cycle.id}")
            try:
                deleted = await calendar_service.delete_event_by_cycle(
                    db=db,
                    cycle_id=cycle.id,
                    event_type=CalendarEventType.renewal_deadline
                )
                if deleted:
                    logger.info(f"[CALENDAR_EVENT] Renewal deadline event deleted for cycle_id={cycle.id}")
                else:
                    logger.info(f"[CALENDAR_EVENT] No renewal deadline event found for cycle_id={cycle.id}")
            except Exception as e:
                logger.warning(f"[CALENDAR_EVENT] Failed to delete renewal deadline event: {e}")

        # monitoring完了時: モニタリング期限イベントを削除
        if target_step_type == SupportPlanStep.monitoring:
            logger.info(f"[CALENDAR_EVENT] Deleting monitoring deadline event for status_id={current_status.id}")
            try:
                deleted = await calendar_service.delete_event_by_status(
                    db=db,
                    status_id=current_status.id,
                    event_type=CalendarEventType.next_plan_start_date
                )
                if deleted:
                    logger.info(f"[CALENDAR_EVENT] Monitoring deadline event deleted for status_id={current_status.id}")
                else:
                    logger.info(f"[CALENDAR_EVENT] No monitoring deadline event found for status_id={current_status.id}")
            except Exception as e:
                logger.warning(f"[CALENDAR_EVENT] Failed to delete monitoring deadline event: {e}")

        if deliverable_in.deliverable_type == DeliverableType.monitoring_report_pdf:
            logger.info(f"[MONITORING] Detected monitoring_report_pdf upload for cycle {cycle.id}")

            # ステータス更新をデータベースに反映させるため、ここでflushを呼ぶ
            await db.flush()

            # cycle_numberが現在のサイクルより大きいサイクルがあるか確認
            future_cycle_stmt = select(SupportPlanCycle).where(
                SupportPlanCycle.welfare_recipient_id == cycle.welfare_recipient_id,
                SupportPlanCycle.cycle_number > cycle.cycle_number
            )
            future_cycle_result = await db.execute(future_cycle_stmt)
            has_future_cycles = future_cycle_result.scalar_one_or_none() is not None

            logger.info(f"[MONITORING] has_future_cycles={has_future_cycles}")

            # 既に次のサイクルが存在する場合は、未来のサイクルを削除して再定義
            if has_future_cycles:
                logger.info(f"[MONITORING] Resetting future cycles for recipient {cycle.welfare_recipient_id}")
                await SupportPlanService._reset_future_cycles(
                    db,
                    welfare_recipient_id=cycle.welfare_recipient_id,
                    current_cycle_number=cycle.cycle_number
                )
                logger.info(f"[MONITORING] Future cycles reset completed")

            # 新しいサイクルを作成
            logger.info(f"[MONITORING] Creating new cycle from monitoring for cycle {cycle.id}")
            await SupportPlanService._create_new_cycle_from_monitoring(
                db, old_cycle=cycle, monitoring_completed_at=current_status.completed_at
            )
            logger.info(f"[MONITORING] New cycle creation completed")
        else:
            # 次のステップを最新にする
            try:
                current_index = CYCLE_STEPS.index(target_step_type)
                if current_index < len(CYCLE_STEPS) - 1:
                    next_step_type = CYCLE_STEPS[current_index + 1]
                    next_status = next((s for s in cycle.statuses if s.step_type == next_step_type), None)
                    if next_status:
                        # 全てのステータスをis_latest_status=Falseにする
                        for status in cycle.statuses:
                            status.is_latest_status = False
                        # 次のステップのみをis_latest_status=Trueにする
                        next_status.is_latest_status = True
                        logger.info(f"[STEP_PROGRESS] Moved to next step: {next_step_type.value}")
            except (ValueError, IndexError):
                pass

        # 成果物レコードを作成
        logger.info(f"[DELIVERABLE_CREATE] Creating PlanDeliverable for cycle {deliverable_in.plan_cycle_id}, type={deliverable_in.deliverable_type}")
        new_deliverable = PlanDeliverable(
            plan_cycle_id=deliverable_in.plan_cycle_id,
            deliverable_type=deliverable_in.deliverable_type,
            file_path=deliverable_in.file_path,
            original_filename=deliverable_in.original_filename,
            uploaded_by=uploaded_by_staff_id
        )
        db.add(new_deliverable)
        logger.info(f"[DELIVERABLE_CREATE] PlanDeliverable added to session")

        logger.info(f"[COMMIT] Calling db.commit() for deliverable upload...")
        try:
            await db.commit()
            logger.info(f"[COMMIT] db.commit() completed successfully")
        except Exception as commit_error:
            logger.error(f"[COMMIT] db.commit() FAILED: {type(commit_error).__name__}: {commit_error}")
            import traceback
            logger.error(f"[COMMIT] Traceback:\n{traceback.format_exc()}")
            raise

        await db.refresh(new_deliverable)
        logger.info(f"[DELIVERABLE_CREATE] PlanDeliverable created with id={new_deliverable.id}")

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
        try:
            current_index = CYCLE_STEPS.index(target_step_type)
            # 次以降のステップをis_latest_status=Falseにする
            for i in range(current_index + 1, len(CYCLE_STEPS)):
                next_step_type = CYCLE_STEPS[i]
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

    @staticmethod
    async def update_status_completion(
        db: AsyncSession,
        status_id: int,
        completed: bool
    ) -> SupportPlanStatus:
        """ステータスのcompleted状態を更新する（テスト用ヘルパーメソッド）

        Args:
            db: データベースセッション
            status_id: ステータスID
            completed: 完了状態

        Returns:
            更新されたステータス

        Raises:
            NotFoundException: ステータスが見つからない場合
        """
        from sqlalchemy import select
        from app.core.exceptions import NotFoundException

        # ステータスを取得
        stmt = select(SupportPlanStatus).where(SupportPlanStatus.id == status_id)
        result = await db.execute(stmt)
        status = result.scalar_one_or_none()

        if not status:
            raise NotFoundException(f"ステータスID {status_id} が見つかりません。")

        # completedを更新
        status.completed = completed
        if completed:
            status.completed_at = datetime.datetime.now(datetime.timezone.utc)
        else:
            status.completed_at = None
            status.completed_by = None

        # カレンダーイベント削除フック
        if completed:
            from app.services.calendar_service import calendar_service
            from app.models.enums import CalendarEventType

            # final_plan_signed完了時: 更新期限イベントを削除
            if status.step_type == SupportPlanStep.final_plan_signed:
                logger.info(f"[CALENDAR_EVENT] Deleting renewal deadline event for cycle_id={status.plan_cycle_id}")
                try:
                    deleted = await calendar_service.delete_event_by_cycle(
                        db=db,
                        cycle_id=status.plan_cycle_id,
                        event_type=CalendarEventType.renewal_deadline
                    )
                    if deleted:
                        logger.info(f"[CALENDAR_EVENT] Renewal deadline event deleted for cycle_id={status.plan_cycle_id}")
                except Exception as e:
                    logger.warning(f"[CALENDAR_EVENT] Failed to delete renewal deadline event: {e}")

            # monitoring完了時: モニタリング期限イベントを削除
            if status.step_type == SupportPlanStep.monitoring:
                logger.info(f"[CALENDAR_EVENT] Deleting monitoring deadline event for status_id={status.id}")
                try:
                    deleted = await calendar_service.delete_event_by_status(
                        db=db,
                        status_id=status.id,
                        event_type=CalendarEventType.next_plan_start_date
                    )
                    if deleted:
                        logger.info(f"[CALENDAR_EVENT] Monitoring deadline event deleted for status_id={status.id}")
                except Exception as e:
                    logger.warning(f"[CALENDAR_EVENT] Failed to delete monitoring deadline event: {e}")

        await db.flush()
        return status

    @staticmethod
    async def get_deliverables_list(
        db: AsyncSession,
        current_user,
        office_id: UUID,
        search: str = None,
        recipient_ids: list[UUID] = None,
        deliverable_types: list[DeliverableType] = None,
        date_from: datetime.datetime = None,
        date_to: datetime.datetime = None,
        sort_by: str = "uploaded_at",
        sort_order: str = "desc",
        skip: int = 0,
        limit: int = 20,
    ):
        """
        PDF一覧を取得する

        Args:
            db: データベースセッション
            current_user: 現在のユーザー
            office_id: 事業所ID
            search: 検索キーワード
            recipient_ids: 利用者IDリスト
            deliverable_types: deliverable_typeリスト
            date_from: アップロード日時の開始
            date_to: アップロード日時の終了
            sort_by: ソート対象
            sort_order: ソート順
            skip: スキップ件数
            limit: 取得件数

        Returns:
            PlanDeliverableListResponse
        """
        from app.schemas.support_plan import (
            PlanDeliverableListResponse,
            PlanDeliverableListItem,
            WelfareRecipientBrief,
            StaffBrief,
            PlanCycleBrief,
        )
        from app.core import storage
        from app.core.config import settings

        # フィルター条件の構築
        filters = {}
        if search:
            filters["search"] = search
        if recipient_ids:
            filters["recipient_ids"] = recipient_ids
        if deliverable_types:
            filters["deliverable_types"] = deliverable_types
        if date_from:
            filters["date_from"] = date_from
        if date_to:
            filters["date_to"] = date_to

        # データ取得
        deliverables = await crud.support_plan.get_multi_deliverables_with_relations(
            db,
            office_id=office_id,
            filters=filters,
            sort_by=sort_by,
            sort_order=sort_order,
            skip=skip,
            limit=limit,
        )

        # 総件数取得
        total = await crud.support_plan.count_deliverables_with_filters(
            db,
            office_id=office_id,
            filters=filters,
        )

        # deliverable_typeの表示名マッピング
        DELIVERABLE_TYPE_DISPLAY = {
            DeliverableType.assessment_sheet: "アセスメントシート",
            DeliverableType.draft_plan_pdf: "計画書（原案）",
            DeliverableType.final_plan_signed_pdf: "計画書（署名済）",
            DeliverableType.staff_meeting_minutes: "担当者会議議事録",
            DeliverableType.monitoring_report_pdf: "モニタリング報告書",
        }

        # レスポンスデータの構築
        items = []
        for deliverable in deliverables:
            # S3パスから署名付きURL生成
            object_name = deliverable.file_path.replace(f"s3://{settings.S3_BUCKET_NAME}/", "")
            try:
                download_url = await storage.create_presigned_url(
                    object_name=object_name,
                    expiration=3600,  # 1時間
                    inline=True
                )
            except Exception as e:
                logger.warning(f"Failed to generate presigned URL for {object_name}: {e}")
                download_url = None

            # レスポンスオブジェクト作成
            item = PlanDeliverableListItem(
                id=deliverable.id,
                original_filename=deliverable.original_filename,
                file_path=deliverable.file_path,
                deliverable_type=deliverable.deliverable_type,
                deliverable_type_display=DELIVERABLE_TYPE_DISPLAY.get(
                    deliverable.deliverable_type,
                    deliverable.deliverable_type.value
                ),
                plan_cycle=PlanCycleBrief(
                    id=deliverable.plan_cycle.id,
                    cycle_number=deliverable.plan_cycle.cycle_number,
                    plan_cycle_start_date=deliverable.plan_cycle.plan_cycle_start_date,
                    next_renewal_deadline=deliverable.plan_cycle.next_renewal_deadline,
                    is_latest_cycle=deliverable.plan_cycle.is_latest_cycle,
                ),
                welfare_recipient=WelfareRecipientBrief(
                    id=deliverable.plan_cycle.welfare_recipient.id,
                    full_name=deliverable.plan_cycle.welfare_recipient.full_name,
                    full_name_furigana=deliverable.plan_cycle.welfare_recipient.full_name_furigana,
                ),
                uploaded_by=StaffBrief(
                    id=deliverable.uploaded_by_staff.id,
                    name=deliverable.uploaded_by_staff.full_name,
                    role=deliverable.uploaded_by_staff.role.value,
                ),
                uploaded_at=deliverable.uploaded_at,
                download_url=download_url,
            )
            items.append(item)

        # ページネーション情報
        has_more = (skip + limit) < total

        return PlanDeliverableListResponse(
            items=items,
            total=total,
            skip=skip,
            limit=limit,
            has_more=has_more,
        )


support_plan_service = SupportPlanService()
