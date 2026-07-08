"""Tests for Phase 5: continuation boundary validator.

A `continuation` decision authorizes the system to proceed from one work
phase to the next. It is NOT a persistent supervisor — each continuation is
a one-shot gate decision under declared scope, policy, evidence, and context
boundaries.

Plan (document-driven-transformation-final-plan-20260705.md:224-231):
"After gates work, introduce higher-power continuation only as explicit gate
decisions under declared scope, policy, evidence, and context boundaries.
Goal-bound continuation is not a persistent supervisor."

A continuation decision is valid only when:
  - kind="continue"
  - outcome="pass"
  - scope is declared (non-empty, with from/to boundaries)
  - policy_ref resolves to a declared policy artifact
  - it is evidence-backed (evidence_ids non-empty + resolve + support +
    source_artifact resolves)
  - it cites the prior gate decision (prior_gate_ref) that passed the
    preceding phase
  - the prior gate decision resolves, kind="gate", outcome="pass"
  - it is NOT a persistent supervisor: max_iterations must be declared
    and > 0 (finite), no persistent_supervisor flag
"""
from __future__ import annotations

import pytest

from control_plane.continuation_validator import (
    ValidationResult,
    validate_continuation,
    derive_continuation,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _continuation(cid="cont-1", scope_from="phase-4", scope_to="phase-5",
                  policy_ref="pol-1", evidence_ids=None, prior_gate_ref="gate-4",
                  max_iterations=1, project_id="proj-1", decided_at="2026-07-06T12:00:00Z",
                  decider_principal_id="principal-1", rationale="phase 4 passed"):
    return {
        "id": cid,
        "kind": "continue",
        "project_id": project_id,
        "scope_from": scope_from,
        "scope_to": scope_to,
        "policy_ref": policy_ref,
        "evidence_ids": evidence_ids if evidence_ids is not None else ["ev-1"],
        "prior_gate_ref": prior_gate_ref,
        "max_iterations": max_iterations,
        "decided_at": decided_at,
        "decider_principal_id": decider_principal_id,
        "outcome": "pass",
        "rationale": rationale,
    }


def _packet(continuation=None, artifacts=None, evidence=None, decisions=None):
    return {
        "continuation": continuation or [],
        "artifacts": artifacts or [],
        "evidence": evidence or [],
        "decisions": decisions or [],
    }


def _artifact(aid="art-out", kind="run_output"):
    return {"id": aid, "kind": kind}


def _policy_artifact(polid="pol-1", kind="policy_document"):
    return {"id": polid, "kind": kind}


def _evidence(eid="ev-1", supports="supports", source_artifact_id="art-out"):
    return {"id": eid, "supports": supports, "source_artifact_id": source_artifact_id,
            "claim": "claim", "scope": "scope", "freshness": "fresh",
            "observed_result": "result", "project_id": "proj-1"}


def _decision(did="gate-4", kind="gate", outcome="pass", target_ref="phase-4"):
    return {"id": did, "project_id": "proj-1", "kind": kind, "target_ref": target_ref,
            "decider_principal_id": "principal-1", "outcome": outcome,
            "evidence_ids": ["ev-1"], "rationale": "ok"}


def _whitespace_only_authority_packet():
    blank = "   "
    cont = _continuation(
        cid=blank,
        project_id=blank,
        scope_from=blank,
        scope_to=blank,
        policy_ref=blank,
        evidence_ids=[blank],
        prior_gate_ref=blank,
        decider_principal_id=blank,
    )
    gate = _decision(blank, kind="gate", outcome="pass", target_ref=blank)
    gate["project_id"] = blank
    gate["evidence_ids"] = [blank]
    return _packet(
        continuation=[cont],
        artifacts=[_artifact(blank), _policy_artifact(blank)],
        evidence=[_evidence(blank, source_artifact_id=blank)],
        decisions=[gate],
    )


# ---------------------------------------------------------------------------
# validate_continuation
# ---------------------------------------------------------------------------

class TestValidateContinuation:
    def test_empty_passes(self):
        result = validate_continuation(_packet())
        assert result.valid

    def test_full_valid_record_passes(self):
        cont = _continuation()
        gate = _decision("gate-4", kind="gate", outcome="pass")
        gate["evidence_ids"] = ["ev-1"]
        pkt = _packet(continuation=[cont],
                      artifacts=[_artifact("art-out"), _policy_artifact("pol-1")],
                      evidence=[_evidence("ev-1")],
                      decisions=[gate])
        result = validate_continuation(pkt)
        assert result.valid, "\n".join(result.errors)

    def test_kind_must_be_continue(self):
        cont = _continuation()
        cont["kind"] = "review"
        pkt = _packet(continuation=[cont],
                      artifacts=[_artifact("art-out"), _policy_artifact("pol-1")],
                      evidence=[_evidence("ev-1")],
                      decisions=[_decision("gate-4", kind="gate", outcome="pass")])
        result = validate_continuation(pkt)
        assert not result.valid
        assert any("kind" in e and "continue" in e for e in result.errors)

    def test_outcome_must_be_pass(self):
        cont = _continuation()
        cont["outcome"] = "fail"
        pkt = _packet(continuation=[cont],
                      artifacts=[_artifact("art-out"), _policy_artifact("pol-1")],
                      evidence=[_evidence("ev-1")],
                      decisions=[_decision("gate-4", kind="gate", outcome="pass")])
        result = validate_continuation(pkt)
        assert not result.valid
        assert any("outcome" in e for e in result.errors)

    def test_scope_from_required(self):
        cont = _continuation(scope_from="")
        pkt = _packet(continuation=[cont],
                      artifacts=[_artifact("art-out"), _policy_artifact("pol-1")],
                      evidence=[_evidence("ev-1")],
                      decisions=[_decision("gate-4", kind="gate", outcome="pass")])
        result = validate_continuation(pkt)
        assert not result.valid
        assert any("scope_from" in e for e in result.errors)

    def test_scope_to_required(self):
        cont = _continuation(scope_to="")
        pkt = _packet(continuation=[cont],
                      artifacts=[_artifact("art-out"), _policy_artifact("pol-1")],
                      evidence=[_evidence("ev-1")],
                      decisions=[_decision("gate-4", kind="gate", outcome="pass")])
        result = validate_continuation(pkt)
        assert not result.valid
        assert any("scope_to" in e for e in result.errors)

    def test_policy_ref_must_resolve(self):
        cont = _continuation(policy_ref="pol-missing")
        pkt = _packet(continuation=[cont],
                      artifacts=[_artifact("art-out"), _policy_artifact("pol-1")],
                      evidence=[_evidence("ev-1")],
                      decisions=[_decision("gate-4", kind="gate", outcome="pass")])
        result = validate_continuation(pkt)
        assert not result.valid
        assert any("policy_ref" in e and "pol-missing" in e for e in result.errors)

    def test_policy_ref_required(self):
        cont = _continuation(policy_ref="")
        pkt = _packet(continuation=[cont],
                      artifacts=[_artifact("art-out"), _policy_artifact("pol-1")],
                      evidence=[_evidence("ev-1")],
                      decisions=[_decision("gate-4", kind="gate", outcome="pass")])
        result = validate_continuation(pkt)
        assert not result.valid
        assert any("policy_ref" in e for e in result.errors)

    def test_evidence_backing_required(self):
        cont = _continuation(evidence_ids=[])
        pkt = _packet(continuation=[cont],
                      artifacts=[_artifact("art-out"), _policy_artifact("pol-1")],
                      evidence=[_evidence("ev-1")],
                      decisions=[_decision("gate-4", kind="gate", outcome="pass")])
        result = validate_continuation(pkt)
        assert not result.valid
        assert any("evidence_ids" in e for e in result.errors)

    def test_evidence_must_resolve(self):
        cont = _continuation(evidence_ids=["ev-missing"])
        pkt = _packet(continuation=[cont],
                      artifacts=[_artifact("art-out"), _policy_artifact("pol-1")],
                      evidence=[_evidence("ev-1")],
                      decisions=[_decision("gate-4", kind="gate", outcome="pass")])
        result = validate_continuation(pkt)
        assert not result.valid
        assert any("ev-missing" in e for e in result.errors)

    def test_evidence_must_support(self):
        cont = _continuation(evidence_ids=["ev-1"])
        pkt = _packet(continuation=[cont],
                      artifacts=[_artifact("art-out"), _policy_artifact("pol-1")],
                      evidence=[_evidence("ev-1", supports="rejects")],
                      decisions=[_decision("gate-4", kind="gate", outcome="pass")])
        result = validate_continuation(pkt)
        assert not result.valid
        assert any("supports" in e for e in result.errors)

    def test_evidence_source_artifact_must_resolve(self):
        cont = _continuation(evidence_ids=["ev-1"])
        pkt = _packet(continuation=[cont],
                      artifacts=[_artifact("art-out"), _policy_artifact("pol-1")],
                      evidence=[_evidence("ev-1", source_artifact_id="art-orphan")],
                      decisions=[_decision("gate-4", kind="gate", outcome="pass")])
        result = validate_continuation(pkt)
        assert not result.valid
        assert any("source_artifact_id" in e for e in result.errors)

    def test_prior_gate_ref_must_resolve(self):
        cont = _continuation(prior_gate_ref="gate-missing")
        pkt = _packet(continuation=[cont],
                      artifacts=[_artifact("art-out"), _policy_artifact("pol-1")],
                      evidence=[_evidence("ev-1")],
                      decisions=[_decision("gate-4", kind="gate", outcome="pass")])
        result = validate_continuation(pkt)
        assert not result.valid
        assert any("prior_gate_ref" in e and "gate-missing" in e for e in result.errors)

    def test_prior_gate_must_be_gate_kind(self):
        cont = _continuation(prior_gate_ref="gate-4")
        pkt = _packet(continuation=[cont],
                      artifacts=[_artifact("art-out"), _policy_artifact("pol-1")],
                      evidence=[_evidence("ev-1")],
                      decisions=[_decision("gate-4", kind="review", outcome="pass")])
        result = validate_continuation(pkt)
        assert not result.valid
        assert any("prior gate" in e for e in result.errors)

    def test_prior_gate_must_have_pass_outcome(self):
        cont = _continuation(prior_gate_ref="gate-4")
        pkt = _packet(continuation=[cont],
                      artifacts=[_artifact("art-out"), _policy_artifact("pol-1")],
                      evidence=[_evidence("ev-1")],
                      decisions=[_decision("gate-4", kind="gate", outcome="fail")])
        result = validate_continuation(pkt)
        assert not result.valid
        assert any("prior gate" in e for e in result.errors)

    def test_max_iterations_required_positive(self):
        cont = _continuation(max_iterations=0)
        pkt = _packet(continuation=[cont],
                      artifacts=[_artifact("art-out"), _policy_artifact("pol-1")],
                      evidence=[_evidence("ev-1")],
                      decisions=[_decision("gate-4", kind="gate", outcome="pass")])
        result = validate_continuation(pkt)
        assert not result.valid
        assert any("max_iterations" in e for e in result.errors)

    def test_persistent_supervisor_rejected(self):
        """A continuation with max_iterations=-1 (persistent) is rejected."""
        cont = _continuation(max_iterations=-1)
        pkt = _packet(continuation=[cont],
                      artifacts=[_artifact("art-out"), _policy_artifact("pol-1")],
                      evidence=[_evidence("ev-1")],
                      decisions=[_decision("gate-4", kind="gate", outcome="pass")])
        result = validate_continuation(pkt)
        assert not result.valid
        assert any("persistent" in e for e in result.errors)

    def test_prior_gate_must_be_evidence_backed(self):
        cont = _continuation(prior_gate_ref="gate-4")
        gate = _decision("gate-4", kind="gate", outcome="pass")
        gate["evidence_ids"] = []
        pkt = _packet(continuation=[cont],
                      artifacts=[_artifact("art-out"), _policy_artifact("pol-1")],
                      evidence=[_evidence("ev-1")],
                      decisions=[gate])
        result = validate_continuation(pkt)
        assert not result.valid
        assert any("prior gate" in e for e in result.errors)

    def test_prior_gate_evidence_ids_must_resolve(self):
        """Prior gate's evidence_ids must each resolve to declared evidence."""
        cont = _continuation(prior_gate_ref="gate-4")
        gate = _decision("gate-4", kind="gate", outcome="pass")
        gate["evidence_ids"] = ["ev-missing"]
        pkt = _packet(continuation=[cont],
                      artifacts=[_artifact("art-out"), _policy_artifact("pol-1")],
                      evidence=[_evidence("ev-1")],
                      decisions=[gate])
        result = validate_continuation(pkt)
        assert not result.valid
        assert any("ev-missing" in e for e in result.errors)

    def test_prior_gate_evidence_must_support(self):
        """Prior gate's evidence must have supports='supports'."""
        cont = _continuation(prior_gate_ref="gate-4")
        gate = _decision("gate-4", kind="gate", outcome="pass")
        gate["evidence_ids"] = ["ev-1"]
        pkt = _packet(continuation=[cont],
                      artifacts=[_artifact("art-out"), _policy_artifact("pol-1")],
                      evidence=[_evidence("ev-1", supports="rejects")],
                      decisions=[gate])
        result = validate_continuation(pkt)
        assert not result.valid
        assert any("supports" in e for e in result.errors)

    def test_prior_gate_evidence_source_artifact_must_resolve(self):
        """Prior gate's evidence source_artifact_id must resolve to declared artifact."""
        cont = _continuation(prior_gate_ref="gate-4")
        gate = _decision("gate-4", kind="gate", outcome="pass")
        gate["evidence_ids"] = ["ev-1"]
        pkt = _packet(continuation=[cont],
                      artifacts=[_artifact("art-out"), _policy_artifact("pol-1")],
                      evidence=[_evidence("ev-1", source_artifact_id="art-orphan")],
                      decisions=[gate])
        result = validate_continuation(pkt)
        assert not result.valid
        assert any("source_artifact_id" in e for e in result.errors)

    def test_max_iterations_must_be_integer(self):
        """max_iterations=0.5 (float) is rejected — must be integer."""
        cont = _continuation(max_iterations=0.5)
        pkt = _packet(continuation=[cont],
                      artifacts=[_artifact("art-out"), _policy_artifact("pol-1")],
                      evidence=[_evidence("ev-1")],
                      decisions=[_decision("gate-4", kind="gate", outcome="pass")])
        result = validate_continuation(pkt)
        assert not result.valid
        assert any("max_iterations" in e for e in result.errors)

    def test_max_iterations_bool_rejected(self):
        """max_iterations=True (bool) is rejected — must be integer, not bool."""
        cont = _continuation(max_iterations=True)
        pkt = _packet(continuation=[cont],
                      artifacts=[_artifact("art-out"), _policy_artifact("pol-1")],
                      evidence=[_evidence("ev-1")],
                      decisions=[_decision("gate-4", kind="gate", outcome="pass")])
        result = validate_continuation(pkt)
        assert not result.valid
        assert any("max_iterations" in e for e in result.errors)

    def test_multiple_errors_accumulated(self):
        cont = _continuation(scope_from="", policy_ref="", evidence_ids=[],
                           prior_gate_ref="", max_iterations=0)
        pkt = _packet(continuation=[cont],
                      artifacts=[_artifact("art-out"), _policy_artifact("pol-1")],
                      evidence=[_evidence("ev-1")],
                      decisions=[_decision("gate-4", kind="gate", outcome="pass")])
        result = validate_continuation(pkt)
        assert not result.valid
        assert len(result.errors) >= 4

    def test_whitespace_only_required_ids_and_refs_rejected(self):
        pkt = _whitespace_only_authority_packet()
        result = validate_continuation(pkt)
        assert not result.valid
        assert any("id is required" in e for e in result.errors)
        assert any("policy_ref is required" in e for e in result.errors)
        assert any("prior_gate_ref is required" in e for e in result.errors)


# ---------------------------------------------------------------------------
# derive_continuation
# ---------------------------------------------------------------------------

class TestDeriveContinuation:
    def test_empty_packet(self):
        result = derive_continuation(_packet())
        assert result["continuation_count"] == 0
        assert result["active_count"] == 0
        assert result["by_scope"] == {}

    def test_counts_active_continuations(self):
        cont1 = _continuation(cid="cont-1", scope_to="phase-5")
        cont2 = _continuation(cid="cont-2", scope_to="phase-6",
                            prior_gate_ref="gate-5")
        gate1 = _decision("gate-4", kind="gate", outcome="pass")
        gate1["evidence_ids"] = ["ev-1"]
        gate2 = _decision("gate-5", kind="gate", outcome="pass")
        gate2["evidence_ids"] = ["ev-1"]
        pkt = _packet(continuation=[cont1, cont2],
                      artifacts=[_artifact("art-out"), _policy_artifact("pol-1")],
                      evidence=[_evidence("ev-1")],
                      decisions=[gate1, gate2])
        result = derive_continuation(pkt)
        assert result["continuation_count"] == 2
        assert result["active_count"] == 2

    def test_does_not_count_without_evidence_backing(self):
        cont = _continuation(evidence_ids=[])
        pkt = _packet(continuation=[cont],
                      artifacts=[_artifact("art-out"), _policy_artifact("pol-1")],
                      evidence=[_evidence("ev-1")],
                      decisions=[_decision("gate-4", kind="gate", outcome="pass")])
        result = derive_continuation(pkt)
        assert result["active_count"] == 0

    def test_does_not_count_when_prior_gate_not_pass(self):
        cont = _continuation(prior_gate_ref="gate-4")
        pkt = _packet(continuation=[cont],
                      artifacts=[_artifact("art-out"), _policy_artifact("pol-1")],
                      evidence=[_evidence("ev-1")],
                      decisions=[_decision("gate-4", kind="gate", outcome="fail")])
        result = derive_continuation(pkt)
        assert result["active_count"] == 0

    def test_does_not_count_persistent_supervisor(self):
        cont = _continuation(max_iterations=-1)
        pkt = _packet(continuation=[cont],
                      artifacts=[_artifact("art-out"), _policy_artifact("pol-1")],
                      evidence=[_evidence("ev-1")],
                      decisions=[_decision("gate-4", kind="gate", outcome="pass")])
        result = derive_continuation(pkt)
        assert result["active_count"] == 0

    def test_does_not_count_when_policy_missing(self):
        cont = _continuation(policy_ref="pol-missing")
        pkt = _packet(continuation=[cont],
                      artifacts=[_artifact("art-out"), _policy_artifact("pol-1")],
                      evidence=[_evidence("ev-1")],
                      decisions=[_decision("gate-4", kind="gate", outcome="pass")])
        result = derive_continuation(pkt)
        assert result["active_count"] == 0

    def test_groups_by_scope(self):
        cont1 = _continuation(cid="cont-1", scope_to="phase-5")
        cont2 = _continuation(cid="cont-2", scope_to="phase-5")
        cont3 = _continuation(cid="cont-3", scope_to="phase-6",
                            prior_gate_ref="gate-5")
        gate1 = _decision("gate-4", kind="gate", outcome="pass"); gate1["evidence_ids"] = ["ev-1"]
        gate2 = _decision("gate-5", kind="gate", outcome="pass"); gate2["evidence_ids"] = ["ev-1"]
        pkt = _packet(continuation=[cont1, cont2, cont3],
                      artifacts=[_artifact("art-out"), _policy_artifact("pol-1")],
                      evidence=[_evidence("ev-1")],
                      decisions=[gate1, gate2])
        result = derive_continuation(pkt)
        assert result["by_scope"]["phase-5"]["count"] == 2
        assert result["by_scope"]["phase-6"]["count"] == 1

    def test_projection_is_read_only(self):
        cont = _continuation()
        gate = _decision("gate-4", kind="gate", outcome="pass")
        gate["evidence_ids"] = ["ev-1"]
        pkt = _packet(continuation=[cont],
                      artifacts=[_artifact("art-out"), _policy_artifact("pol-1")],
                      evidence=[_evidence("ev-1")],
                      decisions=[gate])
        original = {"continuation": list(pkt["continuation"])}
        derive_continuation(pkt)
        assert pkt["continuation"] == original["continuation"]

    def test_does_not_count_prior_gate_with_unresolved_evidence(self):
        """Projection must not count continuation whose prior gate has
        evidence that doesn't resolve."""
        cont = _continuation(prior_gate_ref="gate-4")
        gate = _decision("gate-4", kind="gate", outcome="pass")
        gate["evidence_ids"] = ["ev-missing"]
        pkt = _packet(continuation=[cont],
                      artifacts=[_artifact("art-out"), _policy_artifact("pol-1")],
                      evidence=[_evidence("ev-1")],
                      decisions=[gate])
        result = derive_continuation(pkt)
        assert result["active_count"] == 0

    def test_does_not_count_prior_gate_with_rejecting_evidence(self):
        """Projection must not count continuation whose prior gate evidence
        does not support."""
        cont = _continuation(prior_gate_ref="gate-4")
        gate = _decision("gate-4", kind="gate", outcome="pass")
        gate["evidence_ids"] = ["ev-1"]
        pkt = _packet(continuation=[cont],
                      artifacts=[_artifact("art-out"), _policy_artifact("pol-1")],
                      evidence=[_evidence("ev-1", supports="rejects")],
                      decisions=[gate])
        result = derive_continuation(pkt)
        assert result["active_count"] == 0

    def test_does_not_count_prior_gate_with_orphan_source_artifact(self):
        """Projection must not count continuation whose prior gate evidence
        source_artifact does not resolve."""
        cont = _continuation(prior_gate_ref="gate-4")
        gate = _decision("gate-4", kind="gate", outcome="pass")
        gate["evidence_ids"] = ["ev-1"]
        pkt = _packet(continuation=[cont],
                      artifacts=[_artifact("art-out"), _policy_artifact("pol-1")],
                      evidence=[_evidence("ev-1", source_artifact_id="art-orphan")],
                      decisions=[gate])
        result = derive_continuation(pkt)
        assert result["active_count"] == 0

    def test_does_not_count_float_max_iterations(self):
        """Projection must not count continuation with max_iterations=0.5."""
        cont = _continuation(max_iterations=0.5)
        pkt = _packet(continuation=[cont],
                      artifacts=[_artifact("art-out"), _policy_artifact("pol-1")],
                      evidence=[_evidence("ev-1")],
                      decisions=[_decision("gate-4", kind="gate", outcome="pass")])
        result = derive_continuation(pkt)
        assert result["active_count"] == 0

    def test_does_not_count_bool_max_iterations(self):
        """Projection must not count continuation with max_iterations=True."""
        cont = _continuation(max_iterations=True)
        pkt = _packet(continuation=[cont],
                      artifacts=[_artifact("art-out"), _policy_artifact("pol-1")],
                      evidence=[_evidence("ev-1")],
                      decisions=[_decision("gate-4", kind="gate", outcome="pass")])
        result = derive_continuation(pkt)
        assert result["active_count"] == 0

    def test_prior_gate_project_id_must_match_continuation(self):
        """P0: prior gate with different project_id is rejected."""
        cont = _continuation(prior_gate_ref="gate-4", scope_from="phase-4")
        gate = _decision("gate-4", kind="gate", outcome="pass")
        gate["project_id"] = "proj-2"
        gate["evidence_ids"] = ["ev-1"]
        pkt = _packet(continuation=[cont],
                      artifacts=[_artifact("art-out"), _policy_artifact("pol-1")],
                      evidence=[_evidence("ev-1")],
                      decisions=[gate])
        result = validate_continuation(pkt)
        assert not result.valid
        assert any("project_id" in e and "proj-2" in e for e in result.errors)

    def test_prior_gate_target_ref_must_match_scope_from(self):
        """P0: prior gate with different target_ref is rejected."""
        cont = _continuation(prior_gate_ref="gate-4", scope_from="phase-4")
        gate = _decision("gate-4", kind="gate", outcome="pass", target_ref="unrelated-work")
        gate["evidence_ids"] = ["ev-1"]
        pkt = _packet(continuation=[cont],
                      artifacts=[_artifact("art-out"), _policy_artifact("pol-1")],
                      evidence=[_evidence("ev-1")],
                      decisions=[gate])
        result = validate_continuation(pkt)
        assert not result.valid
        assert any("target_ref" in e and "unrelated-work" in e for e in result.errors)

    def test_does_not_count_prior_gate_for_wrong_project(self):
        """Projection: cross-project gate does not authorize continuation."""
        cont = _continuation(prior_gate_ref="gate-4", scope_from="phase-4")
        gate = _decision("gate-4", kind="gate", outcome="pass")
        gate["project_id"] = "proj-2"
        gate["evidence_ids"] = ["ev-1"]
        pkt = _packet(continuation=[cont],
                      artifacts=[_artifact("art-out"), _policy_artifact("pol-1")],
                      evidence=[_evidence("ev-1")],
                      decisions=[gate])
        result = derive_continuation(pkt)
        assert result["active_count"] == 0

    def test_does_not_count_prior_gate_for_wrong_scope(self):
        """Projection: wrong-scope gate does not authorize continuation."""
        cont = _continuation(prior_gate_ref="gate-4", scope_from="phase-4")
        gate = _decision("gate-4", kind="gate", outcome="pass", target_ref="unrelated-work")
        gate["evidence_ids"] = ["ev-1"]
        pkt = _packet(continuation=[cont],
                      artifacts=[_artifact("art-out"), _policy_artifact("pol-1")],
                      evidence=[_evidence("ev-1")],
                      decisions=[gate])
        result = derive_continuation(pkt)
        assert result["active_count"] == 0

    def test_does_not_count_whitespace_only_required_ids_and_refs(self):
        pkt = _whitespace_only_authority_packet()
        result = derive_continuation(pkt)
        assert result["active_count"] == 0
        assert all(scope["active_count"] == 0 for scope in result["by_scope"].values())
