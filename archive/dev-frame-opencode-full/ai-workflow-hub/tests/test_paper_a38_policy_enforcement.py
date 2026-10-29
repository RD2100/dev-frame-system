"""A38 — Policy Enforcement Tests.

Covers the A38 features:

 1. chain_verification_mode enforcement from policy
 2. required_artifacts enforcement
 3. strict_timestamps policy enforcement annotation
 4. allowed_key_ids element type validation
 5. required_artifacts list type validation
 6. Full integration: policy-enforced verify-chain
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
        "description": "A38 test policy",
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
# 1. chain_verification_mode enforcement
# ===========================================================================

class TestA38ChainModeEnforcement:
    def test_chain_only_policy_passes_chain_only(self, tmp_path):
        """chain_only policy + chain_only mode → pass."""
        policy_path = tmp_path / "policy.json"
        _write_policy(policy_path, _valid_policy(chain_verification_mode="chain_only"))

        log_path = tmp_path / "log.jsonl"
        log_path.write_text(_build_anchor_log(_make_entries(2)), encoding="utf-8")

        r, stdout, _ = _invoke_verify_chain(
            log_path, extra_args=["--policy", str(policy_path)])
        assert r.exit_code == 0
        data = _get_json_from_stdout(stdout)
        checks = {c["check"]: c for c in data["checks"]}
        assert checks["policy_chain_mode"]["passed"] is True

    def test_chain_plus_zip_policy_fails_without_zip(self, tmp_path):
        """chain_plus_zip policy + no zip-dir → fail (chain_only actual)."""
        policy_path = tmp_path / "policy.json"
        _write_policy(policy_path, _valid_policy(chain_verification_mode="chain_plus_zip"))

        log_path = tmp_path / "log.jsonl"
        log_path.write_text(_build_anchor_log(_make_entries()), encoding="utf-8")

        r, stdout, _ = _invoke_verify_chain(
            log_path, extra_args=["--policy", str(policy_path)])
        assert r.exit_code == 1
        data = _get_json_from_stdout(stdout)
        checks = {c["check"]: c for c in data["checks"]}
        assert checks["policy_chain_mode"]["passed"] is False
        assert "chain_plus_zip" in checks["policy_chain_mode"]["detail"]

    def test_chain_only_policy_fails_on_partial(self, tmp_path):
        """chain_only policy + chain_partial mode → fail."""
        policy_path = tmp_path / "policy.json"
        _write_policy(policy_path, _valid_policy(
            chain_verification_mode="chain_only",
            strict_chain=False))

        log_path = tmp_path / "log.jsonl"
        log_path.write_text(_build_anchor_log(_make_entries()), encoding="utf-8")

        # chain_partial happens when --zip-dir is given but no ZIPs found
        zip_dir = tmp_path / "empty_zips"
        zip_dir.mkdir()
        r, stdout, _ = _invoke_verify_chain(
            log_path,
            extra_args=["--policy", str(policy_path), "--zip-dir", str(zip_dir)])
        data = _get_json_from_stdout(stdout)
        checks = {c["check"]: c for c in data["checks"]}
        # Should fail because policy says chain_only but actual is chain_partial
        assert checks["policy_chain_mode"]["passed"] is False


# ===========================================================================
# 2. required_artifacts enforcement
# ===========================================================================

class TestA38RequiredArtifacts:
    def test_required_artifacts_all_present(self, tmp_path):
        """All required artifacts present → pass."""
        run_dir = tmp_path / "run-a38"
        run_dir.mkdir()
        log_path = run_dir / "log.jsonl"
        log_path.write_text(_build_anchor_log(_make_entries()), encoding="utf-8")

        # Create required artifact files
        (run_dir / "state.json").write_text("{}", encoding="utf-8")
        (run_dir / "ledger.json").write_text("{}", encoding="utf-8")

        policy_path = tmp_path / "policy.json"
        _write_policy(policy_path, _valid_policy(
            required_artifacts=["state.json", "ledger.json"]))

        r, stdout, _ = _invoke_verify_chain(
            log_path, extra_args=["--policy", str(policy_path)])
        assert r.exit_code == 0
        data = _get_json_from_stdout(stdout)
        checks = {c["check"]: c for c in data["checks"]}
        assert checks["policy_required_artifacts"]["passed"] is True
        assert "2 required" in checks["policy_required_artifacts"]["detail"]

    def test_required_artifacts_missing(self, tmp_path):
        """Missing required artifact → fail."""
        run_dir = tmp_path / "run-a38"
        run_dir.mkdir()
        log_path = run_dir / "log.jsonl"
        log_path.write_text(_build_anchor_log(_make_entries()), encoding="utf-8")

        # Only create state.json, NOT ledger.json
        (run_dir / "state.json").write_text("{}", encoding="utf-8")

        policy_path = tmp_path / "policy.json"
        _write_policy(policy_path, _valid_policy(
            required_artifacts=["state.json", "ledger.json"]))

        r, stdout, _ = _invoke_verify_chain(
            log_path, extra_args=["--policy", str(policy_path)])
        assert r.exit_code == 1
        data = _get_json_from_stdout(stdout)
        checks = {c["check"]: c for c in data["checks"]}
        assert checks["policy_required_artifacts"]["passed"] is False
        assert "ledger.json" in checks["policy_required_artifacts"]["detail"]

    def test_no_required_artifacts_skips_check(self, tmp_path):
        """Empty required_artifacts → no check added."""
        policy_path = tmp_path / "policy.json"
        _write_policy(policy_path, _valid_policy(required_artifacts=[]))

        log_path = tmp_path / "log.jsonl"
        log_path.write_text(_build_anchor_log(_make_entries()), encoding="utf-8")

        r, stdout, _ = _invoke_verify_chain(
            log_path, extra_args=["--policy", str(policy_path)])
        assert r.exit_code == 0
        data = _get_json_from_stdout(stdout)
        checks = {c["check"]: c for c in data["checks"]}
        assert "policy_required_artifacts" not in checks


# ===========================================================================
# 3. Element type validation
# ===========================================================================

class TestA38ElementValidation:
    def test_empty_string_key_id_rejected(self, tmp_path):
        """Empty string in allowed_key_ids should be rejected."""
        policy_path = tmp_path / "bad.json"
        _write_policy(policy_path, _valid_policy(allowed_key_ids=["valid", ""]))

        log_path = tmp_path / "log.jsonl"
        log_path.write_text(_build_anchor_log(_make_entries()), encoding="utf-8")

        r, _, _ = _invoke_checkpoint(
            log_path, extra_args=["--policy", str(policy_path)])
        assert r.exit_code == 1

    def test_non_string_key_id_rejected(self, tmp_path):
        """Non-string in allowed_key_ids should be rejected."""
        policy_path = tmp_path / "bad.json"
        policy = _valid_policy()
        policy["allowed_key_ids"] = ["valid", 123]  # int not allowed
        _write_policy(policy_path, policy)

        log_path = tmp_path / "log.jsonl"
        log_path.write_text(_build_anchor_log(_make_entries()), encoding="utf-8")

        r, _, _ = _invoke_checkpoint(
            log_path, extra_args=["--policy", str(policy_path)])
        assert r.exit_code == 1

    def test_required_artifacts_non_list_rejected(self, tmp_path):
        """Non-list required_artifacts should be rejected."""
        policy_path = tmp_path / "bad.json"
        policy = _valid_policy()
        policy["required_artifacts"] = "not-a-list"
        _write_policy(policy_path, policy)

        log_path = tmp_path / "log.jsonl"
        log_path.write_text(_build_anchor_log(_make_entries()), encoding="utf-8")

        r, _, _ = _invoke_checkpoint(
            log_path, extra_args=["--policy", str(policy_path)])
        assert r.exit_code == 1


# ===========================================================================
# 4. strict_timestamps enforcement
# ===========================================================================

class TestA38StrictTimestamps:
    def test_strict_timestamps_annotates_failure(self, tmp_path):
        """strict_timestamps=True should annotate timestamp failures."""
        policy_path = tmp_path / "policy.json"
        _write_policy(policy_path, _valid_policy(strict_timestamps=True))

        log_path = tmp_path / "log.jsonl"
        # Create entries with naive timestamps (no Z suffix)
        entries = [
            {"timestamp": "2026-06-12T00:00:00", "bundle_id": "b0",
             "run_id": "r0", "zip_sha256": "0" * 64},
        ]
        log_path.write_text(_build_anchor_log(entries), encoding="utf-8")

        r, stdout, _ = _invoke_verify_chain(
            log_path, extra_args=["--policy", str(policy_path)])
        data = _get_json_from_stdout(stdout)
        checks = {c["check"]: c for c in data["checks"]}
        ts_check = checks.get("timestamp_format_iso8601")
        assert ts_check is not None
        assert ts_check["passed"] is False
        assert "policy: strict_timestamps" in ts_check["detail"]


# ===========================================================================
# 5. Integration
# ===========================================================================

class TestA38Integration:
    def test_full_policy_enforcement_workflow(self, tmp_path):
        """Full workflow: policy with all enforcement features."""
        run_dir = tmp_path / "integ-run"
        run_dir.mkdir()
        log_path = run_dir / "log.jsonl"
        entries = _make_entries(2)
        log_path.write_text(_build_anchor_log(entries), encoding="utf-8")

        # Create required artifacts
        (run_dir / "state.json").write_text("{}", encoding="utf-8")

        # Create policy requiring chain_only + state.json
        policy_path = tmp_path / "policy.json"
        _write_policy(policy_path, _valid_policy(
            chain_verification_mode="chain_only",
            required_artifacts=["state.json"],
            strict_timestamps=True,
            description="Full A38 integration policy"))

        # Verify with policy → should pass
        r, stdout, _ = _invoke_verify_chain(
            log_path, extra_args=["--policy", str(policy_path)])
        assert r.exit_code == 0
        data = _get_json_from_stdout(stdout)
        assert data["verdict"] == "passed"
        checks = {c["check"]: c for c in data["checks"]}
        assert checks["policy_chain_mode"]["passed"] is True
        assert checks["policy_required_artifacts"]["passed"] is True

        # Now remove the artifact and re-verify → should fail
        (run_dir / "state.json").unlink()
        r2, stdout2, _ = _invoke_verify_chain(
            log_path, extra_args=["--policy", str(policy_path)])
        assert r2.exit_code == 1
        data2 = _get_json_from_stdout(stdout2)
        checks2 = {c["check"]: c for c in data2["checks"]}
        assert checks2["policy_required_artifacts"]["passed"] is False
