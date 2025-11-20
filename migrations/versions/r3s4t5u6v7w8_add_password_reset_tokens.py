"""add password reset tokens table

Revision ID: r3s4t5u6v7w8
Revises: a1b2c3d4e5f6
Create Date: 2025-01-20 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'r3s4t5u6v7w8'
down_revision = 'a1b2c3d4e5f6'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """パスワードリセットトークンテーブルを作成"""

    # password_reset_tokens テーブルを作成
    op.create_table(
        'password_reset_tokens',
        sa.Column('id', postgresql.UUID(as_uuid=True), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('staff_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('token_hash', sa.String(length=64), nullable=False),  # SHA-256ハッシュ
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('used', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('used_at', sa.DateTime(timezone=True), nullable=True),
        # セキュリティレビュー対応: 楽観的ロック用バージョン番号
        sa.Column('version', sa.Integer(), nullable=False, server_default=sa.text('0')),
        # セキュリティレビュー対応: リクエスト元情報（監査ログ用）
        sa.Column('request_ip', sa.String(length=45), nullable=True),  # IPv6対応
        sa.Column('request_user_agent', sa.String(length=500), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['staff_id'], ['staffs.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )

    # password_reset_audit_logs テーブルを作成
    op.create_table(
        'password_reset_audit_logs',
        sa.Column('id', postgresql.UUID(as_uuid=True), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('staff_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('action', sa.String(length=50), nullable=False),
        sa.Column('email', sa.String(length=255), nullable=True),
        sa.Column('ip_address', sa.String(length=45), nullable=True),
        sa.Column('user_agent', sa.Text(), nullable=True),
        sa.Column('success', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['staff_id'], ['staffs.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )

    # インデックスを作成（password_reset_tokens）
    op.create_index('idx_password_reset_token_hash', 'password_reset_tokens', ['token_hash'], unique=True)
    op.create_index('idx_password_reset_composite', 'password_reset_tokens', ['staff_id', 'used', 'expires_at'], unique=False)

    # インデックスを作成（password_reset_audit_logs）
    op.create_index('idx_audit_staff_id', 'password_reset_audit_logs', ['staff_id'], unique=False)
    op.create_index('idx_audit_created_at', 'password_reset_audit_logs', ['created_at'], unique=False)
    op.create_index('idx_audit_action', 'password_reset_audit_logs', ['action'], unique=False)


def downgrade() -> None:
    """ロールバック"""

    # インデックスを削除（password_reset_audit_logs）
    op.drop_index('idx_audit_action', table_name='password_reset_audit_logs')
    op.drop_index('idx_audit_created_at', table_name='password_reset_audit_logs')
    op.drop_index('idx_audit_staff_id', table_name='password_reset_audit_logs')

    # インデックスを削除（password_reset_tokens）
    op.drop_index('idx_password_reset_composite', table_name='password_reset_tokens')
    op.drop_index('idx_password_reset_token_hash', table_name='password_reset_tokens')

    # テーブルを削除
    op.drop_table('password_reset_audit_logs')
    op.drop_table('password_reset_tokens')
