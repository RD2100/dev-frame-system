"""A46 Validation -- POLICY-GOVERNED-COMPLETENESS-PROOF (policy-controlled artifact classification)."""

import sys
from pathlib import Path

PASS = 0
FAIL = 0
RESULTS: list = []

ROOT = Path(__file__).resolve().parent
CLI_PATH = ROOT / "src" / "ai_workflow_hub" / "cli.py"
TEST_PATH = ROOT / "tests" / "test_paper_a46_policy_completeness.py"


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
print("Section 1: Policy schema A46 fields")
print("=" * 60)

check("1.1 completeness_strict in _AUDIT_POLICY_JSON_SCHEMA",
      '"completeness_strict"' in cli_src
      and '_AUDIT_POLICY_JSON_SCHEMA' in cli_src
      and '"boolean"' in cli_src,
      "completeness_strict must be declared in the JSON schema")

check("1.2 ignored_artifacts in _AUDIT_POLICY_JSON_SCHEMA",
      '"ignored_artifacts"' in cli_src
      and '"array"' in cli_src,
      "ignored_artifacts must be declared as array type in the JSON schema")

check("1.3 generated_artifacts in _AUDIT_POLICY_JSON_SCHEMA",
      '"generated_artifacts"' in cli_src
      and '"array"' in cli_src,
      "generated_artifacts must be declared as array type in the JSON schema")

check("1.4 fnmatch imported in cli.py",
      "import fnmatch" in cli_src,
      "fnmatch module must be imported for glob pattern matching")

# ============================================================
print("=" * 60)
print("Section 2: Policy loading A46 defaults")
print("=" * 60)

check("2.1 _load_audit_policy sets completeness_strict default",
      'policy.setdefault("completeness_strict", False)' in cli_src,
      "_load_audit_policy must set default for completeness_strict")

check("2.2 _load_audit_policy sets ignored_artifacts default",
      'policy.setdefault("ignored_artifacts", [])' in cli_src,
      "_load_audit_policy must set default for ignored_artifacts")

check("2.3 _load_audit_policy sets generated_artifacts default",
      'policy.setdefault("generated_artifacts", [])' in cli_src,
      "_load_audit_policy must set default for generated_artifacts")

# ============================================================
print("=" * 60)
print("Section 3: Completeness classification")
print("=" * 60)

check("3.1 _matches_patterns function exists",
      "def _matches_patterns" in cli_src,
      "_matches_patterns helper function must be defined")

check("3.2 fnmatch.fnmatch used in _matches_patterns",
      "fnmatch.fnmatch(rel_path" in cli_src
      or "fnmatch.fnmatch(_rel" in cli_src,
      "fnmatch.fnmatch must be called for pattern matching")

check("3.3 _policy_ignored extracted from policy data",
      '_policy_ignored = _policy_data.get("ignored_artifacts"' in cli_src,
      "_policy_ignored must be extracted from policy data")

check("3.4 _policy_generated extracted from policy data",
      '_policy_generated = _policy_data.get("generated_artifacts"' in cli_src,
      "_policy_generated must be extracted from policy data")

check("3.5 _audit_generated merged with policy patterns",
      "_audit_generated.add(_gp)" in cli_src
      or "_audit_generated |= " in cli_src,
      "policy generated patterns must be merged into audit-generated set")

# ============================================================
print("=" * 60)
print("Section 4: Hash-redacted reporting")
print("=" * 60)

check("4.1 path_hash in missing_from_bundle items",
      '"path_hash"' in cli_src
      and "_missing_hashed" in cli_src,
      "missing_from_bundle items must include path_hash field")

check("4.2 basename in missing_from_bundle items",
      '"basename"' in cli_src
      and "Path(_mf).name" in cli_src,
      "missing_from_bundle items must include basename field")

check("4.3 hashlib.sha256 used for path hashing",
      "hashlib.sha256(_mf.encode" in cli_src,
      "hashlib.sha256 must be used to hash-redact file paths")

# Raw paths must NOT appear in the missing_from_bundle output
_has_raw_path_leak = '"missing_from_bundle": _missing_from_bundle' in cli_src
check("4.4 Raw paths NOT exposed in missing_from_bundle",
      not _has_raw_path_leak,
      "missing_from_bundle must use hashed entries, not raw path strings")

# ============================================================
print("=" * 60)
print("Section 5: Completeness strict enforcement")
print("=" * 60)

check("5.1 _completeness_strict extracted from policy",
      '_completeness_strict = _policy_data.get("completeness_strict"' in cli_src,
      "_completeness_strict must be extracted from policy data")

check("5.2 raise typer.Exit(1) when strict + missing",
      "if _completeness_strict:" in cli_src
      and "raise typer.Exit(1)" in cli_src,
      "completeness_strict must block with typer.Exit(1) when files are missing")

check("5.3 Red severity message when strict",
      '_severity = "red" if _completeness_strict else "yellow"' in cli_src,
      "severity must be red when completeness_strict is True")

check("5.4 'COMPLETENESS STRICT' text in blocking message",
      "COMPLETENESS STRICT" in cli_src,
      "blocking message must contain 'COMPLETENESS STRICT' text")

# ============================================================
print("=" * 60)
print("Section 6: Completeness report structure")
print("=" * 60)

check("6.1 total_ignored field in report",
      '"total_ignored"' in cli_src,
      "completeness report must include total_ignored field")

check("6.2 completeness_strict field in report",
      '"completeness_strict": _completeness_strict' in cli_src,
      "completeness report must include completeness_strict field")

check("6.3 policy_governed field in report",
      '"policy_governed"' in cli_src,
      "completeness report must include policy_governed field")

check("6.4 policy_sha256 field in report",
      '"policy_sha256"' in cli_src
      and '_completeness_report["policy_sha256"]' in cli_src,
      "completeness report must include policy_sha256 from provenance")

check("6.5 missing_from_bundle is list of dicts (not strings)",
      '_missing_hashed.append({"path_hash"' in cli_src
      and '"missing_from_bundle": _missing_hashed' in cli_src,
      "missing_from_bundle must be a list of dicts with path_hash/basename")

# ============================================================
print("=" * 60)
print("Section 7: Verify-chain A46 options")
print("=" * 60)

check("7.1 --completeness-check on verify-chain",
      '"verify-chain"' in cli_src
      and cli_src.count('"--completeness-check"') >= 2,
      "--completeness-check must be an option on verify-chain (>=2 occurrences total)")

check("7.2 --run-dir on verify-chain",
      '"--run-dir"' in cli_src
      and "run_dir: Optional[str]" in cli_src,
      "--run-dir must be an option on verify-chain for re-verification")

check("7.3 completeness_reverification in result",
      '"completeness_reverification"' in cli_src
      and 'result["completeness_reverification"]' in cli_src,
      "verify-chain result must include completeness_reverification field")

check("7.4 Completeness re-verification loop exists",
      "for _ce_idx, _ce in enumerate(entries)" in cli_src
      and "_completeness_results" in cli_src,
      "verify-chain must iterate over anchor entries for completeness re-verification")

# ============================================================
print("=" * 60)
print("Section 8: Test coverage")
print("=" * 60)

check("8.1 Test file exists",
      TEST_PATH.exists(),
      f"test file not found: {TEST_PATH}")

_test_a46_count = test_src.count("A46") + test_src.count("a46")
check("8.2 Tests reference A46",
      _test_a46_count >= 4,
      f"found {_test_a46_count} references to A46 in tests")

_test_class_count = test_src.count("class Test")
check("8.3 At least 4 test classes",
      _test_class_count >= 4,
      f"found {_test_class_count} test classes")

test_count = test_src.count("def test_")
check("8.4 At least 10 test functions",
      test_count >= 10,
      f"found {test_count}")

check("8.5 Tests use CliRunner and patch",
      "CliRunner" in test_src and "patch" in test_src,
      "tests should use CliRunner and unittest.mock.patch")

check("8.6 Tests use policy JSON",
      "json.dumps" in test_src
      and "_valid_policy" in test_src
      and "_make_policy" in test_src,
      "tests should construct policy JSON files for testing")

# ============================================================
print("=" * 60)
total = PASS + FAIL
print(f"A46 Validation: {PASS} passed, {FAIL} failed, {total} total")
print("=" * 60)

for r in RESULTS:
    print(r)

check("ALL A46 CHECKS PASSED", FAIL == 0)

sys.exit(0 if FAIL == 0 else 1)
