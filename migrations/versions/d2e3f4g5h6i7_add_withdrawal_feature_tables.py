"""add withdrawal feature tables

Revision ID: d2e3f4g5h6i7
Revises: c1d2e3f4g5h6
Create Date: 2025-11-26 10:00:00.000000

退会機能のためのスキーマ追加:
- StaffRole enumに app_admin を追加
- officesテーブルに論理削除カラム追加（is_deleted, deleted_at, deleted_by）
- audit_logsテーブル作成（統合型監査ログ）
- approval_requestsテーブル作成（統合型承認リクエスト）
- ApprovalResourceType enum作成
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'd2e3f4g5h6i7'
down_revision: Union[str, None] = 'c1d2e3f4g5h6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ===========================================
    # 1. StaffRole enumに app_admin を追加
    # ===========================================
    op.execute("ALTER TYPE staffrole ADD VALUE IF NOT EXISTS 'app_admin'")

    # ===========================================
    # 2. ApprovalResourceType enum作成
    # ===========================================
    op.execute("""
        CREATE TYPE approvalresourcetype AS ENUM (
            'role_change',
            'employee_action',
            'withdrawal'
        )
    """)

    # ===========================================
    # 3. officesテーブルに論理削除カラム追加
    # ===========================================
    op.add_column('offices', sa.Column('is_deleted', sa.Boolean(), nullable=False, server_default='false'))
    op.add_column('offices', sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('offices', sa.Column('deleted_by', postgresql.UUID(as_uuid=True), nullable=True))

    # 外部キー制約
    op.create_foreign_key(
        'fk_offices_deleted_by_staffs',
        'offices', 'staffs',
        ['deleted_by'], ['id'],
        ondelete='SET NULL'
    )

    # インデックス
    op.create_index('idx_offices_is_deleted', 'offices', ['is_deleted'], unique=False)

    # ===========================================
    # 4. audit_logsテーブル作成（統合型監査ログ）
    # ===========================================
    op.create_table(
        'audit_logs',
        sa.Column('id', postgresql.UUID(as_uuid=True), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('actor_id', postgresql.UUID(as_uuid=True), nullable=True, comment='操作実行者のスタッフID'),
        sa.Column('actor_role', sa.String(length=50), nullable=True, comment='実行時のロール'),
        sa.Column('action', sa.String(length=100), nullable=False, comment='アクション種別: staff.deleted, office.updated, withdrawal.approved など'),
        sa.Column('target_type', sa.String(length=50), nullable=False, comment='対象リソースタイプ: staff, office, withdrawal_request など'),
        sa.Column('target_id', postgresql.UUID(as_uuid=True), nullable=True, comment='対象リソースのID'),
        sa.Column('office_id', postgresql.UUID(as_uuid=True), nullable=True, comment='事務所ID（横断検索用、app_adminはNULL可）'),
        sa.Column('ip_address', sa.String(length=45), nullable=True, comment='操作元IPアドレス（IPv6対応）'),
        sa.Column('user_agent', sa.Text(), nullable=True, comment='操作元User-Agent'),
        sa.Column('details', postgresql.JSONB(astext_type=sa.Text()), nullable=True, comment='変更内容（old_values, new_valuesなど）'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('is_test_data', sa.Boolean(), nullable=False, server_default='false', comment='テストデータフラグ'),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['actor_id'], ['staffs.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['office_id'], ['offices.id'], ondelete='SET NULL')
    )

    # audit_logsテーブルのインデックス
    op.create_index('idx_audit_logs_actor_id', 'audit_logs', ['actor_id'], unique=False)
    op.create_index('idx_audit_logs_action', 'audit_logs', ['action'], unique=False)
    op.create_index('idx_audit_logs_target_type', 'audit_logs', ['target_type'], unique=False)
    op.create_index('idx_audit_logs_office_id', 'audit_logs', ['office_id'], unique=False)
    op.create_index('idx_audit_logs_created_at', 'audit_logs', ['created_at'], unique=False)
    op.create_index('idx_audit_logs_is_test_data', 'audit_logs', ['is_test_data'], unique=False)
    # 複合インデックス（よく使う検索パターン用）
    op.create_index('idx_audit_logs_office_created', 'audit_logs', ['office_id', 'created_at'], unique=False)
    op.create_index('idx_audit_logs_action_created', 'audit_logs', ['action', 'created_at'], unique=False)

    # ===========================================
    # 5. approval_requestsテーブル作成（統合型承認リクエスト）
    # ===========================================
    op.create_table(
        'approval_requests',
        sa.Column('id', postgresql.UUID(as_uuid=True), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('requester_staff_id', postgresql.UUID(as_uuid=True), nullable=False, comment='リクエスト作成者のスタッフID'),
        sa.Column('office_id', postgresql.UUID(as_uuid=True), nullable=False, comment='対象事務所ID'),
        sa.Column('resource_type', postgresql.ENUM('role_change', 'employee_action', 'withdrawal', name='approvalresourcetype', create_type=False), nullable=False, comment='リクエスト種別'),
        sa.Column('status', postgresql.ENUM('pending', 'approved', 'rejected', name='requeststatus', create_type=False), nullable=False, server_default='pending', comment='ステータス'),
        sa.Column('request_data', postgresql.JSONB(astext_type=sa.Text()), nullable=True, comment='リクエスト固有のデータ'),
        sa.Column('reviewed_by_staff_id', postgresql.UUID(as_uuid=True), nullable=True, comment='承認/却下したスタッフID'),
        sa.Column('reviewed_at', sa.DateTime(timezone=True), nullable=True, comment='承認/却下日時'),
        sa.Column('reviewer_notes', sa.Text(), nullable=True, comment='承認者のメモ'),
        sa.Column('execution_result', postgresql.JSONB(astext_type=sa.Text()), nullable=True, comment='実行結果'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('is_test_data', sa.Boolean(), nullable=False, server_default='false', comment='テストデータフラグ'),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['requester_staff_id'], ['staffs.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['office_id'], ['offices.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['reviewed_by_staff_id'], ['staffs.id'], ondelete='SET NULL')
    )

    # approval_requestsテーブルのインデックス
    op.create_index('idx_approval_requests_requester', 'approval_requests', ['requester_staff_id'], unique=False)
    op.create_index('idx_approval_requests_office', 'approval_requests', ['office_id'], unique=False)
    op.create_index('idx_approval_requests_resource_type', 'approval_requests', ['resource_type'], unique=False)
    op.create_index('idx_approval_requests_status', 'approval_requests', ['status'], unique=False)
    op.create_index('idx_approval_requests_created_at', 'approval_requests', ['created_at'], unique=False)
    op.create_index('idx_approval_requests_is_test_data', 'approval_requests', ['is_test_data'], unique=False)
    # 複合インデックス（承認待ちリクエスト検索用）
    op.create_index('idx_approval_requests_status_type', 'approval_requests', ['status', 'resource_type'], unique=False)
    op.create_index('idx_approval_requests_office_status', 'approval_requests', ['office_id', 'status'], unique=False)


def downgrade() -> None:
    # ===========================================
    # approval_requestsテーブル削除
    # ===========================================
    op.drop_index('idx_approval_requests_office_status', table_name='approval_requests')
    op.drop_index('idx_approval_requests_status_type', table_name='approval_requests')
    op.drop_index('idx_approval_requests_is_test_data', table_name='approval_requests')
    op.drop_index('idx_approval_requests_created_at', table_name='approval_requests')
    op.drop_index('idx_approval_requests_status', table_name='approval_requests')
    op.drop_index('idx_approval_requests_resource_type', table_name='approval_requests')
    op.drop_index('idx_approval_requests_office', table_name='approval_requests')
    op.drop_index('idx_approval_requests_requester', table_name='approval_requests')
    op.drop_table('approval_requests')

    # ===========================================
    # audit_logsテーブル削除
    # ===========================================
    op.drop_index('idx_audit_logs_action_created', table_name='audit_logs')
    op.drop_index('idx_audit_logs_office_created', table_name='audit_logs')
    op.drop_index('idx_audit_logs_is_test_data', table_name='audit_logs')
    op.drop_index('idx_audit_logs_created_at', table_name='audit_logs')
    op.drop_index('idx_audit_logs_office_id', table_name='audit_logs')
    op.drop_index('idx_audit_logs_target_type', table_name='audit_logs')
    op.drop_index('idx_audit_logs_action', table_name='audit_logs')
    op.drop_index('idx_audit_logs_actor_id', table_name='audit_logs')
    op.drop_table('audit_logs')

    # ===========================================
    # officesテーブルから論理削除カラム削除
    # ===========================================
    op.drop_index('idx_offices_is_deleted', table_name='offices')
    op.drop_constraint('fk_offices_deleted_by_staffs', 'offices', type_='foreignkey')
    op.drop_column('offices', 'deleted_by')
    op.drop_column('offices', 'deleted_at')
    op.drop_column('offices', 'is_deleted')

    # ===========================================
    # ApprovalResourceType enum削除
    # ===========================================
    op.execute("DROP TYPE IF EXISTS approvalresourcetype")

    # ===========================================
    # StaffRole enumから app_admin を削除
    # 注意: PostgreSQLでは直接enumの値を削除できないため、
    # 本番環境では新しいenumを作成して入れ替える必要があります
    # ===========================================
    # 開発環境用のシンプルな対応（本番では使用しないでください）
    # op.execute("ALTER TYPE staffrole RENAME TO staffrole_old")
    # op.execute("CREATE TYPE staffrole AS ENUM ('employee', 'manager', 'owner')")
    # op.execute("DROP TYPE staffrole_old")
    pass  # enum値の削除は手動で行う必要があります
