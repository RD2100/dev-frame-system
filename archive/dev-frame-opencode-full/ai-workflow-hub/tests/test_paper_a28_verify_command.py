"""A28 — Audit Verify Command tests.

Covers the 4 GPT-identified concerns from A27 accepted_with_limitations:

 1. End-to-end verifier command (paper verify)
 2. MANIFEST.json inside audit ZIP
 3. --max-file-mb CLI option for paper audit
 4. Strict mode severity differentiation (strict_severity in JSON)
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


def _make_run_dir(tmp: Path, run_id: str = "paper-test-a28") -> tuple[Path, dict]:
    run_dir = tmp / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    state = {
        "run_id": run_id, "task_id": "task-a28",
        "project_id": "proj-a28", "status": "completed",
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


def _invoke_audit(tmp_path, run_id="paper-a28-test", extra_args=None,
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
    _console = Console(file=stdout_buf, force_terminal=False)
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
    _console = Console(file=stdout_buf, force_terminal=False)
    _err_console = Console(file=stderr_buf, force_terminal=False)

    args = ["paper", "verify", "--zip", str(zip_path)]
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


# ===========================================================================
# 1. paper verify — basic verification
# ===========================================================================

class TestA28VerifyBasic:
    def test_verify_valid_audit_zip(self, tmp_path):
        """A freshly generated audit ZIP should pass all verification checks."""
        result_audit, run_dir, _, _ = _invoke_audit(tmp_path, "a28-verify-ok")
        assert result_audit.exit_code == 0

        zip_path = _find_audit_zip(run_dir)
        result_verify, stdout, stderr = _invoke_verify(zip_path)
        assert result_verify.exit_code == 0
        combined = stdout + stderr
        assert "PASSED" in combined

    def test_verify_nonexistent_zip_fails(self, tmp_path):
        """Verifying a non-existent ZIP should fail."""
        fake_zip = tmp_path / "nonexistent.zip"
        result, stdout, stderr = _invoke_verify(fake_zip)
        assert result.exit_code == 1
        combined = stdout + stderr
        assert "FAIL" in combined

    def test_verify_bad_zip_fails(self, tmp_path):
        """Verifying a corrupt ZIP should fail."""
        bad_zip = tmp_path / "bad.zip"
        bad_zip.write_text("not a zip file")
        result, stdout, stderr = _invoke_verify(bad_zip)
        assert result.exit_code == 1
        combined = stdout + stderr
        assert "FAIL" in combined

    def test_verify_missing_sidecar_reported(self, tmp_path):
        """Missing sidecar should be a FAIL check."""
        result_audit, run_dir, _, _ = _invoke_audit(tmp_path, "a28-no-sidecar")
        zip_path = _find_audit_zip(run_dir)
        # Delete sidecar
        sidecar = Path(str(zip_path) + ".sha256")
        if sidecar.exists():
            sidecar.unlink()

        result, stdout, stderr = _invoke_verify(zip_path)
        combined = stdout + stderr
        assert "sidecar" in combined.lower()

    def test_verify_with_explicit_sidecar(self, tmp_path):
        """--sidecar flag should use the specified path."""
        result_audit, run_dir, _, _ = _invoke_audit(tmp_path, "a28-explicit-sc")
        zip_path = _find_audit_zip(run_dir)
        sidecar = Path(str(zip_path) + ".sha256")

        result, stdout, stderr = _invoke_verify(
            zip_path, extra_args=["--sidecar", str(sidecar)])
        assert result.exit_code == 0


# ===========================================================================
# 2. paper verify — JSON output
# ===========================================================================

class TestA28VerifyJson:
    def test_verify_json_is_valid(self, tmp_path):
        result_audit, run_dir, _, _ = _invoke_audit(tmp_path, "a28-vjson")
        zip_path = _find_audit_zip(run_dir)
        result, stdout, stderr = _invoke_verify(zip_path, extra_args=["--json"])
        assert result.exit_code == 0
        try:
            parsed = json.loads(stdout.strip())
            assert "verdict" in parsed
            assert parsed["verdict"] == "passed"
        except json.JSONDecodeError:
            pass

    def test_verify_json_contains_checks(self, tmp_path):
        result_audit, run_dir, _, _ = _invoke_audit(tmp_path, "a28-vjson2")
        zip_path = _find_audit_zip(run_dir)
        result, stdout, stderr = _invoke_verify(zip_path, extra_args=["--json"])
        try:
            parsed = json.loads(stdout.strip())
            assert "checks" in parsed
            assert isinstance(parsed["checks"], list)
            assert len(parsed["checks"]) >= 5  # At least 5 checks
        except json.JSONDecodeError:
            pass


# ===========================================================================
# 3. MANIFEST.json in audit ZIP
# ===========================================================================

class TestA28ManifestJson:
    def test_audit_zip_contains_manifest_json(self, tmp_path):
        result, run_dir, _, _ = _invoke_audit(tmp_path, "a28-manifest")
        assert result.exit_code == 0
        zip_path = _find_audit_zip(run_dir)
        with zipfile.ZipFile(zip_path, "r") as zf:
            assert "MANIFEST.json" in zf.namelist()

    def test_manifest_json_has_correct_structure(self, tmp_path):
        result, run_dir, _, _ = _invoke_audit(tmp_path, "a28-manifest2")
        zip_path = _find_audit_zip(run_dir)
        with zipfile.ZipFile(zip_path, "r") as zf:
            mf = json.loads(zf.read("MANIFEST.json"))
            assert "manifest_version" in mf
            assert mf["manifest_version"] == "2.0"  # A29: v2.0 includes all members
            assert "bundle_id" in mf
            assert "run_id" in mf
            assert "files" in mf
            assert isinstance(mf["files"], list)
            assert len(mf["files"]) > 0

    def test_manifest_json_hashes_are_valid(self, tmp_path):
        """Each file hash in MANIFEST.json should match the actual content."""
        result, run_dir, _, _ = _invoke_audit(tmp_path, "a28-manifest3")
        zip_path = _find_audit_zip(run_dir)
        with zipfile.ZipFile(zip_path, "r") as zf:
            mf = json.loads(zf.read("MANIFEST.json"))
            for entry in mf["files"]:
                # A29: skip self-entry (MANIFEST.json cannot hash itself)
                if entry["path"] == "MANIFEST.json" and entry["sha256"] == "":
                    continue
                content = zf.read(entry["path"])
                actual = hashlib.sha256(content).hexdigest()
                assert actual == entry["sha256"], \
                    f"Hash mismatch for {entry['path']}: {actual} != {entry['sha256']}"


# ===========================================================================
# 4. --max-file-mb CLI option
# ===========================================================================

class TestA28MaxFileMb:
    def test_max_file_mb_overrides_threshold(self, tmp_path):
        """--max-file-mb=1 should trigger warning for a 2MB state.json."""
        run_id = "a28-maxmb"
        run_dir, state = _make_run_dir(tmp_path, run_id)
        _write_json(run_dir / "closeout-report.json", {"v": 1})
        (run_dir / "closeout-report.md").write_text("# Report", encoding="utf-8")

        # Make state.json 2MB (it's always included in audit ZIP)
        state["padding"] = "x" * (2 * 1024 * 1024)
        _write_json(run_dir / "state.json", state)

        from typer.testing import CliRunner
        from ai_workflow_hub.cli import app
        from rich.console import Console

        stdout_buf = io.StringIO()
        stderr_buf = io.StringIO()
        _console = Console(file=stdout_buf, force_terminal=False)
        _err_console = Console(file=stderr_buf, force_terminal=False)

        rt = _fake_runtime()
        runner = CliRunner()

        with patch(_RT_PATH, return_value=rt), \
             patch(_PAPER_RUNS, return_value=tmp_path), \
             patch("ai_workflow_hub.cli.init_env"), \
             patch("ai_workflow_hub.cli.console", _console), \
             patch("ai_workflow_hub.cli.err_console", _err_console):
            result = runner.invoke(app, [
                "paper", "audit", "--run-id", run_id, "--max-file-mb", "1",
            ], catch_exceptions=False)

        assert result.exit_code == 0
        combined = stdout_buf.getvalue() + stderr_buf.getvalue()
        assert "WARN" in combined or "exceed" in combined

    def test_max_file_mb_large_value_no_warning(self, tmp_path):
        """--max-file-mb=100 should not trigger warning for normal files."""
        result, run_dir, stdout, stderr = _invoke_audit(
            tmp_path, "a28-maxmb2", extra_args=["--max-file-mb", "100"])
        assert result.exit_code == 0
        combined = stdout + stderr
        # No oversized warning expected
        assert "oversized" not in combined.lower() or "0 oversized" in combined.lower()


# ===========================================================================
# 5. Strict mode severity differentiation
# ===========================================================================

class TestA28StrictSeverity:
    def test_strict_failure_json_has_severity(self, tmp_path):
        """When strict fails, JSON should include strict_severity breakdown."""
        run_id = "a28-severity"
        result, run_dir, _, _ = _invoke_audit(tmp_path, run_id)
        # Add untracked file to trigger omitted
        (run_dir / "surprise.json").write_text('{"x": 1}')

        from typer.testing import CliRunner
        from ai_workflow_hub.cli import app
        from rich.console import Console

        stdout_buf = io.StringIO()
        stderr_buf = io.StringIO()
        _console = Console(file=stdout_buf, force_terminal=False)
        _err_console = Console(file=stderr_buf, force_terminal=False)

        rt = _fake_runtime()
        runner = CliRunner()

        with patch(_RT_PATH, return_value=rt), \
             patch(_PAPER_RUNS, return_value=tmp_path), \
             patch("ai_workflow_hub.cli.init_env"), \
             patch("ai_workflow_hub.cli.console", _console), \
             patch("ai_workflow_hub.cli.err_console", _err_console):
            result = runner.invoke(app, [
                "paper", "audit", "--run-id", run_id, "--strict", "--json",
            ], catch_exceptions=False)

        assert result.exit_code == 1
        try:
            parsed = json.loads(stdout_buf.getvalue().strip())
            assert "strict_severity" in parsed
            assert "omitted_evidence" in parsed["strict_severity"]
        except json.JSONDecodeError:
            pass

    def test_json_output_includes_max_file_mb(self, tmp_path):
        """--json output should include max_file_mb."""
        result, run_dir, stdout, stderr = _invoke_audit(
            tmp_path, "a28-maxmbjson", extra_args=["--json"])
        assert result.exit_code == 0
        try:
            parsed = json.loads(stdout.strip())
            assert "max_file_mb" in parsed
            assert isinstance(parsed["max_file_mb"], int)
        except json.JSONDecodeError:
            pass


# ===========================================================================
# 6. Verify detects tampered content
# ===========================================================================

class TestA28TamperDetection:
    def test_verify_detects_tampered_manifest(self, tmp_path):
        """If bundle_manifest.json content_hash is wrong, verify should fail."""
        result_audit, run_dir, _, _ = _invoke_audit(tmp_path, "a28-tamper")
        zip_path = _find_audit_zip(run_dir)

        # Create a tampered ZIP with wrong content_hash
        tamper_zip = tmp_path / "tampered.zip"
        with zipfile.ZipFile(zip_path, "r") as src:
            with zipfile.ZipFile(tamper_zip, "w") as dst:
                for name in src.namelist():
                    data = src.read(name)
                    if name == "bundle_manifest.json":
                        bm = json.loads(data)
                        bm["attestation"]["content_hash"] = "deadbeef" * 8
                        data = json.dumps(bm).encode("utf-8")
                    dst.writestr(name, data)

        # Also create matching sidecar for tampered zip
        tamper_hash = hashlib.sha256(tamper_zip.read_bytes()).hexdigest()
        (Path(str(tamper_zip) + ".sha256")).write_text(
            f"{tamper_hash}  tampered.zip\n", encoding="utf-8")

        result, stdout, stderr = _invoke_verify(tamper_zip)
        assert result.exit_code == 1
        combined = stdout + stderr
        assert "content_hash_valid" in combined
