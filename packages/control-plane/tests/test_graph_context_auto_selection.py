"""Tests for deterministic graph-context selection proposals."""
from __future__ import annotations

import copy

import pytest

from control_plane.graph_context_auto_selection import (
    GraphContextSelectionError,
    propose_graph_context_selection,
)


def _slice() -> dict:
    return {
        "graph_projection_id": "graph-auto-1",
        "project_id": "project-auto-1",
        "selected_node_ids": ["decision-anchor"],
        "source_snapshot_refs": ["repo://docs/plan.md"],
        "nodes": _nodes(),
        "edges": [],
        "omitted_neighbors": [],
        "omitted_edges": [],
        "privacy_summary": {"redacted_field_count": 0},
        "validation_summary": {"source_valid": True, "bounded": True},
    }


def _nodes() -> list[dict]:
    return [
        {
            "id": "decision-anchor",
            "type": "decision",
            "authority": "human_decided",
            "privacy_class": "public_repo",
            "label": "stream cancellation policy",
            "source_ref": "decision://stream-cancel",
            "freshness": "current",
        },
        {
            "id": "evidence-stream",
            "type": "evidence",
            "authority": "test_verified",
            "privacy_class": "public_repo",
            "label": "stream cancellation regression",
            "source_ref": "evidence://stream-cancel",
            "freshness": "current",
            "confidence": 0.9,
        },
        {
            "id": "artifact-old",
            "type": "artifact",
            "authority": "none",
            "privacy_class": "public_repo",
            "label": "stream cancellation archive",
            "source_ref": "artifact://old-stream",
            "freshness": "stale",
            "confidence": 1.0,
        },
        {
            "id": "artifact-unrelated",
            "type": "artifact",
            "authority": "human_decided",
            "privacy_class": "public_repo",
            "label": "release checklist",
            "source_ref": "artifact://release",
            "freshness": "current",
        },
    ]


def _propose(payload: dict, **kwargs: object) -> dict:
    defaults = {
        "task": "investigate stream cancellation regression",
        "reader": "reviewer",
        "decision_needed": "choose safe context",
    }
    defaults.update(kwargs)
    return propose_graph_context_selection(payload, **defaults)


def test_task_relevance_adds_current_matching_node_after_anchor():
    result = _propose(_slice())

    assert result["selected_node_ids"] == ["decision-anchor", "evidence-stream"]
    assert result["candidate_roles"]["evidence-stream"] == "selected"
    assert result["authority_boundary"]["can_execute"] is False
    assert "Deterministic proposal" in result["selection_rationale"]


def test_stale_match_loses_to_current_match_and_unrelated_is_not_required():
    result = _propose(_slice(), max_required_candidates=3)

    assert result["selected_node_ids"][:2] == ["decision-anchor", "evidence-stream"]
    assert "artifact-old" not in result["selected_node_ids"]
    assert "artifact-unrelated" not in result["selected_node_ids"]


def test_explicit_anchor_is_preserved_when_no_safe_label_matches():
    payload = _slice()
    payload["selected_node_ids"] = ["decision-anchor"]
    for node in payload["nodes"]:
        if node["id"] != "decision-anchor":
            node["label"] = "unrelated"

    result = _propose(payload, task="zzzz qqqq")

    assert result["selected_node_ids"] == ["decision-anchor"]


def test_result_is_deterministic_and_input_is_unchanged():
    payload = _slice()
    before = copy.deepcopy(payload)

    first = _propose(payload)
    second = _propose(payload)

    assert first == second
    assert payload == before


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"task": "token=secret"}, "safe text"),
        ({"max_required_candidates": 0}, "max_required_candidates"),
        ({"max_required_candidates": 17}, "max_required_candidates"),
        ({"max_candidates": 0}, "max_candidates"),
    ],
)
def test_unsafe_or_unbounded_arguments_fail_closed(
    kwargs: dict[str, object], message: str
):
    with pytest.raises(GraphContextSelectionError, match=message):
        _propose(_slice(), **kwargs)


def test_anchor_limit_is_checked_before_proposal():
    payload = _slice()
    payload["selected_node_ids"] = ["decision-anchor", "evidence-stream"]

    with pytest.raises(GraphContextSelectionError, match="anchors exceed"):
        _propose(payload, max_required_candidates=1)


def test_malformed_slice_delegates_to_existing_selection_contract():
    payload = _slice()
    del payload["validation_summary"]

    with pytest.raises(GraphContextSelectionError, match="validation_summary"):
        _propose(payload)


def test_proposal_is_compatible_with_existing_packet_canonicalizer():
    from control_plane.graph_context_packet_integration import (
        canonicalize_graph_context_selection,
    )

    result = _propose(_slice())
    canonical = canonicalize_graph_context_selection(result, project_id="project-auto-1")

    assert canonical["selected_node_ids"] == ["decision-anchor", "evidence-stream"]
    assert "selection_rationale" not in canonical


def test_private_label_is_not_used_or_propagated():
    payload = _slice()
    payload["nodes"][1]["label"] = "private secret token"

    result = _propose(payload, task="confidential context")

    assert result["selected_node_ids"] == ["decision-anchor"]
    assert "private secret token" not in str(result)


def test_non_finite_confidence_is_ignored_without_affecting_safety():
    payload = _slice()
    payload["nodes"][1]["confidence"] = float("nan")

    result = _propose(payload)

    assert result["selected_node_ids"] == ["decision-anchor", "evidence-stream"]
