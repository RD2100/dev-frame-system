"""paper_runtime.py — A16/A16B Paper Workflow Runtime E2E Integration.

Provides the entry points for running paper review workflows through
the runtime infrastructure (daemon, task_queue, CLI).

Key functions:
    create_paper_run()    — Create a run directory and initial state.
    execute_paper_run()   — Execute the paper graph with runtime context.
    resume_paper_run()    — Resume a paused paper run after human decision.
    get_paper_run_status() — Read the current status of a paper run.
    write_human_gate_artifact() — Write human-readable review artifact.

A16B Closeout:
    - Privacy redaction: sensitive fields stripped before state.json persist
    - run_id sanitization: prevents path traversal in run directory names
    - dispatch_paper_task: updates task_queue status after dispatch
    - Audit trail isolation: per-run decision audit scoping
    - Error policy: best-effort failures reported as warnings (non-blocking)

Design:
    - Mirrors the coding domain's cli._execute_run() pattern.
    - Creates a run_dir with state.json for persistence.
    - Writes paper-human-gate.md when the workflow pauses for human review.
    - Bridges paper_decision_audit with the file-based resume protocol.
    - Integrates with daemon._execute_one_task via workflow_type routing.
"""

from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ...workflows.paper_graph import (
    compile_paper_graph,
    apply_human_decision,
)
from ...workflows.paper_workflow_state import PaperWorkflowState


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_RUNS_BASE = Path("runs") / "paper"
_STATE_FILE = "state.json"
_GATE_ARTIFACT = "paper-human-gate.md"
_VALID_DECISIONS = {"approved", "rejected"}

# A16B: Privacy — fields to redact before persisting state.json
_SENSITIVE_FIELDS = {"paragraph_text", "writelab_token"}
_REDACTED_MARKER = "[REDACTED]"
_PAPER_SENSITIVE_POLICY_EXPLICIT_ALLOW = "explicit_allow"
_RUNTIME_EXTRA_FIELDS = {"runtime_authorization", "privacy_gate"}
_PRIVACY_GATE_REASON = "paper_sensitive_input_requires_runtime_authorization"

# A16B: run_id sanitization (reuses A15 pattern)
_RUN_ID_SAFE = re.compile(r"[^a-zA-Z0-9_\-]")
_MAX_RUN_ID_LEN = 128


# ---------------------------------------------------------------------------
# Run directory management
# ---------------------------------------------------------------------------

def _runs_root(base_dir: str | None = None) -> Path:
    """Return the paper runs root directory."""
    if base_dir:
        root = Path(base_dir) / _RUNS_BASE
    else:
        root = Path.home() / ".ai_workflow_hub" / _RUNS_BASE
    root.mkdir(parents=True, exist_ok=True)
    return root


def _run_path(run_id: str, base_dir: str | None = None,
              create: bool = True) -> Path:
    """Return the directory for a specific run.

    Args:
        run_id: Run identifier.
        base_dir: Override base directory.
        create: If True (default), create the directory if it doesn't exist.
    """
    p = _runs_root(base_dir) / run_id
    if create:
        p.mkdir(parents=True, exist_ok=True)
    return p


def _save_state(run_dir: Path, state: dict[str, Any]) -> None:
    """Atomically save state to run_dir/state.json."""
    state_file = run_dir / _STATE_FILE
    tmp = state_file.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2, ensure_ascii=False, default=str),
                   encoding="utf-8")
    tmp.replace(state_file)


def _load_state(run_dir: Path) -> dict[str, Any] | None:
    """Load state from run_dir/state.json."""
    state_file = run_dir / _STATE_FILE
    if not state_file.exists():
        return None
    try:
        return json.loads(state_file.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


# ---------------------------------------------------------------------------
# A16B: Privacy redaction, run_id sanitization, audit isolation
# ---------------------------------------------------------------------------

def sanitize_run_id(run_id: str) -> str:
    """Sanitize a run_id for safe filesystem use (A16B).

    Replaces unsafe characters, strips path traversal sequences,
    and truncates to _MAX_RUN_ID_LEN characters.

    Args:
        run_id: The run identifier to sanitize.

    Returns:
        Sanitized run_id string.

    Raises:
        ValueError: If run_id is empty or produces empty string.
    """
    if not run_id or not run_id.strip():
        raise ValueError("run_id must be a non-empty string")
    safe = _RUN_ID_SAFE.sub("_", run_id.strip())
    safe = re.sub(r"_+", "_", safe)
    safe = safe.replace("..", "_")
    safe = re.sub(r"_+", "_", safe)
    safe = safe.lstrip(".")
    safe = safe[:_MAX_RUN_ID_LEN]
    if not safe:
        raise ValueError(f"run_id {run_id!r} produces empty string after sanitization")
    return safe


def redact_state(state: dict[str, Any]) -> dict[str, Any]:
    """Return a copy of state with sensitive fields redacted (A16B).

    Replaces values of _SENSITIVE_FIELDS keys with _REDACTED_MARKER.
    Does NOT modify the original dict.

    Args:
        state: The workflow state dict.

    Returns:
        New dict with sensitive fields replaced.
    """
    redacted = dict(state)
    for field in _SENSITIVE_FIELDS:
        if field in redacted and redacted[field]:
            redacted[field] = _REDACTED_MARKER
    return redacted


def _redact_sensitive_text(text: Any, state: dict[str, Any]) -> str:
    """Redact known sensitive runtime values before writing human artifacts."""
    redacted = str(text)
    raw_values = [
        state.get(field)
        for field in _SENSITIVE_FIELDS
        if isinstance(state.get(field), str)
        and state.get(field)
        and state.get(field) != _REDACTED_MARKER
    ]
    for value in sorted(raw_values, key=len, reverse=True):
        redacted = redacted.replace(value, _REDACTED_MARKER)
    for field in _SENSITIVE_FIELDS:
        redacted = re.sub(
            rf"({re.escape(field)}\s*[:=]\s*)([^,\n;`]+)",
            rf"\1{_REDACTED_MARKER}",
            redacted,
        )
    return redacted


def _raw_sensitive_fields(state: dict[str, Any]) -> set[str]:
    """Return sensitive fields that contain non-redacted runtime values."""
    return {
        field
        for field in _SENSITIVE_FIELDS
        if state.get(field) and state.get(field) != _REDACTED_MARKER
    }


def _has_sensitive_input_authorization(
    state: dict[str, Any],
    sensitive_fields: set[str],
) -> bool:
    """Check explicit RuntimeAuthorization for real paper sensitive input."""
    auth = state.get("runtime_authorization")
    if not isinstance(auth, dict):
        return False
    if auth.get("preflight_status") != "pass":
        return False
    if not auth.get("human_gate_ref"):
        return False

    data_policy = auth.get("data_policy")
    if not isinstance(data_policy, dict):
        return False
    if data_policy.get("paper_sensitive_input") != _PAPER_SENSITIVE_POLICY_EXPLICIT_ALLOW:
        return False
    if data_policy.get("redaction_required") is not True:
        return False

    allowed_fields = set(data_policy.get("allowed_sensitive_fields") or [])
    return sensitive_fields.issubset(allowed_fields)


def _existing_privacy_gate_fields(state: dict[str, Any]) -> set[str]:
    gate = state.get("privacy_gate")
    if not isinstance(gate, dict) or gate.get("reason") != _PRIVACY_GATE_REASON:
        return set()
    return set(gate.get("sensitive_fields") or [])


def _privacy_gate_update(state: dict[str, Any], sensitive_fields: set[str]) -> dict[str, Any]:
    field_list = sorted(sensitive_fields)
    issue = {
        "issue_id": "paper-privacy-runtime-authorization-required",
        "issue_type": "privacy",
        "severity": "blocking",
        "location": {
            "chapter": state.get("task_chapter", ""),
            "section": state.get("task_section", ""),
            "paragraph_index": state.get("paragraph_index", 0),
        },
        "evidence": (
            "Raw paper sensitive input was supplied without explicit "
            "RuntimeAuthorization data_policy."
        ),
        "recommendation": (
            "Provide a RuntimeAuthorization with data_policy.paper_sensitive_input="
            "explicit_allow, allowed_sensitive_fields, redaction_required=true, "
            "and a human_gate_ref before executing with real paper content."
        ),
        "blocking": True,
        "human_required": True,
    }
    return {
        "status": "human_required",
        "human_required": True,
        "human_gate_triggered": True,
        "human_gate_decision": "pending",
        "acceptance_status": "human_required",
        "blocking_count": 1,
        "non_blocking_count": 0,
        "all_review_issues": [issue],
        "privacy_gate": {
            "status": "human_required",
            "reason": _PRIVACY_GATE_REASON,
            "sensitive_fields": field_list,
            "required_authorization": "RuntimeAuthorization.data_policy",
        },
    }


def _paper_sensitive_input_gate(state: dict[str, Any]) -> dict[str, Any] | None:
    """Return a human gate update when paper sensitive input lacks authorization."""
    sensitive_fields = _raw_sensitive_fields(state)
    if sensitive_fields:
        if _has_sensitive_input_authorization(state, sensitive_fields):
            state.pop("privacy_gate", None)
            return None
        return _privacy_gate_update(state, sensitive_fields)

    gated_fields = _existing_privacy_gate_fields(state)
    if gated_fields:
        if _has_sensitive_input_authorization(state, gated_fields):
            state.pop("privacy_gate", None)
            return None
        return _privacy_gate_update(state, gated_fields)

    return None


def _save_state_safe(run_dir: Path, state: dict[str, Any]) -> None:
    """Atomically save redacted state to run_dir/state.json (A16B).

    Uses redact_state() to strip sensitive fields before writing.
    """
    _save_state(run_dir, redact_state(state))


# ---------------------------------------------------------------------------
# Core API
# ---------------------------------------------------------------------------

def create_paper_run(
    task_id: str,
    project_id: str = "",
    base_dir: str | None = None,
    initial_state: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Create a new paper run directory with initial state.

    Args:
        task_id: The paper review task identifier.
        project_id: Optional project identifier.
        base_dir: Override base directory for runs.
        initial_state: Optional state overrides.

    Returns:
        Dict with run_id, run_dir, and initial state.

    Raises:
        ValueError: If task_id is empty.
    """
    if not task_id or not task_id.strip():
        raise ValueError("task_id must be a non-empty string")

    run_id = f"paper-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:6]}"
    run_id = sanitize_run_id(run_id)  # A16B: ensure safe for filesystem
    run_dir = _run_path(run_id, base_dir)

    # Build initial state
    state = PaperWorkflowState().model_dump()
    state["task_id"] = task_id
    state["project_id"] = project_id
    state["run_id"] = run_id
    state["run_dir"] = str(run_dir)
    state["workflow_type"] = "paper"
    state["status"] = "created"
    state["created_at"] = datetime.now(timezone.utc).isoformat()
    state["updated_at"] = state["created_at"]

    if initial_state:
        for k, v in initial_state.items():
            if hasattr(state, k) or k in state or k in _RUNTIME_EXTRA_FIELDS:
                state[k] = v

    gate_update = _paper_sensitive_input_gate(state)
    if gate_update:
        state.update(gate_update)

    # A16B: scope decision audit to this run's directory
    state["decision_base_dir"] = str(run_dir)

    # A16B: use privacy-safe save
    _save_state_safe(run_dir, state)

    return {
        "run_id": run_id,
        "run_dir": str(run_dir),
        "task_id": task_id,
        "project_id": project_id,
        "status": state.get("status", "created"),
        "state": redact_state(state),
    }


def execute_paper_run(
    run_id: str,
    base_dir: str | None = None,
    state_overrides: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Execute the paper workflow graph for a given run.

    Loads state from run_dir, compiles the graph, invokes it, and
    saves the resulting state back to run_dir/state.json.

    If the workflow pauses at human_gate, writes paper-human-gate.md
    to the run_dir for human inspection.

    Args:
        run_id: The run identifier (from create_paper_run).
        base_dir: Override base directory for runs.
        state_overrides: Optional state overrides before invoke.

    Returns:
        Dict with run_id, status, state, and gate_artifact path (if paused).

    Raises:
        FileNotFoundError: If run_dir does not exist.
        ValueError: If state.json is missing or corrupt.
    """
    run_dir = _run_path(run_id, base_dir, create=False)
    if not run_dir.exists():
        raise FileNotFoundError(f"Run directory not found: {run_dir}")

    state = _load_state(run_dir)
    if state is None:
        raise ValueError(f"state.json missing or corrupt in {run_dir}")

    # Apply overrides
    if state_overrides:
        for k, v in state_overrides.items():
            state[k] = v

    gate_update = _paper_sensitive_input_gate(state)
    if gate_update:
        state.update(gate_update)
        state["updated_at"] = datetime.now(timezone.utc).isoformat()
        _save_state_safe(run_dir, state)
        response: dict[str, Any] = {
            "run_id": run_id,
            "status": "human_required",
            "state": redact_state(state),
            "warnings": [],
        }
        try:
            response["gate_artifact"] = write_human_gate_artifact(run_id, state, base_dir)
        except Exception as e:
            response["warnings"].append(f"gate_artifact_write_failed: {e}")
        return response

    state["status"] = "running"
    state["updated_at"] = datetime.now(timezone.utc).isoformat()
    warnings: list[str] = []  # A16B: track best-effort failures

    # Compile and invoke graph
    thread_id = f"paper-{run_id}"
    compiled = compile_paper_graph(thread_id)
    config = {"configurable": {"thread_id": thread_id}}

    try:
        result = compiled.invoke(state, config)
    except Exception as e:
        state["status"] = "error"
        state["error_message"] = str(e)
        state["updated_at"] = datetime.now(timezone.utc).isoformat()
        _save_state_safe(run_dir, state)
        return {
            "run_id": run_id,
            "status": "error",
            "error": str(e),
            "state": redact_state(state),
            "warnings": warnings,
        }

    # Merge result back into state
    if isinstance(result, dict):
        state.update(result)
    elif hasattr(result, "model_dump"):
        state.update(result.model_dump())

    state["updated_at"] = datetime.now(timezone.utc).isoformat()
    _save_state_safe(run_dir, state)

    response: dict[str, Any] = {
        "run_id": run_id,
        "status": state.get("status", "unknown"),
        "state": redact_state(state),
        "warnings": warnings,
    }

    # Write human gate artifact if paused (A16B: report failure as warning)
    if state.get("status") == "human_required":
        try:
            artifact_path = write_human_gate_artifact(run_id, state, base_dir)
            response["gate_artifact"] = artifact_path
        except Exception as e:
            warnings.append(f"gate_artifact_write_failed: {e}")

    return response


def resume_paper_run(
    run_id: str,
    decision: str,
    reviewer_id: str = "",
    note: str = "",
    base_dir: str | None = None,
    require_reviewer: bool = False,
) -> dict[str, Any]:
    """Resume a paused paper run after human decision.

    Loads state from run_dir, applies the decision via apply_human_decision,
    re-invokes the graph, and saves the resulting state.

    Args:
        run_id: The run identifier.
        decision: "approved" or "rejected".
        reviewer_id: Who made the decision.
        note: Optional note explaining the decision.
        base_dir: Override base directory for runs.
        require_reviewer: If True, raise ValueError when reviewer_id is empty.

    Returns:
        Dict with run_id, status, and updated state.

    Raises:
        FileNotFoundError: If run_dir does not exist.
        ValueError: If state is missing, decision is invalid, or reviewer required.
    """
    if decision not in _VALID_DECISIONS:
        raise ValueError(
            f"Invalid decision: {decision}. Must be one of {_VALID_DECISIONS}"
        )

    run_dir = _run_path(run_id, base_dir, create=False)
    if not run_dir.exists():
        raise FileNotFoundError(f"Run directory not found: {run_dir}")

    state = _load_state(run_dir)
    if state is None:
        raise ValueError(f"state.json missing or corrupt in {run_dir}")

    if state.get("status") != "human_required":
        raise ValueError(
            f"Run {run_id} is not paused for human review "
            f"(current status: {state.get('status', 'unknown')})"
        )

    # Apply decision (with persist to decision audit trail)
    # A16B: scope audit to run's decision_base_dir
    decision_base_dir = state.get("decision_base_dir", "") or None
    updated_state = apply_human_decision(
        state=state,
        decision=decision,
        note=note,
        reviewer_id=reviewer_id,
        persist=True,
        base_dir=decision_base_dir,
        require_reviewer=require_reviewer,
    )

    warnings: list[str] = []  # A16B

    # Re-invoke graph from checkpoint
    thread_id = f"paper-{run_id}"
    compiled = compile_paper_graph(thread_id)
    config = {"configurable": {"thread_id": thread_id}}

    try:
        result = compiled.invoke(updated_state, config)
    except Exception as e:
        updated_state["status"] = "error"
        updated_state["error_message"] = str(e)
        updated_state["updated_at"] = datetime.now(timezone.utc).isoformat()
        _save_state_safe(run_dir, updated_state)
        return {
            "run_id": run_id,
            "status": "error",
            "error": str(e),
            "state": redact_state(updated_state),
            "warnings": warnings,
        }

    # Merge result
    if isinstance(result, dict):
        updated_state.update(result)
    elif hasattr(result, "model_dump"):
        updated_state.update(result.model_dump())

    updated_state["updated_at"] = datetime.now(timezone.utc).isoformat()
    _save_state_safe(run_dir, updated_state)

    return {
        "run_id": run_id,
        "status": updated_state.get("status", "unknown"),
        "state": redact_state(updated_state),
        "warnings": warnings,
    }


def get_paper_run_status(
    run_id: str,
    base_dir: str | None = None,
) -> dict[str, Any] | None:
    """Read the current status of a paper run.

    Args:
        run_id: The run identifier.
        base_dir: Override base directory for runs.

    Returns:
        Dict with run_id, status, task_id, and key state fields,
        or None if run not found.
    """
    run_dir = _run_path(run_id, base_dir, create=False)
    state = _load_state(run_dir)
    if state is None:
        return None

    return {
        "run_id": run_id,
        "task_id": state.get("task_id", ""),
        "project_id": state.get("project_id", ""),
        "status": state.get("status", "unknown"),
        "acceptance_status": state.get("acceptance_status", ""),
        "blocking_count": state.get("blocking_count", 0),
        "human_required": state.get("human_required", False),
        "human_gate_decision": state.get("human_gate_decision", ""),
        "reviewer_id": state.get("reviewer_id", ""),
        "decision_round": state.get("decision_round", 0),
        "executed_nodes": state.get("executed_nodes", []),
        "error_message": state.get("error_message", ""),
        "created_at": state.get("created_at", ""),
        "updated_at": state.get("updated_at", ""),
    }


# ---------------------------------------------------------------------------
# Human gate artifact
# ---------------------------------------------------------------------------

def write_human_gate_artifact(
    run_id: str,
    state: dict[str, Any],
    base_dir: str | None = None,
) -> str:
    """Write paper-human-gate.md to the run directory.

    Generates a human-readable artifact summarizing the review results
    and providing resume instructions.

    Args:
        run_id: The run identifier.
        state: Current workflow state.
        base_dir: Override base directory.

    Returns:
        Path to the generated artifact file.
    """
    run_dir = _run_path(run_id, base_dir)
    artifact_path = run_dir / _GATE_ARTIFACT

    acceptance = state.get("acceptance_result", {})
    acceptance_status = state.get("acceptance_status", acceptance.get("status", ""))
    blocking = state.get("blocking_count", 0)
    non_blocking = state.get("non_blocking_count", 0)
    all_issues = state.get("all_review_issues", [])

    lines = [
        f"# Paper Human Gate — {run_id}",
        "",
        f"**Task**: {state.get('task_id', 'N/A')}",
        f"**Project**: {state.get('project_id', 'N/A')}",
        f"**Acceptance Status**: `{acceptance_status}`",
        f"**Blocking Issues**: {blocking}",
        f"**Non-blocking Issues**: {non_blocking}",
        f"**Diagnosis Source**: {state.get('diagnosis_source', 'N/A')}",
        f"**Status**: `{state.get('status', 'unknown')}`",
        f"**Time**: {datetime.now(timezone.utc).isoformat()}",
        "",
        "---",
        "",
        "## Review Summary",
        "",
    ]

    if all_issues:
        for i, issue in enumerate(all_issues[:20], 1):
            sev = issue.get("severity", "unknown")
            itype = issue.get("issue_type", "unknown")
            desc = issue.get("description", issue.get("message", "No description"))
            safe_desc = _redact_sensitive_text(desc, state)
            lines.append(f"{i}. **[{sev}]** ({itype}) {safe_desc[:200]}")
        if len(all_issues) > 20:
            lines.append(f"\n... and {len(all_issues) - 20} more issues")
    else:
        lines.append("No issues found.")

    # Ledger summary
    ledger = state.get("ledger_summary", {})
    if ledger and ledger.get("total", 0) > 0:
        lines.extend([
            "",
            "---",
            "",
            "## Ledger Summary",
            "",
            f"- Total issues in ledger: {ledger.get('total', 0)}",
            f"- Open: {ledger.get('open', 0)}",
            f"- Blocking: {ledger.get('blocking', 0)}",
        ])

    # Resume instructions
    lines.extend([
        "",
        "---",
        "",
        "## Resume Instructions",
        "",
        "To approve or reject this review, call:",
        "",
        "```python",
        "from ai_workflow_hub.context_layer.adapters.paper_runtime import resume_paper_run",
        "",
        f'resume_paper_run(',
        f'    run_id="{run_id}",',
        f'    decision="approved",  # or "rejected"',
        f'    reviewer_id="your-email@example.com",',
        f'    note="Reason for decision",',
        f')',
        "```",
        "",
        "Or via CLI:",
        "",
        "```bash",
        f'aihub paper resume --run-id {run_id} --decision approved --reviewer "your-email"',
        "```",
    ])

    artifact_path.write_text("\n".join(lines), encoding="utf-8")
    return str(artifact_path)


# ---------------------------------------------------------------------------
# Daemon integration
# ---------------------------------------------------------------------------

def dispatch_paper_task(task: dict[str, Any]) -> dict[str, Any]:
    """Dispatch a paper task through the runtime (A16B: with status update).

    Called by daemon._execute_one_task when workflow_type == "paper".
    After execution, updates task_queue with the final status.

    Args:
        task: Task dict from task_queue with at least id, project_id.

    Returns:
        Dict with run_id, final status, and task_queue_update result.
    """
    from ...task_queue import mark_task_finished

    task_id = task.get("id", "")
    project_id = task.get("project_id", "")

    # Create run
    run_info = create_paper_run(
        task_id=task_id,
        project_id=project_id,
    )
    run_id = run_info["run_id"]

    # Execute
    result = execute_paper_run(run_id)
    final_status = result.get("status", "unknown")

    # A16B: Map paper status to task_queue status and update
    status_map = {
        "completed": "passed",
        "human_required": "human_required",
        "blocked": "blocked",
        "error": "failed",
    }
    tq_status = status_map.get(final_status, "failed")
    tq_ok = mark_task_finished(task_id, tq_status, run_id=run_id)

    return {
        "run_id": run_id,
        "status": final_status,
        "gate_artifact": result.get("gate_artifact", ""),
        "task_queue_updated": tq_ok,
        "task_queue_status": tq_status,
    }
