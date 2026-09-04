"""Tests for the explicit governance-digest graph source adapter."""
from __future__ import annotations

import copy
import json

import pytest

from control_plane.graph_context_selection import build_graph_context_selection
from control_plane.graph_projection_slice import build_graph_slice
from control_plane.graph_projection_validator import validate_graph_projection
from control_plane.governance_graph_source import (
    GovernanceGraphSourceError,
    build_governance_graph_projection,
)


def _digest() -> dict:
    return {
        "projects": [
            {
                "project_id": "project-1",
                "status": "in_progress",
                "priority": "P1",
                "autonomy_level": "reviewed",
                "goal": "private goal must not be exported",
                "project_root": r"D:\private\project-1",
            },
            {"project_id": "project-2", "status": "initialized"},
        ],
        "dispatches": [
            {
                "project_id": "project-1",
                "operation": "review",
                "decision_mode": "allow",
                "dispatch_ready": True,
                "packet_id": "packet-1",
                "packet_dir": r"D:\private\packet-1",
                "reason": "private reason must not be exported",
            },
            {
                "project_id": "project-2",
                "operation": "build",
                "decision_mode": "hold",
                "dispatch_ready": False,
                "packet_id": "packet-2",
            },
        ],
        "reports": [
            {
                "project_id": "project-1",
                "packet_id": "packet-1",
                "status": "passed",
                "changed_files": [r"D:\private\changed.py"],
                "report_path": r"D:\private\report.md",
            },
            {
                "project_id": "project-1",
                "status": "blocked",
                "report_path": r"D:\private\blocked.md",
            },
            {
                "project_id": "project-2",
                "packet_id": "packet-2",
                "status": "passed",
            },
        ],
        "runtime_dir": r"D:\private\runtime",
    }


def _build() -> dict:
    return build_governance_graph_projection(
        _digest(),
        graph_projection_id="graph-digest-1",
        project_id="project-1",
        source_snapshot_refs=["repo://PLAN.md"],
    )


def test_projection_is_valid_project_scoped_and_correlates_packet_evidence():
    projection = _build()

    assert validate_graph_projection(projection).valid
    assert [node["id"] for node in projection["nodes"]] == [
        "project-project-1",
        "decision-packet-1",
        "evidence-packet-1",
        "evidence-report-2",
    ]
    assert [edge["id"] for edge in projection["edges"]] == [
        "edge-project-dispatch-1",
        "edge-dispatch-report-1",
        "edge-project-report-2",
    ]
    assert projection["source_snapshot_refs"] == ["repo://PLAN.md"]
    assert projection["nodes"][2]["authority"] == "test_verified"
    assert projection["nodes"][3]["authority"] == "governance_recorded"


def test_existing_slice_and_selection_contracts_can_consume_source_output():
    projection = _build()
    graph_slice = build_graph_slice(projection, ["project-project-1"])

    selection = build_graph_context_selection(
        graph_slice,
        reader="reviewer",
        decision_needed="review digest context",
    )

    assert selection["project_id"] == "project-1"
    assert selection["selected_node_ids"] == ["project-project-1"]
    assert selection["authority_boundary"]["can_execute"] is False


def test_projection_omits_paths_goals_reasons_and_cross_project_records():
    projection = _build()
    serialized = json.dumps(projection, ensure_ascii=True)

    assert "private" not in serialized
    assert "project-2" not in serialized
    assert "packet-2" not in serialized
    assert "packet_dir" not in serialized
    assert "report_path" not in serialized
    assert "runtime_dir" not in serialized


def test_input_digest_is_not_mutated_and_output_is_deterministic():
    digest = _digest()
    before = copy.deepcopy(digest)

    first = build_governance_graph_projection(
        digest,
        graph_projection_id="graph-digest-1",
        project_id="project-1",
    )
    second = build_governance_graph_projection(
        digest,
        graph_projection_id="graph-digest-1",
        project_id="project-1",
    )

    assert digest == before
    assert first == second


@pytest.mark.parametrize(
    ("mutator", "message"),
    [
        (lambda digest: digest.update({"unknown": []}), "unsupported fields"),
        (
            lambda digest: digest["dispatches"][0].update({"unknown": "x"}),
            "unsupported fields",
        ),
        (
            lambda digest: digest["dispatches"][0].update({"dispatch_ready": "yes"}),
            "boolean",
        ),
        (
            lambda digest: digest["dispatches"][0].update({"operation": "token=secret"}),
            "unsafe",
        ),
    ],
)
def test_malformed_or_unsafe_digest_fails_closed(mutator, message: str):
    digest = _digest()
    mutator(digest)

    with pytest.raises(GovernanceGraphSourceError, match=message):
        build_governance_graph_projection(
            digest,
            graph_projection_id="graph-digest-1",
            project_id="project-1",
        )


def test_unsafe_snapshot_reference_fails_before_projection():
    with pytest.raises(GovernanceGraphSourceError, match="snapshot reference"):
        build_governance_graph_projection(
            _digest(),
            graph_projection_id="graph-digest-1",
            project_id="project-1",
            source_snapshot_refs=[r"D:\private\snapshot.json"],
        )


def test_missing_or_duplicate_project_fails_closed():
    with pytest.raises(GovernanceGraphSourceError, match="absent"):
        build_governance_graph_projection(
            _digest(),
            graph_projection_id="graph-digest-1",
            project_id="missing-project",
        )

    digest = _digest()
    digest["projects"].append({"project_id": "project-1", "status": "planned"})
    with pytest.raises(GovernanceGraphSourceError, match="duplicate"):
        build_governance_graph_projection(
            digest,
            graph_projection_id="graph-digest-1",
            project_id="project-1",
        )


@pytest.mark.parametrize(
    ("field", "limit"),
    [("projects", 64), ("dispatches", 256), ("reports", 256)],
)
def test_hard_record_limits_are_enforced(field: str, limit: int):
    digest = _digest()
    template = digest[field][0]
    digest[field] = [copy.deepcopy(template) for _ in range(limit + 1)]
    if field == "projects":
        digest[field] = [
            {"project_id": f"project-{index}", "status": "initialized"}
            for index in range(limit + 1)
        ]

    with pytest.raises(GovernanceGraphSourceError, match="hard limit"):
        build_governance_graph_projection(
            digest,
            graph_projection_id="graph-digest-1",
            project_id="project-1",
        )
