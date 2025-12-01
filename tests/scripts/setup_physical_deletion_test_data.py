"""
物理削除テスト用データセットアップスクリプト

論理削除されたデータのdeleted_atを過去の日付に変更し、
物理削除のテストデータを準備する
"""

import asyncio
from datetime import datetime, timedelta, timezone
from uuid import uuid4
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import AsyncSessionLocal
from app.models.staff import Staff
from app.models.office import Office, OfficeStaff
from app.models.enums import StaffRole, OfficeType
from app.core.security import get_password_hash


async def create_test_data_for_physical_deletion():
    """
    物理削除テスト用のデータを作成

    作成するデータ:
    1. 31日前に削除されたスタッフ（物理削除対象）
    2. 29日前に削除されたスタッフ（物理削除対象外）
    3. 31日前に削除された事務所（物理削除対象）
    4. 29日前に削除された事務所（物理削除対象外）
    5. 通常のアクティブなスタッフと事務所
    """
    async with AsyncSessionLocal() as db:
        try:
            print("=" * 80)
            print("物理削除テスト用データのセットアップ開始")
            print("=" * 80)

            # 1. 管理者スタッフを作成（事務所のcreated_by用）
            admin = Staff(
                first_name="テスト",
                last_name="管理者",
                full_name="テスト管理者",
                email=f"test.admin.{uuid4().hex[:8]}@example.com",
                hashed_password=get_password_hash("password"),
                role=StaffRole.owner,
                is_test_data=True
            )
            db.add(admin)
            await db.flush()
            print(f"✓ 管理者スタッフ作成: {admin.email}")

            # 2. 31日前に削除されたスタッフ（物理削除対象）
            staff_old_deleted = Staff(
                first_name="31日前削除",
                last_name="スタッフ",
                full_name="31日前削除スタッフ",
                email=f"old.deleted.{uuid4().hex[:8]}@example.com",
                hashed_password=get_password_hash("password"),
                role=StaffRole.employee,
                is_test_data=True,
                is_deleted=True,
                deleted_at=datetime.now(timezone.utc) - timedelta(days=31),
                deleted_by=admin.id
            )
            db.add(staff_old_deleted)
            await db.flush()
            print(f"✓ 31日前削除スタッフ作成: {staff_old_deleted.email} (物理削除対象)")

            # 3. 29日前に削除されたスタッフ（物理削除対象外）
            staff_recent_deleted = Staff(
                first_name="29日前削除",
                last_name="スタッフ",
                full_name="29日前削除スタッフ",
                email=f"recent.deleted.{uuid4().hex[:8]}@example.com",
                hashed_password=get_password_hash("password"),
                role=StaffRole.employee,
                is_test_data=True,
                is_deleted=True,
                deleted_at=datetime.now(timezone.utc) - timedelta(days=29),
                deleted_by=admin.id
            )
            db.add(staff_recent_deleted)
            await db.flush()
            print(f"✓ 29日前削除スタッフ作成: {staff_recent_deleted.email} (物理削除対象外)")

            # 4. 通常のアクティブなスタッフ
            staff_active = Staff(
                first_name="アクティブ",
                last_name="スタッフ",
                full_name="アクティブスタッフ",
                email=f"active.{uuid4().hex[:8]}@example.com",
                hashed_password=get_password_hash("password"),
                role=StaffRole.employee,
                is_test_data=True
            )
            db.add(staff_active)
            await db.flush()
            print(f"✓ アクティブスタッフ作成: {staff_active.email}")

            # 5. 31日前に削除された事務所（物理削除対象）
            office_old_deleted = Office(
                name="31日前削除事務所",
                type=OfficeType.type_A_office,
                created_by=admin.id,
                last_modified_by=admin.id,
                is_test_data=True,
                is_deleted=True,
                deleted_at=datetime.now(timezone.utc) - timedelta(days=31)
            )
            db.add(office_old_deleted)
            await db.flush()
            print(f"✓ 31日前削除事務所作成: {office_old_deleted.name} (物理削除対象)")

            # 6. 29日前に削除された事務所（物理削除対象外）
            office_recent_deleted = Office(
                name="29日前削除事務所",
                type=OfficeType.type_A_office,
                created_by=admin.id,
                last_modified_by=admin.id,
                is_test_data=True,
                is_deleted=True,
                deleted_at=datetime.now(timezone.utc) - timedelta(days=29)
            )
            db.add(office_recent_deleted)
            await db.flush()
            print(f"✓ 29日前削除事務所作成: {office_recent_deleted.name} (物理削除対象外)")

            # 7. 通常のアクティブな事務所
            office_active = Office(
                name="アクティブ事務所",
                type=OfficeType.type_A_office,
                created_by=admin.id,
                last_modified_by=admin.id,
                is_test_data=True
            )
            db.add(office_active)
            await db.flush()
            print(f"✓ アクティブ事務所作成: {office_active.name}")

            # 8. アクティブスタッフとアクティブ事務所を関連付け
            office_staff = OfficeStaff(
                office_id=office_active.id,
                staff_id=staff_active.id,
                is_primary=True
            )
            db.add(office_staff)

            # IDを保存
            staff_old_deleted_id = staff_old_deleted.id
            staff_recent_deleted_id = staff_recent_deleted.id
            staff_active_id = staff_active.id
            office_old_deleted_id = office_old_deleted.id
            office_recent_deleted_id = office_recent_deleted.id
            office_active_id = office_active.id

            await db.commit()

            print("\n" + "=" * 80)
            print("テストデータ作成完了")
            print("=" * 80)
            print(f"\n【物理削除対象】")
            print(f"  スタッフID: {staff_old_deleted_id}")
            print(f"  事務所ID:   {office_old_deleted_id}")
            print(f"\n【物理削除対象外】")
            print(f"  スタッフID: {staff_recent_deleted_id} (29日前削除)")
            print(f"  スタッフID: {staff_active_id} (アクティブ)")
            print(f"  事務所ID:   {office_recent_deleted_id} (29日前削除)")
            print(f"  事務所ID:   {office_active_id} (アクティブ)")

            return {
                "physical_deletion_targets": {
                    "staff_id": staff_old_deleted_id,
                    "office_id": office_old_deleted_id
                },
                "should_remain": {
                    "staff_ids": [staff_recent_deleted_id, staff_active_id],
                    "office_ids": [office_recent_deleted_id, office_active_id]
                }
            }

        except Exception as e:
            await db.rollback()
            print(f"\n❌ エラー: {str(e)}")
            raise


async def verify_physical_deletion_candidates():
    """
    物理削除対象のレコードを確認
    """
    async with AsyncSessionLocal() as db:
        print("\n" + "=" * 80)
        print("物理削除対象レコードの確認")
        print("=" * 80)

        # 30日以上前に削除されたスタッフを確認
        threshold_date = datetime.now(timezone.utc) - timedelta(days=30)

        stmt = select(Staff).where(
            Staff.is_deleted == True,
            Staff.deleted_at.isnot(None),
            Staff.deleted_at <= threshold_date,
            Staff.is_test_data == True
        )
        result = await db.execute(stmt)
        staff_list = result.scalars().all()

        print(f"\n【物理削除対象スタッフ】 (30日以上前に削除)")
        if staff_list:
            for staff in staff_list:
                days_ago = (datetime.now(timezone.utc) - staff.deleted_at).days
                print(f"  - {staff.email} (ID: {staff.id}, {days_ago}日前削除)")
        else:
            print("  対象なし")

        # 30日以上前に削除された事務所を確認
        stmt = select(Office).where(
            Office.is_deleted == True,
            Office.deleted_at.isnot(None),
            Office.deleted_at <= threshold_date,
            Office.is_test_data == True
        )
        result = await db.execute(stmt)
        office_list = result.scalars().all()

        print(f"\n【物理削除対象事務所】 (30日以上前に削除)")
        if office_list:
            for office in office_list:
                days_ago = (datetime.now(timezone.utc) - office.deleted_at).days
                print(f"  - {office.name} (ID: {office.id}, {days_ago}日前削除)")
        else:
            print("  対象なし")

        return {
            "staff_count": len(staff_list),
            "office_count": len(office_list)
        }


async def update_deleted_at_to_past(email_or_name: str, days_ago: int, is_office: bool = False):
    """
    特定のスタッフまたは事務所のdeleted_atを過去の日付に更新

    Args:
        email_or_name: スタッフのメールアドレスまたは事務所名
        days_ago: 何日前に削除されたことにするか
        is_office: Trueの場合は事務所、Falseの場合はスタッフ
    """
    async with AsyncSessionLocal() as db:
        try:
            new_deleted_at = datetime.now(timezone.utc) - timedelta(days=days_ago)

            if is_office:
                stmt = update(Office).where(
                    Office.name == email_or_name
                ).values(
                    deleted_at=new_deleted_at
                )
                result = await db.execute(stmt)
                print(f"✓ 事務所 '{email_or_name}' のdeleted_atを{days_ago}日前に更新")
            else:
                stmt = update(Staff).where(
                    Staff.email == email_or_name
                ).values(
                    deleted_at=new_deleted_at
                )
                result = await db.execute(stmt)
                print(f"✓ スタッフ '{email_or_name}' のdeleted_atを{days_ago}日前に更新")

            await db.commit()
            print(f"  更新されたレコード数: {result.rowcount}")

        except Exception as e:
            await db.rollback()
            print(f"❌ エラー: {str(e)}")
            raise


async def cleanup_test_data():
    """
    テスト用に作成したデータをクリーンアップ
    """
    async with AsyncSessionLocal() as db:
        try:
            print("\n" + "=" * 80)
            print("テストデータのクリーンアップ")
            print("=" * 80)

            # is_test_data=Trueのスタッフを削除
            stmt = select(Staff).where(Staff.is_test_data == True)
            result = await db.execute(stmt)
            staff_list = result.scalars().all()

            for staff in staff_list:
                await db.delete(staff)

            print(f"✓ テストスタッフ削除: {len(staff_list)}件")

            # is_test_data=Trueの事務所を削除
            stmt = select(Office).where(Office.is_test_data == True)
            result = await db.execute(stmt)
            office_list = result.scalars().all()

            for office in office_list:
                await db.delete(office)

            print(f"✓ テスト事務所削除: {len(office_list)}件")

            await db.commit()
            print("\n✅ クリーンアップ完了")

        except Exception as e:
            await db.rollback()
            print(f"❌ エラー: {str(e)}")
            raise


async def main():
    """
    メイン処理
    """
    import sys

    if len(sys.argv) < 2:
        print("使用方法:")
        print("  python setup_physical_deletion_test_data.py create    - テストデータ作成")
        print("  python setup_physical_deletion_test_data.py verify    - 物理削除対象確認")
        print("  python setup_physical_deletion_test_data.py cleanup   - テストデータクリーンアップ")
        print("  python setup_physical_deletion_test_data.py update <email_or_name> <days_ago> [--office]")
        print("                                                        - deleted_atを更新")
        sys.exit(1)

    command = sys.argv[1]

    if command == "create":
        await create_test_data_for_physical_deletion()
    elif command == "verify":
        await verify_physical_deletion_candidates()
    elif command == "cleanup":
        await cleanup_test_data()
    elif command == "update":
        if len(sys.argv) < 4:
            print("エラー: update には <email_or_name> と <days_ago> が必要です")
            sys.exit(1)
        email_or_name = sys.argv[2]
        days_ago = int(sys.argv[3])
        is_office = "--office" in sys.argv
        await update_deleted_at_to_past(email_or_name, days_ago, is_office)
    else:
        print(f"エラー: 不明なコマンド '{command}'")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
