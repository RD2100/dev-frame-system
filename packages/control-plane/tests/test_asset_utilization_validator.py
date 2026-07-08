"""Tests for Phase 4b: asset_utilization record validator.

asset_utilization records must point to existing artifacts, evidence, and
gate decisions — they are not standalone authority. An asset's promotion
state only advances when an evidence-backed gate decision accepts it.

Minimum record fields (per skill-asset-utilization-plan.md):
  asset_id, asset_type, source_tier, selected_for_work_type,
  selection_reason, produced_artifact, evidence_ids, gate_decision,
  last_used_at, promotion_state
"""
from __future__ import annotations

import pytest

from control_plane.asset_utilization_validator import (
    ValidationResult,
    validate_asset_utilization,
    derive_asset_utilization,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _asset(au_id="au-1", asset_id="skill-tdd", asset_type="skill",
           source_tier="canonical", selected_for_work_type="phase-1a-kernel",
           selection_reason="required by router", produced_artifact="art-out",
           evidence_ids=None, gate_decision="dec-1", last_used_at="2026-07-06T10:00:00Z",
           promotion_state="adopted", project_id="proj-1"):
    return {
        "id": au_id,
        "project_id": project_id,
        "asset_id": asset_id,
        "asset_type": asset_type,
        "source_tier": source_tier,
        "selected_for_work_type": selected_for_work_type,
        "selection_reason": selection_reason,
        "produced_artifact": produced_artifact,
        "evidence_ids": evidence_ids if evidence_ids is not None else ["ev-1"],
        "gate_decision": gate_decision,
        "last_used_at": last_used_at,
        "promotion_state": promotion_state,
    }


def _packet(asset_utilization=None, artifacts=None, evidence=None, decisions=None):
    return {
        "asset_utilization": asset_utilization or [],
        "artifacts": artifacts or [],
        "evidence": evidence or [],
        "decisions": decisions or [],
    }


def _artifact(aid="art-out", kind="run_output"):
    return {"id": aid, "kind": kind}


def _evidence(eid="ev-1", supports="supports", source_artifact_id="art-out"):
    return {"id": eid, "supports": supports, "source_artifact_id": source_artifact_id,
            "claim": "claim", "scope": "scope", "freshness": "fresh",
            "observed_result": "result", "project_id": "proj-1"}


def _decision(did="dec-1", kind="gate", outcome="pass", target_ref="au-1"):
    return {"id": did, "project_id": "proj-1", "kind": kind, "target_ref": target_ref,
            "decider_principal_id": "principal-1", "outcome": outcome,
            "evidence_ids": ["ev-1"], "rationale": "ok"}


# ---------------------------------------------------------------------------
# validate_asset_utilization
# ---------------------------------------------------------------------------

class TestValidateAssetUtilization:
    def test_empty_passes(self):
        result = validate_asset_utilization(_packet())
        assert result.valid

    def test_full_valid_record_passes(self):
        au = _asset()
        dec = _decision("dec-1", kind="gate", outcome="pass", target_ref="au-1")
        dec["evidence_ids"] = ["ev-1"]
        pkt = _packet(asset_utilization=[au], artifacts=[_artifact("art-out")],
                      evidence=[_evidence("ev-1", source_artifact_id="art-out")],
                      decisions=[dec])
        result = validate_asset_utilization(pkt)
        assert result.valid, "\n".join(result.errors)

    def test_whitespace_only_required_scalar_fails(self):
        au = _asset(asset_id="   ")
        pkt = _packet(asset_utilization=[au], artifacts=[_artifact("art-out")],
                      evidence=[_evidence("ev-1")], decisions=[_decision()])
        result = validate_asset_utilization(pkt)
        assert not result.valid
        assert any("asset_id" in e and "required" in e for e in result.errors)

    def test_missing_produced_artifact_fails(self):
        au = _asset(produced_artifact="art-missing")
        pkt = _packet(asset_utilization=[au], artifacts=[_artifact("art-out")],
                      evidence=[_evidence("ev-1")], decisions=[_decision()])
        result = validate_asset_utilization(pkt)
        assert not result.valid
        assert any("art-missing" in e for e in result.errors)

    def test_missing_evidence_fails(self):
        au = _asset(evidence_ids=["ev-missing"])
        pkt = _packet(asset_utilization=[au], artifacts=[_artifact("art-out")],
                      evidence=[_evidence("ev-1")], decisions=[_decision()])
        result = validate_asset_utilization(pkt)
        assert not result.valid
        assert any("ev-missing" in e for e in result.errors)

    def test_evidence_must_support(self):
        au = _asset(evidence_ids=["ev-1"])
        pkt = _packet(asset_utilization=[au], artifacts=[_artifact("art-out")],
                      evidence=[_evidence("ev-1", supports="rejects")],
                      decisions=[_decision()])
        result = validate_asset_utilization(pkt)
        assert not result.valid
        assert any("supports" in e for e in result.errors)

    def test_evidence_source_artifact_must_resolve(self):
        au = _asset(evidence_ids=["ev-1"])
        pkt = _packet(asset_utilization=[au], artifacts=[_artifact("art-out")],
                      evidence=[_evidence("ev-1", source_artifact_id="art-orphan")],
                      decisions=[_decision()])
        result = validate_asset_utilization(pkt)
        assert not result.valid
        assert any("source_artifact_id" in e for e in result.errors)

    def test_whitespace_only_evidence_source_ref_does_not_resolve(self):
        au = _asset(evidence_ids=["ev-1"])
        dec = _decision("dec-1", target_ref="au-1")
        dec["evidence_ids"] = ["ev-1"]
        pkt = _packet(asset_utilization=[au],
                      artifacts=[_artifact("art-out"), _artifact("   ")],
                      evidence=[_evidence("ev-1", source_artifact_id="   ")],
                      decisions=[dec])
        result = validate_asset_utilization(pkt)
        assert not result.valid
        assert any("source_artifact_id" in e for e in result.errors)

    def test_evidence_ids_required_non_empty(self):
        au = _asset(evidence_ids=[])
        pkt = _packet(asset_utilization=[au], artifacts=[_artifact("art-out")],
                      decisions=[_decision()])
        result = validate_asset_utilization(pkt)
        assert not result.valid
        assert any("evidence_ids" in e for e in result.errors)

    def test_gate_decision_required(self):
        """gate_decision is a required scalar field per plan minimum fields."""
        au = _asset(gate_decision="")
        pkt = _packet(asset_utilization=[au], artifacts=[_artifact("art-out")],
                      evidence=[_evidence("ev-1")], decisions=[_decision()])
        result = validate_asset_utilization(pkt)
        assert not result.valid
        assert any("gate_decision" in e and "required" in e for e in result.errors)

    def test_promotion_state_adopted_without_gate_decision_fails(self):
        """promotion_state=adopted with empty gate_decision must fail."""
        au = _asset(promotion_state="adopted", gate_decision="")
        pkt = _packet(asset_utilization=[au], artifacts=[_artifact("art-out")],
                      evidence=[_evidence("ev-1")], decisions=[_decision()])
        result = validate_asset_utilization(pkt)
        assert not result.valid
        assert any("gate_decision" in e and "required" in e for e in result.errors)

    def test_gate_decision_missing_fails(self):
        au = _asset(gate_decision="dec-missing")
        pkt = _packet(asset_utilization=[au], artifacts=[_artifact("art-out")],
                      evidence=[_evidence("ev-1")], decisions=[_decision()])
        result = validate_asset_utilization(pkt)
        assert not result.valid
        assert any("dec-missing" in e for e in result.errors)

    def test_gate_decision_target_ref_must_match(self):
        au = _asset(gate_decision="dec-1")
        pkt = _packet(asset_utilization=[au], artifacts=[_artifact("art-out")],
                      evidence=[_evidence("ev-1")],
                      decisions=[_decision("dec-1", target_ref="au-other")])
        result = validate_asset_utilization(pkt)
        assert not result.valid
        assert any("target_ref" in e for e in result.errors)

    def test_gate_decision_must_be_gate_kind(self):
        au = _asset(gate_decision="dec-1")
        pkt = _packet(asset_utilization=[au], artifacts=[_artifact("art-out")],
                      evidence=[_evidence("ev-1")],
                      decisions=[_decision("dec-1", kind="review", target_ref="au-1")])
        result = validate_asset_utilization(pkt)
        assert not result.valid
        assert any("kind" in e and "gate" in e for e in result.errors)

    def test_gate_decision_must_have_pass_outcome(self):
        au = _asset(gate_decision="dec-1")
        pkt = _packet(asset_utilization=[au], artifacts=[_artifact("art-out")],
                      evidence=[_evidence("ev-1")],
                      decisions=[_decision("dec-1", outcome="fail", target_ref="au-1")])
        result = validate_asset_utilization(pkt)
        assert not result.valid
        assert any("outcome" in e for e in result.errors)

    def test_gate_decision_must_be_evidence_backed(self):
        """gate decision must have non-empty evidence_ids that resolve + support."""
        au = _asset(gate_decision="dec-1")
        dec = _decision("dec-1", target_ref="au-1")
        dec["evidence_ids"] = []  # no evidence backing
        pkt = _packet(asset_utilization=[au], artifacts=[_artifact("art-out")],
                      evidence=[_evidence("ev-1")], decisions=[dec])
        result = validate_asset_utilization(pkt)
        assert not result.valid
        assert any("evidence_ids" in e for e in result.errors)

    def test_gate_decision_evidence_must_resolve(self):
        au = _asset(gate_decision="dec-1")
        dec = _decision("dec-1", target_ref="au-1")
        dec["evidence_ids"] = ["ev-missing"]
        pkt = _packet(asset_utilization=[au], artifacts=[_artifact("art-out")],
                      evidence=[_evidence("ev-1")], decisions=[dec])
        result = validate_asset_utilization(pkt)
        assert not result.valid
        assert any("ev-missing" in e for e in result.errors)

    def test_gate_decision_evidence_must_cover_record_evidence(self):
        """gate decision evidence_ids must cover (superset of) record evidence_ids."""
        au = _asset(evidence_ids=["ev-1", "ev-2"], gate_decision="dec-1")
        dec = _decision("dec-1", target_ref="au-1")
        dec["evidence_ids"] = ["ev-1"]  # missing ev-2
        pkt = _packet(asset_utilization=[au], artifacts=[_artifact("art-out")],
                      evidence=[_evidence("ev-1"), _evidence("ev-2", source_artifact_id="art-out")],
                      decisions=[dec])
        result = validate_asset_utilization(pkt)
        assert not result.valid
        assert any("cover" in e or "cited" in e for e in result.errors)

    def test_required_scalar_fields(self):
        au = {
            "id": "", "project_id": "", "asset_id": "", "asset_type": "",
            "source_tier": "", "selected_for_work_type": "", "selection_reason": "",
            "produced_artifact": "", "evidence_ids": [], "gate_decision": "",
            "last_used_at": "", "promotion_state": "",
        }
        pkt = _packet(asset_utilization=[au])
        result = validate_asset_utilization(pkt)
        assert not result.valid
        # multiple required field errors
        assert len(result.errors) >= 8

    def test_promotion_state_only_adopted_when_gate_passes(self):
        """promotion_state=adopted requires gate decision with outcome=pass."""
        au = _asset(promotion_state="adopted", gate_decision="dec-1")
        pkt = _packet(asset_utilization=[au], artifacts=[_artifact("art-out")],
                      evidence=[_evidence("ev-1")],
                      decisions=[_decision("dec-1", outcome="fail", target_ref="au-1")])
        result = validate_asset_utilization(pkt)
        assert not result.valid
        assert any("promotion_state" in e or "adopted" in e for e in result.errors)

    def test_promotion_state_pending_allowed_without_pass(self):
        """promotion_state=pending is allowed even if gate hasn't passed."""
        au = _asset(promotion_state="pending", gate_decision="dec-1")
        dec = _decision("dec-1", target_ref="au-1")
        dec["evidence_ids"] = ["ev-1"]
        pkt = _packet(asset_utilization=[au], artifacts=[_artifact("art-out")],
                      evidence=[_evidence("ev-1")], decisions=[dec])
        result = validate_asset_utilization(pkt)
        assert result.valid, "\n".join(result.errors)

    def test_multiple_errors_accumulated(self):
        au = _asset(produced_artifact="art-missing", evidence_ids=["ev-missing"],
                    gate_decision="dec-missing")
        pkt = _packet(asset_utilization=[au], artifacts=[_artifact("art-out")],
                      evidence=[_evidence("ev-1")], decisions=[_decision()])
        result = validate_asset_utilization(pkt)
        assert not result.valid
        assert len(result.errors) >= 3


# ---------------------------------------------------------------------------
# derive_asset_utilization
# ---------------------------------------------------------------------------

class TestDeriveAssetUtilization:
    def test_empty_packet(self):
        result = derive_asset_utilization(_packet())
        assert result["asset_utilization_count"] == 0
        assert result["adopted_count"] == 0
        assert result["by_asset_type"] == {}

    def test_counts_total_and_adopted(self):
        au1 = _asset(au_id="au-1", promotion_state="adopted", gate_decision="dec-1")
        au2 = _asset(au_id="au-2", promotion_state="pending", gate_decision="dec-2")
        dec1 = _decision("dec-1", target_ref="au-1")
        dec1["evidence_ids"] = ["ev-1"]
        dec2 = _decision("dec-2", target_ref="au-2")
        dec2["evidence_ids"] = ["ev-1"]
        pkt = _packet(asset_utilization=[au1, au2], artifacts=[_artifact("art-out")],
                      evidence=[_evidence("ev-1")], decisions=[dec1, dec2])
        result = derive_asset_utilization(pkt)
        assert result["asset_utilization_count"] == 2
        assert result["adopted_count"] == 1

    def test_does_not_invent_adoption_without_gate_pass(self):
        """projection must not count adoption when gate decision fails."""
        au = _asset(au_id="au-1", promotion_state="adopted", gate_decision="dec-1")
        dec = _decision("dec-1", outcome="fail", target_ref="au-1")
        dec["evidence_ids"] = ["ev-1"]
        pkt = _packet(asset_utilization=[au], artifacts=[_artifact("art-out")],
                      evidence=[_evidence("ev-1")], decisions=[dec])
        result = derive_asset_utilization(pkt)
        assert result["adopted_count"] == 0

    def test_does_not_invent_adoption_without_evidence_backing(self):
        au = _asset(au_id="au-1", promotion_state="adopted", gate_decision="dec-1")
        dec = _decision("dec-1", target_ref="au-1")
        dec["evidence_ids"] = []  # no evidence backing
        pkt = _packet(asset_utilization=[au], artifacts=[_artifact("art-out")],
                      evidence=[_evidence("ev-1")], decisions=[dec])
        result = derive_asset_utilization(pkt)
        assert result["adopted_count"] == 0

    def test_does_not_count_adoption_when_produced_artifact_missing(self):
        au = _asset(au_id="au-1", produced_artifact="art-missing",
                    promotion_state="adopted", gate_decision="dec-1")
        dec = _decision("dec-1", target_ref="au-1")
        dec["evidence_ids"] = ["ev-1"]
        pkt = _packet(asset_utilization=[au], artifacts=[_artifact("art-out")],
                      evidence=[_evidence("ev-1")], decisions=[dec])
        result = derive_asset_utilization(pkt)
        assert result["adopted_count"] == 0

    def test_does_not_count_adoption_when_required_scalar_missing(self):
        au = _asset(au_id="", promotion_state="adopted", gate_decision="dec-1")
        dec = _decision("dec-1", target_ref="au-1")
        dec["evidence_ids"] = ["ev-1"]
        pkt = _packet(asset_utilization=[au], artifacts=[_artifact("art-out")],
                      evidence=[_evidence("ev-1")], decisions=[dec])
        result = derive_asset_utilization(pkt)
        assert result["adopted_count"] == 0

    def test_does_not_count_whitespace_required_id_as_utilized_or_adopted(self):
        au = _asset(asset_id="   ", promotion_state="adopted", gate_decision="dec-1")
        dec = _decision("dec-1", target_ref="au-1")
        dec["evidence_ids"] = ["ev-1"]
        pkt = _packet(asset_utilization=[au], artifacts=[_artifact("art-out")],
                      evidence=[_evidence("ev-1")], decisions=[dec])
        result = derive_asset_utilization(pkt)
        assert result["asset_utilization_count"] == 0
        assert result["adopted_count"] == 0
        assert result["by_asset_type"] == {}

    def test_groups_by_asset_type(self):
        au1 = _asset(au_id="au-1", asset_type="skill", gate_decision="dec-1")
        au2 = _asset(au_id="au-2", asset_type="skill", gate_decision="dec-2")
        au3 = _asset(au_id="au-3", asset_type="mcp_tool", gate_decision="dec-3")
        dec1 = _decision("dec-1", target_ref="au-1"); dec1["evidence_ids"] = ["ev-1"]
        dec2 = _decision("dec-2", target_ref="au-2"); dec2["evidence_ids"] = ["ev-1"]
        dec3 = _decision("dec-3", target_ref="au-3"); dec3["evidence_ids"] = ["ev-1"]
        pkt = _packet(asset_utilization=[au1, au2, au3], artifacts=[_artifact("art-out")],
                      evidence=[_evidence("ev-1")], decisions=[dec1, dec2, dec3])
        result = derive_asset_utilization(pkt)
        assert result["by_asset_type"]["skill"]["count"] == 2
        assert result["by_asset_type"]["mcp_tool"]["count"] == 1

    def test_projection_is_read_only(self):
        au = _asset(gate_decision="dec-1")
        dec = _decision("dec-1", target_ref="au-1"); dec["evidence_ids"] = ["ev-1"]
        pkt = _packet(asset_utilization=[au], artifacts=[_artifact("art-out")],
                      evidence=[_evidence("ev-1")], decisions=[dec])
        original = {"asset_utilization": list(pkt["asset_utilization"])}
        derive_asset_utilization(pkt)
        assert pkt["asset_utilization"] == original["asset_utilization"]
