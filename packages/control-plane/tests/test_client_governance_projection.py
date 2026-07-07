"""Tests for Phase 3: client governance projection boundary.

Clients (RDCode, T3, shells) may request, display, and propose. They must not
finalize completion, adoption, or policy. The projection is read-only.
"""
from __future__ import annotations

import pytest

from control_plane.client_governance_projection import (
    CLIENT_ALLOWED_ACTIONS,
    CLIENT_FORBIDDEN_ACTIONS,
    ClientActionError,
    project_for_client,
    validate_client_action,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _kernel_payload(work_item_status="ready", decisions=None, evidence=None,
                    work_item_id="wi-1"):
    """Phase 1A kernel-shaped payload with projection populated for validation."""
    from control_plane.review_governance_validator import derive_projection
    base = {
        "project": {"id": "proj-1", "owner_principal_id": "principal-1"},
        "principals": [{"id": "principal-1"}],
        "work_item": {"id": work_item_id, "status": work_item_status,
                      "input_context_artifact_id": "art-ctx"},
        "artifacts": [{"id": "art-ctx", "kind": "context_snapshot"},
                      {"id": "art-out", "kind": "run_output"}],
        "runs": [{"id": "run-1", "principal_id": "principal-1"}],
        "evidence": evidence or [],
        "decisions": decisions or [],
    }
    base["projection"] = derive_projection(base)
    return base


def _document_payload(documents=None, evidence=None, decisions=None):
    """Phase 2 document-authority-shaped payload."""
    return {
        "documents": documents or [],
        "evidence": evidence or [],
        "decisions": decisions or [],
    }


def _combined_payload(work_item_status="ready", kernel_decisions=None,
                      evidence=None, documents=None, doc_decisions=None,
                      work_item_id="wi-1"):
    """Combined payload with both kernel and document sections."""
    return {
        "kernel": _kernel_payload(work_item_status, kernel_decisions, evidence, work_item_id),
        "documents": _document_payload(documents, evidence, doc_decisions),
    }


# ---------------------------------------------------------------------------
# project_for_client
# ---------------------------------------------------------------------------

class TestProjectForClient:
    def test_empty_payload_returns_missing_context(self):
        """Empty payload must not project as ready — no work_item means missing_context."""
        result = project_for_client({})
        assert result["work_item_status"] == ""
        assert result["computed_status"] == "missing_context"
        assert result["document_authority"]["document_count"] == 0
        # Missing context only allows view, never propose/request_review
        assert result["client_allowed_actions"] == ["view"]
        assert result["source_valid"] is False

    def test_kernel_only_projection(self):
        payload = _combined_payload(work_item_status="ready")
        result = project_for_client(payload)
        assert result["work_item_status"] == "ready"
        assert result["computed_status"] == "ready"
        assert "view" in result["client_allowed_actions"]
        assert "finalize_completion" not in result["client_allowed_actions"]

    def test_documents_only_projection(self):
        doc = {"id": "doc-1", "kind": "policy", "status": "draft",
               "content_hash": "a" * 64, "evidence_ids": [],
               "adopting_decision_id": None, "superseding_document_id": None}
        payload = _combined_payload(documents=[doc])
        result = project_for_client(payload)
        assert "documents" in result["document_authority"]
        assert result["document_authority"]["document_count"] == 1

    def test_projection_is_read_only_marker(self):
        """Projection must declare itself read-only."""
        payload = _combined_payload()
        result = project_for_client(payload)
        assert result["read_only"] is True

    def test_client_actions_never_include_authority_writes(self):
        """Even when computed_status=completed, client actions must not include finalize/adopt/decide."""
        gate_pass = {"id": "dec-gate", "project_id": "proj-1", "kind": "gate",
                     "target_ref": "wi-1", "decider_principal_id": "principal-1",
                     "outcome": "pass", "evidence_ids": ["ev-1"], "rationale": "ok"}
        ev = {"id": "ev-1", "supports": "supports", "source_artifact_id": "art-out"}
        payload = _combined_payload(work_item_status="completed",
                                    kernel_decisions=[gate_pass], evidence=[ev])
        result = project_for_client(payload)
        for forbidden in CLIENT_FORBIDDEN_ACTIONS:
            assert forbidden not in result["client_allowed_actions"], (
                f"client projection must not include {forbidden!r}"
            )

    def test_projection_combines_kernel_and_document_authority(self):
        """Full projection has both work_item computed_status and document authority states."""
        gate_pass = {"id": "dec-gate", "project_id": "proj-1", "kind": "gate",
                     "target_ref": "wi-1", "decider_principal_id": "principal-1",
                     "outcome": "pass", "evidence_ids": ["ev-1"], "rationale": "ok"}
        adopt_dec = {"id": "dec-adopt", "project_id": "proj-1", "kind": "adopt",
                     "target_ref": "doc-1", "decider_principal_id": "principal-1",
                     "outcome": "pass", "evidence_ids": ["ev-1"], "rationale": "ok"}
        ev = {"id": "ev-1", "supports": "supports", "source_artifact_id": "art-out"}
        doc = {"id": "doc-1", "kind": "policy", "status": "current",
               "content_hash": "a" * 64, "evidence_ids": ["ev-1"],
               "adopting_decision_id": "dec-adopt", "superseding_document_id": None}
        payload = _combined_payload(work_item_status="completed",
                                    kernel_decisions=[gate_pass], evidence=[ev],
                                    documents=[doc], doc_decisions=[adopt_dec])
        result = project_for_client(payload)
        assert result["computed_status"] == "completed"
        assert result["document_authority"]["authoritative_count"] == 1


# ---------------------------------------------------------------------------
# validate_client_action
# ---------------------------------------------------------------------------

class TestValidateClientAction:
    def test_allowed_action_passes(self):
        payload = _combined_payload()
        result = validate_client_action(payload, "view")
        assert result.ok is True

    def test_request_review_is_allowed(self):
        """RDCode may request — request_review is a propose-class action."""
        payload = _combined_payload()
        result = validate_client_action(payload, "request_review")
        assert result.ok is True

    def test_propose_is_allowed(self):
        payload = _combined_payload()
        result = validate_client_action(payload, "propose")
        assert result.ok is True

    def test_escalate_is_allowed(self):
        payload = _combined_payload()
        result = validate_client_action(payload, "escalate")
        assert result.ok is True

    def test_finalize_completion_is_forbidden(self):
        """Clients must not finalize completion."""
        payload = _combined_payload()
        result = validate_client_action(payload, "finalize_completion")
        assert result.ok is False
        assert "finalize_completion" in result.error

    def test_adopt_document_is_forbidden(self):
        """Clients must not adopt documents."""
        payload = _combined_payload()
        result = validate_client_action(payload, "adopt_document")
        assert result.ok is False
        assert "adopt_document" in result.error

    def test_record_decision_is_forbidden(self):
        """Clients must not record decisions — that is policy authority."""
        payload = _combined_payload()
        result = validate_client_action(payload, "record_decision")
        assert result.ok is False

    def test_set_status_is_forbidden(self):
        """Clients must not set work_item status — that finalizes completion."""
        payload = _combined_payload()
        result = validate_client_action(payload, "set_status")
        assert result.ok is False

    def test_promote_document_is_forbidden(self):
        """Clients must not promote documents — that is adoption authority."""
        payload = _combined_payload()
        result = validate_client_action(payload, "promote_document")
        assert result.ok is False

    def test_unknown_action_is_forbidden(self):
        """Unknown actions default to forbidden (closed set)."""
        payload = _combined_payload()
        result = validate_client_action(payload, "unknown_thing")
        assert result.ok is False

    def test_forbidden_action_raises_client_action_error(self):
        """When raise_on_violation=True, forbidden actions raise ClientActionError."""
        payload = _combined_payload()
        with pytest.raises(ClientActionError):
            validate_client_action(payload, "finalize_completion", raise_on_violation=True)


# ---------------------------------------------------------------------------
# Boundary invariants
# ---------------------------------------------------------------------------

class TestBoundaryInvariants:
    def test_client_allowed_actions_is_subset_of_safe_actions(self):
        """Every allowed action must be in the safe closed set."""
        safe = {"view", "request_review", "propose", "escalate", "gather_evidence"}
        for action in CLIENT_ALLOWED_ACTIONS:
            assert action in safe, f"unexpected allowed action {action!r}"

    def test_forbidden_actions_cover_all_authority_writes(self):
        """Forbidden set must cover finalize, adopt, decide, policy."""
        required = {"finalize_completion", "adopt_document", "record_decision",
                    "set_status", "promote_document"}
        assert required.issubset(set(CLIENT_FORBIDDEN_ACTIONS))

    def test_allowed_and_forbidden_are_disjoint(self):
        """No action can be both allowed and forbidden."""
        overlap = set(CLIENT_ALLOWED_ACTIONS) & set(CLIENT_FORBIDDEN_ACTIONS)
        assert overlap == set(), f"overlap: {overlap}"

    def test_projection_does_not_expose_internal_decision_mutation(self):
        """Projection must not expose fields that let clients mutate decisions."""
        payload = _combined_payload()
        result = project_for_client(payload)
        # No write-capable fields exposed
        assert "decisions" not in result
        assert "runs" not in result
        assert "artifacts" not in result
        assert "_internal" not in result


# ---------------------------------------------------------------------------
# P1 regression: invalid kernel must not project as completed/authoritative
# ---------------------------------------------------------------------------

class TestInvalidKernelProjection:
    def test_invalid_gate_pass_not_projected_as_completed(self):
        """A gate pass citing only review_report evidence is invalid; must not show completed."""
        gate_pass = {"id": "dec-gate", "project_id": "proj-1", "kind": "gate",
                     "target_ref": "wi-1", "decider_principal_id": "principal-1",
                     "outcome": "pass", "evidence_ids": ["ev-1"], "rationale": "ok"}
        # art-out is review_report — gate pass with only report evidence is invalid
        ev = {"id": "ev-1", "supports": "supports", "source_artifact_id": "art-out"}
        # Override artifacts to make art-out a review_report
        kernel = _kernel_payload(work_item_status="completed",
                                 decisions=[gate_pass], evidence=[ev])
        kernel["artifacts"] = [{"id": "art-ctx", "kind": "context_snapshot"},
                               {"id": "art-out", "kind": "review_report"}]
        payload = {"kernel": kernel, "documents": {}}
        result = project_for_client(payload)
        assert result["source_valid"] is False
        assert result["computed_status"] == "invalid"
        assert result["client_allowed_actions"] == ["view"]

    def test_gate_pass_missing_source_artifact_id_not_projected_as_completed(self):
        """A gate pass evidence item without source_artifact_id must not look trusted."""
        gate_pass = {"id": "dec-gate", "project_id": "proj-1", "kind": "gate",
                     "target_ref": "wi-1", "decider_principal_id": "principal-1",
                     "outcome": "pass", "evidence_ids": ["ev-1"], "rationale": "ok"}
        ev = {"id": "ev-1", "supports": "supports"}
        kernel = _kernel_payload(work_item_status="completed",
                                 decisions=[gate_pass], evidence=[ev])
        payload = {"kernel": kernel, "documents": {}}
        result = project_for_client(payload)
        assert result["source_valid"] is False
        assert result["computed_status"] == "invalid"
        assert any("source_artifact_id" in e for e in result["source_errors"])

    def test_missing_kernel_not_projected_as_ready(self):
        """No work_item in kernel must not yield ready/propose."""
        payload = {"kernel": {}, "documents": {}}
        result = project_for_client(payload)
        assert result["computed_status"] == "missing_context"
        assert "propose" not in result["client_allowed_actions"]
        assert "request_review" not in result["client_allowed_actions"]

    def test_source_errors_exposed_when_invalid(self):
        """Invalid kernel must surface source_errors to the client."""
        gate_pass = {"id": "dec-gate", "project_id": "proj-1", "kind": "gate",
                     "target_ref": "wi-1", "decider_principal_id": "principal-1",
                     "outcome": "pass", "evidence_ids": ["ev-missing"], "rationale": "ok"}
        kernel = _kernel_payload(work_item_status="completed", decisions=[gate_pass])
        payload = {"kernel": kernel, "documents": {}}
        result = project_for_client(payload)
        assert result["source_valid"] is False
        assert len(result["source_errors"]) > 0

    def test_valid_kernel_projects_normally(self):
        """Valid kernel with non-report evidence gate pass projects as completed."""
        gate_pass = {"id": "dec-gate", "project_id": "proj-1", "kind": "gate",
                     "target_ref": "wi-1", "decider_principal_id": "principal-1",
                     "outcome": "pass", "evidence_ids": ["ev-1"], "rationale": "ok"}
        ev = {"id": "ev-1", "supports": "supports", "source_artifact_id": "art-out"}
        # art-out is run_output (non-report) by default in helper
        kernel = _kernel_payload(work_item_status="completed",
                                 decisions=[gate_pass], evidence=[ev])
        payload = {"kernel": kernel, "documents": {}}
        result = project_for_client(payload)
        assert result["source_valid"] is True
        assert result["computed_status"] == "completed"

    def test_invalid_blocked_kernel_is_view_only(self):
        """Invalid kernel with blocked outcome must still downgrade to invalid + view-only."""
        # decider_principal_id not in principals → invalid kernel
        blocked_dec = {"id": "dec-block", "project_id": "proj-1", "kind": "gate",
                       "target_ref": "wi-1", "decider_principal_id": "ghost-principal",
                       "outcome": "blocked", "evidence_ids": [], "rationale": "blocked"}
        kernel = _kernel_payload(work_item_status="blocked", decisions=[blocked_dec])
        payload = {"kernel": kernel, "documents": {}}
        result = project_for_client(payload)
        assert result["source_valid"] is False
        assert result["computed_status"] == "invalid"
        assert result["client_allowed_actions"] == ["view"]

    def test_invalid_insufficient_evidence_kernel_is_view_only(self):
        """Invalid kernel with insufficient_evidence outcome must downgrade to invalid + view-only."""
        ie_dec = {"id": "dec-ie", "project_id": "proj-1", "kind": "review",
                  "target_ref": "wi-1", "decider_principal_id": "ghost-principal",
                  "outcome": "insufficient_evidence", "evidence_ids": [], "rationale": "ie"}
        kernel = _kernel_payload(work_item_status="blocked", decisions=[ie_dec])
        payload = {"kernel": kernel, "documents": {}}
        result = project_for_client(payload)
        assert result["source_valid"] is False
        assert result["computed_status"] == "invalid"
        assert result["client_allowed_actions"] == ["view"]

    def test_invalid_document_section_does_not_show_authoritative(self):
        """When document validation fails, authoritative_count must be 0 and states invalid."""
        # Document missing content_hash → validate_promotion fails
        doc = {"id": "doc-1", "kind": "policy", "status": "current",
               "content_hash": "", "evidence_ids": ["ev-1"],
               "adopting_decision_id": "dec-adopt", "superseding_document_id": None}
        adopt_dec = {"id": "dec-adopt", "project_id": "proj-1", "kind": "adopt",
                     "target_ref": "doc-1", "decider_principal_id": "principal-1",
                     "outcome": "pass", "evidence_ids": ["ev-1"], "rationale": "ok"}
        ev = {"id": "ev-1", "supports": "supports", "source_artifact_id": "art-out"}
        kernel = _kernel_payload(evidence=[ev])
        payload = {"kernel": kernel,
                   "documents": {"documents": [doc], "evidence": [ev], "decisions": [adopt_dec]}}
        result = project_for_client(payload)
        assert result["source_valid"] is False
        assert result["document_authority"]["authoritative_count"] == 0
        states = [d["authority_state"] for d in result["document_authority"]["documents"]]
        assert all(s == "invalid" for s in states)

    @pytest.mark.parametrize(
        ("doc", "doc_evidence", "adopt_dec"),
        [
            (
                {"id": "", "kind": "policy", "status": "current",
                 "content_hash": "a" * 64, "evidence_ids": ["ev-1"],
                 "adopting_decision_id": "dec-adopt", "superseding_document_id": None},
                [{"id": "ev-1", "supports": "supports", "source_artifact_id": "art-out"}],
                {"id": "dec-adopt", "project_id": "proj-1", "kind": "adopt",
                 "target_ref": "", "decider_principal_id": "principal-1",
                 "outcome": "pass", "evidence_ids": ["ev-1"], "rationale": "ok"},
            ),
            (
                {"id": "doc-1", "kind": "policy", "status": "current",
                 "content_hash": "a" * 64, "evidence_ids": ["   "],
                 "adopting_decision_id": "dec-adopt", "superseding_document_id": None},
                [{"id": "   ", "supports": "supports", "source_artifact_id": "art-out"}],
                {"id": "dec-adopt", "project_id": "proj-1", "kind": "adopt",
                 "target_ref": "doc-1", "decider_principal_id": "principal-1",
                 "outcome": "pass", "evidence_ids": ["   "], "rationale": "ok"},
            ),
            (
                {"id": "doc-1", "kind": "policy", "status": "current",
                 "content_hash": "a" * 64, "evidence_ids": ["ev-1"],
                 "adopting_decision_id": "   ", "superseding_document_id": None},
                [{"id": "ev-1", "supports": "supports", "source_artifact_id": "art-out"}],
                {"id": "   ", "project_id": "proj-1", "kind": "adopt",
                 "target_ref": "doc-1", "decider_principal_id": "principal-1",
                 "outcome": "pass", "evidence_ids": ["ev-1"], "rationale": "ok"},
            ),
        ],
        ids=["empty-document-id", "blank-evidence-id-ref", "blank-adopting-decision-id"],
    )
    def test_identity_invalid_document_section_does_not_show_authoritative(
            self, doc, doc_evidence, adopt_dec):
        """Invalid document identities/refs must not project as authoritative."""
        kernel_ev = {"id": "ev-kernel", "supports": "supports",
                     "source_artifact_id": "art-out"}
        kernel = _kernel_payload(evidence=[kernel_ev])
        payload = {"kernel": kernel,
                   "documents": {"documents": [doc],
                                 "evidence": doc_evidence,
                                 "decisions": [adopt_dec]}}
        result = project_for_client(payload)
        assert result["source_valid"] is False
        assert result["document_authority"]["authoritative_count"] == 0
