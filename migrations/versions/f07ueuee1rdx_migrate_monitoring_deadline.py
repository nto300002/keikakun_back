"""migrate_monitoring_deadline_to_support_plan_cycles

Revision ID: f07ueuee1rdx
Revises: gcphzt136gvc
Create Date: 2025-10-21 00:00:14

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f07ueuee1rdx'
down_revision: Union[str, None] = 'gcphzt136gvc'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # SupportPlanCycleテーブルにmonitoring_deadlineカラムを追加
    op.add_column('support_plan_cycles',
                  sa.Column('monitoring_deadline', sa.Integer(), server_default='7', nullable=True))

    # 各SupportPlanCycleに最新のmonitoring_deadline値を移行
    op.execute("""
        UPDATE support_plan_cycles
        SET monitoring_deadline = (
            SELECT COALESCE(
                (SELECT sps.monitoring_deadline
                 FROM support_plan_statuses sps
                 WHERE sps.plan_cycle_id = support_plan_cycles.id
                   AND sps.monitoring_deadline IS NOT NULL
                 ORDER BY sps.updated_at DESC, sps.id DESC
                 LIMIT 1),
                7
            )
        )
    """)


def downgrade() -> None:
    op.drop_column('support_plan_cycles', 'monitoring_deadline')
