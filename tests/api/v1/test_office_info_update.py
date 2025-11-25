"""
事務所情報変更 API のテスト
TDD方式でテストを先に作成
"""
import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import timedelta
import uuid

from app.models.staff import Staff
from app.models.enums import StaffRole
from app.core.security import create_access_token
from app import crud

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def manager_user(db_session: AsyncSession, owner_user_factory, employee_user_factory):
    """マネージャーロールのユーザーを作成するフィクスチャ"""
    owner = await owner_user_factory()
    office = owner.office_associations[0].office if owner.office_associations else None

    manager = await employee_user_factory(office=office)
    manager.role = StaffRole.manager
    await db_session.commit()
    await db_session.refresh(manager)
    return manager


class TestGetOfficeInfo:
    """
    GET /api/v1/offices/me
    事務所情報取得のテスト
    """

    async def test_get_office_info_success(
        self,
        async_client: AsyncClient,
        owner_user_factory
    ):
        """正常系: 事務所情報を取得できる"""
        owner = await owner_user_factory()
        office = owner.office_associations[0].office if owner.office_associations else None

        access_token = create_access_token(str(owner.id), timedelta(minutes=30))
        headers = {"Authorization": f"Bearer {access_token}"}

        response = await async_client.get("/api/v1/offices/me", headers=headers)

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == str(office.id)
        assert "name" in data
        assert "address" in data
        assert "phone_number" in data
        assert "email" in data

    async def test_get_office_info_unauthorized(
        self,
        async_client: AsyncClient
    ):
        """異常系: 未認証ユーザーはアクセス不可"""
        response = await async_client.get("/api/v1/offices/me")
        assert response.status_code == 401


class TestUpdateOfficeInfo:
    """
    PUT /api/v1/offices/me
    事務所情報更新のテスト
    """

    async def test_update_office_info_success_owner(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        owner_user_factory
    ):
        """正常系: オーナーは事務所情報を更新できる"""
        owner = await owner_user_factory()
        office = owner.office_associations[0].office if owner.office_associations else None

        access_token = create_access_token(str(owner.id), timedelta(minutes=30))
        headers = {"Authorization": f"Bearer {access_token}"}

        # 更新データ
        payload = {
            "name": "更新後の事務所名",
            "address": "東京都渋谷区1-2-3",
            "phone_number": "03-1234-5678",
            "email": "updated@example.com"
        }

        response = await async_client.put(
            "/api/v1/offices/me",
            json=payload,
            headers=headers
        )

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "更新後の事務所名"
        assert data["address"] == "東京都渋谷区1-2-3"
        assert data["phone_number"] == "03-1234-5678"
        assert data["email"] == "updated@example.com"

        # DBで確認
        await db_session.refresh(office)
        assert office.name == "更新後の事務所名"
        assert office.address == "東京都渋谷区1-2-3"

    async def test_update_office_info_partial(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        owner_user_factory
    ):
        """正常系: 一部のフィールドのみ更新"""
        owner = await owner_user_factory()
        office = owner.office_associations[0].office if owner.office_associations else None
        original_name = office.name

        access_token = create_access_token(str(owner.id), timedelta(minutes=30))
        headers = {"Authorization": f"Bearer {access_token}"}

        # 住所のみ更新
        payload = {
            "address": "大阪府大阪市北区4-5-6"
        }

        response = await async_client.put(
            "/api/v1/offices/me",
            json=payload,
            headers=headers
        )

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == original_name  # 名前は変更されていない
        assert data["address"] == "大阪府大阪市北区4-5-6"

    async def test_update_office_info_forbidden_manager(
        self,
        async_client: AsyncClient,
        manager_user
    ):
        """異常系: マネージャーは更新不可（403）"""
        access_token = create_access_token(str(manager_user.id), timedelta(minutes=30))
        headers = {"Authorization": f"Bearer {access_token}"}

        payload = {"name": "マネージャーによる更新"}

        response = await async_client.put(
            "/api/v1/offices/me",
            json=payload,
            headers=headers
        )

        assert response.status_code == 403
        # 日本語エラーメッセージを確認
        assert "事業所管理者の権限が必要です" in response.json()["detail"]

    async def test_update_office_info_forbidden_employee(
        self,
        async_client: AsyncClient,
        employee_user_factory
    ):
        """異常系: 一般スタッフは更新不可（403）"""
        employee = await employee_user_factory()
        access_token = create_access_token(str(employee.id), timedelta(minutes=30))
        headers = {"Authorization": f"Bearer {access_token}"}

        payload = {"name": "一般スタッフによる更新"}

        response = await async_client.put(
            "/api/v1/offices/me",
            json=payload,
            headers=headers
        )

        assert response.status_code == 403
        # 日本語エラーメッセージを確認
        assert "事業所管理者の権限が必要です" in response.json()["detail"]

    async def test_update_office_info_unauthorized(
        self,
        async_client: AsyncClient
    ):
        """異常系: 未認証ユーザーは更新不可（401）"""
        payload = {"name": "未認証による更新"}

        response = await async_client.put("/api/v1/offices/me", json=payload)

        assert response.status_code == 401

    async def test_update_office_info_invalid_email(
        self,
        async_client: AsyncClient,
        owner_user_factory
    ):
        """異常系: 無効なメールアドレス形式"""
        owner = await owner_user_factory()
        access_token = create_access_token(str(owner.id), timedelta(minutes=30))
        headers = {"Authorization": f"Bearer {access_token}"}

        payload = {"email": "invalid-email"}

        response = await async_client.put(
            "/api/v1/offices/me",
            json=payload,
            headers=headers
        )

        assert response.status_code == 422  # バリデーションエラー

    async def test_update_office_info_invalid_phone(
        self,
        async_client: AsyncClient,
        owner_user_factory
    ):
        """異常系: 無効な電話番号形式"""
        owner = await owner_user_factory()
        access_token = create_access_token(str(owner.id), timedelta(minutes=30))
        headers = {"Authorization": f"Bearer {access_token}"}

        payload = {"phone_number": "12345"}  # 不正な形式

        response = await async_client.put(
            "/api/v1/offices/me",
            json=payload,
            headers=headers
        )

        assert response.status_code == 422  # バリデーションエラー

    async def test_update_office_info_creates_audit_log(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        owner_user_factory
    ):
        """正常系: 更新時に監査ログが作成される"""
        owner = await owner_user_factory()
        office = owner.office_associations[0].office if owner.office_associations else None

        access_token = create_access_token(str(owner.id), timedelta(minutes=30))
        headers = {"Authorization": f"Bearer {access_token}"}

        # 更新前のログ件数を確認
        logs_before = await crud.office_audit_log.get_by_office_id(
            db=db_session,
            office_id=office.id,
            skip=0,
            limit=100
        )
        count_before = len(logs_before)

        # 更新実行
        payload = {"name": "監査ログテスト用事務所"}

        response = await async_client.put(
            "/api/v1/offices/me",
            json=payload,
            headers=headers
        )

        assert response.status_code == 200

        # 更新後のログ件数を確認
        logs_after = await crud.office_audit_log.get_by_office_id(
            db=db_session,
            office_id=office.id,
            skip=0,
            limit=100
        )
        count_after = len(logs_after)

        assert count_after == count_before + 1

        # 最新のログを確認
        latest_log = logs_after[0]
        assert latest_log.office_id == office.id
        assert latest_log.staff_id == owner.id
        assert latest_log.action_type == "office_info_updated"

    async def test_update_office_info_sends_notification(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        owner_user_factory,
        employee_user_factory
    ):
        """正常系: 更新時にシステム通知が送信される"""
        # オーナーと所属事務所を取得
        owner = await owner_user_factory()
        office = owner.office_associations[0].office if owner.office_associations else None

        # 同じ事務所に他のスタッフを追加
        employee1 = await employee_user_factory(office=office)
        employee2 = await employee_user_factory(office=office)

        access_token = create_access_token(str(owner.id), timedelta(minutes=30))
        headers = {"Authorization": f"Bearer {access_token}"}

        # 更新前のメッセージ件数を確認
        from app.models.message import Message
        from app.models.enums import MessageType
        from sqlalchemy import select, func

        stmt = select(func.count()).select_from(Message).where(
            Message.office_id == office.id,
            Message.message_type == MessageType.announcement,
            Message.sender_staff_id == None  # システム通知
        )
        result = await db_session.execute(stmt)
        count_before = result.scalar()

        # 事務所情報を更新
        payload = {
            "name": "通知テスト事務所",
            "address": "東京都新宿区1-1-1"
        }

        response = await async_client.put(
            "/api/v1/offices/me",
            json=payload,
            headers=headers
        )

        assert response.status_code == 200

        # 更新後のメッセージ件数を確認
        result = await db_session.execute(stmt)
        count_after = result.scalar()

        # システム通知が1件作成されているはず
        assert count_after == count_before + 1

        # 最新のシステム通知を取得
        stmt = select(Message).where(
            Message.office_id == office.id,
            Message.message_type == MessageType.announcement,
            Message.sender_staff_id == None
        ).order_by(Message.created_at.desc())
        result = await db_session.execute(stmt)
        notification = result.scalars().first()

        # 通知の内容を検証
        assert notification is not None
        assert notification.office_id == office.id
        assert notification.sender_staff_id is None  # システム通知
        assert notification.message_type == MessageType.announcement
        assert "事務所情報が更新されました" in notification.title
        assert "name" in notification.content  # 変更されたフィールド名が含まれる
        assert "address" in notification.content  # 変更されたフィールド名が含まれる

        # 全スタッフが受信者に含まれているか確認
        from app.models.message import MessageRecipient
        stmt = select(MessageRecipient).where(
            MessageRecipient.message_id == notification.id
        )
        result = await db_session.execute(stmt)
        recipients = result.scalars().all()

        # オーナー + employee1 + employee2 = 3人
        assert len(recipients) == 3
        recipient_ids = {r.recipient_staff_id for r in recipients}
        assert owner.id in recipient_ids
        assert employee1.id in recipient_ids
        assert employee2.id in recipient_ids


class TestGetOfficeAuditLogs:
    """
    GET /api/v1/offices/me/audit-logs
    監査ログ取得のテスト
    """

    async def test_get_audit_logs_success_owner(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        owner_user_factory
    ):
        """正常系: オーナーは監査ログを取得できる"""
        owner = await owner_user_factory()
        office = owner.office_associations[0].office if owner.office_associations else None

        # テスト用の監査ログを作成
        for i in range(3):
            await crud.office_audit_log.create_office_update_log(
                db=db_session,
                office_id=office.id,
                staff_id=owner.id,
                action_type="office_info_updated",
                old_values={"name": f"旧名称{i}"},
                new_values={"name": f"新名称{i}"}
            )
        await db_session.commit()

        access_token = create_access_token(str(owner.id), timedelta(minutes=30))
        headers = {"Authorization": f"Bearer {access_token}"}

        response = await async_client.get(
            "/api/v1/offices/me/audit-logs",
            headers=headers
        )

        assert response.status_code == 200
        data = response.json()
        assert "logs" in data
        assert len(data["logs"]) >= 3

    async def test_get_audit_logs_forbidden_non_owner(
        self,
        async_client: AsyncClient,
        manager_user
    ):
        """異常系: オーナー以外は監査ログを取得不可"""
        access_token = create_access_token(str(manager_user.id), timedelta(minutes=30))
        headers = {"Authorization": f"Bearer {access_token}"}

        response = await async_client.get(
            "/api/v1/offices/me/audit-logs",
            headers=headers
        )

        assert response.status_code == 403
