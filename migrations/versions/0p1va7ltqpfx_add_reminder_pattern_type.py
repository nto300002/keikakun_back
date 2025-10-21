"""add_reminder_pattern_type

Revision ID: 0p1va7ltqpfx
Revises: k6bsnmc8hdki
Create Date: 2025-10-21 00:00:18

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0p1va7ltqpfx'
down_revision: Union[str, None] = 'k6bsnmc8hdki'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 新しいENUM型の作成
    op.execute("""
        CREATE TYPE reminder_pattern_type AS ENUM (
            'single',
            'multiple_fixed',
            'recurring_rule'
        )
    """)

    op.execute("""
        CREATE TYPE event_instance_status AS ENUM (
            'pending',
            'created',
            'modified',
            'cancelled',
            'completed'
        )
    """)


def downgrade() -> None:
    op.execute('DROP TYPE IF EXISTS event_instance_status')
    op.execute('DROP TYPE IF EXISTS reminder_pattern_type')
