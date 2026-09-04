"""Tests for the bounded, read-only graph projection slice builder."""
from __future__ import annotations

import copy

import pytest

from control_plane.graph_projection_slice import (
    GraphSliceError,
    build_graph_slice,
    render_graph_slice_summary,
)


def _payload() -> dict:
    return {
        "graph_projection_id": "graph-1",
        "project_id": "project-1",
        "created_at": "2026-08-28T00:00:00Z",
        "scope": "governance",
        "source_snapshot_refs": [
            "repo://docs/plan.md",
            "D:\\private\\vault\\note.md",
        ],
        "nodes": [
            {
                "id": "decision-1",
                "type": "decision",
                "authority": "human_decided",
                "privacy_class": "public_repo",
                "label": "Release decision",
                "source_ref": "decision://decision-1",
                "source_kind": "governance",
                "freshness": "current",
                "confidence": 1,
                "evidence_refs": ["evidence-1"],
                "unknown_secret": "token=do-not-copy",
            },
            {
                "id": "evidence-1",
                "type": "evidence",
                "authority": "test_verified",
                "privacy_class": "public_repo",
                "label": "Focused tests",
                "source_ref": "artifact://tests-1",
            },
            {
                "id": "artifact-1",
                "type": "artifact",
                "authority": "governance_recorded",
                "privacy_class": "unknown",
                "label": "private internal title",
                "source_ref": "C:\\private\\artifact.json",
                "body": "private transcript must not escape",
            },
            {
                "id": "review-1",
                "type": "review",
                "authority": "external_reviewed",
                "privacy_class": "private_content_summary",
                "label": "external private review",
                "source_ref": "doc://private-review",
            },
            {
                "id": "forbidden-1",
                "type": "artifact",
                "authority": "none",
                "privacy_class": "forbidden",
                "label": "secret artifact",
                "source_ref": "artifact://secret",
            },
        ],
        "edges": [
            {
                "id": "edge-cited-1",
                "source": "decision-1",
                "target": "evidence-1",
                "type": "cited",
                "citation_source": "decision-1",
                "privacy_class": "public_repo",
                "source_ref": "decision://decision-1",
            },
            {
                "id": "edge-inferred-1",
                "source": "evidence-1",
                "target": "artifact-1",
                "type": "inferred",
                "privacy_class": "unknown",
            },
            {
                "id": "edge-annotated-1",
                "source": "artifact-1",
                "target": "review-1",
                "type": "annotated",
                "privacy_class": "private_content_summary",
            },
            {
                "id": "edge-forbidden-neighbor",
                "source": "decision-1",
                "target": "forbidden-1",
                "type": "inferred",
                "privacy_class": "unknown",
            },
            {
                "id": "edge-forbidden-export",
                "source": "decision-1",
                "target": "evidence-1",
                "type": "inferred",
                "privacy_class": "forbidden",
            },
        ],
        "operations": ["project", "query", "seed_context"],
    }


def _nodes(result: dict) -> dict[str, dict]:
    return {node["id"]: node for node in result["nodes"]}


def _edges(result: dict) -> dict[str, dict]:
    return {edge["id"]: edge for edge in result["edges"]}


def test_selected_nodes_and_one_hop_neighbors_are_bounded():
    result = build_graph_slice(_payload(), ["decision-1"])

    assert result["selected_node_ids"] == ["decision-1"]
    assert list(_nodes(result)) == ["decision-1", "evidence-1"]
    assert list(_edges(result)) == ["edge-cited-1"]
    assert result["validation_summary"]["neighbors_included"] == 1
    assert result["omitted_neighbors"] == [
        {"id": "forbidden-1", "reason": "forbidden_privacy"}
    ]


def test_neighbor_expansion_can_be_disabled_with_transparent_omissions():
    result = build_graph_slice(
        _payload(), ["decision-1"], include_neighbors=False
    )

    assert list(_nodes(result)) == ["decision-1"]
    assert result["edges"] == []
    assert result["omitted_neighbors"] == [
        {"id": "evidence-1", "reason": "neighbors_disabled"},
        {"id": "forbidden-1", "reason": "forbidden_privacy"},
    ]
    assert result["omitted_edges"] == [
        {"id": "edge-cited-1", "reason": "endpoint_omitted"},
        {"id": "edge-forbidden-neighbor", "reason": "endpoint_omitted"},
        {"id": "edge-forbidden-export", "reason": "endpoint_omitted"},
    ]


def test_forbidden_selected_node_fails_closed():
    with pytest.raises(GraphSliceError, match="forbidden privacy"):
        build_graph_slice(_payload(), ["forbidden-1"])


def test_unknown_selected_node_fails_closed():
    with pytest.raises(GraphSliceError, match="unknown selected node"):
        build_graph_slice(_payload(), ["missing-1"])


def test_invalid_source_operation_fails_closed():
    payload = _payload()
    payload["operations"] = ["writeback"]

    with pytest.raises(GraphSliceError, match="source projection is invalid"):
        build_graph_slice(payload, ["decision-1"])


def test_oversized_source_is_rejected_before_traversal():
    payload = _payload()
    payload["nodes"] = payload["nodes"] * 1000

    with pytest.raises(GraphSliceError, match="source nodes exceed"):
        build_graph_slice(payload, ["decision-1"])


def test_sensitive_validation_detail_is_not_echoed():
    payload = _payload()
    payload["operations"] = ["token=should-not-echo"]

    with pytest.raises(GraphSliceError) as caught:
        build_graph_slice(payload, ["decision-1"])

    assert "should-not-echo" not in str(caught.value)
    assert "token=" not in str(caught.value)


def test_selected_count_cannot_exceed_node_cap():
    with pytest.raises(GraphSliceError, match="selected nodes exceed"):
        build_graph_slice(
            _payload(), ["decision-1", "evidence-1"], max_nodes=1
        )


def test_neighbor_node_cap_omits_extra_neighbors():
    result = build_graph_slice(
        _payload(), ["evidence-1"], max_nodes=2
    )

    assert list(_nodes(result)) == ["evidence-1", "decision-1"]
    assert {item["reason"] for item in result["omitted_neighbors"]} == {
        "node_limit"
    }
    assert result["validation_summary"]["included_node_count"] == 2


def test_edge_cap_omits_edges_without_mutating_nodes():
    result = build_graph_slice(
        _payload(), ["decision-1", "evidence-1", "artifact-1"],
        include_neighbors=False,
        max_edges=1,
    )

    assert list(_edges(result)) == ["edge-cited-1"]
    assert result["omitted_edges"] == [
        {"id": "edge-inferred-1", "reason": "edge_limit"},
        {"id": "edge-annotated-1", "reason": "endpoint_omitted"},
        {"id": "edge-forbidden-neighbor", "reason": "endpoint_omitted"},
        {"id": "edge-forbidden-export", "reason": "forbidden_privacy"},
    ]


def test_unsafe_fields_and_private_content_are_not_copied():
    result = build_graph_slice(
        _payload(), ["artifact-1"], include_neighbors=False
    )
    node = _nodes(result)["artifact-1"]

    assert "body" not in node
    assert "source_ref" not in node
    assert "label" not in node
    assert "unknown_secret" not in node
    assert result["privacy_summary"]["redacted_field_count"] >= 3


def test_public_fields_are_allowlisted_and_safe_refs_are_retained():
    result = build_graph_slice(_payload(), ["decision-1"])
    node = _nodes(result)["decision-1"]

    assert node["label"] == "Release decision"
    assert node["source_ref"] == "decision://decision-1"
    assert node["evidence_refs"] == ["evidence-1"]
    assert "unknown_secret" not in node
    assert result["source_snapshot_refs"] == ["repo://docs/plan.md"]
    assert result["privacy_summary"]["redacted_field_count"] >= 1


def test_reference_lists_are_bounded_and_redacted_as_a_whole():
    payload = _payload()
    payload["nodes"][0]["evidence_refs"] = [f"evidence-{i}" for i in range(129)]

    result = build_graph_slice(payload, ["decision-1"])

    assert "evidence_refs" not in _nodes(result)["decision-1"]
    assert result["privacy_summary"]["redacted_field_count"] >= 2


def test_input_payload_is_not_mutated():
    payload = _payload()
    before = copy.deepcopy(payload)

    build_graph_slice(payload, ["decision-1"])

    assert payload == before


def test_result_is_deterministic_for_same_input():
    payload = _payload()

    first = build_graph_slice(payload, ["decision-1"])
    second = build_graph_slice(payload, ["decision-1"])

    assert first == second


def test_summary_is_bounded_and_does_not_include_raw_source_data():
    result = build_graph_slice(_payload(), ["decision-1"])
    summary = render_graph_slice_summary(result)

    assert "graph-1" in summary
    assert "nodes: 2" in summary
    assert "forbidden-1" in summary
    assert "private\\vault" not in summary
    assert "token=do-not-copy" not in summary


@pytest.mark.parametrize(
    ("selected", "kwargs", "message"),
    [
        ([], {}, "at least one selected node"),
        (["decision-1", "decision-1"], {}, "duplicate selected node"),
        (["decision-1"], {"include_neighbors": 1}, "include_neighbors"),
        (["decision-1"], {"max_nodes": 0}, "max_nodes"),
        (["decision-1"], {"max_edges": True}, "max_edges"),
    ],
)
def test_invalid_selection_arguments_fail_closed(
    selected: list[str], kwargs: dict, message: str
):
    with pytest.raises(GraphSliceError, match=message):
        build_graph_slice(_payload(), selected, **kwargs)
