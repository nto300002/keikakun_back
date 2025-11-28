from pydantic import BaseModel, Field, ConfigDict, computed_field
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
    """
    Employee制限リクエスト読み取りスキーマ（統合ApprovalRequest対応）

    注意: 統合approval_requestsテーブルのデータを旧フォーマットに変換して返します
    """
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    requester_staff_id: uuid.UUID
    office_id: uuid.UUID
    status: RequestStatus
    created_at: datetime
    updated_at: datetime
    execution_result: Optional[dict] = None

    # 統合モデルのrequest_dataから抽出
    request_data: Optional[dict] = None

    @computed_field
    @property
    def resource_type(self) -> Optional[ResourceType]:
        """request_dataからresource_typeを抽出"""
        if self.request_data and "resource_type" in self.request_data:
            try:
                return ResourceType(self.request_data["resource_type"])
            except (ValueError, KeyError):
                return None
        return None

    @computed_field
    @property
    def action_type(self) -> Optional[ActionType]:
        """request_dataからaction_typeを抽出"""
        if self.request_data and "action_type" in self.request_data:
            try:
                return ActionType(self.request_data["action_type"])
            except (ValueError, KeyError):
                return None
        return None

    @computed_field
    @property
    def resource_id(self) -> Optional[uuid.UUID]:
        """request_dataからresource_idを抽出"""
        if self.request_data and "resource_id" in self.request_data:
            try:
                return uuid.UUID(self.request_data["resource_id"])
            except (ValueError, KeyError, TypeError):
                return None
        return None

    # reviewed_by_staff_id を approved_by_staff_id にマッピング（後方互換性）
    approved_by_staff_id: Optional[uuid.UUID] = Field(None, alias="reviewed_by_staff_id")
    approved_at: Optional[datetime] = Field(None, alias="reviewed_at")
    approver_notes: Optional[str] = Field(None, alias="reviewer_notes")


class EmployeeActionRequestApprove(BaseModel):
    """Employee制限リクエスト承認スキーマ"""
    approver_notes: Optional[str] = None


class EmployeeActionRequestReject(BaseModel):
    """Employee制限リクエスト却下スキーマ"""
    approver_notes: Optional[str] = None
