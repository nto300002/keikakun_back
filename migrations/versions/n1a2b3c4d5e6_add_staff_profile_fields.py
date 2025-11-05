"""add_staff_profile_fields

Revision ID: n1a2b3c4d5e6
Revises: m9n8x7y6z5a4
Create Date: 2025-10-31 00:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


# revision identifiers, used by Alembic.
revision: str = 'n1a2b3c4d5e6'
down_revision: Union[str, None] = 'm9n8x7y6z5a4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # nameカラムをNULLABLEに変更（後方互換性のため）
    op.alter_column('staffs', 'name', nullable=True)

    # 新しい名前関連カラムを追加
    op.add_column('staffs', sa.Column('last_name', sa.String(50), nullable=True))
    op.add_column('staffs', sa.Column('first_name', sa.String(50), nullable=True))
    op.add_column('staffs', sa.Column('last_name_furigana', sa.String(100), nullable=True))
    op.add_column('staffs', sa.Column('first_name_furigana', sa.String(100), nullable=True))
    op.add_column('staffs', sa.Column('full_name', sa.String(255), nullable=True))

    # パスワード変更関連カラムを追加
    op.add_column('staffs', sa.Column('password_changed_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('staffs', sa.Column('failed_password_attempts', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('staffs', sa.Column('is_locked', sa.Boolean(), nullable=False, server_default='false'))
    op.add_column('staffs', sa.Column('locked_at', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    # パスワード変更関連カラムを削除
    op.drop_column('staffs', 'locked_at')
    op.drop_column('staffs', 'is_locked')
    op.drop_column('staffs', 'failed_password_attempts')
    op.drop_column('staffs', 'password_changed_at')

    # 名前関連カラムを削除
    op.drop_column('staffs', 'full_name')
    op.drop_column('staffs', 'first_name_furigana')
    op.drop_column('staffs', 'last_name_furigana')
    op.drop_column('staffs', 'first_name')
    op.drop_column('staffs', 'last_name')

    # nameカラムをNOT NULLに戻す
    op.alter_column('staffs', 'name', nullable=False)
