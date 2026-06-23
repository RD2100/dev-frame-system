import json
import io
import subprocess
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
    assert "devframe code [\"<goal>\" | --prompt-file <path>]" in output
    assert "devframe go <project> <goal>" in output
    assert "devframe dashboard serve" in output


def test_code_help_is_available(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["devframe", "code", "--help"])

    assert devframe_cli_main() == 0

    output = capsys.readouterr().out
    assert "Usage: devframe code [\"<goal>\" | --prompt-file <path>]" in output
    assert "--prompt-file" in output
    assert "--agents" in output
    assert "--max-agents" in output
    assert "--changed" in output
    assert "--preview" in output
    assert "--dashboard" in output


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
    assert "Backend      : /go concurrent coding-agent dispatch" in output
    assert "status       : queued" in output
    assert "agents       : 1" in output
    assert "Dashboard: devframe dashboard serve --runtime-dir" in output
    assert metadata["project_root"] == str(project_root.resolve())
    assert metadata["requirement"] == "Add a small CLI feature."
    assert metadata["agents"][0]["targets"] == ["src/cli.py"]
    assert len(state["go_runs"]) == 1
    assert state["go_runs"][0]["agents"][0]["agent_id"] == "coding-agent-1"


def test_code_reads_goal_from_prompt_file(tmp_path, monkeypatch, capsys):
    project_root = tmp_path / "demo-project"
    runtime_dir = tmp_path / "runtime"
    prompt_file = tmp_path / "task.md"
    project_root.mkdir()
    prompt_file.write_text("Build a Codex-like shell.\n\nUse changed files only.\n", encoding="utf-8")
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
    assert metadata["requirement"] == "Build a Codex-like shell.\n\nUse changed files only."


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
    prompt_file.write_text("Build a Codex-like shell.\n", encoding="utf-8")
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
    assert "  command: opencode run -m stepfun/step-3.7-flash --agent build" in output
    assert "You are coding shard 1/2." in output
    assert "- coding-agent-2 shard=2/2" in output
    assert "  - src/b.py" in output
    assert "You are coding shard 2/2." in output
    assert "No packets were created." in output
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
    assert "--preview" in output


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
    assert "  bytes  : 20" in output
    assert "opencode run -m stepfun/step-3.7-flash" in output
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


def test_setup_exposes_rdgoal_console_script():
    setup_text = (REPO_ROOT / "packages" / "control-plane" / "setup.py").read_text(encoding="utf-8")

    assert '"devframe=control_plane.cli:main"' in setup_text
    assert '"rdgoal=control_plane.rdgoal_cli:main"' in setup_text
