"""
データベース制約の存在を確認するテスト
"""
import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

pytestmark = pytest.mark.asyncio


async def test_check_calendar_events_table_exists(db_session: AsyncSession):
    """calendar_eventsテーブルが存在することを確認"""
    result = await db_session.execute(
        text("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables
                WHERE table_schema = 'public'
                AND table_name = 'calendar_events'
            );
        """)
    )
    exists = result.scalar()
    print(f"\n=== calendar_events table exists: {exists} ===")
    assert exists is True, "calendar_events table does not exist"


async def test_check_unique_indexes(db_session: AsyncSession):
    """ユニークインデックスが存在することを確認"""
    # calendar_eventsテーブルのインデックスを取得
    result = await db_session.execute(
        text("""
            SELECT
                i.relname as index_name,
                ix.indisunique as is_unique,
                a.attname as column_name,
                pg_get_expr(ix.indpred, ix.indrelid) as index_condition
            FROM pg_class t
            JOIN pg_index ix ON t.oid = ix.indrelid
            JOIN pg_class i ON i.oid = ix.indexrelid
            LEFT JOIN pg_attribute a ON a.attrelid = t.oid AND a.attnum = ANY(ix.indkey)
            WHERE t.relname = 'calendar_events'
            ORDER BY i.relname, a.attnum;
        """)
    )

    indexes = result.fetchall()
    print(f"\n=== Indexes on calendar_events table ===")
    for idx in indexes:
        print(f"Index: {idx.index_name}, Unique: {idx.is_unique}, Column: {idx.column_name}, Condition: {idx.index_condition}")

    # ユニークインデックスを探す
    unique_cycle_type_index = None
    unique_status_type_index = None

    for idx in indexes:
        if idx.index_name == 'idx_calendar_events_cycle_type_unique':
            unique_cycle_type_index = idx
        elif idx.index_name == 'idx_calendar_events_status_type_unique':
            unique_status_type_index = idx

    print(f"\n=== Checking for unique indexes ===")
    print(f"idx_calendar_events_cycle_type_unique found: {unique_cycle_type_index is not None}")
    print(f"idx_calendar_events_status_type_unique found: {unique_status_type_index is not None}")

    if unique_cycle_type_index:
        print(f"Details: {unique_cycle_type_index}")
    if unique_status_type_index:
        print(f"Details: {unique_status_type_index}")


async def test_check_enum_types(db_session: AsyncSession):
    """ENUM型が存在することを確認"""
    result = await db_session.execute(
        text("""
            SELECT
                t.typname as enum_name,
                e.enumlabel as enum_value
            FROM pg_type t
            JOIN pg_enum e ON t.oid = e.enumtypid
            WHERE t.typname IN (
                'calendar_event_type',
                'calendar_sync_status',
                'reminder_pattern_type',
                'event_instance_status'
            )
            ORDER BY t.typname, e.enumsortorder;
        """)
    )

    enums = result.fetchall()
    print(f"\n=== ENUM types ===")

    enum_dict = {}
    for enum in enums:
        if enum.enum_name not in enum_dict:
            enum_dict[enum.enum_name] = []
        enum_dict[enum.enum_name].append(enum.enum_value)

    for enum_name, values in enum_dict.items():
        print(f"{enum_name}: {values}")

    # 必要なENUM型が存在することを確認
    assert 'calendar_event_type' in enum_dict, "calendar_event_type ENUM not found"
    assert 'calendar_sync_status' in enum_dict, "calendar_sync_status ENUM not found"
    assert 'reminder_pattern_type' in enum_dict, "reminder_pattern_type ENUM not found"
    assert 'event_instance_status' in enum_dict, "event_instance_status ENUM not found"


async def test_check_calendar_events_columns(db_session: AsyncSession):
    """calendar_eventsテーブルのカラムを確認"""
    result = await db_session.execute(
        text("""
            SELECT
                column_name,
                data_type,
                is_nullable,
                column_default
            FROM information_schema.columns
            WHERE table_schema = 'public'
            AND table_name = 'calendar_events'
            ORDER BY ordinal_position;
        """)
    )

    columns = result.fetchall()
    print(f"\n=== calendar_events table columns ===")
    for col in columns:
        print(f"Column: {col.column_name}, Type: {col.data_type}, Nullable: {col.is_nullable}, Default: {col.column_default}")

    # 必要なカラムが存在することを確認
    column_names = [col.column_name for col in columns]
    required_columns = [
        'id', 'office_id', 'welfare_recipient_id',
        'support_plan_cycle_id', 'support_plan_status_id',
        'event_type', 'google_calendar_id', 'event_title',
        'event_start_datetime', 'event_end_datetime',
        'sync_status', 'created_at', 'updated_at'
    ]

    for col in required_columns:
        assert col in column_names, f"Required column '{col}' not found in calendar_events table"


async def test_check_foreign_keys(db_session: AsyncSession):
    """外部キー制約を確認"""
    result = await db_session.execute(
        text("""
            SELECT
                kcu.constraint_name,
                kcu.table_name,
                kcu.column_name,
                ccu.table_name AS foreign_table_name,
                ccu.column_name AS foreign_column_name
            FROM information_schema.key_column_usage AS kcu
            JOIN information_schema.referential_constraints AS rc
              ON kcu.constraint_name = rc.constraint_name
              AND kcu.constraint_schema = rc.constraint_schema
            JOIN information_schema.key_column_usage AS ccu
              ON rc.unique_constraint_name = ccu.constraint_name
              AND rc.unique_constraint_schema = ccu.constraint_schema
            WHERE kcu.table_schema = 'public'
            AND kcu.table_name = 'calendar_events'
            ORDER BY kcu.constraint_name;
        """)
    )

    fks = result.fetchall()
    print(f"\n=== Foreign keys on calendar_events table ===")
    for fk in fks:
        print(f"FK: {fk.constraint_name}, Column: {fk.column_name} -> {fk.foreign_table_name}.{fk.foreign_column_name}")

    # 必要な外部キーが存在することを確認
    fk_columns = [fk.column_name for fk in fks]
    assert 'office_id' in fk_columns, "office_id foreign key not found"
    assert 'welfare_recipient_id' in fk_columns, "welfare_recipient_id foreign key not found"


async def test_check_constraints(db_session: AsyncSession):
    """CHECK制約を確認"""
    result = await db_session.execute(
        text("""
            SELECT
                tc.constraint_name,
                tc.constraint_type,
                cc.check_clause
            FROM information_schema.table_constraints AS tc
            LEFT JOIN information_schema.check_constraints AS cc
                ON tc.constraint_name = cc.constraint_name
            WHERE tc.table_name = 'calendar_events'
            AND tc.constraint_type = 'CHECK'
            ORDER BY tc.constraint_name;
        """)
    )

    checks = result.fetchall()
    print(f"\n=== CHECK constraints on calendar_events table ===")
    for check in checks:
        print(f"Constraint: {check.constraint_name}")
        print(f"  Type: {check.constraint_type}")
        print(f"  Clause: {check.check_clause}")

    # 必要なCHECK制約が存在することを確認
    constraint_names = [check.constraint_name for check in checks]

    if 'chk_calendar_events_ref_exclusive' not in constraint_names:
        print("\n!!! WARNING: chk_calendar_events_ref_exclusive constraint NOT FOUND !!!")
        print("Please run the following SQL to add it:")
        print("""
ALTER TABLE calendar_events
ADD CONSTRAINT chk_calendar_events_ref_exclusive
CHECK (
    (support_plan_cycle_id IS NOT NULL AND support_plan_status_id IS NULL) OR
    (support_plan_cycle_id IS NULL AND support_plan_status_id IS NOT NULL)
);
        """)

    assert 'chk_calendar_events_ref_exclusive' in constraint_names, \
        "chk_calendar_events_ref_exclusive constraint not found. Please run check_constraint_fix.sql"
