from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from fastapi_csrf_protect.exceptions import CsrfProtectError
import uvicorn
import logging
import sys
import atexit
import os
import html

from app.core.limiter import limiter  # 新しいファイルからインポート
from app.core.config import settings # settingsをインポート
from app.api.v1.api import api_router
from app.scheduler.calendar_sync_scheduler import calendar_sync_scheduler
from app.scheduler.cleanup_scheduler import cleanup_scheduler
from app.scheduler.billing_scheduler import billing_scheduler

# ログ設定（標準出力に出力）
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)

logger = logging.getLogger(__name__)
logger.info("Application starting...")

app = FastAPI()
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


@app.exception_handler(CsrfProtectError)
async def csrf_protect_exception_handler(request: Request, exc: CsrfProtectError):
    """CSRF保護のエラーハンドラー"""
    return JSONResponse(
        status_code=403,
        content={"detail": f"CSRF token validation failed: {exc.message}"}
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """
    バリデーションエラーのカスタムハンドラー
    XSS攻撃対策として、エラーレスポンスから危険な文字をサニタイズする
    """
    def sanitize_value(value):
        """危険な文字をHTMLエスケープ"""
        if isinstance(value, str):
            return html.escape(value)
        elif isinstance(value, dict):
            return {k: sanitize_value(v) for k, v in value.items()}
        elif isinstance(value, list):
            return [sanitize_value(v) for v in value]
        elif isinstance(value, Exception):
            # Exception オブジェクトは文字列に変換
            return str(value)
        return value

    # エラー詳細をサニタイズ
    errors = []
    for error in exc.errors():
        sanitized_error = {}
        for key, value in error.items():
            if key == "input":
                sanitized_error[key] = sanitize_value(value)
            elif key == "ctx" and isinstance(value, dict):
                # ctx 内の error オブジェクトを文字列化
                sanitized_ctx = {}
                for ctx_key, ctx_value in value.items():
                    if isinstance(ctx_value, Exception):
                        sanitized_ctx[ctx_key] = str(ctx_value)
                    else:
                        sanitized_ctx[ctx_key] = sanitize_value(ctx_value)
                sanitized_error[key] = sanitized_ctx
            else:
                sanitized_error[key] = value
        errors.append(sanitized_error)

    return JSONResponse(
        status_code=422,
        content={"detail": errors}
    )


@app.on_event("startup")
async def startup_event():
    """アプリケーション起動時の処理"""
    # テスト環境ではスケジューラーを起動しない
    if os.getenv("TESTING") != "1":
        logger.info("Starting calendar sync scheduler...")
        calendar_sync_scheduler.start()
        logger.info("Calendar sync scheduler started successfully")

        logger.info("Starting cleanup scheduler...")
        cleanup_scheduler.start()
        logger.info("Cleanup scheduler started successfully")

        logger.info("Starting billing scheduler...")
        billing_scheduler.start()
        logger.info("Billing scheduler started successfully")
    else:
        logger.info("Test environment detected - skipping scheduler startup")


@app.on_event("shutdown")
async def shutdown_event():
    """アプリケーション終了時の処理"""
    logger.info("Shutting down calendar sync scheduler...")
    calendar_sync_scheduler.shutdown()
    logger.info("Calendar sync scheduler stopped successfully")

    logger.info("Shutting down cleanup scheduler...")
    cleanup_scheduler.shutdown()
    logger.info("Cleanup scheduler stopped successfully")

    logger.info("Shutting down billing scheduler...")
    billing_scheduler.shutdown()
    logger.info("Billing scheduler stopped successfully")

# 環境に応じてCORS設定を変更
is_production = os.getenv("ENVIRONMENT") == "production"

if is_production:
    # 本番環境: 必要最小限のオリジン・メソッド・ヘッダーのみ許可
    allowed_origins = [
        "https://keikakun-front.vercel.app",
        "https://www.keikakun.com",
        "https://api.keikakun.com",  # サブドメイン構成のため追加
    ]
    allowed_methods = ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"]
    allowed_headers = [
        "Content-Type",
        "Authorization",
        "X-Requested-With",
        "Accept",
        "X-CSRF-Token",  # CSRF保護用ヘッダー
    ]
else:
    # 開発環境: localhost + 本番確認用
    allowed_origins = [
        "http://localhost:3000",
        "https://keikakun-front.vercel.app",  # 開発環境でも本番確認用
    ]
    allowed_methods = ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"]
    allowed_headers = [
        "Content-Type",
        "Authorization",
        "X-Requested-With",
        "Accept",
        "X-CSRF-Token",  # CSRF保護用ヘッダー
    ]

# CORSミドルウェアの設定
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,  # Cookie送信のために必要
    allow_methods=allowed_methods,
    allow_headers=allowed_headers,
)


@app.get("/")
async def read_root():
    return {"message": "Welcome to the Keikakun API!"}


app.include_router(api_router, prefix="/api/v1")


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)