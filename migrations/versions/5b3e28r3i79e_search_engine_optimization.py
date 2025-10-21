"""search_engine_optimization

Revision ID: 5b3e28r3i79e
Revises: lva6t2b4d1rl
Create Date: 2025-10-21 00:00:07

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '5b3e28r3i79e'
down_revision: Union[str, None] = 'lva6t2b4d1rl'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # pg_trgm拡張機能有効化後に実行
    op.execute("""
        CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_welfare_recipients_furigana_trgm
        ON welfare_recipients USING gin ((last_name_furigana || ' ' || first_name_furigana) gin_trgm_ops)
    """)

    # 個別カラムのtrigramインデックスも作成（より柔軟な検索用）
    op.execute("""
        CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_welfare_recipients_fname_furigana_trgm
        ON welfare_recipients USING gin (first_name_furigana gin_trgm_ops)
    """)

    op.execute("""
        CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_welfare_recipients_lname_furigana_trgm
        ON welfare_recipients USING gin (last_name_furigana gin_trgm_ops)
    """)


def downgrade() -> None:
    op.execute('DROP INDEX IF EXISTS idx_welfare_recipients_lname_furigana_trgm')
    op.execute('DROP INDEX IF EXISTS idx_welfare_recipients_fname_furigana_trgm')
    op.execute('DROP INDEX IF EXISTS idx_welfare_recipients_furigana_trgm')
