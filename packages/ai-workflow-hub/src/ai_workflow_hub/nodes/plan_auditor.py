"""Plan Auditor Node — deterministic plan scope validation.

M4-B1: Entry-point node that validates whether the task plan (scope, risk,
forbidden files) is reasonable before proceeding to execution. Runs BEFORE
human_gate so that obviously broken scopes are blocked without requiring
any model call.
"""

from __future__ import annotations

from typing import Any


def plan_auditor_node(state: dict[str, Any]) -> dict[str, Any]:
    """Validate the task plan scope before proceeding.

    Checks:
    1. If no allowed_files and no plan, and no explicit override — blocked
    2. If risk is high and scope is empty — human_required
    3. Otherwise — clean, continue to human_gate
    """
    result: dict[str, Any] = {}

    allowed = state.get("allowed_files", [])
    forbidden = state.get("forbidden_files", [])
    plan = state.get("plan", "")
    risk = state.get("task_risk", "medium")
    plan_override = state.get("plan_auditor_override", False)

    # Empty scope with no plan — unsafe to proceed
    if not allowed and not plan and not plan_override:
        result["status"] = "blocked"
        result["blocked_reason"] = (
            "plan_auditor: no allowed_files or plan provided, "
            "and plan_auditor_override is False"
        )
        return result

    # High risk with empty scope — requires human review
    if risk == "high" and not allowed and not plan_override:
        result["status"] = "human_required"
        result["human_required"] = True
        result["human_gate_reason"] = (
            "plan_auditor: high risk task with no scope boundaries"
        )
        return result

    # Cross-check: any forbidden file that appears in allowed_files?
    if forbidden:
        intersection = set(allowed) & set(forbidden)
        if intersection:
            result["status"] = "blocked"
            result["blocked_reason"] = (
                "plan_auditor: files appear in both allowed and forbidden: "
                + ", ".join(sorted(intersection))
            )
            return result

    # Clean — proceed
    result["status"] = state.get("status", "running")
    return result
