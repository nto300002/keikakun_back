"""Rename monitoring_deadline to next_plan_start_date in support_plan_cycles table

Revision ID: w5x6y7z8a9b0
Revises: v4w5x6y7z8a9
Create Date: 2026-01-11

Task: 次回開始期限カラムリネーム
- monitoring_deadline (Integer, nullable=True) → next_plan_start_date (Integer, nullable=True)
- テーブル: support_plan_cycles
- 既存データは保持される
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'w5x6y7z8a9b0'
down_revision: Union[str, None] = 'v4w5x6y7z8a9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Rename monitoring_deadline to next_plan_start_date in support_plan_cycles table"""
    # カラムをリネーム
    op.alter_column(
        'support_plan_cycles',
        'monitoring_deadline',
        new_column_name='next_plan_start_date',
        existing_type=sa.Integer(),
        existing_nullable=True,
        comment='次回計画開始期限（日数）'
    )


def downgrade() -> None:
    """Rename next_plan_start_date back to monitoring_deadline in support_plan_cycles table"""
    # カラムをリネーム
    op.alter_column(
        'support_plan_cycles',
        'next_plan_start_date',
        new_column_name='monitoring_deadline',
        existing_type=sa.Integer(),
        existing_nullable=True,
        comment='モニタリング期限（日数）'
    )
