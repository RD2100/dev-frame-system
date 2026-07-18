import hashlib
import json
import shutil
import zipfile
from pathlib import Path

from jsonschema import Draft202012Validator
from jsonschema.validators import validator_for
import pytest
import yaml

from control_plane import stage_executor
from control_plane.cli._core import cmd_pack_validate
from control_plane import paper_pipeline_gate
from control_plane.paper_pipeline_gate import (
    PaperPipelineGateResult,
    finalize_paper_project,
    scan_submission_bypass,
    validate_evidence_pack,
    validate_paper_task_source,
)
from control_plane.run_index import build_run_index


REPO_ROOT = Path(__file__).resolve().parents[3]


def _schema_without_annotations(value):
    if isinstance(value, dict):
        return {
            key: _schema_without_annotations(item)
            for key, item in value.items()
            if key not in {"description", "examples"}
        }
    if isinstance(value, list):
        return [_schema_without_annotations(item) for item in value]
    return value


def test_packaged_final_verdict_schema_matches_canonical_contract():
    canonical = json.loads(
        (REPO_ROOT / "schemas" / "agent-runtime" / "final-verdict.schema.json").read_text(
            encoding="utf-8-sig"
        )
    )
    packaged = json.loads(
        (
            REPO_ROOT
            / "packages"
            / "control-plane"
            / "control_plane"
            / "final-verdict.schema.json"
        ).read_text(encoding="utf-8")
    )

    assert _schema_without_annotations(packaged) == _schema_without_annotations(canonical)


def test_packaged_review_schema_matches_canonical_contract():
    canonical = json.loads(
        (REPO_ROOT / "schemas" / "gpt_review_result.schema.json").read_text(
            encoding="utf-8-sig"
        )
    )
    packaged = json.loads(
        (
            REPO_ROOT
            / "packages"
            / "control-plane"
            / "control_plane"
            / "gpt-review-result.schema.json"
        ).read_text(encoding="utf-8")
    )

    assert _schema_without_annotations(packaged) == _schema_without_annotations(canonical)


def test_pre_submission_check_uses_shipped_gates_on_generated_paper_path(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setattr(stage_executor, "PIPELINE_RUN_ID", "ref-paper-real-path")
    paper_root = tmp_path / "paper"
    shutil.copytree(
        REPO_ROOT / "packages" / "control-plane" / "templates" / "paper_iteration",
        paper_root,
    )

    for stage in (
        stage_executor.execute_project_init,
        stage_executor.execute_load_input,
        stage_executor.execute_paper_review,
        stage_executor.execute_build_evidence_pack,
    ):
        assert stage(paper_root).status == "completed"

    for artifact_name, schema_name in (
        ("PAPER_TASK_INPUT.yaml", "paper_task_input.schema.json"),
        ("PAPER_TASK_OUTPUT.yaml", "paper_task_output.schema.json"),
    ):
        payload = yaml.safe_load(
            (paper_root / "paper_task" / artifact_name).read_text(encoding="utf-8")
        )
        schema = json.loads(
            (REPO_ROOT / "schemas" / schema_name).read_text(encoding="utf-8-sig")
        )
        Draft202012Validator(schema).validate(payload)

    result = stage_executor.execute_pre_submission_check(paper_root)

    assert result.status == "completed"
    assert result.errors == []
    directory_validation = json.loads(
        (paper_root / "evidence" / "PAPER_TASK_VALIDATION.directory.json").read_text(
            encoding="utf-8"
        )
    )
    zip_validation = json.loads(
        (paper_root / "evidence" / "PAPER_TASK_VALIDATION.zip.json").read_text(
            encoding="utf-8"
        )
    )
    assert directory_validation["status"] == "pass"
    assert zip_validation["status"] == "pass"
    assert "result: pass" in (
        paper_root / "evidence" / "PRE_SUBMISSION_CHECK.yaml"
    ).read_text(encoding="utf-8")
    assert cmd_pack_validate(str(paper_root / "evidence" / "ref-paper-review-pack.zip")) == 0


def test_paper_task_gate_rejects_real_full_text(tmp_path, monkeypatch):
    monkeypatch.setattr(stage_executor, "PIPELINE_RUN_ID", "ref-paper-private")
    paper_root = tmp_path / "paper"
    shutil.copytree(
        REPO_ROOT / "packages" / "control-plane" / "templates" / "paper_iteration",
        paper_root,
    )
    assert stage_executor.execute_load_input(paper_root).status == "completed"
    assert stage_executor.execute_paper_review(paper_root).status == "completed"
    input_path = paper_root / "paper_task" / "PAPER_TASK_INPUT.yaml"
    input_path.write_text(
        input_path.read_text(encoding="utf-8").replace(
            'paper_data_classification: "synthetic"',
            'paper_data_classification: "real_paper_full_text"',
        ),
        encoding="utf-8",
    )

    result = validate_paper_task_source(paper_root)

    assert not result.passed
    assert any("real paper full text" in error for error in result.errors)


def test_paper_task_gate_rejects_authorized_real_excerpt_in_synthetic_pipeline(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setattr(stage_executor, "PIPELINE_RUN_ID", "ref-paper-excerpt")
    paper_root = tmp_path / "paper"
    shutil.copytree(
        REPO_ROOT / "packages" / "control-plane" / "templates" / "paper_iteration",
        paper_root,
    )
    assert stage_executor.execute_load_input(paper_root).status == "completed"
    assert stage_executor.execute_paper_review(paper_root).status == "completed"
    input_path = paper_root / "paper_task" / "PAPER_TASK_INPUT.yaml"
    input_path.write_text(
        input_path.read_text(encoding="utf-8")
        .replace(
            'paper_data_classification: "synthetic"',
            'paper_data_classification: "user_authorized_excerpt"',
        )
        .replace('user_authorization: "synthetic"', 'user_authorization: "explicit"'),
        encoding="utf-8",
    )

    result = validate_paper_task_source(paper_root)

    assert not result.passed
    assert any("synthetic pipeline requires synthetic" in error for error in result.errors)


def test_submission_bypass_gate_rejects_unapproved_browser_source(tmp_path):
    (tmp_path / "rogue_submit.py").write_text(
        "from playwright.sync_api import sync_playwright\n",
        encoding="utf-8",
    )

    result = scan_submission_bypass(tmp_path)

    assert not result.passed
    assert any("sync_playwright" in error for error in result.errors)


def test_pre_submission_check_blocks_when_bypass_scanner_is_unavailable(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setattr(stage_executor, "PIPELINE_RUN_ID", "ref-paper-no-scanner")
    paper_root = tmp_path / "paper"
    shutil.copytree(
        REPO_ROOT / "packages" / "control-plane" / "templates" / "paper_iteration",
        paper_root,
    )
    for stage in (
        stage_executor.execute_project_init,
        stage_executor.execute_load_input,
        stage_executor.execute_paper_review,
        stage_executor.execute_build_evidence_pack,
    ):
        assert stage(paper_root).status == "completed"

    def unavailable():
        raise RuntimeError("scanner unavailable")

    monkeypatch.setattr(stage_executor, "scan_submission_bypass", unavailable)

    result = stage_executor.execute_pre_submission_check(paper_root)

    assert result.status == "failed"
    assert "bypass_checker_unavailable" in result.errors


def test_evidence_pack_gate_rejects_payload_hash_tampering(tmp_path, monkeypatch):
    monkeypatch.setattr(stage_executor, "PIPELINE_RUN_ID", "ref-paper-tamper")
    paper_root = tmp_path / "paper"
    shutil.copytree(
        REPO_ROOT / "packages" / "control-plane" / "templates" / "paper_iteration",
        paper_root,
    )
    for stage in (
        stage_executor.execute_project_init,
        stage_executor.execute_load_input,
        stage_executor.execute_paper_review,
        stage_executor.execute_build_evidence_pack,
    ):
        assert stage(paper_root).status == "completed"

    zip_path = paper_root / "evidence" / "ref-paper-review-pack.zip"
    tampered_path = paper_root / "evidence" / "tampered.zip"
    with zipfile.ZipFile(zip_path, "r") as source, zipfile.ZipFile(
        tampered_path,
        "w",
        zipfile.ZIP_DEFLATED,
    ) as target:
        for info in source.infolist():
            payload = source.read(info.filename)
            if info.filename == "input/SYNTHETIC_PAPER.md":
                payload += b"\ntampered\n"
            target.writestr(info, payload)

    result = validate_evidence_pack(tampered_path)

    assert not result.passed
    assert any("sha256 mismatch" in error for error in result.errors)


def test_evidence_pack_gate_rejects_duplicate_and_unsafe_entries(tmp_path):
    zip_path = tmp_path / "unsafe.zip"
    with pytest.warns(UserWarning, match="Duplicate name"):
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("payload.txt", b"first")
            archive.writestr("payload.txt", b"second")
            archive.writestr("../escape.txt", b"escape")
            archive.writestr(
                "PACK_MANIFEST.md",
                "| path | role | sha256 |\n"
                "|------|------|--------|\n"
                "| payload.txt | evidence | " + "0" * 64 + " |\n"
                "| ../escape.txt | evidence | " + "0" * 64 + " |\n"
                "| PACK_MANIFEST.md | pack_manifest | self_excluded |\n",
            )

    result = validate_evidence_pack(zip_path)

    assert not result.passed
    assert "evidence pack contains duplicate ZIP entries" in result.errors
    assert any("unsafe path" in error for error in result.errors)


def test_evidence_pack_gate_requires_valid_manifest_metadata(tmp_path):
    payload = b"bounded evidence"
    zip_path = tmp_path / "missing-metadata.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("payload.txt", payload)
        archive.writestr(
            "PACK_MANIFEST.md",
            "| path | role | sha256 |\n"
            "|------|------|--------|\n"
            f"| payload.txt | evidence | {hashlib.sha256(payload).hexdigest()} |\n"
            "| PACK_MANIFEST.md | pack_manifest | self_excluded |\n",
        )

    result = validate_evidence_pack(zip_path)

    assert not result.passed
    assert "manifest requires files_count" in result.errors
    assert "manifest_valid must be true" in result.errors


def test_evidence_pack_gate_binds_archive_to_current_project_files(tmp_path):
    payload_path = tmp_path / "payload.txt"
    payload_path.write_bytes(b"reviewed bytes")
    zip_path = tmp_path / "bound.zip"
    digest = hashlib.sha256(payload_path.read_bytes()).hexdigest()
    manifest = (
        "files_count: 2\n"
        "| path | role | sha256 |\n"
        "|------|------|--------|\n"
        f"| payload.txt | evidence | {digest} |\n"
        "| PACK_MANIFEST.md | pack_manifest | self_excluded |\n"
        "manifest_valid: true\n"
    )
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("payload.txt", payload_path.read_bytes())
        archive.writestr("PACK_MANIFEST.md", manifest)
    payload_path.write_bytes(b"changed after review")

    result = validate_evidence_pack(zip_path, content_root=tmp_path)

    assert not result.passed
    assert any("current project sha256 mismatch" in error for error in result.errors)


def test_execute_closure_stops_at_independent_review_boundary(tmp_path, monkeypatch):
    monkeypatch.setattr(stage_executor, "PIPELINE_RUN_ID", "ref-paper-test")
    paper_root = tmp_path / "paper"
    shutil.copytree(
        REPO_ROOT / "packages" / "control-plane" / "templates" / "paper_iteration",
        paper_root,
    )
    for stage in (
        stage_executor.execute_project_init,
        stage_executor.execute_load_input,
        stage_executor.execute_paper_review,
        stage_executor.execute_build_evidence_pack,
        stage_executor.execute_pre_submission_check,
        stage_executor.execute_submission_dry_run,
    ):
        assert stage(paper_root).status == "completed"
    task_spec_path = paper_root / "TASKSPEC.json"
    task_spec = json.loads(task_spec_path.read_text(encoding="utf-8"))
    task_spec_schema = json.loads(
        (REPO_ROOT / "schemas" / "agent-runtime" / "task-spec.schema.json").read_text(
            encoding="utf-8-sig"
        )
    )
    Draft202012Validator(task_spec_schema).validate(task_spec)

    result = stage_executor.execute_closure(paper_root)

    assert result.status == "completed"
    assert not (paper_root / "closure" / "FINAL_VERDICT.json").exists()
    assert not (paper_root / "review" / "review.yaml").exists()
    flow = json.loads((paper_root / "closure" / "FLOW_OUTCOME.json").read_text(encoding="utf-8"))
    assert flow["final_status"] == "review_pending"
    assert flow["final_verdict_state"] == "deferred"
    assert "final_verdict_path" not in flow
    execution_report_path = paper_root / "execution-report.json"
    execution_report = json.loads(execution_report_path.read_text(encoding="utf-8"))
    execution_report_schema = json.loads(
        (REPO_ROOT / "schemas" / "agent-runtime" / "execution-report.schema.json").read_text(
            encoding="utf-8-sig"
        )
    )
    Draft202012Validator(execution_report_schema).validate(execution_report)
    assert execution_report["status"] == "escalate"
    assert execution_report["review_status"] == "submitted"
    assert execution_report["blocking_issues"] == ["independent_review_required"]
    assert "reviewer_decision" not in execution_report
    assert "reviewer_artifacts" not in execution_report
    with zipfile.ZipFile(paper_root / "evidence" / "ref-paper-review-pack.zip") as archive:
        names = set(archive.namelist())
    assert "TASKSPEC.json" in names
    assert "execution-report.json" in names
    assert "execution-report.md" in names
    assert "evidence/BYPASS_CHECK_OUTPUT.txt" in names
    assert "evidence/PAPER_PIPELINE_GATE.json" in names
    assert "closure/FLOW_OUTCOME.json" in names
    assert "closure/FINAL_VERDICT.json" not in names

    index = build_run_index(tmp_path / "runtime", paper_project_dirs=[paper_root])
    record = [item["record"] for item in index["runs"] if item["adapter_id"] == "paper"][0]
    _run_record_validator().validate(record)
    assert record["outcome"] == "passed"
    assert record["review_state"] == "review_pending"
    assert record["acceptance_state"] == "review_pending"
    assert "final_verdict_ref" not in record
    evidence_uris = {item["uri"] for item in record["evidence_refs"]}
    assert str(task_spec_path) in evidence_uris
    assert str(execution_report_path) in evidence_uris


def test_explicit_paper_finalize_consumes_external_independent_review(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setattr(stage_executor, "PIPELINE_RUN_ID", "ref-paper-finalize")
    paper_root = tmp_path / "paper"
    shutil.copytree(
        REPO_ROOT / "packages" / "control-plane" / "templates" / "paper_iteration",
        paper_root,
    )
    for stage in (
        stage_executor.execute_project_init,
        stage_executor.execute_load_input,
        stage_executor.execute_paper_review,
        stage_executor.execute_build_evidence_pack,
        stage_executor.execute_pre_submission_check,
        stage_executor.execute_submission_dry_run,
        stage_executor.execute_closure,
    ):
        assert stage(paper_root).status == "completed"

    evidence_paths = [
        "TASKSPEC.json",
        "execution-report.json",
        "closure/FLOW_OUTCOME.json",
        "evidence/PAPER_PIPELINE_GATE.json",
        "evidence/ref-paper-review-pack.zip",
    ]
    review = {
        "REVIEW_RUN_ID": "independent-paper-review-1",
        "template_version": "gpt-review-template-v1",
        "task_type": "paper_revision_review",
        "review_stage": "closure",
        "overall_judgment": "accepted",
        "reviewer_type": "agent",
        "evidence_pack": {
            "path": "evidence/ref-paper-review-pack.zip",
            "sha256": hashlib.sha256(
                (paper_root / "evidence" / "ref-paper-review-pack.zip").read_bytes()
            ).hexdigest(),
            "manifest_valid": True,
        },
        "evidence_inspected": [
            {
                "path": relative,
                "sha256": hashlib.sha256((paper_root / relative).read_bytes()).hexdigest(),
                "inspected": True,
                "role": "paper_execution_evidence",
            }
            for relative in evidence_paths
        ],
        "blocking_reasons": [],
        "missing_evidence": [],
        "scope_violation": False,
        "fake_green_risk": False,
        "safety_boundaries_respected": True,
        "required_next_action": "none",
        "allow_proceed": True,
        "rationale": "Independent review verified the bounded synthetic paper evidence.",
        "created_at": "2026-07-18T00:00:00Z",
        "next_task_authorization": {
            "task_id": "close-synthetic-paper-run",
            "authorized": "已授权",
            "execute_immediately": "否",
            "ask_before_starting": "是",
        },
        "task_type_specific": {"paper_revision_review": {}},
    }
    review_schema = json.loads(
        (REPO_ROOT / "schemas" / "gpt_review_result.schema.json").read_text(
            encoding="utf-8-sig"
        )
    )
    Draft202012Validator(review_schema).validate(review)
    external_review = tmp_path / "independent-review.json"
    external_review.write_text(json.dumps(review, indent=2), encoding="utf-8")

    review_sha256 = hashlib.sha256(external_review.read_bytes()).hexdigest()
    original_input = (paper_root / "input" / "SYNTHETIC_PAPER.md").read_bytes()
    (paper_root / "input" / "SYNTHETIC_PAPER.md").write_bytes(
        original_input + b"\nchanged after review\n"
    )
    stale_result = finalize_paper_project(
        paper_root,
        external_review,
        review_sha256,
        review["REVIEW_RUN_ID"],
    )
    assert not stale_result.passed
    assert any("current project sha256 mismatch" in error for error in stale_result.errors)
    (paper_root / "input" / "SYNTHETIC_PAPER.md").write_bytes(original_input)

    original_scanner = paper_pipeline_gate.scan_submission_bypass
    monkeypatch.setattr(
        paper_pipeline_gate,
        "scan_submission_bypass",
        lambda: PaperPipelineGateResult(
            status="fail",
            errors=("live browser bridge became reachable",),
        ),
    )
    bypass_result = finalize_paper_project(
        paper_root,
        external_review,
        review_sha256,
        review["REVIEW_RUN_ID"],
    )
    assert not bypass_result.passed
    assert "live browser bridge became reachable" in bypass_result.errors
    monkeypatch.setattr(paper_pipeline_gate, "scan_submission_bypass", original_scanner)

    result = finalize_paper_project(
        paper_root,
        external_review,
        review_sha256,
        review["REVIEW_RUN_ID"],
    )

    assert result.passed, result.errors
    final_path = paper_root / "closure" / "FINAL_VERDICT.json"
    final_verdict = json.loads(final_path.read_text(encoding="utf-8"))
    assert final_verdict["final_state"] == "accepted_with_limitation"
    assert final_verdict["reviewer_summary"]["reviewer_id"] == review["REVIEW_RUN_ID"]
    assert (paper_root / "governance" / "INDEPENDENT_REVIEW.json").is_file()
    assert (paper_root / "governance" / "REVIEW_GATE.json").is_file()

    index = build_run_index(tmp_path / "runtime", paper_project_dirs=[paper_root])
    record = [item["record"] for item in index["runs"] if item["adapter_id"] == "paper"][0]
    _run_record_validator().validate(record)
    assert record["review_state"] == "review_passed"
    assert record["gate_state"] == "gate_limited"
    assert record["acceptance_state"] == "accepted_with_limitation"


def test_paper_finalize_rejects_executor_self_review(tmp_path, monkeypatch):
    monkeypatch.setattr(stage_executor, "PIPELINE_RUN_ID", "ref-paper-self-review")
    paper_root = tmp_path / "paper"
    shutil.copytree(
        REPO_ROOT / "packages" / "control-plane" / "templates" / "paper_iteration",
        paper_root,
    )
    for stage in (
        stage_executor.execute_project_init,
        stage_executor.execute_load_input,
        stage_executor.execute_paper_review,
        stage_executor.execute_build_evidence_pack,
        stage_executor.execute_pre_submission_check,
        stage_executor.execute_submission_dry_run,
        stage_executor.execute_closure,
    ):
        assert stage(paper_root).status == "completed"

    review_path = tmp_path / "self-review.json"
    review_path.write_text(
        json.dumps({
            "REVIEW_RUN_ID": "devframe-paper-stage-executor",
            "template_version": "gpt-review-template-v1",
            "task_type": "paper_revision_review",
            "review_stage": "closure",
            "overall_judgment": "accepted",
            "reviewer_type": "agent",
            "evidence_inspected": [{"path": "TASKSPEC.json", "inspected": True}],
            "blocking_reasons": [],
            "missing_evidence": [],
            "scope_violation": False,
            "fake_green_risk": False,
            "safety_boundaries_respected": True,
            "required_next_action": "none",
            "allow_proceed": True,
            "rationale": "self review must be rejected",
            "created_at": "2026-07-18T00:00:00Z",
            "next_task_authorization": {
                "task_id": "close",
                "authorized": "已授权",
                "execute_immediately": "否",
            },
            "task_type_specific": {"paper_revision_review": {}},
        }),
        encoding="utf-8",
    )

    review_sha256 = hashlib.sha256(review_path.read_bytes()).hexdigest()
    lowercase_verdict = paper_root / "closure" / "final-verdict.json"
    lowercase_verdict.write_text("{}\n", encoding="utf-8")
    duplicate_result = finalize_paper_project(
        paper_root,
        review_path,
        review_sha256,
        "devframe-paper-stage-executor",
    )
    assert not duplicate_result.passed
    assert any("FinalVerdict already exists" in error for error in duplicate_result.errors)
    lowercase_verdict.unlink()

    result = finalize_paper_project(
        paper_root,
        review_path,
        review_sha256,
        "devframe-paper-stage-executor",
    )

    assert not result.passed
    assert any("reviewer identity matches executor" in error for error in result.errors)
    assert not (paper_root / "closure" / "FINAL_VERDICT.json").exists()

    in_project_review = paper_root / "review" / "independent-review.json"
    in_project_review.write_bytes(review_path.read_bytes())
    in_project_result = finalize_paper_project(
        paper_root,
        in_project_review,
        hashlib.sha256(in_project_review.read_bytes()).hexdigest(),
        "devframe-paper-stage-executor",
    )
    assert not in_project_result.passed
    assert any("review source must be outside" in error for error in in_project_result.errors)


def _run_record_validator():
    schema = json.loads(
        (REPO_ROOT / "schemas/runtime-governance/run-record.schema.json").read_text(encoding="utf-8-sig")
    )
    validator_class = validator_for(schema)
    validator_class.check_schema(schema)
    return validator_class(schema)
