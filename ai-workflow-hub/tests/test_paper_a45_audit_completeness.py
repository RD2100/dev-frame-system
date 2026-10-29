"""A45 -- Audit Completeness Proof (--completeness-check).

Verifies:
1. --completeness-check option exists on paper audit command
2. Completeness passes when all run files are included in the bundle
3. Completeness detects files missing from the bundle
4. JSON output includes completeness field with correct structure
5. --completeness-check integrates with --strict mode
6. Backward compatibility: audit works without --completeness-check
"""

import hashlib
import json
import os
from pathlib import Path

import pytest
from typer.testing import CliRunner
from unittest.mock import patch

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from ai_workflow_hub.cli import app

runner = CliRunner()


def _make_state(run_id="test-a45"):
    """Return a minimal valid paper run state dict."""
    return {
        "run_id": run_id,
        "task_id": "",
        "evidence_manifest": {"files": []},
        "ledger_dir": "",
        "decision_base_dir": "",
        "closeout_integrity": "complete",
    }


def _make_run_dir(tmp_path, run_id="test-a45", extra_files=None):
    """Create a mock paper run directory with required files.

    Returns (state_dict, run_dir_path).
    """
    rd = tmp_path / "runs" / run_id
    rd.mkdir(parents=True, exist_ok=True)

    state = _make_state(run_id)
    (rd / "state.json").write_text(json.dumps(state), encoding="utf-8")
    (rd / "closeout-report.json").write_text(
        json.dumps({"run_id": run_id, "status": "complete"}),
        encoding="utf-8",
    )
    (rd / "closeout-report.md").write_text(
        f"# Closeout Report: {run_id}",
        encoding="utf-8",
    )

    if extra_files:
        for name, content in extra_files.items():
            fpath = rd / name
            fpath.parent.mkdir(parents=True, exist_ok=True)
            fpath.write_text(content, encoding="utf-8")

    return state, rd


def _invoke_audit(run_id, output_zip, completeness=False,
                  as_json=False, strict=False):
    """Build and invoke 'paper audit' with given flags."""
    args = [
        "paper", "audit",
        "--run-id", run_id,
        "--output", str(output_zip),
    ]
    if completeness:
        args.append("--completeness-check")
    if as_json:
        args.append("--json")
    if strict:
        args.append("--strict")
    return runner.invoke(app, args)


# ============================================================
# TestA45CompletenessOption
# ============================================================

class TestA45CompletenessOption:
    """--completeness-check option on paper audit command."""

    def test_completeness_check_option_exists(self):
        """--completeness-check is recognized as a valid option."""
        result = runner.invoke(app, ["paper", "audit", "--help"])
        assert result.exit_code == 0
        combined = (result.stdout or "") + (result.stderr or "")
        assert "--completeness-check" in combined

    def test_completeness_passes_complete_run(self, tmp_path):
        """All run directory files present in bundle -> PASSED."""
        run_id = "test-a45-complete"
        state, rd = _make_run_dir(tmp_path, run_id)
        output_zip = str(tmp_path / "bundle-output.zip")

        with patch("ai_workflow_hub.cli._load_run_state",
                   return_value=(state, rd)):
            result = _invoke_audit(
                run_id, output_zip, completeness=True,
            )

        assert result.exit_code == 0
        combined = (result.stdout or "") + (result.stderr or "")
        assert "Completeness: PASSED" in combined

    def test_completeness_detects_missing_files(self, tmp_path):
        """Extra files in run directory not in bundle -> detected as missing."""
        run_id = "test-a45-missing"
        state, rd = _make_run_dir(
            tmp_path, run_id,
            extra_files={"debug.log": "debug trace output line 1"},
        )
        output_zip = str(tmp_path / "bundle-output.zip")

        with patch("ai_workflow_hub.cli._load_run_state",
                   return_value=(state, rd)):
            result = _invoke_audit(
                run_id, output_zip, completeness=True,
            )

        combined = (result.stdout or "") + (result.stderr or "")
        assert "Completeness:" in combined
        # Should not be PASSED when files are missing
        assert "not in bundle" in combined or "Missing:" in combined


# ============================================================
# TestA45CompletenessJsonOutput
# ============================================================

class TestA45CompletenessJsonOutput:
    """JSON output includes completeness field when --completeness-check is set."""

    def test_json_includes_completeness_field(self, tmp_path):
        """JSON output with --completeness-check includes 'completeness' key."""
        run_id = "test-a45-json"
        state, rd = _make_run_dir(tmp_path, run_id)
        output_zip = str(tmp_path / "bundle-output.zip")

        with patch("ai_workflow_hub.cli._load_run_state",
                   return_value=(state, rd)):
            result = _invoke_audit(
                run_id, output_zip,
                completeness=True, as_json=True,
            )

        assert result.exit_code == 0
        data = json.loads(result.stdout, strict=False)
        assert "completeness" in data

    def test_completeness_report_structure(self, tmp_path):
        """Completeness report contains all required fields with correct types."""
        run_id = "test-a45-struct"
        state, rd = _make_run_dir(tmp_path, run_id)
        output_zip = str(tmp_path / "bundle-output.zip")

        with patch("ai_workflow_hub.cli._load_run_state",
                   return_value=(state, rd)):
            result = _invoke_audit(
                run_id, output_zip,
                completeness=True, as_json=True,
            )

        assert result.exit_code == 0
        data = json.loads(result.stdout, strict=False)
        comp = data["completeness"]

        # Required fields
        assert "total_run_files" in comp
        assert "total_bundle_files" in comp
        assert "required_present" in comp
        assert "missing_from_bundle" in comp
        assert "missing_count" in comp
        assert "complete" in comp

        # Type checks
        assert isinstance(comp["total_run_files"], int)
        assert isinstance(comp["total_bundle_files"], int)
        assert isinstance(comp["required_present"], bool)
        assert isinstance(comp["missing_from_bundle"], list)
        assert isinstance(comp["missing_count"], int)
        assert isinstance(comp["complete"], bool)


# ============================================================
# TestA45CompletenessIntegration
# ============================================================

class TestA45CompletenessIntegration:
    """Integration tests for --completeness-check with other options."""

    def test_full_completeness_workflow(self, tmp_path):
        """Full workflow: audit with --completeness-check --json produces
        valid JSON with completeness showing complete=True for a clean run.
        """
        run_id = "test-a45-full"
        state, rd = _make_run_dir(tmp_path, run_id)
        output_zip = str(tmp_path / "bundle-output.zip")

        with patch("ai_workflow_hub.cli._load_run_state",
                   return_value=(state, rd)):
            result = _invoke_audit(
                run_id, output_zip,
                completeness=True, as_json=True,
            )

        assert result.exit_code == 0
        data = json.loads(result.stdout, strict=False)

        # Completeness report present and shows complete
        assert "completeness" in data
        comp = data["completeness"]
        assert comp["complete"] is True
        assert comp["missing_count"] == 0
        assert comp["missing_from_bundle"] == []
        assert comp["required_present"] is True
        assert comp["total_bundle_files"] > 0

    def test_completeness_with_strict(self, tmp_path):
        """--completeness-check combined with --strict succeeds for clean run."""
        run_id = "test-a45-strict"
        state, rd = _make_run_dir(tmp_path, run_id)
        output_zip = str(tmp_path / "bundle-output.zip")

        with patch("ai_workflow_hub.cli._load_run_state",
                   return_value=(state, rd)):
            result = _invoke_audit(
                run_id, output_zip,
                completeness=True, strict=True,
            )

        assert result.exit_code == 0
        combined = (result.stdout or "") + (result.stderr or "")
        assert "Strict: PASSED" in combined
        assert "Completeness: PASSED" in combined


# ============================================================
# TestA45BackwardCompat
# ============================================================

class TestA45BackwardCompat:
    """Backward compatibility: audit works without --completeness-check."""

    def test_audit_works_without_completeness_check(self, tmp_path):
        """Audit without --completeness-check produces no completeness output."""
        run_id = "test-a45-compat"
        state, rd = _make_run_dir(tmp_path, run_id)
        output_zip = str(tmp_path / "bundle-output.zip")

        with patch("ai_workflow_hub.cli._load_run_state",
                   return_value=(state, rd)):
            result = _invoke_audit(
                run_id, output_zip,
                completeness=False, as_json=True,
            )

        assert result.exit_code == 0
        data = json.loads(result.stdout, strict=False)
        # Without --completeness-check, no completeness key in JSON
        assert "completeness" not in data
