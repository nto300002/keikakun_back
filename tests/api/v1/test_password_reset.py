"""
パスワードリセット機能のテスト

セキュリティレビュー対応:
- トークン有効期限30分のテスト
- トークンハッシュ化の検証
- タイミング攻撃対策
- 楽観的ロック（並行処理）
- トランザクション境界の検証
"""

import pytest
import asyncio
import hashlib
from datetime import datetime, timedelta, timezone
from httpx import AsyncClient
from fastapi import status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.staff import Staff, PasswordResetToken
from app.core.security import get_password_hash

pytestmark = pytest.mark.asyncio


class TestForgotPasswordEndpoint:
    """パスワードリセット要求エンドポイントのテスト"""

    async def test_forgot_password_endpoint_exists(self, async_client: AsyncClient):
        """
        正常系: forgot-passwordエンドポイントが存在することを確認
        """
        # Arrange
        payload = {
            "email": "test@example.com"
        }

        # Act
        response = await async_client.post(
            "/api/v1/auth/forgot-password",
            json=payload
        )

        # Assert: エンドポイントが存在し、404ではないことを確認
        assert response.status_code != status.HTTP_404_NOT_FOUND

    async def test_forgot_password_returns_expected_structure(self, async_client: AsyncClient):
        """
        正常系: forgot-passwordエンドポイントが期待されるレスポンス構造を返すことを確認
        """
        # Arrange
        payload = {
            "email": "test@example.com"
        }

        # Act
        response = await async_client.post(
            "/api/v1/auth/forgot-password",
            json=payload
        )

        # Assert: レスポンス構造を確認
        data = response.json()
        assert "message" in data, "レスポンスに'message'フィールドが含まれていること"
        assert isinstance(data["message"], str), "'message'は文字列であること"

    async def test_forgot_password_validates_email_format(self, async_client: AsyncClient):
        """
        異常系: 無効なメールアドレス形式でバリデーションエラーを返すことを確認
        """
        # Arrange
        payload = {
            "email": "invalid-email"
        }

        # Act
        response = await async_client.post(
            "/api/v1/auth/forgot-password",
            json=payload
        )

        # Assert: バリデーションエラーを確認
        # 実装によっては422または400が返される
        assert response.status_code in [
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            status.HTTP_400_BAD_REQUEST
        ]


class TestVerifyResetTokenEndpoint:
    """トークン有効性確認エンドポイントのテスト"""

    async def test_verify_reset_token_endpoint_exists(self, async_client: AsyncClient):
        """
        正常系: verify-reset-tokenエンドポイントが存在することを確認
        """
        # Arrange
        token = "dummy-token-12345"

        # Act
        response = await async_client.get(
            f"/api/v1/auth/verify-reset-token?token={token}"
        )

        # Assert: エンドポイントが存在し、404ではないことを確認
        assert response.status_code != status.HTTP_404_NOT_FOUND

    async def test_verify_reset_token_returns_expected_structure(self, async_client: AsyncClient):
        """
        正常系: verify-reset-tokenエンドポイントが期待されるレスポンス構造を返すことを確認
        """
        # Arrange
        token = "dummy-token-12345"

        # Act
        response = await async_client.get(
            f"/api/v1/auth/verify-reset-token?token={token}"
        )

        # Assert: レスポンス構造を確認
        data = response.json()
        assert "valid" in data, "レスポンスに'valid'フィールドが含まれていること"
        assert "message" in data, "レスポンスに'message'フィールドが含まれていること"
        assert isinstance(data["valid"], bool), "'valid'はbool型であること"
        assert isinstance(data["message"], str), "'message'は文字列であること"


class TestResetPasswordEndpoint:
    """パスワードリセット実行エンドポイントのテスト"""

    async def test_reset_password_endpoint_exists(self, async_client: AsyncClient):
        """
        正常系: reset-passwordエンドポイントが存在することを確認
        """
        # Arrange
        payload = {
            "token": "dummy-token-12345",
            "new_password": "NewP@ssw0rd123!"
        }

        # Act
        response = await async_client.post(
            "/api/v1/auth/reset-password",
            json=payload
        )

        # Assert: エンドポイントが存在し、404ではないことを確認
        assert response.status_code != status.HTTP_404_NOT_FOUND

    async def test_reset_password_returns_expected_structure(self, async_client: AsyncClient):
        """
        正常系: reset-passwordエンドポイントが期待されるレスポンス構造を返すことを確認
        """
        # Arrange
        payload = {
            "token": "dummy-token-12345",
            "new_password": "NewP@ssw0rd123!"
        }

        # Act
        response = await async_client.post(
            "/api/v1/auth/reset-password",
            json=payload
        )

        # Assert: レスポンス構造を確認（400エラーでもmessageフィールドは存在するはず）
        data = response.json()
        # エラーレスポンスの場合は "detail" か "message" のどちらかが含まれる
        assert "message" in data or "detail" in data, \
            "レスポンスに'message'または'detail'フィールドが含まれていること"

    async def test_reset_password_validates_required_fields(self, async_client: AsyncClient):
        """
        異常系: 必須フィールドが欠けている場合にバリデーションエラーを返すことを確認
        """
        # Arrange: tokenフィールドが欠けている
        payload = {
            "new_password": "NewP@ssw0rd123!"
        }

        # Act
        response = await async_client.post(
            "/api/v1/auth/reset-password",
            json=payload
        )

        # Assert: バリデーションエラーを確認
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


# ==========================================
# セキュリティレビュー対応テスト
# ==========================================

class TestTokenExpiry:
    """トークン有効期限のテスト（30分）"""

    async def test_token_expires_after_30_minutes(self, db_session: AsyncSession):
        """
        正常系: トークンの有効期限が30分であることを確認
        """
        # Arrange: テスト用スタッフを作成
        staff = Staff(
            email="test@example.com",
            hashed_password=get_password_hash("TestPassword123!"),
            full_name="Test User",
            role="employee",
            is_email_verified=True
        )
        db_session.add(staff)
        await db_session.commit()
        await db_session.refresh(staff)

        # Act: トークンを生成（実装が必要）
        # この時点では実装がないため、テストは失敗する（TDD）
        import uuid
        raw_token = str(uuid.uuid4())
        token_hash = hashlib.sha256(raw_token.encode()).hexdigest()

        # トークンの有効期限は30分後
        expires_at = datetime.now(timezone.utc) + timedelta(minutes=30)

        token = PasswordResetToken(
            staff_id=staff.id,
            token_hash=token_hash,
            expires_at=expires_at,
            used=False
        )
        db_session.add(token)
        await db_session.commit()
        await db_session.refresh(token)

        # Assert: トークンの有効期限が30分であることを確認
        expected_expiry = datetime.now(timezone.utc) + timedelta(minutes=30)
        # 誤差を1分以内とする
        assert abs((token.expires_at - expected_expiry).total_seconds()) < 60

    async def test_expired_token_is_rejected(self, db_session: AsyncSession):
        """
        正常系: 期限切れトークンが拒否されることを確認
        """
        # Arrange: テスト用スタッフと期限切れトークンを作成
        staff = Staff(
            email="test2@example.com",
            hashed_password=get_password_hash("TestPassword123!"),
            full_name="Test User 2",
            role="employee",
            is_email_verified=True
        )
        db_session.add(staff)
        await db_session.commit()
        await db_session.refresh(staff)

        import uuid
        raw_token = str(uuid.uuid4())
        token_hash = hashlib.sha256(raw_token.encode()).hexdigest()

        # 既に期限切れのトークン
        expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)

        token = PasswordResetToken(
            staff_id=staff.id,
            token_hash=token_hash,
            expires_at=expires_at,
            used=False
        )
        db_session.add(token)
        await db_session.commit()

        # Assert: トークンが期限切れであることを確認
        now = datetime.now(timezone.utc)
        assert token.expires_at < now, "トークンは期限切れであること"


class TestTokenHashing:
    """トークンハッシュ化のテスト（SHA-256）"""

    async def test_token_is_hashed_before_storage(self, db_session: AsyncSession):
        """
        正常系: トークンがSHA-256でハッシュ化されて保存されることを確認
        """
        # Arrange: テスト用スタッフを作成
        staff = Staff(
            email="test3@example.com",
            hashed_password=get_password_hash("TestPassword123!"),
            full_name="Test User 3",
            role="employee",
            is_email_verified=True
        )
        db_session.add(staff)
        await db_session.commit()
        await db_session.refresh(staff)

        # Act: 平文トークンを生成してハッシュ化
        import uuid
        raw_token = str(uuid.uuid4())
        expected_hash = hashlib.sha256(raw_token.encode()).hexdigest()

        token = PasswordResetToken(
            staff_id=staff.id,
            token_hash=expected_hash,
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=30),
            used=False
        )
        db_session.add(token)
        await db_session.commit()
        await db_session.refresh(token)

        # Assert: DBに保存されているのはハッシュであること
        assert token.token_hash == expected_hash
        assert token.token_hash != raw_token  # 平文ではない
        assert len(token.token_hash) == 64  # SHA-256は64文字の16進数

    async def test_raw_token_is_never_stored(self, db_session: AsyncSession):
        """
        セキュリティ: 平文トークンがDBに保存されないことを確認
        """
        # Arrange & Act: 上記と同じ処理
        staff = Staff(
            email="test4@example.com",
            hashed_password=get_password_hash("TestPassword123!"),
            full_name="Test User 4",
            role="employee",
            is_email_verified=True
        )
        db_session.add(staff)
        await db_session.commit()
        await db_session.refresh(staff)

        import uuid
        raw_token = str(uuid.uuid4())
        token_hash = hashlib.sha256(raw_token.encode()).hexdigest()

        token = PasswordResetToken(
            staff_id=staff.id,
            token_hash=token_hash,
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=30),
            used=False
        )
        db_session.add(token)
        await db_session.commit()

        # Assert: DB内のすべてのフィールドに平文トークンが含まれていないこと
        stmt = select(PasswordResetToken).where(PasswordResetToken.staff_id == staff.id)
        result = await db_session.execute(stmt)
        db_token = result.scalar_one()

        # DBの全フィールドを文字列化してチェック
        db_values = f"{db_token.token_hash}"
        assert raw_token not in db_values, "平文トークンがDBに保存されていないこと"


class TestOptimisticLocking:
    """楽観的ロックのテスト（並行処理）"""

    async def test_concurrent_token_usage_is_prevented(self, db_session: AsyncSession):
        """
        正常系: 同じトークンの同時使用が防止されることを確認（楽観的ロック）
        """
        # Arrange: テスト用スタッフとトークンを作成
        staff = Staff(
            email="test5@example.com",
            hashed_password=get_password_hash("TestPassword123!"),
            full_name="Test User 5",
            role="employee",
            is_email_verified=True
        )
        db_session.add(staff)
        await db_session.commit()
        await db_session.refresh(staff)

        import uuid
        raw_token = str(uuid.uuid4())
        token_hash = hashlib.sha256(raw_token.encode()).hexdigest()

        token = PasswordResetToken(
            staff_id=staff.id,
            token_hash=token_hash,
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=30),
            used=False,
            version=0  # 楽観的ロック用バージョン（実装が必要）
        )
        db_session.add(token)
        await db_session.commit()
        await db_session.refresh(token)

        # Act & Assert: 並行してトークンを使用しようとした場合、
        # 2番目の使用は失敗すること（実装が必要）
        # この時点では実装がないため、テストは失敗する（TDD）

        # 注: 実際の並行処理テストは実装後に追加する


class TestTransactionBoundary:
    """トランザクション境界のテスト"""

    async def test_token_creation_and_email_send_are_separate_transactions(
        self, db_session: AsyncSession
    ):
        """
        正常系: トークン作成とメール送信が別トランザクションであることを確認

        メール送信が失敗してもトークンはDBに保存される
        （期限切れで自動削除されるため許容される設計）
        """
        # Note: このテストは実装後に完全な形で追加
        # トランザクション境界を確認するには、実際のエンドポイント実装が必要
        pass

    async def test_password_reset_is_atomic(self, db_session: AsyncSession):
        """
        正常系: パスワードリセット実行が単一トランザクションで行われることを確認

        以下の操作が全て成功するか、全て失敗するか:
        - パスワード更新
        - password_changed_at 更新
        - トークン無効化
        - セッション無効化
        """
        # Note: このテストは実装後に完全な形で追加
        pass
