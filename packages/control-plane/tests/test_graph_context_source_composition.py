"""Tests for bounded composition of validated graph source slices."""
from __future__ import annotations

import copy

import pytest

from control_plane.graph_context_auto_selection import propose_graph_context_selection
from control_plane.graph_context_packet_integration import (
    canonicalize_graph_context_selection,
)
from control_plane.graph_context_selection import build_graph_context_selection
from control_plane.graph_context_source_composition import (
    GraphContextSourceCompositionError,
    compose_graph_context_sources,
)
from control_plane.graph_projection_validator import validate_graph_projection


def _node(node_id: str, *, selected: bool = False, **overrides: object) -> dict:
    node = {
        "id": node_id,
        "type": "artifact",
        "authority": "test_verified",
        "privacy_class": "public_repo",
        "label": f"stream evidence {node_id}",
        "source_kind": "test",
        "source_ref": f"evidence://{node_id}",
        "freshness": "current",
        "confidence": 0.8,
    }
    node.update(overrides)
    return node


def _slice(
    graph_id: str,
    nodes: list[dict],
    *,
    selected: list[str] | None = None,
    edges: list[dict] | None = None,
) -> dict:
    selected_ids = selected or [nodes[0]["id"]]
    return {
        "graph_projection_id": graph_id,
        "project_id": "project-compose-1",
        "selected_node_ids": selected_ids,
        "source_snapshot_refs": [f"repo://{graph_id}"],
        "nodes": nodes,
        "edges": edges or [],
        "omitted_neighbors": [],
        "omitted_edges": [],
        "privacy_summary": {"redacted_field_count": 0},
        "validation_summary": {"source_valid": True, "bounded": True},
    }


def _compose(slices: list[dict], **kwargs: object) -> dict:
    defaults = {
        "project_id": "project-compose-1",
        "graph_projection_id": "graph-composed-1",
    }
    defaults.update(kwargs)
    return compose_graph_context_sources(slices, **defaults)


def test_merges_selected_nodes_and_edges_with_provenance():
    first = _slice("graph-a", [_node("anchor-a"), _node("shared")], selected=["anchor-a"])
    second = _slice(
        "graph-b",
        [_node("anchor-b"), _node("shared")],
        selected=["anchor-b"],
        edges=[
            {
                "id": "edge-shared",
                "source": "anchor-b",
                "target": "shared",
                "type": "inferred",
                "privacy_class": "public_repo",
            }
        ],
    )

    result = _compose([first, second])

    assert result["selected_node_ids"] == ["anchor-a", "anchor-b"]
    assert [node["id"] for node in result["nodes"]] == [
        "anchor-a",
        "anchor-b",
        "shared",
    ]
    assert result["source_snapshot_refs"] == [
        "graph://projection/graph-a",
        "graph://projection/graph-b",
    ]
    assert result["source_provenance"][2] == {
        "node_id": "shared",
        "source_projection_ids": ["graph-a", "graph-b"],
    }
    assert result["validation_summary"]["source_count"] == 2
    assert result["edges"][0]["id"] == "edge-shared"


def test_duplicate_metadata_uses_conservative_resolution_and_records_conflicts():
    first = _slice(
        "graph-a",
        [_node("shared", authority="human_decided", freshness="current")],
    )
    second = _slice(
        "graph-b",
        [
            _node(
                "shared",
                authority="none",
                freshness="stale",
                label="different label",
                confidence=0.2,
            )
        ],
    )

    result = _compose([first, second])
    node = result["nodes"][0]

    assert node["authority"] == "none"
    assert node["freshness"] == "stale"
    assert node["confidence"] == 0.2
    assert "label" not in node
    assert {item["field"] for item in result["source_conflicts"]} >= {
        "authority",
        "freshness",
        "label",
        "confidence",
    }


def test_stale_duplicate_cannot_be_auto_promoted_by_downstream_selector():
    first = _slice("graph-a", [_node("anchor")], selected=["anchor"])
    second = _slice(
        "graph-b",
        [_node("anchor"), _node("evidence", freshness="stale")],
        selected=["anchor"],
    )

    result = _compose([first, second])
    proposal = propose_graph_context_selection(
        result,
        task="stream evidence",
        reader="reviewer",
        decision_needed="choose context",
    )

    assert proposal["selected_node_ids"] == ["anchor"]
    assert "graph-node-evidence" in proposal["freshness"]["stale_refs"]


def test_input_is_unchanged_and_output_is_compatible_with_consumers():
    source = _slice("graph-a", [_node("anchor"), _node("neighbor")])
    before = copy.deepcopy(source)

    result = _compose([source])
    manifest = build_graph_context_selection(
        result, reader="reviewer", decision_needed="review"
    )
    canonical = canonicalize_graph_context_selection(
        manifest, project_id="project-compose-1"
    )
    validation = validate_graph_projection(result)

    assert source == before
    assert validation.valid is True
    assert canonical["project_id"] == "project-compose-1"
    assert canonical["selected_node_ids"] == ["anchor"]


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"max_sources": 0}, "max_sources"),
        ({"max_nodes": 0}, "max_nodes"),
        ({"max_edges": 0}, "max_edges"),
        ({"project_id": "other"}, "project does not match"),
    ],
)
def test_bounds_and_scope_fail_closed(kwargs: dict[str, object], message: str):
    with pytest.raises(GraphContextSourceCompositionError, match=message):
        _compose([_slice("graph-a", [_node("anchor")])], **kwargs)


def test_empty_and_too_many_sources_fail_closed():
    with pytest.raises(GraphContextSourceCompositionError, match="at least one"):
        _compose([])
    source = _slice("graph-a", [_node("anchor")])
    with pytest.raises(GraphContextSourceCompositionError, match="max_sources"):
        _compose([source] * 2, max_sources=1)


def test_node_bound_preserves_anchors_and_records_dropped_neighbors():
    source = _slice(
        "graph-a",
        [_node("anchor"), _node("neighbor-a"), _node("neighbor-b")],
        selected=["anchor"],
    )

    result = _compose([source], max_nodes=2)

    assert [node["id"] for node in result["nodes"]] == ["anchor", "neighbor-a"]
    assert {item["id"] for item in result["omitted_neighbors"]} == {"neighbor-b"}


def test_edge_bound_and_dropped_endpoint_are_visible():
    edges = [
        {
            "id": f"edge-{index}",
            "source": "anchor",
            "target": f"neighbor-{index}",
            "type": "inferred",
            "privacy_class": "public_repo",
        }
        for index in range(3)
    ]
    source = _slice(
        "graph-a",
        [_node("anchor"), *[_node(f"neighbor-{index}") for index in range(3)]],
        edges=edges,
    )

    result = _compose([source], max_nodes=2, max_edges=1)
    omissions = {(item["id"], item["reason"]) for item in result["omitted_edges"]}

    assert len(result["edges"]) == 1
    assert ("edge-1", "endpoint_omitted") in omissions
    assert ("edge-2", "endpoint_omitted") in omissions


def test_conflicting_identity_fails_closed():
    first = _slice("graph-a", [_node("shared", type="artifact")])
    second = _slice("graph-b", [_node("shared", type="review")])

    with pytest.raises(GraphContextSourceCompositionError, match="node type"):
        _compose([first, second])


def test_conflicting_edge_identity_fails_closed():
    edge_a = {
        "id": "edge-same",
        "source": "anchor",
        "target": "target-a",
        "type": "inferred",
        "privacy_class": "public_repo",
    }
    edge_b = {**edge_a, "target": "target-b"}
    first = _slice("graph-a", [_node("anchor"), _node("target-a")], edges=[edge_a])
    second = _slice("graph-b", [_node("anchor"), _node("target-b")], edges=[edge_b])

    with pytest.raises(GraphContextSourceCompositionError, match="edge identity"):
        _compose([first, second])


def test_private_and_sensitive_fields_are_not_propagated():
    private_node = _node(
        "private",
        privacy_class="private_content_summary",
        label="private secret token",
    )
    private_node.pop("source_ref")
    source = _slice(
        "graph-a",
        [private_node],
    )

    result = _compose([source])

    assert "label" not in result["nodes"][0]
    assert "source_ref" not in result["nodes"][0]
    assert "private secret token" not in str(result)


def test_unsafe_optional_fields_are_redacted_without_leaking_values():
    source = _slice(
        "graph-a",
        [_node("anchor", label=r"C:\\private\\secret.md")],
    )

    result = _compose([source])

    assert "label" not in result["nodes"][0]
    assert result["privacy_summary"]["redacted_field_count"] >= 1
    assert r"C:\\private\\secret.md" not in str(result)


def test_duplicate_source_snapshot_ids_are_stable_and_deduplicated_by_identity():
    source = _slice("graph-a", [_node("anchor")])
    first = _compose([source, source])
    second = _compose([source, source])

    assert first == second
    assert first["source_snapshot_refs"] == [
        "graph://projection/graph-a",
    ]
