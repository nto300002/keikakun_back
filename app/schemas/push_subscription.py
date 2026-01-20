"""
Web Push通知購読のスキーマ定義
"""
from pydantic import BaseModel, Field, ConfigDict
from datetime import datetime
from uuid import UUID
from typing import Dict


class PushSubscriptionKeys(BaseModel):
    """Push購読のkeysオブジェクト"""
    p256dh: str = Field(..., description="P-256公開鍵（Base64エンコード）")
    auth: str = Field(..., description="認証シークレット（Base64エンコード）")


class PushSubscriptionCreate(BaseModel):
    """Push購読登録リクエスト"""
    endpoint: str = Field(..., description="Push Service提供のエンドポイントURL")
    keys: PushSubscriptionKeys = Field(..., description="暗号化キー情報")


class PushSubscriptionInDB(BaseModel):
    """DB保存用のPush購読データ"""
    staff_id: UUID
    endpoint: str
    p256dh_key: str
    auth_key: str
    user_agent: str | None = None


class PushSubscriptionResponse(BaseModel):
    """Push購読のレスポンス"""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    staff_id: UUID
    endpoint: str
    created_at: datetime


class PushSubscriptionInfo(BaseModel):
    """Push通知送信用の購読情報"""
    endpoint: str
    keys: Dict[str, str] = Field(..., description="p256dh と auth を含む辞書")

    @classmethod
    def from_db_model(cls, db_subscription) -> "PushSubscriptionInfo":
        """DBモデルから変換"""
        return cls(
            endpoint=db_subscription.endpoint,
            keys={
                "p256dh": db_subscription.p256dh_key,
                "auth": db_subscription.auth_key
            }
        )
