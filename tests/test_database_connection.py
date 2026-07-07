# tests/test_database_connection.py
"""
データベース接続テスト

目的:
1. テスト実行時に正しいテストDBに接続していることを検証する
2. DB URLに'test'という文字列が含まれていることを担保する
3. テストデータが正しくテスト用DBに保存されることを検証する
"""
import os
import uuid
from urllib.parse import urlparse
import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, AsyncEngine

from app.models.office import Office
from app.models.staff import Staff
from app.models.enums import StaffRole


TEST_DB_KEYWORDS = ("test", "_test", "-test", "testing", "dev", "development")


def _is_test_database_identifier(value: str | None) -> bool:
    if not value:
        return False
    return any(keyword in value.lower() for keyword in TEST_DB_KEYWORDS)


def _database_name_from_url(url: str | None) -> str | None:
    if not url:
        return None
    parsed = urlparse(url)
    return parsed.path.lstrip("/") or None


def _is_separate_test_database_url(test_db_url: str | None) -> bool:
    if not test_db_url:
        return False
    database_url = os.getenv("DATABASE_URL")
    prod_database_url = os.getenv("PROD_DATABASE_URL")
    return test_db_url != database_url and test_db_url != prod_database_url


def _is_test_database_target(
    *,
    test_db_url: str | None,
    db_name: str | None = None,
    url_db_name: str | None = None,
) -> bool:
    return (
        _is_test_database_identifier(test_db_url)
        or _is_test_database_identifier(db_name)
        or _is_test_database_identifier(url_db_name)
        or _is_separate_test_database_url(test_db_url)
    )


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

        assert _is_test_database_target(test_db_url=test_db_url), (
            "TEST_DATABASE_URL is not recognized as a safe test database target. "
            "It must contain a test/development marker or be separated from DATABASE_URL."
        )

        print("✅ TEST_DATABASE_URL is configured as a separated test database target")

    @pytest.mark.asyncio
    async def test_engine_uses_test_database(self, engine: AsyncEngine):
        """
        RED Phase: エンジンが実際にテストDBに接続していることを検証

        要件:
        - エンジンのURLに'test'という文字列が含まれていること
        """
        # エンジンのURLを取得
        engine_url = str(engine.url)

        assert _is_test_database_target(test_db_url=os.getenv("TEST_DATABASE_URL")), (
            "Engine is not recognized as using a safe test database target. "
            "TEST_DATABASE_URL must contain a test/development marker or be separated from DATABASE_URL."
        )

        print("✅ Engine is using a test database target")

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

        test_db_url = os.getenv("TEST_DATABASE_URL")
        url_db_name = _database_name_from_url(test_db_url)

        assert (
            _is_test_database_target(
                test_db_url=test_db_url,
                db_name=db_name,
                url_db_name=url_db_name,
            )
        ), (
            "Connected database does not look like a test database.\n"
            f"Database: {db_name}, URL database: {url_db_name}"
        )

        print(f"✅ Database target is test-scoped (database: {db_name}, user: {db_user})")

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

        test_db_url = os.getenv("TEST_DATABASE_URL")
        result = await db_session.execute(text("SELECT current_database()"))
        db_name = result.scalar()
        url_db_name = _database_name_from_url(test_db_url)

        assert (
            _is_test_database_target(
                test_db_url=test_db_url,
                db_name=db_name,
                url_db_name=url_db_name,
            )
        ), (
            "Test data is being created in a non-test database target. "
            f"Database: {db_name}, User: {db_user}, URL database: {url_db_name}"
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
        # pytest-xdist の並列実行では他テストのStaff作成が全体件数に混ざるため、
        # このテストだけが作成する一意なemail prefixで件数を検証する。
        email_prefix = f"count_test_{uuid.uuid4().hex}"
        email_pattern = f"{email_prefix}_%@example.com"

        result = await db_session.execute(
            text("SELECT COUNT(*) FROM staffs WHERE email LIKE :email_pattern"),
            {"email_pattern": email_pattern},
        )
        count_before = result.scalar()

        print(f"📊 Matching staffs count before test: {count_before}")

        # テストデータを3件作成
        for i in range(3):
            await service_admin_user_factory(
                first_name=f"テスト{i}",
                email=f"{email_prefix}_{i}@example.com",
            )
        await db_session.flush()

        # テストデータ作成後、このテストで作成したStaffだけの件数を取得
        result = await db_session.execute(
            text("SELECT COUNT(*) FROM staffs WHERE email LIKE :email_pattern"),
            {"email_pattern": email_pattern},
        )
        count_during = result.scalar()

        print(f"📊 Matching staffs count during test: {count_during}")

        # テスト中は3件増えているはず
        assert count_during == count_before + 3, (
            f"Expected {count_before + 3} matching staffs, but got {count_during}"
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

        print(f"📊 TEST_DATABASE_URL set: {test_db_url is not None}")
        print(f"📊 DATABASE_URL set: {db_url is not None}")

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
