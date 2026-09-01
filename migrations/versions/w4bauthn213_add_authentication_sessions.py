"""add WebAuthn authentication sessions

Revision ID: w4bauthn213
Revises: w3bauthn211
Create Date: 2026-09-01 12:00:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "w4bauthn213"
down_revision: Union[str, None] = "w3bauthn211"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "webauthn_authentication_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("staff_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["staff_id"], ["staffs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash"),
    )
    op.create_index("ix_webauthn_authentication_sessions_staff_id", "webauthn_authentication_sessions", ["staff_id"])


def downgrade() -> None:
    op.drop_index("ix_webauthn_authentication_sessions_staff_id", table_name="webauthn_authentication_sessions")
    op.drop_table("webauthn_authentication_sessions")
