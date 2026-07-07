"""Tests for P2-1: evaluation integrity — missing dimensions never default to pass.

Per design-coverage-gap-remediation-plan.md:233-255:

  - no missing dimension contributes to an aggregate score;
  - evaluation cannot override a blocked gate.
"""
from __future__ import annotations

import pytest

from control_plane.evaluation_integrity_validator import (
    ValidationResult,
    validate_evaluation_integrity,
    derive_evaluation_integrity,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _entry(eid="ev-1", evaluation_id="eval-run-1", dimension="code-review",
           outcome="PASS", evidence_refs=None, gate_ref="gate-1"):
    return {
        "id": eid,
        "evaluation_id": evaluation_id,
        "dimension": dimension,
        "outcome": outcome,
        "evidence_refs": evidence_refs if evidence_refs is not None else ["ev-r1"],
        "gate_ref": gate_ref,
    }


def _packet(evaluations=None, evidence=None, artifacts=None, gates=None):
    return {
        "evaluations": evaluations or [],
        "evidence": evidence or [],
        "artifacts": artifacts or [],
        "gates": gates or [],
    }


def _evidence(eid="ev-r1", supports="supports", source_artifact_id="art-out"):
    return {
        "id": eid,
        "supports": supports,
        "source_artifact_id": source_artifact_id,
        "claim": "claim",
        "scope": "scope",
        "freshness": "fresh",
        "observed_result": "result",
        "project_id": "proj-1",
    }


def _artifact(aid="art-out", kind="run_output"):
    return {"id": aid, "kind": kind}


def _gate(gid="gate-1", kind="gate", outcome="BLOCKED"):
    return {
        "id": gid,
        "project_id": "proj-1",
        "kind": kind,
        "outcome": outcome,
        "decider_principal_id": "p-1",
        "evidence_ids": ["ev-r1"],
        "rationale": "ok",
    }


# ---------------------------------------------------------------------------
# validate_evaluation_integrity
# ---------------------------------------------------------------------------

class TestValidateEvaluationIntegrity:
    def test_empty_passes(self):
        result = validate_evaluation_integrity(_packet())
        assert result.valid

    def test_full_valid_pass_passes(self):
        pkt = _packet(
            evaluations=[_entry(outcome="PASS", evidence_refs=["ev-r1"])],
            evidence=[_evidence("ev-r1")],
            artifacts=[_artifact("art-out")],
            gates=[_gate("gate-1", outcome="PASS")],
        )
        result = validate_evaluation_integrity(pkt)
        assert result.valid, "\n".join(result.errors)

    def test_full_valid_not_evaluated_passes(self):
        pkt = _packet(
            evaluations=[_entry(outcome="NOT_EVALUATED", evidence_refs=[])],
            evidence=[_evidence("ev-r1")],
            artifacts=[_artifact("art-out")],
            gates=[_gate("gate-1", outcome="BLOCKED")],
        )
        result = validate_evaluation_integrity(pkt)
        assert result.valid, "\n".join(result.errors)

    def test_full_valid_blocked_passes(self):
        pkt = _packet(
            evaluations=[_entry(outcome="BLOCKED", evidence_refs=[])],
            evidence=[_evidence("ev-r1")],
            artifacts=[_artifact("art-out")],
            gates=[_gate("gate-1", outcome="BLOCKED")],
        )
        result = validate_evaluation_integrity(pkt)
        assert result.valid, "\n".join(result.errors)

    def test_required_fields(self):
        for field in ("id", "evaluation_id", "dimension", "outcome"):
            e = _entry()
            e[field] = ""
            result = validate_evaluation_integrity(_packet(evaluations=[e]))
            assert not result.valid
            assert any(f"{field} is required" in err for err in result.errors)

    def test_whitespace_required_strings_fail(self):
        e = _entry(eid="   ", evaluation_id="\t", dimension="\n", outcome=" ")
        result = validate_evaluation_integrity(_packet(evaluations=[e]))
        assert not result.valid
        assert any("id is required" in err for err in result.errors)
        assert any("evaluation_id is required" in err for err in result.errors)
        assert any("dimension is required" in err for err in result.errors)
        assert any("outcome is required" in err for err in result.errors)

    def test_outcome_must_be_valid(self):
        e = _entry(outcome="SKIPPED")
        result = validate_evaluation_integrity(_packet(evaluations=[e]))
        assert not result.valid
        assert any("SKIPPED" in err for err in result.errors)

    def test_pass_requires_evidence(self):
        """PASS without evidence_refs is rejected."""
        e = _entry(outcome="PASS", evidence_refs=[])
        result = validate_evaluation_integrity(
            _packet(evaluations=[e], gates=[_gate("gate-1", outcome="PASS")])
        )
        assert not result.valid
        assert any("evidence_refs" in err for err in result.errors)

    def test_fail_requires_evidence(self):
        """FAIL without evidence_refs is rejected — missing dimension must be
        NOT_EVALUATED or BLOCKED, never PASS or FAIL."""
        e = _entry(outcome="FAIL", evidence_refs=[])
        result = validate_evaluation_integrity(
            _packet(evaluations=[e], gates=[_gate("gate-1", outcome="BLOCKED")])
        )
        assert not result.valid
        assert any("NOT_EVALUATED" in err for err in result.errors)

    def test_missing_dimension_pass_rejected(self):
        """Missing evidence on a PASS outcome is must-flag."""
        e = _entry(outcome="PASS", evidence_refs=["ev-missing"])
        result = validate_evaluation_integrity(
            _packet(evaluations=[e], evidence=[_evidence("ev-r1")],
                    artifacts=[_artifact("art-out")])
        )
        assert not result.valid
        assert any("ev-missing" in err for err in result.errors)

    def test_evidence_must_support(self):
        e = _entry(outcome="PASS", evidence_refs=["ev-r1"])
        result = validate_evaluation_integrity(
            _packet(evaluations=[e],
                    evidence=[_evidence("ev-r1", supports="rejects")],
                    artifacts=[_artifact("art-out")])
        )
        assert not result.valid
        assert any("supports" in err for err in result.errors)

    def test_evidence_source_artifact_must_resolve(self):
        e = _entry(outcome="PASS", evidence_refs=["ev-r1"])
        result = validate_evaluation_integrity(
            _packet(evaluations=[e],
                    evidence=[_evidence("ev-r1", source_artifact_id="art-orphan")],
                    artifacts=[_artifact("art-out")])
        )
        assert not result.valid
        assert any("source_artifact_id" in err for err in result.errors)

    def test_evidence_source_artifact_required(self):
        e = _entry(outcome="PASS", evidence_refs=["ev-r1"])
        result = validate_evaluation_integrity(
            _packet(evaluations=[e],
                    evidence=[_evidence("ev-r1", source_artifact_id="")],
                    artifacts=[_artifact("art-out")])
        )
        assert not result.valid
        assert any("source_artifact_id" in err for err in result.errors)

    def test_pass_cannot_override_blocked_gate(self):
        """P0: evaluation PASS cannot override a BLOCKED gate."""
        e = _entry(outcome="PASS", evidence_refs=["ev-r1"], gate_ref="gate-1")
        result = validate_evaluation_integrity(
            _packet(evaluations=[e],
                    evidence=[_evidence("ev-r1")],
                    artifacts=[_artifact("art-out")],
                    gates=[_gate("gate-1", outcome="BLOCKED")])
        )
        assert not result.valid
        assert any("BLOCKED" in err and "override" in err for err in result.errors)

    def test_pass_can_reference_pass_gate(self):
        """Pass with a PASS gate is fine."""
        e = _entry(outcome="PASS", evidence_refs=["ev-r1"], gate_ref="gate-1")
        result = validate_evaluation_integrity(
            _packet(evaluations=[e],
                    evidence=[_evidence("ev-r1")],
                    artifacts=[_artifact("art-out")],
                    gates=[_gate("gate-1", outcome="PASS")])
        )
        assert result.valid

    def test_fail_does_not_trigger_gate_override(self):
        """FAIL with BLOCKED gate does not trigger override — only PASS triggers."""
        e = _entry(outcome="FAIL", evidence_refs=["ev-r1"], gate_ref="gate-1")
        result = validate_evaluation_integrity(
            _packet(evaluations=[e],
                    evidence=[_evidence("ev-r1")],
                    artifacts=[_artifact("art-out")],
                    gates=[_gate("gate-1", outcome="BLOCKED")])
        )
        assert result.valid

    def test_not_evaluated_no_gate_override(self):
        e = _entry(outcome="NOT_EVALUATED", evidence_refs=[], gate_ref="gate-1")
        result = validate_evaluation_integrity(
            _packet(evaluations=[e],
                    gates=[_gate("gate-1", outcome="BLOCKED")])
        )
        assert result.valid

    def test_all_four_valid_outcomes_accepted(self):
        """All four valid outcomes (PASS, FAIL, NOT_EVALUATED, BLOCKED) are accepted."""
        for outcome in ("PASS", "FAIL", "NOT_EVALUATED", "BLOCKED"):
            refs = ["ev-r1"] if outcome in ("PASS", "FAIL") else []
            e = _entry(outcome=outcome, evidence_refs=refs)
            # Adjust gate to avoid blocked override for PASS
            gates = [_gate("gate-1", outcome="PASS" if outcome == "PASS" else "BLOCKED")]
            result = validate_evaluation_integrity(
                _packet(evaluations=[e],
                        evidence=[_evidence("ev-r1")],
                        artifacts=[_artifact("art-out")],
                        gates=gates)
            )
            if outcome == "PASS" or outcome == "FAIL" or outcome == "NOT_EVALUATED" or outcome == "BLOCKED":
                assert result.valid, f"{outcome}: " + "\n".join(result.errors)

    def test_multiple_errors_accumulated(self):
        e = _entry(eid="", evaluation_id="", dimension="", outcome="INVALID",
                   evidence_refs=[])
        result = validate_evaluation_integrity(_packet(evaluations=[e]))
        assert not result.valid
        assert len(result.errors) >= 3  # id, evaluation_id, dimension, outcome, missing evidence

    def test_invalid_entry_skips_evidence_check(self):
        """An entry that fails base check (e.g. missing id) still gets base errors
        but evidence check is skipped to avoid cascading nonsense."""
        e = _entry(eid="", outcome="PASS", evidence_refs=["ev-missing"])
        result = validate_evaluation_integrity(_packet(evaluations=[e]))
        assert not result.valid
        # Should have id required error, not evidence missing error
        assert any("id" in err and "required" in err for err in result.errors)

    def test_promotion_state_not_required_for_evaluation(self):
        """Unlike skill governance, evaluation entries don't need promotion_state."""
        e = _entry(outcome="PASS", evidence_refs=["ev-r1"])
        result = validate_evaluation_integrity(
            _packet(evaluations=[e],
                    evidence=[_evidence("ev-r1")],
                    artifacts=[_artifact("art-out")],
                    gates=[_gate("gate-1", outcome="PASS")])
        )
        assert result.valid

    def test_pass_requires_gate_ref(self):
        """PASS without gate_ref is rejected — evaluated outcomes must reference a gate."""
        e = _entry(outcome="PASS", evidence_refs=["ev-r1"], gate_ref="")
        result = validate_evaluation_integrity(
            _packet(evaluations=[e],
                    evidence=[_evidence("ev-r1")],
                    artifacts=[_artifact("art-out")])
        )
        assert not result.valid
        assert any("gate_ref" in err for err in result.errors)

    def test_fail_requires_gate_ref(self):
        """FAIL without gate_ref is rejected — evaluated outcomes must reference a gate."""
        e = _entry(outcome="FAIL", evidence_refs=["ev-r1"], gate_ref="")
        result = validate_evaluation_integrity(
            _packet(evaluations=[e],
                    evidence=[_evidence("ev-r1")],
                    artifacts=[_artifact("art-out")])
        )
        assert not result.valid
        assert any("gate_ref" in err for err in result.errors)

    def test_pass_with_missing_gate_ref_rejected(self):
        """PASS referencing a gate that doesn't exist is rejected."""
        e = _entry(outcome="PASS", evidence_refs=["ev-r1"], gate_ref="gate-missing")
        result = validate_evaluation_integrity(
            _packet(evaluations=[e],
                    evidence=[_evidence("ev-r1")],
                    artifacts=[_artifact("art-out")],
                    gates=[_gate("gate-1", outcome="BLOCKED")])
        )
        assert not result.valid
        assert any("gate-missing" in err and "resolve" in err for err in result.errors)

    def test_fail_with_unresolved_gate_ref_rejected(self):
        """FAIL referencing a gate that doesn't exist is rejected."""
        e = _entry(outcome="FAIL", evidence_refs=["ev-r1"], gate_ref="gate-missing")
        result = validate_evaluation_integrity(
            _packet(evaluations=[e],
                    evidence=[_evidence("ev-r1")],
                    artifacts=[_artifact("art-out")],
                    gates=[_gate("gate-1", outcome="BLOCKED")])
        )
        assert not result.valid
        assert any("gate-missing" in err and "resolve" in err for err in result.errors)

    def test_fail_with_valid_gate_passes(self):
        """FAIL with a valid resolvable gate is accepted."""
        e = _entry(outcome="FAIL", evidence_refs=["ev-r1"], gate_ref="gate-1")
        result = validate_evaluation_integrity(
            _packet(evaluations=[e],
                    evidence=[_evidence("ev-r1")],
                    artifacts=[_artifact("art-out")],
                    gates=[_gate("gate-1", outcome="BLOCKED")])
        )
        assert result.valid, "\n".join(result.errors)


# ---------------------------------------------------------------------------
# derive_evaluation_integrity
# ---------------------------------------------------------------------------

class TestDeriveEvaluationIntegrity:
    def test_empty_packet(self):
        result = derive_evaluation_integrity(_packet())
        assert result["total"] == 0
        assert result["pass_count"] == 0
        assert result["fail_count"] == 0
        assert result["not_evaluated_count"] == 0
        assert result["blocked_count"] == 0
        assert result["by_dimension"] == {}

    def test_counts_valid_pass(self):
        pkt = _packet(
            evaluations=[_entry(outcome="PASS", evidence_refs=["ev-r1"])],
            evidence=[_evidence("ev-r1")],
            artifacts=[_artifact("art-out")],
            gates=[_gate("gate-1", outcome="PASS")],
        )
        result = derive_evaluation_integrity(pkt)
        assert result["pass_count"] == 1

    def test_counts_valid_fail(self):
        pkt = _packet(
            evaluations=[_entry(outcome="FAIL", evidence_refs=["ev-r1"])],
            evidence=[_evidence("ev-r1")],
            artifacts=[_artifact("art-out")],
            gates=[_gate("gate-1", outcome="BLOCKED")],
        )
        result = derive_evaluation_integrity(pkt)
        assert result["fail_count"] == 1

    def test_counts_not_evaluated(self):
        pkt = _packet(
            evaluations=[_entry(outcome="NOT_EVALUATED", evidence_refs=[])],
            gates=[_gate("gate-1", outcome="BLOCKED")],
        )
        result = derive_evaluation_integrity(pkt)
        assert result["not_evaluated_count"] == 1

    def test_counts_blocked(self):
        pkt = _packet(
            evaluations=[_entry(outcome="BLOCKED", evidence_refs=[])],
            gates=[_gate("gate-1", outcome="BLOCKED")],
        )
        result = derive_evaluation_integrity(pkt)
        assert result["blocked_count"] == 1

    def test_does_not_count_invalid(self):
        e = _entry(outcome="PASS", evidence_refs=["ev-missing"])
        result = derive_evaluation_integrity(
            _packet(evaluations=[e], evidence=[_evidence("ev-r1")],
                    artifacts=[_artifact("art-out")])
        )
        assert result["pass_count"] == 0

    def test_does_not_count_pass_overriding_blocked_gate(self):
        """Projection must not count a PASS that overrides a BLOCKED gate."""
        e = _entry(outcome="PASS", evidence_refs=["ev-r1"], gate_ref="gate-1")
        result = derive_evaluation_integrity(
            _packet(evaluations=[e],
                    evidence=[_evidence("ev-r1")],
                    artifacts=[_artifact("art-out")],
                    gates=[_gate("gate-1", outcome="BLOCKED")])
        )
        assert result["pass_count"] == 0

    def test_does_not_count_missing_evidence_as_pass(self):
        """No evidence -> must not count as PASS."""
        e = _entry(outcome="PASS", evidence_refs=[])
        result = derive_evaluation_integrity(
            _packet(evaluations=[e], gates=[_gate("gate-1", outcome="PASS")])
        )
        assert result["pass_count"] == 0

    def test_does_not_count_missing_gate_ref_as_pass(self):
        """Missing gate_ref -> must not count as PASS."""
        e = _entry(outcome="PASS", evidence_refs=["ev-r1"], gate_ref="")
        result = derive_evaluation_integrity(
            _packet(evaluations=[e],
                    evidence=[_evidence("ev-r1")],
                    artifacts=[_artifact("art-out")])
        )
        assert result["pass_count"] == 0

    def test_does_not_count_unresolved_gate_ref_as_pass(self):
        """Unresolved gate_ref -> must not count as PASS."""
        e = _entry(outcome="PASS", evidence_refs=["ev-r1"], gate_ref="gate-missing")
        result = derive_evaluation_integrity(
            _packet(evaluations=[e],
                    evidence=[_evidence("ev-r1")],
                    artifacts=[_artifact("art-out")],
                    gates=[_gate("gate-1", outcome="BLOCKED")])
        )
        assert result["pass_count"] == 0

    def test_does_not_count_unresolved_gate_ref_as_fail(self):
        """Unresolved gate_ref -> FAIL also must not be counted."""
        e = _entry(outcome="FAIL", evidence_refs=["ev-r1"], gate_ref="gate-missing")
        result = derive_evaluation_integrity(
            _packet(evaluations=[e],
                    evidence=[_evidence("ev-r1")],
                    artifacts=[_artifact("art-out")],
                    gates=[_gate("gate-1", outcome="BLOCKED")])
        )
        assert result["fail_count"] == 0

    def test_groups_by_dimension(self):
        e1 = _entry(eid="e1", dimension="code-review", outcome="PASS",
                    evidence_refs=["ev-r1"])
        e2 = _entry(eid="e2", dimension="code-review", outcome="FAIL",
                    evidence_refs=["ev-r1"])
        e3 = _entry(eid="e3", dimension="security", outcome="NOT_EVALUATED",
                    evidence_refs=[])
        pkt = _packet(
            evaluations=[e1, e2, e3],
            evidence=[_evidence("ev-r1")],
            artifacts=[_artifact("art-out")],
            gates=[_gate("gate-1", outcome="PASS")],
        )
        result = derive_evaluation_integrity(pkt)
        assert result["by_dimension"]["code-review"]["total"] == 2
        assert result["by_dimension"]["code-review"]["pass"] == 1
        assert result["by_dimension"]["code-review"]["fail"] == 1
        assert result["by_dimension"]["security"]["total"] == 1
        assert result["by_dimension"]["security"]["not_evaluated"] == 1

    def test_projection_is_read_only(self):
        pkt = _packet(
            evaluations=[_entry(outcome="PASS", evidence_refs=["ev-r1"])],
            evidence=[_evidence("ev-r1")],
            artifacts=[_artifact("art-out")],
            gates=[_gate("gate-1", outcome="PASS")],
        )
        original = {"evaluations": list(pkt["evaluations"])}
        derive_evaluation_integrity(pkt)
        assert pkt["evaluations"] == original["evaluations"]

    def test_does_not_count_with_unsupporting_evidence(self):
        e = _entry(outcome="PASS", evidence_refs=["ev-r1"])
        result = derive_evaluation_integrity(
            _packet(evaluations=[e],
                    evidence=[_evidence("ev-r1", supports="rejects")],
                    artifacts=[_artifact("art-out")])
        )
        assert result["pass_count"] == 0

    def test_does_not_count_with_orphan_source_artifact(self):
        e = _entry(outcome="PASS", evidence_refs=["ev-r1"])
        result = derive_evaluation_integrity(
            _packet(evaluations=[e],
                    evidence=[_evidence("ev-r1", source_artifact_id="art-orphan")],
                    artifacts=[_artifact("art-out")])
        )
        assert result["pass_count"] == 0
