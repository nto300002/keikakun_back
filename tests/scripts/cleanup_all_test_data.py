"""
蓄積されたテストデータの完全削除スクリプト

目的: test_db_cleanup.pyのエラーにより蓄積された
      376件のstaffs、140件のofficesを削除する

実行方法:
    python tests/scripts/cleanup_all_test_data.py --dry-run  # 削除対象を確認（実際には削除しない）
    python tests/scripts/cleanup_all_test_data.py           # 実際に削除を実行

警告: テスト環境でのみ実行してください
"""
import asyncio
import sys
import os
from sqlalchemy import text, select, func
from sqlalchemy.ext.asyncio import AsyncSession

# プロジェクトルートをPYTHONPATHに追加
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))

from app.db.session import AsyncSessionLocal
from app.models.staff import Staff
from app.models.office import Office


async def count_test_data(db: AsyncSession):
    """テストデータの数を確認"""

    # テストスタッフ数
    staff_query = text("""
        SELECT COUNT(*) FROM staffs
        WHERE email LIKE '%@test.com'
           OR email LIKE '%@example.com'
           OR last_name LIKE '%テスト%'
           OR full_name LIKE '%テスト%'
           OR is_test_data = TRUE
    """)
    staff_result = await db.execute(staff_query)
    staff_count = staff_result.scalar()

    # テスト事務所数
    office_query = text("""
        SELECT COUNT(*) FROM offices
        WHERE name LIKE '%テスト%'
           OR name LIKE '%test%'
           OR name LIKE '%Test%'
           OR is_test_data = TRUE
    """)
    office_result = await db.execute(office_query)
    office_count = office_result.scalar()

    return staff_count, office_count


async def delete_all_test_data(db: AsyncSession, dry_run: bool = False):
    """
    すべてのテストデータを削除

    Args:
        db: データベースセッション
        dry_run: Trueの場合、削除対象を表示するのみで実際には削除しない
    """

    print("=" * 80)
    print("テストデータクリーンアップスクリプト")
    print("=" * 80)

    # 削除前の確認
    staff_count, office_count = await count_test_data(db)

    print(f"\n【削除対象】")
    print(f"  スタッフ: {staff_count}件")
    print(f"  事務所:   {office_count}件")

    if staff_count == 0 and office_count == 0:
        print("\n✅ 削除対象のテストデータはありません")
        return

    if dry_run:
        print("\n⚠️  DRY RUN モード - 実際には削除しません")
        print("   実際に削除する場合は --dry-run オプションを外して実行してください")
        return

    # 確認プロンプト
    print("\n⚠️  この操作は元に戻せません")
    response = input("本当に削除しますか？ (yes/no): ")
    if response.lower() != "yes":
        print("❌ 削除をキャンセルしました")
        return

    print("\n🧹 削除を開始します...")

    try:
        # 1. 削除対象のIDを取得
        print("  1/7 削除対象のIDを取得中...")

        # 削除対象のoffice_idを取得
        office_ids_query = text("""
            SELECT id FROM offices
            WHERE name LIKE '%テスト%'
               OR name LIKE '%test%'
               OR name LIKE '%Test%'
               OR is_test_data = TRUE
        """)
        office_ids_result = await db.execute(office_ids_query)
        office_ids = [row[0] for row in office_ids_result.fetchall()]

        # 削除対象のstaff_idを取得
        staff_ids_query = text("""
            SELECT id FROM staffs
            WHERE email LIKE '%@test.com'
               OR email LIKE '%@example.com'
               OR last_name LIKE '%テスト%'
               OR full_name LIKE '%テスト%'
               OR is_test_data = TRUE
        """)
        staff_ids_result = await db.execute(staff_ids_query)
        staff_ids = [row[0] for row in staff_ids_result.fetchall()]

        print(f"     削除対象: {len(office_ids)}件の事務所、{len(staff_ids)}件のスタッフ")

        # 2. 支援計画関連データの削除
        print("  2/7 支援計画関連データを削除中...")

        if office_ids:
            # plan_deliverables
            pd_result = await db.execute(
                text("""
                    DELETE FROM plan_deliverables
                    WHERE plan_cycle_id IN (
                        SELECT id FROM support_plan_cycles
                        WHERE office_id = ANY(:office_ids)
                    )
                """),
                {"office_ids": office_ids}
            )

            # support_plan_statuses
            sps_result = await db.execute(
                text("DELETE FROM support_plan_statuses WHERE office_id = ANY(:office_ids)"),
                {"office_ids": office_ids}
            )

            # support_plan_cycles
            spc_result = await db.execute(
                text("DELETE FROM support_plan_cycles WHERE office_id = ANY(:office_ids)"),
                {"office_ids": office_ids}
            )

            print(f"     削除: plan_deliverables={pd_result.rowcount}, "
                  f"support_plan_statuses={sps_result.rowcount}, "
                  f"support_plan_cycles={spc_result.rowcount}")

        # 3. 中間テーブルの削除
        print("  3/7 中間テーブルを削除中...")

        if office_ids or staff_ids:
            # office_staffs
            os_result = await db.execute(
                text("""
                    DELETE FROM office_staffs
                    WHERE (office_id = ANY(:office_ids) OR :no_offices)
                       OR (staff_id = ANY(:staff_ids) OR :no_staffs)
                """),
                {
                    "office_ids": office_ids if office_ids else [None],
                    "staff_ids": staff_ids if staff_ids else [None],
                    "no_offices": len(office_ids) == 0,
                    "no_staffs": len(staff_ids) == 0
                }
            )

            # office_welfare_recipients
            owr_result = await db.execute(
                text("DELETE FROM office_welfare_recipients WHERE office_id = ANY(:office_ids)"),
                {"office_ids": office_ids if office_ids else [None]}
            ) if office_ids else None

            print(f"     削除: office_staffs={os_result.rowcount}, "
                  f"office_welfare_recipients={owr_result.rowcount if owr_result else 0}")

        # 4. 通知・承認依頼の削除
        print("  4/7 通知・承認依頼を削除中...")

        if office_ids:
            notices_result = await db.execute(
                text("""
                    DELETE FROM notices
                    WHERE office_id = ANY(:office_ids)
                       OR title LIKE '%テスト%'
                       OR title LIKE '%test%'
                """),
                {"office_ids": office_ids}
            )

            approval_result = await db.execute(
                text("DELETE FROM approval_requests WHERE office_id = ANY(:office_ids)"),
                {"office_ids": office_ids}
            )

            print(f"     削除: notices={notices_result.rowcount}, "
                  f"approval_requests={approval_result.rowcount}")

        # 5. 福祉受給者の削除
        print("  5/7 福祉受給者を削除中...")

        welfare_result = await db.execute(
            text("""
                DELETE FROM welfare_recipients
                WHERE first_name LIKE '%テスト%'
                   OR last_name LIKE '%テスト%'
                   OR first_name LIKE '%test%'
                   OR last_name LIKE '%test%'
            """)
        )

        print(f"     削除: {welfare_result.rowcount}件")

        # 6. 事務所の削除
        print("  6/7 事務所を削除中...")

        if office_ids:
            office_delete_result = await db.execute(
                text("DELETE FROM offices WHERE id = ANY(:office_ids)"),
                {"office_ids": office_ids}
            )
            print(f"     削除: {office_delete_result.rowcount}件")

        # 7. スタッフの削除
        print("  7/7 スタッフを削除中...")

        if staff_ids:
            staff_delete_result = await db.execute(
                text("DELETE FROM staffs WHERE id = ANY(:staff_ids)"),
                {"staff_ids": staff_ids}
            )
            print(f"     削除: {staff_delete_result.rowcount}件")

        # コミット
        await db.commit()

        # 削除後の確認
        remaining_staff, remaining_office = await count_test_data(db)

        print("\n" + "=" * 80)
        print("削除完了")
        print("=" * 80)
        print(f"残存スタッフ数: {remaining_staff}件")
        print(f"残存事務所数:   {remaining_office}件")

        if remaining_staff > 0 or remaining_office > 0:
            print("\n⚠️  一部のテストデータが残っています。手動確認が必要です。")
        else:
            print("\n✅ すべてのテストデータが正常に削除されました")

    except Exception as e:
        await db.rollback()
        print(f"\n❌ エラーが発生しました: {str(e)}")
        raise


async def main():
    """メイン処理"""

    # 環境変数の確認
    test_db_url = os.getenv("TEST_DATABASE_URL")
    testing_flag = os.getenv("TESTING")

    if not test_db_url:
        print("❌ TEST_DATABASE_URL環境変数が設定されていません")
        sys.exit(1)

    if "test" not in test_db_url.lower() and "dev" not in test_db_url.lower():
        print("❌ 本番環境のデータベースURLが検出されました")
        print("   このスクリプトはテスト環境でのみ実行できます")
        sys.exit(1)

    # コマンドライン引数の確認
    dry_run = "--dry-run" in sys.argv

    async with AsyncSessionLocal() as db:
        await delete_all_test_data(db, dry_run=dry_run)


if __name__ == "__main__":
    asyncio.run(main())
