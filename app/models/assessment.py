import datetime
import uuid
from typing import List, Optional, TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Text, func, Integer, Boolean
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship as orm_relationship, mapped_column, Mapped
from sqlalchemy import Enum as SQLAlchemyEnum

from app.db.base import Base
from app.models.enums import (
    Household,
    MedicalCareInsurance,
    AidingType,
    WorkConditions,
    WorkOutsideFacility,
)

if TYPE_CHECKING:
    from .welfare_recipient import WelfareRecipient
    from .staff import Staff


class FamilyOfServiceRecipients(Base):
    """家族構成"""
    __tablename__ = 'family_of_service_recipients'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    welfare_recipient_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey('welfare_recipients.id'))
    name: Mapped[str] = mapped_column(Text)
    relationship: Mapped[str] = mapped_column(Text)
    household: Mapped[Household] = mapped_column(SQLAlchemyEnum(Household))
    ones_health: Mapped[str] = mapped_column(Text)
    remarks: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    family_structure_chart: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # URL or path
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # 関係性: FamilyOfServiceRecipients -> WelfareRecipient (many-to-one)
    welfare_recipient: Mapped["WelfareRecipient"] = orm_relationship(back_populates="family_members")


class WelfareServicesUsed(Base):
    """過去のサービス利用歴"""
    __tablename__ = 'welfare_services_used'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    welfare_recipient_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey('welfare_recipients.id'))
    office_name: Mapped[str] = mapped_column(Text)
    starting_day: Mapped[datetime.date]
    amount_used: Mapped[str] = mapped_column(Text)
    service_name: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # 関係性: WelfareServicesUsed -> WelfareRecipient (many-to-one)
    welfare_recipient: Mapped["WelfareRecipient"] = orm_relationship(back_populates="service_history")


class MedicalMatters(Base):
    """医療に関する基本情報"""
    __tablename__ = 'medical_matters'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    welfare_recipient_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey('welfare_recipients.id'), unique=True)
    medical_care_insurance: Mapped[MedicalCareInsurance] = mapped_column(SQLAlchemyEnum(MedicalCareInsurance))
    medical_care_insurance_other_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    aiding: Mapped[AidingType] = mapped_column(SQLAlchemyEnum(AidingType))
    history_of_hospitalization_in_the_past_2_years: Mapped[bool] = mapped_column(Boolean)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # 関係性: MedicalMatters -> WelfareRecipient (one-to-oneの逆側)
    welfare_recipient: Mapped["WelfareRecipient"] = orm_relationship(back_populates="medical_matters")
    # 関係性: MedicalMatters -> HistoryOfHospitalVisits (one-to-many)
    hospital_visits: Mapped[List["HistoryOfHospitalVisits"]] = orm_relationship(back_populates="medical_matters", cascade="all, delete-orphan")


class HistoryOfHospitalVisits(Base):
    """通院歴"""
    __tablename__ = 'history_of_hospital_visits'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    medical_matters_id: Mapped[int] = mapped_column(ForeignKey('medical_matters.id'))
    disease: Mapped[str] = mapped_column(Text)
    frequency_of_hospital_visits: Mapped[str] = mapped_column(Text)
    symptoms: Mapped[str] = mapped_column(Text)
    medical_institution: Mapped[str] = mapped_column(Text)
    doctor: Mapped[str] = mapped_column(Text)
    tel: Mapped[str] = mapped_column(Text)
    taking_medicine: Mapped[bool] = mapped_column(Boolean)
    date_started: Mapped[Optional[datetime.date]] = mapped_column(nullable=True)
    date_ended: Mapped[Optional[datetime.date]] = mapped_column(nullable=True)
    special_remarks: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # 関係性: HistoryOfHospitalVisits -> MedicalMatters (many-to-one)
    medical_matters: Mapped["MedicalMatters"] = orm_relationship(back_populates="hospital_visits")


class EmploymentRelated(Base):
    """就労関係"""
    __tablename__ = 'employment_related'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    welfare_recipient_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey('welfare_recipients.id'), unique=True)
    created_by_staff_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey('staffs.id'))
    work_conditions: Mapped[WorkConditions] = mapped_column(SQLAlchemyEnum(WorkConditions))
    regular_or_part_time_job: Mapped[bool] = mapped_column(Boolean)
    employment_support: Mapped[bool] = mapped_column(Boolean)
    work_experience_in_the_past_year: Mapped[bool] = mapped_column(Boolean)
    suspension_of_work: Mapped[bool] = mapped_column(Boolean)
    qualifications: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    main_places_of_employment: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    general_employment_request: Mapped[bool] = mapped_column(Boolean)
    desired_job: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    special_remarks: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    work_outside_the_facility: Mapped[WorkOutsideFacility] = mapped_column(SQLAlchemyEnum(WorkOutsideFacility))
    special_note_about_working_outside_the_facility: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # 関係性
    welfare_recipient: Mapped["WelfareRecipient"] = orm_relationship(back_populates="employment_related")
    created_by_staff: Mapped["Staff"] = orm_relationship()


class IssueAnalysis(Base):
    """課題分析"""
    __tablename__ = 'issue_analyses'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    welfare_recipient_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey('welfare_recipients.id'), unique=True)
    created_by_staff_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey('staffs.id'))
    what_i_like_to_do: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    im_not_good_at: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    the_life_i_want: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    the_support_i_want: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    points_to_keep_in_mind_when_providing_support: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    future_dreams: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    other: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # 関係性
    welfare_recipient: Mapped["WelfareRecipient"] = orm_relationship(back_populates="issue_analysis")
    created_by_staff: Mapped["Staff"] = orm_relationship()
