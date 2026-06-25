"""Slice 1 OpenCode serve probe.

The probe intentionally treats ``prompt_async`` as fire-and-forget. Completion
is established only by independent signals: SSE/message terminal state, actual
file landing on disk, and a hard wall-clock timeout.
"""

from __future__ import annotations

import json
import logging
import os
import socket
import subprocess
import tempfile
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib import error, request

from .opencode_client import _find_opencode
from .opencode_slice0 import MARKER_CONTENT, MARKER_FILE


REPORT_SCHEMA_VERSION = "opencode-readiness-report/v1"
DEFAULT_MODEL = "stepfun/step-3.7-flash"
logger = logging.getLogger(__name__)


def run_opencode_serve_slice1_probe(
    *,
    model: str = DEFAULT_MODEL,
    output_dir: str | None = None,
    timeout: int = 120,
) -> dict[str, Any]:
    artifact_dir = Path(output_dir) if output_dir else Path(tempfile.mkdtemp(prefix="opencode-serve-slice1-"))
    artifact_dir.mkdir(parents=True, exist_ok=True)
    workspace = artifact_dir / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)

    report = _base_report(artifact_dir, workspace, model, timeout)
    binding_validation = _validate_model_binding(model)
    report["model_binding"] = binding_validation
    _set_check(
        report,
        "model_binding_valid",
        binding_validation["valid"],
        binding_validation.get("reason", ""),
    )
    opencode_path = _find_opencode()
    report["opencode_path"] = opencode_path
    if not opencode_path:
        _set_check(report, "opencode_cli", False, "opencode CLI not found")
        return _finalize_report(report, artifact_dir)

    git_init = _run_command(["git", "init"], cwd=workspace, timeout=20)
    report["git_init"] = _safe_command_record(git_init)
    _set_check(report, "git_repo", git_init["exit_code"] == 0, _summarize_command(git_init))
    if git_init["exit_code"] != 0:
        return _finalize_report(report, artifact_dir)

    port = _find_free_port()
    base_url = f"http://127.0.0.1:{port}"
    report["server"].update({"port": port, "base_url": base_url})

    stdout_path = artifact_dir / "serve-stdout.log"
    stderr_path = artifact_dir / "serve-stderr.log"
    proc = _start_server(opencode_path, workspace, port, model, stdout_path, stderr_path)
    report["server"]["pid"] = proc.pid
    health_ok = False
    finalized_before_cleanup = False

    events: list[dict[str, Any]] = []
    sse = _SseConsumer(f"{base_url}/event", events)
    try:
        health = _wait_for_health(base_url, timeout=min(20, timeout))
        report["server"]["health"] = health
        health_ok = bool(health.get("healthy"))
        _set_check(report, "server_health", bool(health.get("healthy")), json.dumps(health))
        if not health.get("healthy"):
            finalized_before_cleanup = True
            return _finalize_report(report, artifact_dir)

        sse.start()
        connected = sse.wait_connected(timeout=min(20, timeout))
        _set_check(
            report,
            "event_stream_connected",
            connected,
            "server.connected received" if connected else "server.connected not received",
        )
        if not connected:
            finalized_before_cleanup = True
            return _finalize_report(report, artifact_dir)

        session = _http_json(base_url, "POST", "/session", {"title": "devframe opencode serve slice1"})
        session_id = _extract_id(session)
        report["session"] = {"id": session_id, "raw": session}
        _set_check(report, "session_created", bool(session_id), session_id or "missing session id")
        if not session_id:
            finalized_before_cleanup = True
            return _finalize_report(report, artifact_dir)

        body = {
            "model": _model_body(model),
            "agent": "build",
            "parts": [{"type": "text", "text": _probe_prompt()}],
        }
        prompt_status = _http_status(base_url, "POST", f"/session/{session_id}/prompt_async", body)
        report["prompt_async"] = {"status": prompt_status}
        _set_check(report, "prompt_async_accepted", prompt_status == 204, f"HTTP {prompt_status}")
        if prompt_status != 204:
            finalized_before_cleanup = True
            return _finalize_report(report, artifact_dir)

        wait_result = _wait_for_completion(
            base_url=base_url,
            session_id=session_id,
            workspace=workspace,
            events=events,
            timeout=timeout,
        )
        wait_checks = wait_result.pop("checks", {})
        report["checks"].update(wait_checks)
        report.update(wait_result)
    finally:
        sse.stop()
        disposed = _dispose_server(base_url) if health_ok else False
        if disposed:
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                _stop_server(proc)
        else:
            _stop_server(proc)
        report["server"]["stdout_log"] = str(stdout_path)
        report["server"]["stderr_log"] = str(stderr_path)
        report["server"]["disposed"] = disposed
        report["server"]["returncode"] = proc.poll()
        stop_ok, stop_detail = _server_stopped_result(disposed, proc.poll(), stderr_path)
        _set_check(
            report,
            "server_stopped",
            stop_ok,
            stop_detail,
        )
        if finalized_before_cleanup:
            _finalize_report(report, artifact_dir)

    return _finalize_report(report, artifact_dir)


def evaluate_serve_report(report: dict[str, Any]) -> dict[str, Any]:
    checks = report.setdefault("checks", {})
    process_ok = (
        checks.get("server_health", {}).get("status") == "passed"
        and checks.get("server_stopped", {}).get("status") == "passed"
    )
    prompt_ok = checks.get("prompt_async_accepted", {}).get("status") == "passed"
    file_ok = checks.get("file_landed", {}).get("status") == "passed"
    event_ok = checks.get("tool_event_seen", {}).get("status") == "passed"
    finish_ok = checks.get("step_finish_stop", {}).get("status") == "passed"
    blockers = report.get("blockers", {})

    failed = [name for name, check in checks.items() if check.get("status") != "passed"]
    partial_type = ""
    if blockers.get("permission_events"):
        partial_type = "needs-manual-permission-reply"
    elif blockers.get("question_events"):
        partial_type = "question-blocked"
    elif checks.get("server_stopped", {}).get("status") == "failed":
        partial_type = "serve-shutdown-nonzero"
    elif file_ok and not (event_ok and finish_ok):
        partial_type = "event-terminal-missing"
    elif prompt_ok and not file_ok:
        partial_type = "serve-no-file-landing"
    elif report.get("timed_out"):
        partial_type = "serve-timeout"
    elif failed:
        partial_type = "serve-probe-failed"

    if process_ok and prompt_ok and file_ok and event_ok and finish_ok and not partial_type:
        report["verdict"] = "passed"
    elif partial_type:
        report["verdict"] = "partial"
    else:
        report["verdict"] = "failed"
    report["partial_type"] = partial_type
    report["failed_checks"] = failed
    return report


def _base_report(artifact_dir: Path, workspace: Path, model: str, timeout: int) -> dict[str, Any]:
    return {
        "schema_version": REPORT_SCHEMA_VERSION,
        "probe": "opencode-serve-slice1",
        "mode": "serve-http-prompt-async",
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "model": model,
        "platform": {"os_name": os.name, "native": True},
        "cache_key": "",
        "artifact_dir": str(artifact_dir),
        "workspace": str(workspace),
        "timeout_seconds": timeout,
        "timed_out": False,
        "checks": {},
        "blockers": {"permission_events": [], "question_events": []},
        "permission_mode": {
            "config": "OPENCODE_CONFIG_CONTENT permission=allow",
            "active_permission_reply": False,
            "run_vs_serve": "serve config-allow under test",
        },
        "server": {"pid": None, "port": None, "base_url": ""},
        "events": {"raw_sample": [], "event_count": 0, "flattened_keys": [], "candidate_fields": {}},
        "paths": {
            "report": str(artifact_dir / "serve-slice1-report.json"),
            "events": str(artifact_dir / "serve-events.jsonl"),
            "stdout": str(artifact_dir / "serve-stdout.log"),
            "stderr": str(artifact_dir / "serve-stderr.log"),
        },
    }


def _start_server(
    opencode_path: str,
    workspace: Path,
    port: int,
    model: str,
    stdout_path: Path,
    stderr_path: Path,
) -> subprocess.Popen:
    env = os.environ.copy()
    env.pop("OPENCODE_SERVER_PASSWORD", None)
    env.pop("OPENCODE_SERVER_USERNAME", None)
    env["OPENCODE_CONFIG_CONTENT"] = json.dumps(
        {"permission": "allow", "model": model},
        ensure_ascii=False,
    )
    stdout = stdout_path.open("w", encoding="utf-8")
    stderr = stderr_path.open("w", encoding="utf-8")
    return subprocess.Popen(
        [
            opencode_path,
            "serve",
            "--hostname",
            "127.0.0.1",
            "--port",
            str(port),
            "--print-logs",
        ],
        cwd=workspace,
        stdout=stdout,
        stderr=stderr,
        env=env,
    )


def _wait_for_health(base_url: str, timeout: int) -> dict[str, Any]:
    deadline = time.time() + timeout
    last_error = ""
    while time.time() < deadline:
        try:
            data = _http_json(base_url, "GET", "/global/health")
            if data.get("healthy"):
                return data
        except Exception as exc:
            last_error = str(exc)
        time.sleep(0.25)
    return {"healthy": False, "error": last_error or "health timeout"}


def _wait_for_completion(
    *,
    base_url: str,
    session_id: str,
    workspace: Path,
    events: list[dict[str, Any]],
    timeout: int,
) -> dict[str, Any]:
    start = time.time()
    deadline = start + timeout
    marker = workspace / MARKER_FILE
    messages: list[dict[str, Any]] = []
    while time.time() < deadline:
        try:
            messages = _http_json(base_url, "GET", f"/session/{session_id}/message")
        except Exception:
            logger.debug("opencode serve message poll failed", exc_info=True)
            messages = []
        if _file_matches(marker) and (_has_step_finish_stop(events) or _has_step_finish_stop(messages)):
            break
        if _has_permission_or_question(events):
            # Keep watching briefly so the report captures all nearby evidence, but
            # do not auto-approve: Slice 1 tests whether config-allow is sufficient.
            time.sleep(1)
            break
        time.sleep(0.5)

    timed_out = time.time() >= deadline
    summary = _summarize_events(events)
    result = {
        "timed_out": timed_out,
        "duration_seconds": round(time.time() - start, 2),
        "events": summary,
        "messages_sample": messages[:3] if isinstance(messages, list) else [],
        "blockers": _extract_blockers(events),
    }
    _set_check(result, "file_landed", _file_matches(marker), f"{MARKER_FILE} content match={_file_matches(marker)}")
    _set_check(result, "tool_event_seen", _has_tool_event(events), "tool_use write/edit event seen")
    _set_check(
        result,
        "step_finish_stop",
        _has_step_finish_stop(events) or _has_step_finish_stop(messages),
        "step_finish reason=stop seen in events or messages",
    )
    return result


def _http_json(base_url: str, method: str, path: str, body: dict[str, Any] | None = None) -> Any:
    req = _request(base_url, method, path, body)
    with request.urlopen(req, timeout=10) as response:
        data = response.read().decode("utf-8", errors="replace")
    return json.loads(data) if data else {}


def _http_status(base_url: str, method: str, path: str, body: dict[str, Any] | None = None) -> int:
    req = _request(base_url, method, path, body)
    try:
        with request.urlopen(req, timeout=10) as response:
            response.read()
            return response.status
    except error.HTTPError as exc:
        return exc.code


def _dispose_server(base_url: str) -> bool:
    try:
        status = _http_status(base_url, "POST", "/instance/dispose", {})
        return 200 <= status < 300
    except Exception:
        logger.debug("opencode serve dispose failed", exc_info=True)
        return False


def _request(base_url: str, method: str, path: str, body: dict[str, Any] | None = None) -> request.Request:
    data = None if body is None else json.dumps(body).encode("utf-8")
    return request.Request(
        f"{base_url}{path}",
        data=data,
        method=method,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
    )


class _SseConsumer:
    def __init__(self, url: str, events: list[dict[str, Any]]):
        self.url = url
        self.events = events
        self._stop = threading.Event()
        self._connected = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def wait_connected(self, timeout: int) -> bool:
        return self._connected.wait(timeout=timeout)

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2)

    def _run(self) -> None:
        try:
            with request.urlopen(self.url, timeout=10) as response:
                current_event = ""
                data_lines: list[str] = []
                while not self._stop.is_set():
                    raw = response.readline()
                    if not raw:
                        break
                    line = raw.decode("utf-8", errors="replace").rstrip("\r\n")
                    if line.startswith("event:"):
                        current_event = line.split(":", 1)[1].strip()
                    elif line.startswith("data:"):
                        data_lines.append(line.split(":", 1)[1].strip())
                    elif line == "":
                        event = _parse_sse_event(current_event, data_lines)
                        if event:
                            self.events.append(event)
                            if event.get("type") == "server.connected":
                                self._connected.set()
                        current_event = ""
                        data_lines = []
        except Exception:
            logger.debug("opencode serve SSE consumer stopped after error", exc_info=True)
            return


def _parse_sse_event(event_name: str, data_lines: list[str]) -> dict[str, Any] | None:
    if not event_name and not data_lines:
        return None
    data = "\n".join(data_lines)
    parsed: Any = {}
    if data:
        try:
            parsed = json.loads(data)
        except json.JSONDecodeError:
            parsed = {"raw": data}
    if isinstance(parsed, dict):
        if event_name and "type" not in parsed:
            parsed["type"] = event_name
        return parsed
    return {"type": event_name or "message", "data": parsed}


def _finalize_report(report: dict[str, Any], artifact_dir: Path) -> dict[str, Any]:
    if report.get("opencode_path"):
        version = _run_command([report["opencode_path"], "--version"], cwd=Path(report["workspace"]), timeout=15)
        report["version"] = _safe_command_record(version)
        version_text = (version.get("stdout", "").strip().splitlines() or ["unknown"])[0]
        report["cache_key"] = f"{version_text}|{os.name}|{report.get('mode', '')}"
    event_path = artifact_dir / "serve-events.jsonl"
    event_path.write_text(
        "\n".join(json.dumps(event, ensure_ascii=False) for event in report.get("events", {}).get("raw_sample", [])),
        encoding="utf-8",
    )
    evaluate_serve_report(report)
    report_path = artifact_dir / "serve-slice1-report.json"
    report["paths"]["report"] = str(report_path)
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    return report


def _summarize_events(events: list[dict[str, Any]]) -> dict[str, Any]:
    flattened: set[str] = set()
    for event in events:
        _collect_keys(event, flattened)
    return {
        "event_count": len(events),
        "raw_sample": events[:20],
        "flattened_keys": sorted(flattened),
        "candidate_fields": {
            "session": _has_key_containing(flattened, "session"),
            "token": _has_key_containing(flattened, "token"),
            "cost": _has_key_containing(flattened, "cost"),
            "tool": _has_key_containing(flattened, "tool"),
            "error": _has_key_containing(flattened, "error"),
            "permission": _has_key_containing(flattened, "permission"),
            "question": _has_key_containing(flattened, "question"),
        },
    }


def _extract_blockers(events: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    permission_events = []
    question_events = []
    for event in events:
        text = json.dumps(event, ensure_ascii=False).lower()
        if "permission" in text:
            permission_events.append(event)
        if "question" in text:
            question_events.append(event)
    return {
        "permission_events": permission_events[:5],
        "question_events": question_events[:5],
    }


def _has_permission_or_question(events: list[dict[str, Any]]) -> bool:
    blockers = _extract_blockers(events)
    return bool(blockers["permission_events"] or blockers["question_events"])


def _has_tool_event(events: list[dict[str, Any]]) -> bool:
    for event in events:
        text = json.dumps(event, ensure_ascii=False).lower()
        if ("tool_use" in text or '"tool"' in text) and ("write" in text or "edit" in text):
            return True
    return False


def _has_step_finish_stop(value: Any) -> bool:
    text = json.dumps(value, ensure_ascii=False).lower()
    return ("step_finish" in text or "step-finish" in text or "step_finish" in text) and '"stop"' in text


def _file_matches(path: Path) -> bool:
    return path.exists() and path.read_text(encoding="utf-8").strip() == MARKER_CONTENT


def _validate_model_binding(model: str) -> dict[str, Any]:
    if "/" not in model:
        return {"valid": False, "reason": "model must use provider/model format"}
    provider, model_id = model.split("/", 1)
    if not provider or not model_id:
        return {"valid": False, "reason": "provider and model ID must be non-empty"}
    return {"valid": True, "provider": provider, "model_id": model_id}


def _model_body(model: str) -> dict[str, str]:
    if "/" not in model:
        return {"providerID": "", "modelID": model}
    provider, model_id = model.split("/", 1)
    return {"providerID": provider, "modelID": model_id}


def _probe_prompt() -> str:
    return (
        f"Create a file named {MARKER_FILE} in the current repository with exactly "
        f"this content and no extra text: {MARKER_CONTENT}"
    )


def _extract_id(value: Any) -> str:
    if isinstance(value, dict):
        return str(value.get("id") or value.get("sessionID") or value.get("sessionId") or "")
    return ""


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _stop_server(proc: subprocess.Popen) -> None:
    if proc.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)], capture_output=True, timeout=10)
    else:
        proc.terminate()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()


def _server_stopped_result(disposed: bool, returncode: int | None, stderr_path: Path) -> tuple[bool, str]:
    error_signals = _server_error_signals(stderr_path)
    clean_nonzero = disposed and returncode == 1 and not error_signals
    ok = disposed and (returncode == 0 or clean_nonzero)
    detail = (
        f"disposed={disposed} returncode={returncode} "
        f"clean_nonzero={clean_nonzero} error_signals={len(error_signals)}"
    )
    if error_signals:
        detail += f" first_error={error_signals[0][:160]}"
    return ok, detail


def _server_error_signals(stderr_path: Path) -> list[str]:
    try:
        text = stderr_path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return [f"unreadable stderr log: {exc}"]
    signals: list[str] = []
    for line in text.splitlines():
        lowered = line.lower()
        if (
            "level=error" in lowered
            or "panic" in lowered
            or "traceback" in lowered
            or "database is locked" in lowered
        ):
            signals.append(line.strip())
    return signals[:5]


def _run_command(command: list[str], *, cwd: Path, timeout: int) -> dict[str, Any]:
    try:
        completed = subprocess.run(
            command,
            cwd=cwd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
        )
        return {"exit_code": completed.returncode, "stdout": completed.stdout, "stderr": completed.stderr}
    except subprocess.TimeoutExpired as exc:
        return {"exit_code": 124, "stdout": exc.stdout or "", "stderr": exc.stderr or "timeout"}


def _safe_command_record(result: dict[str, Any]) -> dict[str, Any]:
    return {
        "exit_code": result.get("exit_code", -1),
        "stdout_preview": str(result.get("stdout", ""))[:500],
        "stderr_preview": str(result.get("stderr", ""))[:500],
    }


def _summarize_command(result: dict[str, Any]) -> str:
    if result.get("exit_code") == 0:
        return (str(result.get("stdout", "")).strip().splitlines() or ["exit 0"])[0][:200]
    return (str(result.get("stderr", "")).strip().splitlines() or [f"exit {result.get('exit_code')}"])[0][:200]


def _set_check(report: dict[str, Any], name: str, passed: bool, detail: str) -> None:
    report.setdefault("checks", {})[name] = {
        "status": "passed" if passed else "failed",
        "detail": detail,
    }


def _collect_keys(value: Any, keys: set[str], prefix: str = "") -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            dotted = f"{prefix}.{key}" if prefix else str(key)
            keys.add(dotted)
            _collect_keys(child, keys, dotted)
    elif isinstance(value, list):
        for child in value:
            _collect_keys(child, keys, prefix)


def _has_key_containing(keys: set[str], needle: str) -> bool:
    lowered = needle.lower()
    return any(lowered in key.lower() for key in keys)
