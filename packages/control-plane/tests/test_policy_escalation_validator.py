"""Tests for P2-2: policy and human escalation validator.

Per design-coverage-gap-remediation-plan.md:257-272:
  - a worker, browser, dashboard, model score, or external review cannot grant
    itself authority;
  - human-required states name the exact decision requested.
"""
from __future__ import annotations

import pytest

from control_plane.policy_escalation_validator import (
    HIGH_POWER_ACTIONS,
    NON_AUTHORITY_SOURCES,
    VALID_POLICY_OUTCOMES,
    derive_policy_escalation,
    validate_policy_escalation,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _policy_entry(**overrides):
    """Minimal valid policy decision entry."""
    base = {
        "id": "pol-1",
        "project_id": "proj-1",
        "action": "change_default_rules",
        "outcome": "granted",
        "requested_by": "worker",
        "granted_to": "agent-7",
        "decider_principal_id": "principal-1",
        "decider_type": "human",
        "evidence_ids": ["ev-1"],
    }
    base.update(overrides)
    return base


def _escalation(esc_id=None, **overrides):
    """Minimal valid human escalation entry."""
    base = {
        "id": esc_id or "esc-1",
        "project_id": "proj-1",
        "work_item_id": "wi-1",
        "decision_requested": "approve release to production",
        "why_required": "release state change requires human approval per POL-002",
        "consequence_if_declined": "deployment remains blocked; work item stays 'blocked'",
        "context_snapshot_artifact_id": "art-ctx-1",
        "evidence_summary": "all tests pass, review bundle accepted by GPT Round 7",
    }
    base.update(overrides)
    return base


def _payload(policy_decisions=None, escalations=None, work_items=None):
    return {
        "policy_decisions": policy_decisions or [],
        "escalations": escalations or [],
        "work_items": work_items or [],
    }


def _work_item(wi_id="wi-1"):
    return {"id": wi_id, "status": "blocked"}


# ---------------------------------------------------------------------------
# validate_policy_escalation — base shape
# ---------------------------------------------------------------------------

class TestValidatePolicyEntryShape:
    def test_empty_payload_is_valid(self):
        result = validate_policy_escalation({})
        assert result.valid is True

    def test_valid_granted_policy_entry(self):
        result = validate_policy_escalation(
            _payload(policy_decisions=[_policy_entry()])
        )
        assert result.valid is True

    def test_valid_denied_policy_entry(self):
        entry = _policy_entry(outcome="denied", decider_principal_id="")
        result = validate_policy_escalation(
            _payload(policy_decisions=[entry])
        )
        assert result.valid is True

    def test_missing_id(self):
        entry = _policy_entry(id="")
        result = validate_policy_escalation(
            _payload(policy_decisions=[entry])
        )
        assert not result.valid
        assert "id is required" in result.errors[0]

    def test_missing_project_id(self):
        entry = _policy_entry(project_id="")
        result = validate_policy_escalation(
            _payload(policy_decisions=[entry])
        )
        assert not result.valid
        assert "project_id is required" in result.errors[0]

    def test_missing_action(self):
        entry = _policy_entry(action="")
        result = validate_policy_escalation(
            _payload(policy_decisions=[entry])
        )
        assert not result.valid
        assert "action is required" in result.errors[0]

    def test_missing_outcome(self):
        entry = _policy_entry(outcome="")
        result = validate_policy_escalation(
            _payload(policy_decisions=[entry])
        )
        assert not result.valid
        assert "outcome is required" in result.errors[0]

    def test_missing_requested_by(self):
        entry = _policy_entry(requested_by="")
        result = validate_policy_escalation(
            _payload(policy_decisions=[entry])
        )
        assert not result.valid
        assert "requested_by is required" in result.errors[0]

    def test_whitespace_required_policy_strings_fail(self):
        entry = _policy_entry(
            id="   ",
            project_id="\t",
            action="\n",
            outcome=" ",
            requested_by=" \t ",
        )
        result = validate_policy_escalation(
            _payload(policy_decisions=[entry])
        )
        assert not result.valid
        assert any("id is required" in e for e in result.errors)
        assert any("project_id is required" in e for e in result.errors)
        assert any("action is required" in e for e in result.errors)
        assert any("outcome is required" in e for e in result.errors)
        assert any("requested_by is required" in e for e in result.errors)

    def test_invalid_action_type(self):
        entry = _policy_entry(action="casual_thing")
        result = validate_policy_escalation(
            _payload(policy_decisions=[entry])
        )
        assert not result.valid
        assert "casual_thing" in result.errors[0]

    def test_invalid_outcome_type(self):
        entry = _policy_entry(outcome="maybe_later")
        result = validate_policy_escalation(
            _payload(policy_decisions=[entry])
        )
        assert not result.valid
        assert "maybe_later" in result.errors[0]


# ---------------------------------------------------------------------------
# Self-promotion blocked (POL-003)
# ---------------------------------------------------------------------------

class TestSelfPromotionBlocked:
    def test_worker_cannot_grant_itself_authority(self):
        entry = _policy_entry(requested_by="worker", granted_to="worker")
        result = validate_policy_escalation(
            _payload(policy_decisions=[entry])
        )
        assert not result.valid
        assert "self-promotion" in result.errors[0].lower()
        assert "worker" in result.errors[0]

    def test_worker_self_promotion_cannot_use_subject_whitespace_variant(self):
        entry = _policy_entry(
            requested_by="worker ",
            granted_to="\tworker\n",
            decider_principal_id="principal-1",
            decider_type="human",
        )
        result = validate_policy_escalation(
            _payload(policy_decisions=[entry])
        )
        assert not result.valid
        assert any("self-promotion" in e.lower() for e in result.errors)

        projection = derive_policy_escalation(
            _payload(policy_decisions=[entry])
        )
        assert projection["granted"] == 0
        assert projection["self_promotion_blocked"] == 1

    def test_browser_cannot_grant_itself_authority(self):
        entry = _policy_entry(requested_by="browser", granted_to="browser")
        result = validate_policy_escalation(
            _payload(policy_decisions=[entry])
        )
        assert not result.valid
        assert "self-promotion" in result.errors[0].lower()
        assert "browser" in result.errors[0]

    def test_dashboard_cannot_grant_itself_authority(self):
        entry = _policy_entry(
            requested_by="dashboard", granted_to="dashboard",
            decider_principal_id="principal-1", decider_type="human",
        )
        result = validate_policy_escalation(
            _payload(policy_decisions=[entry])
        )
        assert not result.valid
        assert "self-promotion" in result.errors[0].lower()
        assert "dashboard" in result.errors[0]

    def test_model_score_cannot_grant_itself_authority(self):
        entry = _policy_entry(requested_by="model_score", granted_to="model_score")
        result = validate_policy_escalation(
            _payload(policy_decisions=[entry])
        )
        assert not result.valid
        assert "self-promotion" in result.errors[0].lower()
        assert "model_score" in result.errors[0]

    def test_external_review_cannot_grant_itself_authority(self):
        entry = _policy_entry(
            requested_by="external_review", granted_to="external_review",
        )
        result = validate_policy_escalation(
            _payload(policy_decisions=[entry])
        )
        assert not result.valid
        assert "self-promotion" in result.errors[0].lower()
        assert "external_review" in result.errors[0]

    def test_evaluator_cannot_grant_itself_authority(self):
        entry = _policy_entry(requested_by="evaluator", granted_to="evaluator")
        result = validate_policy_escalation(
            _payload(policy_decisions=[entry])
        )
        assert not result.valid
        assert "self-promotion" in result.errors[0].lower()

    def test_learning_loop_cannot_grant_itself_authority(self):
        entry = _policy_entry(
            requested_by="learning_loop", granted_to="learning_loop",
        )
        result = validate_policy_escalation(
            _payload(policy_decisions=[entry])
        )
        assert not result.valid
        assert "self-promotion" in result.errors[0].lower()

    def test_different_non_authority_entities_ok(self):
        """Worker requesting for browser is not self-promotion."""
        entry = _policy_entry(requested_by="worker", granted_to="browser")
        result = validate_policy_escalation(
            _payload(policy_decisions=[entry])
        )
        assert result.valid is True

    def test_same_entity_but_authorized_not_blocked(self):
        """agent-7 requesting for agent-7 is OK — 'agent-7' is not a non-authority source."""
        entry = _policy_entry(requested_by="agent-7", granted_to="agent-7")
        result = validate_policy_escalation(
            _payload(policy_decisions=[entry])
        )
        assert result.valid is True

    def test_human_requested_by_human_not_blocked(self):
        """principal-1 → principal-1 is not a non-authority source."""
        entry = _policy_entry(
            requested_by="principal-1", granted_to="principal-1",
            decider_type="human",
        )
        result = validate_policy_escalation(
            _payload(policy_decisions=[entry])
        )
        assert result.valid is True

    def test_granted_requires_granted_to(self):
        """P0: outcome=granted must have non-empty granted_to."""
        entry = _policy_entry(granted_to="")
        result = validate_policy_escalation(
            _payload(policy_decisions=[entry])
        )
        assert not result.valid
        assert "granted_to" in result.errors[0]

    def test_granted_without_granted_to_not_counted_in_projection(self):
        """Empty granted_to must not produce a granted count in projection."""
        entry = _policy_entry(id="p1", granted_to="")
        result = derive_policy_escalation(
            _payload(policy_decisions=[entry])
        )
        assert result["granted"] == 0

    def test_self_promotion_cannot_be_bypassed_by_empty_granted_to(self):
        """Empty granted_to with non-authority requested_by must fail validation
        and not count as granted (no bypass)."""
        entry = _policy_entry(
            id="p1", requested_by="worker", granted_to="",
            decider_principal_id="principal-1", decider_type="human",
        )
        result = validate_policy_escalation(
            _payload(policy_decisions=[entry])
        )
        assert not result.valid

        proj = derive_policy_escalation(
            _payload(policy_decisions=[entry])
        )
        assert proj["granted"] == 0
        assert proj["self_promotion_blocked"] == 0

    def test_denied_with_self_reference_not_blocked_by_self_promotion(self):
        """P1: denied self-request is not a self-promotion block (POL-003 guards
        granting, not requesting). Denied/deferred/escalated are fine."""
        entry = _policy_entry(
            outcome="denied", requested_by="worker", granted_to="worker",
            decider_principal_id="", decider_type="",
        )
        result = validate_policy_escalation(
            _payload(policy_decisions=[entry])
        )
        assert result.valid is True

        proj = derive_policy_escalation(
            _payload(policy_decisions=[entry])
        )
        assert proj["self_promotion_blocked"] == 0
        assert proj["denied"] == 1


# ---------------------------------------------------------------------------
# Authority source (POL-001, POL-002)
# ---------------------------------------------------------------------------

class TestAuthoritySource:
    def test_granted_requires_decider_principal_id(self):
        entry = _policy_entry(decider_principal_id="")
        result = validate_policy_escalation(
            _payload(policy_decisions=[entry])
        )
        assert not result.valid
        assert "decider_principal_id" in result.errors[0]

    def test_granted_by_non_authority_decider_type_rejected(self):
        entry = _policy_entry(decider_type="model_score")
        result = validate_policy_escalation(
            _payload(policy_decisions=[entry])
        )
        assert not result.valid
        assert "decider_type" in result.errors[0]

    def test_denied_does_not_need_decider(self):
        entry = _policy_entry(
            outcome="denied", decider_principal_id="", decider_type="",
        )
        result = validate_policy_escalation(
            _payload(policy_decisions=[entry])
        )
        assert result.valid is True

    def test_deferred_does_not_need_decider(self):
        entry = _policy_entry(
            outcome="deferred", decider_principal_id="", decider_type="",
        )
        result = validate_policy_escalation(
            _payload(policy_decisions=[entry])
        )
        assert result.valid is True

    def test_escalated_does_not_need_decider(self):
        entry = _policy_entry(
            outcome="escalated", decider_principal_id="", decider_type="",
        )
        result = validate_policy_escalation(
            _payload(policy_decisions=[entry])
        )
        assert result.valid is True

    def test_granted_by_authorized_decider_is_ok(self):
        entry = _policy_entry(decider_type="human")
        result = validate_policy_escalation(
            _payload(policy_decisions=[entry])
        )
        assert result.valid is True

    def test_granted_to_non_authority_source_with_different_decider_ok(self):
        """Granted to worker by human principal is valid (independent decider)."""
        entry = _policy_entry(
            granted_to="worker", requested_by="worker",
            decider_principal_id="principal-1", decider_type="human",
        )
        # Worker requesting for itself but decider is different → self-promotion blocked
        # This is self-promotion (requested_by=worker, granted_to=worker)
        result = validate_policy_escalation(
            _payload(policy_decisions=[entry])
        )
        assert not result.valid  # self-promotion blocks this

    def test_different_requester_granted_to_non_authority_ok(self):
        """Agent-7 requesting for worker, human decider → valid."""
        entry = _policy_entry(
            requested_by="agent-7", granted_to="worker",
            decider_principal_id="principal-1", decider_type="human",
        )
        result = validate_policy_escalation(
            _payload(policy_decisions=[entry])
        )
        assert result.valid is True


# ---------------------------------------------------------------------------
# Human escalation (POL-004, ATTN-001, ATTN-002)
# ---------------------------------------------------------------------------

class TestHumanEscalation:
    def test_valid_escalation(self):
        result = validate_policy_escalation(
            _payload(
                escalations=[_escalation()],
                work_items=[_work_item()],
            )
        )
        assert result.valid is True

    def test_missing_decision_requested(self):
        esc = _escalation(decision_requested="")
        result = validate_policy_escalation(
            _payload(escalations=[esc], work_items=[_work_item()])
        )
        assert not result.valid
        assert "decision_requested" in result.errors[0]

    def test_missing_why_required(self):
        esc = _escalation(why_required="")
        result = validate_policy_escalation(
            _payload(escalations=[esc], work_items=[_work_item()])
        )
        assert not result.valid
        assert "why_required" in result.errors[0]

    def test_missing_consequence_if_declined(self):
        esc = _escalation(consequence_if_declined="")
        result = validate_policy_escalation(
            _payload(escalations=[esc], work_items=[_work_item()])
        )
        assert not result.valid
        assert "consequence_if_declined" in result.errors[0]

    def test_missing_context_snapshot(self):
        esc = _escalation(context_snapshot_artifact_id="")
        result = validate_policy_escalation(
            _payload(escalations=[esc], work_items=[_work_item()])
        )
        assert not result.valid
        assert "context_snapshot_artifact_id" in result.errors[0]

    def test_unresolved_work_item_id(self):
        esc = _escalation(work_item_id="wi-missing")
        result = validate_policy_escalation(
            _payload(escalations=[esc], work_items=[_work_item("wi-1")])
        )
        assert not result.valid
        assert "work_item_id" in result.errors[0]
        assert "wi-missing" in result.errors[0]

    def test_missing_id(self):
        esc = _escalation(id="")
        result = validate_policy_escalation(
            _payload(escalations=[esc], work_items=[_work_item()])
        )
        assert not result.valid
        assert "id is required" in result.errors[0]

    def test_whitespace_required_escalation_strings_fail(self):
        esc = _escalation(
            id="   ",
            project_id="\t",
            work_item_id="\n",
            decision_requested=" ",
            why_required=" \t ",
            consequence_if_declined="\n ",
            context_snapshot_artifact_id="\t ",
        )
        result = validate_policy_escalation(
            _payload(escalations=[esc], work_items=[_work_item()])
        )
        assert not result.valid
        assert any("id is required" in e for e in result.errors)
        assert any("project_id is required" in e for e in result.errors)
        assert any("work_item_id is required" in e for e in result.errors)
        assert any("decision_requested is required" in e for e in result.errors)
        assert any("why_required is required" in e for e in result.errors)
        assert any("consequence_if_declined is required" in e for e in result.errors)
        assert any("context_snapshot_artifact_id is required" in e for e in result.errors)

    def test_human_required_names_exact_decision(self):
        """The escalation must name the exact decision requested (acceptance criterion)."""
        esc = _escalation(decision_requested="approve release to production")
        result = validate_policy_escalation(
            _payload(escalations=[esc], work_items=[_work_item()])
        )
        assert result.valid is True

    def test_multiple_valid_escalations(self):
        esc1 = _escalation(id="esc-1")
        esc2 = _escalation(
            id="esc-2", work_item_id="wi-2",
            decision_requested="grant exception for security config change",
        )
        result = validate_policy_escalation(
            _payload(
                escalations=[esc1, esc2],
                work_items=[_work_item("wi-1"), _work_item("wi-2")],
            )
        )
        assert result.valid is True


# ---------------------------------------------------------------------------
# derive_policy_escalation (projection)
# ---------------------------------------------------------------------------

class TestDerivePolicyEscalation:
    def test_empty_payload_projection(self):
        result = derive_policy_escalation({})
        assert result["total_policy_decisions"] == 0
        assert result["granted"] == 0
        assert result["denied"] == 0
        assert result["self_promotion_blocked"] == 0
        assert result["total_escalations"] == 0
        assert result["valid_escalations"] == 0
        assert result["pending_human_decisions"] == []

    def test_counts_by_outcome(self):
        entries = [
            _policy_entry(id="p1", outcome="granted"),
            _policy_entry(id="p2", outcome="granted"),
            _policy_entry(id="p3", outcome="denied", decider_principal_id="",
                         decider_type=""),
            _policy_entry(id="p4", outcome="deferred", decider_principal_id="",
                         decider_type=""),
            _policy_entry(id="p5", outcome="escalated", decider_principal_id="",
                         decider_type=""),
        ]
        result = derive_policy_escalation(
            _payload(policy_decisions=entries)
        )
        assert result["total_policy_decisions"] == 5
        assert result["granted"] == 2
        assert result["denied"] == 1
        assert result["deferred"] == 1
        assert result["escalated"] == 1

    def test_self_promotion_blocked_count(self):
        entries = [
            _policy_entry(id="p1"),
            _policy_entry(id="p2", requested_by="worker", granted_to="worker"),
        ]
        result = derive_policy_escalation(
            _payload(policy_decisions=entries)
        )
        assert result["self_promotion_blocked"] == 1

    def test_invalid_entries_not_counted_in_outcomes(self):
        """Entries that fail base validation are excluded from outcome counts."""
        entries = [
            _policy_entry(id="p1", outcome="granted"),
            _policy_entry(id="", outcome="granted"),  # invalid
        ]
        result = derive_policy_escalation(
            _payload(policy_decisions=entries)
        )
        assert result["granted"] == 1  # only p1 counted

    def test_valid_escalation_count(self):
        result = derive_policy_escalation(
            _payload(
                escalations=[_escalation("esc-1"), _escalation("esc-2")],
                work_items=[_work_item("wi-1")],
            )
        )
        assert result["total_escalations"] == 2
        assert result["valid_escalations"] == 2

    def test_invalid_escalation_not_counted(self):
        result = derive_policy_escalation(
            _payload(
                escalations=[
                    _escalation("esc-1"),
                    _escalation("esc-2", decision_requested=""),  # invalid
                ],
                work_items=[_work_item("wi-1")],
            )
        )
        assert result["valid_escalations"] == 1

    def test_pending_human_decisions_detail(self):
        esc = _escalation(
            id="esc-1",
            decision_requested="approve production deployment",
            why_required="release state change per POL-002",
            consequence_if_declined="deployment blocked indefinitely",
        )
        result = derive_policy_escalation(
            _payload(escalations=[esc], work_items=[_work_item()])
        )
        pending = result["pending_human_decisions"]
        assert len(pending) == 1
        assert pending[0]["escalation_id"] == "esc-1"
        assert pending[0]["decision_requested"] == "approve production deployment"
        assert pending[0]["why_required"] == "release state change per POL-002"
        assert pending[0]["consequence_if_declined"] == "deployment blocked indefinitely"

    def test_projection_does_not_expose_write_fields(self):
        result = derive_policy_escalation(
            _payload(policy_decisions=[_policy_entry()])
        )
        assert "errors" not in result
        assert "_internal" not in result
        assert "raw_policy_decisions" not in result


# ---------------------------------------------------------------------------
# Combined scenarios
# ---------------------------------------------------------------------------

class TestCombinedScenarios:
    def test_worker_cannot_grant_itself_authority_full_scenario(self):
        """Acceptance: a worker cannot grant itself authority."""
        entry = _policy_entry(
            id="pol-bad",
            requested_by="worker",
            granted_to="worker",
            action="change_document_authority",
            decider_principal_id="worker-7",
            decider_type="worker",
        )
        result = validate_policy_escalation(
            _payload(policy_decisions=[entry])
        )
        assert not result.valid
        assert any("self-promotion" in e.lower() for e in result.errors)

    def test_browser_cannot_grant_itself_authority_full_scenario(self):
        """Acceptance: a browser cannot grant itself authority."""
        entry = _policy_entry(
            id="pol-bad",
            requested_by="browser",
            granted_to="browser",
            action="change_release_state",
            decider_principal_id="cdp-1",
            decider_type="browser",
        )
        result = validate_policy_escalation(
            _payload(policy_decisions=[entry])
        )
        assert not result.valid
        assert any("self-promotion" in e.lower() for e in result.errors)

    def test_dashboard_cannot_grant_itself_authority_full_scenario(self):
        """Acceptance: a dashboard cannot grant itself authority."""
        entry = _policy_entry(
            id="pol-bad",
            requested_by="dashboard",
            granted_to="dashboard",
            action="change_project_memory",
            decider_principal_id="dash-1",
            decider_type="dashboard",
        )
        result = validate_policy_escalation(
            _payload(policy_decisions=[entry])
        )
        assert not result.valid
        assert any("self-promotion" in e.lower() for e in result.errors)

    def test_model_score_cannot_grant_itself_authority_full_scenario(self):
        """Acceptance: a model score cannot grant itself authority."""
        entry = _policy_entry(
            id="pol-bad",
            requested_by="model_score",
            granted_to="model_score",
            action="promote_authority",
            decider_principal_id="eval-1",
            decider_type="model_score",
        )
        result = validate_policy_escalation(
            _payload(policy_decisions=[entry])
        )
        assert not result.valid
        assert any("self-promotion" in e.lower() for e in result.errors)

    def test_external_review_cannot_grant_itself_authority_full_scenario(self):
        """Acceptance: an external review cannot grant itself authority."""
        entry = _policy_entry(
            id="pol-bad",
            requested_by="external_review",
            granted_to="external_review",
            action="adopt_rule",
            decider_principal_id="gpt-1",
            decider_type="external_review",
        )
        result = validate_policy_escalation(
            _payload(policy_decisions=[entry])
        )
        assert not result.valid
        assert any("self-promotion" in e.lower() for e in result.errors)

    def test_human_escalation_names_exact_decision_full_scenario(self):
        """Acceptance: human-required states name the exact decision requested."""
        esc = _escalation(
            id="esc-prod",
            decision_requested="approve production deployment of v2.1",
            why_required="deployment requires human signoff per POL-002",
            consequence_if_declined="v2.1 remains in staging; rollback window closes in 2 hours",
        )
        result = validate_policy_escalation(
            _payload(escalations=[esc], work_items=[_work_item("wi-1")])
        )
        assert result.valid is True

        proj = derive_policy_escalation(
            _payload(escalations=[esc], work_items=[_work_item("wi-1")])
        )
        assert proj["pending_human_decisions"][0]["decision_requested"] == (
            "approve production deployment of v2.1"
        )

    def test_mixed_valid_and_invalid(self):
        entries = [
            _policy_entry(id="p1", outcome="granted"),
            _policy_entry(id="p2", outcome="denied", decider_principal_id="",
                         decider_type=""),
            _policy_entry(id="p3", requested_by="worker", granted_to="worker"),
        ]
        escalations = [
            _escalation(id="esc-1"),
            _escalation(id="esc-2", decision_requested=""),
        ]
        result = validate_policy_escalation(
            _payload(
                policy_decisions=entries,
                escalations=escalations,
                work_items=[_work_item()],
            )
        )
        assert not result.valid
        assert len(result.errors) == 2  # p3 self-promo + esc-2 missing decision

        proj = derive_policy_escalation(
            _payload(
                policy_decisions=entries,
                escalations=escalations,
                work_items=[_work_item()],
            )
        )
        assert proj["granted"] == 1
        assert proj["denied"] == 1
        assert proj["self_promotion_blocked"] == 1
        assert proj["valid_escalations"] == 1
