"""A47 Validation -- VERIFIER-SIDE COMPLETENESS RE-VERIFICATION.

Validates:
1. --completeness-check option on paper verify
2. Completeness re-verification logic
3. Run directory scanning
4. Policy-controlled classification
5. Hash-redacted reporting
6. Claim-only fallback
7. Completeness report in result JSON
8. Test coverage
"""

import sys
from pathlib import Path

PASS = 0
FAIL = 0
RESULTS: list = []

ROOT = Path(__file__).resolve().parent
CLI_PATH = ROOT / "src" / "ai_workflow_hub" / "cli.py"
TEST_PATH = ROOT / "tests" / "test_paper_a47_completeness_verify.py"


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
print("Section 1: --completeness-check option on paper verify")
print("=" * 60)

check("1.1 --completeness-check declared on paper_verify",
      'def paper_verify(' in cli_src
      and '--completeness-check' in cli_src
      and 'Re-verify completeness from bundle vs run directory (A47)' in cli_src,
      "--completeness-check must be a Typer option on paper_verify with A47 help text")

check("1.2 completeness_check typed as bool with default False",
      'completeness_check: bool = typer.Option(False, "--completeness-check"' in cli_src,
      "completeness_check must be bool with default False")

# Count how many commands have --completeness-check (audit, verify, verify-chain)
_completeness_occurrences = cli_src.count('"--completeness-check"')
check("1.3 --completeness-check present on >=3 commands (audit, verify, verify-chain)",
      _completeness_occurrences >= 3,
      f"found {_completeness_occurrences} occurrences (expected >=3)")

# ============================================================
print("=" * 60)
print("Section 2: Completeness re-verification logic")
print("=" * 60)

check("2.1 A47 completeness block gated by 'if completeness_check:'",
      "if completeness_check:" in cli_src
      and "A47 Completeness Re-verification" in cli_src,
      "completeness re-verification must be gated by the flag")

check("2.2 Full re-verification condition: run_dir and bm_ok and bm_data.get('files')",
      "if run_dir and bm_ok and bm_data.get(" in cli_src,
      "full re-verification requires run_dir, valid bundle manifest, and files list")

check("2.3 Completeness report initialised with mode='unknown' and verified=False",
      '"mode": "unknown"' in cli_src
      and '"verified": False' in cli_src,
      "completeness report must be initialised with defaults before branching")

check("2.4 result['completeness'] assigned after branching",
      'result["completeness"] = _comp_report' in cli_src,
      "the completeness report must be written to the result dict")

check("2.5 completeness_strict enforcement message",
      "COMPLETENESS STRICT: verification failed" in cli_src
      and "if _comp_strict and not _comp_report.get(" in cli_src,
      "strict mode must emit blocking message when verification fails")

# ============================================================
print("=" * 60)
print("Section 3: Run directory scanning")
print("=" * 60)

check("3.1 _rd = Path(run_dir) with existence check",
      "_rd = Path(run_dir)" in cli_src
      and "if _rd.exists():" in cli_src,
      "run directory must be converted to Path and checked for existence")

check("3.2 Recursive scan with _rd.rglob('*')",
      "_rd.rglob(" in cli_src,
      "run directory must be scanned recursively")

check("3.3 Relative path computed with forward-slash normalisation",
      '_rp.relative_to(_rd)).replace("\\\\"' in cli_src
      or '_rp.relative_to(_rd)).replace("\\\\' in cli_src,
      "relative paths must use forward slashes for cross-platform consistency")

check("3.4 _rd_ignored set tracked separately from _rd_files",
      "_rd_ignored: set[str] = set()" in cli_src
      and "_rd_ignored.add(_rel)" in cli_src,
      "ignored files must be tracked in a separate set")

# ============================================================
print("=" * 60)
print("Section 4: Policy-controlled classification")
print("=" * 60)

check("4.1 _policy_ignored extracted from policy data in verify",
      '_policy_ignored = _policy_data.get("ignored_artifacts"' in cli_src,
      "ignored_artifacts must be read from policy in the verify command")

check("4.2 _policy_generated extracted from policy data in verify",
      '_policy_generated = _policy_data.get("generated_artifacts"' in cli_src,
      "generated_artifacts must be read from policy in the verify command")

check("4.3 fnmatch.fnmatch used for glob matching (both full path and basename)",
      "fnmatch.fnmatch(_rel, _pat)" in cli_src
      and "fnmatch.fnmatch(Path(_rel).name, _pat)" in cli_src,
      "glob matching must test both full relative path and basename")

check("4.4 Policy generated artifacts merged into _audit_generated set",
      "_audit_generated.add(_gp)" in cli_src
      or "for _gp in _policy_generated" in cli_src,
      "policy generated_artifacts must be merged into the audit-generated set")

# ============================================================
print("=" * 60)
print("Section 5: Hash-redacted reporting")
print("=" * 60)

check("5.1 path_hash in missing_from_bundle items",
      '"path_hash": _mh' in cli_src
      and "_missing_hashed" in cli_src,
      "missing_from_bundle items must include path_hash field")

check("5.2 basename in missing_from_bundle items",
      '"basename": Path(_mf).name' in cli_src,
      "missing_from_bundle items must include basename field")

check("5.3 hashlib.sha256 used for path hashing with 16-char truncation",
      "hashlib.sha256(_mf.encode" in cli_src
      and ".hexdigest()[:16]" in cli_src,
      "hashlib.sha256 must be used to hash-redact file paths (truncated to 16 chars)")

check("5.4 _missing_hashed is a list of dicts (not raw strings)",
      '_missing_hashed.append({"path_hash"' in cli_src,
      "missing entries must be dicts with path_hash/basename, not raw strings")

# ============================================================
print("=" * 60)
print("Section 6: Claim-only fallback")
print("=" * 60)

check("6.1 Claim-only mode when no run_dir",
      '"mode": "claim_only"' in cli_src,
      "claim-only mode must set mode to 'claim_only'")

check("6.2 Stored completeness extracted from attestation",
      'att_data.get("completeness"' in cli_src
      and "if att_ok" in cli_src,
      "stored completeness must be read from attestation when att_ok is True")

check("6.3 Distinct checks for claim_present vs claim_absent",
      "completeness_claim_present" in cli_src
      and "no stored completeness in attestation" in cli_src,
      "claim-only must distinguish between present and absent stored completeness")

# ============================================================
print("=" * 60)
print("Section 7: Completeness report in result JSON")
print("=" * 60)

check("7.1 'verified' mode set in full re-verification",
      '"mode": "verified"' in cli_src,
      "full re-verification must set mode to 'verified'")

check("7.2 total_ignored field in verified report",
      '"total_ignored": len(_rd_ignored)' in cli_src,
      "verified report must include total_ignored count")

check("7.3 completeness_strict field in verified report",
      '"completeness_strict": _comp_strict' in cli_src,
      "verified report must include completeness_strict flag")

check("7.4 policy_governed field in verified report",
      '"policy_governed": bool(_policy_data)' in cli_src,
      "verified report must include policy_governed flag")

check("7.5 complete and missing_count fields in verified report",
      '"complete": len(_missing) == 0' in cli_src
      and '"missing_count": len(_missing)' in cli_src,
      "verified report must include complete boolean and missing_count integer")

# ============================================================
print("=" * 60)
print("Section 8: Test coverage")
print("=" * 60)

check("8.1 Test file exists",
      TEST_PATH.exists(),
      f"test file not found: {TEST_PATH}")

_test_a47_count = test_src.count("A47") + test_src.count("a47")
check("8.2 Tests reference A47",
      _test_a47_count >= 4,
      f"found {_test_a47_count} references to A47 in tests")

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
      and 'result.stdout' in test_src,
      "tests should use CliRunner and parse JSON from stdout")

check("8.6 Tests create real ZIP files with zipfile",
      "zipfile" in test_src or "zf_mod" in test_src,
      "tests should create real ZIP files for verification")

check("8.7 Tests cover claim_only and verified modes",
      '"claim_only"' in test_src
      and '"verified"' in test_src,
      "tests should cover both claim_only and verified completeness modes")

# ============================================================
print("=" * 60)
total = PASS + FAIL
print(f"A47 Validation: {PASS} passed, {FAIL} failed, {total} total")
print("=" * 60)

for r in RESULTS:
    print(r)

check("ALL A47 CHECKS PASSED", FAIL == 0)

sys.exit(0 if FAIL == 0 else 1)
