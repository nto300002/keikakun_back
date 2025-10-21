"""add_calender_index_1

Revision ID: ds951cglvgxs
Revises: paa29np4un6a
Create Date: 2025-10-21 00:00:22

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ds951cglvgxs'
down_revision: Union[str, None] = 'paa29np4un6a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # notification_patterns
    op.create_index('idx_notification_patterns_event_type', 'notification_patterns', ['event_type'])
    op.execute("""
        CREATE INDEX idx_notification_patterns_active
        ON notification_patterns(is_active)
        WHERE is_active = TRUE
    """)

    # calendar_event_series
    op.create_index('idx_calendar_event_series_office_id', 'calendar_event_series', ['office_id'])
    op.create_index('idx_calendar_event_series_welfare_recipient_id', 'calendar_event_series', ['welfare_recipient_id'])
    op.create_index('idx_calendar_event_series_cycle_id', 'calendar_event_series', ['support_plan_cycle_id'])
    op.create_index('idx_calendar_event_series_status_id', 'calendar_event_series', ['support_plan_status_id'])
    op.create_index('idx_calendar_event_series_event_type', 'calendar_event_series', ['event_type'])
    op.create_index('idx_calendar_event_series_deadline_date', 'calendar_event_series', ['base_deadline_date'])
    op.create_index('idx_calendar_event_series_status', 'calendar_event_series', ['series_status'])

    # calendar_event_instances
    op.create_index('idx_calendar_event_instances_series_id', 'calendar_event_instances', ['event_series_id'])
    op.create_index('idx_calendar_event_instances_datetime', 'calendar_event_instances', ['event_datetime'])
    op.create_index('idx_calendar_event_instances_status', 'calendar_event_instances', ['instance_status'])
    op.create_index('idx_calendar_event_instances_sync_status', 'calendar_event_instances', ['sync_status'])
    op.create_index('idx_calendar_event_instances_google_event_id', 'calendar_event_instances', ['google_event_id'])
    op.execute("""
        CREATE INDEX idx_calendar_event_instances_reminder_pending
        ON calendar_event_instances(reminder_sent)
        WHERE reminder_sent = FALSE
    """)


def downgrade() -> None:
    op.execute('DROP INDEX IF EXISTS idx_calendar_event_instances_reminder_pending')
    op.drop_index('idx_calendar_event_instances_google_event_id', table_name='calendar_event_instances')
    op.drop_index('idx_calendar_event_instances_sync_status', table_name='calendar_event_instances')
    op.drop_index('idx_calendar_event_instances_status', table_name='calendar_event_instances')
    op.drop_index('idx_calendar_event_instances_datetime', table_name='calendar_event_instances')
    op.drop_index('idx_calendar_event_instances_series_id', table_name='calendar_event_instances')

    op.drop_index('idx_calendar_event_series_status', table_name='calendar_event_series')
    op.drop_index('idx_calendar_event_series_deadline_date', table_name='calendar_event_series')
    op.drop_index('idx_calendar_event_series_event_type', table_name='calendar_event_series')
    op.drop_index('idx_calendar_event_series_status_id', table_name='calendar_event_series')
    op.drop_index('idx_calendar_event_series_cycle_id', table_name='calendar_event_series')
    op.drop_index('idx_calendar_event_series_welfare_recipient_id', table_name='calendar_event_series')
    op.drop_index('idx_calendar_event_series_office_id', table_name='calendar_event_series')

    op.execute('DROP INDEX IF EXISTS idx_notification_patterns_active')
    op.drop_index('idx_notification_patterns_event_type', table_name='notification_patterns')
