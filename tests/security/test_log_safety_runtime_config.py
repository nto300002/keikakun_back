import pytest

from app.core.log_safety import validate_production_log_safety


def test_production_rejects_debug_true():
    with pytest.raises(ValueError, match="DEBUG"):
        validate_production_log_safety(
            {
                "ENVIRONMENT": "production",
                "DEBUG": "true",
                "LOG_LEVEL": "WARNING",
            }
        )


def test_production_rejects_debug_log_level():
    with pytest.raises(ValueError, match="LOG_LEVEL"):
        validate_production_log_safety(
            {
                "ENVIRONMENT": "production",
                "DEBUG": "false",
                "LOG_LEVEL": "DEBUG",
            }
        )


def test_production_rejects_body_dump_flags():
    with pytest.raises(ValueError, match="BODY"):
        validate_production_log_safety(
            {
                "ENVIRONMENT": "production",
                "DEBUG": "false",
                "LOG_LEVEL": "INFO",
                "LOG_REQUEST_BODY": "1",
            }
        )


def test_non_production_allows_local_debug_flags():
    validate_production_log_safety(
        {
            "ENVIRONMENT": "development",
            "DEBUG": "true",
            "LOG_LEVEL": "DEBUG",
            "LOG_REQUEST_BODY": "1",
        }
    )
