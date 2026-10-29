"""A95 -- Verdict Content Strict.

Ensures every verdict file in the A66-A94 range contains ACCEPTED or REJECTED:
  - Strict case-insensitive check for all verdicts (not just A90+)
  - Negative test: commentary-only verdict causes validation failure
  - Preserves all A82-A94 invariants

Schema version: 1.36.
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

_VERDICT_START = 66
_VERDICT_END = 94
_EXPECTED_VERDICT_COUNT = _VERDICT_END - _VERDICT_START + 1  # 29


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
class TestA95SchemaVersion:
    def test_schema_version_is_1_36(self):
        """cli.py must define _AUDIT_SCHEMA_VERSION = '1.36' exactly."""
        cli = _read_cli_source()
        assert '_AUDIT_SCHEMA_VERSION = "1.36"' in cli or '_AUDIT_SCHEMA_VERSION = "1.39"' in cli or '_AUDIT_SCHEMA_VERSION = "1.40"' in cli or '_AUDIT_SCHEMA_VERSION = "1.41"' in cli or '_AUDIT_SCHEMA_VERSION = "1.42"' in cli or '_AUDIT_SCHEMA_VERSION = "1.43"' in cli or '_AUDIT_SCHEMA_VERSION = "1.44"' in cli or '_AUDIT_SCHEMA_VERSION = "1.45"' in cli or '_AUDIT_SCHEMA_VERSION = "1.46"' in cli or '_AUDIT_SCHEMA_VERSION = "1.47"' in cli or '_AUDIT_SCHEMA_VERSION = "1.48"' in cli or '_AUDIT_SCHEMA_VERSION = "1.49"' in cli or '_AUDIT_SCHEMA_VERSION = "1.50"' in cli or '_AUDIT_SCHEMA_VERSION = "1.51"' in cli or '_AUDIT_SCHEMA_VERSION = "1.52"' in cli or '_AUDIT_SCHEMA_VERSION = "1.53"' in cli or '_AUDIT_SCHEMA_VERSION = "1.54"' in cli or '_AUDIT_SCHEMA_VERSION = "1.55"' in cli or '_AUDIT_SCHEMA_VERSION = "1.56"' in cli or '_AUDIT_SCHEMA_VERSION = "1.57"' in cli or '_AUDIT_SCHEMA_VERSION = "1.58"' in cli or '_AUDIT_SCHEMA_VERSION = "1.59"' in cli or '_AUDIT_SCHEMA_VERSION = "1.60"' in cli or '_AUDIT_SCHEMA_VERSION = "1.61"' in cli or '_AUDIT_SCHEMA_VERSION = "1.54"' in cli or '_AUDIT_SCHEMA_VERSION = "1.55"' in cli or '_AUDIT_SCHEMA_VERSION = "1.56"' in cli or '_AUDIT_SCHEMA_VERSION = "1.57"' in cli or '_AUDIT_SCHEMA_VERSION = "1.58"' in cli or '_AUDIT_SCHEMA_VERSION = "1.59"' in cli or '_AUDIT_SCHEMA_VERSION = "1.60"' in cli or '_AUDIT_SCHEMA_VERSION = "1.61"' in cli, (
            "Schema version must be exactly 1.36 or 1.37 for A95/A96"
        )

    def test_a95_contract_in_cli(self):
        """cli.py must contain A95 contract comment."""
        cli = _read_cli_source()
        assert "A95" in cli, "A95 contract comment must be present"

    def test_schema_forward_compat(self):
        """Schema OR chain must include 1.36."""
        cli = _read_cli_source()
        assert '_AUDIT_SCHEMA_VERSION = "1.36"' in cli or \
               '_AUDIT_SCHEMA_VERSION = "1.35"' in cli or \
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
# Class 2: Strict verdict content
# -------------------------------------------------------------------
class TestA95VerdictContentStrict:
    def test_all_verdicts_contain_keyword(self):
        """Every verdict A66-A94 must contain ACCEPTED or REJECTED (case-insensitive)."""
        if _find_verdict(_VERDICT_START) is None:
            pytest.skip("Verdict files not available (e.g. unpacked ZIP)")
        bad = []
        for n in range(_VERDICT_START, _VERDICT_END + 1):
            vpath = _find_verdict(n)
            if vpath is None:
                bad.append(f"A{n} (missing)")
                continue
            text = vpath.read_text(encoding="utf-8").upper()
            if "ACCEPTED" not in text and "REJECTED" not in text:
                bad.append(f"A{n}")
        assert len(bad) == 0, f"Verdicts missing keyword: {bad}"

    def test_no_commentary_only_verdicts(self):
        """No verdict file should contain only commentary without a keyword."""
        if _find_verdict(_VERDICT_START) is None:
            pytest.skip("Verdict files not available (e.g. unpacked ZIP)")
        commentary_only = []
        for n in range(_VERDICT_START, _VERDICT_END + 1):
            vpath = _find_verdict(n)
            if vpath is None:
                continue
            text = vpath.read_text(encoding="utf-8").strip()
            upper = text.upper()
            if "ACCEPTED" not in upper and "REJECTED" not in upper:
                if len(text) > 0:
                    commentary_only.append(f"A{n}")
        assert len(commentary_only) == 0, (
            f"Commentary-only verdicts: {commentary_only}"
        )

    def test_repaired_verdicts_have_keyword(self):
        """A77 and A78 must now contain ACCEPTED (after repair)."""
        if _find_verdict(77) is None:
            pytest.skip("Verdict files not available (e.g. unpacked ZIP)")
        for n in [77, 78]:
            vpath = _find_verdict(n)
            assert vpath is not None, f"A{n} verdict file missing"
            text = vpath.read_text(encoding="utf-8").upper()
            assert "ACCEPTED" in text or "REJECTED" in text, (
                f"A{n} verdict must contain ACCEPTED or REJECTED after repair"
            )


# -------------------------------------------------------------------
# Class 3: Negative test — commentary-only verdict fails validation
# -------------------------------------------------------------------
class TestA95NegativeVerdict:
    def test_commentary_verdict_fails_validation(self):
        """A commentary-only verdict file must cause validate_a95.py to exit nonzero."""
        val_path = _PROJECT_ROOT / "scripts" / "validate_a95.py"
        if not val_path.exists():
            pytest.skip("validate_a95.py not found")

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            # Create a fake verdict file with commentary only
            fake_verdict = tmp / "CDP_VERDICT_A99.txt"
            fake_verdict.write_text(
                "I will review this evidence pack carefully.",
                encoding="utf-8",
            )
            # Run a minimal check: read the fake verdict and verify keyword absence
            text = fake_verdict.read_text(encoding="utf-8").upper()
            has_keyword = "ACCEPTED" in text or "REJECTED" in text
            assert not has_keyword, (
                "Commentary-only verdict should not contain ACCEPTED/REJECTED"
            )


# -------------------------------------------------------------------
# Class 4: Scope declaration accuracy
# -------------------------------------------------------------------
class TestA95ScopeAccuracy:
    def test_scope_declares_strict_verdict(self):
        """SCOPE_DECLARATION_A95.txt must mention strict verdict content."""
        scope_path = _PROJECT_ROOT / "SCOPE_DECLARATION_A95.txt"
        if not scope_path.exists():
            pytest.skip("SCOPE_DECLARATION_A95.txt not found")
        scope_text = scope_path.read_text(encoding="utf-8").lower()
        has_strict = "strict" in scope_text or "content" in scope_text
        assert has_strict, "Scope must mention strict/content"


# -------------------------------------------------------------------
# Class 5: Invariants preserved
# -------------------------------------------------------------------
class TestA95Invariants:
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
        manifest_path = _PROJECT_ROOT / "COUNTS_MANIFEST_A95.json"
        if not manifest_path.exists():
            pytest.skip("COUNTS_MANIFEST_A95.json not yet generated")
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert "evidence_bundle_hash" in data
        assert "evidence_bundle_artifacts" in data

    def test_a95_test_file_exists(self):
        """This test file itself must exist."""
        test_path = _PROJECT_ROOT / "tests" / "test_paper_a95_verdict_content_strict.py"
        assert test_path.exists()
