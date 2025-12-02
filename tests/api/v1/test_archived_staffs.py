"""
app_admin用アーカイブスタッフAPIのテスト

テスト対象:
- GET /api/v1/admin/archived-staffs
  - 正常系: アーカイブリスト取得
  - 正常系: office_idによるフィルタリング
  - 正常系: archive_reasonによるフィルタリング
  - 正常系: ページネーション
  - 異常系: app_admin以外のアクセス（403）
- GET /api/v1/admin/archived-staffs/{id}
  - 正常系: 特定アーカイブの詳細取得
  - 異常系: 存在しないID（404）
  - 異常系: app_admin以外のアクセス（403）
"""
import uuid
import pytest
from datetime import datetime, timezone, timedelta
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.archived_staff import ArchivedStaff
from app.models.enums import StaffRole

pytestmark = pytest.mark.asyncio


async def test_list_archived_staffs_success(
    async_client: AsyncClient,
    db_session: AsyncSession,
    app_admin_user_factory,
    office_factory
):
    """正常系: app_adminがアーカイブリストを取得できる"""
    # Arrange
    app_admin = await app_admin_user_factory()
    passphrase = "secret123!"
    from app.core.security import get_password_hash
    app_admin.hashed_passphrase = get_password_hash(passphrase)

    office = await office_factory(name="Test Office")
    await db_session.commit()

    # サンプルアーカイブを作成
    now = datetime.now(timezone.utc)
    archives = [
        ArchivedStaff(
            original_staff_id=uuid.uuid4(),
            anonymized_full_name="スタッフ-ABC123",
            anonymized_email="archived-ABC123@deleted.local",
            role=StaffRole.employee.value,
            office_id=office.id,
            office_name=office.name,
            hired_at=now - timedelta(days=365),
            terminated_at=now - timedelta(days=30),
            archive_reason="staff_deletion",
            legal_retention_until=now + timedelta(days=365*5),
            metadata_={"deleted_by_staff_id": str(app_admin.id)},
            is_test_data=False
        ),
        ArchivedStaff(
            original_staff_id=uuid.uuid4(),
            anonymized_full_name="スタッフ-DEF456",
            anonymized_email="archived-DEF456@deleted.local",
            role=StaffRole.manager.value,
            office_id=office.id,
            office_name=office.name,
            hired_at=now - timedelta(days=730),
            terminated_at=now - timedelta(days=60),
            archive_reason="staff_withdrawal",
            legal_retention_until=now + timedelta(days=365*5),
            archive_metadata={"deleted_by_staff_id": str(uuid.uuid4())},
            is_test_data=False
        ),
    ]

    for archive in archives:
        db_session.add(archive)
    await db_session.commit()

    # Act: ログイン
    login_response = await async_client.post(
        "/api/v1/auth/token",
        data={
            "username": app_admin.email,
            "password": "a-very-secure-password",
            "passphrase": passphrase
        }
    )
    assert login_response.status_code == 200, f"Login failed: {login_response.json()}"
    response_data = login_response.json()
    token = response_data.get("access_token") or response_data.get("token")

    # Act: アーカイブリスト取得
    response = await async_client.get(
        "/api/v1/admin/archived-staffs",
        headers={"Authorization": f"Bearer {token}"}
    )

    # Assert
    assert response.status_code == 200
    data = response.json()
    assert "items" in data
    assert "total" in data
    assert data["total"] >= 2
    assert len(data["items"]) >= 2

    # アーカイブデータの確認
    archive_emails = [item["anonymized_email"] for item in data["items"]]
    assert "archived-ABC123@deleted.local" in archive_emails
    assert "archived-DEF456@deleted.local" in archive_emails


async def test_list_archived_staffs_filter_by_office(
    async_client: AsyncClient,
    db_session: AsyncSession,
    app_admin_user_factory,
    office_factory
):
    """正常系: office_idでフィルタリングできる"""
    # Arrange
    app_admin = await app_admin_user_factory()
    passphrase = "secret123!"
    from app.core.security import get_password_hash
    app_admin.hashed_passphrase = get_password_hash(passphrase)

    office1 = await office_factory(name="Office 1")
    office2 = await office_factory(name="Office 2")
    await db_session.commit()

    now = datetime.now(timezone.utc)

    # office1のアーカイブ
    archive1 = ArchivedStaff(
        original_staff_id=uuid.uuid4(),
        anonymized_full_name="スタッフ-AAA111",
        anonymized_email="archived-AAA111@deleted.local",
        role=StaffRole.employee.value,
        office_id=office1.id,
        office_name=office1.name,
        hired_at=now - timedelta(days=365),
        terminated_at=now - timedelta(days=30),
        archive_reason="staff_deletion",
        legal_retention_until=now + timedelta(days=365*5),
        is_test_data=False
    )

    # office2のアーカイブ
    archive2 = ArchivedStaff(
        original_staff_id=uuid.uuid4(),
        anonymized_full_name="スタッフ-BBB222",
        anonymized_email="archived-BBB222@deleted.local",
        role=StaffRole.employee.value,
        office_id=office2.id,
        office_name=office2.name,
        hired_at=now - timedelta(days=365),
        terminated_at=now - timedelta(days=30),
        archive_reason="staff_deletion",
        legal_retention_until=now + timedelta(days=365*5),
        is_test_data=False
    )

    db_session.add(archive1)
    db_session.add(archive2)
    await db_session.commit()

    # Act: ログイン
    login_response = await async_client.post(
        "/api/v1/auth/token",
        data={
            "username": app_admin.email,
            "password": "a-very-secure-password",
            "passphrase": passphrase
        }
    )
    response_data = login_response.json()
    token = response_data.get("access_token") or response_data.get("token")

    # Act: office1でフィルタリング
    response = await async_client.get(
        f"/api/v1/admin/archived-staffs?office_id={office1.id}",
        headers={"Authorization": f"Bearer {token}"}
    )

    # Assert
    assert response.status_code == 200
    data = response.json()
    assert data["total"] >= 1

    # office1のアーカイブのみ含まれることを確認
    office_ids = [item["office_id"] for item in data["items"]]
    assert str(office1.id) in office_ids
    # office2のアーカイブは含まれないことを確認
    assert str(office2.id) not in office_ids


async def test_list_archived_staffs_filter_by_reason(
    async_client: AsyncClient,
    db_session: AsyncSession,
    app_admin_user_factory,
    office_factory
):
    """正常系: archive_reasonでフィルタリングできる"""
    # Arrange
    app_admin = await app_admin_user_factory()
    passphrase = "secret123!"
    from app.core.security import get_password_hash
    app_admin.hashed_passphrase = get_password_hash(passphrase)

    office = await office_factory(name="Test Office")
    await db_session.commit()

    now = datetime.now(timezone.utc)

    # staff_deletionのアーカイブ
    archive1 = ArchivedStaff(
        original_staff_id=uuid.uuid4(),
        anonymized_full_name="スタッフ-CCC333",
        anonymized_email="archived-CCC333@deleted.local",
        role=StaffRole.employee.value,
        office_id=office.id,
        office_name=office.name,
        hired_at=now - timedelta(days=365),
        terminated_at=now - timedelta(days=30),
        archive_reason="staff_deletion",
        legal_retention_until=now + timedelta(days=365*5),
        is_test_data=False
    )

    # staff_withdrawalのアーカイブ
    archive2 = ArchivedStaff(
        original_staff_id=uuid.uuid4(),
        anonymized_full_name="スタッフ-DDD444",
        anonymized_email="archived-DDD444@deleted.local",
        role=StaffRole.employee.value,
        office_id=office.id,
        office_name=office.name,
        hired_at=now - timedelta(days=365),
        terminated_at=now - timedelta(days=30),
        archive_reason="staff_withdrawal",
        legal_retention_until=now + timedelta(days=365*5),
        is_test_data=False
    )

    db_session.add(archive1)
    db_session.add(archive2)
    await db_session.commit()

    # Act: ログイン
    login_response = await async_client.post(
        "/api/v1/auth/token",
        data={
            "username": app_admin.email,
            "password": "a-very-secure-password",
            "passphrase": passphrase
        }
    )
    response_data = login_response.json()
    token = response_data.get("access_token") or response_data.get("token")

    # Act: staff_deletionでフィルタリング
    response = await async_client.get(
        "/api/v1/admin/archived-staffs?archive_reason=staff_deletion",
        headers={"Authorization": f"Bearer {token}"}
    )

    # Assert
    assert response.status_code == 200
    data = response.json()
    assert data["total"] >= 1

    # staff_deletionのアーカイブのみ含まれることを確認
    reasons = [item["archive_reason"] for item in data["items"]]
    assert "staff_deletion" in reasons
    # staff_withdrawalは含まれないか、含まれていても別のデータ
    for item in data["items"]:
        assert item["archive_reason"] == "staff_deletion"


async def test_list_archived_staffs_pagination(
    async_client: AsyncClient,
    db_session: AsyncSession,
    app_admin_user_factory,
    office_factory
):
    """正常系: ページネーションが機能する"""
    # Arrange
    app_admin = await app_admin_user_factory()
    passphrase = "secret123!"
    from app.core.security import get_password_hash
    app_admin.hashed_passphrase = get_password_hash(passphrase)

    office = await office_factory(name="Test Office")
    await db_session.commit()

    now = datetime.now(timezone.utc)

    # 5つのアーカイブを作成
    for i in range(5):
        archive = ArchivedStaff(
            original_staff_id=uuid.uuid4(),
            anonymized_full_name=f"スタッフ-{i:03d}",
            anonymized_email=f"archived-{i:03d}@deleted.local",
            role=StaffRole.employee.value,
            office_id=office.id,
            office_name=office.name,
            hired_at=now - timedelta(days=365),
            terminated_at=now - timedelta(days=30+i),
            archive_reason="staff_deletion",
            legal_retention_until=now + timedelta(days=365*5),
            is_test_data=False
        )
        db_session.add(archive)

    await db_session.commit()

    # Act: ログイン
    login_response = await async_client.post(
        "/api/v1/auth/token",
        data={
            "username": app_admin.email,
            "password": "a-very-secure-password",
            "passphrase": passphrase
        }
    )
    response_data = login_response.json()
    token = response_data.get("access_token") or response_data.get("token")

    # Act: limit=2で取得
    response = await async_client.get(
        "/api/v1/admin/archived-staffs?skip=0&limit=2",
        headers={"Authorization": f"Bearer {token}"}
    )

    # Assert
    assert response.status_code == 200
    data = response.json()
    assert data["total"] >= 5
    assert len(data["items"]) == 2


async def test_list_archived_staffs_forbidden_for_non_admin(
    async_client: AsyncClient,
    db_session: AsyncSession,
    owner_user_factory
):
    """異常系: app_admin以外はアクセスできない（403）"""
    # Arrange: Ownerユーザーでログイン
    owner = await owner_user_factory()
    passphrase = "secret123!"
    from app.core.security import get_password_hash
    owner.hashed_passphrase = get_password_hash(passphrase)
    await db_session.commit()

    # Act: ログイン
    login_response = await async_client.post(
        "/api/v1/auth/token",
        data={
            "username": owner.email,
            "password": "a-very-secure-password",
            "passphrase": passphrase
        }
    )
    response_data = login_response.json()
    token = response_data.get("access_token") or response_data.get("token")

    # Act: アーカイブリスト取得を試みる
    response = await async_client.get(
        "/api/v1/admin/archived-staffs",
        headers={"Authorization": f"Bearer {token}"}
    )

    # Assert: 403 Forbidden
    assert response.status_code == 403


async def test_get_archived_staff_by_id_success(
    async_client: AsyncClient,
    db_session: AsyncSession,
    app_admin_user_factory,
    office_factory
):
    """正常系: app_adminが特定のアーカイブ詳細を取得できる"""
    # Arrange
    app_admin = await app_admin_user_factory()
    passphrase = "secret123!"
    from app.core.security import get_password_hash
    app_admin.hashed_passphrase = get_password_hash(passphrase)

    office = await office_factory(name="Test Office")
    await db_session.commit()

    now = datetime.now(timezone.utc)
    archive = ArchivedStaff(
        original_staff_id=uuid.uuid4(),
        anonymized_full_name="スタッフ-XYZ789",
        anonymized_email="archived-XYZ789@deleted.local",
        role=StaffRole.owner.value,
        office_id=office.id,
        office_name=office.name,
        hired_at=now - timedelta(days=1000),
        terminated_at=now - timedelta(days=100),
        archive_reason="office_withdrawal",
        legal_retention_until=now + timedelta(days=365*5),
        metadata_={
            "deleted_by_staff_id": str(app_admin.id),
            "original_email_domain": "example.com"
        },
        is_test_data=False
    )

    db_session.add(archive)
    await db_session.commit()
    await db_session.refresh(archive)

    # Act: ログイン
    login_response = await async_client.post(
        "/api/v1/auth/token",
        data={
            "username": app_admin.email,
            "password": "a-very-secure-password",
            "passphrase": passphrase
        }
    )
    response_data = login_response.json()
    token = response_data.get("access_token") or response_data.get("token")

    # Act: アーカイブ詳細取得
    response = await async_client.get(
        f"/api/v1/admin/archived-staffs/{archive.id}",
        headers={"Authorization": f"Bearer {token}"}
    )

    # Assert
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == str(archive.id)
    assert data["anonymized_full_name"] == "スタッフ-XYZ789"
    assert data["anonymized_email"] == "archived-XYZ789@deleted.local"
    assert data["role"] == "owner"
    assert data["archive_reason"] == "office_withdrawal"
    assert "archive_metadata" in data


async def test_get_archived_staff_by_id_not_found(
    async_client: AsyncClient,
    db_session: AsyncSession,
    app_admin_user_factory
):
    """異常系: 存在しないIDで404エラー"""
    # Arrange
    app_admin = await app_admin_user_factory()
    passphrase = "secret123!"
    from app.core.security import get_password_hash
    app_admin.hashed_passphrase = get_password_hash(passphrase)
    await db_session.commit()

    # Act: ログイン
    login_response = await async_client.post(
        "/api/v1/auth/token",
        data={
            "username": app_admin.email,
            "password": "a-very-secure-password",
            "passphrase": passphrase
        }
    )
    response_data = login_response.json()
    token = response_data.get("access_token") or response_data.get("token")

    # Act: 存在しないIDでアーカイブ詳細取得
    non_existent_id = uuid.uuid4()
    response = await async_client.get(
        f"/api/v1/admin/archived-staffs/{non_existent_id}",
        headers={"Authorization": f"Bearer {token}"}
    )

    # Assert: 404 Not Found
    assert response.status_code == 404


async def test_get_archived_staff_by_id_forbidden_for_non_admin(
    async_client: AsyncClient,
    db_session: AsyncSession,
    owner_user_factory,
    office_factory
):
    """異常系: app_admin以外はアクセスできない（403）"""
    # Arrange
    owner = await owner_user_factory()
    passphrase = "secret123!"
    from app.core.security import get_password_hash
    owner.hashed_passphrase = get_password_hash(passphrase)

    office = await office_factory(name="Test Office")
    await db_session.commit()

    now = datetime.now(timezone.utc)
    archive = ArchivedStaff(
        original_staff_id=uuid.uuid4(),
        anonymized_full_name="スタッフ-TEST999",
        anonymized_email="archived-TEST999@deleted.local",
        role=StaffRole.employee.value,
        office_id=office.id,
        office_name=office.name,
        hired_at=now - timedelta(days=365),
        terminated_at=now - timedelta(days=30),
        archive_reason="staff_deletion",
        legal_retention_until=now + timedelta(days=365*5),
        is_test_data=False
    )

    db_session.add(archive)
    await db_session.commit()
    await db_session.refresh(archive)

    # Act: Ownerでログイン
    login_response = await async_client.post(
        "/api/v1/auth/token",
        data={
            "username": owner.email,
            "password": "a-very-secure-password",
            "passphrase": passphrase
        }
    )
    response_data = login_response.json()
    token = response_data.get("access_token") or response_data.get("token")

    # Act: アーカイブ詳細取得を試みる
    response = await async_client.get(
        f"/api/v1/admin/archived-staffs/{archive.id}",
        headers={"Authorization": f"Bearer {token}"}
    )

    # Assert: 403 Forbidden
    assert response.status_code == 403
