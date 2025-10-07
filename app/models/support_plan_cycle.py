import datetime
import uuid
from typing import List, Optional, TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    Text,
    func,
    Enum as SQLAlchemyEnum,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import SupportPlanStep, DeliverableType

if TYPE_CHECKING:
    from .welfare_recipient import WelfareRecipient
    from .staff import Staff


class SupportPlanCycle(Base):
    """個別支援計画の1サイクル（約6ヶ月）"""
    __tablename__ = 'support_plan_cycles'
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    welfare_recipient_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('welfare_recipients.id'))
    plan_cycle_start_date: Mapped[Optional[datetime.date]]
    final_plan_signed_date: Mapped[Optional[datetime.date]]
    next_renewal_deadline: Mapped[Optional[datetime.date]]
    is_latest_cycle: Mapped[bool] = mapped_column(Boolean, default=True)
    cycle_number: Mapped[int] = mapped_column(Integer, default=1)  # 1, 2, 3, ...
    monitoring_deadline: Mapped[Optional[int]] = mapped_column(Integer) # default = 7
    google_calendar_id: Mapped[Optional[str]] = mapped_column(Text)
    google_event_id: Mapped[Optional[str]] = mapped_column(Text)
    google_event_url: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    welfare_recipient: Mapped["WelfareRecipient"] = relationship(back_populates="support_plan_cycles")
    statuses: Mapped[List["SupportPlanStatus"]] = relationship(back_populates="plan_cycle", cascade="all, delete-orphan")
    deliverables: Mapped[List["PlanDeliverable"]] = relationship(back_populates="plan_cycle", cascade="all, delete-orphan")

class SupportPlanStatus(Base):
    """計画サイクル内の各ステップの進捗"""
    __tablename__ = 'support_plan_statuses'
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    plan_cycle_id: Mapped[int] = mapped_column(ForeignKey('support_plan_cycles.id'))
    step_type: Mapped[SupportPlanStep] = mapped_column(SQLAlchemyEnum(SupportPlanStep))
    is_latest_status: Mapped[bool] = mapped_column(Boolean, default=True)
    completed: Mapped[bool] = mapped_column(Boolean, default=False)
    completed_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(timezone=True))
    completed_by: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey('staffs.id'))
    due_date: Mapped[Optional[datetime.date]]
    notes: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    # Relationships
    plan_cycle: Mapped["SupportPlanCycle"] = relationship(back_populates="statuses")
    completed_by_staff: Mapped[Optional["Staff"]] = relationship(foreign_keys=[completed_by])


class PlanDeliverable(Base):
    """計画サイクルに関連する成果物"""
    __tablename__ = 'plan_deliverables'
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    plan_cycle_id: Mapped[int] = mapped_column(ForeignKey('support_plan_cycles.id'))
    deliverable_type: Mapped[DeliverableType] = mapped_column(SQLAlchemyEnum(DeliverableType))
    file_path: Mapped[str] = mapped_column(Text)
    original_filename: Mapped[str] = mapped_column(Text)
    uploaded_by: Mapped[uuid.UUID] = mapped_column(ForeignKey('staffs.id'))
    uploaded_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    plan_cycle: Mapped["SupportPlanCycle"] = relationship(back_populates="deliverables")
    uploaded_by_staff: Mapped["Staff"] = relationship(foreign_keys=[uploaded_by])