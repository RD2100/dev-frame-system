"""End-to-end pipeline tests — full 4-node flow via manual node invocation.

Test 1: dry-run full pipeline (no mocking needed)
Test 2: high risk task blocked at human_gate
Test 3: fix-loop with mocked opencode_run

Imports are inside test functions to prevent pytest from collecting
node functions (tester_node, etc.) as test items.
"""

import shutil
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

FIXTURE = Path(__file__).parent / "fixtures" / "mock_project"


def _copy_fixture(tmp_path: Path) -> Path:
    project = tmp_path / "mock_project"
    shutil.copytree(FIXTURE, project)
    subprocess.run(["git", "init"], cwd=str(project),
                   capture_output=True, check=True)
    subprocess.run(["git", "config", "user.email", "test@test.com"],
                   cwd=str(project), capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test"],
                   cwd=str(project), capture_output=True)
    subprocess.run(["git", "add", "."], cwd=str(project),
                   capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"],
                   cwd=str(project), capture_output=True)
    return project


def _base_state(project_path: str, run_dir: str, **overrides) -> dict:
    s = {
        "project_id": "mock-proj",
        "project_name": "mock_project",
        "project_path": project_path,
        "worktree_path": project_path,
        "run_id": "e2e-test-001",
        "run_dir": run_dir,
        "task_id": "task-001",
        "task_title": "Add docstring to main.py",
        "task_description": "Add a module docstring to src/main.py",
        "task_risk": "low",
        "plan": "Add a docstring at top of src/main.py.",
        "allowed_files": ["src/main.py"],
        "test_commands": {"unit_test": "echo ALL_PASSED"},
        "dry_run": True,
        "apply_changes": False,
        "run_tests": True,
        "max_fix_rounds": 3,
        "fix_round": 0,
        "review_result": "",
    }
    s.update(overrides)
    return s


# ---------------------------------------------------------------------------
# Test 1: dry-run full pipeline
# ---------------------------------------------------------------------------

class TestDryRunPipeline:

    def test_full_pipeline_passes(self, tmp_path):
        from ai_workflow_hub.nodes.human_gate import human_gate_node
        from ai_workflow_hub.nodes.executor import executor_node
        from ai_workflow_hub.nodes.tester import tester_node
        from ai_workflow_hub.nodes.finalizer import finalizer_node

        project = _copy_fixture(tmp_path)
        run_dir = str(tmp_path / "runs" / "e2e-dry")
        Path(run_dir).mkdir(parents=True, exist_ok=True)

        s = _base_state(str(project), run_dir)
        s.update(human_gate_node(s))
        assert s.get("human_required") is not True

        s.update(executor_node(s))
        assert s.get("status") != "failed"

        s.update(tester_node(s))
        assert s["test_exit_code"] == 0

        s.update(finalizer_node(s))
        assert "ALL_PASSED" in s.get("test_output", "")
        assert Path(run_dir, "execution-log.md").exists()
        assert Path(run_dir, "test-output.md").exists()
        assert Path(run_dir, "final-report.md").exists()

    def test_dry_run_lists_without_run_tests(self, tmp_path):
        from ai_workflow_hub.nodes.human_gate import human_gate_node
        from ai_workflow_hub.nodes.executor import executor_node
        from ai_workflow_hub.nodes.tester import tester_node

        project = _copy_fixture(tmp_path)
        run_dir = str(tmp_path / "runs" / "e2e-list")
        Path(run_dir).mkdir(parents=True, exist_ok=True)

        s = _base_state(str(project), run_dir, run_tests=False)
        s.update(human_gate_node(s))
        s.update(executor_node(s))
        s.update(tester_node(s))

        assert s["test_exit_code"] == 0
        assert "DRY-RUN" in s.get("test_output", "")


# ---------------------------------------------------------------------------
# Test 2: high risk blocks at gate
# ---------------------------------------------------------------------------

class TestGateBlock:

    def test_high_risk_human_required_blocks(self, tmp_path):
        from ai_workflow_hub.nodes.human_gate import human_gate_node

        project = _copy_fixture(tmp_path)
        run_dir = str(tmp_path / "runs" / "e2e-blocked")
        Path(run_dir).mkdir(parents=True, exist_ok=True)

        s = _base_state(str(project), run_dir,
                        task_risk="high",
                        human_required=True,
                        dangerous_change=True)
        s.update(human_gate_node(s))

        assert s["status"] == "human_required"
        assert Path(run_dir, "human-gate.md").exists()


# ---------------------------------------------------------------------------
# Test 3: fix-loop with mocked opencode_run
# ---------------------------------------------------------------------------

FAKE_OPECODE_RESULT = {
    "exit_code": 0,
    "stdout": "Changes applied.",
    "stderr": "",
    "timed_out": False,
    "duration_seconds": 1.0,
    "command_preview": "mock",
}

FAKE_DIFF = {
    "diff_text": "diff --git a/src/main.py b/src/main.py\n+docstring\n",
    "changed_files": ["src/main.py"],
    "name_status": {"src/main.py": "M"},
    "diff_line_count": 3,
}


class TestFixLoop:

    def test_fix_loop_one_round(self, tmp_path):
        from ai_workflow_hub.nodes.human_gate import human_gate_node
        from ai_workflow_hub.nodes.executor import executor_node
        from ai_workflow_hub.nodes.tester import tester_node
        from ai_workflow_hub.nodes.fixer import fixer_node
        from ai_workflow_hub.nodes.finalizer import finalizer_node

        project = _copy_fixture(tmp_path)
        run_dir = str(tmp_path / "runs" / "e2e-fix")
        Path(run_dir).mkdir(parents=True, exist_ok=True)

        s = _base_state(
            str(project), run_dir,
            dry_run=False,
            apply_changes=True,
            run_tests=True,
            test_commands={"unit_test": "echo FIX_LOOP_TEST"},
            review_result="fail",
            review_summary="Test failed, need docstring.",
            next_fixes=["Add module docstring to src/main.py"],
            allowed_fix_files=["src/main.py"],
        )

        call_count = [0]
        test_call_count = [0]

        def fake_opencode_run(**kwargs):
            call_count[0] += 1
            return {**FAKE_OPECODE_RESULT,
                    "stdout": f"Mock call #{call_count[0]}"}

        # Mock tester subprocess: fail on first call, pass on second
        def fake_run_project_commands(commands, cwd, run_dir,
                                      command_names=None):
            test_call_count[0] += 1
            if test_call_count[0] == 1:
                return {"unit_test": {
                    "exit_code": 1, "stdout": "FAIL", "stderr": "",
                    "output_file": "",
                }}
            else:
                return {"unit_test": {
                    "exit_code": 0, "stdout": "PASS", "stderr": "",
                    "output_file": "",
                }}

        with patch(
            "ai_workflow_hub.opencode_client.opencode_run",
            side_effect=fake_opencode_run,
        ) as mock_oc, patch(
            "ai_workflow_hub.nodes.tester.run_project_commands",
            side_effect=fake_run_project_commands,
        ), patch(
            "ai_workflow_hub.nodes.executor.collect_all_diff_info",
            return_value=FAKE_DIFF,
        ), patch(
            "ai_workflow_hub.nodes.fixer.collect_all_diff_info",
            return_value={"diff_text": "fix diff\n",
                          "changed_files": ["src/main.py"],
                          "name_status": {"src/main.py": "M"},
                          "diff_line_count": 1},
        ), patch(
            "ai_workflow_hub.nodes.executor.save_diff_patch",
        ), patch(
            "ai_workflow_hub.nodes.fixer.save_diff_patch",
        ):
            # 1. human_gate
            s.update(human_gate_node(s))
            assert s.get("human_required") is not True

            # 2. executor (apply)
            s.update(executor_node(s))
            assert s.get("status") != "failed"

            # 3. tester (first run — fails)
            s.update(tester_node(s))
            assert s["test_exit_code"] != 0, \
                f"expected test fail, got exit={s['test_exit_code']}"

            # 4. fixer
            s["review_result"] = "fail"
            s.update(fixer_node(s))
            assert s["fix_round"] == 1

            # 5. tester (second run — passes)
            s.update(tester_node(s))
            assert s["test_exit_code"] == 0, \
                f"expected test pass after fix, got exit={s['test_exit_code']}"

            # 6. finalizer
            s["review_result"] = "pass"
            s.update(finalizer_node(s))

        assert mock_oc.call_count >= 2, \
            f"expected ≥2 opencode calls, got {mock_oc.call_count}"
        assert test_call_count[0] == 2, \
            f"expected 2 test runs, got {test_call_count[0]}"
        assert Path(run_dir, "execution-log.md").exists()
        assert Path(run_dir, "test-output.md").exists()
        assert Path(run_dir, "final-report.md").exists()
        assert s.get("status") == "passed", \
            f"final status={s.get('status')}"
