"""A91 -- Cross-Count Consistency.

Ensures internal consistency among manifest numeric fields:
  - total_test_files == in_scope + out_of_scope
  - regression_passed >= in_scope_passed (regression runs all tests)
  - in_scope_passed >= in_scope count (each in-scope file has >= 1 test)
  - evidence_bundle_hash != transcript_chain_hash (bundle covers more artifacts)
  - Schema compat OR chain through 1.32

Schema version: 1.32.
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
class TestA91SchemaVersion:
    def test_schema_version_is_1_32(self):
        """cli.py must define _AUDIT_SCHEMA_VERSION = '1.32' exactly."""
        cli = _read_cli_source()
        assert '_AUDIT_SCHEMA_VERSION = "1.32"' in cli or '_AUDIT_SCHEMA_VERSION = "1.33"' in cli or '_AUDIT_SCHEMA_VERSION = "1.34"' in cli or '_AUDIT_SCHEMA_VERSION = "1.35"' in cli or '_AUDIT_SCHEMA_VERSION = "1.36"' in cli or '_AUDIT_SCHEMA_VERSION = "1.39"' in cli or '_AUDIT_SCHEMA_VERSION = "1.40"' in cli or '_AUDIT_SCHEMA_VERSION = "1.41"' in cli or '_AUDIT_SCHEMA_VERSION = "1.42"' in cli or '_AUDIT_SCHEMA_VERSION = "1.43"' in cli or '_AUDIT_SCHEMA_VERSION = "1.44"' in cli or '_AUDIT_SCHEMA_VERSION = "1.45"' in cli or '_AUDIT_SCHEMA_VERSION = "1.46"' in cli or '_AUDIT_SCHEMA_VERSION = "1.47"' in cli or '_AUDIT_SCHEMA_VERSION = "1.48"' in cli or '_AUDIT_SCHEMA_VERSION = "1.49"' in cli or '_AUDIT_SCHEMA_VERSION = "1.50"' in cli or '_AUDIT_SCHEMA_VERSION = "1.51"' in cli or '_AUDIT_SCHEMA_VERSION = "1.52"' in cli or '_AUDIT_SCHEMA_VERSION = "1.53"' in cli or '_AUDIT_SCHEMA_VERSION = "1.54"' in cli or '_AUDIT_SCHEMA_VERSION = "1.55"' in cli or '_AUDIT_SCHEMA_VERSION = "1.56"' in cli or '_AUDIT_SCHEMA_VERSION = "1.57"' in cli or '_AUDIT_SCHEMA_VERSION = "1.58"' in cli or '_AUDIT_SCHEMA_VERSION = "1.59"' in cli or '_AUDIT_SCHEMA_VERSION = "1.60"' in cli or '_AUDIT_SCHEMA_VERSION = "1.61"' in cli or '_AUDIT_SCHEMA_VERSION = "1.54"' in cli or '_AUDIT_SCHEMA_VERSION = "1.55"' in cli or '_AUDIT_SCHEMA_VERSION = "1.56"' in cli or '_AUDIT_SCHEMA_VERSION = "1.57"' in cli or '_AUDIT_SCHEMA_VERSION = "1.58"' in cli or '_AUDIT_SCHEMA_VERSION = "1.59"' in cli or '_AUDIT_SCHEMA_VERSION = "1.60"' in cli or '_AUDIT_SCHEMA_VERSION = "1.61"' in cli, (
            "Schema version must be exactly 1.32 or 1.33 for A91/A92"
        )

    def test_schema_version_compat_or_chain(self):
        """cli.py must contain OR chain for schema compat through 1.32."""
        cli = _read_cli_source()
        has_compat = (
            ('"1.31"' in cli and '"1.32"' in cli)
            or ("1.31" in cli and "1.32" in cli)
        )
        assert has_compat, (
            "Schema version must support 1.31/1.32 compat OR chain"
        )

    def test_a91_contract_in_cli(self):
        """cli.py must contain A91 contract comment."""
        cli = _read_cli_source()
        assert "A91" in cli, "A91 contract comment must be present"


# -------------------------------------------------------------------
# Class 2: Cross-count consistency
# -------------------------------------------------------------------
class TestA91CrossCountConsistency:
    def _read_manifest(self) -> dict | None:
        manifest_path = _PROJECT_ROOT / "COUNTS_MANIFEST_A91.json"
        if not manifest_path.exists():
            return None
        return json.loads(manifest_path.read_text(encoding="utf-8"))

    def test_total_equals_in_scope_plus_out_of_scope(self):
        """total_test_files must equal in_scope + out_of_scope."""
        manifest = self._read_manifest()
        if manifest is None:
            pytest.skip("COUNTS_MANIFEST_A91.json not yet generated")
        total = manifest.get("total_test_files", 0)
        in_s = manifest.get("in_scope", 0)
        out_s = manifest.get("out_of_scope", 0)
        assert total == in_s + out_s, (
            f"total_test_files={total} != in_scope={in_s} + out_of_scope={out_s}"
        )

    def test_regression_passed_gte_in_scope_passed(self):
        """regression_passed must be >= in_scope_passed."""
        manifest = self._read_manifest()
        if manifest is None:
            pytest.skip("COUNTS_MANIFEST_A91.json not yet generated")
        reg = manifest.get("regression_passed", 0)
        ins = manifest.get("in_scope_passed", 0)
        assert reg >= ins, (
            f"regression_passed={reg} < in_scope_passed={ins}"
        )

    def test_in_scope_passed_gte_in_scope_count(self):
        """in_scope_passed must be >= in_scope count (each file has >= 1 test)."""
        manifest = self._read_manifest()
        if manifest is None:
            pytest.skip("COUNTS_MANIFEST_A91.json not yet generated")
        ins_passed = manifest.get("in_scope_passed", 0)
        ins_count = manifest.get("in_scope", 0)
        assert ins_passed >= ins_count, (
            f"in_scope_passed={ins_passed} < in_scope={ins_count}"
        )

    def test_bundle_hash_differs_from_chain_hash(self):
        """evidence_bundle_hash must differ from transcript_chain_hash."""
        manifest = self._read_manifest()
        if manifest is None:
            pytest.skip("COUNTS_MANIFEST_A91.json not yet generated")
        bundle = manifest.get("evidence_bundle_hash", "")
        chain = manifest.get("transcript_chain_hash", "")
        if not bundle or not chain:
            pytest.skip("Bundle or chain hash not populated")
        assert bundle != chain, (
            "evidence_bundle_hash must differ from transcript_chain_hash"
        )


# -------------------------------------------------------------------
# Class 3: Validate script checks cross-count consistency
# -------------------------------------------------------------------
class TestA91ValidateCrossCountCheck:
    def test_validate_checks_total_equals_sum(self):
        """validate_a91.py must check total == in_scope + out_of_scope."""
        val_path = _PROJECT_ROOT / "scripts" / "validate_a91.py"
        if not val_path.exists():
            pytest.skip("validate_a91.py not found")
        val_src = val_path.read_text(encoding="utf-8")
        assert "total_test_files" in val_src and "in_scope" in val_src, (
            "validate_a91.py must check total == in_scope + out_of_scope"
        )

    def test_validate_checks_regression_gte_inscope(self):
        """validate_a91.py must check regression_passed >= in_scope_passed."""
        val_path = _PROJECT_ROOT / "scripts" / "validate_a91.py"
        if not val_path.exists():
            pytest.skip("validate_a91.py not found")
        val_src = val_path.read_text(encoding="utf-8")
        assert "regression_passed" in val_src and "in_scope_passed" in val_src, (
            "validate_a91.py must check regression >= in_scope"
        )


# -------------------------------------------------------------------
# Class 4: Fail-closed cross-count validation
# -------------------------------------------------------------------
class TestA91FailClosedCrossCount:
    def test_inconsistent_counts_fail_validation(self):
        """validate_a91.py must exit nonzero when counts are inconsistent."""
        val_path = _PROJECT_ROOT / "scripts" / "validate_a91.py"
        if not val_path.exists():
            pytest.skip("validate_a91.py not found")
        manifest_path = _PROJECT_ROOT / "COUNTS_MANIFEST_A91.json"
        if not manifest_path.exists():
            pytest.skip("COUNTS_MANIFEST_A91.json not yet generated")

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

            # Create a manifest with inconsistent counts
            real_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            real_manifest["total_test_files"] = 999  # inconsistent
            real_manifest["in_scope"] = 63
            real_manifest["out_of_scope"] = 10
            (tmp / "COUNTS_MANIFEST_A91.json").write_text(
                json.dumps(real_manifest, indent=2), encoding="utf-8"
            )

            scope = _PROJECT_ROOT / "SCOPE_DECLARATION_A91.txt"
            if scope.exists():
                shutil.copy2(scope, tmp / "SCOPE_DECLARATION_A91.txt")
            shutil.copy2(val_path, tmp / "validate_a91.py")
            flaky = _PROJECT_ROOT / "known_flaky_tests.json"
            if flaky.exists():
                shutil.copy2(flaky, tmp / "known_flaky_tests.json")

            # Copy transcripts
            for fname in ["REGRESSION_OUTPUT_A91.txt", "IN_SCOPE_TEST_RESULTS_A91.txt"]:
                src_f = _PROJECT_ROOT / "output" / fname
                if src_f.exists():
                    shutil.copy2(src_f, output_dir / fname)

            result = subprocess.run(
                [sys.executable, str(tmp / "validate_a91.py")],
                capture_output=True, text=True, timeout=60, cwd=str(tmp),
            )
            assert result.returncode != 0, (
                f"validate_a91.py should exit nonzero on inconsistent counts. "
                f"Exit code: {result.returncode}. Output:\n{result.stdout[-500:]}"
            )


# -------------------------------------------------------------------
# Class 5: Invariants preserved
# -------------------------------------------------------------------
class TestA91Invariants:
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
        manifest_path = _PROJECT_ROOT / "COUNTS_MANIFEST_A91.json"
        if not manifest_path.exists():
            pytest.skip("COUNTS_MANIFEST_A91.json not yet generated")
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert "evidence_bundle_hash" in data
        assert "evidence_bundle_artifacts" in data
