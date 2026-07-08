import json
from pathlib import Path

from typer.testing import CliRunner

from ai_workflow_hub import opencode_client
from ai_workflow_hub import opencode_slice0
from ai_workflow_hub.cli import app


def test_parse_jsonl_summarizes_candidate_fields():
    text = "\n".join(
        [
            json.dumps(
                {
                    "type": "message",
                    "sessionID": "sess-1",
                    "usage": {"inputTokens": 10, "cost": 0.01},
                    "tool": {"name": "edit"},
                }
            ),
            "not-json",
            json.dumps({"type": "error", "error": {"message": "boom"}}),
        ]
    )

    result = opencode_slice0.parse_jsonl(text)

    assert result["event_count"] == 2
    assert result["invalid_line_count"] == 1
    assert result["candidate_fields"] == {
        "session": True,
        "token": True,
        "cost": True,
        "tool": True,
        "error": True,
    }
    assert "usage.inputTokens" in result["flattened_keys"]


def test_opencode_lookup_source_has_no_machine_private_fallback():
    source = Path(opencode_client.__file__).read_text(encoding="utf-8")

    assert "D:\\Tools" not in source
    assert "OPENCODE_BIN" in source


def test_run_probe_writes_report_and_verifies_real_file_landing(tmp_path, monkeypatch):
    calls = []

    def fake_find_opencode():
        return "opencode"

    def fake_supports_flag(flag):
        return flag in {"--format", "--dangerously-skip-permissions"}

    def fake_run_command(command, *, cwd: Path, timeout: int):
        calls.append(command)
        if command == ["opencode", "--version"]:
            return _command_result(stdout="1.2.3\n")
        if command == ["git", "init"]:
            return _command_result(stdout="Initialized empty Git repository\n")
        assert command[:-1] == [
            "opencode",
            "run",
            "-m",
            "model/test",
            "--dangerously-skip-permissions",
            "--format",
            "json",
        ]
        (cwd / opencode_slice0.MARKER_FILE).write_text(
            opencode_slice0.MARKER_CONTENT,
            encoding="utf-8",
        )
        return _command_result(
            stdout=json.dumps(
                {
                    "sessionID": "sess-1",
                    "usage": {"outputTokens": 4, "cost": 0.001},
                    "tool": {"name": "edit"},
                }
            )
            + "\n"
        )

    monkeypatch.setattr(opencode_slice0, "_find_opencode", fake_find_opencode)
    monkeypatch.setattr(opencode_slice0, "opencode_supports_flag", fake_supports_flag)
    monkeypatch.setattr(opencode_slice0, "_run_command", fake_run_command)

    report = opencode_slice0.run_opencode_slice0_probe(
        model="model/test",
        output_dir=str(tmp_path),
        timeout=10,
    )

    assert report["verdict"] == "passed"
    assert report["failed_checks"] == []
    assert (tmp_path / "slice0-report.json").exists()
    assert (tmp_path / "opencode-stdout.jsonl").exists()
    assert (tmp_path / "opencode-stderr.log").exists()
    assert (tmp_path / "workspace" / opencode_slice0.MARKER_FILE).read_text(
        encoding="utf-8"
    ) == opencode_slice0.MARKER_CONTENT
    assert report["run"]["command"][-1] == "<probe-prompt>"
    assert calls[2][-1] != "<probe-prompt>"


def test_run_probe_fails_cleanly_when_cli_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(opencode_slice0, "_find_opencode", lambda: None)

    report = opencode_slice0.run_opencode_slice0_probe(output_dir=str(tmp_path))

    assert report["verdict"] == "failed"
    assert report["failed_checks"] == ["opencode_cli"]
    assert json.loads((tmp_path / "slice0-report.json").read_text(encoding="utf-8"))[
        "checks"
    ]["opencode_cli"]["status"] == "failed"


def test_cli_opencode_slice0_json_uses_probe_report(tmp_path, monkeypatch):
    def fake_probe(**kwargs):
        return {
            "verdict": "passed",
            "failed_checks": [],
            "workspace": str(tmp_path / "workspace"),
            "paths": {"report": str(tmp_path / "slice0-report.json")},
            "received": kwargs,
        }

    monkeypatch.setattr(
        "ai_workflow_hub.opencode_slice0.run_opencode_slice0_probe",
        fake_probe,
    )

    result = CliRunner().invoke(
        app,
        [
            "opencode-slice0",
            "--model",
            "model/test",
            "--output-dir",
            str(tmp_path),
            "--timeout",
            "5",
            "--json",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["verdict"] == "passed"
    assert payload["received"] == {
        "model": "model/test",
        "output_dir": str(tmp_path),
        "timeout": 5,
    }


def _command_result(stdout="", stderr="", exit_code=0):
    return {
        "exit_code": exit_code,
        "stdout": stdout,
        "stderr": stderr,
        "timed_out": False,
        "duration_seconds": 0.01,
    }
