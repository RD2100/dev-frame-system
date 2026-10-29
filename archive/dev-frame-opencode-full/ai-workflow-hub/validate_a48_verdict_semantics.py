"""A48 Validation -- CONSISTENT COMPLETENESS VERDICT SEMANTICS.

Validates:
1. Deferred verdict computation (verdict after completeness block)
2. completeness_verdict field on paper verify
3. trust_summary completeness suffix
4. verify-chain completeness_verdict
5. verify-chain verification_mode suffix
6. Policy integration
7. JSON output
8. Test coverage
"""

import sys
from pathlib import Path

PASS = 0
FAIL = 0
RESULTS: list = []

ROOT = Path(__file__).resolve().parent
CLI_PATH = ROOT / "src" / "ai_workflow_hub" / "cli.py"
TEST_PATH = ROOT / "tests" / "test_paper_a48_verdict_semantics.py"


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
print("Section 1: Deferred verdict computation")
print("=" * 60)

check("1.1 A48 deferred verdict marker present in paper_verify",
      "A48: Deferred final verdict" in cli_src,
      "paper_verify must contain A48 deferred verdict comment")

_completeness_pos = cli_src.find("if completeness_check:")
_verdict_after_pos = cli_src.find(
    'result["verdict"] = "passed" if result["failed"] == 0 else "failed"',
    _completeness_pos + 1 if _completeness_pos >= 0 else 0,
)
check("1.2 Verdict computed AFTER completeness block in paper_verify",
      _completeness_pos >= 0 and _verdict_after_pos > _completeness_pos,
      f"completeness_block={_completeness_pos}, verdict={_verdict_after_pos}")

_trust_after = cli_src.find('result["trust_summary"]', _completeness_pos + 1
                            if _completeness_pos >= 0 else 0)
check("1.3 trust_summary computed AFTER completeness block in paper_verify",
      _trust_after > _completeness_pos >= 0,
      f"completeness_block={_completeness_pos}, trust_summary={_trust_after}")

# ============================================================
print("=" * 60)
print("Section 2: completeness_verdict field on paper verify")
print("=" * 60)

check("2.1 A48 completeness_verdict computation block present",
      "A48: Compute completeness_verdict" in cli_src,
      "paper_verify must contain A48 completeness_verdict computation comment")

check("2.2 completeness_verdict = 'verified' when mode=verified and verified=True",
      'result["completeness_verdict"] = "verified"' in cli_src,
      "completeness_verdict must be set to 'verified' for successful re-verification")

check("2.3 completeness_verdict = 'verified_failed' when mode=verified and verified=False",
      'result["completeness_verdict"] = "verified_failed"' in cli_src,
      "completeness_verdict must be set to 'verified_failed' when files are missing")

check("2.4 completeness_verdict = 'claim_only' when mode=claim_only",
      'result["completeness_verdict"] = "claim_only"' in cli_src,
      "completeness_verdict must be set to 'claim_only' when no run_dir")

check("2.5 completeness_verdict = 'error' when mode=error",
      'result["completeness_verdict"] = "error"' in cli_src,
      "completeness_verdict must be set to 'error' when run_dir not found")

check("2.6 completeness_verdict = 'unknown' as default fallback",
      'result["completeness_verdict"] = "unknown"' in cli_src,
      "completeness_verdict must be set to 'unknown' as fallback")

# ============================================================
print("=" * 60)
print("Section 3: trust_summary completeness suffix")
print("=" * 60)

check("3.1 A48 trust_summary suffix computation block present",
      "A48: trust_summary with completeness awareness" in cli_src,
      "paper_verify must contain A48 trust_summary computation comment")

check("3.2 trust_summary suffix '_complete' when completeness_verdict='verified'",
      '_ts += "_complete"' in cli_src,
      "trust_summary must append '_complete' for verified completeness")

check("3.3 trust_summary suffix '_incomplete' when completeness_verdict='verified_failed'",
      '_ts += "_incomplete"' in cli_src,
      "trust_summary must append '_incomplete' for failed completeness")

check("3.4 trust_summary suffix '_claim_only' when completeness_verdict='claim_only'",
      '_ts += "_claim_only"' in cli_src,
      "trust_summary must append '_claim_only' for claim-only mode")

# ============================================================
print("=" * 60)
print("Section 4: verify-chain completeness_verdict")
print("=" * 60)

check("4.1 A48 completeness_verdict block present in verify-chain",
      "A48: Compute completeness_verdict for verify-chain" in cli_src,
      "verify-chain must contain A48 completeness_verdict computation comment")

check("4.2 verify-chain completeness_verdict = 'verified' (all entries verified)",
      cli_src.count('result["completeness_verdict"] = "verified"') >= 2,
      "verify-chain must set completeness_verdict='verified' for all-verified case")

check("4.3 verify-chain completeness_verdict = 'verified_partial'",
      'result["completeness_verdict"] = "verified_partial"' in cli_src,
      "verify-chain must set completeness_verdict='verified_partial' for partial case")

check("4.4 verify-chain completeness_verdict = 'verified_failed'",
      cli_src.count('result["completeness_verdict"] = "verified_failed"') >= 2,
      "verify-chain must set completeness_verdict='verified_failed' for all-failed case")

check("4.5 verify-chain completeness_verdict = 'claim_only' (no run_dir)",
      cli_src.count('result["completeness_verdict"] = "claim_only"') >= 2,
      "verify-chain must set completeness_verdict='claim_only' when no run_dir")

# ============================================================
print("=" * 60)
print("Section 5: verify-chain verification_mode suffix")
print("=" * 60)

check("5.1 A48 verification_mode suffix block present in verify-chain",
      "A48: Append completeness suffix to verification_mode" in cli_src,
      "verify-chain must contain A48 verification_mode suffix comment")

check("5.2 verification_mode suffix '_complete' for verified",
      '_vm += "_complete"' in cli_src,
      "verification_mode must append '_complete' for verified completeness")

check("5.3 verification_mode suffix '_partial' for verified_partial",
      '_vm += "_partial"' in cli_src,
      "verification_mode must append '_partial' for partial verification")

check("5.4 verification_mode suffix '_incomplete' for verified_failed",
      '_vm += "_incomplete"' in cli_src,
      "verification_mode must append '_incomplete' for failed completeness")

check("5.5 verification_mode suffix '_claim_only' for claim_only",
      '_vm += "_claim_only"' in cli_src,
      "verification_mode must append '_claim_only' for claim-only mode")

# ============================================================
print("=" * 60)
print("Section 6: Policy integration")
print("=" * 60)

check("6.1 completeness_strict extracted from policy in paper_verify",
      '_comp_strict = _policy_data.get("completeness_strict"' in cli_src,
      "completeness_strict must be read from policy data")

check("6.2 COMPLETENESS STRICT enforcement message present",
      "COMPLETENESS STRICT: verification failed" in cli_src,
      "strict mode must emit blocking message when verification fails")

check("6.3 Strict enforcement gated by _comp_strict and not _comp_verified",
      "if _comp_strict and not _comp_verified" in cli_src
      or "if _comp_strict and not _comp_report.get(" in cli_src,
      "strict enforcement must check both strict flag and verification result")

# ============================================================
print("=" * 60)
print("Section 7: JSON output")
print("=" * 60)

check("7.1 result['completeness'] assignment present",
      'result["completeness"] = _comp_report' in cli_src,
      "completeness report must be written to result dict")

check("7.2 completeness_verdict assignment present in result dict",
      'result["completeness_verdict"]' in cli_src,
      "completeness_verdict must be written to result dict")

check("7.3 trust_summary assigned to result dict",
      'result["trust_summary"] = _ts' in cli_src,
      "trust_summary must be written to result dict for JSON output")

# ============================================================
print("=" * 60)
print("Section 8: Test coverage")
print("=" * 60)

check("8.1 Test file exists",
      TEST_PATH.exists(),
      f"test file not found: {TEST_PATH}")

_test_a48_count = test_src.count("A48") + test_src.count("a48")
check("8.2 Tests reference A48 at least 4 times",
      _test_a48_count >= 4,
      f"found {_test_a48_count} references to A48 in tests")

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

check("8.7 Tests cover all completeness_verdict values",
      '"verified"' in test_src
      and '"verified_failed"' in test_src
      and '"claim_only"' in test_src,
      "tests should cover verified, verified_failed, and claim_only verdict values")

# ============================================================
print("=" * 60)
total = PASS + FAIL
print(f"A48 Validation: {PASS} passed, {FAIL} failed, {total} total")
print("=" * 60)

for r in RESULTS:
    print(r)

check("ALL A48 CHECKS PASSED", FAIL == 0)

sys.exit(0 if FAIL == 0 else 1)
