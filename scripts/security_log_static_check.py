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
        self.exception_derived_names: set[str] = set()

    def visit_Assign(self, node: ast.Assign) -> None:
        if _contains_exception_source(node.value, self.exception_derived_names):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    self.exception_derived_names.add(target.id)
        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        if (
            isinstance(node.target, ast.Name)
            and _contains_exception_source(node.value, self.exception_derived_names)
        ):
            self.exception_derived_names.add(node.target.id)
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        call_type = _get_sensitive_call_type(node)
        if call_type:
            call_source = ast.get_source_segment(self.source, node) or ""
            reason_terms = _sensitive_argument_terms(node)
            if call_type.startswith("logger.") and any(
                _contains_exception_source(argument, self.exception_derived_names)
                for argument in [*node.args, *(keyword.value for keyword in node.keywords)]
            ):
                reason_terms.append("indirect_exception_value")
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


def _contains_exception_source(
    node: ast.AST | None,
    exception_derived_names: set[str],
) -> bool:
    if node is None or _is_safe_expression(node):
        return False

    if isinstance(node, ast.Name):
        return node.id in exception_derived_names or node.id in {"e", "exc", "exception"}

    if isinstance(node, ast.Call):
        return any(_contains_exception_source(argument, exception_derived_names) for argument in node.args)

    if isinstance(node, ast.JoinedStr):
        return any(
            _contains_exception_source(value.value, exception_derived_names)
            for value in node.values
            if isinstance(value, ast.FormattedValue)
        )

    if isinstance(node, ast.Attribute):
        if node.attr in {"status_code", "code", "errno"}:
            return False
        return _contains_exception_source(node.value, exception_derived_names)

    if isinstance(node, (ast.Dict, ast.List, ast.Tuple, ast.Set)):
        return any(
            _contains_exception_source(child, exception_derived_names)
            for child in ast.iter_child_nodes(node)
        )

    return False


def _is_safe_expression(node: ast.AST) -> bool:
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
        return node.func.id in {"bool", "len", "mask_external_id", "sanitize_log_value", "redact"}
    if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Call):
        return (
            isinstance(node.value.func, ast.Name)
            and node.value.func.id == "type"
            and node.attr == "__name__"
        )
    return False


def _sensitive_argument_terms(node: ast.Call) -> list[str]:
    terms: set[str] = set()
    for argument in [*node.args, *(keyword.value for keyword in node.keywords)]:
        if _is_safe_expression(argument):
            continue
        for child in _iter_sensitive_name_nodes(argument):
            if not isinstance(child, ast.Name):
                continue
            normalized = child.id.lower()
            if normalized.startswith("has_") or normalized.endswith(("_count", "_present")):
                continue
            terms.update(term for term in SENSITIVE_TERMS if term in normalized)
    return sorted(terms)


def _iter_sensitive_name_nodes(node: ast.AST) -> Iterable[ast.AST]:
    if isinstance(node, ast.IfExp):
        yield from _iter_sensitive_name_nodes(node.body)
        yield from _iter_sensitive_name_nodes(node.orelse)
        return
    yield from ast.walk(node)


def _is_exception_string_conversion(node: ast.AST | None) -> bool:
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "str"
        and bool(node.args)
        and isinstance(node.args[0], ast.Name)
        and (
            node.args[0].id in {"e", "exc", "exception", "error"}
            or "exception" in node.args[0].id.lower()
        )
    )


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

    return found_terms


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
