"""Tests for P3-2: graph projection and knowledge canvas validator.

Per design-coverage-gap-remediation-plan.md:318-336:
  - inferred edges cannot become source truth;
  - annotations cannot become decisions;
  - graph context can seed context selection only with cited, authority-labeled
    nodes;
  - first graph slice is read-only: no UI, graph database, broad extraction,
    writeback, or graph-driven code changes.
"""
from __future__ import annotations

import pytest

from control_plane.graph_projection_validator import (
    AUTHORITATIVE_SOURCES,
    FORBIDDEN_GRAPH_OPERATIONS,
    derive_graph_projection,
    validate_graph_projection,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _node(**overrides):
    """Minimal valid graph node."""
    base = {
        "id": "n1",
        "type": "decision",
        "authority": "human_decided",
    }
    base.update(overrides)
    return base


def _edge(**overrides):
    """Minimal valid graph edge."""
    base = {
        "id": "e1",
        "source": "n1",
        "target": "n2",
        "type": "cited",
        "citation_source": "paper-1",
    }
    base.update(overrides)
    return base


def _context_seed(**overrides):
    base = {"id": "seed-1", "type": "context_seed", "authority": "external_reviewed"}
    base.update(overrides)
    return _node(**base)


def _context_seed_edge():
    return _edge(id="ce1", source="n1", target="seed-1", type="cited",
                 citation_source="paper-1")


def _payload(nodes=None, edges=None, operations=None):
    return {
        "nodes": nodes or [],
        "edges": edges or [],
        "operations": operations or [],
    }


# ---------------------------------------------------------------------------
# Forbidden operations (read-only first slice)
# ---------------------------------------------------------------------------


class TestForbiddenOperations:
    def test_build_ui_is_forbidden(self):
        p = _payload(nodes=[_node()], operations=["build_ui"])
        result = validate_graph_projection(p)
        assert not result.valid
        assert "build_ui" in result.errors[0]

    def test_init_graph_db_is_forbidden(self):
        p = _payload(nodes=[_node()], operations=["init_graph_db"])
        result = validate_graph_projection(p)
        assert not result.valid
        assert "init_graph_db" in result.errors[0]

    def test_broad_extraction_is_forbidden(self):
        p = _payload(nodes=[_node()], operations=["broad_extraction"])
        result = validate_graph_projection(p)
        assert not result.valid

    def test_writeback_is_forbidden(self):
        p = _payload(nodes=[_node()], operations=["writeback"])
        result = validate_graph_projection(p)
        assert not result.valid

    def test_graph_driven_code_change_is_forbidden(self):
        p = _payload(nodes=[_node()], operations=["graph_driven_code_change"])
        result = validate_graph_projection(p)
        assert not result.valid

    def test_export_canvas_is_forbidden(self):
        p = _payload(nodes=[_node()], operations=["export_canvas"])
        result = validate_graph_projection(p)
        assert not result.valid

    @pytest.mark.parametrize("operation", ["add_node", "add_edge", "annotate"])
    def test_mutation_like_operations_are_forbidden(self, operation):
        p = _payload(nodes=[_node()], operations=[operation])
        result = validate_graph_projection(p)
        assert not result.valid
        assert operation in result.errors[0]

    def test_project_is_allowed(self):
        p = _payload(nodes=[_node()], operations=["project"])
        result = validate_graph_projection(p)
        assert result.valid

    def test_query_is_allowed(self):
        p = _payload(nodes=[_node()], operations=["query"])
        result = validate_graph_projection(p)
        assert result.valid

    def test_seed_context_is_allowed(self):
        p = _payload(
            nodes=[_node(), _context_seed()],
            edges=[_context_seed_edge()],
            operations=["seed_context"],
        )
        result = validate_graph_projection(p)
        assert result.valid

    def test_unknown_operation_rejected(self):
        p = _payload(nodes=[_node()], operations=["deploy_knowledge"])
        result = validate_graph_projection(p)
        assert not result.valid

    def test_all_forbidden_listed(self):
        assert "build_ui" in FORBIDDEN_GRAPH_OPERATIONS
        assert "init_graph_db" in FORBIDDEN_GRAPH_OPERATIONS
        assert "broad_extraction" in FORBIDDEN_GRAPH_OPERATIONS
        assert "writeback" in FORBIDDEN_GRAPH_OPERATIONS
        assert "graph_driven_code_change" in FORBIDDEN_GRAPH_OPERATIONS
        assert "export_canvas" in FORBIDDEN_GRAPH_OPERATIONS
        assert "add_node" in FORBIDDEN_GRAPH_OPERATIONS
        assert "add_edge" in FORBIDDEN_GRAPH_OPERATIONS
        assert "annotate" in FORBIDDEN_GRAPH_OPERATIONS


# ---------------------------------------------------------------------------
# Inferred edges cannot be source truth
# ---------------------------------------------------------------------------


class TestInferredEdgesNotSourceTruth:
    def test_inferred_edge_as_truth_rejected(self):
        """Inferred edges cannot carry source-truth weight."""
        e = _edge(id="e1", type="inferred", is_source_truth=True)
        p = _payload(nodes=[_node(), _node(id="n2")], edges=[e])
        result = validate_graph_projection(p)
        assert not result.valid
        assert "inferred" in result.errors[0].lower()
        assert "source truth" in result.errors[0].lower()

    def test_inferred_edge_not_truth_ok(self):
        e = _edge(id="e1", type="inferred")
        p = _payload(nodes=[_node(), _node(id="n2")], edges=[e])
        result = validate_graph_projection(p)
        assert result.valid

    def test_cited_edge_as_truth_ok(self):
        """Cited edges CAN carry source-truth weight."""
        e = _edge(id="e1", type="cited", citation_source="paper-1",
                  is_source_truth=True)
        p = _payload(nodes=[_node(), _node(id="n2")], edges=[e])
        result = validate_graph_projection(p)
        assert result.valid

    @pytest.mark.parametrize("field", ["source", "target"])
    def test_source_truth_cited_edge_missing_endpoint_rejected(self, field):
        """Source-truth cited edges cannot cite through dangling endpoints."""
        e = _edge(id="e1", type="cited", citation_source="paper-1",
                  is_source_truth=True, **{field: f"missing-{field}"})
        p = _payload(nodes=[_node(), _node(id="n2")], edges=[e])
        result = validate_graph_projection(p)
        assert not result.valid
        assert any(
            field in error and "shape-valid existing node" in error
            for error in result.errors
        )

    def test_multiple_inferred_truth_rejected(self):
        e1 = _edge(id="e1", type="inferred", is_source_truth=True)
        e2 = _edge(id="e2", type="inferred", is_source_truth=True)
        p = _payload(
            nodes=[_node(), _node(id="n2"), _node(id="n3")],
            edges=[e1, e2],
        )
        result = validate_graph_projection(p)
        assert not result.valid
        assert len(result.errors) >= 2


# ---------------------------------------------------------------------------
# Annotations cannot become decisions
# ---------------------------------------------------------------------------


class TestAnnotationsNotDecisions:
    def test_annotated_edge_promoted_to_decision_rejected(self):
        e = _edge(id="e1", type="annotated", promoted_to_decision=True)
        p = _payload(nodes=[_node(), _node(id="n2")], edges=[e])
        result = validate_graph_projection(p)
        assert not result.valid
        assert "annotat" in result.errors[0].lower()
        assert "decision" in result.errors[0].lower()

    def test_annotated_edge_not_promoted_ok(self):
        e = _edge(id="e1", type="annotated")
        p = _payload(nodes=[_node(), _node(id="n2")], edges=[e])
        result = validate_graph_projection(p)
        assert result.valid

    def test_cited_edge_promoted_to_decision_ok(self):
        """cite edges are annotations."""
        e = _edge(id="e1", type="cited", citation_source="paper-1",
                  promoted_to_decision=True)
        p = _payload(nodes=[_node(), _node(id="n2")], edges=[e])
        # cited edges are not annotated — promotion doesn't trigger annotated rule
        result = validate_graph_projection(p)
        assert result.valid


# ---------------------------------------------------------------------------
# Context seeds need authority-labeled source nodes with cited edges
# ---------------------------------------------------------------------------


class TestContextSeedAuthority:
    def test_context_seed_non_authority_rejected(self):
        """Context seed with authority='none' is rejected."""
        seed = _context_seed(authority="none")
        p = _payload(
            nodes=[_node(), seed],
            edges=[_context_seed_edge()],
        )
        result = validate_graph_projection(p)
        assert not result.valid
        assert "context_seed" in result.errors[0].lower()

    def test_context_seed_inferred_only_not_authoritative(self):
        """'inferred' is not an authoritative source."""
        seed = _context_seed(authority="inferred")
        p = _payload(
            nodes=[_node(), seed],
            edges=[_context_seed_edge()],
        )
        result = validate_graph_projection(p)
        assert not result.valid

    def test_context_seed_human_decided_valid(self):
        seed = _context_seed(authority="human_decided")
        p = _payload(
            nodes=[_node(), seed],
            edges=[_context_seed_edge()],
        )
        result = validate_graph_projection(p)
        assert result.valid

    def test_context_seed_external_reviewed_valid(self):
        seed = _context_seed(authority="external_reviewed")
        p = _payload(
            nodes=[_node(), seed],
            edges=[_context_seed_edge()],
        )
        result = validate_graph_projection(p)
        assert result.valid

    def test_context_seed_needs_cited_incoming_edge(self):
        """Authority alone is not enough — need a cited edge to the seed."""
        seed = _context_seed(authority="external_reviewed")
        p = _payload(
            nodes=[_node(), seed],
            edges=[],  # no cited edge to seed
        )
        result = validate_graph_projection(p)
        assert not result.valid
        assert "cited" in result.errors[0].lower()

    def test_context_seed_inferred_edge_not_enough(self):
        """An inferred edge to the seed is not sufficient — need cited."""
        seed = _context_seed(authority="external_reviewed")
        inf_edge = _edge(id="ie1", type="inferred", target="seed-1")
        p = _payload(
            nodes=[_node(), seed],
            edges=[inf_edge],
        )
        result = validate_graph_projection(p)
        assert not result.valid
        assert "cited" in result.errors[0].lower()

    def test_context_seed_cited_edge_missing_source_rejected(self):
        seed = _context_seed(authority="external_reviewed")
        cited_edge = _edge(id="ce1", source="missing", target="seed-1",
                           type="cited", citation_source="paper-1")
        p = _payload(nodes=[_node(), seed], edges=[cited_edge])
        result = validate_graph_projection(p)
        assert not result.valid
        assert "authoritative source node" in result.errors[-1]

    def test_context_seed_cited_edge_non_authority_source_rejected(self):
        seed = _context_seed(authority="external_reviewed")
        source = _node(id="source-1", type="artifact", authority="none")
        cited_edge = _edge(id="ce1", source="source-1", target="seed-1",
                           type="cited", citation_source="paper-1")
        p = _payload(nodes=[source, seed], edges=[cited_edge])
        result = validate_graph_projection(p)
        assert not result.valid
        assert "authoritative source node" in result.errors[-1]

    def test_authoritative_sources_list(self):
        assert "human_decided" in AUTHORITATIVE_SOURCES
        assert "external_reviewed" in AUTHORITATIVE_SOURCES
        assert "test_verified" in AUTHORITATIVE_SOURCES
        assert "governance_recorded" in AUTHORITATIVE_SOURCES
        assert "cited_source" not in AUTHORITATIVE_SOURCES
        assert "none" not in AUTHORITATIVE_SOURCES


# ---------------------------------------------------------------------------
# Node/edge shape validation
# ---------------------------------------------------------------------------


class TestNodeShape:
    def test_missing_node_id(self):
        n = _node(id="")
        result = validate_graph_projection(_payload(nodes=[n]))
        assert not result.valid
        assert "id" in result.errors[0]

    def test_whitespace_node_id_rejected(self):
        n = _node(id="   ")
        result = validate_graph_projection(_payload(nodes=[n]))
        assert not result.valid
        assert "id" in result.errors[0]

    def test_missing_node_type(self):
        n = _node(type="")
        result = validate_graph_projection(_payload(nodes=[n]))
        assert not result.valid
        assert "type" in result.errors[0]

    def test_invalid_node_type(self):
        n = _node(type="unknown_node")
        result = validate_graph_projection(_payload(nodes=[n]))
        assert not result.valid

    def test_missing_authority(self):
        n = _node(authority="")
        result = validate_graph_projection(_payload(nodes=[n]))
        assert not result.valid
        assert "authority" in result.errors[0]

    def test_invalid_authority(self):
        n = _node(authority="self_declared")
        result = validate_graph_projection(_payload(nodes=[n]))
        assert not result.valid


class TestEdgeShape:
    def test_missing_edge_id(self):
        e = _edge(id="")
        result = validate_graph_projection(_payload(
            nodes=[_node(), _node(id="n2")], edges=[e]))
        assert not result.valid
        assert "id" in result.errors[0]

    def test_missing_source(self):
        e = _edge(source="")
        result = validate_graph_projection(_payload(
            nodes=[_node(), _node(id="n2")], edges=[e]))
        assert not result.valid

    def test_missing_target(self):
        e = _edge(target="")
        result = validate_graph_projection(_payload(
            nodes=[_node(), _node(id="n2")], edges=[e]))
        assert not result.valid

    def test_missing_type(self):
        e = _edge(type="")
        result = validate_graph_projection(_payload(
            nodes=[_node(), _node(id="n2")], edges=[e]))
        assert not result.valid

    def test_invalid_edge_type(self):
        e = _edge(type="hyperlinked")
        result = validate_graph_projection(_payload(
            nodes=[_node(), _node(id="n2")], edges=[e]))
        assert not result.valid

    def test_cited_edge_needs_citation_source(self):
        e = _edge(type="cited", citation_source="")
        result = validate_graph_projection(_payload(
            nodes=[_node(), _node(id="n2")], edges=[e]))
        assert not result.valid
        assert "citation_source" in result.errors[0]


# ---------------------------------------------------------------------------
# derive_graph_projection (projection)
# ---------------------------------------------------------------------------


class TestDeriveGraphProjection:
    def test_empty_payload(self):
        result = derive_graph_projection({})
        assert result["total_nodes"] == 0
        assert result["total_edges"] == 0

    def test_counts_by_node_type(self):
        nodes = [
            _node(id="n1", type="decision"),
            _node(id="n2", type="evidence"),
            _node(id="n3", type="evidence"),
        ]
        result = derive_graph_projection(_payload(nodes=nodes))
        assert result["total_nodes"] == 3
        assert result["by_node_type"]["decision"] == 1
        assert result["by_node_type"]["evidence"] == 2

    def test_counts_by_authority(self):
        nodes = [
            _node(id="n1", authority="human_decided"),
            _node(id="n2", authority="human_decided"),
            _node(id="n3", authority="external_reviewed"),
        ]
        result = derive_graph_projection(_payload(nodes=nodes))
        assert result["by_authority"]["human_decided"] == 2
        assert result["by_authority"]["external_reviewed"] == 1

    def test_authority_seeded_count(self):
        """Only context_seed nodes with authoritative source are counted."""
        nodes = [
            _node(id="n1", type="decision", authority="human_decided"),
            _node(id="seed-1", type="context_seed",
                  authority="external_reviewed"),
            _node(id="seed-2", type="context_seed", authority="none"),
        ]
        edges = [_edge(id="ce1", source="n1", target="seed-1",
                       type="cited", citation_source="paper-1")]
        result = derive_graph_projection(_payload(nodes=nodes, edges=edges))
        assert result["authority_seeded_count"] == 1

    def test_authority_seeded_count_requires_authoritative_cited_incoming(self):
        nodes = [
            _node(id="n1", type="decision", authority="human_decided"),
            _node(id="seed-1", type="context_seed",
                  authority="external_reviewed"),
        ]
        result = derive_graph_projection(_payload(nodes=nodes, edges=[]))
        assert result["authority_seeded_count"] == 0

    def test_counts_by_edge_type(self):
        edges = [
            _edge(id="e1", type="cited", citation_source="p1"),
            _edge(id="e2", type="cited", citation_source="p2"),
            _edge(id="e3", type="inferred"),
        ]
        result = derive_graph_projection(_payload(
            nodes=[_node(), _node(id="n2"), _node(id="n3")], edges=edges))
        assert result["total_edges"] == 3
        assert result["by_edge_type"]["cited"] == 2
        assert result["by_edge_type"]["inferred"] == 1

    def test_inferred_truth_edges_counted(self):
        edges = [
            _edge(id="e1", type="inferred", is_source_truth=True),
            _edge(id="e2", type="inferred"),
        ]
        result = derive_graph_projection(_payload(
            nodes=[_node(), _node(id="n2")], edges=edges))
        assert result["inferred_truth_edges"] == 1

    @pytest.mark.parametrize("field", ["source", "target"])
    def test_source_truth_cited_edge_with_missing_endpoint_excluded(self, field):
        nodes = [
            _node(id="n1", type="decision", authority="human_decided"),
            _node(id="seed-1", type="context_seed",
                  authority="external_reviewed"),
        ]
        edge = _edge(
            id="ce1",
            source="n1",
            target="seed-1",
            type="cited",
            citation_source="paper-1",
            is_source_truth=True,
        )
        edge[field] = f"missing-{field}"
        result = derive_graph_projection(_payload(nodes=nodes, edges=[edge]))
        assert result["authority_seeded_count"] == 0
        assert result["total_edges"] == 0
        assert "cited" not in result["by_edge_type"]

    def test_shape_invalid_excluded(self):
        nodes = [_node(id="")]
        result = derive_graph_projection(_payload(nodes=nodes))
        assert result["total_nodes"] == 0

    def test_projection_read_only(self):
        result = derive_graph_projection(
            _payload(nodes=[_node(), _node(id="n2")], edges=[_edge(
                id="e1", type="cited", citation_source="p1")]))
        assert "errors" not in result
        assert "raw" not in result
        assert "decisions" not in result

    def test_operation_count(self):
        result = derive_graph_projection(_payload(
            nodes=[_node()],
            operations=["project", "query", "seed_context"],
        ))
        assert result["operation_count"] == 3


# ---------------------------------------------------------------------------
# Good path
# ---------------------------------------------------------------------------


class TestGoodPath:
    def test_minimal_valid_graph(self):
        p = _payload(
            nodes=[_node(), _node(id="n2")],
            edges=[_edge(id="e1", type="cited", citation_source="p1")],
        )
        result = validate_graph_projection(p)
        assert result.valid

    def test_full_valid_projection(self):
        p = _payload(
            nodes=[
                _node(id="n1", type="decision",
                      authority="human_decided"),
                _node(id="n2", type="evidence",
                      authority="external_reviewed"),
                _node(id="seed-1", type="context_seed",
                      authority="external_reviewed"),
            ],
            edges=[
                _edge(id="e1", type="cited", citation_source="paper-1",
                      source="n1", target="seed-1"),
                _edge(id="e2", type="inferred",
                      source="n1", target="n2"),
            ],
            operations=["project", "seed_context"],
        )
        result = validate_graph_projection(p)
        assert result.valid
