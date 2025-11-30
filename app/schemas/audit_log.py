"""
監査ログのPydanticスキーマ
"""
from datetime import datetime
from typing import Optional, Dict, Any, List
from uuid import UUID
from pydantic import BaseModel, Field, field_serializer


class AuditLogResponse(BaseModel):
    """監査ログレスポンス"""
    id: UUID
    staff_id: UUID
    actor_id: Optional[UUID] = None
    actor_name: Optional[str] = None
    actor_role: Optional[str] = None
    action: str
    target_type: str
    target_id: Optional[UUID] = None
    office_id: Optional[UUID] = None
    office_name: Optional[str] = None
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    details: Optional[Dict[str, Any]] = None
    timestamp: datetime
    created_at: Optional[datetime] = None
    is_test_data: bool = False

    model_config = {"from_attributes": True}

    def model_post_init(self, __context):
        """timestampをcreated_atにも設定"""
        if self.created_at is None:
            self.created_at = self.timestamp


class AuditLogListResponse(BaseModel):
    """監査ログ一覧レスポンス"""
    logs: List[AuditLogResponse]
    total: int
    skip: int
    limit: int
