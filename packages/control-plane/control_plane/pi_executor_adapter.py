"""Map Pi RPC turn facts through DevFrame's provider-neutral executor seam.

This boundary renders a draft ExecutionReport and returns the existing
``WorkerResult``.  It never turns execution completion into verification or
acceptance; a completed Pi turn remains blocked pending independent checks.
"""

from __future__ import annotations

import os
import re
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from typing import Callable, Protocol

from .dispatch_packet import DispatchPacket, DispatchPacketStore
from .executor_adapter import ExecutorAdapter, ExecutorInvocation
from .executor_readiness import (
    ExecutorReadinessAdapter,
    ExecutorReadinessResult,
    is_local_absolute_path,
)
from .pi_rpc_adapter import (
    MAX_PI_RPC_TIMEOUT_SECONDS,
    OFFICIAL_PI_CLI_SHA256,
    OFFICIAL_PI_INTEGRITY,
    OFFICIAL_PI_PACKAGE,
    OFFICIAL_PI_PROTOCOL,
    OFFICIAL_PI_VERSION,
    PiRpcAdapter,
    PiRpcConfig,
    PiRpcProbeResult,
)
from .pi_rpc_turn import MAX_PI_RPC_TURN_EVENTS, PiRpcTurnResult, PiRpcTurnRunner
from .worker import WorkerResult


_EVENT_EVIDENCE = re.compile(
    r"pi:event:(?P<sequence>[0-9]{6}):"
    r"(?P<event_type>[a-z][a-z0-9_]*):sha256:[0-9a-f]{64}\Z"
)
_MAX_EVENT_EVIDENCE_CHARS = 160
_PI_EVENT_TYPES = frozenset(
    {
        "agent_start",
        "agent_end",
        "agent_settled",
        "turn_start",
        "turn_end",
        "message_start",
        "message_update",
        "message_end",
        "bash_execution_update",
        "tool_execution_start",
        "tool_execution_update",
        "tool_execution_end",
        "queue_update",
        "compaction_start",
        "compaction_end",
        "auto_retry_start",
        "auto_retry_end",
        "summarization_retry_scheduled",
        "summarization_retry_attempt_start",
        "summarization_retry_finished",
        "extension_error",
    }
)
_RESULT_REASONS = {
    "completed": {"STOP"},
    "interrupted": {"ABORTED", "CANCELLED", "CANCELLED_BEFORE_START", "TIMEOUT"},
    "failed": {
        "PI_STOP_ERROR",
        "PI_STOP_LENGTH",
        "PI_STOP_TOOLUSE",
        "PROMPT_REJECTED",
    },
}


class _TurnRunner(Protocol):
    def run_turn(self, message: str, *, cancel_event: object = None) -> PiRpcTurnResult: ...


RunnerFactory = Callable[[PiRpcConfig], _TurnRunner]


class PiExecutorAdapterError(RuntimeError):
    """A sanitized packet, cancellation-marker, or turn-result error."""


class _MarkerCancelSignal:
    def __init__(self, path: Path) -> None:
        self._path = path

    def is_set(self) -> bool:
        return self._path.is_file()


def create_pi_executor_adapter(
    config: PiRpcConfig,
    *,
    runner_factory: RunnerFactory = PiRpcTurnRunner,
) -> ExecutorAdapter:
    """Create the replaceable Pi boundary behind the stable executor port."""

    if not isinstance(config, PiRpcConfig):
        raise TypeError("Pi executor adapter requires PiRpcConfig")
    if not callable(runner_factory):
        raise TypeError("Pi executor adapter runner_factory must be callable")

    def execute(invocation: ExecutorInvocation) -> WorkerResult:
        return _execute_pi_turn(invocation, config, runner_factory)

    return ExecutorAdapter(
        driver="pi",
        adapter_id="pi-rpc-turn",
        protocol=OFFICIAL_PI_PROTOCOL,
        _execute=execute,
    )


def create_pi_environment_executor_adapter() -> ExecutorAdapter:
    """Create the production Pi driver with lazy, local-only path resolution."""

    def execute(invocation: ExecutorInvocation) -> WorkerResult:
        if not isinstance(invocation, ExecutorInvocation):
            raise PiExecutorAdapterError("Pi executor invocation is invalid")
        store, packet, report_path = _load_packet_context(invocation)
        if not packet.dispatch_ready:
            report_path.write_text(
                _render_report(
                    packet,
                    status="blocked",
                    reason="PACKET_NOT_DISPATCH_READY",
                ),
                encoding="utf-8",
            )
            return _ingest(store, packet, report_path)
        try:
            config = _environment_config(invocation)
        except PiExecutorAdapterError:
            report_path.write_text(
                _render_report(
                    packet,
                    status="failed",
                    reason="PI_RUNTIME_UNAVAILABLE",
                ),
                encoding="utf-8",
            )
            return _ingest(store, packet, report_path)
        return _execute_pi_turn(invocation, config, PiRpcTurnRunner)

    return ExecutorAdapter(
        driver="pi",
        adapter_id="pi-rpc-turn",
        protocol=OFFICIAL_PI_PROTOCOL,
        _execute=execute,
    )


def create_pi_readiness_adapter() -> ExecutorReadinessAdapter:
    """Bind Pi's bounded offline probe to the provider-neutral readiness port."""

    def probe(project_root: Path) -> ExecutorReadinessResult:
        try:
            config = _environment_config(SimpleNamespace(project_root=str(project_root)))
        except Exception:
            return ExecutorReadinessResult(
                status="blocked",
                reason="RUNTIME_UNAVAILABLE",
            )
        try:
            result = PiRpcAdapter(config).probe()
        except Exception:
            return ExecutorReadinessResult(
                status="blocked",
                reason="READINESS_FAILED",
            )
        if not _valid_pi_readiness_probe(result):
            return ExecutorReadinessResult(
                status="blocked",
                reason="READINESS_FAILED",
            )
        return ExecutorReadinessResult(
            status="ready",
            details=(
                ("adapter_id", "pi-rpc"),
                ("artifact_sha256", OFFICIAL_PI_CLI_SHA256),
                ("integrity", OFFICIAL_PI_INTEGRITY),
                ("package", OFFICIAL_PI_PACKAGE),
                ("protocol", OFFICIAL_PI_PROTOCOL),
                ("state_received", True),
                ("version", OFFICIAL_PI_VERSION),
            ),
        )

    return ExecutorReadinessAdapter(driver="pi", _probe=probe)


def _valid_pi_readiness_probe(probe: object) -> bool:
    return bool(
        isinstance(probe, PiRpcProbeResult)
        and probe.adapter_id == "pi-rpc"
        and probe.protocol == OFFICIAL_PI_PROTOCOL
        and probe.package == OFFICIAL_PI_PACKAGE
        and probe.version == OFFICIAL_PI_VERSION
        and probe.integrity == OFFICIAL_PI_INTEGRITY
        and probe.artifact_sha256 == OFFICIAL_PI_CLI_SHA256
        and probe.state_received is True
        and probe.is_streaming is False
        and isinstance(probe.message_count, int)
        and not isinstance(probe.message_count, bool)
        and probe.message_count >= 0
        and isinstance(probe.process_exit_code, int)
        and not isinstance(probe.process_exit_code, bool)
        and probe.process_exit_code == 0
    )


def _execute_pi_turn(
    invocation: ExecutorInvocation,
    config: PiRpcConfig,
    runner_factory: RunnerFactory,
) -> WorkerResult:
    if not isinstance(invocation, ExecutorInvocation):
        raise PiExecutorAdapterError("Pi executor invocation is invalid")
    store, packet, report_path = _load_packet_context(invocation)
    if not packet.dispatch_ready:
        report_path.write_text(
            _render_report(packet, status="blocked", reason="PACKET_NOT_DISPATCH_READY"),
            encoding="utf-8",
        )
        return _ingest(store, packet, report_path)

    message = _packet_message(packet)
    if message is None:
        report_path.write_text(
            _render_report(packet, status="failed", reason="PROMPT_UNAVAILABLE"),
            encoding="utf-8",
        )
        return _ingest(store, packet, report_path)

    try:
        cancel_signal = _cancel_signal(invocation)
        result = runner_factory(_effective_config(config, invocation)).run_turn(
            message,
            cancel_event=cancel_signal,
        )
    except Exception:
        report_path.write_text(
            _render_report(packet, status="failed", reason="PI_BOUNDARY_FAILED"),
            encoding="utf-8",
        )
        return _ingest(store, packet, report_path)

    if not _valid_turn_result(result):
        report_path.write_text(
            _render_report(packet, status="failed", reason="PI_RESULT_INVALID"),
            encoding="utf-8",
        )
        return _ingest(store, packet, report_path)

    status, reason = _report_terminal(result)
    report_path.write_text(
        _render_report(
            packet,
            status=status,
            reason=reason,
            execution_status=result.execution_status,
            evidence=result.event_evidence,
        ),
        encoding="utf-8",
    )
    return _ingest(store, packet, report_path)


def _load_packet_context(
    invocation: ExecutorInvocation,
) -> tuple[DispatchPacketStore, DispatchPacket, Path]:
    packet_dir = getattr(invocation.agent, "packet_dir", None)
    if (
        not isinstance(invocation.runtime_dir, str)
        or not invocation.runtime_dir
        or "\x00" in invocation.runtime_dir
        or not isinstance(packet_dir, str)
        or not packet_dir
        or "\x00" in packet_dir
    ):
        raise PiExecutorAdapterError("Pi executor packet reference is invalid")
    try:
        runtime_root = Path(invocation.runtime_dir).resolve(strict=True)
        resolved_packet_dir = Path(packet_dir).resolve(strict=True)
        resolved_packet_dir.relative_to(runtime_root)
        if not runtime_root.is_dir() or not resolved_packet_dir.is_dir():
            raise ValueError
        store = DispatchPacketStore(runtime_dir=runtime_root)
        packet = store.load_packet(resolved_packet_dir)
        packet_record_dir = Path(packet.packet_dir).resolve(strict=True)
        packet_project_root = Path(packet.project_root).resolve(strict=True)
        invocation_project_root = Path(invocation.project_root).resolve(strict=True)
    except Exception:
        raise PiExecutorAdapterError("Pi executor packet reference is invalid") from None
    if (
        packet_record_dir != resolved_packet_dir
        or packet_project_root != invocation_project_root
    ):
        raise PiExecutorAdapterError("Pi executor packet reference is invalid")
    return store, packet, resolved_packet_dir / "ExecutionReport.md"


def _packet_message(packet: DispatchPacket) -> str | None:
    for value in (packet.objective_text, packet.requirement):
        if isinstance(value, str) and value.strip():
            return value
    return None


def _cancel_signal(invocation: ExecutorInvocation) -> _MarkerCancelSignal | None:
    overrides = invocation.env_overrides or {}
    raw = overrides.get("DEVFRAME_CANCEL_MARKER")
    if raw is None:
        return None
    if not isinstance(raw, str) or not raw or "\x00" in raw:
        raise PiExecutorAdapterError("Pi executor cancel marker is invalid")
    marker = Path(raw)
    if not marker.is_absolute():
        raise PiExecutorAdapterError("Pi executor cancel marker is invalid")
    runtime_root = Path(invocation.runtime_dir).resolve()
    resolved = marker.resolve(strict=False)
    try:
        resolved.relative_to(runtime_root)
    except ValueError:
        raise PiExecutorAdapterError("Pi executor cancel marker is invalid") from None
    return _MarkerCancelSignal(resolved)


def _effective_config(
    config: PiRpcConfig,
    invocation: ExecutorInvocation,
) -> PiRpcConfig:
    if (
        isinstance(invocation.timeout_seconds, bool)
        or not isinstance(invocation.timeout_seconds, int)
        or invocation.timeout_seconds <= 0
    ):
        raise PiExecutorAdapterError("Pi executor timeout is invalid")
    for value in (invocation.project_root, invocation.cwd or invocation.project_root):
        if not isinstance(value, str) or not value or "\x00" in value:
            raise PiExecutorAdapterError("Pi executor working directory is invalid")
    try:
        project_root = Path(invocation.project_root).resolve(strict=True)
        cwd = Path(invocation.cwd or invocation.project_root).resolve(strict=True)
        cwd.relative_to(project_root)
    except (OSError, ValueError):
        raise PiExecutorAdapterError("Pi executor working directory is invalid") from None
    if not project_root.is_dir() or not cwd.is_dir():
        raise PiExecutorAdapterError("Pi executor working directory is invalid")
    return replace(
        config,
        cwd=cwd,
        timeout_seconds=min(
            float(config.timeout_seconds),
            float(invocation.timeout_seconds),
        ),
    )


def _environment_config(invocation: ExecutorInvocation) -> PiRpcConfig:
    raw_runtime = os.environ.get("DEVFRAME_PI_RUNTIME", "").strip()
    raw_node = os.environ.get("DEVFRAME_PI_NODE", "").strip()
    raw_provider = os.environ.get("DEVFRAME_PI_PROVIDER", "")
    raw_model = os.environ.get("DEVFRAME_PI_MODEL", "")
    raw_timeout = getattr(invocation, "timeout_seconds", 30)
    if (
        isinstance(raw_timeout, bool)
        or not isinstance(raw_timeout, int)
        or raw_timeout <= 0
        or raw_timeout > MAX_PI_RPC_TIMEOUT_SECONDS
    ):
        raise PiExecutorAdapterError("Pi executor timeout is invalid")
    if not is_local_absolute_path(raw_runtime) or not is_local_absolute_path(raw_node):
        raise PiExecutorAdapterError("Pi executor runtime is unavailable")
    runtime_path = Path(raw_runtime)
    node_path = Path(raw_node)
    try:
        runtime_root = runtime_path.resolve(strict=True)
        node = node_path.resolve(strict=True)
    except OSError:
        raise PiExecutorAdapterError("Pi executor runtime is unavailable") from None
    if (
        not is_local_absolute_path(str(runtime_root))
        or not is_local_absolute_path(str(node))
        or not runtime_root.is_dir()
        or not node.is_file()
    ):
        raise PiExecutorAdapterError("Pi executor runtime is unavailable")
    artifact = (
        runtime_root
        / "node_modules"
        / "@earendil-works"
        / "pi-coding-agent"
        / "dist"
        / "cli.js"
    )
    try:
        return PiRpcConfig(
            command=(str(node), str(artifact)),
            lock_path=runtime_root / "package-lock.json",
            artifact_path=artifact,
            artifact_sha256=OFFICIAL_PI_CLI_SHA256,
            agent_dir=runtime_root / ".isolated-agent-home",
            cwd=Path(invocation.project_root),
            timeout_seconds=float(raw_timeout),
            provider=raw_provider or None,
            model=raw_model or None,
        )
    except ValueError:
        raise PiExecutorAdapterError("Pi executor runtime is unavailable") from None


def _valid_turn_result(result: object) -> bool:
    if not isinstance(result, PiRpcTurnResult):
        return False
    if (
        not isinstance(result.execution_status, str)
        or not isinstance(result.reason, str)
        or not isinstance(result.prompt_accepted, bool)
        or not isinstance(result.abort_acknowledged, bool)
        or not isinstance(result.event_evidence, tuple)
        or isinstance(result.event_count, bool)
        or not isinstance(result.event_count, int)
        or (
            result.process_exit_code is not None
            and (
                isinstance(result.process_exit_code, bool)
                or not isinstance(result.process_exit_code, int)
            )
        )
    ):
        return False
    allowed_reasons = _RESULT_REASONS.get(result.execution_status)
    if allowed_reasons is None or result.reason not in allowed_reasons:
        return False
    if (
        result.event_count != len(result.event_evidence)
        or not 0 <= result.event_count <= MAX_PI_RPC_TURN_EVENTS
    ):
        return False
    for expected_sequence, item in enumerate(result.event_evidence, start=1):
        if not isinstance(item, str) or len(item) > _MAX_EVENT_EVIDENCE_CHARS:
            return False
        match = _EVENT_EVIDENCE.fullmatch(item)
        if (
            match is None
            or int(match.group("sequence")) != expected_sequence
            or match.group("event_type") not in _PI_EVENT_TYPES
        ):
            return False
    if result.execution_status == "completed":
        return (
            result.prompt_accepted is True
            and result.abort_acknowledged is False
            and result.process_exit_code == 0
        )
    return True


def _report_terminal(result: PiRpcTurnResult) -> tuple[str, str]:
    if result.execution_status == "completed":
        return ("blocked", "INDEPENDENT_VERIFICATION_REQUIRED")
    if result.execution_status == "interrupted":
        return ("cancelled", result.reason)
    return ("failed", result.reason)


def _render_report(
    packet: DispatchPacket,
    *,
    status: str,
    reason: str,
    execution_status: str = "not_started",
    evidence: tuple[str, ...] = (),
) -> str:
    evidence_lines = "\n".join(f"- `{item}`" for item in evidence) or "- (none)"
    return (
        f"## ExecutionReport: {packet.packet_id}\n\n"
        f"- **Status**: {status}\n"
        "- **Review Status**: draft\n"
        "- **Verification**: blocked\n"
        f"- **Execution Status**: {execution_status}\n"
        f"- **Reason**: {reason}\n"
        "- **Summary**: Provider boundary execution was mapped without granting "
        "verification authority.\n"
        "- **Changed Files**:\n"
        "- (none)\n"
        "- **Evidence**:\n"
        f"{evidence_lines}\n"
        "- **Risks**: Changed paths were not independently observed; downstream "
        "verification remains required.\n"
    )


def _ingest(
    store: DispatchPacketStore,
    packet: DispatchPacket,
    report_path: Path,
) -> WorkerResult:
    summary = store.ingest_report(packet.packet_dir, report_path)
    return WorkerResult(packet=packet, report_path=str(report_path), summary=summary)
