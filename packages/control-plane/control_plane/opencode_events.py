"""Defensive parser for OpenCode `run --format json` JSONL event output.

OpenCode emits one JSON object per line. Its event schema is not stable across
versions, so this parser is intentionally tolerant: it extracts the values it
recognizes and leaves defaults otherwise, and it never raises on malformed
input. It reuses the robustness approach proven by the ai-workflow-hub slice0
probe (`parse_jsonl`), but extracts concrete values instead of only detecting
field presence, and lives in control-plane so it carries no cross-package
dependency.

The extracted summary is the structured execution data DevFrame surfaces in the
go-run record and `DevFrameSession`: session id, model, token usage, cost, tool
calls, and changed files. This raises the OpenCode worker integration from a
subprocess black box (reuse-depth L1) to a structured-event adapter (L2).
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any

_SESSION_KEYS = ("sessionID", "session_id", "sessionId")
_TOTAL_TOKEN_KEYS = ("total", "totalTokens", "total_tokens")
_INPUT_TOKEN_KEYS = ("input", "inputTokens", "input_tokens", "prompt", "promptTokens")
_OUTPUT_TOKEN_KEYS = ("output", "outputTokens", "output_tokens", "completion", "completionTokens")
_FILE_TOOL_NAMES = ("write", "edit", "patch", "apply", "create", "multiedit")
_FILE_PATH_KEYS = ("filePath", "file_path", "path", "file", "filename", "target")
_ERROR_TOKENS = ("level=error", "panic", "traceback", "database is locked", "fatal")


@dataclass
class OpenCodeToolCall:
    name: str
    target: str = ""


@dataclass
class OpenCodeRunSummary:
    parsed: bool = False
    event_count: int = 0
    invalid_line_count: int = 0
    session_id: str = ""
    model: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    cost: float = 0.0
    tool_calls: list[OpenCodeToolCall] = field(default_factory=list)
    changed_files: list[str] = field(default_factory=list)
    error_signals: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["tool_calls"] = [asdict(call) for call in self.tool_calls]
        return data

    def is_empty(self) -> bool:
        return not (
            self.session_id
            or self.model
            or self.total_tokens
            or self.input_tokens
            or self.output_tokens
            or self.cost
            or self.tool_calls
            or self.changed_files
        )


def parse_opencode_run_jsonl(text: str) -> OpenCodeRunSummary:
    """Parse OpenCode JSONL stdout into a structured, defensive summary."""
    summary = OpenCodeRunSummary()
    if not text:
        return summary

    events: list[dict[str, Any]] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        try:
            value = json.loads(stripped)
        except json.JSONDecodeError:
            summary.invalid_line_count += 1
            continue
        if isinstance(value, dict):
            events.append(value)
        else:
            summary.invalid_line_count += 1

    summary.event_count = len(events)
    summary.parsed = bool(events)

    seen_files: set[str] = set()
    seen_tools: set[tuple[str, str]] = set()
    for event in events:
        _extract_session(event, summary)
        _extract_model(event, summary)
        _extract_tokens(event, summary)
        _extract_cost(event, summary)
        _extract_tool_and_files(event, summary, seen_tools, seen_files)
    _extract_errors(text, summary)
    return summary


def _first_string(value: object) -> str:
    if isinstance(value, str) and value.strip():
        return value.strip()
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return str(value)
    return ""


def _coerce_int(value: object) -> int:
    if isinstance(value, bool):
        return 0
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(float(value))
        except ValueError:
            return 0
    return 0


def _coerce_float(value: object) -> float:
    if isinstance(value, bool):
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return 0.0
    return 0.0


def _find_first(event: dict[str, Any], keys: tuple[str, ...]) -> object:
    """Find the first matching key anywhere in the (possibly nested) event."""
    stack: list[Any] = [event]
    while stack:
        current = stack.pop()
        if isinstance(current, dict):
            for key in keys:
                if key in current and current[key] not in (None, "", {}, []):
                    return current[key]
            stack.extend(current.values())
        elif isinstance(current, list):
            stack.extend(current)
    return None


def _extract_session(event: dict[str, Any], summary: OpenCodeRunSummary) -> None:
    if summary.session_id:
        return
    direct = _find_first(event, _SESSION_KEYS)
    candidate = _first_string(direct)
    if candidate:
        summary.session_id = candidate
        return
    session = event.get("session")
    if isinstance(session, dict):
        candidate = _first_string(session.get("id"))
        if candidate:
            summary.session_id = candidate


def _extract_model(event: dict[str, Any], summary: OpenCodeRunSummary) -> None:
    if summary.model:
        return
    for key in ("modelID", "model_id", "model"):
        if key in event:
            candidate = _first_string(event[key])
            if not candidate and isinstance(event[key], dict):
                candidate = _first_string(event[key].get("id") or event[key].get("name"))
            if candidate:
                summary.model = candidate
                return


def _token_container(event: dict[str, Any]) -> dict[str, Any] | None:
    for key in ("tokens", "usage", "token_usage", "tokenUsage"):
        value = _find_first(event, (key,))
        if isinstance(value, dict):
            return value
    return None


def _extract_tokens(event: dict[str, Any], summary: OpenCodeRunSummary) -> None:
    container = _token_container(event)
    if container is None:
        return
    total = _first_present(container, _TOTAL_TOKEN_KEYS)
    inp = _first_present(container, _INPUT_TOKEN_KEYS)
    out = _first_present(container, _OUTPUT_TOKEN_KEYS)
    if inp is not None:
        summary.input_tokens = max(summary.input_tokens, _coerce_int(inp))
    if out is not None:
        summary.output_tokens = max(summary.output_tokens, _coerce_int(out))
    if total is not None:
        summary.total_tokens = max(summary.total_tokens, _coerce_int(total))
    derived = summary.input_tokens + summary.output_tokens
    if summary.total_tokens < derived:
        summary.total_tokens = derived


def _first_present(container: dict[str, Any], keys: tuple[str, ...]) -> object:
    for key in keys:
        if key in container and container[key] is not None:
            return container[key]
    return None


def _extract_cost(event: dict[str, Any], summary: OpenCodeRunSummary) -> None:
    value = _find_first(event, ("cost",))
    if isinstance(value, dict):
        value = _first_present(value, ("amount", "total", "usd"))
    cost = _coerce_float(value)
    if cost > summary.cost:
        summary.cost = cost


def _extract_tool_and_files(
    event: dict[str, Any],
    summary: OpenCodeRunSummary,
    seen_tools: set[tuple[str, str]],
    seen_files: set[str],
) -> None:
    tool_name = _tool_name(event)
    if not tool_name:
        return
    target = _tool_target(event)
    key = (tool_name.lower(), target)
    if key not in seen_tools:
        seen_tools.add(key)
        summary.tool_calls.append(OpenCodeToolCall(name=tool_name, target=target))
    if target and tool_name.lower() in _FILE_TOOL_NAMES and target not in seen_files:
        seen_files.add(target)
        summary.changed_files.append(target)


def _tool_name(event: dict[str, Any]) -> str:
    event_type = _first_string(event.get("type"))
    is_tool_event = event_type.lower() in ("tool", "tool_use", "tool-call", "tool_call")
    # Real OpenCode nests tool info under "part" (part.tool = "write"/"skill"/...).
    containers = [event]
    part = event.get("part")
    if isinstance(part, dict):
        containers.append(part)
    for container in containers:
        tool = container.get("tool")
        if isinstance(tool, str) and tool.strip():
            return tool.strip()
        if isinstance(tool, dict):
            name = _first_string(tool.get("name") or tool.get("id"))
            if name:
                return name
        if is_tool_event:
            name = _first_string(container.get("name"))
            if name:
                return name
    return ""


def _tool_target(event: dict[str, Any]) -> str:
    for container_key in ("input", "args", "arguments", "state", "tool", "params"):
        container = event.get(container_key)
        if isinstance(container, dict):
            candidate = _first_string(_find_first(container, _FILE_PATH_KEYS))
            if candidate:
                return candidate
    return _first_string(_find_first(event, _FILE_PATH_KEYS))


def _extract_errors(text: str, summary: OpenCodeRunSummary) -> None:
    lowered = text.lower()
    for token in _ERROR_TOKENS:
        if token in lowered and token not in summary.error_signals:
            summary.error_signals.append(token)
