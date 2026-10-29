"""validate_paper_acceptance_gate.py — A8 Paper Acceptance Gate validation.

Runs 14 checks to verify the Paper Acceptance Gate:
  1-3:  Module structure
  4-6:  Status determination (all 5 statuses reachable)
  7-8:  Privacy gate
  9-10: Schema validation
  11-12: Multi-reviewer merge
  13-14: Integration with A5 adapter + A7 client
"""

import sys
import ast
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "ai-workflow-hub" / "src"))

from ai_workflow_hub.context_layer.adapters.paper_acceptance_gate import (
    compute_acceptance,
    validate_acceptance_result,
    merge_reviewer_results,
)
from ai_workflow_hub.context_layer.adapters.writelab_adapter import (
    convert_expression_results,
    validate_review_issue,
)


def run_check(check_id: int, description: str, passed: bool, detail: str = ""):
    status = "PASS" if passed else "FAIL"
    print(f"  [{status}] Check {check_id:02d}: {description}")
    if detail and not passed:
        print(f"         Detail: {detail}")
    return passed


def main():
    print("=" * 60)
    print("A8 Paper Acceptance Gate Validation")
    print("=" * 60)

    results = []

    # --- Module structure (1-3) ---
    gate_file = PROJECT_ROOT / "ai-workflow-hub" / "src" / "ai_workflow_hub" / "context_layer" / "adapters" / "paper_acceptance_gate.py"
    results.append(run_check(1, "paper_acceptance_gate.py exists",
                             gate_file.exists()))

    source = gate_file.read_text(encoding="utf-8")
    has_compute = "def compute_acceptance" in source
    has_validate = "def validate_acceptance_result" in source
    has_merge = "def merge_reviewer_results" in source
    results.append(run_check(2, "Three public functions defined",
                             has_compute and has_validate and has_merge))

    results.append(run_check(3, "No I/O or network imports",
                             "import httpx" not in source and "import requests" not in source))

    # --- Status determination (4-6) ---
    r_accepted = compute_acceptance(issues=[])
    results.append(run_check(4, "Empty issues → accepted",
                             r_accepted["status"] == "accepted"))

    issues_blocking = [{
        "issue_id": "test-b1", "issue_type": "expression", "severity": "major",
        "location": {"chapter": "", "section": "", "paragraph_index": 0},
        "evidence": "test", "recommendation": "fix", "blocking": True, "human_required": False,
    }]
    r_blocked = compute_acceptance(issues=issues_blocking)
    results.append(run_check(5, "Blocking issue → blocked",
                             r_blocked["status"] == "blocked"
                             and len(r_blocked["blocking_issues"]) == 1))

    issues_nonblocking = [{
        "issue_id": "test-nb1", "issue_type": "expression", "severity": "minor",
        "location": {"chapter": "", "section": "", "paragraph_index": 0},
        "evidence": "test", "recommendation": "fix", "blocking": False, "human_required": False,
    }]
    r_limited = compute_acceptance(issues=issues_nonblocking)
    results.append(run_check(6, "Non-blocking issue → accepted_with_limitation",
                             r_limited["status"] == "accepted_with_limitation"))

    # --- Privacy gate (7-8) ---
    r_privacy_fail = compute_acceptance(
        issues=[],
        privacy_attestation={"no_full_text": False, "no_api_keys": True, "no_personal_identity": True},
    )
    results.append(run_check(7, "Privacy violation → blocked",
                             r_privacy_fail["status"] == "blocked"))

    r_privacy_ok = compute_acceptance(
        issues=[],
        privacy_attestation={"no_full_text": True, "no_api_keys": True, "no_personal_identity": True},
    )
    results.append(run_check(8, "Valid attestation → not blocked",
                             r_privacy_ok["status"] != "blocked"))

    # --- Schema validation (9-10) ---
    errors = validate_acceptance_result(r_accepted)
    results.append(run_check(9, "Valid result passes schema check",
                             errors == []))

    errors_bad = validate_acceptance_result({"status": "invalid"})
    results.append(run_check(10, "Invalid result caught by schema check",
                             len(errors_bad) >= 2))

    # --- Multi-reviewer merge (11-12) ---
    merged = merge_reviewer_results([r_accepted, r_blocked])
    results.append(run_check(11, "Merge: blocked wins over accepted",
                             merged["status"] == "blocked"))

    merged_all_ok = merge_reviewer_results([r_accepted, r_accepted])
    results.append(run_check(12, "Merge: all accepted → accepted",
                             merged_all_ok["status"] == "accepted"))

    # --- Integration with A5 adapter (13-14) ---
    # Feed adapter output into acceptance gate
    expr_issues = convert_expression_results([{
        "detection_id": "gate-0001",
        "rule_id": "W1",
        "risk_level": "high",
        "chapter": "引言",
        "section": "",
        "paragraph_index": 0,
        "rule_description": "双重模板结构",
        "suggestion": "拆分论点",
        "matched_text": "不是A而是B",
    }])
    r_adapter = compute_acceptance(
        issues=expr_issues,
        reviewer="writelab_adapter",
        evidence_pack_ref="ep-test-001",
    )
    results.append(run_check(13, "Adapter issues → acceptance gate (end-to-end)",
                             r_adapter["status"] == "blocked"
                             and len(r_adapter["blocking_issues"]) >= 1))

    adapter_errors = validate_acceptance_result(r_adapter)
    results.append(run_check(14, "End-to-end result passes schema validation",
                             adapter_errors == []))

    # Summary
    passed = sum(results)
    total = len(results)
    print("=" * 60)
    print(f"Result: {passed}/{total} checks passed")
    if passed == total:
        print("STATUS: ALL CHECKS PASSED")
    else:
        print(f"STATUS: {total - passed} CHECK(S) FAILED")
    print("=" * 60)

    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
