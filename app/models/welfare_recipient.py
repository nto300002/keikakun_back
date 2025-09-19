import datetime
import uuid
import uuid
from typing import List, TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, String, text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import Enum as SQLAlchemyEnum

from app.db.base import Base
from app.models.enums import GenderType

if TYPE_CHECKING:
    from .office import Office
    from .support_plan_cycle import SupportPlanCycle
    # from .assessment import AssessmentSheetDeliverable # NOTE: 未実装のためコメントアウト


class WelfareRecipient(Base):
    """受給者"""
    __tablename__ = 'welfare_recipients'
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    first_name: Mapped[str] = mapped_column(String(255))
    last_name: Mapped[str] = mapped_column(String(255))
    first_name_furigana: Mapped[str] = mapped_column(String(255))
    last_name_furigana: Mapped[str] = mapped_column(String(255))
    birth_day: Mapped[datetime.date]
    gender: Mapped[GenderType] = mapped_column(SQLAlchemyEnum(GenderType))
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    office_associations: Mapped[List["OfficeWelfareRecipient"]] = relationship(back_populates="welfare_recipient")
    support_plan_cycles: Mapped[List["SupportPlanCycle"]] = relationship(back_populates="welfare_recipient")
    # assessment_sheets: Mapped[List["AssessmentSheetDeliverable"]] = relationship(back_populates="welfare_recipient")


class OfficeWelfareRecipient(Base):
    """事業所と受給者の中間テーブル"""
    __tablename__ = 'office_welfare_recipients'
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    welfare_recipient_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('welfare_recipients.id'))
    office_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('offices.id'))
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    welfare_recipient: Mapped["WelfareRecipient"] = relationship(back_populates="office_associations")
    office: Mapped["Office"] = relationship(back_populates="recipient_associations")
