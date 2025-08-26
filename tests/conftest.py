# tests/conftest.py (pytest-asyncio構成)
import asyncio
import os
import sys
from typing import AsyncGenerator, Generator, Optional

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    create_async_engine,
)

# --- パスの設定 ---
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.core.security import get_password_hash
from app.main import app
from app.api.deps import get_db as get_async_db, get_current_user
from app.models.staff import Staff
from app.models.enums import StaffRole


# --- データベースフィクスチャ ---

@pytest_asyncio.fixture(scope="session")
async def engine() -> AsyncGenerator[AsyncEngine, None]:
    DATABASE_URL = os.getenv("DATABASE_URL")
    if not DATABASE_URL:
        raise ValueError("DATABASE_URL environment variable is not set for tests")

    if "?sslmode" in DATABASE_URL:
        DATABASE_URL = DATABASE_URL.split("?")[0]

    # poolclass=StaticPool を削除し、デフォルトのプールを使用
    async_engine = create_async_engine(DATABASE_URL)
    yield async_engine
    await async_engine.dispose()

@pytest_asyncio.fixture(scope="function")
async def db_session(engine: AsyncEngine) -> AsyncGenerator[AsyncSession, None]:
    # engine.connect() を使うことで、トランザクション管理をより明示的に行う
    async with engine.connect() as connection:
        # トランザクションを開始
        async with connection.begin() as transaction:
            # セッションを作成
            session = AsyncSession(bind=connection, expire_on_commit=False)
            yield session
            # テスト終了後、必ずロールバックする
            await transaction.rollback()


# --- APIクライアントとファクトリ ---

@pytest_asyncio.fixture(scope="function")
async def async_client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    def override_get_async_db() -> Generator:
        yield db_session
    app.dependency_overrides[get_async_db] = override_get_async_db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client
    del app.dependency_overrides[get_async_db]


@pytest_asyncio.fixture
async def service_admin_user_factory(db_session: AsyncSession):
    async def _create_user(
        name: str = "テスト管理者",
        email: str = "admin@example.com",
        password: str = "a-very-secure-password",
        role: StaffRole = StaffRole.owner,
        session: Optional[AsyncSession] = None,
    ) -> Staff:
        active_session = session or db_session
        new_user = Staff(
            name=name,
            email=email,
            hashed_password=get_password_hash(password),
            role=role,
        )
        active_session.add(new_user)
        await active_session.flush()
        await active_session.refresh(new_user)
        return new_user
    yield _create_user


@pytest_asyncio.fixture
async def test_admin_user(service_admin_user_factory):
    return await service_admin_user_factory(email="me@example.com", name="MySelf")


@pytest.fixture
def mock_current_user(request):
    user_fixture_name = request.param
    user = request.getfixturevalue(user_fixture_name)
    def override_get_current_user():
        return user
    app.dependency_overrides[get_current_user] = override_get_current_user
    yield user
    del app.dependency_overrides[get_current_user]