"""Tests for MCP connect-time consent + connection governance (Phase 0)."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from threading import Thread
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import control_plane.mcp_consent as mcp_consent  # noqa: E402
from control_plane.dashboard import build_dashboard_server  # noqa: E402


@pytest.fixture(autouse=True)
def _isolate_devframe_mcp_token(monkeypatch):
    # The suite must not inherit an operator-level DEVFRAME_MCP_TOKEN from the host.
    monkeypatch.delenv("DEVFRAME_MCP_TOKEN", raising=False)


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
    client = {"name": "ChatGPT", "title": "Codex", "version": "1.0"}
    mcp_consent.register_connection(
        "s1",
        client,
        runtime_dir=tmp_path,
        trust_secret="loopback-token",
    )
    mcp_consent.decide("s1", "allow_always", runtime_dir=tmp_path)
    assert mcp_consent.is_authorized("s1") is True
    mcp_consent.decide("s1", "revoke", runtime_dir=tmp_path)
    assert mcp_consent.is_authorized("s1") is False
    # A new session from the same client must NOT auto-authorize after revoke.
    mcp_consent._reset_for_tests()
    conn = mcp_consent.register_connection(
        "s2",
        client,
        runtime_dir=tmp_path,
        trust_secret="loopback-token",
    )
    assert conn["status"] == "pending"


def test_allow_always_auto_authorizes_returning_client(tmp_path):
    client = {"name": "ChatGPT", "title": "Codex", "version": "1.0"}
    mcp_consent.register_connection(
        "s1",
        client,
        runtime_dir=tmp_path,
        trust_secret="loopback-token",
    )
    mcp_consent.decide("s1", "allow_always", runtime_dir=tmp_path)
    # Simulate a reconnect (new session id, same client) after a restart.
    mcp_consent._reset_for_tests()
    conn = mcp_consent.register_connection(
        "s2",
        client,
        runtime_dir=tmp_path,
        trust_secret="loopback-token",
    )
    assert conn["status"] == "authorized"


def test_allow_always_requires_token_bound_client_identity(tmp_path):
    mcp_consent.register_connection(
        "s1",
        {"name": "Codex", "version": "0.143.0"},
        runtime_dir=tmp_path,
    )

    with pytest.raises(mcp_consent.ConsentError, match="trust-bound"):
        mcp_consent.decide("s1", "allow_always", runtime_dir=tmp_path)


def test_allow_always_requires_complete_client_info_even_with_token(tmp_path):
    mcp_consent.register_connection(
        "s1",
        "codex-mcp-client",
        runtime_dir=tmp_path,
        trust_secret="loopback-token",
    )

    with pytest.raises(mcp_consent.ConsentError, match="complete trust-bound"):
        mcp_consent.decide("s1", "allow_always", runtime_dir=tmp_path)


def test_allow_always_survives_client_upgrade_but_rejects_other_name_or_token(
    tmp_path,
):
    trusted = {"name": "codex-mcp-client", "title": "Codex", "version": "0.143.0"}
    mcp_consent.register_connection(
        "s1",
        trusted,
        runtime_dir=tmp_path,
        trust_secret="token-a",
    )
    mcp_consent.decide("s1", "allow_always", runtime_dir=tmp_path)
    mcp_consent._reset_for_tests()

    upgraded_client = mcp_consent.register_connection(
        "s2",
        {
            **trusted,
            "title": "Codex Desktop",
            "version": "0.146.0-alpha.3.1",
        },
        runtime_dir=tmp_path,
        trust_secret="token-a",
    )
    changed_token = mcp_consent.register_connection(
        "s3",
        trusted,
        runtime_dir=tmp_path,
        trust_secret="token-b",
    )
    changed_name = mcp_consent.register_connection(
        "s4",
        {**trusted, "name": "other-mcp-client"},
        runtime_dir=tmp_path,
        trust_secret="token-a",
    )

    assert upgraded_client["status"] == "authorized"
    assert upgraded_client["fingerprint_version"] == 3
    assert changed_token["status"] == "pending"
    assert changed_name["status"] == "pending"


def test_legacy_exact_version_grant_is_not_silently_promoted(tmp_path):
    client = {"name": "codex-mcp-client", "title": "Codex", "version": "0.143.0"}
    grant_key = mcp_consent.fingerprint(client, trust_secret="token-a")
    (tmp_path / "mcp-connection-grants.json").write_text(
        json.dumps(
            {
                grant_key: {
                    "decision": "allow_always",
                    "client_info": client,
                    "fingerprint_version": 2,
                    "revoked": False,
                }
            }
        ),
        encoding="utf-8",
    )

    conn = mcp_consent.register_connection(
        "s1",
        client,
        runtime_dir=tmp_path,
        trust_secret="token-a",
    )

    assert conn["status"] == "pending"


def test_client_identity_is_control_free_and_bounded_by_utf8_bytes(tmp_path):
    client = {
        "name": "codex-\n" + ("界" * 300),
        "title": "Codex\rDesktop",
        "version": "0.143.0\x7f",
    }

    conn = mcp_consent.register_connection(
        "s1",
        client,
        runtime_dir=tmp_path,
        trust_secret="token-a",
    )

    for value in conn["client_info"].values():
        assert len(value.encode("utf-8")) <= 256
        assert all(ord(character) >= 32 and ord(character) != 127 for character in value)


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


@pytest.mark.parametrize("method", ["GET", "DELETE"])
def test_streamable_http_declines_unsupported_session_stream_with_allow_header(
    tmp_path,
    method,
):
    runtime_dir = tmp_path / "runtime"
    runtime_dir.mkdir()
    server = build_dashboard_server(runtime_dir=runtime_dir, port=0, refresh_seconds=0)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base_url = f"http://127.0.0.1:{server.server_address[1]}"
        _, headers, _ = _post(
            base_url,
            "/mcp",
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "Codex"},
                },
            },
        )
        request = Request(
            f"{base_url}/mcp",
            headers={
                "Accept": "text/event-stream",
                "MCP-Session-Id": _header(headers, "MCP-Session-Id"),
            },
            method=method,
        )

        with pytest.raises(HTTPError) as captured:
            urlopen(request, timeout=5)

        assert captured.value.code == 405
        assert _header(dict(captured.value.headers), "Allow") == "POST"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_streamable_http_rejects_stale_session_then_family_grant_reconnects(
    tmp_path,
    monkeypatch,
):
    token = "loopback-token"
    monkeypatch.setenv("DEVFRAME_MCP_TOKEN", token)
    runtime_dir = tmp_path / "runtime"
    runtime_dir.mkdir()
    server = build_dashboard_server(runtime_dir=runtime_dir, port=0, refresh_seconds=0)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base_url = f"http://127.0.0.1:{server.server_address[1]}"
        auth = {"Authorization": f"Bearer {token}"}
        client = {
            "name": "codex-mcp-client",
            "title": "Codex",
            "version": "0.143.0",
        }
        _, headers, _ = _post(
            base_url,
            "/mcp",
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": client,
                },
            },
            headers=auth,
        )
        stale_session_id = _header(headers, "MCP-Session-Id")
        mcp_consent.decide(
            stale_session_id,
            "allow_always",
            runtime_dir=runtime_dir,
        )
        mcp_consent._reset_for_tests()

        with pytest.raises(HTTPError) as captured:
            _post(
                base_url,
                "/mcp",
                {
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "tools/call",
                    "params": {"name": "server_config", "arguments": {}},
                },
                headers={**auth, "MCP-Session-Id": stale_session_id},
            )

        assert captured.value.code == 404

        _, reconnect_headers, _ = _post(
            base_url,
            "/mcp",
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {
                        **client,
                        "title": "Codex Desktop",
                        "version": "0.146.0-alpha.3.1",
                    },
                },
            },
            headers=auth,
        )
        reconnect_session_id = _header(reconnect_headers, "MCP-Session-Id")
        _, _, ok = _post(
            base_url,
            "/mcp",
            {
                "jsonrpc": "2.0",
                "id": 4,
                "method": "tools/call",
                "params": {"name": "server_config", "arguments": {}},
            },
            headers={**auth, "MCP-Session-Id": reconnect_session_id},
        )

        assert ok["result"]["isError"] is False
        assert mcp_consent.get_connection(reconnect_session_id)["status"] == "authorized"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


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
        server.server_close()
        thread.join(timeout=5)
