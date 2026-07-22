"""Slice 0 OpenCode probe.

This module verifies the minimum facts needed before promoting OpenCode to a
routine low-cost worker:

- the CLI is present and can report a version;
- a temporary git repository can be initialized;
- ``opencode run`` can make a real file change in that repository;
- JSONL output is present and has fields we can inspect before writing a parser.
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .opencode_client import (
    _find_opencode,
    _sanitize_external_secret_text,
    _sanitize_external_secret_value,
    opencode_supports_flag,
)


DEFAULT_MODEL = "stepfun/step-3.7-flash"
MARKER_FILE = "slice0-marker.txt"
MARKER_CONTENT = "opencode-slice0-ok"
REPORT_SCHEMA_VERSION = "opencode-readiness-report/v1"


def run_opencode_slice0_probe(
    *,
    model: str = DEFAULT_MODEL,
    output_dir: str | None = None,
    timeout: int = 120,
) -> dict[str, Any]:
    """Run a real OpenCode write probe and persist a reviewable report."""

    opencode_path = _find_opencode()
    artifact_dir = Path(output_dir) if output_dir else Path(tempfile.mkdtemp(prefix="opencode-slice0-"))
    artifact_dir.mkdir(parents=True, exist_ok=True)
    workspace = artifact_dir / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)

    report: dict[str, Any] = {
        "schema_version": REPORT_SCHEMA_VERSION,
        "probe": "opencode-slice0",
        "mode": "run-cli-direct",
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "model": model,
        "artifact_dir": str(artifact_dir),
        "workspace": str(workspace),
        "checks": {},
        "cache_key": "",
        "paths": {
            "report": str(artifact_dir / "slice0-report.json"),
            "stdout": str(artifact_dir / "opencode-stdout.jsonl"),
            "stderr": str(artifact_dir / "opencode-stderr.log"),
        },
    }

    report["opencode_path"] = opencode_path
    if not opencode_path:
        _set_check(report, "opencode_cli", False, "opencode CLI not found")
        return _finalize_report(report, artifact_dir)

    version = _run_command([opencode_path, "--version"], cwd=workspace, timeout=15)
    report["version"] = _safe_command_record(version)
    _set_check(report, "opencode_version", version["exit_code"] == 0, _summarize_command(version))
    if version["exit_code"] != 0:
        return _finalize_report(report, artifact_dir)

    git_init = _run_command(["git", "init"], cwd=workspace, timeout=20)
    report["git_init"] = _safe_command_record(git_init)
    _set_check(report, "git_repo", git_init["exit_code"] == 0, _summarize_command(git_init))
    if git_init["exit_code"] != 0:
        return _finalize_report(report, artifact_dir)

    supports_format = opencode_supports_flag("--format")
    supports_skip_permissions = opencode_supports_flag("--dangerously-skip-permissions")
    report["flag_support"] = {
        "--format": supports_format,
        "--dangerously-skip-permissions": supports_skip_permissions,
    }

    command = [opencode_path, "run", "-m", model]
    if supports_skip_permissions:
        command.append("--dangerously-skip-permissions")
    if supports_format:
        command.extend(["--format", "json"])
    command.append(_build_probe_prompt())

    result = _sanitize_external_secret_value(
        _run_command(command, cwd=workspace, timeout=timeout)
    )
    stdout_path = artifact_dir / "opencode-stdout.jsonl"
    stderr_path = artifact_dir / "opencode-stderr.log"
    stdout_path.write_text(result["stdout"], encoding="utf-8")
    stderr_path.write_text(result["stderr"], encoding="utf-8")

    report["run"] = _safe_command_record(result)
    report["run"]["command"] = _redact_prompt_command(command)
    _set_check(report, "run_exit_zero", result["exit_code"] == 0, _summarize_command(result))
    _set_check(
        report,
        "format_json_supported",
        supports_format,
        "--format found in opencode run help" if supports_format else "--format not found in help",
    )
    _set_check(
        report,
        "skip_permissions_supported",
        supports_skip_permissions,
        (
            "--dangerously-skip-permissions found in opencode run help"
            if supports_skip_permissions
            else "--dangerously-skip-permissions not found in help"
        ),
    )

    marker = workspace / MARKER_FILE
    marker_text = marker.read_text(encoding="utf-8").strip() if marker.exists() else ""
    _set_check(
        report,
        "file_landed",
        marker.exists() and marker_text == MARKER_CONTENT,
        f"{MARKER_FILE} {'matched' if marker_text == MARKER_CONTENT else 'missing or mismatched'}",
    )

    jsonl = parse_jsonl(result["stdout"])
    report["jsonl"] = jsonl
    _set_check(
        report,
        "jsonl_events_present",
        jsonl["event_count"] > 0,
        f"{jsonl['event_count']} events, {jsonl['invalid_line_count']} invalid lines",
    )

    return _finalize_report(report, artifact_dir)


def parse_jsonl(text: str) -> dict[str, Any]:
    """Parse JSONL loosely enough for unstable OpenCode event schemas."""

    text = _sanitize_external_secret_text(text)
    events: list[dict[str, Any]] = []
    invalid_lines: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        try:
            value = json.loads(stripped)
        except json.JSONDecodeError:
            invalid_lines.append(stripped[:200])
            continue
        if isinstance(value, dict):
            events.append(value)
        else:
            invalid_lines.append(stripped[:200])

    flattened_keys: set[str] = set()
    for event in events:
        _collect_keys(event, flattened_keys)

    return {
        "event_count": len(events),
        "invalid_line_count": len(invalid_lines),
        "invalid_lines_sample": invalid_lines[:3],
        "top_level_keys": sorted({key for event in events for key in event.keys()}),
        "flattened_keys": sorted(flattened_keys),
        "candidate_fields": {
            "session": _has_key_containing(flattened_keys, "session"),
            "token": _has_key_containing(flattened_keys, "token"),
            "cost": _has_key_containing(flattened_keys, "cost"),
            "tool": _has_key_containing(flattened_keys, "tool"),
            "error": _has_key_containing(flattened_keys, "error"),
        },
    }


def _run_command(command: list[str], *, cwd: Path, timeout: int) -> dict[str, Any]:
    start = time.time()
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
        return _sanitize_external_secret_value({
            "exit_code": completed.returncode,
            "stdout": completed.stdout,
            "stderr": completed.stderr,
            "timed_out": False,
            "duration_seconds": round(time.time() - start, 2),
        })
    except subprocess.TimeoutExpired as exc:
        return _sanitize_external_secret_value({
            "exit_code": 124,
            "stdout": _as_text(exc.stdout),
            "stderr": _as_text(exc.stderr) or f"TIMEOUT after {timeout}s",
            "timed_out": True,
            "duration_seconds": round(time.time() - start, 2),
        })
    except FileNotFoundError as exc:
        return _sanitize_external_secret_value({
            "exit_code": 127,
            "stdout": "",
            "stderr": _sanitize_external_secret_text(exc),
            "timed_out": False,
            "duration_seconds": round(time.time() - start, 2),
        })
    except Exception as exc:
        return _sanitize_external_secret_value({
            "exit_code": 1,
            "stdout": "",
            "stderr": f"opencode command failed: {exc}",
            "timed_out": False,
            "duration_seconds": round(time.time() - start, 2),
        })


def _build_probe_prompt() -> str:
    return (
        f"Create a file named {MARKER_FILE} in the current repository with exactly "
        f"this content and no extra text: {MARKER_CONTENT}"
    )


def _set_check(report: dict[str, Any], name: str, passed: bool, detail: str) -> None:
    report["checks"][name] = {
        "status": "passed" if passed else "failed",
        "detail": detail,
    }


def _finalize_report(report: dict[str, Any], artifact_dir: Path) -> dict[str, Any]:
    checks = report.get("checks", {})
    failed = [name for name, check in checks.items() if check.get("status") != "passed"]
    report["verdict"] = "passed" if not failed and checks else "failed"
    report["failed_checks"] = failed

    if report.get("opencode_path"):
        version = _run_command([report["opencode_path"], "--version"], cwd=Path(report["workspace"]), timeout=15)
        version_text = (version.get("stdout", "").strip().splitlines() or ["unknown"])[0]
        report["cache_key"] = f"{version_text}|{os.name}|{report.get('mode', '')}"

    report = _sanitize_external_secret_value(report)
    report_path = artifact_dir / "slice0-report.json"
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    report["paths"]["report"] = str(report_path)
    return report


def _safe_command_record(result: dict[str, Any]) -> dict[str, Any]:
    result = _sanitize_external_secret_value(result)
    return {
        "exit_code": result["exit_code"],
        "timed_out": result["timed_out"],
        "duration_seconds": result["duration_seconds"],
        "stdout_preview": result["stdout"][:500],
        "stderr_preview": result["stderr"][:500],
    }


def _summarize_command(result: dict[str, Any]) -> str:
    result = _sanitize_external_secret_value(result)
    if result["timed_out"]:
        return f"timed out after {result['duration_seconds']}s"
    if result["exit_code"] == 0:
        first_line = (result["stdout"].strip().splitlines() or ["exit 0"])[0]
        return first_line[:200]
    stderr = result["stderr"].strip().splitlines()
    return (stderr[0] if stderr else f"exit {result['exit_code']}")[:200]


def _redact_prompt_command(command: list[str]) -> list[str]:
    if not command:
        return []
    return command[:-1] + ["<probe-prompt>"]


def _as_text(value: str | bytes | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return _sanitize_external_secret_text(value)
    return _sanitize_external_secret_text(value)


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
