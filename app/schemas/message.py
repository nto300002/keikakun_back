"""
メッセージ機能のスキーマ定義

個別メッセージ、一斉通知、受信箱、統計情報などのスキーマを提供
"""
from pydantic import BaseModel, Field, ConfigDict, field_validator
from typing import Optional, List
from datetime import datetime
import uuid

from app.models.enums import MessageType, MessagePriority


# ========================================
# 基本スキーマ
# ========================================

class MessageBase(BaseModel):
    """メッセージ基本スキーマ"""
    title: str = Field(..., min_length=1, max_length=200, description="メッセージタイトル")
    content: str = Field(..., min_length=1, description="メッセージ本文")
    priority: MessagePriority = Field(default=MessagePriority.normal, description="優先度")

    @field_validator("title")
    @classmethod
    def validate_title(cls, v: str) -> str:
        """タイトルのバリデーション"""
        v = v.strip()
        if not v:
            raise ValueError("タイトルは空にできません")
        if len(v) > 200:
            raise ValueError("タイトルは200文字以内で入力してください")
        return v

    @field_validator("content")
    @classmethod
    def validate_content(cls, v: str) -> str:
        """本文のバリデーション"""
        v = v.strip()
        if not v:
            raise ValueError("本文は空にできません")
        if len(v) > 10000:
            raise ValueError("本文は10000文字以内で入力してください")
        return v


# ========================================
# 作成スキーマ
# ========================================

class MessagePersonalCreate(MessageBase):
    """個別メッセージ作成スキーマ"""
    recipient_staff_ids: List[uuid.UUID] = Field(
        ...,
        min_length=1,
        description="受信者スタッフIDのリスト"
    )

    @field_validator("recipient_staff_ids")
    @classmethod
    def validate_recipients(cls, v: List[uuid.UUID]) -> List[uuid.UUID]:
        """受信者のバリデーション"""
        if not v:
            raise ValueError("受信者を少なくとも1人指定してください")
        if len(v) > 100:
            raise ValueError("一度に送信できる受信者は100人までです")
        # 重複チェック
        if len(v) != len(set(v)):
            raise ValueError("受信者リストに重複があります")
        return v


class MessageAnnouncementCreate(MessageBase):
    """一斉通知作成スキーマ"""
    # 一斉通知は事務所内の全スタッフに送信されるため、受信者指定は不要
    pass


# ========================================
# レスポンススキーマ - Message
# ========================================

class MessageSenderInfo(BaseModel):
    """送信者情報スキーマ"""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    first_name: str
    last_name: str
    email: str

    @property
    def full_name(self) -> str:
        """フルネームを返す"""
        return f"{self.last_name} {self.first_name}"


class MessageResponse(BaseModel):
    """メッセージレスポンススキーマ"""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    sender_staff_id: Optional[uuid.UUID]
    office_id: uuid.UUID
    message_type: MessageType
    priority: MessagePriority
    title: str
    content: str
    created_at: datetime
    updated_at: datetime


class MessageDetailResponse(MessageResponse):
    """メッセージ詳細レスポンススキーマ（送信者情報と受信者数を含む）"""
    sender: Optional[MessageSenderInfo] = None
    recipient_count: Optional[int] = Field(None, description="受信者数")


# ========================================
# レスポンススキーマ - MessageRecipient
# ========================================

class MessageRecipientResponse(BaseModel):
    """メッセージ受信者レスポンススキーマ"""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    message_id: uuid.UUID
    recipient_staff_id: uuid.UUID
    is_read: bool
    read_at: Optional[datetime] = None
    is_archived: bool
    created_at: datetime
    updated_at: datetime


# ========================================
# レスポンススキーマ - 受信箱
# ========================================

class MessageInboxItem(BaseModel):
    """受信箱アイテムスキーマ（メッセージ + 受信者状態）"""
    model_config = ConfigDict(from_attributes=True)

    # メッセージ情報
    message_id: uuid.UUID
    title: str
    content: str
    message_type: MessageType
    priority: MessagePriority
    created_at: datetime

    # 送信者情報
    sender_staff_id: Optional[uuid.UUID] = None
    sender_name: Optional[str] = None

    # 受信者状態
    recipient_id: uuid.UUID  # MessageRecipient.id
    is_read: bool
    read_at: Optional[datetime] = None
    is_archived: bool


class MessageInboxResponse(BaseModel):
    """受信箱レスポンススキーマ"""
    messages: List[MessageInboxItem]
    total: int
    unread_count: int


# ========================================
# レスポンススキーマ - 統計
# ========================================

class MessageStatsResponse(BaseModel):
    """メッセージ統計レスポンススキーマ"""
    message_id: uuid.UUID
    total_recipients: int = Field(..., description="総受信者数")
    read_count: int = Field(..., description="既読数")
    unread_count: int = Field(..., description="未読数")
    read_rate: float = Field(..., description="既読率（0.0〜1.0）")


class UnreadCountResponse(BaseModel):
    """未読件数レスポンススキーマ"""
    unread_count: int = Field(..., description="未読メッセージ数")


# ========================================
# レスポンススキーマ - リスト
# ========================================

class MessageListResponse(BaseModel):
    """メッセージリストレスポンススキーマ"""
    messages: List[MessageDetailResponse]
    total: int


# ========================================
# 更新スキーマ
# ========================================

class MessageMarkAsReadRequest(BaseModel):
    """既読化リクエストスキーマ"""
    # メッセージIDはパスパラメータから取得するため、ボディは空でもOK
    pass


class MessageArchiveRequest(BaseModel):
    """アーカイブリクエストスキーマ"""
    is_archived: bool = Field(..., description="アーカイブ状態")


# ========================================
# バッチ操作スキーマ
# ========================================

class MessageBulkMarkAsReadRequest(BaseModel):
    """一括既読化リクエストスキーマ"""
    message_ids: List[uuid.UUID] = Field(
        ...,
        min_length=1,
        max_length=100,
        description="既読化するメッセージIDのリスト"
    )

    @field_validator("message_ids")
    @classmethod
    def validate_message_ids(cls, v: List[uuid.UUID]) -> List[uuid.UUID]:
        """メッセージIDのバリデーション"""
        if not v:
            raise ValueError("メッセージIDを少なくとも1つ指定してください")
        if len(v) > 100:
            raise ValueError("一度に処理できるメッセージは100件までです")
        # 重複チェック
        if len(v) != len(set(v)):
            raise ValueError("メッセージIDリストに重複があります")
        return v


class MessageBulkOperationResponse(BaseModel):
    """一括操作レスポンススキーマ"""
    success_count: int = Field(..., description="成功件数")
    failed_count: int = Field(..., description="失敗件数")
    total_count: int = Field(..., description="総件数")
