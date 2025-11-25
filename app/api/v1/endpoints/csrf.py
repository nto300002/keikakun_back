"""
CSRF トークン関連のエンドポイント
"""
from fastapi import APIRouter, Depends, Response
from fastapi_csrf_protect import CsrfProtect
from pydantic import BaseModel

from app.core.csrf import get_csrf_config


router = APIRouter()


class CsrfTokenResponse(BaseModel):
    """CSRFトークンレスポンス"""
    csrf_token: str


@router.get("/csrf-token", response_model=CsrfTokenResponse)
async def get_csrf_token(
    response: Response,
    csrf_protect: CsrfProtect = Depends()
):
    """
    CSRFトークンを取得

    クライアントはこのエンドポイントでCSRFトークンを取得し、
    状態変更リクエスト(POST/PUT/DELETE)の際にヘッダーに含める必要がある。

    Returns:
        CsrfTokenResponse: CSRFトークン
    """
    # CSRFトークンを生成（タプル: (csrf_token, signed_token) を返す）
    csrf_token, signed_token = csrf_protect.generate_csrf_tokens()

    # 署名付きトークンをCookieに設定
    csrf_protect.set_csrf_cookie(signed_token, response)

    return CsrfTokenResponse(csrf_token=csrf_token)
