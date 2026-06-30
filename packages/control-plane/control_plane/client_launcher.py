"""Zero-config local Agent native client launcher metadata."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
import webbrowser
from pathlib import Path
from threading import Thread
from typing import Any
from urllib.parse import urlparse
from urllib.request import urlopen

from .backup_guard import default_runtime_dir
from .methodology_dispatch import METHODOLOGY_DISPATCH


T3_CODE_SOURCE_URL = "https://github.com/pingdotgg/t3code"
OPENCODE_SOURCE_URL = "https://github.com/anomalyco/opencode"
T3_RENDERER_CDP_DEFAULT_PORT = 8315
T3_RENDERER_WEB_DEV_DEFAULT_ORIGIN = "http://127.0.0.1:5733"

_BROWSER_EXECUTABLE_NAMES = {
    "chrome.exe", "msedge.exe", "firefox.exe", "brave.exe",
    "opera.exe", "iexplore.exe", "chromium.exe",
}

_T3_RUNTIME_EXECUTABLE_NAMES = {
    "node.exe", "electron.exe", "pnpm.exe", "cmd.exe",
}


def build_client_launch_plan(
    runtime_dir: str | Path | None = None,
    *,
    host: str = "127.0.0.1",
    port: int = 8765,
    lang: str = "zh-CN",
    paper_project_dirs: list[str | Path] | None = None,
) -> dict[str, Any]:
    """Build the self-describing launch plan for the local Agent native client."""
    runtime_root = Path(runtime_dir).resolve() if runtime_dir else default_runtime_dir()
    base_url = f"http://{host}:{port}"
    dashboard_url = f"{base_url}/?lang={lang}" if lang else f"{base_url}/"
    t3_status = _first_command_status(["t3", "t3code"])
    opencode_status = _command_status("opencode")
    return {
        "version": 1,
        "name": "devframe-local-agent-client",
        "launch": {
            "mode": "loopback-http",
            "command": "devframe client serve",
            "dryRunCommand": "devframe client --dry-run",
            "url": dashboard_url,
            "primarySurface": "t3code-native-client",
            "auxiliarySurface": "lightweight-web-dashboard",
            "host": host,
            "port": port,
            "runtimeDir": str(runtime_root),
            "paperProjects": [str(Path(path).resolve()) for path in paper_project_dirs or []],
        },
        "surfaces": {
            "primary": {
                "id": "t3code-native-client",
                "candidate": "t3code",
                "kind": "native-client",
                "bridgeEndpoint": f"{base_url}/t3-bridge.json",
                "shellEndpoint": f"{base_url}/t3-shell.json",
                "purpose": "Primary T3 Code native client integration for project, thread, session, and gated action workflows.",
            },
            "auxiliary": [
                {
                    "id": "lightweight-web-dashboard",
                    "kind": "web-dashboard",
                    "url": dashboard_url,
                    "purpose": "Support-only loopback dashboard for snapshots, diagnostics, and public-surface checks.",
                }
            ],
        },
        "reuse": {
            "visualClient": {
                "candidate": "t3code",
                "source": T3_CODE_SOURCE_URL,
                "license": "MIT",
                "status": "bridge-ready" if t3_status.get("available") else "bridge-ready-client-runtime-missing",
                "command": t3_status,
                "boundary": "T3 Code owns the primary native client shell plus project/thread/session interaction patterns.",
            },
            "executor": {
                "candidate": "opencode",
                "source": OPENCODE_SOURCE_URL,
                "license": "MIT",
                "status": "ready" if opencode_status.get("available") else "missing",
                "command": opencode_status,
                "boundary": "OpenCode is the default local coding-agent runtime for the /go development orchestration loop.",
            },
            "devframe": {
                "status": "ready",
                "boundary": "DevFrame owns project contracts, external-brain workflow, read model, evidence, gates, decisions, and write policy.",
            },
        },
        "endpoints": {
            "dashboard": dashboard_url,
            "manifest": f"{base_url}/client-manifest.json",
            "t3Bridge": f"{base_url}/t3-bridge.json",
            "t3Shell": f"{base_url}/t3-shell.json",
            "state": f"{base_url}/state.json",
            "sessions": f"{base_url}/sessions.json",
            "actions": f"{base_url}/actions.json",
            "goDispatch": f"{base_url}/go/dispatch",
            "actionExecute": f"{base_url}/actions/execute",
            "approvalResponse": f"{base_url}/api/t3/approval-response",
            "clientPlan": f"{base_url}/client-plan.json",
        },
        "t3RendererCdp": {
            "port": T3_RENDERER_CDP_DEFAULT_PORT,
            "endpoint": f"http://127.0.0.1:{T3_RENDERER_CDP_DEFAULT_PORT}",
            "rendererOrigin": T3_RENDERER_WEB_DEV_DEFAULT_ORIGIN,
        },
        "reviewGate": {
            "id": "web-gpt-review-gate",
            "provider": "chatgpt",
            "role": "external-reviewer",
            "defaultMode": "dry-run",
            "dryRunCommand": "devframe web-ai submit-review --zip <context.zip> --prompt-file <review-request.md> --conversation <chatgpt-url-or-id>",
            "executeCommand": "devframe web-ai submit-review --zip <context.zip> --prompt-file <review-request.md> --conversation <chatgpt-url-or-id> --execute",
            "promptFileEncodings": ["utf-8", "utf-8-sig", "utf-16-bom"],
            "reviewedInputs": ["diff.patch", "test-output.md", "safety-report.json", "chain-evidence.json"],
            "liveRequires": ["explicit --execute", "loopback Chrome CDP", "summary-only binding", "no raw transcript persistence"],
        },
        "writePolicy": {
            "default": "read-only",
            "blockedMethods": ["PUT", "PATCH", "DELETE"],
            "allowedMutationEndpoints": [
                "/go/dispatch",
                "/actions/execute",
                "/api/t3/approval-response",
                "/api/t3/writeback-propose",
            ],
            "allowedActionKinds": [
                "queued_go_run_execute",
                "web_gpt_task_intake_dispatch",
                "writeback_apply_file",
            ],
            "humanGateRequiredFor": [
                "execute_worker",
                "reply_to_provider",
                "read_browser_profile",
                "persist_raw_transcript",
                "apply_patch",
                "publish_or_deploy",
            ],
        },
        "supportedMethodologies": [
            {
                "skillId": entry["skill_id"],
                "title": entry["title"],
                "displayLabel": entry.get("display_label") or entry["title"],
                "triggers": list(dict.fromkeys(entry.get("triggers", []))),
                "sourceKind": entry.get("source_kind", ""),
                **({"requireRedGreenEvidence": True} if entry.get("require_red_green_evidence") else {}),
                **({"profiles": [
                    {
                        "profileId": p.get("profile_id"),
                        "selectedTriggerLabel": p.get("selected_trigger_label"),
                        "displayLabel": p.get("display_label"),
                        "readOnly": p.get("read_only"),
                        "networkEnabled": p.get("network_enabled"),
                    }
                    for p in entry.get("profiles", [])
                ]} if entry.get("profiles") else {}),
            }
            for entry in METHODOLOGY_DISPATCH.values()
        ],
        "governance": {
            "reconReceipt": "docs/status/recon-receipt-local-agent-client-mainline.md",
            "rkrRulePath": "rules/recon.md",
            "reuseAssessment": "docs/status/t3code-client-mainline-reuse-assessment.md",
            "primaryClientDecision": "T3Code: primary native-client shell; DevFrame owns governance",
            "workerDecision": "OpenCode: local coding-agent worker runtime",
            "webAiAdapterDecision": "CodexPro/DevSpace: Web AI MCP bridge patterns; ZIP/report is fallback only",
            "nextApprovedSlice": "Expose Recon Receipt and reuse decision in client launch plan and visual client manifest",
        },
        "acceptance": {
            "zeroConfig": True,
            "browserCheck": "Open the auxiliary launch.url and verify project, sessions, gates, actions, /go/dispatch, /client-manifest.json, and /t3-shell.json are reachable.",
            "nextIntegrationStep": "Install the T3 Code bridge from endpoints.t3Bridge, point the primary native T3 shell at endpoints.t3Shell and endpoints.manifest, then use reviewGate for Web GPT external review before gated execution.",
        },
    }


def render_client_launch_plan_json(plan: dict[str, Any] | None = None) -> str:
    return json.dumps(plan or build_client_launch_plan(), indent=2, ensure_ascii=True)


def render_client_launch_plan_text(plan: dict[str, Any]) -> str:
    visual_client = plan["reuse"]["visualClient"]
    executor = plan["reuse"]["executor"]
    lines = [
        "DevFrame Local Agent Client",
        "Primary path : devframe code (governed coding CLI)",
        "Mode         : Secondary T3 Code desktop/native client + DevFrame read model + control-plane inspection",
        f"T3 shell     : {plan['endpoints']['t3Shell']}",
        f"Dashboard    : {plan['launch']['url']} (auxiliary)",
        f"Runtime      : {plan['launch']['runtimeDir']}",
        f"T3 bridge    : {visual_client['status']}",
        f"OpenCode     : {executor['status']}",
        f"Review gate  : {plan['reviewGate']['id']} ({plan['reviewGate']['defaultMode']} default)",
        "Write policy : read-only until a future human-gated adapter is enabled",
        "",
        "Endpoints",
        f"- t3 bridge : {plan['endpoints']['t3Bridge']}",
        f"- t3 shell  : {plan['endpoints']['t3Shell']}",
        f"- manifest  : {plan['endpoints']['manifest']}",
        f"- dashboard : {plan['endpoints']['dashboard']} (auxiliary)",
        f"- sessions  : {plan['endpoints']['sessions']}",
        f"- actions   : {plan['endpoints']['actions']}",
        f"- /go page  : {plan['endpoints']['goDispatch']}",
        "",
        "Reuse boundary",
        "- T3 Code: secondary native client shell for project/thread/session inspection",
        "- OpenCode: local coding-agent runtime for /go development orchestration",
        "- Web GPT: external review gate through explicit submit-review command",
        "- DevFrame: primary governed coding product, plus evidence, gates, decisions, /go dispatch, auxiliary dashboard, and external-brain workflow",
    ]
    return "\n".join(lines) + "\n"


def _is_loopback_host(host: str) -> bool:
    if host.lower() == "localhost":
        return True
    try:
        import ipaddress
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def _check_windows_shell() -> dict[str, Any]:
    pwsh_path = shutil.which("pwsh.exe") or ""
    ps_path = shutil.which("powershell.exe") or ""
    pwsh_ok = bool(pwsh_path)
    ps_ok = bool(ps_path)
    if pwsh_ok:
        return {
            "name": "windows-shell",
            "ok": True,
            "status": "pass",
            "pwshPath": pwsh_path,
            "powershellFallback": ps_path if ps_ok else None,
        }
    if ps_ok:
        return {
            "name": "windows-shell",
            "ok": True,
            "status": "pass-with-warnings",
            "pwshPath": None,
            "powershellPath": ps_path,
            "fixHint": "pwsh.exe not found; DevFrame will fall back to powershell.exe. Install PowerShell 7+ for best experience.",
        }
    return {
        "name": "windows-shell",
        "ok": False,
        "status": "fail",
        "pwshPath": None,
        "powershellPath": None,
        "fixHint": "Neither pwsh.exe nor powershell.exe found. Install PowerShell from https://github.com/PowerShell/PowerShell.",
    }


def _check_electron_runtime(t3_root: Path) -> dict[str, Any]:
    electron_glob = "node_modules/.pnpm/electron@*/node_modules/electron/dist/electron.exe"
    matches = list(t3_root.glob(electron_glob))
    electron_exe = matches[0] if matches else None
    path_txt = None
    if electron_exe:
        package_root = electron_exe.parent.parent
        candidate = package_root / "path.txt"
        if candidate.exists():
            path_txt = candidate
    check = {
        "name": "electron-runtime",
        "ok": electron_exe is not None and path_txt is not None,
        "status": "pass" if electron_exe is not None and path_txt is not None else "fail",
        "electronExe": str(electron_exe) if electron_exe else None,
        "pathTxt": str(path_txt) if path_txt else None,
        "scanned": str(t3_root / electron_glob),
        "fixHint": (
            "Run 'pnpm install' in the T3 checkout to restore electron-v41.5.0-win32-x64.zip "
            "and its runtime files."
            if not electron_exe or not path_txt
            else None
        ),
    }
    return check


_SPLASH_TITLE_PATTERNS: list[str] = [
    "t3 code",
    "loading",
    "splash",
    "boot",
]


def _is_splash_title(title: str) -> bool:
    lower = title.lower()
    return lower == "" or lower in _SPLASH_TITLE_PATTERNS


def _is_loopback_t3_renderer_page(page: dict[str, Any], title: str) -> bool:
    if "t3 code" not in title:
        return False
    page_url = (page.get("url") or "").strip()
    if not page_url:
        return False
    try:
        parsed = urlparse(page_url)
    except ValueError:
        return False
    return parsed.scheme in {"http", "https"} and parsed.hostname in {
        "127.0.0.1",
        "localhost",
        "::1",
    }


def _probe_cdp_targets(cdp_endpoint: str, timeout: int = 3) -> dict[str, Any]:
    base = cdp_endpoint.rstrip("/")
    list_url = f"{base}/json/list"
    try:
        with urlopen(list_url, timeout=timeout) as resp:
            targets = json.loads(resp.read().decode("utf-8"))
            if not isinstance(targets, list):
                return {"reachable": False, "error": "invalid target list format"}
            return {"reachable": True, "targets": targets}
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        return {"reachable": False, "error": str(exc)}


def _check_boot_shell_element(
    cdp_endpoint: str,
    targets: list[dict[str, Any]],
    timeout: int = 3,
    origin: str | None = None,
) -> dict[str, Any]:
    for target in targets:
        if target.get("type") != "page":
            continue
        ws_url = target.get("webSocketDebuggerUrl")
        if not ws_url:
            continue
        try:
            from websocket import create_connection
        except ImportError:
            return {"available": False, "error": "websocket-client not installed"}
        try:
            create_kwargs: dict[str, Any] = {"timeout": timeout}
            if origin:
                create_kwargs["origin"] = origin
            ws = create_connection(ws_url, **create_kwargs)
            ws.send(
                json.dumps(
                    {
                        "id": 1,
                        "method": "Runtime.evaluate",
                        "params": {
                            "expression": "!!document.querySelector('#boot-shell')",
                            "returnByValue": True,
                        },
                    }
                )
            )
            raw = ws.recv()
            ws.close()
            result = json.loads(raw)
            if "result" in result and "result" in result.get("result", {}):
                value = result["result"]["result"].get("value", False)
                return {"available": True, "present": bool(value)}
            return {"available": True, "present": False}
        except Exception as exc:
            return {"available": False, "error": str(exc)}
    return {"available": False, "error": "no page target with webSocketDebuggerUrl"}


def _analyze_renderer_state(
    targets: list[dict[str, Any]],
    dashboard_url: str = "",
    t3_renderer_origins: list[str] | None = None,
) -> dict[str, Any]:
    pages = [t for t in targets if isinstance(t, dict) and t.get("type") == "page"]
    if not pages:
        return {
            "status": "no-page",
            "detail": "No page targets visible; T3 renderer may be at boot shell or not yet launched.",
        }

    known_origins: list[str] = []
    if dashboard_url:
        parsed = urlparse(dashboard_url)
        known_origins.append(f"{parsed.scheme}://{parsed.netloc}")
    for origin in (t3_renderer_origins or []):
        if origin and origin not in known_origins:
            known_origins.append(origin)

    def _url_matches(page: dict[str, Any]) -> bool:
        if not known_origins:
            return True
        page_url = (page.get("url") or "").strip()
        if not page_url:
            return False
        return any(page_url.startswith(origin) for origin in known_origins)

    splash_pages: list[dict[str, Any]] = []
    rendered_pages: list[dict[str, Any]] = []
    unrelated_pages: list[dict[str, Any]] = []
    for page in pages:
        title = (page.get("title") or "").strip().lower()
        if not _url_matches(page) and not _is_loopback_t3_renderer_page(page, title):
            unrelated_pages.append(page)
            continue
        is_splash = _is_splash_title(title)
        if is_splash:
            splash_pages.append(page)
        else:
            rendered_pages.append(page)

    if rendered_pages:
        return {
            "status": "rendered",
            "detail": (
                f"Found {len(rendered_pages)} rendered page(s)."
            ),
            "pageCount": len(rendered_pages),
        }

    if splash_pages:
        return {
            "status": "boot-shell",
            "detail": (
                f"Only splash/boot pages visible ({len(splash_pages)}). "
                "T3 renderer has not loaded application content."
            ),
            "pageCount": len(splash_pages),
        }

    if unrelated_pages:
        origins_text = ", ".join(known_origins) if known_origins else "(any)"
        return {
            "status": "unknown-page",
            "detail": (
                f"Found {len(unrelated_pages)} page(s) at CDP endpoint "
                f"but none match recognized origins ({origins_text}). "
                "Unrelated pages may indicate the CDP endpoint is not the T3 renderer."
            ),
            "pageCount": len(unrelated_pages),
        }

    return {
        "status": "unknown-page",
        "detail": (
            f"Found {len(pages)} page(s) but cannot determine render state."
        ),
        "pageCount": len(pages),
    }


def _t3_renderer_origins_from_plan(plan: dict[str, Any]) -> list[str]:
    origins: list[str] = []
    cdp_section = plan.get("t3RendererCdp")
    if isinstance(cdp_section, dict):
        renderer_origin = str(cdp_section.get("rendererOrigin") or "")
        if renderer_origin:
            try:
                parsed = urlparse(renderer_origin)
                if parsed.scheme and parsed.netloc:
                    origins.append(f"{parsed.scheme}://{parsed.netloc}")
            except ValueError:
                pass
    return origins


def check_client_readiness(
    runtime_dir: str | Path | None = None,
    *,
    t3_root: str | Path | None = None,
    host: str = "127.0.0.1",
    port: int = 8765,
    lang: str = "zh-CN",
    force: bool = False,
    allow_remote: bool = False,
    cdp_endpoint: str | None = None,
) -> dict[str, Any]:
    plan = build_client_launch_plan(
        runtime_dir,
        host=host,
        port=port,
        lang=lang,
    )
    checks: list[dict[str, Any]] = []
    fix_hints: list[str] = []

    resolved_t3_root = Path(t3_root).resolve() if t3_root else None
    if resolved_t3_root is None:
        resolved_t3_root = Path(_discover_t3_root()) if _discover_t3_root() else None

    t3_root_ok = resolved_t3_root is not None and _is_valid_t3_checkout(resolved_t3_root)
    checks.append({
        "name": "t3-root",
        "ok": t3_root_ok,
        "status": "pass" if t3_root_ok else "fail",
        "path": str(resolved_t3_root) if resolved_t3_root else None,
        "fixHint": (
            "Pass --t3-root <valid T3 checkout> or set DEVFRAME_T3_ROOT/T3CODE_ROOT/T3_ROOT."
            if not t3_root_ok
            else None
        ),
    })
    if not t3_root_ok:
        fix_hints.append("Set a valid T3 checkout via --t3-root or DEVFRAME_T3_ROOT/T3CODE_ROOT/T3_ROOT.")

    primary_surface = plan["launch"]["primarySurface"]
    auxiliary_surface = plan["launch"]["auxiliarySurface"]
    surface_ok = primary_surface == "t3code-native-client" and auxiliary_surface == "lightweight-web-dashboard"
    checks.append({
        "name": "surfaces",
        "ok": surface_ok,
        "status": "pass" if surface_ok else "fail",
        "primarySurface": primary_surface,
        "auxiliarySurface": auxiliary_surface,
        "fixHint": (
            "Recon Receipt assigns T3Code as primary native client and web dashboard as auxiliary only."
            if not surface_ok
            else None
        ),
    })

    endpoint_urls = {
        "dashboard": plan["endpoints"]["dashboard"],
        "manifest": plan["endpoints"]["manifest"],
        "t3Bridge": plan["endpoints"]["t3Bridge"],
        "t3Shell": plan["endpoints"]["t3Shell"],
        "goDispatch": plan["endpoints"]["goDispatch"],
    }
    expected_prefix = f"http://{host}:{port}"
    endpoints_ok = all(url.startswith(expected_prefix) for url in endpoint_urls.values())
    checks.append({
        "name": "endpoints",
        "ok": endpoints_ok,
        "status": "pass" if endpoints_ok else "fail",
        "urls": endpoint_urls,
        "fixHint": (
            "Regenerate the launch plan with matching --host and --port."
            if not endpoints_ok
            else None
        ),
    })

    remote_ok = allow_remote or _is_loopback_host(host)
    checks.append({
        "name": "remote-host-guard",
        "ok": remote_ok,
        "status": "pass" if remote_ok else "fail",
        "host": host,
        "fixHint": (
            "Add --allow-remote to bind outside loopback."
            if not remote_ok
            else None
        ),
    })

    bridge_check = None
    electron_check = None
    if t3_root_ok and resolved_t3_root:
        from .t3_bridge_bundle import (
            build_t3_bridge_bundle,
            install_t3_bridge_bundle,
        )
        bundle = build_t3_bridge_bundle(plan)
        required_files = [
            "devframe.t3desktop.mjs",
            "devframe.t3web.mjs",
            ".env.devframe.local",
            "apps/web/src/devframe/devframeShellBridge.ts",
        ]
        try:
            install_t3_bridge_bundle(resolved_t3_root, bundle, force=force)
        except (FileExistsError, ValueError) as exc:
            if isinstance(exc, FileExistsError):
                missing = [f for f in required_files if not (resolved_t3_root / f).exists()]
                if missing:
                    checks.append({
                        "name": "t3-bridge",
                        "ok": False,
                        "status": "fail",
                        "error": str(exc),
                        "requiredFiles": required_files,
                        "missing": missing,
                        "fixHint": (
                            f"Bridge files missing after existing install conflict: {missing}. "
                            "Re-run with --force or inspect the T3 root permissions."
                        ),
                    })
                    fix_hints.append("Restore missing T3 bridge files.")
                else:
                    checks.append({
                        "name": "t3-bridge",
                        "ok": True,
                        "status": "pass",
                        "detail": "Bridge files already present; install skipped to preserve existing files.",
                    })
            else:
                checks.append({
                    "name": "t3-bridge",
                    "ok": False,
                    "status": "fail",
                    "error": str(exc),
                    "fixHint": "Use --force to overwrite existing bridge files or resolve the install conflict.",
                })
                fix_hints.append("Resolve the T3 bridge bundle install conflict or pass --force.")
        else:
            missing = [f for f in required_files if not (resolved_t3_root / f).exists()]
            bridge_check = {
                "name": "t3-bridge",
                "ok": not missing,
                "status": "pass" if not missing else "fail",
                "requiredFiles": required_files,
                "missing": missing,
                "fixHint": (
                    f"Missing bridge files: {missing}. Re-run with --force or inspect the T3 root permissions."
                    if missing
                    else None
                ),
            }
            checks.append(bridge_check)
            if missing:
                fix_hints.append("Restore missing T3 bridge files.")

        electron_check = _check_electron_runtime(resolved_t3_root)
        checks.append(electron_check)
        if not electron_check["ok"]:
            fix_hints.append(
                "Run 'pnpm install' in the T3 checkout to restore electron-v41.5.0-win32-x64.zip "
                "and its runtime files."
            )

        runtime_processes = _enumerate_processes()
        stale_processes = _find_stale_t3_processes(resolved_t3_root, processes=runtime_processes)
        active_launcher = _has_active_t3_desktop_launcher(
            resolved_t3_root,
            port=port,
            processes=runtime_processes,
        )
        stale_ok = len(stale_processes) == 0 or active_launcher
        stale_check: dict[str, Any] = {
            "name": "stale-t3-processes",
            "ok": stale_ok,
            "status": "pass" if stale_ok else "warning",
            "staleCount": 0 if active_launcher else len(stale_processes),
            "stalePids": [] if active_launcher else [int(p["pid"]) for p in stale_processes],
            "runtimeProcessCount": len(stale_processes),
            "runtimeProcessPids": [int(p["pid"]) for p in stale_processes],
            "activeLauncher": active_launcher,
        }
        if active_launcher and stale_processes:
            stale_check["detail"] = (
                "DevFrame-owned T3 runtime processes are active under the current launcher; "
                "they are not treated as stale."
            )
        elif not stale_ok:
            stale_check["fixHint"] = (
                f"Found {len(stale_processes)} stale DevFrame T3 process(es) "
                f"(PIDs: {[int(p['pid']) for p in stale_processes]}). "
                "Run with --force to clean up before launching."
            )
            fix_hints.append(
                f"Clean up {len(stale_processes)} stale T3 process(es) by running with --force."
            )
        checks.append(stale_check)

    if sys.platform == "win32":
        shell_check = _check_windows_shell()
        checks.append(shell_check)
        if shell_check.get("fixHint"):
            fix_hints.append(shell_check["fixHint"])

    dashboard_url = plan["endpoints"].get("dashboard", "")
    if cdp_endpoint:
        effective_cdp = cdp_endpoint
        cdp_source = "explicit"
    else:
        effective_cdp = plan.get("t3RendererCdp", {}).get("endpoint")
        cdp_source = "default"
    if effective_cdp:
        cdp_probe = _probe_cdp_targets(effective_cdp)
        if cdp_probe.get("reachable"):
            t3_origins = _t3_renderer_origins_from_plan(plan)
            renderer_state = _analyze_renderer_state(
                cdp_probe["targets"],
                dashboard_url=dashboard_url,
                t3_renderer_origins=t3_origins,
            )
            if renderer_state.get("status") == "rendered":
                dom_check = _check_boot_shell_element(
                    effective_cdp,
                    cdp_probe["targets"],
                    origin=t3_origins[0] if t3_origins else None,
                )
                if dom_check.get("available") and dom_check.get("present"):
                    renderer_state = {
                        "status": "not-mounted",
                        "detail": (
                            "Renderer shows a loaded page, but #boot-shell is still "
                            "present in the DOM. The application has not finished mounting."
                        ),
                        "pageCount": renderer_state.get("pageCount", 0),
                    }
            renderer_ok = renderer_state.get("status") == "rendered"
            renderer_status = "pass" if renderer_ok else "warning"
            renderer_check: dict[str, Any] = {
                "name": "t3-renderer-state",
                "ok": renderer_ok,
                "status": renderer_status,
                "cdpEndpoint": effective_cdp,
                "cdpSource": cdp_source,
                "rendererState": renderer_state.get("status"),
                "detail": renderer_state.get("detail"),
            }
            if renderer_state.get("status") == "boot-shell":
                renderer_check["fixHint"] = (
                    "T3 renderer shows boot shell only; "
                    "wait for application to load or restart the T3 desktop client."
                )
            elif renderer_state.get("status") == "not-mounted":
                renderer_check["fixHint"] = (
                    "T3 renderer title changed but #boot-shell is still present; "
                    "wait for the application to finish mounting or restart the T3 desktop client."
                )
            checks.append(renderer_check)
            if renderer_state.get("status") == "boot-shell":
                fix_hints.append(
                    "T3 renderer is at splash screen; the client may need to complete loading."
                )
            elif renderer_state.get("status") == "not-mounted":
                fix_hints.append(
                    "T3 renderer has not finished mounting; "
                    "the client may need to complete application startup."
                )
        else:
            renderer_ok = cdp_source != "default"
            renderer_status = "warning" if not renderer_ok else "unknown"
            renderer_check: dict[str, Any] = {
                "name": "t3-renderer-state",
                "ok": renderer_ok,
                "status": renderer_status,
                "cdpEndpoint": effective_cdp,
                "cdpSource": cdp_source,
                "error": cdp_probe.get("error", "unknown"),
                "detail": "CDP endpoint unreachable; cannot determine T3 renderer state.",
                "fixHint": (
                    "Ensure the T3 desktop client is launched with remote debugging enabled "
                    "on the DevFrame-owned default renderer endpoint."
                ),
            }
            checks.append(renderer_check)
            if not renderer_ok:
                fix_hints.append(
                    "T3 renderer CDP endpoint is unreachable; "
                    "restart or launch the T3 desktop client with the DevFrame bridge "
                    "so the default renderer endpoint is available for doctor probes."
                )
    else:
        checks.append({
            "name": "t3-renderer-state",
            "ok": True,
            "status": "unknown",
            "cdpEndpoint": None,
            "cdpSource": "default",
            "detail": "No CDP endpoint available; cannot probe T3 renderer state.",
        })

    overall = "pass"
    for check in checks:
        if check["status"] == "fail":
            if check["name"] in {"t3-root", "surfaces", "endpoints", "remote-host-guard"}:
                overall = "fail"
            elif check["name"] == "t3-renderer-state":
                overall = "pass-with-warnings" if overall == "pass" else overall
            else:
                overall = "blocked"
            break
        if check["status"] in {"pass-with-warnings", "warning"}:
            overall = "pass-with-warnings"

    result: dict[str, Any] = {
        "status": overall,
        "plan": plan,
        "checks": checks,
        "fixHints": fix_hints,
    }
    return result


def render_client_readiness_text(result: dict[str, Any]) -> str:
    status = result.get("status", "unknown")
    lines = [
        "DevFrame Client Doctor",
        f"status      : {status}",
        "",
        "Checks",
    ]
    for check in result.get("checks", []):
        status_label = check.get("status", "unknown").upper()
        lines.append(f"  {status_label} {check.get('name', '')}")
        if check.get("path"):
            lines.append(f"    path     : {check['path']}")
        if check.get("primarySurface"):
            lines.append(f"    primary  : {check['primarySurface']}")
        if check.get("auxiliarySurface"):
            lines.append(f"    auxiliary: {check['auxiliarySurface']}")
        if check.get("urls"):
            for label, url in check["urls"].items():
                lines.append(f"    {label:<10}: {url}")
        if check.get("host"):
            lines.append(f"    host     : {check['host']}")
        if check.get("electronExe"):
            lines.append(f"    electron : {check['electronExe']}")
        if check.get("pathTxt"):
            lines.append(f"    pathTxt  : {check['pathTxt']}")
        if check.get("scanned"):
            lines.append(f"    scanned  : {check['scanned']}")
        if check.get("missing"):
            lines.append(f"    missing  : {check['missing']}")
        if check.get("staleCount") is not None:
            lines.append(f"    staleCount: {check['staleCount']}")
        if check.get("stalePids"):
            lines.append(f"    stalePids: {check['stalePids']}")
        if check.get("fixHint"):
            lines.append(f"    fixHint  : {check['fixHint']}")
        if check.get("cdpEndpoint"):
            lines.append(f"    cdp      : {check['cdpEndpoint']}")
        if check.get("cdpSource"):
            lines.append(f"    cdpSource: {check['cdpSource']}")
        if check.get("rendererState"):
            lines.append(f"    renderer : {check['rendererState']}")
        if check.get("detail"):
            lines.append(f"    detail   : {check['detail']}")
        if check.get("error"):
            lines.append(f"    error    : {check['error']}")
    fix_hints = result.get("fixHints") or []
    if fix_hints:
        lines.extend(["", "Fix hints"])
        for hint in fix_hints:
            lines.append(f"  - {hint}")
    return "\n".join(lines) + "\n"


def serve_local_agent_client(
    runtime_dir: str | Path | None = None,
    *,
    host: str = "127.0.0.1",
    port: int = 8765,
    refresh_seconds: int = 5,
    lang: str = "zh-CN",
    paper_project_dirs: list[str | Path] | None = None,
    open_browser: bool = False,
) -> None:
    from .dashboard import serve_dashboard

    plan = build_client_launch_plan(
        runtime_dir,
        host=host,
        port=port,
        lang=lang,
        paper_project_dirs=paper_project_dirs,
    )
    print(render_client_launch_plan_text(plan), end="")
    if open_browser:
        webbrowser.open(plan["launch"]["url"])
    serve_dashboard(
        runtime_dir=runtime_dir,
        host=host,
        port=port,
        refresh_seconds=refresh_seconds,
        paper_project_dirs=paper_project_dirs,
    )


def serve_t3_desktop_client(
    runtime_dir: str | Path | None = None,
    *,
    t3_root: str | Path | None = None,
    host: str = "127.0.0.1",
    port: int = 8765,
    lang: str = "zh-CN",
    paper_project_dirs: list[str | Path] | None = None,
    force: bool = False,
    open_browser: bool = False,
    refresh_seconds: int = 5,
    mode: str = "dev",
) -> int:
    from .dashboard import serve_dashboard
    from .t3_bridge_bundle import (
        BRIDGE_T3_DESKTOP_LAUNCHER_RELATIVE_PATH,
        BRIDGE_T3_DESKTOP_PROD_LAUNCHER_RELATIVE_PATH,
        build_t3_bridge_bundle,
        install_t3_bridge_bundle,
        render_t3_bridge_bundle_text,
    )

    plan = build_client_launch_plan(
        runtime_dir,
        host=host,
        port=port,
        lang=lang,
        paper_project_dirs=paper_project_dirs,
    )
    print(render_client_launch_plan_text(plan), end="")

    resolved_t3_root = t3_root or _discover_t3_root()
    if not resolved_t3_root:
        print("ERROR: T3 desktop launcher not found; pass --t3-root to install the bridge bundle first.", file=sys.stderr)
        print("Diagnostics:", file=sys.stderr)
        for env_var in ("DEVFRAME_T3_ROOT", "T3CODE_ROOT", "T3_ROOT"):
            if os.environ.get(env_var):
                print(f"  {env_var}=<set, invalid T3 checkout>", file=sys.stderr)
            else:
                print(f"  {env_var}=<unset>", file=sys.stderr)
        print("  current directory and parents were checked (no valid T3 checkout found)", file=sys.stderr)
        print("Fix: set one of the env vars above to a T3 checkout root, or pass --t3-root <path>.", file=sys.stderr)
        return 1

    t3_root = resolved_t3_root

    bundle = build_t3_bridge_bundle(plan)
    written_paths: list[Path] = []
    if t3_root:
        try:
            written_paths.extend(install_t3_bridge_bundle(t3_root, bundle, force=force))
        except (FileExistsError, ValueError) as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 2
        print(render_t3_bridge_bundle_text(bundle), end="")
        for path in written_paths:
            print(f"wrote       : {path}")

    dashboard_url = plan["launch"]["url"]
    print(f"\n[devframe] Auxiliary dashboard: {dashboard_url}")

    thread = Thread(
        target=serve_dashboard,
        kwargs={
            "runtime_dir": runtime_dir,
            "host": host,
            "port": port,
            "refresh_seconds": refresh_seconds,
            "paper_project_dirs": paper_project_dirs,
        },
        daemon=True,
    )
    thread.start()

    if open_browser:
        webbrowser.open(dashboard_url)

    resolved_t3_root_path = Path(t3_root).resolve()
    if force:
        cleanup = _cleanup_stale_t3_processes(resolved_t3_root_path)
        if cleanup["stale_found"]:
            print(
                f"[devframe] Force cleanup: found {cleanup['stale_found']} stale T3 process(es) "
                f"(PIDs: {cleanup['stale_pids']})"
            )
            if cleanup["terminated"]:
                print(f"[devframe] Terminated {len(cleanup['terminated'])} process(es): {cleanup['terminated']}")
            if cleanup["errors"]:
                for error in cleanup["errors"]:
                    print(f"[devframe] {error}", file=sys.stderr)
        else:
            print("[devframe] Force cleanup: no stale T3 processes found")

    launcher_name = (
        BRIDGE_T3_DESKTOP_PROD_LAUNCHER_RELATIVE_PATH
        if mode == "prod"
        else BRIDGE_T3_DESKTOP_LAUNCHER_RELATIVE_PATH
    )
    launcher_path = resolved_t3_root_path / launcher_name
    if not launcher_path.exists():
        print("ERROR: T3 desktop launcher not found; pass --t3-root to install the bridge bundle first.", file=sys.stderr)
        return 1

    if mode == "prod":
        print(f"[devframe] Starting T3 Desktop (production build): {launcher_path}")
    else:
        print(f"[devframe] Starting T3 Desktop launcher: {launcher_path}")
    try:
        completed = subprocess.run(["node", str(launcher_path)], cwd=str(resolved_t3_root_path), check=False)
    except FileNotFoundError:
        print("ERROR: node not found; install Node.js to run the T3 desktop launcher.", file=sys.stderr)
        return 1
    return completed.returncode


def _command_status(command: str) -> dict[str, Any]:
    path = shutil.which(command) or ""
    return {
        "name": command,
        "available": bool(path),
        "path": path,
    }


def _first_command_status(commands: list[str]) -> dict[str, Any]:
    checked = [_command_status(command) for command in commands]
    for status in checked:
        if status["available"]:
            return status
    return checked[0]


def _is_valid_t3_checkout(path: str | Path) -> bool:
    root = Path(path)
    return (root / "package.json").exists() and (root / "apps" / "web").is_dir()


def _discover_t3_root() -> str | None:
    for env_var in ("DEVFRAME_T3_ROOT", "T3CODE_ROOT", "T3_ROOT"):
        candidate = os.environ.get(env_var)
        if candidate and _is_valid_t3_checkout(candidate):
            return candidate

    cwd = Path.cwd()
    for parent in [cwd, *cwd.parents]:
        runtime_t3 = parent / ".devframe-runtime" / "external" / "t3code"
        if _is_valid_t3_checkout(runtime_t3):
            return str(runtime_t3)
        if _is_valid_t3_checkout(parent):
            return str(parent)

    return None


def _enumerate_processes() -> list[dict[str, Any]]:
    if sys.platform != "win32":
        return []
    try:
        completed = subprocess.run(
            [
                "powershell.exe", "-NoProfile", "-Command",
                "Get-CimInstance Win32_Process | "
                "Select-Object @{N='pid';E={$_.ProcessId}}, "
                "@{N='name';E={$_.Name}}, "
                "@{N='command_line';E={$_.CommandLine}} | "
                "ConvertTo-Json -Compress",
            ],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=15,
        )
        if completed.returncode != 0:
            return []
        raw = (completed.stdout or "").strip()
        if not raw:
            return []
        data = json.loads(raw)
        if isinstance(data, dict):
            data = [data]
        result: list[dict[str, Any]] = []
        for proc in data:
            if isinstance(proc, dict) and proc.get("pid"):
                result.append({
                    "pid": int(proc["pid"]),
                    "name": str(proc.get("name") or ""),
                    "command_line": str(proc.get("command_line") or ""),
                })
        return result
    except (subprocess.TimeoutExpired, json.JSONDecodeError, OSError, ValueError):
        return []


def _find_stale_t3_processes(
    t3_root: Path,
    processes: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    if processes is None:
        processes = _enumerate_processes()
    t3_root_str = str(t3_root.resolve()).lower()
    results: list[dict[str, Any]] = []
    for proc in processes:
        name = (proc.get("name") or "").lower()
        cmd = (proc.get("command_line") or "").lower()
        if name in _BROWSER_EXECUTABLE_NAMES:
            continue
        if not proc.get("pid"):
            continue
        if int(proc["pid"]) == os.getpid():
            continue
        if name not in _T3_RUNTIME_EXECUTABLE_NAMES:
            continue
        if t3_root_str not in cmd:
            continue
        results.append(proc)
    return results


def _has_active_t3_desktop_launcher(
    t3_root: Path,
    *,
    port: int,
    processes: list[dict[str, Any]] | None = None,
) -> bool:
    if processes is None:
        processes = _enumerate_processes()
    t3_root_str = str(t3_root.resolve()).lower()
    for proc in processes:
        name = (proc.get("name") or "").lower()
        cmd = (proc.get("command_line") or "").lower()
        if name not in {"python.exe", "python"}:
            continue
        if "control_plane.cli" not in cmd or "client t3desktop" not in cmd:
            continue
        if t3_root_str not in cmd:
            continue
        if f"--port {port}" not in cmd:
            continue
        return True
    return False


def _terminate_process_tree(pid: int) -> bool:
    try:
        completed = subprocess.run(
            ["taskkill", "/PID", str(pid), "/F", "/T"],
            capture_output=True, timeout=10, check=False,
        )
        return completed.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def _cleanup_stale_t3_processes(t3_root: Path) -> dict[str, Any]:
    processes = _enumerate_processes()
    stale = _find_stale_t3_processes(t3_root, processes=processes)
    terminated_pids: list[int] = []
    errors: list[str] = []
    for proc in stale:
        pid = int(proc["pid"])
        if _terminate_process_tree(pid):
            terminated_pids.append(pid)
        else:
            errors.append(f"failed to terminate PID {pid} ({proc.get('name', '')})")
    return {
        "stale_found": len(stale),
        "stale_pids": [int(p["pid"]) for p in stale],
        "terminated": terminated_pids,
        "errors": errors,
    }


def smoke_local_agent_client(
    runtime_dir: str | Path | None = None,
    *,
    host: str = "127.0.0.1",
    port: int = 0,
    lang: str = "zh-CN",
    paper_project_dirs: list[str | Path] | None = None,
    output_format: str = "text",
    t3_root: str | Path | None = None,
    force: bool = False,
) -> int:
    from .dashboard import build_dashboard_server
    from .t3_bridge_bundle import (
        build_t3_bridge_bundle,
        install_t3_bridge_bundle,
        render_t3_bridge_bundle_text,
    )

    server = build_dashboard_server(
        runtime_dir=runtime_dir,
        host=host,
        port=port,
        refresh_seconds=0,
        paper_project_dirs=paper_project_dirs,
    )
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        address, actual_port = server.server_address
        base_url = f"http://{address}:{actual_port}"
        plan = build_client_launch_plan(
            runtime_dir,
            host=host,
            port=actual_port,
            lang=lang,
            paper_project_dirs=paper_project_dirs,
        )

        for _ in range(20):
            try:
                with urlopen(f"{base_url}/healthz", timeout=1) as response:
                    if response.status == 200:
                        break
            except OSError:
                time.sleep(0.1)

        required_endpoints = [
            "/client-plan.json",
            "/client-manifest.json",
            "/t3-bridge.json",
            "/t3-shell.json",
            "/actions.json",
            "/sessions.json",
        ]

        fetched: dict[str, Any] = {}
        missing_endpoint = None
        invalid_json = None
        for endpoint in required_endpoints:
            try:
                with urlopen(f"{base_url}{endpoint}", timeout=5) as response:
                    raw = response.read().decode("utf-8")
                    try:
                        fetched[endpoint] = json.loads(raw)
                    except json.JSONDecodeError as exc:
                        invalid_json = (endpoint, str(exc))
            except OSError as exc:
                missing_endpoint = (endpoint, str(exc))

        if missing_endpoint:
            print(f"ERROR: missing endpoint {missing_endpoint[0]}: {missing_endpoint[1]}", file=sys.stderr)
            return 1
        if invalid_json:
            print(f"ERROR: invalid JSON from {invalid_json[0]}: {invalid_json[1]}", file=sys.stderr)
            return 1

        client_plan = fetched.get("/client-plan.json", {})
        launch = client_plan.get("launch", {})
        if launch.get("primarySurface") != "t3code-native-client":
            print("ERROR: primarySurface is not t3code-native-client", file=sys.stderr)
            return 1
        if launch.get("auxiliarySurface") != "lightweight-web-dashboard":
            print("ERROR: auxiliarySurface is not lightweight-web-dashboard", file=sys.stderr)
            return 1

        shell = fetched.get("/t3-shell.json", {})
        if shell.get("source") != "devframe":
            print("ERROR: t3-shell source is not devframe", file=sys.stderr)
            return 1
        t3_snapshot = shell.get("t3")
        if not isinstance(t3_snapshot, dict):
            print("ERROR: t3-shell missing t3 snapshot", file=sys.stderr)
            return 1
        projects = t3_snapshot.get("projects") or []
        threads = t3_snapshot.get("threads") or []
        if not isinstance(projects, list) or not isinstance(threads, list):
            print("ERROR: t3-shell missing projects or threads array", file=sys.stderr)
            return 1
        team = shell.get("devframe", {}).get("team")
        if not isinstance(team, dict):
            print("ERROR: t3-shell missing devframe.team", file=sys.stderr)
            return 1
        required_team_arrays = [
            "agentRegistry",
            "taskBoard",
            "messageBus",
            "eventLog",
            "evidenceStore",
            "reviewGates",
            "conflictControl",
        ]
        for array_name in required_team_arrays:
            if not isinstance(team.get(array_name), list):
                print(f"ERROR: t3-shell devframe.team missing {array_name}", file=sys.stderr)
                return 1

        bridge_checks = None
        if t3_root is not None:
            resolved_t3_root = Path(t3_root).resolve()
            if not _is_valid_t3_checkout(resolved_t3_root):
                print(f"ERROR: invalid T3 root: {resolved_t3_root}", file=sys.stderr)
                return 1
            bundle = build_t3_bridge_bundle(plan)
            try:
                written_paths = install_t3_bridge_bundle(resolved_t3_root, bundle, force=force)
            except (FileExistsError, ValueError) as exc:
                print(f"ERROR: {exc}", file=sys.stderr)
                return 2
            required_files = [
                "devframe.t3desktop.mjs",
                "devframe.t3web.mjs",
                ".env.devframe.local",
                "apps/web/src/devframe/devframeShellBridge.ts",
            ]
            missing = [f for f in required_files if not (resolved_t3_root / f).exists()]
            if missing:
                print(f"ERROR: missing T3 bridge files: {missing}", file=sys.stderr)
                return 1
            bridge_checks = {
                "written": [str(p) for p in written_paths],
                "requiredFiles": required_files,
                "missing": missing,
                "ok": not missing,
            }

        if output_format == "json":
            payload: dict[str, Any] = {
                "status": "pass",
                "endpoints": required_endpoints,
                "primarySurface": launch.get("primarySurface"),
                "auxiliarySurface": launch.get("auxiliarySurface"),
                "projects": len(projects),
                "threads": len(threads),
                "team": {
                    array_name: len(team.get(array_name, [])) if isinstance(team.get(array_name), list) else 0
                    for array_name in required_team_arrays
                },
            }
            if bridge_checks is not None:
                payload["t3Bridge"] = bridge_checks
            print(json.dumps(payload, indent=2, ensure_ascii=True))
        else:
            lines = [
                "DevFrame Client Smoke",
                f"server       : {base_url}",
                "status       : pass",
                "",
                "Endpoints",
            ]
            for endpoint in required_endpoints:
                status = "ok" if endpoint in fetched else "missing"
                lines.append(f"  {endpoint:<25} {status}")
            lines.extend([
                "",
                "Surfaces",
                f"  primary   : {launch.get('primarySurface')}",
                f"  auxiliary : {launch.get('auxiliarySurface')}",
                "",
                "T3 Shell",
                f"  projects   : {len(projects)}",
                f"  threads    : {len(threads)}",
                "",
                "Team arrays",
            ])
            for array_name in required_team_arrays:
                count = len(team.get(array_name, [])) if isinstance(team.get(array_name), list) else 0
                lines.append(f"  {array_name:<15} {count}")
            if bridge_checks is not None:
                lines.extend([
                    "",
                    "T3 bridge",
                    f"  ok        : {bridge_checks['ok']}",
                    f"  missing   : {bridge_checks['missing']}",
                ])
                for path in bridge_checks.get("written", []):
                    lines.append(f"  wrote     : {path}")
            print("\n".join(lines) + "\n")

        return 0
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
