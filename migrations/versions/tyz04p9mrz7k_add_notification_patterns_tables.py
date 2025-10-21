"""add_notification_patterns_tables

Revision ID: tyz04p9mrz7k
Revises: 0p1va7ltqpfx
Create Date: 2025-10-21 00:00:19

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ARRAY


# revision identifiers, used by Alembic.
revision: str = 'tyz04p9mrz7k'
down_revision: Union[str, None] = '0p1va7ltqpfx'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 通知パターンテンプレート管理テーブル
    op.create_table('notification_patterns',
        sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('pattern_name', sa.String(length=100), nullable=False),
        sa.Column('pattern_description', sa.Text(), nullable=True),
        sa.Column('event_type', sa.Enum('renewal_deadline', 'monitoring_deadline', 'custom', name='calendar_event_type'), nullable=False),
        sa.Column('reminder_days_before', ARRAY(sa.Integer()), nullable=False),
        sa.Column('title_template', sa.String(length=500), nullable=False),
        sa.Column('description_template', sa.Text(), nullable=True),
        sa.Column('is_system_default', sa.Boolean(), server_default='false', nullable=True),
        sa.Column('is_active', sa.Boolean(), server_default='true', nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('pattern_name')
    )


def downgrade() -> None:
    op.drop_table('notification_patterns')
