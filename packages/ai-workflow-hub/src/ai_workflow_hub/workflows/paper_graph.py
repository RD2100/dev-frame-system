"""paper_graph.py — A10/A12 LangGraph StateGraph for Paper Review Workflow.

Defines a multi-node state graph for paper paragraph review:

  start → diagnosis → acceptance_gate → ledger_ingest → route:
    blocked          → finalizer → END
    human_required   → human_gate → END (pause)
    other statuses   → finalizer → END

Design:
  - Follows coding_graph.py patterns: _wrap(), conditional edges, MemorySaver
  - State is PaperWorkflowState (Pydantic BaseModel)
  - Nodes are plain functions: dict → dict (partial update)
  - diagnosis_node consumes precomputed review issues
  - acceptance_gate_node uses A8 compute_acceptance (pure)
  - ledger_ingest_node (A12) persists issues to paper_issue_ledger
  - human_gate_node sets triggered flag (END = pause for human)
  - finalizer_node computes terminal status + ledger summary

Usage:
    compiled = compile_paper_graph("thread-1")
    result = compiled.invoke(initial_state, {"configurable": {"thread_id": "thread-1"}})
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver

from .paper_workflow_state import PaperWorkflowState
from ..context_layer.adapters.paper_acceptance_gate import (
    compute_acceptance,
    validate_acceptance_result,
)
from ..context_layer.adapters.paper_issue_ledger import (
    ingest_from_acceptance_result,
    ledger_summary as get_ledger_summary,
    build_prompt_context as get_ledger_context,
)
from ..context_layer.adapters.paper_decision_audit import (
    record_decision,
    read_decision_record,
    log_decision_audit,
    sanitize_task_id,
    is_decision_stale,
    get_decision_count,
)


# ---------------------------------------------------------------------------
# Node functions
# ---------------------------------------------------------------------------

def diagnosis_node(state: dict[str, Any]) -> dict[str, Any]:
    """Collect precomputed paper review issues.

    Returns:
        Partial state update with diagnosis results.
    """
    update: dict[str, Any] = {
        "status": "running",
        "executed_nodes": _append_node(state, "diagnosis_node"),
    }

    try:
        existing = list(state.get("all_review_issues", []))
        expr = list(state.get("expression_issues", []))
        para = list(state.get("paragraph_issues", []))
        update["all_review_issues"] = existing or (expr + para)
        update["diagnosis_source"] = state.get("diagnosis_source") or "deterministic_gate"

    except Exception as e:
        update["diagnosis_error"] = str(e)
        update["diagnosis_source"] = "unavailable"

    return update


def acceptance_gate_node(state: dict[str, Any]) -> dict[str, Any]:
    """Run the Paper Acceptance Gate on collected issues.

    Skipped if diagnosis_node already populated acceptance_result (offline/live modes).
    For mock mode, computes acceptance from all_review_issues.

    Returns:
        Partial state update with acceptance result.
    """
    # If acceptance already computed (offline/live diagnosis), skip re-computation
    existing = state.get("acceptance_result")
    if existing and existing.get("status"):
        return {
            "executed_nodes": _append_node(state, "acceptance_gate_node"),
        }

    issues = state.get("all_review_issues", [])
    # Only pass privacy_attestation if it contains actual attestation data.
    # An empty dict {} would trigger privacy violation in compute_acceptance
    # because all required keys resolve to None.
    pa = state.get("privacy_attestation")
    if pa is not None and not pa:
        pa = None
    result = compute_acceptance(
        issues=issues,
        reviewer=state.get("diagnosis_source") or "deterministic_gate",
        evidence_pack_ref=state.get("evidence_pack_ref", ""),
        privacy_attestation=pa,
    )

    return {
        "acceptance_result": result,
        "acceptance_status": result.get("status", ""),
        "blocking_count": len(result.get("blocking_issues", [])),
        "non_blocking_count": len(result.get("non_blocking_issues", [])),
        "executed_nodes": _append_node(state, "acceptance_gate_node"),
    }


def ledger_ingest_node(state: dict[str, Any]) -> dict[str, Any]:
    """Persist issues from acceptance_result into the Paper Issue Ledger (A12).

    Ingests both blocking and non-blocking issues from the acceptance result.
    Uses task_id as the ledger key and ledger_dir for storage location.

    Returns:
        Partial state update with ledger ingestion results.
    """
    task_id = state.get("task_id", "")
    acceptance_result = state.get("acceptance_result", {})
    ledger_dir = state.get("ledger_dir", "") or None

    update: dict[str, Any] = {
        "executed_nodes": _append_node(state, "ledger_ingest_node"),
    }

    # Only ingest if we have a task_id and acceptance_result with issues
    if not task_id or not acceptance_result.get("status"):
        update["ledger_issue_count"] = 0
        update["ledger_summary"] = {}
        return update

    try:
        added = ingest_from_acceptance_result(
            task_id=task_id,
            acceptance_result=acceptance_result,
            ledger_dir=ledger_dir,
        )
        summary = get_ledger_summary(task_id=task_id, ledger_dir=ledger_dir)
        update["ledger_issue_count"] = added
        update["ledger_summary"] = summary
    except Exception as e:
        update["ledger_issue_count"] = 0
        update["ledger_summary"] = {"error": str(e)}

    return update


def human_gate_node(state: dict[str, Any]) -> dict[str, Any]:
    """Mark that human review is required and pause the workflow (A14: audit-aware).

    On first execution:
      - Sets human_gate_triggered = True, status = human_required
      - Graph pauses at END after this node

    On resume (after apply_human_decision):
      - Checks human_gate_decision field
      - If "approved": clears human_required, populates audit fields, routes to finalizer
      - If "rejected": sets status to rejected, populates audit fields

    Returns:
        Partial state update for human gate handling.
    """
    decision = state.get("human_gate_decision", "")

    # Resume path: decision already made
    if decision == "approved":
        update: dict[str, Any] = {
            "human_required": False,
            "human_gate_triggered": True,
            "human_gate_decision": "approved",
            "status": "running",
            "executed_nodes": _append_node(state, "human_gate_node"),
        }
        # A14: populate audit fields from state or decision record
        _populate_audit_fields(state, update)
        return update

    if decision == "rejected":
        update = {
            "human_required": False,
            "human_gate_triggered": True,
            "human_gate_decision": "rejected",
            "status": "rejected",
            "executed_nodes": _append_node(state, "human_gate_node"),
        }
        _populate_audit_fields(state, update)
        return update

    # First-time path: pause for human intervention
    update_pause: dict[str, Any] = {
        "human_required": True,
        "human_gate_triggered": True,
        "human_gate_decision": "pending",
        "status": "human_required",
        "executed_nodes": _append_node(state, "human_gate_node"),
    }

    # A16: Write human gate artifact to run_dir if available
    run_dir = state.get("run_dir", "")
    run_id = state.get("run_id", "")
    if run_dir and run_id:
        try:
            from pathlib import Path as _P
            artifact = _P(run_dir) / "paper-human-gate.md"
            _write_gate_artifact_inline(artifact, run_id, state)
        except Exception:
            pass  # artifact is best-effort, not blocking

    return update_pause


def _populate_audit_fields(
    state: dict[str, Any],
    update: dict[str, Any],
) -> None:
    """Populate A14/A15 audit fields in update from state or decision record (in-place)."""
    # Prefer fields already in state (set by apply_human_decision)
    reviewer_id = state.get("reviewer_id", "")
    decision_ts = state.get("decision_timestamp", "")
    decision_note = state.get("decision_note", "")
    decision_round = state.get("decision_round", 0)

    # Fallback: try reading from persisted decision record
    task_id = state.get("task_id", "")
    base_dir = state.get("decision_base_dir", "") or None
    if not reviewer_id and task_id:
        try:
            record = read_decision_record(task_id=task_id, base_dir=base_dir)
            if record:
                reviewer_id = reviewer_id or record.get("reviewer_id", "")
                decision_ts = decision_ts or record.get("timestamp", "")
                decision_note = decision_note or record.get("note", "")
                decision_round = decision_round or record.get("round", 0)
        except Exception:
            pass

    update["reviewer_id"] = reviewer_id
    update["decision_timestamp"] = decision_ts
    update["decision_note"] = decision_note
    update["decision_round"] = decision_round


def apply_human_decision(
    state: dict[str, Any],
    decision: str,
    note: str = "",
    reviewer_id: str = "",
    persist: bool = False,
    base_dir: str | None = None,
    require_reviewer: bool = False,
) -> dict[str, Any]:
    """Apply a human decision to the workflow state for resume (A15: hardened).

    Call this function before re-invoking the graph to resume from
    the human_gate pause point.

    Args:
        state: Current workflow state (from checkpoint or dict).
        decision: "approved" or "rejected".
        note: Optional note explaining the decision.
        reviewer_id: Who made the decision (email, username, or role).
        persist: If True, write decision record to disk + emit audit_log.
        base_dir: Override directory for decision file persistence.
        require_reviewer: If True, raise ValueError when reviewer_id is empty.

    Returns:
        Updated state dict ready for graph resume.

    Raises:
        ValueError: If decision is invalid or reviewer_id required but empty.
    """
    if decision not in ("approved", "rejected"):
        raise ValueError(
            f"Invalid decision: {decision}. Must be 'approved' or 'rejected'."
        )
    if require_reviewer and not reviewer_id.strip():
        raise ValueError(
            "reviewer_id is required when require_reviewer=True"
        )

    if isinstance(state, dict):
        state_dict = dict(state)
    elif hasattr(state, "model_dump"):
        state_dict = state.model_dump()
    else:
        state_dict = dict(state)

    from datetime import datetime, timezone

    now = datetime.now(timezone.utc).isoformat()

    state_dict["human_gate_decision"] = decision
    state_dict["reviewer_id"] = reviewer_id
    state_dict["decision_timestamp"] = now
    state_dict["decision_note"] = note
    if base_dir:
        state_dict["decision_base_dir"] = base_dir
    if note:
        state_dict["error_message"] = f"Human decision: {decision}. {note}"

    # Persist to disk and emit audit log if requested
    if persist:
        task_id = state_dict.get("task_id", "")
        if task_id:
            try:
                rec = record_decision(
                    task_id=task_id,
                    decision=decision,
                    reviewer_id=reviewer_id,
                    note=note,
                    context={
                        "acceptance_status": state_dict.get("acceptance_status", ""),
                        "blocking_count": state_dict.get("blocking_count", 0),
                    },
                    base_dir=base_dir,
                    require_reviewer=require_reviewer,
                )
                state_dict["decision_round"] = rec.get("round", 1)
            except Exception:
                pass
            try:
                log_decision_audit(
                    task_id=task_id,
                    decision=decision,
                    reviewer_id=reviewer_id,
                    note=note,
                )
            except Exception:
                pass

    return state_dict


def paper_finalizer_node(state: dict[str, Any]) -> dict[str, Any]:
    """Compute the final workflow status from acceptance result.

    Determines terminal status based on acceptance_result and other state flags.
    Includes ledger summary and prompt context in the final state.
    Sets status and updated_at timestamp.

    Returns:
        Partial state update with final status and ledger data.
    """
    acceptance = state.get("acceptance_result", {})
    acceptance_status = acceptance.get("status", state.get("acceptance_status", ""))

    # Determine final status
    # If human gate was approved, treat human_required as resolved (A13)
    human_approved = state.get("human_gate_decision") == "approved"

    if acceptance_status == "blocked" or state.get("blocking_count", 0) > 0:
        status = "blocked"
    elif acceptance_status == "human_required" and not human_approved:
        status = "human_required"
    elif state.get("diagnosis_error") and not state.get("all_review_issues"):
        status = "error"
    else:
        status = "completed"

    update: dict[str, Any] = {
        "status": status,
        "acceptance_status": acceptance_status,
        "final_acceptance": (
            acceptance_status == "accepted"
            and status == "completed"
            and state.get("blocking_count", 0) == 0
        ),
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "executed_nodes": _append_node(state, "paper_finalizer_node"),
    }

    # Enrich with ledger data if available (A12)
    task_id = state.get("task_id", "")
    ledger_dir = state.get("ledger_dir", "") or None
    if task_id:
        try:
            summary = get_ledger_summary(task_id=task_id, ledger_dir=ledger_dir)
            if summary.get("total", 0) > 0:
                update["ledger_summary"] = summary
        except Exception:
            pass

    # A16/A16B: Persist final state to run_dir if available (with privacy redaction)
    run_dir = state.get("run_dir", "")
    if run_dir:
        try:
            import json as _json
            from pathlib import Path as _Path
            from ..context_layer.adapters.paper_runtime import redact_state
            rd = _Path(run_dir)
            if rd.exists():
                final = dict(state)
                final.update(update)
                redacted = redact_state(final)
                tmp = rd / "state.json.tmp"
                tmp.write_text(
                    _json.dumps(redacted, indent=2, ensure_ascii=False, default=str),
                    encoding="utf-8",
                )
                tmp.replace(rd / "state.json")
        except Exception:
            pass  # best-effort persistence

    return update


# ---------------------------------------------------------------------------
# Routing functions
# ---------------------------------------------------------------------------

def _route_after_ledger(state: dict[str, Any] | Any) -> str:
    """Route after ledger_ingest_node based on acceptance status.

    Returns:
        "finalizer" for terminal statuses (blocked, accepted, etc.)
        "human_gate" when human review is needed
    """
    s = _s(state)
    acceptance_status = s.get("acceptance_status", "")

    if acceptance_status == "blocked":
        return "finalizer"
    if acceptance_status == "human_required":
        return "human_gate"
    # accepted, accepted_with_limitation, needs_more_evidence → finalizer
    return "finalizer"


def _route_after_human_gate(state: dict[str, Any] | Any) -> str:
    """Route after human_gate_node based on decision (A13).

    Returns:
        "finalizer" if approved (proceed to completion)
        "__end__" if pending (pause for human) or rejected
    """
    s = _s(state)
    decision = s.get("human_gate_decision", "")

    if decision == "approved":
        return "finalizer"
    # pending or rejected → END (pause or terminate)
    return "__end__"


# Backward-compatible alias (A10 name)
_route_after_acceptance = _route_after_ledger


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

def _s(state: dict[str, Any] | Any) -> dict[str, Any]:
    """Safe state unpack: PaperWorkflowState / dict → dict."""
    if hasattr(state, "model_dump"):
        return state.model_dump()
    if isinstance(state, dict):
        return state
    return {}


def _append_node(state: dict[str, Any], node_name: str) -> list[str]:
    """Append a node name to executed_nodes list (no duplicates for same name)."""
    executed = list(state.get("executed_nodes", []))
    if node_name not in executed:
        executed.append(node_name)
    return executed


def _write_gate_artifact_inline(
    artifact_path: Any,
    run_id: str,
    state: dict[str, Any],
) -> None:
    """Write a human gate artifact inline (A16, best-effort).

    Lightweight version that writes directly to the given path
    without depending on paper_runtime's directory management.
    """
    from pathlib import Path
    p = Path(artifact_path)

    acceptance_status = state.get("acceptance_status", "")
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
        f"**Status**: `{state.get('status', 'unknown')}`",
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
            lines.append(f"{i}. **[{sev}]** ({itype}) {desc[:200]}")
        if len(all_issues) > 20:
            lines.append(f"\n... and {len(all_issues) - 20} more issues")
    else:
        lines.append("No issues found.")

    lines.extend([
        "",
        "---",
        "",
        "## Resume Instructions",
        "",
        "```python",
        "from ai_workflow_hub.context_layer.adapters.paper_runtime import resume_paper_run",
        f'resume_paper_run(run_id="{run_id}", decision="approved", reviewer_id="...")',
        "```",
    ])

    p.write_text("\n".join(lines), encoding="utf-8")


def _wrap(fn):
    """Wrap node function for PaperWorkflowState / dict compatibility.

    Converts Pydantic model to dict before calling fn, then merges
    the result back into the state dict.
    """
    def wrapped(state: dict[str, Any] | PaperWorkflowState | Any) -> dict[str, Any]:
        if hasattr(state, "model_dump"):
            state_dict = state.model_dump()
        elif isinstance(state, dict):
            state_dict = state
        else:
            state_dict = dict(state) if state else {}
        result = fn(state_dict)
        state_dict.update(result)
        return state_dict
    return wrapped


# ---------------------------------------------------------------------------
# Graph construction
# ---------------------------------------------------------------------------

def create_paper_graph(checkpointer: MemorySaver | None = None) -> StateGraph:
    """Create the paper review workflow state graph.

    State machine (A12: ledger_ingest added after acceptance_gate):

    start → diagnosis → acceptance_gate → ledger_ingest → route:
      blocked          → finalizer → END
      human_required   → human_gate → END (pause for human)
      other statuses   → finalizer → END

    Args:
        checkpointer: Optional MemorySaver for state persistence.

    Returns:
        Configured StateGraph (not yet compiled).
    """
    graph = StateGraph(PaperWorkflowState)

    # Add nodes (A12: added ledger_ingest)
    graph.add_node("diagnosis", _wrap(diagnosis_node))
    graph.add_node("acceptance_gate", _wrap(acceptance_gate_node))
    graph.add_node("ledger_ingest", _wrap(ledger_ingest_node))
    graph.add_node("human_gate", _wrap(human_gate_node))
    graph.add_node("finalizer", _wrap(paper_finalizer_node))

    # Entry point
    graph.set_entry_point("diagnosis")

    # diagnosis → acceptance_gate (always)
    graph.add_edge("diagnosis", "acceptance_gate")

    # acceptance_gate → ledger_ingest (always)
    graph.add_edge("acceptance_gate", "ledger_ingest")

    # ledger_ingest → human_gate / finalizer (A12: route moved here)
    graph.add_conditional_edges(
        "ledger_ingest",
        _route_after_ledger,
        {
            "human_gate": "human_gate",
            "finalizer": "finalizer",
        },
    )

    # human_gate → finalizer (approved) / END (pending/rejected) (A13)
    graph.add_conditional_edges(
        "human_gate",
        _route_after_human_gate,
        {
            "finalizer": "finalizer",
            "__end__": END,
        },
    )

    # finalizer → END
    graph.add_edge("finalizer", END)

    return graph


def compile_paper_graph(thread_id: str = "default") -> Any:
    """Compile paper graph with MemorySaver checkpointer.

    Args:
        thread_id: Thread identifier for checkpointing.

    Returns:
        Compiled graph ready for .invoke() or .stream().
    """
    checkpointer = MemorySaver()
    graph = create_paper_graph(checkpointer)
    return graph.compile(checkpointer=checkpointer)
