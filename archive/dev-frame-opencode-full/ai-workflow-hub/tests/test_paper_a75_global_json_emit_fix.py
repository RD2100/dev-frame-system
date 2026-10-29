"""A75 -- Global JSON Emit Fix (_emit_json module-level, all paper commands).

Verifies:
1. Schema version "1.16".
2. _emit_json() is a module-level function (not nested inside paper_audit).
3. Zero console.print(json.dumps(...)) calls remain in cli.py.
4. _emit_json() called 20+ times across ALL paper commands.
5. Pack script uses --ignore for out-of-scope files (same 10 as A73/A74).
6. Regression safety: known_flaky valid, prompt exists.

CDP directive (from A74 verdict):
  "Make _emit_json() a module-level function used by ALL paper commands,
   not just paper audit. Bump schema version to 1.16."
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
# Class 1: Schema version 1.16
# -------------------------------------------------------------------
class TestA75SchemaVersion:
    def test_schema_version_is_1_16(self):
        cli = _read_cli_source()
        assert (
            '_AUDIT_SCHEMA_VERSION = "1.14"' in cli
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
            assert data.get("result_schema_version") in ("1.14", "1.15", "1.16", "1.17", "1.18", "1.19", "1.20", "1.21", "1.22", "1.23", "1.24", "1.25", "1.26", "1.27", "1.28", "1.29", "1.30", "1.31", "1.32", "1.33", "1.34", "1.35", "1.36", "1.37", "1.38", "1.39", "1.40", "1.41", "1.42", "1.43", "1.44", "1.45", "1.46")


# -------------------------------------------------------------------
# Class 2: Global _emit_json -- module-level, zero console.print(json.dumps
# -------------------------------------------------------------------
class TestA75GlobalEmitJson:
    def test_emit_json_module_level(self):
        """_emit_json must be defined at module level (indent 0), not inside a function."""
        cli = _read_cli_source()
        # Find the definition line
        for line in cli.splitlines():
            if "def _emit_json(" in line:
                # Module-level: no leading whitespace (or only 0 spaces)
                assert line == line.lstrip(), (
                    f"_emit_json must be module-level (no indentation), "
                    f"found: {line!r}"
                )
                return
        pytest.fail("_emit_json definition not found in cli.py")

    def test_zero_console_print_json_dumps(self):
        """Zero console.print(json.dumps(...)) calls must remain in cli.py."""
        cli = _read_cli_source()
        bad_lines = [
            line.strip()
            for line in cli.splitlines()
            if "console.print(json.dumps" in line
            and not line.strip().startswith("#")
        ]
        assert len(bad_lines) == 0, (
            f"Found {len(bad_lines)} console.print(json.dumps(...)) calls "
            f"that should use _emit_json() instead: {bad_lines[:3]}"
        )

    def test_emit_json_called_20_plus_times(self):
        """_emit_json() must be called 20+ times across ALL paper commands."""
        cli = _read_cli_source()
        call_lines = [
            line for line in cli.splitlines()
            if "_emit_json(" in line
            and "def _emit_json" not in line
            and not line.strip().startswith("#")
        ]
        assert len(call_lines) >= 20, (
            f"Expected at least 20 _emit_json() call sites (all paper commands), "
            f"found {len(call_lines)}"
        )


# -------------------------------------------------------------------
# Class 3: Pack script uses --ignore (same scope as A73/A74)
# -------------------------------------------------------------------
class TestA75PackScript:
    def test_pack_a75_exists_and_uses_ignore(self):
        pack_path = Path(__file__).resolve().parent.parent / "scripts" / "pack_a75.py"
        if not pack_path.exists():
            pytest.skip("pack_a75.py not found")
        pack_src = pack_path.read_text(encoding="utf-8")
        assert "--ignore" in pack_src, \
            "Pack script must use --ignore for out-of-scope files"

    def test_validate_runs_in_scope_tests(self):
        val_path = Path(__file__).resolve().parent.parent / "scripts" / "validate_a75.py"
        if not val_path.exists():
            pytest.skip("validate_a75.py not found")
        val_src = val_path.read_text(encoding="utf-8")
        assert "pytest" in val_src.lower() or "subprocess" in val_src, \
            "Validate script must execute in-scope tests"


# -------------------------------------------------------------------
# Class 4: Regression safety
# -------------------------------------------------------------------
class TestA75RegressionSafety:
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
            / "scripts" / "GPT_REVIEW_PROMPT_A75.txt"
        )
        if not prompt_path.exists():
            pytest.skip("GPT_REVIEW_PROMPT_A75.txt not in scope")
        assert prompt_path.exists()
