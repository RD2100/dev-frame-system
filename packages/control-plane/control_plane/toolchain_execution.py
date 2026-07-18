"""Explicit, provider-neutral execution of one validated toolchain action."""

from __future__ import annotations

import argparse
import hashlib
import os
import signal
import shutil
import subprocess
import time
from pathlib import Path

from .backup_guard import is_inside
from .toolchain_manifest import validate_toolchain_manifest_bytes


def execute_manifest_action(
    manifest: str | Path,
    action: str,
    project: str | Path,
    *,
    expected_sha256: str,
    report_path: str | Path,
    timeout_seconds: int = 900,
) -> int:
    """Run one tokenized action after revalidating its manifest and project path."""
    manifest_path = Path(manifest).resolve()
    report = Path(report_path).resolve()
    try:
        manifest_bytes = manifest_path.read_bytes()
    except OSError as exc:
        return _write_failure(report, f"cannot hash manifest: {exc}")
    actual_sha256 = hashlib.sha256(manifest_bytes).hexdigest()
    if actual_sha256 != expected_sha256:
        return _write_failure(
            report,
            "manifest changed after the execution request was prepared; "
            f"expected_sha256={expected_sha256}; actual_sha256={actual_sha256}",
        )

    result = validate_toolchain_manifest_bytes(manifest_bytes, manifest_path)
    if result["status"] != "pass":
        return _write_failure(report, "; ".join(result["errors"]))
    commands = result["commands"]
    command = commands.get(action)
    if not command:
        return _write_failure(report, f"manifest has no executable {action} command")

    project_root = Path(project).resolve()
    working_directory = (project_root / result["working_directory"]).resolve()
    if not project_root.is_dir() or not is_inside(working_directory, project_root):
        return _write_failure(report, "working directory is outside the project")
    if not working_directory.is_dir():
        return _write_failure(report, "working directory does not exist")

    executable = shutil.which(command[0])
    if (
        Path(command[0]).suffix.lower() in {".bat", ".cmd"}
        or executable
        and Path(executable).suffix.lower() in {".bat", ".cmd"}
    ):
        return _write_failure(report, "batch-file executables require a separate shell adapter")

    returncode, stdout, stderr, timed_out = _run_command(
        command,
        cwd=working_directory,
        timeout_seconds=timeout_seconds,
    )
    status = "pass" if returncode == 0 else "failed"
    summary = (
        f"manifest action `{action}` timed out after {timeout_seconds} seconds"
        if timed_out
        else f"manifest action `{action}` exited {returncode}"
    )
    report.write_text(
        "## ExecutionReport: toolchain action\n\n"
        f"- **Status**: {status}\n"
        "- **Review Status**: draft\n"
        f"- **Summary**: {summary}.\n"
        "- **Changed Files**:\n"
        "- (unknown)\n"
        f"- **Evidence**: manifest_sha256={actual_sha256}; token-list command; cwd={working_directory}\n"
        "- **Risks**: execution is explicit; acceptance still requires independent review.\n"
        "- **Reviewer Index**:\n"
        "- verify manifest digest, project-relative cwd, command tokens, and canonical RunIndex projection.\n",
        encoding="utf-8",
    )
    if stdout:
        print(stdout, end="")
    if stderr:
        print(stderr, end="")
    return returncode


def _run_command(
    command: list[str],
    *,
    cwd: Path,
    timeout_seconds: int,
) -> tuple[int, str, str, bool]:
    """Run a command in its own process group and stop the whole tree on timeout."""
    creationflags = (
        getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) if os.name == "nt" else 0
    )
    process = subprocess.Popen(
        command,
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        creationflags=creationflags,
        start_new_session=os.name != "nt",
    )
    try:
        stdout, stderr = process.communicate(timeout=timeout_seconds)
        return process.returncode, stdout, stderr, False
    except subprocess.TimeoutExpired as exc:
        _terminate_process_tree(process)
        try:
            stdout, stderr = process.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            stdout, stderr = process.communicate()
        captured_stdout = _captured_text(exc.stdout) + stdout
        captured_stderr = _captured_text(exc.stderr) + stderr
        return 124, captured_stdout, captured_stderr, True


def _terminate_process_tree(process: subprocess.Popen[str]) -> None:
    if os.name == "nt":
        if process.poll() is not None:
            return
        subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
            capture_output=True,
            text=True,
            check=False,
        )
    else:
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            return
        time.sleep(0.2)
        try:
            os.killpg(process.pid, 0)
        except ProcessLookupError:
            return
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            return
    if process.poll() is None:
        process.kill()


def _captured_text(value: str | bytes | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


def _write_failure(report: Path, reason: str) -> int:
    report.write_text(
        "## ExecutionReport: toolchain action\n\n"
        "- **Status**: failed\n"
        "- **Review Status**: draft\n"
        f"- **Summary**: {reason}\n"
        "- **Changed Files**:\n"
        "- (none)\n"
        "- **Evidence**: action was rejected before command execution.\n"
        "- **Risks**: fail-closed validation prevented an unverified action.\n",
        encoding="utf-8",
    )
    return 2


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m control_plane.toolchain_execution")
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--action", choices=("build", "test", "lint"), required=True)
    parser.add_argument("--project", required=True)
    parser.add_argument("--expected-sha256", required=True)
    parser.add_argument("--report-path", required=True)
    parser.add_argument("--timeout", type=int, default=900)
    args = parser.parse_args(argv)
    return execute_manifest_action(
        args.manifest,
        args.action,
        args.project,
        expected_sha256=args.expected_sha256,
        report_path=args.report_path,
        timeout_seconds=args.timeout,
    )


if __name__ == "__main__":
    raise SystemExit(main())
