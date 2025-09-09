import pytest
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import patch, MagicMock

from fastapi import status
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app import crud
from app.models.staff import Staff
from app.models.enums import StaffRole
from app.core.security import create_access_token, verify_totp, generate_totp_secret, get_password_hash
from tests.utils import (
    random_email,
    random_string,
    create_random_staff,
)


class TestMFAEnrollment:
    """MFA登録機能のテスト"""
    
    @pytest.mark.asyncio
    async def test_mfa_enroll_success(self, async_client: AsyncClient, db_session: AsyncSession):
        """MFA登録が成功する正常系テスト"""
        # テスト用スタッフを作成（MFA未設定）
        staff = await create_random_staff(db_session, is_mfa_enabled=False)
        await db_session.commit()
        
        # アクセストークンを作成
        token = create_access_token(subject=str(staff.id))
        headers = {"Authorization": f"Bearer {token}"}
        
        # MFA登録エンドポイントを呼び出し
        response = await async_client.post("/api/v1/auth/mfa/enroll", headers=headers)
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        
        # レスポンスにQRコードURIとシークレットキーが含まれること
        assert "qr_code_uri" in data
        assert "secret_key" in data
        assert data["qr_code_uri"].startswith("otpauth://totp/")
        
        # DBでMFAシークレットが設定されていることを確認
        await db_session.refresh(staff)
        assert staff.mfa_secret is not None
        assert staff.is_mfa_enabled is False  # まだ検証前なので無効
        
    @pytest.mark.asyncio
    async def test_mfa_enroll_already_enabled(self, async_client: AsyncClient, db_session: AsyncSession):
        """MFA既に有効なユーザーが再登録しようとする異常系テスト"""
        # MFA有効なスタッフを作成
        staff = await create_random_staff(db_session, is_mfa_enabled=True)
        await db_session.commit()
        
        token = create_access_token(subject=str(staff.id))
        headers = {"Authorization": f"Bearer {token}"}
        
        response = await async_client.post("/api/v1/auth/mfa/enroll", headers=headers)
        
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "already enabled" in response.json()["detail"].lower()
        
    @pytest.mark.asyncio
    async def test_mfa_enroll_unauthorized(self, async_client: AsyncClient):
        """認証なしでMFA登録しようとする異常系テスト"""
        response = await async_client.post("/api/v1/auth/mfa/enroll")
        
        assert response.status_code == status.HTTP_401_UNAUTHORIZED


class TestMFAVerification:
    """MFA検証機能のテスト"""
    
    @pytest.mark.asyncio
    async def test_mfa_verify_success(self, async_client: AsyncClient, db_session: AsyncSession):
        """MFA検証が成功する正常系テスト"""
        # テスト用スタッフを作成（MFAシークレット設定済み、有効化前）
        staff = await create_random_staff(db_session, is_mfa_enabled=False)
        mfa_secret = generate_totp_secret()
        staff.mfa_secret = mfa_secret
        await db_session.commit()
        
        token = create_access_token(subject=str(staff.id))
        headers = {"Authorization": f"Bearer {token}"}
        
        # 正しいTOTPコードを生成
        with patch('''app.services.mfa.verify_totp''') as mock_verify:
            mock_verify.return_value = True
            
            response = await async_client.post(
                "/api/v1/auth/mfa/verify",
                headers=headers,
                json={"totp_code": "123456"}
            )
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["message"] == "MFA verification successful"
        
        # DBでMFAが有効化されていることを確認
        await db_session.refresh(staff)
        assert staff.is_mfa_enabled is True
        
    @pytest.mark.asyncio
    async def test_mfa_verify_invalid_code(self, async_client: AsyncClient, db_session: AsyncSession):
        """無効なTOTPコードでのMFA検証異常系テスト"""
        staff = await create_random_staff(db_session, is_mfa_enabled=False)
        staff.mfa_secret = generate_totp_secret()
        await db_session.commit()
        
        token = create_access_token(subject=str(staff.id))
        headers = {"Authorization": f"Bearer {token}"}
        
        # 無効なTOTPコード
        with patch('''app.core.security.verify_totp''') as mock_verify:
            mock_verify.return_value = False
            
            response = await async_client.post(
                "/api/v1/auth/mfa/verify",
                headers=headers,
                json={"totp_code": "000000"}
            )
        
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "invalid" in response.json()["detail"].lower()
        
        # MFAは有効化されていないこと
        await db_session.refresh(staff)
        assert staff.is_mfa_enabled is False
        
    @pytest.mark.asyncio
    async def test_mfa_verify_no_secret(self, async_client: AsyncClient, db_session: AsyncSession):
        """MFAシークレット未設定でのMFA検証異常系テスト"""
        staff = await create_random_staff(db_session, is_mfa_enabled=False)
        await db_session.commit()
        
        token = create_access_token(subject=str(staff.id))
        headers = {"Authorization": f"Bearer {token}"}
        
        response = await async_client.post(
            "/api/v1/auth/mfa/verify",
            headers=headers,
            json={"totp_code": "123456"}
        )
        
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "not enrolled" in response.json()["detail"].lower()


class TestMFALogin:
    """MFA組み込みログイン機能のテスト"""
    
    @pytest.mark.asyncio
    async def test_login_mfa_not_enabled_first_time(self, async_client: AsyncClient, db_session: AsyncSession):
        """MFA未設定ユーザーの初回ログイン正常系テスト"""
        staff = await create_random_staff(db_session, is_mfa_enabled=False)
        password = "testpassword123"
        staff.hashed_password = get_password_hash(password)
        await db_session.commit()
        
        response = await async_client.post(
            "/api/v1/auth/token",
            data={"username": staff.email, "password": password}
        )
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        
        # MFA未設定ユーザーは通常のトークンが発行される
        assert "access_token" in data
        assert "refresh_token" in data
        assert data["token_type"] == "bearer"
        
    @pytest.mark.asyncio
    async def test_login_mfa_enabled_success(self, async_client: AsyncClient, db_session: AsyncSession):
        """MFA有効ユーザーのログイン（TOTP検証成功）正常系テスト"""
        staff = await create_random_staff(db_session, is_mfa_enabled=True)
        password = "testpassword123"
        staff.hashed_password = get_password_hash(password)
        staff.mfa_secret = generate_totp_secret()
        await db_session.commit()
        
        # 1段階目: メール・パスワード認証
        login_response = await async_client.post(
            "/api/v1/auth/token",
            data={"username": staff.email, "password": password}
        )
        
        assert login_response.status_code == status.HTTP_200_OK
        login_data = login_response.json()
        assert login_data["requires_mfa_verification"] is True
        assert "temporary_token" in login_data
        
        # 2段階目: TOTP検証
        temp_token = login_data["temporary_token"]
        with patch('''app.api.v1.endpoints.auths.verify_totp''') as mock_verify:
            mock_verify.return_value = True
            
            verify_response = await async_client.post(
                "/api/v1/auth/token/verify-mfa",
                json={
                    "temporary_token": temp_token,
                    "totp_code": "123456"
                }
            )
        
        assert verify_response.status_code == status.HTTP_200_OK
        verify_data = verify_response.json()
        assert "access_token" in verify_data
        assert "refresh_token" in verify_data
        assert verify_data["token_type"] == "bearer"
        
    @pytest.mark.asyncio
    async def test_login_mfa_enabled_invalid_totp(self, async_client: AsyncClient, db_session: AsyncSession):
        """MFA有効ユーザーのログイン（TOTP検証失敗）異常系テスト"""
        staff = await create_random_staff(db_session, is_mfa_enabled=True)
        password = "testpassword123"
        staff.hashed_password = get_password_hash(password)
        staff.mfa_secret = generate_totp_secret()
        await db_session.commit()
        
        # 1段階目: メール・パスワード認証
        login_response = await async_client.post(
            "/api/v1/auth/token",
            data={"username": staff.email, "password": password}
        )
        temp_token = login_response.json()["temporary_token"]
        
        # 2段階目: 無効なTOTP検証
        with patch('''app.core.security.verify_totp''') as mock_verify:
            mock_verify.return_value = False
            
            verify_response = await async_client.post(
                "/api/v1/auth/token/verify-mfa",
                json={
                    "temporary_token": temp_token,
                    "totp_code": "000000"
                }
            )
        
        assert verify_response.status_code == status.HTTP_401_UNAUTHORIZED
        assert "invalid" in verify_response.json()["detail"].lower()
        
    @pytest.mark.asyncio
    async def test_login_invalid_temporary_token(self, async_client: AsyncClient):
        """無効な一時トークンでのMFA検証異常系テスト"""
        response = await async_client.post(
            "/api/v1/auth/token/verify-mfa",
            json={
                "temporary_token": "invalid_token",
                "totp_code": "123456"
            }
        )
        
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert "invalid" in response.json()["detail"].lower()


class TestMFARecoveryCode:
    """MFAリカバリーコード機能のテスト"""
    
    @pytest.mark.asyncio
    async def test_mfa_recovery_code_success(self, async_client: AsyncClient, db_session: AsyncSession):
        """リカバリーコードでのMFA検証成功正常系テスト"""
        staff = await create_random_staff(db_session, is_mfa_enabled=True)
        password = "testpassword123"
        staff.hashed_password = get_password_hash(password)
        staff.mfa_secret = generate_totp_secret()
        
        # リカバリーコードを設定（実際の実装ではハッシュ化される）
        recovery_codes = ["recovery123", "recovery456"]
        staff.mfa_recovery_codes = recovery_codes
        await db_session.commit()
        
        # 1段階目: ログイン
        login_response = await async_client.post(
            "/api/v1/auth/token",
            data={"username": staff.email, "password": password}
        )
        temp_token = login_response.json()["temporary_token"]
        
        # 2段階目: リカバリーコード使用
        with patch('''app.core.security.verify_recovery_code''') as mock_verify:
            mock_verify.return_value = True
            
            verify_response = await async_client.post(
                "/api/v1/auth/token/verify-mfa",
                json={
                    "temporary_token": temp_token,
                    "recovery_code": "recovery123"
                }
            )
        
        assert verify_response.status_code == status.HTTP_200_OK
        data = verify_response.json()
        assert "access_token" in data
        
    @pytest.mark.asyncio  
    async def test_mfa_recovery_code_invalid(self, async_client: AsyncClient, db_session: AsyncSession):
        """無効なリカバリーコードでのMFA検証異常系テスト"""
        staff = await create_random_staff(db_session, is_mfa_enabled=True)
        password = "testpassword123"
        staff.hashed_password = get_password_hash(password)
        staff.mfa_secret = generate_totp_secret()
        await db_session.commit()
        
        # 1段階目: ログイン
        login_response = await async_client.post(
            "/api/v1/auth/token",
            data={"username": staff.email, "password": password}
        )
        temp_token = login_response.json()["temporary_token"]
        
        # 2段階目: 無効なリカバリーコード
        with patch('''app.core.security.verify_recovery_code''') as mock_verify:
            mock_verify.return_value = False
            
            verify_response = await async_client.post(
                "/api/v1/auth/token/verify-mfa",
                json={
                    "temporary_token": temp_token,
                    "recovery_code": "invalid_code"
                }
            )
        
        assert verify_response.status_code == status.HTTP_401_UNAUTHORIZED


class TestMFADisable:
    """MFA無効化機能のテスト"""

    @pytest.mark.asyncio
    async def test_mfa_disable_success(self, async_client: AsyncClient, db_session: AsyncSession):
        """MFA無効化成功正常系テスト"""
        staff = await create_random_staff(db_session, is_mfa_enabled=True)
        staff.mfa_secret = generate_totp_secret()
        password = "testpassword123"
        staff.hashed_password = get_password_hash(password)
        await db_session.commit()
        
        token = create_access_token(subject=str(staff.id))
        headers = {"Authorization": f"Bearer {token}"}
        
        with patch('''app.core.security.verify_password''') as mock_verify:
            mock_verify.return_value = True
            
            response = await async_client.post(
                "/api/v1/auth/mfa/disable",
                headers=headers,
                json={"password": password}
            )
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["message"] == "MFA disabled successfully"
        
        # DBでMFAが無効化されていることを確認
        await db_session.refresh(staff)
        assert staff.is_mfa_enabled is False
        assert staff.mfa_secret is None
        
    @pytest.mark.asyncio
    async def test_mfa_disable_wrong_password(self, async_client: AsyncClient, db_session: AsyncSession):
        """MFA無効化時のパスワード間違い異常系テスト"""
        staff = await create_random_staff(db_session, is_mfa_enabled=True)
        await db_session.commit()
        
        token = create_access_token(subject=str(staff.id))
        headers = {"Authorization": f"Bearer {token}"}
        
        with patch('''app.core.security.verify_password''') as mock_verify:
            mock_verify.return_value = False
            
            response = await async_client.post(
                "/api/v1/auth/mfa/disable",
                headers=headers,
                json={"password": "wrongpassword"}
            )
        
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert "incorrect password" in response.json()["detail"].lower()
        
        # MFAは無効化されていないこと
        await db_session.refresh(staff)
        assert staff.is_mfa_enabled is True
