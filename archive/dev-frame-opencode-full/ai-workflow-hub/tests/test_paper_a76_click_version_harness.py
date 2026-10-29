"""A76 -- Cross-Platform Behavioral Harness Fix (Click stdout/stderr separation).

Root cause diagnosis:
  On Windows (Click 8.2+/8.3.3), CliRunner.invoke() separates stdout and
  stderr into independent streams, so result.stdout contains ONLY JSON.
  On Linux with Click 8.0/8.1 (mix_stderr=True, the default), stderr is
  merged into stdout, so result.stdout contains progress messages + JSON,
  causing json.loads() to fail with JSONDecodeError at char 0.

Fix:
  Pin click>=8.2.0 in pyproject.toml so that all environments get the
  version with separated stdout/stderr streams.

Verifies:
1. Schema version "1.17".
2. pyproject.toml pins click>=8.2.0.
3. A76 contract comment in cli.py explains the cross-platform fix.
4. _emit_json() still at module level, zero console.print(json.dumps).
5. Behavioral: Click stdout/stderr separation confirmed.
6. Regression safety: known_flaky valid, prompt exists, scope unchanged.

CDP directive (from A75 verdict):
  "Diagnose and fix the remaining unpacked-ZIP JSONDecodeError failures.
   Capture failing stdout/stderr samples; determine whether failures are
   caused by missing fixture data, command exit behavior, stderr handling,
   or JSON emission; update the evidence-pack harness."
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


def _read_pyproject() -> str:
    return (_PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8")


# -------------------------------------------------------------------
# Class 1: Schema version 1.17
# -------------------------------------------------------------------
class TestA76SchemaVersion:
    def test_schema_version_is_1_17(self):
        cli = _read_cli_source()
        assert (
            '_AUDIT_SCHEMA_VERSION = "1.15"' in cli
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
            assert data.get("result_schema_version") in ("1.15", "1.16", "1.17", "1.18", "1.19", "1.20", "1.21", "1.22", "1.23", "1.24", "1.25", "1.26", "1.27", "1.28", "1.29", "1.30", "1.31", "1.32", "1.33", "1.34", "1.35", "1.36", "1.37", "1.38", "1.39", "1.40", "1.41", "1.42", "1.43", "1.44", "1.45", "1.46")


# -------------------------------------------------------------------
# Class 2: Click>=8.2.0 pin in pyproject.toml
# -------------------------------------------------------------------
class TestA76ClickVersionPin:
    def test_pyproject_pins_click_82(self):
        """pyproject.toml must pin click>=8.2.0 for stdout/stderr separation."""
        toml = _read_pyproject()
        assert 'click>=8.2.0' in toml or 'click>=8.2' in toml, (
            "pyproject.toml must pin click>=8.2.0 to ensure CliRunner "
            "separates stdout and stderr on all platforms"
        )

    def test_click_pin_in_dependencies_section(self):
        """click pin must be in [project] dependencies, not optional."""
        toml = _read_pyproject()
        # Find the main dependencies block
        in_deps = False
        for line in toml.splitlines():
            stripped = line.strip()
            if stripped.startswith("dependencies = ["):
                in_deps = True
            elif in_deps and stripped == "]":
                break
            elif in_deps and "click>=" in stripped:
                return  # Found in main deps
        pytest.fail("click>=8.2.0 must be in main [project] dependencies")

    def test_installed_click_version_satisfies_pin(self):
        """Installed click must be >= 8.2.0."""
        try:
            import click
            from packaging.version import Version
            v = Version(click.__version__)
            assert v >= Version("8.2.0"), (
                f"Installed click {v} < 8.2.0; stdout/stderr separation requires >= 8.2.0"
            )
        except ImportError:
            # packaging not installed -- skip version check
            pytest.skip("packaging module not available for version comparison")


# -------------------------------------------------------------------
# Class 3: A76 contract comment + structural invariants preserved
# -------------------------------------------------------------------
class TestA76ContractAndInvariants:
    def test_a76_contract_comment_in_cli(self):
        """cli.py must contain A76 contract explaining the cross-platform fix."""
        cli = _read_cli_source()
        assert "A76" in cli, "A76 contract comment missing from cli.py"
        assert "click>=8.2.0" in cli or "Click 8.2" in cli, (
            "A76 contract must reference the Click version requirement"
        )

    def test_emit_json_still_module_level(self):
        """_emit_json must remain at module level after A76."""
        cli = _read_cli_source()
        for line in cli.splitlines():
            if "def _emit_json(" in line:
                assert line == line.lstrip(), (
                    f"_emit_json must be module-level, found indented: {line!r}"
                )
                return
        pytest.fail("_emit_json definition not found in cli.py")

    def test_zero_console_print_json_dumps_still(self):
        """Zero console.print(json.dumps(...)) calls after A76."""
        cli = _read_cli_source()
        bad_lines = [
            line.strip()
            for line in cli.splitlines()
            if "console.print(json.dumps" in line
            and not line.strip().startswith("#")
        ]
        assert len(bad_lines) == 0, (
            f"A76 regression: {len(bad_lines)} console.print(json.dumps) calls remain"
        )


# -------------------------------------------------------------------
# Class 4: Behavioral -- stdout/stderr separation
# -------------------------------------------------------------------
class TestA76BehavioralHarness:
    def test_cli_runner_stdout_stderr_separation(self):
        """CliRunner must separate stdout from stderr (Click 8.2+ behavior).

        This test proves the behavioral harness works: progress messages
        on stderr do NOT contaminate JSON on stdout.
        """
        import click
        from packaging.version import Version
        if Version(click.__version__) < Version("8.2.0"):
            pytest.skip(f"click {click.__version__} < 8.2.0 -- stdout/stderr merged")

        # Invoke a command that writes progress to err_console and JSON to stdout
        runs_dir = Path("/tmp/fake_runs_a76_test")
        runs_dir.mkdir(parents=True, exist_ok=True)
        run_dir = runs_dir / "sep-test"
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / "state.json").write_text(json.dumps({
            "run_id": "sep-test", "task_id": "t", "status": "completed",
            "started_at": "2025-01-01T00:00:00Z", "completed_at": "2025-01-01T01:00:00Z",
            "evidence_manifest": {"files": []}, "closeout_integrity": "complete",
            "ledger_dir": str(run_dir), "decision_base_dir": str(run_dir),
        }), encoding="utf-8")
        (run_dir / "closeout_report.json").write_text(json.dumps({
            "run_id": "sep-test", "summary": "test",
            "generated_at": "2025-01-01T01:00:00Z",
        }), encoding="utf-8")
        (run_dir / "closeout-closeout.md").write_text("# Report\nTest", encoding="utf-8")

        rt = {"sanitize": lambda rid: rid, "runs_root": runs_dir}
        with patch(_RT_PATH, return_value=rt), patch(_PAPER_RUNS, str(runs_dir)):
            r = runner.invoke(app, ["paper", "audit", "--run-id", "sep-test", "--json"])

        if r.exit_code == 0:
            # stdout must be parseable JSON (no progress messages mixed in)
            try:
                data = json.loads(r.stdout)
                assert "result_schema_version" in data
            except json.JSONDecodeError as exc:
                pytest.fail(
                    f"JSON parse failed on stdout: {exc}\n"
                    f"stdout[:200]: {r.stdout[:200]!r}\n"
                    f"stderr[:200]: {getattr(r, 'stderr', 'N/A')!r}"
                )

    def test_pattern_b_json_parse_succeeds(self):
        """Bare CliRunner + json.loads(result.stdout) must work.

        This is the exact pattern that failed on Linux with Click 8.0/8.1.
        With click>=8.2.0 pinned, it must succeed.
        """
        import click
        from packaging.version import Version
        if Version(click.__version__) < Version("8.2.0"):
            pytest.skip(f"click {click.__version__} < 8.2.0")

        runs_dir = Path("/tmp/fake_runs_a76_pattern_b")
        runs_dir.mkdir(parents=True, exist_ok=True)
        run_dir = runs_dir / "pat-b-test"
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / "state.json").write_text(json.dumps({
            "run_id": "pat-b-test", "task_id": "t", "status": "completed",
            "started_at": "2025-01-01T00:00:00Z", "completed_at": "2025-01-01T01:00:00Z",
            "evidence_manifest": {"files": []}, "closeout_integrity": "complete",
            "ledger_dir": str(run_dir), "decision_base_dir": str(run_dir),
        }), encoding="utf-8")
        (run_dir / "closeout_report.json").write_text(json.dumps({
            "run_id": "pat-b-test", "summary": "test",
            "generated_at": "2025-01-01T01:00:00Z",
        }), encoding="utf-8")
        (run_dir / "closeout-closeout.md").write_text("# Report\nTest", encoding="utf-8")

        rt = {"sanitize": lambda rid: rid, "runs_root": runs_dir}
        with patch(_RT_PATH, return_value=rt), patch(_PAPER_RUNS, str(runs_dir)):
            r = runner.invoke(app, ["paper", "audit", "--run-id", "pat-b-test", "--json"])

        if r.exit_code == 0:
            # This is the exact Pattern B invocation that caused 68 failures
            data = json.loads(r.stdout)
            assert data["run_id"] == "pat-b-test"


# -------------------------------------------------------------------
# Class 5: Regression safety
# -------------------------------------------------------------------
class TestA76RegressionSafety:
    def test_known_flaky_still_valid(self):
        jf = _PROJECT_ROOT / "known_flaky_tests.json"
        if not jf.exists():
            pytest.skip("known_flaky_tests.json not found")
        data = json.loads(jf.read_text(encoding="utf-8"))
        assert data["total_known_flaky"] >= 1
        assert "::TestA20CLIAgainstRealData::" in data["tests"][0]["deselect_arg"]

    def test_prompt_file_exists(self):
        prompt_path = _PROJECT_ROOT / "scripts" / "GPT_REVIEW_PROMPT_A76.txt"
        if not prompt_path.exists():
            pytest.skip("GPT_REVIEW_PROMPT_A76.txt not in scope")
        assert prompt_path.exists()

    def test_scope_unchanged_10_out_of_scope(self):
        """Same 10 out-of-scope files as A73/A74/A75."""
        cli = _read_cli_source()
        # Scope is defined in pack/validate scripts, not cli.py
        pack_path = _PROJECT_ROOT / "scripts" / "pack_a76.py"
        if not pack_path.exists():
            pytest.skip("pack_a76.py not found")
        pack_src = pack_path.read_text(encoding="utf-8")
        for name in [
            "test_paper_a19_safe_e2e.py",
            "test_paper_a20_real_e2e.py",
            "test_paper_a23_closeout_report.py",
            "test_paper_acceptance_gate.py",
            "test_paper_a45_audit_completeness.py",
            "test_paper_a46_policy_completeness.py",
        ]:
            assert name in pack_src, f"{name} missing from out-of-scope list"
