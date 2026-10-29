"""A34 — External Checkpoint Tests.

Covers the A34 features:

 1. paper checkpoint --export: export chain head checkpoint
 2. paper checkpoint --verify: verify checkpoint against current log
 3. paper checkpoint (display): show current chain head
 4. --strict-chain option in verify-chain
 5. ISO-8601 timestamp format validation in verify-chain
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import zipfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def _make_run_dir(tmp: Path, run_id: str = "paper-test-a34") -> tuple[Path, dict]:
    run_dir = tmp / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    state = {
        "run_id": run_id, "task_id": "task-a34",
        "project_id": "proj-a34", "status": "completed",
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


_RT_PATH = "ai_workflow_hub.cli._paper_runtime"
_PAPER_RUNS = "ai_workflow_hub.cli._paper_runs_root"


def _fake_runtime():
    return {
        "sanitize": lambda rid: rid,
        "create": MagicMock(), "execute": MagicMock(),
        "status": MagicMock(), "redact": lambda s: s,
    }


def _invoke_audit(tmp_path, run_id="paper-a34-test", extra_args=None,
                  create_reports=True):
    from typer.testing import CliRunner
    from ai_workflow_hub.cli import app
    from rich.console import Console

    run_dir, state = _make_run_dir(tmp_path, run_id)
    if create_reports:
        _write_json(run_dir / "closeout-report.json", {"v": 1, "run_id": run_id})
        (run_dir / "closeout-report.md").write_text(f"# Report {run_id}", encoding="utf-8")

    rt = _fake_runtime()
    runner = CliRunner()
    stdout_buf = io.StringIO()
    stderr_buf = io.StringIO()
    _console = Console(file=stdout_buf, force_terminal=False, width=4096)
    _err_console = Console(file=stderr_buf, force_terminal=False)

    args = ["paper", "audit", "--run-id", run_id]
    if extra_args:
        args.extend(extra_args)

    with patch(_RT_PATH, return_value=rt), \
         patch(_PAPER_RUNS, return_value=tmp_path), \
         patch("ai_workflow_hub.cli.init_env"), \
         patch("ai_workflow_hub.cli.console", _console), \
         patch("ai_workflow_hub.cli.err_console", _err_console):
        result = runner.invoke(app, args, catch_exceptions=False)

    return result, run_dir, stdout_buf.getvalue(), stderr_buf.getvalue()


def _invoke_verify_chain(log_path, extra_args=None):
    from typer.testing import CliRunner
    from ai_workflow_hub.cli import app
    from rich.console import Console

    rt = _fake_runtime()
    runner = CliRunner()
    stdout_buf = io.StringIO()
    stderr_buf = io.StringIO()
    _console = Console(file=stdout_buf, force_terminal=False, width=4096)
    _err_console = Console(file=stderr_buf, force_terminal=False)

    args = ["paper", "verify-chain", "--log", str(log_path), "--json"]
    if extra_args:
        args.extend(extra_args)

    with patch(_RT_PATH, return_value=rt), \
         patch("ai_workflow_hub.cli.init_env"), \
         patch("ai_workflow_hub.cli.console", _console), \
         patch("ai_workflow_hub.cli.err_console", _err_console):
        result = runner.invoke(app, args, catch_exceptions=False)

    return result, stdout_buf.getvalue(), stderr_buf.getvalue()


def _invoke_checkpoint(log_path, extra_args=None):
    from typer.testing import CliRunner
    from ai_workflow_hub.cli import app
    from rich.console import Console

    rt = _fake_runtime()
    runner = CliRunner()
    stdout_buf = io.StringIO()
    stderr_buf = io.StringIO()
    _console = Console(file=stdout_buf, force_terminal=False, width=4096)
    _err_console = Console(file=stderr_buf, force_terminal=False)

    args = ["paper", "checkpoint", "--log", str(log_path), "--json"]
    if extra_args:
        args.extend(extra_args)

    with patch(_RT_PATH, return_value=rt), \
         patch("ai_workflow_hub.cli.init_env"), \
         patch("ai_workflow_hub.cli.console", _console), \
         patch("ai_workflow_hub.cli.err_console", _err_console):
        result = runner.invoke(app, args, catch_exceptions=False)

    return result, stdout_buf.getvalue(), stderr_buf.getvalue()


def _get_json_from_stdout(stdout: str) -> dict:
    lines = stdout.strip().split("\n")
    json_start = -1
    for i, line in enumerate(lines):
        if line.strip().startswith("{"):
            json_start = i
            break
    if json_start < 0:
        raise ValueError("No JSON found in stdout")
    return json.loads("\n".join(lines[json_start:]))


def _build_anchor_log(entries_data: list[dict]) -> str:
    """Build a JSONL chain string from a list of entry dicts."""
    lines = []
    for i, entry in enumerate(entries_data):
        if i > 0:
            entry["prev_hash"] = hashlib.sha256(lines[-1].encode("utf-8")).hexdigest()
        else:
            entry["prev_hash"] = ""
        lines.append(json.dumps(entry, ensure_ascii=False))
    return "\n".join(lines) + "\n"


# ===========================================================================
# 1. Checkpoint export
# ===========================================================================

class TestA34CheckpointExport:
    def test_export_creates_file(self, tmp_path):
        """Checkpoint export should create a JSON file."""
        log_path = tmp_path / "log.jsonl"
        entries = [
            {"timestamp": "2026-06-12T00:00:00Z", "bundle_id": "b0",
             "run_id": "r0", "zip_sha256": "0" * 64},
        ]
        log_path.write_text(_build_anchor_log(entries), encoding="utf-8")

        cp_path = tmp_path / "checkpoint.json"
        result, stdout, _ = _invoke_checkpoint(
            log_path, extra_args=["--export", str(cp_path)])
        assert result.exit_code == 0
        assert cp_path.exists()
        cp_data = json.loads(cp_path.read_text(encoding="utf-8"))
        assert cp_data["format_version"] in ("1.0", "1.1")
        assert cp_data["entries_count"] == 1
        assert cp_data["chain_head_hash"] != ""
        assert cp_data["chain_full_hash"] != ""
        assert cp_data["head_bundle_id"] == "b0"

    def test_export_json_matches_stdout(self, tmp_path):
        """Exported file JSON should match the JSON in stdout."""
        log_path = tmp_path / "log.jsonl"
        entries = [
            {"timestamp": "2026-06-12T00:00:00Z", "bundle_id": "b0",
             "run_id": "r0", "zip_sha256": "0" * 64},
        ]
        log_path.write_text(_build_anchor_log(entries), encoding="utf-8")

        cp_path = tmp_path / "cp.json"
        result, stdout, _ = _invoke_checkpoint(
            log_path, extra_args=["--export", str(cp_path)])
        assert result.exit_code == 0
        stdout_data = _get_json_from_stdout(stdout)
        file_data = json.loads(cp_path.read_text(encoding="utf-8"))
        assert stdout_data["chain_head_hash"] == file_data["chain_head_hash"]
        assert stdout_data["entries_count"] == file_data["entries_count"]

    def test_display_without_export(self, tmp_path):
        """Without --export, should display checkpoint info."""
        log_path = tmp_path / "log.jsonl"
        entries = [
            {"timestamp": "2026-06-12T00:00:00Z", "bundle_id": "b0",
             "run_id": "r0", "zip_sha256": "0" * 64},
        ]
        log_path.write_text(_build_anchor_log(entries), encoding="utf-8")

        result, stdout, _ = _invoke_checkpoint(log_path)
        assert result.exit_code == 0
        data = _get_json_from_stdout(stdout)
        assert "chain_head_hash" in data
        assert data["entries_count"] == 1

    def test_empty_log_fails(self, tmp_path):
        """Empty log should fail checkpoint."""
        log_path = tmp_path / "empty.log"
        log_path.write_text("", encoding="utf-8")
        result, stdout, _ = _invoke_checkpoint(log_path)
        assert result.exit_code == 1

    def test_missing_log_fails(self, tmp_path):
        """Nonexistent log should fail."""
        result, stdout, _ = _invoke_checkpoint(tmp_path / "ghost.log")
        assert result.exit_code == 1


# ===========================================================================
# 2. Checkpoint verify
# ===========================================================================

class TestA34CheckpointVerify:
    def test_verify_matching_checkpoint(self, tmp_path):
        """Verify a valid checkpoint against current log."""
        log_path = tmp_path / "log.jsonl"
        entries = [
            {"timestamp": "2026-06-12T00:00:00Z", "bundle_id": "b0",
             "run_id": "r0", "zip_sha256": "0" * 64},
            {"timestamp": "2026-06-12T00:01:00Z", "bundle_id": "b1",
             "run_id": "r1", "zip_sha256": "1" * 64},
        ]
        log_path.write_text(_build_anchor_log(entries), encoding="utf-8")

        # First export
        cp_path = tmp_path / "cp.json"
        r1, _, _ = _invoke_checkpoint(
            log_path, extra_args=["--export", str(cp_path)])
        assert r1.exit_code == 0

        # Then verify
        r2, stdout, _ = _invoke_checkpoint(
            log_path, extra_args=["--verify", str(cp_path)])
        assert r2.exit_code == 0
        data = _get_json_from_stdout(stdout)
        assert data["verdict"] == "passed"
        assert data["head_hash_match"] is True

    def test_verify_after_new_entry(self, tmp_path):
        """After appending a new entry, old checkpoint head should not match."""
        log_path = tmp_path / "log.jsonl"
        entries = [
            {"timestamp": "2026-06-12T00:00:00Z", "bundle_id": "b0",
             "run_id": "r0", "zip_sha256": "0" * 64},
        ]
        log_path.write_text(_build_anchor_log(entries), encoding="utf-8")

        # Export checkpoint at entry 1
        cp_path = tmp_path / "cp.json"
        _invoke_checkpoint(log_path, extra_args=["--export", str(cp_path)])

        # Append another entry
        entries2 = [
            {"timestamp": "2026-06-12T00:00:00Z", "bundle_id": "b0",
             "run_id": "r0", "zip_sha256": "0" * 64},
            {"timestamp": "2026-06-12T00:01:00Z", "bundle_id": "b1",
             "run_id": "r1", "zip_sha256": "1" * 64},
        ]
        log_path.write_text(_build_anchor_log(entries2), encoding="utf-8")

        # Verify — head hash should NOT match (chain grew)
        result, stdout, _ = _invoke_checkpoint(
            log_path, extra_args=["--verify", str(cp_path)])
        assert result.exit_code == 1
        data = _get_json_from_stdout(stdout)
        assert data["head_hash_match"] is False
        assert data["current_entries"] == 2
        assert data["checkpoint_entries"] == 1

    def test_verify_missing_checkpoint_file(self, tmp_path):
        """Verifying with a nonexistent checkpoint should fail."""
        log_path = tmp_path / "log.jsonl"
        entries = [
            {"timestamp": "2026-06-12T00:00:00Z", "bundle_id": "b0",
             "run_id": "r0", "zip_sha256": "0" * 64},
        ]
        log_path.write_text(_build_anchor_log(entries), encoding="utf-8")

        result, stdout, _ = _invoke_checkpoint(
            log_path, extra_args=["--verify", str(tmp_path / "ghost_cp.json")])
        assert result.exit_code == 1


# ===========================================================================
# 3. --strict-chain in verify-chain
# ===========================================================================

class TestA34StrictChain:
    def test_strict_chain_fails_on_partial(self, tmp_path):
        """--strict-chain should fail when verification_mode is chain_partial."""
        log_path = tmp_path / "strict.log"
        entries = [
            {"timestamp": "2026-06-12T00:00:00Z", "bundle_id": "b0",
             "run_id": "r0", "zip_sha256": "0" * 64},
        ]
        log_path.write_text(_build_anchor_log(entries), encoding="utf-8")

        empty_dir = tmp_path / "empty_zips"
        empty_dir.mkdir()
        result, stdout, _ = _invoke_verify_chain(
            log_path, extra_args=["--zip-dir", str(empty_dir), "--strict-chain"])
        data = _get_json_from_stdout(stdout)
        assert result.exit_code == 1
        assert data["verdict"] == "failed"
        checks = {c["check"]: c for c in data["checks"]}
        assert "strict_chain_policy" in checks
        assert checks["strict_chain_policy"]["passed"] is False

    def test_strict_chain_passes_without_zip_dir(self, tmp_path):
        """--strict-chain without --zip-dir should pass (chain_only mode)."""
        log_path = tmp_path / "strict2.log"
        entries = [
            {"timestamp": "2026-06-12T00:00:00Z", "bundle_id": "b0",
             "run_id": "r0", "zip_sha256": "0" * 64},
        ]
        log_path.write_text(_build_anchor_log(entries), encoding="utf-8")

        result, stdout, _ = _invoke_verify_chain(
            log_path, extra_args=["--strict-chain"])
        data = _get_json_from_stdout(stdout)
        assert result.exit_code == 0
        assert data["verdict"] == "passed"


# ===========================================================================
# 4. ISO-8601 timestamp validation in verify-chain
# ===========================================================================

class TestA34TimestampFormat:
    def test_valid_iso8601_timestamps(self, tmp_path):
        """Valid ISO-8601 UTC timestamps should pass."""
        log_path = tmp_path / "iso_ok.log"
        entries = [
            {"timestamp": "2026-06-12T00:00:00Z", "bundle_id": "b0",
             "run_id": "r0", "zip_sha256": "0" * 64},
            {"timestamp": "2026-06-12T00:01:00Z", "bundle_id": "b1",
             "run_id": "r1", "zip_sha256": "1" * 64},
        ]
        log_path.write_text(_build_anchor_log(entries), encoding="utf-8")

        result, stdout, _ = _invoke_verify_chain(log_path)
        data = _get_json_from_stdout(stdout)
        checks = {c["check"]: c for c in data["checks"]}
        assert checks["timestamp_format_iso8601"]["passed"] is True

    def test_valid_iso8601_with_offset(self, tmp_path):
        """ISO-8601 with timezone offset (+08:00) should pass."""
        log_path = tmp_path / "iso_offset.log"
        entries = [
            {"timestamp": "2026-06-12T08:00:00+08:00", "bundle_id": "b0",
             "run_id": "r0", "zip_sha256": "0" * 64},
        ]
        log_path.write_text(_build_anchor_log(entries), encoding="utf-8")

        result, stdout, _ = _invoke_verify_chain(log_path)
        data = _get_json_from_stdout(stdout)
        checks = {c["check"]: c for c in data["checks"]}
        assert checks["timestamp_format_iso8601"]["passed"] is True

    def test_invalid_timestamp_format(self, tmp_path):
        """Non-ISO-8601 timestamps should fail."""
        log_path = tmp_path / "iso_bad.log"
        entries = [
            {"timestamp": "June 12 2026", "bundle_id": "b0",
             "run_id": "r0", "zip_sha256": "0" * 64},
        ]
        log_path.write_text(_build_anchor_log(entries), encoding="utf-8")

        result, stdout, _ = _invoke_verify_chain(log_path)
        data = _get_json_from_stdout(stdout)
        checks = {c["check"]: c for c in data["checks"]}
        assert checks["timestamp_format_iso8601"]["passed"] is False


# ===========================================================================
# 5. Integration: full A34 workflow
# ===========================================================================

class TestA34Integration:
    def test_full_checkpoint_workflow(self, tmp_path):
        """End-to-end: audit → checkpoint export → verify checkpoint."""
        log_path = tmp_path / "integ.log"

        # Run two audits writing to the same anchor log
        for i in range(2):
            rid = f"a34-integ-{i}"
            r, run_dir, _, _ = _invoke_audit(
                tmp_path, rid,
                extra_args=["--anchor-log", str(log_path)])
            assert r.exit_code == 0

        # Export checkpoint
        cp_path = tmp_path / "integ_cp.json"
        r_cp, stdout_cp, _ = _invoke_checkpoint(
            log_path, extra_args=["--export", str(cp_path)])
        assert r_cp.exit_code == 0
        cp_data = json.loads(cp_path.read_text(encoding="utf-8"))
        assert cp_data["entries_count"] == 2
        assert cp_data["format_version"] in ("1.0", "1.1")

        # Verify checkpoint matches
        r_v, stdout_v, _ = _invoke_checkpoint(
            log_path, extra_args=["--verify", str(cp_path)])
        assert r_v.exit_code == 0
        v_data = _get_json_from_stdout(stdout_v)
        assert v_data["verdict"] == "passed"

        # Run verify-chain with strict
        r_vc, stdout_vc, _ = _invoke_verify_chain(
            log_path, extra_args=["--strict-chain"])
        assert r_vc.exit_code == 0
        vc_data = _get_json_from_stdout(stdout_vc)
        assert vc_data["verdict"] == "passed"
        assert vc_data["verification_mode"] == "chain_only"
