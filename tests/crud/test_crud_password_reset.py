"""
パスワードリセットCRUDのテスト (Phase 4)

TDD: REDフェーズ - テストを先に作成
"""

import pytest
import uuid
from datetime import datetime, timedelta, timezone
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud import password_reset as crud_password_reset
from app.models.staff import Staff
from app.core.security import hash_reset_token


@pytest.fixture
async def test_staff(db_session: AsyncSession):
    """テスト用スタッフを作成"""
    staff = Staff(
        email="password_reset_test@example.com",
        hashed_password="hashed_password",
        first_name="リセット",
        last_name="テスト",
        full_name="テスト リセット",
        role="employee"
    )
    db_session.add(staff)
    await db_session.commit()
    await db_session.refresh(staff)
    return staff


class TestCRUDPasswordReset:
    """CRUDPasswordResetのユニットテスト"""

    @pytest.mark.asyncio
    async def test_create_token(self, db_session: AsyncSession, test_staff: Staff):
        """トークン作成"""
        token = str(uuid.uuid4())
        db_token = await crud_password_reset.create_token(
            db_session,
            staff_id=test_staff.id,
            token=token,
            expires_in_hours=1
        )
        await db_session.commit()

        assert db_token.staff_id == test_staff.id
        assert db_token.token_hash == hash_reset_token(token)
        assert db_token.used is False
        assert db_token.expires_at > datetime.now(timezone.utc)

    @pytest.mark.asyncio
    async def test_get_valid_token_success(self, db_session: AsyncSession, test_staff: Staff):
        """有効なトークンの取得（成功）"""
        token = str(uuid.uuid4())
        await crud_password_reset.create_token(
            db_session,
            staff_id=test_staff.id,
            token=token,
            expires_in_hours=1
        )
        await db_session.commit()

        # 有効なトークンを取得
        db_token = await crud_password_reset.get_valid_token(db_session, token=token)

        assert db_token is not None
        assert db_token.staff_id == test_staff.id
        assert db_token.used is False

    @pytest.mark.asyncio
    async def test_get_valid_token_expired(self, db_session: AsyncSession, test_staff: Staff):
        """期限切れトークンは取得できない"""
        from app.models.staff import PasswordResetToken

        token = str(uuid.uuid4())
        token_hash = hash_reset_token(token)

        # 期限切れトークンを作成
        expired_token = PasswordResetToken(
            staff_id=test_staff.id,
            token_hash=token_hash,
            expires_at=datetime.now(timezone.utc) - timedelta(hours=1),  # 1時間前に期限切れ
            used=False
        )
        db_session.add(expired_token)
        await db_session.commit()

        # 期限切れトークンは取得できない
        db_token = await crud_password_reset.get_valid_token(db_session, token=token)
        assert db_token is None

    @pytest.mark.asyncio
    async def test_get_valid_token_already_used(self, db_session: AsyncSession, test_staff: Staff):
        """使用済みトークンは取得できない"""
        from app.models.staff import PasswordResetToken

        token = str(uuid.uuid4())
        token_hash = hash_reset_token(token)

        # 使用済みトークンを作成
        used_token = PasswordResetToken(
            staff_id=test_staff.id,
            token_hash=token_hash,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
            used=True,
            used_at=datetime.now(timezone.utc)
        )
        db_session.add(used_token)
        await db_session.commit()

        # 使用済みトークンは取得できない
        db_token = await crud_password_reset.get_valid_token(db_session, token=token)
        assert db_token is None

    @pytest.mark.asyncio
    async def test_mark_as_used(self, db_session: AsyncSession, test_staff: Staff):
        """トークンを使用済みにマーク"""
        token = str(uuid.uuid4())
        db_token = await crud_password_reset.create_token(
            db_session,
            staff_id=test_staff.id,
            token=token,
            expires_in_hours=1
        )
        await db_session.commit()

        # トークンを使用済みにマーク
        marked_token = await crud_password_reset.mark_as_used(db_session, token_id=db_token.id)
        await db_session.commit()

        assert marked_token is not None
        assert marked_token.used is True
        assert marked_token.used_at is not None

    @pytest.mark.asyncio
    async def test_mark_as_used_race_condition(self, db_session: AsyncSession, test_staff: Staff):
        """楽観的ロック: 既に使用済みの場合はNoneを返す"""
        token = str(uuid.uuid4())
        db_token = await crud_password_reset.create_token(
            db_session,
            staff_id=test_staff.id,
            token=token,
            expires_in_hours=1
        )
        await db_session.commit()

        # 1回目: 成功
        marked_token1 = await crud_password_reset.mark_as_used(db_session, token_id=db_token.id)
        await db_session.commit()
        assert marked_token1 is not None

        # 2回目: 失敗（既に使用済み）
        marked_token2 = await crud_password_reset.mark_as_used(db_session, token_id=db_token.id)
        assert marked_token2 is None

    @pytest.mark.asyncio
    async def test_invalidate_existing_tokens(self, db_session: AsyncSession, test_staff: Staff):
        """既存の未使用トークンを無効化"""
        # 複数のトークンを作成
        token1 = str(uuid.uuid4())
        token2 = str(uuid.uuid4())

        await crud_password_reset.create_token(db_session, staff_id=test_staff.id, token=token1)
        await crud_password_reset.create_token(db_session, staff_id=test_staff.id, token=token2)
        await db_session.commit()

        # 既存トークンを無効化
        count = await crud_password_reset.invalidate_existing_tokens(db_session, staff_id=test_staff.id)
        await db_session.commit()

        assert count == 2  # 2つのトークンが無効化された

        # 無効化されたトークンは取得できない
        db_token1 = await crud_password_reset.get_valid_token(db_session, token=token1)
        db_token2 = await crud_password_reset.get_valid_token(db_session, token=token2)
        assert db_token1 is None
        assert db_token2 is None

    @pytest.mark.asyncio
    async def test_delete_expired_tokens(self, db_session: AsyncSession, test_staff: Staff):
        """期限切れトークンの削除"""
        from app.models.staff import PasswordResetToken

        # 期限切れトークンを作成
        token1 = str(uuid.uuid4())
        expired_token = PasswordResetToken(
            staff_id=test_staff.id,
            token_hash=hash_reset_token(token1),
            expires_at=datetime.now(timezone.utc) - timedelta(hours=1),
            used=False
        )
        db_session.add(expired_token)

        # 有効なトークンを作成
        token2 = str(uuid.uuid4())
        valid_token = await crud_password_reset.create_token(
            db_session,
            staff_id=test_staff.id,
            token=token2,
            expires_in_hours=1
        )
        await db_session.commit()

        # 期限切れトークンを削除
        count = await crud_password_reset.delete_expired_tokens(db_session)
        await db_session.commit()

        assert count == 1  # 1つのトークンが削除された

        # 有効なトークンはまだ存在する
        db_token = await crud_password_reset.get_valid_token(db_session, token=token2)
        assert db_token is not None

    @pytest.mark.asyncio
    async def test_create_audit_log(self, db_session: AsyncSession, test_staff: Staff):
        """監査ログの作成"""
        audit_log = await crud_password_reset.create_audit_log(
            db_session,
            staff_id=test_staff.id,
            action='requested',
            email=test_staff.email,
            ip_address='192.168.1.1',
            user_agent='Mozilla/5.0',
            success=True
        )
        await db_session.commit()

        assert audit_log.staff_id == test_staff.id
        assert audit_log.action == 'requested'
        assert audit_log.success is True
