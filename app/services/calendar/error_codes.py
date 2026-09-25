"""Calendar integration error codes safe to persist and return."""

CALENDAR_CONNECTION_FAILED = "calendar_connection_failed"
CALENDAR_SYNC_FAILED = "calendar_sync_failed"


def sanitize_calendar_error_code(value: object, *, default: str) -> str:
    """Return a known code instead of an exception message or external payload."""
    return value if value in {CALENDAR_CONNECTION_FAILED, CALENDAR_SYNC_FAILED} else default
