from __future__ import annotations

import hashlib
import json
import threading
from datetime import datetime
from pathlib import Path
from typing import Callable

import pytest
from jsonschema import FormatChecker
from jsonschema.exceptions import ValidationError
from jsonschema.validators import validator_for

from control_plane.governance_events import (
    ConcurrentSliceAllowlistError,
    RootGateLifecycleError,
)
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
REVIEWER_TASK_ID = "task-concurrent-reviewer"
WRITER_TASK_ID = "task-concurrent-writer"
BASELINE_MANIFEST_HASH = (
    "b1e6983a7368eb982f3a5c46a68ab3a1b5b252ff19b2c5f8fd9633607576865f"
)
ALLOWLIST_BASELINE_KWARGS = {
    "reviewer_task_id": REVIEWER_TASK_ID,
    "dedupe_key": "devframe/concurrent-reviewer/baseline/v1",
    "checkout_identity": "dev-frame-system:codex/concurrent-allowlist@1b9eb988",
    "exact_repo_paths": [],
    "baseline_manifest": "exact-write-set:df-concurrent-allowlist-event-b1",
    "baseline_hash": BASELINE_MANIFEST_HASH,
    "version": 1,
    "reason": "Register the running zero-write reviewer before adding a writer.",
}
ALLOWLIST_DELTA_KWARGS = {
    "reviewer_task_id": REVIEWER_TASK_ID,
    "writer_task_id": WRITER_TASK_ID,
    "dedupe_key": "devframe/concurrent-reviewer/writer/v2",
    "checkout_identity": ALLOWLIST_BASELINE_KWARGS["checkout_identity"],
    "exact_repo_paths": [
        "packages/control-plane/control_plane/governance_events.py",
        "packages/control-plane/tests/test_governance_events.py",
    ],
    "baseline_manifest": ALLOWLIST_BASELINE_KWARGS["baseline_manifest"],
    "baseline_hash": BASELINE_MANIFEST_HASH,
    "previous_version": 1,
    "new_version": 2,
    "delivered_at": "2026-07-22T01:00:00+00:00",
    "first_file_change_at": "2026-07-22T01:00:01+00:00",
    "reason": "Authorize the disjoint writer before its first file change.",
}


def _audit_validator():
    schema = json.loads(
        (REPO_ROOT / "schemas" / "agent-runtime" / "audit-event.schema.json").read_text(
            encoding="utf-8-sig"
        )
    )
    validator_class = validator_for(schema)
    validator_class.check_schema(schema)
    format_checker = FormatChecker()

    @format_checker.checks("date-time", raises=(TypeError, ValueError))
    def is_iso8601_datetime(value):
        if not isinstance(value, str) or "T" not in value:
            return False
        moment = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return moment.tzinfo is not None and moment.utcoffset() is not None

    return validator_class(schema, format_checker=format_checker)


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


def _allowlist_records(runtime_dir: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in (runtime_dir / TEAM_EVENTS_FILE).read_text(encoding="utf-8").splitlines()
        if json.loads(line).get("event_type") == "concurrent_slice_allowlist_event"
    ]


def _request(team: TeamRuntime, **overrides) -> str:
    kwargs = dict(REQUEST_KWARGS)
    kwargs.update(overrides)
    return team.record_root_gate_request("go-run-m10b", "project-controller", **kwargs)


def _register_allowlist(team: TeamRuntime, **overrides) -> str:
    kwargs = dict(ALLOWLIST_BASELINE_KWARGS)
    kwargs.update(overrides)
    return team.record_concurrent_slice_allowlist_baseline(
        "go-run-concurrent-allowlist",
        "project-controller",
        **kwargs,
    )


def _append_allowlist_delta(team: TeamRuntime, **overrides) -> str:
    kwargs = dict(ALLOWLIST_DELTA_KWARGS)
    kwargs.update(overrides)
    return team.record_concurrent_slice_allowlist_delta(
        "project-controller",
        **kwargs,
    )


def _assert_rejected_without_mutation(
    runtime_dir: Path,
    operation: Callable[[], object],
    match: str,
) -> None:
    before = _journal_bytes(runtime_dir)
    with pytest.raises(RootGateLifecycleError, match=match):
        operation()
    assert _journal_bytes(runtime_dir) == before


def _assert_allowlist_rejected_without_mutation(
    runtime_dir: Path,
    operation: Callable[[], object],
    match: str,
) -> None:
    before = _journal_bytes(runtime_dir)
    with pytest.raises(ConcurrentSliceAllowlistError, match=match):
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


def test_concurrent_allowlist_delta_survives_restart_with_schema_valid_provenance(
    tmp_path,
):
    baseline_event_id = _register_allowlist(TeamRuntime(runtime_dir=tmp_path))

    registered = TeamRuntime(runtime_dir=tmp_path).read_concurrent_slice_allowlists()[
        REVIEWER_TASK_ID
    ]
    assert registered["version"] == 1
    assert registered["allowed_paths_by_task"] == {REVIEWER_TASK_ID: []}
    assert WRITER_TASK_ID not in registered["allowed_paths_by_task"]
    assert registered["allowed_concurrent_paths"] == []

    delta_event_id = _append_allowlist_delta(TeamRuntime(runtime_dir=tmp_path))

    restarted = TeamRuntime(runtime_dir=tmp_path).read_concurrent_slice_allowlists()[
        REVIEWER_TASK_ID
    ]
    assert restarted["version"] == 2
    assert restarted["checkout_identity"] == ALLOWLIST_BASELINE_KWARGS["checkout_identity"]
    assert restarted["baseline_manifest"] == ALLOWLIST_BASELINE_KWARGS["baseline_manifest"]
    assert restarted["baseline_hash"] == BASELINE_MANIFEST_HASH
    assert restarted["allowed_paths_by_task"] == {
        REVIEWER_TASK_ID: [],
        WRITER_TASK_ID: ALLOWLIST_DELTA_KWARGS["exact_repo_paths"],
    }
    assert restarted["allowed_concurrent_paths"] == ALLOWLIST_DELTA_KWARGS[
        "exact_repo_paths"
    ]
    assert restarted["event_ids"] == [baseline_event_id, delta_event_id]
    assert [item["kind"] for item in restarted["provenance"]] == ["baseline", "delta"]
    assert restarted["provenance"][1] == {
        "kind": "delta",
        "event_id": delta_event_id,
        "run_id": "go-run-concurrent-allowlist",
        "timestamp": restarted["provenance"][1]["timestamp"],
        "actor": "project-controller",
        "dedupe_key": ALLOWLIST_DELTA_KWARGS["dedupe_key"],
        "allowlist_hash": restarted["provenance"][1]["allowlist_hash"],
        "writer_task_id": WRITER_TASK_ID,
        "exact_repo_paths": ALLOWLIST_DELTA_KWARGS["exact_repo_paths"],
        "previous_version": 1,
        "new_version": 2,
        "delivered_at": ALLOWLIST_DELTA_KWARGS["delivered_at"],
        "first_file_change_at": ALLOWLIST_DELTA_KWARGS["first_file_change_at"],
    }
    assert len(restarted["provenance"][1]["allowlist_hash"]) == 64

    records = _allowlist_records(tmp_path)
    assert [record["payload"]["subject_type"] for record in records] == [
        "ConcurrentSliceAllowlist",
        "ConcurrentSliceAllowlistDelta",
    ]
    validator = _audit_validator()
    for record in records:
        assert record["event_id"] == record["payload"]["event_id"]
        assert record["timestamp"] == record["payload"]["timestamp"]
        validator.validate(record["payload"])


def test_exact_duplicate_allowlist_events_are_idempotent_after_restart(tmp_path):
    baseline_event_id = _register_allowlist(TeamRuntime(runtime_dir=tmp_path))
    baseline_bytes = _journal_bytes(tmp_path)
    assert _register_allowlist(TeamRuntime(runtime_dir=tmp_path)) == baseline_event_id
    assert _journal_bytes(tmp_path) == baseline_bytes

    delta_event_id = _append_allowlist_delta(TeamRuntime(runtime_dir=tmp_path))
    delta_bytes = _journal_bytes(tmp_path)
    assert _append_allowlist_delta(TeamRuntime(runtime_dir=tmp_path)) == delta_event_id
    assert _journal_bytes(tmp_path) == delta_bytes
    assert len(_allowlist_records(tmp_path)) == 2


def test_unicode_task_ids_emit_ascii_schema_valid_event_ids(tmp_path):
    reviewer_task_id = "reviewer-审查-ß"
    writer_task_id = "writer-写入-İ"
    _register_allowlist(
        TeamRuntime(runtime_dir=tmp_path),
        reviewer_task_id=reviewer_task_id,
    )
    _append_allowlist_delta(
        TeamRuntime(runtime_dir=tmp_path),
        reviewer_task_id=reviewer_task_id,
        writer_task_id=writer_task_id,
    )

    records = _allowlist_records(tmp_path)
    expected_digest = hashlib.sha256(reviewer_task_id.encode("utf-8")).hexdigest()[:12]
    baseline_prefix = records[0]["event_id"].rsplit("-v1-", maxsplit=1)[0]
    delta_prefix = records[1]["event_id"].rsplit("-v2-", maxsplit=1)[0]
    assert baseline_prefix == delta_prefix
    assert expected_digest in baseline_prefix
    assert all(record["event_id"].isascii() for record in records)
    assert records[0]["payload"]["subject_id"] == reviewer_task_id
    assert records[1]["payload"]["subject_id"] == reviewer_task_id
    assert (
        records[1]["payload"]["concurrent_slice_allowlist_delta"]["writer_task_id"]
        == writer_task_id
    )
    validator = _audit_validator()
    for record in records:
        validator.validate(record["payload"])
    invalid_timestamp = json.loads(json.dumps(records[0]["payload"]))
    invalid_timestamp["timestamp"] = "not-an-iso8601-timestamp"
    with pytest.raises(ValidationError):
        validator.validate(invalid_timestamp)


def test_two_runtime_instances_serialize_conflicting_allowlist_deltas(
    tmp_path,
    monkeypatch,
):
    first = TeamRuntime(runtime_dir=tmp_path)
    second = TeamRuntime(runtime_dir=tmp_path)
    _register_allowlist(first)
    append_barrier = threading.Barrier(2)
    original_append_locked = TeamRuntime._append_locked

    def barrier_append(self, event):
        if (
            event.event_type == "concurrent_slice_allowlist_event"
            and event.payload.get("subject_type") == "ConcurrentSliceAllowlistDelta"
        ):
            try:
                append_barrier.wait(timeout=1)
            except threading.BrokenBarrierError:
                pass
        original_append_locked(self, event)

    monkeypatch.setattr(TeamRuntime, "_append_locked", barrier_append)
    start_barrier = threading.Barrier(3)
    outcomes: list[tuple[str, object]] = []
    outcome_lock = threading.Lock()

    def append_delta(team: TeamRuntime, suffix: str) -> None:
        start_barrier.wait(timeout=3)
        try:
            result: tuple[str, object] = (
                "success",
                _append_allowlist_delta(
                    team,
                    writer_task_id=f"task-concurrent-writer-{suffix}",
                    dedupe_key=f"devframe/concurrent-reviewer/writer-{suffix}/v2",
                    exact_repo_paths=[f"packages/control-plane/{suffix}.py"],
                ),
            )
        except Exception as exc:  # noqa: BLE001 - the assertion checks the exact type
            result = ("error", exc)
        with outcome_lock:
            outcomes.append(result)

    threads = [
        threading.Thread(target=append_delta, args=(first, "alpha")),
        threading.Thread(target=append_delta, args=(second, "beta")),
    ]
    for thread in threads:
        thread.start()
    start_barrier.wait(timeout=3)
    for thread in threads:
        thread.join(timeout=5)
    assert not any(thread.is_alive() for thread in threads)

    successes = [value for status, value in outcomes if status == "success"]
    errors = [value for status, value in outcomes if status == "error"]
    assert len(successes) == 1
    assert len(errors) == 1
    assert isinstance(errors[0], ConcurrentSliceAllowlistError)
    assert "version" in str(errors[0])
    assert len(_allowlist_records(tmp_path)) == 2
    folded = TeamRuntime(runtime_dir=tmp_path).read_concurrent_slice_allowlists()[
        REVIEWER_TASK_ID
    ]
    assert folded["version"] == 2
    assert len(folded["allowed_paths_by_task"]) == 2


def test_allowlist_conflicting_dedupe_and_same_version_fail_before_append(tmp_path):
    team = TeamRuntime(runtime_dir=tmp_path)
    _register_allowlist(team)
    _append_allowlist_delta(team)

    _assert_allowlist_rejected_without_mutation(
        tmp_path,
        lambda: _append_allowlist_delta(
            TeamRuntime(runtime_dir=tmp_path),
            writer_task_id="task-conflicting-dedupe",
        ),
        "dedupe key",
    )
    _assert_allowlist_rejected_without_mutation(
        tmp_path,
        lambda: _append_allowlist_delta(
            TeamRuntime(runtime_dir=tmp_path),
            dedupe_key="devframe/concurrent-reviewer/conflicting-v2",
        ),
        "version",
    )

    _assert_allowlist_rejected_without_mutation(
        tmp_path,
        lambda: _append_allowlist_delta(
            TeamRuntime(runtime_dir=tmp_path),
            writer_task_id="task-overlapping-writer",
            dedupe_key="devframe/concurrent-reviewer/overlapping-writer/v3",
            previous_version=2,
            new_version=3,
            exact_repo_paths=[ALLOWLIST_DELTA_KWARGS["exact_repo_paths"][0]],
        ),
        "overlap existing paths",
    )


@pytest.mark.parametrize(
    ("overrides", "match"),
    [
        ({"new_version": 3}, "contiguous"),
        ({"previous_version": 0, "new_version": 1}, "version"),
    ],
)
def test_allowlist_version_gaps_and_regressions_fail_before_append(
    tmp_path,
    overrides,
    match,
):
    _register_allowlist(TeamRuntime(runtime_dir=tmp_path))
    _assert_allowlist_rejected_without_mutation(
        tmp_path,
        lambda: _append_allowlist_delta(TeamRuntime(runtime_dir=tmp_path), **overrides),
        match,
    )


@pytest.mark.parametrize(
    "paths",
    [
        ["../escape.py"],
        ["/absolute.py"],
        ["C:/absolute.py"],
        ["packages/control-plane/../escape.py"],
        ["packages//control-plane/file.py"],
        ["packages\\control-plane\\file.py"],
        ["packages/control-plane/file.py", "packages/control-plane/file.py"],
    ],
)
def test_allowlist_rejects_non_normalized_or_duplicate_repo_paths_before_append(
    tmp_path,
    paths,
):
    _register_allowlist(TeamRuntime(runtime_dir=tmp_path))
    _assert_allowlist_rejected_without_mutation(
        tmp_path,
        lambda: _append_allowlist_delta(
            TeamRuntime(runtime_dir=tmp_path),
            exact_repo_paths=paths,
        ),
        "exact_repo_paths",
    )


def test_allowlist_rejects_case_insensitive_path_alias_without_mutating_journal(
    tmp_path,
):
    team = TeamRuntime(runtime_dir=tmp_path)
    _register_allowlist(team)
    canonical_path = "packages/control-plane/File.py"
    _append_allowlist_delta(team, exact_repo_paths=[canonical_path])

    _assert_allowlist_rejected_without_mutation(
        tmp_path,
        lambda: _append_allowlist_delta(
            TeamRuntime(runtime_dir=tmp_path),
            writer_task_id="task-case-alias-writer",
            dedupe_key="devframe/concurrent-reviewer/case-alias/v3",
            exact_repo_paths=[canonical_path.lower()],
            previous_version=2,
            new_version=3,
        ),
        "collision",
    )
    folded = TeamRuntime(runtime_dir=tmp_path).read_concurrent_slice_allowlists()[
        REVIEWER_TASK_ID
    ]
    assert folded["version"] == 2
    assert "task-case-alias-writer" not in folded["allowed_paths_by_task"]


@pytest.mark.parametrize(
    "path",
    [
        "packages/control-plane/File.py.",
        "packages/control-plane/dir /File.py",
        "packages/control-plane/CON.txt",
        "packages/control-plane/File.py:stream",
    ],
)
def test_allowlist_and_schema_reject_windows_ambiguous_paths_without_mutation(
    tmp_path,
    path,
):
    _register_allowlist(TeamRuntime(runtime_dir=tmp_path))
    _assert_allowlist_rejected_without_mutation(
        tmp_path,
        lambda: _append_allowlist_delta(
            TeamRuntime(runtime_dir=tmp_path),
            exact_repo_paths=[path],
        ),
        "exact_repo_paths",
    )

    invalid_event = _allowlist_records(tmp_path)[0]["payload"]
    invalid_event["concurrent_slice_allowlist"]["exact_repo_paths"] = [path]
    with pytest.raises(ValidationError):
        _audit_validator().validate(invalid_event)


@pytest.mark.parametrize(
    ("overrides", "match"),
    [
        ({"checkout_identity": "different-checkout@1b9eb988"}, "checkout identity"),
        ({"baseline_manifest": ""}, "baseline_manifest"),
        ({"baseline_hash": ""}, "baseline_hash"),
        ({"baseline_hash": "0" * 64}, "baseline evidence"),
        (
            {"delivered_at": ALLOWLIST_DELTA_KWARGS["first_file_change_at"]},
            "before first_file_change_at",
        ),
        (
            {"delivered_at": "2026-07-22T01:00:02+00:00"},
            "before first_file_change_at",
        ),
        ({"delivered_at": "2026-07-22T01:00:00"}, "timezone"),
        ({"delivered_at": "not-a-timestamp"}, "ISO8601"),
    ],
)
def test_allowlist_delta_identity_evidence_and_delivery_boundary_fail_before_append(
    tmp_path,
    overrides,
    match,
):
    _register_allowlist(TeamRuntime(runtime_dir=tmp_path))
    _assert_allowlist_rejected_without_mutation(
        tmp_path,
        lambda: _append_allowlist_delta(TeamRuntime(runtime_dir=tmp_path), **overrides),
        match,
    )
    folded = TeamRuntime(runtime_dir=tmp_path).read_concurrent_slice_allowlists()[
        REVIEWER_TASK_ID
    ]
    assert WRITER_TASK_ID not in folded["allowed_paths_by_task"]


@pytest.mark.parametrize("missing_field", ["baseline_manifest", "baseline_hash"])
def test_allowlist_baseline_requires_manifest_hash_evidence_before_journal_creation(
    tmp_path,
    missing_field,
):
    with pytest.raises(ConcurrentSliceAllowlistError, match=missing_field):
        _register_allowlist(
            TeamRuntime(runtime_dir=tmp_path),
            **{missing_field: ""},
        )
    assert not (tmp_path / TEAM_EVENTS_FILE).exists()


def test_unknown_reviewer_delta_fails_closed_without_creating_a_journal(tmp_path):
    with pytest.raises(ConcurrentSliceAllowlistError, match="Unknown concurrent reviewer"):
        _append_allowlist_delta(TeamRuntime(runtime_dir=tmp_path))
    assert not (tmp_path / TEAM_EVENTS_FILE).exists()


def test_allowlist_fold_rejects_delta_whose_reviewer_baseline_is_missing(tmp_path):
    team = TeamRuntime(runtime_dir=tmp_path)
    _register_allowlist(team)
    _append_allowlist_delta(team)
    journal = tmp_path / TEAM_EVENTS_FILE
    records = _allowlist_records(tmp_path)
    journal.write_text(json.dumps(records[1]) + "\n", encoding="utf-8")
    before = journal.read_bytes()

    with pytest.raises(ConcurrentSliceAllowlistError, match="Unknown concurrent reviewer"):
        TeamRuntime(runtime_dir=tmp_path).read_concurrent_slice_allowlists()
    assert journal.read_bytes() == before
