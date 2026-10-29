"""A37 — Audit Policy Schema Tests.

Covers the A37 features:

 1. _load_audit_policy: load valid policy file
 2. _load_audit_policy: reject invalid schema_version
 3. _load_audit_policy: reject invalid signature_policy
 4. _load_audit_policy: reject invalid chain_verification_mode
 5. _load_audit_policy: reject missing file
 6. _load_audit_policy: reject invalid JSON
 7. --policy on checkpoint: overrides signature_policy
 8. --policy on checkpoint: overrides expected_key_id from allowed_key_ids
 9. --policy on checkpoint: multiple allowed_key_ids
10. --policy on verify-chain: overrides strict_chain
11. Policy JSON output fields
12. Full integration: policy-driven checkpoint workflow
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
        "signature_policy": "required",
        "allowed_key_ids": ["kid-1"],
        "chain_verification_mode": "chain_only",
        "strict_chain": True,
        "strict_timestamps": True,
        "required_artifacts": ["state.json"],
        "description": "Test policy A37",
    }
    base.update(overrides)
    return base


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
# 1. Policy loading — valid policy
# ===========================================================================

class TestA37PolicyLoading:
    def test_load_valid_policy(self, tmp_path):
        """Valid policy file should load without error."""
        policy_path = tmp_path / "policy.json"
        _write_policy(policy_path, _valid_policy())

        log_path = tmp_path / "log.jsonl"
        log_path.write_text(_build_anchor_log(_make_entries()), encoding="utf-8")

        cp_path = tmp_path / "cp.json"
        r, stdout, _ = _invoke_checkpoint(
            log_path,
            extra_args=["--export", str(cp_path), "--policy", str(policy_path)],
            env_overrides={"AIHUB_SIGNING_KEY": "k", "AIHUB_SIGNING_KEY_ID": "kid-1"})
        assert r.exit_code == 0

    def test_reject_invalid_schema_version(self, tmp_path):
        """Invalid schema_version should fail with exit 1."""
        policy_path = tmp_path / "bad_schema.json"
        _write_policy(policy_path, _valid_policy(schema_version="9.9"))

        log_path = tmp_path / "log.jsonl"
        log_path.write_text(_build_anchor_log(_make_entries()), encoding="utf-8")

        r, _, stderr = _invoke_checkpoint(
            log_path,
            extra_args=["--policy", str(policy_path)])
        assert r.exit_code == 1

    def test_reject_invalid_signature_policy(self, tmp_path):
        """Invalid signature_policy value should be rejected."""
        policy_path = tmp_path / "bad_sig.json"
        _write_policy(policy_path, _valid_policy(signature_policy="invalid_value"))

        log_path = tmp_path / "log.jsonl"
        log_path.write_text(_build_anchor_log(_make_entries()), encoding="utf-8")

        r, _, stderr = _invoke_checkpoint(
            log_path,
            extra_args=["--policy", str(policy_path)])
        assert r.exit_code == 1

    def test_reject_invalid_chain_mode(self, tmp_path):
        """Invalid chain_verification_mode should be rejected."""
        policy_path = tmp_path / "bad_mode.json"
        _write_policy(policy_path, _valid_policy(chain_verification_mode="invalid_mode"))

        log_path = tmp_path / "log.jsonl"
        log_path.write_text(_build_anchor_log(_make_entries()), encoding="utf-8")

        r, _, stderr = _invoke_checkpoint(
            log_path,
            extra_args=["--policy", str(policy_path)])
        assert r.exit_code == 1

    def test_reject_missing_file(self, tmp_path):
        """Non-existent policy file should fail."""
        log_path = tmp_path / "log.jsonl"
        log_path.write_text(_build_anchor_log(_make_entries()), encoding="utf-8")

        r, _, stderr = _invoke_checkpoint(
            log_path,
            extra_args=["--policy", str(tmp_path / "nonexistent.json")])
        assert r.exit_code == 1

    def test_reject_invalid_json(self, tmp_path):
        """Malformed JSON should fail."""
        policy_path = tmp_path / "bad.json"
        policy_path.write_text("{invalid json!!!", encoding="utf-8")

        log_path = tmp_path / "log.jsonl"
        log_path.write_text(_build_anchor_log(_make_entries()), encoding="utf-8")

        r, _, stderr = _invoke_checkpoint(
            log_path,
            extra_args=["--policy", str(policy_path)])
        assert r.exit_code == 1


# ===========================================================================
# 2. Policy overrides CLI flags
# ===========================================================================

class TestA37PolicyOverrides:
    def test_policy_overrides_signature_policy(self, tmp_path):
        """Policy signature_policy=required should override CLI default (optional)."""
        policy_path = tmp_path / "policy.json"
        _write_policy(policy_path, _valid_policy(signature_policy="required"))

        log_path = tmp_path / "log.jsonl"
        log_path.write_text(_build_anchor_log(_make_entries()), encoding="utf-8")

        cp_path = tmp_path / "unsigned.json"
        _invoke_checkpoint(log_path, extra_args=["--export", str(cp_path)])

        # CLI would default to optional, but policy forces required
        r, stdout, _ = _invoke_checkpoint(
            log_path,
            extra_args=["--verify", str(cp_path), "--policy", str(policy_path)],
            env_overrides={})
        assert r.exit_code == 1  # required + unsigned = fail
        data = _get_json_from_stdout(stdout)
        assert data["signature_policy"] == "required"
        assert data["signature_status"] == "signature_required_missing"

    def test_policy_allowed_key_ids_match(self, tmp_path):
        """Checkpoint key_id in allowed_key_ids list should pass."""
        policy_path = tmp_path / "policy.json"
        _write_policy(policy_path, _valid_policy(
            signature_policy="required",
            allowed_key_ids=["kid-1", "kid-2", "kid-3"]))

        log_path = tmp_path / "log.jsonl"
        log_path.write_text(_build_anchor_log(_make_entries()), encoding="utf-8")

        cp_path = tmp_path / "signed.json"
        _invoke_checkpoint(
            log_path, extra_args=["--export", str(cp_path), "--sign"],
            env_overrides={"AIHUB_SIGNING_KEY": "mykey", "AIHUB_SIGNING_KEY_ID": "kid-2"})

        r, stdout, _ = _invoke_checkpoint(
            log_path,
            extra_args=["--verify", str(cp_path), "--policy", str(policy_path)],
            env_overrides={"AIHUB_SIGNING_KEY": "mykey", "AIHUB_SIGNING_KEY_ID": "kid-2"})
        assert r.exit_code == 0
        data = _get_json_from_stdout(stdout)
        assert data["key_id_match"] is True
        assert data["allowed_key_ids"] == ["kid-1", "kid-2", "kid-3"]

    def test_policy_key_id_not_in_list_fails(self, tmp_path):
        """Checkpoint key_id not in allowed_key_ids should fail under required."""
        policy_path = tmp_path / "policy.json"
        _write_policy(policy_path, _valid_policy(
            signature_policy="required",
            allowed_key_ids=["kid-1"]))

        log_path = tmp_path / "log.jsonl"
        log_path.write_text(_build_anchor_log(_make_entries()), encoding="utf-8")

        cp_path = tmp_path / "signed.json"
        _invoke_checkpoint(
            log_path, extra_args=["--export", str(cp_path), "--sign"],
            env_overrides={"AIHUB_SIGNING_KEY": "mykey", "AIHUB_SIGNING_KEY_ID": "kid-999"})

        r, stdout, _ = _invoke_checkpoint(
            log_path,
            extra_args=["--verify", str(cp_path), "--policy", str(policy_path)],
            env_overrides={"AIHUB_SIGNING_KEY": "mykey", "AIHUB_SIGNING_KEY_ID": "kid-999"})
        assert r.exit_code == 1
        data = _get_json_from_stdout(stdout)
        assert data["key_id_match"] is False


# ===========================================================================
# 3. Policy on verify-chain
# ===========================================================================

class TestA37VerifyChainPolicy:
    def test_policy_strict_chain_override(self, tmp_path):
        """Policy strict_chain=True should override CLI --strict-chain."""
        policy_path = tmp_path / "policy.json"
        _write_policy(policy_path, _valid_policy(strict_chain=True))

        log_path = tmp_path / "log.jsonl"
        entries = _make_entries(2)
        log_path.write_text(_build_anchor_log(entries), encoding="utf-8")

        # Without policy, no strict-chain → would pass
        # With policy strict_chain=True → depends on chain_partial
        r, stdout, _ = _invoke_verify_chain(
            log_path,
            extra_args=["--policy", str(policy_path)])
        data = _get_json_from_stdout(stdout)
        assert "policy_file_hash" in data
        assert data["policy_schema_version"] == "1.0"
        assert data["policy_strict_chain"] is True

    def test_policy_info_in_json_output(self, tmp_path):
        """Policy metadata should appear in JSON output."""
        policy_path = tmp_path / "policy.json"
        _write_policy(policy_path, _valid_policy(
            allowed_key_ids=["k1", "k2"]))

        log_path = tmp_path / "log.jsonl"
        log_path.write_text(_build_anchor_log(_make_entries()), encoding="utf-8")

        r, stdout, _ = _invoke_verify_chain(
            log_path,
            extra_args=["--policy", str(policy_path)])
        data = _get_json_from_stdout(stdout)
        assert len(data["policy_file_hash"]) == 64  # A43: hash not raw path
        assert data["policy_schema_version"] == "1.0"
        assert data["allowed_key_ids"] == ["k1", "k2"]


# ===========================================================================
# 4. Integration
# ===========================================================================

class TestA37Integration:
    def test_full_policy_driven_workflow(self, tmp_path):
        """Export signed → policy verify required → pass → tamper → fail."""
        log_path = tmp_path / "integ.jsonl"
        entries = _make_entries(2)
        log_path.write_text(_build_anchor_log(entries), encoding="utf-8")

        # 1. Create policy
        policy_path = tmp_path / "policy.json"
        _write_policy(policy_path, _valid_policy(
            signature_policy="required",
            allowed_key_ids=["integ-kid"],
            strict_chain=True,
            description="Integration test policy"))

        # 2. Export signed checkpoint with matching key_id
        cp_path = tmp_path / "cp.json"
        r, _, _ = _invoke_checkpoint(
            log_path,
            extra_args=["--export", str(cp_path), "--sign",
                         "--policy", str(policy_path)],
            env_overrides={"AIHUB_SIGNING_KEY": "integ-key",
                           "AIHUB_SIGNING_KEY_ID": "integ-kid"})
        assert r.exit_code == 0

        # 3. Verify with policy → should pass
        r2, stdout2, _ = _invoke_checkpoint(
            log_path,
            extra_args=["--verify", str(cp_path), "--policy", str(policy_path)],
            env_overrides={"AIHUB_SIGNING_KEY": "integ-key",
                           "AIHUB_SIGNING_KEY_ID": "integ-kid"})
        assert r2.exit_code == 0
        data2 = _get_json_from_stdout(stdout2)
        assert data2["verdict"] == "passed"
        assert data2["signature_policy"] == "required"
        assert data2["signature_status"] == "signed_valid"
        assert data2["key_id_match"] is True
        assert len(data2["policy_file_hash"]) == 64  # A43: hash not raw path

        # 4. Tamper with log
        entries_extra = _make_entries(3)
        log_path.write_text(_build_anchor_log(entries_extra), encoding="utf-8")

        # 5. Verify again with policy → should fail (hash mismatch)
        r3, stdout3, _ = _invoke_checkpoint(
            log_path,
            extra_args=["--verify", str(cp_path), "--policy", str(policy_path)],
            env_overrides={"AIHUB_SIGNING_KEY": "integ-key",
                           "AIHUB_SIGNING_KEY_ID": "integ-kid"})
        assert r3.exit_code == 1
        data3 = _get_json_from_stdout(stdout3)
        assert data3["verdict"] == "failed"
        assert data3["head_hash_match"] is False
