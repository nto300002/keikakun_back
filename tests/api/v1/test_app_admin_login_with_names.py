"""
app_admin ログイン後の /staffs/me エンドポイントのテスト

TDD形式でapp_adminがログイン後に /staffs/me を呼び出した際、
first_name, last_name, full_name が正しく返されることをテスト
"""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import StaffRole

pytestmark = pytest.mark.asyncio


async def test_app_admin_get_me_returns_name_fields(
    async_client: AsyncClient,
    db_session: AsyncSession,
    app_admin_user_factory
):
    """正常系: app_adminがログイン後に/staffs/meを呼び出すとfirst_name/last_nameが返る"""
    # Arrange
    passphrase = "secret123!"
    app_admin = await app_admin_user_factory(
        first_name="太郎",
        last_name="山田",
        password="a-very-secure-password"
    )

    # 合言葉を設定
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

    # Assert: ログイン成功
    assert login_response.status_code == 200

    # Act: /staffs/me を呼び出し
    me_response = await async_client.get("/api/v1/staffs/me")

    # Assert: レスポンス成功
    assert me_response.status_code == 200
    data = me_response.json()

    # 名前フィールドが正しく返されることを確認
    assert data["first_name"] == "太郎"
    assert data["last_name"] == "山田"
    assert data["full_name"] == "山田 太郎"
    assert data["role"] == "app_admin"
    assert data["email"] == app_admin.email


async def test_owner_get_me_returns_name_fields(
    async_client: AsyncClient,
    db_session: AsyncSession,
    owner_user_factory
):
    """正常系: ownerがログイン後に/staffs/meを呼び出すとfirst_name/last_nameが返る"""
    # Arrange
    owner = await owner_user_factory(
        first_name="花子",
        last_name="鈴木",
        password="a-very-secure-password"
    )
    await db_session.commit()

    # Act: ログイン
    login_response = await async_client.post(
        "/api/v1/auth/token",
        data={
            "username": owner.email,
            "password": "a-very-secure-password"
        }
    )

    # Assert: ログイン成功
    assert login_response.status_code == 200

    # Act: /staffs/me を呼び出し
    me_response = await async_client.get("/api/v1/staffs/me")

    # Assert: レスポンス成功
    assert me_response.status_code == 200
    data = me_response.json()

    # 名前フィールドが正しく返されることを確認
    assert data["first_name"] == "花子"
    assert data["last_name"] == "鈴木"
    assert data["full_name"] == "鈴木 花子"
    assert data["role"] == "owner"
