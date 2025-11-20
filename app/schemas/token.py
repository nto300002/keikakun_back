from pydantic import BaseModel, EmailStr, field_validator
from typing import Optional
import re


class Token(BaseModel):
    access_token: str
    token_type: str
    refresh_token: Optional[str] = None


class TokenData(BaseModel):
    sub: Optional[str] = None

class RefreshToken(BaseModel):
    refresh_token: str


class AccessToken(BaseModel):
    access_token: str
    token_type: str = "bearer"


class MFARequiredResponse(BaseModel):
    requires_mfa_verification: bool = True
    temporary_token: str


# Cookie認証用のレスポンススキーマ
class TokenWithCookie(BaseModel):
    """
    Cookie認証を使用する場合のレスポンス
    access_tokenはCookieに設定されるため、レスポンスボディには含まれない
    """
    refresh_token: str
    token_type: str = "bearer"
    session_duration: Optional[int] = None
    session_type: Optional[str] = None
    message: Optional[str] = None


class TokenRefreshResponse(BaseModel):
    """
    トークンリフレッシュ時のレスポンス
    access_tokenはCookieに設定されるため、レスポンスボディには含まれない
    """
    token_type: str = "bearer"
    session_duration: Optional[int] = None
    session_type: Optional[str] = None
    message: Optional[str] = None


# ==========================================
# パスワードリセット関連
# ==========================================

class ForgotPasswordRequest(BaseModel):
    """パスワードリセット要求"""
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    """パスワードリセット実行"""
    token: str
    new_password: str

    @field_validator("new_password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        """パスワード要件の検証"""
        if len(v) < 8:
            raise ValueError("パスワードは8文字以上である必要があります")

        checks = {
            "lowercase": lambda s: re.search(r'[a-z]', s),
            "uppercase": lambda s: re.search(r'[A-Z]', s),
            "digit": lambda s: re.search(r'\d', s),
            "symbol": lambda s: re.search(r'[!@#$%^&*(),.?":{}|<>]', s),
        }

        score = sum(1 for check in checks.values() if check(v))

        if score < 4:
            raise ValueError("パスワードは大文字、小文字、数字、記号を全て含む必要があります")

        return v


class PasswordResetResponse(BaseModel):
    """パスワードリセットレスポンス"""
    message: str


class TokenValidityResponse(BaseModel):
    """トークン有効性レスポンス"""
    valid: bool
    message: str