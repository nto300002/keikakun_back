"""
Web Push通知の購読情報モデル
"""
import uuid
import datetime
from typing import TYPE_CHECKING, Optional
from sqlalchemy import String, DateTime, UUID, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import func

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.staff import Staff


class PushSubscription(Base):
    """Web Push通知の購読情報（スタッフのデバイス登録）"""
    __tablename__ = 'push_subscriptions'

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid()
    )
    staff_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey('staffs.id', ondelete='CASCADE'),
        nullable=False,
        index=True
    )
    endpoint: Mapped[str] = mapped_column(
        Text,
        unique=True,
        nullable=False
    )
    p256dh_key: Mapped[str] = mapped_column(
        Text,
        nullable=False
    )
    auth_key: Mapped[str] = mapped_column(
        Text,
        nullable=False
    )
    user_agent: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True
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

    # Relationships
    staff: Mapped["Staff"] = relationship(
        "Staff",
        back_populates="push_subscriptions"
    )
