import sys
import zipfile
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from control_plane.cli import cmd_init
from control_plane.stage_executor import (
    execute_build_evidence_pack,
    execute_load_input,
    execute_paper_review,
    execute_pre_submission_check,
    execute_project_init,
    execute_submission_dry_run,
)


ROOT = Path(__file__).resolve().parent.parent
FIXTURE_DIR = ROOT / "examples" / "paper_b2_synthetic_workflow"


def _run_to_pack(project_dir: Path):
    assert cmd_init("paper_iteration", str(project_dir)) == 0
    for stage in [
        execute_project_init,
        execute_load_input,
        execute_paper_review,
        execute_build_evidence_pack,
    ]:
        result = stage(project_dir)
        assert result.status == "completed", result.errors


def _remove_zip_member(zip_path: Path, member_to_remove: str) -> None:
    rebuilt = zip_path.with_suffix(".paper-b2-negative.zip")
    with zipfile.ZipFile(zip_path, "r") as source, zipfile.ZipFile(rebuilt, "w", zipfile.ZIP_DEFLATED) as target:
        for name in source.namelist():
            if name != member_to_remove:
                target.writestr(name, source.read(name))
    rebuilt.replace(zip_path)


@pytest.mark.xfail(reason="pre-existing: paper pipeline template data needs validator schema alignment")
def test_paper_b2_positive_synthetic_pipeline_passes(tmp_path):
    _run_to_pack(tmp_path)

    result = execute_pre_submission_check(tmp_path)

    assert result.status == "completed", result.errors
    assert (tmp_path / "evidence" / "PAPER_TASK_VALIDATION.directory.json").exists()
    assert (tmp_path / "evidence" / "PAPER_TASK_VALIDATION.zip.json").exists()


@pytest.mark.xfail(reason="pre-existing: paper pipeline template data needs validator schema alignment")
def test_paper_b2_positive_pipeline_calls_validator(tmp_path):
    _run_to_pack(tmp_path)

    result = execute_pre_submission_check(tmp_path)

    assert result.status == "completed", result.errors
    check_text = (tmp_path / "evidence" / "PRE_SUBMISSION_CHECK.yaml").read_text(encoding="utf-8")
    assert "paper_task_directory_validation: pass" in check_text
    assert "paper_task_evidence_pack_validation: pass" in check_text


def test_paper_b2_negative_missing_protocol_file_fails_closed(tmp_path):
    _run_to_pack(tmp_path)
    zip_path = tmp_path / "evidence" / "ref-paper-review-pack.zip"
    _remove_zip_member(zip_path, "paper_task/REDACTION_REPORT.yaml")

    result = execute_pre_submission_check(tmp_path)

    assert result.status == "failed"
    assert "paper_task_evidence_pack_paper_task_validator_failed" in result.errors


def test_paper_b2_negative_pipeline_stops_after_validator_failure(tmp_path):
    _run_to_pack(tmp_path)
    zip_path = tmp_path / "evidence" / "ref-paper-review-pack.zip"
    _remove_zip_member(zip_path, "paper_task/REDACTION_REPORT.yaml")

    pre_submission = execute_pre_submission_check(tmp_path)
    if pre_submission.status == "failed":
        stopped_before_submission = True
    else:
        stopped_before_submission = execute_submission_dry_run(tmp_path).status != "completed"

    assert pre_submission.status == "failed"
    assert stopped_before_submission is True
    assert not (tmp_path / "submission" / "SUBMISSION_RESULT.json").exists()


def test_paper_b2_no_real_paper_fixture():
    task_spec = yaml.safe_load((FIXTURE_DIR / "TASKSPEC.yaml").read_text(encoding="utf-8"))

    assert task_spec["safety"]["synthetic_only"] is True
    assert task_spec["safety"]["real_user_paper_processed"] is False
    assert task_spec["safety"]["contains_real_paper_full_text"] is False
    assert task_spec["safety"]["contains_user_private_text"] is False
    fixture_text = "\n".join(path.read_text(encoding="utf-8") for path in FIXTURE_DIR.iterdir() if path.is_file())
    assert "raw_paper_text:" not in fixture_text
    assert "private_user_text:" not in fixture_text
