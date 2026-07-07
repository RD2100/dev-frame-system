"""P3-2: graph projection and knowledge canvas contract validator.

Per design-coverage-gap-remediation-plan.md:318-336:

  - inferred edges cannot become source truth;
  - annotations cannot become decisions;
  - graph context can seed context selection only with cited, authority-labeled
    nodes;
  - first graph slice is read-only: no UI, graph database, broad extraction,
    writeback, or graph-driven code changes.

Repair strategy:
  1. Define graph node and edge schemas.
  2. Block writeback and graph-driven changes in the first slice.
  3. Enforce authority labeling on context-seeding nodes.
  4. Keep edges inferred-only unless cited from authoritative source.
"""
from __future__ import annotations

from dataclasses import dataclass, field

# Edge types — only cited edges carry authority weight.
EDGE_TYPES: tuple[str, ...] = (
    "cited",
    "inferred",
    "annotated",
)

# Node types in the projection.
NODE_TYPES: tuple[str, ...] = (
    "decision",
    "evidence",
    "artifact",
    "agent",
    "review",
    "context_seed",
)

# Authority labels that nodes can carry.
AUTHORITY_LABELS: tuple[str, ...] = (
    "human_decided",
    "external_reviewed",
    "test_verified",
    "governance_recorded",
    "cited_source",
    "none",
)

# Sources treated as authoritative for edge citations.
AUTHORITATIVE_SOURCES: tuple[str, ...] = (
    "human_decided",
    "external_reviewed",
    "test_verified",
    "governance_recorded",
)

# Operations forbidden in the read-only first slice.
FORBIDDEN_GRAPH_OPERATIONS: tuple[str, ...] = (
    "add_node",
    "add_edge",
    "annotate",
    "build_ui",
    "init_graph_db",
    "broad_extraction",
    "writeback",
    "graph_driven_code_change",
    "export_canvas",
)

# Recognized graph operations.
KNOWN_GRAPH_OPERATIONS: tuple[str, ...] = (
    "project",
    "query",
    "seed_context",
    "add_node",
    "add_edge",
    "annotate",
    "build_ui",
    "init_graph_db",
    "broad_extraction",
    "writeback",
    "graph_driven_code_change",
    "export_canvas",
)


@dataclass
class ValidationResult:
    valid: bool
    errors: list[str] = field(default_factory=list)

    def __bool__(self) -> bool:
        return self.valid


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _is_valid_graph_node_shape(
    node: dict,
    collect_errors: bool = False,
) -> tuple[bool, list[str]]:
    """Structural check for a single graph node."""
    errors: list[str] = []
    nid = node.get("id", "")
    prefix = f"node[{nid or '<missing>'}]"

    for field in ("id", "type", "authority"):
        val = str(node.get(field, "")).strip()
        if not val:
            if collect_errors:
                errors.append(f"{prefix}: {field} is required")
            else:
                return False, errors

    ntype = str(node.get("type", "")).strip()
    if ntype not in NODE_TYPES:
        if collect_errors:
            errors.append(
                f"{prefix}: type={ntype!r} not in {NODE_TYPES}"
            )
        else:
            return False, errors

    authority = str(node.get("authority", "")).strip()
    if authority not in AUTHORITY_LABELS:
        if collect_errors:
            errors.append(
                f"{prefix}: authority={authority!r} not in {AUTHORITY_LABELS}"
            )
        else:
            return False, errors

    return True, errors


def _is_valid_graph_edge_shape(
    edge: dict,
    collect_errors: bool = False,
) -> tuple[bool, list[str]]:
    """Structural check for a single graph edge."""
    errors: list[str] = []
    eid = edge.get("id", "")
    prefix = f"edge[{eid or '<missing>'}]"

    for field in ("id", "source", "target", "type"):
        val = str(edge.get(field, "")).strip()
        if not val:
            if collect_errors:
                errors.append(f"{prefix}: {field} is required")
            else:
                return False, errors

    etype = str(edge.get("type", "")).strip()
    if etype not in EDGE_TYPES:
        if collect_errors:
            errors.append(
                f"{prefix}: type={etype!r} not in {EDGE_TYPES}"
            )
        else:
            return False, errors

    # cited edges need a citation_source.
    if etype == "cited":
        citation = str(edge.get("citation_source", "")).strip()
        if not citation:
            if collect_errors:
                errors.append(
                    f"{prefix}: cited edge requires citation_source"
                )
            else:
                return False, errors

    return True, errors


def _valid_node_by_id(nodes: list[dict]) -> dict[str, dict]:
    """Return shape-valid nodes keyed by normalized id."""
    result: dict[str, dict] = {}
    for node in nodes:
        shape_ok, _ = _is_valid_graph_node_shape(node, collect_errors=False)
        if not shape_ok:
            continue
        result[str(node.get("id", "")).strip()] = node
    return result


def _edge_requires_existing_nodes(edge: dict) -> bool:
    """Return whether an edge can carry authority and must resolve endpoints."""
    etype = str(edge.get("type", "")).strip()
    return etype == "cited" or bool(edge.get("is_source_truth", False))


def _authority_edge_reference_errors(
    edge: dict,
    node_by_id: dict[str, dict],
) -> list[str]:
    """Return endpoint resolution errors for authority-bearing graph edges."""
    if not _edge_requires_existing_nodes(edge):
        return []

    eid = str(edge.get("id", "")).strip()
    prefix = f"edge[{eid or '<missing>'}]"
    errors: list[str] = []

    for field in ("source", "target"):
        node_id = str(edge.get(field, "")).strip()
        if not node_id:
            continue
        if node_id not in node_by_id:
            errors.append(
                f"{prefix}: authority-bearing edge {field}={node_id!r} "
                f"must reference a shape-valid existing node"
            )

    return errors


def _has_resolved_authority_edge_references(
    edge: dict,
    node_by_id: dict[str, dict],
) -> bool:
    return not _authority_edge_reference_errors(edge, node_by_id)


def _has_authoritative_cited_incoming_edge(
    *,
    seed_id: str,
    edges: list[dict],
    node_by_id: dict[str, dict],
) -> bool:
    """Check that a context seed is cited by an existing authoritative node."""
    for edge in edges:
        shape_ok, _ = _is_valid_graph_edge_shape(edge, collect_errors=False)
        if not shape_ok:
            continue
        if str(edge.get("type", "")).strip() != "cited":
            continue
        if not _has_resolved_authority_edge_references(edge, node_by_id):
            continue
        if str(edge.get("target", "")).strip() != seed_id:
            continue
        source_id = str(edge.get("source", "")).strip()
        source_node = node_by_id.get(source_id)
        if not source_node:
            continue
        source_authority = str(source_node.get("authority", "")).strip()
        if source_authority in AUTHORITATIVE_SOURCES:
            return True
    return False


def _check_graph_boundary_rules(
    payload: dict,
    collect_errors: bool = False,
) -> tuple[bool, list[str]]:
    """Boundary rule checks for the graph projection."""
    errors: list[str] = []
    nodes: list[dict] = payload.get("nodes") or []
    edges: list[dict] = payload.get("edges") or []
    operations: list[str] = payload.get("operations") or []

    node_by_id = _valid_node_by_id(nodes)

    # Block forbidden operations.
    for op in operations:
        op = str(op).strip()
        if op in FORBIDDEN_GRAPH_OPERATIONS:
            if collect_errors:
                errors.append(
                    f"operation={op!r} is forbidden in the first graph slice; "
                    f"read-only projection only"
                )
            else:
                return False, errors
        if op not in KNOWN_GRAPH_OPERATIONS:
            if collect_errors:
                errors.append(
                    f"operation={op!r} is not a known graph operation; "
                    f"must be one of {KNOWN_GRAPH_OPERATIONS}"
                )
            else:
                return False, errors

    # Authority-bearing edges must reference existing, shape-valid nodes.
    for edge in edges:
        for ref_error in _authority_edge_reference_errors(edge, node_by_id):
            if collect_errors:
                errors.append(ref_error)
            else:
                return False, errors

    # Inferred edges cannot become source truth.
    for edge in edges:
        eid = str(edge.get("id", "")).strip()
        prefix = f"edge[{eid}]"
        etype = str(edge.get("type", "")).strip()

        if etype == "inferred":
            is_truth = edge.get("is_source_truth", False)
            if is_truth:
                if collect_errors:
                    errors.append(
                        f"{prefix}: inferred edge cannot be source truth; "
                        f"only cited edges may carry authority weight"
                    )
                else:
                    return False, errors

    # Annotations cannot become decisions.
    for edge in edges:
        eid = str(edge.get("id", "")).strip()
        prefix = f"edge[{eid}]"
        etype = str(edge.get("type", "")).strip()

        if etype == "annotated":
            promoted = edge.get("promoted_to_decision", False)
            if promoted:
                if collect_errors:
                    errors.append(
                        f"{prefix}: annotated edge cannot be promoted to "
                        f"decision; annotations are not decisions"
                    )
                else:
                    return False, errors

    # Context seeds need authority-labeled source nodes.
    context_seed_nodes = [
        n for n in nodes
        if str(n.get("type", "")).strip() == "context_seed"
    ]
    for seed in context_seed_nodes:
        sid = str(seed.get("id", "")).strip()
        prefix = f"node[{sid}]"
        authority = str(seed.get("authority", "")).strip()

        if authority not in AUTHORITATIVE_SOURCES:
            if collect_errors:
                errors.append(
                    f"{prefix}: context_seed node must have an authoritative "
                    f"source; authority={authority!r} is not in "
                    f"{AUTHORITATIVE_SOURCES}. Context seeds require cited, "
                    f"authority-labeled nodes."
                )
            else:
                return False, errors

        # Also check that context_seed has at least one cited incoming edge.
        cited_incoming = any(
            str(e.get("type", "")).strip() == "cited"
            and str(e.get("target", "")).strip() == sid
            for e in edges
        )
        if not cited_incoming:
            if collect_errors:
                errors.append(
                    f"{prefix}: context_seed requires at least one cited "
                    f"incoming edge; context seeds must be reachable from "
                    f"authoritative sources"
                )
            else:
                return False, errors
        elif not _has_authoritative_cited_incoming_edge(
            seed_id=sid,
            edges=edges,
            node_by_id=node_by_id,
        ):
            if collect_errors:
                errors.append(
                    f"{prefix}: context_seed requires a cited incoming edge "
                    f"from an existing authoritative source node"
                )
            else:
                return False, errors

    return True, errors


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def validate_graph_projection(payload: dict) -> ValidationResult:
    """Validate graph projection against boundary rules.

    Enforces:
      - Read-only first slice (no UI, DB, extraction, writeback, code changes)
      - Inferred edges cannot be source truth
      - Annotations cannot become decisions
      - Context seeds need authority-labeled source nodes with cited edges
    """
    errors: list[str] = []
    nodes: list[dict] = payload.get("nodes") or []
    edges: list[dict] = payload.get("edges") or []

    for node in nodes:
        _, shape_errors = _is_valid_graph_node_shape(node, collect_errors=True)
        errors.extend(shape_errors)

    for edge in edges:
        _, shape_errors = _is_valid_graph_edge_shape(edge, collect_errors=True)
        errors.extend(shape_errors)

    _, boundary_errors = _check_graph_boundary_rules(payload, collect_errors=True)
    errors.extend(boundary_errors)

    return ValidationResult(valid=len(errors) == 0, errors=errors)


def derive_graph_projection(payload: dict) -> dict:
    """Read-only projection of graph state.

    Returns counts by node type, edge type, and authority level.
    Shape-invalid nodes/edges are excluded.
    """
    nodes: list[dict] = payload.get("nodes") or []
    edges: list[dict] = payload.get("edges") or []
    operations: list[str] = payload.get("operations") or []

    total_nodes = 0
    by_node_type: dict[str, int] = {}
    by_authority: dict[str, int] = {}
    authority_seeded_count = 0
    total_edges = 0
    by_edge_type: dict[str, int] = {}
    inferred_truth_edges = 0
    valid_node_by_id = _valid_node_by_id(nodes)

    for node in nodes:
        shape_ok, _ = _is_valid_graph_node_shape(node, collect_errors=False)
        if not shape_ok:
            continue
        total_nodes += 1
        ntype = str(node.get("type", "")).strip()
        authority = str(node.get("authority", "")).strip()

        by_node_type[ntype] = by_node_type.get(ntype, 0) + 1
        by_authority[authority] = by_authority.get(authority, 0) + 1

        if (
            ntype == "context_seed"
            and authority in AUTHORITATIVE_SOURCES
            and _has_authoritative_cited_incoming_edge(
                seed_id=str(node.get("id", "")).strip(),
                edges=edges,
                node_by_id=valid_node_by_id,
            )
        ):
            authority_seeded_count += 1

    for edge in edges:
        shape_ok, _ = _is_valid_graph_edge_shape(edge, collect_errors=False)
        if not shape_ok:
            continue
        if not _has_resolved_authority_edge_references(edge, valid_node_by_id):
            continue
        total_edges += 1
        etype = str(edge.get("type", "")).strip()
        by_edge_type[etype] = by_edge_type.get(etype, 0) + 1

        if etype == "inferred" and edge.get("is_source_truth", False):
            inferred_truth_edges += 1

    return {
        "total_nodes": total_nodes,
        "by_node_type": by_node_type,
        "by_authority": by_authority,
        "authority_seeded_count": authority_seeded_count,
        "total_edges": total_edges,
        "by_edge_type": by_edge_type,
        "inferred_truth_edges": inferred_truth_edges,
        "operation_count": len(operations),
    }
