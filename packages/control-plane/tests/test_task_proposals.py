"""Tests for human-gated task proposals (MCP Phase 2).

Locks the invariant: proposing or approving a task never runs anything and never
spends tokens — approval only promotes it to a queued intent.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from threading import Thread
from urllib.request import Request, urlopen

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from control_plane.dashboard import build_dashboard_server  # noqa: E402
from control_plane.task_proposals import (  # noqa: E402
    TaskProposalError,
    list_pending_task_proposals,
    load_task_proposal,
    resolve_task_proposal,
    stage_task_proposal,
)


def test_stage_is_pending_and_runs_nothing(tmp_path):
    staged = stage_task_proposal(tmp_path, "demo", "add a feature", proposed_by="mcp-ai")
    assert staged["request_id"].startswith("tk-")
    assert staged["status"] == "pending"
    loaded = load_task_proposal(tmp_path, staged["request_id"])
    assert loaded["status"] == "pending"
    assert loaded["goal"] == "add a feature"


def test_stage_requires_project_and_goal(tmp_path):
    with pytest.raises(TaskProposalError):
        stage_task_proposal(tmp_path, "", "goal")
    with pytest.raises(TaskProposalError):
        stage_task_proposal(tmp_path, "demo", "   ")


def test_stage_rejects_oversize_goal(tmp_path):
    with pytest.raises(TaskProposalError):
        stage_task_proposal(tmp_path, "demo", "x" * 4001)


def test_list_pending(tmp_path):
    stage_task_proposal(tmp_path, "demo", "goal one")
    stage_task_proposal(tmp_path, "demo", "goal two")
    pending = list_pending_task_proposals(tmp_path)
    assert len(pending) == 2


def test_approve_queues_without_running_or_spending(tmp_path):
    staged = stage_task_proposal(tmp_path, "demo", "do work")
    result = resolve_task_proposal(tmp_path, staged["request_id"], "approve")
    assert result["approved"] is True
    assert result["status"] == "approved"
    assert result["ran"] is False
    assert result["spent_tokens"] is False
    # no longer pending
    assert list_pending_task_proposals(tmp_path) == []


def test_reject_discards(tmp_path):
    staged = stage_task_proposal(tmp_path, "demo", "do work")
    result = resolve_task_proposal(tmp_path, staged["request_id"], "reject")
    assert result["approved"] is False
    assert result["status"] == "rejected"


def test_resolve_invalid_id(tmp_path):
    with pytest.raises(TaskProposalError):
        resolve_task_proposal(tmp_path, "../etc", "approve")


def test_double_resolve_is_noop(tmp_path):
    staged = stage_task_proposal(tmp_path, "demo", "do work")
    resolve_task_proposal(tmp_path, staged["request_id"], "approve")
    again = resolve_task_proposal(tmp_path, staged["request_id"], "approve")
    assert again.get("already_resolved") is True


def test_dashboard_approve_task_proposal_does_not_execute(tmp_path):
    runtime_dir = tmp_path / "runtime"
    runtime_dir.mkdir()
    staged = stage_task_proposal(runtime_dir, "demo", "ship it")
    server = build_dashboard_server(runtime_dir=runtime_dir, port=0, refresh_seconds=0)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base_url = f"http://127.0.0.1:{server.server_address[1]}"
        request = Request(
            f"{base_url}/api/t3/approval-response",
            data=json.dumps({"requestId": staged["request_id"], "threadId": "t-1", "decision": "approve"}).encode("utf-8"),
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            method="POST",
        )
        with urlopen(request, timeout=5) as response:
            body = json.loads(response.read().decode("utf-8"))
        assert body["executed"] is False
        assert body["status"] == "approved"
        assert body["spent_tokens"] is False
    finally:
        server.shutdown()
