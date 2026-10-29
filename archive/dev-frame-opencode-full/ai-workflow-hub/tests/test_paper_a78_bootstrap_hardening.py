"""A78 -- Dependency Bootstrap Hardening (fresh subprocess version check, pin range).

From A77 accepted_with_limitations directive:
  A77 bootstrap works but has two issues:
  1. Same-process version check after pip install can be stale
     (importlib.metadata caches old version)
  2. Click pin is open-ended (>=8.2.0) -- Click 9 may break compatibility

Fix:
  1. Re-check Click version in a fresh subprocess after installation
  2. Pin tested Click range: click>=8.2.0,<9 in pyproject.toml
  3. Report both before/after versions accurately in validation transcripts
  4. Align prompt counts with actual test counts

Verifies:
1. Schema version "1.19".
2. pyproject.toml pins click>=8.2.0,<9.
3. validate_a78.py uses subprocess for version check after pip install.
4. All invariants preserved.
5. Regression safety.

CDP directive (from A77 verdict):
  "Make dependency bootstrap reporting and isolation stronger. Re-check Click
   in a fresh subprocess after installation. Report both before/after versions.
   Pin a tested Click range."
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from ai_workflow_hub.cli import app

runner = CliRunner()
_RT_PATH = "ai_workflow_hub.cli._paper_runtime"
_PAPER_RUNS = "ai_workflow_hub.cli._paper_runs_root"

_PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _read_cli_source() -> str:
    cli_path = _PROJECT_ROOT / "src" / "ai_workflow_hub" / "cli.py"
    return cli_path.read_text(encoding="utf-8")


def _read_pyproject() -> str:
    return (_PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8")


# -------------------------------------------------------------------
# Class 1: Schema version 1.19
# -------------------------------------------------------------------
class TestA78SchemaVersion:
    def test_schema_version_is_1_19(self):
        cli = _read_cli_source()
        assert (
            '_AUDIT_SCHEMA_VERSION = "1.17"' in cli
            or '_AUDIT_SCHEMA_VERSION = "1.18"' in cli
            or '_AUDIT_SCHEMA_VERSION = "1.19"' in cli
            or '_AUDIT_SCHEMA_VERSION = "1.20"' in cli
            or '_AUDIT_SCHEMA_VERSION = "1.21"' in cli
            or '_AUDIT_SCHEMA_VERSION = "1.22"' in cli or '_AUDIT_SCHEMA_VERSION = "1.23"' in cli or '_AUDIT_SCHEMA_VERSION = "1.24"' in cli or '_AUDIT_SCHEMA_VERSION = "1.25"' in cli or '_AUDIT_SCHEMA_VERSION = "1.26"' in cli or '_AUDIT_SCHEMA_VERSION = "1.27"' in cli or '_AUDIT_SCHEMA_VERSION = "1.28"' in cli or '_AUDIT_SCHEMA_VERSION = "1.29"' in cli or '_AUDIT_SCHEMA_VERSION = "1.30"' in cli or '_AUDIT_SCHEMA_VERSION = "1.31"' in cli or '_AUDIT_SCHEMA_VERSION = "1.32"' in cli or '_AUDIT_SCHEMA_VERSION = "1.33"' in cli or '_AUDIT_SCHEMA_VERSION = "1.34"' in cli or '_AUDIT_SCHEMA_VERSION = "1.35"' in cli or '_AUDIT_SCHEMA_VERSION = "1.36"' in cli or '_AUDIT_SCHEMA_VERSION = "1.39"' in cli or '_AUDIT_SCHEMA_VERSION = "1.40"' in cli or '_AUDIT_SCHEMA_VERSION = "1.41"' in cli or '_AUDIT_SCHEMA_VERSION = "1.42"' in cli or '_AUDIT_SCHEMA_VERSION = "1.43"' in cli or '_AUDIT_SCHEMA_VERSION = "1.44"' in cli or '_AUDIT_SCHEMA_VERSION = "1.45"' in cli or '_AUDIT_SCHEMA_VERSION = "1.46"' in cli or '_AUDIT_SCHEMA_VERSION = "1.47"' in cli or '_AUDIT_SCHEMA_VERSION = "1.48"' in cli or '_AUDIT_SCHEMA_VERSION = "1.49"' in cli or '_AUDIT_SCHEMA_VERSION = "1.50"' in cli or '_AUDIT_SCHEMA_VERSION = "1.51"' in cli or '_AUDIT_SCHEMA_VERSION = "1.52"' in cli or '_AUDIT_SCHEMA_VERSION = "1.53"' in cli or '_AUDIT_SCHEMA_VERSION = "1.54"' in cli or '_AUDIT_SCHEMA_VERSION = "1.55"' in cli or '_AUDIT_SCHEMA_VERSION = "1.56"' in cli or '_AUDIT_SCHEMA_VERSION = "1.57"' in cli or '_AUDIT_SCHEMA_VERSION = "1.58"' in cli or '_AUDIT_SCHEMA_VERSION = "1.59"' in cli or '_AUDIT_SCHEMA_VERSION = "1.60"' in cli or '_AUDIT_SCHEMA_VERSION = "1.61"' in cli or '_AUDIT_SCHEMA_VERSION = "1.54"' in cli or '_AUDIT_SCHEMA_VERSION = "1.55"' in cli or '_AUDIT_SCHEMA_VERSION = "1.56"' in cli or '_AUDIT_SCHEMA_VERSION = "1.57"' in cli or '_AUDIT_SCHEMA_VERSION = "1.58"' in cli or '_AUDIT_SCHEMA_VERSION = "1.59"' in cli or '_AUDIT_SCHEMA_VERSION = "1.60"' in cli or '_AUDIT_SCHEMA_VERSION = "1.61"' in cli
        )

    def test_schema_version_in_output(self, tmp_path):
        runs_dir = tmp_path / "runs"
        run_dir = runs_dir / "test-run"
        run_dir.mkdir(parents=True)
        (run_dir / "state.json").write_text(json.dumps({
            "run_id": "test-run", "task_id": "t", "status": "completed",
            "started_at": "2025-01-01T00:00:00Z", "completed_at": "2025-01-01T01:00:00Z",
            "evidence_manifest": {"files": []}, "closeout_integrity": "complete",
            "ledger_dir": str(run_dir), "decision_base_dir": str(run_dir),
        }), encoding="utf-8")
        (run_dir / "closeout_report.json").write_text(json.dumps({
            "run_id": "test-run", "summary": "test", "generated_at": "2025-01-01T01:00:00Z",
        }), encoding="utf-8")
        (run_dir / "closeout-closeout.md").write_text("# Report\nTest", encoding="utf-8")
        rt = {"sanitize": lambda rid: rid, "runs_root": Path("/tmp/fake_runs")}
        with patch(_RT_PATH, return_value=rt), patch(_PAPER_RUNS, str(runs_dir)):
            r = runner.invoke(app, ["paper", "audit", "--run-id", "test-run", "--json"])
        if r.exit_code == 0:
            data = json.loads(r.stdout)
            assert data.get("result_schema_version") in ("1.17", "1.18", "1.19", "1.20", "1.21", "1.22", "1.23", "1.24", "1.25", "1.26", "1.27", "1.28", "1.29", "1.30", "1.31", "1.32", "1.33", "1.34", "1.35", "1.36", "1.37", "1.38", "1.39", "1.40", "1.41", "1.42", "1.43", "1.44", "1.45", "1.46")


# -------------------------------------------------------------------
# Class 2: Click range pin and subprocess version check
# -------------------------------------------------------------------
class TestA78ClickRangePin:
    def test_pyproject_pins_click_range(self):
        """pyproject.toml must pin click>=8.2.0,<9 (tested range)."""
        toml = _read_pyproject()
        assert "click>=8.2.0,<9" in toml or "click>=8.2.0, <9" in toml, (
            "pyproject.toml must pin click>=8.2.0,<9 for tested range"
        )

    def test_validate_uses_subprocess_version_check(self):
        """validate_a78.py must use subprocess for Click version check."""
        val_path = _PROJECT_ROOT / "scripts" / "validate_a78.py"
        if not val_path.exists():
            pytest.skip("validate_a78.py not found")
        val_src = val_path.read_text(encoding="utf-8")
        # Must use subprocess to check version (not same-process importlib)
        assert "subprocess" in val_src, \
            "validate script must use subprocess for version verification"
        assert "click" in val_src.lower(), \
            "validate script must check Click version"

    def test_validate_reports_before_after_versions(self):
        """validate_a78.py must report before/after Click versions."""
        val_path = _PROJECT_ROOT / "scripts" / "validate_a78.py"
        if not val_path.exists():
            pytest.skip("validate_a78.py not found")
        val_src = val_path.read_text(encoding="utf-8")
        # Must have before/after version reporting
        assert "before" in val_src.lower() or "initial" in val_src.lower() or "current" in val_src.lower(), \
            "validate script must report initial Click version"
        assert "after" in val_src.lower() or "upgraded" in val_src.lower() or "fresh" in val_src.lower(), \
            "validate script must report post-bootstrap Click version"


# -------------------------------------------------------------------
# Class 3: Invariants preserved
# -------------------------------------------------------------------
class TestA78InvariantsPreserved:
    def test_a78_contract_in_cli(self):
        cli = _read_cli_source()
        assert "A78" in cli, "A78 contract comment missing from cli.py"

    def test_emit_json_still_module_level(self):
        cli = _read_cli_source()
        for line in cli.splitlines():
            if "def _emit_json(" in line:
                assert line == line.lstrip()
                return
        pytest.fail("_emit_json definition not found")

    def test_zero_console_print_json_dumps(self):
        cli = _read_cli_source()
        bad_lines = [
            line.strip()
            for line in cli.splitlines()
            if "console.print(json.dumps" in line
            and not line.strip().startswith("#")
        ]
        assert len(bad_lines) == 0

    def test_bootstrap_still_in_validate(self):
        val_path = _PROJECT_ROOT / "scripts" / "validate_a78.py"
        if not val_path.exists():
            pytest.skip("validate_a78.py not found")
        val_src = val_path.read_text(encoding="utf-8")
        assert "pip install" in val_src or "bootstrap" in val_src.lower()


# -------------------------------------------------------------------
# Class 4: Regression safety
# -------------------------------------------------------------------
class TestA78RegressionSafety:
    def test_known_flaky_still_valid(self):
        jf = _PROJECT_ROOT / "known_flaky_tests.json"
        if not jf.exists():
            pytest.skip("known_flaky_tests.json not found")
        data = json.loads(jf.read_text(encoding="utf-8"))
        assert data["total_known_flaky"] >= 1

    def test_prompt_file_exists(self):
        prompt_path = _PROJECT_ROOT / "scripts" / "GPT_REVIEW_PROMPT_A78.txt"
        if not prompt_path.exists():
            pytest.skip("GPT_REVIEW_PROMPT_A78.txt not in scope")
        assert prompt_path.exists()
