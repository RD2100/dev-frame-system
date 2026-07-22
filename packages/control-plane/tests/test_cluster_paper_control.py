from __future__ import annotations

import json
import os
import time
from contextlib import contextmanager
from pathlib import Path
from threading import Event, Lock, Thread
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, urlopen

import pytest

from control_plane import cluster_run as cluster_run_module
from control_plane.cli._core import cmd_init
from control_plane.dashboard import build_dashboard_server


def _request_json(
    base_url: str,
    path: str,
    *,
    payload: dict | None = None,
) -> tuple[int, dict]:
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    headers = {"Accept": "application/json"}
    method = "GET"
    if data is not None:
        headers.update({
            "Content-Type": "application/json",
            "Origin": base_url,
        })
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


def _wait_for_cluster_run(base_url: str, run_id: str) -> dict:
    deadline = time.time() + 15
    while time.time() < deadline:
        status, payload = _request_json(base_url, "/api/t3/cluster-runs")
        assert status == 200
        record = next(
            (item for item in payload["runs"] if item.get("runId") == run_id),
            None,
        )
        if record and record.get("status") in {"review_pending", "failed"}:
            return record
        time.sleep(0.05)
    raise AssertionError(f"cluster paper run did not finish: {run_id}")


@contextmanager
def _running_dashboard(runtime_dir: Path, paper_root: Path):
    server = build_dashboard_server(
        runtime_dir=runtime_dir,
        paper_project_dirs=[paper_root],
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


def test_http_cluster_paper_run_reaches_human_review_boundary(tmp_path, monkeypatch):
    runtime_dir = tmp_path / "runtime"
    paper_root = tmp_path / "paper-project"
    assert cmd_init("paper_iteration", str(paper_root)) == 0

    def fail_if_generic_workflow_runs(*_args, **_kwargs):
        raise AssertionError("rdpaper must not invoke the generic WorkflowEngine")

    monkeypatch.setattr(
        cluster_run_module,
        "_run_cluster_workflow",
        fail_if_generic_workflow_runs,
    )

    with _running_dashboard(runtime_dir, paper_root) as base_url:
        targets_status, targets_payload = _request_json(
            base_url,
            "/api/t3/cluster-targets?project=" + quote(paper_root.name),
        )
        target_ids = [item["id"] for item in targets_payload.get("targets", [])]

        start_status, started = _request_json(
            base_url,
            "/api/t3/cluster-run",
            payload={
                "projectId": str(paper_root),
                "target": "rdpaper",
                "goal": "Run the existing local synthetic paper review vertical.",
                "proposedBy": "rd-code-test",
            },
        )

        assert targets_status == 200
        assert start_status == 202, (
            f"targets={target_ids}; status={start_status}; response={started}"
        )
        assert "rdpaper" in target_ids
        assert started["started"] is True
        assert started["target"] == "rdpaper"

        record = _wait_for_cluster_run(base_url, started["runId"])
        paper_run_id = "paper-project-paper-review"
        paper_action_id = f"{paper_run_id}-command-action"
        required_evidence = {
            str((paper_root / "TASKSPEC.json").resolve()),
            str((paper_root / "execution-report.json").resolve()),
            str((paper_root / "closure" / "FLOW_OUTCOME.json").resolve()),
            str((paper_root / "evidence" / "PAPER_PIPELINE_GATE.json").resolve()),
            str((paper_root / "evidence" / "ref-paper-review-pack.zip").resolve()),
        }

        assert record["kind"] == "paper"
        assert record["status"] == "review_pending"
        assert record["paperRunId"] == paper_run_id
        assert record["paperActionId"] == paper_action_id
        assert record["paperActionEvidence"]["status"] == "open"
        assert "devframe paper finalize" in record["paperActionEvidence"]["command"]
        assert required_evidence <= set(record["evidenceRefs"])
        assert all(path.is_file() for path in map(Path, required_evidence))
        assert not (paper_root / "closure" / "FINAL_VERDICT.json").exists()

        flow = json.loads(
            (paper_root / "closure" / "FLOW_OUTCOME.json").read_text(
                encoding="utf-8"
            )
        )
        assert flow["final_status"] == "review_pending"

        shell_status, shell = _request_json(base_url, "/t3-shell.json")
        assert shell_status == 200
        paper_thread = next(
            item
            for item in shell["t3"]["threads"]
            if item.get("devframe", {}).get("runId") == paper_run_id
        )
        finalize_action = next(
            item
            for item in paper_thread["devframe"]["actionDetails"]
            if item["actionId"] == paper_action_id
        )
        assert paper_thread["session"]["status"] == "ready"
        assert finalize_action["status"] == "open"
        assert "devframe paper finalize" in finalize_action["command"]


def test_http_cluster_paper_run_rejects_uninitialized_project(tmp_path):
    runtime_dir = tmp_path / "runtime"
    paper_root = tmp_path / "not-initialized"
    paper_root.mkdir()

    with _running_dashboard(runtime_dir, paper_root) as base_url:
        status, payload = _request_json(
            base_url,
            "/api/t3/cluster-run",
            payload={
                "projectId": str(paper_root),
                "target": "rdpaper",
                "goal": "Run the local synthetic paper review vertical.",
            },
        )
        _, runs = _request_json(base_url, "/api/t3/cluster-runs")

    assert status == 400
    assert payload["error"] == "cluster_run_rejected"
    assert "missing initialized files" in payload["detail"]
    assert runs["runs"] == []


@pytest.mark.parametrize(
    "unexpected_relative_path",
    ["REAL_PAPER.pdf", "nested/SYNTHETIC_PAPER.md"],
)
def test_http_cluster_paper_run_rejects_unexpected_input_file(
    tmp_path,
    unexpected_relative_path,
):
    runtime_dir = tmp_path / "runtime"
    paper_root = tmp_path / "paper-project"
    assert cmd_init("paper_iteration", str(paper_root)) == 0
    input_dir = paper_root / "input"
    unexpected_path = input_dir / unexpected_relative_path
    unexpected_path.parent.mkdir(parents=True)
    unexpected_path.write_bytes(b"not real paper content")

    with _running_dashboard(runtime_dir, paper_root) as base_url:
        status, payload = _request_json(
            base_url,
            "/api/t3/cluster-run",
            payload={
                "projectId": str(paper_root),
                "target": "rdpaper",
                "goal": "Run the local synthetic paper review vertical.",
            },
        )
        _, runs = _request_json(base_url, "/api/t3/cluster-runs")

    assert status == 400
    assert payload["error"] == "cluster_run_rejected"
    assert "unexpected input files:" in payload["detail"]
    assert unexpected_relative_path in payload["detail"]
    assert runs["runs"] == []


def test_http_cluster_paper_run_rejects_unexpected_managed_artifact(
    tmp_path,
    monkeypatch,
):
    runtime_dir = tmp_path / "runtime"
    paper_root = tmp_path / "paper-project"
    assert cmd_init("paper_iteration", str(paper_root)) == 0
    unexpected_path = paper_root / "review" / "REAL_PAPER.md"
    unexpected_path.parent.mkdir()
    unexpected_path.write_text("not a managed review artifact", encoding="utf-8")

    def fail_if_worker_starts(*_args, **_kwargs):
        raise AssertionError("unexpected managed artifact must be rejected before worker start")

    monkeypatch.setattr(
        cluster_run_module,
        "_run_paper_workflow",
        fail_if_worker_starts,
    )

    with _running_dashboard(runtime_dir, paper_root) as base_url:
        status, payload = _request_json(
            base_url,
            "/api/t3/cluster-run",
            payload={
                "projectId": str(paper_root),
                "target": "rdpaper",
                "goal": "Run the local synthetic paper review vertical.",
            },
        )
        _, runs = _request_json(base_url, "/api/t3/cluster-runs")

    assert status == 400
    assert payload["error"] == "cluster_run_rejected"
    assert "unexpected managed paper paths: review/REAL_PAPER.md" in payload["detail"]
    assert runs["runs"] == []


def test_http_cluster_paper_run_rejects_managed_file_slot_as_directory(
    tmp_path,
    monkeypatch,
):
    runtime_dir = tmp_path / "runtime"
    paper_root = tmp_path / "paper-project"
    assert cmd_init("paper_iteration", str(paper_root)) == 0
    (paper_root / "review" / "REVIEW_REPORT.md").mkdir(parents=True)

    def fail_if_worker_starts(*_args, **_kwargs):
        raise AssertionError("wrong managed entry type must be rejected before worker start")

    monkeypatch.setattr(
        cluster_run_module,
        "_run_paper_workflow",
        fail_if_worker_starts,
    )

    with _running_dashboard(runtime_dir, paper_root) as base_url:
        status, payload = _request_json(
            base_url,
            "/api/t3/cluster-run",
            payload={
                "projectId": str(paper_root),
                "target": "rdpaper",
                "goal": "Run the local synthetic paper review vertical.",
            },
        )
        _, runs = _request_json(base_url, "/api/t3/cluster-runs")

    assert status == 400
    assert payload["error"] == "cluster_run_rejected"
    assert (
        "managed file slots must be regular files: review/REVIEW_REPORT.md"
        in payload["detail"]
    )
    assert runs["runs"] == []


def test_http_cluster_paper_run_rejects_managed_output_hardlink(tmp_path, monkeypatch):
    runtime_dir = tmp_path / "runtime"
    paper_root = tmp_path / "paper-project"
    outside_task_spec = tmp_path / "outside-taskspec.json"
    assert cmd_init("paper_iteration", str(paper_root)) == 0
    outside_task_spec.write_text("sentinel", encoding="utf-8")
    os.link(outside_task_spec, paper_root / "TASKSPEC.json")

    def fail_if_worker_starts(*_args, **_kwargs):
        raise AssertionError("unsafe managed output must be rejected before worker start")

    monkeypatch.setattr(
        cluster_run_module,
        "_run_paper_workflow",
        fail_if_worker_starts,
    )

    with _running_dashboard(runtime_dir, paper_root) as base_url:
        status, payload = _request_json(
            base_url,
            "/api/t3/cluster-run",
            payload={
                "projectId": str(paper_root),
                "target": "rdpaper",
                "goal": "Run the local synthetic paper review vertical.",
            },
        )
        _, runs = _request_json(base_url, "/api/t3/cluster-runs")

    assert status == 400
    assert payload["error"] == "cluster_run_rejected"
    assert "managed paths must be regular and project-local: TASKSPEC.json" in payload["detail"]
    assert runs["runs"] == []
    assert outside_task_spec.read_text(encoding="utf-8") == "sentinel"


def test_http_cluster_paper_run_serializes_same_resolved_root(tmp_path, monkeypatch):
    runtime_dir = tmp_path / "runtime"
    paper_root = tmp_path / "paper-project"
    assert cmd_init("paper_iteration", str(paper_root)) == 0
    task_spec = paper_root / "TASKSPEC.json"
    sentinel = b'{"owner":"preexisting"}'
    task_spec.write_bytes(sentinel)

    original_workflow = cluster_run_module._run_paper_workflow
    first_worker_entered = Event()
    release_first_worker = Event()
    workflow_call_lock = Lock()
    workflow_calls: list[str] = []

    def controlled_paper_workflow(runtime_path, project_path):
        with workflow_call_lock:
            workflow_calls.append(str(Path(project_path).resolve()))
            call_number = len(workflow_calls)
        if call_number == 1:
            first_worker_entered.set()
            if not release_first_worker.wait(timeout=5):
                raise AssertionError("timed out waiting to release the first paper worker")
        elif not release_first_worker.is_set():
            raise AssertionError("a concurrent paper worker reached shared evidence")
        return original_workflow(runtime_path, project_path)

    monkeypatch.setattr(
        cluster_run_module,
        "_run_paper_workflow",
        controlled_paper_workflow,
    )
    payload = {
        "projectId": str(paper_root),
        "target": "rdpaper",
        "goal": "Run the local synthetic paper review vertical.",
    }
    equivalent_project_path = str(
        paper_root.parent / paper_root.name / ".." / paper_root.name
    )

    with _running_dashboard(runtime_dir, paper_root) as base_url:
        try:
            first_status, first_started = _request_json(
                base_url,
                "/api/t3/cluster-run",
                payload=payload,
            )
            assert first_status == 202
            assert first_worker_entered.wait(timeout=5)

            concurrent_status, concurrent_payload = _request_json(
                base_url,
                "/api/t3/cluster-run",
                payload={**payload, "projectId": equivalent_project_path},
            )
            runs_status, during_run = _request_json(
                base_url,
                "/api/t3/cluster-runs",
            )
            sentinel_during_concurrent_request = task_spec.read_bytes()
            calls_during_concurrent_request = len(workflow_calls)
        finally:
            release_first_worker.set()

        first_record = _wait_for_cluster_run(base_url, first_started["runId"])

        assert concurrent_status == 400
        assert concurrent_payload["error"] == "cluster_run_rejected"
        assert "already has an active paper cluster run" in concurrent_payload["detail"]
        assert runs_status == 200
        assert [item["runId"] for item in during_run["runs"]] == [first_started["runId"]]
        assert sentinel_during_concurrent_request == sentinel
        assert calls_during_concurrent_request == 1
        assert first_record["status"] == "review_pending"

        retry_deadline = time.time() + 5
        while time.time() < retry_deadline:
            retry_status, retry_payload = _request_json(
                base_url,
                "/api/t3/cluster-run",
                payload=payload,
            )
            if retry_status == 202:
                break
            assert retry_status == 400
            assert "already has an active paper cluster run" in retry_payload["detail"]
            time.sleep(0.02)
        else:
            raise AssertionError("paper root reservation was not released")

        retry_record = _wait_for_cluster_run(base_url, retry_payload["runId"])
        _, completed_runs = _request_json(base_url, "/api/t3/cluster-runs")

    assert retry_record["status"] == "review_pending"
    assert len(workflow_calls) == 2
    assert {item["runId"] for item in completed_runs["runs"]} == {
        first_started["runId"],
        retry_payload["runId"],
    }
