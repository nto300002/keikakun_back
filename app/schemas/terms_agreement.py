import uuid
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict


class TermsAgreementBase(BaseModel):
    """同意履歴の基本スキーマ"""
    terms_version: Optional[str] = None
    privacy_version: Optional[str] = None


class TermsAgreementCreate(TermsAgreementBase):
    """同意履歴作成用スキーマ"""
    staff_id: uuid.UUID
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None


class TermsAgreementUpdate(BaseModel):
    """同意履歴更新用スキーマ"""
    terms_of_service_agreed_at: Optional[datetime] = None
    privacy_policy_agreed_at: Optional[datetime] = None
    terms_version: Optional[str] = None
    privacy_version: Optional[str] = None
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None


class TermsAgreementRead(TermsAgreementBase):
    """同意履歴読み取り用スキーマ"""
    id: uuid.UUID
    staff_id: uuid.UUID
    terms_of_service_agreed_at: Optional[datetime] = None
    privacy_policy_agreed_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AgreeToTermsRequest(BaseModel):
    """利用規約・プライバシーポリシー同意リクエスト"""
    agree_to_terms: bool
    agree_to_privacy: bool
    terms_version: str = "1.0"
    privacy_version: str = "1.0"


class AgreeToTermsResponse(BaseModel):
    """同意レスポンス"""
    message: str
    agreed_at: datetime
    terms_version: str
    privacy_version: str
