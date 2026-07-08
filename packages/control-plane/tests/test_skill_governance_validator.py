"""Tests for P1-2: skill governance — fingerprints and promotion history.

Per design-coverage-gap-remediation-plan.md:175-193:

  1. Add a skill content fingerprint record that includes SKILL.md and
     relevant bundled references.
  2. Add revision and promotion metadata for custom/project skills.
  3. Tie future evaluation findings to proposed skill revisions, not just
     skill IDs.

Acceptance:
  - the same skill ID with changed content has a different fingerprint;
  - a learning proposal cannot update a skill without regression evidence
    and a promotion decision.
"""
from __future__ import annotations

import pytest

from control_plane.skill_governance_validator import (
    ValidationResult,
    validate_skill_governance,
    derive_skill_governance,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _skill(skill_id="skill-tdd", fingerprint="fp-abc123", revision=1,
           promotion_state="candidate", adopted_by_decision_id=None,
           source_path="skills/tdd/SKILL.md"):
    entry = {
        "skill_id": skill_id,
        "fingerprint": fingerprint,
        "revision": revision,
        "promotion_state": promotion_state,
        "source_path": source_path,
    }
    if adopted_by_decision_id:
        entry["adopted_by_decision_id"] = adopted_by_decision_id
    return entry


def _packet(skill_registry=None, artifacts=None, evidence=None, decisions=None):
    return {
        "skill_registry": skill_registry or [],
        "artifacts": artifacts or [],
        "evidence": evidence or [],
        "decisions": decisions or [],
    }


def _artifact(aid="art-out"):
    return {"id": aid, "kind": "skill_bundle"}


def _evidence(eid="ev-1", supports="supports", source_artifact_id="art-out"):
    return {"id": eid, "supports": supports, "source_artifact_id": source_artifact_id,
            "claim": "claim", "scope": "scope", "freshness": "fresh",
            "observed_result": "result", "project_id": "proj-1"}


def _decision(did="dec-1", kind="adopt", outcome="pass", target_ref="skill-tdd",
              evidence_ids=None):
    return {"id": did, "project_id": "proj-1", "kind": kind, "target_ref": target_ref,
            "decider_principal_id": "principal-1", "outcome": outcome,
            "evidence_ids": evidence_ids if evidence_ids is not None else ["ev-1"],
            "rationale": "ok"}


# ---------------------------------------------------------------------------
# validate_skill_governance
# ---------------------------------------------------------------------------

class TestValidateSkillGovernance:
    def test_empty_passes(self):
        result = validate_skill_governance(_packet())
        assert result.valid

    def test_single_valid_skill_passes(self):
        pkt = _packet(skill_registry=[_skill()])
        result = validate_skill_governance(pkt)
        assert result.valid, "\n".join(result.errors)

    def test_missing_fingerprint_fails(self):
        s = _skill(fingerprint="")
        result = validate_skill_governance(_packet(skill_registry=[s]))
        assert not result.valid
        assert any("fingerprint" in e for e in result.errors)

    def test_missing_skill_id_fails(self):
        s = _skill(skill_id="")
        result = validate_skill_governance(_packet(skill_registry=[s]))
        assert not result.valid
        assert any("skill_id" in e for e in result.errors)

    def test_invalid_promotion_state_fails(self):
        s = _skill(promotion_state="bogus")
        result = validate_skill_governance(_packet(skill_registry=[s]))
        assert not result.valid
        assert any("promotion_state" in e for e in result.errors)

    def test_missing_revision_fails(self):
        s = _skill(revision=0)
        result = validate_skill_governance(_packet(skill_registry=[s]))
        assert not result.valid
        assert any("revision" in e for e in result.errors)

    def test_revision_true_rejected(self):
        """P2: bool True passes isinstance(int) in Python, must be rejected."""
        s = _skill(revision=True)
        result = validate_skill_governance(_packet(skill_registry=[s]))
        assert not result.valid
        assert any("revision" in e for e in result.errors)

    def test_missing_source_path_fails(self):
        s = _skill(source_path="")
        result = validate_skill_governance(_packet(skill_registry=[s]))
        assert not result.valid
        assert any("source_path" in e for e in result.errors)

    def test_whitespace_required_strings_fail(self):
        s = _skill(skill_id="   ", fingerprint="\t", source_path="\n ")
        result = validate_skill_governance(_packet(skill_registry=[s]))
        assert not result.valid
        assert any("skill_id is required" in e for e in result.errors)
        assert any("fingerprint is required" in e for e in result.errors)
        assert any("source_path is required" in e for e in result.errors)

    def test_adoption_decision_must_resolve(self):
        s = _skill(adopted_by_decision_id="dec-missing")
        result = validate_skill_governance(_packet(skill_registry=[s]))
        assert not result.valid
        assert any("dec-missing" in e for e in result.errors)

    def test_adoption_decision_must_be_evidence_backed(self):
        s = _skill(adopted_by_decision_id="dec-1")
        dec = _decision("dec-1", target_ref="skill-tdd", evidence_ids=[])
        result = validate_skill_governance(_packet(
            skill_registry=[s], decisions=[dec]))
        assert not result.valid
        assert any("evidence_ids" in e for e in result.errors)

    def test_adoption_decision_evidence_must_resolve_and_support(self):
        s = _skill(adopted_by_decision_id="dec-1")
        dec = _decision("dec-1", target_ref="skill-tdd", evidence_ids=["ev-1"])
        pkt = _packet(skill_registry=[s], decisions=[dec],
                      evidence=[_evidence("ev-1", supports="rejects")])
        result = validate_skill_governance(pkt)
        assert not result.valid
        assert any("supports" in e for e in result.errors)

    def test_adoption_decision_kind_must_be_adopt_or_promote(self):
        s = _skill(adopted_by_decision_id="dec-1")
        dec = _decision("dec-1", kind="review", target_ref="skill-tdd")
        result = validate_skill_governance(_packet(
            skill_registry=[s], decisions=[dec],
            evidence=[_evidence("ev-1")]))
        assert not result.valid
        assert any("kind" in e for e in result.errors)

    def test_adoption_decision_outcome_must_be_pass(self):
        s = _skill(adopted_by_decision_id="dec-1")
        dec = _decision("dec-1", outcome="fail", target_ref="skill-tdd")
        result = validate_skill_governance(_packet(
            skill_registry=[s], decisions=[dec],
            evidence=[_evidence("ev-1")]))
        assert not result.valid
        assert any("outcome" in e for e in result.errors)

    def test_adoption_decision_target_ref_must_match_skill_id(self):
        s = _skill(skill_id="skill-tdd", adopted_by_decision_id="dec-1")
        dec = _decision("dec-1", target_ref="skill-other")
        result = validate_skill_governance(_packet(
            skill_registry=[s], decisions=[dec],
            evidence=[_evidence("ev-1")]))
        assert not result.valid
        assert any("target_ref" in e for e in result.errors)

    def test_valid_adoption_chain_passes(self):
        s = _skill(skill_id="skill-tdd", adopted_by_decision_id="dec-1",
                   promotion_state="adopted")
        dec = _decision("dec-1", target_ref="skill-tdd", evidence_ids=["ev-1"])
        pkt = _packet(skill_registry=[s], decisions=[dec],
                      evidence=[_evidence("ev-1", source_artifact_id="art-out")],
                      artifacts=[_artifact("art-out")])
        result = validate_skill_governance(pkt)
        assert result.valid, "\n".join(result.errors)

    # Fingerprint uniqueness

    def test_same_skill_id_same_revision_different_fingerprint_fails(self):
        """Two entries for same skill_id+revision with mismatched fingerprints
        is ambiguous data."""
        s1 = _skill(skill_id="skill-tdd", revision=1, fingerprint="fp-aaa")
        s2 = _skill(skill_id="skill-tdd", revision=1, fingerprint="fp-bbb")
        result = validate_skill_governance(_packet(skill_registry=[s1, s2]))
        assert not result.valid
        assert any("fingerprint" in e and "conflicting" in e.lower()
                   for e in result.errors)

    def test_skill_id_whitespace_variant_same_revision_different_fingerprint_fails(self):
        """P2: skill_id whitespace variants are the same governance key."""
        s1 = _skill(skill_id="skill-a", revision=1, fingerprint="fp-aaa")
        s2 = _skill(skill_id="skill-a ", revision=1, fingerprint="fp-bbb")
        result = validate_skill_governance(_packet(skill_registry=[s1, s2]))
        assert not result.valid
        assert any("fingerprint" in e and "conflicting" in e.lower()
                   for e in result.errors)

    def test_same_skill_id_different_revision_same_fingerprint_fails(self):
        """Acceptance: same skill ID with changed content has a different
        fingerprint. Revision bump with unchanged fingerprint implies the
        revision was bumped without a real content change."""
        s1 = _skill(skill_id="skill-tdd", revision=1, fingerprint="fp-abc")
        s2 = _skill(skill_id="skill-tdd", revision=2, fingerprint="fp-abc")
        result = validate_skill_governance(_packet(skill_registry=[s1, s2]))
        assert not result.valid
        assert any("fingerprint" in e and "unchanged" in e.lower()
                   for e in result.errors)

    def test_same_skill_id_different_revision_different_fingerprint_passes(self):
        """Normal case: revision bump + content change = different fingerprint."""
        s1 = _skill(skill_id="skill-tdd", revision=1, fingerprint="fp-abc")
        s2 = _skill(skill_id="skill-tdd", revision=2, fingerprint="fp-def")
        result = validate_skill_governance(_packet(skill_registry=[s1, s2]))
        assert result.valid, "\n".join(result.errors)

    def test_different_skill_ids_same_fingerprint_ok(self):
        """Two entirely different skills could hash to the same value
        (astronomically unlikely but structurally valid)."""
        s1 = _skill(skill_id="skill-tdd", fingerprint="fp-abc")
        s2 = _skill(skill_id="skill-review", fingerprint="fp-abc")
        result = validate_skill_governance(_packet(skill_registry=[s1, s2]))
        assert result.valid, "\n".join(result.errors)

    def test_revision_number_monotonic_violation_detected(self):
        """Duplicate revision for same skill_id is rejected."""
        s1 = _skill(skill_id="skill-tdd", revision=2)
        s2 = _skill(skill_id="skill-tdd", revision=2)
        result = validate_skill_governance(_packet(skill_registry=[s1, s2]))
        assert not result.valid
        assert any("duplicate" in e.lower() for e in result.errors)

    def test_multiple_errors_accumulated(self):
        s1 = _skill(skill_id="", fingerprint="", promotion_state="bogus",
                    revision=0, source_path="")
        result = validate_skill_governance(_packet(skill_registry=[s1]))
        assert not result.valid
        assert len(result.errors) >= 4

    def test_valid_promotion_states_pass(self):
        for state in ("pending", "candidate", "deprecated", "rejected"):
            s = _skill(promotion_state=state)
            result = validate_skill_governance(_packet(skill_registry=[s]))
            assert result.valid, f"state={state}: " + "\n".join(result.errors)

    def test_adopted_state_requires_adoption_decision(self):
        """P0-1: promotion_state='adopted' without adopted_by_decision_id fails."""
        s = _skill(promotion_state="adopted")
        result = validate_skill_governance(_packet(skill_registry=[s]))
        assert not result.valid
        assert any("adopted" in e.lower() and "decision" in e.lower()
                   for e in result.errors)

    def test_adopted_state_requires_valid_evidence_backed_decision(self):
        """P0-1: promotion_state='adopted' with a failing decision chain fails."""
        s = _skill(skill_id="skill-tdd", promotion_state="adopted",
                   adopted_by_decision_id="dec-1")
        dec = _decision("dec-1", target_ref="skill-tdd", evidence_ids=[])
        result = validate_skill_governance(_packet(
            skill_registry=[s], decisions=[dec]))
        assert not result.valid
        assert any("evidence_ids" in e for e in result.errors)

    def test_adoption_decision_evidence_source_artifact_must_resolve(self):
        s = _skill(skill_id="skill-tdd", adopted_by_decision_id="dec-1",
                   promotion_state="adopted")
        dec = _decision("dec-1", target_ref="skill-tdd", evidence_ids=["ev-1"])
        pkt = _packet(skill_registry=[s], decisions=[dec],
                      evidence=[_evidence("ev-1", source_artifact_id="art-orphan")])
        result = validate_skill_governance(pkt)
        assert not result.valid
        assert any("source_artifact_id" in e for e in result.errors)


# ---------------------------------------------------------------------------
# derive_skill_governance
# ---------------------------------------------------------------------------

class TestDeriveSkillGovernance:
    def test_empty_packet(self):
        result = derive_skill_governance(_packet())
        assert result["total_skills"] == 0
        assert result["adopted_count"] == 0
        assert result["by_promotion_state"] == {}

    def test_counts_total_skills(self):
        pkt = _packet(skill_registry=[
            _skill("skill-a"), _skill("skill-b"), _skill("skill-c"),
        ])
        result = derive_skill_governance(pkt)
        assert result["total_skills"] == 3

    def test_groups_by_promotion_state(self):
        pkt = _packet(skill_registry=[
            _skill("skill-a", promotion_state="adopted"),
            _skill("skill-b", promotion_state="adopted"),
            _skill("skill-c", promotion_state="candidate"),
        ])
        result = derive_skill_governance(pkt)
        assert result["by_promotion_state"]["adopted"] == 2
        assert result["by_promotion_state"]["candidate"] == 1

    def test_counts_adopted_only_with_valid_decision_chain(self):
        """Adoption count only increments when decision chain is valid."""
        s1 = _skill("skill-a", adopted_by_decision_id="dec-1",
                    promotion_state="adopted", fingerprint="fp-1")
        s2 = _skill("skill-b", adopted_by_decision_id="dec-2",
                    promotion_state="adopted", fingerprint="fp-2")
        dec1 = _decision("dec-1", target_ref="skill-a", evidence_ids=["ev-1"])
        dec2 = _decision("dec-2", target_ref="skill-b", evidence_ids=[])
        pkt = _packet(skill_registry=[s1, s2],
                      decisions=[dec1, dec2],
                      evidence=[_evidence("ev-1", source_artifact_id="art-out")],
                      artifacts=[_artifact("art-out")])
        result = derive_skill_governance(pkt)
        assert result["adopted_count"] == 1

    def test_adoption_requires_evidence_coverage(self):
        """Adoption requires decision evidence to cover supporting evidence."""
        s = _skill("skill-a", adopted_by_decision_id="dec-1",
                   promotion_state="adopted", fingerprint="fp-1")
        dec = _decision("dec-1", target_ref="skill-a", evidence_ids=["ev-1"])
        pkt = _packet(skill_registry=[s], decisions=[dec],
                      evidence=[_evidence("ev-1", source_artifact_id="art-out")],
                      artifacts=[_artifact("art-out")])
        result = derive_skill_governance(pkt)
        assert result["adopted_count"] == 1

    def test_read_only_projection(self):
        s = _skill("skill-a")
        pkt = _packet(skill_registry=[s])
        original = list(pkt["skill_registry"])
        derive_skill_governance(pkt)
        assert pkt["skill_registry"] == original

    def test_candidate_with_valid_adoption_decision_not_counted_adopted(self):
        """P0-2: candidate with valid decision chain is NOT counted as adopted."""
        s = _skill("skill-a", promotion_state="candidate",
                   adopted_by_decision_id="dec-1", fingerprint="fp-1")
        dec = _decision("dec-1", target_ref="skill-a", evidence_ids=["ev-1"])
        pkt = _packet(skill_registry=[s], decisions=[dec],
                      evidence=[_evidence("ev-1", source_artifact_id="art-out")],
                      artifacts=[_artifact("art-out")])
        result = derive_skill_governance(pkt)
        assert result["adopted_count"] == 0

    def test_rejected_with_valid_adoption_decision_not_counted_adopted(self):
        """P0-2: rejected with valid decision chain is NOT counted as adopted."""
        s = _skill("skill-a", promotion_state="rejected",
                   adopted_by_decision_id="dec-1", fingerprint="fp-1")
        dec = _decision("dec-1", target_ref="skill-a", evidence_ids=["ev-1"])
        pkt = _packet(skill_registry=[s], decisions=[dec],
                      evidence=[_evidence("ev-1", source_artifact_id="art-out")],
                      artifacts=[_artifact("art-out")])
        result = derive_skill_governance(pkt)
        assert result["adopted_count"] == 0

    def test_invalid_skill_base_not_counted_in_projection(self):
        """P0-3: projection must not count entries that fail base validation."""
        s = _skill("", promotion_state="adopted",
                   adopted_by_decision_id="dec-1", fingerprint="fp-1")
        dec = _decision("dec-1", target_ref="", evidence_ids=["ev-1"])
        pkt = _packet(skill_registry=[s], decisions=[dec],
                      evidence=[_evidence("ev-1", source_artifact_id="art-out")],
                      artifacts=[_artifact("art-out")])
        result = derive_skill_governance(pkt)
        assert result["adopted_count"] == 0

    def test_adopted_without_decision_not_counted_in_projection(self):
        """P0-1: adopted without decision is not counted in projection."""
        s = _skill("skill-a", promotion_state="adopted", fingerprint="fp-1")
        pkt = _packet(skill_registry=[s])
        result = derive_skill_governance(pkt)
        assert result["adopted_count"] == 0

    def test_adoption_decision_target_ref_revision_scoped_accepted(self):
        """P1: target_ref='skill-a@rev:2' matches skill_id='skill-a' revision=2."""
        s = _skill("skill-a", revision=2, promotion_state="adopted",
                   adopted_by_decision_id="dec-1", fingerprint="fp-1")
        dec = _decision("dec-1", target_ref="skill-a@rev:2", evidence_ids=["ev-1"])
        pkt = _packet(skill_registry=[s], decisions=[dec],
                      evidence=[_evidence("ev-1", source_artifact_id="art-out")],
                      artifacts=[_artifact("art-out")])
        result = validate_skill_governance(pkt)
        assert result.valid, "\n".join(result.errors)
        result2 = derive_skill_governance(pkt)
        assert result2["adopted_count"] == 1

    def test_adoption_decision_target_ref_revision_scoped_mismatch_fails(self):
        """P1: target_ref='skill-a@rev:3' doesn't match revision=2."""
        s = _skill("skill-a", revision=2, promotion_state="adopted",
                   adopted_by_decision_id="dec-1", fingerprint="fp-1")
        dec = _decision("dec-1", target_ref="skill-a@rev:3", evidence_ids=["ev-1"])
        pkt = _packet(skill_registry=[s], decisions=[dec],
                      evidence=[_evidence("ev-1", source_artifact_id="art-out")],
                      artifacts=[_artifact("art-out")])
        result = validate_skill_governance(pkt)
        assert not result.valid
        assert any("target_ref" in e for e in result.errors)

    def test_one_adoption_decision_cannot_adopt_two_revisions(self):
        """P1: plain skill_id as target_ref is rejected when multiple revisions
        of the same skill exist. Each revision must have its own scoped decision."""
        s1 = _skill("skill-a", revision=1, promotion_state="adopted",
                    adopted_by_decision_id="dec-1", fingerprint="fp-1")
        s2 = _skill("skill-a", revision=2, promotion_state="adopted",
                    adopted_by_decision_id="dec-1", fingerprint="fp-2")
        dec = _decision("dec-1", target_ref="skill-a", evidence_ids=["ev-1"])
        pkt = _packet(skill_registry=[s1, s2], decisions=[dec],
                      evidence=[_evidence("ev-1", source_artifact_id="art-out")],
                      artifacts=[_artifact("art-out")])
        result = validate_skill_governance(pkt)
        assert not result.valid
        assert any("revision-scoped" in e.lower() or "multiple revisions" in e.lower()
                   for e in result.errors)
        result2 = derive_skill_governance(pkt)
        assert result2["adopted_count"] == 0

    def test_skill_id_whitespace_variant_cannot_bypass_revision_scoped_adoption(self):
        """P2: whitespace variants still count as multiple revisions."""
        s1 = _skill("skill-a", revision=1, promotion_state="adopted",
                    adopted_by_decision_id="dec-1", fingerprint="fp-1")
        s2 = _skill("skill-a ", revision=2, promotion_state="adopted",
                    adopted_by_decision_id="dec-2", fingerprint="fp-2")
        dec1 = _decision("dec-1", target_ref="skill-a", evidence_ids=["ev-1"])
        dec2 = _decision("dec-2", target_ref="skill-a ", evidence_ids=["ev-2"])
        pkt = _packet(skill_registry=[s1, s2], decisions=[dec1, dec2],
                      evidence=[_evidence("ev-1", source_artifact_id="art-out"),
                                _evidence("ev-2", source_artifact_id="art-out")],
                      artifacts=[_artifact("art-out")])
        result = validate_skill_governance(pkt)
        assert not result.valid
        assert any("revision-scoped" in e.lower() or "multiple revisions" in e.lower()
                   for e in result.errors)
        result2 = derive_skill_governance(pkt)
        assert result2["adopted_count"] == 0

    def test_plain_skill_id_target_allowed_for_single_revision(self):
        """P1: plain skill_id target_ref is OK when only one revision exists."""
        s = _skill("skill-a", revision=1, promotion_state="adopted",
                   adopted_by_decision_id="dec-1", fingerprint="fp-1")
        dec = _decision("dec-1", target_ref="skill-a", evidence_ids=["ev-1"])
        pkt = _packet(skill_registry=[s], decisions=[dec],
                      evidence=[_evidence("ev-1", source_artifact_id="art-out")],
                      artifacts=[_artifact("art-out")])
        assert validate_skill_governance(pkt).valid
        assert derive_skill_governance(pkt)["adopted_count"] == 1

    def test_revision_scoped_target_adopts_only_matching_revision(self):
        """P1: scoped target_ref='skill-a@rev:2' only adopts revision 2."""
        s1 = _skill("skill-a", revision=1, promotion_state="adopted",
                    adopted_by_decision_id="dec-1", fingerprint="fp-1")
        s2 = _skill("skill-a", revision=2, promotion_state="adopted",
                    adopted_by_decision_id="dec-2", fingerprint="fp-2")
        dec1 = _decision("dec-1", target_ref="skill-a@rev:1", evidence_ids=["ev-1"])
        dec2 = _decision("dec-2", target_ref="skill-a@rev:2", evidence_ids=["ev-2"])
        pkt = _packet(skill_registry=[s1, s2], decisions=[dec1, dec2],
                      evidence=[_evidence("ev-1", source_artifact_id="art-out"),
                                _evidence("ev-2", source_artifact_id="art-out")],
                      artifacts=[_artifact("art-out")])
        assert validate_skill_governance(pkt).valid
        result = derive_skill_governance(pkt)
        assert result["adopted_count"] == 2

    def test_projection_zeroes_adopted_when_fingerprint_uniqueness_fails(self):
        """P0: projection must not count adoption when fingerprint check fails."""
        # Duplicate revision — validator rejects
        s1 = _skill("skill-a", revision=1, fingerprint="fp-1",
                    promotion_state="adopted", adopted_by_decision_id="dec-1")
        s2 = _skill("skill-a", revision=1, fingerprint="fp-1",
                    promotion_state="adopted", adopted_by_decision_id="dec-1")
        dec = _decision("dec-1", target_ref="skill-a@rev:1", evidence_ids=["ev-1"])
        pkt = _packet(skill_registry=[s1, s2], decisions=[dec],
                      evidence=[_evidence("ev-1", source_artifact_id="art-out")],
                      artifacts=[_artifact("art-out")])
        assert not validate_skill_governance(pkt).valid
        result = derive_skill_governance(pkt)
        assert result["adopted_count"] == 0
        # by_promotion_state should correctly count duplicate states
        assert result["by_promotion_state"]["adopted"] == 2

    def test_mixed_revision_types_do_not_crash_validator(self):
        """P1: mixed revision types (int vs str) must not crash validation."""
        s1 = _skill("skill-a", revision="x", fingerprint="fp-x")
        s2 = _skill("skill-a", revision=1, fingerprint="fp-1")
        pkt = _packet(skill_registry=[s1, s2])
        # Must not raise TypeError; should return validation result
        result = validate_skill_governance(pkt)
        assert not result.valid
        # Both entries should be flagged for base validation
        assert any("revision must be a positive integer" in e for e in result.errors)

    def test_mixed_revision_types_do_not_crash_projection(self):
        """P1: mixed revision types must not crash projection."""
        s1 = _skill("skill-a", revision="x", fingerprint="fp-x",
                    promotion_state="adopted", adopted_by_decision_id="dec-1")
        s2 = _skill("skill-a", revision=1, fingerprint="fp-1",
                    promotion_state="adopted", adopted_by_decision_id="dec-1")
        dec = _decision("dec-1", target_ref="skill-a@rev:1", evidence_ids=["ev-1"])
        pkt = _packet(skill_registry=[s1, s2], decisions=[dec],
                      evidence=[_evidence("ev-1", source_artifact_id="art-out")],
                      artifacts=[_artifact("art-out")])
        # Must not raise TypeError
        result = derive_skill_governance(pkt)
        assert result["total_skills"] == 2
        assert result["adopted_count"] == 1  # only s2 passes
