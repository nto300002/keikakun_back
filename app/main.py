from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
import uvicorn
import logging
import sys
import atexit

from app.core.limiter import limiter  # 新しいファイルからインポート
from app.core.config import settings # settingsをインポート
from app.api.v1.api import api_router
from app.scheduler.calendar_sync_scheduler import calendar_sync_scheduler

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


@app.on_event("startup")
async def startup_event():
    """アプリケーション起動時の処理"""
    logger.info("Starting calendar sync scheduler...")
    calendar_sync_scheduler.start()
    logger.info("Calendar sync scheduler started successfully")


@app.on_event("shutdown")
async def shutdown_event():
    """アプリケーション終了時の処理"""
    logger.info("Shutting down calendar sync scheduler...")
    calendar_sync_scheduler.shutdown()
    logger.info("Calendar sync scheduler stopped successfully")

# CORSミドルウェアの設定
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "https://keikakun-front.vercel.app", "https://www.keikakun.com"],  # フロントエンドのオリジンと、一旦すべてのオリジンを許可
    allow_credentials=True,
    allow_methods=["*"],  # すべてのメソッドを許可
    allow_headers=["*"],  # すべてのヘッダーを許可
)


@app.get("/")
async def read_root():
    return {"message": "Welcome to the Keikakun API!"}


app.include_router(api_router, prefix="/api/v1")


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)