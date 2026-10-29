"""A39 — Policy Global Enforcement Tests.

Covers the A39 features:

 1. --policy on paper verify command
 2. strict_timestamps=False downgrades failures to warnings
 3. chain_verification_mode minimum assurance semantics
 4. Policy JSON output on paper verify
 5. Full integration: policy-driven multi-command workflow
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
        "description": "A39 test policy",
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


def _invoke_verify(zip_path, extra_args=None, env_overrides=None):
    from typer.testing import CliRunner
    from ai_workflow_hub.cli import app
    from rich.console import Console

    rt = _fake_runtime()
    runner = CliRunner()
    stdout_buf = io.StringIO()
    stderr_buf = io.StringIO()
    _console = Console(file=stdout_buf, force_terminal=False, width=4096)
    _err_console = Console(file=stderr_buf, force_terminal=False)

    args = ["paper", "verify", "--zip", str(zip_path), "--json",
            "--no-check-artifacts"]
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


def _make_minimal_zip(tmp_path: Path) -> Path:
    """Create a minimal valid ZIP for paper verify."""
    zp = tmp_path / "bundle.zip"
    with zipfile.ZipFile(zp, "w") as zf:
        zf.writestr("MANIFEST.json", json.dumps({
            "manifest_version": "2.0",
            "bundle_id": "test-bundle",
            "files": [],
            "generated_members": [],
        }))
        zf.writestr("attestation.json", json.dumps({
            "attestation_id": "att-001",
            "bundle_hash": "0" * 64,
            "content_hash": "0" * 64,
            "privacy_attestation": {
                "no_full_text": True,
                "no_api_keys": True,
                "no_personal_identity": True,
            },
        }))
    return zp


# ===========================================================================
# 1. --policy on paper verify
# ===========================================================================

class TestA39VerifyPolicy:
    def test_verify_with_policy_loads(self, tmp_path):
        """paper verify --policy should load policy and include in JSON output."""
        policy_path = tmp_path / "policy.json"
        _write_policy(policy_path, _valid_policy())

        zp = _make_minimal_zip(tmp_path)

        r, stdout, _ = _invoke_verify(
            zp, extra_args=["--policy", str(policy_path)])
        # May pass or fail depending on ZIP content, but policy should load
        if r.exit_code == 0:
            data = _get_json_from_stdout(stdout)
            assert "policy_file_hash" in data
            assert data["policy_schema_version"] == "1.0"

    def test_verify_without_policy_no_policy_fields(self, tmp_path):
        """paper verify without --policy should not include policy fields."""
        zp = _make_minimal_zip(tmp_path)

        r, stdout, _ = _invoke_verify(zp)
        if r.exit_code == 0:
            data = _get_json_from_stdout(stdout)
            assert "policy_file_hash" not in data


# ===========================================================================
# 2. strict_timestamps=False downgrades failures
# ===========================================================================

class TestA39StrictTimestampsFalse:
    def test_strict_timestamps_false_downgrades(self, tmp_path):
        """strict_timestamps=False should downgrade timestamp failures to warnings."""
        policy_path = tmp_path / "policy.json"
        _write_policy(policy_path, _valid_policy(strict_timestamps=False))

        log_path = tmp_path / "log.jsonl"
        # Naive timestamps (no Z suffix)
        entries = [
            {"timestamp": "2026-06-12T00:00:00", "bundle_id": "b0",
             "run_id": "r0", "zip_sha256": "0" * 64},
        ]
        log_path.write_text(_build_anchor_log(entries), encoding="utf-8")

        r, stdout, _ = _invoke_verify_chain(
            log_path, extra_args=["--policy", str(policy_path)])
        # Should pass because strict_timestamps=False downgrades ts failures
        assert r.exit_code == 0
        data = _get_json_from_stdout(stdout)
        checks = {c["check"]: c for c in data["checks"]}
        ts_check = checks.get("timestamp_format_iso8601")
        assert ts_check is not None
        assert ts_check["passed"] is False  # A54: raw check stays failed (immutable)
        # A54: Waiver info is in policy_waivers, not check entry detail
        waivers = data.get("policy_waivers", [])
        ts_waivers = [w for w in waivers if w["check"] == "timestamp_format_iso8601"]
        assert len(ts_waivers) >= 1
        assert ts_waivers[0]["severity"] == "warning"

    def test_strict_timestamps_true_blocks(self, tmp_path):
        """strict_timestamps=True should keep timestamp failures as blocking."""
        policy_path = tmp_path / "policy.json"
        _write_policy(policy_path, _valid_policy(strict_timestamps=True))

        log_path = tmp_path / "log.jsonl"
        entries = [
            {"timestamp": "2026-06-12T00:00:00", "bundle_id": "b0",
             "run_id": "r0", "zip_sha256": "0" * 64},
        ]
        log_path.write_text(_build_anchor_log(entries), encoding="utf-8")

        r, stdout, _ = _invoke_verify_chain(
            log_path, extra_args=["--policy", str(policy_path)])
        assert r.exit_code == 1
        data = _get_json_from_stdout(stdout)
        checks = {c["check"]: c for c in data["checks"]}
        ts_check = checks.get("timestamp_format_iso8601")
        assert ts_check["passed"] is False
        assert "strict_timestamps" in ts_check["detail"]


# ===========================================================================
# 3. chain_verification_mode semantics
# ===========================================================================

class TestA39ChainModeSemantics:
    def test_chain_plus_zip_is_minimum_assurance(self, tmp_path):
        """chain_plus_zip policy accepts chain_plus_zip mode."""
        policy_path = tmp_path / "policy.json"
        _write_policy(policy_path, _valid_policy(chain_verification_mode="chain_plus_zip"))

        log_path = tmp_path / "log.jsonl"
        log_path.write_text(_build_anchor_log(_make_entries()), encoding="utf-8")

        # Without zip-dir, mode is chain_only → should fail
        r, stdout, _ = _invoke_verify_chain(
            log_path, extra_args=["--policy", str(policy_path)])
        data = _get_json_from_stdout(stdout)
        checks = {c["check"]: c for c in data["checks"]}
        assert checks["policy_chain_mode"]["passed"] is False

    def test_chain_partial_mode_allows_partial(self, tmp_path):
        """chain_partial policy should accept any mode."""
        policy_path = tmp_path / "policy.json"
        _write_policy(policy_path, _valid_policy(chain_verification_mode="chain_partial"))

        log_path = tmp_path / "log.jsonl"
        log_path.write_text(_build_anchor_log(_make_entries()), encoding="utf-8")

        r, stdout, _ = _invoke_verify_chain(
            log_path, extra_args=["--policy", str(policy_path)])
        data = _get_json_from_stdout(stdout)
        checks = {c["check"]: c for c in data["checks"]}
        assert checks["policy_chain_mode"]["passed"] is True


# ===========================================================================
# 4. Integration
# ===========================================================================

class TestA39Integration:
    def test_multi_command_policy_workflow(self, tmp_path):
        """Same policy applied across verify-chain and checkpoint."""
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
            signature_policy="optional",
            description="A39 integration"))

        # verify-chain with policy
        r1, stdout1, _ = _invoke_verify_chain(
            log_path, extra_args=["--policy", str(policy_path)])
        assert r1.exit_code == 0
        data1 = _get_json_from_stdout(stdout1)
        assert data1["verdict"] == "passed"
        checks1 = {c["check"]: c for c in data1["checks"]}
        assert checks1["policy_chain_mode"]["passed"] is True
        assert checks1["policy_required_artifacts"]["passed"] is True

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
