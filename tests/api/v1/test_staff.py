# tests/api/v1/test_staff.py

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

# Pytestに非同期テストであることを認識させる
pytestmark = pytest.mark.asyncio


# --- Issue #5: 保護されたルート(`/staff/me`)のテスト ---

# conftest.pyのmock_current_userフィクスチャを利用するための準備
# service_admin_user_factoryフィクスチャで作成したユーザーをテストに渡す
@pytest_asyncio.fixture
async def test_admin_user(service_admin_user_factory):
    return await service_admin_user_factory(email="me@example.com", first_name="太郎", last_name="自分")

@pytest.mark.parametrize("mock_current_user", ["test_admin_user"], indirect=True)
async def test_get_me_success(async_client: AsyncClient, mock_current_user):
    """正常系: 認証済みユーザーが自身の情報を正しく取得できることをテスト"""
    # Arrange: mock_current_userがDIを上書きし、test_admin_userを返す
    # トークン自体は検証されないので何でも良いが、形式は合わせる
    headers = {"Authorization": "Bearer fake-token"}

    # Act
    response = await async_client.get("/api/v1/staffs/me", headers=headers)

    # Assert
    assert response.status_code == 200
    data = response.json()
    assert data["email"] == mock_current_user.email
    assert data["full_name"] == mock_current_user.full_name
    assert "hashed_password" not in data

async def test_get_me_no_token(async_client: AsyncClient):
    """異常系: トークンなしで保護されたルートにアクセスできないことをテスト"""
    # Act
    response = await async_client.get("/api/v1/staffs/me")
    
    # Assert
    assert response.status_code == 401 # Unauthorized

async def test_get_me_invalid_token(async_client: AsyncClient):
    """異常系: 無効なトークンで保護されたルートにアクセスできないことをテスト"""
    # Arrange
    headers = {"Authorization": "Bearer invalid-token"}
    
    # Act
    response = await async_client.get("/api/v1/staffs/me", headers=headers)

    # Assert
    assert response.status_code == 401 # Unauthorized