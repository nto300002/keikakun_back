"""fix_calendar_unique_index

Revision ID: zxz0k0ya6bc8
Revises: zrcknaddjteq
Create Date: 2025-10-21 00:00:27

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'zxz0k0ya6bc8'
down_revision: Union[str, None] = 'zrcknaddjteq'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 既存のインデックスを削除（存在する場合）
    op.execute('DROP INDEX IF EXISTS idx_calendar_events_cycle_type_unique')
    op.execute('DROP INDEX IF EXISTS idx_calendar_events_status_type_unique')

    # 新しいインデックスを作成（IMMUTABLEな条件式を使用）
    op.execute("""
        CREATE UNIQUE INDEX idx_calendar_events_cycle_type_unique
        ON calendar_events(support_plan_cycle_id, event_type)
        WHERE support_plan_cycle_id IS NOT NULL AND (sync_status = 'pending' OR sync_status = 'synced')
    """)

    op.execute("""
        CREATE UNIQUE INDEX idx_calendar_events_status_type_unique
        ON calendar_events(support_plan_status_id, event_type)
        WHERE support_plan_status_id IS NOT NULL AND (sync_status = 'pending' OR sync_status = 'synced')
    """)


def downgrade() -> None:
    op.execute('DROP INDEX IF EXISTS idx_calendar_events_status_type_unique')
    op.execute('DROP INDEX IF EXISTS idx_calendar_events_cycle_type_unique')
