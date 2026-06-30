"""Minimal provider-neutral MCP live-check boundary using stdlib only."""
from __future__ import annotations

import json
import socket
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from .provider_binding_probe import _safe_endpoint, _safe_id


def _post_json(
    url: str,
    payload: dict[str, Any],
    headers: dict[str, str] | None = None,
    timeout: int = 10,
) -> tuple[int, dict[str, Any], dict[str, str]]:
    req = Request(
        url,
        data=json.dumps(payload, ensure_ascii=True).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            **(headers or {}),
        },
        method="POST",
    )
    resp = urlopen(req, timeout=timeout)
    resp_headers = {k: v for k, v in resp.getheaders()}
    body = resp.read().decode("utf-8", errors="replace")
    # MCP Streamable HTTP replies as Server-Sent Events; the JSON-RPC message is
    # carried in `data:` lines. Header casing is server-defined (Node servers do
    # not match Python's title-case), so look it up case-insensitively.
    content_type = _header_value(resp_headers, "Content-Type") or ""
    if content_type.lower().startswith("text/event-stream"):
        body = _extract_sse_json(body) or body
    try:
        data = json.loads(body) if body else {}
    except json.JSONDecodeError:
        data = {"_raw": body}
    return resp.status, data, resp_headers


def _extract_sse_json(body: str) -> str | None:
    """Return the first SSE event payload that parses as a JSON-RPC object.

    SSE frames separate events with a blank line and may split one event's data
    across several `data:` lines (joined with newlines). We collect each event's
    data and return the first that is valid JSON, so a single Streamable-HTTP
    JSON-RPC response is recovered regardless of framing details.
    """
    events: list[str] = []
    current: list[str] = []
    for raw_line in body.splitlines():
        line = raw_line.rstrip("\r")
        if line.startswith("data:"):
            current.append(line[5:].lstrip())
        elif line == "":
            if current:
                events.append("\n".join(current))
                current = []
    if current:
        events.append("\n".join(current))
    for event in events:
        try:
            json.loads(event)
            return event
        except json.JSONDecodeError:
            continue
    return events[0] if events else None


def _header_value(headers: dict[str, str], name: str) -> str | None:
    wanted = name.lower()
    for key, value in headers.items():
        if str(key).lower() == wanted:
            return value
    return None


def _is_auth_error(status: int, data: dict[str, Any]) -> bool:
    if status in {401, 403}:
        return True
    error = data.get("error")
    if isinstance(error, dict):
        code = error.get("code")
        if isinstance(code, int) and -32003 <= code <= -32001:
            return True
    return False


def _is_protocol_error(data: dict[str, Any]) -> bool:
    error = data.get("error")
    if not isinstance(error, dict):
        return False
    code = error.get("code")
    return isinstance(code, int) and code in {-32700, -32600}


def _classify_http_error(exc: HTTPError) -> tuple[str, str, list[str]]:
    status = "unavailable"
    message = f"MCP endpoint returned HTTP {exc.code}."
    notes = [f"http error {exc.code}"]
    if exc.code in {401, 403}:
        status = "auth_required"
        message = "MCP endpoint returned authentication required."
        notes = ["http auth required"]
    return status, message, notes


def _session_status_for_probe_status(status: str) -> str:
    if status == "live_ok":
        return "active"
    if status == "auth_required":
        return "needs_human"
    if status == "blocked":
        return "blocked"
    if status in {"protocol_error", "unavailable"}:
        return "failed"
    return "unknown"


def _tool_call_status_for_probe_status(status: str) -> str:
    if status == "live_ok":
        return "completed"
    return _session_status_for_probe_status(status)


def mcp_live_probe(
    endpoint: str,
    *,
    provider: str = "unknown",
    project_id: str = "unknown",
    token: str | None = None,
    tool: str | None = None,
    timeout: int = 10,
) -> dict[str, Any]:
    """Attempt a live MCP check against a Streamable HTTP endpoint."""
    safe_endpoint = _safe_endpoint(endpoint)
    profile_id = _safe_id(provider)
    safe_project_id = _safe_id(project_id)

    request_headers: dict[str, str] = {}
    if token:
        request_headers["Authorization"] = f"Bearer {token}"

    session_id: str | None = None
    tool_names: list[str] = []
    tool_called: str | None = None
    evidence_notes: list[str] = []
    status = "unavailable"
    message = ""

    try:
        init_payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "devframe", "version": "0.1"},
            },
        }
        init_status, init_data, init_headers = _post_json(
            safe_endpoint, init_payload, headers=request_headers, timeout=timeout
        )
        session_id = _header_value(init_headers, "MCP-Session-Id")

        if init_status in {401, 403} or _is_auth_error(init_status, init_data):
            status = "auth_required"
            message = "MCP endpoint returned authentication required."
            evidence_notes.append("initialize returned auth required")
        elif init_status != 200 or not isinstance(init_data, dict) or "result" not in init_data:
            if _is_protocol_error(init_data):
                status = "protocol_error"
                message = "MCP initialize returned a protocol error."
                evidence_notes.append("initialize returned protocol error")
            else:
                status = "unavailable"
                message = "MCP initialize did not return a valid JSON-RPC result."
                evidence_notes.append("initialize returned no valid result")
        else:
            list_headers: dict[str, str] = {}
            if session_id:
                list_headers["MCP-Session-Id"] = session_id
            list_payload = {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/list",
                "params": {},
            }
            list_status, list_data, _ = _post_json(
                safe_endpoint, list_payload, headers={**request_headers, **list_headers}, timeout=timeout
            )
            if list_status in {401, 403} or _is_auth_error(list_status, list_data):
                status = "auth_required"
                message = "MCP tools/list returned authentication required."
                evidence_notes.append("tools/list returned auth required")
            elif list_status != 200 or not isinstance(list_data, dict) or "result" not in list_data:
                if _is_protocol_error(list_data):
                    status = "protocol_error"
                    message = "MCP tools/list returned a protocol error."
                    evidence_notes.append("tools/list returned protocol error")
                else:
                    status = "unavailable"
                    message = "MCP tools/list did not return a valid JSON-RPC result."
                    evidence_notes.append("tools/list returned no valid result")
            else:
                tools_result = list_data.get("result", {})
                raw_tools = tools_result.get("tools", [])
                if isinstance(raw_tools, list):
                    tool_names = [
                        str(t.get("name", ""))
                        for t in raw_tools
                        if isinstance(t, dict) and t.get("name")
                    ]

                resolved_tool = None
                if tool:
                    if tool not in SAFE_TOOLS:
                        status = "blocked"
                        message = f"Requested tool {tool} is not in the safe-tool allowlist."
                        evidence_notes.append(f"blocked unsafe tool: {tool}")
                    elif tool in tool_names:
                        resolved_tool = tool
                    else:
                        evidence_notes.append(f"requested tool {tool} not advertised by server")

                if status == "blocked":
                    pass
                elif resolved_tool and resolved_tool in LIST_ONLY_SAFE_TOOLS:
                    status = "live_ok"
                    message = f"MCP live check succeeded ({resolved_tool} advertised; tools/call skipped)."
                    evidence_notes.append(f"tools/list advertised {resolved_tool}; tools/call skipped for side-effect safety")
                elif resolved_tool:
                    call_headers: dict[str, str] = {}
                    if session_id:
                        call_headers["MCP-Session-Id"] = session_id
                    call_payload = {
                        "jsonrpc": "2.0",
                        "id": 3,
                        "method": "tools/call",
                        "params": {"name": resolved_tool, "arguments": {}},
                    }
                    call_status, call_data, _ = _post_json(
                        safe_endpoint, call_payload, headers={**request_headers, **call_headers}, timeout=timeout
                    )
                    if call_status in {401, 403} or _is_auth_error(call_status, call_data):
                        status = "auth_required"
                        message = "MCP tools/call returned authentication required."
                        evidence_notes.append("tools/call returned auth required")
                    elif call_status != 200 or not isinstance(call_data, dict) or "result" not in call_data:
                        if _is_protocol_error(call_data):
                            status = "protocol_error"
                            message = "MCP tools/call returned a protocol error."
                            evidence_notes.append("tools/call returned protocol error")
                        else:
                            status = "unavailable"
                            message = "MCP tools/call did not return a valid JSON-RPC result."
                            evidence_notes.append("tools/call returned no valid result")
                    else:
                        status = "live_ok"
                        message = "MCP live check succeeded."
                        evidence_notes.append(f"tools/call {resolved_tool} succeeded")
                        tool_called = resolved_tool
                else:
                    status = "live_ok"
                    message = "MCP live check succeeded (initialize + tools/list)."
                    evidence_notes.append("initialize and tools/list succeeded")
    except HTTPError as exc:
        status, message, evidence_notes = _classify_http_error(exc)
    except ConnectionRefusedError:
        status = "unavailable"
        message = "MCP endpoint refused the connection."
        evidence_notes = ["connection refused"]
    except socket.timeout:
        status = "unavailable"
        message = "MCP endpoint timed out."
        evidence_notes = ["request timed out"]
    except URLError as exc:
        reason = exc.reason
        if isinstance(reason, ConnectionRefusedError):
            status = "unavailable"
            message = "MCP endpoint refused the connection."
            evidence_notes = ["connection refused"]
        elif isinstance(reason, socket.timeout):
            status = "unavailable"
            message = "MCP endpoint timed out."
            evidence_notes = ["request timed out"]
        else:
            status = "unavailable"
            message = f"MCP check failed: {reason}"
            evidence_notes = [f"unexpected error: {reason}"]
    except Exception as exc:  # noqa: BLE001
        status = "unavailable"
        message = f"MCP check failed: {exc}"
        evidence_notes = [f"unexpected error: {exc}"]

    if not message:
        message = "MCP live check completed with unknown status."

    session_status = _session_status_for_probe_status(status)
    tool_call_status = _tool_call_status_for_probe_status(status)
    tool_calls = [
        {
            "tool_call_id": f"{_safe_id(profile_id)}-endpoint-check",
            "name": "mcp-endpoint-check",
            "status": tool_call_status,
        }
    ]
    if tool_called:
        tool_calls.append({
            "tool_call_id": f"{_safe_id(profile_id)}-tool-call",
            "name": tool_called,
            "status": tool_call_status,
        })

    session_summary: dict[str, Any] = {
        "session_id": _safe_id(f"{profile_id}-live-{session_id or 'session'}"),
        "provider": profile_id,
        "agent_id": _safe_id(f"{profile_id}-live-agent"),
        "agent_role": "coordinator",
        "project_id": safe_project_id,
        "run_id": "",
        "task_spec_id": "",
        "status": session_status,
        "messages": [
            {
                "message_id": f"{_safe_id(profile_id)}-live-probe-message",
                "role": "system",
                "content_summary": message,
            },
        ],
        "tool_calls": tool_calls,
        "changed_files": [],
        "diff_summary": "",
        "evidence_refs": [],
        "cost": {},
        "tokens": {},
        "gates": [f"{_safe_id(profile_id)}-mcp-live-gate"],
        "actions": [message],
        "native_refs": {
            "runtime": "mcp-live-probe",
            "endpoint": safe_endpoint,
        },
        "tool_names": tool_names,
    }

    probe: dict[str, Any] = {
        "status": status,
        "provider": profile_id,
        "binding_id": _safe_id(f"{profile_id}-mcp-live"),
        "mode": "mcp_live_probe",
        "health": "ready" if status == "live_ok" else "blocked" if status == "blocked" else "needs_login",
        "session_id": session_summary["session_id"],
        "project_id": safe_project_id,
        "tool_names": tool_names,
        "tool_called": tool_called,
        "message": message,
        "evidence_notes": evidence_notes,
        "session_summary": session_summary,
    }
    return probe


def render_mcp_live_probe_text(probe: dict[str, Any]) -> str:
    lines = [
        "MCP Live Probe",
        f"status       : {probe.get('status', '')}",
        f"provider     : {probe.get('provider', '')}",
        f"binding_id   : {probe.get('binding_id', '')}",
        f"mode         : {probe.get('mode', '')}",
        f"health       : {probe.get('health', '')}",
        f"session_id   : {probe.get('session_id', '')}",
        f"project_id   : {probe.get('project_id', '')}",
        f"tool_names   : {', '.join(probe.get('tool_names', [])) or '(none)'}",
        f"message      : {probe.get('message', '')}",
    ]
    if probe.get("tool_called"):
        lines.append(f"tool_called  : {probe['tool_called']}")
    lines.append("")
    return "\n".join(lines) + "\n"


def render_mcp_live_probe_json(probe: dict[str, Any]) -> str:
    return json.dumps(probe, indent=2, ensure_ascii=True) + "\n"


SAFE_TOOLS = {"server_config", "handoff_to_agent", "task_intake", "project_summary"}
LIST_ONLY_SAFE_TOOLS = {"task_intake"}
