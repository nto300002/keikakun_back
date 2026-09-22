"""redact legacy audit log personal data

Revision ID: w7logmin230
Revises: w6passkey215
"""

from typing import Sequence, Union

from alembic import op


revision: str = "w7logmin230"
down_revision: Union[str, None] = "w6passkey215"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

REDACTED = "<redacted>"


def upgrade() -> None:
    """Remove legacy raw personal data; this operation is intentionally irreversible."""
    op.execute(
        """
        DO $$
        BEGIN
            IF to_regclass('password_reset_audit_logs') IS NOT NULL THEN
                UPDATE password_reset_audit_logs
                SET email = CASE WHEN email IS NULL THEN NULL ELSE '<redacted>' END,
                    ip_address = CASE WHEN ip_address IS NULL THEN NULL ELSE '<redacted>' END,
                    user_agent = CASE WHEN user_agent IS NULL THEN NULL ELSE '<redacted>' END,
                    error_message = CASE WHEN error_message IS NULL THEN NULL ELSE '<redacted>' END;
            END IF;

            IF to_regclass('audit_logs') IS NOT NULL THEN
                UPDATE audit_logs
                SET ip_address = CASE WHEN ip_address IS NULL THEN NULL ELSE '<redacted>' END,
                    user_agent = CASE WHEN user_agent IS NULL THEN NULL ELSE '<redacted>' END,
                    details = CASE
                        WHEN details IS NULL THEN NULL
                        ELSE '{"redacted_details": "<redacted>"}'::jsonb
                    END;
            END IF;

            IF to_regclass('office_audit_logs') IS NOT NULL THEN
                UPDATE office_audit_logs
                SET details = CASE
                    WHEN details IS NULL THEN NULL
                    ELSE '{"redacted_details": "<redacted>"}'
                END;
            END IF;
        END $$;
        """
    )


def downgrade() -> None:
    """Redacted personal data cannot be restored."""
    pass
