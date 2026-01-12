"""Add next_plan_start_date to calendar_event_type enum

Revision ID: x6y7z8a9b0c1
Revises: w5x6y7z8a9b0
Create Date: 2026-01-12

Task: calendar_event_type enumに次回計画開始期限の値を追加
- enum値追加: 'next_plan_start_date'
- 既存のmonitoring_deadlineイベントをnext_plan_start_dateに更新
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'x6y7z8a9b0c1'
down_revision: Union[str, None] = 'w5x6y7z8a9b0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add next_plan_start_date to calendar_event_type enum and update existing events"""

    # 1. calendar_event_type enumに新しい値を追加
    # Note: PostgreSQL enumへの値追加はトランザクション外で実行する必要がある
    op.execute("COMMIT")
    op.execute("ALTER TYPE calendar_event_type ADD VALUE IF NOT EXISTS 'next_plan_start_date'")

    # 2. 既存のmonitoring_deadlineイベントをnext_plan_start_dateに更新
    op.execute(
        """
        UPDATE calendar_events
        SET event_type = 'next_plan_start_date'
        WHERE event_type = 'monitoring_deadline'
        """
    )


def downgrade() -> None:
    """Revert next_plan_start_date events back to monitoring_deadline"""

    # 既存のnext_plan_start_dateイベントをmonitoring_deadlineに戻す
    op.execute(
        """
        UPDATE calendar_events
        SET event_type = 'monitoring_deadline'
        WHERE event_type = 'next_plan_start_date'
        """
    )

    # Note: PostgreSQLではenum値の削除は簡単にはできないため、
    # ダウングレード時は値を残したまま、データのみ戻す
