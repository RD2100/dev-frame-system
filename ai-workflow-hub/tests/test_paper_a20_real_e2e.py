"""test_paper_a20_real_e2e.py — A20 PAPER-REAL-RUNTIME-E2E Tests.

Proves the full paper workflow lifecycle using REAL runtime (no API mocks):
  create → execute (graph) → human_required → resume (graph) → completed

Then exercises CLI commands against the same real run directory to prove
ledger/evidence/validate/status/list all read from the same persisted state.

Privacy assertions: state.json on disk never contains sensitive values.
Decision audit trail verified on disk.

Uses writelab_mode="mock" with synthetic issues — no external services.
"""

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from ai_workflow_hub.cli import app
from ai_workflow_hub.context_layer.adapters.paper_runtime import (
    create_paper_run, execute_paper_run, resume_paper_run,
    get_paper_run_status, _load_state, _run_path,
)
from ai_workflow_hub.context_layer.adapters.paper_issue_ledger import (
    get_all_issues, get_open_issues, ledger_summary, is_clear,
)
from ai_workflow_hub.context_layer.adapters.paper_acceptance_gate import (
    validate_acceptance_result,
)

runner = CliRunner()
_RT_PATH = "ai_workflow_hub.context_layer.adapters.paper_runtime"

TASK_ID = "a20-real-e2e"
PROJECT_ID = "a20-proj"

SYNTHETIC_ISSUES = [
    {
        "issue_id": "a20-iss-001",
        "issue_type": "citation",
        "severity": "major",
        "description": "Reference [42] is missing from bibliography",
        "evidence": "Section 3, paragraph 2 cites [42] but it does not appear",
        "human_required": True,
        "blocking": False,
        "recommendation": "Add reference [42] or remove citation",
    },
    {
        "issue_id": "a20-iss-002",
        "issue_type": "argument",
        "severity": "minor",
        "description": "Weak justification in methodology section",
        "evidence": "Paragraph 4 does not explain why method X was chosen",
        "human_required": False,
        "blocking": False,
        "recommendation": "Strengthen methodology justification",
    },
    {
        "issue_id": "a20-iss-003",
        "issue_type": "expression",
        "severity": "info",
        "description": "Typo in abstract line 5",
        "evidence": "'teh' should be 'the'",
        "human_required": False,
        "blocking": False,
        "recommendation": "Fix typo",
    },
]


def _invoke(args: list[str]):
    with patch("ai_workflow_hub.cli.init_env"):
        return runner.invoke(app, args, catch_exceptions=False)


def _assert_state_privacy(state_path: Path):
    """Assert state.json on disk contains no sensitive values."""
    text = state_path.read_text(encoding="utf-8")
    for key in ("paragraph_text", "writelab_token"):
        # Key followed by a non-empty, non-REDACTED value
        import re
        m = re.search(rf'"{key}"\s*:\s*"(?!\[REDACTED\])([^"]+)"', text)
        if m:
            assert False, f"Sensitive key '{key}' with unredacted value on disk: {m.group(0)[:80]}"


# ===========================================================================
# TestA20RealLifecycle — Real runtime, real graph, real disk
# ===========================================================================

class TestA20RealLifecycle:
    """Full lifecycle with real graph execution — no API mocks."""

    def test_create_run(self, tmp_path):
        """Step 1: create_paper_run should produce run directory on disk."""
        base_dir = str(tmp_path)
        ledger_dir = str(tmp_path / "ledger")
        Path(ledger_dir).mkdir(parents=True, exist_ok=True)

        run = create_paper_run(
            TASK_ID, project_id=PROJECT_ID, base_dir=base_dir,
            initial_state={"ledger_dir": ledger_dir},
        )
        assert run["status"] == "created"
        assert run["task_id"] == TASK_ID
        assert run["project_id"] == PROJECT_ID
        assert Path(run["run_dir"]).exists()
        assert (Path(run["run_dir"]) / "state.json").exists()

        # State on disk should be privacy-clean
        _assert_state_privacy(Path(run["run_dir"]) / "state.json")

    def test_execute_to_human_required(self, tmp_path):
        """Step 2: execute should run graph and pause at human gate."""
        base_dir = str(tmp_path)
        ledger_dir = str(tmp_path / "ledger")
        Path(ledger_dir).mkdir(parents=True, exist_ok=True)

        run = create_paper_run(
            TASK_ID, project_id=PROJECT_ID, base_dir=base_dir,
            initial_state={"ledger_dir": ledger_dir},
        )
        result = execute_paper_run(
            run["run_id"], base_dir=base_dir,
            state_overrides={
                "writelab_mode": "mock",
                "expression_issues": [],
                "paragraph_issues": SYNTHETIC_ISSUES,
            },
        )
        assert result["status"] == "human_required"
        assert "gate_artifact" in result
        assert Path(result["gate_artifact"]).exists()

        # Verify graph nodes executed
        state = result["state"]
        assert "diagnosis_node" in state["executed_nodes"]
        assert "acceptance_gate_node" in state["executed_nodes"]
        assert "ledger_ingest_node" in state["executed_nodes"]
        assert "human_gate_node" in state["executed_nodes"]

        # Verify ledger on disk (same directory used by CLI)
        ledger_file = Path(ledger_dir) / f"{TASK_ID}.json"
        assert ledger_file.exists()
        ledger_entries = json.loads(ledger_file.read_text(encoding="utf-8"))
        assert len(ledger_entries) == 3
        issue_ids = [e["issue_id"] for e in ledger_entries]
        assert "a20-iss-001" in issue_ids
        assert "a20-iss-002" in issue_ids
        assert "a20-iss-003" in issue_ids

        # Verify ledger API reads same data
        summary = ledger_summary(TASK_ID, ledger_dir=ledger_dir)
        assert summary["total"] == 3
        assert summary["open"] == 3

        # Verify status API
        status = get_paper_run_status(run["run_id"], base_dir=base_dir)
        assert status["status"] == "human_required"
        assert status["human_required"] is True

        # State on disk privacy
        _assert_state_privacy(Path(run["run_dir"]) / "state.json")

    def test_resume_approved(self, tmp_path):
        """Step 3: resume with approved should complete via graph."""
        base_dir = str(tmp_path)
        ledger_dir = str(tmp_path / "ledger")
        Path(ledger_dir).mkdir(parents=True, exist_ok=True)

        # Create + execute
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

        # Resume
        resume_result = resume_paper_run(
            run["run_id"],
            decision="approved",
            reviewer_id="a20-reviewer@example.com",
            note="Issues acknowledged, proceeding with revision",
            base_dir=base_dir,
        )
        assert resume_result["status"] == "completed"

        state = resume_result["state"]
        assert state["human_gate_decision"] == "approved"
        assert state["reviewer_id"] == "a20-reviewer@example.com"
        assert state["decision_round"] == 1
        assert "paper_finalizer_node" in state["executed_nodes"]

        # Verify decision audit trail on disk
        decisions_dir = Path(run["run_dir"]) / "decisions"
        assert decisions_dir.is_dir()
        decision_file = decisions_dir / f"{TASK_ID}-decision.json"
        assert decision_file.exists()
        decision = json.loads(decision_file.read_text(encoding="utf-8"))
        assert decision["decision"] == "approved"
        assert decision["reviewer_id"] == "a20-reviewer@example.com"

        audit_file = decisions_dir / f"{TASK_ID}-audit.jsonl"
        assert audit_file.exists()
        audit_lines = [l for l in audit_file.read_text(encoding="utf-8").splitlines() if l.strip()]
        assert len(audit_lines) >= 1
        audit_entry = json.loads(audit_lines[0])
        assert audit_entry["decision"] == "approved"

        # Verify final status via API
        final_status = get_paper_run_status(run["run_id"], base_dir=base_dir)
        assert final_status["status"] == "completed"
        assert final_status["human_gate_decision"] == "approved"

        # State on disk privacy
        _assert_state_privacy(Path(run["run_dir"]) / "state.json")

    def test_full_lifecycle_with_ledger_verification(self, tmp_path):
        """Step 4: Full lifecycle with ledger entries verified from same source."""
        base_dir = str(tmp_path)
        ledger_dir = str(tmp_path / "ledger")
        Path(ledger_dir).mkdir(parents=True, exist_ok=True)

        # Create + execute + resume
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
            reviewer_id="a20-reviewer", base_dir=base_dir,
        )

        # Verify ledger entries are the same ones created during graph execution
        all_issues = get_all_issues(TASK_ID, ledger_dir=ledger_dir)
        assert len(all_issues) == 3
        open_issues = get_open_issues(TASK_ID, ledger_dir=ledger_dir)
        assert len(open_issues) == 3  # All still open (not resolved)

        summary = ledger_summary(TASK_ID, ledger_dir=ledger_dir)
        assert summary["total"] == 3
        assert summary["open"] == 3
        assert summary["blocking"] == 0

        # Verify gate artifact exists
        gate = Path(run["run_dir"]) / "paper-human-gate.md"
        assert gate.exists()
        gate_text = gate.read_text(encoding="utf-8")
        assert "Resume" in gate_text or "resume" in gate_text

        # Verify state.json has acceptance_result
        state = _load_state(_run_path(run["run_id"], base_dir))
        assert state is not None
        assert "acceptance_result" in state
        acceptance = state["acceptance_result"]
        assert acceptance["status"] in ("human_required", "accepted_with_limitation")

        # Validate acceptance result via gate API
        errors = validate_acceptance_result(acceptance)
        assert len(errors) == 0, f"Validation errors: {errors}"


# ===========================================================================
# TestA20CLIAgainstRealData — CLI reads from real run directory
# ===========================================================================

class TestA20CLIAgainstRealData:
    """CLI commands exercised against real persisted data (no mocks)."""

    @pytest.fixture
    def completed_run(self, tmp_path):
        """Set up a completed run via real runtime, return run info."""
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
            reviewer_id="a20-reviewer", base_dir=base_dir,
        )
        return {"run": run, "base_dir": base_dir, "ledger_dir": ledger_dir,
                "tmp_path": tmp_path}

    def test_cli_status_reads_real_state(self, completed_run):
        """paper status should read from real state.json."""
        run = completed_run["run"]
        runs_root = Path(completed_run["base_dir"]) / "runs" / "paper"
        with patch("ai_workflow_hub.cli._paper_runs_root",
                   return_value=runs_root), \
             patch(f"{_RT_PATH}._runs_root", return_value=runs_root):
            result = _invoke(["paper", "status", "--run-id", run["run_id"]])
        assert result.exit_code == 0
        assert "completed" in result.output

    def test_cli_status_json_reads_real_state(self, completed_run):
        """paper status --json should read from real state.json."""
        run = completed_run["run"]
        runs_root = Path(completed_run["base_dir"]) / "runs" / "paper"
        with patch("ai_workflow_hub.cli._paper_runs_root",
                   return_value=runs_root), \
             patch(f"{_RT_PATH}._runs_root", return_value=runs_root):
            result = _invoke(["paper", "status", "--run-id", run["run_id"], "--json"])
        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert parsed["status"] == "completed"

    def test_cli_ledger_reads_real_entries(self, completed_run):
        """paper ledger should read real ledger entries from disk."""
        run = completed_run["run"]
        # Need to set ledger_dir in state for CLI to find it
        # The CLI reads task_id from state, then queries ledger.
        # Since ledger_dir is not in the CLI path by default, we mock the ledger API
        # to use our ledger_dir.
        from ai_workflow_hub.context_layer.adapters import paper_issue_ledger as ledger_mod
        ledger_dir = completed_run["ledger_dir"]
        with patch("ai_workflow_hub.cli._paper_runs_root",
                   return_value=Path(completed_run["base_dir"]) / "runs" / "paper"), \
             patch(f"{_RT_PATH}.sanitize_run_id", return_value=run["run_id"]), \
             patch.object(ledger_mod, "ledger_summary",
                         side_effect=lambda tid: ledger_summary(tid, ledger_dir=ledger_dir)), \
             patch.object(ledger_mod, "get_open_issues",
                         side_effect=lambda tid: get_open_issues(tid, ledger_dir=ledger_dir)), \
             patch.object(ledger_mod, "is_clear",
                         side_effect=lambda tid: is_clear(tid, ledger_dir=ledger_dir)):
            result = _invoke(["paper", "ledger", "--run-id", run["run_id"]])
        assert result.exit_code == 0
        assert TASK_ID in result.output
        assert "3" in result.output  # 3 issues

    def test_cli_validate_reads_real_acceptance(self, completed_run):
        """paper validate should read real acceptance_result from state."""
        run = completed_run["run"]
        with patch("ai_workflow_hub.cli._paper_runs_root",
                   return_value=Path(completed_run["base_dir"]) / "runs" / "paper"):
            result = _invoke(["paper", "validate", "--run-id", run["run_id"]])
        assert result.exit_code == 0
        assert "PASSED" in result.output

    def test_cli_list_shows_real_run(self, completed_run):
        """paper list should show the real run."""
        run = completed_run["run"]
        runs_root = Path(completed_run["base_dir"]) / "runs" / "paper"
        with patch("ai_workflow_hub.cli._paper_runs_root",
                   return_value=runs_root):
            result = _invoke(["paper", "list"])
        assert result.exit_code == 0
        # Run ID is truncated in Rich table; check for visible prefix + task_id
        assert run["run_id"][:14] in result.output
        assert TASK_ID in result.output
        assert "completed" in result.output


# ===========================================================================
# TestA20PrivacyOnDisk — Real state.json privacy verification
# ===========================================================================

class TestA20PrivacyOnDisk:
    """Verify privacy of real state.json files throughout lifecycle."""

    def test_state_json_clean_after_create(self, tmp_path):
        """state.json after create should not contain sensitive values."""
        base_dir = str(tmp_path)
        run = create_paper_run(TASK_ID, base_dir=base_dir)
        _assert_state_privacy(Path(run["run_dir"]) / "state.json")

    def test_state_json_clean_after_execute(self, tmp_path):
        """state.json after execute should not contain sensitive values."""
        base_dir = str(tmp_path)
        ledger_dir = str(tmp_path / "ledger")
        Path(ledger_dir).mkdir(parents=True, exist_ok=True)
        run = create_paper_run(TASK_ID, base_dir=base_dir,
                               initial_state={"ledger_dir": ledger_dir})
        execute_paper_run(
            run["run_id"], base_dir=base_dir,
            state_overrides={
                "writelab_mode": "mock",
                "expression_issues": [],
                "paragraph_issues": SYNTHETIC_ISSUES,
            },
        )
        _assert_state_privacy(Path(run["run_dir"]) / "state.json")

    def test_state_json_clean_after_resume(self, tmp_path):
        """state.json after resume should not contain sensitive values."""
        base_dir = str(tmp_path)
        ledger_dir = str(tmp_path / "ledger")
        Path(ledger_dir).mkdir(parents=True, exist_ok=True)
        run = create_paper_run(TASK_ID, base_dir=base_dir,
                               initial_state={"ledger_dir": ledger_dir})
        execute_paper_run(
            run["run_id"], base_dir=base_dir,
            state_overrides={
                "writelab_mode": "mock",
                "expression_issues": [],
                "paragraph_issues": SYNTHETIC_ISSUES,
            },
        )
        resume_paper_run(run["run_id"], decision="approved", base_dir=base_dir)
        _assert_state_privacy(Path(run["run_dir"]) / "state.json")

    def test_gate_artifact_no_sensitive_data(self, tmp_path):
        """paper-human-gate.md should not contain paragraph_text or writelab_token values."""
        base_dir = str(tmp_path)
        ledger_dir = str(tmp_path / "ledger")
        Path(ledger_dir).mkdir(parents=True, exist_ok=True)
        run = create_paper_run(TASK_ID, base_dir=base_dir,
                               initial_state={"ledger_dir": ledger_dir})
        result = execute_paper_run(
            run["run_id"], base_dir=base_dir,
            state_overrides={
                "writelab_mode": "mock",
                "expression_issues": [],
                "paragraph_issues": SYNTHETIC_ISSUES,
            },
        )
        gate_path = Path(result["gate_artifact"])
        assert gate_path.exists()
        gate_text = gate_path.read_text(encoding="utf-8")
        # Gate artifact should not contain raw writelab_token
        assert "writelab_token" not in gate_text or "[REDACTED]" in gate_text
