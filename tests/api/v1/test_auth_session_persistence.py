import pytest
import os
from datetime import datetime, timedelta
from httpx import AsyncClient
from unittest.mock import patch
from jose import jwt as jose_jwt
from app.core.security import decode_access_token
from sqlalchemy.ext.asyncio import AsyncSession

import pytest_asyncio

# --- 追加: conftest に合わせたテスト用 fixture ---
@pytest_asyncio.fixture
async def test_password() -> str:
    # conftest のファクトリがこの値でハッシュ化してユーザーを作る想定
    return "a-very-secure-password"

@pytest_asyncio.fixture
async def test_staff_user(employee_user_factory, test_password):
    # employee_user_factory は conftest に定義済みの async factory
    return await employee_user_factory(email="staff@example.com", name="Test Staff", password=test_password)

@pytest_asyncio.fixture
async def test_admin_user(manager_user_factory, test_password):
    # manager_user_factory は conftest に定義済みの async factory
    return await manager_user_factory(email="admin@example.com", name="Test Admin", password=test_password)

# 非同期テストであることを明示
pytestmark = pytest.mark.asyncio


class TestAuthSessionPersistence:
    """ログイン状態保持機能のテスト"""

    async def test_login_without_remember_me_creates_1hour_session(
        self, async_client: AsyncClient, test_staff_user, test_password
    ):
        """チェックボックス未選択時に1時間セッションが作成されることをテスト"""
        login_data = {
            "username": test_staff_user.email,
            "password": test_password,
            "rememberMe": False
        }

        response = await async_client.post("/api/v1/auth/token", data=login_data)

        assert response.status_code == 200
        response_data = response.json()

        # Cookie認証: access_tokenはCookieに設定される
        assert "access_token" in response.cookies
        assert "access_token" not in response_data  # レスポンスボディには含まれない

        # レスポンスボディの検証
        assert "session_duration" in response_data
        assert response_data["session_duration"] == 3600  # 1時間（3600秒）

        # トークンをデコードして期限を確認
        token = response.cookies.get("access_token")
        secret_key = os.getenv("SECRET_KEY", "test_secret_key_for_pytest")
        payload = decode_access_token(token)

        # トークンの有効期限が約1時間後
        exp_time = datetime.fromtimestamp(payload["exp"])
        iat_time = datetime.fromtimestamp(payload["iat"])
        duration = exp_time - iat_time

        assert 3590 <= duration.total_seconds() <= 3610  # 1時間±10秒の許容範囲

    async def test_login_with_remember_me_creates_8hour_session(
        self, async_client: AsyncClient, test_staff_user, test_password
    ):
        """チェックボックス選択時に8時間セッションが作成されることをテスト"""
        login_data = {
            "username": test_staff_user.email,
            "password": test_password,
            "rememberMe": True
        }

        response = await async_client.post("/api/v1/auth/token", data=login_data)

        assert response.status_code == 200
        response_data = response.json()

        # Cookie認証: access_tokenはCookieに設定される
        assert "access_token" in response.cookies
        assert "access_token" not in response_data

        # レスポンスボディの検証
        assert "session_duration" in response_data
        assert response_data["session_duration"] == 28800  # 8時間（28800秒）

        # トークンをデコードして期限を確認
        token = response.cookies.get("access_token")
        secret_key = os.getenv("SECRET_KEY", "test_secret_key_for_pytest")
        payload = decode_access_token(token)

        # トークンの有効期限が約8時間後
        exp_time = datetime.fromtimestamp(payload["exp"])
        iat_time = datetime.fromtimestamp(payload["iat"])
        duration = exp_time - iat_time

        assert 28790 <= duration.total_seconds() <= 28810  # 8時間±10秒の許容範囲

    async def test_default_behavior_without_remember_me_parameter(
        self, async_client: AsyncClient, test_staff_user, test_password
    ):
        """rememberMeパラメータ未指定時はデフォルトで1時間セッション"""
        login_data = {
            "username": test_staff_user.email,
            "password": test_password
        }

        response = await async_client.post("/api/v1/auth/token", data=login_data)

        assert response.status_code == 200
        response_data = response.json()

        # デフォルトは1時間セッション
        assert response_data["session_duration"] == 3600

    async def test_token_contains_session_type_claim(
        self, async_client: AsyncClient, test_staff_user, test_password
    ):
        """JWTトークンにセッション種別のクレームが含まれることをテスト"""
        # 8時間セッションでログイン
        login_data = {
            "username": test_staff_user.email,
            "password": test_password,
            "rememberMe": True
        }

        response = await async_client.post("/api/v1/auth/token", data=login_data)

        # Cookie認証: access_tokenはCookieに設定される
        assert "access_token" in response.cookies
        token = response.cookies.get("access_token")

        # トークンをデコードしてカスタムクレームを確認
        secret_key = os.getenv("SECRET_KEY", "test_secret_key_for_pytest")
        payload = decode_access_token(token)

        assert "session_type" in payload
        assert payload["session_type"] == "extended"
        assert "session_duration" in payload
        assert payload["session_duration"] == 28800

        # 1時間セッションでログイン
        login_data["rememberMe"] = False
        response = await async_client.post("/api/v1/auth/token", data=login_data)

        # Cookie認証: access_tokenはCookieに設定される
        assert "access_token" in response.cookies
        token = response.cookies.get("access_token")

        secret_key = os.getenv("SECRET_KEY", "test_secret_key_for_pytest")
        payload = decode_access_token(token)

        assert payload["session_type"] == "standard"
        assert payload["session_duration"] == 3600

    async def test_expired_1hour_token_rejected(
        self, async_client: AsyncClient, test_staff_user
    ):
        """1時間経過後のトークンが拒否されることをテスト"""
        # 期限切れトークンを手動作成（1時間前に発行された1時間有効トークン）
        past_time = datetime.utcnow() - timedelta(hours=1, minutes=1)
        exp_time = past_time + timedelta(hours=1)

        payload = {
            "sub": str(test_staff_user.id),
            "iat": int(past_time.timestamp()),
            "exp": int(exp_time.timestamp()),
            "session_type": "standard",
            "session_duration": 3600
        }

        secret_key = os.getenv("SECRET_KEY", "test_secret_key_for_pytest")
        expired_token = jose_jwt.encode(payload, secret_key, algorithm="HS256")

        # 期限切れトークンで保護されたエンドポイントにアクセス
        headers = {"Authorization": f"Bearer {expired_token}"}
        response = await async_client.get("/api/v1/staffs/me", headers=headers)

        assert response.status_code == 401
        assert "Could not validate credentials" in response.json()["detail"]

    async def test_valid_8hour_token_accepted_after_7hours(
        self, async_client: AsyncClient, test_staff_user
    ):
        """7時間経過後の8時間トークンが受け入れられることをテスト"""
        # 7時間前に発行された8時間有効トークンを作成
        past_time = datetime.utcnow() - timedelta(hours=7)
        exp_time = past_time + timedelta(hours=8)

        payload = {
            "sub": str(test_staff_user.id),
            "iat": int(past_time.timestamp()),
            "exp": int(exp_time.timestamp()),
            "session_type": "extended",
            "session_duration": 28800
        }

        secret_key = os.getenv("SECRET_KEY", "test_secret_key_for_pytest")
        valid_token = jose_jwt.encode(payload, secret_key, algorithm="HS256")

        # 有効なトークンで保護されたエンドポイントにアクセス
        headers = {"Authorization": f"Bearer {valid_token}"}
        response = await async_client.get("/api/v1/staffs/me", headers=headers)

        assert response.status_code == 200

    async def test_expired_8hour_token_rejected(
        self, async_client: AsyncClient, test_staff_user
    ):
        """8時間経過後の8時間トークンが拒否されることをテスト"""
        # 期限切れ8時間トークンを作成（8時間1分前に発行）
        past_time = datetime.utcnow() - timedelta(hours=8, minutes=1)
        exp_time = past_time + timedelta(hours=8)

        payload = {
            "sub": str(test_staff_user.id),
            "iat": int(past_time.timestamp()),
            "exp": int(exp_time.timestamp()),
            "session_type": "extended",
            "session_duration": 28800
        }

        secret_key = os.getenv("SECRET_KEY", "test_secret_key_for_pytest")
        expired_token = jose_jwt.encode(payload, secret_key, algorithm="HS256")

        # 期限切れトークンで保護されたエンドポイントにアクセス
        headers = {"Authorization": f"Bearer {expired_token}"}
        response = await async_client.get("/api/v1/staffs/me", headers=headers)

        assert response.status_code == 401
        assert "Could not validate credentials" in response.json()["detail"]

    async def test_refresh_token_maintains_session_type(
        self, async_client: AsyncClient, test_staff_user, test_password
    ):
        """リフレッシュ時に元のセッション種別が維持されることをテスト"""
        # 8時間セッションでログイン
        login_data = {
            "username": test_staff_user.email,
            "password": test_password,
            "rememberMe": True
        }

        login_response = await async_client.post("/api/v1/auth/token", data=login_data)
        refresh_token = login_response.json()["refresh_token"]

        # リフレッシュトークンを使用して新しいアクセストークンを取得
        refresh_data = {"refresh_token": refresh_token}
        refresh_response = await async_client.post("/api/v1/auth/refresh-token", json=refresh_data)

        assert refresh_response.status_code == 200

        # Cookie認証: access_tokenはCookieに設定される
        assert "access_token" in refresh_response.cookies
        new_token = refresh_response.cookies.get("access_token")
        payload = decode_access_token(new_token)

        # 新しいトークンも8時間セッション
        assert payload["session_type"] == "extended"
        assert payload["session_duration"] == 28800

    async def test_logout_endpoint_works(
        self, async_client: AsyncClient, test_staff_user, test_password
    ):
        """ログアウトエンドポイントが正常に動作することをテスト"""
        # 8時間セッションでログイン
        login_data = {
            "username": test_staff_user.email,
            "password": test_password,
            "rememberMe": True
        }

        login_response = await async_client.post("/api/v1/auth/token", data=login_data)

        # Cookie認証: access_tokenはCookieに設定される
        assert "access_token" in login_response.cookies
        token = login_response.cookies.get("access_token")

        # ログアウト
        headers = {"Authorization": f"Bearer {token}"}
        logout_response = await async_client.post("/api/v1/auth/logout", headers=headers)

        assert logout_response.status_code == 200
        assert logout_response.json()["message"] == "Logout successful"

        # 注意: JWTトークンはステートレスなので、ログアウト後もサーバー側では技術的に有効
        # 実際のアプリケーションではクライアント側でトークンを削除する
        # Cookie削除はresponse.delete_cookie()で実行されるが、テスト環境ではCookieの削除を
        # 直接検証することは難しいため、ログアウトエンドポイントが正常に動作することのみ確認

    async def test_concurrent_different_session_types(
        self, async_client: AsyncClient, test_staff_user, test_admin_user, test_password
    ):
        """異なるユーザーが異なるセッション種別で同時ログインできることをテスト"""
        # スタッフユーザーは1時間セッション
        staff_login_data = {
            "username": test_staff_user.email,
            "password": test_password,
            "rememberMe": False
        }
        staff_response = await async_client.post("/api/v1/auth/token", data=staff_login_data)
        assert staff_response.status_code == 200, f"staff token endpoint failed: {staff_response.status_code} {staff_response.text}"

        # Cookie認証: access_tokenはCookieに設定される
        assert "access_token" in staff_response.cookies, f"staff token missing in cookies: {staff_response.cookies}"
        staff_token = staff_response.cookies.get("access_token")

        # 管理者ユーザーは8時間セッション
        admin_login_data = {
            "username": test_admin_user.email,
            "password": test_password,
            "rememberMe": True
        }
        admin_response = await async_client.post("/api/v1/auth/token", data=admin_login_data)
        assert admin_response.status_code == 200, f"admin token endpoint failed: {admin_response.status_code} {admin_response.text}"

        # Cookie認証: access_tokenはCookieに設定される
        assert "access_token" in admin_response.cookies, f"admin token missing in cookies: {admin_response.cookies}"
        admin_token = admin_response.cookies.get("access_token")

        # 両方のトークンが有効
        staff_headers = {"Authorization": f"Bearer {staff_token}"}
        admin_headers = {"Authorization": f"Bearer {admin_token}"}

        staff_check = await async_client.get("/api/v1/staffs/me", headers=staff_headers)
        admin_check = await async_client.get("/api/v1/staffs/me", headers=admin_headers)

        if staff_check.status_code != 200:
            print(">>>> DEBUG staff_check failed <<<<", staff_check.status_code, staff_check.text)
            # try common alternative path for debug
            alt = await async_client.get("/api/v1/staffs/me", headers=staff_headers)
            print(">>>> DEBUG staff_check alt /api/v1/staffs/me <<<<", alt.status_code, alt.text)
        if admin_check.status_code != 200:
            print(">>>> DEBUG admin_check failed <<<<", admin_check.status_code, admin_check.text)
            alt = await async_client.get("/api/v1/staffs/me", headers=admin_headers)
            print(">>>> DEBUG admin_check alt /api/v1/staffs/me <<<<", alt.status_code, alt.text)

        assert staff_check.status_code == 200, f"staff /staffs/me failed: {staff_check.status_code} {staff_check.text}"
        assert admin_check.status_code == 200, f"admin /staffs/me failed: {admin_check.status_code} {admin_check.text}"

        # トークンの種別確認
        staff_payload = decode_access_token(staff_token)
        admin_payload = decode_access_token(admin_token)

        assert staff_payload["session_type"] == "standard"
        assert admin_payload["session_type"] == "extended"