import pytest

from app.api.v1.endpoints import auths
from app.core.auth_cookie import (
    build_access_cookie_options,
    build_delete_access_cookie_options,
)


@pytest.fixture(autouse=True)
def clear_cookie_env(monkeypatch):
    monkeypatch.delenv("ENVIRONMENT", raising=False)
    monkeypatch.delenv("COOKIE_DOMAIN", raising=False)
    monkeypatch.delenv("COOKIE_SAMESITE", raising=False)


def test_build_access_cookie_options_for_local_defaults():
    options = build_access_cookie_options(value="token", max_age=3600)

    assert options == {
        "key": "access_token",
        "value": "token",
        "httponly": True,
        "secure": False,
        "max_age": 3600,
        "samesite": "lax",
    }


def test_build_access_cookie_options_for_production_defaults(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")

    options = build_access_cookie_options(value="token", max_age=3600)

    assert options["secure"] is True
    assert options["samesite"] == "none"
    assert "domain" not in options


def test_build_access_cookie_options_uses_valid_domain_and_samesite(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("COOKIE_DOMAIN", " .keikakun.com ")
    monkeypatch.setenv("COOKIE_SAMESITE", "Strict")

    options = build_access_cookie_options(value="token", max_age=3600)

    assert options["domain"] == ".keikakun.com"
    assert options["samesite"] == "strict"


@pytest.mark.parametrize(
    ("domain", "samesite"),
    [
        ("# .keikakun.com", "invalid"),
        ("日本語.example.com", "invalid"),
        ("   ", "invalid"),
    ],
)
def test_build_access_cookie_options_ignores_invalid_env_values(
    monkeypatch, domain, samesite
):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("COOKIE_DOMAIN", domain)
    monkeypatch.setenv("COOKIE_SAMESITE", samesite)

    options = build_access_cookie_options(value="token", max_age=3600)

    assert "domain" not in options
    assert options["samesite"] == "none"


def test_build_delete_cookie_options_matches_access_cookie_scope(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("COOKIE_DOMAIN", ".keikakun.com")

    options = build_delete_access_cookie_options()

    assert options == {
        "key": "access_token",
        "path": "/",
        "samesite": "none",
        "domain": ".keikakun.com",
    }


def test_auth_endpoint_uses_shared_cookie_option_builders():
    source_path = auths.__file__
    with open(source_path, encoding="utf-8") as source_file:
        source = source_file.read()

    assert source.count("build_access_cookie_options(") == 4
    assert source.count("build_delete_access_cookie_options(") == 1
    assert "COOKIE_DOMAIN" not in source
    assert "COOKIE_SAMESITE" not in source
    assert "cookie_options =" not in source
    assert "delete_cookie_options =" not in source
