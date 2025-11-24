"""
メッセージ・お知らせ機能のモデル

Messages: メッセージ本体
MessageRecipients: 受信者ごとの状態管理（既読/未読など）
"""
import uuid
import datetime
from typing import List, Optional, TYPE_CHECKING
from sqlalchemy import (
    func, String, Text, DateTime, UUID, ForeignKey,
    Boolean, Enum as SQLAlchemyEnum, UniqueConstraint, Index
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import MessageType, MessagePriority

if TYPE_CHECKING:
    from app.models.staff import Staff
    from app.models.office import Office


class Message(Base):
    """
    メッセージ本体

    個別メッセージ、一斉通知、システム通知などを格納
    受信者ごとの状態はMessageRecipientで管理
    """
    __tablename__ = 'messages'

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid()
    )
    sender_staff_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey('staffs.id', ondelete="SET NULL"),
        nullable=True,  # スタッフ削除時にNULLに設定
        index=True
    )
    office_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey('offices.id', ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    message_type: Mapped[MessageType] = mapped_column(
        SQLAlchemyEnum(MessageType),
        default=MessageType.personal,
        nullable=False
    )
    priority: Mapped[MessagePriority] = mapped_column(
        SQLAlchemyEnum(MessagePriority),
        default=MessagePriority.normal,
        nullable=False
    )
    title: Mapped[str] = mapped_column(
        String(200),
        nullable=False
    )
    content: Mapped[str] = mapped_column(
        Text,
        nullable=False
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False
    )
    is_test_data: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
        index=True
    )

    # Relationships
    sender: Mapped[Optional["Staff"]] = relationship(
        "Staff",
        foreign_keys=[sender_staff_id],
        lazy="selectin"
    )
    office: Mapped["Office"] = relationship(
        "Office",
        foreign_keys=[office_id],
        lazy="selectin"
    )
    recipients: Mapped[List["MessageRecipient"]] = relationship(
        "MessageRecipient",
        back_populates="message",
        cascade="all, delete-orphan"
    )

    # Indexes
    __table_args__ = (
        Index('ix_messages_office_created', 'office_id', 'created_at'),
        Index('ix_messages_sender', 'sender_staff_id'),
    )


class MessageRecipient(Base):
    """
    メッセージ受信者（中間テーブル）

    受信者ごとの既読/未読状態、アーカイブ状態を管理
    1つのメッセージに複数の受信者が紐づく（1:N）
    """
    __tablename__ = 'message_recipients'

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid()
    )
    message_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey('messages.id', ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    recipient_staff_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey('staffs.id', ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    is_read: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False
    )
    read_at: Mapped[Optional[datetime.datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True
    )
    is_archived: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False
    )
    is_test_data: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
        index=True
    )

    # Relationships
    message: Mapped["Message"] = relationship(
        "Message",
        back_populates="recipients",
        lazy="selectin"
    )
    recipient_staff: Mapped["Staff"] = relationship(
        "Staff",
        foreign_keys=[recipient_staff_id],
        lazy="selectin"
    )

    # Constraints and Indexes
    __table_args__ = (
        # 同じメッセージに同じ受信者を複数回追加できない
        UniqueConstraint('message_id', 'recipient_staff_id', name='uq_message_recipient'),
        # 受信者の未読メッセージを効率的に取得
        Index('ix_message_recipients_recipient_read', 'recipient_staff_id', 'is_read'),
        # メッセージの受信者一覧を効率的に取得
        Index('ix_message_recipients_message', 'message_id'),
    )


class MessageAuditLog(Base):
    """
    メッセージ監査ログ

    メッセージに関する操作履歴を記録
    - 送信 (sent)
    - 既読 (read)
    - アーカイブ (archived)
    - 削除 (deleted)
    """
    __tablename__ = 'message_audit_logs'

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid()
    )
    staff_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey('staffs.id', ondelete="SET NULL"),
        nullable=True,  # 操作者削除時もログは保持
        index=True
    )
    message_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey('messages.id', ondelete="SET NULL"),
        nullable=True,  # メッセージ削除時もログは保持
        index=True
    )
    action: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True
    )
    ip_address: Mapped[Optional[str]] = mapped_column(
        String(45),  # IPv6対応
        nullable=True
    )
    user_agent: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True
    )
    success: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False
    )
    error_message: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True
    )
    is_test_data: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
        index=True
    )

    # Relationships
    staff: Mapped[Optional["Staff"]] = relationship(
        "Staff",
        foreign_keys=[staff_id],
        lazy="selectin"
    )
    message: Mapped[Optional["Message"]] = relationship(
        "Message",
        foreign_keys=[message_id],
        lazy="selectin"
    )

    # Indexes
    __table_args__ = (
        Index('ix_message_audit_staff', 'staff_id'),
        Index('ix_message_audit_message', 'message_id'),
        Index('ix_message_audit_action', 'action'),
        Index('ix_message_audit_created', 'created_at'),
    )
