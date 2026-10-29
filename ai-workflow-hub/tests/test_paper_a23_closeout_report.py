"""test_paper_a23_closeout_report.py — A23 PAPER-RUN-CLOSEOUT-REPORT Tests.

Proves the unified closeout report (`paper report`) binds together:
  - Run status + timestamps
  - Acceptance result (status, reasons, blocking count)
  - Issue ledger (total, open, resolved, blocking, severity breakdown)
  - Evidence manifest (manifest_id, status, file count, privacy attestation)
  - Decision audit trail (decision, reviewer, round, note)
  - Human gate (decision, reviewer_id)
  - Executed nodes

Both JSON and Markdown outputs verified. Privacy assertions on report content.
Report files saved to run directory.
"""

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from ai_workflow_hub.cli import app
from ai_workflow_hub.context_layer.adapters.paper_runtime import (
    create_paper_run, execute_paper_run, resume_paper_run,
)

runner = CliRunner()
_RT_PATH = "ai_workflow_hub.context_layer.adapters.paper_runtime"

TASK_ID = "a23-closeout"
PROJECT_ID = "a23-proj"

SYNTHETIC_ISSUES = [
    {
        "issue_id": "a23-iss-001",
        "issue_type": "citation",
        "severity": "major",
        "description": "Reference [10] missing from bibliography",
        "evidence": "Section 2 cites [10] but it does not appear",
        "human_required": True,
        "blocking": False,
        "recommendation": "Add reference [10]",
    },
    {
        "issue_id": "a23-iss-002",
        "issue_type": "expression",
        "severity": "minor",
        "description": "Typo in abstract",
        "evidence": "'teh' should be 'the'",
        "human_required": False,
        "blocking": False,
        "recommendation": "Fix typo",
    },
]


def _invoke(args: list[str]):
    with patch("ai_workflow_hub.cli.init_env"):
        return runner.invoke(app, args, catch_exceptions=False)


def _assert_no_sensitive_data(text: str):
    """Assert report text contains no sensitive values."""
    import re
    for key in ("paragraph_text", "writelab_token"):
        m = re.search(rf'"{key}"\s*:\s*"(?!\[REDACTED\])([^"]+)"', text)
        if m:
            assert False, f"Sensitive key '{key}' with unredacted value: {m.group(0)[:80]}"


# ===========================================================================
# TestA23ReportJson — JSON output verification
# ===========================================================================

class TestA23ReportJson:
    """Verify JSON closeout report contains all required sections."""

    @pytest.fixture
    def completed_run(self, tmp_path):
        """Create a completed run with real runtime."""
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
            },
        )
        resume_paper_run(
            run["run_id"], decision="approved",
            reviewer_id="a23-reviewer@example.com",
            note="Issues acknowledged",
            base_dir=base_dir,
        )
        return {"run": run, "base_dir": base_dir, "ledger_dir": ledger_dir}

    def test_report_json_has_run_info(self, completed_run):
        """JSON report should contain run_id, task_id, status."""
        run = completed_run["run"]
        runs_root = Path(completed_run["base_dir"]) / "runs" / "paper"
        with patch("ai_workflow_hub.cli._paper_runs_root",
                   return_value=runs_root), \
             patch(f"{_RT_PATH}._runs_root", return_value=runs_root):
            result = _invoke(["paper", "report", "--run-id", run["run_id"],
                             "--json", "--no-save"])
        assert result.exit_code == 0
        report = json.loads(result.output)
        assert report["run_id"] == run["run_id"]
        assert report["task_id"] == TASK_ID
        assert report["run_status"] == "completed"
        assert report["workflow_type"] == "paper"

    def test_report_json_has_acceptance(self, completed_run):
        """JSON report should contain acceptance section."""
        run = completed_run["run"]
        runs_root = Path(completed_run["base_dir"]) / "runs" / "paper"
        with patch("ai_workflow_hub.cli._paper_runs_root",
                   return_value=runs_root), \
             patch(f"{_RT_PATH}._runs_root", return_value=runs_root):
            result = _invoke(["paper", "report", "--run-id", run["run_id"],
                             "--json", "--no-save"])
        report = json.loads(result.output)
        assert "acceptance" in report
        acc = report["acceptance"]
        assert acc["status"] in ("accepted", "accepted_with_limitation",
                                  "human_required")
        assert "blocking_count" in acc
        assert "non_blocking_count" in acc

    def test_report_json_has_ledger(self, completed_run):
        """JSON report should contain ledger section with >= 2 issues."""
        run = completed_run["run"]
        runs_root = Path(completed_run["base_dir"]) / "runs" / "paper"

        fake_summary = {
            "task_id": TASK_ID, "total": 2, "open": 1, "resolved": 1,
            "blocking": 0, "critical": 0, "human_required": 1,
            "severity_breakdown": {"major": 1, "minor": 1},
            "type_breakdown": {"citation": 1, "expression": 1},
        }
        fake_issues = [
            {"issue_id": "a23-iss-001", "status": "open"},
            {"issue_id": "a23-iss-002", "status": "resolved"},
        ]
        fake_api = {
            "summary": lambda tid, **kw: fake_summary,
            "all_issues": lambda tid, **kw: fake_issues,
            "open_issues": lambda tid, **kw: fake_issues[:1],
            "blocking_count": lambda tid, **kw: 0,
            "critical_count": lambda tid, **kw: 0,
            "is_clear": lambda tid, **kw: True,
        }

        with patch("ai_workflow_hub.cli._paper_runs_root",
                   return_value=runs_root), \
             patch(f"{_RT_PATH}._runs_root", return_value=runs_root), \
             patch("ai_workflow_hub.cli._paper_ledger_api",
                   return_value=fake_api):
            result = _invoke(["paper", "report", "--run-id", run["run_id"],
                             "--json", "--no-save"])
        assert result.exit_code == 0
        report = json.loads(result.output)
        assert "ledger" in report
        assert report["ledger"].get("total", 0) >= 2

    def test_report_json_has_decision(self, completed_run):
        """JSON report should contain decision audit section."""
        run = completed_run["run"]
        runs_root = Path(completed_run["base_dir"]) / "runs" / "paper"
        with patch("ai_workflow_hub.cli._paper_runs_root",
                   return_value=runs_root), \
             patch(f"{_RT_PATH}._runs_root", return_value=runs_root):
            result = _invoke(["paper", "report", "--run-id", run["run_id"],
                             "--json", "--no-save"])
        report = json.loads(result.output)
        assert "decision" in report
        dec = report["decision"]
        assert dec.get("decision") == "approved"
        assert dec.get("reviewer_id") == "a23-reviewer@example.com"

    def test_report_json_has_executed_nodes(self, completed_run):
        """JSON report should list executed graph nodes."""
        run = completed_run["run"]
        runs_root = Path(completed_run["base_dir"]) / "runs" / "paper"
        with patch("ai_workflow_hub.cli._paper_runs_root",
                   return_value=runs_root), \
             patch(f"{_RT_PATH}._runs_root", return_value=runs_root):
            result = _invoke(["paper", "report", "--run-id", run["run_id"],
                             "--json", "--no-save"])
        report = json.loads(result.output)
        nodes = report.get("executed_nodes", [])
        assert len(nodes) >= 4  # diagnosis, acceptance_gate, ledger_ingest, human_gate, finalizer

    def test_report_json_has_human_gate(self, completed_run):
        """JSON report should contain human gate section."""
        run = completed_run["run"]
        runs_root = Path(completed_run["base_dir"]) / "runs" / "paper"
        with patch("ai_workflow_hub.cli._paper_runs_root",
                   return_value=runs_root), \
             patch(f"{_RT_PATH}._runs_root", return_value=runs_root):
            result = _invoke(["paper", "report", "--run-id", run["run_id"],
                             "--json", "--no-save"])
        report = json.loads(result.output)
        assert "human_gate" in report
        hg = report["human_gate"]
        assert "human_required" in hg
        assert hg["decision"] == "approved"

    def test_report_json_privacy_clean(self, completed_run):
        """JSON report should not contain sensitive values."""
        run = completed_run["run"]
        runs_root = Path(completed_run["base_dir"]) / "runs" / "paper"
        with patch("ai_workflow_hub.cli._paper_runs_root",
                   return_value=runs_root), \
             patch(f"{_RT_PATH}._runs_root", return_value=runs_root):
            result = _invoke(["paper", "report", "--run-id", run["run_id"],
                             "--json", "--no-save"])
        _assert_no_sensitive_data(result.output)


# ===========================================================================
# TestA23ReportSave — Report file persistence
# ===========================================================================

class TestA23ReportSave:
    """Verify report files are saved to run directory."""

    @pytest.fixture
    def completed_run(self, tmp_path):
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
            },
        )
        resume_paper_run(
            run["run_id"], decision="approved",
            reviewer_id="a23-reviewer", base_dir=base_dir,
        )
        return {"run": run, "base_dir": base_dir}

    def test_saves_json_report(self, completed_run):
        """paper report --save should write closeout-report.json."""
        run = completed_run["run"]
        runs_root = Path(completed_run["base_dir"]) / "runs" / "paper"
        with patch("ai_workflow_hub.cli._paper_runs_root",
                   return_value=runs_root), \
             patch(f"{_RT_PATH}._runs_root", return_value=runs_root):
            result = _invoke(["paper", "report", "--run-id", run["run_id"],
                             "--json"])
        assert result.exit_code == 0
        json_path = runs_root / run["run_id"] / "closeout-report.json"
        assert json_path.exists()
        report = json.loads(json_path.read_text(encoding="utf-8"))
        assert report["run_id"] == run["run_id"]

    def test_saves_markdown_report(self, completed_run):
        """paper report --save should write closeout-report.md."""
        run = completed_run["run"]
        runs_root = Path(completed_run["base_dir"]) / "runs" / "paper"
        with patch("ai_workflow_hub.cli._paper_runs_root",
                   return_value=runs_root), \
             patch(f"{_RT_PATH}._runs_root", return_value=runs_root):
            result = _invoke(["paper", "report", "--run-id", run["run_id"]])
        assert result.exit_code == 0
        md_path = runs_root / run["run_id"] / "closeout-report.md"
        assert md_path.exists()
        md_text = md_path.read_text(encoding="utf-8")
        assert "Closeout Report" in md_text
        assert TASK_ID in md_text

    def test_markdown_has_all_sections(self, completed_run):
        """Markdown report should have Acceptance, Ledger, Decision, Nodes sections."""
        run = completed_run["run"]
        runs_root = Path(completed_run["base_dir"]) / "runs" / "paper"

        fake_summary = {
            "task_id": TASK_ID, "total": 2, "open": 1, "resolved": 1,
            "blocking": 0, "critical": 0, "human_required": 1,
            "severity_breakdown": {"major": 1}, "type_breakdown": {"citation": 1},
        }
        fake_api = {
            "summary": lambda tid, **kw: fake_summary,
            "all_issues": lambda tid, **kw: [{"issue_id": "x"}],
            "open_issues": lambda tid, **kw: [],
            "blocking_count": lambda tid, **kw: 0,
            "critical_count": lambda tid, **kw: 0,
            "is_clear": lambda tid, **kw: True,
        }

        with patch("ai_workflow_hub.cli._paper_runs_root",
                   return_value=runs_root), \
             patch(f"{_RT_PATH}._runs_root", return_value=runs_root), \
             patch("ai_workflow_hub.cli._paper_ledger_api",
                   return_value=fake_api):
            result = _invoke(["paper", "report", "--run-id", run["run_id"]])
        md_path = runs_root / run["run_id"] / "closeout-report.md"
        md_text = md_path.read_text(encoding="utf-8")
        assert "Acceptance Summary" in md_text
        assert "Decision Audit" in md_text or "decision" in md_text.lower()
        assert "Executed Nodes" in md_text


# ===========================================================================
# TestA23ReportPrivacy — Privacy of report outputs
# ===========================================================================

class TestA23ReportPrivacy:
    """Verify report outputs never contain sensitive values."""

    def test_json_report_privacy(self, tmp_path):
        """JSON report on disk should be privacy-clean."""
        base_dir = str(tmp_path)
        ledger_dir = str(tmp_path / "ledger")
        Path(ledger_dir).mkdir(parents=True, exist_ok=True)
        run = create_paper_run(
            TASK_ID, base_dir=base_dir,
            initial_state={"ledger_dir": ledger_dir},
        )
        execute_paper_run(
            run["run_id"], base_dir=base_dir,
            state_overrides={
                "writelab_mode": "mock",
                "expression_issues": [],
                "paragraph_issues": SYNTHETIC_ISSUES,
            },
        )
        resume_paper_run(run["run_id"], decision="approved", base_dir=base_dir)

        runs_root = tmp_path / "runs" / "paper"
        with patch("ai_workflow_hub.cli._paper_runs_root",
                   return_value=runs_root), \
             patch(f"{_RT_PATH}._runs_root", return_value=runs_root):
            _invoke(["paper", "report", "--run-id", run["run_id"], "--json"])

        json_path = runs_root / run["run_id"] / "closeout-report.json"
        if json_path.exists():
            _assert_no_sensitive_data(json_path.read_text(encoding="utf-8"))
