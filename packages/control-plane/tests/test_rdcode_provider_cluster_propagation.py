from __future__ import annotations

import json
import time
from contextlib import contextmanager
from pathlib import Path
from threading import Thread
from types import SimpleNamespace
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from control_plane import cluster_run as cluster_run_module
from control_plane.cli._core import cmd_init
from control_plane.dashboard import build_dashboard_server
from control_plane.workflow_engine import WorkflowEngine


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
    try:
        with urlopen(request, timeout=5) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except HTTPError as error:
        return error.code, json.loads(error.read().decode("utf-8"))


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


@pytest.mark.parametrize(
    ("target", "selection"),
    [
        ("coordinator", _SELECTION_A),
        ("executor", _SELECTION_B),
        ("reviewer", _SELECTION_A),
    ],
)
def test_http_cluster_run_preserves_selection_through_workflow_boundary(
    tmp_path,
    monkeypatch,
    target,
    selection,
):
    runtime_dir = tmp_path / "runtime"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    calls: list[dict[str, object]] = []

    def capture_workflow(
        self,
        project_path,
        goal,
        *,
        worker,
        model_provider,
        model,
        on_prepared=None,
    ):
        calls.append(
            {
                "runtimeDir": str(self.runtime_dir),
                "projectPath": str(project_path),
                "goal": goal,
                "worker": worker,
                "modelProvider": model_provider,
                "model": model,
            }
        )
        if on_prepared is not None:
            on_prepared("go-selection-probe")
        return SimpleNamespace(
            status="completed",
            verdict="awaiting_review",
            passed_agents=2,
            failed_agents=0,
            go_run_id="go-selection-probe",
        )

    monkeypatch.setattr(WorkflowEngine, "run_coding_workflow", capture_workflow)

    with _running_dashboard(runtime_dir) as base_url:
        status, started = _request_json(
            base_url,
            "/api/t3/cluster-run",
            payload={
                "projectId": str(workspace),
                "target": target,
                "goal": "Implement the bounded provider propagation probe.",
                **selection,
            },
        )
        assert status == 202
        record = _wait_for_record(runtime_dir, started["runId"])

    assert calls == [
        {
            "runtimeDir": str(runtime_dir.resolve()),
            "projectPath": str(workspace.resolve()),
            "goal": "Implement the bounded provider propagation probe.",
            "worker": selection["executor"],
            "modelProvider": selection["modelProvider"],
            "model": selection["model"],
        }
    ]
    assert record["target"] == target
    assert record["executor"] == selection["executor"]
    assert record["modelProvider"] == selection["modelProvider"]
    assert record["model"] == selection["model"]
    assert started["executor"] == selection["executor"]
    assert started["modelProvider"] == selection["modelProvider"]
    assert started["model"] == selection["model"]


def test_http_cluster_run_omitted_selection_preserves_legacy_shape(
    tmp_path,
    monkeypatch,
):
    runtime_dir = tmp_path / "runtime"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    calls: list[tuple[str, str]] = []

    def capture_legacy_workflow(self, project_path, goal, *, on_prepared=None):
        calls.append((str(project_path), goal))
        return SimpleNamespace(
            status="completed",
            verdict="awaiting_review",
            passed_agents=2,
            failed_agents=0,
            go_run_id="go-legacy-probe",
        )

    monkeypatch.setattr(
        WorkflowEngine,
        "run_coding_workflow",
        capture_legacy_workflow,
    )

    with _running_dashboard(runtime_dir) as base_url:
        status, started = _request_json(
            base_url,
            "/api/t3/cluster-run",
            payload={
                "projectId": str(workspace),
                "target": "coordinator",
                "goal": "Preserve the existing cluster request shape.",
            },
        )
        assert status == 202
        record = _wait_for_record(runtime_dir, started["runId"])

    assert calls == [
        (
            str(workspace.resolve()),
            "Preserve the existing cluster request shape.",
        )
    ]
    for field in ("executor", "modelProvider", "model"):
        assert field not in started
        assert field not in record


@pytest.mark.parametrize(
    "selection",
    [
        {"executor": "codex", "modelProvider": "provider-alpha"},
        {"executor": "codex", "modelProvider": " ", "model": "model-alpha"},
        {
            "executor": ["codex"],
            "modelProvider": "provider-alpha",
            "model": "model-alpha",
        },
        {"executor": "codex", "modelProvider": None, "model": "model-alpha"},
    ],
)
def test_http_cluster_run_rejects_invalid_selection_before_artifacts(
    tmp_path,
    monkeypatch,
    selection,
):
    runtime_dir = tmp_path / "runtime"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    workflow_calls: list[object] = []

    monkeypatch.setattr(
        WorkflowEngine,
        "run_coding_workflow",
        lambda *args, **kwargs: workflow_calls.append((args, kwargs)),
    )

    with _running_dashboard(runtime_dir) as base_url:
        status, _response = _request_json(
            base_url,
            "/api/t3/cluster-run",
            payload={
                "projectId": str(workspace),
                "target": "coordinator",
                "goal": "Reject this invalid selection.",
                **selection,
            },
        )

    assert status == 400
    assert workflow_calls == []
    assert cluster_run_module.list_cluster_runs(runtime_dir) == []
    assert not (runtime_dir / "cluster-runs").exists()
    assert not (runtime_dir / "go-runs").exists()


def test_http_cluster_run_rejects_selection_for_rdpaper_before_artifacts(
    tmp_path,
    monkeypatch,
):
    runtime_dir = tmp_path / "runtime"
    paper_root = tmp_path / "paper-project"
    assert cmd_init("paper_iteration", str(paper_root)) == 0
    paper_calls: list[object] = []

    monkeypatch.setattr(
        cluster_run_module,
        "_run_paper_workflow",
        lambda *args, **kwargs: paper_calls.append((args, kwargs)),
    )

    with _running_dashboard(runtime_dir) as base_url:
        status, response = _request_json(
            base_url,
            "/api/t3/cluster-run",
            payload={
                "projectId": str(paper_root),
                "target": "rdpaper",
                "goal": "Run the bounded synthetic paper review vertical.",
                **_SELECTION_B,
            },
        )

    assert status == 400
    assert response["error"] == "cluster_run_rejected"
    assert "does not consume executor/model selection" in response["detail"]
    assert paper_calls == []
    assert cluster_run_module.list_cluster_runs(runtime_dir) == []
    assert not (runtime_dir / "cluster-runs").exists()
    assert not (runtime_dir / "go-runs").exists()
