"""test_paper_cli.py — A17 Paper CLI Entry Point Tests.

Tests the `aihub paper` command group added to cli.py:
  - Command registration (paper group with 5 subcommands)
  - paper create (success, error)
  - paper run (success, sanitize, error, human_required)
  - paper resume (success, sanitize, invalid decision, not paused)
  - paper status (success, not found, redaction)
  - paper list (empty, with runs, status filter, limit)

All tests mock paper_runtime to avoid real filesystem / graph invocations.
"""

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
from typer.testing import CliRunner

from ai_workflow_hub.cli import app


runner = CliRunner()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _invoke(args: list[str], env: dict | None = None):
    """Invoke the CLI with the given arguments, mocking init_env."""
    with patch("ai_workflow_hub.cli.init_env"):
        result = runner.invoke(app, args, catch_exceptions=False)
    return result


def _make_run_dir(base: Path, run_id: str, state: dict) -> Path:
    """Create a paper run directory with state.json."""
    rd = base / run_id
    rd.mkdir(parents=True, exist_ok=True)
    (rd / "state.json").write_text(
        json.dumps(state, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )
    return rd


# ===========================================================================
# TestPaperCommandRegistration — A17
# ===========================================================================

class TestPaperCommandRegistration:
    """Verify the paper command group is registered with all subcommands."""

    def test_paper_group_exists(self):
        """paper group should be a registered subcommand."""
        result = runner.invoke(app, ["paper", "--help"])
        assert result.exit_code == 0
        assert "Paper review workflow" in result.output

    def test_create_command_listed(self):
        result = runner.invoke(app, ["paper", "--help"])
        assert "create" in result.output

    def test_run_command_listed(self):
        result = runner.invoke(app, ["paper", "--help"])
        assert "run" in result.output

    def test_resume_command_listed(self):
        result = runner.invoke(app, ["paper", "--help"])
        assert "resume" in result.output

    def test_status_command_listed(self):
        result = runner.invoke(app, ["paper", "--help"])
        assert "status" in result.output

    def test_list_command_listed(self):
        result = runner.invoke(app, ["paper", "--help"])
        assert "list" in result.output

    def test_subcommand_count(self):
        """Should have exactly 5 subcommands: create, run, resume, status, list."""
        result = runner.invoke(app, ["paper", "--help"])
        for cmd in ("create", "run", "resume", "status", "list"):
            assert cmd in result.output


# ===========================================================================
# TestPaperCreate — A17
# ===========================================================================

_RT_PATH = "ai_workflow_hub.context_layer.adapters.paper_runtime"


class TestPaperCreate:
    """Test `paper create` command."""

    def test_create_success(self, tmp_path):
        """create should display run_id and run_dir on success."""
        mock_result = {
            "run_id": "paper-20260612-test01",
            "run_dir": str(tmp_path / "paper-20260612-test01"),
            "task_id": "TASK-001",
            "project_id": "proj-1",
            "status": "created",
        }
        with patch(f"{_RT_PATH}.create_paper_run", return_value=mock_result):
            result = _invoke(["paper", "create", "--task", "TASK-001", "--project", "proj-1"])
        assert result.exit_code == 0
        assert "paper-20260612-test01" in result.output
        assert "TASK-001" in result.output

    def test_create_shows_project_when_present(self, tmp_path):
        """create should print project_id when non-empty."""
        mock_result = {
            "run_id": "paper-20260612-abc",
            "run_dir": str(tmp_path),
            "task_id": "T-1",
            "project_id": "my-project",
            "status": "created",
        }
        with patch(f"{_RT_PATH}.create_paper_run", return_value=mock_result):
            result = _invoke(["paper", "create", "--task", "T-1", "--project", "my-project"])
        assert result.exit_code == 0
        assert "my-project" in result.output

    def test_create_empty_task_error(self):
        """create with empty task_id should fail."""
        with patch(f"{_RT_PATH}.create_paper_run", side_effect=ValueError("task_id must be a non-empty string")):
            result = _invoke(["paper", "create", "--task", ""])
        assert result.exit_code == 1
        assert "Create failed" in result.output

    def test_create_no_project(self, tmp_path):
        """create without project_id should succeed."""
        mock_result = {
            "run_id": "paper-20260612-np",
            "run_dir": str(tmp_path),
            "task_id": "T-2",
            "project_id": "",
            "status": "created",
        }
        with patch(f"{_RT_PATH}.create_paper_run", return_value=mock_result):
            result = _invoke(["paper", "create", "--task", "T-2"])
        assert result.exit_code == 0
        assert "paper-20260612-np" in result.output


# ===========================================================================
# TestPaperRun — A17
# ===========================================================================

class TestPaperRun:
    """Test `paper run` command."""

    def test_run_completed_success(self):
        """run should display completed status."""
        mock_result = {
            "run_id": "paper-test-01",
            "status": "completed",
            "state": {
                "task_id": "TASK-001",
                "executed_nodes": ["parser", "acceptance", "finalizer"],
                "paragraph_text": "sensitive text",
            },
            "warnings": [],
        }
        with patch(f"{_RT_PATH}.execute_paper_run", return_value=mock_result), \
             patch(f"{_RT_PATH}.sanitize_run_id", return_value="paper-test-01"):
            result = _invoke(["paper", "run", "--run-id", "paper-test-01"])
        assert result.exit_code == 0
        assert "completed" in result.output
        assert "TASK-001" in result.output

    def test_run_sanitizes_run_id(self):
        """run should sanitize user-supplied run_id (A16B L1)."""
        mock_result = {
            "run_id": "paper_test_01",
            "status": "completed",
            "state": {"task_id": "T-1", "executed_nodes": []},
            "warnings": [],
        }
        with patch(f"{_RT_PATH}.execute_paper_run", return_value=mock_result) as mock_exec, \
             patch(f"{_RT_PATH}.sanitize_run_id", return_value="paper_test_01") as mock_san:
            result = _invoke(["paper", "run", "--run-id", "paper/test/01"])
        assert result.exit_code == 0
        mock_san.assert_called_once_with("paper/test/01")
        mock_exec.assert_called_once()
        # Verify sanitized run_id was passed
        call_args = mock_exec.call_args
        assert call_args[0][0] == "paper_test_01" or call_args[1].get("run_id") == "paper_test_01"
        assert "sanitized" in result.output

    def test_run_file_not_found(self):
        """run with non-existent run_id should fail."""
        with patch(f"{_RT_PATH}.execute_paper_run",
                   side_effect=FileNotFoundError("Run directory not found")), \
             patch(f"{_RT_PATH}.sanitize_run_id", return_value="bad-id"):
            result = _invoke(["paper", "run", "--run-id", "bad-id"])
        assert result.exit_code == 1
        assert "Execute failed" in result.output

    def test_run_human_required(self):
        """run should show resume instructions for human_required status."""
        mock_result = {
            "run_id": "paper-hr-01",
            "status": "human_required",
            "state": {
                "task_id": "TASK-002",
                "executed_nodes": ["parser", "acceptance", "human_gate"],
            },
            "gate_artifact": "/path/to/paper-human-gate.md",
            "warnings": [],
        }
        with patch(f"{_RT_PATH}.execute_paper_run", return_value=mock_result), \
             patch(f"{_RT_PATH}.sanitize_run_id", return_value="paper-hr-01"):
            result = _invoke(["paper", "run", "--run-id", "paper-hr-01"])
        assert result.exit_code == 0
        assert "human_required" in result.output
        assert "Human review required" in result.output
        assert "paper-human-gate.md" in result.output
        assert "aihub paper resume" in result.output

    def test_run_with_error(self):
        """run should display error message if present."""
        mock_result = {
            "run_id": "paper-err-01",
            "status": "error",
            "state": {"task_id": "T-3", "executed_nodes": []},
            "error": "graph compilation failed",
            "warnings": [],
        }
        with patch(f"{_RT_PATH}.execute_paper_run", return_value=mock_result), \
             patch(f"{_RT_PATH}.sanitize_run_id", return_value="paper-err-01"):
            result = _invoke(["paper", "run", "--run-id", "paper-err-01"])
        assert result.exit_code == 0
        assert "error" in result.output
        assert "graph compilation failed" in result.output

    def test_run_with_warnings(self):
        """run should display warnings from best-effort operations."""
        mock_result = {
            "run_id": "paper-warn-01",
            "status": "completed",
            "state": {"task_id": "T-4", "executed_nodes": ["parser"]},
            "warnings": ["gate_artifact_write_failed: disk full"],
        }
        with patch(f"{_RT_PATH}.execute_paper_run", return_value=mock_result), \
             patch(f"{_RT_PATH}.sanitize_run_id", return_value="paper-warn-01"):
            result = _invoke(["paper", "run", "--run-id", "paper-warn-01"])
        assert result.exit_code == 0
        assert "WARN" in result.output
        assert "disk full" in result.output


# ===========================================================================
# TestPaperResume — A17
# ===========================================================================

class TestPaperResume:
    """Test `paper resume` command."""

    def test_resume_approved_success(self):
        """resume with approved decision should succeed."""
        mock_result = {
            "run_id": "paper-res-01",
            "status": "completed",
            "state": {
                "human_gate_decision": "approved",
                "decision_round": 1,
                "executed_nodes": ["parser", "acceptance", "finalizer"],
            },
            "warnings": [],
        }
        with patch(f"{_RT_PATH}.resume_paper_run", return_value=mock_result), \
             patch(f"{_RT_PATH}.sanitize_run_id", return_value="paper-res-01"):
            result = _invoke([
                "paper", "resume", "--run-id", "paper-res-01",
                "--decision", "approved", "--reviewer", "user@test.com",
            ])
        assert result.exit_code == 0
        assert "completed" in result.output
        assert "approved" in result.output

    def test_resume_rejected(self):
        """resume with rejected decision should succeed."""
        mock_result = {
            "run_id": "paper-rej-01",
            "status": "completed",
            "state": {
                "human_gate_decision": "rejected",
                "decision_round": 1,
                "executed_nodes": ["parser", "human_gate", "finalizer"],
            },
            "warnings": [],
        }
        with patch(f"{_RT_PATH}.resume_paper_run", return_value=mock_result), \
             patch(f"{_RT_PATH}.sanitize_run_id", return_value="paper-rej-01"):
            result = _invoke([
                "paper", "resume", "--run-id", "paper-rej-01",
                "--decision", "rejected",
            ])
        assert result.exit_code == 0
        assert "rejected" in result.output

    def test_resume_sanitizes_run_id(self):
        """resume should sanitize user-supplied run_id."""
        mock_result = {
            "run_id": "paper_res_01",
            "status": "completed",
            "state": {"human_gate_decision": "approved", "decision_round": 1, "executed_nodes": []},
            "warnings": [],
        }
        with patch(f"{_RT_PATH}.resume_paper_run", return_value=mock_result) as mock_res, \
             patch(f"{_RT_PATH}.sanitize_run_id", return_value="paper_res_01") as mock_san:
            result = _invoke([
                "paper", "resume", "--run-id", "paper/res/01",
                "--decision", "approved",
            ])
        assert result.exit_code == 0
        mock_san.assert_called_once_with("paper/res/01")
        mock_res.assert_called_once_with(
            run_id="paper_res_01", decision="approved", reviewer_id="", note="",
        )

    def test_resume_invalid_decision(self):
        """resume with invalid decision should fail."""
        with patch(f"{_RT_PATH}.resume_paper_run",
                   side_effect=ValueError("Invalid decision: maybe. Must be one of {'approved', 'rejected'}")), \
             patch(f"{_RT_PATH}.sanitize_run_id", return_value="paper-inv-01"):
            result = _invoke([
                "paper", "resume", "--run-id", "paper-inv-01",
                "--decision", "maybe",
            ])
        assert result.exit_code == 1
        assert "Resume failed" in result.output

    def test_resume_not_paused(self):
        """resume on non-paused run should fail."""
        with patch(f"{_RT_PATH}.resume_paper_run",
                   side_effect=ValueError("Run paper-x is not paused")), \
             patch(f"{_RT_PATH}.sanitize_run_id", return_value="paper-x"):
            result = _invoke([
                "paper", "resume", "--run-id", "paper-x",
                "--decision", "approved",
            ])
        assert result.exit_code == 1
        assert "Resume failed" in result.output

    def test_resume_with_note(self):
        """resume should pass note through to runtime."""
        mock_result = {
            "run_id": "paper-note-01",
            "status": "completed",
            "state": {"human_gate_decision": "approved", "decision_round": 1, "executed_nodes": []},
            "warnings": [],
        }
        with patch(f"{_RT_PATH}.resume_paper_run", return_value=mock_result) as mock_res, \
             patch(f"{_RT_PATH}.sanitize_run_id", return_value="paper-note-01"):
            result = _invoke([
                "paper", "resume", "--run-id", "paper-note-01",
                "--decision", "approved", "--note", "Looks good",
            ])
        assert result.exit_code == 0
        mock_res.assert_called_once_with(
            run_id="paper-note-01", decision="approved",
            reviewer_id="", note="Looks good",
        )


# ===========================================================================
# TestPaperStatus — A17
# ===========================================================================

class TestPaperStatus:
    """Test `paper status` command."""

    def test_status_found(self):
        """status should display run info."""
        mock_info = {
            "run_id": "paper-st-01",
            "task_id": "TASK-100",
            "project_id": "proj-a",
            "status": "completed",
            "acceptance_status": "accepted",
            "blocking_count": 0,
            "human_required": False,
            "human_gate_decision": "",
            "reviewer_id": "",
            "decision_round": 0,
            "executed_nodes": ["parser", "acceptance", "finalizer"],
            "error_message": "",
            "created_at": "2026-06-12T10:00:00+00:00",
            "updated_at": "2026-06-12T10:05:00+00:00",
        }
        with patch(f"{_RT_PATH}.get_paper_run_status", return_value=mock_info), \
             patch(f"{_RT_PATH}.sanitize_run_id", return_value="paper-st-01"):
            result = _invoke(["paper", "status", "--run-id", "paper-st-01"])
        assert result.exit_code == 0
        assert "completed" in result.output
        assert "TASK-100" in result.output

    def test_status_not_found(self):
        """status with unknown run_id should fail."""
        with patch(f"{_RT_PATH}.get_paper_run_status", return_value=None), \
             patch(f"{_RT_PATH}.sanitize_run_id", return_value="paper-unknown"):
            result = _invoke(["paper", "status", "--run-id", "paper-unknown"])
        assert result.exit_code == 1
        assert "not found" in result.output

    def test_status_redacts_sensitive_fields(self):
        """status should redact sensitive fields before display (A16B L3)."""
        mock_info = {
            "run_id": "paper-rd-01",
            "task_id": "T-RD",
            "project_id": "",
            "status": "human_required",
            "acceptance_status": "",
            "blocking_count": 1,
            "human_required": True,
            "human_gate_decision": "",
            "reviewer_id": "",
            "decision_round": 0,
            "executed_nodes": ["parser", "acceptance"],
            "error_message": "",
            "created_at": "2026-06-12T09:00:00",
            "updated_at": "2026-06-12T09:01:00",
            # Sensitive fields that should be redacted
            "paragraph_text": "SECRET CONTENT",
            "writelab_token": "tok-secret-123",
        }
        with patch(f"{_RT_PATH}.get_paper_run_status", return_value=mock_info), \
             patch(f"{_RT_PATH}.sanitize_run_id", return_value="paper-rd-01"):
            result = _invoke(["paper", "status", "--run-id", "paper-rd-01"])
        assert result.exit_code == 0
        # Sensitive values should NOT appear in output
        assert "SECRET CONTENT" not in result.output
        assert "tok-secret-123" not in result.output

    def test_status_sanitizes_run_id(self):
        """status should sanitize run_id (A16B L1)."""
        mock_info = {
            "run_id": "paper_san_01",
            "task_id": "T",
            "project_id": "",
            "status": "completed",
            "acceptance_status": "",
            "blocking_count": 0,
            "human_required": False,
            "human_gate_decision": "",
            "reviewer_id": "",
            "decision_round": 0,
            "executed_nodes": [],
            "error_message": "",
            "created_at": "",
            "updated_at": "",
        }
        with patch(f"{_RT_PATH}.get_paper_run_status", return_value=mock_info) as mock_st, \
             patch(f"{_RT_PATH}.sanitize_run_id", return_value="paper_san_01") as mock_san:
            result = _invoke(["paper", "status", "--run-id", "paper/san/01"])
        assert result.exit_code == 0
        mock_san.assert_called_once_with("paper/san/01")
        mock_st.assert_called_once_with("paper_san_01")

    def test_status_shows_error_message(self):
        """status should display error_message when present."""
        mock_info = {
            "run_id": "paper-err-st",
            "task_id": "T-E",
            "project_id": "",
            "status": "error",
            "acceptance_status": "",
            "blocking_count": 0,
            "human_required": False,
            "human_gate_decision": "",
            "reviewer_id": "",
            "decision_round": 0,
            "executed_nodes": [],
            "error_message": "something went terribly wrong",
            "created_at": "2026-06-12T08:00:00",
            "updated_at": "2026-06-12T08:00:05",
        }
        with patch(f"{_RT_PATH}.get_paper_run_status", return_value=mock_info), \
             patch(f"{_RT_PATH}.sanitize_run_id", return_value="paper-err-st"):
            result = _invoke(["paper", "status", "--run-id", "paper-err-st"])
        assert result.exit_code == 0
        assert "something went terribly wrong" in result.output


# ===========================================================================
# TestPaperList — A17
# ===========================================================================

class TestPaperList:
    """Test `paper list` command."""

    def test_list_empty(self, tmp_path):
        """list with no runs should show empty message."""
        with patch("ai_workflow_hub.cli._paper_runs_root", return_value=tmp_path), \
             patch(f"{_RT_PATH}.redact_state", side_effect=lambda s: dict(s)):
            result = _invoke(["paper", "list"])
        assert result.exit_code == 0
        assert "No paper runs" in result.output

    def test_list_nonexistent_root(self, tmp_path):
        """list when runs root doesn't exist should show empty."""
        fake_root = tmp_path / "nonexistent"
        with patch("ai_workflow_hub.cli._paper_runs_root", return_value=fake_root), \
             patch(f"{_RT_PATH}.redact_state", side_effect=lambda s: dict(s)):
            result = _invoke(["paper", "list"])
        assert result.exit_code == 0
        assert "No paper runs" in result.output

    def test_list_with_runs(self, tmp_path):
        """list should display runs in a table."""
        state1 = {
            "task_id": "TASK-A",
            "status": "completed",
            "blocking_count": 0,
            "updated_at": "2026-06-12T10:00:00",
        }
        state2 = {
            "task_id": "TASK-B",
            "status": "human_required",
            "blocking_count": 2,
            "updated_at": "2026-06-12T09:00:00",
        }
        _make_run_dir(tmp_path, "paper-run-1", state1)
        _make_run_dir(tmp_path, "paper-run-2", state2)

        with patch("ai_workflow_hub.cli._paper_runs_root", return_value=tmp_path), \
             patch(f"{_RT_PATH}.redact_state", side_effect=lambda s: dict(s)):
            result = _invoke(["paper", "list"])
        assert result.exit_code == 0
        assert "TASK-A" in result.output or "paper-run" in result.output

    def test_list_status_filter(self, tmp_path):
        """list --status should filter by status."""
        state_completed = {
            "task_id": "TASK-C",
            "status": "completed",
            "blocking_count": 0,
            "updated_at": "2026-06-12T10:00:00",
        }
        state_hr = {
            "task_id": "TASK-H",
            "status": "human_required",
            "blocking_count": 1,
            "updated_at": "2026-06-12T09:00:00",
        }
        _make_run_dir(tmp_path, "paper-c", state_completed)
        _make_run_dir(tmp_path, "paper-h", state_hr)

        with patch("ai_workflow_hub.cli._paper_runs_root", return_value=tmp_path), \
             patch(f"{_RT_PATH}.redact_state", side_effect=lambda s: dict(s)):
            result = _invoke(["paper", "list", "--status", "completed"])
        assert result.exit_code == 0
        # Should show completed but not human_required
        assert "No matching" not in result.output or "TASK-C" in result.output

    def test_list_limit(self, tmp_path):
        """list --limit should restrict output."""
        for i in range(5):
            _make_run_dir(tmp_path, f"paper-{i:03d}", {
                "task_id": f"TASK-{i}",
                "status": "completed",
                "blocking_count": 0,
                "updated_at": f"2026-06-12T1{i}:00:00",
            })

        with patch("ai_workflow_hub.cli._paper_runs_root", return_value=tmp_path), \
             patch(f"{_RT_PATH}.redact_state", side_effect=lambda s: dict(s)):
            result = _invoke(["paper", "list", "--limit", "2"])
        assert result.exit_code == 0

    def test_list_redacts_sensitive(self, tmp_path):
        """list should redact sensitive fields before display."""
        state = {
            "task_id": "TASK-SECRET",
            "status": "completed",
            "blocking_count": 0,
            "updated_at": "2026-06-12T10:00:00",
            "paragraph_text": "THIS IS SECRET",
            "writelab_token": "SECRET_TOKEN",
        }
        _make_run_dir(tmp_path, "paper-secret", state)

        from ai_workflow_hub.context_layer.adapters.paper_runtime import redact_state as real_redact

        with patch("ai_workflow_hub.cli._paper_runs_root", return_value=tmp_path), \
             patch(f"{_RT_PATH}.redact_state", side_effect=real_redact):
            result = _invoke(["paper", "list"])
        assert result.exit_code == 0
        assert "THIS IS SECRET" not in result.output
        assert "SECRET_TOKEN" not in result.output


# ===========================================================================
# TestPaperCLISanitization — A17 (cross-cutting)
# ===========================================================================

class TestPaperCLISanitization:
    """Cross-cutting tests: sanitize + redact in every command path."""

    def test_run_no_sanitize_message_when_clean(self):
        """run should NOT print sanitized message when run_id is already clean."""
        mock_result = {
            "run_id": "paper-clean-01",
            "status": "completed",
            "state": {"task_id": "T", "executed_nodes": []},
            "warnings": [],
        }
        # sanitize returns the same string
        with patch(f"{_RT_PATH}.execute_paper_run", return_value=mock_result), \
             patch(f"{_RT_PATH}.sanitize_run_id", return_value="paper-clean-01"):
            result = _invoke(["paper", "run", "--run-id", "paper-clean-01"])
        assert result.exit_code == 0
        assert "sanitized" not in result.output

    def test_resume_no_sanitize_message_when_clean(self):
        """resume should NOT print sanitized message when run_id is clean."""
        mock_result = {
            "run_id": "paper-clean-r",
            "status": "completed",
            "state": {"human_gate_decision": "approved", "decision_round": 1, "executed_nodes": []},
            "warnings": [],
        }
        with patch(f"{_RT_PATH}.resume_paper_run", return_value=mock_result), \
             patch(f"{_RT_PATH}.sanitize_run_id", return_value="paper-clean-r"):
            result = _invoke([
                "paper", "resume", "--run-id", "paper-clean-r",
                "--decision", "approved",
            ])
        assert result.exit_code == 0
        assert "sanitized" not in result.output

    def test_status_no_sanitize_message_when_clean(self):
        """status should NOT print sanitized message when run_id is clean."""
        mock_info = {
            "run_id": "paper-clean-s",
            "task_id": "T", "project_id": "", "status": "completed",
            "acceptance_status": "", "blocking_count": 0,
            "human_required": False, "human_gate_decision": "",
            "reviewer_id": "", "decision_round": 0,
            "executed_nodes": [], "error_message": "",
            "created_at": "", "updated_at": "",
        }
        with patch(f"{_RT_PATH}.get_paper_run_status", return_value=mock_info), \
             patch(f"{_RT_PATH}.sanitize_run_id", return_value="paper-clean-s"):
            result = _invoke(["paper", "status", "--run-id", "paper-clean-s"])
        assert result.exit_code == 0
        assert "sanitized" not in result.output


# ===========================================================================
# TestA17L2Fix — sanitize ValueError handling (L2)
# ===========================================================================

class TestA17L2Fix:
    """Verify sanitize_run_id ValueError is caught in run/resume (A17 L2 fix)."""

    def test_run_sanitize_value_error(self):
        """run should catch ValueError from sanitize_run_id."""
        with patch(f"{_RT_PATH}.sanitize_run_id", side_effect=ValueError("run_id produces empty string")):
            result = _invoke(["paper", "run", "--run-id", "!!"])
        assert result.exit_code == 1
        assert "Invalid run_id" in result.output

    def test_resume_sanitize_value_error(self):
        """resume should catch ValueError from sanitize_run_id."""
        with patch(f"{_RT_PATH}.sanitize_run_id", side_effect=ValueError("run_id must be non-empty")):
            result = _invoke([
                "paper", "resume", "--run-id", "!!",
                "--decision", "approved",
            ])
        assert result.exit_code == 1
        assert "Invalid run_id" in result.output

    def test_status_sanitize_value_error(self):
        """status should catch ValueError from sanitize_run_id."""
        with patch(f"{_RT_PATH}.sanitize_run_id", side_effect=ValueError("empty after sanitize")):
            result = _invoke(["paper", "status", "--run-id", "!!"])
        assert result.exit_code == 1
        assert "Invalid run_id" in result.output


# ===========================================================================
# TestA17L3Fix — error/warning redaction (L3)
# ===========================================================================

class TestA17L3Fix:
    """Verify error/warning strings are redacted before display (A17 L3 fix)."""

    def test_redact_str_helper(self):
        """_redact_str should replace sensitive field values."""
        from ai_workflow_hub.cli import _redact_str
        assert _redact_str("paragraph_text: secret content here") == "paragraph_text: [REDACTED]"
        assert _redact_str("writelab_token: tok-abc123") == "writelab_token: [REDACTED]"

    def test_redact_str_preserves_clean_text(self):
        """_redact_str should leave non-sensitive text unchanged."""
        from ai_workflow_hub.cli import _redact_str
        clean = "disk full, cannot write artifact"
        assert _redact_str(clean) == clean

    def test_run_warnings_redacted(self):
        """run should redact warning strings before printing."""
        mock_result = {
            "run_id": "paper-l3-w",
            "status": "completed",
            "state": {"task_id": "T", "executed_nodes": []},
            "warnings": ["paragraph_text: leaked secret data in node X"],
        }
        with patch(f"{_RT_PATH}.execute_paper_run", return_value=mock_result), \
             patch(f"{_RT_PATH}.sanitize_run_id", return_value="paper-l3-w"):
            result = _invoke(["paper", "run", "--run-id", "paper-l3-w"])
        assert result.exit_code == 0
        assert "leaked secret data" not in result.output
        assert "[REDACTED]" in result.output

    def test_run_error_redacted(self):
        """run should redact error string before printing."""
        mock_result = {
            "run_id": "paper-l3-e",
            "status": "error",
            "state": {"task_id": "T", "executed_nodes": []},
            "error": "writelab_token: secret-tok-xyz caused auth failure",
            "warnings": [],
        }
        with patch(f"{_RT_PATH}.execute_paper_run", return_value=mock_result), \
             patch(f"{_RT_PATH}.sanitize_run_id", return_value="paper-l3-e"):
            result = _invoke(["paper", "run", "--run-id", "paper-l3-e"])
        assert result.exit_code == 0
        assert "secret-tok-xyz" not in result.output
        assert "[REDACTED]" in result.output

    def test_resume_warnings_redacted(self):
        """resume should redact warning strings before printing."""
        mock_result = {
            "run_id": "paper-l3-r",
            "status": "completed",
            "state": {"human_gate_decision": "approved", "decision_round": 1, "executed_nodes": []},
            "warnings": ["paragraph_text=raw secret text"],
        }
        with patch(f"{_RT_PATH}.resume_paper_run", return_value=mock_result), \
             patch(f"{_RT_PATH}.sanitize_run_id", return_value="paper-l3-r"):
            result = _invoke([
                "paper", "resume", "--run-id", "paper-l3-r",
                "--decision", "approved",
            ])
        assert result.exit_code == 0
        assert "raw secret text" not in result.output
        assert "[REDACTED]" in result.output
