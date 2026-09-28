"""Regression tests for the public 422 validation-error contract."""
import json
import logging

import pytest
from fastapi import Request
from fastapi.exceptions import RequestValidationError

from app.main import validation_exception_handler


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("location", "raw_input", "error_type", "ctx", "expected_code", "expected_message"),
    [
        (
            ("body", "profile", "password"),
            "password-value-must-not-appear",
            "string_too_short",
            {"min_length": 12},
            "validation.invalid_length",
            "入力文字数が正しくありません",
        ),
        (
            ("body", "token-value-must-not-appear"),
            "nested-input-value-must-not-appear",
            "value_error",
            {},
            "validation.invalid_value",
            "入力内容が正しくありません",
        ),
        (
            ("body", "contacts", 0, "email"),
            "person@example.invalid",
            "value_error",
            {"error": ValueError("person@example.invalid rejected")},
            "validation.invalid_value",
            "入力内容が正しくありません",
        ),
        (
            ("query", "token"),
            "query-token-value-must-not-appear",
            "string_pattern_mismatch",
            {"pattern": "safe-pattern"},
            "validation.invalid_format",
            "入力形式が正しくありません",
        ),
        (
            ("header", "authorization"),
            "header-credential-must-not-appear",
            "missing",
            {},
            "validation.required",
            "必須項目です",
        ),
        (
            ("path", "recipient_id"),
            "not-a-uuid-value",
            "uuid_parsing",
            {"error": "invalid UUID at /internal/path.py"},
            "validation.invalid_format",
            "入力形式が正しくありません",
        ),
        (
            ("body", "attachment"),
            "multipart-private-content-must-not-appear",
            "bytes_too_long",
            {"max_length": 10},
            "validation.invalid_length",
            "入力文字数が正しくありません",
        ),
    ],
)
async def test_validation_errors_expose_only_safe_allowlisted_fields(
    caplog,
    location,
    raw_input,
    error_type,
    ctx,
    expected_code,
    expected_message,
):
    """422 responses never echo user input or exception details."""
    request = Request({"type": "http", "method": "POST", "path": "/test", "headers": []})
    error = RequestValidationError(
        [
            {
                "type": error_type,
                "loc": location,
                "msg": "untrusted validation detail",
                "input": raw_input,
                "ctx": ctx,
            }
        ]
    )

    with caplog.at_level(logging.WARNING):
        response = await validation_exception_handler(request, error)

    body = response.body.decode()
    for sensitive_value in (raw_input, *location[1:]):
        assert str(sensitive_value) not in body
        assert str(sensitive_value) not in caplog.text
    assert "untrusted validation detail" not in body
    assert "internal/path.py" not in body

    assert response.status_code == 422
    assert json.loads(body) == {
        "detail": [
            {
                "loc": [location[0]],
                "code": expected_code,
                "message": expected_message,
            }
        ]
    }
