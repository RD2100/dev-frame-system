"""Hermetic tests for the M3 workflow engine.

Drives a real plan -> execute -> review workflow with a trivial cross-platform
no-op command worker (no OpenCode, no tokens) and verifies that phases and the
controller verdict are recorded as real team events and surface in the read
model.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from jsonschema.validators import validator_for

from control_plane.team_runtime import TEAM_EVENTS_FILE, build_team_runtime_view
from control_plane.visual_state import build_visual_control_plane_state
from control_plane.workflow_engine import (
    VERDICT_AWAITING_REVIEW,
    VERDICT_REVISE,
    WorkflowEngine,
)

REPO_ROOT = Path(__file__).resolve().parents[3]


def _pass_command() -> list[str]:
    script = (
        "import os;"
        "open(os.environ['RDGOAL_REPORT_PATH'],'w',encoding='utf-8')"
        ".write('## ExecutionReport\\n\\n- **Status**: pass\\n- **Changed Files**:\\n- (none)\\n"
        "- **Evidence**: workflow test\\n')"
    )
    return [sys.executable, "-c", script]


def _fail_command() -> list[str]:
    # Exits non-zero and writes no passing report -> worker status failed.
    return [sys.executable, "-c", "import sys; sys.exit(3)"]


def _validate_state(state: dict) -> None:
    schema = json.loads(
        (REPO_ROOT / "schemas/visual_control_plane_state.schema.json").read_text(encoding="utf-8-sig")
    )
    validator_class = validator_for(schema)
    validator_class.check_schema(schema)
    validator_class(schema).validate(state)


def _project(tmp_path: Path) -> Path:
    project = tmp_path / "proj"
    project.mkdir()
    (project / "a.py").write_text("a = 1\n", encoding="utf-8")
    (project / "b.py").write_text("b = 2\n", encoding="utf-8")
    return project


def test_workflow_runs_phases_and_awaits_review_on_all_pass(tmp_path):
    runtime = tmp_path / "runtime"
    engine = WorkflowEngine(runtime_dir=runtime)
    result = engine.run_coding_workflow(
        _project(tmp_path),
        "hermetic workflow goal",
        agents=2,
        targets=["a.py", "b.py"],
        worker_command=_pass_command(),
    )

    phase_names = [p.name for p in result.phases]
    assert phase_names == ["plan", "execute", "review"]
    assert result.verdict == VERDICT_AWAITING_REVIEW
    assert result.passed_agents == 2
    assert result.failed_agents == 0
    assert result.phases[-1].role == "controller"
    assert "independent review is required" in result.phases[-1].summary

    # Phases recorded as real team events.
    view = build_team_runtime_view(runtime)
    workflow_kinds = {e["kind"] for e in view["event_log"] if e["kind"].startswith("workflow-")}
    assert {"workflow-plan", "workflow-execute", "workflow-review"} <= workflow_kinds
    # The verdict is broadcast to the team.
    verdict_msgs = [m for m in view["message_bus"] if m["kind"] == "workflow-verdict"]
    assert verdict_msgs
    assert verdict_msgs[-1]["from_role"] == "controller"
    assert "independent review is required" in verdict_msgs[-1]["summary"]


def test_workflow_revises_on_failure(tmp_path):
    runtime = tmp_path / "runtime"
    engine = WorkflowEngine(runtime_dir=runtime)
    result = engine.run_coding_workflow(
        _project(tmp_path),
        "failing workflow goal",
        agents=1,
        targets=["a.py"],
        worker_command=_fail_command(),
    )
    assert result.verdict == VERDICT_REVISE
    assert result.failed_agents >= 1


def test_workflow_events_surface_in_read_model_and_validate(tmp_path):
    runtime = tmp_path / "runtime"
    engine = WorkflowEngine(runtime_dir=runtime)
    engine.run_coding_workflow(
        _project(tmp_path),
        "surface workflow goal",
        agents=2,
        targets=["a.py", "b.py"],
        worker_command=_pass_command(),
    )
    assert (runtime / TEAM_EVENTS_FILE).exists()
    state = build_visual_control_plane_state(runtime_dir=runtime)
    _validate_state(state)
    event_kinds = {e["kind"] for e in state["team"]["event_log"]}
    assert "workflow-review" in event_kinds


def test_workflow_rejects_unknown_driver(tmp_path):
    import pytest

    engine = WorkflowEngine(runtime_dir=tmp_path / "runtime")
    with pytest.raises(ValueError, match="unknown driver"):
        engine.run_coding_workflow(_project(tmp_path), "goal", driver="bogus", worker_command=_pass_command())


def test_workflow_records_driver_in_start_event(tmp_path):
    runtime = tmp_path / "runtime"
    engine = WorkflowEngine(runtime_dir=runtime)
    engine.run_coding_workflow(
        _project(tmp_path),
        "driver-recorded goal",
        agents=1,
        targets=["a.py"],
        worker_command=_pass_command(),
        driver="command",
    )
    starts = [
        json.loads(line)
        for line in (runtime / TEAM_EVENTS_FILE).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    start_summaries = [r["payload"]["summary"] for r in starts if r.get("event_type") == "workflow_event" and r["payload"].get("phase") == "start"]
    assert any("driver=command" in s for s in start_summaries)


def test_workflow_preserves_authoritative_project_id_in_go_and_team_runtime(tmp_path):
    runtime = tmp_path / "runtime"
    project = _project(tmp_path)
    engine = WorkflowEngine(runtime_dir=runtime)

    result = engine.run_coding_workflow(
        project,
        "authoritative project identity workflow",
        project_id="registered-project-id",
        agents=2,
        targets=["a.py", "b.py"],
        worker_command=_pass_command(),
    )

    assert result.project_id == "registered-project-id"
    go_run = json.loads(
        (runtime / "go-runs" / result.go_run_id / "go-run.json").read_text(
            encoding="utf-8"
        )
    )
    assert go_run["project_id"] == "registered-project-id"
    events = [
        json.loads(line)
        for line in (runtime / TEAM_EVENTS_FILE).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    task_events = [event for event in events if event["event_type"] == "task_created"]
    assert len(task_events) == 2
    assert {event["payload"]["project_id"] for event in task_events} == {
        "registered-project-id"
    }
