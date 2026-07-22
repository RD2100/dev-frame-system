"""Truthful read-only team activity and starvation projection.

The projection folds facts already owned by ``TeamRuntime`` and the visual
control plane.  It never starts work, sends a wake message, or writes another
journal.  ``wake_required`` therefore means only that a caller can observe an
unacknowledged gated-READY item with no live worker/command owner.
"""
from __future__ import annotations

import hashlib
from typing import Any

from .team_runtime import TeamRuntime, build_team_runtime_view


_ACTIVE_WORKER_STATUSES = {
    "active",
    "assigned",
    "claimed",
    "dispatched",
    "executing",
    "in_progress",
    "running",
    "started",
    "starting",
    "working",
}
_ACTIVE_COMMAND_STATUSES = {"active", "executing", "running", "started", "starting"}
_TERMINAL_COMMAND_STATUSES = {"cancelled", "completed", "failed", "passed", "stopped"}
_CONTROLLER_ROLES = {"controller", "coordinator", "planner"}
_COMMAND_LIFECYCLE_ORDER = {
    "unknown": 0,
    "ready": 1,
    "starting": 2,
    "started": 2,
    "active": 2,
    "executing": 2,
    "running": 2,
    "cancelled": 3,
    "completed": 3,
    "failed": 3,
    "passed": 3,
    "stopped": 3,
}


def empty_activity_liveness() -> dict[str, Any]:
    """Return the stable empty shape used for legacy adapter input."""
    return {
        "state": "idle",
        "controller": {
            "worker_id": "controller",
            "status": "idle",
            "child_worker_ids": [],
        },
        "internal_workers": [],
        "visible_workers": [],
        "owned_commands": [],
        "ready": [],
        "gated_ready": [],
        "counts": {
            "internal_workers": 0,
            "visible_workers": 0,
            "active_workers": 0,
            "owned_commands": 0,
            "ready": 0,
            "gated_ready": 0,
        },
        "wake_required": False,
        "dedupe_key": "",
    }


def build_activity_liveness(
    runtime_dir: str,
    *,
    recorded_team: dict[str, Any] | None = None,
    visible_agents: list[dict[str, Any]] | None = None,
    visible_sessions: list[dict[str, Any]] | None = None,
    actions: list[dict[str, Any]] | None = None,
    action_runs: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Fold durable team/root-gate facts into one deterministic observation."""
    if not runtime_dir:
        return empty_activity_liveness()

    runtime = TeamRuntime(runtime_dir=runtime_dir)
    # The strict root-gate read fails closed on malformed journal history before
    # any liveness conclusion can be reported.
    root_gates = runtime.read_root_gate_requests()
    team = recorded_team if isinstance(recorded_team, dict) else build_team_runtime_view(runtime_dir)

    controller = _controller(
        team.get("agent_registry"),
        visible_agents,
    )
    controller_id = controller["worker_id"]
    internal_workers = _internal_workers(team, root_gates, controller_id)
    visible_workers = _visible_workers(visible_agents, visible_sessions, controller_id)
    owned_commands = _owned_commands(actions, action_runs)
    _attach_command_ids(internal_workers, visible_workers, owned_commands)

    ready = _ready_work(actions, root_gates)
    gated_ready = _gated_ready_work(root_gates)
    active_worker_ids = {
        worker["worker_id"]
        for worker in internal_workers + visible_workers
        if _is_active(worker.get("status"))
    }
    active_worker_ids.update(
        command["owner_id"]
        for command in owned_commands
        if _is_active_command(command.get("status")) and command["owner_id"]
    )
    acknowledged = any(
        isinstance(snapshot, dict) and snapshot.get("state") == "acknowledged"
        for snapshot in root_gates.values()
    )

    if active_worker_ids:
        state = "active"
    elif gated_ready:
        state = "gated_ready"
    elif ready:
        state = "ready"
    elif acknowledged:
        state = "acknowledged"
    else:
        state = "idle"

    wake_required = bool(gated_ready) and not active_worker_ids
    dedupe_key = _wake_dedupe_key(gated_ready) if wake_required else ""
    child_worker_ids = sorted({
        worker["worker_id"]
        for worker in internal_workers + visible_workers
        if worker["worker_id"]
    } | {
        command["owner_id"]
        for command in owned_commands
        if command["owner_id"] and command["owner_id"] != controller_id
    })
    return {
        "state": state,
        "controller": {
            "worker_id": controller_id,
            "status": controller["status"],
            "child_worker_ids": child_worker_ids,
        },
        "internal_workers": internal_workers,
        "visible_workers": visible_workers,
        "owned_commands": owned_commands,
        "ready": ready,
        "gated_ready": gated_ready,
        "counts": {
            "internal_workers": len(internal_workers),
            "visible_workers": len(visible_workers),
            "active_workers": len(active_worker_ids),
            "owned_commands": len(owned_commands),
            "ready": len(ready),
            "gated_ready": len(gated_ready),
        },
        "wake_required": wake_required,
        "dedupe_key": dedupe_key,
    }


def project_activity_liveness(value: object) -> dict[str, Any]:
    """Project the internal snake_case shape to the T3/MCP camelCase contract."""
    activity = value if isinstance(value, dict) else empty_activity_liveness()
    controller = activity.get("controller") if isinstance(activity.get("controller"), dict) else {}
    counts = activity.get("counts") if isinstance(activity.get("counts"), dict) else {}
    return {
        "state": _text(activity.get("state"), "idle"),
        "controller": {
            "workerId": _text(controller.get("worker_id"), "controller"),
            "status": _text(controller.get("status"), "idle"),
            "childWorkerIds": _strings(controller.get("child_worker_ids")),
        },
        "internalWorkers": _project_workers(activity.get("internal_workers")),
        "visibleWorkers": _project_workers(activity.get("visible_workers")),
        "ownedCommands": _project_commands(activity.get("owned_commands")),
        "ready": _project_work(activity.get("ready")),
        "gatedReady": _project_work(activity.get("gated_ready")),
        "counts": {
            "internalWorkers": _count(counts.get("internal_workers")),
            "visibleWorkers": _count(counts.get("visible_workers")),
            "activeWorkers": _count(counts.get("active_workers")),
            "ownedCommands": _count(counts.get("owned_commands")),
            "ready": _count(counts.get("ready")),
            "gatedReady": _count(counts.get("gated_ready")),
        },
        "wakeRequired": activity.get("wake_required") is True,
        "dedupeKey": _text(activity.get("dedupe_key"), ""),
    }


def _controller(
    recorded_agents: object,
    visible_agents: list[dict[str, Any]] | None,
) -> dict[str, str]:
    for candidates in (recorded_agents, visible_agents):
        if not isinstance(candidates, list):
            continue
        for candidate in candidates:
            if not isinstance(candidate, dict):
                continue
            role = _normalized(candidate.get("role"))
            if role in _CONTROLLER_ROLES:
                return {
                    "worker_id": _text(candidate.get("agent_id"), role),
                    "status": _text(candidate.get("status"), "idle"),
                }
    return {"worker_id": "controller", "status": "idle"}


def _internal_workers(
    team: dict[str, Any],
    root_gates: dict[str, dict[str, Any]],
    controller_id: str,
) -> list[dict[str, Any]]:
    workers: dict[str, dict[str, Any]] = {}
    agents = team.get("agent_registry")
    if isinstance(agents, list):
        for agent in agents:
            if not isinstance(agent, dict):
                continue
            worker_id = _text(agent.get("agent_id"), "")
            role = _text(agent.get("role"), "worker")
            if not worker_id or _normalized(role) in _CONTROLLER_ROLES:
                continue
            workers[worker_id] = _worker(
                worker_id,
                controller_id,
                role,
                _text(agent.get("status"), "idle"),
                set(),
            )

    for snapshot in root_gates.values():
        if not isinstance(snapshot, dict) or snapshot.get("state") != "dispatched":
            continue
        run_id = _text(snapshot.get("run_id"), "")
        for task_id in _strings(snapshot.get("dispatch_task_ids")):
            worker = workers.get(task_id)
            if worker is None:
                workers[task_id] = _worker(
                    task_id,
                    controller_id,
                    "worker",
                    "dispatched",
                    {run_id} if run_id else set(),
                )
            elif run_id and run_id not in worker["run_ids"]:
                worker["run_ids"].append(run_id)
                worker["run_ids"].sort()
    return [workers[key] for key in sorted(workers)]


def _visible_workers(
    agents: list[dict[str, Any]] | None,
    sessions: list[dict[str, Any]] | None,
    controller_id: str,
) -> list[dict[str, Any]]:
    workers: dict[str, dict[str, Any]] = {}
    for agent in agents or []:
        if not isinstance(agent, dict):
            continue
        worker_id = _text(agent.get("agent_id"), "")
        role = _text(agent.get("role"), "worker")
        if not worker_id or _normalized(role) in _CONTROLLER_ROLES:
            continue
        workers[worker_id] = _worker(
            worker_id,
            controller_id,
            role,
            _text(agent.get("status"), "idle"),
            set(),
        )
    for session in sessions or []:
        if not isinstance(session, dict):
            continue
        worker_id = _text(session.get("agent_id"), "") or _text(session.get("session_id"), "")
        role = _text(session.get("agent_role"), "worker")
        if not worker_id or _normalized(role) in _CONTROLLER_ROLES:
            continue
        run_id = _text(session.get("run_id"), "")
        existing = workers.get(worker_id)
        if existing is None:
            workers[worker_id] = _worker(
                worker_id,
                controller_id,
                role,
                _text(session.get("status"), "idle"),
                {run_id} if run_id else set(),
            )
            continue
        if run_id and run_id not in existing["run_ids"]:
            existing["run_ids"].append(run_id)
            existing["run_ids"].sort()
        session_status = _text(session.get("status"), "idle")
        if _is_active(session_status) and not _is_active(existing.get("status")):
            existing["status"] = session_status
    return [workers[key] for key in sorted(workers)]


def _worker(
    worker_id: str,
    parent_id: str,
    role: str,
    status: str,
    run_ids: set[str],
) -> dict[str, Any]:
    return {
        "worker_id": worker_id,
        "parent_id": parent_id,
        "role": role,
        "status": status,
        "run_ids": sorted(run_ids),
        "command_ids": [],
    }


def _owned_commands(
    actions: list[dict[str, Any]] | None,
    action_runs: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    commands: dict[str, dict[str, Any]] = {}
    actions_by_id: dict[str, dict[str, Any]] = {}
    for action in actions or []:
        if not isinstance(action, dict) or not _text(action.get("command"), ""):
            continue
        command_id = _text(action.get("action_id"), "")
        if not command_id:
            continue
        actions_by_id[command_id] = action

    run_snapshots: dict[str, tuple[tuple[int, str, int], dict[str, Any]]] = {}
    action_ids_with_runs: set[str] = set()
    for index, record in enumerate(action_runs or []):
        if not isinstance(record, dict):
            continue
        action_id = _text(record.get("action_id"), "")
        command_id = _action_run_command_id(record)
        if not command_id:
            continue
        if action_id:
            action_ids_with_runs.add(action_id)
        lifecycle_key = _action_run_lifecycle_key(record, index)
        current = run_snapshots.get(command_id)
        if current is None or lifecycle_key > current[0]:
            run_snapshots[command_id] = (lifecycle_key, record)

    for action_id, action in actions_by_id.items():
        if action_id in action_ids_with_runs:
            continue
        source_id = _text(action.get("source_id"), "")
        commands[action_id] = {
            "command_id": action_id,
            "owner_id": source_id or "controller",
            "run_id": source_id,
            "kind": _text(action.get("source_type"), "action"),
            "status": _text(action.get("status"), "ready"),
        }

    for command_id, (_, record) in run_snapshots.items():
        action_id = _text(record.get("action_id"), "")
        action = actions_by_id.get(action_id, {})
        run_id = _text(record.get("run_id"), "") or _text(record.get("go_run_id"), "")
        owner_id = _text(record.get("session_id"), "") or run_id or "controller"
        commands[command_id] = {
            "command_id": command_id,
            "owner_id": owner_id,
            "run_id": run_id,
            "kind": _text(record.get("kind"), _text(action.get("source_type"), "action")),
            "status": _text(record.get("status"), "unknown"),
        }
    return [
        commands[key]
        for key in sorted(commands)
        if _normalized(commands[key]["status"]) not in _TERMINAL_COMMAND_STATUSES
    ]


def _action_run_command_id(record: dict[str, Any]) -> str:
    action_id = _text(record.get("action_id"), "")
    action_run_id = _text(record.get("action_run_id"), "")
    if action_id and action_run_id:
        return f"{action_id}/{action_run_id}"
    if action_run_id:
        return action_run_id
    if not action_id:
        return ""
    identity_material = "\0".join([
        action_id,
        _text(record.get("run_id"), ""),
        _text(record.get("go_run_id"), ""),
        _text(record.get("session_id"), ""),
        _text(record.get("created_at"), ""),
    ])
    suffix = hashlib.sha256(identity_material.encode("utf-8")).hexdigest()[:16]
    return f"{action_id}/{suffix}"


def _action_run_lifecycle_key(record: dict[str, Any], index: int) -> tuple[int, str, int]:
    status = _normalized(record.get("status")) or "unknown"
    timestamp = (
        _text(record.get("completed_at"), "")
        or _text(record.get("updated_at"), "")
        or _text(record.get("started_at"), "")
        or _text(record.get("created_at"), "")
    )
    return (_COMMAND_LIFECYCLE_ORDER.get(status, 0), timestamp, index)


def _attach_command_ids(
    internal_workers: list[dict[str, Any]],
    visible_workers: list[dict[str, Any]],
    commands: list[dict[str, Any]],
) -> None:
    command_ids_by_owner: dict[str, list[str]] = {}
    for command in commands:
        command_ids_by_owner.setdefault(command["owner_id"], []).append(command["command_id"])
    for worker in internal_workers + visible_workers:
        worker["command_ids"] = sorted(command_ids_by_owner.get(worker["worker_id"], []))


def _ready_work(
    actions: list[dict[str, Any]] | None,
    root_gates: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    work: list[dict[str, Any]] = []
    for action in actions or []:
        if not isinstance(action, dict) or _normalized(action.get("status")) != "ready":
            continue
        source_id = _text(action.get("source_id"), "")
        work.append({
            "work_id": _text(action.get("action_id"), source_id or "action"),
            "project_id": "",
            "run_id": source_id,
            "kind": _text(action.get("source_type"), "action"),
            "state": "ready",
            "dedupe_key": "",
        })
    for snapshot in root_gates.values():
        if isinstance(snapshot, dict) and snapshot.get("state") == "authorized":
            work.append(_root_gate_work(snapshot, "ready"))
    return sorted(work, key=_work_sort_key)


def _gated_ready_work(root_gates: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        [
            _root_gate_work(snapshot, "gated_ready")
            for snapshot in root_gates.values()
            if isinstance(snapshot, dict) and snapshot.get("state") == "requested"
        ],
        key=_work_sort_key,
    )


def _root_gate_work(snapshot: dict[str, Any], state: str) -> dict[str, Any]:
    request = snapshot.get("request") if isinstance(snapshot.get("request"), dict) else {}
    return {
        "work_id": _text(snapshot.get("request_id"), "root-gate"),
        "project_id": _text(request.get("project_id"), ""),
        "run_id": _text(snapshot.get("run_id"), ""),
        "kind": "root_gate",
        "state": state,
        "dedupe_key": _text(snapshot.get("dedupe_key"), ""),
    }


def _work_sort_key(item: dict[str, Any]) -> tuple[str, str, str]:
    return (item["project_id"], item["run_id"], item["work_id"])


def _wake_dedupe_key(gated_ready: list[dict[str, Any]]) -> str:
    material = "\n".join(sorted(
        f"{item['project_id']}\0{item['run_id']}\0{item['work_id']}\0{item['dedupe_key']}"
        for item in gated_ready
    ))
    digest = hashlib.sha256(material.encode("utf-8")).hexdigest()
    return f"activity-liveness/{digest}"


def _is_active(value: object) -> bool:
    return _normalized(value) in _ACTIVE_WORKER_STATUSES


def _is_active_command(value: object) -> bool:
    return _normalized(value) in _ACTIVE_COMMAND_STATUSES


def _normalized(value: object) -> str:
    return _text(value, "").strip().lower().replace("-", "_")


def _text(value: object, fallback: str) -> str:
    text = str(value or "").strip()
    return text or fallback


def _strings(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item)]


def _count(value: object) -> int:
    if isinstance(value, bool):
        return 0
    return value if isinstance(value, int) and value >= 0 else 0


def _project_workers(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [
        {
            "workerId": _text(worker.get("worker_id"), ""),
            "parentId": _text(worker.get("parent_id"), ""),
            "role": _text(worker.get("role"), "worker"),
            "status": _text(worker.get("status"), "idle"),
            "runIds": _strings(worker.get("run_ids")),
            "commandIds": _strings(worker.get("command_ids")),
        }
        for worker in value
        if isinstance(worker, dict)
    ]


def _project_commands(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [
        {
            "commandId": _text(command.get("command_id"), ""),
            "ownerId": _text(command.get("owner_id"), ""),
            "runId": _text(command.get("run_id"), ""),
            "kind": _text(command.get("kind"), "action"),
            "status": _text(command.get("status"), "unknown"),
        }
        for command in value
        if isinstance(command, dict)
    ]


def _project_work(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [
        {
            "workId": _text(item.get("work_id"), ""),
            "projectId": _text(item.get("project_id"), ""),
            "runId": _text(item.get("run_id"), ""),
            "kind": _text(item.get("kind"), ""),
            "state": _text(item.get("state"), ""),
            "dedupeKey": _text(item.get("dedupe_key"), ""),
        }
        for item in value
        if isinstance(item, dict)
    ]
