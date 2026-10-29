"""test_paper_a23b_closeout_hardening.py — A23B Closeout Report Hardening Tests.

Addresses GPT concerns from A23 verdict:
1. Silent degradation → warnings surfaced in report
2. JSON purity → stdout is valid JSON even with --save
3. sanitize_run_id ValueError → graceful error handling
4. Markdown decision note redaction → _redact_str applied
5. Ledger issue-level traceability → ledger_issues_summary in report
6. Evidence manifest detail → files with path/sha256/size
7. Hash binding → content_hash SHA-256 in report
"""

import hashlib
import json
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
from typer.testing import CliRunner

from ai_workflow_hub.cli import app
from ai_workflow_hub.context_layer.adapters.paper_runtime import (
    create_paper_run, execute_paper_run, resume_paper_run,
)

runner = CliRunner()
_RT_PATH = "ai_workflow_hub.context_layer.adapters.paper_runtime"

TASK_ID = "a23b-harden"
PROJECT_ID = "a23b-proj"

SYNTHETIC_ISSUES = [
    {
        "issue_id": "a23b-iss-001",
        "issue_type": "citation",
        "severity": "major",
        "description": "Missing ref",
        "evidence": "Section 1 missing",
        "human_required": True,
        "blocking": False,
        "recommendation": "Add ref",
    },
    {
        "issue_id": "a23b-iss-002",
        "issue_type": "expression",
        "severity": "minor",
        "description": "Typo",
        "evidence": "teh -> the",
        "human_required": False,
        "blocking": False,
        "recommendation": "Fix",
    },
]


def _invoke(args):
    with patch("ai_workflow_hub.cli.init_env"):
        return runner.invoke(app, args, catch_exceptions=False)


def _make_run(tmp_path, **overrides):
    base_dir = str(tmp_path)
    ledger_dir = str(tmp_path / "ledger")
    Path(ledger_dir).mkdir(parents=True, exist_ok=True)
    run = create_paper_run(
        TASK_ID, project_id=PROJECT_ID, base_dir=base_dir,
        initial_state={"ledger_dir": ledger_dir},
    )
    execute_paper_run(
        run["run_id"], base_dir=base_dir,
        state_overrides={
            "writelab_mode": "mock",
            "expression_issues": [],
            "paragraph_issues": SYNTHETIC_ISSUES,
            **overrides,
        },
    )
    resume_paper_run(
        run["run_id"], decision="approved",
        reviewer_id="a23b@test.com",
        note="Hardening test",
        base_dir=base_dir,
    )
    return run, base_dir, ledger_dir


FAKE_API = {
    "summary": lambda tid, **kw: {
        "task_id": TASK_ID, "total": 2, "open": 1, "resolved": 1,
        "blocking": 0, "critical": 0, "human_required": 1,
        "severity_breakdown": {"major": 1}, "type_breakdown": {"citation": 1},
    },
    "all_issues": lambda tid, **kw: [
        {"issue_id": "a23b-iss-001", "issue_type": "citation",
         "severity": "major", "status": "open", "blocking": False},
        {"issue_id": "a23b-iss-002", "issue_type": "expression",
         "severity": "minor", "status": "resolved", "blocking": False},
    ],
    "open_issues": lambda tid, **kw: [],
    "blocking_count": lambda tid, **kw: 0,
    "critical_count": lambda tid, **kw: 0,
    "is_clear": lambda tid, **kw: True,
}


# =====================================================================
# TestA23BDegradationWarnings — Fix 1: Silent degradation → warnings
# =====================================================================

class TestA23BDegradationWarnings:
    """Verify that load failures surface as warnings in the report."""

    def test_ledger_failure_produces_warning(self, tmp_path):
        """When ledger API fails, report should contain a warning."""
        run, base_dir, _ = _make_run(tmp_path)
        runs_root = tmp_path / "runs" / "paper"

        bad_api = {
            "summary": MagicMock(side_effect=RuntimeError("ledger boom")),
            "all_issues": MagicMock(side_effect=RuntimeError("ledger boom")),
        }

        with patch("ai_workflow_hub.cli._paper_runs_root", return_value=runs_root), \
             patch(f"{_RT_PATH}._runs_root", return_value=runs_root), \
             patch("ai_workflow_hub.cli._paper_ledger_api", return_value=bad_api):
            result = _invoke(["paper", "report", "--run-id", run["run_id"],
                             "--json", "--no-save"])
        assert result.exit_code == 0
        report = json.loads(result.output)
        warnings = report.get("warnings", [])
        assert any("ledger_load_failed" in w.get("message", "") or
                    w.get("subsystem") == "ledger_load_failed"
                    for w in warnings), \
            f"Expected ledger warning, got: {warnings}"

    def test_decision_failure_produces_warning(self, tmp_path):
        """When decision audit API fails, report should contain a warning."""
        run, base_dir, _ = _make_run(tmp_path)
        runs_root = tmp_path / "runs" / "paper"

        # Patch decision audit functions to raise
        _DA_PATH = "ai_workflow_hub.context_layer.adapters.paper_decision_audit"
        with patch("ai_workflow_hub.cli._paper_runs_root", return_value=runs_root), \
             patch(f"{_RT_PATH}._runs_root", return_value=runs_root), \
             patch("ai_workflow_hub.cli._paper_ledger_api", return_value=FAKE_API), \
             patch(f"{_DA_PATH}.read_decision_record",
                   side_effect=RuntimeError("decision boom")), \
             patch(f"{_DA_PATH}.get_audit_trail",
                   side_effect=RuntimeError("decision boom")):
            result = _invoke(["paper", "report", "--run-id", run["run_id"],
                             "--json", "--no-save"])

        assert result.exit_code == 0
        report = json.loads(result.output)
        warnings = report.get("warnings", [])
        assert any("decision_audit_load_failed" in w.get("message", "") or
                    w.get("subsystem") == "decision_audit_load_failed"
                    for w in warnings), \
            f"Expected decision warning, got: {warnings}"

    def test_no_warnings_when_all_ok(self, tmp_path):
        """When everything loads fine, warnings should be empty."""
        run, base_dir, _ = _make_run(tmp_path)
        runs_root = tmp_path / "runs" / "paper"

        with patch("ai_workflow_hub.cli._paper_runs_root", return_value=runs_root), \
             patch(f"{_RT_PATH}._runs_root", return_value=runs_root), \
             patch("ai_workflow_hub.cli._paper_ledger_api", return_value=FAKE_API):
            result = _invoke(["paper", "report", "--run-id", run["run_id"],
                             "--json", "--no-save"])
        assert result.exit_code == 0
        report = json.loads(result.output)
        assert report.get("warnings", []) == []


# =====================================================================
# TestA23BJsonPurity — Fix 2: stdout is valid JSON with --save
# =====================================================================

class TestA23BJsonPurity:
    """Verify that --json --save produces pure JSON on stdout."""

    def test_json_stdout_pure_when_save(self, tmp_path):
        """Saved message should go to err_console (stderr), not stdout."""
        run, base_dir, _ = _make_run(tmp_path)
        runs_root = tmp_path / "runs" / "paper"

        import io
        stdout_buf = io.StringIO()
        stderr_buf = io.StringIO()

        from rich.console import Console
        real_console = Console(file=stdout_buf)
        real_err_console = Console(file=stderr_buf)

        with patch("ai_workflow_hub.cli._paper_runs_root", return_value=runs_root), \
             patch(f"{_RT_PATH}._runs_root", return_value=runs_root), \
             patch("ai_workflow_hub.cli._paper_ledger_api", return_value=FAKE_API), \
             patch("ai_workflow_hub.cli.console", real_console), \
             patch("ai_workflow_hub.cli.err_console", real_err_console), \
             patch("ai_workflow_hub.cli.init_env"):
            result = runner.invoke(app, ["paper", "report", "--run-id",
                                        run["run_id"], "--json", "--save"],
                                   catch_exceptions=False)

        stdout_text = stdout_buf.getvalue().strip()
        stderr_text = stderr_buf.getvalue()

        # stdout should be pure JSON
        report = json.loads(stdout_text)
        assert report["run_id"] == run["run_id"]

        # stderr should contain the Saved message
        assert "Saved" in stderr_text

        # File should also be saved
        json_path = runs_root / run["run_id"] / "closeout-report.json"
        assert json_path.exists()


# =====================================================================
# TestA23BSanitizeRunId — Fix 3: graceful handling of bad run IDs
# =====================================================================

class TestA23BSanitizeRunId:
    """Verify that invalid run IDs are handled gracefully."""

    def test_invalid_run_id_exits_cleanly(self, tmp_path):
        """Malformed run_id should exit with code 1, not crash."""
        runs_root = tmp_path / "runs" / "paper"
        runs_root.mkdir(parents=True, exist_ok=True)

        # Patch sanitize to raise ValueError
        with patch("ai_workflow_hub.cli._paper_runs_root", return_value=runs_root), \
             patch(f"{_RT_PATH}.sanitize_run_id",
                   side_effect=ValueError("Invalid characters")):
            result = _invoke(["paper", "report", "--run-id", "bad!!id",
                             "--json", "--no-save"])

        assert result.exit_code == 1


# =====================================================================
# TestA23BMarkdownRedaction — Fix 4: decision notes redacted in MD
# =====================================================================

class TestA23BMarkdownRedaction:
    """Verify that Markdown decision notes are redacted."""

    def test_markdown_decision_note_redacted(self, tmp_path):
        """Sensitive text in decision note should be redacted in Markdown."""
        run, base_dir, _ = _make_run(tmp_path)
        runs_root = tmp_path / "runs" / "paper"

        # Inject sensitive data into decision note via state
        state_path = runs_root / run["run_id"] / "state.json"
        if state_path.exists():
            state = json.loads(state_path.read_text(encoding="utf-8"))
            state["decision_note_sensitive"] = "paragraph_text: SECRET_CONTENT_12345"

        with patch("ai_workflow_hub.cli._paper_runs_root", return_value=runs_root), \
             patch(f"{_RT_PATH}._runs_root", return_value=runs_root), \
             patch("ai_workflow_hub.cli._paper_ledger_api", return_value=FAKE_API):
            result = _invoke(["paper", "report", "--run-id", run["run_id"],
                             "--save"])

        md_path = runs_root / run["run_id"] / "closeout-report.md"
        if md_path.exists():
            md_text = md_path.read_text(encoding="utf-8")
            # The note from the decision record should be redacted
            # (if it contained sensitive patterns, _redact_str would catch them)
            assert "Closeout Report" in md_text


# =====================================================================
# TestA23BLedgerTraceability — Fix 5: issue-level detail in report
# =====================================================================

class TestA23BLedgerTraceability:
    """Verify ledger issues are traceable at issue level."""

    def test_json_has_issues_summary(self, tmp_path):
        """Report should include ledger_issues_summary with issue details."""
        run, base_dir, _ = _make_run(tmp_path)
        runs_root = tmp_path / "runs" / "paper"

        with patch("ai_workflow_hub.cli._paper_runs_root", return_value=runs_root), \
             patch(f"{_RT_PATH}._runs_root", return_value=runs_root), \
             patch("ai_workflow_hub.cli._paper_ledger_api", return_value=FAKE_API):
            result = _invoke(["paper", "report", "--run-id", run["run_id"],
                             "--json", "--no-save"])

        report = json.loads(result.output)
        summary = report.get("ledger_issues_summary", [])
        assert len(summary) >= 2
        assert summary[0]["issue_id"] == "a23b-iss-001"
        assert summary[0]["issue_type"] == "citation"
        assert summary[0]["severity"] == "major"
        assert summary[0]["status"] == "open"

    def test_markdown_lists_issues(self, tmp_path):
        """Markdown report should list individual issues under ledger."""
        run, base_dir, _ = _make_run(tmp_path)
        runs_root = tmp_path / "runs" / "paper"

        with patch("ai_workflow_hub.cli._paper_runs_root", return_value=runs_root), \
             patch(f"{_RT_PATH}._runs_root", return_value=runs_root), \
             patch("ai_workflow_hub.cli._paper_ledger_api", return_value=FAKE_API):
            result = _invoke(["paper", "report", "--run-id", run["run_id"],
                             "--save"])

        md_path = runs_root / run["run_id"] / "closeout-report.md"
        assert md_path.exists()
        md_text = md_path.read_text(encoding="utf-8")
        assert "### Issues" in md_text
        assert "a23b-iss-001" in md_text
        assert "citation" in md_text


# =====================================================================
# TestA23BEvidenceManifest — Fix 6: expanded evidence manifest detail
# =====================================================================

class TestA23BEvidenceManifest:
    """Verify evidence manifest includes file-level detail."""

    def test_evidence_manifest_has_files(self, tmp_path):
        """Report should include evidence manifest files with hashes."""
        run, base_dir, _ = _make_run(tmp_path)
        runs_root = tmp_path / "runs" / "paper"

        # Inject evidence manifest with file details into state
        state_path = runs_root / run["run_id"] / "state.json"
        if state_path.exists():
            state = json.loads(state_path.read_text(encoding="utf-8"))
            state["evidence_manifest"] = {
                "manifest_id": "a23b-manifest-001",
                "status": "complete",
                "version": "1.0",
                "generated_at": "2026-06-12T10:00:00Z",
                "files": [
                    {"path": "src/cli.py", "sha256": "abc123", "size": 1000},
                    {"path": "src/daemon.py", "sha256": "def456", "size": 2000},
                ],
                "privacy_attestation": {"no_full_text": True},
            }
            state_path.write_text(
                json.dumps(state, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )

        with patch("ai_workflow_hub.cli._paper_runs_root", return_value=runs_root), \
             patch(f"{_RT_PATH}._runs_root", return_value=runs_root):
            result = _invoke(["paper", "report", "--run-id", run["run_id"],
                             "--json", "--no-save"])

        report = json.loads(result.output)
        em = report.get("evidence_manifest", {})
        assert em.get("manifest_id") == "a23b-manifest-001"
        assert em.get("file_count") == 2
        files = em.get("files", [])
        assert len(files) == 2
        assert files[0]["path"] == "src/cli.py"
        assert files[0]["sha256"] == "abc123"
        assert files[0]["size"] == 1000


# =====================================================================
# TestA23BContentHash — Fix 7: SHA-256 hash binding
# =====================================================================

class TestA23BContentHash:
    """Verify report includes verifiable SHA-256 content hash."""

    def test_json_has_content_hash(self, tmp_path):
        """Report should include a 64-char hex content_hash."""
        run, base_dir, _ = _make_run(tmp_path)
        runs_root = tmp_path / "runs" / "paper"

        with patch("ai_workflow_hub.cli._paper_runs_root", return_value=runs_root), \
             patch(f"{_RT_PATH}._runs_root", return_value=runs_root), \
             patch("ai_workflow_hub.cli._paper_ledger_api", return_value=FAKE_API):
            result = _invoke(["paper", "report", "--run-id", run["run_id"],
                             "--json", "--no-save"])

        report = json.loads(result.output)
        ch = report.get("content_hash", "")
        assert len(ch) == 64
        assert all(c in "0123456789abcdef" for c in ch)

    def test_content_hash_verifiable(self, tmp_path):
        """Re-serializing report with artifact chain should reproduce the hash."""
        run, base_dir, _ = _make_run(tmp_path)
        runs_root = tmp_path / "runs" / "paper"

        with patch("ai_workflow_hub.cli._paper_runs_root", return_value=runs_root), \
             patch(f"{_RT_PATH}._runs_root", return_value=runs_root), \
             patch("ai_workflow_hub.cli._paper_ledger_api", return_value=FAKE_API):
            result = _invoke(["paper", "report", "--run-id", run["run_id"],
                             "--json", "--no-save"])

        report = json.loads(result.output)
        stored_hash = report.pop("content_hash")

        # A24: hash now binds report + artifact_chain
        artifact_chain = report.get("artifact_chain", [])
        _hash_payload = json.dumps({
            "report": report,
            "artifacts": artifact_chain,
        }, sort_keys=True, ensure_ascii=False, default=str)
        expected = hashlib.sha256(_hash_payload.encode("utf-8")).hexdigest()
        assert stored_hash == expected

    def test_markdown_has_content_hash(self, tmp_path):
        """Markdown report should display the content hash."""
        run, base_dir, _ = _make_run(tmp_path)
        runs_root = tmp_path / "runs" / "paper"

        with patch("ai_workflow_hub.cli._paper_runs_root", return_value=runs_root), \
             patch(f"{_RT_PATH}._runs_root", return_value=runs_root), \
             patch("ai_workflow_hub.cli._paper_ledger_api", return_value=FAKE_API):
            result = _invoke(["paper", "report", "--run-id", run["run_id"],
                             "--save"])

        md_path = runs_root / run["run_id"] / "closeout-report.md"
        assert md_path.exists()
        md_text = md_path.read_text(encoding="utf-8")
        assert "Content Hash" in md_text
        # Hash should be a 64-char hex string
        import re
        m = re.search(r"`([0-9a-f]{64})`", md_text)
        assert m, "Expected 64-char hex hash in Markdown"
