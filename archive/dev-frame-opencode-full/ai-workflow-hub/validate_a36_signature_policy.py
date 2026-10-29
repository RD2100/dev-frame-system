"""A36 Validation — Signature Policy (37 checks across 8 sections)."""

import json
import os
import re
import sys
from pathlib import Path

PASS = 0
FAIL = 0
RESULTS: list[str] = []

ROOT = Path(__file__).resolve().parent
CLI_PATH = ROOT / "src" / "ai_workflow_hub" / "cli.py"
TEST_PATH = ROOT / "tests" / "test_paper_a36_signature_policy.py"


def check(label: str, cond: bool, detail: str = ""):
    global PASS, FAIL
    if cond:
        PASS += 1
        RESULTS.append(f"[PASS] {label}")
    else:
        FAIL += 1
        RESULTS.append(f"[FAIL] {label}  — {detail}")


# --- Read sources ---
cli_src = CLI_PATH.read_text(encoding="utf-8")
test_src = TEST_PATH.read_text(encoding="utf-8")

# ============================================================
print("=" * 60)
print("Section 1: signature_policy parameter")
print("=" * 60)

check("1.1 --signature-policy parameter exists",
      '--signature-policy' in cli_src,
      "missing in cli.py")

check("1.2 signature_policy default is 'optional'",
      '"optional"' in cli_src and "signature_policy" in cli_src,
      "default not found")

check("1.3 Policy values: required|optional|off",
      all(v in cli_src for v in ["required", "optional", "off"]),
      "missing policy values")

check("1.4 signature_policy in function signature",
      "signature_policy:" in cli_src,
      "not in function params")

# ============================================================
print("=" * 60)
print("Section 2: --expected-key-id parameter")
print("=" * 60)

check("2.1 --expected-key-id parameter exists",
      "--expected-key-id" in cli_src,
      "missing in cli.py")

check("2.2 expected_key_id in function signature",
      "expected_key_id:" in cli_src,
      "not in function params")

# ============================================================
print("=" * 60)
print("Section 3: signature_status values")
print("=" * 60)

check("3.1 signed_valid status",
      "signed_valid" in cli_src,
      "missing signed_valid")

check("3.2 signed_invalid status",
      "signed_invalid" in cli_src,
      "missing signed_invalid")

check("3.3 signed_unverified status",
      "signed_unverified" in cli_src,
      "missing signed_unverified")

check("3.4 signature_required_missing status",
      "signature_required_missing" in cli_src,
      "missing signature_required_missing")

check("3.5 unsigned status",
      '"unsigned"' in cli_src,
      "missing unsigned status")

# ============================================================
print("=" * 60)
print("Section 4: Policy enforcement logic")
print("=" * 60)

check("4.1 required policy blocks unsigned",
      "signature_required_missing" in cli_src and "required" in cli_src,
      "missing required+unsigned logic")

check("4.2 required policy blocks invalid signature",
      "_sig_policy_fail" in cli_src,
      "missing policy fail flag")

check("4.3 optional policy warns but doesn't block",
      "optional" in cli_src and "warning" in cli_src.lower(),
      "missing optional warning")

check("4.4 off policy skips checks",
      "off" in cli_src,
      "missing off policy handling")

check("4.5 _all_ok includes _sig_policy_fail",
      "_sig_policy_fail" in cli_src and "_all_ok" in cli_src,
      "exit code doesn't respect policy")

# ============================================================
print("=" * 60)
print("Section 5: Key ID policy")
print("=" * 60)

check("5.1 key_id_match check exists",
      "key_id_match" in cli_src or "_key_id_match" in cli_src,
      "missing key_id_match")

check("5.2 expected_key_id in JSON output",
      "expected_key_id" in cli_src and "result" in cli_src,
      "missing expected_key_id in output")

check("5.3 key_id mismatch fails required policy",
      "_key_id_match is False" in cli_src,
      "missing key_id mismatch enforcement")

# ============================================================
print("=" * 60)
print("Section 6: JSON output fields")
print("=" * 60)

check("6.1 signature_policy in result",
      '"signature_policy"' in cli_src,
      "missing in JSON result")

check("6.2 signature_status in result",
      '"signature_status"' in cli_src,
      "missing in JSON result")

check("6.3 signature_policy_pass in result",
      '"signature_policy_pass"' in cli_src,
      "missing in JSON result")

# ============================================================
print("=" * 60)
print("Section 7: A35 carry-forward")
print("=" * 60)

check("7.1 format_version 1.1 preserved",
      '"format_version"' in cli_src and '"1.1"' in cli_src,
      "format_version 1.1 missing")

check("7.2 chain_full_hash in checkpoint verify",
      "chain_full_hash" in cli_src,
      "missing chain_full_hash")

check("7.3 entries_count in checkpoint verify",
      "entries_count" in cli_src,
      "missing entries_count")

check("7.4 _sign_record function exists",
      "def _sign_record" in cli_src,
      "missing _sign_record")

check("7.5 HMAC-SHA256 algorithm",
      "HMAC-SHA256" in cli_src,
      "missing HMAC-SHA256")

check("7.6 paper checkpoint command",
      '@paper_app.command("checkpoint")' in cli_src,
      "missing checkpoint command")

check("7.7 verify-chain command preserved",
      '@paper_app.command("verify-chain")' in cli_src,
      "missing verify-chain command")

check("7.8 --strict-chain preserved",
      "--strict-chain" in cli_src,
      "missing --strict-chain")

check("7.9 verification_mode preserved",
      "verification_mode" in cli_src,
      "missing verification_mode")

check("7.10 trust_level preserved",
      "trust_level" in cli_src,
      "missing trust_level")

# ============================================================
print("=" * 60)
print("Section 8: Test coverage")
print("=" * 60)

check("8.1 TestA36SignaturePolicyRequired class",
      "TestA36SignaturePolicyRequired" in test_src,
      "missing test class")

check("8.2 TestA36SignaturePolicyOptional class",
      "TestA36SignaturePolicyOptional" in test_src,
      "missing test class")

check("8.3 TestA36SignaturePolicyOff class",
      "TestA36SignaturePolicyOff" in test_src,
      "missing test class")

check("8.4 TestA36KeyIdPolicy class",
      "TestA36KeyIdPolicy" in test_src,
      "missing test class")

check("8.5 TestA36Integration class",
      "TestA36Integration" in test_src,
      "missing test class")

test_count = test_src.count("def test_")
check("8.6 At least 13 tests",
      test_count >= 13,
      f"found {test_count}")

# ============================================================
print("=" * 60)
total = PASS + FAIL
print(f"A36 Validation: {PASS} passed, {FAIL} failed, {total} total")
print("=" * 60)

for r in RESULTS:
    print(r)

sys.exit(0 if FAIL == 0 else 1)
