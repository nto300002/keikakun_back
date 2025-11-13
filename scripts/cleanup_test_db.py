"""
⚠️ 手動実行専用の強力なクリーンアップスクリプト ⚠️

このスクリプトはテストデータベースの全データを削除します。
本番環境では絶対に実行しないでください。

使用方法:
    docker-compose exec backend python scripts/cleanup_test_db.py

安全性:
- TEST_DATABASE_URLが明示的に設定されている必要があります
- 本番環境のキーワード（prod, production等）が含まれている場合は実行を拒否
- 実行前に確認プロンプトが表示されます
"""
import asyncio
import os
import sys
from pathlib import Path

# プロジェクトルートをパスに追加
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import text, create_engine
from sqlalchemy.orm import sessionmaker, Session


def verify_test_environment() -> str:
    """
    テスト環境であることを確認し、本番環境での実行を防ぐ

    Returns:
        テストデータベースのURL

    Raises:
        SystemExit: 本番環境と判断された場合、またはキャンセルされた場合
    """
    test_db_url = os.getenv("TEST_DATABASE_URL")

    # 1. TEST_DATABASE_URLが設定されていることを確認
    if not test_db_url:
        print("=" * 70)
        print("❌ ERROR: TEST_DATABASE_URL environment variable is not set")
        print("=" * 70)
        print()
        print("This script requires TEST_DATABASE_URL to be explicitly set.")
        print("This is a safety measure to prevent accidental execution on")
        print("production databases.")
        print()
        print("Please set TEST_DATABASE_URL and try again.")
        print()
        sys.exit(1)

    # 2. 本番環境のキーワードチェック
    production_keywords = ['prod', 'production', 'main', 'live', 'master']
    found_keywords = [kw for kw in production_keywords if kw in test_db_url.lower()]

    if found_keywords:
        print("=" * 70)
        print("❌ ERROR: Production database detected!")
        print("=" * 70)
        print()
        print(f"Database URL contains production keywords: {', '.join(found_keywords)}")
        print(f"URL: {test_db_url[:80]}...")
        print()
        print("This script cannot be run on production databases.")
        print()
        sys.exit(1)

    # 3. 確認プロンプト（環境変数でスキップ可能）
    skip_confirmation = os.getenv("SKIP_CLEANUP_CONFIRMATION", "").lower() == "true"

    if not skip_confirmation:
        print("=" * 70)
        print("⚠️  WARNING: DESTRUCTIVE OPERATION")
        print("=" * 70)
        print()
        print("This will DELETE ALL DATA from the following database:")
        print(f"  {test_db_url[:80]}...")
        print()
        print("This operation cannot be undone.")
        print()

        response = input("Type 'DELETE ALL DATA' to confirm (or anything else to cancel): ")

        if response != "DELETE ALL DATA":
            print()
            print("✅ Operation cancelled - no data was deleted")
            print()
            sys.exit(0)

        print()
        print("⚠️  Proceeding with deletion...")
        print()
    else:
        print("=" * 70)
        print("⚠️  AUTO-CONFIRMED: Skipping confirmation prompt")
        print("=" * 70)
        print()

    return test_db_url


def cleanup_database():
    """テストデータベースのすべてのデータを削除"""
    # 安全性チェック
    test_db_url = verify_test_environment()

    print(f"🔌 接続先: {test_db_url[:50]}...")

    # エンジンとセッションを作成
    engine = create_engine(test_db_url, echo=False)
    session_maker = sessionmaker(bind=engine)

    with session_maker() as session:
        # 削除対象のテーブル（依存関係の逆順）
        tables = [
            "plan_deliverables",
            "support_plan_statuses",
            "support_plan_cycles",
            "calendar_event_series",
            "calendar_events",
            "office_calendar_accounts",
            "notices",
            "employee_action_requests",  # 追加
            "role_change_requests",
            "office_welfare_recipients",
            "welfare_recipients",
            "office_staffs",
            "offices",
            "staffs",
        ]

        print("\n🧹 データベースクリーンアップを開始...")
        deleted_counts = {}

        for table in tables:
            try:
                # 削除前のカウント
                count_result = session.execute(
                    text(f"SELECT COUNT(*) FROM {table}")
                )
                count = count_result.scalar()

                if count > 0:
                    # DELETE実行
                    session.execute(text(f"DELETE FROM {table}"))
                    deleted_counts[table] = count
                    print(f"  ✓ {table}: {count}件削除")

            except Exception as e:
                print(f"  ❌ {table}: エラー - {e}")

        session.commit()

        print("\n" + "=" * 50)
        print("✅ データベースクリーンアップ完了")
        print("=" * 50)

        if deleted_counts:
            total = sum(deleted_counts.values())
            print(f"\n合計削除数: {total}件\n")
            for table, count in sorted(
                deleted_counts.items(), key=lambda x: x[1], reverse=True
            ):
                print(f"  {table}: {count}件")
        else:
            print("\n削除するデータはありませんでした")

    engine.dispose()


if __name__ == "__main__":
    cleanup_database()
