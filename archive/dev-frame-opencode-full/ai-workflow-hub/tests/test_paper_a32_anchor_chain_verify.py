"""A32 — Anchor Chain Verify Tests.

Covers the A31 carry-forward and new features:

 1. paper verify-chain command — anchor log chain integrity verification
 2. Check 12 in paper verify — anchor log cross-verification
 3. Chain tamper detection
 4. Cross-verify zip_sha256 against actual ZIP files
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


def _make_run_dir(tmp: Path, run_id: str = "paper-test-a32") -> tuple[Path, dict]:
    run_dir = tmp / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    state = {
        "run_id": run_id, "task_id": "task-a32",
        "project_id": "proj-a32", "status": "completed",
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


def _invoke_audit(tmp_path, run_id="paper-a32-test", extra_args=None,
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
# 1. verify-chain command — basic chain integrity
# ===========================================================================

class TestA32VerifyChainBasic:
    def test_empty_log_fails(self, tmp_path):
        """Empty log file should fail log_exists check... actually it exists but no entries."""
        log_path = tmp_path / "empty.log"
        log_path.write_text("", encoding="utf-8")
        result, stdout, _ = _invoke_verify_chain(log_path)
        data = _get_json_from_stdout(stdout)
        # Log exists, but entries_parseable might pass (0 entries, 0 errors)
        assert data["entries"] == 0

    def test_nonexistent_log_fails(self, tmp_path):
        """Nonexistent log should fail and exit."""
        result, stdout, _ = _invoke_verify_chain(tmp_path / "ghost.log")
        assert result.exit_code == 1
        data = _get_json_from_stdout(stdout)
        checks = {c["check"]: c for c in data["checks"]}
        assert checks["log_exists"]["passed"] is False

    def test_valid_single_entry(self, tmp_path):
        """Single valid entry with empty prev_hash should pass."""
        log_path = tmp_path / "single.log"
        entry = json.dumps({
            "timestamp": "2026-06-12T00:00:00Z", "bundle_id": "b1",
            "run_id": "r1", "zip_sha256": "a" * 64, "prev_hash": "",
        }, ensure_ascii=False)
        log_path.write_text(entry + "\n", encoding="utf-8")
        result, stdout, _ = _invoke_verify_chain(log_path)
        assert result.exit_code == 0
        data = _get_json_from_stdout(stdout)
        assert data["verdict"] == "passed"

    def test_valid_chain_of_three(self, tmp_path):
        """Three-entry chain should pass all checks."""
        log_path = tmp_path / "chain3.log"
        entries = []
        for i in range(3):
            entry = {
                "timestamp": f"2026-06-12T00:0{i}:00Z", "bundle_id": f"b{i}",
                "run_id": f"r{i}", "zip_sha256": f"{i}" * 64,
                "bundle_hash": f"h{i}", "signed": False,
            }
            if i > 0:
                prev_line = entries[-1]
                entry["prev_hash"] = hashlib.sha256(prev_line.encode("utf-8")).hexdigest()
            else:
                entry["prev_hash"] = ""
            line = json.dumps(entry, ensure_ascii=False)
            entries.append(line)
        log_path.write_text("\n".join(entries) + "\n", encoding="utf-8")
        result, stdout, _ = _invoke_verify_chain(log_path)
        assert result.exit_code == 0
        data = _get_json_from_stdout(stdout)
        assert data["entries"] == 3
        assert data["verdict"] == "passed"


# ===========================================================================
# 2. verify-chain — tamper detection
# ===========================================================================

class TestA32VerifyChainTamper:
    def test_tampered_entry_breaks_chain(self, tmp_path):
        """Modifying an entry should break the chain."""
        log_path = tmp_path / "tamper.log"
        entries = []
        for i in range(3):
            entry = {
                "timestamp": f"2026-06-12T00:0{i}:00Z", "bundle_id": f"b{i}",
                "run_id": f"r{i}", "zip_sha256": f"{i}" * 64,
                "bundle_hash": f"h{i}", "signed": False,
            }
            if i > 0:
                prev_line = entries[-1]
                entry["prev_hash"] = hashlib.sha256(prev_line.encode("utf-8")).hexdigest()
            else:
                entry["prev_hash"] = ""
            entries.append(json.dumps(entry, ensure_ascii=False))
        # Tamper with entry 0
        tampered = json.loads(entries[0])
        tampered["zip_sha256"] = "f" * 64
        entries[0] = json.dumps(tampered, ensure_ascii=False)
        log_path.write_text("\n".join(entries) + "\n", encoding="utf-8")

        result, stdout, _ = _invoke_verify_chain(log_path)
        data = _get_json_from_stdout(stdout)
        checks = {c["check"]: c for c in data["checks"]}
        assert checks["chain_integrity"]["passed"] is False


# ===========================================================================
# 3. Check 12 in paper verify — anchor log cross-verification
# ===========================================================================

class TestA32VerifyCheck12:
    def test_verify_with_anchor_log_finds_match(self, tmp_path):
        """Verify with --anchor-log should find ZIP hash in the log."""
        log_path = tmp_path / "check12.log"
        result_audit, run_dir, _, _ = _invoke_audit(
            tmp_path, "a32-c12-ok",
            extra_args=["--anchor-log", str(log_path)])
        assert result_audit.exit_code == 0

        zip_path = _find_audit_zip(run_dir)
        result_verify, stdout, _ = _invoke_verify(
            zip_path, extra_args=["--anchor-log", str(log_path)])
        assert result_verify.exit_code == 0
        data = _get_json_from_stdout(stdout)
        checks = {c["check"]: c for c in data["checks"]}
        assert checks["anchor_log_cross_verify"]["passed"] is True

    def test_verify_without_anchor_log_skips_check(self, tmp_path):
        """Without --anchor-log, Check 12 should pass (skipped)."""
        result_audit, run_dir, _, _ = _invoke_audit(tmp_path, "a32-c12-skip")
        assert result_audit.exit_code == 0
        zip_path = _find_audit_zip(run_dir)
        result_verify, stdout, _ = _invoke_verify(zip_path)
        data = _get_json_from_stdout(stdout)
        checks = {c["check"]: c for c in data["checks"]}
        assert checks["anchor_log_cross_verify"]["passed"] is True
        assert "skipped" in checks["anchor_log_cross_verify"].get("detail", "")

    def test_verify_with_wrong_anchor_log_fails(self, tmp_path):
        """Verify with wrong anchor log should fail Check 12."""
        result_audit, run_dir, _, _ = _invoke_audit(tmp_path, "a32-c12-bad")
        assert result_audit.exit_code == 0
        zip_path = _find_audit_zip(run_dir)

        # Create a fake anchor log with wrong hash
        fake_log = tmp_path / "fake.log"
        fake_entry = json.dumps({
            "timestamp": "2026-01-01", "bundle_id": "fake",
            "run_id": "fake", "zip_sha256": "0" * 64,
            "prev_hash": "",
        })
        fake_log.write_text(fake_entry + "\n", encoding="utf-8")

        result_verify, stdout, _ = _invoke_verify(
            zip_path, extra_args=["--anchor-log", str(fake_log)])
        data = _get_json_from_stdout(stdout)
        checks = {c["check"]: c for c in data["checks"]}
        assert checks["anchor_log_cross_verify"]["passed"] is False


# ===========================================================================
# 4. Integration: audit + anchor + verify-chain + verify
# ===========================================================================

class TestA32Integration:
    def test_full_chain_workflow(self, tmp_path):
        """End-to-end: multiple audits → verify-chain → verify with anchor."""
        log_path = tmp_path / "integ.log"
        zips = []

        for i in range(3):
            rid = f"a32-integ-{i}"
            r, run_dir, _, _ = _invoke_audit(
                tmp_path, rid,
                extra_args=["--anchor-log", str(log_path)])
            assert r.exit_code == 0
            zips.append(_find_audit_zip(run_dir))

        # Verify chain
        result_chain, stdout_chain, _ = _invoke_verify_chain(log_path)
        assert result_chain.exit_code == 0
        data_chain = _get_json_from_stdout(stdout_chain)
        assert data_chain["entries"] == 3
        assert data_chain["verdict"] == "passed"

        # Verify last ZIP with anchor cross-check
        result_verify, stdout_verify, _ = _invoke_verify(
            zips[-1], extra_args=["--anchor-log", str(log_path)])
        assert result_verify.exit_code == 0
        data_verify = _get_json_from_stdout(stdout_verify)
        checks = {c["check"]: c for c in data_verify["checks"]}
        assert checks["anchor_log_cross_verify"]["passed"] is True
