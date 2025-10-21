"""add_pgcrypto_extension

Revision ID: xwhkgkwlo35p
Revises: 8btga4fq6fym
Create Date: 2025-10-21 00:00:05

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'xwhkgkwlo35p'
down_revision: Union[str, None] = '8btga4fq6fym'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute('CREATE EXTENSION IF NOT EXISTS "pgcrypto"')


def downgrade() -> None:
    op.execute('DROP EXTENSION IF EXISTS "pgcrypto"')
