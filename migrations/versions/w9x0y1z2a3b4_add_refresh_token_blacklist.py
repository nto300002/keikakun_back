"""add refresh token blacklist

Revision ID: w9x0y1z2a3b4
Revises: r3s4t5u6v7w8
Create Date: 2025-11-20 13:30:00.000000

Option 2: Refresh Token Blacklist
- パスワード変更時に既存のリフレッシュトークンを無効化
- OWASP A07:2021 Identification and Authentication Failures 対策
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'w9x0y1z2a3b4'
down_revision: Union[str, None] = 'r3s4t5u6v7w8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # refresh_token_blacklist テーブル作成
    op.create_table(
        'refresh_token_blacklist',
        sa.Column('id', postgresql.UUID(as_uuid=True), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('jti', sa.String(length=64), nullable=False),
        sa.Column('staff_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('blacklisted_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('reason', sa.String(length=100), nullable=False, server_default='password_changed'),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['staff_id'], ['staffs.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('jti')
    )

    # インデックス作成
    op.create_index('ix_refresh_token_blacklist_jti', 'refresh_token_blacklist', ['jti'], unique=False)
    op.create_index('ix_refresh_token_blacklist_staff_id', 'refresh_token_blacklist', ['staff_id'], unique=False)
    op.create_index('ix_refresh_token_blacklist_blacklisted_at', 'refresh_token_blacklist', ['blacklisted_at'], unique=False)
    op.create_index('ix_refresh_token_blacklist_expires_at', 'refresh_token_blacklist', ['expires_at'], unique=False)


def downgrade() -> None:
    # インデックス削除
    op.drop_index('ix_refresh_token_blacklist_expires_at', table_name='refresh_token_blacklist')
    op.drop_index('ix_refresh_token_blacklist_blacklisted_at', table_name='refresh_token_blacklist')
    op.drop_index('ix_refresh_token_blacklist_staff_id', table_name='refresh_token_blacklist')
    op.drop_index('ix_refresh_token_blacklist_jti', table_name='refresh_token_blacklist')

    # テーブル削除
    op.drop_table('refresh_token_blacklist')
