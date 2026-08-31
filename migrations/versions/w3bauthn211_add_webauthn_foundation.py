"""add WebAuthn credential and challenge foundation

Revision ID: w3bauthn211
Revises: c171deadlinecal
Create Date: 2026-08-26 12:00:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "w3bauthn211"
down_revision: Union[str, None] = "c171deadlinecal"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "webauthn_credentials",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("staff_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("credential_id", sa.LargeBinary(), nullable=False),
        sa.Column("public_key", sa.LargeBinary(), nullable=False),
        sa.Column("sign_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("transports", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("aaguid", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("backup_eligible", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("backup_state", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("display_name", sa.String(length=100), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["staff_id"], ["staffs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("credential_id"),
    )
    op.create_index("ix_webauthn_credentials_staff_id", "webauthn_credentials", ["staff_id"])
    op.create_index("ix_webauthn_credentials_revoked_at", "webauthn_credentials", ["revoked_at"])

    op.create_table(
        "webauthn_challenges",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("staff_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("ceremony", sa.String(length=20), nullable=False),
        sa.Column("challenge_hash", sa.String(length=64), nullable=False),
        sa.Column("session_id_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["staff_id"], ["staffs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "ceremony IN ('registration', 'authentication')",
            name="ck_webauthn_challenges_ceremony",
        ),
        sa.UniqueConstraint("challenge_hash", name="uq_webauthn_challenges_challenge_hash"),
    )
    op.create_index("ix_webauthn_challenges_staff_id", "webauthn_challenges", ["staff_id"])
    op.create_index("ix_webauthn_challenges_ceremony", "webauthn_challenges", ["ceremony"])
    op.create_index("ix_webauthn_challenges_session_id_hash", "webauthn_challenges", ["session_id_hash"])
    op.create_index("ix_webauthn_challenges_expires_at", "webauthn_challenges", ["expires_at"])
    op.create_index("ix_webauthn_challenges_used_at", "webauthn_challenges", ["used_at"])


def downgrade() -> None:
    op.drop_table("webauthn_challenges")
    op.drop_table("webauthn_credentials")
