"""Tests for the explicit domain-index graph source adapter."""
from __future__ import annotations

import copy
import json

import pytest

from control_plane.graph_context_selection import build_graph_context_selection
from control_plane.graph_projection_slice import build_graph_slice
from control_plane.graph_projection_validator import validate_graph_projection
from control_plane.indexed_graph_source import (
    IndexedGraphSourceError,
    build_indexed_graph_projection,
)


def _records() -> list[dict]:
    return [
        {
            "id": "project-node",
            "project_id": "project-1",
            "kind": "project",
            "authority": "governance_recorded",
            "privacy_class": "public_repo",
            "label": "Project map",
            "source_ref": "project://project-1",
        },
        {
            "id": "code-node",
            "project_id": "project-1",
            "kind": "code",
            "authority": "cited_source",
            "privacy_class": "public_repo",
            "label": "Graph adapter",
            "source_ref": "code://packages/control-plane/control_plane/indexed_graph_source.py",
            "evidence_refs": ["evidence-1"],
        },
        {
            "id": "doc-node",
            "project_id": "project-1",
            "kind": "document",
            "authority": "cited_source",
            "privacy_class": "public_repo",
            "label": "Graph plan",
            "source_ref": "doc://status/graph-projection-knowledge-canvas-plan.md",
        },
        {
            "id": "paper-node",
            "project_id": "project-1",
            "kind": "paper",
            "authority": "external_reviewed",
            "privacy_class": "public_repo",
            "label": "Paper source",
            "source_ref": "paper://doi/10.1000/example",
        },
        {
            "id": "decision-node",
            "project_id": "project-1",
            "kind": "decision",
            "authority": "human_decided",
            "privacy_class": "public_repo",
            "label": "Accepted boundary",
            "source_ref": "decision://decision-node",
        },
        {
            "id": "evidence-node",
            "project_id": "project-1",
            "kind": "evidence",
            "authority": "test_verified",
            "privacy_class": "public_repo",
            "label": "Focused tests",
            "source_ref": "evidence://evidence-node",
        },
        {
            "id": "review-node",
            "project_id": "project-1",
            "kind": "review",
            "authority": "external_reviewed",
            "privacy_class": "public_repo",
            "label": "Independent review",
            "source_ref": "review://review-node",
        },
        {
            "id": "seed-node",
            "project_id": "project-1",
            "kind": "context_seed",
            "authority": "external_reviewed",
            "privacy_class": "public_repo",
            "label": "Bounded context",
            "source_ref": "artifact://seed-node",
        },
        {
            "id": "private-node",
            "project_id": "project-1",
            "kind": "code",
            "authority": "cited_source",
            "privacy_class": "local_path_only",
            "label": r"D:\private\secret.py",
            "source_ref": r"D:\private\secret.py",
        },
        {
            "id": "foreign-node",
            "project_id": "project-2",
            "kind": "document",
            "authority": "cited_source",
            "privacy_class": "public_repo",
            "label": "foreign project",
            "source_ref": "doc://foreign/project.md",
        },
    ]


def _relations() -> list[dict]:
    return [
        {
            "id": "edge-decision-seed",
            "project_id": "project-1",
            "source": "decision-node",
            "target": "seed-node",
            "type": "cited",
            "citation_source": "decision://decision-node",
            "privacy_class": "public_repo",
            "authority": "governed_decision",
        },
        {
            "id": "edge-code-doc",
            "project_id": "project-1",
            "source": "code-node",
            "target": "doc-node",
            "type": "inferred",
            "privacy_class": "public_repo",
            "confidence": 0.4,
        },
        {
            "id": "edge-doc-paper",
            "project_id": "project-1",
            "source": "doc-node",
            "target": "paper-node",
            "type": "annotated",
            "privacy_class": "public_repo",
        },
        {
            "id": "edge-foreign",
            "project_id": "project-2",
            "source": "foreign-node",
            "target": "foreign-node",
            "type": "inferred",
            "privacy_class": "public_repo",
        },
    ]


def _build() -> dict:
    return build_indexed_graph_projection(
        _records(),
        _relations(),
        graph_projection_id="graph-indexed-1",
        project_id="project-1",
        source_snapshot_refs=["repo://PLAN.md"],
    )


def test_supported_domain_kinds_map_to_existing_graph_contract():
    projection = _build()

    assert validate_graph_projection(projection).valid
    assert [node["id"] for node in projection["nodes"]] == sorted(
        node["id"] for node in projection["nodes"]
    )
    assert {node["type"] for node in projection["nodes"]} == {
        "artifact",
        "decision",
        "evidence",
        "review",
        "context_seed",
    }
    assert len(projection["edges"]) == 3
    cited = next(edge for edge in projection["edges"] if edge["type"] == "cited")
    assert cited["citation_source"] == "decision://decision-node"


def test_existing_slice_and_selection_can_consume_indexed_projection():
    graph_slice = build_graph_slice(_build(), ["seed-node"])
    selection = build_graph_context_selection(
        graph_slice,
        reader="reviewer",
        decision_needed="inspect indexed evidence",
    )

    assert selection["project_id"] == "project-1"
    assert selection["selected_node_ids"] == ["seed-node"]
    assert selection["authority_boundary"]["can_execute"] is False


def test_private_records_are_content_free_and_foreign_project_is_omitted():
    projection = _build()
    serialized = json.dumps(projection, ensure_ascii=True)

    assert "private-node" in serialized
    assert "D:\\private" not in serialized
    assert "secret.py" not in serialized
    assert "foreign-node" not in serialized
    assert "foreign project" not in serialized

    private = next(node for node in projection["nodes"] if node["id"] == "private-node")
    assert set(private) == {
        "id",
        "type",
        "authority",
        "privacy_class",
        "freshness",
        "confidence",
    }


def test_input_is_immutable_and_output_is_deterministic():
    records = _records()
    relations = _relations()
    before_records = copy.deepcopy(records)
    before_relations = copy.deepcopy(relations)

    first = build_indexed_graph_projection(
        records,
        relations,
        graph_projection_id="graph-indexed-1",
        project_id="project-1",
    )
    second = build_indexed_graph_projection(
        records,
        relations,
        graph_projection_id="graph-indexed-1",
        project_id="project-1",
    )

    assert records == before_records
    assert relations == before_relations
    assert first == second


@pytest.mark.parametrize(
    ("mutator", "message"),
    [
        (
            lambda records, relations: records[0].update({"unknown": "x"}),
            "unsupported fields",
        ),
        (
            lambda records, relations: records.append({
                "id": "bad-node",
                "project_id": "project-1",
                "kind": "unknown",
                "authority": "none",
            }),
            "kind",
        ),
        (
            lambda records, relations: relations[0].update({"target": "missing-node"}),
            "endpoint",
        ),
        (
            lambda records, relations: relations[1].update({"is_source_truth": True}),
            "source truth",
        ),
        (
            lambda records, relations: relations[1].update({"is_source_truth": "yes"}),
            "boolean",
        ),
        (
            lambda records, relations: relations[2].update({"promoted_to_decision": True}),
            "decision",
        ),
    ],
)
def test_unsafe_or_malformed_input_fails_closed(mutator, message: str):
    records = _records()
    relations = _relations()
    mutator(records, relations)

    with pytest.raises(IndexedGraphSourceError, match=message):
        build_indexed_graph_projection(
            records,
            relations,
            graph_projection_id="graph-indexed-1",
            project_id="project-1",
        )


def test_forbidden_record_and_unsafe_reference_fail_closed():
    records = _records()
    records.append({
        "id": "forbidden-node",
        "project_id": "project-1",
        "kind": "document",
        "authority": "none",
        "privacy_class": "forbidden",
    })
    with pytest.raises(IndexedGraphSourceError, match="privacy"):
        build_indexed_graph_projection(
            records,
            graph_projection_id="graph-indexed-1",
            project_id="project-1",
        )

    records = _records()
    records[1]["source_ref"] = r"D:\private\secret.py"
    with pytest.raises(IndexedGraphSourceError, match="unsafe"):
        build_indexed_graph_projection(
            records,
            graph_projection_id="graph-indexed-1",
            project_id="project-1",
        )


def test_missing_project_and_unsafe_snapshot_fail_closed():
    with pytest.raises(IndexedGraphSourceError, match="no indexed records"):
        build_indexed_graph_projection(
            _records(),
            graph_projection_id="graph-indexed-1",
            project_id="missing-project",
        )
    with pytest.raises(IndexedGraphSourceError, match="unsafe"):
        build_indexed_graph_projection(
            _records(),
            graph_projection_id="graph-indexed-1",
            project_id="project-1",
            source_snapshot_refs=[r"D:\private\snapshot.json"],
        )


@pytest.mark.parametrize(
    ("field", "limit"),
    [("records", 512), ("relations", 1024)],
)
def test_hard_input_limits_are_enforced(field: str, limit: int):
    records = _records()
    relations = _relations()
    if field == "records":
        records = [
            {
                "id": f"node-{index}",
                "project_id": "project-1",
                "kind": "artifact",
                "authority": "governance_recorded",
            }
            for index in range(limit + 1)
        ]
    else:
        relations = [
            {
                "id": f"edge-{index}",
                "project_id": "project-1",
                "source": "project-node",
                "target": "project-node",
                "type": "inferred",
            }
            for index in range(limit + 1)
        ]

    with pytest.raises(IndexedGraphSourceError, match="hard limit"):
        build_indexed_graph_projection(
            records,
            relations,
            graph_projection_id="graph-indexed-1",
            project_id="project-1",
        )
