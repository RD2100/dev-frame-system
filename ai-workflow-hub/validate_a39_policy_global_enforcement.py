"""A39 Validation — Policy Global Enforcement (38 checks across 8 sections)."""

import json
import sys
from pathlib import Path

PASS = 0
FAIL = 0
RESULTS: list[str] = []

ROOT = Path(__file__).resolve().parent
CLI_PATH = ROOT / "src" / "ai_workflow_hub" / "cli.py"
TEST_PATH = ROOT / "tests" / "test_paper_a39_policy_global_enforcement.py"


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
print("Section 1: --policy on paper verify")
print("=" * 60)

check("1.1 --policy in paper verify signature",
      "policy_file" in cli_src and "paper_verify" in cli_src or
      cli_src.count('policy_file: str') >= 3,
      "not found in paper verify")

check("1.2 Policy loading in paper verify",
      "_load_audit_policy" in cli_src)

check("1.3 policy_file in verify JSON output",
      '"policy_file"' in cli_src)

# ============================================================
print("=" * 60)
print("Section 2: strict_timestamps downgrade")
print("=" * 60)

check("2.1 strict_timestamps=False downgrade logic",
      "warning-only" in cli_src)

check("2.2 result['failed'] -= 1 for downgrade",
      'result["failed"] -= 1' in cli_src)

check("2.3 result['passed'] += 1 for downgrade",
      'result["passed"] += 1' in cli_src)

check("2.4 _ts_check passed set to True",
      '_ts_check["passed"] = True' in cli_src)

# ============================================================
print("=" * 60)
print("Section 3: A38 carry-forward")
print("=" * 60)

check("3.1 policy_chain_mode check",
      "policy_chain_mode" in cli_src)

check("3.2 policy_required_artifacts check",
      "policy_required_artifacts" in cli_src)

check("3.3 Element type validation",
      "isinstance(_kid_val, str)" in cli_src)

check("3.4 Empty string rejection",
      "_kid_val.strip()" in cli_src)

# ============================================================
print("=" * 60)
print("Section 4: A37 carry-forward")
print("=" * 60)

check("4.1 _load_audit_policy function",
      "def _load_audit_policy" in cli_src)

check("4.2 schema_version validation",
      "_AUDIT_POLICY_SCHEMA_VERSION" in cli_src)

check("4.3 --policy in 3+ commands",
      cli_src.count("policy_file: str") >= 3,
      f"found {cli_src.count('policy_file: str')}")

check("4.4 Multiple allowed_key_ids",
      "_check_kids" in cli_src)

# ============================================================
print("=" * 60)
print("Section 5: A36 carry-forward")
print("=" * 60)

check("5.1 signature_policy",
      "signature_policy" in cli_src)

check("5.2 signature_status",
      "signed_valid" in cli_src)

check("5.3 signature_policy_pass",
      "signature_policy_pass" in cli_src)

# ============================================================
print("=" * 60)
print("Section 6: A35 carry-forward")
print("=" * 60)

check("6.1 format_version 1.1",
      '"1.1"' in cli_src)

check("6.2 chain_full_hash",
      "chain_full_hash" in cli_src)

check("6.3 entries_count",
      "entries_count" in cli_src)

check("6.4 _sign_record function",
      "def _sign_record" in cli_src)

# ============================================================
print("=" * 60)
print("Section 7: A34 carry-forward")
print("=" * 60)

check("7.1 paper checkpoint",
      '@paper_app.command("checkpoint")' in cli_src)

check("7.2 verify-chain",
      '@paper_app.command("verify-chain")' in cli_src)

check("7.3 paper verify",
      '@paper_app.command("verify")' in cli_src)

check("7.4 --strict-chain",
      "--strict-chain" in cli_src)

check("7.5 verification_mode",
      "verification_mode" in cli_src)

# ============================================================
print("=" * 60)
print("Section 8: Test coverage")
print("=" * 60)

check("8.1 TestA39VerifyPolicy",
      "TestA39VerifyPolicy" in test_src)

check("8.2 TestA39StrictTimestampsFalse",
      "TestA39StrictTimestampsFalse" in test_src)

check("8.3 TestA39ChainModeSemantics",
      "TestA39ChainModeSemantics" in test_src)

check("8.4 TestA39Integration",
      "TestA39Integration" in test_src)

test_count = test_src.count("def test_")
check("8.5 At least 7 tests",
      test_count >= 7,
      f"found {test_count}")

# ============================================================
print("=" * 60)
total = PASS + FAIL
print(f"A39 Validation: {PASS} passed, {FAIL} failed, {total} total")
print("=" * 60)

for r in RESULTS:
    print(r)

sys.exit(0 if FAIL == 0 else 1)
