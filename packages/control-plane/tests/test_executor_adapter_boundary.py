"""Real-file binding checks for the provider-neutral executor seam."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import fields, replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from control_plane import dispatch_packet as dispatch_packet_module
from control_plane import executor_adapter as executor_adapter_module
from control_plane.agent_adapter import SubAgentObjective
from control_plane.decision_engine import Decision, DecisionMode
from control_plane.dispatch_packet import DispatchPacketStore
from control_plane.executor_adapter import (
    ExecutorAdapter,
    ExecutorAdapterError,
    ExecutorAdapterRegistry,
    ExecutorInvocation,
    define_executor_adapter,
)
from control_plane.go_dispatch import GoAgentDispatch, _run_agent_in_place
from control_plane.project_contract import ProjectContract
from control_plane import WorkerResult


def test_executor_adapter_is_a_lazy_public_package_export() -> None:
    probe = (
        "import sys, control_plane; "
        "assert 'control_plane.executor_adapter' not in sys.modules; "
        "assert 'control_plane.worker' not in sys.modules; "
        "from control_plane import (ExecutorAdapter, ExecutorAdapterError, "
        "ExecutorAdapterRegistry, ExecutorInvocation, WorkerResult, "
        "define_executor_adapter); "
        "assert control_plane.__all__ == ('ExecutorAdapter', "
        "'ExecutorAdapterError', 'ExecutorAdapterRegistry', 'ExecutorInvocation', "
        "'define_executor_adapter', 'WorkerResult'); "
        "assert ExecutorAdapter.__module__ == 'control_plane.executor_adapter'; "
        "assert ExecutorAdapterError.__module__ == 'control_plane.executor_adapter'; "
        "assert ExecutorAdapterRegistry.__module__ == 'control_plane.executor_adapter'; "
        "assert ExecutorInvocation.__module__ == 'control_plane.executor_adapter'; "
        "assert define_executor_adapter.__module__ == 'control_plane.executor_adapter'; "
        "assert WorkerResult.__module__ == 'control_plane.worker'"
    )

    completed = subprocess.run(
        [sys.executable, "-c", probe],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
        env={
            **os.environ,
            "PYTHONPATH": os.pathsep.join(
                filter(
                    None,
                    (
                        str(Path(__file__).parents[1]),
                        os.environ.get("PYTHONPATH", ""),
                    ),
                )
            ),
        },
    )

    assert completed.returncode == 0, completed.stderr


def _bound_fixture(
    tmp_path: Path,
    *,
    runtime_dir: Path | None = None,
    project_root: Path | None = None,
) -> tuple[ExecutorInvocation, WorkerResult]:
    runtime_dir = runtime_dir or tmp_path / "runtime"
    project_root = project_root or tmp_path / "project"
    project_root.mkdir(parents=True, exist_ok=True)
    store = DispatchPacketStore(runtime_dir=runtime_dir)
    contract = ProjectContract(project_id="demo-project", goal="exercise the seam")
    decision = Decision(
        mode=DecisionMode.AUTO_EXECUTE,
        operation="synthetic",
        reason="bounded test",
        dispatch_allowed=True,
    )
    objective = SubAgentObjective(
        project_id=contract.project_id,
        project_root=str(project_root.resolve()),
        text="make one bounded change",
        dispatch_ready=True,
    )
    packet = store.write_packet(
        contract=contract,
        project_root=project_root,
        requirement="make one bounded change",
        operation="synthetic",
        targets=["allowed.txt"],
        decision=decision,
        objective=objective,
        dispatch_ready=True,
    )
    packet_dir = Path(packet.packet_dir)
    report_path = packet_dir / "ExecutionReport.md"
    report_path.write_text(
        "## ExecutionReport\n\n"
        "- **Status**: pass\n"
        "- **Review Status**: draft\n"
        "- **Changed Files**:\n"
        "- `allowed.txt`\n"
        "- **Evidence**: provider-neutral boundary probe\n",
        encoding="utf-8",
    )
    summary = store.ingest_report(packet.packet_dir, report_path)
    result = WorkerResult(
        packet=packet,
        report_path=str(report_path.resolve()),
        summary=summary,
    )
    invocation = ExecutorInvocation(
        runtime_dir=str(runtime_dir.resolve()),
        project_root=str(project_root.resolve()),
        go_run_id="go-1",
        agent=SimpleNamespace(packet_dir=str(packet_dir.resolve())),
        timeout_seconds=30,
        cwd=None,
        env_overrides=None,
        acp_command=None,
        team=None,
    )
    return invocation, result


def _adapter(result: WorkerResult) -> ExecutorAdapter:
    return ExecutorAdapter(
        driver="test",
        adapter_id="test-boundary",
        protocol="process-v1",
        _execute=lambda _invocation: result,
    )


def test_define_executor_adapter_uses_the_bound_public_callback(tmp_path: Path) -> None:
    invocation, result = _bound_fixture(tmp_path)
    received: list[ExecutorInvocation] = []

    def execute(candidate: ExecutorInvocation) -> WorkerResult:
        received.append(candidate)
        return result

    adapter = define_executor_adapter(
        driver="test",
        adapter_id="test-public-factory",
        protocol="process-v1",
        execute=execute,
    )

    bound = adapter.execute(invocation)

    assert received == [invocation]
    assert bound is not result
    assert bound.packet.packet_id == result.packet.packet_id
    assert bound.summary == result.summary
    assert bound.report_path == result.report_path


def test_executor_adapter_accepts_result_bound_to_real_packet_and_report(tmp_path: Path) -> None:
    invocation, result = _bound_fixture(tmp_path)

    bound = _adapter(result).execute(invocation)

    expected_packet = json.loads(
        (Path(invocation.agent.packet_dir) / "packet.json").read_text(encoding="utf-8")
    )
    assert bound.summary == result.summary
    assert bound.report_path == result.report_path
    if "run_manifest" in expected_packet:
        assert bound.packet.run_manifest == expected_packet["run_manifest"]
    else:
        assert not hasattr(bound.packet, "run_manifest")
        assert not hasattr(bound.summary, "final_candidate_identity")


def test_executor_adapter_missing_packet_validator_fails_before_callback(
    tmp_path: Path,
    monkeypatch,
) -> None:
    if not hasattr(dispatch_packet_module, "_validate_dispatch_packet_payload"):
        pytest.skip("legacy packet generation has no manifest validator")
    invocation, result = _bound_fixture(tmp_path)
    callback_calls: list[str] = []

    def execute(_invocation: ExecutorInvocation) -> WorkerResult:
        callback_calls.append("called")
        return result

    monkeypatch.delattr(
        dispatch_packet_module,
        "_validate_dispatch_packet_payload",
    )
    adapter = ExecutorAdapter(
        driver="test",
        adapter_id="test-boundary",
        protocol="process-v1",
        _execute=execute,
    )

    with pytest.raises(ExecutorAdapterError, match="bound to the invocation") as exc_info:
        adapter.execute(invocation)

    assert callback_calls == []
    assert exc_info.value.__cause__ is None
    assert exc_info.value.__context__ is None


def test_executor_adapter_rejects_validator_removed_during_callback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    if not hasattr(dispatch_packet_module, "_validate_dispatch_packet_payload"):
        pytest.skip("legacy packet generation has no manifest validator")
    invocation, result = _bound_fixture(tmp_path)
    callback_calls: list[str] = []

    def execute(_invocation: ExecutorInvocation) -> WorkerResult:
        callback_calls.append("called")
        monkeypatch.delattr(
            dispatch_packet_module,
            "_validate_dispatch_packet_payload",
        )
        return result

    adapter = ExecutorAdapter(
        driver="test",
        adapter_id="test-boundary",
        protocol="process-v1",
        _execute=execute,
    )

    with pytest.raises(ExecutorAdapterError, match="bound to the invocation"):
        adapter.execute(invocation)

    assert callback_calls == ["called"]


def test_executor_adapter_rejects_unknown_contract_fingerprint_before_callback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    invocation, result = _bound_fixture(tmp_path)
    packet_type = type(result.packet)
    original_field_names = executor_adapter_module._contract_field_names
    callback_calls: list[str] = []

    def hybrid_field_names(model: type[object]) -> tuple[str, ...]:
        names = original_field_names(model)
        if model is packet_type:
            return names + ("unexpected_authority",)
        return names

    monkeypatch.setattr(
        executor_adapter_module,
        "_contract_field_names",
        hybrid_field_names,
    )
    adapter = ExecutorAdapter(
        driver="test",
        adapter_id="test-boundary",
        protocol="process-v1",
        _execute=lambda _invocation: (callback_calls.append("called") or result),
    )

    with pytest.raises(ExecutorAdapterError, match="bound to the invocation"):
        adapter.execute(invocation)

    assert callback_calls == []


def test_executor_adapter_rejects_foreign_report_path(tmp_path: Path) -> None:
    invocation, result = _bound_fixture(tmp_path)
    foreign_report = tmp_path / "foreign" / "ExecutionReport.md"
    foreign_report.parent.mkdir()
    foreign_report.write_text("- **Status**: pass\n", encoding="utf-8")
    forged = replace(
        result,
        report_path=str(foreign_report.resolve()),
        summary=replace(result.summary, report_path=str(foreign_report.resolve())),
    )

    with pytest.raises(ExecutorAdapterError, match="bound to the invocation") as exc_info:
        _adapter(forged).execute(invocation)

    assert exc_info.value.__cause__ is None
    assert exc_info.value.__context__ is None


@pytest.mark.parametrize("remote_path", [r"\\server\share\report.md", r"\\?\C:\report.md"])
def test_executor_adapter_rejects_remote_report_before_filesystem_access(
    tmp_path: Path,
    remote_path: str,
) -> None:
    invocation, result = _bound_fixture(tmp_path)
    forged = replace(
        result,
        report_path=remote_path,
        summary=replace(result.summary, report_path=remote_path),
    )

    with pytest.raises(ExecutorAdapterError, match="bound to the invocation"):
        _adapter(forged).execute(invocation)


def test_executor_adapter_rejects_packet_identity_mismatch(tmp_path: Path) -> None:
    invocation, result = _bound_fixture(tmp_path)
    forged = replace(
        result,
        packet=replace(result.packet, packet_id="packet-2"),
        summary=replace(result.summary, packet_id="packet-2"),
    )

    with pytest.raises(ExecutorAdapterError, match="bound to the invocation"):
        _adapter(forged).execute(invocation)


def test_executor_adapter_rejects_project_identity_mismatch(tmp_path: Path) -> None:
    invocation, result = _bound_fixture(tmp_path)
    other_project = tmp_path / "other-project"
    other_project.mkdir()
    forged = replace(result, packet=replace(result.packet, project_root=str(other_project)))

    with pytest.raises(ExecutorAdapterError, match="bound to the invocation"):
        _adapter(forged).execute(invocation)


def test_executor_adapter_rejects_forged_summary_truth(tmp_path: Path) -> None:
    invocation, result = _bound_fixture(tmp_path)
    forged = replace(
        result,
        summary=replace(
            result.summary,
            status="passed",
            changed_files=["forged.txt"],
            verification="passed",
        ),
    )

    with pytest.raises(ExecutorAdapterError, match="bound to the invocation"):
        _adapter(forged).execute(invocation)


def test_executor_adapter_rejects_forged_packet_payload(tmp_path: Path) -> None:
    invocation, result = _bound_fixture(tmp_path)
    forged = replace(result, packet=replace(result.packet, targets=["forged.txt"]))

    with pytest.raises(ExecutorAdapterError, match="bound to the invocation"):
        _adapter(forged).execute(invocation)


def test_executor_adapter_returns_canonical_run_manifest(tmp_path: Path) -> None:
    invocation, result = _bound_fixture(tmp_path)
    if "run_manifest" not in {field.name for field in fields(type(result.packet))}:
        pytest.skip("legacy packet generation has no run manifest")
    forged = replace(
        result,
        packet=replace(result.packet, run_manifest={"status": "forged"}),
    )

    bound = _adapter(forged).execute(invocation)

    expected_packet = json.loads(
        (Path(invocation.agent.packet_dir) / "packet.json").read_text(encoding="utf-8")
    )
    assert bound.packet.run_manifest == expected_packet["run_manifest"]
    assert bound is not forged


@pytest.mark.parametrize(
    ("field_name", "value"),
    [("task_id", "forged-task"), ("status", "deferred")],
)
def test_executor_adapter_rejects_task_spec_identity_mismatch_before_callback(
    tmp_path: Path,
    field_name: str,
    value: str,
) -> None:
    invocation, result = _bound_fixture(tmp_path)
    packet_path = Path(invocation.agent.packet_dir) / "packet.json"
    payload = json.loads(packet_path.read_text(encoding="utf-8"))
    payload["task_spec"][field_name] = value
    packet_path.write_text(json.dumps(payload), encoding="utf-8")
    callback_calls: list[str] = []
    adapter = ExecutorAdapter(
        driver="test",
        adapter_id="test-boundary",
        protocol="process-v1",
        _execute=lambda _invocation: (callback_calls.append("called") or result),
    )

    with pytest.raises(ExecutorAdapterError, match="bound to the invocation"):
        adapter.execute(invocation)

    assert callback_calls == []


def test_executor_adapter_redacts_malformed_packet_error(tmp_path: Path) -> None:
    invocation, result = _bound_fixture(tmp_path)
    raw_marker = "RAW_PACKET_MARKER"
    packet_path = Path(invocation.agent.packet_dir) / "packet.json"
    packet_path.write_text(f'{{"{raw_marker}"', encoding="utf-8")

    with pytest.raises(ExecutorAdapterError) as captured:
        _adapter(result).execute(invocation)

    assert str(captured.value) == "executor adapter result is not bound to the invocation"
    assert captured.value.__cause__ is None
    assert raw_marker not in repr(captured.value)


def test_executor_adapter_sanitizes_callback_failure_on_go_production_path(
    tmp_path: Path,
) -> None:
    invocation, _result = _bound_fixture(tmp_path)
    raw_marker = "SECRET_ADAPTER_RUNTIME_PATH"
    packet_root = Path(invocation.agent.packet_dir)
    agent = GoAgentDispatch(
        agent_id="agent-1",
        shard_index=0,
        shard_count=1,
        targets=["allowed.txt"],
        target_bytes=0,
        packet_dir=str(packet_root),
        task_spec_path=str(packet_root / "TASKSPEC.md"),
        worker_command=[],
    )

    def fail(_invocation: ExecutorInvocation) -> WorkerResult:
        raise RuntimeError(raw_marker)

    adapter = ExecutorAdapter(
        driver="test",
        adapter_id="test-sanitized-failure",
        protocol="process-v1",
        _execute=fail,
    )

    _run_agent_in_place(
        invocation.runtime_dir,
        invocation.project_root,
        invocation.go_run_id,
        agent,
        invocation.timeout_seconds,
        None,
        adapter,
    )

    error_text = (packet_root / "go-agent-error.txt").read_text(encoding="utf-8")
    assert agent.status == "failed"
    assert agent.worker_status == "failed"
    assert error_text == "ExecutorAdapterError: executor adapter execution failed\n"
    assert raw_marker not in error_text


def test_executor_adapter_does_not_retain_callback_exception(tmp_path: Path) -> None:
    invocation, _result = _bound_fixture(tmp_path)
    raw_marker = "SECRET_ADAPTER_EXCEPTION_OBJECT"

    def fail(_invocation: ExecutorInvocation) -> WorkerResult:
        raise RuntimeError(raw_marker)

    adapter = ExecutorAdapter(
        driver="test",
        adapter_id="test-detached-failure",
        protocol="process-v1",
        _execute=fail,
    )

    with pytest.raises(ExecutorAdapterError) as captured:
        adapter.execute(invocation)

    assert str(captured.value) == "executor adapter execution failed"
    assert captured.value.__cause__ is None
    assert captured.value.__context__ is None
    assert raw_marker not in repr(captured.value)


def test_executor_adapter_preflights_packet_before_callback(tmp_path: Path) -> None:
    invocation, result = _bound_fixture(tmp_path)
    packet_path = Path(invocation.agent.packet_dir) / "packet.json"
    payload = json.loads(packet_path.read_text(encoding="utf-8"))
    payload["targets"] = "allowed.txt"
    packet_path.write_text(json.dumps(payload), encoding="utf-8")
    forged = replace(result, packet=replace(result.packet, targets="allowed.txt"))
    calls: list[str] = []
    adapter = ExecutorAdapter(
        driver="test",
        adapter_id="test-preflight",
        protocol="process-v1",
        _execute=lambda _invocation: (calls.append("called") or forged),
    )

    with pytest.raises(ExecutorAdapterError, match="bound to the invocation"):
        adapter.execute(invocation)

    assert calls == []


def test_executor_adapter_rejects_path_resolved_to_remote_before_callback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    invocation, result = _bound_fixture(tmp_path)
    runtime_path = Path(invocation.runtime_dir)
    original_resolve = Path.resolve
    calls: list[str] = []

    def resolve_to_remote(path: Path, *args: object, **kwargs: object) -> Path:
        if path == runtime_path:
            return Path(r"\\server\share\runtime")
        return original_resolve(path, *args, **kwargs)

    monkeypatch.setattr(Path, "resolve", resolve_to_remote)
    adapter = ExecutorAdapter(
        driver="test",
        adapter_id="test-resolved-remote",
        protocol="process-v1",
        _execute=lambda _invocation: (calls.append("called") or result),
    )

    with pytest.raises(ExecutorAdapterError, match="bound to the invocation"):
        adapter.execute(invocation)

    assert calls == []


def test_executor_adapter_rejects_oversized_packet_before_callback(tmp_path: Path) -> None:
    invocation, result = _bound_fixture(tmp_path)
    packet_path = Path(invocation.agent.packet_dir) / "packet.json"
    packet_path.write_bytes(b'{"padding":"' + (b"x" * 1_048_576) + b'"}')
    calls: list[str] = []
    adapter = ExecutorAdapter(
        driver="test",
        adapter_id="test-oversized",
        protocol="process-v1",
        _execute=lambda _invocation: (calls.append("called") or result),
    )

    with pytest.raises(ExecutorAdapterError, match="bound to the invocation"):
        adapter.execute(invocation)

    assert calls == []


def test_executor_adapter_rejects_hardlinked_packet(tmp_path: Path) -> None:
    invocation, result = _bound_fixture(tmp_path)
    packet_path = Path(invocation.agent.packet_dir) / "packet.json"
    source = tmp_path / "packet-source.json"
    source.write_bytes(packet_path.read_bytes())
    packet_path.unlink()
    os.link(source, packet_path)

    with pytest.raises(ExecutorAdapterError, match="bound to the invocation"):
        _adapter(result).execute(invocation)


def test_executor_adapter_rejects_malformed_canonical_summary(tmp_path: Path) -> None:
    invocation, result = _bound_fixture(tmp_path)
    summary_path = (
        Path(invocation.runtime_dir)
        / "rdgoal-reports"
        / result.packet.project_id
        / result.packet.packet_id
        / "execution-summary.json"
    )
    payload = json.loads(summary_path.read_text(encoding="utf-8"))
    payload["status"] = []
    summary_path.write_text(json.dumps(payload), encoding="utf-8")
    forged = replace(result, summary=replace(result.summary, status=[]))

    with pytest.raises(ExecutorAdapterError, match="bound to the invocation"):
        _adapter(forged).execute(invocation)


def test_executor_adapter_rejects_packet_redirected_during_callback(tmp_path: Path) -> None:
    runtime_dir = tmp_path / "runtime"
    project_root = tmp_path / "project"
    invocation, _result = _bound_fixture(
        tmp_path / "first",
        runtime_dir=runtime_dir,
        project_root=project_root,
    )
    original_packet_dir = invocation.agent.packet_dir
    redirected_invocation, redirected_result = _bound_fixture(
        tmp_path / "second",
        runtime_dir=runtime_dir,
        project_root=project_root,
    )

    def redirect(_invocation: ExecutorInvocation) -> WorkerResult:
        invocation.agent.packet_dir = redirected_invocation.agent.packet_dir
        return redirected_result

    adapter = ExecutorAdapter(
        driver="test",
        adapter_id="test-redirect",
        protocol="process-v1",
        _execute=redirect,
    )

    with pytest.raises(ExecutorAdapterError, match="bound to the invocation"):
        adapter.execute(invocation)

    assert invocation.agent.packet_dir == original_packet_dir


def test_executor_adapter_rejects_invocation_subclass(tmp_path: Path) -> None:
    invocation, result = _bound_fixture(tmp_path)

    class ForgedInvocation(ExecutorInvocation):
        pass

    forged = ForgedInvocation(**invocation.__dict__)

    with pytest.raises(ExecutorAdapterError, match="bound to the invocation"):
        _adapter(result).execute(forged)


def test_executor_adapter_rejects_worker_result_subclass(tmp_path: Path) -> None:
    invocation, result = _bound_fixture(tmp_path)

    class ForgedWorkerResult(WorkerResult):
        pass

    forged = ForgedWorkerResult(
        packet=result.packet,
        report_path=result.report_path,
        summary=result.summary,
    )

    with pytest.raises(ExecutorAdapterError, match="return WorkerResult"):
        _adapter(forged).execute(invocation)


def test_executor_registry_rejects_adapter_subclass_that_bypasses_binding(
    tmp_path: Path,
) -> None:
    invocation, result = _bound_fixture(tmp_path)
    foreign_report = tmp_path / "foreign" / "ExecutionReport.md"
    foreign_report.parent.mkdir()
    foreign_report.write_text("- **Status**: pass\n", encoding="utf-8")
    forged_result = replace(
        result,
        report_path=str(foreign_report.resolve()),
        summary=replace(result.summary, report_path=str(foreign_report.resolve())),
    )

    class BypassAdapter(ExecutorAdapter):
        def execute(self, _invocation: ExecutorInvocation) -> WorkerResult:
            return forged_result

    registry = ExecutorAdapterRegistry()
    bypass = BypassAdapter(
        driver="test",
        adapter_id="test-bypass",
        protocol="process-v1",
        _execute=lambda _invocation: result,
    )

    with pytest.raises(ExecutorAdapterError, match="entries only"):
        registry.register(bypass)
        registry.resolve("test").execute(invocation)
