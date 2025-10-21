"""fix_calendar_event_unique_idx

Revision ID: 7kk4eluc4xjl
Revises: 5lw3xzwujmw0
Create Date: 2025-10-21 00:00:30

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7kk4eluc4xjl'
down_revision: Union[str, None] = '5lw3xzwujmw0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Step 1: 既存のインデックスを削除
    op.execute('DROP INDEX IF EXISTS idx_calendar_events_cycle_type_unique')
    op.execute('DROP INDEX IF EXISTS idx_calendar_events_status_type_unique')

    # Step 2: 重複イベントを削除（cycle_idベース）
    op.execute("""
        WITH duplicates AS (
            SELECT
                id,
                ROW_NUMBER() OVER (
                    PARTITION BY support_plan_cycle_id, event_type
                    ORDER BY created_at ASC, id ASC
                ) as row_num
            FROM calendar_events
            WHERE support_plan_cycle_id IS NOT NULL
              AND (sync_status = 'pending' OR sync_status = 'synced')
        )
        DELETE FROM calendar_events
        WHERE id IN (
            SELECT id FROM duplicates WHERE row_num > 1
        )
    """)

    # Step 3: 重複イベントを削除（status_idベース）
    op.execute("""
        WITH duplicates AS (
            SELECT
                id,
                ROW_NUMBER() OVER (
                    PARTITION BY support_plan_status_id, event_type
                    ORDER BY created_at ASC, id ASC
                ) as row_num
            FROM calendar_events
            WHERE support_plan_status_id IS NOT NULL
              AND (sync_status = 'pending' OR sync_status = 'synced')
        )
        DELETE FROM calendar_events
        WHERE id IN (
            SELECT id FROM duplicates WHERE row_num > 1
        )
    """)

    # Step 4: 元のユニーク制約を再作成
    op.execute("""
        CREATE UNIQUE INDEX idx_calendar_events_cycle_type_unique
        ON calendar_events (support_plan_cycle_id, event_type)
        WHERE support_plan_cycle_id IS NOT NULL
          AND (sync_status = 'pending' OR sync_status = 'synced')
    """)

    op.execute("""
        CREATE UNIQUE INDEX idx_calendar_events_status_type_unique
        ON calendar_events (support_plan_status_id, event_type)
        WHERE support_plan_status_id IS NOT NULL
          AND (sync_status = 'pending' OR sync_status = 'synced')
    """)


def downgrade() -> None:
    op.execute('DROP INDEX IF EXISTS idx_calendar_events_status_type_unique')
    op.execute('DROP INDEX IF EXISTS idx_calendar_events_cycle_type_unique')
