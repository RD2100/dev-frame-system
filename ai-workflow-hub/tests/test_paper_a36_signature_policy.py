"""A36 — Signature Policy Tests.

Covers the A36 features:

 1. --signature-policy required: blocks unsigned/invalid/mismatched
 2. --signature-policy optional: warns but does not block
 3. --signature-policy off: skips all signature checks
 4. --expected-key-id: key ID policy enforcement
 5. signature_status field in JSON output
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

def _write_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


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


# ===========================================================================
# 1. Signature policy: required
# ===========================================================================

class TestA36SignaturePolicyRequired:
    def test_required_signed_valid_passes(self, tmp_path):
        """Signed checkpoint with valid key + required policy → pass."""
        log_path = tmp_path / "log.jsonl"
        log_path.write_text(_build_anchor_log(_make_entries()), encoding="utf-8")

        cp_path = tmp_path / "signed.json"
        _invoke_checkpoint(
            log_path, extra_args=["--export", str(cp_path), "--sign"],
            env_overrides={"AIHUB_SIGNING_KEY": "correct-key"})

        r, stdout, _ = _invoke_checkpoint(
            log_path,
            extra_args=["--verify", str(cp_path), "--signature-policy", "required"],
            env_overrides={"AIHUB_SIGNING_KEY": "correct-key"})
        assert r.exit_code == 0
        data = _get_json_from_stdout(stdout)
        assert data["signature_policy"] == "required"
        assert data["signature_status"] == "signed_valid"
        assert data["signature_policy_pass"] is True
        assert data["verdict"] == "passed"

    def test_required_unsigned_fails(self, tmp_path):
        """Unsigned checkpoint + required policy → fail (signature_required_missing)."""
        log_path = tmp_path / "log.jsonl"
        log_path.write_text(_build_anchor_log(_make_entries()), encoding="utf-8")

        cp_path = tmp_path / "unsigned.json"
        _invoke_checkpoint(log_path, extra_args=["--export", str(cp_path)])

        r, stdout, _ = _invoke_checkpoint(
            log_path,
            extra_args=["--verify", str(cp_path), "--signature-policy", "required"],
            env_overrides={})
        assert r.exit_code == 1
        data = _get_json_from_stdout(stdout)
        assert data["signature_policy"] == "required"
        assert data["signature_status"] == "signature_required_missing"
        assert data["signature_policy_pass"] is False
        assert data["verdict"] == "failed"

    def test_required_wrong_key_fails(self, tmp_path):
        """Signed with one key, verified with different key + required → fail."""
        log_path = tmp_path / "log.jsonl"
        log_path.write_text(_build_anchor_log(_make_entries()), encoding="utf-8")

        cp_path = tmp_path / "signed.json"
        _invoke_checkpoint(
            log_path, extra_args=["--export", str(cp_path), "--sign"],
            env_overrides={"AIHUB_SIGNING_KEY": "key-A"})

        r, stdout, _ = _invoke_checkpoint(
            log_path,
            extra_args=["--verify", str(cp_path), "--signature-policy", "required"],
            env_overrides={"AIHUB_SIGNING_KEY": "key-B"})
        assert r.exit_code == 1
        data = _get_json_from_stdout(stdout)
        assert data["signature_policy"] == "required"
        assert data["signature_status"] == "signed_invalid"
        assert data["signature_policy_pass"] is False
        assert data["signature_valid"] is False

    def test_required_no_key_fails(self, tmp_path):
        """Signed checkpoint, but verification key not available + required → fail."""
        log_path = tmp_path / "log.jsonl"
        log_path.write_text(_build_anchor_log(_make_entries()), encoding="utf-8")

        cp_path = tmp_path / "signed.json"
        _invoke_checkpoint(
            log_path, extra_args=["--export", str(cp_path), "--sign"],
            env_overrides={"AIHUB_SIGNING_KEY": "some-key"})

        r, stdout, _ = _invoke_checkpoint(
            log_path,
            extra_args=["--verify", str(cp_path), "--signature-policy", "required"],
            env_overrides={})  # No AIHUB_SIGNING_KEY
        assert r.exit_code == 1
        data = _get_json_from_stdout(stdout)
        assert data["signature_policy"] == "required"
        assert data["signature_status"] == "signed_unverified"
        assert data["signature_policy_pass"] is False


# ===========================================================================
# 2. Signature policy: optional
# ===========================================================================

class TestA36SignaturePolicyOptional:
    def test_optional_signed_valid_passes(self, tmp_path):
        """Signed valid checkpoint + optional policy → pass."""
        log_path = tmp_path / "log.jsonl"
        log_path.write_text(_build_anchor_log(_make_entries()), encoding="utf-8")

        cp_path = tmp_path / "signed.json"
        _invoke_checkpoint(
            log_path, extra_args=["--export", str(cp_path), "--sign"],
            env_overrides={"AIHUB_SIGNING_KEY": "mykey"})

        r, stdout, _ = _invoke_checkpoint(
            log_path,
            extra_args=["--verify", str(cp_path), "--signature-policy", "optional"],
            env_overrides={"AIHUB_SIGNING_KEY": "mykey"})
        assert r.exit_code == 0
        data = _get_json_from_stdout(stdout)
        assert data["signature_policy"] == "optional"
        assert data["signature_status"] == "signed_valid"
        assert data["signature_policy_pass"] is True

    def test_optional_unsigned_passes(self, tmp_path):
        """Unsigned checkpoint + optional policy → pass (warning only)."""
        log_path = tmp_path / "log.jsonl"
        log_path.write_text(_build_anchor_log(_make_entries()), encoding="utf-8")

        cp_path = tmp_path / "unsigned.json"
        _invoke_checkpoint(log_path, extra_args=["--export", str(cp_path)])

        r, stdout, _ = _invoke_checkpoint(
            log_path,
            extra_args=["--verify", str(cp_path), "--signature-policy", "optional"],
            env_overrides={})
        assert r.exit_code == 0  # Not blocking
        data = _get_json_from_stdout(stdout)
        assert data["signature_policy"] == "optional"
        assert data["signature_status"] == "unsigned"
        assert data["signature_policy_pass"] is True

    def test_optional_wrong_key_passes(self, tmp_path):
        """Signed with wrong key + optional policy → pass (warning only)."""
        log_path = tmp_path / "log.jsonl"
        log_path.write_text(_build_anchor_log(_make_entries()), encoding="utf-8")

        cp_path = tmp_path / "signed.json"
        _invoke_checkpoint(
            log_path, extra_args=["--export", str(cp_path), "--sign"],
            env_overrides={"AIHUB_SIGNING_KEY": "key-A"})

        r, stdout, _ = _invoke_checkpoint(
            log_path,
            extra_args=["--verify", str(cp_path), "--signature-policy", "optional"],
            env_overrides={"AIHUB_SIGNING_KEY": "key-B"})
        assert r.exit_code == 0  # Warning only
        data = _get_json_from_stdout(stdout)
        assert data["signature_policy"] == "optional"
        assert data["signature_status"] == "signed_invalid"
        assert data["signature_policy_pass"] is True


# ===========================================================================
# 3. Signature policy: off
# ===========================================================================

class TestA36SignaturePolicyOff:
    def test_off_unsigned_passes(self, tmp_path):
        """Unsigned checkpoint + off policy → pass (skip checks)."""
        log_path = tmp_path / "log.jsonl"
        log_path.write_text(_build_anchor_log(_make_entries()), encoding="utf-8")

        cp_path = tmp_path / "unsigned.json"
        _invoke_checkpoint(log_path, extra_args=["--export", str(cp_path)])

        r, stdout, _ = _invoke_checkpoint(
            log_path,
            extra_args=["--verify", str(cp_path), "--signature-policy", "off"],
            env_overrides={})
        assert r.exit_code == 0
        data = _get_json_from_stdout(stdout)
        assert data["signature_policy"] == "off"
        assert data["signature_policy_pass"] is True

    def test_off_wrong_key_ignored(self, tmp_path):
        """Signed invalid + off policy → pass (signature ignored entirely)."""
        log_path = tmp_path / "log.jsonl"
        log_path.write_text(_build_anchor_log(_make_entries()), encoding="utf-8")

        cp_path = tmp_path / "signed.json"
        _invoke_checkpoint(
            log_path, extra_args=["--export", str(cp_path), "--sign"],
            env_overrides={"AIHUB_SIGNING_KEY": "key-A"})

        r, stdout, _ = _invoke_checkpoint(
            log_path,
            extra_args=["--verify", str(cp_path), "--signature-policy", "off"],
            env_overrides={"AIHUB_SIGNING_KEY": "completely-wrong-key"})
        assert r.exit_code == 0
        data = _get_json_from_stdout(stdout)
        assert data["signature_policy"] == "off"
        assert data["signature_policy_pass"] is True


# ===========================================================================
# 4. Key ID policy
# ===========================================================================

class TestA36KeyIdPolicy:
    def test_key_id_match_required_passes(self, tmp_path):
        """Correct key ID + required policy → pass."""
        log_path = tmp_path / "log.jsonl"
        log_path.write_text(_build_anchor_log(_make_entries()), encoding="utf-8")

        cp_path = tmp_path / "signed.json"
        _invoke_checkpoint(
            log_path, extra_args=["--export", str(cp_path), "--sign"],
            env_overrides={"AIHUB_SIGNING_KEY": "mykey", "AIHUB_SIGNING_KEY_ID": "kid-1"})

        r, stdout, _ = _invoke_checkpoint(
            log_path,
            extra_args=["--verify", str(cp_path), "--signature-policy", "required",
                         "--expected-key-id", "kid-1"],
            env_overrides={"AIHUB_SIGNING_KEY": "mykey", "AIHUB_SIGNING_KEY_ID": "kid-1"})
        assert r.exit_code == 0
        data = _get_json_from_stdout(stdout)
        assert data["signature_status"] == "signed_valid"
        assert data["key_id_match"] is True
        assert data["expected_key_id"] == "kid-1"

    def test_key_id_mismatch_required_fails(self, tmp_path):
        """Wrong key ID + required policy → fail."""
        log_path = tmp_path / "log.jsonl"
        log_path.write_text(_build_anchor_log(_make_entries()), encoding="utf-8")

        cp_path = tmp_path / "signed.json"
        _invoke_checkpoint(
            log_path, extra_args=["--export", str(cp_path), "--sign"],
            env_overrides={"AIHUB_SIGNING_KEY": "mykey", "AIHUB_SIGNING_KEY_ID": "kid-1"})

        r, stdout, _ = _invoke_checkpoint(
            log_path,
            extra_args=["--verify", str(cp_path), "--signature-policy", "required",
                         "--expected-key-id", "kid-2"],
            env_overrides={"AIHUB_SIGNING_KEY": "mykey", "AIHUB_SIGNING_KEY_ID": "kid-2"})
        assert r.exit_code == 1
        data = _get_json_from_stdout(stdout)
        assert data["key_id_match"] is False
        assert data["signature_policy_pass"] is False

    def test_key_id_mismatch_optional_passes(self, tmp_path):
        """Wrong key ID + optional policy → pass (warning only)."""
        log_path = tmp_path / "log.jsonl"
        log_path.write_text(_build_anchor_log(_make_entries()), encoding="utf-8")

        cp_path = tmp_path / "signed.json"
        _invoke_checkpoint(
            log_path, extra_args=["--export", str(cp_path), "--sign"],
            env_overrides={"AIHUB_SIGNING_KEY": "mykey", "AIHUB_SIGNING_KEY_ID": "kid-1"})

        r, stdout, _ = _invoke_checkpoint(
            log_path,
            extra_args=["--verify", str(cp_path), "--signature-policy", "optional",
                         "--expected-key-id", "kid-2"],
            env_overrides={"AIHUB_SIGNING_KEY": "mykey", "AIHUB_SIGNING_KEY_ID": "kid-2"})
        assert r.exit_code == 0  # Warning only
        data = _get_json_from_stdout(stdout)
        assert data["key_id_match"] is False
        assert data["signature_policy_pass"] is True


# ===========================================================================
# 5. Integration
# ===========================================================================

class TestA36Integration:
    def test_full_policy_workflow(self, tmp_path):
        """Export signed → verify required pass → tamper → verify required fail."""
        log_path = tmp_path / "integ.jsonl"
        entries = _make_entries(2)
        log_path.write_text(_build_anchor_log(entries), encoding="utf-8")

        # 1. Export signed checkpoint
        cp_path = tmp_path / "cp.json"
        r, _, _ = _invoke_checkpoint(
            log_path, extra_args=["--export", str(cp_path), "--sign"],
            env_overrides={"AIHUB_SIGNING_KEY": "integ-key", "AIHUB_SIGNING_KEY_ID": "k1"})
        assert r.exit_code == 0

        # 2. Verify with required policy → should pass
        r2, stdout2, _ = _invoke_checkpoint(
            log_path,
            extra_args=["--verify", str(cp_path), "--signature-policy", "required",
                         "--expected-key-id", "k1"],
            env_overrides={"AIHUB_SIGNING_KEY": "integ-key", "AIHUB_SIGNING_KEY_ID": "k1"})
        assert r2.exit_code == 0
        data2 = _get_json_from_stdout(stdout2)
        assert data2["verdict"] == "passed"
        assert data2["signature_status"] == "signed_valid"
        assert data2["key_id_match"] is True

        # 3. Tamper with log (add entry)
        entries_extra = _make_entries(3)
        log_path.write_text(_build_anchor_log(entries_extra), encoding="utf-8")

        # 4. Verify again with required → should fail (hash mismatch)
        r3, stdout3, _ = _invoke_checkpoint(
            log_path,
            extra_args=["--verify", str(cp_path), "--signature-policy", "required"],
            env_overrides={"AIHUB_SIGNING_KEY": "integ-key"})
        assert r3.exit_code == 1
        data3 = _get_json_from_stdout(stdout3)
        assert data3["verdict"] == "failed"
        assert data3["head_hash_match"] is False

        # 5. Same scenario with off policy → signature check skipped, but hash still fails
        r4, stdout4, _ = _invoke_checkpoint(
            log_path,
            extra_args=["--verify", str(cp_path), "--signature-policy", "off"],
            env_overrides={})
        assert r4.exit_code == 1
        data4 = _get_json_from_stdout(stdout4)
        assert data4["signature_policy"] == "off"
        assert data4["head_hash_match"] is False
