import uuid
import datetime
from typing import Optional, List
from sqlalchemy import func, String, DateTime, UUID, ForeignKey, Boolean, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class MFABackupCode(Base):
    """MFAバックアップ/リカバリーコード"""
    __tablename__ = 'mfa_backup_codes'
    
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    staff_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('staffs.id', ondelete="CASCADE"), nullable=False)
    code_hash: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    is_used: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    used_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    staff: Mapped["Staff"] = relationship(back_populates="mfa_backup_codes")
    
    def mark_as_used(self) -> None:
        """バックアップコードを使用済みとしてマーク"""
        self.is_used = True
        self.used_at = datetime.datetime.now(datetime.timezone.utc)


class MFAAuditLog(Base):
    """MFA関連のアクションの監査ログ"""
    __tablename__ = 'mfa_audit_logs'
    
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    staff_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('staffs.id', ondelete="CASCADE"), nullable=False)
    action: Mapped[str] = mapped_column(String(50), nullable=False)  # 'enabled', 'disabled', 'login_success', 'login_failed', 'backup_used'
    ip_address: Mapped[Optional[str]] = mapped_column(String(45), nullable=True)  # IPv6対応
    user_agent: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    details: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    staff: Mapped["Staff"] = relationship(back_populates="mfa_audit_logs")