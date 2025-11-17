from datetime import date
from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator
import uuid

from app.models.enums import StaffRole, BillingStatus, SupportPlanStep
from app.messages import ja


# --- ベーススキーマ ---
class DashboardBase(BaseModel):
    """ダッシュボード情報のベース"""
    staff_name: str = Field(..., min_length=1)
    staff_role: StaffRole
    office_id: uuid.UUID
    office_name: str = Field(..., min_length=1)
    current_user_count: int = Field(..., ge=0)
    max_user_count: int = Field(..., ge=0)
    billing_status: BillingStatus


# --- レスポンスモデル ---
class DashboardSummary(BaseModel):
    """ダッシュボード:利用者情報"""
    # Use str so tests (and JSON output) compare IDs as strings.
    id: str
    full_name: str = Field(..., min_length=1)
    # Make furigana optional to allow summaries without reading-field populated
    furigana: Optional[str] = Field(default=None, min_length=1)
    current_cycle_number: int = Field(..., ge=0)
    latest_step: Optional[SupportPlanStep]
    next_renewal_deadline: Optional[date]
    monitoring_due_date: Optional[date]
    monitoring_deadline: Optional[int] = None  # モニタリング期限（日数）

    # Use Pydantic v2 model_config only (remove class Config to avoid conflict)
    model_config = ConfigDict(
        from_attributes=True,
        json_encoders={uuid.UUID: lambda v: str(v)},
    )

    @field_validator('id')
    @classmethod
    def _validate_id_is_uuid(cls, v: str) -> str:
        """Ensure id is a valid UUID string and normalize formatting."""
        try:
            return str(uuid.UUID(str(v)))
        except Exception:
            raise ValueError(ja.VALIDATION_ID_MUST_BE_UUID)


class DashboardData(DashboardBase):
    """ダッシュボード情報（レスポンス）"""
    recipients: List[DashboardSummary]

    model_config = ConfigDict(from_attributes=True)


# --- 作成用スキーマ ---
class DashboardDataCreate(DashboardBase):
    """ダッシュボード情報（作成）"""
    recipients: List[uuid.UUID] # 作成時はIDのリストを受け取るなど、要件に応じて変更
