"""Project-to-ChatGPT conversation binding files.

Bindings are local agent state and default to the user's home directory so the
public repository stays clean.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


def default_binding_root() -> Path:
    return Path.home() / ".agents" / "bindings"


def write_conversation_binding(
    *,
    project_id: str,
    project_root: str | Path,
    chat_url: str,
    binding_root: str | Path | None = None,
    cdp_endpoint: str = "http://localhost:9222",
) -> dict[str, Any]:
    safe_project_id = _safe_id(project_id)
    root = Path(binding_root).resolve() if binding_root else default_binding_root().resolve()
    project_path = Path(project_root).resolve()
    conversation_id = _conversation_id(chat_url)
    canonical_url = f"https://chatgpt.com/c/{conversation_id}"
    target = root / safe_project_id
    target.mkdir(parents=True, exist_ok=True)

    registry = {
        "schema_version": "1.0.0",
        "projects": [
            {
                "project_id": safe_project_id,
                "project_root": str(project_path),
                "binding_status": "active",
                "conversation_id": conversation_id,
                "chat_url": canonical_url,
            }
        ],
    }
    binding = {
        "schema_version": "1.0.0",
        "awsp_version": "1.3.0",
        "project_id": safe_project_id,
        "project_root": str(project_path),
        "default_conversation_policy": "one_agent_one_conversation",
        "bindings": [
            {
                "agent_id": f"agent-{safe_project_id}-001",
                "role": "executor",
                "binding_status": "active",
                "conversation_id": conversation_id,
                "chat_url": canonical_url,
                "cdp_endpoint": cdp_endpoint,
                "allowed_task_scope": ["*"],
                "capture_policy": {
                    "must_match_run_id": True,
                    "must_match_task_id": True,
                    "must_include_end_marker": True,
                    "forbid_last_message_only_capture": True,
                },
            }
        ],
    }

    registry_path = target / "PROJECT_REGISTRY.json"
    binding_path = target / "CONVERSATION_BINDING.json"
    registry_path.write_text(json.dumps(registry, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    binding_path.write_text(json.dumps(binding, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")

    return {
        "project_id": safe_project_id,
        "project_root": str(project_path),
        "conversation_id": conversation_id,
        "chat_url": canonical_url,
        "registry_path": str(registry_path),
        "binding_path": str(binding_path),
    }


def _conversation_id(chat_url: str) -> str:
    parsed = urlparse(str(chat_url or "").strip())
    if parsed.scheme != "https" or (parsed.hostname or "").lower() not in {"chatgpt.com", "www.chatgpt.com"}:
        raise ValueError("chat_url must be an https://chatgpt.com/c/<id> URL")
    if parsed.username or parsed.password:
        raise ValueError("chat_url must not include credentials")
    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) < 2 or parts[0] != "c" or not parts[1].strip():
        raise ValueError("chat_url must include /c/<conversation_id>")
    return parts[1]


def _safe_id(value: object) -> str:
    text = str(value or "").strip().lower()
    normalized = "".join(
        char if "a" <= char <= "z" or "0" <= char <= "9" else "-"
        for char in text
    )
    normalized = "-".join(part for part in normalized.split("-") if part)
    return normalized or "project"
