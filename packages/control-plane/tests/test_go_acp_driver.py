"""Hermetic test for the opt-in ACP /go executor driver (M2 slice 2).

Runs a real `/go` agent with driver='acp' against a MOCK ACP agent (no OpenCode,
no tokens). The mock edits a file via fs/write_text_file and ends the turn; the
driver must synthesize an ExecutionReport, mark the agent passed, capture the
changed file (git), and record team events.
"""
from __future__ import annotations

import subprocess
import sys
import textwrap
from pathlib import Path

from control_plane.go_dispatch import run_go_dispatch
from control_plane.team_runtime import build_team_runtime_view

# Mock ACP agent: handshake, session, on prompt it writes target.py via the
# client's fs/write_text_file seam, then ends the turn.
MOCK_ACP_AGENT = textwrap.dedent(
    """
    import json, sys
    def send(m):
        sys.stdout.write(json.dumps(m) + "\\n"); sys.stdout.flush()
    def call(method, params, rid):
        send({"jsonrpc":"2.0","id":rid,"method":method,"params":params})
        for line in sys.stdin:
            line=line.strip()
            if not line: continue
            m=json.loads(line)
            if m.get("id")==rid and ("result" in m or "error" in m):
                return m.get("result")
    for line in sys.stdin:
        line=line.strip()
        if not line: continue
        msg=json.loads(line); method=msg.get("method"); mid=msg.get("id")
        if method=="initialize":
            send({"jsonrpc":"2.0","id":mid,"result":{"protocolVersion":1,"agentCapabilities":{}}})
        elif method=="session/new":
            send({"jsonrpc":"2.0","id":mid,"result":{"sessionId":"sess-driver"}})
        elif method=="session/prompt":
            sid=msg.get("params",{}).get("sessionId")
            call("fs/write_text_file", {"sessionId":sid,"path":"target.py","content":"x = 42\\n"}, 7001)
            send({"jsonrpc":"2.0","id":mid,"result":{"stopReason":"end_turn"}})
        elif method=="shutdown":
            send({"jsonrpc":"2.0","id":mid,"result":{}}); break
        else:
            send({"jsonrpc":"2.0","id":mid,"error":{"code":-32601,"message":"nope"}})
    """
)


def test_go_with_acp_driver_produces_report_and_records(tmp_path):
    project = tmp_path / "proj"
    project.mkdir()
    (project / "target.py").write_text("x = 0\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(project), "init", "-q"])
    subprocess.run(["git", "-C", str(project), "config", "user.email", "t@e.com"])
    subprocess.run(["git", "-C", str(project), "config", "user.name", "t"])
    subprocess.run(["git", "-C", str(project), "add", "."])
    subprocess.run(["git", "-C", str(project), "commit", "-q", "-m", "init"])

    script = tmp_path / "mock_acp_agent.py"
    script.write_text(MOCK_ACP_AGENT, encoding="utf-8")
    runtime = tmp_path / "runtime"

    result = run_go_dispatch(
        project,
        "edit target.py",
        runtime_dir=runtime,
        agents=1,
        targets=["target.py"],
        execute=True,
        driver="acp",
        acp_command=[sys.executable, str(script)],
        timeout_seconds=60,
    )

    assert result.driver == "acp"
    assert result.status == "passed"
    agent = result.agents[0]
    assert agent.worker_status in {"pass", "passed"}
    assert agent.session_id == "sess-driver"
    # The mock edited target.py via the governed fs seam; git sees the change.
    assert any("target.py" in cf for cf in agent.changed_files)
    assert (project / "target.py").read_text(encoding="utf-8") == "x = 42\n"

    # Team events recorded for the ACP session.
    view = build_team_runtime_view(runtime)
    kinds = {e["kind"] for e in view["event_log"]}
    assert "workflow-acp-session" in kinds
    assert {"task-created", "task-result"} <= kinds


def test_go_acp_driver_under_isolate(tmp_path):
    project = tmp_path / "proj"
    project.mkdir()
    (project / "target.py").write_text("x = 0\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(project), "init", "-q"])
    subprocess.run(["git", "-C", str(project), "config", "user.email", "t@e.com"])
    subprocess.run(["git", "-C", str(project), "config", "user.name", "t"])
    subprocess.run(["git", "-C", str(project), "add", "."])
    subprocess.run(["git", "-C", str(project), "commit", "-q", "-m", "init"])

    script = tmp_path / "mock_acp_agent.py"
    script.write_text(MOCK_ACP_AGENT, encoding="utf-8")
    runtime = tmp_path / "runtime"

    result = run_go_dispatch(
        project, "edit target.py", runtime_dir=runtime,
        agents=1, targets=["target.py"], execute=True,
        driver="acp", acp_command=[sys.executable, str(script)],
        isolate=True, timeout_seconds=60,
    )
    assert result.status == "passed"
    agent = result.agents[0]
    # Isolation took effect: the edit landed in the worktree, not the main tree.
    assert agent.isolated is True
    assert agent.worktree_path
    assert (project / "target.py").read_text(encoding="utf-8") == "x = 0\n"
    assert (Path(agent.worktree_path) / "target.py").read_text(encoding="utf-8") == "x = 42\n"


def test_default_driver_is_command(tmp_path):
    project = tmp_path / "proj"
    project.mkdir()
    (project / "a.py").write_text("a=1\n", encoding="utf-8")
    runtime = tmp_path / "runtime"
    result = run_go_dispatch(
        project, "prepare only", runtime_dir=runtime,
        agents=1, targets=["a.py"], execute=False,
    )
    assert result.driver == "command"
