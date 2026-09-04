"""Pinned Pi JSONL RPC boundary behind DevFrame's neutral executor seam.

This first slice is deliberately readiness-only: it validates the installed
artifact, starts Pi with project resources and persistence disabled, sends one
offline ``get_state`` command, validates the correlated response, and exits.
It never sends a prompt and it owns no verification or acceptance authority.

Current boundary: ``PLAN.md`` and ``rules/recon.md``.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO

from .local_process_containment import WindowsJob
from .toolchain_execution import _terminate_process_tree


_WindowsJob = WindowsJob


OFFICIAL_PI_PACKAGE = "@earendil-works/pi-coding-agent"
OFFICIAL_PI_VERSION = "0.84.1"
OFFICIAL_PI_RESOLVED = (
    "https://registry.npmjs.org/@earendil-works/"
    "pi-coding-agent/-/pi-coding-agent-0.84.1.tgz"
)
OFFICIAL_PI_INTEGRITY = (
    "sha512-ncAqFrG+iybuPGOhMiZoEHkEzTpJgz3guYD32pD+M7ucc0WeHmauP6wa7qwP8V/"
    "KWvsZDVNa5XGsdZ7fkC7w7A=="
)
OFFICIAL_PI_CLI_SHA256 = "840d1e8e689ed9e4937bcb00b9a810e02a8567d9afb10a47097f11ca93ea1521"
OFFICIAL_PI_PROTOCOL = "pi-jsonl-rpc-v1"
MAX_PI_RPC_TIMEOUT_SECONDS = 900.0

_PROBE_ID = "devframe-pi-readiness-1"
_MAX_LOCK_BYTES = 1_048_576
_MAX_STDOUT_BYTES = 1_048_576
_MAX_STDERR_BYTES = 65_536
_MAX_COMMAND_PART_CHARS = 4096
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_MODEL_SELECTOR = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/+@-]{0,127}\Z")
_SHELL_SUFFIXES = {".bat", ".cmd", ".ps1"}
_INHERITED_ENV_KEYS = {
    "COMSPEC",
    "LANG",
    "LC_ALL",
    "PATH",
    "PATHEXT",
    "SYSTEMDRIVE",
    "SYSTEMROOT",
    "TEMP",
    "TMP",
    "WINDIR",
}
_RPC_ARGS = (
    "--mode",
    "rpc",
    "--offline",
    "--no-session",
    "--no-approve",
    "--no-extensions",
    "--no-skills",
    "--no-prompt-templates",
    "--no-context-files",
)


class PiRpcError(RuntimeError):
    """A fail-closed Pi identity, launch, framing, timeout, or response error."""


@dataclass(frozen=True)
class PiRpcConfig:
    """Caller-owned paths, bounds, and optional non-secret model selection."""

    command: tuple[str, ...]
    lock_path: Path
    artifact_path: Path
    artifact_sha256: str
    agent_dir: Path
    cwd: Path
    timeout_seconds: float = 10.0
    provider: str | None = None
    model: str | None = None

    def __post_init__(self) -> None:
        if (
            len(self.command) != 2
            or any(
                not isinstance(part, str)
                or not part
                or "\x00" in part
                or len(part) > _MAX_COMMAND_PART_CHARS
                for part in self.command
            )
        ):
            raise ValueError("Pi RPC command must be runtime plus pinned artifact")
        if (
            not _SHA256.fullmatch(self.artifact_sha256)
            or self.artifact_sha256 != OFFICIAL_PI_CLI_SHA256
        ):
            raise ValueError("Pi RPC artifact_sha256 must match the pinned artifact")
        if (
            isinstance(self.timeout_seconds, bool)
            or not isinstance(self.timeout_seconds, (int, float))
            or not 0.1 <= float(self.timeout_seconds) <= MAX_PI_RPC_TIMEOUT_SECONDS
        ):
            raise ValueError("Pi RPC timeout_seconds must be between 0.1 and 900")
        if (self.provider is None) != (self.model is None):
            raise ValueError("Pi RPC provider and model must be selected together")
        for value, label in ((self.provider, "provider"), (self.model, "model")):
            if value is not None and not _valid_model_selector(value):
                raise ValueError(f"Pi RPC {label} selection is invalid")
        for value, label in (
            (self.lock_path, "lock_path"),
            (self.artifact_path, "artifact_path"),
            (self.agent_dir, "agent_dir"),
            (self.cwd, "cwd"),
        ):
            if not isinstance(value, Path):
                raise TypeError(f"Pi RPC {label} must be a Path")

    def rpc_args(self) -> tuple[str, ...]:
        if self.provider is None:
            return _RPC_ARGS
        assert self.model is not None
        return (
            *_RPC_ARGS,
            "--provider",
            self.provider,
            "--model",
            self.model,
        )


def _valid_model_selector(value: object) -> bool:
    if not isinstance(value, str) or _MODEL_SELECTOR.fullmatch(value) is None:
        return False
    return all(part not in {"", ".", ".."} for part in value.split("/"))


@dataclass(frozen=True)
class PiRpcPreparedRuntime:
    """Identity-checked launch facts shared by Pi protocol operations."""

    command: tuple[str, str]
    cwd: Path
    environment: tuple[tuple[str, str], ...]
    timeout_seconds: float
    rpc_args: tuple[str, ...] = _RPC_ARGS

    def environment_dict(self) -> dict[str, str]:
        return dict(self.environment)


@dataclass(frozen=True)
class PiRpcProbeResult:
    """Bounded readiness evidence; intentionally excludes provider/model data."""

    adapter_id: str
    protocol: str
    package: str
    version: str
    integrity: str
    artifact_sha256: str
    state_received: bool
    is_streaming: bool
    message_count: int
    process_exit_code: int


@dataclass
class _ReaderResult:
    data: bytearray
    overflow: bool = False
    error: str = ""


@dataclass(frozen=True)
class _ProcessResult:
    returncode: int
    stdout: bytes
    stderr: bytes


class PiRpcAdapter:
    """Identify and probe one pinned Pi runtime without model execution."""

    adapter_id = "pi-rpc"
    protocol = OFFICIAL_PI_PROTOCOL

    def __init__(self, config: PiRpcConfig) -> None:
        if not isinstance(config, PiRpcConfig):
            raise TypeError("PiRpcAdapter requires PiRpcConfig")
        self._config = config

    def probe(self) -> PiRpcProbeResult:
        """Run the real credential-free Pi version and offline RPC path."""

        prepared = self.prepare_runtime()
        env = prepared.environment_dict()

        version_result = self._run_bounded((*prepared.command, "--version"), b"", env=env)
        if version_result.returncode != 0 or version_result.stderr:
            raise PiRpcError("Pi version probe failed")
        try:
            version = version_result.stdout.decode("utf-8", errors="strict").strip("\r\n")
        except UnicodeDecodeError as exc:
            raise PiRpcError("Pi version output is not UTF-8") from exc
        if version != OFFICIAL_PI_VERSION:
            raise PiRpcError("Pi version identity mismatch")

        request = json.dumps(
            {"id": _PROBE_ID, "type": "get_state"},
            ensure_ascii=True,
            separators=(",", ":"),
        ).encode("utf-8") + b"\n"
        rpc_result = self._run_bounded(
            (*prepared.command, *prepared.rpc_args), request, env=env
        )
        if rpc_result.returncode != 0 or rpc_result.stderr:
            raise PiRpcError("Pi RPC probe failed")
        response = self._parse_response(rpc_result.stdout)
        data = response.get("data")
        if not isinstance(data, dict):
            raise PiRpcError("Pi RPC response data is invalid")
        is_streaming = data.get("isStreaming")
        message_count = data.get("messageCount")
        if (
            is_streaming is not False
            or isinstance(message_count, bool)
            or not isinstance(message_count, int)
            or message_count < 0
        ):
            raise PiRpcError("Pi RPC state is invalid")
        return PiRpcProbeResult(
            adapter_id=self.adapter_id,
            protocol=self.protocol,
            package=OFFICIAL_PI_PACKAGE,
            version=OFFICIAL_PI_VERSION,
            integrity=OFFICIAL_PI_INTEGRITY,
            artifact_sha256=self._config.artifact_sha256,
            state_received=True,
            is_streaming=False,
            message_count=message_count,
            process_exit_code=rpc_result.returncode,
        )

    def prepare_runtime(self) -> PiRpcPreparedRuntime:
        """Validate the pinned installation and return bounded launch facts."""

        self._verify_lock()
        self._verify_artifact()
        launch = self._resolve_launch()
        env = self._probe_env()
        return PiRpcPreparedRuntime(
            command=(launch[0], launch[1]),
            cwd=self._config.cwd.resolve(),
            environment=tuple(sorted(env.items())),
            timeout_seconds=float(self._config.timeout_seconds),
            rpc_args=self._config.rpc_args(),
        )

    def _verify_lock(self) -> None:
        path = _regular_file(self._config.lock_path, "lock")
        try:
            size = path.stat().st_size
            if size > _MAX_LOCK_BYTES:
                raise PiRpcError("Pi lock identity mismatch")
            payload = json.loads(path.read_bytes().decode("utf-8", errors="strict"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise PiRpcError("Pi lock identity mismatch") from exc
        if not isinstance(payload, dict):
            raise PiRpcError("Pi lock identity mismatch")
        packages = payload.get("packages")
        if not isinstance(packages, dict):
            raise PiRpcError("Pi lock identity mismatch")
        root = packages.get("")
        record = packages.get(f"node_modules/{OFFICIAL_PI_PACKAGE}")
        dependencies = root.get("dependencies") if isinstance(root, dict) else None
        if (
            not isinstance(dependencies, dict)
            or dependencies.get(OFFICIAL_PI_PACKAGE) != OFFICIAL_PI_VERSION
            or not isinstance(record, dict)
            or record.get("version") != OFFICIAL_PI_VERSION
            or record.get("resolved") != OFFICIAL_PI_RESOLVED
            or record.get("integrity") != OFFICIAL_PI_INTEGRITY
            or record.get("license") != "MIT"
        ):
            raise PiRpcError("Pi lock identity mismatch")

    def _verify_artifact(self) -> None:
        path = _regular_file(self._config.artifact_path, "artifact")
        digest = hashlib.sha256()
        try:
            with path.open("rb") as handle:
                for chunk in iter(lambda: handle.read(65_536), b""):
                    digest.update(chunk)
        except OSError as exc:
            raise PiRpcError("Pi artifact identity mismatch") from exc
        if digest.hexdigest() != self._config.artifact_sha256:
            raise PiRpcError("Pi artifact identity mismatch")

    def _resolve_launch(self) -> tuple[str, ...]:
        executable = shutil.which(self._config.command[0]) or self._config.command[0]
        path = Path(executable)
        if path.suffix.lower() in _SHELL_SUFFIXES:
            raise PiRpcError("Pi shell shims are unsupported; use node plus dist/cli.js")
        if not path.is_file():
            raise PiRpcError("Pi executable is unavailable")
        configured_artifact = Path(self._config.command[1])
        if not configured_artifact.is_absolute():
            configured_artifact = self._config.cwd / configured_artifact
        try:
            command_artifact = configured_artifact.resolve(strict=True)
            approved_artifact = self._config.artifact_path.resolve(strict=True)
            same_artifact = os.path.samefile(command_artifact, approved_artifact)
        except OSError as exc:
            raise PiRpcError("Pi command/artifact identity mismatch") from exc
        if not same_artifact:
            raise PiRpcError("Pi command/artifact identity mismatch")
        return (str(path.resolve()), str(approved_artifact))

    def _probe_env(self) -> dict[str, str]:
        agent_dir = _directory(self._config.agent_dir, "agent_dir")
        _directory(self._config.cwd, "cwd")
        env = {
            key: value
            for key, value in os.environ.items()
            if key.upper() in _INHERITED_ENV_KEYS and "\x00" not in value
        }
        env.update(
            {
                "HOME": str(agent_dir),
                "USERPROFILE": str(agent_dir),
                "APPDATA": str(agent_dir / "appdata"),
                "LOCALAPPDATA": str(agent_dir / "localappdata"),
                "PI_CODING_AGENT_DIR": str(agent_dir),
                "PI_OFFLINE": "1",
                "PI_TELEMETRY": "0",
            }
        )
        return env

    def _run_bounded(
        self,
        command: tuple[str, ...],
        input_bytes: bytes,
        *,
        env: dict[str, str],
    ) -> _ProcessResult:
        creationflags = (
            getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) if os.name == "nt" else 0
        )
        job: _WindowsJob | None = None
        process: subprocess.Popen[bytes] | None = None
        stdout_thread: threading.Thread | None = None
        stderr_thread: threading.Thread | None = None
        started_threads: list[threading.Thread] = []
        stdout_result = _ReaderResult(bytearray())
        stderr_result = _ReaderResult(bytearray())
        job_assigned = False
        unexpected_descendant = False
        cleanup_failed = False
        primary_error: BaseException | None = None
        try:
            try:
                job = _WindowsJob() if os.name == "nt" else None
            except OSError as exc:
                raise PiRpcError("Pi process containment could not start") from exc
            if job is not None:
                creationflags |= job.suspended_creation_flag()
            try:
                process = subprocess.Popen(
                    list(command),
                    cwd=str(self._config.cwd.resolve()),
                    env=env,
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=False,
                    creationflags=creationflags,
                    start_new_session=os.name != "nt",
                )
            except OSError as exc:
                raise PiRpcError("Pi process could not start") from exc
            if job is not None:
                try:
                    job.assign(process)
                    job_assigned = True
                    job.resume(process)
                except OSError as exc:
                    raise PiRpcError("Pi process containment failed") from exc
            if process.stdin is None or process.stdout is None or process.stderr is None:
                raise PiRpcError("Pi process pipes are unavailable")
            try:
                stdout_thread = threading.Thread(
                    target=_drain_bounded,
                    args=(process.stdout, _MAX_STDOUT_BYTES, stdout_result),
                    name="pi-rpc-stdout",
                    daemon=True,
                )
                stderr_thread = threading.Thread(
                    target=_drain_bounded,
                    args=(process.stderr, _MAX_STDERR_BYTES, stderr_result),
                    name="pi-rpc-stderr",
                    daemon=True,
                )
                stdout_thread.start()
                started_threads.append(stdout_thread)
                stderr_thread.start()
                started_threads.append(stderr_thread)
            except RuntimeError as exc:
                raise PiRpcError("Pi output readers could not start") from exc
            if process.stdin is None:
                raise PiRpcError("Pi process stdin is unavailable")
            try:
                if input_bytes:
                    process.stdin.write(input_bytes)
                    process.stdin.flush()
            except (BrokenPipeError, OSError) as exc:
                raise PiRpcError("Pi process rejected input") from exc
            finally:
                process.stdin.close()
            try:
                process.wait(timeout=float(self._config.timeout_seconds))
            except subprocess.TimeoutExpired as exc:
                raise PiRpcError("Pi process timed out") from exc
        except BaseException as exc:
            primary_error = exc
            raise
        finally:
            if process is not None and process.stdin is not None and not process.stdin.closed:
                try:
                    process.stdin.close()
                except OSError:
                    cleanup_failed = True
            if process is not None and process.poll() is not None:
                if job is not None and job_assigned:
                    try:
                        unexpected_descendant = job.active_processes() > 0
                    except OSError:
                        unexpected_descendant = True
                        cleanup_failed = True
                elif job is None:
                    unexpected_descendant = _posix_process_group_exists(process.pid)
            if job is not None:
                if not job.close():
                    cleanup_failed = True
            if process is not None:
                if process.poll() is None or (job is None and unexpected_descendant):
                    try:
                        _terminate_process_tree(process)
                    except OSError:
                        cleanup_failed = True
                try:
                    process.wait(timeout=5.0)
                except subprocess.TimeoutExpired:
                    try:
                        process.kill()
                        process.wait(timeout=5.0)
                    except (OSError, subprocess.TimeoutExpired):
                        cleanup_failed = True
                for stream, reader in (
                    (process.stdout, stdout_thread),
                    (process.stderr, stderr_thread),
                ):
                    if stream is not None and reader not in started_threads:
                        try:
                            stream.close()
                        except OSError:
                            cleanup_failed = True
            for reader in started_threads:
                reader.join(timeout=2.0)
                if reader.is_alive():
                    cleanup_failed = True
            if cleanup_failed:
                if primary_error is not None:
                    setattr(primary_error, "cleanup_failed", True)
                else:
                    raise PiRpcError("Pi process containment cleanup failed")
        assert process is not None
        if any(reader.is_alive() for reader in started_threads):
            raise PiRpcError("Pi output readers did not stop")
        if stdout_result.error or stderr_result.error:
            raise PiRpcError("Pi output could not be read")
        if stdout_result.overflow or stderr_result.overflow:
            raise PiRpcError("Pi output exceeded the probe limit")
        if unexpected_descendant:
            raise PiRpcError("Pi process left an unexpected descendant")
        return _ProcessResult(
            returncode=int(process.returncode or 0),
            stdout=bytes(stdout_result.data),
            stderr=bytes(stderr_result.data),
        )

    @staticmethod
    def _parse_response(stdout: bytes) -> dict[str, object]:
        if not stdout.endswith(b"\n"):
            raise PiRpcError("Pi RPC response is not LF-delimited")
        records = stdout[:-1].split(b"\n")
        if len(records) != 1 or not records[0]:
            raise PiRpcError("Pi RPC response count is invalid")
        raw = records[0][:-1] if records[0].endswith(b"\r") else records[0]
        try:
            response = json.loads(raw.decode("utf-8", errors="strict"))
        except (UnicodeError, json.JSONDecodeError) as exc:
            raise PiRpcError("Pi RPC response is invalid") from exc
        if (
            not isinstance(response, dict)
            or response.get("id") != _PROBE_ID
            or response.get("type") != "response"
            or response.get("command") != "get_state"
            or response.get("success") is not True
        ):
            raise PiRpcError("Pi RPC response is invalid")
        return response


def _regular_file(value: Path, label: str) -> Path:
    if value.is_symlink() or not value.is_file():
        raise PiRpcError(f"Pi {label} identity mismatch")
    return value.resolve()


def _directory(value: Path, label: str) -> Path:
    if value.is_symlink() or not value.is_dir():
        raise PiRpcError(f"Pi {label} must be an existing non-symlink directory")
    return value.resolve()


def _drain_bounded(stream: BinaryIO, limit: int, result: _ReaderResult) -> None:
    try:
        while True:
            chunk = stream.read(65_536)
            if not chunk:
                return
            remaining = max(0, limit - len(result.data))
            if remaining:
                result.data.extend(chunk[:remaining])
            if len(chunk) > remaining:
                result.overflow = True
    except OSError as exc:
        result.error = type(exc).__name__


def _posix_process_group_exists(pid: int) -> bool:
    if os.name == "nt":
        return False
    try:
        os.killpg(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True
