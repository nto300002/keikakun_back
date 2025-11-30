"""add passphrase to staff

Revision ID: e3f4g5h6i7j8
Revises: d2e3f4g5h6i7
Create Date: 2025-11-27 10:00:00.000000

app_admin用の合言葉（セカンドパスワード）機能:
- staffsテーブルに hashed_passphrase カラム追加
- staffsテーブルに passphrase_changed_at カラム追加
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e3f4g5h6i7j8'
down_revision: Union[str, None] = 'd2e3f4g5h6i7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ===========================================
    # staffsテーブルに合言葉関連カラムを追加
    # ===========================================

    # hashed_passphrase: app_admin専用の合言葉（bcryptハッシュ化）
    op.add_column(
        'staffs',
        sa.Column(
            'hashed_passphrase',
            sa.String(length=255),
            nullable=True,
            comment='app_admin専用の合言葉（bcryptハッシュ化）'
        )
    )

    # passphrase_changed_at: 合言葉の最終変更日時
    op.add_column(
        'staffs',
        sa.Column(
            'passphrase_changed_at',
            sa.DateTime(timezone=True),
            nullable=True,
            comment='合言葉の最終変更日時'
        )
    )


def downgrade() -> None:
    # ===========================================
    # staffsテーブルから合言葉関連カラムを削除
    # ===========================================
    op.drop_column('staffs', 'passphrase_changed_at')
    op.drop_column('staffs', 'hashed_passphrase')
