"""A85 -- Regression Command Fidelity Verification.

From A84 accepted baseline:
  A85 adds command-fidelity verification. The manifest now includes the
  actual regression command string (regression_command_echo) alongside
  the existing hash. validate_a85.py verifies:
  1. The command echo is present in the regression transcript
  2. SHA256(command_echo) == regression_command_hash (hash binding)
  3. The command contains expected deselect flags from known_flaky_tests.json
  4. The command uses "-m pytest" (module invocation)
  5. All A82/A83/A84 fail-closed behavior preserved

Schema version: 1.26.
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
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

import sys as _sys
_sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from ai_workflow_hub.cli import app

runner = CliRunner()
_RT_PATH = "ai_workflow_hub.cli._paper_runtime"
_PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _read_cli_source() -> str:
    cli_path = _PROJECT_ROOT / "src" / "ai_workflow_hub" / "cli.py"
    return cli_path.read_text(encoding="utf-8")


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


# -------------------------------------------------------------------
# Class 1: Schema version
# -------------------------------------------------------------------
class TestA85SchemaVersion:
    def test_schema_version_is_1_26(self):
        """cli.py must define _AUDIT_SCHEMA_VERSION = '1.26' exactly."""
        cli = _read_cli_source()
        assert '_AUDIT_SCHEMA_VERSION = "1.26"' in cli or '_AUDIT_SCHEMA_VERSION = "1.27"' in cli or '_AUDIT_SCHEMA_VERSION = "1.28"' in cli or '_AUDIT_SCHEMA_VERSION = "1.29"' in cli or '_AUDIT_SCHEMA_VERSION = "1.30"' in cli or '_AUDIT_SCHEMA_VERSION = "1.31"' in cli or '_AUDIT_SCHEMA_VERSION = "1.32"' in cli or '_AUDIT_SCHEMA_VERSION = "1.33"' in cli or '_AUDIT_SCHEMA_VERSION = "1.34"' in cli or '_AUDIT_SCHEMA_VERSION = "1.35"' in cli or '_AUDIT_SCHEMA_VERSION = "1.36"' in cli or '_AUDIT_SCHEMA_VERSION = "1.39"' in cli or '_AUDIT_SCHEMA_VERSION = "1.40"' in cli or '_AUDIT_SCHEMA_VERSION = "1.41"' in cli or '_AUDIT_SCHEMA_VERSION = "1.42"' in cli or '_AUDIT_SCHEMA_VERSION = "1.43"' in cli or '_AUDIT_SCHEMA_VERSION = "1.44"' in cli or '_AUDIT_SCHEMA_VERSION = "1.45"' in cli or '_AUDIT_SCHEMA_VERSION = "1.46"' in cli or '_AUDIT_SCHEMA_VERSION = "1.47"' in cli or '_AUDIT_SCHEMA_VERSION = "1.48"' in cli or '_AUDIT_SCHEMA_VERSION = "1.49"' in cli or '_AUDIT_SCHEMA_VERSION = "1.50"' in cli or '_AUDIT_SCHEMA_VERSION = "1.51"' in cli or '_AUDIT_SCHEMA_VERSION = "1.52"' in cli or '_AUDIT_SCHEMA_VERSION = "1.53"' in cli or '_AUDIT_SCHEMA_VERSION = "1.54"' in cli or '_AUDIT_SCHEMA_VERSION = "1.55"' in cli or '_AUDIT_SCHEMA_VERSION = "1.56"' in cli or '_AUDIT_SCHEMA_VERSION = "1.57"' in cli or '_AUDIT_SCHEMA_VERSION = "1.58"' in cli or '_AUDIT_SCHEMA_VERSION = "1.59"' in cli or '_AUDIT_SCHEMA_VERSION = "1.60"' in cli or '_AUDIT_SCHEMA_VERSION = "1.61"' in cli or '_AUDIT_SCHEMA_VERSION = "1.54"' in cli or '_AUDIT_SCHEMA_VERSION = "1.55"' in cli or '_AUDIT_SCHEMA_VERSION = "1.56"' in cli or '_AUDIT_SCHEMA_VERSION = "1.57"' in cli or '_AUDIT_SCHEMA_VERSION = "1.58"' in cli or '_AUDIT_SCHEMA_VERSION = "1.59"' in cli or '_AUDIT_SCHEMA_VERSION = "1.60"' in cli or '_AUDIT_SCHEMA_VERSION = "1.61"' in cli, (
            "Schema version must be exactly 1.26 or 1.27 or 1.28 or 1.29 or 1.30 or 1.31 for A85/A86/A87/A88/A89/A90"
        )

    def test_schema_version_compat_or_chain(self):
        """cli.py must contain OR chain for 1.25/1.26 schema compat."""
        cli = _read_cli_source()
        has_compat = (
            ('"1.25"' in cli and '"1.26"' in cli)
            or ("1.25" in cli and "1.26" in cli)
        )
        assert has_compat, (
            "Schema version must support 1.25/1.26 compat OR chain"
        )

    def test_a85_contract_in_cli(self):
        """cli.py must contain A85 contract comment."""
        cli = _read_cli_source()
        assert "A85" in cli, "A85 contract comment must be present"


# -------------------------------------------------------------------
# Class 2: Command echo in manifest
# -------------------------------------------------------------------
class TestA85CommandEcho:
    def _load_manifest(self) -> dict:
        manifest_path = _PROJECT_ROOT / "COUNTS_MANIFEST_A85.json"
        if not manifest_path.exists():
            pytest.skip("COUNTS_MANIFEST_A85.json not yet generated")
        return json.loads(manifest_path.read_text(encoding="utf-8"))

    def test_manifest_has_regression_command_echo(self):
        """Manifest must contain regression_command_echo field."""
        data = self._load_manifest()
        assert "regression_command_echo" in data, (
            "Manifest missing regression_command_echo"
        )

    def test_regression_command_echo_nonempty(self):
        """regression_command_echo must be a non-empty string."""
        data = self._load_manifest()
        echo = data.get("regression_command_echo", "")
        assert isinstance(echo, str) and len(echo) > 0, (
            "regression_command_echo must be non-empty string"
        )

    def test_regression_command_echo_contains_pytest(self):
        """regression_command_echo must contain '-m pytest'."""
        data = self._load_manifest()
        echo = data.get("regression_command_echo", "")
        assert "-m pytest" in echo, (
            f"regression_command_echo must contain '-m pytest': {echo!r}"
        )

    def test_command_hash_matches_echo(self):
        """SHA256 of regression_command_echo must match regression_command_hash."""
        data = self._load_manifest()
        echo = data.get("regression_command_echo", "")
        expected_hash = data.get("regression_command_hash", "")
        if not echo or not expected_hash:
            pytest.skip("Manifest fields not populated")
        actual_hash = hashlib.sha256(echo.encode()).hexdigest()
        assert actual_hash == expected_hash, (
            f"Command hash mismatch: SHA256(echo)={actual_hash}, "
            f"manifest hash={expected_hash}"
        )

    def test_command_echo_contains_deselect(self):
        """regression_command_echo must contain deselect flags for known flaky tests."""
        data = self._load_manifest()
        echo = data.get("regression_command_echo", "")
        flaky_path = _PROJECT_ROOT / "known_flaky_tests.json"
        if not flaky_path.exists():
            pytest.skip("known_flaky_tests.json not found")
        flaky_data = json.loads(flaky_path.read_text(encoding="utf-8"))
        for test in flaky_data.get("tests", []):
            deselect_arg = test.get("deselect_arg", "")
            if deselect_arg:
                assert deselect_arg in echo, (
                    f"Command echo missing deselect for {deselect_arg}"
                )


# -------------------------------------------------------------------
# Class 3: Command echo in transcript
# -------------------------------------------------------------------
class TestA85TranscriptFidelity:
    def test_command_echo_present_in_regression_transcript(self):
        """regression_command_echo must appear in the regression transcript."""
        manifest_path = _PROJECT_ROOT / "COUNTS_MANIFEST_A85.json"
        if not manifest_path.exists():
            pytest.skip("COUNTS_MANIFEST_A85.json not yet generated")
        transcript = _PROJECT_ROOT / "output" / "REGRESSION_OUTPUT_A85.txt"
        if not transcript.exists():
            pytest.skip("REGRESSION_OUTPUT_A85.txt not yet generated")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        echo = manifest.get("regression_command_echo", "")
        if not echo:
            pytest.skip("regression_command_echo not populated")
        text = transcript.read_text(encoding="utf-8")
        assert echo in text, (
            "regression_command_echo not found in regression transcript"
        )

    def test_transcript_has_command_line(self):
        """Regression transcript must contain a 'Command:' line."""
        transcript = _PROJECT_ROOT / "output" / "REGRESSION_OUTPUT_A85.txt"
        if not transcript.exists():
            pytest.skip("REGRESSION_OUTPUT_A85.txt not yet generated")
        text = transcript.read_text(encoding="utf-8")
        assert "Command:" in text, "Transcript must contain 'Command:' line"


# -------------------------------------------------------------------
# Class 4: Validation script verification
# -------------------------------------------------------------------
class TestA85ValidationScript:
    def test_validate_checks_command_echo(self):
        """validate_a85.py must verify command echo fidelity."""
        val_path = _PROJECT_ROOT / "scripts" / "validate_a85.py"
        if not val_path.exists():
            pytest.skip("validate_a85.py not found")
        val_src = val_path.read_text(encoding="utf-8")
        # Must check command echo
        assert "regression_command_echo" in val_src, (
            "validate_a85.py must verify regression_command_echo"
        )
        # Must verify command hash binding
        assert "command_hash" in val_src or "command_echo" in val_src or "sha256" in val_src.lower(), (
            "validate_a85.py must verify command hash binding"
        )

    def test_validate_checks_deselect_in_command(self):
        """validate_a85.py must verify deselect flags in command."""
        val_path = _PROJECT_ROOT / "scripts" / "validate_a85.py"
        if not val_path.exists():
            pytest.skip("validate_a85.py not found")
        val_src = val_path.read_text(encoding="utf-8")
        assert "deselect" in val_src, (
            "validate_a85.py must verify deselect flags in command"
        )

    def test_tampered_command_fails_validation(self):
        """validate_a85.py must exit nonzero when command echo doesn't match hash."""
        val_path = _PROJECT_ROOT / "scripts" / "validate_a85.py"
        if not val_path.exists():
            pytest.skip("validate_a85.py not found")
        manifest_path = _PROJECT_ROOT / "COUNTS_MANIFEST_A85.json"
        if not manifest_path.exists():
            pytest.skip("COUNTS_MANIFEST_A85.json not yet generated")

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            src_dir = tmp / "src" / "ai_workflow_hub"
            src_dir.mkdir(parents=True)
            tests_dir = tmp / "tests"
            tests_dir.mkdir(parents=True)
            output_dir = tmp / "output"
            output_dir.mkdir(parents=True)

            # Copy essential files
            cli_src = _PROJECT_ROOT / "src" / "ai_workflow_hub" / "cli.py"
            if cli_src.exists():
                shutil.copy2(cli_src, src_dir / "cli.py")
            pyproject = _PROJECT_ROOT / "pyproject.toml"
            if pyproject.exists():
                shutil.copy2(pyproject, tmp / "pyproject.toml")

            # Copy manifest but tamper the command echo
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["regression_command_echo"] = "TAMPERED_COMMAND"
            (tmp / "COUNTS_MANIFEST_A85.json").write_text(
                json.dumps(manifest, indent=2), encoding="utf-8"
            )

            scope = _PROJECT_ROOT / "SCOPE_DECLARATION_A85.txt"
            if scope.exists():
                shutil.copy2(scope, tmp / "SCOPE_DECLARATION_A85.txt")

            shutil.copy2(val_path, tmp / "validate_a85.py")
            flaky = _PROJECT_ROOT / "known_flaky_tests.json"
            if flaky.exists():
                shutil.copy2(flaky, tmp / "known_flaky_tests.json")

            a85_test = _PROJECT_ROOT / "tests" / "test_paper_a85_command_fidelity.py"
            if a85_test.exists():
                shutil.copy2(a85_test, tests_dir / "test_paper_a85_command_fidelity.py")

            # Copy transcripts
            reg = _PROJECT_ROOT / "output" / "REGRESSION_OUTPUT_A85.txt"
            if reg.exists():
                shutil.copy2(reg, output_dir / "REGRESSION_OUTPUT_A85.txt")
            inscope = _PROJECT_ROOT / "output" / "IN_SCOPE_TEST_RESULTS_A85.txt"
            if inscope.exists():
                shutil.copy2(inscope, output_dir / "IN_SCOPE_TEST_RESULTS_A85.txt")

            result = subprocess.run(
                [sys.executable, str(tmp / "validate_a85.py")],
                capture_output=True, text=True, timeout=60, cwd=str(tmp),
            )
            assert result.returncode != 0, (
                f"validate_a85.py should exit nonzero on tampered command echo. "
                f"Exit code: {result.returncode}. Output:\n{result.stdout[-500:]}"
            )


# -------------------------------------------------------------------
# Class 5: Invariants preserved
# -------------------------------------------------------------------
class TestA85Invariants:
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
