"""A33 — Chain Strict Policy Tests.

Covers the A33 features added to verify-chain and Check 12:

 1. entries_non_empty — empty log fails
 2. timestamp_monotonic — non-monotonic timestamps detected
 3. no_duplicates — duplicate bundle_id / zip_sha256 detected
 4. verification_mode — chain_only / chain_plus_zip / chain_partial
 5. trust_level in verify-chain result
 6. zip_any_verified — warns when all ZIPs skipped
 7. Check 12 malformed line count
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


def _make_run_dir(tmp: Path, run_id: str = "paper-test-a33") -> tuple[Path, dict]:
    run_dir = tmp / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    state = {
        "run_id": run_id, "task_id": "task-a33",
        "project_id": "proj-a33", "status": "completed",
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


def _invoke_audit(tmp_path, run_id="paper-a33-test", extra_args=None,
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


def _make_chain(entries_data: list[dict]) -> str:
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
# 1. verify-chain strict checks
# ===========================================================================

class TestA33VerifyChainStrict:
    def test_empty_log_fails_entries_non_empty(self, tmp_path):
        """Empty log should fail entries_non_empty and exit non-zero."""
        log_path = tmp_path / "empty.log"
        log_path.write_text("", encoding="utf-8")
        result, stdout, _ = _invoke_verify_chain(log_path)
        assert result.exit_code == 1
        data = _get_json_from_stdout(stdout)
        checks = {c["check"]: c for c in data["checks"]}
        assert checks["entries_non_empty"]["passed"] is False
        assert data["entries"] == 0

    def test_timestamp_monotonic_passes(self, tmp_path):
        """Monotonically increasing timestamps should pass."""
        entries = [
            {"timestamp": f"2026-06-12T00:0{i}:00Z", "bundle_id": f"b{i}",
             "run_id": f"r{i}", "zip_sha256": f"{i}" * 64}
            for i in range(3)
        ]
        log_path = tmp_path / "mono.log"
        log_path.write_text(_make_chain(entries), encoding="utf-8")
        result, stdout, _ = _invoke_verify_chain(log_path)
        assert result.exit_code == 0
        data = _get_json_from_stdout(stdout)
        checks = {c["check"]: c for c in data["checks"]}
        assert checks["timestamp_monotonic"]["passed"] is True

    def test_timestamp_monotonic_fails(self, tmp_path):
        """Out-of-order timestamps should fail timestamp_monotonic."""
        entries = [
            {"timestamp": "2026-06-12T00:02:00Z", "bundle_id": "b0",
             "run_id": "r0", "zip_sha256": "0" * 64},
            {"timestamp": "2026-06-12T00:01:00Z", "bundle_id": "b1",  # Earlier!
             "run_id": "r1", "zip_sha256": "1" * 64},
            {"timestamp": "2026-06-12T00:03:00Z", "bundle_id": "b2",
             "run_id": "r2", "zip_sha256": "2" * 64},
        ]
        log_path = tmp_path / "bad_ts.log"
        log_path.write_text(_make_chain(entries), encoding="utf-8")
        result, stdout, _ = _invoke_verify_chain(log_path)
        data = _get_json_from_stdout(stdout)
        checks = {c["check"]: c for c in data["checks"]}
        assert checks["timestamp_monotonic"]["passed"] is False

    def test_no_duplicates_passes(self, tmp_path):
        """Unique bundle_id/zip_sha256 entries should pass."""
        entries = [
            {"timestamp": f"2026-06-12T00:0{i}:00Z", "bundle_id": f"b{i}",
             "run_id": f"r{i}", "zip_sha256": f"{i}" * 64}
            for i in range(3)
        ]
        log_path = tmp_path / "unique.log"
        log_path.write_text(_make_chain(entries), encoding="utf-8")
        result, stdout, _ = _invoke_verify_chain(log_path)
        assert result.exit_code == 0
        data = _get_json_from_stdout(stdout)
        checks = {c["check"]: c for c in data["checks"]}
        assert checks["no_duplicates"]["passed"] is True

    def test_duplicate_bundle_id_fails(self, tmp_path):
        """Duplicate bundle_id should fail no_duplicates."""
        entries = [
            {"timestamp": "2026-06-12T00:00:00Z", "bundle_id": "dup",
             "run_id": "r0", "zip_sha256": "0" * 64},
            {"timestamp": "2026-06-12T00:01:00Z", "bundle_id": "dup",  # Same!
             "run_id": "r1", "zip_sha256": "1" * 64},
        ]
        log_path = tmp_path / "dup_bid.log"
        log_path.write_text(_make_chain(entries), encoding="utf-8")
        result, stdout, _ = _invoke_verify_chain(log_path)
        data = _get_json_from_stdout(stdout)
        checks = {c["check"]: c for c in data["checks"]}
        assert checks["no_duplicates"]["passed"] is False
        assert "1 duplicate bundle_ids" in checks["no_duplicates"]["detail"]

    def test_duplicate_zip_sha256_fails(self, tmp_path):
        """Duplicate zip_sha256 should fail no_duplicates."""
        entries = [
            {"timestamp": "2026-06-12T00:00:00Z", "bundle_id": "b0",
             "run_id": "r0", "zip_sha256": "a" * 64},
            {"timestamp": "2026-06-12T00:01:00Z", "bundle_id": "b1",
             "run_id": "r1", "zip_sha256": "a" * 64},  # Same hash!
        ]
        log_path = tmp_path / "dup_hash.log"
        log_path.write_text(_make_chain(entries), encoding="utf-8")
        result, stdout, _ = _invoke_verify_chain(log_path)
        data = _get_json_from_stdout(stdout)
        checks = {c["check"]: c for c in data["checks"]}
        assert checks["no_duplicates"]["passed"] is False
        assert "1 duplicate zip_sha256" in checks["no_duplicates"]["detail"]


# ===========================================================================
# 2. verification_mode and trust_level
# ===========================================================================

class TestA33VerificationMode:
    def test_chain_only_mode(self, tmp_path):
        """Without --zip-dir, verification_mode should be chain_only."""
        entries = [
            {"timestamp": "2026-06-12T00:00:00Z", "bundle_id": "b0",
             "run_id": "r0", "zip_sha256": "0" * 64},
        ]
        log_path = tmp_path / "mode.log"
        log_path.write_text(_make_chain(entries), encoding="utf-8")
        result, stdout, _ = _invoke_verify_chain(log_path)
        data = _get_json_from_stdout(stdout)
        assert data["verification_mode"] == "chain_only"
        assert data["trust_level"] == "chain_valid"

    def test_chain_invalid_on_failure(self, tmp_path):
        """Failed chain should have trust_level=chain_invalid."""
        log_path = tmp_path / "fail.log"
        log_path.write_text("", encoding="utf-8")
        result, stdout, _ = _invoke_verify_chain(log_path)
        data = _get_json_from_stdout(stdout)
        assert data["trust_level"] == "chain_invalid"

    def test_chain_empty_trust_level(self, tmp_path):
        """Empty log (0 entries, failed entries_non_empty) → chain_empty."""
        log_path = tmp_path / "empty.log"
        log_path.write_text("", encoding="utf-8")
        result, stdout, _ = _invoke_verify_chain(log_path)
        data = _get_json_from_stdout(stdout)
        # entries_non_empty fails → verdict=failed → trust_level should be chain_invalid
        assert data["trust_level"] in ("chain_empty", "chain_invalid")


# ===========================================================================
# 3. Check 12 malformed line count
# ===========================================================================

class TestA33Check12Malformed:
    def test_malformed_lines_reported(self, tmp_path):
        """Check 12 should report malformed line count in detail."""
        # Create audit to get a real ZIP
        result_audit, run_dir, _, _ = _invoke_audit(tmp_path, "a33-c12-mal")
        assert result_audit.exit_code == 0
        zip_path = _find_audit_zip(run_dir)

        # Create anchor log with 1 valid entry (matching ZIP hash) + 1 malformed line
        zip_hash = hashlib.sha256(zip_path.read_bytes()).hexdigest()
        valid_entry = json.dumps({
            "timestamp": "2026-06-12T00:00:00Z", "bundle_id": "b1",
            "run_id": "a33-c12-mal", "zip_sha256": zip_hash,
            "prev_hash": "",
        })
        malformed = "this is not json at all"
        log_path = tmp_path / "malformed.log"
        log_path.write_text(valid_entry + "\n" + malformed + "\n", encoding="utf-8")

        result_verify, stdout, _ = _invoke_verify(
            zip_path, extra_args=["--anchor-log", str(log_path)])
        data = _get_json_from_stdout(stdout)
        checks = {c["check"]: c for c in data["checks"]}
        c12 = checks["anchor_log_cross_verify"]
        assert c12["passed"] is True  # ZIP hash found
        assert "1 malformed lines skipped" in c12["detail"]

    def test_no_malformed_no_report(self, tmp_path):
        """When no malformed lines, detail should not mention malformed."""
        result_audit, run_dir, _, _ = _invoke_audit(tmp_path, "a33-c12-clean")
        assert result_audit.exit_code == 0
        zip_path = _find_audit_zip(run_dir)

        zip_hash = hashlib.sha256(zip_path.read_bytes()).hexdigest()
        valid_entry = json.dumps({
            "timestamp": "2026-06-12T00:00:00Z", "bundle_id": "b1",
            "run_id": "a33-c12-clean", "zip_sha256": zip_hash,
            "prev_hash": "",
        })
        log_path = tmp_path / "clean.log"
        log_path.write_text(valid_entry + "\n", encoding="utf-8")

        result_verify, stdout, _ = _invoke_verify(
            zip_path, extra_args=["--anchor-log", str(log_path)])
        data = _get_json_from_stdout(stdout)
        checks = {c["check"]: c for c in data["checks"]}
        c12 = checks["anchor_log_cross_verify"]
        assert "malformed" not in c12.get("detail", "")


# ===========================================================================
# 4. zip_any_verified
# ===========================================================================

class TestA33ZipAnyVerified:
    def test_zip_all_skipped_fails(self, tmp_path):
        """When --zip-dir has no matching ZIPs, zip_any_verified should fail."""
        entries = [
            {"timestamp": "2026-06-12T00:00:00Z", "bundle_id": "b0",
             "run_id": "r0", "zip_sha256": "0" * 64},
        ]
        log_path = tmp_path / "noskip.log"
        log_path.write_text(_make_chain(entries), encoding="utf-8")

        empty_dir = tmp_path / "empty_zips"
        empty_dir.mkdir()
        result, stdout, _ = _invoke_verify_chain(
            log_path, extra_args=["--zip-dir", str(empty_dir)])
        data = _get_json_from_stdout(stdout)
        checks = {c["check"]: c for c in data["checks"]}
        assert checks["zip_any_verified"]["passed"] is False

    def test_zip_verified_passes(self, tmp_path):
        """When --zip-dir has matching ZIPs, zip_any_verified should pass."""
        # Create audit to get a real ZIP
        result_audit, run_dir, _, _ = _invoke_audit(tmp_path, "a33-zip-ok")
        assert result_audit.exit_code == 0
        zip_path = _find_audit_zip(run_dir)

        # Build anchor log entry for this ZIP
        zip_hash = hashlib.sha256(zip_path.read_bytes()).hexdigest()
        entries = [
            {"timestamp": "2026-06-12T00:00:00Z", "bundle_id": run_dir.name,
             "run_id": "a33-zip-ok", "zip_sha256": zip_hash},
        ]
        log_path = tmp_path / "real.log"
        log_path.write_text(_make_chain(entries), encoding="utf-8")

        # --zip-dir points to run_dir where the actual ZIP lives
        result, stdout, _ = _invoke_verify_chain(
            log_path, extra_args=["--zip-dir", str(run_dir)])
        data = _get_json_from_stdout(stdout)
        checks = {c["check"]: c for c in data["checks"]}
        assert checks["zip_cross_verify"]["passed"] is True
        assert checks["zip_any_verified"]["passed"] is True
        assert data["verification_mode"] == "chain_plus_zip"


# ===========================================================================
# 5. Integration: full A33 workflow
# ===========================================================================

class TestA33Integration:
    def test_full_strict_chain_workflow(self, tmp_path):
        """End-to-end: audits → verify-chain (strict) → verify with anchor."""
        log_path = tmp_path / "integ.log"
        zips = []

        for i in range(3):
            rid = f"a33-integ-{i}"
            r, run_dir, _, _ = _invoke_audit(
                tmp_path, rid,
                extra_args=["--anchor-log", str(log_path)])
            assert r.exit_code == 0
            zips.append(_find_audit_zip(run_dir))

        # Verify chain with strict checks
        result_chain, stdout_chain, _ = _invoke_verify_chain(log_path)
        assert result_chain.exit_code == 0
        data_chain = _get_json_from_stdout(stdout_chain)
        assert data_chain["entries"] == 3
        assert data_chain["verdict"] == "passed"
        assert data_chain["verification_mode"] == "chain_only"
        checks = {c["check"]: c for c in data_chain["checks"]}
        assert checks["entries_non_empty"]["passed"] is True
        assert checks["timestamp_monotonic"]["passed"] is True
        assert checks["no_duplicates"]["passed"] is True

        # Verify last ZIP with anchor cross-check
        result_verify, stdout_verify, _ = _invoke_verify(
            zips[-1], extra_args=["--anchor-log", str(log_path)])
        assert result_verify.exit_code == 0
        data_verify = _get_json_from_stdout(stdout_verify)
        vchecks = {c["check"]: c for c in data_verify["checks"]}
        assert vchecks["anchor_log_cross_verify"]["passed"] is True
