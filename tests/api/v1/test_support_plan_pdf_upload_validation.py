import pytest
from fastapi import HTTPException

from app.api.v1.endpoints.support_plans import (
    get_original_pdf_filename,
    sanitize_pdf_filename,
    validate_pdf_upload,
)


def test_sanitize_pdf_filename_keeps_safe_pdf_extension_for_japanese_name():
    assert sanitize_pdf_filename("画面遷移要件.pdf") == "file.pdf"


def test_get_original_pdf_filename_keeps_japanese_display_name():
    assert get_original_pdf_filename("画面遷移要件.pdf") == "画面遷移要件.pdf"


def test_validate_pdf_upload_accepts_japanese_pdf_filename():
    try:
        validate_pdf_upload(
            b"%PDF-1.7\n%%EOF",
            "画面遷移要件.pdf",
            "application/pdf",
        )
    except HTTPException as exc:
        pytest.fail(f"valid Japanese PDF filename was rejected: {exc.detail}")
