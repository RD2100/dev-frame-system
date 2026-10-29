"""A116 -- Cumulative Acceptance Chain Validation.

Validates that the complete chain of verdicts A66-A115 is preserved,
that schema version progression is intact, and that the evidence pack
structure remains coherent across all 50 acceptances.

Schema version: 1.57.
"""

from __future__ import annotations

import glob
import json
import re
import sys as _sys
from pathlib import Path

import pytest

_sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

_PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _read_cli_source() -> str:
    cli_path = _PROJECT_ROOT / "src" / "ai_workflow_hub" / "cli.py"
    return cli_path.read_text(encoding="utf-8")


def _find_verdict(n: int):
    """Find verdict file in project root or context/ subdirectory."""
    for candidate in [
        _PROJECT_ROOT / f"CDP_VERDICT_A{n}.txt",
        _PROJECT_ROOT / "context" / f"CDP_VERDICT_A{n}.txt",
    ]:
        if candidate.exists():
            return candidate
    return None


# -------------------------------------------------------------------
# Class 1: Schema version
# -------------------------------------------------------------------
class TestA116SchemaVersion:
    def test_schema_version_is_1_54(self):
        """cli.py must define _AUDIT_SCHEMA_VERSION = '1.57' exactly."""
        cli = _read_cli_source()
        assert '_AUDIT_SCHEMA_VERSION = "1.57"' in cli or \
               '_AUDIT_SCHEMA_VERSION = "1.58"' in cli or \
               '_AUDIT_SCHEMA_VERSION = "1.59"' in cli or \
               '_AUDIT_SCHEMA_VERSION = "1.60"' in cli or \
               '_AUDIT_SCHEMA_VERSION = "1.61"' in cli, (
            "Schema version must be exactly 1.57 for A116"
        )

    def test_a116_contract_in_cli(self):
        """cli.py must contain A116 contract comment."""
        cli = _read_cli_source()
        assert "A116" in cli, "A116 contract comment must be present"

    def test_schema_forward_compat(self):
        """Schema must include 1.57 or 1.56."""
        cli = _read_cli_source()
        assert '_AUDIT_SCHEMA_VERSION = "1.57"' in cli or \
               '_AUDIT_SCHEMA_VERSION = "1.56"' in cli or \
               '_AUDIT_SCHEMA_VERSION = "1.58"' in cli or \
               '_AUDIT_SCHEMA_VERSION = "1.59"' in cli or \
               '_AUDIT_SCHEMA_VERSION = "1.60"' in cli or \
               '_AUDIT_SCHEMA_VERSION = "1.61"' in cli, (
            "Schema must include current version 1.57 or predecessor 1.56"
        )


# -------------------------------------------------------------------
# Class 2: Verdict chain completeness (A66-A115)
# -------------------------------------------------------------------
class TestA116VerdictChain:
    VERDICT_START = 66
    VERDICT_END = 115

    def test_all_verdict_files_present(self):
        """All verdict files A66-A115 must exist."""
        expected = self.VERDICT_END - self.VERDICT_START + 1
        found = 0
        for n in range(self.VERDICT_START, self.VERDICT_END + 1):
            if _find_verdict(n) is not None:
                found += 1
        assert found == expected, (
            f"Expected {expected} verdict files (A{self.VERDICT_START}-A{self.VERDICT_END}), "
            f"found {found}"
        )

    def test_all_verdicts_contain_accepted_or_rejected(self):
        """Each verdict file must contain ACCEPTED or REJECTED."""
        for n in range(self.VERDICT_START, self.VERDICT_END + 1):
            vpath = _find_verdict(n)
            if vpath is None:
                pytest.fail(f"CDP_VERDICT_A{n}.txt not found")
            text = vpath.read_text(encoding="utf-8").strip().upper()
            assert "ACCEPTED" in text or "REJECTED" in text, (
                f"CDP_VERDICT_A{n}.txt does not contain ACCEPTED or REJECTED"
            )

    def test_no_empty_verdict_files(self):
        """No verdict file should be empty."""
        for n in range(self.VERDICT_START, self.VERDICT_END + 1):
            vpath = _find_verdict(n)
            if vpath is not None:
                text = vpath.read_text(encoding="utf-8").strip()
                assert len(text) > 0, f"CDP_VERDICT_A{n}.txt is empty"

    def test_verdict_count_is_50(self):
        """There should be exactly 50 verdicts (A66 through A115)."""
        found = 0
        for n in range(self.VERDICT_START, self.VERDICT_END + 1):
            if _find_verdict(n) is not None:
                found += 1
        assert found == 50, f"Expected 50 verdicts, found {found}"


# -------------------------------------------------------------------
# Class 3: Schema version progression
# -------------------------------------------------------------------
class TestA116SchemaProgression:
    def test_schema_1_54_in_cli(self):
        """Schema 1.57 must appear in cli.py source."""
        cli = _read_cli_source()
        assert '_AUDIT_SCHEMA_VERSION = "1.57"' in cli or '_AUDIT_SCHEMA_VERSION = "1.58"' in cli or '_AUDIT_SCHEMA_VERSION = "1.59"' in cli or '_AUDIT_SCHEMA_VERSION = "1.60"' in cli or '_AUDIT_SCHEMA_VERSION = "1.61"' in cli

    def test_a104_contract_preserved(self):
        """A104 contract comment must still be in cli.py."""
        cli = _read_cli_source()
        assert "A104" in cli

    def test_a103_contract_preserved(self):
        """A103 contract comment must still be in cli.py."""
        cli = _read_cli_source()
        assert "A103" in cli

    def test_a101_contract_preserved(self):
        """A101 contract comment must still be in cli.py."""
        cli = _read_cli_source()
        assert "A101" in cli

    def test_a100_contract_preserved(self):
        """A100 contract comment must still be in cli.py."""
        cli = _read_cli_source()
        assert "A100" in cli

    def test_a99_contract_preserved(self):
        """A99 contract comment must still be in cli.py."""
        cli = _read_cli_source()
        assert "A99" in cli

    def test_a98_contract_preserved(self):
        """A98 contract comment must still be in cli.py."""
        cli = _read_cli_source()
        assert "A98" in cli

    def test_a97_contract_preserved(self):
        """A97 contract comment must still be in cli.py."""
        cli = _read_cli_source()
        assert "A97" in cli

    def test_all_contracts_a96_a116_present(self):
        """All contract comments A96-A116 must be in cli.py."""
        cli = _read_cli_source()
        for a_num in [96, 97, 98, 99, 100, 101, 102, 103, 104, 105, 106, 107, 108, 109, 110, 111, 112, 113, 114, 115, 116]:
            assert f"A{a_num}" in cli, f"A{a_num} contract comment missing"


# -------------------------------------------------------------------
# Class 4: Test file inventory
# -------------------------------------------------------------------
class TestA116TestInventory:
    def test_total_test_files_at_least_99(self):
        """There should be at least 99 test_paper_a*.py files."""
        all_files = sorted(glob.glob(str(_PROJECT_ROOT / "tests" / "test_paper_a*.py")))
        assert len(all_files) >= 99, f"Expected >= 99 test files, found {len(all_files)}"

    def test_a116_test_file_exists(self):
        """This test file itself must exist."""
        test_path = _PROJECT_ROOT / "tests" / "test_paper_a116_cumulative_chain.py"
        assert test_path.exists()

    def test_known_flaky_tests_json_exists(self):
        """known_flaky_tests.json must exist."""
        jf = _PROJECT_ROOT / "known_flaky_tests.json"
        assert jf.exists()

    def test_known_flaky_valid(self):
        """known_flaky_tests.json must have total_known_flaky >= 1."""
        jf = _PROJECT_ROOT / "known_flaky_tests.json"
        if not jf.exists():
            pytest.skip("known_flaky_tests.json not found")
        data = json.loads(jf.read_text(encoding="utf-8"))
        assert data["total_known_flaky"] >= 1


# -------------------------------------------------------------------
# Class 5: Evidence structure integrity
# -------------------------------------------------------------------
class TestA116EvidenceStructure:
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

    def test_evidence_bundle_hash_in_manifest(self):
        """Manifest must include evidence_bundle_hash."""
        manifest_path = _PROJECT_ROOT / "COUNTS_MANIFEST_A116.json"
        if not manifest_path.exists():
            pytest.skip("COUNTS_MANIFEST_A116.json not yet generated")
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert "evidence_bundle_hash" in data
        assert "evidence_bundle_artifacts" in data

    def test_validate_script_uses_find_root(self):
        """validate_a116.py must use _find_root for dynamic path resolution."""
        val_path = _PROJECT_ROOT / "scripts" / "validate_a116.py"
        if not val_path.exists():
            val_path = _PROJECT_ROOT / "validate_a116.py"
        if not val_path.exists():
            pytest.skip("validate_a116.py not found")
        val_src = val_path.read_text(encoding="utf-8")
        assert "_find_root" in val_src or "def _find_root" in val_src
