"""Tests for MCP connect-time consent + connection governance (Phase 0)."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from threading import Thread
from urllib.request import Request, urlopen

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import control_plane.mcp_consent as mcp_consent  # noqa: E402
from control_plane.dashboard import build_dashboard_server  # noqa: E402


def setup_function(_):
    mcp_consent._reset_for_tests()


def test_register_is_pending(tmp_path):
    conn = mcp_consent.register_connection("s1", "ChatGPT", runtime_dir=tmp_path)
    assert conn["status"] == "pending"
    assert mcp_consent.is_authorized("s1") is False


def test_allow_once_authorizes(tmp_path):
    mcp_consent.register_connection("s1", "ChatGPT", runtime_dir=tmp_path)
    mcp_consent.decide("s1", "allow_once", runtime_dir=tmp_path)
    assert mcp_consent.is_authorized("s1") is True


def test_deny_blocks(tmp_path):
    mcp_consent.register_connection("s1", "ChatGPT", runtime_dir=tmp_path)
    mcp_consent.decide("s1", "deny", runtime_dir=tmp_path)
    assert mcp_consent.is_authorized("s1") is False
    assert mcp_consent.get_connection("s1")["status"] == "denied"


def test_revoke_blocks_and_revokes_grant(tmp_path):
    mcp_consent.register_connection("s1", "ChatGPT", runtime_dir=tmp_path)
    mcp_consent.decide("s1", "allow_always", runtime_dir=tmp_path)
    assert mcp_consent.is_authorized("s1") is True
    mcp_consent.decide("s1", "revoke", runtime_dir=tmp_path)
    assert mcp_consent.is_authorized("s1") is False
    # A new session from the same client must NOT auto-authorize after revoke.
    mcp_consent._reset_for_tests()
    conn = mcp_consent.register_connection("s2", "ChatGPT", runtime_dir=tmp_path)
    assert conn["status"] == "pending"


def test_allow_always_auto_authorizes_returning_client(tmp_path):
    mcp_consent.register_connection("s1", "ChatGPT", runtime_dir=tmp_path)
    mcp_consent.decide("s1", "allow_always", runtime_dir=tmp_path)
    # Simulate a reconnect (new session id, same client) after a restart.
    mcp_consent._reset_for_tests()
    conn = mcp_consent.register_connection("s2", "ChatGPT", runtime_dir=tmp_path)
    assert conn["status"] == "authorized"


def test_invalid_decision_raises(tmp_path):
    mcp_consent.register_connection("s1", "ChatGPT", runtime_dir=tmp_path)
    with pytest.raises(mcp_consent.ConsentError):
        mcp_consent.decide("s1", "maybe", runtime_dir=tmp_path)


def test_decision_on_unknown_connection_raises(tmp_path):
    with pytest.raises(mcp_consent.ConsentError):
        mcp_consent.decide("ghost", "allow_once", runtime_dir=tmp_path)


def test_audit_log_records_events(tmp_path):
    mcp_consent.register_connection("s1", "ChatGPT", runtime_dir=tmp_path)
    mcp_consent.decide("s1", "allow_once", runtime_dir=tmp_path)
    audit = (tmp_path / "mcp-audit.jsonl").read_text(encoding="utf-8").strip().splitlines()
    events = [json.loads(line)["event"] for line in audit]
    assert "connect" in events
    assert "decision" in events


def _post(base_url, path, payload, headers=None):
    request = Request(
        f"{base_url}{path}",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "Accept": "application/json", **(headers or {})},
        method="POST",
    )
    with urlopen(request, timeout=5) as response:
        return response.status, dict(response.headers), json.loads(response.read().decode("utf-8"))


def _header(headers, name):
    expected = name.lower()
    for header_name, header_value in headers.items():
        if header_name.lower() == expected:
            return header_value
    return None


def test_dashboard_consent_flow_end_to_end(tmp_path):
    mcp_consent._reset_for_tests()
    runtime_dir = tmp_path / "runtime"
    runtime_dir.mkdir()
    server = build_dashboard_server(runtime_dir=runtime_dir, port=0, refresh_seconds=0)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base_url = f"http://127.0.0.1:{server.server_address[1]}"
        # 1. initialize -> get a session id
        _, headers, _ = _post(base_url, "/mcp", {
            "jsonrpc": "2.0", "id": 1, "method": "initialize",
            "params": {"protocolVersion": "2024-11-05", "capabilities": {}, "clientInfo": {"name": "ChatGPT"}},
        })
        sid = _header(headers, "MCP-Session-Id")
        assert sid

        # 2. tools/call before consent -> authorization_pending, no data
        _, _, pending = _post(base_url, "/mcp", {
            "jsonrpc": "2.0", "id": 2, "method": "tools/call",
            "params": {"name": "server_config", "arguments": {}},
        }, headers={"MCP-Session-Id": sid})
        assert pending["result"]["isError"] is True
        assert "authorization_pending" in pending["result"]["content"][0]["text"]

        # 3. the connection shows up as pending for the human
        with urlopen(f"{base_url}/api/mcp/connections", timeout=5) as response:
            conns = json.loads(response.read().decode("utf-8"))["connections"]
        assert any(c["connection_id"] == sid and c["status"] == "pending" for c in conns)

        # 4. human allows it
        status, _, decided = _post(base_url, "/api/mcp/connections/decide", {
            "connectionId": sid, "decision": "allow_once",
        })
        assert status == 200 and decided["connection"]["status"] == "authorized"

        # 5. tools/call now succeeds
        _, _, ok = _post(base_url, "/mcp", {
            "jsonrpc": "2.0", "id": 3, "method": "tools/call",
            "params": {"name": "server_config", "arguments": {}},
        }, headers={"MCP-Session-Id": sid})
        assert ok["result"]["isError"] is False
        assert "devframe-mcp" in ok["result"]["content"][0]["text"]
    finally:
        server.shutdown()
