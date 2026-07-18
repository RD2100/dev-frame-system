from __future__ import annotations

import json
from pathlib import Path

from jsonschema.validators import validator_for

import control_plane.run_index as run_index_module
from control_plane.run_index import ADAPTER_VERSION, build_run_index
from control_plane.team_runtime import TeamRuntime

REPO_ROOT = Path(__file__).resolve().parents[3]


def _run_record_validator():
    schema = json.loads(
        (REPO_ROOT / "schemas/runtime-governance/run-record.schema.json").read_text(encoding="utf-8-sig")
    )
    validator_class = validator_for(schema)
    validator_class.check_schema(schema)
    return validator_class(schema)


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=True), encoding="utf-8")


def _write_sealed_context(runtime: Path, token: str) -> tuple[Path, Path]:
    task_input = runtime / "context" / token / "TASKSPEC.json"
    task_input.parent.mkdir(parents=True, exist_ok=True)
    task_input.write_text('{"task": "sealed context fixture"}\n', encoding="utf-8")
    context_packet_path = runtime / "context" / token / "context-packet.json"
    context_ledger_path = runtime / "context" / token / "context-ledger.json"
    context_packet_id = f"cp-{token}"
    _write_json(context_packet_path, {
        "schema_version": "0.1",
        "context_packet_id": context_packet_id,
        "project_id": "demo-project",
        "goal_id": "goal-demo-project",
        "task_id": f"task-{token}",
        "domain": "code",
        "profile": "go-dispatch-task-context",
        "producer_role": "coordinator",
        "created_at": "2026-07-07T00:00:00Z",
        "intent_summary": "Fixture sealed context for final-ready projection.",
        "intended_use": "execution",
        "immutability": {
            "immutable": True,
            "content_hash": "sha256:" + "1" * 64,
        },
        "source_refs": [{
            "ref_id": "taskspec-json",
            "kind": "file",
            "uri": str(task_input),
            "included": True,
            "required": True,
            "freshness_state": "current",
        }],
        "omitted_required_refs": [],
        "forbidden_refs": [],
        "freshness": {
            "checked_at": "2026-07-07T00:00:00Z",
            "stale_refs": [],
            "unknown_refs": [],
        },
        "completeness_state": "complete",
        "privacy_state": "redacted",
        "seal_state": "sealed",
        "limitations": ["Fixture only."],
        "constraints": {
            "allowed_actions": ["execute assigned task"],
            "forbidden_actions": ["claim final acceptance"],
            "stop_lines": ["FinalVerdict is required before acceptance."],
            "authority_boundary": {
                "can_execute": True,
                "can_review": False,
                "can_claim_final_acceptance": False,
                "final_verdict_required": True,
            },
        },
        "domain_refs": {"fixture": token},
    })
    _write_json(context_ledger_path, {
        "schema_version": "0.1",
        "context_ledger_id": f"cl-{token}",
        "project_id": "demo-project",
        "goal_id": "goal-demo-project",
        "task_id": f"task-{token}",
        "created_at": "2026-07-07T00:00:00Z",
        "append_only": True,
        "entries": [{
            "ledger_entry_id": f"cle-{token}-created",
            "entry_index": 0,
            "previous_entry_hash": None,
            "entry_hash": "sha256:" + "2" * 64,
            "occurred_at": "2026-07-07T00:00:00Z",
            "actor_id": "test-coordinator",
            "actor_role": "coordinator",
            "event_type": "packet_created",
            "context_packet_id": context_packet_id,
            "summary": "Created sealed context fixture.",
        }],
    })
    return context_packet_path, context_ledger_path


def _sealed_context_created_event(runtime: Path, run_id: str, *, agent_id: str = "coding-agent-1") -> str:
    token = f"{run_id}-context"
    context_packet_path, context_ledger_path = _write_sealed_context(runtime, token)
    return json.dumps({
        "event_type": "task_created",
        "run_id": run_id,
        "agent_id": agent_id,
        "payload": {
            "project_id": "demo-project",
            "context_refs": [
                {
                    "ref_type": "context_packet",
                    "ref_path": str(context_packet_path),
                    "context_id": f"cp-{token}",
                },
                {
                    "ref_type": "context_ledger",
                    "ref_path": str(context_ledger_path),
                    "context_id": f"cl-{token}",
                },
            ],
        },
        "timestamp": "2026-07-07T00:00:00Z",
        "event_id": f"team-{run_id}-context-created",
    })


def _records_by_adapter(index: dict) -> dict[str, list[dict]]:
    grouped: dict[str, list[dict]] = {}
    for entry in index["runs"]:
        grouped.setdefault(entry["adapter_id"], []).append(entry["record"])
    return grouped


def _write_physical_go_run(
    runtime: Path,
    *,
    team_project_id: str,
    go_project_id: str = "demo-project",
    go_status: str = "passed",
    go_worker_status: str = "passed",
    team_worker_status: str = "passed",
    go_only_worker_id: str = "",
) -> str:
    report_path = runtime / "reports" / "worker.md"
    report_path.parent.mkdir(parents=True)
    report_path.write_text("worker report\n", encoding="utf-8")
    agents = [{
        "agent_id": "coding-agent-1",
        "status": "completed",
        "worker_status": go_worker_status,
        "report_path": str(report_path),
    }]
    if go_only_worker_id:
        agents.append({
            "agent_id": go_only_worker_id,
            "status": "completed",
            "worker_status": "passed",
            "report_path": str(report_path),
        })
    _write_json(runtime / "go-runs" / "go-canonical" / "go-run.json", {
        "go_run_id": "go-canonical",
        "project_id": go_project_id,
        "status": go_status,
        "created_at": "2026-07-18T00:00:00Z",
        "agents": agents,
    })
    team = TeamRuntime(runtime_dir=runtime)
    team.record_task_created(
        "go-canonical",
        "coding-agent-1",
        project_id=team_project_id,
        targets=["src/app.py"],
    )
    return team.record_result(
        "go-canonical",
        "coding-agent-1",
        status=team_worker_status,
        report_path=str(report_path),
    )


def _write_team_final_ready(
    runtime: Path,
    *,
    reviewer_id: str,
    result_event_id: str,
    producer_role: str = "governance",
) -> None:
    report_path = runtime / "reports" / "worker.md"
    review_path = runtime / "reviews" / "review.yaml"
    review_path.parent.mkdir(parents=True)
    review_path.write_text("verdict: pass\n", encoding="utf-8")
    final_path = runtime / "final" / "final-verdict.json"
    gate_id = "gate-go-canonical-independent-review"
    review_id = "review-go-canonical"
    _write_json(final_path, {
        "verdict_id": "fv-go-canonical",
        "produced_by": "go-evidence-finalizer",
        "produced_at": "2026-07-18T00:02:00Z",
        "producer_role": producer_role,
        "final_state": "final_ready",
        "inputs_reviewed": [str(report_path), str(review_path)],
        "gate_summary": [{
            "gate_id": gate_id,
            "result": "pass",
            "evidence_path": str(review_path),
        }],
        "reviewer_summary": {
            "reviewer_id": reviewer_id,
            "verdict": "pass",
            "evidence_path": str(review_path),
        },
        "limitations": [],
        "human_or_governance_reference": "go-evidence-finalize:go-canonical",
    })
    context_packet_path, context_ledger_path = _write_sealed_context(
        runtime,
        "go-canonical-context",
    )
    team = TeamRuntime(runtime_dir=runtime)
    team.record_task_created(
        "go-canonical",
        "coding-agent-1",
        context_refs=[
            {
                "ref_type": "context_packet",
                "ref_path": str(context_packet_path),
                "context_id": "cp-go-canonical-context",
            },
            {
                "ref_type": "context_ledger",
                "ref_path": str(context_ledger_path),
                "context_id": "cl-go-canonical-context",
            },
        ],
    )
    team.record_review_ref(
        "go-canonical",
        reviewer_id,
        review_id=review_id,
        reviewer_role="reviewer",
        executor_id="coding-agent-1",
        verdict="pass",
        ref_path=str(review_path),
        reviewed_evidence_refs=[f"ev-team-{result_event_id}"],
    )
    team.record_final_verdict_ref(
        "go-canonical",
        "go-evidence-finalizer",
        verdict_id="fv-go-canonical",
        producer_role=producer_role,
        final_state="final_ready",
        ref_path=str(final_path),
        review_ref=review_id,
        gate_refs=[gate_id],
        gate_summary=[{
            "gate_id": gate_id,
            "result": "pass",
            "evidence_path": str(review_path),
        }],
        human_or_governance_reference="go-evidence-finalize:go-canonical",
    )


def test_run_index_builds_one_canonical_view_for_matching_go_and_team_run(tmp_path):
    runtime = tmp_path / "runtime"
    _write_physical_go_run(runtime, team_project_id="")

    index = build_run_index(runtime)
    repeated = build_run_index(runtime)

    assert len(index["runs"]) == 2
    raw_entries = {entry["adapter_id"]: entry for entry in index["runs"]}
    assert set(raw_entries) == {"go_run", "team_events"}
    assert {entry["record"]["run_id"] for entry in raw_entries.values()} == {"run-go-canonical"}
    assert raw_entries["go_run"]["record"]["project_id"] == "demo-project"
    assert raw_entries["team_events"]["record"]["project_id"] == "unknown-project"

    assert index["canonical_runs"] == repeated["canonical_runs"]
    assert len(index["canonical_runs"]) == 1
    canonical_entry = index["canonical_runs"][0]
    canonical_record = canonical_entry["record"]
    _run_record_validator().validate(canonical_record)
    assert canonical_record["run_id"] == "run-go-canonical"
    assert canonical_record["project_id"] == "demo-project"
    assert canonical_record["review_state"] == "review_pending"
    assert canonical_record["acceptance_state"] == "review_pending"
    assert {
        source["adapter_id"] for source in canonical_entry["provenance"]["sources"]
    } == {"go_run", "team_events"}


def test_run_index_fails_closed_on_conflicting_canonical_project_identity(tmp_path):
    runtime = tmp_path / "runtime"
    _write_physical_go_run(runtime, team_project_id="conflicting-project")

    index = build_run_index(runtime)

    assert len(index["runs"]) == 2
    raw_entries = {entry["adapter_id"]: entry for entry in index["runs"]}
    assert raw_entries["go_run"]["record"]["project_id"] == "demo-project"
    assert raw_entries["team_events"]["record"]["project_id"] == "conflicting-project"

    assert len(index["canonical_runs"]) == 1
    canonical_entry = index["canonical_runs"][0]
    canonical_record = canonical_entry["record"]
    _run_record_validator().validate(canonical_record)
    assert canonical_record["run_id"] == "run-go-canonical"
    assert canonical_record["project_id"] == "unknown-project"
    assert canonical_record["outcome"] == "blocked"
    assert canonical_record["acceptance_state"] == "blocked"
    assert canonical_record["failure_refs"][0]["status"] == "blocked"
    assert "project identity conflict" in canonical_record["domain_refs"]["diagnostic"].lower()
    assert {
        source["adapter_id"] for source in canonical_entry["provenance"]["sources"]
    } == {"go_run", "team_events"}


def test_run_index_blocks_canonical_reviewer_found_in_merged_worker_union(tmp_path):
    runtime = tmp_path / "runtime"
    result_event_id = _write_physical_go_run(
        runtime,
        team_project_id="demo-project",
        go_only_worker_id="reviewer-1",
    )
    _write_team_final_ready(
        runtime,
        reviewer_id="reviewer-1",
        result_event_id=result_event_id,
    )

    index = build_run_index(runtime)

    raw_entries = {entry["adapter_id"]: entry["record"] for entry in index["runs"]}
    assert raw_entries["team_events"]["acceptance_state"] == "final_ready"
    assert {item["worker_id"] for item in raw_entries["go_run"]["worker_results"]} == {
        "coding-agent-1",
        "reviewer-1",
    }
    canonical_record = index["canonical_runs"][0]["record"]
    _run_record_validator().validate(canonical_record)
    assert canonical_record["acceptance_state"] == "blocked"
    assert canonical_record["outcome"] == "blocked"
    assert canonical_record["failure_refs"][0]["status"] == "blocked"
    diagnostic = canonical_record["domain_refs"]["diagnostic"].lower()
    assert "reviewer-1" in diagnostic
    assert "worker" in diagnostic


def test_run_index_blocks_canonical_final_verdict_producer_in_merged_worker_union(tmp_path):
    runtime = tmp_path / "runtime"
    result_event_id = _write_physical_go_run(
        runtime,
        team_project_id="demo-project",
        go_only_worker_id="go-evidence-finalizer",
    )
    _write_team_final_ready(
        runtime,
        reviewer_id="reviewer-1",
        result_event_id=result_event_id,
    )

    index = build_run_index(runtime)

    raw_entries = {entry["adapter_id"]: entry["record"] for entry in index["runs"]}
    assert raw_entries["team_events"]["acceptance_state"] == "final_ready"
    assert {item["worker_id"] for item in raw_entries["go_run"]["worker_results"]} == {
        "coding-agent-1",
        "go-evidence-finalizer",
    }
    canonical_record = index["canonical_runs"][0]["record"]
    _run_record_validator().validate(canonical_record)
    assert canonical_record["acceptance_state"] == "blocked"
    assert canonical_record["outcome"] == "blocked"
    assert canonical_record["failure_refs"][0]["status"] == "blocked"
    diagnostic = canonical_record["domain_refs"]["diagnostic"].lower()
    assert "go-evidence-finalizer" in diagnostic
    assert "worker" in diagnostic


def test_run_index_blocks_canonical_final_verdict_event_producer_in_merged_worker_union(tmp_path):
    runtime = tmp_path / "runtime"
    result_event_id = _write_physical_go_run(
        runtime,
        team_project_id="demo-project",
        go_only_worker_id="event-producer-worker",
    )
    _write_team_final_ready(
        runtime,
        reviewer_id="reviewer-1",
        result_event_id=result_event_id,
    )
    events_path = runtime / "team-events.jsonl"
    events = [json.loads(line) for line in events_path.read_text(encoding="utf-8").splitlines()]
    final_event = next(event for event in events if event["event_type"] == "final_verdict_ref")
    final_event["agent_id"] = "event-producer-worker"
    events_path.write_text(
        "".join(json.dumps(event, ensure_ascii=True) + "\n" for event in events),
        encoding="utf-8",
    )

    index = build_run_index(runtime)

    raw_entries = {entry["adapter_id"]: entry["record"] for entry in index["runs"]}
    assert raw_entries["team_events"]["acceptance_state"] == "final_ready"
    assert final_event["payload"]["produced_by"] == "go-evidence-finalizer"
    assert {item["worker_id"] for item in raw_entries["go_run"]["worker_results"]} == {
        "coding-agent-1",
        "event-producer-worker",
    }
    canonical_record = index["canonical_runs"][0]["record"]
    _run_record_validator().validate(canonical_record)
    assert canonical_record["acceptance_state"] == "blocked"
    assert canonical_record["outcome"] == "blocked"
    assert canonical_record["failure_refs"][0]["status"] == "blocked"
    diagnostic = canonical_record["domain_refs"]["diagnostic"].lower()
    assert "event-producer-worker" in diagnostic
    assert "worker" in diagnostic


def test_run_index_blocks_client_final_verdict_producer_role(tmp_path):
    runtime = tmp_path / "runtime"
    result_event_id = _write_physical_go_run(
        runtime,
        team_project_id="demo-project",
    )
    _write_team_final_ready(
        runtime,
        reviewer_id="reviewer-1",
        result_event_id=result_event_id,
        producer_role="client",
    )

    index = build_run_index(runtime)

    raw_entries = {entry["adapter_id"]: entry["record"] for entry in index["runs"]}
    raw_team_record = raw_entries["team_events"]
    _run_record_validator().validate(raw_team_record)
    assert raw_team_record["acceptance_state"] == "blocked"
    assert raw_team_record["outcome"] == "blocked"
    assert raw_team_record["failure_refs"][0]["status"] == "blocked"
    raw_diagnostic = raw_team_record["domain_refs"]["diagnostic"].lower()
    assert "client" in raw_diagnostic
    assert "producer role" in raw_diagnostic

    canonical_record = index["canonical_runs"][0]["record"]
    _run_record_validator().validate(canonical_record)
    assert canonical_record["acceptance_state"] == "blocked"
    assert canonical_record["outcome"] == "blocked"
    assert canonical_record["failure_refs"][0]["status"] == "blocked"
    canonical_diagnostic = canonical_record["domain_refs"]["diagnostic"].lower()
    assert "client" in canonical_diagnostic
    assert "producer role" in canonical_diagnostic


def test_run_index_blocks_dotted_client_final_verdict_producer_role(tmp_path):
    runtime = tmp_path / "runtime"
    result_event_id = _write_physical_go_run(
        runtime,
        team_project_id="demo-project",
    )
    _write_team_final_ready(
        runtime,
        reviewer_id="reviewer-1",
        result_event_id=result_event_id,
        producer_role="client.adapter",
    )

    index = build_run_index(runtime)

    raw_entries = {entry["adapter_id"]: entry["record"] for entry in index["runs"]}
    raw_team_record = raw_entries["team_events"]
    _run_record_validator().validate(raw_team_record)
    assert raw_team_record["acceptance_state"] == "blocked"
    assert raw_team_record["outcome"] == "blocked"
    assert raw_team_record["failure_refs"][0]["status"] == "blocked"
    raw_diagnostic = raw_team_record["domain_refs"]["diagnostic"].lower()
    assert "client" in raw_diagnostic
    assert "producer role" in raw_diagnostic

    canonical_record = index["canonical_runs"][0]["record"]
    _run_record_validator().validate(canonical_record)
    assert canonical_record["acceptance_state"] == "blocked"
    assert canonical_record["outcome"] == "blocked"
    assert canonical_record["failure_refs"][0]["status"] == "blocked"
    canonical_diagnostic = canonical_record["domain_refs"]["diagnostic"].lower()
    assert "client" in canonical_diagnostic
    assert "producer role" in canonical_diagnostic


def test_run_index_fails_closed_when_team_journal_changes_after_initial_parse(
    tmp_path,
    monkeypatch,
):
    runtime = tmp_path / "runtime"
    result_event_id = _write_physical_go_run(
        runtime,
        team_project_id="demo-project",
    )
    _write_team_final_ready(
        runtime,
        reviewer_id="reviewer-1",
        result_event_id=result_event_id,
    )
    initial = build_run_index(runtime)
    assert _records_by_adapter(initial)["team_events"][0]["acceptance_state"] == "final_ready"
    assert initial["canonical_runs"][0]["record"]["acceptance_state"] == "final_ready"

    events_path = (runtime / "team-events.jsonl").resolve()
    original_read_snapshot = run_index_module._read_jsonl_snapshot
    journal_changed_after_parse = False

    def read_then_replace_final_event(path):
        nonlocal journal_changed_after_parse
        parsed, source_hash = original_read_snapshot(path)
        if Path(path).resolve() == events_path and not journal_changed_after_parse:
            events = [
                json.loads(line)
                for line in events_path.read_text(encoding="utf-8").splitlines()
            ]
            final_event = next(
                event for event in events if event["event_type"] == "final_verdict_ref"
            )
            final_event["payload"]["produced_by"] = "coding-agent-1"
            final_event["payload"]["producer_role"] = "client.adapter"
            events_path.write_text(
                "".join(json.dumps(event, ensure_ascii=True) + "\n" for event in events),
                encoding="utf-8",
            )
            journal_changed_after_parse = True
        return parsed, source_hash

    monkeypatch.setattr(
        run_index_module,
        "_read_jsonl_snapshot",
        read_then_replace_final_event,
    )

    index = run_index_module.build_run_index(runtime)

    assert journal_changed_after_parse is True
    raw_team_record = _records_by_adapter(index)["team_events"][0]
    _run_record_validator().validate(raw_team_record)
    assert raw_team_record["acceptance_state"] == "final_ready"
    assert raw_team_record["outcome"] == "passed"

    canonical_record = index["canonical_runs"][0]["record"]
    _run_record_validator().validate(canonical_record)
    assert canonical_record["acceptance_state"] == "blocked"
    assert canonical_record["outcome"] == "blocked"
    canonical_diagnostic = str(
        canonical_record["domain_refs"].get("diagnostic") or ""
    ).lower()
    assert "team event source" in canonical_diagnostic
    assert "changed" in canonical_diagnostic or "unbound" in canonical_diagnostic


def test_run_index_blocks_canonical_run_without_valid_project_identity(tmp_path):
    runtime = tmp_path / "runtime"
    _write_physical_go_run(
        runtime,
        go_project_id="",
        team_project_id="",
    )

    index = build_run_index(runtime)

    raw_entries = {entry["adapter_id"]: entry["record"] for entry in index["runs"]}
    assert {record["project_id"] for record in raw_entries.values()} == {"unknown-project"}
    canonical_record = index["canonical_runs"][0]["record"]
    _run_record_validator().validate(canonical_record)
    assert canonical_record["project_id"] == "unknown-project"
    assert canonical_record["acceptance_state"] == "blocked"
    assert canonical_record["outcome"] == "blocked"
    assert canonical_record["failure_refs"][0]["status"] == "blocked"
    assert "project identity" in canonical_record["domain_refs"]["diagnostic"].lower()


def test_run_index_blocks_non_equivalent_run_and_worker_statuses(tmp_path):
    runtime = tmp_path / "runtime"
    _write_physical_go_run(
        runtime,
        team_project_id="demo-project",
        go_status="running",
        go_worker_status="unknown",
        team_worker_status="passed",
    )

    index = build_run_index(runtime)

    raw_entries = {entry["adapter_id"]: entry["record"] for entry in index["runs"]}
    assert raw_entries["go_run"]["domain_refs"]["legacy_status"] == "running"
    assert raw_entries["team_events"]["domain_refs"]["legacy_status"] == "passed"
    assert raw_entries["go_run"]["worker_results"][0]["status"] == "unknown"
    assert raw_entries["team_events"]["worker_results"][0]["status"] == "passed"
    canonical_record = index["canonical_runs"][0]["record"]
    _run_record_validator().validate(canonical_record)
    assert canonical_record["acceptance_state"] == "blocked"
    assert canonical_record["outcome"] == "blocked"
    assert canonical_record["failure_refs"][0]["status"] == "blocked"
    diagnostic = canonical_record["domain_refs"]["diagnostic"].lower()
    assert "run status conflict" in diagnostic
    assert "worker result conflict" in diagnostic


def test_run_index_keeps_valid_canonical_final_verdict_final_ready(tmp_path):
    runtime = tmp_path / "runtime"
    result_event_id = _write_physical_go_run(
        runtime,
        team_project_id="demo-project",
    )
    _write_team_final_ready(
        runtime,
        reviewer_id="reviewer-1",
        result_event_id=result_event_id,
    )

    index = build_run_index(runtime)

    raw_entries = {entry["adapter_id"]: entry["record"] for entry in index["runs"]}
    assert raw_entries["team_events"]["acceptance_state"] == "final_ready"
    canonical_record = index["canonical_runs"][0]["record"]
    _run_record_validator().validate(canonical_record)
    assert canonical_record["project_id"] == "demo-project"
    assert canonical_record["review_state"] == "review_passed"
    assert canonical_record["gate_state"] == "gate_passed"
    assert canonical_record["acceptance_state"] == "final_ready"
    assert canonical_record["review_refs"][0]["reviewer_id"] == "reviewer-1"
    assert {item["worker_id"] for item in canonical_record["worker_results"]} == {
        "coding-agent-1",
    }


def test_run_index_projects_legacy_adapters_into_schema_records(tmp_path):
    runtime = tmp_path / "runtime"
    report_path = runtime / "rdgoal-outbox" / "demo-project" / "packet-1" / "ExecutionReport.md"
    report_path.parent.mkdir(parents=True)
    report_path.write_text("## ExecutionReport\n\n- **Status**: pass\n", encoding="utf-8")
    (runtime / "rdgoal-events.jsonl").write_text(
        json.dumps({
            "event_type": "decision_made",
            "project_id": "demo-project",
            "payload": {
                "operation": "choose direction",
                "decision_mode": "recommend_execute",
                "dispatch_ready": True,
                "packet_dir": str(report_path.parent),
            },
            "timestamp": "2026-07-07T00:00:00Z",
            "event_id": "decision-1",
        }) + "\n",
        encoding="utf-8",
    )
    _write_json(runtime / "rdgoal-reports" / "demo-project" / "packet-1" / "execution-summary.json", {
        "packet_id": "packet-1",
        "project_id": "demo-project",
        "status": "passed",
        "changed_files": ["src/app.py"],
        "report_path": str(report_path),
        "ingested_at": "2026-07-07T00:01:00Z",
    })
    _write_json(runtime / "go-runs" / "go-demo" / "go-run.json", {
        "go_run_id": "go-demo",
        "project_id": "demo-project",
        "project_root": str(tmp_path / "project"),
        "requirement": "Build feature",
        "status": "passed",
        "execute": True,
        "created_at": "2026-07-07T00:02:00Z",
        "agents": [{
            "agent_id": "coding-agent-1",
            "status": "completed",
            "worker_status": "passed",
            "report_path": str(report_path),
        }],
    })
    (runtime / "team-events.jsonl").write_text(
        "\n".join([
            json.dumps({
                "event_type": "task_created",
                "run_id": "go-demo",
                "agent_id": "coding-agent-1",
                "payload": {
                    "project_id": "demo-project",
                    "targets": ["src/app.py"],
                    "context_refs": [
                        {
                            "ref_type": "legacy_context",
                            "ref_path": str(report_path.parent),
                            "context_id": "packet-1",
                        },
                        {
                            "ref_type": "legacy_task_spec",
                            "ref_path": str(report_path.parent / "TASKSPEC.json"),
                            "context_id": "packet-1",
                        },
                    ],
                },
                "timestamp": "2026-07-07T00:03:00Z",
                "event_id": "team-1",
            }),
            json.dumps({
                "event_type": "task_result",
                "run_id": "go-demo",
                "agent_id": "coding-agent-1",
                "payload": {"status": "passed", "report_path": str(report_path)},
                "timestamp": "2026-07-07T00:04:00Z",
                "event_id": "team-2",
            }),
            json.dumps({
                "event_type": "evidence_ref",
                "run_id": "go-demo",
                "agent_id": "coding-agent-1",
                "payload": {
                    "ref_type": "report",
                    "ref_path": str(report_path),
                    "source_event_id": "team-2",
                },
                "timestamp": "2026-07-07T00:04:01Z",
                "event_id": "team-3",
            }),
        ]) + "\n",
        encoding="utf-8",
    )
    atgo_dir = runtime / "atgo-runs" / "go-demo"
    atgo_dir.mkdir(parents=True)
    (atgo_dir / "review.yaml").write_text(
        "project_id: demo-project\nverdict: pass\nreviewer_role: reviewer\nreviewer_id: reviewer-1\nexecutor_id: coding-agent-1\n",
        encoding="utf-8",
    )
    _write_json(runtime / "test-runs" / "test-demo" / "test-run.json", {
        "test_run_id": "test-demo",
        "project_id": "demo-project",
        "status": "passed",
        "created_at": "2026-07-07T00:05:00Z",
        "report_path": str(runtime / "test-runs" / "test-demo" / "report.md"),
        "verdicts": {"codeReview": "PASS"},
        "quality_gate": {"passed": True},
    })
    (runtime / "test-runs" / "test-demo" / "report.md").write_text("test report\n", encoding="utf-8")
    paper_root = tmp_path / "paper"
    paper_root.mkdir()
    (paper_root / "PAPER_PROFILE.yaml").write_text("paper_id: demo-paper\ncurrent_stage: review\n", encoding="utf-8")
    (paper_root / "PAPER_STATE.yaml").write_text(
        "paper_id: demo-paper\nacceptance_status: human_required\nchain_trusted: true\n",
        encoding="utf-8",
    )
    (paper_root / "paper_task").mkdir()
    (paper_root / "paper_task" / "PAPER_TASK_INPUT.yaml").write_text("task_type: cssci_review\n", encoding="utf-8")

    index = build_run_index(runtime, paper_project_dirs=[paper_root])

    assert index["adapter_version"] == ADAPTER_VERSION
    grouped = _records_by_adapter(index)
    assert {"rdgoal", "go_run", "team_events", "atgo_evidence", "test_run", "paper"} <= set(grouped)
    validator = _run_record_validator()
    for entry in index["runs"]:
        assert entry["provenance"]["adapter_version"] == ADAPTER_VERSION
        assert entry["record"]["domain_refs"]["adapter_version"] == ADAPTER_VERSION
        validator.validate(entry["record"])

    go_record = grouped["go_run"][0]
    assert go_record["outcome"] == "passed"
    assert go_record["acceptance_state"] == "review_pending"
    assert go_record["projection_state"] == "completed"
    assert go_record["review_state"] == "review_pending"

    rdgoal_entry = next(entry for entry in index["runs"] if entry["adapter_id"] == "rdgoal")
    assert rdgoal_entry["provenance"]["source_path"].endswith("rdgoal-events.jsonl")
    assert rdgoal_entry["provenance"]["source_hash"].startswith("sha256:")

    atgo_record = grouped["atgo_evidence"][0]
    assert atgo_record["review_state"] == "review_passed"
    assert atgo_record["acceptance_state"] == "review_pending"
    assert atgo_record["review_refs"][0]["reviewer_role"] == "reviewer"
    assert atgo_record["review_refs"][0]["reviewer_id"] == "reviewer-1"

    test_record = grouped["test_run"][0]
    assert test_record["domain_refs"]["codeReview"] == "PASS"
    assert test_record["review_state"] != "review_passed"
    assert test_record["acceptance_state"] != "final_ready"

    team_record = grouped["team_events"][0]
    assert team_record["domain_refs"]["event_count"] == 3
    assert "evidence_ref" in team_record["domain_refs"]["event_types"]
    assert team_record["domain_refs"]["legacy_context_ref_count"] == 2
    assert team_record["domain_refs"]["legacy_context_ref_types"] == ["legacy_context", "legacy_task_spec"]
    context_refs = [ref for ref in team_record["evidence_refs"] if ref["kind"] == "context_packet"]
    assert len(context_refs) == 2
    assert {ref["supports"] for ref in context_refs} == {"limitation"}
    assert {ref["uri"] for ref in context_refs} == {str(report_path.parent), str(report_path.parent / "TASKSPEC.json")}
    assert {
        artifact["uri"] for artifact in team_record["artifact_refs"] if artifact["artifact_id"].startswith("artifact-team-context-")
    } == {str(report_path.parent), str(report_path.parent / "TASKSPEC.json")}
    assert [ref for ref in team_record["evidence_refs"] if ref["kind"] == "command_output"] == [{
        "evidence_id": "ev-team-team-2",
        "kind": "command_output",
        "uri": str(report_path),
        "supports": "outcome",
    }]

    paper_record = grouped["paper"][0]
    assert paper_record["outcome"] == "human_required"
    assert paper_record["acceptance_state"] == "blocked"
    assert paper_record["failure_refs"][0]["status"] == "blocked"
    assert paper_record["domain_refs"]["chain_trusted"] is True


def test_run_index_projects_explicit_team_evidence_without_task_result_report(tmp_path):
    runtime = tmp_path / "runtime"
    report_path = runtime / "reports" / "worker-report.md"
    report_path.parent.mkdir(parents=True)
    report_path.write_text("worker report\n", encoding="utf-8")
    (runtime / "team-events.jsonl").write_text(
        "\n".join([
            json.dumps({
                "event_type": "task_created",
                "run_id": "go-explicit",
                "agent_id": "coding-agent-1",
                "payload": {"project_id": "demo-project"},
                "timestamp": "2026-07-07T00:00:00Z",
                "event_id": "team-explicit-1",
            }),
            json.dumps({
                "event_type": "evidence_ref",
                "run_id": "go-explicit",
                "agent_id": "coding-agent-1",
                "payload": {
                    "ref_type": "report",
                    "ref_path": str(report_path),
                    "source_event_id": "team-explicit-result",
                },
                "timestamp": "2026-07-07T00:01:00Z",
                "event_id": "team-explicit-2",
            }),
        ]) + "\n",
        encoding="utf-8",
    )

    index = build_run_index(runtime)

    record = _records_by_adapter(index)["team_events"][0]
    _run_record_validator().validate(record)
    assert record["domain_refs"]["legacy_status"] == "running"
    assert record["evidence_refs"] == [{
        "evidence_id": "ev-team-team-explicit-result",
        "kind": "command_output",
        "uri": str(report_path),
        "supports": "outcome",
    }]


def test_run_index_keeps_team_review_without_final_verdict_review_pending(tmp_path):
    runtime = tmp_path / "runtime"
    review_path = runtime / "reviews" / "review.yaml"
    review_path.parent.mkdir(parents=True)
    review_path.write_text("verdict: pass\n", encoding="utf-8")
    (runtime / "team-events.jsonl").write_text(
        "\n".join([
            json.dumps({
                "event_type": "task_result",
                "run_id": "go-review-only",
                "agent_id": "coding-agent-1",
                "payload": {"status": "passed", "report_path": str(runtime / "reports" / "worker.md")},
                "timestamp": "2026-07-07T00:00:00Z",
                "event_id": "team-review-only-result",
            }),
            json.dumps({
                "event_type": "review_ref",
                "run_id": "go-review-only",
                "agent_id": "reviewer-1",
                "payload": {
                    "review_id": "review-go-review-only",
                    "reviewer_id": "reviewer-1",
                    "reviewer_role": "reviewer",
                    "executor_id": "coding-agent-1",
                    "verdict": "pass",
                    "ref_path": str(review_path),
                    "reviewed_evidence_refs": ["ev-team-team-review-only-result"],
                },
                "timestamp": "2026-07-07T00:01:00Z",
                "event_id": "team-review-only-review",
            }),
        ]) + "\n",
        encoding="utf-8",
    )

    record = _records_by_adapter(build_run_index(runtime))["team_events"][0]

    _run_record_validator().validate(record)
    assert record["review_state"] == "review_passed"
    assert record["gate_state"] == "not_evaluated"
    assert record["acceptance_state"] == "review_pending"
    assert "final_verdict_ref" not in record


def test_run_index_projects_team_final_verdict_to_final_ready(tmp_path):
    runtime = tmp_path / "runtime"
    report_path = runtime / "reports" / "worker.md"
    report_path.parent.mkdir(parents=True)
    report_path.write_text("worker report\n", encoding="utf-8")
    review_path = runtime / "reviews" / "review.yaml"
    review_path.parent.mkdir(parents=True)
    review_path.write_text("verdict: pass\n", encoding="utf-8")
    final_path = runtime / "final" / "final-verdict.json"
    prior_v1_path = runtime / "final" / "final-verdict-v1.json"
    prior_v0_path = runtime / "final" / "final-verdict-v0.json"
    gate_id = "gate-go-final-independent-review"
    _write_json(prior_v0_path, {
        "verdict_id": "fv-go-final-v0",
        "produced_by": "go-evidence-finalizer",
        "produced_at": "2026-07-07T00:00:00Z",
        "producer_role": "governance",
        "final_state": "blocked",
        "inputs_reviewed": [str(review_path)],
        "gate_summary": [{
            "gate_id": "gate-go-final-v0-independent-review",
            "result": "blocked",
            "evidence_path": str(review_path),
        }],
        "reviewer_summary": {
            "reviewer_id": "reviewer-1",
            "verdict": "blocked",
            "evidence_path": str(review_path),
        },
        "limitations": [],
        "human_or_governance_reference": "go-evidence-finalize:go-final-v0",
    })
    _write_json(prior_v1_path, {
        "verdict_id": "fv-go-final-v1",
        "produced_by": "go-evidence-finalizer",
        "produced_at": "2026-07-07T00:01:00Z",
        "producer_role": "governance",
        "final_state": "accepted_with_limitation",
        "inputs_reviewed": [str(review_path), str(prior_v0_path)],
        "gate_summary": [{
            "gate_id": "gate-go-final-v1-independent-review",
            "result": "warning",
            "evidence_path": str(review_path),
        }],
        "reviewer_summary": {
            "reviewer_id": "reviewer-1",
            "verdict": "pass",
            "evidence_path": str(review_path),
        },
        "limitations": ["prior verdict was incomplete"],
        "human_or_governance_reference": "go-evidence-finalize:go-final-v1",
        "supersedes": {
            "verdict_id": "fv-go-final-v0",
            "uri": str(prior_v0_path),
            "reason": "Governance review replaced the blocked draft.",
        },
    })
    _write_json(final_path, {
        "verdict_id": "fv-go-final",
        "produced_by": "go-evidence-finalizer",
        "produced_at": "2026-07-07T00:02:00Z",
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
        "human_or_governance_reference": "go-evidence-finalize:go-final",
        "supersedes": {
            "verdict_id": "fv-go-final-v1",
            "uri": str(prior_v1_path),
            "reason": "New independent review evidence superseded the prior verdict.",
        },
    })
    context_packet_path, context_ledger_path = _write_sealed_context(runtime, "go-final-context")
    (runtime / "team-events.jsonl").write_text(
        "\n".join([
            json.dumps({
                "event_type": "task_created",
                "run_id": "go-final",
                "agent_id": "coding-agent-1",
                "payload": {
                    "project_id": "demo-project",
                    "context_refs": [
                        {
                            "ref_type": "context_packet",
                            "ref_path": str(context_packet_path),
                            "context_id": "cp-go-final-context",
                        },
                        {
                            "ref_type": "context_ledger",
                            "ref_path": str(context_ledger_path),
                            "context_id": "cl-go-final-context",
                        },
                    ],
                },
                "timestamp": "2026-07-07T00:00:00Z",
                "event_id": "team-final-created",
            }),
            json.dumps({
                "event_type": "task_result",
                "run_id": "go-final",
                "agent_id": "coding-agent-1",
                "payload": {"status": "passed", "report_path": str(report_path)},
                "timestamp": "2026-07-07T00:00:00Z",
                "event_id": "team-final-result",
            }),
            json.dumps({
                "event_type": "review_ref",
                "run_id": "go-final",
                "agent_id": "reviewer-1",
                "payload": {
                    "review_id": "review-go-final",
                    "reviewer_id": "reviewer-1",
                    "reviewer_role": "reviewer",
                    "executor_id": "coding-agent-1",
                    "verdict": "pass",
                    "ref_path": str(review_path),
                    "reviewed_evidence_refs": ["ev-team-team-final-result"],
                },
                "timestamp": "2026-07-07T00:01:00Z",
                "event_id": "team-final-review",
            }),
            json.dumps({
                "event_type": "final_verdict_ref",
                "run_id": "go-final",
                "agent_id": "go-evidence-finalizer",
                "payload": {
                    "verdict_id": "fv-go-final",
                    "produced_by": "go-evidence-finalizer",
                    "producer_role": "governance",
                    "final_state": "final_ready",
                    "ref_path": str(final_path),
                    "review_ref": "review-go-final",
                    "gate_refs": [gate_id],
                    "gate_summary": [{
                        "gate_id": gate_id,
                        "result": "pass",
                        "evidence_path": str(review_path),
                    }],
                    "limitations": [],
                    "human_or_governance_reference": "go-evidence-finalize:go-final",
                },
                "timestamp": "2026-07-07T00:02:00Z",
                "event_id": "team-final-verdict",
            }),
        ]) + "\n",
        encoding="utf-8",
    )

    record = _records_by_adapter(build_run_index(runtime))["team_events"][0]

    _run_record_validator().validate(record)
    assert record["review_state"] == "review_passed"
    assert record["gate_state"] == "gate_passed"
    assert record["acceptance_state"] == "final_ready"
    assert record["final_verdict_ref"] == {
        "verdict_id": "fv-go-final",
        "producer_role": "governance",
        "final_state": "final_ready",
        "uri": str(final_path),
        "review_ref": "review-go-final",
        "gate_refs": [gate_id],
        "supersedes": {
            "verdict_id": "fv-go-final-v1",
            "uri": str(prior_v1_path),
            "reason": "New independent review evidence superseded the prior verdict.",
        },
        "supersession_chain": [
            {
                "verdict_id": "fv-go-final-v1",
                "uri": str(prior_v1_path),
                "reason": "New independent review evidence superseded the prior verdict.",
                "resolved": True,
                "resolution_state": "resolved",
                "final_state": "accepted_with_limitation",
            },
            {
                "verdict_id": "fv-go-final-v0",
                "uri": str(prior_v0_path),
                "reason": "Governance review replaced the blocked draft.",
                "resolved": True,
                "resolution_state": "resolved",
                "final_state": "blocked",
            },
        ],
    }
    assert {ref["kind"] for ref in record["evidence_refs"]} >= {"command_output", "review", "final_verdict"}
    assert [ref["kind"] for ref in record["evidence_refs"] if ref["kind"] == "context_packet"]
    assert {"context_packet", "context_ledger"} <= {artifact["kind"] for artifact in record["artifact_refs"]}
    final_evidence_refs = [ref for ref in record["evidence_refs"] if ref["kind"] == "final_verdict"]
    assert final_evidence_refs == [{
        "evidence_id": "ev-team-final-verdict-team-final-verdict",
        "kind": "final_verdict",
        "uri": str(final_path),
        "supports": "acceptance",
    }]


def test_run_index_blocks_final_ready_without_sealed_context(tmp_path):
    runtime = tmp_path / "runtime"
    report_path = runtime / "reports" / "worker.md"
    report_path.parent.mkdir(parents=True)
    report_path.write_text("worker report\n", encoding="utf-8")
    review_path = runtime / "reviews" / "review.yaml"
    review_path.parent.mkdir(parents=True)
    review_path.write_text("verdict: pass\n", encoding="utf-8")
    final_path = runtime / "final" / "final-verdict.json"
    gate_id = "gate-go-no-context-independent-review"
    _write_json(final_path, {
        "verdict_id": "fv-go-no-context",
        "produced_by": "go-evidence-finalizer",
        "produced_at": "2026-07-07T00:02:00Z",
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
        "human_or_governance_reference": "go-evidence-finalize:go-no-context",
    })
    (runtime / "team-events.jsonl").write_text(
        "\n".join([
            json.dumps({
                "event_type": "task_result",
                "run_id": "go-no-context",
                "agent_id": "coding-agent-1",
                "payload": {"status": "passed", "report_path": str(report_path)},
                "timestamp": "2026-07-07T00:00:00Z",
                "event_id": "team-no-context-result",
            }),
            json.dumps({
                "event_type": "review_ref",
                "run_id": "go-no-context",
                "agent_id": "reviewer-1",
                "payload": {
                    "review_id": "review-go-no-context",
                    "reviewer_id": "reviewer-1",
                    "reviewer_role": "reviewer",
                    "executor_id": "coding-agent-1",
                    "verdict": "pass",
                    "ref_path": str(review_path),
                    "reviewed_evidence_refs": ["ev-team-team-no-context-result"],
                },
                "timestamp": "2026-07-07T00:01:00Z",
                "event_id": "team-no-context-review",
            }),
            json.dumps({
                "event_type": "final_verdict_ref",
                "run_id": "go-no-context",
                "agent_id": "go-evidence-finalizer",
                "payload": {
                    "verdict_id": "fv-go-no-context",
                    "produced_by": "go-evidence-finalizer",
                    "producer_role": "governance",
                    "final_state": "final_ready",
                    "ref_path": str(final_path),
                    "review_ref": "review-go-no-context",
                    "gate_refs": [gate_id],
                    "gate_summary": [{
                        "gate_id": gate_id,
                        "result": "pass",
                        "evidence_path": str(review_path),
                    }],
                },
                "timestamp": "2026-07-07T00:02:00Z",
                "event_id": "team-no-context-final",
            }),
        ]) + "\n",
        encoding="utf-8",
    )

    record = _records_by_adapter(build_run_index(runtime))["team_events"][0]

    _run_record_validator().validate(record)
    assert record["outcome"] == "blocked"
    assert record["acceptance_state"] == "blocked"
    assert "final_verdict_ref" not in record
    assert record["failure_refs"][0]["status"] == "blocked"


def test_run_index_blocks_final_ready_without_task_result(tmp_path):
    runtime = tmp_path / "runtime"
    review_path = runtime / "reviews" / "review.yaml"
    review_path.parent.mkdir(parents=True)
    review_path.write_text("verdict: pass\n", encoding="utf-8")
    final_path = runtime / "final" / "final-verdict.json"
    gate_id = "gate-go-no-task-result-independent-review"
    _write_json(final_path, {
        "verdict_id": "fv-go-no-task-result",
        "produced_by": "go-evidence-finalizer",
        "produced_at": "2026-07-07T00:02:00Z",
        "producer_role": "governance",
        "final_state": "final_ready",
        "inputs_reviewed": [str(review_path)],
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
        "human_or_governance_reference": "go-evidence-finalize:go-no-task-result",
    })
    (runtime / "team-events.jsonl").write_text(
        "\n".join([
            _sealed_context_created_event(runtime, "go-no-task-result"),
            json.dumps({
                "event_type": "review_ref",
                "run_id": "go-no-task-result",
                "agent_id": "reviewer-1",
                "payload": {
                    "review_id": "review-go-no-task-result",
                    "reviewer_id": "reviewer-1",
                    "reviewer_role": "reviewer",
                    "executor_id": "coding-agent-1",
                    "verdict": "pass",
                    "ref_path": str(review_path),
                    "reviewed_evidence_refs": ["ev-team-missing-task-result"],
                },
                "timestamp": "2026-07-07T00:01:00Z",
                "event_id": "team-no-task-result-review",
            }),
            json.dumps({
                "event_type": "final_verdict_ref",
                "run_id": "go-no-task-result",
                "agent_id": "go-evidence-finalizer",
                "payload": {
                    "verdict_id": "fv-go-no-task-result",
                    "produced_by": "go-evidence-finalizer",
                    "producer_role": "governance",
                    "final_state": "final_ready",
                    "ref_path": str(final_path),
                    "review_ref": "review-go-no-task-result",
                    "gate_refs": [gate_id],
                },
                "timestamp": "2026-07-07T00:02:00Z",
                "event_id": "team-no-task-result-final",
            }),
        ]) + "\n",
        encoding="utf-8",
    )

    record = _records_by_adapter(build_run_index(runtime))["team_events"][0]

    _run_record_validator().validate(record)
    assert record["outcome"] == "blocked"
    assert record["acceptance_state"] == "blocked"
    assert "final_verdict_ref" not in record
    assert record["failure_refs"][0]["status"] == "blocked"


def test_run_index_blocks_invalid_final_verdict_supersedes_metadata(tmp_path):
    runtime = tmp_path / "runtime"
    review_path = runtime / "reviews" / "review.yaml"
    review_path.parent.mkdir(parents=True)
    review_path.write_text("verdict: pass\n", encoding="utf-8")
    final_path = runtime / "final" / "final-verdict.json"
    gate_id = "gate-go-invalid-supersedes-independent-review"
    _write_json(final_path, {
        "verdict_id": "fv-go-invalid-supersedes",
        "produced_by": "go-evidence-finalizer",
        "produced_at": "2026-07-07T00:02:00Z",
        "producer_role": "governance",
        "final_state": "final_ready",
        "inputs_reviewed": [str(review_path)],
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
        "human_or_governance_reference": "go-evidence-finalize:go-invalid-supersedes",
        "supersedes": {
            "verdict_id": "fv-go-invalid-supersedes-v1",
            "uri": str(runtime / "final" / "final-verdict-v1.json"),
        },
    })
    (runtime / "team-events.jsonl").write_text(
        "\n".join([
            json.dumps({
                "event_type": "task_result",
                "run_id": "go-invalid-supersedes",
                "agent_id": "coding-agent-1",
                "payload": {"status": "passed"},
                "timestamp": "2026-07-07T00:00:00Z",
                "event_id": "team-invalid-supersedes-result",
            }),
            json.dumps({
                "event_type": "review_ref",
                "run_id": "go-invalid-supersedes",
                "agent_id": "reviewer-1",
                "payload": {
                    "review_id": "review-go-invalid-supersedes",
                    "reviewer_id": "reviewer-1",
                    "reviewer_role": "reviewer",
                    "executor_id": "coding-agent-1",
                    "verdict": "pass",
                    "ref_path": str(review_path),
                    "reviewed_evidence_refs": ["ev-team-team-invalid-supersedes-result"],
                },
                "timestamp": "2026-07-07T00:01:00Z",
                "event_id": "team-invalid-supersedes-review",
            }),
            json.dumps({
                "event_type": "final_verdict_ref",
                "run_id": "go-invalid-supersedes",
                "agent_id": "go-evidence-finalizer",
                "payload": {
                    "verdict_id": "fv-go-invalid-supersedes",
                    "produced_by": "go-evidence-finalizer",
                    "producer_role": "governance",
                    "final_state": "final_ready",
                    "ref_path": str(final_path),
                    "review_ref": "review-go-invalid-supersedes",
                    "gate_refs": [gate_id],
                },
                "timestamp": "2026-07-07T00:02:00Z",
                "event_id": "team-invalid-supersedes-final",
            }),
        ]) + "\n",
        encoding="utf-8",
    )

    record = _records_by_adapter(build_run_index(runtime))["team_events"][0]

    _run_record_validator().validate(record)
    assert record["acceptance_state"] == "blocked"
    assert "final_verdict_ref" not in record
    assert record["failure_refs"][0]["status"] == "blocked"
    assert record["failure_refs"][0]["uri"] == str(final_path)


def test_run_index_keeps_missing_superseded_verdict_non_authoritative(tmp_path):
    runtime = tmp_path / "runtime"
    review_path = runtime / "reviews" / "review.yaml"
    review_path.parent.mkdir(parents=True)
    review_path.write_text("verdict: pass\n", encoding="utf-8")
    final_path = runtime / "final" / "final-verdict.json"
    missing_prior_path = runtime / "final" / "missing-final-verdict-v1.json"
    gate_id = "gate-go-missing-superseded-independent-review"
    _write_json(final_path, {
        "verdict_id": "fv-go-missing-superseded",
        "produced_by": "go-evidence-finalizer",
        "produced_at": "2026-07-07T00:02:00Z",
        "producer_role": "governance",
        "final_state": "final_ready",
        "inputs_reviewed": [str(review_path)],
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
        "human_or_governance_reference": "go-evidence-finalize:go-missing-superseded",
        "supersedes": {
            "verdict_id": "fv-go-missing-superseded-v1",
            "uri": str(missing_prior_path),
            "reason": "Current governance verdict superseded a missing historical artifact.",
        },
    })
    (runtime / "team-events.jsonl").write_text(
        "\n".join([
            _sealed_context_created_event(runtime, "go-missing-superseded"),
            json.dumps({
                "event_type": "task_result",
                "run_id": "go-missing-superseded",
                "agent_id": "coding-agent-1",
                "payload": {"status": "passed"},
                "timestamp": "2026-07-07T00:00:00Z",
                "event_id": "team-missing-superseded-result",
            }),
            json.dumps({
                "event_type": "review_ref",
                "run_id": "go-missing-superseded",
                "agent_id": "reviewer-1",
                "payload": {
                    "review_id": "review-go-missing-superseded",
                    "reviewer_id": "reviewer-1",
                    "reviewer_role": "reviewer",
                    "executor_id": "coding-agent-1",
                    "verdict": "pass",
                    "ref_path": str(review_path),
                    "reviewed_evidence_refs": ["ev-team-team-missing-superseded-result"],
                },
                "timestamp": "2026-07-07T00:01:00Z",
                "event_id": "team-missing-superseded-review",
            }),
            json.dumps({
                "event_type": "final_verdict_ref",
                "run_id": "go-missing-superseded",
                "agent_id": "go-evidence-finalizer",
                "payload": {
                    "verdict_id": "fv-go-missing-superseded",
                    "produced_by": "go-evidence-finalizer",
                    "producer_role": "governance",
                    "final_state": "final_ready",
                    "ref_path": str(final_path),
                    "review_ref": "review-go-missing-superseded",
                    "gate_refs": [gate_id],
                },
                "timestamp": "2026-07-07T00:02:00Z",
                "event_id": "team-missing-superseded-final",
            }),
        ]) + "\n",
        encoding="utf-8",
    )

    record = _records_by_adapter(build_run_index(runtime))["team_events"][0]

    _run_record_validator().validate(record)
    assert record["acceptance_state"] == "final_ready"
    assert record["final_verdict_ref"]["supersession_chain"] == [{
        "verdict_id": "fv-go-missing-superseded-v1",
        "uri": str(missing_prior_path),
        "reason": "Current governance verdict superseded a missing historical artifact.",
        "resolved": False,
        "resolution_state": "missing",
        "diagnostic": "missing superseded FinalVerdict artifact",
    }]
    assert [ref for ref in record["evidence_refs"] if ref["kind"] == "final_verdict"] == [{
        "evidence_id": "ev-team-final-verdict-team-missing-superseded-final",
        "kind": "final_verdict",
        "uri": str(final_path),
        "supports": "acceptance",
    }]


def test_run_index_keeps_mismatched_superseded_verdict_unresolved(tmp_path):
    runtime = tmp_path / "runtime"
    review_path = runtime / "reviews" / "review.yaml"
    review_path.parent.mkdir(parents=True)
    review_path.write_text("verdict: pass\n", encoding="utf-8")
    final_path = runtime / "final" / "final-verdict.json"
    prior_path = runtime / "final" / "final-verdict-v1.json"
    gate_id = "gate-go-mismatched-superseded-independent-review"
    _write_json(prior_path, {
        "verdict_id": "fv-different-prior",
        "produced_by": "go-evidence-finalizer",
        "produced_at": "2026-07-07T00:01:00Z",
        "producer_role": "governance",
        "final_state": "blocked",
        "inputs_reviewed": [str(review_path)],
        "gate_summary": [{
            "gate_id": "gate-different-prior",
            "result": "blocked",
            "evidence_path": str(review_path),
        }],
        "reviewer_summary": {
            "reviewer_id": "reviewer-1",
            "verdict": "blocked",
            "evidence_path": str(review_path),
        },
        "limitations": [],
        "human_or_governance_reference": "go-evidence-finalize:different-prior",
    })
    _write_json(final_path, {
        "verdict_id": "fv-go-mismatched-superseded",
        "produced_by": "go-evidence-finalizer",
        "produced_at": "2026-07-07T00:02:00Z",
        "producer_role": "governance",
        "final_state": "final_ready",
        "inputs_reviewed": [str(review_path)],
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
        "human_or_governance_reference": "go-evidence-finalize:go-mismatched-superseded",
        "supersedes": {
            "verdict_id": "fv-go-mismatched-superseded-v1",
            "uri": str(prior_path),
            "reason": "Current governance verdict pointed at a mismatched artifact.",
        },
    })
    (runtime / "team-events.jsonl").write_text(
        "\n".join([
            _sealed_context_created_event(runtime, "go-mismatched-superseded"),
            json.dumps({
                "event_type": "task_result",
                "run_id": "go-mismatched-superseded",
                "agent_id": "coding-agent-1",
                "payload": {"status": "passed"},
                "timestamp": "2026-07-07T00:00:00Z",
                "event_id": "team-mismatched-superseded-result",
            }),
            json.dumps({
                "event_type": "review_ref",
                "run_id": "go-mismatched-superseded",
                "agent_id": "reviewer-1",
                "payload": {
                    "review_id": "review-go-mismatched-superseded",
                    "reviewer_id": "reviewer-1",
                    "reviewer_role": "reviewer",
                    "executor_id": "coding-agent-1",
                    "verdict": "pass",
                    "ref_path": str(review_path),
                    "reviewed_evidence_refs": ["ev-team-team-mismatched-superseded-result"],
                },
                "timestamp": "2026-07-07T00:01:00Z",
                "event_id": "team-mismatched-superseded-review",
            }),
            json.dumps({
                "event_type": "final_verdict_ref",
                "run_id": "go-mismatched-superseded",
                "agent_id": "go-evidence-finalizer",
                "payload": {
                    "verdict_id": "fv-go-mismatched-superseded",
                    "produced_by": "go-evidence-finalizer",
                    "producer_role": "governance",
                    "final_state": "final_ready",
                    "ref_path": str(final_path),
                    "review_ref": "review-go-mismatched-superseded",
                    "gate_refs": [gate_id],
                },
                "timestamp": "2026-07-07T00:02:00Z",
                "event_id": "team-mismatched-superseded-final",
            }),
        ]) + "\n",
        encoding="utf-8",
    )

    record = _records_by_adapter(build_run_index(runtime))["team_events"][0]

    _run_record_validator().validate(record)
    assert record["acceptance_state"] == "final_ready"
    assert record["final_verdict_ref"]["supersession_chain"] == [{
        "verdict_id": "fv-go-mismatched-superseded-v1",
        "uri": str(prior_path),
        "reason": "Current governance verdict pointed at a mismatched artifact.",
        "resolved": False,
        "resolution_state": "id_mismatch",
        "diagnostic": "superseded verdict_id does not match artifact",
    }]


def test_run_index_marks_invalid_superseded_verdict_unresolved(tmp_path):
    runtime = tmp_path / "runtime"
    review_path = runtime / "reviews" / "review.yaml"
    review_path.parent.mkdir(parents=True)
    review_path.write_text("verdict: pass\n", encoding="utf-8")
    final_path = runtime / "final" / "final-verdict.json"
    prior_path = runtime / "final" / "invalid-final-verdict-v1.json"
    prior_path.parent.mkdir(parents=True)
    prior_path.write_text("{bad json\n", encoding="utf-8")
    gate_id = "gate-go-invalid-superseded-independent-review"
    _write_json(final_path, {
        "verdict_id": "fv-go-invalid-superseded",
        "produced_by": "go-evidence-finalizer",
        "produced_at": "2026-07-07T00:02:00Z",
        "producer_role": "governance",
        "final_state": "final_ready",
        "inputs_reviewed": [str(review_path)],
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
        "human_or_governance_reference": "go-evidence-finalize:go-invalid-superseded",
        "supersedes": {
            "verdict_id": "fv-go-invalid-superseded-v1",
            "uri": str(prior_path),
            "reason": "Current governance verdict pointed at an invalid historical artifact.",
        },
    })
    (runtime / "team-events.jsonl").write_text(
        "\n".join([
            _sealed_context_created_event(runtime, "go-invalid-superseded"),
            json.dumps({
                "event_type": "task_result",
                "run_id": "go-invalid-superseded",
                "agent_id": "coding-agent-1",
                "payload": {"status": "passed"},
                "timestamp": "2026-07-07T00:00:00Z",
                "event_id": "team-invalid-superseded-result",
            }),
            json.dumps({
                "event_type": "review_ref",
                "run_id": "go-invalid-superseded",
                "agent_id": "reviewer-1",
                "payload": {
                    "review_id": "review-go-invalid-superseded",
                    "reviewer_id": "reviewer-1",
                    "reviewer_role": "reviewer",
                    "executor_id": "coding-agent-1",
                    "verdict": "pass",
                    "ref_path": str(review_path),
                    "reviewed_evidence_refs": ["ev-team-team-invalid-superseded-result"],
                },
                "timestamp": "2026-07-07T00:01:00Z",
                "event_id": "team-invalid-superseded-review",
            }),
            json.dumps({
                "event_type": "final_verdict_ref",
                "run_id": "go-invalid-superseded",
                "agent_id": "go-evidence-finalizer",
                "payload": {
                    "verdict_id": "fv-go-invalid-superseded",
                    "produced_by": "go-evidence-finalizer",
                    "producer_role": "governance",
                    "final_state": "final_ready",
                    "ref_path": str(final_path),
                    "review_ref": "review-go-invalid-superseded",
                    "gate_refs": [gate_id],
                },
                "timestamp": "2026-07-07T00:02:00Z",
                "event_id": "team-invalid-superseded-final",
            }),
        ]) + "\n",
        encoding="utf-8",
    )

    record = _records_by_adapter(build_run_index(runtime))["team_events"][0]

    _run_record_validator().validate(record)
    assert record["acceptance_state"] == "final_ready"
    assert record["final_verdict_ref"]["supersession_chain"] == [{
        "verdict_id": "fv-go-invalid-superseded-v1",
        "uri": str(prior_path),
        "reason": "Current governance verdict pointed at an invalid historical artifact.",
        "resolved": False,
        "resolution_state": "invalid",
        "diagnostic": "invalid superseded FinalVerdict artifact",
    }]


def test_run_index_marks_supersession_chain_depth_limited(tmp_path):
    runtime = tmp_path / "runtime"
    review_path = runtime / "reviews" / "review.yaml"
    review_path.parent.mkdir(parents=True)
    review_path.write_text("verdict: pass\n", encoding="utf-8")
    final_path = runtime / "final" / "final-verdict.json"
    gate_id = "gate-go-depth-limited-independent-review"
    prior_paths = {
        index: runtime / "final" / f"final-verdict-v{index}.json"
        for index in range(1, 7)
    }
    for index in range(6, 0, -1):
        payload = {
            "verdict_id": f"fv-go-depth-limited-v{index}",
            "produced_by": "go-evidence-finalizer",
            "produced_at": f"2026-07-07T00:0{index}:00Z",
            "producer_role": "governance",
            "final_state": "accepted_with_limitation",
            "inputs_reviewed": [str(review_path)],
            "gate_summary": [{
                "gate_id": f"gate-go-depth-limited-v{index}",
                "result": "warning",
                "evidence_path": str(review_path),
            }],
            "reviewer_summary": {
                "reviewer_id": "reviewer-1",
                "verdict": "pass",
                "evidence_path": str(review_path),
            },
            "limitations": [f"historical verdict v{index}"],
            "human_or_governance_reference": f"go-evidence-finalize:go-depth-limited-v{index}",
        }
        if index < 6:
            payload["supersedes"] = {
                "verdict_id": f"fv-go-depth-limited-v{index + 1}",
                "uri": str(prior_paths[index + 1]),
                "reason": f"Historical verdict v{index} superseded v{index + 1}.",
            }
        _write_json(prior_paths[index], payload)
    _write_json(final_path, {
        "verdict_id": "fv-go-depth-limited",
        "produced_by": "go-evidence-finalizer",
        "produced_at": "2026-07-07T00:07:00Z",
        "producer_role": "governance",
        "final_state": "final_ready",
        "inputs_reviewed": [str(review_path)],
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
        "human_or_governance_reference": "go-evidence-finalize:go-depth-limited",
        "supersedes": {
            "verdict_id": "fv-go-depth-limited-v1",
            "uri": str(prior_paths[1]),
            "reason": "Current governance verdict superseded a long historical chain.",
        },
    })
    (runtime / "team-events.jsonl").write_text(
        "\n".join([
            _sealed_context_created_event(runtime, "go-depth-limited"),
            json.dumps({
                "event_type": "task_result",
                "run_id": "go-depth-limited",
                "agent_id": "coding-agent-1",
                "payload": {"status": "passed"},
                "timestamp": "2026-07-07T00:00:00Z",
                "event_id": "team-depth-limited-result",
            }),
            json.dumps({
                "event_type": "review_ref",
                "run_id": "go-depth-limited",
                "agent_id": "reviewer-1",
                "payload": {
                    "review_id": "review-go-depth-limited",
                    "reviewer_id": "reviewer-1",
                    "reviewer_role": "reviewer",
                    "executor_id": "coding-agent-1",
                    "verdict": "pass",
                    "ref_path": str(review_path),
                    "reviewed_evidence_refs": ["ev-team-team-depth-limited-result"],
                },
                "timestamp": "2026-07-07T00:01:00Z",
                "event_id": "team-depth-limited-review",
            }),
            json.dumps({
                "event_type": "final_verdict_ref",
                "run_id": "go-depth-limited",
                "agent_id": "go-evidence-finalizer",
                "payload": {
                    "verdict_id": "fv-go-depth-limited",
                    "produced_by": "go-evidence-finalizer",
                    "producer_role": "governance",
                    "final_state": "final_ready",
                    "ref_path": str(final_path),
                    "review_ref": "review-go-depth-limited",
                    "gate_refs": [gate_id],
                },
                "timestamp": "2026-07-07T00:02:00Z",
                "event_id": "team-depth-limited-final",
            }),
        ]) + "\n",
        encoding="utf-8",
    )

    record = _records_by_adapter(build_run_index(runtime))["team_events"][0]

    _run_record_validator().validate(record)
    assert record["acceptance_state"] == "final_ready"
    chain = record["final_verdict_ref"]["supersession_chain"]
    assert len(chain) == 5
    assert chain[-1] == {
        "verdict_id": "fv-go-depth-limited-v5",
        "uri": str(prior_paths[5]),
        "reason": "Historical verdict v4 superseded v5.",
        "resolved": True,
        "resolution_state": "depth_limited",
        "diagnostic": "supersession chain depth limit reached",
        "final_state": "accepted_with_limitation",
    }


def test_run_index_stops_supersession_chain_before_duplicate_cycle_entry(tmp_path):
    runtime = tmp_path / "runtime"
    review_path = runtime / "reviews" / "review.yaml"
    review_path.parent.mkdir(parents=True)
    review_path.write_text("verdict: pass\n", encoding="utf-8")
    final_path = runtime / "final" / "final-verdict.json"
    prior_path = runtime / "final" / "final-verdict-v1.json"
    gate_id = "gate-go-cyclic-superseded-independent-review"
    base_payload = {
        "produced_by": "go-evidence-finalizer",
        "producer_role": "governance",
        "inputs_reviewed": [str(review_path)],
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
        "human_or_governance_reference": "go-evidence-finalize:go-cyclic-superseded",
    }
    _write_json(prior_path, {
        **base_payload,
        "verdict_id": "fv-go-cyclic-superseded-v1",
        "produced_at": "2026-07-07T00:01:00Z",
        "final_state": "accepted_with_limitation",
        "supersedes": {
            "verdict_id": "fv-go-cyclic-superseded",
            "uri": str(final_path),
            "reason": "Malformed history points back to the current verdict.",
        },
    })
    _write_json(final_path, {
        **base_payload,
        "verdict_id": "fv-go-cyclic-superseded",
        "produced_at": "2026-07-07T00:02:00Z",
        "final_state": "final_ready",
        "supersedes": {
            "verdict_id": "fv-go-cyclic-superseded-v1",
            "uri": str(prior_path),
            "reason": "Current verdict points to a cyclic historical artifact.",
        },
    })
    (runtime / "team-events.jsonl").write_text(
        "\n".join([
            _sealed_context_created_event(runtime, "go-cyclic-superseded"),
            json.dumps({
                "event_type": "task_result",
                "run_id": "go-cyclic-superseded",
                "agent_id": "coding-agent-1",
                "payload": {"status": "passed"},
                "timestamp": "2026-07-07T00:00:00Z",
                "event_id": "team-cyclic-superseded-result",
            }),
            json.dumps({
                "event_type": "review_ref",
                "run_id": "go-cyclic-superseded",
                "agent_id": "reviewer-1",
                "payload": {
                    "review_id": "review-go-cyclic-superseded",
                    "reviewer_id": "reviewer-1",
                    "reviewer_role": "reviewer",
                    "executor_id": "coding-agent-1",
                    "verdict": "pass",
                    "ref_path": str(review_path),
                    "reviewed_evidence_refs": ["ev-team-team-cyclic-superseded-result"],
                },
                "timestamp": "2026-07-07T00:01:00Z",
                "event_id": "team-cyclic-superseded-review",
            }),
            json.dumps({
                "event_type": "final_verdict_ref",
                "run_id": "go-cyclic-superseded",
                "agent_id": "go-evidence-finalizer",
                "payload": {
                    "verdict_id": "fv-go-cyclic-superseded",
                    "produced_by": "go-evidence-finalizer",
                    "producer_role": "governance",
                    "final_state": "final_ready",
                    "ref_path": str(final_path),
                    "review_ref": "review-go-cyclic-superseded",
                    "gate_refs": [gate_id],
                },
                "timestamp": "2026-07-07T00:02:00Z",
                "event_id": "team-cyclic-superseded-final",
            }),
        ]) + "\n",
        encoding="utf-8",
    )

    record = _records_by_adapter(build_run_index(runtime))["team_events"][0]

    _run_record_validator().validate(record)
    assert record["acceptance_state"] == "final_ready"
    assert record["final_verdict_ref"]["supersession_chain"] == [
        {
            "verdict_id": "fv-go-cyclic-superseded-v1",
            "uri": str(prior_path),
            "reason": "Current verdict points to a cyclic historical artifact.",
            "resolved": True,
            "resolution_state": "cycle",
            "diagnostic": "supersession chain cycle detected",
            "final_state": "accepted_with_limitation",
        }
    ]


def test_run_index_blocks_team_self_review_and_worker_final_verdict(tmp_path):
    runtime = tmp_path / "runtime"
    review_path = runtime / "reviews" / "review.yaml"
    review_path.parent.mkdir(parents=True)
    review_path.write_text("verdict: pass\n", encoding="utf-8")
    final_path = runtime / "final" / "final-verdict.json"
    _write_json(final_path, {
        "verdict_id": "fv-go-unsafe",
        "produced_by": "coding-agent-1",
        "produced_at": "2026-07-07T00:02:00Z",
        "producer_role": "worker",
        "final_state": "final_ready",
        "inputs_reviewed": [str(review_path)],
        "gate_summary": [{
            "gate_id": "gate-go-unsafe-independent-review",
            "result": "pass",
            "evidence_path": str(review_path),
        }],
        "reviewer_summary": {
            "reviewer_id": "reviewer-1",
            "verdict": "pass",
            "evidence_path": str(review_path),
        },
        "limitations": [],
        "human_or_governance_reference": "go-evidence-finalize:go-unsafe",
    })
    (runtime / "team-events.jsonl").write_text(
        "\n".join([
            json.dumps({
                "event_type": "task_result",
                "run_id": "go-unsafe",
                "agent_id": "coding-agent-1",
                "payload": {"status": "passed"},
                "timestamp": "2026-07-07T00:00:00Z",
                "event_id": "team-unsafe-result",
            }),
            json.dumps({
                "event_type": "review_ref",
                "run_id": "go-unsafe",
                "agent_id": "coding-agent-1",
                "payload": {
                    "review_id": "review-go-unsafe",
                    "reviewer_id": "coding-agent-1",
                    "reviewer_role": "worker",
                    "executor_id": "coding-agent-1",
                    "verdict": "pass",
                    "ref_path": str(review_path),
                    "reviewed_evidence_refs": ["ev-team-team-unsafe-result"],
                },
                "timestamp": "2026-07-07T00:01:00Z",
                "event_id": "team-unsafe-review",
            }),
            json.dumps({
                "event_type": "final_verdict_ref",
                "run_id": "go-unsafe",
                "agent_id": "coding-agent-1",
                "payload": {
                    "verdict_id": "fv-go-unsafe",
                    "produced_by": "coding-agent-1",
                    "producer_role": "worker",
                    "final_state": "final_ready",
                    "ref_path": str(final_path),
                    "review_ref": "review-go-unsafe",
                    "gate_refs": ["gate-go-unsafe-independent-review"],
                    "gate_summary": [{
                        "gate_id": "gate-go-unsafe-independent-review",
                        "result": "pass",
                        "evidence_path": str(review_path),
                    }],
                },
                "timestamp": "2026-07-07T00:02:00Z",
                "event_id": "team-unsafe-final",
            }),
        ]) + "\n",
        encoding="utf-8",
    )

    record = _records_by_adapter(build_run_index(runtime))["team_events"][0]

    _run_record_validator().validate(record)
    assert record["outcome"] == "blocked"
    assert record["acceptance_state"] == "blocked"
    assert record["review_refs"] == []
    assert "final_verdict_ref" not in record
    assert len(record["failure_refs"]) >= 1


def test_run_index_blocks_team_worker_review_when_executor_id_is_omitted(tmp_path):
    runtime = tmp_path / "runtime"
    review_path = runtime / "reviews" / "review.yaml"
    review_path.parent.mkdir(parents=True)
    review_path.write_text("verdict: pass\n", encoding="utf-8")
    final_path = runtime / "final" / "final-verdict.json"
    gate_id = "gate-go-omitted-executor-independent-review"
    _write_json(final_path, {
        "verdict_id": "fv-go-omitted-executor",
        "produced_by": "go-evidence-finalizer",
        "produced_at": "2026-07-07T00:02:00Z",
        "producer_role": "governance",
        "final_state": "final_ready",
        "inputs_reviewed": [str(review_path)],
        "gate_summary": [{
            "gate_id": gate_id,
            "result": "pass",
            "evidence_path": str(review_path),
        }],
        "reviewer_summary": {
            "reviewer_id": "coding-agent-1",
            "verdict": "pass",
            "evidence_path": str(review_path),
        },
        "limitations": [],
        "human_or_governance_reference": "go-evidence-finalize:go-omitted-executor",
    })
    (runtime / "team-events.jsonl").write_text(
        "\n".join([
            json.dumps({
                "event_type": "task_result",
                "run_id": "go-omitted-executor",
                "agent_id": "coding-agent-1",
                "payload": {"status": "passed"},
                "timestamp": "2026-07-07T00:00:00Z",
                "event_id": "team-omitted-executor-result",
            }),
            json.dumps({
                "event_type": "review_ref",
                "run_id": "go-omitted-executor",
                "agent_id": "coding-agent-1",
                "payload": {
                    "review_id": "review-go-omitted-executor",
                    "reviewer_id": "coding-agent-1",
                    "reviewer_role": "reviewer",
                    "verdict": "pass",
                    "ref_path": str(review_path),
                    "reviewed_evidence_refs": ["ev-team-team-omitted-executor-result"],
                },
                "timestamp": "2026-07-07T00:01:00Z",
                "event_id": "team-omitted-executor-review",
            }),
            json.dumps({
                "event_type": "final_verdict_ref",
                "run_id": "go-omitted-executor",
                "agent_id": "go-evidence-finalizer",
                "payload": {
                    "verdict_id": "fv-go-omitted-executor",
                    "produced_by": "go-evidence-finalizer",
                    "producer_role": "governance",
                    "final_state": "final_ready",
                    "ref_path": str(final_path),
                    "review_ref": "review-go-omitted-executor",
                    "gate_refs": [gate_id],
                    "gate_summary": [{
                        "gate_id": gate_id,
                        "result": "pass",
                        "evidence_path": str(review_path),
                    }],
                },
                "timestamp": "2026-07-07T00:02:00Z",
                "event_id": "team-omitted-executor-final",
            }),
        ]) + "\n",
        encoding="utf-8",
    )

    record = _records_by_adapter(build_run_index(runtime))["team_events"][0]

    _run_record_validator().validate(record)
    assert record["outcome"] == "blocked"
    assert record["acceptance_state"] == "blocked"
    assert record["review_refs"] == []
    assert "final_verdict_ref" not in record


def test_run_index_blocks_worker_produced_final_verdict_with_governance_role(tmp_path):
    runtime = tmp_path / "runtime"
    review_path = runtime / "reviews" / "review.yaml"
    review_path.parent.mkdir(parents=True)
    review_path.write_text("verdict: pass\n", encoding="utf-8")
    final_path = runtime / "final" / "final-verdict.json"
    gate_id = "gate-go-spoof-independent-review"
    _write_json(final_path, {
        "verdict_id": "fv-go-spoof",
        "produced_by": "coding-agent-1",
        "produced_at": "2026-07-07T00:02:00Z",
        "producer_role": "governance",
        "final_state": "final_ready",
        "inputs_reviewed": [str(review_path)],
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
        "human_or_governance_reference": "go-evidence-finalize:go-spoof",
    })
    (runtime / "team-events.jsonl").write_text(
        "\n".join([
            json.dumps({
                "event_type": "task_result",
                "run_id": "go-spoof",
                "agent_id": "coding-agent-1",
                "payload": {"status": "passed"},
                "timestamp": "2026-07-07T00:00:00Z",
                "event_id": "team-spoof-result",
            }),
            json.dumps({
                "event_type": "review_ref",
                "run_id": "go-spoof",
                "agent_id": "reviewer-1",
                "payload": {
                    "review_id": "review-go-spoof",
                    "reviewer_id": "reviewer-1",
                    "reviewer_role": "reviewer",
                    "executor_id": "coding-agent-1",
                    "verdict": "pass",
                    "ref_path": str(review_path),
                    "reviewed_evidence_refs": ["ev-team-team-spoof-result"],
                },
                "timestamp": "2026-07-07T00:01:00Z",
                "event_id": "team-spoof-review",
            }),
            json.dumps({
                "event_type": "final_verdict_ref",
                "run_id": "go-spoof",
                "agent_id": "coding-agent-1",
                "payload": {
                    "verdict_id": "fv-go-spoof",
                    "produced_by": "coding-agent-1",
                    "producer_role": "governance",
                    "final_state": "final_ready",
                    "ref_path": str(final_path),
                    "review_ref": "review-go-spoof",
                    "gate_refs": [gate_id],
                    "gate_summary": [{
                        "gate_id": gate_id,
                        "result": "pass",
                        "evidence_path": str(review_path),
                    }],
                },
                "timestamp": "2026-07-07T00:02:00Z",
                "event_id": "team-spoof-final",
            }),
        ]) + "\n",
        encoding="utf-8",
    )

    record = _records_by_adapter(build_run_index(runtime))["team_events"][0]

    _run_record_validator().validate(record)
    assert record["outcome"] == "blocked"
    assert record["acceptance_state"] == "blocked"
    assert "final_verdict_ref" not in record


def test_run_index_blocks_final_verdict_event_gate_mismatch_with_artifact(tmp_path):
    runtime = tmp_path / "runtime"
    review_path = runtime / "reviews" / "review.yaml"
    review_path.parent.mkdir(parents=True)
    review_path.write_text("verdict: pass\n", encoding="utf-8")
    final_path = runtime / "final" / "final-verdict.json"
    gate_id = "gate-go-gate-mismatch-independent-review"
    _write_json(final_path, {
        "verdict_id": "fv-go-gate-mismatch",
        "produced_by": "go-evidence-finalizer",
        "produced_at": "2026-07-07T00:02:00Z",
        "producer_role": "governance",
        "final_state": "final_ready",
        "inputs_reviewed": [str(review_path)],
        "gate_summary": [{
            "gate_id": gate_id,
            "result": "fail",
            "evidence_path": str(review_path),
        }],
        "reviewer_summary": {
            "reviewer_id": "reviewer-1",
            "verdict": "pass",
            "evidence_path": str(review_path),
        },
        "limitations": [],
        "human_or_governance_reference": "go-evidence-finalize:go-gate-mismatch",
    })
    (runtime / "team-events.jsonl").write_text(
        "\n".join([
            json.dumps({
                "event_type": "task_result",
                "run_id": "go-gate-mismatch",
                "agent_id": "coding-agent-1",
                "payload": {"status": "passed"},
                "timestamp": "2026-07-07T00:00:00Z",
                "event_id": "team-gate-mismatch-result",
            }),
            json.dumps({
                "event_type": "review_ref",
                "run_id": "go-gate-mismatch",
                "agent_id": "reviewer-1",
                "payload": {
                    "review_id": "review-go-gate-mismatch",
                    "reviewer_id": "reviewer-1",
                    "reviewer_role": "reviewer",
                    "executor_id": "coding-agent-1",
                    "verdict": "pass",
                    "ref_path": str(review_path),
                    "reviewed_evidence_refs": ["ev-team-team-gate-mismatch-result"],
                },
                "timestamp": "2026-07-07T00:01:00Z",
                "event_id": "team-gate-mismatch-review",
            }),
            json.dumps({
                "event_type": "final_verdict_ref",
                "run_id": "go-gate-mismatch",
                "agent_id": "go-evidence-finalizer",
                "payload": {
                    "verdict_id": "fv-go-gate-mismatch",
                    "produced_by": "go-evidence-finalizer",
                    "producer_role": "governance",
                    "final_state": "final_ready",
                    "ref_path": str(final_path),
                    "review_ref": "review-go-gate-mismatch",
                    "gate_refs": [gate_id],
                    "gate_summary": [{
                        "gate_id": gate_id,
                        "result": "pass",
                        "evidence_path": str(review_path),
                    }],
                },
                "timestamp": "2026-07-07T00:02:00Z",
                "event_id": "team-gate-mismatch-final",
            }),
        ]) + "\n",
        encoding="utf-8",
    )

    record = _records_by_adapter(build_run_index(runtime))["team_events"][0]

    _run_record_validator().validate(record)
    assert record["outcome"] == "blocked"
    assert record["acceptance_state"] == "blocked"
    assert "final_verdict_ref" not in record


def test_run_index_projects_corrupt_legacy_records_as_blocked_failures(tmp_path):
    runtime = tmp_path / "runtime"
    (runtime / "go-runs" / "bad-go").mkdir(parents=True)
    (runtime / "go-runs" / "bad-go" / "go-run.json").write_text("{bad json\n", encoding="utf-8")
    runtime.mkdir(exist_ok=True)
    (runtime / "team-events.jsonl").write_text(
        json.dumps({
            "event_type": "task_created",
            "run_id": "go-good",
            "agent_id": "coding-agent-1",
            "payload": {},
            "timestamp": "2026-07-07T00:00:00Z",
            "event_id": "team-good",
        }) + "\n" + "{bad jsonl\n",
        encoding="utf-8",
    )
    atgo_dir = runtime / "atgo-runs" / "bad-review"
    atgo_dir.mkdir(parents=True)
    (atgo_dir / "review.yaml").write_text("verdict: [unterminated\n", encoding="utf-8")

    index = build_run_index(runtime)

    validator = _run_record_validator()
    failure_records = [
        entry["record"] for entry in index["runs"]
        if entry["source_type"] == "failure_record"
    ]
    assert len(failure_records) == 3
    for record in failure_records:
        validator.validate(record)
        assert record["outcome"] == "blocked"
        assert record["projection_state"] == "blocked"
        assert record["failure_refs"][0]["status"] == "blocked"
        assert "diagnostic" in record["domain_refs"]


def test_run_index_projects_atgo_prepare_chain_evidence_as_review_pending(tmp_path):
    runtime = tmp_path / "runtime"
    evidence_dir = runtime / "atgo-runs" / "go-prepare"
    evidence_dir.mkdir(parents=True)
    _write_json(evidence_dir / "chain-evidence.json", {
        "run_id": "go-prepare",
        "project_id": "demo-project",
        "executor_id": "opencode",
        "mode": "prepare",
        "task": str(evidence_dir / "task-spec.md"),
        "next_commands": {
            "finalize": {
                "command": f"tools/go_evidence.py finalize {evidence_dir} --team-runtime-dir {runtime}",
                "command_args": [
                    "tools/go_evidence.py",
                    "finalize",
                    str(evidence_dir),
                    "--team-runtime-dir",
                    str(runtime),
                ],
                "authority": "guidance_only",
                "creates_acceptance": False,
                "requires_independent_review": True,
                "manual": True,
            },
        },
        "timestamps": {"created_at": "2026-07-07T00:00:00+00:00"},
    })

    index = build_run_index(runtime)

    assert len(index["runs"]) == 1
    entry = index["runs"][0]
    record = entry["record"]
    _run_record_validator().validate(record)
    assert entry["source_type"] == "atgo_prepare"
    assert record["phase"] == "prepared"
    assert record["outcome"] == "unknown"
    assert record["review_state"] == "not_reviewed"
    assert record["gate_state"] == "not_evaluated"
    assert record["acceptance_state"] == "deferred"
    assert "final_verdict_ref" not in record
    assert record["review_refs"] == []
    assert record["gate_refs"] == []
    assert record["failure_refs"] == []
    assert record["domain_refs"]["finalizer_authority"] == "guidance_only"
    assert record["domain_refs"]["finalizer_creates_acceptance"] is False
    assert record["domain_refs"]["finalizer_requires_independent_review"] is True
    assert record["domain_refs"]["finalizer_manual"] is True
    assert record["domain_refs"]["finalizer_command_args"][-2:] == [
        "--team-runtime-dir",
        str(runtime),
    ]


def test_run_index_blocks_atgo_executor_self_review(tmp_path):
    runtime = tmp_path / "runtime"
    review_dir = runtime / "atgo-runs" / "self-review"
    review_dir.mkdir(parents=True)
    (review_dir / "review.yaml").write_text(
        "\n".join([
            "project_id: demo-project",
            "verdict: pass",
            "reviewer_role: executor",
            "reviewer_id: coding-agent-1",
            "executor_id: coding-agent-1",
        ]),
        encoding="utf-8",
    )

    index = build_run_index(runtime)

    assert len(index["runs"]) == 1
    record = index["runs"][0]["record"]
    _run_record_validator().validate(record)
    assert record["outcome"] == "blocked"
    assert record["review_state"] == "review_blocked"
    assert record["acceptance_state"] == "blocked"
    assert record["review_refs"] == []
    assert record["failure_refs"][0]["status"] == "blocked"
    assert "reviewer role is not independent" in record["domain_refs"]["diagnostic"]


def test_run_index_keeps_non_ascii_legacy_ids_schema_safe(tmp_path):
    runtime = tmp_path / "runtime"
    go_dir = runtime / "go-runs" / "运行-一"
    go_dir.mkdir(parents=True)
    _write_json(go_dir / "go-run.json", {
        "go_run_id": "运行-一",
        "project_id": "项目",
        "status": "queued",
        "created_at": "2026-07-07T00:00:00Z",
        "agents": [],
    })

    index = build_run_index(runtime)

    assert len(index["runs"]) == 1
    record = index["runs"][0]["record"]
    _run_record_validator().validate(record)
    assert record["run_id"] == "run-unknown"


def test_run_index_blocks_atgo_pass_without_independent_reviewer_identity(tmp_path):
    runtime = tmp_path / "runtime"
    review_dir = runtime / "atgo-runs" / "anonymous-review"
    review_dir.mkdir(parents=True)
    (review_dir / "review.yaml").write_text("project_id: demo-project\nverdict: pass\n", encoding="utf-8")

    index = build_run_index(runtime)

    record = index["runs"][0]["record"]
    _run_record_validator().validate(record)
    assert record["outcome"] == "blocked"
    assert record["review_refs"] == []
    assert "reviewer_role is missing" in record["domain_refs"]["diagnostic"]


def test_run_index_blocks_incomplete_paper_workspace_without_state(tmp_path):
    runtime = tmp_path / "runtime"
    paper_root = tmp_path / "paper"
    paper_root.mkdir()
    (paper_root / "PAPER_PROFILE.yaml").write_text("paper_id: demo-paper\n", encoding="utf-8")

    index = build_run_index(runtime, paper_project_dirs=[paper_root])

    record = index["runs"][0]["record"]
    _run_record_validator().validate(record)
    assert record["outcome"] == "blocked"
    assert record["projection_state"] == "blocked"
    assert "missing YAML file" in record["domain_refs"]["diagnostic"]


def test_run_index_projects_paper_workflow_state_without_final_authority(tmp_path):
    runtime = tmp_path / "runtime"
    paper_root = tmp_path / "paper"
    paper_root.mkdir()
    (paper_root / "PAPER_PROFILE.yaml").write_text("paper_id: demo-paper\ncurrent_stage: closure\n", encoding="utf-8")
    (paper_root / "PAPER_STATE.yaml").write_text(
        "\n".join([
            "paper_id: demo-paper",
            "workflow_type: paper_review",
            "current_stage: closure",
            "acceptance_status: accepted",
            "manifest_status: complete",
            "evidence_pack_ref: evidence/ref-paper-review-pack.zip",
            "final_acceptance: true",
            "blocking_count: 0",
            "non_blocking_count: 2",
            "human_required: false",
            "human_gate_triggered: false",
            "privacy_attestation:",
            "  contains_real_paper_full_text: false",
            "ledger_issue_count: 2",
            "executed_nodes:",
            "  - diagnosis",
            "  - finalizer",
            "chain_trusted: true",
        ]) + "\n",
        encoding="utf-8",
    )
    (paper_root / "paper_task").mkdir()
    (paper_root / "paper_task" / "PAPER_TASK_INPUT.yaml").write_text("task_type: cssci_review\n", encoding="utf-8")
    (paper_root / "paper_task" / "PRIVACY_ATTESTATION.yaml").write_text("contains_real_paper_full_text: false\n", encoding="utf-8")
    (paper_root / "review").mkdir()
    (paper_root / "review" / "REVIEW_REPORT.md").write_text("# Review\n", encoding="utf-8")
    (paper_root / "closure").mkdir()
    (paper_root / "closure" / "CLOSURE_REPORT.md").write_text("# Closure\n", encoding="utf-8")
    _write_json(paper_root / "closure" / "FLOW_OUTCOME.json", {"final_state": "accepted"})
    (paper_root / "evidence").mkdir()
    (paper_root / "evidence" / "ref-paper-review-pack.zip").write_bytes(b"fixture")

    index = build_run_index(runtime, paper_project_dirs=[paper_root])

    record = _records_by_adapter(index)["paper"][0]
    _run_record_validator().validate(record)
    assert record["outcome"] == "passed"
    assert record["acceptance_state"] == "review_pending"
    assert "final_verdict_ref" not in record
    assert record["domain_refs"]["workflow_type"] == "paper_review"
    assert record["domain_refs"]["manifest_status"] == "complete"
    assert record["domain_refs"]["final_acceptance"] is True
    assert record["domain_refs"]["canonical_final_verdict_required"] is True
    assert {ref["kind"] for ref in record["evidence_refs"]} >= {
        "context_packet",
        "gate_result",
        "review",
        "command_output",
        "other",
    }
    assert record["gate_refs"] == [{
        "gate_id": "gate-paper-privacy-demo-paper",
        "result": "pass",
        "uri": str(paper_root / "paper_task" / "PRIVACY_ATTESTATION.yaml"),
        "evidence_refs": ["ev-paper-privacy-demo-paper"],
    }]
    assert any("FinalVerdict" in item for item in record["limitations"])


def test_run_index_projects_paper_final_verdict_to_final_ready(tmp_path):
    runtime = tmp_path / "runtime"
    paper_root = tmp_path / "paper"
    paper_root.mkdir()
    (paper_root / "PAPER_PROFILE.yaml").write_text("paper_id: demo-paper\ncurrent_stage: closure\n", encoding="utf-8")
    (paper_root / "PAPER_STATE.yaml").write_text(
        "\n".join([
            "paper_id: demo-paper",
            "workflow_type: paper_review",
            "current_stage: closure",
            "acceptance_status: accepted",
            "manifest_status: complete",
            "evidence_pack_ref: evidence/ref-paper-review-pack.zip",
            "final_acceptance: true",
            "blocking_count: 0",
            "human_required: false",
            "human_gate_triggered: false",
            "chain_trusted: true",
        ]) + "\n",
        encoding="utf-8",
    )
    (paper_root / "paper_task").mkdir()
    (paper_root / "paper_task" / "PAPER_TASK_INPUT.yaml").write_text("task_type: cssci_review\n", encoding="utf-8")
    privacy_path = paper_root / "paper_task" / "PRIVACY_ATTESTATION.yaml"
    privacy_path.write_text("contains_real_paper_full_text: false\n", encoding="utf-8")
    (paper_root / "review").mkdir()
    review_path = paper_root / "review" / "REVIEW_REPORT.md"
    review_path.write_text("# Review\n", encoding="utf-8")
    (paper_root / "closure").mkdir()
    _write_json(paper_root / "closure" / "FINAL_VERDICT.json", {
        "verdict_id": "fv-paper-demo-final",
        "produced_by": "paper-governance-finalizer",
        "produced_at": "2026-07-09T00:00:00Z",
        "producer_role": "governance",
        "final_state": "final_ready",
        "inputs_reviewed": [str(review_path), str(privacy_path)],
        "gate_summary": [{
            "gate_id": "gate-paper-demo-privacy-final",
            "result": "pass",
            "evidence_path": str(privacy_path),
        }],
        "reviewer_summary": {
            "reviewer_id": "paper-reviewer-1",
            "verdict": "pass",
            "evidence_path": str(review_path),
        },
        "limitations": [],
        "human_or_governance_reference": "paper-final-verdict-fixture",
    })

    index = build_run_index(runtime, paper_project_dirs=[paper_root])

    record = _records_by_adapter(index)["paper"][0]
    _run_record_validator().validate(record)
    assert record["phase"] == "closed"
    assert record["outcome"] == "passed"
    assert record["review_state"] == "review_passed"
    assert record["gate_state"] == "gate_passed"
    assert record["acceptance_state"] == "final_ready"
    assert record["projection_state"] == "completed"
    assert record["final_verdict_ref"]["verdict_id"] == "fv-paper-demo-final"
    assert record["final_verdict_ref"]["review_ref"] == "review-paper-final-demo-paper"
    assert record["review_refs"][0]["reviewer_id"] == "paper-reviewer-1"
    assert record["review_refs"][0]["reviewed_evidence_refs"] == ["ev-paper-review-demo-paper"]
    assert record["gate_refs"][-1]["evidence_refs"] == ["ev-paper-privacy-demo-paper"]
    assert "paper final_acceptance requires a canonical FinalVerdict before final_ready projection" not in record["limitations"]


def test_run_index_blocks_invalid_paper_final_verdict(tmp_path):
    runtime = tmp_path / "runtime"
    paper_root = tmp_path / "paper"
    paper_root.mkdir()
    (paper_root / "PAPER_PROFILE.yaml").write_text("paper_id: demo-paper\ncurrent_stage: closure\n", encoding="utf-8")
    (paper_root / "PAPER_STATE.yaml").write_text(
        "paper_id: demo-paper\nacceptance_status: accepted\nfinal_acceptance: true\n",
        encoding="utf-8",
    )
    (paper_root / "paper_task").mkdir()
    privacy_path = paper_root / "paper_task" / "PRIVACY_ATTESTATION.yaml"
    privacy_path.write_text("contains_real_paper_full_text: false\n", encoding="utf-8")
    (paper_root / "review").mkdir()
    review_path = paper_root / "review" / "REVIEW_REPORT.md"
    review_path.write_text("# Review\n", encoding="utf-8")
    (paper_root / "closure").mkdir()
    _write_json(paper_root / "closure" / "FINAL_VERDICT.json", {
        "verdict_id": "fv-paper-demo-invalid",
        "produced_by": "paper-governance-finalizer",
        "produced_at": "2026-07-09T00:00:00Z",
        "producer_role": "governance",
        "final_state": "final_ready",
        "inputs_reviewed": [str(review_path), str(privacy_path)],
        "gate_summary": [{
            "gate_id": "gate-paper-demo-privacy-final",
            "result": "pass",
            "evidence_path": str(privacy_path),
        }],
        "reviewer_summary": {
            "reviewer_id": "paper-reviewer-1",
            "verdict": "fail",
            "evidence_path": str(review_path),
        },
        "limitations": [],
        "human_or_governance_reference": "paper-final-verdict-fixture",
    })

    index = build_run_index(runtime, paper_project_dirs=[paper_root])

    record = _records_by_adapter(index)["paper"][0]
    _run_record_validator().validate(record)
    assert record["outcome"] == "blocked"
    assert record["acceptance_state"] == "blocked"
    assert "final_verdict_ref" not in record
    assert record["failure_refs"][0]["failure_id"] == "failure-paper-final-verdict-demo-paper"


def test_run_index_blocks_paper_final_verdict_with_external_gate_evidence(tmp_path):
    runtime = tmp_path / "runtime"
    paper_root = tmp_path / "paper"
    paper_root.mkdir()
    (paper_root / "PAPER_PROFILE.yaml").write_text("paper_id: demo-paper\ncurrent_stage: closure\n", encoding="utf-8")
    (paper_root / "PAPER_STATE.yaml").write_text(
        "paper_id: demo-paper\nacceptance_status: accepted\nfinal_acceptance: true\n",
        encoding="utf-8",
    )
    (paper_root / "paper_task").mkdir()
    (paper_root / "paper_task" / "PRIVACY_ATTESTATION.yaml").write_text(
        "contains_real_paper_full_text: false\n",
        encoding="utf-8",
    )
    (paper_root / "review").mkdir()
    review_path = paper_root / "review" / "REVIEW_REPORT.md"
    review_path.write_text("# Review\n", encoding="utf-8")
    external_dir = tmp_path / "outside"
    external_dir.mkdir()
    external_privacy_path = external_dir / "PRIVACY_ATTESTATION.yaml"
    external_privacy_path.write_text("contains_real_paper_full_text: unknown\n", encoding="utf-8")
    (paper_root / "closure").mkdir()
    _write_json(paper_root / "closure" / "FINAL_VERDICT.json", {
        "verdict_id": "fv-paper-demo-external-evidence",
        "produced_by": "paper-governance-finalizer",
        "produced_at": "2026-07-09T00:00:00Z",
        "producer_role": "governance",
        "final_state": "final_ready",
        "inputs_reviewed": [str(review_path), str(external_privacy_path)],
        "gate_summary": [{
            "gate_id": "gate-paper-demo-privacy-final",
            "result": "pass",
            "evidence_path": str(external_privacy_path),
        }],
        "reviewer_summary": {
            "reviewer_id": "paper-reviewer-1",
            "verdict": "pass",
            "evidence_path": str(review_path),
        },
        "limitations": [],
        "human_or_governance_reference": "paper-final-verdict-fixture",
    })

    index = build_run_index(runtime, paper_project_dirs=[paper_root])

    record = _records_by_adapter(index)["paper"][0]
    _run_record_validator().validate(record)
    assert record["outcome"] == "blocked"
    assert record["acceptance_state"] == "blocked"
    assert "final_verdict_ref" not in record
    assert record["failure_refs"][0]["failure_id"] == "failure-paper-final-verdict-demo-paper"


def test_run_index_blocks_paper_human_gate_from_workflow_state(tmp_path):
    runtime = tmp_path / "runtime"
    paper_root = tmp_path / "paper"
    paper_root.mkdir()
    (paper_root / "PAPER_PROFILE.yaml").write_text("paper_id: demo-paper\ncurrent_stage: closure\n", encoding="utf-8")
    (paper_root / "PAPER_STATE.yaml").write_text(
        "\n".join([
            "paper_id: demo-paper",
            "acceptance_status: accepted",
            "human_required: true",
            "human_gate_triggered: true",
            "human_gate_decision: pending",
            "chain_trusted: true",
        ]) + "\n",
        encoding="utf-8",
    )

    index = build_run_index(runtime, paper_project_dirs=[paper_root])

    record = _records_by_adapter(index)["paper"][0]
    _run_record_validator().validate(record)
    assert record["outcome"] == "human_required"
    assert record["gate_state"] == "gate_blocked"
    assert record["acceptance_state"] == "blocked"
    assert record["projection_state"] == "waiting_for_you"
    assert record["domain_refs"]["effective_status"] == "human_required"
    assert record["gate_refs"] == [{
        "gate_id": "gate-paper-human-demo-paper",
        "result": "blocked",
        "uri": str(paper_root / "PAPER_STATE.yaml"),
        "evidence_refs": [],
    }]
    assert record["failure_refs"][0]["failure_id"] == "failure-paper-human-gate-demo-paper"
    assert any("human gate" in item for item in record["limitations"])


def test_run_index_blocks_passed_test_run_when_report_is_missing(tmp_path):
    runtime = tmp_path / "runtime"
    _write_json(runtime / "test-runs" / "missing-report" / "test-run.json", {
        "test_run_id": "missing-report",
        "project_id": "demo-project",
        "status": "passed",
        "created_at": "2026-07-07T00:00:00Z",
        "report_path": str(runtime / "test-runs" / "missing-report" / "report.md"),
    })

    index = build_run_index(runtime)

    record = index["runs"][0]["record"]
    _run_record_validator().validate(record)
    assert record["outcome"] == "blocked"
    assert record["evidence_refs"] == []
    assert record["failure_refs"][0]["status"] == "blocked"
    assert "test report is missing" in record["domain_refs"]["diagnostic"]


def test_run_index_blocks_passed_test_run_when_report_path_is_missing(tmp_path):
    runtime = tmp_path / "runtime"
    _write_json(runtime / "test-runs" / "missing-report-path" / "test-run.json", {
        "test_run_id": "missing-report-path",
        "project_id": "demo-project",
        "status": "passed",
        "created_at": "2026-07-07T00:00:00Z",
    })

    index = build_run_index(runtime)

    record = index["runs"][0]["record"]
    _run_record_validator().validate(record)
    assert record["outcome"] == "blocked"
    assert record["evidence_refs"] == []
    assert record["failure_refs"][0]["uri"].endswith("test-run.json")
    assert "test report is missing" in record["domain_refs"]["diagnostic"]
