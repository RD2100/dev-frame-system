"""Tests for Phase 2: document authority and promotion validation."""
from __future__ import annotations

import pytest

from control_plane.document_authority import (
    DOCUMENT_LIFECYCLE,
    ValidationResult,
    derive_authority,
    validate_promotion,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _base_payload(documents=None, evidence=None, decisions=None):
    return {
        "documents": documents or [],
        "evidence": evidence or [],
        "decisions": decisions or [],
    }


def _decision(did="dec-1", outcome="pass", target_ref="doc-1", project_id="project-1",
              kind="adopt", decider_principal_id="principal-1", rationale="ok",
              evidence_ids=None):
    return {"id": did, "project_id": project_id, "kind": kind,
            "target_ref": target_ref, "decider_principal_id": decider_principal_id,
            "outcome": outcome, "evidence_ids": evidence_ids or ["ev-1"], "rationale": rationale}


def _evidence(eid="ev-1", supports="supports"):
    return {"id": eid, "supports": supports, "source_artifact_id": "artifact-1"}


def _document(did="doc-1", status="current", content_hash="a" * 64,
              evidence_ids=None, adopting_decision_id=None,
              superseding_document_id=None, kind="policy"):
    return {
        "id": did,
        "kind": kind,
        "status": status,
        "content_hash": content_hash,
        "evidence_ids": evidence_ids or [],
        "adopting_decision_id": adopting_decision_id,
        "superseding_document_id": superseding_document_id,
    }


# ---------------------------------------------------------------------------
# derive_authority
# ---------------------------------------------------------------------------

class TestDeriveAuthority:
    def test_empty_documents(self):
        result = derive_authority(_base_payload())
        assert result["document_count"] == 0
        assert result["authoritative_count"] == 0
        assert result["documents"] == []

    def test_draft_document_state(self):
        doc = _document("doc-1", status="draft")
        result = derive_authority(_base_payload(documents=[doc]))
        assert result["documents"][0]["authority_state"] == "draft"

    def test_authoritative_with_adoption_and_evidence(self):
        doc = _document("doc-1", status="current",
                        evidence_ids=["ev-1"],
                        adopting_decision_id="dec-1")
        dec = _decision("dec-1")
        ev = _evidence("ev-1")
        result = derive_authority(_base_payload(
            documents=[doc], evidence=[ev], decisions=[dec]))
        proj = result["documents"][0]
        assert proj["authority_state"] == "authoritative"
        assert proj["is_adopted"] is True
        assert proj["has_evidence"] is True

    @pytest.mark.parametrize(
        ("documents", "evidence", "decisions"),
        [
            (
                [_document("", status="current",
                           evidence_ids=["ev-1"],
                           adopting_decision_id="dec-1")],
                [_evidence("ev-1")],
                [_decision("dec-1", target_ref="")],
            ),
            (
                [_document("doc-1", status="current",
                           evidence_ids=["   "],
                           adopting_decision_id="dec-1")],
                [_evidence("   ")],
                [_decision("dec-1", evidence_ids=["   "])],
            ),
            (
                [_document("doc-1", status="current",
                           evidence_ids=["ev-1"],
                           adopting_decision_id="   ")],
                [_evidence("ev-1")],
                [_decision("   ", target_ref="doc-1")],
            ),
        ],
        ids=["empty-document-id", "blank-evidence-id-ref", "blank-adopting-decision-id"],
    )
    def test_blank_identity_values_are_not_authoritative(self, documents, evidence, decisions):
        result = derive_authority(_base_payload(
            documents=documents, evidence=evidence, decisions=decisions))
        proj = result["documents"][0]
        assert result["authoritative_count"] == 0
        assert proj["authority_state"] == "invalid"
        assert proj["is_adopted"] is False

    @pytest.mark.parametrize("content_hash", [None, "   "])
    def test_current_missing_or_blank_content_hash_not_authoritative(self, content_hash):
        doc = _document("doc-1", status="current",
                        evidence_ids=["ev-1"],
                        adopting_decision_id="dec-1")
        if content_hash is None:
            doc.pop("content_hash")
        else:
            doc["content_hash"] = content_hash
        dec = _decision("dec-1")
        ev = _evidence("ev-1")
        result = derive_authority(_base_payload(
            documents=[doc], evidence=[ev], decisions=[dec]))
        proj = result["documents"][0]
        assert proj["authority_state"] == "pending"
        assert result["authoritative_count"] == 0

    def test_current_with_adoption_but_no_evidence_is_pending(self):
        doc = _document("doc-1", status="current",
                        adopting_decision_id="dec-1")
        dec = _decision("dec-1")
        result = derive_authority(_base_payload(
            documents=[doc], decisions=[dec]))
        proj = result["documents"][0]
        assert proj["authority_state"] == "pending"
        assert proj["has_evidence"] is False

    def test_superseded_with_adoption_and_evidence_is_not_authoritative(self):
        doc = _document("doc-1", status="superseded",
                        superseding_document_id="doc-2",
                        evidence_ids=["ev-1"],
                        adopting_decision_id="dec-1")
        doc2 = _document("doc-2", status="current")
        dec = _decision("dec-1")
        ev = _evidence("ev-1")
        result = derive_authority(_base_payload(
            documents=[doc, doc2], evidence=[ev], decisions=[dec]))
        proj = result["documents"][0]
        assert proj["authority_state"] == "superseded"

    def test_pending_current_without_adoption(self):
        doc = _document("doc-1", status="current")
        result = derive_authority(_base_payload(documents=[doc]))
        assert result["documents"][0]["authority_state"] == "pending"

    def test_archived_document(self):
        doc = _document("doc-1", status="archived")
        result = derive_authority(_base_payload(documents=[doc]))
        assert result["documents"][0]["authority_state"] == "archived"

    def test_superseded_with_successor(self):
        doc = _document("doc-1", status="superseded",
                        superseding_document_id="doc-2")
        doc2 = _document("doc-2", status="current")
        result = derive_authority(_base_payload(documents=[doc, doc2]))
        assert result["documents"][0]["authority_state"] == "superseded"

    def test_superseded_self_loop_invalid(self):
        doc = _document("doc-1", status="superseded",
                        superseding_document_id="doc-1")
        result = derive_authority(_base_payload(documents=[doc]))
        assert result["documents"][0]["authority_state"] == "invalid"

    def test_authoritative_count(self):
        d1 = _document("doc-1", status="current", evidence_ids=["ev-1"],
                       adopting_decision_id="dec-1")
        d2 = _document("doc-2", status="draft")
        dec = _decision("dec-1")
        ev = _evidence("ev-1")
        result = derive_authority(_base_payload(
            documents=[d1, d2], evidence=[ev], decisions=[dec]))
        assert result["authoritative_count"] == 1
        assert result["document_count"] == 2

    def test_target_ref_mismatch_not_authoritative(self):
        doc = _document("doc-1", status="current",
                        evidence_ids=["ev-1"],
                        adopting_decision_id="dec-1")
        dec = _decision("dec-1", target_ref="doc-wrong")
        ev = _evidence("ev-1")
        result = derive_authority(_base_payload(
            documents=[doc], evidence=[ev], decisions=[dec]))
        proj = result["documents"][0]
        assert proj["authority_state"] == "pending"
        assert proj["is_adopted"] is False

    def test_review_kind_decision_cannot_adopt_document(self):
        doc = _document("doc-1", status="current",
                        evidence_ids=["ev-1"],
                        adopting_decision_id="dec-1")
        dec = _decision("dec-1", kind="review")
        ev = _evidence("ev-1")
        result = derive_authority(_base_payload(
            documents=[doc], evidence=[ev], decisions=[dec]))
        proj = result["documents"][0]
        assert proj["authority_state"] == "pending"
        assert proj["is_adopted"] is False


# ---------------------------------------------------------------------------
# validate_promotion
# ---------------------------------------------------------------------------

class TestValidatePromotion:
    def test_empty_documents_fails(self):
        result = validate_promotion(_base_payload())
        assert not result.valid
        assert any("empty" in e for e in result.errors)

    def test_current_with_adoption_and_evidence_passes(self):
        doc = _document("doc-1", status="current",
                        content_hash="a" * 64,
                        evidence_ids=["ev-1"],
                        adopting_decision_id="dec-1")
        dec = _decision("dec-1")
        ev = _evidence("ev-1")
        result = validate_promotion(_base_payload(
            documents=[doc], evidence=[ev], decisions=[dec]))
        assert result.valid, "\n".join(result.errors)

    @pytest.mark.parametrize(
        ("documents", "evidence", "decisions", "expected_error"),
        [
            (
                [_document("", status="current",
                           content_hash="a" * 64,
                           evidence_ids=["ev-1"],
                           adopting_decision_id="dec-1")],
                [_evidence("ev-1")],
                [_decision("dec-1", target_ref="")],
                "document id",
            ),
            (
                [_document("doc-1", status="current",
                           content_hash="a" * 64,
                           evidence_ids=["   "],
                           adopting_decision_id="dec-1")],
                [_evidence("   ")],
                [_decision("dec-1", evidence_ids=["   "])],
                "evidence_ids",
            ),
            (
                [_document("doc-1", status="current",
                           content_hash="a" * 64,
                           evidence_ids=["ev-1"],
                           adopting_decision_id="   ")],
                [_evidence("ev-1")],
                [_decision("   ", target_ref="doc-1")],
                "adopting_decision_id",
            ),
        ],
        ids=["empty-document-id", "blank-evidence-id-ref", "blank-adopting-decision-id"],
    )
    def test_identity_and_evidence_refs_must_be_nonblank(
            self, documents, evidence, decisions, expected_error):
        result = validate_promotion(_base_payload(
            documents=documents, evidence=evidence, decisions=decisions))
        assert not result.valid
        assert any(expected_error in e and "nonblank" in e for e in result.errors)

    def test_current_without_adoption_fails(self):
        doc = _document("doc-1", status="current", content_hash="a" * 64)
        result = validate_promotion(_base_payload(documents=[doc]))
        assert not result.valid
        assert any("adopting_decision_id" in e for e in result.errors)

    def test_current_with_adoption_but_no_evidence_fails(self):
        doc = _document("doc-1", status="current", content_hash="a" * 64,
                        adopting_decision_id="dec-1")
        dec = _decision("dec-1")
        result = validate_promotion(_base_payload(documents=[doc], decisions=[dec]))
        assert not result.valid
        assert any("requires at least one evidence_id" in e for e in result.errors)

    def test_current_with_rejecting_decision_fails(self):
        doc = _document("doc-1", status="current", content_hash="a" * 64,
                        evidence_ids=["ev-1"], adopting_decision_id="dec-1")
        dec = _decision("dec-1", outcome="fail")
        ev = _evidence("ev-1")
        result = validate_promotion(_base_payload(
            documents=[doc], evidence=[ev], decisions=[dec]))
        assert not result.valid
        assert any("outcome" in e for e in result.errors)

    def test_target_ref_mismatch_fails(self):
        doc = _document("doc-1", status="current", content_hash="a" * 64,
                        evidence_ids=["ev-1"], adopting_decision_id="dec-1")
        dec = _decision("dec-1", target_ref="doc-wrong")
        ev = _evidence("ev-1")
        result = validate_promotion(_base_payload(
            documents=[doc], evidence=[ev], decisions=[dec]))
        assert not result.valid
        assert any("target_ref" in e for e in result.errors)

    def test_review_kind_decision_cannot_adopt_document(self):
        doc = _document("doc-1", status="current", content_hash="a" * 64,
                        evidence_ids=["ev-1"], adopting_decision_id="dec-1")
        dec = _decision("dec-1", kind="review")
        ev = _evidence("ev-1")
        result = validate_promotion(_base_payload(
            documents=[doc], evidence=[ev], decisions=[dec]))
        assert not result.valid
        assert any("kind" in e and "adopt" in e for e in result.errors)

    def test_adopt_decision_requires_evidence_ids(self):
        doc = _document("doc-1", status="current", content_hash="a" * 64,
                        evidence_ids=["ev-1"], adopting_decision_id="dec-1")
        dec = {"id": "dec-1", "project_id": "project-1", "kind": "adopt",
               "target_ref": "doc-1", "decider_principal_id": "principal-1",
               "outcome": "pass", "evidence_ids": [], "rationale": "ok"}
        ev = _evidence("ev-1")
        result = validate_promotion(_base_payload(
            documents=[doc], evidence=[ev], decisions=[dec]))
        assert not result.valid
        assert any("no evidence_ids" in e for e in result.errors)

    def test_adopting_decision_evidence_ids_must_resolve(self):
        doc = _document("doc-1", status="current", content_hash="a" * 64,
                        evidence_ids=["ev-1"], adopting_decision_id="dec-1")
        dec = {"id": "dec-1", "project_id": "project-1", "kind": "adopt",
               "target_ref": "doc-1", "decider_principal_id": "principal-1",
               "outcome": "pass", "evidence_ids": ["ev-missing"], "rationale": "ok"}
        ev = _evidence("ev-1")
        result = validate_promotion(_base_payload(
            documents=[doc], evidence=[ev], decisions=[dec]))
        assert not result.valid
        assert any("adopting decision evidence_id" in e for e in result.errors)

    def test_document_evidence_must_be_backed_by_adopting_decision(self):
        doc = _document("doc-1", status="current", content_hash="a" * 64,
                        evidence_ids=["ev-extra"],
                        adopting_decision_id="dec-1")
        dec = _decision("dec-1", kind="adopt", outcome="pass",
                        target_ref="doc-1", evidence_ids=["ev-1"])
        ev = _evidence("ev-1")
        ev_extra = _evidence("ev-extra", "supports")
        result = validate_promotion(_base_payload(
            documents=[doc], evidence=[ev, ev_extra], decisions=[dec]))
        assert not result.valid
        assert any("not subset of" in e for e in result.errors)

    def test_missing_content_hash_fails(self):
        doc = _document("doc-1", status="current", content_hash="",
                        adopting_decision_id="dec-1")
        dec = _decision("dec-1")
        result = validate_promotion(_base_payload(documents=[doc], decisions=[dec]))
        assert not result.valid
        assert any("content_hash" in e for e in result.errors)

    def test_blank_content_hash_fails(self):
        doc = _document("doc-1", status="current", content_hash="   ",
                        evidence_ids=["ev-1"], adopting_decision_id="dec-1")
        dec = _decision("dec-1")
        ev = _evidence("ev-1")
        result = validate_promotion(_base_payload(
            documents=[doc], evidence=[ev], decisions=[dec]))
        assert not result.valid
        assert any("content_hash" in e for e in result.errors)

    def test_missing_evidence_id_fails(self):
        doc = _document("doc-1", status="current", content_hash="a" * 64,
                        evidence_ids=["ev-missing"], adopting_decision_id="dec-1")
        dec = _decision("dec-1")
        result = validate_promotion(_base_payload(documents=[doc], decisions=[dec]))
        assert not result.valid
        assert any("ev-missing" in e for e in result.errors)

    def test_invalid_status_fails(self):
        doc = _document("doc-1", status="obsolete", content_hash="a" * 64)
        result = validate_promotion(_base_payload(documents=[doc]))
        assert not result.valid
        assert any("status=" in e for e in result.errors)

    def test_superseded_without_successor_fails(self):
        doc = _document("doc-1", status="superseded", content_hash="a" * 64)
        result = validate_promotion(_base_payload(documents=[doc]))
        assert not result.valid
        assert any("superseding_document_id" in e for e in result.errors)

    def test_superseded_self_loop_fails(self):
        doc = _document("doc-1", status="superseded", content_hash="a" * 64,
                        superseding_document_id="doc-1")
        result = validate_promotion(_base_payload(documents=[doc]))
        assert not result.valid
        assert any("self-referential" in e for e in result.errors)

    def test_superseded_missing_successor_fails(self):
        doc = _document("doc-1", status="superseded", content_hash="a" * 64,
                        superseding_document_id="doc-nonexistent")
        result = validate_promotion(_base_payload(documents=[doc]))
        assert not result.valid
        assert any("not in documents list" in e for e in result.errors)

    def test_draft_document_passes(self):
        doc = _document("doc-1", status="draft", content_hash="a" * 64)
        result = validate_promotion(_base_payload(documents=[doc]))
        assert result.valid, "\n".join(result.errors)

    def test_archived_document_passes(self):
        doc = _document("doc-1", status="archived", content_hash="a" * 64)
        result = validate_promotion(_base_payload(documents=[doc]))
        assert result.valid, "\n".join(result.errors)

    def test_multiple_errors_accumulated(self):
        doc = _document("doc-1", status="current", content_hash="",
                        evidence_ids=["ev-missing"],
                        adopting_decision_id="dec-missing")
        result = validate_promotion(_base_payload(documents=[doc]))
        assert not result.valid
        assert len(result.errors) >= 3
