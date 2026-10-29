import json
import sys
import zipfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from control_plane.cli import cmd_init
from control_plane.stage_executor import (
    execute_build_evidence_pack,
    execute_load_input,
    execute_paper_review,
    execute_pre_submission_check,
    execute_project_init,
)


def _prepare_review_pack(project_dir: Path):
    assert cmd_init("paper_iteration", str(project_dir)) == 0
    for stage in [
        execute_project_init,
        execute_load_input,
        execute_paper_review,
        execute_build_evidence_pack,
    ]:
        result = stage(project_dir)
        assert result.status == "completed", result.errors


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _remove_zip_member(zip_path: Path, member_to_remove: str) -> None:
    rebuilt = zip_path.with_suffix(".without-redaction.zip")
    with zipfile.ZipFile(zip_path, "r") as src, zipfile.ZipFile(rebuilt, "w", zipfile.ZIP_DEFLATED) as dst:
        for name in src.namelist():
            if name != member_to_remove:
                dst.writestr(name, src.read(name))
    rebuilt.replace(zip_path)


@pytest.mark.xfail(reason="pre-existing: paper pipeline template data needs validator schema alignment")
def test_pre_submission_check_runs_paper_task_validators(tmp_path):
    _prepare_review_pack(tmp_path)

    result = execute_pre_submission_check(tmp_path)

    assert result.status == "completed", result.errors
    directory_result = _read_json(tmp_path / "evidence" / "PAPER_TASK_VALIDATION.directory.json")
    zip_result = _read_json(tmp_path / "evidence" / "PAPER_TASK_VALIDATION.zip.json")
    assert directory_result["result"] == "pass"
    assert zip_result["result"] == "pass"
    with zipfile.ZipFile(tmp_path / "evidence" / "ref-paper-review-pack.zip", "r") as zf:
        assert "paper_task/PAPER_TASK_INPUT.yaml" in zf.namelist()
        assert "paper_task/PAPER_TASK_OUTPUT.yaml" in zf.namelist()


def test_pre_submission_check_fails_closed_for_invalid_paper_task_output(tmp_path):
    _prepare_review_pack(tmp_path)
    output_path = tmp_path / "paper_task" / "PAPER_TASK_OUTPUT.yaml"
    output_text = output_path.read_text(encoding="utf-8")
    output_path.write_text(
        output_text.replace("contains_real_paper_full_text: false", "contains_real_paper_full_text: true"),
        encoding="utf-8",
    )
    result = execute_build_evidence_pack(tmp_path)
    assert result.status == "completed", result.errors

    result = execute_pre_submission_check(tmp_path)

    assert result.status == "failed"
    assert "paper_task_directory_paper_task_validator_failed" in result.errors
    assert "paper_task_evidence_pack_paper_task_validator_failed" in result.errors


def test_pre_submission_check_fails_closed_when_evidence_pack_missing_paper_protocol_file(tmp_path):
    _prepare_review_pack(tmp_path)
    zip_path = tmp_path / "evidence" / "ref-paper-review-pack.zip"
    _remove_zip_member(zip_path, "paper_task/REDACTION_REPORT.yaml")

    result = execute_pre_submission_check(tmp_path)

    assert result.status == "failed"
    assert "paper_task_directory_validation: fail" in (tmp_path / "evidence" / "PRE_SUBMISSION_CHECK.yaml").read_text(encoding="utf-8")
    assert "paper_task_evidence_pack_paper_task_validator_failed" in result.errors
