"""Recovery — 失败/blocked/human_required 时给出可执行建议.

S3 Phase 2: Oracle gate integration — recovery suggestions are suppressed
when the Oracle gate is not in an allowed state.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Optional

from .config_loader import _hub_dir
from .run_governance import summarize_run_governance

_logger = logging.getLogger(__name__)


def analyze_recovery(
    run_id: str,
    project_id: str,
    flow_outcome_path: Optional[Path] = None,
) -> dict[str, Any]:
    """分析 run 并给出恢复建议.

    S3 Phase 2: Before generating automatic recovery suggestions, consults
    the Oracle gate. If the gate is blocked or human_required, no automatic
    recovery suggestions are produced.

    Args:
        run_id: Run ID to analyze.
        project_id: Project ID.
        flow_outcome_path: Optional path to FLOW_OUTCOME.json for gate check.
    """
    # -- Oracle gate check (S3 Phase 2) --
    gate_result = None
    try:
        from .oracle_gate import check_oracle_gate
        gate_result = check_oracle_gate(flow_outcome_path)
    except Exception as e:
        _logger.warning("recover: oracle gate check failed: %s", e)

    rd = _hub_dir() / "runs" / project_id / run_id
    sf = rd / "state.json"
    if not sf.exists():
        return {"error": f"State not found: {sf}"}

    s = json.loads(sf.read_text(encoding="utf-8"))
    status = s.get("status", "?")
    task_id = s.get("task_id", "")
    branch = s.get("current_branch", "")
    wt = s.get("worktree_path", "")
    blocking = _infer_blocking(s)

    # If Oracle gate blocked → suppress automatic recovery suggestions
    if gate_result and not gate_result.allowed:
        if gate_result.business_decision == "human_required" or gate_result.dispatch_status == "manual_confirm_required":
            return {
                "run_id": run_id, "status": status, "task_id": task_id,
                "blocking": blocking, "worktree": wt, "branch": branch,
                "evidence_dir": str(rd),
                "suggestions": [],
                "oracle_gate": {
                    "allowed": False,
                    "business_decision": gate_result.business_decision,
                    "dispatch_status": gate_result.dispatch_status,
                    "reason": gate_result.reason,
                },
                "recovery_blocked_by_oracle": True,
                "required_human_action": gate_result.reason,
            }
        return {
            "run_id": run_id, "status": status, "task_id": task_id,
            "blocking": blocking, "worktree": wt, "branch": branch,
            "evidence_dir": str(rd),
            "suggestions": [],
            "oracle_gate": {
                "allowed": False,
                "business_decision": gate_result.business_decision,
                "dispatch_status": gate_result.dispatch_status,
                "reason": gate_result.reason,
            },
            "recovery_blocked_by_oracle": True,
        }

    suggestions: list[str] = []
    if status == "passed":
        suggestions = [
            "aihub run archive --project ... --run-id ...",
            "aihub worktree clean passed",
        ]
    elif status in ("failed", "blocked"):
        suggestions = [
            f"Read evidence: {rd}",
            "aihub run show --run-id " + run_id,
            "aihub task retry " + task_id,
            f"cd {wt} && git diff" if wt else "",
        ]
    elif status == "human_required":
        suggestions = [
            f"Review: {rd}/human-gate.md",
            f"Approve and re-run: aihub do --apply <task>",
        ]
    elif status == "running":
        suggestions = [
            "May be stale. Check duration.",
            "aihub task mark <id> failed --reason 'stale running'",
        ]

    suggestions = [s for s in suggestions if s]

    run_governance = {}
    governance = {}
    try:
        run_governance = summarize_run_governance(rd, state=s)
        governance = dict(run_governance.get("governance", {}))
    except Exception:
        run_governance = {}
        governance = {}

    result = {
        "run_id": run_id, "status": status, "task_id": task_id,
        "blocking": blocking, "worktree": wt, "branch": branch,
        "evidence_dir": str(rd), "suggestions": suggestions,
        "governance": governance,
        "run_governance": run_governance,
    }
    if gate_result:
        result["oracle_gate"] = {
            "allowed": gate_result.allowed,
            "business_decision": gate_result.business_decision,
            "dispatch_status": gate_result.dispatch_status,
            "reason": gate_result.reason,
        }
    return result


def _infer_blocking(state: dict) -> str:
    err = state.get("error_message", "")
    if err and "timeout" in err.lower():
        return "executor (timeout)"
    if state.get("human_required"):
        return "human_gate"
    if state.get("review_result") == "blocked":
        return "reviewer"
    if state.get("fix_round", 0) >= state.get("max_fix_rounds", 3):
        return "fixer (rounds exhausted)"
    if state.get("test_exit_code", 0) not in (0, -1):
        return "tester"
    return "unknown"
