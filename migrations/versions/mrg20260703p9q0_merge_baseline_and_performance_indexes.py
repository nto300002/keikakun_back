"""advance baseline after performance index ancestry fix

Revision ID: mrg20260703p9q0
Revises: baseline_20260701
Create Date: 2026-07-03

"""
from typing import Sequence, Union


# revision identifiers, used by Alembic.
revision: str = "mrg20260703p9q0"
down_revision: Union[str, tuple[str, ...], None] = "baseline_20260701"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """No-op marker to keep production upgrades on the baseline path."""
    pass


def downgrade() -> None:
    """No-op merge marker downgrade."""
    pass
