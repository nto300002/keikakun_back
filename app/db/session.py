import os
import dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.orm import declarative_base

dotenv.load_dotenv()

# For asynchronous operations
ASYNC_DATABASE_URL = os.getenv("DATABASE_URL")
if not ASYNC_DATABASE_URL:
    raise ValueError("No DATABASE_URL environment variable set for async connection")

# For synchronous operations
SYNC_DATABASE_URL = ASYNC_DATABASE_URL.replace("+psycopg", "").replace("+asyncpg", "")

async_engine = create_async_engine(
    ASYNC_DATABASE_URL,
    pool_size=20,           # 同時接続数を増やす
    max_overflow=30,        # プールサイズを超えた場合の追加接続数
    pool_pre_ping=True,     # 接続の有効性を事前確認
    pool_recycle=3600,      # 1時間後に接続を再利用
    echo=False,             # 本番環境ではSQLログを無効化
)
AsyncSessionLocal = async_sessionmaker(autocommit=False, autoflush=False, bind=async_engine)

sync_engine = create_engine(
    SYNC_DATABASE_URL,
    pool_size=20,
    max_overflow=30,
    pool_pre_ping=True,
    pool_recycle=3600,
    echo=False,
)
SyncSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=sync_engine)

Base = declarative_base()

async def get_db():
    async with AsyncSessionLocal() as session:
        yield session
