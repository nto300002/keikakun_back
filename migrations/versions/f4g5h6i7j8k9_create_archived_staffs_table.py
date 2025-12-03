"""create archived_staffs table

Revision ID: f4g5h6i7j8k9
Revises: e3f4g5h6i7j8
Create Date: 2025-12-02 14:00:00.000000

法定保存義務に基づくスタッフアーカイブテーブルの作成:
- 労働基準法第109条：労働者名簿を退職後5年間保存
- 障害者総合支援法：サービス提供記録を5年間保存
- 個人情報は匿名化、法定保存が必要な情報のみを保持
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'f4g5h6i7j8k9'
down_revision: Union[str, None] = 'e3f4g5h6i7j8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """アーカイブテーブルを作成"""

    op.create_table(
        'archived_staffs',
        sa.Column('id', postgresql.UUID(as_uuid=True), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('original_staff_id', postgresql.UUID(as_uuid=True), nullable=False, comment='元のスタッフID（参照整合性なし）'),
        sa.Column('anonymized_full_name', sa.String(length=255), nullable=False, comment='匿名化された氏名（例: スタッフ-ABC123）'),
        sa.Column('anonymized_email', sa.String(length=255), nullable=False, comment='匿名化されたメール（例: archived-ABC123@deleted.local）'),
        sa.Column('role', sa.String(length=20), nullable=False, comment='役職（owner/manager/employee）'),
        sa.Column('office_id', postgresql.UUID(as_uuid=True), nullable=True, comment='所属していた事務所ID（参照整合性なし）'),
        sa.Column('office_name', sa.String(length=255), nullable=True, comment='事務所名（スナップショット）'),
        sa.Column('hired_at', sa.DateTime(timezone=True), nullable=False, comment='雇入れ日（元のcreated_at）'),
        sa.Column('terminated_at', sa.DateTime(timezone=True), nullable=False, comment='退職日（deleted_at）'),
        sa.Column('archived_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False, comment='アーカイブ作成日時'),
        sa.Column('archive_reason', sa.String(length=50), nullable=False, comment='アーカイブ理由（staff_deletion/staff_withdrawal/office_withdrawal）'),
        sa.Column('legal_retention_until', sa.DateTime(timezone=True), nullable=False, comment='法定保存期限（terminated_at + 5年）'),
        sa.Column('metadata', postgresql.JSONB(astext_type=sa.Text()), nullable=True, comment='その他の法定保存が必要なメタデータ'),
        sa.Column('is_test_data', sa.Boolean(), server_default='false', nullable=False, comment='テストデータフラグ'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )

    # インデックスを作成
    op.create_index('idx_archived_staffs_original_id', 'archived_staffs', ['original_staff_id'])
    op.create_index('idx_archived_staffs_office_id', 'archived_staffs', ['office_id'])
    op.create_index('idx_archived_staffs_terminated_at', 'archived_staffs', ['terminated_at'])
    op.create_index('idx_archived_staffs_archived_at', 'archived_staffs', ['archived_at'])
    op.create_index('idx_archived_staffs_retention_until', 'archived_staffs', ['legal_retention_until'])
    op.create_index('idx_archived_staffs_is_test_data', 'archived_staffs', ['is_test_data'])

    # テーブルコメント
    op.execute("""
        COMMENT ON TABLE archived_staffs IS
        '法定保存義務に基づくスタッフアーカイブ（労働基準法・障害者総合支援法対応）'
    """)


def downgrade() -> None:
    """ロールバック"""

    op.drop_index('idx_archived_staffs_is_test_data', table_name='archived_staffs')
    op.drop_index('idx_archived_staffs_retention_until', table_name='archived_staffs')
    op.drop_index('idx_archived_staffs_archived_at', table_name='archived_staffs')
    op.drop_index('idx_archived_staffs_terminated_at', table_name='archived_staffs')
    op.drop_index('idx_archived_staffs_office_id', table_name='archived_staffs')
    op.drop_index('idx_archived_staffs_original_id', table_name='archived_staffs')
    op.drop_table('archived_staffs')
