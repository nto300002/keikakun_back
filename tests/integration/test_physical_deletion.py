"""
物理削除E2Eテスト

論理削除から30日経過したレコードが物理削除されることを確認
"""

import pytest
from datetime import datetime, timedelta, timezone
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import uuid4

from app.models.staff import Staff
from app.models.office import Office, OfficeStaff
from app.models.enums import StaffRole, OfficeType
from app.services.cleanup_service import cleanup_service
from app.core.security import get_password_hash
from app.db.session import AsyncSessionLocal

pytestmark = pytest.mark.asyncio


@pytest.fixture(scope="function")
async def db() -> AsyncSession:
    """テスト用の非同期DBセッションを提供するフィクスチャ"""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            try:
                await session.rollback()
            except Exception:
                pass


class TestPhysicalDeletion:
    """物理削除のE2Eテスト"""

    async def test_staff_physical_deletion_after_30_days(
        self,
        db: AsyncSession
    ):
        """
        論理削除から30日以上経過したスタッフが物理削除されることを確認
        """
        # テスト用管理者スタッフを作成（事務所のcreated_by用）
        admin = Staff(
            first_name="管理者",
            last_name="テスト",
            full_name="テスト管理者",
            email=f"admin.{uuid4().hex[:8]}@example.com",
            hashed_password=get_password_hash("password"),
            role=StaffRole.owner,
            is_test_data=True
        )
        db.add(admin)
        await db.flush()

        # テスト用事務所を作成
        office = Office(
            name="物理削除テスト事務所",
            type=OfficeType.type_A_office,
            created_by=admin.id,
            last_modified_by=admin.id,
            is_test_data=True
        )
        db.add(office)
        await db.flush()

        # テスト対象のスタッフを作成
        staff = Staff(
            first_name="物理削除",
            last_name="テストユーザー",
            full_name="物理削除テストユーザー",
            email=f"physical.delete.{uuid4().hex[:8]}@example.com",
            hashed_password=get_password_hash("password"),
            role=StaffRole.employee,
            is_test_data=True
        )
        db.add(staff)
        await db.flush()

        # OfficeStaff関連付け
        office_staff = OfficeStaff(
            office_id=office.id,
            staff_id=staff.id,
            is_primary=True
        )
        db.add(office_staff)
        await db.flush()

        staff_id = staff.id

        # スタッフを論理削除（31日前に削除されたことにする）
        deleted_at = datetime.now(timezone.utc) - timedelta(days=31)
        staff.is_deleted = True
        staff.deleted_at = deleted_at
        staff.deleted_by = staff_id
        await db.commit()

        # 論理削除されたことを確認
        stmt = select(Staff).where(Staff.id == staff_id)
        result = await db.execute(stmt)
        soft_deleted_staff = result.scalar_one_or_none()
        assert soft_deleted_staff is not None
        assert soft_deleted_staff.is_deleted is True
        assert soft_deleted_staff.deleted_at == deleted_at

        # クリーンアップサービスを実行（30日閾値）
        cleanup_result = await cleanup_service.cleanup_soft_deleted_records(
            db,
            days_threshold=30
        )

        # 物理削除されたことを確認
        assert cleanup_result["deleted_staff_count"] == 1
        assert cleanup_result["deleted_office_count"] == 0
        assert len(cleanup_result["errors"]) == 0

        # データベースから完全に削除されていることを確認
        result = await db.execute(stmt)
        physically_deleted_staff = result.scalar_one_or_none()
        assert physically_deleted_staff is None

    async def test_staff_not_deleted_before_30_days(
        self,
        db: AsyncSession
    ):
        """
        論理削除から30日未満のスタッフは物理削除されないことを確認
        """
        # テスト用管理者スタッフを作成
        admin = Staff(
            first_name="管理者",
            last_name="テスト",
            full_name="テスト管理者",
            email=f"admin.{uuid4().hex[:8]}@example.com",
            hashed_password=get_password_hash("password"),
            role=StaffRole.owner,
            is_test_data=True
        )
        db.add(admin)
        await db.flush()

        # テスト用事務所を作成
        office = Office(
            name="未削除テスト事務所",
            type=OfficeType.type_A_office,
            created_by=admin.id,
            last_modified_by=admin.id,
            is_test_data=True
        )
        db.add(office)
        await db.flush()

        # テスト対象のスタッフを作成
        staff = Staff(
            first_name="未削除",
            last_name="テストユーザー",
            full_name="未削除テストユーザー",
            email=f"not.delete.yet.{uuid4().hex[:8]}@example.com",
            hashed_password=get_password_hash("password"),
            role=StaffRole.employee,
            is_test_data=True
        )
        db.add(staff)
        await db.flush()

        # OfficeStaff関連付け
        office_staff = OfficeStaff(
            office_id=office.id,
            staff_id=staff.id,
            is_primary=True
        )
        db.add(office_staff)
        await db.flush()

        staff_id = staff.id

        # スタッフを論理削除（29日前に削除されたことにする = 30日未満）
        deleted_at = datetime.now(timezone.utc) - timedelta(days=29)
        staff.is_deleted = True
        staff.deleted_at = deleted_at
        staff.deleted_by = staff_id
        await db.commit()

        # クリーンアップサービスを実行（30日閾値）
        cleanup_result = await cleanup_service.cleanup_soft_deleted_records(
            db,
            days_threshold=30
        )

        # 物理削除されていないことを確認
        assert cleanup_result["deleted_staff_count"] == 0
        assert cleanup_result["deleted_office_count"] == 0

        # データベースにまだ存在することを確認（論理削除状態）
        stmt = select(Staff).where(Staff.id == staff_id)
        result = await db.execute(stmt)
        still_soft_deleted_staff = result.scalar_one_or_none()
        assert still_soft_deleted_staff is not None
        assert still_soft_deleted_staff.is_deleted is True
        assert still_soft_deleted_staff.deleted_at == deleted_at

    async def test_office_physical_deletion_after_30_days(
        self,
        db: AsyncSession
    ):
        """
        論理削除から30日以上経過した事務所が物理削除されることを確認
        """
        # テスト用管理者スタッフを作成
        admin = Staff(
            first_name="管理者",
            last_name="テスト",
            full_name="テスト管理者",
            email=f"admin.{uuid4().hex[:8]}@example.com",
            hashed_password=get_password_hash("password"),
            role=StaffRole.owner,
            is_test_data=True
        )
        db.add(admin)
        await db.flush()

        # テスト用事務所を作成
        office = Office(
            name="事務所物理削除テスト",
            type=OfficeType.type_A_office,
            created_by=admin.id,
            last_modified_by=admin.id,
            is_test_data=True
        )
        db.add(office)
        await db.flush()
        office_id = office.id

        # 事務所を論理削除（31日前に削除されたことにする）
        deleted_at = datetime.now(timezone.utc) - timedelta(days=31)
        office.is_deleted = True
        office.deleted_at = deleted_at
        await db.commit()

        # 論理削除されたことを確認
        stmt = select(Office).where(Office.id == office_id)
        result = await db.execute(stmt)
        soft_deleted_office = result.scalar_one_or_none()
        assert soft_deleted_office is not None
        assert soft_deleted_office.is_deleted is True
        assert soft_deleted_office.deleted_at == deleted_at

        # クリーンアップサービスを実行（30日閾値）
        cleanup_result = await cleanup_service.cleanup_soft_deleted_records(
            db,
            days_threshold=30
        )

        # 物理削除されたことを確認
        assert cleanup_result["deleted_staff_count"] == 0
        assert cleanup_result["deleted_office_count"] == 1
        assert len(cleanup_result["errors"]) == 0

        # データベースから完全に削除されていることを確認
        result = await db.execute(stmt)
        physically_deleted_office = result.scalar_one_or_none()
        assert physically_deleted_office is None

    async def test_mixed_deletion_scenario(
        self,
        db: AsyncSession
    ):
        """
        複数のスタッフと事務所が混在する状態で正しく物理削除されることを確認

        - 31日前に削除: 2スタッフ、1事務所 → 物理削除される
        - 29日前に削除: 1スタッフ、1事務所 → 物理削除されない
        - 論理削除されていない: 1スタッフ、1事務所 → 物理削除されない
        """
        # 管理者スタッフを作成
        admin = Staff(
            first_name="管理者",
            last_name="テスト",
            full_name="テスト管理者",
            email=f"admin.{uuid4().hex[:8]}@example.com",
            hashed_password=get_password_hash("password"),
            role=StaffRole.owner,
            is_test_data=True
        )
        db.add(admin)
        await db.flush()

        # 事務所1: 31日前に削除（物理削除される）
        office1 = Office(
            name="削除事務所1",
            type=OfficeType.type_A_office,
            created_by=admin.id,
            last_modified_by=admin.id,
            is_test_data=True
        )
        db.add(office1)
        await db.flush()
        office1.is_deleted = True
        office1.deleted_at = datetime.now(timezone.utc) - timedelta(days=31)

        # 事務所2: 29日前に削除（物理削除されない）
        office2 = Office(
            name="削除事務所2",
            type=OfficeType.type_A_office,
            created_by=admin.id,
            last_modified_by=admin.id,
            is_test_data=True
        )
        db.add(office2)
        await db.flush()
        office2.is_deleted = True
        office2.deleted_at = datetime.now(timezone.utc) - timedelta(days=29)

        # 事務所3: 削除されていない（物理削除されない）
        office3 = Office(
            name="通常事務所",
            type=OfficeType.type_A_office,
            created_by=admin.id,
            last_modified_by=admin.id,
            is_test_data=True
        )
        db.add(office3)
        await db.flush()

        # スタッフ1: 31日前に削除（物理削除される）
        staff1 = Staff(
            first_name="削除",
            last_name="ユーザー1",
            full_name="削除ユーザー1",
            email=f"delete1.{uuid4().hex[:8]}@example.com",
            hashed_password=get_password_hash("password"),
            role=StaffRole.employee,
            is_test_data=True
        )
        db.add(staff1)
        await db.flush()
        office_staff1 = OfficeStaff(
            office_id=office3.id,
            staff_id=staff1.id,
            is_primary=True
        )
        db.add(office_staff1)
        await db.flush()
        staff1.is_deleted = True
        staff1.deleted_at = datetime.now(timezone.utc) - timedelta(days=31)
        staff1.deleted_by = staff1.id

        # スタッフ2: 31日前に削除（物理削除される）
        staff2 = Staff(
            first_name="削除",
            last_name="ユーザー2",
            full_name="削除ユーザー2",
            email=f"delete2.{uuid4().hex[:8]}@example.com",
            hashed_password=get_password_hash("password"),
            role=StaffRole.employee,
            is_test_data=True
        )
        db.add(staff2)
        await db.flush()
        office_staff2 = OfficeStaff(
            office_id=office3.id,
            staff_id=staff2.id,
            is_primary=True
        )
        db.add(office_staff2)
        await db.flush()
        staff2.is_deleted = True
        staff2.deleted_at = datetime.now(timezone.utc) - timedelta(days=31)
        staff2.deleted_by = staff2.id

        # スタッフ3: 29日前に削除（物理削除されない）
        staff3 = Staff(
            first_name="最近削除",
            last_name="ユーザー",
            full_name="最近削除ユーザー",
            email=f"recent.delete.{uuid4().hex[:8]}@example.com",
            hashed_password=get_password_hash("password"),
            role=StaffRole.employee,
            is_test_data=True
        )
        db.add(staff3)
        await db.flush()
        office_staff3 = OfficeStaff(
            office_id=office3.id,
            staff_id=staff3.id,
            is_primary=True
        )
        db.add(office_staff3)
        await db.flush()
        staff3.is_deleted = True
        staff3.deleted_at = datetime.now(timezone.utc) - timedelta(days=29)
        staff3.deleted_by = staff3.id

        # スタッフ4: 削除されていない（物理削除されない）
        staff4 = Staff(
            first_name="通常",
            last_name="ユーザー",
            full_name="通常ユーザー",
            email=f"active.{uuid4().hex[:8]}@example.com",
            hashed_password=get_password_hash("password"),
            role=StaffRole.employee,
            is_test_data=True
        )
        db.add(staff4)
        await db.flush()
        office_staff4 = OfficeStaff(
            office_id=office3.id,
            staff_id=staff4.id,
            is_primary=True
        )
        db.add(office_staff4)
        await db.flush()

        office1_id = office1.id
        office2_id = office2.id
        office3_id = office3.id
        staff1_id = staff1.id
        staff2_id = staff2.id
        staff3_id = staff3.id
        staff4_id = staff4.id

        await db.commit()

        # クリーンアップサービスを実行
        cleanup_result = await cleanup_service.cleanup_soft_deleted_records(
            db,
            days_threshold=30
        )

        # 物理削除されたレコード数を確認
        assert cleanup_result["deleted_staff_count"] == 2  # staff1, staff2
        assert cleanup_result["deleted_office_count"] == 1  # office1
        assert len(cleanup_result["errors"]) == 0

        # 物理削除されたことを確認
        stmt = select(Staff).where(Staff.id.in_([staff1_id, staff2_id]))
        result = await db.execute(stmt)
        assert len(result.scalars().all()) == 0

        stmt = select(Office).where(Office.id == office1_id)
        result = await db.execute(stmt)
        assert result.scalar_one_or_none() is None

        # 残っているレコードを確認
        stmt = select(Staff).where(Staff.id.in_([staff3_id, staff4_id]))
        result = await db.execute(stmt)
        remaining_staff = result.scalars().all()
        assert len(remaining_staff) == 2

        stmt = select(Office).where(Office.id.in_([office2_id, office3_id]))
        result = await db.execute(stmt)
        remaining_offices = result.scalars().all()
        assert len(remaining_offices) == 2

    async def test_custom_threshold_days(
        self,
        db: AsyncSession
    ):
        """
        カスタム閾値日数で物理削除が実行されることを確認
        """
        # テスト用管理者スタッフを作成
        admin = Staff(
            first_name="管理者",
            last_name="テスト",
            full_name="テスト管理者",
            email=f"admin.{uuid4().hex[:8]}@example.com",
            hashed_password=get_password_hash("password"),
            role=StaffRole.owner,
            is_test_data=True
        )
        db.add(admin)
        await db.flush()

        # テスト用事務所を作成
        office = Office(
            name="カスタム閾値テスト事務所",
            type=OfficeType.type_A_office,
            created_by=admin.id,
            last_modified_by=admin.id,
            is_test_data=True
        )
        db.add(office)
        await db.flush()

        # テスト対象のスタッフを作成
        staff = Staff(
            first_name="カスタム閾値",
            last_name="テストユーザー",
            full_name="カスタム閾値テストユーザー",
            email=f"custom.threshold.{uuid4().hex[:8]}@example.com",
            hashed_password=get_password_hash("password"),
            role=StaffRole.employee,
            is_test_data=True
        )
        db.add(staff)
        await db.flush()

        # OfficeStaff関連付け
        office_staff = OfficeStaff(
            office_id=office.id,
            staff_id=staff.id,
            is_primary=True
        )
        db.add(office_staff)
        await db.flush()

        staff_id = staff.id

        # スタッフを論理削除（8日前に削除されたことにする）
        deleted_at = datetime.now(timezone.utc) - timedelta(days=8)
        staff.is_deleted = True
        staff.deleted_at = deleted_at
        staff.deleted_by = staff_id
        await db.commit()

        # クリーンアップサービスを実行（7日閾値 = 8日前のレコードは削除される）
        cleanup_result = await cleanup_service.cleanup_soft_deleted_records(
            db,
            days_threshold=7
        )

        # 物理削除されたことを確認（前のテストのデータも削除される可能性があるため >= で確認）
        assert cleanup_result["deleted_staff_count"] >= 1
        assert cleanup_result["deleted_office_count"] >= 0

        # データベースから完全に削除されていることを確認
        stmt = select(Staff).where(Staff.id == staff_id)
        result = await db.execute(stmt)
        physically_deleted_staff = result.scalar_one_or_none()
        assert physically_deleted_staff is None
