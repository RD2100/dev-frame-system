import json
import socket
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPStatus, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import pytest

from control_plane.cli import main as devframe_cli_main
from control_plane.mcp_live_probe import (
    _header_value,
    mcp_live_probe,
    render_mcp_live_probe_json,
    render_mcp_live_probe_text,
)
from control_plane.visual_state import validate_web_ai_session_summary


class _FakeMcpHandler(BaseHTTPRequestHandler):
    server_version = "DevFrameFakeMCP/0.1"

    def log_message(self, format, *args):  # noqa: A002
        pass

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length).decode("utf-8", errors="replace") if length else ""
        try:
            payload = json.loads(body) if body else {}
        except json.JSONDecodeError:
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": {"code": -32700, "message": "parse error"}})
            return

        response: dict[str, Any] = {"jsonrpc": "2.0", "id": payload.get("id")}
        method = payload.get("method")

        if getattr(self.server, "mcp_auth_required", False):
            self._send_json(HTTPStatus.UNAUTHORIZED, {"error": {"code": -32001, "message": "auth required"}})
            return
        if getattr(self.server, "mcp_protocol_error", False):
            self._send_json(HTTPStatus.OK, {"error": {"code": -32700, "message": "parse error"}})
            return

        if method == "initialize":
            self.server.mcp_session_id = str(payload.get("id", "1"))
            response["result"] = {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": "fake-mcp", "version": "0.1"},
            }
            self._send_json(HTTPStatus.OK, response, session_id=self.server.mcp_session_id)
            return

        if getattr(self.server, "mcp_require_session", False):
            expected = getattr(self.server, "mcp_session_id", None)
            actual = self.headers.get("MCP-Session-Id")
            if not expected or actual != expected:
                self._send_json(
                    HTTPStatus.BAD_REQUEST,
                    {"error": {"code": -32000, "message": "No valid MCP session"}},
                )
                return

        if method == "tools/list":
            response["result"] = {"tools": getattr(self.server, "mcp_tools", [])}
            self._send_json(HTTPStatus.OK, response)
            return

        if method == "tools/call":
            tool_name = (payload.get("params") or {}).get("name")
            self.server.mcp_tool_calls.append(tool_name)
            allowed = getattr(self.server, "mcp_allowed_tools", set())
            if tool_name not in allowed:
                response["error"] = {"code": -32601, "message": f"tool not found: {tool_name}"}
            else:
                response["result"] = {
                    "content": [{"type": "text", "text": f"ok:{tool_name}"}],
                    "isError": False,
                }
            self._send_json(HTTPStatus.OK, response)
            return

        response["error"] = {"code": -32601, "message": f"method not found: {method}"}
        self._send_json(HTTPStatus.OK, response)

    def _send_json(self, status: HTTPStatus, payload: dict[str, Any], session_id: str | None = None) -> None:
        data = json.dumps(payload, ensure_ascii=True).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        if session_id:
            self.send_header("Mcp-Session-Id", session_id)
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)


def build_fake_mcp_server(
    tools=None,
    allowed_tools=None,
    auth_required=False,
    protocol_error=False,
    require_session=False,
):
    server = ThreadingHTTPServer(("127.0.0.1", 0), _FakeMcpHandler)
    server.mcp_tools = tools or [{"name": "server_config", "description": "fake server config", "inputSchema": {}}]
    server.mcp_allowed_tools = allowed_tools or {t["name"] for t in server.mcp_tools}
    server.mcp_tool_calls = []
    server.mcp_session_id = None
    server.mcp_auth_required = auth_required
    server.mcp_protocol_error = protocol_error
    server.mcp_require_session = require_session
    return server


class FakeMcpServer:
    def __init__(self, **kwargs):
        self.server = build_fake_mcp_server(**kwargs)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        time.sleep(0.05)
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"

    def close(self):
        self.server.shutdown()
        self.server.server_close()


def test_live_check_initialize_and_tools_list_succeeds():
    server = FakeMcpServer()
    try:
        probe = mcp_live_probe(server.url, provider="codexpro", project_id="demo")

        assert probe["status"] == "live_ok"
        assert probe["health"] == "ready"
        assert "server_config" in probe["tool_names"]
        assert probe["session_summary"]["native_refs"]["runtime"] == "mcp-live-probe"
        assert probe["session_summary"]["status"] == "active"
        assert probe["session_summary"]["tool_calls"][0]["status"] == "completed"
        assert probe["session_summary"]["provider"] == "codexpro"
        assert probe["session_summary"]["project_id"] == "demo"
        validate_web_ai_session_summary(probe["session_summary"])
    finally:
        server.close()


def test_header_value_reads_session_id_case_insensitively():
    assert _header_value({"Mcp-Session-Id": "a"}, "MCP-Session-Id") == "a"
    assert _header_value({"mcp-session-id": "b"}, "MCP-Session-Id") == "b"
    assert _header_value({"MCP-SESSION-ID": "c"}, "mcp-session-id") == "c"


def test_live_check_preserves_mixed_case_session_header():
    server = FakeMcpServer(require_session=True)
    try:
        probe = mcp_live_probe(server.url, provider="codexpro", project_id="demo")

        assert probe["status"] == "live_ok"
        assert "server_config" in probe["tool_names"]
        validate_web_ai_session_summary(probe["session_summary"])
    finally:
        server.close()


def test_live_check_auth_required():
    server = FakeMcpServer(auth_required=True)
    try:
        probe = mcp_live_probe(server.url, provider="codexpro")

        assert probe["status"] == "auth_required"
        assert probe["health"] == "needs_login"
        assert "authentication required" in probe["message"]
    finally:
        server.close()


def test_live_check_unavailable_connection_refused():
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    probe = mcp_live_probe(f"http://127.0.0.1:{port}", provider="codexpro")

    assert probe["status"] == "unavailable"


def test_live_check_protocol_error():
    server = FakeMcpServer(protocol_error=True)
    try:
        probe = mcp_live_probe(server.url, provider="codexpro")

        assert probe["status"] == "protocol_error"
        assert "protocol error" in probe["message"]
    finally:
        server.close()


def test_live_check_unsafe_endpoint_rejected():
    with pytest.raises(ValueError, match="credentials, query strings, or fragments"):
        mcp_live_probe("https://token@example.test/mcp?secret=1", provider="codexpro")


def test_live_check_safe_tool_call():
    server = FakeMcpServer(
        tools=[{"name": "server_config", "description": "fake", "inputSchema": {}}]
    )
    try:
        probe = mcp_live_probe(server.url, provider="devspace", tool="server_config")

        assert probe["status"] == "live_ok"
        assert probe["tool_called"] == "server_config"
        assert probe["session_summary"]["tool_names"] == ["server_config"]
    finally:
        server.close()


def test_live_check_unsafe_tool_blocked():
    server = FakeMcpServer()
    try:
        probe = mcp_live_probe(server.url, provider="devspace", tool="evil_tool")

        assert probe["status"] == "blocked"
        assert "not in the safe-tool allowlist" in probe["message"]
    finally:
        server.close()


def test_live_check_cli_text_format(monkeypatch, capsys):
    server = FakeMcpServer()
    try:
        monkeypatch.setattr(sys, "argv", [
            "devframe", "web-ai", "live-check", "codexpro",
            "--endpoint", server.url,
            "--project", "demo",
        ])
        exit_code = devframe_cli_main()
        output = capsys.readouterr().out

        assert exit_code == 0
        assert "MCP Live Probe" in output
        assert "live_ok" in output
        assert "demo" in output
    finally:
        server.close()


def test_live_check_cli_json_format(monkeypatch, capsys):
    server = FakeMcpServer()
    try:
        monkeypatch.setattr(sys, "argv", [
            "devframe", "web-ai", "live-check", "codexpro",
            "--endpoint", server.url,
            "--format", "json",
        ])
        exit_code = devframe_cli_main()
        data = json.loads(capsys.readouterr().out)

        assert exit_code == 0
        assert data["status"] == "live_ok"
        assert data["session_summary"]["provider"] == "codexpro"
        assert data["session_summary"]["native_refs"]["runtime"] == "mcp-live-probe"
    finally:
        server.close()


def test_live_check_cli_session_json_format(monkeypatch, capsys):
    server = FakeMcpServer()
    try:
        monkeypatch.setattr(sys, "argv", [
            "devframe", "web-ai", "live-check", "devspace",
            "--endpoint", server.url,
            "--format", "session-json",
        ])
        exit_code = devframe_cli_main()
        session = json.loads(capsys.readouterr().out)

        assert exit_code == 0
        assert session["provider"] == "devspace"
        assert session["native_refs"]["runtime"] == "mcp-live-probe"
        assert "tool_names" in session
        validate_web_ai_session_summary(session)
    finally:
        server.close()


def test_live_check_cli_returns_nonzero_on_failure(monkeypatch, capsys):
    server = FakeMcpServer(auth_required=True)
    try:
        monkeypatch.setattr(sys, "argv", [
            "devframe", "web-ai", "live-check", "codexpro",
            "--endpoint", server.url,
        ])
        exit_code = devframe_cli_main()
        output = capsys.readouterr().out

        assert exit_code == 1
        assert "auth_required" in output
    finally:
        server.close()


def test_live_check_help_is_available(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["devframe", "web-ai", "live-check", "--help"])

    assert devframe_cli_main() == 0

    output = capsys.readouterr().out
    assert "Usage: devframe web-ai live-check codexpro|devspace --endpoint <url>" in output
    assert "--token" in output
    assert "--tool" in output
    assert "project_summary" in output


def test_live_check_cli_import_persists_session(monkeypatch, tmp_path):
    server = FakeMcpServer()
    try:
        runtime_dir = tmp_path / "runtime"
        monkeypatch.setattr(sys, "argv", [
            "devframe", "web-ai", "live-check", "codexpro",
            "--endpoint", server.url,
            "--project", "demo",
            "--import",
            "--runtime-dir", str(runtime_dir),
        ])
        exit_code = devframe_cli_main()

        assert exit_code == 0
        imported = list((runtime_dir / "web-ai-sessions").glob("*.json"))
        assert len(imported) == 1
        data = json.loads(imported[0].read_text(encoding="utf-8"))
        assert data["provider"] == "codexpro"
        assert data["native_refs"]["source_runtime"] == "mcp-live-probe"
        validate_web_ai_session_summary(data)
    finally:
        server.close()


def test_live_check_cli_json_import_stays_machine_readable(monkeypatch, capsys, tmp_path):
    server = FakeMcpServer()
    try:
        runtime_dir = tmp_path / "runtime"
        monkeypatch.setattr(sys, "argv", [
            "devframe", "web-ai", "live-check", "codexpro",
            "--endpoint", server.url,
            "--project", "demo",
            "--import",
            "--runtime-dir", str(runtime_dir),
            "--format", "json",
        ])
        exit_code = devframe_cli_main()
        output = capsys.readouterr().out
        data = json.loads(output)

        assert exit_code == 0
        assert data["status"] == "live_ok"
        assert data["imported_session_path"].endswith(".json")
        assert Path(data["imported_session_path"]).exists()
    finally:
        server.close()


def test_live_check_import_preserves_mcp_live_provenance(monkeypatch, tmp_path):
    server = FakeMcpServer()
    try:
        runtime_dir = tmp_path / "runtime"
        monkeypatch.setattr(sys, "argv", [
            "devframe", "web-ai", "live-check", "devspace",
            "--endpoint", server.url,
            "--project", "demo",
            "--tool", "server_config",
            "--import",
            "--runtime-dir", str(runtime_dir),
        ])
        exit_code = devframe_cli_main()

        assert exit_code == 0
        imported = list((runtime_dir / "web-ai-sessions").glob("*.json"))
        assert len(imported) == 1
        data = json.loads(imported[0].read_text(encoding="utf-8"))
        assert data["native_refs"]["source_runtime"] == "mcp-live-probe"
        assert data["native_refs"]["runtime"] == "mcp-live-probe"
        assert any(tc["name"] == "server_config" for tc in data["tool_calls"])
    finally:
        server.close()


def test_web_ai_help_lists_live_check(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["devframe", "web-ai", "--help"])

    assert devframe_cli_main() == 0

    output = capsys.readouterr().out
    assert "live-check" in output


def test_live_check_safe_tool_call_handoff_to_agent():
    server = FakeMcpServer(
        tools=[{"name": "handoff_to_agent", "description": "fake handoff", "inputSchema": {}}]
    )
    try:
        probe = mcp_live_probe(server.url, provider="codexpro", project_id="demo", tool="handoff_to_agent")

        assert probe["status"] == "live_ok"
        assert probe["tool_called"] == "handoff_to_agent"
        assert probe["session_summary"]["tool_names"] == ["handoff_to_agent"]
        assert probe["session_summary"]["tool_calls"][1]["status"] == "completed"
        validate_web_ai_session_summary(probe["session_summary"])
    finally:
        server.close()


def test_live_check_safe_tool_call_task_intake():
    server = FakeMcpServer(
        tools=[{"name": "task_intake", "description": "fake task intake", "inputSchema": {}}]
    )
    try:
        probe = mcp_live_probe(server.url, provider="codexpro", project_id="demo", tool="task_intake")

        assert probe["status"] == "live_ok"
        assert probe["tool_called"] is None
        assert probe["session_summary"]["tool_names"] == ["task_intake"]
        assert len(probe["session_summary"]["tool_calls"]) == 1
        assert any("tools/call skipped for side-effect safety" in note for note in probe["evidence_notes"])
        assert server.server.mcp_tool_calls == []
        validate_web_ai_session_summary(probe["session_summary"])
    finally:
        server.close()


def test_live_check_safe_tool_call_project_summary():
    server = FakeMcpServer(
        tools=[{"name": "project_summary", "description": "fake project summary", "inputSchema": {}}]
    )
    try:
        probe = mcp_live_probe(server.url, provider="codexpro", project_id="demo", tool="project_summary")

        assert probe["status"] == "live_ok"
        assert probe["tool_called"] == "project_summary"
        assert probe["session_summary"]["tool_names"] == ["project_summary"]
        assert probe["session_summary"]["tool_calls"][1]["name"] == "project_summary"
        assert probe["session_summary"]["tool_calls"][1]["status"] == "completed"
        assert server.server.mcp_tool_calls == ["project_summary"]
        validate_web_ai_session_summary(probe["session_summary"])
    finally:
        server.close()


def test_live_check_task_intake_missing_from_tools_list_does_not_call_tool():
    server = FakeMcpServer(
        tools=[{"name": "server_config", "description": "fake", "inputSchema": {}}]
    )
    try:
        probe = mcp_live_probe(server.url, provider="codexpro", project_id="demo", tool="task_intake")

        assert probe["status"] == "live_ok"
        assert probe["tool_called"] is None
        assert probe["session_summary"]["tool_names"] == ["server_config"]
        assert "requested tool task_intake not advertised by server" in probe["evidence_notes"]
        assert server.server.mcp_tool_calls == []
    finally:
        server.close()
