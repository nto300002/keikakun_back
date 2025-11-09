from pydantic import BaseModel, Field, ConfigDict
from typing import Optional
from datetime import datetime
import uuid

from app.models.enums import RequestStatus, ActionType, ResourceType


class EmployeeActionRequestBase(BaseModel):
    """Employee制限リクエスト基本スキーマ"""
    resource_type: ResourceType
    action_type: ActionType
    resource_id: Optional[uuid.UUID] = None
    request_data: Optional[dict] = None


class EmployeeActionRequestCreate(EmployeeActionRequestBase):
    """Employee制限リクエスト作成スキーマ"""
    pass


class EmployeeActionRequestRead(BaseModel):
    """Employee制限リクエスト読み取りスキーマ"""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    requester_staff_id: uuid.UUID
    office_id: uuid.UUID
    resource_type: ResourceType
    action_type: ActionType
    resource_id: Optional[uuid.UUID]
    request_data: Optional[dict]
    status: RequestStatus
    approved_by_staff_id: Optional[uuid.UUID]
    approved_at: Optional[datetime]
    approver_notes: Optional[str]
    execution_result: Optional[dict]
    created_at: datetime
    updated_at: datetime


class EmployeeActionRequestApprove(BaseModel):
    """Employee制限リクエスト承認スキーマ"""
    approver_notes: Optional[str] = None


class EmployeeActionRequestReject(BaseModel):
    """Employee制限リクエスト却下スキーマ"""
    approver_notes: Optional[str] = None
