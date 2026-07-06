from pathlib import Path

from scripts.security_log_static_check import main, scan_paths


def write_source(tmp_path: Path, content: str) -> Path:
    source_path = tmp_path / "sample.py"
    source_path.write_text(content, encoding="utf-8")
    return source_path


def test_static_check_detects_sensitive_logger_arguments(tmp_path):
    source_path = write_source(
        tmp_path,
        """
import logging
logger = logging.getLogger(__name__)

def run(token, stripe_customer_id):
    logger.error("failed token=%s stripe_customer_id=%s", token, stripe_customer_id)
""",
    )

    findings = scan_paths([source_path])

    assert len(findings) == 1
    assert findings[0].path == source_path
    assert "logger.error" in findings[0].source
    assert "token" in findings[0].reason
    assert "stripe_customer_id" in findings[0].reason


def test_static_check_detects_sensitive_print_arguments(tmp_path):
    source_path = write_source(
        tmp_path,
        """
def run(response_body):
    print("response body:", response_body)
""",
    )

    findings = scan_paths([source_path])

    assert len(findings) == 1
    assert "print" in findings[0].source
    assert "response" in findings[0].reason


def test_static_check_allows_safe_logging_patterns(tmp_path):
    source_path = write_source(
        tmp_path,
        """
import logging
logger = logging.getLogger(__name__)

def run(error, stripe_customer_id, payload, token):
    logger.error("failed error_type=%s", type(error).__name__)
    logger.info("stripe_customer_id_present=%s", bool(stripe_customer_id))
    logger.info("payload=%s", sanitize_log_value(payload))
    logger.info("token=%s", mask_external_id(token))
""",
    )

    findings = scan_paths([source_path])

    assert findings == []


def test_static_check_detects_sensitive_frontend_console_arguments(tmp_path):
    source_path = tmp_path / "sample.tsx"
    source_path.write_text(
        """
export function report(apiErr: unknown, responseBody: unknown) {
  console.error("request failed", apiErr, responseBody);
}
""",
        encoding="utf-8",
    )

    findings = scan_paths([source_path])

    assert len(findings) == 1
    assert findings[0].call_type == "console.error"
    assert "apierr" in findings[0].reason
    assert "response" in findings[0].reason


def test_static_check_block_mode_fails_when_findings_exist(tmp_path):
    source_path = write_source(
        tmp_path,
        """
def run(token):
    print("token", token)
""",
    )

    assert main(["--mode", "block", str(source_path)]) == 1


def test_static_check_allows_reasoned_unexpired_allowlist_entry(tmp_path):
    source_path = write_source(
        tmp_path,
        """
def run(token):
    print("token", token)
""",
    )
    allowlist_path = tmp_path / "allowlist.json"
    allowlist_path.write_text(
        f"""
[
  {{
    "path": "{source_path.name}",
    "call_type": "print",
    "reason": "legacy script triage",
    "owner": "security",
    "expires_on": "2099-01-01"
  }}
]
""",
        encoding="utf-8",
    )

    assert main(["--mode", "block", "--allowlist-file", str(allowlist_path), str(source_path)]) == 0


def test_static_check_rejects_expired_allowlist_entry(tmp_path):
    source_path = write_source(
        tmp_path,
        """
def run(token):
    print("token", token)
""",
    )
    allowlist_path = tmp_path / "allowlist.json"
    allowlist_path.write_text(
        f"""
[
  {{
    "path": "{source_path.name}",
    "call_type": "print",
    "reason": "expired exception",
    "owner": "security",
    "expires_on": "2000-01-01"
  }}
]
""",
        encoding="utf-8",
    )

    assert main(["--mode", "block", "--allowlist-file", str(allowlist_path), str(source_path)]) == 1
