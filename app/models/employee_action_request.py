import uuid
import datetime
from typing import Optional, TYPE_CHECKING

from sqlalchemy import func, DateTime, UUID, ForeignKey, Text, Boolean, Enum as SQLAlchemyEnum
from sqlalchemy.dialects.postgresql import JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import RequestStatus, ActionType, ResourceType

if TYPE_CHECKING:
    from .staff import Staff
    from .office import Office


class EmployeeActionRequest(Base):
    """EmployeeのCRUD許可リクエスト"""
    __tablename__ = 'employee_action_requests'

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
    resource_type: Mapped[ResourceType] = mapped_column(
        SQLAlchemyEnum(ResourceType),
        nullable=False
    )
    action_type: Mapped[ActionType] = mapped_column(
        SQLAlchemyEnum(ActionType),
        nullable=False
    )
    resource_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        nullable=True  # createの場合はNone
    )
    request_data: Mapped[Optional[dict]] = mapped_column(
        JSON,  # 実行するデータ（Pydanticスキーマのdict）
        nullable=True
    )
    status: Mapped[RequestStatus] = mapped_column(
        SQLAlchemyEnum(RequestStatus),
        default=RequestStatus.pending,
        nullable=False,
        index=True
    )
    approved_by_staff_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey('staffs.id', ondelete="SET NULL"),
        nullable=True
    )
    approved_at: Mapped[Optional[datetime.datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True
    )
    approver_notes: Mapped[Optional[str]] = mapped_column(Text)
    execution_result: Mapped[Optional[dict]] = mapped_column(
        JSON,  # 実行結果（成功/失敗、エラーメッセージなど）
        nullable=True
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
    requester: Mapped["Staff"] = relationship(
        "Staff",
        foreign_keys=[requester_staff_id]
    )
    approver: Mapped[Optional["Staff"]] = relationship(
        "Staff",
        foreign_keys=[approved_by_staff_id]
    )
    office: Mapped["Office"] = relationship(
        "Office",
        foreign_keys=[office_id]
    )
