"""add_sequential_numbering

Revision ID: c6r6a2uqmvic
Revises: byddyrpnnpk5
Create Date: 2025-10-21 00:00:03

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c6r6a2uqmvic'
down_revision: Union[str, None] = 'byddyrpnnpk5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # support_plan_cycles テーブル
    op.execute("CREATE SEQUENCE IF NOT EXISTS support_plan_cycles_id_seq")
    op.execute("ALTER TABLE support_plan_cycles ALTER COLUMN id SET DEFAULT nextval('support_plan_cycles_id_seq')")
    op.execute("SELECT setval('support_plan_cycles_id_seq', COALESCE((SELECT MAX(id) FROM support_plan_cycles), 1), false)")

    # support_plan_statuses テーブル
    op.execute("CREATE SEQUENCE IF NOT EXISTS support_plan_statuses_id_seq")
    op.execute("ALTER TABLE support_plan_statuses ALTER COLUMN id SET DEFAULT nextval('support_plan_statuses_id_seq')")
    op.execute("SELECT setval('support_plan_statuses_id_seq', COALESCE((SELECT MAX(id) FROM support_plan_statuses), 1), false)")

    # plan_deliverables テーブル
    op.execute("CREATE SEQUENCE IF NOT EXISTS plan_deliverables_id_seq")
    op.execute("ALTER TABLE plan_deliverables ALTER COLUMN id SET DEFAULT nextval('plan_deliverables_id_seq')")
    op.execute("SELECT setval('plan_deliverables_id_seq', COALESCE((SELECT MAX(id) FROM plan_deliverables), 1), false)")


def downgrade() -> None:
    op.execute("ALTER TABLE plan_deliverables ALTER COLUMN id DROP DEFAULT")
    op.execute("DROP SEQUENCE IF EXISTS plan_deliverables_id_seq")

    op.execute("ALTER TABLE support_plan_statuses ALTER COLUMN id DROP DEFAULT")
    op.execute("DROP SEQUENCE IF EXISTS support_plan_statuses_id_seq")

    op.execute("ALTER TABLE support_plan_cycles ALTER COLUMN id DROP DEFAULT")
    op.execute("DROP SEQUENCE IF EXISTS support_plan_cycles_id_seq")
