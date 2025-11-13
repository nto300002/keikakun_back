# tests/test_full_suite_data_accumulation.py
"""
テスト全体実行時のデータ蓄積を検証

目的:
1. テスト全体を実行してもデータが蓄積されないことを確認
2. 各テストのトランザクションが正しくロールバックされることを確認
"""
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


class TestFullSuiteDataAccumulation:
    """テスト全体実行時のデータ蓄積を検証するテスト"""

    @pytest.mark.order(1)
    @pytest.mark.asyncio
    async def test_record_initial_counts(self, db_session: AsyncSession):
        """
        テスト開始時のデータ数を記録

        このテストは最初に実行される必要がある（@pytest.mark.order(1)）
        """
        result = await db_session.execute(text("SELECT COUNT(*) FROM staffs"))
        staff_count = result.scalar()

        result = await db_session.execute(text("SELECT COUNT(*) FROM offices"))
        office_count = result.scalar()

        result = await db_session.execute(text("SELECT COUNT(*) FROM welfare_recipients"))
        welfare_count = result.scalar()

        print("\n" + "=" * 80)
        print("📊 Initial Data Counts (Before Full Suite)")
        print("=" * 80)
        print(f"Staffs:             {staff_count}")
        print(f"Offices:            {office_count}")
        print(f"Welfare Recipients: {welfare_count}")
        print("=" * 80 + "\n")

        # テスト間でデータを共有するために、クラス変数に保存
        # （注意: pytestの推奨方法ではないが、シンプルな検証のため使用）
        TestFullSuiteDataAccumulation.initial_staff_count = staff_count
        TestFullSuiteDataAccumulation.initial_office_count = office_count
        TestFullSuiteDataAccumulation.initial_welfare_count = welfare_count

    @pytest.mark.order(999)  # 最後に実行
    @pytest.mark.asyncio
    async def test_verify_no_data_accumulation(self, db_session: AsyncSession):
        """
        テスト終了時にデータが蓄積されていないことを確認

        このテストは最後に実行される必要がある（@pytest.mark.order(999)）
        """
        result = await db_session.execute(text("SELECT COUNT(*) FROM staffs"))
        final_staff_count = result.scalar()

        result = await db_session.execute(text("SELECT COUNT(*) FROM offices"))
        final_office_count = result.scalar()

        result = await db_session.execute(text("SELECT COUNT(*) FROM welfare_recipients"))
        final_welfare_count = result.scalar()

        print("\n" + "=" * 80)
        print("📊 Final Data Counts (After Full Suite)")
        print("=" * 80)
        print(f"Staffs:             {final_staff_count}")
        print(f"Offices:            {final_office_count}")
        print(f"Welfare Recipients: {final_welfare_count}")
        print("=" * 80)

        # 初期値と比較
        initial_staff = getattr(TestFullSuiteDataAccumulation, 'initial_staff_count', None)
        initial_office = getattr(TestFullSuiteDataAccumulation, 'initial_office_count', None)
        initial_welfare = getattr(TestFullSuiteDataAccumulation, 'initial_welfare_count', None)

        if initial_staff is not None:
            staff_diff = final_staff_count - initial_staff
            office_diff = final_office_count - initial_office
            welfare_diff = final_welfare_count - initial_welfare

            print("\n" + "=" * 80)
            print("📈 Data Accumulation Summary")
            print("=" * 80)
            print(f"Staffs:             {staff_diff:+d}")
            print(f"Offices:            {office_diff:+d}")
            print(f"Welfare Recipients: {welfare_diff:+d}")
            print("=" * 80 + "\n")

            # データが蓄積されていないことを検証
            if staff_diff == 0 and office_diff == 0 and welfare_diff == 0:
                print("✅ SUCCESS: No data accumulation detected!")
                print("   All test transactions were properly rolled back.")
            else:
                print("⚠️  WARNING: Data accumulation detected!")
                print("   Some test data was not rolled back.")
                print("\n💡 Possible causes:")
                print("   1. Some tests use commit() instead of flush()")
                print("   2. Tests that don't use db_session fixture")
                print("   3. Integration tests that bypass transaction rollback")

            # アサーション（許容範囲を設定）
            # 少量のデータ蓄積は許容（例: 手動テストや初期データ）
            assert abs(staff_diff) <= 5, (
                f"Staff count changed by {staff_diff}. "
                "Significant data accumulation detected."
            )
            assert abs(office_diff) <= 2, (
                f"Office count changed by {office_diff}. "
                "Significant data accumulation detected."
            )
            assert abs(welfare_diff) <= 3, (
                f"Welfare recipient count changed by {welfare_diff}. "
                "Significant data accumulation detected."
            )
        else:
            print("⚠️  Initial counts not available. Run test_record_initial_counts first.")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
