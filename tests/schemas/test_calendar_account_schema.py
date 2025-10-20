import pytest
from pydantic import ValidationError
from datetime import datetime
import uuid

from app.schemas.calendar_account import (
    OfficeCalendarAccountCreate,
    OfficeCalendarAccountUpdate,
    OfficeCalendarAccountResponse,
    StaffCalendarAccountCreate,
    StaffCalendarAccountUpdate,
    StaffCalendarAccountResponse,
)
from app.models.enums import CalendarConnectionStatus, NotificationTiming


class TestOfficeCalendarAccountSchema:
    """OfficeCalendarAccountスキーマのテスト"""

    def test_office_calendar_account_create_valid(self):
        """正常なデータでOfficeCalendarAccountCreateモデルが作成できることをテスト"""
        valid_data = {
            "office_id": str(uuid.uuid4()),
            "google_calendar_id": "calendar@group.calendar.google.com",
            "calendar_name": "テスト事業所カレンダー",
            "calendar_url": "https://calendar.google.com/calendar/u/0?cid=xxx",
            "service_account_email": "service@project.iam.gserviceaccount.com",
            "auto_invite_staff": True,
            "default_reminder_minutes": 1440,
        }
        account = OfficeCalendarAccountCreate(**valid_data)
        assert account.google_calendar_id == "calendar@group.calendar.google.com"
        assert account.calendar_name == "テスト事業所カレンダー"
        assert account.auto_invite_staff is True
        assert account.default_reminder_minutes == 1440

    def test_office_calendar_account_create_minimal(self):
        """最小限の必須フィールドでOfficeCalendarAccountCreateモデルが作成できることをテスト"""
        minimal_data = {
            "office_id": str(uuid.uuid4()),
        }
        account = OfficeCalendarAccountCreate(**minimal_data)
        assert account.google_calendar_id is None
        assert account.calendar_name is None
        assert account.auto_invite_staff is True  # デフォルト値
        assert account.default_reminder_minutes == 1440  # デフォルト値

    def test_office_calendar_account_create_negative_reminder(self):
        """負のリマインダー分数でValidationErrorが発生することをテスト"""
        invalid_data = {
            "office_id": str(uuid.uuid4()),
            "default_reminder_minutes": -10,
        }
        with pytest.raises(ValidationError) as exc_info:
            OfficeCalendarAccountCreate(**invalid_data)
        errors = exc_info.value.errors()
        assert any(error["loc"] == ("default_reminder_minutes",) for error in errors)

    def test_office_calendar_account_update_valid(self):
        """正常なデータでOfficeCalendarAccountUpdateモデルが作成できることをテスト"""
        update_data = {
            "calendar_name": "更新されたカレンダー名",
            "connection_status": CalendarConnectionStatus.connected,
            "auto_invite_staff": False,
        }
        account_update = OfficeCalendarAccountUpdate(**update_data)
        assert account_update.calendar_name == "更新されたカレンダー名"
        assert account_update.connection_status == CalendarConnectionStatus.connected
        assert account_update.auto_invite_staff is False

    def test_office_calendar_account_update_partial(self):
        """部分的な更新データでOfficeCalendarAccountUpdateモデルが作成できることをテスト"""
        update_data = {
            "last_error_message": "認証エラーが発生しました",
        }
        account_update = OfficeCalendarAccountUpdate(**update_data)
        assert account_update.last_error_message == "認証エラーが発生しました"
        assert account_update.calendar_name is None

    def test_office_calendar_account_response_valid(self):
        """正常なデータでOfficeCalendarAccountResponseモデルが作成できることをテスト"""
        response_data = {
            "id": str(uuid.uuid4()),
            "office_id": str(uuid.uuid4()),
            "google_calendar_id": "calendar@group.calendar.google.com",
            "calendar_name": "テストカレンダー",
            "calendar_url": "https://calendar.google.com/calendar/u/0?cid=xxx",
            "service_account_email": "service@project.iam.gserviceaccount.com",
            "connection_status": CalendarConnectionStatus.connected,
            "last_sync_at": datetime.now(),
            "last_error_message": None,
            "auto_invite_staff": True,
            "default_reminder_minutes": 1440,
            "created_at": datetime.now(),
            "updated_at": datetime.now(),
        }
        account_response = OfficeCalendarAccountResponse(**response_data)
        assert account_response.id == uuid.UUID(response_data["id"])
        assert account_response.google_calendar_id == "calendar@group.calendar.google.com"
        assert account_response.connection_status == CalendarConnectionStatus.connected

    def test_office_calendar_account_response_from_attributes(self):
        """from_attributes=Trueが設定されていることをテスト"""
        assert OfficeCalendarAccountResponse.model_config.get("from_attributes") is True


class TestStaffCalendarAccountSchema:
    """StaffCalendarAccountスキーマのテスト"""

    def test_staff_calendar_account_create_valid(self):
        """正常なデータでStaffCalendarAccountCreateモデルが作成できることをテスト"""
        valid_data = {
            "staff_id": str(uuid.uuid4()),
            "calendar_notifications_enabled": True,
            "email_notifications_enabled": True,
            "in_app_notifications_enabled": True,
            "notification_email": "custom@example.com",
            "notification_timing": NotificationTiming.standard,
        }
        account = StaffCalendarAccountCreate(**valid_data)
        assert account.calendar_notifications_enabled is True
        assert account.notification_email == "custom@example.com"
        assert account.notification_timing == NotificationTiming.standard

    def test_staff_calendar_account_create_minimal(self):
        """最小限の必須フィールドでStaffCalendarAccountCreateモデルが作成できることをテスト"""
        minimal_data = {
            "staff_id": str(uuid.uuid4()),
        }
        account = StaffCalendarAccountCreate(**minimal_data)
        assert account.calendar_notifications_enabled is True  # デフォルト値
        assert account.email_notifications_enabled is True  # デフォルト値
        assert account.in_app_notifications_enabled is True  # デフォルト値
        assert account.notification_timing == NotificationTiming.standard  # デフォルト値

    def test_staff_calendar_account_create_custom_timing(self):
        """カスタム通知タイミングでStaffCalendarAccountCreateモデルが作成できることをテスト"""
        valid_data = {
            "staff_id": str(uuid.uuid4()),
            "notification_timing": NotificationTiming.custom,
            "custom_reminder_days": "60,30,14,7,3,1",
        }
        account = StaffCalendarAccountCreate(**valid_data)
        assert account.notification_timing == NotificationTiming.custom
        assert account.custom_reminder_days == "60,30,14,7,3,1"

    def test_staff_calendar_account_update_valid(self):
        """正常なデータでStaffCalendarAccountUpdateモデルが作成できることをテスト"""
        update_data = {
            "calendar_notifications_enabled": False,
            "notification_timing": NotificationTiming.early,
        }
        account_update = StaffCalendarAccountUpdate(**update_data)
        assert account_update.calendar_notifications_enabled is False
        assert account_update.notification_timing == NotificationTiming.early

    def test_staff_calendar_account_update_partial(self):
        """部分的な更新データでStaffCalendarAccountUpdateモデルが作成できることをテスト"""
        update_data = {
            "notification_email": "updated@example.com",
        }
        account_update = StaffCalendarAccountUpdate(**update_data)
        assert account_update.notification_email == "updated@example.com"
        assert account_update.calendar_notifications_enabled is None

    def test_staff_calendar_account_update_pause_notifications(self):
        """通知一時停止設定でStaffCalendarAccountUpdateモデルが作成できることをテスト"""
        from datetime import date, timedelta
        future_date = date.today() + timedelta(days=7)

        update_data = {
            "notifications_paused_until": future_date,
            "pause_reason": "休暇中",
        }
        account_update = StaffCalendarAccountUpdate(**update_data)
        assert account_update.notifications_paused_until == future_date
        assert account_update.pause_reason == "休暇中"

    def test_staff_calendar_account_response_valid(self):
        """正常なデータでStaffCalendarAccountResponseモデルが作成できることをテスト"""
        response_data = {
            "id": str(uuid.uuid4()),
            "staff_id": str(uuid.uuid4()),
            "calendar_notifications_enabled": True,
            "email_notifications_enabled": True,
            "in_app_notifications_enabled": True,
            "notification_email": "test@example.com",
            "notification_timing": NotificationTiming.standard,
            "custom_reminder_days": None,
            "notifications_paused_until": None,
            "pause_reason": None,
            "has_calendar_access": True,
            "calendar_access_granted_at": datetime.now(),
            "total_notifications_sent": 10,
            "last_notification_sent_at": datetime.now(),
            "created_at": datetime.now(),
            "updated_at": datetime.now(),
        }
        account_response = StaffCalendarAccountResponse(**response_data)
        assert account_response.id == uuid.UUID(response_data["id"])
        assert account_response.notification_email == "test@example.com"
        assert account_response.total_notifications_sent == 10

    def test_staff_calendar_account_response_from_attributes(self):
        """from_attributes=Trueが設定されていることをテスト"""
        assert StaffCalendarAccountResponse.model_config.get("from_attributes") is True
