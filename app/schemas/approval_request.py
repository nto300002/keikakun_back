from pydantic import BaseModel, Field, ConfigDict
from typing import Optional
from datetime import datetime
import uuid

from app.models.enums import RequestStatus, ApprovalResourceType


class ApprovalRequestBase(BaseModel):
    """統合型承認リクエスト基本スキーマ"""
    resource_type: ApprovalResourceType
    request_data: Optional[dict] = None


class ApprovalRequestCreate(ApprovalRequestBase):
    """統合型承認リクエスト作成スキーマ"""
    pass


class ApprovalRequestRead(BaseModel):
    """統合型承認リクエスト読み取りスキーマ"""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    requester_staff_id: uuid.UUID
    office_id: uuid.UUID
    resource_type: ApprovalResourceType
    status: RequestStatus
    request_data: Optional[dict]
    reviewed_by_staff_id: Optional[uuid.UUID]
    reviewed_at: Optional[datetime]
    reviewer_notes: Optional[str]
    execution_result: Optional[dict]
    created_at: datetime
    updated_at: datetime
    is_test_data: bool = False


class ApprovalRequestApprove(BaseModel):
    """統合型承認リクエスト承認スキーマ"""
    reviewer_notes: Optional[str] = None


class ApprovalRequestReject(BaseModel):
    """統合型承認リクエスト却下スキーマ"""
    reviewer_notes: Optional[str] = None


# Employee Action用の便利スキーマ（employee_action固有のrequest_data構造）
class EmployeeActionRequestData(BaseModel):
    """Employee Action用のrequest_dataスキーマ"""
    resource_type: str  # ResourceType.value
    action_type: str    # ActionType.value
    resource_id: Optional[str] = None  # UUID string
    original_request_data: Optional[dict] = None


# Role Change用の便利スキーマ（role_change固有のrequest_data構造）
class RoleChangeRequestData(BaseModel):
    """Role Change用のrequest_dataスキーマ"""
    from_role: str
    requested_role: str
    request_notes: Optional[str] = None
