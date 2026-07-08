import builtins
import io
import json
import pytest
import subprocess
import sys
from pathlib import Path

from jsonschema.validators import validator_for

from control_plane.cli import main as devframe_cli_main
from control_plane.evidence_gate import FULL_EVIDENCE_FILES
from control_plane.run_index import build_run_index
from control_plane.visual_state import build_visual_control_plane_state


REPO_ROOT = Path(__file__).resolve().parents[3]


def _schema_validator(path: str):
    schema = json.loads((REPO_ROOT / path).read_text(encoding="utf-8-sig"))
    validator_class = validator_for(schema)
    validator_class.check_schema(schema)
    return validator_class(schema)


def test_doctor_passes_for_packaged_resources(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["devframe", "doctor"])

    assert devframe_cli_main() == 0


def test_root_help_is_available(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["devframe", "--help"])

    assert devframe_cli_main() == 0

    output = capsys.readouterr().out
    assert "DevFrame Code CLI" in output
    assert "OpenCode-first local coding tool" in output
    assert "devframe code [[<goal>] | --prompt-file <path>]" in output
    assert "devframe client" in output
    assert "devframe code workers" in output
    assert "devframe code status [latest|<go-run-id>]" in output
    assert "devframe code execute [latest|<go-run-id>]" in output
    assert "devframe go <project> <goal>" in output
    assert "devframe atgo <goal>" in output
    assert "devframe dashboard serve" in output


def test_code_help_is_available(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["devframe", "code", "--help"])

    assert devframe_cli_main() == 0

    output = capsys.readouterr().out
    assert "Usage: devframe code [[\"<goal>\"] | --prompt-file <path>]" in output
    assert "--prompt-file" in output
    assert "--agents" in output
    assert "--max-agents" in output
    assert "--changed" in output
    assert "--since" in output
    assert "--preview" in output
    assert "--worker" in output
    assert "--dashboard" in output


def test_client_help_is_available(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["devframe", "client", "--help"])

    assert devframe_cli_main() == 0

    output = capsys.readouterr().out
    assert "Usage: devframe client" in output
    assert "bridge" in output
    assert "--runtime-dir" in output
    assert "--dry-run" in output
    assert "--open" in output
    assert "--t3-root" in output


def test_code_session_help_is_available(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["devframe", "code", "session", "--help"])

    assert devframe_cli_main() == 0

    output = capsys.readouterr().out
    assert "Usage: devframe code session" in output
    assert "--runtime-dir" in output
    assert "--format" in output


def test_code_execute_help_is_available(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["devframe", "code", "execute", "--help"])

    assert devframe_cli_main() == 0

    output = capsys.readouterr().out
    assert "Usage: devframe code execute [latest|<go-run-id>]" in output
    assert "--rerun-passed" in output
    assert "--evidence-dir" in output
    assert "--auto-finalize" in output
    assert "--prepare-evidence-dir <dir>" in output
    assert "--auto-finalize | --prepare-evidence-dir <dir>" in output


def test_go_execute_auto_finalize_requires_evidence_dir(tmp_path, monkeypatch, capsys):
    runtime_dir = tmp_path / "runtime"
    monkeypatch.setattr(sys, "argv", [
        "devframe",
        "go",
        "execute",
        "--runtime-dir",
        str(runtime_dir),
        "--auto-finalize",
    ])

    exit_code = devframe_cli_main()
    captured = capsys.readouterr()

    assert exit_code == 2
    assert "--auto-finalize requires --evidence-dir" in captured.err
    assert not runtime_dir.exists()


def test_code_workers_lists_available_worker_profiles(monkeypatch, capsys):
    paths = {
        "opencode": "C:\\Tools\\opencode.cmd",
        "t3code": "",
    }

    monkeypatch.setattr("control_plane.cli.shutil.which", lambda name: paths.get(name) or None)
    monkeypatch.setattr(sys, "argv", ["devframe", "code", "workers"])

    assert devframe_cli_main() == 0

    output = capsys.readouterr().out
    assert "DevFrame Code workers" in output
    assert "Token mode   : status-only; no packets are created and no workers run" in output
    assert "- opencode [built-in] ready" in output
    assert "use    : devframe code \"<goal>\" --worker opencode --preview" in output
    assert "- t3code [custom] missing" in output
    assert "--command t3code <args...>" in output


def test_code_workers_json_output(monkeypatch, capsys):
    monkeypatch.setattr("control_plane.cli.shutil.which", lambda name: f"C:\\Tools\\{name}.cmd")
    monkeypatch.setattr(sys, "argv", ["devframe", "code", "workers", "--format", "json"])

    assert devframe_cli_main() == 0

    data = json.loads(capsys.readouterr().out)
    names = [worker["name"] for worker in data["workers"]]
    assert names == ["opencode", "t3code"]
    assert all(worker["available"] for worker in data["workers"])
    assert data["workers"][0]["usage"] == "--worker opencode"
    assert data["workers"][1]["usage"] == "--command t3code <args...>"


def test_go_workers_alias_uses_same_probe(monkeypatch, capsys):
    monkeypatch.setattr("control_plane.cli.shutil.which", lambda name: None)
    monkeypatch.setattr(sys, "argv", ["devframe", "go", "workers"])

    assert devframe_cli_main() == 0

    output = capsys.readouterr().out
    assert "DevFrame Code workers" in output
    assert "- opencode [built-in] missing" in output
    assert "- t3code [custom] missing" in output


def test_code_prepares_current_repo_coding_session(tmp_path, monkeypatch, capsys):
    project_root = tmp_path / "demo-project"
    runtime_dir = tmp_path / "runtime"
    project_root.mkdir()
    monkeypatch.chdir(project_root)
    monkeypatch.setattr(sys, "argv", [
        "devframe",
        "code",
        "Add a small CLI feature.",
        "--runtime-dir",
        str(runtime_dir),
        "--target",
        "src/cli.py",
    ])

    exit_code = devframe_cli_main()
    output = capsys.readouterr().out
    metadata_path = next((runtime_dir / "go-runs").glob("*/go-run.json"))
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    state = build_visual_control_plane_state(runtime_dir)

    assert exit_code == 0
    assert "DevFrame Code session" in output
    assert "Tool shape   : OpenCode-first local coding CLI" in output
    assert "Backend      : /go concurrent coding-agent dispatch" in output
    assert "status       : queued" in output
    assert "agents       : 1" in output
    assert "Inspect   : devframe code status" in output
    assert "Resume    : devframe code execute" in output
    assert metadata["go_run_id"] in output
    assert "Control   : devframe dashboard serve --runtime-dir" in output
    assert metadata["project_root"] == str(project_root.resolve())
    assert metadata["requirement"] == "Add a small CLI feature."
    assert metadata["agents"][0]["targets"] == ["src/cli.py"]
    assert len(state["go_runs"]) == 1
    assert state["go_runs"][0]["agents"][0]["agent_id"] == "coding-agent-1"


def test_code_prompts_for_interactive_goal(tmp_path, monkeypatch, capsys):
    project_root = tmp_path / "demo-project"
    runtime_dir = tmp_path / "runtime"
    project_root.mkdir()
    monkeypatch.setattr(sys, "argv", [
        "devframe",
        "code",
        "--project",
        str(project_root),
        "--runtime-dir",
        str(runtime_dir),
        "--target",
        "src/cli.py",
    ])
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
    prompts = []

    def fake_input(prompt):
        prompts.append(prompt)
        return "Add an interactive coding entrypoint."

    monkeypatch.setattr(builtins, "input", fake_input)

    exit_code = devframe_cli_main()
    output = capsys.readouterr().out
    metadata_path = next((runtime_dir / "go-runs").glob("*/go-run.json"))
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))

    assert exit_code == 0
    assert prompts == ["Goal: "]
    assert "DevFrame Code session" in output
    assert metadata["requirement"] == "Add an interactive coding entrypoint."
    assert metadata["agents"][0]["targets"] == ["src/cli.py"]


def test_code_status_reads_latest_go_run_without_creating_packets(tmp_path, monkeypatch, capsys):
    project_root = tmp_path / "demo-project"
    runtime_dir = tmp_path / "runtime"
    project_root.mkdir()
    monkeypatch.setattr(sys, "argv", [
        "devframe",
        "code",
        "Add a small CLI feature.",
        "--project",
        str(project_root),
        "--runtime-dir",
        str(runtime_dir),
        "--target",
        "src/cli.py",
    ])
    assert devframe_cli_main() == 0
    metadata_files_before = list((runtime_dir / "go-runs").glob("*/go-run.json"))
    metadata = json.loads(metadata_files_before[0].read_text(encoding="utf-8"))
    monkeypatch.setattr(sys, "argv", [
        "devframe",
        "code",
        "status",
        "--runtime-dir",
        str(runtime_dir),
    ])

    exit_code = devframe_cli_main()
    output = capsys.readouterr().out
    metadata_files_after = list((runtime_dir / "go-runs").glob("*/go-run.json"))

    assert exit_code == 0
    assert "DevFrame Code status" in output
    assert metadata["go_run_id"] in output
    assert "status       : prepared" in output
    assert "coding-agent-1" in output
    assert metadata_files_after == metadata_files_before


def test_code_status_reads_specific_go_run_as_json(tmp_path, monkeypatch, capsys):
    project_root = tmp_path / "demo-project"
    runtime_dir = tmp_path / "runtime"
    project_root.mkdir()
    monkeypatch.setattr(sys, "argv", [
        "devframe",
        "code",
        "Add a small CLI feature.",
        "--project",
        str(project_root),
        "--runtime-dir",
        str(runtime_dir),
        "--target",
        "src/cli.py",
    ])
    assert devframe_cli_main() == 0
    metadata_path = next((runtime_dir / "go-runs").glob("*/go-run.json"))
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    capsys.readouterr()
    monkeypatch.setattr(sys, "argv", [
        "devframe",
        "code",
        "status",
        metadata["go_run_id"],
        "--runtime-dir",
        str(runtime_dir),
        "--format",
        "json",
    ])

    exit_code = devframe_cli_main()
    status = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert status["go_run_id"] == metadata["go_run_id"]
    assert status["agents"][0]["targets"] == ["src/cli.py"]


def test_code_status_reports_missing_runtime(tmp_path, monkeypatch, capsys):
    runtime_dir = tmp_path / "runtime"
    monkeypatch.setattr(sys, "argv", [
        "devframe",
        "code",
        "status",
        "--runtime-dir",
        str(runtime_dir),
    ])

    exit_code = devframe_cli_main()
    output = capsys.readouterr()

    assert exit_code == 1
    assert "no go runs found" in output.err


def test_code_execute_reuses_prepared_go_run_packets(tmp_path, monkeypatch, capsys):
    project_root = tmp_path / "demo-project"
    runtime_dir = tmp_path / "runtime"
    marker_dir = tmp_path / "worker-markers"
    project_root.mkdir()
    report_code = (
        "from pathlib import Path; import os; "
        f"marker_dir = Path({str(marker_dir)!r}); "
        "marker_dir.mkdir(parents=True, exist_ok=True); "
        "packet_name = Path(os.environ['RDGOAL_PACKET_DIR']).name; "
        "(marker_dir / f'{packet_name}.txt').write_text('ran', encoding='utf-8'); "
        "Path(os.environ['RDGOAL_REPORT_PATH']).write_text("
        "'## ExecutionReport\\n\\n"
        "- **Status**: pass\\n"
        "- **Changed Files**:\\n"
        "- `src/app.py`\\n"
        "- **Evidence**: reused prepared packet\\n', encoding='utf-8')"
    )
    monkeypatch.setattr(sys, "argv", [
        "devframe",
        "code",
        "Execute prepared packets later.",
        "--project",
        str(project_root),
        "--runtime-dir",
        str(runtime_dir),
        "--agents",
        "2",
        "--target",
        "src/app.py",
        "--target",
        "src/lib.py",
        "--command",
        sys.executable,
        "-c",
        report_code,
    ])
    assert devframe_cli_main() == 0
    metadata_files_before = list((runtime_dir / "go-runs").glob("*/go-run.json"))
    metadata_before = json.loads(metadata_files_before[0].read_text(encoding="utf-8"))
    packet_dirs_before = {agent["packet_dir"] for agent in metadata_before["agents"]}
    capsys.readouterr()
    monkeypatch.setattr(sys, "argv", [
        "devframe",
        "code",
        "execute",
        metadata_before["go_run_id"],
        "--runtime-dir",
        str(runtime_dir),
        "--timeout",
        "30",
    ])

    exit_code = devframe_cli_main()
    output = capsys.readouterr().out
    metadata_files_after = list((runtime_dir / "go-runs").glob("*/go-run.json"))
    metadata_after = json.loads(metadata_files_after[0].read_text(encoding="utf-8"))
    packet_dirs_after = {agent["packet_dir"] for agent in metadata_after["agents"]}
    state = build_visual_control_plane_state(runtime_dir)

    assert exit_code == 0
    assert "DevFrame Code execute" in output
    assert "Tool shape   : reusing prepared coding-agent packets" in output
    assert "status       : passed" in output
    assert "changed: src/app.py" in output
    assert metadata_files_after == metadata_files_before
    assert packet_dirs_after == packet_dirs_before
    assert metadata_after["execute"] is True
    assert metadata_after["status"] == "passed"
    assert {agent["worker_status"] for agent in metadata_after["agents"]} == {"passed"}
    assert len(list(marker_dir.glob("*.txt"))) == 2
    assert state["go_runs"][0]["status"] == "passed"


def test_code_execute_skips_previously_passed_agents(tmp_path, monkeypatch, capsys):
    project_root = tmp_path / "demo-project"
    runtime_dir = tmp_path / "runtime"
    counter_path = tmp_path / "worker-count.txt"
    project_root.mkdir()
    report_code = (
        "from pathlib import Path; import os; "
        f"counter = Path({str(counter_path)!r}); "
        "count = int(counter.read_text(encoding='utf-8')) if counter.exists() else 0; "
        "counter.write_text(str(count + 1), encoding='utf-8'); "
        "Path(os.environ['RDGOAL_REPORT_PATH']).write_text("
        "'## ExecutionReport\\n\\n"
        "- **Status**: pass\\n"
        "- **Evidence**: skip rerun evidence\\n', encoding='utf-8')"
    )
    monkeypatch.setattr(sys, "argv", [
        "devframe",
        "code",
        "Execute prepared packet once.",
        "--project",
        str(project_root),
        "--runtime-dir",
        str(runtime_dir),
        "--target",
        "src/app.py",
        "--command",
        sys.executable,
        "-c",
        report_code,
    ])
    assert devframe_cli_main() == 0
    metadata_path = next((runtime_dir / "go-runs").glob("*/go-run.json"))
    go_run_id = json.loads(metadata_path.read_text(encoding="utf-8"))["go_run_id"]
    capsys.readouterr()
    for _index in range(2):
        monkeypatch.setattr(sys, "argv", [
            "devframe",
            "code",
            "execute",
            go_run_id,
            "--runtime-dir",
            str(runtime_dir),
            "--timeout",
            "30",
        ])
        assert devframe_cli_main() == 0

    assert counter_path.read_text(encoding="utf-8") == "1"


def test_go_execute_auto_finalize_records_reviewed_evidence_real_path(tmp_path, monkeypatch, capsys):
    project_root = tmp_path / "demo-project"
    runtime_dir = tmp_path / "runtime"
    evidence_dir = tmp_path / "generic-go-evidence"
    project_root.mkdir()
    report_code = (
        "from pathlib import Path; import json, os; "
        f"evidence_dir = Path({str(evidence_dir)!r}); "
        "evidence_dir.mkdir(parents=True, exist_ok=True); "
        "(evidence_dir / 'diff.patch').write_text('', encoding='utf-8'); "
        "(evidence_dir / 'test-output.md').write_text('1 passed\\n', encoding='utf-8'); "
        "(evidence_dir / 'safety-report.json').write_text("
        "json.dumps({"
        "'generated_at': '2026-07-08T00:00:00+00:00',"
        "'producer': 'test',"
        "'command': 'pytest',"
        "'exit_code': 0,"
        "'stdout': '1 passed'"
        "}) + '\\n', encoding='utf-8'); "
        "(evidence_dir / 'review.md').write_text('Independent review passed.\\n', encoding='utf-8'); "
        "(evidence_dir / 'review.yaml').write_text("
        "'reviewer_role: reviewer\\n'"
        "'reviewer_id: reviewer-1\\n'"
        "'executor_id: executor-1\\n'"
        "'verdict: pass\\n'"
        "'reviewed_inputs:\\n'"
        "'  - diff.patch\\n'"
        "'  - test-output.md\\n'"
        "'  - safety-report.json\\n'"
        "'  - chain-evidence.json\\n'"
        "'findings: []\\n', encoding='utf-8'); "
        "Path(os.environ['RDGOAL_REPORT_PATH']).write_text("
        "'## ExecutionReport\\n\\n"
        "- **Status**: pass\\n"
        "- **Changed Files**:\\n"
        "- `src/app.py`\\n"
        "- **Evidence**: generic go auto-finalize real path\\n',"
        "encoding='utf-8')"
    )
    monkeypatch.setattr(sys, "argv", [
        "devframe",
        "go",
        str(project_root),
        "Execute reviewed evidence later.",
        "--runtime-dir",
        str(runtime_dir),
        "--agents",
        "1",
        "--target",
        "src/app.py",
        "--command",
        sys.executable,
        "-c",
        report_code,
    ])
    assert devframe_cli_main() == 0
    metadata_path = next((runtime_dir / "go-runs").glob("*/go-run.json"))
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    go_run_id = metadata["go_run_id"]
    evidence_dir.mkdir(parents=True, exist_ok=True)
    (evidence_dir / "task-spec.md").write_text("generic go finalize task\n", encoding="utf-8")
    (evidence_dir / "chain-evidence.json").write_text(
        json.dumps({
            "run_id": go_run_id,
            "executor_id": "executor-1",
            "mode": "auto_execute",
            "planner": None,
            "task": str(evidence_dir / "task-spec.md"),
            "methodology": None,
            "evidence_files": FULL_EVIDENCE_FILES[:],
            "timestamps": {
                "created_at": "2026-07-08T00:00:00+00:00",
            },
        }, indent=2) + "\n",
        encoding="utf-8",
    )
    capsys.readouterr()
    monkeypatch.setattr(sys, "argv", [
        "devframe",
        "go",
        "execute",
        go_run_id,
        "--runtime-dir",
        str(runtime_dir),
        "--timeout",
        "30",
        "--evidence-dir",
        str(evidence_dir),
        "--auto-finalize",
    ])

    exit_code = devframe_cli_main()
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "DevFrame Code execute" in output
    assert "Auto-finalize: tools/go_evidence.py finalize" in output
    assert "PASS" in output
    assert (evidence_dir / "final-verdict.json").exists()
    assert (evidence_dir / "evidence-manifest.json").exists()
    assert (evidence_dir / "final-report.md").exists()

    index = build_run_index(runtime_dir)
    team_record = next(
        entry["record"]
        for entry in index["runs"]
        if entry["adapter_id"] == "team_events"
        and entry["record"]["domain_refs"].get("source_run_id") == go_run_id
    )
    assert team_record["acceptance_state"] == "final_ready"
    assert team_record["review_state"] == "review_passed"
    assert team_record["gate_state"] == "gate_passed"


def test_go_execute_prepare_evidence_dir_generates_draft_and_can_be_finalized_later(tmp_path, monkeypatch, capsys):
    project_root = tmp_path / "demo-project"
    runtime_dir = tmp_path / "runtime"
    evidence_dir = tmp_path / "prepared-evidence"
    project_root.mkdir()
    report_code = (
        "from pathlib import Path; import os; "
        "Path(os.environ['RDGOAL_REPORT_PATH']).write_text("
        "'## ExecutionReport\\n\\n"
        "- **Status**: pass\\n"
        "- **Changed Files**:\\n"
        "- `src/app.py`\\n"
        "- **Evidence**: prepare-only evidence path\\n',"
        "encoding='utf-8')"
    )
    monkeypatch.setattr(sys, "argv", [
        "devframe",
        "go",
        str(project_root),
        "Prepare evidence without acceptance.",
        "--runtime-dir",
        str(runtime_dir),
        "--agents",
        "1",
        "--target",
        "src/app.py",
        "--command",
        sys.executable,
        "-c",
        report_code,
    ])
    assert devframe_cli_main() == 0
    metadata_path = next((runtime_dir / "go-runs").glob("*/go-run.json"))
    go_run_id = json.loads(metadata_path.read_text(encoding="utf-8"))["go_run_id"]
    capsys.readouterr()

    monkeypatch.setattr(sys, "argv", [
        "devframe",
        "go",
        "execute",
        go_run_id,
        "--runtime-dir",
        str(runtime_dir),
        "--timeout",
        "30",
        "--prepare-evidence-dir",
        str(evidence_dir),
    ])
    assert devframe_cli_main() == 0
    output = capsys.readouterr().out
    manifest = json.loads((evidence_dir / "evidence-manifest.json").read_text(encoding="utf-8"))
    chain = json.loads((evidence_dir / "chain-evidence.json").read_text(encoding="utf-8"))

    assert "Prepare evidence:" in output
    assert manifest["verdict_eligibility"]["status"] == "needs_more_evidence"
    assert chain["run_id"] == go_run_id
    assert chain["next_commands"]["finalize"]["creates_acceptance"] is False
    assert chain["next_commands"]["finalize"]["requires_independent_review"] is True
    assert not (evidence_dir / "review.yaml").exists()
    assert not (evidence_dir / "final-verdict.json").exists()
    index = build_run_index(runtime_dir)
    team_record = next(
        entry["record"]
        for entry in index["runs"]
        if entry["adapter_id"] == "team_events"
        and entry["record"]["domain_refs"].get("source_run_id") == go_run_id
    )
    assert team_record["acceptance_state"] != "final_ready"

    (evidence_dir / "diff.patch").write_text("", encoding="utf-8")
    (evidence_dir / "test-output.md").write_text("1 passed\n", encoding="utf-8")
    (evidence_dir / "safety-report.json").write_text(
        json.dumps({
            "generated_at": "2026-07-08T00:00:00+00:00",
            "producer": "test",
            "command": "pytest",
            "exit_code": 0,
            "stdout": "1 passed",
        }) + "\n",
        encoding="utf-8",
    )
    (evidence_dir / "review.md").write_text("Independent review passed.\n", encoding="utf-8")
    (evidence_dir / "review.yaml").write_text(
        "reviewer_role: reviewer\n"
        "reviewer_id: reviewer-1\n"
        "executor_id: devframe-go-execute\n"
        "verdict: pass\n"
        "reviewed_inputs:\n"
        "  - diff.patch\n"
        "  - test-output.md\n"
        "  - safety-report.json\n"
        "  - chain-evidence.json\n"
        "findings: []\n",
        encoding="utf-8",
    )
    capsys.readouterr()
    monkeypatch.setattr(sys, "argv", [
        "devframe",
        "go",
        "execute",
        go_run_id,
        "--runtime-dir",
        str(runtime_dir),
        "--timeout",
        "30",
        "--evidence-dir",
        str(evidence_dir),
        "--auto-finalize",
    ])
    assert devframe_cli_main() == 0

    assert (evidence_dir / "final-verdict.json").exists()
    index = build_run_index(runtime_dir)
    team_record = next(
        entry["record"]
        for entry in index["runs"]
        if entry["adapter_id"] == "team_events"
        and entry["record"]["domain_refs"].get("source_run_id") == go_run_id
    )
    assert team_record["acceptance_state"] == "final_ready"


def test_code_reads_goal_from_prompt_file(tmp_path, monkeypatch, capsys):
    project_root = tmp_path / "demo-project"
    runtime_dir = tmp_path / "runtime"
    prompt_file = tmp_path / "task.md"
    project_root.mkdir()
    prompt_file.write_text("Build an OpenCode-backed shell.\n\nUse changed files only.\n", encoding="utf-8")
    monkeypatch.setattr(sys, "argv", [
        "devframe",
        "code",
        "--project",
        str(project_root),
        "--runtime-dir",
        str(runtime_dir),
        "--prompt-file",
        str(prompt_file),
        "--target",
        "src/cli.py",
    ])

    exit_code = devframe_cli_main()
    metadata_path = next((runtime_dir / "go-runs").glob("*/go-run.json"))
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))

    assert exit_code == 0
    assert metadata["requirement"] == "Build an OpenCode-backed shell.\n\nUse changed files only."


def test_code_reads_goal_from_stdin_pipe(tmp_path, monkeypatch, capsys):
    project_root = tmp_path / "demo-project"
    runtime_dir = tmp_path / "runtime"
    project_root.mkdir()
    monkeypatch.setattr(sys, "stdin", io.StringIO("Fix failing tests.\nKeep the change small.\n"))
    monkeypatch.setattr(sys, "argv", [
        "devframe",
        "code",
        "--project",
        str(project_root),
        "--runtime-dir",
        str(runtime_dir),
        "--target",
        "tests/test_app.py",
    ])

    exit_code = devframe_cli_main()
    metadata_path = next((runtime_dir / "go-runs").glob("*/go-run.json"))
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))

    assert exit_code == 0
    assert metadata["requirement"] == "Fix failing tests.\nKeep the change small."


def test_code_rejects_goal_and_prompt_file_together(tmp_path, monkeypatch, capsys):
    project_root = tmp_path / "demo-project"
    runtime_dir = tmp_path / "runtime"
    prompt_file = tmp_path / "task.md"
    project_root.mkdir()
    prompt_file.write_text("Build an OpenCode-backed shell.\n", encoding="utf-8")
    monkeypatch.setattr(sys, "argv", [
        "devframe",
        "code",
        "Build another thing.",
        "--project",
        str(project_root),
        "--runtime-dir",
        str(runtime_dir),
        "--prompt-file",
        str(prompt_file),
    ])

    exit_code = devframe_cli_main()
    output = capsys.readouterr()

    assert exit_code == 2
    assert "pass either a positional goal or --prompt-file" in output.err
    assert not runtime_dir.exists()


def test_code_changed_targets_git_files(tmp_path, monkeypatch, capsys):
    project_root = tmp_path / "demo-project"
    runtime_dir = tmp_path / "runtime"
    src_dir = project_root / "src"
    src_dir.mkdir(parents=True)
    (src_dir / "app.py").write_text("print('hello')\n", encoding="utf-8")
    subprocess.run(["git", "init"], cwd=project_root, check=True, capture_output=True, text=True)
    monkeypatch.setattr(sys, "argv", [
        "devframe",
        "code",
        "Implement only changed files.",
        "--project",
        str(project_root),
        "--runtime-dir",
        str(runtime_dir),
        "--changed",
    ])

    exit_code = devframe_cli_main()
    metadata_path = next((runtime_dir / "go-runs").glob("*/go-run.json"))
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))

    assert exit_code == 0
    assert metadata["agents"][0]["targets"] == ["src/app.py"]


def test_code_since_targets_git_ref_files(tmp_path, monkeypatch, capsys):
    project_root = tmp_path / "demo-project"
    runtime_dir = tmp_path / "runtime"
    src_dir = project_root / "src"
    src_dir.mkdir(parents=True)
    (src_dir / "app.py").write_text("print('base')\n", encoding="utf-8")
    subprocess.run(["git", "init"], cwd=project_root, check=True, capture_output=True, text=True)
    subprocess.run(["git", "add", "src/app.py"], cwd=project_root, check=True, capture_output=True, text=True)
    subprocess.run([
        "git",
        "-c",
        "user.name=DevFrame Test",
        "-c",
        "user.email=devframe@example.invalid",
        "commit",
        "-m",
        "base",
    ], cwd=project_root, check=True, capture_output=True, text=True)
    (src_dir / "api.py").write_text("print('feature')\n", encoding="utf-8")
    subprocess.run(["git", "add", "src/api.py"], cwd=project_root, check=True, capture_output=True, text=True)
    subprocess.run([
        "git",
        "-c",
        "user.name=DevFrame Test",
        "-c",
        "user.email=devframe@example.invalid",
        "commit",
        "-m",
        "feature",
    ], cwd=project_root, check=True, capture_output=True, text=True)
    monkeypatch.setattr(sys, "argv", [
        "devframe",
        "code",
        "Review branch delta only.",
        "--project",
        str(project_root),
        "--runtime-dir",
        str(runtime_dir),
        "--since",
        "HEAD~1",
        "--agents",
        "auto",
    ])

    exit_code = devframe_cli_main()
    metadata_path = next((runtime_dir / "go-runs").glob("*/go-run.json"))
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))

    assert exit_code == 0
    assert len(metadata["agents"]) == 1
    assert metadata["agents"][0]["targets"] == ["src/api.py"]


def test_code_agents_auto_uses_changed_file_count(tmp_path, monkeypatch, capsys):
    project_root = tmp_path / "demo-project"
    runtime_dir = tmp_path / "runtime"
    src_dir = project_root / "src"
    src_dir.mkdir(parents=True)
    for name in ("app.py", "api.py", "ui.py"):
        (src_dir / name).write_text(f"# {name}\n", encoding="utf-8")
    subprocess.run(["git", "init"], cwd=project_root, check=True, capture_output=True, text=True)
    monkeypatch.setattr(sys, "argv", [
        "devframe",
        "code",
        "Fan out changed files.",
        "--project",
        str(project_root),
        "--runtime-dir",
        str(runtime_dir),
        "--changed",
        "--agents",
        "auto",
    ])

    exit_code = devframe_cli_main()
    metadata_path = next((runtime_dir / "go-runs").glob("*/go-run.json"))
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))

    assert exit_code == 0
    assert len(metadata["agents"]) == 3
    assert [agent["targets"] for agent in metadata["agents"]] == [
        ["src/api.py"],
        ["src/app.py"],
        ["src/ui.py"],
    ]


def test_code_preview_shows_shards_without_creating_packets(tmp_path, monkeypatch, capsys):
    project_root = tmp_path / "demo-project"
    runtime_dir = tmp_path / "runtime"
    project_root.mkdir()
    monkeypatch.setattr(sys, "argv", [
        "devframe",
        "code",
        "Preview coding fanout.",
        "--project",
        str(project_root),
        "--runtime-dir",
        str(runtime_dir),
        "--agents",
        "auto",
        "--target",
        "src/a.py",
        "--target",
        "src/b.py",
        "--preview",
    ])

    exit_code = devframe_cli_main()
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "DevFrame coding preview" in output
    assert "entrypoint   : devframe code" in output
    assert "runtime_dir  : " in output
    assert "agents       : 2" in output
    assert "targets      : 2" in output
    assert "worker       : opencode model=stepfun/step-3.7-flash agent=build" in output
    assert "- coding-agent-1 shard=1/2" in output
    assert "  - src/a.py" in output
    assert "  command: opencode run -m stepfun/step-3.7-flash --dangerously-skip-permissions --agent build" in output
    assert "You are coding shard 1/2." in output
    assert "- coding-agent-2 shard=2/2" in output
    assert "  - src/b.py" in output
    assert "You are coding shard 2/2." in output
    assert "Prepare   : re-run without --preview to create a resumable coding run." in output
    assert not runtime_dir.exists()


def test_code_preview_shows_custom_worker_command(tmp_path, monkeypatch, capsys):
    project_root = tmp_path / "demo-project"
    runtime_dir = tmp_path / "runtime"
    project_root.mkdir()
    monkeypatch.setattr(sys, "argv", [
        "devframe",
        "code",
        "Preview custom worker.",
        "--project",
        str(project_root),
        "--runtime-dir",
        str(runtime_dir),
        "--target",
        "src/app.py",
        "--preview",
        "--command",
        sys.executable,
        "-c",
        "print('worker')",
    ])

    exit_code = devframe_cli_main()
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "worker       : custom command" in output
    assert f"command: {sys.executable}" in output
    assert "-c \"print('worker')\"" in output
    assert "opencode run" not in output
    assert not runtime_dir.exists()


def test_code_agents_rejects_invalid_value(tmp_path, monkeypatch, capsys):
    project_root = tmp_path / "demo-project"
    runtime_dir = tmp_path / "runtime"
    project_root.mkdir()
    monkeypatch.setattr(sys, "argv", [
        "devframe",
        "code",
        "Invalid agents value.",
        "--project",
        str(project_root),
        "--runtime-dir",
        str(runtime_dir),
        "--agents",
        "many",
    ])

    exit_code = devframe_cli_main()
    output = capsys.readouterr()

    assert exit_code == 2
    assert "--agents must be a positive integer or auto" in output.err
    assert not runtime_dir.exists()


def test_code_rejects_removed_builtin_worker_choice(tmp_path, monkeypatch, capsys):
    project_root = tmp_path / "demo-project"
    runtime_dir = tmp_path / "runtime"
    project_root.mkdir()
    monkeypatch.setattr(sys, "argv", [
        "devframe",
        "code",
        "Removed worker value.",
        "--project",
        str(project_root),
        "--runtime-dir",
        str(runtime_dir),
        "--worker",
        "codex",
    ])

    with pytest.raises(SystemExit) as excinfo:
        devframe_cli_main()
    output = capsys.readouterr()

    assert excinfo.value.code == 2
    assert "invalid choice" in output.err
    assert "opencode" in output.err


def test_code_changed_requires_git_changes(tmp_path, monkeypatch, capsys):
    project_root = tmp_path / "demo-project"
    runtime_dir = tmp_path / "runtime"
    project_root.mkdir()
    subprocess.run(["git", "init"], cwd=project_root, check=True, capture_output=True, text=True)
    monkeypatch.setattr(sys, "argv", [
        "devframe",
        "code",
        "Implement only changed files.",
        "--project",
        str(project_root),
        "--runtime-dir",
        str(runtime_dir),
        "--changed",
    ])

    exit_code = devframe_cli_main()
    output = capsys.readouterr()

    assert exit_code == 2
    assert "--changed found no modified, staged, or untracked git files" in output.err
    assert not runtime_dir.exists()


def test_code_dashboard_serves_prepared_session(tmp_path, monkeypatch, capsys):
    from control_plane import dashboard

    project_root = tmp_path / "demo-project"
    runtime_dir = tmp_path / "runtime"
    project_root.mkdir()
    captured = {}

    def fake_serve_dashboard(**kwargs):
        captured.update(kwargs)

    monkeypatch.setattr(dashboard, "serve_dashboard", fake_serve_dashboard)
    monkeypatch.setattr(sys, "argv", [
        "devframe",
        "code",
        "Add a visible coding dashboard.",
        "--project",
        str(project_root),
        "--runtime-dir",
        str(runtime_dir),
        "--dashboard",
        "--port",
        "0",
        "--refresh-seconds",
        "0",
    ])

    exit_code = devframe_cli_main()
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "Dashboard UI : starting read-only visual interface" in output
    assert "Chinese UI   : append ?lang=zh-CN to the dashboard URL" in output
    assert captured["runtime_dir"] == str(runtime_dir.resolve())
    assert captured["host"] == "127.0.0.1"
    assert captured["port"] == 0
    assert captured["refresh_seconds"] == 0


def test_code_dashboard_requires_allow_remote_for_non_loopback(tmp_path, monkeypatch, capsys):
    project_root = tmp_path / "demo-project"
    runtime_dir = tmp_path / "runtime"
    project_root.mkdir()
    monkeypatch.setattr(sys, "argv", [
        "devframe",
        "code",
        "Add a visible coding dashboard.",
        "--project",
        str(project_root),
        "--runtime-dir",
        str(runtime_dir),
        "--dashboard",
        "--host",
        "0.0.0.0",
    ])

    exit_code = devframe_cli_main()
    output = capsys.readouterr()

    assert exit_code == 1
    assert "use --allow-remote" in output.out
    assert not runtime_dir.exists()


def test_go_help_is_available(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["devframe", "go", "--help"])

    assert devframe_cli_main() == 0

    output = capsys.readouterr().out
    assert "Usage: devframe go <project> <goal>" in output
    assert "--agents" in output
    assert "--max-agents" in output
    assert "--changed" in output
    assert "--since" in output
    assert "--preview" in output
    assert "--worker" in output


def test_go_agents_auto_respects_max_agents(tmp_path, monkeypatch, capsys):
    project_root = tmp_path / "demo-project"
    runtime_dir = tmp_path / "runtime"
    project_root.mkdir()
    monkeypatch.setattr(sys, "argv", [
        "devframe",
        "go",
        str(project_root),
        "Fan out explicit targets.",
        "--runtime-dir",
        str(runtime_dir),
        "--agents",
        "auto",
        "--max-agents",
        "2",
        "--target",
        "src/a.py",
        "--target",
        "src/b.py",
        "--target",
        "src/c.py",
    ])

    exit_code = devframe_cli_main()
    metadata_path = next((runtime_dir / "go-runs").glob("*/go-run.json"))
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))

    assert exit_code == 0
    assert len(metadata["agents"]) == 2
    assert metadata["agents"][0]["targets"] == ["src/a.py", "src/c.py"]
    assert metadata["agents"][1]["targets"] == ["src/b.py"]


def test_go_shards_targets_by_estimated_size(tmp_path, monkeypatch, capsys):
    project_root = tmp_path / "demo-project"
    runtime_dir = tmp_path / "runtime"
    src_dir = project_root / "src"
    src_dir.mkdir(parents=True)
    (src_dir / "large.py").write_text("x" * 100, encoding="utf-8")
    (src_dir / "medium.py").write_text("x" * 60, encoding="utf-8")
    (src_dir / "small.py").write_text("x" * 40, encoding="utf-8")
    monkeypatch.setattr(sys, "argv", [
        "devframe",
        "go",
        str(project_root),
        "Balance file-sized shards.",
        "--runtime-dir",
        str(runtime_dir),
        "--agents",
        "2",
        "--target",
        "src/small.py",
        "--target",
        "src/large.py",
        "--target",
        "src/medium.py",
    ])

    exit_code = devframe_cli_main()
    metadata_path = next((runtime_dir / "go-runs").glob("*/go-run.json"))
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))

    assert exit_code == 0
    assert metadata["agents"][0]["targets"] == ["src/large.py"]
    assert metadata["agents"][1]["targets"] == ["src/medium.py", "src/small.py"]


def test_go_preview_respects_shard_plan_without_runtime(tmp_path, monkeypatch, capsys):
    project_root = tmp_path / "demo-project"
    runtime_dir = tmp_path / "runtime"
    project_root.mkdir()
    monkeypatch.setattr(sys, "argv", [
        "devframe",
        "go",
        str(project_root),
        "Preview explicit targets.",
        "--runtime-dir",
        str(runtime_dir),
        "--agents",
        "2",
        "--target",
        "src/a.py",
        "--target",
        "src/b.py",
        "--target",
        "src/c.py",
        "--preview",
    ])

    exit_code = devframe_cli_main()
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "entrypoint   : devframe go" in output
    assert "agents       : 2" in output
    assert "targets      : 3" in output
    assert "worker       : opencode model=stepfun/step-3.7-flash agent=build" in output
    assert "- coding-agent-1 shard=1/2" in output
    assert "  - src/a.py" in output
    assert "  - src/c.py" in output
    assert "You are coding shard 1/2." in output
    assert "- coding-agent-2 shard=2/2" in output
    assert "  - src/b.py" in output
    assert "You are coding shard 2/2." in output
    assert not runtime_dir.exists()


def test_go_preview_shows_size_balanced_shards(tmp_path, monkeypatch, capsys):
    project_root = tmp_path / "demo-project"
    runtime_dir = tmp_path / "runtime"
    src_dir = project_root / "src"
    src_dir.mkdir(parents=True)
    (src_dir / "large.py").write_text("x" * 100, encoding="utf-8")
    (src_dir / "medium.py").write_text("x" * 60, encoding="utf-8")
    (src_dir / "small.py").write_text("x" * 40, encoding="utf-8")
    monkeypatch.setattr(sys, "argv", [
        "devframe",
        "go",
        str(project_root),
        "Preview balanced targets.",
        "--runtime-dir",
        str(runtime_dir),
        "--agents",
        "2",
        "--target",
        "src/small.py",
        "--target",
        "src/large.py",
        "--target",
        "src/medium.py",
        "--preview",
    ])

    exit_code = devframe_cli_main()
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "target_bytes : 200" in output
    assert "- coding-agent-1 shard=1/2 bytes=100" in output
    assert "  - src/large.py" in output
    assert "- coding-agent-2 shard=2/2 bytes=100" in output
    assert "  - src/medium.py" in output
    assert "  - src/small.py" in output
    assert not runtime_dir.exists()


def test_go_prepares_parallel_coding_agent_packets(tmp_path, monkeypatch, capsys):
    project_root = tmp_path / "demo-project"
    runtime_dir = tmp_path / "runtime"
    project_root.mkdir()
    source_dir = project_root / "packages" / "control-plane" / "control_plane"
    source_dir.mkdir(parents=True)
    (source_dir / "cli.py").write_text("c" * 20, encoding="utf-8")
    (source_dir / "go_dispatch.py").write_text("g" * 20, encoding="utf-8")
    monkeypatch.setattr(sys, "argv", [
        "devframe",
        "go",
        str(project_root),
        "Build an OpenCode-first programming tool MVP.",
        "--runtime-dir",
        str(runtime_dir),
        "--agents",
        "2",
        "--target",
        "packages/control-plane/control_plane/cli.py",
        "--target",
        "packages/control-plane/control_plane/go_dispatch.py",
    ])

    exit_code = devframe_cli_main()
    output = capsys.readouterr().out
    metadata_files = list((runtime_dir / "go-runs").glob("*/go-run.json"))
    metadata = json.loads(metadata_files[0].read_text(encoding="utf-8"))
    state = build_visual_control_plane_state(runtime_dir)

    assert exit_code == 0
    assert "status       : queued" in output
    assert "agents       : 2" in output
    assert "coding-agent-1" in output
    assert "coding-agent-2" in output
    assert "  bytes  : 20" in output
    assert "opencode run -m stepfun/step-3.7-flash --dangerously-skip-permissions" in output
    assert "Inspect   : devframe code status" in output
    assert "Resume    : devframe code execute" in output
    assert "devframe dashboard serve --runtime-dir" in output
    assert len(metadata_files) == 1
    assert metadata["status"] == "queued"
    assert len(metadata["agents"]) == 2
    assert metadata["agents"][0]["targets"] == ["packages/control-plane/control_plane/cli.py"]
    assert metadata["agents"][0]["target_bytes"] == 20
    assert metadata["agents"][1]["targets"] == ["packages/control-plane/control_plane/go_dispatch.py"]
    assert metadata["agents"][1]["target_bytes"] == 20
    assert all(Path(agent["packet_dir"]).exists() for agent in metadata["agents"])
    assert len(state["go_runs"]) == 1
    assert state["go_runs"][0]["go_run_id"] == metadata["go_run_id"]
    assert state["go_runs"][0]["agents"][1]["targets"] == ["packages/control-plane/control_plane/go_dispatch.py"]
    assert state["go_runs"][0]["agents"][1]["target_bytes"] == 20
    assert len(state["runs"]) == 2
    assert all(run["next_command"].startswith("rdgoal worker ") for run in state["runs"])


def test_go_execute_runs_worker_command_for_each_agent(tmp_path, monkeypatch, capsys):
    project_root = tmp_path / "demo-project"
    runtime_dir = tmp_path / "runtime"
    project_root.mkdir()
    report_code = (
        "from pathlib import Path; import os; "
        "Path(os.environ['RDGOAL_REPORT_PATH']).write_text("
        "'## ExecutionReport\\n\\n"
        "- **Status**: pass\\n"
        "- **Review Status**: pass\\n"
        "- **Changed Files**:\\n"
        "- `src/app.py`\\n"
        "- **Evidence**: fake worker command\\n"
        "- **Reviewer Index**:\\n"
        "- fake worker evidence\\n', encoding='utf-8')"
    )
    monkeypatch.setattr(sys, "argv", [
        "devframe",
        "go",
        str(project_root),
        "Run two coding shards.",
        "--runtime-dir",
        str(runtime_dir),
        "--agents",
        "2",
        "--execute",
        "--command",
        sys.executable,
        "-c",
        report_code,
    ])

    exit_code = devframe_cli_main()
    output = capsys.readouterr().out
    metadata_path = next((runtime_dir / "go-runs").glob("*/go-run.json"))
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    state = build_visual_control_plane_state(runtime_dir)

    assert exit_code == 0
    assert "status       : passed" in output
    assert "changed: src/app.py" in output
    assert "evidence: Evidence: fake worker command" in output
    assert metadata["execute"] is True
    assert metadata["status"] == "passed"
    assert {agent["worker_status"] for agent in metadata["agents"]} == {"passed"}
    assert all(agent["changed_files"] == ["src/app.py"] for agent in metadata["agents"])
    assert all("fake worker command" in agent["verification"] for agent in metadata["agents"])
    assert all(Path(agent["report_path"]).exists() for agent in metadata["agents"])
    assert all(agent["changed_files"] == ["src/app.py"] for agent in state["go_runs"][0]["agents"])
    assert {run["status"] for run in state["runs"]} == {"completed"}


def test_run_help_is_available(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["devframe", "run", "--help"])

    assert devframe_cli_main() == 0

    output = capsys.readouterr().out
    assert "Usage: devframe run --pipeline <path>" in output


def test_dashboard_help_is_available(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["devframe", "dashboard", "--help"])

    assert devframe_cli_main() == 0

    output = capsys.readouterr().out
    assert "Usage: devframe dashboard serve" in output


def test_init_code_project_generates_runnable_pipeline(tmp_path, monkeypatch):
    project_root = tmp_path / "demo-project"
    monkeypatch.setattr(sys, "argv", ["devframe", "init", "code_project", str(project_root)])

    assert devframe_cli_main() == 0

    pipeline_path = project_root / "PIPELINE.yaml"
    assert pipeline_path.exists()
    assert "{{" not in pipeline_path.read_text(encoding="utf-8")

    monkeypatch.setattr(sys, "argv", ["devframe", "run", "--pipeline", str(pipeline_path)])

    assert devframe_cli_main() == 0


def test_run_execute_passes_project_dir_to_stage_executor(tmp_path, monkeypatch):
    from control_plane import stage_executor

    project_root = tmp_path / "paper-project"
    pipeline_path = tmp_path / "reference_paper_review.yaml"
    project_root.mkdir()
    pipeline_path.write_text("pipeline_id: reference_paper_review\nstages: []\n", encoding="utf-8")
    captured = {}

    class FakeStageResult:
        stage_id = "project_init"
        status = "completed"
        outputs = []

    def fake_execute_full_pipeline(project_dir=None):
        captured["project_dir"] = project_dir
        return [FakeStageResult()]

    monkeypatch.setattr(stage_executor, "execute_full_pipeline", fake_execute_full_pipeline)
    monkeypatch.setattr(sys, "argv", [
        "devframe",
        "run",
        "--pipeline",
        str(pipeline_path),
        "--execute",
        "--project",
        str(project_root),
    ])

    assert devframe_cli_main() == 0
    assert captured["project_dir"] == project_root.resolve()


def test_code_session_reads_latest_go_run(tmp_path, monkeypatch, capsys):
    project_root = tmp_path / "demo-project"
    runtime_dir = tmp_path / "runtime"
    project_root.mkdir()
    monkeypatch.setattr(sys, "argv", [
        "devframe",
        "code",
        "Add a small CLI feature.",
        "--project",
        str(project_root),
        "--runtime-dir",
        str(runtime_dir),
        "--target",
        "src/cli.py",
    ])
    assert devframe_cli_main() == 0
    metadata_path = next((runtime_dir / "go-runs").glob("*/go-run.json"))
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    metadata["agents"][0]["changed_files"] = ["`src/cli.py` - added session command"]
    metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    capsys.readouterr()
    monkeypatch.setattr(sys, "argv", [
        "devframe",
        "code",
        "session",
        "--runtime-dir",
        str(runtime_dir),
    ])

    exit_code = devframe_cli_main()
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "DevFrame Code sessions" in output
    assert metadata["go_run_id"] in output
    assert "provider=opencode" in output
    assert "task_spec   : TASKSPEC.json" in output


def test_code_session_json_output(tmp_path, monkeypatch, capsys):
    project_root = tmp_path / "demo-project"
    runtime_dir = tmp_path / "runtime"
    project_root.mkdir()
    monkeypatch.setattr(sys, "argv", [
        "devframe",
        "code",
        "Add a small CLI feature.",
        "--project",
        str(project_root),
        "--runtime-dir",
        str(runtime_dir),
        "--target",
        "src/cli.py",
    ])
    assert devframe_cli_main() == 0
    metadata_path = next((runtime_dir / "go-runs").glob("*/go-run.json"))
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    metadata["methodology"] = {
        "skill_id": "tdd",
        "title": "tdd",
        "source_path": "tools/skills/tdd/SKILL.md",
        "source_kind": "local_repository_asset",
        "triggers": ["@tdd"],
        "status": "registered",
    }
    metadata["agents"][0]["changed_files"] = ["src/cli.py` added `SESSION_USAGE`"]
    metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    capsys.readouterr()
    monkeypatch.setattr(sys, "argv", [
        "devframe",
        "code",
        "session",
        "--runtime-dir",
        str(runtime_dir),
        "--format",
        "json",
    ])

    exit_code = devframe_cli_main()
    sessions = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert len(sessions) == 1
    assert sessions[0]["run_id"] == metadata["go_run_id"]
    assert sessions[0]["provider"] == "opencode"
    assert sessions[0]["methodology"]["skill_id"] == "tdd"
    assert sessions[0]["task_spec"] == "TASKSPEC.json"
    assert sessions[0]["targets"] == ["src/cli.py"]
    assert sessions[0]["changed_files"] == ["src/cli.py"]


def test_code_session_text_output_shows_methodology(tmp_path, monkeypatch, capsys):
    project_root = tmp_path / "demo-project"
    runtime_dir = tmp_path / "runtime"
    project_root.mkdir()
    monkeypatch.setattr(sys, "argv", [
        "devframe",
        "code",
        "@tdd Add a small CLI feature.",
        "--project",
        str(project_root),
        "--runtime-dir",
        str(runtime_dir),
        "--target",
        "src/cli.py",
    ])
    assert devframe_cli_main() == 0
    capsys.readouterr()
    monkeypatch.setattr(sys, "argv", [
        "devframe",
        "code",
        "session",
        "--runtime-dir",
        str(runtime_dir),
    ])

    exit_code = devframe_cli_main()
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "DevFrame Code sessions" in output
    assert "methodology : tdd" in output


def test_code_session_reports_missing_runtime(tmp_path, monkeypatch, capsys):
    runtime_dir = tmp_path / "runtime"
    monkeypatch.setattr(sys, "argv", [
        "devframe",
        "code",
        "session",
        "--runtime-dir",
        str(runtime_dir),
    ])

    exit_code = devframe_cli_main()
    output = capsys.readouterr()

    assert exit_code == 1
    assert "no go runs found" in output.err


def test_sessions_help_is_available(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["devframe", "sessions", "--help"])

    assert devframe_cli_main() == 0

    output = capsys.readouterr().out
    assert "Usage: devframe sessions" in output
    assert "--runtime-dir" in output
    assert "--format" in output


def test_sessions_lists_imported_web_ai_sessions(tmp_path, monkeypatch, capsys):
    runtime_dir = tmp_path / "runtime"
    sessions_dir = runtime_dir / "web-ai-sessions"
    sessions_dir.mkdir(parents=True)
    (sessions_dir / "chatgpt-summary.json").write_text(
        json.dumps({
            "session_id": "chatgpt-session-1",
            "provider": "chatgpt",
            "agent_id": "chatgpt-agent",
            "agent_role": "executor",
            "project_id": "demo-project",
            "run_id": "chatgpt-run-1",
            "task_spec_id": "TASKSPEC.json",
            "status": "completed",
            "messages": [
                {"message_id": "m1", "role": "user", "content_summary": "Hello"},
                {"message_id": "m2", "role": "assistant", "content_summary": "Hi there"},
            ],
            "tool_calls": [],
            "changed_files": ["src/app.py"],
            "diff_summary": "1 changed file",
            "evidence_refs": ["/tmp/evidence1"],
            "cost": {"amount": 0.01, "currency": "USD"},
            "tokens": {"input": 10, "output": 20, "total": 30},
            "gates": [],
            "actions": [],
            "native_refs": {"runtime": "web-ai-import"},
        }),
        encoding="utf-8",
    )
    monkeypatch.setattr(sys, "argv", [
        "devframe",
        "sessions",
        "--runtime-dir",
        str(runtime_dir),
    ])

    exit_code = devframe_cli_main()
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "DevFrame sessions" in output
    assert "provider=chatgpt" in output
    assert str(runtime_dir) not in output
    assert "runtime_dir  : hidden" in output
    assert "status=completed" in output
    assert "agent_id    : chatgpt-agent" in output
    assert "role        : executor" in output
    assert "task_spec   : TASKSPEC.json" in output
    assert "changed     : src/app.py" in output


def test_sessions_json_output(tmp_path, monkeypatch, capsys):
    runtime_dir = tmp_path / "runtime"
    sessions_dir = runtime_dir / "web-ai-sessions"
    sessions_dir.mkdir(parents=True)
    (sessions_dir / "deepseek-summary.json").write_text(
        json.dumps({
            "session_id": "deepseek-session-1",
            "provider": "deepseek",
            "agent_role": "reviewer",
            "project_id": "demo-project",
            "status": "idle",
            "messages": [],
            "tool_calls": [],
            "changed_files": [],
            "evidence_refs": [],
            "gates": [],
            "actions": [],
        }),
        encoding="utf-8",
    )
    monkeypatch.setattr(sys, "argv", [
        "devframe",
        "sessions",
        "--runtime-dir",
        str(runtime_dir),
        "--format",
        "json",
    ])

    exit_code = devframe_cli_main()
    sessions = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert len(sessions["sessions"]) == 1
    assert sessions["sessions"][0]["provider"] == "deepseek"
    assert sessions["sessions"][0]["agent_role"] == "reviewer"
    assert sessions["sessions"][0]["status"] == "idle"


def test_sessions_reports_missing_runtime(tmp_path, monkeypatch, capsys):
    runtime_dir = tmp_path / "runtime"
    monkeypatch.setattr(sys, "argv", [
        "devframe",
        "sessions",
        "--runtime-dir",
        str(runtime_dir),
    ])

    exit_code = devframe_cli_main()
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "DevFrame sessions" in output
    assert "(no sessions)" in output


def test_web_ai_import_help(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["devframe", "web-ai", "import", "--help"])

    assert devframe_cli_main() == 0

    output = capsys.readouterr().out
    assert "Usage: devframe web-ai import" in output
    assert "<source>" in output
    assert "--runtime-dir" in output


def test_web_ai_bind_chrome_help(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["devframe", "web-ai", "bind-chrome", "--help"])

    assert devframe_cli_main() == 0

    output = capsys.readouterr().out
    assert "Usage: devframe web-ai bind-chrome" in output
    assert "--cdp-endpoint" in output
    assert "--dry-run" in output


def test_web_ai_ensure_browser_help(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["devframe", "web-ai", "ensure-browser", "--help"])

    assert devframe_cli_main() == 0

    output = capsys.readouterr().out
    assert "Usage: devframe web-ai ensure-browser" in output
    assert "--profile-dir" in output
    assert "--write-config" in output


def test_web_ai_ensure_browser_json(monkeypatch, capsys, tmp_path):
    def fake_ensure_web_ai_browser(**kwargs):
        return {
            "status": "already_running",
            "browser": "chrome",
            "browser_exe": "C:/Chrome/chrome.exe",
            "cdp_endpoint": "http://127.0.0.1:9222",
            "profile_dir": str(tmp_path / "profile"),
            "url": "https://chatgpt.com/",
            "started": False,
            "opened_url": True,
            "config_written": "",
            "reason": "",
            "probe": {"reachable": True},
            "first_use_note": "First use may require logging in once inside this dedicated browser profile.",
            "kwargs": kwargs,
        }

    import control_plane.web_ai_browser_launcher as launcher_module

    monkeypatch.setattr(launcher_module, "ensure_web_ai_browser", fake_ensure_web_ai_browser)
    monkeypatch.setattr(sys, "argv", [
        "devframe",
        "web-ai",
        "ensure-browser",
        "--runtime-dir",
        str(tmp_path / "runtime"),
        "--profile-dir",
        str(tmp_path / "profile"),
        "--format",
        "json",
    ])

    assert devframe_cli_main() == 0
    data = json.loads(capsys.readouterr().out)
    assert data["status"] == "already_running"
    assert data["profile_dir"] == str(tmp_path / "profile")


def test_web_ai_bind_conversation_help(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["devframe", "web-ai", "bind-conversation", "--help"])

    assert devframe_cli_main() == 0

    output = capsys.readouterr().out
    assert "Usage: devframe web-ai bind-conversation" in output


def test_web_ai_bind_conversation_url_creates_session_and_user_binding(tmp_path, monkeypatch, capsys):
    project = tmp_path / "project"
    runtime = tmp_path / "runtime"
    binding_root = tmp_path / "bindings"
    project.mkdir()
    monkeypatch.setattr(sys, "argv", [
        "devframe",
        "web-ai",
        "bind-conversation",
        "--conversation",
        "https://chatgpt.com/c/example-conversation-id",
        "--project",
        "dev-frame-system",
        "--project-root",
        str(project),
        "--runtime-dir",
        str(runtime),
        "--binding-root",
        str(binding_root),
        "--output-name",
        "bound-chatgpt.json",
    ])

    exit_code = devframe_cli_main()
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "Imported ChatGPT conversation session" in output
    session_path = runtime / "web-ai-sessions" / "bound-chatgpt.json"
    session = json.loads(session_path.read_text(encoding="utf-8"))
    assert session["native_refs"]["conversation_url"] == "https://chatgpt.com/c/example-conversation-id"
    binding_path = binding_root / "dev-frame-system" / "CONVERSATION_BINDING.json"
    registry_path = binding_root / "dev-frame-system" / "PROJECT_REGISTRY.json"
    assert binding_path.exists()
    assert registry_path.exists()
    binding = json.loads(binding_path.read_text(encoding="utf-8"))
    assert binding["bindings"][0]["conversation_id"] == "example-conversation-id"


def test_web_ai_bind_conversation_rejects_unsafe_url(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", [
        "devframe",
        "web-ai",
        "bind-conversation",
        "--conversation",
        "https://user:pass@chatgpt.com/c/abc?token=secret",
        "--runtime-dir",
        str(tmp_path / "runtime"),
        "--binding-root",
        str(tmp_path / "bindings"),
    ])

    exit_code = devframe_cli_main()
    output = capsys.readouterr()

    assert exit_code == 2
    assert "must not include credentials" in output.err


def test_web_ai_prepare_review_bundle_help(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["devframe", "web-ai", "prepare-review-bundle", "--help"])

    assert devframe_cli_main() == 0

    output = capsys.readouterr().out
    assert "Usage: devframe web-ai prepare-review-bundle" in output


def test_web_ai_prepare_review_bundle_cli_creates_valid_bundle(tmp_path, monkeypatch, capsys):
    project = tmp_path / "project"
    runtime = tmp_path / "runtime"
    (project / "docs").mkdir(parents=True)
    (project / "docs" / "README.md").write_text("# Map\n", encoding="utf-8")
    (project / "docs" / "PLAN.md").write_text("# Plan\n", encoding="utf-8")
    monkeypatch.setattr(sys, "argv", [
        "devframe",
        "web-ai",
        "prepare-review-bundle",
        "--project-root",
        str(project),
        "--runtime-dir",
        str(runtime),
        "--output-id",
        "cli-review",
        "--question",
        "Can Web GPT review this plan?",
        "--source",
        "map=docs/README.md",
        "--source",
        "plan=docs/PLAN.md",
        "--required-role",
        "map",
        "--required-role",
        "plan",
    ])

    exit_code = devframe_cli_main()
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "Prepared external review bundle: ready_for_review" in output
    manifest_path = runtime / "external-review-bundles" / "cli-review" / "PACK_MANIFEST.json"
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert data["status"] == "ready_for_review"
    assert Path(data["zip_path"]).exists()


def test_web_ai_validate_review_bundle_cli_reports_incomplete(tmp_path, monkeypatch, capsys):
    from control_plane.external_review_bundle import ReviewSource, prepare_external_review_bundle

    project = tmp_path / "project"
    runtime = tmp_path / "runtime"
    project.mkdir()
    (project / "README.md").write_text("# Map\n", encoding="utf-8")
    result = prepare_external_review_bundle(
        project_root=project,
        runtime_dir=runtime,
        output_id="cli-incomplete",
        review_question="Enough?",
        required_roles=["map", "evidence"],
        sources=[ReviewSource("README.md", role="map")],
    )
    monkeypatch.setattr(sys, "argv", [
        "devframe",
        "web-ai",
        "validate-review-bundle",
        "--zip",
        result["zip_path"],
    ])

    exit_code = devframe_cli_main()
    output = capsys.readouterr().out

    assert exit_code == 1
    data = json.loads(output)
    assert data["status"] == "context_incomplete"


def test_web_ai_import_normalizes_valid_summary(tmp_path, monkeypatch, capsys):
    runtime_dir = tmp_path / "runtime"
    source = tmp_path / "chatgpt-summary.json"
    source.write_bytes(
        ("\ufeff" + json.dumps({
            "session_id": "chatgpt-session-1",
            "provider": "chatgpt",
            "agent_role": "executor",
            "project_id": "demo-project",
            "run_id": "chatgpt-run-1",
            "task_spec_id": "TASKSPEC.json",
            "status": "completed",
            "messages": [{"message_id": "m1", "role": "user", "content_summary": "Hello"}],
            "tool_calls": [],
            "changed_files": ["src/app.py"],
            "diff_summary": "1 changed file",
            "evidence_refs": ["/tmp/evidence1"],
            "cost": {"amount": 0.01, "currency": "USD"},
            "tokens": {"input": 10, "output": 20, "total": 30},
            "gates": [],
            "actions": [],
        })).encode("utf-8"),
    )
    monkeypatch.setattr(sys, "argv", [
        "devframe",
        "web-ai",
        "import",
        str(source),
        "--runtime-dir",
        str(runtime_dir),
    ])

    exit_code = devframe_cli_main()
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "Imported web-ai session" in output
    imported = runtime_dir / "web-ai-sessions" / "chatgpt-summary.json"
    assert imported.exists()
    assert not imported.read_bytes().startswith(b"\xef\xbb\xbf")


def test_web_ai_import_accepts_powershell_utf16_summary(tmp_path, monkeypatch, capsys):
    runtime_dir = tmp_path / "runtime"
    source = tmp_path / "chatgpt-summary.json"
    source.write_text(
        json.dumps({
            "session_id": "powershell-utf16-session",
            "provider": "chatgpt",
            "agent_role": "coordinator",
            "project_id": "demo-project",
            "status": "active",
            "messages": [{
                "message_id": "m1",
                "role": "user",
                "content_summary": "PowerShell redirection wrote this JSON as UTF-16.",
            }],
            "tool_calls": [],
            "actions": ["review-imported-session"],
        }),
        encoding="utf-16",
    )
    monkeypatch.setattr(sys, "argv", [
        "devframe",
        "web-ai",
        "import",
        str(source),
        "--runtime-dir",
        str(runtime_dir),
    ])

    exit_code = devframe_cli_main()
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "Imported web-ai session" in output
    imported = runtime_dir / "web-ai-sessions" / "chatgpt-summary.json"
    data = json.loads(imported.read_text(encoding="utf-8"))
    assert data["session_id"] == "powershell-utf16-session"
    assert not imported.read_bytes().startswith(b"\xff\xfe")


def test_web_ai_import_rejects_raw_transcript_fields(tmp_path, monkeypatch, capsys):
    runtime_dir = tmp_path / "runtime"
    source = tmp_path / "bad-summary.json"
    source.write_text(
        json.dumps({
            "session_id": "bad-session",
            "provider": "chatgpt",
            "raw_transcript": "secret raw text",
            "messages": [],
            "tool_calls": [],
            "changed_files": [],
            "diff_summary": "",
            "evidence_refs": [],
            "cost": {},
            "tokens": {},
            "gates": [],
            "actions": [],
        }),
        encoding="utf-8",
    )
    monkeypatch.setattr(sys, "argv", [
        "devframe",
        "web-ai",
        "import",
        str(source),
        "--runtime-dir",
        str(runtime_dir),
    ])

    exit_code = devframe_cli_main()
    output = capsys.readouterr()

    assert exit_code == 1
    assert "raw transcript field" in output.err
    assert not (runtime_dir / "web-ai-sessions" / "bad-summary.json").exists()


def test_web_ai_import_rejects_nested_raw_message_content(tmp_path, monkeypatch, capsys):
    runtime_dir = tmp_path / "runtime"
    source = tmp_path / "bad-message-summary.json"
    source.write_text(
        json.dumps({
            "session_id": "bad-message-session",
            "provider": "chatgpt",
            "messages": [
                {
                    "message_id": "m1",
                    "role": "assistant",
                    "content_summary": "Summarized answer.",
                    "content": "Full browser transcript should not be persisted.",
                },
            ],
            "tool_calls": [],
            "changed_files": [],
            "diff_summary": "",
            "evidence_refs": [],
            "cost": {},
            "tokens": {},
            "gates": [],
            "actions": [],
        }),
        encoding="utf-8",
    )
    monkeypatch.setattr(sys, "argv", [
        "devframe",
        "web-ai",
        "import",
        str(source),
        "--runtime-dir",
        str(runtime_dir),
    ])

    exit_code = devframe_cli_main()
    output = capsys.readouterr()

    assert exit_code == 1
    assert "raw message field 'content'" in output.err
    assert "content_summary" in output.err
    assert not (runtime_dir / "web-ai-sessions" / "bad-message-summary.json").exists()


def test_web_ai_import_lists_through_sessions(tmp_path, monkeypatch, capsys):
    runtime_dir = tmp_path / "runtime"
    source = tmp_path / "deepseek-summary.json"
    source.write_text(
        json.dumps({
            "session_id": "deepseek-session-1",
            "provider": "deepseek",
            "agent_role": "reviewer",
            "project_id": "demo-project",
            "status": "idle",
            "messages": [],
            "tool_calls": [],
            "changed_files": [],
            "evidence_refs": [],
            "gates": [],
            "actions": [],
        }),
        encoding="utf-8",
    )
    monkeypatch.setattr(sys, "argv", [
        "devframe",
        "web-ai",
        "import",
        str(source),
        "--runtime-dir",
        str(runtime_dir),
    ])
    assert devframe_cli_main() == 0

    monkeypatch.setattr(sys, "argv", [
        "devframe",
        "sessions",
        "--runtime-dir",
        str(runtime_dir),
    ])

    exit_code = devframe_cli_main()
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "provider=deepseek" in output
    assert "status=idle" in output


def test_web_ai_bind_chrome_imports_runtime_session(tmp_path, monkeypatch, capsys):
    from control_plane import chrome_binding_probe

    runtime_dir = tmp_path / "runtime"

    def fake_fetch(cdp_endpoint):
        return (
            {"Browser": "Chrome/149.0.7827.155"},
            [{"type": "page", "title": "ChatGPT", "url": "https://chatgpt.com/"}],
        )

    monkeypatch.setattr(chrome_binding_probe, "fetch_chrome_debugger_state", fake_fetch)
    monkeypatch.setattr(sys, "argv", [
        "devframe",
        "web-ai",
        "bind-chrome",
        "--runtime-dir",
        str(runtime_dir),
        "--project",
        "demo-project",
    ])

    exit_code = devframe_cli_main()
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "Chrome Web AI Binding" in output
    assert "Imported Chrome web AI session" in output
    imported = runtime_dir / "web-ai-sessions" / "chatgpt-chrome-binding.json"
    assert imported.exists()
    data = json.loads(imported.read_text(encoding="utf-8"))
    assert data["provider"] == "chatgpt"
    assert data["native_refs"]["runtime"] == "chrome-cdp-binding"

    monkeypatch.setattr(sys, "argv", [
        "devframe",
        "sessions",
        "--runtime-dir",
        str(runtime_dir),
    ])
    assert devframe_cli_main() == 0

    sessions_output = capsys.readouterr().out
    assert "provider=chatgpt" in sessions_output
    assert "status=active" in sessions_output


def test_code_setup_exposes_rdgoal_console_script():
    setup_text = (REPO_ROOT / "packages" / "control-plane" / "setup.py").read_text(encoding="utf-8")

    assert '"devframe=control_plane.cli:main"' in setup_text
    assert '"rdgoal=control_plane.rdgoal_cli:main"' in setup_text


def test_web_ai_submit_review_dry_run_is_default(tmp_path, monkeypatch, capsys):
    zip_path = tmp_path / "review.zip"
    zip_path.write_bytes(b"fake zip")
    monkeypatch.setattr(sys, "argv", [
        "devframe",
        "web-ai",
        "submit-review",
        "--zip",
        str(zip_path),
        "--conversation",
        "https://chatgpt.com/c/test",
    ])

    exit_code = devframe_cli_main()
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "dry_run" in output
    assert "success=True" in output


def test_web_ai_submit_review_help_mentions_prompt_encodings(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["devframe", "web-ai", "submit-review", "--help"])

    assert devframe_cli_main() == 0

    output = capsys.readouterr().out
    assert "UTF-8/UTF-8-SIG or UTF-16 BOM" in output


def test_web_ai_record_mcp_result_help(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["devframe", "web-ai", "record-mcp-result", "--help"])

    assert devframe_cli_main() == 0

    output = capsys.readouterr().out
    assert "Usage: devframe web-ai record-mcp-result" in output
    assert "--conversation" in output
    assert "--tool-name" in output
    assert "--status" in output
    assert "--origin" in output
    assert "--outcome" in output
    assert "--connector-app-id" in output
    assert "--result" in output
    assert "--runtime-dir" in output


def test_web_ai_record_mcp_result_completed_server_config(tmp_path, monkeypatch, capsys):
    runtime_dir = tmp_path / "runtime"
    monkeypatch.setattr(sys, "argv", [
        "devframe",
        "web-ai",
        "record-mcp-result",
        "--conversation", "https://chatgpt.com/c/abc123",
        "--tool-name", "server_config",
        "--status", "completed",
        "--result", "server_config returned adapter config",
        "--runtime-dir", str(runtime_dir),
    ])

    exit_code = devframe_cli_main()
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "Recorded MCP result" in output
    assert "status    : completed" in output
    sessions = list((runtime_dir / "web-ai-sessions").glob("*.json"))
    assert len(sessions) == 1
    data = json.loads(sessions[0].read_text(encoding="utf-8"))
    assert data["provider"] == "chatgpt"
    assert data["status"] == "completed"
    assert data["tool_calls"][0]["name"] == "server_config"
    assert data["tool_calls"][0]["status"] == "completed"
    assert Path(data["tool_calls"][0]["evidence_ref"]).exists()
    assert data["native_refs"]["source_runtime"] == "chatgpt-web-mcp"
    assert data["native_refs"]["runtime"] == "chatgpt-web-mcp"
    assert data["native_refs"]["tool_name"] == "server_config"
    assert data["native_refs"]["conversation_url"] == "https://chatgpt.com/c/abc123"
    assert len(data["evidence_refs"]) == 1
    assert Path(data["evidence_refs"][0]).exists()
    evidence = json.loads(Path(data["evidence_refs"][0]).read_text(encoding="utf-8"))
    assert evidence["tool_name"] == "server_config"
    assert evidence["status"] == "completed"
    assert evidence["result_summary"] == "server_config returned adapter config"


def test_web_ai_record_mcp_result_blocked_open_current_workspace(tmp_path, monkeypatch, capsys):
    runtime_dir = tmp_path / "runtime"
    monkeypatch.setattr(sys, "argv", [
        "devframe",
        "web-ai",
        "record-mcp-result",
        "--conversation", "https://chatgpt.com/c/def456",
        "--tool-name", "open_current_workspace",
        "--status", "blocked",
        "--marker", "openai-safety",
        "--result", "Blocked by OpenAI safety policy",
        "--runtime-dir", str(runtime_dir),
    ])

    exit_code = devframe_cli_main()
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "Recorded MCP result" in output
    assert "status    : blocked" in output
    sessions = list((runtime_dir / "web-ai-sessions").glob("*.json"))
    assert len(sessions) == 1
    data = json.loads(sessions[0].read_text(encoding="utf-8"))
    assert data["status"] == "blocked"
    assert data["tool_calls"][0]["name"] == "open_current_workspace"
    assert data["tool_calls"][0]["status"] == "blocked"
    assert data["native_refs"]["source_runtime"] == "chatgpt-web-mcp"
    assert data["native_refs"]["marker"] == "openai-safety"
    evidence = json.loads(Path(data["evidence_refs"][0]).read_text(encoding="utf-8"))
    assert evidence["status"] == "blocked"
    assert evidence["marker"] == "openai-safety"


def test_web_ai_record_mcp_result_rejects_unsafe_conversation_url(tmp_path, monkeypatch, capsys):
    runtime_dir = tmp_path / "runtime"
    monkeypatch.setattr(sys, "argv", [
        "devframe",
        "web-ai",
        "record-mcp-result",
        "--conversation", "https://user:pass@chatgpt.com/c/abc?token=secret",
        "--tool-name", "server_config",
        "--status", "completed",
        "--result", "should not reach this",
        "--runtime-dir", str(runtime_dir),
    ])

    exit_code = devframe_cli_main()
    output = capsys.readouterr()

    assert exit_code == 2
    assert "conversation_url must not include credentials" in output.err or "conversation_url must not include query strings" in output.err
    assert not (runtime_dir / "web-ai-sessions").exists()


def test_web_ai_record_mcp_result_with_optional_output_fields(tmp_path, monkeypatch, capsys):
    runtime_dir = tmp_path / "runtime"
    monkeypatch.setattr(sys, "argv", [
        "devframe",
        "web-ai",
        "record-mcp-result",
        "--conversation", "https://chatgpt.com/c/ghi789",
        "--tool-name", "server_config",
        "--status", "completed",
        "--provider", "chatgpt",
        "--project", "my-project",
        "--connector-name", "codexpro",
        "--connector-app-id", "asdk_app_test",
        "--marker", "test-run",
        "--result", "adapter config retrieved",
        "--output-id", "out-1",
        "--output-name", "server_adapter",
        "--runtime-dir", str(runtime_dir),
    ])

    exit_code = devframe_cli_main()

    assert exit_code == 0
    sessions = list((runtime_dir / "web-ai-sessions").glob("*.json"))
    assert len(sessions) == 1
    data = json.loads(sessions[0].read_text(encoding="utf-8"))
    assert data["native_refs"]["connector_name"] == "codexpro"
    assert data["native_refs"]["connector_app_id"] == "asdk_app_test"
    assert data["native_refs"]["marker"] == "test-run"
    assert data["native_refs"]["output_id"] == "out-1"
    assert data["native_refs"]["output_name"] == "server_adapter"
    evidence = json.loads(Path(data["evidence_refs"][0]).read_text(encoding="utf-8"))
    assert evidence["connector_name"] == "codexpro"
    assert evidence["connector_app_id"] == "asdk_app_test"
    assert evidence["output_id"] == "out-1"
    assert evidence["output_name"] == "server_adapter"


def test_web_ai_record_mcp_result_web_host_no_result_handoff_to_agent(tmp_path, monkeypatch, capsys):
    runtime_dir = tmp_path / "runtime"
    monkeypatch.setattr(sys, "argv", [
        "devframe",
        "web-ai",
        "record-mcp-result",
        "--conversation", "https://chatgpt.com/c/handoff123",
        "--tool-name", "handoff_to_agent",
        "--status", "web_host_no_result",
        "--result", "Web host did not return a result; handoff plan stuck.",
        "--runtime-dir", str(runtime_dir),
    ])

    exit_code = devframe_cli_main()
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "Recorded MCP result" in output
    sessions = list((runtime_dir / "web-ai-sessions").glob("*.json"))
    assert len(sessions) == 1
    data = json.loads(sessions[0].read_text(encoding="utf-8"))
    assert data["provider"] == "chatgpt"
    assert data["status"] == "blocked"
    assert data["tool_calls"][0]["name"] == "handoff_to_agent"
    assert data["tool_calls"][0]["status"] == "blocked"
    assert Path(data["tool_calls"][0]["evidence_ref"]).exists()
    assert data["native_refs"]["source_runtime"] == "chatgpt-web-mcp"
    assert data["native_refs"]["runtime"] == "chatgpt-web-mcp"
    assert data["native_refs"]["origin"] == "web_host"
    assert data["native_refs"]["outcome"] == "no_result"
    assert len(data["evidence_refs"]) == 1
    assert Path(data["evidence_refs"][0]).exists()
    evidence = json.loads(Path(data["evidence_refs"][0]).read_text(encoding="utf-8"))
    assert evidence["tool_name"] == "handoff_to_agent"
    assert evidence["status"] == "web_host_no_result"
    assert evidence["origin"] == "web_host"
    assert evidence["outcome"] == "no_result"
    assert "handoff plan stuck" in evidence["result_summary"]


def test_web_ai_record_mcp_result_local_mcp_completed_handoff_to_agent(tmp_path, monkeypatch, capsys):
    runtime_dir = tmp_path / "runtime"
    monkeypatch.setattr(sys, "argv", [
        "devframe",
        "web-ai",
        "record-mcp-result",
        "--conversation", "https://chatgpt.com/c/local-handoff",
        "--tool-name", "handoff_to_agent",
        "--status", "local_mcp_completed",
        "--provider", "codexpro",
        "--result", "Direct local MCP JSON-RPC handoff succeeded.",
        "--runtime-dir", str(runtime_dir),
    ])

    exit_code = devframe_cli_main()
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "Recorded MCP result" in output
    sessions = list((runtime_dir / "web-ai-sessions").glob("*.json"))
    assert len(sessions) == 1
    data = json.loads(sessions[0].read_text(encoding="utf-8"))
    assert data["provider"] == "codexpro"
    assert data["status"] == "completed"
    assert data["tool_calls"][0]["name"] == "handoff_to_agent"
    assert data["tool_calls"][0]["status"] == "completed"
    assert Path(data["tool_calls"][0]["evidence_ref"]).exists()
    assert data["native_refs"]["source_runtime"] == "codexpro-web-mcp"
    assert data["native_refs"]["runtime"] == "codexpro-web-mcp"
    assert data["native_refs"]["origin"] == "local_mcp"
    assert data["native_refs"]["outcome"] == "completed"
    assert len(data["evidence_refs"]) == 1
    assert Path(data["evidence_refs"][0]).exists()
    evidence = json.loads(Path(data["evidence_refs"][0]).read_text(encoding="utf-8"))
    assert evidence["tool_name"] == "handoff_to_agent"
    assert evidence["status"] == "local_mcp_completed"
    assert evidence["origin"] == "local_mcp"
    assert evidence["outcome"] == "completed"
    assert "Direct local MCP" in evidence["result_summary"]


def test_web_ai_record_mcp_result_explicit_origin_local_mcp_completed(tmp_path, monkeypatch, capsys):
    runtime_dir = tmp_path / "runtime"
    monkeypatch.setattr(sys, "argv", [
        "devframe",
        "web-ai",
        "record-mcp-result",
        "--conversation", "https://chatgpt.com/c/local-handoff",
        "--tool-name", "handoff_to_agent",
        "--status", "local_mcp_completed",
        "--origin", "local_mcp",
        "--outcome", "completed",
        "--provider", "codexpro",
        "--result", "Direct local MCP JSON-RPC handoff succeeded.",
        "--runtime-dir", str(runtime_dir),
    ])

    exit_code = devframe_cli_main()
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "Recorded MCP result" in output
    sessions = list((runtime_dir / "web-ai-sessions").glob("*.json"))
    assert len(sessions) == 1
    data = json.loads(sessions[0].read_text(encoding="utf-8"))
    assert data["native_refs"]["origin"] == "local_mcp"
    assert data["native_refs"]["outcome"] == "completed"
    evidence = json.loads(Path(data["evidence_refs"][0]).read_text(encoding="utf-8"))
    assert evidence["origin"] == "local_mcp"
    assert evidence["outcome"] == "completed"


def test_web_ai_record_mcp_result_explicit_outcome_no_result(tmp_path, monkeypatch, capsys):
    runtime_dir = tmp_path / "runtime"
    monkeypatch.setattr(sys, "argv", [
        "devframe",
        "web-ai",
        "record-mcp-result",
        "--conversation", "https://chatgpt.com/c/handoff123",
        "--tool-name", "handoff_to_agent",
        "--status", "web_host_no_result",
        "--outcome", "no_result",
        "--result", "Web host did not return a result; handoff plan stuck.",
        "--runtime-dir", str(runtime_dir),
    ])

    exit_code = devframe_cli_main()
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "Recorded MCP result" in output
    sessions = list((runtime_dir / "web-ai-sessions").glob("*.json"))
    assert len(sessions) == 1
    data = json.loads(sessions[0].read_text(encoding="utf-8"))
    assert data["native_refs"]["origin"] == "web_host"
    assert data["native_refs"]["outcome"] == "no_result"
    evidence = json.loads(Path(data["evidence_refs"][0]).read_text(encoding="utf-8"))
    assert evidence["origin"] == "web_host"
    assert evidence["outcome"] == "no_result"
    assert "handoff plan stuck" in evidence["result_summary"]


def test_web_ai_record_task_intake_help(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["devframe", "web-ai", "record-task-intake", "--help"])

    assert devframe_cli_main() == 0

    output = capsys.readouterr().out
    assert "Usage: devframe web-ai record-task-intake" in output
    assert "--conversation" in output
    assert "--task-title" in output
    assert "--task-summary" in output
    assert "--priority" in output
    assert "--suggested-agent" in output
    assert "--runtime-dir" in output


def test_web_ai_record_task_intake_success(tmp_path, monkeypatch, capsys):
    runtime_dir = tmp_path / "runtime"
    monkeypatch.setattr(sys, "argv", [
        "devframe",
        "web-ai",
        "record-task-intake",
        "--conversation", "https://chatgpt.com/c/intake123",
        "--task-title", "Add login page",
        "--task-summary", "Web GPT wants a login page with OAuth.",
        "--priority", "high",
        "--suggested-agent", "opencode",
        "--runtime-dir", str(runtime_dir),
    ])

    exit_code = devframe_cli_main()
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "Recorded task intake" in output
    assert "status    : idle" in output
    sessions = list((runtime_dir / "web-ai-sessions").glob("*.json"))
    assert len(sessions) == 1
    data = json.loads(sessions[0].read_text(encoding="utf-8"))
    assert data["provider"] == "chatgpt"
    assert data["status"] == "idle"
    assert data["tool_calls"][0]["name"] == "task_intake"
    assert data["tool_calls"][0]["status"] == "completed"
    assert Path(data["tool_calls"][0]["evidence_ref"]).exists()
    assert data["native_refs"]["source_runtime"] == "chatgpt-web-mcp"
    assert data["native_refs"]["tool_name"] == "task_intake"
    assert data["native_refs"]["origin"] == "web_host"
    assert data["native_refs"]["outcome"] == "task_intake_recorded"
    assert len(data["actions"]) == 1
    assert isinstance(data["actions"][0], str)
    assert "Execute task intake 'Add login page' through local DevFrame Code or @go" in data["actions"][0]
    assert data["native_refs"]["task_title"] == "Add login page"
    assert data["native_refs"]["priority"] == "high"
    assert data["native_refs"]["suggested_agent"] == "opencode"
    assert data["native_refs"]["intake_id"] == data["session_id"]
    evidence = json.loads(Path(data["evidence_refs"][0]).read_text(encoding="utf-8"))
    assert evidence["task_title"] == "Add login page"
    assert evidence["task_summary"] == "Web GPT wants a login page with OAuth."
    assert evidence["priority"] == "high"
    assert evidence["suggested_agent"] == "opencode"
    assert evidence["origin"] == "web_host"
    assert evidence["outcome"] == "task_intake_recorded"
    assert evidence["intake_id"] == data["session_id"]

    state = build_visual_control_plane_state(runtime_dir)
    session = next(item for item in state["sessions"] if item["session_id"] == data["session_id"])
    assert session["binding_id"] == "chatgpt-web-mcp"
    assert session["tool_calls"][0]["name"] == "task_intake"
    action = next(item for item in state["next_actions"] if item["source_id"] == data["session_id"])
    assert action["source_type"] == "session"
    assert action["priority"] == "high"
    assert action["status"] == "ready"
    assert action["label"] == "Execute Web GPT task intake through local agents."
    assert "Execute task intake" in action["detail"]
    assert action["command"] == f"devframe web-ai dispatch-task-intakes --intake-id {data['session_id']}"


def test_web_ai_record_task_intake_rejects_unsafe_conversation_url(tmp_path, monkeypatch, capsys):
    runtime_dir = tmp_path / "runtime"
    monkeypatch.setattr(sys, "argv", [
        "devframe",
        "web-ai",
        "record-task-intake",
        "--conversation", "https://user:pass@chatgpt.com/c/abc?token=secret",
        "--task-title", "Bad intake",
        "--task-summary", "Should be rejected.",
        "--runtime-dir", str(runtime_dir),
    ])

    exit_code = devframe_cli_main()
    output = capsys.readouterr()

    assert exit_code == 2
    assert "conversation_url must not include credentials" in output.err or "conversation_url must not include query strings" in output.err
    assert not (runtime_dir / "web-ai-sessions").exists()


def test_web_ai_record_task_intake_rejects_url_fragment(tmp_path, monkeypatch, capsys):
    runtime_dir = tmp_path / "runtime"
    monkeypatch.setattr(sys, "argv", [
        "devframe",
        "web-ai",
        "record-task-intake",
        "--conversation", "https://chatgpt.com/c/abc#private",
        "--task-title", "Bad intake",
        "--task-summary", "Should be rejected.",
        "--runtime-dir", str(runtime_dir),
    ])

    exit_code = devframe_cli_main()
    output = capsys.readouterr()

    assert exit_code == 2
    assert "conversation_url must not include fragments" in output.err
    assert not (runtime_dir / "web-ai-sessions").exists()


def test_web_ai_record_task_intake_rejects_empty_task_fields(tmp_path, monkeypatch, capsys):
    runtime_dir = tmp_path / "runtime"
    monkeypatch.setattr(sys, "argv", [
        "devframe",
        "web-ai",
        "record-task-intake",
        "--conversation", "https://chatgpt.com/c/abc",
        "--task-title", " ",
        "--task-summary", " ",
        "--runtime-dir", str(runtime_dir),
    ])

    exit_code = devframe_cli_main()
    output = capsys.readouterr()

    assert exit_code == 2
    assert "task_title is required" in output.err
    assert not (runtime_dir / "web-ai-sessions").exists()


def test_record_mcp_result_project_summary_creates_session_action_item(tmp_path):
    from control_plane.web_ai_mcp_recorder import record_mcp_result

    runtime_dir = tmp_path / "runtime"
    result = record_mcp_result(
        runtime_dir=runtime_dir,
        provider="chatgpt",
        project="demo-project",
        conversation_url="https://chatgpt.com/c/projsum123",
        tool_name="project_summary",
        status="completed",
        result_summary="Bounded project summary imported from Web GPT.",
    )

    assert result["status"] == "completed"
    session_path = Path(result["session_path"])
    assert session_path.exists()
    data = json.loads(session_path.read_text(encoding="utf-8"))
    assert data["tool_calls"][0]["name"] == "project_summary"
    assert len(data["actions"]) == 1
    assert "Review the imported bounded project summary" in data["actions"][0]

    state = build_visual_control_plane_state(runtime_dir)
    action = next(
        item for item in state["next_actions"]
        if item["source_id"] == data["session_id"]
    )
    assert action["source_type"] == "session"
    assert action["status"] == "open"
    assert action["priority"] == "medium"
    assert action["label"] == "Review imported project summary for next local handoff or task intake."
    assert "command" not in action


def test_record_mcp_result_project_summary_blocked_has_no_action_text(tmp_path):
    from control_plane.web_ai_mcp_recorder import record_mcp_result

    runtime_dir = tmp_path / "runtime"
    result = record_mcp_result(
        runtime_dir=runtime_dir,
        provider="chatgpt",
        project="demo-project",
        conversation_url="https://chatgpt.com/c/projsum-blk",
        tool_name="project_summary",
        status="blocked",
        result_summary="Project summary blocked due to missing bounds.",
    )

    assert result["outcome"] == "blocked"
    session_path = Path(result["session_path"])
    assert session_path.exists()
    data = json.loads(session_path.read_text(encoding="utf-8"))
    assert data["actions"] == []

    state = build_visual_control_plane_state(runtime_dir)
    matching = [
        item for item in state["next_actions"]
        if item["source_id"] == data["session_id"]
    ]
    assert matching == []


def test_record_mcp_result_project_summary_no_result_has_no_action_item(tmp_path):
    from control_plane.web_ai_mcp_recorder import record_mcp_result

    runtime_dir = tmp_path / "runtime"
    result = record_mcp_result(
        runtime_dir=runtime_dir,
        provider="chatgpt",
        project="demo-project",
        conversation_url="https://chatgpt.com/c/projsum-nr",
        tool_name="project_summary",
        status="web_host_no_result",
        result_summary="No project summary available from Web GPT.",
    )

    assert result["outcome"] == "no_result"
    session_path = Path(result["session_path"])
    assert session_path.exists()
    data = json.loads(session_path.read_text(encoding="utf-8"))
    assert data["actions"] == []

    state = build_visual_control_plane_state(runtime_dir)
    matching = [
        item for item in state["next_actions"]
        if item["source_id"] == data["session_id"]
    ]
    assert matching == []


def test_record_mcp_result_server_config_has_no_action_text(tmp_path):
    from control_plane.web_ai_mcp_recorder import record_mcp_result

    runtime_dir = tmp_path / "runtime"
    result = record_mcp_result(
        runtime_dir=runtime_dir,
        provider="chatgpt",
        project="demo-project",
        conversation_url="https://chatgpt.com/c/srvcfg123",
        tool_name="server_config",
        status="completed",
        result_summary="Server config retrieved.",
    )

    session_path = Path(result["session_path"])
    data = json.loads(session_path.read_text(encoding="utf-8"))
    assert data["actions"] == []


def test_atgo_help_is_available(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["devframe", "atgo", "--help"])

    assert devframe_cli_main() == 0

    output = capsys.readouterr().out
    assert "Usage: devframe atgo" in output
    assert "--project" in output
    assert "--runtime-dir" in output
    assert "--target" in output
    assert "--execute" in output
    assert "--auto-finalize" in output


def test_atgo_prepare_creates_evidence_dir(tmp_path, monkeypatch, capsys):
    project_root = tmp_path / "demo-project"
    runtime_dir = tmp_path / "runtime"
    project_root.mkdir()
    monkeypatch.setattr(sys, "argv", [
        "devframe",
        "atgo",
        "Add a small @go bridge.",
        "--project",
        str(project_root),
        "--runtime-dir",
        str(runtime_dir),
        "--target",
        "src/cli.py",
    ])

    exit_code = devframe_cli_main()
    output = capsys.readouterr().out
    metadata_path = next((runtime_dir / "go-runs").glob("*/go-run.json"))
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    evidence_dir = runtime_dir / "atgo-runs" / metadata["go_run_id"]

    assert exit_code == 0
    assert "DevFrame @go" in output
    assert metadata["go_run_id"] in output
    assert "devframe code status" in output
    assert f"Finalize  : tools/go_evidence.py finalize {evidence_dir} --team-runtime-dir {runtime_dir}" in output
    assert evidence_dir.exists()
    assert (evidence_dir / "task-spec.md").exists()
    assert (evidence_dir / "chain-evidence.json").exists()
    assert metadata["agents"][0]["targets"] == ["src/cli.py"]


def test_atgo_finalize_command_quotes_paths_with_spaces(tmp_path, monkeypatch, capsys):
    project_root = tmp_path / "demo project"
    runtime_dir = tmp_path / "runtime dir"
    project_root.mkdir()
    monkeypatch.setattr(sys, "argv", [
        "devframe",
        "atgo",
        "Add a small @go bridge.",
        "--project",
        str(project_root),
        "--runtime-dir",
        str(runtime_dir),
        "--target",
        "src/cli.py",
    ])

    exit_code = devframe_cli_main()
    output = capsys.readouterr().out
    metadata_path = next((runtime_dir / "go-runs").glob("*/go-run.json"))
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    evidence_dir = runtime_dir / "atgo-runs" / metadata["go_run_id"]
    chain_evidence = json.loads((evidence_dir / "chain-evidence.json").read_text(encoding="utf-8"))
    expected_command = (
        f'tools/go_evidence.py finalize "{evidence_dir}" '
        f'--team-runtime-dir "{runtime_dir}"'
    )

    assert exit_code == 0
    assert f"Finalize  : {expected_command}" in output
    finalize = chain_evidence["next_commands"]["finalize"]
    assert finalize["command"] == expected_command
    assert finalize["command_args"] == [
        "tools/go_evidence.py",
        "finalize",
        str(evidence_dir),
        "--team-runtime-dir",
        str(runtime_dir),
    ]


def test_atgo_auto_finalize_requires_execute(tmp_path, monkeypatch, capsys):
    project_root = tmp_path / "demo-project"
    runtime_dir = tmp_path / "runtime"
    project_root.mkdir()
    monkeypatch.setattr(sys, "argv", [
        "devframe",
        "atgo",
        "Add a small @go bridge.",
        "--project",
        str(project_root),
        "--runtime-dir",
        str(runtime_dir),
        "--auto-finalize",
    ])

    exit_code = devframe_cli_main()
    captured = capsys.readouterr()

    assert exit_code == 2
    assert "--auto-finalize requires --execute" in captured.err
    assert not runtime_dir.exists()


def test_atgo_execute_auto_finalize_skips_without_review_evidence(tmp_path, monkeypatch, capsys):
    project_root = tmp_path / "demo-project"
    runtime_dir = tmp_path / "runtime"
    project_root.mkdir()

    import control_plane.go_dispatch as go_dispatch_module

    def fake_execute_go_run(runtime_root, run_id, **_kwargs):
        result = go_dispatch_module.load_go_run_result(runtime_root, run_id)
        result.execute = True
        result.status = "passed"
        return result

    monkeypatch.setattr(go_dispatch_module, "execute_go_run", fake_execute_go_run)
    monkeypatch.setattr(sys, "argv", [
        "devframe",
        "atgo",
        "Add a small @go bridge.",
        "--project",
        str(project_root),
        "--runtime-dir",
        str(runtime_dir),
        "--target",
        "src/cli.py",
        "--execute",
        "--auto-finalize",
    ])

    exit_code = devframe_cli_main()
    output = capsys.readouterr().out
    metadata_path = next((runtime_dir / "go-runs").glob("*/go-run.json"))
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    evidence_dir = runtime_dir / "atgo-runs" / metadata["go_run_id"]

    assert exit_code == 0
    assert "Auto-finalize: skipped" in output
    assert "missing required review evidence" in output
    assert f"Finalize     : tools/go_evidence.py finalize {evidence_dir} --team-runtime-dir {runtime_dir}" in output
    assert not (evidence_dir / "final-verdict.json").exists()
    assert not (runtime_dir / "team-events.jsonl").exists()

    index = build_run_index(runtime_dir)
    atgo_record = next(entry["record"] for entry in index["runs"] if entry["adapter_id"] == "atgo_evidence")
    assert atgo_record["acceptance_state"] == "deferred"


def test_atgo_auto_finalize_skip_quotes_paths_with_spaces(tmp_path, monkeypatch, capsys):
    project_root = tmp_path / "demo project"
    runtime_dir = tmp_path / "runtime dir"
    project_root.mkdir()

    import control_plane.go_dispatch as go_dispatch_module

    def fake_execute_go_run(runtime_root, run_id, **_kwargs):
        result = go_dispatch_module.load_go_run_result(runtime_root, run_id)
        result.execute = True
        result.status = "passed"
        return result

    monkeypatch.setattr(go_dispatch_module, "execute_go_run", fake_execute_go_run)
    monkeypatch.setattr(sys, "argv", [
        "devframe",
        "atgo",
        "Add a small @go bridge.",
        "--project",
        str(project_root),
        "--runtime-dir",
        str(runtime_dir),
        "--target",
        "src/cli.py",
        "--execute",
        "--auto-finalize",
    ])

    exit_code = devframe_cli_main()
    output = capsys.readouterr().out
    metadata_path = next((runtime_dir / "go-runs").glob("*/go-run.json"))
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    evidence_dir = runtime_dir / "atgo-runs" / metadata["go_run_id"]
    expected_command = (
        f'tools/go_evidence.py finalize "{evidence_dir}" '
        f'--team-runtime-dir "{runtime_dir}"'
    )

    assert exit_code == 0
    assert "Auto-finalize: skipped" in output
    assert f"Finalize     : {expected_command}" in output
    assert not (evidence_dir / "final-verdict.json").exists()
    assert not (runtime_dir / "team-events.jsonl").exists()


def test_atgo_execute_auto_finalize_records_reviewed_evidence(tmp_path, monkeypatch, capsys):
    project_root = tmp_path / "demo-project"
    runtime_dir = tmp_path / "runtime"
    project_root.mkdir()

    import control_plane.go_dispatch as go_dispatch_module

    def fake_execute_go_run(runtime_root, run_id, **_kwargs):
        evidence_dir = Path(runtime_root) / "atgo-runs" / run_id
        (evidence_dir / "diff.patch").write_text("", encoding="utf-8")
        (evidence_dir / "test-output.md").write_text("1 passed\n", encoding="utf-8")
        (evidence_dir / "safety-report.json").write_text(
            json.dumps({
                "generated_at": "2026-07-08T00:00:00+00:00",
                "producer": "test",
                "command": "pytest",
                "exit_code": 0,
                "stdout": "1 passed",
            }) + "\n",
            encoding="utf-8",
        )
        (evidence_dir / "review.md").write_text("Independent review passed.\n", encoding="utf-8")
        (evidence_dir / "review.yaml").write_text(
            "\n".join([
                "reviewer_role: reviewer",
                "reviewer_id: reviewer-1",
                "executor_id: opencode",
                "verdict: pass",
                "reviewed_inputs:",
                "  - diff.patch",
                "  - test-output.md",
                "  - safety-report.json",
                "  - chain-evidence.json",
                "findings: []",
                "",
            ]),
            encoding="utf-8",
        )
        result = go_dispatch_module.load_go_run_result(runtime_root, run_id)
        result.execute = True
        result.status = "passed"
        return result

    monkeypatch.setattr(go_dispatch_module, "execute_go_run", fake_execute_go_run)
    monkeypatch.setattr(sys, "argv", [
        "devframe",
        "atgo",
        "Add a reviewed @go bridge.",
        "--project",
        str(project_root),
        "--runtime-dir",
        str(runtime_dir),
        "--target",
        "src/cli.py",
        "--execute",
        "--auto-finalize",
    ])

    exit_code = devframe_cli_main()
    output = capsys.readouterr().out
    metadata_path = next((runtime_dir / "go-runs").glob("*/go-run.json"))
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    evidence_dir = runtime_dir / "atgo-runs" / metadata["go_run_id"]

    assert exit_code == 0
    assert "Auto-finalize: tools/go_evidence.py finalize" in output
    assert "PASS" in output
    assert (evidence_dir / "final-verdict.json").exists()
    assert (runtime_dir / "team-events.jsonl").exists()

    index = build_run_index(runtime_dir)
    team_record = next(entry["record"] for entry in index["runs"] if entry["adapter_id"] == "team_events")
    assert team_record["acceptance_state"] == "final_ready"
    assert team_record["final_verdict_ref"]["final_state"] == "final_ready"


def test_web_ai_import_task_intakes_help(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["devframe", "web-ai", "import-task-intakes", "--help"])

    assert devframe_cli_main() == 0

    output = capsys.readouterr().out
    assert "Usage: devframe web-ai import-task-intakes" in output
    assert "--project-root" in output
    assert "--runtime-dir" in output
    assert "--provider" in output


def test_web_ai_import_task_intakes_creates_session_action(tmp_path, monkeypatch, capsys):
    runtime_dir = tmp_path / "runtime"
    project_root = tmp_path / "demo-project"
    intake_dir = project_root / ".ai-bridge" / "task-intakes"
    intake_dir.mkdir(parents=True)
    intake_path = intake_dir / "20260625T072143-intake-test-99e9c2.json"
    intake_path.write_text(
        json.dumps({
            "id": "20260625T072143-intake-test-99e9c2",
            "title": "Add login page",
            "summary": "Web GPT wants a login page with OAuth.",
            "priority": "high",
            "suggested_agent": "opencode",
            "conversation_url": "https://chatgpt.com/c/intake123",
            "marker": "test-run",
            "workspace_id": "ws-1",
            "root": str(project_root),
            "created_at": "2025-06-25T07:21:43Z",
            "status": "queued",
        }),
        encoding="utf-8",
    )

    monkeypatch.setattr(sys, "argv", [
        "devframe",
        "web-ai",
        "import-task-intakes",
        "--project-root", str(project_root),
        "--runtime-dir", str(runtime_dir),
        "--provider", "codexpro",
        "--project", "demo-project",
        "--connector-name", "DevFrame",
    ])

    exit_code = devframe_cli_main()
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "Imported 1 task intake" in output
    assert "skipped 0" in output
    assert "Add login page" in output

    sessions = list((runtime_dir / "web-ai-sessions").glob("*.json"))
    assert len(sessions) == 1
    data = json.loads(sessions[0].read_text(encoding="utf-8"))
    assert data["provider"] == "codexpro"
    assert data["status"] == "idle"
    assert data["tool_calls"][0]["name"] == "task_intake"
    assert data["native_refs"]["source_runtime"] == "codexpro-web-mcp"
    assert data["native_refs"]["outcome"] == "task_intake_recorded"
    assert data["native_refs"]["intake_id"] == "20260625T072143-intake-test-99e9c2"
    assert data["native_refs"]["intake_path"] == ".ai-bridge/task-intakes/20260625T072143-intake-test-99e9c2.json"
    assert data["native_refs"]["output_id"] == "20260625T072143-intake-test-99e9c2"
    assert data["native_refs"]["output_name"] == ".ai-bridge/task-intakes/20260625T072143-intake-test-99e9c2.json"
    assert data["native_refs"]["priority"] == "high"
    assert data["native_refs"]["task_title"] == "Add login page"
    assert data["native_refs"]["connector_name"] == "DevFrame"

    evidence_files = list((runtime_dir / "web-ai-mcp-results").glob("*.json"))
    assert len(evidence_files) == 1
    evidence = json.loads(evidence_files[0].read_text(encoding="utf-8"))
    assert evidence["output_id"] == "20260625T072143-intake-test-99e9c2"
    assert evidence["output_name"] == ".ai-bridge/task-intakes/20260625T072143-intake-test-99e9c2.json"

    from control_plane.visual_state import build_visual_control_plane_state

    state = build_visual_control_plane_state(runtime_dir)
    action = next(item for item in state["next_actions"] if item["source_id"] == data["session_id"])
    assert action["priority"] == "high"
    assert action["status"] == "ready"
    assert action["command"] == "devframe web-ai dispatch-task-intakes --intake-id 20260625T072143-intake-test-99e9c2"
    assert action["label"] == "Execute Web GPT task intake through local agents."


def test_web_ai_import_task_intakes_skips_duplicate(tmp_path, monkeypatch, capsys):
    runtime_dir = tmp_path / "runtime"
    project_root = tmp_path / "demo-project"
    intake_dir = project_root / ".ai-bridge" / "task-intakes"
    intake_dir.mkdir(parents=True)
    intake_path = intake_dir / "intake-abc.json"
    intake_path.write_text(
        json.dumps({
            "id": "intake-abc",
            "title": "Fix login bug",
            "summary": "Fix OAuth redirect issue.",
            "priority": "medium",
            "suggested_agent": "opencode",
            "conversation_url": "https://chatgpt.com/c/bug123",
            "marker": "",
            "workspace_id": "ws-1",
            "root": str(project_root),
            "created_at": "2025-06-25T08:00:00Z",
            "status": "queued",
        }),
        encoding="utf-8",
    )

    argv = [
        "devframe",
        "web-ai",
        "import-task-intakes",
        "--project-root", str(project_root),
        "--runtime-dir", str(runtime_dir),
    ]
    monkeypatch.setattr(sys, "argv", argv)
    first_exit = devframe_cli_main()
    capsys.readouterr()

    monkeypatch.setattr(sys, "argv", argv)
    second_exit = devframe_cli_main()
    output = capsys.readouterr().out

    assert first_exit == 0
    assert second_exit == 0
    assert "Imported 0 task intake" in output
    assert "skipped 1" in output
    assert "duplicate" in output

    sessions = list((runtime_dir / "web-ai-sessions").glob("*.json"))
    assert len(sessions) == 1


def test_web_ai_import_task_intakes_skips_malformed(tmp_path, monkeypatch, capsys):
    runtime_dir = tmp_path / "runtime"
    project_root = tmp_path / "demo-project"
    intake_dir = project_root / ".ai-bridge" / "task-intakes"
    intake_dir.mkdir(parents=True)

    (intake_dir / "bad-json.json").write_text("not valid json", encoding="utf-8")
    (intake_dir / "empty-id.json").write_text(json.dumps({
        "title": "No ID",
        "summary": "Missing required id field.",
    }), encoding="utf-8")
    (intake_dir / "empty-title.json").write_text(json.dumps({
        "id": "no-title-1",
        "title": "",
        "summary": "Has empty title.",
    }), encoding="utf-8")
    (intake_dir / "valid.json").write_text(json.dumps({
        "id": "valid-1",
        "title": "Valid task",
        "summary": "This one should import.",
        "priority": "low",
        "suggested_agent": "codex",
    }), encoding="utf-8")

    monkeypatch.setattr(sys, "argv", [
        "devframe",
        "web-ai",
        "import-task-intakes",
        "--project-root", str(project_root),
        "--runtime-dir", str(runtime_dir),
    ])

    exit_code = devframe_cli_main()
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "Imported 1 task intake" in output
    assert "skipped 3" in output
    assert "invalid JSON" in output
    assert "missing or empty id field" in output
    assert "missing or empty title field" in output

    sessions = list((runtime_dir / "web-ai-sessions").glob("*.json"))
    assert len(sessions) == 1


def test_web_ai_import_task_intakes_empty_project(tmp_path, monkeypatch, capsys):
    runtime_dir = tmp_path / "runtime"
    project_root = tmp_path / "no-intakes-project"
    project_root.mkdir()

    monkeypatch.setattr(sys, "argv", [
        "devframe",
        "web-ai",
        "import-task-intakes",
        "--project-root", str(project_root),
        "--runtime-dir", str(runtime_dir),
    ])

    exit_code = devframe_cli_main()
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "No intake files found" in output or "Imported 0 task intake" in output


def test_web_ai_dispatch_task_intakes_prepares_go_run(tmp_path, monkeypatch, capsys):
    runtime_dir = tmp_path / "runtime"
    project_root = tmp_path / "demo-project"
    intake_dir = project_root / ".ai-bridge" / "task-intakes"
    intake_dir.mkdir(parents=True)
    (intake_dir / "intake-web-gpt.json").write_text(json.dumps({
        "id": "intake-web-gpt",
        "title": "Wire GPT task into agent queue",
        "summary": "Create a local @go dispatch from the Web GPT MCP task intake.",
        "priority": "high",
        "suggested_agent": "opencode",
        "conversation_url": "https://chatgpt.com/c/intake123",
        "marker": "dispatch-test",
        "status": "queued",
    }), encoding="utf-8")

    calls = []

    class FakeGoResult:
        go_run_id = "go-demo-123"
        status = "queued"
        metadata_path = str(runtime_dir / "go-runs" / "go-demo-123.json")

    def fake_run_go_dispatch(**kwargs):
        calls.append(kwargs)
        return FakeGoResult()

    import control_plane.go_dispatch as go_dispatch_module

    monkeypatch.setattr(go_dispatch_module, "run_go_dispatch", fake_run_go_dispatch)
    monkeypatch.setattr(sys, "argv", [
        "devframe",
        "web-ai",
        "dispatch-task-intakes",
        "--project-root", str(project_root),
        "--runtime-dir", str(runtime_dir),
        "--provider", "codexpro",
        "--project", "demo-project",
        "--connector-name", "DevFrame",
        "--agents", "1",
    ])

    exit_code = devframe_cli_main()
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "dispatched 1" in output
    assert "go-demo-123" in output
    assert calls
    assert calls[0]["project_path"] == project_root.resolve()
    assert calls[0]["agents"] == 1
    assert calls[0]["execute"] is False
    assert "Wire GPT task into agent queue" in calls[0]["requirement"]

    session_file = next((runtime_dir / "web-ai-sessions").glob("*.json"))
    session = json.loads(session_file.read_text(encoding="utf-8"))
    assert session["native_refs"]["dispatch_go_run_id"] == "go-demo-123"
    assert session["native_refs"]["dispatch_status"] == "queued"
    assert "Inspect dispatched @go/OpenCode run go-demo-123" in session["actions"][0]

    state = build_visual_control_plane_state(runtime_dir)
    action = next(item for item in state["next_actions"] if item["source_id"] == session["session_id"])
    assert action["status"] == "info"
    assert action["label"] == "Web GPT task intake dispatched to local agents."


def test_web_ai_dispatch_task_intakes_skips_existing_go_run(tmp_path, monkeypatch, capsys):
    runtime_dir = tmp_path / "runtime"
    sessions_dir = runtime_dir / "web-ai-sessions"
    sessions_dir.mkdir(parents=True)
    (sessions_dir / "already.json").write_text(json.dumps({
        "session_id": "already",
        "provider": "codexpro",
        "status": "queued",
        "actions": ["Inspect dispatched @go/OpenCode run go-existing."],
        "native_refs": {
            "outcome": "task_intake_recorded",
            "intake_id": "intake-existing",
            "task_title": "Already dispatched",
            "suggested_agent": "opencode",
            "dispatch_go_run_id": "go-existing",
        },
    }), encoding="utf-8")
    project_root = tmp_path / "demo-project"
    project_root.mkdir()

    import control_plane.go_dispatch as go_dispatch_module

    def fail_run_go_dispatch(**_kwargs):
        raise AssertionError("run_go_dispatch should not be called")

    monkeypatch.setattr(go_dispatch_module, "run_go_dispatch", fail_run_go_dispatch)
    monkeypatch.setattr(sys, "argv", [
        "devframe",
        "web-ai",
        "dispatch-task-intakes",
        "--project-root", str(project_root),
        "--runtime-dir", str(runtime_dir),
    ])

    exit_code = devframe_cli_main()
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "dispatched 0" in output
    assert "already dispatched go_run_id=go-existing" in output


def test_code_preview_shows_methodology_for_tdd_goal(tmp_path, monkeypatch, capsys):
    project_root = tmp_path / "demo-project"
    runtime_dir = tmp_path / "runtime"
    project_root.mkdir()
    monkeypatch.setattr(sys, "argv", [
        "devframe",
        "code",
        "@tdd Add a TDD feature.",
        "--project",
        str(project_root),
        "--runtime-dir",
        str(runtime_dir),
        "--agents",
        "1",
        "--target",
        "src/app.py",
        "--preview",
    ])

    exit_code = devframe_cli_main()
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "DevFrame coding preview" in output
    assert "methodology" in output
    assert "tdd" in output
    assert "goal         : Add a TDD feature." in output
    assert not runtime_dir.exists()


def test_code_stores_methodology_metadata_for_tdd_goal(tmp_path, monkeypatch, capsys):
    project_root = tmp_path / "demo-project"
    runtime_dir = tmp_path / "runtime"
    project_root.mkdir()
    monkeypatch.setattr(sys, "argv", [
        "devframe",
        "code",
        "@tdd Add a TDD feature.",
        "--project",
        str(project_root),
        "--runtime-dir",
        str(runtime_dir),
        "--target",
        "src/app.py",
    ])

    exit_code = devframe_cli_main()
    output = capsys.readouterr().out
    metadata_path = next((runtime_dir / "go-runs").glob("*/go-run.json"))
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))

    assert exit_code == 0
    assert "DevFrame Code session" in output
    assert metadata["requirement"] == "Add a TDD feature."
    assert metadata["methodology"]["skill_id"] == "tdd"
    assert metadata["methodology"]["title"] == "tdd"
    assert metadata["agents"][0]["methodology"]["skill_id"] == "tdd"


def test_code_status_shows_methodology_for_tdd_goal(tmp_path, monkeypatch, capsys):
    project_root = tmp_path / "demo-project"
    runtime_dir = tmp_path / "runtime"
    project_root.mkdir()
    monkeypatch.setattr(sys, "argv", [
        "devframe",
        "code",
        "@tdd Add a TDD feature.",
        "--project",
        str(project_root),
        "--runtime-dir",
        str(runtime_dir),
        "--target",
        "src/app.py",
    ])
    assert devframe_cli_main() == 0
    metadata_path = next((runtime_dir / "go-runs").glob("*/go-run.json"))
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    capsys.readouterr()
    monkeypatch.setattr(sys, "argv", [
        "devframe",
        "code",
        "status",
        "--runtime-dir",
        str(runtime_dir),
    ])

    exit_code = devframe_cli_main()
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "DevFrame Code status" in output
    assert metadata["go_run_id"] in output
    assert "methodology" in output
    assert "tdd" in output


def test_code_preview_strips_leading_whitespace_tdd_trigger(tmp_path, monkeypatch, capsys):
    project_root = tmp_path / "demo-project"
    runtime_dir = tmp_path / "runtime"
    project_root.mkdir()
    monkeypatch.setattr(sys, "argv", [
        "devframe",
        "code",
        "   @tdd Add a TDD feature.",
        "--project",
        str(project_root),
        "--runtime-dir",
        str(runtime_dir),
        "--target",
        "src/app.py",
        "--preview",
    ])

    exit_code = devframe_cli_main()
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "methodology" in output
    assert "tdd" in output
    assert "goal         :    Add a TDD feature." in output or "goal         : Add a TDD feature." in output


def test_atgo_prepare_records_tdd_methodology(tmp_path, monkeypatch, capsys):
    project_root = tmp_path / "demo-project"
    runtime_dir = tmp_path / "runtime"
    project_root.mkdir()
    monkeypatch.setattr(sys, "argv", [
        "devframe",
        "atgo",
        "@tdd Add a small TDD bridge.",
        "--project",
        str(project_root),
        "--runtime-dir",
        str(runtime_dir),
        "--target",
        "src/cli.py",
    ])

    exit_code = devframe_cli_main()
    output = capsys.readouterr().out
    metadata_path = next((runtime_dir / "go-runs").glob("*/go-run.json"))
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    evidence_dir = runtime_dir / "atgo-runs" / metadata["go_run_id"]
    task_spec = (evidence_dir / "task-spec.md").read_text(encoding="utf-8")

    assert exit_code == 0
    assert "DevFrame @go" in output
    assert metadata["requirement"] == "Add a small TDD bridge."
    assert metadata["methodology"]["skill_id"] == "tdd"
    assert "- **Methodology**: tdd" in task_spec


def test_atgo_prepare_writes_methodology_to_chain_evidence(tmp_path, monkeypatch, capsys):
    project_root = tmp_path / "demo-project"
    runtime_dir = tmp_path / "runtime"
    project_root.mkdir()
    monkeypatch.setattr(sys, "argv", [
        "devframe",
        "atgo",
        "@tdd Add a small TDD bridge.",
        "--project",
        str(project_root),
        "--runtime-dir",
        str(runtime_dir),
        "--target",
        "src/cli.py",
    ])

    exit_code = devframe_cli_main()
    output = capsys.readouterr().out
    metadata_path = next((runtime_dir / "go-runs").glob("*/go-run.json"))
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    evidence_dir = runtime_dir / "atgo-runs" / metadata["go_run_id"]
    chain_evidence = json.loads((evidence_dir / "chain-evidence.json").read_text(encoding="utf-8"))

    assert exit_code == 0
    _schema_validator("schemas/agent-runtime/chain-evidence.schema.json").validate(chain_evidence)
    assert chain_evidence.get("methodology", {}).get("skill_id") == "tdd"
    finalize = chain_evidence["next_commands"]["finalize"]
    assert finalize["command"] == (
        f"tools/go_evidence.py finalize {evidence_dir} --team-runtime-dir {runtime_dir}"
    )
    assert finalize["command_args"] == [
        "tools/go_evidence.py",
        "finalize",
        str(evidence_dir),
        "--team-runtime-dir",
        str(runtime_dir),
    ]
    assert finalize["authority"] == "guidance_only"
    assert finalize["creates_acceptance"] is False
    assert finalize["requires_independent_review"] is True
    assert finalize["manual"] is True


def test_methodology_dispatch_exposes_required_traits():
    from control_plane.methodology_dispatch import METHODOLOGY_DISPATCH

    tdd = METHODOLOGY_DISPATCH.get("tdd")
    assert tdd is not None
    assert tdd["skill_id"] == "tdd"
    assert tdd["title"] == "tdd"
    assert tdd["triggers"] == ["@tdd"]
    assert tdd["require_red_green_evidence"] is True
    assert tdd["display_label"] == "@tdd"


def test_methodology_dispatch_exposes_go_profiles_for_agent_acceptance():
    from control_plane.methodology_dispatch import METHODOLOGY_DISPATCH

    agent = METHODOLOGY_DISPATCH.get("agent-acceptance")
    assert agent is not None
    assert agent.get("profiles")
    assert len(agent["profiles"]) == 4
    go_read = next(p for p in agent["profiles"] if p["selected_trigger_label"] == "@go read")
    assert go_read["profile_id"] == "read-only"
    assert go_read["read_only"] is True
    assert go_read["network_enabled"] is False
    go_risky = next(p for p in agent["profiles"] if p["selected_trigger_label"] == "@go risky")
    assert go_risky["profile_id"] == "ai-risky"
    assert go_risky["read_only"] is False
    assert go_risky["network_enabled"] is True


def test_methodology_dispatch_resolve_strips_tdd_trigger():
    from control_plane.methodology_dispatch import resolve_methodology

    effective, methodology = resolve_methodology("@tdd Add a TDD feature.")
    assert effective == "Add a TDD feature."
    assert methodology is not None
    assert methodology["skill_id"] == "tdd"
    assert methodology["require_red_green_evidence"] is True
    assert methodology["display_label"] == "@tdd"


def test_methodology_dispatch_resolve_returns_none_for_non_methodology():
    from control_plane.methodology_dispatch import resolve_methodology

    effective, methodology = resolve_methodology("Add a plain feature.")
    assert effective == "Add a plain feature."
    assert methodology is None


def test_methodology_dispatch_resolve_matches_go_read_profile():
    from control_plane.methodology_dispatch import resolve_methodology

    effective, methodology = resolve_methodology("@go read the source.")
    assert effective == "the source."
    assert methodology is not None
    assert methodology["skill_id"] == "agent-acceptance"
    assert methodology["selected_trigger"] == "@go read"
    assert methodology["dispatch_profile"] == "read-only"
    assert methodology["read_only"] is True
    assert methodology["network_enabled"] is False


def test_methodology_dispatch_resolve_matches_go_edit_profile():
    from control_plane.methodology_dispatch import resolve_methodology

    effective, methodology = resolve_methodology("@go edit the code.")
    assert effective == "the code."
    assert methodology is not None
    assert methodology["selected_trigger"] == "@go edit"
    assert methodology["dispatch_profile"] == "ai-dev"
    assert methodology["read_only"] is False
    assert methodology["network_enabled"] is False


def test_methodology_dispatch_resolve_matches_go_risky_profile():
    from control_plane.methodology_dispatch import resolve_methodology

    effective, methodology = resolve_methodology("@go risky deploy.")
    assert effective == "deploy."
    assert methodology is not None
    assert methodology["selected_trigger"] == "@go risky"
    assert methodology["dispatch_profile"] == "ai-risky"
    assert methodology["read_only"] is False
    assert methodology["network_enabled"] is True


def test_methodology_dispatch_resolve_matches_go_profile():
    from control_plane.methodology_dispatch import resolve_methodology

    effective, methodology = resolve_methodology("@go do the thing.")
    assert effective == "do the thing."
    assert methodology is not None
    assert methodology["selected_trigger"] == "@go"
    assert methodology["dispatch_profile"] == "ai-dev"
    assert methodology["read_only"] is False
    assert methodology["network_enabled"] is False


def test_code_preview_shows_methodology_for_go_read_goal(tmp_path, monkeypatch, capsys):
    project_root = tmp_path / "demo-project"
    runtime_dir = tmp_path / "runtime"
    project_root.mkdir()
    monkeypatch.setattr(sys, "argv", [
        "devframe",
        "code",
        "@go read the source.",
        "--project",
        str(project_root),
        "--runtime-dir",
        str(runtime_dir),
        "--agents",
        "1",
        "--target",
        "src/app.py",
        "--preview",
    ])

    exit_code = devframe_cli_main()
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "DevFrame coding preview" in output
    assert "methodology" in output
    assert "agent-acceptance" in output
    assert "goal         : the source." in output
    assert not runtime_dir.exists()


def test_code_stores_methodology_metadata_for_go_read_goal(tmp_path, monkeypatch, capsys):
    project_root = tmp_path / "demo-project"
    runtime_dir = tmp_path / "runtime"
    project_root.mkdir()
    monkeypatch.setattr(sys, "argv", [
        "devframe",
        "code",
        "@go read the source.",
        "--project",
        str(project_root),
        "--runtime-dir",
        str(runtime_dir),
        "--target",
        "src/app.py",
    ])

    exit_code = devframe_cli_main()
    output = capsys.readouterr().out
    metadata_path = next((runtime_dir / "go-runs").glob("*/go-run.json"))
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))

    assert exit_code == 0
    assert "DevFrame Code session" in output
    assert metadata["requirement"] == "the source."
    assert metadata["methodology"]["skill_id"] == "agent-acceptance"
    assert metadata["methodology"]["selected_trigger"] == "@go read"
    assert metadata["methodology"]["dispatch_profile"] == "read-only"
    assert metadata["methodology"]["read_only"] is True
    assert metadata["agents"][0]["methodology"]["skill_id"] == "agent-acceptance"
    assert metadata["agents"][0]["methodology"]["selected_trigger"] == "@go read"
