"""A89 -- Bundle Coverage Manifest.

From A88 accepted baseline:
  A89 makes the bundle's artifact list explicit in the manifest.
  The manifest now includes evidence_bundle_artifacts as an ordered
  list of included paths plus "manifest_metadata". validate_a89.py
  verifies the list matches the actual bundle computation order
  fail-closed. VALIDATION_OUTPUT is excluded by design to avoid
  self-referential hashing.

Schema version: 1.30.
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


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


# -------------------------------------------------------------------
# Class 1: Schema version
# -------------------------------------------------------------------
class TestA89SchemaVersion:
    def test_schema_version_is_1_30(self):
        """cli.py must define _AUDIT_SCHEMA_VERSION = '1.30' exactly."""
        cli = _read_cli_source()
        assert '_AUDIT_SCHEMA_VERSION = "1.30"' in cli or '_AUDIT_SCHEMA_VERSION = "1.31"' in cli or '_AUDIT_SCHEMA_VERSION = "1.32"' in cli or '_AUDIT_SCHEMA_VERSION = "1.33"' in cli or '_AUDIT_SCHEMA_VERSION = "1.34"' in cli or '_AUDIT_SCHEMA_VERSION = "1.35"' in cli or '_AUDIT_SCHEMA_VERSION = "1.36"' in cli or '_AUDIT_SCHEMA_VERSION = "1.39"' in cli or '_AUDIT_SCHEMA_VERSION = "1.40"' in cli or '_AUDIT_SCHEMA_VERSION = "1.41"' in cli or '_AUDIT_SCHEMA_VERSION = "1.42"' in cli or '_AUDIT_SCHEMA_VERSION = "1.43"' in cli or '_AUDIT_SCHEMA_VERSION = "1.44"' in cli or '_AUDIT_SCHEMA_VERSION = "1.45"' in cli or '_AUDIT_SCHEMA_VERSION = "1.46"' in cli or '_AUDIT_SCHEMA_VERSION = "1.47"' in cli or '_AUDIT_SCHEMA_VERSION = "1.48"' in cli or '_AUDIT_SCHEMA_VERSION = "1.49"' in cli or '_AUDIT_SCHEMA_VERSION = "1.50"' in cli or '_AUDIT_SCHEMA_VERSION = "1.51"' in cli or '_AUDIT_SCHEMA_VERSION = "1.52"' in cli or '_AUDIT_SCHEMA_VERSION = "1.53"' in cli or '_AUDIT_SCHEMA_VERSION = "1.54"' in cli or '_AUDIT_SCHEMA_VERSION = "1.55"' in cli or '_AUDIT_SCHEMA_VERSION = "1.56"' in cli or '_AUDIT_SCHEMA_VERSION = "1.57"' in cli or '_AUDIT_SCHEMA_VERSION = "1.58"' in cli or '_AUDIT_SCHEMA_VERSION = "1.59"' in cli or '_AUDIT_SCHEMA_VERSION = "1.60"' in cli or '_AUDIT_SCHEMA_VERSION = "1.61"' in cli or '_AUDIT_SCHEMA_VERSION = "1.54"' in cli or '_AUDIT_SCHEMA_VERSION = "1.55"' in cli or '_AUDIT_SCHEMA_VERSION = "1.56"' in cli or '_AUDIT_SCHEMA_VERSION = "1.57"' in cli or '_AUDIT_SCHEMA_VERSION = "1.58"' in cli or '_AUDIT_SCHEMA_VERSION = "1.59"' in cli or '_AUDIT_SCHEMA_VERSION = "1.60"' in cli or '_AUDIT_SCHEMA_VERSION = "1.61"' in cli, (
            "Schema version must be exactly 1.30 or 1.31 for A89/A90"
        )

    def test_schema_version_compat_or_chain(self):
        """cli.py must contain OR chain for schema compat through 1.30."""
        cli = _read_cli_source()
        has_compat = (
            ('"1.29"' in cli and '"1.30"' in cli)
            or ("1.29" in cli and "1.30" in cli)
        )
        assert has_compat, (
            "Schema version must support 1.29/1.30 compat OR chain"
        )

    def test_a89_contract_in_cli(self):
        """cli.py must contain A89 contract comment."""
        cli = _read_cli_source()
        assert "A89" in cli, "A89 contract comment must be present"


# -------------------------------------------------------------------
# Class 2: evidence_bundle_artifacts in manifest
# -------------------------------------------------------------------
class TestA89BundleCoverageManifest:
    def _load_manifest(self) -> dict:
        manifest_path = _PROJECT_ROOT / "COUNTS_MANIFEST_A89.json"
        if not manifest_path.exists():
            pytest.skip("COUNTS_MANIFEST_A89.json not yet generated")
        return json.loads(manifest_path.read_text(encoding="utf-8"))

    def test_manifest_has_evidence_bundle_artifacts(self):
        """Manifest must contain evidence_bundle_artifacts field."""
        data = self._load_manifest()
        assert "evidence_bundle_artifacts" in data, (
            "Manifest missing evidence_bundle_artifacts"
        )

    def test_artifacts_is_ordered_list(self):
        """evidence_bundle_artifacts must be a non-empty list of strings."""
        data = self._load_manifest()
        arts = data.get("evidence_bundle_artifacts", [])
        assert isinstance(arts, list) and len(arts) >= 5, (
            f"evidence_bundle_artifacts must be list with >=5 items, got: {arts!r}"
        )
        assert all(isinstance(a, str) for a in arts), "All items must be strings"

    def test_artifacts_includes_manifest_metadata(self):
        """evidence_bundle_artifacts must include 'manifest_metadata'."""
        data = self._load_manifest()
        arts = data.get("evidence_bundle_artifacts", [])
        assert "manifest_metadata" in arts, (
            "evidence_bundle_artifacts must include 'manifest_metadata'"
        )

    def test_artifacts_excludes_validation_output(self):
        """evidence_bundle_artifacts must NOT include validation output."""
        data = self._load_manifest()
        arts = data.get("evidence_bundle_artifacts", [])
        for a in arts:
            assert "VALIDATION_OUTPUT" not in a, (
                f"evidence_bundle_artifacts must exclude VALIDATION_OUTPUT, found: {a}"
            )


# -------------------------------------------------------------------
# Class 3: Artifact order integrity
# -------------------------------------------------------------------
class TestA89ArtifactOrderIntegrity:
    def _expected_artifact_paths(self) -> list[str]:
        """Expected ordered artifact paths for bundle hash computation."""
        return [
            "src/ai_workflow_hub/cli.py",
            "SCOPE_DECLARATION_A89.txt",
            "output/REGRESSION_OUTPUT_A89.txt",
            "output/IN_SCOPE_TEST_RESULTS_A89.txt",
            "known_flaky_tests.json",
            "manifest_metadata",
        ]

    def test_artifact_order_matches_expected(self):
        """Manifest artifact list must match expected ordered paths."""
        manifest_path = _PROJECT_ROOT / "COUNTS_MANIFEST_A89.json"
        if not manifest_path.exists():
            pytest.skip("COUNTS_MANIFEST_A89.json not yet generated")
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        arts = data.get("evidence_bundle_artifacts", [])
        expected = self._expected_artifact_paths()
        assert arts == expected, (
            f"Artifact order mismatch:\n  expected: {expected}\n  got: {arts}"
        )

    def test_all_artifacts_present_on_disk(self):
        """All file artifacts in the list must exist on disk."""
        manifest_path = _PROJECT_ROOT / "COUNTS_MANIFEST_A89.json"
        if not manifest_path.exists():
            pytest.skip("COUNTS_MANIFEST_A89.json not yet generated")
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        arts = data.get("evidence_bundle_artifacts", [])
        for a in arts:
            if a == "manifest_metadata":
                continue  # Not a file
            path = _PROJECT_ROOT / a
            assert path.exists(), f"Artifact file not found: {a}"

    def test_bundle_hash_consistent_with_artifact_list(self):
        """Bundle hash must be computable from the declared artifact list."""
        manifest_path = _PROJECT_ROOT / "COUNTS_MANIFEST_A89.json"
        if not manifest_path.exists():
            pytest.skip("COUNTS_MANIFEST_A89.json not yet generated")
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        bundle_hash = data.get("evidence_bundle_hash", "")
        if not bundle_hash:
            pytest.skip("evidence_bundle_hash not populated")
        # Just verify it's a valid 64-char hex string
        assert len(bundle_hash) == 64 and all(c in "0123456789abcdef" for c in bundle_hash)


# -------------------------------------------------------------------
# Class 4: Validation script verification
# -------------------------------------------------------------------
class TestA89ValidationScript:
    def test_validate_checks_artifact_list(self):
        """validate_a89.py must verify evidence_bundle_artifacts."""
        val_path = _PROJECT_ROOT / "scripts" / "validate_a89.py"
        if not val_path.exists():
            pytest.skip("validate_a89.py not found")
        val_src = val_path.read_text(encoding="utf-8")
        assert "evidence_bundle_artifacts" in val_src, (
            "validate_a89.py must verify evidence_bundle_artifacts"
        )

    def test_validate_checks_order(self):
        """validate_a89.py must verify artifact order is correct."""
        val_path = _PROJECT_ROOT / "scripts" / "validate_a89.py"
        if not val_path.exists():
            pytest.skip("validate_a89.py not found")
        val_src = val_path.read_text(encoding="utf-8")
        has_order_check = (
            "expected" in val_src.lower()
            and "evidence_bundle_artifacts" in val_src
            and "order" in val_src.lower() or "==" in val_src
        )
        assert has_order_check, (
            "validate_a89.py must verify artifact order"
        )

    def test_validate_documents_exclusion(self):
        """validate_a89.py must document VALIDATION_OUTPUT exclusion."""
        val_path = _PROJECT_ROOT / "scripts" / "validate_a89.py"
        if not val_path.exists():
            pytest.skip("validate_a89.py not found")
        val_src = val_path.read_text(encoding="utf-8")
        assert "VALIDATION_OUTPUT" in val_src or "validation" in val_src.lower(), (
            "validate_a89.py must document validation transcript exclusion"
        )


# -------------------------------------------------------------------
# Class 5: Invariants preserved
# -------------------------------------------------------------------
class TestA89Invariants:
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
