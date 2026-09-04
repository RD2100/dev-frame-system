"""Tests for explicit CodeGraph freshness-to-context composition."""
from __future__ import annotations

import copy

import pytest

import control_plane.codegraph_fresh_context as fresh
from control_plane.codegraph_fresh_context import (
    CodeGraphFreshContextError,
    query_codegraph_context_with_status,
)
from control_plane.codegraph_status_transport import CodeGraphStatusTransportError


def _status(**overrides):
    result = {
        "project_id": "project-1",
        "resource_id": "codegraph-project-1",
        "index_name": "project-1-codegraph",
        "index_status": "stale",
        "index_freshness": "stale",
        "trusted_for_current_run": False,
        "pending_changes": {"added": 2, "modified": 1, "removed": 0},
    }
    result.update(overrides)
    return result


def _projection():
    return {
        "graph_projection_id": "graph-1",
        "project_id": "project-1",
        "nodes": [],
        "edges": [],
        "source_adapter": {"transport": "codegraph_json_context"},
    }


def test_status_is_read_before_context_and_freshness_is_forwarded(monkeypatch, tmp_path):
    events: list[tuple[str, dict]] = []

    def fake_status(**kwargs):
        events.append(("status", kwargs))
        return _status()

    def fake_context(**kwargs):
        events.append(("context", kwargs))
        return _projection()

    monkeypatch.setattr(fresh, "query_codegraph_status", fake_status)
    monkeypatch.setattr(fresh, "query_codegraph_context", fake_context)
    result = query_codegraph_context_with_status(
        project_root=tmp_path,
        task="inspect graph",
        graph_projection_id="graph-1",
        project_id="project-1",
        resource_id="codegraph-project-1",
        index_name="project-1-codegraph",
    )

    assert [event[0] for event in events] == ["status", "context"]
    assert events[1][1]["index_status"] == "stale"
    assert events[1][1]["index_freshness"] == "stale"
    assert result["source_adapter"]["freshness_attestation"] == {
        "transport": "codegraph_status_json",
        "index_status": "stale",
        "index_freshness": "stale",
        "pending_changes": {"added": 2, "modified": 1, "removed": 0},
        "trusted_for_current_run": False,
    }


def test_optional_executable_is_forwarded_to_both_transports(monkeypatch, tmp_path):
    calls: list[tuple[str, str]] = []

    def fake_status(**kwargs):
        calls.append(("status", kwargs["executable"]))
        return _status()

    def fake_context(**kwargs):
        calls.append(("context", kwargs["executable"]))
        return _projection()

    monkeypatch.setattr(fresh, "query_codegraph_status", fake_status)
    monkeypatch.setattr(fresh, "query_codegraph_context", fake_context)
    query_codegraph_context_with_status(
        project_root=tmp_path,
        task="inspect",
        graph_projection_id="graph-1",
        project_id="project-1",
        resource_id="codegraph-project-1",
        index_name="project-1-codegraph",
        executable="codegraph.cmd",
    )

    assert calls == [("status", "codegraph.cmd"), ("context", "codegraph.cmd")]


def test_status_failure_prevents_context_subprocess(monkeypatch, tmp_path):
    called = False

    def fail_status(**_kwargs):
        raise CodeGraphStatusTransportError("timeout", "timed out")

    def unexpected_context(**_kwargs):
        nonlocal called
        called = True
        return _projection()

    monkeypatch.setattr(fresh, "query_codegraph_status", fail_status)
    monkeypatch.setattr(fresh, "query_codegraph_context", unexpected_context)
    with pytest.raises(CodeGraphStatusTransportError) as raised:
        query_codegraph_context_with_status(
            project_root=tmp_path,
            task="inspect",
            graph_projection_id="graph-1",
            project_id="project-1",
            resource_id="codegraph-project-1",
            index_name="project-1-codegraph",
        )
    assert raised.value.code == "timeout"
    assert called is False


@pytest.mark.parametrize(
    "overrides",
    [
        {"project_id": "other"},
        {"resource_id": "other"},
        {"index_name": "other"},
        {"index_status": "bad"},
        {"index_freshness": "bad"},
        {"trusted_for_current_run": True},
        {"pending_changes": {"added": 1}},
    ],
)
def test_invalid_attestation_fails_before_context(monkeypatch, tmp_path, overrides):
    called = False

    monkeypatch.setattr(fresh, "query_codegraph_status", lambda **_kwargs: _status(**overrides))

    def unexpected_context(**_kwargs):
        nonlocal called
        called = True
        return _projection()

    monkeypatch.setattr(fresh, "query_codegraph_context", unexpected_context)
    with pytest.raises(CodeGraphFreshContextError):
        query_codegraph_context_with_status(
            project_root=tmp_path,
            task="inspect",
            graph_projection_id="graph-1",
            project_id="project-1",
            resource_id="codegraph-project-1",
            index_name="project-1-codegraph",
        )
    assert called is False


def test_attestation_is_copied_without_mutating_status_or_projection(monkeypatch, tmp_path):
    status = _status()
    projection = _projection()
    before_status = copy.deepcopy(status)
    before_projection = copy.deepcopy(projection)
    monkeypatch.setattr(fresh, "query_codegraph_status", lambda **_kwargs: status)
    monkeypatch.setattr(fresh, "query_codegraph_context", lambda **_kwargs: projection)

    result = query_codegraph_context_with_status(
        project_root=tmp_path,
        task="inspect",
        graph_projection_id="graph-1",
        project_id="project-1",
        resource_id="codegraph-project-1",
        index_name="project-1-codegraph",
    )

    assert status == before_status
    assert projection == before_projection
    assert result is not projection
