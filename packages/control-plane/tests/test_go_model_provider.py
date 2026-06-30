"""Hermetic tests: go-dispatch records the chosen model provider on the session.

These do not execute workers or spend tokens; they only prepare packets.
"""
import pytest

from control_plane.go_dispatch import run_go_dispatch


def _prepare(tmp_path, **kwargs):
    project_root = tmp_path / "project"
    runtime_dir = tmp_path / "runtime"
    project_root.mkdir(exist_ok=True)
    (project_root / "a.py").write_text("x" * 10, encoding="utf-8")
    return run_go_dispatch(
        project_root,
        "Light coding task.",
        runtime_dir=runtime_dir,
        agents=1,
        targets=["a.py"],
        execute=False,
        **kwargs,
    )


def test_default_provider_is_recorded_and_command_unchanged(tmp_path):
    result = _prepare(tmp_path)
    assert result.model_provider == "opencode-api"
    assert result.agents[0].model_provider == "opencode-api"
    # Default path stays byte-identical: opencode run -m stepfun/step-3.7-flash
    assert result.agents[0].worker_command[:4] == [
        "opencode",
        "run",
        "-m",
        "stepfun/step-3.7-flash",
    ]


def test_explicit_provider_is_recorded_on_run_and_shards(tmp_path):
    result = _prepare(tmp_path, model_provider="web-chatgpt-shim")
    assert result.model_provider == "web-chatgpt-shim"
    assert all(agent.model_provider == "web-chatgpt-shim" for agent in result.agents)


def test_unknown_provider_raises_before_packets(tmp_path):
    with pytest.raises(ValueError) as exc:
        _prepare(tmp_path, model_provider="nope")
    assert "unknown model provider" in str(exc.value)
    # No go-run metadata should have been written.
    runtime_dir = tmp_path / "runtime"
    assert not (runtime_dir / "go-runs").exists()


def test_local_provider_recorded(tmp_path):
    result = _prepare(tmp_path, model_provider="local-ollama")
    assert result.model_provider == "local-ollama"


def test_deferred_provider_refuses_execute_to_avoid_silent_paid_run(tmp_path):
    # Preparing packets with the deferred web-shim profile is allowed.
    prepared = _prepare(tmp_path, model_provider="web-chatgpt-shim")
    assert prepared.model_provider == "web-chatgpt-shim"
    # But executing it must be refused: the "free" profile must not silently
    # fall back to the paid default worker.
    project_root = tmp_path / "project"
    runtime_dir = tmp_path / "runtime2"
    with pytest.raises(ValueError) as exc:
        run_go_dispatch(
            project_root,
            "Light task.",
            runtime_dir=runtime_dir,
            agents=1,
            targets=["a.py"],
            execute=True,
            model_provider="web-chatgpt-shim",
        )
    assert "deferred live backend" in str(exc.value)
    assert not (runtime_dir / "go-runs").exists()
