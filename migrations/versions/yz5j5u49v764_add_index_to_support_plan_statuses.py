"""add_index_to_support_plan_statuses

Revision ID: yz5j5u49v764
Revises: lql9jwfmxenr
Create Date: 2025-10-21 00:00:09

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'yz5j5u49v764'
down_revision: Union[str, None] = 'lql9jwfmxenr'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # カラム追加
    op.add_column('support_plan_statuses',
                  sa.Column('is_latest_status', sa.Boolean(), nullable=False, server_default='true'))

    # 既存レコードのデフォルト値設定
    op.execute("""
        UPDATE support_plan_statuses
        SET is_latest_status = true
        WHERE is_latest_status IS NULL
    """)

    # インデックス追加
    op.create_index('ix_support_plan_statuses_is_latest', 'support_plan_statuses', ['is_latest_status'])

    # 複合インデックス
    op.create_index('ix_support_plan_statuses_cycle_latest', 'support_plan_statuses',
                    ['plan_cycle_id', 'is_latest_status'])


def downgrade() -> None:
    op.drop_index('ix_support_plan_statuses_cycle_latest', table_name='support_plan_statuses')
    op.drop_index('ix_support_plan_statuses_is_latest', table_name='support_plan_statuses')
    op.drop_column('support_plan_statuses', 'is_latest_status')
