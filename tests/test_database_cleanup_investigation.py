# tests/test_database_cleanup_investigation.py
"""
データベースクリーンアップの調査テスト

目的:
1. 現在のDBにどれだけデータが残っているか確認
2. テスト実行後にデータが残る原因を特定
3. クリーンアップ機能の動作を検証
"""
import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


class TestDatabaseDataInvestigation:
    """データベース内のデータを調査するテスト"""

    @pytest.mark.asyncio
    async def test_check_current_data_counts(self, db_session: AsyncSession):
        """
        現在のDBに存在するデータ数を確認

        目的: テスト実行前にどれだけデータが残っているか把握する
        """
        # 主要テーブルのデータ数を取得
        tables = [
            "staffs",
            "offices",
            "office_staffs",
            "welfare_recipients",
            "office_welfare_recipients",
            "approval_requests",
            "notices"
        ]

        print("\n" + "=" * 80)
        print("📊 Current Database Data Counts")
        print("=" * 80)

        total_count = 0
        for table in tables:
            result = await db_session.execute(text(f"SELECT COUNT(*) FROM {table}"))
            count = result.scalar()
            total_count += count
            status = "⚠️ " if count > 0 else "✅ "
            print(f"{status}{table:30s}: {count:5d} rows")

        print("=" * 80)
        print(f"Total records across all tables: {total_count}")
        print("=" * 80 + "\n")

        if total_count > 0:
            print("⚠️  WARNING: Database contains leftover test data!")
            print("   This indicates that cleanup is not working correctly.")

    @pytest.mark.asyncio
    async def test_check_staff_emails_pattern(self, db_session: AsyncSession):
        """
        Staffsテーブルのメールアドレスパターンを確認

        目的: ファクトリで生成されたテストデータかどうかを判別する
        """
        result = await db_session.execute(
            text("""
                SELECT email, role, created_at
                FROM staffs
                ORDER BY created_at DESC
                LIMIT 20
            """)
        )
        rows = result.fetchall()

        if not rows:
            print("✅ No staff records found in database")
            return

        print("\n" + "=" * 80)
        print("📧 Staff Email Patterns (Latest 20)")
        print("=" * 80)

        factory_pattern_count = 0
        for email, role, created_at in rows:
            is_factory = any([
                "admin_" in email and "@example.com" in email,
                "employee_" in email and "@example.com" in email,
                "manager_" in email and "@example.com" in email,
                "owner_" in email and "@example.com" in email,
                "@test.com" in email
            ])

            marker = "🏭 FACTORY" if is_factory else "❓ UNKNOWN"
            if is_factory:
                factory_pattern_count += 1

            print(f"{marker} | {email:50s} | {role:10s} | {created_at}")

        print("=" * 80)
        print(f"Factory-generated emails: {factory_pattern_count}/{len(rows)}")
        print("=" * 80 + "\n")

        if factory_pattern_count > 0:
            print("⚠️  WARNING: Factory-generated test data found!")
            print("   These should have been cleaned up after tests.")

    @pytest.mark.asyncio
    async def test_check_office_names_pattern(self, db_session: AsyncSession):
        """
        Officesテーブルの名前パターンを確認

        目的: ファクトリで生成されたテストデータかどうかを判別する
        """
        result = await db_session.execute(
            text("""
                SELECT name, type, created_at
                FROM offices
                ORDER BY created_at DESC
                LIMIT 20
            """)
        )
        rows = result.fetchall()

        if not rows:
            print("✅ No office records found in database")
            return

        print("\n" + "=" * 80)
        print("🏢 Office Name Patterns (Latest 20)")
        print("=" * 80)

        factory_pattern_count = 0
        for name, type_, created_at in rows:
            is_factory = "テスト事業所" in name

            marker = "🏭 FACTORY" if is_factory else "❓ UNKNOWN"
            if is_factory:
                factory_pattern_count += 1

            print(f"{marker} | {name:40s} | {type_:20s} | {created_at}")

        print("=" * 80)
        print(f"Factory-generated offices: {factory_pattern_count}/{len(rows)}")
        print("=" * 80 + "\n")

        if factory_pattern_count > 0:
            print("⚠️  WARNING: Factory-generated test data found!")
            print("   These should have been cleaned up after tests.")


class TestCleanupBehaviorVerification:
    """クリーンアップの動作を検証するテスト"""

    @pytest.mark.asyncio
    async def test_transaction_rollback_works(
        self,
        db_session: AsyncSession,
        service_admin_user_factory
    ):
        """
        トランザクションのロールバックが機能することを検証

        要件:
        - db_sessionフィクスチャはネストトランザクションを使用
        - テスト終了後にデータは自動的にロールバックされる
        """
        # テスト開始時のStaffデータ数
        result = await db_session.execute(text("SELECT COUNT(*) FROM staffs"))
        count_before = result.scalar()

        print(f"\n📊 Staff count before creating test data: {count_before}")

        # テストデータを作成
        test_user = await service_admin_user_factory(
            first_name="ロールバックテスト",
            email="rollback_test@example.com"
        )
        await db_session.flush()

        # データが作成されたことを確認
        result = await db_session.execute(
            text("SELECT COUNT(*) FROM staffs WHERE email = :email"),
            {"email": "rollback_test@example.com"}
        )
        count_created = result.scalar()
        assert count_created == 1, "Test data was not created"

        print(f"✅ Test data created successfully")
        print(f"   Email: {test_user.email}")

        # テスト終了時のStaffデータ数
        result = await db_session.execute(text("SELECT COUNT(*) FROM staffs"))
        count_after = result.scalar()

        print(f"📊 Staff count after creating test data: {count_after}")
        print(f"   Expected to rollback to {count_before} after test ends")

        # このテストが終了すると、db_sessionのトランザクションがロールバックされ、
        # 作成したデータは削除されるはず

    @pytest.mark.asyncio
    async def test_verify_previous_test_rolled_back(self, db_session: AsyncSession):
        """
        前のテスト（test_transaction_rollback_works）で作成したデータが
        ロールバックされていることを確認

        要件:
        - 前のテストで作成した'rollback_test@example.com'が存在しないこと
        """
        result = await db_session.execute(
            text("SELECT COUNT(*) FROM staffs WHERE email = :email"),
            {"email": "rollback_test@example.com"}
        )
        count = result.scalar()

        if count == 0:
            print("✅ Previous test data was successfully rolled back")
        else:
            print("❌ Previous test data was NOT rolled back!")
            print(f"   Found {count} records with email 'rollback_test@example.com'")

        assert count == 0, (
            "Previous test data was not rolled back. "
            "This indicates a problem with transaction management."
        )


class TestCleanupFunctionVerification:
    """クリーンアップ関数の動作を検証するテスト"""

    @pytest.mark.asyncio
    async def test_safe_cleanup_detection(self, db_session: AsyncSession):
        """
        SafeTestDataCleanupがファクトリデータを正しく検出できるか検証

        目的: クリーンアップ対象のデータパターンを確認
        """
        from tests.utils.safe_cleanup import SafeTestDataCleanup

        # ファクトリパターンを持つStaffを検出
        result = await db_session.execute(
            text("""
                SELECT COUNT(*) FROM staffs
                WHERE email LIKE '%@example.com'
                   OR email LIKE '%@test.com'
            """)
        )
        factory_staff_count = result.scalar()

        print(f"\n📊 Potential factory-generated staff: {factory_staff_count}")

        # ファクトリパターンを持つOfficeを検出
        result = await db_session.execute(
            text("""
                SELECT COUNT(*) FROM offices
                WHERE name LIKE '%テスト事業所%'
            """)
        )
        factory_office_count = result.scalar()

        print(f"📊 Potential factory-generated offices: {factory_office_count}")

        if factory_staff_count > 0 or factory_office_count > 0:
            print("\n⚠️  Factory-generated data detected!")
            print("   These should be cleaned up by SafeTestDataCleanup")
            print("\n💡 Recommendation:")
            print("   Run the cleanup script to remove factory-generated data:")
            print("   docker-compose exec backend python scripts/cleanup_test_db.py")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
