"""
退会リクエストスキーマ

事務所退会申請のためのPydanticスキーマ
"""
from pydantic import BaseModel, Field, ConfigDict
from typing import Optional
from datetime import datetime
import uuid

from app.models.enums import RequestStatus


class WithdrawalRequestBase(BaseModel):
    """退会リクエスト基本スキーマ"""
    title: str = Field(..., min_length=1, max_length=100, description="退会申請のタイトル")
    reason: str = Field(..., min_length=1, max_length=2000, description="退会理由")


class WithdrawalRequestCreate(WithdrawalRequestBase):
    """退会リクエスト作成スキーマ"""
    pass


class WithdrawalRequestRead(BaseModel):
    """退会リクエスト読み取りスキーマ"""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    requester_staff_id: uuid.UUID
    office_id: uuid.UUID
    status: RequestStatus
    title: str
    reason: str
    reviewed_by_staff_id: Optional[uuid.UUID] = None
    reviewed_at: Optional[datetime] = None
    reviewer_notes: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    # リクエスト作成者情報（展開用）
    requester_name: Optional[str] = None
    office_name: Optional[str] = None


class WithdrawalRequestApprove(BaseModel):
    """退会リクエスト承認スキーマ"""
    reviewer_notes: Optional[str] = Field(None, max_length=500, description="承認者のメモ")


class WithdrawalRequestReject(BaseModel):
    """退会リクエスト却下スキーマ"""
    reviewer_notes: Optional[str] = Field(None, max_length=500, description="却下理由")


class WithdrawalRequestListResponse(BaseModel):
    """退会リクエスト一覧レスポンス"""
    items: list[WithdrawalRequestRead]
    total: int
    skip: int
    limit: int
