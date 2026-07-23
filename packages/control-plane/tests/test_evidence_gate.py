from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml
from jsonschema.validators import validator_for

from control_plane.evidence_gate import (
    build_evidence_manifest,
    build_failure_record,
    build_final_verdict,
    evaluate_evidence_dir,
)

REPO_ROOT = Path(__file__).resolve().parents[3]


def _schema_validator(path: str):
    schema = json.loads((REPO_ROOT / path).read_text(encoding="utf-8-sig"))
    validator_class = validator_for(schema)
    validator_class.check_schema(schema)
    return validator_class(schema)


def _chain_evidence(**overrides) -> dict:
    data = {
        "run_id": "run-lib",
        "executor_id": "executor-1",
        "mode": "auto_execute",
        "planner": None,
        "task": "task.md",
        "methodology": None,
        "evidence_files": [
            "diff.patch",
            "test-output.md",
            "safety-report.json",
            "chain-evidence.json",
            "review.md",
            "review.yaml",
            "evidence-manifest.json",
            "final-report.md",
            "final-verdict.json",
        ],
        "timestamps": {
            "created_at": "2026-07-07T00:00:00+00:00",
        },
    }
    data.update(overrides)
    return data


def _write_evidence(path: Path, review: dict) -> None:
    path.mkdir(parents=True, exist_ok=True)
    (path / "diff.patch").write_text("diff\n", encoding="utf-8")
    (path / "test-output.md").write_text("1 passed\n", encoding="utf-8")
    (path / "safety-report.json").write_text(
        json.dumps({
            "generated_at": "2026-07-07T00:00:00+00:00",
            "producer": "go_evidence.py",
            "command": "pytest",
            "exit_code": 0,
            "stdout": "1 passed",
            "stderr": "",
        }),
        encoding="utf-8",
    )
    (path / "chain-evidence.json").write_text(
        json.dumps(_chain_evidence()),
        encoding="utf-8",
    )
    (path / "review.md").write_text("review\n", encoding="utf-8")
    (path / "review.yaml").write_text(yaml.safe_dump(review), encoding="utf-8")


def _review(**overrides):
    data = {
        "reviewer_role": "reviewer",
        "reviewer_id": "reviewer-1",
        "executor_id": "executor-1",
        "verdict": "pass",
        "reviewed_inputs": [
            "diff.patch",
            "test-output.md",
            "safety-report.json",
            "chain-evidence.json",
        ],
        "findings": [],
    }
    data.update(overrides)
    return data


def test_evidence_gate_builds_schema_valid_manifest_and_final_verdict(tmp_path):
    evidence_dir = tmp_path / "evidence"
    _write_evidence(evidence_dir, _review())

    result = evaluate_evidence_dir(evidence_dir)
    manifest = build_evidence_manifest(evidence_dir, result, "2026-07-07T00:00:00+00:00")
    final_verdict = build_final_verdict(evidence_dir, result, "2026-07-07T00:00:00+00:00")

    assert result.status == "pass"
    _schema_validator("schemas/agent-runtime/evidence-manifest.schema.json").validate(manifest)
    _schema_validator("schemas/agent-runtime/final-verdict.schema.json").validate(final_verdict)
    assert manifest["verdict_eligibility"]["status"] == "eligible_clean"
    assert final_verdict["final_state"] == "final_ready"
    assert final_verdict["producer_role"] == "governance"


def test_evidence_gate_blocks_same_reviewer_and_executor_identity(tmp_path):
    evidence_dir = tmp_path / "evidence"
    _write_evidence(evidence_dir, _review(reviewer_id="executor-1"))

    result = evaluate_evidence_dir(evidence_dir)
    failure = build_failure_record(evidence_dir, result, "2026-07-07T00:00:00+00:00")
    final_verdict = build_final_verdict(evidence_dir, result, "2026-07-07T00:00:00+00:00")

    assert result.status == "blocked"
    assert "reviewer_id must differ from executor_id" in result.reason
    _schema_validator("schemas/agent-runtime/failure-record.schema.json").validate(failure)
    _schema_validator("schemas/agent-runtime/final-verdict.schema.json").validate(final_verdict)
    assert final_verdict["final_state"] == "blocked"


def test_evidence_gate_blocks_whitespace_padded_executor_role(tmp_path):
    evidence_dir = tmp_path / "evidence"
    _write_evidence(evidence_dir, _review(reviewer_role="executor "))

    result = evaluate_evidence_dir(evidence_dir)
    final_verdict = build_final_verdict(evidence_dir, result, "2026-07-07T00:00:00+00:00")

    assert result.status == "blocked"
    assert "reviewer_role 'executor' is not allowed" in result.reason
    assert final_verdict["final_state"] == "blocked"


@pytest.mark.parametrize("reviewer_role", ["controller", " Coordinator ", "ROOT"])
def test_evidence_gate_blocks_governance_authority_reviewer_roles(
    tmp_path, reviewer_role
):
    evidence_dir = tmp_path / "evidence"
    _write_evidence(evidence_dir, _review(reviewer_role=reviewer_role))

    result = evaluate_evidence_dir(evidence_dir)
    final_verdict = build_final_verdict(
        evidence_dir, result, "2026-07-07T00:00:00+00:00"
    )

    assert result.status == "blocked"
    assert "review" in result.reason
    assert final_verdict["final_state"] == "blocked"


@pytest.mark.parametrize("reviewer_id", ["controller", " Coordinator ", "ROOT"])
def test_evidence_gate_blocks_governance_author_reviewer_id(tmp_path, reviewer_id):
    evidence_dir = tmp_path / "evidence"
    _write_evidence(evidence_dir, _review(reviewer_id=reviewer_id))

    result = evaluate_evidence_dir(evidence_dir)
    final_verdict = build_final_verdict(
        evidence_dir, result, "2026-07-07T00:00:00+00:00"
    )

    assert result.status == "blocked"
    assert "reviewer_id" in result.reason
    assert final_verdict["final_state"] == "blocked"


def test_evidence_gate_blocks_invalid_chain_evidence_schema(tmp_path):
    evidence_dir = tmp_path / "evidence"
    _write_evidence(evidence_dir, _review())
    (evidence_dir / "chain-evidence.json").write_text(
        json.dumps({"run_id": "run-lib", "executor_id": "executor-1", "task": "task.md"}),
        encoding="utf-8",
    )

    result = evaluate_evidence_dir(evidence_dir)
    failure = build_failure_record(evidence_dir, result, "2026-07-07T00:00:00+00:00")
    final_verdict = build_final_verdict(evidence_dir, result, "2026-07-07T00:00:00+00:00")

    assert result.status == "blocked"
    assert "chain-evidence.json schema invalid" in result.reason
    assert failure["source_contract"] == "EvidenceManifest"
    assert final_verdict["final_state"] == "blocked"


def test_review_schema_mirror_matches_independent_reviewer_contract():
    root_path = REPO_ROOT / "schemas" / "agent-runtime" / "review.schema.json"
    mirror_path = (
        REPO_ROOT
        / "packages"
        / "test-frame"
        / "schemas"
        / "agent-runtime"
        / "review.schema.json"
    )
    root_schema = json.loads(root_path.read_text(encoding="utf-8-sig"))
    mirror_schema = json.loads(mirror_path.read_text(encoding="utf-8-sig"))

    assert mirror_schema == root_schema
    assert root_schema["properties"]["verdict"]["enum"] == [
        "pass",
        "blocked",
        "fail",
        "escalate",
    ]
    valid = _review()
    blocked_roles = [
        "executor",
        "fixer",
        "coder",
        "worker",
        "controller",
        "coordinator",
        "root",
    ]
    for schema in (root_schema, mirror_schema):
        validator_class = validator_for(schema)
        validator_class.check_schema(schema)
        validator = validator_class(schema)
        validator.validate(valid)
        for role in blocked_roles:
            assert list(validator.iter_errors({**valid, "reviewer_role": role}))
