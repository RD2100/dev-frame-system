"""Production-path tests for the opt-in Pi executor driver."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from control_plane.cli import main as devframe_cli_main
from control_plane.go_dispatch import (
    execute_go_run,
    render_go_dispatch_text,
    run_go_dispatch,
)
from control_plane.pi_rpc_adapter import PiRpcAdapter
from control_plane.pi_executor_adapter import (
    PiExecutorAdapterError,
    _environment_config,
)
from control_plane.pi_rpc_turn import PiRpcTurnResult


def _project(tmp_path: Path) -> Path:
    project = tmp_path / "project"
    project.mkdir()
    (project / "target.py").write_text("value = 1\n", encoding="utf-8")
    return project


def test_pi_driver_without_runtime_fails_closed_without_worker_command(
    tmp_path,
    monkeypatch,
):
    monkeypatch.delenv("DEVFRAME_PI_RUNTIME", raising=False)
    monkeypatch.delenv("DEVFRAME_PI_NODE", raising=False)
    monkeypatch.setattr(
        "control_plane.go_dispatch.resolve_model_provider",
        lambda _value: (_ for _ in ()).throw(AssertionError("provider resolved")),
    )

    result = run_go_dispatch(
        _project(tmp_path),
        "bounded Pi route without local runtime",
        runtime_dir=tmp_path / "runtime",
        agents=1,
        targets=["target.py"],
        execute=True,
        driver="pi",
    )

    assert result.status == "failed"
    assert result.model_provider == ""
    assert result.agents[0].worker_command == []
    assert result.agents[0].executor_adapter_id == "pi-rpc-turn"
    assert result.agents[0].worker_status == "failed"
    report = Path(result.agents[0].report_path).read_text(encoding="utf-8")
    assert "PI_RUNTIME_UNAVAILABLE" in report
    assert "DEVFRAME_PI_RUNTIME" not in report


def test_pi_driver_pre_cancel_uses_production_registry_without_starting_pi(
    tmp_path,
    monkeypatch,
):
    install_root = tmp_path / "pi-install"
    install_root.mkdir()
    monkeypatch.setenv("DEVFRAME_PI_RUNTIME", str(install_root.resolve()))
    monkeypatch.setenv("DEVFRAME_PI_NODE", str(Path(sys.executable).resolve()))
    monkeypatch.setattr(
        "control_plane.go_dispatch.resolve_model_provider",
        lambda _value: (_ for _ in ()).throw(AssertionError("provider resolved")),
    )
    monkeypatch.setattr(
        PiRpcAdapter,
        "prepare_runtime",
        lambda _self: (_ for _ in ()).throw(AssertionError("Pi runtime started")),
    )
    runtime = tmp_path / "runtime"
    prepared = run_go_dispatch(
        _project(tmp_path),
        "raw-production-objective-must-not-enter-report",
        runtime_dir=runtime,
        agents=1,
        targets=["target.py"],
        execute=False,
        driver="pi",
    )
    cancel_marker = runtime / "cancel-requested.json"
    cancel_marker.write_text('{"requested":true}', encoding="utf-8")

    result = execute_go_run(
        runtime,
        prepared.go_run_id,
        cancel_marker=cancel_marker,
    )

    assert result.status == "cancelled"
    assert result.model_provider == ""
    assert result.agents[0].worker_command == []
    assert result.agents[0].executor_adapter_id == "pi-rpc-turn"
    assert result.agents[0].executor_protocol == "pi-jsonl-rpc-v1"
    assert result.agents[0].worker_status == "cancelled"
    rendered = render_go_dispatch_text(result)
    assert "executor driver=pi" in rendered
    assert "rdgoal worker" not in rendered
    assert "opencode" not in rendered.lower()
    report = Path(result.agents[0].report_path).read_text(encoding="utf-8")
    assert "CANCELLED_BEFORE_START" in report
    assert "raw-production-objective-must-not-enter-report" not in report


def test_pi_driver_rejects_outside_cancel_marker_without_masking_failure(
    tmp_path,
    monkeypatch,
):
    install_root = tmp_path / "pi-install"
    install_root.mkdir()
    monkeypatch.setenv("DEVFRAME_PI_RUNTIME", str(install_root.resolve()))
    monkeypatch.setenv("DEVFRAME_PI_NODE", str(Path(sys.executable).resolve()))
    runtime = tmp_path / "runtime"
    prepared = run_go_dispatch(
        _project(tmp_path),
        "outside marker must fail closed",
        runtime_dir=runtime,
        agents=1,
        targets=["target.py"],
        execute=False,
        driver="pi",
    )
    outside_marker = tmp_path / "outside-cancel.json"
    outside_marker.write_text('{"requested":true}', encoding="utf-8")

    result = execute_go_run(
        runtime,
        prepared.go_run_id,
        cancel_marker=outside_marker,
    )

    assert result.status == "failed"
    assert result.agents[0].status == "failed"
    assert result.agents[0].worker_status == "failed"
    report = Path(result.agents[0].report_path).read_text(encoding="utf-8")
    assert "PI_BOUNDARY_FAILED" in report


@pytest.mark.skipif(shutil.which("git") is None, reason="git not available")
def test_pi_driver_pre_cancel_supports_governed_worktree_isolation(
    tmp_path,
    monkeypatch,
):
    project = _project(tmp_path)
    subprocess.run(["git", "-C", str(project), "init", "-q"], check=True)
    subprocess.run(
        ["git", "-C", str(project), "config", "user.email", "pi-test@example.invalid"],
        check=True,
    )
    subprocess.run(
        ["git", "-C", str(project), "config", "user.name", "Pi Test"],
        check=True,
    )
    subprocess.run(["git", "-C", str(project), "add", "."], check=True)
    subprocess.run(
        ["git", "-C", str(project), "commit", "-q", "-m", "fixture"],
        check=True,
    )
    install_root = tmp_path / "pi-install"
    install_root.mkdir()
    monkeypatch.setenv("DEVFRAME_PI_RUNTIME", str(install_root.resolve()))
    monkeypatch.setenv("DEVFRAME_PI_NODE", str(Path(sys.executable).resolve()))
    monkeypatch.setattr(
        PiRpcAdapter,
        "prepare_runtime",
        lambda _self: (_ for _ in ()).throw(AssertionError("Pi runtime started")),
    )
    runtime = tmp_path / "runtime"
    prepared = run_go_dispatch(
        project,
        "isolated pre-cancel",
        runtime_dir=runtime,
        agents=1,
        targets=["target.py"],
        execute=False,
        isolate=True,
        driver="pi",
    )
    cancel_marker = runtime / "cancel-requested.json"
    cancel_marker.write_text('{"requested":true}', encoding="utf-8")

    result = execute_go_run(
        runtime,
        prepared.go_run_id,
        cancel_marker=cancel_marker,
    )

    agent = result.agents[0]
    assert result.status == "cancelled"
    assert agent.worker_status == "cancelled"
    assert agent.isolated is True
    assert agent.worktree_path
    assert Path(agent.worktree_path).is_dir()
    report = Path(agent.report_path).read_text(encoding="utf-8")
    assert "CANCELLED_BEFORE_START" in report


def test_go_cli_accepts_pi_driver_without_constructing_command_provider(
    tmp_path,
    monkeypatch,
    capsys,
):
    project = _project(tmp_path)
    runtime = tmp_path / "runtime"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "devframe",
            "go",
            str(project),
            "prepare through Pi",
            "--runtime-dir",
            str(runtime),
            "--target",
            "target.py",
            "--driver",
            "pi",
        ],
    )

    assert devframe_cli_main() == 0

    output = capsys.readouterr().out
    metadata_path = next((runtime / "go-runs").glob("*/go-run.json"))
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    assert metadata["driver"] == "pi"
    assert metadata["model_provider"] == ""
    assert metadata["agents"][0]["worker_command"] == []
    assert "executor driver=pi" in output
    assert "opencode" not in output.lower()


def test_code_cli_renders_pi_as_provider_neutral_executor(
    tmp_path,
    monkeypatch,
    capsys,
):
    project = _project(tmp_path)
    runtime = tmp_path / "runtime"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "devframe",
            "code",
            "prepare through Pi",
            "--project",
            str(project),
            "--runtime-dir",
            str(runtime),
            "--target",
            "target.py",
            "--driver",
            "pi",
        ],
    )

    assert devframe_cli_main() == 0

    output = capsys.readouterr().out
    metadata_path = next((runtime / "go-runs").glob("*/go-run.json"))
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    assert metadata["driver"] == "pi"
    assert "Tool shape   : provider-neutral local executor CLI" in output
    assert "OpenCode-first" not in output
    assert "rdgoal worker" not in output
    assert "opencode" not in output.lower()


@pytest.mark.parametrize("entrypoint", ["go", "code"])
def test_pi_cli_preview_does_not_construct_command_worker(
    tmp_path,
    monkeypatch,
    capsys,
    entrypoint,
):
    project = _project(tmp_path)
    runtime = tmp_path / "runtime"
    if entrypoint == "go":
        argv = ["devframe", "go", str(project), "preview Pi"]
    else:
        argv = ["devframe", "code", "preview Pi", "--project", str(project)]
    argv.extend(
        [
            "--runtime-dir",
            str(runtime),
            "--target",
            "target.py",
            "--driver",
            "pi",
            "--preview",
        ]
    )
    monkeypatch.setattr(sys, "argv", argv)

    assert devframe_cli_main() == 0

    output = capsys.readouterr().out
    assert "worker       : executor driver=pi" in output
    assert "executor: driver=pi" in output
    assert "opencode" not in output.lower()
    assert "rdgoal worker" not in output
    assert not runtime.exists()


@pytest.mark.parametrize("remote_field", ["runtime", "node"])
def test_pi_environment_rejects_remote_windows_paths_before_filesystem_access(
    tmp_path,
    monkeypatch,
    remote_field,
):
    runtime_value = str(tmp_path.resolve())
    node_value = str(Path(sys.executable).resolve())
    remote_value = r"\\example.invalid\share\pi"
    if remote_field == "runtime":
        runtime_value = remote_value
    else:
        node_value = remote_value
    monkeypatch.setenv("DEVFRAME_PI_RUNTIME", runtime_value)
    monkeypatch.setenv("DEVFRAME_PI_NODE", node_value)
    monkeypatch.setattr(
        Path,
        "resolve",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("remote path reached filesystem resolution")
        ),
    )

    with pytest.raises(PiExecutorAdapterError, match="runtime is unavailable"):
        _environment_config(SimpleNamespace(project_root=str(tmp_path)))


def test_pi_environment_requires_explicit_node_before_filesystem_access(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setenv("DEVFRAME_PI_RUNTIME", str(tmp_path.resolve()))
    monkeypatch.delenv("DEVFRAME_PI_NODE", raising=False)
    monkeypatch.setattr(
        Path,
        "resolve",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("missing node reached filesystem resolution")
        ),
    )

    with pytest.raises(PiExecutorAdapterError, match="runtime is unavailable"):
        _environment_config(SimpleNamespace(project_root=str(tmp_path)))


def test_pi_environment_keeps_model_selection_absent_for_pre_cancel(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setenv("DEVFRAME_PI_RUNTIME", str(tmp_path.resolve()))
    monkeypatch.setenv("DEVFRAME_PI_NODE", str(Path(sys.executable).resolve()))
    monkeypatch.delenv("DEVFRAME_PI_PROVIDER", raising=False)
    monkeypatch.delenv("DEVFRAME_PI_MODEL", raising=False)

    config = _environment_config(SimpleNamespace(project_root=str(tmp_path)))

    assert config.provider is None
    assert config.model is None


def test_pi_environment_binds_explicit_non_secret_model_selection(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setenv("DEVFRAME_PI_RUNTIME", str(tmp_path.resolve()))
    monkeypatch.setenv("DEVFRAME_PI_NODE", str(Path(sys.executable).resolve()))
    monkeypatch.setenv("DEVFRAME_PI_PROVIDER", "local-loopback")
    monkeypatch.setenv("DEVFRAME_PI_MODEL", "Qwen3-4B-Q4_K_M")

    config = _environment_config(SimpleNamespace(project_root=str(tmp_path)))

    assert config.provider == "local-loopback"
    assert config.model == "Qwen3-4B-Q4_K_M"


def test_production_registry_forwards_model_selection_and_timeout_without_reporting_it(
    tmp_path,
    monkeypatch,
):
    install_root = tmp_path / "pi-install"
    install_root.mkdir()
    monkeypatch.setenv("DEVFRAME_PI_RUNTIME", str(install_root.resolve()))
    monkeypatch.setenv("DEVFRAME_PI_NODE", str(Path(sys.executable).resolve()))
    monkeypatch.setenv("DEVFRAME_PI_PROVIDER", "local-loopback")
    monkeypatch.setenv("DEVFRAME_PI_MODEL", "Qwen3-4B-Q4_K_M")
    configs = []

    class CapturingRunner:
        def __init__(self, config):
            configs.append(config)

        def run_turn(self, _message, *, cancel_event=None):
            assert cancel_event is None
            return PiRpcTurnResult(
                execution_status="completed",
                reason="STOP",
                prompt_accepted=True,
                abort_acknowledged=False,
                event_count=0,
                event_evidence=(),
                process_exit_code=0,
            )

    monkeypatch.setattr(
        "control_plane.pi_executor_adapter.PiRpcTurnRunner", CapturingRunner
    )

    result = run_go_dispatch(
        _project(tmp_path),
        "bounded model selection",
        runtime_dir=tmp_path / "runtime",
        agents=1,
        targets=["target.py"],
        execute=True,
        driver="pi",
        timeout_seconds=120,
    )

    assert len(configs) == 1
    assert configs[0].provider == "local-loopback"
    assert configs[0].model == "Qwen3-4B-Q4_K_M"
    assert configs[0].timeout_seconds == 120.0
    report = Path(result.agents[0].report_path).read_text(encoding="utf-8")
    assert "local-loopback" not in report
    assert "Qwen3-4B-Q4_K_M" not in report
    assert "INDEPENDENT_VERIFICATION_REQUIRED" in report
