"""
パスワードリセットCRUD操作

Phase 4: TDD GREENフェーズ - CRUD実装
"""

import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, delete

from app.models.staff import PasswordResetToken, PasswordResetAuditLog
from app.core.security import hash_reset_token


async def create_token(
    db: AsyncSession,
    *,
    staff_id: uuid.UUID,
    token: str,
    expires_in_hours: int = 1
) -> PasswordResetToken:
    """
    パスワードリセットトークンを作成

    Args:
        db: データベースセッション
        staff_id: スタッフID
        token: 生のトークン（UUID）
        expires_in_hours: 有効期限（時間）

    Returns:
        PasswordResetToken: 作成されたトークン
    """
    token_hash = hash_reset_token(token)
    expires_at = datetime.now(timezone.utc) + timedelta(hours=expires_in_hours)

    db_token = PasswordResetToken(
        staff_id=staff_id,
        token_hash=token_hash,
        expires_at=expires_at,
        used=False
    )
    db.add(db_token)
    return db_token


async def get_valid_token(
    db: AsyncSession,
    *,
    token: str
) -> Optional[PasswordResetToken]:
    """
    有効なパスワードリセットトークンを取得

    Args:
        db: データベースセッション
        token: 生のトークン

    Returns:
        Optional[PasswordResetToken]: 有効なトークン、または None
    """
    token_hash = hash_reset_token(token)
    now = datetime.now(timezone.utc)

    stmt = select(PasswordResetToken).where(
        PasswordResetToken.token_hash == token_hash,
        PasswordResetToken.used == False,
        PasswordResetToken.expires_at > now
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def mark_as_used(
    db: AsyncSession,
    *,
    token_id: uuid.UUID
) -> Optional[PasswordResetToken]:
    """
    トークンを使用済みにマーク（楽観的ロック）

    Args:
        db: データベースセッション
        token_id: トークンID

    Returns:
        Optional[PasswordResetToken]: 更新されたトークン、または None（既に使用済みの場合）
    """
    now = datetime.now(timezone.utc)

    # 楽観的ロック: used=Falseの条件で更新
    stmt = (
        update(PasswordResetToken)
        .where(
            PasswordResetToken.id == token_id,
            PasswordResetToken.used == False
        )
        .values(used=True, used_at=now)
        .returning(PasswordResetToken)
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def invalidate_existing_tokens(
    db: AsyncSession,
    *,
    staff_id: uuid.UUID
) -> int:
    """
    スタッフの既存の未使用トークンを無効化

    Args:
        db: データベースセッション
        staff_id: スタッフID

    Returns:
        int: 無効化されたトークン数
    """
    now = datetime.now(timezone.utc)

    stmt = (
        update(PasswordResetToken)
        .where(
            PasswordResetToken.staff_id == staff_id,
            PasswordResetToken.used == False,
            PasswordResetToken.expires_at > now
        )
        .values(used=True, used_at=now)
    )
    result = await db.execute(stmt)
    return result.rowcount


async def delete_expired_tokens(
    db: AsyncSession
) -> int:
    """
    期限切れトークンを削除

    Args:
        db: データベースセッション

    Returns:
        int: 削除されたトークン数
    """
    now = datetime.now(timezone.utc)

    stmt = delete(PasswordResetToken).where(
        PasswordResetToken.expires_at <= now
    )
    result = await db.execute(stmt)
    return result.rowcount


async def create_audit_log(
    db: AsyncSession,
    *,
    staff_id: Optional[uuid.UUID] = None,
    action: str,
    email: Optional[str] = None,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
    success: bool = True,
    error_message: Optional[str] = None
) -> PasswordResetAuditLog:
    """
    パスワードリセット監査ログを作成

    Args:
        db: データベースセッション
        staff_id: スタッフID（存在しない場合はNone）
        action: アクション（requested, token_verified, completed, failed）
        email: メールアドレス
        ip_address: IPアドレス
        user_agent: ユーザーエージェント
        success: 成功/失敗
        error_message: エラーメッセージ

    Returns:
        PasswordResetAuditLog: 作成された監査ログ
    """
    audit_log = PasswordResetAuditLog(
        staff_id=staff_id,
        action=action,
        email=email,
        ip_address=ip_address,
        user_agent=user_agent,
        success=success,
        error_message=error_message
    )
    db.add(audit_log)
    return audit_log
