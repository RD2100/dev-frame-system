"""A31 — Trust Verify Hardening Tests.

Covers the 8 GPT-identified concerns from A30 accepted_with_limitations:

 1. trust_summary field (verified_signed_trusted / verified_unsigned / failed_signed / failed_unsigned)
 2. Anchor log entry chaining (prev_hash)
 3. Key ID support (AIHUB_SIGNING_KEY_ID)
 4. Anchor write timing (before JSON output)
 5. Required files hash validation (file:sha256 format)
 6. Key ID in signature verification output
"""

from __future__ import annotations

import hashlib
import hmac
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


def _make_run_dir(tmp: Path, run_id: str = "paper-test-a31") -> tuple[Path, dict]:
    run_dir = tmp / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    state = {
        "run_id": run_id, "task_id": "task-a31",
        "project_id": "proj-a31", "status": "completed",
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


def _invoke_audit(tmp_path, run_id="paper-a31-test", extra_args=None,
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


def _invoke_verify(zip_path, extra_args=None):
    from typer.testing import CliRunner
    from ai_workflow_hub.cli import app
    from rich.console import Console

    rt = _fake_runtime()
    runner = CliRunner()
    stdout_buf = io.StringIO()
    stderr_buf = io.StringIO()
    _console = Console(file=stdout_buf, force_terminal=False, width=4096)
    _err_console = Console(file=stderr_buf, force_terminal=False)

    args = ["paper", "verify", "--zip", str(zip_path), "--json"]
    if extra_args:
        args.extend(extra_args)

    with patch(_RT_PATH, return_value=rt), \
         patch("ai_workflow_hub.cli.init_env"), \
         patch("ai_workflow_hub.cli.console", _console), \
         patch("ai_workflow_hub.cli.err_console", _err_console):
        result = runner.invoke(app, args, catch_exceptions=False)

    return result, stdout_buf.getvalue(), stderr_buf.getvalue()


def _find_audit_zip(run_dir: Path) -> Path:
    zips = list(run_dir.glob("audit-bundle-*.zip"))
    assert len(zips) == 1
    return zips[0]


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
# 1. trust_summary — combined verdict + trust_level
# ===========================================================================

class TestA31TrustSummary:
    def test_unsigned_passed_has_verified_unsigned(self, tmp_path):
        """Unsigned bundle that passes should have trust_summary='verified_unsigned'."""
        result_audit, run_dir, _, _ = _invoke_audit(tmp_path, "a31-ts-unsigned")
        assert result_audit.exit_code == 0
        zip_path = _find_audit_zip(run_dir)
        result_verify, stdout, _ = _invoke_verify(zip_path)
        data = _get_json_from_stdout(stdout)
        assert data["trust_summary"] == "verified_unsigned"

    def test_signed_passed_has_verified_signed_trusted(self, tmp_path):
        """Signed bundle that passes should have trust_summary='verified_signed_trusted'."""
        key = "ts-key-1"
        with patch.dict(os.environ, {"AIHUB_SIGNING_KEY": key}):
            result_audit, run_dir, _, _ = _invoke_audit(
                tmp_path, "a31-ts-signed", extra_args=["--sign"])
        assert result_audit.exit_code == 0
        zip_path = _find_audit_zip(run_dir)

        with patch.dict(os.environ, {"AIHUB_SIGNING_KEY": key}):
            result_verify, stdout, _ = _invoke_verify(zip_path)
        data = _get_json_from_stdout(stdout)
        assert data["trust_summary"] == "verified_signed_trusted"

    def test_signed_failed_has_failed_signed(self, tmp_path):
        """Signed bundle that fails should have trust_summary='failed_signed'."""
        with patch.dict(os.environ, {"AIHUB_SIGNING_KEY": "orig"}):
            result_audit, run_dir, _, _ = _invoke_audit(
                tmp_path, "a31-ts-fail-signed", extra_args=["--sign"])
        assert result_audit.exit_code == 0
        zip_path = _find_audit_zip(run_dir)

        with patch.dict(os.environ, {"AIHUB_SIGNING_KEY": "wrong"}):
            result_verify, stdout, _ = _invoke_verify(zip_path)
        data = _get_json_from_stdout(stdout)
        assert data["trust_summary"] == "failed_signed"

    def test_trust_summary_in_status_output(self, tmp_path):
        """trust_summary should appear in status output when verify runs without --json."""
        result_audit, run_dir, _, _ = _invoke_audit(tmp_path, "a31-ts-stderr")
        assert result_audit.exit_code == 0
        zip_path = _find_audit_zip(run_dir)
        from typer.testing import CliRunner
        from ai_workflow_hub.cli import app
        from rich.console import Console
        rt = _fake_runtime()
        runner = CliRunner()
        stdout_buf = io.StringIO()
        stderr_buf = io.StringIO()
        _console = Console(file=stdout_buf, force_terminal=False, width=4096)
        _err_console = Console(file=stderr_buf, force_terminal=False)
        with patch(_RT_PATH, return_value=rt), \
             patch("ai_workflow_hub.cli.init_env"), \
             patch("ai_workflow_hub.cli.console", _console), \
             patch("ai_workflow_hub.cli.err_console", _err_console):
            result = runner.invoke(app, ["paper", "verify", "--zip", str(zip_path)],
                                   catch_exceptions=False)
        combined = stdout_buf.getvalue() + stderr_buf.getvalue()
        assert "verified_unsigned" in combined


# ===========================================================================
# 2. Anchor log entry chaining (prev_hash)
# ===========================================================================

class TestA31AnchorChaining:
    def test_first_entry_has_empty_prev_hash(self, tmp_path):
        """First anchor log entry should have prev_hash=''."""
        log_path = tmp_path / "chain.log"
        result, _, _, _ = _invoke_audit(
            tmp_path, "a31-ac-first",
            extra_args=["--anchor-log", str(log_path)])
        assert result.exit_code == 0
        entry = json.loads(log_path.read_text(encoding="utf-8").strip())
        assert entry["prev_hash"] == ""

    def test_second_entry_has_prev_hash(self, tmp_path):
        """Second anchor log entry should have non-empty prev_hash."""
        log_path = tmp_path / "chain2.log"
        result1, _, _, _ = _invoke_audit(
            tmp_path, "a31-ac-a",
            extra_args=["--anchor-log", str(log_path)])
        assert result1.exit_code == 0
        result2, _, _, _ = _invoke_audit(
            tmp_path, "a31-ac-b",
            extra_args=["--anchor-log", str(log_path)])
        assert result2.exit_code == 0

        lines = [l for l in log_path.read_text(encoding="utf-8").strip().split("\n") if l]
        assert len(lines) == 2
        entry1 = json.loads(lines[0])
        entry2 = json.loads(lines[1])
        assert entry1["prev_hash"] == ""
        assert entry2["prev_hash"] != ""
        # Verify prev_hash matches hash of first entry
        expected = hashlib.sha256(lines[0].encode("utf-8")).hexdigest()
        assert entry2["prev_hash"] == expected

    def test_third_entry_chains_from_second(self, tmp_path):
        """Third entry's prev_hash should match hash of second entry."""
        log_path = tmp_path / "chain3.log"
        for i, rid in enumerate(["a31-ac-1", "a31-ac-2", "a31-ac-3"]):
            r, _, _, _ = _invoke_audit(
                tmp_path, rid, extra_args=["--anchor-log", str(log_path)])
            assert r.exit_code == 0

        lines = [l for l in log_path.read_text(encoding="utf-8").strip().split("\n") if l]
        assert len(lines) == 3
        for i in range(1, len(lines)):
            prev = json.loads(lines[i])["prev_hash"]
            expected = hashlib.sha256(lines[i-1].encode("utf-8")).hexdigest()
            assert prev == expected


# ===========================================================================
# 3. Key ID support
# ===========================================================================

class TestA31KeyId:
    def test_key_id_in_signed_attestation(self, tmp_path):
        """Signature block should include key_id when AIHUB_SIGNING_KEY_ID is set."""
        with patch.dict(os.environ, {
            "AIHUB_SIGNING_KEY": "key-abc",
            "AIHUB_SIGNING_KEY_ID": "key-v1",
        }):
            result, run_dir, _, _ = _invoke_audit(
                tmp_path, "a31-kid-1", extra_args=["--sign"])
        assert result.exit_code == 0
        zip_path = _find_audit_zip(run_dir)
        with zipfile.ZipFile(zip_path, "r") as zf:
            att = json.loads(zf.read("attestation.json"))
            assert att["signature"]["key_id"] == "key-v1"

    def test_no_key_id_when_not_set(self, tmp_path):
        """Signature block should not include key_id when not configured."""
        env = {k: v for k, v in os.environ.items() if k != "AIHUB_SIGNING_KEY_ID"}
        with patch.dict(os.environ, env, clear=True):
            with patch.dict(os.environ, {"AIHUB_SIGNING_KEY": "key-only"}):
                result, run_dir, _, _ = _invoke_audit(
                    tmp_path, "a31-kid-2", extra_args=["--sign"])
        assert result.exit_code == 0
        zip_path = _find_audit_zip(run_dir)
        with zipfile.ZipFile(zip_path, "r") as zf:
            att = json.loads(zf.read("attestation.json"))
            assert "key_id" not in att["signature"]

    def test_key_id_in_anchor_log(self, tmp_path):
        """Anchor log entry should include key_id when signing is enabled."""
        log_path = tmp_path / "kid.log"
        with patch.dict(os.environ, {
            "AIHUB_SIGNING_KEY": "key-abc",
            "AIHUB_SIGNING_KEY_ID": "key-v2",
        }):
            result, _, _, _ = _invoke_audit(
                tmp_path, "a31-kid-log",
                extra_args=["--sign", "--anchor-log", str(log_path)])
        assert result.exit_code == 0
        entry = json.loads(log_path.read_text(encoding="utf-8").strip())
        assert entry["key_id"] == "key-v2"

    def test_key_id_in_verify_output(self, tmp_path):
        """Signature verification should report key_id when present."""
        key = "verify-kid"
        with patch.dict(os.environ, {
            "AIHUB_SIGNING_KEY": key,
            "AIHUB_SIGNING_KEY_ID": "prod-v1",
        }):
            result_audit, run_dir, _, _ = _invoke_audit(
                tmp_path, "a31-kid-verify", extra_args=["--sign"])
        assert result_audit.exit_code == 0
        zip_path = _find_audit_zip(run_dir)

        with patch.dict(os.environ, {"AIHUB_SIGNING_KEY": key}):
            result_verify, stdout, _ = _invoke_verify(zip_path)
        data = _get_json_from_stdout(stdout)
        sig_check = next(c for c in data["checks"] if c["check"] == "signature_valid")
        assert "key_id=prod-v1" in sig_check.get("detail", "")


# ===========================================================================
# 4. Required files hash validation (file:sha256 format)
# ===========================================================================

class TestA31RequiredFilesHash:
    def test_required_with_correct_hash_passes(self, tmp_path):
        """--required-files with correct hash should not produce warnings."""
        run_dir, state = _make_run_dir(tmp_path, "a31-rfh-ok")
        _write_json(run_dir / "closeout-report.json", {"v": 1})
        (run_dir / "closeout-report.md").write_text("# Report", encoding="utf-8")

        # Compute actual hash of state.json
        state_hash = hashlib.sha256(
            (run_dir / "state.json").read_bytes()).hexdigest()

        from typer.testing import CliRunner
        from ai_workflow_hub.cli import app
        from rich.console import Console
        rt = _fake_runtime()
        runner = CliRunner()
        stdout_buf = io.StringIO()
        stderr_buf = io.StringIO()
        _console = Console(file=stdout_buf, force_terminal=False, width=4096)
        _err_console = Console(file=stderr_buf, force_terminal=False)

        with patch(_RT_PATH, return_value=rt), \
             patch(_PAPER_RUNS, return_value=tmp_path), \
             patch("ai_workflow_hub.cli.init_env"), \
             patch("ai_workflow_hub.cli.console", _console), \
             patch("ai_workflow_hub.cli.err_console", _err_console):
            result = runner.invoke(app, [
                "paper", "audit", "--run-id", "a31-rfh-ok",
                "--json",
                "--required-files", f"state.json:{state_hash}",
            ], catch_exceptions=False)
        assert result.exit_code == 0
        data = _get_json_from_stdout(stdout_buf.getvalue())
        assert data["missing_required"] == []

    def test_required_with_wrong_hash_fails_strict(self, tmp_path):
        """--required-files with wrong hash + --strict should fail."""
        run_dir, state = _make_run_dir(tmp_path, "a31-rfh-bad")
        _write_json(run_dir / "closeout-report.json", {"v": 1})
        (run_dir / "closeout-report.md").write_text("# Report", encoding="utf-8")

        from typer.testing import CliRunner
        from ai_workflow_hub.cli import app
        from rich.console import Console
        rt = _fake_runtime()
        runner = CliRunner()
        stdout_buf = io.StringIO()
        stderr_buf = io.StringIO()
        _console = Console(file=stdout_buf, force_terminal=False, width=4096)
        _err_console = Console(file=stderr_buf, force_terminal=False)

        with patch(_RT_PATH, return_value=rt), \
             patch(_PAPER_RUNS, return_value=tmp_path), \
             patch("ai_workflow_hub.cli.init_env"), \
             patch("ai_workflow_hub.cli.console", _console), \
             patch("ai_workflow_hub.cli.err_console", _err_console):
            result = runner.invoke(app, [
                "paper", "audit", "--run-id", "a31-rfh-bad",
                "--json", "--strict",
                "--required-files", "state.json:" + "0" * 64,
            ], catch_exceptions=False)
        assert result.exit_code == 1  # strict failure


# ===========================================================================
# 5. Integration
# ===========================================================================

class TestA31Integration:
    def test_full_hardened_workflow(self, tmp_path):
        """End-to-end: sign + key_id + anchor + verify → verified_signed_trusted."""
        key = "integ-key-a31"
        key_id = "integ-v1"
        log_path = tmp_path / "integ.log"

        with patch.dict(os.environ, {
            "AIHUB_SIGNING_KEY": key,
            "AIHUB_SIGNING_KEY_ID": key_id,
        }):
            result_audit, run_dir, _, _ = _invoke_audit(
                tmp_path, "a31-integ",
                extra_args=["--sign", "--anchor-log", str(log_path)])
        assert result_audit.exit_code == 0
        assert log_path.exists()

        # Verify anchor chaining
        entry = json.loads(log_path.read_text(encoding="utf-8").strip())
        assert entry["prev_hash"] == ""
        assert entry["key_id"] == key_id

        # Verify
        zip_path = _find_audit_zip(run_dir)
        with patch.dict(os.environ, {"AIHUB_SIGNING_KEY": key}):
            result_verify, stdout, _ = _invoke_verify(zip_path)
        assert result_verify.exit_code == 0
        data = _get_json_from_stdout(stdout)
        assert data["trust_summary"] == "verified_signed_trusted"
        assert data["trust_level"] == "signed_trusted"
        assert data["verdict"] == "passed"
