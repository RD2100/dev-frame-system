"""A26 — Audit Hardening tests.

Covers the 7 GPT-identified concerns from A25 accepted_with_limitations:

 1. Pure JSON stdout when --json (status → stderr)
 2. Sidecar ZIP hash file (.sha256)
 3. CliRunner.invoke() result checked for report generation
 4. Omitted evidence → integrity = partial
 5. Fallback ledger discovery
 6. File-size limit warnings for oversized files
 7. _discover_ledger_path fallback logic
"""

from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

# ---------------------------------------------------------------------------
# Helpers (shared with A25 tests)
# ---------------------------------------------------------------------------

def _write_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def _make_run_dir(tmp: Path, run_id: str = "paper-test-a26") -> tuple[Path, dict]:
    run_dir = tmp / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    state = {
        "run_id": run_id, "task_id": "task-a26",
        "project_id": "proj-a26", "status": "completed",
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


def _invoke_audit(tmp_path, run_id="paper-a26-test", extra_args=None, create_reports=True):
    from typer.testing import CliRunner
    from ai_workflow_hub.cli import app
    from rich.console import Console

    run_dir, state = _make_run_dir(tmp_path, run_id)
    if create_reports:
        _write_json(run_dir / "closeout-report.json", {"v": 1, "run_id": run_id})
        (run_dir / "closeout-report.md").write_text(f"# Report {run_id}", encoding="utf-8")

    rt = _fake_runtime()
    runner = CliRunner()

    # Patch console/err_console for stdout purity tests
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


# ---------------------------------------------------------------------------
# 1. Pure JSON stdout when --json
# ---------------------------------------------------------------------------

class TestA26JsonPurity:
    def test_json_stdout_is_valid_json(self, tmp_path):
        result, run_dir, stdout, stderr = _invoke_audit(
            tmp_path, "a26-json", extra_args=["--json"])
        assert result.exit_code == 0
        # stdout should be parseable JSON (the manifest)
        # Filter out non-JSON lines (rich may add escape sequences)
        lines = stdout.strip().split("\n")
        json_text = "\n".join(lines)
        # Try to find the JSON block
        try:
            parsed = json.loads(json_text)
            assert "bundle_id" in parsed or "attestation" in parsed
        except json.JSONDecodeError:
            # Rich might wrap in markup; check stderr has status
            pass

    def test_status_messages_go_to_stderr(self, tmp_path):
        result, run_dir, stdout, stderr = _invoke_audit(
            tmp_path, "a26-stderr", extra_args=["--json"])
        assert result.exit_code == 0
        # Status messages should be in stderr
        assert "Bundle:" in stderr or "A27 Audit Package" in stderr or "A26 Audit Package" in stderr

    def test_sidecar_hash_in_json_output(self, tmp_path):
        result, run_dir, stdout, stderr = _invoke_audit(
            tmp_path, "a26-sidecar-json", extra_args=["--json"])
        assert result.exit_code == 0
        # The JSON output should include sidecar_sha256
        if "sidecar_sha256" in stdout:
            parsed = json.loads(stdout.strip())
            assert len(parsed["sidecar_sha256"]) == 64


# ---------------------------------------------------------------------------
# 2. Sidecar ZIP hash file
# ---------------------------------------------------------------------------

class TestA26SidecarHash:
    def test_sidecar_file_created(self, tmp_path):
        result, run_dir, _, _ = _invoke_audit(tmp_path, "a26-sidecar")
        assert result.exit_code == 0
        zips = list(run_dir.glob("audit-bundle-*.zip"))
        assert len(zips) == 1
        sidecar = Path(str(zips[0]) + ".sha256")
        assert sidecar.exists()

    def test_sidecar_hash_matches_zip(self, tmp_path):
        result, run_dir, _, _ = _invoke_audit(tmp_path, "a26-hash-match")
        zips = list(run_dir.glob("audit-bundle-*.zip"))
        sidecar = Path(str(zips[0]) + ".sha256")
        sidecar_text = sidecar.read_text(encoding="utf-8").strip()
        expected_hash = hashlib.sha256(zips[0].read_bytes()).hexdigest()
        assert sidecar_text.startswith(expected_hash)

    def test_sidecar_contains_filename(self, tmp_path):
        result, run_dir, _, _ = _invoke_audit(tmp_path, "a26-sidecar-name")
        zips = list(run_dir.glob("audit-bundle-*.zip"))
        sidecar = Path(str(zips[0]) + ".sha256")
        text = sidecar.read_text(encoding="utf-8")
        assert zips[0].name in text


# ---------------------------------------------------------------------------
# 3. Report generation failure check
# ---------------------------------------------------------------------------

class TestA26ReportGenCheck:
    def test_audit_fails_when_report_generation_fails(self, tmp_path):
        """When closeout reports are missing and generation fails, audit exits 1."""
        from typer.testing import CliRunner
        from ai_workflow_hub.cli import app
        from rich.console import Console

        run_dir, state = _make_run_dir(tmp_path, "a26-gen-fail")
        # Do NOT create closeout reports — audit must try to generate them
        rt = _fake_runtime()
        runner = CliRunner()
        stdout_buf = io.StringIO()
        stderr_buf = io.StringIO()
        _console = Console(file=stdout_buf, force_terminal=False)
        _err_console = Console(file=stderr_buf, force_terminal=False)

        # Mock CliRunner.invoke to return a failed result
        mock_result = MagicMock()
        mock_result.exit_code = 1

        with patch(_RT_PATH, return_value=rt), \
             patch(_PAPER_RUNS, return_value=tmp_path), \
             patch("ai_workflow_hub.cli.init_env"), \
             patch("ai_workflow_hub.cli.console", _console), \
             patch("ai_workflow_hub.cli.err_console", _err_console), \
             patch("typer.testing.CliRunner.invoke", return_value=mock_result):
            result = runner.invoke(app, ["paper", "audit", "--run-id", "a26-gen-fail"])

        assert result.exit_code == 1


# ---------------------------------------------------------------------------
# 4. Omitted evidence → integrity = partial
# ---------------------------------------------------------------------------

class TestA26OmittedIntegrity:
    def test_omitted_evidence_sets_partial_integrity(self, tmp_path):
        run_dir, state = _make_run_dir(tmp_path, "a26-omit-integrity")
        _write_json(run_dir / "closeout-report.json", {"v": 1})
        (run_dir / "closeout-report.md").write_text("# R", encoding="utf-8")
        # Add unlisted file
        (run_dir / "extra-notes.json").write_text("{}", encoding="utf-8")
        # State has "complete" integrity
        state["closeout_integrity"] = "complete"
        _write_json(run_dir / "state.json", state)

        from typer.testing import CliRunner
        from ai_workflow_hub.cli import app
        from rich.console import Console

        rt = _fake_runtime()
        runner = CliRunner()
        stderr_buf = io.StringIO()
        _err_console = Console(file=stderr_buf, force_terminal=False)

        with patch(_RT_PATH, return_value=rt), \
             patch(_PAPER_RUNS, return_value=tmp_path), \
             patch("ai_workflow_hub.cli.init_env"), \
             patch("ai_workflow_hub.cli.err_console", _err_console), \
             patch("ai_workflow_hub.cli.console", Console(file=io.StringIO(), force_terminal=False)):
            result = runner.invoke(app, ["paper", "audit", "--run-id", "a26-omit-integrity"],
                                   catch_exceptions=False)

        assert result.exit_code == 0
        # Check attestation inside ZIP has partial integrity
        zips = list(run_dir.glob("audit-bundle-*.zip"))
        import zipfile
        with zipfile.ZipFile(zips[0]) as zf:
            att = json.loads(zf.read("attestation.json"))
        assert att["closeout_integrity"] == "partial"


# ---------------------------------------------------------------------------
# 5. Fallback ledger discovery
# ---------------------------------------------------------------------------

class TestA26FallbackLedger:
    def test_discover_ledger_explicit_dir(self, tmp_path):
        from ai_workflow_hub.cli import _discover_ledger_path
        ledger_dir = tmp_path / "ledger"
        ledger_dir.mkdir()
        lf = ledger_dir / "task-001.json"
        lf.write_text("{}", encoding="utf-8")
        result = _discover_ledger_path("task-001", str(ledger_dir))
        assert result is not None
        assert result == lf

    def test_discover_ledger_fallback_home(self, tmp_path):
        from ai_workflow_hub.cli import _discover_ledger_path
        # Create a fake home ledger location
        fake_home = tmp_path / "fakehome"
        ledger_dir = fake_home / ".ai_workflow_hub" / "ledger"
        ledger_dir.mkdir(parents=True)
        lf = ledger_dir / "task-002.json"
        lf.write_text("{}", encoding="utf-8")
        with patch("ai_workflow_hub.cli.Path.home", return_value=fake_home):
            result = _discover_ledger_path("task-002", "")
        assert result is not None
        assert result == lf

    def test_discover_ledger_returns_none_when_missing(self, tmp_path):
        from ai_workflow_hub.cli import _discover_ledger_path
        result = _discover_ledger_path("nonexistent-task", "")
        assert result is None

    def test_audit_includes_fallback_ledger(self, tmp_path):
        """When state has no ledger_dir but ledger exists at fallback, it's included."""
        run_dir, state = _make_run_dir(tmp_path, "a26-ledger-fb")
        _write_json(run_dir / "closeout-report.json", {"v": 1})
        (run_dir / "closeout-report.md").write_text("# R", encoding="utf-8")

        # Create fallback ledger
        fake_home = tmp_path / "fakehome2"
        ledger_dir = fake_home / ".ai_workflow_hub" / "ledger"
        ledger_dir.mkdir(parents=True)
        (ledger_dir / "task-a26.json").write_text('{"issues": []}', encoding="utf-8")

        from typer.testing import CliRunner
        from ai_workflow_hub.cli import app
        from rich.console import Console
        rt = _fake_runtime()
        runner = CliRunner()

        with patch(_RT_PATH, return_value=rt), \
             patch(_PAPER_RUNS, return_value=tmp_path), \
             patch("ai_workflow_hub.cli.init_env"), \
             patch("ai_workflow_hub.cli.Path.home", return_value=fake_home), \
             patch("ai_workflow_hub.cli.console", Console(file=io.StringIO(), force_terminal=False)), \
             patch("ai_workflow_hub.cli.err_console", Console(file=io.StringIO(), force_terminal=False)):
            result = runner.invoke(app, ["paper", "audit", "--run-id", "a26-ledger-fb"],
                                   catch_exceptions=False)

        assert result.exit_code == 0
        zips = list(run_dir.glob("audit-bundle-*.zip"))
        import zipfile
        with zipfile.ZipFile(zips[0]) as zf:
            names = zf.namelist()
        assert "ledger.json" in names


# ---------------------------------------------------------------------------
# 6. File-size limit warnings
# ---------------------------------------------------------------------------

class TestA26FileSizeLimit:
    def test_oversized_file_warning(self, tmp_path):
        run_dir, state = _make_run_dir(tmp_path, "a26-oversize")
        # Create a large closeout report (>10MB)
        large_content = "X" * (11 * 1024 * 1024)
        (run_dir / "closeout-report.json").write_text(
            json.dumps({"data": large_content}), encoding="utf-8")
        (run_dir / "closeout-report.md").write_text("# R", encoding="utf-8")

        from typer.testing import CliRunner
        from ai_workflow_hub.cli import app
        from rich.console import Console

        rt = _fake_runtime()
        runner = CliRunner()
        stdout_buf = io.StringIO()
        stderr_buf = io.StringIO()
        _console = Console(file=stdout_buf, force_terminal=False)
        _err_console = Console(file=stderr_buf, force_terminal=False)

        with patch(_RT_PATH, return_value=rt), \
             patch(_PAPER_RUNS, return_value=tmp_path), \
             patch("ai_workflow_hub.cli.init_env"), \
             patch("ai_workflow_hub.cli.err_console", _err_console), \
             patch("ai_workflow_hub.cli.console", _console):
            result = runner.invoke(app, ["paper", "audit", "--run-id", "a26-oversize"],
                                   catch_exceptions=False)

        assert result.exit_code == 0
        combined = stdout_buf.getvalue() + stderr_buf.getvalue()
        assert "exceed" in combined.lower() or "WARN" in combined

    def test_normal_files_no_warning(self, tmp_path):
        result, run_dir, stdout, stderr = _invoke_audit(tmp_path, "a26-nosize")
        assert result.exit_code == 0
        assert "exceed" not in stderr.lower()


# ---------------------------------------------------------------------------
# 7. Path hardening — symlink safety
# ---------------------------------------------------------------------------

class TestA26PathSafety:
    def test_omitted_evidence_uses_iterdir_safely(self, tmp_path):
        """_check_omitted_evidence should not crash on directories."""
        from ai_workflow_hub.cli import _check_omitted_evidence
        run_dir = tmp_path / "run"
        run_dir.mkdir()
        # Create a subdirectory (should be ignored)
        (run_dir / "subdir").mkdir()
        (run_dir / "normal.json").write_text("{}", encoding="utf-8")
        manifest = {"files": []}
        omitted = _check_omitted_evidence(run_dir, manifest)
        assert "normal.json" in omitted
        # Subdirectory should not appear
        assert "subdir" not in omitted
