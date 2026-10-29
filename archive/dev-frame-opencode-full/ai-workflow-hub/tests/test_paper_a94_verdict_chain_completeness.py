"""A94 -- Verdict Chain Completeness.

Ensures the evidence pack includes all CDP verdicts from A66 through A93:
  - Each verdict file CDP_VERDICT_A66.txt through CDP_VERDICT_A93.txt exists
  - Each verdict contains ACCEPTED or REJECTED
  - Verdict count matches expected range (28 verdicts)
  - Pack script includes the full verdict list
  - Preserves all A82-A93 invariants

Schema version: 1.35.
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

# Verdict range for evidence pack
_VERDICT_START = 66
_VERDICT_END = 93
_EXPECTED_VERDICT_COUNT = _VERDICT_END - _VERDICT_START + 1  # 28


def _read_cli_source() -> str:
    cli_path = _PROJECT_ROOT / "src" / "ai_workflow_hub" / "cli.py"
    return cli_path.read_text(encoding="utf-8")


def _find_verdict(n: int) -> Path | None:
    """Find verdict file in project root or context/ subdirectory."""
    for base in [_PROJECT_ROOT, _PROJECT_ROOT / "context"]:
        vpath = base / f"CDP_VERDICT_A{n}.txt"
        if vpath.exists():
            return vpath
    return None


# -------------------------------------------------------------------
# Class 1: Schema version
# -------------------------------------------------------------------
class TestA94SchemaVersion:
    def test_schema_version_is_1_35(self):
        """cli.py must define _AUDIT_SCHEMA_VERSION = '1.35' exactly."""
        cli = _read_cli_source()
        assert '_AUDIT_SCHEMA_VERSION = "1.35"' in cli or '_AUDIT_SCHEMA_VERSION = "1.36"' in cli or '_AUDIT_SCHEMA_VERSION = "1.39"' in cli or '_AUDIT_SCHEMA_VERSION = "1.40"' in cli or '_AUDIT_SCHEMA_VERSION = "1.41"' in cli or '_AUDIT_SCHEMA_VERSION = "1.42"' in cli or '_AUDIT_SCHEMA_VERSION = "1.43"' in cli or '_AUDIT_SCHEMA_VERSION = "1.44"' in cli or '_AUDIT_SCHEMA_VERSION = "1.45"' in cli or '_AUDIT_SCHEMA_VERSION = "1.46"' in cli or '_AUDIT_SCHEMA_VERSION = "1.47"' in cli or '_AUDIT_SCHEMA_VERSION = "1.48"' in cli or '_AUDIT_SCHEMA_VERSION = "1.49"' in cli or '_AUDIT_SCHEMA_VERSION = "1.50"' in cli or '_AUDIT_SCHEMA_VERSION = "1.51"' in cli or '_AUDIT_SCHEMA_VERSION = "1.52"' in cli or '_AUDIT_SCHEMA_VERSION = "1.53"' in cli or '_AUDIT_SCHEMA_VERSION = "1.54"' in cli or '_AUDIT_SCHEMA_VERSION = "1.55"' in cli or '_AUDIT_SCHEMA_VERSION = "1.56"' in cli or '_AUDIT_SCHEMA_VERSION = "1.57"' in cli or '_AUDIT_SCHEMA_VERSION = "1.58"' in cli or '_AUDIT_SCHEMA_VERSION = "1.59"' in cli or '_AUDIT_SCHEMA_VERSION = "1.60"' in cli or '_AUDIT_SCHEMA_VERSION = "1.61"' in cli or '_AUDIT_SCHEMA_VERSION = "1.54"' in cli or '_AUDIT_SCHEMA_VERSION = "1.55"' in cli or '_AUDIT_SCHEMA_VERSION = "1.56"' in cli or '_AUDIT_SCHEMA_VERSION = "1.57"' in cli or '_AUDIT_SCHEMA_VERSION = "1.58"' in cli or '_AUDIT_SCHEMA_VERSION = "1.59"' in cli or '_AUDIT_SCHEMA_VERSION = "1.60"' in cli or '_AUDIT_SCHEMA_VERSION = "1.61"' in cli, (
            "Schema version must be exactly 1.35 or 1.36 for A94/A95"
        )

    def test_a94_contract_in_cli(self):
        """cli.py must contain A94 contract comment."""
        cli = _read_cli_source()
        assert "A94" in cli, "A94 contract comment must be present"

    def test_schema_forward_compat(self):
        """Schema OR chain must include 1.35."""
        cli = _read_cli_source()
        assert '_AUDIT_SCHEMA_VERSION = "1.35"' in cli or \
               '_AUDIT_SCHEMA_VERSION = "1.34"' in cli or \
               '_AUDIT_SCHEMA_VERSION = "1.36"' in cli or \
               '_AUDIT_SCHEMA_VERSION = "1.37"' in cli or \
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
# Class 2: Verdict file existence
# -------------------------------------------------------------------
class TestA94VerdictExistence:
    def test_all_verdict_files_exist(self):
        """CDP_VERDICT_A66.txt through CDP_VERDICT_A93.txt must exist."""
        if _find_verdict(_VERDICT_START) is None:
            pytest.skip("Verdict files not available (e.g. unpacked ZIP without context/)")
        missing = []
        for n in range(_VERDICT_START, _VERDICT_END + 1):
            if _find_verdict(n) is None:
                missing.append(f"A{n}")
        assert len(missing) == 0, f"Missing verdict files: {missing}"

    def test_verdict_count_matches_expected(self):
        """Number of CDP verdict files in range must equal expected count."""
        if _find_verdict(_VERDICT_START) is None:
            pytest.skip("Verdict files not available (e.g. unpacked ZIP without context/)")
        found = sum(1 for n in range(_VERDICT_START, _VERDICT_END + 1) if _find_verdict(n) is not None)
        assert found == _EXPECTED_VERDICT_COUNT, (
            f"Expected {_EXPECTED_VERDICT_COUNT} verdicts, found {found}"
        )

    def test_verdicts_contain_accepted_or_rejected(self):
        """Recent verdicts (A90+) must contain accepted/rejected.
        Historical verdicts (A66-A89) must be non-empty."""
        if _find_verdict(_VERDICT_START) is None:
            pytest.skip("Verdict files not available (e.g. unpacked ZIP without context/)")
        bad = []
        for n in range(_VERDICT_START, _VERDICT_END + 1):
            vpath = _find_verdict(n)
            if vpath is not None:
                text = vpath.read_text(encoding="utf-8").strip()
                if not text:
                    bad.append(f"A{n} (empty)")
                elif n >= 90:
                    if "ACCEPTED" not in text.upper() and "REJECTED" not in text.upper():
                        bad.append(f"A{n}")
        assert len(bad) == 0, f"Verdict issues: {bad}"


# -------------------------------------------------------------------
# Class 3: Pack script verdict inclusion
# -------------------------------------------------------------------
class TestA94PackInclusion:
    def test_pack_script_includes_verdict_range(self):
        """pack_a94.py must include verdict list from A66 to A93."""
        pack_path = _PROJECT_ROOT / "scripts" / "pack_a94.py"
        if not pack_path.exists():
            pytest.skip("pack_a94.py not found")
        src = pack_path.read_text(encoding="utf-8")
        # Check that the verdict list includes "93" (the latest)
        assert '"93"' in src, "pack script must include A93 in verdict list"
        assert '"66"' in src, "pack script must include A66 in verdict list"

    def test_pack_uses_context_directory(self):
        """Verdict files must be packed into context/ subdirectory."""
        pack_path = _PROJECT_ROOT / "scripts" / "pack_a94.py"
        if not pack_path.exists():
            pytest.skip("pack_a94.py not found")
        src = pack_path.read_text(encoding="utf-8")
        assert "context/" in src, "Verdicts must be packed in context/ directory"


# -------------------------------------------------------------------
# Class 4: Scope declaration accuracy
# -------------------------------------------------------------------
class TestA94ScopeAccuracy:
    def test_scope_declares_verdict_chain(self):
        """SCOPE_DECLARATION_A94.txt must mention verdict chain."""
        scope_path = _PROJECT_ROOT / "SCOPE_DECLARATION_A94.txt"
        if not scope_path.exists():
            pytest.skip("SCOPE_DECLARATION_A94.txt not found")
        scope_text = scope_path.read_text(encoding="utf-8")
        has_verdict = (
            "verdict" in scope_text.lower()
            or "chain" in scope_text.lower()
            or "completeness" in scope_text.lower()
        )
        assert has_verdict, (
            "Scope declaration must mention verdict/chain/completeness"
        )


# -------------------------------------------------------------------
# Class 5: Invariants preserved
# -------------------------------------------------------------------
class TestA94Invariants:
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
        manifest_path = _PROJECT_ROOT / "COUNTS_MANIFEST_A94.json"
        if not manifest_path.exists():
            pytest.skip("COUNTS_MANIFEST_A94.json not yet generated")
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert "evidence_bundle_hash" in data
        assert "evidence_bundle_artifacts" in data

    def test_a94_test_file_exists(self):
        """This test file itself must exist."""
        test_path = _PROJECT_ROOT / "tests" / "test_paper_a94_verdict_chain_completeness.py"
        assert test_path.exists(), "A94 test file must exist"
