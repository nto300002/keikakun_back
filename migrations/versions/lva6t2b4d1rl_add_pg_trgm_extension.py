"""add_pg_trgm_extension

Revision ID: lva6t2b4d1rl
Revises: xwhkgkwlo35p
Create Date: 2025-10-21 00:00:06

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'lva6t2b4d1rl'
down_revision: Union[str, None] = 'xwhkgkwlo35p'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute('CREATE EXTENSION IF NOT EXISTS pg_trgm')


def downgrade() -> None:
    op.execute('DROP EXTENSION IF EXISTS pg_trgm')
