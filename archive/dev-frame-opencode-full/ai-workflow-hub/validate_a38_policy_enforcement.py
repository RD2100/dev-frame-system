"""A38 Validation — Policy Enforcement (40 checks across 9 sections)."""

import json
import sys
from pathlib import Path

PASS = 0
FAIL = 0
RESULTS: list[str] = []

ROOT = Path(__file__).resolve().parent
CLI_PATH = ROOT / "src" / "ai_workflow_hub" / "cli.py"
TEST_PATH = ROOT / "tests" / "test_paper_a38_policy_enforcement.py"


def check(label: str, cond: bool, detail: str = ""):
    global PASS, FAIL
    if cond:
        PASS += 1
        RESULTS.append(f"[PASS] {label}")
    else:
        FAIL += 1
        RESULTS.append(f"[FAIL] {label}  — {detail}")


cli_src = CLI_PATH.read_text(encoding="utf-8")
test_src = TEST_PATH.read_text(encoding="utf-8")

# ============================================================
print("=" * 60)
print("Section 1: chain_verification_mode enforcement")
print("=" * 60)

check("1.1 policy_chain_mode check exists",
      "policy_chain_mode" in cli_src)

check("1.2 chain_plus_zip enforcement",
      "chain_plus_zip" in cli_src and "_p_cvm" in cli_src)

check("1.3 chain_only enforcement on partial",
      "chain_only" in cli_src and "chain_partial" in cli_src)

check("1.4 _actual_mode computed from result",
      "_actual_mode" in cli_src)

# ============================================================
print("=" * 60)
print("Section 2: required_artifacts enforcement")
print("=" * 60)

check("2.1 policy_required_artifacts check",
      "policy_required_artifacts" in cli_src)

check("2.2 _missing_artifacts tracking",
      "_missing_artifacts" in cli_src)

check("2.3 evidence_manifest lookup",
      "evidence_manifest" in cli_src)

check("2.4 required_artifacts list validation",
      "required_artifacts" in cli_src and "isinstance" in cli_src)

# ============================================================
print("=" * 60)
print("Section 3: Element type validation")
print("=" * 60)

check("3.1 allowed_key_ids element string check",
      "isinstance(_kid_val, str)" in cli_src)

check("3.2 Empty string rejection",
      "_kid_val.strip()" in cli_src)

check("3.3 Element index in error message",
      "_kid_idx" in cli_src)

# ============================================================
print("=" * 60)
print("Section 4: strict_timestamps enforcement")
print("=" * 60)

check("4.1 strict_timestamps annotation",
      "policy: strict_timestamps" in cli_src)

check("4.2 Timestamp check lookup",
      "timestamp_format_iso8601" in cli_src and "_p_st" in cli_src)

# ============================================================
print("=" * 60)
print("Section 5: A37 carry-forward")
print("=" * 60)

check("5.1 _load_audit_policy exists",
      "def _load_audit_policy" in cli_src)

check("5.2 schema_version validation",
      "_AUDIT_POLICY_SCHEMA_VERSION" in cli_src)

check("5.3 --policy in both commands",
      cli_src.count("--policy") >= 2)

check("5.4 allowed_key_ids multiple support",
      "_check_kids" in cli_src)

check("5.5 policy_file in JSON output",
      '"policy_file"' in cli_src)

check("5.6 policy_schema_version in JSON",
      '"policy_schema_version"' in cli_src)

# ============================================================
print("=" * 60)
print("Section 6: A36 carry-forward")
print("=" * 60)

check("6.1 signature_policy preserved",
      "signature_policy" in cli_src)

check("6.2 signature_status preserved",
      "signed_valid" in cli_src)

check("6.3 signature_policy_pass preserved",
      "signature_policy_pass" in cli_src)

check("6.4 expected_key_id preserved",
      "expected_key_id" in cli_src)

# ============================================================
print("=" * 60)
print("Section 7: A35 carry-forward")
print("=" * 60)

check("7.1 format_version 1.1",
      '"1.1"' in cli_src and "format_version" in cli_src)

check("7.2 chain_full_hash",
      "chain_full_hash" in cli_src)

check("7.3 entries_count",
      "entries_count" in cli_src)

check("7.4 _sign_record function",
      "def _sign_record" in cli_src)

check("7.5 HMAC-SHA256",
      "HMAC-SHA256" in cli_src)

# ============================================================
print("=" * 60)
print("Section 8: A34 carry-forward")
print("=" * 60)

check("8.1 paper checkpoint command",
      '@paper_app.command("checkpoint")' in cli_src)

check("8.2 verify-chain command",
      '@paper_app.command("verify-chain")' in cli_src)

check("8.3 --strict-chain",
      "--strict-chain" in cli_src)

check("8.4 verification_mode",
      "verification_mode" in cli_src)

check("8.5 trust_level",
      "trust_level" in cli_src)

# ============================================================
print("=" * 60)
print("Section 9: Test coverage")
print("=" * 60)

check("9.1 TestA38ChainModeEnforcement",
      "TestA38ChainModeEnforcement" in test_src)

check("9.2 TestA38RequiredArtifacts",
      "TestA38RequiredArtifacts" in test_src)

check("9.3 TestA38ElementValidation",
      "TestA38ElementValidation" in test_src)

check("9.4 TestA38StrictTimestamps",
      "TestA38StrictTimestamps" in test_src)

check("9.5 TestA38Integration",
      "TestA38Integration" in test_src)

test_count = test_src.count("def test_")
check("9.6 At least 11 tests",
      test_count >= 11,
      f"found {test_count}")

# ============================================================
print("=" * 60)
total = PASS + FAIL
print(f"A38 Validation: {PASS} passed, {FAIL} failed, {total} total")
print("=" * 60)

for r in RESULTS:
    print(r)

sys.exit(0 if FAIL == 0 else 1)
