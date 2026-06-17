"""Evidence helpers shared by workflow nodes."""

from __future__ import annotations

from typing import Any

from ..config_loader import get_execution_policy
from ..safety import produce_safety_report


def collect_safety_evidence(
    state: dict[str, Any],
    cwd: str,
    diff_info: dict[str, Any],
) -> dict[str, Any]:
    """Run the canonical safety checks for the current diff facts."""
    constraints = state.get("constraints", {})
    execution_policy = get_execution_policy()
    safety_report = produce_safety_report(
        run_dir=state.get("run_dir", ""),
        repo_path=cwd,
        name_status=diff_info["name_status"],
        changed_files=diff_info["changed_files"],
        forbidden_patterns=state.get("forbidden_files", []),
        protected_patterns=state.get("protected_tests", []),
        diff_line_count=diff_info["diff_line_count"],
        max_diff_lines=constraints.get(
            "max_diff_lines", execution_policy.get("max_diff_lines", 800)
        ),
        max_changed_files=constraints.get(
            "max_changed_files", execution_policy.get("max_changed_files", 20)
        ),
        risk=state.get("task_risk", "medium"),
    )
    forbidden_paths = []
    for check in safety_report.get("checks", []):
        if check.get("name") == "forbidden_paths":
            detail = check.get("detail", [])
            forbidden_paths = detail if isinstance(detail, list) else []
            break

    result: dict[str, Any] = {
        "safety_overall": safety_report.get("overall", "unknown"),
        "safety_report": safety_report,
        "forbidden_paths_touched": forbidden_paths,
    }
    if safety_report.get("overall") == "blocked":
        result.update({
            "status": "blocked",
            "review_result": "blocked",
            "error_message": "Safety report blocked this run",
        })
    elif safety_report.get("overall") == "human_gate":
        result.update({
            "status": "human_required",
            "human_required": True,
            "error_message": "Safety report requires human review",
        })
    return result
