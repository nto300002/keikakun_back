import uuid
import datetime
from typing import Optional, TYPE_CHECKING

from sqlalchemy import func, DateTime, UUID, ForeignKey, Text, Enum as SQLAlchemyEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import StaffRole, RequestStatus

if TYPE_CHECKING:
    from .staff import Staff
    from .office import Office


class RoleChangeRequest(Base):
    """Role変更リクエスト"""
    __tablename__ = 'role_change_requests'

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid()
    )
    requester_staff_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey('staffs.id', ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    office_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey('offices.id', ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    from_role: Mapped[StaffRole] = mapped_column(
        SQLAlchemyEnum(StaffRole),
        nullable=False
    )
    requested_role: Mapped[StaffRole] = mapped_column(
        SQLAlchemyEnum(StaffRole),
        nullable=False
    )
    status: Mapped[RequestStatus] = mapped_column(
        SQLAlchemyEnum(RequestStatus),
        default=RequestStatus.pending,
        nullable=False,
        index=True
    )
    request_notes: Mapped[Optional[str]] = mapped_column(Text)
    reviewed_by_staff_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey('staffs.id', ondelete="SET NULL"),
        nullable=True
    )
    reviewed_at: Mapped[Optional[datetime.datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True
    )
    reviewer_notes: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now()
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now()
    )

    # Relationships
    requester: Mapped["Staff"] = relationship(
        "Staff",
        foreign_keys=[requester_staff_id]
    )
    reviewer: Mapped[Optional["Staff"]] = relationship(
        "Staff",
        foreign_keys=[reviewed_by_staff_id]
    )
    office: Mapped["Office"] = relationship(
        "Office",
        foreign_keys=[office_id]
    )
