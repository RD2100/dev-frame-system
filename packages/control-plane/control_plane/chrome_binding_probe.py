"""Summary-only Chrome/CDP binding probe for browser-hosted web AI."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse, urlunparse
from urllib.request import urlopen


DEFAULT_CDP_ENDPOINT = "http://127.0.0.1:9222"
CHATGPT_HOSTS = {"chatgpt.com", "www.chatgpt.com"}


class ChromeBindingError(RuntimeError):
    """Raised when Chrome/CDP cannot produce a safe web AI binding."""


def fetch_chrome_debugger_state(cdp_endpoint: str = DEFAULT_CDP_ENDPOINT) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Read Chrome debugger version and tab list from a local CDP endpoint."""

    endpoint = _safe_cdp_endpoint(cdp_endpoint)
    with urlopen(f"{endpoint}/json/version", timeout=3) as response:
        version = json.loads(response.read().decode("utf-8"))
    with urlopen(f"{endpoint}/json", timeout=3) as response:
        tabs = json.loads(response.read().decode("utf-8"))
    if not isinstance(version, dict):
        raise ChromeBindingError("Chrome CDP version response was not an object")
    if not isinstance(tabs, list):
        raise ChromeBindingError("Chrome CDP tab response was not a list")
    return version, [tab for tab in tabs if isinstance(tab, dict)]


def build_chrome_chatgpt_session_summary(
    *,
    project_id: str = "unknown",
    cdp_endpoint: str = DEFAULT_CDP_ENDPOINT,
    session_id: str | None = None,
    agent_id: str | None = None,
    version: dict[str, Any] | None = None,
    tabs: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build a summary-only session from an already-open ChatGPT Chrome tab."""

    endpoint = _safe_cdp_endpoint(cdp_endpoint)
    if version is None or tabs is None:
        version, tabs = fetch_chrome_debugger_state(endpoint)
    tab = _select_chatgpt_tab(tabs)
    safe_url = _safe_public_url(str(tab.get("url") or ""))
    health = _chatgpt_tab_health(safe_url)
    resolved_session_id = _safe_id(session_id or _session_id_from_url(safe_url))
    resolved_agent_id = _safe_id(agent_id or "chatgpt-web-coordinator")
    resolved_project_id = _safe_id(project_id)
    observed_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    browser = str(version.get("Browser") or "Chrome")

    if health != "ready":
        raise ChromeBindingError(
            "ChatGPT tab is not ready for binding; complete login or open a normal ChatGPT page first"
        )

    return {
        "session_id": resolved_session_id,
        "provider": "chatgpt",
        "agent_id": resolved_agent_id,
        "agent_role": "coordinator",
        "project_id": resolved_project_id,
        "run_id": "stage-4-web-ai-binding",
        "task_spec_id": "",
        "status": "active",
        "messages": [
            {
                "message_id": f"{resolved_session_id}-binding-observation",
                "role": "system",
                "content_summary": (
                    "Chrome CDP is reachable and a ChatGPT tab is open. "
                    "No raw transcript, cookies, profile data, or message text was captured."
                ),
                "created_at": observed_at,
            }
        ],
        "tool_calls": [
            {
                "tool_call_id": f"{resolved_session_id}-chrome-cdp",
                "name": "chrome-cdp-tab-observed",
                "status": "completed",
            }
        ],
        "changed_files": [],
        "diff_summary": "",
        "evidence_refs": [],
        "cost": {},
        "tokens": {},
        "gates": [],
        "actions": [
            "Use this imported session as the summary-only ChatGPT external-brain binding for the next governed run."
        ],
        "native_refs": {
            "runtime": "chrome-cdp-binding",
            "cdp_endpoint": endpoint,
            "provider_url": safe_url,
            "browser": browser,
            "observed_at": observed_at,
        },
    }


def render_chrome_binding_text(summary: dict[str, Any]) -> str:
    refs = summary.get("native_refs", {})
    lines = [
        "Chrome Web AI Binding",
        f"provider     : {summary.get('provider', '')}",
        f"session_id   : {summary.get('session_id', '')}",
        f"project_id   : {summary.get('project_id', '')}",
        f"status       : {summary.get('status', '')}",
        f"provider_url : {refs.get('provider_url', '')}",
        f"browser      : {refs.get('browser', '')}",
        "",
        "Summary-only binding: no transcript, cookies, profile data, or message text captured.",
    ]
    return "\n".join(lines) + "\n"


def _safe_cdp_endpoint(value: str) -> str:
    text = str(value or "").strip().rstrip("/")
    parsed = urlparse(text)
    if parsed.scheme not in {"http", "https"}:
        raise ChromeBindingError("CDP endpoint must be an http or https URL")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ChromeBindingError("CDP endpoint must not include credentials, query strings, or fragments")
    host = parsed.hostname or ""
    if host not in {"127.0.0.1", "localhost", "::1"}:
        raise ChromeBindingError("CDP endpoint must be loopback-only")
    return text


def _select_chatgpt_tab(tabs: list[dict[str, Any]]) -> dict[str, Any]:
    chatgpt_tabs = [
        tab for tab in tabs
        if tab.get("type") == "page" and _is_chatgpt_url(str(tab.get("url") or ""))
    ]
    if not chatgpt_tabs:
        raise ChromeBindingError("No ChatGPT page tab found in Chrome CDP")
    ready_tabs = [tab for tab in chatgpt_tabs if _chatgpt_tab_health(str(tab.get("url") or "")) == "ready"]
    return ready_tabs[0] if ready_tabs else chatgpt_tabs[0]


def _is_chatgpt_url(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme == "https" and (parsed.hostname or "").lower() in CHATGPT_HOSTS


def _chatgpt_tab_health(value: str) -> str:
    parsed = urlparse(value)
    path = parsed.path.lower()
    if "auth" in path or "login" in path:
        return "needs_login"
    return "ready" if _is_chatgpt_url(value) else "blocked"


def _safe_public_url(value: str) -> str:
    parsed = urlparse(value)
    if not _is_chatgpt_url(value):
        raise ChromeBindingError("ChatGPT tab URL is not a supported https://chatgpt.com page")
    if parsed.username or parsed.password:
        raise ChromeBindingError("ChatGPT tab URL must not include credentials")
    return urlunparse((parsed.scheme, parsed.netloc, parsed.path or "/", "", "", ""))


def _session_id_from_url(value: str) -> str:
    parsed = urlparse(value)
    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) >= 2 and parts[0] == "c":
        return f"chatgpt-{parts[1]}-session"
    return "chatgpt-chrome-session"


def _safe_id(value: object) -> str:
    text = str(value or "").strip().lower()
    normalized = "".join(
        char if "a" <= char <= "z" or "0" <= char <= "9" else "-"
        for char in text
    )
    normalized = "-".join(part for part in normalized.split("-") if part)
    return normalized or "unknown"
