#!/usr/bin/env python3
"""
test_status_synthesis.py — Fixture-based tests for final_batch_status synthesis.

Verifies all 1 positive + 7 negative fixtures from the S1 Frozen TaskSpec.
Run from tools/ directory: python test_status_synthesis.py
"""

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from ai_guard import synthesize, validate_result, generate_report


def _make_run_dir(files: dict) -> Path:
    """Create a temporary run directory with given artifact files."""
    tmp = Path(tempfile.mkdtemp(prefix="s1-fixture-"))
    for relpath, content in files.items():
        full = tmp / relpath
        full.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, dict) or isinstance(content, list):
            full.write_text(json.dumps(content), encoding="utf-8")
        else:
            full.write_text(str(content), encoding="utf-8")
    return tmp


# ── Fixtures ─────────────────────────────────────────────────────

def test_positive_fixture():
    """All pass → final_batch_status: pass"""
    run_dir = _make_run_dir({
        "chain-evidence.json": {
            "task_id": "test-001",
            "run_id": "run-001",
            "preflight_blocked": False,
        },
        "state.json": {
            "evidence_ok": True,
            "human_required": False,
        },
        "review.yaml": {
            "passed": True,
            "recommendation": "proceed",
        },
    })
    result = synthesize(run_dir)
    errors = validate_result(result)

    assert result["final_batch_status"] == "pass", f"Expected pass, got: {result}"
    assert result["blocked_by"] == [], f"Expected empty blocked_by, got: {result['blocked_by']}"
    assert not errors, f"Validation errors: {errors}"
    assert result["source_status"]["human_required"] is False
    return "PASS"


def test_negative_fixture_1():
    """guard_result=blocked + evidence=pass → blocked (policy/blocking)"""
    run_dir = _make_run_dir({
        "chain-evidence.json": {
            "preflight_blocked": True,
        },
        "review.yaml": {
            "passed": True,
        },
    })
    result = synthesize(run_dir)
    errors = validate_result(result)

    assert result["final_batch_status"] == "blocked", f"Expected blocked, got: {result}"
    assert not errors, f"Validation errors: {errors}"
    blocked_reasons = [b["reason"] for b in result["blocked_by"]]
    assert "TaskSpec_boundary" in blocked_reasons, f"Expected TaskSpec_boundary in blocked_by, got: {blocked_reasons}"
    return "PASS"


def test_negative_fixture_2():
    """guard=pass + evidence=pass + reviewer=invalid → blocked (review/blocking)"""
    run_dir = _make_run_dir({
        "chain-evidence.json": {
            "task_id": "test-002",
        },
        "review.yaml": {
            "format": "broken",
        },
    })
    # review.yaml has no recognized verdict field → reviewer_invalid
    result = synthesize(run_dir)
    errors = validate_result(result)

    assert result["final_batch_status"] == "blocked", f"Expected blocked, got: {result}"
    assert not errors, f"Validation errors: {errors}"
    blocked_reasons = [b["reason"] for b in result["blocked_by"]]
    assert "reviewer_invalid" in blocked_reasons, f"Expected reviewer_invalid in blocked_by, got: {blocked_reasons}"
    return "PASS"


def test_negative_fixture_3():
    """guard=pass + evidence=pass + reviewer=rejected → blocked (review/blocking)"""
    run_dir = _make_run_dir({
        "chain-evidence.json": {
            "task_id": "test-003",
        },
        "state.json": {"evidence_ok": True},
        "review.yaml": {
            "passed": False,
        },
    })
    result = synthesize(run_dir)
    errors = validate_result(result)

    assert result["final_batch_status"] == "blocked", f"Expected blocked, got: {result}"
    assert not errors, f"Validation errors: {errors}"
    blocked_reasons = [b["reason"] for b in result["blocked_by"]]
    assert "reviewer_rejected" in blocked_reasons, f"Expected reviewer_rejected, got: {blocked_reasons}"
    return "PASS"


def test_negative_fixture_4():
    """guard=pass + evidence=pass + reviewer=timeout → blocked (review/blocking)"""
    # No review.yaml, no review.md, no review-issues.json → timeout
    run_dir = _make_run_dir({
        "chain-evidence.json": {
            "task_id": "test-004",
        },
        "state.json": {"evidence_ok": True},
    })
    result = synthesize(run_dir)
    errors = validate_result(result)

    assert result["final_batch_status"] == "blocked", f"Expected blocked, got: {result}"
    assert not errors, f"Validation errors: {errors}"
    blocked_reasons = [b["reason"] for b in result["blocked_by"]]
    assert "reviewer_timeout" in blocked_reasons, f"Expected reviewer_timeout, got: {blocked_reasons}"
    return "PASS"


def test_negative_fixture_5():
    """All pass but human_required=true → blocked (policy/blocking)"""
    run_dir = _make_run_dir({
        "chain-evidence.json": {
            "task_id": "test-005",
        },
        "state.json": {
            "evidence_ok": True,
            "human_required": True,
        },
        "review.yaml": {
            "passed": True,
        },
    })
    result = synthesize(run_dir)
    errors = validate_result(result)

    assert result["final_batch_status"] == "blocked", f"Expected blocked, got: {result}"
    assert not errors, f"Validation errors: {errors}"
    assert result["source_status"]["human_required"] is True
    blocked_reasons = [b["reason"] for b in result["blocked_by"]]
    assert "human_required" in blocked_reasons, f"Expected human_required in blocked_by, got: {blocked_reasons}"
    return "PASS"


def test_negative_fixture_6():
    """guard=unknown + evidence=pass + reviewer=pass → blocked (infra/blocking)"""
    # No chain-evidence.json at all → guard is blocked, blocked_by includes evidence_missing
    run_dir = _make_run_dir({
        "state.json": {"evidence_ok": True},
        "review.yaml": {
            "passed": True,
        },
    })
    result = synthesize(run_dir)
    errors = validate_result(result)

    assert result["final_batch_status"] == "blocked", f"Expected blocked, got: {result}"
    assert not errors, f"Validation errors: {errors}"
    blocked_reasons = [b["reason"] for b in result["blocked_by"]]
    # No chain-evidence → guard returns ("blocked", [evidence_missing])
    assert "evidence_missing" in blocked_reasons, f"Expected evidence_missing in blocked_by, got: {blocked_reasons}"
    return "PASS"


def test_negative_fixture_7():
    """final_batch_status=blocked with empty blocked_by → must be caught by validate_result"""
    result = {
        "final_batch_status": "blocked",
        "blocked_by": [],
        "source_status": {
            "guard_result": "unknown",
            "evidence_status": "unknown",
            "reviewer_verdict": "unknown",
            "human_required": False,
        },
    }
    errors = validate_result(result)

    assert len(errors) > 0, f"Expected validation errors for blocked with empty blocked_by, got none"
    assert any("blocked_by is empty" in e for e in errors), f"Expected blocked_by empty error, got: {errors}"
    return "PASS"


def test_report_machine_readable_block():
    """Verify generate_report produces machine-readable final_batch_status block at top."""
    result = {
        "final_batch_status": "blocked",
        "blocked_by": [{"category": "policy/blocking", "reason": "TaskSpec_boundary"}],
        "source_status": {
            "guard_result": "blocked",
            "evidence_status": "pass",
            "reviewer_verdict": "not_applicable",
            "human_required": False,
        },
    }
    report = generate_report(result, Path("/nonexistent"))
    lines = report.split("\n")

    # Top block check
    assert lines[0].startswith("final_batch_status:"), f"Line 0: expected final_batch_status, got '{lines[0]}'"
    assert "blocked_by:" in lines[1] or (len(lines) > 1 and "blocked" in lines[0]), f"blocked_by not in top block: {lines[:5]}"
    assert "source_status:" in report, f"source_status missing from report"
    assert "human_required:" in report, f"human_required missing from report"

    return "PASS"


def test_legal_enums_all_valid():
    """Verify all enum values are recognized by validate_result."""
    result = {
        "final_batch_status": "pass",
        "blocked_by": [],
        "source_status": {
            "guard_result": "pass",
            "evidence_status": "pass",
            "reviewer_verdict": "pass",
            "human_required": False,
        },
    }
    errors = validate_result(result)
    assert not errors, f"Valid pass should have no errors: {errors}"

    # Test a blocked result with legal blocked_by
    result2 = {
        "final_batch_status": "blocked",
        "blocked_by": [
            {"category": "infra/blocking", "reason": "unknown_status"},
            {"category": "infra/blocking", "reason": "unparseable_report"},
        ],
        "source_status": {
            "guard_result": "unknown",
            "evidence_status": "unknown",
            "reviewer_verdict": "unknown",
            "human_required": False,
        },
    }
    errors2 = validate_result(result2)
    assert not errors2, f"Legal infra/blocking should have no errors: {errors2}"

    return "PASS"


def test_report_only_one_final_status():
    """Verify final-report.md has exactly one machine-readable final_batch_status."""
    result1 = {
        "final_batch_status": "pass",
        "blocked_by": [],
        "source_status": {
            "guard_result": "pass",
            "evidence_status": "pass",
            "reviewer_verdict": "pass",
            "human_required": False,
        },
    }
    report = generate_report(result1, Path("/nonexistent"))
    # "final_batch_status:" should appear exactly once as a key (not as a value)
    key_count = sum(1 for line in report.split("\n") if line.startswith("final_batch_status:"))
    assert key_count == 1, f"Expected 1 final_batch_status key line, found {key_count}"
    return "PASS"


def test_pass_with_not_applicable_reviewer_must_fail_validation():
    """GPT review fix: final_batch_status=pass + reviewer_verdict=not_applicable → validation error."""
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
    assert len(errors) > 0, f"Expected validation errors for pass + reviewer_verdict=not_applicable, got none"
    assert any("reviewer_verdict" in e for e in errors), f"Expected reviewer_verdict error, got: {errors}"
    return "PASS"


def test_pass_with_missing_evidence_must_fail_validation():
    """final_batch_status=pass + evidence_status=missing → validation error."""
    result = {
        "final_batch_status": "pass",
        "blocked_by": [],
        "source_status": {
            "guard_result": "pass",
            "evidence_status": "missing",
            "reviewer_verdict": "pass",
            "human_required": False,
        },
    }
    errors = validate_result(result)
    assert len(errors) > 0, f"Expected validation errors for pass + evidence_status=missing"
    assert any("evidence_status" in e for e in errors), f"Expected evidence_status error, got: {errors}"
    return "PASS"


def test_pass_with_human_required_true_must_fail_validation():
    """final_batch_status=pass + human_required=true → validation error."""
    result = {
        "final_batch_status": "pass",
        "blocked_by": [],
        "source_status": {
            "guard_result": "pass",
            "evidence_status": "pass",
            "reviewer_verdict": "pass",
            "human_required": True,
        },
    }
    errors = validate_result(result)
    assert len(errors) > 0, f"Expected validation errors for pass + human_required=true"
    assert any("human_required" in e for e in errors), f"Expected human_required error, got: {errors}"
    return "PASS"


# ── Runner ────────────────────────────────────────────────────────

def main():
    tests = [
        ("Positive fixture (all pass → pass)", test_positive_fixture),
        ("Negative fixture 1 (guard blocked → blocked)", test_negative_fixture_1),
        ("Negative fixture 2 (reviewer invalid → blocked)", test_negative_fixture_2),
        ("Negative fixture 3 (reviewer rejected → blocked)", test_negative_fixture_3),
        ("Negative fixture 4 (reviewer timeout → blocked)", test_negative_fixture_4),
        ("Negative fixture 5 (human_required → blocked)", test_negative_fixture_5),
        ("Negative fixture 6 (guard unknown → blocked)", test_negative_fixture_6),
        ("Negative fixture 7 (blocked with empty blocked_by → error)", test_negative_fixture_7),
        ("Report machine-readable block check", test_report_machine_readable_block),
        ("Legal enums validation", test_legal_enums_all_valid),
        ("Report single final_batch_status", test_report_only_one_final_status),
        ("GPT fix: pass + reviewer not_applicable → error", test_pass_with_not_applicable_reviewer_must_fail_validation),
        ("GPT fix: pass + evidence missing → error", test_pass_with_missing_evidence_must_fail_validation),
        ("GPT fix: pass + human_required true → error", test_pass_with_human_required_true_must_fail_validation),
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
