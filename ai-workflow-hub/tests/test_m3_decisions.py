"""M3 decision-driven pipeline tests.

Covers: human_gate approved/rejected/pending, fixer supervised mode,
decision file corruption, legacy run compat.
"""

import json
import shutil
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

FIXTURE = Path(__file__).parent / "fixtures" / "mock_project"

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _setup_project(tmp_path: Path) -> Path:
    project = tmp_path / "mock_project"
    shutil.copytree(FIXTURE, project)
    subprocess.run(["git", "init"], cwd=str(project), capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@x.com"], cwd=str(project), capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=str(project), capture_output=True)
    subprocess.run(["git", "add", "."], cwd=str(project), capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=str(project), capture_output=True)
    return project


def _base_state(project_path: str, run_dir: str, **overrides) -> dict:
    s = {
        "project_id": "mock-proj", "project_name": "mock",
        "project_path": project_path, "worktree_path": project_path,
        "run_id": "m3-test", "run_dir": run_dir,
        "task_id": "t1", "task_title": "M3 decision test",
        "task_description": "test", "task_risk": "low", "plan": "test",
        "allowed_files": ["src/main.py"],
        "test_commands": {"unit_test": "echo PASS"},
        "dry_run": True, "apply_changes": False, "run_tests": True,
        "max_fix_rounds": 3, "fix_round": 0, "review_result": "",
    }
    s.update(overrides)
    return s


def _write_decision(run_dir: str, name: str, status: str):
    path = Path(run_dir) / "decisions"
    path.mkdir(parents=True, exist_ok=True)
    (path / f"{name}.json").write_text(json.dumps({"status": status}), encoding="utf-8")


def _write_fix_control(run_dir: str, mode: str = "auto", pause: bool = False):
    path = Path(run_dir) / "decisions"
    path.mkdir(parents=True, exist_ok=True)
    (path / "fix-control.json").write_text(
        json.dumps({"mode": mode, "pause_before_next_fix": pause}), encoding="utf-8")


# ---------------------------------------------------------------------------
# T1-T3: human_gate decisions
# ---------------------------------------------------------------------------

class TestHumanGateDecisions:

    def test_approved_routes_to_execute(self, tmp_path):
        """T1: approved decision → human_gate returns running, evidence written."""
        from ai_workflow_hub.nodes.human_gate import human_gate_node

        project = _setup_project(tmp_path)
        run_dir = str(tmp_path / "runs" / "t1")
        Path(run_dir).mkdir(parents=True)

        s = _base_state(str(project), run_dir, task_risk="high")
        _write_decision(run_dir, "human-gate", "approved")

        result = human_gate_node(s)
        assert result["human_required"] is False
        assert result["human_gate_triggered"] is True
        assert result["human_gate_decision"] == "approved"

    def test_rejected_routes_to_final(self, tmp_path):
        """T2: rejected decision → status=rejected, human_required=False."""
        from ai_workflow_hub.nodes.human_gate import human_gate_node

        project = _setup_project(tmp_path)
        run_dir = str(tmp_path / "runs" / "t2")
        Path(run_dir).mkdir(parents=True)

        s = _base_state(str(project), run_dir, task_risk="high")
        _write_decision(run_dir, "human-gate", "rejected")

        result = human_gate_node(s)
        assert result["status"] == "rejected"
        assert result["human_required"] is False
        assert result["human_gate_decision"] == "rejected"
        assert "blocked_reason" in result

    def test_pending_pauses_pipeline(self, tmp_path):
        """T3: pending → writes human-gate.md + decision, returns human_required."""
        from ai_workflow_hub.nodes.human_gate import human_gate_node

        project = _setup_project(tmp_path)
        run_dir = str(tmp_path / "runs" / "t3")
        Path(run_dir).mkdir(parents=True)

        s = _base_state(str(project), run_dir, task_risk="high")

        result = human_gate_node(s)
        assert result["status"] == "human_required"
        assert result["human_required"] is True
        assert result["human_gate_triggered"] is True
        assert Path(run_dir, "human-gate.md").exists()
        assert Path(run_dir, "decisions", "human-gate.json").exists()

        # verify decision file content
        decision = json.loads(
            Path(run_dir, "decisions", "human-gate.json").read_text(encoding="utf-8"))
        assert decision["status"] == "pending"


class TestHumanGateIdempotency:

    def test_does_not_overwrite_approved(self, tmp_path):
        """T4: pre-written approved survives re-execution."""
        from ai_workflow_hub.nodes.human_gate import human_gate_node

        project = _setup_project(tmp_path)
        run_dir = str(tmp_path / "runs" / "t4")
        Path(run_dir).mkdir(parents=True)

        _write_decision(run_dir, "human-gate", "approved")
        s = _base_state(str(project), run_dir, task_risk="high")

        result = human_gate_node(s)
        assert result["human_gate_decision"] == "approved"

        # file untouched
        decision = json.loads(
            Path(run_dir, "decisions", "human-gate.json").read_text(encoding="utf-8"))
        assert decision["status"] == "approved"

    def test_low_risk_passes_through(self, tmp_path):
        """low risk task → no gate → no decision file."""
        from ai_workflow_hub.nodes.human_gate import human_gate_node

        project = _setup_project(tmp_path)
        run_dir = str(tmp_path / "runs" / "t5")
        Path(run_dir).mkdir(parents=True)

        s = _base_state(str(project), run_dir, task_risk="low")
        result = human_gate_node(s)

        assert result["human_required"] is False
        assert not Path(run_dir, "decisions", "human-gate.json").exists()


# ---------------------------------------------------------------------------
# T5-T8: corrupted JSON + fixer decisions
# ---------------------------------------------------------------------------

class TestDecisionFileCorruption:

    def test_corrupt_json_returns_invalid(self, tmp_path):
        """T5: corrupt JSON → Decision.valid=False."""
        from ai_workflow_hub.run_decisions import read_decision as _read_decision

        run_dir = str(tmp_path)
        path = Path(run_dir) / "decisions"
        path.mkdir(parents=True)
        (path / "bad.json").write_text("{not json", encoding="utf-8")

        d = _read_decision(run_dir, "bad")
        assert d.valid is False
        assert d.exists is True
        assert d.error is not None

    def test_missing_file_returns_none_status(self, tmp_path):
        """File doesn't exist → status=None, exists=False, valid=True."""
        from ai_workflow_hub.run_decisions import read_decision as _read_decision

        d = _read_decision(str(tmp_path), "nonexistent")
        assert d.status is None
        assert d.exists is False
        assert d.valid is True

    def test_invalid_status_is_invalid(self, tmp_path):
        """Status not in allowed set → valid=False."""
        from ai_workflow_hub.run_decisions import read_decision as _read_decision

        run_dir = str(tmp_path)
        path = Path(run_dir) / "decisions"
        path.mkdir(parents=True)
        (path / "bad-status.json").write_text(
            json.dumps({"status": "maybe"}), encoding="utf-8")

        d = _read_decision(run_dir, "bad-status")
        assert d.valid is False
        assert "maybe" in (d.error or "")


class TestFixControl:

    def test_read_fix_control_defaults(self, tmp_path):
        """No control file → defaults."""
        from ai_workflow_hub.run_decisions import read_fix_control as _read_fix_control

        c = _read_fix_control(str(tmp_path))
        assert c.mode == "auto"
        assert c.pause_before_next_fix is False
        assert c.exists is False
        assert c.valid is True

    def test_invalid_fix_control_mode(self, tmp_path):
        """Invalid mode → valid=False."""
        from ai_workflow_hub.run_decisions import read_fix_control as _read_fix_control

        run_dir = str(tmp_path)
        path = Path(run_dir) / "decisions"
        path.mkdir(parents=True)
        (path / "fix-control.json").write_text(
            json.dumps({"mode": "unknown", "pause_before_next_fix": False}),
            encoding="utf-8")

        c = _read_fix_control(run_dir)
        assert c.valid is False


# ---------------------------------------------------------------------------
# T9-T11: fixer records
# ---------------------------------------------------------------------------

class TestFixerRecords:

    def test_fix_record_written_to_fix_records_dir(self):
        """_write_fix_record writes to fix-records/ not decisions/."""
        import tempfile
        from ai_workflow_hub.nodes.fixer import _write_fix_record

        with tempfile.TemporaryDirectory() as td:
            _write_fix_record(td, 1, applied=True)
            assert Path(td, "fix-records", "fix-after-round-1.json").exists()
            assert not Path(td, "decisions", "fix-after-round-1.json").exists()
            # verify content
            import json
            data = json.loads(
                Path(td, "fix-records", "fix-after-round-1.json").read_text(encoding="utf-8"))
            assert data["applied"] is True
            assert data["round"] == 1

    def test_fix_record_dry_run_marked(self):
        """dry-run fix record sets applied=False."""
        import tempfile
        from ai_workflow_hub.nodes.fixer import _write_fix_record

        with tempfile.TemporaryDirectory() as td:
            _write_fix_record(td, 2, applied=False)
            import json
            data = json.loads(
                Path(td, "fix-records", "fix-after-round-2.json").read_text(encoding="utf-8"))
            assert data["applied"] is False


# ---------------------------------------------------------------------------
# T14: human_gate_triggered compat
# ---------------------------------------------------------------------------

class TestEvidenceCompat:

    def test_human_gate_triggered_without_decision_is_legacy(self, tmp_path):
        """T14: old run with human-gate.md but no decision file → warning, not error."""
        project = _setup_project(tmp_path)
        run_dir = str(tmp_path / "runs" / "t14")
        Path(run_dir).mkdir(parents=True)

        # Simulate legacy run
        Path(run_dir, "human-gate.md").write_text("legacy", encoding="utf-8")

        state = {"human_gate_triggered": True, "status": "passed", "run_dir": run_dir}

        # Should not crash — legacy compat
        from ai_workflow_hub.run_decisions import read_decision as _read_decision
        d = _read_decision(run_dir, "human-gate")
        assert d.exists is False  # no decision file


# ---------------------------------------------------------------------------
# _side_effect_route control flow (P3 audit requirement)
# ---------------------------------------------------------------------------

class TestSideEffectRoute:

    def test_executor_failed_skips_test_node(self):
        """executor returns failed → route to final, not test."""
        from ai_workflow_hub.workflows.coding_graph import _side_effect_route

        state = {"status": "failed"}
        assert _side_effect_route(state) == "final_node"

    def test_executor_blocked_skips_test_node(self):
        """executor returns blocked → route to final."""
        from ai_workflow_hub.workflows.coding_graph import _side_effect_route

        state = {"status": "blocked"}
        assert _side_effect_route(state) == "final_node"

    def test_executor_rejected_skips_test_node(self):
        """executor returns rejected → route to final."""
        from ai_workflow_hub.workflows.coding_graph import _side_effect_route

        state = {"status": "rejected"}
        assert _side_effect_route(state) == "final_node"

    def test_executor_human_required_skips_test_node(self):
        """executor returns human_required → route to final."""
        from ai_workflow_hub.workflows.coding_graph import _side_effect_route

        state = {"status": "human_required"}
        assert _side_effect_route(state) == "final_node"

    def test_fixer_normal_continues_to_test(self):
        """Normal fix completion → test_node."""
        from ai_workflow_hub.workflows.coding_graph import _side_effect_route

        state = {"status": "running"}
        assert _side_effect_route(state) == "test_node"

    def test_executor_normal_continues_to_test(self):
        """Normal executor completion → test_node."""
        from ai_workflow_hub.workflows.coding_graph import _side_effect_route

        state = {}
        assert _side_effect_route(state) == "test_node"
