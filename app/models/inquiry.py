"""
問い合わせ機能のモデル

InquiryDetail: 問い合わせ固有の情報（Message との 1:1 関連）
"""
import uuid
import datetime
from typing import Optional, TYPE_CHECKING
from sqlalchemy import (
    func, String, Text, DateTime, UUID, ForeignKey,
    Boolean, Enum as SQLAlchemyEnum, Index, JSON
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import InquiryStatus, InquiryPriority

if TYPE_CHECKING:
    from app.models.message import Message
    from app.models.staff import Staff


class InquiryDetail(Base):
    """
    問い合わせ詳細

    Messageテーブルと1:1で関連し、問い合わせ固有の情報を保持
    - sender_name, sender_email: 未ログインユーザーからの問い合わせに使用
    - status: 問い合わせの対応状態
    - priority: 優先度
    - assigned_staff_id: 担当者
    - admin_notes: 管理者メモ
    - delivery_log: メール送信履歴（JSON形式）
    """
    __tablename__ = 'inquiry_details'

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid()
    )
    message_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey('messages.id', ondelete="CASCADE"),
        nullable=False,
        unique=True,  # 1:1 関連
        index=True
    )
    sender_name: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True
    )
    sender_email: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
        index=True  # 送信者検索用
    )
    ip_address: Mapped[Optional[str]] = mapped_column(
        String(45),  # IPv6対応
        nullable=True
    )
    user_agent: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True
    )
    status: Mapped["InquiryStatus"] = mapped_column(
        SQLAlchemyEnum(InquiryStatus),
        default=InquiryStatus.new,
        nullable=False,
        index=True  # ステータスによるフィルタリング用
    )
    assigned_staff_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey('staffs.id', ondelete="SET NULL"),
        nullable=True,
        index=True  # 担当者によるフィルタリング用
    )
    priority: Mapped["InquiryPriority"] = mapped_column(
        SQLAlchemyEnum(InquiryPriority),
        default=InquiryPriority.normal,
        nullable=False,
        index=True  # 優先度によるフィルタリング用
    )
    admin_notes: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True
    )
    delivery_log: Mapped[Optional[dict]] = mapped_column(
        JSON,
        nullable=True
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True  # 作成日時によるソート用
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
        foreign_keys=[message_id],
        lazy="selectin"
    )
    assigned_staff: Mapped[Optional["Staff"]] = relationship(
        "Staff",
        foreign_keys=[assigned_staff_id],
        lazy="selectin"
    )

    # Indexes
    __table_args__ = (
        # 複合インデックス: ステータス×作成日時（一覧表示の最適化）
        Index('ix_inquiry_details_status_created', 'status', 'created_at'),
        # 複合インデックス: 担当者×ステータス（担当者別の未対応一覧）
        Index('ix_inquiry_details_assigned_status', 'assigned_staff_id', 'status'),
        # 複合インデックス: 優先度×ステータス（優先度別の対応状況）
        Index('ix_inquiry_details_priority_status', 'priority', 'status'),
    )
