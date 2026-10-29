"""A30 — Trust Policy Tests.

Covers the 5 GPT-identified concerns from A29 accepted_with_limitations:

 1. Trust level field (signed_trusted / unsigned_valid / signed_unverified)
 2. External anchoring (--anchor-log appends to audit log)
 3. Generated-member governance (_AUDIT_GENERATED_MEMBERS module constant)
 4. Symlink policy (--no-follow-symlinks)
 5. Required files policy (--required-files)
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
# Helpers — reuse patterns from A28/A29 tests
# ---------------------------------------------------------------------------

def _write_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def _make_run_dir(tmp: Path, run_id: str = "paper-test-a30") -> tuple[Path, dict]:
    run_dir = tmp / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    state = {
        "run_id": run_id, "task_id": "task-a30",
        "project_id": "proj-a30", "status": "completed",
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


def _invoke_audit(tmp_path, run_id="paper-a30-test", extra_args=None,
                  create_reports=True):
    """Run paper audit and return (result, run_dir, stdout, stderr)."""
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
    """Run paper verify and return (result, stdout, stderr)."""
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
    """Extract JSON from stdout."""
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
# 1. Trust Level — signed_trusted / unsigned_valid / signed_unverified
# ===========================================================================

class TestA30TrustLevel:
    def test_unsigned_bundle_has_unsigned_valid(self, tmp_path):
        """Unsigned bundle should produce trust_level='unsigned_valid'."""
        result_audit, run_dir, _, _ = _invoke_audit(tmp_path, "a30-tl-unsigned")
        assert result_audit.exit_code == 0
        zip_path = _find_audit_zip(run_dir)
        result_verify, stdout, _ = _invoke_verify(zip_path)
        data = _get_json_from_stdout(stdout)
        assert data["trust_level"] == "unsigned_valid"

    def test_signed_bundle_has_signed_trusted(self, tmp_path):
        """Signed bundle with correct key should produce trust_level='signed_trusted'."""
        key = "trust-test-key"
        with patch.dict(os.environ, {"AIHUB_SIGNING_KEY": key}):
            result_audit, run_dir, _, _ = _invoke_audit(
                tmp_path, "a30-tl-signed", extra_args=["--sign"])
        assert result_audit.exit_code == 0
        zip_path = _find_audit_zip(run_dir)

        with patch.dict(os.environ, {"AIHUB_SIGNING_KEY": key}):
            result_verify, stdout, _ = _invoke_verify(zip_path)
        data = _get_json_from_stdout(stdout)
        assert data["trust_level"] == "signed_trusted"

    def test_signed_bundle_without_key_has_signed_unverified(self, tmp_path):
        """Signed bundle verified without key should produce trust_level='signed_unverified'."""
        with patch.dict(os.environ, {"AIHUB_SIGNING_KEY": "orig-key"}):
            result_audit, run_dir, _, _ = _invoke_audit(
                tmp_path, "a30-tl-unverified", extra_args=["--sign"])
        assert result_audit.exit_code == 0
        zip_path = _find_audit_zip(run_dir)

        env = {k: v for k, v in os.environ.items() if k != "AIHUB_SIGNING_KEY"}
        with patch.dict(os.environ, env, clear=True):
            result_verify, stdout, _ = _invoke_verify(zip_path)
        data = _get_json_from_stdout(stdout)
        assert data["trust_level"] == "signed_unverified"

    def test_signed_bundle_wrong_key_has_signed_unverified(self, tmp_path):
        """Signed bundle verified with wrong key should produce trust_level='signed_unverified'."""
        with patch.dict(os.environ, {"AIHUB_SIGNING_KEY": "correct-key"}):
            result_audit, run_dir, _, _ = _invoke_audit(
                tmp_path, "a30-tl-wrongkey", extra_args=["--sign"])
        assert result_audit.exit_code == 0
        zip_path = _find_audit_zip(run_dir)

        with patch.dict(os.environ, {"AIHUB_SIGNING_KEY": "wrong-key"}):
            result_verify, stdout, _ = _invoke_verify(zip_path)
        data = _get_json_from_stdout(stdout)
        assert data["trust_level"] == "signed_unverified"


# ===========================================================================
# 2. Anchor Log — append bundle hash to audit log
# ===========================================================================

class TestA30AnchorLog:
    def test_anchor_log_creates_file(self, tmp_path):
        """--anchor-log should create the log file with bundle entry."""
        log_path = tmp_path / "audit-anchor.log"
        result, run_dir, _, _ = _invoke_audit(
            tmp_path, "a30-al-create",
            extra_args=["--anchor-log", str(log_path)])
        assert result.exit_code == 0
        assert log_path.exists()

    def test_anchor_log_contains_bundle_hash(self, tmp_path):
        """Anchor log entry should contain zip_sha256 and bundle_id."""
        log_path = tmp_path / "audit-anchor2.log"
        result, run_dir, _, _ = _invoke_audit(
            tmp_path, "a30-al-hash",
            extra_args=["--anchor-log", str(log_path)])
        assert result.exit_code == 0
        entry = json.loads(log_path.read_text(encoding="utf-8").strip())
        assert "zip_sha256" in entry
        assert "bundle_id" in entry
        assert "timestamp" in entry
        assert "bundle_hash" in entry

    def test_anchor_log_appends_multiple_entries(self, tmp_path):
        """Multiple audits should append to the same log file."""
        log_path = tmp_path / "audit-append.log"
        result1, _, _, _ = _invoke_audit(
            tmp_path, "a30-al-multi1",
            extra_args=["--anchor-log", str(log_path)])
        assert result1.exit_code == 0
        result2, _, _, _ = _invoke_audit(
            tmp_path, "a30-al-multi2",
            extra_args=["--anchor-log", str(log_path)])
        assert result2.exit_code == 0
        lines = [l for l in log_path.read_text(encoding="utf-8").strip().split("\n") if l]
        assert len(lines) == 2
        entry1 = json.loads(lines[0])
        entry2 = json.loads(lines[1])
        assert entry1["run_id"] == "a30-al-multi1"
        assert entry2["run_id"] == "a30-al-multi2"

    def test_anchor_log_signed_flag(self, tmp_path):
        """Anchor log should record whether bundle was signed."""
        log_path = tmp_path / "audit-signed.log"
        with patch.dict(os.environ, {"AIHUB_SIGNING_KEY": "test-key"}):
            result, _, _, _ = _invoke_audit(
                tmp_path, "a30-al-sign",
                extra_args=["--anchor-log", str(log_path), "--sign"])
        assert result.exit_code == 0
        entry = json.loads(log_path.read_text(encoding="utf-8").strip())
        assert entry["signed"] is True

    def test_anchor_log_in_json_output(self, tmp_path):
        """JSON output should include anchor_log field."""
        log_path = tmp_path / "audit-json-al.log"
        result, run_dir, stdout, _ = _invoke_audit(
            tmp_path, "a30-al-json",
            extra_args=["--json", "--anchor-log", str(log_path)])
        assert result.exit_code == 0
        data = _get_json_from_stdout(stdout)
        assert data.get("anchor_log") == str(log_path)


# ===========================================================================
# 3. Generated Member Governance
# ===========================================================================

class TestA30GeneratedMemberGovernance:
    def test_module_constant_exists(self):
        """_AUDIT_GENERATED_MEMBERS should be a module-level frozenset."""
        from ai_workflow_hub.cli import _AUDIT_GENERATED_MEMBERS
        assert isinstance(_AUDIT_GENERATED_MEMBERS, frozenset)

    def test_constant_contains_expected_members(self):
        """Generated members should include all known generated files."""
        from ai_workflow_hub.cli import _AUDIT_GENERATED_MEMBERS
        assert "bundle_manifest.json" in _AUDIT_GENERATED_MEMBERS
        assert "attestation.json" in _AUDIT_GENERATED_MEMBERS
        assert "MANIFEST.json" in _AUDIT_GENERATED_MEMBERS
        assert "artifact_chain.json" in _AUDIT_GENERATED_MEMBERS


# ===========================================================================
# 4. Symlink Policy
# ===========================================================================

class TestA30SymlinkPolicy:
    def test_no_symlinks_no_warning(self, tmp_path):
        """Regular files should not trigger symlink warnings."""
        result, run_dir, stdout, stderr = _invoke_audit(
            tmp_path, "a30-sl-none")
        assert result.exit_code == 0
        combined = stdout + stderr
        # Check for the actual warning text, not just the word "symlink"
        assert "symlink(s) detected" not in combined.lower()

    def test_no_follow_symlinks_flag_in_json(self, tmp_path):
        """JSON output should include symlinks field (empty for no symlinks)."""
        result, run_dir, stdout, _ = _invoke_audit(
            tmp_path, "a30-sl-json", extra_args=["--json"])
        assert result.exit_code == 0
        data = _get_json_from_stdout(stdout)
        assert "symlinks" in data
        assert data["symlinks"] == []


# ===========================================================================
# 5. Required Files Policy
# ===========================================================================

class TestA30RequiredFiles:
    def test_required_files_all_present(self, tmp_path):
        """--required-files with existing files should not produce warnings."""
        result, run_dir, stdout, stderr = _invoke_audit(
            tmp_path, "a30-rf-ok",
            extra_args=["--required-files", "state.json,closeout-report.json"])
        assert result.exit_code == 0
        combined = stdout + stderr
        assert "MISSING REQUIRED" not in combined

    def test_required_files_missing_strict_fails(self, tmp_path):
        """--required-files with missing files + --strict should fail."""
        result, run_dir, stdout, stderr = _invoke_audit(
            tmp_path, "a30-rf-miss",
            extra_args=["--required-files", "nonexistent-file.json", "--strict"])
        assert result.exit_code == 1  # strict failure

    def test_required_files_missing_in_json(self, tmp_path):
        """JSON output should include missing_required field."""
        result, run_dir, stdout, _ = _invoke_audit(
            tmp_path, "a30-rf-json",
            extra_args=["--json", "--required-files", "ghost.json"])
        assert result.exit_code == 0
        data = _get_json_from_stdout(stdout)
        assert "missing_required" in data
        assert "ghost.json" in data["missing_required"]

    def test_required_files_severity_in_strict(self, tmp_path):
        """Strict failure should include missing_required in severity."""
        result, run_dir, stdout, _ = _invoke_audit(
            tmp_path, "a30-rf-sev",
            extra_args=["--json", "--strict",
                        "--required-files", "missing1.json,missing2.json"])
        assert result.exit_code == 1
        data = _get_json_from_stdout(stdout)
        assert "strict_severity" in data
        assert data["strict_severity"].get("missing_required") == 2


# ===========================================================================
# 6. Integration: trust_level + anchor_log + verify
# ===========================================================================

class TestA30Integration:
    def test_full_signed_anchored_workflow(self, tmp_path):
        """End-to-end: sign + anchor + verify should produce signed_trusted."""
        key = "integration-key"
        log_path = tmp_path / "integration.log"
        with patch.dict(os.environ, {"AIHUB_SIGNING_KEY": key}):
            result_audit, run_dir, _, _ = _invoke_audit(
                tmp_path, "a30-integ",
                extra_args=["--sign", "--anchor-log", str(log_path)])
        assert result_audit.exit_code == 0
        assert log_path.exists()

        zip_path = _find_audit_zip(run_dir)
        with patch.dict(os.environ, {"AIHUB_SIGNING_KEY": key}):
            result_verify, stdout, _ = _invoke_verify(zip_path)
        assert result_verify.exit_code == 0
        data = _get_json_from_stdout(stdout)
        assert data["trust_level"] == "signed_trusted"
        assert data["verdict"] == "passed"

        # Verify anchor log
        entry = json.loads(log_path.read_text(encoding="utf-8").strip())
        assert entry["signed"] is True
        assert len(entry["zip_sha256"]) == 64
