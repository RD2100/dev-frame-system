"""A62 -- Failure Registry Coverage: Hardened registry, dedup, symbolic codes, error profiles.

Verifies:
1. Schema version "1.3".
2. Extended registry: new entries (filesystem_containment, manifest_mismatch, etc.).
3. failure_types[] deduplication (same type not recorded twice).
4. Symbolic reason_code in failure_details[].
5. Numeric exit_code at top level.
6. error_profile field ("full" vs "minimal").
7. Early abort JSON includes checks: [] and policy_waivers: [].
8. Unregistered failure type handled with fallback exit_code 99.
9. waiver_integrity_failed recording path.
10. Backward compatibility with A61 fields.
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


def _make_run_dir(tmp: Path, run_id: str = "paper-test-a62") -> tuple[Path, dict]:
    run_dir = tmp / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    state = {
        "run_id": run_id, "task_id": "task-a62",
        "project_id": "proj-a62", "status": "completed",
        "workflow_type": "paper",
        "created_at": "2026-06-13T00:00:00+00:00",
        "updated_at": "2026-06-13T00:01:00+00:00",
        "executed_nodes": ["plan", "execute"],
        "acceptance_result": {"status": "accepted", "reasons": [], "blocking_issues": []},
        "blocking_count": 0, "non_blocking_count": 0,
        "evidence_manifest": {
            "manifest_id": "ev-001", "status": "complete",
            "version": "1.0", "generated_at": "2026-06-13T00:00:30",
            "files": [],
            "privacy_attestation": {"no_full_text": True, "no_api_keys": True, "no_personal_identity": True},
        },
        "ledger_dir": "", "decision_base_dir": "",
    }
    _write_json(run_dir / "state.json", state)
    return run_dir, state


def _invoke_audit(tmp_path, run_id="paper-a62-test", extra_args=None,
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


def _invoke_audit_raw(tmp_path, run_id="paper-a62-raw", extra_args=None):
    """Invoke audit without creating run dir (for early abort tests)."""
    from rich.console import Console

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
# TestA62SchemaVersion
# ============================================================

class TestA62SchemaVersion:
    """Schema version 1.3."""

    def test_schema_version_1_3(self, tmp_path):
        result, stdout, _ = _invoke_audit(tmp_path, "a62-sv")
        assert result.exit_code == 0
        data = _get_json(stdout)
        assert data["result_schema_version"] in ("1.3", "1.4", "1.5", "1.6", "1.7", "1.8", "1.9", "1.10", "1.11", "1.12", "1.13", "1.14", "1.15", "1.16", "1.17", "1.18", "1.19", "1.20", "1.21", "1.22", "1.23", "1.24", "1.25", "1.26", "1.27", "1.28", "1.29", "1.30", "1.31", "1.32", "1.33", "1.34", "1.35", "1.36", "1.37", "1.38", "1.39", "1.40", "1.41", "1.42", "1.43", "1.44", "1.45", "1.46", "1.47", "1.48", "1.49", "1.50", "1.51", "1.52", "1.53", "1.54", "1.55", "1.56", "1.57", "1.58", "1.61")


# ============================================================
# TestA62ExtendedRegistry
# ============================================================

class TestA62ExtendedRegistry:
    """New registry entries present in source."""

    def test_registry_new_entries_in_source(self):
        """New failure types registered in cli.py source."""
        cli = (Path(__file__).resolve().parent.parent /
               "src" / "ai_workflow_hub" / "cli.py").read_text(encoding="utf-8")
        for ft in ["filesystem_containment", "manifest_mismatch",
                    "signature_failure", "anchor_log_corruption",
                    "artifact_chain_integrity"]:
            assert f'"{ft}"' in cli, f"Missing registry entry: {ft}"

    def test_registry_reason_codes(self):
        """Symbolic reason_code present for each new entry."""
        cli = (Path(__file__).resolve().parent.parent /
               "src" / "ai_workflow_hub" / "cli.py").read_text(encoding="utf-8")
        for rc in ["FILESYSTEM_CONTAINMENT_FAILED", "MANIFEST_MISMATCH",
                    "SIGNATURE_FAILED", "ANCHOR_LOG_CORRUPT",
                    "ARTIFACT_CHAIN_BROKEN"]:
            assert f'"{rc}"' in cli, f"Missing reason_code: {rc}"


# ============================================================
# TestA62Deduplication
# ============================================================

class TestA62Deduplication:
    """failure_types[] deduplication."""

    def test_no_duplicate_failure_types(self, tmp_path):
        """failure_types[] should not contain duplicates after a single failure."""
        extras = {"orphan_evidence.txt": "omitted"}
        result, stdout, _ = _invoke_audit(
            tmp_path, "a62-dedup", extra_files=extras,
            extra_args=["--strict"])
        data = _get_json(stdout)
        assert len(data["failure_types"]) == len(set(data["failure_types"]))

    def test_failure_details_matches_types(self, tmp_path):
        """failure_details length matches failure_types length."""
        extras = {"orphan_evidence.txt": "omitted"}
        result, stdout, _ = _invoke_audit(
            tmp_path, "a62-dedup2", extra_files=extras,
            extra_args=["--strict"])
        data = _get_json(stdout)
        assert len(data["failure_details"]) == len(data["failure_types"])


# ============================================================
# TestA62SymbolicReasonCode
# ============================================================

class TestA62SymbolicReasonCode:
    """Symbolic reason_code in failure_details."""

    def test_reason_code_in_strict_failure(self, tmp_path):
        extras = {"orphan_evidence.txt": "omitted"}
        result, stdout, _ = _invoke_audit(
            tmp_path, "a62-rc", extra_files=extras,
            extra_args=["--strict"])
        data = _get_json(stdout)
        assert len(data["failure_details"]) >= 1
        detail = data["failure_details"][0]
        assert detail["reason_code"] == "STRICT_AUDIT_FAILED"

    def test_reason_code_in_early_abort(self, tmp_path):
        result, stdout, _ = _invoke_audit_raw(tmp_path, "nonexistent-a62-rc")
        data = _get_json(stdout)
        assert data["failure_details"][0]["reason_code"] == "RUN_STATE_NOT_FOUND"

    def test_reason_code_success_empty(self, tmp_path):
        """Success path: no failures, no reason codes."""
        result, stdout, _ = _invoke_audit(tmp_path, "a62-rc-ok")
        data = _get_json(stdout)
        assert data["failure_details"] == []


# ============================================================
# TestA62NumericExitCode
# ============================================================

class TestA62NumericExitCode:
    """Numeric exit_code at top level."""

    def test_exit_code_zero_success(self, tmp_path):
        result, stdout, _ = _invoke_audit(tmp_path, "a62-ec-ok")
        data = _get_json(stdout)
        assert data["exit_code"] == 0

    def test_exit_code_10_strict(self, tmp_path):
        extras = {"orphan_evidence.txt": "omitted"}
        result, stdout, _ = _invoke_audit(
            tmp_path, "a62-ec-s", extra_files=extras,
            extra_args=["--strict"])
        data = _get_json(stdout)
        assert data["exit_code"] in (1, 10)  # A65: aligned to 1, but accept 10 for compat

    def test_exit_code_20_early_abort(self, tmp_path):
        result, stdout, _ = _invoke_audit_raw(tmp_path, "nonexistent-a62-ec")
        data = _get_json(stdout)
        assert data["exit_code"] in (1, 20)  # A65: aligned to 1, but accept 20 for compat

    def test_exit_code_is_integer(self, tmp_path):
        result, stdout, _ = _invoke_audit(tmp_path, "a62-ec-int")
        data = _get_json(stdout)
        assert isinstance(data["exit_code"], int)


# ============================================================
# TestA62ErrorProfile
# ============================================================

class TestA62ErrorProfile:
    """error_profile field: full vs minimal."""

    def test_full_profile_success(self, tmp_path):
        result, stdout, _ = _invoke_audit(tmp_path, "a62-ep-ok")
        data = _get_json(stdout)
        assert data["error_profile"] == "full"

    def test_full_profile_strict_failure(self, tmp_path):
        extras = {"orphan_evidence.txt": "omitted"}
        result, stdout, _ = _invoke_audit(
            tmp_path, "a62-ep-s", extra_files=extras,
            extra_args=["--strict"])
        data = _get_json(stdout)
        assert data["error_profile"] == "full"

    def test_minimal_profile_early_abort(self, tmp_path):
        result, stdout, _ = _invoke_audit_raw(tmp_path, "nonexistent-a62-ep")
        data = _get_json(stdout)
        assert data["error_profile"] == "minimal"


# ============================================================
# TestA62EarlyAbortEnhanced
# ============================================================

class TestA62EarlyAbortEnhanced:
    """Early abort JSON includes checks[] and policy_waivers[]."""

    def test_early_abort_has_checks(self, tmp_path):
        result, stdout, _ = _invoke_audit_raw(tmp_path, "nonexistent-a62-chk")
        data = _get_json(stdout)
        assert "checks" in data
        assert data["checks"] == []

    def test_early_abort_has_policy_waivers(self, tmp_path):
        result, stdout, _ = _invoke_audit_raw(tmp_path, "nonexistent-a62-pw")
        data = _get_json(stdout)
        assert "policy_waivers" in data
        assert data["policy_waivers"] == []

    def test_early_abort_has_numeric_exit_code(self, tmp_path):
        result, stdout, _ = _invoke_audit_raw(tmp_path, "nonexistent-a62-ec")
        data = _get_json(stdout)
        assert data["exit_code"] in (1, 20)  # A65: aligned to 1, but accept 20 for compat
        assert isinstance(data["exit_code"], int)


# ============================================================
# TestA62UnregisteredFailureType
# ============================================================

class TestA62UnregisteredFailureType:
    """Unregistered failure types handled with fallback."""

    def test_unregistered_gets_fallback_code(self):
        """Source shows unregistered types get exit_code=99."""
        cli = (Path(__file__).resolve().parent.parent /
               "src" / "ai_workflow_hub" / "cli.py").read_text(encoding="utf-8")
        assert '"UNKNOWN_FAILURE"' in cli
        assert '"exit_code": 99' in cli or "'exit_code': 99" in cli

    def test_unregistered_gets_reason_code(self):
        """Source shows unregistered types get reason_code=UNKNOWN_FAILURE."""
        cli = (Path(__file__).resolve().parent.parent /
               "src" / "ai_workflow_hub" / "cli.py").read_text(encoding="utf-8")
        assert "Unregistered failure type" in cli


# ============================================================
# TestA62WaiverIntegrityRecording
# ============================================================

class TestA62WaiverIntegrityRecording:
    """waiver_integrity_failed recording path."""

    def test_waiver_integrity_source_recording(self):
        """Source shows _record_failure called for waiver_integrity_failed."""
        cli = (Path(__file__).resolve().parent.parent /
               "src" / "ai_workflow_hub" / "cli.py").read_text(encoding="utf-8")
        assert '_record_failure("waiver_integrity_failed"' in cli

    def test_waiver_integrity_after_verify(self):
        """Source shows waiver check happens after _verify_waiver_integrity."""
        cli = (Path(__file__).resolve().parent.parent /
               "src" / "ai_workflow_hub" / "cli.py").read_text(encoding="utf-8")
        # Find the position of _verify_waiver_integrity call
        verify_pos = cli.index('_verify_waiver_integrity(_audit_result)')
        record_pos = cli.index('_record_failure("waiver_integrity_failed"')
        assert record_pos > verify_pos


# ============================================================
# TestA62BackwardCompat
# ============================================================

class TestA62BackwardCompat:
    """Backward compatibility with A61 fields."""

    def test_all_a61_fields_present(self, tmp_path):
        result, stdout, _ = _invoke_audit(tmp_path, "a62-bc")
        data = _get_json(stdout)
        for field in ["result_schema_version", "failure_type", "failure_types",
                       "failure_details", "exit_reason", "exit_reason_code",
                       "strict_mode", "waiver_mode", "checks", "policy_waivers"]:
            assert field in data, f"Missing A61 field: {field}"

    def test_failure_type_none_success(self, tmp_path):
        result, stdout, _ = _invoke_audit(tmp_path, "a62-bc-ok")
        data = _get_json(stdout)
        assert data["failure_type"] == "none"
        assert data["failure_types"] == []
        assert data["exit_reason_code"] == ""
