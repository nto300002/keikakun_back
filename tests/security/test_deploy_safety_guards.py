from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def read_app_source(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


def test_totp_values_are_not_logged():
    auth_source = read_app_source("app/api/v1/endpoints/auths.py")
    security_source = read_app_source("app/core/security.py")
    log_lines = [
        line
        for line in (auth_source + "\n" + security_source).splitlines()
        if "logger." in line
    ]

    forbidden_fragments = [
        "totp_code:",
        "Current valid code",
        "Original token",
        "Sanitized token",
        "Secret decrypted successfully",
    ]
    combined_log_source = "\n".join(log_lines)

    for fragment in forbidden_fragments:
        assert fragment not in combined_log_source


def test_raw_request_data_and_tracebacks_are_not_logged_in_refactor_paths():
    checked_paths = [
        "app/services/employee_action_service.py",
        "app/services/approval/employee_action_executor.py",
        "app/services/support_plan_service.py",
        "app/services/calendar/google_calendar_sync_service.py",
        "app/scheduler/calendar_sync_scheduler.py",
    ]

    for relative_path in checked_paths:
        source = read_app_source(relative_path)
        assert "Request data:" not in source
        assert "traceback.format_exc()" not in source


def test_production_cors_does_not_allow_preview_regex_or_bypass_header():
    source = read_app_source("app/main.py")
    production_block = source.split("if is_production:", 1)[1].split("else:", 1)[0]

    assert "allow_origin_regex" not in production_block
    assert "x-vercel-protection-bypass" not in production_block
    assert "X-Requested-With" not in production_block


def test_cookie_authenticated_state_changes_use_csrf_middleware():
    source = read_app_source("app/main.py")

    assert "csrf_cookie_auth_middleware" in source
    assert 'request.method in {"POST", "PUT", "PATCH", "DELETE"}' in source
    assert 'request.cookies.get("access_token")' in source
    assert "CsrfProtect().validate_csrf(request)" in source
    assert '"/api/v1/billing/webhook"' in source


def test_jwt_and_mfa_encryption_do_not_use_known_production_fallbacks():
    security_source = read_app_source("app/core/security.py")
    auth_source = read_app_source("app/api/v1/endpoints/auths.py")

    assert 'os.getenv("SECRET_KEY", "test_secret_key_for_pytest")' not in security_source
    assert 'os.getenv("SECRET_KEY", "test_secret_key_for_pytest")' not in auth_source
    assert 'os.getenv("ENCRYPTION_KEY", os.getenv("SECRET_KEY", "test_secret_key_for_pytest"))' not in security_source
    assert "get_jwt_secret()" in security_source
    assert "get_mfa_encryption_key_source()" in security_source


def test_app_adds_security_headers_in_frontend_and_backend():
    backend_source = read_app_source("app/main.py")

    required_headers = [
        "Content-Security-Policy",
        "X-Content-Type-Options",
        "Referrer-Policy",
        "Strict-Transport-Security",
        "Permissions-Policy",
    ]

    assert "security_headers_middleware" in backend_source
    for header in required_headers:
        assert header in backend_source


def test_pdf_upload_validation_has_server_side_size_and_magic_byte_checks():
    source = read_app_source("app/api/v1/endpoints/support_plans.py")

    assert "MAX_PDF_UPLOAD_BYTES" in source
    assert "validate_pdf_upload" in source
    assert "len(file_content) > MAX_PDF_UPLOAD_BYTES" in source
    assert 'file_content.startswith(b"%PDF-")' in source


def test_google_service_account_json_validation_limits_sensitive_payloads():
    source = read_app_source("app/schemas/calendar_account.py")

    assert "MAX_SERVICE_ACCOUNT_JSON_BYTES" in source
    assert "SERVICE_ACCOUNT_PRIVATE_KEY_PATTERN" in source
    assert "SERVICE_ACCOUNT_EMAIL_PATTERN" in source
    assert "len(v.encode(\"utf-8\")) > MAX_SERVICE_ACCOUNT_JSON_BYTES" in source
    assert "VALIDATION_INVALID_JSON_FORMAT.format(error=str(e))" not in source
