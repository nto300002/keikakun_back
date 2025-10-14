from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict
import uuid

from app.models.enums import CalendarEventType, CalendarSyncStatus


# ==================== CalendarEvent Schemas ====================

class CalendarEventBase(BaseModel):
    """カレンダーイベントのベーススキーマ"""
    event_type: CalendarEventType
    google_calendar_id: str
    event_title: str
    event_description: Optional[str] = None
    event_start_datetime: datetime
    event_end_datetime: datetime


class CalendarEventCreate(CalendarEventBase):
    """カレンダーイベント作成用スキーマ"""
    office_id: uuid.UUID
    welfare_recipient_id: uuid.UUID
    support_plan_cycle_id: Optional[uuid.UUID] = None
    support_plan_status_id: Optional[uuid.UUID] = None
    google_event_id: Optional[str] = None
    google_event_url: Optional[str] = None
    created_by_system: bool = True
    sync_status: CalendarSyncStatus = CalendarSyncStatus.pending


class CalendarEventUpdate(BaseModel):
    """カレンダーイベント更新用スキーマ"""
    event_title: Optional[str] = None
    event_description: Optional[str] = None
    event_start_datetime: Optional[datetime] = None
    event_end_datetime: Optional[datetime] = None
    google_event_id: Optional[str] = None
    google_event_url: Optional[str] = None
    sync_status: Optional[CalendarSyncStatus] = None
    last_sync_at: Optional[datetime] = None
    last_error_message: Optional[str] = None


class CalendarEventResponse(CalendarEventBase):
    """カレンダーイベントレスポンス用スキーマ"""
    id: uuid.UUID
    office_id: uuid.UUID
    welfare_recipient_id: uuid.UUID
    support_plan_cycle_id: Optional[uuid.UUID] = None
    support_plan_status_id: Optional[uuid.UUID] = None
    google_event_id: Optional[str] = None
    google_event_url: Optional[str] = None
    created_by_system: bool
    sync_status: CalendarSyncStatus
    last_sync_at: Optional[datetime] = None
    last_error_message: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class CalendarEventInDB(CalendarEventResponse):
    """DB内のカレンダーイベント"""
    model_config = ConfigDict(from_attributes=True)
