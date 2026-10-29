"""A49 Validation -- COMPLETENESS CLAIM BINDING.

Validates:
1. Completeness claim binding block in paper_verify
2. Trust status values for verified mode (matched, drift, no_claim)
3. Trust status values for claim-only and fallback modes
4. Drift warning message output
5. Non-strict completeness warning flag
6. Strict enforcement (no warning in strict mode)
7. Verify-chain claim-only fix (verified=False, claim_only=True)
8. Test coverage
"""

import sys
from pathlib import Path

PASS = 0
FAIL = 0
RESULTS: list = []

ROOT = Path(__file__).resolve().parent
CLI_PATH = ROOT / "src" / "ai_workflow_hub" / "cli.py"
TEST_PATH = ROOT / "tests" / "test_paper_a49_claim_binding.py"


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
print("Section 1: Completeness claim binding block in paper_verify")
print("=" * 60)

check("1.1 A49 claim binding marker present in paper_verify",
      "A49: Completeness claim binding" in cli_src,
      "paper_verify must contain A49 claim binding comment")

check("1.2 Stored completeness extracted from attestation for comparison",
      '_stored_comp = att_data.get("completeness", {}) if att_ok else {}' in cli_src,
      "stored completeness must be extracted from attestation when att_ok is True")

check("1.3 Comparison gated by verified mode and stored data presence",
      'if _comp_mode == "verified" and _stored_comp:' in cli_src,
      "claim binding comparison requires verified mode and non-empty stored completeness")

check("1.4 Stored complete field extracted with None default",
      '_stored_complete = _stored_comp.get("complete", None)' in cli_src,
      "stored complete must be extracted with None as default for comparison")

check("1.5 Recomputed complete assigned from _comp_verified",
      '_recomputed_complete = _comp_verified' in cli_src,
      "recomputed complete must come from the completeness verification result")

# ============================================================
print("=" * 60)
print("Section 2: Trust status values for verified mode")
print("=" * 60)

check("2.1 verified_matched set when stored matches recomputed",
      'result["completeness_trust_status"] = "verified_matched" if _claim_matches else "verified_drift"' in cli_src,
      "verified_matched and verified_drift must be set based on _claim_matches")

check("2.2 _claim_matches compares both complete and missing_count",
      '_claim_matches = (_stored_complete == _recomputed_complete' in cli_src
      and '_stored_missing == _recomputed_missing)' in cli_src,
      "claim match must compare both complete boolean and missing_count integer")

check("2.3 verified_no_claim set when verified mode but no stored completeness",
      'result["completeness_trust_status"] = "verified_no_claim"' in cli_src,
      "verified_no_claim must be set when mode is verified but no stored claim exists")

check("2.4 Verified-no-claim condition: verified mode and empty stored",
      'elif _comp_mode == "verified" and not _stored_comp:' in cli_src,
      "verified_no_claim condition must check mode=verified and empty stored completeness")

check("2.5 stored missing_count extracted with -1 sentinel default",
      '_stored_missing = _stored_comp.get("missing_count", -1)' in cli_src,
      "stored missing_count must use -1 sentinel so absent field causes drift")

# ============================================================
print("=" * 60)
print("Section 3: Trust status values for claim-only and fallback")
print("=" * 60)

check("3.1 claim_only_unverified set when claim-only with stored completeness",
      'result["completeness_trust_status"] = "claim_only_unverified"' in cli_src,
      "claim_only_unverified must be set for claim-only mode with stored data")

check("3.2 claim_only_no_claim set when claim-only without stored completeness",
      'result["completeness_trust_status"] = "claim_only_no_claim"' in cli_src,
      "claim_only_no_claim must be set for claim-only mode without stored data")

check("3.3 no_completeness set as fallback for other modes",
      'result["completeness_trust_status"] = "no_completeness"' in cli_src,
      "no_completeness must be set as fallback when mode is neither verified nor claim_only")

check("3.4 Claim-only-unverified condition: claim_only mode with stored data",
      'elif _comp_mode == "claim_only" and _stored_comp:' in cli_src,
      "claim_only_unverified condition must check mode=claim_only and non-empty stored")

check("3.5 Fallback else clause for no_completeness",
      cli_src.count('result["completeness_trust_status"] = "no_completeness"') == 1,
      "no_completeness must appear exactly once as the final fallback")

# ============================================================
print("=" * 60)
print("Section 4: Drift warning message")
print("=" * 60)

check("4.1 Yellow drift warning emitted on mismatch",
      "[yellow]Completeness drift:" in cli_src,
      "drift warning must use yellow colour and 'Completeness drift:' prefix")

check("4.2 Drift message includes stored complete value",
      "stored complete=" in cli_src,
      "drift message must report the stored complete value")

check("4.3 Drift message includes recomputed complete value",
      "recomputed complete=" in cli_src,
      "drift message must report the recomputed complete value")

check("4.4 Drift message includes missing count values",
      "missing=" in cli_src,
      "drift message must report stored and recomputed missing counts")

check("4.5 Drift warning gated by 'if not _claim_matches:'",
      "if not _claim_matches:" in cli_src,
      "drift warning must only fire when claim does not match")

# ============================================================
print("=" * 60)
print("Section 5: Non-strict completeness warning flag")
print("=" * 60)

check("5.1 A49 non-strict warning marker present",
      "A49: Non-strict completeness failure" in cli_src,
      "paper_verify must contain A49 non-strict warning comment")

check("5.2 completeness_warning=True set in result dict",
      'result["completeness_warning"] = True' in cli_src,
      "completeness_warning must be set to True in result dict")

check("5.3 Non-strict condition: not _comp_strict and not _comp_verified and mode=verified",
      "if not _comp_strict and not _comp_verified and _comp_mode" in cli_src,
      "non-strict warning must fire only when strict=False, verified=False, mode=verified")

check("5.4 Yellow non-strict warning message emitted",
      "[yellow]Completeness: non-strict failure (warning only)[/yellow]" in cli_src,
      "non-strict warning must emit a yellow Rich-formatted message")

# ============================================================
print("=" * 60)
print("Section 6: Strict enforcement (no warning in strict mode)")
print("=" * 60)

check("6.1 Strict enforcement block present after non-strict warning",
      "if _comp_strict and not _comp_verified:" in cli_src,
      "strict enforcement must check _comp_strict and not _comp_verified")

check("6.2 COMPLETENESS STRICT message present",
      "COMPLETENESS STRICT: verification failed" in cli_src,
      "strict mode must emit 'COMPLETENESS STRICT: verification failed'")

_nonstrict_pos = cli_src.find("if not _comp_strict and not _comp_verified")
_strict_pos = cli_src.find("if _comp_strict and not _comp_verified:")
check("6.3 Non-strict warning appears BEFORE strict enforcement",
      _nonstrict_pos >= 0 and _strict_pos > _nonstrict_pos,
      f"non_strict={_nonstrict_pos}, strict={_strict_pos}")

check("6.4 Strict message uses red colour",
      "[red]COMPLETENESS STRICT:" in cli_src,
      "strict enforcement message must use red colour")

# ============================================================
print("=" * 60)
print("Section 7: Verify-chain claim-only fix")
print("=" * 60)

check("7.1 A49 claim-only marker present in verify-chain",
      "A49: Without run_dir, mark as claim-only" in cli_src,
      "verify-chain must contain A49 claim-only marker comment")

check("7.2 Claim-only entries set verified=False",
      '_ce_entry["verified"] = False' in cli_src,
      "claim-only entries must have verified=False (A49 fix from A46's True)")

check("7.3 Claim-only entries set claim_only=True",
      '_ce_entry["claim_only"] = True' in cli_src,
      "claim-only entries must have claim_only=True")

check("7.4 Claim-only note message present",
      "no run_dir -- claim-only verification" in cli_src,
      "claim-only entries must include a note explaining the mode")

# Verify the A49 comment is near the claim_only assignment
_a49_vc_pos = cli_src.find("A49: Without run_dir, mark as claim-only")
_claim_only_pos = cli_src.find('_ce_entry["claim_only"] = True')
check("7.5 A49 marker is near claim_only assignment (within 200 chars)",
      _a49_vc_pos >= 0 and _claim_only_pos > _a49_vc_pos
      and (_claim_only_pos - _a49_vc_pos) < 200,
      f"a49_marker={_a49_vc_pos}, claim_only_assign={_claim_only_pos}")

# ============================================================
print("=" * 60)
print("Section 8: Test coverage")
print("=" * 60)

check("8.1 Test file exists",
      TEST_PATH.exists(),
      f"test file not found: {TEST_PATH}")

_test_a49_count = test_src.count("A49") + test_src.count("a49")
check("8.2 Tests reference A49 at least 4 times",
      _test_a49_count >= 4,
      f"found {_test_a49_count} references to A49 in tests")

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

check("8.7 Tests cover all trust_status values",
      '"verified_matched"' in test_src
      and '"verified_drift"' in test_src
      and '"verified_no_claim"' in test_src
      and '"claim_only_unverified"' in test_src
      and '"claim_only_no_claim"' in test_src,
      "tests should cover all completeness_trust_status values")

check("8.8 Tests cover verify-chain claim-only fix",
      '"claim_only"' in test_src
      and "verified" in test_src
      and "completeness_reverification" in test_src,
      "tests should verify that claim-only entries have verified=False and claim_only=True")

# ============================================================
print("=" * 60)
total = PASS + FAIL
print(f"A49 Validation: {PASS} passed, {FAIL} failed, {total} total")
print("=" * 60)

for r in RESULTS:
    print(r)

check("ALL A49 CHECKS PASSED", FAIL == 0)

sys.exit(0 if FAIL == 0 else 1)
