from pydantic import BaseModel, Field, ConfigDict, computed_field
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
    """
    Role変更リクエスト読み取りスキーマ（統合ApprovalRequest対応）

    注意: 統合approval_requestsテーブルのデータを旧フォーマットに変換して返します
    """
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    requester_staff_id: uuid.UUID
    office_id: uuid.UUID
    status: RequestStatus
    reviewed_by_staff_id: Optional[uuid.UUID] = None
    reviewed_at: Optional[datetime] = None
    reviewer_notes: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    # 統合モデルのrequest_dataから抽出
    request_data: Optional[dict] = None

    @computed_field
    @property
    def from_role(self) -> Optional[StaffRole]:
        """request_dataからfrom_roleを抽出"""
        if self.request_data and "from_role" in self.request_data:
            try:
                return StaffRole(self.request_data["from_role"])
            except (ValueError, KeyError):
                return None
        return None

    @computed_field
    @property
    def requested_role(self) -> Optional[StaffRole]:
        """request_dataからrequested_roleを抽出"""
        if self.request_data and "requested_role" in self.request_data:
            try:
                return StaffRole(self.request_data["requested_role"])
            except (ValueError, KeyError):
                return None
        return None

    @computed_field
    @property
    def request_notes(self) -> Optional[str]:
        """request_dataからrequest_notesを抽出"""
        if self.request_data and "request_notes" in self.request_data:
            return self.request_data["request_notes"]
        return None


class RoleChangeRequestApprove(BaseModel):
    """Role変更リクエスト承認スキーマ"""
    reviewer_notes: Optional[str] = None


class RoleChangeRequestReject(BaseModel):
    """Role変更リクエスト却下スキーマ"""
    reviewer_notes: Optional[str] = None
