import os
import dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.orm import declarative_base

dotenv.load_dotenv()


def _to_async_database_url(database_url: str) -> str:
    if database_url.startswith("postgresql+psycopg://"):
        return database_url
    if database_url.startswith("postgresql+asyncpg://"):
        return database_url.replace("postgresql+asyncpg://", "postgresql+psycopg://", 1)
    if database_url.startswith("postgresql://"):
        return database_url.replace("postgresql://", "postgresql+psycopg://", 1)
    return database_url


def _to_sync_database_url(database_url: str) -> str:
    if database_url.startswith("postgresql+asyncpg://"):
        return database_url.replace("postgresql+asyncpg://", "postgresql+psycopg://", 1)
    return database_url


# For asynchronous operations
# テスト実行時のみTEST_DATABASE_URLを使用、それ以外はDATABASE_URLを使用
if os.getenv("TESTING") == "1":
    ASYNC_DATABASE_URL = os.getenv("TEST_DATABASE_URL")
    if not ASYNC_DATABASE_URL:
        raise ValueError("TEST_DATABASE_URL environment variable is not set for test environment")
else:
    ASYNC_DATABASE_URL = os.getenv("DATABASE_URL")
    if not ASYNC_DATABASE_URL:
        raise ValueError("DATABASE_URL environment variable is not set")

ASYNC_DATABASE_URL = _to_async_database_url(ASYNC_DATABASE_URL)

# For synchronous operations
SYNC_DATABASE_URL = _to_sync_database_url(ASYNC_DATABASE_URL)

async_engine = create_async_engine(
    ASYNC_DATABASE_URL,
    pool_size=20,           # 同時接続数を増やす
    max_overflow=30,        # プールサイズを超えた場合の追加接続数
    pool_pre_ping=True,     # 接続の有効性を事前確認
    pool_recycle=300,       # 5分後に接続を再利用（Neon auto-suspendに対応）
    echo=False,             # 本番環境ではSQLログを無効化
)
AsyncSessionLocal = async_sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=async_engine,
    expire_on_commit=False  # commit後も属性を維持（MissingGreenletエラー回避）
)
# Alias for backward compatibility
async_session_maker = AsyncSessionLocal

sync_engine = create_engine(
    SYNC_DATABASE_URL,
    pool_size=20,
    max_overflow=30,
    pool_pre_ping=True,
    pool_recycle=300,  # 5分後に接続を再利用（Neon auto-suspendに対応）
    echo=False,
)
SyncSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=sync_engine)

Base = declarative_base()

async def get_db():
    async with AsyncSessionLocal() as session:
        yield session
