"""add_notice_table

Revision ID: j6ewiuu6hhlu
Revises: f07ueuee1rdx
Create Date: 2025-10-21 00:00:15

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'j6ewiuu6hhlu'
down_revision: Union[str, None] = 'f07ueuee1rdx'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Noticesテーブル作成
    op.create_table('notices',
        sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('recipient_staff_id', sa.UUID(), nullable=False),
        sa.Column('office_id', sa.UUID(), nullable=False),
        sa.Column('type', sa.String(length=50), nullable=False),
        sa.Column('title', sa.String(length=255), nullable=False),
        sa.Column('content', sa.Text(), nullable=True),
        sa.Column('link_url', sa.String(length=255), nullable=True),
        sa.Column('is_read', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['recipient_staff_id'], ['staffs.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['office_id'], ['offices.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )

    # 基本インデックス作成
    op.create_index('idx_notices_recipient_staff_id', 'notices', ['recipient_staff_id'])
    op.create_index('idx_notices_office_id', 'notices', ['office_id'])
    op.create_index('idx_notices_is_read', 'notices', ['is_read'])
    op.create_index('idx_notices_created_at', 'notices', ['created_at'])

    # updated_at自動更新トリガー
    op.execute("""
        CREATE OR REPLACE FUNCTION update_notices_updated_at()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.updated_at = NOW();
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
    """)

    op.execute("""
        CREATE TRIGGER trigger_update_notices_updated_at
        BEFORE UPDATE ON notices
        FOR EACH ROW
        EXECUTE FUNCTION update_notices_updated_at()
    """)


def downgrade() -> None:
    op.execute('DROP TRIGGER IF EXISTS trigger_update_notices_updated_at ON notices')
    op.execute('DROP FUNCTION IF EXISTS update_notices_updated_at()')

    op.drop_index('idx_notices_created_at', table_name='notices')
    op.drop_index('idx_notices_is_read', table_name='notices')
    op.drop_index('idx_notices_office_id', table_name='notices')
    op.drop_index('idx_notices_recipient_staff_id', table_name='notices')

    op.drop_table('notices')
