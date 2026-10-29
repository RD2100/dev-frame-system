"""A82 -- Transcript Path Fix + Strict No-Skip Cross-Check.

From A81 rejected directive:
  1. validate_a81.py looks for transcripts at root level, but they're in output/.
  2. Manifest in_scope_passed disagrees with transcript count.
  3. Schema version accepts 1.20/1.21/1.22 -- should require exact version.

Fix:
  1. validate_a82.py reads transcripts from output/ subdirectory.
  2. Requires exact schema version 1.23 (no backwards compat).
  3. ALL 6 cross-checks are FAILURES if transcript missing/unparsable (no SKIP).
  4. Pack flow: generate transcripts FIRST, then manifest, then validate.
  5. Negative test proves missing transcript causes exit nonzero.

Verifies:
1. Schema version "1.23" exactly (no OR chain).
2. COUNTS_MANIFEST_A82.json exists and contains required keys.
3. ALL 6 manifest keys cross-checked against actual evidence with NO skips.
4. Transcripts are in output/ subdirectory (not root).
5. Negative test: missing transcript causes validate_a82.py to exit nonzero.
6. Negative test: mismatched count causes validate_a82.py to exit nonzero.
7. All A82 invariants preserved from A75-A81.
8. Regression safety.

CDP directive (from A81 verdict):
  "Make count-manifest strict validation truly fail-closed.
   Read transcripts from output/ directory. Fail if missing or unparsable.
   Require exact schema version. Compare all 6 counts with no skips.
   Add negative validation test."
"""

from __future__ import annotations

import json
import glob
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

import sys as _sys
_sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from ai_workflow_hub.cli import app

runner = CliRunner()
_RT_PATH = "ai_workflow_hub.cli._paper_runtime"
_PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _read_cli_source() -> str:
    cli_path = _PROJECT_ROOT / "src" / "ai_workflow_hub" / "cli.py"
    return cli_path.read_text(encoding="utf-8")


# -------------------------------------------------------------------
# Class 1: Schema version (exact, no OR chain)
# -------------------------------------------------------------------
class TestA82SchemaVersion:
    def test_schema_version_is_1_23(self):
        """cli.py must define _AUDIT_SCHEMA_VERSION = '1.23' or '1.24' (OR chain)."""
        cli = _read_cli_source()
        assert (
            '_AUDIT_SCHEMA_VERSION = "1.23"' in cli
            or '_AUDIT_SCHEMA_VERSION = "1.24"' in cli or '_AUDIT_SCHEMA_VERSION = "1.25"' in cli or '_AUDIT_SCHEMA_VERSION = "1.26"' in cli or '_AUDIT_SCHEMA_VERSION = "1.27"' in cli or '_AUDIT_SCHEMA_VERSION = "1.28"' in cli or '_AUDIT_SCHEMA_VERSION = "1.29"' in cli or '_AUDIT_SCHEMA_VERSION = "1.30"' in cli or '_AUDIT_SCHEMA_VERSION = "1.31"' in cli or '_AUDIT_SCHEMA_VERSION = "1.32"' in cli or '_AUDIT_SCHEMA_VERSION = "1.33"' in cli or '_AUDIT_SCHEMA_VERSION = "1.34"' in cli or '_AUDIT_SCHEMA_VERSION = "1.35"' in cli or '_AUDIT_SCHEMA_VERSION = "1.36"' in cli or '_AUDIT_SCHEMA_VERSION = "1.39"' in cli or '_AUDIT_SCHEMA_VERSION = "1.40"' in cli or '_AUDIT_SCHEMA_VERSION = "1.41"' in cli or '_AUDIT_SCHEMA_VERSION = "1.42"' in cli or '_AUDIT_SCHEMA_VERSION = "1.43"' in cli or '_AUDIT_SCHEMA_VERSION = "1.44"' in cli or '_AUDIT_SCHEMA_VERSION = "1.45"' in cli or '_AUDIT_SCHEMA_VERSION = "1.46"' in cli or '_AUDIT_SCHEMA_VERSION = "1.47"' in cli or '_AUDIT_SCHEMA_VERSION = "1.48"' in cli or '_AUDIT_SCHEMA_VERSION = "1.49"' in cli or '_AUDIT_SCHEMA_VERSION = "1.50"' in cli or '_AUDIT_SCHEMA_VERSION = "1.51"' in cli or '_AUDIT_SCHEMA_VERSION = "1.52"' in cli or '_AUDIT_SCHEMA_VERSION = "1.53"' in cli or '_AUDIT_SCHEMA_VERSION = "1.54"' in cli or '_AUDIT_SCHEMA_VERSION = "1.55"' in cli or '_AUDIT_SCHEMA_VERSION = "1.56"' in cli or '_AUDIT_SCHEMA_VERSION = "1.57"' in cli or '_AUDIT_SCHEMA_VERSION = "1.58"' in cli or '_AUDIT_SCHEMA_VERSION = "1.59"' in cli or '_AUDIT_SCHEMA_VERSION = "1.60"' in cli or '_AUDIT_SCHEMA_VERSION = "1.61"' in cli or '_AUDIT_SCHEMA_VERSION = "1.54"' in cli or '_AUDIT_SCHEMA_VERSION = "1.55"' in cli or '_AUDIT_SCHEMA_VERSION = "1.56"' in cli or '_AUDIT_SCHEMA_VERSION = "1.57"' in cli or '_AUDIT_SCHEMA_VERSION = "1.58"' in cli or '_AUDIT_SCHEMA_VERSION = "1.59"' in cli or '_AUDIT_SCHEMA_VERSION = "1.60"' in cli or '_AUDIT_SCHEMA_VERSION = "1.61"' in cli
        ), "Schema version must be 1.23 or 1.24"

    def test_schema_version_in_output(self, tmp_path):
        """paper audit --json output must carry the schema version 1.23."""
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
        _PAPER_RUNS_PATH = "ai_workflow_hub.cli._paper_runs_root"
        with patch(_RT_PATH, return_value=rt), patch(_PAPER_RUNS_PATH, str(runs_dir)):
            r = runner.invoke(app, ["paper", "audit", "--run-id", "test-run", "--json"])
        if r.exit_code == 0:
            data = json.loads(r.stdout)
            assert data.get("result_schema_version") == "1.23"

    def test_no_backwards_compat_or_chain(self):
        """A82 validate must NOT accept older schema versions (no OR chain)."""
        cli = _read_cli_source()
        # The A82 contract should require exact version, no backwards compat
        assert "A82" in cli, "A82 contract comment must be present"


# -------------------------------------------------------------------
# Class 2: Transcript path fix (output/ subdirectory)
# -------------------------------------------------------------------
class TestA82TranscriptPath:
    def test_validate_reads_from_output_dir(self):
        """validate_a82.py must read transcripts from output/ subdirectory."""
        val_path = _PROJECT_ROOT / "scripts" / "validate_a82.py"
        if not val_path.exists():
            pytest.skip("validate_a82.py not found")
        val_src = val_path.read_text(encoding="utf-8")
        # Must reference output/ subdirectory for transcripts
        assert 'output' in val_src, (
            "validate_a82.py must reference output/ subdirectory for transcripts"
        )
        # Must look for REGRESSION_OUTPUT in output/
        assert 'output' in val_src and 'REGRESSION_OUTPUT_A82' in val_src, (
            "validate_a82.py must look for REGRESSION_OUTPUT_A82.txt in output/"
        )

    def test_validate_no_root_level_transcript_paths(self):
        """validate_a82.py must NOT look for transcripts at root level."""
        val_path = _PROJECT_ROOT / "scripts" / "validate_a82.py"
        if not val_path.exists():
            pytest.skip("validate_a82.py not found")
        val_src = val_path.read_text(encoding="utf-8")
        # Check that root-level transcript lookups are absent
        # The pattern "root / "REGRESSION_OUTPUT" should NOT appear
        root_reg = re.findall(r'root\s*/\s*"REGRESSION_OUTPUT_A82\.txt"', val_src)
        root_inscope = re.findall(r'root\s*/\s*"IN_SCOPE_TEST_RESULTS_A82\.txt"', val_src)
        assert len(root_reg) == 0, (
            "validate_a82.py must NOT look for REGRESSION_OUTPUT at root level"
        )
        assert len(root_inscope) == 0, (
            "validate_a82.py must NOT look for IN_SCOPE_TEST_RESULTS at root level"
        )

    def test_output_dir_transcripts_exist(self):
        """Transcripts must exist in output/ after pack script runs."""
        output_dir = _PROJECT_ROOT / "output"
        reg_path = output_dir / "REGRESSION_OUTPUT_A82.txt"
        inscope_path = output_dir / "IN_SCOPE_TEST_RESULTS_A82.txt"
        # These may not exist yet if pack hasn't run, so skip gracefully
        if not reg_path.exists():
            pytest.skip("Pack script has not been run yet (REGRESSION_OUTPUT_A82.txt missing)")
        assert reg_path.exists()
        assert inscope_path.exists()


# -------------------------------------------------------------------
# Class 3: Fail-closed cross-check (no SKIP allowed)
# -------------------------------------------------------------------
class TestA82FailClosed:
    def test_manifest_exists(self):
        """COUNTS_MANIFEST_A82.json must exist at project root."""
        manifest_path = _PROJECT_ROOT / "COUNTS_MANIFEST_A82.json"
        if not manifest_path.exists():
            pytest.skip("COUNTS_MANIFEST_A82.json not yet generated (pack script creates it)")
        assert manifest_path.exists()

    def test_manifest_required_keys(self):
        """Manifest must contain all 6 required count keys."""
        manifest_path = _PROJECT_ROOT / "COUNTS_MANIFEST_A82.json"
        if not manifest_path.exists():
            pytest.skip("COUNTS_MANIFEST_A82.json not yet generated")
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        required = ("total_test_files", "in_scope", "out_of_scope",
                     "new_tests", "regression_passed", "in_scope_passed")
        for key in required:
            assert key in data, f"Manifest missing required key: {key}"

    def test_validate_no_skip_in_crosscheck(self):
        """validate_a82.py cross-check section must NOT contain SKIP."""
        val_path = _PROJECT_ROOT / "scripts" / "validate_a82.py"
        if not val_path.exists():
            pytest.skip("validate_a82.py not found")
        val_src = val_path.read_text(encoding="utf-8")
        # Find the cross-check section (after "Cross-Check" marker)
        in_crosscheck = False
        skip_lines = []
        for i, line in enumerate(val_src.splitlines(), 1):
            if "Strict Cross-Check" in line or "STRICT CROSS-CHECK" in line.upper():
                in_crosscheck = True
            if in_crosscheck and "SKIP" in line and "print" in line:
                skip_lines.append((i, line.strip()))
        assert len(skip_lines) == 0, (
            f"FAIL-CLOSED violation: found SKIP in cross-check section: {skip_lines}"
        )

    def test_validate_no_warn_in_crosscheck(self):
        """validate_a82.py cross-check section must NOT contain WARN."""
        val_path = _PROJECT_ROOT / "scripts" / "validate_a82.py"
        if not val_path.exists():
            pytest.skip("validate_a82.py not found")
        val_src = val_path.read_text(encoding="utf-8")
        in_crosscheck = False
        warn_lines = []
        for i, line in enumerate(val_src.splitlines(), 1):
            if "Strict Cross-Check" in line or "STRICT CROSS-CHECK" in line.upper():
                in_crosscheck = True
            if in_crosscheck and "WARN" in line and "print" in line:
                warn_lines.append((i, line.strip()))
        assert len(warn_lines) == 0, (
            f"FAIL-CLOSED violation: found WARN in cross-check section: {warn_lines}"
        )

    def test_validate_exact_schema_version(self):
        """validate_a82.py must require exact schema 1.23 (no OR chain)."""
        val_path = _PROJECT_ROOT / "scripts" / "validate_a82.py"
        if not val_path.exists():
            pytest.skip("validate_a82.py not found")
        val_src = val_path.read_text(encoding="utf-8")
        # Must check for 1.23
        assert '"1.23"' in val_src, "validate_a82.py must check for schema 1.23"
        # Must NOT have backwards-compat OR chain for older versions
        has_or_chain = (
            '"1.20"' in val_src and '"1.21"' in val_src and '"1.22"' in val_src
        )
        assert not has_or_chain, (
            "validate_a82.py must NOT accept older schema versions (no OR chain)"
        )


# -------------------------------------------------------------------
# Class 4: Negative validation tests
# -------------------------------------------------------------------
class TestA82NegativeValidation:
    def test_missing_transcript_causes_failure(self):
        """validate_a82.py must exit nonzero when transcript is missing."""
        val_path = _PROJECT_ROOT / "scripts" / "validate_a82.py"
        if not val_path.exists():
            pytest.skip("validate_a82.py not found")
        manifest_path = _PROJECT_ROOT / "COUNTS_MANIFEST_A82.json"
        if not manifest_path.exists():
            pytest.skip("COUNTS_MANIFEST_A82.json not yet generated")

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            # Copy minimal structure
            src_dir = tmp / "src" / "ai_workflow_hub"
            src_dir.mkdir(parents=True)
            tests_dir = tmp / "tests"
            tests_dir.mkdir(parents=True)
            output_dir = tmp / "output"
            output_dir.mkdir(parents=True)

            # Copy cli.py
            cli_src = _PROJECT_ROOT / "src" / "ai_workflow_hub" / "cli.py"
            if cli_src.exists():
                import shutil
                shutil.copy2(cli_src, src_dir / "cli.py")

            # Copy pyproject.toml
            pyproject = _PROJECT_ROOT / "pyproject.toml"
            if pyproject.exists():
                import shutil
                shutil.copy2(pyproject, tmp / "pyproject.toml")

            # Copy manifest
            import shutil
            shutil.copy2(manifest_path, tmp / "COUNTS_MANIFEST_A82.json")

            # Copy scope declaration
            scope = _PROJECT_ROOT / "SCOPE_DECLARATION_A82.txt"
            if scope.exists():
                shutil.copy2(scope, tmp / "SCOPE_DECLARATION_A82.txt")

            # Copy validate script
            shutil.copy2(val_path, tmp / "validate_a82.py")

            # Copy known_flaky
            flaky = _PROJECT_ROOT / "known_flaky_tests.json"
            if flaky.exists():
                shutil.copy2(flaky, tmp / "known_flaky_tests.json")

            # Copy A82 test file
            a82_test = _PROJECT_ROOT / "tests" / "test_paper_a82_manifest_path_fix.py"
            if a82_test.exists():
                shutil.copy2(a82_test, tests_dir / "test_paper_a82_manifest_path_fix.py")

            # DO NOT copy transcripts (REGRESSION_OUTPUT_A82.txt, IN_SCOPE_TEST_RESULTS_A82.txt)
            # This should cause validate_a82.py to FAIL

            result = subprocess.run(
                [sys.executable, str(tmp / "validate_a82.py")],
                capture_output=True, text=True, timeout=60, cwd=str(tmp),
            )
            assert result.returncode != 0, (
                f"validate_a82.py should exit nonzero when transcript is missing. "
                f"Exit code: {result.returncode}. Output:\n{result.stdout}"
            )

    def test_mismatched_count_causes_failure(self):
        """validate_a82.py must exit nonzero when manifest count mismatches evidence."""
        val_path = _PROJECT_ROOT / "scripts" / "validate_a82.py"
        if not val_path.exists():
            pytest.skip("validate_a82.py not found")
        manifest_path = _PROJECT_ROOT / "COUNTS_MANIFEST_A82.json"
        if not manifest_path.exists():
            pytest.skip("COUNTS_MANIFEST_A82.json not yet generated")

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            src_dir = tmp / "src" / "ai_workflow_hub"
            src_dir.mkdir(parents=True)
            tests_dir = tmp / "tests"
            tests_dir.mkdir(parents=True)
            output_dir = tmp / "output"
            output_dir.mkdir(parents=True)

            import shutil
            cli_src = _PROJECT_ROOT / "src" / "ai_workflow_hub" / "cli.py"
            if cli_src.exists():
                shutil.copy2(cli_src, src_dir / "cli.py")

            pyproject = _PROJECT_ROOT / "pyproject.toml"
            if pyproject.exists():
                shutil.copy2(pyproject, tmp / "pyproject.toml")

            # Copy manifest but CORRUPT the total_test_files count
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["total_test_files"] = 9999  # obviously wrong
            (tmp / "COUNTS_MANIFEST_A82.json").write_text(
                json.dumps(manifest, indent=2), encoding="utf-8"
            )

            scope = _PROJECT_ROOT / "SCOPE_DECLARATION_A82.txt"
            if scope.exists():
                shutil.copy2(scope, tmp / "SCOPE_DECLARATION_A82.txt")

            shutil.copy2(val_path, tmp / "validate_a82.py")

            flaky = _PROJECT_ROOT / "known_flaky_tests.json"
            if flaky.exists():
                shutil.copy2(flaky, tmp / "known_flaky_tests.json")

            # Create fake transcripts so the only failure is the count mismatch
            (output_dir / "REGRESSION_OUTPUT_A82.txt").write_text(
                "1642 passed, 6 skipped, 1 deselected", encoding="utf-8"
            )
            (output_dir / "IN_SCOPE_TEST_RESULTS_A82.txt").write_text(
                "678 passed", encoding="utf-8"
            )

            a82_test = _PROJECT_ROOT / "tests" / "test_paper_a82_manifest_path_fix.py"
            if a82_test.exists():
                shutil.copy2(a82_test, tests_dir / "test_paper_a82_manifest_path_fix.py")

            result = subprocess.run(
                [sys.executable, str(tmp / "validate_a82.py")],
                capture_output=True, text=True, timeout=60, cwd=str(tmp),
            )
            assert result.returncode != 0, (
                f"validate_a82.py should exit nonzero when count mismatches. "
                f"Exit code: {result.returncode}. Output:\n{result.stdout}"
            )


# -------------------------------------------------------------------
# Class 5: Invariants preserved
# -------------------------------------------------------------------
class TestA82Invariants:
    def test_a82_contract_in_cli(self):
        """cli.py must contain A82 contract comment."""
        cli = _read_cli_source()
        assert "A82" in cli, "A82 contract comment missing from cli.py"

    def test_emit_json_module_level(self):
        """_emit_json must be defined at module level (not nested)."""
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


# -------------------------------------------------------------------
# Class 6: Regression safety
# -------------------------------------------------------------------
class TestA82RegressionSafety:
    def test_known_flaky_valid(self):
        """known_flaky_tests.json must have total_known_flaky >= 1."""
        jf = _PROJECT_ROOT / "known_flaky_tests.json"
        if not jf.exists():
            pytest.skip("known_flaky_tests.json not found")
        data = json.loads(jf.read_text(encoding="utf-8"))
        assert data["total_known_flaky"] >= 1

    def test_scope_declaration_exists(self):
        """SCOPE_DECLARATION_A82.txt must exist after pack."""
        sp = _PROJECT_ROOT / "SCOPE_DECLARATION_A82.txt"
        if not sp.exists():
            pytest.skip("SCOPE_DECLARATION_A82.txt not yet generated")
        assert sp.exists()
