"""カレンダー連携サービス

事業所のGoogleカレンダー連携設定を管理するサービス
- サービスアカウントJSONの処理
- 暗号化処理
- OfficeCalendarAccountの作成・更新・取得
- Google Calendar APIとの連携
- カレンダーイベントの作成・同期
"""

import json
import logging
from typing import Optional, Dict
from uuid import UUID
from datetime import datetime, date, time, timedelta
from zoneinfo import ZoneInfo
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from fastapi import HTTPException, status

from app.crud.crud_office_calendar_account import crud_office_calendar_account
from app.crud.crud_calendar_event import crud_calendar_event
from app.schemas.calendar_account import (
    CalendarSetupRequest,
    OfficeCalendarAccountCreate,
    OfficeCalendarAccountUpdate
)
from app.schemas.calendar_event import CalendarEventCreate, CalendarEventUpdate
from app.models.calendar_account import OfficeCalendarAccount
from app.models.calendar_events import CalendarEvent
from app.models.welfare_recipient import WelfareRecipient
from app.models.enums import (
    CalendarConnectionStatus,
    CalendarEventType,
    CalendarSyncStatus
)
from app.services.google_calendar_client import (
    GoogleCalendarClient,
    GoogleCalendarAuthenticationError,
    GoogleCalendarAPIError
)
from app.services.calendar.calendar_event_ledger_service import CalendarEventLedgerService
from app.services.calendar.google_calendar_gateway import GoogleCalendarGateway
from app.services.calendar.google_calendar_sync_service import GoogleCalendarSyncService
from app.messages import ja

logger = logging.getLogger(__name__)


class CalendarService:
    """カレンダー連携サービス"""

    def __init__(
        self,
        *,
        event_ledger_service: Optional[CalendarEventLedgerService] = None,
        google_sync_service: Optional[GoogleCalendarSyncService] = None,
        google_gateway: Optional[GoogleCalendarGateway] = None,
    ):
        self.event_ledger_service = event_ledger_service or CalendarEventLedgerService()
        self.google_gateway = google_gateway
        self.google_sync_service = google_sync_service or GoogleCalendarSyncService(
            gateway=google_gateway or self._google_gateway(),
            event_ledger_service=self.event_ledger_service,
        )

    def _google_gateway(self) -> GoogleCalendarGateway:
        return self.google_gateway or GoogleCalendarGateway(client_class=GoogleCalendarClient)

    async def setup_office_calendar(
        self,
        db: AsyncSession,
        request: CalendarSetupRequest
    ) -> OfficeCalendarAccount:
        """事業所のカレンダー連携を設定する

        Args:
            db: データベースセッション
            request: カレンダー設定リクエスト

        Returns:
            作成されたOfficeCalendarAccount

        Raises:
            ValueError: 既に設定が存在する場合
        """
        # 既に設定が存在するかチェック
        existing = await crud_office_calendar_account.get_by_office_id(
            db=db,
            office_id=request.office_id
        )
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=ja.SERVICE_CALENDAR_ALREADY_EXISTS.format(office_id=request.office_id)
            )

        # サービスアカウントメールアドレスを抽出
        service_account_email = self._extract_service_account_email(
            request.service_account_json
        )

        # OfficeCalendarAccountCreate スキーマを作成
        create_data = OfficeCalendarAccountCreate(
            office_id=request.office_id,
            google_calendar_id=request.google_calendar_id,
            calendar_name=request.calendar_name,
            service_account_key=request.service_account_json,  # 暗号化前のJSON
            service_account_email=service_account_email,
            connection_status=CalendarConnectionStatus.not_connected,
            auto_invite_staff=request.auto_invite_staff,
            default_reminder_minutes=request.default_reminder_minutes
        )

        # CRUDレイヤーで暗号化して保存
        account = await crud_office_calendar_account.create_with_encryption(
            db=db,
            obj_in=create_data
        )

        # flush()後にrefresh()を呼び出すと、非同期セッションの状態が不整合になり、greenletエラーを引き起こす
        # CRUDレイヤーで作成されたオブジェクトは既に全属性がロードされている
        await db.flush()

        return account

    async def update_office_calendar(
        self,
        db: AsyncSession,
        account_id: UUID,
        request: CalendarSetupRequest
    ) -> OfficeCalendarAccount:
        """事業所のカレンダー連携設定を更新する

        Args:
            db: データベースセッション
            account_id: 更新対象のアカウントID
            request: カレンダー設定リクエスト

        Returns:
            更新されたOfficeCalendarAccount

        Raises:
            HTTPException: アカウントが存在しない場合
        """
        # 既存のアカウントを取得
        existing = await crud_office_calendar_account.get(db=db, id=account_id)
        if not existing:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=ja.SERVICE_CALENDAR_NOT_FOUND.format(account_id=account_id)
            )

        # サービスアカウントメールアドレスを抽出
        service_account_email = self._extract_service_account_email(
            request.service_account_json
        )

        # OfficeCalendarAccountUpdate スキーマを作成
        update_data = OfficeCalendarAccountUpdate(
            google_calendar_id=request.google_calendar_id,
            calendar_name=request.calendar_name,
            service_account_key=request.service_account_json,
            service_account_email=service_account_email,
            auto_invite_staff=request.auto_invite_staff,
            default_reminder_minutes=request.default_reminder_minutes
        )

        # CRUDレイヤーで暗号化して更新
        account = await crud_office_calendar_account.update_with_encryption(
            db=db,
            db_obj=existing,
            obj_in=update_data
        )

        # flush()後にrefresh()を呼び出すと、非同期セッションの状態が不整合になり、greenletエラーを引き起こす
        # CRUDレイヤーで更新されたオブジェクトは既に全属性がロードされている
        await db.flush()

        return account

    async def get_office_calendar_by_office_id(
        self,
        db: AsyncSession,
        office_id: UUID
    ) -> Optional[OfficeCalendarAccount]:
        """事業所IDでカレンダー設定を取得する

        Args:
            db: データベースセッション
            office_id: 事業所ID

        Returns:
            OfficeCalendarAccount または None
        """
        return await crud_office_calendar_account.get_by_office_id(
            db=db,
            office_id=office_id
        )

    async def get_office_calendar_by_id(
        self,
        db: AsyncSession,
        account_id: UUID
    ) -> Optional[OfficeCalendarAccount]:
        """アカウントIDでカレンダー設定を取得する

        Args:
            db: データベースセッション
            account_id: アカウントID

        Returns:
            OfficeCalendarAccount または None
        """
        return await crud_office_calendar_account.get(db=db, id=account_id)

    async def update_connection_status(
        self,
        db: AsyncSession,
        account_id: UUID,
        status: CalendarConnectionStatus,
        error_message: Optional[str] = None
    ) -> Optional[OfficeCalendarAccount]:
        """カレンダー連携状態を更新する

        Args:
            db: データベースセッション
            account_id: アカウントID
            status: 新しい連携状態
            error_message: エラーメッセージ（任意）

        Returns:
            更新されたOfficeCalendarAccount または None
        """
        return await crud_office_calendar_account.update_connection_status(
            db=db,
            account_id=account_id,
            status=status,
            error_message=error_message
        )

    def _extract_service_account_email(self, service_account_json: str) -> str:
        """サービスアカウントJSONからclient_emailを抽出する

        Args:
            service_account_json: サービスアカウントJSON文字列

        Returns:
            client_emailの値

        Raises:
            HTTPException: client_emailが存在しない場合またはJSON形式が不正な場合
        """
        try:
            parsed = json.loads(service_account_json)
            client_email = parsed.get("client_email")
            if not client_email:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=ja.SERVICE_CLIENT_EMAIL_NOT_FOUND
                )
            return client_email
        except json.JSONDecodeError as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=ja.SERVICE_INVALID_JSON.format(error=str(e))
            )

    async def test_calendar_connection(
        self,
        db: AsyncSession,
        account_id: UUID
    ) -> bool:
        """カレンダー接続をテストして接続ステータスを更新する

        Args:
            db: データベースセッション
            account_id: カレンダーアカウントID

        Returns:
            接続成功時True、失敗時False

        Raises:
            HTTPException: アカウントが存在しない場合
        """
        # カレンダーアカウントを取得
        account = await crud_office_calendar_account.get(db=db, id=account_id)
        if not account:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=ja.SERVICE_CALENDAR_NOT_FOUND.format(account_id=account_id)
            )

        # refresh()を呼び出すと、非同期セッションの状態が不整合になり、greenletエラーを引き起こす
        # クエリ結果から直接属性にアクセス可能

        try:
            # サービスアカウントキーを復号化
            service_account_json = account.decrypt_service_account_key()
            if not service_account_json:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=ja.SERVICE_ACCOUNT_KEY_NOT_FOUND
                )

            logger.info("カレンダー接続テスト開始")

            # テストイベントを作成して接続を確認（すぐに削除）
            test_title = "Connection Test"
            test_description = "This is a connection test event"
            test_start = datetime.now()
            test_end = test_start + timedelta(hours=1)  # 23時台でもエラーが発生しないようにtimedeltaを使用

            google_gateway = self._google_gateway()
            event_id = google_gateway.create_event(
                service_account_json=service_account_json,
                calendar_id=account.google_calendar_id,
                title=test_title,
                description=test_description,
                start_datetime=test_start,
                end_datetime=test_end
            )

            # テストイベントを削除
            google_gateway.delete_event(
                service_account_json=service_account_json,
                calendar_id=account.google_calendar_id,
                event_id=event_id
            )

            # 接続ステータスを更新
            await crud_office_calendar_account.update_connection_status(
                db=db,
                account_id=account_id,
                status=CalendarConnectionStatus.connected,
                error_message=None
            )

            logger.info("カレンダー接続テスト成功")

            return True

        except (GoogleCalendarAuthenticationError, GoogleCalendarAPIError, Exception) as e:
            # 接続エラー
            error_message = str(e)
            logger.error("カレンダー接続テスト失敗: %s", type(e).__name__)

            await crud_office_calendar_account.update_connection_status(
                db=db,
                account_id=account_id,
                status=CalendarConnectionStatus.error,
                error_message=error_message
            )

            return False

    async def create_renewal_deadline_events(
        self,
        db: AsyncSession,
        office_id: UUID,
        welfare_recipient_id: UUID,
        cycle_id: int,
        next_renewal_deadline: date
    ) -> list[UUID]:
        """更新期限イベントを作成する（150日目～180日目の1イベント）

        1つのイベントで150日目9:00～180日目18:00の期間を表現します。
        これにより、更新期限の30日前から期限日までをカレンダー上で視覚的に確認できます。

        Args:
            db: データベースセッション
            office_id: 事業所ID
            welfare_recipient_id: 利用者ID
            cycle_id: サイクルID
            next_renewal_deadline: 更新期限日（180日目）

        Returns:
            作成されたイベントIDのリスト（1要素、またはカレンダー未設定時・重複時は空リスト）
        """
        return await self.event_ledger_service.create_renewal_deadline_events(
            db=db,
            office_id=office_id,
            welfare_recipient_id=welfare_recipient_id,
            cycle_id=cycle_id,
            next_renewal_deadline=next_renewal_deadline,
        )

    async def create_next_plan_start_date_events(
        self,
        db: AsyncSession,
        office_id: UUID,
        welfare_recipient_id: UUID,
        cycle_id: int,
        cycle_start_date: date,
        cycle_number: int,
        status_id: Optional[UUID] = None
    ) -> Optional[list[UUID]]:
        """次回計画開始期限イベントを作成する（1~7日の1イベント）

        Args:
            db: データベースセッション
            office_id: 事業所ID
            welfare_recipient_id: 利用者ID
            cycle_id: サイクルID
            cycle_start_date: サイクル開始日
            cycle_number: サイクル番号
            status_id: モニタリングステータスID（オプション）

        Returns:
            作成されたイベントIDのリスト、またはNone（status_id未指定の場合）
        """
        return await self.event_ledger_service.create_next_plan_start_date_events(
            db=db,
            office_id=office_id,
            welfare_recipient_id=welfare_recipient_id,
            cycle_id=cycle_id,
            cycle_start_date=cycle_start_date,
            cycle_number=cycle_number,
            status_id=status_id,
        )

    async def create_next_plan_start_date_event(
        self,
        db: AsyncSession,
        office_id: UUID,
        welfare_recipient_id: UUID,
        status_id: int,
        due_date: date
    ) -> Optional[UUID]:
        """モニタリング期限イベントを作成する（重複チェック付き）

        Args:
            db: データベースセッション
            office_id: 事業所ID
            welfare_recipient_id: 利用者ID
            status_id: ステータスID
            due_date: 期限日

        Returns:
            作成されたイベントのID、またはNone（カレンダー未設定時、または重複時）
        """
        # 重複チェック: 同じstatus_id + event_typeのイベントが既に存在するか
        existing_event_result = await db.execute(
            select(CalendarEvent).where(
                CalendarEvent.support_plan_status_id == status_id,
                CalendarEvent.event_type == CalendarEventType.next_plan_start_date
            )
        )
        existing_event = existing_event_result.scalar_one_or_none()

        if existing_event:
            logger.info(
                f"Monitoring deadline event already exists for status_id={status_id}. "
                f"Skipping creation."
            )
            return None

        # カレンダーアカウントを取得
        account = await crud_office_calendar_account.get_by_office_id(
            db=db,
            office_id=office_id
        )

        if not account:
            logger.warning(
                f"Calendar account not found for office {office_id}. "
                "Skipping event creation."
            )
            return None

        # refresh()を呼び出すと、非同期セッションの状態が不整合になり、greenletエラーを引き起こす
        # クエリ結果から直接属性にアクセス可能

        if account.connection_status != CalendarConnectionStatus.connected:
            logger.warning(
                f"Calendar account not connected for office {office_id}. "
                "Skipping event creation."
            )
            return None

        # 利用者情報を取得
        result = await db.execute(
            select(WelfareRecipient).where(WelfareRecipient.id == welfare_recipient_id)
        )
        recipient = result.scalar_one_or_none()

        if not recipient:
            logger.error("Welfare recipient not found")
            return None

        # ステータス情報からサイクル情報を取得（cycle_numberを取得するため）
        from app.models.support_plan_cycle import SupportPlanStatus, SupportPlanCycle
        status_result = await db.execute(
            select(SupportPlanStatus).where(SupportPlanStatus.id == status_id)
        )
        status = status_result.scalar_one_or_none()

        if not status:
            logger.error("Support plan status not found")
            return None

        # サイクル情報を取得
        cycle_result = await db.execute(
            select(SupportPlanCycle).where(SupportPlanCycle.id == status.plan_cycle_id)
        )
        cycle = cycle_result.scalar_one_or_none()

        if not cycle:
            logger.error("Support plan cycle not found")
            return None

        cycle_number = cycle.cycle_number

        # イベントタイトルを作成
        event_title = f"{recipient.last_name} {recipient.first_name} 次の個別支援計画の開始期限"

        # JST（日本時間）で明示的に指定
        jst = ZoneInfo("Asia/Tokyo")

        # イベント開始時刻: 期限日の9:00 JST
        event_start = datetime.combine(due_date, time(9, 0), tzinfo=jst)

        # イベント終了時刻: 期限日の18:00 JST
        event_end = datetime.combine(due_date, time(18, 0), tzinfo=jst)

        # カレンダーイベントを作成
        event_data = CalendarEventCreate(
            office_id=office_id,
            welfare_recipient_id=welfare_recipient_id,
            support_plan_status_id=status_id,
            event_type=CalendarEventType.next_plan_start_date,
            google_calendar_id=account.google_calendar_id,
            event_title=event_title,
            event_description=f"次の個別支援計画の開始期限です（{cycle_number}回目）。\n期限: {due_date}",
            event_start_datetime=event_start,
            event_end_datetime=event_end,
            sync_status=CalendarSyncStatus.pending
        )

        event = await crud_calendar_event.create(db=db, obj_in=event_data)
        await db.flush()

        return event.id

    async def delete_office_calendar(
        self,
        db: AsyncSession,
        account_id: UUID
    ) -> None:
        """事業所のカレンダー連携設定を削除する

        Args:
            db: データベースセッション
            account_id: 削除対象のアカウントID

        Raises:
            HTTPException: アカウントが存在しない場合
        """
        # 既存のアカウントを取得
        existing = await crud_office_calendar_account.get(db=db, id=account_id)
        if not existing:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=ja.SERVICE_CALENDAR_NOT_FOUND.format(account_id=account_id)
            )

        # アカウントを削除
        await crud_office_calendar_account.remove(db=db, id=account_id)

    async def sync_pending_events(
        self,
        db: AsyncSession,
        office_id: Optional[UUID] = None
    ) -> Dict[str, int]:
        """未同期イベントをGoogle Calendarに同期する

        Args:
            db: データベースセッション
            office_id: 事業所ID（指定時はその事業所のイベントのみ同期）

        Returns:
            同期結果の辞書 {"synced": 成功数, "failed": 失敗数}
        """
        self.google_sync_service.gateway = self._google_gateway()
        return await self.google_sync_service.sync_pending_events(
            db=db,
            office_id=office_id,
        )

    async def delete_event_by_cycle(
        self,
        db: AsyncSession,
        cycle_id: int,
        event_type: CalendarEventType
    ) -> bool:
        """cycleに紐づくカレンダーイベントを削除する

        Args:
            db: データベースセッション
            cycle_id: サイクルID
            event_type: イベントタイプ

        Returns:
            削除に成功した場合True、イベントが存在しない場合False
        """
        self.google_sync_service.gateway = self._google_gateway()
        return await self.google_sync_service.delete_event_by_cycle(
            db=db,
            cycle_id=cycle_id,
            event_type=event_type,
        )

    async def delete_event_by_status(
        self,
        db: AsyncSession,
        status_id: int,
        event_type: CalendarEventType
    ) -> bool:
        """statusに紐づくカレンダーイベントを削除する

        Args:
            db: データベースセッション
            status_id: ステータスID
            event_type: イベントタイプ

        Returns:
            削除に成功した場合True、イベントが存在しない場合False
        """
        self.google_sync_service.gateway = self._google_gateway()
        return await self.google_sync_service.delete_event_by_status(
            db=db,
            status_id=status_id,
            event_type=event_type,
        )


# シングルトンインスタンス
calendar_service = CalendarService()
