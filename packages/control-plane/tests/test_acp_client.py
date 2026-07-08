"""Hermetic tests for the ACP transport seam (M2, slice 0).

Drives `AcpConnection` against a MOCK ACP agent (a tiny python script that speaks
newline-delimited JSON-RPC 2.0 over stdio). No real coding agent, no tokens. The
mock implements just enough of ACP to verify the transport + handshake:
- initialize -> protocolVersion + agentCapabilities
- session/new -> sessionId
- session/prompt -> emits a streamed session/update notification, then returns
  a stopReason result
- an unknown method -> JSON-RPC error (verifies error propagation)
"""
from __future__ import annotations

import sys
import textwrap

import pytest

from control_plane.acp_client import ACP_PROTOCOL_VERSION, AcpConnection, AcpError

MOCK_AGENT = textwrap.dedent(
    """
    import json, sys

    def send(msg):
        sys.stdout.write(json.dumps(msg) + "\\n")
        sys.stdout.flush()

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        msg = json.loads(line)
        method = msg.get("method")
        mid = msg.get("id")
        if method == "initialize":
            send({"jsonrpc": "2.0", "id": mid, "result": {
                "protocolVersion": msg.get("params", {}).get("protocolVersion"),
                "agentCapabilities": {"promptCapabilities": {"image": False}},
            }})
        elif method == "session/new":
            send({"jsonrpc": "2.0", "id": mid, "result": {"sessionId": "sess-mock-1"}})
        elif method == "session/prompt":
            # Stream one update notification, then return a stop reason.
            send({"jsonrpc": "2.0", "method": "session/update", "params": {
                "sessionId": msg.get("params", {}).get("sessionId"),
                "update": {"sessionUpdate": "agent_message_chunk",
                           "content": {"type": "text", "text": "working"}},
            }})
            send({"jsonrpc": "2.0", "id": mid, "result": {"stopReason": "end_turn"}})
        elif method == "shutdown":
            send({"jsonrpc": "2.0", "id": mid, "result": {}})
            break
        else:
            send({"jsonrpc": "2.0", "id": mid, "error": {"code": -32601, "message": "method not found"}})
    """
)


def _spawn_mock(tmp_path):
    script = tmp_path / "mock_acp_agent.py"
    script.write_text(MOCK_AGENT, encoding="utf-8")
    conn = AcpConnection.spawn([sys.executable, str(script)])
    conn.start()
    return conn


def test_initialize_handshake(tmp_path):
    conn = _spawn_mock(tmp_path)
    try:
        result = conn.initialize(client_capabilities={"fs": {"readTextFile": True}})
        assert result["protocolVersion"] == ACP_PROTOCOL_VERSION
        assert "agentCapabilities" in result
    finally:
        conn.close()


def test_session_new_and_prompt_with_streamed_update(tmp_path):
    conn = _spawn_mock(tmp_path)
    updates = []
    conn.on_notification("session/update", lambda params: updates.append(params))
    try:
        conn.initialize()
        session_id = conn.new_session(cwd=str(tmp_path))
        assert session_id == "sess-mock-1"
        result = conn.prompt(session_id=session_id, text="do something", timeout=30.0)
        assert result["stopReason"] == "end_turn"
        # The streamed notification was dispatched on the reader thread.
        assert any(u.get("sessionId") == session_id for u in updates)
        assert updates[0]["update"]["sessionUpdate"] == "agent_message_chunk"
    finally:
        conn.close()


def test_error_propagation(tmp_path):
    conn = _spawn_mock(tmp_path)
    try:
        conn.initialize()
        with pytest.raises(AcpError):
            conn.request("does/not/exist", {}, timeout=10.0)
    finally:
        conn.close()


def test_request_timeout_when_agent_silent(tmp_path):
    # Agent that reads but never replies -> request must time out, not hang.
    script = tmp_path / "silent_agent.py"
    script.write_text("import sys\nfor _ in sys.stdin:\n    pass\n", encoding="utf-8")
    conn = AcpConnection.spawn([sys.executable, str(script)])
    conn.start()
    try:
        with pytest.raises(AcpError):
            conn.request("initialize", {"protocolVersion": 1}, timeout=1.0)
    finally:
        conn.close()


def test_no_embedded_newlines_in_framed_messages(tmp_path):
    # A prompt containing newlines must still be one framed line (no corruption).
    conn = _spawn_mock(tmp_path)
    try:
        conn.initialize()
        session_id = conn.new_session(cwd=str(tmp_path))
        result = conn.prompt(session_id=session_id, text="line1\nline2\nline3", timeout=30.0)
        assert result["stopReason"] == "end_turn"
    finally:
        conn.close()


def test_spawn_requires_command():
    with pytest.raises(ValueError):
        AcpConnection.spawn([])
