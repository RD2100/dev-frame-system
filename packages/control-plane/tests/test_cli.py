import sys
from pathlib import Path

from control_plane.cli import main as devframe_cli_main


REPO_ROOT = Path(__file__).resolve().parents[3]


def test_doctor_passes_for_packaged_resources(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["devframe", "doctor"])

    assert devframe_cli_main() == 0


def test_root_help_is_available(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["devframe", "--help"])

    assert devframe_cli_main() == 0

    output = capsys.readouterr().out
    assert "DevFrame Control Plane CLI" in output
    assert "devframe dashboard serve" in output


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
