"""Tests for the DevFrame MCP server (governed AI operation surface).

Includes a real round-trip with DevFrame's own MCP client against the running
loopback server, proving initialize -> tools/list -> tools/call end to end.
"""
from __future__ import annotations

import json
import socket
import sys
from pathlib import Path
from threading import Thread
from urllib.request import Request, urlopen

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import control_plane.dashboard as dashboard_module  # noqa: E402
import control_plane.mcp_consent as mcp_consent  # noqa: E402
from control_plane.dashboard import build_dashboard_server  # noqa: E402
from control_plane.mcp_live_probe import mcp_live_probe  # noqa: E402
from control_plane.obsidian_memory import memory_authority_fingerprint  # noqa: E402
from control_plane.mcp_server import TOOLS, handle_mcp_jsonrpc  # noqa: E402


def _authorize(session_id, runtime_dir):
    mcp_consent.register_connection(session_id, "test-client", runtime_dir=runtime_dir)
    mcp_consent.decide(session_id, "allow_once", runtime_dir=runtime_dir)


def _authorize_scope(session_id, runtime_dir, scope, project_id="demo"):
    mcp_consent.register_connection(session_id, "test-client", runtime_dir=runtime_dir)
    mcp_consent.request_scope(
        session_id,
        scope,
        memory_authority_fingerprint(project_id),
    )
    mcp_consent.decide(session_id, "allow_once", runtime_dir=runtime_dir)


def test_initialize_returns_protocol_and_session():
    response, headers = handle_mcp_jsonrpc({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
    assert response["result"]["protocolVersion"]
    assert response["result"]["serverInfo"]["name"] == "devframe-mcp"
    assert "MCP-Session-Id" in headers


def test_initialized_notification_has_no_response():
    response, _ = handle_mcp_jsonrpc({"jsonrpc": "2.0", "method": "notifications/initialized"})
    assert response is None


def test_tools_list_advertises_tools():
    response, _ = handle_mcp_jsonrpc({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
    names = {t["name"] for t in response["result"]["tools"]}
    assert {
        "server_config",
        "read_project_shell",
        "propose_writeback",
        "list_pending_writebacks",
        "search_obsidian_memory",
        "propose_obsidian_memory",
    } <= names
    assert names == {t["name"] for t in TOOLS}


def test_unknown_method_errors():
    response, _ = handle_mcp_jsonrpc({"jsonrpc": "2.0", "id": 9, "method": "does/not/exist"})
    assert response["error"]["code"] == -32601


@pytest.mark.parametrize("method", ["initialize", "tools/call"])
@pytest.mark.parametrize("params", ["invalid", []])
def test_mcp_rejects_non_object_params(method, params):
    response, _ = handle_mcp_jsonrpc(
        {"jsonrpc": "2.0", "id": 10, "method": method, "params": params}
    )
    assert response["error"]["code"] == -32602


def test_server_config_tool_call(tmp_path):
    mcp_consent._reset_for_tests()
    _authorize("sess-cfg", tmp_path)
    response, _ = handle_mcp_jsonrpc(
        {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "server_config", "arguments": {}}},
        runtime_dir=tmp_path,
        session_id="sess-cfg",
    )
    assert response["result"]["isError"] is False
    text = response["result"]["content"][0]["text"]
    assert "devframe-mcp" in text


def test_tools_call_requires_authorization(tmp_path):
    mcp_consent._reset_for_tests()
    mcp_consent.register_connection("sess-pending", "test-client", runtime_dir=tmp_path)
    response, _ = handle_mcp_jsonrpc(
        {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "server_config", "arguments": {}}},
        runtime_dir=tmp_path,
        session_id="sess-pending",
    )
    assert response["result"]["isError"] is True
    assert "authorization_pending" in response["result"]["content"][0]["text"]
    mcp_consent.decide("sess-pending", "allow_once", runtime_dir=tmp_path)
    response2, _ = handle_mcp_jsonrpc(
        {"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {"name": "server_config", "arguments": {}}},
        runtime_dir=tmp_path,
        session_id="sess-pending",
    )
    assert response2["result"]["isError"] is False


def test_propose_writeback_tool_stages_without_writing(tmp_path, monkeypatch):
    mcp_consent._reset_for_tests()
    _authorize("sess-wb", tmp_path)
    workspace = tmp_path / "ws"
    workspace.mkdir()
    runtime = tmp_path / "rt"
    monkeypatch.setattr(
        dashboard_module,
        "_resolve_writeback_workspace_root",
        lambda rd, ppd, project_id: str(workspace),
    )
    response, _ = handle_mcp_jsonrpc(
        {
            "jsonrpc": "2.0",
            "id": 4,
            "method": "tools/call",
            "params": {
                "name": "propose_writeback",
                "arguments": {"projectId": "demo", "relativePath": "src/a.txt", "contents": "ai proposed"},
            },
        },
        runtime_dir=runtime,
        session_id="sess-wb",
    )
    result = response["result"]
    assert result["isError"] is False
    payload = json.loads(result["content"][0]["text"])
    assert payload["staged"] is True
    assert payload["requestId"].startswith("wb-")
    # The MCP server must never write; only a human approval applies it.
    assert not (workspace / "src" / "a.txt").exists()


def test_propose_writeback_unknown_project_is_tool_error(tmp_path, monkeypatch):
    mcp_consent._reset_for_tests()
    _authorize("sess-unk", tmp_path)
    monkeypatch.setattr(
        dashboard_module,
        "_resolve_writeback_workspace_root",
        lambda rd, ppd, project_id: "",
    )
    response, _ = handle_mcp_jsonrpc(
        {
            "jsonrpc": "2.0",
            "id": 5,
            "method": "tools/call",
            "params": {
                "name": "propose_writeback",
                "arguments": {"projectId": "nope", "relativePath": "a.txt", "contents": "x"},
            },
        },
        runtime_dir=tmp_path,
        session_id="sess-unk",
    )
    assert response["result"]["isError"] is True
    assert "unknown_project" in response["result"]["content"][0]["text"]


def test_live_probe_round_trip_against_running_server(tmp_path):
    runtime_dir = tmp_path / "runtime"
    runtime_dir.mkdir()
    server = build_dashboard_server(runtime_dir=runtime_dir, port=0, refresh_seconds=0)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base_url = f"http://127.0.0.1:{server.server_address[1]}"
        probe = mcp_live_probe(f"{base_url}/mcp", provider="codexpro", tool="server_config")
        assert probe["status"] == "live_ok"
        assert "server_config" in probe["tool_names"]
        assert probe["tool_called"] == "server_config"
    finally:
        server.shutdown()


_INIT_BODY = json.dumps({
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {"protocolVersion": "2024-11-05", "capabilities": {}, "clientInfo": {"name": "t", "version": "1"}},
}).encode("utf-8")


def _start(tmp_path):
    runtime_dir = tmp_path / "runtime"
    runtime_dir.mkdir(exist_ok=True)
    server = build_dashboard_server(runtime_dir=runtime_dir, port=0, refresh_seconds=0)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, f"http://127.0.0.1:{server.server_address[1]}"


def test_mcp_rejects_oversized_body_before_reading_it(tmp_path):
    server, _ = _start(tmp_path)
    try:
        host, port = server.server_address
        with socket.create_connection((host, port), timeout=5) as client:
            client.sendall(
                (
                    "POST /mcp HTTP/1.1\r\n"
                    f"Host: {host}:{port}\r\n"
                    f"Content-Length: {(8 * 1024 * 1024) + 1}\r\n"
                    "Content-Type: application/json\r\n"
                    "Connection: close\r\n\r\n"
                ).encode("ascii")
            )
            client.shutdown(socket.SHUT_WR)
            response = b""
            while True:
                chunk = client.recv(65_536)
                if not chunk:
                    break
                response += chunk
        assert response.startswith(b"HTTP/1.0 413")
        assert b"request_body_too_large" in response
    finally:
        server.shutdown()
        server.server_close()


def test_mcp_rejects_invalid_utf8_without_replacement(tmp_path):
    from urllib.error import HTTPError

    server, base_url = _start(tmp_path)
    try:
        request = Request(
            f"{base_url}/mcp",
            data=b'\xff{"jsonrpc":"2.0"}',
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            method="POST",
        )
        with pytest.raises(HTTPError) as caught:
            urlopen(request, timeout=5)
        assert caught.value.code == 400
        payload = json.loads(caught.value.read().decode("utf-8"))
        assert payload["error"]["message"] == "invalid_utf8_body"
    finally:
        server.shutdown()
        server.server_close()


def test_mcp_sse_response_when_accept_event_stream(tmp_path):
    server, base_url = _start(tmp_path)
    try:
        request = Request(
            f"{base_url}/mcp",
            data=_INIT_BODY,
            headers={"Content-Type": "application/json", "Accept": "application/json, text/event-stream"},
            method="POST",
        )
        with urlopen(request, timeout=5) as response:
            assert response.headers.get("Content-Type", "").startswith("text/event-stream")
            body = response.read().decode("utf-8")
        assert body.startswith("event: message")
        assert '"protocolVersion"' in body
    finally:
        server.shutdown()


def test_mcp_token_required_when_configured(tmp_path, monkeypatch):
    monkeypatch.setenv("DEVFRAME_MCP_TOKEN", "secret-token-123")
    server, base_url = _start(tmp_path)
    try:
        from urllib.error import HTTPError

        # No token -> 401
        no_token = Request(
            f"{base_url}/mcp",
            data=_INIT_BODY,
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            method="POST",
        )
        try:
            urlopen(no_token, timeout=5)
            raise AssertionError("MCP endpoint accepted a request without the configured token")
        except HTTPError as error:
            assert error.code == 401

        # Correct token via query -> 200
        with_token = Request(
            f"{base_url}/mcp?token=secret-token-123",
            data=_INIT_BODY,
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            method="POST",
        )
        with urlopen(with_token, timeout=5) as response:
            assert response.status == 200
            data = json.loads(response.read().decode("utf-8"))
        assert data["result"]["serverInfo"]["name"] == "devframe-mcp"
    finally:
        server.shutdown()


def _call(tool, args, runtime_dir, session_id):
    response, _ = handle_mcp_jsonrpc(
        {"jsonrpc": "2.0", "id": 7, "method": "tools/call", "params": {"name": tool, "arguments": args}},
        runtime_dir=runtime_dir,
        session_id=session_id,
    )
    assert response["result"]["isError"] is False
    return json.loads(response["result"]["content"][0]["text"])


def test_get_run_status_empty_runtime(tmp_path):
    mcp_consent._reset_for_tests()
    _authorize("sess-run", tmp_path)
    payload = _call("get_run_status", {}, tmp_path, "sess-run")
    assert "runs" in payload  # no runs recorded yet


def test_get_team_status_shape(tmp_path):
    mcp_consent._reset_for_tests()
    _authorize("sess-team", tmp_path)
    payload = _call("get_team_status", {}, tmp_path, "sess-team")
    for key in ("agentRegistry", "taskBoard", "recentEvents", "reviewGates", "conflictControl"):
        assert key in payload


def test_list_pending_gates_shape(tmp_path):
    mcp_consent._reset_for_tests()
    _authorize("sess-gates", tmp_path)
    payload = _call("list_pending_gates", {}, tmp_path, "sess-gates")
    assert "pendingGates" in payload
    assert isinstance(payload["pendingGates"], list)


def test_phase1_tools_require_authorization(tmp_path):
    mcp_consent._reset_for_tests()
    mcp_consent.register_connection("sess-unauth", "c", runtime_dir=tmp_path)
    response, _ = handle_mcp_jsonrpc(
        {"jsonrpc": "2.0", "id": 8, "method": "tools/call", "params": {"name": "get_team_status", "arguments": {}}},
        runtime_dir=tmp_path,
        session_id="sess-unauth",
    )
    assert response["result"]["isError"] is True
    assert "authorization_pending" in response["result"]["content"][0]["text"]


def test_propose_task_tool_stages_without_running(tmp_path, monkeypatch):
    mcp_consent._reset_for_tests()
    _authorize("sess-task", tmp_path)
    monkeypatch.setattr(
        dashboard_module,
        "_resolve_writeback_workspace_root",
        lambda rd, ppd, project_id: str(tmp_path),
    )
    payload = _call("propose_task", {"projectId": "demo", "goal": "add a feature"}, tmp_path, "sess-task")
    assert payload["staged"] is True
    assert payload["requestId"].startswith("tk-")
    # listed as pending
    pending = _call("list_pending_tasks", {}, tmp_path, "sess-task")
    assert any(p["request_id"] == payload["requestId"] for p in pending["pending"])


def test_propose_task_unknown_project_is_error(tmp_path, monkeypatch):
    mcp_consent._reset_for_tests()
    _authorize("sess-task2", tmp_path)
    monkeypatch.setattr(
        dashboard_module,
        "_resolve_writeback_workspace_root",
        lambda rd, ppd, project_id: "",
    )
    response, _ = handle_mcp_jsonrpc(
        {"jsonrpc": "2.0", "id": 9, "method": "tools/call",
         "params": {"name": "propose_task", "arguments": {"projectId": "nope", "goal": "x"}}},
        runtime_dir=tmp_path,
        session_id="sess-task2",
    )
    assert response["result"]["isError"] is True
    assert "unknown_project" in response["result"]["content"][0]["text"]


def test_memory_search_requires_scope_and_returns_real_chinese_text(tmp_path, monkeypatch):
    mcp_consent._reset_for_tests()
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "memory.md").write_text(
        "---\nproject_id: demo\n---\n# 记忆\n模型记忆永久存储需要来源和新鲜度。",
        encoding="utf-8",
    )
    monkeypatch.setenv("DEVFRAME_OBSIDIAN_MEMORY_ROOT", str(vault))
    monkeypatch.setenv("DEVFRAME_OBSIDIAN_MEMORY_ALLOWLIST", '["memory.md"]')
    _authorize_scope("sess-memory", runtime, mcp_consent.MEMORY_READ_SCOPE)

    payload = _call(
        "search_obsidian_memory",
        {"projectId": "demo", "query": "永久存储", "relativePaths": ["memory.md"]},
        runtime,
        "sess-memory",
    )
    assert "永久存储" in payload["results"][0]["excerpt"]
    audit = (runtime / "mcp-audit.jsonl").read_text(encoding="utf-8")
    assert str(vault) not in audit
    assert "永久存储" not in audit
    events = [json.loads(line) for line in audit.splitlines()]
    result_event = next(
        event
        for event in reversed(events)
        if event.get("event") == "tool_result"
    )
    assert result_event["required_scope"] == mcp_consent.MEMORY_READ_SCOPE
    assert mcp_consent.MEMORY_READ_SCOPE in result_event["granted_scopes"]
    assert result_event["source_digests"] == [payload["results"][0]["sha256"]]


def test_persisted_name_grant_cannot_access_memory_without_fresh_decision(tmp_path, monkeypatch):
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "memory.md").write_text("memory", encoding="utf-8")
    monkeypatch.setenv("DEVFRAME_OBSIDIAN_MEMORY_ROOT", str(vault))
    monkeypatch.setenv("DEVFRAME_OBSIDIAN_MEMORY_ALLOWLIST", '["memory.md"]')
    mcp_consent._reset_for_tests()
    mcp_consent.register_connection("s1", "Codex", runtime_dir=runtime)
    mcp_consent.request_scope("s1", mcp_consent.MEMORY_READ_SCOPE)
    mcp_consent.decide("s1", "allow_always", runtime_dir=runtime)
    mcp_consent._reset_for_tests()
    returning = mcp_consent.register_connection("s2", "Codex", runtime_dir=runtime)
    assert returning["status"] == "authorized"

    response, _ = handle_mcp_jsonrpc(
        {
            "jsonrpc": "2.0",
            "id": 10,
            "method": "tools/call",
            "params": {
                "name": "search_obsidian_memory",
                "arguments": {
                    "projectId": "demo",
                    "query": "memory",
                    "relativePaths": ["memory.md"],
                },
            },
        },
        runtime_dir=runtime,
        session_id="s2",
    )
    assert response["result"]["isError"] is True
    assert "fresh_memory_authorization_required" in response["result"]["content"][0]["text"]


def test_memory_scope_is_bound_to_project_and_config(tmp_path, monkeypatch):
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "public.md").write_text(
        "---\nproject_id: public-project\n---\npublic memory",
        encoding="utf-8",
    )
    (vault / "private.md").write_text(
        "---\nproject_id: secret-project\n---\nconfidential memory",
        encoding="utf-8",
    )
    monkeypatch.setenv("DEVFRAME_OBSIDIAN_MEMORY_ROOT", str(vault))
    monkeypatch.setenv(
        "DEVFRAME_OBSIDIAN_MEMORY_ALLOWLIST",
        '["public.md", "private.md"]',
    )
    mcp_consent._reset_for_tests()
    mcp_consent.register_connection("s-bound", "Codex", runtime_dir=runtime)

    first, _ = handle_mcp_jsonrpc(
        {
            "jsonrpc": "2.0",
            "id": 12,
            "method": "tools/call",
            "params": {
                "name": "search_obsidian_memory",
                "arguments": {
                    "projectId": "public-project",
                    "query": "public",
                    "relativePaths": ["public.md"],
                },
            },
        },
        runtime_dir=runtime,
        session_id="s-bound",
    )
    assert "authorization_pending" in first["result"]["content"][0]["text"]
    mcp_consent.decide("s-bound", "allow_once", runtime_dir=runtime)
    public_payload = _call(
        "search_obsidian_memory",
        {
            "projectId": "public-project",
            "query": "public",
            "relativePaths": ["public.md"],
        },
        runtime,
        "s-bound",
    )
    assert public_payload["results"]

    switched, _ = handle_mcp_jsonrpc(
        {
            "jsonrpc": "2.0",
            "id": 13,
            "method": "tools/call",
            "params": {
                "name": "search_obsidian_memory",
                "arguments": {
                    "projectId": "secret-project",
                    "query": "confidential",
                    "relativePaths": ["private.md"],
                },
            },
        },
        runtime_dir=runtime,
        session_id="s-bound",
    )
    assert switched["result"]["isError"] is True
    assert "memory_scope_required" in switched["result"]["content"][0]["text"]


def test_memory_tool_fails_closed_when_audit_cannot_be_written(tmp_path, monkeypatch):
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    (runtime / "mcp-audit.jsonl").mkdir()
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "memory.md").write_text("memory", encoding="utf-8")
    monkeypatch.setenv("DEVFRAME_OBSIDIAN_MEMORY_ROOT", str(vault))
    monkeypatch.setenv("DEVFRAME_OBSIDIAN_MEMORY_ALLOWLIST", '["memory.md"]')
    mcp_consent._reset_for_tests()
    _authorize_scope("s-audit", runtime, mcp_consent.MEMORY_READ_SCOPE)
    response, _ = handle_mcp_jsonrpc(
        {
            "jsonrpc": "2.0",
            "id": 11,
            "method": "tools/call",
            "params": {
                "name": "search_obsidian_memory",
                "arguments": {
                    "projectId": "demo",
                    "query": "memory",
                    "relativePaths": ["memory.md"],
                },
            },
        },
        runtime_dir=runtime,
        session_id="s-audit",
    )
    assert response["result"]["isError"] is True
    assert "memory_audit_unavailable" in response["result"]["content"][0]["text"]


def test_memory_proposal_is_thread_bound_and_does_not_write_before_approval(tmp_path, monkeypatch):
    from control_plane.writeback import WritebackError, resolve_writeback_proposal

    runtime = tmp_path / "runtime"
    runtime.mkdir()
    vault = tmp_path / "vault"
    vault.mkdir()
    monkeypatch.setenv("DEVFRAME_OBSIDIAN_MEMORY_ROOT", str(vault))
    monkeypatch.setenv("DEVFRAME_OBSIDIAN_MEMORY_ALLOWLIST", '["memory.md"]')
    mcp_consent._reset_for_tests()
    _authorize_scope("s-propose", runtime, mcp_consent.MEMORY_PROPOSE_SCOPE)
    payload = _call(
        "propose_obsidian_memory",
        {
            "projectId": "demo",
            "title": "Review lesson",
            "lesson": "Memory must cite its source.",
            "memoryType": "lesson",
            "sourceRefs": ["run-1/review.yaml"],
        },
        runtime,
        "s-propose",
    )
    assert payload["threadId"] == "s-propose"
    assert str(vault) not in str(payload)
    assert not (vault / payload["relativePath"]).exists()
    with pytest.raises(WritebackError, match="thread mismatch"):
        resolve_writeback_proposal(
            runtime, payload["requestId"], "approve", expected_thread_id="other"
        )
    resolved = resolve_writeback_proposal(
        runtime, payload["requestId"], "approve", expected_thread_id="s-propose"
    )
    assert resolved["applied"] is True
    assert str(vault) not in str(resolved)


def test_memory_search_real_http_round_trip(tmp_path, monkeypatch):
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "memory.md").write_text(
        "---\nproject_id: demo\n---\n# 记忆\n模型记忆永久存储需要可追溯来源。",
        encoding="utf-8",
    )
    monkeypatch.setenv("DEVFRAME_OBSIDIAN_MEMORY_ROOT", str(vault))
    monkeypatch.setenv("DEVFRAME_OBSIDIAN_MEMORY_ALLOWLIST", '["memory.md"]')
    mcp_consent._reset_for_tests()
    server = build_dashboard_server(runtime_dir=runtime, port=0, refresh_seconds=0)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()

    def post(base_url, path, payload, headers=None):
        request = Request(
            f"{base_url}{path}",
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json", "Accept": "application/json", **(headers or {})},
            method="POST",
        )
        with urlopen(request, timeout=5) as response:
            return response, json.loads(response.read().decode("utf-8"))

    try:
        base_url = f"http://127.0.0.1:{server.server_address[1]}"
        response, _ = post(
            base_url,
            "/mcp",
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {"clientInfo": {"name": "Codex"}},
            },
        )
        sid = response.headers["MCP-Session-Id"]
        _, pending = post(
            base_url,
            "/mcp",
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {
                    "name": "search_obsidian_memory",
                    "arguments": {
                        "projectId": "demo",
                        "query": "永久存储",
                        "relativePaths": ["memory.md"],
                    },
                },
            },
            {"MCP-Session-Id": sid},
        )
        assert pending["result"]["isError"] is True
        _, decided = post(
            base_url,
            "/api/mcp/connections/decide",
            {"connectionId": sid, "decision": "allow_once"},
        )
        assert mcp_consent.MEMORY_READ_SCOPE in decided["connection"]["scopes"]
        _, result = post(
            base_url,
            "/mcp",
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {
                    "name": "search_obsidian_memory",
                    "arguments": {
                        "projectId": "demo",
                        "query": "永久存储",
                        "relativePaths": ["memory.md"],
                    },
                },
            },
            {"MCP-Session-Id": sid},
        )
        assert result["result"]["isError"] is False
        assert "永久存储" in result["result"]["content"][0]["text"]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
