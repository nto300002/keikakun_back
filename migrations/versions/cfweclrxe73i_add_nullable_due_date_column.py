"""add_nullable_due_date_column

Revision ID: cfweclrxe73i
Revises: jzk8xy5j6nqw
Create Date: 2025-10-21 00:00:12

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'cfweclrxe73i'
down_revision: Union[str, None] = 'jzk8xy5j6nqw'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add nullable due_date column (DATE)
    op.add_column('support_plan_statuses', sa.Column('due_date', sa.Date(), nullable=True))


def downgrade() -> None:
    op.drop_column('support_plan_statuses', 'due_date')
