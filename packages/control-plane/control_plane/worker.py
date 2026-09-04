"""Local dry-run worker for rdgoal dispatch packets.

This worker proves the packet -> ExecutionReport -> ingest loop without
modifying the target project. Real workers can later replace this adapter.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from .dispatch_packet import DispatchPacket, DispatchPacketStore, ExecutionReportSummary
from .local_process_containment import WindowsJob
from .toolchain_execution import _terminate_process_tree


_COMMAND_CLEANUP_TIMEOUT_SECONDS = 5.0
_MAX_WINDOWS_DESCENDANTS = 256
_MAX_WINDOWS_SNAPSHOT_ENTRIES = 4096


@dataclass
class WorkerResult:
    packet: DispatchPacket
    report_path: str
    summary: ExecutionReportSummary


class LocalDryRunWorker:
    def __init__(self, runtime_dir: str | Path | None = None,
                 repo_root: str | Path | None = None) -> None:
        self.store = DispatchPacketStore(runtime_dir=runtime_dir, repo_root=repo_root)

    def run_packet(self, packet_dir: str | Path) -> WorkerResult:
        packet = self.store.load_packet(packet_dir)
        report_path = Path(packet.packet_dir) / "ExecutionReport.md"
        report_path.write_text(self._render_report(packet), encoding="utf-8")
        summary = self.store.ingest_report(packet.packet_dir, report_path)
        return WorkerResult(packet=packet, report_path=str(report_path), summary=summary)

    def _render_report(self, packet: DispatchPacket) -> str:
        status = "pass" if packet.dispatch_ready else "blocked"
        changed_files = "\n".join(f"- `{target}`" for target in packet.targets) or "- (none)"
        blocked_reason = (
            ""
            if packet.dispatch_ready
            else "\n- **Blocked Reason**: Packet is not dispatch-ready; worker performed no project changes."
        )
        return (
            f"## ExecutionReport: {packet.packet_id}\n\n"
            f"- **Status**: {status}{blocked_reason}\n"
            "- **Review Status**: draft\n"
            "- **Summary**: Local dry-run worker consumed the rdgoal dispatch packet. "
            "No target project files were modified.\n"
            "- **Changed Files**:\n"
            f"{changed_files}\n"
            "- **Evidence**: dry-run worker loaded packet.json and wrote this ExecutionReport.\n"
            "- **Risks**: Real implementation still requires a live project-local worker.\n"
            "- **Reviewer Index**:\n"
            f"- `{packet.packet_dir}` -> verify packet.json and TASKSPEC.md before live dispatch.\n"
        )


class CommandWorker:
    """Run an explicit worker command against a dispatch packet."""

    def __init__(self, runtime_dir: str | Path | None = None,
                 repo_root: str | Path | None = None,
                 timeout_seconds: int = 900) -> None:
        self.store = DispatchPacketStore(runtime_dir=runtime_dir, repo_root=repo_root)
        self.timeout_seconds = timeout_seconds

    def run_packet(self, packet_dir: str | Path, command: list[str], *,
                   cwd: str | Path | None = None,
                   env_overrides: dict[str, str] | None = None) -> WorkerResult:
        if not command:
            raise ValueError("CommandWorker requires a non-empty command list.")

        packet = self.store.load_packet(packet_dir)
        report_path = Path(packet.packet_dir) / "ExecutionReport.md"
        if not packet.dispatch_ready:
            report_path.write_text(self._blocked_report(packet), encoding="utf-8")
            summary = self.store.ingest_report(packet.packet_dir, report_path)
            return WorkerResult(packet=packet, report_path=str(report_path), summary=summary)

        output_path = Path(packet.packet_dir) / "worker-output.txt"
        env = os.environ.copy()
        env.update({
            "RDGOAL_PACKET_DIR": packet.packet_dir,
            "RDGOAL_PACKET_JSON": str(Path(packet.packet_dir) / "packet.json"),
            "RDGOAL_TASKSPEC_JSON": str(Path(packet.packet_dir) / "TASKSPEC.json"),
            "RDGOAL_TASKSPEC_MD": str(Path(packet.packet_dir) / "TASKSPEC.md"),
            "RDGOAL_REPORT_PATH": str(report_path),
        })
        # Optional, backward-compatible overrides. When unset, behavior is
        # byte-identical: cwd stays the packet project root and the environment
        # is the inherited environment plus the RDGOAL_* keys above.
        if env_overrides:
            env.update({str(key): str(value) for key, value in env_overrides.items()})
        effective_cwd = str(cwd) if cwd is not None else packet.project_root
        resolved_command = _resolve_command(command)
        cancel_marker = Path(env["DEVFRAME_CANCEL_MARKER"]) if env.get("DEVFRAME_CANCEL_MARKER") else None
        if cancel_marker is not None and cancel_marker.is_file():
            output_path.write_text(
                "STDOUT\n\nSTDERR\n\nCANCELLED before worker start\n",
                encoding="utf-8",
            )
            report_path.write_text(self._cancelled_report(packet), encoding="utf-8")
            summary = self.store.ingest_report(packet.packet_dir, report_path)
            return WorkerResult(packet=packet, report_path=str(report_path), summary=summary)

        job: WindowsJob | None = None
        process: subprocess.Popen[str] | None = None
        job_closed = False
        job_cleanup_ok = True
        job_assigned = False
        process_started = False

        def close_job() -> bool:
            nonlocal job_closed, job_cleanup_ok
            if job is None or job_closed:
                return job_cleanup_ok
            try:
                job_cleanup_ok = job.close()
            except Exception:
                job_cleanup_ok = False
            job_closed = True
            return job_cleanup_ok

        def stop_process_tree() -> bool:
            nonlocal job_cleanup_ok
            cleanup_deadline = time.monotonic() + _COMMAND_CLEANUP_TIMEOUT_SECONDS
            job_closed_cleanly = close_job()
            if job is not None and job_closed_cleanly and (process is None or job_assigned):
                return True
            if process is None:
                return job_cleanup_ok
            fallback_ok = False
            try:
                fallback_ok = _terminate_command_process_tree(
                    process,
                    timeout_seconds=max(0.0, cleanup_deadline - time.monotonic()),
                )
            except Exception:
                fallback_ok = False
            try:
                root_still_running = process.poll() is None
            except Exception:
                root_still_running = True
                fallback_ok = False
            if root_still_running:
                try:
                    process.kill()
                except Exception:
                    fallback_ok = False
            remaining = max(0.0, cleanup_deadline - time.monotonic())
            try:
                process.wait(timeout=remaining)
            except (Exception, subprocess.TimeoutExpired):
                fallback_ok = False
            job_cleanup_ok = job_cleanup_ok and fallback_ok
            return job_cleanup_ok

        stdout = ""
        stderr = ""
        output_collected = False
        cancelled = False
        timed_out = False
        primary_error: Exception | None = None
        try:
            try:
                creationflags = (
                    getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
                    if os.name == "nt"
                    else 0
                )
                job = WindowsJob() if os.name == "nt" else None
                if job is not None:
                    creationflags |= job.suspended_creation_flag()
                process = subprocess.Popen(
                    resolved_command,
                    cwd=effective_cwd,
                    env=env,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    creationflags=creationflags,
                    start_new_session=os.name != "nt",
                )
                if job is not None:
                    job.assign(process)
                    job_assigned = True
                    job.resume(process)
                process_started = True
            except Exception as exc:
                primary_error = exc

            if primary_error is None:
                deadline = time.monotonic() + max(0, self.timeout_seconds)
                while True:
                    if cancel_marker is not None and cancel_marker.is_file():
                        cancelled = True
                        break
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        timed_out = True
                        break
                    try:
                        stdout, stderr = process.communicate(timeout=min(0.1, remaining))
                        output_collected = True
                        break
                    except subprocess.TimeoutExpired:
                        continue

                if (
                    not cancelled
                    and cancel_marker is not None
                    and cancel_marker.is_file()
                ):
                    cancelled = True
        except Exception as exc:
            primary_error = exc
        finally:
            stop_process_tree()

        if process is not None and not output_collected:
            drain_deadline = time.monotonic() + _COMMAND_CLEANUP_TIMEOUT_SECONDS
            try:
                stdout, stderr = process.communicate(
                    timeout=max(0.0, drain_deadline - time.monotonic())
                )
                output_collected = True
            except subprocess.TimeoutExpired as exc:
                stdout = _captured_output(exc.stdout)
                stderr = _captured_output(exc.stderr)
                try:
                    process.kill()
                except Exception:
                    job_cleanup_ok = False
                remaining = max(0.0, drain_deadline - time.monotonic())
                if remaining > 0:
                    try:
                        tail_stdout, tail_stderr = process.communicate(timeout=remaining)
                        stdout += tail_stdout
                        stderr += tail_stderr
                        output_collected = True
                    except Exception:
                        job_cleanup_ok = False
                else:
                    job_cleanup_ok = False
            except Exception as exc:
                if primary_error is None:
                    primary_error = exc
                job_cleanup_ok = False
            if not output_collected:
                _close_process_pipes(process)

        if primary_error is not None:
            failure_reason = f"worker command could not start: {type(primary_error).__name__}"
            failure_label = "FAILED TO START"
            if process_started:
                failure_reason = f"worker command failed during execution: {type(primary_error).__name__}"
                failure_label = "FAILED DURING EXECUTION"
            if not job_cleanup_ok:
                failure_reason += "; process containment cleanup failed"
            output_path.write_text(
                "STDOUT\n\n"
                "STDERR\n"
                f"{failure_label}: {type(primary_error).__name__}\n"
                f"COMMAND: {command[0]} ({max(0, len(command) - 1)} args)\n",
                encoding="utf-8",
            )
            worker_report = _read_worker_report(report_path)
            failure_report = self._failed_report(packet, failure_reason)
            if worker_report:
                failure_report += "\n## Worker-provided partial report\n\n" + worker_report
            report_path.write_text(failure_report, encoding="utf-8")
            summary = self.store.ingest_report(packet.packet_dir, report_path)
            return WorkerResult(packet=packet, report_path=str(report_path), summary=summary)
        output_suffix = ""
        if cancelled:
            output_suffix = f"\n\nCANCELLED worker_pid={process.pid}\n"
        elif timed_out:
            output_suffix = f"\n\nTIMEOUT after {self.timeout_seconds} seconds worker_pid={process.pid}\n"
        output_path.write_text(
            "STDOUT\n"
            f"{stdout}\n\n"
            "STDERR\n"
            f"{stderr}"
            f"{output_suffix}",
            encoding="utf-8",
        )

        if not job_cleanup_ok:
            worker_report = _read_worker_report(report_path)
            cleanup_reason = "worker process containment cleanup failed"
            if cancelled:
                cleanup_reason = "worker cancellation requested; process containment cleanup failed"
            elif timed_out:
                cleanup_reason = "worker command timed out; process containment cleanup failed"
            elif process.returncode not in (None, 0):
                cleanup_reason = (
                    f"worker command exited {process.returncode}; "
                    "process containment cleanup failed"
                )
            failure_report = self._failed_report(packet, cleanup_reason)
            if worker_report:
                failure_report += "\n## Worker-provided partial report\n\n" + worker_report
            report_path.write_text(failure_report, encoding="utf-8")
            summary = self.store.ingest_report(packet.packet_dir, report_path)
            return WorkerResult(packet=packet, report_path=str(report_path), summary=summary)

        if cancelled:
            worker_report = _read_worker_report(report_path)
            cancellation_report = self._cancelled_report(packet)
            if worker_report:
                cancellation_report += "\n## Worker-provided partial report\n\n" + worker_report
            report_path.write_text(cancellation_report, encoding="utf-8")
            summary = self.store.ingest_report(packet.packet_dir, report_path)
            return WorkerResult(packet=packet, report_path=str(report_path), summary=summary)
        if timed_out:
            worker_report = _read_worker_report(report_path)
            failure_report = self._failed_report(packet, "worker command timed out")
            if worker_report:
                failure_report += "\n## Worker-provided partial report\n\n" + worker_report
            report_path.write_text(failure_report, encoding="utf-8")
            summary = self.store.ingest_report(packet.packet_dir, report_path)
            return WorkerResult(packet=packet, report_path=str(report_path), summary=summary)

        if process.returncode != 0:
            worker_report = _read_worker_report(report_path)
            failure_report = self._failed_report(
                packet, f"worker command exited {process.returncode}"
            )
            if worker_report:
                failure_report += "\n## Worker-provided report\n\n" + worker_report
            report_path.write_text(failure_report, encoding="utf-8")
        elif not report_path.exists():
            report_path.write_text(
                self._failed_report(packet, "worker command did not produce ExecutionReport.md"),
                encoding="utf-8",
            )

        summary = self.store.ingest_report(packet.packet_dir, report_path)
        return WorkerResult(packet=packet, report_path=str(report_path), summary=summary)

    def _blocked_report(self, packet: DispatchPacket) -> str:
        return (
            f"## ExecutionReport: {packet.packet_id}\n\n"
            "- **Status**: blocked\n"
            "- **Review Status**: draft\n"
            "- **Summary**: Command worker did not run because the packet is not dispatch-ready.\n"
            "- **Changed Files**:\n"
            "- (none)\n"
            "- **Evidence**: packet dispatch_ready was false.\n"
            "- **Risks**: Live worker command was intentionally skipped.\n"
        )

    def _failed_report(self, packet: DispatchPacket, reason: str) -> str:
        return (
            f"## ExecutionReport: {packet.packet_id}\n\n"
            "- **Status**: failed\n"
            "- **Review Status**: draft\n"
            f"- **Summary**: Command worker failed: {reason}.\n"
            "- **Changed Files**:\n"
            "- (unknown)\n"
            "- **Evidence**: see worker-output.txt in the packet directory.\n"
            "- **Risks**: Runner failure must not be reported as pass.\n"
        )

    def _cancelled_report(self, packet: DispatchPacket) -> str:
        return (
            f"## ExecutionReport: {packet.packet_id}\n\n"
            "- **Status**: cancelled\n"
            "- **Review Status**: draft\n"
            "- **Summary**: Command worker stopped after a durable cancellation request.\n"
            "- **Changed Files**:\n"
            "- (unknown)\n"
            "- **Evidence**: see worker-output.txt in the packet directory.\n"
            "- **Risks**: Cancellation is not rollback; partial project changes may exist.\n"
        )


def _resolve_command(command: list[str]) -> list[str]:
    executable = command[0]
    resolved = shutil.which(executable)
    if not resolved:
        return command
    return [resolved, *command[1:]]


def _read_worker_report(report_path: Path) -> str:
    if not report_path.is_file():
        return ""
    try:
        return report_path.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return ""


def _captured_output(value: str | bytes | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


def _close_process_pipes(process: subprocess.Popen[str]) -> None:
    for name in ("stdout", "stderr"):
        try:
            stream = getattr(process, name)
        except Exception:
            continue
        if stream is None:
            continue
        try:
            stream.close()
        except Exception:
            continue


def _terminate_command_process_tree(
    process: subprocess.Popen[str],
    *,
    timeout_seconds: float = _COMMAND_CLEANUP_TIMEOUT_SECONDS,
) -> bool:
    deadline = time.monotonic() + max(0.0, timeout_seconds)
    if os.name != "nt":
        cleanup_ok = True
        try:
            _terminate_process_tree(process)
        except Exception:
            cleanup_ok = False
        return _wait_for_process_exit(process, deadline) and cleanup_ok
    cleanup_ok = True
    try:
        descendant_pids, descendants_complete = _windows_descendant_process_ids(
            process.pid,
            deadline=deadline,
            limit=_MAX_WINDOWS_DESCENDANTS,
        )
        cleanup_ok = cleanup_ok and descendants_complete
    except Exception:
        descendant_pids = []
        cleanup_ok = False
    for pid in (process.pid, *reversed(descendant_pids)):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            cleanup_ok = False
            break
        try:
            subprocess.run(
                ["taskkill", "/PID", str(pid), "/T", "/F"],
                capture_output=True,
                text=True,
                check=False,
                timeout=remaining,
            )
        except (OSError, subprocess.TimeoutExpired):
            cleanup_ok = False
            continue
    return _wait_for_process_exit(process, deadline) and cleanup_ok


def _wait_for_process_exit(
    process: subprocess.Popen[str],
    deadline: float,
) -> bool:
    try:
        root_still_running = process.poll() is None
    except Exception:
        root_still_running = True
    if root_still_running:
        try:
            process.kill()
        except Exception:
            return False
    remaining = max(0.0, deadline - time.monotonic())
    try:
        process.wait(timeout=remaining)
    except (Exception, subprocess.TimeoutExpired):
        return False
    try:
        return process.poll() is not None
    except Exception:
        return False


def _windows_descendant_process_ids(
    root_pid: int,
    *,
    deadline: float,
    limit: int,
) -> tuple[list[int], bool]:
    import ctypes
    from ctypes import wintypes

    snapshot_flag = 0x00000002
    invalid_handle_value = ctypes.c_void_p(-1).value

    class ProcessEntry32(ctypes.Structure):
        _fields_ = [
            ("dwSize", wintypes.DWORD),
            ("cntUsage", wintypes.DWORD),
            ("th32ProcessID", wintypes.DWORD),
            ("th32DefaultHeapID", ctypes.c_size_t),
            ("th32ModuleID", wintypes.DWORD),
            ("cntThreads", wintypes.DWORD),
            ("th32ParentProcessID", wintypes.DWORD),
            ("pcPriClassBase", wintypes.LONG),
            ("dwFlags", wintypes.DWORD),
            ("szExeFile", wintypes.WCHAR * 260),
        ]

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
    kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    kernel32.Process32FirstW.argtypes = [
        wintypes.HANDLE,
        ctypes.POINTER(ProcessEntry32),
    ]
    kernel32.Process32FirstW.restype = wintypes.BOOL
    kernel32.Process32NextW.argtypes = [
        wintypes.HANDLE,
        ctypes.POINTER(ProcessEntry32),
    ]
    kernel32.Process32NextW.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL

    snapshot = kernel32.CreateToolhelp32Snapshot(snapshot_flag, 0)
    if not snapshot or snapshot == invalid_handle_value:
        return [], False

    children_by_parent: dict[int, list[int]] = {}
    entry = ProcessEntry32()
    entry.dwSize = ctypes.sizeof(ProcessEntry32)
    snapshot_complete = True
    entries_seen = 0
    try:
        has_entry = bool(kernel32.Process32FirstW(snapshot, ctypes.byref(entry)))
        if not has_entry:
            snapshot_complete = False
        while has_entry:
            if (
                time.monotonic() >= deadline
                or entries_seen >= _MAX_WINDOWS_SNAPSHOT_ENTRIES
            ):
                snapshot_complete = False
                break
            entries_seen += 1
            pid = int(entry.th32ProcessID)
            parent_pid = int(entry.th32ParentProcessID)
            if pid != root_pid:
                children_by_parent.setdefault(parent_pid, []).append(pid)
            has_entry = bool(kernel32.Process32NextW(snapshot, ctypes.byref(entry)))
    finally:
        kernel32.CloseHandle(snapshot)

    descendants, descendants_complete = _bounded_descendant_ids(
        children_by_parent,
        root_pid,
        deadline=deadline,
        limit=limit,
    )
    return descendants, snapshot_complete and descendants_complete


def _bounded_descendant_ids(
    children_by_parent: dict[int, list[int]],
    root_pid: int,
    *,
    deadline: float,
    limit: int,
) -> tuple[list[int], bool]:
    descendants: list[int] = []
    pending = list(children_by_parent.get(root_pid, []))
    seen: set[int] = set()
    while pending:
        if time.monotonic() >= deadline or len(descendants) >= max(0, limit):
            return descendants, False
        pid = pending.pop()
        if pid in seen:
            return descendants, False
        seen.add(pid)
        descendants.append(pid)
        pending.extend(children_by_parent.get(pid, []))
    return descendants, True


class AihubGoWorker(CommandWorker):
    """Adapter for ai_workflow_hub's `go` TaskSpec entry point."""

    def run_packet(self, packet_dir: str | Path, *, apply_changes: bool = False,
                   python_executable: str | None = None,
                   module_name: str = "ai_workflow_hub.cli") -> WorkerResult:
        packet = self.store.load_packet(packet_dir)
        command = [
            python_executable or sys.executable,
            "-m",
            module_name,
            "go",
            str(Path(packet.packet_dir) / "TASKSPEC.json"),
            "--project",
            packet.project_id,
        ]
        command.append("--apply" if apply_changes else "--dry-run")
        return super().run_packet(packet_dir, command)
