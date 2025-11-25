from uuid import UUID
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field, ConfigDict, EmailStr

from app.models.enums import OfficeType, BillingStatus

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
    billing_status: BillingStatus
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