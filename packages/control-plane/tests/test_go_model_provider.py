"""Hermetic tests: go-dispatch records and enforces the model-provider route.

These do not run external workers or spend tokens; resume checks stay hermetic.
"""
import json
from pathlib import Path

import pytest

from control_plane.go_dispatch import execute_go_run, run_go_dispatch


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
    assert result.agents[0].command_origin == "builtin"
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
    result = _prepare(
        tmp_path,
        model_provider="local-ollama",
        model="ollama/qwen2.5-coder:7b",
    )
    assert result.model_provider == "local-ollama"
    assert result.agents[0].worker_command[:4] == [
        "opencode",
        "run",
        "-m",
        "ollama/qwen2.5-coder:7b",
    ]


def test_local_provider_requires_explicit_ollama_model_before_packets(tmp_path):
    with pytest.raises(ValueError) as exc:
        _prepare(tmp_path, model_provider="local-ollama")
    assert "requires an explicit --model ollama/<model>" in str(exc.value)
    assert not (tmp_path / "runtime" / "go-runs").exists()


def test_local_provider_refuses_foreign_model_before_packets(tmp_path):
    with pytest.raises(ValueError) as exc:
        _prepare(
            tmp_path,
            model_provider="local-ollama",
            model="stepfun/step-3.7-flash",
        )
    assert "must use the OpenCode model form ollama/<model>" in str(exc.value)
    assert not (tmp_path / "runtime" / "go-runs").exists()


def test_custom_command_is_provider_model_neutral(tmp_path):
    result = _prepare(
        tmp_path,
        model_provider="local-ollama",
        worker_command=["custom-worker", "--flag"],
    )
    assert result.model_provider == ""
    assert result.agents[0].model_provider == ""
    assert result.agents[0].command_origin == "custom"
    assert result.agents[0].worker_command == ["custom-worker", "--flag"]


def test_custom_opencode_named_command_resume_is_provider_neutral(tmp_path, monkeypatch):
    prepared = _prepare(
        tmp_path,
        model_provider="local-ollama",
        worker_command=["opencode.cmd", "run", "--custom-route"],
    )
    worker_calls = []

    def fake_worker(*args, **kwargs):
        worker_calls.append((args, kwargs))

    monkeypatch.setattr("control_plane.go_dispatch._execute_parallel", fake_worker)

    resumed = execute_go_run(tmp_path / "runtime", prepared.go_run_id)

    assert resumed.model_provider == ""
    assert resumed.agents[0].model_provider == ""
    assert resumed.agents[0].command_origin == "custom"
    assert len(worker_calls) == 1


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


def test_deferred_provider_refuses_resume_before_worker(tmp_path, monkeypatch):
    prepared = _prepare(tmp_path, model_provider="web-chatgpt-shim")
    metadata_path = Path(prepared.metadata_path)
    metadata_before = metadata_path.read_bytes()
    worker_calls = []

    def forbidden_worker(*args, **kwargs):
        worker_calls.append((args, kwargs))
        raise AssertionError("deferred provider reached the worker")

    monkeypatch.setattr("control_plane.go_dispatch._execute_parallel", forbidden_worker)

    with pytest.raises(ValueError) as exc:
        execute_go_run(tmp_path / "runtime", prepared.go_run_id)

    assert "deferred live backend" in str(exc.value)
    assert worker_calls == []
    assert metadata_path.read_bytes() == metadata_before


@pytest.mark.parametrize(
    ("case_id", "replacement_provider"),
    [
        ("deleted", None),
        ("empty", ""),
        ("replaced_with_opencode_api", "opencode-api"),
    ],
)
def test_prepared_web_chatgpt_shim_resume_rejects_top_level_provider_tampering(
    tmp_path,
    monkeypatch,
    case_id,
    replacement_provider,
):
    prepared = _prepare(tmp_path, model_provider="web-chatgpt-shim")
    metadata_path = Path(prepared.metadata_path)
    payload = json.loads(metadata_path.read_text(encoding="utf-8"))
    assert payload["model_provider"] == "web-chatgpt-shim"
    assert payload["agents"][0]["model_provider"] == "web-chatgpt-shim"
    if case_id == "deleted":
        del payload["model_provider"]
    else:
        payload["model_provider"] = replacement_provider
    metadata_path.write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8")
    metadata_before_execute = metadata_path.read_bytes()
    worker_calls = []

    def forbidden_worker(*args, **kwargs):
        worker_calls.append((args, kwargs))
        raise AssertionError("provider-tampered run reached the worker")

    monkeypatch.setattr("control_plane.go_dispatch._execute_parallel", forbidden_worker)

    with pytest.raises(ValueError):
        execute_go_run(tmp_path / "runtime", prepared.go_run_id)

    assert worker_calls == []
    assert metadata_path.read_bytes() == metadata_before_execute


def test_prepared_web_chatgpt_shim_resume_rejects_command_reclassification(
    tmp_path,
    monkeypatch,
):
    prepared = _prepare(tmp_path, model_provider="web-chatgpt-shim")
    metadata_path = Path(prepared.metadata_path)
    payload = json.loads(metadata_path.read_text(encoding="utf-8"))
    payload["agents"][0]["worker_command"][0] = "opencode.cmd"
    metadata_path.write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8")
    metadata_before_execute = metadata_path.read_bytes()
    worker_calls = []

    def forbidden_worker(*args, **kwargs):
        worker_calls.append((args, kwargs))
        raise AssertionError("command-reclassified run reached the worker")

    monkeypatch.setattr("control_plane.go_dispatch._execute_parallel", forbidden_worker)

    with pytest.raises(ValueError) as exc:
        execute_go_run(tmp_path / "runtime", prepared.go_run_id)

    assert "deferred live backend" in str(exc.value)
    assert worker_calls == []
    assert metadata_path.read_bytes() == metadata_before_execute


@pytest.mark.parametrize("executable", ["opencode", "opencode.exe", "opencode.cmd", "opencode.bat"])
def test_providerless_builtin_resume_requires_reprepare(tmp_path, monkeypatch, executable):
    prepared = _prepare(tmp_path)
    metadata_path = Path(prepared.metadata_path)
    payload = json.loads(metadata_path.read_text(encoding="utf-8"))
    payload["model_provider"] = ""
    payload["agents"][0]["model_provider"] = ""
    payload["agents"][0].pop("command_origin", None)
    payload["agents"][0]["worker_command"][0] = executable
    metadata_path.write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8")
    metadata_before_execute = metadata_path.read_bytes()
    worker_calls = []

    def forbidden_worker(*args, **kwargs):
        worker_calls.append((args, kwargs))
        raise AssertionError("providerless built-in run reached the worker")

    monkeypatch.setattr("control_plane.go_dispatch._execute_parallel", forbidden_worker)

    with pytest.raises(ValueError) as exc:
        execute_go_run(tmp_path / "runtime", prepared.go_run_id)

    assert "missing model_provider" in str(exc.value)
    assert worker_calls == []
    assert metadata_path.read_bytes() == metadata_before_execute


def test_local_provider_resume_revalidates_persisted_model_route(tmp_path, monkeypatch):
    prepared = _prepare(
        tmp_path,
        model_provider="local-ollama",
        model="ollama/qwen2.5-coder:7b",
    )
    metadata_path = Path(prepared.metadata_path)
    metadata = metadata_path.read_text(encoding="utf-8")
    metadata_path.write_text(
        metadata.replace("ollama/qwen2.5-coder:7b", "stepfun/step-3.7-flash"),
        encoding="utf-8",
    )
    worker_calls = []

    def forbidden_worker(*args, **kwargs):
        worker_calls.append((args, kwargs))
        raise AssertionError("local provider reached the worker")

    monkeypatch.setattr("control_plane.go_dispatch._execute_parallel", forbidden_worker)

    with pytest.raises(ValueError) as exc:
        execute_go_run(tmp_path / "runtime", prepared.go_run_id)

    assert "must use the OpenCode model form ollama/<model>" in str(exc.value)
    assert worker_calls == []
