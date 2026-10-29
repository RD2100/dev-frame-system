"""A35 — Checkpoint Strict Verify Tests.

Covers the A35 features:

 1. checkpoint --verify: chain_full_hash independent verification
 2. checkpoint --verify: entries_count mismatch detection
 3. checkpoint --sign: optional HMAC-SHA256 signing
 4. checkpoint verify: signature validation
 5. Parser-based ISO-8601 validation (datetime.fromisoformat)
 6. format_version 1.1
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


def _make_run_dir(tmp: Path, run_id: str = "paper-test-a35") -> tuple[Path, dict]:
    run_dir = tmp / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    state = {
        "run_id": run_id, "task_id": "task-a35",
        "project_id": "proj-a35", "status": "completed",
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


def _invoke_checkpoint(log_path, extra_args=None, env_overrides=None):
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

    # Build environment
    filtered = {k: v for k, v in os.environ.items() if k != "AIHUB_SIGNING_KEY"}
    if env_overrides:
        filtered.update(env_overrides)

    with patch(_RT_PATH, return_value=rt), \
         patch("ai_workflow_hub.cli.init_env"), \
         patch("ai_workflow_hub.cli.console", _console), \
         patch("ai_workflow_hub.cli.err_console", _err_console), \
         patch.dict(os.environ, filtered, clear=True):
        result = runner.invoke(app, args, catch_exceptions=False)

    return result, stdout_buf.getvalue(), stderr_buf.getvalue()


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
    lines = []
    for i, entry in enumerate(entries_data):
        if i > 0:
            entry["prev_hash"] = hashlib.sha256(lines[-1].encode("utf-8")).hexdigest()
        else:
            entry["prev_hash"] = ""
        lines.append(json.dumps(entry, ensure_ascii=False))
    return "\n".join(lines) + "\n"


# ===========================================================================
# 1. Checkpoint verify: chain_full_hash + entries_count
# ===========================================================================

class TestA35CheckpointVerifyChainFull:
    def test_chain_full_hash_match(self, tmp_path):
        """Verify should check chain_full_hash independently."""
        log_path = tmp_path / "log.jsonl"
        entries = [
            {"timestamp": "2026-06-12T00:00:00Z", "bundle_id": "b0",
             "run_id": "r0", "zip_sha256": "0" * 64},
        ]
        log_path.write_text(_build_anchor_log(entries), encoding="utf-8")

        cp_path = tmp_path / "cp.json"
        _invoke_checkpoint(log_path, extra_args=["--export", str(cp_path)])

        r, stdout, _ = _invoke_checkpoint(
            log_path, extra_args=["--verify", str(cp_path)])
        assert r.exit_code == 0
        data = _get_json_from_stdout(stdout)
        assert data["chain_full_hash_match"] is True
        assert data["entries_count_match"] is True

    def test_chain_full_hash_tamper_detected(self, tmp_path):
        """Modifying earlier entries should break chain_full_hash."""
        log_path = tmp_path / "log.jsonl"
        entries = [
            {"timestamp": "2026-06-12T00:00:00Z", "bundle_id": "b0",
             "run_id": "r0", "zip_sha256": "0" * 64},
            {"timestamp": "2026-06-12T00:01:00Z", "bundle_id": "b1",
             "run_id": "r1", "zip_sha256": "1" * 64},
        ]
        log_path.write_text(_build_anchor_log(entries), encoding="utf-8")

        # Export checkpoint
        cp_path = tmp_path / "cp.json"
        _invoke_checkpoint(log_path, extra_args=["--export", str(cp_path)])

        # Tamper with first entry (change zip_sha256, rebuild chain)
        tampered = [
            {"timestamp": "2026-06-12T00:00:00Z", "bundle_id": "b0",
             "run_id": "r0", "zip_sha256": "f" * 64},  # Changed
            {"timestamp": "2026-06-12T00:01:00Z", "bundle_id": "b1",
             "run_id": "r1", "zip_sha256": "1" * 64},
        ]
        log_path.write_text(_build_anchor_log(tampered), encoding="utf-8")

        r, stdout, _ = _invoke_checkpoint(
            log_path, extra_args=["--verify", str(cp_path)])
        assert r.exit_code == 1
        data = _get_json_from_stdout(stdout)
        assert data["chain_full_hash_match"] is False

    def test_entries_count_mismatch_detected(self, tmp_path):
        """Different entry count should be detected."""
        log_path = tmp_path / "log.jsonl"
        entries = [
            {"timestamp": "2026-06-12T00:00:00Z", "bundle_id": "b0",
             "run_id": "r0", "zip_sha256": "0" * 64},
        ]
        log_path.write_text(_build_anchor_log(entries), encoding="utf-8")

        cp_path = tmp_path / "cp.json"
        _invoke_checkpoint(log_path, extra_args=["--export", str(cp_path)])

        # Add another entry (head hash will also change)
        entries2 = [
            {"timestamp": "2026-06-12T00:00:00Z", "bundle_id": "b0",
             "run_id": "r0", "zip_sha256": "0" * 64},
            {"timestamp": "2026-06-12T00:01:00Z", "bundle_id": "b1",
             "run_id": "r1", "zip_sha256": "1" * 64},
        ]
        log_path.write_text(_build_anchor_log(entries2), encoding="utf-8")

        r, stdout, _ = _invoke_checkpoint(
            log_path, extra_args=["--verify", str(cp_path)])
        assert r.exit_code == 1
        data = _get_json_from_stdout(stdout)
        assert data["entries_count_match"] is False
        assert data["head_hash_match"] is False


# ===========================================================================
# 2. Checkpoint signing
# ===========================================================================

class TestA35CheckpointSigning:
    def test_signed_export(self, tmp_path):
        """Checkpoint --sign should include HMAC signature."""
        log_path = tmp_path / "log.jsonl"
        entries = [
            {"timestamp": "2026-06-12T00:00:00Z", "bundle_id": "b0",
             "run_id": "r0", "zip_sha256": "0" * 64},
        ]
        log_path.write_text(_build_anchor_log(entries), encoding="utf-8")

        cp_path = tmp_path / "signed_cp.json"
        r, _, _ = _invoke_checkpoint(
            log_path, extra_args=["--export", str(cp_path), "--sign"],
            env_overrides={"AIHUB_SIGNING_KEY": "test-key-35"})
        assert r.exit_code == 0

        cp_data = json.loads(cp_path.read_text(encoding="utf-8"))
        assert "signature" in cp_data
        assert cp_data["signature"]["algorithm"] == "HMAC-SHA256"
        assert cp_data["signature"]["signature"] != ""

    def test_unsigned_export_no_signature(self, tmp_path):
        """Without --sign, checkpoint should not have signature field."""
        log_path = tmp_path / "log.jsonl"
        entries = [
            {"timestamp": "2026-06-12T00:00:00Z", "bundle_id": "b0",
             "run_id": "r0", "zip_sha256": "0" * 64},
        ]
        log_path.write_text(_build_anchor_log(entries), encoding="utf-8")

        cp_path = tmp_path / "unsigned_cp.json"
        r, _, _ = _invoke_checkpoint(
            log_path, extra_args=["--export", str(cp_path)])
        assert r.exit_code == 0

        cp_data = json.loads(cp_path.read_text(encoding="utf-8"))
        assert "signature" not in cp_data

    def test_verify_signed_checkpoint(self, tmp_path):
        """Verify a signed checkpoint with the same key."""
        log_path = tmp_path / "log.jsonl"
        entries = [
            {"timestamp": "2026-06-12T00:00:00Z", "bundle_id": "b0",
             "run_id": "r0", "zip_sha256": "0" * 64},
        ]
        log_path.write_text(_build_anchor_log(entries), encoding="utf-8")

        cp_path = tmp_path / "signed.json"
        _invoke_checkpoint(
            log_path, extra_args=["--export", str(cp_path), "--sign"],
            env_overrides={"AIHUB_SIGNING_KEY": "key35"})

        r, stdout, _ = _invoke_checkpoint(
            log_path, extra_args=["--verify", str(cp_path)],
            env_overrides={"AIHUB_SIGNING_KEY": "key35"})
        assert r.exit_code == 0
        data = _get_json_from_stdout(stdout)
        assert data["signature_valid"] is True

    def test_verify_signed_checkpoint_wrong_key(self, tmp_path):
        """Wrong key should produce invalid signature."""
        log_path = tmp_path / "log.jsonl"
        entries = [
            {"timestamp": "2026-06-12T00:00:00Z", "bundle_id": "b0",
             "run_id": "r0", "zip_sha256": "0" * 64},
        ]
        log_path.write_text(_build_anchor_log(entries), encoding="utf-8")

        cp_path = tmp_path / "signed.json"
        _invoke_checkpoint(
            log_path, extra_args=["--export", str(cp_path), "--sign"],
            env_overrides={"AIHUB_SIGNING_KEY": "correct-key"})

        r, stdout, _ = _invoke_checkpoint(
            log_path, extra_args=["--verify", str(cp_path)],
            env_overrides={"AIHUB_SIGNING_KEY": "wrong-key"})
        assert r.exit_code == 0  # Head hash still matches, but sig invalid
        data = _get_json_from_stdout(stdout)
        assert data["signature_valid"] is False


# ===========================================================================
# 3. Parser-based ISO-8601 in verify-chain
# ===========================================================================

class TestA35ParserISO8601:
    def test_parser_validates_z_suffix(self, tmp_path):
        """Z-suffix timestamps should pass parser validation."""
        log_path = tmp_path / "iso.log"
        entries = [
            {"timestamp": "2026-06-12T00:00:00Z", "bundle_id": "b0",
             "run_id": "r0", "zip_sha256": "0" * 64},
        ]
        log_path.write_text(_build_anchor_log(entries), encoding="utf-8")

        r, stdout, _ = _invoke_verify_chain(log_path)
        data = _get_json_from_stdout(stdout)
        checks = {c["check"]: c for c in data["checks"]}
        assert checks["timestamp_format_iso8601"]["passed"] is True
        assert "parser-validated" in checks["timestamp_format_iso8601"].get("detail", "")

    def test_parser_rejects_naive_timestamp(self, tmp_path):
        """Naive timestamp (no timezone) should fail parser validation."""
        log_path = tmp_path / "naive.log"
        entries = [
            {"timestamp": "2026-06-12T00:00:00", "bundle_id": "b0",
             "run_id": "r0", "zip_sha256": "0" * 64},
        ]
        log_path.write_text(_build_anchor_log(entries), encoding="utf-8")

        r, stdout, _ = _invoke_verify_chain(log_path)
        data = _get_json_from_stdout(stdout)
        checks = {c["check"]: c for c in data["checks"]}
        assert checks["timestamp_format_iso8601"]["passed"] is False
        assert "naive" in checks["timestamp_format_iso8601"].get("detail", "")


# ===========================================================================
# 4. format_version 1.1
# ===========================================================================

class TestA35FormatVersion:
    def test_format_version_is_1_1(self, tmp_path):
        """New checkpoints should use format_version 1.1."""
        log_path = tmp_path / "log.jsonl"
        entries = [
            {"timestamp": "2026-06-12T00:00:00Z", "bundle_id": "b0",
             "run_id": "r0", "zip_sha256": "0" * 64},
        ]
        log_path.write_text(_build_anchor_log(entries), encoding="utf-8")

        cp_path = tmp_path / "cp.json"
        _invoke_checkpoint(log_path, extra_args=["--export", str(cp_path)])
        cp_data = json.loads(cp_path.read_text(encoding="utf-8"))
        assert cp_data["format_version"] == "1.1"


# ===========================================================================
# 5. Integration
# ===========================================================================

class TestA35Integration:
    def test_signed_checkpoint_workflow(self, tmp_path):
        """Full signed checkpoint: export → verify → tamper → detect."""
        log_path = tmp_path / "integ.log"
        entries = [
            {"timestamp": "2026-06-12T00:00:00Z", "bundle_id": "b0",
             "run_id": "r0", "zip_sha256": "0" * 64},
            {"timestamp": "2026-06-12T00:01:00Z", "bundle_id": "b1",
             "run_id": "r1", "zip_sha256": "1" * 64},
        ]
        log_path.write_text(_build_anchor_log(entries), encoding="utf-8")

        # Export signed checkpoint
        cp_path = tmp_path / "signed.json"
        r, _, _ = _invoke_checkpoint(
            log_path, extra_args=["--export", str(cp_path), "--sign"],
            env_overrides={"AIHUB_SIGNING_KEY": "integ-key"})
        assert r.exit_code == 0

        # Verify — should pass
        r2, stdout2, _ = _invoke_checkpoint(
            log_path, extra_args=["--verify", str(cp_path)],
            env_overrides={"AIHUB_SIGNING_KEY": "integ-key"})
        assert r2.exit_code == 0
        data2 = _get_json_from_stdout(stdout2)
        assert data2["verdict"] == "passed"
        assert data2["head_hash_match"] is True
        assert data2["chain_full_hash_match"] is True
        assert data2["entries_count_match"] is True
        assert data2["signature_valid"] is True
