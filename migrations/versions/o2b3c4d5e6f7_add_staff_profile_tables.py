"""add_staff_profile_tables

Revision ID: o2b3c4d5e6f7
Revises: n1a2b3c4d5e6
Create Date: 2025-10-31 00:01:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


# revision identifiers, used by Alembic.
revision: str = 'o2b3c4d5e6f7'
down_revision: Union[str, None] = 'n1a2b3c4d5e6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # EmailChangeRequestテーブルを作成
    op.create_table('email_change_requests',
        sa.Column('id', UUID(as_uuid=True), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('staff_id', UUID(as_uuid=True), nullable=False),
        sa.Column('old_email', sa.String(255), nullable=False),
        sa.Column('new_email', sa.String(255), nullable=False),
        sa.Column('verification_token', sa.String(255), nullable=False),
        sa.Column('status', sa.String(50), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['staff_id'], ['staffs.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_email_change_requests_verification_token', 'email_change_requests', ['verification_token'], unique=True)

    # Trigger for email_change_requests
    op.execute("""
        CREATE TRIGGER update_email_change_requests_updated_at
        BEFORE UPDATE ON email_change_requests
        FOR EACH ROW
        EXECUTE FUNCTION update_updated_at_column()
    """)

    # PasswordHistoryテーブルを作成
    op.create_table('password_histories',
        sa.Column('id', UUID(as_uuid=True), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('staff_id', UUID(as_uuid=True), nullable=False),
        sa.Column('hashed_password', sa.String(255), nullable=False),
        sa.Column('changed_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['staff_id'], ['staffs.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_password_histories_staff_id', 'password_histories', ['staff_id'])

    # AuditLogテーブルを作成
    op.create_table('audit_logs',
        sa.Column('id', UUID(as_uuid=True), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('staff_id', UUID(as_uuid=True), nullable=False),
        sa.Column('action', sa.String(100), nullable=False),
        sa.Column('old_value', sa.Text(), nullable=True),
        sa.Column('new_value', sa.Text(), nullable=True),
        sa.Column('ip_address', sa.String(45), nullable=True),
        sa.Column('user_agent', sa.Text(), nullable=True),
        sa.Column('timestamp', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['staff_id'], ['staffs.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_audit_logs_staff_id', 'audit_logs', ['staff_id'])
    op.create_index('ix_audit_logs_action', 'audit_logs', ['action'])


def downgrade() -> None:
    op.drop_index('ix_audit_logs_action', 'audit_logs')
    op.drop_index('ix_audit_logs_staff_id', 'audit_logs')
    op.drop_table('audit_logs')

    op.drop_index('ix_password_histories_staff_id', 'password_histories')
    op.drop_table('password_histories')

    op.execute('DROP TRIGGER IF EXISTS update_email_change_requests_updated_at ON email_change_requests')
    op.drop_index('ix_email_change_requests_verification_token', 'email_change_requests')
    op.drop_table('email_change_requests')
