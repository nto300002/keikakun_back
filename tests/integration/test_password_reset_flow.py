"""
パスワードリセットフロー統合テスト (Phase 4)

TDD: REDフェーズ - 統合テストを先に作成
"""

import pytest
import uuid
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime, timedelta, timezone

from app.core.config import settings
from app.models.staff import Staff, PasswordResetToken, PasswordResetAuditLog
from app.crud import password_reset as crud_password_reset
from app.core.security import get_password_hash, hash_reset_token, verify_password
from sqlalchemy import select


@pytest.fixture
async def test_staff(db_session: AsyncSession):
    """テスト用スタッフを作成"""
    staff = Staff(
        email="integration_test@example.com",
        hashed_password=get_password_hash("OldP@ssw0rd123"),
        first_name="統合",
        last_name="テスト",
        full_name="テスト 統合",
        role="employee",
        is_test_data=True
    )
    db_session.add(staff)
    await db_session.commit()
    await db_session.refresh(staff)
    return staff


class TestPasswordResetFlow:
    """パスワードリセットフロー全体のE2Eテスト"""

    @pytest.mark.asyncio
    async def test_complete_password_reset_flow(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_staff: Staff
    ):
        """
        正常系: パスワードリセットフロー全体

        1. パスワードリセット要求
        2. トークン取得（DBから）
        3. トークン検証
        4. パスワードリセット
        5. 新しいパスワードでログイン確認
        """
        # 1. パスワードリセット要求
        response = await async_client.post(
            f"{settings.API_V1_STR}/auth/forgot-password",
            json={"email": test_staff.email}
        )
        assert response.status_code == 200
        assert "パスワードリセット用のメールを送信しました" in response.json()["message"]

        # 2. トークンを取得（実際のテストではDBから直接取得）
        stmt = select(PasswordResetToken).where(
            PasswordResetToken.staff_id == test_staff.id,
            PasswordResetToken.used == False
        ).order_by(PasswordResetToken.created_at.desc())
        result = await db_session.execute(stmt)
        token_record = result.scalar_one()

        # 生のトークンを取得するため、全てのUUIDトークンを試す（テストのため）
        # 実際のアプリケーションでは、メールで送信されたトークンを使用
        raw_token = None
        for _ in range(1000):  # 実用的には、トークンを直接保存するか、モックする
            test_token = str(uuid.uuid4())
            if hash_reset_token(test_token) == token_record.token_hash:
                raw_token = test_token
                break

        # テストのため、トークンハッシュから逆算できないので、
        # 新しいトークンを作成して使用
        raw_token = str(uuid.uuid4())
        token_record.token_hash = hash_reset_token(raw_token)
        await db_session.commit()

        # 3. トークン検証
        response = await async_client.get(
            f"{settings.API_V1_STR}/auth/verify-reset-token",
            params={"token": raw_token}
        )
        assert response.status_code == 200
        assert response.json()["valid"] is True

        # 4. パスワードリセット
        new_password = "NewP@ssw0rd123"
        response = await async_client.post(
            f"{settings.API_V1_STR}/auth/reset-password",
            json={
                "token": raw_token,
                "new_password": new_password
            }
        )
        assert response.status_code == 200
        assert "パスワードが正常にリセットされました" in response.json()["message"]

        # 5. 新しいパスワードでログイン確認
        await db_session.refresh(test_staff)
        assert verify_password(new_password, test_staff.hashed_password)

        # トークンが使用済みになっていることを確認
        await db_session.refresh(token_record)
        assert token_record.used is True
        assert token_record.used_at is not None

    @pytest.mark.asyncio
    async def test_forgot_password_nonexistent_email(
        self,
        async_client: AsyncClient
    ):
        """存在しないメールアドレスでも成功レスポンス（セキュリティ）"""
        response = await async_client.post(
            f"{settings.API_V1_STR}/auth/forgot-password",
            json={"email": "nonexistent@example.com"}
        )
        assert response.status_code == 200
        assert "パスワードリセット用のメールを送信しました" in response.json()["message"]

    @pytest.mark.asyncio
    async def test_reset_password_expired_token(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_staff: Staff
    ):
        """期限切れトークンでリセット → エラー"""
        # 期限切れトークンを作成
        token = str(uuid.uuid4())
        expired_token = PasswordResetToken(
            staff_id=test_staff.id,
            token_hash=hash_reset_token(token),
            expires_at=datetime.now(timezone.utc) - timedelta(hours=1),
            used=False
        )
        db_session.add(expired_token)
        await db_session.commit()

        # パスワードリセット試行
        response = await async_client.post(
            f"{settings.API_V1_STR}/auth/reset-password",
            json={
                "token": token,
                "new_password": "NewP@ssw0rd123"
            }
        )
        assert response.status_code == 400
        assert "無効または期限切れ" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_reset_password_already_used_token(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_staff: Staff
    ):
        """使用済みトークンでリセット → エラー"""
        # トークンを作成
        token = str(uuid.uuid4())
        db_token = await crud_password_reset.create_token(
            db_session,
            staff_id=test_staff.id,
            token=token,
        )
        await db_session.commit()

        # 1回目: 成功
        response1 = await async_client.post(
            f"{settings.API_V1_STR}/auth/reset-password",
            json={
                "token": token,
                "new_password": "NewP@ssw0rd123"
            }
        )
        assert response1.status_code == 200

        # 2回目: 失敗（使用済み）
        response2 = await async_client.post(
            f"{settings.API_V1_STR}/auth/reset-password",
            json={
                "token": token,
                "new_password": "AnotherP@ssw0rd456"
            }
        )
        assert response2.status_code == 400
        assert "無効または期限切れ" in response2.json()["detail"]

    @pytest.mark.asyncio
    async def test_reset_password_weak_password(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_staff: Staff
    ):
        """パスワード要件を満たさない → バリデーションエラー"""
        token = str(uuid.uuid4())
        await crud_password_reset.create_token(
            db_session,
            staff_id=test_staff.id,
            token=token,
        )
        await db_session.commit()

        # 弱いパスワード
        response = await async_client.post(
            f"{settings.API_V1_STR}/auth/reset-password",
            json={
                "token": token,
                "new_password": "weak"
            }
        )
        assert response.status_code == 422  # バリデーションエラー

    @pytest.mark.asyncio
    async def test_verify_reset_token_invalid(
        self,
        async_client: AsyncClient
    ):
        """無効なトークンの検証"""
        invalid_token = str(uuid.uuid4())
        response = await async_client.get(
            f"{settings.API_V1_STR}/auth/verify-reset-token",
            params={"token": invalid_token}
        )
        assert response.status_code == 200
        assert response.json()["valid"] is False

    @pytest.mark.asyncio
    async def test_forgot_password_invalid_email_format(
        self,
        async_client: AsyncClient
    ):
        """無効なメール形式でバリデーションエラー"""
        response = await async_client.post(
            f"{settings.API_V1_STR}/auth/forgot-password",
            json={"email": "invalid-email"}
        )
        assert response.status_code == 422  # バリデーションエラー

    @pytest.mark.asyncio
    async def test_password_reset_creates_audit_log(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_staff: Staff
    ):
        """パスワードリセット要求で監査ログが作成されること"""
        # パスワードリセット要求
        response = await async_client.post(
            f"{settings.API_V1_STR}/auth/forgot-password",
            json={"email": test_staff.email}
        )
        assert response.status_code == 200

        # 監査ログを確認
        stmt = select(PasswordResetAuditLog).where(
            PasswordResetAuditLog.staff_id == test_staff.id,
            PasswordResetAuditLog.action == 'requested'
        )
        result = await db_session.execute(stmt)
        audit_log = result.scalar_one_or_none()

        assert audit_log is not None
        assert audit_log.email == test_staff.email
        assert audit_log.success is True
