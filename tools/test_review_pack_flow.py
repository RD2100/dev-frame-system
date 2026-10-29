from __future__ import annotations

import json
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

TOOLS_DIR = Path(__file__).resolve().parent
HELPER = TOOLS_DIR / "review_pack_flow.py"

sys.path.insert(0, str(TOOLS_DIR))
import review_pack_flow as rpf


@pytest.fixture
def report_dir(tmp_path):
    path = tmp_path / "report"
    path.mkdir()
    return path


@pytest.fixture
def populated(report_dir):
    (report_dir / "COMMAND_LOG.md").write_text("log content", encoding="utf-8")
    (report_dir / "SAFETY_CHECK.md").write_text("safety content", encoding="utf-8")
    (report_dir / "READ_SET.json").write_text('{"files":["a.py"]}', encoding="utf-8")
    nested = report_dir / "gpt-review"
    nested.mkdir()
    (nested / "GPT_REVIEW_RESULT.md").write_text("review", encoding="utf-8")
    return report_dir


@pytest.fixture
def captured_review(tmp_path):
    path = tmp_path / "captured-review.md"
    path.write_text(
        "\n".join(
            [
                "REVIEW_RUN_ID: run-accepted",
                "",
                "YAML",
                "REVIEW_RUN_ID: run-accepted",
                "overall_judgment: accepted",
                "",
                "controlled_review_persistence_helper_execution:",
                "  accepted: yes",
                "",
                "next_stage:",
                "  approved_to_prepare_review_pack: yes",
                "  approved_to_execute_without_additional_gpt_review: no",
                "",
                "broader_real_chain_testing:",
                "  unblocked: no",
                "  status: still_blocked",
                "",
                "production_promotion:",
                "  approved: no",
                "",
                "hardcoded_driver_replacement:",
                "  approved: no",
                "",
                "guard_removal:",
                "  approved: no",
                "",
                "evidence_cleanup:",
                "  approved: no",
                "",
                "human_required: no",
                "",
                "复审结论",
                "Accepted for this stage only.",
            ]
        ),
        encoding="utf-8",
    )
    return path


def test_help_exits_zero():
    result = subprocess.run(["python", str(HELPER), "--help"], capture_output=True, text=True, timeout=10)
    assert result.returncode == 0
    assert "usage" in result.stdout.lower()


def test_manifest_contains_hashes_and_nested_paths(populated):
    rpf.generate_manifest(populated, "task-1", "run-1")
    text = (populated / "PACK_MANIFEST.md").read_text(encoding="utf-8")
    assert "Task ID: task-1" in text
    assert "Review Run ID: run-1" in text
    assert "| COMMAND_LOG.md |" in text
    assert "| gpt-review/GPT_REVIEW_RESULT.md |" in text
    assert rpf.sha256_hex(populated / "COMMAND_LOG.md") in text


def test_expected_pack_entry_names_includes_manifest(populated):
    names = rpf.expected_pack_entry_names(populated, "run-1.zip")
    assert "PACK_MANIFEST.md" in names
    assert "COMMAND_LOG.md" in names


def test_zip_contains_manifest_and_nested_paths(populated):
    rpf.generate_manifest(populated, "task-1", "run-1")
    zip_path = rpf.create_zip(populated, "run-1.zip")
    with zipfile.ZipFile(zip_path, "r") as archive:
        names = set(archive.namelist())
    assert "PACK_MANIFEST.md" in names
    assert "COMMAND_LOG.md" in names
    assert "gpt-review/GPT_REVIEW_RESULT.md" in names


def test_validate_passes_consistent_pack(populated):
    rpf.generate_manifest(populated, "task-1", "run-1")
    rpf.create_zip(populated, "run-1.zip")
    result = rpf.validate_pack(populated, "task-1", "run-1", "run-1.zip")
    assert result["validation_verdict"] == "passed"
    assert result["missing_from_zip"] == []
    assert result["extra_in_zip"] == []
    assert result["hash_failures"] == []


def test_validate_fails_on_hash_mismatch(populated):
    rpf.generate_manifest(populated, "task-1", "run-1")
    (populated / "COMMAND_LOG.md").write_text("tampered", encoding="utf-8")
    result = rpf.validate_pack(populated, "task-1", "run-1")
    assert result["validation_verdict"] == "failed"
    assert result["hash_failures"]


def test_validate_fails_on_missing_from_zip(populated):
    rpf.generate_manifest(populated, "task-1", "run-1")
    with zipfile.ZipFile(populated / "run-1.zip", "w", zipfile.ZIP_DEFLATED) as archive:
        archive.write(populated / "COMMAND_LOG.md", "COMMAND_LOG.md")
    result = rpf.validate_pack(populated, "task-1", "run-1", "run-1.zip")
    assert result["validation_verdict"] == "failed"
    assert "PACK_MANIFEST.md" in result["missing_from_zip"]


def test_validate_fails_on_extra_in_zip(populated):
    rpf.generate_manifest(populated, "task-1", "run-1")
    with zipfile.ZipFile(populated / "run-1.zip", "w", zipfile.ZIP_DEFLATED) as archive:
        for path in rpf.iter_pack_files(populated, "run-1.zip"):
            archive.write(path, rpf.relative_name(populated, path))
        archive.writestr("ORPHAN.md", "orphan")
    result = rpf.validate_pack(populated, "task-1", "run-1", "run-1.zip")
    assert result["validation_verdict"] == "failed"
    assert "ORPHAN.md" in result["extra_in_zip"]


def test_self_referential_files_are_present_but_hash_excluded(populated):
    (populated / "OUTPUT_DIRECTORY_TREE.md").write_text("tree", encoding="utf-8")
    (populated / "VALIDATION_RESULT.json").write_text("{}", encoding="utf-8")
    rpf.generate_manifest(populated, "task-1", "run-1")
    result = rpf.validate_pack(populated, "task-1", "run-1")
    assert result["validation_verdict"] == "passed"
    assert "PACK_MANIFEST.md" in result["hash_exclusions"]
    assert "OUTPUT_DIRECTORY_TREE.md" in result["hash_exclusions"]
    assert "VALIDATION_RESULT.json" in result["hash_exclusions"]


def test_cli_full_flow_final_zip_contains_validation_result(populated):
    result = subprocess.run(
        ["python", str(HELPER), str(populated), "task-cli", "run-cli", "--zip-out", "my-pack.zip"],
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert result.returncode == 0, result.stderr + result.stdout
    validation = json.loads((populated / "VALIDATION_RESULT.json").read_text(encoding="utf-8"))
    assert validation["validation_verdict"] == "passed"
    assert validation["missing_from_zip"] == []
    assert validation["extra_in_zip"] == []
    with zipfile.ZipFile(populated / "my-pack.zip", "r") as archive:
        names = set(archive.namelist())
    assert "PACK_MANIFEST.md" in names
    assert "VALIDATION_RESULT.json" in names
    assert "PACK_MANIFEST_VERIFY.md" in names


def test_run_flow_writes_manifest_verify(populated):
    result = rpf.run_flow(populated, "task-verify", "run-verify", "verify-pack.zip", True)
    verify_path = populated / "PACK_MANIFEST_VERIFY.md"
    assert result["validation_verdict"] == "passed"
    assert verify_path.exists()
    text = verify_path.read_text(encoding="utf-8")
    assert "REVIEW_RUN_ID: run-verify" in text
    assert "validation_verdict: passed" in text
    assert "pending" not in text.lower()


def test_write_evidence_skeleton_creates_conservative_files(report_dir):
    created = rpf.write_evidence_skeleton(report_dir, "task-skel", "run-skel")
    route = json.loads((report_dir / "POST_REVIEW_ROUTE.json").read_text(encoding="utf-8"))
    names = {path.name for path in created}
    assert "TASKSPEC.md" in names
    assert "POST_REVIEW_ROUTE.json" in names
    assert route["review_submitted"] is False
    assert route["overall_judgment"] == "pending"
    assert route["full_broader_real_chain_testing_unblocked"] is False


def test_write_evidence_skeleton_refuses_existing_files(report_dir):
    (report_dir / "TASKSPEC.md").write_text("existing", encoding="utf-8")
    with pytest.raises(FileExistsError):
        rpf.write_evidence_skeleton(report_dir, "task-skel", "run-skel")


def test_cli_init_skeleton(report_dir):
    result = subprocess.run(
        ["python", str(HELPER), str(report_dir), "task-skel", "run-skel", "--init-skeleton", "--no-zip", "--no-validate"],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 0, result.stderr + result.stdout
    assert "[skeleton] wrote" in result.stdout
    assert (report_dir / "TASKSPEC.md").exists()


def test_write_workspace_status_snapshot_and_diff(report_dir):
    rpf.write_workspace_status_snapshot(report_dir, "before", status_lines=[" M one.py", "?? two.py"])
    rpf.write_workspace_status_snapshot(report_dir, "after", status_lines=[" M one.py", "?? two.py", "?? three.py"])
    diff_path = rpf.write_workspace_status_diff(report_dir)
    before_text = (report_dir / "WORKSPACE_STATUS_BEFORE.txt").read_text(encoding="utf-8")
    diff_text = diff_path.read_text(encoding="utf-8")
    assert " M one.py" in before_text
    assert "three.py" in diff_text
    assert "WORKSPACE_STATUS_BEFORE.txt" in diff_text


def test_capture_workspace_status_after_writes_diff_when_before_exists(report_dir, monkeypatch):
    (report_dir / "WORKSPACE_STATUS_BEFORE.txt").write_text(" M one.py\n", encoding="utf-8")
    monkeypatch.setattr(rpf, "read_workspace_status_lines", lambda _: [" M one.py", "?? new.py"])
    paths = rpf.capture_workspace_status(report_dir, "after", workspace_root=report_dir)
    assert any(path.name == "WORKSPACE_STATUS_AFTER.txt" for path in paths)
    assert any(path.name == "WORKSPACE_STATUS_DIFF.txt" for path in paths)


def test_capture_workspace_status_after_without_before_only_writes_after(report_dir, monkeypatch):
    monkeypatch.setattr(rpf, "read_workspace_status_lines", lambda _: [" M one.py"])
    paths = rpf.capture_workspace_status(report_dir, "after", workspace_root=report_dir)
    assert [path.name for path in paths] == ["WORKSPACE_STATUS_AFTER.txt"]
    assert not (report_dir / "WORKSPACE_STATUS_DIFF.txt").exists()


def test_cli_capture_workspace_status(report_dir):
    result = subprocess.run(
        [
            "python",
            str(HELPER),
            str(report_dir),
            "task-status",
            "run-status",
            "--capture-workspace-status",
            "before",
            "--no-zip",
            "--no-validate",
        ],
        capture_output=True,
        text=True,
        timeout=15,
        cwd=str(TOOLS_DIR.parent),
    )
    assert result.returncode == 0, result.stderr + result.stdout
    assert "[workspace-status] wrote WORKSPACE_STATUS_BEFORE.txt" in result.stdout
    assert (report_dir / "WORKSPACE_STATUS_BEFORE.txt").exists()


def test_write_supplement_pack_creates_note_and_scope(report_dir):
    inputs = {
        "supplement_items": ["WORKSPACE_STATUS_BEFORE.txt", "WORKSPACE_STATUS_AFTER.txt"],
        "workspace_scope": {
            "before_file": "WORKSPACE_STATUS_BEFORE.txt",
            "after_file": "WORKSPACE_STATUS_AFTER.txt",
            "diff_file": "WORKSPACE_STATUS_DIFF.txt",
            "preexisting_scope_note": "Root-level dirty state existed before this pilot.",
            "allowed_changed_files": ["tools/review_pack_flow.py", "tools/test_review_pack_flow.py"],
            "evidence_sources": ["WRITE_SET.json", "DIFF_SUMMARY.md"],
        },
    }
    written = rpf.write_supplement_pack(report_dir, "run-supp", inputs)
    names = {path.name for path in written}
    assert "SUPPLEMENT_NOTE.md" in names
    assert "WORKSPACE_SCOPE_EXPLANATION.md" in names
    note_text = (report_dir / "SUPPLEMENT_NOTE.md").read_text(encoding="utf-8")
    scope_text = (report_dir / "WORKSPACE_SCOPE_EXPLANATION.md").read_text(encoding="utf-8")
    assert "WORKSPACE_STATUS_BEFORE.txt" in note_text
    assert "Root-level dirty state existed before this pilot." in scope_text


def test_write_supplement_pack_fails_on_missing_inputs(report_dir):
    with pytest.raises(ValueError):
        rpf.write_supplement_pack(report_dir, "run-supp", {"supplement_items": ["only"]})


def test_cli_write_supplement_pack(report_dir, tmp_path):
    input_path = tmp_path / "supplement-input.json"
    input_path.write_text(
        json.dumps(
            {
                "supplement_items": ["SUPPLEMENT_NOTE.md", "WORKSPACE_SCOPE_EXPLANATION.md"],
                "workspace_scope": {
                    "before_file": "WORKSPACE_STATUS_BEFORE.txt",
                    "after_file": "WORKSPACE_STATUS_AFTER.txt",
                    "diff_file": "WORKSPACE_STATUS_DIFF.txt",
                    "preexisting_scope_note": "Pre-existing dirty state note.",
                    "allowed_changed_files": ["tools/review_pack_flow.py", "tools/test_review_pack_flow.py"],
                    "evidence_sources": ["WRITE_SET.json", "CODE_CHANGE_EXECUTION_RESULT.json"],
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    result = subprocess.run(
        [
            "python",
            str(HELPER),
            str(report_dir),
            "task-supp",
            "run-supp",
            "--write-supplement-pack",
            str(input_path),
            "--no-zip",
            "--no-validate",
        ],
        capture_output=True,
        text=True,
        timeout=15,
        cwd=str(TOOLS_DIR.parent),
    )
    assert result.returncode == 0, result.stderr + result.stdout
    assert "[supplement-pack] wrote SUPPLEMENT_NOTE.md, WORKSPACE_SCOPE_EXPLANATION.md" in result.stdout
    assert (report_dir / "SUPPLEMENT_NOTE.md").exists()


def test_load_review_decision_requires_exact_run_id(captured_review):
    _, decision = rpf.load_review_decision(captured_review, "run-accepted")
    assert decision["REVIEW_RUN_ID"] == "run-accepted"
    with pytest.raises(ValueError):
        rpf.load_review_decision(captured_review, "run-mismatch")


def test_persist_review_result_writes_route_and_decision(populated, captured_review):
    result = rpf.persist_review_result(
        populated,
        "task-review",
        "run-accepted",
        captured_review,
        "review-pack.zip",
        True,
    )
    route = json.loads((populated / "POST_REVIEW_ROUTE.json").read_text(encoding="utf-8"))
    decision_text = (populated / "GPT_REVIEW_DECISION.md").read_text(encoding="utf-8")
    assert result["validation_verdict"] == "passed"
    assert route["review_submitted"] is True
    assert route["overall_judgment"] == "accepted"
    assert route["controlled_review_persistence_helper_execution_accepted"] is True
    assert route["full_broader_real_chain_testing_unblocked"] is False
    assert route["broader_real_chain_testing_status"] == "still_blocked"
    assert route["next_stage_approved_to_prepare_review_pack"] is True
    assert route["next_stage_approved_to_execute_without_additional_gpt_review"] is False
    assert "overall_judgment: accepted" in decision_text
    assert (populated / "GPT_REVIEW_RESULT.md").exists()
    with zipfile.ZipFile(populated / "review-pack.zip", "r") as archive:
        names = set(archive.namelist())
    assert "GPT_REVIEW_RESULT.md" in names
    assert "GPT_REVIEW_DECISION.md" in names
    assert "POST_REVIEW_ROUTE.json" in names


def test_cli_persist_review(populated, captured_review):
    result = subprocess.run(
        [
            "python",
            str(HELPER),
            str(populated),
            "task-cli",
            "run-accepted",
            "--zip-out",
            "persist-pack.zip",
            "--persist-review",
            str(captured_review),
        ],
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert result.returncode == 0, result.stderr + result.stdout
    route = json.loads((populated / "POST_REVIEW_ROUTE.json").read_text(encoding="utf-8"))
    assert route["review_run_id"] == "run-accepted"
    assert "GPT_REVIEW_RESULT.md" in result.stdout


def test_manifest_and_validation_counts_match_after_persist_review(populated, captured_review):
    result = rpf.persist_review_result(populated, "task-count", "run-accepted", captured_review, "count-pack.zip", True)
    with zipfile.ZipFile(populated / "count-pack.zip", "r") as archive:
        names = {name for name in archive.namelist()}
    assert result["zip_entry_count"] == len(names)
    assert result["manifest_file_count"] == len(names)


def test_manifest_and_validation_counts_match_with_helper_artifacts(report_dir):
    rpf.write_evidence_skeleton(report_dir, "task-artifacts", "run-artifacts")
    (report_dir / "OUTPUT_DIRECTORY_TREE.md").write_text("tree", encoding="utf-8")
    rpf.write_workspace_status_snapshot(report_dir, "before", status_lines=[" M one.py"])
    rpf.write_workspace_status_snapshot(report_dir, "after", status_lines=[" M one.py", "?? two.py"])
    rpf.write_workspace_status_diff(report_dir)
    rpf.write_supplement_pack(
        report_dir,
        "run-artifacts",
        {
            "supplement_items": ["WORKSPACE_STATUS_BEFORE.txt", "WORKSPACE_STATUS_AFTER.txt"],
            "workspace_scope": {
                "before_file": "WORKSPACE_STATUS_BEFORE.txt",
                "after_file": "WORKSPACE_STATUS_AFTER.txt",
                "diff_file": "WORKSPACE_STATUS_DIFF.txt",
                "preexisting_scope_note": "Pre-existing root-level dirty state.",
                "allowed_changed_files": ["tools/review_pack_flow.py", "tools/test_review_pack_flow.py"],
                "evidence_sources": ["WRITE_SET.json", "DIFF_SUMMARY.md"],
            },
        },
    )
    result = rpf.run_flow(report_dir, "task-artifacts", "run-artifacts", "artifacts-pack.zip", True)
    with zipfile.ZipFile(report_dir / "artifacts-pack.zip", "r") as archive:
        names = {name for name in archive.namelist()}
    assert result["zip_entry_count"] == len(names)
    assert result["manifest_file_count"] == len(names)


def test_cli_no_zip(populated):
    result = subprocess.run(
        ["python", str(HELPER), str(populated), "task-cli", "run-cli", "--no-zip"],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 0
    assert "skipped (--no-zip)" in result.stdout


def test_cli_no_validate(populated):
    result = subprocess.run(
        ["python", str(HELPER), str(populated), "task-cli", "run-cli", "--no-validate"],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 0
    assert "skipped (--no-validate)" in result.stdout


def test_cli_json_output(populated):
    result = subprocess.run(
        ["python", str(HELPER), str(populated), "task-json", "run-json", "--no-zip", "--json"],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 0
    data = json.loads(result.stdout[result.stdout.index('{\n  "review_run_id"') :])
    assert data["task_id"] == "task-json"
    assert data["review_run_id"] == "run-json"


def test_cli_missing_dir():
    result = subprocess.run(
        ["python", str(HELPER), "/nonexistent/dir", "task-x", "run-x"],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 2
