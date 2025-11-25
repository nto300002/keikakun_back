"""
CSRF保護のテスト

Cookie認証を使用する状態変更エンドポイント(POST/PUT/DELETE)に対して、
CSRFトークンの検証が正しく機能することを確認する。
"""
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import timedelta

from app.core.security import create_access_token


class TestCSRFProtection:
    """CSRF保護のテストクラス"""

    @pytest.mark.asyncio
    async def test_get_csrf_token_endpoint(
        self,
        async_client: AsyncClient,
    ):
        """CSRFトークン取得エンドポイントのテスト"""
        response = await async_client.get("/api/v1/csrf-token")

        assert response.status_code == 200
        data = response.json()
        assert "csrf_token" in data
        assert isinstance(data["csrf_token"], str)
        assert len(data["csrf_token"]) > 0

    @pytest.mark.asyncio
    async def test_csrf_token_in_cookie(
        self,
        async_client: AsyncClient,
    ):
        """CSRFトークンがCookieに設定されることを確認"""
        response = await async_client.get("/api/v1/csrf-token")

        assert response.status_code == 200
        assert "fastapi-csrf-token" in response.cookies

    @pytest.mark.asyncio
    async def test_protected_endpoint_requires_csrf_token(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        owner_user_factory,
    ):
        """
        保護されたエンドポイントはCSRFトークンを要求する

        事務所情報更新エンドポイントでテスト
        """
        # ユーザーを作成
        owner = await owner_user_factory()
        access_token = create_access_token(str(owner.id), timedelta(minutes=30))

        # CSRFトークンなしでリクエスト（Cookie認証使用）
        cookies = {"access_token": access_token}
        payload = {"name": "Updated Office Name"}

        response = await async_client.put(
            "/api/v1/offices/me",
            json=payload,
            cookies=cookies,
        )

        # CSRFトークンがないため失敗するはず
        assert response.status_code == 403
        assert "CSRF" in response.json().get("detail", "").upper()

    @pytest.mark.asyncio
    async def test_protected_endpoint_with_valid_csrf_token(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        owner_user_factory,
    ):
        """
        有効なCSRFトークンがあれば保護されたエンドポイントにアクセスできる
        """
        # CSRFトークンを取得
        csrf_response = await async_client.get("/api/v1/csrf-token")
        csrf_token = csrf_response.json()["csrf_token"]
        csrf_cookie = csrf_response.cookies.get("fastapi-csrf-token")

        # ユーザーを作成
        owner = await owner_user_factory()
        access_token = create_access_token(str(owner.id), timedelta(minutes=30))

        # CSRFトークン付きでリクエスト
        cookies = {
            "access_token": access_token,
            "fastapi-csrf-token": csrf_cookie,
        }
        headers = {"X-CSRF-Token": csrf_token}
        payload = {"name": "Updated Office Name"}

        response = await async_client.put(
            "/api/v1/offices/me",
            json=payload,
            cookies=cookies,
            headers=headers,
        )

        # 成功するはず
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Updated Office Name"

    @pytest.mark.asyncio
    async def test_protected_endpoint_with_invalid_csrf_token(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        owner_user_factory,
    ):
        """
        無効なCSRFトークンでは保護されたエンドポイントにアクセスできない
        """
        # ユーザーを作成
        owner = await owner_user_factory()
        access_token = create_access_token(str(owner.id), timedelta(minutes=30))

        # 無効なCSRFトークンでリクエスト
        cookies = {
            "access_token": access_token,
            "fastapi-csrf-token": "invalid_cookie_token",
        }
        headers = {"X-CSRF-Token": "invalid_header_token"}
        payload = {"name": "Updated Office Name"}

        response = await async_client.put(
            "/api/v1/offices/me",
            json=payload,
            cookies=cookies,
            headers=headers,
        )

        # 失敗するはず
        assert response.status_code == 403
        assert "CSRF" in response.json().get("detail", "").upper()

    @pytest.mark.asyncio
    async def test_bearer_token_does_not_require_csrf(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        owner_user_factory,
    ):
        """
        Bearer認証の場合はCSRFトークン不要

        Headerでトークンを送信する場合、CSRFトークンは不要
        （Same-Origin PolicyによりJavaScriptからのカスタムヘッダー送信は
        　攻撃者のサイトから不可能なため）
        """
        # ユーザーを作成
        owner = await owner_user_factory()
        access_token = create_access_token(str(owner.id), timedelta(minutes=30))

        # Bearer認証でリクエスト（CSRFトークンなし）
        headers = {"Authorization": f"Bearer {access_token}"}
        payload = {"name": "Updated Office Name"}

        response = await async_client.put(
            "/api/v1/offices/me",
            json=payload,
            headers=headers,
        )

        # Bearer認証ならCSRFトークンなしで成功するはず
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Updated Office Name"

    @pytest.mark.asyncio
    async def test_message_creation_requires_csrf_with_cookie(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        owner_user_factory,
        manager_user_factory,
    ):
        """
        メッセージ作成エンドポイントでもCSRF保護を確認
        """
        # ユーザーを作成
        owner = await owner_user_factory()
        manager = await manager_user_factory(office=owner.office_associations[0].office)
        access_token = create_access_token(str(owner.id), timedelta(minutes=30))

        # CSRFトークンなしでリクエスト（Cookie認証）
        cookies = {"access_token": access_token}
        payload = {
            "title": "Test Message",
            "body": "Test Body",
            "recipient_staff_ids": [str(manager.id)],
        }

        response = await async_client.post(
            "/api/v1/messages/personal",
            json=payload,
            cookies=cookies,
        )

        # CSRFトークンがないため失敗するはず
        assert response.status_code == 403
        assert "CSRF" in response.json().get("detail", "").upper()

    @pytest.mark.asyncio
    async def test_get_requests_do_not_require_csrf(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        owner_user_factory,
    ):
        """
        GETリクエストはCSRFトークン不要

        GETは状態を変更しないため、CSRF保護は不要
        """
        # ユーザーを作成
        owner = await owner_user_factory()
        access_token = create_access_token(str(owner.id), timedelta(minutes=30))

        # Cookie認証でGETリクエスト（CSRFトークンなし）
        cookies = {"access_token": access_token}

        response = await async_client.get(
            "/api/v1/offices/me",
            cookies=cookies,
        )

        # GETはCSRFトークンなしで成功するはず
        assert response.status_code == 200
