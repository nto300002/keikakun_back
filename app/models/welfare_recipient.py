import datetime
import uuid
from typing import List, Optional, TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, String, text, func, Integer, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship, mapped_column, Mapped
from sqlalchemy.orm import relationship as orm_relationship
from sqlalchemy import Enum as SQLAlchemyEnum

from app.db.base import Base
from app.models.enums import (
    GenderType,
    FormOfResidence,
    MeansOfTransportation,
    LivelihoodProtection,
    ApplicationStatus,
    PhysicalDisabilityType,
    DisabilityCategory,
)

if TYPE_CHECKING:
    from .office import Office
    from .support_plan_cycle import SupportPlanCycle
    # from .assessment import AssessmentSheetDeliverable # NOTE: 未実装のためコメントアウト


class WelfareRecipient(Base):
    """受給者"""
    __tablename__ = "welfare_recipients"
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
    office_associations: Mapped[List["OfficeWelfareRecipient"]] = relationship(back_populates="welfare_recipient", cascade="all, delete-orphan")
    support_plan_cycles: Mapped[List["SupportPlanCycle"]] = relationship(back_populates="welfare_recipient", cascade="all, delete-orphan")
    detail: Mapped[Optional["ServiceRecipientDetail"]] = relationship(back_populates="welfare_recipient", cascade="all, delete-orphan")
    disability_status: Mapped[Optional["DisabilityStatus"]] = relationship(back_populates="welfare_recipient", cascade="all, delete-orphan")
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


class ServiceRecipientDetail(Base):
    """受給者の詳細情報 (基本情報)"""
    __tablename__ = 'service_recipient_details'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    welfare_recipient_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('welfare_recipients.id'), unique=True)
    address: Mapped[str] = mapped_column(Text)
    form_of_residence: Mapped[FormOfResidence] = mapped_column(SQLAlchemyEnum(FormOfResidence, name='form_of_residence'))
    form_of_residence_other_text: Mapped[Optional[str]] = mapped_column(Text)
    means_of_transportation: Mapped[MeansOfTransportation] = mapped_column(SQLAlchemyEnum(MeansOfTransportation, name='means_of_transportation'))
    means_of_transportation_other_text: Mapped[Optional[str]] = mapped_column(Text)
    tel: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    welfare_recipient: Mapped["WelfareRecipient"] = orm_relationship(back_populates="detail")
    emergency_contacts: Mapped[List["EmergencyContact"]] = orm_relationship(back_populates="service_recipient_detail", cascade="all, delete-orphan")


class EmergencyContact(Base):
    """緊急連絡先"""
    __tablename__ = 'emergency_contacts'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    service_recipient_detail_id: Mapped[int] = mapped_column(ForeignKey('service_recipient_details.id'))
    first_name: Mapped[str] = mapped_column(String(255))
    last_name: Mapped[str] = mapped_column(String(255))
    first_name_furigana: Mapped[str] = mapped_column(String(255))
    last_name_furigana: Mapped[str] = mapped_column(String(255))
    relationship: Mapped[str] = mapped_column(String(255))
    tel: Mapped[str] = mapped_column(Text)
    address: Mapped[Optional[str]] = mapped_column(Text)
    notes: Mapped[Optional[str]] = mapped_column(Text)
    priority: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # relationship 関数を orm_relationship として呼ぶ（名前衝突回避）
    service_recipient_detail: Mapped["ServiceRecipientDetail"] = orm_relationship(back_populates="emergency_contacts")


class DisabilityStatus(Base):
    """障害についての基本情報"""
    __tablename__ = 'disability_statuses'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    welfare_recipient_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('welfare_recipients.id'), unique=True)
    disability_or_disease_name: Mapped[str] = mapped_column(Text)
    livelihood_protection: Mapped[LivelihoodProtection] = mapped_column(SQLAlchemyEnum(LivelihoodProtection, name='livelihood_protection'))
    special_remarks: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    welfare_recipient: Mapped["WelfareRecipient"] = orm_relationship(back_populates="disability_status")
    details: Mapped[List["DisabilityDetail"]] = orm_relationship(back_populates="disability_status", cascade="all, delete-orphan")


class DisabilityDetail(Base):
    """個別の障害・手帳・年金の詳細"""
    __tablename__ = 'disability_details'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    disability_status_id: Mapped[int] = mapped_column(ForeignKey('disability_statuses.id'))
    category: Mapped[DisabilityCategory] = mapped_column(SQLAlchemyEnum(DisabilityCategory, name='disability_category'))
    grade_or_level: Mapped[Optional[str]] = mapped_column(Text)
    physical_disability_type: Mapped[Optional[PhysicalDisabilityType]] = mapped_column(SQLAlchemyEnum(PhysicalDisabilityType, name='physical_disability_type'))
    physical_disability_type_other_text: Mapped[Optional[str]] = mapped_column(Text)
    application_status: Mapped[ApplicationStatus] = mapped_column(SQLAlchemyEnum(ApplicationStatus, name='application_status'))
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    disability_status: Mapped["DisabilityStatus"] = orm_relationship(back_populates="details")
