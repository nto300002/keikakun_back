import uuid
import datetime
import os
from typing import Optional, TYPE_CHECKING
from datetime import date

from sqlalchemy import func, String, DateTime, UUID, ForeignKey, Boolean, Text, Integer, Date, Enum as SQLAlchemyEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from cryptography.fernet import Fernet

from app.db.base import Base
from app.models.enums import CalendarConnectionStatus, NotificationTiming

if TYPE_CHECKING:
    from .office import Office
    from .staff import Staff


class OfficeCalendarAccount(Base):
    """事業所カレンダーアカウント

    事業所とGoogleカレンダーの連携を管理するモデル
    - 1つの事業所につき1つのGoogleカレンダーアカウント
    - サービスアカウント方式での認証
    """
    __tablename__ = "office_calendar_accounts"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid()
    )

    # 事業所との1:1リレーション
    office_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("offices.id", ondelete="CASCADE"),
        unique=True,  # 1:1を保証
        nullable=False
    )

    # Googleカレンダー情報
    google_calendar_id: Mapped[Optional[str]] = mapped_column(
        String(255),
        unique=True
    )

    calendar_name: Mapped[Optional[str]] = mapped_column(String(255))

    calendar_url: Mapped[Optional[str]] = mapped_column(Text)

    # 認証情報（暗号化して保存）
    service_account_key: Mapped[Optional[str]] = mapped_column(Text)

    service_account_email: Mapped[Optional[str]] = mapped_column(String(255))

    # 連携状態管理
    connection_status: Mapped[CalendarConnectionStatus] = mapped_column(
        SQLAlchemyEnum(CalendarConnectionStatus),
        default=CalendarConnectionStatus.not_connected,
        nullable=False
    )

    last_sync_at: Mapped[Optional[datetime.datetime]] = mapped_column(
        DateTime(timezone=True)
    )

    last_error_message: Mapped[Optional[str]] = mapped_column(Text)

    # 設定情報
    auto_invite_staff: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False
    )

    default_reminder_minutes: Mapped[int] = mapped_column(
        Integer,
        default=1440,  # 24時間前
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
    office: Mapped["Office"] = relationship(
        "Office",
        back_populates="calendar_account"
    )

    def encrypt_service_account_key(self, key_data: Optional[str]) -> None:
        """サービスアカウントキーを暗号化して保存"""
        if not key_data:
            return

        encryption_key = os.getenv("CALENDAR_ENCRYPTION_KEY")
        if not encryption_key:
            raise ValueError("CALENDAR_ENCRYPTION_KEY environment variable is not set")

        fernet = Fernet(encryption_key.encode())
        encrypted_key = fernet.encrypt(key_data.encode())
        self.service_account_key = encrypted_key.decode()

    def decrypt_service_account_key(self) -> Optional[str]:
        """暗号化されたサービスアカウントキーを復号化"""
        if not self.service_account_key:
            return None

        encryption_key = os.getenv("CALENDAR_ENCRYPTION_KEY")
        if not encryption_key:
            raise ValueError("CALENDAR_ENCRYPTION_KEY environment variable is not set")

        fernet = Fernet(encryption_key.encode())
        decrypted_key = fernet.decrypt(self.service_account_key.encode())
        return decrypted_key.decode()


class StaffCalendarAccount(Base):
    """スタッフカレンダーアカウント

    スタッフ個人のカレンダー通知設定を管理するモデル
    - 1人のスタッフにつき1つのカレンダーアカウント設定
    - 個人の通知設定、タイミング設定を管理
    """
    __tablename__ = "staff_calendar_accounts"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid()
    )

    # スタッフとの1:1リレーション
    staff_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("staffs.id", ondelete="CASCADE"),
        unique=True,  # 1:1を保証
        nullable=False
    )

    # 通知設定
    calendar_notifications_enabled: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False
    )

    email_notifications_enabled: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False
    )

    in_app_notifications_enabled: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False
    )

    # 通知先情報
    notification_email: Mapped[Optional[str]] = mapped_column(String(255))

    # 通知タイミング設定
    notification_timing: Mapped[NotificationTiming] = mapped_column(
        SQLAlchemyEnum(NotificationTiming),
        default=NotificationTiming.standard,
        nullable=False
    )

    # カスタム通知設定（notification_timing=CUSTOMの場合）
    custom_reminder_days: Mapped[Optional[str]] = mapped_column(String(100))

    # 一時停止設定
    notifications_paused_until: Mapped[Optional[date]] = mapped_column(Date)

    pause_reason: Mapped[Optional[str]] = mapped_column(String(255))

    # Googleカレンダーアクセス設定
    has_calendar_access: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False
    )

    calendar_access_granted_at: Mapped[Optional[datetime.datetime]] = mapped_column(
        DateTime(timezone=True)
    )

    # 統計情報
    total_notifications_sent: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False
    )

    last_notification_sent_at: Mapped[Optional[datetime.datetime]] = mapped_column(
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

    # リレーションシップ
    staff: Mapped["Staff"] = relationship(
        "Staff",
        back_populates="calendar_account"
    )

    def get_notification_email(self) -> str:
        """通知先メールアドレスを取得（設定されていない場合はStaff.emailを返す）"""
        return self.notification_email or self.staff.email

    def get_reminder_days(self) -> list[int]:
        """リマインダー日数のリストを取得"""
        if self.notification_timing == NotificationTiming.early:
            return [30, 14, 7, 3, 1]
        elif self.notification_timing == NotificationTiming.standard:
            return [30, 7, 1]
        elif self.notification_timing == NotificationTiming.minimal:
            return [7, 1]
        elif self.notification_timing == NotificationTiming.custom and self.custom_reminder_days:
            return [int(day.strip()) for day in self.custom_reminder_days.split(',')]
        else:
            return [7, 1]  # デフォルト

    def is_notifications_paused(self) -> bool:
        """通知が一時停止中かどうかを判定"""
        if not self.notifications_paused_until:
            return False

        from datetime import date
        return date.today() <= self.notifications_paused_until

    def increment_notification_count(self) -> None:
        """通知カウントを増加"""
        self.total_notifications_sent += 1
        self.last_notification_sent_at = datetime.datetime.now(datetime.timezone.utc)
