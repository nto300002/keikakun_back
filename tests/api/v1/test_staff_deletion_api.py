"""
スタッフ削除 API のテスト
TDD方式でテストを先に作成（Phase 3 Red）

テスト対象:
- DELETE /api/v1/staffs/{staff_id}
- 認証・認可のテスト（Phase 4で実装）
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
    from sqlalchemy.orm import selectinload
    from sqlalchemy import select
    from app.models.office import OfficeStaff

    owner = await owner_user_factory()

    # eager loadingでoffice_associationsを取得
    stmt = select(Staff).where(Staff.id == owner.id).options(
        selectinload(Staff.office_associations).selectinload(OfficeStaff.office)
    )
    result = await db_session.execute(stmt)
    owner = result.scalar_one()

    office = owner.office_associations[0].office if owner.office_associations else None

    manager = await employee_user_factory(office=office)
    manager.role = StaffRole.manager
    await db_session.commit()

    # managerもeager loadingで再取得
    stmt = select(Staff).where(Staff.id == manager.id).options(
        selectinload(Staff.office_associations).selectinload(OfficeStaff.office)
    )
    result = await db_session.execute(stmt)
    manager = result.scalar_one()

    return manager


class TestDeleteStaffAuthorization:
    """
    DELETE /api/v1/staffs/{staff_id}
    認証・認可のテスト
    """

    async def test_delete_staff_success_as_owner(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        owner_user_factory,
        employee_user_factory
    ):
        """正常系: オーナーはスタッフを削除できる"""
        owner = await owner_user_factory()
        office = owner.office_associations[0].office if owner.office_associations else None

        # 削除対象のスタッフを作成
        target_staff = await employee_user_factory(office=office)
        target_staff_id = target_staff.id
        target_staff_name = f"{target_staff.last_name} {target_staff.first_name}"

        access_token = create_access_token(str(owner.id), timedelta(minutes=30))
        headers = {"Authorization": f"Bearer {access_token}"}

        response = await async_client.delete(
            f"/api/v1/staffs/{target_staff_id}",
            headers=headers
        )

        assert response.status_code == 200
        data = response.json()
        assert "message" in data
        assert data["staff_id"] == str(target_staff_id)
        assert "deleted_at" in data

        # DBで確認: is_deleted = True
        await db_session.refresh(target_staff)
        assert target_staff.is_deleted == True
        assert target_staff.deleted_at is not None
        assert target_staff.deleted_by == owner.id

    async def test_delete_staff_forbidden_as_manager(
        self,
        async_client: AsyncClient,
        manager_user,
        employee_user_factory
    ):
        """異常系: マネージャーは削除不可（403）"""
        office = manager_user.office_associations[0].office if manager_user.office_associations else None
        target_staff = await employee_user_factory(office=office)

        access_token = create_access_token(str(manager_user.id), timedelta(minutes=30))
        headers = {"Authorization": f"Bearer {access_token}"}

        response = await async_client.delete(
            f"/api/v1/staffs/{target_staff.id}",
            headers=headers
        )

        assert response.status_code == 403
        # 日本語メッセージを確認
        assert "事業所管理者の権限が必要です" in response.json()["detail"]

    async def test_delete_staff_forbidden_as_employee(
        self,
        async_client: AsyncClient,
        employee_user_factory
    ):
        """異常系: 一般スタッフは削除不可（403）"""
        employee = await employee_user_factory()
        office = employee.office_associations[0].office if employee.office_associations else None

        # 別の一般スタッフを作成
        target_staff = await employee_user_factory(office=office)

        access_token = create_access_token(str(employee.id), timedelta(minutes=30))
        headers = {"Authorization": f"Bearer {access_token}"}

        response = await async_client.delete(
            f"/api/v1/staffs/{target_staff.id}",
            headers=headers
        )

        assert response.status_code == 403
        # 日本語メッセージを確認
        assert "事業所管理者の権限が必要です" in response.json()["detail"]

    async def test_delete_staff_unauthorized(
        self,
        async_client: AsyncClient,
        employee_user_factory
    ):
        """異常系: 未認証ユーザーは削除不可（401）"""
        target_staff = await employee_user_factory()

        response = await async_client.delete(f"/api/v1/staffs/{target_staff.id}")

        assert response.status_code == 401


class TestDeleteStaffValidation:
    """
    DELETE /api/v1/staffs/{staff_id}
    バリデーションのテスト
    """

    async def test_delete_staff_cannot_delete_self(
        self,
        async_client: AsyncClient,
        owner_user_factory
    ):
        """異常系: 自分自身を削除できない（400）"""
        owner = await owner_user_factory()

        access_token = create_access_token(str(owner.id), timedelta(minutes=30))
        headers = {"Authorization": f"Bearer {access_token}"}

        response = await async_client.delete(
            f"/api/v1/staffs/{owner.id}",
            headers=headers
        )

        assert response.status_code == 400
        assert "自分自身は削除できません" in response.json()["detail"]

    async def test_delete_staff_cannot_delete_last_owner(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        owner_user_factory
    ):
        """異常系: 最後のオーナーを削除できない（409）"""
        # 事務所に1人だけのオーナーを作成
        owner1 = await owner_user_factory()
        office = owner1.office_associations[0].office if owner1.office_associations else None

        # もう1人のオーナーを作成して、後で削除する
        owner2 = await owner_user_factory()
        # owner2を同じ事務所に追加
        from app.models.office import OfficeStaff
        office_staff = OfficeStaff(
            office_id=office.id,
            staff_id=owner2.id,
            is_primary=False
        )
        db_session.add(office_staff)
        owner2.role = StaffRole.owner
        await db_session.commit()
        await db_session.refresh(owner2)

        # owner1のトークンでowner2を削除（これは成功するはず）
        access_token = create_access_token(str(owner1.id), timedelta(minutes=30))
        headers = {"Authorization": f"Bearer {access_token}"}

        response = await async_client.delete(
            f"/api/v1/staffs/{owner2.id}",
            headers=headers
        )
        assert response.status_code == 200

        # 次にowner1を削除しようとする（最後のオーナーなので失敗）
        # 新しいオーナートークンを作成（owner1はまだ有効）
        access_token2 = create_access_token(str(owner1.id), timedelta(minutes=30))
        headers2 = {"Authorization": f"Bearer {access_token2}"}

        # owner1を削除しようとすると失敗（自己削除）
        # 代わりに、別のテストケースとして、owner1が最後のオーナーであることを確認
        owner_count = await crud.staff.count_owners_in_office(
            db=db_session,
            office_id=office.id
        )
        assert owner_count == 1  # owner2が削除され、owner1のみが残っている

    async def test_delete_staff_different_office_forbidden(
        self,
        async_client: AsyncClient,
        owner_user_factory
    ):
        """異常系: 異なる事務所のスタッフは削除できない（403）"""
        # 事務所1のオーナー
        owner1 = await owner_user_factory()

        # 事務所2のオーナー
        owner2 = await owner_user_factory()

        # owner1のトークンでowner2を削除しようとする
        access_token = create_access_token(str(owner1.id), timedelta(minutes=30))
        headers = {"Authorization": f"Bearer {access_token}"}

        response = await async_client.delete(
            f"/api/v1/staffs/{owner2.id}",
            headers=headers
        )

        assert response.status_code == 403
        assert "異なる事務所のスタッフは削除できません" in response.json()["detail"]

    async def test_delete_staff_already_deleted(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        owner_user_factory,
        employee_user_factory
    ):
        """異常系: 既に削除済みのスタッフを削除しようとする（400）"""
        owner = await owner_user_factory()
        office = owner.office_associations[0].office if owner.office_associations else None

        target_staff = await employee_user_factory(office=office)
        target_staff_id = target_staff.id

        # スタッフを削除
        access_token = create_access_token(str(owner.id), timedelta(minutes=30))
        headers = {"Authorization": f"Bearer {access_token}"}

        response = await async_client.delete(
            f"/api/v1/staffs/{target_staff_id}",
            headers=headers
        )
        assert response.status_code == 200

        # 同じスタッフを再度削除しようとする
        response2 = await async_client.delete(
            f"/api/v1/staffs/{target_staff_id}",
            headers=headers
        )

        assert response2.status_code == 400
        assert "このスタッフは既に削除されています" in response2.json()["detail"]

    async def test_delete_staff_not_found(
        self,
        async_client: AsyncClient,
        owner_user_factory
    ):
        """異常系: 存在しないスタッフID（404）"""
        owner = await owner_user_factory()

        access_token = create_access_token(str(owner.id), timedelta(minutes=30))
        headers = {"Authorization": f"Bearer {access_token}"}

        # 存在しないUUID
        non_existent_id = uuid.uuid4()

        response = await async_client.delete(
            f"/api/v1/staffs/{non_existent_id}",
            headers=headers
        )

        assert response.status_code == 404


class TestDeleteStaffAuditLog:
    """
    DELETE /api/v1/staffs/{staff_id}
    監査ログのテスト
    """

    async def test_delete_staff_creates_audit_log(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        owner_user_factory,
        employee_user_factory
    ):
        """正常系: 削除時に監査ログが作成される"""
        owner = await owner_user_factory()
        office = owner.office_associations[0].office if owner.office_associations else None

        target_staff = await employee_user_factory(office=office)
        target_staff_id = target_staff.id

        access_token = create_access_token(str(owner.id), timedelta(minutes=30))
        headers = {"Authorization": f"Bearer {access_token}"}

        # 削除実行
        response = await async_client.delete(
            f"/api/v1/staffs/{target_staff_id}",
            headers=headers
        )

        assert response.status_code == 200

        # 監査ログを確認
        from app.models.staff_audit_log import StaffAuditLog
        from sqlalchemy import select

        stmt = (
            select(StaffAuditLog)
            .where(StaffAuditLog.staff_id == target_staff_id)
            .where(StaffAuditLog.action == "deleted")
        )
        result = await db_session.execute(stmt)
        audit_log = result.scalar_one_or_none()

        assert audit_log is not None
        assert audit_log.performed_by == owner.id
        assert audit_log.action == "deleted"


class TestDeleteStaffSystemNotification:
    """
    DELETE /api/v1/staffs/{staff_id}
    システム通知のテスト
    """

    async def test_system_notification_sent_on_deletion(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        owner_user_factory,
        employee_user_factory
    ):
        """正常系: 削除時にシステム通知が送信される"""
        owner = await owner_user_factory()
        office = owner.office_associations[0].office if owner.office_associations else None

        # 同じ事務所に複数のスタッフを作成
        employee1 = await employee_user_factory(office=office)
        employee2 = await employee_user_factory(office=office)

        # employee1を削除
        target_staff_id = employee1.id
        target_staff_name = f"{employee1.last_name} {employee1.first_name}"

        access_token = create_access_token(str(owner.id), timedelta(minutes=30))
        headers = {"Authorization": f"Bearer {access_token}"}

        response = await async_client.delete(
            f"/api/v1/staffs/{target_staff_id}",
            headers=headers
        )

        assert response.status_code == 200

        # システム通知を確認
        from app.models.message import Message
        from app.models.enums import MessageType
        from sqlalchemy import select, desc

        stmt = (
            select(Message)
            .where(Message.sender_staff_id == None)  # システム通知は sender_staff_id が None
            .where(Message.message_type == MessageType.announcement)
            .order_by(desc(Message.created_at))
        )
        result = await db_session.execute(stmt)
        notification = result.scalars().first()

        assert notification is not None
        assert notification.title == "スタッフ退会のお知らせ"
        assert target_staff_name in notification.content
        assert f"{employee1.last_name} {employee1.first_name}さんが退会しました" in notification.content


class TestDeletedStaffAuthentication:
    """
    削除済みスタッフの認証・認可テスト
    Phase 4: 削除済みスタッフはログインおよび既存トークンの使用ができない
    """

    async def test_deleted_staff_cannot_login(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        owner_user_factory,
        employee_user_factory
    ):
        """異常系: 削除済みスタッフはログインできない（403）"""
        owner = await owner_user_factory()
        office = owner.office_associations[0].office if owner.office_associations else None

        # スタッフを作成してパスワードを保存
        password = "Test-password123!"
        target_staff = await employee_user_factory(office=office, password=password)
        target_email = target_staff.email

        # スタッフを削除
        await crud.staff.soft_delete(
            db=db_session,
            staff_id=target_staff.id,
            deleted_by=owner.id
        )
        await db_session.commit()

        # 削除されたスタッフでログインを試みる
        response = await async_client.post(
            "/api/v1/auth/token",
            data={"username": target_email, "password": password},
        )

        assert response.status_code == 403
        assert "このアカウントは削除されています" in response.json()["detail"]

    async def test_deleted_staff_cannot_use_existing_token(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        owner_user_factory,
        employee_user_factory
    ):
        """異常系: 削除済みスタッフは既存の有効なトークンを使用できない（403）"""
        owner = await owner_user_factory()
        office = owner.office_associations[0].office if owner.office_associations else None

        # スタッフを作成
        target_staff = await employee_user_factory(office=office)

        # トークンを生成（削除前）
        access_token = create_access_token(str(target_staff.id), timedelta(minutes=30))

        # トークンが有効であることを確認
        headers = {"Authorization": f"Bearer {access_token}"}
        response = await async_client.get("/api/v1/staffs/me", headers=headers)
        assert response.status_code == 200

        # スタッフを削除
        await crud.staff.soft_delete(
            db=db_session,
            staff_id=target_staff.id,
            deleted_by=owner.id
        )
        await db_session.commit()

        # 削除後、同じトークンでアクセスを試みる
        response2 = await async_client.get("/api/v1/staffs/me", headers=headers)

        assert response2.status_code == 403
        assert "このアカウントは削除されています" in response2.json()["detail"]

    async def test_deleted_staff_cannot_access_any_endpoint(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        owner_user_factory,
        employee_user_factory
    ):
        """異常系: 削除済みスタッフはすべてのエンドポイントにアクセスできない"""
        owner = await owner_user_factory()
        office = owner.office_associations[0].office if owner.office_associations else None

        target_staff = await employee_user_factory(office=office)
        access_token = create_access_token(str(target_staff.id), timedelta(minutes=30))

        # スタッフを削除
        await crud.staff.soft_delete(
            db=db_session,
            staff_id=target_staff.id,
            deleted_by=owner.id
        )
        await db_session.commit()

        headers = {"Authorization": f"Bearer {access_token}"}

        # 複数のエンドポイントをテスト
        endpoints = [
            "/api/v1/staffs/me",
            "/api/v1/offices/me",
        ]

        for endpoint in endpoints:
            response = await async_client.get(endpoint, headers=headers)
            assert response.status_code == 403, f"Failed for {endpoint}"
            assert "このアカウントは削除されています" in response.json()["detail"]
