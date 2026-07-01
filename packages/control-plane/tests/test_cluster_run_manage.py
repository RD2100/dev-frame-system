"""Tests for cluster-run delete/rename (module + dashboard endpoints)."""
from __future__ import annotations

import json
from threading import Thread
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from control_plane.cluster_run import (
    ClusterRunError,
    _write_run_record,
    delete_cluster_run,
    list_cluster_runs,
    rename_cluster_run,
)
from control_plane.dashboard import build_dashboard_server


def _seed(runtime, run_id="g-test-1", goal="old goal"):
    _write_run_record(
        runtime,
        {"runId": run_id, "target": "coordinator", "goal": goal, "startedAt": "2026-06-29T00:00:00Z"},
    )


def test_delete_removes_record(tmp_path):
    runtime = tmp_path / "runtime"
    _seed(runtime)
    assert len(list_cluster_runs(runtime)) == 1
    assert delete_cluster_run(runtime, "g-test-1") is True
    assert list_cluster_runs(runtime) == []


def test_delete_missing_is_idempotent(tmp_path):
    runtime = tmp_path / "runtime"
    assert delete_cluster_run(runtime, "g-nope") is False


def test_delete_requires_run_id(tmp_path):
    runtime = tmp_path / "runtime"
    with pytest.raises(ClusterRunError):
        delete_cluster_run(runtime, "")


def test_rename_updates_goal(tmp_path):
    runtime = tmp_path / "runtime"
    _seed(runtime, goal="old goal")
    record = rename_cluster_run(runtime, "g-test-1", "新的目标")
    assert record["goal"] == "新的目标"
    runs = list_cluster_runs(runtime)
    assert runs[0]["goal"] == "新的目标"


def test_rename_rejects_empty_goal(tmp_path):
    runtime = tmp_path / "runtime"
    _seed(runtime)
    with pytest.raises(ClusterRunError):
        rename_cluster_run(runtime, "g-test-1", "   ")


def test_rename_missing_run(tmp_path):
    runtime = tmp_path / "runtime"
    with pytest.raises(ClusterRunError):
        rename_cluster_run(runtime, "g-missing", "x")


def _server(tmp_path):
    server = build_dashboard_server(runtime_dir=tmp_path / "runtime", port=0, refresh_seconds=0)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread, f"http://127.0.0.1:{server.server_address[1]}"


def _post(base_url, path, body, origin=None):
    headers = {"Content-Type": "application/json"}
    if origin is not None:
        headers["Origin"] = origin
    request = Request(f"{base_url}{path}", data=json.dumps(body).encode("utf-8"), headers=headers, method="POST")
    with urlopen(request, timeout=5) as response:
        return response.status, json.loads(response.read().decode("utf-8"))


def test_dashboard_delete_and_rename_round_trip(tmp_path):
    _seed(tmp_path / "runtime", run_id="g-abc", goal="old")
    server, thread, base_url = _server(tmp_path)
    try:
        status, resp = _post(base_url, "/api/t3/cluster-run-rename", {"runId": "g-abc", "goal": "renamed"})
        assert status == 200 and resp["goal"] == "renamed"
        status, resp = _post(base_url, "/api/t3/cluster-run-delete", {"runId": "g-abc"})
        assert status == 200 and resp["deleted"] is True
        assert list_cluster_runs(tmp_path / "runtime") == []
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_dashboard_rename_rejects_disallowed_origin(tmp_path):
    _seed(tmp_path / "runtime", run_id="g-abc")
    server, thread, base_url = _server(tmp_path)
    try:
        try:
            _post(base_url, "/api/t3/cluster-run-rename", {"runId": "g-abc", "goal": "x"}, origin="http://evil.example.com")
        except HTTPError as error:
            assert error.code == 403
        else:
            raise AssertionError("expected 403")
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_dashboard_delete_bad_request(tmp_path):
    server, thread, base_url = _server(tmp_path)
    try:
        try:
            _post(base_url, "/api/t3/cluster-run-delete", {"runId": ""})
        except HTTPError as error:
            assert error.code == 400
        else:
            raise AssertionError("expected 400")
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
