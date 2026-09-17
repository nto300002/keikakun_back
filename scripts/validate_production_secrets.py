"""Validate production secret values without exposing their contents."""

from __future__ import annotations

import os
import re
import sys
from urllib.parse import urlsplit


REQUIRED_PRODUCTION_SECRETS = (
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
)

_CONTROL_CHARACTER_PATTERN = re.compile(r"[\x00-\x1f\x7f]")


def validate_secret_values(values: dict[str, str | None]) -> list[str]:
    """Return safe, value-free validation errors for production secrets."""

    errors: list[str] = []
    for name in REQUIRED_PRODUCTION_SECRETS:
        value = values.get(name)
        if value is None or not value.strip():
            errors.append(f"{name}: empty")
            continue
        if _CONTROL_CHARACTER_PATTERN.search(value):
            errors.append(f"{name}: contains control characters")

    database_url = values.get("DATABASE_URL")
    if database_url and not _is_database_url(database_url):
        errors.append("DATABASE_URL: invalid URL scheme or host")

    stripe_secret_key = values.get("STRIPE_SECRET_KEY")
    if stripe_secret_key and not stripe_secret_key.startswith("sk_"):
        errors.append("STRIPE_SECRET_KEY: invalid prefix")

    webhook_secret = values.get("STRIPE_WEBHOOK_SECRET")
    if webhook_secret and not webhook_secret.startswith("whsec_"):
        errors.append("STRIPE_WEBHOOK_SECRET: invalid prefix")

    return errors


def _is_database_url(value: str) -> bool:
    parsed = urlsplit(value)
    return parsed.scheme.startswith("postgresql") and bool(parsed.hostname)


def main() -> int:
    errors = validate_secret_values(
        {name: os.environ.get(name) for name in REQUIRED_PRODUCTION_SECRETS}
    )
    if errors:
        for error in errors:
            print(f"FAIL secret value: {error}", file=sys.stderr)
        return 1

    print(
        "PASS secret values: "
        f"{len(REQUIRED_PRODUCTION_SECRETS)} required values validated"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
