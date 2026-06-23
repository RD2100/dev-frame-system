import json
import sys
from pathlib import Path

from control_plane.cli import main as devframe_cli_main
from control_plane.visual_state import build_visual_control_plane_state


REPO_ROOT = Path(__file__).resolve().parents[3]


def test_doctor_passes_for_packaged_resources(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["devframe", "doctor"])

    assert devframe_cli_main() == 0


def test_root_help_is_available(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["devframe", "--help"])

    assert devframe_cli_main() == 0

    output = capsys.readouterr().out
    assert "DevFrame Control Plane CLI" in output
    assert "devframe go <project> <goal>" in output
    assert "devframe dashboard serve" in output


def test_go_help_is_available(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["devframe", "go", "--help"])

    assert devframe_cli_main() == 0

    output = capsys.readouterr().out
    assert "Usage: devframe go <project> <goal>" in output


def test_go_prepares_parallel_coding_agent_packets(tmp_path, monkeypatch, capsys):
    project_root = tmp_path / "demo-project"
    runtime_dir = tmp_path / "runtime"
    project_root.mkdir()
    monkeypatch.setattr(sys, "argv", [
        "devframe",
        "go",
        str(project_root),
        "Build a Codex-like programming tool MVP.",
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
    assert "opencode run -m stepfun/step-3.7-flash" in output
    assert "devframe dashboard serve --runtime-dir" in output
    assert len(metadata_files) == 1
    assert metadata["status"] == "queued"
    assert len(metadata["agents"]) == 2
    assert metadata["agents"][0]["targets"] == ["packages/control-plane/control_plane/cli.py"]
    assert metadata["agents"][1]["targets"] == ["packages/control-plane/control_plane/go_dispatch.py"]
    assert all(Path(agent["packet_dir"]).exists() for agent in metadata["agents"])
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
        "- (none)\\n"
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
    assert metadata["execute"] is True
    assert metadata["status"] == "passed"
    assert {agent["worker_status"] for agent in metadata["agents"]} == {"passed"}
    assert all(Path(agent["report_path"]).exists() for agent in metadata["agents"])
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


def test_setup_exposes_rdgoal_console_script():
    setup_text = (REPO_ROOT / "packages" / "control-plane" / "setup.py").read_text(encoding="utf-8")

    assert '"devframe=control_plane.cli:main"' in setup_text
    assert '"rdgoal=control_plane.rdgoal_cli:main"' in setup_text
