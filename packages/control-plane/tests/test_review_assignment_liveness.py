"""Real-path review assignment liveness tests."""
from __future__ import annotations

import json
import multiprocessing
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier

import pytest

from control_plane.run_index import build_run_index
from control_plane.team_runtime import TEAM_EVENTS_FILE, TeamRuntime, build_team_runtime_view
from control_plane.workflow_engine import VERDICT_AWAITING_REVIEW, WorkflowEngine


def _pass_command() -> list[str]:
    script = (
        "import os;"
        "open(os.environ['RDGOAL_REPORT_PATH'],'w',encoding='utf-8')"
        ".write('## ExecutionReport\\n\\n- **Status**: pass\\n- **Changed Files**:\\n"
        "- (none)\\n- **Evidence**: review assignment liveness test\\n')"
    )
    return [sys.executable, "-c", script]


def _run_workflow(tmp_path: Path):
    project = tmp_path / "project"
    project.mkdir()
    (project / "a.py").write_text("value = 1\n", encoding="utf-8")
    runtime = tmp_path / "runtime"
    result = WorkflowEngine(runtime_dir=runtime).run_coding_workflow(
        project,
        "review assignment liveness",
        agents=1,
        targets=["a.py"],
        worker_command=_pass_command(),
    )
    team = TeamRuntime(runtime_dir=runtime)
    executor_id = next(
        event["agent_id"]
        for event in team.read_all()
        if event.get("event_type") == "task_result"
    )
    assert result.verdict == VERDICT_AWAITING_REVIEW
    return runtime, result.go_run_id, executor_id, team


def _review_task(view: dict, reviewer_id: str) -> dict:
    return next(task for task in view["task_board"] if task["agent_ids"] == [reviewer_id])


def _reviewer(view: dict, reviewer_id: str) -> dict:
    return next(agent for agent in view["agent_registry"] if agent["agent_id"] == reviewer_id)


def _team_record(runtime: Path) -> dict:
    return next(
        entry["record"]
        for entry in build_run_index(runtime)["runs"]
        if entry["adapter_id"] == "team_events"
    )


def _append_team_event(runtime: Path, event: dict) -> None:
    with (runtime / TEAM_EVENTS_FILE).open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event) + "\n")


def _write_final_verdict_artifact(
    path: Path,
    *,
    run_id: str,
    reviewer_id: str,
    review_path: Path,
    gate_id: str,
) -> dict:
    artifact = {
        "verdict_id": f"fv-{run_id}",
        "produced_by": "go-evidence-finalizer",
        "produced_at": "2026-07-23T00:00:00+00:00",
        "producer_role": "governance",
        "final_state": "final_ready",
        "inputs_reviewed": [str(review_path)],
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
        "human_or_governance_reference": f"go-evidence-finalize:{run_id}",
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(artifact, indent=2) + "\n", encoding="utf-8")
    return artifact


def _record_pass_review_and_final(
    tmp_path,
    team: TeamRuntime,
    *,
    run_id: str,
    executor_id: str,
    reviewer_id: str,
    review_id: str,
    file_stem: str,
    verdict_id: str | None = None,
) -> dict:
    review_path = tmp_path / f"{file_stem}-review.yaml"
    review_path.write_text("verdict: pass\n", encoding="utf-8")
    team.record_review_ref(
        run_id,
        reviewer_id,
        review_id=review_id,
        reviewer_role="reviewer",
        executor_id=executor_id,
        verdict="pass",
        ref_path=str(review_path),
        reviewed_evidence_refs=[str(review_path)],
    )
    gate_id = f"gate-{run_id}-{file_stem}-independent-review"
    final_path = tmp_path / f"{file_stem}-final-verdict.json"
    artifact = _write_final_verdict_artifact(
        final_path,
        run_id=run_id,
        reviewer_id=reviewer_id,
        review_path=review_path,
        gate_id=gate_id,
    )
    if verdict_id:
        artifact["verdict_id"] = verdict_id
        final_path.write_text(
            json.dumps(artifact, indent=2) + "\n", encoding="utf-8"
        )
    team.record_final_verdict_ref(
        run_id,
        artifact["produced_by"],
        verdict_id=artifact["verdict_id"],
        producer_role=artifact["producer_role"],
        final_state=artifact["final_state"],
        ref_path=str(final_path),
        review_ref=review_id,
        gate_refs=[gate_id],
        gate_summary=artifact["gate_summary"],
        limitations=artifact["limitations"],
        human_or_governance_reference=artifact[
            "human_or_governance_reference"
        ],
    )
    return artifact


def _assign_review_in_process(
    runtime: str,
    reviewer_id: str,
    barrier,
    results,
    run_id: str = "run-cross-process",
    target: str = "a.py",
) -> None:
    team = TeamRuntime(runtime_dir=runtime)
    barrier.wait(timeout=10)
    try:
        team.record_task_created(
            run_id,
            reviewer_id,
            task_kind="independent_review",
            agent_role="reviewer",
            targets=[target],
        )
    except ValueError:
        results.put("rejected")
    else:
        results.put("created")


def _create_role_in_process(
    runtime: str,
    task_kind: str,
    barrier,
    results,
) -> None:
    team = TeamRuntime(runtime_dir=runtime)
    barrier.wait(timeout=10)
    try:
        team.record_task_created(
            "run-review-execution-race",
            "agent-shared",
            task_kind=task_kind,
            agent_role=("reviewer" if task_kind == "independent_review" else "worker"),
            targets=["a.py"],
        )
    except ValueError:
        results.put((task_kind, "rejected"))
    else:
        results.put((task_kind, "created"))


def test_inventory_progress_keeps_same_reviewer_active_until_final_verdict(tmp_path):
    runtime, run_id, executor_id, team = _run_workflow(tmp_path)
    reviewer_id = "reviewer-1"
    team.record_task_created(
        run_id,
        reviewer_id,
        task_kind="independent_review",
        agent_role="reviewer",
        targets=["a.py"],
    )
    team.record_task_claimed(run_id, reviewer_id)
    inventory_path = tmp_path / "review-inventory.md"
    inventory_path.write_text("# Inventory only\nNo verdict.\n", encoding="utf-8")

    team.record_result(
        run_id,
        reviewer_id,
        status="completed",
        report_path=str(inventory_path),
    )

    pending_view = build_team_runtime_view(runtime)
    assert _review_task(pending_view, reviewer_id)["status"] == "claimed"
    assert _reviewer(pending_view, reviewer_id) == {
        "agent_id": reviewer_id,
        "role": "reviewer",
        "binding_id": "",
        "status": "working",
        "session_ids": [],
    }
    pending_record = _team_record(runtime)
    assert reviewer_id not in {
        worker["worker_id"] for worker in pending_record.get("worker_results", [])
    }
    assert pending_record.get("review_refs", []) == []

    review_path = tmp_path / "review.yaml"
    review_path.write_text("verdict: pass\n", encoding="utf-8")
    team.record_review_ref(
        run_id,
        reviewer_id,
        review_id="review-liveness-1",
        reviewer_role="reviewer",
        executor_id=executor_id,
        verdict="pass",
        ref_path=str(review_path),
        reviewed_evidence_refs=[str(inventory_path)],
        reviewed_inputs=[
            "diff.patch",
            "test-output.md",
            "safety-report.json",
            "chain-evidence.json",
        ],
        source="go_evidence_finalize",
    )

    reviewed_view = build_team_runtime_view(runtime)
    assert _review_task(reviewed_view, reviewer_id)["status"] == "claimed"
    assert _reviewer(reviewed_view, reviewer_id)["status"] == "working"
    reviewed_record = _team_record(runtime)
    assert reviewed_record["review_refs"][0]["reviewer_id"] == reviewer_id
    assert reviewed_record["review_refs"][0]["verdict"] == "pass"
    with pytest.raises(ValueError, match="active review assignment"):
        team.record_task_created(
            run_id,
            "reviewer-2",
            task_kind="independent_review",
            agent_role="reviewer",
            targets=["a.py"],
        )


def test_second_active_reviewer_for_same_target_is_rejected_atomically(tmp_path):
    runtime, run_id, _executor_id, team = _run_workflow(tmp_path)
    team.record_task_created(
        run_id,
        "reviewer-1",
        task_kind="independent_review",
        agent_role="reviewer",
        targets=["a.py"],
    )
    team.record_task_claimed(run_id, "reviewer-1")
    journal = runtime / "team-events.jsonl"
    line_count = len(journal.read_bytes().splitlines())

    with pytest.raises(ValueError, match="active review assignment"):
        team.record_task_created(
            run_id,
            "reviewer-2",
            task_kind="independent_review",
            agent_role="reviewer",
            targets=["a.py"],
        )

    assert len(journal.read_bytes().splitlines()) == line_count
    reviewer_tasks = [
        task
        for task in build_team_runtime_view(runtime)["task_board"]
        if task["agent_ids"] in (["reviewer-1"], ["reviewer-2"])
    ]
    assert [task["agent_ids"] for task in reviewer_tasks] == [["reviewer-1"]]


def test_second_active_reviewer_for_disjoint_target_is_rejected_atomically(tmp_path):
    runtime, run_id, _executor_id, team = _run_workflow(tmp_path)
    team.record_task_created(
        run_id,
        "reviewer-1",
        task_kind="independent_review",
        agent_role="reviewer",
        targets=["a.py"],
    )
    team.record_task_claimed(run_id, "reviewer-1")
    journal = runtime / TEAM_EVENTS_FILE
    journal_before = journal.read_bytes()

    with pytest.raises(ValueError, match="active review assignment"):
        team.record_task_created(
            run_id,
            "reviewer-2",
            task_kind="independent_review",
            agent_role="reviewer",
            targets=["disjoint.py"],
        )

    assert journal.read_bytes() == journal_before


def test_concurrent_review_assignment_claim_has_one_owner(tmp_path):
    runtime, run_id, _executor_id, team = _run_workflow(tmp_path)

    def assign(reviewer_id: str) -> str:
        try:
            team.record_task_created(
                run_id,
                reviewer_id,
                task_kind="independent_review",
                agent_role="reviewer",
                targets=["a.py"],
            )
        except ValueError:
            return "rejected"
        return "created"

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(assign, ["reviewer-1", "reviewer-2"]))

    assert sorted(outcomes) == ["created", "rejected"]
    reviewer_tasks = [
        task
        for task in build_team_runtime_view(runtime)["task_board"]
        if task["agent_ids"] in (["reviewer-1"], ["reviewer-2"])
    ]
    assert len(reviewer_tasks) == 1


def test_review_assignment_is_atomic_across_independent_runtime_instances(tmp_path):
    runtime = tmp_path / "runtime"
    barrier = Barrier(2)

    def assign(reviewer_id: str) -> str:
        team = TeamRuntime(runtime_dir=runtime)
        barrier.wait(timeout=10)
        try:
            team.record_task_created(
                "run-two-instances",
                reviewer_id,
                task_kind="independent_review",
                agent_role="reviewer",
                targets=["a.py"],
            )
        except ValueError:
            return "rejected"
        return "created"

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(assign, ["reviewer-1", "reviewer-2"]))

    assert sorted(outcomes) == ["created", "rejected"]
    review_tasks = [
        event
        for event in TeamRuntime(runtime_dir=runtime).read_all()
        if event["event_type"] == "task_created"
    ]
    assert len(review_tasks) == 1


def test_review_assignment_is_atomic_across_processes(tmp_path):
    runtime = tmp_path / "runtime"
    context = multiprocessing.get_context("spawn")
    barrier = context.Barrier(2)
    results = context.Queue()
    processes = [
        context.Process(
            target=_assign_review_in_process,
            args=(str(runtime), reviewer_id, barrier, results),
        )
        for reviewer_id in ("reviewer-1", "reviewer-2")
    ]

    for process in processes:
        process.start()
    for process in processes:
        process.join(timeout=15)

    assert [process.exitcode for process in processes] == [0, 0]
    assert sorted(results.get(timeout=2) for _ in processes) == ["created", "rejected"]
    review_tasks = [
        event
        for event in TeamRuntime(runtime_dir=runtime).read_all()
        if event["event_type"] == "task_created"
    ]
    assert len(review_tasks) == 1


def test_disjoint_review_targets_still_have_one_owner_across_processes(tmp_path):
    runtime = tmp_path / "runtime"
    context = multiprocessing.get_context("spawn")
    barrier = context.Barrier(2)
    results = context.Queue()
    assignments = (("reviewer-1", "a.py"), ("reviewer-2", "disjoint.py"))
    processes = [
        context.Process(
            target=_assign_review_in_process,
            args=(
                str(runtime),
                reviewer_id,
                barrier,
                results,
                "run-cross-process-disjoint",
                target,
            ),
        )
        for reviewer_id, target in assignments
    ]

    for process in processes:
        process.start()
    for process in processes:
        process.join(timeout=15)

    assert [process.exitcode for process in processes] == [0, 0]
    assert sorted(results.get(timeout=2) for _ in processes) == [
        "created",
        "rejected",
    ]
    review_tasks = [
        event
        for event in TeamRuntime(runtime_dir=runtime).read_all()
        if event["event_type"] == "task_created"
    ]
    assert len(review_tasks) == 1
    assert review_tasks[0]["payload"]["targets"] in [["a.py"], ["disjoint.py"]]


def test_execution_task_cannot_replace_an_active_reviewer(tmp_path):
    runtime = tmp_path / "runtime"
    team = TeamRuntime(runtime_dir=runtime)
    team.record_task_created(
        "run-review-first",
        "agent-shared",
        task_kind="independent_review",
        agent_role="reviewer",
        targets=["a.py"],
    )
    journal = runtime / TEAM_EVENTS_FILE
    journal_before = journal.read_bytes()

    with pytest.raises(ValueError, match="active reviewer"):
        team.record_task_created(
            "run-review-first",
            "agent-shared",
            task_kind="execution",
            agent_role="worker",
            targets=["a.py"],
        )

    assert journal.read_bytes() == journal_before
    tasks = [
        event
        for event in team.read_all()
        if event["event_type"] == "task_created"
    ]
    assert len(tasks) == 1
    assert tasks[0]["payload"]["task_kind"] == "independent_review"


def test_review_and_execution_creation_race_has_one_role_owner(tmp_path):
    runtime = tmp_path / "runtime"
    context = multiprocessing.get_context("spawn")
    barrier = context.Barrier(2)
    results = context.Queue()
    task_kinds = ("execution", "independent_review")
    processes = [
        context.Process(
            target=_create_role_in_process,
            args=(str(runtime), task_kind, barrier, results),
        )
        for task_kind in task_kinds
    ]

    for process in processes:
        process.start()
    for process in processes:
        process.join(timeout=15)

    assert [process.exitcode for process in processes] == [0, 0]
    outcomes = [results.get(timeout=2) for _ in processes]
    assert sorted(status for _task_kind, status in outcomes) == ["created", "rejected"]
    created_kind = next(
        task_kind for task_kind, status in outcomes if status == "created"
    )
    tasks = [
        event
        for event in TeamRuntime(runtime_dir=runtime).read_all()
        if event["event_type"] == "task_created"
    ]
    assert len(tasks) == 1
    assert tasks[0]["agent_id"] == "agent-shared"
    assert tasks[0]["payload"]["task_kind"] == created_kind


def test_concurrent_process_appends_preserve_nonconflicting_assignments(tmp_path):
    runtime = tmp_path / "runtime"
    context = multiprocessing.get_context("spawn")
    barrier = context.Barrier(2)
    results = context.Queue()
    assignments = [
        ("reviewer-1", "run-process-1", "a.py"),
        ("reviewer-2", "run-process-2", "b.py"),
    ]
    processes = [
        context.Process(
            target=_assign_review_in_process,
            args=(
                str(runtime),
                reviewer_id,
                barrier,
                results,
                run_id,
                target,
            ),
        )
        for reviewer_id, run_id, target in assignments
    ]

    for process in processes:
        process.start()
    for process in processes:
        process.join(timeout=15)

    assert [process.exitcode for process in processes] == [0, 0]
    assert [results.get(timeout=2) for _ in processes] == ["created", "created"]
    events = TeamRuntime(runtime_dir=runtime).read_all()
    assert {event["run_id"] for event in events} == {"run-process-1", "run-process-2"}
    assert len(events) == 2


def test_task_created_rejects_unknown_task_kind_without_journal_mutation(tmp_path):
    runtime = tmp_path / "runtime"
    team = TeamRuntime(runtime_dir=runtime)

    with pytest.raises(ValueError, match="task_kind"):
        team.record_task_created(
            "go-unknown-kind",
            "agent-1",
            task_kind="mystery",
        )

    assert not (runtime / TEAM_EVENTS_FILE).exists()


@pytest.mark.parametrize("reviewer_role", ["controller", "coordinator", "root"])
def test_bound_review_assignment_rejects_governance_author_role(
    tmp_path, reviewer_role
):
    runtime, run_id, executor_id, team = _run_workflow(tmp_path)
    reviewer_id = "reviewer-1"
    team.record_task_created(
        run_id,
        reviewer_id,
        task_kind="independent_review",
        agent_role="reviewer",
        targets=["a.py"],
    )
    team.record_task_claimed(run_id, reviewer_id)
    review_path = tmp_path / "review.yaml"
    review_path.write_text("verdict: pass\n", encoding="utf-8")
    journal = runtime / "team-events.jsonl"
    journal_before = journal.read_bytes()

    with pytest.raises(ValueError, match="not independent"):
        team.record_review_ref(
            run_id,
            reviewer_id,
            review_id="review-unsafe-role",
            reviewer_role=reviewer_role,
            executor_id=executor_id,
            verdict="pass",
            ref_path=str(review_path),
            reviewed_evidence_refs=[str(review_path)],
            source="go_evidence_finalize",
        )

    assert journal.read_bytes() == journal_before
    view = build_team_runtime_view(runtime)
    assert _review_task(view, reviewer_id)["status"] == "claimed"
    assert _reviewer(view, reviewer_id)["status"] == "working"


def test_review_ref_must_match_the_active_reviewer_assignment(tmp_path):
    runtime, run_id, executor_id, team = _run_workflow(tmp_path)
    team.record_task_created(
        run_id,
        "reviewer-1",
        task_kind="independent_review",
        agent_role="reviewer",
        targets=["a.py"],
    )
    team.record_task_claimed(run_id, "reviewer-1")
    review_path = tmp_path / "review.yaml"
    review_path.write_text("verdict: pass\n", encoding="utf-8")
    journal = runtime / "team-events.jsonl"
    journal_before = journal.read_bytes()

    with pytest.raises(ValueError, match="active review assignment"):
        team.record_review_ref(
            run_id,
            "reviewer-2",
            review_id="review-wrong-reviewer",
            reviewer_role="reviewer",
            executor_id=executor_id,
            verdict="pass",
            ref_path=str(review_path),
            reviewed_evidence_refs=[str(review_path)],
            source="go_evidence_finalize",
        )

    assert journal.read_bytes() == journal_before
    view = build_team_runtime_view(runtime)
    assert _review_task(view, "reviewer-1")["status"] == "claimed"
    assert _reviewer(view, "reviewer-1")["status"] == "working"


@pytest.mark.parametrize(
    ("review_id", "verdict", "reviewed_evidence_refs", "error"),
    [
        ("review-invalid-structure", "completed", ["inventory.md"], "verdict"),
        ("review-invalid-structure", "pass", [], "evidence"),
        ("", "pass", ["inventory.md"], "review_id"),
    ],
)
def test_review_ref_requires_canonical_verdict_and_evidence_reference(
    tmp_path, review_id, verdict, reviewed_evidence_refs, error
):
    runtime, run_id, executor_id, team = _run_workflow(tmp_path)
    reviewer_id = "reviewer-1"
    team.record_task_created(
        run_id,
        reviewer_id,
        task_kind="independent_review",
        agent_role="reviewer",
        targets=["a.py"],
    )
    team.record_task_claimed(run_id, reviewer_id)
    review_path = tmp_path / "review.yaml"
    review_path.write_text("verdict: pass\n", encoding="utf-8")
    journal = runtime / "team-events.jsonl"
    journal_before = journal.read_bytes()

    with pytest.raises(ValueError, match=error):
        team.record_review_ref(
            run_id,
            reviewer_id,
            review_id=review_id,
            reviewer_role="reviewer",
            executor_id=executor_id,
            verdict=verdict,
            ref_path=str(review_path),
            reviewed_evidence_refs=reviewed_evidence_refs,
            source="go_evidence_finalize",
        )

    assert journal.read_bytes() == journal_before
    view = build_team_runtime_view(runtime)
    assert _review_task(view, reviewer_id)["status"] == "claimed"
    assert _reviewer(view, reviewer_id)["status"] == "working"


@pytest.mark.parametrize(
    ("reviewer_id_kind", "agent_role", "error"),
    [
        ("executor", "reviewer", "execution worker"),
        ("controller", "reviewer", "not independent"),
        ("coordinator", "reviewer", "not independent"),
        ("root", "reviewer", "not independent"),
        ("", "reviewer", "not independent"),
        ("reviewer-1", "controller", "not independent"),
    ],
)
def test_review_assignment_rejects_execution_and_governance_authors(
    tmp_path, reviewer_id_kind, agent_role, error
):
    runtime, run_id, executor_id, team = _run_workflow(tmp_path)
    reviewer_id = executor_id if reviewer_id_kind == "executor" else reviewer_id_kind
    journal = runtime / "team-events.jsonl"
    journal_before = journal.read_bytes()

    with pytest.raises(ValueError, match=error):
        team.record_task_created(
            run_id,
            reviewer_id,
            task_kind="independent_review",
            agent_role=agent_role,
            targets=["a.py"],
        )

    assert journal.read_bytes() == journal_before


@pytest.mark.parametrize("reviewer_id_kind", ["executor", "controller", "coordinator", "root"])
def test_legacy_review_ref_rejects_execution_and_governance_authors(
    tmp_path, reviewer_id_kind
):
    runtime, run_id, executor_id, team = _run_workflow(tmp_path)
    reviewer_id = executor_id if reviewer_id_kind == "executor" else reviewer_id_kind
    review_path = tmp_path / "review.yaml"
    review_path.write_text("verdict: pass\n", encoding="utf-8")
    journal = runtime / "team-events.jsonl"
    journal_before = journal.read_bytes()

    with pytest.raises(ValueError, match="not independent|execution worker"):
        team.record_review_ref(
            run_id,
            reviewer_id,
            review_id="review-legacy-unsafe-author",
            reviewer_role="reviewer",
            executor_id=executor_id,
            verdict="pass",
            ref_path=str(review_path),
            reviewed_evidence_refs=[str(review_path)],
            source="go_evidence_finalize",
        )

    assert journal.read_bytes() == journal_before


def test_review_ref_implicitly_binds_legacy_writer_to_one_assignment(tmp_path):
    runtime, run_id, executor_id, team = _run_workflow(tmp_path)
    reviewer_id = "reviewer-1"
    review_path = tmp_path / "legacy-bound-review.yaml"
    review_path.write_text("verdict: pass\n", encoding="utf-8")

    team.record_review_ref(
        run_id,
        reviewer_id,
        review_id="legacy-bound-review",
        reviewer_role="reviewer",
        executor_id=executor_id,
        verdict="pass",
        ref_path=str(review_path),
        reviewed_evidence_refs=[str(review_path)],
        source="go_evidence_finalize",
    )

    reviewer_events = [
        event["event_type"]
        for event in team.read_all()
        if event["agent_id"] == reviewer_id
    ]
    assert reviewer_events == ["task_created", "task_claimed", "review_ref"]
    view = build_team_runtime_view(runtime)
    assert _review_task(view, reviewer_id)["status"] == "claimed"
    record = _team_record(runtime)
    assert record["review_refs"][0]["reviewer_id"] == reviewer_id


def test_legacy_review_ref_is_revoked_if_identity_later_claims_execution(tmp_path):
    runtime, run_id, executor_id, _team = _run_workflow(tmp_path)
    reviewer_id = "agent-shared"
    review_id = "legacy-review-before-execution"
    review_path = tmp_path / "legacy-review-before-execution.yaml"
    review_path.write_text("verdict: pass\n", encoding="utf-8")
    gate_id = f"gate-{run_id}-independent-review"
    final_path = tmp_path / "final-verdict-before-execution.json"
    artifact = _write_final_verdict_artifact(
        final_path,
        run_id=run_id,
        reviewer_id=reviewer_id,
        review_path=review_path,
        gate_id=gate_id,
    )
    raw_events = [
        {
            "event_type": "review_ref",
            "run_id": run_id,
            "agent_id": reviewer_id,
            "payload": {
                "review_id": review_id,
                "reviewer_id": reviewer_id,
                "reviewer_role": "reviewer",
                "executor_id": executor_id,
                "verdict": "pass",
                "ref_path": str(review_path),
                "reviewed_evidence_refs": [str(review_path)],
                "source": "legacy-go-evidence-finalize",
            },
            "timestamp": "2026-07-23T01:00:00+00:00",
            "event_id": "legacy-review-before-execution",
        },
        {
            "event_type": "final_verdict_ref",
            "run_id": run_id,
            "agent_id": artifact["produced_by"],
            "payload": {
                "verdict_id": artifact["verdict_id"],
                "produced_by": artifact["produced_by"],
                "producer_role": artifact["producer_role"],
                "final_state": artifact["final_state"],
                "ref_path": str(final_path),
                "review_ref": review_id,
                "gate_refs": [gate_id],
                "gate_summary": artifact["gate_summary"],
                "limitations": artifact["limitations"],
                "human_or_governance_reference": artifact[
                    "human_or_governance_reference"
                ],
            },
            "timestamp": "2026-07-23T01:00:01+00:00",
            "event_id": "legacy-final-before-execution",
        },
        {
            "event_type": "task_created",
            "run_id": run_id,
            "agent_id": reviewer_id,
            "payload": {
                "project_id": "legacy-takeover",
                "targets": ["takeover.py"],
                "context_refs": [],
                "task_kind": "execution",
                "agent_role": "worker",
            },
            "timestamp": "2026-07-23T01:00:02+00:00",
            "event_id": "legacy-execution-after-review",
        },
        {
            "event_type": "task_claimed",
            "run_id": run_id,
            "agent_id": reviewer_id,
            "payload": {"context_refs": []},
            "timestamp": "2026-07-23T01:00:03+00:00",
            "event_id": "legacy-execution-claim-after-review",
        },
    ]
    for event in raw_events:
        _append_team_event(runtime, event)

    record = _team_record(runtime)
    assert {
        "review_ref_count": len(record.get("review_refs", [])),
        "has_final_verdict": "final_verdict_ref" in record,
        "acceptance_state": record["acceptance_state"],
        "has_failure": bool(record.get("failure_refs")),
    } == {
        "review_ref_count": 0,
        "has_final_verdict": False,
        "acceptance_state": "blocked",
        "has_failure": True,
    }
    view = build_team_runtime_view(runtime)
    unsafe_gate_kinds = {
        gate["kind"]
        for gate in view["review_gates"]
        if gate["status"] == "pass"
    }
    assert "independent-review" not in unsafe_gate_kinds
    assert "final-verdict" not in unsafe_gate_kinds


def test_raw_concurrent_review_assignments_block_final_ready_after_later_fail(
    tmp_path,
):
    runtime, run_id, executor_id, _team = _run_workflow(tmp_path)
    review_a_path = tmp_path / "reviewer-a-pass.yaml"
    review_a_path.write_text("verdict: pass\n", encoding="utf-8")
    review_b_path = tmp_path / "reviewer-b-fail.yaml"
    review_b_path.write_text("verdict: fail\n", encoding="utf-8")
    gate_id = f"gate-{run_id}-independent-review"
    final_path = tmp_path / "final-verdict-before-later-fail.json"
    artifact = _write_final_verdict_artifact(
        final_path,
        run_id=run_id,
        reviewer_id="reviewer-a",
        review_path=review_a_path,
        gate_id=gate_id,
    )
    raw_events = [
        {
            "event_type": "task_created",
            "run_id": run_id,
            "agent_id": "reviewer-a",
            "payload": {
                "targets": ["a.py"],
                "task_kind": "independent_review",
                "agent_role": "reviewer",
            },
            "timestamp": "2026-07-23T02:00:00+00:00",
            "event_id": "raw-reviewer-a-created",
        },
        {
            "event_type": "task_claimed",
            "run_id": run_id,
            "agent_id": "reviewer-a",
            "payload": {"context_refs": []},
            "timestamp": "2026-07-23T02:00:01+00:00",
            "event_id": "raw-reviewer-a-claimed",
        },
        {
            "event_type": "task_created",
            "run_id": run_id,
            "agent_id": "reviewer-b",
            "payload": {
                "targets": ["disjoint.py"],
                "task_kind": "independent_review",
                "agent_role": "reviewer",
            },
            "timestamp": "2026-07-23T02:00:02+00:00",
            "event_id": "raw-reviewer-b-created",
        },
        {
            "event_type": "task_claimed",
            "run_id": run_id,
            "agent_id": "reviewer-b",
            "payload": {"context_refs": []},
            "timestamp": "2026-07-23T02:00:03+00:00",
            "event_id": "raw-reviewer-b-claimed",
        },
        {
            "event_type": "review_ref",
            "run_id": run_id,
            "agent_id": "reviewer-a",
            "payload": {
                "review_id": "raw-reviewer-a-pass",
                "reviewer_id": "reviewer-a",
                "reviewer_role": "reviewer",
                "executor_id": executor_id,
                "verdict": "pass",
                "ref_path": str(review_a_path),
                "reviewed_evidence_refs": [str(review_a_path)],
            },
            "timestamp": "2026-07-23T02:00:04+00:00",
            "event_id": "raw-reviewer-a-pass",
        },
        {
            "event_type": "final_verdict_ref",
            "run_id": run_id,
            "agent_id": artifact["produced_by"],
            "payload": {
                "verdict_id": artifact["verdict_id"],
                "produced_by": artifact["produced_by"],
                "producer_role": artifact["producer_role"],
                "final_state": artifact["final_state"],
                "ref_path": str(final_path),
                "review_ref": "raw-reviewer-a-pass",
                "gate_refs": [gate_id],
                "gate_summary": artifact["gate_summary"],
                "limitations": artifact["limitations"],
                "human_or_governance_reference": artifact[
                    "human_or_governance_reference"
                ],
            },
            "timestamp": "2026-07-23T02:00:05+00:00",
            "event_id": "raw-final-before-later-fail",
        },
        {
            "event_type": "review_ref",
            "run_id": run_id,
            "agent_id": "reviewer-b",
            "payload": {
                "review_id": "raw-reviewer-b-fail",
                "reviewer_id": "reviewer-b",
                "reviewer_role": "reviewer",
                "executor_id": executor_id,
                "verdict": "fail",
                "ref_path": str(review_b_path),
                "reviewed_evidence_refs": [str(review_b_path)],
            },
            "timestamp": "2026-07-23T02:00:06+00:00",
            "event_id": "raw-reviewer-b-fail",
        },
    ]
    for event in raw_events:
        _append_team_event(runtime, event)

    record = _team_record(runtime)
    assert {
        "has_final_verdict": "final_verdict_ref" in record,
        "acceptance_state": record["acceptance_state"],
        "projection_state": record["projection_state"],
        "has_failure": bool(record.get("failure_refs")),
    } == {
        "has_final_verdict": False,
        "acceptance_state": "blocked",
        "projection_state": "blocked",
        "has_failure": True,
    }
    final_gates = [
        gate
        for gate in build_team_runtime_view(runtime)["review_gates"]
        if gate["kind"] == "final-verdict" and gate["status"] == "pass"
    ]
    assert final_gates == []


def test_review_api_rejects_review_id_reuse_across_assignment_generations(
    tmp_path,
):
    runtime, run_id, executor_id, team = _run_workflow(tmp_path)
    review_id = "review-generation-unique"
    first_reviewer = "reviewer-a"
    team.record_task_created(
        run_id,
        first_reviewer,
        task_kind="independent_review",
        agent_role="reviewer",
        targets=["a.py"],
    )
    team.record_task_claimed(run_id, first_reviewer)
    _record_pass_review_and_final(
        tmp_path,
        team,
        run_id=run_id,
        executor_id=executor_id,
        reviewer_id=first_reviewer,
        review_id=review_id,
        file_stem="first-generation",
    )
    second_reviewer = "reviewer-b"
    team.record_task_created(
        run_id,
        second_reviewer,
        task_kind="independent_review",
        agent_role="reviewer",
        targets=["b.py"],
    )
    team.record_task_claimed(run_id, second_reviewer)
    second_review_path = tmp_path / "second-generation-review.yaml"
    second_review_path.write_text("verdict: pass\n", encoding="utf-8")
    journal = runtime / TEAM_EVENTS_FILE
    journal_before = journal.read_bytes()

    with pytest.raises(ValueError, match="review_id"):
        team.record_review_ref(
            run_id,
            second_reviewer,
            review_id=review_id,
            reviewer_role="reviewer",
            executor_id=executor_id,
            verdict="pass",
            ref_path=str(second_review_path),
            reviewed_evidence_refs=[str(second_review_path)],
        )

    assert journal.read_bytes() == journal_before


def test_exact_review_replay_is_not_idempotent_in_a_new_generation(tmp_path):
    runtime, run_id, executor_id, team = _run_workflow(tmp_path)
    reviewer_id = "reviewer-a"
    review_id = "review-exact-replay"
    team.record_task_created(
        run_id,
        reviewer_id,
        task_kind="independent_review",
        agent_role="reviewer",
        targets=["a.py"],
    )
    team.record_task_claimed(run_id, reviewer_id)
    _record_pass_review_and_final(
        tmp_path,
        team,
        run_id=run_id,
        executor_id=executor_id,
        reviewer_id=reviewer_id,
        review_id=review_id,
        file_stem="exact-replay",
    )
    team.record_task_created(
        run_id,
        reviewer_id,
        task_kind="independent_review",
        agent_role="reviewer",
        targets=["a.py"],
    )
    team.record_task_claimed(run_id, reviewer_id)
    review_path = tmp_path / "exact-replay-review.yaml"
    journal = runtime / TEAM_EVENTS_FILE
    journal_before = journal.read_bytes()

    with pytest.raises(ValueError, match="review_id"):
        team.record_review_ref(
            run_id,
            reviewer_id,
            review_id=review_id,
            reviewer_role="reviewer",
            executor_id=executor_id,
            verdict="pass",
            ref_path=str(review_path),
            reviewed_evidence_refs=[str(review_path)],
        )

    assert journal.read_bytes() == journal_before


def test_exact_review_replay_remains_idempotent_in_the_same_generation(
    tmp_path,
):
    runtime, run_id, executor_id, team = _run_workflow(tmp_path)
    reviewer_id = "reviewer-a"
    review_path = tmp_path / "same-generation-review.yaml"
    review_path.write_text("verdict: pass\n", encoding="utf-8")
    team.record_task_created(
        run_id,
        reviewer_id,
        task_kind="independent_review",
        agent_role="reviewer",
        targets=["a.py"],
    )
    team.record_task_claimed(run_id, reviewer_id)
    kwargs = {
        "review_id": "review-same-generation",
        "reviewer_role": "reviewer",
        "executor_id": executor_id,
        "verdict": "pass",
        "ref_path": str(review_path),
        "reviewed_evidence_refs": [str(review_path)],
    }

    first_event_id = team.record_review_ref(
        run_id, reviewer_id, **kwargs
    )
    journal = runtime / TEAM_EVENTS_FILE
    journal_after_first = journal.read_bytes()
    repeated_event_id = team.record_review_ref(
        run_id, reviewer_id, **kwargs
    )

    assert repeated_event_id == first_event_id
    assert journal.read_bytes() == journal_after_first


def test_active_sequential_reassignment_resets_run_axes_to_review_pending(
    tmp_path,
):
    runtime, run_id, executor_id, team = _run_workflow(tmp_path)
    first_reviewer = "reviewer-a"
    team.record_task_created(
        run_id,
        first_reviewer,
        task_kind="independent_review",
        agent_role="reviewer",
        targets=["a.py"],
    )
    team.record_task_claimed(run_id, first_reviewer)
    _record_pass_review_and_final(
        tmp_path,
        team,
        run_id=run_id,
        executor_id=executor_id,
        reviewer_id=first_reviewer,
        review_id="review-generation-one",
        file_stem="active-reset-first",
    )
    second_reviewer = "reviewer-b"
    team.record_task_created(
        run_id,
        second_reviewer,
        task_kind="independent_review",
        agent_role="reviewer",
        targets=["b.py"],
    )
    team.record_task_claimed(run_id, second_reviewer)

    record = _team_record(runtime)

    assert {
        "has_final_verdict": "final_verdict_ref" in record,
        "review_state": record["review_state"],
        "gate_state": record["gate_state"],
        "acceptance_state": record["acceptance_state"],
        "has_failure": bool(record.get("failure_refs")),
    } == {
        "has_final_verdict": False,
        "review_state": "review_pending",
        "gate_state": "not_evaluated",
        "acceptance_state": "review_pending",
        "has_failure": False,
    }


def test_raw_review_id_reuse_across_generations_fails_closed(tmp_path):
    runtime, run_id, executor_id, team = _run_workflow(tmp_path)
    review_id = "raw-generation-reuse"
    first_reviewer = "reviewer-a"
    team.record_task_created(
        run_id,
        first_reviewer,
        task_kind="independent_review",
        agent_role="reviewer",
        targets=["a.py"],
    )
    team.record_task_claimed(run_id, first_reviewer)
    _record_pass_review_and_final(
        tmp_path,
        team,
        run_id=run_id,
        executor_id=executor_id,
        reviewer_id=first_reviewer,
        review_id=review_id,
        file_stem="raw-reuse-first",
    )
    second_reviewer = "reviewer-b"
    team.record_task_created(
        run_id,
        second_reviewer,
        task_kind="independent_review",
        agent_role="reviewer",
        targets=["b.py"],
    )
    team.record_task_claimed(run_id, second_reviewer)
    second_review_path = tmp_path / "raw-reuse-second-review.yaml"
    second_review_path.write_text("verdict: pass\n", encoding="utf-8")
    _append_team_event(runtime, {
        "event_type": "review_ref",
        "run_id": run_id,
        "agent_id": second_reviewer,
        "payload": {
            "review_id": review_id,
            "reviewer_id": second_reviewer,
            "reviewer_role": "reviewer",
            "executor_id": executor_id,
            "verdict": "pass",
            "ref_path": str(second_review_path),
            "reviewed_evidence_refs": [str(second_review_path)],
        },
        "timestamp": "2026-07-23T03:00:00+00:00",
        "event_id": "raw-generation-reuse-second-review",
    })

    record = _team_record(runtime)

    assert {
        "has_final_verdict": "final_verdict_ref" in record,
        "review_refs": record.get("review_refs", []),
        "acceptance_state": record["acceptance_state"],
        "projection_state": record["projection_state"],
        "has_failure": bool(record.get("failure_refs")),
    } == {
        "has_final_verdict": False,
        "review_refs": [],
        "acceptance_state": "blocked",
        "projection_state": "blocked",
        "has_failure": True,
    }
    assert any(
        gate["kind"] == "independent-review" and gate["status"] == "blocked"
        for gate in build_team_runtime_view(runtime)["review_gates"]
    )


def test_sequential_new_review_id_can_produce_a_new_canonical_final(
    tmp_path,
):
    runtime, run_id, executor_id, team = _run_workflow(tmp_path)
    first_reviewer = "reviewer-a"
    team.record_task_created(
        run_id,
        first_reviewer,
        task_kind="independent_review",
        agent_role="reviewer",
        targets=["a.py"],
    )
    team.record_task_claimed(run_id, first_reviewer)
    _record_pass_review_and_final(
        tmp_path,
        team,
        run_id=run_id,
        executor_id=executor_id,
        reviewer_id=first_reviewer,
        review_id="review-generation-one",
        file_stem="new-id-first",
    )
    second_reviewer = "reviewer-b"
    second_review_id = "review-generation-two"
    second_verdict_id = f"fv-{run_id}-generation-two"
    team.record_task_created(
        run_id,
        second_reviewer,
        task_kind="independent_review",
        agent_role="reviewer",
        targets=["b.py"],
    )
    team.record_task_claimed(run_id, second_reviewer)
    _record_pass_review_and_final(
        tmp_path,
        team,
        run_id=run_id,
        executor_id=executor_id,
        reviewer_id=second_reviewer,
        review_id=second_review_id,
        file_stem="new-id-second",
        verdict_id=second_verdict_id,
    )

    record = _team_record(runtime)

    assert record["acceptance_state"] == "final_ready"
    assert record["projection_state"] == "completed"
    assert record["review_refs"][-1]["review_id"] == second_review_id
    assert record["final_verdict_ref"]["verdict_id"] == second_verdict_id
    assert record["final_verdict_ref"]["review_ref"] == second_review_id
    assert not record.get("failure_refs")
    final_gates = [
        gate
        for gate in build_team_runtime_view(runtime)["review_gates"]
        if gate["kind"] == "final-verdict" and gate["status"] == "pass"
    ]
    assert len(final_gates) == 1
    assert final_gates[0]["gate_id"] == (
        f"team-final-verdict-{second_verdict_id}"
    )


def test_bound_review_keeps_raw_identity_while_view_uses_projected_id(tmp_path):
    runtime, run_id, executor_id, team = _run_workflow(tmp_path)
    reviewer_id = "Reviewer_Alpha"
    projected_id = "reviewer-alpha"
    review_path = tmp_path / "opaque-id-review.yaml"
    review_path.write_text("verdict: pass\n", encoding="utf-8")
    team.record_task_created(
        run_id,
        reviewer_id,
        task_kind="independent_review",
        agent_role="reviewer",
        targets=["a.py"],
    )
    team.record_task_claimed(run_id, reviewer_id)

    team.record_review_ref(
        run_id,
        reviewer_id,
        review_id="opaque-id-review",
        reviewer_role="reviewer",
        executor_id=executor_id,
        verdict="pass",
        ref_path=str(review_path),
        reviewed_evidence_refs=[str(review_path)],
    )

    view = build_team_runtime_view(runtime)
    assert _review_task(view, projected_id)["status"] == "claimed"
    assert _team_record(runtime)["review_refs"][0]["reviewer_id"] == reviewer_id


def test_final_verdict_api_rejects_missing_gates_without_releasing_owner(tmp_path):
    runtime, run_id, executor_id, team = _run_workflow(tmp_path)
    reviewer_id = "reviewer-1"
    review_id = "review-pending-final-api"
    review_path = tmp_path / "review.yaml"
    review_path.write_text("verdict: pass\n", encoding="utf-8")
    team.record_task_created(
        run_id,
        reviewer_id,
        task_kind="independent_review",
        agent_role="reviewer",
        targets=["a.py"],
    )
    team.record_task_claimed(run_id, reviewer_id)
    team.record_review_ref(
        run_id,
        reviewer_id,
        review_id=review_id,
        reviewer_role="reviewer",
        executor_id=executor_id,
        verdict="pass",
        ref_path=str(review_path),
        reviewed_evidence_refs=[str(review_path)],
        source="go_evidence_finalize",
    )
    final_path = tmp_path / "final-verdict.json"
    gate_id = f"gate-{run_id}-independent-review"
    artifact = _write_final_verdict_artifact(
        final_path,
        run_id=run_id,
        reviewer_id=reviewer_id,
        review_path=review_path,
        gate_id=gate_id,
    )
    journal = runtime / TEAM_EVENTS_FILE
    journal_before = journal.read_bytes()

    with pytest.raises(ValueError, match="gate"):
        team.record_final_verdict_ref(
            run_id,
            artifact["produced_by"],
            verdict_id=artifact["verdict_id"],
            producer_role=artifact["producer_role"],
            final_state=artifact["final_state"],
            ref_path=str(final_path),
            review_ref=review_id,
            gate_refs=[],
            gate_summary=artifact["gate_summary"],
            limitations=artifact["limitations"],
            human_or_governance_reference=artifact[
                "human_or_governance_reference"
            ],
        )

    assert journal.read_bytes() == journal_before
    assert _review_task(build_team_runtime_view(runtime), reviewer_id)["status"] == "claimed"
    with pytest.raises(ValueError, match="active review assignment"):
        team.record_task_created(
            run_id,
            "reviewer-2",
            task_kind="independent_review",
            agent_role="reviewer",
            targets=["a.py"],
        )
    final_kwargs = {
        "verdict_id": artifact["verdict_id"],
        "producer_role": artifact["producer_role"],
        "final_state": artifact["final_state"],
        "ref_path": str(final_path),
        "review_ref": review_id,
        "gate_refs": [gate_id],
        "gate_summary": artifact["gate_summary"],
        "limitations": artifact["limitations"],
        "human_or_governance_reference": artifact[
            "human_or_governance_reference"
        ],
    }

    final_event_id = team.record_final_verdict_ref(
        run_id, artifact["produced_by"], **final_kwargs
    )
    repeated_event_id = team.record_final_verdict_ref(
        run_id, artifact["produced_by"], **final_kwargs
    )

    assert repeated_event_id == final_event_id
    assert sum(
        event["event_type"] == "final_verdict_ref" for event in team.read_all()
    ) == 1
    assert _review_task(build_team_runtime_view(runtime), reviewer_id)["status"] == "completed"
    journal_after_final = journal.read_bytes()
    with pytest.raises(ValueError, match="reviewer"):
        team.record_task_created(
            run_id,
            reviewer_id,
            task_kind="execution",
            agent_role="worker",
            targets=["a.py"],
        )
    assert journal.read_bytes() == journal_after_final


@pytest.mark.parametrize(
    "mutation",
    [
        "producer_id",
        "producer_role",
        "final_state",
        "verdict_id",
        "ref_path",
        "review_ref",
        "gate_refs",
        "event_gate_summary",
        "artifact_schema",
        "artifact_reviewer",
        "artifact_gate_evidence",
        "artifact_inputs_reviewed",
        "human_reference",
        "limitations",
    ],
)
def test_final_verdict_api_rejects_noncanonical_identity_before_journal_mutation(
    tmp_path, mutation
):
    runtime, run_id, executor_id, team = _run_workflow(tmp_path)
    reviewer_id = "reviewer-1"
    review_id = "review-pending-final-identity"
    review_path = tmp_path / "review.yaml"
    review_path.write_text("verdict: pass\n", encoding="utf-8")
    team.record_task_created(
        run_id,
        reviewer_id,
        task_kind="independent_review",
        agent_role="reviewer",
        targets=["a.py"],
    )
    team.record_task_claimed(run_id, reviewer_id)
    team.record_review_ref(
        run_id,
        reviewer_id,
        review_id=review_id,
        reviewer_role="reviewer",
        executor_id=executor_id,
        verdict="pass",
        ref_path=str(review_path),
        reviewed_evidence_refs=[str(review_path)],
        source="go_evidence_finalize",
    )
    final_path = tmp_path / "final-verdict.json"
    gate_id = f"gate-{run_id}-independent-review"
    artifact = _write_final_verdict_artifact(
        final_path,
        run_id=run_id,
        reviewer_id=reviewer_id,
        review_path=review_path,
        gate_id=gate_id,
    )
    producer_id = artifact["produced_by"]
    kwargs = {
        "verdict_id": artifact["verdict_id"],
        "producer_role": artifact["producer_role"],
        "final_state": artifact["final_state"],
        "ref_path": str(final_path),
        "review_ref": review_id,
        "gate_refs": [gate_id],
        "gate_summary": artifact["gate_summary"],
        "limitations": artifact["limitations"],
        "human_or_governance_reference": artifact[
            "human_or_governance_reference"
        ],
    }
    if mutation == "producer_id":
        producer_id = "client-finalizer"
    elif mutation == "producer_role":
        kwargs["producer_role"] = "client"
    elif mutation == "final_state":
        kwargs["final_state"] = "blocked"
    elif mutation == "verdict_id":
        kwargs["verdict_id"] = ""
    elif mutation == "ref_path":
        kwargs["ref_path"] = ""
    elif mutation == "review_ref":
        kwargs["review_ref"] = "review-other"
    elif mutation == "gate_refs":
        kwargs["gate_refs"] = ["gate-other"]
    elif mutation == "event_gate_summary":
        kwargs["gate_summary"] = [{
            "gate_id": gate_id,
            "result": "pass",
            "evidence_path": "other-review.yaml",
        }]
    elif mutation == "artifact_schema":
        artifact.pop("produced_at")
    elif mutation == "artifact_reviewer":
        artifact["reviewer_summary"]["reviewer_id"] = "reviewer-2"
    elif mutation == "artifact_gate_evidence":
        artifact["gate_summary"][0]["evidence_path"] = "other-review.yaml"
        kwargs["gate_summary"] = artifact["gate_summary"]
    elif mutation == "artifact_inputs_reviewed":
        artifact["inputs_reviewed"] = ["other-evidence.json"]
    elif mutation == "human_reference":
        kwargs["human_or_governance_reference"] = "other-governance-reference"
    elif mutation == "limitations":
        kwargs["limitations"] = ["fabricated limitation"]
    final_path.write_text(json.dumps(artifact, indent=2) + "\n", encoding="utf-8")
    journal = runtime / TEAM_EVENTS_FILE
    journal_before = journal.read_bytes()

    with pytest.raises(ValueError, match="Final verdict"):
        team.record_final_verdict_ref(run_id, producer_id, **kwargs)

    assert journal.read_bytes() == journal_before
    assert _review_task(build_team_runtime_view(runtime), reviewer_id)["status"] == "claimed"
    with pytest.raises(ValueError, match="active review assignment"):
        team.record_task_created(
            run_id,
            "reviewer-2",
            task_kind="independent_review",
            agent_role="reviewer",
            targets=["a.py"],
        )


def test_run_index_rejects_governance_author_review_event(tmp_path):
    runtime, run_id, executor_id, _team = _run_workflow(tmp_path)
    review_path = tmp_path / "controller-review.yaml"
    review_path.write_text("verdict: pass\n", encoding="utf-8")
    _append_team_event(runtime, {
        "event_type": "review_ref",
        "run_id": run_id,
        "agent_id": "controller",
        "payload": {
            "review_id": "review-controller-bypass",
            "reviewer_id": "controller",
            "reviewer_role": "controller",
            "executor_id": executor_id,
            "verdict": "pass",
            "ref_path": str(review_path),
            "reviewed_evidence_refs": [str(review_path)],
        },
        "timestamp": "2026-07-23T00:00:00+00:00",
        "event_id": "controller-review-bypass",
    })

    record = _team_record(runtime)

    assert record.get("review_refs", []) == []
    assert record.get("failure_refs")
    assert "final_verdict_ref" not in record


def test_run_index_treats_unknown_task_kind_as_execution_for_review_safety(tmp_path):
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    review_path = tmp_path / "unknown-kind-review.yaml"
    review_path.write_text("verdict: pass\n", encoding="utf-8")
    for event in [
        {
            "event_type": "task_created",
            "run_id": "go-unknown-kind",
            "agent_id": "agent-1",
            "payload": {
                "targets": ["a.py"],
                "task_kind": "mystery",
                "agent_role": "worker",
            },
            "timestamp": "2026-07-23T00:00:00+00:00",
            "event_id": "unknown-kind-task",
        },
        {
            "event_type": "task_result",
            "run_id": "go-unknown-kind",
            "agent_id": "agent-1",
            "payload": {"status": "passed"},
            "timestamp": "2026-07-23T00:00:01+00:00",
            "event_id": "unknown-kind-result",
        },
        {
            "event_type": "review_ref",
            "run_id": "go-unknown-kind",
            "agent_id": "agent-1",
            "payload": {
                "review_id": "unknown-kind-self-review",
                "reviewer_id": "agent-1",
                "reviewer_role": "reviewer",
                "executor_id": "",
                "verdict": "pass",
                "ref_path": str(review_path),
                "reviewed_evidence_refs": [str(review_path)],
            },
            "timestamp": "2026-07-23T00:00:02+00:00",
            "event_id": "unknown-kind-self-review",
        },
    ]:
        _append_team_event(runtime, event)

    record = _team_record(runtime)

    assert record.get("review_refs", []) == []
    assert record.get("failure_refs")
    assert {worker["worker_id"] for worker in record["worker_results"]} == {"agent-1"}


def test_run_index_requires_review_ref_to_match_active_assignment(tmp_path):
    runtime, run_id, executor_id, team = _run_workflow(tmp_path)
    team.record_task_created(
        run_id,
        "reviewer-1",
        task_kind="independent_review",
        agent_role="reviewer",
        targets=["a.py"],
    )
    team.record_task_claimed(run_id, "reviewer-1")
    review_path = tmp_path / "wrong-reviewer.yaml"
    review_path.write_text("verdict: pass\n", encoding="utf-8")
    _append_team_event(runtime, {
        "event_type": "review_ref",
        "run_id": run_id,
        "agent_id": "reviewer-2",
        "payload": {
            "review_id": "review-wrong-assignee-bypass",
            "reviewer_id": "reviewer-2",
            "reviewer_role": "reviewer",
            "executor_id": executor_id,
            "verdict": "pass",
            "ref_path": str(review_path),
            "reviewed_evidence_refs": [str(review_path)],
        },
        "timestamp": "2026-07-23T00:00:00+00:00",
        "event_id": "wrong-assignee-review-bypass",
    })

    record = _team_record(runtime)

    assert record.get("review_refs", []) == []
    assert record.get("failure_refs")
    assert "final_verdict_ref" not in record


@pytest.mark.parametrize(
    ("verdict", "expected_axes"),
    [
        (
            "pass",
            {
                "phase": "awaiting_review",
                "outcome": "passed",
                "review_state": "review_passed",
                "gate_state": "not_evaluated",
                "acceptance_state": "review_pending",
                "projection_state": "completed",
            },
        ),
        (
            "fail",
            {
                "phase": "closed",
                "outcome": "failed",
                "review_state": "review_failed",
                "gate_state": "not_evaluated",
                "acceptance_state": "failed",
                "projection_state": "failed",
            },
        ),
        (
            "blocked",
            {
                "phase": "closed",
                "outcome": "blocked",
                "review_state": "review_blocked",
                "gate_state": "not_evaluated",
                "acceptance_state": "blocked",
                "projection_state": "blocked",
            },
        ),
        (
            "escalate",
            {
                "phase": "closed",
                "outcome": "human_required",
                "review_state": "escalated",
                "gate_state": "not_evaluated",
                "acceptance_state": "blocked",
                "projection_state": "waiting_for_you",
            },
        ),
    ],
)
def test_run_index_projects_each_review_verdict_to_truthful_axes(
    tmp_path, verdict, expected_axes
):
    runtime, run_id, executor_id, team = _run_workflow(tmp_path)
    reviewer_id = "reviewer-1"
    review_path = tmp_path / f"review-{verdict}.yaml"
    review_path.write_text(f"verdict: {verdict}\n", encoding="utf-8")
    team.record_task_created(
        run_id,
        reviewer_id,
        task_kind="independent_review",
        agent_role="reviewer",
        targets=["a.py"],
    )
    team.record_task_claimed(run_id, reviewer_id)
    team.record_review_ref(
        run_id,
        reviewer_id,
        review_id=f"review-axes-{verdict}",
        reviewer_role="reviewer",
        executor_id=executor_id,
        verdict=verdict,
        ref_path=str(review_path),
        reviewed_evidence_refs=[str(review_path)],
    )

    record = _team_record(runtime)

    assert {key: record[key] for key in expected_axes} == expected_axes


def test_fail_review_closes_assignment_as_rework_without_final_success(tmp_path):
    runtime, run_id, executor_id, team = _run_workflow(tmp_path)
    reviewer_id = "reviewer-1"
    team.record_task_created(
        run_id,
        reviewer_id,
        task_kind="independent_review",
        agent_role="reviewer",
        targets=["a.py"],
    )
    team.record_task_claimed(run_id, reviewer_id)
    inventory_path = tmp_path / "review-inventory.md"
    inventory_path.write_text("# Inventory only\n", encoding="utf-8")
    team.record_result(
        run_id,
        reviewer_id,
        status="completed",
        report_path=str(inventory_path),
    )
    review_path = tmp_path / "review-fail.yaml"
    review_path.write_text("verdict: fail\n", encoding="utf-8")

    team.record_review_ref(
        run_id,
        reviewer_id,
        review_id="review-rework-1",
        reviewer_role="reviewer",
        executor_id=executor_id,
        verdict="fail",
        ref_path=str(review_path),
        reviewed_evidence_refs=[str(inventory_path)],
        source="go_evidence_finalize",
    )

    view = build_team_runtime_view(runtime)
    assert _review_task(view, reviewer_id)["status"] == "failed"
    assert _reviewer(view, reviewer_id)["status"] == "failed"
    record = _team_record(runtime)
    assert record["review_refs"][0]["verdict"] == "fail"
    assert "final_verdict_ref" not in record
    team.record_task_created(
        run_id,
        "reviewer-2",
        task_kind="independent_review",
        agent_role="reviewer",
        targets=["a.py"],
    )


@pytest.mark.parametrize(
    ("later_verdict", "expected_axes"),
    [
        (
            "fail",
            {
                "outcome": "failed",
                "review_state": "review_failed",
                "acceptance_state": "failed",
                "projection_state": "failed",
            },
        ),
        (
            "blocked",
            {
                "outcome": "blocked",
                "review_state": "review_blocked",
                "acceptance_state": "blocked",
                "projection_state": "blocked",
            },
        ),
        (
            "escalate",
            {
                "outcome": "human_required",
                "review_state": "escalated",
                "acceptance_state": "blocked",
                "projection_state": "waiting_for_you",
            },
        ),
    ],
)
def test_post_terminal_nonpass_retry_invalidates_prior_final_ready(
    tmp_path, later_verdict, expected_axes
):
    runtime, run_id, executor_id, team = _run_workflow(tmp_path)
    first_reviewer = "reviewer-1"
    first_review_id = "review-before-retry"
    first_review_path = tmp_path / "review-before-retry.yaml"
    first_review_path.write_text("verdict: pass\n", encoding="utf-8")
    team.record_task_created(
        run_id,
        first_reviewer,
        task_kind="independent_review",
        agent_role="reviewer",
        targets=["a.py"],
    )
    team.record_task_claimed(run_id, first_reviewer)
    team.record_review_ref(
        run_id,
        first_reviewer,
        review_id=first_review_id,
        reviewer_role="reviewer",
        executor_id=executor_id,
        verdict="pass",
        ref_path=str(first_review_path),
        reviewed_evidence_refs=[str(first_review_path)],
    )
    gate_id = f"gate-{run_id}-independent-review"
    final_path = tmp_path / "final-verdict-before-retry.json"
    artifact = _write_final_verdict_artifact(
        final_path,
        run_id=run_id,
        reviewer_id=first_reviewer,
        review_path=first_review_path,
        gate_id=gate_id,
    )
    team.record_final_verdict_ref(
        run_id,
        artifact["produced_by"],
        verdict_id=artifact["verdict_id"],
        producer_role=artifact["producer_role"],
        final_state=artifact["final_state"],
        ref_path=str(final_path),
        review_ref=first_review_id,
        gate_refs=[gate_id],
        gate_summary=artifact["gate_summary"],
        limitations=artifact["limitations"],
        human_or_governance_reference=artifact[
            "human_or_governance_reference"
        ],
    )
    assert _team_record(runtime)["acceptance_state"] == "final_ready"

    retry_reviewer = "reviewer-2"
    team.record_task_created(
        run_id,
        retry_reviewer,
        task_kind="independent_review",
        agent_role="reviewer",
        targets=["disjoint.py"],
    )
    team.record_task_claimed(run_id, retry_reviewer)
    reopened_record = _team_record(runtime)
    assert "final_verdict_ref" not in reopened_record
    assert reopened_record["acceptance_state"] != "final_ready"
    assert not any(
        gate["kind"] == "final-verdict" and gate["status"] == "pass"
        for gate in build_team_runtime_view(runtime)["review_gates"]
    )
    retry_review_path = tmp_path / f"review-retry-{later_verdict}.yaml"
    retry_review_path.write_text(
        f"verdict: {later_verdict}\n", encoding="utf-8"
    )
    team.record_review_ref(
        run_id,
        retry_reviewer,
        review_id=f"review-retry-{later_verdict}",
        reviewer_role="reviewer",
        executor_id=executor_id,
        verdict=later_verdict,
        ref_path=str(retry_review_path),
        reviewed_evidence_refs=[str(retry_review_path)],
    )

    record = _team_record(runtime)
    assert "final_verdict_ref" not in record
    assert not record.get("failure_refs")
    assert record["review_refs"][-1]["verdict"] == later_verdict
    assert {key: record[key] for key in expected_axes} == expected_axes
    view = build_team_runtime_view(runtime)
    assert not any(
        gate["kind"] == "final-verdict" and gate["status"] == "pass"
        for gate in view["review_gates"]
    )
    team.record_task_created(
        run_id,
        "reviewer-3",
        task_kind="independent_review",
        agent_role="reviewer",
        targets=["retry.py"],
    )


@pytest.mark.parametrize("verdict", ["blocked", "escalate"])
def test_blocked_review_verdicts_preserve_blocked_semantics(tmp_path, verdict):
    runtime, run_id, executor_id, team = _run_workflow(tmp_path)
    reviewer_id = "reviewer-1"
    team.record_task_created(
        run_id,
        reviewer_id,
        task_kind="independent_review",
        agent_role="reviewer",
        targets=["a.py"],
    )
    team.record_task_claimed(run_id, reviewer_id)
    review_path = tmp_path / f"review-{verdict}.yaml"
    review_path.write_text(f"verdict: {verdict}\n", encoding="utf-8")

    team.record_review_ref(
        run_id,
        reviewer_id,
        review_id=f"review-{verdict}-1",
        reviewer_role="reviewer",
        executor_id=executor_id,
        verdict=verdict,
        ref_path=str(review_path),
        reviewed_evidence_refs=[str(review_path)],
        source="go_evidence_finalize",
    )

    view = build_team_runtime_view(runtime)
    assert _review_task(view, reviewer_id)["status"] == "blocked"
    assert _reviewer(view, reviewer_id)["status"] == "blocked"
    record = _team_record(runtime)
    assert record["review_refs"][0]["verdict"] == verdict
    assert "final_verdict_ref" not in record


@pytest.mark.parametrize(
    ("reviewer_role", "verdict"),
    [
        ("controller", "pass"),
        ("reviewer", "approved"),
    ],
)
def test_invalid_bypass_review_ref_does_not_release_assignment(
    tmp_path, reviewer_role, verdict
):
    runtime, run_id, executor_id, team = _run_workflow(tmp_path)
    reviewer_id = "reviewer-1"
    team.record_task_created(
        run_id,
        reviewer_id,
        task_kind="independent_review",
        agent_role="reviewer",
        targets=["a.py"],
    )
    team.record_task_claimed(run_id, reviewer_id)
    review_path = tmp_path / "invalid-controller-review.yaml"
    review_path.write_text("verdict: pass\n", encoding="utf-8")
    _append_team_event(runtime, {
        "event_type": "review_ref",
        "run_id": run_id,
        "agent_id": reviewer_id,
        "payload": {
            "review_id": "invalid-controller-review",
            "reviewer_id": reviewer_id,
            "reviewer_role": reviewer_role,
            "executor_id": executor_id,
            "verdict": verdict,
            "ref_path": str(review_path),
            "reviewed_evidence_refs": [str(review_path)],
        },
        "timestamp": "2026-07-23T00:00:00+00:00",
        "event_id": "invalid-controller-review",
    })

    view = build_team_runtime_view(runtime)
    assert _review_task(view, reviewer_id)["status"] == "claimed"
    assert _reviewer(view, reviewer_id)["status"] == "working"
    assert _team_record(runtime).get("review_refs", []) == []
    with pytest.raises(ValueError, match="active review assignment"):
        team.record_task_created(
            run_id,
            "reviewer-2",
            task_kind="independent_review",
            agent_role="reviewer",
            targets=["a.py"],
        )


@pytest.mark.parametrize("assignment_role", ["controller", ""])
def test_invalid_assignment_role_cannot_authorize_review_ref(
    tmp_path, assignment_role
):
    runtime, run_id, executor_id, _team = _run_workflow(tmp_path)
    reviewer_id = "reviewer-1"
    review_path = tmp_path / "spoofed-reviewer-role.yaml"
    review_path.write_text("verdict: pass\n", encoding="utf-8")
    _append_team_event(runtime, {
        "event_type": "task_created",
        "run_id": run_id,
        "agent_id": reviewer_id,
        "payload": {
            "project_id": "probe",
            "shard_index": 1,
            "shard_count": 1,
            "targets": ["a.py"],
            "context_refs": [],
            "task_kind": "independent_review",
            "agent_role": assignment_role,
        },
        "timestamp": "2026-07-23T00:00:00+00:00",
        "event_id": "invalid-review-assignment-role",
    })
    _append_team_event(runtime, {
        "event_type": "task_claimed",
        "run_id": run_id,
        "agent_id": reviewer_id,
        "payload": {"context_refs": []},
        "timestamp": "2026-07-23T00:00:01+00:00",
        "event_id": "invalid-review-assignment-claim",
    })
    _append_team_event(runtime, {
        "event_type": "review_ref",
        "run_id": run_id,
        "agent_id": reviewer_id,
        "payload": {
            "review_id": "spoofed-reviewer-role",
            "reviewer_id": reviewer_id,
            "reviewer_role": "reviewer",
            "executor_id": executor_id,
            "verdict": "pass",
            "ref_path": str(review_path),
            "reviewed_evidence_refs": [str(review_path)],
        },
        "timestamp": "2026-07-23T00:00:02+00:00",
        "event_id": "spoofed-reviewer-role",
    })

    view = build_team_runtime_view(runtime)
    assert _review_task(view, reviewer_id)["status"] == "claimed"
    assert _team_record(runtime).get("review_refs", []) == []
