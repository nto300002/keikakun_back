"""create_mfa

Revision ID: 001_create_mfa
Revises: 7fa9fdd58c84
Create Date: 2025-10-21 00:00:01

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '001_create_mfa'
down_revision: Union[str, None] = '7fa9fdd58c84'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # staffs テーブルにMFA関連のカラムを追加
    op.add_column('staffs', sa.Column('is_mfa_enabled', sa.Boolean(), nullable=False, server_default='false'))
    op.add_column('staffs', sa.Column('mfa_secret', sa.String(length=255), nullable=True))
    op.add_column('staffs', sa.Column('mfa_backup_codes_used', sa.Integer(), nullable=False, server_default='0'))

    # mfa_audit_logs テーブルを作成
    op.create_table('mfa_audit_logs',
        sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('staff_id', sa.UUID(), nullable=False),
        sa.Column('action', sa.String(length=50), nullable=False),
        sa.Column('ip_address', sa.String(length=45), nullable=True),
        sa.Column('user_agent', sa.String(length=500), nullable=True),
        sa.Column('details', sa.String(length=1000), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['staff_id'], ['staffs.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )

    # mfa_backup_codes テーブルを作成
    op.create_table('mfa_backup_codes',
        sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('staff_id', sa.UUID(), nullable=False),
        sa.Column('code_hash', sa.String(length=255), nullable=False),
        sa.Column('is_used', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('used_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['staff_id'], ['staffs.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('code_hash')
    )


def downgrade() -> None:
    op.drop_table('mfa_backup_codes')
    op.drop_table('mfa_audit_logs')
    op.drop_column('staffs', 'mfa_backup_codes_used')
    op.drop_column('staffs', 'mfa_secret')
    op.drop_column('staffs', 'is_mfa_enabled')
