"""カレンダー設定APIのテスト"""
import pytest
import pytest_asyncio
import json
import os
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import uuid
from datetime import timedelta
from unittest.mock import patch

from app.models.office import Office, OfficeStaff
from app.models.staff import Staff
from app.models.calendar_account import OfficeCalendarAccount
from app.models.enums import StaffRole, OfficeType, CalendarConnectionStatus
from app import crud
from app.core.security import create_access_token

# Pytestに非同期テストであることを認識させる
pytestmark = pytest.mark.asyncio


# --- フィクスチャの準備 ---

@pytest_asyncio.fixture
async def owner_user_with_office(db_session: AsyncSession, service_admin_user_factory, office_factory):
    """事業所に所属しているownerユーザーを作成するフィクスチャ"""
    user = await service_admin_user_factory(
        email=f"owner.calendar.{uuid.uuid4().hex[:6]}@example.com",
        name="Calendar Owner"
    )
    office = await office_factory(
        creator=user,
        name=f"Calendar Office {uuid.uuid4().hex[:6]}"
    )

    # ユーザーと事務所を紐付け
    association = OfficeStaff(staff_id=user.id, office_id=office.id, is_primary=True)
    db_session.add(association)
    await db_session.commit()
    await db_session.refresh(user, attribute_names=["office_associations"])
    return user, office


@pytest_asyncio.fixture
async def employee_user(service_admin_user_factory):
    """employeeロールのユーザーを作成するフィクスチャ"""
    return await service_admin_user_factory(
        email=f"employee.calendar.{uuid.uuid4().hex[:6]}@example.com",
        name="Normal Employee",
        role=StaffRole.employee
    )


@pytest_asyncio.fixture
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


# --- カレンダー設定API (/api/v1/calendar/setup) のテスト ---

class TestSetupCalendar:
    """
    POST /api/v1/calendar/setup
    """

    @pytest.mark.parametrize("mock_current_user", ["owner_user_with_office"], indirect=True)
    async def test_setup_calendar_success(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        mock_current_user: tuple[Staff, Office],
        valid_service_account_json: str
    ):
        """正常系: ownerが正常にカレンダー設定を登録できる"""
        # Arrange
        user, office = mock_current_user
        payload = {
            "office_id": str(office.id),
            "google_calendar_id": "test-calendar@group.calendar.google.com",
            "service_account_json": valid_service_account_json,
            "calendar_name": "テスト事業所カレンダー",
            "auto_invite_staff": True,
            "default_reminder_minutes": 1440
        }

        access_token = create_access_token(str(user.id), timedelta(minutes=30))
        headers = {"Authorization": f"Bearer {access_token}"}

        # モックして接続テストを成功させる
        with patch('app.services.calendar_service.GoogleCalendarClient') as mock_client_class:
            mock_client = mock_client_class.return_value
            mock_client.authenticate.return_value = None
            mock_client.create_event.return_value = "test-event-id"
            mock_client.delete_event.return_value = None

            # Act
            response = await async_client.post("/api/v1/calendar/setup", json=payload, headers=headers)

        # Assert: レスポンスの検証
        assert response.status_code == 201
        data = response.json()
        assert data["success"] is True
        assert "account" in data
        assert data["account"]["google_calendar_id"] == payload["google_calendar_id"]
        assert data["account"]["calendar_name"] == payload["calendar_name"]
        assert data["account"]["service_account_email"] == "test-account@test-project-123456.iam.gserviceaccount.com"
        # 接続テストが成功したので connected になる
        assert data["account"]["connection_status"] == CalendarConnectionStatus.connected.value

        # Assert: DBの状態の検証
        stmt = select(OfficeCalendarAccount).where(OfficeCalendarAccount.office_id == office.id)
        result = await db_session.execute(stmt)
        account_in_db = result.scalars().first()

        assert account_in_db is not None
        assert account_in_db.google_calendar_id == payload["google_calendar_id"]
        assert account_in_db.calendar_name == payload["calendar_name"]
        assert account_in_db.connection_status == CalendarConnectionStatus.connected
        assert account_in_db.service_account_key is not None  # 暗号化されている

    @pytest.mark.parametrize("mock_current_user", ["owner_user_with_office"], indirect=True)
    async def test_setup_calendar_duplicate(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        mock_current_user: tuple[Staff, Office],
        valid_service_account_json: str
    ):
        """異常系: 既にカレンダー設定が存在する事業所では登録できない"""
        # Arrange
        user, office = mock_current_user
        payload = {
            "office_id": str(office.id),
            "google_calendar_id": "test-calendar@group.calendar.google.com",
            "service_account_json": valid_service_account_json
        }

        access_token = create_access_token(str(user.id), timedelta(minutes=30))
        headers = {"Authorization": f"Bearer {access_token}"}

        # 1回目の登録（モック付き）
        with patch('app.services.calendar_service.GoogleCalendarClient') as mock_client_class:
            mock_client = mock_client_class.return_value
            mock_client.authenticate.return_value = None
            mock_client.create_event.return_value = "test-event-id"
            mock_client.delete_event.return_value = None

            await async_client.post("/api/v1/calendar/setup", json=payload, headers=headers)

        # Act: 2回目の登録（重複エラーを期待）
        response = await async_client.post("/api/v1/calendar/setup", json=payload, headers=headers)

        # Assert
        assert response.status_code == 400
        data = response.json()
        # FastAPIのHTTPExceptionは {"detail": "..."} 形式を返す
        assert "detail" in data
        assert "already has a calendar account" in data["detail"]

    @pytest.mark.parametrize("mock_current_user", ["employee_user"], indirect=True)
    async def test_setup_calendar_forbidden_for_employee(
        self,
        async_client: AsyncClient,
        mock_current_user: Staff,
        owner_user_with_office,
        valid_service_account_json: str
    ):
        """異常系: employeeロールではカレンダー設定ができない (403 Forbidden)"""
        # Arrange
        _, office = owner_user_with_office
        payload = {
            "office_id": str(office.id),
            "google_calendar_id": "test-calendar@group.calendar.google.com",
            "service_account_json": valid_service_account_json
        }

        access_token = create_access_token(str(mock_current_user.id), timedelta(minutes=30))
        headers = {"Authorization": f"Bearer {access_token}"}

        # Act
        response = await async_client.post("/api/v1/calendar/setup", json=payload, headers=headers)

        # Assert
        assert response.status_code == 403

    @pytest.mark.parametrize("mock_current_user", ["owner_user_with_office"], indirect=True)
    async def test_setup_calendar_invalid_json(
        self,
        async_client: AsyncClient,
        mock_current_user: tuple[Staff, Office]
    ):
        """異常系: 不正なサービスアカウントJSONの場合はバリデーションエラー"""
        # Arrange
        user, office = mock_current_user
        invalid_json = json.dumps({
            "type": "service_account",
            "project_id": "test-project"
            # client_emailなどが欠落
        })
        payload = {
            "office_id": str(office.id),
            "google_calendar_id": "test-calendar@group.calendar.google.com",
            "service_account_json": invalid_json
        }

        access_token = create_access_token(str(user.id), timedelta(minutes=30))
        headers = {"Authorization": f"Bearer {access_token}"}

        # Act
        response = await async_client.post("/api/v1/calendar/setup", json=payload, headers=headers)

        # Assert
        assert response.status_code == 422
        assert "Missing required field" in str(response.json())

    async def test_setup_calendar_unauthorized(
        self,
        async_client: AsyncClient,
        owner_user_with_office,
        valid_service_account_json: str
    ):
        """異常系: 認証なしでカレンダー設定ができない (401 Unauthorized)"""
        # Arrange
        _, office = owner_user_with_office
        payload = {
            "office_id": str(office.id),
            "google_calendar_id": "test-calendar@group.calendar.google.com",
            "service_account_json": valid_service_account_json
        }

        # Act
        response = await async_client.post("/api/v1/calendar/setup", json=payload)

        # Assert
        assert response.status_code == 401


# --- カレンダー設定取得API (/api/v1/calendar/office/{office_id}) のテスト ---

class TestGetCalendarByOffice:
    """
    GET /api/v1/calendar/office/{office_id}
    """

    @pytest.mark.parametrize("mock_current_user", ["owner_user_with_office"], indirect=True)
    async def test_get_calendar_success(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        mock_current_user: tuple[Staff, Office],
        valid_service_account_json: str
    ):
        """正常系: カレンダー設定を取得できる"""
        # Arrange
        user, office = mock_current_user

        # カレンダー設定を事前に作成
        setup_payload = {
            "office_id": str(office.id),
            "google_calendar_id": "test-calendar@group.calendar.google.com",
            "service_account_json": valid_service_account_json,
            "calendar_name": "取得テスト用カレンダー"
        }
        access_token = create_access_token(str(user.id), timedelta(minutes=30))
        headers = {"Authorization": f"Bearer {access_token}"}
        await async_client.post("/api/v1/calendar/setup", json=setup_payload, headers=headers)

        # Act: 取得
        response = await async_client.get(f"/api/v1/calendar/office/{office.id}", headers=headers)

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["google_calendar_id"] == "test-calendar@group.calendar.google.com"
        assert data["calendar_name"] == "取得テスト用カレンダー"
        assert "service_account_key" not in data  # 暗号化キーは返さない

    @pytest.mark.parametrize("mock_current_user", ["owner_user_with_office"], indirect=True)
    async def test_get_calendar_not_found(
        self,
        async_client: AsyncClient,
        mock_current_user: tuple[Staff, Office]
    ):
        """正常系: カレンダー設定が存在しない場合は404"""
        # Arrange
        user, office = mock_current_user
        access_token = create_access_token(str(user.id), timedelta(minutes=30))
        headers = {"Authorization": f"Bearer {access_token}"}

        # Act
        response = await async_client.get(f"/api/v1/calendar/office/{office.id}", headers=headers)

        # Assert
        assert response.status_code == 404

    async def test_get_calendar_unauthorized(
        self,
        async_client: AsyncClient,
        owner_user_with_office
    ):
        """異常系: 認証なしでカレンダー設定を取得できない (401 Unauthorized)"""
        # Arrange
        _, office = owner_user_with_office

        # Act
        response = await async_client.get(f"/api/v1/calendar/office/{office.id}")

        # Assert
        assert response.status_code == 401


# --- カレンダー設定更新API (PUT /api/v1/calendar/{account_id}) のテスト ---

class TestUpdateCalendar:
    """
    PUT /api/v1/calendar/{account_id}
    """

    @pytest.mark.parametrize("mock_current_user", ["owner_user_with_office"], indirect=True)
    async def test_update_calendar_success(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        mock_current_user: tuple[Staff, Office],
        valid_service_account_json: str
    ):
        """正常系: カレンダー設定を更新できる（JSONファイル再アップロード）"""
        # Arrange
        user, office = mock_current_user

        # 初期設定を作成
        setup_payload = {
            "office_id": str(office.id),
            "google_calendar_id": "old-calendar@group.calendar.google.com",
            "service_account_json": valid_service_account_json,
            "calendar_name": "旧カレンダー名"
        }
        access_token = create_access_token(str(user.id), timedelta(minutes=30))
        headers = {"Authorization": f"Bearer {access_token}"}

        with patch('app.services.calendar_service.GoogleCalendarClient') as mock_client_class:
            mock_client = mock_client_class.return_value
            mock_client.authenticate.return_value = None
            mock_client.create_event.return_value = "test-event-id"
            mock_client.delete_event.return_value = None

            setup_response = await async_client.post("/api/v1/calendar/setup", json=setup_payload, headers=headers)
            account_id = setup_response.json()["account"]["id"]

        # 新しいサービスアカウントJSON
        new_service_account_json = json.dumps({
            "type": "service_account",
            "project_id": "new-project-123456",
            "private_key_id": "new-key-id-123456",
            "private_key": "-----BEGIN PRIVATE KEY-----\nNEWKEY...\n-----END PRIVATE KEY-----\n",
            "client_email": "new-account@new-project-123456.iam.gserviceaccount.com",
            "client_id": "999999999999999999999",
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
            "client_x509_cert_url": "https://www.googleapis.com/robot/v1/metadata/x509/new-account%40new-project-123456.iam.gserviceaccount.com"
        })

        # 更新ペイロード
        update_payload = {
            "office_id": str(office.id),
            "google_calendar_id": "new-calendar@group.calendar.google.com",
            "service_account_json": new_service_account_json,
            "calendar_name": "新カレンダー名"
        }

        with patch('app.services.calendar_service.GoogleCalendarClient') as mock_client_class:
            mock_client = mock_client_class.return_value
            mock_client.authenticate.return_value = None
            mock_client.create_event.return_value = "test-event-id-2"
            mock_client.delete_event.return_value = None

            # Act
            response = await async_client.put(f"/api/v1/calendar/{account_id}", json=update_payload, headers=headers)

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["account"]["google_calendar_id"] == "new-calendar@group.calendar.google.com"
        assert data["account"]["calendar_name"] == "新カレンダー名"
        assert data["account"]["service_account_email"] == "new-account@new-project-123456.iam.gserviceaccount.com"

        # DBの確認
        stmt = select(OfficeCalendarAccount).where(OfficeCalendarAccount.id == account_id)
        result = await db_session.execute(stmt)
        updated_account = result.scalars().first()
        assert updated_account.calendar_name == "新カレンダー名"
        assert updated_account.google_calendar_id == "new-calendar@group.calendar.google.com"

    @pytest.mark.parametrize("mock_current_user", ["owner_user_with_office"], indirect=True)
    async def test_update_calendar_not_found(
        self,
        async_client: AsyncClient,
        mock_current_user: tuple[Staff, Office],
        valid_service_account_json: str
    ):
        """異常系: 存在しないカレンダーアカウントIDでは更新できない"""
        # Arrange
        user, office = mock_current_user
        non_existent_id = str(uuid.uuid4())

        update_payload = {
            "office_id": str(office.id),
            "google_calendar_id": "new-calendar@group.calendar.google.com",
            "service_account_json": valid_service_account_json,
            "calendar_name": "新カレンダー名"
        }

        access_token = create_access_token(str(user.id), timedelta(minutes=30))
        headers = {"Authorization": f"Bearer {access_token}"}

        # Act
        response = await async_client.put(f"/api/v1/calendar/{non_existent_id}", json=update_payload, headers=headers)

        # Assert
        assert response.status_code == 404

    @pytest.mark.parametrize("mock_current_user", ["employee_user"], indirect=True)
    async def test_update_calendar_forbidden_for_employee(
        self,
        async_client: AsyncClient,
        mock_current_user: Staff,
        owner_user_with_office,
        valid_service_account_json: str
    ):
        """異常系: employeeロールではカレンダー設定を更新できない"""
        # Arrange
        owner, office = owner_user_with_office

        # owner でカレンダー設定を作成
        setup_payload = {
            "office_id": str(office.id),
            "google_calendar_id": "test-calendar@group.calendar.google.com",
            "service_account_json": valid_service_account_json
        }
        owner_token = create_access_token(str(owner.id), timedelta(minutes=30))
        owner_headers = {"Authorization": f"Bearer {owner_token}"}

        # owner_user_with_officeで作成したownerを使うため、一時的に依存関係をオーバーライド
        from app.main import app
        from app.api.deps import get_current_user

        async def override_owner_user():
            return owner

        # 現在のオーバーライドを一時的に保存
        previous_override = app.dependency_overrides.get(get_current_user)

        with patch('app.services.calendar_service.GoogleCalendarClient') as mock_client_class:
            mock_client = mock_client_class.return_value
            mock_client.authenticate.return_value = None
            mock_client.create_event.return_value = "test-event-id"
            mock_client.delete_event.return_value = None

            # ownerの依存関係をオーバーライド
            app.dependency_overrides[get_current_user] = override_owner_user

            setup_response = await async_client.post("/api/v1/calendar/setup", json=setup_payload, headers=owner_headers)

            # 元のオーバーライドを復元
            if previous_override:
                app.dependency_overrides[get_current_user] = previous_override

            assert setup_response.status_code == 201, f"Setup failed: {setup_response.json()}"
            account_id = setup_response.json()["account"]["id"]

        # employee で更新を試みる
        update_payload = {
            "office_id": str(office.id),
            "google_calendar_id": "new-calendar@group.calendar.google.com",
            "service_account_json": valid_service_account_json
        }
        employee_token = create_access_token(str(mock_current_user.id), timedelta(minutes=30))
        employee_headers = {"Authorization": f"Bearer {employee_token}"}

        # Act
        response = await async_client.put(f"/api/v1/calendar/{account_id}", json=update_payload, headers=employee_headers)

        # Assert
        assert response.status_code == 403


# --- カレンダー連携解除API (DELETE /api/v1/calendar/{account_id}) のテスト ---

class TestDeleteCalendar:
    """
    DELETE /api/v1/calendar/{account_id}
    """

    @pytest.mark.parametrize("mock_current_user", ["owner_user_with_office"], indirect=True)
    async def test_delete_calendar_success(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        mock_current_user: tuple[Staff, Office],
        valid_service_account_json: str
    ):
        """正常系: カレンダー連携を解除できる"""
        # Arrange
        user, office = mock_current_user

        # カレンダー設定を作成
        setup_payload = {
            "office_id": str(office.id),
            "google_calendar_id": "test-calendar@group.calendar.google.com",
            "service_account_json": valid_service_account_json
        }
        access_token = create_access_token(str(user.id), timedelta(minutes=30))
        headers = {"Authorization": f"Bearer {access_token}"}

        with patch('app.services.calendar_service.GoogleCalendarClient') as mock_client_class:
            mock_client = mock_client_class.return_value
            mock_client.authenticate.return_value = None
            mock_client.create_event.return_value = "test-event-id"
            mock_client.delete_event.return_value = None

            setup_response = await async_client.post("/api/v1/calendar/setup", json=setup_payload, headers=headers)
            account_id = setup_response.json()["account"]["id"]

        # Act
        response = await async_client.delete(f"/api/v1/calendar/{account_id}", headers=headers)

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "削除しました" in data["message"] or "解除しました" in data["message"]

        # DBから削除されたことを確認
        stmt = select(OfficeCalendarAccount).where(OfficeCalendarAccount.id == account_id)
        result = await db_session.execute(stmt)
        deleted_account = result.scalars().first()
        assert deleted_account is None

    @pytest.mark.parametrize("mock_current_user", ["owner_user_with_office"], indirect=True)
    async def test_delete_calendar_not_found(
        self,
        async_client: AsyncClient,
        mock_current_user: tuple[Staff, Office]
    ):
        """異常系: 存在しないカレンダーアカウントIDでは削除できない"""
        # Arrange
        user, office = mock_current_user
        non_existent_id = str(uuid.uuid4())

        access_token = create_access_token(str(user.id), timedelta(minutes=30))
        headers = {"Authorization": f"Bearer {access_token}"}

        # Act
        response = await async_client.delete(f"/api/v1/calendar/{non_existent_id}", headers=headers)

        # Assert
        assert response.status_code == 404

    @pytest.mark.parametrize("mock_current_user", ["employee_user"], indirect=True)
    async def test_delete_calendar_forbidden_for_employee(
        self,
        async_client: AsyncClient,
        mock_current_user: Staff,
        owner_user_with_office,
        valid_service_account_json: str
    ):
        """異常系: employeeロールではカレンダー連携を解除できない"""
        # Arrange
        owner, office = owner_user_with_office

        # owner でカレンダー設定を作成
        setup_payload = {
            "office_id": str(office.id),
            "google_calendar_id": "test-calendar@group.calendar.google.com",
            "service_account_json": valid_service_account_json
        }
        owner_token = create_access_token(str(owner.id), timedelta(minutes=30))
        owner_headers = {"Authorization": f"Bearer {owner_token}"}

        # owner_user_with_officeで作成したownerを使うため、一時的に依存関係をオーバーライド
        from app.main import app
        from app.api.deps import get_current_user

        async def override_owner_user():
            return owner

        # 現在のオーバーライドを一時的に保存
        previous_override = app.dependency_overrides.get(get_current_user)

        with patch('app.services.calendar_service.GoogleCalendarClient') as mock_client_class:
            mock_client = mock_client_class.return_value
            mock_client.authenticate.return_value = None
            mock_client.create_event.return_value = "test-event-id"
            mock_client.delete_event.return_value = None

            # ownerの依存関係をオーバーライド
            app.dependency_overrides[get_current_user] = override_owner_user

            setup_response = await async_client.post("/api/v1/calendar/setup", json=setup_payload, headers=owner_headers)

            # 元のオーバーライドを復元
            if previous_override:
                app.dependency_overrides[get_current_user] = previous_override

            assert setup_response.status_code == 201, f"Setup failed: {setup_response.json()}"
            account_id = setup_response.json()["account"]["id"]

        # employee で削除を試みる
        employee_token = create_access_token(str(mock_current_user.id), timedelta(minutes=30))
        employee_headers = {"Authorization": f"Bearer {employee_token}"}

        # Act
        response = await async_client.delete(f"/api/v1/calendar/{account_id}", headers=employee_headers)

        # Assert
        assert response.status_code == 403
