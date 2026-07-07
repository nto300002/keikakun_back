"""
CSRF保護のテスト

Cookie認証を使用する状態変更エンドポイント(POST/PUT/DELETE)に対して、
CSRFトークンの検証が正しく機能することを確認する。
"""
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import timedelta

from app import crud
from app.core.security import create_access_token
from app.models.enums import MessagePriority, MessageType


async def get_csrf_auth(async_client: AsyncClient, user_id) -> tuple[dict[str, str], dict[str, str]]:
    csrf_response = await async_client.get("/api/v1/csrf-token")
    csrf_token = csrf_response.json()["csrf_token"]
    csrf_cookie = csrf_response.cookies.get("fastapi-csrf-token")
    access_token = create_access_token(str(user_id), timedelta(minutes=30))
    return (
        {
            "access_token": access_token,
            "fastapi-csrf-token": csrf_cookie,
        },
        {"X-CSRF-Token": csrf_token},
    )


async def create_unread_message(db_session: AsyncSession, sender, recipient, title: str = "CSRF既読テスト"):
    office_id = sender.office_associations[0].office_id
    message_data = {
        "sender_staff_id": sender.id,
        "office_id": office_id,
        "recipient_ids": [recipient.id],
        "message_type": MessageType.personal,
        "priority": MessagePriority.normal,
        "title": title,
        "content": "CSRF cleanup regression test",
    }
    message = await crud.message.create_personal_message(db=db_session, obj_in=message_data)
    await db_session.commit()
    return message


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
    async def test_message_mark_as_read_with_valid_csrf_token(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        owner_user_factory,
        manager_user_factory,
    ):
        """メッセージ既読APIはCookie認証でも有効CSRF付きで成功する。"""
        owner = await owner_user_factory()
        manager = await manager_user_factory(office=owner.office_associations[0].office)
        message = await create_unread_message(db_session, sender=owner, recipient=manager)
        cookies, headers = await get_csrf_auth(async_client, manager.id)

        response = await async_client.post(
            f"/api/v1/messages/{message.id}/read",
            cookies=cookies,
            headers=headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["is_read"] is True
        assert data["read_at"] is not None

    @pytest.mark.asyncio
    async def test_message_mark_as_read_without_csrf_is_rejected_by_global_middleware(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        owner_user_factory,
        manager_user_factory,
    ):
        """個別dependencyを削除してもglobal middlewareが既読APIを保護する。"""
        owner = await owner_user_factory()
        manager = await manager_user_factory(office=owner.office_associations[0].office)
        message = await create_unread_message(db_session, sender=owner, recipient=manager)
        access_token = create_access_token(str(manager.id), timedelta(minutes=30))

        response = await async_client.post(
            f"/api/v1/messages/{message.id}/read",
            cookies={"access_token": access_token},
        )

        assert response.status_code == 403
        assert response.json()["detail"] == "CSRF token validation failed"

    @pytest.mark.asyncio
    async def test_message_mark_all_read_with_valid_csrf_token(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        owner_user_factory,
        manager_user_factory,
    ):
        """全既読APIはCookie認証でも有効CSRF付きで成功する。"""
        owner = await owner_user_factory()
        manager = await manager_user_factory(office=owner.office_associations[0].office)
        for index in range(3):
            await create_unread_message(
                db_session,
                sender=owner,
                recipient=manager,
                title=f"CSRF全既読テスト{index}",
            )
        cookies, headers = await get_csrf_auth(async_client, manager.id)

        response = await async_client.post(
            "/api/v1/messages/mark-all-read",
            cookies=cookies,
            headers=headers,
        )

        assert response.status_code == 200
        assert response.json()["updated_count"] == 3

    @pytest.mark.asyncio
    async def test_admin_announcement_create_with_valid_csrf_token(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        app_admin_user_factory,
        owner_user_factory,
    ):
        """app_adminのお知らせ作成APIはCookie認証でも有効CSRF付きで成功する。"""
        app_admin = await app_admin_user_factory()
        await owner_user_factory()
        cookies, headers = await get_csrf_auth(async_client, app_admin.id)

        response = await async_client.post(
            "/api/v1/admin/announcements",
            json={
                "title": "CSRFお知らせ",
                "content": "CSRF cleanup regression test",
                "priority": "normal",
            },
            cookies=cookies,
            headers=headers,
        )

        assert response.status_code == 201
        data = response.json()
        assert data["title"] == "CSRFお知らせ"
        assert data["message_type"] == "announcement"
        assert data["recipient_count"] >= 1

    @pytest.mark.asyncio
    async def test_admin_announcement_without_csrf_is_rejected_by_global_middleware(
        self,
        async_client: AsyncClient,
        app_admin_user_factory,
        owner_user_factory,
    ):
        """個別dependencyを削除してもglobal middlewareがapp_adminお知らせ作成を保護する。"""
        app_admin = await app_admin_user_factory()
        await owner_user_factory()
        access_token = create_access_token(str(app_admin.id), timedelta(minutes=30))

        response = await async_client.post(
            "/api/v1/admin/announcements",
            json={
                "title": "CSRFなしお知らせ",
                "content": "CSRF cleanup regression test",
                "priority": "normal",
            },
            cookies={"access_token": access_token},
        )

        assert response.status_code == 403
        assert response.json()["detail"] == "CSRF token validation failed"

    @pytest.mark.asyncio
    async def test_login_is_not_blocked_by_csrf_when_stale_access_cookie_exists(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        owner_user_factory,
    ):
        """
        ログインAPIは既存Cookieが残っていてもCSRFでは止めない。

        退会済み判定など、ログイン本体のエラーメッセージを返す必要があるため。
        """
        owner = await owner_user_factory()
        office = owner.office_associations[0].office
        office.is_deleted = True
        await db_session.commit()

        stale_access_token = create_access_token(str(owner.id), timedelta(minutes=30))

        response = await async_client.post(
            "/api/v1/auth/token",
            data={
                "username": owner.email,
                "password": "a-very-secure-password",
            },
            cookies={"access_token": stale_access_token},
        )

        assert response.status_code == 403
        assert response.json()["detail"] == "所属事務所が退会済みのため、ログインできません"

    @pytest.mark.asyncio
    async def test_logout_is_not_blocked_by_csrf_with_cookie_auth(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        owner_user_factory,
    ):
        """
        logoutは401後の後始末でも使うため、Cookie認証でもCSRF exemptにする。
        """
        owner = await owner_user_factory()
        access_token = create_access_token(str(owner.id), timedelta(minutes=30))

        response = await async_client.post(
            "/api/v1/auth/logout",
            cookies={"access_token": access_token},
        )

        assert response.status_code == 200
        assert response.json()["message"] == "ログアウトしました"
        assert "access_token=" in response.headers.get("set-cookie", "")

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
