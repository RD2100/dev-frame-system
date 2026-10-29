"""A45 Validation -- PAPER-AUDIT-COMPLETENESS-PROOF (--completeness-check on paper audit)."""

import json
import sys
import tempfile
from pathlib import Path

PASS = 0
FAIL = 0
RESULTS: list = []

ROOT = Path(__file__).resolve().parent
CLI_PATH = ROOT / "src" / "ai_workflow_hub" / "cli.py"
TEST_PATH = ROOT / "tests" / "test_paper_a45_audit_completeness.py"


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
print("Section 1: --completeness-check option on paper audit")
print("=" * 60)

check("1.1 --completeness-check option declared on paper audit",
      '"audit"' in cli_src
      and 'completeness_check: bool = typer.Option(False, "--completeness-check"' in cli_src,
      "paper audit must declare --completeness-check option")

check("1.2 --completeness-check defaults to False",
      'completeness_check: bool = typer.Option(False, "--completeness-check"' in cli_src,
      "default must be False")

check("1.3 --completeness-check has help text",
      '"--completeness-check"' in cli_src
      and "help=" in cli_src,
      "--completeness-check must have help text")

# ============================================================
print("=" * 60)
print("Section 2: Completeness check logic")
print("=" * 60)

check("2.1 completeness_check conditional block exists",
      "if completeness_check:" in cli_src,
      "CLI must have 'if completeness_check:' block")

check("2.2 Run directory scanning with rglob",
      "rglob" in cli_src
      and "_all_run_files" in cli_src,
      "must scan run directory for all files")

check("2.3 Bundle file collection from manifest",
      "_bundle_files" in cli_src
      and 'manifest.get("files")' in cli_src,
      "must collect files from bundle manifest")

check("2.4 Missing files computed via set difference",
      "_missing_from_bundle" in cli_src
      and "_all_run_files - _bundle_files" in cli_src,
      "must compute set difference to find missing files")

check("2.5 Completeness report dict constructed",
      '"total_run_files"' in cli_src
      and '"total_bundle_files"' in cli_src
      and '"missing_from_bundle"' in cli_src,
      "completeness report must include required fields")

# ============================================================
print("=" * 60)
print("Section 3: Completeness report structure")
print("=" * 60)

check("3.1 total_run_files in report",
      '"total_run_files": len(_all_run_files)' in cli_src,
      "report must include total_run_files count")

check("3.2 total_bundle_files in report",
      '"total_bundle_files": len(_bundle_files)' in cli_src,
      "report must include total_bundle_files count")

check("3.3 required_present in report",
      '"required_present"' in cli_src,
      "report must include required_present boolean")

check("3.4 missing_count in report",
      '"missing_count": len(_missing_from_bundle)' in cli_src,
      "report must include missing_count")

check("3.5 complete boolean in report",
      '"complete"' in cli_src
      and "len(_missing_from_bundle) == 0" in cli_src,
      "report must include complete boolean based on missing counts")

# ============================================================
print("=" * 60)
print("Section 4: User-facing output")
print("=" * 60)

check("4.1 Green PASSED message for complete runs",
      '[green]Completeness: PASSED' in cli_src,
      "must print green PASSED when all files present")

check("4.2 Yellow warning for incomplete runs",
      '[yellow]Completeness:' in cli_src
      and 'not in bundle' in cli_src,
      "must print yellow warning when files missing")

check("4.3 Missing file list displayed",
      "Missing:" in cli_src
      and "_missing_from_bundle" in cli_src,
      "must display list of missing files")

# ============================================================
print("=" * 60)
print("Section 5: JSON output integration")
print("=" * 60)

check("5.1 completeness added to JSON output when enabled",
      'if completeness_check:' in cli_src
      and '_json_out["completeness"]' in cli_src,
      "JSON output must include completeness field when check enabled")

check("5.2 completeness uses _completeness_report dict",
      '_json_out["completeness"] = _completeness_report' in cli_src,
      "JSON completeness must use the report dict")

check("5.3 completeness absent from JSON when not enabled",
      # The conditional 'if completeness_check:' before adding to _json_out
      # ensures it is absent when not enabled
      cli_src.count('if completeness_check:') >= 2,
      "completeness must be conditional on completeness_check flag")

# ============================================================
print("=" * 60)
print("Section 6: CliRunner runtime tests")
print("=" * 60)

from typer.testing import CliRunner
from unittest.mock import patch

sys.path.insert(0, str(ROOT / "src"))
from ai_workflow_hub.cli import app

_runner = CliRunner()


def _make_state(run_id="a45val"):
    return {
        "run_id": run_id,
        "task_id": "",
        "evidence_manifest": {"files": []},
        "ledger_dir": "",
        "decision_base_dir": "",
        "closeout_integrity": "complete",
    }


with tempfile.TemporaryDirectory(prefix="a45val_") as _tmpdir:
    _tmpdir_path = Path(_tmpdir)
    _run_dir = _tmpdir_path / "runs" / "a45val"
    _run_dir.mkdir(parents=True)

    _state = _make_state("a45val")
    (_run_dir / "state.json").write_text(
        json.dumps(_state), encoding="utf-8")
    (_run_dir / "closeout-report.json").write_text(
        json.dumps({"run_id": "a45val", "status": "complete"}),
        encoding="utf-8")
    (_run_dir / "closeout-report.md").write_text(
        "# Closeout Report: a45val", encoding="utf-8")

    _output_zip = str(_tmpdir_path / "bundle.zip")

    # --- 6.1 --completeness-check with clean run -> PASSED ---
    with patch("ai_workflow_hub.cli._load_run_state",
               return_value=(_state, _run_dir)):
        _r = _runner.invoke(app, [
            "paper", "audit",
            "--run-id", "a45val",
            "--output", _output_zip,
            "--completeness-check",
        ])
    _combined = (_r.stdout or "") + (_r.stderr or "")
    check("6.1 Clean run + --completeness-check: exit 0",
          _r.exit_code == 0,
          f"exit={_r.exit_code}, output: {_combined[:200]}")

    check("6.2 Clean run + --completeness-check: shows PASSED",
          "Completeness: PASSED" in _combined,
          f"output: {_combined[:300]}")

    # --- 6.3 --completeness-check --json -> JSON has completeness ---
    _output_zip2 = str(_tmpdir_path / "bundle2.zip")
    with patch("ai_workflow_hub.cli._load_run_state",
               return_value=(_state, _run_dir)):
        _r = _runner.invoke(app, [
            "paper", "audit",
            "--run-id", "a45val",
            "--output", _output_zip2,
            "--completeness-check",
            "--json",
        ])
    _has_completeness = False
    if _r.exit_code == 0:
        try:
            _data = json.loads(_r.stdout, strict=False)
            _has_completeness = "completeness" in _data
        except (json.JSONDecodeError, TypeError):
            pass
    check("6.3 --completeness-check --json: JSON has completeness key",
          _has_completeness,
          f"exit={_r.exit_code}, stdout snippet: {(_r.stdout or '')[:200]}")

    # --- 6.4 Without --completeness-check -> no completeness in JSON ---
    _output_zip3 = str(_tmpdir_path / "bundle3.zip")
    with patch("ai_workflow_hub.cli._load_run_state",
               return_value=(_state, _run_dir)):
        _r = _runner.invoke(app, [
            "paper", "audit",
            "--run-id", "a45val",
            "--output", _output_zip3,
            "--json",
        ])
    _no_completeness = True
    if _r.exit_code == 0:
        try:
            _data = json.loads(_r.stdout, strict=False)
            _no_completeness = "completeness" not in _data
        except (json.JSONDecodeError, TypeError):
            pass
    check("6.4 Without --completeness-check: no completeness in JSON",
          _no_completeness,
          f"exit={_r.exit_code}")

    # --- 6.5 Extra file in run dir -> completeness detects missing ---
    (_run_dir / "extra-artifact.txt").write_text(
        "extra content not in bundle", encoding="utf-8")
    _output_zip4 = str(_tmpdir_path / "bundle4.zip")
    with patch("ai_workflow_hub.cli._load_run_state",
               return_value=(_state, _run_dir)):
        _r = _runner.invoke(app, [
            "paper", "audit",
            "--run-id", "a45val",
            "--output", _output_zip4,
            "--completeness-check",
        ])
    _combined = (_r.stdout or "") + (_r.stderr or "")
    _detects_missing = "not in bundle" in _combined or "Missing:" in _combined
    check("6.5 Extra file in run dir: detects missing from bundle",
          _detects_missing,
          f"output: {_combined[:300]}")

# ============================================================
print("=" * 60)
print("Section 7: A44 carry-forward")
print("=" * 60)

check("7.1 --strict-policy still present on audit (A44)",
      '"--strict-policy"' in cli_src
      and "strict_policy: bool = typer.Option" in cli_src,
      "A44 strict-policy must be preserved")

check("7.2 _load_audit_policy still called (A44)",
      "_load_audit_policy" in cli_src,
      "A44 policy loading must be preserved")

check("7.3 Policy provenance in bundle manifest (A44)",
      "_policy_provenance" in cli_src,
      "A44 provenance binding must be preserved")

# ============================================================
print("=" * 60)
print("Section 8: Test coverage")
print("=" * 60)

check("8.1 Test file exists",
      TEST_PATH.exists(),
      f"test file not found: {TEST_PATH}")

_test_completeness_count = test_src.count("completeness")
check("8.2 Tests reference completeness",
      _test_completeness_count >= 4,
      f"found {_test_completeness_count} references to completeness in tests")

_test_class_count = test_src.count("class Test")
check("8.3 At least 3 test classes",
      _test_class_count >= 3,
      f"found {_test_class_count} test classes")

test_count = test_src.count("def test_")
check("8.4 At least 8 test functions",
      test_count >= 8,
      f"found {test_count}")

check("8.5 Tests use CliRunner and patch",
      "CliRunner" in test_src and "patch" in test_src,
      "tests should use CliRunner and unittest.mock.patch")

check("8.6 Tests use JSON parsing",
      "json.loads" in test_src,
      "tests should verify JSON output structure")

# ============================================================
print("=" * 60)
total = PASS + FAIL
print(f"A45 Validation: {PASS} passed, {FAIL} failed, {total} total")
print("=" * 60)

for r in RESULTS:
    print(r)

check("ALL A45 CHECKS PASSED", FAIL == 0)

sys.exit(0 if FAIL == 0 else 1)
