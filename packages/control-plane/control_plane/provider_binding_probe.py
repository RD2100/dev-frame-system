"""Provider binding probe shapes for external web AI bridge adapters."""
from __future__ import annotations

import json
from urllib.parse import urlparse
from typing import Any


SUPPORTED_PROVIDER_PROFILES = {
    "codexpro": {
        "mode": "mcp_app",
        "role": "coordinator",
        "health": "needs_login",
        "message": "CodexPro MCP app bridge prepared; connect it from an MCP-capable Web AI host before treating it as a web-agent bridge.",
        "action": "Connect CodexPro Server URL from an MCP-capable Web AI host, then import this summary as the bound external brain session.",
        "manual_fallback": [
            "Start CodexPro in the target workspace.",
            "Paste the CodexPro Server URL into an MCP-capable Web AI host.",
            "Ask the Web AI host to open the workspace and create a handoff_to_agent plan.",
        ],
    },
    "devspace": {
        "mode": "local_mcp_bridge",
        "role": "coordinator",
        "health": "needs_login",
        "message": "DevSpace MCP workspace bridge prepared; complete owner approval before treating it as live.",
        "action": "Approve the DevSpace OAuth owner prompt, then call open_workspace from the MCP host.",
        "manual_fallback": [
            "Start DevSpace with allowed roots configured.",
            "Connect the MCP host to the DevSpace /mcp endpoint.",
            "Approve the owner prompt and call open_workspace.",
        ],
    },
}


def build_provider_binding_probe(
    provider: str,
    endpoint: str,
    *,
    project_id: str = "unknown",
    session_id: str | None = None,
    agent_id: str | None = None,
    agent_role: str | None = None,
    health: str | None = None,
) -> dict[str, Any]:
    """Build a summary-only DevFrame probe for a local web AI bridge."""

    profile_id = _safe_id(provider)
    if profile_id not in SUPPORTED_PROVIDER_PROFILES:
        raise ValueError(f"unsupported provider binding probe: {provider}")
    safe_endpoint = _safe_endpoint(endpoint)
    profile = SUPPORTED_PROVIDER_PROFILES[profile_id]
    resolved_health = _health(health or str(profile["health"]))
    resolved_role = _agent_role(agent_role or str(profile["role"]))
    resolved_session_id = _safe_id(session_id or f"{profile_id}-probe-session")
    resolved_agent_id = _safe_id(agent_id or resolved_session_id)
    resolved_project_id = _safe_id(project_id)
    binding_id = _safe_id(f"{profile_id}-web")
    action_text = str(profile["action"])
    session_status = "needs_human" if resolved_health in {"needs_login", "blocked"} else "idle"

    provider_binding = {
        "binding_id": binding_id,
        "provider": profile_id,
        "mode": str(profile["mode"]),
        "health": resolved_health,
        "adapter_config_path": "",
        "manual_fallback_instructions": list(profile["manual_fallback"]),
        "notes": "Probe-only local MCP bridge binding; no network call was performed.",
    }
    agent = {
        "agent_id": resolved_agent_id,
        "binding_id": binding_id,
        "role": _agent_schema_role(resolved_role),
        "scope": "project",
        "permissions": ["read_context", "plan", "review"],
        "status": "needs_human" if session_status == "needs_human" else "idle",
    }
    session_summary = {
        "session_id": resolved_session_id,
        "provider": profile_id,
        "agent_id": resolved_agent_id,
        "agent_role": resolved_role,
        "project_id": resolved_project_id,
        "run_id": "",
        "task_spec_id": "",
        "status": session_status,
        "messages": [
            {
                "message_id": f"{resolved_session_id}-probe-message",
                "role": "system",
                "content_summary": str(profile["message"]),
            },
        ],
        "tool_calls": [
            {
                "tool_call_id": f"{resolved_session_id}-endpoint",
                "name": "mcp-endpoint-configured",
                "status": "needs_human" if session_status == "needs_human" else "idle",
            },
        ],
        "changed_files": [],
        "diff_summary": "",
        "evidence_refs": [],
        "cost": {},
        "tokens": {},
        "gates": [f"{binding_id}-connection-gate"],
        "actions": [action_text],
        "native_refs": {
            "runtime": "provider-binding-probe",
            "endpoint": safe_endpoint,
        },
    }
    action = {
        "action_id": _safe_id(f"{resolved_session_id}-{action_text}"),
        "source_type": "session",
        "source_id": resolved_session_id,
        "priority": "medium",
        "status": "open" if session_status == "needs_human" else "info",
        "label": "Complete external web AI bridge binding.",
        "detail": action_text,
    }
    probe = {
        "provider_binding": provider_binding,
        "agent": agent,
        "session_summary": session_summary,
        "next_action": action,
    }
    _validate_provider_binding_probe(probe)
    return probe


def _validate_provider_binding_probe(probe: dict[str, Any]) -> None:
    for key in ("provider_binding", "agent", "session_summary", "next_action"):
        if key not in probe:
            raise ValueError(f"provider binding probe missing required key: {key}")
        if not isinstance(probe[key], dict):
            raise ValueError(f"provider binding probe {key} must be a dict")


def render_provider_binding_probe_text(probe: dict[str, Any]) -> str:
    binding = probe.get("provider_binding", {})
    session = probe.get("session_summary", {})
    action = probe.get("next_action", {})
    lines = [
        "Provider Binding Probe",
        f"provider     : {binding.get('provider', '')}",
        f"binding_id   : {binding.get('binding_id', '')}",
        f"mode         : {binding.get('mode', '')}",
        f"health       : {binding.get('health', '')}",
        f"session_id   : {session.get('session_id', '')}",
        f"project_id   : {session.get('project_id', '')}",
        f"next_action  : {action.get('detail', '')}",
        "",
        "No service was started, no network call was made, and no runtime file was written.",
        "Use --format json and import the session_summary with devframe web-ai import after review.",
    ]
    return "\n".join(lines) + "\n"


def render_provider_binding_probe_json(probe: dict[str, Any]) -> str:
    return json.dumps(probe, indent=2, ensure_ascii=True) + "\n"


def _safe_endpoint(endpoint: str) -> str:
    text = str(endpoint or "").strip()
    if not text:
        raise ValueError("endpoint is required")
    parsed = urlparse(text)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("endpoint must be an http or https URL")
    if not parsed.netloc:
        raise ValueError("endpoint must include a host")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("endpoint must not include credentials, query strings, or fragments")
    return text


def _safe_id(value: object) -> str:
    text = str(value or "").strip().lower()
    normalized = "".join(
        char if "a" <= char <= "z" or "0" <= char <= "9" else "-"
        for char in text
    )
    normalized = "-".join(part for part in normalized.split("-") if part)
    return normalized or "unknown"


def _health(value: str) -> str:
    normalized = _safe_id(value)
    if normalized not in {"unknown", "ready", "needs-login", "blocked", "disabled"}:
        raise ValueError(f"unsupported provider health: {value}")
    return normalized.replace("-", "_")


def _agent_role(value: str) -> str:
    normalized = _safe_id(value).replace("-", "_")
    allowed = {"coordinator", "reviewer", "executor", "paper_reviewer", "human_reviewer", "custom"}
    if normalized not in allowed:
        raise ValueError(f"unsupported agent role: {value}")
    return normalized


def _agent_schema_role(value: str) -> str:
    return "reviewer" if value == "custom" else value
