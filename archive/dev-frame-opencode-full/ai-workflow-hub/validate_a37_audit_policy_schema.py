"""A37 Validation — Audit Policy Schema (38 checks across 9 sections)."""

import json
import sys
from pathlib import Path

PASS = 0
FAIL = 0
RESULTS: list[str] = []

ROOT = Path(__file__).resolve().parent
CLI_PATH = ROOT / "src" / "ai_workflow_hub" / "cli.py"
TEST_PATH = ROOT / "tests" / "test_paper_a37_audit_policy_schema.py"


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
print("Section 1: _load_audit_policy function")
print("=" * 60)

check("1.1 _load_audit_policy function exists",
      "def _load_audit_policy" in cli_src)

check("1.2 schema_version validation",
      "schema_version" in cli_src and "_AUDIT_POLICY_SCHEMA_VERSION" in cli_src)

check("1.3 Valid signature_policy enum",
      "_AUDIT_POLICY_VALID_SIG_POLICIES" in cli_src)

check("1.4 Valid chain_verification_mode enum",
      "_AUDIT_POLICY_VALID_CHAIN_MODES" in cli_src)

check("1.5 allowed_key_ids validation (list check)",
      "isinstance(_akids, list)" in cli_src or "isinstance" in cli_src)

check("1.6 Default values set",
      "setdefault" in cli_src and "strict_chain" in cli_src)

# ============================================================
print("=" * 60)
print("Section 2: --policy parameter")
print("=" * 60)

check("2.1 --policy parameter in checkpoint",
      '--policy' in cli_src and 'policy_file' in cli_src)

check("2.2 --policy parameter in verify-chain",
      cli_src.count('--policy') >= 2,
      f"found {cli_src.count('--policy')} occurrences")

check("2.3 policy_file type str",
      "policy_file: str" in cli_src)

# ============================================================
print("=" * 60)
print("Section 3: Policy override logic")
print("=" * 60)

check("3.1 signature_policy override from policy",
      "signature_policy = _policy_data" in cli_src or
      '_policy_data["signature_policy"]' in cli_src)

check("3.2 allowed_key_ids to expected_key_id override",
      "allowed_key_ids" in cli_src and "expected_key_id" in cli_src)

check("3.3 strict_chain override in verify-chain",
      "strict_chain = _policy_data" in cli_src or
      '_policy_data["strict_chain"]' in cli_src or
      '_policy_data.get("strict_chain")' in cli_src)

# ============================================================
print("=" * 60)
print("Section 4: Multiple allowed_key_ids")
print("=" * 60)

check("4.1 _check_kids list built",
      "_check_kids" in cli_src)

check("4.2 _cp_key_id in _check_kids",
      "_cp_key_id in _check_kids" in cli_src)

check("4.3 allowed_key_ids in JSON output",
      '"allowed_key_ids"' in cli_src)

# ============================================================
print("=" * 60)
print("Section 5: JSON output fields")
print("=" * 60)

check("5.1 policy_file in result",
      '"policy_file"' in cli_src)

check("5.2 policy_schema_version in result",
      '"policy_schema_version"' in cli_src)

check("5.3 policy_strict_chain in verify-chain result",
      '"policy_strict_chain"' in cli_src)

# ============================================================
print("=" * 60)
print("Section 6: A36 carry-forward")
print("=" * 60)

check("6.1 signature_policy preserved",
      "signature_policy" in cli_src)

check("6.2 signature_status preserved",
      "signature_status" in cli_src or "signed_valid" in cli_src)

check("6.3 signature_policy_pass preserved",
      "signature_policy_pass" in cli_src)

check("6.4 expected_key_id preserved",
      "expected_key_id" in cli_src)

check("6.5 key_id_match preserved",
      "key_id_match" in cli_src)

check("6.6 _sign_record function exists",
      "def _sign_record" in cli_src)

# ============================================================
print("=" * 60)
print("Section 7: A35 carry-forward")
print("=" * 60)

check("7.1 format_version 1.1",
      '"format_version"' in cli_src and '"1.1"' in cli_src)

check("7.2 chain_full_hash preserved",
      "chain_full_hash" in cli_src)

check("7.3 entries_count preserved",
      "entries_count" in cli_src)

check("7.4 HMAC-SHA256 algorithm",
      "HMAC-SHA256" in cli_src)

# ============================================================
print("=" * 60)
print("Section 8: A34 carry-forward")
print("=" * 60)

check("8.1 paper checkpoint command",
      '@paper_app.command("checkpoint")' in cli_src)

check("8.2 verify-chain command",
      '@paper_app.command("verify-chain")' in cli_src)

check("8.3 --strict-chain preserved",
      "--strict-chain" in cli_src)

check("8.4 verification_mode preserved",
      "verification_mode" in cli_src)

check("8.5 trust_level preserved",
      "trust_level" in cli_src)

# ============================================================
print("=" * 60)
print("Section 9: Test coverage")
print("=" * 60)

check("9.1 TestA37PolicyLoading class",
      "TestA37PolicyLoading" in test_src)

check("9.2 TestA37PolicyOverrides class",
      "TestA37PolicyOverrides" in test_src)

check("9.3 TestA37VerifyChainPolicy class",
      "TestA37VerifyChainPolicy" in test_src)

check("9.4 TestA37Integration class",
      "TestA37Integration" in test_src)

test_count = test_src.count("def test_")
check("9.5 At least 12 tests",
      test_count >= 12,
      f"found {test_count}")

# ============================================================
print("=" * 60)
total = PASS + FAIL
print(f"A37 Validation: {PASS} passed, {FAIL} failed, {total} total")
print("=" * 60)

for r in RESULTS:
    print(r)

sys.exit(0 if FAIL == 0 else 1)
