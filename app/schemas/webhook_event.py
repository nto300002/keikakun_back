"""
WebhookEvent スキーマ
"""
from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class WebhookEventBase(BaseModel):
    """WebhookEvent 基底スキーマ"""
    event_id: str = Field(..., description="Stripe Event ID")
    event_type: str = Field(..., description="イベントタイプ")
    source: str = Field(default="stripe", description="Webhook送信元")
    billing_id: Optional[UUID] = Field(None, description="関連するBilling ID")
    office_id: Optional[UUID] = Field(None, description="関連するOffice ID")
    payload: Optional[dict] = Field(None, description="Webhookペイロード")
    status: str = Field(default="success", description="処理ステータス")
    error_message: Optional[str] = Field(None, description="エラーメッセージ")


class WebhookEventCreate(WebhookEventBase):
    """WebhookEvent 作成用スキーマ"""
    pass


class WebhookEventUpdate(BaseModel):
    """WebhookEvent 更新用スキーマ"""
    status: Optional[str] = None
    error_message: Optional[str] = None


class WebhookEventInDBBase(WebhookEventBase):
    """WebhookEvent DB基底スキーマ"""
    id: UUID
    processed_at: datetime
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class WebhookEvent(WebhookEventInDBBase):
    """WebhookEvent レスポンス用スキーマ"""
    pass


class WebhookEventListResponse(BaseModel):
    """WebhookEvent 一覧レスポンス"""
    events: list[WebhookEvent]
    total: int
    limit: int
    offset: int
