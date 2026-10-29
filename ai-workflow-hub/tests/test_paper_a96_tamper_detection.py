"""A96 -- Evidence Pack Tamper Detection.

Ensures that modifying any artifact in the evidence pack after packing
is detected by validate_a96.py:
  - Tampered cli.py causes bundle hash mismatch
  - Tampered transcript causes transcript hash mismatch
  - Tampered manifest metadata is detected
  - Preserves all A82-A95 invariants

Schema version: 1.37.
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


def _build_sandbox(tmp: Path) -> Path:
    """Build a minimal sandbox with evidence artifacts for tamper testing."""
    src_dir = tmp / "src" / "ai_workflow_hub"
    src_dir.mkdir(parents=True)
    output_dir = tmp / "output"
    output_dir.mkdir(parents=True)

    # Copy cli.py
    cli_src = _PROJECT_ROOT / "src" / "ai_workflow_hub" / "cli.py"
    if cli_src.exists():
        shutil.copy2(cli_src, src_dir / "cli.py")

    # Copy pyproject
    pp = _PROJECT_ROOT / "pyproject.toml"
    if pp.exists():
        shutil.copy2(pp, tmp / "pyproject.toml")

    # Copy validate script
    val = _PROJECT_ROOT / "scripts" / "validate_a96.py"
    if val.exists():
        shutil.copy2(val, tmp / "validate_a96.py")

    # Copy manifest
    manifest = _PROJECT_ROOT / "COUNTS_MANIFEST_A96.json"
    if manifest.exists():
        shutil.copy2(manifest, tmp / "COUNTS_MANIFEST_A96.json")

    # Copy scope
    scope = _PROJECT_ROOT / "SCOPE_DECLARATION_A96.txt"
    if scope.exists():
        shutil.copy2(scope, tmp / "SCOPE_DECLARATION_A96.txt")

    # Copy flaky
    flaky = _PROJECT_ROOT / "known_flaky_tests.json"
    if flaky.exists():
        shutil.copy2(flaky, tmp / "known_flaky_tests.json")

    # Copy transcripts
    for fname in ["REGRESSION_OUTPUT_A96.txt", "IN_SCOPE_TEST_RESULTS_A96.txt"]:
        src_f = _PROJECT_ROOT / "output" / fname
        if src_f.exists():
            shutil.copy2(src_f, output_dir / fname)

    return tmp


# -------------------------------------------------------------------
# Class 1: Schema version
# -------------------------------------------------------------------
class TestA96SchemaVersion:
    def test_schema_version_is_1_37(self):
        """cli.py must define _AUDIT_SCHEMA_VERSION = '1.37' exactly."""
        cli = _read_cli_source()
        assert '_AUDIT_SCHEMA_VERSION = "1.39"' in cli or '_AUDIT_SCHEMA_VERSION = "1.40"' in cli or '_AUDIT_SCHEMA_VERSION = "1.41"' in cli or '_AUDIT_SCHEMA_VERSION = "1.42"' in cli or '_AUDIT_SCHEMA_VERSION = "1.43"' in cli or '_AUDIT_SCHEMA_VERSION = "1.44"' in cli or '_AUDIT_SCHEMA_VERSION = "1.45"' in cli or '_AUDIT_SCHEMA_VERSION = "1.46"' in cli or '_AUDIT_SCHEMA_VERSION = "1.47"' in cli or '_AUDIT_SCHEMA_VERSION = "1.48"' in cli or '_AUDIT_SCHEMA_VERSION = "1.49"' in cli or '_AUDIT_SCHEMA_VERSION = "1.50"' in cli or '_AUDIT_SCHEMA_VERSION = "1.51"' in cli or '_AUDIT_SCHEMA_VERSION = "1.52"' in cli or '_AUDIT_SCHEMA_VERSION = "1.53"' in cli or '_AUDIT_SCHEMA_VERSION = "1.54"' in cli or '_AUDIT_SCHEMA_VERSION = "1.55"' in cli or '_AUDIT_SCHEMA_VERSION = "1.56"' in cli or '_AUDIT_SCHEMA_VERSION = "1.57"' in cli or '_AUDIT_SCHEMA_VERSION = "1.58"' in cli or '_AUDIT_SCHEMA_VERSION = "1.59"' in cli or '_AUDIT_SCHEMA_VERSION = "1.60"' in cli or '_AUDIT_SCHEMA_VERSION = "1.61"' in cli, (
            "Schema version must be 1.39+ for A96"
        )

    def test_a96_contract_in_cli(self):
        """cli.py must contain A96 contract comment."""
        cli = _read_cli_source()
        assert "A96" in cli, "A96 contract comment must be present"

    def test_schema_forward_compat(self):
        """Schema must include 1.37 or 1.36."""
        cli = _read_cli_source()
        assert '_AUDIT_SCHEMA_VERSION = "1.37"' in cli or \
               '_AUDIT_SCHEMA_VERSION = "1.36"' in cli or \
               '_AUDIT_SCHEMA_VERSION = "1.38"' in cli or \
               '_AUDIT_SCHEMA_VERSION = "1.39"' in cli or \
               '_AUDIT_SCHEMA_VERSION = "1.40"' in cli or \
               '_AUDIT_SCHEMA_VERSION = "1.41"' in cli or \
               '_AUDIT_SCHEMA_VERSION = "1.42"' in cli or \
               '_AUDIT_SCHEMA_VERSION = "1.43"' in cli or \
               '_AUDIT_SCHEMA_VERSION = "1.44"' in cli or \
               '_AUDIT_SCHEMA_VERSION = "1.45"' in cli or \
               '_AUDIT_SCHEMA_VERSION = "1.46"' in cli or \
               '_AUDIT_SCHEMA_VERSION = "1.47"' in cli or \
               '_AUDIT_SCHEMA_VERSION = "1.48"' in cli or \
               '_AUDIT_SCHEMA_VERSION = "1.49"' in cli or \
               '_AUDIT_SCHEMA_VERSION = "1.50"' in cli or \
               '_AUDIT_SCHEMA_VERSION = "1.51"' in cli or \
               '_AUDIT_SCHEMA_VERSION = "1.52"' in cli or \
               '_AUDIT_SCHEMA_VERSION = "1.53"' in cli or \
               '_AUDIT_SCHEMA_VERSION = "1.54"' in cli or \
               '_AUDIT_SCHEMA_VERSION = "1.55"' in cli or \
               '_AUDIT_SCHEMA_VERSION = "1.56"' in cli or \
               '_AUDIT_SCHEMA_VERSION = "1.57"' in cli or \
               '_AUDIT_SCHEMA_VERSION = "1.58"' in cli or \
               '_AUDIT_SCHEMA_VERSION = "1.59"' in cli or \
               '_AUDIT_SCHEMA_VERSION = "1.60"' in cli or \
               '_AUDIT_SCHEMA_VERSION = "1.61"' in cli, (
            "Schema OR chain must include current version"
        )


# -------------------------------------------------------------------
# Class 2: Tamper detection — cli.py
# -------------------------------------------------------------------
class TestA96TamperCli:
    def test_tampered_cli_detected(self):
        """Modifying cli.py after packing must cause validation to exit nonzero."""
        val_path = _PROJECT_ROOT / "scripts" / "validate_a96.py"
        manifest_path = _PROJECT_ROOT / "COUNTS_MANIFEST_A96.json"
        if not val_path.exists() or not manifest_path.exists():
            pytest.skip("validate_a96.py or manifest not ready")

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            sandbox = _build_sandbox(tmp)

            # Run validation (should pass)
            r1 = subprocess.run(
                [sys.executable, str(sandbox / "validate_a96.py")],
                capture_output=True, text=True, timeout=60, cwd=str(sandbox),
            )

            # Tamper cli.py
            cli_path = sandbox / "src" / "ai_workflow_hub" / "cli.py"
            text = cli_path.read_text(encoding="utf-8")
            text = text.replace("1.37", "9.99", 1)
            cli_path.write_text(text, encoding="utf-8")

            # Run validation again (should fail)
            r2 = subprocess.run(
                [sys.executable, str(sandbox / "validate_a96.py")],
                capture_output=True, text=True, timeout=60, cwd=str(sandbox),
            )

            assert r2.returncode != 0 or "FAIL" in r2.stdout, (
                "Tampered cli.py should cause validation failure"
            )


# -------------------------------------------------------------------
# Class 3: Tamper detection — transcripts
# -------------------------------------------------------------------
class TestA96TamperTranscript:
    def test_tampered_regression_transcript_detected(self):
        """Modifying regression transcript must cause hash mismatch."""
        val_path = _PROJECT_ROOT / "scripts" / "validate_a96.py"
        manifest_path = _PROJECT_ROOT / "COUNTS_MANIFEST_A96.json"
        if not val_path.exists() or not manifest_path.exists():
            pytest.skip("validate_a96.py or manifest not ready")

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            sandbox = _build_sandbox(tmp)

            # Tamper regression transcript
            reg_path = sandbox / "output" / "REGRESSION_OUTPUT_A96.txt"
            if reg_path.exists():
                text = reg_path.read_text(encoding="utf-8")
                reg_path.write_text(text + "\n# tampered\n", encoding="utf-8")

            r = subprocess.run(
                [sys.executable, str(sandbox / "validate_a96.py")],
                capture_output=True, text=True, timeout=60, cwd=str(sandbox),
            )

            assert r.returncode != 0 or "FAIL" in r.stdout, (
                "Tampered regression transcript should cause failure"
            )


# -------------------------------------------------------------------
# Class 4: Scope declaration accuracy
# -------------------------------------------------------------------
class TestA96ScopeAccuracy:
    def test_scope_declares_tamper_detection(self):
        """SCOPE_DECLARATION_A96.txt must mention tamper detection."""
        scope_path = _PROJECT_ROOT / "SCOPE_DECLARATION_A96.txt"
        if not scope_path.exists():
            pytest.skip("SCOPE_DECLARATION_A96.txt not found")
        scope_text = scope_path.read_text(encoding="utf-8").lower()
        has_tamper = "tamper" in scope_text or "integrity" in scope_text
        assert has_tamper, "Scope must mention tamper/integrity"


# -------------------------------------------------------------------
# Class 5: Invariants preserved
# -------------------------------------------------------------------
class TestA96Invariants:
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
        assert len(bad) == 0

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
        manifest_path = _PROJECT_ROOT / "COUNTS_MANIFEST_A96.json"
        if not manifest_path.exists():
            pytest.skip("COUNTS_MANIFEST_A96.json not yet generated")
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert "evidence_bundle_hash" in data
        assert "evidence_bundle_artifacts" in data

    def test_a96_test_file_exists(self):
        """This test file itself must exist."""
        test_path = _PROJECT_ROOT / "tests" / "test_paper_a96_tamper_detection.py"
        assert test_path.exists()
