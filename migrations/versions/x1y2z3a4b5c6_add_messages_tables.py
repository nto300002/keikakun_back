"""add messages and message recipients tables

Revision ID: x1y2z3a4b5c6
Revises: w9x0y1z2a3b4
Create Date: 2025-11-21

メッセージ・お知らせ機能のデータベーステーブル追加
- messages: メッセージ本体
- message_recipients: 受信者管理（中間テーブル）
- message_audit_logs: 監査ログ
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'x1y2z3a4b5c6'
down_revision: Union[str, None] = 'w9x0y1z2a3b4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """メッセージ関連テーブルを作成"""

    # messages テーブルを作成
    op.create_table(
        'messages',
        sa.Column('id', postgresql.UUID(as_uuid=True), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('sender_staff_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('office_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('message_type', sa.String(length=20), nullable=False, server_default='personal'),
        sa.Column('priority', sa.String(length=20), nullable=False, server_default='normal'),
        sa.Column('title', sa.String(length=200), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['sender_staff_id'], ['staffs.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['office_id'], ['offices.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )

    # message_recipients テーブルを作成
    op.create_table(
        'message_recipients',
        sa.Column('id', postgresql.UUID(as_uuid=True), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('message_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('recipient_staff_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('is_read', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('read_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('is_archived', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['message_id'], ['messages.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['recipient_staff_id'], ['staffs.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('message_id', 'recipient_staff_id', name='uq_message_recipient')
    )

    # message_audit_logs テーブルを作成
    op.create_table(
        'message_audit_logs',
        sa.Column('id', postgresql.UUID(as_uuid=True), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('staff_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('message_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('action', sa.String(length=50), nullable=False),
        sa.Column('ip_address', sa.String(length=45), nullable=True),
        sa.Column('user_agent', sa.Text(), nullable=True),
        sa.Column('success', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['staff_id'], ['staffs.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['message_id'], ['messages.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )

    # インデックスを作成（messages）
    op.create_index('idx_messages_office_created', 'messages', ['office_id', sa.text('created_at DESC')], unique=False)
    op.create_index('idx_messages_sender', 'messages', ['sender_staff_id'], unique=False)
    op.create_index('idx_messages_type', 'messages', ['message_type'], unique=False)

    # インデックスを作成（message_recipients）
    op.create_index('idx_message_recipients_recipient_read', 'message_recipients', ['recipient_staff_id', 'is_read'], unique=False)
    op.create_index('idx_message_recipients_message', 'message_recipients', ['message_id'], unique=False)
    op.create_index('idx_message_recipients_created', 'message_recipients', [sa.text('created_at DESC')], unique=False)

    # インデックスを作成（message_audit_logs）
    op.create_index('idx_message_audit_staff', 'message_audit_logs', ['staff_id'], unique=False)
    op.create_index('idx_message_audit_message', 'message_audit_logs', ['message_id'], unique=False)
    op.create_index('idx_message_audit_created', 'message_audit_logs', [sa.text('created_at DESC')], unique=False)
    op.create_index('idx_message_audit_action', 'message_audit_logs', ['action'], unique=False)


def downgrade() -> None:
    """ロールバック"""

    # インデックスを削除（message_audit_logs）
    op.drop_index('idx_message_audit_action', table_name='message_audit_logs')
    op.drop_index('idx_message_audit_created', table_name='message_audit_logs')
    op.drop_index('idx_message_audit_message', table_name='message_audit_logs')
    op.drop_index('idx_message_audit_staff', table_name='message_audit_logs')

    # インデックスを削除（message_recipients）
    op.drop_index('idx_message_recipients_created', table_name='message_recipients')
    op.drop_index('idx_message_recipients_message', table_name='message_recipients')
    op.drop_index('idx_message_recipients_recipient_read', table_name='message_recipients')

    # インデックスを削除（messages）
    op.drop_index('idx_messages_type', table_name='messages')
    op.drop_index('idx_messages_sender', table_name='messages')
    op.drop_index('idx_messages_office_created', table_name='messages')

    # テーブルを削除（依存関係の逆順）
    op.drop_table('message_audit_logs')
    op.drop_table('message_recipients')
    op.drop_table('messages')
