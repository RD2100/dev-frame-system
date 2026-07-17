from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Thread
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from control_plane.conversation_intake import get_thread_intakes, record_intake
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


def test_conversation_intake_http_persists_and_projects_after_refresh(tmp_path: Path):
    runtime_dir = tmp_path / "runtime"
    server = build_dashboard_server(runtime_dir=runtime_dir, port=0, refresh_seconds=0)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_address[1]}"
    payload = {
        "threadId": _GLOBAL_COORDINATOR_THREAD_ID,
        "projectId": "",
        "clientRequestId": "request-001",
        "message": "Continue with the next verified product milestone.",
        "environmentId": "devframe-local",
    }

    try:
        status, accepted = _post_json(base_url, "/api/t3/conversation-intake", payload)
        assert status == 202
        assert accepted["accepted"] is True

        replay_payload = {**payload, "message": "This replay must not replace the original."}
        replay_status, replay = _post_json(base_url, "/api/t3/conversation-intake", replay_payload)
        assert replay_status == 202
        assert replay["eventId"] == accepted["eventId"]

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

    def write_once(_: int) -> str:
        result = record_intake(
            runtime_dir,
            _GLOBAL_COORDINATOR_THREAD_ID,
            "",
            "concurrent-request",
            "Only one durable message.",
            environment_id="devframe-local",
        )
        return result["eventId"]

    with ThreadPoolExecutor(max_workers=8) as executor:
        event_ids = list(executor.map(write_once, range(32)))

    assert len(set(event_ids)) == 1
    assert len(get_thread_intakes(runtime_dir, _GLOBAL_COORDINATOR_THREAD_ID)) == 1


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
