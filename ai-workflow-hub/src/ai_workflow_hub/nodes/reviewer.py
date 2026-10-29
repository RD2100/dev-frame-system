"""Reviewer Node — deterministic code review verdict.

Produces a structured review verdict from test results, safety checks, and
execution logs. No model call — deterministic only.
"""

from __future__ import annotations

from typing import Any


def reviewer_node(state: dict[str, Any]) -> dict[str, Any]:
    """Generate a deterministic review verdict.

    Uses test results, safety report, and fix-round exhaustion to produce
    a pass/blocked/human_gate verdict without calling any AI model.
    """
    result: dict[str, Any] = {}

    test_passed = state.get("test_exit_code", -1) == 0
    fix_round = state.get("fix_round", 0)
    max_fix_rounds = state.get("max_fix_rounds", 3)
    safety = state.get("safety_overall", "")
    dangerous = state.get("dangerous_change", False)

    # Safety hard-block
    if safety == "blocked":
        result["status"] = "blocked"
        result["review_result"] = "blocked"
        result["review_verdict"] = (
            "Safety check blocked: execution touched forbidden paths"
        )
        result["blocked_reason"] = state.get("safety_message", "safety blocked")
        return result

    # Danger detected — requires human
    if dangerous:
        result["status"] = "human_required"
        result["human_required"] = True
        result["review_result"] = "human_gate"
        result["review_verdict"] = (
            "Dangerous change detected — requires human review"
        )
        return result

    # Tests passed → clean
    if test_passed:
        result["status"] = "passed"
        result["review_result"] = "pass"
        result["review_verdict"] = "All tests passed, no safety violations"
        return result

    # Tests failed, still have fix rounds → should go to fixer, not here
    if fix_round < max_fix_rounds:
        result["status"] = "running"
        result["review_result"] = "fail"
        result["review_verdict"] = (
            f"Tests failed, round {fix_round}/{max_fix_rounds} — retry via fixer"
        )
        return result

    # Tests failed, no more fix rounds
    result["status"] = "blocked"
    result["review_result"] = "blocked"
    result["review_verdict"] = (
        f"Tests still failing after {fix_round} fix rounds (max={max_fix_rounds})"
    )
    return result
