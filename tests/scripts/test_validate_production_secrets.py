import base64

import pytest

from scripts.validate_production_secrets import (
    REQUIRED_PRODUCTION_SECRETS,
    validate_secret_values,
)


def _valid_values() -> dict[str, str]:
    return {
        name: f"configured-{name.lower()}"
        for name in REQUIRED_PRODUCTION_SECRETS
    }


def test_all_production_secret_names_are_checked():
    assert set(REQUIRED_PRODUCTION_SECRETS) == {
        "DATABASE_URL",
        "SECRET_KEY",
        "ENCRYPTION_KEY",
        "AWS_ACCESS_KEY_ID",
        "AWS_SECRET_ACCESS_KEY",
        "S3_ACCESS_KEY",
        "S3_SECRET_KEY",
        "MAIL_USERNAME",
        "MAIL_PASSWORD",
        "STRIPE_SECRET_KEY",
        "STRIPE_WEBHOOK_SECRET",
        "VAPID_PRIVATE_KEY",
        "CALENDAR_ENCRYPTION_KEY",
    }


def test_valid_production_secret_values_pass():
    values = _valid_values()
    values["DATABASE_URL"] = "postgresql+psycopg://user:password@example.com/app"
    values["STRIPE_SECRET_KEY"] = "sk_live_example"
    values["STRIPE_WEBHOOK_SECRET"] = "whsec_example"

    assert validate_secret_values(values) == []


@pytest.mark.parametrize("secret_name", list(REQUIRED_PRODUCTION_SECRETS))
def test_missing_or_empty_secret_is_rejected(secret_name):
    values = _valid_values()
    values[secret_name] = ""

    errors = validate_secret_values(values)

    assert secret_name in errors[0]
    assert "empty" in errors[0]


def test_database_url_and_webhook_have_safe_shape_checks():
    values = _valid_values()
    values["DATABASE_URL"] = "not-a-database-url"
    values["STRIPE_WEBHOOK_SECRET"] = "not-a-webhook-secret"

    errors = validate_secret_values(values)

    assert any("DATABASE_URL" in error for error in errors)
    assert any("STRIPE_WEBHOOK_SECRET" in error for error in errors)


def test_secret_values_are_never_in_validation_errors():
    values = _valid_values()
    sensitive_value = base64.b64encode(b"sensitive-value").decode()
    values["SECRET_KEY"] = sensitive_value
    values["DATABASE_URL"] = ""

    errors = validate_secret_values(values)

    assert all(sensitive_value not in error for error in errors)
