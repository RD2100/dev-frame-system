"""A50 Validation -- POLICY-ADJUSTED COMPLETENESS RESULTS.

Validates:
1. Raw completeness pass (before policy adjustment)
2. Policy-adjusted completeness outcome
3. Drift severity computation
4. Deeper claim comparison (5 dimensions)
5. Non-strict warning behaviour
6. Strict enforcement
7. Verdict and trust_summary integration
8. Test coverage
"""

import sys
from pathlib import Path

PASS = 0
FAIL = 0
RESULTS: list = []

ROOT = Path(__file__).resolve().parent
CLI_PATH = ROOT / "src" / "ai_workflow_hub" / "cli.py"
TEST_PATH = ROOT / "tests" / "test_paper_a50_policy_adjusted.py"


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
print("Section 1: Raw completeness pass (before policy adjustment)")
print("=" * 60)

check("1.1 A50 raw completeness marker present",
      "A50: Raw completeness pass" in cli_src,
      "paper_verify must contain A50 raw completeness comment")

check("1.2 raw_completeness_pass assigned to result dict",
      'result["raw_completeness_pass"]' in cli_src,
      "raw_completeness_pass must be written to result dict")

check("1.3 Ternary: _comp_verified when mode=='verified' else None",
      '_comp_verified if _comp_mode == "verified" else None' in cli_src,
      "raw_completeness_pass must be _comp_verified only for verified mode, None otherwise")

check("1.4 _comp_verified extracted from _comp_report",
      '_comp_verified = _comp_report.get("verified", False)' in cli_src,
      "_comp_verified must come from the completeness report's 'verified' field")

check("1.5 _comp_mode extracted from _comp_report",
      '_comp_mode = _comp_report.get("mode", "unknown")' in cli_src,
      "_comp_mode must come from the completeness report's 'mode' field")

# ============================================================
print("=" * 60)
print("Section 2: Policy-adjusted completeness outcome")
print("=" * 60)

check("2.1 A50 policy-adjusted marker present",
      "A50: Policy-adjusted completeness outcome" in cli_src,
      "paper_verify must contain A50 policy-adjusted comment")

check("2.2 policy_completeness_pass=True when verified+complete",
      'result["policy_completeness_pass"] = True' in cli_src,
      "policy_completeness_pass must be True when completeness passes")

check("2.3 completeness_policy_action='pass' when verified+complete",
      'result["completeness_policy_action"] = "pass"' in cli_src,
      "completeness_policy_action must be 'pass' when completeness passes")

check("2.4 policy_completeness_pass=False when strict block",
      'result["policy_completeness_pass"] = False' in cli_src,
      "policy_completeness_pass must be False when strict blocks")

check("2.5 completeness_policy_action='block' when strict block",
      'result["completeness_policy_action"] = "block"' in cli_src,
      "completeness_policy_action must be 'block' when strict enforcement fires")

check("2.6 policy_completeness_pass=None for non-verified modes",
      'result["policy_completeness_pass"] = None' in cli_src,
      "policy_completeness_pass must be None for claim_only, error, unknown modes")

check("2.7 Strict condition: verified + not verified + strict",
      'elif _comp_mode == "verified" and not _comp_verified and _comp_strict:' in cli_src,
      "strict block condition must check mode=verified, verified=False, strict=True")

# ============================================================
print("=" * 60)
print("Section 3: Drift severity computation")
print("=" * 60)

check("3.1 _drift_severity initialised to 'none'",
      '_drift_severity = "none"' in cli_src,
      "drift severity must default to 'none' before comparison")

check("3.2 High severity when drift_dims >= 2",
      'if _drift_dims >= 2:' in cli_src and '_drift_severity = "high"' in cli_src,
      "high severity must fire when 2 or more dimensions drift")

check("3.3 Low severity when drift_dims == 1",
      'elif _drift_dims == 1:' in cli_src and '_drift_severity = "low"' in cli_src,
      "low severity must fire when exactly 1 dimension drifts")

check("3.4 None severity when drift_dims == 0 (else clause)",
      '_drift_severity = "none"' in cli_src,
      "none severity must be set when no dimensions drift")

check("3.5 completeness_drift_severity assigned to result",
      'result["completeness_drift_severity"]' in cli_src,
      "drift severity must be written to result dict")

check("3.6 completeness_drift_dims assigned to result",
      'result["completeness_drift_dims"]' in cli_src,
      "drift dimension count must be written to result dict")

# ============================================================
print("=" * 60)
print("Section 4: Deeper claim comparison (5 dimensions)")
print("=" * 60)

check("4.1 Complete dimension: stored vs recomputed",
      '_stored_complete = _stored_comp.get("complete", None)' in cli_src
      and '_recomputed_complete = _comp_verified' in cli_src,
      "complete dimension must compare stored complete (None default) vs recomputed")

check("4.2 Complete mismatch adds 2 to drift_dims (high severity weight)",
      '_drift_dims += 2  # complete mismatch is high severity' in cli_src,
      "complete mismatch must weight 2 to immediately trigger high severity")

check("4.3 Sentinel -1 for missing_count, total_run_files, total_ignored",
      '_stored_missing = _stored_comp.get("missing_count", -1)' in cli_src
      and '_stored_run_files = _stored_comp.get("total_run_files", -1)' in cli_src
      and '_stored_ignored = _stored_comp.get("total_ignored", -1)' in cli_src,
      "missing_count, total_run_files, total_ignored must use -1 sentinel default")

check("4.4 policy_sha256 comparison gated by both values truthy",
      "if _stored_policy and _recomputed_policy and _stored_policy != _recomputed_policy:" in cli_src,
      "policy_sha256 drift must only fire when both stored and recomputed are non-empty")

check("4.5 _claim_matches derived from drift_dims == 0",
      "_claim_matches = (_drift_dims == 0)" in cli_src,
      "claim match must be True only when zero drift dimensions detected")

check("4.6 Sentinel skip: stored != -1 for missing_count",
      "if _stored_missing != _recomputed_missing and _stored_missing != -1:" in cli_src,
      "missing_count comparison must skip when stored is sentinel -1")

check("4.7 Sentinel skip: stored != -1 for total_run_files",
      "if _stored_run_files != _recomputed_run_files and _stored_run_files != -1:" in cli_src,
      "total_run_files comparison must skip when stored is sentinel -1")

check("4.8 Sentinel skip: stored != -1 for total_ignored",
      "if _stored_ignored != _recomputed_ignored and _stored_ignored != -1:" in cli_src,
      "total_ignored comparison must skip when stored is sentinel -1")

# ============================================================
print("=" * 60)
print("Section 5: Non-strict warning behaviour")
print("=" * 60)

check("5.1 A50 non-strict comment marker present",
      "A50: Non-strict" in cli_src,
      "paper_verify must contain A50 non-strict comment")

check("5.2 completeness_warning=True set in result dict",
      'result["completeness_warning"] = True' in cli_src,
      "completeness_warning must be set to True in result dict")

check("5.3 completeness_policy_action='warn' set in non-strict branch",
      'result["completeness_policy_action"] = "warn"' in cli_src,
      "completeness_policy_action must be 'warn' for non-strict failures")

check("5.4 Failed counter decremented for non-strict (verdict not forced)",
      'result["failed"] = max(0, result["failed"] - 1)' in cli_src,
      "failed counter must be decremented so verdict is not forced to 'failed'")

check("5.5 policy_completeness_pass=True in non-strict branch (pass with warning)",
      cli_src.count('result["policy_completeness_pass"] = True') >= 2,
      "policy_completeness_pass=True must appear in both pass and warn branches")

# ============================================================
print("=" * 60)
print("Section 6: Strict enforcement")
print("=" * 60)

check("6.1 COMPLETENESS STRICT message present",
      "COMPLETENESS STRICT: verification failed" in cli_src,
      "strict mode must emit 'COMPLETENESS STRICT: verification failed'")

check("6.2 Strict message uses red colour",
      "[red]COMPLETENESS STRICT:" in cli_src,
      "strict enforcement message must use red colour")

_policy_adj_pos = cli_src.find("A50: Policy-adjusted completeness outcome")
_strict_pos = cli_src.find('elif _comp_mode == "verified" and not _comp_verified and _comp_strict:',
                           _policy_adj_pos if _policy_adj_pos >= 0 else 0)
_nonstrict_pos = cli_src.find('elif _comp_mode == "verified" and not _comp_verified:',
                              _strict_pos + 1 if _strict_pos >= 0 else 0)
check("6.3 Strict branch appears before non-strict branch in policy block",
      _strict_pos >= 0 and _nonstrict_pos > _strict_pos,
      f"strict={_strict_pos}, non_strict={_nonstrict_pos}")

check("6.4 Non-strict branch does NOT emit red message",
      "[red]" not in cli_src[(_nonstrict_pos if _nonstrict_pos >= 0 else 0):
                              (_nonstrict_pos + 500 if _nonstrict_pos >= 0 else 0)],
      "non-strict branch must not use red colour (it is a warning, not a block)")

# ============================================================
print("=" * 60)
print("Section 7: Verdict and trust_summary integration")
print("=" * 60)

check("7.1 Final verdict computed after completeness blocks",
      "A48: Final verdict -- computed after ALL checks including completeness" in cli_src,
      "verdict computation must have A48 comment indicating post-completeness ordering")

check("7.2 Verdict assignment: 'passed' if failed == 0 else 'failed'",
      'result["verdict"] = "passed" if result["failed"] == 0 else "failed"' in cli_src,
      "verdict must use the standard passed/failed ternary")

check("7.3 Drift severity set to 'none' in all non-verified branches",
      cli_src.count('result["completeness_drift_severity"] = "none"') >= 4,
      "drift severity must default to 'none' for verified_no_claim, claim_only, and fallback")

check("7.4 Drift warning message includes severity and dims",
      "Completeness drift (" in cli_src
      and "_drift_severity" in cli_src
      and "_drift_dims" in cli_src,
      "drift warning must include severity level and dimension count")

# ============================================================
print("=" * 60)
print("Section 8: Test coverage")
print("=" * 60)

check("8.1 Test file exists",
      TEST_PATH.exists(),
      f"test file not found: {TEST_PATH}")

_test_a50_count = test_src.count("A50") + test_src.count("a50")
check("8.2 Tests reference A50 at least 4 times",
      _test_a50_count >= 4,
      f"found {_test_a50_count} references to A50 in tests")

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

check("8.7 Tests cover raw_completeness_pass and policy_completeness_pass",
      '"raw_completeness_pass"' in test_src
      and '"policy_completeness_pass"' in test_src,
      "tests should cover both raw and policy completeness pass fields")

check("8.8 Tests cover drift severity levels",
      '"completeness_drift_severity"' in test_src
      and '"none"' in test_src
      and '"low"' in test_src
      and '"high"' in test_src,
      "tests should cover all drift severity levels (none, low, high)")

check("8.9 Tests cover completeness_policy_action values",
      '"completeness_policy_action"' in test_src
      and '"pass"' in test_src
      and '"block"' in test_src
      and '"warn"' in test_src,
      "tests should cover all policy action values (pass, block, warn)")

# ============================================================
print("=" * 60)
total = PASS + FAIL
print(f"A50 Validation: {PASS} passed, {FAIL} failed, {total} total")
print("=" * 60)

for r in RESULTS:
    print(r)

check("ALL A50 CHECKS PASSED", FAIL == 0)

sys.exit(0 if FAIL == 0 else 1)
