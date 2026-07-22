from __future__ import annotations

import json
from pathlib import Path
from typing import Callable

import pytest
from jsonschema.validators import validator_for

from control_plane.governance_events import RootGateLifecycleError
from control_plane.team_runtime import TEAM_EVENTS_FILE, TeamRuntime


REPO_ROOT = Path(__file__).resolve().parents[3]
REQUEST_ID = "root-gate-request-1"
REQUEST_KWARGS = {
    "request_id": REQUEST_ID,
    "dedupe_key": "devframe/m10b-core-safety",
    "project_id": "dev-frame-system",
    "gate": "P1",
    "summary": "Authorize the bounded core-safety repair.",
    "exact_write_set": ["control_plane/go_dispatch.py", "tests/test_workflow_profiles.py"],
    "evidence_refs": ["evidence/m10b-review.json"],
    "reason": "Independent review found a root-gated safety repair.",
}


def _audit_validator():
    schema = json.loads(
        (REPO_ROOT / "schemas" / "agent-runtime" / "audit-event.schema.json").read_text(
            encoding="utf-8-sig"
        )
    )
    validator_class = validator_for(schema)
    validator_class.check_schema(schema)
    return validator_class(schema)


def test_audit_schema_keeps_existing_examples_valid():
    schema = json.loads(
        (REPO_ROOT / "schemas" / "agent-runtime" / "audit-event.schema.json").read_text(
            encoding="utf-8-sig"
        )
    )
    validator = _audit_validator()
    for example in schema.get("examples", []):
        validator.validate(example)


def _journal_bytes(runtime_dir: Path) -> bytes:
    return (runtime_dir / TEAM_EVENTS_FILE).read_bytes()


def _root_gate_records(runtime_dir: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in (runtime_dir / TEAM_EVENTS_FILE).read_text(encoding="utf-8").splitlines()
        if json.loads(line).get("event_type") == "root_gate_event"
    ]


def _request(team: TeamRuntime, **overrides) -> str:
    kwargs = dict(REQUEST_KWARGS)
    kwargs.update(overrides)
    return team.record_root_gate_request("go-run-m10b", "project-controller", **kwargs)


def _assert_rejected_without_mutation(
    runtime_dir: Path,
    operation: Callable[[], object],
    match: str,
) -> None:
    before = _journal_bytes(runtime_dir)
    with pytest.raises(RootGateLifecycleError, match=match):
        operation()
    assert _journal_bytes(runtime_dir) == before


def test_root_gate_lifecycle_survives_restart_and_persists_schema_valid_events(tmp_path):
    request_event_id = _request(TeamRuntime(runtime_dir=tmp_path))

    restarted = TeamRuntime(runtime_dir=tmp_path)
    requested = restarted.read_root_gate_requests()[REQUEST_ID]
    assert requested["state"] == "requested"
    assert requested["request"]["exact_write_set"] == REQUEST_KWARGS["exact_write_set"]

    restarted.record_root_gate_acknowledgement(
        REQUEST_ID,
        "root-controller",
        reason="The root controller received the request.",
    )
    restarted.record_root_gate_decision(
        REQUEST_ID,
        "root-controller",
        decision="authorized",
        reason="The bounded write set is authorized.",
    )
    restarted.record_root_gate_dispatch(
        REQUEST_ID,
        "root-controller",
        task_ids=["task-m10b-writer"],
        reason="The authorized writer was dispatched.",
    )

    final = TeamRuntime(runtime_dir=tmp_path).read_root_gate_requests()[REQUEST_ID]
    assert final["state"] == "dispatched"
    assert final["decision"] == "authorized"
    assert final["dispatch_task_ids"] == ["task-m10b-writer"]
    assert all(
        final[field]
        for field in ("created_at", "root_ack_at", "decision_at", "dispatch_at")
    )
    assert final["event_ids"][0] == request_event_id

    records = _root_gate_records(tmp_path)
    assert [record["payload"]["action"] for record in records] == [
        "requested",
        "acknowledged",
        "authorized",
        "dispatched",
    ]
    assert [record["payload"]["after_state"] for record in records] == [
        "requested",
        "acknowledged",
        "authorized",
        "dispatched",
    ]
    validator = _audit_validator()
    for record in records:
        assert record["event_id"] == record["payload"]["event_id"]
        assert record["timestamp"] == record["payload"]["timestamp"]
        validator.validate(record["payload"])


def test_exact_duplicate_request_is_idempotent_after_restart(tmp_path):
    first_event_id = _request(TeamRuntime(runtime_dir=tmp_path))
    before = _journal_bytes(tmp_path)

    duplicate_event_id = _request(TeamRuntime(runtime_dir=tmp_path))

    assert duplicate_event_id == first_event_id
    assert _journal_bytes(tmp_path) == before
    assert len(_root_gate_records(tmp_path)) == 1


def test_truncated_root_gate_line_blocks_reads_and_transitions_without_mutation(tmp_path):
    team = TeamRuntime(runtime_dir=tmp_path)
    _request(team)
    team.record_root_gate_acknowledgement(
        REQUEST_ID,
        "root-controller",
        reason="The request was received.",
    )
    journal = tmp_path / TEAM_EVENTS_FILE
    with journal.open("ab") as handle:
        handle.write(
            b'{"event_type":"root_gate_event","run_id":"go-run-m10b",'
            b'"payload":{"action":"authorized"'
        )
    before = journal.read_bytes()
    restarted = TeamRuntime(runtime_dir=tmp_path)

    operations = [
        restarted.read_root_gate_requests,
        lambda: restarted.record_root_gate_decision(
            REQUEST_ID,
            "root-controller",
            decision="authorized",
            reason="A malformed journal must block this decision.",
        ),
        lambda: restarted.record_root_gate_dispatch(
            REQUEST_ID,
            "root-controller",
            task_ids=["task-must-not-be-recorded"],
            reason="A malformed journal must block this dispatch.",
        ),
    ]
    for operation in operations:
        with pytest.raises(RootGateLifecycleError, match="malformed TeamRuntime journal"):
            operation()
        assert journal.read_bytes() == before


def test_conflicting_duplicate_dedupe_key_is_rejected_without_journal_mutation(tmp_path):
    _request(TeamRuntime(runtime_dir=tmp_path))
    restarted = TeamRuntime(runtime_dir=tmp_path)

    _assert_rejected_without_mutation(
        tmp_path,
        lambda: _request(
            restarted,
            request_id="root-gate-request-conflict",
            summary="A materially different request using the same dedupe key.",
        ),
        "dedupe key",
    )


def test_decision_before_acknowledgement_is_rejected_without_journal_mutation(tmp_path):
    _request(TeamRuntime(runtime_dir=tmp_path))
    restarted = TeamRuntime(runtime_dir=tmp_path)

    _assert_rejected_without_mutation(
        tmp_path,
        lambda: restarted.record_root_gate_decision(
            REQUEST_ID,
            "root-controller",
            decision="authorized",
            reason="This transition is too early.",
        ),
        "requires state acknowledged",
    )


def test_dispatch_before_authorization_is_rejected_without_journal_mutation(tmp_path):
    team = TeamRuntime(runtime_dir=tmp_path)
    _request(team)
    team.record_root_gate_acknowledgement(
        REQUEST_ID,
        "root-controller",
        reason="The request was received.",
    )

    _assert_rejected_without_mutation(
        tmp_path,
        lambda: team.record_root_gate_dispatch(
            REQUEST_ID,
            "root-controller",
            task_ids=["task-too-early"],
            reason="This transition is too early.",
        ),
        "requires state authorized",
    )


@pytest.mark.parametrize(
    "operation",
    [
        lambda team: team.record_root_gate_acknowledgement(
            "unknown-request",
            "root-controller",
            reason="Unknown request.",
        ),
        lambda team: team.record_root_gate_decision(
            "unknown-request",
            "root-controller",
            decision="rejected",
            reason="Unknown request.",
        ),
        lambda team: team.record_root_gate_dispatch(
            "unknown-request",
            "root-controller",
            task_ids=["task-unknown"],
            reason="Unknown request.",
        ),
    ],
)
def test_unknown_request_id_fails_closed_without_creating_a_journal(tmp_path, operation):
    with pytest.raises(RootGateLifecycleError, match="Unknown root-gate request"):
        operation(TeamRuntime(runtime_dir=tmp_path))
    assert not (tmp_path / TEAM_EVENTS_FILE).exists()


def test_rejected_request_cannot_be_dispatched(tmp_path):
    team = TeamRuntime(runtime_dir=tmp_path)
    _request(team)
    team.record_root_gate_acknowledgement(
        REQUEST_ID,
        "root-controller",
        reason="The request was received.",
    )
    team.record_root_gate_decision(
        REQUEST_ID,
        "root-controller",
        decision="rejected",
        reason="The requested scope is not authorized.",
    )

    _assert_rejected_without_mutation(
        tmp_path,
        lambda: team.record_root_gate_dispatch(
            REQUEST_ID,
            "root-controller",
            task_ids=["task-rejected"],
            reason="Rejected work cannot be dispatched.",
        ),
        "requires state authorized",
    )
