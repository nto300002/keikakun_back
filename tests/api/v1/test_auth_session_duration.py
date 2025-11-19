import pytest
from datetime import datetime, timedelta
from jose import jwt
import os

from fastapi import status
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token, get_password_hash, ALGORITHM
from app.models.enums import StaffRole
from tests.utils import (
    create_random_staff,
)


class TestSessionDurationFixed:
    """セッション期間1時間固定のテスト（TDD）"""

    @pytest.mark.asyncio
    async def test_login_session_duration_fixed_to_1_hour(self, async_client: AsyncClient, db_session: AsyncSession):
        """
        正常系: ログイン時のセッション期間が常に1時間（3600秒）に固定されることをテスト

        前提条件:
        - スタッフユーザーが存在する
        - MFAは無効

        期待される結果:
        - ステータスコード: 200
        - session_duration: 3600（1時間）
        - session_type: "standard"
        - rememberMeパラメータは存在しない（削除済み）
        """
        # Arrange: テスト用スタッフを作成
        password = "testpassword123"
        staff = await create_random_staff(
            db_session,
            role=StaffRole.employee,
            is_mfa_enabled=False
        )
        staff.hashed_password = get_password_hash(password)
        # 一度だけcommit
        await db_session.commit()

        # Act: ログインエンドポイントを呼び出し（rememberMeパラメータなし）
        response = await async_client.post(
            "/api/v1/auth/token",
            data={
                "username": staff.email,
                "password": password,
            }
        )

        # Assert: レスポンス検証
        assert response.status_code == status.HTTP_200_OK
        data = response.json()

        # セッション期間が1時間（3600秒）に固定されていることを確認
        assert data["session_duration"] == 3600
        assert data["session_type"] == "standard"

        # Cookieからaccess_tokenを取得してJWTをデコード
        access_token = response.cookies.get("access_token")
        assert access_token is not None

        # JWTをデコードして有効期限を確認
        secret_key = os.getenv("SECRET_KEY", "test_secret_key_for_pytest")
        payload = jwt.decode(access_token, secret_key, algorithms=[ALGORITHM])

        # exp（有効期限）を確認
        assert "exp" in payload
        exp_timestamp = payload["exp"]
        iat_timestamp = payload.get("iat", datetime.utcnow().timestamp())

        # 有効期限が発行時刻から約1時間後であることを確認（多少の誤差を許容）
        duration = exp_timestamp - iat_timestamp
        assert 3590 <= duration <= 3610  # 3600秒 ± 10秒の誤差を許容

    @pytest.mark.asyncio
    async def test_login_remember_me_parameter_removed(self, async_client: AsyncClient, db_session: AsyncSession):
        """
        異常系: rememberMeパラメータが削除されており、送信してもエラーにならないことをテスト

        前提条件:
        - スタッフユーザーが存在する
        - MFAは無効

        期待される結果:
        - ステータスコード: 200（rememberMeパラメータは無視される）
        - session_duration: 3600（1時間）- rememberMeの値に関わらず固定
        - session_type: "standard"
        """
        # Arrange: テスト用スタッフを作成
        password = "testpassword123"
        staff = await create_random_staff(
            db_session,
            role=StaffRole.employee,
            is_mfa_enabled=False
        )
        staff.hashed_password = get_password_hash(password)
        # 一度だけcommit
        await db_session.commit()

        # Act: ログインエンドポイントを呼び出し（rememberMe=Trueを送信）
        response = await async_client.post(
            "/api/v1/auth/token",
            data={
                "username": staff.email,
                "password": password,
                "rememberMe": "true",  # このパラメータは無視される
            }
        )

        # Assert: レスポンス検証
        # rememberMeパラメータが存在しても、実装がそれを無視することを確認
        # ただし、実装が完全に削除されていない場合は、このテストは失敗する
        assert response.status_code == status.HTTP_200_OK
        data = response.json()

        # セッション期間が1時間（3600秒）に固定されていることを確認
        # rememberMe=trueを送信しても8時間にはならない
        assert data["session_duration"] == 3600
        assert data["session_type"] == "standard"

    @pytest.mark.asyncio
    async def test_login_mfa_session_duration_fixed(self, async_client: AsyncClient, db_session: AsyncSession):
        """
        正常系: MFA有効ユーザーのログイン時もセッション期間が1時間に固定されることをテスト

        前提条件:
        - スタッフユーザーが存在する
        - MFAが有効

        期待される結果:
        - ステータスコード: 200
        - session_duration: 3600（1時間）
        - session_type: "standard"
        - requires_mfa_verification: True
        """
        # Arrange: テスト用スタッフを作成（MFA有効）
        from app.core.security import generate_totp_secret

        password = "testpassword123"
        staff = await create_random_staff(
            db_session,
            role=StaffRole.employee,
            is_mfa_enabled=True
        )
        staff.hashed_password = get_password_hash(password)
        staff.set_mfa_secret(generate_totp_secret())  # Use method to encrypt secret
        staff.is_mfa_verified_by_user = True  # Normal MFA flow, not first-time setup
        # 一度だけcommit
        await db_session.commit()

        # Act: ログインエンドポイントを呼び出し
        response = await async_client.post(
            "/api/v1/auth/token",
            data={
                "username": staff.email,
                "password": password,
            }
        )

        # Assert: レスポンス検証
        assert response.status_code == status.HTTP_200_OK
        data = response.json()

        # MFA検証が必要であることを確認
        assert data["requires_mfa_verification"] is True
        assert "temporary_token" in data

        # セッション期間が1時間（3600秒）に固定されていることを確認
        assert data["session_duration"] == 3600
        assert data["session_type"] == "standard"

    @pytest.mark.asyncio
    async def test_refresh_token_session_duration_preserved(self, async_client: AsyncClient, db_session: AsyncSession):
        """
        正常系: リフレッシュトークン使用時もセッション期間が1時間で維持されることをテスト

        前提条件:
        - スタッフユーザーが存在する
        - 有効なリフレッシュトークンを持っている

        期待される結果:
        - ステータスコード: 200
        - 新しいaccess_tokenのセッション期間が1時間
        """
        # Arrange: テスト用スタッフを作成してログイン
        password = "testpassword123"
        staff = await create_random_staff(
            db_session,
            role=StaffRole.employee,
            is_mfa_enabled=False
        )
        staff.hashed_password = get_password_hash(password)
        # 一度だけcommit
        await db_session.commit()

        # ログインしてリフレッシュトークンを取得
        login_response = await async_client.post(
            "/api/v1/auth/token",
            data={
                "username": staff.email,
                "password": password,
            }
        )
        assert login_response.status_code == status.HTTP_200_OK
        refresh_token = login_response.json()["refresh_token"]

        # Act: リフレッシュトークンエンドポイントを呼び出し
        response = await async_client.post(
            "/api/v1/auth/refresh-token",
            json={"refresh_token": refresh_token}
        )

        # Assert: レスポンス検証
        assert response.status_code == status.HTTP_200_OK

        # 新しいaccess_tokenのCookieを取得してJWTをデコード
        new_access_token = response.cookies.get("access_token")
        assert new_access_token is not None

        # JWTをデコードして有効期限を確認
        secret_key = os.getenv("SECRET_KEY", "test_secret_key_for_pytest")
        payload = jwt.decode(new_access_token, secret_key, algorithms=[ALGORITHM])

        # 有効期限が1時間後であることを確認
        assert "exp" in payload
        exp_timestamp = payload["exp"]
        iat_timestamp = payload.get("iat", datetime.utcnow().timestamp())

        duration = exp_timestamp - iat_timestamp
        assert 3590 <= duration <= 3610  # 3600秒 ± 10秒の誤差を許容
