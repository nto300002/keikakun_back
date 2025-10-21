"""add_calendar_events_tables

Revision ID: si3z83ycga3r
Revises: j6ewiuu6hhlu
Create Date: 2025-10-21 00:00:16

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'si3z83ycga3r'
down_revision: Union[str, None] = 'j6ewiuu6hhlu'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 新しいENUM型の作成
    op.execute("""
        CREATE TYPE calendar_event_type AS ENUM (
            'renewal_deadline',
            'monitoring_deadline',
            'custom'
        )
    """)

    op.execute("""
        CREATE TYPE calendar_sync_status AS ENUM (
            'pending',
            'synced',
            'failed',
            'cancelled'
        )
    """)

    # calendar_eventsテーブル作成
    op.create_table('calendar_events',
        sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('office_id', sa.UUID(), nullable=False),
        sa.Column('welfare_recipient_id', sa.UUID(), nullable=False),
        sa.Column('support_plan_cycle_id', sa.Integer(), nullable=True),
        sa.Column('support_plan_status_id', sa.Integer(), nullable=True),
        sa.Column('event_type', sa.Enum('renewal_deadline', 'monitoring_deadline', 'custom', name='calendar_event_type'), nullable=False),
        sa.Column('google_calendar_id', sa.String(length=255), nullable=False),
        sa.Column('google_event_id', sa.String(length=255), nullable=True),
        sa.Column('google_event_url', sa.Text(), nullable=True),
        sa.Column('event_title', sa.String(length=500), nullable=False),
        sa.Column('event_description', sa.Text(), nullable=True),
        sa.Column('event_start_datetime', sa.DateTime(timezone=True), nullable=False),
        sa.Column('event_end_datetime', sa.DateTime(timezone=True), nullable=False),
        sa.Column('created_by_system', sa.Boolean(), server_default='true', nullable=True),
        sa.Column('sync_status', sa.Enum('pending', 'synced', 'failed', 'cancelled', name='calendar_sync_status'), server_default='pending', nullable=True),
        sa.Column('last_sync_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_error_message', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('google_event_id')
    )

    # インデックス作成
    op.create_index('idx_calendar_events_office_id', 'calendar_events', ['office_id'])
    op.create_index('idx_calendar_events_welfare_recipient_id', 'calendar_events', ['welfare_recipient_id'])
    op.create_index('idx_calendar_events_cycle_id', 'calendar_events', ['support_plan_cycle_id'])
    op.create_index('idx_calendar_events_status_id', 'calendar_events', ['support_plan_status_id'])
    op.create_index('idx_calendar_events_event_type', 'calendar_events', ['event_type'])
    op.create_index('idx_calendar_events_sync_status', 'calendar_events', ['sync_status'])
    op.create_index('idx_calendar_events_google_event_id', 'calendar_events', ['google_event_id'])
    op.create_index('idx_calendar_events_event_datetime', 'calendar_events', ['event_start_datetime'])

    # 複合インデックス（重複防止用）
    op.execute("""
        CREATE UNIQUE INDEX idx_calendar_events_cycle_type_unique
        ON calendar_events(support_plan_cycle_id, event_type)
        WHERE support_plan_cycle_id IS NOT NULL AND (sync_status = 'pending' OR sync_status = 'synced')
    """)

    op.execute("""
        CREATE UNIQUE INDEX idx_calendar_events_status_type_unique
        ON calendar_events(support_plan_status_id, event_type)
        WHERE support_plan_status_id IS NOT NULL AND (sync_status = 'pending' OR sync_status = 'synced')
    """)

    # updated_at自動更新トリガー
    op.execute("""
        CREATE OR REPLACE FUNCTION update_calendar_events_updated_at()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.updated_at = NOW();
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
    """)

    op.execute("""
        CREATE TRIGGER trigger_update_calendar_events_updated_at
        BEFORE UPDATE ON calendar_events
        FOR EACH ROW
        EXECUTE FUNCTION update_calendar_events_updated_at()
    """)


def downgrade() -> None:
    op.execute('DROP TRIGGER IF EXISTS trigger_update_calendar_events_updated_at ON calendar_events')
    op.execute('DROP FUNCTION IF EXISTS update_calendar_events_updated_at()')

    op.execute('DROP INDEX IF EXISTS idx_calendar_events_status_type_unique')
    op.execute('DROP INDEX IF EXISTS idx_calendar_events_cycle_type_unique')

    op.drop_index('idx_calendar_events_event_datetime', table_name='calendar_events')
    op.drop_index('idx_calendar_events_google_event_id', table_name='calendar_events')
    op.drop_index('idx_calendar_events_sync_status', table_name='calendar_events')
    op.drop_index('idx_calendar_events_event_type', table_name='calendar_events')
    op.drop_index('idx_calendar_events_status_id', table_name='calendar_events')
    op.drop_index('idx_calendar_events_cycle_id', table_name='calendar_events')
    op.drop_index('idx_calendar_events_welfare_recipient_id', table_name='calendar_events')
    op.drop_index('idx_calendar_events_office_id', table_name='calendar_events')

    op.drop_table('calendar_events')

    op.execute('DROP TYPE IF EXISTS calendar_sync_status')
    op.execute('DROP TYPE IF EXISTS calendar_event_type')
