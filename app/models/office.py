import uuid
import datetime
from typing import List, Optional

from sqlalchemy import func, String, DateTime, UUID, ForeignKey, Enum as SQLAlchemyEnum, Boolean
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import OfficeType, BillingStatus

class Office(Base):
    """事業所"""
    __tablename__ = 'offices'
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    name: Mapped[str] = mapped_column(String(255))
    is_group: Mapped[bool] = mapped_column(Boolean, default=False)
    type: Mapped[OfficeType] = mapped_column(SQLAlchemyEnum(OfficeType))
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey('staffs.id', ondelete="CASCADE"))
    last_modified_by: Mapped[uuid.UUID] = mapped_column(ForeignKey('staffs.id', ondelete="CASCADE"))
    billing_status: Mapped[BillingStatus] = mapped_column(
        SQLAlchemyEnum(BillingStatus), default=BillingStatus.free, nullable=False
    )
    stripe_customer_id: Mapped[Optional[str]] = mapped_column(String(255), unique=True)
    stripe_subscription_id: Mapped[Optional[str]] = mapped_column(String(255), unique=True)
    deactivated_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Office -> OfficeStaff (one-to-many)
    staff_associations: Mapped[List["OfficeStaff"]] = relationship(back_populates="office")
    
    # Office -> office_welfare_recipients (one-to-many)
    # recipient_associations: Mapped[List["OfficeWelfareRecipient"]] = relationship(back_populates="office")

class OfficeStaff(Base):
    """スタッフと事業所の中間テーブル"""
    __tablename__ = 'office_staffs'
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    staff_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('staffs.id', ondelete="CASCADE"))
    office_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('offices.id', ondelete="CASCADE"))
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False) # メインの所属か
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # OfficeStaff -> Staff (many-to-one)
    staff: Mapped["Staff"] = relationship(back_populates="office_associations")
    # OfficeStaff -> Office (many-to-one)
    office: Mapped["Office"] = relationship(back_populates="staff_associations")
