"""
決済通知イベントのスキーマ
"""
from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_serializer

from app.utils.privacy_utils import mask_webhook_payload_for_display


class WebhookEventBase(BaseModel):
    """決済通知イベント基底スキーマ"""
    event_id: str = Field(..., description="Stripe Event ID")
    event_type: str = Field(..., description="イベントタイプ")
    source: str = Field(default="stripe", description="決済通知の送信元")
    billing_id: Optional[UUID] = Field(None, description="関連するBilling ID")
    office_id: Optional[UUID] = Field(None, description="関連するOffice ID")
    payload: Optional[dict] = Field(None, description="決済通知の内容")
    status: str = Field(default="success", description="処理状態")
    error_message: Optional[str] = Field(None, description="エラーメッセージ")


class WebhookEventCreate(WebhookEventBase):
    """決済通知イベント作成用スキーマ"""
    pass


class WebhookEventUpdate(BaseModel):
    """決済通知イベント更新用スキーマ"""
    status: Optional[str] = None
    error_message: Optional[str] = None


class WebhookEventInDBBase(WebhookEventBase):
    """決済通知イベントDB基底スキーマ"""
    id: UUID
    processed_at: datetime
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class WebhookEvent(WebhookEventInDBBase):
    """決済通知イベントレスポンス用スキーマ"""

    @field_serializer("payload")
    def serialize_payload(self, payload: Optional[dict]) -> Optional[dict]:
        if payload is None:
            return None
        return mask_webhook_payload_for_display(payload)


class WebhookEventListResponse(BaseModel):
    """決済通知イベント一覧レスポンス"""
    events: list[WebhookEvent]
    total: int
    limit: int
    offset: int
