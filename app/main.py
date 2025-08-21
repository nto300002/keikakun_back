from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import AsyncSession
import uvicorn

from app.db.session import AsyncSessionLocal
from app.api.v1.endpoints import debug

app = FastAPI()

# CORSミドルウェアの設定
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "*"],  # フロントエンドのオリジンと、一旦すべてのオリジンを許可
    allow_credentials=True,
    allow_methods=["*"],  # すべてのメソッドを許可
    allow_headers=["*"],  # すべてのヘッダーを許可
)

async def get_async_db() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        yield session

@app.get("/")
async def read_root():
    return {"message": "Welcome to the Keikakun API!"}

app.include_router(debug.router, prefix="/api/v1/debug", tags=["debug"])

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)
