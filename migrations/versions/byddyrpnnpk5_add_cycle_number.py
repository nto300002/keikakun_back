"""add_cycle_number

Revision ID: byddyrpnnpk5
Revises: su6cug3oavuk
Create Date: 2025-10-21 00:00:02

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'byddyrpnnpk5'
down_revision: Union[str, None] = 'su6cug3oavuk'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('support_plan_cycles', sa.Column('cycle_number', sa.Integer(), server_default='1', nullable=True))


def downgrade() -> None:
    op.drop_column('support_plan_cycles', 'cycle_number')
