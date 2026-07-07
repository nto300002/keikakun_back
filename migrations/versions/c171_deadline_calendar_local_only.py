"""support local-only deadline calendar events

Revision ID: c171deadlinecal
Revises: mrg20260703p9q0
Create Date: 2026-07-07

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "c171deadlinecal"
down_revision: Union[str, None] = "mrg20260703p9q0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE calendar_sync_status ADD VALUE IF NOT EXISTS 'local_only'")
        op.execute("ALTER TYPE calendar_event_type ADD VALUE IF NOT EXISTS 'assessment_incomplete'")

    op.alter_column(
        "calendar_events",
        "google_calendar_id",
        existing_type=sa.String(length=255),
        nullable=True,
    )

    op.execute("DROP INDEX IF EXISTS idx_calendar_events_cycle_type_unique")
    op.execute("DROP INDEX IF EXISTS idx_calendar_events_status_type_unique")
    op.execute(
        """
        CREATE UNIQUE INDEX idx_calendar_events_cycle_type_unique
        ON calendar_events(support_plan_cycle_id, event_type)
        WHERE support_plan_cycle_id IS NOT NULL
          AND sync_status IN ('pending', 'synced', 'local_only')
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX idx_calendar_events_status_type_unique
        ON calendar_events(support_plan_status_id, event_type)
        WHERE support_plan_status_id IS NOT NULL
          AND sync_status IN ('pending', 'synced', 'local_only')
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_calendar_events_status_type_unique")
    op.execute("DROP INDEX IF EXISTS idx_calendar_events_cycle_type_unique")
    op.execute(
        """
        CREATE UNIQUE INDEX idx_calendar_events_cycle_type_unique
        ON calendar_events(support_plan_cycle_id, event_type)
        WHERE support_plan_cycle_id IS NOT NULL
          AND (sync_status = 'pending' OR sync_status = 'synced')
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX idx_calendar_events_status_type_unique
        ON calendar_events(support_plan_status_id, event_type)
        WHERE support_plan_status_id IS NOT NULL
          AND (sync_status = 'pending' OR sync_status = 'synced')
        """
    )
    op.alter_column(
        "calendar_events",
        "google_calendar_id",
        existing_type=sa.String(length=255),
        nullable=False,
    )
