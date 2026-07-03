"""merge baseline and performance index migration heads

Revision ID: mrg20260703p9q0
Revises: baseline_20260701, p9q0r1s2t3u4
Create Date: 2026-07-03

"""
from typing import Sequence, Union


# revision identifiers, used by Alembic.
revision: str = "mrg20260703p9q0"
down_revision: Union[str, tuple[str, ...], None] = (
    "baseline_20260701",
    "p9q0r1s2t3u4",
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """No-op merge marker to restore a single Alembic head."""
    pass


def downgrade() -> None:
    """No-op merge marker downgrade."""
    pass
