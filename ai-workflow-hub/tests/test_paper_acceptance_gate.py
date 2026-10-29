"""test_paper_acceptance_gate.py — A8 Paper Acceptance Gate tests.

Tests the deterministic quality gate that aggregates PaperReviewIssue[]
into PaperAcceptanceResult:
  - Status determination (all 5 statuses)
  - Issue splitting (blocking / non-blocking)
  - Privacy attestation gate
  - Human required detection
  - Degraded/unavailable warning recording
  - Schema validation
  - Multi-reviewer merge
  - Edge cases
"""

import pytest
from ai_workflow_hub.context_layer.adapters.paper_acceptance_gate import (
    compute_acceptance,
    validate_acceptance_result,
    merge_reviewer_results,
    VALID_STATUSES,
    VALID_REVIEWERS,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_issue(
    issue_id: str = "test-001",
    issue_type: str = "expression",
    severity: str = "minor",
    blocking: bool = False,
    human_required: bool = False,
    evidence: str = "test evidence",
    recommendation: str = "fix this",
    chapter: str = "引言",
    paragraph_index: int = 0,
) -> dict:
    return {
        "issue_id": issue_id,
        "issue_type": issue_type,
        "severity": severity,
        "location": {"chapter": chapter, "section": "", "paragraph_index": paragraph_index},
        "evidence": evidence,
        "recommendation": recommendation,
        "blocking": blocking,
        "human_required": human_required,
    }


def valid_attestation():
    return {"no_full_text": True, "no_api_keys": True, "no_personal_identity": True}


# ===========================================================================
# TestStatusDetermination
# ===========================================================================
class TestStatusDetermination:

    def test_accepted_when_no_issues(self):
        result = compute_acceptance(issues=[], reviewer="writelab_adapter")
        assert result["status"] == "accepted"
        assert result["blocking_issues"] == []
        assert result["non_blocking_issues"] == []

    def test_accepted_with_limitation_on_non_blocking(self):
        issues = [make_issue(severity="minor", blocking=False)]
        result = compute_acceptance(issues=issues)
        assert result["status"] == "accepted_with_limitation"
        assert len(result["non_blocking_issues"]) == 1

    def test_blocked_on_blocking_issue(self):
        issues = [
            make_issue(issue_id="wl-expr-0001", severity="major", blocking=True),
            make_issue(issue_id="wl-expr-0002", severity="minor", blocking=False),
        ]
        result = compute_acceptance(issues=issues)
        assert result["status"] == "blocked"
        assert len(result["blocking_issues"]) == 1
        assert len(result["non_blocking_issues"]) == 1

    def test_human_required_on_human_flag(self):
        issues = [make_issue(human_required=True, blocking=False)]
        result = compute_acceptance(issues=issues)
        assert result["status"] == "human_required"

    def test_needs_more_evidence_flag(self):
        result = compute_acceptance(issues=[], needs_more_evidence=True)
        assert result["status"] == "needs_more_evidence"

    def test_blocked_overrides_human_required(self):
        """Blocking issue takes priority over human_required."""
        issues = [
            make_issue(issue_id="b1", blocking=True, severity="major"),
            make_issue(issue_id="h1", human_required=True, blocking=False),
        ]
        result = compute_acceptance(issues=issues)
        assert result["status"] == "blocked"

    def test_privacy_violation_blocks_everything(self):
        """Privacy violation overrides all other statuses."""
        bad_attestation = {"no_full_text": False, "no_api_keys": True, "no_personal_identity": True}
        issues = [make_issue(severity="minor", blocking=False)]
        result = compute_acceptance(
            issues=issues,
            privacy_attestation=bad_attestation,
        )
        assert result["status"] == "blocked"
        assert any("privacy violation" in r for r in result["reasons"])


# ===========================================================================
# TestIssueSplitting
# ===========================================================================
class TestIssueSplitting:

    def test_blocking_goes_to_blocking_list(self):
        issues = [
            make_issue(issue_id="b1", blocking=True, severity="major"),
            make_issue(issue_id="b2", blocking=True, severity="critical"),
            make_issue(issue_id="nb1", blocking=False, severity="minor"),
        ]
        result = compute_acceptance(issues=issues)
        assert len(result["blocking_issues"]) == 2
        assert len(result["non_blocking_issues"]) == 1
        assert all(i["blocking"] for i in result["blocking_issues"])
        assert all(not i["blocking"] for i in result["non_blocking_issues"])

    def test_empty_issues(self):
        result = compute_acceptance(issues=[])
        assert result["blocking_issues"] == []
        assert result["non_blocking_issues"] == []


# ===========================================================================
# TestReasons
# ===========================================================================
class TestReasons:

    def test_accepted_reasons(self):
        result = compute_acceptance(issues=[])
        assert len(result["reasons"]) >= 1
        assert "no issues" in result["reasons"][0].lower()

    def test_blocked_reasons_include_count(self):
        issues = [make_issue(blocking=True, severity="major")]
        result = compute_acceptance(issues=issues)
        assert any("1 blocking" in r for r in result["reasons"])

    def test_limitation_reasons_include_severity_counts(self):
        issues = [
            make_issue(severity="minor", blocking=False),
            make_issue(issue_id="i2", severity="minor", blocking=False),
            make_issue(issue_id="i3", severity="info", blocking=False),
        ]
        result = compute_acceptance(issues=issues)
        assert any("minor=2" in r for r in result["reasons"])
        assert any("info=1" in r for r in result["reasons"])

    def test_reasons_never_empty(self):
        for status in VALID_STATUSES:
            if status == "accepted":
                result = compute_acceptance(issues=[])
            elif status == "blocked":
                result = compute_acceptance(
                    issues=[make_issue(blocking=True, severity="major")]
                )
            elif status == "human_required":
                result = compute_acceptance(
                    issues=[make_issue(human_required=True)]
                )
            elif status == "needs_more_evidence":
                result = compute_acceptance(issues=[], needs_more_evidence=True)
            elif status == "accepted_with_limitation":
                result = compute_acceptance(
                    issues=[make_issue(severity="info", blocking=False)]
                )
            assert len(result["reasons"]) >= 1, f"No reasons for status={status}"


# ===========================================================================
# TestNextActions
# ===========================================================================
class TestNextActions:

    def test_blocking_generates_actions(self):
        issues = [
            make_issue(
                issue_id="b1", blocking=True, severity="major",
                recommendation="重写段落",
            ),
        ]
        result = compute_acceptance(issues=issues)
        assert len(result["required_next_actions"]) >= 1
        assert "重写段落" in result["required_next_actions"][0]

    def test_non_blocking_generates_actions(self):
        issues = [
            make_issue(
                issue_id="nb1", blocking=False, severity="minor",
                recommendation="替换表达",
            ),
        ]
        result = compute_acceptance(issues=issues)
        assert len(result["required_next_actions"]) >= 1

    def test_no_actions_when_accepted(self):
        result = compute_acceptance(issues=[])
        assert result["required_next_actions"] == []


# ===========================================================================
# TestPrivacyGate
# ===========================================================================
class TestPrivacyGate:

    def test_valid_attestation_does_not_block(self):
        result = compute_acceptance(
            issues=[],
            privacy_attestation=valid_attestation(),
        )
        assert result["status"] == "accepted"

    def test_missing_key_blocks(self):
        result = compute_acceptance(
            issues=[],
            privacy_attestation={"no_full_text": True},  # missing 2 keys
        )
        assert result["status"] == "blocked"

    def test_false_value_blocks(self):
        result = compute_acceptance(
            issues=[],
            privacy_attestation={
                "no_full_text": True,
                "no_api_keys": False,
                "no_personal_identity": True,
            },
        )
        assert result["status"] == "blocked"
        assert any("no_api_keys" in r for r in result["reasons"])

    def test_no_attestation_skips_check(self):
        result = compute_acceptance(issues=[])
        assert result["status"] == "accepted"


# ===========================================================================
# TestDegradedWarnings
# ===========================================================================
class TestDegradedWarnings:

    def test_unavailable_warning_recorded(self):
        """WriteLab unavailable issues are recorded in reasons."""
        issues = [
            make_issue(
                issue_id="wl-unavailable-0001",
                severity="info",
                blocking=False,
                evidence="WriteLab service unavailable: connection refused",
            ),
        ]
        result = compute_acceptance(issues=issues)
        assert result["status"] == "accepted_with_limitation"
        assert any("WriteLab-unavailable" in r for r in result["reasons"])

    def test_unavailable_is_non_blocking(self):
        issues = [make_issue(issue_id="wl-unavailable-0001", severity="info", blocking=False)]
        result = compute_acceptance(issues=issues)
        assert result["status"] != "blocked"


# ===========================================================================
# TestSchemaValidation
# ===========================================================================
class TestSchemaValidation:

    def test_valid_result_passes(self):
        result = compute_acceptance(
            issues=[make_issue(blocking=True, severity="major")],
            reviewer="writelab_adapter",
            evidence_pack_ref="ep-001",
        )
        errors = validate_acceptance_result(result)
        assert errors == [], f"Unexpected errors: {errors}"

    def test_empty_result_fails(self):
        errors = validate_acceptance_result({})
        assert len(errors) >= 3  # missing status, reasons, etc.

    def test_invalid_status_fails(self):
        result = compute_acceptance(issues=[])
        result["status"] = "invalid_status"
        errors = validate_acceptance_result(result)
        assert any("invalid status" in e for e in errors)

    def test_invalid_reviewer_fails(self):
        result = compute_acceptance(issues=[])
        result["reviewer"] = "unknown"
        errors = validate_acceptance_result(result)
        assert any("invalid reviewer" in e for e in errors)

    def test_blocking_consistency_check(self):
        """blocking_issues entries must have blocking=true."""
        result = compute_acceptance(issues=[])
        # Manually inject inconsistent issue
        result["blocking_issues"] = [make_issue(blocking=False)]
        errors = validate_acceptance_result(result)
        assert any("blocking should be true" in e for e in errors)

    def test_non_blocking_consistency_check(self):
        result = compute_acceptance(issues=[])
        result["non_blocking_issues"] = [make_issue(blocking=True)]
        errors = validate_acceptance_result(result)
        assert any("blocking should be false" in e for e in errors)

    def test_all_statuses_validate(self):
        """Each status produces a valid result."""
        configs = [
            {"issues": []},
            {"issues": [make_issue(severity="info", blocking=False)]},
            {"issues": [make_issue(blocking=True, severity="major")]},
            {"issues": [make_issue(human_required=True)]},
            {"issues": [], "needs_more_evidence": True},
        ]
        for cfg in configs:
            result = compute_acceptance(**cfg)
            errors = validate_acceptance_result(result)
            assert errors == [], f"Status {result['status']} failed validation: {errors}"


# ===========================================================================
# TestReviewerField
# ===========================================================================
class TestReviewerField:

    def test_default_reviewer(self):
        result = compute_acceptance(issues=[])
        assert result["reviewer"] == "writelab_adapter"

    def test_custom_reviewer(self):
        result = compute_acceptance(issues=[], reviewer="deterministic_gate")
        assert result["reviewer"] == "deterministic_gate"

    def test_invalid_reviewer_raises(self):
        with pytest.raises(ValueError, match="Invalid reviewer"):
            compute_acceptance(issues=[], reviewer="invalid")

    def test_evidence_pack_ref(self):
        result = compute_acceptance(
            issues=[], evidence_pack_ref="ep-20260611-intro-001"
        )
        assert result["evidence_pack_ref"] == "ep-20260611-intro-001"


# ===========================================================================
# TestMultiReviewerMerge
# ===========================================================================
class TestMultiReviewerMerge:

    def test_empty_merge_returns_accepted(self):
        result = merge_reviewer_results([])
        assert result["status"] == "accepted"

    def test_all_accepted_merges_to_accepted(self):
        r1 = compute_acceptance(issues=[], reviewer="writelab_adapter")
        r2 = compute_acceptance(issues=[], reviewer="deterministic_gate")
        merged = merge_reviewer_results([r1, r2])
        assert merged["status"] == "accepted"

    def test_one_blocked_merges_to_blocked(self):
        r1 = compute_acceptance(issues=[], reviewer="writelab_adapter")
        r2 = compute_acceptance(
            issues=[make_issue(blocking=True, severity="major")],
            reviewer="deterministic_gate",
        )
        merged = merge_reviewer_results([r1, r2])
        assert merged["status"] == "blocked"

    def test_issues_concatenated(self):
        r1 = compute_acceptance(
            issues=[make_issue(issue_id="a1", severity="info", blocking=False)],
            reviewer="writelab_adapter",
        )
        r2 = compute_acceptance(
            issues=[make_issue(issue_id="b1", severity="minor", blocking=False)],
            reviewer="deterministic_gate",
        )
        merged = merge_reviewer_results([r1, r2])
        assert len(merged["non_blocking_issues"]) == 2

    def test_human_required_priority(self):
        r1 = compute_acceptance(issues=[], reviewer="writelab_adapter")
        r2 = compute_acceptance(
            issues=[make_issue(human_required=True)],
            reviewer="human",
        )
        merged = merge_reviewer_results([r1, r2])
        assert merged["status"] == "human_required"

    def test_blocked_beats_human_required(self):
        r1 = compute_acceptance(
            issues=[make_issue(human_required=True)],
            reviewer="human",
        )
        r2 = compute_acceptance(
            issues=[make_issue(blocking=True, severity="major")],
            reviewer="deterministic_gate",
        )
        merged = merge_reviewer_results([r1, r2])
        assert merged["status"] == "blocked"

    def test_merged_result_validates(self):
        r1 = compute_acceptance(
            issues=[make_issue(severity="info", blocking=False)],
            reviewer="writelab_adapter",
            evidence_pack_ref="ep-001",
        )
        r2 = compute_acceptance(
            issues=[make_issue(issue_id="b1", blocking=True, severity="major")],
            reviewer="deterministic_gate",
        )
        merged = merge_reviewer_results([r1, r2])
        errors = validate_acceptance_result(merged)
        assert errors == [], f"Merged result invalid: {errors}"


# ===========================================================================
# TestEdgeCases
# ===========================================================================
class TestEdgeCases:

    def test_many_issues_performance(self):
        """100 issues should not crash."""
        issues = [make_issue(issue_id=f"i-{i:04d}", severity="info", blocking=False) for i in range(100)]
        result = compute_acceptance(issues=issues)
        assert result["status"] == "accepted_with_limitation"
        assert len(result["non_blocking_issues"]) == 100

    def test_mixed_severity_non_blocking(self):
        issues = [
            make_issue(issue_id="c1", severity="critical", blocking=False),
            make_issue(issue_id="m1", severity="major", blocking=False),
            make_issue(issue_id="mi1", severity="minor", blocking=False),
            make_issue(issue_id="i1", severity="info", blocking=False),
        ]
        result = compute_acceptance(issues=issues)
        assert result["status"] == "accepted_with_limitation"
        # Actions should be sorted by severity (critical first)
        assert "critical" in result["required_next_actions"][0]

    def test_empty_recommendation_skipped(self):
        issues = [make_issue(severity="minor", blocking=False, recommendation="")]
        result = compute_acceptance(issues=issues)
        assert result["required_next_actions"] == []
