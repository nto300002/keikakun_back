"""
Clean up E2E staffs and their related offices.

Default behavior is a dry run. Add --execute to run the destructive SQL.

Targets:
    - staffs.email contains both "e2e_staff" and "@example.com"
    - offices.name contains "E2Eテスト事務所"

Usage:
    TEST_DATABASE_URL=... python scripts/cleanup_e2e_staffs_and_offices.py
    TEST_DATABASE_URL=... python scripts/cleanup_e2e_staffs_and_offices.py --execute
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from sqlalchemy import create_engine, text


SCRIPT_DIR = Path(__file__).resolve().parent
SQL_PATH = SCRIPT_DIR / "cleanup_e2e_staffs_and_offices.sql"

PREVIEW_SQL = """
WITH target_staffs AS (
    SELECT id, email
    FROM staffs
    WHERE email ILIKE '%e2e_staff%'
      AND email ILIKE '%@example.com%'
),
target_offices AS (
    SELECT DISTINCT o.id, o.name
    FROM offices o
    WHERE o.name LIKE '%E2Eテスト事務所%'
       OR o.created_by IN (SELECT id FROM target_staffs)
       OR o.last_modified_by IN (SELECT id FROM target_staffs)
       OR o.deleted_by IN (SELECT id FROM target_staffs)
       OR EXISTS (
            SELECT 1
            FROM office_staffs os
            WHERE os.office_id = o.id
              AND os.staff_id IN (SELECT id FROM target_staffs)
       )
),
target_welfare_recipients AS (
    SELECT DISTINCT owr.welfare_recipient_id AS id
    FROM office_welfare_recipients owr
    WHERE owr.office_id IN (SELECT id FROM target_offices)
      AND NOT EXISTS (
          SELECT 1
          FROM office_welfare_recipients other_owr
          WHERE other_owr.welfare_recipient_id = owr.welfare_recipient_id
            AND other_owr.office_id NOT IN (SELECT id FROM target_offices)
      )
),
target_support_plan_cycles AS (
    SELECT DISTINCT spc.id
    FROM support_plan_cycles spc
    WHERE spc.office_id IN (SELECT id FROM target_offices)
       OR spc.welfare_recipient_id IN (SELECT id FROM target_welfare_recipients)
)
SELECT 'staffs' AS table_name, count(*) AS target_count FROM target_staffs
UNION ALL
SELECT 'offices', count(*) FROM target_offices
UNION ALL
SELECT 'welfare_recipients', count(*) FROM target_welfare_recipients
UNION ALL
SELECT 'support_plan_cycles', count(*) FROM target_support_plan_cycles
ORDER BY table_name;
"""


def normalize_database_url(url: str) -> str:
    return url.replace("postgresql+psycopg://", "postgresql://", 1).replace(
        "postgresql+asyncpg://", "postgresql://", 1
    )


def get_database_url(env_name: str) -> str:
    database_url = os.getenv(env_name)
    if not database_url:
        print(f"ERROR: {env_name} is not set", file=sys.stderr)
        sys.exit(1)
    return normalize_database_url(database_url)


def verify_database_url(database_url: str, allow_production_keywords: bool) -> None:
    if allow_production_keywords:
        return

    production_keywords = ("prod", "production", "live")
    found = [keyword for keyword in production_keywords if keyword in database_url.lower()]
    if found:
        print("ERROR: database URL looks production-like.", file=sys.stderr)
        print(f"Matched keywords: {', '.join(found)}", file=sys.stderr)
        print("Pass --allow-production-keywords only if you are certain.", file=sys.stderr)
        sys.exit(1)


def confirm_execution(skip_confirmation: bool) -> None:
    if skip_confirmation:
        return

    print()
    print("This will DELETE E2E staffs/offices and related rows.")
    response = input("Type DELETE E2E DATA to continue: ")
    if response != "DELETE E2E DATA":
        print("Cancelled.")
        sys.exit(0)


def print_preview(engine) -> None:
    with engine.connect() as connection:
        rows = connection.execute(text(PREVIEW_SQL)).mappings().all()

    print("Dry-run target counts:")
    for row in rows:
        print(f"  {row['table_name']}: {row['target_count']}")


def execute_cleanup(engine) -> None:
    sql = SQL_PATH.read_text(encoding="utf-8")
    with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
        connection.exec_driver_sql(sql)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--database-url-env",
        default="TEST_DATABASE_URL",
        help="Environment variable containing the database URL. Defaults to TEST_DATABASE_URL.",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Run the destructive cleanup. Without this flag only target counts are shown.",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Skip the interactive confirmation prompt when used with --execute.",
    )
    parser.add_argument(
        "--allow-production-keywords",
        action="store_true",
        help="Allow database URLs containing production-like keywords.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    database_url = get_database_url(args.database_url_env)
    verify_database_url(database_url, args.allow_production_keywords)

    engine = create_engine(database_url, echo=False)
    try:
        print_preview(engine)
        if not args.execute:
            print()
            print("No rows were deleted. Re-run with --execute to apply cleanup.")
            return

        confirm_execution(args.yes)
        execute_cleanup(engine)
        print("Cleanup completed.")
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
