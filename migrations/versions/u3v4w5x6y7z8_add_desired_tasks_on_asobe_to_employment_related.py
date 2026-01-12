"""Add desired_tasks_on_asobe column to employment_related table

Revision ID: u3v4w5x6y7z8
Revises: p7q8r9s0t1u2
Create Date: 2026-01-08

Task 2: asoBeで希望する作業フィールドの追加
- desired_tasks_on_asobe カラムを employment_related テーブルに追加
- TEXT型、NULL許容
- asoBeでの希望作業内容を記録（最大1000文字、Pydanticでバリデーション）
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'u3v4w5x6y7z8'
down_revision: Union[str, None] = 'p7q8r9s0t1u2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add desired_tasks_on_asobe column to employment_related table"""
    op.add_column(
        'employment_related',
        sa.Column(
            'desired_tasks_on_asobe',
            sa.Text(),
            nullable=True,
            comment='asoBeで希望する作業内容（最大1000文字）'
        )
    )


def downgrade() -> None:
    """Remove desired_tasks_on_asobe column from employment_related table"""
    op.drop_column('employment_related', 'desired_tasks_on_asobe')
