"""add inquiry_details table

Revision ID: a1b2c3d4e5f6
Revises: x1y2z3a4b5c6
Create Date: 2025-12-04

問い合わせ機能のデータベーステーブル追加
- inquiry_details: 問い合わせ固有の情報（Messageとの1:1関連）
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = 'x1y2z3a4b5c6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """inquiry_details テーブルを作成"""

    # InquiryStatus と InquiryPriority の ENUM 型を作成
    op.execute("""
        CREATE TYPE inquirystatus AS ENUM (
            'new',
            'open',
            'in_progress',
            'answered',
            'closed',
            'spam'
        )
    """)

    op.execute("""
        CREATE TYPE inquirypriority AS ENUM (
            'low',
            'normal',
            'high'
        )
    """)

    # inquiry_details テーブルを作成
    op.create_table(
        'inquiry_details',
        sa.Column('id', postgresql.UUID(as_uuid=True), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('message_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('sender_name', sa.String(length=100), nullable=True),
        sa.Column('sender_email', sa.String(length=255), nullable=True),
        sa.Column('ip_address', sa.String(length=45), nullable=True),
        sa.Column('user_agent', sa.Text(), nullable=True),
        sa.Column('status', postgresql.ENUM(
            'new', 'open', 'in_progress', 'answered', 'closed', 'spam',
            name='inquirystatus',
            create_type=False
        ), nullable=False, server_default='new'),
        sa.Column('assigned_staff_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('priority', postgresql.ENUM(
            'low', 'normal', 'high',
            name='inquirypriority',
            create_type=False
        ), nullable=False, server_default='normal'),
        sa.Column('admin_notes', sa.Text(), nullable=True),
        sa.Column('delivery_log', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('is_test_data', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.ForeignKeyConstraint(['message_id'], ['messages.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['assigned_staff_id'], ['staffs.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('message_id', name='uq_inquiry_message')
    )

    # インデックスを作成
    op.create_index('ix_inquiry_details_message_id', 'inquiry_details', ['message_id'], unique=True)
    op.create_index('ix_inquiry_details_sender_email', 'inquiry_details', ['sender_email'], unique=False)
    op.create_index('ix_inquiry_details_status', 'inquiry_details', ['status'], unique=False)
    op.create_index('ix_inquiry_details_assigned_staff_id', 'inquiry_details', ['assigned_staff_id'], unique=False)
    op.create_index('ix_inquiry_details_priority', 'inquiry_details', ['priority'], unique=False)
    op.create_index('ix_inquiry_details_created_at', 'inquiry_details', ['created_at'], unique=False)
    op.create_index('ix_inquiry_details_is_test_data', 'inquiry_details', ['is_test_data'], unique=False)

    # 複合インデックスを作成
    op.create_index('ix_inquiry_details_status_created', 'inquiry_details', ['status', sa.text('created_at DESC')], unique=False)
    op.create_index('ix_inquiry_details_assigned_status', 'inquiry_details', ['assigned_staff_id', 'status'], unique=False)
    op.create_index('ix_inquiry_details_priority_status', 'inquiry_details', ['priority', 'status'], unique=False)


def downgrade() -> None:
    """ロールバック"""

    # 複合インデックスを削除
    op.drop_index('ix_inquiry_details_priority_status', table_name='inquiry_details')
    op.drop_index('ix_inquiry_details_assigned_status', table_name='inquiry_details')
    op.drop_index('ix_inquiry_details_status_created', table_name='inquiry_details')

    # インデックスを削除
    op.drop_index('ix_inquiry_details_is_test_data', table_name='inquiry_details')
    op.drop_index('ix_inquiry_details_created_at', table_name='inquiry_details')
    op.drop_index('ix_inquiry_details_priority', table_name='inquiry_details')
    op.drop_index('ix_inquiry_details_assigned_staff_id', table_name='inquiry_details')
    op.drop_index('ix_inquiry_details_status', table_name='inquiry_details')
    op.drop_index('ix_inquiry_details_sender_email', table_name='inquiry_details')
    op.drop_index('ix_inquiry_details_message_id', table_name='inquiry_details')

    # テーブルを削除
    op.drop_table('inquiry_details')

    # ENUM 型を削除
    op.execute('DROP TYPE inquirypriority')
    op.execute('DROP TYPE inquirystatus')
