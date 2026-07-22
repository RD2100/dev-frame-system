import json
from pathlib import Path
import subprocess

import pytest

from ai_workflow_hub import opencode_client
from ai_workflow_hub import opencode_readiness
from ai_workflow_hub import opencode_serve_slice1
from ai_workflow_hub import opencode_slice0
from ai_workflow_hub import acceptance


REQUIRED_SECRET_ENV = "OPENCODE_API_KEY"


def test_client_rejects_missing_secret_before_opencode_lookup(monkeypatch):
    monkeypatch.delenv(REQUIRED_SECRET_ENV, raising=False)
    monkeypatch.setattr(opencode_client, "_opencode_path", None)
    monkeypatch.setattr(
        opencode_client.subprocess,
        "run",
        lambda *args, **kwargs: pytest.fail("OpenCode subprocess was invoked"),
    )

    with pytest.raises(RuntimeError, match=REQUIRED_SECRET_ENV):
        opencode_client._find_opencode()


def test_client_run_rejects_missing_secret_before_temp_capture(monkeypatch):
    monkeypatch.delenv(REQUIRED_SECRET_ENV, raising=False)
    monkeypatch.setattr(opencode_client, "_ensure_env", lambda: None)
    monkeypatch.setattr(
        opencode_client,
        "_find_opencode",
        lambda: pytest.fail("OpenCode lookup was invoked"),
    )
    monkeypatch.setattr(
        opencode_client.tempfile,
        "mkstemp",
        lambda *args, **kwargs: pytest.fail("temporary capture was created"),
    )

    result = opencode_client.opencode_run("synthetic prompt")

    assert result["exit_code"] == 1
    assert result["stderr"] == f"required environment variable is not set: {REQUIRED_SECRET_ENV}"


def test_client_run_sanitizes_environment_init_exception_before_other_work(monkeypatch):
    sentinel = "synthetic-opencode-key-env-init"
    monkeypatch.setenv(REQUIRED_SECRET_ENV, sentinel)
    monkeypatch.setattr(
        opencode_client,
        "_ensure_env",
        lambda: (_ for _ in ()).throw(RuntimeError(f"init failed:{sentinel}")),
    )
    monkeypatch.setattr(
        opencode_client,
        "_find_opencode",
        lambda: pytest.fail("OpenCode lookup was invoked"),
    )
    monkeypatch.setattr(
        opencode_client.tempfile,
        "mkstemp",
        lambda *args, **kwargs: pytest.fail("temporary capture was created"),
    )

    result = opencode_client.opencode_run("synthetic prompt")

    assert result["exit_code"] == 1
    assert result["timed_out"] is False
    assert "environment initialization failed" in result["stderr"]
    assert sentinel not in json.dumps(result)


def test_readiness_rejects_missing_secret_before_subprocess(monkeypatch):
    monkeypatch.delenv(REQUIRED_SECRET_ENV, raising=False)
    monkeypatch.setattr(opencode_readiness, "opencode_is_installed", lambda: True)
    monkeypatch.setattr(
        opencode_readiness.subprocess,
        "run",
        lambda *args, **kwargs: pytest.fail("OpenCode subprocess was invoked"),
    )

    ok, error = opencode_readiness.opencode_probe(model="synthetic/model")

    assert ok is False
    assert error == f"required environment variable is not set: {REQUIRED_SECRET_ENV}"


@pytest.mark.parametrize(
    ("runner", "directory_name"),
    [
        (opencode_slice0.run_opencode_slice0_probe, "slice0"),
        (
            opencode_serve_slice1.run_opencode_serve_slice1_probe,
            "serve-slice1",
        ),
    ],
)
def test_probe_rejects_missing_secret_before_artifact_creation(
    tmp_path: Path,
    monkeypatch,
    runner,
    directory_name: str,
):
    monkeypatch.delenv(REQUIRED_SECRET_ENV, raising=False)
    artifact_dir = tmp_path / directory_name
    monkeypatch.setattr(opencode_client, "_opencode_path", None)
    monkeypatch.setattr(
        opencode_client.subprocess,
        "run",
        lambda *args, **kwargs: pytest.fail("OpenCode subprocess was invoked"),
    )

    with pytest.raises(RuntimeError, match=REQUIRED_SECRET_ENV):
        runner(model="synthetic/model", output_dir=str(artifact_dir), timeout=1)

    assert not artifact_dir.exists()


def test_client_sanitizes_timeout_output_and_persisted_logs(tmp_path: Path, monkeypatch):
    sentinel = "synthetic-opencode-key-timeout"
    monkeypatch.setenv(REQUIRED_SECRET_ENV, sentinel)
    monkeypatch.setattr(opencode_client, "_ensure_env", lambda: None)
    monkeypatch.setattr(opencode_client, "_find_opencode", lambda: "opencode")
    monkeypatch.setattr(opencode_client, "opencode_supports_flag", lambda flag: False)
    monkeypatch.setattr(opencode_client, "_kill_process_tree", lambda pid: None)

    class FakeProcess:
        pid = 4242

        def __init__(self, command, *, stdout, stderr, **kwargs):
            stdout.write(f"stdout:{sentinel}")
            stderr.write(f"stderr:{sentinel}")
            self.wait_count = 0

        def wait(self, timeout):
            self.wait_count += 1
            if self.wait_count == 1:
                raise subprocess.TimeoutExpired(
                    cmd="opencode",
                    timeout=timeout,
                    output=f"timeout-stdout:{sentinel}",
                    stderr=f"timeout-stderr:{sentinel}",
                )
            return 1

    monkeypatch.setattr(opencode_client.subprocess, "Popen", FakeProcess)
    stdout_log = tmp_path / "stdout.log"
    stderr_log = tmp_path / "stderr.log"

    result = opencode_client.opencode_run(
        "synthetic prompt",
        timeout=1,
        stdout_log=str(stdout_log),
        stderr_log=str(stderr_log),
    )

    assert result["timed_out"] is True
    assert sentinel not in json.dumps(result)
    assert sentinel not in stdout_log.read_text(encoding="utf-8")
    assert sentinel not in stderr_log.read_text(encoding="utf-8")


def test_client_sanitizes_process_exception(tmp_path: Path, monkeypatch):
    sentinel = "synthetic-opencode-key-exception"
    monkeypatch.setenv(REQUIRED_SECRET_ENV, sentinel)
    monkeypatch.setattr(opencode_client, "_ensure_env", lambda: None)
    monkeypatch.setattr(opencode_client, "_find_opencode", lambda: "opencode")
    monkeypatch.setattr(opencode_client, "opencode_supports_flag", lambda flag: False)
    monkeypatch.setattr(
        opencode_client.subprocess,
        "Popen",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError(f"failed:{sentinel}")),
    )
    stderr_log = tmp_path / "stderr.log"

    result = opencode_client.opencode_run(
        "synthetic prompt",
        stderr_log=str(stderr_log),
    )

    assert sentinel not in result["stderr"]
    assert sentinel not in stderr_log.read_text(encoding="utf-8")


def test_readiness_sanitizes_failed_process_output(monkeypatch):
    sentinel = "synthetic-opencode-key-readiness"
    monkeypatch.setenv(REQUIRED_SECRET_ENV, sentinel)
    monkeypatch.setattr(opencode_readiness, "opencode_is_installed", lambda: True)
    monkeypatch.setattr(
        opencode_readiness.subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args[0],
            1,
            stdout=f"stdout:{sentinel}",
            stderr=f"stderr:{sentinel}",
        ),
    )

    ok, error = opencode_readiness.opencode_probe(model="synthetic/model")

    assert ok is False
    assert sentinel not in error


def test_model_listing_sanitizes_returned_output(monkeypatch):
    sentinel = "synthetic-opencode-key-model-list"
    monkeypatch.setenv(REQUIRED_SECRET_ENV, sentinel)
    monkeypatch.setattr(opencode_client, "_find_opencode", lambda: "opencode")
    monkeypatch.setattr(
        opencode_client.subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args[0],
            0,
            stdout=f"synthetic/model\n{sentinel}\n",
            stderr="",
        ),
    )

    models = opencode_client.opencode_list_models()

    assert sentinel not in json.dumps(models)


def test_slice0_sanitizes_returned_and_persisted_evidence(tmp_path: Path, monkeypatch):
    sentinel = "synthetic-opencode-key-slice0"
    monkeypatch.setenv(REQUIRED_SECRET_ENV, sentinel)
    monkeypatch.setattr(opencode_slice0, "_find_opencode", lambda: "opencode")
    monkeypatch.setattr(opencode_slice0, "opencode_supports_flag", lambda flag: False)

    def fake_run_command(command, *, cwd: Path, timeout: int):
        if command == ["opencode", "--version"]:
            return _command_result(stdout=f"version:{sentinel}\n")
        if command == ["git", "init"]:
            return _command_result(stdout="git initialized\n")
        (cwd / opencode_slice0.MARKER_FILE).write_text(
            opencode_slice0.MARKER_CONTENT,
            encoding="utf-8",
        )
        return _command_result(
            stdout=json.dumps({"type": "message", "text": sentinel}) + "\n",
            stderr=f"stderr:{sentinel}",
        )

    monkeypatch.setattr(opencode_slice0, "_run_command", fake_run_command)

    report = opencode_slice0.run_opencode_slice0_probe(
        model="synthetic/model",
        output_dir=str(tmp_path),
        timeout=1,
    )

    assert sentinel not in json.dumps(report)
    for name in ("slice0-report.json", "opencode-stdout.jsonl", "opencode-stderr.log"):
        assert sentinel not in (tmp_path / name).read_text(encoding="utf-8")


def test_serve_slice1_sanitizes_returned_and_persisted_evidence(tmp_path: Path, monkeypatch):
    sentinel = "synthetic-opencode-key-serve"
    monkeypatch.setenv(REQUIRED_SECRET_ENV, sentinel)
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    report = opencode_serve_slice1._base_report(tmp_path, workspace, "synthetic/model", 1)
    report["events"]["raw_sample"] = [{"type": "error", "message": sentinel}]
    report["messages_sample"] = [{"message": sentinel}]
    report["blockers"] = {"permission_events": [{"detail": sentinel}], "question_events": []}
    for name in ("serve-stdout.log", "serve-stderr.log"):
        (tmp_path / name).write_text(f"log:{sentinel}", encoding="utf-8")

    result = opencode_serve_slice1._finalize_report(report, tmp_path)

    assert sentinel not in json.dumps(result)
    for name in (
        "serve-slice1-report.json",
        "serve-events.jsonl",
        "serve-stdout.log",
        "serve-stderr.log",
    ):
        assert sentinel not in (tmp_path / name).read_text(encoding="utf-8")


@pytest.mark.parametrize("module", [opencode_slice0, opencode_serve_slice1])
def test_probe_command_sanitizes_process_exception(tmp_path: Path, monkeypatch, module):
    sentinel = "synthetic-opencode-key-command-exception"
    monkeypatch.setenv(REQUIRED_SECRET_ENV, sentinel)
    monkeypatch.setattr(
        module.subprocess,
        "run",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError(f"failed:{sentinel}")),
    )

    result = module._run_command(["synthetic-command"], cwd=tmp_path, timeout=1)

    assert result["exit_code"] == 1
    assert sentinel not in json.dumps(result)


def test_serve_start_sanitizes_process_exception(tmp_path: Path, monkeypatch):
    sentinel = "synthetic-opencode-key-serve-start"
    monkeypatch.setenv(REQUIRED_SECRET_ENV, sentinel)
    monkeypatch.setattr(
        opencode_serve_slice1.subprocess,
        "Popen",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError(f"failed:{sentinel}")),
    )

    with pytest.raises(RuntimeError) as exc_info:
        opencode_serve_slice1._start_server(
            "synthetic-opencode",
            tmp_path,
            49152,
            "synthetic/model",
            tmp_path / "stdout.log",
            tmp_path / "stderr.log",
        )

    assert sentinel not in str(exc_info.value)


def test_serve_probe_hides_live_logs_and_sanitizes_after_abrupt_child_exit(
    tmp_path: Path,
    monkeypatch,
):
    sentinel = "synthetic-opencode-key-live-log-window"
    monkeypatch.setenv(REQUIRED_SECRET_ENV, sentinel)
    monkeypatch.setattr(opencode_serve_slice1, "_find_opencode", lambda: "opencode")
    monkeypatch.setattr(
        opencode_serve_slice1,
        "_run_command",
        lambda *args, **kwargs: _command_result(stdout="ok\n"),
    )
    monkeypatch.setattr(opencode_serve_slice1, "_find_free_port", lambda: 49153)

    final_stdout = tmp_path / "serve-stdout.log"
    final_stderr = tmp_path / "serve-stderr.log"
    capture_paths = []
    observed = {}

    class FakeProcess:
        pid = 4243
        returncode = 137

        def poll(self):
            return self.returncode

    def fake_start_server(
        opencode_path,
        workspace,
        port,
        model,
        stdout_path,
        stderr_path,
    ):
        capture_paths.extend([stdout_path, stderr_path])
        stdout_path.write_text(f"stdout:{sentinel}", encoding="utf-8")
        stderr_path.write_text(f"stderr:{sentinel}", encoding="utf-8")
        return FakeProcess()

    def fake_wait_for_health(base_url, timeout):
        observed["stdout_exists"] = final_stdout.exists()
        observed["stderr_exists"] = final_stderr.exists()
        return {"healthy": False, "error": "synthetic health failure"}

    monkeypatch.setattr(opencode_serve_slice1, "_start_server", fake_start_server)
    monkeypatch.setattr(opencode_serve_slice1, "_wait_for_health", fake_wait_for_health)

    report = opencode_serve_slice1.run_opencode_serve_slice1_probe(
        model="synthetic/model",
        output_dir=str(tmp_path),
        timeout=1,
    )

    assert observed == {"stdout_exists": False, "stderr_exists": False}
    assert capture_paths != [final_stdout, final_stderr]
    assert all(path.parent != tmp_path for path in capture_paths)
    assert all(not path.exists() for path in capture_paths)
    assert sentinel not in final_stdout.read_text(encoding="utf-8")
    assert sentinel not in final_stderr.read_text(encoding="utf-8")
    assert sentinel not in json.dumps(report)


def test_serve_probe_sanitizes_and_cleans_logs_when_start_is_interrupted(
    tmp_path: Path,
    monkeypatch,
):
    sentinel = "synthetic-opencode-key-start-interrupted"
    monkeypatch.setenv(REQUIRED_SECRET_ENV, sentinel)
    monkeypatch.setattr(opencode_serve_slice1, "_find_opencode", lambda: "opencode")
    monkeypatch.setattr(
        opencode_serve_slice1,
        "_run_command",
        lambda *args, **kwargs: _command_result(stdout="ok\n"),
    )
    monkeypatch.setattr(opencode_serve_slice1, "_find_free_port", lambda: 49154)

    final_stdout = tmp_path / "serve-stdout.log"
    final_stderr = tmp_path / "serve-stderr.log"
    capture_paths = []

    def interrupted_start(
        opencode_path,
        workspace,
        port,
        model,
        stdout_path,
        stderr_path,
    ):
        capture_paths.extend([stdout_path, stderr_path])
        stdout_path.write_text(f"stdout:{sentinel}", encoding="utf-8")
        stderr_path.write_text(f"stderr:{sentinel}", encoding="utf-8")
        raise RuntimeError("synthetic interrupted start")

    monkeypatch.setattr(opencode_serve_slice1, "_start_server", interrupted_start)

    with pytest.raises(RuntimeError, match="synthetic interrupted start"):
        opencode_serve_slice1.run_opencode_serve_slice1_probe(
            model="synthetic/model",
            output_dir=str(tmp_path),
            timeout=1,
        )

    assert capture_paths != [final_stdout, final_stderr]
    assert all(path.parent != tmp_path for path in capture_paths)
    assert all(not path.exists() for path in capture_paths)
    assert sentinel not in final_stdout.read_text(encoding="utf-8")
    assert sentinel not in final_stderr.read_text(encoding="utf-8")


def test_acceptance_sanitizes_console_and_persisted_results(tmp_path: Path, monkeypatch, capsys):
    key_sentinel = "synthetic-opencode-key-acceptance"
    base_sentinel = "https://synthetic.invalid/?token=sentinel"
    monkeypatch.setenv(REQUIRED_SECRET_ENV, key_sentinel)
    monkeypatch.setenv("OPENCODE_API_BASE", base_sentinel)
    monkeypatch.setattr(acceptance, "_hub_dir", lambda: tmp_path)
    monkeypatch.setattr(acceptance, "_results", [])
    monkeypatch.setattr(acceptance, "_suite_name", "synthetic")
    monkeypatch.setattr(acceptance, "_start_time", 0.0)

    acceptance._pass("synthetic output", f"{key_sentinel} {base_sentinel}")
    report_dir = Path(acceptance._save_report())

    output = capsys.readouterr().out
    assert key_sentinel not in output
    assert base_sentinel not in output
    for path in report_dir.iterdir():
        text = path.read_text(encoding="utf-8")
        assert key_sentinel not in text
        assert base_sentinel not in text


@pytest.mark.parametrize("runner", [acceptance.run_backend, acceptance.run_backend_probe])
def test_backend_acceptance_rejects_missing_secret_before_other_work(monkeypatch, runner):
    monkeypatch.delenv(REQUIRED_SECRET_ENV, raising=False)
    blocked = []
    monkeypatch.setattr(acceptance, "_blocked", lambda test, reason="": blocked.append((test, reason)))
    monkeypatch.setattr(
        acceptance,
        "_pass",
        lambda *args, **kwargs: pytest.fail("acceptance continued after secret rejection"),
    )
    monkeypatch.setattr(
        acceptance,
        "_save_report",
        lambda: pytest.fail("acceptance report was created"),
    )

    result = runner()

    assert result == 1
    assert blocked == [("opencode", f"required environment variable is not set: {REQUIRED_SECRET_ENV}")]


def _command_result(stdout="", stderr="", exit_code=0):
    return {
        "exit_code": exit_code,
        "stdout": stdout,
        "stderr": stderr,
        "timed_out": False,
        "duration_seconds": 0.01,
    }
