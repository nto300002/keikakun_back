from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
import uvicorn

from app.core.limiter import limiter  # 新しいファイルからインポート
from app.api.v1.endpoints import (
    auths,
    staffs,
    offices,
    office_staff,
)

app = FastAPI()
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

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


# APIルーターの登録
app.include_router(auths.router, prefix="/api/v1/auth", tags=["auth"])
app.include_router(staffs.router, prefix="/api/v1/staffs", tags=["staffs"])
app.include_router(offices.router, prefix="/api/v1/offices", tags=["offices"])
app.include_router(office_staff.router, prefix="/api/v1/staff", tags=["staff-office"])


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)