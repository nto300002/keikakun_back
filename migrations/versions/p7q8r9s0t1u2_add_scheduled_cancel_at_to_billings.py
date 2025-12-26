"""Add scheduled_cancel_at column to billings table

Revision ID: p7q8r9s0t1u2
Revises: acke3219j1m2
Create Date: 2025-12-22

スケジュールされたキャンセル（Scheduled Cancellation）対応:
- scheduled_cancel_at カラムを billings テーブルに追加
- Stripe の cancel_at タイムスタンプを保存
- キャンセル予定日をユーザーに表示可能にする
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'p7q8r9s0t1u2'
down_revision: Union[str, None] = 'acke3219j1m2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add scheduled_cancel_at column to billings table"""
    op.add_column(
        'billings',
        sa.Column(
            'scheduled_cancel_at',
            sa.DateTime(timezone=True),
            nullable=True,
            comment='Stripeのcancel_atに対応するスケジュールキャンセル日時'
        )
    )


def downgrade() -> None:
    """Remove scheduled_cancel_at column from billings table"""
    op.drop_column('billings', 'scheduled_cancel_at')
