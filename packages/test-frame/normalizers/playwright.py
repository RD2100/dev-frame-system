# -*- coding: utf-8 -*-
"""Playwright JSON normalizer: raw Playwright JSON report -> CanonicalTestResult."""

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from schema.canonical import CanonicalTestResult, Summary, ToolStats
from normalizers.base import (
    _utc_now,
    _generate_result_id,
    _build_tool_info,
    _build_suite_info,
    _empty_summary,
    _empty_tool_stats,
)


# ---- Playwright status mapping ----

_PW_STATUS_MAP = {
    "passed": "passed",
    "failed": "failed",
    "skipped": "skipped",
    "timedOut": "error",
    "interrupted": "cancelled",
}


def _map_pw_status(pw_status: str) -> str:
    return _PW_STATUS_MAP.get(pw_status, "error")


# ---- Count helpers ----

def _counts_from_pw(data: dict) -> dict:
    """Extract test counts from Playwright JSON stats."""
    stats = data.get("stats", {})
    expected = stats.get("expected", 0)
    unexpected = stats.get("unexpected", 0)
    skipped = stats.get("skipped", 0)
    flaky = stats.get("flaky", 0)

    total = sum(1
        for suite in data.get("suites", [])
        for spec in suite.get("specs", [])
        for test in spec.get("tests", [])
        for _ in test.get("results", [])
    )

    if total == 0 and (expected + unexpected + skipped) > 0:
        total = expected + unexpected + skipped

    passed = expected - flaky if flaky < expected else expected

    failed_count = 0
    error_count = 0
    cancelled_count = 0

    for suite in data.get("suites", []):
        for spec in suite.get("specs", []):
            for test in spec.get("tests", []):
                for tr in test.get("results", []):
                    s = _map_pw_status(tr.get("status", ""))
                    if s == "failed":
                        failed_count += 1
                    elif s == "error":
                        error_count += 1
                    elif s == "cancelled":
                        cancelled_count += 1

    if failed_count + error_count + cancelled_count == 0 and unexpected > 0:
        failed_count = unexpected

    return {
        "total": total,
        "passed": passed,
        "failed": failed_count,
        "skipped": skipped,
        "error": error_count,
        "blocked": 0,
        "cancelled": cancelled_count,
        "duration_ms": stats.get("duration", 0),
    }


# ---- Test case building ----

def _build_tests_from_pw(data: dict, context: dict) -> list[dict[str, Any]]:
    """Build normalized test cases from Playwright JSON suites."""
    tests: list[dict[str, Any]] = []
    idx = 0

    for suite in data.get("suites", []):
        suite_title = suite.get("title", "")
        for spec in suite.get("specs", []):
            spec_title = spec.get("title", "")
            spec_file = spec.get("file", spec_title)
            for test in spec.get("tests", []):
                test_title = test.get("title", "unknown")
                test_line = test.get("line")
                # Playwright can have multiple results per test (retries)
                for tr in test.get("results", []):
                    idx += 1
                    pw_status = tr.get("status", "unknown")
                    canonical_status = _map_pw_status(pw_status)
                    error_info = tr.get("error") or {}
                    tests.append({
                        "test_id": f"{context['tool_name']}-{idx:04d}",
                        "name": test_title,
                        "full_name": f"{spec_title} > {test_title}",
                        "file": spec_file,
                        "line": test_line,
                        "status": canonical_status,
                        "raw_status": pw_status,
                        "duration_ms": int(tr.get("duration", 0)),
                        "started_at": tr.get("startTime"),
                        "ended_at": None,
                        "attempt": tr.get("retry", 0) + 1,
                        "retry": tr.get("retry", 0),
                        "tags": [],
                        "message": error_info.get("message") if isinstance(error_info, dict) else str(error_info) if error_info else None,
                        "trace": error_info.get("stack") if isinstance(error_info, dict) else None,
                        "evidence_refs": [],
                    })

    return tests


# ---- Error building ----

def _build_errors_from_pw(data: dict, context: dict) -> list[dict[str, Any]]:
    """Build errors from Playwright test failures and global errors."""
    errors: list[dict[str, Any]] = []
    tool_name = context["tool_name"]
    stage = context.get("stage", "unknown")

    for suite in data.get("suites", []):
        for spec in suite.get("specs", []):
            for test in spec.get("tests", []):
                for tr in test.get("results", []):
                    pw_status = tr.get("status", "")
                    canonical_status = _map_pw_status(pw_status)
                    error_info = tr.get("error") or {}

                    if canonical_status == "failed":
                        errors.append({
                            "error_id": f"err-{uuid.uuid4().hex[:8]}",
                            "type": "TEST_ASSERTION_FAILED",
                            "severity": "error",
                            "message": error_info.get("message") if isinstance(error_info, dict) else str(error_info),
                            "tool": tool_name,
                            "stage": stage,
                            "test_id": test.get("title"),
                            "retryable": False,
                            "raw_status": pw_status,
                            "raw_ref": None,
                        })
                    elif canonical_status == "error":
                        errors.append({
                            "error_id": f"err-{uuid.uuid4().hex[:8]}",
                            "type": "TOOL_TIMEOUT",
                            "severity": "error",
                            "message": f'Test timed out: {test.get("title", "unknown")}',
                            "tool": tool_name,
                            "stage": stage,
                            "test_id": test.get("title"),
                            "retryable": True,
                            "raw_status": pw_status,
                            "raw_ref": None,
                        })

    # Global errors (suite-level errors, e.g., config issues)
    for err in data.get("errors", []):
        if isinstance(err, dict):
            errors.append({
                "error_id": f"err-{uuid.uuid4().hex[:8]}",
                "type": "PARSE_ERROR",
                "severity": "error",
                "message": err.get("message", "Unknown suite error"),
                "tool": tool_name,
                "stage": stage,
                "test_id": None,
                "retryable": False,
                "raw_status": None,
                "raw_ref": None,
            })

    return errors


# ---- Main normalizer ----

def normalize_playwright_json(
    payload: dict | Path | str,
    context: dict,
) -> CanonicalTestResult:
    """Convert a raw Playwright JSON report to CanonicalTestResult.

    Args:
        payload: Parsed Playwright JSON dict, or a Path to the report file.
        context: NormalizeContext with run_id, stage, tool_name, etc.

    Returns:
        A CanonicalTestResult with full test case details.
    """
    tool_name = context["tool_name"]
    stage = context.get("stage", "unknown")

    # Load payload if it is a path
    if isinstance(payload, (str, Path)):
        path = Path(payload)
        if path.exists():
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        else:
            from normalizers.base import make_error_result
            return make_error_result(
                context=context,
                error_type="PARSE_ERROR",
                message=f"Playwright report not found: {path}",
            )
    else:
        data = payload

    now = _utc_now()

    # Derive overall status
    counts = _counts_from_pw(data)
    if counts["cancelled"] > 0:
        status = "cancelled"
    elif counts["failed"] > 0:
        status = "failed"
    elif counts["error"] > 0:
        status = "error"
    elif counts["passed"] > 0:
        status = "passed"
    elif counts["skipped"] > 0 and counts["total"] == counts["skipped"]:
        status = "skipped"
    else:
        status = "failed"

    executed = counts["passed"] + counts["failed"] + counts["error"]
    test_pass_rate = (counts["passed"] / executed * 100) if executed > 0 else None

    summary = Summary(
        total=counts["total"],
        passed=counts["passed"],
        failed=counts["failed"],
        skipped=counts["skipped"],
        error=counts["error"],
        blocked=0,
        cancelled=counts["cancelled"],
        test_pass_rate=test_pass_rate,
        test_pass_rate_basis="executed_tests",
        duration_ms=counts["duration_ms"],
    )

    tool_stats = {
        tool_name: ToolStats(
            status=status,
            total=counts["total"],
            passed=counts["passed"],
            failed=counts["failed"],
            skipped=counts["skipped"],
            error=counts["error"],
            blocked=0,
            cancelled=counts["cancelled"],
            duration_ms=counts["duration_ms"],
        )
    }

    tests = _build_tests_from_pw(data, context)
    errors = _build_errors_from_pw(data, context)

    return CanonicalTestResult(
        schema_version="test-frame.canonical.v1",
        result_id=_generate_result_id(stage, tool_name),
        run_id=context.get("run_id", "unknown"),
        stage=stage,
        tool=_build_tool_info(context),
        suite=_build_suite_info(context, status, now, now),
        status=status,
        summary=summary,
        tool_stats=tool_stats,
        tests=tests,
        signals=[],
        issues=[],
        quality={},
        errors=errors,
        evidence=[],
        environment=context.get("environment", {}),
        source={
            "type": "playwright_json",
            "path": str(payload) if isinstance(payload, (str, Path)) else None,
        },
        metadata={"normalizer": "playwright_json_v1"},
    )
