"""test_paper_a24_artifact_binding.py — A24 Artifact Binding Tests.

Addresses GPT concerns from A23B verdict:
1. warnings_list redacted in JSON output
2. content_hash binds underlying artifacts (artifact chain)
3. Ledger issues include provenance (source, evidence, recommendation)
4. Evidence manifest independently verifies file existence/hashes
5. Unified redaction over all report fields
6. Warning severity distinction (critical vs non-critical)
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

TASK_ID = "a24-binding"
PROJECT_ID = "a24-proj"

SYNTHETIC_ISSUES = [
    {"issue_id": "a24-iss-001", "issue_type": "citation", "severity": "major",
     "description": "Missing ref", "evidence": "S1", "human_required": True,
     "blocking": False, "recommendation": "Add ref"},
]


def _invoke(args):
    with patch("ai_workflow_hub.cli.init_env"):
        return runner.invoke(app, args, catch_exceptions=False)


def _make_run(tmp_path, **overrides):
    base_dir = str(tmp_path)
    ledger_dir = str(tmp_path / "ledger")
    Path(ledger_dir).mkdir(parents=True, exist_ok=True)
    run = create_paper_run(TASK_ID, project_id=PROJECT_ID, base_dir=base_dir,
                           initial_state={"ledger_dir": ledger_dir})
    execute_paper_run(run["run_id"], base_dir=base_dir, state_overrides={
        "writelab_mode": "mock", "expression_issues": [],
        "paragraph_issues": SYNTHETIC_ISSUES, **overrides,
    })
    resume_paper_run(run["run_id"], decision="approved",
                     reviewer_id="a24@test.com", note="A24",
                     base_dir=base_dir)
    return run, base_dir, ledger_dir


FAKE_API = {
    "summary": lambda tid, **kw: {
        "task_id": TASK_ID, "total": 2, "open": 1, "resolved": 1,
        "blocking": 0, "critical": 0, "human_required": 1,
        "severity_breakdown": {}, "type_breakdown": {},
    },
    "all_issues": lambda tid, **kw: [
        {"issue_id": "a24-iss-001", "issue_type": "citation",
         "severity": "major", "status": "open", "blocking": False,
         "source": "writelab_adapter", "evidence": "Section 1 missing",
         "evidence_pack_ref": "pack-001", "recommendation": "Add reference"},
        {"issue_id": "a24-iss-002", "issue_type": "expression",
         "severity": "minor", "status": "resolved", "blocking": False,
         "source": "gpt", "evidence": "typo found",
         "evidence_pack_ref": "pack-001", "recommendation": "Fix typo"},
    ],
    "open_issues": lambda tid, **kw: [],
    "blocking_count": lambda tid, **kw: 0,
    "critical_count": lambda tid, **kw: 0,
    "is_clear": lambda tid, **kw: True,
}


# =====================================================================
# TestA24WarningRedaction — Concern 1: warnings redacted in JSON
# =====================================================================

class TestA24WarningRedaction:
    """Verify warnings in JSON are redacted via _redact_str."""

    def test_warning_message_redacted(self, tmp_path):
        """Exception message with sensitive path should be redacted in JSON."""
        run, base_dir, _ = _make_run(tmp_path)
        runs_root = tmp_path / "runs" / "paper"

        bad_api = {
            "summary": MagicMock(side_effect=RuntimeError(
                "paragraph_text: SECRET_VALUE_12345")),
            "all_issues": MagicMock(side_effect=RuntimeError("boom")),
        }

        with patch("ai_workflow_hub.cli._paper_runs_root", return_value=runs_root), \
             patch(f"{_RT_PATH}._runs_root", return_value=runs_root), \
             patch("ai_workflow_hub.cli._paper_ledger_api", return_value=bad_api):
            result = _invoke(["paper", "report", "--run-id", run["run_id"],
                             "--json", "--no-save"])
        report = json.loads(result.output)
        warnings = report.get("warnings", [])
        assert len(warnings) >= 1
        # Sensitive value should be redacted
        msg = warnings[0].get("message", "")
        assert "SECRET_VALUE_12345" not in msg


# =====================================================================
# TestA24WarningSeverity — Concern 6: severity classification
# =====================================================================

class TestA24WarningSeverity:
    """Verify warnings have severity/subsystem/impact structure."""

    def test_critical_severity_on_ledger_failure(self, tmp_path):
        """Ledger load failure should be classified as critical."""
        run, base_dir, _ = _make_run(tmp_path)
        runs_root = tmp_path / "runs" / "paper"

        bad_api = {
            "summary": MagicMock(side_effect=RuntimeError("boom")),
            "all_issues": MagicMock(side_effect=RuntimeError("boom")),
        }

        with patch("ai_workflow_hub.cli._paper_runs_root", return_value=runs_root), \
             patch(f"{_RT_PATH}._runs_root", return_value=runs_root), \
             patch("ai_workflow_hub.cli._paper_ledger_api", return_value=bad_api):
            result = _invoke(["paper", "report", "--run-id", run["run_id"],
                             "--json", "--no-save"])
        report = json.loads(result.output)
        warnings = report.get("warnings", [])
        assert len(warnings) >= 1
        w = warnings[0]
        assert w["severity"] == "critical"
        assert w["subsystem"] == "ledger_load_failed"
        assert w["impact"] == "closeout_partial"

    def test_closeout_integrity_partial_on_critical(self, tmp_path):
        """Critical warnings should set closeout_integrity to partial."""
        run, base_dir, _ = _make_run(tmp_path)
        runs_root = tmp_path / "runs" / "paper"

        bad_api = {
            "summary": MagicMock(side_effect=RuntimeError("boom")),
            "all_issues": MagicMock(side_effect=RuntimeError("boom")),
        }

        with patch("ai_workflow_hub.cli._paper_runs_root", return_value=runs_root), \
             patch(f"{_RT_PATH}._runs_root", return_value=runs_root), \
             patch("ai_workflow_hub.cli._paper_ledger_api", return_value=bad_api):
            result = _invoke(["paper", "report", "--run-id", run["run_id"],
                             "--json", "--no-save"])
        report = json.loads(result.output)
        assert report.get("closeout_integrity") == "partial"

    def test_closeout_integrity_complete_when_ok(self, tmp_path):
        """No critical warnings should give closeout_integrity=complete."""
        run, base_dir, _ = _make_run(tmp_path)
        runs_root = tmp_path / "runs" / "paper"

        with patch("ai_workflow_hub.cli._paper_runs_root", return_value=runs_root), \
             patch(f"{_RT_PATH}._runs_root", return_value=runs_root), \
             patch("ai_workflow_hub.cli._paper_ledger_api", return_value=FAKE_API):
            result = _invoke(["paper", "report", "--run-id", run["run_id"],
                             "--json", "--no-save"])
        report = json.loads(result.output)
        assert report.get("closeout_integrity") == "complete"
        assert report.get("warnings", []) == []


# =====================================================================
# TestA24LedgerProvenance — Concern 3: issue-level provenance
# =====================================================================

class TestA24LedgerProvenance:
    """Verify ledger issues include source, evidence, recommendation."""

    def test_issues_summary_has_provenance(self, tmp_path):
        """ledger_issues_summary should include source, evidence, recommendation."""
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
        iss = summary[0]
        assert iss["source"] == "writelab_adapter"
        assert iss["evidence"] == "Section 1 missing"
        assert iss["evidence_pack_ref"] == "pack-001"
        assert iss["recommendation"] == "Add reference"

    def test_markdown_shows_source_and_rec(self, tmp_path):
        """Markdown should include src: and rec: for each issue."""
        run, base_dir, _ = _make_run(tmp_path)
        runs_root = tmp_path / "runs" / "paper"

        with patch("ai_workflow_hub.cli._paper_runs_root", return_value=runs_root), \
             patch(f"{_RT_PATH}._runs_root", return_value=runs_root), \
             patch("ai_workflow_hub.cli._paper_ledger_api", return_value=FAKE_API):
            result = _invoke(["paper", "report", "--run-id", run["run_id"],
                             "--save"])
        md_path = runs_root / run["run_id"] / "closeout-report.md"
        md = md_path.read_text(encoding="utf-8")
        assert "src:" in md
        assert "rec:" in md


# =====================================================================
# TestA24EvidenceVerification — Concern 4: independent verification
# =====================================================================

class TestA24EvidenceVerification:
    """Verify evidence files are independently checked."""

    def test_verification_all_match(self, tmp_path):
        """Real evidence files should show hash_match=True."""
        run, base_dir, _ = _make_run(tmp_path)
        runs_root = tmp_path / "runs" / "paper"

        # Create evidence files on disk
        ev_dir = runs_root / run["run_id"]
        ev_dir.mkdir(parents=True, exist_ok=True)
        (ev_dir / "test.txt").write_text("hello", encoding="utf-8")
        actual_hash = hashlib.sha256(b"hello").hexdigest()

        # Inject manifest referencing the file
        state_path = ev_dir / "state.json"
        state = json.loads(state_path.read_text(encoding="utf-8"))
        state["evidence_manifest"] = {
            "manifest_id": "m1", "status": "ok",
            "files": [{"path": "test.txt", "sha256": actual_hash, "size": 5}],
            "privacy_attestation": {},
        }
        state_path.write_text(json.dumps(state), encoding="utf-8")

        with patch("ai_workflow_hub.cli._paper_runs_root", return_value=runs_root), \
             patch(f"{_RT_PATH}._runs_root", return_value=runs_root):
            result = _invoke(["paper", "report", "--run-id", run["run_id"],
                             "--json", "--no-save"])
        report = json.loads(result.output)
        ev = report.get("evidence_manifest", {}).get("evidence_verification", [])
        assert len(ev) == 1
        assert ev[0]["exists"] is True
        assert ev[0]["hash_match"] is True
        assert ev[0]["actual_sha256"] == actual_hash

    def test_verification_missing_file(self, tmp_path):
        """Missing evidence file should produce exists=False and warning."""
        run, base_dir, _ = _make_run(tmp_path)
        runs_root = tmp_path / "runs" / "paper"

        state_path = runs_root / run["run_id"] / "state.json"
        state = json.loads(state_path.read_text(encoding="utf-8"))
        state["evidence_manifest"] = {
            "manifest_id": "m1", "status": "ok",
            "files": [{"path": "nonexistent.txt", "sha256": "abc", "size": 0}],
            "privacy_attestation": {},
        }
        state_path.write_text(json.dumps(state), encoding="utf-8")

        with patch("ai_workflow_hub.cli._paper_runs_root", return_value=runs_root), \
             patch(f"{_RT_PATH}._runs_root", return_value=runs_root):
            result = _invoke(["paper", "report", "--run-id", run["run_id"],
                             "--json", "--no-save"])
        report = json.loads(result.output)
        ev = report.get("evidence_manifest", {}).get("evidence_verification", [])
        assert len(ev) == 1
        assert ev[0]["exists"] is False
        # Should have a warning
        warnings = report.get("warnings", [])
        assert any("evidence_verification" in w.get("message", "") or
                    w.get("subsystem") == "evidence_verification"
                    for w in warnings)

    def test_verification_hash_mismatch(self, tmp_path):
        """Modified evidence file should show hash_match=False."""
        run, base_dir, _ = _make_run(tmp_path)
        runs_root = tmp_path / "runs" / "paper"

        ev_dir = runs_root / run["run_id"]
        (ev_dir / "doc.txt").write_text("modified content", encoding="utf-8")

        state_path = ev_dir / "state.json"
        state = json.loads(state_path.read_text(encoding="utf-8"))
        state["evidence_manifest"] = {
            "manifest_id": "m1", "status": "ok",
            "files": [{"path": "doc.txt", "sha256": "original_hash", "size": 16}],
            "privacy_attestation": {},
        }
        state_path.write_text(json.dumps(state), encoding="utf-8")

        with patch("ai_workflow_hub.cli._paper_runs_root", return_value=runs_root), \
             patch(f"{_RT_PATH}._runs_root", return_value=runs_root):
            result = _invoke(["paper", "report", "--run-id", run["run_id"],
                             "--json", "--no-save"])
        report = json.loads(result.output)
        ev = report.get("evidence_manifest", {}).get("evidence_verification", [])
        assert len(ev) == 1
        assert ev[0]["exists"] is True
        assert ev[0]["hash_match"] is False


# =====================================================================
# TestA24ArtifactChain — Concern 2: artifact hash binding
# =====================================================================

class TestA24ArtifactChain:
    """Verify artifact_chain hashes underlying files."""

    def test_artifact_chain_has_state(self, tmp_path):
        """artifact_chain should include state.json hash."""
        run, base_dir, _ = _make_run(tmp_path)
        runs_root = tmp_path / "runs" / "paper"

        with patch("ai_workflow_hub.cli._paper_runs_root", return_value=runs_root), \
             patch(f"{_RT_PATH}._runs_root", return_value=runs_root), \
             patch("ai_workflow_hub.cli._paper_ledger_api", return_value=FAKE_API):
            result = _invoke(["paper", "report", "--run-id", run["run_id"],
                             "--json", "--no-save"])
        report = json.loads(result.output)
        chain = report.get("artifact_chain", [])
        state_entries = [c for c in chain if c["artifact"] == "state.json"]
        assert len(state_entries) == 1
        assert len(state_entries[0]["sha256"]) == 64

    def test_hash_changes_when_state_modified(self, tmp_path):
        """Modifying state.json should change content_hash."""
        run, base_dir, _ = _make_run(tmp_path)
        runs_root = tmp_path / "runs" / "paper"

        # First report
        with patch("ai_workflow_hub.cli._paper_runs_root", return_value=runs_root), \
             patch(f"{_RT_PATH}._runs_root", return_value=runs_root), \
             patch("ai_workflow_hub.cli._paper_ledger_api", return_value=FAKE_API):
            r1 = _invoke(["paper", "report", "--run-id", run["run_id"],
                          "--json", "--no-save"])
        hash1 = json.loads(r1.output)["content_hash"]

        # Modify state.json
        state_path = runs_root / run["run_id"] / "state.json"
        state = json.loads(state_path.read_text(encoding="utf-8"))
        state["extra_field"] = "tampered"
        state_path.write_text(json.dumps(state), encoding="utf-8")

        # Second report
        with patch("ai_workflow_hub.cli._paper_runs_root", return_value=runs_root), \
             patch(f"{_RT_PATH}._runs_root", return_value=runs_root), \
             patch("ai_workflow_hub.cli._paper_ledger_api", return_value=FAKE_API):
            r2 = _invoke(["paper", "report", "--run-id", run["run_id"],
                          "--json", "--no-save"])
        hash2 = json.loads(r2.output)["content_hash"]
        assert hash1 != hash2

    def test_hash_stable_without_changes(self, tmp_path):
        """Two reports without changes should have identical hashes."""
        run, base_dir, _ = _make_run(tmp_path)
        runs_root = tmp_path / "runs" / "paper"

        with patch("ai_workflow_hub.cli._paper_runs_root", return_value=runs_root), \
             patch(f"{_RT_PATH}._runs_root", return_value=runs_root), \
             patch("ai_workflow_hub.cli._paper_ledger_api", return_value=FAKE_API):
            r1 = _invoke(["paper", "report", "--run-id", run["run_id"],
                          "--json", "--no-save"])
            r2 = _invoke(["paper", "report", "--run-id", run["run_id"],
                          "--json", "--no-save"])
        h1 = json.loads(r1.output)["content_hash"]
        h2 = json.loads(r2.output)["content_hash"]
        assert h1 == h2


# =====================================================================
# TestA24UnifiedRedaction — Concern 5: all fields redacted
# =====================================================================

class TestA24UnifiedRedaction:
    """Verify all free-text fields go through redaction."""

    def test_node_names_redacted(self, tmp_path):
        """Executed node names should not leak sensitive data."""
        run, base_dir, _ = _make_run(tmp_path)
        runs_root = tmp_path / "runs" / "paper"

        # Inject sensitive node name
        state_path = runs_root / run["run_id"] / "state.json"
        state = json.loads(state_path.read_text(encoding="utf-8"))
        state["executed_nodes"] = [
            "diagnosis", "acceptance_gate",
            "paragraph_text: SECRET_NODE_DATA",
        ]
        state_path.write_text(json.dumps(state), encoding="utf-8")

        with patch("ai_workflow_hub.cli._paper_runs_root", return_value=runs_root), \
             patch(f"{_RT_PATH}._runs_root", return_value=runs_root):
            result = _invoke(["paper", "report", "--run-id", run["run_id"],
                             "--json", "--no-save"])
        report = json.loads(result.output)
        nodes = report.get("executed_nodes", [])
        for n in nodes:
            assert "SECRET_NODE_DATA" not in str(n)


# =====================================================================
# TestA24MarkdownSeverity — Markdown warning severity grouping
# =====================================================================

class TestA24MarkdownSeverity:
    """Verify Markdown shows warning severity groups."""

    def test_markdown_critical_warnings_section(self, tmp_path):
        """Markdown should have Critical warnings section when critical exists."""
        run, base_dir, _ = _make_run(tmp_path)
        runs_root = tmp_path / "runs" / "paper"

        bad_api = {
            "summary": MagicMock(side_effect=RuntimeError("boom")),
            "all_issues": MagicMock(side_effect=RuntimeError("boom")),
        }

        with patch("ai_workflow_hub.cli._paper_runs_root", return_value=runs_root), \
             patch(f"{_RT_PATH}._runs_root", return_value=runs_root), \
             patch("ai_workflow_hub.cli._paper_ledger_api", return_value=bad_api):
            _invoke(["paper", "report", "--run-id", run["run_id"], "--save"])

        md_path = runs_root / run["run_id"] / "closeout-report.md"
        md = md_path.read_text(encoding="utf-8")
        assert "Warnings (Critical)" in md
        assert "Closeout Integrity" in md or "closeout_partial" in md.lower() or "partial" in md.lower()

    def test_markdown_shows_artifact_chain_count(self, tmp_path):
        """Markdown should display artifact chain count."""
        run, base_dir, _ = _make_run(tmp_path)
        runs_root = tmp_path / "runs" / "paper"

        with patch("ai_workflow_hub.cli._paper_runs_root", return_value=runs_root), \
             patch(f"{_RT_PATH}._runs_root", return_value=runs_root), \
             patch("ai_workflow_hub.cli._paper_ledger_api", return_value=FAKE_API):
            _invoke(["paper", "report", "--run-id", run["run_id"], "--save"])

        md_path = runs_root / run["run_id"] / "closeout-report.md"
        md = md_path.read_text(encoding="utf-8")
        assert "Artifact Chain" in md
        assert "artifact(s) hashed" in md
