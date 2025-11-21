"""
パスワードリセットセキュリティテスト (Phase 4)

TDD: REDフェーズ - セキュリティテストを先に作成
"""

import pytest
import uuid
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from unittest.mock import patch, AsyncMock, MagicMock

from app.models.staff import Staff, PasswordResetAuditLog
from app.crud import password_reset as crud_password_reset
from app.core.security import hash_reset_token, get_password_hash
from app.core.config import settings
from app.messages import ja


@pytest.fixture
async def test_staff(db_session: AsyncSession):
    """テスト用スタッフを作成"""
    staff = Staff(
        email="security_test@example.com",
        hashed_password=get_password_hash("TestP@ssw0rd123"),
        first_name="セキュリティ",
        last_name="テスト",
        full_name="テスト セキュリティ",
        role="employee",
        is_test_data=True
    )
    db_session.add(staff)
    await db_session.commit()
    await db_session.refresh(staff)
    return staff


class TestPasswordResetSecurity:
    """パスワードリセットのセキュリティテスト"""

    @pytest.mark.asyncio
    async def test_token_hash_uniqueness(self, db_session: AsyncSession, test_staff: Staff):
        """トークンハッシュの一意性"""
        token1 = str(uuid.uuid4())
        token2 = str(uuid.uuid4())

        hash1 = hash_reset_token(token1)
        hash2 = hash_reset_token(token2)

        # 異なるトークンは異なるハッシュ
        assert hash1 != hash2

        # 同じトークンは同じハッシュ
        hash1_duplicate = hash_reset_token(token1)
        assert hash1 == hash1_duplicate

    @pytest.mark.asyncio
    async def test_token_not_predictable(self):
        """トークンの予測不可能性（UUID v4）"""
        tokens = [str(uuid.uuid4()) for _ in range(100)]

        # 全てのトークンがユニーク
        assert len(tokens) == len(set(tokens))

    @pytest.mark.asyncio
    async def test_user_enumeration_prevention(
        self,
        async_client: AsyncClient,
        test_staff: Staff
    ):
        """ユーザー存在の推測防止"""
        # 存在するメールアドレス
        response1 = await async_client.post(
            f"{settings.API_V1_STR}/auth/forgot-password",
            json={"email": test_staff.email}
        )

        # 存在しないメールアドレス
        response2 = await async_client.post(
            f"{settings.API_V1_STR}/auth/forgot-password",
            json={"email": "nonexistent@example.com"}
        )

        # 両方とも同じレスポンス
        assert response1.status_code == response2.status_code == 200
        assert response1.json()["message"] == response2.json()["message"]

    @pytest.mark.asyncio
    async def test_audit_log_records_all_actions(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_staff: Staff
    ):
        """監査ログの記録確認"""
        # パスワードリセット要求
        await async_client.post(
            f"{settings.API_V1_STR}/auth/forgot-password",
            json={"email": test_staff.email}
        )

        # 監査ログを確認
        stmt = select(PasswordResetAuditLog).where(
            PasswordResetAuditLog.staff_id == test_staff.id
        )
        result = await db_session.execute(stmt)
        audit_logs = result.scalars().all()

        assert len(audit_logs) > 0
        assert any(log.action == 'requested' for log in audit_logs)

    @pytest.mark.asyncio
    async def test_sql_injection_prevention(
        self,
        async_client: AsyncClient
    ):
        """SQLインジェクション対策"""
        # SQLインジェクション試行
        malicious_email = "admin@example.com'; DROP TABLE staffs; --"

        response = await async_client.post(
            f"{settings.API_V1_STR}/auth/forgot-password",
            json={"email": malicious_email}
        )

        # バリデーションエラーまたは安全に処理される
        assert response.status_code in [200, 422]

    @pytest.mark.asyncio
    async def test_token_hash_length(self):
        """トークンハッシュ長の検証（SHA-256 = 64文字の16進数）"""
        token = str(uuid.uuid4())
        token_hash = hash_reset_token(token)

        # SHA-256ハッシュは64文字の16進数
        assert len(token_hash) == 64
        # 16進数文字のみ
        assert all(c in '0123456789abcdef' for c in token_hash)

    @pytest.mark.asyncio
    async def test_different_tokens_same_staff_different_hashes(
        self,
        db_session: AsyncSession,
        test_staff: Staff
    ):
        """同じスタッフに対する複数のトークンは異なるハッシュを持つ"""
        token1 = str(uuid.uuid4())
        token2 = str(uuid.uuid4())

        db_token1 = await crud_password_reset.create_token(
            db_session,
            staff_id=test_staff.id,
            token=token1,
        )
        db_token2 = await crud_password_reset.create_token(
            db_session,
            staff_id=test_staff.id,
            token=token2,
        )
        await db_session.commit()

        assert db_token1.token_hash != db_token2.token_hash

    @pytest.mark.asyncio
    async def test_audit_log_captures_ip_and_user_agent(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_staff: Staff
    ):
        """監査ログがIPアドレスとUser-Agentを記録すること"""
        # カスタムヘッダーでリクエスト
        response = await async_client.post(
            f"{settings.API_V1_STR}/auth/forgot-password",
            json={"email": test_staff.email},
            headers={"user-agent": "TestAgent/1.0"}
        )
        assert response.status_code == 200

        # 監査ログを確認
        stmt = select(PasswordResetAuditLog).where(
            PasswordResetAuditLog.staff_id == test_staff.id,
            PasswordResetAuditLog.action == 'requested'
        ).order_by(PasswordResetAuditLog.created_at.desc())
        result = await db_session.execute(stmt)
        audit_log = result.scalar_one_or_none()

        assert audit_log is not None
        assert audit_log.ip_address is not None
        assert audit_log.user_agent == "TestAgent/1.0"

    @pytest.mark.asyncio
    async def test_breached_password_rejected(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_staff: Staff
    ):
        """侵害されたパスワードが拒否されること（HIBP統合）"""
        # パスワードリセットトークンを作成
        token = str(uuid.uuid4())
        await crud_password_reset.create_token(
            db_session,
            staff_id=test_staff.id,
            token=token
        )
        await db_session.commit()

        # HIBP APIをモック（侵害されたパスワードとして検出）
        mock_response = MagicMock()
        mock_response.status_code = 200
        # パスワード "BreachedP@ss123" のSHA-1ハッシュの残り部分が存在すると仮定
        import hashlib
        breached_password = "BreachedP@ss123"
        sha1_hash = hashlib.sha1(breached_password.encode('utf-8')).hexdigest().upper()
        hash_suffix = sha1_hash[5:]
        mock_response.text = f"{hash_suffix}:100000\nOTHERHASH:50"

        with patch('httpx.AsyncClient') as mock_client:
            mock_instance = AsyncMock()
            mock_instance.get = AsyncMock(return_value=mock_response)
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=None)
            mock_client.return_value = mock_instance

            # パスワードリセットを試行
            response = await async_client.post(
                f"{settings.API_V1_STR}/auth/reset-password",
                json={
                    "token": token,
                    "new_password": breached_password
                }
            )

            # 侵害されたパスワードは拒否される
            assert response.status_code == 400
            assert ja.AUTH_PASSWORD_BREACHED in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_safe_password_accepted(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_staff: Staff
    ):
        """侵害されていないパスワードが受け入れられること（HIBP統合）"""
        # パスワードリセットトークンを作成
        token = str(uuid.uuid4())
        await crud_password_reset.create_token(
            db_session,
            staff_id=test_staff.id,
            token=token
        )
        await db_session.commit()

        # HIBP APIをモック（侵害されていないパスワードとして検出）
        mock_response = MagicMock()
        mock_response.status_code = 200
        # ハッシュが存在しない（侵害されていない）
        mock_response.text = "DIFFERENTHASH1:100\nDIFFERENTHASH2:50"

        with patch('httpx.AsyncClient') as mock_client:
            mock_instance = AsyncMock()
            mock_instance.get = AsyncMock(return_value=mock_response)
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=None)
            mock_client.return_value = mock_instance

            # パスワードリセットを試行
            safe_password = "V3ry$tr0ng&UniqueP@ss2024!"
            response = await async_client.post(
                f"{settings.API_V1_STR}/auth/reset-password",
                json={
                    "token": token,
                    "new_password": safe_password
                }
            )

            # 侵害されていないパスワードは受け入れられる
            assert response.status_code == 200
            assert ja.AUTH_PASSWORD_RESET_SUCCESS in response.json()["message"]

    @pytest.mark.asyncio
    async def test_hibp_api_failure_allows_password(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_staff: Staff
    ):
        """HIBP API障害時にフェイルセーフでパスワードが許可されること"""
        # パスワードリセットトークンを作成
        token = str(uuid.uuid4())
        await crud_password_reset.create_token(
            db_session,
            staff_id=test_staff.id,
            token=token
        )
        await db_session.commit()

        # HIBP APIをモック（タイムアウト）
        with patch('httpx.AsyncClient') as mock_client:
            mock_instance = AsyncMock()
            import httpx
            mock_instance.get = AsyncMock(side_effect=httpx.TimeoutException("Timeout"))
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=None)
            mock_client.return_value = mock_instance

            # パスワードリセットを試行
            response = await async_client.post(
                f"{settings.API_V1_STR}/auth/reset-password",
                json={
                    "token": token,
                    "new_password": "NewP@ssw0rd123!"
                }
            )

            # API障害時もフェイルセーフで許可される
            assert response.status_code == 200
            assert ja.AUTH_PASSWORD_RESET_SUCCESS in response.json()["message"]
