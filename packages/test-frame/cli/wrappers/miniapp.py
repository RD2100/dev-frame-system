"""MiniApp automation wrapper for WeChat DevTools + miniprogram-automator.

The wrapper is intentionally conservative:
- missing project/config/tool prerequisites are ``blocked``;
- wrapper/tool failures are ``error``;
- real E2E assertion failures are ``failed``.
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import time
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _read_text(path: str) -> str:
    return Path(path).read_text(encoding="utf-8", errors="replace")


def _write_json_artifact(project_config: dict, file_name: str, payload: dict) -> str | None:
    project_name = project_config.get("project", {}).get("name") or "miniapp"
    report_date = datetime.now().strftime("%Y-%m-%d")
    output_dir = PROJECT_ROOT / "reports" / project_name / report_date
    try:
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / file_name
        output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return str(output_path)
    except OSError:
        return None


def _persist_runtime_probe(project_config: dict, probe: dict, artifact_name: str) -> dict:
    setting = project_config.get("miniapp", {}).get("runtime_probe_artifact")
    if not setting:
        return probe

    file_name = artifact_name if setting is True else str(setting)
    artifact_path = _write_json_artifact(project_config, file_name, probe)
    if artifact_path:
        probe = dict(probe)
        probe["artifact_path"] = artifact_path
    else:
        probe = dict(probe)
        probe["artifact_error"] = f"failed to write runtime probe artifact: {file_name}"
    return probe


def _persist_script_results(project_config: dict, artifact_name: str, payload: dict) -> str | None:
    if project_config.get("miniapp", {}).get("results_artifact") is not True:
        return None
    return _write_json_artifact(project_config, artifact_name, payload)


def _artifact_error(project_config: dict, artifact_name: str, artifact_path: str | None) -> str | None:
    if project_config.get("miniapp", {}).get("results_artifact") is not True:
        return None
    if artifact_path:
        return None
    return f"failed to write miniapp results artifact: {artifact_name}"


def _run_command(cmd: list[str], timeout: int | float) -> SimpleNamespace:
    """Run a command while avoiding pipe inheritance hangs on Windows."""
    stdout_file = tempfile.NamedTemporaryFile(delete=False)
    stderr_file = tempfile.NamedTemporaryFile(delete=False)
    stdout_path = stdout_file.name
    stderr_path = stderr_file.name
    stdout_file.close()
    stderr_file.close()

    try:
        with open(stdout_path, "wb") as stdout, open(stderr_path, "wb") as stderr:
            try:
                completed = subprocess.run(
                    cmd,
                    stdin=subprocess.DEVNULL,
                    stdout=stdout,
                    stderr=stderr,
                    timeout=timeout,
                )
                timed_out = False
                returncode = completed.returncode
            except subprocess.TimeoutExpired:
                timed_out = True
                returncode = -9

        return SimpleNamespace(
            returncode=returncode,
            stdout=_read_text(stdout_path),
            stderr=_read_text(stderr_path),
            timed_out=timed_out,
        )
    finally:
        for path in (stdout_path, stderr_path):
            try:
                os.unlink(path)
            except OSError:
                pass


def _is_unset(value) -> bool:
    return not value or (isinstance(value, str) and value.startswith("${") and value.endswith("}"))


def _blocked(reason: str, **extra) -> dict:
    return {
        "status": "blocked",
        "passed": False,
        "tool": "miniapp",
        "results": [],
        "reason": reason,
        "error_type": "CONFIG_ERROR",
        **extra,
    }


def _error(reason: str, **extra) -> dict:
    return {
        "status": "error",
        "passed": False,
        "tool": "miniapp",
        "results": [],
        "reason": reason,
        "error": reason,
        "error_type": "TOOL_PROCESS_ERROR",
        **extra,
    }


def _project_path(project_config: dict) -> str:
    miniapp = project_config.get("miniapp", {})
    project = project_config.get("project", {})
    return (
        miniapp.get("project_path")
        or project.get("project_path")
        or os.environ.get("FITTRACK_PATH")
        or os.environ.get("MINIPROGRAM_PATH")
        or ""
    )


def _devtool_path(project_config: dict) -> str:
    miniapp = project_config.get("miniapp", {})
    return (
        miniapp.get("devtool_path")
        or os.environ.get("WECHAT_DEVTOOLS_CLI")
        or os.environ.get("WECHAT_DEVTOOL_PATH")
        or ""
    )


def _force_clean_devtools(devtool_path: str) -> dict | None:
    devtool_dir = str(Path(devtool_path).parent)
    script = (
        "$dir = "
        + json.dumps(devtool_dir)
        + "; $names = @('wechatdevtools', 'WeChatAppEx', '微信开发者工具', 'wxfilewatcher_x64'); "
        + "for ($i = 0; $i -lt 5; $i++) { "
        + "$procs = @(Get-CimInstance Win32_Process | Where-Object { "
        + "$base = [System.IO.Path]::GetFileNameWithoutExtension($_.Name); "
        + "$cmd = [string]$_.CommandLine; "
        + "$_.ProcessId -ne $PID -and ("
        + "$names -contains $base -or "
        + "($_.ExecutablePath -and $_.ExecutablePath.StartsWith($dir, [System.StringComparison]::OrdinalIgnoreCase)) -or "
        + "($cmd.IndexOf($dir, [System.StringComparison]::OrdinalIgnoreCase) -ge 0) -or "
        + "($cmd -match 'miniprogram-automator|miniapp_runtime_probe|e2e_group\\.js|run_miniapp_e2e\\.js')"
        + ") "
        + "}); "
        + "if ($procs.Count -eq 0) { break }; "
        + "$procs | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }; "
        + "Start-Sleep -Seconds 2 "
        + "}"
    )
    try:
        result = _run_command(
            ["powershell", "-NoProfile", "-Command", script],
            timeout=30,
        )
    except FileNotFoundError:
        return _blocked("PowerShell not found; cannot stop existing WeChat DevTools processes")
    if getattr(result, "timed_out", False):
        return _blocked("Timed out while stopping existing WeChat DevTools processes")

    if result.returncode != 0:
        return _blocked(
            "Failed to stop existing WeChat DevTools processes",
            stdout=result.stdout[-1000:],
            stderr=result.stderr[-1000:],
        )
    time.sleep(3)
    return None


def _run_route_preflight(project_config: dict, project_path: str) -> tuple[dict | None, dict | None]:
    miniapp = project_config.get("miniapp", {})
    required_routes = miniapp.get("required_routes", [])
    script = miniapp.get("route_preflight_script") or str(
        PROJECT_ROOT / "scripts" / "miniapp_route_preflight.js"
    )
    cmd = ["node", script, "--project", project_path]
    if required_routes:
        cmd += ["--required-routes", ",".join(required_routes)]

    try:
        result = _run_command(cmd, timeout=30)
    except FileNotFoundError:
        return None, _blocked("Node.js not found; cannot run miniapp route preflight")
    if getattr(result, "timed_out", False):
        return None, _error("miniapp route preflight timed out")

    try:
        preflight = json.loads(result.stdout.strip())
    except json.JSONDecodeError:
        return None, _error(
            "miniapp route preflight returned invalid JSON",
            stdout=result.stdout[:1000],
            stderr=result.stderr[:1000],
        )

    if preflight.get("status") == "passed" and result.returncode == 0:
        return preflight, None

    status = preflight.get("status")
    reason = preflight.get("reason") or "miniapp route preflight failed"
    if status == "blocked":
        return preflight, _blocked(reason, preflight=preflight)
    return preflight, _error(reason, preflight=preflight)


def _run_runtime_probe(
    project_config: dict,
    preflight: dict,
    port: int,
    artifact_name: str = "miniapp-runtime-probe.json",
) -> tuple[dict | None, dict | None]:
    miniapp = project_config.get("miniapp", {})
    script = miniapp.get("runtime_probe_script") or str(
        PROJECT_ROOT / "scripts" / "miniapp_runtime_probe.js"
    )
    routes = preflight.get("requiredRoutes") or preflight.get("pages") or miniapp.get("required_routes", [])
    cmd = [
        "node",
        script,
        "--port",
        str(port),
        "--host",
        str(miniapp.get("runtime_probe_host", "localhost")),
    ]
    if routes:
        cmd += ["--required-routes", ",".join(routes)]
    if miniapp.get("automator_package"):
        cmd += ["--automator-package", str(miniapp["automator_package"])]
    if miniapp.get("operation_timeout_ms"):
        cmd += ["--operation-timeout-ms", str(miniapp["operation_timeout_ms"])]

    try:
        result = _run_command(
            cmd,
            timeout=miniapp.get("runtime_probe_timeout", 45),
        )
    except FileNotFoundError:
        return None, _blocked("Node.js not found; cannot run miniapp runtime probe")
    if getattr(result, "timed_out", False):
        endpoint = f"ws://{miniapp.get('runtime_probe_host', 'localhost')}:{port}"
        probe = _persist_runtime_probe(
            project_config,
            {
                "schema_version": "test-frame.miniapp-runtime-probe.v1",
                "status": "blocked",
                "error_type": "RESOURCE_UNAVAILABLE",
                "reason": "miniapp runtime probe timed out",
                "endpoint": endpoint,
            },
            artifact_name,
        )
        return probe, _blocked(
            "miniapp runtime probe timed out",
            error_type="RESOURCE_UNAVAILABLE",
            runtime_probe=probe,
        )

    try:
        probe = json.loads(result.stdout.strip())
    except json.JSONDecodeError:
        return None, _error(
            "miniapp runtime probe returned invalid JSON",
            stdout=result.stdout[:1000],
            stderr=result.stderr[:1000],
        )

    probe = _persist_runtime_probe(project_config, probe, artifact_name)

    if probe.get("status") == "passed" and result.returncode == 0:
        return probe, None

    reason = probe.get("reason") or "miniapp runtime probe failed"
    status = probe.get("status")
    if status == "blocked":
        return probe, _blocked(
            reason,
            error_type=probe.get("error_type", "RESOURCE_UNAVAILABLE"),
            runtime_probe=probe,
        )
    return probe, _error(reason, error_type=probe.get("error_type", "RUNTIME_PROBE_ERROR"), runtime_probe=probe)


def _is_runtime_probe_recoverable(probe: dict | None, probe_error: dict | None) -> bool:
    if not probe_error:
        return False
    if probe_error.get("status") != "blocked":
        return False
    error_type = probe_error.get("error_type") or (probe or {}).get("error_type")
    if error_type != "RESOURCE_UNAVAILABLE":
        return False
    reason = str(probe_error.get("reason") or (probe or {}).get("reason") or "")
    return (
        "could not connect" in reason
        or "connection closed" in reason
        or "timed out" in reason
    )


def _run_runtime_probe_with_recovery(
    project_config: dict,
    preflight: dict,
    port: int,
    artifact_name: str,
    devtool_path: str,
    project_path: str,
) -> tuple[dict | None, dict | None]:
    miniapp = project_config.get("miniapp", {})
    attempts_limit = int(miniapp.get("runtime_probe_attempts", 1) or 1)
    retry_interval = float(miniapp.get("runtime_probe_retry_interval", 0) or 0)
    attempts = []
    last_probe = None
    last_error = None

    for attempt in range(1, attempts_limit + 1):
        probe, probe_error = _run_runtime_probe(project_config, preflight, port, artifact_name)
        last_probe = probe
        last_error = probe_error
        attempts.append(
            {
                "attempt": attempt,
                "status": (probe or {}).get("status") or (probe_error or {}).get("status"),
                "error_type": (probe_error or {}).get("error_type") or (probe or {}).get("error_type"),
                "reason": (probe_error or {}).get("reason") or (probe or {}).get("reason"),
            }
        )

        if probe_error is None:
            if probe is not None:
                probe = dict(probe)
                probe["attempts"] = attempts
                probe = _persist_runtime_probe(project_config, probe, artifact_name)
            return probe, None

        if attempt >= attempts_limit or not _is_runtime_probe_recoverable(probe, probe_error):
            break

        automation_error = _open_devtools_with_optional_retry(
            project_config,
            devtool_path,
            project_path,
            port,
            preflight,
        )
        if automation_error:
            automation_error["runtime_probe_attempts"] = attempts
            return last_probe, automation_error
        if retry_interval > 0:
            time.sleep(retry_interval)

    if last_probe is not None:
        last_probe = dict(last_probe)
        last_probe["attempts"] = attempts
        last_probe = _persist_runtime_probe(project_config, last_probe, artifact_name)
    if last_error is not None:
        last_error["runtime_probe"] = last_probe
        last_error["runtime_probe_attempts"] = attempts
    return last_probe, last_error


def _has_jest_specs(test_dir: str) -> bool:
    path = Path(test_dir)
    if not path.is_dir():
        return False
    return any(path.rglob("*.test.js"))


def _parse_miniapp_results(stdout: str) -> list[dict]:
    for line in stdout.splitlines():
        if line.startswith("MINIAPP_RESULTS:"):
            return json.loads(line.replace("MINIAPP_RESULTS:", "", 1))
    return []


def _miniapp_script_entries(miniapp: dict) -> list[dict]:
    entries = miniapp.get("test_scripts")
    if entries:
        normalized = []
        for index, entry in enumerate(entries, start=1):
            if isinstance(entry, str):
                normalized.append({"name": Path(entry).stem, "script": entry, "args": []})
            elif isinstance(entry, dict):
                normalized.append(
                    {
                        "name": entry.get("name") or Path(str(entry.get("script", f"script-{index}"))).stem,
                        "script": entry.get("script"),
                        "args": entry.get("args") or [],
                    }
                )
            else:
                normalized.append({"name": f"script-{index}", "script": None, "args": []})
        return normalized

    test_script = miniapp.get("test_script")
    if test_script:
        return [{"name": Path(str(test_script)).stem, "script": test_script, "args": []}]
    return []


def _annotate_script_results(results: list[dict], entry: dict) -> list[dict]:
    annotated = []
    for item in results:
        copied = dict(item)
        copied.setdefault("script", entry["name"])
        copied.setdefault("group", entry["name"])
        annotated.append(copied)
    return annotated


def _script_command(entry: dict, port: int, miniapp: dict | None = None) -> list[str] | None:
    script = entry.get("script")
    if not script:
        return None
    args = [str(arg) for arg in entry.get("args", [])]
    cmd = ["node", str(script), *args, "--port", str(port)]
    miniapp = miniapp or {}
    automator_package = entry.get("automator_package") or miniapp.get("automator_package")
    if automator_package:
        cmd += ["--automator-package", str(automator_package)]
    operation_timeout_ms = entry.get("operation_timeout_ms") or miniapp.get("operation_timeout_ms")
    if operation_timeout_ms:
        cmd += ["--operation-timeout-ms", str(operation_timeout_ms)]
    return cmd


def _safe_artifact_stem(value: str) -> str:
    return "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in value) or "probe"


def _script_result_payload(entry: dict, result: SimpleNamespace, script_results: list[dict]) -> dict:
    failed = [
        item.get("name", "unknown")
        for item in script_results
        if item.get("status") == "failed"
    ]
    connection_block_reason = _automator_connection_block_reason(script_results)
    status = "blocked" if connection_block_reason else ("failed" if failed or result.returncode != 0 else "passed")
    return {
        "schema_version": "test-frame.miniapp-script-results.v1",
        "name": entry["name"],
        "script": entry.get("script"),
        "returncode": result.returncode,
        "status": status,
        "passed": not failed and result.returncode == 0,
        "error_type": "RESOURCE_UNAVAILABLE" if connection_block_reason else None,
        "reason": connection_block_reason,
        "failed": failed,
        "result_count": len(script_results),
        "results": script_results,
    }


def _script_timeout_payload(entry: dict, timeout_seconds: int | float, result: SimpleNamespace) -> dict:
    name = entry["name"]
    return {
        "schema_version": "test-frame.miniapp-script-results.v1",
        "name": name,
        "script": entry.get("script"),
        "returncode": result.returncode,
        "status": "error",
        "passed": False,
        "failed": [f"{name}:timeout"],
        "result_count": 0,
        "results": [],
        "reason": f"miniapp test script timed out after {timeout_seconds}s: {name}",
    }


def _devtools_port_block_reason(output: str, port: int) -> str | None:
    if "must be restarted on port" in output and "IDE server has started on" in output:
        return (
            "WeChat DevTools is already running on a different automation port; "
            f"quit DevTools before using port {port}"
        )
    return None


def _automator_connection_block_reason(results: list[dict]) -> str | None:
    failed_items = [item for item in results if item.get("status") == "failed"]
    for item in results:
        if item.get("name") != "fatal" or item.get("status") != "failed":
            continue
        error = str(item.get("error", ""))
        if "Failed connecting to ws://" in error or "Connection closed" in error:
            return "miniprogram-automator could not connect to WeChat DevTools automation"
    if failed_items and all("Connection closed" in str(item.get("error", "")) for item in failed_items):
        if any(item.get("status") == "passed" for item in results):
            return "miniprogram-automator connection closed during MiniApp E2E"
        return "miniprogram-automator connection closed before MiniApp E2E could run"
    return None


def _runtime_project_mismatch_block_reason(results: list[dict], expected_routes: list[str]) -> str | None:
    expected = set(expected_routes)
    for item in results:
        name = str(item.get("name", ""))
        if name == "env:project_mismatch":
            return str(item.get("error") or "MiniApp runtime project does not match configured project")
        if name.startswith("env:page=") and expected:
            runtime_page = name.replace("env:page=", "", 1)
            if runtime_page not in expected:
                return f"MiniApp runtime opened unexpected page: {runtime_page}"

    page_not_found = [
        item for item in results
        if item.get("status") == "failed" and " is not found" in str(item.get("error", ""))
    ]
    if page_not_found and len(page_not_found) >= 3:
        return "MiniApp runtime project does not contain configured FitTrack routes"
    return None


def _is_port_drift_error(result: dict | None) -> bool:
    if not result:
        return False
    return "different automation port" in str(result.get("reason", ""))


def _open_devtools_automation(
    project_config: dict,
    devtool_path: str,
    project_path: str,
    port: int,
    preflight: dict | None,
) -> dict | None:
    miniapp = project_config.get("miniapp", {})
    if miniapp.get("skip_devtools_open") is not True:
        open_cmd = [
            devtool_path,
            "open",
            "--project",
            project_path,
            "--port",
            str(port),
        ]
        try:
            opened = _run_command(open_cmd, timeout=90)
        except subprocess.TimeoutExpired:
            return _blocked("WeChat DevTools project open timed out", preflight=preflight)
        except FileNotFoundError:
            return _blocked("WeChat DevTools CLI not found", preflight=preflight)
        if getattr(opened, "timed_out", False):
            return _blocked("WeChat DevTools project open timed out", preflight=preflight)

        open_output = f"{opened.stdout}\n{opened.stderr}"
        open_block_reason = _devtools_port_block_reason(open_output, port)
        if open_block_reason:
            return _blocked(
                open_block_reason,
                preflight=preflight,
                stdout=opened.stdout[-1000:],
                stderr=opened.stderr[-1000:],
            )
        if opened.returncode != 0:
            return _blocked(
                "WeChat DevTools project could not be opened",
                preflight=preflight,
                stdout=opened.stdout[-1000:],
                stderr=opened.stderr[-1000:],
            )

    auto_cmd = [
        devtool_path,
        "auto",
        "--project",
        project_path,
        "--auto-port",
        str(port),
        "--trust-project",
    ]
    try:
        auto = _run_command(auto_cmd, timeout=60)
    except FileNotFoundError:
        return _blocked("WeChat DevTools CLI not found", preflight=preflight)
    if getattr(auto, "timed_out", False):
        return _blocked("WeChat DevTools automation enable timed out", preflight=preflight)

    if auto.returncode != 0:
        return _blocked(
            "WeChat DevTools automation could not be enabled",
            preflight=preflight,
            stdout=auto.stdout[-1000:],
            stderr=auto.stderr[-1000:],
        )

    auto_output = f"{auto.stdout}\n{auto.stderr}"
    auto_block_reason = _devtools_port_block_reason(auto_output, port)
    if auto_block_reason:
        return _blocked(
            auto_block_reason,
            preflight=preflight,
            stdout=auto.stdout[-1000:],
            stderr=auto.stderr[-1000:],
        )

    time.sleep(3)
    return None


def _open_devtools_with_optional_retry(
    project_config: dict,
    devtool_path: str,
    project_path: str,
    port: int,
    preflight: dict | None,
) -> dict | None:
    miniapp = project_config.get("miniapp", {})
    automation_error = _open_devtools_automation(project_config, devtool_path, project_path, port, preflight)
    if not _is_port_drift_error(automation_error) or miniapp.get("force_clean_start") is not True:
        return automation_error

    clean_error = _force_clean_devtools(devtool_path)
    if clean_error:
        return clean_error
    return _open_devtools_automation(project_config, devtool_path, project_path, port, preflight)


def run(project_config: dict) -> dict:
    """Run miniapp route preflight and optional E2E/Jest tests."""
    miniapp = project_config.get("miniapp", {})
    test_dir = miniapp.get("test_dir", "tests/miniapp/specs/")
    port = miniapp.get("devtool_port", 9420)
    project_path = _project_path(project_config)
    devtool_path = _devtool_path(project_config)

    if _is_unset(project_path):
        return _blocked("miniapp project path not configured")

    preflight, preflight_error = _run_route_preflight(project_config, project_path)
    if preflight_error:
        return preflight_error

    if _is_unset(devtool_path) or not os.path.exists(devtool_path):
        return _blocked("WeChat DevTools CLI not found", preflight=preflight)

    if miniapp.get("force_clean_start") is True:
        clean_error = _force_clean_devtools(devtool_path)
        if clean_error:
            return clean_error

    automation_error = _open_devtools_with_optional_retry(
        project_config,
        devtool_path,
        project_path,
        port,
        preflight,
    )
    if automation_error:
        return automation_error

    script_entries = _miniapp_script_entries(miniapp)
    runtime_probe = None
    runtime_probe_enabled = miniapp.get("runtime_probe", True) is not False

    if not script_entries:
        if runtime_probe_enabled:
            runtime_probe, runtime_probe_error = _run_runtime_probe_with_recovery(
                project_config,
                preflight or {},
                port,
                "miniapp-runtime-probe.json",
                devtool_path,
                project_path,
            )
            if runtime_probe_error:
                return runtime_probe_error

        if not _has_jest_specs(test_dir):
            return _blocked(f"miniapp test specs not found: {test_dir}", preflight=preflight)
        cmd = ["npx", "jest", test_dir, "--json"]

        try:
            result = _run_command(cmd, timeout=miniapp.get("test_timeout", 300))
        except FileNotFoundError:
            return _blocked("miniapp test runner not found", preflight=preflight)
        if getattr(result, "timed_out", False):
            return _error("miniapp test timed out after 300s", preflight=preflight)

        try:
            data = json.loads(result.stdout)
        except json.JSONDecodeError:
            return _error("miniapp Jest output is not valid JSON", preflight=preflight)
        wrapper_result = {
            "status": "passed" if result.returncode == 0 else "failed",
            "passed": result.returncode == 0,
            "tool": "miniapp",
            "results": [],
            "failed": [],
            "preflight": preflight,
            "runtime_probe": runtime_probe,
        }
        for tr in data.get("testResults", []):
            name = tr.get("name", "unknown")
            if tr.get("status") == "failed":
                wrapper_result["failed"].append(name)
                wrapper_result["results"].append({"name": name, "status": "failed"})
            else:
                wrapper_result["results"].append({"name": name, "status": "passed"})

        return wrapper_result

    all_results = []
    script_runs = []
    artifact_errors = []

    for index, entry in enumerate(script_entries):
        cmd = _script_command(entry, port, miniapp)
        if cmd is None:
            return _blocked(
                "miniapp test script is not configured",
                preflight=preflight,
                results=all_results,
                script_runs=script_runs,
                artifact_errors=artifact_errors,
            )

        if miniapp.get("reopen_between_scripts") is True and index > 0:
            automation_error = _open_devtools_with_optional_retry(
                project_config,
                devtool_path,
                project_path,
                port,
                preflight,
            )
            if automation_error:
                automation_error["results"] = all_results
                automation_error["script_runs"] = script_runs
                automation_error["artifact_errors"] = artifact_errors
                return automation_error

        if runtime_probe_enabled:
            artifact_name = f"miniapp-runtime-probe-{_safe_artifact_stem(entry['name'])}.json"
            runtime_probe, runtime_probe_error = _run_runtime_probe_with_recovery(
                project_config,
                preflight or {},
                port,
                artifact_name,
                devtool_path,
                project_path,
            )
            if runtime_probe_error:
                runtime_probe_error["results"] = all_results
                runtime_probe_error["script_runs"] = script_runs
                runtime_probe_error["artifact_errors"] = artifact_errors
                return runtime_probe_error

        try:
            result = _run_command(cmd, timeout=miniapp.get("test_timeout", 300))
        except FileNotFoundError:
            return _blocked(
                "miniapp test runner not found",
                preflight=preflight,
                results=all_results,
                script_runs=script_runs,
                artifact_errors=artifact_errors,
            )
        if getattr(result, "timed_out", False):
            timeout_seconds = miniapp.get("test_timeout", 300)
            script_payload = _script_timeout_payload(entry, timeout_seconds, result)
            artifact_name = f"miniapp-results-{_safe_artifact_stem(entry['name'])}.json"
            script_artifact_path = _persist_script_results(project_config, artifact_name, script_payload)
            script_artifact_error = _artifact_error(project_config, artifact_name, script_artifact_path)
            if script_artifact_error:
                artifact_errors.append(script_artifact_error)
            script_runs.append(
                {
                    "name": entry["name"],
                    "script": entry["script"],
                    "returncode": result.returncode,
                    "passed": False,
                    "result_count": 0,
                    "artifact_path": script_artifact_path,
                    "artifact_error": script_artifact_error,
                }
            )
            return _error(
                script_payload["reason"],
                error_type="TOOL_TIMEOUT",
                preflight=preflight,
                results=all_results,
                script_runs=script_runs,
                artifact_errors=artifact_errors,
            )

        try:
            script_results = _annotate_script_results(_parse_miniapp_results(result.stdout), entry)
        except json.JSONDecodeError:
            return _error(
                f"miniapp E2E output is not valid JSON: {entry['name']}",
                preflight=preflight,
                results=all_results,
                script_runs=script_runs,
                artifact_errors=artifact_errors,
            )

        script_payload = _script_result_payload(entry, result, script_results)
        script_artifact_path = _persist_script_results(
            project_config,
            f"miniapp-results-{_safe_artifact_stem(entry['name'])}.json",
            script_payload,
        )
        script_artifact_error = _artifact_error(
            project_config,
            f"miniapp-results-{_safe_artifact_stem(entry['name'])}.json",
            script_artifact_path,
        )
        if script_artifact_error:
            artifact_errors.append(script_artifact_error)
        combined_results = all_results + script_results
        script_runs.append(
            {
                "name": entry["name"],
                "script": entry["script"],
                "returncode": result.returncode,
                "passed": script_payload["passed"],
                "result_count": len(script_results),
                "artifact_path": script_artifact_path,
                "artifact_error": script_artifact_error,
            }
        )

        connection_block_reason = _automator_connection_block_reason(script_results)
        if connection_block_reason:
            return _blocked(
                connection_block_reason,
                error_type="RESOURCE_UNAVAILABLE",
                preflight=preflight,
                runtime_probe=runtime_probe,
                results=combined_results,
                script_runs=script_runs,
                artifact_errors=artifact_errors,
                stdout=result.stdout[-1000:],
                stderr=result.stderr[-1000:],
            )

        project_mismatch_reason = _runtime_project_mismatch_block_reason(
            script_results,
            (preflight or {}).get("pages", []),
        )
        if project_mismatch_reason:
            return _blocked(
                project_mismatch_reason,
                error_type="RUNTIME_PROJECT_MISMATCH",
                preflight=preflight,
                runtime_probe=runtime_probe,
                results=combined_results,
                script_runs=script_runs,
                artifact_errors=artifact_errors,
                stdout=result.stdout[-1000:],
                stderr=result.stderr[-1000:],
            )

        all_results = combined_results

    failed = [
        item.get("name", "unknown")
        for item in all_results
        if item.get("status") == "failed"
    ]
    passed = not failed and all(run["passed"] for run in script_runs)

    return {
        "status": "passed" if passed else "failed",
        "passed": passed,
        "tool": "miniapp",
        "results": all_results,
        "failed": failed,
        "preflight": preflight,
        "runtime_probe": runtime_probe,
        "script_runs": script_runs,
        "artifact_errors": artifact_errors,
    }
