# tests/conftest.py (pytest-asyncio構成)
import asyncio
import os
import sys
from typing import AsyncGenerator, Generator, Optional
import uuid
from datetime import timedelta
import logging

# テスト環境であることを示すフラグを設定（スケジューラーなどを無効化するため）
os.environ.setdefault("TESTING", "1")

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

# ロガーの設定 - テスト実行時のログ出力を抑制
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.WARNING)  # WARNING以上のみ表示

# SQLAlchemyのエンジンログを無効化
logging.getLogger('sqlalchemy.engine').setLevel(logging.WARNING)

# --- パスの設定 ---
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.core.security import get_password_hash, create_access_token
from app.core.config import settings
from app.main import app
from app.api.deps import get_db, get_current_user
from app.models.staff import Staff
from app.models.office import Office, OfficeStaff
from app.models.enums import StaffRole, OfficeType, GenderType


# --- データベースクリーンアップ（セッション全体） ---

async def safe_cleanup_test_database(engine: AsyncEngine):
    """
    ファクトリ関数で生成されたテストデータのみを安全にクリーンアップ

    Args:
        engine: データベースエンジン
    """
    from tests.utils.safe_cleanup import SafeTestDataCleanup
    verbose_cleanup = os.getenv("PYTEST_VERBOSE_CLEANUP") == "1"

    # テスト環境であることを確認
    if not SafeTestDataCleanup.verify_test_environment():
        logger.warning("Not in test environment - skipping cleanup")
        return

    async with engine.connect() as connection:
        transaction = await connection.begin()

        # AsyncSessionを作成してクリーンアップ実行
        async_session_factory = sessionmaker(
            bind=connection,
            class_=AsyncSession,
            expire_on_commit=False
        )
        session = async_session_factory()

        try:
            result = await SafeTestDataCleanup.delete_factory_generated_data(session)
            # トランザクションをコミット（重要！）
            await transaction.commit()

            if result:
                total = sum(result.values())
                if verbose_cleanup:
                    logger.info(
                        "Deleted %s factory-generated records: %s",
                        total,
                        dict(sorted(result.items(), key=lambda x: x[1], reverse=True)),
                    )
                else:
                    logger.info("Deleted %s factory-generated records", total)
            elif verbose_cleanup:
                logger.info("No factory-generated data found")
        except Exception as e:
            logger.error("Safe cleanup failed: %s", e)
            await transaction.rollback()
            raise
        finally:
            await session.close()


@pytest_asyncio.fixture(scope="session", autouse=True)
async def cleanup_database_session():
    """
    全テストセッションの前後でファクトリ生成データをクリーンアップ

    autouse=True により、pytest実行時に自動的に実行される

    安全性:
    - ファクトリ関数で生成されたデータのみを削除
    - TEST_DATABASE_URLが設定されている場合のみ実行
    - 本番環境では実行されない
    """
    # テスト実行前: ファクトリ生成データをクリーンアップ
    TEST_DATABASE_URL_VAR = os.getenv("TEST_DATABASE_URL")
    DATABASE_URL_VAR = os.getenv("DATABASE_URL")
    DATABASE_URL = TEST_DATABASE_URL_VAR or DATABASE_URL_VAR

    if DATABASE_URL:
        if "?sslmode" in DATABASE_URL:
            DATABASE_URL = DATABASE_URL.split("?")[0]

        # データベース接続情報をログ出力（デバッグ用）
        def get_db_branch_name(url: str) -> str:
            """URLからデータベースブランチ名を抽出"""
            if "keikakun_dev_test" in url:
                return "dev_test"
            elif "keikakun_dev" in url:
                return "dev"
            elif "keikakun_prod_test" in url:
                return "prod_test"
            elif "keikakun_prod" in url:
                return "prod"
            else:
                return "unknown"

        branch_name = get_db_branch_name(DATABASE_URL)
        if os.getenv("PYTEST_VERBOSE_CLEANUP") == "1":
            logger.info(
                "Test DB: using=%s branch=%s test_url_set=%s database_url_set=%s",
                "TEST_DATABASE_URL" if TEST_DATABASE_URL_VAR else "DATABASE_URL",
                branch_name,
                bool(TEST_DATABASE_URL_VAR),
                bool(DATABASE_URL_VAR),
            )
        elif not TEST_DATABASE_URL_VAR:
            logger.warning("TEST_DATABASE_URL not set; falling back to DATABASE_URL for tests")

        temp_engine = create_async_engine(DATABASE_URL, echo=False)

        try:
            await safe_cleanup_test_database(temp_engine)
        except Exception as e:
            logger.warning("Pre-test safe cleanup failed: %s", e)
        finally:
            await temp_engine.dispose()

    # テストを実行
    yield

    # テスト実行後: ファクトリ生成データをクリーンアップ
    if DATABASE_URL:
        temp_engine = create_async_engine(DATABASE_URL, echo=False)

        try:
            await safe_cleanup_test_database(temp_engine)
        except Exception as e:
            logger.warning("Post-test safe cleanup failed: %s", e)
        finally:
            await temp_engine.dispose()


# --- データベースフィクスチャ ---

@pytest_asyncio.fixture(scope="session")
async def engine() -> AsyncGenerator[AsyncEngine, None]:
    DATABASE_URL = os.getenv("TEST_DATABASE_URL")

    # TEST_DATABASE_URLが設定されていない場合、DATABASE_URLをフォールバック
    if not DATABASE_URL:
        DATABASE_URL = os.getenv("DATABASE_URL")

    if not DATABASE_URL:
        raise ValueError("Neither TEST_DATABASE_URL nor DATABASE_URL environment variable is set for tests")

    if "?sslmode" in DATABASE_URL:
        DATABASE_URL = DATABASE_URL.split("?")[0]

    async_engine = create_async_engine(
        DATABASE_URL,
        pool_size=10,           # 接続プールサイズを減らす
        max_overflow=20,        # プールサイズを超えた場合の追加接続数
        pool_pre_ping=True,     # 接続の有効性を事前確認
        pool_recycle=300,       # 5分後に接続をリサイクル（タイムアウト対策）
        pool_timeout=30,        # 接続取得のタイムアウト（秒）
        echo=False,             # SQLログを無効化（テスト時のノイズ削減）
        pool_use_lifo=True,     # LIFOで新しい接続を優先的に使用
    )
    yield async_engine
    await async_engine.dispose()

@pytest_asyncio.fixture(scope="function")
async def db_session(engine: AsyncEngine) -> AsyncGenerator[AsyncSession, None]:
    """
    テスト用のDBセッションフィクスチャ。
    ネストされたトランザクション（セーブポイント）を利用して、テスト終了時に
    全ての変更がロールバックされることを保証する。

    重要: このセッションでは commit() ではなく flush() を使用すること。
    commit() を呼ぶとトランザクションがコミットされ、ロールバックできなくなる。
    """
    async with engine.connect() as connection:
        try:
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

        except Exception as e:
            logger.error(f"Database session error: {e}")
            raise
        finally:
            # セッションのクリーンアップ
            try:
                await session.close()
            except Exception as e:
                logger.warning(f"Error closing session: {e}")

            # 接続のロールバック（テストデータを確実に削除）
            try:
                await connection.rollback()
                logger.debug("Transaction rolled back successfully")
            except Exception as e:
                logger.warning(f"Error rolling back connection: {e}")


# --- APIクライアントとファクトリ ---

@pytest_asyncio.fixture(scope="function")
async def async_client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="https://test", follow_redirects=True) as client:
        try:
            yield client
        finally:
            # tolerate either override key (avoid KeyError when function object differs)
            app.dependency_overrides.pop(get_db, None)


@pytest_asyncio.fixture
async def csrf_headers(async_client: AsyncClient) -> dict[str, str]:
    """Return headers for cookie-authenticated state-changing test requests."""
    response = await async_client.get("/api/v1/csrf-token")
    return {"X-CSRF-Token": response.json()["csrf_token"]}


@pytest_asyncio.fixture
async def service_admin_user_factory(db_session: AsyncSession):
    counter = {"count": 0}  # ローカルカウンター

    async def _create_user(
        name: Optional[str] = None,  # DEPRECATED: 後方互換性のため残す
        first_name: str = "管理者",
        last_name: str = "テスト",
        email: Optional[str] = None,
        password: str = "a-very-secure-password",
        role: StaffRole = StaffRole.owner,
        is_email_verified: bool = True,
        is_mfa_enabled: bool = False,
        session: Optional[AsyncSession] = None,
        is_test_data: bool = True,
    ) -> Staff:
        from sqlalchemy import select
        from sqlalchemy.orm import selectinload
        import time

        # 後方互換性: nameが指定されている場合は分割
        if name is not None:
            parts = name.split(maxsplit=1)
            if len(parts) == 2:
                last_name, first_name = parts
            else:
                first_name = parts[0]
                last_name = "テスト"

        # full_nameを生成
        full_name = f"{last_name} {first_name}"

        # デフォルトのメールアドレスを生成（UUID + タイムスタンプ + カウンター）
        if email is None:
            counter["count"] += 1
            timestamp = int(time.time() * 1000000)  # マイクロ秒単位
            email = f"admin_{uuid.uuid4().hex}_{timestamp}_{counter['count']}@example.com"

        active_session = session or db_session
        new_user = Staff(
            first_name=first_name,
            last_name=last_name,
            full_name=full_name,
            email=email,
            hashed_password=get_password_hash(password),
            role=role,
            is_email_verified=is_email_verified,
            is_mfa_enabled=is_mfa_enabled,
            is_test_data=is_test_data,
        )
        active_session.add(new_user)
        await active_session.flush()

        # リレーションシップをeager loadしてからrefresh
        stmt = select(Staff).where(Staff.id == new_user.id).options(
            selectinload(Staff.office_associations).selectinload(OfficeStaff.office)
        )
        result = await active_session.execute(stmt)
        new_user = result.scalars().first()

        return new_user
    yield _create_user


@pytest_asyncio.fixture
async def test_admin_user(service_admin_user_factory, db_session: AsyncSession):
    """
    管理者ユーザーを作成し、get_current_userをオーバーライドするフィクスチャ

    このフィクスチャは認証が必要なAPIテストで使用できます。
    テスト関数内で個別にget_current_userをオーバーライドする場合は、
    そちらが優先されます。
    """
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload
    from app.models.office import OfficeStaff

    user = await service_admin_user_factory()

    # get_current_userをオーバーライドして、作成したユーザーを返す
    async def override_get_current_user():
        stmt = select(Staff).where(Staff.id == user.id).options(
            selectinload(Staff.office_associations).selectinload(OfficeStaff.office)
        ).execution_options(populate_existing=True)
        result = await db_session.execute(stmt)
        return result.scalars().first()

    app.dependency_overrides[get_current_user] = override_get_current_user

    try:
        yield user
    finally:
        # クリーンアップ: オーバーライドを削除
        app.dependency_overrides.pop(get_current_user, None)


@pytest_asyncio.fixture
async def employee_user_factory(db_session: AsyncSession, office_factory):
    """従業員ロールのユーザーを作成するFactory（事業所に関連付け）"""
    counter = {"count": 0}  # ローカルカウンター

    async def _create_user(
        name: Optional[str] = None,  # DEPRECATED: 後方互換性のため残す
        first_name: str = "従業員",
        last_name: str = "テスト",
        email: Optional[str] = None,
        password: str = "a-very-secure-password",
        role: StaffRole = StaffRole.employee,
        is_email_verified: bool = True,
        is_mfa_enabled: bool = False,
        session: Optional[AsyncSession] = None,
        office: Optional[Office] = None,  # 事業所を外部から受け取れるようにする
        with_office: bool = True,
        is_test_data: bool = True,
    ) -> Staff:
        from sqlalchemy import select
        from sqlalchemy.orm import selectinload
        from app.models.office import OfficeStaff
        import time

        # 後方互換性: nameが指定されている場合は分割
        if name is not None:
            parts = name.split(maxsplit=1)
            if len(parts) == 2:
                last_name, first_name = parts
            else:
                first_name = parts[0]
                last_name = "テスト"

        # full_nameを生成
        full_name = f"{last_name} {first_name}"

        # デフォルトのメールアドレスを生成（UUID + タイムスタンプ + カウンター）
        if email is None:
            counter["count"] += 1
            timestamp = int(time.time() * 1000000)  # マイクロ秒単位
            email = f"employee_{uuid.uuid4().hex}_{timestamp}_{counter['count']}@example.com"

        active_session = session or db_session
        new_user = Staff(
            first_name=first_name,
            last_name=last_name,
            full_name=full_name,
            email=email,
            hashed_password=get_password_hash(password),
            role=role,
            is_email_verified=is_email_verified,
            is_mfa_enabled=is_mfa_enabled,
            is_test_data=is_test_data,
        )
        active_session.add(new_user)
        await active_session.flush()

        # 事業所に関連付け
        if with_office:
            target_office = office
            if not target_office:
                target_office = await office_factory(creator=new_user, session=active_session, is_test_data=is_test_data)

            association = OfficeStaff(
                staff_id=new_user.id,
                office_id=target_office.id,
                is_primary=True,
                is_test_data=True,
            )
            active_session.add(association)
            await active_session.flush()

        # リレーションシップをeager loadしてからrefresh
        stmt = select(Staff).where(Staff.id == new_user.id).options(
            selectinload(Staff.office_associations).selectinload(OfficeStaff.office)
        )
        result = await active_session.execute(stmt)
        new_user = result.scalars().first()

        return new_user
    yield _create_user


@pytest_asyncio.fixture
async def manager_user_factory(db_session: AsyncSession, office_factory):
    """マネージャーロールのユーザーを作成するFactory（事業所に関連付け）"""
    counter = {"count": 0}  # ローカルカウンター

    async def _create_user(
        name: Optional[str] = None,  # DEPRECATED: 後方互換性のため残す
        first_name: str = "マネージャー",
        last_name: str = "テスト",
        email: Optional[str] = None,
        password: str = "a-very-secure-password",
        role: StaffRole = StaffRole.manager,
        is_email_verified: bool = True,
        is_mfa_enabled: bool = False,
        session: Optional[AsyncSession] = None,
        office: Optional[Office] = None,  # 事業所を外部から受け取れるようにする
        with_office: bool = True,
        is_test_data: bool = True,
    ) -> Staff:
        from sqlalchemy import select
        from sqlalchemy.orm import selectinload
        from app.models.office import OfficeStaff
        import time

        # 後方互換性: nameが指定されている場合は分割
        if name is not None:
            parts = name.split(maxsplit=1)
            if len(parts) == 2:
                last_name, first_name = parts
            else:
                first_name = parts[0]
                last_name = "テスト"

        # full_nameを生成
        full_name = f"{last_name} {first_name}"

        # デフォルトのメールアドレスを生成（UUID + タイムスタンプ + カウンター）
        if email is None:
            counter["count"] += 1
            timestamp = int(time.time() * 1000000)  # マイクロ秒単位
            email = f"manager_{uuid.uuid4().hex}_{timestamp}_{counter['count']}@example.com"

        active_session = session or db_session
        new_user = Staff(
            first_name=first_name,
            last_name=last_name,
            full_name=full_name,
            email=email,
            hashed_password=get_password_hash(password),
            role=role,
            is_email_verified=is_email_verified,
            is_mfa_enabled=is_mfa_enabled,
            is_test_data=is_test_data,
        )
        active_session.add(new_user)
        await active_session.flush()

        # 事業所に関連付け
        if with_office:
            target_office = office
            if not target_office:
                target_office = await office_factory(creator=new_user, session=active_session, is_test_data=is_test_data)

            association = OfficeStaff(
                staff_id=new_user.id,
                office_id=target_office.id,
                is_primary=True,
                is_test_data=True,
            )
            active_session.add(association)
            await active_session.flush()

        # リレーションシップをeager loadしてからrefresh
        stmt = select(Staff).where(Staff.id == new_user.id).options(
            selectinload(Staff.office_associations).selectinload(OfficeStaff.office)
        )
        result = await active_session.execute(stmt)
        new_user = result.scalars().first()

        return new_user
    yield _create_user


@pytest_asyncio.fixture
async def owner_user_factory(db_session: AsyncSession, office_factory):
    """オーナーロールのユーザーを作成するFactory（事業所に関連付け）"""
    counter = {"count": 0}  # ローカルカウンター

    async def _create_user(
        name: Optional[str] = None,  # DEPRECATED: 後方互換性のため残す
        first_name: str = "オーナー",
        last_name: str = "テスト",
        email: Optional[str] = None,
        password: str = "a-very-secure-password",
        role: StaffRole = StaffRole.owner,
        is_email_verified: bool = True,
        is_mfa_enabled: bool = False,
        session: Optional[AsyncSession] = None,
        office: Optional[Office] = None,  # 事業所を外部から受け取れるようにする
        with_office: bool = True,
        is_test_data: bool = True,
    ) -> Staff:
        from sqlalchemy import select
        from sqlalchemy.orm import selectinload
        from app.models.office import OfficeStaff
        import time

        # 後方互換性: nameが指定されている場合は分割
        if name is not None:
            parts = name.split(maxsplit=1)
            if len(parts) == 2:
                last_name, first_name = parts
            else:
                first_name = parts[0]
                last_name = "テスト"

        # full_nameを生成
        full_name = f"{last_name} {first_name}"

        # デフォルトのメールアドレスを生成（UUID + タイムスタンプ + カウンター）
        if email is None:
            counter["count"] += 1
            timestamp = int(time.time() * 1000000)  # マイクロ秒単位
            email = f"owner_{uuid.uuid4().hex}_{timestamp}_{counter['count']}@example.com"

        active_session = session or db_session
        new_user = Staff(
            first_name=first_name,
            last_name=last_name,
            full_name=full_name,
            email=email,
            hashed_password=get_password_hash(password),
            role=role,
            is_email_verified=is_email_verified,
            is_mfa_enabled=is_mfa_enabled,
            is_test_data=is_test_data,
        )
        active_session.add(new_user)
        await active_session.flush()

        # 事業所に関連付け
        if with_office:
            target_office = office
            if not target_office:
                target_office = await office_factory(creator=new_user, session=active_session, is_test_data=is_test_data)

            association = OfficeStaff(
                staff_id=new_user.id,
                office_id=target_office.id,
                is_primary=True,
                is_test_data=True,
            )
            active_session.add(association)
            await active_session.flush()

        # リレーションシップをeager loadしてからrefresh
        stmt = select(Staff).where(Staff.id == new_user.id).options(
            selectinload(Staff.office_associations).selectinload(OfficeStaff.office)
        )
        result = await active_session.execute(stmt)
        new_user = result.scalars().first()

        return new_user
    yield _create_user


@pytest_asyncio.fixture
async def app_admin_user_factory(db_session: AsyncSession):
    """アプリ管理者ロールのユーザーを作成するFactory（事業所なし）"""
    counter = {"count": 0}  # ローカルカウンター

    async def _create_user(
        name: Optional[str] = None,  # DEPRECATED: 後方互換性のため残す
        first_name: str = "管理者",
        last_name: str = "アプリ",
        email: Optional[str] = None,
        password: str = "a-very-secure-password",
        role: StaffRole = StaffRole.app_admin,
        is_email_verified: bool = True,
        is_mfa_enabled: bool = False,
        session: Optional[AsyncSession] = None,
        is_test_data: bool = True,
    ) -> Staff:
        from sqlalchemy import select
        from sqlalchemy.orm import selectinload
        from app.models.office import OfficeStaff
        import time

        # 後方互換性: nameが指定されている場合は分割
        if name is not None:
            parts = name.split(maxsplit=1)
            if len(parts) == 2:
                last_name, first_name = parts
            else:
                first_name = parts[0]
                last_name = "テスト"

        # full_nameを生成
        full_name = f"{last_name} {first_name}"

        # デフォルトのメールアドレスを生成（UUID + タイムスタンプ + カウンター）
        if email is None:
            counter["count"] += 1
            timestamp = int(time.time() * 1000000)  # マイクロ秒単位
            email = f"app_admin_{uuid.uuid4().hex}_{timestamp}_{counter['count']}@example.com"

        active_session = session or db_session
        new_user = Staff(
            first_name=first_name,
            last_name=last_name,
            full_name=full_name,
            email=email,
            hashed_password=get_password_hash(password),
            role=role,
            is_email_verified=is_email_verified,
            is_mfa_enabled=is_mfa_enabled,
            is_test_data=is_test_data,
        )
        active_session.add(new_user)
        await active_session.flush()

        # app_adminは事業所に関連付けない（アプリ全体の管理者）

        # リレーションシップをeager loadしてからrefresh
        stmt = select(Staff).where(Staff.id == new_user.id).options(
            selectinload(Staff.office_associations).selectinload(OfficeStaff.office)
        )
        result = await active_session.execute(stmt)
        new_user = result.scalars().first()

        return new_user
    yield _create_user


@pytest_asyncio.fixture
async def office_factory(db_session: AsyncSession):
    """事業所を作成するFactory"""
    counter = {"count": 0}

    async def _create_office(
        creator: Optional[Staff] = None,
        name: Optional[str] = None,
        type: OfficeType = OfficeType.type_A_office,
        session: Optional[AsyncSession] = None,
        is_test_data: bool = True,
    ) -> Office:
        from sqlalchemy import select

        active_session = session or db_session
        counter["count"] += 1

        # creatorが指定されていない場合、デフォルトのスタッフを作成
        if creator is None:
            last_name = f"テスト{counter['count']}"
            first_name = "管理者"
            creator = Staff(
                first_name=first_name,
                last_name=last_name,
                full_name=f"{last_name} {first_name}",
                email=f"admin{counter['count']}@test.com",
                hashed_password=get_password_hash("password"),
                role=StaffRole.owner,
                is_email_verified=True,
                is_test_data=is_test_data,
            )
            active_session.add(creator)
            await active_session.flush()

        # nameが指定されていない場合、一意な名前を生成
        office_name = name or f"テスト事業所{counter['count']}"

        new_office = Office(
            name=office_name,
            type=type,
            created_by=creator.id,
            last_modified_by=creator.id,
            is_test_data=is_test_data,
        )
        active_session.add(new_office)
        await active_session.flush()
        await active_session.refresh(new_office)
        return new_office
    yield _create_office


@pytest_asyncio.fixture
async def staff_factory(db_session: AsyncSession):
    """スタッフを作成するFactory"""
    counter = {"count": 0}

    async def _create_staff(
        office_id: uuid.UUID,
        first_name: str = "スタッフ",
        last_name: Optional[str] = None,
        email: Optional[str] = None,
        role: StaffRole = StaffRole.employee,
        password: str = "password",
        is_email_verified: bool = True,
        session: Optional[AsyncSession] = None,
        is_test_data: bool = True,
    ) -> Staff:
        from sqlalchemy import select
        from sqlalchemy.orm import selectinload

        active_session = session or db_session
        counter["count"] += 1

        # 一意な値を生成
        staff_last_name = last_name or f"テスト{counter['count']}"
        staff_email = email or f"staff{counter['count']}@test.com"

        new_staff = Staff(
            first_name=first_name,
            last_name=staff_last_name,
            full_name=f"{staff_last_name} {first_name}",
            email=staff_email,
            hashed_password=get_password_hash(password),
            role=role,
            is_email_verified=is_email_verified,
            is_test_data=is_test_data,
        )
        active_session.add(new_staff)
        await active_session.flush()

        # OfficeStaffアソシエーションを作成
        office_staff = OfficeStaff(
            staff_id=new_staff.id,
            office_id=office_id,
            is_primary=True,
            is_test_data=True,
        )
        active_session.add(office_staff)
        await active_session.flush()

        # リレーションシップをロードして返す
        stmt = select(Staff).where(Staff.id == new_staff.id).options(
            selectinload(Staff.office_associations).selectinload(OfficeStaff.office)
        )
        result = await active_session.execute(stmt)
        staff = result.scalars().first()

        return staff
    yield _create_staff


@pytest_asyncio.fixture
async def welfare_recipient_factory(db_session: AsyncSession):
    """福祉受給者を作成するFactory"""
    from app.models.welfare_recipient import WelfareRecipient, OfficeWelfareRecipient
    from datetime import date

    counter = {"count": 0}

    async def _create_welfare_recipient(
        office_id: uuid.UUID,
        first_name: str = "太郎",
        last_name: Optional[str] = None,
        first_name_furigana: str = "たろう",
        last_name_furigana: Optional[str] = None,
        birth_day: date = date(1990, 1, 1),
        gender: GenderType = GenderType.male,
        session: Optional[AsyncSession] = None,
        is_test_data: bool = True,
    ) -> WelfareRecipient:
        active_session = session or db_session
        counter["count"] += 1

        # 一意な値を生成
        recipient_last_name = last_name or f"テスト{counter['count']}"
        recipient_last_name_furigana = last_name_furigana or f"テスト{counter['count']}"

        new_recipient = WelfareRecipient(
            first_name=first_name,
            last_name=recipient_last_name,
            first_name_furigana=first_name_furigana,
            last_name_furigana=recipient_last_name_furigana,
            birth_day=birth_day,
            gender=gender,
            is_test_data=is_test_data,
        )
        active_session.add(new_recipient)
        await active_session.flush()

        # OfficeWelfareRecipientアソシエーションを作成
        office_recipient = OfficeWelfareRecipient(
            office_id=office_id,
            welfare_recipient_id=new_recipient.id,
            is_test_data=True,
        )
        active_session.add(office_recipient)
        await active_session.flush()
        await active_session.refresh(new_recipient)

        return new_recipient
    yield _create_welfare_recipient


@pytest_asyncio.fixture
async def normal_user_token_headers(employee_user_factory, db_session: AsyncSession) -> dict[str, str]:
    employee = await employee_user_factory()
    await db_session.flush()  # Flush changes without committing (allows rollback)

    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    # get_current_user は token.sub を UUID として期待するため user.id を subject に渡す
    access_token = create_access_token(str(employee.id), access_token_expires)

    # get_current_userをオーバーライドして、作成したユーザーを返す
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload
    from app.models.office import OfficeStaff

    async def override_get_current_user():
        stmt = select(Staff).where(Staff.id == employee.id).options(
            selectinload(Staff.office_associations).selectinload(OfficeStaff.office)
        )
        result = await db_session.execute(stmt)
        user = result.scalars().first()
        return user

    app.dependency_overrides[get_current_user] = override_get_current_user

    try:
        yield {"Authorization": f"Bearer {access_token}"}
    finally:
        # Clean up the override after test
        app.dependency_overrides.pop(get_current_user, None)


@pytest_asyncio.fixture
async def manager_user_token_headers(manager_user_factory, db_session: AsyncSession) -> dict[str, str]:
    manager = await manager_user_factory()
    await db_session.flush()  # Flush changes without committing (allows rollback)

    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    # get_current_user は token.sub を UUID として期待するため user.id を subject に渡す
    access_token = create_access_token(str(manager.id), access_token_expires)

    # get_current_userをオーバーライドして、作成したユーザーを返す
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload
    from app.models.office import OfficeStaff

    async def override_get_current_user():
        stmt = select(Staff).where(Staff.id == manager.id).options(
            selectinload(Staff.office_associations).selectinload(OfficeStaff.office)
        )
        result = await db_session.execute(stmt)
        user = result.scalars().first()
        return user

    app.dependency_overrides[get_current_user] = override_get_current_user

    try:
        yield {"Authorization": f"Bearer {access_token}"}
    finally:
        # Clean up the override after test
        app.dependency_overrides.pop(get_current_user, None)


# --- グローバルなテスト設定 ---

from app.core.limiter import limiter

@pytest.fixture(autouse=True)
def reset_limiter_state():
    """各テストの実行前にレートリミッターの状態をリセットする"""
    limiter.reset()


# --- カレンダー関連フィクスチャ ---

@pytest_asyncio.fixture
async def test_office_with_calendar(
    db_session: AsyncSession,
    service_admin_user_factory,
    office_factory
):
    """カレンダーアカウント付きのテスト事業所を作成する共通fixture"""
    from app.models.calendar_account import OfficeCalendarAccount
    from app.models.enums import CalendarConnectionStatus
    from sqlalchemy import delete
    import os

    # テスト管理者と事業所を作成
    admin = await service_admin_user_factory(session=db_session)
    office = await office_factory(creator=admin, session=db_session)

    # 環境変数からサービスアカウントJSONを取得
    service_account_json = os.getenv("TEST_SERVICE_ACCOUNT_JSON")
    if not service_account_json:
        pytest.skip("TEST_SERVICE_ACCOUNT_JSON environment variable is not set")

    # カレンダーIDを取得
    google_calendar_id = os.getenv("TEST_GOOGLE_CALENDAR_ID")
    if not google_calendar_id:
        pytest.skip("TEST_GOOGLE_CALENDAR_ID environment variable is not set")

    # 既存の同じカレンダーIDを持つアカウントを削除（UNIQUE制約違反を防ぐ）
    await db_session.execute(
        delete(OfficeCalendarAccount).where(
            OfficeCalendarAccount.google_calendar_id == google_calendar_id
        )
    )
    await db_session.flush()

    # OfficeCalendarAccountを作成
    from app.crud.crud_office_calendar_account import crud_office_calendar_account
    from app.schemas.calendar_account import OfficeCalendarAccountCreate

    create_data = OfficeCalendarAccountCreate(
        office_id=office.id,
        google_calendar_id=google_calendar_id,
        calendar_name="テスト事業所カレンダー",
        service_account_key=service_account_json,
        service_account_email="test@test-project.iam.gserviceaccount.com",
        connection_status=CalendarConnectionStatus.connected,
        auto_invite_staff=False,
        default_reminder_minutes=1440  # 24時間前
    )

    account = await crud_office_calendar_account.create_with_encryption(
        db=db_session,
        obj_in=create_data
    )

    await db_session.flush()
    await db_session.refresh(account)

    return {
        "office": office,
        "calendar_account": account,
        "admin": admin
    }


@pytest_asyncio.fixture
async def calendar_account_fixture(test_office_with_calendar):
    """テスト用のカレンダーアカウントfixture（実際のGoogle Calendarと連携）"""
    return test_office_with_calendar["calendar_account"]


@pytest_asyncio.fixture
async def welfare_recipient_fixture(
    db_session: AsyncSession,
    test_office_with_calendar
):
    """テスト用の利用者fixture（カレンダーアカウント付き事業所を使用）"""
    from app.models.welfare_recipient import WelfareRecipient, OfficeWelfareRecipient
    from app.models.enums import GenderType
    from datetime import date

    office = test_office_with_calendar["office"]

    # 利用者を作成（正しい属性名を使用）
    recipient = WelfareRecipient(
        last_name="テスト",
        first_name="太郎",
        last_name_furigana="テスト",
        first_name_furigana="タロウ",
        birth_day=date(1990, 1, 1),
        gender=GenderType.male
    )

    db_session.add(recipient)
    await db_session.flush()

    # 事業所との関連付けを作成
    office_recipient_association = OfficeWelfareRecipient(
        welfare_recipient_id=recipient.id,
        office_id=office.id
    )
    db_session.add(office_recipient_association)
    await db_session.flush()
    await db_session.refresh(recipient)

    # テストで使いやすいように、office_idを属性として追加
    recipient.office_id = office.id

    return recipient


@pytest_asyncio.fixture
async def setup_recipient(
    db_session: AsyncSession,
    manager_user_factory,
    office_factory
):
    """アセスメント機能テスト用の利用者、スタッフ、事業所、トークンヘッダーのセットアップ"""
    from app.models.welfare_recipient import WelfareRecipient, OfficeWelfareRecipient
    from app.models.enums import GenderType
    from datetime import date
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload

    logger.debug("setup_recipient fixture start")

    # マネージャーを作成（事業所も自動作成される）
    manager = await manager_user_factory(session=db_session)
    await db_session.flush()  # Flush changes without committing (allows rollback)
    logger.debug("Manager created: id=%s", manager.id)

    # マネージャーの所属事業所を取得
    office = manager.office_associations[0].office
    logger.debug("Office loaded: id=%s", office.id)

    # 利用者を作成
    recipient = WelfareRecipient(
        last_name="テスト",
        first_name="太郎",
        last_name_furigana="テスト",
        first_name_furigana="タロウ",
        birth_day=date(1990, 1, 1),
        gender=GenderType.male
    )
    db_session.add(recipient)
    await db_session.flush()
    logger.debug("Recipient created: id=%s", recipient.id)

    # 事業所との関連付けを作成
    office_recipient_association = OfficeWelfareRecipient(
        welfare_recipient_id=recipient.id,
        office_id=office.id
    )
    db_session.add(office_recipient_association)
    await db_session.flush()
    await db_session.refresh(recipient)

    # トークンを生成
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(str(manager.id), access_token_expires)
    logger.debug("Access token created for setup_recipient")

    # get_current_userをオーバーライド
    async def override_get_current_user():
        logger.debug("override_get_current_user called in setup_recipient")
        stmt = select(Staff).where(Staff.id == manager.id).options(
            selectinload(Staff.office_associations).selectinload(OfficeStaff.office)
        )
        result = await db_session.execute(stmt)
        user = result.scalars().first()
        logger.debug("Returning user from setup_recipient override: id=%s", user.id if user else None)
        return user

    app.dependency_overrides[get_current_user] = override_get_current_user
    logger.debug("dependency_overrides set for get_current_user")

    token_headers = {"Authorization": f"Bearer {access_token}"}

    yield recipient, manager, office, token_headers

    # クリーンアップ
    logger.debug("setup_recipient fixture cleanup")
    app.dependency_overrides.pop(get_current_user, None)
    logger.debug("dependency_overrides removed for get_current_user")


@pytest_asyncio.fixture
async def setup_other_office_staff(
    db_session: AsyncSession,
    manager_user_factory
):
    """別事業所のスタッフとトークンヘッダーを作成（権限テスト用）"""
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload
    from app.models.office import OfficeStaff

    # 別のマネージャーを作成（新しい事業所が自動作成される）
    other_manager = await manager_user_factory(session=db_session)
    await db_session.flush()  # Flush changes without committing (allows rollback)

    # トークンを生成
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(str(other_manager.id), access_token_expires)

    # get_current_userをオーバーライド
    async def override_get_current_user():
        stmt = select(Staff).where(Staff.id == other_manager.id).options(
            selectinload(Staff.office_associations).selectinload(OfficeStaff.office)
        )
        result = await db_session.execute(stmt)
        user = result.scalars().first()
        return user

    app.dependency_overrides[get_current_user] = override_get_current_user

    token_headers = {"Authorization": f"Bearer {access_token}"}

    yield other_manager, token_headers

    # クリーンアップ
    app.dependency_overrides.pop(get_current_user, None)


# --- メール関連フィクスチャ ---

@pytest_asyncio.fixture
async def inquiry_detail_factory(db_session: AsyncSession, office_factory, app_admin_user_factory):
    """InquiryDetailを作成するFactory"""
    from app.models.inquiry import InquiryDetail
    from app.models.message import Message, MessageRecipient
    from app.models.enums import InquiryStatus, InquiryPriority, MessageType, MessagePriority

    counter = {"count": 0}

    async def _create_inquiry_detail(
        sender_staff_id: Optional[uuid.UUID] = None,
        sender_name: Optional[str] = None,
        sender_email: Optional[str] = None,
        title: str = "テスト問い合わせ",
        content: str = "テスト内容です",
        status: InquiryStatus = InquiryStatus.new,
        priority: InquiryPriority = InquiryPriority.normal,
        delivery_log: Optional[list] = None,
        session: Optional[AsyncSession] = None,
        is_test_data: bool = True,
    ) -> InquiryDetail:
        active_session = session or db_session
        counter["count"] += 1

        # 事務所を作成
        office = await office_factory(session=active_session, is_test_data=is_test_data)

        # app_adminユーザーを作成（受信者用）
        admin = await app_admin_user_factory(session=active_session, is_test_data=is_test_data)

        # Messageを作成
        message = Message(
            sender_staff_id=sender_staff_id,
            office_id=office.id,
            message_type=MessageType.inquiry,
            priority=MessagePriority.normal,
            title=title,
            content=content,
            is_test_data=is_test_data
        )
        active_session.add(message)
        await active_session.flush()

        # InquiryDetailを作成
        inquiry_detail = InquiryDetail(
            message_id=message.id,
            sender_name=sender_name or f"テスト送信者{counter['count']}",
            sender_email=sender_email or f"sender{counter['count']}@example.com",
            ip_address="192.168.1.100",
            user_agent="Mozilla/5.0",
            status=status,
            priority=priority,
            assigned_staff_id=None,
            admin_notes=None,
            delivery_log=delivery_log,
            is_test_data=is_test_data
        )
        active_session.add(inquiry_detail)
        await active_session.flush()

        # MessageRecipientを作成
        recipient = MessageRecipient(
            message_id=message.id,
            recipient_staff_id=admin.id,
            is_read=False,
            is_archived=False,
            is_test_data=is_test_data
        )
        active_session.add(recipient)
        await active_session.flush()

        # リレーションシップをロード
        await active_session.refresh(inquiry_detail, ["message"])

        return inquiry_detail

    yield _create_inquiry_detail


@pytest.fixture
def mock_fastmail():
    """FastMailの送信をモックするフィクスチャ"""
    from unittest.mock import AsyncMock, patch

    with patch('app.core.mail.FastMail') as mock_fm_class:
        mock_instance = AsyncMock()
        mock_fm_class.return_value = mock_instance
        yield mock_instance


@pytest.fixture
def mock_asyncio_sleep():
    """asyncio.sleepをモックしてテストを高速化"""
    from unittest.mock import patch, AsyncMock

    with patch('asyncio.sleep', new_callable=AsyncMock) as mock_sleep:
        yield mock_sleep


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
        fixture_value = request.getfixturevalue(fixture_name)

        # フィクスチャがtupleを返す場合（例: owner_user_with_office）、最初の要素（Staff）を取得
        if isinstance(fixture_value, tuple):
            user = fixture_value[0]  # (Staff, Office) の場合、Staffを取得
        else:
            user = fixture_value

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

        # テスト関数には元のフィクスチャの値を返す（tupleの場合もそのまま）
        return fixture_value
    return None
