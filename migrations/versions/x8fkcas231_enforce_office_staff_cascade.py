"""enforce cascade deletion for office_staffs office references

Revision ID: x8fkcas231
Revises: w7logmin230
Create Date: 2026-09-24
"""

from typing import Sequence, Union

from alembic import op


revision: str = "x8fkcas231"
down_revision: Union[str, None] = "w7logmin230"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Align the physical FK with the OfficeStaff model's CASCADE contract."""
    op.drop_constraint(
        "office_staffs_office_id_fkey", "office_staffs", type_="foreignkey"
    )
    op.create_foreign_key(
        "office_staffs_office_id_fkey",
        "office_staffs",
        "offices",
        ["office_id"],
        ["id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    """Restore the previous NO ACTION rule."""
    op.drop_constraint(
        "office_staffs_office_id_fkey", "office_staffs", type_="foreignkey"
    )
    op.create_foreign_key(
        "office_staffs_office_id_fkey",
        "office_staffs",
        "offices",
        ["office_id"],
        ["id"],
    )
