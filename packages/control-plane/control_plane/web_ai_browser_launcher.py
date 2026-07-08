"""Persistent browser launcher for browser-hosted Web AI sessions."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlparse
from urllib.request import Request, urlopen

from .backup_guard import default_runtime_dir
from .chrome_binding_probe import ChromeBindingError, _safe_cdp_endpoint


DEFAULT_CDP_ENDPOINT = "http://127.0.0.1:9222"
DEFAULT_WEB_AI_URL = "https://chatgpt.com/"


class BrowserLaunchError(RuntimeError):
    """Raised when DevFrame cannot ensure a safe browser session."""


@dataclass(frozen=True)
class BrowserLaunchConfig:
    browser: str
    browser_exe: str
    cdp_endpoint: str
    profile_dir: str
    url: str


def default_browser_config_path(runtime_dir: str | Path | None = None) -> Path:
    root = Path(runtime_dir).expanduser().resolve() if runtime_dir else default_runtime_dir()
    return root / "browser-profiles" / "web-ai-browser.json"


def default_browser_profile_dir(runtime_dir: str | Path | None = None) -> Path:
    root = Path(runtime_dir).expanduser().resolve() if runtime_dir else default_runtime_dir()
    return root / "browser-profiles" / "chatgpt-chrome-cdp"


def load_browser_launch_config(
    *,
    runtime_dir: str | Path | None = None,
    config_path: str | Path | None = None,
    browser_exe: str | None = None,
    cdp_endpoint: str | None = None,
    profile_dir: str | Path | None = None,
    url: str | None = None,
) -> BrowserLaunchConfig:
    """Load local launcher config and apply explicit CLI overrides."""

    resolved_config_path = Path(config_path).expanduser().resolve() if config_path else default_browser_config_path(runtime_dir)
    data: dict[str, Any] = {}
    if resolved_config_path.exists():
        try:
            data = json.loads(resolved_config_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise BrowserLaunchError(f"Unable to read browser config: {exc}") from exc

    resolved_browser_exe = str(browser_exe or data.get("browser_exe") or _default_chrome_path())
    resolved_endpoint = _safe_cdp_endpoint(str(cdp_endpoint or data.get("cdp_endpoint") or DEFAULT_CDP_ENDPOINT))
    resolved_profile_dir = str(Path(profile_dir or data.get("profile_dir") or default_browser_profile_dir(runtime_dir)).expanduser().resolve())
    resolved_url = _safe_web_ai_url(str(url or data.get("url") or DEFAULT_WEB_AI_URL))
    browser = str(data.get("browser") or "chrome")

    return BrowserLaunchConfig(
        browser=browser,
        browser_exe=resolved_browser_exe,
        cdp_endpoint=resolved_endpoint,
        profile_dir=resolved_profile_dir,
        url=resolved_url,
    )


def write_browser_launch_config(config: BrowserLaunchConfig, *, config_path: str | Path | None = None, runtime_dir: str | Path | None = None) -> Path:
    destination = Path(config_path).expanduser().resolve() if config_path else default_browser_config_path(runtime_dir)
    destination.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": "1.0.0",
        "browser": config.browser,
        "browser_exe": config.browser_exe,
        "cdp_endpoint": config.cdp_endpoint,
        "profile_dir": config.profile_dir,
        "url": config.url,
        "profile_policy": "dedicated_persistent_profile",
        "login_policy": "login_once_then_reuse_profile",
        "notes": [
            "This is local runtime config. Do not commit browser profiles, cookies, or session data.",
            "First use may require logging in inside the launched browser window.",
        ],
    }
    destination.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    return destination


def ensure_web_ai_browser(
    *,
    runtime_dir: str | Path | None = None,
    config_path: str | Path | None = None,
    browser_exe: str | None = None,
    cdp_endpoint: str | None = None,
    profile_dir: str | Path | None = None,
    url: str | None = None,
    open_url: bool = True,
    write_config: bool = False,
    wait_seconds: float = 8.0,
    launcher: Any | None = None,
) -> dict[str, Any]:
    """Ensure the dedicated Web AI browser is reachable through CDP."""

    config = load_browser_launch_config(
        runtime_dir=runtime_dir,
        config_path=config_path,
        browser_exe=browser_exe,
        cdp_endpoint=cdp_endpoint,
        profile_dir=profile_dir,
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

    _start_browser(config, open_url=open_url, launcher=launcher)
    deadline = time.time() + wait_seconds
    probe = probe_cdp(config.cdp_endpoint)
    while not probe["reachable"] and time.time() < deadline:
        time.sleep(0.5)
        probe = probe_cdp(config.cdp_endpoint)

    if not probe["reachable"]:
        return _result(
            status="blocked",
            config=config,
            probe=probe,
            started=True,
            opened_url=open_url,
            config_written=config_written,
            reason="cdp_endpoint_unreachable_after_launch",
        )

    return _result(
        status="started",
        config=config,
        probe=probe,
        started=True,
        opened_url=open_url,
        config_written=config_written,
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
        f"cdp_endpoint : {result.get('cdp_endpoint', '')}",
        f"profile_dir  : {result.get('profile_dir', '')}",
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
        "browser_exe": config.browser_exe,
        "cdp_endpoint": config.cdp_endpoint,
        "profile_dir": config.profile_dir,
        "url": config.url,
        "started": started,
        "opened_url": opened_url,
        "config_written": config_written,
        "reason": reason,
        "probe": probe,
        "first_use_note": "First use may require logging in once inside this dedicated browser profile.",
    }


def _start_browser(config: BrowserLaunchConfig, *, open_url: bool, launcher: Any | None = None) -> None:
    browser_path = Path(config.browser_exe)
    if not browser_path.exists():
        raise BrowserLaunchError(f"Browser executable not found: {browser_path}")
    profile_dir = Path(config.profile_dir)
    profile_dir.mkdir(parents=True, exist_ok=True)
    args = [
        str(browser_path),
        f"--remote-debugging-port={_port_from_endpoint(config.cdp_endpoint)}",
        f"--user-data-dir={profile_dir}",
    ]
    if open_url:
        args.append(config.url)
    if launcher is not None:
        launcher(args)
        return
    kwargs: dict[str, Any] = {
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
        "close_fds": True,
    }
    if os.name == "nt":
        kwargs["creationflags"] = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    subprocess.Popen(args, **kwargs)  # noqa: S603 - executable and args are explicit, no shell.


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


def _port_from_endpoint(cdp_endpoint: str) -> int:
    parsed = urlparse(cdp_endpoint)
    if parsed.port is None:
        raise BrowserLaunchError("CDP endpoint must include an explicit port")
    return parsed.port


def _safe_web_ai_url(value: str) -> str:
    parsed = urlparse(value.strip())
    if parsed.scheme != "https":
        raise BrowserLaunchError("Web AI URL must be https")
    if parsed.username or parsed.password:
        raise BrowserLaunchError("Web AI URL must not include credentials")
    return value.strip()


def _default_chrome_path() -> str:
    env = os.environ.get("DEVFRAME_CHROME_EXE")
    if env:
        return env
    if sys.platform.startswith("win"):
        candidates = [
            Path(os.environ.get("PROGRAMFILES", "C:/Program Files")) / "Google/Chrome/Application/chrome.exe",
            Path(os.environ.get("PROGRAMFILES(X86)", "C:/Program Files (x86)")) / "Google/Chrome/Application/chrome.exe",
        ]
        for candidate in candidates:
            if candidate.exists():
                return str(candidate)
    return "chrome"
