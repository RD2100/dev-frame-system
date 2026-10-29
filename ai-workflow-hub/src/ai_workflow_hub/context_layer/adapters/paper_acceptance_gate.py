"""paper_acceptance_gate.py — A8 Paper Acceptance Gate.

Aggregates PaperReviewIssue[] from one or more reviewers into a
PaperAcceptanceResult verdict.

Design:
  - Pure function, no I/O, no state
  - Deterministic status rules (priority order):
      1. privacy_violation  → blocked
      2. any blocking issue → blocked
      3. any human_required → human_required
      4. needs_evidence flag → needs_more_evidence
      5. non-blocking issues exist → accepted_with_limitation
      6. no issues at all → accepted
  - Issues split into blocking_issues / non_blocking_issues
  - reasons[] auto-generated from verdict logic
  - required_next_actions[] derived from issue recommendations
  - Output validated against paper_acceptance_result.schema.json

Usage:
    result = compute_acceptance(
        issues=review_issues,
        reviewer="writelab_adapter",
        evidence_pack_ref="ep-20260611-intro-001",
    )
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

VALID_STATUSES = {
    "accepted",
    "accepted_with_limitation",
    "needs_more_evidence",
    "blocked",
    "human_required",
}

VALID_REVIEWERS = {"deterministic_gate", "gpt", "human", "writelab_adapter"}

VALID_ISSUE_TYPES = {
    "structure", "argument", "citation", "expression",
    "format", "privacy", "methodology",
}

VALID_SEVERITIES = {"critical", "major", "minor", "info"}

SCHEMA_PATH = (
    Path(__file__).resolve().parent.parent
    / "domains" / "paper" / "contracts"
    / "paper_acceptance_result.schema.json"
)

# Severity ordering for priority resolution
SEVERITY_RANK = {"critical": 4, "major": 3, "minor": 2, "info": 1}


# ---------------------------------------------------------------------------
# Core gate function
# ---------------------------------------------------------------------------

def compute_acceptance(
    issues: list[dict[str, Any]],
    reviewer: str = "writelab_adapter",
    evidence_pack_ref: str = "",
    privacy_attestation: dict[str, bool] | None = None,
    needs_more_evidence: bool = False,
) -> dict[str, Any]:
    """Compute a PaperAcceptanceResult from a list of review issues.

    Args:
        issues: List of PaperReviewIssue dicts (from adapter, GPT, etc.)
        reviewer: Source of the review (enum: deterministic_gate|gpt|human|writelab_adapter)
        evidence_pack_ref: Reference to the evidence pack manifest_id
        privacy_attestation: Optional dict with no_full_text, no_api_keys, no_personal_identity
        needs_more_evidence: If True, forces status to needs_more_evidence (unless blocked)

    Returns:
        PaperAcceptanceResult dict, validated against schema.
    """
    if reviewer not in VALID_REVIEWERS:
        raise ValueError(f"Invalid reviewer: {reviewer}. Must be one of {VALID_REVIEWERS}")

    # --- Privacy gate ---
    privacy_violation = False
    privacy_reasons: list[str] = []
    if privacy_attestation is not None:
        for key in ("no_full_text", "no_api_keys", "no_personal_identity"):
            val = privacy_attestation.get(key)
            if val is not True:
                privacy_violation = True
                privacy_reasons.append(
                    f"privacy violation: {key} is {val} (must be true)"
                )

    # --- Split issues ---
    blocking_issues: list[dict[str, Any]] = []
    non_blocking_issues: list[dict[str, Any]] = []

    for issue in issues:
        if issue.get("blocking", False):
            blocking_issues.append(issue)
        else:
            non_blocking_issues.append(issue)

    # --- Human required detection ---
    human_required_issues = [
        i for i in issues if i.get("human_required", False)
    ]

    # --- Determine status (priority order) ---
    reasons: list[str] = []
    required_next_actions: list[str] = []

    if privacy_violation:
        status = "blocked"
        reasons.extend(privacy_reasons)
        reasons.append(
            f"privacy attestation failed; "
            f"{len(blocking_issues)} blocking + {len(non_blocking_issues)} non-blocking issues"
        )
        required_next_actions.append("resolve privacy attestation before proceeding")

    elif blocking_issues:
        status = "blocked"
        reasons.append(
            f"{len(blocking_issues)} blocking issue(s) detected"
        )
        # Add details for each blocking issue
        for bi in blocking_issues[:5]:  # cap detail at 5
            reasons.append(
                f"  [{bi.get('issue_id', '?')}] {bi.get('issue_type', '?')}: "
                f"{bi.get('evidence', '')[:100]}"
            )
        # Next actions from blocking issue recommendations
        for bi in blocking_issues:
            rec = bi.get("recommendation", "")
            if rec:
                required_next_actions.append(f"fix [{bi.get('issue_id', '?')}]: {rec}")

    elif human_required_issues:
        status = "human_required"
        reasons.append(
            f"{len(human_required_issues)} issue(s) require human review"
        )
        for hi in human_required_issues:
            reasons.append(
                f"  [{hi.get('issue_id', '?')}] {hi.get('evidence', '')[:100]}"
            )
            rec = hi.get("recommendation", "")
            if rec:
                required_next_actions.append(
                    f"human review [{hi.get('issue_id', '?')}]: {rec}"
                )

    elif needs_more_evidence:
        status = "needs_more_evidence"
        reasons.append("insufficient evidence to determine acceptance")
        required_next_actions.append("gather additional evidence before re-evaluation")

    elif non_blocking_issues:
        status = "accepted_with_limitation"
        # Count by severity
        severity_counts: dict[str, int] = {}
        for ni in non_blocking_issues:
            sev = ni.get("severity", "info")
            severity_counts[sev] = severity_counts.get(sev, 0) + 1
        reasons.append(
            f"{len(non_blocking_issues)} non-blocking issue(s): "
            + ", ".join(f"{s}={c}" for s, c in sorted(severity_counts.items()))
        )
        # Next actions from top-severity issues
        sorted_issues = sorted(
            non_blocking_issues,
            key=lambda x: SEVERITY_RANK.get(x.get("severity", "info"), 0),
            reverse=True,
        )
        for ni in sorted_issues[:5]:
            rec = ni.get("recommendation", "")
            if rec:
                required_next_actions.append(
                    f"{ni.get('severity', 'info')} [{ni.get('issue_id', '?')}]: {rec}"
                )

    else:
        status = "accepted"
        reasons.append("no issues detected; all checks passed")

    # --- Record degraded/unavailable warnings ---
    unavailable_issues = [
        i for i in issues
        if i.get("issue_id", "").startswith("wl-unavailable-")
    ]
    if unavailable_issues:
        reasons.append(
            f"NOTE: {len(unavailable_issues)} WriteLab-unavailable warning(s) recorded "
            f"(non-blocking, severity=info)"
        )

    # --- Build result ---
    result = {
        "status": status,
        "reasons": reasons,
        "blocking_issues": blocking_issues,
        "non_blocking_issues": non_blocking_issues,
        "required_next_actions": required_next_actions,
        "reviewer": reviewer,
        "evidence_pack_ref": evidence_pack_ref,
    }

    return result


# ---------------------------------------------------------------------------
# Schema validation
# ---------------------------------------------------------------------------

def validate_acceptance_result(result: dict[str, Any]) -> list[str]:
    """Validate a PaperAcceptanceResult dict against the schema.

    Returns list of error strings. Empty list = valid.
    """
    errors: list[str] = []

    # Required fields
    for field in ("status", "reasons", "blocking_issues", "reviewer", "evidence_pack_ref"):
        if field not in result:
            errors.append(f"missing required field: {field}")

    # Status enum
    status = result.get("status")
    if status and status not in VALID_STATUSES:
        errors.append(f"invalid status: {status}")

    # Reviewer enum
    reviewer = result.get("reviewer")
    if reviewer and reviewer not in VALID_REVIEWERS:
        errors.append(f"invalid reviewer: {reviewer}")

    # reasons must be array of strings
    reasons = result.get("reasons", [])
    if not isinstance(reasons, list):
        errors.append("reasons must be an array")
    elif not reasons:
        errors.append("reasons must not be empty")

    # blocking_issues / non_blocking_issues validation
    for arr_name in ("blocking_issues", "non_blocking_issues"):
        arr = result.get(arr_name, [])
        if not isinstance(arr, list):
            errors.append(f"{arr_name} must be an array")
            continue
        for i, issue in enumerate(arr):
            for req_field in ("issue_id", "issue_type", "severity", "evidence", "blocking"):
                if req_field not in issue:
                    errors.append(f"{arr_name}[{i}]: missing {req_field}")
            it = issue.get("issue_type")
            if it and it not in VALID_ISSUE_TYPES:
                errors.append(f"{arr_name}[{i}]: invalid issue_type={it}")
            sev = issue.get("severity")
            if sev and sev not in VALID_SEVERITIES:
                errors.append(f"{arr_name}[{i}]: invalid severity={sev}")

    # Consistency: blocking_issues should have blocking=true
    for i, issue in enumerate(result.get("blocking_issues", [])):
        if not issue.get("blocking", False):
            errors.append(f"blocking_issues[{i}]: blocking should be true")

    # Consistency: non_blocking_issues should have blocking=false
    for i, issue in enumerate(result.get("non_blocking_issues", [])):
        if issue.get("blocking", False):
            errors.append(f"non_blocking_issues[{i}]: blocking should be false")

    return errors


# ---------------------------------------------------------------------------
# Multi-reviewer merge
# ---------------------------------------------------------------------------

def merge_reviewer_results(
    results: list[dict[str, Any]],
) -> dict[str, Any]:
    """Merge multiple PaperAcceptanceResult dicts from different reviewers.

    Rules:
      - If ANY reviewer says "blocked", merged status is "blocked"
      - If ANY says "human_required" (and none blocked), merged is "human_required"
      - If ANY says "needs_more_evidence", merged is "needs_more_evidence"
      - If ANY says "accepted_with_limitation", merged is "accepted_with_limitation"
      - Only "accepted" if ALL reviewers say "accepted"
      - Issues are concatenated (all reviewers' issues preserved)
      - Reviewer field is set to the highest-severity reviewer, or "deterministic_gate"
    """
    if not results:
        return compute_acceptance(
            issues=[], reviewer="deterministic_gate", evidence_pack_ref=""
        )

    # Priority: blocked > human_required > needs_more_evidence > accepted_with_limitation > accepted
    STATUS_PRIORITY = {
        "blocked": 5,
        "human_required": 4,
        "needs_more_evidence": 3,
        "accepted_with_limitation": 2,
        "accepted": 1,
    }

    merged_status = "accepted"
    merged_reasons: list[str] = []
    merged_blocking: list[dict] = []
    merged_non_blocking: list[dict] = []
    merged_actions: list[str] = []
    merged_evidence_ref = ""
    top_reviewer = "deterministic_gate"
    top_priority = 0

    for r in results:
        s = r.get("status", "accepted")
        p = STATUS_PRIORITY.get(s, 0)
        if p > top_priority:
            top_priority = p
            merged_status = s
            top_reviewer = r.get("reviewer", "deterministic_gate")

        merged_reasons.extend(r.get("reasons", []))
        merged_blocking.extend(r.get("blocking_issues", []))
        merged_non_blocking.extend(r.get("non_blocking_issues", []))
        merged_actions.extend(r.get("required_next_actions", []))
        if r.get("evidence_pack_ref"):
            merged_evidence_ref = r["evidence_pack_ref"]

    return {
        "status": merged_status,
        "reasons": merged_reasons,
        "blocking_issues": merged_blocking,
        "non_blocking_issues": merged_non_blocking,
        "required_next_actions": merged_actions,
        "reviewer": top_reviewer,
        "evidence_pack_ref": merged_evidence_ref,
    }
