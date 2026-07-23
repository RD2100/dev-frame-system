import json
from pathlib import Path

from jsonschema import Draft7Validator
import pytest
from typer.testing import CliRunner

from ai_workflow_hub import opencode_serve_slice1
from ai_workflow_hub.cli import app


REPO_ROOT = Path(__file__).resolve().parents[3]


def test_evaluate_serve_report_requires_process_file_and_event_signals():
    report = {
        "checks": {
            "server_health": {"status": "passed", "detail": "healthy"},
            "server_stopped": {"status": "passed", "detail": "disposed=True returncode=0"},
            "prompt_async_accepted": {"status": "passed", "detail": "HTTP 204"},
            "file_landed": {"status": "passed", "detail": "content match=True"},
            "tool_event_seen": {"status": "passed", "detail": "tool seen"},
            "step_finish_stop": {"status": "passed", "detail": "stop seen"},
        },
        "blockers": {"permission_events": [], "question_events": []},
        "timed_out": False,
    }

    opencode_serve_slice1.evaluate_serve_report(report)

    assert report["verdict"] == "passed"
    assert report["partial_type"] == ""
    assert report["failed_checks"] == []


def test_evaluate_serve_report_marks_permission_as_partial():
    report = {
        "checks": {
            "server_health": {"status": "passed", "detail": "healthy"},
            "server_stopped": {"status": "passed", "detail": "disposed=True returncode=0"},
            "prompt_async_accepted": {"status": "passed", "detail": "HTTP 204"},
            "file_landed": {"status": "failed", "detail": "missing"},
            "tool_event_seen": {"status": "failed", "detail": "missing"},
            "step_finish_stop": {"status": "failed", "detail": "missing"},
        },
        "blockers": {"permission_events": [{"type": "permission.updated"}], "question_events": []},
        "timed_out": False,
    }

    opencode_serve_slice1.evaluate_serve_report(report)

    assert report["verdict"] == "partial"
    assert report["partial_type"] == "needs-manual-permission-reply"


def test_evaluate_serve_report_marks_nonzero_shutdown_as_partial():
    report = {
        "checks": {
            "server_health": {"status": "passed", "detail": "healthy"},
            "server_stopped": {"status": "failed", "detail": "disposed=True returncode=1"},
            "prompt_async_accepted": {"status": "passed", "detail": "HTTP 204"},
            "file_landed": {"status": "passed", "detail": "content match=True"},
            "tool_event_seen": {"status": "passed", "detail": "tool seen"},
            "step_finish_stop": {"status": "passed", "detail": "stop seen"},
        },
        "blockers": {"permission_events": [], "question_events": []},
        "timed_out": False,
    }

    opencode_serve_slice1.evaluate_serve_report(report)

    assert report["verdict"] == "partial"
    assert report["partial_type"] == "serve-shutdown-nonzero"


def test_server_stopped_result_accepts_clean_dispose_returncode_one(tmp_path):
    stderr_path = tmp_path / "serve-stderr.log"
    stderr_path.write_text(
        "\n".join([
            "timestamp=2026-06-23T09:11:17Z level=INFO message=\"disposing instance\"",
            "timestamp=2026-06-23T09:11:18Z level=WARN message=\"duplicate skill name\"",
        ]),
        encoding="utf-8",
    )

    ok, detail = opencode_serve_slice1._server_stopped_result(True, 1, stderr_path)

    assert ok is True
    assert "clean_nonzero=True" in detail
    assert "error_signals=0" in detail


def test_server_stopped_result_rejects_nonzero_with_error_signal(tmp_path):
    stderr_path = tmp_path / "serve-stderr.log"
    stderr_path.write_text(
        "timestamp=2026-06-23T09:11:18Z level=ERROR message=\"database is locked\"\n",
        encoding="utf-8",
    )

    ok, detail = opencode_serve_slice1._server_stopped_result(True, 1, stderr_path)

    assert ok is False
    assert "error_signals=1" in detail


def test_sse_event_parser_uses_event_name_for_server_connected():
    parsed = opencode_serve_slice1._parse_sse_event("server.connected", [])

    assert parsed == {"type": "server.connected"}


def test_run_probe_refinalizes_early_health_failure_after_server_cleanup(tmp_path, monkeypatch):
    class FakeProc:
        pid = 1234

        def poll(self):
            return None

    monkeypatch.setattr(opencode_serve_slice1, "_find_opencode", lambda: "opencode")
    monkeypatch.setattr(opencode_serve_slice1, "_find_free_port", lambda: 49152)
    monkeypatch.setattr(opencode_serve_slice1, "_start_server", lambda *args: FakeProc())
    monkeypatch.setattr(opencode_serve_slice1, "_wait_for_health", lambda *args, **kwargs: {"healthy": False})
    monkeypatch.setattr(opencode_serve_slice1, "_stop_server", lambda proc: None)

    def fake_run_command(command, *, cwd: Path, timeout: int):
        if command == ["git", "init"]:
            return {"exit_code": 0, "stdout": "Initialized empty Git repository\n", "stderr": ""}
        if command == ["opencode", "--version"]:
            return {"exit_code": 0, "stdout": "opencode 1.0.0\n", "stderr": ""}
        raise AssertionError(command)

    monkeypatch.setattr(opencode_serve_slice1, "_run_command", fake_run_command)

    report = opencode_serve_slice1.run_opencode_serve_slice1_probe(output_dir=str(tmp_path))
    persisted = json.loads((tmp_path / "serve-slice1-report.json").read_text(encoding="utf-8"))

    assert report["checks"]["server_stopped"]["status"] == "failed"
    assert persisted["checks"]["server_stopped"]["status"] == "failed"
    assert persisted["failed_checks"] == ["server_health", "server_stopped"]
    assert persisted["partial_type"] == "serve-shutdown-nonzero"


@pytest.mark.parametrize(
    ("failure_stage", "failed_check"),
    [
        ("event_stream", "event_stream_connected"),
        ("session", "session_created"),
        ("prompt", "prompt_async_accepted"),
    ],
)
def test_run_probe_finalizes_other_early_failures_only_after_server_cleanup(
    tmp_path,
    monkeypatch,
    failure_stage,
    failed_check,
):
    class FakeProc:
        pid = 1234

        def poll(self):
            return None

    class FakeSse:
        def __init__(self, url, events):
            pass

        def start(self):
            pass

        def wait_connected(self, timeout):
            return failure_stage != "event_stream"

        def stop(self):
            pass

    monkeypatch.setattr(opencode_serve_slice1, "_find_opencode", lambda: "opencode")
    monkeypatch.setattr(opencode_serve_slice1, "_find_free_port", lambda: 49152)
    monkeypatch.setattr(opencode_serve_slice1, "_start_server", lambda *args: FakeProc())
    monkeypatch.setattr(
        opencode_serve_slice1,
        "_wait_for_health",
        lambda *args, **kwargs: {"healthy": True},
    )
    monkeypatch.setattr(opencode_serve_slice1, "_SseConsumer", FakeSse)
    monkeypatch.setattr(
        opencode_serve_slice1,
        "_http_json",
        lambda *args, **kwargs: {} if failure_stage == "session" else {"id": "session-1"},
    )
    monkeypatch.setattr(
        opencode_serve_slice1,
        "_http_status",
        lambda *args, **kwargs: 500 if failure_stage == "prompt" else 204,
    )
    monkeypatch.setattr(
        opencode_serve_slice1,
        "_wait_for_completion",
        lambda *args, **kwargs: pytest.fail("completion wait ran after an early failure"),
    )
    monkeypatch.setattr(opencode_serve_slice1, "_dispose_server", lambda base_url: False)
    monkeypatch.setattr(opencode_serve_slice1, "_stop_server", lambda proc: None)

    def fake_run_command(command, *, cwd: Path, timeout: int):
        if command == ["git", "init"]:
            return {"exit_code": 0, "stdout": "Initialized empty Git repository\n", "stderr": ""}
        if command == ["opencode", "--version"]:
            return {"exit_code": 0, "stdout": "opencode 1.0.0\n", "stderr": ""}
        raise AssertionError(command)

    monkeypatch.setattr(opencode_serve_slice1, "_run_command", fake_run_command)

    report = opencode_serve_slice1.run_opencode_serve_slice1_probe(output_dir=str(tmp_path))
    persisted = json.loads((tmp_path / "serve-slice1-report.json").read_text(encoding="utf-8"))

    assert report == persisted
    assert report["checks"][failed_check]["status"] == "failed"
    assert report["checks"]["server_stopped"]["status"] == "failed"
    assert report["failed_checks"] == [failed_check, "server_stopped"]


def test_readiness_report_schema_accepts_slice1_shape(tmp_path):
    schema = json.loads(
        (REPO_ROOT / "schemas" / "agent-runtime" / "opencode-readiness-report.schema.json").read_text(
            encoding="utf-8"
        )
    )
    report = {
        "schema_version": "opencode-readiness-report/v1",
        "probe": "opencode-serve-slice1",
        "mode": "serve-http-prompt-async",
        "model": "stepfun/step-3.7-flash",
        "workspace": str(tmp_path / "workspace"),
        "checks": {
            "server_health": {"status": "passed", "detail": "healthy"},
            "prompt_async_accepted": {"status": "passed", "detail": "HTTP 204"},
        },
        "paths": {"report": str(tmp_path / "serve-slice1-report.json")},
        "verdict": "partial",
        "partial_type": "event-terminal-missing",
        "failed_checks": ["step_finish_stop"],
    }

    Draft7Validator.check_schema(schema)
    Draft7Validator(schema).validate(report)


def test_cli_opencode_serve_slice1_json_uses_probe_report(tmp_path, monkeypatch):
    def fake_probe(**kwargs):
        return {
            "schema_version": "opencode-readiness-report/v1",
            "probe": "opencode-serve-slice1",
            "mode": "serve-http-prompt-async",
            "verdict": "partial",
            "partial_type": "event-terminal-missing",
            "failed_checks": ["step_finish_stop"],
            "workspace": str(tmp_path / "workspace"),
            "paths": {"report": str(tmp_path / "serve-slice1-report.json")},
            "received": kwargs,
        }

    monkeypatch.setattr(
        "ai_workflow_hub.opencode_serve_slice1.run_opencode_serve_slice1_probe",
        fake_probe,
    )

    result = CliRunner().invoke(
        app,
        [
            "opencode-serve-slice1",
            "--model",
            "model/test",
            "--output-dir",
            str(tmp_path),
            "--timeout",
            "7",
            "--json",
        ],
    )

    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    assert payload["verdict"] == "partial"
    assert payload["received"] == {
        "model": "model/test",
        "output_dir": str(tmp_path),
        "timeout": 7,
    }
