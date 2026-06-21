import sys
from pathlib import Path

from control_plane.cli import main as devframe_cli_main


REPO_ROOT = Path(__file__).resolve().parents[3]


def test_doctor_passes_for_packaged_resources(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["devframe", "doctor"])

    assert devframe_cli_main() == 0


def test_init_code_project_generates_runnable_pipeline(tmp_path, monkeypatch):
    project_root = tmp_path / "demo-project"
    monkeypatch.setattr(sys, "argv", ["devframe", "init", "code_project", str(project_root)])

    assert devframe_cli_main() == 0

    pipeline_path = project_root / "PIPELINE.yaml"
    assert pipeline_path.exists()
    assert "{{" not in pipeline_path.read_text(encoding="utf-8")

    monkeypatch.setattr(sys, "argv", ["devframe", "run", "--pipeline", str(pipeline_path)])

    assert devframe_cli_main() == 0


def test_setup_exposes_rdgoal_console_script():
    setup_text = (REPO_ROOT / "packages" / "control-plane" / "setup.py").read_text(encoding="utf-8")

    assert '"devframe=control_plane.cli:main"' in setup_text
    assert '"rdgoal=control_plane.rdgoal_cli:main"' in setup_text
