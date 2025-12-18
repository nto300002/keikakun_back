"""
Billingスキーマ: 事業所の課金情報
"""
from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.models.enums import BillingStatus


# 共通プロパティ
class BillingBase(BaseModel):
    """Billingの基本スキーマ"""
    billing_status: BillingStatus = BillingStatus.free
    trial_start_date: datetime
    trial_end_date: datetime
    subscription_start_date: Optional[datetime] = None
    next_billing_date: Optional[datetime] = None
    current_plan_amount: int = 6000
    last_payment_date: Optional[datetime] = None


# 作成時のスキーマ
class BillingCreate(BillingBase):
    """Billing作成時のスキーマ"""
    office_id: UUID
    stripe_customer_id: Optional[str] = None
    stripe_subscription_id: Optional[str] = None


# 更新時のスキーマ
class BillingUpdate(BaseModel):
    """Billing更新時のスキーマ"""
    stripe_customer_id: Optional[str] = None
    stripe_subscription_id: Optional[str] = None
    billing_status: Optional[BillingStatus] = None
    trial_end_date: Optional[datetime] = None
    subscription_start_date: Optional[datetime] = None
    next_billing_date: Optional[datetime] = None
    current_plan_amount: Optional[int] = None
    last_payment_date: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


# レスポンス用スキーマ
class BillingInDBBase(BillingBase):
    """DBからのBilling情報（共通）"""
    id: UUID
    office_id: UUID
    stripe_customer_id: Optional[str] = None
    stripe_subscription_id: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


# API レスポンス用
class Billing(BillingInDBBase):
    """API レスポンス用Billingスキーマ"""
    pass


# Billing ステータス取得用の簡易スキーマ（Phase 2のAPI用）
class BillingStatusResponse(BaseModel):
    """課金ステータス取得APIのレスポンス"""
    billing_status: BillingStatus
    trial_end_date: datetime
    next_billing_date: Optional[datetime] = None
    current_plan_amount: int

    model_config = ConfigDict(from_attributes=True)
