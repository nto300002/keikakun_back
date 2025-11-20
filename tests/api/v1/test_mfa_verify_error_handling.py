"""
MFA検証のエラーハンドリングテスト (TDD)

このテストは以下の問題を検証します:
1. get_mfa_secret() がValueErrorを発生させる場合のエラーハンドリング
2. トランザクション管理の正しさ
3. ユーザーフレンドリーなエラーメッセージの返却
"""

import pytest
from unittest.mock import patch, MagicMock
from fastapi import status
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token, generate_totp_secret, encrypt_mfa_secret
from tests.utils import create_random_staff, TEST_STAFF_PASSWORD


class TestMFAVerifyErrorHandling:
    """MFA検証のエラーハンドリングテスト"""

    @pytest.mark.asyncio
    async def test_verify_with_decryption_failure_returns_400(
        self, async_client: AsyncClient, db_session: AsyncSession
    ):
        """
        復号化失敗時に500エラーではなく400エラーを返すことを確認

        シナリオ:
        1. MFAシークレットが設定されているが、復号化に失敗する
        2. ValueError が発生
        3. サービス層でキャッチして False を返す
        4. エンドポイント層で 400 Bad Request を返す
        """
        # テスト用スタッフを作成
        staff = await create_random_staff(db_session, is_mfa_enabled=False)

        # 有効なシークレットを暗号化して設定
        mfa_secret = generate_totp_secret()
        staff.set_mfa_secret(mfa_secret)
        await db_session.commit()

        token = create_access_token(subject=str(staff.id))
        headers = {"Authorization": f"Bearer {token}"}

        # get_mfa_secret() が ValueError を発生させるようにモック
        with patch('app.models.staff.Staff.get_mfa_secret') as mock_get_secret:
            mock_get_secret.side_effect = ValueError("MFAシークレットの復号化に失敗しました")

            response = await async_client.post(
                "/api/v1/auth/mfa/verify",
                headers=headers,
                json={"totp_code": "123456"}
            )

        # 500エラーではなく400エラーを返すこと
        assert response.status_code == status.HTTP_400_BAD_REQUEST

        # ユーザーフレンドリーなエラーメッセージ
        detail = response.json()["detail"]
        assert "認証コード" in detail or "正しく" in detail or "無効" in detail

        # MFAが有効化されていないこと（ロールバックされている）
        await db_session.refresh(staff)
        assert staff.is_mfa_enabled is False

    @pytest.mark.asyncio
    async def test_verify_success_with_encrypted_secret(
        self, async_client: AsyncClient, db_session: AsyncSession
    ):
        """
        暗号化されたシークレットでMFA検証が成功することを確認

        シナリオ:
        1. MFAシークレットを暗号化して保存
        2. 復号化が成功
        3. TOTP検証が成功
        4. MFAが有効化される
        """
        # テスト用スタッフを作成
        staff = await create_random_staff(db_session, is_mfa_enabled=False)

        # 有効なシークレットを暗号化して設定
        mfa_secret = generate_totp_secret()
        staff.set_mfa_secret(mfa_secret)
        await db_session.commit()

        token = create_access_token(subject=str(staff.id))
        headers = {"Authorization": f"Bearer {token}"}

        # TOTP検証をモック（成功）
        with patch('app.services.mfa.verify_totp') as mock_verify:
            mock_verify.return_value = True

            response = await async_client.post(
                "/api/v1/auth/mfa/verify",
                headers=headers,
                json={"totp_code": "123456"}
            )

        # 成功すること
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["message"] == "多要素認証の検証に成功しました"

        # MFAが有効化されていること
        await db_session.refresh(staff)
        assert staff.is_mfa_enabled is True

    @pytest.mark.asyncio
    async def test_verify_already_enabled_returns_400(
        self, async_client: AsyncClient, db_session: AsyncSession
    ):
        """
        既にMFAが有効なユーザーが再検証しようとすると400エラーを返すことを確認

        シナリオ（ユーザーが報告した問題）:
        1. 初回検証でMFAが有効化される
        2. レスポンスがフロントエンドに届かない
        3. ユーザーが2回目のリクエストを送信
        4. 既に is_mfa_enabled = True なので 400 エラー
        """
        # MFA既に有効なスタッフを作成
        staff = await create_random_staff(db_session, is_mfa_enabled=True)
        mfa_secret = generate_totp_secret()
        staff.set_mfa_secret(mfa_secret)
        await db_session.commit()

        token = create_access_token(subject=str(staff.id))
        headers = {"Authorization": f"Bearer {token}"}

        response = await async_client.post(
            "/api/v1/auth/mfa/verify",
            headers=headers,
            json={"totp_code": "123456"}
        )

        # 400エラーを返すこと
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        detail = response.json()["detail"]
        assert "多要素認証" in detail and "有効" in detail

    @pytest.mark.asyncio
    async def test_verify_transaction_rollback_on_error(
        self, async_client: AsyncClient, db_session: AsyncSession
    ):
        """
        検証中にエラーが発生した場合、トランザクションがロールバックされることを確認

        シナリオ:
        1. TOTP検証は成功
        2. しかし、その後にエラーが発生
        3. is_mfa_enabled がロールバックされること
        """
        # テスト用スタッフを作成
        staff = await create_random_staff(db_session, is_mfa_enabled=False)
        mfa_secret = generate_totp_secret()
        staff.set_mfa_secret(mfa_secret)
        await db_session.commit()

        token = create_access_token(subject=str(staff.id))
        headers = {"Authorization": f"Bearer {token}"}

        # TOTP検証は成功するが、その後commit()でエラーが発生するようにモック
        with patch('app.services.mfa.verify_totp') as mock_verify:
            mock_verify.return_value = True

            with patch('sqlalchemy.ext.asyncio.AsyncSession.commit') as mock_commit:
                mock_commit.side_effect = Exception("Database error")

                # エラーが発生することを確認
                with pytest.raises(Exception):
                    await async_client.post(
                        "/api/v1/auth/mfa/verify",
                        headers=headers,
                        json={"totp_code": "123456"}
                    )

        # MFAが有効化されていないこと（ロールバックされている）
        await db_session.refresh(staff)
        assert staff.is_mfa_enabled is False


class TestMFAServiceVerify:
    """MfaService.verify() メソッドのユニットテスト"""

    @pytest.mark.asyncio
    async def test_verify_catches_value_error_from_get_mfa_secret(
        self, db_session: AsyncSession
    ):
        """
        get_mfa_secret() が ValueError を発生させた場合、
        verify() が False を返すことを確認
        """
        from app.services.mfa import MfaService

        # テスト用スタッフを作成
        staff = await create_random_staff(db_session, is_mfa_enabled=False)
        mfa_secret = generate_totp_secret()
        staff.set_mfa_secret(mfa_secret)
        await db_session.commit()

        # MfaService インスタンスを作成
        mfa_service = MfaService(db_session)

        # get_mfa_secret() が ValueError を発生させるようにモック
        with patch.object(staff, 'get_mfa_secret') as mock_get_secret:
            mock_get_secret.side_effect = ValueError("復号化失敗")

            # verify() を呼び出し
            result = await mfa_service.verify(user=staff, totp_code="123456")

        # False を返すこと（例外を発生させない）
        assert result is False

        # MFAが有効化されていないこと
        assert staff.is_mfa_enabled is False

    @pytest.mark.asyncio
    async def test_verify_logs_decryption_error(
        self, db_session: AsyncSession, caplog
    ):
        """
        復号化エラーが適切にログに記録されることを確認
        """
        import logging
        from app.services.mfa import MfaService

        # ログレベルを設定
        caplog.set_level(logging.ERROR)

        # テスト用スタッフを作成
        staff = await create_random_staff(db_session, is_mfa_enabled=False)
        mfa_secret = generate_totp_secret()
        staff.set_mfa_secret(mfa_secret)
        await db_session.commit()

        # MfaService インスタンスを作成
        mfa_service = MfaService(db_session)

        # get_mfa_secret() が ValueError を発生させるようにモック
        with patch.object(staff, 'get_mfa_secret') as mock_get_secret:
            mock_get_secret.side_effect = ValueError("復号化失敗")

            # verify() を呼び出し
            await mfa_service.verify(user=staff, totp_code="123456")

        # エラーログが記録されていること
        assert "MFA VERIFY" in caplog.text
        assert "Decryption failed" in caplog.text or "復号化" in caplog.text


class TestMFALoginVerifyErrorHandling:
    """ログイン時のMFA検証エラーハンドリングテスト（verify_mfa_for_login）"""

    @pytest.mark.asyncio
    async def test_verify_mfa_for_login_decryption_failure(
        self, async_client: AsyncClient, db_session: AsyncSession
    ):
        """
        タスク1-1: verify_mfa_for_login で復号化失敗時に500エラーとメッセージを返すことを確認

        問題:
        - `user.get_mfa_secret()` が ValueError を発生させた場合、例外がハンドルされていない
        - 復号化失敗時に適切なエラーレスポンスがない

        期待される動作:
        - 500 Internal Server Error を返す
        - ユーザーフレンドリーなエラーメッセージを返す
        """
        # Arrange: MFA有効なスタッフを作成
        staff = await create_random_staff(
            db_session, is_mfa_enabled=True, password=TEST_STAFF_PASSWORD
        )
        mfa_secret = generate_totp_secret()
        staff.set_mfa_secret(mfa_secret)
        staff.is_mfa_verified_by_user = True  # 通常のMFA検証フローを使用
        await db_session.commit()

        # 通常ログインして temporary_token を取得
        login_response = await async_client.post(
            "/api/v1/auth/token",
            data={"username": staff.email, "password": TEST_STAFF_PASSWORD}
        )
        assert login_response.status_code == status.HTTP_200_OK
        login_data = login_response.json()
        assert login_data["requires_mfa_verification"] is True
        temporary_token = login_data["temporary_token"]

        # get_mfa_secret() が ValueError を発生させるようにモック
        with patch('app.models.staff.Staff.get_mfa_secret') as mock_get_secret:
            mock_get_secret.side_effect = ValueError("MFAシークレットの復号化に失敗しました")

            # Act: MFA検証を試行
            response = await async_client.post(
                "/api/v1/auth/token/verify-mfa",
                json={
                    "temporary_token": temporary_token,
                    "totp_code": "123456"
                }
            )

        # Assert: 500エラーを返すこと
        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR

        # ユーザーフレンドリーなエラーメッセージ
        detail = response.json()["detail"]
        assert "MFA設定" in detail or "エラー" in detail or "管理者" in detail

    @pytest.mark.asyncio
    async def test_verify_mfa_for_login_decryption_success(
        self, async_client: AsyncClient, db_session: AsyncSession
    ):
        """
        タスク1-1: 正常な復号化とTOTP検証が成功することを確認

        期待される動作:
        - 復号化が成功
        - TOTP検証が成功
        - 200 OK とアクセストークンを返す
        """
        # Arrange: MFA有効なスタッフを作成
        staff = await create_random_staff(
            db_session, is_mfa_enabled=True, password=TEST_STAFF_PASSWORD
        )
        mfa_secret = generate_totp_secret()
        staff.set_mfa_secret(mfa_secret)
        staff.is_mfa_verified_by_user = True  # 通常のMFA検証フローを使用
        await db_session.commit()

        # 通常ログインして temporary_token を取得
        login_response = await async_client.post(
            "/api/v1/auth/token",
            data={"username": staff.email, "password": TEST_STAFF_PASSWORD}
        )
        assert login_response.status_code == status.HTTP_200_OK
        login_data = login_response.json()
        assert login_data["requires_mfa_verification"] is True
        temporary_token = login_data["temporary_token"]

        # TOTP検証をモック（成功）
        with patch('app.api.v1.endpoints.auths.verify_totp') as mock_verify:
            mock_verify.return_value = True

            # Act: MFA検証を試行
            response = await async_client.post(
                "/api/v1/auth/token/verify-mfa",
                json={
                    "temporary_token": temporary_token,
                    "totp_code": "123456"
                }
            )

        # Assert: 成功すること
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        # access_tokenはCookieに設定されるため、レスポンスボディには含まれない
        assert "refresh_token" in data
        assert data["token_type"] == "bearer"
        assert data["message"] == "多要素認証に成功しました"
        # Cookieにaccess_tokenが設定されていることを確認
        assert "access_token" in response.cookies

    @pytest.mark.asyncio
    async def test_verify_mfa_for_login_recovery_code_success(
        self, async_client: AsyncClient, db_session: AsyncSession
    ):
        """
        タスク1-2: リカバリーコードでのログイン検証が正しく動作することを確認

        期待される動作:
        - リカバリーコードがデータベースから検索される
        - 各ハッシュ化されたコードと照合される
        - マッチした場合、使用済みとしてマークされる
        - 200 OK とアクセストークンを返す
        """
        from app.models.mfa import MFABackupCode
        from app.core.security import hash_recovery_code, generate_recovery_codes

        # Arrange: MFA有効なスタッフとリカバリーコードを作成
        staff = await create_random_staff(
            db_session, is_mfa_enabled=True, password=TEST_STAFF_PASSWORD
        )
        mfa_secret = generate_totp_secret()
        staff.set_mfa_secret(mfa_secret)
        staff.is_mfa_verified_by_user = True

        # スタッフをコミットしてIDを取得
        await db_session.commit()
        await db_session.refresh(staff)

        # リカバリーコードを生成して保存
        recovery_codes = generate_recovery_codes(count=3)
        for code in recovery_codes:
            backup_code = MFABackupCode(
                staff_id=staff.id,
                code_hash=hash_recovery_code(code),
                is_used=False
            )
            db_session.add(backup_code)
        await db_session.commit()

        # 通常ログインして temporary_token を取得
        login_response = await async_client.post(
            "/api/v1/auth/token",
            data={"username": staff.email, "password": TEST_STAFF_PASSWORD}
        )
        assert login_response.status_code == status.HTTP_200_OK
        login_data = login_response.json()
        assert login_data["requires_mfa_verification"] is True
        temporary_token = login_data["temporary_token"]

        # Act: リカバリーコードでMFA検証を試行
        response = await async_client.post(
            "/api/v1/auth/token/verify-mfa",
            json={
                "temporary_token": temporary_token,
                "recovery_code": recovery_codes[0]  # 最初のコードを使用
            }
        )

        # Assert: 成功すること
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "refresh_token" in data
        assert data["token_type"] == "bearer"
        assert "access_token" in response.cookies

        # リカバリーコードが使用済みとしてマークされていることを確認
        await db_session.refresh(staff)
        from sqlalchemy import select
        stmt = select(MFABackupCode).where(
            MFABackupCode.staff_id == staff.id,
            MFABackupCode.is_used == True
        )
        result = await db_session.execute(stmt)
        used_codes = result.scalars().all()
        assert len(used_codes) == 1
