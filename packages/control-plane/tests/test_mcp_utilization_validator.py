"""Tests for Phase 4c: MCP offline utilization ledger validator.

An `mcp_utilization` record accounts for an MCP server/tool call so it can be
audited offline (no live dashboard required). It is NOT standalone authority;
it must point to:

  - session_id, tool_id, consent_id, result_artifact (MCP-specific scalars)
  - produced_artifact resolving to a declared artifact
  - evidence_ids non-empty + each resolves + supports + source_artifact resolves
  - gate_decision required, evidence-backed (kind="gate", outcome="pass",
    target_ref == record id, evidence coverage of record evidence_ids)

A record is only counted as `adopted` in projection when promotion_state=
"adopted" AND the full gate chain passes — same non-divergence contract as
Phase 4 skill_usage and Phase 4b asset_utilization.
"""
from __future__ import annotations

import pytest

from control_plane.mcp_utilization_validator import (
    ValidationResult,
    validate_mcp_utilization,
    derive_mcp_utilization,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mcp(mu_id="mcp-1", session_id="sess-1", tool_id="tool-fetch",
         consent_id="consent-1", result_artifact="art-result",
         produced_artifact="art-out", evidence_ids=None,
         gate_decision="dec-1", last_used_at="2026-07-06T10:00:00Z",
         promotion_state="adopted", project_id="proj-1",
         asset_id="mcp-fetch", asset_type="mcp_tool",
         source_tier="canonical", selected_for_work_type="phase-4c-mcp",
         selection_reason="route requires fetch"):
    return {
        "id": mu_id,
        "project_id": project_id,
        "session_id": session_id,
        "tool_id": tool_id,
        "consent_id": consent_id,
        "result_artifact": result_artifact,
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


def _packet(mcp_utilization=None, artifacts=None, evidence=None, decisions=None):
    return {
        "mcp_utilization": mcp_utilization or [],
        "artifacts": artifacts or [],
        "evidence": evidence or [],
        "decisions": decisions or [],
    }


def _artifact(aid="art-out", kind="run_output"):
    return {"id": aid, "kind": kind}


def _artifacts():
    """Both produced_artifact and result_artifact must resolve."""
    return [_artifact("art-out"), _artifact("art-result", kind="mcp_result")]


def _evidence(eid="ev-1", supports="supports", source_artifact_id="art-out"):
    return {"id": eid, "supports": supports, "source_artifact_id": source_artifact_id,
            "claim": "claim", "scope": "scope", "freshness": "fresh",
            "observed_result": "result", "project_id": "proj-1"}


def _decision(did="dec-1", kind="gate", outcome="pass", target_ref="mcp-1"):
    return {"id": did, "project_id": "proj-1", "kind": kind, "target_ref": target_ref,
            "decider_principal_id": "principal-1", "outcome": outcome,
            "evidence_ids": ["ev-1"], "rationale": "ok"}


# ---------------------------------------------------------------------------
# validate_mcp_utilization
# ---------------------------------------------------------------------------

class TestValidateMcpUtilization:
    def test_empty_passes(self):
        result = validate_mcp_utilization(_packet())
        assert result.valid

    def test_full_valid_record_passes(self):
        mu = _mcp()
        dec = _decision("dec-1", target_ref="mcp-1")
        dec["evidence_ids"] = ["ev-1"]
        pkt = _packet(mcp_utilization=[mu], artifacts=_artifacts(),
                      evidence=[_evidence("ev-1")], decisions=[dec])
        result = validate_mcp_utilization(pkt)
        assert result.valid, "\n".join(result.errors)

    def test_mcp_specific_scalars_required(self):
        """session_id, tool_id, consent_id, result_artifact are required."""
        au = _mcp(session_id="", tool_id="", consent_id="", result_artifact="")
        pkt = _packet(mcp_utilization=[au], artifacts=_artifacts(),
                      evidence=[_evidence("ev-1")], decisions=[_decision()])
        result = validate_mcp_utilization(pkt)
        assert not result.valid
        # 4 MCP-specific required fields
        errs = "\n".join(result.errors)
        for field_name in ("session_id", "tool_id", "consent_id", "result_artifact"):
            assert field_name in errs

    def test_whitespace_only_required_ids_and_refs_fail(self):
        mu = _mcp(
            mu_id="   ",
            session_id="   ",
            tool_id="   ",
            consent_id="   ",
            result_artifact="\t",
            produced_artifact="   ",
            evidence_ids=["\n"],
            gate_decision="\r",
        )
        dec = _decision("\r", target_ref="   ")
        dec["evidence_ids"] = ["\n"]
        pkt = _packet(
            mcp_utilization=[mu],
            artifacts=[_artifact("   "), _artifact("\t", kind="mcp_result")],
            evidence=[_evidence("\n", source_artifact_id="   ")],
            decisions=[dec],
        )
        result = validate_mcp_utilization(pkt)
        assert not result.valid
        errs = "\n".join(result.errors)
        for field_name in (
            "id",
            "session_id",
            "tool_id",
            "consent_id",
            "result_artifact",
            "produced_artifact",
            "gate_decision",
            "evidence_id",
        ):
            assert field_name in errs

    def test_result_artifact_must_resolve(self):
        mu = _mcp(result_artifact="art-missing-result")
        pkt = _packet(mcp_utilization=[mu], artifacts=_artifacts(),
                      evidence=[_evidence("ev-1")], decisions=[_decision()])
        result = validate_mcp_utilization(pkt)
        assert not result.valid
        assert any("result_artifact" in e and "resolve" in e for e in result.errors)

    def test_produced_artifact_must_resolve(self):
        mu = _mcp(produced_artifact="art-missing")
        pkt = _packet(mcp_utilization=[mu], artifacts=_artifacts(),
                      evidence=[_evidence("ev-1")], decisions=[_decision()])
        result = validate_mcp_utilization(pkt)
        assert not result.valid
        assert any("art-missing" in e for e in result.errors)

    def test_evidence_ids_required_non_empty(self):
        mu = _mcp(evidence_ids=[])
        pkt = _packet(mcp_utilization=[mu], artifacts=_artifacts(),
                      decisions=[_decision()])
        result = validate_mcp_utilization(pkt)
        assert not result.valid
        assert any("evidence_ids" in e for e in result.errors)

    def test_evidence_must_resolve(self):
        mu = _mcp(evidence_ids=["ev-missing"])
        pkt = _packet(mcp_utilization=[mu], artifacts=_artifacts(),
                      evidence=[_evidence("ev-1")], decisions=[_decision()])
        result = validate_mcp_utilization(pkt)
        assert not result.valid
        assert any("ev-missing" in e for e in result.errors)

    def test_evidence_must_support(self):
        mu = _mcp(evidence_ids=["ev-1"])
        pkt = _packet(mcp_utilization=[mu], artifacts=_artifacts(),
                      evidence=[_evidence("ev-1", supports="rejects")],
                      decisions=[_decision()])
        result = validate_mcp_utilization(pkt)
        assert not result.valid
        assert any("supports" in e for e in result.errors)

    def test_evidence_source_artifact_must_resolve(self):
        mu = _mcp(evidence_ids=["ev-1"])
        pkt = _packet(mcp_utilization=[mu], artifacts=_artifacts(),
                      evidence=[_evidence("ev-1", source_artifact_id="art-orphan")],
                      decisions=[_decision()])
        result = validate_mcp_utilization(pkt)
        assert not result.valid
        assert any("source_artifact_id" in e for e in result.errors)

    def test_result_artifact_must_be_distinct_from_produced_artifact(self):
        """result_artifact must be a distinct artifact from produced_artifact."""
        mu = _mcp(result_artifact="art-out", produced_artifact="art-out")
        pkt = _packet(mcp_utilization=[mu], artifacts=_artifacts(),
                      evidence=[_evidence("ev-1")], decisions=[_decision()])
        result = validate_mcp_utilization(pkt)
        assert not result.valid
        assert any("distinct" in e for e in result.errors)

    def test_gate_decision_required(self):
        mu = _mcp(gate_decision="")
        pkt = _packet(mcp_utilization=[mu], artifacts=_artifacts(),
                      evidence=[_evidence("ev-1")], decisions=[_decision()])
        result = validate_mcp_utilization(pkt)
        assert not result.valid
        assert any("gate_decision" in e and "required" in e for e in result.errors)

    def test_gate_decision_must_resolve(self):
        mu = _mcp(gate_decision="dec-missing")
        pkt = _packet(mcp_utilization=[mu], artifacts=_artifacts(),
                      evidence=[_evidence("ev-1")], decisions=[_decision()])
        result = validate_mcp_utilization(pkt)
        assert not result.valid
        assert any("dec-missing" in e for e in result.errors)

    def test_gate_decision_must_be_gate_kind(self):
        mu = _mcp(gate_decision="dec-1")
        pkt = _packet(mcp_utilization=[mu], artifacts=_artifacts(),
                      evidence=[_evidence("ev-1")],
                      decisions=[_decision("dec-1", kind="review", target_ref="mcp-1")])
        result = validate_mcp_utilization(pkt)
        assert not result.valid
        assert any("kind" in e and "gate" in e for e in result.errors)

    def test_gate_decision_must_have_pass_outcome(self):
        mu = _mcp(gate_decision="dec-1")
        pkt = _packet(mcp_utilization=[mu], artifacts=_artifacts(),
                      evidence=[_evidence("ev-1")],
                      decisions=[_decision("dec-1", outcome="fail", target_ref="mcp-1")])
        result = validate_mcp_utilization(pkt)
        assert not result.valid
        assert any("outcome" in e for e in result.errors)

    def test_gate_decision_target_ref_must_match(self):
        mu = _mcp(gate_decision="dec-1")
        pkt = _packet(mcp_utilization=[mu], artifacts=_artifacts(),
                      evidence=[_evidence("ev-1")],
                      decisions=[_decision("dec-1", target_ref="mcp-other")])
        result = validate_mcp_utilization(pkt)
        assert not result.valid
        assert any("target_ref" in e for e in result.errors)

    def test_gate_decision_must_be_evidence_backed(self):
        mu = _mcp(gate_decision="dec-1")
        dec = _decision("dec-1", target_ref="mcp-1")
        dec["evidence_ids"] = []
        pkt = _packet(mcp_utilization=[mu], artifacts=_artifacts(),
                      evidence=[_evidence("ev-1")], decisions=[dec])
        result = validate_mcp_utilization(pkt)
        assert not result.valid
        assert any("evidence_ids" in e for e in result.errors)

    def test_gate_decision_evidence_must_resolve(self):
        mu = _mcp(gate_decision="dec-1")
        dec = _decision("dec-1", target_ref="mcp-1")
        dec["evidence_ids"] = ["ev-missing"]
        pkt = _packet(mcp_utilization=[mu], artifacts=_artifacts(),
                      evidence=[_evidence("ev-1")], decisions=[dec])
        result = validate_mcp_utilization(pkt)
        assert not result.valid
        assert any("ev-missing" in e for e in result.errors)

    def test_gate_decision_evidence_must_cover_record_evidence(self):
        mu = _mcp(evidence_ids=["ev-1", "ev-2"], gate_decision="dec-1")
        dec = _decision("dec-1", target_ref="mcp-1")
        dec["evidence_ids"] = ["ev-1"]
        pkt = _packet(mcp_utilization=[mu], artifacts=_artifacts(),
                      evidence=[_evidence("ev-1"), _evidence("ev-2", source_artifact_id="art-out")],
                      decisions=[dec])
        result = validate_mcp_utilization(pkt)
        assert not result.valid
        assert any("cover" in e or "cited" in e for e in result.errors)

    def test_promotion_state_adopted_without_gate_decision_fails(self):
        mu = _mcp(promotion_state="adopted", gate_decision="")
        pkt = _packet(mcp_utilization=[mu], artifacts=_artifacts(),
                      evidence=[_evidence("ev-1")], decisions=[_decision()])
        result = validate_mcp_utilization(pkt)
        assert not result.valid
        assert any("gate_decision" in e and "required" in e for e in result.errors)

    def test_promotion_state_adopted_requires_gate_pass(self):
        mu = _mcp(promotion_state="adopted", gate_decision="dec-1")
        pkt = _packet(mcp_utilization=[mu], artifacts=_artifacts(),
                      evidence=[_evidence("ev-1")],
                      decisions=[_decision("dec-1", outcome="fail", target_ref="mcp-1")])
        result = validate_mcp_utilization(pkt)
        assert not result.valid
        assert any("promotion_state" in e or "adopted" in e for e in result.errors)

    def test_promotion_state_pending_allowed(self):
        mu = _mcp(promotion_state="pending", gate_decision="dec-1")
        dec = _decision("dec-1", target_ref="mcp-1")
        dec["evidence_ids"] = ["ev-1"]
        pkt = _packet(mcp_utilization=[mu], artifacts=_artifacts(),
                      evidence=[_evidence("ev-1")], decisions=[dec])
        result = validate_mcp_utilization(pkt)
        assert result.valid, "\n".join(result.errors)

    def test_multiple_errors_accumulated(self):
        mu = _mcp(session_id="", produced_artifact="art-missing",
                  evidence_ids=["ev-missing"], gate_decision="dec-missing")
        pkt = _packet(mcp_utilization=[mu], artifacts=_artifacts(),
                      evidence=[_evidence("ev-1")], decisions=[_decision()])
        result = validate_mcp_utilization(pkt)
        assert not result.valid
        assert len(result.errors) >= 4


# ---------------------------------------------------------------------------
# derive_mcp_utilization
# ---------------------------------------------------------------------------

class TestDeriveMcpUtilization:
    def test_empty_packet(self):
        result = derive_mcp_utilization(_packet())
        assert result["mcp_utilization_count"] == 0
        assert result["adopted_count"] == 0
        assert result["by_tool_id"] == {}

    def test_counts_total_and_adopted(self):
        mu1 = _mcp(mu_id="mcp-1", promotion_state="adopted", gate_decision="dec-1")
        mu2 = _mcp(mu_id="mcp-2", promotion_state="pending", gate_decision="dec-2")
        dec1 = _decision("dec-1", target_ref="mcp-1"); dec1["evidence_ids"] = ["ev-1"]
        dec2 = _decision("dec-2", target_ref="mcp-2"); dec2["evidence_ids"] = ["ev-1"]
        pkt = _packet(mcp_utilization=[mu1, mu2], artifacts=_artifacts(),
                      evidence=[_evidence("ev-1")], decisions=[dec1, dec2])
        result = derive_mcp_utilization(pkt)
        assert result["mcp_utilization_count"] == 2
        assert result["adopted_count"] == 1

    def test_does_not_invent_adoption_without_gate_pass(self):
        mu = _mcp(mu_id="mcp-1", promotion_state="adopted", gate_decision="dec-1")
        dec = _decision("dec-1", outcome="fail", target_ref="mcp-1")
        dec["evidence_ids"] = ["ev-1"]
        pkt = _packet(mcp_utilization=[mu], artifacts=_artifacts(),
                      evidence=[_evidence("ev-1")], decisions=[dec])
        result = derive_mcp_utilization(pkt)
        assert result["adopted_count"] == 0

    def test_does_not_invent_adoption_without_evidence_backing(self):
        mu = _mcp(mu_id="mcp-1", promotion_state="adopted", gate_decision="dec-1")
        dec = _decision("dec-1", target_ref="mcp-1")
        dec["evidence_ids"] = []
        pkt = _packet(mcp_utilization=[mu], artifacts=_artifacts(),
                      evidence=[_evidence("ev-1")], decisions=[dec])
        result = derive_mcp_utilization(pkt)
        assert result["adopted_count"] == 0

    def test_does_not_count_adoption_when_produced_artifact_missing(self):
        mu = _mcp(mu_id="mcp-1", produced_artifact="art-missing",
                  promotion_state="adopted", gate_decision="dec-1")
        dec = _decision("dec-1", target_ref="mcp-1")
        dec["evidence_ids"] = ["ev-1"]
        pkt = _packet(mcp_utilization=[mu], artifacts=_artifacts(),
                      evidence=[_evidence("ev-1")], decisions=[dec])
        result = derive_mcp_utilization(pkt)
        assert result["adopted_count"] == 0

    def test_does_not_count_adoption_when_result_artifact_missing(self):
        mu = _mcp(mu_id="mcp-1", result_artifact="art-missing-result",
                  promotion_state="adopted", gate_decision="dec-1")
        dec = _decision("dec-1", target_ref="mcp-1")
        dec["evidence_ids"] = ["ev-1"]
        pkt = _packet(mcp_utilization=[mu], artifacts=_artifacts(),
                      evidence=[_evidence("ev-1")], decisions=[dec])
        result = derive_mcp_utilization(pkt)
        assert result["adopted_count"] == 0

    def test_does_not_count_adoption_when_mcp_scalar_missing(self):
        mu = _mcp(mu_id="mcp-1", session_id="",
                  promotion_state="adopted", gate_decision="dec-1")
        dec = _decision("dec-1", target_ref="mcp-1")
        dec["evidence_ids"] = ["ev-1"]
        pkt = _packet(mcp_utilization=[mu], artifacts=_artifacts(),
                      evidence=[_evidence("ev-1")], decisions=[dec])
        result = derive_mcp_utilization(pkt)
        assert result["adopted_count"] == 0

    def test_does_not_count_whitespace_only_required_refs_as_utilized(self):
        mu = _mcp(
            mu_id="   ",
            session_id="   ",
            tool_id="   ",
            consent_id="   ",
            result_artifact="\t",
            produced_artifact="   ",
            evidence_ids=["\n"],
            gate_decision="\r",
            promotion_state="adopted",
        )
        dec = _decision("\r", target_ref="   ")
        dec["evidence_ids"] = ["\n"]
        pkt = _packet(
            mcp_utilization=[mu],
            artifacts=[_artifact("   "), _artifact("\t", kind="mcp_result")],
            evidence=[_evidence("\n", source_artifact_id="   ")],
            decisions=[dec],
        )
        result = derive_mcp_utilization(pkt)
        assert result["mcp_utilization_count"] == 0
        assert result["adopted_count"] == 0
        assert result["by_tool_id"] == {}

    def test_does_not_count_adoption_when_result_equals_produced(self):
        mu = _mcp(mu_id="mcp-1", result_artifact="art-out",
                  produced_artifact="art-out",
                  promotion_state="adopted", gate_decision="dec-1")
        dec = _decision("dec-1", target_ref="mcp-1")
        dec["evidence_ids"] = ["ev-1"]
        pkt = _packet(mcp_utilization=[mu], artifacts=_artifacts(),
                      evidence=[_evidence("ev-1")], decisions=[dec])
        result = derive_mcp_utilization(pkt)
        assert result["adopted_count"] == 0

    def test_groups_by_tool_id(self):
        mu1 = _mcp(mu_id="mcp-1", tool_id="tool-fetch", gate_decision="dec-1")
        mu2 = _mcp(mu_id="mcp-2", tool_id="tool-fetch", gate_decision="dec-2")
        mu3 = _mcp(mu_id="mcp-3", tool_id="tool-search", gate_decision="dec-3")
        dec1 = _decision("dec-1", target_ref="mcp-1"); dec1["evidence_ids"] = ["ev-1"]
        dec2 = _decision("dec-2", target_ref="mcp-2"); dec2["evidence_ids"] = ["ev-1"]
        dec3 = _decision("dec-3", target_ref="mcp-3"); dec3["evidence_ids"] = ["ev-1"]
        pkt = _packet(mcp_utilization=[mu1, mu2, mu3], artifacts=_artifacts(),
                      evidence=[_evidence("ev-1")], decisions=[dec1, dec2, dec3])
        result = derive_mcp_utilization(pkt)
        assert result["by_tool_id"]["tool-fetch"]["count"] == 2
        assert result["by_tool_id"]["tool-search"]["count"] == 1

    def test_projection_is_read_only(self):
        mu = _mcp(gate_decision="dec-1")
        dec = _decision("dec-1", target_ref="mcp-1"); dec["evidence_ids"] = ["ev-1"]
        pkt = _packet(mcp_utilization=[mu], artifacts=_artifacts(),
                      evidence=[_evidence("ev-1")], decisions=[dec])
        original = {"mcp_utilization": list(pkt["mcp_utilization"])}
        derive_mcp_utilization(pkt)
        assert pkt["mcp_utilization"] == original["mcp_utilization"]
