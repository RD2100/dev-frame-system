# -*- coding: utf-8 -*-
"""Normalizer entry point and shared helpers.

Dispatches raw results (wrapper dict, Playwright JSON, JUnit XML, etc.)
to CanonicalTestResult via source-specific normalizers.
"""

import uuid
from datetime import datetime, timezone
from typing import Any

from schema.canonical import (
    VALID_STATUSES,
    ToolInfo,
    SuiteInfo,
    Summary,
    ToolStats,
    CanonicalTestResult,
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _generate_result_id(stage: str, tool_name: str) -> str:
    """Generate a unique result_id: ctr-{stage}-{tool}-{short_uuid}."""
    short = uuid.uuid4().hex[:8]
    return f"ctr-{stage}-{tool_name}-{short}"


def _build_tool_info(context: dict) -> ToolInfo:
    """Build ToolInfo from NormalizeContext."""
    return ToolInfo(
        name=context["tool_name"],
        display_name=context.get("display_name", context["tool_name"]),
        adapter_type=context.get("adapter_type", "wrapper"),
        version=context.get("tool_version"),
        contract_ref=context.get("contract_ref"),
    )


def _build_suite_info(context: dict, status: str, started_at: str, ended_at: str) -> SuiteInfo:
    """Build SuiteInfo from context."""
    return SuiteInfo(
        name=context.get("suite_name", f'{context.get("stage", "unknown")}-{context["tool_name"]}'),
        type=context.get("suite_type", "unknown"),
        status=status,
        started_at=started_at,
        ended_at=ended_at,
        duration_ms=None,
    )


def _empty_summary() -> Summary:
    """Return a zeroed Summary (for error/empty results)."""
    return Summary(
        total=0, passed=0, failed=0, skipped=0,
        error=0, blocked=0, cancelled=0,
        test_pass_rate=None, test_pass_rate_basis="executed_tests",
        duration_ms=None,
    )


def _empty_tool_stats(context: dict, status: str) -> dict[str, ToolStats]:
    """Return tool_stats dict with a single zeroed entry."""
    return {
        context["tool_name"]: ToolStats(
            status=status,
            total=0, passed=0, failed=0, skipped=0,
            error=0, blocked=0, cancelled=0,
            duration_ms=None,
        )
    }


def make_error_result(
    context: dict,
    error_type: str,
    message: str,
    *,
    status: str = "error",
    retryable: bool = False,
) -> CanonicalTestResult:
    """Create a CanonicalTestResult representing a normalization or execution error.

    Args:
        context: NormalizeContext dict.
        error_type: One of ErrorType literals (TOOL_PROCESS_ERROR, PARSE_ERROR, etc.).
        message: Human-readable error message.
        status: CanonicalStatus, defaults to "error".
        retryable: Whether the operation can be retried.

    Returns:
        A minimal CanonicalTestResult with error information populated.
    """
    now = _utc_now()
    tool_name = context["tool_name"]
    stage = context.get("stage", "unknown")

    return CanonicalTestResult(
        schema_version="test-frame.canonical.v1",
        result_id=_generate_result_id(stage, tool_name),
        run_id=context.get("run_id", "unknown"),
        stage=stage,
        tool=_build_tool_info(context),
        suite=_build_suite_info(context, status, now, now),
        status=status,
        summary=_empty_summary(),
        tool_stats=_empty_tool_stats(context, status),
        tests=[],
        signals=[],
        issues=[],
        quality={},
        errors=[{
            "error_id": f"err-{uuid.uuid4().hex[:8]}",
            "type": error_type,
            "severity": "error",
            "message": message,
            "tool": tool_name,
            "stage": stage,
            "test_id": None,
            "retryable": retryable,
            "raw_status": None,
            "raw_ref": None,
        }],
        evidence=[],
        environment=context.get("environment", {}),
        source={
            "type": "normalizer_error",
            "path": None,
        },
        metadata={"normalizer": "error_result"},
    )


def normalize_result(
    source: dict,
    context: dict,
) -> CanonicalTestResult:
    """Dispatch a raw result source to the appropriate normalizer.

    Args:
        source: RawResultSource dict with keys: kind, payload, path.
        context: NormalizeContext dict.

    Returns:
        A CanonicalTestResult.

    Raises:
        ValueError: If source.kind is unsupported.
    """
    kind = source.get("kind", "unknown")

    if kind == "wrapper_dict":
        from normalizers.wrapper import normalize_wrapper_dict
        return normalize_wrapper_dict(source.get("payload", {}), context)

    # Future normalizers:
    if kind == "playwright_json":
        from normalizers.playwright import normalize_playwright_json
        return normalize_playwright_json(source.get("payload"), context)
    if kind == "junit_xml":
        from normalizers.junit import normalize_junit_xml
        return normalize_junit_xml(source.get("payload"), context)
    if kind == "sentry_issues":
        from normalizers.signals import normalize_sentry_issues
        return normalize_sentry_issues(source.get("payload"), context)
    if kind == "bugly_crash_stats":
        from normalizers.signals import normalize_bugly_crash_stats
        return normalize_bugly_crash_stats(source.get("payload"), context)

    return make_error_result(
        context=context,
        error_type="UNSUPPORTED_RESULT_SOURCE",
        message=f"Unsupported result source kind: {kind}",
        status="error",
        retryable=False,
    )
