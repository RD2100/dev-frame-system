"""T3 Code facing read model projection for the Visual Control Plane."""
from __future__ import annotations

import json
import platform
import re
import threading
import time
from copy import deepcopy
from datetime import datetime, timezone
from functools import cmp_to_key
from pathlib import Path
from typing import Any
from urllib.parse import quote

from .conversation_intake import GLOBAL_COORDINATOR_THREAD_ID
from .visual_state import build_visual_control_plane_state


_T3_SHELL_CACHE_TTL = 2.0
_T3_SHELL_CACHE: dict[tuple, tuple[float, dict[str, Any]]] = {}
_T3_SHELL_COMPACT_JSON_CACHE: dict[tuple, tuple[float, str]] = {}
_T3_SHELL_BUILD_LOCK = threading.RLock()

_WEB_AI_KEYWORDS = (
    "web gpt", "webgpt", "task intake", "task-intake", "mcp",
    "codexpro", "chatgpt", "web ai", "webai", "web-ai",
    "project summary", "project-summary",
)

_TASK_INTAKE_KEYWORDS = ("task intake", "task-intake", "task_intake")
_PROJECT_SUMMARY_KEYWORDS = ("project summary", "project-summary", "project_summary")
_GLOBAL_COORDINATOR_THREAD_ID = GLOBAL_COORDINATOR_THREAD_ID


def _t3_shell_cache_key(
    runtime_dir: str | Path | None,
    paper_project_dirs: list[str | Path] | None,
    base_url: str | None,
) -> tuple:
    return (
        str(Path(runtime_dir).resolve()) if runtime_dir is not None else "",
        tuple(str(Path(p).resolve()) for p in (paper_project_dirs or [])),
        base_url,
    )


def _prune_t3_shell_cache(now: float) -> None:
    expired = [
        key for key, (created_at, _) in _T3_SHELL_CACHE.items()
        if now - created_at >= _T3_SHELL_CACHE_TTL
    ]
    for key in expired:
        _T3_SHELL_CACHE.pop(key, None)


def _prune_t3_shell_compact_json_cache(now: float) -> None:
    expired = [
        key for key, (created_at, _) in _T3_SHELL_COMPACT_JSON_CACHE.items()
        if now - created_at >= _T3_SHELL_CACHE_TTL
    ]
    for key in expired:
        _T3_SHELL_COMPACT_JSON_CACHE.pop(key, None)


def build_t3_client_shell(
    runtime_dir: str | Path | None = None,
    paper_project_dirs: list[str | Path] | None = None,
    base_url: str | None = None,
) -> dict[str, Any]:
    """Project DevFrame state into a T3-style project/thread shell snapshot."""
    cache_key = _t3_shell_cache_key(runtime_dir, paper_project_dirs, base_url)
    with _T3_SHELL_BUILD_LOCK:
        now = time.monotonic()
        _prune_t3_shell_cache(now)
        cached = _T3_SHELL_CACHE.get(cache_key)
        if cached is not None and now - cached[0] < _T3_SHELL_CACHE_TTL:
            return deepcopy(cached[1])
        state = build_visual_control_plane_state(runtime_dir, paper_project_dirs=paper_project_dirs)
        try:
            from .cluster_run import list_cluster_runs

            cluster_runs = list_cluster_runs(runtime_dir)
        except Exception:  # noqa: BLE001 - best-effort projection only
            cluster_runs = []
        shell = build_t3_client_shell_from_state(
            state,
            base_url=base_url,
            runtime_dir=runtime_dir,
            cluster_runs=cluster_runs,
        )
        _T3_SHELL_CACHE[cache_key] = (now, deepcopy(shell))
        return shell


def invalidate_t3_shell_cache(runtime_dir: str | Path | None) -> None:
    """Drop cached shell snapshots for one runtime after a local state write."""
    runtime_key = str(Path(runtime_dir).resolve()) if runtime_dir is not None else ""
    with _T3_SHELL_BUILD_LOCK:
        for cache in (_T3_SHELL_CACHE, _T3_SHELL_COMPACT_JSON_CACHE):
            for key in [candidate for candidate in cache if candidate[0] == runtime_key]:
                cache.pop(key, None)


def build_t3_client_shell_from_state(
    state: dict[str, Any],
    base_url: str | None = None,
    *,
    runtime_dir: str | Path | None = None,
    cluster_runs: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    updated_at = _now_iso()
    projects = state.get("projects", [])
    sessions = state.get("sessions", [])
    actions = state.get("next_actions", [])
    gates = state.get("gates", [])
    provider_bindings = state.get("provider_bindings", [])
    runs = state.get("runs", [])
    go_runs = state.get("go_runs", [])
    team = state.get("team") or {}
    actions_by_source = _items_by_key(actions, "source_id")
    gates_by_run = _items_by_key(gates, "run_id")
    gates_by_id = _items_by_key(gates, "gate_id")
    runs_by_id = _items_by_single_key(runs, "run_id")
    go_runs_by_id = _items_by_single_key(go_runs, "go_run_id")
    run_ids_by_packet_path = _run_ids_by_path(runs, "packet_path")
    run_ids_by_task_spec_path = _run_ids_by_path(runs, "task_spec_path")
    bindings_by_id = {
        str(binding.get("binding_id") or ""): binding
        for binding in provider_bindings
        if isinstance(binding, dict)
    }
    team_task_board = _items_by_single_key(team.get("task_board") or [], "task_id")
    team_evidence_store = _items_by_key(team.get("evidence_store") or [], "run_id")
    team_message_bus = _items_by_key(team.get("message_bus") or [], "run_id")
    team_review_gates = _items_by_key(team.get("review_gates") or [], "run_id")
    team_conflict_control = _items_by_key(team.get("conflict_control") or [], "owner_run_id")
    team_event_log = _items_by_key(team.get("event_log") or [], "run_id")
    thread_shells = [
        _thread_shell(
            session,
            bindings_by_id,
            gates_by_run,
            gates_by_id,
            actions_by_source,
            runs_by_id,
            go_runs_by_id,
            run_ids_by_packet_path,
            run_ids_by_task_spec_path,
            _clean_base_url(base_url),
            updated_at,
            team_task_board,
            team_evidence_store,
            team_message_bus,
            team_review_gates,
            team_conflict_control,
            team_event_log,
        )
        for session in sessions
        if isinstance(session, dict)
    ]
    projected_thread_ids = {str(thread.get("id") or "") for thread in thread_shells if isinstance(thread, dict)}
    cluster_runs = [run for run in (cluster_runs or []) if isinstance(run, dict)]
    thread_shells.extend(
        _cluster_run_thread_shell(
            run,
            actions_by_source,
            _clean_base_url(base_url),
            updated_at,
            team_evidence_store,
            team_message_bus,
            team_review_gates,
        )
        for run in cluster_runs
        if str(run.get("runId") or "") and str(run.get("runId") or "") not in projected_thread_ids
    )
    first_project = next((project for project in projects if isinstance(project, dict)), {})
    project_id = _text(first_project.get("project_id"), "project")
    thread_shells.append(
        _team_workbench_thread_shell(
            team if isinstance(team, dict) else {},
            _clean_base_url(base_url),
            updated_at,
            project_id=project_id,
            actions=actions,
        )
    )
    thread_details = [
        _cluster_run_thread_detail(thread_shell, runtime_dir, updated_at)
        if _is_cluster_goal_thread(thread_shell)
        else _thread_detail(
            thread_shell,
            updated_at,
            team if _is_team_workbench_session(thread_shell.get("id")) else None,
            runtime_dir=runtime_dir,
        )
        for thread_shell in thread_shells
    ]
    return {
        "version": 1,
        "source": "devframe",
        "updatedAt": updated_at,
        "reuse": {
            "client": "t3code",
            "executor": "opencode",
            "protocol": "devframe-governed-agent-control-plane",
        },
        "t3": {
            "snapshotSequence": int(state.get("version") or 1),
            "projects": [_project_shell(project, updated_at) for project in projects if isinstance(project, dict)],
            "threads": thread_shells,
            "threadDetails": thread_details,
            "updatedAt": updated_at,
        },
        "devframe": {
            "manifest": "/client-manifest.json",
            "state": "/state.json",
            "sessions": "/sessions.json",
            "actions": "/actions.json",
            "controlPlaneBaseUrl": _clean_base_url(base_url),
            "writePolicy": "read-only",
            "conversationModel": build_devframe_conversation_model(),
            "gates": [_gate_overlay(gate) for gate in gates if isinstance(gate, dict)],
            "actionsBySource": _public_actions_by_source(actions_by_source),
            "team": _project_team(team),
        },
    }


def build_devframe_conversation_model() -> dict[str, Any]:
    return {
        "globalCoordinatorThreadId": _GLOBAL_COORDINATOR_THREAD_ID,
        "goalProjectBindingRequired": True,
        "threadKinds": ["native_chat", "goal_conversation", "global_coordinator"],
    }


def build_t3_coordinator_entry(
    shell: dict[str, Any],
    projects: list[dict[str, Any]] | None = None,
    selected_project_id: str | None = None,
) -> dict[str, Any]:
    """Build the one-call shell entry model for the Global Coordinator surface."""
    if not isinstance(shell, dict):
        shell = {}
    t3_payload = shell.get("t3")
    t3_snapshot = t3_payload if isinstance(t3_payload, dict) else {}
    if not isinstance(t3_snapshot, dict):
        t3_snapshot = {}
    is_malformed_response = not isinstance(t3_payload, dict)

    conversation_model = (
        shell.get("devframe", {}).get("conversationModel")
        if isinstance(shell.get("devframe"), dict)
        else None
    )
    if not isinstance(conversation_model, dict):
        conversation_model = build_devframe_conversation_model()

    sorted_shell = _sort_t3_shell_snapshot(t3_snapshot)
    shell_threads = [thread for thread in sorted_shell.get("threads", []) if isinstance(thread, dict)]
    global_thread_id = _text(conversation_model.get("globalCoordinatorThreadId"), _GLOBAL_COORDINATOR_THREAD_ID)
    global_thread = next(
        (thread for thread in shell_threads if _text(thread.get("id"), "") == global_thread_id),
        None,
    )
    if global_thread is None:
        global_thread = next(
            (thread for thread in shell_threads if _text(thread.get("threadKind"), "") == "global_coordinator"),
            None,
        )
    goal_conversations = [
        thread for thread in shell_threads if _text(thread.get("threadKind"), "") == "goal_conversation"
    ]
    shell_thread_summaries = [
        _coordinator_entry_thread_summary(thread)
        for thread in shell_threads
    ]
    thread_summary_by_id = {
        _text(thread.get("id"), ""): thread
        for thread in shell_thread_summaries
    }
    global_thread_summary = (
        thread_summary_by_id.get(_text(global_thread.get("id"), ""))
        if isinstance(global_thread, dict)
        else None
    )
    goal_conversation_summaries = [
        thread_summary_by_id[_text(thread.get("id"), "")]
        for thread in goal_conversations
        if _text(thread.get("id"), "") in thread_summary_by_id
    ]
    entry_sorted_shell = _coordinator_entry_sorted_shell(
        sorted_shell,
        shell_thread_summaries,
    )
    project_options = [project for project in (projects or []) if isinstance(project, dict)]

    requested_project_id = _text(selected_project_id, "")
    selected_project = (
        next(
            (
                project for project in project_options
                if _text(project.get("projectId"), "") == requested_project_id
            ),
            None,
        )
        if requested_project_id
        else None
    )
    if selected_project is None:
        selected_project = project_options[0] if project_options else None
    selected_project_id = _text(selected_project.get("projectId"), "") if isinstance(selected_project, dict) else ""
    project_coordinator_thread = None
    if selected_project_id:
        project_coordinator_thread = next(
            (
                thread
                for thread in goal_conversation_summaries
                if _text(thread.get("projectId"), "") == selected_project_id
            ),
            None,
        )

    empty_state_reason = None
    disabled_reason = None
    if not shell_threads:
        empty_state_reason = "no_threads"
        if is_malformed_response:
            empty_state_reason = "malformed_entry_response"
    elif not global_thread:
        empty_state_reason = "missing_global_coordinator_thread"
    elif is_malformed_response:
        empty_state_reason = "malformed_entry_response"

    goal_binding_required = bool(conversation_model.get("goalProjectBindingRequired"))
    if goal_binding_required and not project_options:
        disabled_reason = "missing_required_project"
        if not empty_state_reason:
            empty_state_reason = "no_projects"
    can_start_coordinator_goal = (not goal_binding_required) or bool(project_options)
    return {
        "version": 1,
        "source": "devframe",
        "updatedAt": _text(shell.get("updatedAt"), _now_iso()),
        "conversationModel": conversation_model,
        "projects": project_options,
        "projectOptions": project_options,
        "selectedProject": selected_project,
        "projectCoordinatorThread": project_coordinator_thread,
        "shellThreads": shell_thread_summaries,
        "globalCoordinatorThread": global_thread_summary,
        "goalConversations": goal_conversation_summaries,
        "sortedShell": entry_sorted_shell,
        "canStartCoordinatorGoal": can_start_coordinator_goal,
        "emptyStateReason": empty_state_reason,
        "disabledReason": disabled_reason,
    }


def _coordinator_entry_thread_summary(thread: dict[str, Any]) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "id": _text(thread.get("id"), ""),
        "projectId": _text(thread.get("projectId"), ""),
        "title": _text(thread.get("title"), ""),
        "threadKind": _text(thread.get("threadKind"), "native_chat"),
        "coordinatorScope": _text(thread.get("coordinatorScope"), "none"),
        "projectBinding": thread.get("projectBinding"),
        "threadListPriority": _safe_thread_list_priority(
            thread.get("threadListPriority"),
            _text(thread.get("threadKind"), "native_chat"),
        ),
        "threadListSummary": _text(thread.get("threadListSummary"), ""),
    }
    for key in (
        "modelSelection",
        "runtimeMode",
        "interactionMode",
        "branch",
        "worktreePath",
        "latestTurn",
        "createdAt",
        "updatedAt",
        "archivedAt",
        "deletedAt",
        "session",
        "latestUserMessageAt",
        "hasPendingApprovals",
        "hasPendingUserInput",
        "hasActionableProposedPlan",
    ):
        if key in thread:
            summary[key] = thread.get(key)
    return summary


def _coordinator_entry_sorted_shell(
    sorted_shell: dict[str, Any],
    thread_summaries: list[dict[str, Any]],
) -> dict[str, Any]:
    """Keep coordinator-entry payload focused on shell navigation state."""
    entry_shell = deepcopy(sorted_shell)
    entry_shell["threads"] = thread_summaries
    entry_shell["threadDetails"] = []
    return entry_shell


def render_t3_client_shell_json(shell: dict[str, Any] | None = None) -> str:
    return json.dumps(shell or build_t3_client_shell(), indent=2, ensure_ascii=True)


def render_t3_client_shell_compact_json(shell: dict[str, Any] | None = None) -> str:
    return json.dumps(shell or build_t3_client_shell(), separators=(",", ":"), ensure_ascii=True)


def render_cached_t3_client_shell_compact_json(
    runtime_dir: str | Path | None = None,
    paper_project_dirs: list[str | Path] | None = None,
    base_url: str | None = None,
) -> str:
    cache_key = _t3_shell_cache_key(runtime_dir, paper_project_dirs, base_url)
    with _T3_SHELL_BUILD_LOCK:
        now = time.monotonic()
        _prune_t3_shell_compact_json_cache(now)
        cached = _T3_SHELL_COMPACT_JSON_CACHE.get(cache_key)
        if cached is not None and now - cached[0] < _T3_SHELL_CACHE_TTL:
            return cached[1]
        shell = build_t3_client_shell(runtime_dir, paper_project_dirs=paper_project_dirs, base_url=base_url)
        compact = json.dumps(shell, separators=(",", ":"), ensure_ascii=True)
        _T3_SHELL_COMPACT_JSON_CACHE[cache_key] = (now, compact)
        return compact


def build_t3_environment_descriptor() -> dict[str, Any]:
    """Expose the minimal descriptor T3 Code expects for a primary environment."""
    return {
        "environmentId": "devframe-local",
        "label": "DevFrame Local Agent Control Plane",
        "platform": {
            "os": _platform_os(),
            "arch": _platform_arch(),
        },
        "serverVersion": "devframe-control-plane/0.1",
        "capabilities": {
            "repositoryIdentity": False,
        },
    }


def render_t3_environment_descriptor_json(descriptor: dict[str, Any] | None = None) -> str:
    return json.dumps(descriptor or build_t3_environment_descriptor(), indent=2, ensure_ascii=True)


def _project_shell(project: dict[str, Any], updated_at: str) -> dict[str, Any]:
    project_id = _text(project.get("project_id"), "project")
    return {
        "id": project_id,
        "title": _text(project.get("display_name"), project_id),
        "workspaceRoot": _workspace_root(project),
        "repositoryIdentity": None,
        "defaultModelSelection": None,
        "scripts": [],
        "createdAt": updated_at,
        "updatedAt": updated_at,
        "devframe": {
            "goal": _text(project.get("goal"), ""),
            "status": _text(project.get("status"), "initialized"),
            "riskState": _text(project.get("risk_state"), "medium"),
            "contractPath": _text(project.get("contract_path"), ""),
        },
    }


def _project_team(team: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(team, dict):
        return _empty_team_projection()
    return {
        "agentRegistry": _project_team_agents(team.get("agent_registry")),
        "taskBoard": _project_team_tasks(team.get("task_board")),
        "messageBus": _project_team_messages(team.get("message_bus")),
        "eventLog": _project_team_events(team.get("event_log")),
        "evidenceStore": _project_team_evidence(team.get("evidence_store")),
        "reviewGates": _project_team_gates(team.get("review_gates")),
        "conflictControl": _project_team_conflicts(team.get("conflict_control")),
    }


def _empty_team_projection() -> dict[str, Any]:
    return {
        "agentRegistry": [],
        "taskBoard": [],
        "messageBus": [],
        "eventLog": [],
        "evidenceStore": [],
        "reviewGates": [],
        "conflictControl": [],
    }


def _project_team_agents(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [
        {
            "agentId": _text(a.get("agent_id"), ""),
            "role": _text(a.get("role"), ""),
            "bindingId": _text(a.get("binding_id"), ""),
            "status": _text(a.get("status"), "idle"),
            "sessionIds": _strings(a.get("session_ids")),
        }
        for a in value if isinstance(a, dict)
    ]


def _project_team_tasks(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    items: list[dict[str, Any]] = []
    for t in value:
        if not isinstance(t, dict):
            continue
        entry = {
            "taskId": _text(t.get("task_id"), ""),
            "type": _text(t.get("type"), ""),
            "projectId": _text(t.get("project_id"), ""),
            "status": _text(t.get("status"), ""),
            "agentIds": _strings(t.get("agent_ids")),
            "sessionIds": _strings(t.get("session_ids")),
            "targetFiles": _strings(t.get("target_files")),
        }
        methodology = _project_methodology(t.get("methodology"))
        if methodology:
            entry["methodology"] = methodology
        items.append(entry)
    return items


def _project_methodology(value: object) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    skill_id = _text(value.get("skill_id"), "")
    if not skill_id:
        return None
    return {
        "skillId": skill_id,
        "title": _text(value.get("title"), skill_id),
        "sourcePath": _text(value.get("source_path"), ""),
        "sourceKind": _text(value.get("source_kind"), ""),
        "triggers": _strings(value.get("triggers")),
        "status": _text(value.get("status"), ""),
    }


def _project_team_messages(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [
        {
            "messageId": _text(m.get("message_id"), ""),
            "fromRole": _text(m.get("from_role"), ""),
            "toRole": _text(m.get("to_role"), ""),
            "kind": _text(m.get("kind"), ""),
            "runId": _text(m.get("run_id"), ""),
            "summary": _text(m.get("summary"), ""),
        }
        for m in value if isinstance(m, dict)
    ]


def _project_team_events(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [
        {
            "eventId": _text(e.get("event_id"), ""),
            "kind": _text(e.get("kind"), ""),
            "runId": _text(e.get("run_id"), ""),
            "summary": _text(e.get("summary"), ""),
        }
        for e in value if isinstance(e, dict)
    ]


def _project_team_evidence(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [
        {
            "evidenceId": _text(e.get("evidence_id"), ""),
            "runId": _text(e.get("run_id"), ""),
            "refType": _text(e.get("ref_type"), ""),
            "refPath": _public_safe_evidence_path(e.get("ref_path")),
        }
        for e in value if isinstance(e, dict)
    ]


def _project_team_gates(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [
        {
            "gateId": _text(g.get("gate_id"), ""),
            "kind": _text(g.get("kind"), ""),
            "status": _text(g.get("status"), ""),
            "reason": _text(g.get("reason"), ""),
            "runId": _text(g.get("run_id"), ""),
        }
        for g in value if isinstance(g, dict)
    ]


def _project_team_conflicts(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [
        {
            "filePath": _text(c.get("file_path"), ""),
            "ownerRunId": _text(c.get("owner_run_id"), ""),
            "ownerAgentId": _text(c.get("owner_agent_id"), ""),
            "fileKind": _text(c.get("file_kind"), ""),
        }
        for c in value if isinstance(c, dict)
    ]


def _workspace_root(project: dict[str, Any]) -> str:
    contract_path = _text(project.get("contract_path"), "")
    if not contract_path:
        return ""
    path = Path(contract_path)
    if path.parent.name == "project-contracts":
        return str(path.parent.parent.parent)
    return str(path.parent)


def _thread_shell(
    session: dict[str, Any],
    bindings_by_id: dict[str, dict[str, Any]],
    gates_by_run: dict[str, list[dict[str, Any]]],
    gates_by_id: dict[str, list[dict[str, Any]]],
    actions_by_source: dict[str, list[dict[str, Any]]],
    runs_by_id: dict[str, dict[str, Any]],
    go_runs_by_id: dict[str, dict[str, Any]],
    run_ids_by_packet_path: dict[str, list[str]],
    run_ids_by_task_spec_path: dict[str, list[str]],
    base_url: str,
    updated_at: str,
    team_task_board: dict[str, dict[str, Any]] | None = None,
    team_evidence_store: dict[str, list[dict[str, Any]]] | None = None,
    team_message_bus: dict[str, list[dict[str, Any]]] | None = None,
    team_review_gates: dict[str, list[dict[str, Any]]] | None = None,
    team_conflict_control: dict[str, list[dict[str, Any]]] | None = None,
    team_event_log: dict[str, list[dict[str, Any]]] | None = None,
) -> dict[str, Any]:
    thread_id = _text(session.get("session_id"), "session")
    project_id = _text(session.get("project_id"), "project")
    provider = _text(session.get("provider"), "custom")
    run_id = _text(session.get("run_id"), "")
    related_run_ids = _related_run_ids(
        session,
        runs_by_id,
        go_runs_by_id,
        run_ids_by_packet_path,
        run_ids_by_task_spec_path,
    )
    direct_gate_ids = [str(gate) for gate in session.get("gates", [])] if isinstance(session.get("gates"), list) else []
    run_gates = _unique_gates(
        [
            gate
            for related_run_id in related_run_ids
            for gate in gates_by_run.get(related_run_id, [])
        ]
        + [
            gate
            for gate_id in direct_gate_ids
            for gate in gates_by_id.get(gate_id, [])
        ]
    )
    gate_ids = [str(gate.get("gate_id")) for gate in run_gates if gate.get("gate_id")]
    direct_action_ids = [str(action) for action in session.get("actions", [])] if isinstance(session.get("actions"), list) else []
    action_ids = _unique(
        direct_action_ids
        + [
            str(action.get("action_id"))
            for gate_id in gate_ids
            for action in actions_by_source.get(gate_id, [])
            if action.get("action_id")
        ]
        + [
            str(action.get("action_id"))
            for action in actions_by_source.get(run_id, [])
            if action.get("action_id")
        ]
        + [
            str(action.get("action_id"))
            for related_run_id in related_run_ids
            for action in actions_by_source.get(related_run_id, [])
            if action.get("action_id")
        ]
        + [
            str(action.get("action_id"))
            for related_run_id in related_run_ids
            for action in actions_by_source.get(f"{related_run_id}-decision", [])
            if action.get("action_id")
        ]
        + [
            str(action.get("action_id"))
            for action in actions_by_source.get(thread_id, [])
            if action.get("action_id")
        ]
    )
    action_details = _action_details(actions_by_source, action_ids, base_url)
    pending_gate = any(_text(gate.get("status"), "") in {"open", "blocked", "failed"} for gate in run_gates)
    pending_action = bool(action_ids)
    thread_kind = _thread_kind(session, related_run_ids)
    project_binding = _project_binding(thread_kind, project_id)
    session_status = _session_status(session)
    all_team_gates = _readable_team_gates(run_id, related_run_ids, team_review_gates or {}, base_url)
    team_detail_gates, team_detail_gate_overflow = _cap_with_overflow(all_team_gates, _PROJECTED_DETAIL_LIMIT)
    team_review_gate_status_counts = _count_gate_statuses(all_team_gates)
    team_next_actionable_gates = _sorted_actionable_gates(all_team_gates)[:_PROJECTED_DETAIL_LIMIT]
    return {
        "id": thread_id,
        "projectId": project_id,
        "title": _thread_title(session),
        "threadKind": thread_kind,
        "coordinatorScope": "project" if thread_kind == "goal_conversation" else "none",
        "projectBinding": project_binding,
        "threadListPriority": _thread_list_priority(thread_kind),
        "threadListSummary": _thread_list_summary(
            thread_kind=thread_kind,
            title=_thread_title(session),
            project_id=project_id,
            provider=provider,
            role=_text(session.get("agent_role"), "custom"),
            status=session_status,
            summary=_text(session.get("diff_summary"), ""),
        ),
        "modelSelection": {
            "instanceId": _provider_instance_id(session, bindings_by_id),
            "model": "devframe-governed-session",
        },
        "runtimeMode": _runtime_mode(session, pending_gate),
        "interactionMode": "plan" if pending_gate else "default",
        "branch": None,
        "worktreePath": None,
        "latestTurn": None,
        "createdAt": updated_at,
        "updatedAt": updated_at,
        "archivedAt": None,
        "session": {
            "threadId": thread_id,
            "status": session_status,
            "providerName": provider,
            "runtimeMode": _runtime_mode(session, pending_gate),
            "activeTurnId": None,
            "lastError": _session_error(session),
            "updatedAt": updated_at,
        },
        "latestUserMessageAt": None,
        "hasPendingApprovals": pending_gate,
        "hasPendingUserInput": pending_action,
        "hasActionableProposedPlan": any(
            _text(action.get("status"), "") == "ready"
            for action in action_details
        ),
        "devframe": {
            "provider": provider,
            "agentRole": _text(session.get("agent_role"), "custom"),
            "bindingId": _text(session.get("binding_id"), ""),
            "runId": run_id,
            "taskSpecId": _text(session.get("task_spec_id"), ""),
            "messageCount": _count(session.get("messages")),
            "toolCallCount": _count(session.get("tool_calls")),
            "changedFiles": _strings(session.get("changed_files")),
            "diffSummary": _text(session.get("diff_summary"), ""),
            "relatedRunIds": related_run_ids,
            "gateIds": gate_ids,
            "gateDetails": [
                {
                    "gateId": _text(gate.get("gate_id"), ""),
                    "kind": _text(gate.get("kind"), ""),
                    "status": _text(gate.get("status"), ""),
                    "reason": _text(gate.get("reason"), ""),
                }
                for gate in run_gates
                if isinstance(gate, dict) and gate.get("gate_id")
            ],
            "actionIds": action_ids,
            "actionDetails": action_details,
            "evidenceRefs": [_evidence_ref_detail(ref, base_url) for ref in _strings(session.get("evidence_refs"))[:_PROJECTED_DETAIL_LIMIT]],
            "evidenceRefOverflow": max(0, len(_strings(session.get("evidence_refs"))) - _PROJECTED_DETAIL_LIMIT),
            "teamTaskIds": _team_task_ids_for_run(run_id, related_run_ids, team_task_board or {}),
            "teamMessageIds": _team_message_ids_for_run(run_id, related_run_ids, team_message_bus or {}),
            "teamEvidenceIds": _team_evidence_ids_for_run(run_id, related_run_ids, team_evidence_store or {}),
            "teamReviewGateIds": _team_review_gate_ids_for_run(run_id, related_run_ids, team_review_gates or {}),
            "teamConflictFiles": _team_conflict_files_for_run(run_id, related_run_ids, team_conflict_control or {}),
            "teamDetailMethodologies": _readable_team_methodologies(run_id, related_run_ids, team_task_board or {}),
            "teamDetailMessages": _readable_team_messages(run_id, related_run_ids, team_message_bus or {})[:_PROJECTED_DETAIL_LIMIT],
            "teamDetailMessageOverflow": max(0, len(_readable_team_messages(run_id, related_run_ids, team_message_bus or {})) - _PROJECTED_DETAIL_LIMIT),
            "teamDetailEvidence": _readable_team_evidence(run_id, related_run_ids, team_evidence_store or {}, base_url)[:_PROJECTED_DETAIL_LIMIT],
            "teamDetailEvidenceOverflow": max(0, len(_readable_team_evidence(run_id, related_run_ids, team_evidence_store or {}, base_url)) - _PROJECTED_DETAIL_LIMIT),
            "teamDetailGates": team_detail_gates,
            "teamDetailGateOverflow": team_detail_gate_overflow,
            "teamReviewGateStatusCounts": team_review_gate_status_counts,
            "teamNextActionableGates": team_next_actionable_gates,
            "teamDetailConflicts": _readable_team_conflicts(run_id, related_run_ids, team_conflict_control or {})[:_PROJECTED_DETAIL_LIMIT],
            "teamDetailConflictOverflow": max(0, len(_readable_team_conflicts(run_id, related_run_ids, team_conflict_control or {})) - _PROJECTED_DETAIL_LIMIT),
            "teamDetailEvents": _readable_team_events(run_id, related_run_ids, team_event_log or {})[:_PROJECTED_DETAIL_LIMIT],
            "teamDetailEventOverflow": max(0, len(_readable_team_events(run_id, related_run_ids, team_event_log or {})) - _PROJECTED_DETAIL_LIMIT),
        },
    }


def _has_team_data(team: dict[str, Any]) -> bool:
    if not isinstance(team, dict):
        return False
    return any(team.get(key) for key in [
        "agent_registry",
        "task_board",
        "message_bus",
        "evidence_store",
        "review_gates",
        "conflict_control",
        "event_log",
    ])


def _is_team_workbench_session(thread_id: str) -> bool:
    return thread_id == _GLOBAL_COORDINATOR_THREAD_ID


def _thread_kind(session: dict[str, Any], related_run_ids: list[str]) -> str:
    run_id = _text(session.get("run_id"), "")
    task_spec_id = _text(session.get("task_spec_id"), "")
    if run_id or task_spec_id or related_run_ids:
        return "goal_conversation"
    return "native_chat"


def _project_binding(thread_kind: str, project_id: str) -> dict[str, Any]:
    if thread_kind == "goal_conversation":
        return {
            "mode": "required",
            "projectId": project_id,
            "status": "bound" if project_id else "missing",
        }
    if thread_kind == "global_coordinator":
        return {
            "mode": "optional",
            "projectId": project_id,
            "status": "bound" if project_id else "not-applicable",
        }
    return {
        "mode": "none",
        "projectId": project_id,
        "status": "bound" if project_id else "not-applicable",
    }


def _thread_kind_label(thread_kind: str) -> str:
    return {
        "native_chat": "Native chat",
        "goal_conversation": "Goal conversation",
        "global_coordinator": "Global coordinator",
    }.get(thread_kind, thread_kind or "Unknown")


def _project_binding_summary(value: object) -> str:
    if not isinstance(value, dict):
        return "none"
    mode = _text(value.get("mode"), "none")
    status = _text(value.get("status"), "not-applicable")
    project_id = _text(value.get("projectId"), "")
    if project_id:
        return f"{mode} ({status}, project={project_id})"
    return f"{mode} ({status})"


def _thread_list_priority(thread_kind: str) -> int:
    return {
        "global_coordinator": 0,
        "goal_conversation": 1,
        "native_chat": 2,
    }.get(thread_kind, 99)


def _safe_thread_list_priority(value: object, thread_kind: str) -> int:
    kind = _text(thread_kind, "native_chat")
    if kind == "global_coordinator":
        return 0
    if isinstance(value, bool):
        return _thread_list_priority(kind)
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return _thread_list_priority(kind)
    if isinstance(value, float):
        return int(value)
    return _thread_list_priority(kind)


def _sort_t3_shell_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]:
    sorted_snapshot = deepcopy(snapshot) if isinstance(snapshot, dict) else {}
    if not isinstance(sorted_snapshot.get("snapshotSequence"), int):
        sorted_snapshot["snapshotSequence"] = 1
    if not isinstance(sorted_snapshot.get("projects"), list):
        sorted_snapshot["projects"] = []
    if not isinstance(sorted_snapshot.get("updatedAt"), str):
        sorted_snapshot["updatedAt"] = _now_iso()
    if not isinstance(sorted_snapshot.get("threadDetails"), list):
        sorted_snapshot["threadDetails"] = []
    threads = [
        thread
        for thread in sorted_snapshot.get("threads", [])
        if isinstance(thread, dict)
    ]
    details_by_id = {
        _text(detail.get("id"), ""): detail
        for detail in sorted_snapshot.get("threadDetails", [])
        if isinstance(detail, dict)
    }
    normalized_threads: list[dict[str, Any]] = []
    for thread in threads:
        if not isinstance(thread, dict):
            continue
        thread_copy = thread.copy()
        thread_copy["threadListPriority"] = _safe_thread_list_priority(
            thread_copy.get("threadListPriority"),
            _text(thread_copy.get("threadKind"), "native_chat"),
        )
        normalized_threads.append(thread_copy)

    def compare_threads(left: dict[str, Any], right: dict[str, Any]) -> int:
        left_priority = _safe_thread_list_priority(
            left.get("threadListPriority"),
            _text(left.get("threadKind"), "native_chat"),
        )
        right_priority = _safe_thread_list_priority(
            right.get("threadListPriority"),
            _text(right.get("threadKind"), "native_chat"),
        )
        if left_priority != right_priority:
            return left_priority - right_priority
        left_updated = _text(left.get("updatedAt"), "")
        right_updated = _text(right.get("updatedAt"), "")
        if left_updated != right_updated:
            return -1 if left_updated > right_updated else 1
        left_title = _text(left.get("title"), "")
        right_title = _text(right.get("title"), "")
        return (left_title > right_title) - (left_title < right_title)

    threads = sorted(normalized_threads, key=cmp_to_key(compare_threads))
    sorted_snapshot["threads"] = threads
    sorted_snapshot["threadDetails"] = [
        details_by_id[_text(thread.get("id"), "")]
        for thread in threads
        if _text(thread.get("id"), "") in details_by_id
    ]
    return sorted_snapshot


def _thread_list_summary(
    *,
    thread_kind: str,
    title: str,
    project_id: str,
    provider: str,
    role: str,
    status: str,
    summary: str = "",
) -> str:
    if thread_kind == "global_coordinator":
        return "Global coordinator inbox for starting goals, supervising work, and reviewing what needs attention."
    if thread_kind == "goal_conversation":
        prefix = f"{project_id}: {status}" if project_id else status
        return f"{prefix} - {summary or title}".strip(" -")
    return f"{provider} / {role} - {status}"


def _cluster_run_status_to_session_status(status: str) -> str:
    return {
        "answered": "stopped",
        "completed": "stopped",
        "failed": "error",
        "interrupted": "error",
        "running": "running",
        "started": "running",
    }.get(_text(status, "running"), "idle")


def _cluster_run_thread_shell(
    run: dict[str, Any],
    actions_by_source: dict[str, list[dict[str, Any]]],
    base_url: str,
    updated_at: str,
    team_evidence_store: dict[str, list[dict[str, Any]]],
    team_message_bus: dict[str, list[dict[str, Any]]],
    team_review_gates: dict[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    run_id = _text(run.get("runId"), "")
    raw_go_run_id = run.get("goRunId")
    go_run_id = raw_go_run_id.strip() if isinstance(raw_go_run_id, str) else ""
    goal = _text(run.get("goal"), run_id)
    project_id = _text(run.get("projectId"), "project")
    project_path = _text(run.get("projectPath"), "")
    action_ids = _unique(
        [
            str(action.get("action_id"))
            for action in actions_by_source.get(run_id, [])
            if action.get("action_id")
        ]
        + [
            str(action.get("action_id"))
            for action in actions_by_source.get(f"{run_id}-decision", [])
            if action.get("action_id")
        ]
    )
    action_details = _action_details(actions_by_source, action_ids, base_url)
    status = _text(run.get("status"), "running")
    pending_action = bool(action_ids)
    session_status = _cluster_run_status_to_session_status(status)
    all_team_gates = (
        _readable_team_gates(go_run_id, [], team_review_gates, base_url)
        if go_run_id else []
    )
    team_detail_gates, team_detail_gate_overflow = _cap_with_overflow(
        all_team_gates,
        _PROJECTED_DETAIL_LIMIT,
    )
    return {
        "id": run_id,
        "projectId": project_id,
        "title": goal,
        "threadKind": "goal_conversation",
        "coordinatorScope": "project",
        "projectBinding": {
            "mode": "required",
            "projectId": project_id,
            "status": "bound" if project_id else "missing",
        },
        "threadListPriority": _thread_list_priority("goal_conversation"),
        "threadListSummary": _thread_list_summary(
            thread_kind="goal_conversation",
            title=goal,
            project_id=project_id,
            provider="devframe",
            role="project-coordinator",
            status=session_status,
            summary=_text(run.get("summary"), ""),
        ),
        "modelSelection": {
            "instanceId": "devframe-project-coordinator",
            "model": "devframe-project-coordinator",
        },
        "runtimeMode": "approval-required" if pending_action or status in {"failed", "interrupted"} else "full-access",
        "interactionMode": "plan",
        "branch": None,
        "worktreePath": project_path or None,
        "latestTurn": None,
        "createdAt": _text(run.get("startedAt"), updated_at),
        "updatedAt": _text(run.get("finishedAt"), _text(run.get("startedAt"), updated_at)),
        "archivedAt": None,
        "session": {
            "threadId": run_id,
            "status": session_status,
            "providerName": "devframe",
            "runtimeMode": "approval-required" if pending_action or status in {"failed", "interrupted"} else "full-access",
            "activeTurnId": None,
            "lastError": "Goal conversation failed or was interrupted." if status in {"failed", "interrupted"} else None,
            "updatedAt": _text(run.get("finishedAt"), _text(run.get("startedAt"), updated_at)),
        },
        "latestUserMessageAt": None,
        "hasPendingApprovals": bool(action_ids),
        "hasPendingUserInput": bool(action_ids),
        "hasActionableProposedPlan": any(_text(action.get("status"), "").lower() == "ready" for action in action_details),
        "devframe": {
            "provider": "devframe",
            "agentRole": "project-coordinator",
            "bindingId": "",
            "runId": run_id,
            "taskSpecId": "",
            "messageCount": 0,
            "toolCallCount": 0,
            "changedFiles": [],
            "diffSummary": _text(run.get("summary"), ""),
            "relatedRunIds": [go_run_id] if go_run_id else [],
            "gateIds": [],
            "actionIds": action_ids,
            "actionDetails": action_details,
            "evidenceRefs": [],
            "evidenceRefOverflow": 0,
            "teamTaskIds": [],
            "teamMessageIds": (
                _team_message_ids_for_run(go_run_id, [], team_message_bus)
                if go_run_id else []
            ),
            "teamEvidenceIds": (
                _team_evidence_ids_for_run(go_run_id, [], team_evidence_store)
                if go_run_id else []
            ),
            "teamReviewGateIds": (
                _team_review_gate_ids_for_run(go_run_id, [], team_review_gates)
                if go_run_id else []
            ),
            "teamConflictFiles": [],
            "teamDetailMethodologies": [],
            "teamDetailMessages": [],
            "teamDetailMessageOverflow": 0,
            "teamDetailEvidence": [],
            "teamDetailEvidenceOverflow": 0,
            "teamDetailGates": team_detail_gates,
            "teamDetailGateOverflow": team_detail_gate_overflow,
            "teamReviewGateStatusCounts": _count_gate_statuses(all_team_gates),
            "teamNextActionableGates": _sorted_actionable_gates(all_team_gates)[:_PROJECTED_DETAIL_LIMIT],
            "teamDetailConflicts": [],
            "teamDetailConflictOverflow": 0,
            "teamDetailEvents": [],
            "teamDetailEventOverflow": 0,
        },
    }


def _is_cluster_goal_thread(thread_shell: dict[str, Any]) -> bool:
    return (
        _text(thread_shell.get("threadKind"), "") == "goal_conversation"
        and _text((thread_shell.get("devframe") or {}).get("agentRole"), "") == "project-coordinator"
    )


def _is_web_ai_local_agent_item(item: dict[str, Any]) -> bool:
    fields = [
        _text(item.get("action_id"), ""),
        _text(item.get("label"), ""),
        _text(item.get("detail"), ""),
        _text(item.get("command"), ""),
        _text(item.get("source_type"), ""),
        _text(item.get("source_id"), ""),
        _text(item.get("kind"), ""),
        _text(item.get("summary"), ""),
        _text(item.get("reason"), ""),
        _text(item.get("ref_path"), ""),
        _text(item.get("message_id"), ""),
        _text(item.get("evidence_id"), ""),
        _text(item.get("gate_id"), ""),
        _text(item.get("event_id"), ""),
        _text(item.get("run_id"), ""),
        _text(item.get("from_role"), ""),
        _text(item.get("to_role"), ""),
        _text(item.get("refPath"), ""),
        _text(item.get("messageId"), ""),
        _text(item.get("evidenceId"), ""),
        _text(item.get("gateId"), ""),
        _text(item.get("eventId"), ""),
        _text(item.get("runId"), ""),
        _text(item.get("fromRole"), ""),
        _text(item.get("toRole"), ""),
    ]
    combined = " ".join(fields).lower()
    return any(keyword in combined for keyword in _WEB_AI_KEYWORDS)


def _is_task_intake_item(item: dict[str, Any]) -> bool:
    fields = [
        _text(item.get("action_id"), ""),
        _text(item.get("label"), ""),
        _text(item.get("detail"), ""),
        _text(item.get("command"), ""),
        _text(item.get("source_type"), ""),
        _text(item.get("source_id"), ""),
        _text(item.get("kind"), ""),
        _text(item.get("summary"), ""),
        _text(item.get("reason"), ""),
        _text(item.get("ref_path"), ""),
        _text(item.get("message_id"), ""),
        _text(item.get("evidence_id"), ""),
        _text(item.get("gate_id"), ""),
        _text(item.get("event_id"), ""),
        _text(item.get("run_id"), ""),
        _text(item.get("from_role"), ""),
        _text(item.get("to_role"), ""),
        _text(item.get("refPath"), ""),
        _text(item.get("messageId"), ""),
        _text(item.get("evidenceId"), ""),
        _text(item.get("gateId"), ""),
        _text(item.get("eventId"), ""),
        _text(item.get("runId"), ""),
        _text(item.get("fromRole"), ""),
        _text(item.get("toRole"), ""),
    ]
    combined = " ".join(fields).lower()
    return any(keyword in combined for keyword in _TASK_INTAKE_KEYWORDS)


def _is_project_summary_item(item: dict[str, Any]) -> bool:
    fields = [
        _text(item.get("action_id"), ""),
        _text(item.get("label"), ""),
        _text(item.get("detail"), ""),
        _text(item.get("command"), ""),
        _text(item.get("source_type"), ""),
        _text(item.get("source_id"), ""),
        _text(item.get("kind"), ""),
        _text(item.get("summary"), ""),
        _text(item.get("reason"), ""),
        _text(item.get("ref_path"), ""),
        _text(item.get("message_id"), ""),
        _text(item.get("evidence_id"), ""),
        _text(item.get("gate_id"), ""),
        _text(item.get("event_id"), ""),
        _text(item.get("run_id"), ""),
        _text(item.get("from_role"), ""),
        _text(item.get("to_role"), ""),
        _text(item.get("refPath"), ""),
        _text(item.get("messageId"), ""),
        _text(item.get("evidenceId"), ""),
        _text(item.get("gateId"), ""),
        _text(item.get("eventId"), ""),
        _text(item.get("runId"), ""),
        _text(item.get("fromRole"), ""),
        _text(item.get("toRole"), ""),
    ]
    combined = " ".join(fields).lower()
    return any(keyword in combined for keyword in _PROJECT_SUMMARY_KEYWORDS)


def _workbench_priority_actions(
    actions: list[dict[str, Any]],
    base_url: str,
    limit: int = 10,
) -> list[dict[str, str]]:
    actionable = [
        a for a in actions
        if isinstance(a, dict)
        and _text(a.get("status"), "").lower() in {"ready", "open"}
    ]
    web_ai = [a for a in actionable if _is_web_ai_local_agent_item(a)]
    other = [a for a in actionable if a not in web_ai]
    priority_order = {"high": 0, "medium": 1, "low": 2}

    def _web_ai_category(a: dict[str, Any]) -> int:
        if _is_task_intake_item(a):
            return 0
        if _is_project_summary_item(a):
            return 1
        return 2

    web_ai.sort(key=lambda a: (
        _web_ai_category(a),
        priority_order.get(_text(a.get("priority"), "").lower(), 3),
    ))
    other.sort(key=lambda a: priority_order.get(_text(a.get("priority"), "").lower(), 3))
    combined = web_ai + other
    return [_action_detail(a, base_url) for a in combined[:limit]]


def _render_workbench_action_lines(
    priority_actions: list[dict[str, str]],
) -> list[str]:
    if not priority_actions:
        return []
    lines = ["", "#### WebGPT / MCP Local Agent Actions", ""]
    for action in priority_actions:
        action_id = _text(action.get("actionId"), "")
        status = _text(action.get("status"), "")
        priority = _text(action.get("priority"), "")
        label = _text(action.get("label"), "")
        command = _text(action.get("command"), "")
        open_url = _text(action.get("openUrl"), "")
        if open_url:
            lines.append(f"  - `{action_id}` [{status}/{priority}]: [{label}]({open_url})")
        else:
            lines.append(f"  - `{action_id}` [{status}/{priority}]: {label}")
        if command:
            lines.append(f"    - Command: `{command}`")
    lines.append("")
    return lines


def _render_web_ai_team_activity_lines(
    messages: list[dict[str, Any]],
    evidence: list[dict[str, Any]],
    gates: list[dict[str, Any]],
    events: list[dict[str, Any]],
) -> list[str]:
    lines: list[str] = []
    if messages:
        lines.append("  - **Messages**:")
        for m in messages:
            fr = _text(m.get("fromRole"), "")
            to = _text(m.get("toRole"), "")
            kind = _text(m.get("kind"), "")
            summary = _text(m.get("summary"), "")
            lines.append(f"    - {fr} -> {to} [{kind}]: {summary}")
    if evidence:
        lines.append("  - **Evidence**:")
        for e in evidence:
            ref_type = _text(e.get("refType"), "")
            ref_path = _text(e.get("refPath"), "")
            lines.append(f"    - [{ref_type}] `{ref_path}`")
    if gates:
        lines.append("  - **Review Gates**:")
        for g in gates:
            gid = _text(g.get("gateId"), "")
            kind = _text(g.get("kind"), "")
            status = _text(g.get("status"), "")
            lines.append(f"    - `{gid}` [{kind}] {status}")
    if events:
        lines.append("  - **Events**:")
        for e in events:
            kind = _text(e.get("kind"), "")
            summary = _text(e.get("summary"), "")
            lines.append(f"    - [{kind}] {summary}")
    return lines


def _team_workbench_thread_shell(
    team: dict[str, Any],
    base_url: str,
    updated_at: str,
    project_id: str = "project",
    actions: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    all_messages = [
        {
            "messageId": _text(m.get("message_id"), ""),
            "fromRole": _text(m.get("from_role"), ""),
            "toRole": _text(m.get("to_role"), ""),
            "kind": _text(m.get("kind"), ""),
            "summary": _text(m.get("summary"), ""),
        }
        for m in (team.get("message_bus") or [])
        if isinstance(m, dict)
    ]
    all_evidence = [
        {
            "evidenceId": _text(e.get("evidence_id"), ""),
            "refType": _text(e.get("ref_type"), ""),
            "refPath": _public_safe_evidence_path(e.get("ref_path")),
        }
        for e in (team.get("evidence_store") or [])
        if isinstance(e, dict)
    ]
    all_gates = [
        {
            "gateId": _text(g.get("gate_id"), ""),
            "kind": _text(g.get("kind"), ""),
            "status": _text(g.get("status"), ""),
            "reason": _text(g.get("reason"), ""),
            "runId": _text(g.get("run_id"), ""),
        }
        for g in (team.get("review_gates") or [])
        if isinstance(g, dict)
    ]
    all_conflicts = [
        {
            "filePath": _text(c.get("file_path"), ""),
            "ownerRunId": _text(c.get("owner_run_id"), ""),
            "ownerAgentId": _text(c.get("owner_agent_id"), ""),
            "fileKind": _text(c.get("file_kind"), ""),
        }
        for c in (team.get("conflict_control") or [])
        if isinstance(c, dict)
    ]
    all_events = [
        {
            "eventId": _text(e.get("event_id"), ""),
            "kind": _text(e.get("kind"), ""),
            "summary": _text(e.get("summary"), ""),
        }
        for e in (team.get("event_log") or [])
        if isinstance(e, dict)
    ]

    team_detail_messages, team_msg_overflow = _cap_with_overflow(all_messages, _PROJECTED_DETAIL_LIMIT)
    team_detail_evidence, team_ev_overflow = _cap_with_overflow(all_evidence, _PROJECTED_DETAIL_LIMIT)
    team_detail_gates, team_gate_overflow = _cap_with_overflow(all_gates, _PROJECTED_DETAIL_LIMIT)
    team_detail_conflicts, team_conflict_overflow = _cap_with_overflow(all_conflicts, _PROJECTED_DETAIL_LIMIT)
    team_detail_events, team_event_overflow = _cap_with_overflow(all_events, _PROJECTED_DETAIL_LIMIT)

    team_task_ids = [t.get("task_id") for t in (team.get("task_board") or []) if isinstance(t, dict) and t.get("task_id")]
    team_msg_ids = [m.get("message_id") for m in (team.get("message_bus") or []) if isinstance(m, dict) and m.get("message_id")]
    team_ev_ids = [e.get("evidence_id") for e in (team.get("evidence_store") or []) if isinstance(e, dict) and e.get("evidence_id")]
    team_gate_ids = [g.get("gate_id") for g in (team.get("review_gates") or []) if isinstance(g, dict) and g.get("gate_id")]
    team_conflict_files = [c.get("file_path") for c in (team.get("conflict_control") or []) if isinstance(c, dict) and c.get("file_path")]

    gate_status_counts = _count_gate_statuses(all_gates)
    team_next_actionable_gates = _sorted_actionable_gates(all_gates)[:_PROJECTED_DETAIL_LIMIT]
    has_pending_approvals = bool(team_next_actionable_gates)
    has_pending_user_input = bool(team_next_actionable_gates)
    has_actionable_proposed_plan = any(
        _text(gate.get("status"), "").lower() in {"ready", "open"}
        for gate in team_next_actionable_gates
    )

    priority_actions = _workbench_priority_actions(actions or [], base_url)

    workbench_action_ids = [a.get("actionId") for a in priority_actions if a.get("actionId")]
    workbench_action_details = priority_actions

    ready_command_workbench_actions = [
        a for a in workbench_action_details
        if _text(a.get("status"), "").lower() == "ready"
        and _text(a.get("command"), "").strip()
    ]
    has_workbench_actionable = bool(ready_command_workbench_actions)

    has_pending_approvals = has_pending_approvals or has_workbench_actionable
    has_pending_user_input = has_pending_user_input or has_workbench_actionable
    has_actionable_proposed_plan = has_actionable_proposed_plan or has_workbench_actionable

    web_ai_messages = [m for m in all_messages if _is_web_ai_local_agent_item(m)][:5]
    web_ai_evidence = [e for e in all_evidence if _is_web_ai_local_agent_item(e)][:5]
    web_ai_gates = [g for g in all_gates if _is_web_ai_local_agent_item(g)][:5]
    web_ai_events = [e for e in all_events if _is_web_ai_local_agent_item(e)][:5]

    return {
        "id": _GLOBAL_COORDINATOR_THREAD_ID,
        "projectId": project_id,
        "title": "DevFrame Global Coordinator",
        "threadKind": "global_coordinator",
        "coordinatorScope": "global",
        "projectBinding": _project_binding("global_coordinator", project_id),
        "threadListPriority": _thread_list_priority("global_coordinator"),
        "threadListSummary": _thread_list_summary(
            thread_kind="global_coordinator",
            title="DevFrame Global Coordinator",
            project_id=project_id,
            provider="devframe",
            role="global-coordinator",
            status="idle",
        ),
        "modelSelection": {
            "instanceId": "devframe-team-workbench",
            "model": "devframe-team-workbench",
        },
        "runtimeMode": "approval-required",
        "interactionMode": "plan",
        "branch": None,
        "worktreePath": None,
        "latestTurn": None,
        "createdAt": updated_at,
        "updatedAt": updated_at,
        "archivedAt": None,
        "session": {
            "threadId": _GLOBAL_COORDINATOR_THREAD_ID,
            "status": "idle",
            "providerName": "devframe",
            "runtimeMode": "approval-required",
            "activeTurnId": None,
            "lastError": None,
            "updatedAt": updated_at,
        },
        "latestUserMessageAt": None,
        "hasPendingApprovals": has_pending_approvals,
        "hasPendingUserInput": has_pending_user_input,
        "hasActionableProposedPlan": has_actionable_proposed_plan,
        "devframe": {
            "provider": "devframe",
            "agentRole": "global-coordinator",
            "bindingId": "",
            "runId": "",
            "taskSpecId": "",
            "messageCount": 0,
            "toolCallCount": 0,
            "changedFiles": [],
            "diffSummary": "",
            "relatedRunIds": [],
            "gateIds": [],
            "actionIds": workbench_action_ids,
            "actionDetails": workbench_action_details,
            "evidenceRefs": [],
            "evidenceRefOverflow": 0,
            "teamTaskIds": team_task_ids,
            "teamMessageIds": team_msg_ids,
            "teamEvidenceIds": team_ev_ids,
            "teamReviewGateIds": team_gate_ids,
            "teamConflictFiles": team_conflict_files,
            "teamDetailMessages": team_detail_messages,
            "teamDetailMessageOverflow": team_msg_overflow,
            "teamDetailEvidence": team_detail_evidence,
            "teamDetailEvidenceOverflow": team_ev_overflow,
            "teamDetailGates": team_detail_gates,
            "teamDetailGateOverflow": team_gate_overflow,
            "teamReviewGateStatusCounts": gate_status_counts,
            "teamNextActionableGates": team_next_actionable_gates,
            "teamDetailConflicts": team_detail_conflicts,
            "teamDetailConflictOverflow": team_conflict_overflow,
            "teamDetailEvents": team_detail_events,
            "teamDetailEventOverflow": team_event_overflow,
            "workbenchPriorityActions": priority_actions,
            "workbenchWebAiMessages": web_ai_messages,
            "workbenchWebAiEvidence": web_ai_evidence,
            "workbenchWebAiGates": web_ai_gates,
            "workbenchWebAiEvents": web_ai_events,
        },
    }


def _team_workbench_summary_lines(
    team: dict[str, Any],
    devframe: dict[str, Any],
    updated_at: str,
) -> list[str]:
    agent_count = len(team.get("agent_registry") or [])
    task_count = len(team.get("task_board") or [])
    message_count = len(team.get("message_bus") or [])
    evidence_count = len(team.get("evidence_store") or [])
    gate_count = len(team.get("review_gates") or [])
    conflict_count = len(team.get("conflict_control") or [])
    event_count = len(team.get("event_log") or [])

    gate_status_counts = dict(devframe.get("teamReviewGateStatusCounts", {}))
    next_actionable_gates = devframe.get("teamNextActionableGates", [])

    lines = [
        "### DevFrame Global Coordinator",
        "",
        "- This thread is the global coordinator inbox.",
        "- New coordinator-owned goals must bind to a project before execution.",
        "",
        f"- Agents: {agent_count}",
        f"- Tasks: {task_count}",
        f"- Messages: {message_count}",
        f"- Evidence refs: {evidence_count}",
    ]
    if gate_status_counts:
        gate_parts = []
        for key in ["pass", "blocked/failed", "open/ready/needs_human", "unknown"]:
            if key in gate_status_counts:
                gate_parts.append(f"{key}: {gate_status_counts[key]}")
        lines.append("- Review gates: " + "; ".join(gate_parts))
    else:
        lines.append("- Review gates: 0")
    lines.append(f"- Conflicts: {conflict_count}")
    lines.append(f"- Recent events: {event_count}")

    workbench_priority = devframe.get("workbenchPriorityActions", [])
    if workbench_priority:
        lines.extend(_render_workbench_action_lines(workbench_priority))

    web_ai_messages = devframe.get("workbenchWebAiMessages", [])
    web_ai_evidence = devframe.get("workbenchWebAiEvidence", [])
    web_ai_gates = devframe.get("workbenchWebAiGates", [])
    web_ai_events = devframe.get("workbenchWebAiEvents", [])
    if web_ai_messages or web_ai_evidence or web_ai_gates or web_ai_events:
        lines.extend(["", "#### Recent WebGPT / MCP Team Activity", ""])
        lines.extend(_render_web_ai_team_activity_lines(web_ai_messages, web_ai_evidence, web_ai_gates, web_ai_events))
        lines.append("")

    lines.extend(_render_team_detail_digest(
        devframe.get("teamDetailMessages", []),
        devframe.get("teamDetailEvidence", []),
        devframe.get("teamDetailGates", []),
        devframe.get("teamDetailConflicts", []),
        devframe.get("teamDetailEvents", []),
        message_total=len(devframe.get("teamDetailMessages", [])) + devframe.get("teamDetailMessageOverflow", 0),
        evidence_total=len(devframe.get("teamDetailEvidence", [])) + devframe.get("teamDetailEvidenceOverflow", 0),
        gate_total=len(devframe.get("teamDetailGates", [])) + devframe.get("teamDetailGateOverflow", 0),
        conflict_total=len(devframe.get("teamDetailConflicts", [])) + devframe.get("teamDetailConflictOverflow", 0),
        event_total=len(devframe.get("teamDetailEvents", [])) + devframe.get("teamDetailEventOverflow", 0),
    ))

    next_actions = []
    for gate in next_actionable_gates:
        status = _text(gate.get("status"), "").lower()
        if status in {"blocked", "failed", "error"} or status not in {"pass", "passed", "success", "complete", "completed"}:
            gid = _text(gate.get("gateId"), "")
            kind = _text(gate.get("kind"), "")
            reason = _text(gate.get("reason"), "")
            open_url = _text(gate.get("openUrl"), "")
            if open_url:
                line = f"[`{gid}`]({open_url}) [{kind}]: {status}"
            else:
                line = f"`{gid}` [{kind}]: {status}"
            if reason:
                line += f" - {reason}"
            next_actions.append(f"  - {line}")
    if next_actions:
        lines.extend(["", "#### Next required review/actions", ""])
        lines.extend(next_actions)
    lines.append("")
    return lines


def _team_workbench_proposed_plan(team: dict[str, Any], updated_at: str) -> str:
    agent_count = len(team.get("agent_registry") or [])
    task_board = team.get("task_board") or []
    task_count = len(task_board)
    message_count = len(team.get("message_bus") or [])
    evidence_count = len(team.get("evidence_store") or [])
    gate_count = len(team.get("review_gates") or [])
    conflict_count = len(team.get("conflict_control") or [])
    event_count = len(team.get("event_log") or [])
    methodologies = sorted({
        _text((task.get("methodology") or {}).get("skill_id"), "")
        for task in task_board if isinstance(task, dict)
        if isinstance(task.get("methodology"), dict) and _text((task.get("methodology") or {}).get("skill_id"), "")
    })
    lines = [
        "# DevFrame Global Coordinator",
        "",
        f"- Agents: {agent_count}",
        f"- Tasks: {task_count}",
    ]
    if methodologies:
        lines.append(f"- Methodologies: {', '.join(methodologies)}")
    lines.extend([
        f"- Messages: {message_count}",
        f"- Evidence refs: {evidence_count}",
        f"- Review gates: {gate_count}",
        f"- Conflicts: {conflict_count}",
        f"- Recent events: {event_count}",
        "- Write policy: read-only from T3 until a DevFrame gate authorizes mutation.",
    ])
    return "\n".join(lines)


def _thread_title(session: dict[str, Any]) -> str:
    role = _text(session.get("agent_role"), "agent")
    provider = _text(session.get("provider"), "provider")
    run_id = _text(session.get("run_id"), "")
    if run_id:
        return f"{role} / {provider} / {run_id}"
    return f"{role} / {provider}"


def _approval_activities(
    thread_id: str,
    action_details: list[dict[str, str]],
    updated_at: str,
) -> list[dict[str, Any]]:
    activities: list[dict[str, Any]] = []
    sequence = 3
    seen_ids: set[str] = set()
    for action in action_details:
        status = _text(action.get("status"), "").lower()
        if status != "ready":
            continue
        command = _text(action.get("command"), "")
        if not command:
            continue
        action_id = _text(action.get("actionId"), "")
        if not action_id or action_id in seen_ids:
            continue
        seen_ids.add(action_id)
        request_id = f"{thread_id}-{action_id}"
        detail = _text(action.get("detail"), "")
        label = _text(action.get("label"), "action")
        summary = f"Pending approval: {label}"
        if detail:
            summary = f"{summary} ({detail})"
        activities.append({
            "id": f"{thread_id}-approval-{action_id}",
            "tone": "approval",
            "kind": "approval.requested",
            "summary": summary,
            "payload": {
                "requestId": request_id,
                "requestKind": "command",
                "detail": detail or None,
                "actionId": action_id,
                "actionStatus": _text(action.get("status"), ""),
                "actionPriority": _text(action.get("priority"), ""),
                "command": _text(action.get("command"), ""),
                "openUrl": _text(action.get("openUrl"), ""),
                "handoffUrl": _text(action.get("handoffUrl"), ""),
                "writePolicy": "read-only",
            },
            "turnId": None,
            "sequence": sequence,
            "createdAt": updated_at,
        })
        sequence += 1
    return activities


def _evidence_activities(
    thread_id: str,
    evidence_refs: list[str],
    updated_at: str,
) -> list[dict[str, Any]]:
    if not evidence_refs:
        return []
    return [{
        "id": f"{thread_id}-evidence",
        "tone": "tool",
        "kind": "devframe.evidence.projected",
        "summary": f"Evidence: {len(evidence_refs)} reference(s)",
        "payload": {"refs": evidence_refs, "count": len(evidence_refs)},
        "turnId": None,
        "sequence": 0,
        "createdAt": updated_at,
    }]


def _gate_activities(
    thread_id: str,
    gate_details: list[dict[str, Any]],
    updated_at: str,
) -> list[dict[str, Any]]:
    if not gate_details:
        return []
    tones: set[str] = set()
    activities: list[dict[str, Any]] = []
    for gd in gate_details:
        status = _text(gd.get("status"), "")
        tone = _gate_status_tone(status)
        tones.add(tone)
        activities.append({
            "id": f"""{thread_id}-gate-{_text(gd.get("gateId"), "unnamed")}""",
            "tone": tone,
            "kind": "devframe.gate.projected",
            "summary": f"""Gate: {_text(gd.get("gateId"), "unnamed")} ({status})""",
            "payload": {
                "gateId": _text(gd.get("gateId"), ""),
                "kind": _text(gd.get("kind"), ""),
                "status": status,
                "count": len(gate_details),
            },
            "turnId": None,
            "sequence": 0,
            "createdAt": updated_at,
        })
    return activities


def _gate_status_tone(status: str) -> str:
    s = status.strip().lower()
    if s in {"blocked", "failed", "error"}:
        return "error"
    if s in {"open", "pending", "waiting"}:
        return "approval"
    if s in {"pass", "passed", "success", "complete", "completed"}:
        return "info"
    return "tool"


def _readable_team_messages(
    run_id: str,
    related_run_ids: list[str],
    team_message_bus: dict[str, list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for rid in [run_id] + related_run_ids:
        for msg in team_message_bus.get(rid, []):
            if isinstance(msg, dict) and msg.get("message_id"):
                items.append({
                    "messageId": _text(msg.get("message_id"), ""),
                    "fromRole": _text(msg.get("from_role"), ""),
                    "toRole": _text(msg.get("to_role"), ""),
                    "kind": _text(msg.get("kind"), ""),
                    "summary": _text(msg.get("summary"), ""),
                })
    return items


def _readable_team_methodologies(
    run_id: str,
    related_run_ids: list[str],
    team_task_board: dict[str, dict[str, Any]],
) -> list[str]:
    skills: list[str] = []
    for rid in [run_id] + related_run_ids:
        task = team_task_board.get(rid)
        if isinstance(task, dict) and isinstance(task.get("methodology"), dict):
            skill_id = _text(task["methodology"].get("skill_id"), "")
            if skill_id:
                skills.append(skill_id)
    return sorted(_unique(skills))


def _readable_team_evidence(
    run_id: str,
    related_run_ids: list[str],
    team_evidence_store: dict[str, list[dict[str, Any]]],
    base_url: str = "",
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for rid in [run_id] + related_run_ids:
        for ev in team_evidence_store.get(rid, []):
            if isinstance(ev, dict) and ev.get("evidence_id"):
                ref_path = str(ev.get("ref_path") or "")
                detail = _evidence_ref_detail(ref_path, base_url)
                items.append({
                    "evidenceId": _text(ev.get("evidence_id"), ""),
                    "refType": _text(ev.get("ref_type"), ""),
                    "refPath": detail["refPath"],
                    "openPath": detail["openPath"],
                    "openUrl": detail["openUrl"],
                })
    return items


def _readable_team_gates(
    run_id: str,
    related_run_ids: list[str],
    team_review_gates: dict[str, list[dict[str, Any]]],
    base_url: str = "",
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for rid in [run_id] + related_run_ids:
        for gate in team_review_gates.get(rid, []):
            if isinstance(gate, dict) and gate.get("gate_id"):
                gate_id = _text(gate.get("gate_id"), "")
                open_path = f"/review-gates/open?gate_id={quote(gate_id)}" if gate_id else ""
                open_url = f"{base_url}{open_path}" if base_url and open_path else ""
                items.append({
                    "gateId": gate_id,
                    "kind": _text(gate.get("kind"), ""),
                    "status": _text(gate.get("status"), ""),
                    "reason": _text(gate.get("reason"), ""),
                    "runId": _text(gate.get("run_id"), ""),
                    "openPath": open_path,
                    "openUrl": open_url,
                })
    return items


def _readable_team_conflicts(
    run_id: str,
    related_run_ids: list[str],
    team_conflict_control: dict[str, list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for rid in [run_id] + related_run_ids:
        for entry in team_conflict_control.get(rid, []):
            if isinstance(entry, dict) and entry.get("file_path"):
                items.append({
                    "filePath": _text(entry.get("file_path"), ""),
                    "ownerRunId": _text(entry.get("owner_run_id"), ""),
                    "ownerAgentId": _text(entry.get("owner_agent_id"), ""),
                    "fileKind": _text(entry.get("file_kind"), ""),
                })
    return items


def _readable_team_events(
    run_id: str,
    related_run_ids: list[str],
    team_event_log: dict[str, list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for rid in [run_id] + related_run_ids:
        for event in team_event_log.get(rid, []):
            if isinstance(event, dict) and event.get("event_id"):
                items.append({
                    "eventId": _text(event.get("event_id"), ""),
                    "kind": _text(event.get("kind"), ""),
                    "summary": _text(event.get("summary"), ""),
                })
    return items


def _team_context_activities(
    thread_id: str,
    team_task_ids: list[str],
    team_detail_messages: list[dict[str, Any]],
    team_detail_evidence: list[dict[str, Any]],
    team_detail_gates: list[dict[str, Any]],
    team_detail_conflicts: list[dict[str, Any]],
    team_detail_events: list[dict[str, Any]],
    updated_at: str,
) -> list[dict[str, Any]]:
    activities: list[dict[str, Any]] = []
    if team_task_ids:
        activities.append({
            "id": f"{thread_id}-team-tasks",
            "tone": "tool",
            "kind": "devframe.team.task.projected",
            "summary": f"Team Tasks: {len(team_task_ids)} active",
            "payload": {"taskIds": team_task_ids, "count": len(team_task_ids)},
            "turnId": None,
            "sequence": 0,
            "createdAt": updated_at,
        })
    for msg in team_detail_messages:
        mid = _text(msg.get("messageId"), "")
        fr = _text(msg.get("fromRole"), "")
        to = _text(msg.get("toRole"), "")
        kind = _text(msg.get("kind"), "")
        summary = _text(msg.get("summary"), "")
        activities.append({
            "id": f"{thread_id}-team-msg-{mid}",
            "tone": "info",
            "kind": "devframe.team.message.projected",
            "summary": f"{fr} -> {to} [{kind}]: {summary}",
            "payload": {"messageId": mid, "fromRole": fr, "toRole": to, "kind": kind},
            "turnId": None,
            "sequence": 0,
            "createdAt": updated_at,
        })
    for ev in team_detail_evidence:
        eid = _text(ev.get("evidenceId"), "")
        ref_type = _text(ev.get("refType"), "")
        ref_path = _text(ev.get("refPath"), "")
        activities.append({
            "id": f"{thread_id}-team-ev-{eid}",
            "tone": "tool",
            "kind": "devframe.team.evidence.projected",
            "summary": f"Evidence [{ref_type}]: {ref_path}",
            "payload": {"evidenceId": eid, "refType": ref_type, "refPath": ref_path},
            "turnId": None,
            "sequence": 0,
            "createdAt": updated_at,
        })
    for gate in team_detail_gates:
        gid = _text(gate.get("gateId"), "")
        kind = _text(gate.get("kind"), "")
        status = _text(gate.get("status"), "")
        reason = _text(gate.get("reason"), "")
        tone = _gate_status_tone(status)
        activities.append({
            "id": f"{thread_id}-team-gate-{gid}",
            "tone": tone,
            "kind": "devframe.team.gate.projected",
            "summary": f"Review Gate [{kind}]: {status}" + (f" - {reason}" if reason else ""),
            "payload": {"gateId": gid, "kind": kind, "status": status, "reason": reason},
            "turnId": None,
            "sequence": 0,
            "createdAt": updated_at,
        })
    for conf in team_detail_conflicts:
        file_path = _text(conf.get("filePath"), "")
        owner_agent = _text(conf.get("ownerAgentId"), "")
        file_kind = _text(conf.get("fileKind"), "")
        activities.append({
            "id": f"{thread_id}-team-conf-{file_path}",
            "tone": "error",
            "kind": "devframe.team.conflict.projected",
            "summary": f"Conflict [{file_kind}]: {file_path} (owner: {owner_agent})",
            "payload": {"filePath": file_path, "ownerAgentId": owner_agent, "fileKind": file_kind},
            "turnId": None,
            "sequence": 0,
            "createdAt": updated_at,
        })
    for ev in team_detail_events:
        eid = _text(ev.get("eventId"), "")
        kind = _text(ev.get("kind"), "")
        summary = _text(ev.get("summary"), "")
        tone = "info"
        if "failed" in kind.lower() or "fail" in kind.lower() or "blocked" in kind.lower():
            tone = "error"
        activities.append({
            "id": f"{thread_id}-team-event-{eid}",
            "tone": tone,
            "kind": "devframe.team.event.projected",
            "summary": f"Event [{kind}]: {summary}",
            "payload": {"eventId": eid, "kind": kind},
            "turnId": None,
            "sequence": 0,
            "createdAt": updated_at,
        })
    return activities


_DETAIL_DIGEST_MAX_ITEMS = 3
_PROJECTED_DETAIL_LIMIT = 10


def _count_gate_statuses(gates: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for gate in gates:
        status = _text(gate.get("status"), "").lower()
        if status in {"pass", "passed", "success", "complete", "completed"}:
            counts["pass"] = counts.get("pass", 0) + 1
        elif status in {"blocked", "failed", "error"}:
            counts["blocked/failed"] = counts.get("blocked/failed", 0) + 1
        elif status in {"open", "ready", "needs_human", "needs_review", "pending", "waiting"}:
            counts["open/ready/needs_human"] = counts.get("open/ready/needs_human", 0) + 1
        else:
            counts["unknown"] = counts.get("unknown", 0) + 1
    return counts


_GATE_ACTIONABLE_PRIORITY = {
    "blocked": 0,
    "failed": 0,
    "error": 0,
    "open": 1,
    "ready": 1,
    "needs_human": 1,
    "needs_review": 1,
    "pending": 1,
    "waiting": 1,
}


def _sorted_actionable_gates(gates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    actionable = set(_GATE_ACTIONABLE_PRIORITY)
    indexed = [
        (i, g)
        for i, g in enumerate(gates)
        if _text(g.get("status"), "").lower() in actionable
    ]
    return [
        gate
        for _, gate in sorted(
            indexed,
            key=lambda item: (
                _GATE_ACTIONABLE_PRIORITY.get(_text(item[1].get("status"), "").lower(), 2),
                item[0],
            ),
        )
    ]


def _cap_with_overflow(items: list[Any], limit: int) -> tuple[list[Any], int]:
    if len(items) <= limit:
        return items, 0
    return items[:limit], len(items) - limit


def _is_large_synthetic_reviewer_session(thread_id: str, devframe: dict[str, Any]) -> bool:
    if thread_id != "web-gpt-review-board-session":
        return False
    total = (
        len(devframe.get("teamDetailMessages", []))
        + len(devframe.get("teamDetailEvidence", []))
        + len(devframe.get("teamDetailGates", []))
        + len(devframe.get("teamDetailConflicts", []))
        + len(devframe.get("teamDetailEvents", []))
    )
    return total > 20


def _render_team_detail_digest(
    team_detail_messages: list[dict[str, Any]],
    team_detail_evidence: list[dict[str, Any]],
    team_detail_gates: list[dict[str, Any]],
    team_detail_conflicts: list[dict[str, Any]],
    team_detail_events: list[dict[str, Any]],
    message_total: int | None = None,
    evidence_total: int | None = None,
    gate_total: int | None = None,
    conflict_total: int | None = None,
    event_total: int | None = None,
) -> list[str]:
    lines: list[str] = []

    def _summary(category: str, items: list[dict[str, Any]], render_item, total: int | None = None) -> None:
        total = total if total is not None else len(items)
        if total == 0:
            return
        omitted = max(0, total - _DETAIL_DIGEST_MAX_ITEMS)
        lines.append(f"- **{category}**: {total} item(s), omitted {omitted} of {total} total")
        for item in items[:_DETAIL_DIGEST_MAX_ITEMS]:
            lines.append(f"  - {render_item(item)}")
        if omitted > 0:
            lines.append(f"  - ... omitted {omitted} of {total} total")

    _summary(
        "Team Communication",
        team_detail_messages,
        lambda m: f"{_text(m.get('fromRole'), '')} -> {_text(m.get('toRole'), '')} [{_text(m.get('kind'), '')}]: {_text(m.get('summary'), '')}",
        total=message_total,
    )
    def _render_evidence_item(e: dict[str, Any]) -> str:
        ref_type = _text(e.get("refType"), "")
        ref_path = _text(e.get("refPath"), "")
        open_url = _text(e.get("openUrl"), "")
        if open_url:
            return f"[{ref_type}] [{ref_path}]({open_url})"
        return f"[{ref_type}] `{ref_path}`"

    _summary(
        "Evidence",
        team_detail_evidence,
        _render_evidence_item,
        total=evidence_total,
    )
    def _render_gate_item(g: dict[str, Any]) -> str:
        gid = _text(g.get("gateId"), "")
        kind = _text(g.get("kind"), "")
        status = _text(g.get("status"), "")
        reason = _text(g.get("reason"), "")
        open_url = _text(g.get("openUrl"), "")
        if open_url:
            return f"[`{gid}`]({open_url}) [{kind}] {status}" + (f" - {reason}" if reason else "")
        return f"`{gid}` [{kind}] {status}" + (f" - {reason}" if reason else "")

    _summary(
        "Review Gates",
        team_detail_gates,
        _render_gate_item,
        total=gate_total,
    )
    _summary(
        "Conflicts",
        team_detail_conflicts,
        lambda c: f"`{_text(c.get('filePath'), '')}` [{_text(c.get('fileKind'), '')}] (owner: {_text(c.get('ownerAgentId'), '')})",
        total=conflict_total,
    )
    _summary(
        "Events",
        team_detail_events,
        lambda e: f"[{_text(e.get('kind'), '')}] {_text(e.get('summary'), '')}",
        total=event_total,
    )
    return lines


def _review_board_summary(
    thread_id: str,
    devframe: dict[str, Any],
    action_details: list[dict[str, str]],
    updated_at: str,
    gate_total: int | None = None,
    event_total: int | None = None,
) -> list[str]:
    if thread_id != "web-gpt-review-board-session":
        return []
    team_task_ids = _strings(devframe.get("teamTaskIds"))
    team_msg_ids = _strings(devframe.get("teamMessageIds"))
    team_ev_ids = _strings(devframe.get("teamEvidenceIds"))
    team_gate_ids = _strings(devframe.get("teamReviewGateIds"))
    team_conflict_files = _strings(devframe.get("teamConflictFiles"))
    team_detail_gates = devframe.get("teamDetailGates", [])
    team_detail_events = devframe.get("teamDetailEvents", [])
    gate_status_counts = dict(devframe.get("teamReviewGateStatusCounts", {}))
    next_actionable_gates = devframe.get("teamNextActionableGates", [])
    if not gate_status_counts:
        for gate in team_detail_gates:
            status = _text(gate.get("status"), "").lower()
            if status in {"pass", "passed", "success", "complete", "completed"}:
                gate_status_counts["pass"] = gate_status_counts.get("pass", 0) + 1
            elif status in {"blocked", "failed", "error"}:
                gate_status_counts["blocked/failed"] = gate_status_counts.get("blocked/failed", 0) + 1
            else:
                gate_status_counts["unknown"] = gate_status_counts.get("unknown", 0) + 1
        if gate_total is not None and len(team_detail_gates) < gate_total:
            gate_status_counts["unknown"] = gate_status_counts.get("unknown", 0) + (gate_total - len(team_detail_gates))
    lines = [
        "### Review Board Summary",
        "",
        f"- Team tasks: {len(team_task_ids)}",
        f"- Messages: {len(team_msg_ids)}",
        f"- Evidence refs: {len(team_ev_ids)}",
    ]
    if gate_status_counts:
        gate_parts = []
        for key in ["pass", "blocked/failed", "open/ready/needs_human", "unknown"]:
            if key in gate_status_counts:
                gate_parts.append(f"{key}: {gate_status_counts[key]}")
        lines.append("- Review gates: " + "; ".join(gate_parts))
    else:
        lines.append("- Review gates: 0")
    lines.append(f"- Conflicts: {len(team_conflict_files)}")
    lines.append(f"- Recent events: {event_total if event_total is not None else len(team_detail_events)}")
    next_actions = []
    for gate in next_actionable_gates:
        status = _text(gate.get("status"), "").lower()
        if status in {"blocked", "failed", "error"}:
            gid = _text(gate.get("gateId"), "")
            kind = _text(gate.get("kind"), "")
            reason = _text(gate.get("reason"), "")
            open_url = _text(gate.get("openUrl"), "")
            if open_url:
                line = f"[`{gid}`]({open_url}) [{kind}]: {status}"
            else:
                line = f"`{gid}` [{kind}]: {status}"
            if reason:
                line += f" - {reason}"
            next_actions.append(f"  - {line}")
        elif status not in {"pass", "passed", "success", "complete", "completed"}:
            gid = _text(gate.get("gateId"), "")
            kind = _text(gate.get("kind"), "")
            reason = _text(gate.get("reason"), "")
            open_url = _text(gate.get("openUrl"), "")
            if open_url:
                line = f"[`{gid}`]({open_url}) [{kind}]: {status}"
            else:
                line = f"`{gid}` [{kind}]: {status}"
            if reason:
                line += f" - {reason}"
            next_actions.append(f"  - {line}")
    for action in action_details:
        status = _text(action.get("status"), "").lower()
        if status == "ready":
            action_id = _text(action.get("actionId"), "")
            label = _text(action.get("label"), "")
            next_actions.append(f"  - `{action_id}`: {label}")
    if next_actions:
        lines.extend(["", "#### Next required actions", ""])
        lines.extend(next_actions)
    lines.append("")
    return lines


def _thread_detail(
    thread_shell: dict[str, Any],
    updated_at: str,
    team: dict[str, Any] | None = None,
    *,
    runtime_dir: str | Path | None = None,
) -> dict[str, Any]:
    devframe = thread_shell.get("devframe", {})
    if not isinstance(devframe, dict):
        devframe = {}
    thread_id = _text(thread_shell.get("id"), "session")
    evidence_ref_objects = [ev for ev in devframe.get("evidenceRefs", []) if isinstance(ev, dict)]
    evidence_refs = [_text(ev.get("refPath"), "") for ev in evidence_ref_objects]
    gate_ids = _strings(devframe.get("gateIds"))
    action_ids = _strings(devframe.get("actionIds"))
    action_details = _action_detail_list(devframe.get("actionDetails"))
    run_id = _text(devframe.get("runId"), "")
    task_spec_id = _text(devframe.get("taskSpecId"), "")
    status = _text(thread_shell.get("session", {}).get("status") if isinstance(thread_shell.get("session"), dict) else "", "idle")
    if _is_team_workbench_session(thread_id) and isinstance(team, dict):
        details = _team_workbench_summary_lines(team, devframe, updated_at)
    else:
        summary_lines = _review_board_summary(
            thread_id, devframe, action_details, updated_at,
            gate_total=len(devframe.get("teamDetailGates", [])) + devframe.get("teamDetailGateOverflow", 0),
            event_total=len(devframe.get("teamDetailEvents", [])) + devframe.get("teamDetailEventOverflow", 0),
        )
        details = summary_lines + [
            "### DevFrame Agent Session",
            "",
            f"- Provider: {_text(devframe.get('provider'), 'opencode')}",
            f"- Agent role: {_text(devframe.get('agentRole'), 'executor')}",
            f"- Run: `{run_id or 'not linked'}`",
            f"- TaskSpec: `{task_spec_id or 'not linked'}`",
            f"- Status: {status}",
        ]
    details.append(f"- Conversation kind: {_thread_kind_label(_text(thread_shell.get('threadKind'), ''))}")
    details.append(f"- Coordinator scope: {_text(thread_shell.get('coordinatorScope'), 'none')}")
    details.append(f"- Project binding: {_project_binding_summary(thread_shell.get('projectBinding'))}")
    if gate_ids:
        details.append("- Gates: " + ", ".join(f"`{gate_id}`" for gate_id in gate_ids))
    if action_ids:
        details.append("- Actions: " + ", ".join(f"`{action_id}`" for action_id in action_ids))
    if action_details:
        details.append("- Next actions:")
        for action in action_details:
            details.append(
                f"  - `{action['actionId']}` [{action['status']}/{action['priority']}]: {_markdown_text(action['label'])}"
            )
            if action["command"]:
                details.append(f"    - Command: `{action['command']}`")
            if action["openUrl"]:
                details.append(f"    - Open action: [open controlled action]({action['openUrl']})")
    if evidence_refs:
        details.append("- Evidence:")
        for ev in evidence_ref_objects:
            ref_path = _text(ev.get("refPath"), "")
            open_url = _text(ev.get("openUrl"), "")
            if open_url:
                details.append(f"  - [{ref_path}]({open_url})")
            else:
                details.append(f"  - `{ref_path}`")
        evidence_ref_overflow = devframe.get("evidenceRefOverflow", 0)
        if evidence_ref_overflow > 0:
            details.append(f"- ... omitted: {evidence_ref_overflow} more evidence reference(s)")
    team_detail_messages = devframe.get("teamDetailMessages", [])
    team_detail_evidence = devframe.get("teamDetailEvidence", [])
    team_detail_gates = devframe.get("teamDetailGates", [])
    team_detail_conflicts = devframe.get("teamDetailConflicts", [])
    team_detail_events = devframe.get("teamDetailEvents", [])
    team_msg_overflow = devframe.get("teamDetailMessageOverflow", 0)
    team_ev_overflow = devframe.get("teamDetailEvidenceOverflow", 0)
    team_gate_overflow = devframe.get("teamDetailGateOverflow", 0)
    team_conflict_overflow = devframe.get("teamDetailConflictOverflow", 0)
    team_event_overflow = devframe.get("teamDetailEventOverflow", 0)
    if not _is_team_workbench_session(thread_id) and (team_detail_messages or team_detail_evidence or team_detail_gates or team_detail_conflicts or team_detail_events):
            details.extend(["", "## Team Communication", ""])
            team_detail_methodologies = devframe.get("teamDetailMethodologies", [])
            if team_detail_methodologies:
                details.append(f"- Methodologies: {', '.join(team_detail_methodologies)}")
            if _is_large_synthetic_reviewer_session(thread_id, devframe):
                details.extend(_render_team_detail_digest(
                    team_detail_messages,
                    team_detail_evidence,
                    team_detail_gates,
                    team_detail_conflicts,
                    team_detail_events,
                    message_total=len(team_detail_messages) + team_msg_overflow,
                    evidence_total=len(team_detail_evidence) + team_ev_overflow,
                    gate_total=len(team_detail_gates) + team_gate_overflow,
                    conflict_total=len(team_detail_conflicts) + team_conflict_overflow,
                    event_total=len(team_detail_events) + team_event_overflow,
                ))
            else:
                for msg in team_detail_messages:
                    fr = _text(msg.get("fromRole"), "")
                    to = _text(msg.get("toRole"), "")
                    kind = _text(msg.get("kind"), "")
                    summary = _text(msg.get("summary"), "")
                    details.append(f"- **{fr} -> {to}** [{kind}]: {summary}")
                if team_detail_evidence:
                    details.append("- **Evidence**:")
                    for ev in team_detail_evidence:
                        ref_type = _text(ev.get("refType"), "")
                        ref_path = _text(ev.get("refPath"), "")
                        open_url = _text(ev.get("openUrl"), "")
                        if open_url:
                            details.append(f"  - [{ref_type}] [{ref_path}]({open_url})")
                        else:
                            details.append(f"  - [{ref_type}] `{ref_path}`")
                if team_detail_gates:
                    details.append("- **Review Gates**:")
                    for gate in team_detail_gates:
                        gid = _text(gate.get("gateId"), "")
                        kind = _text(gate.get("kind"), "")
                        status = _text(gate.get("status"), "")
                        reason = _text(gate.get("reason"), "")
                        open_url = _text(gate.get("openUrl"), "")
                        if open_url:
                            line = f"  - [`{gid}`]({open_url}) [{kind}] {status}"
                        else:
                            line = f"  - `{gid}` [{kind}] {status}"
                        if reason:
                            line += f" - {reason}"
                        details.append(line)
                if team_detail_conflicts:
                    details.append("- **Conflicts**:")
                    for conf in team_detail_conflicts:
                        fp = _text(conf.get("filePath"), "")
                        owner = _text(conf.get("ownerAgentId"), "")
                        fk = _text(conf.get("fileKind"), "")
                        details.append(f"  - `{fp}` [{fk}] (owner: {owner})")
                if team_detail_events:
                    details.append("- **Events**:")
                    for ev in team_detail_events:
                        eid = _text(ev.get("eventId"), "")
                        kind = _text(ev.get("kind"), "")
                        summary = _text(ev.get("summary"), "")
                        details.append(f"  - [{kind}] {summary}")
            overflow_parts = []
            if team_msg_overflow > 0:
                overflow_parts.append(f"{team_msg_overflow} more message(s)")
            if team_ev_overflow > 0:
                overflow_parts.append(f"{team_ev_overflow} more evidence item(s)")
            if team_gate_overflow > 0:
                overflow_parts.append(f"{team_gate_overflow} more gate(s)")
            if team_conflict_overflow > 0:
                overflow_parts.append(f"{team_conflict_overflow} more conflict(s)")
            if team_event_overflow > 0:
                overflow_parts.append(f"{team_event_overflow} more event(s)")
            if overflow_parts:
                details.append(f"- ... omitted: {', '.join(overflow_parts)}")
    message_text = "\n".join(details)
    activity_summary = (
        f"DevFrame projected {len(evidence_refs)} evidence reference(s), "
        f"{len(gate_ids)} gate(s), and {len(action_ids)} action(s)."
    )
    if _is_team_workbench_session(thread_id) and isinstance(team, dict):
        proposed_plan = _team_workbench_proposed_plan(team, updated_at)
    else:
        proposed_plan = _proposed_plan_text(thread_shell, evidence_refs, evidence_ref_objects, gate_ids, action_ids, action_details, evidence_ref_overflow=devframe.get("evidenceRefOverflow", 0))
    team_task_ids = _strings(devframe.get("teamTaskIds"))
    team_msg_ids = _strings(devframe.get("teamMessageIds"))
    team_ev_ids = _strings(devframe.get("teamEvidenceIds"))
    team_gate_ids = _strings(devframe.get("teamReviewGateIds"))
    team_conflict_files = _strings(devframe.get("teamConflictFiles"))
    team_events = devframe.get("teamDetailEvents", [])
    team_activity_summary = (
        f"Team: {len(team_task_ids)} task(s), {len(team_msg_ids)} message(s), "
        f"{len(team_ev_ids)} evidence ref(s), {len(team_gate_ids)} gate(s), "
        f"{len(team_conflict_files)} conflict file(s), {len(team_events)} event(s) linked."
    )
    approval_activities = _approval_activities(
        thread_id=thread_id,
        action_details=action_details,
        updated_at=updated_at,
    )
    if not _is_team_workbench_session(thread_id):
        thread_shell["hasPendingApprovals"] = bool(approval_activities)
    evidence_activities = _evidence_activities(thread_id, evidence_refs, updated_at)
    gate_activities = _gate_activities(thread_id, devframe.get("gateDetails", []), updated_at)
    team_context_activities = _team_context_activities(
        thread_id,
        team_task_ids,
        devframe.get("teamDetailMessages", []),
        devframe.get("teamDetailEvidence", []),
        devframe.get("teamDetailGates", []),
        devframe.get("teamDetailConflicts", []),
        devframe.get("teamDetailEvents", []),
        updated_at,
    )
    overflow_parts = []
    if team_msg_overflow > 0:
        overflow_parts.append(f"{team_msg_overflow} more message(s)")
    if team_ev_overflow > 0:
        overflow_parts.append(f"{team_ev_overflow} more evidence item(s)")
    if team_gate_overflow > 0:
        overflow_parts.append(f"{team_gate_overflow} more gate(s)")
    if team_conflict_overflow > 0:
        overflow_parts.append(f"{team_conflict_overflow} more conflict(s)")
    if team_event_overflow > 0:
        overflow_parts.append(f"{team_event_overflow} more event(s)")
    if overflow_parts:
        team_context_activities.append({
            "id": f"{thread_id}-team-overflow",
            "tone": "info",
            "kind": "devframe.team.overflow.projected",
            "summary": f"Team details truncated: {', '.join(overflow_parts)}",
            "payload": {
                "messageOverflow": team_msg_overflow,
                "evidenceOverflow": team_ev_overflow,
                "gateOverflow": team_gate_overflow,
                "conflictOverflow": team_conflict_overflow,
                "eventOverflow": team_event_overflow,
                "writePolicy": "read-only",
            },
            "turnId": None,
            "sequence": 0,
            "createdAt": updated_at,
        })
    from .conversation_intake import build_intake_activities

    intake_activities = (
        build_intake_activities(runtime_dir, thread_id, updated_at)
        if runtime_dir is not None
        else []
    )
    next_sequence = 3 + len(approval_activities)
    for activity in evidence_activities + gate_activities + team_context_activities + intake_activities:
        activity["sequence"] = next_sequence
        next_sequence += 1
    return {
        "id": thread_id,
        "projectId": thread_shell.get("projectId"),
        "title": thread_shell.get("title"),
        "threadKind": _text(thread_shell.get("threadKind"), "native_chat"),
        "coordinatorScope": _text(thread_shell.get("coordinatorScope"), "none"),
        "projectBinding": (
            thread_shell.get("projectBinding")
            if isinstance(thread_shell.get("projectBinding"), dict)
            else _project_binding("native_chat", _text(thread_shell.get("projectId"), ""))
        ),
        "threadListPriority": _safe_thread_list_priority(
            thread_shell.get("threadListPriority"),
            _text(thread_shell.get("threadKind"), "native_chat"),
        ),
        "threadListSummary": _text(thread_shell.get("threadListSummary"), ""),
        "modelSelection": thread_shell.get("modelSelection"),
        "runtimeMode": thread_shell.get("runtimeMode"),
        "interactionMode": thread_shell.get("interactionMode"),
        "branch": thread_shell.get("branch"),
        "worktreePath": thread_shell.get("worktreePath"),
        "latestTurn": thread_shell.get("latestTurn"),
        "createdAt": thread_shell.get("createdAt"),
        "updatedAt": thread_shell.get("updatedAt"),
        "archivedAt": thread_shell.get("archivedAt"),
        "deletedAt": None,
        "messages": [
            {
                "id": f"{thread_id}-devframe-summary",
                "role": "assistant",
                "text": message_text,
                "turnId": None,
                "streaming": False,
                "createdAt": updated_at,
                "updatedAt": updated_at,
            }
        ],
        "proposedPlans": [
            {
                "id": f"{thread_id}-devframe-plan",
                "turnId": None,
                "planMarkdown": proposed_plan,
                "implementedAt": None,
                "implementationThreadId": None,
                "createdAt": updated_at,
                "updatedAt": updated_at,
            }
        ],
        "activities": [
            {
                "id": f"{thread_id}-devframe-activity",
                "tone": "info",
                "kind": "devframe.session.projected",
                "summary": activity_summary,
                "payload": {
                    "runId": run_id,
                    "taskSpecId": task_spec_id,
                    "evidenceRefs": evidence_refs,
                    "gateIds": gate_ids,
                    "actionIds": action_ids,
                    "actionDetails": action_details,
                    "writePolicy": "read-only",
                },
                "turnId": None,
                "sequence": 1,
                "createdAt": updated_at,
            },
            {
                "id": f"{thread_id}-devframe-team-activity",
                "tone": "info",
                "kind": "devframe.team.projected",
                "summary": team_activity_summary,
                "payload": {
                    "teamTaskIds": team_task_ids,
                    "teamMessageIds": team_msg_ids,
                    "teamEvidenceIds": team_ev_ids,
                    "teamReviewGateIds": team_gate_ids,
                    "teamConflictFiles": team_conflict_files,
                    "teamEventCount": len(team_events),
                    "writePolicy": "read-only",
                },
                "turnId": None,
                "sequence": 2,
                "createdAt": updated_at,
            },
            *approval_activities,
            *evidence_activities,
            *gate_activities,
            *team_context_activities,
            *intake_activities,
        ],
        "checkpoints": [],
        "session": thread_shell.get("session"),
    }


def _cluster_run_thread_detail(
    thread_shell: dict[str, Any],
    runtime_dir: str | Path | None,
    updated_at: str,
) -> dict[str, Any]:
    run_id = _text((thread_shell.get("devframe") or {}).get("runId"), "")
    detail_data: dict[str, Any] = {}
    if run_id:
        try:
            from .cluster_run import cluster_run_detail

            detail_data = cluster_run_detail(runtime_dir, run_id)
        except Exception:  # noqa: BLE001 - projection fallback only
            detail_data = {}

    status = _text(detail_data.get("status"), _text(thread_shell.get("session", {}).get("status"), "idle"))
    summary = _text(detail_data.get("summary"), _text((thread_shell.get("devframe") or {}).get("diffSummary"), ""))
    messages = [m for m in detail_data.get("messages", []) if isinstance(m, dict)]
    agents = [a for a in detail_data.get("agents", []) if isinstance(a, dict)]
    action_details = _action_detail_list((thread_shell.get("devframe") or {}).get("actionDetails"))
    details = [
        "### DevFrame Goal Conversation",
        "",
        f"- Goal: {_text(thread_shell.get('title'), run_id)}",
        f"- Status: {status}",
        f"- Coordinator scope: {_text(thread_shell.get('coordinatorScope'), 'project')}",
        f"- Project binding: {_project_binding_summary(thread_shell.get('projectBinding'))}",
    ]
    if summary:
        details.append(f"- Summary: {summary}")
    if messages:
        details.extend(["", "## Coordinator Timeline", ""])
        for msg in messages:
            fr = _text(msg.get("from"), "")
            to = _text(msg.get("to"), "")
            kind = _text(msg.get("kind"), "")
            text = _text(msg.get("text"), "")
            if to:
                details.append(f"- **{fr} -> {to}** [{kind}]: {text}")
            else:
                details.append(f"- **{fr}** [{kind}]: {text}")
    if agents:
        details.extend(["", "## Agent Summary", ""])
        for agent in agents:
            details.append(
                f"- `{_text(agent.get('agentId'), '')}` shard "
                f"{agent.get('shardIndex', 0)}/{agent.get('shardCount', 0)}: "
                f"{_text(agent.get('status'), 'queued')} "
                f"(changed files: {agent.get('changedFileCount', 0)}, tokens: {agent.get('totalTokens', 0)})"
            )
    if action_details:
        details.append("- Next actions:")
        for action in action_details:
            details.append(
                f"  - `{action['actionId']}` [{action['status']}/{action['priority']}]: {_markdown_text(action['label'])}"
            )
            if action["command"]:
                details.append(f"    - Command: `{action['command']}`")

    message_text = "\n".join(details)
    activity_summary = f"Goal conversation {run_id or 'unknown'} projected from cluster-run state."
    approval_activities = _approval_activities(
        thread_id=_text(thread_shell.get("id"), run_id or "goal"),
        action_details=action_details,
        updated_at=updated_at,
    )
    from .conversation_intake import build_intake_activities

    intake_activities = (
        build_intake_activities(
            runtime_dir,
            _text(thread_shell.get("id"), run_id),
            updated_at,
        )
        if runtime_dir is not None
        else []
    )
    next_sequence = 2 + len(approval_activities)
    for activity in intake_activities:
        activity["sequence"] = next_sequence
        next_sequence += 1
    proposed_plan = "\n".join([
        "# DevFrame Goal Conversation",
        "",
        f"- Goal: {_text(thread_shell.get('title'), run_id)}",
        f"- Status: {status}",
        f"- Summary: {summary or 'Waiting for coordinator progress.'}",
    ])
    return {
        "id": thread_shell.get("id"),
        "projectId": thread_shell.get("projectId"),
        "title": thread_shell.get("title"),
        "threadKind": _text(thread_shell.get("threadKind"), "goal_conversation"),
        "coordinatorScope": _text(thread_shell.get("coordinatorScope"), "project"),
        "projectBinding": thread_shell.get("projectBinding"),
        "threadListPriority": _safe_thread_list_priority(
            thread_shell.get("threadListPriority"),
            "goal_conversation",
        ),
        "threadListSummary": _text(thread_shell.get("threadListSummary"), ""),
        "modelSelection": thread_shell.get("modelSelection"),
        "runtimeMode": thread_shell.get("runtimeMode"),
        "interactionMode": thread_shell.get("interactionMode"),
        "branch": thread_shell.get("branch"),
        "worktreePath": thread_shell.get("worktreePath"),
        "latestTurn": thread_shell.get("latestTurn"),
        "createdAt": thread_shell.get("createdAt"),
        "updatedAt": thread_shell.get("updatedAt"),
        "archivedAt": thread_shell.get("archivedAt"),
        "deletedAt": None,
        "messages": [{
            "id": f"{_text(thread_shell.get('id'), run_id)}-goal-summary",
            "role": "assistant",
            "text": message_text,
            "turnId": None,
            "streaming": False,
            "createdAt": updated_at,
            "updatedAt": updated_at,
        }],
        "proposedPlans": [{
            "id": f"{_text(thread_shell.get('id'), run_id)}-goal-plan",
            "turnId": None,
            "planMarkdown": proposed_plan,
            "implementedAt": None,
            "implementationThreadId": None,
            "createdAt": updated_at,
            "updatedAt": updated_at,
        }],
        "activities": [
            {
                "id": f"{_text(thread_shell.get('id'), run_id)}-goal-activity",
                "tone": "info",
                "kind": "devframe.goal.projected",
                "summary": activity_summary,
                "payload": {
                    "runId": run_id,
                    "status": status,
                    "writePolicy": "read-only",
                },
                "turnId": None,
                "sequence": 1,
                "createdAt": updated_at,
            },
            *approval_activities,
            *intake_activities,
        ],
        "checkpoints": [],
        "session": thread_shell.get("session"),
    }


def _proposed_plan_text(
    thread_shell: dict[str, Any],
    evidence_refs: list[str],
    evidence_ref_objects: list[dict[str, Any]],
    gate_ids: list[str],
    action_ids: list[str],
    action_details: list[dict[str, str]],
    evidence_ref_overflow: int = 0,
) -> str:
    devframe = thread_shell.get("devframe", {})
    if not isinstance(devframe, dict):
        devframe = {}
    lines = [
        "# DevFrame Read-only Agent Session",
        "",
        f"- Agent: {_text(devframe.get('agentRole'), 'executor')}",
        f"- Executor: {_text(devframe.get('provider'), 'opencode')}",
        f"- Run: `{_text(devframe.get('runId'), 'not linked')}`",
        f"- TaskSpec: `{_text(devframe.get('taskSpecId'), 'not linked')}`",
        "- Write policy: read-only from T3 until a DevFrame gate authorizes mutation.",
    ]
    if gate_ids:
        lines.append("- Gates: " + ", ".join(f"`{gate_id}`" for gate_id in gate_ids))
    if action_ids:
        lines.append("- Actions: " + ", ".join(f"`{action_id}`" for action_id in action_ids))
    if action_details:
        lines.extend(["", "## Next Actions"])
        for action in action_details:
            lines.append(
                f"- `{action['actionId']}` [{action['status']}/{action['priority']}]: {_markdown_text(action['label'])}"
            )
            if action["handoffUrl"]:
                lines.append(f"  - Handoff: [open markdown packet]({action['handoffUrl']})")
            elif action["handoffPath"]:
                lines.append(f"  - Handoff: `{action['handoffPath']}`")
            if action["openUrl"]:
                lines.append(f"  - Open action: [review / execute]({action['openUrl']})")
            if action["resumeFilter"]:
                lines.append(f"  - Resume filter: `{action['resumeFilter']}`")
            if action["command"]:
                lines.extend(["", "```powershell", action["command"], "```"])
    if evidence_refs:
        parts = []
        for ref_path in evidence_refs:
            ev = next((e for e in evidence_ref_objects if _text(e.get("refPath"), "") == ref_path), {})
            open_url = _text(ev.get("openUrl"), "")
            if open_url:
                parts.append(f"[{ref_path}]({open_url})")
            else:
                parts.append(f"`{ref_path}`")
        suffix = f" ({evidence_ref_overflow} more omitted)" if evidence_ref_overflow > 0 else ""
        lines.append("- Evidence refs: " + ", ".join(parts) + suffix)
    return "\n".join(lines)


def _provider_instance_id(session: dict[str, Any], bindings_by_id: dict[str, dict[str, Any]]) -> str:
    binding_id = _text(session.get("binding_id"), "")
    binding = bindings_by_id.get(binding_id, {})
    provider = _text(binding.get("provider"), _text(session.get("provider"), "custom"))
    return binding_id or provider


def _runtime_mode(session: dict[str, Any], pending_gate: bool) -> str:
    if pending_gate or _text(session.get("status"), "") in {"blocked", "needs_human"}:
        return "approval-required"
    return "full-access"


def _session_status(session: dict[str, Any]) -> str:
    return {
        "active": "running",
        "blocked": "ready",
        "completed": "stopped",
        "failed": "error",
        "idle": "idle",
        "needs_human": "ready",
        "unknown": "idle",
    }.get(_text(session.get("status"), "unknown"), "idle")


def _session_error(session: dict[str, Any]) -> str | None:
    if _text(session.get("status"), "") == "failed":
        return "DevFrame session failed; inspect evidenceRefs and gates."
    return None


def _gate_overlay(gate: dict[str, Any]) -> dict[str, Any]:
    return {
        "gateId": _text(gate.get("gate_id"), ""),
        "kind": _text(gate.get("kind"), ""),
        "status": _text(gate.get("status"), ""),
        "runId": _text(gate.get("run_id"), ""),
        "reason": _text(gate.get("reason"), ""),
        "nextAction": _text(gate.get("next_action"), ""),
    }


def _public_actions_by_source(actions_by_source: dict[str, list[dict[str, Any]]]) -> dict[str, list[dict[str, Any]]]:
    return {
        source_id: [
            {
                "actionId": _text(action.get("action_id"), ""),
                "priority": _text(action.get("priority"), ""),
                "status": _text(action.get("status"), ""),
                "label": _text(action.get("label"), ""),
            }
            for action in actions
        ]
        for source_id, actions in actions_by_source.items()
    }


def _items_by_single_key(items: object, key: str) -> dict[str, dict[str, Any]]:
    indexed: dict[str, dict[str, Any]] = {}
    if not isinstance(items, list):
        return indexed
    for item in items:
        if not isinstance(item, dict):
            continue
        value = str(item.get(key) or "")
        if value and value not in indexed:
            indexed[value] = item
    return indexed


def _items_by_key(items: object, key: str) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    if not isinstance(items, list):
        return grouped
    for item in items:
        if not isinstance(item, dict):
            continue
        value = str(item.get(key) or "")
        if not value:
            continue
        grouped.setdefault(value, []).append(item)
    return grouped


def _run_ids_by_path(runs: object, path_key: str) -> dict[str, list[str]]:
    indexed: dict[str, list[str]] = {}
    if not isinstance(runs, list):
        return indexed
    for run in runs:
        if not isinstance(run, dict):
            continue
        run_id = str(run.get("run_id") or "")
        path = _normalized_path_key(run.get(path_key))
        if run_id and path:
            indexed.setdefault(path, []).append(run_id)
    return indexed


def _related_run_ids(
    session: dict[str, Any],
    runs_by_id: dict[str, dict[str, Any]],
    go_runs_by_id: dict[str, dict[str, Any]],
    run_ids_by_packet_path: dict[str, list[str]],
    run_ids_by_task_spec_path: dict[str, list[str]],
) -> list[str]:
    run_id = _text(session.get("run_id"), "")
    related: list[str] = [run_id] if run_id in runs_by_id else []
    native_refs = session.get("native_refs")
    go_run_id = ""
    if isinstance(native_refs, dict):
        go_run_id = _text(native_refs.get("go_run_id"), "")
        explicit = native_refs.get("related_run_ids")
        if isinstance(explicit, list):
            related.extend(str(item) for item in explicit if item is not None)
    go_run_id = go_run_id or run_id
    go_run = go_runs_by_id.get(go_run_id, {})
    agents = go_run.get("agents", []) if isinstance(go_run, dict) else []
    if isinstance(agents, list):
        for agent in agents:
            if not isinstance(agent, dict):
                continue
            related.extend(run_ids_by_packet_path.get(_normalized_path_key(agent.get("packet_dir")), []))
            related.extend(run_ids_by_task_spec_path.get(_normalized_path_key(agent.get("task_spec_path")), []))
    for ref in _strings(session.get("evidence_refs")):
        normalized_ref = _normalized_path_key(ref)
        related.extend(run_ids_by_packet_path.get(normalized_ref, []))
        related.extend(run_ids_by_task_spec_path.get(normalized_ref, []))
    return _unique(related)


def _action_details(
    actions_by_source: dict[str, list[dict[str, Any]]],
    action_ids: list[str],
    base_url: str,
) -> list[dict[str, str]]:
    details: list[dict[str, str]] = []
    seen: set[str] = set()
    for action_id in action_ids:
        if action_id in seen:
            continue
        seen.add(action_id)
        action = next(iter(_actions_by_id(actions_by_source, action_id)), None)
        if action is None:
            continue
        details.append(_action_detail(action, base_url))
    return details


def _action_detail(action: dict[str, Any], base_url: str) -> dict[str, str]:
    action_id = _text(action.get("action_id"), "")
    handoff_path = f"/actions.md?action_id={quote(action_id)}" if action_id else ""
    handoff_url = f"{base_url}{handoff_path}" if base_url and handoff_path else ""
    open_path = f"/actions/open?action_id={quote(action_id)}" if action_id else ""
    open_url = f"{base_url}{open_path}" if base_url and open_path else ""
    resume_filter = f"devframe actions --action-id {action_id} --format markdown" if action_id else ""
    return {
        "actionId": action_id,
        "sourceType": _text(action.get("source_type"), ""),
        "sourceId": _text(action.get("source_id"), ""),
        "priority": _text(action.get("priority"), ""),
        "status": _text(action.get("status"), ""),
        "label": _text(action.get("label"), ""),
        "detail": _text(action.get("detail"), ""),
        "command": _text(action.get("command"), ""),
        "resumeFilter": resume_filter,
        "handoffPath": handoff_path,
        "handoffUrl": handoff_url,
        "openPath": open_path,
        "openUrl": open_url,
    }


def _action_detail_list(value: object) -> list[dict[str, str]]:
    if not isinstance(value, list):
        return []
    return [
        {
            "actionId": _text(item.get("actionId"), ""),
            "sourceType": _text(item.get("sourceType"), ""),
            "sourceId": _text(item.get("sourceId"), ""),
            "priority": _text(item.get("priority"), ""),
            "status": _text(item.get("status"), ""),
            "label": _text(item.get("label"), ""),
            "detail": _text(item.get("detail"), ""),
            "command": _text(item.get("command"), ""),
            "resumeFilter": _text(item.get("resumeFilter"), ""),
            "handoffPath": _text(item.get("handoffPath"), ""),
            "handoffUrl": _text(item.get("handoffUrl"), ""),
            "openPath": _text(item.get("openPath"), ""),
            "openUrl": _text(item.get("openUrl"), ""),
        }
        for item in value
        if isinstance(item, dict)
    ]


def _actions_by_id(actions_by_source: dict[str, list[dict[str, Any]]], action_id: str) -> list[dict[str, Any]]:
    return [
        action
        for actions in actions_by_source.values()
        for action in actions
        if str(action.get("action_id") or "") == action_id
    ]


def _count(value: object) -> int:
    return len(value) if isinstance(value, list) else 0


def _strings(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if item is not None]


def _text(value: object, fallback: str) -> str:
    text = str(value or "").strip()
    return text or fallback


def _clean_base_url(base_url: str | None) -> str:
    return str(base_url or "").strip().rstrip("/")


def _markdown_text(value: str) -> str:
    return value.replace("\\", "\\\\")


def _normalized_path_key(value: object) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    return text.replace("\\", "/").rstrip("/").casefold()


def _evidence_ref_detail(ref_path: str, base_url: str) -> dict[str, str]:
    safe_path = _public_safe_evidence_path(ref_path)
    open_path = f"/evidence/open?ref={quote(safe_path)}" if safe_path else ""
    open_url = f"{base_url}{open_path}" if base_url and open_path else ""
    return {
        "refPath": safe_path,
        "openPath": open_path,
        "openUrl": open_url,
    }


def _public_safe_evidence_path(path: object, cwd: Path | None = None) -> str:
    """Convert an evidence path to a public-safe display path.

    - Relative paths are preserved as-is.
    - Absolute paths under cwd become relative to cwd.
    - Other absolute paths return a safe suffix without drive root,
      user home, or leading slash.
    """
    text = str(path or "").strip()
    if not text:
        return ""

    normalized = text.replace("\\", "/")
    is_windows_absolute = bool(re.match(r"^[A-Za-z]:/", normalized))
    is_unc_absolute = normalized.startswith("//")
    is_posix_absolute = normalized.startswith("/")
    if not (is_windows_absolute or is_unc_absolute or is_posix_absolute):
        return text

    if cwd is None:
        cwd = Path.cwd()

    cwd_text = str(cwd.resolve()).replace("\\", "/").rstrip("/")
    if normalized.casefold().startswith(cwd_text.casefold() + "/"):
        return normalized[len(cwd_text) + 1:]

    path_without_root = normalized
    if is_windows_absolute:
        path_without_root = normalized[3:]
    else:
        path_without_root = normalized.lstrip("/")

    parts = [part for part in path_without_root.split("/") if part]

    sensitive_leaders = {'users', 'home', 'windows', 'program files', 'programdata', 'tmp', 'temp'}
    while parts and parts[0].lower() in sensitive_leaders:
        parts = parts[1:]

    if not parts:
        return Path(text).name

    suffix = "/".join(parts[-2:]) if len(parts) > 2 else "/".join(parts)
    return suffix


def _unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if not value or value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def _unique_gates(gates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    result: list[dict[str, Any]] = []
    for gate in gates:
        gate_id = str(gate.get("gate_id") or "")
        if not gate_id or gate_id in seen:
            continue
        seen.add(gate_id)
        result.append(gate)
    return result


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _team_task_ids_for_run(
    run_id: str,
    related_run_ids: list[str],
    team_task_board: dict[str, dict[str, Any]],
) -> list[str]:
    ids: list[str] = []
    for rid in [run_id] + related_run_ids:
        if rid and rid in team_task_board:
            ids.append(rid)
    return _unique(ids)


def _team_message_ids_for_run(
    run_id: str,
    related_run_ids: list[str],
    team_message_bus: dict[str, list[dict[str, Any]]],
) -> list[str]:
    ids: list[str] = []
    for rid in [run_id] + related_run_ids:
        for msg in team_message_bus.get(rid, []):
            if isinstance(msg, dict) and msg.get("message_id"):
                ids.append(str(msg.get("message_id")))
    return _unique(ids)


def _team_evidence_ids_for_run(
    run_id: str,
    related_run_ids: list[str],
    team_evidence_store: dict[str, list[dict[str, Any]]],
) -> list[str]:
    ids: list[str] = []
    for rid in [run_id] + related_run_ids:
        for ev in team_evidence_store.get(rid, []):
            if isinstance(ev, dict) and ev.get("evidence_id"):
                ids.append(str(ev.get("evidence_id")))
    return _unique(ids)


def _team_review_gate_ids_for_run(
    run_id: str,
    related_run_ids: list[str],
    team_review_gates: dict[str, list[dict[str, Any]]],
) -> list[str]:
    ids: list[str] = []
    for rid in [run_id] + related_run_ids:
        for gate in team_review_gates.get(rid, []):
            if isinstance(gate, dict) and gate.get("gate_id"):
                ids.append(str(gate.get("gate_id")))
    return _unique(ids)


def _team_conflict_files_for_run(
    run_id: str,
    related_run_ids: list[str],
    team_conflict_control: dict[str, list[dict[str, Any]]],
) -> list[str]:
    files: list[str] = []
    for rid in [run_id] + related_run_ids:
        for entry in team_conflict_control.get(rid, []):
            if isinstance(entry, dict) and entry.get("file_path"):
                files.append(str(entry.get("file_path")))
    return _unique(files)


def _platform_os() -> str:
    system = platform.system().lower()
    if system == "darwin":
        return "darwin"
    if system == "linux":
        return "linux"
    if system == "windows":
        return "windows"
    return "unknown"


def _platform_arch() -> str:
    machine = platform.machine().lower()
    if machine in {"amd64", "x86_64"}:
        return "x64"
    if machine in {"aarch64", "arm64"}:
        return "arm64"
    return "other"
