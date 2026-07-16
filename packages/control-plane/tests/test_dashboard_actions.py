import json
import time
from pathlib import Path
from threading import Thread
from typing import Any
from urllib.parse import quote
from urllib.request import Request, urlopen
from urllib.error import HTTPError

import control_plane.dashboard as dashboard_module
from control_plane.dashboard import build_dashboard_server


def _read_record_with_retry(record_path: Path, max_attempts: int = 10) -> dict[str, Any]:
    for attempt in range(max_attempts):
        try:
            return json.loads(record_path.read_text("utf-8"))
        except PermissionError:
            if attempt < max_attempts - 1:
                time.sleep(0.001 * (attempt + 1))
    return json.loads(record_path.read_text("utf-8"))


def _wait_for_record_completion(record_path: Path, timeout: float = 5.0, interval: float = 0.05) -> dict[str, Any]:
    deadline = time.time() + timeout
    while time.time() < deadline:
        record = _read_record_with_retry(record_path)
        if record.get("status") != "started":
            return record
        time.sleep(interval)
    return _read_record_with_retry(record_path)


def _write_go_run(runtime_dir, go_run_id):
    go_run_dir = runtime_dir / "go-runs" / go_run_id
    go_run_dir.mkdir(parents=True, exist_ok=True)
    (go_run_dir / "go-run.json").write_text(json.dumps({
        "go_run_id": go_run_id,
        "project_id": "project",
        "project_root": str(runtime_dir.parent / "project"),
        "requirement": "Test action execution persistence.",
        "runtime_dir": str(runtime_dir),
        "status": "queued",
        "execute": False,
        "agents": [{
            "agent_id": "coding-agent-1",
            "shard_index": 1,
            "shard_count": 1,
            "targets": [],
            "target_bytes": 0,
            "packet_dir": str(runtime_dir / "rdgoal-outbox" / "project" / "run-1"),
            "task_spec_path": str(runtime_dir / "rdgoal-outbox" / "project" / "run-1" / "TASKSPEC.json"),
            "worker_command": ["opencode", "run", "do work"],
            "status": "queued",
        }],
    }, indent=2, ensure_ascii=True), encoding="utf-8")


def _write_paper_project(root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / "PAPER_PROFILE.yaml").write_text(
        "\n".join([
            "paper_id: demo-paper",
            "title: Demo Paper",
            "current_stage: drafting",
        ]),
        encoding="utf-8",
    )
    (root / "PAPER_STATE.yaml").write_text(
        "\n".join([
            "paper_id: demo-paper",
            "current_stage: drafting",
            "status: initialized",
        ]),
        encoding="utf-8",
    )
    (root / "PAPER_LEDGER.md").write_text("# Paper Ledger\n", encoding="utf-8")
    paper_task = root / "paper_task"
    paper_task.mkdir()
    (paper_task / "PAPER_TASK_INPUT.yaml").write_text("task_type: cssci_review\n", encoding="utf-8")
    (paper_task / "PRIVACY_ATTESTATION.yaml").write_text(
        "contains_real_paper_full_text: false\n",
        encoding="utf-8",
    )
    return root


class _FakeProcess:
    pid = 99999

    def __init__(self, returncode=0):
        self.returncode = returncode

    def wait(self, timeout=None):
        return self.returncode


def _fake_popen(*args, **kwargs):
    return _FakeProcess()


def test_session_detail_endpoint_returns_public_projection_and_hides_runtime_refs(tmp_path, monkeypatch):
    runtime_dir = tmp_path / "runtime"
    state = {
        "sessions": [{
            "session_id": "review-session-1",
            "provider": "chatgpt",
            "binding_id": "web-ai",
            "agent_id": "reviewer-1",
            "agent_role": "reviewer",
            "project_id": "demo-project",
            "run_id": "run-1",
            "task_spec_id": "D:/private/TASKSPEC.json",
            "task_spec_path": "D:/private/TASKSPEC.json",
            "report_path": "D:/private/ExecutionReport.md",
            "status": "completed",
            "messages": [{"message_id": "m1", "role": "agent", "content_summary": "Reviewed."}],
            "tool_calls": [{"tool_call_id": "t1", "name": "test", "status": "completed"}],
            "changed_files": ["src/demo.py"],
            "diff_summary": "1 file changed",
            "evidence_refs": ["D:/private/evidence/receipt.md"],
            "cost": {"amount": 0, "currency": "USD"},
            "tokens": {"input": 1, "output": 2, "total": 3},
            "gates": ["review-gate"],
            "actions": ["Review result"],
            "native_refs": {"runtime": "web-ai-import", "secret": "must-not-leak"},
        }],
    }
    monkeypatch.setattr(dashboard_module, "build_visual_control_plane_state", lambda *a, **kw: state)

    server = build_dashboard_server(runtime_dir=runtime_dir, port=0, refresh_seconds=0)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        with urlopen(f"{base_url}/sessions/review-session-1.json", timeout=5) as response:
            payload = json.loads(response.read().decode("utf-8"))

        assert response.status == 200
        assert payload["session_id"] == "review-session-1"
        assert payload["task_spec_id"] == "TASKSPEC.json"
        assert payload["message_count"] == 1
        assert payload["tool_call_count"] == 1
        assert "task_spec_path" not in payload
        assert "report_path" not in payload
        assert "evidence_refs" not in payload
        assert "native_refs" not in payload
        assert "secret" not in json.dumps(payload)

        try:
            with urlopen(f"{base_url}/sessions/missing-session.json", timeout=5):
                raise AssertionError("missing session unexpectedly returned a response")
        except HTTPError as error:
            assert error.code == 404
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_session_stream_links_to_matching_read_only_detail(tmp_path, monkeypatch):
    state = {
        "projects": [],
        "provider_bindings": [],
        "agents": [],
        "sessions": [{
            "session_id": "review-session-1",
            "provider": "chatgpt",
            "agent_role": "reviewer",
            "status": "completed",
        }, {
            "session_id": "",
            "provider": "unknown",
            "agent_role": "custom",
            "status": "unknown",
        }],
        "runs": [],
        "gates": [],
        "decisions": [],
        "next_actions": [],
        "team": {},
        "safety": {
            "raw_transcripts_persisted": False,
            "remote_execution_default": False,
            "human_gate_required_for": ["credential_access"],
        },
        "skills": [],
    }
    monkeypatch.setattr(dashboard_module, "build_visual_control_plane_state", lambda *a, **kw: state)

    server = build_dashboard_server(runtime_dir=tmp_path / "runtime", port=0, refresh_seconds=0)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        with urlopen(base_url, timeout=5) as response:
            html = response.read().decode("utf-8")

        assert response.status == 200
        assert 'href="/sessions/review-session-1.json"' in html
        assert 'href="/sessions/.json"' not in html
        assert 'action="/sessions/review-session-1.json"' not in html
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_execute_action_persists_action_run_record(tmp_path, monkeypatch):
    runtime_dir = tmp_path / "runtime"
    go_run_id = "go-test"
    _write_go_run(runtime_dir, go_run_id)
    action_id = f"{go_run_id}-execute-action"

    monkeypatch.setattr(dashboard_module.subprocess, "Popen", _fake_popen)

    server = build_dashboard_server(runtime_dir=runtime_dir, port=0, refresh_seconds=0)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_address[1]}"

    try:
        request = Request(
            f"{base_url}/actions/execute?action_id={action_id}",
            data=b"confirm=execute",
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "Origin": base_url,
            },
            method="POST",
        )
        with urlopen(request, timeout=5) as response:
            payload = json.loads(response.read().decode("utf-8"))

        assert response.status == 202
        assert payload["started"] is True
        assert payload["action_id"] == action_id
        assert payload["action_run_id"]
        assert payload["go_run_id"] == go_run_id
        assert payload["kind"] == "go_run_execute"
        assert payload["pid"] == 99999
        assert payload["command"]
        assert payload["stdout_log"]
        assert payload["stderr_log"]
        assert "record_path" in payload

        record_path = Path(payload["record_path"])
        assert record_path.exists()

        record = _wait_for_record_completion(record_path)

        assert record["action_id"] == action_id
        assert record["action_run_id"] == payload["action_run_id"]
        assert record["status"] == "completed"
        assert record["exit_code"] == 0
        assert "completed_at" in record
        assert record["pid"] == 99999
        assert record["go_run_id"] == go_run_id
        assert record["kind"] == "go_run_execute"
        assert record["command"] == payload["command"]
        assert record["stdout_log"]
        assert record["stderr_log"]
        assert "created_at" in record

        assert Path(payload["stdout_log"]).exists()
        assert Path(payload["stderr_log"]).exists()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_approval_response_approve_persists_action_run_record(tmp_path, monkeypatch):
    runtime_dir = tmp_path / "runtime"
    go_run_id = "go-approval"
    _write_go_run(runtime_dir, go_run_id)
    action_id = f"{go_run_id}-execute-action"

    def fake_resolve_action_id(_runtime_dir, _paper_dirs, _request_id):
        return action_id

    monkeypatch.setattr(dashboard_module, "_resolve_approval_action_id", fake_resolve_action_id)
    monkeypatch.setattr(dashboard_module.subprocess, "Popen", _fake_popen)

    server = build_dashboard_server(runtime_dir=runtime_dir, port=0, refresh_seconds=0)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_address[1]}"

    try:
        body = json.dumps({
            "requestId": "req-1",
            "threadId": "thread-1",
            "decision": "approve",
        })
        request = Request(
            f"{base_url}/api/t3/approval-response",
            data=body.encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Origin": base_url,
            },
            method="POST",
        )
        with urlopen(request, timeout=5) as response:
            payload = json.loads(response.read().decode("utf-8"))

        assert response.status == 202
        assert payload["started"] is True
        assert payload["responded"] is True
        assert payload["decision"] == "approve"
        assert payload["requestId"] == "req-1"
        assert payload["action_id"] == action_id
        assert payload["go_run_id"] == go_run_id
        assert "record_path" in payload
        assert payload["action_run_id"]

        record_path = Path(payload["record_path"])
        assert record_path.exists()

        record = _wait_for_record_completion(record_path)

        assert record["action_id"] == action_id
        assert record["status"] == "completed"
        assert record["exit_code"] == 0
        assert "completed_at" in record
        assert record["go_run_id"] == go_run_id
        assert record["kind"] == "go_run_execute"
        assert record["pid"] == 99999
        assert "created_at" in record
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_approval_response_reject_does_not_start_execution(tmp_path, monkeypatch):
    runtime_dir = tmp_path / "runtime"
    go_run_id = "go-reject"
    _write_go_run(runtime_dir, go_run_id)
    action_id = f"{go_run_id}-execute-action"

    def fake_resolve_action_id(_runtime_dir, _paper_dirs, _request_id):
        return action_id

    monkeypatch.setattr(dashboard_module, "_resolve_approval_action_id", fake_resolve_action_id)

    server = build_dashboard_server(runtime_dir=runtime_dir, port=0, refresh_seconds=0)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_address[1]}"

    try:
        body = json.dumps({
            "requestId": "req-1",
            "threadId": "thread-1",
            "decision": "reject",
        })
        request = Request(
            f"{base_url}/api/t3/approval-response",
            data=body.encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Origin": base_url,
            },
            method="POST",
        )
        with urlopen(request, timeout=5) as response:
            payload = json.loads(response.read().decode("utf-8"))

        assert response.status == 200
        assert payload["responded"] is True
        assert payload["decision"] == "reject"
        assert payload["executed"] is False

        action_runs_dir = runtime_dir / "action-runs" / action_id
        assert not action_runs_dir.exists()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_execute_action_failed_lifecycle(tmp_path, monkeypatch):
    runtime_dir = tmp_path / "runtime"
    go_run_id = "go-failed"
    _write_go_run(runtime_dir, go_run_id)
    action_id = f"{go_run_id}-execute-action"

    def _fake_popen_failed(*args, **kwargs):
        return _FakeProcess(returncode=1)

    monkeypatch.setattr(dashboard_module.subprocess, "Popen", _fake_popen_failed)

    server = build_dashboard_server(runtime_dir=runtime_dir, port=0, refresh_seconds=0)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_address[1]}"

    try:
        request = Request(
            f"{base_url}/actions/execute?action_id={action_id}",
            data=b"confirm=execute",
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "Origin": base_url,
            },
            method="POST",
        )
        with urlopen(request, timeout=5) as response:
            payload = json.loads(response.read().decode("utf-8"))

        assert response.status == 202
        assert payload["started"] is True
        assert payload["action_id"] == action_id
        assert "record_path" in payload

        record_path = Path(payload["record_path"])
        assert record_path.exists()

        record = _wait_for_record_completion(record_path)

        assert record["action_id"] == action_id
        assert record["status"] == "failed"
        assert record["exit_code"] == 1
        assert "completed_at" in record
        assert record["go_run_id"] == go_run_id
        assert record["kind"] == "go_run_execute"
        assert record["pid"] == 99999
        assert "created_at" in record
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_duplicate_execute_action_returns_existing_run(tmp_path, monkeypatch):
    runtime_dir = tmp_path / "runtime"
    go_run_id = "go-duplicate-execute"
    _write_go_run(runtime_dir, go_run_id)
    action_id = f"{go_run_id}-execute-action"

    monkeypatch.setattr(dashboard_module.subprocess, "Popen", _fake_popen)

    server = build_dashboard_server(runtime_dir=runtime_dir, port=0, refresh_seconds=0)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_address[1]}"

    try:
        request = Request(
            f"{base_url}/actions/execute?action_id={action_id}",
            data=b"confirm=execute",
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "Origin": base_url,
            },
            method="POST",
        )
        with urlopen(request, timeout=5) as response:
            first_payload = json.loads(response.read().decode("utf-8"))

        assert response.status == 202
        assert first_payload["started"] is True
        first_run_id = first_payload["action_run_id"]

        record_path = Path(first_payload["record_path"])
        record = _wait_for_record_completion(record_path)

        request = Request(
            f"{base_url}/actions/execute?action_id={action_id}",
            data=b"confirm=execute",
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "Origin": base_url,
            },
            method="POST",
        )
        with urlopen(request, timeout=5) as response:
            second_payload = json.loads(response.read().decode("utf-8"))

        assert response.status == 202
        assert second_payload["started"] is False
        assert second_payload["reused"] is True
        assert second_payload["action_run_id"] == first_run_id
        assert second_payload["previous_status"] == "completed"
        assert second_payload["action_id"] == action_id
        assert second_payload["go_run_id"] == go_run_id
        second_record_path = Path(second_payload["record_path"])
        assert second_record_path.exists()
        assert second_record_path == record_path
        assert second_payload["record_path"] == first_payload["record_path"]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_paper_action_requires_confirm_before_execution(tmp_path):
    runtime_dir = tmp_path / "runtime"
    paper_root = _write_paper_project(tmp_path / "paper-project")
    action_id = "demo-paper-paper-review-command-action"

    server = build_dashboard_server(
        runtime_dir=runtime_dir,
        paper_project_dirs=[paper_root],
        port=0,
        refresh_seconds=0,
    )
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_address[1]}"

    try:
        request = Request(
            f"{base_url}/actions/execute?action_id={action_id}",
            data=b"",
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "Origin": base_url,
            },
            method="POST",
        )
        try:
            with urlopen(request, timeout=5):
                pass
            raise AssertionError("expected 409 Conflict")
        except HTTPError as error:
            assert error.code == 409
            payload = json.loads(error.read().decode("utf-8"))

        assert payload["error"] == "human_required"
        assert payload["action_id"] == action_id
        assert "confirm=execute" in payload["confirm"]
        assert "devframe run --pipeline" in payload["command"]
        assert "rdpaper" in payload["context"]
        assert not (runtime_dir / "action-runs").exists()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_paper_action_executes_controlled_local_command(tmp_path, monkeypatch):
    runtime_dir = tmp_path / "runtime"
    paper_root = _write_paper_project(tmp_path / "paper-project")
    action_id = "demo-paper-paper-review-command-action"
    popen_calls = []

    def fake_popen(*args, **kwargs):
        popen_calls.append((args, kwargs))
        return _FakeProcess()

    monkeypatch.setattr(dashboard_module.subprocess, "Popen", fake_popen)

    server = build_dashboard_server(
        runtime_dir=runtime_dir,
        paper_project_dirs=[paper_root],
        port=0,
        refresh_seconds=0,
    )
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_address[1]}"

    try:
        request = Request(
            f"{base_url}/actions/execute?action_id={action_id}",
            data=b"confirm=execute",
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "Origin": base_url,
            },
            method="POST",
        )
        with urlopen(request, timeout=5) as response:
            payload = json.loads(response.read().decode("utf-8"))

        assert response.status == 202
        assert payload["started"] is True
        assert payload["kind"] == "paper_run_command"
        assert payload["run_id"] == "demo-paper-paper-review"
        assert payload["go_run_id"] == "demo-paper-paper-review"
        assert "devframe run --pipeline" in payload["command"]

        assert len(popen_calls) == 1
        argv = popen_calls[0][0][0]
        assert argv[:4] == [argv[0], "-m", "control_plane.cli", "run"]
        assert "--pipeline" in argv
        assert "--execute" in argv
        assert argv[-2:] == ["--project", str(paper_root.resolve())]
        assert popen_calls[0][1]["stdin"] == dashboard_module.subprocess.DEVNULL

        record_path = Path(payload["record_path"])
        record = _wait_for_record_completion(record_path)
        assert record["status"] == "completed"
        assert record["kind"] == "paper_run_command"
        assert record["run_id"] == "demo-paper-paper-review"
        assert record["exit_code"] == 0
        assert Path(record["stdout_log"]).exists()
        assert Path(record["stderr_log"]).exists()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_duplicate_approval_response_returns_existing_run(tmp_path, monkeypatch):
    runtime_dir = tmp_path / "runtime"
    go_run_id = "go-duplicate-approval"
    _write_go_run(runtime_dir, go_run_id)
    action_id = f"{go_run_id}-execute-action"

    def fake_resolve_action_id(_runtime_dir, _paper_dirs, _request_id):
        return action_id

    monkeypatch.setattr(dashboard_module, "_resolve_approval_action_id", fake_resolve_action_id)
    monkeypatch.setattr(dashboard_module.subprocess, "Popen", _fake_popen)

    server = build_dashboard_server(runtime_dir=runtime_dir, port=0, refresh_seconds=0)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_address[1]}"

    try:
        body = json.dumps({
            "requestId": "req-duplicate",
            "threadId": "thread-duplicate",
            "decision": "approve",
        })
        request = Request(
            f"{base_url}/api/t3/approval-response",
            data=body.encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Origin": base_url,
            },
            method="POST",
        )
        with urlopen(request, timeout=5) as response:
            first_payload = json.loads(response.read().decode("utf-8"))

        assert response.status == 202
        assert first_payload["started"] is True
        first_run_id = first_payload["action_run_id"]

        record_path = Path(first_payload["record_path"])
        record = _wait_for_record_completion(record_path)

        body = json.dumps({
            "requestId": "req-duplicate",
            "threadId": "thread-duplicate",
            "decision": "approve",
        })
        request = Request(
            f"{base_url}/api/t3/approval-response",
            data=body.encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Origin": base_url,
            },
            method="POST",
        )
        with urlopen(request, timeout=5) as response:
            second_payload = json.loads(response.read().decode("utf-8"))

        assert response.status == 202
        assert second_payload["started"] is False
        assert second_payload["reused"] is True
        assert second_payload["action_run_id"] == first_run_id
        assert second_payload["previous_status"] == "completed"
        assert second_payload["responded"] is True
        assert second_payload["decision"] == "approve"
        assert second_payload["requestId"] == "req-duplicate"
        second_record_path = Path(second_payload["record_path"])
        assert second_record_path.exists()
        assert second_record_path == record_path
        assert second_payload["record_path"] == first_payload["record_path"]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_atomic_json_write_used_by_lifecycle(tmp_path, monkeypatch):
    import threading as _threading

    runtime_dir = tmp_path / "runtime"
    go_run_id = "go-atomic-lifecycle"
    _write_go_run(runtime_dir, go_run_id)
    action_id = f"{go_run_id}-execute-action"

    atomic_calls = []
    original = dashboard_module._atomic_json_write

    def tracked_atomic(path, data):
        atomic_calls.append(str(path))
        original(path, data)

    monkeypatch.setattr(dashboard_module, "_atomic_json_write", tracked_atomic)

    update_ready = _threading.Event()
    update_done = _threading.Event()

    class DelayingProcess:
        pid = 66666

        def wait(self, timeout=None):
            update_ready.set()
            update_done.wait(timeout=10)
            return 0

    monkeypatch.setattr(dashboard_module.subprocess, "Popen",
                        lambda *args, **kwargs: DelayingProcess())

    server = build_dashboard_server(runtime_dir=runtime_dir, port=0, refresh_seconds=0)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_address[1]}"

    try:
        request = Request(
            f"{base_url}/actions/execute?action_id={action_id}",
            data=b"confirm=execute",
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "Origin": base_url,
            },
            method="POST",
        )
        with urlopen(request, timeout=5) as response:
            payload = json.loads(response.read().decode("utf-8"))

        assert payload["started"] is True
        record_path = Path(payload["record_path"])
        assert record_path.exists()
        assert len(atomic_calls) >= 1  # initial write used atomic writer

        assert update_ready.wait(timeout=5), "Lifecycle thread did not start update"

        for _ in range(200):
            try:
                data = _read_record_with_retry(record_path)
                assert isinstance(data, dict)
                assert data["status"] == "started"
            except json.JSONDecodeError:
                update_done.set()
                raise AssertionError("Reader hit JSONDecodeError during lifecycle update")
            time.sleep(0.01)

        update_done.set()

        data = _wait_for_record_completion(record_path)

        assert data["status"] == "completed"
        assert data["exit_code"] == 0
        assert "completed_at" in data
        assert len(atomic_calls) >= 2  # lifecycle update also used atomic writer
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_evidence_open_serves_text_file(tmp_path):
    runtime_dir = tmp_path / "runtime"
    runtime_dir.mkdir(parents=True, exist_ok=True)
    evidence_file = runtime_dir / "ExecutionReport.md"
    evidence_file.write_text("# Report\nHello world.", encoding="utf-8")

    server = build_dashboard_server(runtime_dir=runtime_dir, port=0, refresh_seconds=0)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_address[1]}"

    try:
        with urlopen(f"{base_url}/evidence/open?ref=ExecutionReport.md", timeout=5) as response:
            html = response.read().decode("utf-8")
        assert response.status == 200
        assert "<h1>ExecutionReport.md</h1>" in html
        assert "# Report" in html
        assert "Hello world." in html
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_evidence_open_rejects_path_traversal(tmp_path):
    runtime_dir = tmp_path / "runtime"
    server = build_dashboard_server(runtime_dir=runtime_dir, port=0, refresh_seconds=0)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_address[1]}"

    try:
        traversal_refs = [
            "..%2F..%2Fetc%2Fpasswd",
            "..%5C..%5Cetc%5Cpasswd",
            "/etc/passwd",
            "../ExecutionReport.md",
            "..%5CExecutionReport.md",
            quote(str(tmp_path / "ExecutionReport.md"), safe=""),
        ]
        for ref in traversal_refs:
            try:
                with urlopen(f"{base_url}/evidence/open?ref={ref}", timeout=5) as response:
                    response.read().decode("utf-8")
                raise AssertionError(f"dashboard served path traversal for {ref}")
            except HTTPError as error:
                assert error.code in {404, 403}
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_evidence_open_serves_directory_with_child_link(tmp_path):
    runtime_dir = tmp_path / "runtime"
    runtime_dir.mkdir(parents=True, exist_ok=True)
    evidence_dir = runtime_dir / "evidence"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    child_file = evidence_dir / "ExecutionReport.md"
    child_file.write_text("# Report\nHello world.", encoding="utf-8")

    server = build_dashboard_server(runtime_dir=runtime_dir, port=0, refresh_seconds=0)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_address[1]}"

    try:
        with urlopen(f"{base_url}/evidence/open?ref=evidence", timeout=5) as response:
            html = response.read().decode("utf-8")
        assert response.status == 200
        assert "<h1>Directory: evidence</h1>" in html
        assert "ExecutionReport.md" in html
        assert 'href="/evidence/open?ref=evidence/ExecutionReport.md"' in html
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_evidence_open_child_link_preview(tmp_path):
    runtime_dir = tmp_path / "runtime"
    runtime_dir.mkdir(parents=True, exist_ok=True)
    evidence_dir = runtime_dir / "evidence"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    child_file = evidence_dir / "ExecutionReport.md"
    child_file.write_text("# Report\nHello world.", encoding="utf-8")

    server = build_dashboard_server(runtime_dir=runtime_dir, port=0, refresh_seconds=0)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_address[1]}"

    try:
        with urlopen(f"{base_url}/evidence/open?ref=evidence/ExecutionReport.md", timeout=5) as response:
            html = response.read().decode("utf-8")
        assert response.status == 200
        assert "<h1>evidence/ExecutionReport.md</h1>" in html
        assert "# Report" in html
        assert "Hello world." in html
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_review_gate_open_200_with_evidence(tmp_path, monkeypatch):
    runtime_dir = tmp_path / "runtime"
    runtime_dir.mkdir(parents=True, exist_ok=True)
    evidence_file = runtime_dir / "evidence.md"
    evidence_file.write_text("# Evidence\nHello world.", encoding="utf-8")

    state = {
        "gates": [
            {
                "gate_id": "gate-1",
                "kind": "human",
                "status": "open",
                "reason": "Needs review",
                "run_id": "run-1",
                "next_action": "Review now",
            }
        ],
        "team": {
            "review_gates": [
                {
                    "gate_id": "gate-1",
                    "kind": "human",
                    "status": "open",
                    "reason": "Needs review",
                    "run_id": "run-1",
                }
            ],
            "evidence_store": [
                {
                    "evidence_id": "ev-1",
                    "run_id": "run-1",
                    "ref_type": "report",
                    "ref_path": str(evidence_file),
                }
            ],
        },
    }

    monkeypatch.setattr(dashboard_module, "build_visual_control_plane_state", lambda *a, **kw: state)

    server = build_dashboard_server(runtime_dir=runtime_dir, port=0, refresh_seconds=0)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_address[1]}"

    try:
        with urlopen(f"{base_url}/review-gates/open?gate_id=gate-1", timeout=5) as response:
            html = response.read().decode("utf-8")
        assert response.status == 200
        assert "gate-1" in html
        assert "Needs review" in html
        assert "Review now" in html
        assert "evidence.md" in html
        assert "/evidence/open?ref=evidence.md" in html
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_review_gate_open_400_missing_gate_id(tmp_path, monkeypatch):
    runtime_dir = tmp_path / "runtime"
    runtime_dir.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(dashboard_module, "build_visual_control_plane_state", lambda *a, **kw: {"gates": [], "team": {}})

    server = build_dashboard_server(runtime_dir=runtime_dir, port=0, refresh_seconds=0)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_address[1]}"

    try:
        try:
            with urlopen(f"{base_url}/review-gates/open", timeout=5) as response:
                response.read()
            raise AssertionError("expected 400")
        except HTTPError as error:
            assert error.code == 400
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_review_gate_open_404_unknown_gate(tmp_path, monkeypatch):
    runtime_dir = tmp_path / "runtime"
    runtime_dir.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(dashboard_module, "build_visual_control_plane_state", lambda *a, **kw: {"gates": [], "team": {}})

    server = build_dashboard_server(runtime_dir=runtime_dir, port=0, refresh_seconds=0)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_address[1]}"

    try:
        try:
            with urlopen(f"{base_url}/review-gates/open?gate_id=nonexistent", timeout=5) as response:
                response.read()
            raise AssertionError("expected 404")
        except HTTPError as error:
            assert error.code == 404
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_review_gate_open_encodes_evidence_ref_with_space(tmp_path, monkeypatch):
    runtime_dir = tmp_path / "runtime"
    runtime_dir.mkdir(parents=True, exist_ok=True)
    evidence_file = runtime_dir / "my evidence.md"
    evidence_file.write_text("# Evidence\nHello world.", encoding="utf-8")

    state = {
        "gates": [
            {
                "gate_id": "gate-1",
                "kind": "human",
                "status": "open",
                "reason": "Needs review",
                "run_id": "run-1",
                "next_action": "Review now",
            }
        ],
        "team": {
            "review_gates": [
                {
                    "gate_id": "gate-1",
                    "kind": "human",
                    "status": "open",
                    "reason": "Needs review",
                    "run_id": "run-1",
                }
            ],
            "evidence_store": [
                {
                    "evidence_id": "ev-1",
                    "run_id": "run-1",
                    "ref_type": "report",
                    "ref_path": str(evidence_file),
                }
            ],
        },
    }

    monkeypatch.setattr(dashboard_module, "build_visual_control_plane_state", lambda *a, **kw: state)

    server = build_dashboard_server(runtime_dir=runtime_dir, port=0, refresh_seconds=0)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_address[1]}"

    try:
        with urlopen(f"{base_url}/review-gates/open?gate_id=gate-1", timeout=5) as response:
            html = response.read().decode("utf-8")
        assert response.status == 200
        assert "my%20evidence.md" in html
        assert "my evidence.md" in html
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_review_gate_open_has_no_mojibake_fallback(tmp_path, monkeypatch):
    runtime_dir = tmp_path / "runtime"
    runtime_dir.mkdir(parents=True, exist_ok=True)

    state = {
        "gates": [
            {
                "gate_id": "gate-1",
                "kind": "human",
                "status": "open",
                "reason": "",
                "run_id": "run-1",
                "next_action": "",
            }
        ],
        "team": {
            "review_gates": [
                {
                    "gate_id": "gate-1",
                    "kind": "human",
                    "status": "open",
                    "reason": "",
                    "run_id": "run-1",
                }
            ],
            "evidence_store": [],
        },
    }

    monkeypatch.setattr(dashboard_module, "build_visual_control_plane_state", lambda *a, **kw: state)

    server = build_dashboard_server(runtime_dir=runtime_dir, port=0, refresh_seconds=0)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_address[1]}"

    try:
        with urlopen(f"{base_url}/review-gates/open?gate_id=gate-1", timeout=5) as response:
            html = response.read().decode("utf-8")
        assert response.status == 200
        assert "鈥" not in html
        assert "<dd>-</dd>" in html
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_review_gate_open_blocked_shows_repair_dispatch_form(tmp_path, monkeypatch):
    runtime_dir = tmp_path / "runtime"
    runtime_dir.mkdir(parents=True, exist_ok=True)
    evidence_file = runtime_dir / "evidence.md"
    evidence_file.write_text("# Evidence\nHello world.", encoding="utf-8")

    state = {
        "gates": [
            {
                "gate_id": "gate-1",
                "kind": "acceptance",
                "status": "blocked",
                "reason": "Tests failing",
                "run_id": "run-1",
                "next_action": "Fix tests",
            }
        ],
        "projects": [
            {
                "project_id": "proj-1",
                "contract_path": str(runtime_dir / "project-contracts" / "contract.json"),
                "display_name": "Project 1",
            }
        ],
        "team": {
            "review_gates": [
                {
                    "gate_id": "gate-1",
                    "kind": "acceptance",
                    "status": "blocked",
                    "reason": "Tests failing",
                    "run_id": "run-1",
                }
            ],
            "evidence_store": [
                {
                    "evidence_id": "ev-1",
                    "run_id": "run-1",
                    "ref_type": "report",
                    "ref_path": str(evidence_file),
                }
            ],
        },
    }

    monkeypatch.setattr(dashboard_module, "build_visual_control_plane_state", lambda *a, **kw: state)

    server = build_dashboard_server(runtime_dir=runtime_dir, port=0, refresh_seconds=0)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_address[1]}"

    try:
        with urlopen(f"{base_url}/review-gates/open?gate_id=gate-1", timeout=5) as response:
            html = response.read().decode("utf-8")
        assert response.status == 200
        assert "Repair Dispatch" in html
        assert '<form method="post" action="/go/dispatch">' in html
        assert "Repair review gate gate-1" in html
        assert "Status: blocked" in html
        assert "Kind: acceptance" in html
        assert "Run ID: run-1" in html
        assert "Reason: Tests failing" in html
        assert "Next action: Fix tests" in html
        assert "evidence.md" in html
        assert 'name="agents" value="1"' in html
        assert 'id="max_agents"' in html
        assert 'name="execute" value="1"' in html
        assert 'name="execute" value="1" checked' not in html
        assert 'name="changed" value="1"' in html
        assert 'name="changed" value="1" checked' not in html
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_review_gate_open_pass_hides_repair_form(tmp_path, monkeypatch):
    runtime_dir = tmp_path / "runtime"
    runtime_dir.mkdir(parents=True, exist_ok=True)

    state = {
        "gates": [
            {
                "gate_id": "gate-1",
                "kind": "acceptance",
                "status": "PASS",
                "reason": "All good",
                "run_id": "run-1",
                "next_action": "Merge",
            }
        ],
        "projects": [
            {
                "project_id": "proj-1",
                "contract_path": str(runtime_dir / "project-contracts" / "contract.json"),
                "display_name": "Project 1",
            }
        ],
        "team": {
            "review_gates": [
                {
                    "gate_id": "gate-1",
                    "kind": "acceptance",
                    "status": "PASS",
                    "reason": "All good",
                    "run_id": "run-1",
                }
            ],
            "evidence_store": [],
        },
    }

    monkeypatch.setattr(dashboard_module, "build_visual_control_plane_state", lambda *a, **kw: state)

    server = build_dashboard_server(runtime_dir=runtime_dir, port=0, refresh_seconds=0)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_address[1]}"

    try:
        with urlopen(f"{base_url}/review-gates/open?gate_id=gate-1", timeout=5) as response:
            html = response.read().decode("utf-8")
        assert response.status == 200
        assert "Repair Dispatch" not in html
        assert '<form method="post" action="/go/dispatch">' not in html
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def _write_session_intake(runtime_dir, session_id, intake_id, *, dispatched=False):
    project_root = runtime_dir.parent / "project"
    project_root.mkdir(parents=True, exist_ok=True)
    sessions_dir = runtime_dir / "web-ai-sessions"
    sessions_dir.mkdir(parents=True, exist_ok=True)
    native_refs = {
        "outcome": "task_intake_recorded",
        "project_root": str(project_root),
        "intake_id": intake_id,
        "task_title": "Test session dispatch",
        "suggested_agent": "opencode",
        "priority": "high",
        "connector_name": "DevFrame",
    }
    if dispatched:
        native_refs["dispatch_go_run_id"] = "go-already-dispatched"
    session_file = sessions_dir / f"{session_id}.json"
    session_file.write_text(json.dumps({
        "session_id": session_id,
        "provider": "codexpro",
        "status": "idle",
        "project_id": "demo-project",
        "native_refs": native_refs,
        "actions": ["Execute Web GPT task intake through local agents."],
    }, indent=2, ensure_ascii=True), encoding="utf-8")
    return session_file


def _session_action_id(session_id, action_text):
    from control_plane.visual_state import _safe_id
    return _safe_id(f"{session_id}-{action_text}")


class _FakeDispatchGoResult:
    go_run_id = "go-dispatched-001"
    status = "queued"
    project_root = str(Path.cwd())
    execute = False
    agents = []
    metadata_path = str(Path.cwd() / "go-runs" / "go-dispatched-001.json")


def test_session_execute_human_required_on_first_post(tmp_path, monkeypatch):
    runtime_dir = tmp_path / "runtime"
    session_id = "session-exec-1"
    intake_id = "intake-exec-1"
    _write_session_intake(runtime_dir, session_id, intake_id)
    action_id = _session_action_id(session_id, "Execute Web GPT task intake through local agents.")

    monkeypatch.setattr(dashboard_module, "_start_session_dispatch", lambda *a, **kw: {
        "started": True, "reused": False, "action_id": a[0], "kind": "session_dispatch",
    })

    server = build_dashboard_server(runtime_dir=runtime_dir, port=0, refresh_seconds=0)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_address[1]}"

    try:
        request = Request(
            f"{base_url}/actions/execute?action_id={action_id}",
            data=b"",
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "Origin": base_url,
            },
            method="POST",
        )
        try:
            with urlopen(request, timeout=5) as response:
                payload = json.loads(response.read().decode("utf-8"))
            raise AssertionError("expected 409 Conflict")
        except HTTPError as error:
            assert error.code == 409
            payload = json.loads(error.read().decode("utf-8"))

        assert payload["error"] == "human_required"
        assert payload["action_id"] == action_id
        assert "confirm=execute" in payload["confirm"]
        assert "dispatch-task-intakes" in payload["command"]
        assert "intake" in payload["command"].lower()
        assert payload["context"]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_session_execute_dispatches_one_intake_without_open_code(tmp_path, monkeypatch):
    runtime_dir = tmp_path / "runtime"
    session_id = "session-exec-2"
    intake_id = "intake-exec-2"
    _write_session_intake(runtime_dir, session_id, intake_id)
    action_id = _session_action_id(session_id, "Execute Web GPT task intake through local agents.")

    dispatch_calls = []

    import control_plane.go_dispatch as go_dispatch_module

    def fake_run_go_dispatch(**kwargs):
        dispatch_calls.append(kwargs)
        return _FakeDispatchGoResult()

    monkeypatch.setattr(go_dispatch_module, "run_go_dispatch", fake_run_go_dispatch)

    popen_called = []

    def track_popen(*args, **kwargs):
        popen_called.append((args, kwargs))
        return _FakeProcess()

    monkeypatch.setattr(dashboard_module.subprocess, "Popen", track_popen)

    server = build_dashboard_server(runtime_dir=runtime_dir, port=0, refresh_seconds=0)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_address[1]}"

    try:
        request = Request(
            f"{base_url}/actions/execute?action_id={action_id}",
            data=b"confirm=execute",
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "Origin": base_url,
            },
            method="POST",
        )
        with urlopen(request, timeout=5) as response:
            payload = json.loads(response.read().decode("utf-8"))

        assert response.status == 202
        assert payload["started"] is True
        assert payload["action_id"] == action_id
        assert payload["kind"] == "session_dispatch"
        assert payload["session_id"] == session_id
        assert payload["action_run_id"]
        assert "record_path" in payload

        assert len(dispatch_calls) == 1
        assert dispatch_calls[0]["project_path"] == (runtime_dir.parent / "project").resolve()
        assert dispatch_calls[0]["execute"] is False
        assert dispatch_calls[0]["agents"] == 1
        assert "task intake" in str(dispatch_calls[0].get("requirement", "")).lower()

        assert not popen_called

        record_path = Path(payload["record_path"])
        assert record_path.exists()
        record = json.loads(record_path.read_text(encoding="utf-8"))
        assert record["action_id"] == action_id
        assert record["status"] == "completed"
        assert record["kind"] == "session_dispatch"
        assert record["exit_code"] == 0
        assert record["completed_at"]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_approval_response_approve_dispatches_task_intake_session(tmp_path, monkeypatch):
    runtime_dir = tmp_path / "runtime"
    session_id = "session-approval-intake"
    intake_id = "intake-approval-intake"
    _write_session_intake(runtime_dir, session_id, intake_id)

    dispatch_calls = []

    import control_plane.go_dispatch as go_dispatch_module

    def fake_run_go_dispatch(**kwargs):
        dispatch_calls.append(kwargs)
        return _FakeDispatchGoResult()

    monkeypatch.setattr(go_dispatch_module, "run_go_dispatch", fake_run_go_dispatch)
    monkeypatch.setattr(dashboard_module.subprocess, "Popen", lambda *a, **kw: (_ for _ in ()).throw(AssertionError("Popen should not run")))

    server = build_dashboard_server(runtime_dir=runtime_dir, port=0, refresh_seconds=0)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_address[1]}"

    try:
        action_id = _session_action_id(session_id, "Execute Web GPT task intake through local agents.")
        request_id = f"{session_id}-{action_id}"
        body = json.dumps({
            "requestId": request_id,
            "threadId": session_id,
            "decision": "approve",
        })
        request = Request(
            f"{base_url}/api/t3/approval-response",
            data=body.encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Origin": base_url,
            },
            method="POST",
        )
        with urlopen(request, timeout=5) as response:
            payload = json.loads(response.read().decode("utf-8"))

        assert response.status == 202
        assert payload["responded"] is True
        assert payload["decision"] == "approve"
        assert payload["kind"] == "session_dispatch"
        assert payload["session_id"] == session_id
        assert payload["go_run_id"] == "go-dispatched-001"
        assert len(dispatch_calls) == 1
        assert dispatch_calls[0]["execute"] is False
        assert dispatch_calls[0]["project_path"] == (runtime_dir.parent / "project").resolve()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_session_execute_unsupported_already_dispatched(tmp_path, monkeypatch):
    runtime_dir = tmp_path / "runtime"
    session_id = "session-dispatched"
    intake_id = "intake-dispatched"
    _write_session_intake(runtime_dir, session_id, intake_id, dispatched=True)
    action_id = _session_action_id(session_id, "Execute Web GPT task intake through local agents.")

    server = build_dashboard_server(runtime_dir=runtime_dir, port=0, refresh_seconds=0)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_address[1]}"

    try:
        request = Request(
            f"{base_url}/actions/execute?action_id={action_id}",
            data=b"confirm=execute",
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "Origin": base_url,
            },
            method="POST",
        )
        try:
            with urlopen(request, timeout=5):
                pass
            raise AssertionError("expected 409 Conflict")
        except HTTPError as error:
            assert error.code == 409
            payload = json.loads(error.read().decode("utf-8"))

        assert payload["error"] == "unsupported_action"
        assert "Only queued go_run" in payload["reason"]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_session_execute_unsupported_non_task_intake(tmp_path, monkeypatch):
    runtime_dir = tmp_path / "runtime"
    sessions_dir = runtime_dir / "web-ai-sessions"
    sessions_dir.mkdir(parents=True, exist_ok=True)
    session_id = "session-review"
    session_file = sessions_dir / f"{session_id}.json"
    session_file.write_text(json.dumps({
        "session_id": session_id,
        "provider": "chatgpt",
        "status": "idle",
        "native_refs": {
            "outcome": "review_completed",
        },
        "actions": ["Review imported web AI session action."],
    }, indent=2, ensure_ascii=True), encoding="utf-8")
    action_id = _session_action_id(session_id, "Review imported web AI session action.")

    server = build_dashboard_server(runtime_dir=runtime_dir, port=0, refresh_seconds=0)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_address[1]}"

    try:
        request = Request(
            f"{base_url}/actions/execute?action_id={action_id}",
            data=b"confirm=execute",
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "Origin": base_url,
            },
            method="POST",
        )
        try:
            with urlopen(request, timeout=5):
                pass
            raise AssertionError("expected 409 Conflict")
        except HTTPError as error:
            assert error.code == 409
            payload = json.loads(error.read().decode("utf-8"))

        assert payload["error"] == "unsupported_action"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_review_gate_open_escapes_repair_form_values(tmp_path, monkeypatch):
    runtime_dir = tmp_path / "runtime"
    runtime_dir.mkdir(parents=True, exist_ok=True)

    state = {
        "gates": [
            {
                "gate_id": "gate-1",
                "kind": "acceptance",
                "status": "blocked",
                "reason": "<script>alert('xss')</script>",
                "run_id": "run-1",
                "next_action": "<img src=x onerror=alert(1)>",
            }
        ],
        "projects": [
            {
                "project_id": "proj-1",
                "contract_path": str(runtime_dir / "project-contracts" / "contract.json"),
                "display_name": "Project 1",
            }
        ],
        "team": {
            "review_gates": [
                {
                    "gate_id": "gate-1",
                    "kind": "acceptance",
                    "status": "blocked",
                    "reason": "<script>alert('xss')</script>",
                    "run_id": "run-1",
                }
            ],
            "evidence_store": [],
        },
    }

    monkeypatch.setattr(dashboard_module, "build_visual_control_plane_state", lambda *a, **kw: state)

    server = build_dashboard_server(runtime_dir=runtime_dir, port=0, refresh_seconds=0)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_address[1]}"

    try:
        with urlopen(f"{base_url}/review-gates/open?gate_id=gate-1", timeout=5) as response:
            html = response.read().decode("utf-8")
        assert response.status == 200
        assert "<script>alert('xss')</script>" not in html
        assert "&lt;script&gt;alert(&#x27;xss&#x27;)&lt;/script&gt;" in html
        assert "<img src=x onerror=alert(1)>" not in html
        assert "&lt;img src=x onerror=alert(1)&gt;" in html
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
