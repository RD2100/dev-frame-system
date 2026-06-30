"""Human-gated task proposals (M8/MCP Phase 2).

An AI may PROPOSE a coding task (a goal for a project). Staging and approving a
proposal never runs an executor and never spends tokens: approval only promotes
the proposal to ``approved`` (a queued intent). Actually running it — which
spends tokens — stays the existing, separate human execution gate
(`/actions/execute` confirm / `devframe go ... --execute`). This module owns only
the proposal store + lifecycle; it never executes anything.
"""
from __future__ import annotations

import json
import os
import re
import secrets
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_REQUEST_ID_RE = re.compile(r"^tk-[0-9a-f]{16}$")
_MAX_GOAL_LEN = 4000


class TaskProposalError(Exception):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _dir(runtime_dir: str | Path | None) -> Path:
    from .backup_guard import default_runtime_dir

    base = Path(runtime_dir).resolve() if runtime_dir else default_runtime_dir()
    return base / "task-proposals"


def _safe_request_id(request_id: str) -> str:
    rid = str(request_id or "").strip()
    if not _REQUEST_ID_RE.match(rid):
        raise TaskProposalError("invalid task proposal id")
    return rid


def _atomic_write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.parent / (path.name + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8")
    os.replace(tmp, path)


def stage_task_proposal(
    runtime_dir: str | Path,
    project_id: str,
    goal: str,
    *,
    proposed_by: str = "",
    agents: int | None = None,
    target: str = "",
) -> dict[str, Any]:
    """Stage a pending, human-gated task proposal. Never runs or spends anything."""
    pid = str(project_id or "").strip()
    text = str(goal or "").strip()
    if not pid:
        raise TaskProposalError("projectId is required")
    if not text:
        raise TaskProposalError("goal is required")
    if len(text) > _MAX_GOAL_LEN:
        raise TaskProposalError(f"goal exceeds max length ({len(text)} > {_MAX_GOAL_LEN})")
    request_id = "tk-" + secrets.token_hex(8)
    proposal = {
        "request_id": request_id,
        "status": "pending",
        "project_id": pid,
        "goal": text,
        "proposed_by": str(proposed_by or ""),
        "agents": int(agents) if isinstance(agents, int) and agents > 0 else None,
        "target": str(target or ""),
        "staged_at": _now(),
    }
    _atomic_write(_dir(runtime_dir) / f"{request_id}.json", proposal)
    return {"request_id": request_id, "project_id": pid, "goal": text, "status": "pending"}


def load_task_proposal(runtime_dir: str | Path, request_id: str) -> dict[str, Any] | None:
    rid = _safe_request_id(request_id)
    path = _dir(runtime_dir) / f"{rid}.json"
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def list_pending_task_proposals(runtime_dir: str | Path) -> list[dict[str, Any]]:
    directory = _dir(runtime_dir)
    if not directory.is_dir():
        return []
    pending: list[dict[str, Any]] = []
    for path in sorted(directory.glob("tk-*.json")):
        try:
            proposal = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if str(proposal.get("status") or "") != "pending":
            continue
        pending.append({
            "request_id": proposal.get("request_id"),
            "project_id": proposal.get("project_id"),
            "goal": proposal.get("goal"),
            "proposed_by": proposal.get("proposed_by"),
            "staged_at": proposal.get("staged_at"),
        })
    return pending


def resolve_task_proposal(runtime_dir: str | Path, request_id: str, decision: str) -> dict[str, Any]:
    """Approve (promote to queued, NO execution/spend) or reject a task proposal."""
    rid = _safe_request_id(request_id)
    proposal = load_task_proposal(runtime_dir, rid)
    if proposal is None:
        raise TaskProposalError("task proposal not found")
    if str(proposal.get("status") or "") != "pending":
        return {"request_id": rid, "approved": False, "already_resolved": True, "status": proposal.get("status")}
    if decision == "reject":
        proposal["status"] = "rejected"
    elif decision == "approve":
        # Approval is a queued intent only. It does NOT run an executor or spend
        # tokens — that remains the existing human execution gate.
        proposal["status"] = "approved"
    else:
        raise TaskProposalError(f"invalid decision: {decision}")
    proposal["resolved_at"] = _now()
    _atomic_write(_dir(runtime_dir) / f"{rid}.json", proposal)
    return {
        "request_id": rid,
        "approved": proposal["status"] == "approved",
        "status": proposal["status"],
        "project_id": proposal.get("project_id"),
        "goal": proposal.get("goal"),
        "ran": False,
        "spent_tokens": False,
        "next_step": (
            "Approved as a queued task. To actually run it (which spends tokens), "
            "use the existing human execution gate: devframe go <project> \"<goal>\" --execute "
            "or the /actions/execute confirm step."
        ) if proposal["status"] == "approved" else "",
    }
