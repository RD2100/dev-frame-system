"""Project-bound, memory-only MCP server over standard input/output."""
from __future__ import annotations

import copy
import json
import logging
import sys
from pathlib import Path
from typing import Any, TextIO

from .mcp_server import (
    PROTOCOL_VERSION,
    _MEMORY_PROJECT_TOOLS,
    _call_tool,
    _error,
    _result,
    _tool_text,
    available_tools,
)
from .obsidian_memory import resolve_session_project

LOGGER = logging.getLogger(__name__)
SERVER_INFO = {"name": "devframe-memory", "version": "0.1"}
_PARSE_ERROR = -32700
_INVALID_REQUEST = -32600
_INVALID_PARAMS = -32602
_METHOD_NOT_FOUND = -32601
_INTERNAL_ERROR = -32603
_MAX_MESSAGE_CHARS = 10 * 1024 * 1024


def memory_stdio_tools() -> list[dict[str, Any]]:
    """Return the safe current-project memory surface for stdio clients."""
    tools = []
    for source in available_tools():
        if source["name"] not in _MEMORY_PROJECT_TOOLS:
            continue
        tool = copy.deepcopy(source)
        schema = tool["inputSchema"]
        schema.get("properties", {}).pop("projectId", None)
        required = [
            field for field in schema.get("required", []) if field != "projectId"
        ]
        if required:
            schema["required"] = required
        else:
            schema.pop("required", None)
        tools.append(tool)
    return tools


def handle_memory_stdio_jsonrpc(
    request: dict[str, Any],
    *,
    runtime_dir: Path,
    project_root: Path,
    project_id: str,
) -> dict[str, Any] | None:
    """Handle one memory-only MCP message bound to a server-derived project."""
    if not isinstance(request, dict):
        return _error(None, _INVALID_REQUEST, "invalid JSON-RPC request")
    has_id = "id" in request
    if not has_id:
        # MCP tool calls are requests, not notifications. Ignoring every
        # id-less object also prevents write-capable tools from running
        # without a result that the client can inspect.
        return None
    if (
        request.get("jsonrpc") != "2.0"
        or not isinstance(request.get("method"), str)
        or not request["method"]
    ):
        return _error(None, _INVALID_REQUEST, "invalid JSON-RPC request")
    method = request["method"]
    req_id = request.get("id")

    if method == "initialize":
        return _result(
            req_id,
            {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": SERVER_INFO,
            },
        )
    if method == "ping":
        return _result(req_id, {})
    if method == "tools/list":
        return _result(req_id, {"tools": memory_stdio_tools()})
    if method == "tools/call":
        params = request.get("params", {})
        if params is None:
            params = {}
        if not isinstance(params, dict):
            return _error(req_id, _INVALID_PARAMS, "params must be an object")
        name = str(params.get("name") or "")
        arguments = params.get("arguments", {})
        if arguments is None:
            arguments = {}
        if not isinstance(arguments, dict):
            return _error(req_id, _INVALID_PARAMS, "arguments must be an object")
        if name not in _MEMORY_PROJECT_TOOLS:
            return _error(req_id, _METHOD_NOT_FOUND, f"unknown tool: {name}")
        supplied_project_id = str(arguments.get("projectId") or "").strip()
        if supplied_project_id and supplied_project_id != project_id:
            LOGGER.warning("Rejected cross-project stdio memory tool call: %s", name)
            return _tool_text(
                req_id,
                {
                    "error": "project_scope_rejected",
                    "detail": "Memory access is limited to the current project.",
                },
                is_error=True,
            )
        bound_arguments = dict(arguments)
        bound_arguments["projectId"] = project_id
        request_meta = {
            "codex/sandbox-state-meta": {
                "sandboxCwd": project_root.resolve().as_uri(),
            }
        }
        LOGGER.debug("Dispatching project-bound stdio memory tool: %s", name)
        return _call_tool(
            name,
            bound_arguments,
            runtime_dir=runtime_dir,
            paper_project_dirs=None,
            base_url=None,
            req_id=req_id,
            request_meta=request_meta,
        )
    return _error(req_id, _METHOD_NOT_FOUND, f"method not found: {method}")


def run_memory_stdio(
    *,
    cwd: Path,
    runtime_dir: Path,
    input_stream: TextIO = sys.stdin,
    output_stream: TextIO = sys.stdout,
) -> int:
    """Run newline-delimited MCP until the client closes standard input."""
    project = resolve_session_project(cwd=cwd, runtime_dir=runtime_dir)
    project_root = Path(str(project["projectRoot"]))
    project_id = str(project["projectId"])
    LOGGER.debug("Started project-bound stdio memory server")

    while True:
        raw_line = input_stream.readline(_MAX_MESSAGE_CHARS + 1)
        if raw_line == "":
            break
        if len(raw_line) > _MAX_MESSAGE_CHARS:
            while raw_line and not raw_line.endswith("\n"):
                raw_line = input_stream.readline(_MAX_MESSAGE_CHARS + 1)
            response = _error(None, _INVALID_REQUEST, "message too large")
            output_stream.write(
                json.dumps(response, ensure_ascii=True, separators=(",", ":")) + "\n"
            )
            output_stream.flush()
            continue
        line = raw_line.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
        except (json.JSONDecodeError, UnicodeError):
            response = _error(None, _PARSE_ERROR, "parse error")
        else:
            try:
                response = handle_memory_stdio_jsonrpc(
                    request,
                    runtime_dir=runtime_dir,
                    project_root=project_root,
                    project_id=project_id,
                )
            except Exception as exc:  # MCP boundary: keep the client alive.
                LOGGER.error(
                    "Project-bound stdio memory dispatch failed: %s",
                    type(exc).__name__,
                )
                response = _error(
                    request.get("id") if isinstance(request, dict) else None,
                    _INTERNAL_ERROR,
                    "internal error",
                )
        if response is None:
            continue
        output_stream.write(
            json.dumps(response, ensure_ascii=True, separators=(",", ":")) + "\n"
        )
        output_stream.flush()
    LOGGER.debug("Stopped project-bound stdio memory server")
    return 0
