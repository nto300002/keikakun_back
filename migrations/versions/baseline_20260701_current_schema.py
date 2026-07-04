"""baseline current schema for Alembic restart

Revision ID: baseline_20260701
Revises: a1b2c3d4e5f6, a1b2c3d4e5f7, a1b2c3d4e5f8, b0c1d2e3f4g5, p9q0r1s2t3u4, q8r9s0t1u2v3
Create Date: 2026-07-01

This revision is a no-op baseline marker.

The existing NeonDB branches were mostly managed with manual SQL before this
point, and their alembic_version state is not a reliable representation of the
actual schema. Do not run historical migrations against existing databases to
reach this revision. Existing databases should be schema-verified first, then
stamped to this revision only after approval.
"""
from typing import Sequence, Union


# revision identifiers, used by Alembic.
revision: str = "baseline_20260701"
down_revision: Union[str, tuple[str, ...], None] = (
    "a1b2c3d4e5f6",
    "a1b2c3d4e5f7",
    "a1b2c3d4e5f8",
    "b0c1d2e3f4g5",
    "p9q0r1s2t3u4",
    "q8r9s0t1u2v3",
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """No-op: baseline marker for existing verified schemas."""
    pass


def downgrade() -> None:
    """No-op: do not use this revision to roll back schema objects."""
    pass
