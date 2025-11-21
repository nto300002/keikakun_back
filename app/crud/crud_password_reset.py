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
    expires_in_minutes: int = 30
) -> PasswordResetToken:
    """
    パスワードリセットトークンを作成

    Args:
        db: データベースセッション
        staff_id: スタッフID
        token: 生のトークン（UUID）
        expires_in_minutes: 有効期限（分）- Phase 1セキュリティレビューで30分推奨

    Returns:
        PasswordResetToken: 作成されたトークン
    """
    token_hash = hash_reset_token(token)
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=expires_in_minutes)

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


# ==========================================
# Option 2: Refresh Token Blacklist
# ==========================================

async def blacklist_refresh_token(
    db: AsyncSession,
    *,
    jti: str,
    staff_id: uuid.UUID,
    expires_at: datetime,
    reason: str = "password_changed"
) -> None:
    """
    リフレッシュトークンをブラックリストに追加

    Args:
        db: データベースセッション
        jti: JWT ID (トークン識別子)
        staff_id: スタッフID
        expires_at: トークンの有効期限
        reason: ブラックリスト化の理由
    """
    from app.models.staff import RefreshTokenBlacklist

    blacklist_entry = RefreshTokenBlacklist(
        jti=jti,
        staff_id=staff_id,
        expires_at=expires_at,
        reason=reason
    )
    db.add(blacklist_entry)


async def is_refresh_token_blacklisted(
    db: AsyncSession,
    *,
    jti: str
) -> bool:
    """
    リフレッシュトークンがブラックリスト化されているか確認

    Args:
        db: データベースセッション
        jti: JWT ID (トークン識別子)

    Returns:
        bool: ブラックリスト化されている場合True
    """
    from app.models.staff import RefreshTokenBlacklist

    stmt = select(RefreshTokenBlacklist).where(
        RefreshTokenBlacklist.jti == jti
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none() is not None


async def blacklist_all_user_refresh_tokens(
    db: AsyncSession,
    *,
    staff_id: uuid.UUID,
    reason: str = "password_changed"
) -> int:
    """
    ユーザーの全リフレッシュトークンをブラックリスト化

    注: 実際には、現在有効なトークンのJTIを取得する方法がないため、
    この関数は将来の実装のためのプレースホルダーです。
    実際の運用では、ログイン時にJTIをセッション管理テーブルに保存し、
    パスワード変更時にそれらをブラックリスト化する必要があります。

    現在の実装では、password_changed_atを使った Option 1 が主な防御策となります。

    Args:
        db: データベースセッション
        staff_id: スタッフID
        reason: ブラックリスト化の理由

    Returns:
        int: ブラックリスト化されたトークン数 (現在は常に0)
    """
    # 将来の実装: セッション管理テーブルから有効なトークンを取得してブラックリスト化
    # 現在はOption 1 (password_changed_at) が主な防御策
    return 0
