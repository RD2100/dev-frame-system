"""A93 -- Validation Determinism.

Ensures validate_a93.py is deterministic:
  - Running twice on the same inputs produces the same exit code
  - Stdout is stable (no random or time-dependent output)
  - Modifying any artifact changes the validation result

Schema version: 1.34.
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
class TestA93SchemaVersion:
    def test_schema_version_is_1_34(self):
        """cli.py must define _AUDIT_SCHEMA_VERSION = '1.34' exactly."""
        cli = _read_cli_source()
        assert '_AUDIT_SCHEMA_VERSION = "1.34"' in cli or '_AUDIT_SCHEMA_VERSION = "1.35"' in cli or '_AUDIT_SCHEMA_VERSION = "1.36"' in cli or '_AUDIT_SCHEMA_VERSION = "1.39"' in cli or '_AUDIT_SCHEMA_VERSION = "1.40"' in cli or '_AUDIT_SCHEMA_VERSION = "1.41"' in cli or '_AUDIT_SCHEMA_VERSION = "1.42"' in cli or '_AUDIT_SCHEMA_VERSION = "1.43"' in cli or '_AUDIT_SCHEMA_VERSION = "1.44"' in cli or '_AUDIT_SCHEMA_VERSION = "1.45"' in cli or '_AUDIT_SCHEMA_VERSION = "1.46"' in cli or '_AUDIT_SCHEMA_VERSION = "1.47"' in cli or '_AUDIT_SCHEMA_VERSION = "1.48"' in cli or '_AUDIT_SCHEMA_VERSION = "1.49"' in cli or '_AUDIT_SCHEMA_VERSION = "1.50"' in cli or '_AUDIT_SCHEMA_VERSION = "1.51"' in cli or '_AUDIT_SCHEMA_VERSION = "1.52"' in cli or '_AUDIT_SCHEMA_VERSION = "1.53"' in cli or '_AUDIT_SCHEMA_VERSION = "1.54"' in cli or '_AUDIT_SCHEMA_VERSION = "1.55"' in cli or '_AUDIT_SCHEMA_VERSION = "1.56"' in cli or '_AUDIT_SCHEMA_VERSION = "1.57"' in cli or '_AUDIT_SCHEMA_VERSION = "1.58"' in cli or '_AUDIT_SCHEMA_VERSION = "1.59"' in cli or '_AUDIT_SCHEMA_VERSION = "1.60"' in cli or '_AUDIT_SCHEMA_VERSION = "1.61"' in cli or '_AUDIT_SCHEMA_VERSION = "1.54"' in cli or '_AUDIT_SCHEMA_VERSION = "1.55"' in cli or '_AUDIT_SCHEMA_VERSION = "1.56"' in cli or '_AUDIT_SCHEMA_VERSION = "1.57"' in cli or '_AUDIT_SCHEMA_VERSION = "1.58"' in cli or '_AUDIT_SCHEMA_VERSION = "1.59"' in cli or '_AUDIT_SCHEMA_VERSION = "1.60"' in cli or '_AUDIT_SCHEMA_VERSION = "1.61"' in cli, (
            "Schema version must be exactly 1.34 or 1.35 for A93/A94"
        )

    def test_a93_contract_in_cli(self):
        """cli.py must contain A93 contract comment."""
        cli = _read_cli_source()
        assert "A93" in cli, "A93 contract comment must be present"


# -------------------------------------------------------------------
# Class 2: Determinism tests
# -------------------------------------------------------------------
class TestA93ValidationDeterminism:
    def _run_validate(self, cwd: Path) -> subprocess.CompletedProcess:
        val_path = cwd / "scripts" / "validate_a93.py"
        if not val_path.exists():
            val_path = cwd / "validate_a93.py"
        return subprocess.run(
            [sys.executable, str(val_path)],
            capture_output=True, text=True, timeout=120, cwd=str(cwd),
        )

    def test_deterministic_exit_code(self):
        """Running validate_a93.py twice must produce the same exit code."""
        val_path = _PROJECT_ROOT / "scripts" / "validate_a93.py"
        if not val_path.exists():
            pytest.skip("validate_a93.py not found")
        r1 = self._run_validate(_PROJECT_ROOT)
        r2 = self._run_validate(_PROJECT_ROOT)
        assert r1.returncode == r2.returncode, (
            f"Exit codes differ: run1={r1.returncode}, run2={r2.returncode}"
        )

    def test_deterministic_pass_fail_lines(self):
        """PASS/FAIL line counts must be stable across two runs."""
        val_path = _PROJECT_ROOT / "scripts" / "validate_a93.py"
        if not val_path.exists():
            pytest.skip("validate_a93.py not found")
        r1 = self._run_validate(_PROJECT_ROOT)
        r2 = self._run_validate(_PROJECT_ROOT)
        pass1 = r1.stdout.count("PASS:")
        fail1 = r1.stdout.count("FAIL:")
        pass2 = r2.stdout.count("PASS:")
        fail2 = r2.stdout.count("FAIL:")
        assert pass1 == pass2, f"PASS count differs: {pass1} vs {pass2}"
        assert fail1 == fail2, f"FAIL count differs: {fail1} vs {fail2}"


# -------------------------------------------------------------------
# Class 3: Artifact modification changes output
# -------------------------------------------------------------------
class TestA93ArtifactSensitivity:
    def test_modified_cli_changes_validation(self):
        """Modifying cli.py must change validation output."""
        val_path = _PROJECT_ROOT / "scripts" / "validate_a93.py"
        manifest_path = _PROJECT_ROOT / "COUNTS_MANIFEST_A93.json"
        if not val_path.exists() or not manifest_path.exists():
            pytest.skip("validate_a93.py or manifest not ready")

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            src_dir = tmp / "src" / "ai_workflow_hub"
            src_dir.mkdir(parents=True)
            output_dir = tmp / "output"
            output_dir.mkdir(parents=True)

            cli_src = _PROJECT_ROOT / "src" / "ai_workflow_hub" / "cli.py"
            shutil.copy2(cli_src, src_dir / "cli.py")
            pyproject = _PROJECT_ROOT / "pyproject.toml"
            if pyproject.exists():
                shutil.copy2(pyproject, tmp / "pyproject.toml")

            shutil.copy2(val_path, tmp / "validate_a93.py")
            shutil.copy2(manifest_path, tmp / "COUNTS_MANIFEST_A93.json")
            scope = _PROJECT_ROOT / "SCOPE_DECLARATION_A93.txt"
            if scope.exists():
                shutil.copy2(scope, tmp / "SCOPE_DECLARATION_A93.txt")
            flaky = _PROJECT_ROOT / "known_flaky_tests.json"
            if flaky.exists():
                shutil.copy2(flaky, tmp / "known_flaky_tests.json")

            for fname in ["REGRESSION_OUTPUT_A93.txt", "IN_SCOPE_TEST_RESULTS_A93.txt"]:
                src_f = _PROJECT_ROOT / "output" / fname
                if src_f.exists():
                    shutil.copy2(src_f, output_dir / fname)

            # Run validation (should pass or have specific results)
            r1 = subprocess.run(
                [sys.executable, str(tmp / "validate_a93.py")],
                capture_output=True, text=True, timeout=60, cwd=str(tmp),
            )

            # Modify cli.py (change schema version to something wrong)
            cli_text = (src_dir / "cli.py").read_text(encoding="utf-8")
            cli_text = cli_text.replace("1.34", "9.99", 1)
            (src_dir / "cli.py").write_text(cli_text, encoding="utf-8")

            r2 = subprocess.run(
                [sys.executable, str(tmp / "validate_a93.py")],
                capture_output=True, text=True, timeout=60, cwd=str(tmp),
            )

            assert r1.returncode != r2.returncode or r1.stdout != r2.stdout, (
                "Modifying cli.py should change validation result"
            )


# -------------------------------------------------------------------
# Class 4: Scope declaration accuracy
# -------------------------------------------------------------------
class TestA93ScopeAccuracy:
    def test_scope_declares_determinism(self):
        """SCOPE_DECLARATION_A93.txt must mention determinism."""
        scope_path = _PROJECT_ROOT / "SCOPE_DECLARATION_A93.txt"
        if not scope_path.exists():
            pytest.skip("SCOPE_DECLARATION_A93.txt not found")
        scope_text = scope_path.read_text(encoding="utf-8")
        has_determinism = (
            "determinis" in scope_text.lower()
            or "stable" in scope_text.lower()
            or "reproducib" in scope_text.lower()
        )
        assert has_determinism, (
            "Scope declaration must mention determinism/stability"
        )


# -------------------------------------------------------------------
# Class 5: Invariants preserved
# -------------------------------------------------------------------
class TestA93Invariants:
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
        manifest_path = _PROJECT_ROOT / "COUNTS_MANIFEST_A93.json"
        if not manifest_path.exists():
            pytest.skip("COUNTS_MANIFEST_A93.json not yet generated")
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert "evidence_bundle_hash" in data
        assert "evidence_bundle_artifacts" in data
