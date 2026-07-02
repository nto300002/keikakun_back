"""add_performance_optimization_indexes

Revision ID: p9q0r1s2t3u4
Revises: n3o4p5q6r7s8
Create Date: 2026-06-30 00:00:00

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'p9q0r1s2t3u4'
down_revision: Union[str, None] = 'n3o4p5q6r7s8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


INDEX_UPGRADE_SQL = [
    """
    CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_notices_recipient_read_created
    ON notices (recipient_staff_id, is_read, created_at DESC)
    """,
    """
    CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_notices_recipient_created
    ON notices (recipient_staff_id, created_at DESC)
    """,
    """
    CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_notices_office_created
    ON notices (office_id, created_at DESC)
    """,
    """
    CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_support_plan_cycles_office_latest_renewal
    ON support_plan_cycles (office_id, is_latest_cycle, next_renewal_deadline)
    """,
    """
    CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_support_plan_cycles_recipient_office_latest
    ON support_plan_cycles (welfare_recipient_id, office_id, is_latest_cycle)
    """,
    """
    CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_plan_deliverables_cycle_type
    ON plan_deliverables (plan_cycle_id, deliverable_type)
    """,
    """
    CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_support_plan_statuses_office_latest_step
    ON support_plan_statuses (office_id, is_latest_status, step_type)
    """,
]


INDEX_DOWNGRADE_SQL = [
    "DROP INDEX CONCURRENTLY IF EXISTS idx_support_plan_statuses_office_latest_step",
    "DROP INDEX CONCURRENTLY IF EXISTS idx_plan_deliverables_cycle_type",
    "DROP INDEX CONCURRENTLY IF EXISTS idx_support_plan_cycles_recipient_office_latest",
    "DROP INDEX CONCURRENTLY IF EXISTS idx_support_plan_cycles_office_latest_renewal",
    "DROP INDEX CONCURRENTLY IF EXISTS idx_notices_office_created",
    "DROP INDEX CONCURRENTLY IF EXISTS idx_notices_recipient_created",
    "DROP INDEX CONCURRENTLY IF EXISTS idx_notices_recipient_read_created",
]


def upgrade() -> None:
    # CREATE INDEX CONCURRENTLY cannot run inside Alembic's default transaction.
    # These indexes mirror:
    # md_files_design_note/task/todo/refactor/performance/db_optimization_indexes.sql
    with op.get_context().autocommit_block():
        for statement in INDEX_UPGRADE_SQL:
            op.execute(statement)

        op.execute("ANALYZE notices")
        op.execute("ANALYZE support_plan_cycles")
        op.execute("ANALYZE support_plan_statuses")
        op.execute("ANALYZE plan_deliverables")


def downgrade() -> None:
    with op.get_context().autocommit_block():
        for statement in INDEX_DOWNGRADE_SQL:
            op.execute(statement)
