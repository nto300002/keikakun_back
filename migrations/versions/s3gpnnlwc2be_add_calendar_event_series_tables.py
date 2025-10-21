"""add_calendar_event_series_tables

Revision ID: s3gpnnlwc2be
Revises: tyz04p9mrz7k
Create Date: 2025-10-21 00:00:20

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ARRAY


# revision identifiers, used by Alembic.
revision: str = 's3gpnnlwc2be'
down_revision: Union[str, None] = 'tyz04p9mrz7k'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # カレンダーイベントシリーズ管理テーブル
    op.create_table('calendar_event_series',
        sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('office_id', sa.UUID(), nullable=False),
        sa.Column('welfare_recipient_id', sa.UUID(), nullable=False),
        sa.Column('support_plan_cycle_id', sa.Integer(), nullable=True),
        sa.Column('support_plan_status_id', sa.Integer(), nullable=True),
        sa.Column('event_type', sa.Enum('renewal_deadline', 'monitoring_deadline', 'custom', name='calendar_event_type'), nullable=False),
        sa.Column('series_title', sa.String(length=500), nullable=False),
        sa.Column('base_deadline_date', sa.Date(), nullable=False),
        sa.Column('pattern_type', sa.Enum('single', 'multiple_fixed', 'recurring_rule', name='reminder_pattern_type'), nullable=False, server_default='multiple_fixed'),
        sa.Column('notification_pattern_id', sa.UUID(), nullable=True),
        sa.Column('reminder_days_before', ARRAY(sa.Integer()), nullable=False),
        sa.Column('google_rrule', sa.Text(), nullable=True),
        sa.Column('google_calendar_id', sa.String(length=255), nullable=False),
        sa.Column('google_master_event_id', sa.String(length=255), nullable=True),
        sa.Column('series_status', sa.Enum('pending', 'synced', 'failed', 'cancelled', name='calendar_sync_status'), server_default='pending', nullable=True),
        sa.Column('total_instances', sa.Integer(), server_default='0', nullable=True),
        sa.Column('completed_instances', sa.Integer(), server_default='0', nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['notification_pattern_id'], ['notification_patterns.id'], ),
        sa.PrimaryKeyConstraint('id')
    )

    # Check constraint
    op.execute("""
        ALTER TABLE calendar_event_series
        ADD CONSTRAINT chk_calendar_event_series_ref_exclusive
        CHECK (
            (support_plan_cycle_id IS NOT NULL AND support_plan_status_id IS NULL) OR
            (support_plan_cycle_id IS NULL AND support_plan_status_id IS NOT NULL)
        )
    """)


def downgrade() -> None:
    op.drop_table('calendar_event_series')
