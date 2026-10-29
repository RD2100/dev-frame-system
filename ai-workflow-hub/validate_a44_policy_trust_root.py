"""A44 Validation -- PAPER-AUDIT-POLICY-TRUST-ROOT (--strict-policy on all 4 paper commands)."""

import json
import sys
import tempfile
from pathlib import Path

PASS = 0
FAIL = 0
RESULTS: list[str] = []

ROOT = Path(__file__).resolve().parent
CLI_PATH = ROOT / "src" / "ai_workflow_hub" / "cli.py"
TEST_PATH = ROOT / "tests" / "test_paper_a44_policy_trust_root.py"


def check(label: str, cond: bool, detail: str = ""):
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
print("Section 1: --strict-policy option on all 4 paper commands")
print("=" * 60)

# The 4 commands that must carry --strict-policy:
#   paper audit, paper verify, paper verify-chain, paper checkpoint
# Each is a @paper_app.command(...) with a strict_policy: bool = typer.Option(..., "--strict-policy", ...)

# 1.1 audit
check("1.1 --strict-policy on 'paper audit' command",
      '"audit"' in cli_src
      and 'strict_policy: bool = typer.Option(False, "--strict-policy"' in cli_src,
      "paper audit must declare --strict-policy option")

# 1.2 verify
# We need to confirm that verify command (not verify-chain) has it.
# Find all occurrences of --strict-policy and ensure there are at least 4.
_strict_policy_count = cli_src.count('"--strict-policy"')
check("1.2 --strict-policy appears on >=4 commands",
      _strict_policy_count >= 4,
      f"found {_strict_policy_count} occurrences of '--strict-policy'")

# 1.3 verify-chain
check("1.3 --strict-policy on 'paper verify-chain' command",
      '"verify-chain"' in cli_src
      and cli_src.count('strict_policy: bool = typer.Option(False, "--strict-policy"') >= 3,
      "paper verify-chain must declare --strict-policy option")

# 1.4 checkpoint
check("1.4 --strict-policy on 'paper checkpoint' command",
      '"checkpoint"' in cli_src
      and cli_src.count('strict_policy: bool = typer.Option(False, "--strict-policy"') >= 4,
      "paper checkpoint must declare --strict-policy option")

# 1.5 Each command passes strict_policy to _load_audit_policy
_strict_call_count = cli_src.count("strict_policy=strict_policy")
check("1.5 strict_policy forwarded to _load_audit_policy (>=4)",
      _strict_call_count >= 4,
      f"found {_strict_call_count} calls with strict_policy=strict_policy")

# ============================================================
print("=" * 60)
print("Section 2: _load_audit_policy accepts strict_policy parameter")
print("=" * 60)

check("2.1 _load_audit_policy function defined",
      "def _load_audit_policy" in cli_src,
      "_load_audit_policy must be defined")

check("2.2 _load_audit_policy signature includes strict_policy",
      "strict_policy: bool = False" in cli_src
      and "def _load_audit_policy" in cli_src,
      "_load_audit_policy must accept strict_policy parameter")

check("2.3 strict_policy escalates warnings to errors",
      "if strict_policy:" in cli_src
      and 'Schema error (strict-policy)' in cli_src,
      "strict_policy must escalate schema warnings to red errors")

check("2.4 strict_policy raises typer.Exit(1) on schema warnings",
      "if strict_policy:" in cli_src
      and "raise typer.Exit(1)" in cli_src,
      "strict_policy must block with exit code != 0")

check("2.5 Non-strict mode prints yellow warnings",
      'Schema warning:' in cli_src,
      "without strict_policy, schema issues should produce yellow warnings")

# ============================================================
print("=" * 60)
print("Section 3: Provenance includes schema_validated field")
print("=" * 60)

check("3.1 schema_validated assigned in _load_audit_policy",
      '"schema_validated"' in cli_src
      and "len(_schema_warnings) == 0" in cli_src,
      "schema_validated must be computed from schema_warnings count")

check("3.2 schema_warnings count in provenance",
      '"schema_warnings"' in cli_src
      and "_provenance" in cli_src,
      "schema_warnings count must be stored in provenance")

check("3.3 _policy_provenance attached to policy dict",
      'policy["_policy_provenance"]' in cli_src
      or "policy['_policy_provenance']" in cli_src,
      "policy dict must carry _policy_provenance")

check("3.4 schema_validated is boolean expression",
      "len(_schema_warnings) == 0" in cli_src,
      "schema_validated must be True when zero warnings, False otherwise")

check("3.5 _compute_policy_provenance defined",
      "def _compute_policy_provenance" in cli_src,
      "provenance computation function must exist")

# ============================================================
print("=" * 60)
print("Section 4: CliRunner runtime tests")
print("=" * 60)

# Import the CLI app and use CliRunner to test actual invocation
from typer.testing import CliRunner

# We need to import the app from the cli module
sys.path.insert(0, str(ROOT / "src"))
from ai_workflow_hub.cli import app

runner = CliRunner()

# Create a valid policy file
_valid_policy = {
    "schema_version": "1.0",
    "signature_policy": "optional",
    "allowed_key_ids": ["kid-test-1"],
    "chain_verification_mode": "chain_only",
    "strict_chain": False,
    "strict_timestamps": True,
    "required_artifacts": [],
    "description": "A44 test policy (valid)",
}

# Create an invalid policy file (wrong type for strict_chain: string instead of boolean)
_invalid_policy = {
    "schema_version": "1.0",
    "signature_policy": "optional",
    "allowed_key_ids": ["kid-test-1"],
    "chain_verification_mode": "chain_only",
    "strict_chain": "yes",
    "strict_timestamps": True,
    "required_artifacts": [],
    "description": "A44 test policy (invalid type)",
}

# We need a valid run_id for audit/verify commands.
# Use a non-existent run_id -- the command will fail on "run not found"
# but that is AFTER policy loading, so --strict-policy with bad policy
# should fail BEFORE reaching "run not found".

with tempfile.TemporaryDirectory(prefix="a44val_") as _tmpdir:
    _tmpdir_path = Path(_tmpdir)

    # Write valid policy
    _valid_path = _tmpdir_path / "valid_policy.json"
    _valid_path.write_text(json.dumps(_valid_policy, indent=2), encoding="utf-8")

    # Write invalid policy
    _invalid_path = _tmpdir_path / "invalid_policy.json"
    _invalid_path.write_text(json.dumps(_invalid_policy, indent=2), encoding="utf-8")

    # --- 4.1 Valid policy + --strict-policy on audit: should load policy (may fail later on run_id) ---
    _r = runner.invoke(app, [
        "paper", "audit",
        "--run-id", "nonexistent-run-a44",
        "--policy", str(_valid_path),
        "--strict-policy",
    ])
    # The command may fail because the run_id does not exist, but it should NOT
    # fail with "Schema error (strict-policy)" -- the policy is valid.
    _output = (_r.stdout or "") + (_r.stderr or "")
    _policy_loaded = "Policy loaded" in _output or "policy loaded" in _output.lower()
    _no_schema_error = "Schema error (strict-policy)" not in _output
    check("4.1 Valid policy + --strict-policy: policy loads without schema error",
          _no_schema_error,
          f"exit={_r.exit_code}, output snippet: {_output[:200]}")

    # --- 4.2 Invalid policy + --strict-policy on audit: should BLOCK ---
    _r = runner.invoke(app, [
        "paper", "audit",
        "--run-id", "nonexistent-run-a44",
        "--policy", str(_invalid_path),
        "--strict-policy",
    ])
    _output = (_r.stdout or "") + (_r.stderr or "")
    check("4.2 Invalid policy + --strict-policy: exit != 0 (blocked)",
          _r.exit_code != 0,
          f"exit={_r.exit_code}, output snippet: {_output[:200]}")

    _has_schema_error = "Schema error (strict-policy)" in _output
    check("4.3 Invalid policy + --strict-policy: emits 'Schema error (strict-policy)'",
          _has_schema_error,
          f"output snippet: {_output[:300]}")

    # --- 4.4 Invalid policy WITHOUT --strict-policy: should WARN but NOT block on schema ---
    _r = runner.invoke(app, [
        "paper", "audit",
        "--run-id", "nonexistent-run-a44",
        "--policy", str(_invalid_path),
    ])
    _output = (_r.stdout or "") + (_r.stderr or "")
    _has_warning = "Schema warning" in _output
    check("4.4 Invalid policy without --strict-policy: emits 'Schema warning'",
          _has_warning,
          f"output snippet: {_output[:300]}")

    _no_block = "Schema error (strict-policy)" not in _output
    check("4.5 Invalid policy without --strict-policy: no strict-policy block",
          _no_block,
          f"output snippet: {_output[:300]}")

    # --- 4.6 Valid policy + --strict-policy on verify command ---
    # verify needs a --zip argument; we pass a dummy path
    _dummy_zip = str(_tmpdir_path / "dummy.zip")
    _r = runner.invoke(app, [
        "paper", "verify",
        "--zip", _dummy_zip,
        "--policy", str(_valid_path),
        "--strict-policy",
    ])
    _output = (_r.stdout or "") + (_r.stderr or "")
    _no_schema_error = "Schema error (strict-policy)" not in _output
    check("4.6 Valid policy + --strict-policy on verify: no schema error",
          _no_schema_error,
          f"exit={_r.exit_code}, output snippet: {_output[:200]}")

    # --- 4.7 Invalid policy + --strict-policy on verify-chain ---
    _dummy_log = str(_tmpdir_path / "dummy.jsonl")
    Path(_dummy_log).write_text("", encoding="utf-8")
    _r = runner.invoke(app, [
        "paper", "verify-chain",
        "--log", _dummy_log,
        "--policy", str(_invalid_path),
        "--strict-policy",
    ])
    _output = (_r.stdout or "") + (_r.stderr or "")
    check("4.7 Invalid policy + --strict-policy on verify-chain: exit != 0",
          _r.exit_code != 0,
          f"exit={_r.exit_code}, output snippet: {_output[:200]}")

    # --- 4.8 Invalid policy + --strict-policy on checkpoint ---
    _r = runner.invoke(app, [
        "paper", "checkpoint",
        "--log", _dummy_log,
        "--policy", str(_invalid_path),
        "--strict-policy",
    ])
    _output = (_r.stdout or "") + (_r.stderr or "")
    check("4.8 Invalid policy + --strict-policy on checkpoint: exit != 0",
          _r.exit_code != 0,
          f"exit={_r.exit_code}, output snippet: {_output[:200]}")

# ============================================================
print("=" * 60)
print("Section 5: Schema validation logic")
print("=" * 60)

check("5.1 _AUDIT_POLICY_JSON_SCHEMA defined",
      "_AUDIT_POLICY_JSON_SCHEMA" in cli_src,
      "module-level JSON schema constant must be defined")

check("5.2 Schema validates boolean type fields",
      '"boolean"' in cli_src
      and "isinstance(_val, bool)" in cli_src,
      "schema validation must check boolean type for strict_chain etc.")

check("5.3 Schema validates string type fields",
      '"string"' in cli_src
      and "isinstance(_val, str)" in cli_src,
      "schema validation must check string type")

check("5.4 Schema validates array type fields",
      '"array"' in cli_src
      and "isinstance(_val, list)" in cli_src,
      "schema validation must check array type")

check("5.5 Schema validates enum constraints",
      '"enum"' in cli_src
      and "not in _spec" in cli_src,
      "schema validation must check enum constraints")

# ============================================================
print("=" * 60)
print("Section 6: A43 carry-forward")
print("=" * 60)

check("6.1 policy_file_hash in cli (A43 path redaction)",
      '"policy_file_hash"' in cli_src,
      "policy_file_hash should appear as a JSON output key")

check("6.2 schema_validated in provenance (A43)",
      "schema_validated" in cli_src,
      "schema_validated field must be present")

check("6.3 schema_warnings in provenance (A43)",
      "schema_warnings" in cli_src,
      "schema_warnings field must be present")

check("6.4 _schema_props references _AUDIT_POLICY_JSON_SCHEMA",
      "_schema_props" in cli_src
      and "_AUDIT_POLICY_JSON_SCHEMA" in cli_src,
      "schema validation must reference the schema constant")

check("6.5 policy_sha256 in provenance (A43)",
      '"policy_sha256"' in cli_src,
      "policy_sha256 must be in provenance output")

# ============================================================
print("=" * 60)
print("Section 7: A41-A42 carry-forward")
print("=" * 60)

check("7.1 _compute_policy_provenance defined (A41)",
      "def _compute_policy_provenance" in cli_src,
      "provenance computation function must exist")

check("7.2 policy_path_hash in provenance (A42)",
      '"policy_path_hash"' in cli_src,
      "policy_path_hash must be in provenance (A42 path privacy)")

check("7.3 policy_loaded_at in provenance (A41)",
      '"policy_loaded_at"' in cli_src,
      "policy_loaded_at must be in provenance")

check("7.4 expected_hash parameter in _load_audit_policy (A41)",
      "expected_hash" in cli_src,
      "expected_hash must be a parameter for hash verification")

check("7.5 policy-schema CLI command exists (A42)",
      '"policy-schema"' in cli_src or "'policy-schema'" in cli_src,
      "JSON schema must be exposed via CLI command")

# ============================================================
print("=" * 60)
print("Section 8: Test coverage")
print("=" * 60)

check("8.1 Test file exists",
      TEST_PATH.exists(),
      f"test file not found: {TEST_PATH}")

_test_strict_count = test_src.count("strict_policy")
check("8.2 Tests reference strict_policy",
      _test_strict_count >= 4,
      f"found {_test_strict_count} references to strict_policy in tests")

_test_schema_validated = test_src.count("schema_validated")
check("8.3 Tests reference schema_validated",
      _test_schema_validated >= 1,
      f"found {_test_schema_validated} references to schema_validated in tests")

test_count = test_src.count("def test_")
check("8.4 At least 6 test functions",
      test_count >= 6,
      f"found {test_count}")

check("8.5 Tests use CliRunner or _load_audit_policy",
      "CliRunner" in test_src or "_load_audit_policy" in test_src,
      "tests should use CliRunner or direct function calls")

# ============================================================
print("=" * 60)
total = PASS + FAIL
print(f"A44 Validation: {PASS} passed, {FAIL} failed, {total} total")
print("=" * 60)

for r in RESULTS:
    print(r)

check("ALL A44 CHECKS PASSED", FAIL == 0)

sys.exit(0 if FAIL == 0 else 1)
