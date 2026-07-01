"""Minimal DevFrame MCP server (Streamable HTTP JSON-RPC, stdlib only).

Exposes DevFrame operations to an AI MCP client over the loopback dashboard at
``POST /mcp``: read the project shell and PROPOSE a governed write-back. The
server never writes to the workspace — a write-back proposal only stages a
human-gated item; applying it still requires a human approval through
``/api/t3/approval-response``. This satisfies the "no silent write" rule while
letting an AI operate the editor directly.

Targets the same protocol DevFrame's own ``mcp_live_probe`` client speaks
(initialize -> tools/list -> tools/call), responding in plain JSON.
"""
from __future__ import annotations

import json
import os
import secrets
from pathlib import Path
from typing import Any

PROTOCOL_VERSION = "2024-11-05"
SERVER_INFO = {"name": "devframe-mcp", "version": "0.1"}

# JSON-RPC error codes
_METHOD_NOT_FOUND = -32601
_INVALID_PARAMS = -32602


def resolve_mcp_token(runtime_dir: str | Path | None = None) -> str | None:
    """Return the configured DevFrame MCP access token, or None for loopback-only.

    Resolution order: ``DEVFRAME_MCP_TOKEN`` env var, then a ``mcp-token`` file in
    the runtime dir. When a token is configured, the ``/mcp`` endpoint requires it
    (so the endpoint can be safely exposed over a tunnel); when it is not, the
    endpoint stays loopback-only.
    """
    env_token = str(os.environ.get("DEVFRAME_MCP_TOKEN") or "").strip()
    if env_token:
        return env_token
    if runtime_dir is not None:
        token_file = Path(runtime_dir) / "mcp-token"
        try:
            if token_file.is_file():
                value = token_file.read_text(encoding="utf-8").strip()
                if value:
                    return value
        except OSError:
            return None
    return None

TOOLS: list[dict[str, Any]] = [
    {
        "name": "server_config",
        "description": "Read-only DevFrame MCP server health and capability summary.",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "read_project_shell",
        "description": "Read-only DevFrame project/thread shell snapshot (governed read model).",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "propose_writeback",
        "description": (
            "Propose a single-file change to a project. This STAGES a human-gated "
            "proposal and writes nothing; a human must approve it before it is "
            "applied. Returns a requestId and a preview."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "projectId": {"type": "string", "description": "Target DevFrame project id"},
                "relativePath": {"type": "string", "description": "Workspace-relative file path"},
                "contents": {"type": "string", "description": "Full proposed file contents (UTF-8)"},
            },
            "required": ["projectId", "relativePath", "contents"],
            "additionalProperties": False,
        },
    },
    {
        "name": "list_pending_writebacks",
        "description": "List write-back proposals awaiting human approval.",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "get_run_status",
        "description": "Read-only status of a governed /go run (or the latest). Metadata only.",
        "inputSchema": {
            "type": "object",
            "properties": {"runId": {"type": "string", "description": "go-run id, or omit/\"latest\" for the most recent"}},
            "additionalProperties": False,
        },
    },
    {
        "name": "get_team_status",
        "description": "Read-only summary of the agent team objects (registry, task board, events, review gates, conflicts).",
        "inputSchema": {
            "type": "object",
            "properties": {"projectId": {"type": "string", "description": "Optional project filter"}},
            "additionalProperties": False,
        },
    },
    {
        "name": "list_pending_gates",
        "description": "Read-only list of review/safety gates awaiting a human decision.",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "propose_task",
        "description": (
            "Propose a coding task (a goal for a project). This STAGES a human-gated "
            "proposal only — it does NOT run anything and does NOT spend tokens. A "
            "human approves it; actually running it stays a separate human step."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "projectId": {"type": "string", "description": "Target DevFrame project id"},
                "goal": {"type": "string", "description": "What the task should accomplish"},
                "agents": {"type": "integer", "description": "Optional suggested agent count"},
                "target": {"type": "string", "description": "Optional target path/scope hint"},
            },
            "required": ["projectId", "goal"],
            "additionalProperties": False,
        },
    },
    {
        "name": "list_pending_tasks",
        "description": "List task proposals awaiting human approval.",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
]


def _result(req_id: Any, result: dict[str, Any]) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": req_id, "result": result}


def _error(req_id: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}}


def _tool_text(req_id: Any, payload: Any, *, is_error: bool = False) -> dict[str, Any]:
    text = payload if isinstance(payload, str) else json.dumps(payload, indent=2, ensure_ascii=True)
    return _result(req_id, {"content": [{"type": "text", "text": text}], "isError": is_error})


def new_session_id() -> str:
    return "devframe-mcp-" + secrets.token_hex(8)


def _project_shell_summary(runtime_dir, paper_project_dirs, base_url) -> dict[str, Any]:
    from .t3_adapter import build_t3_client_shell

    shell = build_t3_client_shell(runtime_dir, paper_project_dirs=paper_project_dirs, base_url=base_url)
    t3 = shell.get("t3", {})
    projects = [
        {"id": p.get("id"), "title": p.get("title"), "workspaceRoot": p.get("workspaceRoot")}
        for p in t3.get("projects", [])
        if isinstance(p, dict)
    ]
    threads = [
        {"id": t.get("id"), "title": t.get("title"), "projectId": t.get("projectId")}
        for t in t3.get("threads", [])
        if isinstance(t, dict)
    ]
    return {
        "source": "devframe",
        "writePolicy": "read-only-default; writes only via human-approved proposals",
        "updatedAt": t3.get("updatedAt"),
        "projects": projects,
        "threads": threads,
    }


def _run_status_summary(runtime_dir, paper_project_dirs, run_id: str | None) -> dict[str, Any]:
    from .visual_state import build_visual_control_plane_state

    state = build_visual_control_plane_state(runtime_dir, paper_project_dirs=paper_project_dirs)
    runs = [r for r in state.get("go_runs", []) if isinstance(r, dict)]

    def _summary(run: dict[str, Any]) -> dict[str, Any]:
        agents = [
            {"agentId": str(a.get("agent_id") or ""), "status": str(a.get("status") or "")}
            for a in (run.get("agents") or [])
            if isinstance(a, dict)
        ]
        return {
            "goRunId": str(run.get("go_run_id") or ""),
            "projectId": str(run.get("project_id") or ""),
            "status": str(run.get("status") or ""),
            "requirement": str(run.get("requirement") or run.get("goal") or ""),
            "agents": agents,
            "updatedAt": str(run.get("updated_at") or run.get("created_at") or ""),
        }

    wanted = str(run_id or "").strip()
    if not wanted or wanted == "latest":
        if not runs:
            return {"runs": [], "detail": "no /go runs recorded yet"}
        return {"run": _summary(runs[-1])}
    match = next((r for r in runs if str(r.get("go_run_id")) == wanted), None)
    if match is None:
        return {"error": "run_not_found", "runId": wanted}
    return {"run": _summary(match)}


def _team_status_summary(runtime_dir, paper_project_dirs, project_id: str | None) -> dict[str, Any]:
    from .visual_state import build_visual_control_plane_state

    state = build_visual_control_plane_state(runtime_dir, paper_project_dirs=paper_project_dirs)
    team = state.get("team") or {}

    def _ids(items, key):
        return [str(i.get(key) or "") for i in (items or []) if isinstance(i, dict)]

    agents = [
        {"agentId": str(a.get("agent_id") or ""), "role": str(a.get("role") or ""), "status": str(a.get("status") or "")}
        for a in (team.get("agent_registry") or []) if isinstance(a, dict)
    ]
    tasks = [
        {"taskId": str(t.get("task_id") or ""), "status": str(t.get("status") or ""), "type": str(t.get("type") or "")}
        for t in (team.get("task_board") or []) if isinstance(t, dict)
    ]
    events = [
        {"kind": str(e.get("kind") or ""), "runId": str(e.get("run_id") or ""), "summary": str(e.get("summary") or "")}
        for e in (team.get("event_log") or []) if isinstance(e, dict)
    ][-10:]
    gates = [
        {"gateId": str(g.get("gate_id") or ""), "status": str(g.get("status") or ""), "kind": str(g.get("kind") or "")}
        for g in (team.get("review_gates") or []) if isinstance(g, dict)
    ]
    conflicts = [
        {"filePath": str(c.get("file_path") or ""), "ownerRunId": str(c.get("owner_run_id") or "")}
        for c in (team.get("conflict_control") or []) if isinstance(c, dict)
    ]
    return {
        "agentRegistry": agents,
        "taskBoard": tasks,
        "recentEvents": events,
        "reviewGates": gates,
        "conflictControl": conflicts,
        "messageCount": len(team.get("message_bus") or []),
    }


def _pending_gates_summary(runtime_dir, paper_project_dirs) -> dict[str, Any]:
    from .visual_state import build_visual_control_plane_state

    state = build_visual_control_plane_state(runtime_dir, paper_project_dirs=paper_project_dirs)
    pending_statuses = {"open", "blocked", "failed", "pending"}
    raw = list(state.get("gates", []))
    raw += list((state.get("team") or {}).get("review_gates", []))
    gates = []
    seen = set()
    for g in raw:
        if not isinstance(g, dict):
            continue
        gid = str(g.get("gate_id") or "")
        if gid in seen:
            continue
        if str(g.get("status") or "").lower() in pending_statuses:
            seen.add(gid)
            gates.append({
                "gateId": gid,
                "kind": str(g.get("kind") or ""),
                "status": str(g.get("status") or ""),
                "reason": str(g.get("reason") or ""),
                "runId": str(g.get("run_id") or ""),
            })
    return {"pendingGates": gates}


def _call_tool(
    name: str,
    arguments: dict[str, Any],
    *,
    runtime_dir,
    paper_project_dirs,
    base_url,
    req_id: Any,
) -> dict[str, Any]:
    if name == "server_config":
        return _tool_text(req_id, {
            "server": SERVER_INFO,
            "protocolVersion": PROTOCOL_VERSION,
            "writePolicy": "read-only by default; AI may propose, humans approve",
            "tools": [t["name"] for t in TOOLS],
        })

    if name == "read_project_shell":
        return _tool_text(req_id, _project_shell_summary(runtime_dir, paper_project_dirs, base_url))

    if name == "propose_writeback":
        from .dashboard import _resolve_writeback_workspace_root
        from .writeback import WritebackError, stage_writeback_proposal

        project_id = str(arguments.get("projectId") or "").strip()
        relative_path = str(arguments.get("relativePath") or "").strip()
        contents = arguments.get("contents")
        if not project_id or not relative_path or not isinstance(contents, str):
            return _tool_text(
                req_id,
                {"error": "propose_writeback requires projectId, relativePath, and string contents"},
                is_error=True,
            )
        workspace_root = _resolve_writeback_workspace_root(runtime_dir, paper_project_dirs, project_id)
        if not workspace_root:
            return _tool_text(req_id, {"error": "unknown_project", "projectId": project_id}, is_error=True)
        try:
            staged = stage_writeback_proposal(
                runtime_dir, workspace_root, relative_path, contents, project_id=project_id
            )
        except WritebackError as exc:
            return _tool_text(req_id, {"error": "writeback_rejected", "detail": str(exc)}, is_error=True)
        return _tool_text(req_id, {
            "staged": True,
            "requestId": staged["request_id"],
            "preview": staged["preview"],
            "humanGate": "A human must approve this proposal before anything is written.",
        })

    if name == "list_pending_writebacks":
        from .writeback import list_pending_writeback_proposals

        return _tool_text(req_id, {"pending": list_pending_writeback_proposals(runtime_dir)})

    if name == "get_run_status":
        return _tool_text(req_id, _run_status_summary(runtime_dir, paper_project_dirs, arguments.get("runId")))

    if name == "get_team_status":
        return _tool_text(req_id, _team_status_summary(runtime_dir, paper_project_dirs, arguments.get("projectId")))

    if name == "list_pending_gates":
        return _tool_text(req_id, _pending_gates_summary(runtime_dir, paper_project_dirs))

    if name == "propose_task":
        from .dashboard import _resolve_writeback_workspace_root
        from .task_proposals import TaskProposalError, stage_task_proposal

        project_id = str(arguments.get("projectId") or "").strip()
        goal = arguments.get("goal")
        if not project_id or not isinstance(goal, str) or not goal.strip():
            return _tool_text(req_id, {"error": "propose_task requires projectId and a non-empty goal"}, is_error=True)
        if not _resolve_writeback_workspace_root(runtime_dir, paper_project_dirs, project_id):
            return _tool_text(req_id, {"error": "unknown_project", "projectId": project_id}, is_error=True)
        agents = arguments.get("agents")
        try:
            staged = stage_task_proposal(
                runtime_dir, project_id, goal,
                proposed_by="mcp-ai",
                agents=agents if isinstance(agents, int) else None,
                target=str(arguments.get("target") or ""),
            )
        except TaskProposalError as exc:
            return _tool_text(req_id, {"error": "task_proposal_rejected", "detail": str(exc)}, is_error=True)
        return _tool_text(req_id, {
            "staged": True,
            "requestId": staged["request_id"],
            "projectId": staged["project_id"],
            "goal": staged["goal"],
            "humanGate": "A human must approve this task; nothing runs and no tokens are spent until then.",
        })

    if name == "list_pending_tasks":
        from .task_proposals import list_pending_task_proposals

        return _tool_text(req_id, {"pending": list_pending_task_proposals(runtime_dir)})

    return _error(req_id, _METHOD_NOT_FOUND, f"unknown tool: {name}")


def handle_mcp_jsonrpc(
    request: dict[str, Any],
    *,
    runtime_dir=None,
    paper_project_dirs=None,
    base_url: str | None = None,
    session_id: str | None = None,
) -> tuple[dict[str, Any] | None, dict[str, str]]:
    """Handle one JSON-RPC request; return (response_or_None, extra_headers).

    ``session_id`` is the incoming ``MCP-Session-Id`` (the caller's connection
    handle); ``initialize`` mints a fresh one. A return of ``None`` means the
    message was a notification (no response).
    """
    from . import mcp_consent

    if not isinstance(request, dict):
        return _error(None, _INVALID_PARAMS, "invalid JSON-RPC request"), {}
    method = str(request.get("method") or "")
    req_id = request.get("id")

    if method == "initialize":
        params = request.get("params") or {}
        client_info = params.get("clientInfo") if isinstance(params, dict) else {}
        client_name = str((client_info or {}).get("name") or "unknown")
        new_sid = new_session_id()
        mcp_consent.register_connection(new_sid, client_name, runtime_dir=runtime_dir)
        response = _result(req_id, {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": SERVER_INFO,
        })
        return response, {"MCP-Session-Id": new_sid}

    if method in {"notifications/initialized", "initialized"}:
        return None, {}

    if method == "tools/list":
        return _result(req_id, {"tools": TOOLS}), {}

    if method == "tools/call":
        params = request.get("params") or {}
        name = str(params.get("name") or "")
        arguments = params.get("arguments") or {}
        if not isinstance(arguments, dict):
            return _error(req_id, _INVALID_PARAMS, "arguments must be an object"), {}
        # Connection consent gate: tools/call requires a human-authorized connection.
        mcp_consent.ensure_connection(session_id or "", runtime_dir=runtime_dir)
        authorized = mcp_consent.is_authorized(session_id)
        mcp_consent.record_tool_call(session_id, name, authorized=authorized, runtime_dir=runtime_dir)
        if not authorized:
            return _tool_text(req_id, {
                "error": "authorization_pending",
                "connectionId": session_id or "",
                "detail": (
                    "This AI connection is awaiting human authorization in DevFrame. "
                    "Ask the owner to Allow this connection, then retry."
                ),
            }, is_error=True), {}
        return _call_tool(
            name,
            arguments,
            runtime_dir=runtime_dir,
            paper_project_dirs=paper_project_dirs,
            base_url=base_url,
            req_id=req_id,
        ), {}

    if req_id is None:
        return None, {}
    return _error(req_id, _METHOD_NOT_FOUND, f"method not found: {method}"), {}
