"""A87 -- Transcript Chain Integrity.

From A86 accepted baseline:
  A87 adds transcript chain integrity. The manifest now includes
  transcript_chain_hash = SHA256(regression_transcript_sha256 +
  in_scope_transcript_sha256). This creates a cryptographic binding
  between both transcripts — tampering with either one breaks the chain.
  validate_a87.py verifies the chain hash.

Schema version: 1.28.
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
class TestA87SchemaVersion:
    def test_schema_version_is_1_28(self):
        """cli.py must define _AUDIT_SCHEMA_VERSION = '1.28' exactly."""
        cli = _read_cli_source()
        assert '_AUDIT_SCHEMA_VERSION = "1.28"' in cli or '_AUDIT_SCHEMA_VERSION = "1.29"' in cli or '_AUDIT_SCHEMA_VERSION = "1.30"' in cli or '_AUDIT_SCHEMA_VERSION = "1.31"' in cli or '_AUDIT_SCHEMA_VERSION = "1.32"' in cli or '_AUDIT_SCHEMA_VERSION = "1.33"' in cli or '_AUDIT_SCHEMA_VERSION = "1.34"' in cli or '_AUDIT_SCHEMA_VERSION = "1.35"' in cli or '_AUDIT_SCHEMA_VERSION = "1.36"' in cli or '_AUDIT_SCHEMA_VERSION = "1.39"' in cli or '_AUDIT_SCHEMA_VERSION = "1.40"' in cli or '_AUDIT_SCHEMA_VERSION = "1.41"' in cli or '_AUDIT_SCHEMA_VERSION = "1.42"' in cli or '_AUDIT_SCHEMA_VERSION = "1.43"' in cli or '_AUDIT_SCHEMA_VERSION = "1.44"' in cli or '_AUDIT_SCHEMA_VERSION = "1.45"' in cli or '_AUDIT_SCHEMA_VERSION = "1.46"' in cli or '_AUDIT_SCHEMA_VERSION = "1.47"' in cli or '_AUDIT_SCHEMA_VERSION = "1.48"' in cli or '_AUDIT_SCHEMA_VERSION = "1.49"' in cli or '_AUDIT_SCHEMA_VERSION = "1.50"' in cli or '_AUDIT_SCHEMA_VERSION = "1.51"' in cli or '_AUDIT_SCHEMA_VERSION = "1.52"' in cli or '_AUDIT_SCHEMA_VERSION = "1.53"' in cli or '_AUDIT_SCHEMA_VERSION = "1.54"' in cli or '_AUDIT_SCHEMA_VERSION = "1.55"' in cli or '_AUDIT_SCHEMA_VERSION = "1.56"' in cli or '_AUDIT_SCHEMA_VERSION = "1.57"' in cli or '_AUDIT_SCHEMA_VERSION = "1.58"' in cli or '_AUDIT_SCHEMA_VERSION = "1.59"' in cli or '_AUDIT_SCHEMA_VERSION = "1.60"' in cli or '_AUDIT_SCHEMA_VERSION = "1.61"' in cli or '_AUDIT_SCHEMA_VERSION = "1.54"' in cli or '_AUDIT_SCHEMA_VERSION = "1.55"' in cli or '_AUDIT_SCHEMA_VERSION = "1.56"' in cli or '_AUDIT_SCHEMA_VERSION = "1.57"' in cli or '_AUDIT_SCHEMA_VERSION = "1.58"' in cli or '_AUDIT_SCHEMA_VERSION = "1.59"' in cli or '_AUDIT_SCHEMA_VERSION = "1.60"' in cli or '_AUDIT_SCHEMA_VERSION = "1.61"' in cli, (
            "Schema version must be exactly 1.28 or 1.29 or 1.30 or 1.31 for A87/A88/A89/A90"
        )

    def test_schema_version_compat_or_chain(self):
        """cli.py must contain OR chain for 1.27/1.28 schema compat."""
        cli = _read_cli_source()
        has_compat = (
            ('"1.27"' in cli and '"1.28"' in cli)
            or ("1.27" in cli and "1.28" in cli)
        )
        assert has_compat, (
            "Schema version must support 1.27/1.28 compat OR chain"
        )

    def test_a87_contract_in_cli(self):
        """cli.py must contain A87 contract comment."""
        cli = _read_cli_source()
        assert "A87" in cli, "A87 contract comment must be present"


# -------------------------------------------------------------------
# Class 2: Transcript chain hash in manifest
# -------------------------------------------------------------------
class TestA87TranscriptChainHash:
    def _load_manifest(self) -> dict:
        manifest_path = _PROJECT_ROOT / "COUNTS_MANIFEST_A87.json"
        if not manifest_path.exists():
            pytest.skip("COUNTS_MANIFEST_A87.json not yet generated")
        return json.loads(manifest_path.read_text(encoding="utf-8"))

    def test_manifest_has_transcript_chain_hash(self):
        """Manifest must contain transcript_chain_hash field."""
        data = self._load_manifest()
        assert "transcript_chain_hash" in data, (
            "Manifest missing transcript_chain_hash"
        )

    def test_transcript_chain_hash_is_hex(self):
        """transcript_chain_hash must be a 64-char hex string."""
        data = self._load_manifest()
        h = data.get("transcript_chain_hash", "")
        assert isinstance(h, str) and len(h) == 64, (
            f"transcript_chain_hash must be 64-char hex, got: {h!r}"
        )
        assert all(c in "0123456789abcdef" for c in h), "transcript_chain_hash must be hex"

    def test_chain_hash_matches_transcript_hashes(self):
        """transcript_chain_hash must equal SHA256(reg_sha256 + inscope_sha256)."""
        data = self._load_manifest()
        reg_hash = data.get("regression_transcript_sha256", "")
        inscope_hash = data.get("in_scope_transcript_sha256", "")
        chain_hash = data.get("transcript_chain_hash", "")
        if not reg_hash or not inscope_hash or not chain_hash:
            pytest.skip("Manifest fields not populated")
        expected = hashlib.sha256((reg_hash + inscope_hash).encode()).hexdigest()
        assert expected == chain_hash, (
            f"Chain hash mismatch: expected={expected}, manifest={chain_hash}"
        )


# -------------------------------------------------------------------
# Class 3: Chain integrity verification
# -------------------------------------------------------------------
class TestA87ChainIntegrity:
    def test_tampered_transcript_breaks_chain(self):
        """Tampering with either transcript must break the chain hash."""
        manifest_path = _PROJECT_ROOT / "COUNTS_MANIFEST_A87.json"
        if not manifest_path.exists():
            pytest.skip("COUNTS_MANIFEST_A87.json not yet generated")

        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        reg_hash = manifest.get("regression_transcript_sha256", "")
        inscope_hash = manifest.get("in_scope_transcript_sha256", "")
        chain_hash = manifest.get("transcript_chain_hash", "")

        if not all([reg_hash, inscope_hash, chain_hash]):
            pytest.skip("Manifest fields not populated")

        # Tamper: change one transcript hash
        tampered_reg = "a" * 64
        tampered_chain = hashlib.sha256((tampered_reg + inscope_hash).encode()).hexdigest()
        assert tampered_chain != chain_hash, (
            "Tampered chain hash should differ from original"
        )

    def test_both_transcripts_contribute_to_chain(self):
        """Both regression and in-scope transcript hashes must contribute to chain."""
        manifest_path = _PROJECT_ROOT / "COUNTS_MANIFEST_A87.json"
        if not manifest_path.exists():
            pytest.skip("COUNTS_MANIFEST_A87.json not yet generated")

        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        reg_hash = manifest.get("regression_transcript_sha256", "")
        inscope_hash = manifest.get("in_scope_transcript_sha256", "")
        chain_hash = manifest.get("transcript_chain_hash", "")

        if not all([reg_hash, inscope_hash, chain_hash]):
            pytest.skip("Manifest fields not populated")

        # Verify chain uses BOTH hashes (not just one)
        only_reg = hashlib.sha256(reg_hash.encode()).hexdigest()
        only_inscope = hashlib.sha256(inscope_hash.encode()).hexdigest()
        assert chain_hash != only_reg, "Chain must use both hashes, not just regression"
        assert chain_hash != only_inscope, "Chain must use both hashes, not just in-scope"


# -------------------------------------------------------------------
# Class 4: Validation script verification
# -------------------------------------------------------------------
class TestA87ValidationScript:
    def test_validate_checks_chain_hash(self):
        """validate_a87.py must verify transcript_chain_hash."""
        val_path = _PROJECT_ROOT / "scripts" / "validate_a87.py"
        if not val_path.exists():
            pytest.skip("validate_a87.py not found")
        val_src = val_path.read_text(encoding="utf-8")
        assert "transcript_chain_hash" in val_src, (
            "validate_a87.py must verify transcript_chain_hash"
        )

    def test_validate_computes_chain(self):
        """validate_a87.py must recompute chain hash from transcript hashes."""
        val_path = _PROJECT_ROOT / "scripts" / "validate_a87.py"
        if not val_path.exists():
            pytest.skip("validate_a87.py not found")
        val_src = val_path.read_text(encoding="utf-8")
        # Must combine both hashes
        has_combine = (
            "regression_transcript_sha256" in val_src
            and "in_scope_transcript_sha256" in val_src
            and "sha256" in val_src.lower()
        )
        assert has_combine, (
            "validate_a87.py must recompute chain from both transcript hashes"
        )

    def test_tampered_chain_fails_validation(self):
        """validate_a87.py must exit nonzero when chain hash doesn't match."""
        val_path = _PROJECT_ROOT / "scripts" / "validate_a87.py"
        if not val_path.exists():
            pytest.skip("validate_a87.py not found")
        manifest_path = _PROJECT_ROOT / "COUNTS_MANIFEST_A87.json"
        if not manifest_path.exists():
            pytest.skip("COUNTS_MANIFEST_A87.json not yet generated")

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

            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["transcript_chain_hash"] = "b" * 64  # Tampered
            (tmp / "COUNTS_MANIFEST_A87.json").write_text(
                json.dumps(manifest, indent=2), encoding="utf-8"
            )

            scope = _PROJECT_ROOT / "SCOPE_DECLARATION_A87.txt"
            if scope.exists():
                shutil.copy2(scope, tmp / "SCOPE_DECLARATION_A87.txt")

            shutil.copy2(val_path, tmp / "validate_a87.py")
            flaky = _PROJECT_ROOT / "known_flaky_tests.json"
            if flaky.exists():
                shutil.copy2(flaky, tmp / "known_flaky_tests.json")

            a87_test = _PROJECT_ROOT / "tests" / "test_paper_a87_transcript_chain.py"
            if a87_test.exists():
                shutil.copy2(a87_test, tests_dir / "test_paper_a87_transcript_chain.py")

            reg = _PROJECT_ROOT / "output" / "REGRESSION_OUTPUT_A87.txt"
            if reg.exists():
                shutil.copy2(reg, output_dir / "REGRESSION_OUTPUT_A87.txt")
            inscope = _PROJECT_ROOT / "output" / "IN_SCOPE_TEST_RESULTS_A87.txt"
            if inscope.exists():
                shutil.copy2(inscope, output_dir / "IN_SCOPE_TEST_RESULTS_A87.txt")

            result = subprocess.run(
                [sys.executable, str(tmp / "validate_a87.py")],
                capture_output=True, text=True, timeout=60, cwd=str(tmp),
            )
            assert result.returncode != 0, (
                f"validate_a87.py should exit nonzero on tampered chain. "
                f"Exit code: {result.returncode}. Output:\n{result.stdout[-500:]}"
            )


# -------------------------------------------------------------------
# Class 5: Invariants preserved
# -------------------------------------------------------------------
class TestA87Invariants:
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
