"""Hermetic end-to-end test: executing a go-run records real team events that
surface in the visual control plane read model. Uses a trivial cross-platform
command worker (no OpenCode, no tokens).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from jsonschema.validators import validator_for

from control_plane.go_dispatch import execute_go_run, run_go_dispatch
from control_plane.t3_adapter import build_t3_client_shell
from control_plane.team_runtime import TEAM_EVENTS_FILE, build_team_runtime_view
from control_plane.visual_state import build_visual_control_plane_state

REPO_ROOT = Path(__file__).resolve().parents[3]


def _validate_state(state: dict) -> None:
    schema = json.loads(
        (REPO_ROOT / "schemas/visual_control_plane_state.schema.json").read_text(encoding="utf-8-sig")
    )
    validator_class = validator_for(schema)
    validator_class.check_schema(schema)
    validator_class(schema).validate(state)


def _validate_t3_shell(shell: dict) -> None:
    schema = json.loads(
        (REPO_ROOT / "schemas/t3_client_shell.schema.json").read_text(encoding="utf-8-sig")
    )
    validator_class = validator_for(schema)
    validator_class.check_schema(schema)
    validator_class(schema).validate(shell)


def _noop_report_command() -> list[str]:
    # Writes a passing ExecutionReport to the path the worker provides via env.
    script = (
        "import os;"
        "open(os.environ['RDGOAL_REPORT_PATH'],'w',encoding='utf-8')"
        ".write('## ExecutionReport\\n\\n- **Status**: pass\\n- **Changed Files**:\\n- (none)\\n"
        "- **Evidence**: hermetic team-runtime test\\n')"
    )
    return [sys.executable, "-c", script]


def test_execution_records_team_events_and_surfaces_in_state(tmp_path):
    project = tmp_path / "proj"
    project.mkdir()
    (project / "a.py").write_text("a = 1\n", encoding="utf-8")
    (project / "b.py").write_text("b = 2\n", encoding="utf-8")
    runtime = tmp_path / "runtime"

    result = run_go_dispatch(
        project,
        "hermetic team runtime test",
        runtime_dir=runtime,
        agents=2,
        targets=["a.py", "b.py"],
        execute=True,
        worker_command=_noop_report_command(),
    )
    assert result.status in {"passed", "queued"}

    # Real team events were recorded during execution.
    assert (runtime / TEAM_EVENTS_FILE).exists()
    view = build_team_runtime_view(runtime)
    kinds = {e["kind"] for e in view["event_log"]}
    assert {"task-created", "task-claimed", "task-result", "evidence-ref"} <= kinds
    view_evidence = [e for e in view["evidence_store"] if e["evidence_id"].startswith("team-evidence-")]
    assert view_evidence
    assert {e["ref_type"] for e in view_evidence} == {"report"}
    context_evidence = [e for e in view["evidence_store"] if e["evidence_id"].startswith("team-context-")]
    assert {e["ref_type"] for e in context_evidence} == {"legacy_context", "legacy_task_spec"}
    event_types = [
        json.loads(line)["event_type"]
        for line in (runtime / TEAM_EVENTS_FILE).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert "evidence_ref" in event_types
    task_payloads = [
        json.loads(line)["payload"]
        for line in (runtime / TEAM_EVENTS_FILE).read_text(encoding="utf-8").splitlines()
        if line.strip() and json.loads(line)["event_type"] in {"task_created", "task_claimed"}
    ]
    assert task_payloads
    assert all(payload["context_refs"] for payload in task_payloads)

    # They surface in the control-plane read model's team objects.
    state = build_visual_control_plane_state(runtime_dir=runtime)
    # Full schema validation: the assembled state, including REAL recorded team
    # entries, must satisfy the visual control plane schema.
    _validate_state(state)
    team = state["team"]
    recorded_event_ids = {e["event_id"] for e in team["event_log"] if e["event_id"].startswith("team-")}
    assert recorded_event_ids, "recorded team events should appear in the read model"
    recorded_msg_kinds = {m["kind"] for m in team["message_bus"]}
    assert "task-assign" in recorded_msg_kinds
    assert "result" in recorded_msg_kinds
    report_refs = [e for e in team["evidence_store"] if e["ref_type"] == "report"]
    report_paths = [e["ref_path"] for e in report_refs]
    assert report_paths
    assert not [e for e in team["evidence_store"] if e["evidence_id"].startswith("team-evidence-")]
    shell = build_t3_client_shell(runtime_dir=runtime)
    _validate_t3_shell(shell)
    t3_report_refs = [
        e for e in shell["devframe"]["team"]["evidenceStore"]
        if e["refType"] == "report"
    ]
    assert {
        Path(e["refPath"]).name for e in t3_report_refs
    } >= {
        Path(e["ref_path"]).name for e in view_evidence
    }
    # Real Conflict Control: targets owned by their agents this run.
    owned_files = {c["file_path"] for c in team["conflict_control"]}
    assert {"a.py", "b.py"} <= owned_files
    # Real Review Gate: worker success is surfaced as review pending, not pass.
    recorded_gates = [g for g in team["review_gates"] if g["gate_id"].startswith("team-acceptance-")]
    assert recorded_gates, "recorded acceptance gates should appear in the read model"
    assert {g["status"] for g in recorded_gates} == {"open"}
    assert all("independent review is still required" in g["reason"] for g in recorded_gates)

    outcome_gates = [g for g in team["review_gates"] if g["kind"] == "go-run-outcome"]
    assert outcome_gates
    assert {g["status"] for g in outcome_gates} == {"open"}


def test_prepare_only_records_no_team_events(tmp_path):
    project = tmp_path / "proj"
    project.mkdir()
    (project / "a.py").write_text("a = 1\n", encoding="utf-8")
    runtime = tmp_path / "runtime"

    run_go_dispatch(
        project,
        "prepare only",
        runtime_dir=runtime,
        agents=1,
        targets=["a.py"],
        execute=False,
    )
    # No execution => no recorded team events => projection-only (unchanged).
    assert not (runtime / TEAM_EVENTS_FILE).exists()
    assert build_team_runtime_view(runtime) == {
        "message_bus": [],
        "event_log": [],
        "conflict_control": [],
        "review_gates": [],
        "agent_registry": [],
        "task_board": [],
        "evidence_store": [],
    }


def test_resume_prepared_go_run_records_explicit_team_evidence(tmp_path):
    project = tmp_path / "proj"
    project.mkdir()
    (project / "a.py").write_text("a = 1\n", encoding="utf-8")
    runtime = tmp_path / "runtime"

    prepared = run_go_dispatch(
        project,
        "prepare then resume",
        runtime_dir=runtime,
        agents=1,
        targets=["a.py"],
        execute=False,
        worker_command=_noop_report_command(),
    )
    assert not (runtime / TEAM_EVENTS_FILE).exists()

    executed = execute_go_run(runtime, prepared.go_run_id)

    assert executed.status in {"passed", "queued"}
    event_types = [
        json.loads(line)["event_type"]
        for line in (runtime / TEAM_EVENTS_FILE).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert "task_result" in event_types
    assert "evidence_ref" in event_types
    evidence = build_team_runtime_view(runtime)["evidence_store"]
    assert len([item for item in evidence if item["ref_type"] == "report"]) == 1
    assert {item["ref_type"] for item in evidence} == {"legacy_context", "legacy_task_spec", "report"}
