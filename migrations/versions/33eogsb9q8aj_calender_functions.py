"""calendar_functions

Revision ID: 33eogsb9q8aj
Revises: ds951cglvgxs
Create Date: 2025-10-21 00:00:23

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '33eogsb9q8aj'
down_revision: Union[str, None] = 'ds951cglvgxs'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # notification_patterns
    op.execute("""
        CREATE OR REPLACE FUNCTION update_notification_patterns_updated_at()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.updated_at = NOW();
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
    """)

    op.execute("""
        CREATE TRIGGER trigger_update_notification_patterns_updated_at
        BEFORE UPDATE ON notification_patterns
        FOR EACH ROW
        EXECUTE FUNCTION update_notification_patterns_updated_at()
    """)

    # calendar_event_series
    op.execute("""
        CREATE OR REPLACE FUNCTION update_calendar_event_series_updated_at()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.updated_at = NOW();
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
    """)

    op.execute("""
        CREATE TRIGGER trigger_update_calendar_event_series_updated_at
        BEFORE UPDATE ON calendar_event_series
        FOR EACH ROW
        EXECUTE FUNCTION update_calendar_event_series_updated_at()
    """)

    # calendar_event_instances
    op.execute("""
        CREATE OR REPLACE FUNCTION update_calendar_event_instances_updated_at()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.updated_at = NOW();
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
    """)

    op.execute("""
        CREATE TRIGGER trigger_update_calendar_event_instances_updated_at
        BEFORE UPDATE ON calendar_event_instances
        FOR EACH ROW
        EXECUTE FUNCTION update_calendar_event_instances_updated_at()
    """)


def downgrade() -> None:
    op.execute('DROP TRIGGER IF EXISTS trigger_update_calendar_event_instances_updated_at ON calendar_event_instances')
    op.execute('DROP FUNCTION IF EXISTS update_calendar_event_instances_updated_at()')

    op.execute('DROP TRIGGER IF EXISTS trigger_update_calendar_event_series_updated_at ON calendar_event_series')
    op.execute('DROP FUNCTION IF EXISTS update_calendar_event_series_updated_at()')

    op.execute('DROP TRIGGER IF EXISTS trigger_update_notification_patterns_updated_at ON notification_patterns')
    op.execute('DROP FUNCTION IF EXISTS update_notification_patterns_updated_at()')
