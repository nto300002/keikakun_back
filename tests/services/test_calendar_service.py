import pytest
import json
import os
from unittest.mock import patch, MagicMock
from uuid import uuid4
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

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
        name="テスト管理者",
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
        with pytest.raises(ValueError, match="already has a calendar account"):
            await calendar_service.setup_office_calendar(db=db_session, request=setup_request)

    async def test_setup_office_calendar_invalid_json(
        self,
        db_session: AsyncSession,
        setup_staff_and_office,
        invalid_service_account_json: str
    ):
        """異常系: 不正なサービスアカウントJSONの場合はバリデーションエラー"""
        _, office, _, office_id = setup_staff_and_office

        # 不完全なJSONでリクエスト作成を試みる（Pydanticバリデーションで失敗するはず）
        with pytest.raises(ValueError, match="Missing required field"):
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
        """異常系: client_emailが存在しない場合はValueError"""
        invalid_json = json.dumps({"type": "service_account", "project_id": "test"})
        with pytest.raises(ValueError, match="client_email not found"):
            calendar_service._extract_service_account_email(invalid_json)

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
