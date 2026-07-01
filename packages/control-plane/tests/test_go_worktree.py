"""Hermetic tests for the go-dispatch worktree isolation wiring.

Verifies that `_resolve_isolation` creates a per-agent worktree and computes the
OpenCode-specific OPENCODE_HOME override when isolation is requested in a git
tree, and honestly falls back (isolated=False) when isolation is impossible. No
tokens are spent.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from control_plane.go_dispatch import GoAgentDispatch, _resolve_isolation

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git not available")


def _init_repo(path):
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "-C", str(path), "init"], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(path), "config", "user.email", "t@example.com"], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(path), "config", "user.name", "Test"], check=True, capture_output=True)
    (path / "file.txt").write_text("hello\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(path), "add", "."], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(path), "commit", "-m", "init"], check=True, capture_output=True)


def _agent(isolated: bool) -> GoAgentDispatch:
    return GoAgentDispatch(
        agent_id="coding-agent-1",
        shard_index=1,
        shard_count=1,
        targets=["file.txt"],
        target_bytes=6,
        packet_dir="",
        task_spec_path="",
        worker_command=["opencode", "run"],
        isolated=isolated,
    )


def test_resolve_isolation_disabled_is_noop(tmp_path):
    repo = tmp_path / "repo"
    _init_repo(repo)
    agent = _agent(isolated=False)

    cwd, env_overrides = _resolve_isolation(str(tmp_path / "runtime"), str(repo), "go-run-1", agent)

    assert cwd is None
    assert env_overrides is None
    assert agent.isolated is False
    assert agent.worktree_path == ""


def test_resolve_isolation_creates_worktree_and_opencode_home(tmp_path):
    repo = tmp_path / "repo"
    _init_repo(repo)
    agent = _agent(isolated=True)
    # rebase_packet needs a real packet on disk; build a minimal one.
    from control_plane.orchestrator import Orchestrator
    from control_plane.rdgoal import rdgoal
    runtime = tmp_path / "runtime"
    orch = Orchestrator(runtime_dir=runtime)
    result = rdgoal(orch, repo, "isolate test", operation="go coding shard 1/1", targets=["file.txt"])
    agent.packet_dir = result.dispatch.packet.packet_dir

    cwd, env_overrides = _resolve_isolation(str(runtime), str(repo), "go-run-1", agent)

    assert cwd is not None
    assert Path(cwd).exists()
    assert agent.isolated is True
    assert agent.worktree_path == cwd
    assert env_overrides is not None
    # Verified executor state dir env var (OpenCode 1.17.9 honors XDG_DATA_HOME).
    assert env_overrides["XDG_DATA_HOME"] == str(Path(cwd) / ".opencode-data")
    # Packet is rebased so the agent's project root is the worktree.
    import json
    packet_json = json.loads((Path(agent.packet_dir) / "packet.json").read_text(encoding="utf-8"))
    assert packet_json["project_root"] == str(Path(cwd).resolve())


def test_resolve_isolation_falls_back_honestly_when_not_git(tmp_path):
    plain = tmp_path / "plain"
    plain.mkdir()
    agent = _agent(isolated=True)

    cwd, env_overrides = _resolve_isolation(str(tmp_path / "runtime"), str(plain), "go-run-1", agent)

    # No fake green: isolation requested but impossible -> recorded as False.
    assert cwd is None
    assert env_overrides is None
    assert agent.isolated is False
    assert agent.worktree_path == ""
