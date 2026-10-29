"""test_paper_cli_a18.py — A18 Paper CLI E2E Extension Tests.

Tests the A18 additions to the paper CLI:
  - paper go (create-and-run combined entry)
  - paper ledger (issue ledger display)
  - paper evidence (evidence manifest display)
  - paper validate (acceptance result validation)
  - --json output mode on run/status/go/ledger/evidence/validate
  - --zip option on run/go

All tests mock paper_runtime / ledger / gate to avoid real invocations.
"""

import json
import os
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
from typer.testing import CliRunner

from ai_workflow_hub.cli import app

runner = CliRunner()

_RT_PATH = "ai_workflow_hub.context_layer.adapters.paper_runtime"
_LEDGER_PATH = "ai_workflow_hub.context_layer.adapters.paper_issue_ledger"
_GATE_PATH = "ai_workflow_hub.context_layer.adapters.paper_acceptance_gate"


def _invoke(args: list[str]):
    with patch("ai_workflow_hub.cli.init_env"):
        return runner.invoke(app, args, catch_exceptions=False)


def _make_run_dir(base: Path, run_id: str, state: dict) -> Path:
    rd = base / run_id
    rd.mkdir(parents=True, exist_ok=True)
    (rd / "state.json").write_text(
        json.dumps(state, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )
    return rd


# ===========================================================================
# TestPaperGo — A18 combined create-and-run
# ===========================================================================

class TestPaperGo:
    """Test `paper go` command."""

    def test_go_completed_success(self):
        mock_create = {"run_id": "paper-go-01", "run_dir": "/tmp/paper-go-01",
                       "task_id": "T-1", "project_id": "", "status": "created"}
        mock_execute = {
            "run_id": "paper-go-01", "status": "completed",
            "state": {"task_id": "T-1", "executed_nodes": ["parser", "finalizer"]},
            "warnings": [],
        }
        with patch(f"{_RT_PATH}.create_paper_run", return_value=mock_create), \
             patch(f"{_RT_PATH}.execute_paper_run", return_value=mock_execute), \
             patch(f"{_RT_PATH}.sanitize_run_id", return_value="paper-go-01"), \
             patch(f"{_RT_PATH}.redact_state", side_effect=lambda s: dict(s)):
            result = _invoke(["paper", "go", "--task", "T-1"])
        assert result.exit_code == 0
        assert "paper-go-01" in result.output
        assert "completed" in result.output

    def test_go_json_output(self):
        mock_create = {"run_id": "paper-go-j", "run_dir": "/tmp/x", "task_id": "T-2",
                       "project_id": "", "status": "created"}
        mock_execute = {
            "run_id": "paper-go-j", "status": "completed",
            "state": {"task_id": "T-2", "executed_nodes": [], "acceptance_status": "accepted",
                      "blocking_count": 0},
            "warnings": [],
        }
        with patch(f"{_RT_PATH}.create_paper_run", return_value=mock_create), \
             patch(f"{_RT_PATH}.execute_paper_run", return_value=mock_execute), \
             patch(f"{_RT_PATH}.sanitize_run_id", return_value="paper-go-j"), \
             patch(f"{_RT_PATH}.redact_state", side_effect=lambda s: dict(s)):
            result = _invoke(["paper", "go", "--task", "T-2", "--json"])
        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert parsed["status"] == "completed"
        assert parsed["run_id"] == "paper-go-j"

    def test_go_create_error(self):
        with patch(f"{_RT_PATH}.create_paper_run", side_effect=ValueError("bad task")):
            result = _invoke(["paper", "go", "--task", ""])
        assert result.exit_code == 1
        assert "Create failed" in result.output

    def test_go_execute_error(self):
        mock_create = {"run_id": "paper-go-err", "run_dir": "/tmp/x", "task_id": "T",
                       "project_id": "", "status": "created"}
        with patch(f"{_RT_PATH}.create_paper_run", return_value=mock_create), \
             patch(f"{_RT_PATH}.execute_paper_run",
                   side_effect=FileNotFoundError("run not found")), \
             patch(f"{_RT_PATH}.sanitize_run_id", return_value="paper-go-err"):
            result = _invoke(["paper", "go", "--task", "T"])
        assert result.exit_code == 1
        assert "Execute failed" in result.output

    def test_go_human_required(self):
        mock_create = {"run_id": "paper-go-hr", "run_dir": "/tmp/x", "task_id": "T",
                       "project_id": "", "status": "created"}
        mock_execute = {
            "run_id": "paper-go-hr", "status": "human_required",
            "state": {"task_id": "T", "executed_nodes": ["parser", "human_gate"]},
            "gate_artifact": "/tmp/x/paper-human-gate.md",
            "warnings": [],
        }
        with patch(f"{_RT_PATH}.create_paper_run", return_value=mock_create), \
             patch(f"{_RT_PATH}.execute_paper_run", return_value=mock_execute), \
             patch(f"{_RT_PATH}.sanitize_run_id", return_value="paper-go-hr"), \
             patch(f"{_RT_PATH}.redact_state", side_effect=lambda s: dict(s)):
            result = _invoke(["paper", "go", "--task", "T"])
        assert result.exit_code == 0
        assert "Human review required" in result.output

    def test_go_zip_not_found(self, tmp_path):
        mock_create = {"run_id": "paper-go-z", "run_dir": str(tmp_path), "task_id": "T",
                       "project_id": "", "status": "created"}
        with patch(f"{_RT_PATH}.create_paper_run", return_value=mock_create):
            result = _invoke(["paper", "go", "--task", "T",
                              "--zip", "/nonexistent/file.zip"])
        assert result.exit_code == 1
        assert "ZIP not found" in result.output


# ===========================================================================
# TestPaperLedger — A18
# ===========================================================================

class TestPaperLedger:
    """Test `paper ledger` command."""

    def test_ledger_with_issues(self, tmp_path):
        state = {"task_id": "TASK-L1", "status": "completed"}
        _make_run_dir(tmp_path, "paper-l1", state)
        mock_summary = {"task_id": "TASK-L1", "total": 3, "open": 2, "resolved": 1,
                        "blocking": 1, "critical": 0, "human_required": False,
                        "severity_breakdown": {}, "type_breakdown": {}}
        mock_issues = [
            {"issue_id": "wl-001", "issue_type": "citation", "severity": "major",
             "status": "open", "description": "Missing ref"},
        ]
        with patch("ai_workflow_hub.cli._paper_runs_root", return_value=tmp_path), \
             patch(f"{_RT_PATH}.sanitize_run_id", return_value="paper-l1"), \
             patch(f"{_LEDGER_PATH}.ledger_summary", return_value=mock_summary), \
             patch(f"{_LEDGER_PATH}.get_open_issues", return_value=mock_issues), \
             patch(f"{_LEDGER_PATH}.is_clear", return_value=False):
            result = _invoke(["paper", "ledger", "--run-id", "paper-l1"])
        assert result.exit_code == 0
        assert "TASK-L1" in result.output
        assert "NOT CLEAR" in result.output

    def test_ledger_json_output(self, tmp_path):
        state = {"task_id": "TASK-L2", "status": "completed"}
        _make_run_dir(tmp_path, "paper-l2", state)
        mock_summary = {"task_id": "TASK-L2", "total": 0, "open": 0, "resolved": 0,
                        "blocking": 0, "critical": 0}
        with patch("ai_workflow_hub.cli._paper_runs_root", return_value=tmp_path), \
             patch(f"{_RT_PATH}.sanitize_run_id", return_value="paper-l2"), \
             patch(f"{_LEDGER_PATH}.ledger_summary", return_value=mock_summary), \
             patch(f"{_LEDGER_PATH}.get_open_issues", return_value=[]), \
             patch(f"{_LEDGER_PATH}.is_clear", return_value=True):
            result = _invoke(["paper", "ledger", "--run-id", "paper-l2", "--json"])
        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert parsed["task_id"] == "TASK-L2"
        assert parsed["summary"]["total"] == 0

    def test_ledger_run_not_found(self, tmp_path):
        with patch("ai_workflow_hub.cli._paper_runs_root", return_value=tmp_path), \
             patch(f"{_RT_PATH}.sanitize_run_id", return_value="paper-missing"):
            result = _invoke(["paper", "ledger", "--run-id", "paper-missing"])
        assert result.exit_code == 1
        assert "not found" in result.output

    def test_ledger_clear(self, tmp_path):
        state = {"task_id": "TASK-CLR", "status": "completed"}
        _make_run_dir(tmp_path, "paper-clr", state)
        mock_summary = {"task_id": "TASK-CLR", "total": 1, "open": 0, "resolved": 1,
                        "blocking": 0, "critical": 0}
        with patch("ai_workflow_hub.cli._paper_runs_root", return_value=tmp_path), \
             patch(f"{_RT_PATH}.sanitize_run_id", return_value="paper-clr"), \
             patch(f"{_LEDGER_PATH}.ledger_summary", return_value=mock_summary), \
             patch(f"{_LEDGER_PATH}.get_open_issues", return_value=[]), \
             patch(f"{_LEDGER_PATH}.is_clear", return_value=True):
            result = _invoke(["paper", "ledger", "--run-id", "paper-clr"])
        assert result.exit_code == 0
        assert "CLEAR" in result.output


# ===========================================================================
# TestPaperEvidence — A18
# ===========================================================================

class TestPaperEvidence:
    """Test `paper evidence` command."""

    def test_evidence_with_manifest(self, tmp_path):
        state = {
            "task_id": "TASK-E1", "status": "completed",
            "evidence_manifest": {
                "reviewer": "writelab_adapter",
                "manifest_status": "complete",
                "evidence_pack_ref": "pack-001",
                "privacy_attestation": {"privacy_ok": True},
                "entries": [
                    {"source": "expression_01", "evidence_type": "expression",
                     "status": "complete", "issue_count": 2},
                ],
            },
        }
        _make_run_dir(tmp_path, "paper-e1", state)
        with patch("ai_workflow_hub.cli._paper_runs_root", return_value=tmp_path), \
             patch(f"{_RT_PATH}.sanitize_run_id", return_value="paper-e1"):
            result = _invoke(["paper", "evidence", "--run-id", "paper-e1"])
        assert result.exit_code == 0
        assert "writelab_adapter" in result.output
        assert "complete" in result.output

    def test_evidence_json(self, tmp_path):
        state = {
            "task_id": "TASK-E2", "status": "completed",
            "evidence_manifest": {"reviewer": "gpt", "manifest_status": "partial"},
        }
        _make_run_dir(tmp_path, "paper-e2", state)
        with patch("ai_workflow_hub.cli._paper_runs_root", return_value=tmp_path), \
             patch(f"{_RT_PATH}.sanitize_run_id", return_value="paper-e2"):
            result = _invoke(["paper", "evidence", "--run-id", "paper-e2", "--json"])
        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert parsed["reviewer"] == "gpt"

    def test_evidence_empty(self, tmp_path):
        state = {"task_id": "TASK-E3", "status": "created"}
        _make_run_dir(tmp_path, "paper-e3", state)
        with patch("ai_workflow_hub.cli._paper_runs_root", return_value=tmp_path), \
             patch(f"{_RT_PATH}.sanitize_run_id", return_value="paper-e3"):
            result = _invoke(["paper", "evidence", "--run-id", "paper-e3"])
        assert result.exit_code == 0
        assert "No evidence manifest" in result.output

    def test_evidence_not_found(self, tmp_path):
        with patch("ai_workflow_hub.cli._paper_runs_root", return_value=tmp_path), \
             patch(f"{_RT_PATH}.sanitize_run_id", return_value="paper-nope"):
            result = _invoke(["paper", "evidence", "--run-id", "paper-nope"])
        assert result.exit_code == 1
        assert "not found" in result.output


# ===========================================================================
# TestPaperValidate — A18
# ===========================================================================

class TestPaperValidate:
    """Test `paper validate` command."""

    def test_validate_pass(self, tmp_path):
        state = {
            "task_id": "TASK-V1", "status": "completed",
            "acceptance_result": {
                "status": "accepted",
                "reasons": ["No blocking issues"],
                "blocking_issues": [],
                "non_blocking_issues": [],
                "reviewer": "writelab_adapter",
            },
        }
        _make_run_dir(tmp_path, "paper-v1", state)
        with patch("ai_workflow_hub.cli._paper_runs_root", return_value=tmp_path), \
             patch(f"{_RT_PATH}.sanitize_run_id", return_value="paper-v1"), \
             patch(f"{_GATE_PATH}.validate_acceptance_result", return_value=[]):
            result = _invoke(["paper", "validate", "--run-id", "paper-v1"])
        assert result.exit_code == 0
        assert "PASSED" in result.output

    def test_validate_fail(self, tmp_path):
        state = {
            "task_id": "TASK-V2", "status": "completed",
            "acceptance_result": {"status": "bad", "reasons": []},
        }
        _make_run_dir(tmp_path, "paper-v2", state)
        with patch("ai_workflow_hub.cli._paper_runs_root", return_value=tmp_path), \
             patch(f"{_RT_PATH}.sanitize_run_id", return_value="paper-v2"), \
             patch(f"{_GATE_PATH}.validate_acceptance_result",
                   return_value=["missing field: blocking_issues", "invalid status: bad"]):
            result = _invoke(["paper", "validate", "--run-id", "paper-v2"])
        assert result.exit_code == 1
        assert "FAILED" in result.output
        assert "missing field" in result.output

    def test_validate_json(self, tmp_path):
        state = {
            "task_id": "TASK-V3", "status": "completed",
            "acceptance_result": {"status": "accepted", "reasons": ["ok"]},
        }
        _make_run_dir(tmp_path, "paper-v3", state)
        with patch("ai_workflow_hub.cli._paper_runs_root", return_value=tmp_path), \
             patch(f"{_RT_PATH}.sanitize_run_id", return_value="paper-v3"), \
             patch(f"{_GATE_PATH}.validate_acceptance_result", return_value=[]):
            result = _invoke(["paper", "validate", "--run-id", "paper-v3", "--json"])
        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert parsed["valid"] is True
        assert parsed["validation_errors"] == []

    def test_validate_no_result(self, tmp_path):
        state = {"task_id": "TASK-V4", "status": "created"}
        _make_run_dir(tmp_path, "paper-v4", state)
        with patch("ai_workflow_hub.cli._paper_runs_root", return_value=tmp_path), \
             patch(f"{_RT_PATH}.sanitize_run_id", return_value="paper-v4"):
            result = _invoke(["paper", "validate", "--run-id", "paper-v4"])
        assert result.exit_code == 0
        assert "No acceptance_result" in result.output

    def test_validate_not_found(self, tmp_path):
        with patch("ai_workflow_hub.cli._paper_runs_root", return_value=tmp_path), \
             patch(f"{_RT_PATH}.sanitize_run_id", return_value="paper-nf"):
            result = _invoke(["paper", "validate", "--run-id", "paper-nf"])
        assert result.exit_code == 1
        assert "not found" in result.output


# ===========================================================================
# TestA18JsonOutput — --json on existing commands
# ===========================================================================

class TestA18JsonOutput:
    """Test --json output mode on existing commands."""

    def test_run_json_output(self):
        mock_result = {
            "run_id": "paper-json-01", "status": "completed",
            "state": {"task_id": "T-J", "executed_nodes": ["parser"],
                      "acceptance_status": "accepted", "blocking_count": 0},
            "warnings": [],
        }
        with patch(f"{_RT_PATH}.execute_paper_run", return_value=mock_result), \
             patch(f"{_RT_PATH}.sanitize_run_id", return_value="paper-json-01"), \
             patch(f"{_RT_PATH}.redact_state", side_effect=lambda s: dict(s)):
            result = _invoke(["paper", "run", "--run-id", "paper-json-01", "--json"])
        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert parsed["status"] == "completed"
        assert parsed["run_id"] == "paper-json-01"

    def test_status_json_output(self):
        mock_info = {
            "run_id": "paper-json-s", "task_id": "T-JS", "project_id": "",
            "status": "completed", "acceptance_status": "accepted",
            "blocking_count": 0, "human_required": False,
            "human_gate_decision": "", "reviewer_id": "", "decision_round": 0,
            "executed_nodes": [], "error_message": "",
            "created_at": "2026-06-12T10:00:00", "updated_at": "2026-06-12T10:01:00",
        }
        with patch(f"{_RT_PATH}.get_paper_run_status", return_value=mock_info), \
             patch(f"{_RT_PATH}.sanitize_run_id", return_value="paper-json-s"), \
             patch(f"{_RT_PATH}.redact_state", side_effect=lambda s: dict(s)):
            result = _invoke(["paper", "status", "--run-id", "paper-json-s", "--json"])
        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert parsed["status"] == "completed"

    def test_run_json_redacts_warnings(self):
        mock_result = {
            "run_id": "paper-json-w", "status": "completed",
            "state": {"task_id": "T", "executed_nodes": [],
                      "acceptance_status": "", "blocking_count": 0},
            "warnings": ["paragraph_text: secret leaked content"],
        }
        with patch(f"{_RT_PATH}.execute_paper_run", return_value=mock_result), \
             patch(f"{_RT_PATH}.sanitize_run_id", return_value="paper-json-w"), \
             patch(f"{_RT_PATH}.redact_state", side_effect=lambda s: dict(s)):
            result = _invoke(["paper", "run", "--run-id", "paper-json-w", "--json"])
        assert result.exit_code == 0
        assert "secret leaked content" not in result.output
        assert "[REDACTED]" in result.output


# ===========================================================================
# TestA18CommandRegistration — verify new commands are listed
# ===========================================================================

class TestA18CommandRegistration:
    """Verify A18 commands are registered."""

    def test_go_listed(self):
        result = runner.invoke(app, ["paper", "--help"])
        assert "go" in result.output

    def test_ledger_listed(self):
        result = runner.invoke(app, ["paper", "--help"])
        assert "ledger" in result.output

    def test_evidence_listed(self):
        result = runner.invoke(app, ["paper", "--help"])
        assert "evidence" in result.output

    def test_validate_listed(self):
        result = runner.invoke(app, ["paper", "--help"])
        assert "validate" in result.output

    def test_total_nine_commands(self):
        """Should have 9 subcommands: 5 from A17 + 4 from A18."""
        result = runner.invoke(app, ["paper", "--help"])
        for cmd in ("create", "run", "resume", "status", "list",
                     "go", "ledger", "evidence", "validate"):
            assert cmd in result.output
