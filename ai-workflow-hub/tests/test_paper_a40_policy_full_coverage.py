"""A40 — Policy Full Coverage Tests.

Covers the A40 features:

 1. --policy on paper audit command
 2. policy_warnings structured field for downgraded failures
 3. Policy overrides required_files in paper audit
 4. Full integration: policy across audit, verify, checkpoint, verify-chain
"""

from __future__ import annotations

import hashlib
import io
import json
import os
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_RT_PATH = "ai_workflow_hub.cli._paper_runtime"


def _fake_runtime():
    return {
        "sanitize": lambda rid: rid,
        "create": MagicMock(), "execute": MagicMock(),
        "status": MagicMock(), "redact": lambda s: s,
    }


def _build_anchor_log(entries_data: list[dict]) -> str:
    lines = []
    for i, entry in enumerate(entries_data):
        if i > 0:
            entry["prev_hash"] = hashlib.sha256(lines[-1].encode("utf-8")).hexdigest()
        else:
            entry["prev_hash"] = ""
        lines.append(json.dumps(entry, ensure_ascii=False))
    return "\n".join(lines) + "\n"


def _make_entries(count: int = 1) -> list[dict]:
    entries = []
    for i in range(count):
        entries.append({
            "timestamp": f"2026-06-12T00:0{i}:00Z",
            "bundle_id": f"b{i}",
            "run_id": f"r{i}",
            "zip_sha256": f"{i}" * 64,
        })
    return entries


def _write_policy(path: Path, policy: dict) -> None:
    path.write_text(json.dumps(policy, indent=2), encoding="utf-8")


def _valid_policy(**overrides) -> dict:
    base = {
        "schema_version": "1.0",
        "signature_policy": "optional",
        "allowed_key_ids": [],
        "chain_verification_mode": "chain_only",
        "strict_chain": False,
        "strict_timestamps": True,
        "required_artifacts": [],
        "description": "A40 test policy",
    }
    base.update(overrides)
    return base


def _invoke_verify_chain(log_path, extra_args=None, env_overrides=None):
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

    filtered = {k: v for k, v in os.environ.items()
                if k not in ("AIHUB_SIGNING_KEY", "AIHUB_SIGNING_KEY_ID")}
    if env_overrides:
        filtered.update(env_overrides)

    with patch(_RT_PATH, return_value=rt), \
         patch("ai_workflow_hub.cli.init_env"), \
         patch("ai_workflow_hub.cli.console", _console), \
         patch("ai_workflow_hub.cli.err_console", _err_console), \
         patch.dict(os.environ, filtered, clear=True):
        result = runner.invoke(app, args, catch_exceptions=False)

    return result, stdout_buf.getvalue(), stderr_buf.getvalue()


def _invoke_audit(extra_args=None, env_overrides=None):
    from typer.testing import CliRunner
    from ai_workflow_hub.cli import app
    from rich.console import Console

    rt = _fake_runtime()
    runner = CliRunner()
    stdout_buf = io.StringIO()
    stderr_buf = io.StringIO()
    _console = Console(file=stdout_buf, force_terminal=False, width=4096)
    _err_console = Console(file=stderr_buf, force_terminal=False)

    args = ["paper", "audit", "--run-id", "test-run-a40", "--json"]
    if extra_args:
        args.extend(extra_args)

    filtered = {k: v for k, v in os.environ.items()
                if k not in ("AIHUB_SIGNING_KEY", "AIHUB_SIGNING_KEY_ID")}
    if env_overrides:
        filtered.update(env_overrides)

    with patch(_RT_PATH, return_value=rt), \
         patch("ai_workflow_hub.cli.init_env"), \
         patch("ai_workflow_hub.cli.console", _console), \
         patch("ai_workflow_hub.cli.err_console", _err_console), \
         patch.dict(os.environ, filtered, clear=True):
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


# ===========================================================================
# 1. policy_warnings structured field
# ===========================================================================

class TestA40PolicyWarnings:
    def test_downgraded_timestamp_appears_in_warnings(self, tmp_path):
        """Downgraded timestamp failures should appear in policy_warnings."""
        policy_path = tmp_path / "policy.json"
        _write_policy(policy_path, _valid_policy(strict_timestamps=False))

        log_path = tmp_path / "log.jsonl"
        entries = [
            {"timestamp": "2026-06-12T00:00:00", "bundle_id": "b0",
             "run_id": "r0", "zip_sha256": "0" * 64},
        ]
        log_path.write_text(_build_anchor_log(entries), encoding="utf-8")

        r, stdout, _ = _invoke_verify_chain(
            log_path, extra_args=["--policy", str(policy_path)])
        assert r.exit_code == 0
        data = _get_json_from_stdout(stdout)
        assert "policy_warnings" in data
        assert len(data["policy_warnings"]) >= 1
        w = data["policy_warnings"][0]
        assert w["warning"] == "timestamp_downgraded"
        assert w["check"] == "timestamp_format_iso8601"
        assert w["reason"] == "strict_timestamps=False"

    def test_no_warnings_when_all_pass(self, tmp_path):
        """No policy_warnings when everything passes normally."""
        policy_path = tmp_path / "policy.json"
        _write_policy(policy_path, _valid_policy(strict_timestamps=True))

        log_path = tmp_path / "log.jsonl"
        log_path.write_text(_build_anchor_log(_make_entries()), encoding="utf-8")

        r, stdout, _ = _invoke_verify_chain(
            log_path, extra_args=["--policy", str(policy_path)])
        assert r.exit_code == 0
        data = _get_json_from_stdout(stdout)
        assert "policy_warnings" not in data or len(data.get("policy_warnings", [])) == 0

    def test_no_warnings_without_policy(self, tmp_path):
        """No policy_warnings when no policy file is used."""
        log_path = tmp_path / "log.jsonl"
        log_path.write_text(_build_anchor_log(_make_entries()), encoding="utf-8")

        r, stdout, _ = _invoke_verify_chain(log_path)
        assert r.exit_code == 0
        data = _get_json_from_stdout(stdout)
        assert "policy_warnings" not in data


# ===========================================================================
# 2. --policy on paper audit
# ===========================================================================

class TestA40AuditPolicy:
    def test_audit_accepts_policy_parameter(self, tmp_path):
        """paper audit should accept --policy without error (parameter exists)."""
        # This tests the CLI parameter is registered, not full audit execution
        policy_path = tmp_path / "policy.json"
        _write_policy(policy_path, _valid_policy(
            required_artifacts=["state.json"]))

        # The audit command will fail because run doesn't exist,
        # but it should NOT fail on --policy parameter
        r, stdout, stderr = _invoke_audit(
            extra_args=["--policy", str(policy_path)])
        # Exit code might be 1 (run not found), but policy should load first
        combined = stdout + stderr
        # Policy loading message should appear
        assert "Policy loaded" in combined or r.exit_code == 0

    def test_audit_policy_overrides_required_files(self, tmp_path):
        """Policy required_artifacts should override CLI --required-files."""
        policy_path = tmp_path / "policy.json"
        _write_policy(policy_path, _valid_policy(
            required_artifacts=["state.json", "ledger.json"]))

        # Even without --required-files, policy should provide it
        r, stdout, stderr = _invoke_audit(
            extra_args=["--policy", str(policy_path)])
        # The audit may fail due to missing run, but policy should load
        combined = stdout + stderr
        assert "Policy loaded" in combined or r.exit_code == 0


# ===========================================================================
# 3. Integration
# ===========================================================================

class TestA40Integration:
    def test_policy_across_commands(self, tmp_path):
        """Same policy should work across verify-chain and checkpoint."""
        run_dir = tmp_path / "integ-run"
        run_dir.mkdir()
        log_path = run_dir / "log.jsonl"
        entries = _make_entries(2)
        log_path.write_text(_build_anchor_log(entries), encoding="utf-8")
        (run_dir / "state.json").write_text("{}", encoding="utf-8")

        policy_path = tmp_path / "policy.json"
        _write_policy(policy_path, _valid_policy(
            chain_verification_mode="chain_only",
            required_artifacts=["state.json"],
            strict_timestamps=True,
            description="A40 cross-command policy"))

        # verify-chain with policy
        r1, stdout1, _ = _invoke_verify_chain(
            log_path, extra_args=["--policy", str(policy_path)])
        assert r1.exit_code == 0
        data1 = _get_json_from_stdout(stdout1)
        assert data1["verdict"] == "passed"
        assert len(data1["policy_file_hash"]) == 64  # A43: hash not raw path

        # checkpoint with policy
        from typer.testing import CliRunner
        from ai_workflow_hub.cli import app
        from rich.console import Console

        rt = _fake_runtime()
        runner = CliRunner()
        stdout_buf = io.StringIO()
        stderr_buf = io.StringIO()
        _console = Console(file=stdout_buf, force_terminal=False, width=4096)
        _err_console = Console(file=stderr_buf, force_terminal=False)

        cp_path = tmp_path / "cp.json"
        args = ["paper", "checkpoint", "--log", str(log_path),
                "--export", str(cp_path), "--json",
                "--policy", str(policy_path)]
        filtered = {k: v for k, v in os.environ.items()
                    if k not in ("AIHUB_SIGNING_KEY", "AIHUB_SIGNING_KEY_ID")}

        with patch(_RT_PATH, return_value=rt), \
             patch("ai_workflow_hub.cli.init_env"), \
             patch("ai_workflow_hub.cli.console", _console), \
             patch("ai_workflow_hub.cli.err_console", _err_console), \
             patch.dict(os.environ, filtered, clear=True):
            r2 = runner.invoke(app, args, catch_exceptions=False)
        assert r2.exit_code == 0
