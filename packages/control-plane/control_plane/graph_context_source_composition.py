"""Compose already-sanitized graph slices into one bounded read model.

The composition boundary is deliberately smaller than a retrieval system.  A
trusted caller supplies validated slices; this module only validates their
project binding, conservatively merges duplicate identities, and delegates
later context ranking to the existing deterministic proposal adapter.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field as dataclass_field
from math import isfinite
import re
from typing import Any

from .graph_context_selection import (
    EDGE_TYPES,
    FRESHNESS_STATES,
    GraphContextSelectionError,
    NODE_TYPES,
    OMISSION_REASONS,
    PRIVACY_CLASSES,
    build_graph_context_selection,
)
from .graph_projection_validator import AUTHORITY_LABELS


MAX_SOURCES = 16
MAX_NODES = 128
MAX_EDGES = 256
MAX_CONFLICTS = 512
MAX_PROVENANCE = 128
MAX_TEXT_LENGTH = 512
MAX_REF_LENGTH = 512

_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_REF_RE = re.compile(
    r"^(?P<scheme>[A-Za-z][A-Za-z0-9+.-]{1,31})://"
    r"(?P<body>[A-Za-z0-9][A-Za-z0-9._~:/#?&=+\-]{0,511})$"
)
_SENSITIVE_RE = re.compile(
    r"(?i)(?:api[_-]?key|authorization|bearer|cookie|password|secret|token)"
    r"|sk-[A-Za-z0-9_-]{12,}"
)
_PUBLIC_REF_SCHEMES = {
    "artifact",
    "code",
    "decision",
    "doc",
    "evidence",
    "graph",
    "paper",
    "project",
    "repo",
    "review",
    "run",
    "skill",
}
_AUTHORITY_RANK = {
    "none": 0,
    "cited_source": 1,
    "governance_recorded": 2,
    "test_verified": 3,
    "external_reviewed": 4,
    "human_decided": 5,
}
_FRESHNESS_RANK = {"unknown": 0, "omitted": 0, "stale": 1, "current": 2}
_PRIVACY_RANK = {
    "public_repo": 0,
    "private_content_summary": 1,
    "local_path_only": 2,
    "sensitive_redacted": 3,
    "unknown": 4,
}


class GraphContextSourceCompositionError(GraphContextSelectionError):
    """Raised when validated source slices cannot be safely composed."""


@dataclass
class _NodeMergeState:
    nodes: dict[str, dict[str, Any]] = dataclass_field(default_factory=dict)
    order: list[str] = dataclass_field(default_factory=list)
    provenance: dict[str, list[str]] = dataclass_field(default_factory=dict)
    selected_ids: list[str] = dataclass_field(default_factory=list)
    selected_seen: set[str] = dataclass_field(default_factory=set)
    conflicts: list[dict[str, str]] = dataclass_field(default_factory=list)
    redacted_count: int = 0


def compose_graph_context_sources(
    slices: Sequence[Mapping[str, Any]],
    *,
    project_id: str,
    graph_projection_id: str,
    max_sources: int = MAX_SOURCES,
    max_nodes: int = MAX_NODES,
    max_edges: int = MAX_EDGES,
) -> dict[str, Any]:
    """Return one deterministic, project-bound graph slice without mutation."""
    _validate_arguments(
        slices,
        project_id=project_id,
        graph_projection_id=graph_projection_id,
        max_sources=max_sources,
        max_nodes=max_nodes,
        max_edges=max_edges,
    )
    sources = _prepare_sources(slices, project_id, max_sources)
    (
        nodes,
        selected_ids,
        dropped_nodes,
        node_conflicts,
        provenance,
        redacted_count,
        node_by_id,
    ) = _merge_nodes(sources, max_nodes)
    edges, dropped_edges, edge_conflicts, edge_redactions = _merge_edges(
        sources, set(node_by_id), max_edges
    )
    redacted_count += edge_redactions
    omitted_neighbors, omitted_edges = _compose_omissions(
        sources, node_by_id, edges, dropped_nodes, dropped_edges
    )
    return _assemble_projection(
        project_id=project_id,
        graph_projection_id=graph_projection_id,
        sources=sources,
        selected_ids=selected_ids,
        nodes=nodes,
        edges=edges,
        omitted_neighbors=_dedupe_omissions(omitted_neighbors),
        omitted_edges=_dedupe_omissions(omitted_edges),
        conflicts=(node_conflicts + edge_conflicts)[:MAX_CONFLICTS],
        provenance=provenance,
        redacted_count=redacted_count,
    )


def _validate_arguments(
    slices: object,
    *,
    project_id: object,
    graph_projection_id: object,
    max_sources: object,
    max_nodes: object,
    max_edges: object,
) -> None:
    if isinstance(slices, (str, bytes, bytearray)) or not isinstance(slices, Sequence):
        raise GraphContextSourceCompositionError("source slices must be a list")
    if not slices:
        raise GraphContextSourceCompositionError("at least one source slice is required")
    for value, field_name in (
        (project_id, "project_id"),
        (graph_projection_id, "graph_projection_id"),
    ):
        if not isinstance(value, str) or not _ID_RE.fullmatch(value):
            raise GraphContextSourceCompositionError(f"{field_name} must be a safe ID")
    for value, field_name, upper in (
        (max_sources, "max_sources", MAX_SOURCES),
        (max_nodes, "max_nodes", MAX_NODES),
        (max_edges, "max_edges", MAX_EDGES),
    ):
        if type(value) is not int or not 1 <= value <= upper:
            raise GraphContextSourceCompositionError(
                f"{field_name} must be an integer from 1 through {upper}"
            )


def _prepare_sources(
    slices: Sequence[Mapping[str, Any]], project_id: str, max_sources: int
) -> list[dict[str, Any]]:
    if len(slices) > max_sources:
        raise GraphContextSourceCompositionError("source slices exceed max_sources")
    result: list[dict[str, Any]] = []
    for index, source in enumerate(slices):
        if not isinstance(source, Mapping):
            raise GraphContextSourceCompositionError(
                f"source slice at index {index} must be an object"
            )
        prepared = dict(source)
        if prepared.get("project_id") != project_id:
            raise GraphContextSourceCompositionError("source slice project does not match")
        try:
            build_graph_context_selection(
                prepared,
                reader="source-composition",
                decision_needed="validate source slice",
                max_candidates=MAX_NODES,
            )
        except GraphContextSelectionError as exc:
            raise GraphContextSourceCompositionError(
                "source slice failed the existing graph contract"
            ) from exc
        result.append(prepared)
    return result


def _merge_nodes(
    sources: Sequence[dict[str, Any]], max_nodes: int
) -> tuple[
    list[dict[str, Any]],
    list[str],
    list[dict[str, str]],
    list[dict[str, str]],
    list[dict[str, Any]],
    int,
    dict[str, dict[str, Any]],
]:
    state = _NodeMergeState()
    for source in sources:
        _merge_node_source(state, source)
    if len(state.selected_ids) > max_nodes:
        raise GraphContextSourceCompositionError("selected nodes exceed max_nodes")
    included_ids = _included_node_ids(state, max_nodes)
    included = {node_id for node_id in included_ids}
    dropped = [
        {"id": node_id, "reason": "node_limit"}
        for node_id in state.order
        if node_id not in included
    ]
    provenance_rows = [
        {"node_id": node_id, "source_projection_ids": state.provenance[node_id]}
        for node_id in included_ids
    ][:MAX_PROVENANCE]
    return (
        [state.nodes[node_id] for node_id in included_ids],
        state.selected_ids,
        dropped,
        state.conflicts,
        provenance_rows,
        state.redacted_count,
        {node_id: state.nodes[node_id] for node_id in included_ids},
    )


def _merge_node_source(state: _NodeMergeState, source: dict[str, Any]) -> None:
    source_id = str(source["graph_projection_id"])
    for node_id in source["selected_node_ids"]:
        if node_id not in state.selected_seen:
            state.selected_ids.append(node_id)
            state.selected_seen.add(node_id)
    for raw_node in source["nodes"]:
        node, redacted = _sanitize_node(raw_node)
        state.redacted_count += redacted
        node_id = node["id"]
        if node_id not in state.nodes:
            state.nodes[node_id] = node
            state.order.append(node_id)
        else:
            _merge_node(state.nodes[node_id], node, source_id, state.conflicts)
        state.provenance.setdefault(node_id, [])
        if source_id not in state.provenance[node_id]:
            state.provenance[node_id].append(source_id)


def _included_node_ids(state: _NodeMergeState, max_nodes: int) -> list[str]:
    return state.selected_ids + [
        node_id for node_id in state.order if node_id not in state.selected_seen
    ][: max_nodes - len(state.selected_ids)]


def _sanitize_node(raw: object) -> tuple[dict[str, Any], int]:
    if not isinstance(raw, Mapping):
        raise GraphContextSourceCompositionError("graph node must be an object")
    node_id = _safe_id(raw.get("id"), "node.id")
    node_type = raw.get("type")
    authority = raw.get("authority")
    privacy = raw.get("privacy_class", "unknown")
    if node_type not in NODE_TYPES or authority not in AUTHORITY_LABELS:
        raise GraphContextSourceCompositionError("graph node shape is invalid")
    if privacy not in PRIVACY_CLASSES or privacy == "forbidden":
        raise GraphContextSourceCompositionError("graph node privacy is invalid")
    freshness = raw.get("freshness", "unknown")
    if freshness not in FRESHNESS_STATES:
        freshness = "unknown"
    result: dict[str, Any] = {
        "id": node_id,
        "type": node_type,
        "authority": authority,
        "privacy_class": privacy,
        "freshness": freshness,
    }
    redacted = 0
    if privacy == "public_repo":
        redacted += _copy_safe_text(raw, result, "label")
        redacted += _copy_safe_text(raw, result, "source_kind")
        redacted += _copy_safe_ref(raw, result, "source_ref")
    else:
        redacted += sum(field in raw for field in ("label", "source_kind", "source_ref"))
    if "confidence" in raw:
        confidence = raw["confidence"]
        if (
            isinstance(confidence, (int, float))
            and not isinstance(confidence, bool)
            and isfinite(float(confidence))
            and 0 <= float(confidence) <= 1
        ):
            result["confidence"] = float(confidence)
        else:
            redacted += 1
    return result, redacted


def _merge_node(
    existing: dict[str, Any],
    incoming: dict[str, Any],
    source_id: str,
    conflicts: list[dict[str, str]],
) -> None:
    if existing["type"] != incoming["type"]:
        raise GraphContextSourceCompositionError("duplicate node type conflicts")
    node_id = str(existing["id"])
    for field in ("authority", "privacy_class", "freshness"):
        if existing[field] == incoming[field]:
            continue
        _record_conflict(conflicts, "node", node_id, field, source_id)
        if field == "authority":
            existing[field] = min(
                (existing[field], incoming[field]), key=lambda value: _AUTHORITY_RANK[value]
            )
        elif field == "freshness":
            existing[field] = min(
                (existing[field], incoming[field]), key=lambda value: _FRESHNESS_RANK[value]
            )
        else:
            existing[field] = max(
                (existing[field], incoming[field]), key=lambda value: _PRIVACY_RANK[value]
            )
    for field in ("label", "source_kind", "source_ref"):
        _merge_optional_field(existing, incoming, field, node_id, source_id, conflicts)
    _merge_confidence(existing, incoming, node_id, source_id, conflicts)
    if existing["privacy_class"] != "public_repo":
        for field in ("label", "source_kind", "source_ref"):
            if field in existing:
                existing.pop(field)


def _merge_optional_field(
    existing: dict[str, Any],
    incoming: dict[str, Any],
    field: str,
    item_id: str,
    source_id: str,
    conflicts: list[dict[str, str]],
) -> None:
    old = existing.get(field)
    new = incoming.get(field)
    if old == new:
        return
    if old is not None and new is not None:
        existing.pop(field, None)
        _record_conflict(conflicts, "node", item_id, field, source_id)
        return
    if old is None and new is not None:
        existing[field] = new
        _record_conflict(conflicts, "node", item_id, field, source_id)


def _merge_confidence(
    existing: dict[str, Any],
    incoming: dict[str, Any],
    item_id: str,
    source_id: str,
    conflicts: list[dict[str, str]],
) -> None:
    old = existing.get("confidence")
    new = incoming.get("confidence")
    if old is None and new is None:
        return
    if old is None:
        existing["confidence"] = new
        return
    if new is None:
        return
    if old != new:
        _record_conflict(conflicts, "node", item_id, "confidence", source_id)
    existing["confidence"] = min(float(old), float(new))


def _merge_edges(
    sources: Sequence[dict[str, Any]],
    included_nodes: set[str],
    max_edges: int,
) -> tuple[list[dict[str, Any]], list[dict[str, str]], list[dict[str, str]], int]:
    edges: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    conflicts: list[dict[str, str]] = []
    redacted_count = 0
    for source in sources:
        source_id = str(source["graph_projection_id"])
        for raw_edge in source.get("edges", []):
            edge, redacted = _sanitize_edge(raw_edge)
            redacted_count += redacted
            edge_id = edge["id"]
            if edge_id not in edges:
                edges[edge_id] = edge
                order.append(edge_id)
            else:
                _merge_edge(edges[edge_id], edge, source_id, conflicts)
    result: list[dict[str, Any]] = []
    omitted: list[dict[str, str]] = []
    for edge_id in order:
        edge = edges[edge_id]
        if edge["source"] not in included_nodes or edge["target"] not in included_nodes:
            omitted.append({"id": edge_id, "reason": "endpoint_omitted"})
        elif len(result) >= max_edges:
            omitted.append({"id": edge_id, "reason": "edge_limit"})
        else:
            result.append(edge)
    return result, omitted, conflicts, redacted_count


def _sanitize_edge(raw: object) -> tuple[dict[str, Any], int]:
    if not isinstance(raw, Mapping):
        raise GraphContextSourceCompositionError("graph edge must be an object")
    edge_id = _safe_id(raw.get("id"), "edge.id")
    source = _safe_id(raw.get("source"), "edge.source")
    target = _safe_id(raw.get("target"), "edge.target")
    edge_type = raw.get("type")
    privacy = raw.get("privacy_class", "unknown")
    if edge_type not in EDGE_TYPES or privacy not in PRIVACY_CLASSES or privacy == "forbidden":
        raise GraphContextSourceCompositionError("graph edge shape is invalid")
    result: dict[str, Any] = {
        "id": edge_id,
        "source": source,
        "target": target,
        "type": edge_type,
        "privacy_class": privacy,
    }
    redacted = 0
    if edge_type == "cited":
        citation = _safe_ref(raw.get("citation_source"))
        if citation is None:
            raise GraphContextSourceCompositionError("cited edge citation is invalid")
        result["citation_source"] = citation
    redacted += _copy_safe_ref(raw, result, "source_ref")
    if "confidence" in raw:
        confidence = raw["confidence"]
        if (
            isinstance(confidence, (int, float))
            and not isinstance(confidence, bool)
            and isfinite(float(confidence))
            and 0 <= float(confidence) <= 1
        ):
            result["confidence"] = float(confidence)
        else:
            redacted += 1
    return result, redacted


def _merge_edge(
    existing: dict[str, Any],
    incoming: dict[str, Any],
    source_id: str,
    conflicts: list[dict[str, str]],
) -> None:
    edge_id = str(existing["id"])
    for field in ("source", "target", "type"):
        if existing[field] != incoming[field]:
            raise GraphContextSourceCompositionError("duplicate edge identity conflicts")
    for field in ("privacy_class",):
        if existing[field] != incoming[field]:
            _record_conflict(conflicts, "edge", edge_id, field, source_id)
            existing[field] = max(
                (existing[field], incoming[field]), key=lambda value: _PRIVACY_RANK[value]
            )
    _merge_optional_field(existing, incoming, "source_ref", edge_id, source_id, conflicts)
    if existing.get("citation_source") != incoming.get("citation_source"):
        if existing.get("citation_source") and incoming.get("citation_source"):
            raise GraphContextSourceCompositionError("duplicate cited edge citation conflicts")
        if incoming.get("citation_source"):
            existing["citation_source"] = incoming["citation_source"]
    _merge_confidence(existing, incoming, edge_id, source_id, conflicts)


def _merge_omissions(
    sources: Sequence[dict[str, Any]],
    field_name: str,
    included_ids: set[str],
) -> list[dict[str, str]]:
    result: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for source in sources:
        for item in source.get(field_name, []):
            item_id = str(item["id"])
            reason = str(item["reason"])
            if item_id in included_ids or (item_id, reason) in seen:
                continue
            if reason not in OMISSION_REASONS:
                continue
            result.append({"id": item_id, "reason": reason})
            seen.add((item_id, reason))
    return result


def _compose_omissions(
    sources: Sequence[dict[str, Any]],
    node_by_id: Mapping[str, dict[str, Any]],
    edges: Sequence[dict[str, Any]],
    dropped_nodes: Sequence[dict[str, str]],
    dropped_edges: Sequence[dict[str, str]],
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    included_nodes = set(node_by_id)
    omitted_neighbors = _merge_omissions(
        sources, "omitted_neighbors", included_nodes
    )
    omitted_neighbors.extend(dropped_nodes)
    included_edges = {edge["id"] for edge in edges}
    omitted_edges = _merge_omissions(sources, "omitted_edges", included_edges)
    omitted_edges.extend(dropped_edges)
    return (
        _dedupe_omissions(omitted_neighbors),
        _dedupe_omissions(omitted_edges),
    )


def _dedupe_omissions(items: Sequence[dict[str, str]]) -> list[dict[str, str]]:
    result: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for item in items:
        key = (item["id"], item["reason"])
        if key not in seen:
            result.append({"id": key[0], "reason": key[1]})
            seen.add(key)
    return result


def _assemble_projection(
    *,
    project_id: str,
    graph_projection_id: str,
    sources: Sequence[dict[str, Any]],
    selected_ids: list[str],
    nodes: list[dict[str, Any]],
    edges: list[dict[str, Any]],
    omitted_neighbors: list[dict[str, str]],
    omitted_edges: list[dict[str, str]],
    conflicts: list[dict[str, str]],
    provenance: list[dict[str, Any]],
    redacted_count: int,
) -> dict[str, Any]:
    metadata = _projection_metadata(
        sources,
        nodes,
        edges,
        omitted_neighbors,
        omitted_edges,
        redacted_count,
    )
    metadata["summaries"]["validation_summary"]["selected_node_count"] = len(
        selected_ids
    )
    return {
        "graph_projection_id": graph_projection_id,
        "project_id": project_id,
        "selected_node_ids": list(selected_ids),
        **metadata["identity"],
        "nodes": nodes,
        "edges": edges,
        "omitted_neighbors": omitted_neighbors,
        "omitted_edges": omitted_edges,
        "operations": ["project", "query", "seed_context"],
        **metadata["summaries"],
        "source_provenance": provenance,
        "source_conflicts": conflicts,
    }


def _projection_metadata(
    sources: Sequence[dict[str, Any]],
    nodes: Sequence[dict[str, Any]],
    edges: Sequence[dict[str, Any]],
    omitted_neighbors: Sequence[dict[str, str]],
    omitted_edges: Sequence[dict[str, str]],
    redacted_count: int,
) -> dict[str, dict[str, Any]]:
    node_classes = {privacy: 0 for privacy in PRIVACY_CLASSES}
    edge_classes = {privacy: 0 for privacy in PRIVACY_CLASSES}
    for node in nodes:
        node_classes[node["privacy_class"]] += 1
    for edge in edges:
        edge_classes[edge["privacy_class"]] += 1
    source_ids = _unique_source_ids(sources)
    return {
        "identity": {
            "source_snapshot_refs": [
                f"graph://projection/{source_id}" for source_id in source_ids
            ]
        },
        "summaries": {
            "privacy_summary": {
                "node_classes": node_classes,
                "edge_classes": edge_classes,
                "redacted_field_count": min(redacted_count, 65535),
            },
            "validation_summary": {
                "source_valid": True,
                "bounded": True,
                "source_count": len(sources),
                "included_node_count": len(nodes),
                "included_edge_count": len(edges),
                "omitted_neighbor_count": len(omitted_neighbors),
                "omitted_edge_count": len(omitted_edges),
            },
            "source_adapter": {
                "id": "graph-source-composition.0.1",
                "input": "explicit_validated_graph_slices",
                "read_only": True,
            },
        },
    }


def _unique_source_ids(sources: Sequence[dict[str, Any]]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for source in sources:
        source_id = str(source["graph_projection_id"])
        if source_id not in seen:
            result.append(source_id)
            seen.add(source_id)
    return result


def _copy_safe_text(raw: Mapping[str, Any], target: dict[str, Any], field: str) -> int:
    if field not in raw:
        return 0
    value = _safe_text(raw[field])
    if value is None:
        return 1
    target[field] = value
    return 0


def _copy_safe_ref(raw: Mapping[str, Any], target: dict[str, Any], field: str) -> int:
    if field not in raw:
        return 0
    value = _safe_ref(raw[field])
    if value is None:
        return 1
    target[field] = value
    return 0


def _safe_id(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not _ID_RE.fullmatch(value):
        raise GraphContextSourceCompositionError(f"{field_name} must be a safe ID")
    return value


def _safe_text(value: object) -> str | None:
    if not isinstance(value, str) or not value or len(value) > MAX_TEXT_LENGTH:
        return None
    if _SENSITIVE_RE.search(value) or "\\" in value or any(ord(char) < 32 for char in value):
        return None
    if value.startswith(("/", "\\")) or re.match(r"^[A-Za-z]:[\\/]", value):
        return None
    return value


def _safe_ref(value: object) -> str | None:
    if not isinstance(value, str) or not value or len(value) > MAX_REF_LENGTH:
        return None
    if _SENSITIVE_RE.search(value) or "\\" in value or ".." in value:
        return None
    match = _REF_RE.fullmatch(value)
    if match is None or match.group("scheme") not in _PUBLIC_REF_SCHEMES:
        return None
    return value


def _record_conflict(
    conflicts: list[dict[str, str]],
    kind: str,
    item_id: str,
    field: str,
    source_id: str,
) -> None:
    if len(conflicts) >= MAX_CONFLICTS:
        return
    conflicts.append(
        {
            "kind": kind,
            "id": item_id,
            "field": field,
            "source_projection_id": source_id,
            "resolution": "conservative",
        }
    )


__all__ = [
    "GraphContextSourceCompositionError",
    "compose_graph_context_sources",
]
