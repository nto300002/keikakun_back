"""
スタッフ監査ログモデル

スタッフに対する操作（削除、作成、更新等）の監査証跡を記録
"""
import uuid
import datetime
from typing import Optional, TYPE_CHECKING
from sqlalchemy import func, String, DateTime, UUID, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import JSONB

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.staff import Staff


class StaffAuditLog(Base):
    """
    スタッフ監査ログ

    全てのスタッフ操作を記録:
    - deleted: スタッフ削除
    - created: スタッフ作成
    - updated: スタッフ更新
    - password_changed: パスワード変更
    - role_changed: ロール変更

    異常なアクセスパターンの検出とコンプライアンスに使用
    """
    __tablename__ = 'staff_audit_logs'

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid()
    )
    staff_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey('staffs.id', ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="対象スタッフID"
    )
    action: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
        comment="操作種別（deleted, created, updated等）"
    )
    performed_by: Mapped[uuid.UUID] = mapped_column(
        ForeignKey('staffs.id', ondelete="SET NULL"),
        nullable=False,
        index=True,
        comment="操作実行者のスタッフID"
    )
    ip_address: Mapped[Optional[str]] = mapped_column(
        String(45),  # IPv6対応
        nullable=True,
        comment="操作元のIPアドレス"
    )
    user_agent: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="操作元のUser-Agent"
    )
    details: Mapped[Optional[dict]] = mapped_column(
        JSONB,
        nullable=True,
        comment="操作の詳細情報（JSON形式）"
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
        comment="記録日時（UTC）"
    )

    # Relationships
    staff: Mapped["Staff"] = relationship(
        "Staff",
        foreign_keys=[staff_id],
        backref="audit_logs"
    )
    performed_by_staff: Mapped["Staff"] = relationship(
        "Staff",
        foreign_keys=[performed_by]
    )
