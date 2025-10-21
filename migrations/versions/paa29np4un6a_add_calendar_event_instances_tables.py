"""add_calendar_event_instances_tables

Revision ID: paa29np4un6a
Revises: s3gpnnlwc2be
Create Date: 2025-10-21 00:00:21

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'paa29np4un6a'
down_revision: Union[str, None] = 's3gpnnlwc2be'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # カレンダーイベントインスタンス管理テーブル
    op.create_table('calendar_event_instances',
        sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('event_series_id', sa.UUID(), nullable=False),
        sa.Column('instance_title', sa.String(length=500), nullable=False),
        sa.Column('instance_description', sa.Text(), nullable=True),
        sa.Column('event_datetime', sa.DateTime(timezone=True), nullable=False),
        sa.Column('days_before_deadline', sa.Integer(), nullable=False),
        sa.Column('google_event_id', sa.String(length=255), nullable=True),
        sa.Column('google_event_url', sa.Text(), nullable=True),
        sa.Column('instance_status', sa.Enum('pending', 'created', 'modified', 'cancelled', 'completed', name='event_instance_status'), server_default='pending', nullable=True),
        sa.Column('sync_status', sa.Enum('pending', 'synced', 'failed', 'cancelled', name='calendar_sync_status'), server_default='pending', nullable=True),
        sa.Column('last_sync_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_error_message', sa.Text(), nullable=True),
        sa.Column('reminder_sent', sa.Boolean(), server_default='false', nullable=True),
        sa.Column('reminder_sent_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['event_series_id'], ['calendar_event_series.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('google_event_id')
    )


def downgrade() -> None:
    op.drop_table('calendar_event_instances')
