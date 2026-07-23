"""Local dry-run worker for rdgoal dispatch packets.

This worker proves the packet -> ExecutionReport -> ingest loop without
modifying the target project. Real workers can later replace this adapter.
"""
from __future__ import annotations

import os
import signal
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from .dispatch_packet import DispatchPacket, DispatchPacketStore, ExecutionReportSummary
from .provider_secret import (
    PROVIDER_SECRET_ENV_NAMES,
    ProviderSecretAttestation,
    ProviderSecretError,
    redact_provider_secret_text,
)


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
                   env_overrides: dict[str, str] | None = None,
                   provider_secret: ProviderSecretAttestation | None = None,
                   strip_provider_secrets: bool = False) -> WorkerResult:
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
        contain_provider_secrets = strip_provider_secrets or provider_secret is not None
        if contain_provider_secrets:
            for env_name in PROVIDER_SECRET_ENV_NAMES:
                env.pop(env_name, None)
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
            normalized_overrides = {
                str(key): str(value) for key, value in env_overrides.items()
            }
            if contain_provider_secrets and PROVIDER_SECRET_ENV_NAMES.intersection(
                normalized_overrides
            ):
                raise ProviderSecretError(
                    "secret_override_rejected",
                    provider_id=(
                        provider_secret.provider_id if provider_secret else ""
                    ),
                    detail="provider secrets must use the attested child-process boundary",
                )
            env.update(normalized_overrides)
        if provider_secret is not None:
            env.update(provider_secret.child_environment())
        redaction_values = (
            provider_secret.redaction_values() if provider_secret is not None else ()
        )
        effective_cwd = str(cwd) if cwd is not None else packet.project_root
        resolved_command = _resolve_command(command)
        try:
            completed = _run_command(
                resolved_command,
                cwd=effective_cwd,
                env=env,
                timeout=self.timeout_seconds,
                require_windows_job_containment=bool(redaction_values),
            )
            stdout = redact_provider_secret_text(completed.stdout, redaction_values)
            stderr = redact_provider_secret_text(completed.stderr, redaction_values)
            output_path.write_text(
                "STDOUT\n"
                f"{stdout}\n\n"
                "STDERR\n"
                f"{stderr}\n",
                encoding="utf-8",
            )
        except subprocess.TimeoutExpired as exc:
            stdout = redact_provider_secret_text(
                _captured_text(exc.stdout), redaction_values
            )
            stderr = redact_provider_secret_text(
                _captured_text(exc.stderr), redaction_values
            )
            output_path.write_text(
                "STDOUT\n"
                f"{stdout}\n\n"
                "STDERR\n"
                f"{stderr}\n\n"
                f"TIMEOUT after {self.timeout_seconds} seconds\n",
                encoding="utf-8",
            )
            report_path.write_text(self._failed_report(packet, "worker command timed out"), encoding="utf-8")
            _sanitize_text_file(report_path, redaction_values)
            summary = self.store.ingest_report(packet.packet_dir, report_path)
            return WorkerResult(packet=packet, report_path=str(report_path), summary=summary)
        except OSError as exc:
            safe_error = redact_provider_secret_text(
                f"{type(exc).__name__}: {exc}",
                redaction_values,
            )
            output_path.write_text(
                "STDOUT\n\n"
                "STDERR\n"
                f"FAILED TO START: {safe_error}\n"
                f"COMMAND: {command[0]} ({max(0, len(command) - 1)} args)\n",
                encoding="utf-8",
            )
            report_path.write_text(
                self._failed_report(
                    packet, f"worker command could not start: {safe_error}"
                ),
                encoding="utf-8",
            )
            _sanitize_text_file(report_path, redaction_values)
            summary = self.store.ingest_report(packet.packet_dir, report_path)
            return WorkerResult(packet=packet, report_path=str(report_path), summary=summary)
        except BaseException:
            _sanitize_text_file(report_path, redaction_values)
            _sanitize_text_file(output_path, redaction_values)
            raise
        finally:
            for env_name in PROVIDER_SECRET_ENV_NAMES:
                env.pop(env_name, None)

        _sanitize_text_file(report_path, redaction_values)
        if completed.returncode != 0:
            worker_report = ""
            if report_path.exists():
                try:
                    worker_report = report_path.read_text(encoding="utf-8")
                except OSError:
                    worker_report = ""
            failure_report = self._failed_report(
                packet, f"worker command exited {completed.returncode}"
            )
            if worker_report:
                failure_report += "\n## Worker-provided report\n\n" + worker_report
            report_path.write_text(failure_report, encoding="utf-8")
        elif not report_path.exists():
            report_path.write_text(
                self._failed_report(packet, "worker command did not produce ExecutionReport.md"),
                encoding="utf-8",
            )

        _sanitize_text_file(report_path, redaction_values)
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


def _run_command(
    command: list[str],
    *,
    cwd: str,
    env: dict[str, str],
    timeout: int,
    require_windows_job_containment: bool = False,
) -> subprocess.CompletedProcess[str]:
    """Run one worker in a contained process group and clean up on every exit."""

    job_handle = _create_windows_kill_job()
    if (
        os.name == "nt"
        and require_windows_job_containment
        and job_handle is None
    ):
        raise OSError("contained worker Job Object could not be created")
    suspend_for_job_assignment = os.name == "nt" and job_handle is not None
    creationflags = 0
    if os.name == "nt":
        creationflags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        if suspend_for_job_assignment:
            creationflags |= getattr(subprocess, "CREATE_SUSPENDED", 0x00000004)
    process: subprocess.Popen[str] | None = None
    try:
        process = subprocess.Popen(
            command,
            cwd=cwd,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=creationflags,
            start_new_session=os.name != "nt",
        )
        if job_handle is not None and not _assign_windows_kill_job(job_handle, process):
            if require_windows_job_containment:
                _terminate_process_tree(process, None)
                _drain_process(process)
                raise OSError("contained worker could not enter its Job Object")
            _close_windows_kill_job(job_handle)
            job_handle = None
        if suspend_for_job_assignment and not _resume_windows_process(process):
            _terminate_process_tree(process, job_handle)
            _drain_process(process)
            raise OSError("contained worker process could not be resumed")
        try:
            stdout, stderr = process.communicate(timeout=timeout)
        except subprocess.TimeoutExpired as exc:
            _terminate_process_tree(process, job_handle)
            stdout, stderr = _drain_process(process)
            raise subprocess.TimeoutExpired(
                command,
                timeout,
                output=_captured_text(exc.stdout) + stdout,
                stderr=_captured_text(exc.stderr) + stderr,
            ) from None
        except BaseException:
            _terminate_process_tree(process, job_handle)
            _drain_process(process)
            raise
        return subprocess.CompletedProcess(
            command,
            process.returncode,
            stdout,
            stderr,
        )
    finally:
        if process is not None and job_handle is None:
            _terminate_process_tree(process, None)
        if job_handle is not None:
            _close_windows_kill_job(job_handle)
        if process is not None and process.poll() is None:
            _terminate_process_tree(process, None)
            _drain_process(process)


def _drain_process(process: subprocess.Popen[str]) -> tuple[str, str]:
    try:
        stdout, stderr = process.communicate(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        try:
            stdout, stderr = process.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            if process.stdout is not None:
                process.stdout.close()
            if process.stderr is not None:
                process.stderr.close()
            process.wait(timeout=5)
            return "", ""
    return _captured_text(stdout), _captured_text(stderr)


def _terminate_process_tree(
    process: subprocess.Popen[str],
    job_handle: int | None,
) -> None:
    if os.name == "nt":
        if job_handle is not None:
            _terminate_windows_kill_job(job_handle)
        else:
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
            pass
        else:
            time.sleep(0.2)
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
    if process.poll() is None:
        process.kill()


def _create_windows_kill_job() -> int | None:
    if os.name != "nt":
        return None
    import ctypes
    from ctypes import wintypes

    class _IoCounters(ctypes.Structure):
        _fields_ = [
            ("ReadOperationCount", ctypes.c_ulonglong),
            ("WriteOperationCount", ctypes.c_ulonglong),
            ("OtherOperationCount", ctypes.c_ulonglong),
            ("ReadTransferCount", ctypes.c_ulonglong),
            ("WriteTransferCount", ctypes.c_ulonglong),
            ("OtherTransferCount", ctypes.c_ulonglong),
        ]

    class _BasicLimitInformation(ctypes.Structure):
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

    class _ExtendedLimitInformation(ctypes.Structure):
        _fields_ = [
            ("BasicLimitInformation", _BasicLimitInformation),
            ("IoInfo", _IoCounters),
            ("ProcessMemoryLimit", ctypes.c_size_t),
            ("JobMemoryLimit", ctypes.c_size_t),
            ("PeakProcessMemoryUsed", ctypes.c_size_t),
            ("PeakJobMemoryUsed", ctypes.c_size_t),
        ]

    kernel32 = ctypes.windll.kernel32
    kernel32.CreateJobObjectW.argtypes = [wintypes.LPVOID, wintypes.LPCWSTR]
    kernel32.CreateJobObjectW.restype = wintypes.HANDLE
    kernel32.SetInformationJobObject.argtypes = [
        wintypes.HANDLE,
        ctypes.c_int,
        wintypes.LPVOID,
        wintypes.DWORD,
    ]
    kernel32.SetInformationJobObject.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL
    handle = kernel32.CreateJobObjectW(None, None)
    if not handle:
        return None
    info = _ExtendedLimitInformation()
    info.BasicLimitInformation.LimitFlags = 0x2000
    if not kernel32.SetInformationJobObject(
        wintypes.HANDLE(handle),
        9,
        ctypes.byref(info),
        ctypes.sizeof(info),
    ):
        kernel32.CloseHandle(wintypes.HANDLE(handle))
        return None
    return int(handle)


def _assign_windows_kill_job(
    job_handle: int,
    process: subprocess.Popen[str],
) -> bool:
    if os.name != "nt":
        return False
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.windll.kernel32
    kernel32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    kernel32.AssignProcessToJobObject.restype = wintypes.BOOL
    process_handle = wintypes.HANDLE(int(getattr(process, "_handle", 0)))
    return bool(
        kernel32.AssignProcessToJobObject(wintypes.HANDLE(job_handle), process_handle)
    )


def _resume_windows_process(process: subprocess.Popen[str]) -> bool:
    if os.name != "nt":
        return True
    import ctypes
    from ctypes import wintypes

    ntdll = ctypes.windll.ntdll
    ntdll.NtResumeProcess.argtypes = [wintypes.HANDLE]
    ntdll.NtResumeProcess.restype = wintypes.LONG
    process_handle = wintypes.HANDLE(int(getattr(process, "_handle", 0)))
    return ntdll.NtResumeProcess(process_handle) >= 0


def _terminate_windows_kill_job(job_handle: int) -> None:
    if os.name != "nt":
        return
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.windll.kernel32
    kernel32.TerminateJobObject.argtypes = [wintypes.HANDLE, wintypes.UINT]
    kernel32.TerminateJobObject.restype = wintypes.BOOL
    kernel32.TerminateJobObject(wintypes.HANDLE(job_handle), 1)


def _close_windows_kill_job(job_handle: int) -> None:
    if os.name != "nt":
        return
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.windll.kernel32
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL
    kernel32.CloseHandle(wintypes.HANDLE(job_handle))


def _captured_text(value: str | bytes | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


def _sanitize_text_file(path: Path, secrets: tuple[str, ...]) -> None:
    if not secrets or not path.is_file():
        return
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return
    sanitized = redact_provider_secret_text(text, secrets)
    if sanitized != text:
        path.write_text(sanitized, encoding="utf-8")


def _resolve_command(command: list[str]) -> list[str]:
    executable = command[0]
    resolved = shutil.which(executable)
    if not resolved:
        return command
    return [resolved, *command[1:]]


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
