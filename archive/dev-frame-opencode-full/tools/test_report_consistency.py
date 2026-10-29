#!/usr/bin/env python3
"""
test_report_consistency.py — Cross-report consistency tests (S2).

Verifies that evidence-index, reviewer-index, and final-report:
  1. Never imply batch success from evidence_status or reviewer_verdict alone
  2. Are consistent with the S1 synthesis rule
  3. Detect and fail-closed on conflicting reports
  4. Reject prose-only status without structured final_batch_status

Run from tools/ directory: python test_report_consistency.py
"""

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from ai_guard import (
    synthesize,
    validate_result,
    generate_report,
    generate_evidence_index,
    generate_reviewer_index,
    validate_cross_report_consistency,
)

def _make_run_dir(files: dict) -> Path:
    tmp = Path(tempfile.mkdtemp(prefix="s2-fixture-"))
    for relpath, content in files.items():
        full = tmp / relpath
        full.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, (dict, list)):
            full.write_text(json.dumps(content), encoding="utf-8")
        else:
            full.write_text(str(content), encoding="utf-8")
    return tmp


# ── Positive fixture ──────────────────────────────────────────────

def test_positive_all_consistent():
    """All pass → all reports consistent."""
    run_dir = _make_run_dir({
        "chain-evidence.json": {"task_id": "t1", "run_id": "r1", "preflight_blocked": False},
        "state.json": {"evidence_ok": True, "human_required": False},
        "review.yaml": {"passed": True, "recommendation": "proceed"},
    })
    result = synthesize(run_dir)
    errors = validate_result(result)
    assert not errors, f"Validation errors: {errors}"
    assert result["final_batch_status"] == "pass"

    ev_idx = generate_evidence_index(result)
    rv_idx = generate_reviewer_index(result)
    report = generate_report(result, run_dir)

    # Check evidence index doesn't claim batch success
    assert "evidence_status: pass" in ev_idx, "evidence_index missing evidence_status"
    disclaimer_terms = ["does not mean the batch passed", "does not indicate batch success",
                        "not from evidence_status", "one of four gates"]
    found = any(t in ev_idx.lower() for t in disclaimer_terms)
    assert found, f"evidence_index must disclaim batch success. Content: {ev_idx[:500]}"

    # Check reviewer index distinguishes verdict from final status
    assert "reviewer_verdict:" in rv_idx, "reviewer_index missing reviewer_verdict"
    rv_distinction = any(t in rv_idx.lower() for t in [
        "reviewer_verdict=pass", "≠ final_batch_status", "does not mean",
        "reviewer is one of four gates", "all four must pass"
    ])
    assert rv_distinction, f"reviewer_index must distinguish verdict from final. Content: {rv_idx[:500]}"

    # Check cross-report consistency
    cons = validate_cross_report_consistency(result, ev_idx, rv_idx, report)
    assert cons["all_reports_consistent"], f"Reports inconsistent: {cons['consistency_errors']}"

    # Evidence index must not have unqualified PASS
    assert "\nPASS" not in ev_idx, "evidence_index has unqualified PASS"

    return "PASS"


# ── Negative fixture 1: evidence pass + reviewer invalid ───────────

def test_negative_evidence_pass_reviewer_invalid():
    """evidence=pass + reviewer=invalid → blocked, reports consistent."""
    run_dir = _make_run_dir({
        "chain-evidence.json": {"task_id": "t1"},
        "review.yaml": {"format": "broken"},
    })
    result = synthesize(run_dir)
    assert result["final_batch_status"] == "blocked"
    blocked_reasons = [b["reason"] for b in result["blocked_by"]]
    assert "reviewer_invalid" in blocked_reasons

    ev_idx = generate_evidence_index(result)
    rv_idx = generate_reviewer_index(result)
    report = generate_report(result, run_dir)

    # Evidence index must NOT say final_batch_status=pass
    assert "final_batch_status: blocked" in ev_idx
    assert "final_batch_status: pass" not in ev_idx

    # Reviewer index must show reviewer_invalid
    assert "reviewer_verdict: reviewer_invalid" in rv_idx

    cons = validate_cross_report_consistency(result, ev_idx, rv_idx, report)
    assert cons["all_reports_consistent"], f"Expected consistent: {cons['consistency_errors']}"

    return "PASS"


# ── Negative fixture 2: evidence pass + guard blocked ──────────────

def test_negative_evidence_pass_guard_blocked():
    """evidence=pass + guard=blocked → blocked, reports consistent."""
    run_dir = _make_run_dir({
        "chain-evidence.json": {"preflight_blocked": True},
        "review.yaml": {"passed": True},
    })
    result = synthesize(run_dir)
    assert result["final_batch_status"] == "blocked"
    blocked_reasons = [b["reason"] for b in result["blocked_by"]]
    assert "TaskSpec_boundary" in blocked_reasons

    ev_idx = generate_evidence_index(result)
    rv_idx = generate_reviewer_index(result)
    report = generate_report(result, run_dir)

    assert "final_batch_status: blocked" in ev_idx
    assert "final_batch_status: pass" not in ev_idx

    cons = validate_cross_report_consistency(result, ev_idx, rv_idx, report)
    assert cons["all_reports_consistent"], f"Expected consistent: {cons['consistency_errors']}"

    return "PASS"


# ── Negative fixture 3: reviewer pass + evidence missing ───────────

def test_negative_reviewer_pass_evidence_missing():
    """reviewer=pass + evidence=missing → blocked, reports consistent."""
    run_dir = _make_run_dir({
        # No chain-evidence.json, no state.json → evidence missing
        "review.yaml": {"passed": True},
    })
    result = synthesize(run_dir)
    assert result["final_batch_status"] == "blocked"
    blocked_reasons = [b["reason"] for b in result["blocked_by"]]
    assert "evidence_missing" in blocked_reasons

    ev_idx = generate_evidence_index(result)
    rv_idx = generate_reviewer_index(result)
    report = generate_report(result, run_dir)

    # Evidence index must show blocked, not pass
    assert "final_batch_status: blocked" in ev_idx
    # Reviewer index: reviewer pass, but final is blocked
    assert "reviewer_verdict: pass" in rv_idx
    assert "final_batch_status: blocked" in rv_idx
    # Must distinguish verdict from final status
    assert "reviewer_verdict=pass" in rv_idx or "reviewer pass" in rv_idx.lower()

    cons = validate_cross_report_consistency(result, ev_idx, rv_idx, report)
    assert cons["all_reports_consistent"], f"Expected consistent: {cons['consistency_errors']}"

    return "PASS"


# ── Negative fixture 4: human_required ─────────────────────────────

def test_negative_human_required():
    """all pass but human_required=true → blocked."""
    run_dir = _make_run_dir({
        "chain-evidence.json": {"task_id": "t1"},
        "state.json": {"evidence_ok": True, "human_required": True},
        "review.yaml": {"passed": True},
    })
    result = synthesize(run_dir)
    assert result["final_batch_status"] == "blocked"
    blocked_reasons = [b["reason"] for b in result["blocked_by"]]
    assert "human_required" in blocked_reasons

    ev_idx = generate_evidence_index(result)
    rv_idx = generate_reviewer_index(result)
    report = generate_report(result, run_dir)

    assert "final_batch_status: blocked" in ev_idx
    assert "final_batch_status: blocked" in rv_idx

    cons = validate_cross_report_consistency(result, ev_idx, rv_idx, report)
    assert cons["all_reports_consistent"], f"Expected consistent: {cons['consistency_errors']}"

    return "PASS"


# ── Negative fixture 5: conflicting reports ────────────────────────

def test_negative_conflicting_reports():
    """Simulate: evidence says pass, reviewer says invalid, final says pass → blocked."""
    # Build synthesis result where final is blocked (reviewer_invalid)
    run_dir = _make_run_dir({
        "chain-evidence.json": {"task_id": "t1"},
        "review.yaml": {"format": "broken"},
    })
    result = synthesize(run_dir)
    assert result["final_batch_status"] == "blocked"

    # Now create a manually-corrupted final report that claims pass
    corrupted_report = "final_batch_status: pass\nblocked_by: []\nsource_status:\n  guard_result: pass\n  evidence_status: pass\n  reviewer_verdict: pass\n  human_required: false\n\n---\n\n# Final Report\n\n## Status\n\npass\n"

    ev_idx = generate_evidence_index(result)
    rv_idx = generate_reviewer_index(result)

    cons = validate_cross_report_consistency(result, ev_idx, rv_idx, corrupted_report)
    assert not cons["all_reports_consistent"], f"Expected inconsistent, got: {cons}"
    assert "parent_summary_conflict" in str(cons["consistency_errors"]), \
        f"Expected parent_summary_conflict error: {cons['consistency_errors']}"
    assert cons["consistency_status"] == "blocked"

    return "PASS"


# ── Negative fixture 6: parent summary pass while child blocked ────

def test_negative_parent_summary_pass_child_blocked():
    """Synthesis says blocked, but final report has unqualified 'pass'."""
    run_dir = _make_run_dir({
        "chain-evidence.json": {"preflight_blocked": True},
    })
    result = synthesize(run_dir)
    assert result["final_batch_status"] == "blocked"

    # Final report with unqualified "pass" text (prose-only)
    bad_report = "# Final Report\n\n## Status\n\npass\n\nEverything looks good.\n"
    ev_idx = generate_evidence_index(result)
    rv_idx = generate_reviewer_index(result)

    cons = validate_cross_report_consistency(result, ev_idx, rv_idx, bad_report)
    assert not cons["all_reports_consistent"], f"Expected inconsistent: {cons}"
    # Should catch either parent_summary_conflict or missing final_batch_status
    assert len(cons["consistency_errors"]) > 0, "Expected errors for prose-only status"
    assert cons["consistency_status"] == "blocked"

    return "PASS"


# ── Negative fixture 7: prose-only final status ────────────────────

def test_negative_prose_only_status():
    """Prose-only 'PASS' in evidence index without structured status → blocked."""
    run_dir = _make_run_dir({
        "chain-evidence.json": {"task_id": "t1"},
        "state.json": {"evidence_ok": True, "human_required": False},
        "review.yaml": {"passed": True},
    })
    result = synthesize(run_dir)
    assert result["final_batch_status"] == "pass"

    # Create a bad evidence index with unqualified PASS and no structured block
    bad_evidence = "# Evidence Index\n\nPASS\n\nAll evidence looks good.\n"

    cons = validate_cross_report_consistency(result, bad_evidence, "", "")
    assert not cons["all_reports_consistent"], f"Expected inconsistent for prose-only: {cons}"
    assert cons["consistency_status"] == "blocked"

    return "PASS"


# ── Additional: S1 rule preservation ───────────────────────────────

def test_s1_rule_preserved():
    """Verify S1 synthesis rule is unchanged and preserved."""
    run_dir = _make_run_dir({
        "chain-evidence.json": {"task_id": "t1", "preflight_blocked": False},
        "state.json": {"evidence_ok": True, "human_required": False},
        "review.yaml": {"passed": True},
    })
    result = synthesize(run_dir)

    # S1 invariants
    assert result["final_batch_status"] == "pass"
    assert result["source_status"]["guard_result"] == "pass"
    assert result["source_status"]["evidence_status"] == "pass"
    assert result["source_status"]["reviewer_verdict"] == "pass"
    assert result["source_status"]["human_required"] is False
    assert result["blocked_by"] == []

    # evidence_status != final_batch_status
    assert result["source_status"]["evidence_status"] != result["final_batch_status"] or \
           result["final_batch_status"] == "pass", \
           "evidence_status must not be mistaken for final_batch_status"

    return "PASS"


# ── Additional: evidence index structural claims ───────────────────

def test_evidence_index_never_claims_batch_success():
    """evidence_index must never make unqualified claims about batch success."""
    # Blocked case
    run_dir = _make_run_dir({
        "chain-evidence.json": {"preflight_blocked": True},
    })
    result = synthesize(run_dir)
    assert result["final_batch_status"] == "blocked"

    ev_idx = generate_evidence_index(result)

    # Must contain disclaimers
    assert "does NOT" in ev_idx, "evidence_index must contain disclaimer"
    assert "evidence_status" in ev_idx
    assert "final_batch_status: blocked" in ev_idx

    # Must NOT contain unqualified success language (disclaimers are OK)
    for i, line in enumerate(ev_idx.lower().split('\n')):
        # Skip disclaimer lines
        if 'does not' in line or 'not mean' in line or 'not indicate' in line:
            continue
        if 'not from evidence_status' in line:
            continue
        for phrase in ["batch passed", "batch succeeded", "run passed", "run succeeded"]:
            assert phrase not in line, f"evidence_index L{i} has unqualified '{phrase}': {line.strip()}"

    return "PASS"


# ── Additional: reviewer index distinguishes ────────────────────────

def test_reviewer_index_distinguishes():
    """reviewer_index must clearly distinguish reviewer_verdict from final_batch_status."""
    # Case: reviewer pass but batch blocked
    run_dir = _make_run_dir({
        "chain-evidence.json": {"preflight_blocked": True},
        "review.yaml": {"passed": True},
    })
    result = synthesize(run_dir)
    assert result["final_batch_status"] == "blocked"
    assert result["source_status"]["reviewer_verdict"] == "pass"

    rv_idx = generate_reviewer_index(result)

    # Must contain both fields
    assert "reviewer_verdict:" in rv_idx
    assert "final_batch_status:" in rv_idx
    # Must explain the distinction
    assert "≠" in rv_idx or "does not" in rv_idx.lower() or "not mean" in rv_idx.lower(), \
        "reviewer_index must explain that reviewer_verdict ≠ final_batch_status"

    return "PASS"


# ── GPT review fix: validate_result cross-field checks ─────────────

def test_validate_result_rejects_pass_with_not_applicable_reviewer():
    """validate_result must reject final_batch_status=pass + reviewer_verdict=not_applicable."""
    from ai_guard import validate_result
    result = {
        "final_batch_status": "pass",
        "blocked_by": [],
        "source_status": {
            "guard_result": "pass",
            "evidence_status": "pass",
            "reviewer_verdict": "not_applicable",
            "human_required": False,
        },
    }
    errors = validate_result(result)
    assert len(errors) > 0, f"Expected validation errors for pass + not_applicable, got none"
    assert any("reviewer_verdict" in e for e in errors), f"Expected reviewer_verdict error: {errors}"
    return "PASS"


# ── Runner ─────────────────────────────────────────────────────────

def main():
    tests = [
        ("Positive: all pass, reports consistent", test_positive_all_consistent),
        ("Negative 1: evidence pass + reviewer invalid", test_negative_evidence_pass_reviewer_invalid),
        ("Negative 2: evidence pass + guard blocked", test_negative_evidence_pass_guard_blocked),
        ("Negative 3: reviewer pass + evidence missing", test_negative_reviewer_pass_evidence_missing),
        ("Negative 4: human_required → blocked", test_negative_human_required),
        ("Negative 5: conflicting reports → blocked", test_negative_conflicting_reports),
        ("Negative 6: parent summary pass, child blocked", test_negative_parent_summary_pass_child_blocked),
        ("Negative 7: prose-only status → blocked", test_negative_prose_only_status),
        ("S1 rule preserved", test_s1_rule_preserved),
        ("Evidence index never claims batch success", test_evidence_index_never_claims_batch_success),
        ("Reviewer index distinguishes verdict from final", test_reviewer_index_distinguishes),
        ("GPT fix: validate_result rejects pass + not_applicable", test_validate_result_rejects_pass_with_not_applicable_reviewer),
    ]

    passed = 0
    failed = 0
    failures = []

    for name, fn in tests:
        try:
            result = fn()
            print(f"  PASS: {name}")
            passed += 1
        except AssertionError as e:
            print(f"  FAIL: {name} — {e}")
            failed += 1
            failures.append((name, str(e)))
        except Exception as e:
            print(f"  ERROR: {name} — {e}")
            failed += 1
            failures.append((name, f"ERROR: {e}"))

    print(f"\n{'='*60}")
    print(f"Results: {passed} passed, {failed} failed, {len(tests)} total")
    if failures:
        print(f"\nFailures:")
        for name, msg in failures:
            print(f"  - {name}: {msg}")
    print(f"{'='*60}")

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
