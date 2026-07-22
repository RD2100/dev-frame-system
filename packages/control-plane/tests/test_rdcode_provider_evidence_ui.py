from __future__ import annotations

import json
import time
from contextlib import contextmanager
from pathlib import Path
from threading import Thread
from types import SimpleNamespace
from urllib.request import Request, urlopen

import pytest
from jsonschema.validators import validator_for

from control_plane import cluster_run as cluster_run_module
from control_plane.dashboard import build_dashboard_server
from control_plane.visual_state import public_cluster_run_states


REPO_ROOT = Path(__file__).resolve().parents[3]
_SELECTION_A = {
    "executor": " codex-executor ",
    "modelProvider": " provider-alpha ",
    "model": " model-alpha ",
}
_SELECTION_B = {
    "executor": "opencode-executor",
    "modelProvider": "provider-beta",
    "model": "model-beta",
}


def _request_json(
    base_url: str,
    path: str,
    *,
    payload: dict[str, object] | None = None,
) -> tuple[int, dict]:
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    headers = {"Accept": "application/json"}
    method = "GET"
    if data is not None:
        headers.update(
            {
                "Content-Type": "application/json",
                "Origin": base_url,
            }
        )
        method = "POST"
    request = Request(
        f"{base_url}{path}",
        data=data,
        headers=headers,
        method=method,
    )
    with urlopen(request, timeout=5) as response:
        return response.status, json.loads(response.read().decode("utf-8"))


@contextmanager
def _running_dashboard(runtime_dir: Path):
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


def _wait_for_record(runtime_dir: Path, run_id: str) -> dict:
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        record = next(
            (
                item
                for item in cluster_run_module.list_cluster_runs(runtime_dir)
                if item.get("runId") == run_id
            ),
            None,
        )
        if record and record.get("status") != "running":
            return record
        time.sleep(0.02)
    raise AssertionError(f"cluster run did not finish: {run_id}")


def _completed_workflow(
    runtime_dir,
    project_path,
    target,
    goal,
    run_id,
    *,
    on_prepared=None,
    executor=None,
    model_provider=None,
    model=None,
):
    if on_prepared is not None:
        on_prepared("go-selection-evidence-probe")
    return SimpleNamespace(
        status="completed",
        verdict="awaiting_review",
        passed_agents=2,
        failed_agents=0,
        go_run_id="go-selection-evidence-probe",
    )


def _item_by_id(items: list[dict], item_id: str) -> dict:
    return next(
        item
        for item in items
        if item.get("id") == item_id or item.get("run_id") == item_id
    )


def _validate_t3_shell(shell: dict) -> None:
    schema = json.loads(
        (REPO_ROOT / "schemas" / "t3_client_shell.schema.json").read_text(
            encoding="utf-8"
        )
    )
    validator_class = validator_for(schema)
    validator_class.check_schema(schema)
    validator_class(schema).validate(shell)


@pytest.mark.parametrize("selection", [_SELECTION_A, _SELECTION_B])
def test_loopback_cluster_run_projects_exact_selection_and_record_provenance(
    tmp_path,
    monkeypatch,
    selection,
):
    runtime_dir = tmp_path / "runtime"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    monkeypatch.setattr(
        cluster_run_module,
        "_run_cluster_workflow",
        _completed_workflow,
    )

    with _running_dashboard(runtime_dir) as base_url:
        status, started = _request_json(
            base_url,
            "/api/t3/cluster-run",
            payload={
                "projectId": str(workspace),
                "target": "coordinator",
                "goal": "Implement the bounded governed-selection evidence probe.",
                **selection,
            },
        )
        assert status == 202
        run_id = started["runId"]
        record = _wait_for_record(runtime_dir, run_id)
        visual_runs = public_cluster_run_states([record])
        shell_status, shell = _request_json(base_url, "/t3-shell.json")

    assert shell_status == 200
    _validate_t3_shell(shell)
    assert {field: record[field] for field in selection} == selection

    visual_run = _item_by_id(visual_runs, run_id)
    assert visual_run["execution_selection"] == {
        "executor": selection["executor"],
        "model_provider": selection["modelProvider"],
        "model": selection["model"],
        "provenance": {
            "source_type": "cluster_run_record",
            "source_id": run_id,
            "record_ref": f"cluster-run:{run_id}",
        },
    }

    thread = _item_by_id(shell["t3"]["threads"], run_id)
    detail = _item_by_id(shell["t3"]["threadDetails"], run_id)
    assert thread["modelSelection"] == {
        "instanceId": selection["executor"],
        "model": selection["model"],
    }
    assert thread["session"]["providerName"] == "devframe"
    selection_activity = next(
        activity
        for activity in detail["activities"]
        if activity.get("kind") == "devframe.execution.selection"
    )
    assert selection_activity["payload"]["executionSelection"] == {
        "executor": selection["executor"],
        "modelProvider": selection["modelProvider"],
        "model": selection["model"],
    }
    assert selection_activity["payload"]["provenance"] == {
        "sourceType": "cluster_run_record",
        "sourceId": run_id,
        "recordRef": f"cluster-run:{run_id}",
    }


def test_loopback_cluster_run_without_selection_does_not_fabricate_evidence(
    tmp_path,
    monkeypatch,
):
    runtime_dir = tmp_path / "runtime"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    monkeypatch.setattr(
        cluster_run_module,
        "_run_cluster_workflow",
        _completed_workflow,
    )

    with _running_dashboard(runtime_dir) as base_url:
        status, started = _request_json(
            base_url,
            "/api/t3/cluster-run",
            payload={
                "projectId": str(workspace),
                "target": "coordinator",
                "goal": "Preserve the legacy unselected cluster projection.",
            },
        )
        assert status == 202
        run_id = started["runId"]
        record = _wait_for_record(runtime_dir, run_id)
        visual_runs = public_cluster_run_states([record])
        shell_status, shell = _request_json(base_url, "/t3-shell.json")

    assert shell_status == 200
    _validate_t3_shell(shell)
    for field in ("executor", "modelProvider", "model"):
        assert field not in record

    visual_run = _item_by_id(visual_runs, run_id)
    assert "execution_selection" not in visual_run

    thread = _item_by_id(shell["t3"]["threads"], run_id)
    detail = _item_by_id(shell["t3"]["threadDetails"], run_id)
    assert thread["session"]["providerName"] == "devframe"
    assert thread["devframe"]["evidenceRefs"] == []
    assert all(
        activity.get("kind") != "devframe.execution.selection"
        for activity in detail["activities"]
    )


def test_failed_cluster_run_keeps_failure_status_with_selection_evidence(
    tmp_path,
    monkeypatch,
):
    runtime_dir = tmp_path / "runtime"
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    def fail_workflow(*args, **kwargs):
        raise RuntimeError("safe local workflow probe failed")

    monkeypatch.setattr(
        cluster_run_module,
        "_run_cluster_workflow",
        fail_workflow,
    )

    with _running_dashboard(runtime_dir) as base_url:
        status, started = _request_json(
            base_url,
            "/api/t3/cluster-run",
            payload={
                "projectId": str(workspace),
                "target": "executor",
                "goal": "Exercise the governed-selection failure projection.",
                **_SELECTION_B,
            },
        )
        assert status == 202
        run_id = started["runId"]
        record = _wait_for_record(runtime_dir, run_id)
        visual_runs = public_cluster_run_states([record])
        shell_status, shell = _request_json(base_url, "/t3-shell.json")

    assert shell_status == 200
    _validate_t3_shell(shell)
    assert record["status"] == "failed"
    visual_run = _item_by_id(visual_runs, run_id)
    assert visual_run["status"] == "failed"
    assert visual_run["execution_selection"]["model"] == _SELECTION_B["model"]

    thread = _item_by_id(shell["t3"]["threads"], run_id)
    detail = _item_by_id(shell["t3"]["threadDetails"], run_id)
    assert thread["session"]["status"] == "error"
    assert thread["session"]["lastError"] == (
        "Goal conversation failed or was interrupted."
    )
    assert "- Status: failed" in detail["messages"][0]["text"]
    goal_activity = next(
        activity
        for activity in detail["activities"]
        if activity.get("kind") == "devframe.goal.projected"
    )
    assert goal_activity["payload"]["status"] == "failed"
    selection_activity = next(
        activity
        for activity in detail["activities"]
        if activity.get("kind") == "devframe.execution.selection"
    )
    assert selection_activity["payload"]["executionSelection"] == _SELECTION_B
    assert selection_activity["payload"]["provenance"] == {
        "sourceType": "cluster_run_record",
        "sourceId": run_id,
        "recordRef": f"cluster-run:{run_id}",
    }
