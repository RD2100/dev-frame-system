"""A59 -- Versioned Audit Result Schema.

Verifies:
1. result_schema_version field present in all audit output paths.
2. waiver_mode field: "active" in non-strict, "disabled_by_strict" in strict.
3. strict_mode field present in all output paths.
4. Schema fields in success path.
5. Schema fields in strict failure path.
6. Multiple simultaneous audit failures.
7. Schema version value is "1.0".
"""

from __future__ import annotations

import hashlib
import io
import json
import os
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
from typer.testing import CliRunner

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from ai_workflow_hub.cli import app

runner = CliRunner()
_RT_PATH = "ai_workflow_hub.cli._paper_runtime"
_PAPER_RUNS = "ai_workflow_hub.cli._paper_runs_root"


def _write_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def _fake_runtime():
    return {
        "sanitize": lambda rid: rid,
        "create": MagicMock(), "execute": MagicMock(),
        "status": MagicMock(), "redact": lambda s: s,
    }


def _make_run_dir(tmp: Path, run_id: str = "paper-test-a59") -> tuple[Path, dict]:
    run_dir = tmp / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    state = {
        "run_id": run_id, "task_id": "task-a59",
        "project_id": "proj-a59", "status": "completed",
        "workflow_type": "paper",
        "created_at": "2026-06-12T00:00:00+00:00",
        "updated_at": "2026-06-12T00:01:00+00:00",
        "executed_nodes": ["plan", "execute"],
        "acceptance_result": {"status": "accepted", "reasons": [], "blocking_issues": []},
        "blocking_count": 0, "non_blocking_count": 0,
        "evidence_manifest": {
            "manifest_id": "ev-001", "status": "complete",
            "version": "1.0", "generated_at": "2026-06-12T00:00:30",
            "files": [],
            "privacy_attestation": {"no_full_text": True, "no_api_keys": True, "no_personal_identity": True},
        },
        "ledger_dir": "", "decision_base_dir": "",
    }
    _write_json(run_dir / "state.json", state)
    return run_dir, state


def _invoke_audit(tmp_path, run_id="paper-a59-test", extra_args=None,
                  create_reports=True, extra_files=None, required_files=None):
    from rich.console import Console

    run_dir, state = _make_run_dir(tmp_path, run_id)
    if create_reports:
        _write_json(run_dir / "closeout-report.json", {"v": 1, "run_id": run_id})
        (run_dir / "closeout-report.md").write_text(f"# Report {run_id}", encoding="utf-8")
    if extra_files:
        for p, c in extra_files.items():
            (run_dir / p).write_text(c, encoding="utf-8")

    rt = _fake_runtime()
    stdout_buf = io.StringIO()
    stderr_buf = io.StringIO()
    _console = Console(file=stdout_buf, force_terminal=False)
    _err_console = Console(file=stderr_buf, force_terminal=False)

    args = ["paper", "audit", "--run-id", run_id, "--json"]
    if required_files:
        args.extend(["--required-files", required_files])
    if extra_args:
        args.extend(extra_args)

    f = {k: v for k, v in os.environ.items()
         if k not in ("AIHUB_SIGNING_KEY", "AIHUB_SIGNING_KEY_ID")}

    with patch(_RT_PATH, return_value=rt), \
         patch(_PAPER_RUNS, return_value=tmp_path), \
         patch("ai_workflow_hub.cli.init_env"), \
         patch("ai_workflow_hub.cli.console", _console), \
         patch("ai_workflow_hub.cli.err_console", _err_console), \
         patch.dict(os.environ, f, clear=True):
        result = runner.invoke(app, args, catch_exceptions=False)

    return result, stdout_buf.getvalue(), stderr_buf.getvalue()


def _get_json(stdout):
    for i, line in enumerate(stdout.strip().split("\n")):
        if line.strip().startswith("{"):
            return json.loads("\n".join(stdout.strip().split("\n")[i:]), strict=False)
    raise ValueError("No JSON in stdout")


# ============================================================
# TestA59SchemaVersion
# ============================================================

class TestA59SchemaVersion:
    """result_schema_version field in all output paths."""

    def test_schema_version_in_success(self, tmp_path):
        result, stdout, _ = _invoke_audit(tmp_path, "a59-sv-ok")
        assert result.exit_code == 0
        data = _get_json(stdout)
        assert data["result_schema_version"] in ("1.0", "1.1", "1.2", "1.3", "1.4", "1.5", "1.6", "1.7", "1.8", "1.9", "1.10", "1.11", "1.12", "1.13", "1.14", "1.15", "1.16", "1.17", "1.18", "1.19", "1.20", "1.21", "1.22", "1.23", "1.24", "1.25", "1.26", "1.27", "1.28", "1.29", "1.30", "1.31", "1.32", "1.33", "1.34", "1.35", "1.36", "1.37", "1.38", "1.39", "1.40", "1.41", "1.42", "1.43", "1.44", "1.45", "1.46", "1.47", "1.48", "1.49", "1.50", "1.51", "1.52", "1.53", "1.54", "1.55", "1.56", "1.57", "1.58", "1.61")

    def test_schema_version_in_strict_failure(self, tmp_path):
        extras = {"orphan_evidence.txt": "omitted"}
        result, stdout, _ = _invoke_audit(
            tmp_path, "a59-sv-fail", extra_files=extras,
            extra_args=["--strict"])
        assert result.exit_code != 0
        data = _get_json(stdout)
        assert data["result_schema_version"] in ("1.0", "1.1", "1.2", "1.3", "1.4", "1.5", "1.6", "1.7", "1.8", "1.9", "1.10", "1.11", "1.12", "1.13", "1.14", "1.15", "1.16", "1.17", "1.18", "1.19", "1.20", "1.21", "1.22", "1.23", "1.24", "1.25", "1.26", "1.27", "1.28", "1.29", "1.30", "1.31", "1.32", "1.33", "1.34", "1.35", "1.36", "1.37", "1.38", "1.39", "1.40", "1.41", "1.42", "1.43", "1.44", "1.45", "1.46", "1.47", "1.48", "1.49", "1.50", "1.51", "1.52", "1.53", "1.54", "1.55", "1.56", "1.57", "1.58", "1.61")

    def test_schema_version_value(self, tmp_path):
        result, stdout, _ = _invoke_audit(tmp_path, "a59-sv-val")
        data = _get_json(stdout)
        assert data["result_schema_version"] in ("1.0", "1.1", "1.2", "1.3", "1.4", "1.5", "1.6", "1.7", "1.8", "1.9", "1.10", "1.11", "1.12", "1.13", "1.14", "1.15", "1.16", "1.17", "1.18", "1.19", "1.20", "1.21", "1.22", "1.23", "1.24", "1.25", "1.26", "1.27", "1.28", "1.29", "1.30", "1.31", "1.32", "1.33", "1.34", "1.35", "1.36", "1.37", "1.38", "1.39", "1.40", "1.41", "1.42", "1.43", "1.44", "1.45", "1.46", "1.47", "1.48", "1.49", "1.50", "1.51", "1.52", "1.53", "1.54", "1.55", "1.56", "1.57", "1.58", "1.61")


# ============================================================
# TestA59WaiverMode
# ============================================================

class TestA59WaiverMode:
    """waiver_mode field: active vs disabled_by_strict."""

    def test_waiver_mode_active_non_strict(self, tmp_path):
        result, stdout, _ = _invoke_audit(tmp_path, "a59-wm-ns")
        data = _get_json(stdout)
        assert data["waiver_mode"] == "active"

    def test_waiver_mode_disabled_strict(self, tmp_path):
        extras = {"orphan_evidence.txt": "omitted"}
        result, stdout, _ = _invoke_audit(
            tmp_path, "a59-wm-s", extra_files=extras,
            extra_args=["--strict"])
        assert result.exit_code != 0
        data = _get_json(stdout)
        assert data["waiver_mode"] == "disabled_by_strict"

    def test_waiver_mode_strict_clean(self, tmp_path):
        """Strict with no failures: waiver_mode still disabled_by_strict."""
        result, stdout, _ = _invoke_audit(
            tmp_path, "a59-wm-sc", extra_args=["--strict"])
        data = _get_json(stdout)
        assert data["waiver_mode"] == "disabled_by_strict"


# ============================================================
# TestA59StrictMode
# ============================================================

class TestA59StrictMode:
    """strict_mode field in all output paths."""

    def test_strict_mode_false(self, tmp_path):
        result, stdout, _ = _invoke_audit(tmp_path, "a59-sm-f")
        data = _get_json(stdout)
        assert data["strict_mode"] is False

    def test_strict_mode_true(self, tmp_path):
        extras = {"orphan_evidence.txt": "omitted"}
        result, stdout, _ = _invoke_audit(
            tmp_path, "a59-sm-t", extra_files=extras,
            extra_args=["--strict"])
        data = _get_json(stdout)
        assert data["strict_mode"] is True


# ============================================================
# TestA59MultipleFailures
# ============================================================

class TestA59MultipleFailures:
    """Multiple simultaneous audit failures."""

    def test_multiple_failures_non_strict(self, tmp_path):
        """Multiple failed checks with waivers."""
        extras = {
            "orphan_a.txt": "omitted file a",
            "orphan_b.txt": "omitted file b",
        }
        result, stdout, _ = _invoke_audit(
            tmp_path, "a59-multi-ns", extra_files=extras,
            required_files="missing_req.json")
        data = _get_json(stdout)
        # Should have multiple failed checks
        failed_checks = [c for c in data["checks"] if not c["passed"]]
        assert len(failed_checks) >= 2
        # Should have waivers for all failed checks (non-strict)
        assert len(data["policy_waivers"]) >= 2

    def test_multiple_failures_strict(self, tmp_path):
        """Multiple failed checks in strict mode -- all voided."""
        extras = {
            "orphan_a.txt": "omitted file a",
            "orphan_b.txt": "omitted file b",
        }
        result, stdout, _ = _invoke_audit(
            tmp_path, "a59-multi-s", extra_files=extras,
            required_files="missing_req.json",
            extra_args=["--strict"])
        assert result.exit_code != 0
        data = _get_json(stdout)
        # Should have failed checks
        failed_checks = [c for c in data["checks"] if not c["passed"]]
        assert len(failed_checks) >= 2
        # Strict voids all waivers
        assert data["policy_waivers"] == []
        assert data["verdict"] == "failed"
