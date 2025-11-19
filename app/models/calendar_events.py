import uuid
import datetime
from typing import Optional, List, TYPE_CHECKING
from sqlalchemy import (
    func, String, DateTime, UUID, ForeignKey, Boolean, Text, Integer,
    Date, ARRAY, Enum as SQLAlchemyEnum, CheckConstraint, UniqueConstraint, Index
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import (
    CalendarEventType, CalendarSyncStatus,
    ReminderPatternType, EventInstanceStatus
)

if TYPE_CHECKING:
    from .office import Office
    from .welfare_recipient import WelfareRecipient
    from .support_plan_cycle import SupportPlanCycle, SupportPlanStatus


class CalendarEvent(Base):
    """カレンダーイベント（レガシー用の単発イベント管理）

    既存システムとの互換性維持のための単発イベント管理
    """
    __tablename__ = "calendar_events"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid()
    )

    # 関連情報
    office_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("offices.id", ondelete="CASCADE"),
        nullable=False
    )

    welfare_recipient_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("welfare_recipients.id", ondelete="CASCADE"),
        nullable=False
    )

    support_plan_cycle_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("support_plan_cycles.id", ondelete="CASCADE")
    )

    support_plan_status_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("support_plan_statuses.id", ondelete="CASCADE")
    )

    # イベント種別
    event_type: Mapped[CalendarEventType] = mapped_column(
        SQLAlchemyEnum(CalendarEventType),
        nullable=False
    )

    # Googleカレンダー情報
    google_calendar_id: Mapped[str] = mapped_column(
        String(255),
        nullable=False
    )

    google_event_id: Mapped[Optional[str]] = mapped_column(
        String(255),
        unique=True
    )

    google_event_url: Mapped[Optional[str]] = mapped_column(Text)

    # イベント詳細
    event_title: Mapped[str] = mapped_column(String(500), nullable=False)

    event_description: Mapped[Optional[str]] = mapped_column(Text)

    event_start_datetime: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False
    )

    event_end_datetime: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False
    )

    # 管理情報
    created_by_system: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False
    )

    sync_status: Mapped[CalendarSyncStatus] = mapped_column(
        SQLAlchemyEnum(CalendarSyncStatus),
        default=CalendarSyncStatus.pending,
        nullable=False
    )

    last_sync_at: Mapped[Optional[datetime.datetime]] = mapped_column(
        DateTime(timezone=True)
    )

    last_error_message: Mapped[Optional[str]] = mapped_column(Text)

    # タイムスタンプ
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

    # リレーションシップ
    office: Mapped["Office"] = relationship(back_populates="calendar_events")
    welfare_recipient: Mapped["WelfareRecipient"] = relationship(back_populates="calendar_events")
    support_plan_cycle: Mapped[Optional["SupportPlanCycle"]] = relationship(back_populates="calendar_events")
    support_plan_status: Mapped[Optional["SupportPlanStatus"]] = relationship(back_populates="calendar_events")

    # 制約
    __table_args__ = (
        CheckConstraint(
            """
            (support_plan_cycle_id IS NOT NULL AND support_plan_status_id IS NULL) OR
            (support_plan_cycle_id IS NULL AND support_plan_status_id IS NOT NULL)
            """,
            name="chk_calendar_events_ref_exclusive"
        ),
        Index("idx_calendar_events_office_id", "office_id"),
        Index("idx_calendar_events_welfare_recipient_id", "welfare_recipient_id"),
        Index("idx_calendar_events_cycle_id", "support_plan_cycle_id"),
        Index("idx_calendar_events_status_id", "support_plan_status_id"),
        Index("idx_calendar_events_event_type", "event_type"),
        Index("idx_calendar_events_sync_status", "sync_status"),
        Index("idx_calendar_events_google_event_id", "google_event_id"),
        Index("idx_calendar_events_event_datetime", "event_start_datetime"),
        # 重複防止用の複合ユニークインデックス
        # 同じcycle_id/status_idと event_typeの組み合わせでは1つのイベントのみ許可
        Index(
            "idx_calendar_events_cycle_type_unique",
            "support_plan_cycle_id", "event_type",
            unique=True,
            postgresql_where="support_plan_cycle_id IS NOT NULL AND (sync_status = 'pending' OR sync_status = 'synced')"
        ),
        Index(
            "idx_calendar_events_status_type_unique",
            "support_plan_status_id", "event_type",
            unique=True,
            postgresql_where="support_plan_status_id IS NOT NULL AND (sync_status = 'pending' OR sync_status = 'synced')"
        ),
    )


class NotificationPattern(Base):
    """通知パターンテンプレート管理

    通知パターンのテンプレート管理
    更新期限やモニタリング期限のデフォルトパターンを定義
    """
    __tablename__ = "notification_patterns"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid()
    )

    # パターン情報
    pattern_name: Mapped[str] = mapped_column(
        String(100),
        unique=True,
        nullable=False
    )

    pattern_description: Mapped[Optional[str]] = mapped_column(Text)

    event_type: Mapped[CalendarEventType] = mapped_column(
        SQLAlchemyEnum(CalendarEventType),
        nullable=False
    )

    # 通知日程（期限の何日前に通知するか）
    reminder_days_before: Mapped[List[int]] = mapped_column(
        ARRAY(Integer),
        nullable=False
    )

    # テンプレート
    title_template: Mapped[str] = mapped_column(
        String(500),
        nullable=False
    )

    description_template: Mapped[Optional[str]] = mapped_column(Text)

    # 設定
    is_system_default: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False
    )

    # タイムスタンプ
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now()
    )

    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now()
    )

    # リレーションシップ
    event_series: Mapped[List["CalendarEventSeries"]] = relationship(
        back_populates="notification_pattern",
        cascade="all, delete-orphan"
    )

    # インデックス
    __table_args__ = (
        Index("idx_notification_patterns_event_type", "event_type"),
        Index(
            "idx_notification_patterns_active",
            "is_active",
            postgresql_where="is_active = TRUE"
        ),
    )


class CalendarEventSeries(Base):
    """カレンダーイベントシリーズ管理

    1つの期限に対する通知シリーズを管理
    複数のインスタンスを持つマスター
    """
    __tablename__ = "calendar_event_series"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid()
    )

    # 関連情報
    office_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("offices.id", ondelete="CASCADE"),
        nullable=False
    )

    welfare_recipient_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("welfare_recipients.id", ondelete="CASCADE"),
        nullable=False
    )

    support_plan_cycle_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("support_plan_cycles.id", ondelete="CASCADE")
    )

    support_plan_status_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("support_plan_statuses.id", ondelete="CASCADE")
    )

    # シリーズ情報
    event_type: Mapped[CalendarEventType] = mapped_column(
        SQLAlchemyEnum(CalendarEventType),
        nullable=False
    )

    series_title: Mapped[str] = mapped_column(
        String(500),
        nullable=False
    )

    base_deadline_date: Mapped[datetime.date] = mapped_column(
        Date,
        nullable=False
    )

    # 繰り返しパターン
    pattern_type: Mapped[ReminderPatternType] = mapped_column(
        SQLAlchemyEnum(ReminderPatternType),
        default=ReminderPatternType.multiple_fixed,
        nullable=False
    )

    notification_pattern_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("notification_patterns.id", ondelete="SET NULL")
    )

    reminder_days_before: Mapped[List[int]] = mapped_column(
        ARRAY(Integer),
        nullable=False
    )

    google_rrule: Mapped[Optional[str]] = mapped_column(Text)

    # Google Calendar情報
    google_calendar_id: Mapped[str] = mapped_column(
        String(255),
        nullable=False
    )

    google_master_event_id: Mapped[Optional[str]] = mapped_column(String(255))

    # 状態管理
    series_status: Mapped[CalendarSyncStatus] = mapped_column(
        SQLAlchemyEnum(CalendarSyncStatus),
        default=CalendarSyncStatus.pending,
        nullable=False
    )

    total_instances: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False
    )

    completed_instances: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False
    )

    # タイムスタンプ
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

    # リレーションシップ
    office: Mapped["Office"] = relationship(back_populates="calendar_event_series")
    welfare_recipient: Mapped["WelfareRecipient"] = relationship(back_populates="calendar_event_series")
    support_plan_cycle: Mapped[Optional["SupportPlanCycle"]] = relationship(back_populates="calendar_event_series")
    support_plan_status: Mapped[Optional["SupportPlanStatus"]] = relationship(back_populates="calendar_event_series")
    notification_pattern: Mapped[Optional["NotificationPattern"]] = relationship(back_populates="event_series")
    instances: Mapped[List["CalendarEventInstance"]] = relationship(
        back_populates="event_series",
        cascade="all, delete-orphan"
    )

    # 制約
    __table_args__ = (
        CheckConstraint(
            """
            (support_plan_cycle_id IS NOT NULL AND support_plan_status_id IS NULL) OR
            (support_plan_cycle_id IS NULL AND support_plan_status_id IS NOT NULL)
            """,
            name="chk_calendar_event_series_ref_exclusive"
        ),
        Index("idx_calendar_event_series_office_id", "office_id"),
        Index("idx_calendar_event_series_welfare_recipient_id", "welfare_recipient_id"),
        Index("idx_calendar_event_series_cycle_id", "support_plan_cycle_id"),
        Index("idx_calendar_event_series_status_id", "support_plan_status_id"),
        Index("idx_calendar_event_series_event_type", "event_type"),
        Index("idx_calendar_event_series_deadline_date", "base_deadline_date"),
        Index("idx_calendar_event_series_status", "series_status"),
    )


class CalendarEventInstance(Base):
    """カレンダーイベントインスタンス管理

    シリーズ内の個別通知イベント
    Googleカレンダーの実際のイベントと1:1対応
    """
    __tablename__ = "calendar_event_instances"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid()
    )

    # 所属シリーズ
    event_series_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("calendar_event_series.id", ondelete="CASCADE"),
        nullable=False
    )

    # 個別イベント情報
    instance_title: Mapped[str] = mapped_column(
        String(500),
        nullable=False
    )

    instance_description: Mapped[Optional[str]] = mapped_column(Text)

    event_datetime: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False
    )

    days_before_deadline: Mapped[int] = mapped_column(
        Integer,
        nullable=False
    )

    # Google Calendar情報
    google_event_id: Mapped[Optional[str]] = mapped_column(
        String(255),
        unique=True
    )

    google_event_url: Mapped[Optional[str]] = mapped_column(Text)

    # 状態管理
    instance_status: Mapped[EventInstanceStatus] = mapped_column(
        SQLAlchemyEnum(EventInstanceStatus),
        default=EventInstanceStatus.pending,
        nullable=False
    )

    sync_status: Mapped[CalendarSyncStatus] = mapped_column(
        SQLAlchemyEnum(CalendarSyncStatus),
        default=CalendarSyncStatus.pending,
        nullable=False
    )

    last_sync_at: Mapped[Optional[datetime.datetime]] = mapped_column(
        DateTime(timezone=True)
    )

    last_error_message: Mapped[Optional[str]] = mapped_column(Text)

    # 通知設定
    reminder_sent: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False
    )

    reminder_sent_at: Mapped[Optional[datetime.datetime]] = mapped_column(
        DateTime(timezone=True)
    )

    # タイムスタンプ
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

    # リレーションシップ
    event_series: Mapped["CalendarEventSeries"] = relationship(back_populates="instances")

    # インデックス
    __table_args__ = (
        Index("idx_calendar_event_instances_series_id", "event_series_id"),
        Index("idx_calendar_event_instances_datetime", "event_datetime"),
        Index("idx_calendar_event_instances_status", "instance_status"),
        Index("idx_calendar_event_instances_sync_status", "sync_status"),
        Index("idx_calendar_event_instances_google_event_id", "google_event_id"),
        Index(
            "idx_calendar_event_instances_reminder_pending",
            "reminder_sent",
            postgresql_where="reminder_sent = FALSE"
        ),
    )
