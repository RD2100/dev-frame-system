"""End-to-end dashboard tests for the human-gated write-back channel (M8.2).

Proposing a write-back never writes; only a human approval through
``/api/t3/approval-response`` applies it, and a reject discards it.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from threading import Thread
from urllib.request import Request, urlopen

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import control_plane.dashboard as dashboard_module  # noqa: E402
from control_plane.dashboard import build_dashboard_server  # noqa: E402


def _post_json(base_url: str, path: str, payload: dict) -> tuple[int, dict]:
    request = Request(
        f"{base_url}{path}",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    with urlopen(request, timeout=5) as response:
        return response.status, json.loads(response.read().decode("utf-8"))


def _run_server(tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    runtime_dir = tmp_path / "runtime"
    runtime_dir.mkdir()
    monkeypatch.setattr(
        dashboard_module,
        "_resolve_writeback_workspace_root",
        lambda rd, ppd, project_id: str(workspace),
    )
    server = build_dashboard_server(runtime_dir=runtime_dir, port=0, refresh_seconds=0)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_address[1]}"
    return server, base_url, workspace


def test_writeback_propose_then_approve_writes(tmp_path, monkeypatch):
    server, base_url, workspace = _run_server(tmp_path, monkeypatch)
    try:
        status, staged = _post_json(base_url, "/api/t3/writeback-propose", {
            "projectId": "demo",
            "relativePath": "src/hello.txt",
            "contents": "approved by human",
            "threadId": "t-1",
        })
        assert status == 202
        assert staged["staged"] is True
        request_id = staged["requestId"]
        assert request_id.startswith("wb-")
        # Nothing written yet — this is only a proposal.
        assert not (workspace / "src" / "hello.txt").exists()

        status, resolved = _post_json(base_url, "/api/t3/approval-response", {
            "requestId": request_id,
            "threadId": "t-1",
            "decision": "approve",
        })
        assert status == 200
        assert resolved["executed"] is True
        assert (workspace / "src" / "hello.txt").read_text(encoding="utf-8") == "approved by human"
    finally:
        server.shutdown()


def test_writeback_propose_then_reject_does_not_write(tmp_path, monkeypatch):
    server, base_url, workspace = _run_server(tmp_path, monkeypatch)
    try:
        _, staged = _post_json(base_url, "/api/t3/writeback-propose", {
            "projectId": "demo",
            "relativePath": "x.txt",
            "contents": "should not be written",
        })
        request_id = staged["requestId"]
        status, resolved = _post_json(base_url, "/api/t3/approval-response", {
            "requestId": request_id,
            "threadId": "t-1",
            "decision": "reject",
        })
        assert status == 200
        assert resolved["executed"] is False
        assert not (workspace / "x.txt").exists()
    finally:
        server.shutdown()


def test_writeback_propose_rejects_unsafe_path(tmp_path, monkeypatch):
    server, base_url, workspace = _run_server(tmp_path, monkeypatch)
    try:
        request = Request(
            f"{base_url}/api/t3/writeback-propose",
            data=json.dumps({"projectId": "demo", "relativePath": "../escape.txt", "contents": "x"}).encode("utf-8"),
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            method="POST",
        )
        from urllib.error import HTTPError

        try:
            urlopen(request, timeout=5)
            raise AssertionError("unsafe write-back proposal was not rejected")
        except HTTPError as error:
            assert error.code == 400
            body = json.loads(error.read().decode("utf-8"))
            assert body["error"] == "writeback_rejected"
        assert not (workspace.parent / "escape.txt").exists()
    finally:
        server.shutdown()
