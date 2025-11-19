"""add is_mfa_verified_by_user to staff

Revision ID: t5u6v7w8x9y0
Revises: s4t5u6v7w8x9
Create Date: 2025-11-19 02:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 't5u6v7w8x9y0'
down_revision: Union[str, None] = 's4t5u6v7w8x9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    is_mfa_verified_by_user カラムを staff テーブルに追加

    このカラムは、ユーザーが実際にTOTPアプリで検証を完了したかどうかを示します。
    - 管理者がMFAを有効化した場合: is_mfa_enabled = True, is_mfa_verified_by_user = False
    - ユーザー自身がMFA設定した場合: is_mfa_enabled = True, is_mfa_verified_by_user = True
    - ログイン時: is_mfa_enabled AND is_mfa_verified_by_user の場合のみ、通常のMFA検証を要求
    """
    # 1. カラム追加（デフォルト値を False に設定）
    op.add_column(
        'staff',
        sa.Column(
            'is_mfa_verified_by_user',
            sa.Boolean(),
            nullable=False,
            server_default='false'
        )
    )

    # 2. 既存データの初期化
    # is_mfa_enabled = TRUE の既存ユーザーは、すでに自分で設定済みとみなす
    # → is_mfa_verified_by_user = TRUE に設定
    op.execute("""
        UPDATE staff
        SET is_mfa_verified_by_user = TRUE
        WHERE is_mfa_enabled = TRUE
    """)


def downgrade() -> None:
    """
    is_mfa_verified_by_user カラムを削除
    """
    op.drop_column('staff', 'is_mfa_verified_by_user')
