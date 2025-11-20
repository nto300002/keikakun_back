"""
パスワードリセットモデルのテスト (Phase 2)

Phase 2: データベースフェーズ
- PasswordResetTokenモデルのテスト
- PasswordResetAuditLogモデルのテスト
"""

import pytest
import uuid
import hashlib
from datetime import datetime, timedelta, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError
from sqlalchemy import select

from app.models.staff import Staff, PasswordResetToken, PasswordResetAuditLog
from app.models.enums import StaffRole


@pytest.fixture
async def test_staff(db_session: AsyncSession):
    """テスト用のスタッフを作成"""
    staff = Staff(
        email="test@example.com",
        hashed_password="hashed_password",
        first_name="太郎",
        last_name="テスト",
        full_name="テスト 太郎",
        role=StaffRole.employee,
        is_test_data=True
    )
    db_session.add(staff)
    await db_session.commit()
    await db_session.refresh(staff)
    return staff


def hash_token(token: str) -> str:
    """トークンをSHA-256でハッシュ化"""
    return hashlib.sha256(token.encode()).hexdigest()


class TestPasswordResetTokenModel:
    """PasswordResetTokenモデルのテスト"""

    @pytest.mark.asyncio
    async def test_create_password_reset_token(self, db_session: AsyncSession, test_staff: Staff):
        """
        正常系: パスワードリセットトークンを作成できること
        """
        # Arrange
        token = str(uuid.uuid4())
        token_hash = hash_token(token)
        expires_at = datetime.now(timezone.utc) + timedelta(hours=1)

        # Act
        reset_token = PasswordResetToken(
            staff_id=test_staff.id,
            token_hash=token_hash,
            expires_at=expires_at,
            used=False
        )
        db_session.add(reset_token)
        await db_session.commit()
        await db_session.refresh(reset_token)

        # Assert
        assert reset_token.id is not None
        assert reset_token.staff_id == test_staff.id
        assert reset_token.token_hash == token_hash
        assert reset_token.expires_at == expires_at
        assert reset_token.used is False
        assert reset_token.used_at is None
        assert reset_token.created_at is not None
        assert reset_token.updated_at is not None

    @pytest.mark.asyncio
    async def test_token_hash_unique_constraint(self, db_session: AsyncSession, test_staff: Staff):
        """
        異常系: token_hashは一意であること（重複するとIntegrityError）
        """
        # Arrange
        token_hash = hash_token("duplicate-token")
        expires_at = datetime.now(timezone.utc) + timedelta(hours=1)

        # 最初のトークンを作成
        reset_token1 = PasswordResetToken(
            staff_id=test_staff.id,
            token_hash=token_hash,
            expires_at=expires_at
        )
        db_session.add(reset_token1)
        await db_session.commit()

        # Act & Assert: 同じtoken_hashで2つ目のトークンを作成しようとするとエラー
        reset_token2 = PasswordResetToken(
            staff_id=test_staff.id,
            token_hash=token_hash,  # 重複
            expires_at=expires_at
        )
        db_session.add(reset_token2)

        with pytest.raises(IntegrityError) as exc_info:
            await db_session.commit()

        assert "token_hash" in str(exc_info.value).lower() or "unique" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_token_hash_not_null_constraint(self, db_session: AsyncSession, test_staff: Staff):
        """
        異常系: token_hashがNULLの場合、IntegrityErrorが発生すること
        """
        # Arrange
        expires_at = datetime.now(timezone.utc) + timedelta(hours=1)

        reset_token = PasswordResetToken(
            staff_id=test_staff.id,
            token_hash=None,  # NULL
            expires_at=expires_at
        )
        db_session.add(reset_token)

        # Act & Assert
        with pytest.raises(IntegrityError) as exc_info:
            await db_session.commit()

        assert "token_hash" in str(exc_info.value).lower() or "null" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_staff_id_foreign_key_constraint(self, db_session: AsyncSession):
        """
        異常系: 存在しないstaff_idではトークンを作成できないこと
        """
        # Arrange
        invalid_staff_id = uuid.uuid4()  # 存在しないID
        token_hash = hash_token("test-token")
        expires_at = datetime.now(timezone.utc) + timedelta(hours=1)

        reset_token = PasswordResetToken(
            staff_id=invalid_staff_id,
            token_hash=token_hash,
            expires_at=expires_at
        )
        db_session.add(reset_token)

        # Act & Assert
        with pytest.raises(IntegrityError) as exc_info:
            await db_session.commit()

        error_message = str(exc_info.value).lower()
        assert "foreign key" in error_message or "staff_id" in error_message

    @pytest.mark.asyncio
    async def test_cascade_delete_on_staff_deletion(self, db_session: AsyncSession):
        """
        正常系: スタッフが削除されると、関連するトークンも削除されること（CASCADE）
        """
        # Arrange: スタッフとトークンを作成
        staff = Staff(
            email="delete_test@example.com",
            hashed_password="hashed_password",
            first_name="削除",
            last_name="テスト",
            full_name="テスト 削除",
            role=StaffRole.employee
        )
        db_session.add(staff)
        await db_session.commit()
        await db_session.refresh(staff)

        token_hash = hash_token("cascade-test-token")
        expires_at = datetime.now(timezone.utc) + timedelta(hours=1)
        reset_token = PasswordResetToken(
            staff_id=staff.id,
            token_hash=token_hash,
            expires_at=expires_at
        )
        db_session.add(reset_token)
        await db_session.commit()
        token_id = reset_token.id

        # Act: スタッフを削除
        await db_session.delete(staff)
        await db_session.commit()

        # Assert: トークンも削除されていること
        stmt = select(PasswordResetToken).where(PasswordResetToken.id == token_id)
        result = await db_session.execute(stmt)
        deleted_token = result.scalar_one_or_none()
        assert deleted_token is None

    @pytest.mark.asyncio
    async def test_token_used_flag_and_used_at(self, db_session: AsyncSession, test_staff: Staff):
        """
        正常系: トークン使用時にusedフラグとused_atが設定されること
        """
        # Arrange: トークンを作成
        token_hash = hash_token("used-token")
        expires_at = datetime.now(timezone.utc) + timedelta(hours=1)
        reset_token = PasswordResetToken(
            staff_id=test_staff.id,
            token_hash=token_hash,
            expires_at=expires_at,
            used=False
        )
        db_session.add(reset_token)
        await db_session.commit()
        await db_session.refresh(reset_token)

        # Act: トークンを使用済みにマーク
        reset_token.used = True
        reset_token.used_at = datetime.now(timezone.utc)
        await db_session.commit()
        await db_session.refresh(reset_token)

        # Assert
        assert reset_token.used is True
        assert reset_token.used_at is not None

    @pytest.mark.asyncio
    async def test_token_relationship_with_staff(self, db_session: AsyncSession, test_staff: Staff):
        """
        正常系: トークンからスタッフへのリレーションが機能すること
        """
        # Arrange & Act
        token_hash = hash_token("relationship-token")
        expires_at = datetime.now(timezone.utc) + timedelta(hours=1)
        reset_token = PasswordResetToken(
            staff_id=test_staff.id,
            token_hash=token_hash,
            expires_at=expires_at
        )
        db_session.add(reset_token)
        await db_session.commit()
        await db_session.refresh(reset_token)

        # リレーションを明示的にロード
        stmt = select(PasswordResetToken).where(PasswordResetToken.id == reset_token.id)
        result = await db_session.execute(stmt)
        loaded_token = result.scalar_one()

        # Assert
        assert loaded_token.staff_id == test_staff.id
        # リレーションシップを通じてスタッフにアクセス可能
        await db_session.refresh(loaded_token, ['staff'])
        assert loaded_token.staff.email == test_staff.email


class TestPasswordResetAuditLogModel:
    """PasswordResetAuditLogモデルのテスト"""

    @pytest.mark.asyncio
    async def test_create_audit_log(self, db_session: AsyncSession, test_staff: Staff):
        """
        正常系: パスワードリセット監査ログを作成できること
        """
        # Arrange & Act
        audit_log = PasswordResetAuditLog(
            staff_id=test_staff.id,
            action="requested",
            email=test_staff.email,
            ip_address="192.168.1.1",
            user_agent="Mozilla/5.0",
            success=True
        )
        db_session.add(audit_log)
        await db_session.commit()
        await db_session.refresh(audit_log)

        # Assert
        assert audit_log.id is not None
        assert audit_log.staff_id == test_staff.id
        assert audit_log.action == "requested"
        assert audit_log.email == test_staff.email
        assert audit_log.ip_address == "192.168.1.1"
        assert audit_log.user_agent == "Mozilla/5.0"
        assert audit_log.success is True
        assert audit_log.error_message is None
        assert audit_log.created_at is not None

    @pytest.mark.asyncio
    async def test_audit_log_action_not_null(self, db_session: AsyncSession, test_staff: Staff):
        """
        異常系: actionがNULLの場合、IntegrityErrorが発生すること
        """
        # Arrange
        audit_log = PasswordResetAuditLog(
            staff_id=test_staff.id,
            action=None,  # NULL
            email=test_staff.email
        )
        db_session.add(audit_log)

        # Act & Assert
        with pytest.raises(IntegrityError) as exc_info:
            await db_session.commit()

        assert "action" in str(exc_info.value).lower() or "null" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_audit_log_staff_id_can_be_null(self, db_session: AsyncSession):
        """
        正常系: staff_idはNULLでも作成可能であること（存在しないメールでのリクエスト時など）
        """
        # Arrange & Act
        audit_log = PasswordResetAuditLog(
            staff_id=None,  # NULL OK
            action="failed",
            email="nonexistent@example.com",
            ip_address="192.168.1.100",
            success=False,
            error_message="User not found"
        )
        db_session.add(audit_log)
        await db_session.commit()
        await db_session.refresh(audit_log)

        # Assert
        assert audit_log.staff_id is None
        assert audit_log.email == "nonexistent@example.com"
        assert audit_log.success is False
        assert audit_log.error_message == "User not found"

    @pytest.mark.asyncio
    async def test_audit_log_set_null_on_staff_deletion(self, db_session: AsyncSession):
        """
        正常系: スタッフが削除されると、監査ログのstaff_idがNULLになること（SET NULL）
        """
        # Arrange: スタッフと監査ログを作成
        staff = Staff(
            email="audit_delete_test@example.com",
            hashed_password="hashed_password",
            first_name="監査",
            last_name="テスト",
            full_name="テスト 監査",
            role=StaffRole.employee
        )
        db_session.add(staff)
        await db_session.commit()
        await db_session.refresh(staff)

        audit_log = PasswordResetAuditLog(
            staff_id=staff.id,
            action="completed",
            email=staff.email,
            success=True
        )
        db_session.add(audit_log)
        await db_session.commit()
        log_id = audit_log.id

        # Act: スタッフを削除
        await db_session.delete(staff)
        await db_session.commit()

        # Assert: 監査ログは残り、staff_idがNULLになっていること
        stmt = select(PasswordResetAuditLog).where(PasswordResetAuditLog.id == log_id)
        result = await db_session.execute(stmt)
        persisted_log = result.scalar_one_or_none()
        assert persisted_log is not None
        assert persisted_log.staff_id is None
        assert persisted_log.email == "audit_delete_test@example.com"

    @pytest.mark.asyncio
    async def test_audit_log_ipv6_address(self, db_session: AsyncSession, test_staff: Staff):
        """
        正常系: IPv6アドレスを記録できること（45文字まで対応）
        """
        # Arrange & Act
        ipv6_address = "2001:0db8:85a3:0000:0000:8a2e:0370:7334"
        audit_log = PasswordResetAuditLog(
            staff_id=test_staff.id,
            action="token_verified",
            email=test_staff.email,
            ip_address=ipv6_address,
            success=True
        )
        db_session.add(audit_log)
        await db_session.commit()
        await db_session.refresh(audit_log)

        # Assert
        assert audit_log.ip_address == ipv6_address

    @pytest.mark.asyncio
    async def test_audit_log_different_actions(self, db_session: AsyncSession, test_staff: Staff):
        """
        正常系: 異なるアクションタイプの監査ログを作成できること
        """
        actions = ["requested", "token_verified", "completed", "failed"]

        for action in actions:
            # Arrange & Act
            audit_log = PasswordResetAuditLog(
                staff_id=test_staff.id,
                action=action,
                email=test_staff.email,
                success=(action != "failed")
            )
            db_session.add(audit_log)

        await db_session.commit()

        # Assert: 全てのアクションが保存されていること
        stmt = select(PasswordResetAuditLog).where(
            PasswordResetAuditLog.staff_id == test_staff.id
        )
        result = await db_session.execute(stmt)
        logs = list(result.scalars().all())
        assert len(logs) == len(actions)
        assert {log.action for log in logs} == set(actions)

    @pytest.mark.asyncio
    async def test_audit_log_relationship_with_staff(self, db_session: AsyncSession, test_staff: Staff):
        """
        正常系: 監査ログからスタッフへのリレーションが機能すること
        """
        # Arrange & Act
        audit_log = PasswordResetAuditLog(
            staff_id=test_staff.id,
            action="requested",
            email=test_staff.email,
            success=True
        )
        db_session.add(audit_log)
        await db_session.commit()
        await db_session.refresh(audit_log)

        # リレーションを明示的にロード
        stmt = select(PasswordResetAuditLog).where(PasswordResetAuditLog.id == audit_log.id)
        result = await db_session.execute(stmt)
        loaded_log = result.scalar_one()

        # Assert
        assert loaded_log.staff_id == test_staff.id
        # リレーションシップを通じてスタッフにアクセス可能
        await db_session.refresh(loaded_log, ['staff'])
        assert loaded_log.staff.email == test_staff.email
