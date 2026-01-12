from datetime import date
from typing import List
from pydantic import BaseModel, ConfigDict, Field
import uuid


class DeadlineAlertItem(BaseModel):
    """期限アラート項目"""
    id: str = Field(..., description="利用者ID（recipient.id）")
    full_name: str = Field(..., min_length=1, description="利用者フルネーム")
    alert_type: str = Field(..., description="アラートタイプ (renewal_deadline, assessment_incomplete)")
    message: str = Field(..., description="アラートメッセージ")
    next_renewal_deadline: date | None = Field(None, description="次回更新期限（renewal_deadlineの場合）")
    days_remaining: int | None = Field(None, ge=0, description="残り日数（renewal_deadlineの場合）")
    current_cycle_number: int = Field(..., ge=0, description="現在のサイクル番号")

    model_config = ConfigDict(
        from_attributes=True,
        json_encoders={uuid.UUID: lambda v: str(v)},
    )


class DeadlineAlertResponse(BaseModel):
    """期限アラートレスポンス"""
    alerts: List[DeadlineAlertItem] = Field(default_factory=list, description="期限が近い利用者のリスト")
    total: int = Field(..., ge=0, description="条件に合致する全利用者数")

    model_config = ConfigDict(from_attributes=True)
