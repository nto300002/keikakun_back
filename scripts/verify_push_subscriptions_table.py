"""
push_subscriptionsテーブルの存在確認スクリプト

使用方法:
    python scripts/verify_push_subscriptions_table.py
"""
import asyncio
import sys
from pathlib import Path

# プロジェクトルートをパスに追加
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import text
from app.db.session import AsyncSessionLocal


async def verify_push_subscriptions_table():
    """push_subscriptionsテーブルの存在と構造を確認"""

    async with AsyncSessionLocal() as db:
        print("=" * 80)
        print("Push Subscriptions Table Verification")
        print("=" * 80)
        print()

        # 1. テーブル存在確認
        print("[1] Checking if push_subscriptions table exists...")
        result = await db.execute(
            text("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables
                    WHERE table_schema = 'public'
                    AND table_name = 'push_subscriptions'
                )
            """)
        )
        table_exists = result.scalar()

        if table_exists:
            print("✅ Table 'push_subscriptions' exists")
        else:
            print("❌ Table 'push_subscriptions' NOT found")
            return

        print()

        # 2. カラム構造確認
        print("[2] Checking table structure...")
        result = await db.execute(
            text("""
                SELECT
                    column_name,
                    data_type,
                    is_nullable,
                    column_default
                FROM information_schema.columns
                WHERE table_name = 'push_subscriptions'
                ORDER BY ordinal_position
            """)
        )
        columns = result.fetchall()

        print(f"{'Column Name':<20} {'Data Type':<30} {'Nullable':<10} {'Default':<20}")
        print("-" * 80)
        for col in columns:
            print(f"{col[0]:<20} {col[1]:<30} {col[2]:<10} {str(col[3] or ''):<20}")

        print()

        # 3. インデックス確認
        print("[3] Checking indexes...")
        result = await db.execute(
            text("""
                SELECT
                    indexname,
                    indexdef
                FROM pg_indexes
                WHERE tablename = 'push_subscriptions'
                ORDER BY indexname
            """)
        )
        indexes = result.fetchall()

        for idx in indexes:
            print(f"  - {idx[0]}")
            print(f"    {idx[1]}")

        print()

        # 4. 外部キー制約確認
        print("[4] Checking foreign key constraints...")
        result = await db.execute(
            text("""
                SELECT
                    conname AS constraint_name,
                    pg_get_constraintdef(oid) AS constraint_definition
                FROM pg_constraint
                WHERE conrelid = 'push_subscriptions'::regclass
                  AND contype = 'f'
            """)
        )
        fkeys = result.fetchall()

        for fk in fkeys:
            print(f"  - {fk[0]}")
            print(f"    {fk[1]}")

        print()

        # 5. UNIQUE制約確認
        print("[5] Checking unique constraints...")
        result = await db.execute(
            text("""
                SELECT
                    conname AS constraint_name,
                    pg_get_constraintdef(oid) AS constraint_definition
                FROM pg_constraint
                WHERE conrelid = 'push_subscriptions'::regclass
                  AND contype = 'u'
            """)
        )
        uniques = result.fetchall()

        for uq in uniques:
            print(f"  - {uq[0]}")
            print(f"    {uq[1]}")

        print()

        # 6. トリガー確認
        print("[6] Checking triggers...")
        result = await db.execute(
            text("""
                SELECT
                    trigger_name,
                    event_manipulation,
                    action_statement
                FROM information_schema.triggers
                WHERE event_object_table = 'push_subscriptions'
            """)
        )
        triggers = result.fetchall()

        if triggers:
            for trig in triggers:
                print(f"  - {trig[0]} ({trig[1]})")
                print(f"    {trig[2]}")
        else:
            print("  No triggers found")

        print()

        # 7. レコード数確認
        print("[7] Checking record count...")
        result = await db.execute(
            text("SELECT COUNT(*) FROM push_subscriptions")
        )
        count = result.scalar()
        print(f"  Current records: {count}")

        print()
        print("=" * 80)
        print("✅ Verification completed successfully!")
        print("=" * 80)


if __name__ == "__main__":
    asyncio.run(verify_push_subscriptions_table())
