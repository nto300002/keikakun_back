from pydantic import BaseModel, ConfigDict, field_validator
from uuid import UUID
from typing import Optional, List
from datetime import date, datetime
from enum import Enum

from app.models.enums import DeliverableType, SupportPlanStep

class PlanDeliverableCreate(BaseModel):
    plan_cycle_id: int
    deliverable_type: DeliverableType
    file_path: str
    original_filename: str
    # uploaded_by は認証情報から取得するため、APIの入力スキーマには含めないのが一般的

class PlanDeliverableRead(BaseModel):
    id: int
    plan_cycle_id: int
    deliverable_type: DeliverableType
    file_path: str
    original_filename: str
    uploaded_by: UUID

    model_config = ConfigDict(from_attributes=True)

# Alias for backward compatibility
PlanDeliverable = PlanDeliverableRead


class PlanDeliverableDownloadResponse(BaseModel):
    presigned_url: str


class SupportPlanCycleUpdate(BaseModel):
    monitoring_deadline: int


class SupportPlanStatusResponse(BaseModel):
    id: int
    plan_cycle_id: int
    step_type: SupportPlanStep
    is_latest_status: bool
    completed: bool
    completed_at: Optional[datetime]
    due_date: Optional[date]
    monitoring_deadline: Optional[int] = None  # モニタリング期限（日数）
    pdf_url: Optional[str] = None  # 署名付きPDF URL（フロントエンド用）
    pdf_filename: Optional[str] = None  # PDF元ファイル名（フロントエンド用）

    model_config = ConfigDict(from_attributes=True)

class SupportPlanCycleRead(BaseModel):
    id: int
    welfare_recipient_id: UUID
    plan_cycle_start_date: Optional[date]
    final_plan_signed_date: Optional[date]
    next_renewal_deadline: Optional[date]
    is_latest_cycle: bool
    cycle_number: int
    monitoring_deadline: Optional[int]
    statuses: List[SupportPlanStatusResponse] = []

    model_config = ConfigDict(from_attributes=True)

class SupportPlanCyclesResponse(BaseModel):
    cycles: List[SupportPlanCycleRead]


# ========================================
# PDF一覧取得用スキーマ
# ========================================

class SortBy(str, Enum):
    """ソート対象"""
    uploaded_at = "uploaded_at"
    recipient_name = "recipient_name"
    file_name = "file_name"


class SortOrder(str, Enum):
    """ソート順"""
    asc = "asc"
    desc = "desc"


class WelfareRecipientBrief(BaseModel):
    """利用者情報（簡易版）"""
    id: UUID
    full_name: str
    full_name_furigana: str

    model_config = ConfigDict(from_attributes=True)


class StaffBrief(BaseModel):
    """スタッフ情報（簡易版）"""
    id: UUID
    name: str
    role: str

    model_config = ConfigDict(from_attributes=True)


class PlanCycleBrief(BaseModel):
    """計画サイクル情報（簡易版）"""
    id: int
    cycle_number: int
    plan_cycle_start_date: Optional[date]
    next_renewal_deadline: Optional[date]
    is_latest_cycle: bool

    model_config = ConfigDict(from_attributes=True)


class PlanDeliverableListItem(BaseModel):
    """PDF成果物レスポンス（一覧用）"""
    id: int
    original_filename: str
    file_path: str
    deliverable_type: DeliverableType
    deliverable_type_display: str
    plan_cycle: PlanCycleBrief
    welfare_recipient: WelfareRecipientBrief
    uploaded_by: StaffBrief
    uploaded_at: datetime
    download_url: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class PlanDeliverableListResponse(BaseModel):
    """PDF一覧レスポンス"""
    items: List[PlanDeliverableListItem]
    total: int
    skip: int
    limit: int
    has_more: bool