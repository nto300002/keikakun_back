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


def test_raw_request_data_and_tracebacks_are_not_logged_in_sensitive_paths():
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
