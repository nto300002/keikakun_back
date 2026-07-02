import os
from typing import Any


ACCESS_COOKIE_KEY = "access_token"
VALID_SAMESITE_VALUES = {"none", "lax", "strict"}


def _is_production() -> bool:
    return os.getenv("ENVIRONMENT") == "production"


def _normalize_cookie_domain(raw_domain: str | None) -> str | None:
    if not raw_domain:
        return None

    domain = raw_domain.strip()
    if not domain or domain.startswith("#"):
        return None

    try:
        domain.encode("latin-1")
    except UnicodeEncodeError:
        return None

    return domain


def _normalize_samesite(raw_samesite: str | None) -> str | None:
    if not raw_samesite:
        return None

    samesite = raw_samesite.strip().lower()
    if samesite not in VALID_SAMESITE_VALUES:
        return None

    return samesite


def _resolve_samesite() -> str:
    configured_samesite = _normalize_samesite(os.getenv("COOKIE_SAMESITE"))
    if configured_samesite:
        return configured_samesite

    return "none" if _is_production() else "lax"


def _cookie_domain_option() -> dict[str, str]:
    domain = _normalize_cookie_domain(os.getenv("COOKIE_DOMAIN"))
    if not domain:
        return {}
    return {"domain": domain}


def build_access_cookie_options(value: str, max_age: int) -> dict[str, Any]:
    options: dict[str, Any] = {
        "key": ACCESS_COOKIE_KEY,
        "value": value,
        "httponly": True,
        "secure": _is_production(),
        "max_age": max_age,
        "samesite": _resolve_samesite(),
    }
    options.update(_cookie_domain_option())
    return options


def build_delete_access_cookie_options() -> dict[str, Any]:
    options: dict[str, Any] = {
        "key": ACCESS_COOKIE_KEY,
        "path": "/",
        "samesite": _resolve_samesite(),
    }
    options.update(_cookie_domain_option())
    return options
