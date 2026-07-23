"""Deterministic evidence gate helpers for @go-style evidence directories."""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from jsonschema.validators import validator_for

from .team_runtime import (
    ALLOWED_REVIEW_VERDICTS,
    BLOCKED_REVIEW_ROLES,
    BLOCKED_REVIEWER_IDS,
)

REQUIRED_FILES = [
    "diff.patch",
    "test-output.md",
    "safety-report.json",
    "chain-evidence.json",
    "review.md",
    "review.yaml",
]
REQUIRED_INPUTS = [
    "diff.patch",
    "test-output.md",
    "safety-report.json",
    "chain-evidence.json",
]
FULL_EVIDENCE_FILES = REQUIRED_FILES + [
    "evidence-manifest.json",
    "final-report.md",
    "final-verdict.json",
]
BLOCKED_ROLES = BLOCKED_REVIEW_ROLES
ALLOWED_VERDICTS = ALLOWED_REVIEW_VERDICTS


@dataclass(frozen=True)
class EvidenceGateResult:
    status: str
    reason: str
    review: dict[str, Any]
    chain_evidence: dict[str, Any]
    missing_files: list[str]
    missing_inputs: list[str]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _schema_validator(schema_path: str):
    schema = json.loads((_repo_root() / schema_path).read_text(encoding="utf-8-sig"))
    validator_class = validator_for(schema)
    validator_class.check_schema(schema)
    return validator_class(schema)


def _validate_schema(schema_path: str, payload: dict[str, Any]) -> None:
    _schema_validator(schema_path).validate(payload)


def _load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    return payload if isinstance(payload, dict) else {}


def parse_review_yaml(path: str | Path) -> dict[str, Any]:
    path = Path(path)
    try:
        import yaml
    except ImportError:
        yaml = None

    if yaml is not None:
        with path.open("r", encoding="utf-8") as fh:
            return yaml.safe_load(fh) or {}

    data: dict[str, Any] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key in ("reviewer_role", "reviewer_id", "executor_id", "verdict"):
            data[key] = value
        elif key == "reviewed_inputs":
            data[key] = [item.strip().strip("- ").strip('"').strip("'") for item in value.split(",")]
    return data


def evaluate_evidence_dir(evidence_dir: str | Path) -> EvidenceGateResult:
    evidence_path = Path(evidence_dir)
    missing_files = [name for name in REQUIRED_FILES if not (evidence_path / name).exists()]
    if missing_files:
        return EvidenceGateResult(
            status="blocked",
            reason=f"missing required files: {', '.join(missing_files)}",
            review={},
            chain_evidence=_load_json(evidence_path / "chain-evidence.json"),
            missing_files=missing_files,
            missing_inputs=[],
        )

    review = parse_review_yaml(evidence_path / "review.yaml")
    chain_evidence = _load_json(evidence_path / "chain-evidence.json")

    chain_errors = sorted(
        _schema_validator("schemas/agent-runtime/chain-evidence.schema.json").iter_errors(
            chain_evidence
        ),
        key=lambda error: list(error.path),
    )
    if chain_errors:
        return EvidenceGateResult(
            status="blocked",
            reason=f"chain-evidence.json schema invalid: {chain_errors[0].message}",
            review=review,
            chain_evidence=chain_evidence,
            missing_files=[],
            missing_inputs=[],
        )

    review_errors = sorted(
        _schema_validator("schemas/agent-runtime/review.schema.json").iter_errors(review),
        key=lambda error: list(error.path),
    )
    if review_errors:
        return EvidenceGateResult(
            status="blocked",
            reason=f"review.yaml schema invalid: {review_errors[0].message}",
            review=review,
            chain_evidence=chain_evidence,
            missing_files=[],
            missing_inputs=[],
        )

    methodology = chain_evidence.get("methodology") or {}
    skill_id = str(methodology.get("skill_id", "")).lower()
    if skill_id == "tdd":
        tdd_required = ["test-output-red.md", "test-output-green.md"]
        missing_tdd = [name for name in tdd_required if not (evidence_path / name).exists()]
        if missing_tdd:
            return EvidenceGateResult(
                status="blocked",
                reason=f"TDD evidence missing: {', '.join(missing_tdd)}",
                review=review,
                chain_evidence=chain_evidence,
                missing_files=missing_tdd,
                missing_inputs=[],
            )

    role = str(review.get("reviewer_role", "")).strip()
    normalized_role = role.casefold()
    if not normalized_role or normalized_role in BLOCKED_ROLES:
        return EvidenceGateResult(
            status="blocked",
            reason=f"reviewer_role '{role}' is not allowed",
            review=review,
            chain_evidence=chain_evidence,
            missing_files=[],
            missing_inputs=[],
        )

    reviewer_id = str(review.get("reviewer_id", "")).strip()
    executor_id = str(review.get("executor_id", "")).strip()
    if reviewer_id.casefold() in BLOCKED_REVIEWER_IDS:
        return EvidenceGateResult(
            status="blocked",
            reason=f"reviewer_id '{reviewer_id}' is not independent",
            review=review,
            chain_evidence=chain_evidence,
            missing_files=[],
            missing_inputs=[],
        )
    if reviewer_id and executor_id and reviewer_id == executor_id:
        return EvidenceGateResult(
            status="blocked",
            reason="reviewer_id must differ from executor_id",
            review=review,
            chain_evidence=chain_evidence,
            missing_files=[],
            missing_inputs=[],
        )

    reviewed = [item.strip() for item in review.get("reviewed_inputs", [])]
    missing_inputs = [name for name in REQUIRED_INPUTS if name not in reviewed]
    if missing_inputs:
        return EvidenceGateResult(
            status="blocked",
            reason=f"reviewed_inputs missing: {', '.join(missing_inputs)}",
            review=review,
            chain_evidence=chain_evidence,
            missing_files=[],
            missing_inputs=missing_inputs,
        )

    verdict = review.get("verdict", "")
    if verdict not in ALLOWED_VERDICTS:
        return EvidenceGateResult(
            status="blocked",
            reason=f"verdict '{verdict}' is not allowed",
            review=review,
            chain_evidence=chain_evidence,
            missing_files=[],
            missing_inputs=[],
        )

    findings = review.get("findings", []) or []
    for finding in findings:
        severity = str(finding.get("severity", "")).upper()
        status = str(finding.get("status", "")).lower()
        if severity in {"P0", "P1"} and status == "open":
            return EvidenceGateResult(
                status="blocked",
                reason=f"open {severity} finding: {finding.get('id', 'unknown')}",
                review=review,
                chain_evidence=chain_evidence,
                missing_files=[],
                missing_inputs=[],
            )

    if verdict != "pass":
        status = "fail" if verdict == "fail" else "blocked"
        return EvidenceGateResult(
            status=status,
            reason=f"verdict is '{verdict}'",
            review=review,
            chain_evidence=chain_evidence,
            missing_files=[],
            missing_inputs=[],
        )

    return EvidenceGateResult(
        status="pass",
        reason="ok",
        review=review,
        chain_evidence=chain_evidence,
        missing_files=[],
        missing_inputs=[],
    )


def build_evidence_manifest(
    evidence_dir: str | Path,
    result: EvidenceGateResult,
    generated_at: str | None = None,
) -> dict[str, Any]:
    evidence_path = Path(evidence_dir)
    generated_at = generated_at or _now_iso()
    files_present = sorted(path.name for path in evidence_path.iterdir() if path.is_file())
    tier_0_missing = [name for name in REQUIRED_FILES if name not in files_present]
    status_map = {
        "pass": "eligible_clean",
        "blocked": "not_eligible",
        "fail": "not_eligible",
    }
    blocking_signals = [] if result.status == "pass" else [result.reason]
    manifest = {
        "schema_version": "evidence-manifest.v1",
        "task_id": str(result.chain_evidence.get("task") or result.chain_evidence.get("task_file") or "unknown-task"),
        "run_id": str(result.chain_evidence.get("run_id") or "unknown-run"),
        "base_commit": str(result.chain_evidence.get("base_commit") or "unknown"),
        "head_commit": str(result.chain_evidence.get("head_commit") or "unknown"),
        "generated_at": generated_at,
        "review_yaml_profile": "ecs-v1",
        "required_files": {
            "tier_0": REQUIRED_FILES[:],
            "tier_1": [],
        },
        "files_present": files_present,
        "files_missing": {
            "tier_0": tier_0_missing,
            "tier_1": [],
        },
        "verdict_eligibility": {
            "status": status_map.get(result.status, "not_eligible"),
            "reasons": [result.reason],
            "blocking_signals": blocking_signals,
            "limitation_signals": [],
        },
        "evidence_completeness": {
            "tier_0_required": REQUIRED_FILES[:],
            "tier_0_present": [name for name in REQUIRED_FILES if name in files_present],
            "tier_0_missing": tier_0_missing,
            "tier_1_conditional": [],
            "tier_1_present": [],
            "tier_1_missing": [],
            "tier_2_optional": [name for name in files_present if name not in REQUIRED_FILES],
        },
    }
    _validate_schema("schemas/agent-runtime/evidence-manifest.schema.json", manifest)
    return manifest


def build_final_verdict(
    evidence_dir: str | Path,
    result: EvidenceGateResult,
    generated_at: str | None = None,
    produced_by: str = "go-evidence-finalizer",
) -> dict[str, Any]:
    evidence_path = Path(evidence_dir)
    generated_at = generated_at or _now_iso()
    run_id = str(result.chain_evidence.get("run_id") or evidence_path.name or "unknown-run")
    final_state = {
        "pass": "final_ready",
        "blocked": "blocked",
        "fail": "failed",
    }.get(result.status, "blocked")
    gate_result = "pass" if result.status == "pass" else result.status
    reviewer_id = str(result.review.get("reviewer_id") or "missing-reviewer")
    review_verdict = str(result.review.get("verdict") or "blocked")
    if review_verdict not in ALLOWED_VERDICTS:
        review_verdict = "blocked"
    inputs_reviewed = [
        str(evidence_path / name)
        for name in REQUIRED_FILES
        if (evidence_path / name).exists()
    ] or [str(evidence_path)]
    verdict = {
        "verdict_id": f"fv-{_safe_token(run_id)}",
        "produced_by": produced_by,
        "produced_at": generated_at,
        "producer_role": "governance",
        "final_state": final_state,
        "inputs_reviewed": inputs_reviewed,
        "gate_summary": [
            {
                "gate_id": f"gate-{_safe_token(run_id)}-independent-review",
                "result": gate_result,
                "evidence_path": str(evidence_path / "review.yaml"),
            }
        ],
        "reviewer_summary": {
            "reviewer_id": reviewer_id,
            "verdict": review_verdict,
            "evidence_path": str(evidence_path / "review.yaml"),
        },
        "limitations": [] if result.status == "pass" else [result.reason],
        "human_or_governance_reference": f"go-evidence-finalize:{run_id}",
    }
    _validate_schema("schemas/agent-runtime/final-verdict.schema.json", verdict)
    return verdict


def build_failure_record(
    evidence_dir: str | Path,
    result: EvidenceGateResult,
    generated_at: str | None = None,
) -> dict[str, Any]:
    evidence_path = Path(evidence_dir)
    generated_at = generated_at or _now_iso()
    run_id = str(result.chain_evidence.get("run_id") or evidence_path.name or "unknown-run")
    source_contract = "ReviewVerdict"
    if result.missing_files or result.reason.startswith("chain-evidence.json schema invalid"):
        source_contract = "EvidenceManifest"
    failure = {
        "failure_id": f"fr-{_safe_token(run_id)}",
        "source_contract": source_contract,
        "severity": "P0" if result.status == "blocked" else "P1",
        "status": "blocked" if result.status == "blocked" else "failed",
        "reason": result.reason,
        "owner": "main-coordinator",
        "next_action": "Provide independent reviewer evidence and rerun finalization.",
        "evidence_path": str(evidence_path / "final-report.md"),
        "related_ids": [run_id, generated_at],
    }
    _validate_schema("schemas/agent-runtime/failure-record.schema.json", failure)
    return failure


def write_json(path: str | Path, payload: dict[str, Any]) -> str:
    path = Path(path)
    content = json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
    if not path.exists() or path.read_text(encoding="utf-8") != content:
        path.write_text(content, encoding="utf-8")
    return str(path)


def _safe_token(value: str) -> str:
    token = "".join(ch if ch.isalnum() or ch in "._-" else "-" for ch in value)
    token = token.strip("-._")
    return token or "unknown"
