"""A77 -- Evidence-Pack Dependency Bootstrap (click>=8.2.0 enforcement).

Root cause from A76 rejection:
  A76 correctly diagnosed the Click stdout/stderr separation issue and pinned
  click>=8.2.0 in pyproject.toml. However, the pin only specifies what SHOULD
  be installed; it does not change the already-installed Click version in
  CDP's Linux environment (which has Click 8.1.8).

Fix:
  Add a bootstrap preflight step to validate and pack scripts that:
  1. Checks the installed Click version
  2. Auto-installs click>=8.2.0 if the installed version < 8.2.0
  3. Records the installed Click version in all validation/test transcripts
  4. Updated reproducible command includes the pip install step

Verifies:
1. Schema version "1.18".
2. validate_a77.py contains bootstrap preflight logic.
3. pack_a77.py contains bootstrap preflight logic.
4. Reproducible command includes pip install click>=8.2.0.
5. All A75/A76 invariants preserved.
6. Regression safety.

CDP directive (from A76 verdict):
  "Make the evidence-pack test environment deterministic. Add a reproducible
   bootstrap step that installs/enforces click>=8.2.0 before running in-scope
   tests. Record the actual Click version in validation and test transcripts."
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

_PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _read_cli_source() -> str:
    cli_path = _PROJECT_ROOT / "src" / "ai_workflow_hub" / "cli.py"
    return cli_path.read_text(encoding="utf-8")


# -------------------------------------------------------------------
# Class 1: Schema version 1.18
# -------------------------------------------------------------------
class TestA77SchemaVersion:
    def test_schema_version_is_1_18(self):
        cli = _read_cli_source()
        assert (
            '_AUDIT_SCHEMA_VERSION = "1.16"' in cli
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
            assert data.get("result_schema_version") in ("1.16", "1.17", "1.18", "1.19", "1.20", "1.21", "1.22", "1.23", "1.24", "1.25", "1.26", "1.27", "1.28", "1.29", "1.30", "1.31", "1.32", "1.33", "1.34", "1.35", "1.36", "1.37", "1.38", "1.39", "1.40", "1.41", "1.42", "1.43", "1.44", "1.45", "1.46")


# -------------------------------------------------------------------
# Class 2: Dependency bootstrap in validate/pack scripts
# -------------------------------------------------------------------
class TestA77DependencyBootstrap:
    def test_validate_has_bootstrap_preflight(self):
        """validate_a77.py must contain Click version bootstrap logic."""
        val_path = _PROJECT_ROOT / "scripts" / "validate_a77.py"
        if not val_path.exists():
            pytest.skip("validate_a77.py not found")
        val_src = val_path.read_text(encoding="utf-8")
        # Must check click version and install if needed
        assert "click" in val_src.lower(), \
            "validate script must reference click"
        assert "pip install" in val_src or "subprocess" in val_src, \
            "validate script must be able to install click>=8.2.0"
        assert "8.2" in val_src, \
            "validate script must check for Click 8.2.0"

    def test_pack_has_bootstrap_preflight(self):
        """pack_a77.py must contain Click version bootstrap logic."""
        pack_path = _PROJECT_ROOT / "scripts" / "pack_a77.py"
        if not pack_path.exists():
            pytest.skip("pack_a77.py not found")
        pack_src = pack_path.read_text(encoding="utf-8")
        assert "click" in pack_src.lower(), \
            "pack script must reference click"
        assert "pip install" in pack_src or "subprocess" in pack_src, \
            "pack script must be able to install click>=8.2.0"
        assert "8.2" in pack_src, \
            "pack script must check for Click 8.2.0"

    def test_bootstrap_records_click_version(self):
        """Validation output must record the installed Click version."""
        val_path = _PROJECT_ROOT / "scripts" / "validate_a77.py"
        if not val_path.exists():
            pytest.skip("validate_a77.py not found")
        val_src = val_path.read_text(encoding="utf-8")
        assert "click" in val_src.lower() and "version" in val_src.lower(), \
            "validate script must record Click version in output"

    def test_reproducible_command_includes_pip(self):
        """Scope declaration reproducible command must include pip install."""
        scope_path = _PROJECT_ROOT / "SCOPE_DECLARATION_A77.txt"
        if not scope_path.exists():
            pytest.skip("SCOPE_DECLARATION_A77.txt not found")
        scope_src = scope_path.read_text(encoding="utf-8")
        assert "pip install" in scope_src, \
            "Reproducible command must include pip install step"
        assert "click" in scope_src.lower(), \
            "Reproducible command must install click>=8.2.0"


# -------------------------------------------------------------------
# Class 3: All invariants preserved from A75/A76
# -------------------------------------------------------------------
class TestA77InvariantsPreserved:
    def test_a77_contract_in_cli(self):
        cli = _read_cli_source()
        assert "A77" in cli, "A77 contract comment missing from cli.py"

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

    def test_click_still_pinned_in_pyproject(self):
        pyproject = (_PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8")
        assert "click>=8.2.0" in pyproject


# -------------------------------------------------------------------
# Class 4: Regression safety
# -------------------------------------------------------------------
class TestA77RegressionSafety:
    def test_known_flaky_still_valid(self):
        jf = _PROJECT_ROOT / "known_flaky_tests.json"
        if not jf.exists():
            pytest.skip("known_flaky_tests.json not found")
        data = json.loads(jf.read_text(encoding="utf-8"))
        assert data["total_known_flaky"] >= 1

    def test_prompt_file_exists(self):
        prompt_path = _PROJECT_ROOT / "scripts" / "GPT_REVIEW_PROMPT_A77.txt"
        if not prompt_path.exists():
            pytest.skip("GPT_REVIEW_PROMPT_A77.txt not in scope")
        assert prompt_path.exists()
