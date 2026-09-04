"""Map a validated graph slice into bounded context-selection metadata.

This module is intentionally not a context-packet writer.  It produces an
in-memory manifest that a later packet assembler may cite.  Graph output is a
read-model input: candidates are references, assumptions remain assumptions,
and no result can create a decision or final verdict.
"""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
import hashlib
import json
import re
from typing import Any


PRIVACY_CLASSES: tuple[str, ...] = (
    "public_repo",
    "local_path_only",
    "private_content_summary",
    "sensitive_redacted",
    "forbidden",
    "unknown",
)

NODE_TYPES: tuple[str, ...] = (
    "decision",
    "evidence",
    "artifact",
    "agent",
    "review",
    "context_seed",
)

EDGE_TYPES: tuple[str, ...] = ("cited", "inferred", "annotated")
FRESHNESS_STATES: tuple[str, ...] = ("current", "stale", "unknown", "omitted")
OMISSION_REASONS: tuple[str, ...] = (
    "forbidden_privacy",
    "node_limit",
    "neighbors_disabled",
    "candidate_limit",
    "endpoint_omitted",
    "edge_limit",
)

MAX_CANDIDATES = 128
MAX_ASSUMPTIONS = 256
MAX_OMISSIONS = 512
MAX_ID_LENGTH = 128
MAX_TEXT_LENGTH = 512

_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_REF_RE = re.compile(
    r"^(?P<scheme>[A-Za-z][A-Za-z0-9+.-]{1,31})://"
    r"(?P<body>[A-Za-z0-9][A-Za-z0-9._~:/#?&=+\-]{0,511})$"
)
_PUBLIC_SCHEMES = {
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
}
_SENSITIVE_RE = re.compile(
    r"(?i)(?:api[_-]?key|authorization|bearer|cookie|password|secret|token)"
    r"|sk-[A-Za-z0-9_-]{12,}"
)


class GraphContextSelectionError(ValueError):
    """Raised when a graph slice cannot safely seed context."""

    def __init__(self, message: str, errors: Sequence[str] = ()) -> None:
        self.errors = tuple(str(error) for error in errors if str(error))
        detail = "; ".join(self.errors[:8])
        super().__init__(f"{message}: {detail}" if detail else message)


@dataclass(frozen=True)
class _SliceData:
    graph_projection_id: str
    project_id: str
    selected_ids: list[str]
    nodes: list[dict[str, Any]]
    edges: list[dict[str, Any]]
    omitted_neighbors: list[dict[str, str]]
    omitted_edges: list[dict[str, str]]
    redacted_field_count: int


@dataclass(frozen=True)
class _SelectionParts:
    source_refs: list[dict[str, Any]]
    roles: dict[str, str]
    freshness: dict[str, list[str]]
    omitted_required: list[dict[str, str]]
    omitted_context: list[dict[str, str]]
    forbidden_refs: list[dict[str, str]]
    assumptions: list[dict[str, str]]
    omitted_assumptions: list[dict[str, str]]


def build_graph_context_selection(
    slice_payload: dict[str, Any],
    *,
    reader: str,
    decision_needed: str,
    context_profile: str = "graph-neighborhood",
    max_candidates: int = 64,
    max_assumptions: int = 128,
) -> dict[str, Any]:
    """Return a bounded context-selection manifest for an accepted graph slice."""
    _validate_arguments(
        slice_payload,
        reader=reader,
        decision_needed=decision_needed,
        context_profile=context_profile,
        max_candidates=max_candidates,
        max_assumptions=max_assumptions,
    )
    source = _parse_slice(slice_payload)
    parts = _prepare_selection_parts(
        source, max_candidates=max_candidates, max_assumptions=max_assumptions
    )
    return _assemble_manifest(
        source,
        reader,
        decision_needed,
        context_profile,
        parts,
    )


def _prepare_selection_parts(
    source: _SliceData, *, max_candidates: int, max_assumptions: int
) -> _SelectionParts:
    selected_ids = _select_ids(source, max_candidates)
    candidate_ids, omitted_candidates = _candidate_ids(
        source, selected_ids, max_candidates
    )
    source_refs, roles, freshness = _candidate_refs(
        source, selected_ids, candidate_ids
    )
    assumptions, omitted_assumptions = _assumptions(
        source.edges, max_assumptions
    )
    omitted_required = _omitted_neighbors(
        source.omitted_neighbors, candidate_ids
    )
    omitted_required.extend(omitted_candidates)
    omitted_context = _omitted_context(source.omitted_edges, omitted_assumptions)
    forbidden_refs = _forbidden_refs(omitted_required, omitted_context)
    return _SelectionParts(
        source_refs,
        roles,
        freshness,
        omitted_required,
        omitted_context,
        forbidden_refs,
        assumptions,
        omitted_assumptions,
    )


def _forbidden_refs(
    *omission_groups: list[dict[str, str]]
) -> list[dict[str, str]]:
    return [
        {"ref": item["ref"], "reason": item["omission_reason"]}
        for group in omission_groups
        for item in group
        if item["omission_reason"] == "forbidden_privacy"
    ]


def _validate_arguments(
    payload: object,
    *,
    reader: object,
    decision_needed: object,
    context_profile: object,
    max_candidates: object,
    max_assumptions: object,
) -> None:
    if not isinstance(payload, dict):
        raise GraphContextSelectionError("graph slice must be an object")
    for name, value in (
        ("reader", reader),
        ("decision_needed", decision_needed),
        ("context_profile", context_profile),
    ):
        if _safe_text(value) is None:
            raise GraphContextSelectionError(f"{name} must be safe text")
    _validate_limit(max_candidates, "max_candidates")
    _validate_limit(max_assumptions, "max_assumptions", MAX_ASSUMPTIONS)


def _validate_limit(value: object, name: str, upper_bound: int = MAX_CANDIDATES) -> None:
    if type(value) is not int or value < 1 or value > upper_bound:
        raise GraphContextSelectionError(
            f"{name} must be an integer from 1 through {upper_bound}"
        )


def _parse_slice(payload: dict[str, Any]) -> _SliceData:
    graph_id = _require_id(payload.get("graph_projection_id"), "graph_projection_id")
    project_id = _require_id(payload.get("project_id"), "project_id")
    selected_ids = _id_list(payload, "selected_node_ids", required=True)
    nodes = _object_list(payload, "nodes", required=True)
    edges = _object_list(payload, "edges", required=False)
    omitted_neighbors = _omission_list(payload, "omitted_neighbors")
    omitted_edges = _omission_list(payload, "omitted_edges")
    _validate_slice_summaries(payload)
    node_index = _validate_nodes(nodes)
    _validate_edges(edges, node_index)
    if any(node_id not in node_index for node_id in selected_ids):
        raise GraphContextSelectionError("selected node is absent from graph slice")
    if any(node_index[node_id]["privacy_class"] == "forbidden" for node_id in selected_ids):
        raise GraphContextSelectionError("selected node has forbidden privacy")
    redacted = _redacted_count(payload["privacy_summary"])
    return _SliceData(
        graph_id,
        project_id,
        selected_ids,
        nodes,
        edges,
        omitted_neighbors,
        omitted_edges,
        redacted,
    )


def _object_list(
    payload: dict[str, Any], name: str, *, required: bool
) -> list[dict[str, Any]]:
    value = payload.get(name)
    if value is None and not required:
        return []
    if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
        raise GraphContextSelectionError(f"{name} must be a list of objects")
    if len(value) > MAX_OMISSIONS * 16:
        raise GraphContextSelectionError(f"{name} exceeds hard limit")
    return value


def _id_list(
    payload: dict[str, Any], name: str, *, required: bool
) -> list[str]:
    value = payload.get(name)
    if value is None and not required:
        return []
    if not isinstance(value, list) or not value:
        raise GraphContextSelectionError(f"{name} must be a non-empty list")
    if len(value) > MAX_CANDIDATES:
        raise GraphContextSelectionError(f"{name} exceeds hard limit")
    result: list[str] = []
    seen: set[str] = set()
    for item in value:
        item_id = _require_id(item, name)
        if item_id in seen:
            raise GraphContextSelectionError(f"duplicate ID in {name}")
        seen.add(item_id)
        result.append(item_id)
    return result


def _omission_list(
    payload: dict[str, Any], name: str
) -> list[dict[str, str]]:
    value = payload.get(name, [])
    if not isinstance(value, list) or len(value) > MAX_OMISSIONS:
        raise GraphContextSelectionError(f"{name} must be a bounded list")
    result: list[dict[str, str]] = []
    for item in value:
        if not isinstance(item, dict):
            raise GraphContextSelectionError(f"{name} contains a non-object")
        item_id = _require_id(item.get("id"), f"{name}.id")
        reason = item.get("reason")
        if not isinstance(reason, str) or reason not in OMISSION_REASONS:
            raise GraphContextSelectionError(f"{name} contains an unknown reason")
        result.append({"id": item_id, "reason": reason})
    return result


def _validate_slice_summaries(payload: dict[str, Any]) -> None:
    validation = payload.get("validation_summary")
    privacy = payload.get("privacy_summary")
    if not isinstance(validation, dict) or validation.get("source_valid") is not True:
        raise GraphContextSelectionError("validation_summary must attest source_valid")
    if validation.get("bounded") is not True:
        raise GraphContextSelectionError("validation_summary must attest bounded")
    if not isinstance(privacy, dict) or "redacted_field_count" not in privacy:
        raise GraphContextSelectionError("privacy_summary must include redacted count")


def _redacted_count(privacy: dict[str, Any]) -> int:
    value = privacy.get("redacted_field_count")
    if type(value) is not int or value < 0 or value > MAX_OMISSIONS * 16:
        raise GraphContextSelectionError("privacy redacted count is invalid")
    return value


def _validate_nodes(nodes: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    for node in nodes:
        node_id = _require_id(node.get("id"), "node.id")
        if node_id in index:
            raise GraphContextSelectionError("graph slice contains duplicate node")
        node_type = node.get("type")
        authority = node.get("authority")
        privacy = node.get("privacy_class", "unknown")
        if node_type not in NODE_TYPES or not isinstance(authority, str):
            raise GraphContextSelectionError("graph slice node shape is invalid")
        if privacy not in PRIVACY_CLASSES or privacy == "forbidden":
            raise GraphContextSelectionError("graph slice node privacy is invalid")
        _validate_node_ref(node, privacy)
        index[node_id] = node
    if not index:
        raise GraphContextSelectionError("graph slice must contain a node")
    return index


def _validate_node_ref(node: dict[str, Any], privacy: str) -> None:
    if "source_ref" not in node:
        return
    if privacy != "public_repo" or not _safe_public_ref(node["source_ref"]):
        raise GraphContextSelectionError("unsafe source_ref in graph slice")


def _validate_edges(
    edges: list[dict[str, Any]], node_index: dict[str, dict[str, Any]]
) -> None:
    seen: set[str] = set()
    for edge in edges:
        edge_id = _require_id(edge.get("id"), "edge.id")
        if edge_id in seen:
            raise GraphContextSelectionError("graph slice contains duplicate edge")
        seen.add(edge_id)
        source = _require_id(edge.get("source"), "edge.source")
        target = _require_id(edge.get("target"), "edge.target")
        if source not in node_index or target not in node_index:
            raise GraphContextSelectionError("graph slice edge endpoint is absent")
        if edge.get("type") not in EDGE_TYPES:
            raise GraphContextSelectionError("graph slice edge type is invalid")
        privacy = edge.get("privacy_class", "unknown")
        if privacy not in PRIVACY_CLASSES or privacy == "forbidden":
            raise GraphContextSelectionError("graph slice edge privacy is invalid")
        if edge.get("type") == "cited" and not _safe_reference(edge.get("citation_source")):
            raise GraphContextSelectionError("cited edge citation is invalid")


def _select_ids(source: _SliceData, max_candidates: int) -> list[str]:
    if len(source.selected_ids) > max_candidates:
        raise GraphContextSelectionError("selected nodes exceed max_candidates")
    return list(source.selected_ids)


def _candidate_ids(
    source: _SliceData,
    selected_ids: list[str],
    max_candidates: int,
) -> tuple[list[str], list[dict[str, str]]]:
    selected = set(selected_ids)
    result = list(selected_ids)
    omitted: list[dict[str, str]] = []
    for node in source.nodes:
        node_id = node["id"]
        if node_id in selected:
            continue
        if len(result) >= max_candidates:
            omitted.append(_omitted_ref(node_id, "candidate_limit"))
            continue
        result.append(node_id)
    return result, omitted


def _candidate_refs(
    source: _SliceData,
    selected_ids: list[str],
    candidate_ids: list[str],
) -> tuple[list[dict[str, Any]], dict[str, str], dict[str, list[str]]]:
    selected = set(selected_ids)
    nodes = {node["id"]: node for node in source.nodes}
    refs: list[dict[str, Any]] = [
        _graph_ref(source.graph_projection_id)
    ]
    roles: dict[str, str] = {}
    freshness = {"stale_refs": [], "unknown_refs": []}
    for node_id in candidate_ids:
        node = nodes[node_id]
        role = "selected" if node_id in selected else "neighbor"
        roles[node_id] = role
        ref = _node_ref(source.graph_projection_id, node, role)
        refs.append(ref)
        _record_freshness(freshness, ref["ref_id"], ref["freshness_state"])
    return refs, roles, freshness


def _graph_ref(graph_id: str) -> dict[str, Any]:
    return {
        "ref_id": f"graph-slice-{graph_id}",
        "kind": "artifact",
        "uri": f"graph://projection/{graph_id}",
        "included": True,
        "required": True,
        "freshness_state": "unknown",
    }


def _node_ref(
    graph_id: str, node: dict[str, Any], role: str
) -> dict[str, Any]:
    node_id = node["id"]
    source_ref = node.get("source_ref")
    uri = source_ref if source_ref else f"graph://projection/{graph_id}/node/{node_id}"
    state = node.get("freshness")
    if state not in FRESHNESS_STATES:
        state = "unknown"
    return {
        "ref_id": f"graph-node-{node_id}",
        "kind": _reference_kind(node["type"]),
        "uri": uri,
        "included": True,
        "required": role == "selected",
        "freshness_state": state,
    }


def _reference_kind(node_type: str) -> str:
    return {
        "evidence": "evidence",
        "review": "review",
        "decision": "final_verdict",
    }.get(node_type, "artifact")


def _record_freshness(
    freshness: dict[str, list[str]], ref_id: str, state: str
) -> None:
    if state == "stale" and len(freshness["stale_refs"]) < MAX_OMISSIONS:
        freshness["stale_refs"].append(ref_id)
    elif state in {"unknown", "omitted"} and len(freshness["unknown_refs"]) < MAX_OMISSIONS:
        freshness["unknown_refs"].append(ref_id)


def _assumptions(
    edges: list[dict[str, Any]], max_assumptions: int
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    assumptions: list[dict[str, str]] = []
    omitted: list[dict[str, str]] = []
    for edge in edges:
        if edge["type"] not in {"inferred", "annotated"}:
            continue
        if len(assumptions) >= max_assumptions:
            omitted.append(_omitted_ref(edge["id"], "candidate_limit", prefix="graph-edge"))
            continue
        assumptions.append(
            {
                "edge_id": edge["id"],
                "source": edge["source"],
                "target": edge["target"],
                "kind": edge["type"],
                "authority": "assumption",
            }
        )
    return assumptions, omitted


def _omitted_neighbors(
    omitted_neighbors: list[dict[str, str]], candidate_ids: list[str]
) -> list[dict[str, str]]:
    included = set(candidate_ids)
    result: list[dict[str, str]] = []
    for item in omitted_neighbors:
        if item["id"] in included:
            continue
        result.append(
            {
                "ref": f"graph-node-{item['id']}",
                "omission_reason": item["reason"],
                "impact": _omission_impact(item["reason"]),
            }
        )
    return result[:MAX_OMISSIONS]


def _omitted_context(
    omitted_edges: list[dict[str, str]],
    omitted_assumptions: list[dict[str, str]],
) -> list[dict[str, str]]:
    result: list[dict[str, str]] = []
    for item in (*omitted_edges, *omitted_assumptions):
        result.append(
            {
                "ref": f"graph-edge-{item['id']}",
                "omission_reason": item["reason"],
                "impact": _omission_impact(item["reason"]),
            }
        )
    return result[:MAX_OMISSIONS]


def _omitted_ref(
    item_id: str, reason: str, *, prefix: str = "graph-node"
) -> dict[str, str]:
    return {
        "ref": f"{prefix}-{item_id}",
        "omission_reason": reason,
        "impact": _omission_impact(reason),
    }


def _omission_impact(reason: str) -> str:
    if reason == "forbidden_privacy":
        return "human_required"
    if reason in {"node_limit", "candidate_limit", "edge_limit"}:
        return "limited"
    return "limited"


def _assemble_manifest(
    source: _SliceData,
    reader: str,
    decision_needed: str,
    context_profile: str,
    parts: _SelectionParts,
) -> dict[str, Any]:
    graph_ref = f"graph://projection/{source.graph_projection_id}"
    return {
        "context_selection_id": _selection_id(source, parts),
        "graph_projection_id": source.graph_projection_id,
        "graph_slice_ref": graph_ref,
        "project_id": source.project_id,
        "reader": reader,
        "decision_needed": decision_needed,
        "context_profile": context_profile,
        "selected_node_ids": list(source.selected_ids),
        "candidate_roles": parts.roles,
        "source_refs": parts.source_refs,
        "omitted_required_refs": parts.omitted_required,
        "omitted_context": parts.omitted_context,
        "forbidden_refs": parts.forbidden_refs,
        "assumption_claims": parts.assumptions,
        "omitted_assumptions": parts.omitted_assumptions,
        "freshness": parts.freshness,
        "completeness_state": "incomplete",
        "privacy_state": "redacted",
        "candidate_source_summary": _candidate_summary(source, parts),
        "selection_rationale": (
            "Selected graph nodes are required candidates; one-hop neighbors are "
            "optional context. The bounded slice is incomplete, and inferred or "
            "annotated relationships remain assumptions."
        ),
        "limitations": [
            "A bounded graph neighborhood is not complete project context.",
            "Candidates are citations, not proof or final authority.",
        ],
        "authority_boundary": _authority_boundary(),
        "domain_refs": {
            "graph_projection_id": source.graph_projection_id,
            "graph_slice_ref": graph_ref,
        },
    }


def _selection_id(source: _SliceData, parts: _SelectionParts) -> str:
    seed = {
        "graph": source.graph_projection_id,
        "project": source.project_id,
        "selected": source.selected_ids,
        "candidates": sorted(parts.roles),
        "assumptions": [item["edge_id"] for item in parts.assumptions],
    }
    digest = hashlib.sha256(
        json.dumps(seed, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()[:16]
    return "gcs-" + digest


def _candidate_summary(
    source: _SliceData, parts: _SelectionParts
) -> dict[str, int]:
    selected_count = sum(role == "selected" for role in parts.roles.values())
    neighbor_count = sum(role == "neighbor" for role in parts.roles.values())
    return {
        "selected_count": selected_count,
        "neighbor_count": neighbor_count,
        "included_candidate_count": len(parts.roles),
        "omitted_neighbor_count": len(source.omitted_neighbors),
        "omitted_edge_count": len(source.omitted_edges),
        "assumption_count": len(parts.assumptions),
        "omitted_assumption_count": len(parts.omitted_assumptions),
        "redacted_field_count": source.redacted_field_count,
    }


def _authority_boundary() -> dict[str, bool]:
    return {
        "can_execute": False,
        "can_review": True,
        "can_claim_final_acceptance": False,
        "final_verdict_required": True,
    }


def _require_id(value: object, field_name: str) -> str:
    if not isinstance(value, str) or len(value) > MAX_ID_LENGTH or not _ID_RE.fullmatch(value):
        raise GraphContextSelectionError(f"{field_name} must be an opaque ID")
    return value


def _safe_reference(value: object) -> bool:
    if not isinstance(value, str) or len(value) > MAX_TEXT_LENGTH:
        return False
    if _ID_RE.fullmatch(value):
        return not _SENSITIVE_RE.search(value)
    match = _REF_RE.fullmatch(value)
    if match is None or match.group("scheme") not in _PUBLIC_SCHEMES:
        return False
    return not _SENSITIVE_RE.search(value) and ".." not in value and "\\" not in value


def _safe_public_ref(value: object) -> bool:
    if not isinstance(value, str):
        return False
    if "\\" in value:
        return False
    match = _REF_RE.fullmatch(value)
    return bool(
        match
        and match.group("scheme") in _PUBLIC_SCHEMES
        and _safe_reference(value)
    )


def _safe_text(value: object) -> str | None:
    if not isinstance(value, str) or not value or len(value) > MAX_TEXT_LENGTH:
        return None
    if _SENSITIVE_RE.search(value) or "\\" in value:
        return None
    if any(ord(char) < 32 for char in value):
        return None
    return value


__all__ = ["GraphContextSelectionError", "build_graph_context_selection"]
