from uuid import UUID
from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict

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

# --- Response Schemas ---

class OfficeResponse(BaseModel):
    id: UUID
    name: str
    # DBモデルの'type'属性を読み込み、JSON出力時には'office_type'というキー名に変換する
    type: OfficeType = Field(serialization_alias="office_type")
    billing_status: BillingStatus
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(
        from_attributes=True,
    )