"""Run evidence -> @go ExecutionReport adapter."""

from __future__ import annotations
import json
from pathlib import Path
from typing import Any


def load_state(run_dir: str) -> dict[str, Any]:
    """Load state.json from a run directory."""
    path = Path(run_dir) / "state.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {}


def load_diff_summary(run_dir: str) -> str:
    """Extract diff summary."""
    path = Path(run_dir) / "diff.patch"
    if path.exists():
        diff = path.read_text(encoding="utf-8")
        lines = [l for l in diff.splitlines() if l and not l.startswith("\\")]
        files = [l for l in diff.splitlines() if l.startswith("---") or l.startswith("+++")]
        return f"{len(files)//2} files changed, {len(lines)} lines"
    return ""


def load_test_results(run_dir: str) -> str:
    """Extract test output summary."""
    path = Path(run_dir) / "test-output.md"
    if path.exists():
        return path.read_text(encoding="utf-8")[:2000]
    return ""


def to_execution_report(run_dir: str) -> dict[str, Any]:
    """Generate a @go ExecutionReport from run evidence.

    Returns a dict matching the ExecutionReport schema:
        task_id, status, diff_summary, test_results,
        safety, evidence_trust, executed_nodes, error_message
    """
    state = load_state(run_dir)
    return {
        "task_id": state.get("task_id", ""),
        "status": state.get("status", "unknown"),
        "diff_summary": load_diff_summary(run_dir),
        "test_results": load_test_results(run_dir),
        "safety": {
            "overall": state.get("safety_overall", "unknown"),
            "forbidden_paths": state.get("forbidden_paths_touched", []),
        },
        "evidence_trust": state.get("signature_status", "unsigned"),
        "executed_nodes": state.get("executed_nodes", []),
        "error_message": state.get("error_message", ""),
        "fix_rounds": state.get("fix_round", 0),
        "changed_files": state.get("changed_files", []),
    }
