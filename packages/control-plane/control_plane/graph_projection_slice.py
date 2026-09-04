"""Build bounded, read-only slices from an explicit graph projection.

The builder is deliberately an in-memory adapter.  It does not discover graph
data, read files, persist a projection, or make graph facts authoritative.  A
caller must provide the source projection and the node IDs to inspect.
"""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from math import isfinite
import re
from typing import Any

from .graph_projection_validator import validate_graph_projection


PRIVACY_CLASSES: tuple[str, ...] = (
    "public_repo",
    "local_path_only",
    "private_content_summary",
    "sensitive_redacted",
    "forbidden",
    "unknown",
)

EDGE_AUTHORITY_LABELS: tuple[str, ...] = (
    "source_truth",
    "governed_decision",
    "evidence_backed",
    "human_annotation",
    "agent_proposal",
    "inferred",
    "unknown",
)

PUBLIC_REF_SCHEMES: tuple[str, ...] = (
    "repo",
    "doc",
    "artifact",
    "decision",
    "evidence",
    "run",
    "skill",
    "code",
    "paper",
    "project",
    "review",
)

DEFAULT_MAX_NODES = 64
DEFAULT_MAX_EDGES = 128
MAX_NODE_LIMIT = 512
MAX_EDGE_LIMIT = 2048
MAX_SOURCE_NODES = 4096
MAX_SOURCE_EDGES = 8192
MAX_SOURCE_OPERATIONS = 128
MAX_SOURCE_SNAPSHOT_REFS = 256
MAX_REFERENCE_ITEMS = 128
MAX_ID_LENGTH = 128
MAX_TEXT_LENGTH = 256
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


class GraphSliceError(ValueError):
    """Raised when a graph slice cannot be built safely."""

    def __init__(self, message: str, errors: Sequence[str] = ()) -> None:
        self.errors = tuple(str(error) for error in errors if str(error))
        detail = "; ".join(self.errors[:8])
        super().__init__(f"{message}: {detail}" if detail else message)


@dataclass(frozen=True)
class _GraphSource:
    graph_projection_id: str
    project_id: str
    nodes: list[Any]
    edges: list[dict[str, Any]]
    operations: list[Any]
    node_by_id: dict[str, dict[str, Any]]
    node_order: list[str]
    node_privacy: dict[str, str]


def build_graph_slice(
    payload: dict[str, Any],
    selected_node_ids: Sequence[str],
    *,
    include_neighbors: bool = True,
    max_nodes: int = DEFAULT_MAX_NODES,
    max_edges: int = DEFAULT_MAX_EDGES,
) -> dict[str, Any]:
    """Return a deterministic one-hop graph slice from an explicit payload.

    Selected nodes are emitted first, in the order supplied by the caller.
    Neighbor nodes follow source-payload order.  Forbidden neighbors and any
    source fields that are not safe to export are omitted with bounded reasons.
    The source payload is never modified.
    """
    _validate_arguments(
        payload,
        selected_node_ids,
        include_neighbors=include_neighbors,
        max_nodes=max_nodes,
        max_edges=max_edges,
    )

    source = _prepare_source(payload)
    selected_ids = _select_nodes(
        source, selected_node_ids, max_nodes=max_nodes
    )
    included_ids, omitted_neighbors = _expand_nodes(
        source,
        selected_ids,
        include_neighbors=include_neighbors,
        max_nodes=max_nodes,
    )
    projected_nodes, node_redactions = _project_nodes(source, included_ids)
    projected_edges, omitted_edges, edge_redactions = _project_edges(
        source.edges, set(included_ids), max_edges=max_edges
    )
    metadata, metadata_redactions = _project_metadata(payload)
    total_redactions = node_redactions + edge_redactions + metadata_redactions
    return _assemble_slice(
        source,
        selected_ids,
        projected_nodes,
        projected_edges,
        omitted_neighbors,
        omitted_edges,
        total_redactions,
        metadata,
    )


def _prepare_source(payload: dict[str, Any]) -> _GraphSource:
    graph_projection_id = _require_id(
        payload.get("graph_projection_id"), "graph_projection_id"
    )
    project_id = _require_id(payload.get("project_id"), "project_id")
    nodes = _require_list(payload, "nodes")
    edges = _require_list(payload, "edges")
    operations = _require_list(payload, "operations", default=[])
    _validate_optional_list(payload, "source_snapshot_refs")
    _validate_source_limits(nodes, edges, operations, payload)

    node_by_id, node_order, node_privacy = _index_nodes(nodes)
    edge_records = _index_edges(edges)
    source_validation = validate_graph_projection(payload)
    if not source_validation.valid:
        raise GraphSliceError(
            "source projection is invalid",
            _safe_validation_errors(source_validation.errors),
        )
    return _GraphSource(
        graph_projection_id,
        project_id,
        nodes,
        edge_records,
        operations,
        node_by_id,
        node_order,
        node_privacy,
    )


def _select_nodes(
    source: _GraphSource,
    selected_node_ids: Sequence[str],
    *,
    max_nodes: int,
) -> list[str]:
    selected_ids = _normalize_selected_ids(selected_node_ids)
    if len(selected_ids) > max_nodes:
        raise GraphSliceError(
            f"selected nodes exceed max_nodes={max_nodes}; selection is too large"
        )
    for node_id in selected_ids:
        if node_id not in source.node_by_id:
            raise GraphSliceError(f"unknown selected node: {node_id}")
        if source.node_privacy[node_id] == "forbidden":
            raise GraphSliceError(
                f"selected node has forbidden privacy: {node_id}"
            )
    return selected_ids


def _expand_nodes(
    source: _GraphSource,
    selected_ids: list[str],
    *,
    include_neighbors: bool,
    max_nodes: int,
) -> tuple[list[str], list[dict[str, str]]]:
    selected_set = set(selected_ids)
    neighbor_ids = _ordered_neighbor_ids(
        source.node_order, selected_set, source.edges
    )
    included_ids = list(selected_ids)
    included_set = set(included_ids)
    omitted_neighbors: list[dict[str, str]] = []
    for neighbor_id in neighbor_ids:
        if neighbor_id in included_set:
            continue
        reason = _neighbor_omission_reason(
            source.node_privacy[neighbor_id],
            include_neighbors=include_neighbors,
            at_capacity=len(included_ids) >= max_nodes,
        )
        if reason:
            omitted_neighbors.append({"id": neighbor_id, "reason": reason})
            continue
        included_ids.append(neighbor_id)
        included_set.add(neighbor_id)
    return included_ids, omitted_neighbors


def _neighbor_omission_reason(
    privacy_class: str, *, include_neighbors: bool, at_capacity: bool
) -> str | None:
    if privacy_class == "forbidden":
        return "forbidden_privacy"
    if not include_neighbors:
        return "neighbors_disabled"
    if at_capacity:
        return "node_limit"
    return None


def _project_nodes(
    source: _GraphSource, included_ids: list[str]
) -> tuple[list[dict[str, Any]], int]:
    projected_nodes: list[dict[str, Any]] = []
    redacted = 0
    for node_id in included_ids:
        projected, node_redactions = _project_node(
            source.node_by_id[node_id], source.node_privacy[node_id]
        )
        projected_nodes.append(projected)
        redacted += node_redactions
    return projected_nodes, redacted


def _project_edges(
    edges: list[dict[str, Any]],
    included_ids: set[str],
    *,
    max_edges: int,
) -> tuple[list[dict[str, Any]], list[dict[str, str]], int]:
    projected_edges: list[dict[str, Any]] = []
    omitted_edges: list[dict[str, str]] = []
    redacted = 0
    for edge in edges:
        source_included = edge["source"] in included_ids
        target_included = edge["target"] in included_ids
        if not (source_included or target_included):
            continue
        if not (source_included and target_included):
            omitted_edges.append(
                {"id": edge["id"], "reason": "endpoint_omitted"}
            )
            continue
        if edge["privacy_class"] == "forbidden":
            omitted_edges.append(
                {"id": edge["id"], "reason": "forbidden_privacy"}
            )
            continue
        if len(projected_edges) >= max_edges:
            omitted_edges.append(
                {"id": edge["id"], "reason": "edge_limit"}
            )
            continue
        projected, edge_redactions = _project_edge(edge)
        projected_edges.append(projected)
        redacted += edge_redactions
    return projected_edges, omitted_edges, redacted


def _project_metadata(
    payload: dict[str, Any]
) -> tuple[dict[str, Any], int]:
    metadata: dict[str, Any] = {"source_snapshot_refs": []}
    redacted = 0
    for value in payload.get("source_snapshot_refs", []):
        safe_ref = _safe_public_ref(value)
        if safe_ref is None:
            redacted += 1
        else:
            metadata["source_snapshot_refs"].append(safe_ref)
    for field_name in ("created_at", "scope"):
        value = payload.get(field_name)
        if value is None:
            continue
        safe_value = _safe_text(value)
        if safe_value is None:
            redacted += 1
        else:
            metadata[field_name] = safe_value
    return metadata, redacted


def _assemble_slice(
    source: _GraphSource,
    selected_ids: list[str],
    projected_nodes: list[dict[str, Any]],
    projected_edges: list[dict[str, Any]],
    omitted_neighbors: list[dict[str, str]],
    omitted_edges: list[dict[str, str]],
    redacted_field_count: int,
    metadata: dict[str, Any],
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "graph_projection_id": source.graph_projection_id,
        "project_id": source.project_id,
        "selected_node_ids": list(selected_ids),
        **metadata,
        "nodes": projected_nodes,
        "edges": projected_edges,
        "omitted_neighbors": omitted_neighbors,
        "omitted_edges": omitted_edges,
        "privacy_summary": _privacy_summary(
            projected_nodes,
            projected_edges,
            omitted_neighbors,
            omitted_edges,
            redacted_field_count,
        ),
        "validation_summary": {
            "source_valid": True,
            "source_operation_count": len(source.operations),
            "selected_node_count": len(selected_ids),
            "included_node_count": len(projected_nodes),
            "included_edge_count": len(projected_edges),
            "neighbors_included": len(projected_nodes) - len(selected_ids),
            "omitted_neighbor_count": len(omitted_neighbors),
            "omitted_edge_count": len(omitted_edges),
            "bounded": True,
        },
    }
    return result


def render_graph_slice_summary(slice_payload: dict[str, Any]) -> str:
    """Render a bounded human-readable summary without copying source text."""
    if not isinstance(slice_payload, dict):
        raise GraphSliceError("graph slice must be an object")

    graph_id = _safe_display_id(slice_payload.get("graph_projection_id"))
    project_id = _safe_display_id(slice_payload.get("project_id"))
    nodes = slice_payload.get("nodes")
    edges = slice_payload.get("edges")
    selected = slice_payload.get("selected_node_ids")
    omitted_neighbors = slice_payload.get("omitted_neighbors")
    omitted_edges = slice_payload.get("omitted_edges")
    lines = [
        "# Graph Projection Slice",
        "",
        f"- graph_projection_id: {graph_id}",
        f"- project_id: {project_id}",
        f"- nodes: {_bounded_count(nodes)}",
        f"- edges: {_bounded_count(edges)}",
        f"- selected: {_display_id_list(selected)}",
        "- omitted_neighbors:",
    ]
    lines.extend(_render_omissions(omitted_neighbors))
    lines.append("- omitted_edges:")
    lines.extend(_render_omissions(omitted_edges))
    privacy = slice_payload.get("privacy_summary")
    redacted = 0
    if isinstance(privacy, dict):
        redacted = _bounded_count(privacy.get("redacted_field_count"))
    lines.append(f"- redacted_fields: {redacted}")
    return "\n".join(lines) + "\n"


def _validate_arguments(
    payload: object,
    selected_node_ids: object,
    *,
    include_neighbors: object,
    max_nodes: object,
    max_edges: object,
) -> None:
    if not isinstance(payload, dict):
        raise GraphSliceError("source projection is invalid: payload must be an object")
    if not isinstance(selected_node_ids, (list, tuple)):
        raise GraphSliceError("selected node IDs must be a list or tuple")
    if not selected_node_ids:
        raise GraphSliceError("at least one selected node is required")
    if type(include_neighbors) is not bool:
        raise GraphSliceError("include_neighbors must be a boolean")
    _validate_limit(max_nodes, "max_nodes", MAX_NODE_LIMIT)
    _validate_limit(max_edges, "max_edges", MAX_EDGE_LIMIT)


def _validate_limit(value: object, name: str, upper_bound: int) -> None:
    if type(value) is not int or value < 1 or value > upper_bound:
        raise GraphSliceError(
            f"{name} must be an integer from 1 through {upper_bound}"
        )


def _require_list(
    payload: dict[str, Any], name: str, *, default: list[Any] | None = None
) -> list[Any]:
    if name not in payload:
        if default is not None:
            return default
        raise GraphSliceError(f"source projection is invalid: {name} must be a list")
    value = payload[name]
    if not isinstance(value, list):
        raise GraphSliceError(f"source projection is invalid: {name} must be a list")
    return value


def _validate_optional_list(payload: dict[str, Any], name: str) -> None:
    if name in payload and not isinstance(payload[name], list):
        raise GraphSliceError(f"source projection is invalid: {name} must be a list")


def _validate_source_limits(
    nodes: list[Any],
    edges: list[Any],
    operations: list[Any],
    payload: dict[str, Any],
) -> None:
    limits = (
        (len(nodes), MAX_SOURCE_NODES, "source nodes"),
        (len(edges), MAX_SOURCE_EDGES, "source edges"),
        (len(operations), MAX_SOURCE_OPERATIONS, "source operations"),
    )
    for count, limit, label in limits:
        if count > limit:
            raise GraphSliceError(f"{label} exceed hard limit {limit}")
    snapshots = payload.get("source_snapshot_refs", [])
    if len(snapshots) > MAX_SOURCE_SNAPSHOT_REFS:
        raise GraphSliceError(
            "source snapshot refs exceed hard limit "
            f"{MAX_SOURCE_SNAPSHOT_REFS}"
        )


def _safe_validation_errors(errors: Sequence[str]) -> tuple[str, ...]:
    safe_errors: list[str] = []
    for error in errors[:8]:
        safe_error = _safe_text(error)
        if safe_error is not None:
            safe_errors.append(safe_error)
    return tuple(safe_errors)


def _require_id(value: object, field_name: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) > MAX_ID_LENGTH
        or not _ID_RE.fullmatch(value)
    ):
        raise GraphSliceError(
            f"source projection is invalid: {field_name} must be an opaque ID"
        )
    return value


def _normalize_selected_ids(values: Sequence[str]) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for index, value in enumerate(values):
        if not isinstance(value, str):
            raise GraphSliceError(
                f"selected node at index {index} must be an opaque ID"
            )
        node_id = _require_id(value, f"selected_node_ids[{index}]")
        if node_id in seen:
            raise GraphSliceError(f"duplicate selected node: {node_id}")
        seen.add(node_id)
        normalized.append(node_id)
    return normalized


def _index_nodes(
    nodes: list[Any],
) -> tuple[dict[str, dict[str, Any]], list[str], dict[str, str]]:
    node_by_id: dict[str, dict[str, Any]] = {}
    node_order: list[str] = []
    privacy_by_id: dict[str, str] = {}
    for index, node in enumerate(nodes):
        if not isinstance(node, dict):
            raise GraphSliceError(
                f"source projection is invalid: node at index {index} is not an object"
            )
        node_id = _require_id(node.get("id"), f"nodes[{index}].id")
        if node_id in node_by_id:
            raise GraphSliceError(f"source projection has duplicate node: {node_id}")
        privacy_class = _privacy_class(node.get("privacy_class"))
        node_by_id[node_id] = node
        node_order.append(node_id)
        privacy_by_id[node_id] = privacy_class
    return node_by_id, node_order, privacy_by_id


def _index_edges(edges: list[Any]) -> list[dict[str, Any]]:
    indexed: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, edge in enumerate(edges):
        if not isinstance(edge, dict):
            raise GraphSliceError(
                f"source projection is invalid: edge at index {index} is not an object"
            )
        edge_id = _require_id(edge.get("id"), f"edges[{index}].id")
        if edge_id in seen:
            raise GraphSliceError(f"source projection has duplicate edge: {edge_id}")
        source = _require_id(edge.get("source"), f"edges[{index}].source")
        target = _require_id(edge.get("target"), f"edges[{index}].target")
        edge_type = edge.get("type")
        if not isinstance(edge_type, str) or not edge_type.strip():
            raise GraphSliceError(
                f"source projection is invalid: edges[{index}].type is required"
            )
        indexed.append(
            {
                "id": edge_id,
                "source": source,
                "target": target,
                "type": edge_type.strip(),
                "privacy_class": _privacy_class(edge.get("privacy_class")),
                "raw": edge,
            }
        )
        seen.add(edge_id)
    return indexed


def _privacy_class(value: object) -> str:
    if value is None:
        return "unknown"
    if not isinstance(value, str) or value not in PRIVACY_CLASSES:
        raise GraphSliceError(
            "source projection is invalid: privacy_class is not recognized"
        )
    return value


def _ordered_neighbor_ids(
    node_order: list[str],
    selected: set[str],
    edges: list[dict[str, Any]],
) -> list[str]:
    candidates: set[str] = set()
    for edge in edges:
        source = edge["source"]
        target = edge["target"]
        if source in selected and target not in selected:
            candidates.add(target)
        if target in selected and source not in selected:
            candidates.add(source)
    return [node_id for node_id in node_order if node_id in candidates]


def _project_node(
    node: dict[str, Any], privacy_class: str
) -> tuple[dict[str, Any], int]:
    projected: dict[str, Any] = {
        "id": str(node["id"]),
        "type": str(node["type"]).strip(),
        "authority": str(node["authority"]).strip(),
        "privacy_class": privacy_class,
    }
    if privacy_class == "public_repo":
        redacted = _project_public_node_fields(node, projected)
    else:
        # Private labels and local refs are deliberately not projected.  Their
        # presence is summarized, but the content is never copied.
        redacted = _private_node_redactions(node)
    redacted += _project_confidence(node, projected)
    redacted += _project_reference_fields(node, projected)
    return projected, redacted


def _project_public_node_fields(
    node: dict[str, Any], projected: dict[str, Any]
) -> int:
    redacted = 0
    for field_name in ("label", "source_kind", "freshness"):
        if field_name not in node:
            continue
        safe_value = _safe_text(node[field_name])
        if safe_value is None:
            redacted += 1
        else:
            projected[field_name] = safe_value
    if "source_ref" in node:
        safe_ref = _safe_public_ref(node["source_ref"])
        if safe_ref is None:
            redacted += 1
        else:
            projected["source_ref"] = safe_ref
    return redacted


def _private_node_redactions(node: dict[str, Any]) -> int:
    return sum(field_name in node for field_name in ("label", "source_ref"))


def _project_confidence(
    source: dict[str, Any], projected: dict[str, Any]
) -> int:
    if "confidence" not in source:
        return 0
    confidence = source["confidence"]
    if (
        isinstance(confidence, (int, float))
        and not isinstance(confidence, bool)
        and isfinite(float(confidence))
        and 0 <= float(confidence) <= 1
    ):
        projected["confidence"] = float(confidence)
        return 0
    return 1


def _project_reference_fields(
    source: dict[str, Any], projected: dict[str, Any]
) -> int:
    redacted = 0
    for field_name in ("evidence_refs", "decision_refs", "provenance"):
        if field_name not in source:
            continue
        references = _safe_reference_list(source[field_name])
        if references is None:
            redacted += 1
        else:
            projected[field_name] = references
    return redacted


def _project_edge(edge: dict[str, Any]) -> tuple[dict[str, Any], int]:
    raw = edge["raw"]
    projected: dict[str, Any] = {
        "id": edge["id"],
        "source": edge["source"],
        "target": edge["target"],
        "type": edge["type"],
        "privacy_class": edge["privacy_class"],
    }
    redacted = 0
    authority = raw.get("authority")
    if authority in EDGE_AUTHORITY_LABELS:
        projected["authority"] = authority

    if "source_ref" in raw:
        safe_ref = _safe_public_ref(raw["source_ref"])
        if edge["privacy_class"] == "public_repo" and safe_ref is not None:
            projected["source_ref"] = safe_ref
        else:
            redacted += 1
    if edge["type"] == "cited" and "citation_source" in raw:
        safe_citation = _safe_reference(raw["citation_source"])
        if safe_citation is not None:
            projected["citation_source"] = safe_citation
        else:
            redacted += 1
    redacted += _project_reference_fields(raw, projected)
    redacted += _project_confidence(raw, projected)
    return projected, redacted


def _safe_reference_list(value: object) -> list[str] | None:
    if not isinstance(value, list) or len(value) > MAX_REFERENCE_ITEMS:
        return None
    result: list[str] = []
    for item in value:
        safe_item = _safe_reference(item)
        if safe_item is None:
            return None
        if safe_item not in result:
            result.append(safe_item)
    return result


def _safe_reference(value: object) -> str | None:
    if not isinstance(value, str) or not value or len(value) > MAX_REF_LENGTH:
        return None
    if _SENSITIVE_RE.search(value):
        return None
    if _ID_RE.fullmatch(value):
        return value
    match = _REF_RE.fullmatch(value)
    if match is None:
        return None
    if ".." in value or "\\" in value or any(ord(char) < 32 for char in value):
        return None
    return value


def _safe_public_ref(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    match = _REF_RE.fullmatch(value)
    if match is None or match.group("scheme") not in PUBLIC_REF_SCHEMES:
        return None
    return _safe_reference(value)


def _safe_text(value: object) -> str | None:
    if not isinstance(value, str) or not value or len(value) > MAX_TEXT_LENGTH:
        return None
    if _SENSITIVE_RE.search(value):
        return None
    if "\\" in value or any(ord(char) < 32 for char in value):
        return None
    return value


def _privacy_summary(
    nodes: list[dict[str, Any]],
    edges: list[dict[str, Any]],
    omitted_neighbors: list[dict[str, str]],
    omitted_edges: list[dict[str, str]],
    redacted_field_count: int,
) -> dict[str, Any]:
    node_classes = {privacy: 0 for privacy in PRIVACY_CLASSES}
    edge_classes = {privacy: 0 for privacy in PRIVACY_CLASSES}
    for node in nodes:
        node_classes[node["privacy_class"]] += 1
    for edge in edges:
        edge_classes[edge["privacy_class"]] += 1
    forbidden_nodes = sum(
        1 for item in omitted_neighbors if item["reason"] == "forbidden_privacy"
    )
    forbidden_edges = sum(
        1 for item in omitted_edges if item["reason"] == "forbidden_privacy"
    )
    return {
        "node_classes": node_classes,
        "edge_classes": edge_classes,
        "omitted_forbidden_nodes": forbidden_nodes,
        "omitted_forbidden_edges": forbidden_edges,
        "redacted_field_count": redacted_field_count,
    }


def _safe_display_id(value: object) -> str:
    if isinstance(value, str) and _ID_RE.fullmatch(value):
        return value
    return "<redacted>"


def _display_id_list(value: object) -> str:
    if not isinstance(value, list):
        return "<none>"
    safe_ids = [
        _safe_display_id(item) for item in value[:MAX_NODE_LIMIT]
    ]
    return ", ".join(safe_ids) if safe_ids else "<none>"


def _bounded_count(value: object) -> int:
    if isinstance(value, bool):
        return 0
    if isinstance(value, int) and value >= 0:
        return min(value, MAX_EDGE_LIMIT)
    if isinstance(value, (list, tuple, dict, set)):
        return min(len(value), MAX_EDGE_LIMIT)
    return 0


def _render_omissions(value: object) -> list[str]:
    if not isinstance(value, list) or not value:
        return ["  - none"]
    lines: list[str] = []
    for item in value[:MAX_EDGE_LIMIT]:
        if not isinstance(item, dict):
            continue
        item_id = _safe_display_id(item.get("id"))
        reason = _safe_text(item.get("reason")) or "unknown"
        lines.append(f"  - {item_id}: {reason}")
    return lines or ["  - none"]


__all__ = [
    "GraphSliceError",
    "build_graph_slice",
    "render_graph_slice_summary",
]
