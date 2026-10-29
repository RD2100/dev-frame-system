#!/usr/bin/env python3
"""
ai_guard.py — Synthesize final_batch_status from run artifacts.

Deterministic fail-closed synthesis. Reads chain-evidence.json, review.yaml,
and other run artifacts to produce a unique final_batch_status with
structured blocked_by entries.

Usage:
  python tools/ai_guard.py <run_dir>
  python tools/ai_guard.py <run_dir> --output json
  python tools/ai_guard.py <run_dir> --output markdown
  python tools/ai_guard.py <run_dir> --validate
  python tools/ai_guard.py <run_dir> --generate-report

Exit codes: 0 = pass, 1 = blocked, 2 = error
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Optional

import yaml

# ── legal enum values ──────────────────────────────────────────────

VALID_BLOCK_CATEGORIES = {
    "policy/blocking",
    "workspace/blocking",
    "artifact/blocking",
    "review/blocking",
    "infra/blocking",
}

VALID_BLOCK_REASONS = {
    "TaskSpec_boundary",
    "human_required",
    "new_dirty_change",
    "schema_invalid",
    "evidence_missing",
    "review_artifact_missing",
    "reviewer_invalid",
    "reviewer_rejected",
    "reviewer_timeout",
    "unknown_status",
    "unparseable_report",
}

# Which reasons belong to which category
REASON_TO_CATEGORY = {
    "TaskSpec_boundary":      "policy/blocking",
    "human_required":         "policy/blocking",
    "new_dirty_change":       "workspace/blocking",
    "schema_invalid":         "artifact/blocking",
    "evidence_missing":       "artifact/blocking",
    "review_artifact_missing":"artifact/blocking",
    "reviewer_invalid":       "review/blocking",
    "reviewer_rejected":      "review/blocking",
    "reviewer_timeout":       "review/blocking",
    "unknown_status":         "infra/blocking",
    "unparseable_report":     "infra/blocking",
}


# ── file readers ────────────────────────────────────────────────────

def read_json(path: Path) -> Optional[dict]:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (json.JSONDecodeError, UnicodeDecodeError, OSError):
        return None


def read_yaml(path: Path) -> Optional[dict]:
    if not path.exists():
        return None
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8"))
    except (yaml.YAMLError, UnicodeDecodeError, OSError):
        return None


def read_text(path: Path) -> Optional[str]:
    if not path.exists():
        return None
    try:
        return path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return None


# ── extractors ──────────────────────────────────────────────────────

def extract_guard_result(run_dir: Path) -> tuple:
    """
    Determine guard_result from chain-evidence.json and task-spec.yaml.

    Returns (guard_result: str, blocked_by: list[dict]).
    guard_result values: pass | blocked | not_applicable
    """
    blocked = []
    chain = read_json(run_dir / "chain-evidence.json")

    # No chain-evidence -> no dispatch record
    if chain is None:
        return ("blocked", [_block("evidence_missing")])

    # Explicit preflight block marker
    if chain.get("preflight_blocked"):
        return ("blocked", [_block("TaskSpec_boundary")])

    # Verify-boundary exit 69 marker (from m4-l13 pattern)
    if chain.get("verify_boundary_exit_code") == 69:
        return ("blocked", [_block("TaskSpec_boundary")])

    # Guard gates in chain-evidence
    guard_gates = chain.get("guard_gates", None)
    if guard_gates is not None and isinstance(guard_gates, dict):
        if guard_gates.get("verify_deny_check") == "blocked":
            return ("blocked", [_block("TaskSpec_boundary")])
        if guard_gates.get("human_required_override") == "blocked":
            return ("blocked", [_block("human_required")])

    # Has task_id -> dispatch completed, guard pass
    if chain.get("task_id"):
        return ("pass", [])

    return ("pass", [])


def extract_evidence_status(run_dir: Path) -> tuple:
    """
    Determine evidence_status from available artifacts.

    Returns (evidence_status: str, blocked_by: list[dict]).
    evidence_status values: pass | missing | fail
    """
    blocked = []
    chain = read_json(run_dir / "chain-evidence.json")
    state = read_json(run_dir / "state.json")

    # No artifacts at all
    if chain is None and state is None:
        return ("missing", [_block("evidence_missing")])

    # chain-evidence schema validation
    if chain is not None:
        if not chain.get("run_id") and not chain.get("task_id"):
            return ("fail", [_block("schema_invalid")])

    # state.json evidence_ok check
    if state is not None:
        if state.get("evidence_ok") is False:
            return ("fail", [_block("schema_invalid")])

    # Evidence artifacts present and valid -> pass
    return ("pass", [])


def extract_reviewer_verdict(run_dir: Path) -> tuple:
    """
    Extract reviewer_verdict from review.yaml.

    Returns (reviewer_verdict: str, blocked_by: list[dict]).
    Values: pass | reviewer_rejected | reviewer_invalid | reviewer_timeout | not_applicable

    Distinguishes reviewer_invalid vs reviewer_rejected vs reviewer_timeout:
      - review.yaml missing entirely, no review artifacts -> reviewer_timeout
      - review.yaml present but unparseable -> reviewer_invalid
      - review.yaml valid but verdict is fail/blocked -> reviewer_rejected
      - review.yaml valid with verdict=pass -> pass
    """
    blocked = []
    review = read_yaml(run_dir / "review.yaml")

    # No review.yaml at all
    if review is None:
        review_md = read_text(run_dir / "review.md")
        review_issues = read_json(run_dir / "review-issues.json")
        if review_md is None and review_issues is None:
            return ("reviewer_timeout", [_block("reviewer_timeout")])
        # Has some review artifacts but no review.yaml -> invalid
        return ("reviewer_invalid", [_block("reviewer_invalid")])

    # Not a dict -> invalid
    if not isinstance(review, dict):
        return ("reviewer_invalid", [_block("reviewer_invalid")])

    # ── Format A: model-parsed review.yaml ──
    # {"passed": bool, "recommendation": "block_finalizer"|"proceed"|...}
    if "passed" in review:
        if review["passed"] is False:
            return ("reviewer_rejected", [_block("reviewer_rejected")])
        if review.get("recommendation") == "block_finalizer":
            return ("reviewer_rejected", [_block("reviewer_rejected")])
        if review["passed"] is True:
            return ("pass", [])
        # passed field present but not bool -> reviewer_invalid
        return ("reviewer_invalid", [_block("reviewer_invalid")])

    # ── Format B: human-written review.yaml ──
    # {"verdict": "pass"|"fail"|"blocked", "findings": [...]}
    if "verdict" in review:
        verdict = review["verdict"]
        if verdict == "pass":
            return ("pass", [])
        if verdict in ("fail", "blocked", "rejected", "block_finalizer"):
            return ("reviewer_rejected", [_block("reviewer_rejected")])
        # Unknown verdict string -> invalid
        return ("reviewer_invalid", [_block("reviewer_invalid")])

    # Has review.yaml but no recognized verdict field -> invalid
    return ("reviewer_invalid", [_block("reviewer_invalid")])


def extract_workspace_status(run_dir: Path) -> tuple:
    """
    Check for workspace-level blocking (e.g., dirty changes not in allow_write).
    Returns (workspace_ok: bool, blocked_by: list[dict]).
    """
    blocked = []
    state = read_json(run_dir / "state.json")
    if state is not None and state.get("new_dirty_change"):
        return ("blocked", [_block("new_dirty_change")])
    # In the tools layer we don't run git status — check state.json markers
    return ("pass", [])


def extract_human_required(run_dir: Path) -> tuple:
    """
    Determine human_required from run artifacts.

    Returns (human_required: bool, blocked_by: list[dict]).
    human_required=True with no explicit approval → policy/blocking.

    Sources checked (in order):
      1. state.json → human_required flag
      2. chain-evidence.json → guard_gates.human_required_override
      3. human-gate.md → resume/pending indicator
    """
    blocked = []
    human_required = False

    # state.json human_required flag
    state = read_json(run_dir / "state.json")
    if state is not None and state.get("human_required") is True:
        human_required = True

    # chain-evidence guard_gates override
    chain = read_json(run_dir / "chain-evidence.json")
    if chain is not None:
        guard_gates = chain.get("guard_gates", None)
        if guard_gates is not None and isinstance(guard_gates, dict):
            if guard_gates.get("human_required_override") == "blocked":
                human_required = True

    # human-gate.md existence with no approval marker
    hg_md = read_text(run_dir / "human-gate.md")
    if hg_md is not None:
        if "**Decision**: approved" not in hg_md and "**Decision**: rejected" not in hg_md:
            human_required = True

    if human_required:
        blocked = [_block("human_required")]

    return (human_required, blocked)


# ── helper ──────────────────────────────────────────────────────────

def _block(reason: str) -> dict:
    """Build a blocked_by entry, inferring category from reason."""
    category = REASON_TO_CATEGORY.get(reason, "artifact/blocking")
    return {"category": category, "reason": reason}


# ── synthesis engine ────────────────────────────────────────────────

def synthesize(run_dir: Path) -> dict:
    """
    Apply deterministic fail-closed synthesis rules.

    Priority order (first match wins, all fail-closed):
      1. policy/blocking    -> blocked
      2. workspace/blocking -> blocked
      3. artifact/blocking  -> blocked
      4. review/blocking    -> blocked
      5. infra/blocking     -> blocked
      6. guard=pass AND evidence=pass AND reviewer=pass
         AND human_required=false AND blocked_by=[] -> pass
      7. Everything else    -> blocked (fail-closed: can't prove pass)

    human_required=true without explicit approval → blocked.
    unknown/missing/invalid/timeout statuses → fail-closed as blocked.
    """
    guard_result, guard_blocked = extract_guard_result(run_dir)
    evidence_status, evidence_blocked = extract_evidence_status(run_dir)
    reviewer_verdict, reviewer_blocked = extract_reviewer_verdict(run_dir)
    workspace_status, workspace_blocked = extract_workspace_status(run_dir)
    human_required, human_blocked = extract_human_required(run_dir)

    all_blocked = guard_blocked + workspace_blocked + evidence_blocked + reviewer_blocked + human_blocked

    has_policy    = any(b["category"] == "policy/blocking"    for b in all_blocked)
    has_workspace = any(b["category"] == "workspace/blocking" for b in all_blocked)
    has_artifact  = any(b["category"] == "artifact/blocking"  for b in all_blocked)
    has_review    = any(b["category"] == "review/blocking"    for b in all_blocked)
    has_infra     = any(b["category"] == "infra/blocking"     for b in all_blocked)

    # Fail-closed: unknown/missing/invalid guard/evidence/reviewer statuses
    if guard_result not in ("pass", "blocked", "not_applicable"):
        all_blocked.append(_block("unknown_status"))
        has_infra = True
    if evidence_status not in ("pass", "missing", "fail"):
        all_blocked.append(_block("unknown_status"))
        has_infra = True
    if reviewer_verdict not in ("pass", "reviewer_rejected", "reviewer_invalid",
                                 "reviewer_timeout", "not_applicable"):
        all_blocked.append(_block("unknown_status"))
        has_infra = True

    # Priority-ordered fail-closed synthesis
    if has_policy:
        final_batch_status = "blocked"
    elif has_workspace:
        final_batch_status = "blocked"
    elif has_artifact:
        final_batch_status = "blocked"
    elif has_review:
        final_batch_status = "blocked"
    elif has_infra:
        final_batch_status = "blocked"
    elif (guard_result == "pass" and evidence_status == "pass"
          and reviewer_verdict == "pass" and human_required is False):
        final_batch_status = "pass"
        all_blocked = []
    else:
        # Fail-closed: cannot prove pass
        final_batch_status = "blocked"
        if not all_blocked:
            all_blocked = [_block("unknown_status")]

    # Deduplicate blocked_by entries (same category + reason)
    seen = set()
    unique_blocked = []
    for b in all_blocked:
        key = (b["category"], b["reason"])
        if key not in seen:
            seen.add(key)
            unique_blocked.append(b)

    return {
        "final_batch_status": final_batch_status,
        "blocked_by": unique_blocked,
        "source_status": {
            "guard_result": guard_result,
            "evidence_status": evidence_status,
            "reviewer_verdict": reviewer_verdict,
            "human_required": human_required,
        },
    }


# ── report generation ───────────────────────────────────────────────

def generate_report(result: dict, run_dir: Path) -> str:
    """Generate final-report.md with unique status block at top."""
    lines = []
    status = result["final_batch_status"]
    blocked_by = result.get("blocked_by", [])
    source = result.get("source_status", {})

    # ── Unique machine-readable status block at top ──
    lines.append("final_batch_status: " + status)
    if blocked_by:
        lines.append("blocked_by:")
        for b in blocked_by:
            lines.append("  - category: " + b["category"])
            lines.append("    reason: " + b["reason"])
    else:
        lines.append("blocked_by: []")
    lines.append("source_status:")
    lines.append("  guard_result: " + source.get("guard_result", "unknown"))
    lines.append("  evidence_status: " + source.get("evidence_status", "unknown"))
    lines.append("  reviewer_verdict: " + source.get("reviewer_verdict", "unknown"))
    lines.append("  human_required: " + str(source.get("human_required", False)).lower())
    lines.append("")
    lines.append("---")
    lines.append("")

    # ── Human-readable sections ──
    lines.append("# Final Report")
    lines.append("")
    lines.append("## Status")
    lines.append("")
    lines.append(status)
    lines.append("")

    if blocked_by:
        lines.append("## Blocked By")
        lines.append("")
        for b in blocked_by:
            lines.append("- **" + b["category"] + "**: " + b["reason"])
        lines.append("")

    lines.append("## Source Status")
    lines.append("")
    lines.append("| Field | Value |")
    lines.append("|-------|-------|")
    lines.append("| guard_result | " + source.get("guard_result", "unknown") + " |")
    lines.append("| evidence_status | " + source.get("evidence_status", "unknown") + " |")
    lines.append("| reviewer_verdict | " + source.get("reviewer_verdict", "unknown") + " |")
    lines.append("| human_required | " + str(source.get("human_required", False)).lower() + " |")
    lines.append("| final_batch_status | **" + status + "** |")
    lines.append("")

    return "\n".join(lines)


def validate_result(result: dict) -> list[str]:
    """Validate blocked_by entries against legal enums AND cross-field consistency."""
    errors = []
    for b in result.get("blocked_by", []):
        if b["category"] not in VALID_BLOCK_CATEGORIES:
            errors.append("Invalid blocked_by category: " + b["category"] + " (valid: " + ", ".join(sorted(VALID_BLOCK_CATEGORIES)) + ")")
        if b["reason"] not in VALID_BLOCK_REASONS:
            errors.append("Invalid blocked_by reason: " + b["reason"] + " (valid: " + ", ".join(sorted(VALID_BLOCK_REASONS)) + ")")

    # Final consistency: blocked must have non-empty blocked_by
    if result["final_batch_status"] == "blocked" and not result.get("blocked_by"):
        errors.append("final_batch_status=blocked but blocked_by is empty — violates invariant")

    # Final consistency: pass must have empty blocked_by
    if result["final_batch_status"] == "pass" and result.get("blocked_by"):
        errors.append("final_batch_status=pass but blocked_by is non-empty — violates invariant")

    # S1 cross-field: pass requires ALL source gates to be pass
    source = result.get("source_status", {})
    if result["final_batch_status"] == "pass":
        if source.get("guard_result") != "pass":
            errors.append("final_batch_status=pass but guard_result=" + str(source.get("guard_result")) + " — must be 'pass' per S1 synthesis rule")
        if source.get("evidence_status") != "pass":
            errors.append("final_batch_status=pass but evidence_status=" + str(source.get("evidence_status")) + " — must be 'pass' per S1 synthesis rule")
        if source.get("reviewer_verdict") != "pass":
            errors.append("final_batch_status=pass but reviewer_verdict=" + str(source.get("reviewer_verdict")) + " — must be 'pass' per S1 synthesis rule")
        if source.get("human_required") is not False:
            errors.append("final_batch_status=pass but human_required=" + str(source.get("human_required")) + " — must be false per S1 synthesis rule")

    return errors


# ── evidence / reviewer index generation (S2) ──────────────────────

def generate_evidence_index(result: dict) -> str:
    """
    Generate evidence-index.md.

    CRITICAL: evidence_status describes evidence package structural validity ONLY.
    It does NOT imply final_batch_status. The evidence index MUST NOT contain
    any language suggesting batch success/failure — that is the sole domain of
    final_batch_status from the synthesis rule.

    Returns machine-readable YAML block at top, followed by human-readable section.
    """
    source = result.get("source_status", {})
    evidence_status = source.get("evidence_status", "unknown")
    fbs = result.get("final_batch_status", "unknown")
    blocked_by = result.get("blocked_by", [])

    lines = []
    # ── Machine-readable block ──
    lines.append("evidence_status: " + evidence_status)
    lines.append("# NOTE: evidence_status describes evidence package STRUCTURAL validity only.")
    lines.append("# It does NOT indicate batch success. See final-report.md for final_batch_status.")
    lines.append("final_batch_status: " + fbs + "  # from synthesis rule, NOT from evidence_status")
    lines.append("")
    lines.append("---")
    lines.append("")

    # ── Human-readable section ──
    lines.append("# Evidence Index")
    lines.append("")
    lines.append("## Evidence Package Status")
    lines.append("")
    lines.append("| Field | Value | Meaning |")
    lines.append("|-------|-------|---------|")
    lines.append("| evidence_status | " + evidence_status + " | Structural validity of evidence files |")
    lines.append("| final_batch_status | **" + fbs + "** | Authoritative batch status (from synthesis rule) |")
    lines.append("")
    lines.append("## Important Distinction")
    lines.append("")
    lines.append("- **evidence_status=pass**: Evidence files are present and structurally valid.")
    lines.append("- **evidence_status=pass does NOT mean the batch passed.**")
    lines.append("- **final_batch_status** is the single authoritative final status.")
    lines.append("- Evidence is ONE of FOUR gates (guard, evidence, reviewer, human_required).")
    lines.append("")

    if evidence_status != "pass":
        lines.append("## Evidence Issues")
        lines.append("")
        reasons = [b["reason"] for b in blocked_by if b["category"] == "artifact/blocking"]
        if reasons:
            for r in reasons:
                lines.append("- **artifact/blocking**: " + r)
        else:
            lines.append("- Evidence status is `" + evidence_status + "` — structural check did not pass.")
        lines.append("")

    return "\n".join(lines)


def generate_reviewer_index(result: dict) -> str:
    """
    Generate reviewer-index.md.

    CRITICAL: reviewer_verdict describes the reviewer's independent judgment ONLY.
    It does NOT imply final_batch_status. The reviewer-index MUST clearly
    distinguish reviewer_verdict from final_batch_status.

    - reviewer_verdict=pass does NOT mean the batch passed
    - reviewer_invalid/reviewer_rejected/reviewer_timeout → review/blocking
    - final_batch_status is the sole authoritative final status
    """
    source = result.get("source_status", {})
    reviewer_verdict = source.get("reviewer_verdict", "unknown")
    fbs = result.get("final_batch_status", "unknown")
    blocked_by = result.get("blocked_by", [])

    lines = []
    # ── Machine-readable block ──
    lines.append("reviewer_verdict: " + reviewer_verdict)
    lines.append("# NOTE: reviewer_verdict is the reviewer's independent judgment ONLY.")
    lines.append("# reviewer_verdict=pass does NOT mean the batch passed.")
    lines.append("# See final-report.md for authoritative final_batch_status.")
    lines.append("final_batch_status: " + fbs + "  # from synthesis rule")
    lines.append("")
    lines.append("---")
    lines.append("")

    # ── Reviewer verdict classification ──
    verdict_map = {
        "pass": "Reviewer approved the changes",
        "reviewer_rejected": "Reviewer rejected the changes",
        "reviewer_invalid": "Reviewer output is present but unparseable/invalid",
        "reviewer_timeout": "No reviewer artifact was produced (timeout)",
        "not_applicable": "Reviewer step was not applicable for this run",
    }
    verdict_desc = verdict_map.get(reviewer_verdict, "Unknown reviewer state")

    lines.append("# Reviewer Index")
    lines.append("")
    lines.append("## Reviewer Verdict")
    lines.append("")
    lines.append("| Field | Value | Meaning |")
    lines.append("|-------|-------|---------|")
    lines.append("| reviewer_verdict | " + reviewer_verdict + " | " + verdict_desc + " |")
    lines.append("| final_batch_status | **" + fbs + "** | Authoritative batch status (from synthesis rule) |")
    lines.append("")

    # ── Key distinction ──
    lines.append("## Important Distinction")
    lines.append("")
    lines.append("- **reviewer_verdict** = the reviewer's independent judgment of code quality")
    lines.append("- **final_batch_status** = the authoritative batch result (from S1 synthesis rule)")
    lines.append("- **reviewer_verdict=pass ≠ final_batch_status=pass**")
    lines.append("- Reviewer is ONE of FOUR gates. All four must pass for final_batch_status=pass.")
    lines.append("")

    # ── Blocking details ──
    review_blocked = [b for b in blocked_by if b["category"] == "review/blocking"]
    artifact_blocked = [b for b in blocked_by if b["reason"] == "review_artifact_missing"]

    if review_blocked or artifact_blocked:
        lines.append("## Review Blocking Reasons")
        lines.append("")
        for b in review_blocked:
            lines.append("- **" + b["category"] + "**: " + b["reason"])
        for b in artifact_blocked:
            lines.append("- **" + b["category"] + "**: " + b["reason"])
        lines.append("")

    # ── Exec checklist ──
    lines.append("## Execution Checklist")
    lines.append("")
    lines.append("| # | Item | Status |")
    lines.append("|---|------|--------|")
    lines.append("| 1 | reviewer_verdict distinguished from final_batch_status | yes |")
    lines.append("| 2 | reviewer pass does not override guard/evidence/human_required blocks | yes |")
    lines.append("| 3 | reviewer invalid/rejected/timeout produces review/blocking | yes |")
    lines.append("| 4 | final_batch_status from synthesis rule only | yes |")
    lines.append("")

    return "\n".join(lines)


def validate_cross_report_consistency(synthesis_result: dict,
                                      evidence_index: str = "",
                                      reviewer_index: str = "",
                                      final_report: str = "") -> dict:
    """
    Validate that evidence-index, reviewer-index, and final-report are consistent
    with each other and with the S1 synthesis rule.

    Returns:
        dict with:
          - consistency_status: "pass" | "blocked"
          - consistency_errors: list[str]
          - all_reports_consistent: bool

    Checks:
      1. evidence-index does not imply batch success (no unqualified "PASS")
      2. reviewer-index distinguishes reviewer_verdict from final_batch_status
      3. final-report has exactly one final_batch_status
      4. No semantic conflicts between the three reports
    """
    errors = []
    source = synthesis_result.get("source_status", {})
    fbs = synthesis_result.get("final_batch_status", "unknown")
    blocked_by = synthesis_result.get("blocked_by", [])
    evidence_status = source.get("evidence_status", "unknown")
    reviewer_verdict = source.get("reviewer_verdict", "unknown")

    # ── Check 1: evidence_index must not imply batch success ──
    if evidence_index:
        # evidence pass should never be rendered as "final pass" in evidence index
        if "evidence_status: pass" in evidence_index and "final_batch_status: pass" in evidence_index:
            # OK only if synthesis actually says pass
            if fbs != "pass":
                pass  # This is correct — evidence says pass but final says blocked
        # Check for unqualified "PASS" that could be misread
        if "\nPASS" in evidence_index or evidence_index.startswith("PASS"):
            errors.append("evidence_index contains unqualified PASS — may be misread as batch success")

    # ── Check 2: reviewer_index must distinguish reviewer_verdict from final_batch_status ──
    if reviewer_index:
        if "reviewer_verdict:" not in reviewer_index:
            errors.append("reviewer_index missing reviewer_verdict field")
        if "final_batch_status:" not in reviewer_index:
            errors.append("reviewer_index missing final_batch_status field")
        # reviewer_verdict=pass + fbs=blocked must be explicit
        if reviewer_verdict == "pass" and fbs == "blocked":
            if "reviewer_verdict=pass" in reviewer_index and "final_batch_status: pass" in reviewer_index:
                errors.append("reviewer_index: reviewer_verdict=pass but final_batch_status renders as pass — conflict")

    # ── Check 3: final_report must have exactly one authoritative status ──
    if final_report:
        fbs_count = sum(1 for line in final_report.split("\n") if line.startswith("final_batch_status:"))
        if fbs_count == 0:
            errors.append("final_report missing final_batch_status block")
        elif fbs_count > 1:
            errors.append("final_report has " + str(fbs_count) + " final_batch_status lines — must have exactly 1")

    # ── Check 4: Cross-report semantic conflicts ──
    # evidence_status=pass in evidence index but final_batch_status not from synthesis
    if evidence_index and "evidence_status: pass" in evidence_index:
        ev_fbs_lines = [l for l in evidence_index.split("\n") if l.startswith("final_batch_status:")]
        for line in ev_fbs_lines:
            if "pass" in line and fbs != "pass":
                errors.append("evidence_index: final_batch_status=pass in evidence index but synthesis says blocked")

    # reviewer_verdict=pass in reviewer index but final_batch_status not from synthesis
    if reviewer_index and "reviewer_verdict: pass" in reviewer_index:
        ri_fbs_lines = [l for l in reviewer_index.split("\n") if l.startswith("final_batch_status:")]
        for line in ri_fbs_lines:
            if "pass" in line and fbs != "pass":
                errors.append("reviewer_index: final_batch_status=pass in reviewer index but synthesis says blocked")

    # ── Check 5: prose-only status detection ──
    unqualified_pass_patterns = [
        "\nPASS\n", "\npass\n", "Status: pass", "Status: PASS",
        "Everything looks good", "All checks passed",
    ]
    for report_text, report_name in [(evidence_index, "evidence_index"),
                                      (reviewer_index, "reviewer_index")]:
        for pattern in unqualified_pass_patterns:
            if pattern.lower() in report_text.lower():
                # Only flag if the report doesn't also have a structured status
                if "final_batch_status:" not in report_text:
                    errors.append(report_name + ": prose-only status '" + pattern.strip() + "' without structured final_batch_status")
                    break

    # ── Check 6: parent summary pass while child blocked ──
    # This checks if the final_report says pass but synthesis says blocked
    if final_report and fbs == "blocked":
        if "final_batch_status: pass" in final_report:
            errors.append("parent_summary_conflict: final-report says pass but synthesis says blocked")
        if "\npass\n" in final_report.lower() and "final_batch_status: pass" not in final_report:
            errors.append("parent_summary_conflict: final-report has unqualified 'pass' while synthesis is blocked")

    return {
        "consistency_status": "pass" if not errors else "blocked",
        "consistency_errors": errors,
        "all_reports_consistent": len(errors) == 0,
    }


# ── CLI ─────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Synthesize final_batch_status from run artifacts (fail-closed)."
    )
    parser.add_argument(
        "run_dir",
        help="Path to run directory (e.g., .ai/runs/<run>/<sub-run>)",
    )
    parser.add_argument(
        "--output", "-o",
        choices=["json", "markdown", "both"],
        default="both",
        help="Output format (default: both)",
    )
    parser.add_argument(
        "--generate-report",
        action="store_true",
        help="Generate final-report.md content to stdout",
    )
    parser.add_argument(
        "--validate",
        action="store_true",
        help="Validate blocked_by categories and reasons against legal enums",
    )
    args = parser.parse_args()

    run_dir = Path(args.run_dir)
    if not run_dir.is_dir():
        print("ERROR: run_dir not found: " + str(run_dir), file=sys.stderr)
        sys.exit(2)

    result = synthesize(run_dir)

    validation_errors = []
    if args.validate:
        validation_errors = validate_result(result)
        if validation_errors:
            print("VALIDATION ERRORS:", file=sys.stderr)
            for e in validation_errors:
                print("  - " + e, file=sys.stderr)
            result["_validation_errors"] = validation_errors

    if args.output in ("json", "both"):
        print(json.dumps(result, indent=2, ensure_ascii=False))

    if args.output in ("markdown", "both"):
        report = generate_report(result, run_dir)
        if args.output == "both":
            print("")
            print("--- MARKDOWN ---")
            print("")
        print(report)

    if args.generate_report:
        print(generate_report(result, run_dir))

    # Exit codes: 0=pass, 1=blocked, 2=validation_error
    if validation_errors:
        sys.exit(2)
    if result["final_batch_status"] == "blocked":
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
