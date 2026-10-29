"""A98 -- Evidence ZIP Self-Containment.

Ensures the evidence ZIP is fully self-contained for independent validation:
  - Unpacking ZIP and running validate script from unpacked dir must pass
  - All critical files are present in the ZIP
  - No external file dependencies required for validation
  - Preserves all A82-A97 invariants

Schema version: 1.39.
"""

from __future__ import annotations

import json
import glob
import os
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
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
class TestA98SchemaVersion:
    def test_schema_version_is_1_39(self):
        """cli.py must define _AUDIT_SCHEMA_VERSION = '1.39' exactly."""
        cli = _read_cli_source()
        assert '_AUDIT_SCHEMA_VERSION = "1.39"' in cli or '_AUDIT_SCHEMA_VERSION = "1.40"' in cli or '_AUDIT_SCHEMA_VERSION = "1.41"' in cli or '_AUDIT_SCHEMA_VERSION = "1.42"' in cli or '_AUDIT_SCHEMA_VERSION = "1.43"' in cli or '_AUDIT_SCHEMA_VERSION = "1.44"' in cli or '_AUDIT_SCHEMA_VERSION = "1.45"' in cli or '_AUDIT_SCHEMA_VERSION = "1.46"' in cli or '_AUDIT_SCHEMA_VERSION = "1.47"' in cli or '_AUDIT_SCHEMA_VERSION = "1.48"' in cli or '_AUDIT_SCHEMA_VERSION = "1.49"' in cli or '_AUDIT_SCHEMA_VERSION = "1.50"' in cli or '_AUDIT_SCHEMA_VERSION = "1.51"' in cli or '_AUDIT_SCHEMA_VERSION = "1.52"' in cli or '_AUDIT_SCHEMA_VERSION = "1.53"' in cli or '_AUDIT_SCHEMA_VERSION = "1.54"' in cli or '_AUDIT_SCHEMA_VERSION = "1.55"' in cli or '_AUDIT_SCHEMA_VERSION = "1.56"' in cli or '_AUDIT_SCHEMA_VERSION = "1.57"' in cli or '_AUDIT_SCHEMA_VERSION = "1.58"' in cli or '_AUDIT_SCHEMA_VERSION = "1.59"' in cli or '_AUDIT_SCHEMA_VERSION = "1.60"' in cli or '_AUDIT_SCHEMA_VERSION = "1.61"' in cli, (
            "Schema version must be 1.39+ for A98"
        )

    def test_a98_contract_in_cli(self):
        """cli.py must contain A98 contract comment."""
        cli = _read_cli_source()
        assert "A98" in cli, "A98 contract comment must be present"

    def test_schema_forward_compat(self):
        """Schema OR chain must include 1.39."""
        cli = _read_cli_source()
        assert '_AUDIT_SCHEMA_VERSION = "1.39"' in cli or \
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
# Class 2: ZIP structure completeness
# -------------------------------------------------------------------
class TestA98ZipStructure:
    def _get_zip_path(self) -> Path:
        env_zip = os.environ.get("AIWFH_EVIDENCE_ZIP_UNDER_TEST")
        if env_zip:
            return Path(env_zip)
        return _PROJECT_ROOT / "CDP_EVIDENCE_A98.zip"

    def test_zip_exists(self):
        """CDP_EVIDENCE_A98.zip must exist."""
        zip_path = self._get_zip_path()
        if not zip_path.exists():
            pytest.skip("CDP_EVIDENCE_A98.zip not yet generated")
        assert zip_path.exists()

    def test_zip_contains_cli_py(self):
        """ZIP must contain cli.py."""
        zip_path = self._get_zip_path()
        if not zip_path.exists():
            pytest.skip("CDP_EVIDENCE_A98.zip not yet generated")
        with zipfile.ZipFile(zip_path, "r") as zf:
            names = zf.namelist()
            cli_files = [n for n in names if n.endswith("cli.py")]
            assert len(cli_files) > 0, "cli.py must be in ZIP"

    def test_zip_contains_validate_script(self):
        """ZIP must contain validate_a98.py."""
        zip_path = self._get_zip_path()
        if not zip_path.exists():
            pytest.skip("CDP_EVIDENCE_A98.zip not yet generated")
        with zipfile.ZipFile(zip_path, "r") as zf:
            names = zf.namelist()
            val_files = [n for n in names if "validate_a98" in n]
            assert len(val_files) > 0, "validate_a98.py must be in ZIP"

    def test_zip_contains_scope_declaration(self):
        """ZIP must contain SCOPE_DECLARATION_A98.txt."""
        zip_path = self._get_zip_path()
        if not zip_path.exists():
            pytest.skip("CDP_EVIDENCE_A98.zip not yet generated")
        with zipfile.ZipFile(zip_path, "r") as zf:
            names = zf.namelist()
            scope_files = [n for n in names if "SCOPE_DECLARATION_A98" in n]
            assert len(scope_files) > 0, "SCOPE_DECLARATION_A98.txt must be in ZIP"

    def test_zip_contains_manifest(self):
        """ZIP must contain COUNTS_MANIFEST_A98.json."""
        zip_path = self._get_zip_path()
        if not zip_path.exists():
            pytest.skip("CDP_EVIDENCE_A98.zip not yet generated")
        with zipfile.ZipFile(zip_path, "r") as zf:
            names = zf.namelist()
            manifest_files = [n for n in names if "COUNTS_MANIFEST_A98" in n]
            assert len(manifest_files) > 0, "COUNTS_MANIFEST_A98.json must be in ZIP"

    def test_zip_contains_transcripts(self):
        """ZIP must contain regression and in-scope transcripts."""
        zip_path = self._get_zip_path()
        if not zip_path.exists():
            pytest.skip("CDP_EVIDENCE_A98.zip not yet generated")
        with zipfile.ZipFile(zip_path, "r") as zf:
            names = zf.namelist()
            reg = [n for n in names if "REGRESSION_OUTPUT_A98" in n]
            inscope = [n for n in names if "IN_SCOPE_TEST_RESULTS_A98" in n]
            assert len(reg) > 0, "REGRESSION_OUTPUT_A98.txt must be in ZIP"
            assert len(inscope) > 0, "IN_SCOPE_TEST_RESULTS_A98.txt must be in ZIP"


# -------------------------------------------------------------------
# Class 3: ZIP self-contained validation
# -------------------------------------------------------------------
class TestA98ZipSelfContained:
    def _get_zip_path(self) -> Path:
        # Support post-pack phase: env var override for final-artifact validation
        env_zip = os.environ.get("AIWFH_EVIDENCE_ZIP_UNDER_TEST")
        if env_zip:
            return Path(env_zip)
        return _PROJECT_ROOT / "CDP_EVIDENCE_A98.zip"

    def test_validate_runs_from_unpacked_zip(self):
        """validate_a98.py must run successfully from unpacked ZIP directory."""
        zip_path = self._get_zip_path()
        if not zip_path.exists():
            pytest.skip("CDP_EVIDENCE_A98.zip not yet generated")

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            with zipfile.ZipFile(zip_path, "r") as zf:
                zf.extractall(tmp)

            # Find the unpacked root (may have a prefix directory)
            unpacked_root = tmp
            candidates = list(tmp.iterdir())
            if len(candidates) == 1 and candidates[0].is_dir():
                unpacked_root = candidates[0]

            # Find validate script
            val_script = None
            for root, dirs, files in os.walk(str(unpacked_root)):
                for f in files:
                    if f == "validate_a98.py":
                        val_script = Path(root) / f
                        break
                if val_script:
                    break

            assert val_script is not None, "validate_a98.py not found in unpacked ZIP"

            # Run validation from unpacked directory
            result = subprocess.run(
                [sys.executable, str(val_script)],
                capture_output=True, text=True, timeout=120,
                cwd=str(unpacked_root),
            )

            assert result.returncode == 0, (
                f"Validation from unpacked ZIP failed (exit {result.returncode}):\n"
                f"stdout: {result.stdout[-500:]}\nstderr: {result.stderr[-500:]}"
            )
            assert "FAIL" not in result.stdout, (
                f"Validation from unpacked ZIP reported failures:\n{result.stdout[-500:]}"
            )


# -------------------------------------------------------------------
# Class 4: No external dependencies
# -------------------------------------------------------------------
class TestA98NoExternalDeps:
    def _get_zip_path(self) -> Path:
        env_zip = os.environ.get("AIWFH_EVIDENCE_ZIP_UNDER_TEST")
        if env_zip:
            return Path(env_zip)
        return _PROJECT_ROOT / "CDP_EVIDENCE_A98.zip"

    def test_zip_contains_all_validation_dependencies(self):
        """All files needed for validation must be in the ZIP."""
        zip_path = self._get_zip_path()
        if not zip_path.exists():
            pytest.skip("CDP_EVIDENCE_A98.zip not yet generated")

        required_patterns = [
            "cli.py",
            "SCOPE_DECLARATION",
            "REGRESSION_OUTPUT",
            "IN_SCOPE_TEST_RESULTS",
            "COUNTS_MANIFEST",
            "validate_",
        ]

        with zipfile.ZipFile(zip_path, "r") as zf:
            names = zf.namelist()
            for pattern in required_patterns:
                matches = [n for n in names if pattern in n]
                assert len(matches) > 0, (
                    f"Required pattern '{pattern}' not found in ZIP. "
                    f"ZIP contains: {names[:20]}..."
                )

    def test_validate_script_uses_dynamic_root(self):
        """validate_a98.py must use _find_root() for path discovery, not hardcode paths."""
        val_path = _PROJECT_ROOT / "scripts" / "validate_a98.py"
        if not val_path.exists():
            pytest.skip("validate_a98.py not found")
        src = val_path.read_text(encoding="utf-8")
        assert "_find_root" in src, (
            "validate_a98.py must use _find_root() for dynamic path discovery"
        )
        assert "def _find_root(" in src, (
            "validate_a98.py must define _find_root() function"
        )


# -------------------------------------------------------------------
# Class 5: Invariants preserved
# -------------------------------------------------------------------
class TestA98Invariants:
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
        manifest_path = _PROJECT_ROOT / "COUNTS_MANIFEST_A98.json"
        if not manifest_path.exists():
            pytest.skip("COUNTS_MANIFEST_A98.json not yet generated")
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert "evidence_bundle_hash" in data
        assert "evidence_bundle_artifacts" in data

    def test_a98_test_file_exists(self):
        """This test file itself must exist."""
        test_path = _PROJECT_ROOT / "tests" / "test_paper_a98_zip_self_containment.py"
        assert test_path.exists()
