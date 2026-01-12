import pytest
import json
import os
from unittest.mock import patch, MagicMock
from uuid import uuid4
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from fastapi import HTTPException

from app.services.calendar_service import calendar_service
from app.schemas.calendar_account import CalendarSetupRequest
from app.db.session import AsyncSessionLocal
from app.models.office import Office
from app.models.staff import Staff
from app.models.calendar_account import OfficeCalendarAccount
from app.models.enums import OfficeType, StaffRole, CalendarConnectionStatus
from app.core.security import get_password_hash


pytestmark = pytest.mark.asyncio


@pytest.fixture
async def setup_staff_and_office(db_session: AsyncSession):
    """テスト用のスタッフと事業所を作成して返すフィクスチャ

    Returns:
        tuple: (staff, office, staff_id, office_id) のタプル
    """
    staff = Staff(
        first_name="管理者",
        last_name="テスト",
        full_name="テスト 管理者",
        email=f"test_admin_{uuid4()}@example.com",
        hashed_password=get_password_hash("password"),
        role=StaffRole.owner,
    )
    db_session.add(staff)
    await db_session.flush()

    # IDを事前に取得
    staff_id = staff.id

    office = Office(
        name="テスト事業所",
        type=OfficeType.type_A_office,
        created_by=staff_id,
        last_modified_by=staff_id,
    )
    db_session.add(office)
    await db_session.flush()

    # IDを事前に取得（expire前に）
    office_id = office.id

    await db_session.refresh(staff)
    await db_session.refresh(office)

    # タプルでIDも一緒に返す
    return staff, office, staff_id, office_id


@pytest.fixture
def valid_service_account_json() -> str:
    """有効なサービスアカウントJSON"""
    return json.dumps({
        "type": "service_account",
        "project_id": "test-project-123456",
        "private_key_id": "test-key-id-123456",
        "private_key": "-----BEGIN PRIVATE KEY-----\nMIIEvQIBADANBgkqhkiG9w0BAQEFAASCBKcwggSjAgEAAoIBAQC...\n-----END PRIVATE KEY-----\n",
        "client_email": "test-account@test-project-123456.iam.gserviceaccount.com",
        "client_id": "123456789012345678901",
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
        "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
        "client_x509_cert_url": "https://www.googleapis.com/robot/v1/metadata/x509/test-account%40test-project-123456.iam.gserviceaccount.com"
    })


@pytest.fixture
def invalid_service_account_json() -> str:
    """不完全なサービスアカウントJSON（client_emailが欠落）"""
    return json.dumps({
        "type": "service_account",
        "project_id": "test-project-123456",
        "private_key_id": "test-key-id-123456",
        "private_key": "-----BEGIN PRIVATE KEY-----\ntest\n-----END PRIVATE KEY-----\n",
        # client_emailが欠落
    })


class TestCalendarService:
    """calendar_service のテスト"""

    async def test_setup_office_calendar_success(
        self,
        db_session: AsyncSession,
        setup_staff_and_office,
        valid_service_account_json: str
    ):
        """正常系: カレンダー連携設定が正しく作成されること"""
        _, office, _, office_id = setup_staff_and_office

        # 一意のgoogle_calendar_idを生成
        unique_calendar_id = f"test-calendar-{uuid4().hex[:8]}@group.calendar.google.com"

        # リクエストデータ作成
        setup_request = CalendarSetupRequest(
            office_id=office_id,
            google_calendar_id=unique_calendar_id,
            service_account_json=valid_service_account_json,
            calendar_name="テスト事業所カレンダー",
            auto_invite_staff=True,
            default_reminder_minutes=1440
        )

        # サービス層を呼び出し
        result = await calendar_service.setup_office_calendar(db=db_session, request=setup_request)

        # アサーション
        assert result is not None
        assert result.office_id == office_id
        assert result.google_calendar_id == unique_calendar_id
        assert result.calendar_name == "テスト事業所カレンダー"
        assert result.service_account_email == "test-account@test-project-123456.iam.gserviceaccount.com"
        assert result.connection_status == CalendarConnectionStatus.not_connected
        assert result.auto_invite_staff is True

        # 暗号化されたキーが保存されていることを確認
        assert result.service_account_key is not None
        assert result.service_account_key != valid_service_account_json  # 暗号化されている

        # 復号化して元のJSONと一致することを確認
        decrypted_json = result.decrypt_service_account_key()
        assert json.loads(decrypted_json) == json.loads(valid_service_account_json)

    async def test_setup_office_calendar_duplicate_office(
        self,
        db_session: AsyncSession,
        setup_staff_and_office,
        valid_service_account_json: str
    ):
        """異常系: 同じ事業所で既に設定されている場合はエラー"""
        _, office, _, office_id = setup_staff_and_office

        # 一意のgoogle_calendar_idを生成
        unique_calendar_id = f"test-calendar-{uuid4().hex[:8]}@group.calendar.google.com"

        # 1回目の設定
        setup_request = CalendarSetupRequest(
            office_id=office_id,
            google_calendar_id=unique_calendar_id,
            service_account_json=valid_service_account_json
        )
        await calendar_service.setup_office_calendar(db=db_session, request=setup_request)

        # 2回目の設定（重複エラーを期待）
        with pytest.raises(HTTPException) as exc_info:
            await calendar_service.setup_office_calendar(db=db_session, request=setup_request)
        assert exc_info.value.status_code == 400
        assert "既にカレンダーアカウントを持っています" in str(exc_info.value.detail)

    async def test_setup_office_calendar_invalid_json(
        self,
        db_session: AsyncSession,
        setup_staff_and_office,
        invalid_service_account_json: str
    ):
        """異常系: 不正なサービスアカウントJSONの場合はバリデーションエラー"""
        _, office, _, office_id = setup_staff_and_office

        # 不完全なJSONでリクエスト作成を試みる（Pydanticバリデーションで失敗するはず）
        from pydantic import ValidationError
        with pytest.raises(ValidationError, match="必須フィールドがありません"):
            setup_request = CalendarSetupRequest(
                office_id=office_id,
                google_calendar_id="test-calendar@group.calendar.google.com",
                service_account_json=invalid_service_account_json
            )

    async def test_extract_service_account_email(
        self,
        valid_service_account_json: str
    ):
        """ユーティリティ: service_account_emailが正しく抽出されること"""
        email = calendar_service._extract_service_account_email(valid_service_account_json)
        assert email == "test-account@test-project-123456.iam.gserviceaccount.com"

    async def test_extract_service_account_email_missing(self):
        """異常系: client_emailが存在しない場合はHTTPException"""
        invalid_json = json.dumps({"type": "service_account", "project_id": "test"})
        with pytest.raises(HTTPException) as exc_info:
            calendar_service._extract_service_account_email(invalid_json)
        assert exc_info.value.status_code == 400
        assert "client_emailが見つかりません" in str(exc_info.value.detail)

    async def test_update_office_calendar_success(
        self,
        db_session: AsyncSession,
        setup_staff_and_office,
        valid_service_account_json: str
    ):
        """正常系: カレンダー連携設定が更新されること"""
        _, office, _, office_id = setup_staff_and_office

        # 一意のgoogle_calendar_idを生成
        unique_calendar_id = f"test-calendar-{uuid4().hex[:8]}@group.calendar.google.com"

        # 初回設定
        setup_request = CalendarSetupRequest(
            office_id=office_id,
            google_calendar_id=unique_calendar_id,
            service_account_json=valid_service_account_json,
            calendar_name="初期名"
        )
        initial_result = await calendar_service.setup_office_calendar(db=db_session, request=setup_request)

        # IDを事前に取得
        initial_result_id = initial_result.id

        # 更新
        update_request = CalendarSetupRequest(
            office_id=office_id,
            google_calendar_id=unique_calendar_id,
            service_account_json=valid_service_account_json,
            calendar_name="更新後の名前"
        )
        updated_result = await calendar_service.update_office_calendar(
            db=db_session,
            account_id=initial_result_id,
            request=update_request
        )

        # アサーション
        assert updated_result.id == initial_result_id
        assert updated_result.calendar_name == "更新後の名前"
        assert updated_result.office_id == office_id

    async def test_get_office_calendar_by_office_id(
        self,
        db_session: AsyncSession,
        setup_staff_and_office,
        valid_service_account_json: str
    ):
        """正常系: 事業所IDでカレンダー設定を取得できること"""
        _, office, _, office_id = setup_staff_and_office

        # 一意のgoogle_calendar_idを生成
        unique_calendar_id = f"test-calendar-{uuid4().hex[:8]}@group.calendar.google.com"

        # 設定作成
        setup_request = CalendarSetupRequest(
            office_id=office_id,
            google_calendar_id=unique_calendar_id,
            service_account_json=valid_service_account_json
        )
        created = await calendar_service.setup_office_calendar(db=db_session, request=setup_request)

        # IDを事前に取得
        created_id = created.id

        # 取得
        retrieved = await calendar_service.get_office_calendar_by_office_id(db=db_session, office_id=office_id)

        # IDを事前に取得
        retrieved_id = retrieved.id if retrieved else None

        # アサーション
        assert retrieved is not None
        assert retrieved_id == created_id
        assert retrieved.office_id == office_id

    async def test_get_office_calendar_by_office_id_not_found(
        self,
        db_session: AsyncSession,
        setup_staff_and_office
    ):
        """正常系: 存在しない事業所IDの場合はNoneを返す"""
        _, office, _, office_id = setup_staff_and_office

        # 未設定の事業所で取得
        retrieved = await calendar_service.get_office_calendar_by_office_id(db=db_session, office_id=office_id)

        # アサーション
        assert retrieved is None

    # ==================== Phase 2: イベント作成機能のテスト ====================

    async def test_create_renewal_deadline_event_success(
        self,
        db_session: AsyncSession,
        setup_staff_and_office,
        valid_service_account_json: str
    ):
        """正常系: 更新期限イベントが正しく作成されること"""
        from datetime import date, timedelta
        from app.models.support_plan_cycle import SupportPlanCycle
        from app.models.welfare_recipient import WelfareRecipient
        from app.models.enums import GenderType, CalendarEventType, CalendarSyncStatus
        from app import crud

        staff, office, staff_id, office_id = setup_staff_and_office

        # カレンダー設定を作成
        unique_calendar_id = f"test-calendar-{uuid4().hex[:8]}@group.calendar.google.com"
        setup_request = CalendarSetupRequest(
            office_id=office_id,
            google_calendar_id=unique_calendar_id,
            service_account_json=valid_service_account_json,
            calendar_name="テスト事業所カレンダー"
        )
        account = await calendar_service.setup_office_calendar(db=db_session, request=setup_request)
        await calendar_service.update_connection_status(
            db=db_session,
            account_id=account.id,
            status=CalendarConnectionStatus.connected
        )

        # 利用者を作成
        recipient = WelfareRecipient(
            first_name="太郎",
            last_name="山田",
            first_name_furigana="たろう",
            last_name_furigana="やまだ",
            birth_day=date(1990, 1, 1),
            gender=GenderType.male
        )
        db_session.add(recipient)
        await db_session.flush()

        # サイクルを作成
        next_renewal = date.today() + timedelta(days=30)
        cycle = SupportPlanCycle(
            welfare_recipient_id=recipient.id,
            office_id=office_id,
            plan_cycle_start_date=date.today(),
            next_renewal_deadline=next_renewal
        )
        db_session.add(cycle)
        await db_session.flush()

        # イベント作成（150日目～180日目の1イベント）
        event_ids = await calendar_service.create_renewal_deadline_events(
            db=db_session,
            office_id=office_id,
            welfare_recipient_id=recipient.id,
            cycle_id=cycle.id,
            next_renewal_deadline=next_renewal
        )

        # アサーション
        assert event_ids is not None
        assert len(event_ids) == 1  # 1つのイベントが作成される

        # イベントが作成されたか確認
        event = await crud.calendar_event.get(db=db_session, id=event_ids[0])
        assert event is not None
        assert event.event_type == CalendarEventType.renewal_deadline
        assert event.welfare_recipient_id == recipient.id
        assert event.support_plan_cycle_id == cycle.id
        assert event.sync_status == CalendarSyncStatus.pending
        assert f"{recipient.last_name} {recipient.first_name}" in event.event_title

    async def test_create_next_plan_start_date_event_success(
        self,
        db_session: AsyncSession,
        setup_staff_and_office,
        valid_service_account_json: str
    ):
        """正常系: モニタリング期限イベントが正しく作成されること"""
        from datetime import date, timedelta
        from app.models.support_plan_cycle import SupportPlanCycle, SupportPlanStatus
        from app.models.welfare_recipient import WelfareRecipient
        from app.models.enums import GenderType, CalendarEventType, CalendarSyncStatus, SupportPlanStep
        from app import crud

        staff, office, staff_id, office_id = setup_staff_and_office

        # カレンダー設定を作成
        unique_calendar_id = f"test-calendar-{uuid4().hex[:8]}@group.calendar.google.com"
        setup_request = CalendarSetupRequest(
            office_id=office_id,
            google_calendar_id=unique_calendar_id,
            service_account_json=valid_service_account_json,
            calendar_name="テスト事業所カレンダー"
        )
        account = await calendar_service.setup_office_calendar(db=db_session, request=setup_request)
        await calendar_service.update_connection_status(
            db=db_session,
            account_id=account.id,
            status=CalendarConnectionStatus.connected
        )

        # 利用者を作成
        recipient = WelfareRecipient(
            first_name="花子",
            last_name="佐藤",
            first_name_furigana="はなこ",
            last_name_furigana="さとう",
            birth_day=date(1985, 5, 15),
            gender=GenderType.female
        )
        db_session.add(recipient)
        await db_session.flush()

        # サイクルとステータスを作成
        cycle = SupportPlanCycle(
            welfare_recipient_id=recipient.id,
            office_id=office_id,
            plan_cycle_start_date=date.today()
        )
        db_session.add(cycle)
        await db_session.flush()

        due_date = date.today() + timedelta(days=7)
        status = SupportPlanStatus(
            plan_cycle_id=cycle.id,
            welfare_recipient_id=recipient.id,
            office_id=office_id,
            step_type=SupportPlanStep.monitoring,
            due_date=due_date
        )
        db_session.add(status)
        await db_session.flush()

        # イベント作成
        event_id = await calendar_service.create_next_plan_start_date_event(
            db=db_session,
            office_id=office_id,
            welfare_recipient_id=recipient.id,
            status_id=status.id,
            due_date=due_date
        )

        # アサーション
        assert event_id is not None

        # イベントが作成されたか確認
        event = await crud.calendar_event.get(db=db_session, id=event_id)
        assert event is not None
        assert event.event_type == CalendarEventType.next_plan_start_date
        assert event.welfare_recipient_id == recipient.id
        assert event.support_plan_status_id == status.id
        assert event.sync_status == CalendarSyncStatus.pending
        assert f"{recipient.last_name} {recipient.first_name}" in event.event_title

    async def test_create_event_without_calendar_account(
        self,
        db_session: AsyncSession,
        setup_staff_and_office
    ):
        """異常系: カレンダー設定がない場合はNoneを返す"""
        from datetime import date, timedelta
        from app.models.support_plan_cycle import SupportPlanCycle
        from app.models.welfare_recipient import WelfareRecipient
        from app.models.enums import GenderType

        staff, office, staff_id, office_id = setup_staff_and_office

        # カレンダー設定なし

        # 利用者を作成
        recipient = WelfareRecipient(
            first_name="次郎",
            last_name="鈴木",
            first_name_furigana="じろう",
            last_name_furigana="すずき",
            birth_day=date(1992, 3, 20),
            gender=GenderType.male
        )
        db_session.add(recipient)
        await db_session.flush()

        # サイクルを作成
        next_renewal = date.today() + timedelta(days=30)
        cycle = SupportPlanCycle(
            welfare_recipient_id=recipient.id,
            office_id=office_id,
            plan_cycle_start_date=date.today(),
            next_renewal_deadline=next_renewal
        )
        db_session.add(cycle)
        await db_session.flush()

        # イベント作成（カレンダー設定がないので空リスト）
        event_ids = await calendar_service.create_renewal_deadline_events(
            db=db_session,
            office_id=office_id,
            welfare_recipient_id=recipient.id,
            cycle_id=cycle.id,
            next_renewal_deadline=next_renewal
        )

        # アサーション
        assert event_ids == []

    async def test_sync_pending_events_success(
        self,
        db_session: AsyncSession,
        setup_staff_and_office,
        valid_service_account_json: str
    ):
        """正常系: 未同期イベントがGoogle Calendarに同期されること"""
        from datetime import date, datetime, timedelta
        from app.models.support_plan_cycle import SupportPlanCycle
        from app.models.welfare_recipient import WelfareRecipient
        from app.models.enums import GenderType, CalendarEventType, CalendarSyncStatus
        from app.models.calendar_events import CalendarEvent
        from app import crud
        from unittest.mock import patch, MagicMock

        staff, office, staff_id, office_id = setup_staff_and_office

        # カレンダー設定を作成
        unique_calendar_id = f"test-calendar-{uuid4().hex[:8]}@group.calendar.google.com"
        setup_request = CalendarSetupRequest(
            office_id=office_id,
            google_calendar_id=unique_calendar_id,
            service_account_json=valid_service_account_json,
            calendar_name="テスト事業所カレンダー"
        )
        account = await calendar_service.setup_office_calendar(db=db_session, request=setup_request)
        await calendar_service.update_connection_status(
            db=db_session,
            account_id=account.id,
            status=CalendarConnectionStatus.connected
        )

        # 利用者を作成
        recipient = WelfareRecipient(
            first_name="三郎",
            last_name="田中",
            first_name_furigana="さぶろう",
            last_name_furigana="たなか",
            birth_day=date(1988, 7, 10),
            gender=GenderType.male
        )
        db_session.add(recipient)
        await db_session.flush()

        # サイクルとイベントを作成
        cycle = SupportPlanCycle(
            welfare_recipient_id=recipient.id,
            office_id=office_id,
            plan_cycle_start_date=date.today(),
            next_renewal_deadline=date.today() + timedelta(days=30)
        )
        db_session.add(cycle)
        await db_session.flush()

        # 未同期イベントを直接作成
        event = CalendarEvent(
            office_id=office_id,
            welfare_recipient_id=recipient.id,
            support_plan_cycle_id=cycle.id,
            event_type=CalendarEventType.renewal_deadline,
            google_calendar_id=unique_calendar_id,
            event_title="テストイベント",
            event_start_datetime=datetime.now(),
            event_end_datetime=datetime.now() + timedelta(hours=1),
            sync_status=CalendarSyncStatus.pending
        )
        db_session.add(event)
        await db_session.flush()

        # Google Calendar APIクライアントをモック
        with patch('app.services.calendar_service.GoogleCalendarClient') as mock_client_class:
            mock_client = MagicMock()
            mock_client.create_event.return_value = "google-event-id-123"
            mock_client_class.return_value = mock_client

            # 同期実行
            result = await calendar_service.sync_pending_events(db=db_session, office_id=office_id)

            # アサーション
            assert result is not None
            assert result["synced"] >= 1
            assert result["failed"] == 0

            # イベントの同期状態を確認
            await db_session.refresh(event)
            assert event.sync_status == CalendarSyncStatus.synced
            assert event.google_event_id == "google-event-id-123"
            assert event.last_sync_at is not None

    async def test_sync_pending_events_with_api_error(
        self,
        db_session: AsyncSession,
        setup_staff_and_office,
        valid_service_account_json: str
    ):
        """異常系: Google Calendar APIエラー時にステータスがfailedになること"""
        from datetime import date, datetime, timedelta
        from app.models.support_plan_cycle import SupportPlanCycle
        from app.models.welfare_recipient import WelfareRecipient
        from app.models.enums import GenderType, CalendarEventType, CalendarSyncStatus
        from app.models.calendar_events import CalendarEvent
        from app import crud
        from unittest.mock import patch, MagicMock
        from app.services.google_calendar_client import GoogleCalendarAPIError

        staff, office, staff_id, office_id = setup_staff_and_office

        # カレンダー設定を作成
        unique_calendar_id = f"test-calendar-{uuid4().hex[:8]}@group.calendar.google.com"
        setup_request = CalendarSetupRequest(
            office_id=office_id,
            google_calendar_id=unique_calendar_id,
            service_account_json=valid_service_account_json,
            calendar_name="テスト事業所カレンダー"
        )
        account = await calendar_service.setup_office_calendar(db=db_session, request=setup_request)
        await calendar_service.update_connection_status(
            db=db_session,
            account_id=account.id,
            status=CalendarConnectionStatus.connected
        )

        # 利用者を作成
        recipient = WelfareRecipient(
            first_name="四郎",
            last_name="高橋",
            first_name_furigana="しろう",
            last_name_furigana="たかはし",
            birth_day=date(1995, 11, 25),
            gender=GenderType.male
        )
        db_session.add(recipient)
        await db_session.flush()

        # サイクルとイベントを作成
        cycle = SupportPlanCycle(
            welfare_recipient_id=recipient.id,
            office_id=office_id,
            plan_cycle_start_date=date.today(),
            next_renewal_deadline=date.today() + timedelta(days=30)
        )
        db_session.add(cycle)
        await db_session.flush()

        # 未同期イベントを直接作成
        event = CalendarEvent(
            office_id=office_id,
            welfare_recipient_id=recipient.id,
            support_plan_cycle_id=cycle.id,
            event_type=CalendarEventType.renewal_deadline,
            google_calendar_id=unique_calendar_id,
            event_title="テストイベント",
            event_start_datetime=datetime.now(),
            event_end_datetime=datetime.now() + timedelta(hours=1),
            sync_status=CalendarSyncStatus.pending
        )
        db_session.add(event)
        await db_session.flush()

        # Google Calendar APIクライアントをモック（エラーを発生させる）
        with patch('app.services.calendar_service.GoogleCalendarClient') as mock_client_class:
            mock_client = MagicMock()
            mock_client.create_event.side_effect = GoogleCalendarAPIError("API Error")
            mock_client_class.return_value = mock_client

            # 同期実行
            result = await calendar_service.sync_pending_events(db=db_session, office_id=office_id)

            # アサーション
            assert result is not None
            assert result["synced"] == 0
            assert result["failed"] >= 1

            # イベントの同期状態を確認
            await db_session.refresh(event)
            assert event.sync_status == CalendarSyncStatus.failed
            assert event.google_event_id is None
            assert "API Error" in event.last_error_message

    async def test_delete_office_calendar_success(
        self,
        db_session: AsyncSession,
        setup_staff_and_office,
        valid_service_account_json: str
    ):
        """正常系: カレンダー設定を削除できること"""
        _, office, _, office_id = setup_staff_and_office

        # カレンダー設定を作成
        unique_calendar_id = f"test-calendar-{uuid4().hex[:8]}@group.calendar.google.com"
        setup_request = CalendarSetupRequest(
            office_id=office_id,
            google_calendar_id=unique_calendar_id,
            service_account_json=valid_service_account_json
        )
        account = await calendar_service.setup_office_calendar(db=db_session, request=setup_request)
        account_id = account.id

        # 削除
        await calendar_service.delete_office_calendar(db=db_session, account_id=account_id)

        # 削除されたことを確認
        deleted_account = await calendar_service.get_office_calendar_by_id(db=db_session, account_id=account_id)
        assert deleted_account is None

    async def test_delete_office_calendar_not_found(
        self,
        db_session: AsyncSession
    ):
        """異常系: 存在しないカレンダーアカウントIDで削除しようとするとHTTPException"""
        non_existent_id = uuid4()

        with pytest.raises(HTTPException) as exc_info:
            await calendar_service.delete_office_calendar(db=db_session, account_id=non_existent_id)
        assert exc_info.value.status_code == 404
        assert "が見つかりません" in str(exc_info.value.detail)

    # ==================== 新要件: 複数イベント作成機能のテスト ====================

    async def test_create_renewal_deadline_events_multiple(
        self,
        db_session: AsyncSession,
        setup_staff_and_office,
        valid_service_account_json: str
    ):
        """正常系: 更新期限イベントが150日目～180日目の1イベントとして作成されること"""
        from datetime import date, time, timedelta
        from app.models.support_plan_cycle import SupportPlanCycle
        from app.models.welfare_recipient import WelfareRecipient
        from app.models.enums import GenderType, CalendarEventType, CalendarSyncStatus
        from app import crud
        from sqlalchemy import select
        from app.models.calendar_events import CalendarEvent

        staff, office, staff_id, office_id = setup_staff_and_office

        # カレンダー設定を作成
        unique_calendar_id = f"test-calendar-{uuid4().hex[:8]}@group.calendar.google.com"
        setup_request = CalendarSetupRequest(
            office_id=office_id,
            google_calendar_id=unique_calendar_id,
            service_account_json=valid_service_account_json,
            calendar_name="テスト事業所カレンダー"
        )
        account = await calendar_service.setup_office_calendar(db=db_session, request=setup_request)
        await calendar_service.update_connection_status(
            db=db_session,
            account_id=account.id,
            status=CalendarConnectionStatus.connected
        )

        # 利用者を作成
        recipient = WelfareRecipient(
            first_name="五郎",
            last_name="伊藤",
            first_name_furigana="ごろう",
            last_name_furigana="いとう",
            birth_day=date(1993, 8, 20),
            gender=GenderType.male
        )
        db_session.add(recipient)
        await db_session.flush()

        # サイクルを作成
        next_renewal = date.today() + timedelta(days=180)
        cycle = SupportPlanCycle(
            welfare_recipient_id=recipient.id,
            office_id=office_id,
            plan_cycle_start_date=date.today(),
            next_renewal_deadline=next_renewal,
            cycle_number=1
        )
        db_session.add(cycle)
        await db_session.flush()

        # 更新期限イベントを作成（150日目～180日目の1イベント）
        event_ids = await calendar_service.create_renewal_deadline_events(
            db=db_session,
            office_id=office_id,
            welfare_recipient_id=recipient.id,
            cycle_id=cycle.id,
            next_renewal_deadline=next_renewal
        )

        # アサーション
        assert event_ids is not None
        assert len(event_ids) == 1  # 1つのイベントが作成される

        # イベントが正しく作成されたか確認
        event = await crud.calendar_event.get(db=db_session, id=event_ids[0])
        assert event is not None
        assert event.event_type == CalendarEventType.renewal_deadline
        assert event.welfare_recipient_id == recipient.id
        assert event.support_plan_cycle_id == cycle.id
        assert event.sync_status == CalendarSyncStatus.pending
        assert f"{recipient.last_name} {recipient.first_name}" in event.event_title

        # イベント期間が150日目～180日目であることを確認
        # DBから取得した値はJSTで保存されているので、そのまま比較
        from zoneinfo import ZoneInfo
        jst = ZoneInfo("Asia/Tokyo")

        # JSTで保存されているので、JSTタイムゾーンで比較
        expected_start_date = date.today() + timedelta(days=150)
        expected_end_date = date.today() + timedelta(days=180)

        # タイムゾーンを揃えて比較（JSTとして）
        event_start_jst = event.event_start_datetime.astimezone(jst)
        event_end_jst = event.event_end_datetime.astimezone(jst)

        assert event_start_jst.date() == expected_start_date
        assert event_end_jst.date() == expected_end_date
        assert event_start_jst.time() == time(9, 0)
        assert event_end_jst.time() == time(18, 0)

    async def test_create_next_plan_start_date_events_for_cycle_2_or_more(
        self,
        db_session: AsyncSession,
        setup_staff_and_office,
        valid_service_account_json: str
    ):
        """正常系: cycle_number>=2の場合、モニタリング期限イベントが1日目～7日目の1イベントとして作成されること"""
        from datetime import date, time, timedelta
        from app.models.support_plan_cycle import SupportPlanCycle
        from app.models.welfare_recipient import WelfareRecipient
        from app.models.enums import GenderType, CalendarEventType, CalendarSyncStatus
        from app import crud
        from sqlalchemy import select
        from app.models.calendar_events import CalendarEvent

        staff, office, staff_id, office_id = setup_staff_and_office

        # カレンダー設定を作成
        unique_calendar_id = f"test-calendar-{uuid4().hex[:8]}@group.calendar.google.com"
        setup_request = CalendarSetupRequest(
            office_id=office_id,
            google_calendar_id=unique_calendar_id,
            service_account_json=valid_service_account_json,
            calendar_name="テスト事業所カレンダー"
        )
        account = await calendar_service.setup_office_calendar(db=db_session, request=setup_request)
        await calendar_service.update_connection_status(
            db=db_session,
            account_id=account.id,
            status=CalendarConnectionStatus.connected
        )

        # 利用者を作成
        recipient = WelfareRecipient(
            first_name="六郎",
            last_name="渡辺",
            first_name_furigana="ろくろう",
            last_name_furigana="わたなべ",
            birth_day=date(1990, 12, 5),
            gender=GenderType.male
        )
        db_session.add(recipient)
        await db_session.flush()

        # サイクルを作成（cycle_number=2）
        cycle_start = date.today()
        cycle = SupportPlanCycle(
            welfare_recipient_id=recipient.id,
            office_id=office_id,
            plan_cycle_start_date=cycle_start,
            next_renewal_deadline=cycle_start + timedelta(days=180),
            cycle_number=2
        )
        db_session.add(cycle)
        await db_session.flush()

        # monitoringステータスを作成
        from app.models.support_plan_cycle import SupportPlanStatus
        from app.models.enums import SupportPlanStep
        status = SupportPlanStatus(
            welfare_recipient_id=recipient.id,
            plan_cycle_id=cycle.id,
            office_id=office_id,
            step_type=SupportPlanStep.monitoring,
            completed=False
        )
        db_session.add(status)
        await db_session.flush()

        # モニタリング期限イベントを作成（1日目～7日目の1イベント）
        event_ids = await calendar_service.create_next_plan_start_date_events(
            db=db_session,
            office_id=office_id,
            welfare_recipient_id=recipient.id,
            cycle_id=cycle.id,
            cycle_start_date=cycle_start,
            cycle_number=cycle.cycle_number,
            status_id=status.id
        )

        # アサーション
        assert event_ids is not None
        assert len(event_ids) == 1  # 1つのイベントが作成される

        # イベントが正しく作成されたか確認
        event = await crud.calendar_event.get(db=db_session, id=event_ids[0])
        assert event is not None
        assert event.event_type == CalendarEventType.next_plan_start_date
        assert event.welfare_recipient_id == recipient.id
        assert event.support_plan_status_id == status.id
        assert event.sync_status == CalendarSyncStatus.pending
        assert f"{recipient.last_name} {recipient.first_name}" in event.event_title

        # イベント期間が登録日から1週間（7日間）であることを厳重に確認
        # DBから取得した値はJSTで保存されているので、JSTで比較
        from zoneinfo import ZoneInfo
        jst = ZoneInfo("Asia/Tokyo")

        # タイムゾーンを揃えて比較（JSTとして）
        event_start_jst = event.event_start_datetime.astimezone(jst)
        event_end_jst = event.event_end_datetime.astimezone(jst)

        # JSTでの日付を確認
        expected_start_date = cycle_start  # 登録日当日
        expected_end_date = cycle_start + timedelta(days=7)  # 7日後

        assert event_start_jst.date() == expected_start_date, \
            f"開始日が期待値と異なります。期待: {expected_start_date}, 実際: {event_start_jst.date()}"
        assert event_end_jst.date() == expected_end_date, \
            f"終了日が期待値と異なります。期待: {expected_end_date}, 実際: {event_end_jst.date()}"

        # JSTでの時刻を確認
        assert event_start_jst.time() == time(9, 0), \
            f"開始時刻が9:00(JST)ではありません: {event_start_jst.time()}"
        assert event_end_jst.time() == time(18, 0), \
            f"終了時刻が18:00(JST)ではありません: {event_end_jst.time()}"

        # イベント期間が正確に7日間であることを確認
        event_duration_days = (event_end_jst.date() - event_start_jst.date()).days
        assert event_duration_days == 7, \
            f"イベント期間が7日間ではありません。実際: {event_duration_days}日間"

        # 具体的な日付範囲を確認（例：10/19開始なら10/19～10/26まで）
        print(f"\n[DEBUG] モニタリング期限イベント:")
        print(f"  cycle_start_date: {cycle_start}")
        print(f"  event_start (JST): {event_start_jst}")
        print(f"  event_end (JST): {event_end_jst}")
        print(f"  期間: {event_duration_days}日間（{expected_start_date} ～ {expected_end_date}）")

    async def test_create_next_plan_start_date_events_for_cycle_1_not_created(
        self,
        db_session: AsyncSession,
        setup_staff_and_office,
        valid_service_account_json: str
    ):
        """正常系: cycle_number=1の場合、モニタリング期限イベントは作成されないこと"""
        from datetime import date, timedelta
        from app.models.support_plan_cycle import SupportPlanCycle
        from app.models.welfare_recipient import WelfareRecipient
        from app.models.enums import GenderType

        staff, office, staff_id, office_id = setup_staff_and_office

        # カレンダー設定を作成
        unique_calendar_id = f"test-calendar-{uuid4().hex[:8]}@group.calendar.google.com"
        setup_request = CalendarSetupRequest(
            office_id=office_id,
            google_calendar_id=unique_calendar_id,
            service_account_json=valid_service_account_json,
            calendar_name="テスト事業所カレンダー"
        )
        account = await calendar_service.setup_office_calendar(db=db_session, request=setup_request)
        await calendar_service.update_connection_status(
            db=db_session,
            account_id=account.id,
            status=CalendarConnectionStatus.connected
        )

        # 利用者を作成
        recipient = WelfareRecipient(
            first_name="七郎",
            last_name="中村",
            first_name_furigana="ななろう",
            last_name_furigana="なかむら",
            birth_day=date(1987, 3, 15),
            gender=GenderType.male
        )
        db_session.add(recipient)
        await db_session.flush()

        # サイクルを作成（cycle_number=1）
        cycle_start = date.today()
        cycle = SupportPlanCycle(
            welfare_recipient_id=recipient.id,
            office_id=office_id,
            plan_cycle_start_date=cycle_start,
            next_renewal_deadline=cycle_start + timedelta(days=180),
            cycle_number=1
        )
        db_session.add(cycle)
        await db_session.flush()

        # モニタリング期限イベントを作成（cycle_number=1なので作成されない）
        event_ids = await calendar_service.create_next_plan_start_date_events(
            db=db_session,
            office_id=office_id,
            welfare_recipient_id=recipient.id,
            cycle_id=cycle.id,
            cycle_start_date=cycle_start,
            cycle_number=cycle.cycle_number
        )

        # アサーション: cycle_number=1なのでNoneまたは空リスト
        assert event_ids is None or len(event_ids) == 0

    async def test_multiple_recipients_same_date_calendar_events(
        self,
        db_session: AsyncSession,
        setup_staff_and_office,
        valid_service_account_json: str
    ):
        """正常系: 複数利用者（4人）の更新期限が同じ日付でも独立してイベントが登録されること"""
        from datetime import date, time, timedelta
        from app.models.support_plan_cycle import SupportPlanCycle
        from app.models.welfare_recipient import WelfareRecipient
        from app.models.enums import GenderType, CalendarEventType, CalendarSyncStatus
        from app import crud
        from sqlalchemy import select
        from app.models.calendar_events import CalendarEvent

        staff, office, staff_id, office_id = setup_staff_and_office

        # カレンダー設定を作成
        unique_calendar_id = f"test-calendar-{uuid4().hex[:8]}@group.calendar.google.com"
        setup_request = CalendarSetupRequest(
            office_id=office_id,
            google_calendar_id=unique_calendar_id,
            service_account_json=valid_service_account_json,
            calendar_name="テスト事業所カレンダー"
        )
        account = await calendar_service.setup_office_calendar(db=db_session, request=setup_request)
        await calendar_service.update_connection_status(
            db=db_session,
            account_id=account.id,
            status=CalendarConnectionStatus.connected
        )

        # 4人の利用者を作成
        recipients = []
        recipient_data = [
            ("太郎", "田中", "たろう", "たなか", date(1990, 1, 1), GenderType.male),
            ("花子", "佐藤", "はなこ", "さとう", date(1985, 5, 15), GenderType.female),
            ("次郎", "鈴木", "じろう", "すずき", date(1992, 3, 20), GenderType.male),
            ("三郎", "高橋", "さぶろう", "たかはし", date(1988, 7, 10), GenderType.male),
        ]

        for first_name, last_name, first_furigana, last_furigana, birth_day, gender in recipient_data:
            recipient = WelfareRecipient(
                first_name=first_name,
                last_name=last_name,
                first_name_furigana=first_furigana,
                last_name_furigana=last_furigana,
                birth_day=birth_day,
                gender=gender
            )
            db_session.add(recipient)
            await db_session.flush()
            recipients.append(recipient)

        # 全員同じ更新期限日を設定
        same_renewal_deadline = date.today() + timedelta(days=180)

        # 各利用者に対してサイクルとイベントを作成
        event_ids_list = []
        cycles = []
        for recipient in recipients:
            cycle = SupportPlanCycle(
                welfare_recipient_id=recipient.id,
                office_id=office_id,
                plan_cycle_start_date=date.today(),
                next_renewal_deadline=same_renewal_deadline,
                cycle_number=1
            )
            db_session.add(cycle)
            await db_session.flush()
            cycles.append(cycle)

            # 更新期限イベントを作成
            event_ids = await calendar_service.create_renewal_deadline_events(
                db=db_session,
                office_id=office_id,
                welfare_recipient_id=recipient.id,
                cycle_id=cycle.id,
                next_renewal_deadline=same_renewal_deadline
            )
            assert event_ids is not None
            assert len(event_ids) == 1
            event_ids_list.extend(event_ids)

        # アサーション: 4つのイベントがすべて作成されている
        assert len(event_ids_list) == 4

        # 同じ日付で複数の利用者のイベントが存在することを確認
        stmt = select(CalendarEvent).where(
            CalendarEvent.event_type == CalendarEventType.renewal_deadline,
            CalendarEvent.office_id == office_id
        ).order_by(CalendarEvent.welfare_recipient_id)

        events = (await db_session.execute(stmt)).scalars().all()
        assert len(events) == 4

        # 各イベントが異なる利用者に紐づいていることを確認
        event_recipient_ids = [event.welfare_recipient_id for event in events]
        recipient_ids = [r.id for r in recipients]
        assert set(event_recipient_ids) == set(recipient_ids)

        # 各イベントが同じ期限日（150日目～180日目）を持つことを確認
        # DBから取得した値はJSTで保存されているので、JSTで比較
        from zoneinfo import ZoneInfo
        jst = ZoneInfo("Asia/Tokyo")

        expected_start_date = date.today() + timedelta(days=150)
        expected_end_date = date.today() + timedelta(days=180)

        for event in events:
            # タイムゾーンを揃えて比較（JSTとして）
            event_start_jst = event.event_start_datetime.astimezone(jst)
            event_end_jst = event.event_end_datetime.astimezone(jst)

            assert event_start_jst.date() == expected_start_date
            assert event_end_jst.date() == expected_end_date
            assert event_start_jst.time() == time(9, 0)
            assert event_end_jst.time() == time(18, 0)
            assert event.sync_status == CalendarSyncStatus.pending

        # 各利用者のイベントタイトルが正しいことを確認
        for event in events:
            # イベントに対応する利用者を検索
            recipient = next(r for r in recipients if r.id == event.welfare_recipient_id)
            expected_title = f"{recipient.last_name} {recipient.first_name} 更新期限まで残り1ヶ月"
            assert event.event_title == expected_title


class TestEventDeletion:
    """カレンダーイベント削除機能のテスト"""

    async def test_delete_renewal_event_by_cycle(
        self, db_session: AsyncSession, setup_staff_and_office
    ):
        """cycleに紐づく更新期限イベントの削除テスト"""
        from app.models.welfare_recipient import WelfareRecipient
        from app.models.support_plan_cycle import SupportPlanCycle
        from app.models.calendar_events import CalendarEvent
        from app.models.enums import GenderType, CalendarEventType
        from datetime import date, timedelta

        _, office, _, office_id = setup_staff_and_office

        # カレンダーアカウントを作成
        valid_service_account_json = json.dumps({
            "type": "service_account",
            "project_id": "test-project",
            "private_key_id": "test-key-id",
            "private_key": "-----BEGIN PRIVATE KEY-----\nMIIEvQIBADANBgkqhkiG9w0BAQEFAASCBKcwggSjAgEAAoIBAQC7VJT\n-----END PRIVATE KEY-----\n",
            "client_email": "test@test-project.iam.gserviceaccount.com",
            "client_id": "123456789",
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
        })
        unique_calendar_id = f"test-calendar-{uuid4().hex[:8]}@group.calendar.google.com"
        setup_request = CalendarSetupRequest(
            office_id=office_id,
            google_calendar_id=unique_calendar_id,
            service_account_json=valid_service_account_json,
            calendar_name="テスト事業所カレンダー"
        )
        account = await calendar_service.setup_office_calendar(db=db_session, request=setup_request)
        await calendar_service.update_connection_status(
            db=db_session,
            account_id=account.id,
            status=CalendarConnectionStatus.connected
        )

        # 利用者を作成
        recipient = WelfareRecipient(
            first_name="太郎",
            last_name="削除",
            first_name_furigana="たろう",
            last_name_furigana="さくじょ",
            birth_day=date(1990, 1, 1),
            gender=GenderType.male
        )
        db_session.add(recipient)
        await db_session.flush()

        # サイクルを作成
        cycle_start = date.today()
        cycle = SupportPlanCycle(
            welfare_recipient_id=recipient.id,
            office_id=office_id,
            plan_cycle_start_date=cycle_start,
            next_renewal_deadline=cycle_start + timedelta(days=180),
            cycle_number=1
        )
        db_session.add(cycle)
        await db_session.flush()

        # 更新期限イベントを作成
        event_ids = await calendar_service.create_renewal_deadline_events(
            db=db_session,
            office_id=office_id,
            welfare_recipient_id=recipient.id,
            cycle_id=cycle.id,
            next_renewal_deadline=cycle.next_renewal_deadline
        )
        assert len(event_ids) == 1

        # イベントが作成されたことを確認
        result = await db_session.execute(
            select(CalendarEvent).where(
                CalendarEvent.support_plan_cycle_id == cycle.id,
                CalendarEvent.event_type == CalendarEventType.renewal_deadline
            )
        )
        event = result.scalar_one_or_none()
        assert event is not None
        assert event.event_title == f"{recipient.last_name} {recipient.first_name} 更新期限まで残り1ヶ月"

        # イベントを削除
        deleted = await calendar_service.delete_event_by_cycle(
            db=db_session,
            cycle_id=cycle.id,
            event_type=CalendarEventType.renewal_deadline
        )
        assert deleted is True

        # イベントが削除されたことを確認
        result = await db_session.execute(
            select(CalendarEvent).where(
                CalendarEvent.support_plan_cycle_id == cycle.id,
                CalendarEvent.event_type == CalendarEventType.renewal_deadline
            )
        )
        event_after_delete = result.scalar_one_or_none()
        assert event_after_delete is None

    async def test_delete_monitoring_event_by_status(
        self, db_session: AsyncSession, setup_staff_and_office
    ):
        """statusに紐づくモニタリング期限イベントの削除テスト"""
        from app.models.welfare_recipient import WelfareRecipient
        from app.models.support_plan_cycle import SupportPlanCycle
        from app.models.calendar_events import CalendarEvent
        from app.models.enums import GenderType, CalendarEventType
        from datetime import date, timedelta

        _, office, _, office_id = setup_staff_and_office

        # カレンダーアカウントを作成
        valid_service_account_json = json.dumps({
            "type": "service_account",
            "project_id": "test-project",
            "private_key_id": "test-key-id",
            "private_key": "-----BEGIN PRIVATE KEY-----\nMIIEvQIBADANBgkqhkiG9w0BAQEFAASCBKcwggSjAgEAAoIBAQC7VJT\n-----END PRIVATE KEY-----\n",
            "client_email": "test@test-project.iam.gserviceaccount.com",
            "client_id": "123456789",
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
        })
        unique_calendar_id = f"test-calendar-{uuid4().hex[:8]}@group.calendar.google.com"
        setup_request = CalendarSetupRequest(
            office_id=office_id,
            google_calendar_id=unique_calendar_id,
            service_account_json=valid_service_account_json,
            calendar_name="テスト事業所カレンダー"
        )
        account = await calendar_service.setup_office_calendar(db=db_session, request=setup_request)
        await calendar_service.update_connection_status(
            db=db_session,
            account_id=account.id,
            status=CalendarConnectionStatus.connected
        )

        # 利用者を作成
        recipient = WelfareRecipient(
            first_name="次郎",
            last_name="削除",
            first_name_furigana="じろう",
            last_name_furigana="さくじょ",
            birth_day=date(1992, 2, 2),
            gender=GenderType.male
        )
        db_session.add(recipient)
        await db_session.flush()

        # サイクルを作成（cycle_number=2でモニタリングイベント作成）
        cycle_start = date.today()
        cycle = SupportPlanCycle(
            welfare_recipient_id=recipient.id,
            office_id=office_id,
            plan_cycle_start_date=cycle_start,
            next_renewal_deadline=cycle_start + timedelta(days=180),
            cycle_number=2
        )
        db_session.add(cycle)
        await db_session.flush()

        # monitoringステータスを作成
        from app.models.support_plan_cycle import SupportPlanStatus
        from app.models.enums import SupportPlanStep
        status = SupportPlanStatus(
            welfare_recipient_id=recipient.id,
            plan_cycle_id=cycle.id,
            office_id=office_id,
            step_type=SupportPlanStep.monitoring,
            completed=False
        )
        db_session.add(status)
        await db_session.flush()

        # モニタリング期限イベントを作成
        event_ids = await calendar_service.create_next_plan_start_date_events(
            db=db_session,
            office_id=office_id,
            welfare_recipient_id=recipient.id,
            cycle_id=cycle.id,
            cycle_start_date=cycle_start,
            cycle_number=cycle.cycle_number,
            status_id=status.id
        )
        assert len(event_ids) == 1

        # イベントが作成されたことを確認
        result = await db_session.execute(
            select(CalendarEvent).where(
                CalendarEvent.support_plan_status_id == status.id,
                CalendarEvent.event_type == CalendarEventType.next_plan_start_date
            )
        )
        event = result.scalar_one_or_none()
        assert event is not None

        # イベントを削除（status_idで削除）
        deleted = await calendar_service.delete_event_by_status(
            db=db_session,
            status_id=status.id,
            event_type=CalendarEventType.next_plan_start_date
        )
        assert deleted is True

        # イベントが削除されたことを確認
        result = await db_session.execute(
            select(CalendarEvent).where(
                CalendarEvent.support_plan_status_id == status.id,
                CalendarEvent.event_type == CalendarEventType.next_plan_start_date
            )
        )
        event_after_delete = result.scalar_one_or_none()
        assert event_after_delete is None
