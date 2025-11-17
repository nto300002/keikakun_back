from datetime import datetime, date
from typing import Optional
from pydantic import BaseModel, ConfigDict, EmailStr, field_validator, Field
import uuid

from app.models.enums import CalendarConnectionStatus, NotificationTiming
from app.messages import ja


# ==================== OfficeCalendarAccount Schemas ====================

class OfficeCalendarAccountBase(BaseModel):
    """事業所カレンダーアカウントのベーススキーマ"""
    google_calendar_id: Optional[str] = None
    calendar_name: Optional[str] = None
    calendar_url: Optional[str] = None
    service_account_email: Optional[str] = None
    connection_status: CalendarConnectionStatus = CalendarConnectionStatus.not_connected
    auto_invite_staff: bool = True
    default_reminder_minutes: int = Field(default=1440, ge=0, description="リマインダー分数（0以上）")


class OfficeCalendarAccountCreate(OfficeCalendarAccountBase):
    """事業所カレンダーアカウント作成用スキーマ"""
    office_id: uuid.UUID
    service_account_key: Optional[str] = None  # 暗号化前の生データ


class OfficeCalendarAccountUpdate(BaseModel):
    """事業所カレンダーアカウント更新用スキーマ"""
    google_calendar_id: Optional[str] = None
    calendar_name: Optional[str] = None
    calendar_url: Optional[str] = None
    service_account_email: Optional[str] = None
    service_account_key: Optional[str] = None
    connection_status: Optional[CalendarConnectionStatus] = None
    auto_invite_staff: Optional[bool] = None
    default_reminder_minutes: Optional[int] = Field(default=None, ge=0, description="リマインダー分数（0以上）")
    last_error_message: Optional[str] = None


class OfficeCalendarAccountResponse(OfficeCalendarAccountBase):
    """事業所カレンダーアカウントレスポンス用スキーマ"""
    id: uuid.UUID
    office_id: uuid.UUID
    last_sync_at: Optional[datetime] = None
    last_error_message: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class OfficeCalendarAccountInDB(OfficeCalendarAccountResponse):
    """DB内の事業所カレンダーアカウント（暗号化キー含む）"""
    service_account_key: Optional[str] = None  # 暗号化済みキー

    model_config = ConfigDict(from_attributes=True)


# ==================== StaffCalendarAccount Schemas ====================

class StaffCalendarAccountBase(BaseModel):
    """スタッフカレンダーアカウントのベーススキーマ"""
    calendar_notifications_enabled: bool = True
    email_notifications_enabled: bool = True
    in_app_notifications_enabled: bool = True
    notification_email: Optional[EmailStr] = None
    notification_timing: NotificationTiming = NotificationTiming.standard
    custom_reminder_days: Optional[str] = None

    @field_validator('custom_reminder_days')
    @classmethod
    def validate_custom_reminder_days(cls, v: Optional[str]) -> Optional[str]:
        """カスタムリマインダー日数のバリデーション"""
        if v is None:
            return v

        try:
            days = [int(day.strip()) for day in v.split(',')]
            if not all(day > 0 for day in days):
                raise ValueError(ja.VALIDATION_REMINDER_DAYS_POSITIVE)
            return v
        except ValueError:
            raise ValueError(ja.VALIDATION_CUSTOM_REMINDER_FORMAT)


class StaffCalendarAccountCreate(StaffCalendarAccountBase):
    """スタッフカレンダーアカウント作成用スキーマ"""
    staff_id: uuid.UUID


class StaffCalendarAccountUpdate(BaseModel):
    """スタッフカレンダーアカウント更新用スキーマ"""
    calendar_notifications_enabled: Optional[bool] = None
    email_notifications_enabled: Optional[bool] = None
    in_app_notifications_enabled: Optional[bool] = None
    notification_email: Optional[EmailStr] = None
    notification_timing: Optional[NotificationTiming] = None
    custom_reminder_days: Optional[str] = None
    notifications_paused_until: Optional[date] = None
    pause_reason: Optional[str] = None
    has_calendar_access: Optional[bool] = None

    @field_validator('custom_reminder_days')
    @classmethod
    def validate_custom_reminder_days(cls, v: Optional[str]) -> Optional[str]:
        """カスタムリマインダー日数のバリデーション"""
        if v is None:
            return v

        try:
            days = [int(day.strip()) for day in v.split(',')]
            if not all(day > 0 for day in days):
                raise ValueError(ja.VALIDATION_REMINDER_DAYS_POSITIVE)
            return v
        except ValueError:
            raise ValueError(ja.VALIDATION_CUSTOM_REMINDER_FORMAT)


class StaffCalendarAccountResponse(StaffCalendarAccountBase):
    """スタッフカレンダーアカウントレスポンス用スキーマ"""
    id: uuid.UUID
    staff_id: uuid.UUID
    notifications_paused_until: Optional[date] = None
    pause_reason: Optional[str] = None
    has_calendar_access: bool = False
    calendar_access_granted_at: Optional[datetime] = None
    total_notifications_sent: int = 0
    last_notification_sent_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class StaffCalendarAccountInDB(StaffCalendarAccountResponse):
    """DB内のスタッフカレンダーアカウント"""
    model_config = ConfigDict(from_attributes=True)


# ==================== Additional Helper Schemas ====================

class CalendarConnectionStatusUpdate(BaseModel):
    """カレンダー連携ステータス更新用スキーマ"""
    connection_status: CalendarConnectionStatus
    error_message: Optional[str] = None


class NotificationSettings(BaseModel):
    """通知設定取得用スキーマ"""
    calendar_enabled: bool
    email_enabled: bool
    in_app_enabled: bool
    notification_email: Optional[str] = None
    timing: NotificationTiming
    reminder_days: list[int]
    is_paused: bool
    paused_until: Optional[date] = None


# ==================== Calendar Setup Schemas ====================

class CalendarSetupRequest(BaseModel):
    """カレンダー連携設定リクエスト用スキーマ"""
    office_id: uuid.UUID
    google_calendar_id: str
    service_account_json: str  # JSON文字列（パース前）
    calendar_name: Optional[str] = None
    auto_invite_staff: bool = True
    default_reminder_minutes: int = Field(default=1440, ge=0, description="リマインダー分数（0以上）")

    @field_validator('service_account_json')
    @classmethod
    def validate_service_account_json(cls, v: str) -> str:
        """サービスアカウントJSONのバリデーション"""
        import json
        try:
            parsed = json.loads(v)
            # 必須フィールドの確認
            required_fields = ['type', 'project_id', 'private_key_id', 'private_key', 'client_email']
            for field in required_fields:
                if field not in parsed:
                    raise ValueError(ja.VALIDATION_MISSING_FIELD_IN_JSON.format(field=field))

            # typeがservice_accountであることを確認
            if parsed.get('type') != 'service_account':
                raise ValueError(ja.VALIDATION_INVALID_SERVICE_ACCOUNT_TYPE)

            return v
        except json.JSONDecodeError as e:
            raise ValueError(ja.VALIDATION_INVALID_JSON_FORMAT.format(error=str(e)))


class CalendarSetupResponse(BaseModel):
    """カレンダー連携設定レスポンス用スキーマ"""
    success: bool
    message: str
    account: Optional[OfficeCalendarAccountResponse] = None
    error_details: Optional[str] = None
