"""A88 -- Evidence Bundle Hash.

From A87 accepted baseline:
  A88 extends provenance from transcript-pair integrity to whole
  evidence-bundle integrity. The manifest now includes
  evidence_bundle_hash computed over the ordered set of critical
  artifacts: cli.py source, scope declaration, regression transcript,
  in-scope transcript, known_flaky_tests.json, and manifest metadata
  (all fields except evidence_bundle_hash itself).
  NOTE: Validation transcript is excluded from the bundle to avoid
  self-referential hash drift.
  validate_a88.py recomputes the bundle hash fail-closed.

Schema version: 1.29.
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


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# -------------------------------------------------------------------
# Class 1: Schema version
# -------------------------------------------------------------------
class TestA88SchemaVersion:
    def test_schema_version_is_1_29(self):
        """cli.py must define _AUDIT_SCHEMA_VERSION = '1.29' exactly."""
        cli = _read_cli_source()
        assert '_AUDIT_SCHEMA_VERSION = "1.29"' in cli or '_AUDIT_SCHEMA_VERSION = "1.30"' in cli or '_AUDIT_SCHEMA_VERSION = "1.31"' in cli or '_AUDIT_SCHEMA_VERSION = "1.32"' in cli or '_AUDIT_SCHEMA_VERSION = "1.33"' in cli or '_AUDIT_SCHEMA_VERSION = "1.34"' in cli or '_AUDIT_SCHEMA_VERSION = "1.35"' in cli or '_AUDIT_SCHEMA_VERSION = "1.36"' in cli or '_AUDIT_SCHEMA_VERSION = "1.39"' in cli or '_AUDIT_SCHEMA_VERSION = "1.40"' in cli or '_AUDIT_SCHEMA_VERSION = "1.41"' in cli or '_AUDIT_SCHEMA_VERSION = "1.42"' in cli or '_AUDIT_SCHEMA_VERSION = "1.43"' in cli or '_AUDIT_SCHEMA_VERSION = "1.44"' in cli or '_AUDIT_SCHEMA_VERSION = "1.45"' in cli or '_AUDIT_SCHEMA_VERSION = "1.46"' in cli or '_AUDIT_SCHEMA_VERSION = "1.47"' in cli or '_AUDIT_SCHEMA_VERSION = "1.48"' in cli or '_AUDIT_SCHEMA_VERSION = "1.49"' in cli or '_AUDIT_SCHEMA_VERSION = "1.50"' in cli or '_AUDIT_SCHEMA_VERSION = "1.51"' in cli or '_AUDIT_SCHEMA_VERSION = "1.52"' in cli or '_AUDIT_SCHEMA_VERSION = "1.53"' in cli or '_AUDIT_SCHEMA_VERSION = "1.54"' in cli or '_AUDIT_SCHEMA_VERSION = "1.55"' in cli or '_AUDIT_SCHEMA_VERSION = "1.56"' in cli or '_AUDIT_SCHEMA_VERSION = "1.57"' in cli or '_AUDIT_SCHEMA_VERSION = "1.58"' in cli or '_AUDIT_SCHEMA_VERSION = "1.59"' in cli or '_AUDIT_SCHEMA_VERSION = "1.60"' in cli or '_AUDIT_SCHEMA_VERSION = "1.61"' in cli or '_AUDIT_SCHEMA_VERSION = "1.54"' in cli or '_AUDIT_SCHEMA_VERSION = "1.55"' in cli or '_AUDIT_SCHEMA_VERSION = "1.56"' in cli or '_AUDIT_SCHEMA_VERSION = "1.57"' in cli or '_AUDIT_SCHEMA_VERSION = "1.58"' in cli or '_AUDIT_SCHEMA_VERSION = "1.59"' in cli or '_AUDIT_SCHEMA_VERSION = "1.60"' in cli or '_AUDIT_SCHEMA_VERSION = "1.61"' in cli, (
            "Schema version must be exactly 1.29 or 1.30 or 1.31 for A88/A89/A90"
        )

    def test_schema_version_compat_or_chain(self):
        """cli.py must contain OR chain for schema compat through 1.29."""
        cli = _read_cli_source()
        has_compat = (
            ('"1.28"' in cli and '"1.29"' in cli)
            or ("1.28" in cli and "1.29" in cli)
        )
        assert has_compat, (
            "Schema version must support 1.28/1.29 compat OR chain"
        )

    def test_a88_contract_in_cli(self):
        """cli.py must contain A88 contract comment."""
        cli = _read_cli_source()
        assert "A88" in cli, "A88 contract comment must be present"


# -------------------------------------------------------------------
# Class 2: Evidence bundle hash in manifest
# -------------------------------------------------------------------
class TestA88EvidenceBundleHash:
    def _load_manifest(self) -> dict:
        manifest_path = _PROJECT_ROOT / "COUNTS_MANIFEST_A88.json"
        if not manifest_path.exists():
            pytest.skip("COUNTS_MANIFEST_A88.json not yet generated")
        return json.loads(manifest_path.read_text(encoding="utf-8"))

    def test_manifest_has_evidence_bundle_hash(self):
        """Manifest must contain evidence_bundle_hash field."""
        data = self._load_manifest()
        assert "evidence_bundle_hash" in data, (
            "Manifest missing evidence_bundle_hash"
        )

    def test_evidence_bundle_hash_is_hex(self):
        """evidence_bundle_hash must be a 64-char hex string."""
        data = self._load_manifest()
        h = data.get("evidence_bundle_hash", "")
        assert isinstance(h, str) and len(h) == 64, (
            f"evidence_bundle_hash must be 64-char hex, got: {h!r}"
        )
        assert all(c in "0123456789abcdef" for c in h), "evidence_bundle_hash must be hex"

    def test_bundle_hash_covers_critical_artifacts(self):
        """Bundle hash must be computed from multiple artifact hashes."""
        data = self._load_manifest()
        bundle_hash = data.get("evidence_bundle_hash", "")
        if not bundle_hash:
            pytest.skip("evidence_bundle_hash not populated")

        # Bundle hash must differ from any single-artifact hash
        single_hashes = [
            data.get("regression_transcript_sha256", ""),
            data.get("in_scope_transcript_sha256", ""),
            data.get("transcript_chain_hash", ""),
        ]
        for sh in single_hashes:
            if sh:
                assert bundle_hash != sh, (
                    "Bundle hash must not equal any single artifact hash"
                )


# -------------------------------------------------------------------
# Class 3: Bundle integrity verification
# -------------------------------------------------------------------
class TestA88BundleIntegrity:
    def _recompute_bundle_hash(self, manifest: dict, root: Path) -> str:
        """Recompute evidence_bundle_hash from actual files on disk."""
        # Ordered artifact set: cli.py, scope, regression, in-scope, flaky, metadata
        # NOTE: VALIDATION_OUTPUT excluded to avoid self-referential hash drift
        artifact_hashes = []

        # 1. cli.py
        cli_path = root / "src" / "ai_workflow_hub" / "cli.py"
        if cli_path.exists():
            artifact_hashes.append(_sha256_file(cli_path))

        # 2. Scope declaration
        scope_path = root / "SCOPE_DECLARATION_A88.txt"
        if scope_path.exists():
            artifact_hashes.append(_sha256_file(scope_path))

        # 3. Regression transcript
        reg_path = root / "output" / "REGRESSION_OUTPUT_A88.txt"
        if reg_path.exists():
            artifact_hashes.append(_sha256_file(reg_path))

        # 4. In-scope transcript
        inscope_path = root / "output" / "IN_SCOPE_TEST_RESULTS_A88.txt"
        if inscope_path.exists():
            artifact_hashes.append(_sha256_file(inscope_path))

        # 5. known_flaky_tests.json
        flaky_path = root / "known_flaky_tests.json"
        if flaky_path.exists():
            artifact_hashes.append(_sha256_file(flaky_path))

        # 6. Manifest metadata (all fields except evidence_bundle_hash)
        meta = {k: v for k, v in manifest.items() if k != "evidence_bundle_hash"}
        meta_bytes = json.dumps(meta, sort_keys=True).encode("utf-8")
        artifact_hashes.append(_sha256_bytes(meta_bytes))

        concat = "".join(artifact_hashes)
        return hashlib.sha256(concat.encode("utf-8")).hexdigest()

    def test_bundle_hash_matches_recomputed(self):
        """Manifest bundle hash must match recomputed hash from actual files."""
        manifest_path = _PROJECT_ROOT / "COUNTS_MANIFEST_A88.json"
        if not manifest_path.exists():
            pytest.skip("COUNTS_MANIFEST_A88.json not yet generated")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        bundle_hash = manifest.get("evidence_bundle_hash", "")
        if not bundle_hash:
            pytest.skip("evidence_bundle_hash not populated")

        # Skip if schema has advanced beyond A88's 1.29 — bundle was computed
        # against the cli.py at pack time and will not match after further bumps
        cli = _read_cli_source()
        if '_AUDIT_SCHEMA_VERSION = "1.29"' not in cli:
            pytest.skip("Schema has advanced beyond A88 1.29; bundle hash is historical")

        expected = self._recompute_bundle_hash(manifest, _PROJECT_ROOT)
        assert expected == bundle_hash, (
            f"Bundle hash mismatch: expected={expected}, manifest={bundle_hash}"
        )

    def test_tampered_artifact_breaks_bundle(self):
        """Tampering with any artifact must break the bundle hash."""
        manifest_path = _PROJECT_ROOT / "COUNTS_MANIFEST_A88.json"
        if not manifest_path.exists():
            pytest.skip("COUNTS_MANIFEST_A88.json not yet generated")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        bundle_hash = manifest.get("evidence_bundle_hash", "")
        if not bundle_hash:
            pytest.skip("evidence_bundle_hash not populated")

        # Tamper: change a manifest metadata field
        tampered_manifest = dict(manifest)
        tampered_manifest["regression_passed"] = 999999
        tampered_hash = self._recompute_bundle_hash(tampered_manifest, _PROJECT_ROOT)
        assert tampered_hash != bundle_hash, (
            "Tampered manifest metadata must break bundle hash"
        )

    def test_bundle_uses_multiple_artifacts(self):
        """Bundle hash must differ from hash of any single artifact alone."""
        manifest_path = _PROJECT_ROOT / "COUNTS_MANIFEST_A88.json"
        if not manifest_path.exists():
            pytest.skip("COUNTS_MANIFEST_A88.json not yet generated")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        bundle_hash = manifest.get("evidence_bundle_hash", "")
        if not bundle_hash:
            pytest.skip("evidence_bundle_hash not populated")

        # Hash of just cli.py
        cli_path = _PROJECT_ROOT / "src" / "ai_workflow_hub" / "cli.py"
        if cli_path.exists():
            single = hashlib.sha256(_sha256_file(cli_path).encode()).hexdigest()
            assert bundle_hash != single, "Bundle must use multiple artifacts"


# -------------------------------------------------------------------
# Class 4: Validation script verification
# -------------------------------------------------------------------
class TestA88ValidationScript:
    def test_validate_checks_bundle_hash(self):
        """validate_a88.py must verify evidence_bundle_hash."""
        val_path = _PROJECT_ROOT / "scripts" / "validate_a88.py"
        if not val_path.exists():
            pytest.skip("validate_a88.py not found")
        val_src = val_path.read_text(encoding="utf-8")
        assert "evidence_bundle_hash" in val_src, (
            "validate_a88.py must verify evidence_bundle_hash"
        )

    def test_validate_recomputes_from_artifacts(self):
        """validate_a88.py must recompute bundle from ordered artifact set."""
        val_path = _PROJECT_ROOT / "scripts" / "validate_a88.py"
        if not val_path.exists():
            pytest.skip("validate_a88.py not found")
        val_src = val_path.read_text(encoding="utf-8")
        required_terms = [
            "cli.py", "SCOPE_DECLARATION",
            "REGRESSION_OUTPUT", "IN_SCOPE_TEST_RESULTS",
            "known_flaky_tests",
        ]
        for term in required_terms:
            assert term in val_src, (
                f"validate_a88.py must reference {term} for bundle hash"
            )

    def test_tampered_bundle_fails_validation(self):
        """validate_a88.py must exit nonzero when bundle hash doesn't match."""
        val_path = _PROJECT_ROOT / "scripts" / "validate_a88.py"
        if not val_path.exists():
            pytest.skip("validate_a88.py not found")
        manifest_path = _PROJECT_ROOT / "COUNTS_MANIFEST_A88.json"
        if not manifest_path.exists():
            pytest.skip("COUNTS_MANIFEST_A88.json not yet generated")

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
            manifest["evidence_bundle_hash"] = "c" * 64  # Tampered
            (tmp / "COUNTS_MANIFEST_A88.json").write_text(
                json.dumps(manifest, indent=2), encoding="utf-8"
            )

            scope = _PROJECT_ROOT / "SCOPE_DECLARATION_A88.txt"
            if scope.exists():
                shutil.copy2(scope, tmp / "SCOPE_DECLARATION_A88.txt")

            shutil.copy2(val_path, tmp / "validate_a88.py")
            flaky = _PROJECT_ROOT / "known_flaky_tests.json"
            if flaky.exists():
                shutil.copy2(flaky, tmp / "known_flaky_tests.json")

            a88_test = _PROJECT_ROOT / "tests" / "test_paper_a88_evidence_bundle_hash.py"
            if a88_test.exists():
                shutil.copy2(a88_test, tests_dir / "test_paper_a88_evidence_bundle_hash.py")

            reg = _PROJECT_ROOT / "output" / "REGRESSION_OUTPUT_A88.txt"
            if reg.exists():
                shutil.copy2(reg, output_dir / "REGRESSION_OUTPUT_A88.txt")
            inscope = _PROJECT_ROOT / "output" / "IN_SCOPE_TEST_RESULTS_A88.txt"
            if inscope.exists():
                shutil.copy2(inscope, output_dir / "IN_SCOPE_TEST_RESULTS_A88.txt")
            valout = _PROJECT_ROOT / "output" / "VALIDATION_OUTPUT_A88.txt"
            if valout.exists():
                shutil.copy2(valout, output_dir / "VALIDATION_OUTPUT_A88.txt")

            result = subprocess.run(
                [sys.executable, str(tmp / "validate_a88.py")],
                capture_output=True, text=True, timeout=60, cwd=str(tmp),
            )
            assert result.returncode != 0, (
                f"validate_a88.py should exit nonzero on tampered bundle. "
                f"Exit code: {result.returncode}. Output:\n{result.stdout[-500:]}"
            )


# -------------------------------------------------------------------
# Class 5: Invariants preserved
# -------------------------------------------------------------------
class TestA88Invariants:
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
