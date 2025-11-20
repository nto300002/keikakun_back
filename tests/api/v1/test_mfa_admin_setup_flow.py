"""
管理者によるMFA設定後のユーザー初回検証フローのテスト

このテストは以下をカバーします:
1. 管理者がMFA有効化 → is_mfa_verified_by_user = False
2. ユーザーログイン → requires_mfa_first_setup = True
3. 初回検証成功 → is_mfa_verified_by_user = True
4. ユーザー自身のMFA設定 → 両方のフラグが True
5. 管理者によるMFA無効化 → is_mfa_verified_by_user もリセット
6. 管理者による再有効化 → 再度初回検証が必要
"""

import pytest
from unittest.mock import patch
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token, generate_totp_secret, get_password_hash
from tests.utils import create_random_staff


class TestAdminMFASetupFlow:
    """管理者によるMFA設定フローのテスト"""

    @pytest.mark.asyncio
    async def test_admin_enable_mfa_sets_verified_false(
        self, async_client: AsyncClient, db_session: AsyncSession
    ):
        """
        管理者がMFA有効化すると、is_mfa_verified_by_user = False になる
        """
        # Owner（管理者）を作成
        admin = await create_random_staff(db_session, role="owner")
        await db_session.flush()  # IDを生成
        admin_token = create_access_token(subject=str(admin.id))

        # 対象スタッフを作成
        target_staff = await create_random_staff(db_session, is_mfa_enabled=False)
        await db_session.flush()  # IDを生成

        # 管理者がMFA有効化
        response = await async_client.post(
            f"/api/v1/auth/admin/staff/{target_staff.id}/mfa/enable",
            headers={"Authorization": f"Bearer {admin_token}"},
        )

        assert response.status_code == 200
        data = response.json()
        assert "qr_code_uri" in data
        assert "secret_key" in data

        # DBを確認
        await db_session.refresh(target_staff)
        assert target_staff.is_mfa_enabled is True
        assert target_staff.is_mfa_verified_by_user is False  # ← 重要

    @pytest.mark.asyncio
    async def test_login_with_admin_enabled_mfa_requires_first_setup(
        self, async_client: AsyncClient, db_session: AsyncSession
    ):
        """
        管理者が設定したMFAの場合、ログイン時に初回セットアップが必要
        """
        # スタッフを作成（管理者がMFA設定済み）
        password = "testpassword123"
        staff = await create_random_staff(db_session, is_mfa_enabled=True)
        staff.hashed_password = get_password_hash(password)
        staff.set_mfa_secret(generate_totp_secret())
        staff.is_mfa_verified_by_user = False  # 管理者が設定
        await db_session.commit()

        # ログイン試行
        response = await async_client.post(
            "/api/v1/auth/token",
            data={"username": staff.email, "password": password},
        )

        assert response.status_code == 200
        data = response.json()

        # 初回セットアップが必要
        assert data.get("requires_mfa_first_setup") is True
        assert "temporary_token" in data
        assert "qr_code_uri" in data
        assert "secret_key" in data
        assert "message" in data

    @pytest.mark.asyncio
    async def test_first_time_mfa_verify_success(
        self, async_client: AsyncClient, db_session: AsyncSession
    ):
        """
        初回MFA検証が成功すると、is_mfa_verified_by_user = True になる
        """
        # スタッフを作成（管理者がMFA設定済み）
        password = "testpassword123"
        staff = await create_random_staff(db_session, is_mfa_enabled=True)
        staff.hashed_password = get_password_hash(password)
        staff.set_mfa_secret(generate_totp_secret())
        staff.is_mfa_verified_by_user = False
        await db_session.commit()

        # ログインして一時トークン取得
        login_response = await async_client.post(
            "/api/v1/auth/token",
            data={"username": staff.email, "password": password},
        )
        temp_token = login_response.json()["temporary_token"]

        # 初回検証（TOTPコード検証をモック）
        with patch("app.api.v1.endpoints.auths.verify_totp") as mock_verify:
            mock_verify.return_value = True

            verify_response = await async_client.post(
                "/api/v1/auth/mfa/first-time-verify",
                json={
                    "temporary_token": temp_token,
                    "totp_code": "123456",
                },
            )

        assert verify_response.status_code == 200
        verify_data = verify_response.json()

        # アクセストークンが発行される
        assert "access_token" in verify_response.cookies or "access_token" in verify_data
        assert "refresh_token" in verify_data

        # DBを確認
        await db_session.refresh(staff)
        assert staff.is_mfa_verified_by_user is True  # ← 重要

    @pytest.mark.asyncio
    async def test_user_self_setup_sets_both_flags_true(
        self, async_client: AsyncClient, db_session: AsyncSession
    ):
        """
        ユーザー自身がMFA設定すると、両方のフラグがTrueになる
        """
        # スタッフを作成（MFA未設定）
        staff = await create_random_staff(db_session, is_mfa_enabled=False)
        await db_session.flush()  # IDを生成
        token = create_access_token(subject=str(staff.id))
        headers = {"Authorization": f"Bearer {token}"}

        # MFA登録
        enroll_response = await async_client.post(
            "/api/v1/auth/mfa/enroll",
            headers=headers,
        )
        assert enroll_response.status_code == 200

        # MFA検証（TOTPコード検証をモック）
        with patch("app.services.mfa.verify_totp") as mock_verify:
            mock_verify.return_value = True

            verify_response = await async_client.post(
                "/api/v1/auth/mfa/verify",
                headers=headers,
                json={"totp_code": "123456"},
            )

        assert verify_response.status_code == 200

        # DBを確認
        await db_session.refresh(staff)
        assert staff.is_mfa_enabled is True
        assert staff.is_mfa_verified_by_user is True  # ← 両方True

    @pytest.mark.asyncio
    async def test_admin_disable_mfa_resets_verified_flag(
        self, async_client: AsyncClient, db_session: AsyncSession
    ):
        """
        管理者がMFA無効化すると、is_mfa_verified_by_user も False にリセット
        """
        # Owner（管理者）を作成
        admin = await create_random_staff(db_session, role="owner")
        await db_session.flush()  # IDを生成
        admin_token = create_access_token(subject=str(admin.id))

        # 対象スタッフを作成（MFA有効化済み）
        target_staff = await create_random_staff(db_session, is_mfa_enabled=True)
        target_staff.set_mfa_secret(generate_totp_secret())
        target_staff.is_mfa_verified_by_user = True
        await db_session.commit()

        # 管理者がMFA無効化
        response = await async_client.post(
            f"/api/v1/auth/admin/staff/{target_staff.id}/mfa/disable",
            headers={"Authorization": f"Bearer {admin_token}"},
        )

        assert response.status_code == 200

        # DBを確認
        await db_session.refresh(target_staff)
        assert target_staff.is_mfa_enabled is False
        assert target_staff.is_mfa_verified_by_user is False  # ← リセット


class TestAdminMFAReEnable:
    """管理者によるMFA再有効化のテスト"""

    @pytest.mark.asyncio
    async def test_admin_reenable_mfa_requires_first_setup_again(
        self, async_client: AsyncClient, db_session: AsyncSession
    ):
        """
        管理者がMFA無効化→再有効化すると、再度初回セットアップが必要
        """
        # Owner（管理者）を作成
        admin = await create_random_staff(db_session, role="owner")
        await db_session.flush()  # IDを生成
        admin_token = create_access_token(subject=str(admin.id))

        # 対象スタッフを作成
        password = "testpassword123"
        target_staff = await create_random_staff(db_session, is_mfa_enabled=True)
        target_staff.hashed_password = get_password_hash(password)
        target_staff.set_mfa_secret(generate_totp_secret())
        target_staff.is_mfa_verified_by_user = True
        await db_session.commit()

        # 1. 管理者がMFA無効化
        await async_client.post(
            f"/api/v1/auth/admin/staff/{target_staff.id}/mfa/disable",
            headers={"Authorization": f"Bearer {admin_token}"},
        )

        # 2. 管理者が再度MFA有効化
        enable_response = await async_client.post(
            f"/api/v1/auth/admin/staff/{target_staff.id}/mfa/enable",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert enable_response.status_code == 200

        # DBを確認
        await db_session.refresh(target_staff)
        assert target_staff.is_mfa_enabled is True
        assert target_staff.is_mfa_verified_by_user is False  # ← 再度False

        # 3. スタッフがログイン試行
        login_response = await async_client.post(
            "/api/v1/auth/token",
            data={"username": target_staff.email, "password": password},
        )

        assert login_response.status_code == 200
        login_data = login_response.json()

        # 初回セットアップが必要（新しいシークレットで再登録）
        assert login_data.get("requires_mfa_first_setup") is True
