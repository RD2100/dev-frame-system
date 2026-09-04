"""Tests for the bounded CodeGraph snapshot source adapter."""
from __future__ import annotations

import copy
import json

import pytest

from control_plane.codegraph_snapshot_source import (
    CodeGraphSnapshotError,
    build_codegraph_snapshot_projection,
)
from control_plane.graph_context_selection import build_graph_context_selection
from control_plane.graph_projection_slice import build_graph_slice
from control_plane.graph_projection_validator import validate_graph_projection


def _snapshot(*, freshness: str = "current") -> dict:
    return {
        "project_id": "project-1",
        "resource_id": "codegraph-project-1",
        "index_name": "project-1-codegraph",
        "index_status": "current",
        "index_freshness": freshness,
        "trusted_for_current_run": False,
        "nodes": [
            {
                "id": "file-main",
                "kind": "file",
                "label": "main.py",
                "source_ref": "code://src/main.py",
                "privacy_class": "public_repo",
                "confidence": 1.0,
            },
            {
                "id": "function-main",
                "kind": "function",
                "label": "main",
                "source_ref": "code://src/main.py#main",
                "privacy_class": "public_repo",
                "confidence": 0.9,
            },
            {
                "id": "private-helper",
                "kind": "function",
                "label": "private helper",
                "source_ref": "code://src/private.py#helper",
                "privacy_class": "local_path_only",
            },
        ],
        "relations": [
            {
                "id": "contains-main",
                "source": "file-main",
                "target": "function-main",
                "kind": "contains",
                "confidence": 0.95,
            },
            {
                "id": "calls-helper",
                "source": "function-main",
                "target": "private-helper",
                "kind": "calls",
                "confidence": 0.7,
            },
        ],
    }


def _build(snapshot: dict | None = None) -> dict:
    return build_codegraph_snapshot_projection(
        snapshot or _snapshot(),
        graph_projection_id="graph-codegraph-1",
        project_id="project-1",
        source_snapshot_refs=["repo://codegraph/status"],
    )


def test_snapshot_maps_files_symbols_and_inferred_relations():
    projection = _build()

    assert validate_graph_projection(projection).valid
    assert [node["id"] for node in projection["nodes"]] == [
        "file-main",
        "function-main",
        "private-helper",
    ]
    assert {node["type"] for node in projection["nodes"]} == {"artifact"}
    assert {node["authority"] for node in projection["nodes"]} == {"none"}
    assert projection["source_adapter"]["index_status"] == "current"
    assert projection["source_adapter"]["read_only"] is True
    relation_kinds = {edge["relation_kind"] for edge in projection["edges"]}
    assert relation_kinds == {"calls", "contains"}
    assert {edge["type"] for edge in projection["edges"]} == {"inferred"}


def test_private_nodes_and_relations_are_content_free():
    projection = _build()
    serialized = json.dumps(projection, ensure_ascii=True)

    assert "private.py" not in serialized
    assert "private-helper" in serialized
    private = next(node for node in projection["nodes"] if node["id"] == "private-helper")
    assert set(private) == {
        "id",
        "type",
        "authority",
        "privacy_class",
        "freshness",
        "confidence",
    }


def test_stale_snapshot_never_reports_current_freshness_or_authority():
    projection = _build(_snapshot(freshness="stale"))

    assert {node["freshness"] for node in projection["nodes"]} == {"stale"}
    assert {node["authority"] for node in projection["nodes"]} == {"none"}
    assert projection["source_adapter"]["index_freshness"] == "stale"


def test_existing_slice_and_selection_consume_codegraph_projection():
    graph_slice = build_graph_slice(_build(), ["function-main"])
    selection = build_graph_context_selection(
        graph_slice,
        reader="reviewer",
        decision_needed="inspect code relationships",
    )

    assert selection["project_id"] == "project-1"
    assert selection["selected_node_ids"] == ["function-main"]
    assert selection["authority_boundary"]["can_execute"] is False


def test_input_is_immutable_and_output_is_deterministic():
    snapshot = _snapshot()
    before = copy.deepcopy(snapshot)

    first = _build(snapshot)
    second = _build(snapshot)

    assert snapshot == before
    assert first == second


@pytest.mark.parametrize(
    ("mutator", "message"),
    [
        (lambda value: value.update({"unknown": True}), "unsupported fields"),
        (lambda value: value.update({"trusted_for_current_run": True}), "trusted"),
        (
            lambda value: value["nodes"][0].update({"source_ref": r"D:\\src\\main.py"}),
            "unsafe",
        ),
        (
            lambda value: value["relations"][0].update({"kind": "source_truth"}),
            "relation kind",
        ),
        (
            lambda value: value["relations"][0].update({"target": "missing-node"}),
            "endpoint",
        ),
    ],
)
def test_unsafe_or_malformed_snapshot_fails_closed(mutator, message: str):
    snapshot = _snapshot()
    mutator(snapshot)

    with pytest.raises(CodeGraphSnapshotError, match=message):
        _build(snapshot)


def test_cross_project_and_missing_snapshot_identity_fail_closed():
    snapshot = _snapshot()
    snapshot["project_id"] = "project-2"
    with pytest.raises(CodeGraphSnapshotError, match="project"):
        _build(snapshot)

    snapshot = _snapshot()
    snapshot.pop("resource_id")
    with pytest.raises(CodeGraphSnapshotError, match="resource_id"):
        _build(snapshot)


def test_invalid_freshness_status_and_empty_nodes_fail_closed():
    snapshot = _snapshot(freshness="invalid")
    with pytest.raises(CodeGraphSnapshotError, match="freshness"):
        _build(snapshot)

    snapshot = _snapshot()
    snapshot["nodes"] = []
    with pytest.raises(CodeGraphSnapshotError, match="nodes"):
        _build(snapshot)


@pytest.mark.parametrize("reference", ["repo://D:/private/index.db", "code://src/../secret.py"])
def test_path_like_snapshot_references_fail_closed(reference: str):
    with pytest.raises(CodeGraphSnapshotError, match="reference"):
        build_codegraph_snapshot_projection(
            _snapshot(),
            graph_projection_id="graph-codegraph-1",
            project_id="project-1",
            source_snapshot_refs=[reference],
        )


@pytest.mark.parametrize(
    ("field", "limit"),
    [("nodes", 512), ("relations", 1024)],
)
def test_hard_snapshot_limits_are_enforced(field: str, limit: int):
    snapshot = _snapshot()
    if field == "nodes":
        snapshot["nodes"] = [
            {
                "id": f"node-{index}",
                "kind": "file",
                "label": f"file-{index}.py",
                "source_ref": f"code://src/file-{index}.py",
                "privacy_class": "public_repo",
            }
            for index in range(limit + 1)
        ]
    else:
        snapshot["relations"] = [
            {
                "id": f"relation-{index}",
                "source": "file-main",
                "target": "file-main",
                "kind": "calls",
            }
            for index in range(limit + 1)
        ]

    with pytest.raises(CodeGraphSnapshotError, match="hard limit"):
        _build(snapshot)
