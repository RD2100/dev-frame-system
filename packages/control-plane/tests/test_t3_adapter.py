import json
import os
import copy
import time
from pathlib import Path
from threading import Thread
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest
from jsonschema.validators import validator_for

from control_plane import cluster_run as cluster_run_module
from control_plane import dashboard as dashboard_module
from control_plane import t3_adapter as t3_adapter_module
from control_plane.dashboard import build_dashboard_server
from control_plane.t3_adapter import (
    build_t3_client_shell,
    build_t3_client_shell_from_state,
    build_t3_coordinator_entry,
    render_cached_t3_client_shell_compact_json,
)


REPO_ROOT = Path(__file__).resolve().parents[3]


def load_schema() -> dict:
    return json.loads((REPO_ROOT / "schemas" / "t3_client_shell.schema.json").read_text(encoding="utf-8"))


def load_coordinator_entry_schema() -> dict:
    return json.loads((REPO_ROOT / "schemas" / "t3_coordinator_entry.schema.json").read_text(encoding="utf-8"))


def validate_schema(schema: dict, data: dict) -> None:
    validator_class = validator_for(schema)
    validator_class.check_schema(schema)
    validator_class(schema).validate(data)


def test_t3_client_shell_projects_mcp_live_session():
    state = {
        "version": 1,
        "projects": [{
            "project_id": "project",
            "display_name": "Project",
            "goal": "Show MCP live session in T3.",
            "status": "active",
            "risk_state": "medium",
            "contract_path": "/x",
        }],
        "provider_bindings": [{
            "binding_id": "codexpro-web",
            "provider": "codexpro",
            "mode": "mcp_live",
            "health": "ready",
        }],
        "sessions": [{
            "session_id": "codexpro-live-session",
            "provider": "codexpro",
            "binding_id": "codexpro-web",
            "agent_role": "coordinator",
            "project_id": "project",
            "run_id": "",
            "task_spec_id": "",
            "status": "active",
            "messages": [{"message_id": "m1", "role": "system", "content_summary": "MCP live check succeeded."}],
            "tool_calls": [{"tool_call_id": "tc-1", "name": "server_config", "status": "completed"}],
            "changed_files": [],
            "diff_summary": "",
            "evidence_refs": [],
            "cost": {},
            "tokens": {},
            "gates": [],
            "actions": [],
            "native_refs": {
                "runtime": "web-ai-import",
                "source_runtime": "mcp-live-probe",
                "endpoint": "http://127.0.0.1:3978/mcp",
            },
        }],
        "gates": [],
        "next_actions": [],
    }

    shell = build_t3_client_shell_from_state(state)

    validate_schema(load_schema(), shell)
    assert shell["devframe"]["conversationModel"] == {
        "globalCoordinatorThreadId": "devframe-team-workbench-session",
        "goalProjectBindingRequired": True,
        "threadKinds": ["native_chat", "goal_conversation", "global_coordinator"],
    }
    thread = shell["t3"]["threads"][0]
    assert thread["id"] == "codexpro-live-session"
    assert thread["threadKind"] == "native_chat"
    assert thread["coordinatorScope"] == "none"
    assert thread["projectBinding"] == {"mode": "none", "projectId": "project", "status": "bound"}
    assert thread["threadListPriority"] == 2
    assert thread["threadListSummary"] == "codexpro / coordinator - running"
    assert thread["modelSelection"]["instanceId"] == "codexpro-web"
    assert thread["runtimeMode"] == "full-access"
    assert thread["session"]["status"] == "running"
    assert thread["devframe"]["provider"] == "codexpro"
    assert thread["devframe"]["bindingId"] == "codexpro-web"
    assert thread["devframe"]["agentRole"] == "coordinator"
    assert thread["devframe"]["messageCount"] == 1
    assert thread["devframe"]["toolCallCount"] == 1
    detail = shell["t3"]["threadDetails"][0]
    assert detail["id"] == "codexpro-live-session"
    assert detail["threadKind"] == "native_chat"
    assert "Provider: codexpro" in detail["messages"][0]["text"]


def _coordinator_entry_fixture_path(name: str) -> Path:
    return (
        Path(__file__).resolve().parents[3]
        / "packages"
        / "control-plane"
        / "tests"
        / "fixtures"
        / "t3_coordinator_entry"
        / f"{name}.json"
    )


def _load_coordinator_entry_fixture(name: str) -> dict[str, object]:
    return json.loads(_coordinator_entry_fixture_path(name).read_text(encoding="utf-8"))


@pytest.mark.parametrize(
    "fixture_name",
    [
        "no_projects",
        "global_coordinator_only",
        "project_with_goal_conversations",
        "project_without_goal_conversations",
        "project_alpha_without_matching_goal_conversation",
        "can_start_coordinator_goal_false",
        "malformed_or_partial_entry_response",
        "global_malformed_priority_still_sorts_global_first",
    ],
)
def test_t3_coordinator_entry_projects_shell_ready_shape_from_fixtures(fixture_name: str):
    fixture = _load_coordinator_entry_fixture(fixture_name)
    shell = fixture["shell"]
    projects = fixture["projects"]
    expected = fixture["expected"]

    entry = build_t3_coordinator_entry(shell, projects)

    validate_schema(load_coordinator_entry_schema(), entry)
    assert entry["source"] == "devframe"
    assert entry["canStartCoordinatorGoal"] is expected["canStartCoordinatorGoal"]
    assert entry["projects"] == projects
    assert len(entry["projectOptions"]) == expected["projectOptionCount"]
    assert entry["projectOptions"] == projects
    assert [thread["id"] for thread in entry["shellThreads"]] == expected["shellThreadsIds"]
    assert [thread["id"] for thread in entry["sortedShell"]["threads"]] == expected["sortedShellThreadIds"]
    assert [detail["id"] for detail in entry["sortedShell"]["threadDetails"]] == expected["sortedShellThreadIds"]
    assert [thread["id"] for thread in entry["goalConversations"]] == expected["goalConversationIds"]
    if expected["selectedProjectId"] is None:
        assert entry["selectedProject"] is None
    else:
        assert entry["selectedProject"]["projectId"] == expected["selectedProjectId"]
    if expected["projectCoordinatorThreadId"] is None:
        assert entry["projectCoordinatorThread"] is None
    else:
        assert entry["projectCoordinatorThread"]["id"] == expected["projectCoordinatorThreadId"]
    if expected["globalThreadId"] is None:
        assert entry["globalCoordinatorThread"] is None
    else:
        assert entry["globalCoordinatorThread"]["id"] == expected["globalThreadId"]
    assert entry["emptyStateReason"] == expected["emptyStateReason"]
    assert entry["disabledReason"] == expected["disabledReason"]


def test_t3_coordinator_entry_schema_contract_boundaries():
    schema = load_coordinator_entry_schema()
    assert schema["type"] == "object"
    assert set(schema["required"]) >= {
        "version",
        "source",
        "updatedAt",
        "conversationModel",
        "projectOptions",
        "selectedProject",
        "projectCoordinatorThread",
        "shellThreads",
        "projects",
        "globalCoordinatorThread",
        "goalConversations",
        "sortedShell",
        "canStartCoordinatorGoal",
        "emptyStateReason",
        "disabledReason",
    }
    assert schema["additionalProperties"] is False


def test_t3_coordinator_entry_rejects_additional_properties_and_missing_required():
    fixture = _load_coordinator_entry_fixture("global_coordinator_only")
    shell = fixture["shell"]
    projects = fixture["projects"]

    entry = build_t3_coordinator_entry(shell, projects)
    validate_schema(load_coordinator_entry_schema(), entry)

    schema = load_coordinator_entry_schema()
    validator = validator_for(schema)

    mutated = copy.deepcopy(entry)
    mutated["unexpected"] = "injected-field"
    with pytest.raises(Exception):
        validator(schema).validate(mutated)

    missing_projects = copy.deepcopy(entry)
    missing_projects.pop("projects")
    with pytest.raises(Exception):
        validator(schema).validate(missing_projects)


def test_t3_client_shell_projects_chatgpt_web_mcp_session():
    state = {
        "version": 1,
        "projects": [{
            "project_id": "project",
            "display_name": "Project",
            "goal": "Show ChatGPT Web MCP session in T3.",
            "status": "active",
            "risk_state": "medium",
            "contract_path": "/x",
        }],
        "provider_bindings": [{
            "binding_id": "chatgpt-web-mcp",
            "provider": "chatgpt",
            "mode": "mcp_web",
            "health": "ready",
        }],
        "sessions": [{
            "session_id": "chatgpt-web-mcp-session",
            "provider": "chatgpt",
            "binding_id": "chatgpt-web-mcp",
            "agent_role": "coordinator",
            "project_id": "project",
            "run_id": "",
            "task_spec_id": "",
            "status": "blocked",
            "messages": [{"message_id": "m1", "role": "system", "content_summary": "ChatGPT Web MCP connector blocked."}],
            "tool_calls": [{"tool_call_id": "tc-1", "name": "open_current_workspace", "status": "blocked"}],
            "changed_files": [],
            "diff_summary": "",
            "evidence_refs": [],
            "cost": {},
            "tokens": {},
            "gates": [],
            "actions": [],
            "native_refs": {
                "runtime": "web-ai-import",
                "source_runtime": "chatgpt-web-mcp",
            },
        }],
        "gates": [],
        "next_actions": [],
    }

    shell = build_t3_client_shell_from_state(state)

    validate_schema(load_schema(), shell)
    thread = shell["t3"]["threads"][0]
    assert thread["id"] == "chatgpt-web-mcp-session"
    assert thread["modelSelection"]["instanceId"] == "chatgpt-web-mcp"
    assert thread["runtimeMode"] == "approval-required"
    assert thread["session"]["status"] == "ready"
    assert thread["devframe"]["provider"] == "chatgpt"
    assert thread["devframe"]["bindingId"] == "chatgpt-web-mcp"
    assert thread["devframe"]["agentRole"] == "coordinator"
    detail = shell["t3"]["threadDetails"][0]
    assert detail["id"] == "chatgpt-web-mcp-session"
    assert "Provider: chatgpt" in detail["messages"][0]["text"]


def test_t3_client_shell_maps_devframe_sessions_to_thread_shells(tmp_path):
    project_root = tmp_path / "project"
    project_root.mkdir()
    contract_path = project_root / "rules" / "project-contracts" / "demo-project.md"
    state = {
        "version": 1,
        "projects": [{
            "project_id": "project",
            "display_name": "Project",
            "goal": "Build a local Agent client.",
            "status": "active",
            "risk_state": "medium",
            "contract_path": str(contract_path),
        }],
        "provider_bindings": [{
            "binding_id": "local-executor",
            "provider": "opencode",
            "mode": "custom",
            "health": "ready",
        }],
        "sessions": [{
            "session_id": "session-1",
            "provider": "opencode",
            "binding_id": "local-executor",
            "agent_role": "executor",
            "project_id": "project",
            "run_id": "run-1",
            "task_spec_id": "TASKSPEC.json",
            "status": "needs_human",
            "messages": [{"message_id": "m1", "role": "user", "content_summary": "Do work."}],
            "tool_calls": [{"tool_call_id": "tool-1", "name": "write", "status": "completed"}],
            "changed_files": ["src/app.py"],
            "diff_summary": "1 changed file",
            "evidence_refs": ["ExecutionReport.md"],
            "cost": {},
            "tokens": {},
            "gates": ["gate-1", "human-gate"],
            "actions": ["gate-1-action"],
        }],
        "gates": [{
            "gate_id": "gate-1",
            "kind": "human",
            "status": "open",
            "run_id": "run-1",
            "reason": "Human approval required.",
            "next_action": "Approve before execution.",
        }, {
            "gate_id": "human-gate",
            "kind": "human",
            "status": "open",
            "reason": "Global approval required.",
            "next_action": "Confirm global gate.",
        }],
        "next_actions": [{
            "action_id": "gate-1-action",
            "source_type": "gate",
            "source_id": "gate-1",
            "priority": "medium",
            "status": "ready",
            "label": "Approve gate.",
        }, {
            "action_id": "human-gate-action",
            "source_type": "gate",
            "source_id": "human-gate",
            "priority": "medium",
            "status": "open",
            "label": "Confirm global gate.",
        }],
    }

    shell = build_t3_client_shell_from_state(state)

    validate_schema(load_schema(), shell)
    assert shell["reuse"]["client"] == "t3code"
    assert shell["reuse"]["executor"] == "opencode"
    assert shell["devframe"]["writePolicy"] == "read-only"
    assert shell["t3"]["projects"][0]["workspaceRoot"] == str(project_root)
    thread = shell["t3"]["threads"][0]
    assert thread["id"] == "session-1"
    assert thread["modelSelection"]["instanceId"] == "local-executor"
    assert thread["runtimeMode"] == "approval-required"
    assert thread["interactionMode"] == "plan"
    assert thread["hasPendingApprovals"] is False
    assert thread["hasPendingUserInput"] is True
    assert thread["hasActionableProposedPlan"] is True
    assert thread["session"]["status"] == "ready"
    assert thread["devframe"]["gateIds"] == ["gate-1", "human-gate"]
    assert thread["devframe"]["actionIds"] == ["gate-1-action", "human-gate-action"]
    assert thread["devframe"]["actionDetails"][0]["actionId"] == "gate-1-action"
    assert thread["devframe"]["actionDetails"][0]["resumeFilter"] == (
        "devframe actions --action-id gate-1-action --format markdown"
    )
    assert thread["devframe"]["changedFiles"] == ["src/app.py"]
    detail = shell["t3"]["threadDetails"][0]
    assert detail["id"] == "session-1"
    assert detail["messages"][0]["role"] == "assistant"
    assert "Provider: opencode" in detail["messages"][0]["text"]
    assert "ExecutionReport.md" in detail["messages"][0]["text"]
    assert detail["proposedPlans"][0]["planMarkdown"].startswith("# DevFrame Read-only Agent Session")
    assert detail["activities"][0]["kind"] == "devframe.session.projected"


def test_t3_client_shell_links_go_run_session_to_rdgoal_actions(tmp_path):
    packet_dir = tmp_path / "runtime" / "rdgoal-outbox" / "project" / "rdgoal-run-1"
    task_spec_path = packet_dir / "TASKSPEC.json"
    command = f'rdgoal worker "{packet_dir}" --runtime-dir "{tmp_path / "runtime"}"'
    state = {
        "version": 1,
        "projects": [{
            "project_id": "project",
            "display_name": "Project",
            "goal": "Show actions in T3.",
            "status": "active",
            "risk_state": "medium",
            "contract_path": str(tmp_path / "project" / "rules" / "project-contracts" / "demo-project.md"),
        }],
        "provider_bindings": [{
            "binding_id": "local-executor",
            "provider": "opencode",
            "mode": "custom",
            "health": "ready",
        }],
        "sessions": [{
            "session_id": "go-1-coding-agent-1-session",
            "provider": "opencode",
            "binding_id": "local-executor",
            "agent_role": "executor",
            "project_id": "project",
            "run_id": "go-1",
            "task_spec_id": "TASKSPEC.json",
            "status": "idle",
            "messages": [],
            "tool_calls": [],
            "changed_files": [],
            "diff_summary": "",
            "evidence_refs": [str(packet_dir)],
            "native_refs": {"runtime": "devframe-code", "go_run_id": "go-1"},
        }],
        "go_runs": [{
            "go_run_id": "go-1",
            "status": "queued",
            "agents": [{
                "agent_id": "coding-agent-1",
                "packet_dir": str(packet_dir),
                "task_spec_path": str(task_spec_path),
            }],
        }],
        "runs": [{
            "run_id": "rdgoal-run-1",
            "entrypoint": "rdgoal",
            "status": "pending",
            "packet_path": str(packet_dir),
            "task_spec_path": str(task_spec_path),
            "next_command": command,
        }],
        "gates": [{
            "gate_id": "rdgoal-run-1-acceptance",
            "kind": "acceptance",
            "status": "open",
            "run_id": "rdgoal-run-1",
            "reason": "Routine reversible work.",
            "next_action": "Run rdgoal worker.",
        }],
        "next_actions": [{
            "action_id": "rdgoal-run-1-acceptance-action",
            "source_type": "gate",
            "source_id": "rdgoal-run-1-acceptance",
            "priority": "medium",
            "status": "open",
            "label": "Run rdgoal worker.",
            "detail": "Routine reversible work.",
        }, {
            "action_id": "go-1-status-action",
            "source_type": "go_run",
            "source_id": "go-1",
            "priority": "low",
            "status": "info",
            "label": "Inspect this DevFrame Code go-run.",
            "detail": "queued",
            "command": 'devframe code status "go-1" --runtime-dir "runtime"',
        }, {
            "action_id": "go-1-execute-action",
            "source_type": "go_run",
            "source_id": "go-1",
            "priority": "medium",
            "status": "ready",
            "label": "Execute this go-run through DevFrame Code.",
            "detail": "queued",
            "command": 'devframe code execute "go-1" --runtime-dir "runtime"',
        }, {
            "action_id": "rdgoal-run-1-command-action",
            "source_type": "run",
            "source_id": "rdgoal-run-1",
            "priority": "medium",
            "status": "ready",
            "label": "Run or inspect the next local command.",
            "detail": "rdgoal",
            "command": command,
        }, {
            "action_id": "rdgoal-run-1-decision-action",
            "source_type": "decision",
            "source_id": "rdgoal-run-1-decision",
            "priority": "low",
            "status": "info",
            "label": "Run a worker against the dispatch packet.",
            "detail": "continue",
        }],
    }

    shell = build_t3_client_shell_from_state(state, base_url="http://127.0.0.1:8790")

    validate_schema(load_schema(), shell)
    assert shell["devframe"]["controlPlaneBaseUrl"] == "http://127.0.0.1:8790"
    thread = shell["t3"]["threads"][0]
    assert thread["hasPendingApprovals"] is True
    assert thread["hasPendingUserInput"] is True
    assert thread["hasActionableProposedPlan"] is True
    assert thread["devframe"]["relatedRunIds"] == ["rdgoal-run-1"]
    assert thread["devframe"]["gateIds"] == ["rdgoal-run-1-acceptance"]
    assert thread["devframe"]["actionIds"] == [
        "rdgoal-run-1-acceptance-action",
        "go-1-status-action",
        "go-1-execute-action",
        "rdgoal-run-1-command-action",
        "rdgoal-run-1-decision-action",
    ]
    go_execute_action = next(action for action in thread["devframe"]["actionDetails"] if action["actionId"] == "go-1-execute-action")
    assert go_execute_action["command"].startswith("devframe code execute")
    assert go_execute_action["openUrl"] == "http://127.0.0.1:8790/actions/open?action_id=go-1-execute-action"
    command_action = next(action for action in thread["devframe"]["actionDetails"] if action["actionId"] == "rdgoal-run-1-command-action")
    assert command_action["handoffUrl"] == "http://127.0.0.1:8790/actions.md?action_id=rdgoal-run-1-command-action"
    assert command_action["openUrl"] == "http://127.0.0.1:8790/actions/open?action_id=rdgoal-run-1-command-action"
    assert command_action["command"] == command
    plan = shell["t3"]["threadDetails"][0]["proposedPlans"][0]["planMarkdown"]
    message_text = shell["t3"]["threadDetails"][0]["messages"][0]["text"]
    assert 'devframe code execute "go-1"' in message_text
    assert "open controlled action" in message_text
    assert "## Next Actions" in plan
    assert "open markdown packet" in plan
    assert "review / execute" in plan
    assert "devframe code execute" in plan
    assert command in plan


def test_dashboard_serves_t3_shell_endpoint_as_read_only(tmp_path):
    server = build_dashboard_server(runtime_dir=tmp_path / "runtime", port=0, refresh_seconds=0)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_address[1]}"

    try:
        with urlopen(f"{base_url}/t3-shell.json", timeout=5) as response:
            body = response.read().decode("utf-8")
            shell = json.loads(body)

        validate_schema(load_schema(), shell)
        assert "\n  " not in body
        assert shell["reuse"]["client"] == "t3code"
        assert shell["devframe"]["manifest"] == "/client-manifest.json"
        assert shell["devframe"]["controlPlaneBaseUrl"] == base_url

        try:
            urlopen(Request(f"{base_url}/t3-shell.json", method="POST"), timeout=5)
        except HTTPError as error:
            assert error.code == 405
        else:
            raise AssertionError("dashboard accepted a t3 shell write request")
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_t3_shell_cache_returns_isolated_shells(tmp_path, monkeypatch):
    calls = {"count": 0}
    state = {
        "version": 1,
        "projects": [],
        "provider_bindings": [],
        "sessions": [],
        "gates": [],
        "next_actions": [],
        "team": {},
    }

    def fake_state(*args, **kwargs):
        calls["count"] += 1
        return state

    t3_adapter_module._T3_SHELL_CACHE.clear()
    t3_adapter_module._T3_SHELL_COMPACT_JSON_CACHE.clear()
    monkeypatch.setattr(t3_adapter_module, "build_visual_control_plane_state", fake_state)

    try:
        first = build_t3_client_shell(tmp_path / "runtime", base_url="http://127.0.0.1:8798")
        first["reuse"]["client"] = "mutated"
        second = build_t3_client_shell(tmp_path / "." / "runtime", base_url="http://127.0.0.1:8798")
    finally:
        t3_adapter_module._T3_SHELL_CACHE.clear()
        t3_adapter_module._T3_SHELL_COMPACT_JSON_CACHE.clear()

    assert calls["count"] == 1
    assert second["reuse"]["client"] == "t3code"


def test_cached_t3_shell_compact_json_single_flight_under_concurrency(tmp_path, monkeypatch):
    calls = {"count": 0}
    state = {
        "version": 1,
        "projects": [],
        "provider_bindings": [],
        "sessions": [],
        "gates": [],
        "next_actions": [],
        "team": {},
    }

    def fake_state(*args, **kwargs):
        calls["count"] += 1
        time.sleep(0.05)
        return state

    t3_adapter_module._T3_SHELL_CACHE.clear()
    t3_adapter_module._T3_SHELL_COMPACT_JSON_CACHE.clear()
    monkeypatch.setattr(t3_adapter_module, "build_visual_control_plane_state", fake_state)

    errors = []
    results = [None] * 8

    def worker(index):
        try:
            results[index] = render_cached_t3_client_shell_compact_json(
                tmp_path / "runtime",
                base_url="http://127.0.0.1:8798",
            )
        except Exception as exc:
            errors.append(exc)

    threads = [Thread(target=worker, args=(i,)) for i in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)

    try:
        assert not errors, f"concurrent render raised: {errors}"
        assert calls["count"] == 1
        assert all(result == results[0] for result in results[1:])
    finally:
        t3_adapter_module._T3_SHELL_CACHE.clear()
        t3_adapter_module._T3_SHELL_COMPACT_JSON_CACHE.clear()


def test_dashboard_serves_controlled_action_page_and_confirmation_gate(tmp_path, monkeypatch):
    runtime_dir = tmp_path / "runtime"
    go_run_id = "go-demo"
    go_run_dir = runtime_dir / "go-runs" / go_run_id
    go_run_dir.mkdir(parents=True)
    (go_run_dir / "go-run.json").write_text(json.dumps({
        "go_run_id": go_run_id,
        "project_id": "project",
        "project_root": str(tmp_path / "project"),
        "requirement": "Wire T3 action clicks.",
        "runtime_dir": str(runtime_dir),
        "status": "queued",
        "execute": False,
        "agents": [{
            "agent_id": "coding-agent-1",
            "shard_index": 1,
            "shard_count": 1,
            "targets": [],
            "target_bytes": 0,
            "packet_dir": str(runtime_dir / "rdgoal-outbox" / "project" / "run-1"),
            "task_spec_path": str(runtime_dir / "rdgoal-outbox" / "project" / "run-1" / "TASKSPEC.json"),
            "worker_command": ["opencode", "run", "do work"],
            "status": "queued",
        }],
    }, indent=2, ensure_ascii=True), encoding="utf-8")
    action_id = f"{go_run_id}-execute-action"
    launched = {}

    def fake_start_execution_plan(started_action_id, plan):
        launched["action_id"] = started_action_id
        launched["plan"] = plan
        return {
            "started": True,
            "pid": 12345,
            "action_id": started_action_id,
            "kind": plan["kind"],
            "go_run_id": plan["go_run_id"],
            "command": plan["command"],
            "stdout_log": str(runtime_dir / "stdout.log"),
            "stderr_log": str(runtime_dir / "stderr.log"),
        }

    monkeypatch.setattr(dashboard_module, "_start_execution_plan", fake_start_execution_plan)
    server = build_dashboard_server(runtime_dir=runtime_dir, port=0, refresh_seconds=0)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_address[1]}"

    try:
        with urlopen(f"{base_url}/actions/open?action_id={action_id}", timeout=5) as response:
            html = response.read().decode("utf-8")
        assert response.status == 200
        assert "DevFrame Controlled Action" in html
        assert "Start controlled execution" in html
        assert f"/actions/execute?action_id={action_id}" in html
        assert "devframe code execute" in html
        assert go_run_id in html

        try:
            urlopen(Request(f"{base_url}/actions/execute?action_id={action_id}", method="POST"), timeout=5)
        except HTTPError as error:
            body = error.read().decode("utf-8")
            assert error.code == 409
            assert "human_required" in body
        else:
            raise AssertionError("dashboard executed an action without confirmation")

        cross_origin_request = Request(
            f"{base_url}/actions/execute?action_id={action_id}",
            data=b"confirm=execute",
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "Origin": "https://example.com",
            },
            method="POST",
        )
        try:
            urlopen(cross_origin_request, timeout=5)
        except HTTPError as error:
            body = error.read().decode("utf-8")
            assert error.code == 403
            assert "same_origin_required" in body
        else:
            raise AssertionError("dashboard accepted a cross-origin action execution")

        request = Request(
            f"{base_url}/actions/execute?action_id={action_id}",
            data=b"confirm=execute",
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "Origin": base_url,
            },
            method="POST",
        )
        with urlopen(request, timeout=5) as response:
            payload = json.loads(response.read().decode("utf-8"))
        assert response.status == 202
        assert payload["started"] is True
        assert payload["go_run_id"] == go_run_id
        assert launched["action_id"] == action_id
        assert launched["plan"]["kind"] == "go_run_execute"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_t3_client_shell_projects_team_model_from_state():
    state = {
        "version": 1,
        "projects": [{
            "project_id": "project",
            "display_name": "Project",
            "goal": "Multi-agent team test.",
            "status": "active",
            "risk_state": "medium",
            "contract_path": "/tmp/project/rules/project-contracts/demo.md",
        }],
        "provider_bindings": [{
            "binding_id": "local-executor",
            "provider": "opencode",
            "mode": "custom",
            "health": "ready",
        }],
        "sessions": [{
            "session_id": "go-1-coding-agent-1-session",
            "provider": "opencode",
            "binding_id": "local-executor",
            "agent_role": "executor",
            "project_id": "project",
            "run_id": "go-1",
            "status": "idle",
            "messages": [],
            "tool_calls": [],
            "changed_files": ["cli.py"],
            "diff_summary": "1 changed file",
            "evidence_refs": [],
        }, {
            "session_id": "go-1-coding-agent-2-session",
            "provider": "opencode",
            "binding_id": "local-executor",
            "agent_role": "executor",
            "project_id": "project",
            "run_id": "go-1",
            "status": "idle",
            "messages": [],
            "tool_calls": [],
            "changed_files": ["go_dispatch.py"],
            "diff_summary": "1 changed file",
            "evidence_refs": [],
        }],
        "go_runs": [{
            "go_run_id": "go-1",
            "status": "queued",
            "agents": [
                {"agent_id": "coding-agent-1", "targets": ["cli.py"], "packet_dir": "/tmp/p1", "task_spec_path": "/tmp/p1/TASKSPEC.json"},
                {"agent_id": "coding-agent-2", "targets": ["go_dispatch.py"], "packet_dir": "/tmp/p2", "task_spec_path": "/tmp/p2/TASKSPEC.json"},
            ],
        }],
        "gates": [],
        "next_actions": [
            {"action_id": "go-1-status-action", "source_type": "go_run", "source_id": "go-1", "priority": "low", "status": "info", "label": "Inspect go-run."},
            {"action_id": "go-1-execute-action", "source_type": "go_run", "source_id": "go-1", "priority": "medium", "status": "ready", "label": "Execute go-run."},
        ],
        "team": {
            "agent_registry": [
                {"agent_id": "coding-agent-1", "role": "go-worker", "binding_id": "local-executor", "status": "queued", "session_ids": ["go-1-coding-agent-1-session"]},
                {"agent_id": "coding-agent-2", "role": "go-worker", "binding_id": "local-executor", "status": "queued", "session_ids": ["go-1-coding-agent-2-session"]},
            ],
            "task_board": [
                {
                    "task_id": "go-1",
                    "type": "go-run",
                    "project_id": "project",
                    "status": "queued",
                    "agent_ids": ["coding-agent-1", "coding-agent-2"],
                    "target_files": ["cli.py", "go_dispatch.py"],
                    "methodology": {
                        "skill_id": "tdd",
                        "title": "tdd",
                        "source_path": "tools/skills/tdd/SKILL.md",
                        "source_kind": "local_repository_asset",
                        "triggers": ["@tdd"],
                        "status": "registered",
                    },
                },
            ],
            "message_bus": [
                {"message_id": "planner-to-coding-agent-1-go-1", "from_role": "planner", "to_role": "coding-agent-1", "kind": "handoff", "run_id": "go-1", "summary": "Shard 1 dispatched."},
                {"message_id": "planner-to-coding-agent-2-go-1", "from_role": "planner", "to_role": "coding-agent-2", "kind": "handoff", "run_id": "go-1", "summary": "Shard 2 dispatched."},
            ],
            "event_log": [
                {"event_id": "go-run-created-go-1", "kind": "go-run-created", "run_id": "go-1", "summary": "go run created."},
            ],
            "evidence_store": [
                {"evidence_id": "go-go-1-coding-agent-1", "run_id": "go-1", "ref_type": "packet", "ref_path": "/tmp/p1/TASKSPEC.json"},
                {"evidence_id": "go-go-1-coding-agent-2", "run_id": "go-1", "ref_type": "packet", "ref_path": "/tmp/p2/TASKSPEC.json"},
            ],
            "review_gates": [
                {"gate_id": "go-1-status-action", "kind": "action-gate", "status": "info", "run_id": "go-1", "reason": "Inspect go-run."},
                {"gate_id": "go-1-execute-action", "kind": "action-gate", "status": "ready", "run_id": "go-1", "reason": "Execute go-run."},
            ],
            "conflict_control": [
                {"file_path": "cli.py", "owner_run_id": "go-1", "owner_agent_id": "coding-agent-1", "file_kind": "go-target"},
                {"file_path": "go_dispatch.py", "owner_run_id": "go-1", "owner_agent_id": "coding-agent-2", "file_kind": "go-target"},
            ],
        },
    }

    shell = build_t3_client_shell_from_state(state, base_url="http://127.0.0.1:8790")

    validate_schema(load_schema(), shell)

    team = shell["devframe"]["team"]
    assert len(team["agentRegistry"]) == 2
    assert team["agentRegistry"][0]["agentId"] == "coding-agent-1"
    assert team["agentRegistry"][0]["role"] == "go-worker"
    assert team["agentRegistry"][0]["sessionIds"] == ["go-1-coding-agent-1-session"]

    assert len(team["taskBoard"]) == 1
    assert team["taskBoard"][0]["taskId"] == "go-1"
    assert team["taskBoard"][0]["agentIds"] == ["coding-agent-1", "coding-agent-2"]
    assert "cli.py" in team["taskBoard"][0]["targetFiles"]
    assert team["taskBoard"][0]["methodology"]["skillId"] == "tdd"

    assert len(team["messageBus"]) == 2
    assert team["messageBus"][0]["fromRole"] == "planner"
    assert team["messageBus"][0]["kind"] == "handoff"

    assert len(team["eventLog"]) == 1
    assert team["eventLog"][0]["kind"] == "go-run-created"

    assert len(team["evidenceStore"]) == 2
    assert team["evidenceStore"][0]["refType"] == "packet"

    assert len(team["reviewGates"]) == 2
    assert team["reviewGates"][0]["kind"] == "action-gate"
    assert team["reviewGates"][1]["runId"] == "go-1"

    assert len(team["conflictControl"]) == 2
    assert team["conflictControl"][0]["fileKind"] == "go-target"
    assert team["conflictControl"][0]["ownerRunId"] == "go-1"

    thread = shell["t3"]["threads"][0]
    assert thread["devframe"]["teamTaskIds"] == ["go-1"]
    assert len(thread["devframe"]["teamMessageIds"]) == 2
    assert len(thread["devframe"]["teamEvidenceIds"]) == 2
    assert set(thread["devframe"]["teamReviewGateIds"]) == {"go-1-status-action", "go-1-execute-action"}
    assert set(thread["devframe"]["teamConflictFiles"]) == {"cli.py", "go_dispatch.py"}

    detail = shell["t3"]["threadDetails"][0]
    team_activities = [a for a in detail["activities"] if a["kind"] == "devframe.team.projected"]
    assert len(team_activities) == 1
    assert "Team:" in team_activities[0]["summary"]
    assert "gate" in team_activities[0]["summary"]
    assert "conflict" in team_activities[0]["summary"]
    assert set(team_activities[0]["payload"]["teamReviewGateIds"]) == {"go-1-status-action", "go-1-execute-action"}
    assert set(team_activities[0]["payload"]["teamConflictFiles"]) == {"cli.py", "go_dispatch.py"}

    message_text = detail["messages"][0]["text"]
    assert "## Team Communication" in message_text
    assert "Methodologies: tdd" in message_text
    assert "planner ->" in message_text and "coding-agent" in message_text
    assert "Review Gates" in message_text
    assert "go-1-status-action" in message_text
    assert "Conflicts" in message_text
    assert "cli.py" in message_text


def test_t3_client_shell_team_projection_backward_compatible_without_team():
    state = {
        "version": 1,
        "projects": [{"project_id": "p", "display_name": "P", "goal": "g", "status": "active", "risk_state": "low", "contract_path": "/x"}],
        "provider_bindings": [],
        "sessions": [],
        "gates": [],
        "next_actions": [],
    }

    shell = build_t3_client_shell_from_state(state)

    validate_schema(load_schema(), shell)
    team = shell["devframe"]["team"]
    assert team["agentRegistry"] == []
    assert team["taskBoard"] == []
    assert team["messageBus"] == []
    assert team["eventLog"] == []
    assert team["evidenceStore"] == []
    assert team["reviewGates"] == []
    assert team["conflictControl"] == []
    assert shell["t3"]["threads"][-1]["id"] == "devframe-team-workbench-session"
    assert shell["t3"]["threads"][-1]["threadKind"] == "global_coordinator"
    assert shell["t3"]["threads"][-1]["threadListPriority"] == 0
    assert shell["t3"]["threadDetails"][-1]["threadKind"] == "global_coordinator"


def test_global_coordinator_thread_exists_even_without_team_or_sessions():
    state = {
        "version": 1,
        "projects": [{
            "project_id": "p",
            "display_name": "P",
            "goal": "g",
            "status": "active",
            "risk_state": "low",
            "contract_path": "/x",
        }],
        "provider_bindings": [],
        "sessions": [],
        "gates": [],
        "next_actions": [],
    }

    shell = build_t3_client_shell_from_state(state)

    validate_schema(load_schema(), shell)
    assert len(shell["t3"]["threads"]) == 1
    thread = shell["t3"]["threads"][0]
    assert thread["id"] == "devframe-team-workbench-session"
    assert thread["title"] == "DevFrame Global Coordinator"
    assert thread["threadKind"] == "global_coordinator"
    assert thread["coordinatorScope"] == "global"
    assert thread["projectBinding"] == {"mode": "optional", "projectId": "p", "status": "bound"}
    detail = shell["t3"]["threadDetails"][0]
    assert detail["threadKind"] == "global_coordinator"
    assert "### DevFrame Global Coordinator" in detail["messages"][0]["text"]
    assert "Agents: 0" in detail["messages"][0]["text"]


def test_build_t3_client_shell_projects_cluster_runs_as_goal_conversations(tmp_path, monkeypatch):
    runtime_dir = tmp_path / "runtime"
    workspace = tmp_path / "workspace"
    workspace.mkdir(parents=True)
    cluster_run_module._write_run_record(runtime_dir, {
        "runId": "g-demo01",
        "projectId": "demo-project",
        "projectPath": str(workspace),
        "target": "coordinator",
        "goal": "Ship the feature",
        "ownerPid": os.getpid(),
        "status": "running",
        "summary": "Coordinator planned the goal; agents are working…",
        "startedAt": "2026-07-01T00:00:00Z",
    })
    monkeypatch.setattr(
        "control_plane.cluster_run.cluster_run_detail",
        lambda runtime_dir, run_id: {
            "runId": run_id,
            "target": "coordinator",
            "goal": "Ship the feature",
            "status": "running",
            "summary": "Coordinator planned the goal; agents are working…",
            "messages": [
                {"from": "coordinator", "to": "executor", "kind": "task-assign", "text": "Coordinator assigned shard 1/2 to executor."},
            ],
            "agents": [
                {"agentId": "coding-agent-1", "shardIndex": 1, "shardCount": 2, "status": "running", "changedFileCount": 0, "totalTokens": 42},
            ],
        },
    )

    shell = build_t3_client_shell(runtime_dir=runtime_dir, base_url="http://127.0.0.1:8790")

    validate_schema(load_schema(), shell)
    goal_thread = next(thread for thread in shell["t3"]["threads"] if thread["id"] == "g-demo01")
    assert goal_thread["threadKind"] == "goal_conversation"
    assert goal_thread["coordinatorScope"] == "project"
    assert goal_thread["projectBinding"] == {
        "mode": "required",
        "projectId": "demo-project",
        "status": "bound",
    }
    assert goal_thread["threadListPriority"] == 1
    assert "demo-project: running -" in goal_thread["threadListSummary"]
    assert goal_thread["title"] == "Ship the feature"

    goal_detail = next(detail for detail in shell["t3"]["threadDetails"] if detail["id"] == "g-demo01")
    assert goal_detail["threadKind"] == "goal_conversation"
    text = goal_detail["messages"][0]["text"]
    assert "### DevFrame Goal Conversation" in text
    assert "Coordinator Timeline" in text
    assert "Coordinator assigned shard 1/2 to executor." in text
    assert "Agent Summary" in text
    assert "coding-agent-1" in text


def test_t3_shell_sanitizes_windows_absolute_evidence_paths(tmp_path):
    project_root = tmp_path / "project"
    contract_path = project_root / "rules" / "project-contracts" / "demo.md"
    abs_evidence = str(tmp_path / ".devframe-runtime" / "runs" / "run-1" / "ExecutionReport.md")
    state = {
        "version": 1,
        "projects": [{
            "project_id": "project",
            "display_name": "Project",
            "goal": "g",
            "status": "active",
            "risk_state": "low",
            "contract_path": str(contract_path),
        }],
        "provider_bindings": [],
        "sessions": [{
            "session_id": "session-1",
            "provider": "opencode",
            "agent_role": "executor",
            "project_id": "project",
            "run_id": "run-1",
            "status": "idle",
            "evidence_refs": [abs_evidence, "ExecutionReport.md"],
        }],
        "gates": [],
        "next_actions": [],
    }

    shell = build_t3_client_shell_from_state(state)

    thread = shell["t3"]["threads"][0]
    detail = shell["t3"]["threadDetails"][0]
    refs_json = json.dumps({
        "threadRefs": thread["devframe"]["evidenceRefs"],
        "activityRefs": detail["activities"][0]["payload"]["evidenceRefs"],
        "messageText": detail["messages"][0]["text"],
    })

    assert abs_evidence not in refs_json
    assert ":\\\\" not in refs_json
    assert ":/" not in refs_json
    assert "ExecutionReport.md" in refs_json
    assert thread["devframe"]["evidenceRefs"][0]["refPath"] == "run-1/ExecutionReport.md"
    assert thread["devframe"]["evidenceRefs"][0]["openPath"] == "/evidence/open?ref=run-1/ExecutionReport.md"
    assert thread["devframe"]["evidenceRefs"][0]["openUrl"] == ""
    assert not Path(thread["devframe"]["evidenceRefs"][0]["refPath"]).is_absolute()


def test_t3_shell_sanitizes_posix_absolute_evidence_paths():
    state = {
        "version": 1,
        "projects": [{
            "project_id": "project",
            "display_name": "Project",
            "goal": "g",
            "status": "active",
            "risk_state": "low",
            "contract_path": "/x",
        }],
        "provider_bindings": [],
        "sessions": [{
            "session_id": "session-1",
            "provider": "opencode",
            "agent_role": "executor",
            "project_id": "project",
            "run_id": "run-1",
            "status": "idle",
            "evidence_refs": ["/tmp/p1/TASKSPEC.json", "/home/rd/paper/ExecutionReport.md"],
        }],
        "gates": [],
        "next_actions": [],
    }

    shell = build_t3_client_shell_from_state(state)

    thread = shell["t3"]["threads"][0]
    detail = shell["t3"]["threadDetails"][0]
    refs = thread["devframe"]["evidenceRefs"]
    refs_json = json.dumps({
        "threadRefs": refs,
        "activityRefs": detail["activities"][0]["payload"]["evidenceRefs"],
        "messageText": detail["messages"][0]["text"],
    })

    assert "/tmp/p1/TASKSPEC.json" not in refs_json
    assert "/home/rd/paper/ExecutionReport.md" not in refs_json
    assert "\"/tmp" not in refs_json
    assert "\"/home" not in refs_json
    ref_paths = [ev["refPath"] for ev in refs]
    assert "p1/TASKSPEC.json" in ref_paths
    assert any("paper/ExecutionReport.md" in ref or "ExecutionReport.md" in ref for ref in ref_paths)


def test_t3_shell_evidence_store_sanitizes_ref_paths(tmp_path):
    state = {
        "version": 1,
        "projects": [{
            "project_id": "project",
            "display_name": "Project",
            "goal": "g",
            "status": "active",
            "risk_state": "low",
            "contract_path": str(tmp_path / "rules" / "project-contracts" / "demo.md"),
        }],
        "provider_bindings": [],
        "sessions": [],
        "gates": [],
        "next_actions": [],
        "team": {
            "evidence_store": [
                {"evidence_id": "ev-1", "run_id": "run-1", "ref_type": "packet", "ref_path": str(tmp_path / "packet" / "TASKSPEC.json")},
                {"evidence_id": "ev-2", "run_id": "run-2", "ref_type": "report", "ref_path": "/tmp/p2/ExecutionReport.md"},
            ],
        },
    }

    shell = build_t3_client_shell_from_state(state)
    json_str = json.dumps(shell)

    team = shell["devframe"]["team"]
    for entry in team["evidenceStore"]:
        ref_path = entry["refPath"]
        assert not Path(ref_path).is_absolute()
        assert ":\\\\" not in ref_path
        assert "\"/" not in ref_path

    paths = [e["refPath"] for e in team["evidenceStore"]]
    assert any("TASKSPEC.json" in p for p in paths)
    assert any("p2/ExecutionReport.md" in p or "ExecutionReport.md" in p for p in paths)


def test_approval_requested_activities_for_ready_and_open_actions():
    state = {
        "version": 1,
        "projects": [{"project_id": "p", "display_name": "P", "goal": "g", "status": "active", "risk_state": "low", "contract_path": "/x"}],
        "provider_bindings": [],
        "sessions": [{
            "session_id": "session-1",
            "provider": "opencode",
            "agent_role": "executor",
            "project_id": "p",
            "run_id": "run-1",
            "status": "idle",
            "messages": [],
            "tool_calls": [],
            "changed_files": [],
            "diff_summary": "",
            "evidence_refs": [],
            "actions": ["ready-action", "open-action", "info-action"],
        }],
        "gates": [],
        "next_actions": [
            {"action_id": "ready-action", "source_type": "run", "source_id": "run-1", "priority": "medium", "status": "ready", "label": "Execute run.", "command": "devframe run run-1"},
            {"action_id": "open-action", "source_type": "run", "source_id": "run-1", "priority": "low", "status": "open", "label": "Review run.", "detail": "pending review", "openUrl": "http://127.0.0.1:8790/actions/open?action_id=open-action"},
            {"action_id": "info-action", "source_type": "run", "source_id": "run-1", "priority": "low", "status": "info", "label": "Inspect run."},
        ],
    }

    shell = build_t3_client_shell_from_state(state, base_url="http://127.0.0.1:8790")
    detail = shell["t3"]["threadDetails"][0]

    approval_activities = [a for a in detail["activities"] if a["kind"] == "approval.requested"]
    assert len(approval_activities) == 1

    ready_activity = approval_activities[0]
    assert ready_activity["id"] == "session-1-approval-ready-action"
    assert ready_activity["tone"] == "approval"
    assert ready_activity["payload"]["requestId"] == "session-1-ready-action"
    assert ready_activity["payload"]["requestKind"] == "command"
    assert ready_activity["payload"]["actionStatus"] == "ready"
    assert ready_activity["payload"]["actionPriority"] == "medium"
    assert ready_activity["payload"]["command"] == "devframe run run-1"
    assert ready_activity["payload"]["writePolicy"] == "read-only"


def test_web_gpt_task_intake_action_projects_as_t3_approval_request(tmp_path):
    runtime_dir = tmp_path / "runtime"
    sessions_dir = runtime_dir / "web-ai-sessions"
    sessions_dir.mkdir(parents=True)
    (sessions_dir / "codexpro-web-mcp-task-intake-1.json").write_text(json.dumps({
            "session_id": "codexpro-web-mcp-task-intake-1",
            "provider": "codexpro",
            "agent_role": "executor",
            "project_id": "p",
            "run_id": "",
            "status": "idle",
            "messages": [],
            "tool_calls": [],
            "changed_files": [],
            "diff_summary": "",
            "evidence_refs": [],
            "actions": ["Execute task intake 'Build feature' through local DevFrame Code or @go."],
            "native_refs": {
                "runtime": "codexpro-web-mcp",
                "source_runtime": "codexpro-web-mcp",
                "outcome": "task_intake_recorded",
                "intake_id": "int-web-gpt-1",
                "task_title": "Build feature",
                "priority": "high",
                "suggested_agent": "opencode",
            },
    }, indent=2), encoding="utf-8")

    shell = build_t3_client_shell(runtime_dir=runtime_dir, base_url="http://127.0.0.1:8790")

    validate_schema(load_schema(), shell)
    thread = shell["t3"]["threads"][0]
    detail = shell["t3"]["threadDetails"][0]
    action = thread["devframe"]["actionDetails"][0]
    approval = next(activity for activity in detail["activities"] if activity["kind"] == "approval.requested")

    assert thread["hasPendingApprovals"] is True
    assert action["status"] == "ready"
    assert action["command"] == "devframe web-ai dispatch-task-intakes --intake-id int-web-gpt-1"
    assert action["openUrl"] == (
        "http://127.0.0.1:8790/actions/open?"
        "action_id=codexpro-web-mcp-task-intake-1-execute-task-intake-build-feature-through-local-devframe-code-or-go"
    )
    assert approval["payload"]["actionId"] == action["actionId"]
    assert approval["payload"]["command"] == action["command"]
    assert approval["payload"]["openUrl"] == action["openUrl"]


def test_info_actions_do_not_produce_approval_activities():
    state = {
        "version": 1,
        "projects": [{"project_id": "p", "display_name": "P", "goal": "g", "status": "active", "risk_state": "low", "contract_path": "/x"}],
        "provider_bindings": [],
        "sessions": [{
            "session_id": "session-1",
            "provider": "opencode",
            "agent_role": "executor",
            "project_id": "p",
            "run_id": "run-1",
            "status": "idle",
            "messages": [],
            "tool_calls": [],
            "changed_files": [],
            "diff_summary": "",
            "evidence_refs": [],
            "actions": ["info-action"],
        }],
        "gates": [],
        "next_actions": [
            {"action_id": "info-action", "source_type": "run", "source_id": "run-1", "priority": "low", "status": "info", "label": "Inspect run."},
        ],
    }

    shell = build_t3_client_shell_from_state(state)
    detail = shell["t3"]["threadDetails"][0]

    approval_activities = [a for a in detail["activities"] if a["kind"] == "approval.requested"]
    assert len(approval_activities) == 0
    assert shell["t3"]["threads"][0]["hasPendingApprovals"] is False


def test_open_link_only_action_does_not_produce_approval_activity():
    state = {
        "version": 1,
        "projects": [{"project_id": "p", "display_name": "P", "goal": "g", "status": "active", "risk_state": "low", "contract_path": "/x"}],
        "provider_bindings": [],
        "sessions": [{
            "session_id": "session-1",
            "provider": "opencode",
            "agent_role": "executor",
            "project_id": "p",
            "run_id": "run-1",
            "status": "idle",
            "messages": [],
            "tool_calls": [],
            "changed_files": [],
            "diff_summary": "",
            "evidence_refs": [],
            "actions": ["open-link-action"],
        }],
        "gates": [],
        "next_actions": [
            {"action_id": "open-link-action", "source_type": "run", "source_id": "run-1", "priority": "low", "status": "open", "label": "Review run.", "detail": "pending review", "openUrl": "http://127.0.0.1:8790/actions/open?action_id=open-link-action"},
        ],
    }

    shell = build_t3_client_shell_from_state(state, base_url="http://127.0.0.1:8790")
    detail = shell["t3"]["threadDetails"][0]

    approval_activities = [a for a in detail["activities"] if a["kind"] == "approval.requested"]
    assert len(approval_activities) == 0
    assert shell["t3"]["threads"][0]["hasPendingApprovals"] is False
    assert detail["messages"][0]["text"].count("open controlled action") == 1


def test_ready_action_without_command_does_not_produce_approval_activity():
    state = {
        "version": 1,
        "projects": [{"project_id": "p", "display_name": "P", "goal": "g", "status": "active", "risk_state": "low", "contract_path": "/x"}],
        "provider_bindings": [],
        "sessions": [{
            "session_id": "session-1",
            "provider": "opencode",
            "agent_role": "executor",
            "project_id": "p",
            "run_id": "run-1",
            "status": "idle",
            "messages": [],
            "tool_calls": [],
            "changed_files": [],
            "diff_summary": "",
            "evidence_refs": [],
            "actions": ["ready-no-cmd-action"],
        }],
        "gates": [],
        "next_actions": [
            {"action_id": "ready-no-cmd-action", "source_type": "run", "source_id": "run-1", "priority": "medium", "status": "ready", "label": "Execute run."},
        ],
    }

    shell = build_t3_client_shell_from_state(state)
    detail = shell["t3"]["threadDetails"][0]

    approval_activities = [a for a in detail["activities"] if a["kind"] == "approval.requested"]
    assert len(approval_activities) == 0
    assert shell["t3"]["threads"][0]["hasPendingApprovals"] is False


def test_blocked_failed_gate_without_approvable_action_does_not_set_has_pending_approvals():
    state = {
        "version": 1,
        "projects": [{"project_id": "p", "display_name": "P", "goal": "g", "status": "active", "risk_state": "low", "contract_path": "/x"}],
        "provider_bindings": [],
        "sessions": [{
            "session_id": "session-1",
            "provider": "opencode",
            "agent_role": "executor",
            "project_id": "p",
            "run_id": "run-1",
            "status": "blocked",
            "messages": [],
            "tool_calls": [],
            "changed_files": [],
            "diff_summary": "",
            "evidence_refs": [],
            "actions": [],
        }],
        "gates": [
            {"gate_id": "gate-1", "kind": "acceptance", "status": "blocked", "run_id": "run-1", "reason": "Tests failing.", "next_action": "Fix tests."},
            {"gate_id": "gate-2", "kind": "human", "status": "failed", "run_id": "run-1", "reason": "Reviewer rejected.", "next_action": "Revise."},
        ],
        "next_actions": [],
    }

    shell = build_t3_client_shell_from_state(state)
    thread = shell["t3"]["threads"][0]

    assert thread["runtimeMode"] == "approval-required"
    assert thread["hasPendingApprovals"] is False
    detail = shell["t3"]["threadDetails"][0]
    approval_activities = [a for a in detail["activities"] if a["kind"] == "approval.requested"]
    assert len(approval_activities) == 0


def test_approval_activities_preserve_existing_session_and_team_activities():
    state = {
        "version": 1,
        "projects": [{"project_id": "p", "display_name": "P", "goal": "g", "status": "active", "risk_state": "low", "contract_path": "/x"}],
        "provider_bindings": [],
        "sessions": [{
            "session_id": "session-1",
            "provider": "opencode",
            "agent_role": "executor",
            "project_id": "p",
            "run_id": "run-1",
            "status": "idle",
            "messages": [],
            "tool_calls": [],
            "changed_files": [],
            "diff_summary": "",
            "evidence_refs": [],
            "actions": ["ready-action"],
        }],
        "gates": [],
        "next_actions": [
            {"action_id": "ready-action", "source_type": "run", "source_id": "run-1", "priority": "medium", "status": "ready", "label": "Execute run.", "command": "devframe run run-1"},
        ],
    }

    shell = build_t3_client_shell_from_state(state)
    detail = shell["t3"]["threadDetails"][0]

    kinds = [a["kind"] for a in detail["activities"]]
    assert kinds[0] == "devframe.session.projected"
    assert kinds[1] == "devframe.team.projected"
    assert kinds[2] == "approval.requested"
    assert len(detail["activities"]) == 3
    tones = [a["tone"] for a in detail["activities"]]
    assert tones[0] == "info"
    assert tones[1] == "info"
    assert tones[2] == "approval"


def test_approval_activities_are_deduplicated():
    state = {
        "version": 1,
        "projects": [{"project_id": "p", "display_name": "P", "goal": "g", "status": "active", "risk_state": "low", "contract_path": "/x"}],
        "provider_bindings": [],
        "sessions": [{
            "session_id": "session-1",
            "provider": "opencode",
            "agent_role": "executor",
            "project_id": "p",
            "run_id": "run-1",
            "status": "idle",
            "messages": [],
            "tool_calls": [],
            "changed_files": [],
            "diff_summary": "",
            "evidence_refs": [],
            "actions": ["ready-action"],
        }],
        "gates": [],
        "next_actions": [
            {"action_id": "ready-action", "source_type": "run", "source_id": "run-1", "priority": "medium", "status": "ready", "label": "Execute run.", "command": "devframe run run-1"},
            {"action_id": "ready-action", "source_type": "run", "source_id": "run-1", "priority": "medium", "status": "ready", "label": "Execute run.", "command": "devframe run run-1"},
        ],
    }

    shell = build_t3_client_shell_from_state(state)
    detail = shell["t3"]["threadDetails"][0]

    approval_activities = [a for a in detail["activities"] if a["kind"] == "approval.requested"]
    assert len(approval_activities) == 1
    assert approval_activities[0]["payload"]["actionId"] == "ready-action"
    assert approval_activities[0]["tone"] == "approval"


def test_evidence_and_gate_activities_projected_in_thread_detail():
    state = {
        "version": 1,
        "projects": [{"project_id": "p", "display_name": "P", "goal": "g", "status": "active", "risk_state": "low", "contract_path": "/x"}],
        "provider_bindings": [],
        "sessions": [{
            "session_id": "session-1",
            "provider": "opencode",
            "agent_role": "executor",
            "project_id": "p",
            "run_id": "run-1",
            "status": "idle",
            "messages": [],
            "tool_calls": [],
            "changed_files": [],
            "diff_summary": "",
            "evidence_refs": ["ExecutionReport.md", "test-output.md"],
            "gates": ["gate-1", "gate-2"],
            "actions": [],
        }],
        "gates": [
            {"gate_id": "gate-1", "kind": "human", "status": "open", "reason": "Human approval required.", "next_action": "Approve."},
            {"gate_id": "gate-2", "kind": "acceptance", "status": "blocked", "reason": "Tests failing.", "next_action": "Fix tests."},
        ],
        "next_actions": [],
        "team": {
            "task_board": [
                {"task_id": "run-1", "type": "go-run", "project_id": "p", "status": "queued", "agent_ids": ["agent-1"], "target_files": ["cli.py"]},
            ],
            "message_bus": [
                {"message_id": "msg-1", "from_role": "planner", "to_role": "agent-1", "kind": "handoff", "run_id": "run-1", "summary": "Dispatch."},
            ],
        },
    }

    shell = build_t3_client_shell_from_state(state)
    detail = shell["t3"]["threadDetails"][0]

    evidence_kinds = [a["kind"] for a in detail["activities"] if a["kind"] == "devframe.evidence.projected"]
    assert len(evidence_kinds) == 1
    evidence_activity = [a for a in detail["activities"] if a["kind"] == "devframe.evidence.projected"][0]
    assert evidence_activity["tone"] == "tool"
    assert evidence_activity["payload"]["count"] == 2
    assert "ExecutionReport.md" in str(evidence_activity["payload"]["refs"])

    gate_kinds = [a["kind"] for a in detail["activities"] if a["kind"] == "devframe.gate.projected"]
    assert len(gate_kinds) == 2
    gate_activities = [a for a in detail["activities"] if a["kind"] == "devframe.gate.projected"]
    gate_tones = {a["payload"]["gateId"]: a["tone"] for a in gate_activities}
    assert gate_tones.get("gate-1") == "approval"
    assert gate_tones.get("gate-2") == "error"

    team_task_kinds = [a["kind"] for a in detail["activities"] if a["kind"] == "devframe.team.task.projected"]
    assert len(team_task_kinds) == 1
    task_activity = [a for a in detail["activities"] if a["kind"] == "devframe.team.task.projected"][0]
    assert task_activity["summary"] == "Team Tasks: 1 active"

    team_msg_kinds = [a["kind"] for a in detail["activities"] if a["kind"] == "devframe.team.message.projected"]
    assert len(team_msg_kinds) >= 1
    msg_activity = [a for a in detail["activities"] if a["kind"] == "devframe.team.message.projected"][0]
    assert "planner" in msg_activity["summary"].lower() or "->" in msg_activity["summary"]


def test_no_evidence_or_gate_activities_when_none_present():
    state = {
        "version": 1,
        "projects": [{"project_id": "p", "display_name": "P", "goal": "g", "status": "active", "risk_state": "low", "contract_path": "/x"}],
        "provider_bindings": [],
        "sessions": [{
            "session_id": "session-1",
            "provider": "opencode",
            "agent_role": "executor",
            "project_id": "p",
            "run_id": "run-1",
            "status": "idle",
            "messages": [],
            "tool_calls": [],
            "changed_files": [],
            "diff_summary": "",
            "evidence_refs": [],
            "actions": [],
        }],
        "gates": [],
        "next_actions": [],
    }

    shell = build_t3_client_shell_from_state(state)
    detail = shell["t3"]["threadDetails"][0]

    evidence_kinds = [a["kind"] for a in detail["activities"] if a["kind"] == "devframe.evidence.projected"]
    assert len(evidence_kinds) == 0
    gate_kinds = [a["kind"] for a in detail["activities"] if a["kind"] == "devframe.gate.projected"]
    assert len(gate_kinds) == 0
    team_task_kinds = [a["kind"] for a in detail["activities"] if a["kind"] == "devframe.team.task.projected"]
    assert len(team_task_kinds) == 0


def test_t3_thread_detail_exposes_action_run_events_for_matching_go_run():
    state = {
        "version": 1,
        "projects": [{"project_id": "p", "display_name": "P", "goal": "g", "status": "active", "risk_state": "low", "contract_path": "/x"}],
        "provider_bindings": [{"binding_id": "local-executor", "provider": "opencode", "mode": "custom", "health": "ready"}],
        "sessions": [{
            "session_id": "go-1-coding-agent-1-session",
            "provider": "opencode",
            "binding_id": "local-executor",
            "agent_role": "executor",
            "project_id": "p",
            "run_id": "go-1",
            "status": "idle",
            "messages": [],
            "tool_calls": [],
            "changed_files": [],
            "diff_summary": "",
            "evidence_refs": [],
            "native_refs": {"runtime": "devframe-code", "go_run_id": "go-1"},
        }],
        "go_runs": [{
            "go_run_id": "go-1",
            "status": "queued",
            "agents": [],
        }],
        "runs": [],
        "gates": [],
        "next_actions": [],
        "team": {
            "agent_registry": [],
            "task_board": [],
            "message_bus": [],
            "event_log": [
                {"event_id": "action-run-action-1-run-1", "kind": "action-run-started", "run_id": "go-1", "summary": "Action action-1 started for /go run go-1"},
                {"event_id": "action-run-action-2-run-2", "kind": "action-run-started", "run_id": "other-run", "summary": "Action action-2 started for /go run other-run"},
            ],
            "evidence_store": [],
            "review_gates": [],
            "conflict_control": [],
        },
    }

    shell = build_t3_client_shell_from_state(state)

    validate_schema(load_schema(), shell)

    thread = shell["t3"]["threads"][0]
    detail = shell["t3"]["threadDetails"][0]

    detail_events = thread["devframe"]["teamDetailEvents"]
    assert len(detail_events) == 1
    assert detail_events[0]["eventId"] == "action-run-action-1-run-1"
    assert detail_events[0]["kind"] == "action-run-started"

    message_text = detail["messages"][0]["text"]
    assert "## Team Communication" in message_text
    assert "Events" in message_text
    assert "action-run-started" in message_text
    assert "action-1" in message_text

    event_activities = [a for a in detail["activities"] if a["kind"] == "devframe.team.event.projected"]
    assert len(event_activities) == 1
    assert event_activities[0]["payload"]["eventId"] == "action-run-action-1-run-1"
    assert event_activities[0]["payload"]["kind"] == "action-run-started"


def test_t3_thread_detail_shows_completed_action_run_with_lifecycle_tones():
    state = {
        "version": 1,
        "projects": [{"project_id": "p", "display_name": "P", "goal": "g", "status": "active", "risk_state": "low", "contract_path": "/x"}],
        "provider_bindings": [{"binding_id": "local-executor", "provider": "opencode", "mode": "custom", "health": "ready"}],
        "sessions": [{
            "session_id": "go-1-coding-agent-1-session",
            "provider": "opencode",
            "binding_id": "local-executor",
            "agent_role": "executor",
            "project_id": "p",
            "run_id": "go-1",
            "status": "idle",
            "messages": [],
            "tool_calls": [],
            "changed_files": [],
            "diff_summary": "",
            "evidence_refs": [],
            "native_refs": {"runtime": "devframe-code", "go_run_id": "go-1"},
        }],
        "go_runs": [{"go_run_id": "go-1", "status": "queued", "agents": []}],
        "runs": [],
        "gates": [],
        "next_actions": [],
        "team": {
            "agent_registry": [],
            "task_board": [],
            "message_bus": [],
            "event_log": [
                {"event_id": "action-run-action-1-run-1", "kind": "action-run-completed", "run_id": "go-1",
                 "summary": "Action action-1 completed for /go run go-1; exit_code=0; completed_at=2025-01-01T00:01:00Z; stdout_log=/tmp/stdout.log; stderr_log=/tmp/stderr.log"},
                {"event_id": "action-run-action-2-run-2", "kind": "action-run-failed", "run_id": "go-1",
                 "summary": "Action action-2 failed for /go run go-1; exit_code=1; completed_at=2025-01-01T00:02:00Z; stdout_log=/tmp/stdout2.log; stderr_log=/tmp/stderr2.log"},
            ],
            "evidence_store": [],
            "review_gates": [],
            "conflict_control": [],
        },
    }

    shell = build_t3_client_shell_from_state(state)

    validate_schema(load_schema(), shell)
    thread = shell["t3"]["threads"][0]
    detail = shell["t3"]["threadDetails"][0]

    detail_events = thread["devframe"]["teamDetailEvents"]
    assert len(detail_events) == 2
    kinds = {e["kind"] for e in detail_events}
    assert "action-run-completed" in kinds
    assert "action-run-failed" in kinds

    message_text = detail["messages"][0]["text"]
    assert "action-run-completed" in message_text
    assert "action-run-failed" in message_text
    assert "exit_code=0" in message_text
    assert "exit_code=1" in message_text

    event_activities = [a for a in detail["activities"] if a["kind"] == "devframe.team.event.projected"]
    assert len(event_activities) == 2
    tones = {a["payload"]["eventId"]: a["tone"] for a in event_activities}
    assert tones.get("action-run-action-1-run-1") == "info"
    assert tones.get("action-run-action-2-run-2") == "error"


def test_t3_client_shell_projects_atgo_team_model(tmp_path):
    abs_evidence = str(tmp_path / ".devframe-runtime" / "atgo-runs" / "atgo-review" / "web-gpt-package.zip")
    state = {
        "version": 1,
        "projects": [{
            "project_id": "project",
            "display_name": "Project",
            "goal": "g",
            "status": "active",
            "risk_state": "low",
            "contract_path": "/x",
        }],
        "provider_bindings": [],
        "sessions": [],
        "gates": [],
        "next_actions": [],
        "team": {
            "agent_registry": [],
            "task_board": [],
            "message_bus": [
                {
                    "message_id": "atgo-reviewer-to-team-atgo-review",
                    "from_role": "reviewer",
                    "to_role": "team",
                    "kind": "review-status",
                    "run_id": "atgo-review",
                    "summary": "ATGO review atgo-review: pass",
                },
            ],
            "event_log": [
                {
                    "event_id": "atgo-review-atgo-review",
                    "kind": "atgo-review",
                    "run_id": "atgo-review",
                    "summary": "ATGO review run atgo-review: pass",
                },
            ],
            "evidence_store": [
                {
                    "evidence_id": "atgo-web-gpt-package-atgo-review",
                    "run_id": "atgo-review",
                    "ref_type": "package",
                    "ref_path": abs_evidence,
                },
            ],
            "review_gates": [
                {
                    "gate_id": "atgo-atgo-review-review-gate",
                    "kind": "acceptance",
                    "status": "pass",
                    "reason": "ATGO review atgo-review: pass",
                    "run_id": "atgo-review",
                },
            ],
            "conflict_control": [],
        },
    }

    shell = build_t3_client_shell_from_state(state)

    validate_schema(load_schema(), shell)
    team = shell["devframe"]["team"]
    assert len(team["evidenceStore"]) == 1
    assert team["evidenceStore"][0]["refType"] == "package"
    assert "web-gpt-package.zip" in team["evidenceStore"][0]["refPath"]
    assert ":\\\\" not in team["evidenceStore"][0]["refPath"]
    assert len(team["reviewGates"]) == 1
    assert team["reviewGates"][0]["status"] == "pass"
    assert team["reviewGates"][0]["kind"] == "acceptance"
    assert len(team["messageBus"]) == 1
    assert team["messageBus"][0]["kind"] == "review-status"
    assert len(team["eventLog"]) == 1
    assert team["eventLog"][0]["kind"] == "atgo-review"


def test_t3_client_shell_links_explicit_related_run_ids_to_team_details():
    state = {
        "version": 1,
        "projects": [{
            "project_id": "project",
            "display_name": "Project",
            "goal": "g",
            "status": "active",
            "risk_state": "low",
            "contract_path": "/x",
        }],
        "provider_bindings": [],
        "sessions": [{
            "session_id": "web-gpt-review-board-session",
            "provider": "chatgpt",
            "agent_role": "reviewer",
            "project_id": "project",
            "status": "idle",
            "messages": [],
            "tool_calls": [],
            "changed_files": [],
            "diff_summary": "",
            "evidence_refs": [],
            "native_refs": {"related_run_ids": ["atgo-run-1", "atgo-run-2"]},
        }],
        "gates": [],
        "next_actions": [],
        "team": {
            "agent_registry": [],
            "task_board": [],
            "message_bus": [
                {"message_id": "msg-1", "from_role": "reviewer", "to_role": "team", "kind": "review-status", "run_id": "atgo-run-1", "summary": "ATGO review atgo-run-1: pass"},
            ],
            "event_log": [
                {"event_id": "ev-1", "kind": "atgo-review", "run_id": "atgo-run-1", "summary": "ATGO review run atgo-run-1: pass"},
            ],
            "evidence_store": [
                {"evidence_id": "ev-1", "run_id": "atgo-run-1", "ref_type": "review", "ref_path": "/abs/path/review.md"},
            ],
            "review_gates": [
                {"gate_id": "gate-1", "kind": "acceptance", "status": "pass", "run_id": "atgo-run-1", "reason": "ATGO review atgo-run-1: pass"},
            ],
            "conflict_control": [],
        },
    }

    shell = build_t3_client_shell_from_state(state)

    validate_schema(load_schema(), shell)
    thread = shell["t3"]["threads"][0]
    assert thread["devframe"]["relatedRunIds"] == ["atgo-run-1", "atgo-run-2"]
    detail = shell["t3"]["threadDetails"][0]
    message_text = detail["messages"][0]["text"]
    assert "Team Communication" in message_text
    assert "reviewer -> team" in message_text
    assert "Evidence" in message_text
    assert "Review Gates" in message_text
    assert "Events" in message_text
    assert thread["devframe"]["teamDetailEvidence"]
    assert thread["devframe"]["teamDetailGates"]
    assert thread["devframe"]["teamDetailMessages"]
    assert thread["devframe"]["teamDetailEvents"]
    assert thread["hasPendingApprovals"] is False


def test_large_synthetic_reviewer_session_renders_detail_digest():
    messages = [
        {"message_id": f"msg-{i}", "from_role": "reviewer", "to_role": "team", "kind": "review-status", "run_id": f"run-{i}", "summary": f"ATGO review run-{i}: pass"}
        for i in range(30)
    ]
    evidence = [
        {"evidence_id": f"ev-{i}", "run_id": f"run-{i}", "ref_type": "review", "ref_path": f"/abs/path/review-{i}.md"}
        for i in range(30)
    ]
    gates = [
        {"gate_id": f"gate-{i}", "kind": "acceptance", "status": "pass", "run_id": f"run-{i}", "reason": f"ATGO review run-{i}: pass"}
        for i in range(30)
    ]
    events = [
        {"event_id": f"evt-{i}", "kind": "atgo-review", "run_id": f"run-{i}", "summary": f"ATGO review run run-{i}: pass"}
        for i in range(30)
    ]
    state = {
        "version": 1,
        "projects": [{"project_id": "p", "display_name": "P", "goal": "g", "status": "active", "risk_state": "low", "contract_path": "/x"}],
        "provider_bindings": [],
        "sessions": [{
            "session_id": "web-gpt-review-board-session",
            "provider": "chatgpt",
            "agent_role": "reviewer",
            "project_id": "p",
            "status": "idle",
            "messages": [],
            "tool_calls": [],
            "changed_files": [],
            "diff_summary": "",
            "evidence_refs": [],
            "native_refs": {"related_run_ids": [f"run-{i}" for i in range(30)]},
        }],
        "gates": [],
        "next_actions": [],
        "team": {
            "agent_registry": [],
            "task_board": [],
            "message_bus": messages,
            "event_log": events,
            "evidence_store": evidence,
            "review_gates": gates,
            "conflict_control": [],
        },
    }

    shell = build_t3_client_shell_from_state(state)

    validate_schema(load_schema(), shell)
    thread = shell["t3"]["threads"][0]
    detail = shell["t3"]["threadDetails"][0]
    message_text = detail["messages"][0]["text"]

    assert "Team Communication" in message_text
    assert "30 item(s), omitted 27 of 30 total" in message_text
    assert "Evidence" in message_text
    assert "30 item(s), omitted 27 of 30 total" in message_text
    assert "Review Gates" in message_text
    assert "30 item(s), omitted 27 of 30 total" in message_text
    assert "Events" in message_text
    assert "30 item(s), omitted 27 of 30 total" in message_text
    assert "... omitted 27 of 30 total" in message_text
    assert len(message_text) < 20000


def test_small_synthetic_reviewer_session_renders_full_detail():
    state = {
        "version": 1,
        "projects": [{"project_id": "p", "display_name": "P", "goal": "g", "status": "active", "risk_state": "low", "contract_path": "/x"}],
        "provider_bindings": [],
        "sessions": [{
            "session_id": "web-gpt-review-board-session",
            "provider": "chatgpt",
            "agent_role": "reviewer",
            "project_id": "p",
            "status": "idle",
            "messages": [],
            "tool_calls": [],
            "changed_files": [],
            "diff_summary": "",
            "evidence_refs": [],
            "native_refs": {"related_run_ids": ["run-1"]},
        }],
        "gates": [],
        "next_actions": [],
        "team": {
            "agent_registry": [],
            "task_board": [],
            "message_bus": [
                {"message_id": "msg-1", "from_role": "reviewer", "to_role": "team", "kind": "review-status", "run_id": "run-1", "summary": "ATGO review run-1: pass"},
            ],
            "event_log": [
                {"event_id": "evt-1", "kind": "atgo-review", "run_id": "run-1", "summary": "ATGO review run run-1: pass"},
            ],
            "evidence_store": [
                {"evidence_id": "ev-1", "run_id": "run-1", "ref_type": "review", "ref_path": "/abs/path/review.md"},
            ],
            "review_gates": [
                {"gate_id": "gate-1", "kind": "acceptance", "status": "pass", "run_id": "run-1", "reason": "ATGO review run-1: pass"},
            ],
            "conflict_control": [],
        },
    }

    shell = build_t3_client_shell_from_state(state)

    validate_schema(load_schema(), shell)
    detail = shell["t3"]["threadDetails"][0]
    message_text = detail["messages"][0]["text"]

    assert "Team Communication" in message_text
    assert "reviewer -> team" in message_text
    assert "Evidence" in message_text
    assert "Review Gates" in message_text
    assert "Events" in message_text
    assert "omitted" not in message_text


def test_normal_session_with_team_details_renders_full_detail():
    state = {
        "version": 1,
        "projects": [{"project_id": "p", "display_name": "P", "goal": "g", "status": "active", "risk_state": "low", "contract_path": "/x"}],
        "provider_bindings": [],
        "sessions": [{
            "session_id": "session-1",
            "provider": "opencode",
            "agent_role": "executor",
            "project_id": "p",
            "run_id": "run-1",
            "status": "idle",
            "messages": [],
            "tool_calls": [],
            "changed_files": [],
            "diff_summary": "",
            "evidence_refs": [],
        }],
        "gates": [],
        "next_actions": [],
        "team": {
            "agent_registry": [],
            "task_board": [],
            "message_bus": [
                {"message_id": "msg-1", "from_role": "planner", "to_role": "agent-1", "kind": "handoff", "run_id": "run-1", "summary": "Dispatch."},
            ],
            "event_log": [
                {"event_id": "evt-1", "kind": "go-run-created", "run_id": "run-1", "summary": "go run created."},
            ],
            "evidence_store": [
                {"evidence_id": "ev-1", "run_id": "run-1", "ref_type": "packet", "ref_path": "/tmp/p1/TASKSPEC.json"},
            ],
            "review_gates": [
                {"gate_id": "gate-1", "kind": "action-gate", "status": "ready", "run_id": "run-1", "reason": "Execute go-run."},
            ],
            "conflict_control": [
                {"file_path": "cli.py", "owner_run_id": "run-1", "owner_agent_id": "agent-1", "file_kind": "go-target"},
            ],
        },
    }

    shell = build_t3_client_shell_from_state(state)

    validate_schema(load_schema(), shell)
    detail = shell["t3"]["threadDetails"][0]
    message_text = detail["messages"][0]["text"]

    assert "Team Communication" in message_text
    assert "planner -> agent-1" in message_text
    assert "Evidence" in message_text
    assert "Review Gates" in message_text
    assert "Events" in message_text
    assert "Conflicts" in message_text
    assert "cli.py" in message_text
    assert "omitted" not in message_text


def test_large_synthetic_reviewer_session_with_mixed_gates_renders_summary_and_digest():
    messages = [
        {"message_id": f"msg-{i}", "from_role": "reviewer", "to_role": "team", "kind": "review-status", "run_id": f"run-{i}", "summary": f"ATGO review run-{i}: pass"}
        for i in range(30)
    ]
    evidence = [
        {"evidence_id": f"ev-{i}", "run_id": f"run-{i}", "ref_type": "review", "ref_path": f"/abs/path/review-{i}.md"}
        for i in range(30)
    ]
    gates = [
        {"gate_id": f"gate-{i}", "kind": "acceptance", "status": "pass" if i % 4 == 0 else ("blocked" if i % 4 == 1 else ("failed" if i % 4 == 2 else "open")), "run_id": f"run-{i}", "reason": f"Reason for gate-{i}"}
        for i in range(30)
    ]
    events = [
        {"event_id": f"evt-{i}", "kind": "atgo-review", "run_id": f"run-{i}", "summary": f"ATGO review run run-{i}: pass"}
        for i in range(30)
    ]
    state = {
        "version": 1,
        "projects": [{"project_id": "p", "display_name": "P", "goal": "g", "status": "active", "risk_state": "low", "contract_path": "/x"}],
        "provider_bindings": [],
        "sessions": [{
            "session_id": "web-gpt-review-board-session",
            "provider": "chatgpt",
            "agent_role": "reviewer",
            "project_id": "p",
            "status": "idle",
            "messages": [],
            "tool_calls": [],
            "changed_files": [],
            "diff_summary": "",
            "evidence_refs": [],
            "native_refs": {"related_run_ids": [f"run-{i}" for i in range(30)]},
        }],
        "gates": [],
        "next_actions": [],
        "team": {
            "agent_registry": [],
            "task_board": [],
            "message_bus": messages,
            "event_log": events,
            "evidence_store": evidence,
            "review_gates": gates,
            "conflict_control": [],
        },
    }

    shell = build_t3_client_shell_from_state(state)

    validate_schema(load_schema(), shell)
    detail = shell["t3"]["threadDetails"][0]
    message_text = detail["messages"][0]["text"]

    assert message_text.startswith("### Review Board Summary")
    assert "Team tasks: 0" in message_text
    assert "Messages: 30" in message_text
    assert "Evidence refs: 30" in message_text
    assert "Review gates: pass: 8" in message_text
    assert "blocked/failed: 15" in message_text
    assert "open/ready/needs_human: 7" in message_text
    assert "Conflicts: 0" in message_text
    assert "Recent events: 30" in message_text
    assert "#### Next required actions" in message_text
    assert "gate-1" in message_text
    assert "blocked" in message_text
    assert "gate-2" in message_text
    assert "failed" in message_text
    assert "Team Communication" in message_text
    assert "30 item(s), omitted 27 of 30 total" in message_text
    assert len(message_text) < 20000


def test_large_mixed_gates_with_actionable_gates_after_index_10_reports_accurate_counts_and_next_actions():
    gates = (
        [{"gate_id": f"gate-{i}", "kind": "acceptance", "status": "pass", "run_id": "run-1", "reason": f"Pass {i}"} for i in range(10)]
        + [
            {"gate_id": "gate-10", "kind": "acceptance", "status": "open", "run_id": "run-1", "reason": "Pending review."},
            {"gate_id": "gate-11", "kind": "acceptance", "status": "blocked", "run_id": "run-1", "reason": "Tests failing."},
            {"gate_id": "gate-12", "kind": "acceptance", "status": "failed", "run_id": "run-1", "reason": "Build failed."},
        ]
        + [{"gate_id": f"gate-{i}", "kind": "acceptance", "status": "pass", "run_id": "run-1", "reason": f"Pass {i}"} for i in range(13, 30)]
    )
    state = {
        "version": 1,
        "projects": [{"project_id": "p", "display_name": "P", "goal": "g", "status": "active", "risk_state": "low", "contract_path": "/x"}],
        "provider_bindings": [],
        "sessions": [{
            "session_id": "web-gpt-review-board-session",
            "provider": "chatgpt",
            "agent_role": "reviewer",
            "project_id": "p",
            "status": "idle",
            "messages": [],
            "tool_calls": [],
            "changed_files": [],
            "diff_summary": "",
            "evidence_refs": [],
            "native_refs": {"related_run_ids": ["run-1"]},
        }],
        "gates": [],
        "next_actions": [],
        "team": {
            "agent_registry": [],
            "task_board": [],
            "message_bus": [],
            "event_log": [],
            "evidence_store": [],
            "review_gates": gates,
            "conflict_control": [],
        },
    }

    shell = build_t3_client_shell_from_state(state, base_url="http://127.0.0.1:8790")

    validate_schema(load_schema(), shell)
    thread = shell["t3"]["threads"][0]
    detail = shell["t3"]["threadDetails"][0]
    message_text = detail["messages"][0]["text"]

    assert len(thread["devframe"]["teamDetailGates"]) == 10
    assert thread["devframe"]["teamDetailGateOverflow"] == 20
    assert message_text.startswith("### Review Board Summary")
    assert "Review gates: pass: 27" in message_text
    assert "blocked/failed: 2" in message_text
    assert "open/ready/needs_human: 1" in message_text
    assert "unknown" not in message_text
    assert "#### Next required actions" in message_text
    assert "[`gate-11`](http://127.0.0.1:8790/review-gates/open?gate_id=gate-11)" in message_text
    assert "blocked" in message_text
    assert "[`gate-12`](http://127.0.0.1:8790/review-gates/open?gate_id=gate-12)" in message_text
    assert "failed" in message_text
    assert "[`gate-10`](http://127.0.0.1:8790/review-gates/open?gate_id=gate-10)" in message_text
    assert "open" in message_text
    assert len(message_text) < 20000


def test_small_synthetic_reviewer_session_with_mixed_gates_preserves_summary_and_full_detail():
    state = {
        "version": 1,
        "projects": [{"project_id": "p", "display_name": "P", "goal": "g", "status": "active", "risk_state": "low", "contract_path": "/x"}],
        "provider_bindings": [],
        "sessions": [{
            "session_id": "web-gpt-review-board-session",
            "provider": "chatgpt",
            "agent_role": "reviewer",
            "project_id": "p",
            "status": "idle",
            "messages": [],
            "tool_calls": [],
            "changed_files": [],
            "diff_summary": "",
            "evidence_refs": [],
            "native_refs": {"related_run_ids": ["run-1"]},
        }],
        "gates": [],
        "next_actions": [],
        "team": {
            "agent_registry": [],
            "task_board": [],
            "message_bus": [
                {"message_id": "msg-1", "from_role": "reviewer", "to_role": "team", "kind": "review-status", "run_id": "run-1", "summary": "ATGO review run-1: pass"},
            ],
            "event_log": [
                {"event_id": "evt-1", "kind": "atgo-review", "run_id": "run-1", "summary": "ATGO review run run-1: pass"},
            ],
            "evidence_store": [
                {"evidence_id": "ev-1", "run_id": "run-1", "ref_type": "review", "ref_path": "/abs/path/review.md"},
            ],
            "review_gates": [
                {"gate_id": "gate-1", "kind": "acceptance", "status": "pass", "run_id": "run-1", "reason": "Good."},
                {"gate_id": "gate-2", "kind": "human", "status": "blocked", "run_id": "run-1", "reason": "Needs fix."},
                {"gate_id": "gate-3", "kind": "acceptance", "status": "failed", "run_id": "run-1", "reason": "Test fail."},
            ],
            "conflict_control": [],
        },
    }

    shell = build_t3_client_shell_from_state(state)

    validate_schema(load_schema(), shell)
    detail = shell["t3"]["threadDetails"][0]
    message_text = detail["messages"][0]["text"]

    assert message_text.startswith("### Review Board Summary")
    assert "Team tasks: 0" in message_text
    assert "Messages: 1" in message_text
    assert "Evidence refs: 1" in message_text
    assert "Review gates: pass: 1; blocked/failed: 2" in message_text
    assert "Conflicts: 0" in message_text
    assert "Recent events: 1" in message_text
    assert "#### Next required actions" in message_text
    assert "gate-2" in message_text
    assert "blocked" in message_text
    assert "gate-3" in message_text
    assert "failed" in message_text
    assert "Team Communication" in message_text
    assert "reviewer -> team" in message_text
    assert "Review Gates" in message_text
    assert "omitted" not in message_text

def test_large_synthetic_reviewer_session_evidence_refs_are_summary_only():
    messages = [
        {"message_id": f"msg-{i}", "from_role": "reviewer", "to_role": "team", "kind": "review-status", "run_id": f"run-{i}", "summary": f"ATGO review run-{i}: pass"}
        for i in range(30)
    ]
    evidence = [
        {"evidence_id": f"ev-{i}", "run_id": f"run-{i}", "ref_type": "review", "ref_path": f"/abs/path/review-{i}.md"}
        for i in range(30)
    ]
    gates = [
        {"gate_id": f"gate-{i}", "kind": "acceptance", "status": "pass", "run_id": f"run-{i}", "reason": f"ATGO review run-{i}: pass"}
        for i in range(30)
    ]
    events = [
        {"event_id": f"evt-{i}", "kind": "atgo-review", "run_id": f"run-{i}", "summary": f"ATGO review run run-{i}: pass"}
        for i in range(30)
    ]
    state = {
        "version": 1,
        "projects": [{"project_id": "p", "display_name": "P", "goal": "g", "status": "active", "risk_state": "low", "contract_path": "/x"}],
        "provider_bindings": [],
        "sessions": [{
            "session_id": "web-gpt-review-board-session",
            "provider": "chatgpt",
            "agent_role": "reviewer",
            "project_id": "p",
            "status": "idle",
            "messages": [],
            "tool_calls": [],
            "changed_files": [],
            "diff_summary": "",
            "evidence_refs": [
                "/abs/path/run-0/review.md",
                "/abs/path/run-0/review.yaml",
                "/abs/path/run-0/web-gpt-package-0",
            ],
            "native_refs": {"related_run_ids": [f"run-{i}" for i in range(30)]},
        }],
        "gates": [],
        "next_actions": [],
        "team": {
            "agent_registry": [],
            "task_board": [],
            "message_bus": messages,
            "event_log": events,
            "evidence_store": evidence,
            "review_gates": gates,
            "conflict_control": [],
        },
    }

    shell = build_t3_client_shell_from_state(state)

    validate_schema(load_schema(), shell)
    thread = shell["t3"]["threads"][0]
    detail = shell["t3"]["threadDetails"][0]
    message_text = detail["messages"][0]["text"]

    assert [ev["refPath"] for ev in thread["devframe"]["evidenceRefs"]] == [
        "run-0/review.md",
        "run-0/review.yaml",
        "run-0/web-gpt-package-0",
    ]
    assert "30 item(s), omitted 27 of 30 total" in message_text
    assert "run-0/review.md" in message_text
    assert "run-0/web-gpt-package-0" in message_text
    assert len(message_text) < 20000


def test_readable_team_gates_exposes_open_url_and_run_id_with_base_url():
    state = {
        "version": 1,
        "projects": [{"project_id": "p", "display_name": "P", "goal": "g", "status": "active", "risk_state": "low", "contract_path": "/x"}],
        "provider_bindings": [],
        "sessions": [{
            "session_id": "session-1",
            "provider": "opencode",
            "agent_role": "executor",
            "project_id": "p",
            "run_id": "run-1",
            "status": "idle",
            "messages": [],
            "tool_calls": [],
            "changed_files": [],
            "diff_summary": "",
            "evidence_refs": [],
        }],
        "gates": [],
        "next_actions": [],
        "team": {
            "review_gates": [
                {"gate_id": "gate-1", "kind": "acceptance", "status": "blocked", "run_id": "run-1", "reason": "Tests failing."},
                {"gate_id": "gate-2", "kind": "human", "status": "failed", "run_id": "run-1", "reason": "Reviewer rejected."},
                {"gate_id": "gate-3", "kind": "acceptance", "status": "open", "run_id": "run-1", "reason": "Pending."},
            ],
        },
    }

    shell = build_t3_client_shell_from_state(state, base_url="http://127.0.0.1:8790")

    thread = shell["t3"]["threads"][0]
    detail_gates = thread["devframe"]["teamDetailGates"]
    assert len(detail_gates) == 3
    for gate in detail_gates:
        assert "runId" in gate
        assert gate["runId"] == "run-1"
        assert gate["openPath"] == f"/review-gates/open?gate_id={gate['gateId']}"
        assert gate["openUrl"] == f"http://127.0.0.1:8790/review-gates/open?gate_id={gate['gateId']}"


def test_review_board_summary_links_blocked_gates_to_open_url():
    state = {
        "version": 1,
        "projects": [{"project_id": "p", "display_name": "P", "goal": "g", "status": "active", "risk_state": "low", "contract_path": "/x"}],
        "provider_bindings": [],
        "sessions": [{
            "session_id": "web-gpt-review-board-session",
            "provider": "chatgpt",
            "agent_role": "reviewer",
            "project_id": "p",
            "status": "idle",
            "messages": [],
            "tool_calls": [],
            "changed_files": [],
            "diff_summary": "",
            "evidence_refs": [],
            "native_refs": {"related_run_ids": ["run-1"]},
        }],
        "gates": [],
        "next_actions": [],
        "team": {
            "agent_registry": [],
            "task_board": [],
            "message_bus": [],
            "event_log": [],
            "evidence_store": [],
            "review_gates": [
                {"gate_id": "gate-1", "kind": "acceptance", "status": "blocked", "run_id": "run-1", "reason": "Tests failing."},
                {"gate_id": "gate-2", "kind": "human", "status": "failed", "run_id": "run-1", "reason": "Reviewer rejected."},
                {"gate_id": "gate-3", "kind": "acceptance", "status": "open", "run_id": "run-1", "reason": "Pending."},
            ],
            "conflict_control": [],
        },
    }

    shell = build_t3_client_shell_from_state(state, base_url="http://127.0.0.1:8790")

    detail = shell["t3"]["threadDetails"][0]
    message_text = detail["messages"][0]["text"]

    assert "### Review Board Summary" in message_text
    assert "#### Next required actions" in message_text
    assert "[`gate-1`](http://127.0.0.1:8790/review-gates/open?gate_id=gate-1)" in message_text
    assert "[`gate-2`](http://127.0.0.1:8790/review-gates/open?gate_id=gate-2)" in message_text
    assert "[`gate-3`](http://127.0.0.1:8790/review-gates/open?gate_id=gate-3)" in message_text


def test_small_synthetic_reviewer_session_with_base_url_renders_full_detail_with_links():
    state = {
        "version": 1,
        "projects": [{"project_id": "p", "display_name": "P", "goal": "g", "status": "active", "risk_state": "low", "contract_path": "/x"}],
        "provider_bindings": [],
        "sessions": [{
            "session_id": "web-gpt-review-board-session",
            "provider": "chatgpt",
            "agent_role": "reviewer",
            "project_id": "p",
            "status": "idle",
            "messages": [],
            "tool_calls": [],
            "changed_files": [],
            "diff_summary": "",
            "evidence_refs": [],
            "native_refs": {"related_run_ids": ["run-1"]},
        }],
        "gates": [],
        "next_actions": [],
        "team": {
            "agent_registry": [],
            "task_board": [],
            "message_bus": [
                {"message_id": "msg-1", "from_role": "reviewer", "to_role": "team", "kind": "review-status", "run_id": "run-1", "summary": "ATGO review run-1: pass"},
            ],
            "event_log": [
                {"event_id": "evt-1", "kind": "atgo-review", "run_id": "run-1", "summary": "ATGO review run run-1: pass"},
            ],
            "evidence_store": [
                {"evidence_id": "ev-1", "run_id": "run-1", "ref_type": "review", "ref_path": "/abs/path/review.md"},
            ],
            "review_gates": [
                {"gate_id": "gate-1", "kind": "acceptance", "status": "blocked", "run_id": "run-1", "reason": "Tests failing."},
                {"gate_id": "gate-2", "kind": "human", "status": "failed", "run_id": "run-1", "reason": "Reviewer rejected."},
            ],
            "conflict_control": [],
        },
    }

    shell = build_t3_client_shell_from_state(state, base_url="http://127.0.0.1:8790")

    detail = shell["t3"]["threadDetails"][0]
    message_text = detail["messages"][0]["text"]

    assert "### Review Board Summary" in message_text
    assert "#### Next required actions" in message_text
    assert "[`gate-1`](http://127.0.0.1:8790/review-gates/open?gate_id=gate-1)" in message_text
    assert "[`gate-2`](http://127.0.0.1:8790/review-gates/open?gate_id=gate-2)" in message_text
    assert "Team Communication" in message_text
    assert "Review Gates" in message_text
    assert "omitted" not in message_text
    assert len(message_text) < 20000


def test_large_evidence_refs_are_bounded_in_thread_detail():
    evidence_refs = [f"/abs/path/review-{i}.md" for i in range(100)]
    state = {
        "version": 1,
        "projects": [{"project_id": "p", "display_name": "P", "goal": "g", "status": "active", "risk_state": "low", "contract_path": "/x"}],
        "provider_bindings": [],
        "sessions": [{
            "session_id": "session-1",
            "provider": "opencode",
            "agent_role": "executor",
            "project_id": "p",
            "run_id": "run-1",
            "status": "idle",
            "messages": [],
            "tool_calls": [],
            "changed_files": [],
            "diff_summary": "",
            "evidence_refs": evidence_refs,
        }],
        "gates": [],
        "next_actions": [],
    }

    shell = build_t3_client_shell_from_state(state)
    thread = shell["t3"]["threads"][0]
    detail = shell["t3"]["threadDetails"][0]

    assert len(thread["devframe"]["evidenceRefs"]) == 10
    assert thread["devframe"]["evidenceRefOverflow"] == 90

    message_text = detail["messages"][0]["text"]
    assert "90 more evidence reference(s)" in message_text

    proposed_plan = detail["proposedPlans"][0]["planMarkdown"]
    assert "(90 more omitted)" in proposed_plan

    evidence_activities = [a for a in detail["activities"] if a["kind"] == "devframe.evidence.projected"]
    assert len(evidence_activities) == 1
    assert evidence_activities[0]["payload"]["count"] == 10


def test_large_team_lists_are_bounded_in_thread_detail_messages_and_activities():
    messages = [
        {"message_id": f"msg-{i}", "from_role": "reviewer", "to_role": "team", "kind": "review-status", "run_id": "run-1", "summary": f"Review {i}"}
        for i in range(100)
    ]
    evidence = [
        {"evidence_id": f"ev-{i}", "run_id": "run-1", "ref_type": "review", "ref_path": f"/abs/path/review-{i}.md"}
        for i in range(100)
    ]
    gates = [
        {"gate_id": f"gate-{i}", "kind": "acceptance", "status": "pass", "run_id": "run-1", "reason": f"Reason {i}"}
        for i in range(100)
    ]
    events = [
        {"event_id": f"evt-{i}", "kind": "atgo-review", "run_id": "run-1", "summary": f"Event {i}"}
        for i in range(100)
    ]
    conflicts = [
        {"file_path": f"file-{i}.py", "owner_run_id": "run-1", "owner_agent_id": "agent-1", "file_kind": "go-target"}
        for i in range(100)
    ]
    state = {
        "version": 1,
        "projects": [{"project_id": "p", "display_name": "P", "goal": "g", "status": "active", "risk_state": "low", "contract_path": "/x"}],
        "provider_bindings": [],
        "sessions": [{
            "session_id": "session-1",
            "provider": "opencode",
            "agent_role": "executor",
            "project_id": "p",
            "run_id": "run-1",
            "status": "idle",
            "messages": [],
            "tool_calls": [],
            "changed_files": [],
            "diff_summary": "",
            "evidence_refs": [],
        }],
        "gates": [],
        "next_actions": [],
        "team": {
            "message_bus": messages,
            "evidence_store": evidence,
            "review_gates": gates,
            "event_log": events,
            "conflict_control": conflicts,
        },
    }

    shell = build_t3_client_shell_from_state(state, base_url="http://127.0.0.1:8790")
    thread = shell["t3"]["threads"][0]
    detail = shell["t3"]["threadDetails"][0]

    assert len(thread["devframe"]["teamDetailMessages"]) == 10
    assert thread["devframe"]["teamDetailMessageOverflow"] == 90
    assert len(thread["devframe"]["teamDetailEvidence"]) == 10
    assert thread["devframe"]["teamDetailEvidenceOverflow"] == 90
    assert len(thread["devframe"]["teamDetailGates"]) == 10
    assert thread["devframe"]["teamDetailGateOverflow"] == 90
    assert len(thread["devframe"]["teamDetailConflicts"]) == 10
    assert thread["devframe"]["teamDetailConflictOverflow"] == 90
    assert len(thread["devframe"]["teamDetailEvents"]) == 10
    assert thread["devframe"]["teamDetailEventOverflow"] == 90

    message_text = detail["messages"][0]["text"]
    assert "90 more message(s)" in message_text
    assert "90 more evidence item(s)" in message_text
    assert "90 more gate(s)" in message_text
    assert "90 more conflict(s)" in message_text
    assert "90 more event(s)" in message_text

    overflow_activities = [a for a in detail["activities"] if a["kind"] == "devframe.team.overflow.projected"]
    assert len(overflow_activities) == 1
    assert overflow_activities[0]["payload"]["messageOverflow"] == 90
    assert overflow_activities[0]["payload"]["evidenceOverflow"] == 90
    assert overflow_activities[0]["payload"]["gateOverflow"] == 90
    assert overflow_activities[0]["payload"]["conflictOverflow"] == 90
    assert overflow_activities[0]["payload"]["eventOverflow"] == 90


def test_overflow_counts_are_visible_in_thread_shell_and_detail():
    messages = [
        {"message_id": f"msg-{i}", "from_role": "reviewer", "to_role": "team", "kind": "review-status", "run_id": "run-1", "summary": f"Review {i}"}
        for i in range(25)
    ]
    evidence = [
        {"evidence_id": f"ev-{i}", "run_id": "run-1", "ref_type": "review", "ref_path": f"/abs/path/review-{i}.md"}
        for i in range(25)
    ]
    state = {
        "version": 1,
        "projects": [{"project_id": "p", "display_name": "P", "goal": "g", "status": "active", "risk_state": "low", "contract_path": "/x"}],
        "provider_bindings": [],
        "sessions": [{
            "session_id": "session-1",
            "provider": "opencode",
            "agent_role": "executor",
            "project_id": "p",
            "run_id": "run-1",
            "status": "idle",
            "messages": [],
            "tool_calls": [],
            "changed_files": [],
            "diff_summary": "",
            "evidence_refs": [f"/abs/path/ref-{i}.md" for i in range(25)],
        }],
        "gates": [],
        "next_actions": [],
        "team": {
            "message_bus": messages,
            "evidence_store": evidence,
            "review_gates": [],
            "event_log": [],
            "conflict_control": [],
        },
    }

    shell = build_t3_client_shell_from_state(state)
    thread = shell["t3"]["threads"][0]
    detail = shell["t3"]["threadDetails"][0]

    assert thread["devframe"]["evidenceRefOverflow"] == 15
    assert thread["devframe"]["teamDetailMessageOverflow"] == 15
    assert thread["devframe"]["teamDetailEvidenceOverflow"] == 15

    message_text = detail["messages"][0]["text"]
    assert "15 more message(s)" in message_text
    assert "15 more evidence item(s)" in message_text
    assert "15 more evidence reference(s)" in message_text


def test_team_workbench_created_with_team_data_and_no_sessions():
    state = {
        "version": 1,
        "projects": [{"project_id": "p", "display_name": "P", "goal": "g", "status": "active", "risk_state": "low", "contract_path": "/x"}],
        "provider_bindings": [],
        "sessions": [],
        "gates": [],
        "next_actions": [],
        "team": {
            "agent_registry": [
                {"agent_id": "agent-1", "role": "worker", "binding_id": "b1", "status": "idle", "session_ids": ["s1"]},
            ],
            "task_board": [
                {"task_id": "task-1", "type": "go-run", "project_id": "p", "status": "queued", "agent_ids": ["agent-1"], "target_files": ["a.py"]},
            ],
            "message_bus": [
                {"message_id": "msg-1", "from_role": "planner", "to_role": "agent-1", "kind": "handoff", "run_id": "run-1", "summary": "Dispatch."},
            ],
            "event_log": [
                {"event_id": "evt-1", "kind": "go-run-created", "run_id": "run-1", "summary": "go run created."},
            ],
            "evidence_store": [
                {"evidence_id": "ev-1", "run_id": "run-1", "ref_type": "packet", "ref_path": "/tmp/p1/TASKSPEC.json"},
            ],
            "review_gates": [
                {"gate_id": "gate-1", "kind": "action-gate", "status": "ready", "run_id": "run-1", "reason": "Execute go-run."},
            ],
            "conflict_control": [
                {"file_path": "a.py", "owner_run_id": "run-1", "owner_agent_id": "agent-1", "file_kind": "go-target"},
            ],
        },
    }

    shell = build_t3_client_shell_from_state(state)
    validate_schema(load_schema(), shell)

    threads = shell["t3"]["threads"]
    assert len(threads) == 1
    thread = threads[0]
    assert thread["id"] == "devframe-team-workbench-session"
    assert thread["title"] == "DevFrame Global Coordinator"
    assert thread["threadKind"] == "global_coordinator"
    assert thread["coordinatorScope"] == "global"
    assert thread["projectBinding"] == {"mode": "optional", "projectId": "p", "status": "bound"}
    assert thread["threadListPriority"] == 0
    assert "Global coordinator inbox" in thread["threadListSummary"]
    assert thread["runtimeMode"] == "approval-required"
    assert thread["interactionMode"] == "plan"
    assert thread["hasPendingApprovals"] is True
    assert thread["hasPendingUserInput"] is True
    assert thread["hasActionableProposedPlan"] is True
    assert thread["session"]["runtimeMode"] == "approval-required"

    detail = shell["t3"]["threadDetails"][0]
    message_text = detail["messages"][0]["text"]
    assert detail["threadKind"] == "global_coordinator"
    assert "### DevFrame Global Coordinator" in message_text
    assert "New coordinator-owned goals must bind to a project before execution." in message_text
    assert "Agents: 1" in message_text
    assert "Tasks: 1" in message_text
    assert "Messages: 1" in message_text
    assert "Evidence refs: 1" in message_text
    assert "Review gates: open/ready/needs_human: 1" in message_text
    assert "Conflicts: 1" in message_text
    assert "Recent events: 1" in message_text
    assert "planner -> agent-1" in message_text
    assert "Evidence" in message_text
    assert "Review Gates" in message_text
    assert "Conflicts" in message_text
    assert "Events" in message_text


def test_team_workbench_with_all_pass_gates_has_no_pending_flags():
    state = {
        "version": 1,
        "projects": [{"project_id": "p", "display_name": "P", "goal": "g", "status": "active", "risk_state": "low", "contract_path": "/x"}],
        "provider_bindings": [],
        "sessions": [],
        "gates": [],
        "next_actions": [],
        "team": {
            "agent_registry": [
                {"agent_id": "agent-1", "role": "worker", "binding_id": "b1", "status": "idle", "session_ids": ["s1"]},
            ],
            "task_board": [
                {"task_id": "task-1", "type": "go-run", "project_id": "p", "status": "queued", "agent_ids": ["agent-1"], "target_files": ["a.py"]},
            ],
            "message_bus": [
                {"message_id": "msg-1", "from_role": "planner", "to_role": "agent-1", "kind": "handoff", "run_id": "run-1", "summary": "Dispatch."},
            ],
            "event_log": [
                {"event_id": "evt-1", "kind": "go-run-created", "run_id": "run-1", "summary": "go run created."},
            ],
            "evidence_store": [
                {"evidence_id": "ev-1", "run_id": "run-1", "ref_type": "packet", "ref_path": "/tmp/p1/TASKSPEC.json"},
            ],
            "review_gates": [
                {"gate_id": "gate-1", "kind": "action-gate", "status": "pass", "run_id": "run-1", "reason": "All good."},
                {"gate_id": "gate-2", "kind": "acceptance", "status": "success", "run_id": "run-1", "reason": "Tests passed."},
                {"gate_id": "gate-3", "kind": "human", "status": "complete", "run_id": "run-1", "reason": "Reviewer approved."},
            ],
            "conflict_control": [],
        },
    }

    shell = build_t3_client_shell_from_state(state)
    validate_schema(load_schema(), shell)

    thread = shell["t3"]["threads"][0]
    assert thread["id"] == "devframe-team-workbench-session"
    assert thread["threadKind"] == "global_coordinator"
    assert thread["hasPendingApprovals"] is False
    assert thread["hasPendingUserInput"] is False
    assert thread["hasActionableProposedPlan"] is False
    assert thread["session"]["runtimeMode"] == "approval-required"


def test_review_board_summary_works_alongside_team_workbench():
    state = {
        "version": 1,
        "projects": [{"project_id": "p", "display_name": "P", "goal": "g", "status": "active", "risk_state": "low", "contract_path": "/x"}],
        "provider_bindings": [],
        "sessions": [{
            "session_id": "web-gpt-review-board-session",
            "provider": "chatgpt",
            "agent_role": "reviewer",
            "project_id": "p",
            "status": "idle",
            "messages": [],
            "tool_calls": [],
            "changed_files": [],
            "diff_summary": "",
            "evidence_refs": [],
            "native_refs": {"related_run_ids": ["run-1"]},
        }],
        "gates": [],
        "next_actions": [],
        "team": {
            "agent_registry": [
                {"agent_id": "agent-1", "role": "worker", "binding_id": "b1", "status": "idle", "session_ids": ["s1"]},
            ],
            "task_board": [
                {"task_id": "task-1", "type": "go-run", "project_id": "p", "status": "queued", "agent_ids": ["agent-1"], "target_files": ["a.py"]},
            ],
            "message_bus": [
                {"message_id": "msg-1", "from_role": "planner", "to_role": "agent-1", "kind": "handoff", "run_id": "run-1", "summary": "Dispatch."},
            ],
            "event_log": [
                {"event_id": "evt-1", "kind": "go-run-created", "run_id": "run-1", "summary": "go run created."},
            ],
            "evidence_store": [
                {"evidence_id": "ev-1", "run_id": "run-1", "ref_type": "packet", "ref_path": "/tmp/p1/TASKSPEC.json"},
            ],
            "review_gates": [
                {"gate_id": "gate-1", "kind": "action-gate", "status": "ready", "run_id": "run-1", "reason": "Execute go-run."},
            ],
            "conflict_control": [
                {"file_path": "a.py", "owner_run_id": "run-1", "owner_agent_id": "agent-1", "file_kind": "go-target"},
            ],
        },
    }

    shell = build_t3_client_shell_from_state(state)
    validate_schema(load_schema(), shell)

    threads = shell["t3"]["threads"]
    assert len(threads) == 2
    assert threads[0]["id"] == "web-gpt-review-board-session"
    assert threads[0]["threadKind"] == "goal_conversation"
    assert threads[1]["id"] == "devframe-team-workbench-session"

    review_detail = shell["t3"]["threadDetails"][0]
    review_text = review_detail["messages"][0]["text"]
    assert "### Review Board Summary" in review_text

    workbench_detail = shell["t3"]["threadDetails"][1]
    workbench_text = workbench_detail["messages"][0]["text"]
    assert "### DevFrame Global Coordinator" in workbench_text
    assert "Agents: 1" in workbench_text


def test_team_workbench_uses_first_valid_project_id():
    state = {
        "version": 1,
        "projects": [None, {"project_id": "p", "display_name": "P", "goal": "g", "status": "active", "risk_state": "low", "contract_path": "/x"}],
        "provider_bindings": [],
        "sessions": [],
        "gates": [],
        "next_actions": [],
        "team": {
            "message_bus": [
                {"message_id": "msg-1", "from_role": "planner", "to_role": "team", "kind": "handoff", "run_id": "run-1", "summary": "Dispatch."},
            ],
        },
    }

    shell = build_t3_client_shell_from_state(state)
    validate_schema(load_schema(), shell)

    assert shell["t3"]["threads"][0]["id"] == "devframe-team-workbench-session"
    assert shell["t3"]["threads"][0]["projectId"] == "p"


def test_large_team_data_is_bounded_in_team_workbench():
    messages = [
        {"message_id": f"msg-{i}", "from_role": "reviewer", "to_role": "team", "kind": "review-status", "run_id": "run-1", "summary": f"Review {i}"}
        for i in range(100)
    ]
    evidence = [
        {"evidence_id": f"ev-{i}", "run_id": "run-1", "ref_type": "review", "ref_path": f"/abs/path/review-{i}.md"}
        for i in range(100)
    ]
    state = {
        "version": 1,
        "projects": [{"project_id": "p", "display_name": "P", "goal": "g", "status": "active", "risk_state": "low", "contract_path": "/x"}],
        "provider_bindings": [],
        "sessions": [],
        "gates": [],
        "next_actions": [],
        "team": {
            "agent_registry": [],
            "task_board": [],
            "message_bus": messages,
            "event_log": [],
            "evidence_store": evidence,
            "review_gates": [],
            "conflict_control": [],
        },
    }

    shell = build_t3_client_shell_from_state(state)
    validate_schema(load_schema(), shell)

    thread = shell["t3"]["threads"][0]
    assert thread["id"] == "devframe-team-workbench-session"
    assert len(thread["devframe"]["teamDetailMessages"]) == 10
    assert thread["devframe"]["teamDetailMessageOverflow"] == 90
    assert len(thread["devframe"]["teamDetailEvidence"]) == 10
    assert thread["devframe"]["teamDetailEvidenceOverflow"] == 90

    detail = shell["t3"]["threadDetails"][0]
    message_text = detail["messages"][0]["text"]
    assert "100 item(s), omitted 97 of 100 total" in message_text


def test_serialized_shell_size_stays_bounded_for_synthetic_large_state():
    messages = [
        {"message_id": f"msg-{i}", "from_role": "reviewer", "to_role": "team", "kind": "review-status", "run_id": "run-1", "summary": f"Review {i}"}
        for i in range(200)
    ]
    evidence = [
        {"evidence_id": f"ev-{i}", "run_id": "run-1", "ref_type": "review", "ref_path": f"/abs/path/review-{i}.md"}
        for i in range(200)
    ]
    gates = [
        {"gate_id": f"gate-{i}", "kind": "acceptance", "status": "pass", "run_id": "run-1", "reason": f"Reason {i}"}
        for i in range(200)
    ]
    events = [
        {"event_id": f"evt-{i}", "kind": "atgo-review", "run_id": "run-1", "summary": f"Event {i}"}
        for i in range(200)
    ]
    state = {
        "version": 1,
        "projects": [{"project_id": "p", "display_name": "P", "goal": "g", "status": "active", "risk_state": "low", "contract_path": "/x"}],
        "provider_bindings": [],
        "sessions": [{
            "session_id": "web-gpt-review-board-session",
            "provider": "chatgpt",
            "agent_role": "reviewer",
            "project_id": "p",
            "status": "idle",
            "messages": [],
            "tool_calls": [],
            "changed_files": [],
            "diff_summary": "",
            "evidence_refs": [f"/abs/path/ref-{i}.md" for i in range(200)],
            "native_refs": {"related_run_ids": ["run-1"]},
        }],
        "gates": [],
        "next_actions": [],
        "team": {
            "message_bus": messages,
            "evidence_store": evidence,
            "review_gates": gates,
            "event_log": events,
            "conflict_control": [],
        },
    }

    shell = build_t3_client_shell_from_state(state)
    json_size = len(json.dumps(shell))

    assert json_size < 200000, f"Shell size {json_size} exceeds bound"


def test_t3_client_shell_exposes_go_run_outcome_gates():
    state = {
        "version": 1,
        "projects": [{"project_id": "p", "display_name": "P", "goal": "g", "status": "active", "risk_state": "low", "contract_path": "/x"}],
        "provider_bindings": [],
        "sessions": [],
        "gates": [],
        "next_actions": [],
        "go_runs": [{
            "go_run_id": "go-1",
            "status": "passed",
            "agents": [],
        }, {
            "go_run_id": "go-2",
            "status": "failed",
            "agents": [],
        }, {
            "go_run_id": "go-3",
            "status": "queued",
            "agents": [],
        }],
        "team": {
            "agent_registry": [],
            "task_board": [],
            "message_bus": [
                {"message_id": "reviewer-to-team-go-1", "from_role": "reviewer", "to_role": "team",
                 "kind": "review-status", "run_id": "go-1", "summary": "Review status for /go run go-1: passed"},
                {"message_id": "reviewer-to-team-go-2", "from_role": "reviewer", "to_role": "team",
                 "kind": "review-status", "run_id": "go-2", "summary": "Review status for /go run go-2: failed"},
            ],
            "event_log": [],
            "evidence_store": [],
            "review_gates": [
                {"gate_id": "go-1-outcome-gate", "kind": "go-run-outcome", "status": "pass",
                 "reason": "/go run go-1 completed successfully.", "run_id": "go-1"},
                {"gate_id": "go-2-outcome-gate", "kind": "go-run-outcome", "status": "failed",
                 "reason": "/go run go-2 failed.", "run_id": "go-2"},
            ],
            "conflict_control": [],
        },
    }

    shell = build_t3_client_shell_from_state(state, base_url="http://127.0.0.1:8790")

    validate_schema(load_schema(), shell)
    team = shell["devframe"]["team"]
    assert len(team["reviewGates"]) == 2
    assert team["reviewGates"][0]["gateId"] == "go-1-outcome-gate"
    assert team["reviewGates"][0]["kind"] == "go-run-outcome"
    assert team["reviewGates"][0]["status"] == "pass"
    assert team["reviewGates"][1]["gateId"] == "go-2-outcome-gate"
    assert team["reviewGates"][1]["kind"] == "go-run-outcome"
    assert team["reviewGates"][1]["status"] == "failed"

    assert len(team["messageBus"]) == 2
    assert team["messageBus"][0]["kind"] == "review-status"
    assert "passed" in team["messageBus"][0]["summary"]
    assert team["messageBus"][1]["kind"] == "review-status"
    assert "failed" in team["messageBus"][1]["summary"]


def test_workbench_shows_webgpt_task_intake_action_before_team_communication_digest():
    state = {
        "version": 1,
        "projects": [{"project_id": "p", "display_name": "P", "goal": "g", "status": "active", "risk_state": "low", "contract_path": "/x"}],
        "provider_bindings": [],
        "sessions": [],
        "gates": [],
        "next_actions": [
            {"action_id": "web-gpt-task-intake-action", "source_type": "task_intake", "source_id": "intake-1", "priority": "high", "status": "ready", "label": "Execute Web GPT task intake through local agents.", "command": "devframe web-ai dispatch-task-intakes --intake-id int-1"},
            {"action_id": "generic-action", "source_type": "run", "source_id": "run-1", "priority": "medium", "status": "ready", "label": "Generic action."},
        ],
        "team": {
            "agent_registry": [],
            "task_board": [],
            "message_bus": [
                {"message_id": "msg-1", "from_role": "planner", "to_role": "agent-1", "kind": "handoff", "run_id": "run-1", "summary": "Old message."},
            ],
            "event_log": [],
            "evidence_store": [],
            "review_gates": [],
            "conflict_control": [],
        },
    }

    shell = build_t3_client_shell_from_state(state, base_url="http://127.0.0.1:8790")
    validate_schema(load_schema(), shell)

    thread = [t for t in shell["t3"]["threads"] if t["id"] == "devframe-team-workbench-session"][0]
    assert len(thread["devframe"]["workbenchPriorityActions"]) == 2
    assert thread["devframe"]["workbenchPriorityActions"][0]["actionId"] == "web-gpt-task-intake-action"
    assert thread["devframe"]["workbenchPriorityActions"][1]["actionId"] == "generic-action"

    detail = shell["t3"]["threadDetails"][0]
    message_text = detail["messages"][0]["text"]

    webgpt_pos = message_text.index("#### WebGPT / MCP Local Agent Actions")
    team_com_pos = message_text.index("- **Team Communication**")
    assert webgpt_pos < team_com_pos

    assert "web-gpt-task-intake-action" in message_text
    assert "[ready/high]" in message_text
    assert "Execute Web GPT task intake" in message_text
    assert "planner -> agent-1" in message_text


def test_workbench_preserves_generic_messages_evidence_in_bounded_form():
    messages = [
        {"message_id": f"msg-{i}", "from_role": "reviewer", "to_role": "team", "kind": "review-status", "run_id": "run-1", "summary": f"Generic review {i}."}
        for i in range(30)
    ]
    state = {
        "version": 1,
        "projects": [{"project_id": "p", "display_name": "P", "goal": "g", "status": "active", "risk_state": "low", "contract_path": "/x"}],
        "provider_bindings": [],
        "sessions": [],
        "gates": [],
        "next_actions": [],
        "team": {
            "agent_registry": [],
            "task_board": [],
            "message_bus": messages,
            "event_log": [],
            "evidence_store": [],
            "review_gates": [],
            "conflict_control": [],
        },
    }

    shell = build_t3_client_shell_from_state(state)
    validate_schema(load_schema(), shell)

    detail = shell["t3"]["threadDetails"][0]
    message_text = detail["messages"][0]["text"]

    assert "- **Team Communication**" in message_text
    assert "Generic review 0." in message_text
    assert "Generic review 1." in message_text
    assert "Generic review 2." in message_text
    assert "omitted" in message_text
    assert "30 item(s)" in message_text


def test_workbench_webgpt_actions_sort_before_non_webgpt():
    state = {
        "version": 1,
        "projects": [{"project_id": "p", "display_name": "P", "goal": "g", "status": "active", "risk_state": "low", "contract_path": "/x"}],
        "provider_bindings": [],
        "sessions": [],
        "gates": [],
        "next_actions": [
            {"action_id": "action-b", "source_type": "run", "source_id": "run-2", "priority": "medium", "status": "ready", "label": "B - generic."},
            {"action_id": "action-c", "source_type": "run", "source_id": "run-3", "priority": "low", "status": "open", "label": "C - generic."},
            {"action_id": "action-mcp", "source_type": "task_intake", "source_id": "intake-1", "priority": "low", "status": "ready", "label": "MCP task intake.", "detail": "Web GPT MCP flow."},
            {"action_id": "action-codexpro", "source_type": "task_intake", "source_id": "intake-2", "priority": "medium", "status": "open", "label": "CodexPro intake.", "command": "devframe codexpro"},
            {"action_id": "action-a", "source_type": "run", "source_id": "run-1", "priority": "high", "status": "ready", "label": "A - generic."},
            {"action_id": "action-chatgpt", "source_type": "web_ai", "source_id": "web-1", "priority": "high", "status": "ready", "label": "ChatGPT Web task intake.", "command": "devframe chatgpt-intake"},
        ],
        "team": {
            "agent_registry": [],
            "task_board": [],
            "message_bus": [
                {"message_id": "msg-1", "from_role": "planner", "to_role": "agent-1", "kind": "handoff", "run_id": "run-1", "summary": "Old message."},
            ],
            "event_log": [],
            "evidence_store": [],
            "review_gates": [],
            "conflict_control": [],
        },
    }

    shell = build_t3_client_shell_from_state(state, base_url="http://127.0.0.1:8790")
    validate_schema(load_schema(), shell)

    thread = [t for t in shell["t3"]["threads"] if t["id"] == "devframe-team-workbench-session"][0]
    actions = thread["devframe"]["workbenchPriorityActions"]
    assert len(actions) == 6

    web_ai_ids = {a["actionId"] for a in actions if a["actionId"] in {"action-mcp", "action-codexpro", "action-chatgpt"}}
    generic_ids = {a["actionId"] for a in actions if a["actionId"] in {"action-a", "action-b", "action-c"}}
    assert web_ai_ids == {"action-chatgpt", "action-codexpro", "action-mcp"}
    assert generic_ids == {"action-a", "action-b", "action-c"}

    web_ai_positions = [i for i, a in enumerate(actions) if a["actionId"] in web_ai_ids]
    generic_positions = [i for i, a in enumerate(actions) if a["actionId"] in generic_ids]

    assert max(web_ai_positions) < min(generic_positions)

    chatgpt_idx = next(i for i, a in enumerate(actions) if a["actionId"] == "action-chatgpt")
    mcp_idx = next(i for i, a in enumerate(actions) if a["actionId"] == "action-mcp")
    codexpro_idx = next(i for i, a in enumerate(actions) if a["actionId"] == "action-codexpro")
    assert chatgpt_idx == min(chatgpt_idx, mcp_idx, codexpro_idx)

    a_idx = next(i for i, a in enumerate(actions) if a["actionId"] == "action-a")
    b_idx = next(i for i, a in enumerate(actions) if a["actionId"] == "action-b")
    assert a_idx < b_idx


def test_workbench_large_team_data_remains_bounded():
    messages = [
        {"message_id": f"msg-{i}", "from_role": "reviewer", "to_role": "team", "kind": "review-status", "run_id": "run-1", "summary": f"Generic review {i}."}
        for i in range(100)
    ]
    evidence = [
        {"evidence_id": f"ev-{i}", "run_id": "run-1", "ref_type": "review", "ref_path": f"/abs/review-{i}.md"}
        for i in range(100)
    ]
    state = {
        "version": 1,
        "projects": [{"project_id": "p", "display_name": "P", "goal": "g", "status": "active", "risk_state": "low", "contract_path": "/x"}],
        "provider_bindings": [],
        "sessions": [],
        "gates": [],
        "next_actions": [],
        "team": {
            "agent_registry": [],
            "task_board": [],
            "message_bus": messages,
            "event_log": [],
            "evidence_store": evidence,
            "review_gates": [],
            "conflict_control": [],
        },
    }

    shell = build_t3_client_shell_from_state(state)
    validate_schema(load_schema(), shell)

    thread = [t for t in shell["t3"]["threads"] if t["id"] == "devframe-team-workbench-session"][0]
    assert len(thread["devframe"]["teamDetailMessages"]) == 10
    assert thread["devframe"]["teamDetailMessageOverflow"] == 90
    assert len(thread["devframe"]["teamDetailEvidence"]) == 10
    assert thread["devframe"]["teamDetailEvidenceOverflow"] == 90

    detail = shell["t3"]["threadDetails"][0]
    message_text = detail["messages"][0]["text"]
    assert "100 item(s), omitted 97 of 100 total" in message_text
    assert len(message_text) < 20000


def test_workbench_ready_command_action_projected_into_action_ids_and_approval():
    state = {
        "version": 1,
        "projects": [{"project_id": "p", "display_name": "P", "goal": "g", "status": "active", "risk_state": "low", "contract_path": "/x"}],
        "provider_bindings": [],
        "sessions": [],
        "gates": [],
        "next_actions": [
            {"action_id": "web-gpt-task-intake-action", "source_type": "task_intake", "source_id": "intake-1", "priority": "high", "status": "ready", "label": "Execute Web GPT task intake.", "command": "devframe web-ai dispatch-task-intakes --intake-id int-1"},
        ],
        "team": {
            "agent_registry": [],
            "task_board": [],
            "message_bus": [
                {"message_id": "msg-1", "from_role": "planner", "to_role": "agent-1", "kind": "handoff", "run_id": "run-1", "summary": "Old message."},
            ],
            "event_log": [],
            "evidence_store": [],
            "review_gates": [
                {"gate_id": "gate-all-pass", "kind": "acceptance", "status": "pass", "run_id": "run-1", "reason": "All good."},
            ],
            "conflict_control": [],
        },
    }

    shell = build_t3_client_shell_from_state(state, base_url="http://127.0.0.1:8790")
    validate_schema(load_schema(), shell)

    thread = [t for t in shell["t3"]["threads"] if t["id"] == "devframe-team-workbench-session"][0]
    assert thread["devframe"]["actionIds"] == ["web-gpt-task-intake-action"]
    assert thread["devframe"]["actionDetails"][0]["actionId"] == "web-gpt-task-intake-action"
    assert thread["devframe"]["actionDetails"][0]["status"] == "ready"
    assert thread["devframe"]["actionDetails"][0]["command"] == "devframe web-ai dispatch-task-intakes --intake-id int-1"
    assert thread["hasPendingApprovals"] is True
    assert thread["hasPendingUserInput"] is True
    assert thread["hasActionableProposedPlan"] is True

    detail = shell["t3"]["threadDetails"][0]
    approval_activities = [a for a in detail["activities"] if a["kind"] == "approval.requested"]
    assert len(approval_activities) == 1
    approval = approval_activities[0]
    assert approval["id"] == "devframe-team-workbench-session-approval-web-gpt-task-intake-action"
    assert approval["tone"] == "approval"
    assert approval["payload"]["actionId"] == "web-gpt-task-intake-action"
    assert approval["payload"]["command"] == "devframe web-ai dispatch-task-intakes --intake-id int-1"
    assert approval["payload"]["writePolicy"] == "read-only"

    message_text = detail["messages"][0]["text"]
    webgpt_pos = message_text.index("#### WebGPT / MCP Local Agent Actions")
    team_com_pos = message_text.index("- **Team Communication**")
    assert webgpt_pos < team_com_pos


def test_workbench_open_or_no_command_action_appears_in_details_but_no_approval():
    state = {
        "version": 1,
        "projects": [{"project_id": "p", "display_name": "P", "goal": "g", "status": "active", "risk_state": "low", "contract_path": "/x"}],
        "provider_bindings": [],
        "sessions": [],
        "gates": [],
        "next_actions": [
            {"action_id": "open-action", "source_type": "task_intake", "source_id": "intake-1", "priority": "low", "status": "open", "label": "Open Web GPT task intake.", "command": "devframe web-ai dispatch-task-intakes --intake-id int-1"},
            {"action_id": "ready-no-cmd-action", "source_type": "task_intake", "source_id": "intake-2", "priority": "medium", "status": "ready", "label": "Ready but no command action."},
        ],
        "team": {
            "agent_registry": [],
            "task_board": [],
            "message_bus": [
                {"message_id": "msg-1", "from_role": "planner", "to_role": "agent-1", "kind": "handoff", "run_id": "run-1", "summary": "Old message."},
            ],
            "event_log": [],
            "evidence_store": [],
            "review_gates": [
                {"gate_id": "gate-all-pass", "kind": "acceptance", "status": "pass", "run_id": "run-1", "reason": "All good."},
            ],
            "conflict_control": [],
        },
    }

    shell = build_t3_client_shell_from_state(state, base_url="http://127.0.0.1:8790")
    validate_schema(load_schema(), shell)

    thread = [t for t in shell["t3"]["threads"] if t["id"] == "devframe-team-workbench-session"][0]
    assert thread["devframe"]["actionIds"] == ["open-action", "ready-no-cmd-action"]
    assert len(thread["devframe"]["actionDetails"]) == 2
    assert thread["hasPendingApprovals"] is False
    assert thread["hasPendingUserInput"] is False
    assert thread["hasActionableProposedPlan"] is False

    detail = shell["t3"]["threadDetails"][0]
    approval_activities = [a for a in detail["activities"] if a["kind"] == "approval.requested"]
    assert len(approval_activities) == 0


def test_project_summary_action_prioritized_as_web_mcp_before_generic():
    state = {
        "version": 1,
        "projects": [{"project_id": "p", "display_name": "P", "goal": "g", "status": "active", "risk_state": "low", "contract_path": "/x"}],
        "provider_bindings": [],
        "sessions": [],
        "gates": [],
        "next_actions": [
            {"action_id": "generic-action", "source_type": "run", "source_id": "run-1", "priority": "high", "status": "ready", "label": "Generic high-priority action."},
            {"action_id": "project-summary-action", "source_type": "session", "source_id": "session-ps-1", "priority": "medium", "status": "open", "label": "Review imported project summary for next local handoff or task intake.", "detail": "Review the imported bounded project summary to inform the next local handoff or task intake."},
        ],
        "team": {
            "agent_registry": [],
            "task_board": [],
            "message_bus": [
                {"message_id": "msg-1", "from_role": "planner", "to_role": "agent-1", "kind": "handoff", "run_id": "run-1", "summary": "Old message."},
            ],
            "event_log": [],
            "evidence_store": [],
            "review_gates": [],
            "conflict_control": [],
        },
    }

    shell = build_t3_client_shell_from_state(state, base_url="http://127.0.0.1:8790")
    validate_schema(load_schema(), shell)

    thread = [t for t in shell["t3"]["threads"] if t["id"] == "devframe-team-workbench-session"][0]
    actions = thread["devframe"]["workbenchPriorityActions"]
    assert len(actions) == 2
    assert actions[0]["actionId"] == "project-summary-action"
    assert actions[1]["actionId"] == "generic-action"


def test_task_intake_ready_actions_rank_ahead_of_project_summary():
    state = {
        "version": 1,
        "projects": [{"project_id": "p", "display_name": "P", "goal": "g", "status": "active", "risk_state": "low", "contract_path": "/x"}],
        "provider_bindings": [],
        "sessions": [],
        "gates": [],
        "next_actions": [
            {"action_id": "project-summary-review-action", "source_type": "session", "source_id": "session-ps-1", "priority": "high", "status": "open", "label": "Review imported project summary.", "detail": "project summary data ready for review."},
            {"action_id": "web-gpt-task-intake-action", "source_type": "task_intake", "source_id": "intake-1", "priority": "low", "status": "ready", "label": "Execute Web GPT task intake.", "command": "devframe web-ai dispatch-task-intakes --intake-id int-1"},
            {"action_id": "generic-mcp-action", "source_type": "mcp_live", "source_id": "mcp-1", "priority": "medium", "status": "open", "label": "MCP live check action.", "detail": "web gpt mcp session imported."},
        ],
        "team": {
            "agent_registry": [],
            "task_board": [],
            "message_bus": [
                {"message_id": "msg-1", "from_role": "planner", "to_role": "agent-1", "kind": "handoff", "run_id": "run-1", "summary": "Old message."},
            ],
            "event_log": [],
            "evidence_store": [],
            "review_gates": [],
            "conflict_control": [],
        },
    }

    shell = build_t3_client_shell_from_state(state, base_url="http://127.0.0.1:8790")
    validate_schema(load_schema(), shell)

    thread = [t for t in shell["t3"]["threads"] if t["id"] == "devframe-team-workbench-session"][0]
    actions = thread["devframe"]["workbenchPriorityActions"]
    assert len(actions) == 3
    assert actions[0]["actionId"] == "web-gpt-task-intake-action"
    assert actions[1]["actionId"] == "project-summary-review-action"
    assert actions[2]["actionId"] == "generic-mcp-action"


def test_project_summary_ranks_ahead_of_generic_mcp_live_check_review_actions():
    state = {
        "version": 1,
        "projects": [{"project_id": "p", "display_name": "P", "goal": "g", "status": "active", "risk_state": "low", "contract_path": "/x"}],
        "provider_bindings": [],
        "sessions": [],
        "gates": [],
        "next_actions": [
            {"action_id": "generic-mcp-live-check", "source_type": "session", "source_id": "mcp-live-1", "priority": "high", "status": "open", "label": "MCP live check session.", "detail": "Live check: codexpro web mcp session."},
            {"action_id": "project-summary-review", "source_type": "session", "source_id": "session-ps-1", "priority": "medium", "status": "open", "label": "Review imported project summary.", "detail": "project summary data ready for review."},
            {"action_id": "old-webgpt-action", "source_type": "session", "source_id": "web-1", "priority": "high", "status": "open", "label": "Older ChatGPT Web MCP session.", "detail": "chatgpt web mcp imported session."},
        ],
        "team": {
            "agent_registry": [],
            "task_board": [],
            "message_bus": [
                {"message_id": "msg-1", "from_role": "planner", "to_role": "agent-1", "kind": "handoff", "run_id": "run-1", "summary": "Old message."},
            ],
            "event_log": [],
            "evidence_store": [],
            "review_gates": [],
            "conflict_control": [],
        },
    }

    shell = build_t3_client_shell_from_state(state, base_url="http://127.0.0.1:8790")
    validate_schema(load_schema(), shell)

    thread = [t for t in shell["t3"]["threads"] if t["id"] == "devframe-team-workbench-session"][0]
    actions = thread["devframe"]["workbenchPriorityActions"]
    assert len(actions) == 3
    assert actions[0]["actionId"] == "project-summary-review"
    assert actions[1]["actionId"] == "generic-mcp-live-check"
    assert actions[2]["actionId"] == "old-webgpt-action"


def test_workbench_bounded_list_behavior_remains_intact_with_project_summary():
    actions = []
    for i in range(5):
        actions.append({"action_id": f"task-intake-{i}", "source_type": "task_intake", "source_id": f"intake-{i}", "priority": "high", "status": "ready", "label": "Execute Web GPT task intake.", "command": f"devframe web-ai dispatch-task-intakes --intake-id int-{i}"})
    for i in range(5):
        actions.append({"action_id": f"project-summary-{i}", "source_type": "session", "source_id": f"session-ps-{i}", "priority": "medium", "status": "open", "label": "Review imported project summary.", "detail": "project summary data ready for review."})
    for i in range(5):
        actions.append({"action_id": f"generic-mcp-{i}", "source_type": "session", "source_id": f"mcp-{i}", "priority": "low", "status": "open", "label": "Older MCP live check session.", "detail": "codexpro web mcp imported session."})

    state = {
        "version": 1,
        "projects": [{"project_id": "p", "display_name": "P", "goal": "g", "status": "active", "risk_state": "low", "contract_path": "/x"}],
        "provider_bindings": [],
        "sessions": [],
        "gates": [],
        "next_actions": actions,
        "team": {
            "agent_registry": [],
            "task_board": [],
            "message_bus": [
                {"message_id": "msg-1", "from_role": "planner", "to_role": "agent-1", "kind": "handoff", "run_id": "run-1", "summary": "Old message."},
            ],
            "event_log": [],
            "evidence_store": [],
            "review_gates": [],
            "conflict_control": [],
        },
    }

    shell = build_t3_client_shell_from_state(state, base_url="http://127.0.0.1:8790")
    validate_schema(load_schema(), shell)

    thread = [t for t in shell["t3"]["threads"] if t["id"] == "devframe-team-workbench-session"][0]
    priority_actions = thread["devframe"]["workbenchPriorityActions"]
    assert len(priority_actions) == 10

    task_intake_ids = [a["actionId"] for a in priority_actions if a["actionId"].startswith("task-intake-")]
    project_summary_ids = [a["actionId"] for a in priority_actions if a["actionId"].startswith("project-summary-")]
    generic_mcp_ids = [a["actionId"] for a in priority_actions if a["actionId"].startswith("generic-mcp-")]

    assert len(task_intake_ids) == 5
    assert len(project_summary_ids) == 5
    assert len(generic_mcp_ids) == 0

    task_intake_positions = [i for i, a in enumerate(priority_actions) if a["actionId"].startswith("task-intake-")]
    project_summary_positions = [i for i, a in enumerate(priority_actions) if a["actionId"].startswith("project-summary-")]
    assert max(task_intake_positions) < min(project_summary_positions)
