"""Tests for graph-derived context candidates and omission records."""
from __future__ import annotations

import copy
import json

import pytest

from control_plane.graph_context_selection import (
    GraphContextSelectionError,
    build_graph_context_selection,
)


def _slice() -> dict:
    return {
        "graph_projection_id": "graph-1",
        "project_id": "project-1",
        "selected_node_ids": ["decision-1"],
        "source_snapshot_refs": ["repo://docs/plan.md"],
        "nodes": [
            {
                "id": "decision-1",
                "type": "decision",
                "authority": "human_decided",
                "privacy_class": "public_repo",
                "label": "must not be copied",
                "source_ref": "decision://decision-1",
                "freshness": "current",
            },
            {
                "id": "evidence-1",
                "type": "evidence",
                "authority": "test_verified",
                "privacy_class": "public_repo",
                "source_ref": "artifact://tests-1",
                "freshness": "stale",
            },
        ],
        "edges": [
            {
                "id": "edge-cited-1",
                "source": "decision-1",
                "target": "evidence-1",
                "type": "cited",
                "citation_source": "decision-1",
            },
            {
                "id": "edge-inferred-1",
                "source": "decision-1",
                "target": "evidence-1",
                "type": "inferred",
                "private_claim": "never copy",
            },
            {
                "id": "edge-annotated-1",
                "source": "decision-1",
                "target": "evidence-1",
                "type": "annotated",
            },
        ],
        "omitted_neighbors": [
            {"id": "review-1", "reason": "forbidden_privacy"},
            {"id": "neighbor-2", "reason": "node_limit"},
        ],
        "omitted_edges": [
            {"id": "edge-omitted-1", "reason": "endpoint_omitted"}
        ],
        "privacy_summary": {"redacted_field_count": 2},
        "validation_summary": {"source_valid": True, "bounded": True},
    }


def _refs(result: dict) -> dict[str, dict]:
    return {ref["ref_id"]: ref for ref in result["source_refs"]}


def test_selected_and_neighbor_nodes_become_cited_context_candidates():
    result = build_graph_context_selection(
        _slice(),
        reader="reviewer",
        decision_needed="choose safe graph context",
    )
    refs = _refs(result)

    assert result["project_id"] == "project-1"
    assert refs["graph-slice-graph-1"]["uri"] == "graph://projection/graph-1"
    assert refs["graph-node-decision-1"]["required"] is True
    assert refs["graph-node-decision-1"]["uri"] == "decision://decision-1"
    assert refs["graph-node-evidence-1"]["required"] is False
    assert refs["graph-node-evidence-1"]["freshness_state"] == "stale"
    assert result["candidate_roles"] == {
        "decision-1": "selected",
        "evidence-1": "neighbor",
    }
    assert result["completeness_state"] == "incomplete"
    assert result["privacy_state"] == "redacted"
    serialized = json.dumps(result, ensure_ascii=True)
    assert "must not be copied" not in serialized
    assert "private_claim" not in serialized


def test_omitted_neighbors_are_visible_with_impact_and_forbidden_refs():
    result = build_graph_context_selection(
        _slice(), reader="reviewer", decision_needed="review"
    )

    assert result["omitted_required_refs"] == [
        {
            "ref": "graph-node-review-1",
            "omission_reason": "forbidden_privacy",
            "impact": "human_required",
        },
        {
            "ref": "graph-node-neighbor-2",
            "omission_reason": "node_limit",
            "impact": "limited",
        },
    ]
    assert result["forbidden_refs"] == [
        {
            "ref": "graph-node-review-1",
            "reason": "forbidden_privacy",
        }
    ]
    assert result["omitted_context"] == [
        {
            "ref": "graph-edge-edge-omitted-1",
            "omission_reason": "endpoint_omitted",
            "impact": "limited",
        }
    ]
    assert result["candidate_source_summary"]["omitted_neighbor_count"] == 2


def test_inferred_and_annotated_edges_are_assumptions_not_authority():
    result = build_graph_context_selection(
        _slice(), reader="reviewer", decision_needed="review"
    )

    assert result["assumption_claims"] == [
        {
            "edge_id": "edge-inferred-1",
            "source": "decision-1",
            "target": "evidence-1",
            "kind": "inferred",
            "authority": "assumption",
        },
        {
            "edge_id": "edge-annotated-1",
            "source": "decision-1",
            "target": "evidence-1",
            "kind": "annotated",
            "authority": "assumption",
        },
    ]
    assert all(
        claim["authority"] != "source_truth"
        for claim in result["assumption_claims"]
    )


def test_private_source_fields_are_never_copied():
    payload = _slice()
    payload["nodes"][1]["body"] = "private body"
    payload["nodes"][1]["source_ref"] = "C:\\private\\evidence.md"

    with pytest.raises(GraphContextSelectionError, match="unsafe source_ref"):
        build_graph_context_selection(
            payload, reader="reviewer", decision_needed="review"
        )


def test_malformed_slice_fails_closed():
    payload = _slice()
    del payload["validation_summary"]

    with pytest.raises(GraphContextSelectionError, match="validation_summary"):
        build_graph_context_selection(
            payload, reader="reviewer", decision_needed="review"
        )


def test_candidate_limit_keeps_selected_nodes_and_records_omission():
    payload = _slice()
    payload["nodes"].append(
        {
            "id": "artifact-2",
            "type": "artifact",
            "authority": "governance_recorded",
            "privacy_class": "public_repo",
            "source_ref": "artifact://artifact-2",
        }
    )
    payload["selected_node_ids"] = ["decision-1"]
    payload["edges"].append(
        {
            "id": "edge-neighbor-2",
            "source": "decision-1",
            "target": "artifact-2",
            "type": "inferred",
        }
    )

    result = build_graph_context_selection(
        payload,
        reader="reviewer",
        decision_needed="review",
        max_candidates=2,
    )

    assert "graph-node-artifact-2" not in _refs(result)
    assert {
        "ref": "graph-node-artifact-2",
        "omission_reason": "candidate_limit",
        "impact": "limited",
    } in result["omitted_required_refs"]


def test_selection_is_deterministic_and_does_not_mutate_input():
    payload = _slice()
    before = copy.deepcopy(payload)

    first = build_graph_context_selection(
        payload, reader="reviewer", decision_needed="review"
    )
    second = build_graph_context_selection(
        payload, reader="reviewer", decision_needed="review"
    )

    assert first == second
    assert payload == before
    assert first["authority_boundary"]["can_claim_final_acceptance"] is False
    assert first["authority_boundary"]["final_verdict_required"] is True


def test_invalid_limits_and_selection_types_fail_closed():
    with pytest.raises(GraphContextSelectionError, match="max_candidates"):
        build_graph_context_selection(
            _slice(),
            reader="reviewer",
            decision_needed="review",
            max_candidates=0,
        )
    with pytest.raises(GraphContextSelectionError, match="reader"):
        build_graph_context_selection(
            _slice(), reader="token=secret", decision_needed="review"
        )
