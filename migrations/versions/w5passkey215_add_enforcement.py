"""add app_admin passkey enforcement state"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "w5passkey215"
down_revision: Union[str, None] = "w4bauthn213"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "staffs",
        sa.Column("passkey_enforced_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "webauthn_authentication_sessions",
        sa.Column("purpose", sa.String(length=20), server_default="login", nullable=False),
    )
    op.drop_constraint(
        "ck_webauthn_challenges_ceremony", "webauthn_challenges", type_="check"
    )
    op.create_check_constraint(
        "ck_webauthn_challenges_ceremony",
        "webauthn_challenges",
        "ceremony IN ('registration', 'authentication', 'step_up')",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_webauthn_challenges_ceremony", "webauthn_challenges", type_="check"
    )
    op.create_check_constraint(
        "ck_webauthn_challenges_ceremony",
        "webauthn_challenges",
        "ceremony IN ('registration', 'authentication')",
    )
    op.drop_column("webauthn_authentication_sessions", "purpose")
    op.drop_column("staffs", "passkey_enforced_at")
