"""add_support_plan_cycles_office_id

Revision ID: 5lw3xzwujmw0
Revises: j55xku9clhmn
Create Date: 2025-10-21 00:00:29

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '5lw3xzwujmw0'
down_revision: Union[str, None] = 'j55xku9clhmn'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # OfficeCalendarAccount外部キー制約
    op.execute("""
        ALTER TABLE office_calendar_accounts
        ADD CONSTRAINT fk_office_calendar_accounts_office_id
        FOREIGN KEY (office_id) REFERENCES offices(id) ON DELETE CASCADE
    """)

    # StaffCalendarAccount外部キー制約
    op.execute("""
        ALTER TABLE staff_calendar_accounts
        ADD CONSTRAINT fk_staff_calendar_accounts_staff_id
        FOREIGN KEY (staff_id) REFERENCES staffs(id) ON DELETE CASCADE
    """)


def downgrade() -> None:
    op.execute('ALTER TABLE staff_calendar_accounts DROP CONSTRAINT IF EXISTS fk_staff_calendar_accounts_staff_id')
    op.execute('ALTER TABLE office_calendar_accounts DROP CONSTRAINT IF EXISTS fk_office_calendar_accounts_office_id')
