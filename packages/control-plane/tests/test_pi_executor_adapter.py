"""Contract tests for mapping Pi turn facts through the neutral executor seam."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from control_plane.agent_adapter import SubAgentObjective
from control_plane.decision_engine import Decision, DecisionMode
from control_plane.dispatch_packet import DispatchPacketStore
from control_plane.executor_adapter import ExecutorAdapterError, ExecutorInvocation
from control_plane.pi_executor_adapter import (
    create_pi_executor_adapter,
)
from control_plane.pi_rpc_adapter import OFFICIAL_PI_CLI_SHA256, PiRpcConfig
from control_plane.pi_rpc_turn import PiRpcTurnResult
from control_plane.project_contract import ProjectContract
from control_plane.worker import WorkerResult


EVENT_HASH = "pi:event:000001:agent_start:sha256:" + ("a" * 64)


def _rpc_config(tmp_path: Path) -> PiRpcConfig:
    return PiRpcConfig(
        command=("node", str(tmp_path / "cli.js")),
        lock_path=tmp_path / "package-lock.json",
        artifact_path=tmp_path / "cli.js",
        artifact_sha256=OFFICIAL_PI_CLI_SHA256,
        agent_dir=tmp_path / "agent-home",
        cwd=tmp_path,
        timeout_seconds=1.0,
    )


def _invocation(tmp_path: Path, *, dispatch_ready: bool = True, cancel: bool = False):
    runtime = tmp_path / "runtime"
    project = tmp_path / "project"
    project.mkdir()
    store = DispatchPacketStore(runtime_dir=runtime)
    contract = ProjectContract(project_id="pi-bridge-test", goal="exercise the bridge")
    decision = Decision(
        mode=DecisionMode.AUTO_EXECUTE,
        operation="synthetic",
        reason="bounded test",
        dispatch_allowed=dispatch_ready,
    )
    objective = SubAgentObjective(
        project_id=contract.project_id,
        project_root=str(project),
        text="raw-objective-must-not-enter-report",
        dispatch_ready=dispatch_ready,
    )
    packet = store.write_packet(
        contract=contract,
        project_root=project,
        requirement="bounded provider-neutral bridge",
        operation="synthetic",
        targets=[],
        decision=decision,
        objective=objective,
        dispatch_ready=dispatch_ready,
    )
    env_overrides = None
    if cancel:
        marker = runtime / "cancel.marker"
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text("cancel", encoding="utf-8")
        env_overrides = {"DEVFRAME_CANCEL_MARKER": str(marker.resolve())}
    invocation = ExecutorInvocation(
        runtime_dir=str(runtime),
        project_root=str(project),
        go_run_id="pi-bridge-run-1",
        agent=SimpleNamespace(packet_dir=packet.packet_dir),
        timeout_seconds=30,
        cwd=str(project),
        env_overrides=env_overrides,
        acp_command=None,
        team=None,
    )
    return invocation


def _runner_factory(
    result: PiRpcTurnResult,
    calls: list[tuple[str, bool]],
    configs: list[PiRpcConfig] | None = None,
):
    class FakeRunner:
        def __init__(self, config):
            assert isinstance(config, PiRpcConfig)
            if configs is not None:
                configs.append(config)

        def run_turn(self, message, *, cancel_event=None):
            calls.append((message, bool(cancel_event and cancel_event.is_set())))
            return result

    return FakeRunner


def test_completed_turn_maps_to_blocked_worker_result_pending_verification(tmp_path):
    calls: list[tuple[str, bool]] = []
    configs: list[PiRpcConfig] = []
    result = PiRpcTurnResult(
        execution_status="completed",
        reason="STOP",
        prompt_accepted=True,
        abort_acknowledged=False,
        event_count=1,
        event_evidence=(EVENT_HASH,),
        process_exit_code=0,
    )
    adapter = create_pi_executor_adapter(
        _rpc_config(tmp_path), runner_factory=_runner_factory(result, calls, configs)
    )

    worker_result = adapter.execute(_invocation(tmp_path))
    report = Path(worker_result.report_path).read_text(encoding="utf-8")

    assert isinstance(worker_result, WorkerResult)
    assert adapter.driver == "pi"
    assert adapter.protocol == "pi-jsonl-rpc-v1"
    assert worker_result.summary.status == "blocked"
    assert "blocked" in worker_result.summary.verification.lower()
    assert calls == [("raw-objective-must-not-enter-report", False)]
    assert configs[0].cwd == (tmp_path / "project").resolve()
    assert configs[0].timeout_seconds == 1.0
    assert EVENT_HASH in report
    assert "raw-objective-must-not-enter-report" not in report
    assert "accepted" not in report.lower()


def test_completed_stream_longer_than_64_events_remains_valid(tmp_path):
    calls: list[tuple[str, bool]] = []
    evidence = tuple(
        f"pi:event:{sequence:06d}:message_update:sha256:{'a' * 64}"
        for sequence in range(1, 129)
    )
    result = PiRpcTurnResult(
        execution_status="completed",
        reason="STOP",
        prompt_accepted=True,
        abort_acknowledged=False,
        event_count=len(evidence),
        event_evidence=evidence,
        process_exit_code=0,
    )
    adapter = create_pi_executor_adapter(
        _rpc_config(tmp_path), runner_factory=_runner_factory(result, calls)
    )

    worker_result = adapter.execute(_invocation(tmp_path))

    assert worker_result.summary.status == "blocked"
    assert calls == [("raw-objective-must-not-enter-report", False)]


def test_cancel_marker_is_forwarded_without_becoming_child_environment(tmp_path):
    calls: list[tuple[str, bool]] = []
    result = PiRpcTurnResult(
        execution_status="interrupted",
        reason="CANCELLED_BEFORE_START",
        prompt_accepted=False,
        abort_acknowledged=False,
        event_count=0,
        event_evidence=(),
        process_exit_code=None,
    )
    adapter = create_pi_executor_adapter(
        _rpc_config(tmp_path), runner_factory=_runner_factory(result, calls)
    )

    worker_result = adapter.execute(_invocation(tmp_path, cancel=True))

    assert worker_result.summary.status == "cancelled"
    assert calls == [("raw-objective-must-not-enter-report", True)]


def test_not_dispatch_ready_never_calls_turn_runner(tmp_path):
    calls: list[tuple[str, bool]] = []
    result = PiRpcTurnResult(
        execution_status="completed",
        reason="STOP",
        prompt_accepted=True,
        abort_acknowledged=False,
        event_count=0,
        event_evidence=(),
        process_exit_code=0,
    )
    adapter = create_pi_executor_adapter(
        _rpc_config(tmp_path), runner_factory=_runner_factory(result, calls)
    )

    worker_result = adapter.execute(_invocation(tmp_path, dispatch_ready=False))

    assert worker_result.summary.status == "blocked"
    assert calls == []


@pytest.mark.parametrize(
    "raw_value",
    [
        "raw-event-must-not-enter-report",
        "pi:event:000001:unknown_event:sha256:" + ("b" * 64),
        "pi:event:000001:" + ("raw_event_secret_" * 100) + ":sha256:" + ("c" * 64),
    ],
)
def test_invalid_turn_evidence_fails_closed_without_copying_raw_value(
    tmp_path,
    raw_value,
):
    calls: list[tuple[str, bool]] = []
    result = PiRpcTurnResult(
        execution_status="completed",
        reason="STOP",
        prompt_accepted=True,
        abort_acknowledged=False,
        event_count=1,
        event_evidence=(raw_value,),
        process_exit_code=0,
    )
    adapter = create_pi_executor_adapter(
        _rpc_config(tmp_path), runner_factory=_runner_factory(result, calls)
    )

    worker_result = adapter.execute(_invocation(tmp_path))
    report = Path(worker_result.report_path).read_text(encoding="utf-8")

    assert worker_result.summary.status == "failed"
    assert raw_value not in report


def test_runner_failure_is_sanitized_into_failed_report(tmp_path):
    raw_value = "raw-runner-error-must-not-enter-report"

    class FailingRunner:
        def __init__(self, config):
            assert isinstance(config, PiRpcConfig)

        def run_turn(self, message, *, cancel_event=None):
            raise RuntimeError(raw_value)

    adapter = create_pi_executor_adapter(_rpc_config(tmp_path), runner_factory=FailingRunner)

    worker_result = adapter.execute(_invocation(tmp_path))
    report = Path(worker_result.report_path).read_text(encoding="utf-8")

    assert worker_result.summary.status == "failed"
    assert "PI_BOUNDARY_FAILED" in report
    assert raw_value not in report


@pytest.mark.parametrize(
    "field,value",
    [
        ("prompt_accepted", 1),
        ("abort_acknowledged", 0),
        ("event_count", True),
        ("event_evidence", None),
        ("process_exit_code", False),
    ],
)
def test_malformed_turn_result_fails_closed(tmp_path, field, value):
    calls: list[tuple[str, bool]] = []
    values = {
        "execution_status": "completed",
        "reason": "STOP",
        "prompt_accepted": True,
        "abort_acknowledged": False,
        "event_count": 1,
        "event_evidence": (EVENT_HASH,),
        "process_exit_code": 0,
    }
    values[field] = value
    result = PiRpcTurnResult(**values)
    adapter = create_pi_executor_adapter(
        _rpc_config(tmp_path), runner_factory=_runner_factory(result, calls)
    )

    worker_result = adapter.execute(_invocation(tmp_path))

    assert worker_result.summary.status == "failed"


def test_cancel_marker_outside_runtime_fails_before_runner(tmp_path):
    calls: list[tuple[str, bool]] = []
    result = PiRpcTurnResult(
        execution_status="interrupted",
        reason="CANCELLED_BEFORE_START",
        prompt_accepted=False,
        abort_acknowledged=False,
        event_count=0,
        event_evidence=(),
        process_exit_code=None,
    )
    adapter = create_pi_executor_adapter(
        _rpc_config(tmp_path), runner_factory=_runner_factory(result, calls)
    )
    invocation = _invocation(tmp_path)
    outside_marker = tmp_path / "outside.marker"
    outside_marker.write_text("cancel", encoding="utf-8")
    invocation = ExecutorInvocation(
        **{
            **invocation.__dict__,
            "env_overrides": {"DEVFRAME_CANCEL_MARKER": str(outside_marker.resolve())},
        }
    )

    worker_result = adapter.execute(invocation)

    assert worker_result.summary.status == "failed"
    assert calls == []


def test_real_turn_runner_honours_pre_cancel_without_loading_runtime(tmp_path):
    adapter = create_pi_executor_adapter(_rpc_config(tmp_path))

    worker_result = adapter.execute(_invocation(tmp_path, cancel=True))
    report = Path(worker_result.report_path).read_text(encoding="utf-8")

    assert worker_result.summary.status == "cancelled"
    assert "CANCELLED_BEFORE_START" in report
    assert "raw-objective-must-not-enter-report" not in report


def test_invocation_cannot_expand_timeout_or_escape_project_root(tmp_path):
    calls: list[tuple[str, bool]] = []
    configs: list[PiRpcConfig] = []
    result = PiRpcTurnResult(
        execution_status="interrupted",
        reason="CANCELLED_BEFORE_START",
        prompt_accepted=False,
        abort_acknowledged=False,
        event_count=0,
        event_evidence=(),
        process_exit_code=None,
    )
    base_config = _rpc_config(tmp_path)
    adapter = create_pi_executor_adapter(
        base_config,
        runner_factory=_runner_factory(result, calls, configs),
    )
    invocation = _invocation(tmp_path)
    invocation = ExecutorInvocation(
        **{
            **invocation.__dict__,
            "timeout_seconds": 30,
            "cwd": str(tmp_path.resolve()),
        }
    )

    worker_result = adapter.execute(invocation)

    assert worker_result.summary.status == "failed"
    assert calls == []
    assert configs == []


def test_packet_reference_must_stay_inside_matching_runtime(tmp_path):
    calls: list[tuple[str, bool]] = []
    result = PiRpcTurnResult(
        execution_status="completed",
        reason="STOP",
        prompt_accepted=True,
        abort_acknowledged=False,
        event_count=1,
        event_evidence=(EVENT_HASH,),
        process_exit_code=0,
    )
    adapter = create_pi_executor_adapter(
        _rpc_config(tmp_path), runner_factory=_runner_factory(result, calls)
    )
    invocation = _invocation(tmp_path)
    other_runtime = tmp_path / "other-runtime"
    other_runtime.mkdir()
    invocation = ExecutorInvocation(
        **{**invocation.__dict__, "runtime_dir": str(other_runtime)}
    )

    with pytest.raises(ExecutorAdapterError, match="bound to the invocation"):
        adapter.execute(invocation)

    assert calls == []
