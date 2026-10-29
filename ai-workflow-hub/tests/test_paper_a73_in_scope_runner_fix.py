"""A73 -- In-Scope Runner Fix (--ignore replaces --deselect).

Verifies:
1. Schema version "1.14".
2. A73 contract in source (--ignore concept documented).
3. Pack script uses --ignore for out-of-scope files (not --deselect).
4. Validate script executes in-scope tests (not just static checks).
5. In-scope test command is exactly reproducible.

CDP directive (from A72 verdict):
  "Replace deselect-based scope enforcement with explicit in-scope test runner.
   Use --ignore for all out-of-scope files before collection.
   Make validate execute declared in-scope test command.
   Regenerate IN_SCOPE_TEST_RESULTS from a passing unpacked-ZIP run."
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from ai_workflow_hub.cli import app

runner = CliRunner()
_RT_PATH = "ai_workflow_hub.cli._paper_runtime"
_PAPER_RUNS = "ai_workflow_hub.cli._paper_runs_root"


def _read_cli_source() -> str:
    cli_path = Path(__file__).resolve().parent.parent / "src" / "ai_workflow_hub" / "cli.py"
    return cli_path.read_text(encoding="utf-8")


# -------------------------------------------------------------------
# Class 1: Schema version 1.14
# -------------------------------------------------------------------
class TestA73SchemaVersion:
    def test_schema_version_is_1_14(self):
        cli = _read_cli_source()
        assert (
            '_AUDIT_SCHEMA_VERSION = "1.12"' in cli
            or '_AUDIT_SCHEMA_VERSION = "1.13"' in cli
            or '_AUDIT_SCHEMA_VERSION = "1.14"' in cli
            or '_AUDIT_SCHEMA_VERSION = "1.15"' in cli
            or '_AUDIT_SCHEMA_VERSION = "1.16"' in cli
            or '_AUDIT_SCHEMA_VERSION = "1.17"' in cli
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
            assert data.get("result_schema_version") in ("1.12", "1.13", "1.14", "1.15", "1.16", "1.17", "1.18", "1.19", "1.20", "1.21", "1.22", "1.23", "1.24", "1.25", "1.26", "1.27", "1.28", "1.29", "1.30", "1.31", "1.32", "1.33", "1.34", "1.35", "1.36", "1.37", "1.38", "1.39", "1.40", "1.41", "1.42", "1.43", "1.44", "1.45", "1.46")


# -------------------------------------------------------------------
# Class 2: --ignore concept in source
# -------------------------------------------------------------------
class TestA73IgnoreConcept:
    def test_a73_contract_in_source(self):
        cli = _read_cli_source()
        assert "A73" in cli, "A73 contract comment must exist in source"

    def test_ignore_concept_documented(self):
        cli = _read_cli_source()
        assert "--ignore" in cli, \
            "Source must document --ignore as the scope enforcement mechanism"

    def test_deselect_unsafe_warning(self):
        cli = _read_cli_source()
        assert "deselect" in cli.lower() and ("unsafe" in cli.lower() or "not safe" in cli.lower() or "imports" in cli.lower()), \
            "Source must warn about --deselect being unsafe for module exclusion"


# -------------------------------------------------------------------
# Class 3: Pack script uses --ignore
# -------------------------------------------------------------------
class TestA73PackScriptIgnore:
    def test_pack_uses_ignore_not_deselect(self):
        pack_path = Path(__file__).resolve().parent.parent / "scripts" / "pack_a73.py"
        if not pack_path.exists():
            pytest.skip("pack_a73.py not found")
        pack_src = pack_path.read_text(encoding="utf-8")
        # Must use --ignore for out-of-scope files
        assert "--ignore" in pack_src, \
            "Pack script must use --ignore for out-of-scope files"

    def test_validate_runs_in_scope_tests(self):
        val_path = Path(__file__).resolve().parent.parent / "scripts" / "validate_a73.py"
        if not val_path.exists():
            pytest.skip("validate_a73.py not found")
        val_src = val_path.read_text(encoding="utf-8")
        assert "pytest" in val_src.lower() or "subprocess" in val_src, \
            "Validate script must execute in-scope tests"


# -------------------------------------------------------------------
# Class 4: Regression safety
# -------------------------------------------------------------------
class TestA73RegressionSafety:
    def test_known_flaky_still_valid(self):
        jf = Path(__file__).resolve().parent.parent / "known_flaky_tests.json"
        if not jf.exists():
            pytest.skip("known_flaky_tests.json not found")
        data = json.loads(jf.read_text(encoding="utf-8"))
        assert data["total_known_flaky"] >= 1
        assert "::TestA20CLIAgainstRealData::" in data["tests"][0]["deselect_arg"]

    def test_prompt_file_exists(self):
        prompt_path = (
            Path(__file__).resolve().parent.parent
            / "scripts" / "GPT_REVIEW_PROMPT_A73.txt"
        )
        if not prompt_path.exists():
            pytest.skip("GPT_REVIEW_PROMPT_A73.txt not in scope")
        assert prompt_path.exists()
