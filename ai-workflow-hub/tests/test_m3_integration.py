"""M3 integration tests: compile_graph().invoke() pause-approve-resume flow.

These tests exercise the full LangGraph pipeline with decision files,
verifying that the graph actually stops at human_gate/fixer and resumes
correctly when decisions are written.
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
    subprocess.run(["git", "config", "user.email", "test@x.com"],
                   cwd=str(project), capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test"],
                   cwd=str(project), capture_output=True)
    subprocess.run(["git", "add", "."], cwd=str(project), capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"],
                   cwd=str(project), capture_output=True)
    return project


def _base_state(project_path: str, run_dir: str, **overrides) -> dict:
    s = {
        "project_id": "mock-proj", "project_name": "mock",
        "project_path": project_path, "worktree_path": project_path,
        "run_id": "m3-int", "run_dir": run_dir,
        "task_id": "t1", "task_title": "M3 integration test",
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
    (path / f"{name}.json").write_text(
        json.dumps({"status": status}), encoding="utf-8")


def _write_fix_control(run_dir: str, mode: str, pause: bool = False):
    path = Path(run_dir) / "decisions"
    path.mkdir(parents=True, exist_ok=True)
    (path / "fix-control.json").write_text(
        json.dumps({"mode": mode, "pause_before_next_fix": pause}),
        encoding="utf-8")


# ---------------------------------------------------------------------------
# T1: human_gate pause → approve → continue
# ---------------------------------------------------------------------------

class TestHumanGatePauseResume:

    def test_graph_invoke_pause_approve_continue(self, tmp_path):
        """Full graph.invoke() cycle with explicit state injection.

        NOT graph.invoke(None) checkpoint resume (MemorySaver unreliable).
        NOT CLI resume (aihub resume not implemented yet).

        Flow: first invoke pauses at gate → write approved →
        re-invoke with cleared state → gate passes → pipeline completes.
        This simulates the aihub resume pattern: load state.json,
        clear human_required, re-invoke.
        """
        from ai_workflow_hub.workflows.coding_graph import compile_graph
        from ai_workflow_hub.schemas import WorkflowState

        project = _setup_project(tmp_path)
        run_dir = str(tmp_path / "runs" / "int-graph")
        Path(run_dir).mkdir(parents=True)

        state_data = _base_state(str(project), run_dir, task_risk="high")
        state = WorkflowState(**state_data)

        graph = compile_graph("m3-int-graph")

        # --- first invoke: gate triggers, graph stops ---
        r1 = graph.invoke(
            state.model_dump(),
            {"configurable": {"thread_id": "m3-int-graph"}},
        )
        assert r1.get("status") == "human_required"
        assert r1.get("human_gate_triggered") is True
        assert Path(run_dir, "decisions", "human-gate.json").exists()
        assert not Path(run_dir, "execution-log.md").exists(), \
            "executor must not run before gate approval"

        # --- write approved decision ---
        _write_decision(run_dir, "human-gate", "approved")

        # --- second invoke: resume with cleared gate ---
        # Use r1 result + human_required=False to simulate aihub resume
        resume_state = WorkflowState(**{**r1, "human_required": False})
        r2 = graph.invoke(
            resume_state.model_dump(),
            {"configurable": {"thread_id": "m3-int-graph-2"}},
        )
        assert r2.get("human_required") is False
        assert r2.get("human_gate_decision") == "approved"
        assert Path(run_dir, "execution-log.md").exists(), \
            "executor should run after gate approval"
        assert Path(run_dir, "final-report.md").exists(), \
            "finalizer should produce report"

    def test_rejected_goes_to_final(self, tmp_path):
        """Write rejected → graph invoke → should end without execution."""
        from ai_workflow_hub.workflows.coding_graph import compile_graph
        from ai_workflow_hub.schemas import WorkflowState

        project = _setup_project(tmp_path)
        run_dir = str(tmp_path / "runs" / "int-t2")
        Path(run_dir).mkdir(parents=True)

        _write_decision(run_dir, "human-gate", "rejected")
        state_data = _base_state(str(project), run_dir, task_risk="high")
        state = WorkflowState(**state_data)

        graph = compile_graph("m3-int-t2")
        result = graph.invoke(
            state.model_dump(),
            {"configurable": {"thread_id": "m3-int-t2"}},
        )
        assert result.get("status") == "rejected"
        assert result.get("human_gate_decision") == "rejected"
        assert not Path(run_dir, "execution-log.md").exists(), \
            "executor should NOT run when gate rejected"


# ---------------------------------------------------------------------------
# T2: fixer supervised mode pause → continue
# ---------------------------------------------------------------------------

class TestFixerSupervisedPause:

    def test_supervised_pauses_before_first_fix(self, tmp_path):
        """supervised mode + no decision → test failure should pause, not auto-fix."""
        from ai_workflow_hub.nodes.human_gate import human_gate_node
        from ai_workflow_hub.nodes.executor import executor_node
        from ai_workflow_hub.nodes.tester import tester_node

        project = _setup_project(tmp_path)
        run_dir = str(tmp_path / "runs" / "int-t3")
        Path(run_dir).mkdir(parents=True)

        # Set up a failing test + supervised mode
        _write_fix_control(run_dir, "supervised")
        s = _base_state(str(project), run_dir,
                        test_commands={"unit_test": "exit 1"},
                        dry_run=False, apply_changes=False, run_tests=True)

        # Run through human_gate, executor, tester manually
        s.update(human_gate_node(s))
        assert s.get("human_required") is not True

        s.update(executor_node(s))
        s.update(tester_node(s))
        assert s["test_exit_code"] != 0, "test should fail"

        # Now manually invoke the route logic to verify it would pause
        from ai_workflow_hub.workflows.coding_graph import _test_route
        route = _test_route(s)
        assert route == "__end__", \
            f"supervised mode should pause before fix, got route={route}"

    def test_supervised_with_continue_proceeds_to_fix(self, tmp_path):
        """supervised mode + fix-before-round-1.json=continue → should proceed."""
        from ai_workflow_hub.nodes.human_gate import human_gate_node
        from ai_workflow_hub.nodes.executor import executor_node
        from ai_workflow_hub.nodes.tester import tester_node

        project = _setup_project(tmp_path)
        run_dir = str(tmp_path / "runs" / "int-t4")
        Path(run_dir).mkdir(parents=True)

        _write_fix_control(run_dir, "supervised")
        _write_decision(run_dir, "fix-before-round-1", "continue")

        s = _base_state(str(project), run_dir,
                        test_commands={"unit_test": "exit 1"},
                        dry_run=False, run_tests=True)

        s.update(human_gate_node(s))
        s.update(executor_node(s))
        s.update(tester_node(s))
        assert s["test_exit_code"] != 0

        from ai_workflow_hub.workflows.coding_graph import _test_route
        route = _test_route(s)
        assert route == "fix_node", \
            f"continue decision should proceed to fix, got route={route}"


# ---------------------------------------------------------------------------
# T3: corrupted JSON does not proceed to side-effect nodes
# ---------------------------------------------------------------------------

class TestCorruptJsonNoSideEffect:

    def test_corrupt_human_gate_json_pauses(self, tmp_path):
        """Corrupt human-gate.json → route should return __end__, not execute."""
        from ai_workflow_hub.workflows.coding_graph import _human_gate_route

        run_dir = str(tmp_path)
        path = Path(run_dir) / "decisions"
        path.mkdir(parents=True)
        (path / "human-gate.json").write_text("{not valid json", encoding="utf-8")

        state = {
            "status": "human_required",
            "human_required": True,
            "run_dir": run_dir,
        }
        route = _human_gate_route(state)
        assert route == "__end__", \
            f"corrupt json should pause, got {route}"

    def test_corrupt_fix_decision_pauses(self, tmp_path):
        """Corrupt fix-before-round-1.json → route should return __end__."""
        from ai_workflow_hub.workflows.coding_graph import _test_route

        run_dir = str(tmp_path)
        path = Path(run_dir) / "decisions"
        path.mkdir(parents=True)
        (path / "fix-before-round-1.json").write_text(
            "{broken", encoding="utf-8")

        state = {
            "test_exit_code": 1,
            "fix_round": 0,
            "max_fix_rounds": 3,
            "run_dir": run_dir,
        }
        route = _test_route(state)
        assert route == "__end__", \
            f"corrupt fix decision should pause, got {route}"


# ---------------------------------------------------------------------------
# T4: legacy run compat
# ---------------------------------------------------------------------------

class TestLegacyRunCompat:

    def test_legacy_human_gate_md_without_decision(self, tmp_path):
        """Old run with human-gate.md but no decision file → should not error."""
        from ai_workflow_hub.nodes.human_gate import human_gate_node

        project = _setup_project(tmp_path)
        run_dir = str(tmp_path / "runs" / "int-t7")
        Path(run_dir).mkdir(parents=True)

        # Simulate legacy: write human-gate.md manually, no decisions dir
        Path(run_dir, "human-gate.md").write_text("# Human Gate (legacy)",
                                                  encoding="utf-8")

        s = _base_state(str(project), run_dir, task_risk="high")
        result = human_gate_node(s)

        # Should NOT crash; should proceed to write decision file
        assert result["human_required"] is True
        assert result["human_gate_triggered"] is True
        # New decision file should be created
        assert Path(run_dir, "decisions", "human-gate.json").exists()
