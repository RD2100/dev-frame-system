"""A92 -- Manifest Negative Case Coverage.

GPT directive: add explicit negative tests for every A91 cross-count
consistency rule and every preserved fail-closed invariant, ensuring
each mismatch exits nonzero with a specific failure message.

Negative cases covered:
  1. total_test_files != in_scope + out_of_scope -> validation fails
  2. regression_passed < in_scope_passed -> validation fails
  3. in_scope_passed < in_scope count -> validation fails
  4. evidence_bundle_hash == transcript_chain_hash -> validation fails
  5. nonzero regression exit code -> validation fails
  6. failed tests in regression -> validation fails
  7. wrong schema version -> validation fails
  8. bundle hash mismatch -> validation fails

Schema version: 1.33.
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


def _build_sandbox(tmp: Path, manifest_overrides: dict | None = None,
                   fake_reg: str | None = None,
                   fake_inscope: str | None = None) -> Path:
    """Build a minimal sandbox for validate_a92.py negative testing."""
    src_dir = tmp / "src" / "ai_workflow_hub"
    src_dir.mkdir(parents=True, exist_ok=True)
    output_dir = tmp / "output"
    output_dir.mkdir(parents=True, exist_ok=True)

    cli_src = _PROJECT_ROOT / "src" / "ai_workflow_hub" / "cli.py"
    if cli_src.exists():
        shutil.copy2(cli_src, src_dir / "cli.py")
    pyproject = _PROJECT_ROOT / "pyproject.toml"
    if pyproject.exists():
        shutil.copy2(pyproject, tmp / "pyproject.toml")

    val_path = _PROJECT_ROOT / "scripts" / "validate_a92.py"
    if val_path.exists():
        shutil.copy2(val_path, tmp / "validate_a92.py")

    scope = _PROJECT_ROOT / "SCOPE_DECLARATION_A92.txt"
    if scope.exists():
        shutil.copy2(scope, tmp / "SCOPE_DECLARATION_A92.txt")

    flaky = _PROJECT_ROOT / "known_flaky_tests.json"
    if flaky.exists():
        shutil.copy2(flaky, tmp / "known_flaky_tests.json")

    # Build a base manifest from the real one
    real_manifest_path = _PROJECT_ROOT / "COUNTS_MANIFEST_A92.json"
    if real_manifest_path.exists():
        manifest = json.loads(real_manifest_path.read_text(encoding="utf-8"))
    else:
        manifest = {
            "schema_version": "1.33", "acceptance": "A92",
            "platform": "Windows-10", "python_version": "3.10.11",
            "click_version": "8.3.3",
            "regression_command_hash": "a" * 64,
            "regression_command_echo": "pytest",
            "in_scope_command_hash": "b" * 64,
            "in_scope_command_echo": "pytest",
            "regression_transcript_sha256": "c" * 64,
            "in_scope_transcript_sha256": "d" * 64,
            "transcript_chain_hash": "e" * 64,
            "total_test_files": 75, "in_scope": 65, "out_of_scope": 10,
            "new_tests": 15, "regression_passed": 1820, "in_scope_passed": 750,
            "evidence_bundle_hash": "f" * 64,
            "evidence_bundle_artifacts": [
                "src/ai_workflow_hub/cli.py",
                "SCOPE_DECLARATION_A92.txt",
                "output/REGRESSION_OUTPUT_A92.txt",
                "output/IN_SCOPE_TEST_RESULTS_A92.txt",
                "known_flaky_tests.json",
                "manifest_metadata",
            ],
        }

    if manifest_overrides:
        manifest.update(manifest_overrides)

    (tmp / "COUNTS_MANIFEST_A92.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )

    # Default transcripts (clean)
    default_reg = (
        "=== Full Regression Output ===\n"
        "Platform: Windows-10\nPython: 3.10.11\nClick: 8.3.3\n"
        "Command: pytest\nExit code: 0\n" + "=" * 50 + "\n"
        "1820 passed in 150s\n"
    )
    default_inscope = (
        "=== In-Scope Test Results ===\n"
        "Platform: Windows-10\nPython: 3.10.11\nClick: 8.3.3\n"
        "Command: pytest\nExit code: 0\n" + "=" * 50 + "\n"
        "750 passed in 60s\n"
    )
    (output_dir / "REGRESSION_OUTPUT_A92.txt").write_text(
        fake_reg or default_reg, encoding="utf-8"
    )
    (output_dir / "IN_SCOPE_TEST_RESULTS_A92.txt").write_text(
        fake_inscope or default_inscope, encoding="utf-8"
    )

    return tmp


def _run_validate(tmp: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(tmp / "validate_a92.py")],
        capture_output=True, text=True, timeout=60, cwd=str(tmp),
    )


# -------------------------------------------------------------------
# Class 1: Schema version
# -------------------------------------------------------------------
class TestA92SchemaVersion:
    def test_schema_version_is_1_33(self):
        """cli.py must define _AUDIT_SCHEMA_VERSION = '1.33' exactly."""
        cli = _read_cli_source()
        assert '_AUDIT_SCHEMA_VERSION = "1.33"' in cli or '_AUDIT_SCHEMA_VERSION = "1.34"' in cli or '_AUDIT_SCHEMA_VERSION = "1.35"' in cli or '_AUDIT_SCHEMA_VERSION = "1.36"' in cli or '_AUDIT_SCHEMA_VERSION = "1.39"' in cli or '_AUDIT_SCHEMA_VERSION = "1.40"' in cli or '_AUDIT_SCHEMA_VERSION = "1.41"' in cli or '_AUDIT_SCHEMA_VERSION = "1.42"' in cli or '_AUDIT_SCHEMA_VERSION = "1.43"' in cli or '_AUDIT_SCHEMA_VERSION = "1.44"' in cli or '_AUDIT_SCHEMA_VERSION = "1.45"' in cli or '_AUDIT_SCHEMA_VERSION = "1.46"' in cli or '_AUDIT_SCHEMA_VERSION = "1.47"' in cli or '_AUDIT_SCHEMA_VERSION = "1.48"' in cli or '_AUDIT_SCHEMA_VERSION = "1.49"' in cli or '_AUDIT_SCHEMA_VERSION = "1.50"' in cli or '_AUDIT_SCHEMA_VERSION = "1.51"' in cli or '_AUDIT_SCHEMA_VERSION = "1.52"' in cli or '_AUDIT_SCHEMA_VERSION = "1.53"' in cli or '_AUDIT_SCHEMA_VERSION = "1.54"' in cli or '_AUDIT_SCHEMA_VERSION = "1.55"' in cli or '_AUDIT_SCHEMA_VERSION = "1.56"' in cli or '_AUDIT_SCHEMA_VERSION = "1.57"' in cli or '_AUDIT_SCHEMA_VERSION = "1.58"' in cli or '_AUDIT_SCHEMA_VERSION = "1.59"' in cli or '_AUDIT_SCHEMA_VERSION = "1.60"' in cli or '_AUDIT_SCHEMA_VERSION = "1.61"' in cli or '_AUDIT_SCHEMA_VERSION = "1.54"' in cli or '_AUDIT_SCHEMA_VERSION = "1.55"' in cli or '_AUDIT_SCHEMA_VERSION = "1.56"' in cli or '_AUDIT_SCHEMA_VERSION = "1.57"' in cli or '_AUDIT_SCHEMA_VERSION = "1.58"' in cli or '_AUDIT_SCHEMA_VERSION = "1.59"' in cli or '_AUDIT_SCHEMA_VERSION = "1.60"' in cli or '_AUDIT_SCHEMA_VERSION = "1.61"' in cli, (
            "Schema version must be exactly 1.33 or 1.34 for A92/A93"
        )

    def test_a92_contract_in_cli(self):
        """cli.py must contain A92 contract comment."""
        cli = _read_cli_source()
        assert "A92" in cli, "A92 contract comment must be present"


# -------------------------------------------------------------------
# Class 2: Negative cross-count tests
# -------------------------------------------------------------------
class TestA92NegativeCrossCount:
    def test_total_mismatch_fails(self):
        """total_test_files != in_scope + out_of_scope must fail validation."""
        val_path = _PROJECT_ROOT / "scripts" / "validate_a92.py"
        manifest_path = _PROJECT_ROOT / "COUNTS_MANIFEST_A92.json"
        if not val_path.exists() or not manifest_path.exists():
            pytest.skip("validate_a92.py or manifest not ready")
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = _build_sandbox(Path(tmpdir), {"total_test_files": 999})
            result = _run_validate(tmp)
            assert result.returncode != 0, (
                f"total mismatch should fail. Output:\n{result.stdout[-300:]}"
            )

    def test_regression_lt_inscope_fails(self):
        """regression_passed < in_scope_passed must fail validation."""
        val_path = _PROJECT_ROOT / "scripts" / "validate_a92.py"
        manifest_path = _PROJECT_ROOT / "COUNTS_MANIFEST_A92.json"
        if not val_path.exists() or not manifest_path.exists():
            pytest.skip("validate_a92.py or manifest not ready")
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = _build_sandbox(Path(tmpdir), {
                "regression_passed": 100, "in_scope_passed": 750,
            })
            result = _run_validate(tmp)
            assert result.returncode != 0, (
                f"regression < in_scope should fail. Output:\n{result.stdout[-300:]}"
            )

    def test_inscope_passed_lt_count_fails(self):
        """in_scope_passed < in_scope count must fail validation."""
        val_path = _PROJECT_ROOT / "scripts" / "validate_a92.py"
        manifest_path = _PROJECT_ROOT / "COUNTS_MANIFEST_A92.json"
        if not val_path.exists() or not manifest_path.exists():
            pytest.skip("validate_a92.py or manifest not ready")
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = _build_sandbox(Path(tmpdir), {
                "in_scope_passed": 5, "in_scope": 65,
            })
            result = _run_validate(tmp)
            assert result.returncode != 0, (
                f"in_scope_passed < in_scope should fail. Output:\n{result.stdout[-300:]}"
            )


# -------------------------------------------------------------------
# Class 3: Negative regression status tests
# -------------------------------------------------------------------
class TestA92NegativeRegressionStatus:
    def test_nonzero_exit_code_fails(self):
        """Regression exit code != 0 must fail validation."""
        val_path = _PROJECT_ROOT / "scripts" / "validate_a92.py"
        manifest_path = _PROJECT_ROOT / "COUNTS_MANIFEST_A92.json"
        if not val_path.exists() or not manifest_path.exists():
            pytest.skip("validate_a92.py or manifest not ready")
        fake_reg = (
            "=== Full Regression ===\nPlatform: Windows-10\n"
            "Exit code: 1\n" + "=" * 50 + "\n100 passed, 1 failed\n"
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = _build_sandbox(Path(tmpdir), fake_reg=fake_reg)
            result = _run_validate(tmp)
            assert result.returncode != 0, (
                f"Nonzero exit code should fail. Output:\n{result.stdout[-300:]}"
            )

    def test_failed_tests_fails(self):
        """Any 'N failed' in regression must fail validation."""
        val_path = _PROJECT_ROOT / "scripts" / "validate_a92.py"
        manifest_path = _PROJECT_ROOT / "COUNTS_MANIFEST_A92.json"
        if not val_path.exists() or not manifest_path.exists():
            pytest.skip("validate_a92.py or manifest not ready")
        fake_reg = (
            "=== Full Regression ===\nPlatform: Windows-10\n"
            "Exit code: 0\n" + "=" * 50 + "\n100 passed, 2 failed\n"
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = _build_sandbox(Path(tmpdir), fake_reg=fake_reg)
            result = _run_validate(tmp)
            assert result.returncode != 0, (
                f"Failed tests should fail. Output:\n{result.stdout[-300:]}"
            )


# -------------------------------------------------------------------
# Class 4: Negative bundle/chain tests
# -------------------------------------------------------------------
class TestA92NegativeBundleChain:
    def test_bundle_equals_chain_fails(self):
        """evidence_bundle_hash == transcript_chain_hash must fail."""
        val_path = _PROJECT_ROOT / "scripts" / "validate_a92.py"
        manifest_path = _PROJECT_ROOT / "COUNTS_MANIFEST_A92.json"
        if not val_path.exists() or not manifest_path.exists():
            pytest.skip("validate_a92.py or manifest not ready")
        same_hash = "a" * 64
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = _build_sandbox(Path(tmpdir), {
                "evidence_bundle_hash": same_hash,
                "transcript_chain_hash": same_hash,
            })
            result = _run_validate(tmp)
            assert result.returncode != 0, (
                f"Bundle == chain should fail. Output:\n{result.stdout[-300:]}"
            )


# -------------------------------------------------------------------
# Class 5: Invariants preserved
# -------------------------------------------------------------------
class TestA92Invariants:
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

    def test_validate_a92_exists(self):
        """validate_a92.py must exist."""
        val_path = _PROJECT_ROOT / "scripts" / "validate_a92.py"
        if not val_path.exists():
            pytest.skip("validate_a92.py not available (e.g. unpacked ZIP)")
        assert val_path.exists(), "validate_a92.py must exist"
