"""Tests for the RD-Code cluster control surface (&-mention targets + run start).

There is no dashboard-approval / proposal-staging path: a human typing
`&target <goal>` and confirming inline in the conversation is the authorization.
`start_cluster_run` validates the target and starts a project-coordinator run in
the background. The real workflow invocation is patched out here so tests never
spawn a real, token-spending run.
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from threading import Thread
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest
from jsonschema.validators import validator_for

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from control_plane import cluster_run as cluster_run_module  # noqa: E402
from control_plane.cluster_control import (  # noqa: E402
    is_valid_cluster_target,
    list_cluster_targets,
)
from control_plane.cluster_run import ClusterRunError, start_cluster_run  # noqa: E402
from control_plane.dashboard import build_dashboard_server  # noqa: E402
from control_plane.t3_adapter import build_t3_client_shell_from_state  # noqa: E402


REPO_ROOT = Path(__file__).resolve().parents[3]
SYNTHETIC_OPENCODE_API_KEY = "synthetic-cluster-control-fixture"


def _attest_default_execution(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENCODE_API_KEY", SYNTHETIC_OPENCODE_API_KEY)


def _load_coordinator_entry_schema() -> dict:
    return json.loads((REPO_ROOT / "schemas" / "t3_coordinator_entry.schema.json").read_text(encoding="utf-8"))


def _load_client_shell_schema() -> dict:
    return json.loads((REPO_ROOT / "schemas" / "t3_client_shell.schema.json").read_text(encoding="utf-8"))


def _validate_schema(schema: dict, data: dict) -> None:
    validator_class = validator_for(schema)
    validator_class.check_schema(schema)
    validator_class(schema).validate(data)


def test_targets_include_coordinator_and_default_roster(tmp_path):
    targets = list_cluster_targets(tmp_path / "runtime", "demo")
    ids = [t["id"] for t in targets]
    assert "coordinator" in ids
    assert "executor" in ids
    assert "reviewer" in ids
    coordinator = next(t for t in targets if t["id"] == "coordinator")
    assert coordinator["kind"] == "coordinator"
    assert "主控" in coordinator["label"]
    assert len(ids) == len(set(ids))


def test_is_valid_cluster_target(tmp_path):
    runtime = tmp_path / "runtime"
    assert is_valid_cluster_target(runtime, "coordinator", "demo") is True
    assert is_valid_cluster_target(runtime, "executor", "demo") is True
    assert is_valid_cluster_target(runtime, "does-not-exist", "demo") is False
    assert is_valid_cluster_target(runtime, "", "demo") is False


def test_start_cluster_run_validates_and_starts(tmp_path, monkeypatch):
    _attest_default_execution(monkeypatch)
    runtime = tmp_path / "runtime"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    calls: list[tuple] = []
    monkeypatch.setattr(
        cluster_run_module,
        "_run_cluster_workflow",
        lambda rd, path, target, goal, run_id, on_prepared=None: calls.append((path, target, goal, run_id)),
    )
    started = start_cluster_run(runtime, str(workspace), "coordinator", "ship the feature")
    assert started["started"] is True
    assert started["runId"].startswith("g-")
    assert started["target"] == "coordinator"
    assert started["projectId"] == "workspace"
    assert started["projectPath"] == str(workspace)
    assert started["conversationKind"] == "goal_conversation"
    assert started["coordinatorScope"] == "project"
    assert started["projectBinding"] == {
        "mode": "required",
        "projectId": "workspace",
        "projectPath": str(workspace),
        "status": "bound",
    }
    # The background workflow seam is invoked with the validated inputs.
    deadline = time.time() + 5
    while not calls and time.time() < deadline:
        time.sleep(0.02)
    assert calls and calls[0][1] == "coordinator" and calls[0][2] == "ship the feature"


def test_start_cluster_run_rejects_unknown_target(tmp_path, monkeypatch):
    runtime = tmp_path / "runtime"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    monkeypatch.setattr(cluster_run_module, "_run_cluster_workflow", lambda *a, **k: None)
    with pytest.raises(ClusterRunError):
        start_cluster_run(runtime, str(workspace), "ghost-agent", "do something")


def test_start_cluster_run_requires_goal_and_dir(tmp_path, monkeypatch):
    runtime = tmp_path / "runtime"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    monkeypatch.setattr(cluster_run_module, "_run_cluster_workflow", lambda *a, **k: None)
    with pytest.raises(ClusterRunError):
        start_cluster_run(runtime, str(workspace), "coordinator", "")
    with pytest.raises(ClusterRunError):
        start_cluster_run(runtime, str(tmp_path / "missing"), "coordinator", "goal")


def test_start_cluster_run_records_and_lists(tmp_path, monkeypatch):
    _attest_default_execution(monkeypatch)
    from types import SimpleNamespace

    from control_plane.cluster_run import list_cluster_runs

    runtime = tmp_path / "runtime"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    monkeypatch.setattr(
        cluster_run_module,
        "_run_cluster_workflow",
        lambda rd, path, target, goal, run_id, on_prepared=None: SimpleNamespace(
            status="completed", verdict="continue", passed_agents=2, failed_agents=0, go_run_id="go-123"
        ),
    )
    started = start_cluster_run(runtime, str(workspace), "coordinator", "ship it")
    run_id = started["runId"]
    # Background thread updates the record; wait for completion.
    deadline = time.time() + 5
    record = None
    while time.time() < deadline:
        runs = list_cluster_runs(runtime)
        record = next((r for r in runs if r["runId"] == run_id), None)
        if record and record.get("status") == "completed":
            break
        time.sleep(0.02)
    assert record is not None
    assert record["target"] == "coordinator"
    assert record["goal"] == "ship it"
    assert record["status"] == "completed"
    assert "2 passed" in record["summary"]


def _get_json(base_url: str, path: str) -> tuple[int, dict]:
    with urlopen(f"{base_url}{path}", timeout=5) as response:
        return response.status, json.loads(response.read().decode("utf-8"))


def _request_status(
    base_url: str,
    path: str,
    method: str,
    payload: dict | None = None,
) -> tuple[int, str]:
    headers = {"Accept": "application/json"}
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    if data is not None:
        headers["Content-Type"] = "application/json"
    request = Request(f"{base_url}{path}", data=data, headers=headers, method=method)
    try:
        with urlopen(request, timeout=5) as response:
            return response.status, response.read().decode("utf-8")
    except HTTPError as error:
        return error.code, error.read().decode("utf-8")


def _post_json(base_url: str, path: str, payload: dict) -> tuple[int, dict]:
    request = Request(
        f"{base_url}{path}",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    with urlopen(request, timeout=5) as response:
        return response.status, json.loads(response.read().decode("utf-8"))


def test_dashboard_cluster_targets_and_run(tmp_path, monkeypatch):
    _attest_default_execution(monkeypatch)
    calls: list[tuple] = []
    monkeypatch.setattr(cluster_run_module, "_run_cluster_workflow", lambda *a, **k: calls.append(a))
    runtime_dir = tmp_path / "runtime"
    runtime_dir.mkdir()
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    server = build_dashboard_server(runtime_dir=runtime_dir, port=0, refresh_seconds=0)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        status, body = _get_json(base_url, "/api/t3/cluster-targets?project=demo")
        assert status == 200
        ids = [t["id"] for t in body["targets"]]
        assert "coordinator" in ids and "executor" in ids

        status, started = _post_json(base_url, "/api/t3/cluster-run", {
            "projectId": str(workspace),
            "target": "coordinator",
            "goal": "add a settings page",
        })
        assert status == 202
        assert started["started"] is True
        assert started["runId"].startswith("g-")
        assert started["projectId"] == "workspace"
        assert started["target"] == "coordinator"
        assert started["projectPath"] == str(workspace)
        assert started["conversationKind"] == "goal_conversation"
        assert started["coordinatorScope"] == "project"
        assert started["projectBinding"] == {
            "mode": "required",
            "projectId": "workspace",
            "projectPath": str(workspace),
            "status": "bound",
        }
        deadline = time.time() + 5
        while time.time() < deadline and not calls:
            time.sleep(0.02)
        assert calls
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_rdcode_goal_product_path_projects_authoritative_review_state(tmp_path, monkeypatch):
    _attest_default_execution(monkeypatch)
    from control_plane.team_runtime import build_team_runtime_view
    from control_plane.workflow_engine import WorkflowEngine

    runtime_dir = tmp_path / "runtime"
    runtime_dir.mkdir()
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "task.py").write_text("value = 1\n", encoding="utf-8")
    worker_script = (
        "import os;"
        "from pathlib import Path;"
        "Path(os.environ['RDGOAL_REPORT_PATH']).write_text("
        "'## ExecutionReport\\n\\n- **Status**: pass\\n- **Changed Files**:\\n- (none)\\n"
        "- **Evidence**: local cluster product-path test\\n',encoding='utf-8')"
    )

    def run_local_workflow(runtime, project_path, target, goal, run_id, on_prepared=None):
        assert target == "coordinator"
        assert run_id.startswith("g-")
        return WorkflowEngine(runtime).run_coding_workflow(
            project_path,
            goal,
            agents=1,
            targets=["task.py"],
            worker_command=[sys.executable, "-c", worker_script],
            on_prepared=on_prepared,
        )

    monkeypatch.setattr(cluster_run_module, "_run_cluster_workflow", run_local_workflow)
    server = build_dashboard_server(runtime_dir=runtime_dir, port=0, refresh_seconds=0)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        status, started = _post_json(base_url, "/api/t3/cluster-run", {
            "projectId": str(workspace),
            "target": "coordinator",
            "goal": "add authoritative review projection",
        })
        assert status == 202

        deadline = time.monotonic() + 10
        detail = {}
        while time.monotonic() < deadline:
            _, detail = _get_json(
                base_url,
                f"/api/t3/cluster-run-events?runId={started['runId']}",
            )
            if detail.get("goRunId") and detail.get("status") not in {"running", "started"}:
                break
            time.sleep(0.02)
        assert detail.get("status") == "passed", detail
        go_run_id = detail["goRunId"]

        recorded_team = build_team_runtime_view(runtime_dir)
        assert any(item.get("run_id") == go_run_id for item in recorded_team["message_bus"])
        assert any(item.get("run_id") == go_run_id for item in recorded_team["evidence_store"])
        assert any(item.get("run_id") == go_run_id for item in recorded_team["review_gates"])

        monkeypatch.delenv("OPENCODE_API_KEY")
        assert "OPENCODE_API_KEY" not in os.environ
        unlinked_status, unlinked = _post_json(base_url, "/api/t3/cluster-run", {
            "projectId": str(workspace),
            "target": "coordinator",
            "goal": "hello",
        })
        assert unlinked_status == 202
        assert unlinked["kind"] == "conversation"

        shell_status, shell = _get_json(base_url, "/t3-shell.json")
        assert shell_status == 200
        goal_thread = next(item for item in shell["t3"]["threads"] if item["id"] == started["runId"])
        devframe = goal_thread["devframe"]
        assert goal_thread["session"]["status"] == "stopped"
        assert goal_thread["runtimeMode"] == "approval-required"
        assert goal_thread["session"]["runtimeMode"] == "approval-required"
        assert goal_thread["hasPendingApprovals"] is True
        goal_detail = next(
            item for item in shell["t3"]["threadDetails"]
            if item["id"] == started["runId"]
        )
        assert any(
            activity["tone"] == "approval"
            for activity in goal_detail["activities"]
        )
        authoritative_team = shell["devframe"]["team"]
        expected_message_ids = {
            item["messageId"] for item in authoritative_team["messageBus"]
            if item["runId"] == go_run_id
        }
        expected_evidence_ids = {
            item["evidenceId"] for item in authoritative_team["evidenceStore"]
            if item["runId"] == go_run_id
        }
        expected_gates = {
            item["gateId"]: item for item in authoritative_team["reviewGates"]
            if item["runId"] == go_run_id
        }
        assert expected_message_ids
        assert expected_evidence_ids
        assert expected_gates
        assert devframe["relatedRunIds"] == [go_run_id]
        assert set(devframe["teamMessageIds"]) == expected_message_ids
        assert set(devframe["teamEvidenceIds"]) == expected_evidence_ids
        assert set(devframe["teamReviewGateIds"]) == set(expected_gates)
        gate_details = {item["gateId"]: item for item in devframe["teamDetailGates"]}
        assert set(gate_details) == set(expected_gates)
        for gate_id, expected in expected_gates.items():
            assert {
                key: gate_details[gate_id][key]
                for key in ("kind", "status", "reason", "runId")
            } == {
                key: expected[key]
                for key in ("kind", "status", "reason", "runId")
            }
        assert all(item["openPath"] for item in gate_details.values())
        assert all(item["openUrl"].startswith(base_url) for item in gate_details.values())

        unlinked_thread = next(item for item in shell["t3"]["threads"] if item["id"] == unlinked["runId"])
        unlinked_devframe = unlinked_thread["devframe"]
        assert unlinked_devframe["relatedRunIds"] == []
        assert unlinked_devframe["teamMessageIds"] == []
        assert unlinked_devframe["teamEvidenceIds"] == []
        assert unlinked_devframe["teamReviewGateIds"] == []
        assert unlinked_devframe["teamDetailGates"] == []
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


@pytest.mark.parametrize(
    (
        "case",
        "raw_status",
        "gate_status",
        "action_status",
        "action_command",
        "expected_session_status",
        "expected_runtime_mode",
        "expected_pending_approval",
    ),
    [
        ("open review gate", "passed", "open", None, "", "stopped", "approval-required", True),
        ("blocked review gate", "passed", "blocked", None, "", "stopped", "full-access", False),
        ("failed review gate", "passed", "failed", None, "", "stopped", "full-access", False),
        ("passed review gate", "passed", "pass", None, "", "stopped", "full-access", False),
        ("info action", "passed", None, "info", "devframe inspect", "stopped", "full-access", False),
        ("open action", "passed", None, "open", "devframe inspect", "stopped", "full-access", False),
        ("ready action without command", "passed", None, "ready", "", "stopped", "full-access", False),
        (
            "ready command action",
            "passed",
            None,
            "ready",
            "devframe inspect",
            "stopped",
            "approval-required",
            True,
        ),
        ("legacy passed run", "passed", None, None, "", "stopped", "full-access", False),
        ("raw blocked run", "blocked", None, None, "", "ready", "approval-required", False),
    ],
)
def test_cluster_run_projection_fails_closed_for_review_and_blocked_states(
    case,
    raw_status,
    gate_status,
    action_status,
    action_command,
    expected_session_status,
    expected_runtime_mode,
    expected_pending_approval,
):
    go_run_id = "go-projection"
    review_gates = (
        [{
            "gate_id": "gate-review",
            "run_id": go_run_id,
            "kind": "independent_review",
            "status": gate_status,
            "reason": "Independent review is still required.",
        }]
        if gate_status
        else []
    )
    actions = (
        [{
            "action_id": f"action-{case.replace(' ', '-')}",
            "source_type": "cluster_run",
            "source_id": "g-projection",
            "priority": "high",
            "status": action_status,
            "label": case,
            "command": action_command,
        }]
        if action_status
        else []
    )
    shell = build_t3_client_shell_from_state(
        {
            "version": 1,
            "projects": [],
            "sessions": [],
            "next_actions": actions,
            "gates": [],
            "provider_bindings": [],
            "runs": [],
            "go_runs": [],
            "team": {"review_gates": review_gates},
        },
        cluster_runs=[{
            "runId": "g-projection",
            "goRunId": go_run_id,
            "projectId": "demo-project",
            "goal": "Project a fail-closed cluster lifecycle",
            "status": raw_status,
        }],
    )

    thread = next(item for item in shell["t3"]["threads"] if item["id"] == "g-projection")
    detail = next(item for item in shell["t3"]["threadDetails"] if item["id"] == "g-projection")
    approval_activities = [
        activity for activity in detail["activities"]
        if activity["tone"] == "approval"
    ]
    assert thread["session"]["status"] == expected_session_status
    assert thread["runtimeMode"] == expected_runtime_mode
    assert thread["session"]["runtimeMode"] == expected_runtime_mode
    assert thread["session"]["lastError"] is None
    assert thread["hasPendingApprovals"] is expected_pending_approval
    assert bool(approval_activities) is expected_pending_approval


@pytest.mark.parametrize("leading_status", ["pass", "blocked", "failed"])
def test_cluster_run_projection_surfaces_open_gate_beyond_detail_limit(
    leading_status,
):
    go_run_id = "go-overflow"
    review_gates = [
        {
            "gate_id": f"gate-{leading_status}-{index}",
            "run_id": go_run_id,
            "kind": "independent_review",
            "status": leading_status,
            "reason": f"Review is {leading_status}.",
        }
        for index in range(10)
    ] + [{
        "gate_id": "gate-open-overflow",
        "run_id": go_run_id,
        "kind": "independent_review",
        "status": "open",
        "reason": "Independent review is still required.",
    }]
    shell = build_t3_client_shell_from_state(
        {
            "version": 1,
            "projects": [],
            "sessions": [],
            "next_actions": [],
            "gates": [],
            "provider_bindings": [],
            "runs": [],
            "go_runs": [],
            "team": {"review_gates": review_gates},
        },
        cluster_runs=[{
            "runId": "g-overflow",
            "goRunId": go_run_id,
            "projectId": "demo-project",
            "goal": "Keep an overflowed open review gate visible",
            "status": "passed",
        }],
    )
    _validate_schema(_load_client_shell_schema(), shell)

    thread = next(item for item in shell["t3"]["threads"] if item["id"] == "g-overflow")
    detail = next(item for item in shell["t3"]["threadDetails"] if item["id"] == "g-overflow")
    devframe = thread["devframe"]
    approval_activities = [
        activity for activity in detail["activities"]
        if activity["tone"] == "approval"
    ]

    assert [gate["status"] for gate in devframe["teamDetailGates"]] == [
        leading_status
    ] * 10
    assert devframe["teamDetailGateOverflow"] == 1
    next_actionable_gate_ids = [
        gate["gateId"] for gate in devframe["teamNextActionableGates"]
    ]
    if leading_status == "pass":
        assert next_actionable_gate_ids == ["gate-open-overflow"]
    else:
        assert next_actionable_gate_ids == [
            f"gate-{leading_status}-{index}"
            for index in range(10)
        ]
    assert thread["hasPendingApprovals"] is True
    assert thread["runtimeMode"] == "approval-required"
    assert thread["session"]["runtimeMode"] == "approval-required"
    assert [
        (activity["id"], activity["kind"], activity["payload"]["gateId"])
        for activity in approval_activities
    ] == [(
        "g-overflow-gate-gate-open-overflow",
        "devframe.gate.projected",
        "gate-open-overflow",
    )]


def test_dashboard_projects_endpoint_lists_registered_projects(tmp_path, monkeypatch):
    runtime_dir = tmp_path / "runtime"
    runtime_dir.mkdir()
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    monkeypatch.setattr(
        "control_plane.dashboard.build_visual_control_plane_state",
        lambda runtime_dir, paper_project_dirs=None: {
            "projects": [{
                "project_id": "demo-project",
                "display_name": "Demo Project",
                "goal": "Ship it",
                "status": "active",
                "risk_state": "low",
                "contract_path": str(workspace / "rules" / "project-contracts" / "demo-project.md"),
            }]
        },
    )
    server = build_dashboard_server(runtime_dir=runtime_dir, port=0, refresh_seconds=0)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        status, body = _get_json(base_url, "/api/t3/projects")
        assert status == 200
        assert body["projects"] == [{
            "projectId": "demo-project",
            "projectPath": str(workspace),
            "workspaceRoot": str(workspace),
            "label": f"Demo Project - {workspace}",
        }]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_dashboard_conversation_model_endpoint(tmp_path):
    server = build_dashboard_server(runtime_dir=tmp_path / "runtime", port=0, refresh_seconds=0)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        status, body = _get_json(base_url, "/api/t3/conversation-model")
        assert status == 200
        assert body == {
            "globalCoordinatorThreadId": "devframe-team-workbench-session",
            "goalProjectBindingRequired": True,
            "threadKinds": ["native_chat", "goal_conversation", "global_coordinator"],
        }
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_dashboard_coordinator_entry_endpoint(tmp_path, monkeypatch):
    runtime_dir = tmp_path / "runtime"
    runtime_dir.mkdir()
    workspace_alpha = tmp_path / "workspace-alpha"
    workspace_alpha.mkdir()
    workspace_beta = tmp_path / "workspace-beta"
    workspace_beta.mkdir()
    monkeypatch.setattr(
        "control_plane.dashboard.build_visual_control_plane_state",
        lambda runtime_dir, paper_project_dirs=None: {
            "version": 1,
            "projects": [
                {
                    "project_id": "demo-alpha",
                    "display_name": "Demo Alpha",
                    "goal": "Ship alpha",
                    "status": "active",
                    "risk_state": "low",
                    "contract_path": str(workspace_alpha / "rules" / "project-contracts" / "demo-alpha.md"),
                },
                {
                    "project_id": "demo-beta",
                    "display_name": "Demo Beta",
                    "goal": "Ship beta",
                    "status": "active",
                    "risk_state": "low",
                    "contract_path": str(workspace_beta / "rules" / "project-contracts" / "demo-beta.md"),
                },
            ],
            "provider_bindings": [],
            "sessions": [{
                "session_id": "demo-beta-goal",
                "provider": "opencode",
                "agent_role": "coordinator",
                "project_id": "demo-beta",
                "run_id": "run-beta",
                "task_spec_id": "task-beta",
                "status": "active",
                "messages": [],
                "tool_calls": [],
                "changed_files": [],
                "diff_summary": "",
                "evidence_refs": [],
                "gates": [],
                "actions": [],
                "native_refs": {"runtime": "devframe-code"},
            }],
            "gates": [],
            "next_actions": [],
            "team": {},
        },
    )
    server = build_dashboard_server(runtime_dir=runtime_dir, port=0, refresh_seconds=0)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        _, projects = _get_json(base_url, "/api/t3/projects")
        _, conversation_model = _get_json(base_url, "/api/t3/conversation-model")
        status, body = _get_json(base_url, "/api/t3/coordinator-entry")
        assert status == 200
        _validate_schema(_load_coordinator_entry_schema(), body)
        assert body["source"] == "devframe"
        assert body["conversationModel"] == conversation_model
        assert body["conversationModel"]["globalCoordinatorThreadId"] == "devframe-team-workbench-session"
        assert body["projects"] == [
            {
                "projectId": "demo-alpha",
                "projectPath": str(workspace_alpha),
                "workspaceRoot": str(workspace_alpha),
                "label": f"Demo Alpha - {workspace_alpha}",
            },
            {
                "projectId": "demo-beta",
                "projectPath": str(workspace_beta),
                "workspaceRoot": str(workspace_beta),
                "label": f"Demo Beta - {workspace_beta}",
            },
        ]
        assert body["projects"] == projects["projects"]
        assert body["selectedProject"]["projectId"] == "demo-alpha"
        assert body["canStartCoordinatorGoal"] is True
        assert body["globalCoordinatorThread"]["threadKind"] == "global_coordinator"
        assert body["sortedShell"]["threads"][0]["id"] == "devframe-team-workbench-session"
        assert sorted(thread["id"] for thread in body["sortedShell"]["threads"]) == [
            "demo-beta-goal",
            "devframe-team-workbench-session",
        ]
        assert [thread["id"] for thread in body["goalConversations"]] == ["demo-beta-goal"]

        status, body = _get_json(base_url, "/api/t3/coordinator-entry?projectId=demo-beta")
        assert status == 200
        _validate_schema(_load_coordinator_entry_schema(), body)
        assert body["selectedProject"]["projectId"] == "demo-beta"
        assert body["projectCoordinatorThread"]["id"] == "demo-beta-goal"

        status, body = _get_json(base_url, "/api/t3/coordinator-entry?projectId=missing")
        assert status == 200
        assert body["selectedProject"]["projectId"] == "demo-alpha"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_dashboard_coordinator_entry_endpoint_no_projects(tmp_path, monkeypatch):
    runtime_dir = tmp_path / "runtime"
    runtime_dir.mkdir()
    monkeypatch.setattr(
        "control_plane.dashboard.build_visual_control_plane_state",
        lambda runtime_dir, paper_project_dirs=None: {
            "version": 1,
            "projects": [],
            "provider_bindings": [],
            "sessions": [],
            "gates": [],
            "next_actions": [],
            "team": {},
        },
    )
    server = build_dashboard_server(runtime_dir=runtime_dir, port=0, refresh_seconds=0)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        status, body = _get_json(base_url, "/api/t3/coordinator-entry")
        assert status == 200
        assert body["projects"] == []
        assert body["canStartCoordinatorGoal"] is False
        assert body["emptyStateReason"] == "no_projects"
        assert body["disabledReason"] == "missing_required_project"
        assert body["selectedProject"] is None
        assert body["projectCoordinatorThread"] is None
        assert body["globalCoordinatorThread"] is not None
        assert body["globalCoordinatorThread"]["threadKind"] == "global_coordinator"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_dashboard_coordinator_entry_endpoint_rejects_write_methods(tmp_path, monkeypatch):
    runtime_dir = tmp_path / "runtime"
    runtime_dir.mkdir()
    monkeypatch.setattr(
        "control_plane.dashboard.build_visual_control_plane_state",
        lambda runtime_dir, paper_project_dirs=None: {
            "version": 1,
            "projects": [],
            "provider_bindings": [],
            "sessions": [],
            "gates": [],
            "next_actions": [],
            "team": {},
        },
    )
    server = build_dashboard_server(runtime_dir=runtime_dir, port=0, refresh_seconds=0)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        for method in ("POST", "PUT", "PATCH", "DELETE"):
            status, _body = _request_status(base_url, "/api/t3/coordinator-entry", method, payload={"ignored": True})
            assert status == 405, f"{method} accepted for coordinator-entry"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_dashboard_cluster_run_rejects_unknown_target(tmp_path, monkeypatch):
    monkeypatch.setattr(cluster_run_module, "_run_cluster_workflow", lambda *a, **k: None)
    runtime_dir = tmp_path / "runtime"
    runtime_dir.mkdir()
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    server = build_dashboard_server(runtime_dir=runtime_dir, port=0, refresh_seconds=0)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        request = Request(
            f"{base_url}/api/t3/cluster-run",
            data=json.dumps({"projectId": str(workspace), "target": "ghost", "goal": "x"}).encode("utf-8"),
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            method="POST",
        )
        try:
            urlopen(request, timeout=5)
            raise AssertionError("unknown cluster target was not rejected")
        except HTTPError as error:
            assert error.code == 400
            body = json.loads(error.read().decode("utf-8"))
            assert body["error"] == "cluster_run_rejected"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_start_cluster_run_accepts_project_id_from_runtime_state(tmp_path, monkeypatch):
    _attest_default_execution(monkeypatch)
    runtime = tmp_path / "runtime"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    calls: list[tuple] = []
    monkeypatch.setattr(
        cluster_run_module,
        "_run_cluster_workflow",
        lambda rd, path, target, goal, run_id, on_prepared=None: calls.append((path, target, goal, run_id)),
    )
    monkeypatch.setattr(
        cluster_run_module,
        "build_visual_control_plane_state",
        lambda runtime_dir: {
            "projects": [{
                "project_id": "demo-project",
                "display_name": "Demo Project",
                "goal": "g",
                "status": "active",
                "risk_state": "low",
                "contract_path": str(workspace / "rules" / "project-contracts" / "demo-project.md"),
            }]
        },
    )

    started = start_cluster_run(runtime, "demo-project", "coordinator", "ship the feature")

    assert started["projectId"] == "demo-project"
    assert started["projectPath"] == str(workspace)
    assert started["projectBinding"] == {
        "mode": "required",
        "projectId": "demo-project",
        "projectPath": str(workspace),
        "status": "bound",
    }
    deadline = time.time() + 5
    while not calls and time.time() < deadline:
        time.sleep(0.02)
    assert calls and calls[0][0] == str(workspace)



def test_cluster_run_detail_formats_coordinator_messages(tmp_path, monkeypatch):
    runtime = tmp_path / "runtime"
    cluster_run_module._write_run_record(runtime, {
        "runId": "g-abc123",
        "target": "coordinator",
        "goal": "do it",
        "status": "running",
        "goRunId": "go-xyz",
        "startedAt": "t",
    })
    monkeypatch.setattr(
        "control_plane.team_runtime.build_team_runtime_view",
        lambda rd: {
            "message_bus": [
                {
                    "run_id": "go-xyz",
                    "from_role": "coordinator",
                    "to_role": "executor",
                    "kind": "task-assign",
                    "summary": "Coordinator assigned shard 1/2 to executor.",
                },
            ],
            "event_log": [],
        },
    )
    detail = cluster_run_module.cluster_run_detail(runtime, "g-abc123")
    assert detail["goal"] == "do it"
    assert detail["messages"][0]["from"] == "coordinator"
    assert detail["messages"][0]["to"] == "executor"
    assert "assigned" in detail["messages"][0]["text"]


def test_dashboard_cluster_run_events_endpoint(tmp_path, monkeypatch):
    monkeypatch.setattr(cluster_run_module, "_run_cluster_workflow", lambda *a, **k: None)
    runtime_dir = tmp_path / "runtime"
    runtime_dir.mkdir()
    cluster_run_module._write_run_record(runtime_dir, {
        "runId": "g-feed01", "target": "coordinator", "goal": "stream me",
        "status": "running", "startedAt": "t",
    })
    server = build_dashboard_server(runtime_dir=runtime_dir, port=0, refresh_seconds=0)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        status, body = _get_json(base_url, "/api/t3/cluster-run-events?runId=g-feed01")
        assert status == 200
        assert body["goal"] == "stream me"
        assert isinstance(body["messages"], list)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_dashboard_trusts_native_desktop_renderer_origin():
    """The RD-Code desktop renderer is served from a custom protocol scheme
    (t3code://app), not a loopback http origin. The dashboard must trust it so
    the `&` cluster targets fetch (CORS) and the cluster-run POST (origin gate)
    work in the production desktop build."""
    from types import SimpleNamespace

    from control_plane.dashboard import (
        _DEVFRAME_DESKTOP_ORIGINS,
        _is_loopback_origin,
        _loopback_origin_allowed,
    )

    assert "t3code://app" in _DEVFRAME_DESKTOP_ORIGINS
    assert "t3code-dev://app" in _DEVFRAME_DESKTOP_ORIGINS

    # CORS echo gate (GET /api/t3/cluster-targets responses + OPTIONS preflight)
    assert _is_loopback_origin("t3code://app") is True
    assert _is_loopback_origin("t3code-dev://app") is True
    assert _is_loopback_origin("http://127.0.0.1:8765") is True
    assert _is_loopback_origin("https://evil.example.com") is False
    assert _is_loopback_origin("app://.") is False

    # Mutating-origin gate (POST /api/t3/cluster-run)
    def handler(origin):
        return SimpleNamespace(headers={"Origin": origin} if origin is not None else {})

    assert _loopback_origin_allowed(handler("t3code://app")) is True
    assert _loopback_origin_allowed(handler("http://127.0.0.1:8788")) is True
    assert _loopback_origin_allowed(handler("https://evil.example.com")) is False
    assert _loopback_origin_allowed(handler(None)) is True


def test_normalize_local_path_handles_web_and_electron_forms(tmp_path):
    """The editor renderer can send URL-style / leading-slash drive paths that
    Python's Path cannot resolve on Windows; normalize them so a real local
    directory is accepted by start_cluster_run."""
    from control_plane.cluster_run import _normalize_local_path

    assert _normalize_local_path("/D:/proj/travel_app") == "D:/proj/travel_app"
    assert _normalize_local_path("file:///D:/proj/travel%20app") == "D:/proj/travel app"
    # Native paths pass through unchanged.
    assert _normalize_local_path("D:/proj/travel_app") == "D:/proj/travel_app"
    assert _normalize_local_path("/home/user/proj") == "/home/user/proj"
    assert _normalize_local_path("  ") == ""


def test_start_cluster_run_accepts_leading_slash_drive_path(tmp_path, monkeypatch):
    """A leading-slash Windows drive path that points at a real directory must
    be accepted (it is normalized before the is_dir() check)."""
    _attest_default_execution(monkeypatch)
    calls: list[tuple] = []
    monkeypatch.setattr(cluster_run_module, "_run_cluster_workflow", lambda *a, **k: calls.append(a))
    runtime = tmp_path / "runtime"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    # Build a "/D:/..." style path from the real workspace dir.
    native = str(workspace)
    if len(native) >= 2 and native[1] == ":":
        url_style = "/" + native.replace("\\", "/")
        started = start_cluster_run(runtime, url_style, "coordinator", "ship it")
        assert started["started"] is True
        deadline = time.time() + 5
        while time.time() < deadline and not calls:
            time.sleep(0.02)
        assert calls


def test_orphaned_running_run_is_marked_interrupted(tmp_path, monkeypatch):
    """A run left at 'running' by a control-plane process that no longer exists
    must be reconciled to 'interrupted' on read, never shown frozen forever."""
    from control_plane.cluster_run import (
        _reconcile_orphaned_run,
        cluster_run_detail,
        list_cluster_runs,
    )

    runtime = tmp_path / "runtime"
    cluster_run_module._write_run_record(runtime, {
        "runId": "g-orphan",
        "target": "coordinator",
        "goal": "stuck goal",
        "ownerPid": 999_999_999,  # not a live process
        "status": "running",
        "summary": "agents are working…",
        "startedAt": "t0",
    })
    # Force the owner-pid liveness check to report dead.
    monkeypatch.setattr(cluster_run_module, "_pid_alive", lambda pid: False)

    runs = list_cluster_runs(runtime)
    assert runs[0]["status"] == "interrupted"
    assert runs[0].get("finishedAt")
    # Reconciliation is durable.
    detail = cluster_run_detail(runtime, "g-orphan")
    assert detail["status"] == "interrupted"


def test_running_run_with_live_owner_stays_running(tmp_path, monkeypatch):
    from control_plane.cluster_run import _reconcile_orphaned_run

    runtime = tmp_path / "runtime"
    record = {
        "runId": "g-live", "target": "coordinator", "goal": "g",
        "ownerPid": 4321, "status": "running", "startedAt": "t0",
    }
    monkeypatch.setattr(cluster_run_module, "_pid_alive", lambda pid: pid == 4321)
    reconciled = _reconcile_orphaned_run(runtime, record)
    assert reconciled["status"] == "running"
    assert "finishedAt" not in reconciled


def test_finished_run_is_not_reconciled(tmp_path, monkeypatch):
    from control_plane.cluster_run import _reconcile_orphaned_run

    runtime = tmp_path / "runtime"
    record = {
        "runId": "g-done", "target": "coordinator", "goal": "g",
        "ownerPid": 1, "status": "completed", "finishedAt": "t1", "startedAt": "t0",
    }
    monkeypatch.setattr(cluster_run_module, "_pid_alive", lambda pid: False)
    reconciled = _reconcile_orphaned_run(runtime, record)
    assert reconciled["status"] == "completed"


def test_cluster_run_detail_includes_agent_summaries(tmp_path, monkeypatch):
    """The goal detail view exposes per-agent summary cards built from the
    underlying go-run, so the editor can list agents and drill into each one."""
    from types import SimpleNamespace

    from control_plane import cluster_run as crm

    runtime = tmp_path / "runtime"
    crm._write_run_record(runtime, {
        "runId": "g-agents",
        "target": "coordinator",
        "goal": "ship it",
        "goRunId": "go-x",
        "ownerPid": 1234,
        "status": "running",
        "startedAt": "t0",
    })
    monkeypatch.setattr(crm, "_pid_alive", lambda pid: True)
    fake_agents = [
        SimpleNamespace(
            agent_id="coding-agent-1", shard_index=1, shard_count=2,
            worker_status="completed", status="completed",
            changed_files=["a.py", "b.py"], total_tokens=120,
        ),
        SimpleNamespace(
            agent_id="coding-agent-2", shard_index=2, shard_count=2,
            worker_status="", status="queued",
            changed_files=[], total_tokens=0,
        ),
    ]
    monkeypatch.setattr(crm, "_load_go_agents", lambda rd, gid: fake_agents)

    detail = crm.cluster_run_detail(runtime, "g-agents")
    assert len(detail["agents"]) == 2
    first = detail["agents"][0]
    assert first["agentId"] == "coding-agent-1"
    assert first["changedFileCount"] == 2
    assert first["status"] == "completed"


def test_cluster_run_agent_detail_returns_report_and_tokens(tmp_path, monkeypatch):
    from types import SimpleNamespace

    from control_plane import cluster_run as crm

    runtime = tmp_path / "runtime"
    report = tmp_path / "report.md"
    report.write_text("# ExecutionReport\nStatus: completed\n", encoding="utf-8")
    crm._write_run_record(runtime, {
        "runId": "g-drill", "target": "coordinator", "goal": "g",
        "goRunId": "go-y", "ownerPid": 1, "status": "running", "startedAt": "t0",
    })
    monkeypatch.setattr(crm, "_pid_alive", lambda pid: True)
    agent = SimpleNamespace(
        agent_id="coding-agent-1", shard_index=1, shard_count=1,
        worker_status="completed", status="completed",
        changed_files=["x.py"], verification="pytest -q",
        session_id="sess-1", model_provider="opencode-api",
        input_tokens=10, output_tokens=20, total_tokens=30, cost=0.01,
        tool_calls=[{"name": "edit"}], report_path=str(report),
    )
    monkeypatch.setattr(crm, "_load_go_agents", lambda rd, gid: [agent])

    detail = crm.cluster_run_agent_detail(runtime, "g-drill", "coding-agent-1")
    assert detail["agentId"] == "coding-agent-1"
    assert detail["totalTokens"] == 30
    assert detail["changedFiles"] == ["x.py"]
    assert "ExecutionReport" in detail["reportMarkdown"]
    assert detail["toolCalls"] == [{"name": "edit"}]

    with pytest.raises(crm.ClusterRunError):
        crm.cluster_run_agent_detail(runtime, "g-drill", "ghost-agent")


def test_classify_goal_conversation_vs_development():
    from control_plane.goal_triage import (
        GOAL_KIND_CONVERSATION,
        GOAL_KIND_DEVELOPMENT,
        classify_goal,
    )

    assert classify_goal("你好") == GOAL_KIND_CONVERSATION
    assert classify_goal("你好，请问你能做什么") == GOAL_KIND_CONVERSATION
    assert classify_goal("hello") == GOAL_KIND_CONVERSATION
    assert classify_goal("") == GOAL_KIND_CONVERSATION
    # Real development goals (including a greeting that carries a real task).
    assert classify_goal("在 README 增加快速开始章节") == GOAL_KIND_DEVELOPMENT
    assert classify_goal("修复登录页的空指针报错") == GOAL_KIND_DEVELOPMENT
    assert classify_goal("你好，帮我修复登录bug") == GOAL_KIND_DEVELOPMENT
    assert classify_goal("add a date formatter to utils.ts") == GOAL_KIND_DEVELOPMENT
    assert classify_goal("refactor the auth module") == GOAL_KIND_DEVELOPMENT


def test_conversational_goal_answers_without_running_agents(tmp_path, monkeypatch):
    """A conversational goal must NOT spawn the coding workflow; the coordinator
    answers directly and the run is recorded as 'answered'."""
    calls: list[tuple] = []
    monkeypatch.setattr(
        cluster_run_module,
        "_run_cluster_workflow",
        lambda *a, **k: calls.append(a),
    )
    runtime = tmp_path / "runtime"
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    started = start_cluster_run(runtime, str(workspace), "coordinator", "你好，你能做什么")
    assert started["started"] is True
    assert started["kind"] == "conversation"
    assert "主控" in started["answer"]
    assert calls == []  # never dispatched a token-spending run

    detail = cluster_run_module.cluster_run_detail(runtime, started["runId"])
    assert detail["status"] == "answered"
    assert detail["messages"]
    assert detail["messages"][0]["from"] == "coordinator"
    assert detail["agents"] == []


def test_development_goal_still_dispatches(tmp_path, monkeypatch):
    _attest_default_execution(monkeypatch)
    calls: list[tuple] = []
    monkeypatch.setattr(
        cluster_run_module,
        "_run_cluster_workflow",
        lambda rd, path, target, goal, run_id, on_prepared=None: calls.append((target, goal)),
    )
    runtime = tmp_path / "runtime"
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    started = start_cluster_run(runtime, str(workspace), "coordinator", "修复登录页的报错")
    assert started["started"] is True
    assert started.get("kind") != "conversation"
    # Background thread should invoke the workflow seam.
    import time as _time

    deadline = _time.time() + 5
    while _time.time() < deadline and not calls:
        _time.sleep(0.05)
    assert calls and calls[0][1] == "修复登录页的报错"


def test_configured_roster_overrides_default(tmp_path):
    """A saved roster replaces the hardcoded default worker roster in the
    &-mention targets (the coordinator is always still present)."""
    from control_plane.cluster_control import (
        list_cluster_targets,
        load_cluster_roster,
        save_cluster_roster,
    )

    runtime = tmp_path / "runtime"
    assert load_cluster_roster(runtime) == []  # none configured yet

    # Default roster is the executor/reviewer pair.
    default_ids = {t["id"] for t in list_cluster_targets(runtime, "demo")}
    assert {"coordinator", "executor", "reviewer"} <= default_ids

    saved = save_cluster_roster(runtime, [
        {"id": "docs-bot", "role": "docs", "label": "Docs (文档)", "methodology": "tdd"},
        {"id": "qa", "role": "reviewer", "label": "QA", "enabled": False},
    ])
    assert len(saved) == 2

    targets = list_cluster_targets(runtime, "demo")
    ids = {t["id"] for t in targets}
    assert "coordinator" in ids
    assert "docs-bot" in ids
    assert "qa" not in ids  # disabled agents are hidden
    assert "executor" not in ids  # default roster replaced by the configured one
    docs = next(t for t in targets if t["id"] == "docs-bot")
    assert docs["source"] == "configured"
    assert docs["methodology"] == "tdd"


def test_save_cluster_roster_validation(tmp_path):
    from control_plane.cluster_control import ClusterControlError, save_cluster_roster

    runtime = tmp_path / "runtime"
    with pytest.raises(ClusterControlError):
        save_cluster_roster(runtime, [{"id": "", "role": "x", "label": "y"}])
    with pytest.raises(ClusterControlError):
        save_cluster_roster(runtime, [{"id": "coordinator", "role": "x", "label": "y"}])
    with pytest.raises(ClusterControlError):
        save_cluster_roster(runtime, [
            {"id": "dup", "role": "a", "label": "A"},
            {"id": "dup", "role": "b", "label": "B"},
        ])


def test_malformed_roster_file_falls_back_to_default(tmp_path):
    from control_plane.cluster_control import _roster_path, list_cluster_targets

    runtime = tmp_path / "runtime"
    path = _roster_path(runtime)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{ not valid json", encoding="utf-8")
    # A bad edit must never break &-mention; falls back to the default roster.
    ids = {t["id"] for t in list_cluster_targets(runtime, "demo")}
    assert {"coordinator", "executor", "reviewer"} <= ids


# --- Scope-aware retrofit (task 3.2) -----------------------------------------

def _roster_global_path(runtime):
    from control_plane.scoped_store import ScopedStore
    from control_plane.scope_resolver import Scope

    return ScopedStore(runtime, "cluster-roster.json", default_factory=dict).path(Scope.GLOBAL, None)


def _roster_project_path(runtime, project_id):
    from control_plane.scoped_store import ScopedStore
    from control_plane.scope_resolver import Scope

    return ScopedStore(runtime, "cluster-roster.json", default_factory=dict).path(
        Scope.PROJECT, project_id
    )


def test_resolve_roster_compat_no_project_layer(tmp_path):
    from control_plane.cluster_control import resolve_roster, save_cluster_roster
    from control_plane.scope_resolver import Scope

    runtime = tmp_path / "runtime"
    save_cluster_roster(runtime, [{"id": "docs", "role": "docs", "label": "Docs"}])
    rc = resolve_roster(runtime)  # no project id
    assert rc.project == []
    effective = {r["id"]: r for r in rc.effective}
    # built-in executor/reviewer plus the global docs agent
    assert {"executor", "reviewer", "docs"} <= set(effective)
    assert effective["docs"]["_scope"] == "global"
    assert effective["executor"]["_scope"] == "builtin"


def test_resolve_roster_project_overrides_global(tmp_path):
    from control_plane.cluster_control import resolve_roster, save_at
    from control_plane.scope_resolver import Scope

    runtime = tmp_path / "runtime"
    save_at(runtime, Scope.GLOBAL, None, [{"id": "executor", "role": "executor", "label": "Global Exec"}])
    save_at(runtime, Scope.PROJECT, "demo", [{"id": "executor", "role": "executor", "label": "Project Exec"}])
    rc = resolve_roster(runtime, "demo")
    effective = {r["id"]: r for r in rc.effective}
    assert effective["executor"]["label"] == "Project Exec"
    assert effective["executor"]["_scope"] == "project"


def test_resolve_roster_absent_project_uses_global(tmp_path):
    from control_plane.cluster_control import resolve_roster, save_at
    from control_plane.scope_resolver import Scope

    runtime = tmp_path / "runtime"
    save_at(runtime, Scope.GLOBAL, None, [{"id": "executor", "role": "executor", "label": "Global Exec"}])
    rc = resolve_roster(runtime, "demo")  # no project file exists
    effective = {r["id"]: r for r in rc.effective}
    assert effective["executor"]["label"] == "Global Exec"
    assert effective["executor"]["_scope"] == "global"


def test_resolve_roster_malformed_project_falls_back_to_global(tmp_path):
    from control_plane.cluster_control import resolve_roster, save_at
    from control_plane.scope_resolver import Scope

    runtime = tmp_path / "runtime"
    save_at(runtime, Scope.GLOBAL, None, [{"id": "executor", "role": "executor", "label": "Global Exec"}])
    path = _roster_project_path(runtime, "demo")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{ not json", encoding="utf-8")
    rc = resolve_roster(runtime, "demo")
    effective = {r["id"]: r for r in rc.effective}
    assert effective["executor"]["label"] == "Global Exec"
    assert effective["executor"]["_scope"] == "global"


def test_resolve_roster_malformed_global_falls_back_to_builtin(tmp_path):
    from control_plane.cluster_control import resolve_roster

    runtime = tmp_path / "runtime"
    path = _roster_global_path(runtime)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{ not json", encoding="utf-8")
    rc = resolve_roster(runtime)
    effective = {r["id"]: r for r in rc.effective}
    assert {"executor", "reviewer"} <= set(effective)
    assert effective["executor"]["_scope"] == "builtin"


def test_scoped_writes_are_isolated(tmp_path):
    from control_plane.cluster_control import load_cluster_roster_at, save_at
    from control_plane.scope_resolver import Scope

    runtime = tmp_path / "runtime"
    save_at(runtime, Scope.GLOBAL, None, [{"id": "g", "role": "r", "label": "G"}])
    save_at(runtime, Scope.PROJECT, "demo", [{"id": "p", "role": "r", "label": "P"}])
    # Writing project never disturbs global and vice versa.
    assert [a["id"] for a in load_cluster_roster_at(runtime, Scope.GLOBAL, None)] == ["g"]
    assert [a["id"] for a in load_cluster_roster_at(runtime, Scope.PROJECT, "demo")] == ["p"]
