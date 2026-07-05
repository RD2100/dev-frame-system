import json
import jsonschema
import pytest
from pathlib import Path

from control_plane.review_governance_validator import validate_packet


SCHEMA_PATH = Path(__file__).resolve().parents[3] / "schemas" / "review_governance_kernel.schema.json"
FIXTURES_DIR = Path(__file__).resolve().parents[3] / "schemas" / "examples" / "review-governance"


@pytest.fixture(scope="session")
def schema():
    with open(SCHEMA_PATH, encoding="utf-8") as fh:
        return json.load(fh)


def _load_fixture(name):
    with open(FIXTURES_DIR / name, encoding="utf-8") as fh:
        return json.load(fh)


def _validate(schema, instance):
    jsonschema.validate(instance, schema, cls=jsonschema.Draft7Validator)


def _semantic_validate(instance):
    from control_plane.review_governance_validator import validate_packet
    result = validate_packet(instance)
    assert result.valid, "\n".join(result.errors)


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------

def test_success_fixture_validates(schema):
    payload = _load_fixture("success.json")
    _validate(schema, payload)


def test_success_fixture_has_output_artifact():
    payload = _load_fixture("success.json")
    kinds = [a["kind"] for a in payload["artifacts"]]
    assert "command_output" in kinds, "success fixture must include non-report output artifact"


def test_success_fixture_gate_evidence_points_to_non_report():
    payload = _load_fixture("success.json")
    report_ids = {a["id"] for a in payload["artifacts"] if a["kind"] == "review_report"}
    gate = next(d for d in payload["decisions"] if d["kind"] == "gate")
    evidence_refs = set(gate.get("evidence_ids", []))
    evidence_source_ids = {
        e["source_artifact_id"] for e in payload["evidence"]
        if e["id"] in evidence_refs
    }
    non_report = evidence_source_ids - report_ids
    assert non_report, "gate pass evidence must cite at least one non-report artifact"


def test_completed_status_requires_passing_gate(schema):
    payload = _load_fixture("success.json")
    assert payload["work_item"]["status"] == "completed"
    gate_outcomes = [d["outcome"] for d in payload["decisions"] if d["kind"] == "gate"]
    assert "pass" in gate_outcomes


def test_success_passes_semantic_validation():
    payload = _load_fixture("success.json")
    _semantic_validate(payload)


# ---------------------------------------------------------------------------
# Negative: prohibited top-level keys
# ---------------------------------------------------------------------------

def test_rejects_new_top_level_key(schema):
    payload = _load_fixture("success.json")
    payload["new_governance_object"] = {"id": "x"}
    with pytest.raises(jsonschema.ValidationError):
        _validate(schema, payload)


def test_rejects_forbidden_top_level_keys(schema):
    forbidden = ["human_approvals", "policy_activations", "decision_requests",
                 "attention_requests", "goal_contracts", "work_loops"]
    for key in forbidden:
        payload = _load_fixture("success.json")
        payload[key] = [{"id": "x"}]
        with pytest.raises(jsonschema.ValidationError):
            _validate(schema, payload)


def test_rejects_unknown_work_item_kind(schema):
    payload = _load_fixture("success.json")
    payload["work_item"]["kind"] = "task"
    with pytest.raises(jsonschema.ValidationError):
        _validate(schema, payload)


def test_rejects_unknown_decision_kind(schema):
    payload = _load_fixture("success.json")
    payload["decisions"][0]["kind"] = "approve"
    with pytest.raises(jsonschema.ValidationError):
        _validate(schema, payload)


def test_rejects_unknown_run_status(schema):
    payload = _load_fixture("success.json")
    payload["runs"][0]["status"] = "done"
    with pytest.raises(jsonschema.ValidationError):
        _validate(schema, payload)


def test_rejects_invalid_schema_version(schema):
    payload = _load_fixture("success.json")
    payload["schema_version"] = "0.2"
    with pytest.raises(jsonschema.ValidationError):
        _validate(schema, payload)


# ---------------------------------------------------------------------------
# Negative: context_snapshot constraints
# ---------------------------------------------------------------------------

def test_context_snapshot_requires_immutable_true(schema):
    payload = _load_fixture("success.json")
    ctx = next(a for a in payload["artifacts"] if a["kind"] == "context_snapshot")
    ctx["immutable"] = False
    with pytest.raises(jsonschema.ValidationError):
        _validate(schema, payload)


def test_context_snapshot_requires_content_hash_format(schema):
    payload = _load_fixture("success.json")
    ctx = next(a for a in payload["artifacts"] if a["kind"] == "context_snapshot")
    ctx["content_hash"] = "not-a-real-hash"
    with pytest.raises(jsonschema.ValidationError):
        _validate(schema, payload)


def test_context_snapshot_requires_source_refs(schema):
    payload = _load_fixture("success.json")
    ctx = next(a for a in payload["artifacts"] if a["kind"] == "context_snapshot")
    ctx["source_refs"] = []
    with pytest.raises(jsonschema.ValidationError):
        _validate(schema, payload)


def test_context_snapshot_requires_token_budget_positive(schema):
    payload = _load_fixture("success.json")
    ctx = next(a for a in payload["artifacts"] if a["kind"] == "context_snapshot")
    ctx["token_budget"] = 0
    with pytest.raises(jsonschema.ValidationError):
        _validate(schema, payload)


def test_context_snapshot_rejects_extra_fields(schema):
    payload = _load_fixture("success.json")
    ctx = next(a for a in payload["artifacts"] if a["kind"] == "context_snapshot")
    ctx["extra_field"] = "not allowed"
    with pytest.raises(jsonschema.ValidationError):
        _validate(schema, payload)


# ---------------------------------------------------------------------------
# Negative: run-success != completion
# ---------------------------------------------------------------------------

def test_run_succeeded_does_not_force_completed(schema):
    payload = _load_fixture("success.json")
    payload["runs"][0]["status"] = "succeeded"
    payload["work_item"]["status"] = "ready"
    payload["decisions"] = []
    payload["evidence"] = []
    payload["projection"]["computed_status"] = "ready"
    payload["projection"]["blocked_reason"] = ""
    _validate(schema, payload)


def test_completed_without_gate_fails_semantic(schema):
    payload = _load_fixture("success.json")
    payload["work_item"]["status"] = "completed"
    payload["decisions"] = [
        {
            "id": "decision-review-only",
            "project_id": "proj-review-demo",
            "kind": "review",
            "target_ref": "wi-review-1",
            "decider_principal_id": "principal-human-1",
            "outcome": "pass",
            "evidence_ids": ["ev-1"],
            "rationale": "review only"
        }
    ]
    result = validate_packet(payload)
    assert not result.valid
    assert any("gate" in e for e in result.errors)


def test_completed_requires_gate_for_correct_work_item():
    payload = _load_fixture("success.json")
    payload["work_item"]["status"] = "completed"
    # Replace gate decision with one targeting a different work item
    payload["decisions"] = [
        {
            "id": "decision-gate-other",
            "project_id": "proj-review-demo",
            "kind": "gate",
            "target_ref": "wi-other",
            "decider_principal_id": "principal-human-1",
            "outcome": "pass",
            "evidence_ids": ["ev-1", "ev-2"],
            "payload": {},
            "rationale": "gate for wrong work item"
        }
    ]
    result = validate_packet(payload)
    assert not result.valid
    assert any("gate" in e for e in result.errors)


# ---------------------------------------------------------------------------
# Negative: evidence constraints
# ---------------------------------------------------------------------------

def test_evidence_requires_source_artifact_id(schema):
    payload = _load_fixture("success.json")
    ev = payload["evidence"][0]
    ev["source_artifact_id"] = ""
    with pytest.raises(jsonschema.ValidationError):
        _validate(schema, payload)


def test_report_only_evidence_fails_semantic(schema):
    payload = _load_fixture("success.json")
    payload["evidence"] = [
        {
            "id": "ev-report-only",
            "project_id": "proj-review-demo",
            "claim": "report says it passed",
            "supports": "supports",
            "source_artifact_id": "artifact-report-1",
            "scope": "schema_contract",
            "freshness": "2026-07-05T10:05:00Z",
            "observed_result": "report claims pass"
        }
    ]
    # Schema passes (draft-07 cannot enforce cross-object constraints).
    _validate(schema, payload)
    # Semantic layer catches report-only evidence for gate pass.
    result = validate_packet(payload)
    assert not result.valid


def test_gate_pass_with_missing_evidence_id_fails_semantic(schema):
    payload = _load_fixture("success.json")
    gate = next(d for d in payload["decisions"] if d["kind"] == "gate")
    gate["evidence_ids"] = ["ev-nonexistent"]
    _validate(schema, payload)
    result = validate_packet(payload)
    assert not result.valid
    assert any("missing" in e.lower() or "nonexistent" in e.lower() for e in result.errors)


def test_gate_pass_with_inconclusive_evidence_fails_semantic(schema):
    payload = _load_fixture("success.json")
    payload["evidence"][0]["supports"] = "inconclusive"
    _validate(schema, payload)
    result = validate_packet(payload)
    assert not result.valid
    assert any("inconclusive" in e.lower() or "supports" in e.lower() for e in result.errors)


def test_gate_pass_requires_evidence_ids(schema):
    payload = _load_fixture("success.json")
    gate = next(d for d in payload["decisions"] if d["kind"] == "gate")
    assert len(gate["evidence_ids"]) >= 1


# ---------------------------------------------------------------------------
# Negative: decision kind constraints
# ---------------------------------------------------------------------------

def test_review_decision_requires_evidence_on_pass(schema):
    payload = _load_fixture("success.json")
    payload["decisions"][0]["outcome"] = "pass"
    payload["decisions"][0]["evidence_ids"] = []
    with pytest.raises(jsonschema.ValidationError):
        _validate(schema, payload)


def test_gate_decision_fail_does_not_require_evidence_ids(schema):
    payload = _load_fixture("success.json")
    payload["decisions"][1]["outcome"] = "fail"
    payload["decisions"][1]["evidence_ids"] = []
    _validate(schema, payload)


def test_rejects_review_outcome_human_required(schema):
    payload = _load_fixture("success.json")
    payload["decisions"][0]["kind"] = "review"
    payload["decisions"][0]["outcome"] = "human_required"
    with pytest.raises(jsonschema.ValidationError):
        _validate(schema, payload)


def test_rejects_gate_outcome_enum(schema):
    payload = _load_fixture("success.json")
    payload["decisions"][1]["outcome"] = "invalid_outcome"
    with pytest.raises(jsonschema.ValidationError):
        _validate(schema, payload)


def test_gate_outcome_allows_human_required(schema):
    payload = _load_fixture("success.json")
    gate = next(d for d in payload["decisions"] if d["kind"] == "gate")
    gate["outcome"] = "human_required"
    gate["evidence_ids"] = ["ev-1", "ev-2"]
    _validate(schema, payload)


# ---------------------------------------------------------------------------
# Negative: work_item status enum
# ---------------------------------------------------------------------------

def test_rejects_unknown_work_item_status(schema):
    payload = _load_fixture("success.json")
    payload["work_item"]["status"] = "finished"
    with pytest.raises(jsonschema.ValidationError):
        _validate(schema, payload)


def test_missing_context_rejects_ready_status(schema):
    payload = _load_fixture("missing-context.json")
    payload["work_item"]["status"] = "ready"
    _validate(schema, payload)
    result = validate_packet(payload)
    assert not result.valid


# ---------------------------------------------------------------------------
# Negative: artifact kind enum
# ---------------------------------------------------------------------------

def test_rejects_unknown_artifact_kind(schema):
    payload = _load_fixture("success.json")
    payload["artifacts"][0]["kind"] = "binary_blob"
    with pytest.raises(jsonschema.ValidationError):
        _validate(schema, payload)


# ---------------------------------------------------------------------------
# Blocked fixture
# ---------------------------------------------------------------------------

def test_blocked_fixture_validates(schema):
    payload = _load_fixture("blocked.json")
    _validate(schema, payload)


def test_blocked_fixture_projection_status(schema):
    payload = _load_fixture("blocked.json")
    assert payload["projection"]["computed_status"] == "blocked"
    assert payload["projection"]["blocked_reason"]


def test_blocked_passes_semantic_validation():
    payload = _load_fixture("blocked.json")
    _semantic_validate(payload)


# ---------------------------------------------------------------------------
# Insufficient-evidence fixture
# ---------------------------------------------------------------------------

def test_insufficient_evidence_fixture_validates(schema):
    payload = _load_fixture("insufficient-evidence.json")
    _validate(schema, payload)


def test_insufficient_evidence_projection_status(schema):
    payload = _load_fixture("insufficient-evidence.json")
    assert payload["projection"]["computed_status"] == "insufficient_evidence"
    assert payload["projection"]["blocked_reason"]


def test_insufficient_evidence_passes_semantic_validation():
    payload = _load_fixture("insufficient-evidence.json")
    _semantic_validate(payload)


# ---------------------------------------------------------------------------
# Missing-context fixture
# ---------------------------------------------------------------------------

def test_missing_context_fixture_validates(schema):
    payload = _load_fixture("missing-context.json")
    _validate(schema, payload)


def test_missing_context_projection_blocked(schema):
    payload = _load_fixture("missing-context.json")
    assert payload["projection"]["computed_status"] == "blocked"


def test_missing_context_work_item_not_ready(schema):
    payload = _load_fixture("missing-context.json")
    assert payload["work_item"]["status"] in ("blocked", "draft")


def test_missing_context_passes_semantic_validation():
    payload = _load_fixture("missing-context.json")
    _semantic_validate(payload)


# ---------------------------------------------------------------------------
# Semantic: principal reference resolution
# ---------------------------------------------------------------------------

def test_empty_principals_fails_semantic_when_referenced():
    payload = _load_fixture("success.json")
    payload["principals"] = []
    result = validate_packet(payload)
    assert not result.valid


def test_unknown_principal_ref_fails_semantic():
    payload = _load_fixture("success.json")
    payload["decisions"][0]["decider_principal_id"] = "principal-unknown"
    result = validate_packet(payload)
    assert not result.valid


# ---------------------------------------------------------------------------
# Semantic: projection consistency
# ---------------------------------------------------------------------------

def test_projection_computed_status_matches_gate(schema):
    payload = _load_fixture("success.json")
    assert payload["projection"]["computed_status"] == "completed"
