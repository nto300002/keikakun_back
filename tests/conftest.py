# tests/conftest.py (pytest-asyncio構成)
import asyncio
import os
import sys
from typing import AsyncGenerator, Generator, Optional
import uuid
from datetime import timedelta
import logging

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
from app.models.enums import StaffRole, OfficeType


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
    async with AsyncClient(transport=ASGITransport(app=app), base_url="https://test") as client:
        try:
            yield client
        finally:
            # tolerate either override key (avoid KeyError when function object differs)
            app.dependency_overrides.pop(get_db, None)


@pytest_asyncio.fixture
async def service_admin_user_factory(db_session: AsyncSession):
    counter = {"count": 0}  # ローカルカウンター

    async def _create_user(
        name: str = "テスト管理者",
        email: Optional[str] = None,
        password: str = "a-very-secure-password",
        role: StaffRole = StaffRole.owner,
        is_email_verified: bool = True,
        is_mfa_enabled: bool = False,
        session: Optional[AsyncSession] = None,
    ) -> Staff:
        from sqlalchemy import select
        from sqlalchemy.orm import selectinload
        import time

        # デフォルトのメールアドレスを生成（UUID + タイムスタンプ + カウンター）
        if email is None:
            counter["count"] += 1
            timestamp = int(time.time() * 1000000)  # マイクロ秒単位
            email = f"admin_{uuid.uuid4().hex}_{timestamp}_{counter['count']}@example.com"

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
        name: str = "テスト従業員",
        email: Optional[str] = None,
        password: str = "a-very-secure-password",
        role: StaffRole = StaffRole.employee,
        is_email_verified: bool = True,
        is_mfa_enabled: bool = False,
        session: Optional[AsyncSession] = None,
        office: Optional[Office] = None,  # 事業所を外部から受け取れるようにする
        with_office: bool = True,
    ) -> Staff:
        from sqlalchemy import select
        from sqlalchemy.orm import selectinload
        from app.models.office import OfficeStaff
        import time

        # デフォルトのメールアドレスを生成（UUID + タイムスタンプ + カウンター）
        if email is None:
            counter["count"] += 1
            timestamp = int(time.time() * 1000000)  # マイクロ秒単位
            email = f"employee_{uuid.uuid4().hex}_{timestamp}_{counter['count']}@example.com"

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

            association = OfficeStaff(
                staff_id=new_user.id,
                office_id=target_office.id,
                is_primary=True
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
        name: str = "テストマネージャー",
        email: Optional[str] = None,
        password: str = "a-very-secure-password",
        role: StaffRole = StaffRole.manager,
        is_email_verified: bool = True,
        is_mfa_enabled: bool = False,
        session: Optional[AsyncSession] = None,
        office: Optional[Office] = None,  # 事業所を外部から受け取れるようにする
        with_office: bool = True,
    ) -> Staff:
        from sqlalchemy import select
        from sqlalchemy.orm import selectinload
        from app.models.office import OfficeStaff
        import time

        # デフォルトのメールアドレスを生成（UUID + タイムスタンプ + カウンター）
        if email is None:
            counter["count"] += 1
            timestamp = int(time.time() * 1000000)  # マイクロ秒単位
            email = f"manager_{uuid.uuid4().hex}_{timestamp}_{counter['count']}@example.com"

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

            association = OfficeStaff(
                staff_id=new_user.id,
                office_id=target_office.id,
                is_primary=True
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

    print("\n" + "="*80)
    print("=== setup_recipient fixture start ===")
    logger.info("=== setup_recipient fixture start ===")

    # マネージャーを作成（事業所も自動作成される）
    manager = await manager_user_factory(session=db_session)
    await db_session.flush()  # Flush changes without committing (allows rollback)
    print(f"Manager created: {manager.email}, id: {manager.id}")
    logger.info(f"Manager created: {manager.email}, id: {manager.id}")

    # マネージャーの所属事業所を取得
    office = manager.office_associations[0].office
    print(f"Office: {office.name}, id: {office.id}")
    logger.info(f"Office: {office.name}, id: {office.id}")

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
    print(f"Recipient created: {recipient.id}")
    logger.info(f"Recipient created: {recipient.id}")

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
    print(f"Token created: {access_token[:30]}...")
    logger.info(f"Token created: {access_token[:30]}...")

    # get_current_userをオーバーライド
    async def override_get_current_user():
        print(f"\n{'='*80}")
        print(f"=== override_get_current_user called in setup_recipient ===")
        logger.info(f"=== override_get_current_user called in setup_recipient ===")
        stmt = select(Staff).where(Staff.id == manager.id).options(
            selectinload(Staff.office_associations).selectinload(OfficeStaff.office)
        )
        result = await db_session.execute(stmt)
        user = result.scalars().first()
        print(f"Returning user from override: {user.email if user else 'None'}")
        print(f"{'='*80}\n")
        logger.info(f"Returning user from override: {user.email if user else 'None'}")
        return user

    app.dependency_overrides[get_current_user] = override_get_current_user
    print("dependency_overrides set for get_current_user")
    print(f"Current overrides: {list(app.dependency_overrides.keys())}")
    print("="*80 + "\n")
    logger.info("dependency_overrides set for get_current_user")

    token_headers = {"Authorization": f"Bearer {access_token}"}

    yield recipient, manager, office, token_headers

    # クリーンアップ
    print("\n" + "="*80)
    print("=== setup_recipient fixture cleanup ===")
    logger.info("=== setup_recipient fixture cleanup ===")
    app.dependency_overrides.pop(get_current_user, None)
    print("dependency_overrides removed for get_current_user")
    print(f"Current overrides after cleanup: {list(app.dependency_overrides.keys())}")
    print("="*80 + "\n")
    logger.info("dependency_overrides removed for get_current_user")


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
