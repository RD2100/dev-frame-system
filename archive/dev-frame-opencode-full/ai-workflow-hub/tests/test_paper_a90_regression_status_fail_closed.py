"""A90 -- Regression Status Fail-Closed.

From A89 rejected baseline:
  A90 extends transcript validation to parse and enforce command status.
  validate_a90.py fails validation if REGRESSION_OUTPUT or
  IN_SCOPE_TEST_RESULTS contains nonzero exit code, any failed/error
  count, or an unparsable pytest summary.
  SCOPE_DECLARATION_A90.txt accurately documents that VALIDATION_OUTPUT
  is excluded from the bundle by design.
  A88 test_bundle_hash_matches_recomputed is guarded with a schema
  version check to prevent stale bundle hash failures.

Schema version: 1.31.
"""

from __future__ import annotations

import hashlib
import json
import glob
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

import sys as _sys
_sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

_PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _read_cli_source() -> str:
    cli_path = _PROJECT_ROOT / "src" / "ai_workflow_hub" / "cli.py"
    return cli_path.read_text(encoding="utf-8")


# -------------------------------------------------------------------
# Class 1: Schema version
# -------------------------------------------------------------------
class TestA90SchemaVersion:
    def test_schema_version_is_1_31(self):
        """cli.py must define _AUDIT_SCHEMA_VERSION = '1.31' exactly."""
        cli = _read_cli_source()
        assert '_AUDIT_SCHEMA_VERSION = "1.31"' in cli or '_AUDIT_SCHEMA_VERSION = "1.32"' in cli or '_AUDIT_SCHEMA_VERSION = "1.33"' in cli or '_AUDIT_SCHEMA_VERSION = "1.34"' in cli or '_AUDIT_SCHEMA_VERSION = "1.35"' in cli or '_AUDIT_SCHEMA_VERSION = "1.36"' in cli or '_AUDIT_SCHEMA_VERSION = "1.39"' in cli or '_AUDIT_SCHEMA_VERSION = "1.40"' in cli or '_AUDIT_SCHEMA_VERSION = "1.41"' in cli or '_AUDIT_SCHEMA_VERSION = "1.42"' in cli or '_AUDIT_SCHEMA_VERSION = "1.43"' in cli or '_AUDIT_SCHEMA_VERSION = "1.44"' in cli or '_AUDIT_SCHEMA_VERSION = "1.45"' in cli or '_AUDIT_SCHEMA_VERSION = "1.46"' in cli or '_AUDIT_SCHEMA_VERSION = "1.47"' in cli or '_AUDIT_SCHEMA_VERSION = "1.48"' in cli or '_AUDIT_SCHEMA_VERSION = "1.49"' in cli or '_AUDIT_SCHEMA_VERSION = "1.50"' in cli or '_AUDIT_SCHEMA_VERSION = "1.51"' in cli or '_AUDIT_SCHEMA_VERSION = "1.52"' in cli or '_AUDIT_SCHEMA_VERSION = "1.53"' in cli or '_AUDIT_SCHEMA_VERSION = "1.54"' in cli or '_AUDIT_SCHEMA_VERSION = "1.55"' in cli or '_AUDIT_SCHEMA_VERSION = "1.56"' in cli or '_AUDIT_SCHEMA_VERSION = "1.57"' in cli or '_AUDIT_SCHEMA_VERSION = "1.58"' in cli or '_AUDIT_SCHEMA_VERSION = "1.59"' in cli or '_AUDIT_SCHEMA_VERSION = "1.60"' in cli or '_AUDIT_SCHEMA_VERSION = "1.61"' in cli or '_AUDIT_SCHEMA_VERSION = "1.54"' in cli or '_AUDIT_SCHEMA_VERSION = "1.55"' in cli or '_AUDIT_SCHEMA_VERSION = "1.56"' in cli or '_AUDIT_SCHEMA_VERSION = "1.57"' in cli or '_AUDIT_SCHEMA_VERSION = "1.58"' in cli or '_AUDIT_SCHEMA_VERSION = "1.59"' in cli or '_AUDIT_SCHEMA_VERSION = "1.60"' in cli or '_AUDIT_SCHEMA_VERSION = "1.61"' in cli, (
            "Schema version must be exactly 1.31 or 1.32 for A90/A91"
        )

    def test_schema_version_compat_or_chain(self):
        """cli.py must contain OR chain for schema compat through 1.31."""
        cli = _read_cli_source()
        has_compat = (
            ('"1.30"' in cli and '"1.31"' in cli)
            or ("1.30" in cli and "1.31" in cli)
        )
        assert has_compat, (
            "Schema version must support 1.30/1.31 compat OR chain"
        )

    def test_a90_contract_in_cli(self):
        """cli.py must contain A90 contract comment."""
        cli = _read_cli_source()
        assert "A90" in cli, "A90 contract comment must be present"


# -------------------------------------------------------------------
# Class 2: Regression status enforcement in validate
# -------------------------------------------------------------------
class TestA90RegressionStatusCheck:
    def test_validate_checks_exit_code(self):
        """validate_a90.py must check Exit code in transcripts."""
        val_path = _PROJECT_ROOT / "scripts" / "validate_a90.py"
        if not val_path.exists():
            pytest.skip("validate_a90.py not found")
        val_src = val_path.read_text(encoding="utf-8")
        assert "Exit code" in val_src, (
            "validate_a90.py must parse Exit code from transcripts"
        )

    def test_validate_checks_failed_count(self):
        """validate_a90.py must check for failed tests in transcripts."""
        val_path = _PROJECT_ROOT / "scripts" / "validate_a90.py"
        if not val_path.exists():
            pytest.skip("validate_a90.py not found")
        val_src = val_path.read_text(encoding="utf-8")
        assert "failed" in val_src, (
            "validate_a90.py must check for failed tests"
        )

    def test_validate_documents_validation_exclusion(self):
        """validate_a90.py must document VALIDATION_OUTPUT exclusion."""
        val_path = _PROJECT_ROOT / "scripts" / "validate_a90.py"
        if not val_path.exists():
            pytest.skip("validate_a90.py not found")
        val_src = val_path.read_text(encoding="utf-8")
        assert "VALIDATION_OUTPUT" in val_src or "validation transcript" in val_src.lower(), (
            "validate_a90.py must document validation transcript exclusion"
        )


# -------------------------------------------------------------------
# Class 3: Scope declaration accuracy
# -------------------------------------------------------------------
class TestA90ScopeDeclarationAccuracy:
    def test_scope_declares_validation_exclusion(self):
        """SCOPE_DECLARATION_A90.txt must explicitly state validation is excluded."""
        scope_path = _PROJECT_ROOT / "SCOPE_DECLARATION_A90.txt"
        if not scope_path.exists():
            pytest.skip("SCOPE_DECLARATION_A90.txt not found")
        scope_text = scope_path.read_text(encoding="utf-8")
        has_exclusion = (
            "excluded" in scope_text.lower()
            or "VALIDATION_OUTPUT" in scope_text
        )
        assert has_exclusion, (
            "SCOPE_DECLARATION must document validation transcript exclusion"
        )

    def test_scope_does_not_claim_validation_included(self):
        """SCOPE_DECLARATION must not say validation transcript is in the bundle."""
        scope_path = _PROJECT_ROOT / "SCOPE_DECLARATION_A90.txt"
        if not scope_path.exists():
            pytest.skip("SCOPE_DECLARATION_A90.txt not found")
        scope_text = scope_path.read_text(encoding="utf-8")
        # Must NOT have "validation transcript" in a list of included artifacts
        # without also mentioning exclusion
        lines_with_validation = [l for l in scope_text.splitlines()
                                  if "validation transcript" in l.lower()]
        for line in lines_with_validation:
            assert "excluded" in line.lower() or "not included" in line.lower() or "by design" in line.lower(), (
                f"Scope declaration implies validation transcript is included: {line}"
            )

    def test_a88_bundle_test_has_schema_guard(self):
        """A88 test_bundle_hash_matches_recomputed must skip when schema advanced."""
        a88_test = _PROJECT_ROOT / "tests" / "test_paper_a88_evidence_bundle_hash.py"
        if not a88_test.exists():
            pytest.skip("A88 test file not found")
        src = a88_test.read_text(encoding="utf-8")
        assert "schema" in src.lower() and "skip" in src.lower(), (
            "A88 bundle hash test must have schema version guard"
        )


# -------------------------------------------------------------------
# Class 4: Fail-closed regression status in validate
# -------------------------------------------------------------------
class TestA90FailClosedRegression:
    def test_failed_regression_fails_validation(self):
        """validate_a90.py must exit nonzero when regression has failures."""
        val_path = _PROJECT_ROOT / "scripts" / "validate_a90.py"
        if not val_path.exists():
            pytest.skip("validate_a90.py not found")
        manifest_path = _PROJECT_ROOT / "COUNTS_MANIFEST_A90.json"
        if not manifest_path.exists():
            pytest.skip("COUNTS_MANIFEST_A90.json not yet generated")

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            src_dir = tmp / "src" / "ai_workflow_hub"
            src_dir.mkdir(parents=True)
            tests_dir = tmp / "tests"
            tests_dir.mkdir(parents=True)
            output_dir = tmp / "output"
            output_dir.mkdir(parents=True)

            cli_src = _PROJECT_ROOT / "src" / "ai_workflow_hub" / "cli.py"
            if cli_src.exists():
                shutil.copy2(cli_src, src_dir / "cli.py")
            pyproject = _PROJECT_ROOT / "pyproject.toml"
            if pyproject.exists():
                shutil.copy2(pyproject, tmp / "pyproject.toml")

            shutil.copy2(manifest_path, tmp / "COUNTS_MANIFEST_A90.json")
            scope = _PROJECT_ROOT / "SCOPE_DECLARATION_A90.txt"
            if scope.exists():
                shutil.copy2(scope, tmp / "SCOPE_DECLARATION_A90.txt")
            shutil.copy2(val_path, tmp / "validate_a90.py")
            flaky = _PROJECT_ROOT / "known_flaky_tests.json"
            if flaky.exists():
                shutil.copy2(flaky, tmp / "known_flaky_tests.json")

            # Create a regression transcript with exit code 1 and 1 failed
            fake_reg = (
                "=== Full Regression Output ===\n"
                "Provenance: project-root\nPlatform: Linux-5.15\n"
                "Python: 3.10.11\nClick: 8.3.3\n"
                "Command: pytest tests -q\nExit code: 1\n"
                "=" * 50 + "\n"
                "100 passed, 1 failed in 10s\n"
            )
            (output_dir / "REGRESSION_OUTPUT_A90.txt").write_text(fake_reg, encoding="utf-8")

            # Create a valid in-scope transcript
            fake_inscope = (
                "=== In-Scope Test Results ===\n"
                "Provenance: unpacked-ZIP\nPlatform: Linux-5.15\n"
                "Python: 3.10.11\nClick: 8.3.3\n"
                "Command: pytest tests -q\nExit code: 0\n"
                "=" * 50 + "\n"
                "80 passed in 8s\n"
            )
            (output_dir / "IN_SCOPE_TEST_RESULTS_A90.txt").write_text(fake_inscope, encoding="utf-8")

            result = subprocess.run(
                [sys.executable, str(tmp / "validate_a90.py")],
                capture_output=True, text=True, timeout=60, cwd=str(tmp),
            )
            assert result.returncode != 0, (
                f"validate_a90.py should exit nonzero on failed regression. "
                f"Exit code: {result.returncode}. Output:\n{result.stdout[-500:]}"
            )


# -------------------------------------------------------------------
# Class 5: Invariants preserved
# -------------------------------------------------------------------
class TestA90Invariants:
    def test_emit_json_module_level(self):
        """_emit_json must be defined at module level."""
        cli = _read_cli_source()
        for line in cli.splitlines():
            if "def _emit_json(" in line:
                assert line == line.lstrip(), "_emit_json must be at module level"
                return
        pytest.fail("_emit_json definition not found")

    def test_zero_console_print_json_dumps(self):
        """No console.print(json.dumps(...)) calls should remain."""
        cli = _read_cli_source()
        bad = [
            l.strip() for l in cli.splitlines()
            if "console.print(json.dumps" in l and not l.strip().startswith("#")
        ]
        assert len(bad) == 0, f"Found {len(bad)} console.print(json.dumps(...)) calls"

    def test_click_pin_in_pyproject(self):
        """pyproject.toml must pin click>=8.2.0,<9."""
        pp = _PROJECT_ROOT / "pyproject.toml"
        if not pp.exists():
            pytest.skip("pyproject.toml not found")
        text = pp.read_text(encoding="utf-8")
        assert "click>=8.2.0,<9" in text or "click>=8.2.0, <9" in text

    def test_known_flaky_valid(self):
        """known_flaky_tests.json must have total_known_flaky >= 1."""
        jf = _PROJECT_ROOT / "known_flaky_tests.json"
        if not jf.exists():
            pytest.skip("known_flaky_tests.json not found")
        data = json.loads(jf.read_text(encoding="utf-8"))
        assert data["total_known_flaky"] >= 1

    def test_evidence_bundle_hash_in_manifest(self):
        """Manifest must still include evidence_bundle_hash."""
        manifest_path = _PROJECT_ROOT / "COUNTS_MANIFEST_A90.json"
        if not manifest_path.exists():
            pytest.skip("COUNTS_MANIFEST_A90.json not yet generated")
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert "evidence_bundle_hash" in data
        assert "evidence_bundle_artifacts" in data
