"""Hermetic tests for the governed ACP session driver (M2, slice 1).

Policy is unit-tested pure; the end-to-end path drives a MOCK ACP agent (no
OpenCode, no tokens) that issues a normal permission request, a high-risk
permission request, and an fs/write_text_file request, then ends the turn. We
assert the gate policy decisions, that the file write passed through the seam,
and that the session was recorded via the team runtime.
"""
from __future__ import annotations

import sys
import textwrap

from control_plane.acp_session import (
    GovernedAcpSession,
    PermissionDecision,
    default_permission_policy,
    is_high_risk,
)
from control_plane.team_runtime import build_team_runtime_view

ALLOW_OPTS = [
    {"optionId": "allow-once", "kind": "allow_once", "name": "Allow"},
    {"optionId": "reject-once", "kind": "reject_once", "name": "Reject"},
]


def test_policy_allows_normal_edit():
    decision = default_permission_policy({"title": "edit file a.py"}, ALLOW_OPTS)
    assert decision.allowed is True
    assert decision.option_id == "allow-once"


def test_policy_holds_high_risk():
    decision = default_permission_policy({"title": "delete the database", "command": "rm -rf"}, ALLOW_OPTS)
    assert decision.allowed is False
    assert decision.option_id == "reject-once"


def test_policy_holds_when_no_recognizable_allow():
    decision = default_permission_policy({"title": "edit"}, [{"optionId": "weird", "kind": "?", "name": "?"}])
    assert decision.allowed is False


def test_is_high_risk_keywords():
    assert is_high_risk({"command": "git push --force"})
    assert is_high_risk({"title": "read secret token"})
    assert not is_high_risk({"title": "append a line to notes.md"})


MOCK_ACP_AGENT = textwrap.dedent(
    """
    import json, sys

    def send(msg):
        sys.stdout.write(json.dumps(msg) + "\\n"); sys.stdout.flush()

    def call(method, params, rid):
        send({"jsonrpc": "2.0", "id": rid, "method": method, "params": params})
        # wait for the client's response with this id
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue
            m = json.loads(line)
            if m.get("id") == rid and ("result" in m or "error" in m):
                return m.get("result")

    pending_prompt_id = None
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        msg = json.loads(line)
        method = msg.get("method"); mid = msg.get("id")
        if method == "initialize":
            send({"jsonrpc": "2.0", "id": mid, "result": {"protocolVersion": 1, "agentCapabilities": {}}})
        elif method == "session/new":
            send({"jsonrpc": "2.0", "id": mid, "result": {"sessionId": "sess-mock-acp"}})
        elif method == "session/prompt":
            sid = msg.get("params", {}).get("sessionId")
            # streamed update (should surface as workflow-acp-stream)
            send({"jsonrpc": "2.0", "method": "session/update", "params": {
                "sessionId": sid, "update": {"sessionUpdate": "tool_call",
                "content": {"type": "text", "text": "editing"}}}})
            # 1) normal permission request (server -> client) using a fresh id
            normal = call("session/request_permission", {"sessionId": sid,
                "toolCall": {"title": "edit notes.md"}, "options": [
                    {"optionId": "allow-once", "kind": "allow_once", "name": "Allow"},
                    {"optionId": "reject-once", "kind": "reject_once", "name": "Reject"}]}, 9001)
            # 2) high-risk permission request
            risky = call("session/request_permission", {"sessionId": sid,
                "toolCall": {"title": "delete production data", "command": "rm -rf /"}, "options": [
                    {"optionId": "allow-once", "kind": "allow_once", "name": "Allow"},
                    {"optionId": "reject-once", "kind": "reject_once", "name": "Reject"}]}, 9002)
            # 3) fs write through the client seam (only if normal was allowed)
            call("fs/write_text_file", {"sessionId": sid, "path": "notes.md",
                "content": "written via acp seam\\n"}, 9003)
            send({"jsonrpc": "2.0", "id": mid, "result": {"stopReason": "end_turn"}})
        elif method == "shutdown":
            send({"jsonrpc": "2.0", "id": mid, "result": {}}); break
        else:
            send({"jsonrpc": "2.0", "id": mid, "error": {"code": -32601, "message": "nope"}})
    """
)


def test_governed_session_enforces_gates_and_records(tmp_path):
    script = tmp_path / "mock_acp_agent.py"
    script.write_text(MOCK_ACP_AGENT, encoding="utf-8")
    workdir = tmp_path / "work"
    workdir.mkdir()
    runtime = tmp_path / "runtime"

    session = GovernedAcpSession(
        command=[sys.executable, str(script)],
        runtime_dir=runtime,
        cwd=workdir,
    )
    result = session.run("edit notes and try something risky", run_id="acp-run-1", prompt_timeout=30.0)

    assert result.stop_reason == "end_turn"
    # Two permission decisions: normal allowed, risky held.
    assert len(result.permission_decisions) == 2
    assert result.permission_decisions[0].allowed is True
    assert result.permission_decisions[1].allowed is False
    assert result.held_high_risk == 1

    # The fs write passed through the governed seam and landed in cwd.
    assert (workdir / "notes.md").read_text(encoding="utf-8") == "written via acp seam\n"

    # The session + permission decisions were recorded as real team events.
    view = build_team_runtime_view(runtime)
    kinds = {e["kind"] for e in view["event_log"]}
    assert "workflow-acp-session" in kinds
    assert "workflow-permission" in kinds
    # Streamed activity surfaced as a low-noise summary event.
    assert "workflow-acp-stream" in kinds
    assert len(result.updates) >= 1


def test_fs_write_confined_to_cwd(tmp_path):
    workdir = tmp_path / "work"
    workdir.mkdir()
    session = GovernedAcpSession(runtime_dir=tmp_path / "rt", cwd=workdir)
    # Attempt to escape the cwd: handler must refuse (no write outside).
    session._handle_fs_write({"path": "../escape.txt", "content": "x"})
    assert not (tmp_path / "escape.txt").exists()
