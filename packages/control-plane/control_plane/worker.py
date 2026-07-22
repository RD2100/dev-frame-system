"""Local dry-run worker for rdgoal dispatch packets.

This worker proves the packet -> ExecutionReport -> ingest loop without
modifying the target project. Real workers can later replace this adapter.
"""
from __future__ import annotations

import ctypes
import json
import os
import signal
import shutil
import subprocess
import sys
import time
import uuid
from ctypes import wintypes
from dataclasses import dataclass
from pathlib import Path

from .dispatch_packet import DispatchPacket, DispatchPacketStore, ExecutionReportSummary


@dataclass
class WorkerResult:
    packet: DispatchPacket
    report_path: str
    summary: ExecutionReportSummary


class _JobObjectBasicAccountingInformation(ctypes.Structure):
    _fields_ = [
        ("TotalUserTime", ctypes.c_longlong),
        ("TotalKernelTime", ctypes.c_longlong),
        ("ThisPeriodTotalUserTime", ctypes.c_longlong),
        ("ThisPeriodTotalKernelTime", ctypes.c_longlong),
        ("TotalPageFaultCount", wintypes.DWORD),
        ("TotalProcesses", wintypes.DWORD),
        ("ActiveProcesses", wintypes.DWORD),
        ("TotalTerminatedProcesses", wintypes.DWORD),
    ]


class _IoCounters(ctypes.Structure):
    _fields_ = [
        ("ReadOperationCount", ctypes.c_ulonglong),
        ("WriteOperationCount", ctypes.c_ulonglong),
        ("OtherOperationCount", ctypes.c_ulonglong),
        ("ReadTransferCount", ctypes.c_ulonglong),
        ("WriteTransferCount", ctypes.c_ulonglong),
        ("OtherTransferCount", ctypes.c_ulonglong),
    ]


class _JobObjectBasicLimitInformation(ctypes.Structure):
    _fields_ = [
        ("PerProcessUserTimeLimit", ctypes.c_longlong),
        ("PerJobUserTimeLimit", ctypes.c_longlong),
        ("LimitFlags", wintypes.DWORD),
        ("MinimumWorkingSetSize", ctypes.c_size_t),
        ("MaximumWorkingSetSize", ctypes.c_size_t),
        ("ActiveProcessLimit", wintypes.DWORD),
        ("Affinity", ctypes.c_size_t),
        ("PriorityClass", wintypes.DWORD),
        ("SchedulingClass", wintypes.DWORD),
    ]


class _JobObjectExtendedLimitInformation(ctypes.Structure):
    _fields_ = [
        ("BasicLimitInformation", _JobObjectBasicLimitInformation),
        ("IoInfo", _IoCounters),
        ("ProcessMemoryLimit", ctypes.c_size_t),
        ("JobMemoryLimit", ctypes.c_size_t),
        ("PeakProcessMemoryUsed", ctypes.c_size_t),
        ("PeakJobMemoryUsed", ctypes.c_size_t),
    ]


def _windows_kernel32():
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
    kernel32.CreateJobObjectW.restype = wintypes.HANDLE
    kernel32.SetInformationJobObject.argtypes = [
        wintypes.HANDLE,
        ctypes.c_int,
        ctypes.c_void_p,
        wintypes.DWORD,
    ]
    kernel32.SetInformationJobObject.restype = wintypes.BOOL
    kernel32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    kernel32.AssignProcessToJobObject.restype = wintypes.BOOL
    kernel32.QueryInformationJobObject.argtypes = [
        wintypes.HANDLE,
        ctypes.c_int,
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.c_void_p,
    ]
    kernel32.QueryInformationJobObject.restype = wintypes.BOOL
    kernel32.TerminateJobObject.argtypes = [wintypes.HANDLE, wintypes.UINT]
    kernel32.TerminateJobObject.restype = wintypes.BOOL
    kernel32.CreateEventW.argtypes = [
        ctypes.c_void_p,
        wintypes.BOOL,
        wintypes.BOOL,
        wintypes.LPCWSTR,
    ]
    kernel32.CreateEventW.restype = wintypes.HANDLE
    kernel32.SetEvent.argtypes = [wintypes.HANDLE]
    kernel32.SetEvent.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL
    return kernel32


class _WindowsJob:
    _BASIC_ACCOUNTING_INFORMATION = 1
    _EXTENDED_LIMIT_INFORMATION = 9
    _KILL_ON_JOB_CLOSE = 0x00002000

    def __init__(self) -> None:
        self._kernel32 = _windows_kernel32()
        handle = self._kernel32.CreateJobObjectW(None, None)
        if not handle:
            raise ctypes.WinError(ctypes.get_last_error())
        self._handle: int | None = int(handle)
        limits = _JobObjectExtendedLimitInformation()
        limits.BasicLimitInformation.LimitFlags = self._KILL_ON_JOB_CLOSE
        if not self._kernel32.SetInformationJobObject(
            self._handle,
            self._EXTENDED_LIMIT_INFORMATION,
            ctypes.byref(limits),
            ctypes.sizeof(limits),
        ):
            error = ctypes.WinError(ctypes.get_last_error())
            self.close()
            raise error

    def assign(self, process: subprocess.Popen[str]) -> None:
        if not self._kernel32.AssignProcessToJobObject(
            self._handle, int(process._handle)
        ):
            raise ctypes.WinError(ctypes.get_last_error())

    def active_processes(self) -> int:
        accounting = _JobObjectBasicAccountingInformation()
        if not self._kernel32.QueryInformationJobObject(
            self._handle,
            self._BASIC_ACCOUNTING_INFORMATION,
            ctypes.byref(accounting),
            ctypes.sizeof(accounting),
            None,
        ):
            raise ctypes.WinError(ctypes.get_last_error())
        return int(accounting.ActiveProcesses)

    def wait_empty(self, timeout: float) -> tuple[bool, str]:
        deadline = time.monotonic() + timeout
        while True:
            try:
                active = self.active_processes()
            except OSError as exc:
                return False, f"job query failed: {type(exc).__name__}"
            if active == 0:
                return True, "job object is empty"
            if time.monotonic() >= deadline:
                return False, f"job object still owns {active} process(es)"
            time.sleep(0.05)

    def terminate(self) -> tuple[bool, str]:
        if not self._kernel32.TerminateJobObject(self._handle, 1):
            return False, f"TerminateJobObject failed: {ctypes.WinError(ctypes.get_last_error())}"
        return self.wait_empty(timeout=5.0)

    def create_start_event(self, name: str) -> int:
        handle = self._kernel32.CreateEventW(None, True, False, name)
        if not handle:
            raise ctypes.WinError(ctypes.get_last_error())
        return int(handle)

    def signal_start_event(self, handle: int) -> None:
        if not self._kernel32.SetEvent(handle):
            raise ctypes.WinError(ctypes.get_last_error())

    def close_handle(self, handle: int) -> tuple[bool, str]:
        if self._kernel32.CloseHandle(handle):
            return True, "handle closed"
        return False, f"CloseHandle failed: {ctypes.WinError(ctypes.get_last_error())}"

    def close(self) -> tuple[bool, str]:
        if self._handle is None:
            return True, "job handle already closed"
        if not self._kernel32.CloseHandle(self._handle):
            return False, f"CloseHandle failed: {ctypes.WinError(ctypes.get_last_error())}"
        self._handle = None
        return True, "job handle closed"


@dataclass
class _OwnedProcess:
    process: subprocess.Popen[str]
    process_group_id: int | None = None
    windows_job: _WindowsJob | None = None
    windows_start_event: int | None = None


_WINDOWS_JOB_LAUNCHER = """
import ctypes
import json
import subprocess
import sys

kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
kernel32.OpenEventW.argtypes = [ctypes.c_ulong, ctypes.c_int, ctypes.c_wchar_p]
kernel32.OpenEventW.restype = ctypes.c_void_p
kernel32.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
kernel32.WaitForSingleObject.restype = ctypes.c_ulong
kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
kernel32.CloseHandle.restype = ctypes.c_int
event = kernel32.OpenEventW(0x00100000, False, sys.argv[1])
if not event:
    raise SystemExit(125)
wait_result = kernel32.WaitForSingleObject(event, 30000)
kernel32.CloseHandle(event)
if wait_result != 0:
    raise SystemExit(125)
raise SystemExit(subprocess.call(json.loads(sys.argv[2])))
"""


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
        owned_process: _OwnedProcess | None = None
        try:
            resolved_command = _resolve_command(command, cwd=effective_cwd)
            owned_process = _start_command(
                resolved_command,
                cwd=effective_cwd,
                env=env,
            )
            try:
                stdout, stderr = owned_process.process.communicate(
                    timeout=self.timeout_seconds
                )
            except subprocess.TimeoutExpired as exc:
                cleanup_confirmed, cleanup_detail = _terminate_process_tree(owned_process)
                release_confirmed, release_detail = _close_owned_process(owned_process)
                process = owned_process.process
                owned_process = None
                if not release_confirmed:
                    cleanup_confirmed = False
                    cleanup_detail += f"; ownership release failed: {release_detail}"
                stdout, stderr = _collect_timeout_output(process, exc)
                cleanup_status = (
                    "confirmed" if cleanup_confirmed else f"FAILED: {cleanup_detail}"
                )
                output_path.write_text(
                    "STDOUT\n"
                    f"{stdout}\n\n"
                    "STDERR\n"
                    f"{stderr}\n\n"
                    f"TIMEOUT after {self.timeout_seconds} seconds\n"
                    f"PROCESS TREE CLEANUP: {cleanup_status}\n",
                    encoding="utf-8",
                )
                reason = "worker command timed out"
                if not cleanup_confirmed:
                    reason += f"; process tree cleanup failed: {cleanup_detail}"
                report_path.write_text(
                    self._failed_report(packet, reason), encoding="utf-8"
                )
                summary = self.store.ingest_report(packet.packet_dir, report_path)
                return WorkerResult(
                    packet=packet, report_path=str(report_path), summary=summary
                )

            returncode = owned_process.process.returncode
            tree_quiet, cleanup_confirmed, tree_detail = _quiesce_after_exit(
                owned_process
            )
            release_confirmed, release_detail = _close_owned_process(owned_process)
            owned_process = None
            if not release_confirmed:
                tree_quiet = False
                cleanup_confirmed = False
                tree_detail += f"; ownership release failed: {release_detail}"
            tree_status = ""
            if not tree_quiet:
                cleanup_status = "confirmed" if cleanup_confirmed else "FAILED"
                tree_status = (
                    "\nPROCESS TREE CHECK: residual owned descendants detected; "
                    f"cleanup {cleanup_status}: {tree_detail}\n"
                )
            output_path.write_text(
                "STDOUT\n"
                f"{stdout}\n\n"
                "STDERR\n"
                f"{stderr}\n"
                f"{tree_status}",
                encoding="utf-8",
            )
        except OSError as exc:
            cleanup_detail = ""
            if owned_process is not None:
                cleanup_confirmed, cleanup_detail = _terminate_process_tree(owned_process)
                release_confirmed, release_detail = _close_owned_process(owned_process)
                owned_process = None
                if not release_confirmed:
                    cleanup_confirmed = False
                    cleanup_detail += f"; ownership release failed: {release_detail}"
                if not cleanup_confirmed:
                    cleanup_detail = f"\nPROCESS TREE CLEANUP: FAILED: {cleanup_detail}"
            output_path.write_text(
                "STDOUT\n\n"
                "STDERR\n"
                f"FAILED TO START: {type(exc).__name__}: {exc}\n"
                f"COMMAND: {command[0]} ({max(0, len(command) - 1)} args)\n"
                f"{cleanup_detail}",
                encoding="utf-8",
            )
            report_path.write_text(
                self._failed_report(packet, f"worker command could not start: {exc}"),
                encoding="utf-8",
            )
            summary = self.store.ingest_report(packet.packet_dir, report_path)
            return WorkerResult(packet=packet, report_path=str(report_path), summary=summary)
        finally:
            if owned_process is not None:
                _terminate_process_tree(owned_process)
                _close_owned_process(owned_process)

        if not tree_quiet:
            worker_report = ""
            if report_path.exists():
                try:
                    worker_report = report_path.read_text(encoding="utf-8")
                except OSError:
                    worker_report = ""
            reason = "worker command exited while owned descendants were still active"
            if not cleanup_confirmed:
                reason += f"; process tree cleanup failed: {tree_detail}"
            failure_report = self._failed_report(packet, reason)
            if worker_report:
                failure_report += "\n## Worker-provided report\n\n" + worker_report
            report_path.write_text(failure_report, encoding="utf-8")
        elif returncode != 0:
            worker_report = ""
            if report_path.exists():
                try:
                    worker_report = report_path.read_text(encoding="utf-8")
                except OSError:
                    worker_report = ""
            failure_report = self._failed_report(
                packet, f"worker command exited {returncode}"
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


def _resolve_command(
    command: list[str], *, cwd: str | Path | None = None
) -> list[str]:
    executable = command[0]
    resolved = shutil.which(executable)
    if resolved is None:
        candidate = Path(executable)
        if not candidate.is_absolute() and cwd is not None:
            candidate = Path(cwd) / candidate
        if not candidate.is_file():
            raise FileNotFoundError(2, "worker executable was not found", executable)
        resolved = str(candidate)
    arguments = command[1:]
    if os.name == "nt":
        lower = resolved.lower()
        if lower.endswith((".cmd", ".bat")):
            raise OSError(
                "Windows batch scripts are not supported because cmd /c "
                "reinterprets argument tokens"
            )
        if lower.endswith(".ps1"):
            return [
                "powershell",
                "-NoProfile",
                "-NonInteractive",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                resolved,
                *arguments,
            ]
    return [resolved, *arguments]


def _start_command(command: list[str], *, cwd: str, env: dict[str, str]) -> _OwnedProcess:
    kwargs: dict[str, object] = {
        "cwd": cwd,
        "env": env,
        "stdout": subprocess.PIPE,
        "stderr": subprocess.PIPE,
        "text": True,
        "encoding": "utf-8",
        "errors": "replace",
    }
    if os.name == "nt":
        job = _WindowsJob()
        event_name = f"Local\\DevFrameWorker-{uuid.uuid4().hex}"
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        event_handle: int | None = None
        process: subprocess.Popen[str] | None = None
        try:
            event_handle = job.create_start_event(event_name)
            process = subprocess.Popen(
                [
                    sys.executable,
                    "-c",
                    _WINDOWS_JOB_LAUNCHER,
                    event_name,
                    json.dumps(command, ensure_ascii=False),
                ],
                **kwargs,
            )
            job.assign(process)
            job.signal_start_event(event_handle)
            return _OwnedProcess(
                process=process,
                windows_job=job,
                windows_start_event=event_handle,
            )
        except BaseException:
            if process is not None:
                _kill_root_process(process)
            if event_handle is not None:
                job.close_handle(event_handle)
            job.close()
            raise

    kwargs["start_new_session"] = True
    process = subprocess.Popen(command, **kwargs)
    return _OwnedProcess(process=process, process_group_id=process.pid)


def _quiesce_after_exit(owned_process: _OwnedProcess) -> tuple[bool, bool, str]:
    if owned_process.windows_job is not None:
        empty, detail = owned_process.windows_job.wait_empty(timeout=0.25)
        if empty:
            return True, True, detail
        cleanup_confirmed, cleanup_detail = _terminate_process_tree(owned_process)
        return False, cleanup_confirmed, f"{detail}; {cleanup_detail}"

    process_group_id = owned_process.process_group_id
    if process_group_id is None:
        cleanup_confirmed, cleanup_detail = _terminate_process_tree(owned_process)
        return False, cleanup_confirmed, f"missing process group; {cleanup_detail}"
    try:
        os.killpg(process_group_id, 0)
    except ProcessLookupError:
        return True, True, "process group is empty"
    except OSError as exc:
        cleanup_confirmed, cleanup_detail = _terminate_process_tree(owned_process)
        return (
            False,
            cleanup_confirmed,
            f"process group query failed: {type(exc).__name__}; {cleanup_detail}",
        )
    cleanup_confirmed, cleanup_detail = _terminate_process_tree(owned_process)
    return False, cleanup_confirmed, f"process group remained active; {cleanup_detail}"


def _terminate_process_tree(owned_process: _OwnedProcess) -> tuple[bool, str]:
    process = owned_process.process
    if os.name == "nt":
        if owned_process.windows_job is None:
            _kill_root_process(process)
            return False, "Windows Job Object is unavailable"
        return owned_process.windows_job.terminate()

    process_group_id = owned_process.process_group_id
    if process_group_id is None:
        _kill_root_process(process)
        return False, "process group is unavailable"
    try:
        os.killpg(process_group_id, signal.SIGTERM)
    except ProcessLookupError:
        return True, "process group already exited"
    except OSError as exc:
        _kill_root_process(process)
        return False, f"SIGTERM failed: {type(exc).__name__}"
    if _wait_process_group_stopped(process, process_group_id, timeout=1.0):
        return True, "process group stopped after SIGTERM"
    try:
        os.killpg(process_group_id, signal.SIGKILL)
    except ProcessLookupError:
        return True, "process group exited before SIGKILL"
    except OSError as exc:
        _kill_root_process(process)
        return False, f"SIGKILL failed: {type(exc).__name__}"
    if _wait_process_group_stopped(process, process_group_id, timeout=5.0):
        return True, "process group stopped after SIGKILL"
    _kill_root_process(process)
    return False, "process group remained alive after SIGKILL"


def _close_owned_process(owned_process: _OwnedProcess) -> tuple[bool, str]:
    details: list[str] = []
    confirmed = True
    job = owned_process.windows_job
    if job is not None and owned_process.windows_start_event is not None:
        event_closed, event_detail = job.close_handle(owned_process.windows_start_event)
        confirmed = confirmed and event_closed
        details.append(event_detail)
        owned_process.windows_start_event = None
    if job is not None:
        job_closed, job_detail = job.close()
        confirmed = confirmed and job_closed
        details.append(job_detail)
        owned_process.windows_job = None
    return confirmed, "; ".join(details) or "no ownership handles to close"


def _wait_process_group_stopped(
    process: subprocess.Popen[str], process_group_id: int, *, timeout: float
) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        process.poll()
        try:
            os.killpg(process_group_id, 0)
        except ProcessLookupError:
            return True
        time.sleep(0.05)
    process.poll()
    try:
        os.killpg(process_group_id, 0)
    except ProcessLookupError:
        return True
    return False


def _kill_root_process(process: subprocess.Popen[str]) -> None:
    if process.poll() is not None:
        return
    try:
        process.kill()
        process.wait(timeout=5)
    except (OSError, subprocess.TimeoutExpired):
        return


def _collect_timeout_output(
    process: subprocess.Popen[str], exc: subprocess.TimeoutExpired
) -> tuple[str, str]:
    try:
        stdout, stderr = process.communicate(timeout=5)
    except subprocess.TimeoutExpired as cleanup_exc:
        _kill_root_process(process)
        try:
            stdout, stderr = process.communicate(timeout=1)
        except subprocess.TimeoutExpired:
            _close_process_pipes(process)
            return (
                _captured_text(cleanup_exc.stdout) or _captured_text(exc.stdout),
                _captured_text(cleanup_exc.stderr) or _captured_text(exc.stderr),
            )
    return stdout or _captured_text(exc.stdout), stderr or _captured_text(exc.stderr)


def _close_process_pipes(process: subprocess.Popen[str]) -> None:
    for stream in (process.stdout, process.stderr):
        if stream is not None and not stream.closed:
            stream.close()


def _captured_text(value: str | bytes | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


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
