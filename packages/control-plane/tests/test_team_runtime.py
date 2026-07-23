"""Hermetic tests for the real team runtime (M1 slice 1).

Verify that recorded team events become durable JSONL facts and fold into
schema-shaped message_bus / event_log entries, and that an empty journal yields
no entries (so the read model's projection fallback is unchanged).
"""
from __future__ import annotations

import json

import pytest

from control_plane.team_runtime import (
    TEAM_EVENTS_FILE,
    TeamRuntime,
    build_team_runtime_view,
)


def test_empty_view_when_no_journal(tmp_path):
    view = build_team_runtime_view(tmp_path)
    assert view == {
        "message_bus": [],
        "event_log": [],
        "conflict_control": [],
        "review_gates": [],
        "agent_registry": [],
        "task_board": [],
        "evidence_store": [],
    }


def test_view_derives_evidence_store(tmp_path):
    team = TeamRuntime(runtime_dir=tmp_path)
    team.record_task_created("go-run-9", "a1")
    team.record_result("go-run-9", "a1", status="passed", report_path="reports/a1.md")
    evidence = build_team_runtime_view(tmp_path)["evidence_store"]
    assert len(evidence) == 1
    assert evidence[0]["ref_type"] == "report"
    assert evidence[0]["ref_path"] == "reports/a1.md"
    assert evidence[0]["run_id"] == "go-run-9"
    # A result without a report path records no evidence.
    team.record_task_created("go-run-9", "a2")
    team.record_result("go-run-9", "a2", status="passed")
    assert len(build_team_runtime_view(tmp_path)["evidence_store"]) == 1


def test_legacy_task_result_report_path_still_projects_evidence(tmp_path):
    path = tmp_path / TEAM_EVENTS_FILE
    path.write_text(
        json.dumps({
            "event_type": "task_result",
            "run_id": "go-run-legacy",
            "agent_id": "a1",
            "payload": {"status": "passed", "report_path": "reports/legacy.md"},
            "timestamp": "2026-07-07T00:00:00+00:00",
            "event_id": "legacy-event",
        }) + "\n",
        encoding="utf-8",
    )

    evidence = build_team_runtime_view(tmp_path)["evidence_store"]

    assert evidence == [{
        "evidence_id": "team-evidence-legacy-event",
        "run_id": "go-run-legacy",
        "ref_type": "report",
        "ref_path": "reports/legacy.md",
    }]


def test_direct_evidence_ref_without_source_event_id_uses_event_id_and_dedupes_path(tmp_path):
    team = TeamRuntime(runtime_dir=tmp_path)
    team.record_evidence_ref("go-run-direct", "a1", ref_type="report", ref_path="reports/direct.md")
    team.record_evidence_ref("go-run-direct", "a1", ref_type="report", ref_path="reports/direct.md")

    view = build_team_runtime_view(tmp_path)

    assert len(view["evidence_store"]) == 1
    evidence = view["evidence_store"][0]
    assert evidence["evidence_id"] != "team-evidence-x"
    assert evidence["evidence_id"].startswith("team-evidence-go-run-direct-a1-")
    assert evidence["ref_path"] == "reports/direct.md"
    assert len([event for event in view["event_log"] if event["kind"] == "evidence-ref"]) == 2


def test_task_lifecycle_records_legacy_context_refs_as_provenance(tmp_path):
    team = TeamRuntime(runtime_dir=tmp_path)
    context_refs = [
        {"ref_type": "legacy_context", "ref_path": "packets/p1", "context_id": "p1"},
        {"ref_type": "legacy_task_spec", "ref_path": "packets/p1/TASKSPEC.json", "context_id": "p1"},
    ]

    team.record_task_created("go-run-context", "a1", context_refs=context_refs)
    team.record_task_claimed("go-run-context", "a1", context_refs=context_refs)

    lines = (tmp_path / TEAM_EVENTS_FILE).read_text(encoding="utf-8").strip().splitlines()
    payloads = [json.loads(line)["payload"] for line in lines]
    assert payloads[0]["context_refs"] == context_refs
    assert payloads[1]["context_refs"] == context_refs

    evidence = build_team_runtime_view(tmp_path)["evidence_store"]

    assert len(evidence) == 2
    assert {item["run_id"] for item in evidence} == {"go-run-context"}
    assert {item["ref_type"] for item in evidence} == {"legacy_context", "legacy_task_spec"}
    assert {item["ref_path"] for item in evidence} == {"packets/p1", "packets/p1/TASKSPEC.json"}
    assert all(item["evidence_id"].startswith("team-context-go-run-context-a1-") for item in evidence)


def test_view_derives_agent_registry_and_task_board(tmp_path):
    team = TeamRuntime(runtime_dir=tmp_path)
    team.record_task_created("go-run-1", "coding-agent-1", shard_index=1, shard_count=2,
                             project_id="proj", targets=["a.py"])
    team.record_task_claimed("go-run-1", "coding-agent-1")
    team.record_result("go-run-1", "coding-agent-1", status="passed")

    view = build_team_runtime_view(tmp_path)

    # Task Board: one real task with a created -> claimed -> completed lifecycle.
    assert len(view["task_board"]) == 1
    task = view["task_board"][0]
    assert task["type"] == "go-run"
    assert task["status"] == "completed"
    assert task["agent_ids"] == ["coding-agent-1"]
    assert task["target_files"] == ["a.py"]
    assert task["task_id"].startswith("team-task-")

    # Agent Registry: the participant, with its latest recorded status.
    assert len(view["agent_registry"]) == 1
    agent = view["agent_registry"][0]
    assert agent["agent_id"] == "coding-agent-1"
    assert agent["role"] == "worker"
    assert agent["status"] == "completed"
    assert agent["session_ids"] == []


def test_task_board_status_reflects_failure(tmp_path):
    team = TeamRuntime(runtime_dir=tmp_path)
    team.record_task_created("go-run-2", "a1")
    team.record_result("go-run-2", "a1", status="failed")
    task = build_team_runtime_view(tmp_path)["task_board"][0]
    assert task["status"] == "failed"


def test_view_derives_conflict_and_review_objects(tmp_path):
    team = TeamRuntime(runtime_dir=tmp_path)
    team.record_task_created("go-run-1", "coding-agent-1", shard_index=1, shard_count=2, targets=["a.py", "dir/"])
    team.record_task_claimed("go-run-1", "coding-agent-1")
    team.record_result("go-run-1", "coding-agent-1", status="passed", report_path="r.md")

    view = build_team_runtime_view(tmp_path)

    # Conflict Control: each recorded target is owned by the agent for the run.
    owned = {(c["file_path"], c["owner_agent_id"]) for c in view["conflict_control"]}
    assert ("a.py", "coding-agent-1") in owned
    assert ("dir/", "coding-agent-1") in owned
    for c in view["conflict_control"]:
        assert c["owner_run_id"] == "go-run-1"
        assert c["file_kind"] == "target"

    # Review Gate: worker success opens the gate but cannot pass review.
    assert len(view["review_gates"]) == 1
    gate = view["review_gates"][0]
    assert gate["kind"] == "acceptance"
    assert gate["status"] == "open"
    assert gate["run_id"] == "go-run-1"
    assert "independent review is still required" in gate["reason"]


def test_worker_success_without_review_never_passes_acceptance_gate(tmp_path):
    team = TeamRuntime(runtime_dir=tmp_path)
    for status in ["pass", "passed", "completed", "verified"]:
        team.record_result("go-run-1", f"agent-{status}", status=status)

    statuses = {g["status"] for g in build_team_runtime_view(tmp_path)["review_gates"]}
    assert statuses == {"open"}


def test_review_and_final_verdict_events_project_as_distinct_team_objects(tmp_path):
    team = TeamRuntime(runtime_dir=tmp_path)
    report_path = tmp_path / "reports" / "worker.md"
    report_path.parent.mkdir(parents=True)
    report_path.write_text("worker evidence\n", encoding="utf-8")
    review_path = tmp_path / "reviews" / "review.yaml"
    review_path.parent.mkdir(parents=True)
    review_path.write_text("verdict: pass\n", encoding="utf-8")
    final_path = tmp_path / "final" / "final-verdict.json"
    final_path.parent.mkdir(parents=True)
    gate_id = "gate-go-run-review-independent-review"
    final_path.write_text(json.dumps({
        "verdict_id": "fv-go-run-review-1",
        "produced_by": "go-evidence-finalizer",
        "produced_at": "2026-07-23T00:00:00+00:00",
        "producer_role": "governance",
        "final_state": "final_ready",
        "inputs_reviewed": [str(report_path), str(review_path)],
        "gate_summary": [{
            "gate_id": gate_id,
            "result": "pass",
            "evidence_path": str(review_path),
        }],
        "reviewer_summary": {
            "reviewer_id": "reviewer-1",
            "verdict": "pass",
            "evidence_path": str(review_path),
        },
        "limitations": [],
        "human_or_governance_reference": "go-evidence-finalize:go-run-review",
    }), encoding="utf-8")
    team.record_result(
        "go-run-review",
        "coding-agent-1",
        status="passed",
        report_path=str(report_path),
    )
    team.record_review_ref(
        "go-run-review",
        "reviewer-1",
        review_id="review-go-run-review-1",
        reviewer_role="reviewer",
        executor_id="coding-agent-1",
        verdict="pass",
        ref_path=str(review_path),
        reviewed_evidence_refs=[str(report_path)],
        reviewed_inputs=["diff.patch", "test-output.md", "safety-report.json", "chain-evidence.json"],
        source="go_evidence_finalize",
    )
    team.record_final_verdict_ref(
        "go-run-review",
        "go-evidence-finalizer",
        verdict_id="fv-go-run-review-1",
        producer_role="governance",
        final_state="final_ready",
        ref_path=str(final_path),
        review_ref="review-go-run-review-1",
        gate_refs=[gate_id],
        gate_summary=[{
            "gate_id": gate_id,
            "result": "pass",
            "evidence_path": str(review_path),
        }],
        human_or_governance_reference="go-evidence-finalize:go-run-review",
    )

    view = build_team_runtime_view(tmp_path)

    assert {"task-result", "evidence-ref", "review-ref", "final-verdict-ref"} <= {
        event["kind"] for event in view["event_log"]
    }
    assert {"result", "review-verdict", "final-verdict"} <= {
        message["kind"] for message in view["message_bus"]
    }
    assert {item["ref_type"] for item in view["evidence_store"]} == {"report", "review", "final_verdict"}
    gates = {(gate["kind"], gate["status"]) for gate in view["review_gates"]}
    assert ("acceptance", "open") in gates
    assert ("independent-review", "pass") in gates
    assert ("final-verdict", "pass") in gates


def test_review_status_mapping(tmp_path):
    team = TeamRuntime(runtime_dir=tmp_path)
    team.record_result("go-run-1", "a1", status="failed")
    team.record_result("go-run-1", "a2", status="blocked")
    statuses = sorted(g["status"] for g in build_team_runtime_view(tmp_path)["review_gates"])
    assert statuses == ["blocked", "failed"]


def test_conflict_dedup_across_repeated_targets(tmp_path):
    team = TeamRuntime(runtime_dir=tmp_path)
    team.record_task_created("go-run-1", "coding-agent-1", targets=["a.py"])
    team.record_task_created("go-run-1", "coding-agent-1", targets=["a.py"])  # re-run
    conflicts = build_team_runtime_view(tmp_path)["conflict_control"]
    assert len([c for c in conflicts if c["file_path"] == "a.py"]) == 1


def test_duplicate_target_claim_is_rejected_without_journal_mutation(tmp_path):
    team = TeamRuntime(runtime_dir=tmp_path)
    team.record_task_created("go-run-claims", "agent-a", targets=["shared.py"])
    team.record_task_created("go-run-claims", "agent-b", targets=["shared.py"])
    team.record_task_claimed("go-run-claims", "agent-a")
    team.record_task_claimed("go-run-claims", "agent-a")
    journal = tmp_path / TEAM_EVENTS_FILE
    line_count = len(journal.read_text(encoding="utf-8").splitlines())

    with pytest.raises(ValueError, match="shared.py"):
        team.record_task_claimed("go-run-claims", "agent-b")

    assert len(journal.read_text(encoding="utf-8").splitlines()) == line_count
    conflicts = build_team_runtime_view(tmp_path)["conflict_control"]
    assert [(item["file_path"], item["owner_agent_id"]) for item in conflicts] == [
        ("shared.py", "agent-a"),
    ]


def test_distinct_targets_can_be_claimed_in_the_same_run(tmp_path):
    team = TeamRuntime(runtime_dir=tmp_path)
    team.record_task_created("go-run-claims", "agent-a", targets=["a.py"])
    team.record_task_created("go-run-claims", "agent-b", targets=["b.py"])

    team.record_task_claimed("go-run-claims", "agent-a")
    team.record_task_claimed("go-run-claims", "agent-b")

    task_board = build_team_runtime_view(tmp_path)["task_board"]
    assert {task["status"] for task in task_board} == {"claimed"}


def test_record_lifecycle_is_persisted(tmp_path):
    team = TeamRuntime(runtime_dir=tmp_path)
    team.record_task_created("go-run-1", "coding-agent-1", shard_index=1, shard_count=2, targets=["a.py"])
    team.record_task_claimed("go-run-1", "coding-agent-1")
    team.record_result("go-run-1", "coding-agent-1", status="passed", report_path="r.md")

    lines = (tmp_path / TEAM_EVENTS_FILE).read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 4
    types = [json.loads(line)["event_type"] for line in lines]
    assert types == ["task_created", "task_claimed", "task_result", "evidence_ref"]


def test_view_folds_events_into_schema_shapes(tmp_path):
    team = TeamRuntime(runtime_dir=tmp_path)
    team.record_task_created("go-run-1", "coding-agent-1", shard_index=1, shard_count=2, targets=["a.py"])
    team.record_task_claimed("go-run-1", "coding-agent-1")
    team.record_result("go-run-1", "coding-agent-1", status="passed", report_path="r.md")

    view = build_team_runtime_view(tmp_path)
    event_kinds = {e["kind"] for e in view["event_log"]}
    assert {"task-created", "task-claimed", "task-result", "evidence-ref"} <= event_kinds

    # message_bus has a coordinator->agent assign and an agent->coordinator result
    kinds = {(m["from_role"], m["to_role"], m["kind"]) for m in view["message_bus"]}
    assert ("coordinator", "coding-agent-1", "task-assign") in kinds
    assert ("coding-agent-1", "coordinator", "result") in kinds

    # Ids conform to the schema pattern ^[a-z0-9][a-z0-9-]*$.
    import re
    pattern = re.compile(r"^[a-z0-9][a-z0-9-]*$")
    for entry in view["event_log"]:
        assert pattern.match(entry["event_id"]), entry["event_id"]
    for entry in view["message_bus"]:
        assert pattern.match(entry["message_id"]), entry["message_id"]


def test_explicit_agent_message_is_durable_and_not_a_lifecycle_projection(tmp_path):
    team = TeamRuntime(runtime_dir=tmp_path)

    team.record_agent_message(
        "go-run-message",
        "coding-agent-1",
        "coding-agent-2",
        kind="handoff",
        summary="Please review the isolated implementation.",
    )

    record = json.loads((tmp_path / TEAM_EVENTS_FILE).read_text(encoding="utf-8"))
    assert record["event_type"] == "agent_message"
    assert record["agent_id"] == "coding-agent-1"
    assert record["payload"] == {
        "to_agent_id": "coding-agent-2",
        "kind": "handoff",
        "summary": "Please review the isolated implementation.",
    }

    view = build_team_runtime_view(tmp_path)
    assert ("coding-agent-1", "coding-agent-2", "handoff") in {
        (message["from_role"], message["to_role"], message["kind"])
        for message in view["message_bus"]
    }
    assert {
        "agent-message",
    } <= {event["kind"] for event in view["event_log"]}


def test_explicit_agent_message_rejects_missing_required_fields(tmp_path):
    team = TeamRuntime(runtime_dir=tmp_path)

    for kwargs in (
        {"from_agent_id": "", "to_agent_id": "coding-agent-2", "kind": "handoff", "summary": "x"},
        {"from_agent_id": "coding-agent-1", "to_agent_id": "", "kind": "handoff", "summary": "x"},
        {"from_agent_id": "coding-agent-1", "to_agent_id": "coding-agent-2", "kind": "", "summary": "x"},
        {"from_agent_id": "coding-agent-1", "to_agent_id": "coding-agent-2", "kind": "handoff", "summary": ""},
    ):
        try:
            team.record_agent_message("go-run-message", **kwargs)
        except ValueError:
            continue
        raise AssertionError("expected explicit message validation to fail closed")


def test_journal_refuses_inside_repo(tmp_path):
    # repo_root == runtime_dir means the journal would live inside the repo.
    team = TeamRuntime(runtime_dir=tmp_path, repo_root=tmp_path)
    try:
        team.record_task_claimed("go-run-1", "coding-agent-1")
    except ValueError as exc:
        assert "must not be inside the public repository" in str(exc)
    else:
        raise AssertionError("expected ValueError for in-repo journal")


def test_thread_safe_appends(tmp_path):
    import threading

    team = TeamRuntime(runtime_dir=tmp_path)

    def worker(n: int) -> None:
        team.record_task_claimed("go-run-1", f"coding-agent-{n}")

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    lines = (tmp_path / TEAM_EVENTS_FILE).read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 20
    # Every line is valid JSON (no interleaved/corrupted writes).
    for line in lines:
        json.loads(line)
