"""Hermetic end-to-end test: executing a go-run records real team events that
surface in the visual control plane read model. Uses a trivial cross-platform
command worker (no OpenCode, no tokens).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from jsonschema.validators import validator_for

from control_plane.go_dispatch import (
    SUCCESS_WORKER_STATUSES,
    execute_go_run,
    run_go_dispatch,
)
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


def _validate_runtime_context_artifacts(packet_dir: Path) -> None:
    context_packet = json.loads((packet_dir / "context-packet.json").read_text(encoding="utf-8"))
    context_ledger = json.loads((packet_dir / "context-ledger.json").read_text(encoding="utf-8"))
    for schema_name, payload in [
        ("context-packet.schema.json", context_packet),
        ("context-ledger.schema.json", context_ledger),
    ]:
        schema = json.loads(
            (REPO_ROOT / "schemas" / "runtime-governance" / schema_name).read_text(encoding="utf-8-sig")
        )
        validator_class = validator_for(schema)
        validator_class.check_schema(schema)
        validator_class(schema).validate(payload)
    assert context_packet["seal_state"] == "sealed"
    assert context_ledger["append_only"] is True


def _noop_report_command() -> list[str]:
    # Writes a passing ExecutionReport to the path the worker provides via env.
    script = (
        "import os;"
        "open(os.environ['RDGOAL_REPORT_PATH'],'w',encoding='utf-8')"
        ".write('## ExecutionReport\\n\\n- **Status**: pass\\n- **Changed Files**:\\n- (none)\\n"
        "- **Evidence**: hermetic team-runtime test\\n')"
    )
    return [sys.executable, "-c", script]


def _message_report_command(
    to_agent_id: str,
    *,
    kind: str = "handoff",
    summary: str = "Please review the result.",
) -> list[str]:
    script = (
        "import json,os;"
        "from pathlib import Path;"
        "packet=Path(os.environ['RDGOAL_PACKET_DIR']);"
        f"(packet/'team-message.json').write_text(json.dumps({{'to_agent_id':{to_agent_id!r},'kind':{kind!r},'summary':{summary!r}}}),encoding='utf-8');"
        "Path(os.environ['RDGOAL_REPORT_PATH']).write_text('## ExecutionReport\\n\\n- **Status**: pass\\n- **Changed Files**:\\n- (none)\\n- **Evidence**: hermetic message-route test\\n',encoding='utf-8')"
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
    assert {e["ref_type"] for e in context_evidence} == {
        "context_packet",
        "context_ledger",
        "legacy_context",
        "legacy_task_spec",
    }
    for agent in result.agents:
        packet_dir = Path(agent.packet_dir)
        _validate_runtime_context_artifacts(packet_dir)
        assert agent.context_packet_path == str(packet_dir / "context-packet.json")
        assert agent.context_ledger_path == str(packet_dir / "context-ledger.json")
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
    assert all(
        {"context_packet", "context_ledger"} <= {ref["ref_type"] for ref in payload["context_refs"]}
        for payload in task_payloads
    )

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
    assert {item["ref_type"] for item in evidence} == {
        "context_packet",
        "context_ledger",
        "legacy_context",
        "legacy_task_spec",
        "report",
    }
    _validate_runtime_context_artifacts(Path(executed.agents[0].packet_dir))


def test_overlapping_claim_in_real_execute_fails_second_agent(tmp_path):
    # Real-path regression: execute_go_run -> _execute_parallel ->
    # plan_write_set_groups -> _run_group -> _run_agent_in_place.
    # When agent 2's metadata is mutated to overlap agent 1's target,
    # the TeamRuntime claim guard rejects the second claim before append,
    # _run_agent_in_place catches the ValueError, marks the agent failed,
    # writes go-agent-error.txt, and records a failed task result without
    # invoking the worker.
    project = tmp_path / "proj"
    project.mkdir()
    (project / "a.py").write_text("a = 1\n", encoding="utf-8")
    (project / "b.py").write_text("b = 2\n", encoding="utf-8")
    runtime = tmp_path / "runtime"

    prepared = run_go_dispatch(
        project,
        "claim-propagation regression",
        runtime_dir=runtime,
        agents=2,
        targets=["a.py", "b.py"],
        execute=False,
        worker_command=_noop_report_command(),
    )
    assert not (runtime / TEAM_EVENTS_FILE).exists()

    # Drift agent 2's target to overlap agent 1's in the temporary metadata.
    metadata_path = Path(prepared.metadata_path)
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    metadata["agents"][1]["targets"] = list(metadata["agents"][0]["targets"])
    metadata_path.write_text(json.dumps(metadata, indent=2, ensure_ascii=True), encoding="utf-8")

    executed = execute_go_run(runtime, prepared.go_run_id)

    agent1, agent2 = executed.agents
    assert agent1.worker_status in SUCCESS_WORKER_STATUSES
    assert agent1.status == "completed"
    assert agent2.worker_status == "failed"
    assert agent2.status == "failed"

    events = [
        json.loads(line)
        for line in (runtime / TEAM_EVENTS_FILE).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    claim_events = [e for e in events if e["event_type"] == "task_claimed"]
    assert len(claim_events) == 1
    assert claim_events[0]["agent_id"] == agent1.agent_id

    result_events = [e for e in events if e["event_type"] == "task_result"]
    assert len(result_events) == 2
    results_by_agent = {e["agent_id"]: e["payload"]["status"] for e in result_events}
    assert results_by_agent[agent1.agent_id] in SUCCESS_WORKER_STATUSES
    assert results_by_agent[agent2.agent_id] == "failed"

    error_text = (Path(agent2.packet_dir) / "go-agent-error.txt").read_text(encoding="utf-8")
    assert "already claimed" in error_text
    assert agent1.targets[0] in error_text


def test_execute_go_run_records_explicit_worker_message_for_run_participant(tmp_path):
    project = tmp_path / "proj"
    project.mkdir()
    (project / "a.py").write_text("a = 1\n", encoding="utf-8")
    (project / "b.py").write_text("b = 2\n", encoding="utf-8")
    runtime = tmp_path / "runtime"

    prepared = run_go_dispatch(
        project,
        "explicit message route",
        runtime_dir=runtime,
        agents=2,
        targets=["a.py", "b.py"],
        execute=False,
        worker_command=_noop_report_command(),
    )
    metadata_path = Path(prepared.metadata_path)
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    metadata["agents"][0]["worker_command"] = _message_report_command("coding-agent-2")
    metadata_path.write_text(json.dumps(metadata, indent=2, ensure_ascii=True), encoding="utf-8")

    executed = execute_go_run(runtime, prepared.go_run_id)

    assert {agent.status for agent in executed.agents} == {"completed"}
    messages = [
        item
        for item in build_team_runtime_view(runtime)["message_bus"]
        if item["kind"] == "handoff"
    ]
    assert len(messages) == 1
    assert messages[0]["from_role"] == "coding-agent-1"
    assert messages[0]["to_role"] == "coding-agent-2"
    assert messages[0]["summary"] == "Please review the result."
    assert not (Path(executed.agents[0].packet_dir) / "team-message.json").exists()


def test_execute_go_run_discards_invalid_worker_message_without_failing_worker(tmp_path):
    project = tmp_path / "proj"
    project.mkdir()
    (project / "a.py").write_text("a = 1\n", encoding="utf-8")
    (project / "b.py").write_text("b = 2\n", encoding="utf-8")
    runtime = tmp_path / "runtime"

    prepared = run_go_dispatch(
        project,
        "invalid explicit message route",
        runtime_dir=runtime,
        agents=2,
        targets=["a.py", "b.py"],
        execute=False,
        worker_command=_noop_report_command(),
    )
    metadata_path = Path(prepared.metadata_path)
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    metadata["agents"][0]["worker_command"] = _message_report_command("not-in-this-run")
    metadata_path.write_text(json.dumps(metadata, indent=2, ensure_ascii=True), encoding="utf-8")

    executed = execute_go_run(runtime, prepared.go_run_id)

    assert {agent.status for agent in executed.agents} == {"completed"}
    assert not [
        item
        for item in build_team_runtime_view(runtime)["message_bus"]
        if item["kind"] in {"handoff", "note", "review-request"}
    ]
