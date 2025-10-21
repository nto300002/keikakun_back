"""fix_check_constraint

Revision ID: j55xku9clhmn
Revises: zxz0k0ya6bc8
Create Date: 2025-10-21 00:00:28

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'j55xku9clhmn'
down_revision: Union[str, None] = 'zxz0k0ya6bc8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 外部キー制約追加
    # 1. office_id -> offices(id)
    op.execute("""
        ALTER TABLE calendar_events
        ADD CONSTRAINT fk_calendar_events_office_id
        FOREIGN KEY (office_id) REFERENCES offices(id) ON DELETE CASCADE
    """)

    # 2. welfare_recipient_id -> welfare_recipients(id)
    op.execute("""
        ALTER TABLE calendar_events
        ADD CONSTRAINT fk_calendar_events_welfare_recipient_id
        FOREIGN KEY (welfare_recipient_id) REFERENCES welfare_recipients(id) ON DELETE CASCADE
    """)

    # 3. support_plan_cycle_id -> support_plan_cycles(id)
    op.execute("""
        ALTER TABLE calendar_events
        ADD CONSTRAINT fk_calendar_events_support_plan_cycle_id
        FOREIGN KEY (support_plan_cycle_id) REFERENCES support_plan_cycles(id) ON DELETE CASCADE
    """)

    # 4. support_plan_status_id -> support_plan_statuses(id)
    op.execute("""
        ALTER TABLE calendar_events
        ADD CONSTRAINT fk_calendar_events_support_plan_status_id
        FOREIGN KEY (support_plan_status_id) REFERENCES support_plan_statuses(id) ON DELETE CASCADE
    """)


def downgrade() -> None:
    op.execute('ALTER TABLE calendar_events DROP CONSTRAINT IF EXISTS fk_calendar_events_support_plan_status_id')
    op.execute('ALTER TABLE calendar_events DROP CONSTRAINT IF EXISTS fk_calendar_events_support_plan_cycle_id')
    op.execute('ALTER TABLE calendar_events DROP CONSTRAINT IF EXISTS fk_calendar_events_welfare_recipient_id')
    op.execute('ALTER TABLE calendar_events DROP CONSTRAINT IF EXISTS fk_calendar_events_office_id')
