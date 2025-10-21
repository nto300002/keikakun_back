"""add_google_calendar_accounts

Revision ID: gcphzt136gvc
Revises: cfweclrxe73i
Create Date: 2025-10-21 00:00:13

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'gcphzt136gvc'
down_revision: Union[str, None] = 'cfweclrxe73i'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ENUMタイプ作成
    op.execute("""
        CREATE TYPE calendar_connection_status AS ENUM (
            'not_connected', 'connected', 'error', 'suspended'
        )
    """)

    op.execute("""
        CREATE TYPE notification_timing AS ENUM (
            'early', 'standard', 'minimal', 'custom'
        )
    """)

    # 事業所カレンダーアカウントテーブル
    op.create_table('office_calendar_accounts',
        sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('office_id', sa.UUID(), nullable=False),
        sa.Column('google_calendar_id', sa.String(length=255), nullable=True),
        sa.Column('calendar_name', sa.String(length=255), nullable=True),
        sa.Column('calendar_url', sa.Text(), nullable=True),
        sa.Column('service_account_key', sa.Text(), nullable=True),
        sa.Column('service_account_email', sa.String(length=255), nullable=True),
        sa.Column('connection_status', sa.Enum(
            'not_connected', 'connected', 'error', 'suspended',
            name='calendar_connection_status'
        ), nullable=False, server_default='not_connected'),
        sa.Column('last_sync_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_error_message', sa.Text(), nullable=True),
        sa.Column('auto_invite_staff', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('default_reminder_minutes', sa.Integer(), nullable=False, server_default='1440'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('office_id'),
        sa.UniqueConstraint('google_calendar_id')
    )

    # スタッフカレンダーアカウントテーブル
    op.create_table('staff_calendar_accounts',
        sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('staff_id', sa.UUID(), nullable=False),
        sa.Column('calendar_notifications_enabled', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('email_notifications_enabled', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('in_app_notifications_enabled', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('notification_email', sa.String(length=255), nullable=True),
        sa.Column('notification_timing', sa.Enum(
            'early', 'standard', 'minimal', 'custom',
            name='notification_timing'
        ), nullable=False, server_default='standard'),
        sa.Column('custom_reminder_days', sa.String(length=100), nullable=True),
        sa.Column('notifications_paused_until', sa.Date(), nullable=True),
        sa.Column('pause_reason', sa.String(length=255), nullable=True),
        sa.Column('has_calendar_access', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('calendar_access_granted_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('total_notifications_sent', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('last_notification_sent_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('staff_id')
    )

    # インデックス作成
    op.create_index('idx_office_calendar_accounts_office_id', 'office_calendar_accounts', ['office_id'])
    op.create_index('idx_office_calendar_accounts_connection_status', 'office_calendar_accounts', ['connection_status'])
    op.create_index('idx_staff_calendar_accounts_staff_id', 'staff_calendar_accounts', ['staff_id'])
    op.create_index('idx_staff_calendar_accounts_notification_timing', 'staff_calendar_accounts', ['notification_timing'])

    # updated_at自動更新トリガー
    op.execute("""
        CREATE OR REPLACE FUNCTION update_calendar_accounts_updated_at()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.updated_at = NOW();
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
    """)

    op.execute("""
        CREATE TRIGGER trigger_update_office_calendar_accounts_updated_at
        BEFORE UPDATE ON office_calendar_accounts
        FOR EACH ROW
        EXECUTE FUNCTION update_calendar_accounts_updated_at()
    """)

    op.execute("""
        CREATE TRIGGER trigger_update_staff_calendar_accounts_updated_at
        BEFORE UPDATE ON staff_calendar_accounts
        FOR EACH ROW
        EXECUTE FUNCTION update_calendar_accounts_updated_at()
    """)


def downgrade() -> None:
    op.execute('DROP TRIGGER IF EXISTS trigger_update_staff_calendar_accounts_updated_at ON staff_calendar_accounts')
    op.execute('DROP TRIGGER IF EXISTS trigger_update_office_calendar_accounts_updated_at ON office_calendar_accounts')
    op.execute('DROP FUNCTION IF EXISTS update_calendar_accounts_updated_at()')

    op.drop_index('idx_staff_calendar_accounts_notification_timing', table_name='staff_calendar_accounts')
    op.drop_index('idx_staff_calendar_accounts_staff_id', table_name='staff_calendar_accounts')
    op.drop_index('idx_office_calendar_accounts_connection_status', table_name='office_calendar_accounts')
    op.drop_index('idx_office_calendar_accounts_office_id', table_name='office_calendar_accounts')

    op.drop_table('staff_calendar_accounts')
    op.drop_table('office_calendar_accounts')

    op.execute('DROP TYPE IF EXISTS notification_timing')
    op.execute('DROP TYPE IF EXISTS calendar_connection_status')
