"""
一時的なシステム事務所ユーティリティのテスト
"""
import pytest
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.utils.temp_office import (
    create_temporary_system_office,
    delete_temporary_system_office,
    temporary_system_office,
    get_or_create_system_office
)
from app.models.office import Office
from app.models.enums import OfficeType

pytestmark = pytest.mark.asyncio


class TestCreateTemporarySystemOffice:
    """create_temporary_system_office のテスト"""

    async def test_create_temporary_system_office_success(
        self,
        db_session: AsyncSession,
        app_admin_user_factory
    ):
        """一時的なシステム事務所を作成できること"""
        # Setup: app_adminユーザー作成
        app_admin = await app_admin_user_factory()

        # 一時的なシステム事務所を作成
        office = await create_temporary_system_office(
            db=db_session,
            created_by_staff_id=app_admin.id
        )

        # Assert: 事務所が作成された
        assert office is not None
        assert isinstance(office.id, UUID)
        assert office.name == "__TEMP_SYSTEM__"
        assert office.type == OfficeType.type_A_office
        assert office.created_by == app_admin.id
        assert office.last_modified_by == app_admin.id
        assert office.is_deleted is False
        assert office.is_test_data is False

    async def test_created_office_persists_in_db(
        self,
        db_session: AsyncSession,
        app_admin_user_factory
    ):
        """作成された事務所がDBに永続化されること"""
        app_admin = await app_admin_user_factory()
        office = await create_temporary_system_office(
            db=db_session,
            created_by_staff_id=app_admin.id
        )
        await db_session.commit()

        # DBから取得
        stmt = select(Office).where(Office.id == office.id)
        result = await db_session.execute(stmt)
        retrieved_office = result.scalar_one_or_none()

        # Assert: DBに永続化されている
        assert retrieved_office is not None
        assert retrieved_office.id == office.id
        assert retrieved_office.name == "__TEMP_SYSTEM__"


class TestDeleteTemporarySystemOffice:
    """delete_temporary_system_office のテスト"""

    async def test_delete_temporary_system_office_success(
        self,
        db_session: AsyncSession,
        app_admin_user_factory
    ):
        """一時的なシステム事務所を削除できること"""
        app_admin = await app_admin_user_factory()
        office = await create_temporary_system_office(
            db=db_session,
            created_by_staff_id=app_admin.id
        )
        await db_session.commit()

        # 削除
        result = await delete_temporary_system_office(
            db=db_session,
            office_id=office.id
        )
        await db_session.commit()

        # Assert: 削除成功
        assert result is True

        # DBから取得試行
        stmt = select(Office).where(Office.id == office.id)
        db_result = await db_session.execute(stmt)
        retrieved_office = db_result.scalar_one_or_none()

        # Assert: 削除されている
        assert retrieved_office is None

    async def test_delete_non_existent_office(
        self,
        db_session: AsyncSession
    ):
        """存在しない事務所IDを削除しようとすると失敗すること"""
        from uuid import uuid4

        # 存在しないIDで削除試行
        result = await delete_temporary_system_office(
            db=db_session,
            office_id=uuid4()
        )

        # Assert: 削除失敗
        assert result is False

    async def test_delete_regular_office_fails(
        self,
        db_session: AsyncSession,
        office_factory
    ):
        """通常の事務所は削除できないこと（名前チェック）"""
        # 通常の事務所を作成
        regular_office = await office_factory(name="通常の事務所")

        # 削除試行
        result = await delete_temporary_system_office(
            db=db_session,
            office_id=regular_office.id
        )

        # Assert: 削除失敗（名前が "__TEMP_SYSTEM__" でないため）
        assert result is False

        # DBから取得
        stmt = select(Office).where(Office.id == regular_office.id)
        db_result = await db_session.execute(stmt)
        retrieved_office = db_result.scalar_one_or_none()

        # Assert: 削除されていない
        assert retrieved_office is not None


class TestTemporarySystemOfficeContextManager:
    """temporary_system_office コンテキストマネージャーのテスト"""

    async def test_context_manager_creates_and_deletes_office(
        self,
        db_session: AsyncSession,
        app_admin_user_factory
    ):
        """コンテキストマネージャーが事務所を作成・削除すること"""
        app_admin = await app_admin_user_factory()
        office_id = None

        # コンテキスト内で事務所を使用
        async with temporary_system_office(db_session, app_admin.id) as office:
            office_id = office.id

            # コンテキスト内では存在する
            stmt = select(Office).where(Office.id == office_id)
            result = await db_session.execute(stmt)
            assert result.scalar_one_or_none() is not None

        # コンテキスト終了後は削除されている
        await db_session.commit()
        stmt = select(Office).where(Office.id == office_id)
        result = await db_session.execute(stmt)
        assert result.scalar_one_or_none() is None

    async def test_context_manager_deletes_on_exception(
        self,
        db_session: AsyncSession,
        app_admin_user_factory
    ):
        """例外発生時もコンテキストマネージャーが事務所を削除すること"""
        app_admin = await app_admin_user_factory()
        office_id = None

        # 例外を発生させる
        with pytest.raises(ValueError):
            async with temporary_system_office(db_session, app_admin.id) as office:
                office_id = office.id
                raise ValueError("テスト用の例外")

        # 例外発生後も削除されている
        await db_session.commit()
        stmt = select(Office).where(Office.id == office_id)
        result = await db_session.execute(stmt)
        assert result.scalar_one_or_none() is None


class TestGetOrCreateSystemOffice:
    """get_or_create_system_office のテスト"""

    async def test_creates_new_office_if_not_exists(
        self,
        db_session: AsyncSession,
        app_admin_user_factory
    ):
        """既存の一時事務所がない場合、新規作成すること"""
        app_admin = await app_admin_user_factory()

        # 一時事務所を取得または作成
        office_id = await get_or_create_system_office(
            db=db_session,
            admin_staff_id=app_admin.id
        )

        # Assert: IDが返される
        assert office_id is not None
        assert isinstance(office_id, UUID)

        # DBから取得
        stmt = select(Office).where(Office.id == office_id)
        result = await db_session.execute(stmt)
        office = result.scalar_one_or_none()

        # Assert: 事務所が作成されている
        assert office is not None
        assert office.name == "__TEMP_SYSTEM__"

    async def test_reuses_existing_office_if_exists(
        self,
        db_session: AsyncSession,
        app_admin_user_factory
    ):
        """既存の一時事務所がある場合、それを再利用すること"""
        app_admin = await app_admin_user_factory()

        # 最初の呼び出し: 新規作成
        office_id_1 = await get_or_create_system_office(
            db=db_session,
            admin_staff_id=app_admin.id
        )
        await db_session.commit()

        # 2回目の呼び出し: 既存を再利用
        office_id_2 = await get_or_create_system_office(
            db=db_session,
            admin_staff_id=app_admin.id
        )

        # Assert: 同じIDが返される
        assert office_id_1 == office_id_2

        # DBに1つだけ存在する
        stmt = select(Office).where(Office.name == "__TEMP_SYSTEM__")
        result = await db_session.execute(stmt)
        offices = list(result.scalars().all())

        # Assert: 1つだけ
        assert len(offices) == 1
