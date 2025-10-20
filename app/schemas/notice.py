from pydantic import BaseModel, Field, ConfigDict
from typing import Optional
from datetime import datetime
import uuid


class NoticeCreate(BaseModel):
    """通知作成スキーマ"""
    recipient_staff_id: uuid.UUID
    office_id: uuid.UUID
    type: str = Field(..., min_length=1, max_length=50)
    title: str = Field(..., min_length=1, max_length=255)
    content: Optional[str] = None
    link_url: Optional[str] = Field(None, max_length=255)


class NoticeUpdate(BaseModel):
    """通知更新スキーマ"""
    type: Optional[str] = Field(None, min_length=1, max_length=50)
    title: Optional[str] = Field(None, min_length=1, max_length=255)
    content: Optional[str] = None
    link_url: Optional[str] = Field(None, max_length=255)
    is_read: Optional[bool] = None


class NoticeResponse(BaseModel):
    """通知レスポンススキーマ"""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    recipient_staff_id: uuid.UUID
    office_id: uuid.UUID
    type: str
    title: str
    content: Optional[str]
    link_url: Optional[str]
    is_read: bool
    created_at: datetime
    updated_at: datetime


class NoticeListResponse(BaseModel):
    """通知リストレスポンススキーマ"""
    notices: list[NoticeResponse]
    total: int
    unread_count: int
