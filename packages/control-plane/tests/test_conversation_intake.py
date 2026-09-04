from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier, Thread
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from control_plane.conversation_intake import (
    IntakeError,
    get_conversation_proposal,
    get_thread_intakes,
    record_intake,
)
from control_plane.cluster_run import _write_run_record
from control_plane.dashboard import build_dashboard_server
from control_plane.t3_adapter import _GLOBAL_COORDINATOR_THREAD_ID


def _post_json(base_url: str, path: str, payload: dict) -> tuple[int, dict]:
    request = Request(
        f"{base_url}{path}",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    with urlopen(request, timeout=5) as response:
        return response.status, json.loads(response.read().decode("utf-8"))


def _post_json_error(base_url: str, path: str, payload: dict) -> tuple[int, dict]:
    try:
        return _post_json(base_url, path, payload)
    except HTTPError as error:
        return error.code, json.loads(error.read().decode("utf-8"))


def _get_json(base_url: str, path: str) -> dict:
    with urlopen(f"{base_url}{path}", timeout=5) as response:
        return json.loads(response.read().decode("utf-8"))


def _record_development_intake(
    runtime_dir: Path,
    project: Path,
    *,
    request_id: str,
) -> dict:
    project.mkdir(parents=True, exist_ok=True)
    return record_intake(
        runtime_dir,
        _GLOBAL_COORDINATOR_THREAD_ID,
        project.name,
        request_id,
        "Implement one bounded development change.",
        environment_id="devframe-local",
        paper_project_dirs=[project],
    )


def test_conversation_intake_http_persists_and_projects_after_refresh(tmp_path: Path):
    runtime_dir = tmp_path / "runtime"
    project = tmp_path / "project-alpha"
    project.mkdir()
    server = build_dashboard_server(
        runtime_dir=runtime_dir,
        paper_project_dirs=[project],
        port=0,
        refresh_seconds=0,
    )
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_address[1]}"
    payload = {
        "threadId": _GLOBAL_COORDINATOR_THREAD_ID,
        "projectId": project.name,
        "clientRequestId": "request-001",
        "message": "Continue with the next verified product milestone.",
        "environmentId": "devframe-local",
    }

    try:
        status, accepted = _post_json(base_url, "/api/t3/conversation-intake", payload)
        assert status == 202
        assert accepted["accepted"] is True

        replay_status, replay = _post_json(base_url, "/api/t3/conversation-intake", payload)
        assert replay_status == 202
        assert replay["eventId"] == accepted["eventId"]
        assert replay["replayed"] is True

        conflict_status, conflict = _post_json_error(
            base_url,
            "/api/t3/conversation-intake",
            {**payload, "message": "This replay must not replace the original."},
        )
        assert conflict_status == 409
        assert conflict["error"] == "intake_conflict"

        shell = _get_json(base_url, "/t3-shell.json")
        detail = next(
            item
            for item in shell["t3"]["threadDetails"]
            if item["id"] == _GLOBAL_COORDINATOR_THREAD_ID
        )
        intake_activities = [
            item for item in detail["activities"]
            if item["kind"] == "devframe.intake.accepted"
        ]
        assert len(intake_activities) == 1
        assert intake_activities[0]["summary"] == payload["message"]

        event_files = list((runtime_dir / "conversation-intakes").rglob("ci-*.json"))
        assert len(event_files) == 1
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_conversation_intake_http_fails_closed_for_multiple_projects(tmp_path: Path):
    runtime_dir = tmp_path / "runtime"
    project_alpha = tmp_path / "project-alpha"
    project_beta = tmp_path / "project-beta"
    project_alpha.mkdir()
    project_beta.mkdir()
    server = build_dashboard_server(
        runtime_dir=runtime_dir,
        paper_project_dirs=[project_alpha, project_beta],
        port=0,
        refresh_seconds=0,
    )
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_address[1]}"

    try:
        status, body = _post_json_error(
            base_url,
            "/api/t3/conversation-intake",
            {
                "threadId": _GLOBAL_COORDINATOR_THREAD_ID,
                "projectId": "project-alpha",
                "clientRequestId": "request-multiple-projects",
                "message": "Implement the next verified milestone.",
                "environmentId": "devframe-local",
            },
        )
        assert status == 400
        assert body == {
            "accepted": False,
            "error": "global_project_binding_unavailable",
        }
        assert not (runtime_dir / "conversation-intakes").exists()
        assert not (runtime_dir / "conversation-proposals").exists()
        assert not (runtime_dir / "cluster-run-proposals").exists()
        assert not (runtime_dir / "cluster-runs").exists()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_conversation_intake_rejects_unknown_thread_and_environment(tmp_path: Path):
    server = build_dashboard_server(runtime_dir=tmp_path / "runtime", port=0, refresh_seconds=0)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_address[1]}"
    payload = {
        "threadId": "unknown-thread",
        "projectId": "demo",
        "clientRequestId": "request-unknown",
        "message": "Do not accept this.",
        "environmentId": "devframe-local",
    }
    try:
        status, body = _post_json_error(
            base_url,
            "/api/t3/conversation-intake",
            [],
        )
        assert status == 400
        assert body["error"] == "invalid_payload"

        status, body = _post_json_error(base_url, "/api/t3/conversation-intake", payload)
        assert status == 404
        assert body["error"] == "unknown_thread"

        payload["threadId"] = _GLOBAL_COORDINATOR_THREAD_ID
        payload["environmentId"] = "other-environment"
        status, body = _post_json_error(base_url, "/api/t3/conversation-intake", payload)
        assert status == 400
        assert body["error"] == "environment_id_missing_or_mismatch"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_concurrent_replay_creates_one_event(tmp_path: Path):
    runtime_dir = tmp_path / "runtime"
    project = tmp_path / "project-alpha"
    project.mkdir()

    def write_once(_: int) -> str:
        result = record_intake(
            runtime_dir,
            _GLOBAL_COORDINATOR_THREAD_ID,
            project.name,
            "concurrent-request",
            "Only one durable message.",
            environment_id="devframe-local",
            paper_project_dirs=[project],
        )
        return result["eventId"]

    with ThreadPoolExecutor(max_workers=8) as executor:
        event_ids = list(executor.map(write_once, range(32)))

    assert len(set(event_ids)) == 1
    assert len(get_thread_intakes(runtime_dir, _GLOBAL_COORDINATOR_THREAD_ID)) == 1


def test_exact_replay_is_idempotent_but_same_id_payload_drift_conflicts(tmp_path: Path):
    runtime_dir = tmp_path / "runtime"
    project_alpha = tmp_path / "project-alpha"
    project_beta = tmp_path / "project-beta"
    project_alpha.mkdir()
    project_beta.mkdir()
    request = {
        "runtime_dir": runtime_dir,
        "thread_id": _GLOBAL_COORDINATOR_THREAD_ID,
        "project_id": project_alpha.name,
        "client_request_id": "t3-message-001",
        "message": "汇报一下目前的项目进度情况",
        "environment_id": "devframe-local",
        "paper_project_dirs": [project_alpha],
    }

    first = record_intake(**request)
    replay = record_intake(**request)

    assert first["replayed"] is False
    assert replay["replayed"] is True
    assert replay["eventId"] == first["eventId"]
    assert replay["turnId"] == first["turnId"]
    assert replay["assistantMessageId"] == first["assistantMessageId"]
    with pytest.raises(IntakeError, match="intake_conflict"):
        record_intake(**{**request, "message": "Implement the next milestone."})
    with pytest.raises(IntakeError, match="intake_conflict"):
        record_intake(**{**request, "project_id": project_beta.name})


def test_progress_turn_persists_stable_user_and_relevant_assistant_messages(tmp_path: Path):
    runtime_dir = tmp_path / "runtime"
    project = tmp_path / "project-alpha"
    project.mkdir()
    plan = project / "PLAN.md"
    plan.write_text(
        "# Project execution root\n\n"
        "Current verdict: **M13B BACKEND READY FOR IMPLEMENTATION**\n\n"
        "## Next Action\n\n"
        "Implement the bounded native coordinator conversation slice.\n\n"
        "Do not include this second paragraph.\n",
        encoding="utf-8",
    )

    result = record_intake(
        runtime_dir,
        _GLOBAL_COORDINATOR_THREAD_ID,
        project.name,
        "t3-progress-message",
        "汇报一下目前的项目进度情况",
        environment_id="devframe-local",
        paper_project_dirs=[project],
    )

    [turn] = get_thread_intakes(runtime_dir, _GLOBAL_COORDINATOR_THREAD_ID)
    assert result["turnId"] == "t3-progress-message"
    assert result["status"] == "answered"
    assert turn["userMessage"] == {
        "id": "t3-progress-message",
        "role": "user",
        "text": "汇报一下目前的项目进度情况",
        "turnId": "t3-progress-message",
        "createdAt": turn["createdAt"],
        "updatedAt": turn["createdAt"],
    }
    assert turn["assistantMessage"]["id"] == result["assistantMessageId"]
    assert turn["assistantMessage"]["role"] == "assistant"
    assert turn["assistantMessage"]["turnId"] == "t3-progress-message"
    assert "project-alpha" in turn["assistantMessage"]["text"]
    assert "M13B BACKEND READY FOR IMPLEMENTATION" in turn["assistantMessage"]["text"]
    assert "Implement the bounded native coordinator conversation slice." in turn["assistantMessage"]["text"]
    assert "Do not include this second paragraph." not in turn["assistantMessage"]["text"]
    assert "未启动" in turn["assistantMessage"]["text"]
    assert str(project.resolve()) not in turn["assistantMessage"]["text"]
    assert "proposal" not in turn
    assert not (runtime_dir / "cluster-runs").exists()


def test_global_progress_turn_rejects_unknown_nonempty_project(tmp_path: Path):
    project = tmp_path / "project-alpha"
    project.mkdir()
    with pytest.raises(IntakeError, match="project_id_mismatch"):
        record_intake(
            tmp_path / "runtime",
            _GLOBAL_COORDINATOR_THREAD_ID,
            "not-a-registered-project",
            "t3-unknown-project-message",
            "汇报一下目前的项目进度情况",
            environment_id="devframe-local",
            paper_project_dirs=[project],
        )


def test_development_turn_persists_secret_free_semantic_proposal_without_run(tmp_path: Path):
    runtime_dir = tmp_path / "runtime"
    project = tmp_path / "project-alpha"
    project.mkdir()

    result = record_intake(
        runtime_dir,
        _GLOBAL_COORDINATOR_THREAD_ID,
        project.name,
        "t3-development-message",
        "Implement the next verified milestone.",
        environment_id="devframe-local",
        paper_project_dirs=[project],
    )

    assert result["status"] == "proposal_pending"
    assert result["proposalId"].startswith("ctp-")
    assert str(project.resolve()) not in json.dumps(result)
    proposal = get_conversation_proposal(runtime_dir, result["proposalId"])
    assert proposal["status"] == "pending"
    assert proposal["sourceTurnId"] == "t3-development-message"
    assert proposal["threadId"] == _GLOBAL_COORDINATOR_THREAD_ID
    assert proposal["target"] == "coordinator"
    assert proposal["goal"] == "Implement the next verified milestone."
    assert proposal["stableRunId"].startswith("g-")
    assert proposal["projectPath"] == str(project.resolve())
    assert "token" not in json.dumps(proposal).lower()
    [turn] = get_thread_intakes(runtime_dir, _GLOBAL_COORDINATOR_THREAD_ID)
    assistant_text = turn["assistantMessage"]["text"]
    assert all(
        marker not in assistant_text
        for marker in (chr(0xFFFD), "宸插", "鍑嗗", "鐨勯")
    )
    assert not (runtime_dir / "cluster-runs").exists()
    assert not (runtime_dir / "cluster-run-proposals").exists()


def test_semantic_proposal_reject_is_idempotent_and_wins_over_later_approve(tmp_path: Path):
    runtime_dir = tmp_path / "runtime"
    project = tmp_path / "project-alpha"
    project.mkdir()
    server = build_dashboard_server(
        runtime_dir=runtime_dir,
        paper_project_dirs=[project],
        port=0,
        refresh_seconds=0,
    )
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        malformed_status, malformed = _post_json_error(
            base_url,
            "/api/t3/approval-response",
            [],
        )
        assert malformed_status == 400
        assert malformed["error"] == "invalid_payload"

        _, intake = _post_json(
            base_url,
            "/api/t3/conversation-intake",
            {
                "threadId": _GLOBAL_COORDINATOR_THREAD_ID,
                "projectId": project.name,
                "clientRequestId": "t3-reject-message",
                "message": "Implement a bounded development change.",
                "environmentId": "devframe-local",
            },
        )
        decision = {
            "requestId": intake["proposalId"],
            "threadId": _GLOBAL_COORDINATOR_THREAD_ID,
            "decision": "reject",
        }

        status, rejected = _post_json(base_url, "/api/t3/approval-response", decision)
        replay_status, replay = _post_json(base_url, "/api/t3/approval-response", decision)
        conflict_status, conflict = _post_json_error(
            base_url,
            "/api/t3/approval-response",
            {**decision, "decision": "approve"},
        )

        assert status == replay_status == 200
        assert rejected == {
            "responded": True,
            "decision": "reject",
            "requestId": intake["proposalId"],
            "threadId": _GLOBAL_COORDINATOR_THREAD_ID,
            "executed": False,
            "status": "rejected",
            "replayed": False,
        }
        assert replay == {**rejected, "replayed": True}
        assert conflict_status == 409
        assert conflict["error"] == "approval_conflict"
        rejected_proposal = get_conversation_proposal(runtime_dir, intake["proposalId"])
        assert rejected_proposal["status"] == "rejected"
        assert [item["status"] for item in rejected_proposal["stateHistory"]] == [
            "pending",
            "rejected",
        ]
        assert not (runtime_dir / "cluster-runs").exists()
        assert not (runtime_dir / "cluster-run-proposals").exists()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_semantic_proposal_approve_starts_preallocated_run_once_and_replays(tmp_path: Path, monkeypatch):
    from control_plane import cluster_run as cluster_run_module

    runtime_dir = tmp_path / "runtime"
    project = tmp_path / "project-alpha"
    project.mkdir()
    physical_launches: list[str] = []
    monkeypatch.setattr(
        cluster_run_module,
        "_run_cluster_workflow",
        lambda _runtime, _project, _target, _goal, run_id, **_kwargs: physical_launches.append(run_id),
    )
    server = build_dashboard_server(
        runtime_dir=runtime_dir,
        paper_project_dirs=[project],
        port=0,
        refresh_seconds=0,
    )
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        _, intake = _post_json(
            base_url,
            "/api/t3/conversation-intake",
            {
                "threadId": _GLOBAL_COORDINATOR_THREAD_ID,
                "projectId": project.name,
                "clientRequestId": "t3-approve-message",
                "message": "Implement one bounded development change.",
                "environmentId": "devframe-local",
            },
        )
        proposal_before = get_conversation_proposal(runtime_dir, intake["proposalId"])
        decision = {
            "requestId": intake["proposalId"],
            "threadId": _GLOBAL_COORDINATOR_THREAD_ID,
            "decision": "approve",
        }

        status, started = _post_json(base_url, "/api/t3/approval-response", decision)
        replay_status, replay = _post_json(base_url, "/api/t3/approval-response", decision)

        assert status == 202
        assert replay_status == 200
        assert started == {
            "responded": True,
            "decision": "approve",
            "requestId": intake["proposalId"],
            "threadId": _GLOBAL_COORDINATOR_THREAD_ID,
            "executed": True,
            "status": "started",
            "runId": proposal_before["stableRunId"],
            "replayed": False,
        }
        assert replay == {**started, "replayed": True}
        assert "token" not in json.dumps(started).lower()
        proposal_after = get_conversation_proposal(runtime_dir, intake["proposalId"])
        assert proposal_after["status"] == "started"
        assert [item["status"] for item in proposal_after["stateHistory"]] == [
            "pending",
            "approval_claimed",
            "capability_issued",
            "starting",
            "started",
        ]
        record = cluster_run_module._load_run_record(runtime_dir, started["runId"])
        assert record["sourceProposalId"] == intake["proposalId"]
        assert record["sourceTurnId"] == "t3-approve-message"
        deadline = time.time() + 5
        while not physical_launches and time.time() < deadline:
            time.sleep(0.02)
        assert physical_launches == [proposal_before["stableRunId"]]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_http_approval_preserves_canonical_project_binding_across_replay(
    tmp_path: Path,
    monkeypatch,
):
    from control_plane import cluster_run as cluster_run_module

    runtime_dir = tmp_path / "runtime"
    project = tmp_path / "folder-name-differs"
    project.mkdir()
    (project / "PAPER_PROFILE.yaml").write_text(
        "paper_id: canonical-paper-id\n"
        "title: Canonical Paper\n",
        encoding="utf-8",
    )
    physical_launches: list[str] = []
    monkeypatch.setattr(
        cluster_run_module,
        "_run_cluster_workflow",
        lambda _runtime, _project, _target, _goal, run_id, **_kwargs: physical_launches.append(run_id),
    )
    server = build_dashboard_server(
        runtime_dir=runtime_dir,
        paper_project_dirs=[project],
        port=0,
        refresh_seconds=0,
    )
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_address[1]}"

    try:
        _, intake = _post_json(
            base_url,
            "/api/t3/conversation-intake",
            {
                "threadId": _GLOBAL_COORDINATOR_THREAD_ID,
                "projectId": "canonical-paper-id",
                "clientRequestId": "canonical-project-binding",
                "message": "Implement one bounded development change.",
                "environmentId": "devframe-local",
            },
        )
        proposal = get_conversation_proposal(runtime_dir, intake["proposalId"])
        assert proposal["projectId"] == "canonical-paper-id"
        assert proposal["projectPath"] == str(project.resolve())
        decision = {
            "requestId": intake["proposalId"],
            "threadId": _GLOBAL_COORDINATOR_THREAD_ID,
            "decision": "approve",
        }

        status, started = _post_json(base_url, "/api/t3/approval-response", decision)
        replay_status, replay = _post_json(
            base_url,
            "/api/t3/approval-response",
            decision,
        )

        assert status == 202
        assert replay_status == 200
        assert replay == {**started, "replayed": True}
        run = cluster_run_module._load_run_record(runtime_dir, started["runId"])
        assert run["projectId"] == "canonical-paper-id"
        assert run["projectPath"] == str(project.resolve())
        [capability_path] = list(
            (runtime_dir / "cluster-run-proposals").glob("crp-*.json")
        )
        capability = json.loads(capability_path.read_text(encoding="utf-8"))
        assert capability["projectId"] == "canonical-paper-id"
        assert capability["projectPath"] == str(project.resolve())
        deadline = time.time() + 5
        while not physical_launches and time.time() < deadline:
            time.sleep(0.02)
        assert physical_launches == [started["runId"]]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_semantic_proposal_path_drift_fails_before_capability_issue(tmp_path: Path, monkeypatch):
    from control_plane import cluster_run as cluster_run_module
    from control_plane import conversation_intake as intake_module

    runtime_dir = tmp_path / "runtime"
    project = tmp_path / "original" / "project-alpha"
    replacement = tmp_path / "replacement" / "project-alpha"
    project.mkdir(parents=True)
    replacement.mkdir(parents=True)
    intake = record_intake(
        runtime_dir,
        _GLOBAL_COORDINATOR_THREAD_ID,
        project.name,
        "t3-path-drift-message",
        "Implement one bounded development change.",
        environment_id="devframe-local",
        paper_project_dirs=[project],
    )
    proposal_path = (
        runtime_dir
        / "conversation-proposals"
        / f"{intake['proposalId']}.json"
    )
    proposal = json.loads(proposal_path.read_text(encoding="utf-8"))
    proposal["projectPath"] = str(replacement.resolve())
    proposal["fingerprint"] = intake_module._proposal_fingerprint(proposal)
    proposal_path.write_text(json.dumps(proposal), encoding="utf-8")
    [event_path] = list((runtime_dir / "conversation-intakes").rglob("ci-*.json"))
    event = json.loads(event_path.read_text(encoding="utf-8"))
    event["proposal"]["fingerprint"] = proposal["fingerprint"]
    event_path.write_text(json.dumps(event), encoding="utf-8")
    capability_calls: list[tuple] = []
    monkeypatch.setattr(
        cluster_run_module,
        "propose_cluster_run",
        lambda *args, **kwargs: capability_calls.append((args, kwargs)),
    )

    with pytest.raises(IntakeError, match="approval_conflict"):
        intake_module.resolve_conversation_proposal(
            runtime_dir,
            intake["proposalId"],
            _GLOBAL_COORDINATOR_THREAD_ID,
            "approve",
        )

    assert capability_calls == []
    assert not list((runtime_dir / "conversation-proposals").glob("*.decision.json"))
    assert not (runtime_dir / "cluster-run-proposals").exists()
    assert not (runtime_dir / "cluster-runs").exists()


def test_semantic_proposal_rejects_invalid_source_event_id_before_path_read(
    tmp_path: Path,
    monkeypatch,
):
    from control_plane import conversation_intake as intake_module

    runtime_dir = tmp_path / "runtime"
    intake = _record_development_intake(
        runtime_dir,
        tmp_path / "project-alpha",
        request_id="invalid-source-event-id",
    )
    proposal = get_conversation_proposal(runtime_dir, intake["proposalId"])
    proposal["sourceEventId"] = "../../outside-intake-journal"
    proposal["fingerprint"] = intake_module._proposal_fingerprint(proposal)
    monkeypatch.setattr(
        intake_module,
        "_read_event",
        lambda _path: pytest.fail("invalid source event id reached a filesystem read"),
    )

    with pytest.raises(IntakeError, match="approval_conflict"):
        intake_module._validate_semantic_proposal_binding(runtime_dir, proposal)


def test_approval_crash_before_capability_fails_closed_without_retry(
    tmp_path: Path,
    monkeypatch,
):
    from control_plane import cluster_run as cluster_run_module
    from control_plane import conversation_intake as intake_module

    runtime_dir = tmp_path / "runtime"
    intake = _record_development_intake(
        runtime_dir,
        tmp_path / "project-alpha",
        request_id="crash-before-capability",
    )

    def crash_before_capability(*_args, **_kwargs):
        raise SystemExit("simulated crash before capability issue")

    monkeypatch.setattr(
        cluster_run_module,
        "propose_cluster_run",
        crash_before_capability,
    )

    with pytest.raises(SystemExit, match="before capability"):
        intake_module.resolve_conversation_proposal(
            runtime_dir,
            intake["proposalId"],
            _GLOBAL_COORDINATOR_THREAD_ID,
            "approve",
        )

    interrupted = get_conversation_proposal(runtime_dir, intake["proposalId"])
    assert [item["status"] for item in interrupted["stateHistory"]] == [
        "pending",
        "approval_claimed",
    ]
    monkeypatch.setattr(cluster_run_module, "_pid_alive", lambda _pid: False)
    with pytest.raises(IntakeError, match="recovery_required"):
        intake_module.resolve_conversation_proposal(
            runtime_dir,
            intake["proposalId"],
            _GLOBAL_COORDINATOR_THREAD_ID,
            "approve",
        )

    recovered = get_conversation_proposal(runtime_dir, intake["proposalId"])
    assert recovered["status"] == "recovery_required"
    assert recovered["recoveryReason"] == "stale_approval_claimed"
    assert not (runtime_dir / "cluster-run-proposals").exists()
    assert not (runtime_dir / "cluster-runs").exists()


def test_malformed_server_capability_transitions_to_start_failed(
    tmp_path: Path,
    monkeypatch,
):
    from control_plane import cluster_run as cluster_run_module
    from control_plane import conversation_intake as intake_module

    runtime_dir = tmp_path / "runtime"
    intake = _record_development_intake(
        runtime_dir,
        tmp_path / "project-alpha",
        request_id="malformed-capability",
    )
    monkeypatch.setattr(
        cluster_run_module,
        "propose_cluster_run",
        lambda *_args, **_kwargs: None,
    )

    with pytest.raises(IntakeError, match="start_failed"):
        intake_module.resolve_conversation_proposal(
            runtime_dir,
            intake["proposalId"],
            _GLOBAL_COORDINATOR_THREAD_ID,
            "approve",
        )

    failed = get_conversation_proposal(runtime_dir, intake["proposalId"])
    assert failed["status"] == "start_failed"
    assert failed["failureCode"] == "capability_issue_failed"
    assert [item["status"] for item in failed["stateHistory"]] == [
        "pending",
        "approval_claimed",
        "start_failed",
    ]
    assert not (runtime_dir / "cluster-runs").exists()


def test_malformed_cluster_start_result_transitions_to_start_failed(
    tmp_path: Path,
    monkeypatch,
):
    from control_plane import cluster_run as cluster_run_module
    from control_plane import conversation_intake as intake_module

    runtime_dir = tmp_path / "runtime"
    intake = _record_development_intake(
        runtime_dir,
        tmp_path / "project-alpha",
        request_id="malformed-start-result",
    )
    proposal = get_conversation_proposal(runtime_dir, intake["proposalId"])
    monkeypatch.setattr(
        cluster_run_module,
        "propose_cluster_run",
        lambda *_args, **_kwargs: {
            "proposalId": "crp-test-capability",
            "confirmationToken": "server-local-token",
            "expiresAt": "2026-07-30T01:00:00Z",
            "stableRunId": proposal["stableRunId"],
        },
    )
    monkeypatch.setattr(
        cluster_run_module,
        "start_cluster_run",
        lambda *_args, **_kwargs: None,
    )

    with pytest.raises(IntakeError, match="start_failed"):
        intake_module.resolve_conversation_proposal(
            runtime_dir,
            intake["proposalId"],
            _GLOBAL_COORDINATOR_THREAD_ID,
            "approve",
        )

    failed = get_conversation_proposal(runtime_dir, intake["proposalId"])
    assert failed["status"] == "start_failed"
    assert failed["failureCode"] == "cluster_start_failed"
    assert [item["status"] for item in failed["stateHistory"]] == [
        "pending",
        "approval_claimed",
        "capability_issued",
        "starting",
        "start_failed",
    ]
    assert "server-local-token" not in json.dumps(failed)
    assert not (runtime_dir / "cluster-runs").exists()


def test_approval_crash_after_capability_before_consumption_fails_closed(
    tmp_path: Path,
    monkeypatch,
):
    from control_plane import cluster_run as cluster_run_module
    from control_plane import conversation_intake as intake_module

    runtime_dir = tmp_path / "runtime"
    intake = _record_development_intake(
        runtime_dir,
        tmp_path / "project-alpha",
        request_id="crash-after-capability",
    )
    original_transition = intake_module._transition_semantic_proposal

    def crash_before_starting(
        runtime,
        proposal,
        *,
        expected_statuses,
        status,
        **updates,
    ):
        if status == "starting":
            raise SystemExit("simulated crash after capability issue")
        return original_transition(
            runtime,
            proposal,
            expected_statuses=expected_statuses,
            status=status,
            **updates,
        )

    monkeypatch.setattr(
        intake_module,
        "_transition_semantic_proposal",
        crash_before_starting,
    )

    with pytest.raises(SystemExit, match="after capability"):
        intake_module.resolve_conversation_proposal(
            runtime_dir,
            intake["proposalId"],
            _GLOBAL_COORDINATOR_THREAD_ID,
            "approve",
        )

    interrupted = get_conversation_proposal(runtime_dir, intake["proposalId"])
    assert interrupted["status"] == "capability_issued"
    capability_files = list(
        (runtime_dir / "cluster-run-proposals").glob("crp-*.json")
    )
    assert len(capability_files) == 1
    capability = json.loads(capability_files[0].read_text(encoding="utf-8"))
    assert capability["status"] == "unused"
    monkeypatch.setattr(cluster_run_module, "_pid_alive", lambda _pid: False)

    with pytest.raises(IntakeError, match="recovery_required"):
        intake_module.resolve_conversation_proposal(
            runtime_dir,
            intake["proposalId"],
            _GLOBAL_COORDINATOR_THREAD_ID,
            "approve",
        )

    recovered = get_conversation_proposal(runtime_dir, intake["proposalId"])
    assert recovered["status"] == "recovery_required"
    assert recovered["recoveryReason"] == "stale_capability_issued"
    assert list((runtime_dir / "cluster-run-proposals").glob("crp-*.json")) == capability_files
    assert not list((runtime_dir / "cluster-run-proposals").glob("crp-*.used"))
    assert not (runtime_dir / "cluster-runs").exists()


def test_approval_crash_after_capability_consumption_before_run_record_fails_closed(
    tmp_path: Path,
    monkeypatch,
):
    from control_plane import cluster_run as cluster_run_module
    from control_plane import conversation_intake as intake_module

    runtime_dir = tmp_path / "runtime"
    intake = _record_development_intake(
        runtime_dir,
        tmp_path / "project-alpha",
        request_id="crash-after-capability-consumption",
    )
    physical_launches: list[str] = []
    monkeypatch.setattr(
        cluster_run_module,
        "_run_cluster_workflow",
        lambda _runtime, _project, _target, _goal, run_id, **_kwargs: (
            physical_launches.append(run_id)
        ),
    )

    def crash_before_run_record(*_args, **_kwargs):
        raise SystemExit("simulated crash before stable run record")

    monkeypatch.setattr(
        cluster_run_module,
        "_write_run_record",
        crash_before_run_record,
    )

    with pytest.raises(SystemExit, match="before stable run record"):
        intake_module.resolve_conversation_proposal(
            runtime_dir,
            intake["proposalId"],
            _GLOBAL_COORDINATOR_THREAD_ID,
            "approve",
        )

    interrupted = get_conversation_proposal(runtime_dir, intake["proposalId"])
    assert interrupted["status"] == "starting"
    [capability_file] = list(
        (runtime_dir / "cluster-run-proposals").glob("crp-*.json")
    )
    capability = json.loads(capability_file.read_text(encoding="utf-8"))
    assert capability["status"] == "consumed"
    assert capability_file.with_suffix(".used").is_file()
    assert physical_launches == []
    monkeypatch.setattr(cluster_run_module, "_pid_alive", lambda _pid: False)

    with pytest.raises(IntakeError, match="recovery_required"):
        intake_module.resolve_conversation_proposal(
            runtime_dir,
            intake["proposalId"],
            _GLOBAL_COORDINATOR_THREAD_ID,
            "approve",
        )

    recovered = get_conversation_proposal(runtime_dir, intake["proposalId"])
    assert recovered["status"] == "recovery_required"
    assert recovered["recoveryReason"] == "stale_starting"
    assert not (runtime_dir / "cluster-runs").exists()
    assert physical_launches == []


def test_approval_recovery_links_existing_stable_run_without_second_launch(
    tmp_path: Path,
    monkeypatch,
):
    from control_plane import cluster_run as cluster_run_module
    from control_plane import conversation_intake as intake_module

    runtime_dir = tmp_path / "runtime"
    intake = _record_development_intake(
        runtime_dir,
        tmp_path / "project-alpha",
        request_id="crash-before-source-linkage",
    )
    proposal_before = get_conversation_proposal(runtime_dir, intake["proposalId"])
    physical_launches: list[str] = []
    monkeypatch.setattr(
        cluster_run_module,
        "_run_cluster_workflow",
        lambda _runtime, _project, _target, _goal, run_id, **_kwargs: (
            physical_launches.append(run_id)
        ),
    )
    original_write = cluster_run_module._write_run_record
    write_calls = 0

    def write_unlinked_record_then_crash(runtime, record):
        nonlocal write_calls
        write_calls += 1
        if write_calls == 1:
            unlinked = {
                key: value
                for key, value in record.items()
                if key not in {"sourceProposalId", "sourceTurnId"}
            }
            original_write(runtime, unlinked)
            raise SystemExit("simulated crash before source linkage")
        original_write(runtime, record)

    monkeypatch.setattr(
        cluster_run_module,
        "_write_run_record",
        write_unlinked_record_then_crash,
    )

    with pytest.raises(SystemExit, match="before source linkage"):
        intake_module.resolve_conversation_proposal(
            runtime_dir,
            intake["proposalId"],
            _GLOBAL_COORDINATOR_THREAD_ID,
            "approve",
        )

    interrupted = get_conversation_proposal(runtime_dir, intake["proposalId"])
    assert interrupted["status"] == "starting"
    unlinked = cluster_run_module._load_run_record(
        runtime_dir,
        proposal_before["stableRunId"],
    )
    assert "sourceProposalId" not in unlinked
    assert "sourceTurnId" not in unlinked
    assert physical_launches == []

    replay = intake_module.resolve_conversation_proposal(
        runtime_dir,
        intake["proposalId"],
        _GLOBAL_COORDINATOR_THREAD_ID,
        "approve",
    )

    assert replay["replayed"] is True
    assert replay["runId"] == proposal_before["stableRunId"]
    linked = cluster_run_module._load_run_record(runtime_dir, replay["runId"])
    assert linked["sourceProposalId"] == intake["proposalId"]
    assert linked["sourceTurnId"] == "crash-before-source-linkage"
    assert get_conversation_proposal(runtime_dir, intake["proposalId"])["status"] == "started"
    assert len(list((runtime_dir / "cluster-runs").glob("g-*.json"))) == 1
    assert physical_launches == []


def test_approval_crash_after_thread_launch_replays_without_second_launch(
    tmp_path: Path,
    monkeypatch,
):
    from control_plane import cluster_run as cluster_run_module
    from control_plane import conversation_intake as intake_module

    runtime_dir = tmp_path / "runtime"
    intake = _record_development_intake(
        runtime_dir,
        tmp_path / "project-alpha",
        request_id="crash-after-thread-launch",
    )
    proposal_before = get_conversation_proposal(runtime_dir, intake["proposalId"])
    physical_launches: list[str] = []
    monkeypatch.setattr(
        cluster_run_module,
        "_run_cluster_workflow",
        lambda _runtime, _project, _target, _goal, run_id, **_kwargs: (
            physical_launches.append(run_id)
        ),
    )
    original_transition = intake_module._transition_semantic_proposal
    crashed = False

    def crash_after_first_launch(
        runtime,
        proposal,
        *,
        expected_statuses,
        status,
        **updates,
    ):
        nonlocal crashed
        if status == "started" and not crashed:
            crashed = True
            raise SystemExit("simulated crash after thread launch")
        return original_transition(
            runtime,
            proposal,
            expected_statuses=expected_statuses,
            status=status,
            **updates,
        )

    monkeypatch.setattr(
        intake_module,
        "_transition_semantic_proposal",
        crash_after_first_launch,
    )

    with pytest.raises(SystemExit, match="after thread launch"):
        intake_module.resolve_conversation_proposal(
            runtime_dir,
            intake["proposalId"],
            _GLOBAL_COORDINATOR_THREAD_ID,
            "approve",
        )

    deadline = time.time() + 5
    while not physical_launches and time.time() < deadline:
        time.sleep(0.02)
    assert physical_launches == [proposal_before["stableRunId"]]
    assert get_conversation_proposal(runtime_dir, intake["proposalId"])["status"] == "starting"

    replay = intake_module.resolve_conversation_proposal(
        runtime_dir,
        intake["proposalId"],
        _GLOBAL_COORDINATOR_THREAD_ID,
        "approve",
    )

    assert replay["replayed"] is True
    assert replay["runId"] == proposal_before["stableRunId"]
    assert get_conversation_proposal(runtime_dir, intake["proposalId"])["status"] == "started"
    assert physical_launches == [proposal_before["stableRunId"]]


def test_concurrent_approve_replays_one_claim_and_launches_once(
    tmp_path: Path,
    monkeypatch,
):
    from control_plane import cluster_run as cluster_run_module
    from control_plane import conversation_intake as intake_module

    runtime_dir = tmp_path / "runtime"
    intake = _record_development_intake(
        runtime_dir,
        tmp_path / "project-alpha",
        request_id="concurrent-approve",
    )
    physical_launches: list[str] = []
    monkeypatch.setattr(
        cluster_run_module,
        "_run_cluster_workflow",
        lambda _runtime, _project, _target, _goal, run_id, **_kwargs: (
            physical_launches.append(run_id)
        ),
    )
    barrier = Barrier(2)

    def approve_once(_: int) -> tuple[str, object]:
        barrier.wait()
        try:
            return (
                "ok",
                intake_module.resolve_conversation_proposal(
                    runtime_dir,
                    intake["proposalId"],
                    _GLOBAL_COORDINATOR_THREAD_ID,
                    "approve",
                ),
            )
        except IntakeError as exc:
            return "error", str(exc)

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(executor.map(approve_once, range(2)))

    successes = [value for kind, value in outcomes if kind == "ok"]
    failures = [value for kind, value in outcomes if kind == "error"]
    assert successes
    assert all(result["runId"] == successes[0]["runId"] for result in successes)
    assert failures in ([], ["approval_in_progress"])
    deadline = time.time() + 5
    while not physical_launches and time.time() < deadline:
        time.sleep(0.02)
    assert physical_launches == [successes[0]["runId"]]
    assert len(list((runtime_dir / "cluster-runs").glob("g-*.json"))) == 1
    assert len(
        list((runtime_dir / "conversation-proposals").glob("ctp-*.decision.json"))
    ) == 1


def test_concurrent_approve_and_reject_have_one_decision_winner(
    tmp_path: Path,
    monkeypatch,
):
    from control_plane import cluster_run as cluster_run_module
    from control_plane import conversation_intake as intake_module

    runtime_dir = tmp_path / "runtime"
    intake = _record_development_intake(
        runtime_dir,
        tmp_path / "project-alpha",
        request_id="concurrent-approve-reject",
    )
    physical_launches: list[str] = []
    monkeypatch.setattr(
        cluster_run_module,
        "_run_cluster_workflow",
        lambda _runtime, _project, _target, _goal, run_id, **_kwargs: (
            physical_launches.append(run_id)
        ),
    )
    barrier = Barrier(2)

    def decide(decision: str) -> tuple[str, object]:
        barrier.wait()
        try:
            return (
                "ok",
                intake_module.resolve_conversation_proposal(
                    runtime_dir,
                    intake["proposalId"],
                    _GLOBAL_COORDINATOR_THREAD_ID,
                    decision,
                ),
            )
        except IntakeError as exc:
            return "error", str(exc)

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(executor.map(decide, ("approve", "reject")))

    successes = [value for kind, value in outcomes if kind == "ok"]
    failures = [value for kind, value in outcomes if kind == "error"]
    assert len(successes) == 1
    assert failures == ["approval_conflict"]
    winner = successes[0]
    deadline = time.time() + 5
    while winner["decision"] == "approve" and not physical_launches and time.time() < deadline:
        time.sleep(0.02)
    assert len(physical_launches) <= 1
    assert len(
        list((runtime_dir / "conversation-proposals").glob("ctp-*.decision.json"))
    ) == 1
    decision_claim = json.loads(
        next(
            (runtime_dir / "conversation-proposals").glob(
                "ctp-*.decision.json"
            )
        ).read_text(encoding="utf-8")
    )
    assert decision_claim["decision"] == winner["decision"]
    if winner["decision"] == "approve":
        assert physical_launches == [winner["runId"]]
        assert len(list((runtime_dir / "cluster-runs").glob("g-*.json"))) == 1
    else:
        assert physical_launches == []
        assert not (runtime_dir / "cluster-runs").exists()


def test_goal_conversation_enforces_project_binding_and_projects(tmp_path: Path):
    runtime_dir = tmp_path / "runtime"
    _write_run_record(runtime_dir, {
        "runId": "g-project-goal",
        "target": "coordinator",
        "goal": "Deliver the project milestone",
        "projectId": "project-alpha",
        "projectPath": str(tmp_path / "project-alpha"),
        "status": "completed",
        "summary": "Ready for the next message.",
        "startedAt": "2026-07-17T00:00:00Z",
        "finishedAt": "2026-07-17T00:00:01Z",
    })
    server = build_dashboard_server(runtime_dir=runtime_dir, port=0, refresh_seconds=0)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_address[1]}"
    payload = {
        "threadId": "g-project-goal",
        "projectId": "wrong-project",
        "clientRequestId": "goal-request-001",
        "message": "Continue this goal.",
        "environmentId": "devframe-local",
    }
    try:
        status, body = _post_json_error(base_url, "/api/t3/conversation-intake", payload)
        assert status == 400
        assert body["error"] == "project_id_mismatch"

        payload["projectId"] = "project-alpha"
        status, accepted = _post_json(base_url, "/api/t3/conversation-intake", payload)
        assert status == 202
        assert accepted["projectId"] == "project-alpha"

        shell = _get_json(base_url, "/t3-shell.json")
        detail = next(item for item in shell["t3"]["threadDetails"] if item["id"] == "g-project-goal")
        intake = next(item for item in detail["activities"] if item["kind"] == "devframe.intake.accepted")
        assert intake["summary"] == "Continue this goal."
        assert intake["payload"]["projectId"] == "project-alpha"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_visual_goal_session_resolves_by_public_session_id(tmp_path: Path, monkeypatch):
    from control_plane import visual_state

    monkeypatch.setattr(
        visual_state,
        "build_visual_control_plane_state",
        lambda *_args, **_kwargs: {
            "sessions": [{
                "session_id": "public-session-id",
                "run_id": "internal-run-id",
                "task_spec_id": "",
                "project_id": "project-beta",
            }]
        },
    )

    result = record_intake(
        tmp_path / "runtime",
        "public-session-id",
        "project-beta",
        "session-request-001",
        "Continue the visible goal session.",
        environment_id="devframe-local",
    )

    assert result["accepted"] is True
    assert result["threadId"] == "public-session-id"
    assert get_thread_intakes(tmp_path / "runtime", "internal-run-id") == []
