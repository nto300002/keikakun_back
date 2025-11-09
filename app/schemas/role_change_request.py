from pydantic import BaseModel, Field, ConfigDict
from typing import Optional
from datetime import datetime
import uuid

from app.models.enums import StaffRole, RequestStatus


class RoleChangeRequestBase(BaseModel):
    """Role変更リクエスト基本スキーマ"""
    requested_role: StaffRole
    request_notes: Optional[str] = None


class RoleChangeRequestCreate(RoleChangeRequestBase):
    """Role変更リクエスト作成スキーマ"""
    pass


class RoleChangeRequestRead(BaseModel):
    """Role変更リクエスト読み取りスキーマ"""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    requester_staff_id: uuid.UUID
    office_id: uuid.UUID
    from_role: StaffRole
    requested_role: StaffRole
    status: RequestStatus
    request_notes: Optional[str]
    reviewed_by_staff_id: Optional[uuid.UUID]
    reviewed_at: Optional[datetime]
    reviewer_notes: Optional[str]
    created_at: datetime
    updated_at: datetime


class RoleChangeRequestApprove(BaseModel):
    """Role変更リクエスト承認スキーマ"""
    reviewer_notes: Optional[str] = None


class RoleChangeRequestReject(BaseModel):
    """Role変更リクエスト却下スキーマ"""
    reviewer_notes: Optional[str] = None
