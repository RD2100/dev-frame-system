# -*- coding: utf-8 -*-
"""Signals normalizer: Sentry / Bugly quality signals -> CanonicalTestResult.

Non-test tools (Sentry, Bugly) produce:
  - tests = []          (no test cases)
  - signals = [...]     (aggregate quality metrics)
  - issues = [...]      (individual issues/crashes)
  - suite.type = "monitoring"
"""

import uuid
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


# ---- Sentry normalizer ----

def normalize_sentry_issues(
    payload: list[dict] | dict,
    context: dict,
) -> CanonicalTestResult:
    """Convert Sentry issue list (or crash_summary dict) to CanonicalTestResult.

    Args:
        payload: Either a list of Sentry issue dicts (from Sentry API),
                 or a crash_summary dict from get_crash_summary().
        context: NormalizeContext.

    Returns:
        CanonicalTestResult with tests=[], signals and issues populated.
    """
    tool_name = context["tool_name"]
    stage = context.get("stage", "regression")
    now = _utc_now()

    # Normalize payload to issue list
    if isinstance(payload, dict):
        issues_list = payload.get("top_issues", [])
        by_severity = payload.get("by_severity", {})
        unresolved_count = payload.get("unresolved", 0)
        total_count = payload.get("total_issues", 0)
    else:
        issues_list = payload
        by_severity = {}
        for i in issues_list:
            level = i.get("level", i.get("severity", "unknown"))
            by_severity[level] = by_severity.get(level, 0) + 1
        total_count = len(issues_list)
        unresolved_count = sum(1 for i in issues_list if i.get("status") == "unresolved")

    # Build signals
    signals: list[dict[str, Any]] = []

    # Unresolved issue count signal
    unresolved_signal_status = "passed" if unresolved_count == 0 else "failed"
    signals.append({
        "name": "sentry.unresolved_issue_count",
        "type": "count",
        "value": unresolved_count,
        "unit": "issues",
        "status": unresolved_signal_status,
        "threshold": {"operator": "<=", "value": 0},
        "source": tool_name,
        "stage": stage,
    })

    # Fatal issue count
    fatal_count = by_severity.get("fatal", by_severity.get("error", 0))
    if isinstance(fatal_count, int) and fatal_count > 0:
        signals.append({
            "name": "sentry.fatal_issue_count",
            "type": "count",
            "value": fatal_count,
            "unit": "issues",
            "status": "failed" if fatal_count > 0 else "passed",
            "threshold": {"operator": "<=", "value": 0},
            "source": tool_name,
            "stage": stage,
        })

    # Total issues signal (informational)
    signals.append({
        "name": "sentry.total_issue_count",
        "type": "count",
        "value": total_count,
        "unit": "issues",
        "status": "passed",
        "threshold": None,
        "source": tool_name,
        "stage": stage,
    })

    # Build issues list
    issues: list[dict[str, Any]] = []
    for item in issues_list[:50]:  # cap at 50
        issue_id = item.get("id", item.get("issue_id", f"SENTRY-{uuid.uuid4().hex[:8]}"))
        title = item.get("title", item.get("message", "unknown"))
        severity = item.get("level", item.get("severity", "error"))
        status_val = item.get("status", "unresolved")
        count = item.get("count", item.get("eventCount", 1))
        issues.append({
            "issue_id": str(issue_id),
            "source": tool_name,
            "title": str(title)[:200],
            "severity": str(severity),
            "status": str(status_val),
            "count": int(count) if count else 0,
            "affected_users": item.get("userCount") or item.get("affected_users"),
            "first_seen": item.get("firstSeen", item.get("first_seen")),
            "last_seen": item.get("lastSeen", item.get("last_seen")),
            "url": item.get("permalink") or item.get("url"),
            "fingerprint": None,
            "evidence_refs": [],
            "raw_ref": None,
        })

    # Derive overall status from signals
    if any(s["status"] == "failed" for s in signals if s.get("threshold")):
        status = "failed"
    elif total_count == 0 and unresolved_count == 0:
        status = "passed"
    else:
        status = "failed"

    # Duration is network call time, approximate
    duration_ms = 0

    summary = Summary(
        total=0, passed=0, failed=0, skipped=0,
        error=0, blocked=0, cancelled=0,
        test_pass_rate=None,
        test_pass_rate_basis="executed_tests",
        duration_ms=duration_ms,
    )

    tool_stats = {
        tool_name: ToolStats(
            status=status,
            total=0, passed=0, failed=0, skipped=0,
            error=0, blocked=0, cancelled=0,
            duration_ms=duration_ms,
        )
    }

    return CanonicalTestResult(
        schema_version="test-frame.canonical.v1",
        result_id=_generate_result_id(stage, tool_name),
        run_id=context.get("run_id", "unknown"),
        stage=stage,
        tool=_build_tool_info(context),
        suite=_build_suite_info(
            {**context, "suite_type": "monitoring"},
            status, now, now,
        ),
        status=status,
        summary=summary,
        tool_stats=tool_stats,
        tests=[],
        signals=signals,
        issues=issues,
        quality={},
        errors=[],
        evidence=[],
        environment=context.get("environment", {}),
        source={"type": "sentry_issues", "path": None},
        metadata={"normalizer": "sentry_issues_v1"},
    )


# ---- Bugly normalizer ----

def normalize_bugly_crash_stats(
    payload: dict,
    context: dict,
) -> CanonicalTestResult:
    """Convert Bugly crash stats dict to CanonicalTestResult.

    Args:
        payload: Bugly crash statistics dict with keys:
            crash_rate, crash_count, affected_users, top_stacks.
        context: NormalizeContext.

    Returns:
        CanonicalTestResult with tests=[], signals and issues populated.
    """
    tool_name = context["tool_name"]
    stage = context.get("stage", "regression")
    now = _utc_now()

    crash_rate = payload.get("crash_rate", 0)
    crash_count = payload.get("crash_count", 0)
    affected_users = payload.get("affected_users", 0)
    top_stacks = payload.get("top_stacks", [])

    # Build signals
    signals: list[dict[str, Any]] = []

    crash_rate_pct = float(crash_rate) if crash_rate else 0
    signals.append({
        "name": "bugly.crash_rate",
        "type": "rate",
        "value": crash_rate_pct,
        "unit": "%",
        "status": "failed" if crash_rate_pct > 0.1 else "passed",
        "threshold": {"operator": "<=", "value": 0.1},
        "source": tool_name,
        "stage": stage,
    })

    signals.append({
        "name": "bugly.crash_count",
        "type": "count",
        "value": crash_count,
        "unit": "crashes",
        "status": "failed" if crash_count > 0 else "passed",
        "threshold": {"operator": "<=", "value": 0},
        "source": tool_name,
        "stage": stage,
    })

    signals.append({
        "name": "bugly.affected_users",
        "type": "count",
        "value": affected_users,
        "unit": "users",
        "status": "failed" if affected_users > 0 else "passed",
        "threshold": {"operator": "<=", "value": 0},
        "source": tool_name,
        "stage": stage,
    })

    # Build issues from top stacks
    issues: list[dict[str, Any]] = []
    for i, stack in enumerate(top_stacks[:10]):
        issues.append({
            "issue_id": stack.get("id", f"BUGLY-TOP-{i+1:03d}"),
            "source": tool_name,
            "title": str(stack.get("title", stack.get("exception", f"Crash #{i+1}")))[:200],
            "severity": stack.get("severity", "fatal"),
            "status": "active",
            "count": stack.get("count", 0),
            "affected_users": stack.get("affected_users"),
            "first_seen": stack.get("first_seen"),
            "last_seen": stack.get("last_seen"),
            "url": None,
            "fingerprint": stack.get("fingerprint"),
            "evidence_refs": [],
            "raw_ref": None,
        })

    # Derive overall status
    status = "failed" if any(s["status"] == "failed" for s in signals) else "passed"

    summary = Summary(
        total=0, passed=0, failed=0, skipped=0,
        error=0, blocked=0, cancelled=0,
        test_pass_rate=None,
        test_pass_rate_basis="executed_tests",
        duration_ms=0,
    )

    tool_stats = {
        tool_name: ToolStats(
            status=status,
            total=0, passed=0, failed=0, skipped=0,
            error=0, blocked=0, cancelled=0,
            duration_ms=0,
        )
    }

    return CanonicalTestResult(
        schema_version="test-frame.canonical.v1",
        result_id=_generate_result_id(stage, tool_name),
        run_id=context.get("run_id", "unknown"),
        stage=stage,
        tool=_build_tool_info(context),
        suite=_build_suite_info(
            {**context, "suite_type": "monitoring"},
            status, now, now,
        ),
        status=status,
        summary=summary,
        tool_stats=tool_stats,
        tests=[],
        signals=signals,
        issues=issues,
        quality={},
        errors=[],
        evidence=[],
        environment=context.get("environment", {}),
        source={"type": "bugly_crash_stats", "path": None},
        metadata={"normalizer": "bugly_crash_stats_v1"},
    )
