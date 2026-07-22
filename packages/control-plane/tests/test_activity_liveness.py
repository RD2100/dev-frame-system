from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema.validators import validator_for

from control_plane.governance_events import RootGateLifecycleError
from control_plane.activity_liveness import build_activity_liveness
from control_plane.team_runtime import TEAM_EVENTS_FILE, TeamRuntime, build_team_runtime_view
from control_plane.visual_state import build_visual_control_plane_state


REPO_ROOT = Path(__file__).resolve().parents[3]
REQUEST_ID = "root-gate-activity-liveness"
REQUEST_DEDUPE_KEY = "dev-frame-system/activity-liveness"


def _request_root_gate(team: TeamRuntime) -> None:
    team.record_root_gate_request(
        "run-activity-liveness",
        "project-controller",
        request_id=REQUEST_ID,
        dedupe_key=REQUEST_DEDUPE_KEY,
        project_id="dev-frame-system",
        gate="P1",
        summary="A READY slice needs a root-owned dispatch.",
        exact_write_set=["packages/control-plane/control_plane/activity_liveness.py"],
        evidence_refs=["evidence/activity-liveness-red.json"],
        reason="No active child currently owns this gated READY slice.",
    )


def _activity(runtime_dir: Path) -> dict:
    state = build_visual_control_plane_state(runtime_dir=runtime_dir)
    schema = json.loads(
        (REPO_ROOT / "schemas" / "visual_control_plane_state.schema.json").read_text(
            encoding="utf-8-sig"
        )
    )
    validator_class = validator_for(schema)
    validator_class.check_schema(schema)
    validator_class(schema).validate(state)
    return state["team"]["activity_liveness"]


def _write_action_run(
    runtime_dir: Path,
    *,
    action_id: str,
    directory_id: str,
    action_run_id: str,
    status: str,
    run_id: str,
) -> Path:
    record_path = runtime_dir / "action-runs" / action_id / directory_id / "action-run.json"
    record_path.parent.mkdir(parents=True)
    record_path.write_text(
        json.dumps({
            "action_id": action_id,
            "action_run_id": action_run_id,
            "status": status,
            "run_id": run_id,
            "go_run_id": run_id,
            "kind": "go_execute",
            "command": f"devframe go execute {run_id}",
            "created_at": "2026-07-22T00:00:00+00:00",
            "completed_at": (
                "2026-07-22T00:01:00+00:00" if status == "completed" else ""
            ),
        }),
        encoding="utf-8",
    )
    return record_path


def test_real_root_gate_lifecycle_projects_deterministic_starvation_and_clears_on_progress(
    tmp_path,
):
    team = TeamRuntime(runtime_dir=tmp_path)
    _request_root_gate(team)
    journal = tmp_path / TEAM_EVENTS_FILE
    before_reads = journal.read_bytes()

    requested = _activity(tmp_path)
    duplicate_read = _activity(tmp_path)

    assert duplicate_read == requested
    assert journal.read_bytes() == before_reads
    assert requested["state"] == "gated_ready"
    assert requested["counts"]["active_workers"] == 0
    assert requested["counts"]["ready"] == 0
    assert requested["counts"]["gated_ready"] == 1
    assert requested["wake_required"] is True
    assert requested["dedupe_key"]
    assert requested["gated_ready"][0]["dedupe_key"] == REQUEST_DEDUPE_KEY

    team.record_root_gate_acknowledgement(
        REQUEST_ID,
        "root-controller",
        reason="The root controller is handling the request.",
    )
    acknowledged = _activity(tmp_path)
    assert acknowledged["counts"]["gated_ready"] == 0
    assert acknowledged["counts"]["ready"] == 0
    assert acknowledged["wake_required"] is False
    assert acknowledged["dedupe_key"] == ""

    team.record_root_gate_decision(
        REQUEST_ID,
        "root-controller",
        decision="authorized",
        reason="The bounded slice is authorized.",
    )
    authorized = _activity(tmp_path)
    assert authorized["state"] == "ready"
    assert authorized["counts"]["ready"] == 1
    assert authorized["counts"]["gated_ready"] == 0
    assert authorized["ready"][0]["work_id"] == REQUEST_ID
    assert authorized["wake_required"] is False

    team.record_root_gate_dispatch(
        REQUEST_ID,
        "root-controller",
        task_ids=["activity-liveness-writer"],
        reason="The authorized writer is now dispatched.",
    )
    dispatched = _activity(tmp_path)
    assert dispatched["state"] == "active"
    assert dispatched["counts"]["ready"] == 0
    assert dispatched["counts"]["gated_ready"] == 0
    assert dispatched["counts"]["active_workers"] == 1
    assert dispatched["internal_workers"][0]["worker_id"] == "activity-liveness-writer"
    assert dispatched["internal_workers"][0]["status"] == "dispatched"
    assert dispatched["wake_required"] is False


def test_live_claimed_child_prevents_false_idle_without_claiming_wake_delivery(tmp_path):
    team = TeamRuntime(runtime_dir=tmp_path)
    _request_root_gate(team)
    team.record_task_created(
        "run-activity-liveness",
        "live-child",
        project_id="dev-frame-system",
        shard_index=1,
        shard_count=1,
        targets=["packages/control-plane/control_plane/activity_liveness.py"],
    )
    team.record_task_claimed("run-activity-liveness", "live-child")
    before_reads = (tmp_path / TEAM_EVENTS_FILE).read_bytes()

    active = _activity(tmp_path)

    assert active["state"] == "active"
    assert active["counts"]["active_workers"] == 1
    assert active["counts"]["gated_ready"] == 1
    assert active["wake_required"] is False
    assert active["dedupe_key"] == ""
    assert any(
        worker["worker_id"] == "live-child" and worker["status"] == "working"
        for worker in active["internal_workers"]
    )
    assert (tmp_path / TEAM_EVENTS_FILE).read_bytes() == before_reads
    assert not any(
        "wake" in str(item.get("kind") or "").lower()
        for key in ("message_bus", "event_log")
        for item in build_visual_control_plane_state(tmp_path)["team"][key]
    )

    team.record_result("run-activity-liveness", "live-child", status="completed")
    terminal = _activity(tmp_path)
    assert terminal["counts"]["active_workers"] == 0
    assert terminal["wake_required"] is True


def test_owned_running_command_prevents_false_idle_until_it_is_terminal(tmp_path):
    team = TeamRuntime(runtime_dir=tmp_path)
    _request_root_gate(team)
    record_path = tmp_path / "action-runs" / "owned-command" / "run-1" / "action-run.json"
    record_path.parent.mkdir(parents=True)
    record = {
        "action_id": "owned-command",
        "action_run_id": "run-1",
        "status": "started",
        "run_id": "command-owner-run",
        "go_run_id": "command-owner-run",
        "kind": "go_execute",
        "command": "devframe go execute command-owner-run",
    }
    record_path.write_text(json.dumps(record), encoding="utf-8")

    running = _activity(tmp_path)

    assert running["state"] == "active"
    assert running["counts"]["active_workers"] == 1
    assert running["counts"]["owned_commands"] == 1
    assert running["owned_commands"] == [
        {
            "command_id": "owned-command/run-1",
            "owner_id": "command-owner-run",
            "run_id": "command-owner-run",
            "kind": "go_execute",
            "status": "started",
        }
    ]
    assert running["wake_required"] is False

    record["status"] = "completed"
    record_path.write_text(json.dumps(record), encoding="utf-8")
    completed = _activity(tmp_path)
    assert completed["counts"]["active_workers"] == 0
    assert completed["counts"]["owned_commands"] == 0
    assert completed["wake_required"] is True


def test_action_run_history_keeps_a_live_instance_when_another_run_is_terminal(tmp_path):
    team = TeamRuntime(runtime_dir=tmp_path)
    _request_root_gate(team)
    _write_action_run(
        tmp_path,
        action_id="repeatable-action",
        directory_id="001-terminal-started-snapshot",
        action_run_id="run-terminal",
        status="started",
        run_id="terminal-owner",
    )
    _write_action_run(
        tmp_path,
        action_id="repeatable-action",
        directory_id="002-live-run",
        action_run_id="run-live",
        status="started",
        run_id="live-owner",
    )
    _write_action_run(
        tmp_path,
        action_id="repeatable-action",
        directory_id="003-terminal-completed-snapshot",
        action_run_id="run-terminal",
        status="completed",
        run_id="terminal-owner",
    )

    activity = _activity(tmp_path)

    assert activity["state"] == "active"
    assert activity["counts"]["active_workers"] == 1
    assert activity["counts"]["owned_commands"] == 1
    assert activity["owned_commands"] == [
        {
            "command_id": "repeatable-action/run-live",
            "owner_id": "live-owner",
            "run_id": "live-owner",
            "kind": "go_execute",
            "status": "started",
        }
    ]
    assert activity["wake_required"] is False


def test_active_controller_status_is_recorded_independently_without_children(tmp_path):
    team = TeamRuntime(runtime_dir=tmp_path)
    team.record_workflow_event(
        "run-controller-only",
        phase="plan",
        status="started",
        role="controller",
        summary="Controller is actively planning without a child worker.",
    )

    activity = build_activity_liveness(
        str(tmp_path),
        recorded_team=build_team_runtime_view(tmp_path),
        visible_agents=[],
        visible_sessions=[],
    )

    assert activity["state"] == "idle"
    assert activity["counts"]["active_workers"] == 0
    assert activity["controller"] == {
        "worker_id": "controller",
        "status": "active",
        "child_worker_ids": [],
    }


def test_idle_controller_status_does_not_follow_a_live_child(tmp_path):
    team = TeamRuntime(runtime_dir=tmp_path)
    team.record_task_created(
        "run-live-child",
        "live-child",
        project_id="dev-frame-system",
        targets=["packages/control-plane/control_plane/activity_liveness.py"],
    )
    team.record_task_claimed("run-live-child", "live-child")

    activity = build_activity_liveness(
        str(tmp_path),
        recorded_team=build_team_runtime_view(tmp_path),
        visible_agents=[],
        visible_sessions=[],
    )

    assert activity["state"] == "active"
    assert activity["counts"]["active_workers"] == 1
    assert activity["controller"] == {
        "worker_id": "controller",
        "status": "idle",
        "child_worker_ids": ["live-child"],
    }


def test_rejected_root_gate_clears_gated_ready_without_dispatching_a_worker(tmp_path):
    team = TeamRuntime(runtime_dir=tmp_path)
    _request_root_gate(team)
    team.record_root_gate_acknowledgement(
        REQUEST_ID,
        "root-controller",
        reason="The root controller received the request.",
    )
    team.record_root_gate_decision(
        REQUEST_ID,
        "root-controller",
        decision="rejected",
        reason="The proposed slice is not authorized.",
    )

    rejected = _activity(tmp_path)

    assert rejected["state"] == "idle"
    assert rejected["counts"]["ready"] == 0
    assert rejected["counts"]["gated_ready"] == 0
    assert rejected["counts"]["active_workers"] == 0
    assert rejected["internal_workers"] == []
    assert rejected["wake_required"] is False
    assert rejected["dedupe_key"] == ""


def test_visual_schema_keeps_legacy_team_snapshots_without_liveness_valid(tmp_path):
    state = build_visual_control_plane_state(runtime_dir=tmp_path)
    state["team"].pop("activity_liveness")
    schema = json.loads(
        (REPO_ROOT / "schemas" / "visual_control_plane_state.schema.json").read_text(
            encoding="utf-8-sig"
        )
    )
    validator_class = validator_for(schema)
    validator_class.check_schema(schema)
    validator_class(schema).validate(state)


def test_malformed_root_gate_journal_fails_closed_before_reporting_idle(tmp_path):
    team = TeamRuntime(runtime_dir=tmp_path)
    _request_root_gate(team)
    with (tmp_path / TEAM_EVENTS_FILE).open("ab") as handle:
        handle.write(b'{"event_type":"root_gate_event","payload":{"action":"requested"')

    with pytest.raises(RootGateLifecycleError, match="malformed TeamRuntime journal"):
        build_visual_control_plane_state(runtime_dir=tmp_path)
