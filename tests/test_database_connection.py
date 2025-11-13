# tests/test_database_connection.py
"""
データベース接続テスト

目的:
1. テスト実行時に正しいテストDBに接続していることを検証する
2. DB URLに'test'という文字列が含まれていることを担保する
3. テストデータが正しくテスト用DBに保存されることを検証する
"""
import os
import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, AsyncEngine

from app.models.office import Office
from app.models.staff import Staff
from app.models.enums import StaffRole


class TestDatabaseConnection:
    """データベース接続の検証テスト"""

    @pytest.mark.asyncio
    async def test_database_url_contains_test(self, engine: AsyncEngine):
        """
        RED Phase: テストDBのURLに'test'という文字列が含まれていることを検証

        要件:
        - TEST_DATABASE_URL環境変数が設定されていること
        - URLに'test'という文字列が含まれていること（ユーザー名、ホスト名、またはDB名）
        """
        # 環境変数からTEST_DATABASE_URLを取得
        test_db_url = os.getenv("TEST_DATABASE_URL")

        # TEST_DATABASE_URLが設定されていることを確認
        assert test_db_url is not None, (
            "TEST_DATABASE_URL environment variable is not set. "
            "Tests should use a dedicated test database."
        )

        # URLに'test'という文字列が含まれていることを確認
        assert "test" in test_db_url.lower(), (
            f"TEST_DATABASE_URL does not contain 'test': {test_db_url}\n"
            "This is a safety check to prevent accidentally running tests against "
            "a production or development database."
        )

        print(f"✅ TEST_DATABASE_URL is correctly configured: {test_db_url}")

    @pytest.mark.asyncio
    async def test_engine_uses_test_database(self, engine: AsyncEngine):
        """
        RED Phase: エンジンが実際にテストDBに接続していることを検証

        要件:
        - エンジンのURLに'test'という文字列が含まれていること
        """
        # エンジンのURLを取得
        engine_url = str(engine.url)

        # エンジンのURLに'test'という文字列が含まれていることを確認
        assert "test" in engine_url.lower(), (
            f"Engine URL does not contain 'test': {engine_url}\n"
            "The test engine should be connected to a test database."
        )

        print(f"✅ Engine is using test database: {engine_url}")

    @pytest.mark.asyncio
    async def test_can_connect_to_database(self, db_session: AsyncSession):
        """
        テストDBに接続できることを検証

        要件:
        - DBに接続し、簡単なクエリを実行できること
        """
        # 簡単なクエリを実行してDB接続を確認
        result = await db_session.execute(text("SELECT 1 as test_value"))
        row = result.fetchone()

        assert row is not None, "Failed to connect to database"
        assert row[0] == 1, "Query returned unexpected value"

        print("✅ Successfully connected to test database")

    @pytest.mark.asyncio
    async def test_database_name_verification(self, db_session: AsyncSession):
        """
        接続しているデータベース名を確認

        要件:
        - 接続しているDBの名前を表示する（情報収集）
        """
        # 現在のデータベース名を取得
        result = await db_session.execute(text("SELECT current_database()"))
        db_name = result.scalar()

        print(f"📊 Connected to database: {db_name}")

        # ユーザー名も取得
        result = await db_session.execute(text("SELECT current_user"))
        db_user = result.scalar()

        print(f"📊 Connected as user: {db_user}")

        # ユーザー名に'test'が含まれていることを確認（Neonブランチの区別）
        assert "test" in db_user.lower(), (
            f"Database user does not contain 'test': {db_user}\n"
            "This suggests the connection is not using the test branch."
        )

        print(f"✅ Database user '{db_user}' contains 'test'")

    @pytest.mark.asyncio
    async def test_test_data_is_stored_in_test_db(
        self,
        db_session: AsyncSession,
        service_admin_user_factory
    ):
        """
        RED Phase: テストデータが正しくテスト用DBに保存されることを検証

        要件:
        - ファクトリで作成したデータがDBに保存されること
        - 保存されたデータを取得できること
        - 接続しているDBがテスト用DBであること（ユーザー名に'test'が含まれる）
        """
        # 1. 現在接続しているDBユーザーを確認
        result = await db_session.execute(text("SELECT current_user"))
        db_user = result.scalar()

        assert "test" in db_user.lower(), (
            f"Test data is being created in non-test database! User: {db_user}"
        )

        # 2. テストデータを作成
        test_user = await service_admin_user_factory(
            first_name="接続テスト",
            last_name="ユーザー",
            email="connection_test@example.com"
        )
        await db_session.flush()

        # 3. 作成したデータをDBから再取得
        result = await db_session.execute(
            text("SELECT email, first_name, last_name FROM staffs WHERE email = :email"),
            {"email": "connection_test@example.com"}
        )
        row = result.fetchone()

        # 4. データが正しく保存されていることを確認
        assert row is not None, "Test data was not saved to database"
        assert row[0] == "connection_test@example.com", "Email mismatch"
        assert row[1] == "接続テスト", "First name mismatch"
        assert row[2] == "ユーザー", "Last name mismatch"

        print(f"✅ Test data successfully stored in test database (user: {db_user})")
        print(f"   Created user: {row[1]} {row[2]} ({row[0]})")

    @pytest.mark.asyncio
    async def test_data_count_before_and_after_test(
        self,
        db_session: AsyncSession,
        service_admin_user_factory
    ):
        """
        テスト前後のデータ数を比較し、クリーンアップを検証

        要件:
        - テスト実行後にデータがロールバックされること（db_sessionのトランザクション）
        """
        # テスト開始時のStaffデータ数を取得
        result = await db_session.execute(text("SELECT COUNT(*) FROM staffs"))
        count_before = result.scalar()

        print(f"📊 Staffs count before test: {count_before}")

        # テストデータを3件作成
        for i in range(3):
            await service_admin_user_factory(
                first_name=f"テスト{i}",
                email=f"count_test_{i}@example.com"
            )
        await db_session.flush()

        # テストデータ作成後のStaffデータ数を取得
        result = await db_session.execute(text("SELECT COUNT(*) FROM staffs"))
        count_during = result.scalar()

        print(f"📊 Staffs count during test: {count_during}")

        # テスト中は3件増えているはず
        assert count_during == count_before + 3, (
            f"Expected {count_before + 3} staffs, but got {count_during}"
        )

        print("✅ Test data was created successfully")
        print("⚠️  Note: Data will be rolled back after this test (db_session transaction)")


class TestDatabaseIsolation:
    """データベースの分離を検証するテスト"""

    @pytest.mark.asyncio
    async def test_environment_variable_priority(self):
        """
        環境変数の優先順位を検証

        要件:
        - TEST_DATABASE_URLが設定されている場合、それが優先されること
        - DATABASE_URLよりもTEST_DATABASE_URLが優先されること
        """
        test_db_url = os.getenv("TEST_DATABASE_URL")
        db_url = os.getenv("DATABASE_URL")

        print(f"📊 TEST_DATABASE_URL: {test_db_url}")
        print(f"📊 DATABASE_URL: {db_url}")

        # TEST_DATABASE_URLが設定されていること
        assert test_db_url is not None, "TEST_DATABASE_URL is not set"

        # TEST_DATABASE_URLとDATABASE_URLが異なること
        assert test_db_url != db_url, (
            "TEST_DATABASE_URL and DATABASE_URL are the same! "
            "Tests should use a separate database."
        )

        print("✅ TEST_DATABASE_URL is correctly separated from DATABASE_URL")

    @pytest.mark.asyncio
    async def test_verify_not_using_production_database(self, engine: AsyncEngine):
        """
        本番DBに接続していないことを検証

        要件:
        - テスト用のブランチ/データベースを使用していること
        - 'prod'が含まれている場合でも、'test'キーワードがあればOK（例: prod_test）
        """
        engine_url = str(engine.url).lower()

        # テスト環境のキーワードがあればOK
        test_keywords = ['test', '_test', '-test', 'testing', 'dev', 'development']
        is_test_env = any(keyword in engine_url for keyword in test_keywords)

        if is_test_env:
            print(f"✅ Using test/development database: {engine_url[:80]}...")
            return

        # テストキーワードがない場合、本番キーワードがあればNG
        production_keywords = ['prod', 'production', 'main', 'live']
        is_production = any(keyword in engine_url for keyword in production_keywords)

        assert not is_production, (
            f"DANGER: Engine appears to be connected to production database: {engine_url}\n"
            f"URL must contain one of these test keywords: {test_keywords}"
        )

        print("✅ Not connected to production database")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
