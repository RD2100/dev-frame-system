"""Adapt an explicit CodeGraph snapshot into the governed graph projection.

This module is deliberately not a CodeGraph client or indexer.  A caller must
provide a bounded, already-normalized snapshot.  The adapter preserves only
safe code references and metadata, treats every CodeGraph relationship as an
inferred fact, and delegates the common projection checks to the existing
indexed-source boundary.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
import re
from typing import Any

from .graph_projection_validator import validate_graph_projection
from .indexed_graph_source import (
    IndexedGraphSourceError,
    build_indexed_graph_projection,
)


ADAPTER_VERSION = "codegraph-snapshot-source.0.1"
MAX_NODES = 512
MAX_RELATIONS = 1024
MAX_ID_LENGTH = 128
MAX_TEXT_LENGTH = 256
MAX_REF_LENGTH = 512

INDEX_STATUSES = frozenset(
    {
        "present",
        "missing",
        "unknown",
        "stale",
        "current",
        "empty",
        "needs_local_verification",
    }
)
FRESHNESS_STATES = frozenset({"current", "stale", "unknown", "not_applicable"})
PRIVACY_CLASSES = frozenset(
    {"public_repo", "local_path_only", "sensitive_redacted", "unknown"}
)
NODE_KINDS = frozenset(
    {
        "file",
        "class",
        "function",
        "method",
        "variable",
        "constant",
        "import",
        "module",
        "symbol",
    }
)
RELATION_KINDS = frozenset(
    {
        "calls",
        "contains",
        "imports",
        "implements",
        "tests",
        "depends_on",
        "references",
        "derived_from",
        "uses",
        "extends",
        "inherits",
    }
)
_SNAPSHOT_FIELDS = {
    "project_id",
    "resource_id",
    "index_name",
    "index_status",
    "index_freshness",
    "trusted_for_current_run",
    "nodes",
    "relations",
}
_NODE_FIELDS = {
    "id",
    "kind",
    "label",
    "source_ref",
    "privacy_class",
    "freshness",
    "confidence",
}
_RELATION_FIELDS = {
    "id",
    "source",
    "target",
    "kind",
    "source_ref",
    "privacy_class",
    "confidence",
}
_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_CODE_REF_RE = re.compile(
    r"^code://[A-Za-z0-9][A-Za-z0-9._~:/#?&=+\-]{0,511}$"
)
_SENSITIVE_RE = re.compile(
    r"(?i)(?:api[_-]?key|authorization|bearer|cookie|password|secret|token)"
    r"|sk-[A-Za-z0-9_-]{12,}"
)


class CodeGraphSnapshotError(ValueError):
    """Raised when a CodeGraph snapshot cannot be safely projected."""


def build_codegraph_snapshot_projection(
    snapshot: Mapping[str, Any],
    *,
    graph_projection_id: str,
    project_id: str,
    source_snapshot_refs: Sequence[str] = (),
) -> dict[str, Any]:
    """Build a bounded, non-authoritative projection from one CodeGraph snapshot."""
    selected_project_id = _require_id(project_id, "project_id")
    metadata = _validate_snapshot(snapshot, selected_project_id)
    safe_snapshot_refs = _safe_snapshot_refs(source_snapshot_refs)
    records, relations, relation_kinds = _normalize_snapshot_data(
        snapshot, selected_project_id, metadata["index_freshness"]
    )
    try:
        projection = build_indexed_graph_projection(
            records,
            relations,
            graph_projection_id=graph_projection_id,
            project_id=selected_project_id,
            source_snapshot_refs=safe_snapshot_refs,
        )
    except IndexedGraphSourceError as exc:
        raise CodeGraphSnapshotError(str(exc)) from exc
    _add_relation_kinds(projection, relation_kinds)
    projection["source_adapter"] = {
        **projection["source_adapter"],
        "id": ADAPTER_VERSION,
        "input": "explicit_codegraph_snapshot",
        "resource_id": metadata["resource_id"],
        "index_name": metadata["index_name"],
        "index_status": metadata["index_status"],
        "index_freshness": metadata["index_freshness"],
    }
    validation = validate_graph_projection(projection)
    if not validation.valid:
        raise CodeGraphSnapshotError(
            "generated CodeGraph projection is invalid: "
            + "; ".join(validation.errors[:4])
        )
    return projection


def _normalize_snapshot_data(
    snapshot: Mapping[str, Any], project_id: str, freshness: str
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, str]]:
    records = [_node_record(node, project_id, freshness) for node in snapshot["nodes"]]
    node_ids = {record["id"] for record in records}
    node_privacy = {record["id"]: record["privacy_class"] for record in records}
    relations: list[dict[str, Any]] = []
    relation_kinds: dict[str, str] = {}
    for relation in snapshot["relations"]:
        normalized, relation_kind = _relation_record(
            relation, project_id, node_ids, node_privacy
        )
        relations.append(normalized)
        relation_kinds[normalized["id"]] = relation_kind
    return records, relations, relation_kinds


def _validate_snapshot(
    snapshot: Mapping[str, Any], project_id: str
) -> dict[str, str]:
    if not isinstance(snapshot, Mapping):
        raise CodeGraphSnapshotError("snapshot must be an object")
    if set(snapshot) - _SNAPSHOT_FIELDS:
        raise CodeGraphSnapshotError("snapshot contains unsupported fields")
    if _require_id(snapshot.get("project_id"), "snapshot.project_id") != project_id:
        raise CodeGraphSnapshotError("snapshot project does not match requested project")
    resource_id = _require_id(snapshot.get("resource_id"), "snapshot.resource_id")
    index_name = _safe_text(snapshot.get("index_name"), "index_name")
    status = snapshot.get("index_status")
    if status not in INDEX_STATUSES:
        raise CodeGraphSnapshotError("snapshot index_status is invalid")
    freshness = snapshot.get("index_freshness")
    if freshness not in FRESHNESS_STATES:
        raise CodeGraphSnapshotError("snapshot index_freshness is invalid")
    trusted = snapshot.get("trusted_for_current_run")
    if type(trusted) is not bool or trusted:
        raise CodeGraphSnapshotError(
            "CodeGraph snapshot trusted_for_current_run must be false"
        )
    _validate_sequence(snapshot.get("nodes"), "snapshot.nodes", MAX_NODES)
    _validate_sequence(snapshot.get("relations"), "snapshot.relations", MAX_RELATIONS)
    if not snapshot["nodes"]:
        raise CodeGraphSnapshotError("snapshot nodes must not be empty")
    return {
        "resource_id": resource_id,
        "index_name": index_name,
        "index_status": str(status),
        "index_freshness": str(freshness),
    }


def _node_record(
    raw: Mapping[str, Any], project_id: str, snapshot_freshness: str
) -> dict[str, Any]:
    node = _mapping(raw, "snapshot node")
    _allowlisted(node, _NODE_FIELDS, "snapshot node")
    node_id = _require_id(node.get("id"), "node.id")
    kind = node.get("kind")
    if kind not in NODE_KINDS:
        raise CodeGraphSnapshotError("CodeGraph node kind is invalid")
    source_ref = _safe_code_ref(node.get("source_ref"), "node.source_ref")
    privacy = _privacy(node.get("privacy_class", "local_path_only"), "node")
    record: dict[str, Any] = {
        "id": node_id,
        "project_id": project_id,
        "kind": "artifact",
        "source_kind": f"codegraph_{kind}",
        "authority": "none",
        "privacy_class": privacy,
        "freshness": _effective_freshness(
            snapshot_freshness, node.get("freshness")
        ),
        "confidence": _confidence(node.get("confidence")),
    }
    if privacy == "public_repo":
        label = node.get("label")
        if label not in (None, ""):
            record["label"] = _safe_text(label, "node.label")
        record["source_ref"] = source_ref
    return record


def _relation_record(
    raw: Mapping[str, Any],
    project_id: str,
    node_ids: set[str],
    node_privacy: Mapping[str, str],
) -> tuple[dict[str, Any], str]:
    relation = _mapping(raw, "snapshot relation")
    _allowlisted(relation, _RELATION_FIELDS, "snapshot relation")
    relation_id = _require_id(relation.get("id"), "relation.id")
    source = _require_id(relation.get("source"), "relation.source")
    target = _require_id(relation.get("target"), "relation.target")
    if source not in node_ids or target not in node_ids:
        raise CodeGraphSnapshotError("CodeGraph relation endpoint is not in snapshot")
    relation_kind = relation.get("kind")
    if relation_kind not in RELATION_KINDS:
        raise CodeGraphSnapshotError("CodeGraph relation kind is invalid")
    requested_privacy = _privacy(
        relation.get("privacy_class", "unknown"), "relation"
    )
    endpoint_privacy = _relation_privacy(
        node_privacy.get(source, "unknown"), node_privacy.get(target, "unknown")
    )
    if requested_privacy == "public_repo" and endpoint_privacy != "public_repo":
        raise CodeGraphSnapshotError(
            "public CodeGraph relation cannot connect a private node"
        )
    privacy = (
        "public_repo"
        if requested_privacy == "public_repo"
        else endpoint_privacy
    )
    record: dict[str, Any] = {
        "id": relation_id,
        "project_id": project_id,
        "source": source,
        "target": target,
        "type": "inferred",
        "privacy_class": privacy,
        "confidence": _confidence(relation.get("confidence")),
    }
    source_ref = relation.get("source_ref")
    if source_ref is not None:
        record["source_ref"] = _safe_code_ref(source_ref, "relation.source_ref")
    return record, str(relation_kind)


def _add_relation_kinds(
    projection: dict[str, Any], kinds: Mapping[str, str]
) -> None:
    for edge in projection["edges"]:
        relation_kind = kinds.get(str(edge["id"]))
        if relation_kind is None:
            raise CodeGraphSnapshotError("generated relation identity is missing")
        edge["relation_kind"] = relation_kind
        edge["source_kind"] = "codegraph"


def _relation_privacy(source: str, target: str) -> str:
    if source == "public_repo" and target == "public_repo":
        return "public_repo"
    if "sensitive_redacted" in {source, target}:
        return "sensitive_redacted"
    return "local_path_only"


def _effective_freshness(snapshot: str, node: object) -> str:
    if snapshot == "stale":
        return "stale"
    if snapshot in {"unknown", "not_applicable"}:
        return "unknown"
    if node is None:
        return "current"
    if node not in {"current", "stale", "unknown"}:
        raise CodeGraphSnapshotError("node freshness is invalid")
    return str(node)


def _validate_sequence(value: object, name: str, limit: int) -> None:
    if isinstance(value, (str, bytes, bytearray)) or not isinstance(value, Sequence):
        raise CodeGraphSnapshotError(f"{name} must be a list")
    if len(value) > limit:
        raise CodeGraphSnapshotError(f"{name} exceeds hard limit {limit}")


def _mapping(value: object, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise CodeGraphSnapshotError(f"{name} must be an object")
    return value


def _allowlisted(value: Mapping[str, Any], allowed: set[str], name: str) -> None:
    if set(value) - allowed:
        raise CodeGraphSnapshotError(f"{name} contains unsupported fields")


def _privacy(value: object, name: str) -> str:
    if value not in PRIVACY_CLASSES:
        raise CodeGraphSnapshotError(f"{name} privacy_class is invalid")
    return str(value)


def _confidence(value: object) -> float:
    if value is None:
        return 0.5
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise CodeGraphSnapshotError("CodeGraph confidence is invalid")
    result = float(value)
    if result < 0 or result > 1:
        raise CodeGraphSnapshotError("CodeGraph confidence is invalid")
    return result


def _safe_text(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value or len(value) > MAX_TEXT_LENGTH:
        raise CodeGraphSnapshotError(f"CodeGraph {field_name} is invalid")
    if any(ord(char) < 32 for char in value) or _SENSITIVE_RE.search(value):
        raise CodeGraphSnapshotError(f"CodeGraph {field_name} is unsafe")
    if _looks_like_path(value):
        raise CodeGraphSnapshotError(f"CodeGraph {field_name} is unsafe")
    return value


def _safe_code_ref(value: object, field_name: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or len(value) > MAX_REF_LENGTH
        or _SENSITIVE_RE.search(value)
        or not _CODE_REF_RE.fullmatch(value)
        or _has_traversal_segment(value)
    ):
        raise CodeGraphSnapshotError(f"CodeGraph {field_name} is unsafe")
    return value


def _safe_snapshot_refs(value: Sequence[str]) -> list[str]:
    if isinstance(value, (str, bytes, bytearray)) or not isinstance(value, Sequence):
        raise CodeGraphSnapshotError("source_snapshot_refs must be a list")
    if len(value) > 128:
        raise CodeGraphSnapshotError("source_snapshot_refs exceeds hard limit")
    result: list[str] = []
    for item in value:
        if not isinstance(item, str) or len(item) > MAX_REF_LENGTH:
            raise CodeGraphSnapshotError("source snapshot reference is invalid")
        if _SENSITIVE_RE.search(item) or _looks_like_path(item):
            raise CodeGraphSnapshotError("source snapshot reference is unsafe")
        if not re.fullmatch(
            r"(?:repo|graph|artifact|code)://[A-Za-z0-9][A-Za-z0-9._~:/#?&=+\-]{0,511}",
            item,
        ) or _has_traversal_segment(item):
            raise CodeGraphSnapshotError("source snapshot reference is unsafe")
        if item not in result:
            result.append(item)
    return result


def _has_traversal_segment(value: str) -> bool:
    path = value.split("?", 1)[0].split("#", 1)[0]
    return any(segment in {".", ".."} for segment in path.split("/"))


def _looks_like_path(value: str) -> bool:
    body = value.split("://", 1)[1] if "://" in value else value
    return bool(
        re.match(r"^[A-Za-z]:[\\/]", value)
        or re.match(r"^[A-Za-z]:[\\/]", body)
        or value.startswith(("/", "\\"))
        or body.startswith(("/", "\\"))
        or _has_traversal_segment(value)
    )


def _require_id(value: object, field_name: str) -> str:
    if not isinstance(value, str) or len(value) > MAX_ID_LENGTH or not _ID_RE.fullmatch(value):
        raise CodeGraphSnapshotError(f"{field_name} must be a safe ID")
    return value
