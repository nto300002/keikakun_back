from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import AsyncSession
import uvicorn

from app.db.session import AsyncSessionLocal
from app.api.v1.endpoints import (
    auths,
    staffs,
    offices,
    # service_recipient, # コメントアウトされたままのものは一旦そのままにします
    # support_plan,
    # dashboard,
)

app = FastAPI()

# CORSミドルウェアの設定
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "*"],  # フロントエンドのオリジンと、一旦すべてのオリジンを許可
    allow_credentials=True,
    allow_methods=["*"],  # すべてのメソッドを許可
    allow_headers=["*"],  # すべてのヘッダーを許可
)


@app.get("/")
async def read_root():
    return {"message": "Welcome to the Keikakun API!"}


# APIルーターの登録
app.include_router(auths.router, prefix="/api/v1/auths", tags=["auths"])
app.include_router(staffs.router, prefix="/api/v1/staffs", tags=["staffs"])
app.include_router(offices.router, prefix="/api/v1/offices", tags=["offices"])
# app.include_router(
#     service_recipient.router,
#     prefix="/api/v1/service-recipient",
#     tags=["service-recipient"],
# )
# app.include_router(
#     support_plan.router, prefix="/api/v1/support-plan", tags=["support-plan"]
# )
# app.include_router(dashboard.router, prefix="/api/v1/dashboard", tags=["dashboard"])


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)