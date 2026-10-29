"""A58 -- Audit Strict Result Consistency.

Verifies:
1. Strict-mode JSON includes audit result fields (checks, policy_waivers, verdicts).
2. Strict mode voids all waivers (policy_waivers=[]).
3. Strict mode verdict = raw_verdict (no waiver adjustment).
4. Non-strict mode preserves waiver-based verdict adjustment.
5. Verdict fields present in both strict-failure and success JSON.
6. waiver_integrity present in strict failure JSON.
7. adjusted_check_count is 0 in strict mode.
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


def _make_run_dir(tmp: Path, run_id: str = "paper-test-a58") -> tuple[Path, dict]:
    run_dir = tmp / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    state = {
        "run_id": run_id, "task_id": "task-a58",
        "project_id": "proj-a58", "status": "completed",
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


def _invoke_audit(tmp_path, run_id="paper-a58-test", extra_args=None,
                  create_reports=True, extra_files=None):
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
# TestA58StrictJsonConsistency
# ============================================================

class TestA58StrictJsonConsistency:
    """Strict-mode JSON includes A57 result fields."""

    def test_strict_json_has_checks(self, tmp_path):
        """Strict failure JSON should include checks array."""
        extras = {"orphan_evidence.txt": "omitted file"}
        result, stdout, _ = _invoke_audit(
            tmp_path, "a58-strict-checks", extra_files=extras,
            extra_args=["--strict"])
        # Strict with omitted evidence should fail
        assert result.exit_code != 0
        data = _get_json(stdout)
        assert "checks" in data

    def test_strict_json_has_verdict_fields(self, tmp_path):
        extras = {"orphan_evidence.txt": "omitted file"}
        result, stdout, _ = _invoke_audit(
            tmp_path, "a58-strict-verdict", extra_files=extras,
            extra_args=["--strict"])
        assert result.exit_code != 0
        data = _get_json(stdout)
        assert "raw_verdict" in data
        assert "policy_verdict" in data
        assert "verdict" in data

    def test_strict_json_has_waiver_integrity(self, tmp_path):
        extras = {"orphan_evidence.txt": "omitted file"}
        result, stdout, _ = _invoke_audit(
            tmp_path, "a58-strict-integrity", extra_files=extras,
            extra_args=["--strict"])
        assert result.exit_code != 0
        data = _get_json(stdout)
        assert "waiver_integrity" in data

    def test_strict_json_has_policy_waivers(self, tmp_path):
        extras = {"orphan_evidence.txt": "omitted file"}
        result, stdout, _ = _invoke_audit(
            tmp_path, "a58-strict-waivers", extra_files=extras,
            extra_args=["--strict"])
        assert result.exit_code != 0
        data = _get_json(stdout)
        assert "policy_waivers" in data


# ============================================================
# TestA58StrictVoidsWaivers
# ============================================================

class TestA58StrictVoidsWaivers:
    """Strict mode voids all waivers."""

    def test_strict_no_waivers(self, tmp_path):
        extras = {"orphan_evidence.txt": "omitted file"}
        result, stdout, _ = _invoke_audit(
            tmp_path, "a58-no-waivers", extra_files=extras,
            extra_args=["--strict"])
        assert result.exit_code != 0
        data = _get_json(stdout)
        assert data["policy_waivers"] == []

    def test_strict_verdict_equals_raw(self, tmp_path):
        extras = {"orphan_evidence.txt": "omitted file"}
        result, stdout, _ = _invoke_audit(
            tmp_path, "a58-raw-eq", extra_files=extras,
            extra_args=["--strict"])
        assert result.exit_code != 0
        data = _get_json(stdout)
        assert data["policy_verdict"] == data["raw_verdict"]
        assert data["verdict"] == data["raw_verdict"]

    def test_strict_adjusted_count_zero(self, tmp_path):
        extras = {"orphan_evidence.txt": "omitted file"}
        result, stdout, _ = _invoke_audit(
            tmp_path, "a58-adj-zero", extra_files=extras,
            extra_args=["--strict"])
        assert result.exit_code != 0
        data = _get_json(stdout)
        assert data["adjusted_check_count"] == 0

    def test_strict_waived_checks_empty(self, tmp_path):
        extras = {"orphan_evidence.txt": "omitted file"}
        result, stdout, _ = _invoke_audit(
            tmp_path, "a58-wc-empty", extra_files=extras,
            extra_args=["--strict"])
        assert result.exit_code != 0
        data = _get_json(stdout)
        assert data["policy_waived_checks"] == []


# ============================================================
# TestA58NonStrictPreservesWaivers
# ============================================================

class TestA58NonStrictPreservesWaivers:
    """Non-strict mode preserves waiver-based verdict adjustment."""

    def test_nonstrict_has_waivers(self, tmp_path):
        extras = {"orphan_evidence.txt": "omitted file"}
        result, stdout, _ = _invoke_audit(
            tmp_path, "a58-ns-waivers", extra_files=extras)
        assert result.exit_code == 0
        data = _get_json(stdout)
        assert len(data["policy_waivers"]) > 0

    def test_nonstrict_verdict_adjusted(self, tmp_path):
        extras = {"orphan_evidence.txt": "omitted file"}
        result, stdout, _ = _invoke_audit(
            tmp_path, "a58-ns-verdict", extra_files=extras)
        assert result.exit_code == 0
        data = _get_json(stdout)
        # raw_verdict should be "failed" (omitted evidence)
        assert data["raw_verdict"] == "failed"
        # policy_verdict should be "passed" (waiver adjusts it)
        assert data["policy_verdict"] == "passed"
        assert data["verdict"] == "passed"

    def test_nonstrict_clean_run(self, tmp_path):
        """Clean non-strict run should pass with no waivers."""
        result, stdout, _ = _invoke_audit(tmp_path, "a58-ns-clean")
        assert result.exit_code == 0
        data = _get_json(stdout)
        assert data["verdict"] == "passed"
        assert data["policy_waivers"] == []
        assert data["adjusted_check_count"] == 0
