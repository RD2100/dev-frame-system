from __future__ import annotations

import json
from pathlib import Path

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
        json.dumps({
            "run_id": "run-lib",
            "executor_id": "executor-1",
            "task": "task.md",
        }),
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
