from fastapi import FastAPI, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import uvicorn

from app.db.session import SessionLocal

app = FastAPI()

async def get_db() -> AsyncSession:
    async with SessionLocal() as session:
        yield session

@app.get("/")
async def read_root():
    return {"message": "Welcome to the Bookstore API!"}

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)
