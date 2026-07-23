from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from contextlib import contextmanager
from pathlib import Path
from threading import Thread
from types import SimpleNamespace
from typing import Any, Iterator
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from control_plane.client_launcher import build_client_launch_plan  # noqa: E402
from control_plane import cluster_run as cluster_run_module  # noqa: E402
from control_plane.cluster_run import list_cluster_runs  # noqa: E402
from control_plane.dashboard import build_dashboard_server  # noqa: E402
from control_plane.go_dispatch import load_go_run_result  # noqa: E402
from control_plane.t3_bridge_bundle import (  # noqa: E402
    build_t3_bridge_bundle,
    install_t3_bridge_bundle,
)
from control_plane.team_runtime import TeamRuntime, build_team_runtime_view  # noqa: E402
from control_plane.workflow_engine import WorkflowEngine  # noqa: E402


AUTHORITY_FIELDS = {
    "delegationId",
    "rootControllerId",
    "projectControllerId",
    "projectId",
    "clusterRunId",
    "goRunId",
    "delegationState",
    "delegatedAt",
    "requestedBy",
}


def _install_generated_bridge(tmp_path: Path, runtime_dir: Path) -> Path:
    t3_root = tmp_path / "rd-code"
    (t3_root / "apps" / "web").mkdir(parents=True)
    (t3_root / "package.json").write_text('{"type":"module"}\n', encoding="utf-8")
    bundle = build_t3_bridge_bundle(build_client_launch_plan(runtime_dir=runtime_dir))
    install_t3_bridge_bundle(t3_root, bundle)
    return t3_root


def _install_safe_opencode_fixture(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    sleep_seconds: float = 0.45,
) -> None:
    bin_dir = tmp_path / "safe-bin"
    bin_dir.mkdir()
    worker_path = bin_dir / "safe_opencode_worker.py"
    worker_path.write_text(
        "from __future__ import annotations\n"
        "import json\n"
        "import os\n"
        "import time\n"
        "from pathlib import Path\n"
        "started = time.time()\n"
        f"time.sleep({sleep_seconds!r})\n"
        "finished = time.time()\n"
        "packet_dir = Path(os.environ['RDGOAL_PACKET_DIR'])\n"
        "(packet_dir / 'parallel-evidence.json').write_text(\n"
        "    json.dumps({'startedAt': started, 'finishedAt': finished}),\n"
        "    encoding='utf-8',\n"
        ")\n"
        "Path(os.environ['RDGOAL_REPORT_PATH']).write_text(\n"
        "    '## ExecutionReport\\n\\n'\n"
        "    '- **Status**: pass\\n'\n"
        "    '- **Changed Files**:\\n'\n"
        "    '- (none)\\n'\n"
        "    '- **Evidence**: safe no-network local child fixture\\n'\n"
        "    '- **Risks**: none\\n'\n"
        "    '- **Reviewer Index**: packet-local fixture evidence\\n',\n"
        "    encoding='utf-8',\n"
        ")\n",
        encoding="utf-8",
    )
    if os.name == "nt":
        launcher = bin_dir / "opencode.cmd"
        launcher.write_text(
            f'@echo off\r\n"{sys.executable}" "{worker_path}"\r\n',
            encoding="utf-8",
        )
    else:
        launcher = bin_dir / "opencode"
        launcher.write_text(
            f'#!/bin/sh\nexec "{sys.executable}" "{worker_path}"\n',
            encoding="utf-8",
        )
        launcher.chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}")


@contextmanager
def _running_dashboard(runtime_dir: Path) -> Iterator[str]:
    server = build_dashboard_server(
        runtime_dir=runtime_dir,
        host="127.0.0.1",
        port=0,
        refresh_seconds=0,
    )
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def _run_generated_probe(
    t3_root: Path,
    source: str,
    *,
    filename: str = "delegated-control-probe.ts",
) -> dict[str, object]:
    probe_path = t3_root / filename
    probe_path.write_text(source, encoding="utf-8")
    node = shutil.which("node")
    assert node is not None, (
        "Node.js is required for the generated RD-Code bridge probe"
    )
    result = subprocess.run(
        [node, str(probe_path)],
        cwd=t3_root,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return json.loads(result.stdout)


def _start_generated_goal(
    t3_root: Path, base_url: str, project_id: str
) -> dict[str, object]:
    return _run_generated_probe(
        t3_root,
        "import { startDevFrameCoordinatorGoal, type DevFrameCoordinatorGoalRequest }\n"
        '  from "./apps/web/src/devframe/devframeShellBridge.ts";\n\n'
        "const request: DevFrameCoordinatorGoalRequest = {\n"
        f"  projectId: {json.dumps(project_id)},\n"
        '  goal: "Implement the delegated control product slice with two local child shards.",\n'
        '  proposedBy: "rd-code-delegated-control-test",\n'
        "};\n"
        f"const result = await startDevFrameCoordinatorGoal({{ controlPlaneBaseUrl: {json.dumps(base_url)} }}, request);\n"
        "console.log(JSON.stringify(result));\n",
    )


def _typecheck_generated_bridge(t3_root: Path) -> None:
    tsgo = shutil.which("tsgo")
    if tsgo is None:
        return
    (t3_root / "env.d.ts").write_text(
        "interface ImportMetaEnv {\n"
        "  readonly VITE_DEVFRAME_T3_SHELL_URL?: string;\n"
        "  readonly VITE_DEVFRAME_CLIENT_PLAN_URL?: string;\n"
        "  readonly VITE_DEVFRAME_CLIENT_MANIFEST_URL?: string;\n"
        "}\n"
        "interface ImportMeta { readonly env: ImportMetaEnv; }\n",
        encoding="utf-8",
    )
    (t3_root / "tsconfig.json").write_text(
        json.dumps(
            {
                "compilerOptions": {
                    "allowImportingTsExtensions": True,
                    "lib": ["ES2022", "DOM"],
                    "module": "ESNext",
                    "moduleResolution": "Bundler",
                    "noEmit": True,
                    "strict": True,
                    "target": "ES2022",
                },
                "include": [
                    "apps/web/src/devframe/devframeShellBridge.ts",
                    "delegated-control-probe.ts",
                    "env.d.ts",
                ],
            }
        ),
        encoding="utf-8",
    )
    command = [tsgo, "--project", str(t3_root / "tsconfig.json"), "--pretty", "false"]
    if Path(tsgo).suffix.lower() in {".bat", ".cmd"}:
        command = [shutil.which("cmd") or "cmd", "/d", "/c", *command]
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stdout + result.stderr


def _post_json(
    base_url: str,
    path: str,
    payload: Any,
) -> tuple[int, dict[str, object]]:
    request = Request(
        f"{base_url}{path}",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Accept": "application/json", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=5) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except HTTPError as error:
        return error.code, json.loads(error.read().decode("utf-8"))


def _get_json(base_url: str, path: str) -> tuple[int, dict[str, object]]:
    with urlopen(f"{base_url}{path}", timeout=5) as response:
        return response.status, json.loads(response.read().decode("utf-8"))


def _wait_for_terminal_detail(base_url: str, run_id: str) -> dict[str, object]:
    deadline = time.monotonic() + 20
    detail: dict[str, object] = {}
    while time.monotonic() < deadline:
        status, detail = _get_json(
            base_url,
            f"/api/t3/cluster-run-events?runId={run_id}",
        )
        assert status == 200
        if detail.get("goRunId") and detail.get("status") not in {"running", "started"}:
            return detail
        time.sleep(0.03)
    pytest.fail(f"delegated cluster run did not finish: {detail}")


def _wait_for_bound_detail(base_url: str, run_id: str) -> dict[str, object]:
    deadline = time.monotonic() + 10
    detail: dict[str, object] = {}
    while time.monotonic() < deadline:
        status, detail = _get_json(
            base_url,
            f"/api/t3/cluster-run-events?runId={run_id}",
        )
        assert status == 200
        if detail.get("goRunId"):
            return detail
        time.sleep(0.02)
    pytest.fail(f"cluster/go binding was not persisted: {detail}")


def test_omitted_target_enters_root_controller_and_records_real_delegation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime_dir = tmp_path / "runtime"
    workspace = tmp_path / "workspace"
    runtime_dir.mkdir()
    workspace.mkdir()
    (workspace / "module_a.py").write_text("VALUE_A = 1\n", encoding="utf-8")
    (workspace / "module_b.py").write_text("VALUE_B = 2\n", encoding="utf-8")
    _install_safe_opencode_fixture(tmp_path, monkeypatch)
    t3_root = _install_generated_bridge(tmp_path, runtime_dir)

    with _running_dashboard(runtime_dir) as base_url:
        started = _start_generated_goal(t3_root, base_url, str(workspace))
        detail = _wait_for_terminal_detail(base_url, str(started["runId"]))

    assert started["target"] == "coordinator"
    initial_authority = started["authority"]
    assert isinstance(initial_authority, dict)
    assert AUTHORITY_FIELDS <= initial_authority.keys()

    authority = detail["authority"]
    assert isinstance(authority, dict)
    assert AUTHORITY_FIELDS <= authority.keys()
    assert authority["delegationId"] == initial_authority["delegationId"]
    assert authority["clusterRunId"] == started["runId"]
    assert authority["goRunId"] == detail["goRunId"]
    assert authority["projectId"] == detail["projectId"]
    assert authority["rootControllerId"] == "root-controller"
    assert authority["projectControllerId"] != authority["rootControllerId"]
    assert authority["delegationState"] == "awaiting_review"
    assert authority["requestedBy"] == "rd-code-delegated-control-test"
    assert detail["status"] == "passed"
    assert "verdict=awaiting_review" in str(detail["summary"])
    assert any(
        message["from"] == authority["rootControllerId"]
        and message["to"] == authority["projectControllerId"]
        and message["kind"] == "delegation"
        for message in detail["messages"]
    )

    durable = next(
        item
        for item in list_cluster_runs(runtime_dir)
        if item.get("runId") == started["runId"]
    )
    assert durable["authority"] == authority
    go_result = load_go_run_result(runtime_dir, str(detail["goRunId"]))
    assert go_result.status == "passed"
    assert [agent.agent_id for agent in go_result.agents] == [
        "coding-agent-1",
        "coding-agent-2",
    ]

    events = TeamRuntime(runtime_dir).read_all()
    task_events = [event for event in events if event["event_type"] == "task_created"]
    assert len(task_events) == 2
    assert {event["agent_id"] for event in task_events} == {
        "coding-agent-1",
        "coding-agent-2",
    }
    delegation_message = next(
        event
        for event in events
        if event["event_type"] == "agent_message"
        and event["agent_id"] == authority["rootControllerId"]
    )
    assert (
        delegation_message["payload"]["to_agent_id"] == authority["projectControllerId"]
    )
    for binding in (
        authority["delegationId"],
        authority["projectId"],
        authority["clusterRunId"],
    ):
        assert str(binding) in delegation_message["payload"]["summary"]
    assert not {event["event_type"] for event in events} & {
        "review_ref",
        "final_verdict_ref",
    }
    assert any(
        event["event_type"] == "workflow_event"
        and event["payload"].get("phase") == "review"
        and event["payload"].get("status") == "awaiting_review"
        for event in events
    )
    assert not any(
        event["event_type"] == "workflow_event"
        and event["payload"].get("phase") == "review"
        and event["agent_id"] == authority["rootControllerId"]
        for event in events
    )

    view = build_team_runtime_view(runtime_dir)
    assert any(
        message["from_role"] == authority["rootControllerId"]
        and message["to_role"] == authority["projectControllerId"]
        for message in view["message_bus"]
    )
    assert len(view["task_board"]) == 2
    assert {
        agent_id for task in view["task_board"] for agent_id in task["agent_ids"]
    } == {"coding-agent-1", "coding-agent-2"}

    intervals = [
        json.loads(path.read_text(encoding="utf-8"))
        for path in runtime_dir.rglob("parallel-evidence.json")
    ]
    assert len(intervals) == 2
    assert all(item["startedAt"] < item["finishedAt"] for item in intervals)
    _typecheck_generated_bridge(t3_root)

    journal_case = tmp_path / "journal-failure-case"
    journal_runtime = journal_case / "runtime"
    journal_workspace = journal_case / "workspace"
    journal_case.mkdir()
    journal_runtime.mkdir()
    journal_workspace.mkdir()
    (journal_workspace / "module_a.py").write_text("VALUE_A = 1\n", encoding="utf-8")
    (journal_workspace / "module_b.py").write_text("VALUE_B = 2\n", encoding="utf-8")
    _install_safe_opencode_fixture(
        journal_case,
        monkeypatch,
        sleep_seconds=1.0,
    )
    journal_t3_root = _install_generated_bridge(journal_case, journal_runtime)
    journal_sentinel = "JOURNAL_FAILURE_SENTINEL"

    def fail_delegation_message(*_args: object, **_kwargs: object) -> str:
        raise OSError(journal_sentinel)

    monkeypatch.setattr(TeamRuntime, "record_agent_message", fail_delegation_message)
    with _running_dashboard(journal_runtime) as base_url:
        journal_started = _start_generated_goal(
            journal_t3_root,
            base_url,
            str(journal_workspace),
        )
        bound_detail = _wait_for_bound_detail(
            base_url,
            str(journal_started["runId"]),
        )
        assert bound_detail["status"] == "running"
        bound_authority = bound_detail["authority"]
        assert isinstance(bound_authority, dict)
        assert bound_authority["goRunId"] == bound_detail["goRunId"]
        assert bound_authority["delegationState"] == "running"
        bound_record = list_cluster_runs(journal_runtime)[0]
        assert bound_record["goRunId"] == bound_detail["goRunId"]
        assert bound_record["authority"] == bound_authority
        journal_terminal = _wait_for_terminal_detail(
            base_url,
            str(journal_started["runId"]),
        )

    assert journal_terminal["status"] == "passed"
    assert "verdict=awaiting_review" in str(journal_terminal["summary"])
    assert "2 passed, 0 failed" in str(journal_terminal["summary"])
    assert journal_terminal["authority"]["delegationState"] == "awaiting_review"
    journal_go_result = load_go_run_result(
        journal_runtime,
        str(journal_terminal["goRunId"]),
    )
    assert journal_go_result.status == "passed"
    assert len(journal_go_result.agents) == 2


def test_invalid_inputs_fail_before_cluster_go_or_team_artifacts(
    tmp_path: Path,
) -> None:
    runtime_dir = tmp_path / "runtime"
    workspace = tmp_path / "workspace"
    runtime_dir.mkdir()
    workspace.mkdir()
    invalid_requests: list[tuple[Any, str]] = [
        ({"projectId": "", "goal": "Implement the slice"}, "missing_or_invalid_params"),
        ({"projectId": 42, "goal": "Implement the slice"}, "missing_or_invalid_params"),
        ({"projectId": str(workspace), "goal": ""}, "missing_or_invalid_params"),
        (
            {"projectId": str(workspace), "goal": ["not", "a", "string"]},
            "missing_or_invalid_params",
        ),
        (
            {"projectId": str(workspace), "target": "", "goal": "Implement"},
            "missing_or_invalid_params",
        ),
        (
            {"projectId": str(workspace), "target": 7, "goal": "Implement"},
            "missing_or_invalid_params",
        ),
        (
            {"projectId": str(workspace), "target": "ghost-agent", "goal": "Implement"},
            "cluster_run_rejected",
        ),
        ([], "missing_or_invalid_params"),
    ]

    with _running_dashboard(runtime_dir) as base_url:
        for payload, expected_error in invalid_requests:
            status, error = _post_json(base_url, "/api/t3/cluster-run", payload)
            assert status == 400
            assert error["error"] == expected_error
            assert error["retry"] == {
                "allowed": False,
                "action": "correct_request",
            }

    assert not [path for path in runtime_dir.rglob("*") if path.is_file()]
    assert list_cluster_runs(runtime_dir) == []
    assert TeamRuntime(runtime_dir).read_all() == []


def test_explicit_target_stays_compatible_and_bridge_preserves_backend_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime_dir = tmp_path / "runtime"
    workspace = tmp_path / "workspace"
    runtime_dir.mkdir()
    workspace.mkdir()
    t3_root = _install_generated_bridge(tmp_path, runtime_dir)
    sensitive_sentinel = (
        "SENSITIVE_SENTINEL::secret=do-not-leak::path=D:/private/config.json::"
        "worker_command=private-runner --token hidden"
    )

    class FailingThread:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            return

        def start(self) -> None:
            raise RuntimeError(sensitive_sentinel)

    with _running_dashboard(runtime_dir) as base_url:
        output = _run_generated_probe(
            t3_root,
            "import { DevFrameCoordinatorGoalError, startDevFrameCoordinatorGoal }\n"
            '  from "./apps/web/src/devframe/devframeShellBridge.ts";\n\n'
            f"const config = {{ controlPlaneBaseUrl: {json.dumps(base_url)} }};\n"
            "const explicit = await startDevFrameCoordinatorGoal(config, {\n"
            f"  projectId: {json.dumps(str(workspace))},\n"
            '  target: "coordinator",\n'
            '  goal: "hello",\n'
            "});\n"
            "let failure: Record<string, unknown> = {};\n"
            "try {\n"
            "  await startDevFrameCoordinatorGoal(config, {\n"
            f"    projectId: {json.dumps(str(workspace))},\n"
            '    target: "missing-worker",\n'
            '    goal: "Review the paper",\n'
            "  });\n"
            "} catch (error) {\n"
            "  if (!(error instanceof DevFrameCoordinatorGoalError)) throw error;\n"
            "  failure = {\n"
            "    name: error.name,\n"
            "    status: error.status,\n"
            "    code: error.code,\n"
            "    detail: error.detail,\n"
            "    retry: error.retry,\n"
            "    response: error.response,\n"
            "  };\n"
            "}\n"
            "console.log(JSON.stringify({ explicit, failure }));\n",
            filename="explicit-target-probe.ts",
        )
        monkeypatch.setattr(
            cluster_run_module,
            "threading",
            SimpleNamespace(Thread=FailingThread),
        )
        start_failures = _run_generated_probe(
            t3_root,
            "import { DevFrameCoordinatorGoalError, startDevFrameCoordinatorGoal }\n"
            '  from "./apps/web/src/devframe/devframeShellBridge.ts";\n\n'
            f"const config = {{ controlPlaneBaseUrl: {json.dumps(base_url)} }};\n"
            "const failures: Record<string, unknown>[] = [];\n"
            "for (let attempt = 0; attempt < 2; attempt += 1) {\n"
            "  try {\n"
            "    await startDevFrameCoordinatorGoal(config, {\n"
            f"      projectId: {json.dumps(str(workspace))},\n"
            '      goal: "Start a delegated implementation run",\n'
            "    });\n"
            "  } catch (error) {\n"
            "    if (!(error instanceof DevFrameCoordinatorGoalError)) throw error;\n"
            "    failures.push({\n"
            "      name: error.name,\n"
            "      message: error.message,\n"
            "      status: error.status,\n"
            "      code: error.code,\n"
            "      detail: error.detail,\n"
            "      retry: error.retry,\n"
            "      response: error.response,\n"
            "    });\n"
            "  }\n"
            "}\n"
            "console.log(JSON.stringify({ failures }));\n",
            filename="thread-start-failure-probe.ts",
        )

    explicit = output["explicit"]
    assert isinstance(explicit, dict)
    assert explicit["target"] == "coordinator"
    assert explicit["kind"] == "conversation"
    assert "authority" not in explicit
    assert TeamRuntime(runtime_dir).read_all() == []

    failure = output["failure"]
    assert failure == {
        "name": "DevFrameCoordinatorGoalError",
        "status": 400,
        "code": "cluster_run_rejected",
        "detail": "unknown cluster target: missing-worker",
        "retry": {"allowed": False, "action": "correct_request"},
        "response": {
            "error": "cluster_run_rejected",
            "detail": "unknown cluster target: missing-worker",
            "retry": {"allowed": False, "action": "correct_request"},
        },
    }

    expected_start_failure = {
        "name": "DevFrameCoordinatorGoalError",
        "message": "cluster_run_failed: Coordinator run could not be started.",
        "status": 500,
        "code": "cluster_run_failed",
        "detail": "Coordinator run could not be started.",
        "retry": {"allowed": False, "action": "inspect_status"},
        "response": {
            "error": "cluster_run_failed",
            "detail": "Coordinator run could not be started.",
            "retry": {"allowed": False, "action": "inspect_status"},
        },
    }
    assert start_failures == {"failures": [expected_start_failure] * 2}
    assert sensitive_sentinel not in json.dumps(start_failures, ensure_ascii=False)

    records = list_cluster_runs(runtime_dir)
    assert len(records) == 3
    failed_records = [record for record in records if record["status"] == "failed"]
    assert len(failed_records) == 2
    assert all(record.get("finishedAt") for record in failed_records)
    assert all(record.get("goRunId", "") == "" for record in failed_records)
    assert all(
        record["authority"]["delegationState"] == "failed"
        and record["authority"]["goRunId"] == ""
        for record in failed_records
    )
    assert not any(
        record["status"] in {"running", "started"}
        or record.get("authority", {}).get("delegationState") == "delegated"
        for record in records
    )
    assert sensitive_sentinel not in json.dumps(records, ensure_ascii=False)
    assert not list(runtime_dir.rglob("go-run.json"))


def test_disjoint_local_children_keep_parallel_evidence_truth(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime_dir = tmp_path / "runtime"
    workspace = tmp_path / "workspace"
    runtime_dir.mkdir()
    workspace.mkdir()
    (workspace / "module_a.py").write_text("VALUE_A = 1\n", encoding="utf-8")
    (workspace / "module_b.py").write_text("VALUE_B = 2\n", encoding="utf-8")
    _install_safe_opencode_fixture(tmp_path, monkeypatch)

    result = WorkflowEngine(runtime_dir).run_coding_workflow(
        workspace,
        "Update module_a.py and module_b.py through independent local shards.",
        agents=2,
        targets=["module_a.py", "module_b.py"],
    )

    assert result.status == "passed"
    assert result.verdict == "awaiting_review"
    assert result.passed_agents == 2
    intervals = [
        json.loads(path.read_text(encoding="utf-8"))
        for path in runtime_dir.rglob("parallel-evidence.json")
    ]
    assert len(intervals) == 2
    assert max(item["startedAt"] for item in intervals) < min(
        item["finishedAt"] for item in intervals
    )
    events = TeamRuntime(runtime_dir).read_all()
    assert len([event for event in events if event["event_type"] == "task_result"]) == 2
    assert not {event["event_type"] for event in events} & {
        "review_ref",
        "final_verdict_ref",
    }
