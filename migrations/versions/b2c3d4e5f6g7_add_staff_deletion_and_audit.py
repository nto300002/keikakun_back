"""add staff deletion and audit

Revision ID: b2c3d4e5f6g7
Revises: a7b8c9d0e1f2
Create Date: 2025-11-24 14:30:00.000000

スタッフ削除機能のためのスキーマ追加:
- staffsテーブルに論理削除カラム追加（is_deleted, deleted_at, deleted_by）
- staff_audit_logsテーブル作成（監査ログ）
- インデックス追加
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'b2c3d4e5f6g7'
down_revision: Union[str, None] = 'a7b8c9d0e1f2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # staffsテーブルに論理削除カラムを追加
    op.add_column('staffs', sa.Column('is_deleted', sa.Boolean(), nullable=False, server_default='false'))
    op.add_column('staffs', sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('staffs', sa.Column('deleted_by', postgresql.UUID(as_uuid=True), nullable=True))

    # deleted_byの外部キー制約を追加
    op.create_foreign_key(
        'fk_staffs_deleted_by_staffs',
        'staffs',
        'staffs',
        ['deleted_by'],
        ['id']
    )

    # staffsテーブルのインデックス追加
    op.create_index('idx_staff_is_deleted', 'staffs', ['is_deleted'], unique=False)
    op.create_index('idx_staff_office_id_is_deleted', 'staffs', ['office_id', 'is_deleted'], unique=False)

    # staff_audit_logsテーブル作成
    op.create_table(
        'staff_audit_logs',
        sa.Column('id', postgresql.UUID(as_uuid=True), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('staff_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('action', sa.String(length=50), nullable=False),
        sa.Column('performed_by', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('ip_address', sa.String(length=45), nullable=True),
        sa.Column('user_agent', sa.Text(), nullable=True),
        sa.Column('details', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['staff_id'], ['staffs.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['performed_by'], ['staffs.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )

    # staff_audit_logsテーブルのインデックス追加
    op.create_index('ix_staff_audit_logs_staff_id', 'staff_audit_logs', ['staff_id'], unique=False)
    op.create_index('ix_staff_audit_logs_action', 'staff_audit_logs', ['action'], unique=False)
    op.create_index('ix_staff_audit_logs_performed_by', 'staff_audit_logs', ['performed_by'], unique=False)
    op.create_index('ix_staff_audit_logs_created_at', 'staff_audit_logs', ['created_at'], unique=False)


def downgrade() -> None:
    # staff_audit_logsテーブルのインデックス削除
    op.drop_index('ix_staff_audit_logs_created_at', table_name='staff_audit_logs')
    op.drop_index('ix_staff_audit_logs_performed_by', table_name='staff_audit_logs')
    op.drop_index('ix_staff_audit_logs_action', table_name='staff_audit_logs')
    op.drop_index('ix_staff_audit_logs_staff_id', table_name='staff_audit_logs')

    # staff_audit_logsテーブル削除
    op.drop_table('staff_audit_logs')

    # staffsテーブルのインデックス削除
    op.drop_index('idx_staff_office_id_is_deleted', table_name='staffs')
    op.drop_index('idx_staff_is_deleted', table_name='staffs')

    # staffsテーブルの外部キー制約削除
    op.drop_constraint('fk_staffs_deleted_by_staffs', 'staffs', type_='foreignkey')

    # staffsテーブルのカラム削除
    op.drop_column('staffs', 'deleted_by')
    op.drop_column('staffs', 'deleted_at')
    op.drop_column('staffs', 'is_deleted')
