# -*- coding: utf-8 -*-
"""Wrapper-dict normalizer: converts legacy wrapper dicts to CanonicalTestResult.

Handles two wrapper conventions:
  1. New style (status key):  {"status": "passed", "tool": "xxx", ...}
  2. Old style (booleans):    {"passed": True, "tool": "xxx", "skipped": False, ...}
"""

import uuid
from datetime import datetime, timezone
from typing import Any

from orchestrator.stage import _derive_status, STATUS_PASSED, STATUS_FAILED, STATUS_SKIPPED, STATUS_BLOCKED, STATUS_ERROR, STATUS_CANCELLED
from schema.canonical import (
    CanonicalTestResult,
    ToolInfo,
    SuiteInfo,
    Summary,
    ToolStats,
)
from normalizers.base import (
    _utc_now,
    _generate_result_id,
    _build_tool_info,
    _build_suite_info,
    _empty_summary,
    _empty_tool_stats,
)


# ---- count helpers ----

def _count_summary(wrapper: dict, status: str) -> Summary:
    """Derive summary counts from wrapper dict and derived status.

    For wrappers that provide a 'results' list, counts are extracted from it.
    For wrappers that only provide status/reason, a single unit count is used.
    """
    total = wrapper.get("total", 0)
    results = wrapper.get("results", [])

    if results:
        passed = sum(1 for r in results if r.get("status", r.get("passed", False)) in ("passed", True))
        failed = sum(1 for r in results if r.get("status", r.get("passed", True)) in ("failed", False))
        skipped = sum(1 for r in results if r.get("status") == "skipped" or r.get("skipped"))
        total = len(results)
        error = 0
        blocked = 0
        cancelled = 0
    else:
        # Single-unit count based on derived status
        passed = 1 if status == "passed" else 0
        failed = 1 if status == "failed" else 0
        skipped = 1 if status == "skipped" else 0
        error = 1 if status == "error" else 0
        blocked = 1 if status == "blocked" else 0
        cancelled = 1 if status == "cancelled" else 0
        if total == 0:
            total = passed + failed + skipped + error + blocked + cancelled

    executed = passed + failed + error
    test_pass_rate = (passed / executed * 100) if executed > 0 else None

    return Summary(
        total=total,
        passed=passed,
        failed=failed,
        skipped=skipped,
        error=error,
        blocked=blocked,
        cancelled=cancelled,
        test_pass_rate=test_pass_rate,
        test_pass_rate_basis="executed_tests",
        duration_ms=wrapper.get("duration_ms"),
    )


def _build_tool_stats(wrapper: dict, context: dict, status: str, summary: Summary) -> dict[str, ToolStats]:
    """Build per-tool stats."""
    tool_name = context["tool_name"]
    return {
        tool_name: ToolStats(
            status=status,
            total=summary["total"],
            passed=summary["passed"],
            failed=summary["failed"],
            skipped=summary["skipped"],
            error=summary["error"],
            blocked=summary["blocked"],
            cancelled=summary["cancelled"],
            duration_ms=summary.get("duration_ms"),
        )
    }


def _build_errors(wrapper: dict, context: dict, status: str) -> list[dict[str, Any]]:
    """Extract errors from wrapper dict based on status."""
    errors: list[dict[str, Any]] = []

    reason = wrapper.get("reason", "")
    error_msg = wrapper.get("error", "")

    if status == "blocked":
        error_type = "RESOURCE_UNAVAILABLE"
        if "not_installed" in reason or "missing" in reason:
            error_type = "CONFIG_ERROR"
        errors.append({
            "error_id": f"err-{uuid.uuid4().hex[:8]}",
            "type": error_type,
            "severity": "warning",
            "message": reason or "Execution blocked",
            "tool": context["tool_name"],
            "stage": context.get("stage", "unknown"),
            "test_id": None,
            "retryable": True,
            "raw_status": status,
            "raw_ref": None,
        })

    elif status == "error":
        errors.append({
            "error_id": f"err-{uuid.uuid4().hex[:8]}",
            "type": "TOOL_PROCESS_ERROR",
            "severity": "error",
            "message": error_msg or reason or "Tool execution error",
            "tool": context["tool_name"],
            "stage": context.get("stage", "unknown"),
            "test_id": None,
            "retryable": True,
            "raw_status": status,
            "raw_ref": None,
        })

    elif status == "failed":
        failed_tests = wrapper.get("failed", [])
        if isinstance(failed_tests, list) and failed_tests:
            for ft in failed_tests:
                errors.append({
                    "error_id": f"err-{uuid.uuid4().hex[:8]}",
                    "type": "TEST_ASSERTION_FAILED",
                    "severity": "error",
                    "message": str(ft) if isinstance(ft, str) else ft.get("message", "Test failed"),
                    "tool": context["tool_name"],
                    "stage": context.get("stage", "unknown"),
                    "test_id": ft if isinstance(ft, str) else ft.get("test_id"),
                    "retryable": False,
                    "raw_status": "failed",
                    "raw_ref": None,
                })
        elif error_msg or reason:
            errors.append({
                "error_id": f"err-{uuid.uuid4().hex[:8]}",
                "type": "UNKNOWN_ERROR",
                "severity": "error",
                "message": error_msg or reason,
                "tool": context["tool_name"],
                "stage": context.get("stage", "unknown"),
                "test_id": None,
                "retryable": False,
                "raw_status": status,
                "raw_ref": None,
            })

    elif status == "cancelled":
        errors.append({
            "error_id": f"err-{uuid.uuid4().hex[:8]}",
            "type": "CANCELLED_BY_USER",
            "severity": "info",
            "message": reason or "Execution cancelled",
            "tool": context["tool_name"],
            "stage": context.get("stage", "unknown"),
            "test_id": None,
            "retryable": False,
            "raw_status": status,
            "raw_ref": None,
        })

    return errors


def _build_evidence(wrapper: dict) -> list[dict[str, Any]]:
    """Extract evidence references from wrapper dict."""
    evidence: list[dict[str, Any]] = []

    results_file = wrapper.get("results_file")
    if results_file:
        evidence.append({
            "evidence_id": f"ev-{uuid.uuid4().hex[:8]}",
            "type": "json_report",
            "path": results_file,
            "name": "Wrapper results file",
            "mime_type": "application/json",
            "size_bytes": None,
            "related_test_id": None,
            "related_issue_id": None,
        })

    return evidence


def _build_tests(wrapper: dict, context: dict) -> list[dict[str, Any]]:
    """Build normalized test case list from wrapper results array."""
    results = wrapper.get("results", [])
    tests: list[dict[str, Any]] = []

    for i, r in enumerate(results):
        raw_status = r.get("status") if isinstance(r, dict) else None
        if raw_status is None and isinstance(r, str):
            raw_status = r
            r = {"name": r}

        if isinstance(r, dict):
            name = r.get("name", r.get("title", f"test-{i+1}"))
            status = "passed"
            if r.get("passed") is False or r.get("status") == "failed":
                status = "failed"
            elif r.get("skipped") or r.get("status") == "skipped":
                status = "skipped"

            tests.append({
                "test_id": f"{context['tool_name']}-{i+1:03d}",
                "name": name,
                "full_name": name,
                "file": r.get("file"),
                "line": r.get("line"),
                "status": status,
                "raw_status": raw_status,
                "duration_ms": r.get("duration_ms"),
                "started_at": r.get("started_at"),
                "ended_at": r.get("ended_at"),
                "attempt": r.get("attempt", 1),
                "retry": r.get("retry", 0),
                "tags": r.get("tags", []),
                "message": r.get("message") or r.get("reason"),
                "trace": r.get("trace"),
                "evidence_refs": [],
            })

    return tests


# ---- main normalizer ----

def normalize_wrapper_dict(
    payload: dict,
    context: dict,
) -> CanonicalTestResult:
    """Convert a legacy wrapper dict to CanonicalTestResult.

    Args:
        payload: The dict returned by a wrapper's run() function.
        context: NormalizeContext with run_id, stage, tool_name, etc.

    Returns:
        A CanonicalTestResult.
    """
    tool_name = context["tool_name"]
    stage = context.get("stage", "unknown")
    now = _utc_now()

    # Derive canonical status
    status = _derive_status(payload)

    # Build sub-structures
    summary = _count_summary(payload, status)
    tool_stats = _build_tool_stats(payload, context, status, summary)
    errors = _build_errors(payload, context, status)
    evidence = _build_evidence(payload)
    tests = _build_tests(payload, context)

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
        evidence=evidence,
        environment=context.get("environment", {}),
        source={
            "type": "wrapper_dict",
            "path": None,
        },
        metadata={"normalizer": "wrapper_dict_v1"},
    )
