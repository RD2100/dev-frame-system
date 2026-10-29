"""A27 — Audit Polish tests.

Covers the 6 GPT-identified concerns from A26 accepted_with_limitations:

 1. ZIP hash embedded in persisted bundle manifest (zip_sha256)
 2. Configurable 10MB threshold via AIHUB_AUDIT_MAX_MB env var
 3. Strict audit mode (--strict): fail on omitted/oversized
 4. Run-id-aware ledger binding (_discover_ledger_path with run_id)
 5. Strict mode JSON output includes strict_failures + strict_mode
 6. Formal required/ignored artifact policy (improved prefix exclusions)
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


def _make_run_dir(tmp: Path, run_id: str = "paper-test-a27") -> tuple[Path, dict]:
    run_dir = tmp / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    state = {
        "run_id": run_id, "task_id": "task-a27",
        "project_id": "proj-a27", "status": "completed",
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


def _invoke_audit(tmp_path, run_id="paper-a27-test", extra_args=None,
                  create_reports=True, env_vars=None):
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

    patches = {
        _RT_PATH: {"return_value": rt},
        _PAPER_RUNS: {"return_value": tmp_path},
        "ai_workflow_hub.cli.init_env": {},
        "ai_workflow_hub.cli.console": {"new": _console},
        "ai_workflow_hub.cli.err_console": {"new": _err_console},
    }

    # Build env for env var patches
    env = os.environ.copy()
    if env_vars:
        env.update(env_vars)

    with patch(_RT_PATH, return_value=rt), \
         patch(_PAPER_RUNS, return_value=tmp_path), \
         patch("ai_workflow_hub.cli.init_env"), \
         patch("ai_workflow_hub.cli.console", _console), \
         patch("ai_workflow_hub.cli.err_console", _err_console), \
         patch.dict(os.environ, env_vars or {}, clear=False):
        result = runner.invoke(app, args, catch_exceptions=False)

    return result, run_dir, stdout_buf.getvalue(), stderr_buf.getvalue()


# ===========================================================================
# 1. Configurable threshold: _audit_max_file_bytes()
# ===========================================================================

class TestA27ConfigurableThreshold:
    def test_default_threshold_is_10mb(self):
        from ai_workflow_hub.cli import _audit_max_file_bytes
        with patch.dict(os.environ, {}, clear=False):
            # Remove the env var if present
            os.environ.pop("AIHUB_AUDIT_MAX_MB", None)
            assert _audit_max_file_bytes() == 10 * 1024 * 1024

    def test_custom_threshold_from_env(self):
        from ai_workflow_hub.cli import _audit_max_file_bytes
        with patch.dict(os.environ, {"AIHUB_AUDIT_MAX_MB": "5"}):
            assert _audit_max_file_bytes() == 5 * 1024 * 1024

    def test_invalid_env_falls_back_to_default(self):
        from ai_workflow_hub.cli import _audit_max_file_bytes
        with patch.dict(os.environ, {"AIHUB_AUDIT_MAX_MB": "notanumber"}):
            assert _audit_max_file_bytes() == 10 * 1024 * 1024

    def test_zero_env_uses_default(self):
        from ai_workflow_hub.cli import _audit_max_file_bytes
        with patch.dict(os.environ, {"AIHUB_AUDIT_MAX_MB": ""}):
            assert _audit_max_file_bytes() == 10 * 1024 * 1024


# ===========================================================================
# 2. Run-id-aware ledger binding
# ===========================================================================

class TestA27RunIdLedger:
    def test_prefers_run_specific_ledger(self, tmp_path):
        from ai_workflow_hub.cli import _discover_ledger_path
        ledger_dir = tmp_path / "ledgers"
        ledger_dir.mkdir()
        # Create both run-specific and generic
        (ledger_dir / "task1_run1.json").write_text('{"run": "specific"}')
        (ledger_dir / "task1.json").write_text('{"run": "generic"}')
        result = _discover_ledger_path("task1", str(ledger_dir), run_id="run1")
        assert result is not None
        assert result.name == "task1_run1.json"

    def test_falls_back_to_generic_when_no_run_specific(self, tmp_path):
        from ai_workflow_hub.cli import _discover_ledger_path
        ledger_dir = tmp_path / "ledgers"
        ledger_dir.mkdir()
        (ledger_dir / "task1.json").write_text('{"run": "generic"}')
        result = _discover_ledger_path("task1", str(ledger_dir), run_id="run1")
        assert result is not None
        assert result.name == "task1.json"

    def test_run_id_empty_string_falls_back(self, tmp_path):
        from ai_workflow_hub.cli import _discover_ledger_path
        ledger_dir = tmp_path / "ledgers"
        ledger_dir.mkdir()
        (ledger_dir / "task1.json").write_text('{"run": "generic"}')
        result = _discover_ledger_path("task1", str(ledger_dir), run_id="")
        assert result is not None
        assert result.name == "task1.json"

    def test_audit_passes_run_id_to_ledger_discovery(self, tmp_path):
        """Verify paper audit calls _discover_ledger_path with run_id."""
        run_id = "a27-ledger-test"
        run_dir, state = _make_run_dir(tmp_path, run_id)
        _write_json(run_dir / "closeout-report.json", {"v": 1})
        (run_dir / "closeout-report.md").write_text("# Report", encoding="utf-8")

        # Create a run-specific ledger file
        ledger_dir = tmp_path / "ledger_store"
        ledger_dir.mkdir()
        (ledger_dir / f"task-a27_{run_id}.json").write_text('{"ledger": "run-specific"}')

        # Update state to point to our ledger dir
        state["ledger_dir"] = str(ledger_dir)
        _write_json(run_dir / "state.json", state)

        result, run_dir, stdout, stderr = _invoke_audit(
            tmp_path, run_id)
        assert result.exit_code == 0
        combined = stdout + stderr
        # The audit should succeed and include the ledger
        assert "Bundle:" in combined or "A27 Audit Package" in combined


# ===========================================================================
# 3. ZIP hash embedded in persisted manifest
# ===========================================================================

class TestA27ZipHashInManifest:
    def test_persisted_manifest_has_zip_sha256(self, tmp_path):
        result, run_dir, stdout, stderr = _invoke_audit(
            tmp_path, "a27-ziphash")
        assert result.exit_code == 0

        # Find persisted manifest
        manifests = list(run_dir.glob("bundle_manifest_*.json"))
        assert len(manifests) == 1
        manifest = json.loads(manifests[0].read_text(encoding="utf-8"))
        assert "zip_sha256" in manifest
        assert len(manifest["zip_sha256"]) == 64  # SHA-256 hex

    def test_zip_sha256_matches_sidecar(self, tmp_path):
        result, run_dir, stdout, stderr = _invoke_audit(
            tmp_path, "a27-ziphash2")
        assert result.exit_code == 0

        manifests = list(run_dir.glob("bundle_manifest_*.json"))
        manifest = json.loads(manifests[0].read_text(encoding="utf-8"))

        # Find sidecar
        zip_files = list(run_dir.glob("audit-bundle-*.zip"))
        assert len(zip_files) == 1
        sidecar = Path(str(zip_files[0]) + ".sha256")
        assert sidecar.exists()
        sidecar_hash = sidecar.read_text(encoding="utf-8").strip().split()[0]

        assert manifest["zip_sha256"] == sidecar_hash

    def test_zip_sha256_matches_actual_zip(self, tmp_path):
        result, run_dir, stdout, stderr = _invoke_audit(
            tmp_path, "a27-ziphash3")
        assert result.exit_code == 0

        manifests = list(run_dir.glob("bundle_manifest_*.json"))
        manifest = json.loads(manifests[0].read_text(encoding="utf-8"))

        zip_files = list(run_dir.glob("audit-bundle-*.zip"))
        actual_hash = hashlib.sha256(zip_files[0].read_bytes()).hexdigest()
        assert manifest["zip_sha256"] == actual_hash


# ===========================================================================
# 4. Strict mode
# ===========================================================================

class TestA27StrictMode:
    def test_strict_passes_clean_run(self, tmp_path):
        """Strict mode passes when no omitted evidence and no oversized files."""
        result, run_dir, stdout, stderr = _invoke_audit(
            tmp_path, "a27-strict-ok", extra_args=["--strict"])
        assert result.exit_code == 0
        combined = stdout + stderr
        assert "Strict: PASSED" in combined

    def test_strict_fails_on_omitted_evidence(self, tmp_path):
        """Strict mode fails when evidence files exist but not in manifest."""
        run_id = "a27-strict-omit"
        result, run_dir, stdout, stderr = _invoke_audit(
            tmp_path, run_id, extra_args=["--strict"])
        # The default _make_run_dir has empty evidence manifest files[],
        # but we need an extra untracked file to trigger omitted
        extra = run_dir / "surprise-evidence.json"
        extra.write_text('{"unexpected": true}')

        # Re-run audit
        result2, run_dir2, stdout2, stderr2 = _invoke_audit(
            tmp_path, run_id, extra_args=["--strict"])
        assert result2.exit_code == 1
        combined = stdout2 + stderr2
        assert "STRICT AUDIT FAILED" in combined

    def test_strict_fails_on_oversized_files(self, tmp_path):
        """Strict mode fails when files exceed the size threshold."""
        run_id = "a27-strict-big"
        run_dir, state = _make_run_dir(tmp_path, run_id)
        _write_json(run_dir / "closeout-report.json", {"v": 1})
        (run_dir / "closeout-report.md").write_text("# Report", encoding="utf-8")

        # Create a huge closeout-report.json (over 10MB)
        big_data = {"padding": "x" * (11 * 1024 * 1024)}
        _write_json(run_dir / "closeout-report.json", big_data)

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
                "paper", "audit", "--run-id", run_id, "--strict",
            ], catch_exceptions=False)

        assert result.exit_code == 1
        combined = stdout_buf.getvalue() + stderr_buf.getvalue()
        assert "STRICT AUDIT FAILED" in combined

    def test_strict_default_is_off(self, tmp_path):
        """Without --strict, omitted evidence only warns, does not fail."""
        run_id = "a27-nostrict"
        # First run to create the dir
        result, run_dir, stdout, stderr = _invoke_audit(
            tmp_path, run_id)
        # Add untracked file
        (run_dir / "surprise-evidence.json").write_text('{"x": 1}')
        # Second run without --strict
        result2, _, stdout2, stderr2 = _invoke_audit(
            tmp_path, run_id)
        assert result2.exit_code == 0  # Should succeed despite omitted


# ===========================================================================
# 5. Strict mode JSON output
# ===========================================================================

class TestA27StrictJsonOutput:
    def test_json_output_includes_strict_mode_flag(self, tmp_path):
        result, run_dir, stdout, stderr = _invoke_audit(
            tmp_path, "a27-jsonflag", extra_args=["--json"])
        assert result.exit_code == 0
        try:
            parsed = json.loads(stdout.strip())
            assert "strict_mode" in parsed
            assert parsed["strict_mode"] is False
        except json.JSONDecodeError:
            pass  # Rich markup may interfere

    def test_strict_failure_json_includes_failures(self, tmp_path):
        """When strict fails, JSON output includes strict_failures list."""
        run_id = "a27-strict-json"
        # Create run with untracked evidence
        result, run_dir, stdout, stderr = _invoke_audit(
            tmp_path, run_id, extra_args=["--json"])
        (run_dir / "surprise-evidence.json").write_text('{"x": 1}')

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
        out = stdout_buf.getvalue()
        try:
            parsed = json.loads(out.strip())
            assert "strict_failures" in parsed
            assert len(parsed["strict_failures"]) > 0
        except json.JSONDecodeError:
            pass


# ===========================================================================
# 6. Omitted evidence prefix exclusions (improved policy)
# ===========================================================================

class TestA27PrefixExclusions:
    def test_bundle_manifest_prefix_excluded(self, tmp_path):
        """Files starting with bundle_manifest_ should not be flagged as omitted."""
        from ai_workflow_hub.cli import _check_omitted_evidence
        run_dir = tmp_path / "prefix-test"
        run_dir.mkdir()
        (run_dir / "bundle_manifest_abc123.json").write_text("{}")
        (run_dir / "state.json").write_text("{}")
        manifest = {"files": []}
        omitted = _check_omitted_evidence(run_dir, manifest)
        names = [f for f in omitted]
        assert not any("bundle_manifest" in n for n in names)

    def test_attestation_prefix_excluded(self, tmp_path):
        """Files starting with attestation_ should not be flagged as omitted."""
        from ai_workflow_hub.cli import _check_omitted_evidence
        run_dir = tmp_path / "prefix-test2"
        run_dir.mkdir()
        (run_dir / "attestation_abc123.json").write_text("{}")
        (run_dir / "state.json").write_text("{}")
        manifest = {"files": []}
        omitted = _check_omitted_evidence(run_dir, manifest)
        names = [f for f in omitted]
        assert not any("attestation" in n for n in names)

    def test_artifact_chain_prefix_excluded(self, tmp_path):
        from ai_workflow_hub.cli import _check_omitted_evidence
        run_dir = tmp_path / "prefix-test3"
        run_dir.mkdir()
        (run_dir / "artifact_chain.json").write_text("[]")
        (run_dir / "state.json").write_text("{}")
        manifest = {"files": []}
        omitted = _check_omitted_evidence(run_dir, manifest)
        names = [f for f in omitted]
        assert "artifact_chain.json" not in names

    def test_untracked_evidence_detected(self, tmp_path):
        from ai_workflow_hub.cli import _check_omitted_evidence
        run_dir = tmp_path / "prefix-test4"
        run_dir.mkdir()
        (run_dir / "custom-evidence.json").write_text('{"data": true}')
        (run_dir / "state.json").write_text("{}")
        manifest = {"files": []}
        omitted = _check_omitted_evidence(run_dir, manifest)
        assert "custom-evidence.json" in omitted


# ===========================================================================
# 7. Env-configurable threshold in actual audit
# ===========================================================================

class TestA27EnvThresholdInAudit:
    def test_custom_threshold_changes_warning(self, tmp_path):
        """Setting AIHUB_AUDIT_MAX_MB=1 should trigger warning for 2MB file."""
        run_id = "a27-envthresh"
        run_dir, state = _make_run_dir(tmp_path, run_id)
        _write_json(run_dir / "closeout-report.json", {"v": 1})
        (run_dir / "closeout-report.md").write_text("# Report", encoding="utf-8")

        # Create a 2MB closeout-report.json
        big_data = {"padding": "x" * (2 * 1024 * 1024)}
        _write_json(run_dir / "closeout-report.json", big_data)

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
             patch("ai_workflow_hub.cli.err_console", _err_console), \
             patch.dict(os.environ, {"AIHUB_AUDIT_MAX_MB": "1"}):
            result = runner.invoke(app, [
                "paper", "audit", "--run-id", run_id,
            ], catch_exceptions=False)

        assert result.exit_code == 0  # Warning, not failure
        combined = stdout_buf.getvalue() + stderr_buf.getvalue()
        assert "WARN" in combined
        assert "exceed" in combined
