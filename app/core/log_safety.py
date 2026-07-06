from __future__ import annotations

from collections.abc import Mapping


PRODUCTION_ENVIRONMENTS = {"production", "prod"}
TRUE_VALUES = {"1", "true", "yes", "on"}
DEBUG_LOG_LEVELS = {"DEBUG", "TRACE", "NOTSET"}
BODY_DUMP_FLAGS = {
    "LOG_REQUEST_BODY",
    "LOG_RESPONSE_BODY",
    "LOG_RAW_PAYLOAD",
    "DEBUG_BODY",
    "BODY_LOGGING_ENABLED",
}


def _env_value(env: Mapping[str, object], key: str, default: str = "") -> str:
    value = env.get(key, default)
    return str(value).strip()


def _is_truthy(value: str) -> bool:
    return value.lower() in TRUE_VALUES


def validate_production_log_safety(env: Mapping[str, object]) -> None:
    """
    Reject unsafe debug/body logging flags in production.

    This intentionally checks raw environment-like values so tests and startup
    validation can use the same rules before logging is configured.
    """

    environment = _env_value(env, "ENVIRONMENT", "development").lower()
    if environment not in PRODUCTION_ENVIRONMENTS:
        return

    if _is_truthy(_env_value(env, "DEBUG")):
        raise ValueError("DEBUG must not be enabled in production")

    log_level = _env_value(env, "LOG_LEVEL", "WARNING").upper()
    if log_level in DEBUG_LOG_LEVELS:
        raise ValueError("LOG_LEVEL must not be DEBUG/TRACE/NOTSET in production")

    enabled_body_flags = [
        flag for flag in sorted(BODY_DUMP_FLAGS)
        if _is_truthy(_env_value(env, flag))
    ]
    if enabled_body_flags:
        raise ValueError(
            "BODY logging flags must not be enabled in production: "
            + ", ".join(enabled_body_flags)
        )
