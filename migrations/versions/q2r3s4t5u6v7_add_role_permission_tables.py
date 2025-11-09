"""add role permission tables

Revision ID: q2r3s4t5u6v7
Revises: p1q2r3s4t5u6
Create Date: 2025-11-05 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'q2r3s4t5u6v7'
down_revision = 'p1q2r3s4t5u6'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Role権限テーブルを作成（既存のnoticesテーブルを活用）"""

    # RequestStatus enum
    request_status_enum = postgresql.ENUM(
        'pending', 'approved', 'rejected',
        name='requeststatus',
        create_type=True
    )
    request_status_enum.create(op.get_bind(), checkfirst=True)

    # ActionType enum
    action_type_enum = postgresql.ENUM(
        'create', 'update', 'delete',
        name='actiontype',
        create_type=True
    )
    action_type_enum.create(op.get_bind(), checkfirst=True)

    # ResourceType enum
    resource_type_enum = postgresql.ENUM(
        'welfare_recipient',
        'support_plan_cycle',
        'support_plan_status',
        name='resourcetype',
        create_type=True
    )
    resource_type_enum.create(op.get_bind(), checkfirst=True)

    # role_change_requestsテーブル作成
    op.create_table(
        'role_change_requests',
        sa.Column('id', postgresql.UUID(as_uuid=True), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('requester_staff_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('office_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('from_role', postgresql.ENUM('employee', 'manager', 'owner', name='staffrole', create_type=False), nullable=False),
        sa.Column('requested_role', postgresql.ENUM('employee', 'manager', 'owner', name='staffrole', create_type=False), nullable=False),
        sa.Column('status', postgresql.ENUM('pending', 'approved', 'rejected', name='requeststatus', create_type=False), nullable=False, server_default='pending'),
        sa.Column('request_notes', sa.Text(), nullable=True),
        sa.Column('reviewed_by_staff_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('reviewed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('reviewer_notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), onupdate=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['office_id'], ['offices.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['requester_staff_id'], ['staffs.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['reviewed_by_staff_id'], ['staffs.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )

    # role_change_requestsテーブルのインデックス
    op.create_index('ix_role_change_requests_requester_staff_id', 'role_change_requests', ['requester_staff_id'], unique=False)
    op.create_index('ix_role_change_requests_office_id', 'role_change_requests', ['office_id'], unique=False)
    op.create_index('ix_role_change_requests_status', 'role_change_requests', ['status'], unique=False)

    # employee_action_requestsテーブル作成
    op.create_table(
        'employee_action_requests',
        sa.Column('id', postgresql.UUID(as_uuid=True), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('requester_staff_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('office_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('resource_type', postgresql.ENUM(
            'welfare_recipient',
            'support_plan_cycle',
            'support_plan_status',
            name='resourcetype',
            create_type=False
        ), nullable=False),
        sa.Column('action_type', postgresql.ENUM('create', 'update', 'delete', name='actiontype', create_type=False), nullable=False),
        sa.Column('resource_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('request_data', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column('status', postgresql.ENUM('pending', 'approved', 'rejected', name='requeststatus', create_type=False), nullable=False, server_default='pending'),
        sa.Column('approved_by_staff_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('approved_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('approver_notes', sa.Text(), nullable=True),
        sa.Column('execution_result', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), onupdate=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['office_id'], ['offices.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['requester_staff_id'], ['staffs.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['approved_by_staff_id'], ['staffs.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )

    # employee_action_requestsテーブルのインデックス
    op.create_index('ix_employee_action_requests_requester_staff_id', 'employee_action_requests', ['requester_staff_id'], unique=False)
    op.create_index('ix_employee_action_requests_office_id', 'employee_action_requests', ['office_id'], unique=False)
    op.create_index('ix_employee_action_requests_status', 'employee_action_requests', ['status'], unique=False)


def downgrade() -> None:
    """ロールバック"""

    # テーブル削除
    op.drop_index('ix_employee_action_requests_status', table_name='employee_action_requests')
    op.drop_index('ix_employee_action_requests_office_id', table_name='employee_action_requests')
    op.drop_index('ix_employee_action_requests_requester_staff_id', table_name='employee_action_requests')
    op.drop_table('employee_action_requests')

    op.drop_index('ix_role_change_requests_status', table_name='role_change_requests')
    op.drop_index('ix_role_change_requests_office_id', table_name='role_change_requests')
    op.drop_index('ix_role_change_requests_requester_staff_id', table_name='role_change_requests')
    op.drop_table('role_change_requests')

    # enum削除（noticesテーブルは既存なので削除しない）
    sa.Enum(name='resourcetype').drop(op.get_bind(), checkfirst=True)
    sa.Enum(name='actiontype').drop(op.get_bind(), checkfirst=True)
    sa.Enum(name='requeststatus').drop(op.get_bind(), checkfirst=True)
