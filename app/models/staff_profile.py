"""スタッフプロフィール関連のモデル"""
import uuid
import datetime
from typing import Optional
from sqlalchemy import func, String, DateTime, UUID, ForeignKey, Text, Boolean
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import JSONB

from app.db.base import Base


class EmailChangeRequest(Base):
    """メールアドレス変更リクエスト"""
    __tablename__ = 'email_change_requests'

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    staff_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('staffs.id', ondelete='CASCADE'), nullable=False)
    old_email: Mapped[str] = mapped_column(String(255), nullable=False)
    new_email: Mapped[str] = mapped_column(String(255), nullable=False)
    verification_token: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False)  # pending, completed, expired
    expires_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class PasswordHistory(Base):
    """パスワード履歴（過去のパスワード再使用防止）"""
    __tablename__ = 'password_histories'

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    staff_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('staffs.id', ondelete='CASCADE'), nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    changed_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AuditLog(Base):
    """
    統合型監査ログ

    全ての監査対象操作を記録:
    - staff.*: スタッフ関連操作（削除、作成、更新、パスワード変更等）
    - office.*: 事務所関連操作（情報更新等）
    - withdrawal.*: 退会関連操作（リクエスト、承認、実行等）
    - profile.*: プロフィール変更（名前、メール等）
    """
    __tablename__ = 'audit_logs'

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    staff_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey('staffs.id', ondelete='CASCADE'),
        nullable=False,
        index=True,
        comment="操作実行者のスタッフID（旧: actor_id）"
    )
    actor_role: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True,
        comment="実行時のロール"
    )
    action: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        index=True,
        comment="アクション種別: staff.deleted, office.updated, withdrawal.approved 等"
    )
    target_type: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True,
        index=True,
        comment="対象リソースタイプ: staff, office, withdrawal_request 等"
    )
    target_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
        comment="対象リソースのID"
    )
    office_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey('offices.id', ondelete='SET NULL'),
        nullable=True,
        index=True,
        comment="事務所ID（横断検索用、app_adminはNULL可）"
    )
    # 旧カラム（後方互換性のため維持）
    old_value: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="旧値（後方互換用）")
    new_value: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="新値（後方互換用）")
    # 共通カラム
    ip_address: Mapped[Optional[str]] = mapped_column(String(45), nullable=True, comment="操作元IPアドレス（IPv6対応）")
    user_agent: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="操作元User-Agent")
    details: Mapped[Optional[dict]] = mapped_column(
        JSONB,
        nullable=True,
        comment="変更内容（old_values, new_values等のJSON形式）"
    )
    timestamp: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        index=True,
        comment="記録日時（UTC）"
    )
    is_test_data: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
        index=True,
        comment="テストデータフラグ"
    )
