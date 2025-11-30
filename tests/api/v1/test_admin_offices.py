"""
app_admin事務所管理APIのテスト

TDD形式でapp_admin用の事務所管理APIをテスト
"""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import StaffRole

pytestmark = pytest.mark.asyncio


# ========================================
# GET /api/v1/admin/offices - 事務所一覧取得
# ========================================

async def test_app_admin_get_offices_list(
    async_client: AsyncClient,
    db_session: AsyncSession,
    app_admin_user_factory,
    office_factory
):
    """正常系: app_adminが事務所一覧を取得"""
    # Arrange
    app_admin = await app_admin_user_factory()
    passphrase = "secret123!"
    from app.core.security import get_password_hash
    app_admin.hashed_passphrase = get_password_hash(passphrase)
    await db_session.commit()

    # 3つの事務所を作成
    office1 = await office_factory(name="テスト事務所A")
    office2 = await office_factory(name="テスト事務所B")
    office3 = await office_factory(name="テスト事務所C")
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
    assert login_response.status_code == 200

    # Act: 事務所一覧取得
    response = await async_client.get("/api/v1/admin/offices")

    # Assert
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) >= 3  # 少なくとも3つの事務所が返される


async def test_app_admin_get_offices_with_search(
    async_client: AsyncClient,
    db_session: AsyncSession,
    app_admin_user_factory,
    office_factory
):
    """正常系: app_adminが名前検索で事務所を取得"""
    # Arrange
    app_admin = await app_admin_user_factory()
    passphrase = "secret123!"
    from app.core.security import get_password_hash
    app_admin.hashed_passphrase = get_password_hash(passphrase)
    await db_session.commit()

    # 異なる名前の事務所を作成
    office_abc = await office_factory(name="ABC事務所")
    office_xyz = await office_factory(name="XYZ事務所")
    await db_session.commit()

    # Act: ログイン
    await async_client.post(
        "/api/v1/auth/token",
        data={
            "username": app_admin.email,
            "password": "a-very-secure-password",
            "passphrase": passphrase
        }
    )

    # Act: 名前検索
    response = await async_client.get("/api/v1/admin/offices?search=ABC")

    # Assert
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    # ABCを含む事務所のみ返される
    office_names = [office["name"] for office in data]
    assert any("ABC" in name for name in office_names)


async def test_app_admin_get_offices_pagination(
    async_client: AsyncClient,
    db_session: AsyncSession,
    app_admin_user_factory,
    office_factory
):
    """正常系: app_adminが事務所一覧をページネーション付きで取得"""
    # Arrange
    app_admin = await app_admin_user_factory()
    passphrase = "secret123!"
    from app.core.security import get_password_hash
    app_admin.hashed_passphrase = get_password_hash(passphrase)
    await db_session.commit()

    # 5つの事務所を作成
    for i in range(5):
        await office_factory(name=f"事務所{i:02d}")
    await db_session.commit()

    # Act: ログイン
    await async_client.post(
        "/api/v1/auth/token",
        data={
            "username": app_admin.email,
            "password": "a-very-secure-password",
            "passphrase": passphrase
        }
    )

    # Act: 最初の2件を取得
    response = await async_client.get("/api/v1/admin/offices?skip=0&limit=2")

    # Assert
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) <= 2  # 最大2件


async def test_owner_cannot_access_offices_list(
    async_client: AsyncClient,
    db_session: AsyncSession,
    owner_user_factory
):
    """異常系: ownerは事務所一覧を取得できない（403）"""
    # Arrange
    owner = await owner_user_factory()
    await db_session.commit()

    # Act: ログイン
    await async_client.post(
        "/api/v1/auth/token",
        data={
            "username": owner.email,
            "password": "a-very-secure-password"
        }
    )

    # Act: 事務所一覧取得を試みる
    response = await async_client.get("/api/v1/admin/offices")

    # Assert
    assert response.status_code == 403
    data = response.json()
    assert "権限" in data["detail"]


async def test_unauthenticated_cannot_access_offices_list(
    async_client: AsyncClient
):
    """異常系: 未認証ユーザーは事務所一覧を取得できない（401）"""
    # Act: 認証なしでアクセス
    response = await async_client.get("/api/v1/admin/offices")

    # Assert
    assert response.status_code == 401


# ========================================
# GET /api/v1/admin/offices/{id} - 事務所詳細取得
# ========================================

async def test_app_admin_get_office_detail(
    async_client: AsyncClient,
    db_session: AsyncSession,
    app_admin_user_factory,
    office_factory,
    owner_user_factory
):
    """正常系: app_adminが事務所詳細を取得"""
    # Arrange
    app_admin = await app_admin_user_factory()
    passphrase = "secret123!"
    from app.core.security import get_password_hash
    app_admin.hashed_passphrase = get_password_hash(passphrase)

    office = await office_factory(name="詳細テスト事務所")
    owner = await owner_user_factory(office=office)
    await db_session.commit()

    # Act: ログイン
    await async_client.post(
        "/api/v1/auth/token",
        data={
            "username": app_admin.email,
            "password": "a-very-secure-password",
            "passphrase": passphrase
        }
    )

    # Act: 事務所詳細取得
    response = await async_client.get(f"/api/v1/admin/offices/{office.id}")

    # Assert
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == str(office.id)
    assert data["name"] == "詳細テスト事務所"
    assert "staffs" in data  # スタッフ一覧が含まれる
    assert isinstance(data["staffs"], list)
    assert len(data["staffs"]) >= 1  # 少なくともownerがいる


async def test_app_admin_get_office_detail_with_multiple_staffs(
    async_client: AsyncClient,
    db_session: AsyncSession,
    app_admin_user_factory,
    office_factory,
    owner_user_factory,
    manager_user_factory,
    employee_user_factory
):
    """正常系: app_adminが複数スタッフを持つ事務所の詳細を取得"""
    # Arrange
    app_admin = await app_admin_user_factory()
    passphrase = "secret123!"
    from app.core.security import get_password_hash
    app_admin.hashed_passphrase = get_password_hash(passphrase)

    office = await office_factory(name="複数スタッフ事務所")
    owner = await owner_user_factory(office=office)
    manager = await manager_user_factory(office=office)
    employee = await employee_user_factory(office=office)
    await db_session.commit()

    # Act: ログイン
    await async_client.post(
        "/api/v1/auth/token",
        data={
            "username": app_admin.email,
            "password": "a-very-secure-password",
            "passphrase": passphrase
        }
    )

    # Act: 事務所詳細取得
    response = await async_client.get(f"/api/v1/admin/offices/{office.id}")

    # Assert
    assert response.status_code == 200
    data = response.json()
    assert len(data["staffs"]) == 3  # owner, manager, employee
    staff_roles = [staff["role"] for staff in data["staffs"]]
    assert "owner" in staff_roles
    assert "manager" in staff_roles
    assert "employee" in staff_roles


async def test_app_admin_get_nonexistent_office(
    async_client: AsyncClient,
    db_session: AsyncSession,
    app_admin_user_factory
):
    """異常系: 存在しない事務所IDで取得を試みる（404）"""
    # Arrange
    app_admin = await app_admin_user_factory()
    passphrase = "secret123!"
    from app.core.security import get_password_hash
    app_admin.hashed_passphrase = get_password_hash(passphrase)
    await db_session.commit()

    # Act: ログイン
    await async_client.post(
        "/api/v1/auth/token",
        data={
            "username": app_admin.email,
            "password": "a-very-secure-password",
            "passphrase": passphrase
        }
    )

    # Act: 存在しないUUIDで取得
    fake_uuid = "00000000-0000-0000-0000-000000000000"
    response = await async_client.get(f"/api/v1/admin/offices/{fake_uuid}")

    # Assert
    assert response.status_code == 404


async def test_owner_cannot_access_other_office_detail(
    async_client: AsyncClient,
    db_session: AsyncSession,
    owner_user_factory,
    office_factory
):
    """異常系: ownerは他の事務所の詳細を取得できない（403）"""
    # Arrange
    office1 = await office_factory(name="事務所1")
    office2 = await office_factory(name="事務所2")
    owner1 = await owner_user_factory(office=office1)
    await db_session.commit()

    # Act: ログイン
    await async_client.post(
        "/api/v1/auth/token",
        data={
            "username": owner1.email,
            "password": "a-very-secure-password"
        }
    )

    # Act: 他の事務所の詳細取得を試みる
    response = await async_client.get(f"/api/v1/admin/offices/{office2.id}")

    # Assert
    assert response.status_code == 403
