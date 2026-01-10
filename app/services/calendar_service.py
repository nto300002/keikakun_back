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
from app.messages import ja

logger = logging.getLogger(__name__)


class CalendarService:
    """カレンダー連携サービス"""

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

            logger.info("=" * 80)
            logger.info("カレンダー接続テスト開始")
            logger.info(f"  カレンダーID: {account.google_calendar_id}")
            logger.info(f"  カレンダー名: {account.calendar_name}")
            logger.info("=" * 80)

            # Google Calendar APIクライアントを作成して認証
            client = GoogleCalendarClient(service_account_json)
            client.authenticate()

            # テストイベントを作成して接続を確認（すぐに削除）
            test_title = "Connection Test"
            test_description = "This is a connection test event"
            test_start = datetime.now()
            test_end = test_start + timedelta(hours=1)  # 23時台でもエラーが発生しないようにtimedeltaを使用

            logger.info("テストイベント作成開始...")
            event_id = client.create_event(
                calendar_id=account.google_calendar_id,
                title=test_title,
                description=test_description,
                start_datetime=test_start,
                end_datetime=test_end
            )
            logger.info(f"テストイベント作成成功: {event_id}")

            # テストイベントを削除
            logger.info("テストイベント削除開始...")
            client.delete_event(
                calendar_id=account.google_calendar_id,
                event_id=event_id
            )
            logger.info("テストイベント削除成功")

            # 接続ステータスを更新
            await crud_office_calendar_account.update_connection_status(
                db=db,
                account_id=account_id,
                status=CalendarConnectionStatus.connected,
                error_message=None
            )

            logger.info("カレンダー接続テスト成功")
            logger.info("=" * 80)

            return True

        except (GoogleCalendarAuthenticationError, GoogleCalendarAPIError, Exception) as e:
            # 接続エラー
            error_message = str(e)
            logger.error("=" * 80)
            logger.error("カレンダー接続テスト失敗")
            logger.error(f"  エラー: {error_message}")
            logger.error("=" * 80)

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
        logger.info(f"[DEBUG] create_renewal_deadline_events START: office_id={office_id}, cycle_id={cycle_id}")

        # 重複チェック: 同じcycle_id + event_typeのイベントが既に存在するか
        # ※ SELECT文なので、現在のトランザクション内の変更も含めて検索される
        logger.info("[DEBUG] Checking for duplicate events...")
        existing_event_result = await db.execute(
            select(CalendarEvent).where(
                CalendarEvent.support_plan_cycle_id == cycle_id,
                CalendarEvent.event_type == CalendarEventType.renewal_deadline
            ).limit(1)
        )
        existing_event = existing_event_result.scalar_one_or_none()

        if existing_event:
            logger.info(
                f"Renewal deadline event already exists for cycle_id={cycle_id} (event_id={existing_event.id}). "
                f"Skipping creation."
            )
            return []

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
            return []

        # 属性を事前に取得（ループ内でアクセスするとgreenletエラーが発生するため）
        account_calendar_id = account.google_calendar_id
        account_status = account.connection_status

        if account_status != CalendarConnectionStatus.connected:
            logger.warning(
                f"Calendar account not connected for office {office_id}. "
                "Skipping event creation."
            )
            return []

        # 利用者情報を取得
        result = await db.execute(
            select(WelfareRecipient).where(WelfareRecipient.id == welfare_recipient_id)
        )
        recipient = result.scalar_one_or_none()

        if not recipient:
            logger.error(f"Welfare recipient {welfare_recipient_id} not found")
            return []

        # サイクル情報を取得（cycle_numberを取得するため）
        from app.models.support_plan_cycle import SupportPlanCycle
        cycle_result = await db.execute(
            select(SupportPlanCycle).where(SupportPlanCycle.id == cycle_id)
        )
        cycle = cycle_result.scalar_one_or_none()

        if not cycle:
            logger.error(f"Support plan cycle {cycle_id} not found")
            return []

        # 利用者名とサイクル番号を事前に取得
        recipient_last_name = recipient.last_name
        recipient_first_name = recipient.first_name
        cycle_number = cycle.cycle_number
        event_title = f"{recipient_last_name} {recipient_first_name} 更新期限まで残り1ヶ月"

        # 1つのイベントで150日目9:00～180日目18:00の期間を表現
        # JST（日本時間）で明示的に指定
        jst = ZoneInfo("Asia/Tokyo")

        # 開始: 150日目の9:00 JST
        event_start_date = date.today() + timedelta(days=150)
        event_start = datetime.combine(event_start_date, time(9, 0), tzinfo=jst)

        # 終了: 180日目（更新期限日）の18:00 JST
        event_end = datetime.combine(next_renewal_deadline, time(18, 0), tzinfo=jst)

        event = CalendarEvent(
            office_id=office_id,
            welfare_recipient_id=welfare_recipient_id,
            support_plan_cycle_id=cycle_id,
            event_type=CalendarEventType.renewal_deadline,
            google_calendar_id=account_calendar_id,
            event_title=event_title,
            event_description=f"個別支援計画の更新期限です（{cycle_number}回目）。\n期限: {next_renewal_deadline}",
            event_start_datetime=event_start,
            event_end_datetime=event_end,
            created_by_system=True,
            sync_status=CalendarSyncStatus.pending
        )
        db.add(event)

        await db.flush()

        logger.info(f"[DEBUG] create_renewal_deadline_events END: created event_id={event.id}")
        return [event.id]

    async def create_monitoring_deadline_events(
        self,
        db: AsyncSession,
        office_id: UUID,
        welfare_recipient_id: UUID,
        cycle_id: int,
        cycle_start_date: date,
        cycle_number: int,
        status_id: Optional[UUID] = None
    ) -> Optional[list[UUID]]:
        """モニタリング期限イベントを複数作成する（cycle_number>=2の場合、1~7日の1イベント）

        Args:
            db: データベースセッション
            office_id: 事業所ID
            welfare_recipient_id: 利用者ID
            cycle_id: サイクルID
            cycle_start_date: サイクル開始日
            cycle_number: サイクル番号
            status_id: モニタリングステータスID（オプション）

        Returns:
            作成されたイベントIDのリスト、またはNone（cycle_number=1の場合）
        """
        logger.info(f"[DEBUG] create_monitoring_deadline_events START: cycle_number={cycle_number}, cycle_id={cycle_id}")

        # cycle_number=1の場合は作成しない
        if cycle_number < 2:
            logger.info(f"[DEBUG] Skipping monitoring events for cycle_number={cycle_number}")
            return None

        # status_idが指定されていない場合はイベントを作成しない
        if not status_id:
            logger.warning("status_id is None. Cannot create monitoring event without status_id.")
            return []

        # 重複チェック: 同じstatus_id + event_typeのイベントが既に存在するか
        logger.info("[DEBUG] Checking for duplicate monitoring events...")
        existing_event_result = await db.execute(
            select(CalendarEvent).where(
                CalendarEvent.support_plan_status_id == status_id,
                CalendarEvent.event_type == CalendarEventType.monitoring_deadline
            ).limit(1)
        )
        existing_event = existing_event_result.scalar_one_or_none()

        if existing_event:
            logger.info(
                f"Monitoring deadline event already exists for status_id={status_id} (event_id={existing_event.id}). "
                f"Skipping creation."
            )
            return []

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
            return []

        # 属性を事前に取得（ループ内でアクセスするとgreenletエラーが発生するため）
        account_calendar_id = account.google_calendar_id
        account_status = account.connection_status

        if account_status != CalendarConnectionStatus.connected:
            logger.warning(
                f"Calendar account not connected for office {office_id}. "
                "Skipping event creation."
            )
            return []

        # 利用者情報を取得
        result = await db.execute(
            select(WelfareRecipient).where(WelfareRecipient.id == welfare_recipient_id)
        )
        recipient = result.scalar_one_or_none()

        if not recipient:
            logger.error(f"Welfare recipient {welfare_recipient_id} not found")
            return []

        # 利用者名を事前に取得
        recipient_last_name = recipient.last_name
        recipient_first_name = recipient.first_name
        event_title = f"{recipient_last_name} {recipient_first_name} 次の個別支援計画の開始期限"

        # 1つのイベントで登録日当日9:00～7日後18:00の期間（1週間）を表現
        # JST（日本時間）で明示的に指定
        jst = ZoneInfo("Asia/Tokyo")

        # 開始: cycle開始日（登録日当日）の9:00 JST
        event_start_date = cycle_start_date
        event_start = datetime.combine(event_start_date, time(9, 0), tzinfo=jst)

        # 終了: cycle開始7日後の18:00 JST
        event_end_date = cycle_start_date + timedelta(days=7)
        event_end = datetime.combine(event_end_date, time(18, 0), tzinfo=jst)

        event = CalendarEvent(
            office_id=office_id,
            welfare_recipient_id=welfare_recipient_id,
            support_plan_status_id=status_id,
            event_type=CalendarEventType.monitoring_deadline,
            google_calendar_id=account_calendar_id,
            event_title=event_title,
            event_description=f"次の個別支援計画の開始期限です（{cycle_number}回目）。",
            event_start_datetime=event_start,
            event_end_datetime=event_end,
            created_by_system=True,
            sync_status=CalendarSyncStatus.pending
        )
        db.add(event)

        await db.flush()

        logger.info(
            f"[DEBUG] create_monitoring_deadline_events END: "
            f"created event_id={event.id}, cycle_id={cycle_id}, status_id={status_id}"
        )
        return [event.id]

    async def create_monitoring_deadline_event(
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
                CalendarEvent.event_type == CalendarEventType.monitoring_deadline
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
            logger.error(f"Welfare recipient {welfare_recipient_id} not found")
            return None

        # ステータス情報からサイクル情報を取得（cycle_numberを取得するため）
        from app.models.support_plan_cycle import SupportPlanStatus, SupportPlanCycle
        status_result = await db.execute(
            select(SupportPlanStatus).where(SupportPlanStatus.id == status_id)
        )
        status = status_result.scalar_one_or_none()

        if not status:
            logger.error(f"Support plan status {status_id} not found")
            return None

        # サイクル情報を取得
        cycle_result = await db.execute(
            select(SupportPlanCycle).where(SupportPlanCycle.id == status.plan_cycle_id)
        )
        cycle = cycle_result.scalar_one_or_none()

        if not cycle:
            logger.error(f"Support plan cycle {status.plan_cycle_id} not found")
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
            event_type=CalendarEventType.monitoring_deadline,
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
        synced_count = 0
        failed_count = 0

        # 未同期イベントを取得
        pending_events = await crud_calendar_event.get_pending_sync_events(db=db)

        # office_idが指定されている場合はフィルタ
        if office_id:
            pending_events = [e for e in pending_events if e.office_id == office_id]

        if not pending_events:
            return {"synced": 0, "failed": 0}

        # 事業所ごとにグループ化
        events_by_office: Dict[UUID, list] = {}
        for event in pending_events:
            if event.office_id not in events_by_office:
                events_by_office[event.office_id] = []
            events_by_office[event.office_id].append(event)

        # 事業所ごとに同期
        for office_id, events in events_by_office.items():
            # カレンダーアカウントを取得
            account = await crud_office_calendar_account.get_by_office_id(
                db=db,
                office_id=office_id
            )

            if not account:
                # 全イベントを失敗としてマーク
                for event in events:
                    update_data = CalendarEventUpdate(
                        sync_status=CalendarSyncStatus.failed,
                        last_error_message="Calendar account not found",
                        last_sync_at=datetime.now()
                    )
                    await crud_calendar_event.update(db=db, db_obj=event, obj_in=update_data)
                    failed_count += 1
                continue

            # refresh()を呼び出すと、非同期セッションの状態が不整合になり、greenletエラーを引き起こす
            # クエリ結果から直接属性にアクセス可能

            if account.connection_status != CalendarConnectionStatus.connected:
                # 全イベントを失敗としてマーク
                for event in events:
                    update_data = CalendarEventUpdate(
                        sync_status=CalendarSyncStatus.failed,
                        last_error_message="Calendar account not connected",
                        last_sync_at=datetime.now()
                    )
                    await crud_calendar_event.update(db=db, db_obj=event, obj_in=update_data)
                    failed_count += 1
                continue

            # サービスアカウントキーを復号化
            try:
                service_account_json = account.decrypt_service_account_key()
                if not service_account_json:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=ja.SERVICE_ACCOUNT_KEY_NOT_FOUND
                    )

                # Google Calendar APIクライアントを作成
                client = GoogleCalendarClient(service_account_json)
                client.authenticate()

            except Exception as e:
                # 全イベントを失敗としてマーク
                for event in events:
                    update_data = CalendarEventUpdate(
                        sync_status=CalendarSyncStatus.failed,
                        last_error_message=f"Authentication failed: {str(e)}",
                        last_sync_at=datetime.now()
                    )
                    await crud_calendar_event.update(db=db, db_obj=event, obj_in=update_data)
                    failed_count += 1
                continue

            # イベントごとに同期
            for event in events:
                try:
                    # Google Calendarにイベントを作成
                    google_event_id = client.create_event(
                        calendar_id=event.google_calendar_id,
                        title=event.event_title,
                        description=event.event_description,
                        start_datetime=event.event_start_datetime,
                        end_datetime=event.event_end_datetime
                    )

                    # イベントを更新
                    update_data = CalendarEventUpdate(
                        google_event_id=google_event_id,
                        sync_status=CalendarSyncStatus.synced,
                        last_sync_at=datetime.now(),
                        last_error_message=None
                    )
                    await crud_calendar_event.update(db=db, db_obj=event, obj_in=update_data)

                    synced_count += 1

                except (GoogleCalendarAPIError, Exception) as e:
                    # イベントを失敗としてマーク
                    update_data = CalendarEventUpdate(
                        sync_status=CalendarSyncStatus.failed,
                        last_error_message=str(e),
                        last_sync_at=datetime.now()
                    )
                    await crud_calendar_event.update(db=db, db_obj=event, obj_in=update_data)
                    failed_count += 1

        return {"synced": synced_count, "failed": failed_count}

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
        logger.info(f"[DEBUG] delete_event_by_cycle START: cycle_id={cycle_id}, event_type={event_type}")

        # イベントを検索
        result = await db.execute(
            select(CalendarEvent).where(
                CalendarEvent.support_plan_cycle_id == cycle_id,
                CalendarEvent.event_type == event_type
            )
        )
        event = result.scalar_one_or_none()

        if not event:
            logger.info(f"[DEBUG] No event found for cycle_id={cycle_id}, event_type={event_type}")
            return False

        # Google Calendarからイベントを削除（google_event_idがある場合のみ）
        if event.google_event_id:
            try:
                # カレンダーアカウントを取得
                account = await crud_office_calendar_account.get_by_office_id(
                    db=db,
                    office_id=event.office_id
                )

                if account and account.connection_status == CalendarConnectionStatus.connected:
                    # Google Calendar APIクライアントで削除
                    client = google_calendar_client
                    client.authenticate(account.service_account_key)
                    await client.delete_event(
                        calendar_id=event.google_calendar_id,
                        event_id=event.google_event_id
                    )
                    logger.info(f"[DEBUG] Deleted event from Google Calendar: {event.google_event_id}")
            except Exception as e:
                logger.warning(f"[DEBUG] Failed to delete event from Google Calendar: {e}")
                # Google Calendar削除失敗してもDBからは削除する

        # DBからイベントを削除
        await db.delete(event)
        await db.flush()

        logger.info(f"[DEBUG] delete_event_by_cycle END: event_id={event.id} deleted")
        return True

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
        logger.info(f"[DEBUG] delete_event_by_status START: status_id={status_id}, event_type={event_type}")

        # イベントを検索
        result = await db.execute(
            select(CalendarEvent).where(
                CalendarEvent.support_plan_status_id == status_id,
                CalendarEvent.event_type == event_type
            )
        )
        event = result.scalar_one_or_none()

        if not event:
            logger.info(f"[DEBUG] No event found for status_id={status_id}, event_type={event_type}")
            return False

        # Google Calendarからイベントを削除（google_event_idがある場合のみ）
        if event.google_event_id:
            try:
                # カレンダーアカウントを取得
                account = await crud_office_calendar_account.get_by_office_id(
                    db=db,
                    office_id=event.office_id
                )

                if account and account.connection_status == CalendarConnectionStatus.connected:
                    # Google Calendar APIクライアントで削除
                    client = google_calendar_client
                    client.authenticate(account.service_account_key)
                    await client.delete_event(
                        calendar_id=event.google_calendar_id,
                        event_id=event.google_event_id
                    )
                    logger.info(f"[DEBUG] Deleted event from Google Calendar: {event.google_event_id}")
            except Exception as e:
                logger.warning(f"[DEBUG] Failed to delete event from Google Calendar: {e}")
                # Google Calendar削除失敗してもDBからは削除する

        # DBからイベントを削除
        await db.delete(event)
        await db.flush()

        logger.info(f"[DEBUG] delete_event_by_status END: event_id={event.id} deleted")
        return True


# シングルトンインスタンス
calendar_service = CalendarService()
