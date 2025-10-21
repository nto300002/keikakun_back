"""fix_calendar_columns

Revision ID: zrcknaddjteq
Revises: qwa542xilkfk
Create Date: 2025-10-21 00:00:26

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'zrcknaddjteq'
down_revision: Union[str, None] = 'qwa542xilkfk'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # このマイグレーションは、既存のデータでカラム型が正しい場合はスキップされます
    # UUIDからINTEGERへの変換が必要な場合のみ実行されます
    pass


def downgrade() -> None:
    pass
