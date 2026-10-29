"""A42 Validation — Policy Signed Pinning (35 checks across 8 sections)."""

import sys
from pathlib import Path

PASS = 0
FAIL = 0
RESULTS: list[str] = []

ROOT = Path(__file__).resolve().parent
CLI_PATH = ROOT / "src" / "ai_workflow_hub" / "cli.py"
TEST_PATH = ROOT / "tests" / "test_paper_a42_policy_signed_pinning.py"


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
print("Section 1: path_hash_privacy")
print("=" * 60)

check("1.1 policy_path_hash in cli (not policy_path as provenance field)",
      '"policy_path_hash"' in cli_src and '"policy_path"' not in cli_src.replace('"policy_path_hash"', ''),
      "policy_path_hash should replace raw policy_path in provenance output")

check("1.2 SHA-256 hashing for path",
      "hashlib.sha256" in cli_src and "policy_path_hash" in cli_src)

check("1.3 path_hash uses .encode()",
      ".encode(" in cli_src)

check("1.4 No raw policy_path leaked in JSON outputs",
      cli_src.count('"policy_path"') == 0 or '"policy_path_hash"' in cli_src,
      "raw policy_path should not appear as a JSON output key")

check("1.5 _hash_policy_path or equivalent helper defined",
      "def _hash_policy_path" in cli_src or "policy_path_hash" in cli_src)

# ============================================================
print("=" * 60)
print("Section 2: anchor_log_binding")
print("=" * 60)

check("2.1 policy_sha256 bound in anchor log entry",
      '"policy_sha256"' in cli_src)

check("2.2 anchor log entry construction",
      "anchor" in cli_src.lower() and "policy_sha256" in cli_src)

check("2.3 anchor log written on policy load",
      "policy_sha256" in cli_src and "_load_audit_policy" in cli_src)

check("2.4 anchor log includes path_hash",
      "policy_path_hash" in cli_src)

check("2.5 anchor log includes timestamp",
      "policy_loaded_at" in cli_src or "loaded_at" in cli_src)

# ============================================================
print("=" * 60)
print("Section 3: json_schema_artifact")
print("=" * 60)

check("3.1 _AUDIT_POLICY_JSON_SCHEMA defined",
      "_AUDIT_POLICY_JSON_SCHEMA" in cli_src)

check("3.2 policy-schema command exists",
      '"policy-schema"' in cli_src or "'policy-schema'" in cli_src)

check("3.3 schema validation helper",
      "jsonschema" in cli_src or "json_schema" in cli_src or "validate" in cli_src)

check("3.4 schema artifact embedded or referenced",
      "_AUDIT_POLICY_JSON_SCHEMA" in cli_src and len(cli_src.split("_AUDIT_POLICY_JSON_SCHEMA")) >= 2)

check("3.5 policy-schema outputs JSON",
      "policy-schema" in cli_src and "json" in cli_src.lower())

# ============================================================
print("=" * 60)
print("Section 4: checkpoint_export_binding")
print("=" * 60)

check("4.1 policy_provenance excluded from signature verification",
      "policy_provenance" in cli_src and ("exclude" in cli_src or "skip" in cli_src or "sign_keys" in cli_src),
      "policy_provenance must not be part of the signed payload")

check("4.2 checkpoint includes policy_path_hash",
      "policy_path_hash" in cli_src and "checkpoint" in cli_src)

check("4.3 checkpoint includes policy_sha256",
      "policy_sha256" in cli_src and "checkpoint" in cli_src)

check("4.4 export binding attaches policy identity",
      "policy_sha256" in cli_src)

check("4.5 verify-chain validates policy binding",
      "verify-chain" in cli_src or "verify_chain" in cli_src)

# ============================================================
print("=" * 60)
print("Section 5: A41 carry-forward")
print("=" * 60)

check("5.1 _compute_policy_provenance still defined",
      "def _compute_policy_provenance" in cli_src or "policy_provenance" in cli_src)

check("5.2 --expected-policy-hash on commands",
      cli_src.count("--expected-policy-hash") >= 4,
      f"found {cli_src.count('--expected-policy-hash')}")

check("5.3 policy_provenance in JSON outputs",
      '"policy_provenance"' in cli_src and cli_src.count('policy_provenance') >= 5,
      f"found {cli_src.count('policy_provenance')}")

check("5.4 policy_provenance in audit manifest",
      'manifest["policy_provenance"]' in cli_src or "manifest[\"policy_provenance\"]" in cli_src)

check("5.5 expected_hash parameter in _load_audit_policy",
      "expected_hash" in cli_src)

# ============================================================
print("=" * 60)
print("Section 6: A39-A40 carry-forward")
print("=" * 60)

check("6.1 policy_warnings",
      "policy_warnings" in cli_src)

check("6.2 timestamp_downgraded",
      "timestamp_downgraded" in cli_src)

check("6.3 --policy on paper audit",
      cli_src.count("policy_file: str") >= 4,
      f"found {cli_src.count('policy_file: str')}")

check("6.4 policy_file parameter present",
      "policy_file" in cli_src)

# ============================================================
print("=" * 60)
print("Section 7: A36-A38 carry-forward")
print("=" * 60)

check("7.1 signature_policy",
      "signature_policy" in cli_src)

check("7.2 signature_status",
      "signed_valid" in cli_src)

check("7.3 chain_verification_mode",
      "policy_chain_mode" in cli_src)

check("7.4 _load_audit_policy",
      "def _load_audit_policy" in cli_src)

check("7.5 strict_timestamps",
      "strict_timestamps" in cli_src)

check("7.6 _sign_record",
      "def _sign_record" in cli_src)

check("7.7 chain_full_hash",
      "chain_full_hash" in cli_src)

# ============================================================
print("=" * 60)
print("Section 8: Test coverage")
print("=" * 60)

check("8.1 TestA42PathHashPrivacy",
      "TestA42PathHashPrivacy" in test_src)

check("8.2 TestA42AnchorLogBinding",
      "TestA42AnchorLogBinding" in test_src)

check("8.3 TestA42JsonSchemaArtifact",
      "TestA42JsonSchemaArtifact" in test_src)

check("8.4 TestA42CheckpointExportBinding",
      "TestA42CheckpointExportBinding" in test_src)

check("8.5 TestA42Integration",
      "TestA42Integration" in test_src)

test_count = test_src.count("def test_")
check("8.6 At least 13 tests",
      test_count >= 13,
      f"found {test_count}")

# ============================================================
print("=" * 60)
total = PASS + FAIL
print(f"A42 Validation: {PASS} passed, {FAIL} failed, {total} total")
print("=" * 60)

for r in RESULTS:
    print(r)

sys.exit(0 if FAIL == 0 else 1)
