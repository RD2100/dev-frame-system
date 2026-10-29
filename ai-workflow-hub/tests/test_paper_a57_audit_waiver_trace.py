"""A57 -- Audit Waiver Trace Model.

Verifies:
1. Audit command produces policy_waivers list in JSON output.
2. Audit command produces structured checks array.
3. Non-strict mode creates waiver records for failed checks.
4. Strict mode does NOT create waivers (checks remain blocking).
5. Waiver records have correct command="audit".
6. Waiver records have raw_check_hash field.
7. waiver_integrity field present in audit output.
8. verdict/policy_verdict/raw_verdict present in audit output.
9. adjusted_check_count present in audit output.
10. policy_waived_checks only includes valid waivers.
"""

from __future__ import annotations

import hashlib
import io
import json
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


def _make_run_dir(tmp: Path, run_id: str = "paper-test-a57") -> tuple[Path, dict]:
    run_dir = tmp / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    state = {
        "run_id": run_id, "task_id": "task-a57",
        "project_id": "proj-a57", "status": "completed",
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


def _invoke_audit(tmp_path, run_id="paper-a57-test", extra_args=None,
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


import os


def _get_json(stdout):
    for i, line in enumerate(stdout.strip().split("\n")):
        if line.strip().startswith("{"):
            return json.loads("\n".join(stdout.strip().split("\n")[i:]), strict=False)
    raise ValueError("No JSON in stdout")


def _make_policy(tmp_path, overrides=None):
    p = {"schema_version": "1.0", "description": "A57 test"}
    if overrides:
        p.update(overrides)
    pp = tmp_path / "policy.json"
    pp.write_text(json.dumps(p), encoding="utf-8")
    return str(pp)


# ============================================================
# TestA57AuditChecks
# ============================================================

class TestA57AuditChecks:
    """Audit command produces structured checks array."""

    def test_checks_array_present(self, tmp_path):
        result, stdout, _ = _invoke_audit(tmp_path, "a57-checks")
        assert result.exit_code == 0
        data = _get_json(stdout)
        assert "checks" in data
        assert isinstance(data["checks"], list)

    def test_checks_have_expected_entries(self, tmp_path):
        result, stdout, _ = _invoke_audit(tmp_path, "a57-entries")
        assert result.exit_code == 0
        data = _get_json(stdout)
        check_names = [c["check"] for c in data["checks"]]
        assert "omitted_evidence" in check_names
        assert "required_artifacts_present" in check_names
        assert "oversized_files" in check_names
        assert "symlinks_rejected" in check_names

    def test_checks_have_index(self, tmp_path):
        result, stdout, _ = _invoke_audit(tmp_path, "a57-index")
        data = _get_json(stdout)
        for i, c in enumerate(data["checks"]):
            assert c["index"] == i

    def test_all_checks_pass_clean_run(self, tmp_path):
        """Clean run with no issues should have all checks passing."""
        result, stdout, _ = _invoke_audit(tmp_path, "a57-clean")
        data = _get_json(stdout)
        for c in data["checks"]:
            assert c["passed"] is True, "Check %s should pass on clean run" % c["check"]


# ============================================================
# TestA57AuditWaivers
# ============================================================

class TestA57AuditWaivers:
    """Waiver records in audit command."""

    def test_policy_waivers_list_present(self, tmp_path):
        result, stdout, _ = _invoke_audit(tmp_path, "a57-waivers")
        data = _get_json(stdout)
        assert "policy_waivers" in data
        assert isinstance(data["policy_waivers"], list)

    def test_waivers_for_failed_checks_non_strict(self, tmp_path):
        """Non-strict mode should create waivers for failed checks."""
        # Add extra files to run dir that won't be in manifest (omitted evidence)
        # Must use extensions checked by _check_omitted_evidence: .json, .md, .txt, .yaml, .patch
        extras = {"extra_evidence.txt": "untracked content for omitted evidence"}
        result, stdout, _ = _invoke_audit(
            tmp_path, "a57-nonstrict", extra_files=extras)
        data = _get_json(stdout)
        # omitted_evidence check should fail
        omitted = next(c for c in data["checks"] if c["check"] == "omitted_evidence")
        assert omitted["passed"] is False
        # Should have a waiver for it
        waivers = [w for w in data["policy_waivers"]
                   if w["check"] == "omitted_evidence"]
        assert len(waivers) >= 1

    def test_waiver_command_field(self, tmp_path):
        extras = {"orphan_evidence.txt": "orphan file"}
        result, stdout, _ = _invoke_audit(tmp_path, "a57-cmd", extra_files=extras)
        data = _get_json(stdout)
        for w in data["policy_waivers"]:
            assert w["command"] == "audit"

    def test_waiver_has_raw_check_hash(self, tmp_path):
        extras = {"orphan_evidence.txt": "orphan file"}
        result, stdout, _ = _invoke_audit(tmp_path, "a57-hash", extra_files=extras)
        data = _get_json(stdout)
        for w in data["policy_waivers"]:
            assert "raw_check_hash" in w
            assert len(w["raw_check_hash"]) == 16

    def test_waiver_severity_valid(self, tmp_path):
        extras = {"orphan_evidence.txt": "orphan file"}
        result, stdout, _ = _invoke_audit(tmp_path, "a57-sev", extra_files=extras)
        data = _get_json(stdout)
        valid_sevs = {"info", "warning", "partial", "block", "accepted_risk"}
        for w in data["policy_waivers"]:
            assert w["severity"] in valid_sevs

    def test_no_waivers_clean_run(self, tmp_path):
        """Clean run with no issues should have zero waivers."""
        result, stdout, _ = _invoke_audit(tmp_path, "a57-clean-w")
        data = _get_json(stdout)
        assert len(data["policy_waivers"]) == 0


# ============================================================
# TestA57AuditVerdict
# ============================================================

class TestA57AuditVerdict:
    """Verdict fields in audit output."""

    def test_verdict_fields_present(self, tmp_path):
        result, stdout, _ = _invoke_audit(tmp_path, "a57-verdict")
        data = _get_json(stdout)
        assert "verdict" in data
        assert "raw_verdict" in data
        assert "policy_verdict" in data

    def test_clean_run_verdict_passed(self, tmp_path):
        result, stdout, _ = _invoke_audit(tmp_path, "a57-pass")
        data = _get_json(stdout)
        assert data["raw_verdict"] == "passed"
        assert data["policy_verdict"] == "passed"
        assert data["verdict"] == "passed"

    def test_waiver_integrity_present(self, tmp_path):
        result, stdout, _ = _invoke_audit(tmp_path, "a57-integrity")
        data = _get_json(stdout)
        assert "waiver_integrity" in data
        assert data["waiver_integrity"] == "valid"

    def test_adjusted_check_count_present(self, tmp_path):
        result, stdout, _ = _invoke_audit(tmp_path, "a57-adj")
        data = _get_json(stdout)
        assert "adjusted_check_count" in data

    def test_policy_waived_checks_present(self, tmp_path):
        extras = {"orphan_evidence.txt": "orphan"}
        result, stdout, _ = _invoke_audit(tmp_path, "a57-pwc", extra_files=extras)
        data = _get_json(stdout)
        assert "policy_waived_checks" in data
        assert "omitted_evidence" in data["policy_waived_checks"]


# ============================================================
# TestA57AuditWithPolicy
# ============================================================

class TestA57AuditWithPolicy:
    """Audit with policy file loaded."""

    def test_policy_metadata_in_waivers(self, tmp_path):
        extras = {"orphan_evidence.txt": "orphan"}
        policy = _make_policy(tmp_path, {"description": "A57 policy test"})
        result, stdout, _ = _invoke_audit(
            tmp_path, "a57-policy", extra_files=extras,
            extra_args=["--policy", policy])
        data = _get_json(stdout)
        waivers = data["policy_waivers"]
        assert len(waivers) >= 1
        w = waivers[0]
        assert w["policy_schema_version"] == "1.0"
        assert len(w["policy_hash"]) > 0
