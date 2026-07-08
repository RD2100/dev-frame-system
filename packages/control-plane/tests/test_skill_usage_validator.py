"""Tests for Phase 4: skill_usage evidence validator.

skill_usage records must point to existing artifacts, evidence, and decisions.
They are not standalone authority — they only become accountable assets when
an evidence-backed decision adopts them.
"""
from __future__ import annotations

import pytest

from control_plane.skill_usage_validator import (
    ValidationResult,
    validate_skill_usage,
    derive_skill_utilization,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _skill_usage(su_id="su-1", skill_id="skill-tdd", produced_artifact_id="art-out",
                 cited_evidence_ids=None, adopted_by_decision_id=None,
                 project_id="proj-1", invoked_at="2026-07-06T10:00:00Z",
                 work_item_id="wi-1"):
    return {
        "id": su_id,
        "project_id": project_id,
        "skill_id": skill_id,
        "work_item_id": work_item_id,
        "invoked_at": invoked_at,
        "produced_artifact_id": produced_artifact_id,
        "cited_evidence_ids": cited_evidence_ids or [],
        "adopted_by_decision_id": adopted_by_decision_id,
    }


def _packet(skill_usage=None, artifacts=None, evidence=None, decisions=None):
    return {
        "skill_usage": skill_usage or [],
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


def _decision(did="dec-1", kind="adopt", outcome="pass", target_ref="su-1"):
    return {"id": did, "project_id": "proj-1", "kind": kind, "target_ref": target_ref,
            "decider_principal_id": "principal-1", "outcome": outcome,
            "evidence_ids": ["ev-1"], "rationale": "ok"}


# ---------------------------------------------------------------------------
# validate_skill_usage
# ---------------------------------------------------------------------------

class TestValidateSkillUsage:
    def test_empty_skill_usage_passes(self):
        result = validate_skill_usage(_packet())
        assert result.valid

    def test_skill_usage_with_resolved_artifact_and_evidence_passes(self):
        su = _skill_usage(cited_evidence_ids=["ev-1"], produced_artifact_id="art-out")
        pkt = _packet(skill_usage=[su], artifacts=[_artifact("art-out")],
                      evidence=[_evidence("ev-1", source_artifact_id="art-out")])
        result = validate_skill_usage(pkt)
        assert result.valid, "\n".join(result.errors)

    def test_skill_usage_with_missing_artifact_fails(self):
        su = _skill_usage(produced_artifact_id="art-missing")
        pkt = _packet(skill_usage=[su], artifacts=[_artifact("art-out")])
        result = validate_skill_usage(pkt)
        assert not result.valid
        assert any("art-missing" in e for e in result.errors)

    def test_skill_usage_with_resolved_evidence_passes(self):
        su = _skill_usage(cited_evidence_ids=["ev-1"], produced_artifact_id="art-out")
        pkt = _packet(skill_usage=[su], artifacts=[_artifact("art-out")],
                      evidence=[_evidence("ev-1", source_artifact_id="art-out")])
        result = validate_skill_usage(pkt)
        assert result.valid, "\n".join(result.errors)

    def test_skill_usage_with_missing_evidence_fails(self):
        su = _skill_usage(cited_evidence_ids=["ev-missing"], produced_artifact_id="art-out")
        pkt = _packet(skill_usage=[su], artifacts=[_artifact("art-out")])
        result = validate_skill_usage(pkt)
        assert not result.valid
        assert any("ev-missing" in e for e in result.errors)

    def test_skill_usage_with_resolved_decision_passes(self):
        su = _skill_usage(cited_evidence_ids=["ev-1"], adopted_by_decision_id="dec-1",
                          produced_artifact_id="art-out")
        dec = _decision("dec-1", target_ref="su-1")
        dec["evidence_ids"] = ["ev-1"]
        pkt = _packet(skill_usage=[su], artifacts=[_artifact("art-out")],
                      evidence=[_evidence("ev-1", source_artifact_id="art-out")],
                      decisions=[dec])
        result = validate_skill_usage(pkt)
        assert result.valid, "\n".join(result.errors)

    def test_skill_usage_with_missing_decision_fails(self):
        su = _skill_usage(adopted_by_decision_id="dec-missing", produced_artifact_id="art-out")
        pkt = _packet(skill_usage=[su], artifacts=[_artifact("art-out")])
        result = validate_skill_usage(pkt)
        assert not result.valid
        assert any("dec-missing" in e for e in result.errors)

    def test_skill_usage_decision_target_ref_must_match_skill_usage_id(self):
        """An adopt decision for a skill_usage must target the skill_usage id."""
        su = _skill_usage(su_id="su-1", adopted_by_decision_id="dec-1",
                          produced_artifact_id="art-out")
        # decision targets a different ref
        pkt = _packet(skill_usage=[su], artifacts=[_artifact("art-out")],
                      decisions=[_decision("dec-1", target_ref="su-other")])
        result = validate_skill_usage(pkt)
        assert not result.valid
        assert any("target_ref" in e for e in result.errors)

    def test_skill_usage_decision_must_be_adopt_kind(self):
        """Only adopt decisions can adopt a skill_usage — not review/gate."""
        su = _skill_usage(adopted_by_decision_id="dec-1", produced_artifact_id="art-out")
        pkt = _packet(skill_usage=[su], artifacts=[_artifact("art-out")],
                      decisions=[_decision("dec-1", kind="review", target_ref="su-1")])
        result = validate_skill_usage(pkt)
        assert not result.valid
        assert any("kind" in e and "adopt" in e for e in result.errors)

    def test_skill_usage_decision_must_have_pass_outcome(self):
        su = _skill_usage(adopted_by_decision_id="dec-1", produced_artifact_id="art-out")
        pkt = _packet(skill_usage=[su], artifacts=[_artifact("art-out")],
                      decisions=[_decision("dec-1", outcome="fail", target_ref="su-1")])
        result = validate_skill_usage(pkt)
        assert not result.valid
        assert any("outcome" in e for e in result.errors)

    def test_required_fields_missing_fails(self):
        su = {"id": "", "project_id": "", "skill_id": "", "work_item_id": "",
              "invoked_at": "", "produced_artifact_id": "",
              "cited_evidence_ids": [], "adopted_by_decision_id": None}
        pkt = _packet(skill_usage=[su])
        result = validate_skill_usage(pkt)
        assert not result.valid
        assert any("id" in e for e in result.errors)

    def test_produced_artifact_id_required(self):
        su = _skill_usage(produced_artifact_id="")
        pkt = _packet(skill_usage=[su])
        result = validate_skill_usage(pkt)
        assert not result.valid
        assert any("produced_artifact_id" in e for e in result.errors)

    def test_skill_id_required(self):
        su = _skill_usage(skill_id="")
        pkt = _packet(skill_usage=[su])
        result = validate_skill_usage(pkt)
        assert not result.valid
        assert any("skill_id" in e for e in result.errors)

    def test_whitespace_only_cited_evidence_id_fails(self):
        """P1: whitespace-only evidence refs must not resolve or satisfy required evidence."""
        su = _skill_usage(cited_evidence_ids=["   "], produced_artifact_id="art-out")
        pkt = _packet(skill_usage=[su], artifacts=[_artifact("art-out")],
                      evidence=[_evidence("   ", source_artifact_id="art-out")])
        result = validate_skill_usage(pkt)
        assert not result.valid
        assert any("cited_evidence_id" in e for e in result.errors)

    def test_multiple_errors_accumulated(self):
        su = _skill_usage(produced_artifact_id="art-missing",
                          cited_evidence_ids=["ev-missing"],
                          adopted_by_decision_id="dec-missing")
        pkt = _packet(skill_usage=[su])
        result = validate_skill_usage(pkt)
        assert not result.valid
        assert len(result.errors) >= 3

    def test_cited_evidence_must_support(self):
        """Cited evidence with supports=rejects should not count as supporting the skill usage."""
        su = _skill_usage(cited_evidence_ids=["ev-1"], produced_artifact_id="art-out")
        pkt = _packet(skill_usage=[su], artifacts=[_artifact("art-out")],
                      evidence=[_evidence("ev-1", supports="rejects", source_artifact_id="art-out")])
        result = validate_skill_usage(pkt)
        assert not result.valid
        assert any("supports" in e for e in result.errors)

    # Round 2: evidence-backed adoption chain

    def test_skill_usage_requires_cited_evidence(self):
        """P1-1: skill_usage without cited_evidence_ids is standalone authority — reject."""
        su = _skill_usage(cited_evidence_ids=[], produced_artifact_id="art-out")
        pkt = _packet(skill_usage=[su], artifacts=[_artifact("art-out")])
        result = validate_skill_usage(pkt)
        assert not result.valid
        assert any("cited_evidence_ids" in e for e in result.errors)

    def test_cited_evidence_source_artifact_must_resolve(self):
        """P1-2: cited evidence's source_artifact_id must resolve to a declared artifact."""
        su = _skill_usage(cited_evidence_ids=["ev-1"], produced_artifact_id="art-out")
        pkt = _packet(skill_usage=[su], artifacts=[_artifact("art-out")],
                      evidence=[_evidence("ev-1", source_artifact_id="art-orphan")])
        result = validate_skill_usage(pkt)
        assert not result.valid
        assert any("source_artifact_id" in e for e in result.errors)

    def test_adopting_decision_must_have_evidence_ids(self):
        """P0-1: adopt/pass decision with empty evidence_ids must not adopt."""
        su = _skill_usage(cited_evidence_ids=["ev-1"], adopted_by_decision_id="dec-1",
                          produced_artifact_id="art-out")
        dec = _decision("dec-1", target_ref="su-1")
        dec["evidence_ids"] = []
        pkt = _packet(skill_usage=[su], artifacts=[_artifact("art-out")],
                      evidence=[_evidence("ev-1", source_artifact_id="art-out")],
                      decisions=[dec])
        result = validate_skill_usage(pkt)
        assert not result.valid
        assert any("evidence_ids" in e for e in result.errors)

    def test_adopting_decision_evidence_ids_must_resolve(self):
        """P0-1: adopting decision evidence_ids must resolve to declared evidence."""
        su = _skill_usage(cited_evidence_ids=["ev-1"], adopted_by_decision_id="dec-1",
                          produced_artifact_id="art-out")
        dec = _decision("dec-1", target_ref="su-1")
        dec["evidence_ids"] = ["ev-missing"]
        pkt = _packet(skill_usage=[su], artifacts=[_artifact("art-out")],
                      evidence=[_evidence("ev-1", source_artifact_id="art-out")],
                      decisions=[dec])
        result = validate_skill_usage(pkt)
        assert not result.valid
        assert any("ev-missing" in e for e in result.errors)

    def test_adopting_decision_evidence_must_support(self):
        """P0-1: adopting decision evidence with supports=rejects must not adopt."""
        su = _skill_usage(cited_evidence_ids=["ev-1"], adopted_by_decision_id="dec-1",
                          produced_artifact_id="art-out")
        dec = _decision("dec-1", target_ref="su-1")
        dec["evidence_ids"] = ["ev-1"]
        pkt = _packet(skill_usage=[su], artifacts=[_artifact("art-out")],
                      evidence=[_evidence("ev-1", supports="rejects", source_artifact_id="art-out")],
                      decisions=[dec])
        result = validate_skill_usage(pkt)
        assert not result.valid
        assert any("supports" in e for e in result.errors)

    def test_adopting_decision_evidence_must_cover_skill_usage_cited_evidence(self):
        """P0-1: decision evidence_ids must cover (superset of) skill_usage cited_evidence_ids."""
        su = _skill_usage(cited_evidence_ids=["ev-1", "ev-2"], adopted_by_decision_id="dec-1",
                          produced_artifact_id="art-out")
        dec = _decision("dec-1", target_ref="su-1")
        dec["evidence_ids"] = ["ev-1"]  # missing ev-2
        pkt = _packet(skill_usage=[su], artifacts=[_artifact("art-out")],
                      evidence=[_evidence("ev-1", source_artifact_id="art-out"),
                                _evidence("ev-2", source_artifact_id="art-out")],
                      decisions=[dec])
        result = validate_skill_usage(pkt)
        assert not result.valid
        assert any("cover" in e or "subset" in e or "cited" in e for e in result.errors)

    def test_full_evidence_backed_adoption_passes(self):
        """Happy path: cited evidence + evidence-backed adopt decision with full coverage."""
        su = _skill_usage(cited_evidence_ids=["ev-1"], adopted_by_decision_id="dec-1",
                          produced_artifact_id="art-out")
        dec = _decision("dec-1", target_ref="su-1")
        dec["evidence_ids"] = ["ev-1"]
        pkt = _packet(skill_usage=[su], artifacts=[_artifact("art-out")],
                      evidence=[_evidence("ev-1", source_artifact_id="art-out")],
                      decisions=[dec])
        result = validate_skill_usage(pkt)
        assert result.valid, "\n".join(result.errors)


# ---------------------------------------------------------------------------
# derive_skill_utilization
# ---------------------------------------------------------------------------

class TestDeriveSkillUtilization:
    def test_empty_packet_returns_zero_utilization(self):
        result = derive_skill_utilization(_packet())
        assert result["skill_usage_count"] == 0
        assert result["adopted_count"] == 0
        assert result["skills"] == []

    def test_utilization_counts_total_and_adopted(self):
        su1 = _skill_usage(su_id="su-1", cited_evidence_ids=["ev-1"],
                           adopted_by_decision_id="dec-1", produced_artifact_id="art-out")
        su2 = _skill_usage(su_id="su-2", cited_evidence_ids=["ev-1"],
                           adopted_by_decision_id=None, produced_artifact_id="art-out")
        dec = _decision("dec-1", target_ref="su-1")
        dec["evidence_ids"] = ["ev-1"]
        pkt = _packet(skill_usage=[su1, su2], artifacts=[_artifact("art-out")],
                      evidence=[_evidence("ev-1", source_artifact_id="art-out")],
                      decisions=[dec])
        result = derive_skill_utilization(pkt)
        assert result["skill_usage_count"] == 2
        assert result["adopted_count"] == 1

    def test_utilization_groups_by_skill_id(self):
        su1 = _skill_usage(su_id="su-1", skill_id="skill-tdd",
                           produced_artifact_id="art-out")
        su2 = _skill_usage(su_id="su-2", skill_id="skill-tdd",
                           produced_artifact_id="art-out")
        su3 = _skill_usage(su_id="su-3", skill_id="skill-review",
                           produced_artifact_id="art-out")
        pkt = _packet(skill_usage=[su1, su2, su3], artifacts=[_artifact("art-out")])
        result = derive_skill_utilization(pkt)
        by_skill = {s["skill_id"]: s for s in result["skills"]}
        assert by_skill["skill-tdd"]["invocation_count"] == 2
        assert by_skill["skill-review"]["invocation_count"] == 1

    def test_utilization_does_not_invent_adoption(self):
        """Adoption only counts when adopt decision exists, is adopt kind, pass outcome, target_ref matches."""
        su = _skill_usage(su_id="su-1", adopted_by_decision_id="dec-1",
                          produced_artifact_id="art-out")
        # decision has wrong kind
        pkt = _packet(skill_usage=[su], artifacts=[_artifact("art-out")],
                      decisions=[_decision("dec-1", kind="review", target_ref="su-1")])
        result = derive_skill_utilization(pkt)
        assert result["adopted_count"] == 0

    def test_utilization_does_not_count_adoption_without_valid_evidence_backing(self):
        """P1-3: adoption must be evidence-backed to count in utilization."""
        su = _skill_usage(su_id="su-1", cited_evidence_ids=["ev-1"],
                          adopted_by_decision_id="dec-1", produced_artifact_id="art-out")
        dec = _decision("dec-1", target_ref="su-1")
        dec["evidence_ids"] = []  # no evidence backing
        pkt = _packet(skill_usage=[su], artifacts=[_artifact("art-out")],
                      evidence=[_evidence("ev-1", source_artifact_id="art-out")],
                      decisions=[dec])
        result = derive_skill_utilization(pkt)
        assert result["adopted_count"] == 0

    def test_utilization_counts_evidence_backed_adoption(self):
        """Happy path: evidence-backed adopt decision counts as adopted."""
        su = _skill_usage(su_id="su-1", cited_evidence_ids=["ev-1"],
                          adopted_by_decision_id="dec-1", produced_artifact_id="art-out")
        dec = _decision("dec-1", target_ref="su-1")
        dec["evidence_ids"] = ["ev-1"]
        pkt = _packet(skill_usage=[su], artifacts=[_artifact("art-out")],
                      evidence=[_evidence("ev-1", source_artifact_id="art-out")],
                      decisions=[dec])
        result = derive_skill_utilization(pkt)
        assert result["adopted_count"] == 1

    def test_utilization_does_not_count_adoption_without_cited_evidence(self):
        """P0-1: cited_evidence_ids empty -> not adopted in projection."""
        su = _skill_usage(su_id="su-1", cited_evidence_ids=[],
                          adopted_by_decision_id="dec-1", produced_artifact_id="art-out")
        dec = _decision("dec-1", target_ref="su-1")
        dec["evidence_ids"] = ["ev-1"]
        pkt = _packet(skill_usage=[su], artifacts=[_artifact("art-out")],
                      evidence=[_evidence("ev-1", source_artifact_id="art-out")],
                      decisions=[dec])
        result = derive_skill_utilization(pkt)
        assert result["adopted_count"] == 0

    def test_utilization_does_not_count_adoption_when_cited_evidence_source_artifact_missing(self):
        """P0-2: cited evidence source_artifact_id unresolved -> not adopted."""
        su = _skill_usage(su_id="su-1", cited_evidence_ids=["ev-1"],
                          adopted_by_decision_id="dec-1", produced_artifact_id="art-out")
        dec = _decision("dec-1", target_ref="su-1")
        dec["evidence_ids"] = ["ev-1"]
        pkt = _packet(skill_usage=[su], artifacts=[_artifact("art-out")],
                      evidence=[_evidence("ev-1", source_artifact_id="art-missing")],
                      decisions=[dec])
        result = derive_skill_utilization(pkt)
        assert result["adopted_count"] == 0

    def test_utilization_does_not_count_adoption_when_decision_evidence_source_artifact_missing(self):
        """P1-1: decision evidence source_artifact_id unresolved -> not adopted."""
        su = _skill_usage(su_id="su-1", cited_evidence_ids=["ev-1"],
                          adopted_by_decision_id="dec-1", produced_artifact_id="art-out")
        dec = _decision("dec-1", target_ref="su-1")
        dec["evidence_ids"] = ["ev-1", "ev-2"]
        pkt = _packet(skill_usage=[su], artifacts=[_artifact("art-out")],
                      evidence=[_evidence("ev-1", source_artifact_id="art-out"),
                                _evidence("ev-2", source_artifact_id="art-missing")],
                      decisions=[dec])
        result = derive_skill_utilization(pkt)
        assert result["adopted_count"] == 0

    def test_validator_rejects_decision_evidence_with_unresolved_source_artifact(self):
        """P1-1: validator must reject decision evidence whose source_artifact_id is unresolved."""
        su = _skill_usage(su_id="su-1", cited_evidence_ids=["ev-1"],
                          adopted_by_decision_id="dec-1", produced_artifact_id="art-out")
        dec = _decision("dec-1", target_ref="su-1")
        dec["evidence_ids"] = ["ev-1", "ev-2"]
        pkt = _packet(skill_usage=[su], artifacts=[_artifact("art-out")],
                      evidence=[_evidence("ev-1", source_artifact_id="art-out"),
                                _evidence("ev-2", source_artifact_id="art-missing")],
                      decisions=[dec])
        result = validate_skill_usage(pkt)
        assert not result.valid
        assert any("ev-2" in e and "source_artifact_id" in e for e in result.errors)

    def test_utilization_does_not_count_adoption_when_produced_artifact_missing(self):
        """P0: produced_artifact_id unresolved -> not adopted in projection."""
        su = _skill_usage(su_id="su-1", cited_evidence_ids=["ev-1"],
                          adopted_by_decision_id="dec-1", produced_artifact_id="art-missing")
        dec = _decision("dec-1", target_ref="su-1")
        dec["evidence_ids"] = ["ev-1"]
        pkt = _packet(skill_usage=[su], artifacts=[_artifact("art-out")],
                      evidence=[_evidence("ev-1", source_artifact_id="art-out")],
                      decisions=[dec])
        result = derive_skill_utilization(pkt)
        assert result["adopted_count"] == 0

    def test_utilization_does_not_count_adoption_when_produced_artifact_id_empty(self):
        """P0: produced_artifact_id empty -> not adopted in projection."""
        su = _skill_usage(su_id="su-1", cited_evidence_ids=["ev-1"],
                          adopted_by_decision_id="dec-1", produced_artifact_id="")
        dec = _decision("dec-1", target_ref="su-1")
        dec["evidence_ids"] = ["ev-1"]
        pkt = _packet(skill_usage=[su], artifacts=[_artifact("art-out")],
                      evidence=[_evidence("ev-1", source_artifact_id="art-out")],
                      decisions=[dec])
        result = derive_skill_utilization(pkt)
        assert result["adopted_count"] == 0

    def test_utilization_does_not_count_adoption_when_skill_usage_id_missing(self):
        su = _skill_usage(su_id="", cited_evidence_ids=["ev-1"],
                          adopted_by_decision_id="dec-1", produced_artifact_id="art-out")
        dec = _decision("dec-1", target_ref="su-1")
        dec["evidence_ids"] = ["ev-1"]
        pkt = _packet(skill_usage=[su], artifacts=[_artifact("art-out")],
                      evidence=[_evidence("ev-1", source_artifact_id="art-out")],
                      decisions=[dec])
        result = derive_skill_utilization(pkt)
        assert result["adopted_count"] == 0

    def test_utilization_does_not_count_adoption_when_skill_id_missing(self):
        su = _skill_usage(su_id="su-1", skill_id="", cited_evidence_ids=["ev-1"],
                          adopted_by_decision_id="dec-1", produced_artifact_id="art-out")
        dec = _decision("dec-1", target_ref="su-1")
        dec["evidence_ids"] = ["ev-1"]
        pkt = _packet(skill_usage=[su], artifacts=[_artifact("art-out")],
                      evidence=[_evidence("ev-1", source_artifact_id="art-out")],
                      decisions=[dec])
        result = derive_skill_utilization(pkt)
        assert result["adopted_count"] == 0

    def test_utilization_does_not_count_whitespace_skill_id(self):
        su = _skill_usage(su_id="su-1", skill_id="   ", cited_evidence_ids=["ev-1"],
                          adopted_by_decision_id="dec-1", produced_artifact_id="art-out")
        dec = _decision("dec-1", target_ref="su-1")
        dec["evidence_ids"] = ["ev-1"]
        pkt = _packet(skill_usage=[su], artifacts=[_artifact("art-out")],
                      evidence=[_evidence("ev-1", source_artifact_id="art-out")],
                      decisions=[dec])
        result = derive_skill_utilization(pkt)
        assert result["adopted_count"] == 0
        assert result["skills"] == []

    def test_utilization_does_not_count_adoption_when_project_id_missing(self):
        su = _skill_usage(su_id="su-1", project_id="", cited_evidence_ids=["ev-1"],
                          adopted_by_decision_id="dec-1", produced_artifact_id="art-out")
        dec = _decision("dec-1", target_ref="su-1")
        dec["evidence_ids"] = ["ev-1"]
        pkt = _packet(skill_usage=[su], artifacts=[_artifact("art-out")],
                      evidence=[_evidence("ev-1", source_artifact_id="art-out")],
                      decisions=[dec])
        result = derive_skill_utilization(pkt)
        assert result["adopted_count"] == 0

    def test_utilization_does_not_count_adoption_when_work_item_id_missing(self):
        su = _skill_usage(su_id="su-1", work_item_id="", cited_evidence_ids=["ev-1"],
                          adopted_by_decision_id="dec-1", produced_artifact_id="art-out")
        dec = _decision("dec-1", target_ref="su-1")
        dec["evidence_ids"] = ["ev-1"]
        pkt = _packet(skill_usage=[su], artifacts=[_artifact("art-out")],
                      evidence=[_evidence("ev-1", source_artifact_id="art-out")],
                      decisions=[dec])
        result = derive_skill_utilization(pkt)
        assert result["adopted_count"] == 0

    def test_utilization_does_not_count_adoption_when_invoked_at_missing(self):
        su = _skill_usage(su_id="su-1", invoked_at="", cited_evidence_ids=["ev-1"],
                          adopted_by_decision_id="dec-1", produced_artifact_id="art-out")
        dec = _decision("dec-1", target_ref="su-1")
        dec["evidence_ids"] = ["ev-1"]
        pkt = _packet(skill_usage=[su], artifacts=[_artifact("art-out")],
                      evidence=[_evidence("ev-1", source_artifact_id="art-out")],
                      decisions=[dec])
        result = derive_skill_utilization(pkt)
        assert result["adopted_count"] == 0

    def test_utilization_is_read_only(self):
        """derive_skill_utilization is a read-only projection — no mutation."""
        su = _skill_usage(produced_artifact_id="art-out")
        pkt = _packet(skill_usage=[su], artifacts=[_artifact("art-out")])
        original = {"skill_usage": list(pkt["skill_usage"])}
        derive_skill_utilization(pkt)
        assert pkt["skill_usage"] == original["skill_usage"]
