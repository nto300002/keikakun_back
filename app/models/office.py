import uuid
import datetime
from typing import List, Optional, TYPE_CHECKING

from sqlalchemy import func, String, DateTime, UUID, ForeignKey, Enum as SQLAlchemyEnum, Boolean, Text, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import OfficeType

if TYPE_CHECKING:
    from .staff import Staff
    from .welfare_recipient import OfficeWelfareRecipient
    from .calendar_account import OfficeCalendarAccount
    from .calendar_events import CalendarEvent, CalendarEventSeries
    from .support_plan_cycle import SupportPlanCycle, SupportPlanStatus
    from .billing import Billing

class Office(Base):
    """事業所"""
    __tablename__ = 'offices'

    # テーブル引数（インデックス定義）
    __table_args__ = (
        # システム事務所検索用の複合インデックス（name + is_deleted）
        # get_or_create_system_office のクエリを高速化
        Index('ix_offices_name_is_deleted', 'name', 'is_deleted'),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    name: Mapped[str] = mapped_column(String(255))
    is_group: Mapped[bool] = mapped_column(Boolean, default=False)
    type: Mapped[OfficeType] = mapped_column(SQLAlchemyEnum(OfficeType))

    # 事務所の連絡先情報
    address: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    phone_number: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey('staffs.id', ondelete="CASCADE"))
    last_modified_by: Mapped[uuid.UUID] = mapped_column(ForeignKey('staffs.id', ondelete="CASCADE"))
    deactivated_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    is_test_data: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True, comment="テストデータフラグ。Factory関数で生成されたデータはTrue")

    # 論理削除カラム（退会機能用）
    is_deleted: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
        index=True,
        comment="論理削除フラグ"
    )
    deleted_at: Mapped[Optional[datetime.datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="削除日時"
    )
    deleted_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey('staffs.id', ondelete="SET NULL"),
        nullable=True,
        comment="削除実行者のスタッフID"
    )

    # Office -> OfficeStaff (one-to-many)
    staff_associations: Mapped[List["OfficeStaff"]] = relationship(back_populates="office")

    # Office -> office_welfare_recipients (one-to-many)
    recipient_associations: Mapped[List["OfficeWelfareRecipient"]] = relationship(back_populates="office")

    # Office -> OfficeCalendarAccount (one-to-one)
    calendar_account: Mapped[Optional["OfficeCalendarAccount"]] = relationship(
        "OfficeCalendarAccount",
        back_populates="office",
        uselist=False,
        cascade="all, delete-orphan"
    )

    # Office -> Billing (one-to-one)
    billing: Mapped[Optional["Billing"]] = relationship(
        "Billing",
        back_populates="office",
        uselist=False,
        cascade="all, delete-orphan"
    )

    # Office -> CalendarEvent (one-to-many)
    calendar_events: Mapped[List["CalendarEvent"]] = relationship(
        "CalendarEvent",
        back_populates="office",
        cascade="all, delete-orphan"
    )

    # Office -> CalendarEventSeries (one-to-many)
    calendar_event_series: Mapped[List["CalendarEventSeries"]] = relationship(
        "CalendarEventSeries",
        back_populates="office",
        cascade="all, delete-orphan"
    )

    # Office -> SupportPlanCycle (one-to-many)
    support_plan_cycles: Mapped[List["SupportPlanCycle"]] = relationship(
        "SupportPlanCycle",
        back_populates="office",
        cascade="all, delete-orphan"
    )

    # Office -> SupportPlanStatus (one-to-many)
    support_plan_statuses: Mapped[List["SupportPlanStatus"]] = relationship(
        "SupportPlanStatus",
        back_populates="office",
        cascade="all, delete-orphan"
    )

class OfficeStaff(Base):
    """スタッフと事業所の中間テーブル"""
    __tablename__ = 'office_staffs'
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    staff_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('staffs.id', ondelete="CASCADE"))
    office_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('offices.id', ondelete="CASCADE"))
    is_primary: Mapped[bool] = mapped_column(Boolean, default=True) # メインの所属か
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    is_test_data: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)

    # OfficeStaff -> Staff (many-to-one)
    staff: Mapped["Staff"] = relationship(
        "Staff",
        back_populates="office_associations",
        foreign_keys=[staff_id]
    )
    # OfficeStaff -> Office (many-to-one)
    office: Mapped["Office"] = relationship(
        "Office",
        back_populates="staff_associations",
        foreign_keys=[office_id]
    )


class OfficeAuditLog(Base):
    """事務所情報変更の監査ログ"""
    __tablename__ = 'office_audit_logs'

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid()
    )
    office_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey('offices.id', ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    staff_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey('staffs.id', ondelete="SET NULL"),
        nullable=True,
        index=True
    )
    action_type: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="アクション種別: office_info_updated など"
    )
    details: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="変更内容の詳細（JSON形式）"
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        index=True
    )
    is_test_data: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
        index=True,
        comment="テストデータフラグ"
    )