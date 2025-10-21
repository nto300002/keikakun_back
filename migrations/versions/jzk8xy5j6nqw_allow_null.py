"""allow_null

Revision ID: jzk8xy5j6nqw
Revises: l0qvi774bcwo
Create Date: 2025-10-21 00:00:11

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'jzk8xy5j6nqw'
down_revision: Union[str, None] = 'l0qvi774bcwo'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # NULL を許容する
    op.alter_column('support_plan_cycles', 'plan_cycle_start_date',
                    existing_type=sa.Date(),
                    nullable=True)


def downgrade() -> None:
    # NOT NULL に戻す
    op.execute("""
        UPDATE support_plan_cycles
        SET plan_cycle_start_date = CURRENT_DATE
        WHERE plan_cycle_start_date IS NULL
    """)

    op.alter_column('support_plan_cycles', 'plan_cycle_start_date',
                    existing_type=sa.Date(),
                    nullable=False)
