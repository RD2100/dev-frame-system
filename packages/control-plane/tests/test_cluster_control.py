"""Tests for the RD-Code cluster control surface.

Conversation input remains non-executing; development work requires a bound,
expiring, single-use server confirmation. Cancellation propagates from the
loopback HTTP surface through the workflow to real command-worker process trees
while preserving durable evidence.
"""
from __future__ import annotations

import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor
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


REPO_ROOT = Path(__file__).resolve().parents[3]


def _confirmed_start(runtime, project: str, target: str, goal: str):
    proposal = cluster_run_module.propose_cluster_run(
        runtime,
        "devframe-local",
        project,
        target,
        goal,
    )
    return start_cluster_run(
        runtime,
        project,
        target,
        goal,
        environment_id="devframe-local",
        proposal_id=proposal["proposalId"],
        confirmation_token=proposal["confirmationToken"],
        decision="execute",
    )


def _load_coordinator_entry_schema() -> dict:
    return json.loads((REPO_ROOT / "schemas" / "t3_coordinator_entry.schema.json").read_text(encoding="utf-8"))


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


def test_targets_include_paper_review_product(tmp_path):
    targets = list_cluster_targets(tmp_path / "runtime", "demo")
    ids = [t["id"] for t in targets]
    assert "rdpaper" in ids
    paper = next(t for t in targets if t["id"] == "rdpaper")
    assert paper["kind"] == "product"
    assert paper["role"] == "paper_reviewer"
    assert "论文审查" in paper["label"]
    assert paper["source"] == "default"


def test_atomic_write_retries_transient_windows_sharing_violation(tmp_path, monkeypatch):
    calls = {"count": 0}
    real_replace = cluster_run_module.os.replace

    def flaky_replace(src, dst):
        calls["count"] += 1
        if calls["count"] <= 2:
            raise PermissionError(13, "The process cannot access the file because it is being used by another process")
        return real_replace(src, dst)

    monkeypatch.setattr(cluster_run_module.os, "replace", flaky_replace)
    monkeypatch.setattr(time, "sleep", lambda _s: None)
    target = tmp_path / "cluster-runs" / "g-abc123.json"
    cluster_run_module._atomic_write(target, {"runId": "g-abc123"})
    assert calls["count"] == 3
    assert json.loads(target.read_text(encoding="utf-8")) == {"runId": "g-abc123"}


def test_atomic_write_raises_after_retry_exhaustion(tmp_path, monkeypatch):
    calls = {"count": 0}

    def always_locked(src, dst):
        calls["count"] += 1
        raise PermissionError(13, "sharing violation")

    monkeypatch.setattr(cluster_run_module.os, "replace", always_locked)
    monkeypatch.setattr(time, "sleep", lambda _s: None)
    with pytest.raises(PermissionError):
        cluster_run_module._atomic_write(tmp_path / "r.json", {"runId": "x"})
    assert calls["count"] == 5


def test_is_valid_cluster_target(tmp_path):
    runtime = tmp_path / "runtime"
    assert is_valid_cluster_target(runtime, "coordinator", "demo") is True
    assert is_valid_cluster_target(runtime, "executor", "demo") is True
    assert is_valid_cluster_target(runtime, "does-not-exist", "demo") is False
    assert is_valid_cluster_target(runtime, "", "demo") is False


def test_start_cluster_run_validates_and_starts(tmp_path, monkeypatch):
    runtime = tmp_path / "runtime"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    calls: list[tuple] = []
    monkeypatch.setattr(
        cluster_run_module,
        "_run_cluster_workflow",
        lambda rd, path, target, goal, run_id, on_prepared=None, cancel_marker=None: calls.append((path, target, goal, run_id)),
    )
    started = _confirmed_start(runtime, str(workspace), "coordinator", "ship the feature")
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


def test_development_goal_requires_server_confirmation(tmp_path, monkeypatch):
    runtime = tmp_path / "runtime"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    calls: list[tuple] = []
    monkeypatch.setattr(
        cluster_run_module,
        "_run_cluster_workflow",
        lambda *args, **kwargs: calls.append((args, kwargs)),
    )

    with pytest.raises(ClusterRunError, match="execution confirmation required"):
        start_cluster_run(runtime, str(workspace), "coordinator", "修复登录页的报错")

    assert calls == []
    assert not (runtime / "cluster-runs").exists()


def test_cluster_confirmation_is_bound_expiring_single_use(tmp_path, monkeypatch):
    runtime = tmp_path / "runtime"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    calls: list[tuple] = []
    monkeypatch.setattr(
        cluster_run_module,
        "_run_cluster_workflow",
        lambda *args, **kwargs: calls.append((args, kwargs)),
    )
    goal = "修复登录页的报错"

    proposal = cluster_run_module.propose_cluster_run(
        runtime,
        "devframe-local",
        str(workspace),
        "coordinator",
        goal,
    )
    token = proposal["confirmationToken"]
    proposal_files = list((runtime / "cluster-run-proposals").glob("crp-*.json"))
    assert len(proposal_files) == 1
    persisted = proposal_files[0].read_text(encoding="utf-8")
    assert token not in persisted
    assert "tokenHash" in persisted

    started = start_cluster_run(
        runtime,
        str(workspace),
        "coordinator",
        goal,
        environment_id="devframe-local",
        proposal_id=proposal["proposalId"],
        confirmation_token=token,
        decision="execute",
    )
    assert started["started"] is True

    with pytest.raises(ClusterRunError, match="already consumed"):
        start_cluster_run(
            runtime,
            str(workspace),
            "coordinator",
            goal,
            environment_id="devframe-local",
            proposal_id=proposal["proposalId"],
            confirmation_token=token,
            decision="execute",
        )

    deadline = time.time() + 5
    while not calls and time.time() < deadline:
        time.sleep(0.02)
    assert len(calls) == 1


def test_stable_run_identity_and_source_linkage_make_start_idempotent(tmp_path, monkeypatch):
    runtime = tmp_path / "runtime"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    calls: list[tuple] = []
    monkeypatch.setattr(
        cluster_run_module,
        "_run_cluster_workflow",
        lambda *args, **kwargs: calls.append((args, kwargs)),
    )
    goal = "Implement one bounded change."
    proposal = cluster_run_module.propose_cluster_run(
        runtime,
        "devframe-local",
        str(workspace),
        "coordinator",
        goal,
        stable_run_id="g-stable-source-run",
        source_proposal_id="ctp-stable-source-proposal",
        source_turn_id="t3-stable-source-turn",
    )
    start_args = {
        "environment_id": "devframe-local",
        "proposal_id": proposal["proposalId"],
        "confirmation_token": proposal["confirmationToken"],
        "decision": "execute",
        "stable_run_id": "g-stable-source-run",
        "source_proposal_id": "ctp-stable-source-proposal",
        "source_turn_id": "t3-stable-source-turn",
    }

    started = start_cluster_run(
        runtime,
        str(workspace),
        "coordinator",
        goal,
        **start_args,
    )
    replay = start_cluster_run(
        runtime,
        str(workspace),
        "coordinator",
        goal,
        **start_args,
    )

    assert started["runId"] == replay["runId"] == "g-stable-source-run"
    assert replay["replayed"] is True
    record = cluster_run_module._load_run_record(runtime, "g-stable-source-run")
    assert record["sourceProposalId"] == "ctp-stable-source-proposal"
    assert record["sourceTurnId"] == "t3-stable-source-turn"
    deadline = time.time() + 5
    while not calls and time.time() < deadline:
        time.sleep(0.02)
    assert len(calls) == 1


def test_cluster_confirmation_rejects_expired_token(tmp_path, monkeypatch):
    runtime = tmp_path / "runtime"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    monkeypatch.setattr(cluster_run_module, "_run_cluster_workflow", lambda *args, **kwargs: None)
    goal = "修复登录页的报错"
    proposal = cluster_run_module.propose_cluster_run(
        runtime,
        "devframe-local",
        str(workspace),
        "coordinator",
        goal,
        ttl_seconds=0,
    )

    with pytest.raises(ClusterRunError, match="expired"):
        start_cluster_run(
            runtime,
            str(workspace),
            "coordinator",
            goal,
            environment_id="devframe-local",
            proposal_id=proposal["proposalId"],
            confirmation_token=proposal["confirmationToken"],
            decision="execute",
        )

    assert not list((runtime / "cluster-run-proposals").glob("*.used"))
    assert not (runtime / "cluster-runs").exists()


@pytest.mark.parametrize(
    "mutation",
    [
        "boolean-decision",
        "boolean-token",
        "forged-token",
        "wrong-environment",
        "wrong-project",
        "wrong-target",
        "wrong-goal",
    ],
)
def test_cluster_confirmation_fails_closed_for_malformed_forged_or_mismatched(
    tmp_path,
    monkeypatch,
    mutation,
):
    runtime = tmp_path / "runtime"
    workspace = tmp_path / "workspace"
    other_workspace = tmp_path / "other-workspace"
    workspace.mkdir()
    other_workspace.mkdir()
    calls: list[tuple] = []
    monkeypatch.setattr(
        cluster_run_module,
        "_run_cluster_workflow",
        lambda *args, **kwargs: calls.append((args, kwargs)),
    )
    goal = "修复登录页的报错"
    proposal = cluster_run_module.propose_cluster_run(
        runtime,
        "devframe-local",
        str(workspace),
        "coordinator",
        goal,
    )
    values = {
        "project": str(workspace),
        "target": "coordinator",
        "goal": goal,
        "environment_id": "devframe-local",
        "proposal_id": proposal["proposalId"],
        "confirmation_token": proposal["confirmationToken"],
        "decision": "execute",
    }
    if mutation == "boolean-decision":
        values["decision"] = True
    elif mutation == "boolean-token":
        values["confirmation_token"] = True
    elif mutation == "forged-token":
        values["confirmation_token"] = "forged"
    elif mutation == "wrong-environment":
        values["environment_id"] = "other-environment"
    elif mutation == "wrong-project":
        values["project"] = str(other_workspace)
    elif mutation == "wrong-target":
        values["target"] = "executor"
    elif mutation == "wrong-goal":
        values["goal"] = goal + "!"

    with pytest.raises(ClusterRunError):
        start_cluster_run(
            runtime,
            values["project"],
            values["target"],
            values["goal"],
            environment_id=values["environment_id"],
            proposal_id=values["proposal_id"],
            confirmation_token=values["confirmation_token"],
            decision=values["decision"],
        )

    assert calls == []
    assert not list((runtime / "cluster-run-proposals").glob("*.used"))
    assert not (runtime / "cluster-runs").exists()


def test_cluster_confirmation_allows_only_one_concurrent_consumer(tmp_path, monkeypatch):
    runtime = tmp_path / "runtime"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    calls: list[tuple] = []
    monkeypatch.setattr(
        cluster_run_module,
        "_run_cluster_workflow",
        lambda *args, **kwargs: calls.append((args, kwargs)),
    )
    goal = "修复登录页的报错"
    proposal = cluster_run_module.propose_cluster_run(
        runtime,
        "devframe-local",
        str(workspace),
        "coordinator",
        goal,
    )

    def consume():
        try:
            return start_cluster_run(
                runtime,
                str(workspace),
                "coordinator",
                goal,
                environment_id="devframe-local",
                proposal_id=proposal["proposalId"],
                confirmation_token=proposal["confirmationToken"],
                decision="execute",
            )
        except ClusterRunError as exc:
            return exc

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _index: consume(), range(2)))

    assert sum(isinstance(result, dict) for result in results) == 1
    assert sum(
        isinstance(result, ClusterRunError) and "already consumed" in str(result)
        for result in results
    ) == 1
    deadline = time.time() + 5
    while not calls and time.time() < deadline:
        time.sleep(0.02)
    assert len(calls) == 1


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
    from types import SimpleNamespace

    from control_plane.cluster_run import list_cluster_runs

    runtime = tmp_path / "runtime"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    monkeypatch.setattr(
        cluster_run_module,
        "_run_cluster_workflow",
        lambda rd, path, target, goal, run_id, on_prepared=None, cancel_marker=None: SimpleNamespace(
            status="completed", verdict="continue", passed_agents=2, failed_agents=0, go_run_id="go-123"
        ),
    )
    started = _confirmed_start(runtime, str(workspace), "coordinator", "ship it")
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


def test_cancel_before_go_run_and_terminal_races_stay_truthful(tmp_path, monkeypatch):
    from threading import Event
    from types import SimpleNamespace

    from control_plane.cluster_run import cancel_cluster_run, list_cluster_runs

    runtime = tmp_path / "runtime"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    allow_finish = Event()
    with pytest.raises(ClusterRunError) as missing_error:
        cancel_cluster_run(runtime, "g-missing", requested_by="rd-code-editor")
    assert missing_error.value.error_code == "cluster_run_not_found"
    assert missing_error.value.status_code == 404
    with pytest.raises(ClusterRunError):
        cancel_cluster_run(runtime, "../g-missing", requested_by="rd-code-editor")

    def fake_workflow(
        rd,
        path,
        target,
        goal,
        run_id,
        on_prepared=None,
        cancel_marker=None,
    ):
        assert cancel_marker == cluster_run_module._cancellation_marker_path(rd, run_id)
        assert allow_finish.wait(timeout=5)
        if on_prepared is not None:
            on_prepared("go-after-cancel")
        return SimpleNamespace(
            status="completed",
            verdict="continue",
            passed_agents=1,
            failed_agents=0,
            go_run_id="go-after-cancel",
        )

    monkeypatch.setattr(cluster_run_module, "_run_cluster_workflow", fake_workflow)
    started = _confirmed_start(
        runtime,
        str(workspace),
        "coordinator",
        "implement cancellation",
    )
    run_id = started["runId"]

    requested = cancel_cluster_run(runtime, run_id, requested_by="rd-code-editor")
    assert requested["status"] == "cancel_requested"
    assert requested["cancelRequestedBy"] == "rd-code-editor"
    assert cluster_run_module._cancellation_marker_path(runtime, run_id).is_file()

    allow_finish.set()
    deadline = time.monotonic() + 5
    record = None
    while time.monotonic() < deadline:
        record = next(
            (item for item in list_cluster_runs(runtime) if item["runId"] == run_id),
            None,
        )
        if (
            record
            and record.get("status") == "cancelled"
            and record.get("goRunId") == "go-after-cancel"
        ):
            break
        time.sleep(0.02)
    assert record is not None
    assert record["status"] == "cancelled"
    assert record["goRunId"] == "go-after-cancel"
    assert record.get("finishedAt")

    repeated = cancel_cluster_run(runtime, run_id, requested_by="rd-code-editor")
    assert repeated["status"] == "cancelled"

    completed = _confirmed_start(
        runtime,
        str(workspace),
        "coordinator",
        "ship the finished result",
    )
    completed_id = completed["runId"]
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        completed_record = next(
            (
                item
                for item in list_cluster_runs(runtime)
                if item["runId"] == completed_id
            ),
            None,
        )
        if completed_record and completed_record.get("status") == "completed":
            break
        time.sleep(0.02)
    assert completed_record["status"] == "completed"
    with pytest.raises(ClusterRunError) as terminal_error:
        cancel_cluster_run(runtime, completed_id, requested_by="rd-code-editor")
    assert terminal_error.value.error_code == "cluster_run_terminal"
    assert terminal_error.value.status_code == 409


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

        status, proposal = _post_json(base_url, "/api/t3/cluster-run-proposal", {
            "environmentId": "devframe-local",
            "projectId": str(workspace),
            "target": "coordinator",
            "goal": "add a settings page",
        })
        assert status == 201
        assert proposal["proposed"] is True
        assert proposal["started"] is False

        status, started = _post_json(base_url, "/api/t3/cluster-run", {
            "environmentId": "devframe-local",
            "projectId": str(workspace),
            "target": "coordinator",
            "goal": "add a settings page",
            "proposalId": proposal["proposalId"],
            "confirmationToken": proposal["confirmationToken"],
            "decision": "execute",
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


def test_dashboard_status_request_is_nonexecuting_without_confirmation(tmp_path, monkeypatch):
    calls: list[tuple] = []
    monkeypatch.setattr(
        cluster_run_module,
        "_run_cluster_workflow",
        lambda *args, **kwargs: calls.append((args, kwargs)),
    )
    runtime_dir = tmp_path / "runtime"
    workspace = tmp_path / "workspace"
    runtime_dir.mkdir()
    workspace.mkdir()
    server = build_dashboard_server(runtime_dir=runtime_dir, port=0, refresh_seconds=0)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        status, result = _post_json(base_url, "/api/t3/cluster-run", {
            "projectId": str(workspace),
            "target": "coordinator",
            "goal": "汇报一下目前的项目进度情况",
        })
        assert status == 200
        assert result["started"] is False
        assert result["kind"] == "conversation"
        assert result["answer"]
        assert calls == []
        assert not (runtime_dir / "go-runs").exists()
        assert not (runtime_dir / "rdgoal-outbox").exists()
        assert list(workspace.iterdir()) == []
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_dashboard_development_request_requires_confirmation(tmp_path, monkeypatch):
    calls: list[tuple] = []
    monkeypatch.setattr(
        cluster_run_module,
        "_run_cluster_workflow",
        lambda *args, **kwargs: calls.append((args, kwargs)),
    )
    runtime_dir = tmp_path / "runtime"
    workspace = tmp_path / "workspace"
    runtime_dir.mkdir()
    workspace.mkdir()
    server = build_dashboard_server(runtime_dir=runtime_dir, port=0, refresh_seconds=0)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        status, raw_body = _request_status(
            base_url,
            "/api/t3/cluster-run",
            "POST",
            payload={
                "projectId": str(workspace),
                "target": "coordinator",
                "goal": "修复登录页的报错",
            },
        )
        assert status == 409
        assert json.loads(raw_body)["error"] == "execution_confirmation_required"
        assert calls == []
        assert not (runtime_dir / "cluster-runs").exists()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_dashboard_cancel_terminates_real_worker_tree_and_preserves_evidence(
    tmp_path,
    monkeypatch,
):
    from control_plane import go_dispatch as go_dispatch_module
    from control_plane.go_dispatch import load_go_run_result

    runtime_dir = tmp_path / "runtime"
    workspace = tmp_path / "workspace"
    runtime_dir.mkdir()
    workspace.mkdir()
    script_path = tmp_path / "sleeping-go-worker.py"
    script_path.write_text(
        "import json, os, pathlib, subprocess, sys, time\n"
        "packet = pathlib.Path(os.environ['RDGOAL_PACKET_DIR'])\n"
        "child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(120)'])\n"
        "(packet / 'worker-pids.json').write_text("
        "json.dumps({'parent': os.getpid(), 'child': child.pid}), encoding='utf-8')\n"
        "time.sleep(120)\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        go_dispatch_module,
        "build_go_worker_command",
        lambda **_kwargs: [sys.executable, str(script_path)],
    )

    server = build_dashboard_server(runtime_dir=runtime_dir, port=0, refresh_seconds=0)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_address[1]}"
    discovered_pids: dict[str, int] = {}
    try:
        status, proposal = _post_json(base_url, "/api/t3/cluster-run-proposal", {
            "environmentId": "devframe-local",
            "projectId": str(workspace),
            "target": "coordinator",
            "goal": "implement a cancellable worker probe",
        })
        assert status == 201
        status, started = _post_json(base_url, "/api/t3/cluster-run", {
            "environmentId": "devframe-local",
            "projectId": str(workspace),
            "target": "coordinator",
            "goal": "implement a cancellable worker probe",
            "proposalId": proposal["proposalId"],
            "confirmationToken": proposal["confirmationToken"],
            "decision": "execute",
        })
        assert status == 202
        run_id = started["runId"]

        deadline = time.monotonic() + 15
        pid_paths: list[Path] = []
        while time.monotonic() < deadline:
            pid_paths = list(runtime_dir.rglob("worker-pids.json"))
            if pid_paths:
                break
            time.sleep(0.05)
        assert pid_paths, "real HTTP-started worker process did not launch"
        for pid_path in pid_paths:
            for role, pid in json.loads(pid_path.read_text(encoding="utf-8")).items():
                discovered_pids[f"{pid_path.parent.name}:{role}"] = pid

        status, cancelled = _post_json(base_url, "/api/t3/cluster-run-cancel", {
            "runId": run_id,
            "requestedBy": "rd-code-editor",
        })
        assert status == 202
        assert cancelled["status"] == "cancel_requested"

        deadline = time.monotonic() + 15
        final_record = None
        while time.monotonic() < deadline:
            final_record = next(
                (
                    item
                    for item in cluster_run_module.list_cluster_runs(runtime_dir)
                    if item["runId"] == run_id
                ),
                None,
            )
            if final_record and final_record.get("status") == "cancelled":
                break
            time.sleep(0.05)
        assert final_record is not None
        assert final_record["status"] == "cancelled"
        assert final_record.get("goRunId")

        for pid_path in runtime_dir.rglob("worker-pids.json"):
            for role, pid in json.loads(pid_path.read_text(encoding="utf-8")).items():
                discovered_pids[f"{pid_path.parent.name}:{role}"] = pid
        deadline = time.monotonic() + 5
        while (
            any(cluster_run_module._pid_alive(pid) for pid in discovered_pids.values())
            and time.monotonic() < deadline
        ):
            time.sleep(0.05)
        assert discovered_pids
        assert not any(
            cluster_run_module._pid_alive(pid) for pid in discovered_pids.values()
        )

        go_result = load_go_run_result(runtime_dir, final_record["goRunId"])
        assert go_result.status == "cancelled"
        assert go_result.agents
        assert all(agent.worker_status == "cancelled" for agent in go_result.agents)
        for agent in go_result.agents:
            report_path = Path(agent.report_path)
            assert report_path.is_file()
            assert "Status**: cancelled" in report_path.read_text(encoding="utf-8")
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
        import os
        import signal
        import subprocess

        for pid in discovered_pids.values():
            if not cluster_run_module._pid_alive(pid):
                continue
            if os.name == "nt":
                subprocess.run(
                    ["taskkill", "/PID", str(pid), "/T", "/F"],
                    capture_output=True,
                    text=True,
                    check=False,
                )
            else:
                try:
                    os.kill(pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass


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
        assert body["globalCoordinatorThread"] is None
        assert body["emptyStateReason"] == "missing_global_coordinator_thread"
        assert [thread["id"] for thread in body["sortedShell"]["threads"]] == [
            "demo-beta-goal",
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
        assert body["globalCoordinatorThread"] is None
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
    runtime = tmp_path / "runtime"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    calls: list[tuple] = []
    monkeypatch.setattr(
        cluster_run_module,
        "_run_cluster_workflow",
        lambda rd, path, target, goal, run_id, on_prepared=None, cancel_marker=None: calls.append((path, target, goal, run_id)),
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

    started = _confirmed_start(runtime, "demo-project", "coordinator", "ship the feature")

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
    calls: list[tuple] = []
    monkeypatch.setattr(cluster_run_module, "_run_cluster_workflow", lambda *a, **k: calls.append(a))
    runtime = tmp_path / "runtime"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    # Build a "/D:/..." style path from the real workspace dir.
    native = str(workspace)
    if len(native) >= 2 and native[1] == ":":
        url_style = "/" + native.replace("\\", "/")
        started = _confirmed_start(runtime, url_style, "coordinator", "ship it")
        assert started["started"] is True
        deadline = time.time() + 5
        while time.time() < deadline and not calls:
            time.sleep(0.02)
        assert calls


def test_orphaned_running_run_is_marked_interrupted(tmp_path, monkeypatch):
    """A run left at 'running' by a control-plane process that no longer exists
    must be reconciled to 'interrupted' on read, never shown frozen forever."""
    from control_plane.cluster_run import (
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
    assert classify_goal("汇报一下目前的项目进度情况") == GOAL_KIND_CONVERSATION
    # Real development goals (including a greeting that carries a real task).
    assert classify_goal("在 README 增加快速开始章节") == GOAL_KIND_DEVELOPMENT
    assert classify_goal("修复登录页的空指针报错") == GOAL_KIND_DEVELOPMENT
    assert classify_goal("你好，帮我修复登录bug") == GOAL_KIND_DEVELOPMENT
    assert classify_goal("add a date formatter to utils.ts") == GOAL_KIND_DEVELOPMENT
    assert classify_goal("refactor the auth module") == GOAL_KIND_DEVELOPMENT
    assert classify_goal("ship the feature") == GOAL_KIND_DEVELOPMENT


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
    assert started["started"] is False
    assert started["kind"] == "conversation"
    assert "主控" in started["answer"]
    assert calls == []  # never dispatched a token-spending run

    detail = cluster_run_module.cluster_run_detail(runtime, started["runId"])
    assert detail["status"] == "answered"
    assert detail["messages"]
    assert detail["messages"][0]["from"] == "coordinator"
    assert detail["agents"] == []


def test_development_goal_still_dispatches(tmp_path, monkeypatch):
    calls: list[tuple] = []
    monkeypatch.setattr(
        cluster_run_module,
        "_run_cluster_workflow",
        lambda rd, path, target, goal, run_id, on_prepared=None, cancel_marker=None: calls.append((target, goal)),
    )
    runtime = tmp_path / "runtime"
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    started = _confirmed_start(runtime, str(workspace), "coordinator", "修复登录页的报错")
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
