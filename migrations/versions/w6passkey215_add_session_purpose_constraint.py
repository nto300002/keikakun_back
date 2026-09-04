"""constrain WebAuthn authentication session purposes"""

from typing import Sequence, Union

from alembic import op


revision: str = "w6passkey215"
down_revision: Union[str, None] = "w5passkey215"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_check_constraint(
        "ck_webauthn_auth_sessions_purpose",
        "webauthn_authentication_sessions",
        "purpose IN ('login', 'step_up')",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_webauthn_auth_sessions_purpose",
        "webauthn_authentication_sessions",
        type_="check",
    )
