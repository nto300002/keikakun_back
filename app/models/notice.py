import uuid
import datetime
from typing import Optional, TYPE_CHECKING

from sqlalchemy import func, String, DateTime, UUID, ForeignKey, Boolean, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from .staff import Staff
    from .office import Office


class Notice(Base):
    """通知（既存テーブルを使用）"""
    __tablename__ = 'notices'

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid()
    )
    recipient_staff_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey('staffs.id', ondelete="CASCADE"),
        nullable=False
    )
    office_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey('offices.id', ondelete="CASCADE"),
        nullable=False
    )
    type: Mapped[str] = mapped_column(
        String(50),
        nullable=False
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    content: Mapped[Optional[str]] = mapped_column(Text)
    link_url: Mapped[Optional[str]] = mapped_column(String(255))
    is_read: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now()
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now()
    )
    is_test_data: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)

    # Relationships
    recipient_staff: Mapped["Staff"] = relationship(
        "Staff",
        foreign_keys=[recipient_staff_id]
    )
    office: Mapped["Office"] = relationship(
        "Office",
        foreign_keys=[office_id]
    )

    @property
    def notice_type(self) -> str:
        """通知タイプへのエイリアス（後方互換性のため）"""
        return self.type

    @property
    def notice_title(self) -> str:
        """通知タイトルへのエイリアス（後方互換性のため）"""
        return self.title
