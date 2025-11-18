"""add terms agreements table

Revision ID: s4t5u6v7w8x9
Revises: r3s4t5u6v7w8
Create Date: 2025-11-18 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 's4t5u6v7w8x9'
down_revision = 'r3s4t5u6v7w8'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """利用規約・プライバシーポリシーの同意履歴テーブルを作成"""

    # terms_agreements テーブルを作成
    op.create_table(
        'terms_agreements',
        sa.Column('id', postgresql.UUID(as_uuid=True), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('staff_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('terms_of_service_agreed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('privacy_policy_agreed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('terms_version', sa.String(length=50), nullable=True),
        sa.Column('privacy_version', sa.String(length=50), nullable=True),
        sa.Column('ip_address', sa.String(length=45), nullable=True),
        sa.Column('user_agent', sa.String(length=500), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['staff_id'], ['staffs.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )

    # インデックスを作成
    op.create_index('idx_terms_agreements_staff_id', 'terms_agreements', ['staff_id'], unique=True)
    op.create_index('idx_terms_agreements_tos_agreed', 'terms_agreements', ['terms_of_service_agreed_at'], unique=False)
    op.create_index('idx_terms_agreements_privacy_agreed', 'terms_agreements', ['privacy_policy_agreed_at'], unique=False)


def downgrade() -> None:
    """ロールバック"""

    # インデックスを削除
    op.drop_index('idx_terms_agreements_privacy_agreed', table_name='terms_agreements')
    op.drop_index('idx_terms_agreements_tos_agreed', table_name='terms_agreements')
    op.drop_index('idx_terms_agreements_staff_id', table_name='terms_agreements')

    # テーブルを削除
    op.drop_table('terms_agreements')
