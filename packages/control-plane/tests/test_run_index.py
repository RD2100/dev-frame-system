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
                "payload": {"project_id": "demo-project", "targets": ["src/app.py"]},
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
    assert team_record["evidence_refs"] == [{
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
