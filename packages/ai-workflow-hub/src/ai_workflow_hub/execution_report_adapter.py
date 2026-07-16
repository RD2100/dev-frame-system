"""Project run evidence onto the closed ExecutionReport contract."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any
from uuid import uuid4


class ExecutionReportError(ValueError):
    """Raised when run evidence cannot produce a canonical report."""


def load_state(run_dir: str) -> dict[str, Any]:
    """Load state.json from a run directory."""
    path = Path(run_dir) / "state.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {}


def _nonempty_string(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _canonical_status(state: dict[str, Any], run_path: Path) -> tuple[str, list[str]]:
    source_status = _nonempty_string(state.get("status")).lower()
    status = {
        "passed": "pass",
        "failed": "fail",
        "blocked": "blocked",
        "human_required": "escalate",
    }.get(source_status, "blocked")
    issues: list[str] = []

    if status != "pass":
        return status, issues

    executor_id = _nonempty_string(state.get("executor_id"))
    reviewer_id = _nonempty_string(state.get("reviewer_id"))
    reviewer_role = _nonempty_string(state.get("reviewer_role"))
    review_result = _nonempty_string(state.get("review_result")).lower()
    if not executor_id:
        issues.append("Missing executor evidence for passed run.")
    if not reviewer_id:
        issues.append("Missing independent reviewer evidence for passed run.")
    elif reviewer_id == executor_id:
        issues.append("Reviewer must be independent from the executor.")
    if reviewer_role.lower() in {"", "executor", "fixer", "coder"}:
        issues.append("Missing an independent reviewer role for passed run.")
    if review_result != "pass":
        issues.append("Reviewer verdict is not pass.")
    for filename in ("review.yaml", "review.md"):
        if not (run_path / filename).is_file():
            issues.append(f"Missing reviewer artifact: {filename}.")
    return ("blocked", issues) if issues else ("pass", issues)


def _trust_record(state: dict[str, Any]) -> dict[str, Any] | None:
    backend_calls = state.get("backend_calls")
    executor = backend_calls.get("executor") if isinstance(backend_calls, dict) else None
    if not isinstance(executor, dict):
        return None
    mapping = {
        "session_id": "session_id",
        "model": "model_used",
        "tokens_used": "tokens_used",
        "backend": "dispatch_method",
        "cost_estimate": "cost_estimate",
    }
    record = {
        destination: executor[source]
        for source, destination in mapping.items()
        if source in executor and executor[source] is not None
    }
    return record or None


def to_execution_report(
    run_dir: str,
    *,
    batch_id: str | None = None,
) -> dict[str, Any]:
    """Generate a closed-schema ExecutionReport from a run directory."""
    run_path = Path(run_dir)
    state = load_state(run_dir)
    resolved_batch_id = _nonempty_string(batch_id) if batch_id is not None else _nonempty_string(state.get("task_id"))
    if not resolved_batch_id:
        raise ExecutionReportError("ExecutionReport batch_id must be a non-empty string")

    status, issues = _canonical_status(state, run_path)
    error_message = _nonempty_string(state.get("error_message"))
    if error_message:
        issues.append(error_message)

    report: dict[str, Any] = {
        "report_id": f"execution-report-{uuid4()}",
        "batch_id": resolved_batch_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "summary": f"Run {state.get('run_id', resolved_batch_id)} reported {status}.",
    }
    executor_id = _nonempty_string(state.get("executor_id"))
    if executor_id:
        report["executor_id"] = executor_id
    run_id = _nonempty_string(state.get("run_id"))
    if run_id:
        report["run_ids"] = [run_id]
    trust_record = _trust_record(state)
    if trust_record:
        report["trust_record"] = trust_record
    if status == "pass":
        report["reviewer_artifacts"] = {
            "review_md": str(run_path / "review.md"),
            "review_yaml": str(run_path / "review.yaml"),
            "reviewer_role": _nonempty_string(state.get("reviewer_role")),
            "reviewer_id": _nonempty_string(state.get("reviewer_id")),
            "verdict": "pass",
        }
    if issues:
        report["blocking_issues"] = issues
    return report
