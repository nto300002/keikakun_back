from uuid import UUID
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field, ConfigDict, EmailStr

from app.models.enums import OfficeType

# --- Request Schemas ---

class OfficeBase(BaseModel):
    name: str = Field(..., min_length=5, max_length=100)
    office_type: OfficeType = Field(alias="type")

    model_config = ConfigDict(
        populate_by_name=True,
    )

class OfficeCreate(OfficeBase):
    pass

class OfficeUpdate(OfficeBase):
    pass


class OfficeInfoUpdate(BaseModel):
    """事務所情報更新用スキーマ"""
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    type: Optional[OfficeType] = None
    address: Optional[str] = Field(None, max_length=500)
    phone_number: Optional[str] = Field(None, pattern=r'^\d{2,4}-\d{2,4}-\d{4}$')
    email: Optional[EmailStr] = None

    model_config = ConfigDict(
        from_attributes=True,
    )

# --- Response Schemas ---

class OfficeResponse(BaseModel):
    id: UUID
    name: str
    # DBモデルの'type'属性を読み込み、JSON出力時には'office_type'というキー名に変換する
    type: OfficeType = Field(serialization_alias="office_type")
    address: Optional[str] = None
    phone_number: Optional[str] = None
    email: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(
        from_attributes=True,
    )


class OfficeAuditLogResponse(BaseModel):
    """監査ログレスポンス用スキーマ"""
    id: UUID
    office_id: UUID
    staff_id: Optional[UUID] = None
    action_type: str
    details: Optional[str] = None
    created_at: datetime

    model_config = ConfigDict(
        from_attributes=True,
    )


# --- app_admin用レスポンススキーマ ---

class StaffInOffice(BaseModel):
    """事務所詳細レスポンス内のスタッフ情報"""
    id: UUID
    full_name: str
    email: str
    role: str
    is_mfa_enabled: bool
    is_email_verified: bool

    model_config = ConfigDict(
        from_attributes=True,
    )


class OfficeListItemResponse(BaseModel):
    """事務所一覧アイテム（app_admin用）"""
    id: UUID
    name: str
    type: OfficeType = Field(serialization_alias="office_type")
    is_deleted: bool
    created_at: datetime

    model_config = ConfigDict(
        from_attributes=True,
    )


class OfficeDetailResponse(BaseModel):
    """事務所詳細（app_admin用）"""
    id: UUID
    name: str
    type: OfficeType = Field(serialization_alias="office_type")
    address: Optional[str] = None
    phone_number: Optional[str] = None
    email: Optional[str] = None
    is_deleted: bool
    created_at: datetime
    updated_at: datetime
    staffs: list[StaffInOffice] = []

    model_config = ConfigDict(
        from_attributes=True,
    )