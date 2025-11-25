"""
CSRF保護の設定と機能

Double Submit Cookie パターンを使用してCSRF攻撃を防ぐ。
Cookie認証を使用する状態変更エンドポイント(POST/PUT/DELETE)に対して、
CSRFトークンの検証を行う。

Bearer認証の場合はCSRF保護は不要（Same-Origin Policyにより保護される）
"""
import os
from typing import Optional
from fastapi import Request, HTTPException, status
from fastapi_csrf_protect import CsrfProtect
from fastapi_csrf_protect.exceptions import CsrfProtectError
from pydantic import BaseModel, Field


class CsrfSettings(BaseModel):
    """CSRF保護の設定"""

    secret_key: str = Field(default_factory=lambda: os.getenv("SECRET_KEY", "your-secret-key"))
    cookie_name: str = "fastapi-csrf-token"
    header_name: str = "X-CSRF-Token"
    cookie_samesite: str = "lax"
    cookie_secure: bool = Field(default_factory=lambda: os.getenv("ENVIRONMENT") == "production")
    cookie_httponly: bool = False  # JavaScriptからアクセス可能にする必要がある
    cookie_domain: Optional[str] = Field(default_factory=lambda: os.getenv("COOKIE_DOMAIN", None))


@CsrfProtect.load_config
def get_csrf_config():
    """CSRF保護の設定を読み込む"""
    return CsrfSettings()


async def validate_csrf_token(
    request: Request,
    csrf_protect: CsrfProtect,
) -> None:
    """
    CSRFトークンを検証する

    Cookie認証を使用している場合のみCSRF検証を行う。
    Bearer認証（Authorizationヘッダー）の場合は検証をスキップ。

    Args:
        request: FastAPIリクエストオブジェクト
        csrf_protect: CsrfProtectインスタンス

    Raises:
        HTTPException: CSRFトークンが無効な場合
    """
    # Authorizationヘッダーがある場合（Bearer認証）はCSRF検証をスキップ
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        return

    # Cookie認証を使用している場合、CSRF検証を行う
    access_token_cookie = request.cookies.get("access_token")
    if access_token_cookie:
        try:
            await csrf_protect.validate_csrf(request)
        except CsrfProtectError as e:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"CSRF token validation failed: {str(e)}"
            )
