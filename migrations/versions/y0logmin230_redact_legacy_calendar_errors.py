"""redact legacy calendar error messages

Revision ID: y0logmin230
Revises: x8fkcas231
"""

from typing import Sequence, Union

from alembic import op


revision: str = "y0logmin230"
down_revision: Union[str, None] = "x8fkcas231"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Replace persisted exception text with fixed, non-sensitive error codes."""
    op.execute(
        """
        DO $$
        BEGIN
            IF to_regclass('office_calendar_accounts') IS NOT NULL THEN
                UPDATE office_calendar_accounts
                SET last_error_message = 'calendar_connection_failed'
                WHERE last_error_message IS NOT NULL;
            END IF;

            IF to_regclass('calendar_events') IS NOT NULL THEN
                UPDATE calendar_events
                SET last_error_message = 'calendar_sync_failed'
                WHERE last_error_message IS NOT NULL;
            END IF;

            IF to_regclass('calendar_event_instances') IS NOT NULL THEN
                UPDATE calendar_event_instances
                SET last_error_message = 'calendar_sync_failed'
                WHERE last_error_message IS NOT NULL;
            END IF;
        END $$;
        """
    )


def downgrade() -> None:
    """Redacted error messages cannot be restored."""
    pass
