"""A51 Validation -- UNIFIED RAW-VS-POLICY RESULT MODEL.

Validates:
1. Immutable raw results (no counter mutation)
2. raw_verdict field
3. policy_verdict field
4. Missing-file hash comparison
5. Policy severity mapping
6. Integration (verdict = policy_verdict)
7. Structural checks
8. Test coverage
"""

import sys
from pathlib import Path

PASS = 0
FAIL = 0
RESULTS: list = []

ROOT = Path(__file__).resolve().parent
CLI_PATH = ROOT / "src" / "ai_workflow_hub" / "cli.py"
TEST_PATH = ROOT / "tests" / "test_paper_a51_unified_result.py"


def check(label, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        RESULTS.append(f"[PASS] {label}")
    else:
        FAIL += 1
        RESULTS.append(f"[FAIL] {label}  -- {detail}")


cli_src = CLI_PATH.read_text(encoding="utf-8")
test_src = TEST_PATH.read_text(encoding="utf-8")

# ============================================================
print("=" * 60)
print("Section 1: Immutable raw results (no counter mutation)")
print("=" * 60)

check("1.1 A51 immutability comment present",
      "A51: Do NOT mutate" in cli_src,
      "paper_verify must contain A51 immutability comment")

# Extract paper_verify source region for scoped checks
_verify_start = cli_src.find('@paper_app.command("verify")')
_verify_end = cli_src.find('@paper_app.command("verify-chain")')
paper_verify_src = (
    cli_src[_verify_start:_verify_end]
    if _verify_start >= 0 and _verify_end > _verify_start
    else cli_src
)

check("1.2 No counter mutation in paper_verify: result['failed'] -= 1 absent",
      'result["failed"] -= 1' not in paper_verify_src,
      "A51 must remove the counter mutation from paper_verify (result['failed'] -= 1)")

check("1.3 No counter mutation in paper_verify: result['failed'] = max absent",
      'result["failed"] = max(0, result["failed"] - 1)' not in paper_verify_src,
      "A51 must remove the max(0, ...) counter mutation pattern from paper_verify")

check("1.4 A51 immutable raw results comment present",
      "A51: Policy-adjusted verdict (raw results immutable)" in cli_src,
      "paper_verify must contain A51 raw-immutable marker comment")

check("1.5 A50->A51 transition comment present",
      "A50->A51: Non-strict" in cli_src,
      "Non-strict branch must have A50->A51 transition comment")

# ============================================================
print("=" * 60)
print("Section 2: raw_verdict field")
print("=" * 60)

check("2.1 raw_verdict assigned to result dict",
      'result["raw_verdict"]' in cli_src,
      "raw_verdict must be written to result dict")

check("2.2 raw_verdict uses passed/failed ternary",
      'result["raw_verdict"] = "passed" if result["failed"] == 0 else "failed"' in cli_src,
      "raw_verdict must use the standard passed/failed ternary on raw failed count")

check("2.3 raw_verdict computed outside completeness block",
      cli_src.find('result["raw_verdict"]') > cli_src.find('result["completeness_policy_severity"] = "none"'),
      "raw_verdict must be computed after the completeness block (at function level)")

# ============================================================
print("=" * 60)
print("Section 3: policy_verdict field")
print("=" * 60)

check("3.1 policy_verdict assigned to result dict",
      'result["policy_verdict"]' in cli_src,
      "policy_verdict must be written to result dict")

check("3.2 policy_verdict uses passed/failed ternary",
      'result["policy_verdict"] = "passed" if _policy_failed == 0 else "failed"' in cli_src,
      "policy_verdict must use _policy_failed (adjusted count)")

check("3.3 _policy_failed initialised from result['failed']",
      '_policy_failed = result["failed"]' in cli_src,
      "_policy_failed must start from the actual failed count")

check("3.4 _policy_failed adjusted for warn action",
      '_policy_failed = max(0, _policy_failed - 1)' in cli_src,
      "_policy_failed must be decremented for completeness warnings")

check("3.5 Adjustment gated by completeness_policy_action == 'warn'",
      'result.get("completeness_policy_action") == "warn"' in cli_src,
      "policy adjustment must only fire for 'warn' action (not 'block' or 'pass')")

# ============================================================
print("=" * 60)
print("Section 4: Missing-file hash comparison")
print("=" * 60)

check("4.1 A51 missing-file hash comment present",
      "A51: Missing-file hash comparison" in cli_src,
      "paper_verify must contain A51 missing-file hash comment")

check("4.2 Stored missing_from_bundle extracted",
      '_stored_mfb = _stored_comp.get("missing_from_bundle", [])' in cli_src,
      "stored missing_from_bundle must be extracted with [] default")

check("4.3 Recomputed missing_from_bundle extracted",
      '_recomputed_mfb = _comp_report.get("missing_from_bundle", [])' in cli_src,
      "recomputed missing_from_bundle must be extracted from _comp_report")

check("4.4 Path hash extraction from stored (dict format)",
      '_stored_hashes.add(_item.get("path_hash", ""))' in cli_src,
      "stored path_hash must be extracted from dict items")

check("4.5 Path hash extraction from recomputed (dict format)",
      '_recomputed_hashes.add(_item.get("path_hash", ""))' in cli_src,
      "recomputed path_hash must be extracted from dict items")

check("4.6 Hash set comparison",
      "_hash_match = _stored_hashes == _recomputed_hashes" in cli_src,
      "hash match must compare sets with ==")

check("4.7 completeness_missing_hashes_match assigned",
      'result["completeness_missing_hashes_match"]' in cli_src,
      "completeness_missing_hashes_match must be written to result")

check("4.8 Hash mismatch upgrades drift to 'low'",
      'if not _hash_match and result.get("completeness_drift_severity") == "none":' in cli_src
      and 'result["completeness_drift_severity"] = "low"' in cli_src,
      "hash mismatch without other drift must upgrade severity to 'low'")

# ============================================================
print("=" * 60)
print("Section 5: Policy severity mapping")
print("=" * 60)

check("5.1 A51 policy severity comment present",
      "A51: Policy severity" in cli_src,
      "paper_verify must contain A51 policy severity comment")

check("5.2 verified_matched -> severity 'none'",
      'result["completeness_policy_severity"] = "none"' in cli_src,
      "verified_matched must map to severity 'none'")

check("5.3 verified_drift high strict -> 'block'",
      '"warning" if not _comp_strict else "block"' in cli_src,
      "verified_drift with high severity must use 'warning' or 'block' based on strict")

check("5.4 verified_drift low -> 'info'",
      cli_src.count('result["completeness_policy_severity"] = "info"') >= 3,
      "low drift, verified_no_claim, and claim_only must map to 'info'")

check("5.5 completeness_policy_severity assigned to result",
      'result["completeness_policy_severity"]' in cli_src,
      "completeness_policy_severity must be written to result dict")

check("5.6 Fallback severity 'none' for unknown trust_status",
      cli_src.count('result["completeness_policy_severity"] = "none"') >= 2,
      "fallback severity must be 'none' (appears in matched + else branches)")

# ============================================================
print("=" * 60)
print("Section 6: Integration (verdict = policy_verdict)")
print("=" * 60)

check("6.1 verdict uses policy_verdict",
      'result["verdict"] = result["policy_verdict"]' in cli_src,
      "final verdict must use policy_verdict")

check("6.2 Both raw_verdict and policy_verdict in result",
      'result["raw_verdict"]' in cli_src and 'result["policy_verdict"]' in cli_src,
      "both verdict fields must be present in result dict")

check("6.3 Verdict computation comment mentions policy-adjusted",
      "Policy-adjusted verdict" in cli_src or "policy-adjusted verdict" in cli_src.lower(),
      "verdict computation comment must mention policy adjustment")

# ============================================================
print("=" * 60)
print("Section 7: Structural checks")
print("=" * 60)

check("7.1 raw_verdict before policy_verdict in source",
      cli_src.find('result["raw_verdict"]') < cli_src.find('result["policy_verdict"]'),
      "raw_verdict must be computed before policy_verdict")

check("7.2 policy_verdict before verdict assignment",
      cli_src.find('result["policy_verdict"]') < cli_src.find('result["verdict"] = result["policy_verdict"]'),
      "policy_verdict must be computed before final verdict assignment")

check("7.3 Completeness block ends before verdict computation",
      cli_src.find('result["completeness_policy_severity"] = "none"') < cli_src.find('# A51: Policy-adjusted verdict'),
      "completeness policy severity block must end before verdict computation")

check("7.4 Hash comparison inside completeness block",
      cli_src.find('# A51: Missing-file hash') > cli_src.find('if completeness_check:')
      and cli_src.find('# A51: Missing-file hash') < cli_src.find('# A51: Policy-adjusted verdict'),
      "hash comparison must be inside the completeness_check block")

check("7.5 Policy severity inside completeness block",
      cli_src.find('# A51: Policy severity') > cli_src.find('if completeness_check:')
      and cli_src.find('# A51: Policy severity') < cli_src.find('# A51: Policy-adjusted verdict'),
      "policy severity must be inside the completeness_check block")

# ============================================================
print("=" * 60)
print("Section 8: Test coverage")
print("=" * 60)

check("8.1 Test file exists",
      TEST_PATH.exists(),
      f"test file not found: {TEST_PATH}")

_test_a51_count = test_src.count("A51") + test_src.count("a51")
check("8.2 Tests reference A51 at least 4 times",
      _test_a51_count >= 4,
      f"found {_test_a51_count} references to A51 in tests")

_test_class_count = test_src.count("class Test")
check("8.3 At least 4 test classes",
      _test_class_count >= 4,
      f"found {_test_class_count} test classes")

test_count = test_src.count("def test_")
check("8.4 At least 10 test functions",
      test_count >= 10,
      f"found {test_count}")

check("8.5 Tests use CliRunner and JSON parsing",
      "CliRunner" in test_src
      and "json.loads" in test_src
      and "result.stdout" in test_src,
      "tests should use CliRunner and parse JSON from stdout")

check("8.6 Tests create real ZIP files with zipfile",
      "zipfile" in test_src or "zf_mod" in test_src,
      "tests should create real ZIP files for verification")

check("8.7 Tests cover raw_verdict and policy_verdict",
      '"raw_verdict"' in test_src and '"policy_verdict"' in test_src,
      "tests should cover both raw_verdict and policy_verdict fields")

check("8.8 Tests cover completeness_missing_hashes_match",
      '"completeness_missing_hashes_match"' in test_src,
      "tests should cover missing hash comparison field")

check("8.9 Tests cover completeness_policy_severity",
      '"completeness_policy_severity"' in test_src,
      "tests should cover policy severity field")

check("8.10 Tests cover completeness_drift_severity upgrade",
      '"completeness_drift_severity"' in test_src and '"low"' in test_src,
      "tests should verify drift severity upgrade from hash mismatch")

# ============================================================
print("=" * 60)
total = PASS + FAIL
print(f"A51 Validation: {PASS} passed, {FAIL} failed, {total} total")
print("=" * 60)

for r in RESULTS:
    print(r)

check("ALL A51 CHECKS PASSED", FAIL == 0)

sys.exit(0 if FAIL == 0 else 1)
