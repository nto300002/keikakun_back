"""
問い合わせ機能のスキーマ定義

問い合わせ送信、一覧取得、詳細表示、返信、更新などのスキーマを提供
"""
from pydantic import BaseModel, Field, ConfigDict, field_validator, EmailStr
from typing import Optional, List
from datetime import datetime
import uuid
import re

from app.models.enums import InquiryStatus, InquiryPriority, MessageType


# ========================================
# 基本スキーマ
# ========================================

class InquiryBase(BaseModel):
    """問い合わせ基本スキーマ"""
    title: str = Field(..., min_length=1, max_length=200, description="問い合わせ件名")
    content: str = Field(..., min_length=1, max_length=20000, description="問い合わせ内容")

    @field_validator("title")
    @classmethod
    def validate_title(cls, v: str) -> str:
        """タイトルのバリデーション"""
        v = v.strip()
        if not v:
            raise ValueError("件名は空にできません")
        if len(v) > 200:
            raise ValueError("件名は200文字以内で入力してください")
        return v

    @field_validator("content")
    @classmethod
    def validate_content(cls, v: str) -> str:
        """内容のバリデーション"""
        v = v.strip()
        if not v:
            raise ValueError("内容は空にできません")
        if len(v) > 20000:
            raise ValueError("内容は20,000文字以内で入力してください")
        return v


# ========================================
# 作成スキーマ
# ========================================

class InquiryCreate(InquiryBase):
    """問い合わせ作成スキーマ（公開エンドポイント用）"""
    category: Optional[str] = Field(None, description="問い合わせ種別（不具合 | 質問 | その他）")
    sender_name: Optional[str] = Field(None, max_length=100, description="送信者名（未ログイン時は推奨）")
    sender_email: Optional[EmailStr] = Field(None, description="送信者メールアドレス（未ログイン時は必須）")

    @field_validator("category")
    @classmethod
    def validate_category(cls, v: Optional[str]) -> Optional[str]:
        """カテゴリのバリデーション"""
        if v is None:
            return v

        allowed_categories = ["不具合", "質問", "その他"]
        if v not in allowed_categories:
            raise ValueError(f"カテゴリは {', '.join(allowed_categories)} のいずれかを指定してください")
        return v

    @field_validator("sender_name")
    @classmethod
    def validate_sender_name(cls, v: Optional[str]) -> Optional[str]:
        """送信者名のバリデーション"""
        if v is None:
            return v

        v = v.strip()
        if len(v) > 100:
            raise ValueError("お名前は100文字以内で入力してください")
        return v if v else None


class InquiryCreateInternal(BaseModel):
    """内部問い合わせ作成用スキーマ（Message + InquiryDetail 同時作成）"""
    # Message 用
    title: str
    content: str
    message_type: MessageType = MessageType.inquiry
    office_id: uuid.UUID
    sender_staff_id: Optional[uuid.UUID] = None

    # InquiryDetail 用
    sender_name: Optional[str] = None
    sender_email: Optional[EmailStr] = None
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    status: InquiryStatus = InquiryStatus.new
    priority: InquiryPriority = InquiryPriority.normal


# ========================================
# レスポンススキーマ - InquiryDetail
# ========================================

class InquiryDetailResponse(BaseModel):
    """問い合わせ詳細レスポンススキーマ"""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    message_id: uuid.UUID
    sender_name: Optional[str] = None
    sender_email: Optional[str] = None
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    status: InquiryStatus
    assigned_staff_id: Optional[uuid.UUID] = None
    priority: InquiryPriority
    admin_notes: Optional[str] = None
    delivery_log: Optional[dict] = None
    created_at: datetime
    updated_at: datetime


class MessageInfo(BaseModel):
    """メッセージ情報スキーマ"""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    content: str
    created_at: datetime
    sender_staff_id: Optional[uuid.UUID] = None


class StaffInfo(BaseModel):
    """スタッフ情報スキーマ"""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    first_name: str
    last_name: str
    email: str

    @property
    def full_name(self) -> str:
        """フルネームを返す"""
        return f"{self.last_name} {self.first_name}"


class InquiryFullResponse(BaseModel):
    """問い合わせ詳細レスポンススキーマ（メッセージ情報を含む）"""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    message: MessageInfo
    inquiry_detail: InquiryDetailResponse
    assigned_staff: Optional[StaffInfo] = None
    reply_history: Optional[List[dict]] = None  # 返信履歴（将来の拡張用）


# ========================================
# レスポンススキーマ - 一覧
# ========================================

class InquiryListItem(BaseModel):
    """問い合わせ一覧アイテムスキーマ"""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    message_id: uuid.UUID
    title: str
    status: InquiryStatus
    priority: InquiryPriority
    sender_name: Optional[str] = None
    sender_email: Optional[str] = None
    assigned_staff_id: Optional[uuid.UUID] = None
    assigned_staff: Optional[StaffInfo] = None
    created_at: datetime
    updated_at: datetime


class InquiryListResponse(BaseModel):
    """問い合わせ一覧レスポンススキーマ"""
    inquiries: List[InquiryListItem]
    total: int


# ========================================
# 更新スキーマ
# ========================================

class InquiryUpdate(BaseModel):
    """問い合わせ更新スキーマ（管理者専用）"""
    status: Optional[InquiryStatus] = Field(None, description="ステータス")
    assigned_staff_id: Optional[uuid.UUID] = Field(None, description="担当者ID")
    priority: Optional[InquiryPriority] = Field(None, description="優先度")
    admin_notes: Optional[str] = Field(None, description="管理者メモ")

    @field_validator("admin_notes")
    @classmethod
    def validate_admin_notes(cls, v: Optional[str]) -> Optional[str]:
        """管理者メモのバリデーション"""
        if v is None:
            return v

        v = v.strip()
        if len(v) > 5000:
            raise ValueError("管理者メモは5,000文字以内で入力してください")
        return v if v else None


# ========================================
# 返信スキーマ
# ========================================

class InquiryReply(BaseModel):
    """問い合わせ返信スキーマ"""
    body: str = Field(..., min_length=1, max_length=20000, description="返信内容")
    send_email: bool = Field(default=False, description="メール送信するか")

    @field_validator("body")
    @classmethod
    def validate_body(cls, v: str) -> str:
        """返信内容のバリデーション"""
        v = v.strip()
        if not v:
            raise ValueError("返信内容は空にできません")
        if len(v) > 20000:
            raise ValueError("返信内容は20,000文字以内で入力してください")
        return v


class InquiryReplyResponse(BaseModel):
    """問い合わせ返信レスポンススキーマ"""
    id: uuid.UUID
    message: str = Field(..., description="処理結果メッセージ")


# ========================================
# クエリパラメータスキーマ
# ========================================

class InquiryQueryParams(BaseModel):
    """問い合わせ一覧取得クエリパラメータ"""
    status: Optional[InquiryStatus] = Field(None, description="ステータスフィルタ")
    assigned: Optional[uuid.UUID] = Field(None, description="担当者IDフィルタ")
    priority: Optional[InquiryPriority] = Field(None, description="優先度フィルタ")
    search: Optional[str] = Field(None, max_length=200, description="キーワード検索（件名・本文）")
    skip: int = Field(default=0, ge=0, description="オフセット")
    limit: int = Field(default=20, ge=1, le=100, description="取得件数")
    sort: Optional[str] = Field(default="created_at", description="ソートキー（created_at | updated_at | priority）")

    @field_validator("sort")
    @classmethod
    def validate_sort(cls, v: str) -> str:
        """ソートキーのバリデーション"""
        allowed_sorts = ["created_at", "updated_at", "priority"]
        if v not in allowed_sorts:
            raise ValueError(f"ソートキーは {', '.join(allowed_sorts)} のいずれかを指定してください")
        return v

    @field_validator("search")
    @classmethod
    def validate_search(cls, v: Optional[str]) -> Optional[str]:
        """検索キーワードのバリデーション"""
        if v is None:
            return v

        v = v.strip()
        if len(v) > 200:
            raise ValueError("検索キーワードは200文字以内で入力してください")
        return v if v else None


# ========================================
# 作成成功レスポンス
# ========================================

class InquiryCreateResponse(BaseModel):
    """問い合わせ作成レスポンススキーマ"""
    id: uuid.UUID
    message: str = Field(default="問い合わせを受け付けました", description="処理結果メッセージ")


class InquiryUpdateResponse(BaseModel):
    """問い合わせ更新レスポンススキーマ"""
    id: uuid.UUID
    message: str = Field(default="更新しました", description="処理結果メッセージ")


class InquiryDeleteResponse(BaseModel):
    """問い合わせ削除レスポンススキーマ"""
    message: str = Field(default="削除しました", description="処理結果メッセージ")
