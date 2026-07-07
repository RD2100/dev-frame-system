"""Tests for Phase 4d: external-review feedback ledger validator.

An `external_review` record accounts for a GPT review round so it can be
tracked offline. It is NOT standalone authority; it must point to:

  - review_round, review_url, external_verdict (external-review-specific scalars)
  - produced_artifact resolving to a declared artifact (the review bundle)
  - evidence_ids non-empty + each resolves + supports + source_artifact resolves
  - gate_decision required, evidence-backed (kind="gate", outcome="pass",
    target_ref == record id, evidence coverage of record evidence_ids)

Plan: "External-review feedback ledger: Normalize accepted/rejected/deferred
GPT review feedback. Review bundle verdict maps to local decision without
becoming authority." (skill-asset-utilization-plan.md:247)

Stop line: "Do not treat GPT output as project authority" (line 270).
"""
from __future__ import annotations

import pytest

from control_plane.review_feedback_validator import (
    ValidationResult,
    validate_review_feedback,
    derive_review_feedback,
)

VALID_VERDICTS = ("accepted", "rejected", "deferred", "conditional")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _review(rf_id="rf-1", review_round=1, review_url="https://chatgpt.com/c/test",
            external_verdict="accepted", produced_artifact="art-bundle",
            evidence_ids=None, gate_decision="dec-1",
            last_used_at="2026-07-06T10:00:00Z",
            promotion_state="adopted", project_id="proj-1"):
    return {
        "id": rf_id,
        "project_id": project_id,
        "review_round": review_round,
        "review_url": review_url,
        "external_verdict": external_verdict,
        "produced_artifact": produced_artifact,
        "evidence_ids": evidence_ids if evidence_ids is not None else ["ev-1"],
        "gate_decision": gate_decision,
        "last_used_at": last_used_at,
        "promotion_state": promotion_state,
    }


def _packet(review_feedback=None, artifacts=None, evidence=None, decisions=None):
    return {
        "review_feedback": review_feedback or [],
        "artifacts": artifacts or [],
        "evidence": evidence or [],
        "decisions": decisions or [],
    }


def _artifact(aid="art-bundle", kind="review_bundle"):
    return {"id": aid, "kind": kind}


def _evidence(eid="ev-1", supports="supports", source_artifact_id="art-bundle"):
    return {"id": eid, "supports": supports, "source_artifact_id": source_artifact_id,
            "claim": "claim", "scope": "scope", "freshness": "fresh",
            "observed_result": "result", "project_id": "proj-1"}


def _decision(did="dec-1", kind="gate", outcome="pass", target_ref="rf-1"):
    return {"id": did, "project_id": "proj-1", "kind": kind, "target_ref": target_ref,
            "decider_principal_id": "principal-1", "outcome": outcome,
            "evidence_ids": ["ev-1"], "rationale": "ok"}


# ---------------------------------------------------------------------------
# validate_review_feedback
# ---------------------------------------------------------------------------

class TestValidateReviewFeedback:
    def test_empty_passes(self):
        result = validate_review_feedback(_packet())
        assert result.valid

    def test_full_valid_record_passes(self):
        rf = _review()
        dec = _decision("dec-1", target_ref="rf-1")
        dec["evidence_ids"] = ["ev-1"]
        pkt = _packet(review_feedback=[rf], artifacts=[_artifact("art-bundle")],
                      evidence=[_evidence("ev-1")], decisions=[dec])
        result = validate_review_feedback(pkt)
        assert result.valid, "\n".join(result.errors)

    def test_review_specific_scalars_required(self):
        """review_round, review_url, external_verdict are required."""
        rf = _review(review_round=None, review_url="", external_verdict="")
        pkt = _packet(review_feedback=[rf], artifacts=[_artifact("art-bundle")],
                      evidence=[_evidence("ev-1")], decisions=[_decision()])
        result = validate_review_feedback(pkt)
        assert not result.valid
        errs = "\n".join(result.errors)
        for field_name in ("review_round", "review_url", "external_verdict"):
            assert field_name in errs

    def test_whitespace_only_required_ids_and_refs_rejected(self):
        blank = " \t\n"
        rf = _review(rf_id=blank, project_id=blank, review_url=blank,
                     produced_artifact=blank, evidence_ids=[blank],
                     gate_decision=blank, last_used_at=blank)
        dec = _decision(blank, target_ref=blank)
        dec["evidence_ids"] = [blank]
        pkt = _packet(review_feedback=[rf], artifacts=[_artifact(blank)],
                      evidence=[_evidence(blank, source_artifact_id=blank)],
                      decisions=[dec])

        result = validate_review_feedback(pkt)

        assert not result.valid
        errs = "\n".join(result.errors)
        for field_name in ("id", "project_id", "review_url", "last_used_at",
                           "produced_artifact", "evidence_ids", "gate_decision"):
            assert field_name in errs

    def test_external_verdict_must_be_valid(self):
        rf = _review(external_verdict="invalid-verdict")
        pkt = _packet(review_feedback=[rf], artifacts=[_artifact("art-bundle")],
                      evidence=[_evidence("ev-1")], decisions=[_decision()])
        result = validate_review_feedback(pkt)
        assert not result.valid
        assert any("external_verdict" in e for e in result.errors)

    def test_produced_artifact_must_resolve(self):
        rf = _review(produced_artifact="art-missing")
        pkt = _packet(review_feedback=[rf], artifacts=[_artifact("art-bundle")],
                      evidence=[_evidence("ev-1")], decisions=[_decision()])
        result = validate_review_feedback(pkt)
        assert not result.valid
        assert any("art-missing" in e for e in result.errors)

    def test_evidence_ids_required_non_empty(self):
        rf = _review(evidence_ids=[])
        pkt = _packet(review_feedback=[rf], artifacts=[_artifact("art-bundle")],
                      decisions=[_decision()])
        result = validate_review_feedback(pkt)
        assert not result.valid
        assert any("evidence_ids" in e for e in result.errors)

    def test_evidence_must_resolve(self):
        rf = _review(evidence_ids=["ev-missing"])
        pkt = _packet(review_feedback=[rf], artifacts=[_artifact("art-bundle")],
                      evidence=[_evidence("ev-1")], decisions=[_decision()])
        result = validate_review_feedback(pkt)
        assert not result.valid
        assert any("ev-missing" in e for e in result.errors)

    def test_evidence_must_support(self):
        rf = _review(evidence_ids=["ev-1"])
        pkt = _packet(review_feedback=[rf], artifacts=[_artifact("art-bundle")],
                      evidence=[_evidence("ev-1", supports="rejects")],
                      decisions=[_decision()])
        result = validate_review_feedback(pkt)
        assert not result.valid
        assert any("supports" in e for e in result.errors)

    def test_evidence_source_artifact_must_resolve(self):
        rf = _review(evidence_ids=["ev-1"])
        pkt = _packet(review_feedback=[rf], artifacts=[_artifact("art-bundle")],
                      evidence=[_evidence("ev-1", source_artifact_id="art-orphan")],
                      decisions=[_decision()])
        result = validate_review_feedback(pkt)
        assert not result.valid
        assert any("source_artifact_id" in e for e in result.errors)

    def test_gate_decision_required(self):
        rf = _review(gate_decision="")
        pkt = _packet(review_feedback=[rf], artifacts=[_artifact("art-bundle")],
                      evidence=[_evidence("ev-1")], decisions=[_decision()])
        result = validate_review_feedback(pkt)
        assert not result.valid
        assert any("gate_decision" in e and "required" in e for e in result.errors)

    def test_gate_decision_must_resolve(self):
        rf = _review(gate_decision="dec-missing")
        pkt = _packet(review_feedback=[rf], artifacts=[_artifact("art-bundle")],
                      evidence=[_evidence("ev-1")], decisions=[_decision()])
        result = validate_review_feedback(pkt)
        assert not result.valid
        assert any("dec-missing" in e for e in result.errors)

    def test_gate_decision_must_be_gate_kind(self):
        rf = _review(gate_decision="dec-1")
        pkt = _packet(review_feedback=[rf], artifacts=[_artifact("art-bundle")],
                      evidence=[_evidence("ev-1")],
                      decisions=[_decision("dec-1", kind="review", target_ref="rf-1")])
        result = validate_review_feedback(pkt)
        assert not result.valid
        assert any("kind" in e and "gate" in e for e in result.errors)

    def test_gate_decision_must_have_pass_outcome(self):
        rf = _review(gate_decision="dec-1")
        pkt = _packet(review_feedback=[rf], artifacts=[_artifact("art-bundle")],
                      evidence=[_evidence("ev-1")],
                      decisions=[_decision("dec-1", outcome="fail", target_ref="rf-1")])
        result = validate_review_feedback(pkt)
        assert not result.valid
        assert any("outcome" in e for e in result.errors)

    def test_gate_decision_target_ref_must_match(self):
        rf = _review(gate_decision="dec-1")
        pkt = _packet(review_feedback=[rf], artifacts=[_artifact("art-bundle")],
                      evidence=[_evidence("ev-1")],
                      decisions=[_decision("dec-1", target_ref="rf-other")])
        result = validate_review_feedback(pkt)
        assert not result.valid
        assert any("target_ref" in e for e in result.errors)

    def test_gate_decision_must_be_evidence_backed(self):
        rf = _review(gate_decision="dec-1")
        dec = _decision("dec-1", target_ref="rf-1")
        dec["evidence_ids"] = []
        pkt = _packet(review_feedback=[rf], artifacts=[_artifact("art-bundle")],
                      evidence=[_evidence("ev-1")], decisions=[dec])
        result = validate_review_feedback(pkt)
        assert not result.valid
        assert any("evidence_ids" in e for e in result.errors)

    def test_gate_decision_evidence_must_resolve(self):
        rf = _review(gate_decision="dec-1")
        dec = _decision("dec-1", target_ref="rf-1")
        dec["evidence_ids"] = ["ev-missing"]
        pkt = _packet(review_feedback=[rf], artifacts=[_artifact("art-bundle")],
                      evidence=[_evidence("ev-1")], decisions=[dec])
        result = validate_review_feedback(pkt)
        assert not result.valid
        assert any("ev-missing" in e for e in result.errors)

    def test_gate_decision_evidence_must_cover_record_evidence(self):
        rf = _review(evidence_ids=["ev-1", "ev-2"], gate_decision="dec-1")
        dec = _decision("dec-1", target_ref="rf-1")
        dec["evidence_ids"] = ["ev-1"]
        pkt = _packet(review_feedback=[rf], artifacts=[_artifact("art-bundle")],
                      evidence=[_evidence("ev-1"), _evidence("ev-2")],
                      decisions=[dec])
        result = validate_review_feedback(pkt)
        assert not result.valid
        assert any("cover" in e or "cited" in e for e in result.errors)

    def test_promotion_state_adopted_without_gate_decision_fails(self):
        rf = _review(promotion_state="adopted", gate_decision="")
        pkt = _packet(review_feedback=[rf], artifacts=[_artifact("art-bundle")],
                      evidence=[_evidence("ev-1")], decisions=[_decision()])
        result = validate_review_feedback(pkt)
        assert not result.valid

    def test_promotion_state_adopted_requires_gate_pass(self):
        rf = _review(promotion_state="adopted", gate_decision="dec-1")
        pkt = _packet(review_feedback=[rf], artifacts=[_artifact("art-bundle")],
                      evidence=[_evidence("ev-1")],
                      decisions=[_decision("dec-1", outcome="fail", target_ref="rf-1")])
        result = validate_review_feedback(pkt)
        assert not result.valid

    def test_promotion_state_pending_allowed(self):
        rf = _review(promotion_state="pending", external_verdict="deferred",
                     gate_decision="dec-1")
        dec = _decision("dec-1", target_ref="rf-1")
        dec["evidence_ids"] = ["ev-1"]
        pkt = _packet(review_feedback=[rf], artifacts=[_artifact("art-bundle")],
                      evidence=[_evidence("ev-1")], decisions=[dec])
        result = validate_review_feedback(pkt)
        assert result.valid, "\n".join(result.errors)

    def test_deferred_verdict_pending_state_passes(self):
        """deferred external_verdict with pending promotion_state is valid."""
        rf = _review(external_verdict="deferred", promotion_state="pending",
                     gate_decision="dec-1")
        dec = _decision("dec-1", target_ref="rf-1")
        dec["evidence_ids"] = ["ev-1"]
        pkt = _packet(review_feedback=[rf], artifacts=[_artifact("art-bundle")],
                      evidence=[_evidence("ev-1")], decisions=[dec])
        result = validate_review_feedback(pkt)
        assert result.valid, "\n".join(result.errors)

    def test_conditional_verdict_passes(self):
        """conditional external_verdict is a valid verdict type."""
        rf = _review(external_verdict="conditional", promotion_state="adopted",
                     gate_decision="dec-1")
        dec = _decision("dec-1", target_ref="rf-1")
        dec["evidence_ids"] = ["ev-1"]
        pkt = _packet(review_feedback=[rf], artifacts=[_artifact("art-bundle")],
                      evidence=[_evidence("ev-1")], decisions=[dec])
        result = validate_review_feedback(pkt)
        assert result.valid, "\n".join(result.errors)

    def test_rejected_verdict_with_adopted_fails(self):
        """rejected external_verdict cannot have promotion_state=adopted."""
        rf = _review(external_verdict="rejected", promotion_state="adopted",
                     gate_decision="dec-1")
        dec = _decision("dec-1", target_ref="rf-1")
        dec["evidence_ids"] = ["ev-1"]
        pkt = _packet(review_feedback=[rf], artifacts=[_artifact("art-bundle")],
                      evidence=[_evidence("ev-1")], decisions=[dec])
        result = validate_review_feedback(pkt)
        assert not result.valid
        assert any("rejected" in e for e in result.errors)

    def test_rejected_verdict_with_rejected_state_passes(self):
        """rejected external_verdict with promotion_state=rejected is valid."""
        rf = _review(external_verdict="rejected", promotion_state="rejected",
                     gate_decision="dec-1")
        dec = _decision("dec-1", target_ref="rf-1")
        dec["evidence_ids"] = ["ev-1"]
        pkt = _packet(review_feedback=[rf], artifacts=[_artifact("art-bundle")],
                      evidence=[_evidence("ev-1")], decisions=[dec])
        result = validate_review_feedback(pkt)
        assert result.valid, "\n".join(result.errors)

    def test_multiple_errors_accumulated(self):
        rf = _review(review_round=None, produced_artifact="art-missing",
                     evidence_ids=["ev-missing"], gate_decision="dec-missing")
        pkt = _packet(review_feedback=[rf], artifacts=[_artifact("art-bundle")],
                      evidence=[_evidence("ev-1")], decisions=[_decision()])
        result = validate_review_feedback(pkt)
        assert not result.valid
        assert len(result.errors) >= 4


# ---------------------------------------------------------------------------
# derive_review_feedback
# ---------------------------------------------------------------------------

class TestDeriveReviewFeedback:
    def test_empty_packet(self):
        result = derive_review_feedback(_packet())
        assert result["review_feedback_count"] == 0
        assert result["adopted_count"] == 0
        assert result["by_verdict"] == {}

    def test_counts_total_and_adopted(self):
        rf1 = _review(rf_id="rf-1", promotion_state="adopted", gate_decision="dec-1")
        rf2 = _review(rf_id="rf-2", external_verdict="deferred",
                      promotion_state="pending", gate_decision="dec-2")
        dec1 = _decision("dec-1", target_ref="rf-1"); dec1["evidence_ids"] = ["ev-1"]
        dec2 = _decision("dec-2", target_ref="rf-2"); dec2["evidence_ids"] = ["ev-1"]
        pkt = _packet(review_feedback=[rf1, rf2], artifacts=[_artifact("art-bundle")],
                      evidence=[_evidence("ev-1")], decisions=[dec1, dec2])
        result = derive_review_feedback(pkt)
        assert result["review_feedback_count"] == 2
        assert result["adopted_count"] == 1

    def test_does_not_invent_adoption_without_gate_pass(self):
        rf = _review(rf_id="rf-1", promotion_state="adopted", gate_decision="dec-1")
        dec = _decision("dec-1", outcome="fail", target_ref="rf-1")
        dec["evidence_ids"] = ["ev-1"]
        pkt = _packet(review_feedback=[rf], artifacts=[_artifact("art-bundle")],
                      evidence=[_evidence("ev-1")], decisions=[dec])
        result = derive_review_feedback(pkt)
        assert result["adopted_count"] == 0

    def test_does_not_invent_adoption_without_evidence_backing(self):
        rf = _review(rf_id="rf-1", promotion_state="adopted", gate_decision="dec-1")
        dec = _decision("dec-1", target_ref="rf-1")
        dec["evidence_ids"] = []
        pkt = _packet(review_feedback=[rf], artifacts=[_artifact("art-bundle")],
                      evidence=[_evidence("ev-1")], decisions=[dec])
        result = derive_review_feedback(pkt)
        assert result["adopted_count"] == 0

    def test_does_not_count_adoption_when_produced_artifact_missing(self):
        rf = _review(rf_id="rf-1", produced_artifact="art-missing",
                     promotion_state="adopted", gate_decision="dec-1")
        dec = _decision("dec-1", target_ref="rf-1")
        dec["evidence_ids"] = ["ev-1"]
        pkt = _packet(review_feedback=[rf], artifacts=[_artifact("art-bundle")],
                      evidence=[_evidence("ev-1")], decisions=[dec])
        result = derive_review_feedback(pkt)
        assert result["adopted_count"] == 0

    def test_does_not_count_adoption_when_review_scalar_missing(self):
        rf = _review(rf_id="rf-1", review_round=None,
                     promotion_state="adopted", gate_decision="dec-1")
        dec = _decision("dec-1", target_ref="rf-1")
        dec["evidence_ids"] = ["ev-1"]
        pkt = _packet(review_feedback=[rf], artifacts=[_artifact("art-bundle")],
                      evidence=[_evidence("ev-1")], decisions=[dec])
        result = derive_review_feedback(pkt)
        assert result["adopted_count"] == 0

    def test_does_not_count_whitespace_only_adoption_chain(self):
        blank = " \t\n"
        rf = _review(rf_id=blank, project_id=blank, review_url=blank,
                     produced_artifact=blank, evidence_ids=[blank],
                     gate_decision=blank, last_used_at=blank,
                     promotion_state="adopted")
        dec = _decision(blank, target_ref=blank)
        dec["evidence_ids"] = [blank]
        pkt = _packet(review_feedback=[rf], artifacts=[_artifact(blank)],
                      evidence=[_evidence(blank, source_artifact_id=blank)],
                      decisions=[dec])

        result = derive_review_feedback(pkt)

        assert result["adopted_count"] == 0
        assert result["by_verdict"]["accepted"]["adopted_count"] == 0

    def test_projection_does_not_count_rejected_verdict_as_adopted(self):
        """projection must not count rejected+adopted as adopted —
        shared helper must enforce this, not just validator."""
        rf = _review(rf_id="rf-1", external_verdict="rejected",
                     promotion_state="adopted", gate_decision="dec-1")
        dec = _decision("dec-1", target_ref="rf-1")
        dec["evidence_ids"] = ["ev-1"]
        pkt = _packet(review_feedback=[rf], artifacts=[_artifact("art-bundle")],
                      evidence=[_evidence("ev-1")], decisions=[dec])
        assert not validate_review_feedback(pkt).valid
        result = derive_review_feedback(pkt)
        assert result["adopted_count"] == 0
        assert result["by_verdict"]["rejected"]["adopted_count"] == 0

    def test_groups_by_verdict(self):
        rf1 = _review(rf_id="rf-1", external_verdict="accepted", gate_decision="dec-1")
        rf2 = _review(rf_id="rf-2", external_verdict="accepted", gate_decision="dec-2")
        rf3 = _review(rf_id="rf-3", external_verdict="conditional", gate_decision="dec-3")
        dec1 = _decision("dec-1", target_ref="rf-1"); dec1["evidence_ids"] = ["ev-1"]
        dec2 = _decision("dec-2", target_ref="rf-2"); dec2["evidence_ids"] = ["ev-1"]
        dec3 = _decision("dec-3", target_ref="rf-3"); dec3["evidence_ids"] = ["ev-1"]
        pkt = _packet(review_feedback=[rf1, rf2, rf3], artifacts=[_artifact("art-bundle")],
                      evidence=[_evidence("ev-1")], decisions=[dec1, dec2, dec3])
        result = derive_review_feedback(pkt)
        assert result["by_verdict"]["accepted"]["count"] == 2
        assert result["by_verdict"]["conditional"]["count"] == 1

    def test_projection_is_read_only(self):
        rf = _review(gate_decision="dec-1")
        dec = _decision("dec-1", target_ref="rf-1"); dec["evidence_ids"] = ["ev-1"]
        pkt = _packet(review_feedback=[rf], artifacts=[_artifact("art-bundle")],
                      evidence=[_evidence("ev-1")], decisions=[dec])
        original = {"review_feedback": list(pkt["review_feedback"])}
        derive_review_feedback(pkt)
        assert pkt["review_feedback"] == original["review_feedback"]
