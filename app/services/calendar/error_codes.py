"""Calendar integration error codes safe to persist and return."""

from typing import Optional

CALENDAR_CONNECTION_FAILED = "calendar_connection_failed"
CALENDAR_SYNC_FAILED = "calendar_sync_failed"


def sanitize_calendar_error_code(value: object, *, default: str) -> Optional[str]:
    """Return an allowlisted code, preserving ``None`` as an unset value."""
    if value is None:
        return None
    return value if value in {CALENDAR_CONNECTION_FAILED, CALENDAR_SYNC_FAILED} else default
