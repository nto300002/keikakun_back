"""
スタッフ削除機能のCRUD操作テスト

TDD Red Phase: 実装前のテスト作成
"""
import pytest
from datetime import datetime, timezone
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession

from app import crud
from app.models.staff import Staff
from app.models.enums import StaffRole

pytestmark = pytest.mark.asyncio


class TestStaffCRUDCountOwnersInOffice:
    """count_owners_in_office メソッドのテスト"""

    async def test_count_owners_in_office_with_multiple_owners(
        self,
        db_session: AsyncSession,
        owner_user_factory,
        employee_user_factory,
        office_factory
    ):
        """複数のOwnerが存在する場合、正しくカウントされる"""
        # 事務所を作成
        office = await office_factory()

        # Owner を3人作成
        owner1 = await owner_user_factory(office=office)
        owner2 = await owner_user_factory(office=office)
        owner3 = await owner_user_factory(office=office)

        # Employeeも作成（カウントされないはず）
        await employee_user_factory(office=office)

        # テスト実行
        count = await crud.staff.count_owners_in_office(
            db=db_session,
            office_id=office.id
        )

        assert count == 3

    async def test_count_owners_excludes_deleted_owners(
        self,
        db_session: AsyncSession,
        owner_user_factory,
        office_factory
    ):
        """削除済みOwnerはカウントされない"""
        office = await office_factory()

        # Owner を2人作成
        owner1 = await owner_user_factory(office=office)
        owner2 = await owner_user_factory(office=office)

        # owner2を削除済みに設定
        owner2.is_deleted = True
        owner2.deleted_at = datetime.now(timezone.utc)
        db_session.add(owner2)
        await db_session.flush()

        # テスト実行
        count = await crud.staff.count_owners_in_office(
            db=db_session,
            office_id=office.id
        )

        # 削除済みOwnerはカウントされない
        assert count == 1

    async def test_count_owners_in_office_returns_zero_when_no_owners(
        self,
        db_session: AsyncSession,
        employee_user_factory,
        office_factory
    ):
        """Ownerが存在しない場合、0を返す"""
        office = await office_factory()

        # Employeeのみ作成
        await employee_user_factory(office=office)

        # テスト実行
        count = await crud.staff.count_owners_in_office(
            db=db_session,
            office_id=office.id
        )

        assert count == 0


class TestStaffCRUDSoftDelete:
    """soft_delete メソッドのテスト"""

    async def test_soft_delete_sets_is_deleted_to_true(
        self,
        db_session: AsyncSession,
        employee_user_factory,
        owner_user_factory,
        office_factory
    ):
        """論理削除でis_deletedがTrueになる"""
        office = await office_factory()
        staff = await employee_user_factory(office=office)
        deleter = await owner_user_factory(office=office)

        # 削除前の状態を確認
        assert staff.is_deleted is False
        assert staff.deleted_at is None
        assert staff.deleted_by is None

        # soft_deleteを実行
        deleted_staff = await crud.staff.soft_delete(
            db=db_session,
            staff_id=staff.id,
            deleted_by=deleter.id
        )
        await db_session.commit()
        await db_session.refresh(deleted_staff)

        # 削除後の状態を確認
        assert deleted_staff.is_deleted is True
        assert deleted_staff.deleted_at is not None
        assert deleted_staff.deleted_by == deleter.id
        assert deleted_staff.deleted_at.tzinfo is not None  # タイムゾーン情報あり

    async def test_soft_delete_sets_deleted_at_to_current_time(
        self,
        db_session: AsyncSession,
        employee_user_factory,
        owner_user_factory,
        office_factory
    ):
        """論理削除でdeleted_atが現在時刻に設定される"""
        office = await office_factory()
        staff = await employee_user_factory(office=office)
        deleter = await owner_user_factory(office=office)

        before_delete = datetime.now(timezone.utc)

        # soft_deleteを実行
        deleted_staff = await crud.staff.soft_delete(
            db=db_session,
            staff_id=staff.id,
            deleted_by=deleter.id
        )
        await db_session.commit()
        await db_session.refresh(deleted_staff)

        after_delete = datetime.now(timezone.utc)

        # deleted_atが現在時刻の範囲内にあることを確認
        assert before_delete <= deleted_staff.deleted_at <= after_delete


class TestStaffCRUDGetByOfficeIdWithExcludeDeleted:
    """get_by_office_id with exclude_deleted パラメータのテスト"""

    async def test_get_by_office_id_excludes_deleted_staff_by_default(
        self,
        db_session: AsyncSession,
        employee_user_factory,
        office_factory
    ):
        """デフォルトで削除済みスタッフが除外される"""
        office = await office_factory()

        # 有効なスタッフを2人作成
        active_staff1 = await employee_user_factory(office=office)
        active_staff2 = await employee_user_factory(office=office)

        # 削除済みスタッフを1人作成
        deleted_staff = await employee_user_factory(office=office)
        deleted_staff.is_deleted = True
        deleted_staff.deleted_at = datetime.now(timezone.utc)
        db_session.add(deleted_staff)
        await db_session.flush()

        # テスト実行（exclude_deleted=Trueがデフォルト）
        staff_list = await crud.staff.get_by_office_id(
            db=db_session,
            office_id=office.id
        )

        # 有効なスタッフのみ取得される
        assert len(staff_list) == 2
        staff_ids = [s.id for s in staff_list]
        assert active_staff1.id in staff_ids
        assert active_staff2.id in staff_ids
        assert deleted_staff.id not in staff_ids

    async def test_get_by_office_id_includes_deleted_staff_when_exclude_deleted_false(
        self,
        db_session: AsyncSession,
        employee_user_factory,
        office_factory
    ):
        """exclude_deleted=Falseで削除済みスタッフも取得される"""
        office = await office_factory()

        # 有効なスタッフを1人作成
        active_staff = await employee_user_factory(office=office)

        # 削除済みスタッフを1人作成
        deleted_staff = await employee_user_factory(office=office)
        deleted_staff.is_deleted = True
        deleted_staff.deleted_at = datetime.now(timezone.utc)
        db_session.add(deleted_staff)
        await db_session.flush()

        # テスト実行（exclude_deleted=False）
        staff_list = await crud.staff.get_by_office_id(
            db=db_session,
            office_id=office.id,
            exclude_deleted=False
        )

        # 全スタッフ（削除済み含む）が取得される
        assert len(staff_list) == 2
        staff_ids = [s.id for s in staff_list]
        assert active_staff.id in staff_ids
        assert deleted_staff.id in staff_ids


class TestStaffAuditLogCRUDCreateAuditLog:
    """create_audit_log メソッドのテスト"""

    async def test_create_audit_log_saves_all_fields(
        self,
        db_session: AsyncSession,
        employee_user_factory,
        owner_user_factory,
        office_factory
    ):
        """監査ログが全フィールドを保存する"""
        office = await office_factory()
        target_staff = await employee_user_factory(office=office)
        performer = await owner_user_factory(office=office)

        # create_logを実行
        audit_log = await crud.audit_log.create_log(
            db=db_session,
            actor_id=performer.id,
            actor_role=performer.role,
            action="staff.deleted",
            target_type="staff",
            target_id=target_staff.id,
            office_id=office.id,
            ip_address="192.168.1.1",
            user_agent="Mozilla/5.0...",
            details={
                "deleted_staff_email": target_staff.email,
                "deleted_staff_name": target_staff.full_name,
                "deleted_staff_role": target_staff.role.value
            }
        )
        await db_session.commit()
        await db_session.refresh(audit_log)

        # 全フィールドが正しく保存されているか確認
        assert audit_log.target_id == target_staff.id
        assert audit_log.action == "staff.deleted"
        assert audit_log.staff_id == performer.id
        assert audit_log.ip_address == "192.168.1.1"
        assert audit_log.user_agent == "Mozilla/5.0..."
        assert audit_log.details["deleted_staff_email"] == target_staff.email
        assert audit_log.timestamp is not None
        assert audit_log.timestamp.tzinfo is not None  # タイムゾーン情報あり
