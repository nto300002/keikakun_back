#!/usr/bin/env python3
"""
Sensitive log static checker.

Default mode is warning-only so existing findings can be triaged before the
check is made blocking in CI.
"""
from __future__ import annotations

import argparse
import ast
import json
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Iterable, Sequence


SENSITIVE_TERMS = {
    "token",
    "secret",
    "password",
    "payload",
    "request_data",
    "response",
    "response_body",
    "body",
    "cookie",
    "apierr",
    "stripe_customer_id",
    "stripe_subscription_id",
}

SAFE_MARKERS = {
    "_present",
    "_count",
    "has_",
    "error_type",
    "type(",
    ".__name__",
    "mask_",
    "sanitize_",
    "redact",
    "bool(",
}

LOGGER_METHODS = {"debug", "info", "warning", "error", "exception", "critical"}
CONSOLE_METHODS = {"log", "debug", "warn", "error"}
DEFAULT_SCAN_PATHS = (Path("app"), Path("scripts"))
NON_PYTHON_SUFFIXES = {".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs"}


@dataclass(frozen=True)
class Finding:
    path: Path
    line: int
    column: int
    call_type: str
    reason: str
    source: str


@dataclass(frozen=True)
class AllowlistEntry:
    path: str
    call_type: str
    reason: str
    owner: str
    expires_on: date

    def matches(self, finding: Finding) -> bool:
        finding_path = str(finding.path)
        return (
            (finding_path == self.path or finding_path.endswith(self.path))
            and finding.call_type == self.call_type
            and self.expires_on >= date.today()
            and bool(self.reason.strip())
            and bool(self.owner.strip())
        )


def scan_paths(paths: Sequence[Path], allowlist: Sequence[AllowlistEntry] | None = None) -> list[Finding]:
    findings: list[Finding] = []
    for path in _iter_python_files(paths):
        findings.extend(scan_file(path))
    return _apply_allowlist(findings, allowlist or [])


def scan_file(path: Path) -> list[Finding]:
    try:
        source = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        source = path.read_text(encoding="utf-8", errors="ignore")

    if path.suffix == ".py":
        tree = ast.parse(source, filename=str(path))
        visitor = _SensitiveLogVisitor(path=path, source=source)
        visitor.visit(tree)
        return visitor.findings

    if path.suffix in NON_PYTHON_SUFFIXES:
        return _scan_non_python_file(path=path, source=source)

    return []


def _iter_python_files(paths: Sequence[Path]) -> Iterable[Path]:
    for path in paths:
        if path.is_file() and (path.suffix == ".py" or path.suffix in NON_PYTHON_SUFFIXES):
            yield path
        elif path.is_dir():
            for suffix in [".py", *sorted(NON_PYTHON_SUFFIXES)]:
                yield from sorted(path.rglob(f"*{suffix}"))


def _scan_non_python_file(*, path: Path, source: str) -> list[Finding]:
    findings: list[Finding] = []
    console_pattern = re.compile(r"\bconsole\.(log|debug|warn|error)\s*\(")

    for line_number, line in enumerate(source.splitlines(), start=1):
        match = console_pattern.search(line)
        if not match:
            continue

        reason_terms = _unsafe_sensitive_terms(line)
        if not reason_terms:
            continue

        findings.append(
            Finding(
                path=path,
                line=line_number,
                column=match.start(),
                call_type=f"console.{match.group(1)}",
                reason=", ".join(reason_terms),
                source=line.strip(),
            )
        )

    return findings


class _SensitiveLogVisitor(ast.NodeVisitor):
    def __init__(self, *, path: Path, source: str) -> None:
        self.path = path
        self.source = source
        self.findings: list[Finding] = []

    def visit_Call(self, node: ast.Call) -> None:
        call_type = _get_sensitive_call_type(node)
        if call_type:
            call_source = ast.get_source_segment(self.source, node) or ""
            reason_terms = _unsafe_sensitive_terms(call_source)
            if reason_terms:
                self.findings.append(
                    Finding(
                        path=self.path,
                        line=node.lineno,
                        column=node.col_offset,
                        call_type=call_type,
                        reason=", ".join(reason_terms),
                        source=call_source.strip(),
                    )
                )

        self.generic_visit(node)


def _get_sensitive_call_type(node: ast.Call) -> str | None:
    if isinstance(node.func, ast.Name) and node.func.id == "print":
        return "print"

    if isinstance(node.func, ast.Attribute) and node.func.attr in LOGGER_METHODS:
        return f"logger.{node.func.attr}"

    return None


def _unsafe_sensitive_terms(call_source: str) -> list[str]:
    normalized = call_source.lower()
    found_terms = sorted(term for term in SENSITIVE_TERMS if term in normalized)
    if not found_terms:
        return []

    if _is_safe_log_call(normalized):
        return []

    return found_terms


def _is_safe_log_call(normalized_call_source: str) -> bool:
    return any(marker in normalized_call_source for marker in SAFE_MARKERS)


def _format_findings(findings: Sequence[Finding]) -> str:
    lines = []
    for finding in findings:
        lines.append(
            f"{finding.path}:{finding.line}:{finding.column}: "
            f"{finding.call_type}: sensitive log terms [{finding.reason}]"
        )
        lines.append(f"  {finding.source}")
    return "\n".join(lines)


def _apply_allowlist(
    findings: Sequence[Finding],
    allowlist: Sequence[AllowlistEntry],
) -> list[Finding]:
    if not allowlist:
        return list(findings)

    return [
        finding
        for finding in findings
        if not any(entry.matches(finding) for entry in allowlist)
    ]


def load_allowlist(path: Path | None) -> list[AllowlistEntry]:
    if path is None:
        return []

    raw_entries = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw_entries, list):
        raise ValueError("allowlist file must contain a JSON array")

    entries: list[AllowlistEntry] = []
    for raw_entry in raw_entries:
        if not isinstance(raw_entry, dict):
            raise ValueError("allowlist entries must be JSON objects")

        try:
            entry = AllowlistEntry(
                path=str(raw_entry["path"]),
                call_type=str(raw_entry["call_type"]),
                reason=str(raw_entry["reason"]),
                owner=str(raw_entry["owner"]),
                expires_on=date.fromisoformat(str(raw_entry["expires_on"])),
            )
        except KeyError as exc:
            raise ValueError(f"allowlist entry missing required key: {exc.args[0]}") from exc

        entries.append(entry)

    return entries


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "paths",
        nargs="*",
        type=Path,
        default=list(DEFAULT_SCAN_PATHS),
        help="Files or directories to scan. Defaults to app scripts.",
    )
    parser.add_argument(
        "--mode",
        choices=("warn", "block"),
        default="warn",
        help="warn exits 0 with findings; block exits 1 when findings exist.",
    )
    parser.add_argument(
        "--allowlist-file",
        type=Path,
        default=None,
        help="JSON allowlist with path, call_type, reason, owner, expires_on.",
    )
    args = parser.parse_args(argv)

    allowlist = load_allowlist(args.allowlist_file)
    findings = scan_paths(args.paths, allowlist=allowlist)
    if findings:
        print(_format_findings(findings))

    if args.mode == "block" and findings:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
