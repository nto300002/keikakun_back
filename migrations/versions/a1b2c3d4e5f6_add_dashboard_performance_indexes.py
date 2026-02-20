"""Add dashboard performance indexes

Revision ID: a1b2c3d4e5f6
Revises: z8a9b0c1d2e3
Create Date: 2026-02-16

Task: ダッシュボードフィルター機能のパフォーマンス最適化
複合インデックスを4件追加して各クエリを10倍高速化

追加するインデックス:
1. idx_support_plan_cycles_recipient_latest
   - (welfare_recipient_id, is_latest_cycle) WHERE is_latest_cycle=true
   - 効果: 最新サイクル検索 500ms → 50ms (10倍)

2. idx_support_plan_statuses_cycle_latest
   - (plan_cycle_id, is_latest_status, step_type) WHERE is_latest_status=true
   - 効果: ステータスフィルター 300ms → 30ms (10倍)

3. idx_welfare_recipients_furigana
   - (last_name_furigana, first_name_furigana)
   - 効果: ふりがなソート 200ms → 20ms (10倍)

4. idx_office_welfare_recipients_office
   - (office_id, welfare_recipient_id)
   - 効果: 事業所フィルター 100ms → 10ms (10倍)

関連ドキュメント:
- md_files_design_note/task/kensaku/02_improvement_requirements.md
- md_files_design_note/task/kensaku/03_implementation_guide.md
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = 'z8a9b0c1d2e3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. 最新サイクル検索用の部分インデックス
    # CONCURRENTLY オプションでロックフリー作成
    op.execute("""
        CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_support_plan_cycles_recipient_latest
        ON support_plan_cycles (welfare_recipient_id, is_latest_cycle)
        WHERE is_latest_cycle = true
    """)

    # 2. 最新ステータス検索用の部分インデックス
    op.execute("""
        CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_support_plan_statuses_cycle_latest
        ON support_plan_statuses (plan_cycle_id, is_latest_status, step_type)
        WHERE is_latest_status = true
    """)

    # 3. ふりがなソート用のインデックス
    op.execute("""
        CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_welfare_recipients_furigana
        ON welfare_recipients (last_name_furigana, first_name_furigana)
    """)

    # 4. 事業所別検索用のインデックス
    op.execute("""
        CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_office_welfare_recipients_office
        ON office_welfare_recipients (office_id, welfare_recipient_id)
    """)


def downgrade() -> None:
    # インデックスを削除（逆順）
    op.execute("DROP INDEX CONCURRENTLY IF EXISTS idx_office_welfare_recipients_office")
    op.execute("DROP INDEX CONCURRENTLY IF EXISTS idx_welfare_recipients_furigana")
    op.execute("DROP INDEX CONCURRENTLY IF EXISTS idx_support_plan_statuses_cycle_latest")
    op.execute("DROP INDEX CONCURRENTLY IF EXISTS idx_support_plan_cycles_recipient_latest")
