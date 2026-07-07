"""Real multi-agent team runtime objects (M1, slices 1-2).

Turns the Event Log and Message Bus from values *synthesized at read time* into
real, durable, recorded-at-runtime facts. When agents actually execute, the
controller records team events (task created, claimed, result/handoff) to a
dedicated append-only JSONL journal kept outside the repository, reusing the
same persistence shape and outside-repo safety guard as
`control_plane/runtime_store.py`.

Scope (recon-receipt-team-runtime.md): Event Log + Message Bus + a minimal Task
lifecycle. Agent Registry, Evidence Store, Review Gate, and Conflict Control
stay projected for now and are recorded in the receipt as deferred.

Design: this module is executor-agnostic. It records *what the team did*, not how
any one executor works. The read side (`build_team_runtime_view`) folds recorded
events into the schema shapes already defined for `team_message` / `team_event`.
"""
from __future__ import annotations

import json
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .backup_guard import default_runtime_dir, is_inside

TEAM_EVENTS_FILE = "team-events.jsonl"


@dataclass
class TeamEvent:
    """A recorded team fact. Durable, timestamped, append-only."""

    event_type: str
    run_id: str
    agent_id: str
    payload: dict[str, Any] = field(default_factory=dict)
    timestamp: str = ""
    event_id: str = ""

    def __post_init__(self) -> None:
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()
        if not self.event_id:
            self.event_id = f"{_slug(self.run_id)}-{_slug(self.agent_id)}-{int(time.time() * 1000)}-{uuid.uuid4().hex[:6]}"


class TeamRuntime:
    """Append-only recorder for real team events.

    Thread-safe: `_execute_parallel` runs agent groups in parallel threads and
    shares one TeamRuntime, so appends are serialized with an internal lock.
    """

    def __init__(self, runtime_dir: str | Path | None = None,
                 repo_root: str | Path | None = None) -> None:
        self.runtime_dir = Path(runtime_dir).resolve() if runtime_dir else default_runtime_dir()
        self.repo_root = Path(repo_root).resolve() if repo_root else None
        self.path = self.runtime_dir / TEAM_EVENTS_FILE
        self._lock = threading.Lock()

    def _append(self, event: TeamEvent) -> str:
        if self.repo_root and is_inside(self.runtime_dir, self.repo_root):
            raise ValueError("Team runtime journal must not be inside the public repository.")
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(asdict(event), ensure_ascii=True) + "\n")
        return event.event_id

    def record_task_created(self, run_id: str, agent_id: str, *,
                            project_id: str = "", shard_index: int = 0,
                            shard_count: int = 0, targets: list[str] | None = None) -> str:
        return self._append(TeamEvent(
            event_type="task_created",
            run_id=run_id,
            agent_id=agent_id,
            payload={
                "project_id": project_id,
                "shard_index": shard_index,
                "shard_count": shard_count,
                "targets": list(targets or []),
            },
        ))

    def record_task_claimed(self, run_id: str, agent_id: str) -> str:
        return self._append(TeamEvent(
            event_type="task_claimed",
            run_id=run_id,
            agent_id=agent_id,
            payload={},
        ))

    def record_result(self, run_id: str, agent_id: str, *, status: str,
                      report_path: str = "", isolated: bool = False) -> str:
        event_id = self._append(TeamEvent(
            event_type="task_result",
            run_id=run_id,
            agent_id=agent_id,
            payload={
                "status": status,
                "report_present": bool(report_path),
                "report_path": str(report_path or ""),
                "isolated": bool(isolated),
            },
        ))
        if report_path:
            self.record_evidence_ref(
                run_id,
                agent_id,
                ref_type="report",
                ref_path=report_path,
                source_event_id=event_id,
            )
        return event_id

    def record_evidence_ref(self, run_id: str, agent_id: str, *,
                            ref_type: str, ref_path: str,
                            source_event_id: str = "") -> str:
        """Record an explicit artifact/evidence reference produced by an agent."""
        return self._append(TeamEvent(
            event_type="evidence_ref",
            run_id=run_id,
            agent_id=agent_id,
            payload={
                "ref_type": str(ref_type or "artifact"),
                "ref_path": str(ref_path or ""),
                "source_event_id": str(source_event_id or ""),
            },
        ))

    def record_workflow_event(self, run_id: str, *, phase: str, status: str,
                              role: str = "coordinator", summary: str = "") -> str:
        """Record a workflow phase transition or controller decision.

        Used by the M3 workflow engine to make the multi-phase collaboration a
        real recorded fact (plan -> execute -> review -> verdict), reusing the
        same durable journal as the M1 task events.
        """
        return self._append(TeamEvent(
            event_type="workflow_event",
            run_id=run_id,
            agent_id=role,
            payload={
                "phase": str(phase),
                "status": str(status),
                "role": str(role),
                "summary": str(summary),
            },
        ))

    def read_all(self) -> list[dict[str, Any]]:
        return _read_team_events(self.path)


def _read_team_events(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    events: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            stripped = line.strip()
            if not stripped:
                continue
            try:
                events.append(json.loads(stripped))
            except json.JSONDecodeError:
                continue
    return events


def _slug(value: object) -> str:
    text = "".join(
        ch if (ch.isalnum() or ch == "-") else "-"
        for ch in str(value or "").strip().lower()
    ).strip("-")
    while "--" in text:
        text = text.replace("--", "-")
    return text or "x"


def build_team_runtime_view(runtime_dir: str | Path | None = None) -> dict[str, list[dict[str, Any]]]:
    """Fold recorded team events into schema-shaped team objects.

    Returns real, recorded team objects (distinct from the read-time projection),
    using the `team_message`, `team_event`, `team_conflict`, and `team_gate`
    shapes from the visual control plane schema. Slice 1 made message_bus and
    event_log real; slice 2 additionally derives conflict_control (file ownership
    from each task's recorded targets) and review_gates (acceptance facts from
    each recorded task result) from the SAME durable events — no extra recording.
    Empty when no run has recorded events, so callers can extend the projected
    lists without changing default behavior.
    """
    empty = {"message_bus": [], "event_log": [], "conflict_control": [], "review_gates": [],
             "agent_registry": [], "task_board": [], "evidence_store": []}
    if not runtime_dir:
        return empty
    path = Path(runtime_dir) / TEAM_EVENTS_FILE
    records = _read_team_events(path)
    message_bus: list[dict[str, Any]] = []
    event_log: list[dict[str, Any]] = []
    conflict_control: list[dict[str, Any]] = []
    review_gates: list[dict[str, Any]] = []
    evidence_store: list[dict[str, Any]] = []
    # Real Agent Registry + Task Board, derived from the SAME recorded events
    # (no extra recording): a task per (run, agent) with a created->claimed->result
    # lifecycle, and an agent per participant with its latest recorded status.
    tasks_by_key: dict[tuple[str, str], dict[str, Any]] = {}
    agents_by_id: dict[str, dict[str, Any]] = {}
    evidence_keys: set[tuple[str, str]] = set()
    _role_words = {"controller", "coordinator", "reviewer", "planner", "executor"}
    explicit_evidence_keys = {
        (
            _slug(record.get("run_id")),
            str((record.get("payload") if isinstance(record.get("payload"), dict) else {}).get("ref_path") or ""),
        )
        for record in records
        if isinstance(record, dict) and str(record.get("event_type") or "") == "evidence_ref"
    }

    def _touch_agent(agent: str, status: str) -> None:
        if not agent:
            return
        record = agents_by_id.get(agent)
        if record is None:
            agents_by_id[agent] = {
                "agent_id": agent,
                "role": agent if agent in _role_words else "worker",
                "binding_id": "",
                "status": status,
                "session_ids": [],
            }
        else:
            record["status"] = status

    seen_conflicts: set[tuple[str, str]] = set()
    for record in records:
        if not isinstance(record, dict):
            continue
        event_type = str(record.get("event_type") or "")
        run_id = _slug(record.get("run_id"))
        agent_id = _slug(record.get("agent_id"))
        event_id = _slug(record.get("event_id"))
        payload = record.get("payload") if isinstance(record.get("payload"), dict) else {}
        if not event_id or not run_id:
            continue
        if event_type == "task_created":
            shard_index = payload.get("shard_index", "?")
            shard_count = payload.get("shard_count", "?")
            targets = payload.get("targets") if isinstance(payload.get("targets"), list) else []
            # Real Task Board entry + Agent Registry entry for this task.
            task_key = (run_id, agent_id)
            tasks_by_key[task_key] = {
                "task_id": _slug(f"team-task-{run_id}-{agent_id}"),
                "type": "go-run",
                "project_id": str(payload.get("project_id") or ""),
                "status": "created",
                "agent_ids": [agent_id] if agent_id else [],
                "session_ids": [],
                "target_files": [str(t) for t in targets if str(t)],
            }
            _touch_agent(agent_id, "assigned")
            event_log.append({
                "event_id": f"team-{event_id}",
                "kind": "task-created",
                "run_id": run_id,
                "summary": f"Task created for {agent_id} (shard {shard_index}/{shard_count}) in run {run_id}.",
            })
            message_bus.append({
                "message_id": f"team-{event_id}",
                "from_role": "coordinator",
                "to_role": agent_id or "worker",
                "kind": "task-assign",
                "run_id": run_id,
                "summary": f"Coordinator assigned shard {shard_index}/{shard_count} to {agent_id}.",
            })
            # Real Conflict Control: each recorded target is owned by this agent
            # for this run. Deduplicate so re-runs do not double-list a file.
            for target in targets:
                file_path = str(target)
                key = (run_id, file_path)
                if not file_path or key in seen_conflicts:
                    continue
                seen_conflicts.add(key)
                conflict_control.append({
                    "file_path": file_path,
                    "owner_run_id": run_id,
                    "owner_agent_id": agent_id,
                    "file_kind": "target",
                })
        elif event_type == "task_claimed":
            task = tasks_by_key.get((run_id, agent_id))
            if task is not None:
                task["status"] = "claimed"
            _touch_agent(agent_id, "working")
            event_log.append({
                "event_id": f"team-{event_id}",
                "kind": "task-claimed",
                "run_id": run_id,
                "summary": f"{agent_id} claimed its task in run {run_id}.",
            })
            message_bus.append({
                "message_id": f"team-{event_id}",
                "from_role": agent_id or "worker",
                "to_role": "coordinator",
                "kind": "claim",
                "run_id": run_id,
                "summary": f"{agent_id} -> coordinator: claimed task, working…",
            })
        elif event_type == "task_result":
            status = str(payload.get("status") or "unknown")
            task = tasks_by_key.get((run_id, agent_id))
            if task is not None:
                task["status"] = _task_status(status)
            _touch_agent(agent_id, _task_status(status))
            event_log.append({
                "event_id": f"team-{event_id}",
                "kind": "task-result",
                "run_id": run_id,
                "summary": f"{agent_id} reported {status} in run {run_id}.",
            })
            message_bus.append({
                "message_id": f"team-{event_id}",
                "from_role": agent_id or "worker",
                "to_role": "coordinator",
                "kind": "result",
                "run_id": run_id,
                "summary": f"{agent_id} -> coordinator: {status}.",
            })
            # Worker task results are execution outcomes only. A successful
            # worker result opens the review gate but cannot pass it.
            review_gates.append({
                "gate_id": f"team-acceptance-{event_id}",
                "kind": "acceptance",
                "status": _review_status(status),
                "reason": _review_reason(agent_id, run_id, status),
                "run_id": run_id,
            })
            # Real Evidence Store: a recorded evidence ref when the result
            # carried a report path.
            report_path = str(payload.get("report_path") or "")
            if report_path and (run_id, report_path) not in explicit_evidence_keys:
                evidence_keys.add((run_id, report_path))
                evidence_store.append({
                    "evidence_id": f"team-evidence-{event_id}",
                    "run_id": run_id,
                    "ref_type": "report",
                    "ref_path": report_path,
                })
        elif event_type == "evidence_ref":
            ref_path = str(payload.get("ref_path") or "")
            if ref_path:
                if (run_id, ref_path) not in evidence_keys:
                    evidence_keys.add((run_id, ref_path))
                    source_event_id = str(payload.get("source_event_id") or "")
                    evidence_id = _slug(source_event_id) if source_event_id else event_id
                    evidence_store.append({
                        "evidence_id": f"team-evidence-{evidence_id}",
                        "run_id": run_id,
                        "ref_type": str(payload.get("ref_type") or "artifact"),
                        "ref_path": ref_path,
                    })
                event_log.append({
                    "event_id": f"team-{event_id}",
                    "kind": "evidence-ref",
                    "run_id": run_id,
                    "summary": f"{agent_id} recorded evidence {ref_path} in run {run_id}.",
                })
        elif event_type == "workflow_event":
            phase = str(payload.get("phase") or "phase")
            status = str(payload.get("status") or "")
            role = _slug(payload.get("role")) or "coordinator"
            _touch_agent(role, "active")
            summary = str(payload.get("summary") or f"{role} {phase}: {status}")
            event_log.append({
                "event_id": f"team-{event_id}",
                "kind": f"workflow-{_slug(phase)}",
                "run_id": run_id,
                "summary": summary,
            })
            # The controller's final decision is also a message to the team.
            if _slug(phase) in {"review", "decide", "verdict"}:
                message_bus.append({
                    "message_id": f"team-{event_id}",
                    "from_role": role,
                    "to_role": "team",
                    "kind": "workflow-verdict",
                    "run_id": run_id,
                    "summary": summary,
                })
    return {
        "message_bus": message_bus,
        "event_log": event_log,
        "conflict_control": conflict_control,
        "review_gates": review_gates,
        "agent_registry": list(agents_by_id.values()),
        "task_board": list(tasks_by_key.values()),
        "evidence_store": evidence_store,
    }


def _task_status(status: str) -> str:
    normalized = str(status or "").strip().lower()
    if normalized in {"pass", "passed", "completed", "verified", "done"}:
        return "completed"
    if normalized in {"fail", "failed", "error"}:
        return "failed"
    if normalized in {"blocked"}:
        return "blocked"
    return normalized or "unknown"


def _review_status(status: str) -> str:
    normalized = str(status or "").strip().lower()
    if normalized in {"pass", "passed", "completed", "verified"}:
        return "open"
    if normalized in {"fail", "failed", "error"}:
        return "failed"
    if normalized in {"blocked"}:
        return "blocked"
    return "open"


def _review_reason(agent_id: str, run_id: str, status: str) -> str:
    normalized = str(status or "").strip().lower()
    if normalized in {"pass", "passed", "completed", "verified"}:
        return (
            f"Recorded worker result for {agent_id} in run {run_id}: {status}; "
            "independent review is still required."
        )
    return f"Recorded result for {agent_id} in run {run_id}: {status}."
