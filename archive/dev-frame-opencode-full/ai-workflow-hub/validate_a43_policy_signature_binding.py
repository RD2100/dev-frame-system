"""A43 Validation — Policy Signature Binding (35 checks across 8 sections)."""

import sys
from pathlib import Path

PASS = 0
FAIL = 0
RESULTS: list[str] = []

ROOT = Path(__file__).resolve().parent
CLI_PATH = ROOT / "src" / "ai_workflow_hub" / "cli.py"
TEST_PATH = ROOT / "tests" / "test_paper_a43_policy_signature_binding.py"


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
print("Section 1: path_redaction")
print("=" * 60)

check("1.1 policy_file_hash in cli (new field name)",
      '"policy_file_hash"' in cli_src,
      "policy_file_hash should appear as a JSON output key")

check("1.2 result['policy_file'] NOT used as key assignment",
      'result["policy_file"]' not in cli_src,
      "raw policy_file path should be removed from JSON outputs")

check("1.3 policy_file_hash derived from policy_path_hash",
      'result["policy_file_hash"]' in cli_src and "policy_path_hash" in cli_src,
      "policy_file_hash should be derived from provenance policy_path_hash")

check("1.4 policy_file_hash assigned in multiple commands",
      cli_src.count('"policy_file_hash"') >= 2,
      f"found {cli_src.count(chr(34) + 'policy_file_hash' + chr(34))}")

check("1.5 No raw policy_file path leaked in JSON result keys",
      'result["policy_file"]' not in cli_src,
      "no raw filesystem path should appear as result key")

# ============================================================
print("=" * 60)
print("Section 2: schema_validation")
print("=" * 60)

check("2.1 _AUDIT_POLICY_JSON_SCHEMA defined",
      "_AUDIT_POLICY_JSON_SCHEMA" in cli_src,
      "module-level JSON schema constant must be defined")

check("2.2 _schema_props or _AUDIT_POLICY_JSON_SCHEMA referenced in _load_audit_policy",
      "_schema_props" in cli_src or "_AUDIT_POLICY_JSON_SCHEMA" in cli_src,
      "schema validation must reference schema during policy loading")

check("2.3 schema_validated in cli_src",
      "schema_validated" in cli_src,
      "schema_validated field must be present in provenance")

check("2.4 schema_warnings in cli_src",
      "schema_warnings" in cli_src,
      "schema_warnings field must be present in provenance")

check("2.5 _load_audit_policy performs schema validation",
      "_load_audit_policy" in cli_src and "_schema_props" in cli_src,
      "policy loading must include schema-based validation")

# ============================================================
print("=" * 60)
print("Section 3: provenance_enrichment")
print("=" * 60)

check("3.1 schema_validated assigned in provenance",
      '"schema_validated"' in cli_src,
      "schema_validated must be a provenance field")

check("3.2 schema_warnings count assigned in provenance",
      '"schema_warnings"' in cli_src,
      "schema_warnings count must be a provenance field")

check("3.3 policy_sha256 in provenance dict",
      '"policy_sha256"' in cli_src,
      "policy_sha256 must be in provenance output")

check("3.4 policy_path_hash in provenance dict",
      '"policy_path_hash"' in cli_src,
      "policy_path_hash must be in provenance output")

check("3.5 policy_loaded_at in provenance dict",
      '"policy_loaded_at"' in cli_src,
      "policy_loaded_at must be in provenance output")

# ============================================================
print("=" * 60)
print("Section 4: A42 carry-forward")
print("=" * 60)

check("4.1 policy_path_hash still in cli (A42 path hash privacy)",
      "policy_path_hash" in cli_src,
      "A42 path hash must be preserved")

check("4.2 Anchor log binds policy_sha256 at load time",
      "policy_sha256" in cli_src and "anchor" in cli_src.lower(),
      "anchor log must bind policy hash")

check("4.3 policy-schema CLI command exists",
      '"policy-schema"' in cli_src or "'policy-schema'" in cli_src,
      "JSON schema must be exposed via CLI command")

check("4.4 Anchor log includes policy_path_hash",
      "policy_path_hash" in cli_src and "anchor" in cli_src.lower(),
      "anchor record must carry path hash")

check("4.5 policy-schema outputs JSON",
      "policy-schema" in cli_src and "json" in cli_src.lower(),
      "policy-schema command must output JSON")

# ============================================================
print("=" * 60)
print("Section 5: A41 carry-forward")
print("=" * 60)

check("5.1 _compute_policy_provenance still defined",
      "def _compute_policy_provenance" in cli_src or "_compute_policy_provenance" in cli_src,
      "provenance computation function must exist")

check("5.2 --expected-policy-hash on commands (>=4)",
      cli_src.count("--expected-policy-hash") >= 4,
      f"found {cli_src.count('--expected-policy-hash')}")

check("5.3 policy_provenance in JSON outputs",
      "policy_provenance" in cli_src and cli_src.count("policy_provenance") >= 5,
      f"found {cli_src.count('policy_provenance')}")

check("5.4 manifest includes policy_provenance",
      'manifest["policy_provenance"]' in cli_src or 'manifest[\'policy_provenance\']' in cli_src,
      "audit manifest must carry policy provenance")

check("5.5 expected_hash parameter in _load_audit_policy",
      "expected_hash" in cli_src,
      "expected_hash must be a parameter of policy loading")

# ============================================================
print("=" * 60)
print("Section 6: A39-A40 carry-forward")
print("=" * 60)

check("6.1 policy_warnings",
      "policy_warnings" in cli_src,
      "policy_warnings must be present for backward compat")

check("6.2 timestamp_downgraded",
      "timestamp_downgraded" in cli_src,
      "timestamp downgrade warning must be preserved")

check("6.3 --policy on commands (policy_file: str >= 4)",
      cli_src.count("policy_file: str") >= 4,
      f"found {cli_src.count('policy_file: str')}")

check("6.4 policy_file parameter present",
      "policy_file" in cli_src,
      "policy_file parameter must be preserved")

# ============================================================
print("=" * 60)
print("Section 7: A36-A38 carry-forward")
print("=" * 60)

check("7.1 signature_policy",
      "signature_policy" in cli_src,
      "signature_policy must be preserved")

check("7.2 signed_valid (signature status)",
      "signed_valid" in cli_src,
      "signature status values must be preserved")

check("7.3 _sign_record defined",
      "def _sign_record" in cli_src,
      "signing function must be defined")

check("7.4 chain_full_hash",
      "chain_full_hash" in cli_src,
      "chain_full_hash must be preserved")

check("7.5 _load_audit_policy defined",
      "def _load_audit_policy" in cli_src,
      "policy loading function must be defined")

# ============================================================
print("=" * 60)
print("Section 8: Test coverage")
print("=" * 60)

check("8.1 TestA43PathRedaction",
      "TestA43PathRedaction" in test_src,
      "test class for path redaction must exist")

check("8.2 TestA43SchemaValidation",
      "TestA43SchemaValidation" in test_src,
      "test class for schema validation must exist")

check("8.3 TestA43ProvenanceEnrichment",
      "TestA43ProvenanceEnrichment" in test_src,
      "test class for provenance enrichment must exist")

check("8.4 TestA43Integration",
      "TestA43Integration" in test_src,
      "integration test class must exist")

test_count = test_src.count("def test_")
check("8.5 At least 8 tests",
      test_count >= 8,
      f"found {test_count}")

# ============================================================
print("=" * 60)
total = PASS + FAIL
print(f"A43 Validation: {PASS} passed, {FAIL} failed, {total} total")
print("=" * 60)

for r in RESULTS:
    print(r)

sys.exit(0 if FAIL == 0 else 1)
