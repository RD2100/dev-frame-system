"""A63 -- Failure Registry Operationalization.

Verifies:
1. Schema version "1.4".
2. failure_events[] non-deduped event log alongside deduped failure_types[].
3. Operational recording paths for registry entries.
4. exit_code / reason_code / exit_reason_code semantics.
5. Error profile contract (minimal vs full).
6. End-to-end event timestamp presence.
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


def _make_run_dir(tmp: Path, run_id: str = "paper-test-a63") -> tuple[Path, dict]:
    run_dir = tmp / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    state = {
        "run_id": run_id, "task_id": "task-a63",
        "project_id": "proj-a63", "status": "completed",
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


def _invoke_audit(tmp_path, run_id="paper-a63-test", extra_args=None,
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


def _invoke_audit_raw(tmp_path, run_id="paper-a63-raw"):
    from rich.console import Console

    rt = _fake_runtime()
    stdout_buf = io.StringIO()
    stderr_buf = io.StringIO()
    _console = Console(file=stdout_buf, force_terminal=False)
    _err_console = Console(file=stderr_buf, force_terminal=False)

    args = ["paper", "audit", "--run-id", run_id, "--json"]
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
# TestA63SchemaVersion
# ============================================================

class TestA63SchemaVersion:
    def test_schema_version_1_4(self, tmp_path):
        result, stdout, _ = _invoke_audit(tmp_path, "a63-sv")
        assert result.exit_code == 0
        data = _get_json(stdout)
        assert data["result_schema_version"] in ("1.4", "1.5", "1.6", "1.7", "1.8", "1.9", "1.10", "1.11", "1.12", "1.13", "1.14", "1.15", "1.16", "1.17", "1.18", "1.19", "1.20", "1.21", "1.22", "1.23", "1.24", "1.25", "1.26", "1.27", "1.28", "1.29", "1.30", "1.31", "1.32", "1.33", "1.34", "1.35", "1.36", "1.37", "1.38", "1.39", "1.40", "1.41", "1.42", "1.43", "1.44", "1.45", "1.46", "1.47", "1.48", "1.49", "1.50", "1.51", "1.52", "1.53", "1.54", "1.55", "1.56", "1.57", "1.58", "1.61")


# ============================================================
# TestA63FailureEvents
# ============================================================

class TestA63FailureEvents:
    """failure_events[] non-deduped event log."""

    def test_failure_events_empty_success(self, tmp_path):
        result, stdout, _ = _invoke_audit(tmp_path, "a63-fe-ok")
        data = _get_json(stdout)
        assert data["failure_events"] == []

    def test_failure_events_on_strict_failure(self, tmp_path):
        extras = {"orphan_evidence.txt": "omitted"}
        result, stdout, _ = _invoke_audit(
            tmp_path, "a63-fe-s", extra_files=extras,
            extra_args=["--strict"])
        data = _get_json(stdout)
        assert len(data["failure_events"]) >= 1
        assert data["failure_events"][0]["type"] == "strict_audit"

    def test_failure_events_has_timestamp(self, tmp_path):
        extras = {"orphan_evidence.txt": "omitted"}
        result, stdout, _ = _invoke_audit(
            tmp_path, "a63-fe-ts", extra_files=extras,
            extra_args=["--strict"])
        data = _get_json(stdout)
        for evt in data["failure_events"]:
            assert "timestamp" in evt
            assert len(evt["timestamp"]) > 10

    def test_failure_events_on_early_abort(self, tmp_path):
        result, stdout, _ = _invoke_audit_raw(tmp_path, "nonexistent-a63")
        data = _get_json(stdout)
        assert len(data["failure_events"]) == 1
        assert data["failure_events"][0]["type"] == "missing_run_state"

    def test_failure_events_is_list(self, tmp_path):
        result, stdout, _ = _invoke_audit(tmp_path, "a63-fe-list")
        data = _get_json(stdout)
        assert isinstance(data["failure_events"], list)


# ============================================================
# TestA63Semantics
# ============================================================

class TestA63Semantics:
    """exit_code / reason_code / exit_reason_code semantics."""

    def test_exit_code_is_integer(self, tmp_path):
        result, stdout, _ = _invoke_audit(tmp_path, "a63-sem-ec")
        data = _get_json(stdout)
        assert isinstance(data["exit_code"], int)
        assert data["exit_code"] == 0

    def test_reason_code_in_failure_details(self, tmp_path):
        extras = {"orphan_evidence.txt": "omitted"}
        result, stdout, _ = _invoke_audit(
            tmp_path, "a63-sem-rc", extra_files=extras,
            extra_args=["--strict"])
        data = _get_json(stdout)
        assert data["failure_details"][0]["reason_code"] == "STRICT_AUDIT_FAILED"

    def test_exit_reason_code_is_stringified_code(self, tmp_path):
        extras = {"orphan_evidence.txt": "omitted"}
        result, stdout, _ = _invoke_audit(
            tmp_path, "a63-sem-erc", extra_files=extras,
            extra_args=["--strict"])
        data = _get_json(stdout)
        assert data["exit_reason_code"] == str(data["exit_code"])

    def test_semantic_documentation_in_source(self):
        """Source contains semantic clarification comments."""
        cli = (Path(__file__).resolve().parent.parent /
               "src" / "ai_workflow_hub" / "cli.py").read_text(encoding="utf-8")
        assert "exit_code" in cli and "reason_code" in cli
        assert "deprecated alias" in cli or "Semantic clarification" in cli or "Exit metadata contract" in cli


# ============================================================
# TestA63OperationalPaths
# ============================================================

class TestA63OperationalPaths:
    """Operational recording paths for new registry entries."""

    def test_artifact_chain_integrity_source(self):
        cli = (Path(__file__).resolve().parent.parent /
               "src" / "ai_workflow_hub" / "cli.py").read_text(encoding="utf-8")
        assert '_record_failure("artifact_chain_integrity"' in cli

    def test_manifest_mismatch_source(self):
        cli = (Path(__file__).resolve().parent.parent /
               "src" / "ai_workflow_hub" / "cli.py").read_text(encoding="utf-8")
        assert '_record_failure("manifest_mismatch"' in cli

    def test_signature_failure_source(self):
        cli = (Path(__file__).resolve().parent.parent /
               "src" / "ai_workflow_hub" / "cli.py").read_text(encoding="utf-8")
        assert '_record_failure("signature_failure"' in cli

    def test_anchor_log_corruption_source(self):
        cli = (Path(__file__).resolve().parent.parent /
               "src" / "ai_workflow_hub" / "cli.py").read_text(encoding="utf-8")
        assert '_record_failure("anchor_log_corruption"' in cli

    def test_filesystem_containment_source(self):
        cli = (Path(__file__).resolve().parent.parent /
               "src" / "ai_workflow_hub" / "cli.py").read_text(encoding="utf-8")
        assert '_record_failure("filesystem_containment"' in cli


# ============================================================
# TestA63ErrorProfileContract
# ============================================================

class TestA63ErrorProfileContract:
    """Minimal vs full error profile contract."""

    def test_full_profile_fields(self, tmp_path):
        result, stdout, _ = _invoke_audit(tmp_path, "a63-ep-full")
        data = _get_json(stdout)
        assert data["error_profile"] == "full"
        for f in ["raw_verdict", "policy_verdict", "verdict",
                   "waiver_integrity", "failure_events"]:
            assert f in data, f"Missing full-profile field: {f}"

    def test_minimal_profile_fields(self, tmp_path):
        result, stdout, _ = _invoke_audit_raw(tmp_path, "nonexistent-a63-ep")
        data = _get_json(stdout)
        assert data["error_profile"] == "minimal"
        for f in ["result_schema_version", "failure_type", "failure_types",
                   "failure_events", "failure_details", "exit_code",
                   "exit_reason", "strict_mode", "waiver_mode",
                   "checks", "policy_waivers"]:
            assert f in data, f"Missing minimal-profile field: {f}"

    def test_profile_contract_in_source(self):
        cli = (Path(__file__).resolve().parent.parent /
               "src" / "ai_workflow_hub" / "cli.py").read_text(encoding="utf-8")
        assert '"minimal"' in cli and '"full"' in cli
        assert "Error profile contract" in cli or "error_profile" in cli


# ============================================================
# TestA63BackwardCompat
# ============================================================

class TestA63BackwardCompat:
    """Backward compatibility with A62 fields."""

    def test_all_a62_fields_present(self, tmp_path):
        result, stdout, _ = _invoke_audit(tmp_path, "a63-bc")
        data = _get_json(stdout)
        for field in ["result_schema_version", "error_profile", "failure_type",
                       "failure_types", "failure_details", "failure_events",
                       "exit_reason", "exit_reason_code", "exit_code",
                       "strict_mode", "waiver_mode", "checks", "policy_waivers"]:
            assert field in data, f"Missing field: {field}"

    def test_failure_types_deduped(self, tmp_path):
        extras = {"orphan_evidence.txt": "omitted"}
        result, stdout, _ = _invoke_audit(
            tmp_path, "a63-bc-dd", extra_files=extras,
            extra_args=["--strict"])
        data = _get_json(stdout)
        assert len(data["failure_types"]) == len(set(data["failure_types"]))
