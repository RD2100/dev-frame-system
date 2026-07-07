from __future__ import annotations

import json
from pathlib import Path

from jsonschema.validators import validator_for

from control_plane.run_index import ADAPTER_VERSION, build_run_index

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


def _records_by_adapter(index: dict) -> dict[str, list[dict]]:
    grouped: dict[str, list[dict]] = {}
    for entry in index["runs"]:
        grouped.setdefault(entry["adapter_id"], []).append(entry["record"])
    return grouped


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
    (runtime / "team-events.jsonl").write_text(
        "\n".join([
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
    final_evidence_refs = [ref for ref in record["evidence_refs"] if ref["kind"] == "final_verdict"]
    assert final_evidence_refs == [{
        "evidence_id": "ev-team-final-verdict-team-final-verdict",
        "kind": "final_verdict",
        "uri": str(final_path),
        "supports": "acceptance",
    }]


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
