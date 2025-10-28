from pydantic import BaseModel
from typing import Optional


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