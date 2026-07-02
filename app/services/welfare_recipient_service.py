"""
Welfare Recipient Service

このサービスは利用者登録に関するビジネスロジックを管理します。
mini.mdの要件に基づいて、利用者情報と初期支援計画の一括作成を行います。
"""

from typing import Optional, List, Dict
from uuid import UUID
from sqlalchemy.orm import Session, selectinload
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import date
import uuid

from app.crud.crud_welfare_recipient import crud_welfare_recipient
from app.models.welfare_recipient import WelfareRecipient
from app.models.support_plan_cycle import SupportPlanCycle, SupportPlanStatus
from app.models.enums import SupportPlanStep, CYCLE_STEPS
from app.schemas.welfare_recipient import UserRegistrationRequest
from app.schemas.deadline_alert import DeadlineAlertResponse, DeadlineAlertItem
from app.core.exceptions import BadRequestException, InternalServerException
from app.services.welfare_recipient.deadline_alert_service import DeadlineAlertService
from app.services.welfare_recipient.support_plan_integrity_service import (
    SupportPlanIntegrityService,
)
from app.services.calendar.google_calendar_sync_service import GoogleCalendarSyncService
from app.services.calendar.support_plan_calendar_event_service import (
    support_plan_calendar_event_service,
)
from datetime import timedelta
import logging
import inspect
import asyncio

logger = logging.getLogger(__name__)

class WelfareRecipientService:
    """
    利用者登録サービス

    mini.mdの要件に基づいて以下の処理を行います：
    1. 利用者基本情報の作成
    2. 詳細情報（住所、緊急連絡先等）の作成
    3. 障害情報の作成
    4. 初期支援計画サイクルと全ステップステータスの一括作成
    5. 事業所との関連付け

    全ての処理は単一トランザクション内で実行され、
    エラー発生時は自動的にロールバックされます。
    """

    deadline_alert_service = DeadlineAlertService()
    support_plan_integrity_service = SupportPlanIntegrityService()

    @staticmethod
    async def create_recipient_with_initial_plan(
        db: AsyncSession,
        registration_data: UserRegistrationRequest,
        office_id: UUID
    ) -> WelfareRecipient:
        """
        利用者情報と初期支援計画の一括作成 (非同期)
        """
        try:
            # Pydanticによる型変換とバリデーションが完了しているため、手動バリデーションは不要

            # 2. 利用者基本情報の作成
            basic_info = registration_data.basic_info
            welfare_recipient = WelfareRecipient(
                first_name=basic_info.firstName,
                last_name=basic_info.lastName,
                first_name_furigana=basic_info.firstNameFurigana,
                last_name_furigana=basic_info.lastNameFurigana,
                birth_day=basic_info.birthDay,
                gender=basic_info.gender
            )
            db.add(welfare_recipient)
            await db.flush()  # IDを取得するためにflush

            # IMPORTANT: flush()直後にIDを変数に保存する
            # その後の処理（flush等）でオブジェクトがexpired状態になり、
            # 再度welfare_recipient.idにアクセスするとgreenletエラーが発生するため
            recipient_id = welfare_recipient.id
            # 3. 関連データの作成
            await crud_welfare_recipient.create_related_data(
                db=db,
                welfare_recipient=welfare_recipient,
                registration_data=registration_data,
                office_id=office_id
            )

            # 4. 初期支援計画の作成（mini.mdの要件）
            # 既に保存したrecipient_idを使用（welfare_recipient.idに再アクセスしない）
            await WelfareRecipientService._create_initial_support_plan(db, recipient_id, office_id)

            # 5. IDを返す (コミット/ロールバックは呼び出し元で行う)
            return recipient_id

        except IntegrityError as e:
            logger.error("create_recipient_with_initial_plan integrity error: %s", type(e).__name__)
            # トランザクション管理は呼び出し元（エンドポイント層）で行うため、ここではrollbackしない
            raise BadRequestException("データの整合性エラーが発生しました。")

        except SQLAlchemyError as e:
            logger.error("create_recipient_with_initial_plan database error: %s", type(e).__name__)
            # トランザクション管理は呼び出し元（エンドポイント層）で行うため、ここではrollbackしない
            raise InternalServerException("データベースエラーが発生しました")

        except Exception as e:
            logger.error("create_recipient_with_initial_plan failed: %s", type(e).__name__)
            # トランザクション管理は呼び出し元（エンドポイント層）で行うため、ここではrollbackしない
            raise

    @staticmethod
    def _validate_registration_data(registration_data: UserRegistrationRequest) -> None:
        """
        登録データのバリデーション (Pydanticに移行したため、現在は未使用)
        """
        # Pydanticスキーマでほとんどのバリデーションが行われるようになったため、
        # この手動バリデーションは不要になります。
        # カスタムのクロスフィールドバリデーションが必要な場合のみ残します。
        pass

    @staticmethod
    async def _create_initial_support_plan(db: AsyncSession, welfare_recipient_id: UUID, office_id: UUID) -> None:
        """
        利用者作成時の初期支援計画 (サイクル + ステータス) を作成する (非同期)。
        サイクル番号に応じて作成するステップを変更する。
        カレンダーイベントも自動作成する。
        """
        # 既存のサイクル数を取得して新しいサイクル番号を決定
        count_stmt = select(func.count()).select_from(SupportPlanCycle).where(SupportPlanCycle.welfare_recipient_id == welfare_recipient_id)
        existing_cycles_count = (await db.execute(count_stmt)).scalar_one()
        new_cycle_number = existing_cycles_count + 1

        cycle = SupportPlanCycle(
            welfare_recipient_id=welfare_recipient_id,
            office_id=office_id,
            is_latest_cycle=True,
            cycle_number=new_cycle_number,
            plan_cycle_start_date=date.today(),
            next_renewal_deadline=date.today() + timedelta(days=180)
        )
        db.add(cycle)
        await db.flush()  # cycle.id を取得するため

        for i, step in enumerate(CYCLE_STEPS):
            status = SupportPlanStatus(
                plan_cycle_id=cycle.id,
                welfare_recipient_id=welfare_recipient_id,
                office_id=office_id,
                step_type=step,
                completed=False,
                is_latest_status=(i == 0)  # 最初のステップを最新にする
            )
            db.add(status)

        await db.flush()

        # カレンダーイベントを自動作成（ベストエフォート：失敗してもサイクル作成は継続）
        try:
            from sqlalchemy.exc import IntegrityError as SQLAlchemyIntegrityError

            try:
                await support_plan_calendar_event_service.create_cycle_events(
                    db=db,
                    cycle=cycle,
                )
            except SQLAlchemyIntegrityError:
                logger.warning("[DEBUG] Calendar deadline event already exists")
            except Exception as e:
                logger.warning("[DEBUG] Could not create calendar deadline events: %s", type(e).__name__)

        except Exception as e:
            # カレンダーイベント作成の予期しないエラー
            logger.error("[DEBUG] Unexpected error during calendar event creation: %s", type(e).__name__)
            # カレンダーイベント作成の失敗は利用者登録を妨げない

    @staticmethod
    def _create_initial_support_plan_sync(db: Session, welfare_recipient_id: UUID) -> None:
        """
        利用者作成時の初期支援計画 (サイクル + ステータス) を作成する (同期版)。
        """
        # 既存のサイクル数を取得して新しいサイクル番号を決定
        count_stmt = select(func.count()).select_from(SupportPlanCycle).where(SupportPlanCycle.welfare_recipient_id == welfare_recipient_id)
        existing_cycles_count = db.execute(count_stmt).scalar_one()
        new_cycle_number = existing_cycles_count + 1

        cycle = SupportPlanCycle(
            welfare_recipient_id=welfare_recipient_id,
            is_latest_cycle=True,
            cycle_number=new_cycle_number,
            plan_cycle_start_date=date.today(),
            next_renewal_deadline=date.today() + timedelta(days=180)
        )
        db.add(cycle)
        db.flush()  # cycle.id を取得するため

        for i, step in enumerate(CYCLE_STEPS):
            status = SupportPlanStatus(
                plan_cycle_id=cycle.id,
                step_type=step,
                completed=False,
                is_latest_status=(i == 0)  # 最初のステップを最新にする
            )
            db.add(status)

        db.flush()

    # ... (check_data_integrity, repair_support_plan_data, _repair_missing_statuses は同期のまま)
    @staticmethod
    def check_data_integrity(db: Session, welfare_recipient_id: UUID) -> dict:
        return WelfareRecipientService.support_plan_integrity_service.check_data_integrity(
            db,
            welfare_recipient_id,
        )

    @staticmethod
    def repair_support_plan_data(db: Session, welfare_recipient_id: UUID) -> bool:
        return WelfareRecipientService.support_plan_integrity_service.repair_support_plan_data(
            db,
            welfare_recipient_id,
        )

    @staticmethod
    def _repair_missing_statuses(db: Session, welfare_recipient_id: UUID) -> None:
        WelfareRecipientService.support_plan_integrity_service.repair_missing_statuses(
            db,
            welfare_recipient_id,
        )

    @staticmethod
    async def create_recipient_with_details(db: AsyncSession, registration_data: UserRegistrationRequest, office_id: UUID, **kwargs):
        """非同期の作成メソッドを呼び出すラッパー"""
        return await WelfareRecipientService.create_recipient_with_initial_plan(
            db=db,
            registration_data=registration_data,
            office_id=office_id,
            **kwargs
        )

    def check_and_repair_plan_data(self, db, welfare_recipient_id):
        return self.support_plan_integrity_service.check_and_repair_plan_data(
            db,
            welfare_recipient_id,
        )

    async def repair_recipient_support_plan(self, db: AsyncSession, welfare_recipient_id: uuid.UUID, performed_by: uuid.UUID | None = None) -> tuple[bool, str]:
        original_repair_method = getattr(
            self.support_plan_integrity_service,
            "repair_missing_statuses_async",
            None,
        )

        async def repair_missing_statuses_proxy(**kwargs):
            return await self._repair_missing_statuses_async(
                db=kwargs["db"],
                welfare_recipient_id=kwargs["welfare_recipient_id"],
                latest_cycle=kwargs["latest_cycle"],
            )

        self.support_plan_integrity_service.repair_missing_statuses_async = (
            repair_missing_statuses_proxy
        )
        try:
            return await self.support_plan_integrity_service.repair_recipient_support_plan(
                db=db,
                welfare_recipient_id=welfare_recipient_id,
                performed_by=performed_by,
            )
        finally:
            if original_repair_method is not None:
                self.support_plan_integrity_service.repair_missing_statuses_async = (
                    original_repair_method
                )

    async def _repair_missing_statuses_async(self, db: AsyncSession, welfare_recipient_id: uuid.UUID, latest_cycle: SupportPlanCycle) -> int:
        return await SupportPlanIntegrityService().repair_missing_statuses_async(
            db=db,
            welfare_recipient_id=welfare_recipient_id,
            latest_cycle=latest_cycle,
        )

    async def delete_recipient(
        self,
        db: AsyncSession,
        recipient_id: UUID
    ) -> bool:
        """利用者を削除（関連カレンダーイベントもGoogle Calendarから削除）

        【責務の説明】
        利用者削除には2つのアプローチがあります：
        1. crud層の `delete_with_cascade`: データベースのみの削除（CASCADE削除を含む）
        2. services層の `delete_recipient`（このメソッド）: ビジネスロジックを含む削除

        このメソッドを使うべき理由：
        - Google Calendar APIを呼び出してクラウド側からもイベントを削除する
        - データベースのCASCADEだけでは、Google Calendar上のイベントは削除されない
        - カレンダーイベントの完全な削除（DB + Google Calendar）を保証する

        Args:
            db: データベースセッション
            recipient_id: 利用者ID

        Returns:
            削除成功フラグ
        """
        try:
            deleted_count = await GoogleCalendarSyncService().delete_google_events_for_recipient(
                db=db,
                recipient_id=recipient_id,
            )
            logger.debug("[DEBUG] Deleted %s Google Calendar events for recipient", deleted_count)
        except Exception as e:
            logger.warning(
                "[DEBUG] Failed to delete Google Calendar events for recipient: %s",
                type(e).__name__,
            )

        recipient = await db.get(WelfareRecipient, recipient_id)
        if recipient:
            await db.delete(recipient)
            await db.flush()
            return True

        logger.warning("[DEBUG] delete_recipient END: recipient not found")
        return False

    @staticmethod
    async def get_deadline_alerts(
        db: AsyncSession,
        office_id: UUID,
        threshold_days: int = 30,
        limit: Optional[int] = None,
        offset: int = 0
    ) -> DeadlineAlertResponse:
        return await WelfareRecipientService.deadline_alert_service.get_deadline_alerts(
            db=db,
            office_id=office_id,
            threshold_days=threshold_days,
            limit=limit,
            offset=offset,
        )

    @staticmethod
    async def get_deadline_alerts_batch(
        db: AsyncSession,
        office_ids: List[UUID],
        threshold_days: int = 30
    ) -> Dict[UUID, DeadlineAlertResponse]:
        return await WelfareRecipientService.deadline_alert_service.get_deadline_alerts_batch(
            db=db,
            office_ids=office_ids,
            threshold_days=threshold_days,
        )

    @staticmethod
    async def get_staffs_by_offices_batch(
        db: AsyncSession,
        office_ids: List[UUID]
    ) -> Dict[UUID, List]:
        """
        複数事業所のスタッフを一括取得

        Args:
            db: データベースセッション
            office_ids: 事業所IDのリスト

        Returns:
            {office_id: [Staff, ...]} の辞書
        """
        import os
        from app.models.staff import Staff
        from app.models.office import OfficeStaff

        if not office_ids:
            return {}

        # テスト環境かどうかをチェック
        is_testing = os.getenv("TESTING") == "1"

        # office_idsに紐づく全スタッフを一括取得
        conditions = [
            OfficeStaff.office_id.in_(office_ids),
            Staff.deleted_at.is_(None),
            Staff.email.isnot(None)
        ]
        if not is_testing:
            conditions.append(Staff.is_test_data == False)

        stmt = (
            select(Staff, OfficeStaff.office_id)
            .join(OfficeStaff, OfficeStaff.staff_id == Staff.id)
            .where(*conditions)
            .distinct()  # 重複を防ぐ（同じofficeに複数のOfficeStaffレコードがある場合）
            .order_by(OfficeStaff.office_id.asc(), Staff.full_name.asc())
        )

        result = await db.execute(stmt)
        rows = result.all()

        # 事業所ごとにスタッフをグループ化
        staffs_by_office: Dict[UUID, List] = {office_id: [] for office_id in office_ids}
        for staff, office_id in rows:
            staffs_by_office[office_id].append(staff)

        return staffs_by_office


welfare_recipient_service = WelfareRecipientService()
__all__ = ["WelfareRecipientService", "welfare_recipient_service"]
