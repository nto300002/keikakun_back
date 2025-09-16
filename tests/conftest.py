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
from app.models.office import Office, OfficeStaff
from app.models.enums import StaffRole, OfficeType


# --- データベースフィクスチャ ---

@pytest_asyncio.fixture(scope="session")
async def engine() -> AsyncGenerator[AsyncEngine, None]:
    DATABASE_URL = os.getenv("TEST_DATABASE_URL")
    if not DATABASE_URL:
        raise ValueError("DATABASE_URL environment variable is not set for tests")

    if "?sslmode" in DATABASE_URL:
        DATABASE_URL = DATABASE_URL.split("?")[0]

    # execution_options を追加してバルクインサートを無効化
    execution_options = {"insertmanyvalues_page_size": 1}
    async_engine = create_async_engine(
        DATABASE_URL,
        execution_options=execution_options
    )
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
    """
    Create a new FastAPI TestClient that uses the `db_session` fixture to override
    the `get_async_db` dependency that is injected into routes.
    """

    def override_get_async_db() -> Generator:
        yield db_session

    app.dependency_overrides[get_async_db] = override_get_async_db

    # Use https scheme to avoid HTTPSRedirectMiddleware causing 307 redirects in tests
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="https://test"
    ) as client:
        yield client

    # Clean up dependency overrides
    del app.dependency_overrides[get_async_db]


@pytest_asyncio.fixture
async def service_admin_user_factory(db_session: AsyncSession):
    async def _create_user(
        name: str = "テスト管理者",
        email: str = "admin@example.com",
        password: str = "a-very-secure-password",
        role: StaffRole = StaffRole.owner,
        is_email_verified: bool = True,
        is_mfa_enabled: bool = False,
        session: Optional[AsyncSession] = None,
    ) -> Staff:
        active_session = session or db_session
        new_user = Staff(
            name=name,
            email=email,
            hashed_password=get_password_hash(password),
            role=role,
            is_email_verified=is_email_verified,
            is_mfa_enabled=is_mfa_enabled,
        )
        active_session.add(new_user)
        await active_session.flush()
        await active_session.refresh(new_user)
        return new_user
    yield _create_user


@pytest_asyncio.fixture
async def test_admin_user(service_admin_user_factory):
    return await service_admin_user_factory(email="me@example.com", name="MySelf")


@pytest_asyncio.fixture
async def employee_user_factory(db_session: AsyncSession):
    """従業員ロールのユーザーを作成するFactory"""
    async def _create_user(
        name: str = "テスト従業員",
        email: str = "employee@example.com",
        password: str = "a-very-secure-password",
        role: StaffRole = StaffRole.employee,
        is_email_verified: bool = True,
        is_mfa_enabled: bool = False,
        session: Optional[AsyncSession] = None,
    ) -> Staff:
        active_session = session or db_session
        new_user = Staff(
            name=name,
            email=email,
            hashed_password=get_password_hash(password),
            role=role,
            is_email_verified=is_email_verified,
            is_mfa_enabled=is_mfa_enabled,
        )
        active_session.add(new_user)
        await active_session.flush()
        await active_session.refresh(new_user)
        return new_user
    yield _create_user


@pytest_asyncio.fixture
async def manager_user_factory(db_session: AsyncSession):
    """マネージャーロールのユーザーを作成するFactory"""
    async def _create_user(
        name: str = "テストマネージャー",
        email: str = "manager@example.com",
        password: str = "a-very-secure-password",
        role: StaffRole = StaffRole.manager,
        is_email_verified: bool = True,
        is_mfa_enabled: bool = False,
        session: Optional[AsyncSession] = None,
    ) -> Staff:
        active_session = session or db_session
        new_user = Staff(
            name=name,
            email=email,
            hashed_password=get_password_hash(password),
            role=role,
            is_email_verified=is_email_verified,
            is_mfa_enabled=is_mfa_enabled,
        )
        active_session.add(new_user)
        await active_session.flush()
        await active_session.refresh(new_user)
        return new_user
    yield _create_user


@pytest_asyncio.fixture
async def office_factory(db_session: AsyncSession):
    """事業所を作成するFactory"""
    async def _create_office(
        creator: Staff, # 作成者を追加
        name: str = "テスト事業所",
        type: OfficeType = OfficeType.type_A_office,
        session: Optional[AsyncSession] = None,
    ) -> Office:
        active_session = session or db_session
        new_office = Office(
            name=name,
            type=type,
            created_by=creator.id, # created_by を設定
            last_modified_by=creator.id, # last_modified_by を設定
        )
        active_session.add(new_office)
        await active_session.flush()
        await active_session.refresh(new_office)
        return new_office
    yield _create_office


@pytest.fixture
def mock_current_user(request):
    user_fixture_name = request.param
    user = request.getfixturevalue(user_fixture_name)
    def override_get_current_user():
        return user
    app.dependency_overrides[get_current_user] = override_get_current_user
    yield user
    del app.dependency_overrides[get_current_user]


# --- グローバルなテスト設定 ---

from app.core.limiter import limiter

@pytest.fixture(autouse=True)
def reset_limiter_state():
    """各テストの実行前にレートリミッターの状態をリセットする"""
    limiter.reset()
