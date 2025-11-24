"""add is_test_data to message tables

Revision ID: a7b8c9d0e1f2
Revises: x1y2z3a4b5c6
Create Date: 2025-11-23

メッセージ関連テーブルに is_test_data カラムを追加
- messages
- message_recipients
- message_audit_logs
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a7b8c9d0e1f2'
down_revision: Union[str, None] = 'x1y2z3a4b5c6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """is_test_data カラムを追加"""

    # messages テーブルに is_test_data カラムを追加
    op.add_column('messages',
        sa.Column('is_test_data', sa.Boolean(), nullable=False, server_default=sa.text('false'))
    )
    op.create_index('idx_messages_is_test_data', 'messages', ['is_test_data'], unique=False)

    # message_recipients テーブルに is_test_data カラムを追加
    op.add_column('message_recipients',
        sa.Column('is_test_data', sa.Boolean(), nullable=False, server_default=sa.text('false'))
    )
    op.create_index('idx_message_recipients_is_test_data', 'message_recipients', ['is_test_data'], unique=False)

    # message_audit_logs テーブルに is_test_data カラムを追加
    op.add_column('message_audit_logs',
        sa.Column('is_test_data', sa.Boolean(), nullable=False, server_default=sa.text('false'))
    )
    op.create_index('idx_message_audit_logs_is_test_data', 'message_audit_logs', ['is_test_data'], unique=False)


def downgrade() -> None:
    """is_test_data カラムを削除"""

    # インデックスを削除
    op.drop_index('idx_message_audit_logs_is_test_data', table_name='message_audit_logs')
    op.drop_index('idx_message_recipients_is_test_data', table_name='message_recipients')
    op.drop_index('idx_messages_is_test_data', table_name='messages')

    # カラムを削除
    op.drop_column('message_audit_logs', 'is_test_data')
    op.drop_column('message_recipients', 'is_test_data')
    op.drop_column('messages', 'is_test_data')
