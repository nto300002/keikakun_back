"""null_constraint_fix

Revision ID: l0qvi774bcwo
Revises: yz5j5u49v764
Create Date: 2025-10-21 00:00:10

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'l0qvi774bcwo'
down_revision: Union[str, None] = 'yz5j5u49v764'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 事前に NULL の行があればデータを今日の日付に置き換える
    op.execute("""
        UPDATE support_plan_cycles
        SET plan_cycle_start_date = CURRENT_DATE
        WHERE plan_cycle_start_date IS NULL
    """)

    # NOT NULL に戻す
    op.alter_column('support_plan_cycles', 'plan_cycle_start_date',
                    existing_type=sa.Date(),
                    nullable=False)


def downgrade() -> None:
    # NULL を許容する
    op.alter_column('support_plan_cycles', 'plan_cycle_start_date',
                    existing_type=sa.Date(),
                    nullable=True)
