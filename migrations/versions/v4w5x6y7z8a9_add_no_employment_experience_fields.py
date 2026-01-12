"""Add no_employment_experience fields to employment_related table

Revision ID: v4w5x6y7z8a9
Revises: u3v4w5x6y7z8
Create Date: 2026-01-08

Task 1: 就労経験なしチェックボックス追加
- no_employment_experience (Boolean, nullable=False, default=False) - 親チェックボックス
- attended_job_selection_office (Boolean, nullable=False, default=False) - 子
- received_employment_assessment (Boolean, nullable=False, default=False) - 子
- employment_other_experience (Boolean, nullable=False, default=False) - 子（その他）
- employment_other_text (Text, nullable=True) - その他の詳細
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'v4w5x6y7z8a9'
down_revision: Union[str, None] = 'u3v4w5x6y7z8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add no_employment_experience fields to employment_related table"""
    op.add_column(
        'employment_related',
        sa.Column(
            'no_employment_experience',
            sa.Boolean(),
            nullable=False,
            server_default='false',
            comment='就労経験なし（親チェックボックス）'
        )
    )
    op.add_column(
        'employment_related',
        sa.Column(
            'attended_job_selection_office',
            sa.Boolean(),
            nullable=False,
            server_default='false',
            comment='就職選択事務所を利用したことがある'
        )
    )
    op.add_column(
        'employment_related',
        sa.Column(
            'received_employment_assessment',
            sa.Boolean(),
            nullable=False,
            server_default='false',
            comment='就労アセスメントを受けたことがある'
        )
    )
    op.add_column(
        'employment_related',
        sa.Column(
            'employment_other_experience',
            sa.Boolean(),
            nullable=False,
            server_default='false',
            comment='その他の就労関連経験がある'
        )
    )
    op.add_column(
        'employment_related',
        sa.Column(
            'employment_other_text',
            sa.Text(),
            nullable=True,
            comment='その他の就労関連経験の詳細'
        )
    )


def downgrade() -> None:
    """Remove no_employment_experience fields from employment_related table"""
    op.drop_column('employment_related', 'employment_other_text')
    op.drop_column('employment_related', 'employment_other_experience')
    op.drop_column('employment_related', 'received_employment_assessment')
    op.drop_column('employment_related', 'attended_job_selection_office')
    op.drop_column('employment_related', 'no_employment_experience')
