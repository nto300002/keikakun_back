"""add office info and audit

Revision ID: c1d2e3f4g5h6
Revises: b2c3d4e5f6g7
Create Date: 2025-11-24 15:00:00.000000

事務所情報変更機能のためのスキーマ追加:
- officesテーブルに連絡先情報カラム追加（address, phone_number, email）
- office_audit_logsテーブル作成（監査ログ）
- インデックス追加
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'c1d2e3f4g5h6'
down_revision: Union[str, None] = 'b2c3d4e5f6g7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # officesテーブルに連絡先情報カラムを追加
    op.add_column('offices', sa.Column('address', sa.String(length=500), nullable=True))
    op.add_column('offices', sa.Column('phone_number', sa.String(length=20), nullable=True))
    op.add_column('offices', sa.Column('email', sa.String(length=255), nullable=True))

    # office_audit_logsテーブル作成
    op.create_table(
        'office_audit_logs',
        sa.Column('id', postgresql.UUID(as_uuid=True), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('office_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('staff_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('action_type', sa.String(length=100), nullable=False, comment='アクション種別: office_info_updated など'),
        sa.Column('details', sa.Text(), nullable=True, comment='変更内容の詳細（JSON形式）'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('is_test_data', sa.Boolean(), nullable=False, server_default='false', comment='テストデータフラグ'),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['office_id'], ['offices.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['staff_id'], ['staffs.id'], ondelete='SET NULL')
    )

    # office_audit_logsテーブルのインデックス追加
    op.create_index('idx_office_audit_logs_office_id', 'office_audit_logs', ['office_id'], unique=False)
    op.create_index('idx_office_audit_logs_staff_id', 'office_audit_logs', ['staff_id'], unique=False)
    op.create_index('idx_office_audit_logs_created_at', 'office_audit_logs', ['created_at'], unique=False)
    op.create_index('idx_office_audit_logs_is_test_data', 'office_audit_logs', ['is_test_data'], unique=False)


def downgrade() -> None:
    # office_audit_logsテーブルのインデックス削除
    op.drop_index('idx_office_audit_logs_is_test_data', table_name='office_audit_logs')
    op.drop_index('idx_office_audit_logs_created_at', table_name='office_audit_logs')
    op.drop_index('idx_office_audit_logs_staff_id', table_name='office_audit_logs')
    op.drop_index('idx_office_audit_logs_office_id', table_name='office_audit_logs')

    # office_audit_logsテーブル削除
    op.drop_table('office_audit_logs')

    # officesテーブルから連絡先情報カラムを削除
    op.drop_column('offices', 'email')
    op.drop_column('offices', 'phone_number')
    op.drop_column('offices', 'address')
