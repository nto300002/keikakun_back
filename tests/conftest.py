# tests/conftest.py (pytest-asyncio構成)
import asyncio
import os
import sys
from typing import AsyncGenerator, Generator, Optional
import uuid
from datetime import timedelta

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text, event
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    create_async_engine,
)
from sqlalchemy.orm import sessionmaker

# --- パスの設定 ---
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.core.security import get_password_hash, create_access_token
from app.core.config import settings
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

    async_engine = create_async_engine(DATABASE_URL)
    yield async_engine
    await async_engine.dispose()

@pytest_asyncio.fixture(scope="function")
async def db_session(engine: AsyncEngine) -> AsyncGenerator[AsyncSession, None]:
    """
    テスト用のDBセッションフィクスチャ。
    ネストされたトランザクション（セーブポイント）を利用して、テスト終了時に
    全ての変更がロールバックされることを保証する。
    """
    async with engine.connect() as connection:
        await connection.begin()
        await connection.begin_nested()
        
        async_session_factory = sessionmaker(
            bind=connection,
            class_=AsyncSession,
            expire_on_commit=False
        )
        session = async_session_factory()

        @event.listens_for(session.sync_session, "after_transaction_end")
        def end_savepoint(session, transaction):
            if session.is_active and not session.in_nested_transaction():
                session.begin_nested()

        yield session

        await session.close()
        await connection.rollback()


# --- APIクライアントとファクトリ ---

@pytest_asyncio.fixture(scope="function")
async def async_client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    def override_get_async_db() -> Generator:
        yield db_session

    app.dependency_overrides[get_async_db] = override_get_async_db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="https://test") as client:
        try:
            yield client
        finally:
            # tolerate either override key (avoid KeyError when function object differs)
            app.dependency_overrides.pop(get_async_db, None)
            #app.dependency_overrides.pop(get_db, None)


@pytest_asyncio.fixture
async def service_admin_user_factory(db_session: AsyncSession):
    async def _create_user(
        name: str = "テスト管理者",
        email: str = f"admin_{uuid.uuid4().hex}@example.com",
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
    return await service_admin_user_factory()


@pytest_asyncio.fixture
async def employee_user_factory(db_session: AsyncSession, office_factory):
    """従業員ロールのユーザーを作成するFactory（事業所に関連付け）"""
    async def _create_user(
        name: str = "テスト従業員",
        email: str = f"employee_{uuid.uuid4().hex}@example.com",
        password: str = "a-very-secure-password",
        role: StaffRole = StaffRole.employee,
        is_email_verified: bool = True,
        is_mfa_enabled: bool = False,
        session: Optional[AsyncSession] = None,
        office: Optional[Office] = None,  # 事業所を外部から受け取れるようにする
        with_office: bool = True,
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

        # 事業所に関連付け
        if with_office:
            target_office = office
            if not target_office:
                target_office = await office_factory(creator=new_user, session=active_session)
            
            from app.models.office import OfficeStaff
            association = OfficeStaff(
                staff_id=new_user.id,
                office_id=target_office.id,
                is_primary=True
            )
            active_session.add(association)
            await active_session.flush()

        await active_session.refresh(new_user)
        return new_user
    yield _create_user


@pytest_asyncio.fixture
async def manager_user_factory(db_session: AsyncSession, office_factory):
    """マネージャーロールのユーザーを作成するFactory（事業所に関連付け）"""
    async def _create_user(
        name: str = "テストマネージャー",
        email: str = f"manager_{uuid.uuid4().hex}@example.com",
        password: str = "a-very-secure-password",
        role: StaffRole = StaffRole.manager,
        is_email_verified: bool = True,
        is_mfa_enabled: bool = False,
        session: Optional[AsyncSession] = None,
        office: Optional[Office] = None,  # 事業所を外部から受け取れるようにする
        with_office: bool = True,
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

        # 事業所に関連付け
        if with_office:
            target_office = office
            if not target_office:
                target_office = await office_factory(creator=new_user, session=active_session)

            from app.models.office import OfficeStaff
            association = OfficeStaff(
                staff_id=new_user.id,
                office_id=target_office.id,
                is_primary=True
            )
            active_session.add(association)
            await active_session.flush()

        await active_session.refresh(new_user)
        return new_user
    yield _create_user


@pytest_asyncio.fixture
async def office_factory(db_session: AsyncSession):
    """事業所を作成するFactory"""
    async def _create_office(
        creator: Staff,
        name: str = "テスト事業所",
        type: OfficeType = OfficeType.type_A_office,
        session: Optional[AsyncSession] = None,
    ) -> Office:
        active_session = session or db_session
        new_office = Office(
            name=name,
            type=type,
            created_by=creator.id,
            last_modified_by=creator.id,
        )
        active_session.add(new_office)
        await active_session.flush()
        await active_session.refresh(new_office)
        return new_office
    yield _create_office


@pytest_asyncio.fixture
async def normal_user_token_headers(employee_user_factory, db_session: AsyncSession) -> dict[str, str]:
    employee = await employee_user_factory()
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    # get_current_user は token.sub を UUID として期待するため user.id を subject に渡す
    access_token = create_access_token(str(employee.id), access_token_expires)

    # get_current_userをオーバーライドして、作成したユーザーを返す
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload

    async def override_get_current_user():
        stmt = select(Staff).where(Staff.id == employee.id).options(selectinload(Staff.office_associations))
        result = await db_session.execute(stmt)
        user = result.scalars().first()
        return user

    app.dependency_overrides[get_current_user] = override_get_current_user

    return {"Authorization": f"Bearer {access_token}"}


@pytest_asyncio.fixture
async def manager_user_token_headers(manager_user_factory, db_session: AsyncSession) -> dict[str, str]:
    manager = await manager_user_factory()
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    # get_current_user は token.sub を UUID として期待するため user.id を subject に渡す
    access_token = create_access_token(str(manager.id), access_token_expires)

    # get_current_userをオーバーライドして、作成したユーザーを返す
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload

    async def override_get_current_user():
        stmt = select(Staff).where(Staff.id == manager.id).options(selectinload(Staff.office_associations))
        result = await db_session.execute(stmt)
        user = result.scalars().first()
        return user

    app.dependency_overrides[get_current_user] = override_get_current_user

    return {"Authorization": f"Bearer {access_token}"}


# --- グローバルなテスト設定 ---

from app.core.limiter import limiter

@pytest.fixture(autouse=True)
def reset_limiter_state():
    """各テストの実行前にレートリミッターの状態をリセットする"""
    limiter.reset()


# --- mock_current_user フィクスチャ ---
@pytest.fixture
def mock_current_user(request):
    """
    現在のユーザーをモックするフィクスチャ。
    parametrizeでフィクスチャ名を指定することで、そのフィクスチャの結果を返す。

    使用例:
    @pytest.mark.parametrize("mock_current_user", ["owner_user_without_office"], indirect=True)
    async def test_something(mock_current_user: Staff):
        # mock_current_userはowner_user_without_officeの値になる
    """
    if hasattr(request, 'param'):
        # parametrizeで指定されたフィクスチャの名前を取得
        fixture_name = request.param
        # そのフィクスチャの値を取得して返す
        user = request.getfixturevalue(fixture_name)

        # deps.get_current_userをモックするため、appのdependency_overridesを使う
        from app.main import app

        async def override_get_current_user():
            return user

        app.dependency_overrides[get_current_user] = override_get_current_user

        # テスト終了後にクリーンアップ
        def cleanup():
            if get_current_user in app.dependency_overrides:
                del app.dependency_overrides[get_current_user]

        request.addfinalizer(cleanup)
        return user
    return None
