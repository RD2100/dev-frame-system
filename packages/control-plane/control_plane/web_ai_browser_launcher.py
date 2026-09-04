"""Bind browser-hosted Web AI sessions to the browser owned by DSH.

DevFrame deliberately does not launch a browser or own a persistent browser
profile.  DSH owns login state and browser lifecycle; this module only probes
the DSH-provided CDP endpoint and can open a provider URL in an already-running
DSH browser.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlparse
from urllib.request import Request, urlopen

from .backup_guard import default_runtime_dir
from .chrome_binding_probe import _safe_cdp_endpoint


DEFAULT_CDP_ENDPOINT = "http://127.0.0.1:9222"
DEFAULT_WEB_AI_URL = "https://chatgpt.com/"


class BrowserLaunchError(RuntimeError):
    """Raised when DevFrame cannot ensure a safe browser session."""


@dataclass(frozen=True)
class BrowserLaunchConfig:
    browser: str
    cdp_endpoint: str
    url: str
    profile_policy: str = "dsh_managed"


def default_browser_config_path(runtime_dir: str | Path | None = None) -> Path:
    root = Path(runtime_dir).expanduser().resolve() if runtime_dir else default_runtime_dir()
    return root / "browser-profiles" / "web-ai-browser.json"


def load_browser_launch_config(
    *,
    runtime_dir: str | Path | None = None,
    config_path: str | Path | None = None,
    cdp_endpoint: str | None = None,
    url: str | None = None,
) -> BrowserLaunchConfig:
    """Load only the endpoint/URL portion of local DSH binding config.

    Older config files may still contain browser executable or profile fields.
    They are intentionally ignored and are never materialized or used.
    """

    resolved_config_path = Path(config_path).expanduser().resolve() if config_path else default_browser_config_path(runtime_dir)
    data: dict[str, Any] = {}
    if resolved_config_path.exists():
        try:
            data = json.loads(resolved_config_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise BrowserLaunchError(f"Unable to read browser config: {exc}") from exc

    resolved_endpoint = _safe_cdp_endpoint(str(cdp_endpoint or data.get("cdp_endpoint") or DEFAULT_CDP_ENDPOINT))
    resolved_url = _safe_web_ai_url(str(url or data.get("url") or DEFAULT_WEB_AI_URL))
    # The browser owner is always DSH, even when an older config still carries
    # a provider-specific browser label.
    browser = "dsh"

    return BrowserLaunchConfig(
        browser=browser,
        cdp_endpoint=resolved_endpoint,
        url=resolved_url,
        profile_policy="dsh_managed",
    )


def write_browser_launch_config(config: BrowserLaunchConfig, *, config_path: str | Path | None = None, runtime_dir: str | Path | None = None) -> Path:
    destination = Path(config_path).expanduser().resolve() if config_path else default_browser_config_path(runtime_dir)
    destination.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": "1.0.0",
        "browser": "dsh",
        "cdp_endpoint": config.cdp_endpoint,
        "url": config.url,
        "profile_policy": "dsh_managed",
        "login_policy": "dsh_owned",
        "notes": [
            "DSH owns browser startup, login state, profile, and session lifecycle.",
            "DevFrame only probes the DSH-provided CDP endpoint and may open a URL.",
        ],
    }
    destination.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    return destination


def ensure_web_ai_browser(
    *,
    runtime_dir: str | Path | None = None,
    config_path: str | Path | None = None,
    cdp_endpoint: str | None = None,
    url: str | None = None,
    open_url: bool = True,
    write_config: bool = False,
) -> dict[str, Any]:
    """Probe the DSH-owned browser; never launch a browser or profile."""

    config = load_browser_launch_config(
        runtime_dir=runtime_dir,
        config_path=config_path,
        cdp_endpoint=cdp_endpoint,
        url=url,
    )
    config_written = ""
    if write_config:
        config_written = str(write_browser_launch_config(config, config_path=config_path, runtime_dir=runtime_dir))

    before = probe_cdp(config.cdp_endpoint)
    if before["reachable"]:
        opened = _open_url_via_cdp(config.cdp_endpoint, config.url) if open_url else False
        return _result(
            status="already_running",
            config=config,
            probe=probe_cdp(config.cdp_endpoint),
            started=False,
            opened_url=opened,
            config_written=config_written,
        )
    return _result(
        status="blocked",
        config=config,
        probe=before,
        started=False,
        opened_url=False,
        config_written=config_written,
        reason="dsh_cdp_endpoint_unreachable",
    )


def probe_cdp(cdp_endpoint: str) -> dict[str, Any]:
    endpoint = _safe_cdp_endpoint(cdp_endpoint)
    try:
        with urlopen(f"{endpoint}/json/version", timeout=2) as response:
            version = json.loads(response.read().decode("utf-8"))
        with urlopen(f"{endpoint}/json", timeout=2) as response:
            tabs = json.loads(response.read().decode("utf-8"))
    except (OSError, HTTPError, URLError, json.JSONDecodeError) as exc:
        return {
            "reachable": False,
            "endpoint": endpoint,
            "error": str(exc),
            "browser": "",
            "targets": [],
        }
    return {
        "reachable": True,
        "endpoint": endpoint,
        "browser": str(version.get("Browser") or ""),
        "webSocketDebuggerUrl": str(version.get("webSocketDebuggerUrl") or ""),
        "targets": _summarize_targets(tabs if isinstance(tabs, list) else []),
    }


def render_browser_launch_text(result: dict[str, Any]) -> str:
    lines = [
        "DevFrame Web AI browser",
        f"status       : {result.get('status', '')}",
        f"browser      : {result.get('browser', '')}",
        f"profile_policy: {result.get('profile_policy', '')}",
        f"cdp_endpoint : {result.get('cdp_endpoint', '')}",
        f"url          : {result.get('url', '')}",
        f"started      : {str(result.get('started', False)).lower()}",
        f"opened_url   : {str(result.get('opened_url', False)).lower()}",
    ]
    if result.get("config_written"):
        lines.append(f"config       : {result['config_written']}")
    if result.get("reason"):
        lines.append(f"reason       : {result['reason']}")
    if result.get("first_use_note"):
        lines.append("")
        lines.append(str(result["first_use_note"]))
    return "\n".join(lines) + "\n"


def _result(
    *,
    status: str,
    config: BrowserLaunchConfig,
    probe: dict[str, Any],
    started: bool,
    opened_url: bool,
    config_written: str,
    reason: str = "",
) -> dict[str, Any]:
    return {
        "status": status,
        "browser": config.browser,
        "cdp_endpoint": config.cdp_endpoint,
        "profile_policy": config.profile_policy,
        "url": config.url,
        "started": started,
        "opened_url": opened_url,
        "config_written": config_written,
        "reason": reason,
        "probe": probe,
        "first_use_note": "DSH owns browser startup, login state, profile, and session lifecycle.",
    }


def _open_url_via_cdp(cdp_endpoint: str, url: str) -> bool:
    endpoint = _safe_cdp_endpoint(cdp_endpoint)
    request = Request(f"{endpoint}/json/new?{quote(url, safe=':/?&=#%')}", method="PUT")
    try:
        with urlopen(request, timeout=2):
            return True
    except (OSError, HTTPError, URLError):
        return False


def _summarize_targets(tabs: list[object]) -> list[dict[str, str]]:
    targets = []
    for tab in tabs:
        if not isinstance(tab, dict):
            continue
        targets.append({
            "type": str(tab.get("type") or ""),
            "title": str(tab.get("title") or ""),
            "url": str(tab.get("url") or ""),
        })
    return targets


def _safe_web_ai_url(value: str) -> str:
    parsed = urlparse(value.strip())
    if parsed.scheme != "https":
        raise BrowserLaunchError("Web AI URL must be https")
    if parsed.username or parsed.password:
        raise BrowserLaunchError("Web AI URL must not include credentials")
    return value.strip()
