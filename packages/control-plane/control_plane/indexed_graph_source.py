"""Adapt explicit domain-index records into the governed graph projection.

This module is deliberately not an indexer.  Code, document, paper, skill, or
runtime producers must supply already-bounded records and relations.  The
adapter validates their project/privacy/authority boundaries and emits the
existing read-only graph vocabulary without reading files or contacting a
provider.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
import re
from typing import Any

from .graph_projection_validator import (
    AUTHORITY_LABELS,
    EDGE_TYPES,
    NODE_TYPES,
    validate_graph_projection,
)


ADAPTER_VERSION = "indexed-graph-source.0.1"
MAX_RECORDS = 512
MAX_RELATIONS = 1024
MAX_REFS = 128
MAX_ID_LENGTH = 128
MAX_TEXT_LENGTH = 256
MAX_REF_LENGTH = 512

PRIVACY_CLASSES: tuple[str, ...] = (
    "public_repo",
    "local_path_only",
    "private_content_summary",
    "sensitive_redacted",
    "forbidden",
    "unknown",
)
FRESHNESS_STATES: tuple[str, ...] = ("current", "stale", "unknown")
_KIND_TO_NODE_TYPE = {
    "agent": "agent",
    "artifact": "artifact",
    "code": "artifact",
    "context_seed": "context_seed",
    "decision": "decision",
    "doc": "artifact",
    "document": "artifact",
    "evidence": "evidence",
    "paper": "artifact",
    "project": "artifact",
    "review": "review",
    "run": "artifact",
    "skill": "artifact",
}
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
_RECORD_FIELDS = {
    "id",
    "project_id",
    "kind",
    "authority",
    "privacy_class",
    "label",
    "source_ref",
    "source_kind",
    "freshness",
    "confidence",
    "evidence_refs",
    "decision_refs",
    "provenance",
}
_RELATION_FIELDS = {
    "id",
    "project_id",
    "source",
    "target",
    "type",
    "privacy_class",
    "authority",
    "source_ref",
    "citation_source",
    "evidence_refs",
    "confidence",
    "is_source_truth",
    "promoted_to_decision",
}
_EDGE_AUTHORITY = {
    "source_truth",
    "governed_decision",
    "evidence_backed",
    "human_annotation",
    "agent_proposal",
    "inferred",
    "unknown",
}
_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_REF_RE = re.compile(
    r"^(?P<scheme>[A-Za-z][A-Za-z0-9+.-]{1,31})://"
    r"(?P<body>[A-Za-z0-9][A-Za-z0-9._~:/#?&=+\-]{0,511})$"
)
_SENSITIVE_RE = re.compile(
    r"(?i)(?:api[_-]?key|authorization|bearer|cookie|password|secret|token)"
    r"|sk-[A-Za-z0-9_-]{12,}"
)


class IndexedGraphSourceError(ValueError):
    """Raised when explicit index input cannot safely become a projection."""


def build_indexed_graph_projection(
    records: Sequence[Mapping[str, Any]],
    relations: Sequence[Mapping[str, Any]] = (),
    *,
    graph_projection_id: str,
    project_id: str,
    source_snapshot_refs: Sequence[str] = (),
) -> dict[str, Any]:
    """Build a bounded project-scoped projection from explicit index data."""
    projection_id = _require_id(graph_projection_id, "graph_projection_id")
    selected_project_id = _require_id(project_id, "project_id")
    _validate_sequence(records, "records", MAX_RECORDS)
    _validate_sequence(relations, "relations", MAX_RELATIONS)
    snapshot_refs = _safe_snapshot_refs(source_snapshot_refs)

    normalized_records = _normalize_records(records, selected_project_id)
    if not normalized_records:
        raise IndexedGraphSourceError("requested project has no indexed records")
    node_ids = {record["id"] for record in normalized_records}
    normalized_relations = _normalize_relations(
        relations, selected_project_id, node_ids
    )
    projection = {
        "graph_projection_id": projection_id,
        "project_id": selected_project_id,
        "source_snapshot_refs": snapshot_refs,
        "nodes": sorted(normalized_records, key=lambda item: item["id"]),
        "edges": sorted(normalized_relations, key=lambda item: item["id"]),
        "operations": ["project", "query", "seed_context"],
        "source_adapter": {
            "id": ADAPTER_VERSION,
            "input": "explicit_index_records",
            "read_only": True,
        },
    }
    _validate_projection(projection)
    return projection


def _normalize_records(
    records: Sequence[Mapping[str, Any]], project_id: str
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in records:
        record = _mapping(raw, "record")
        _allowlisted(record, _RECORD_FIELDS, "record")
        record_project_id = _require_id(record.get("project_id"), "record.project_id")
        if record_project_id != project_id:
            continue
        normalized = _normalize_record(record)
        if normalized["id"] in seen:
            raise IndexedGraphSourceError("duplicate indexed record identity")
        seen.add(normalized["id"])
        result.append(normalized)
    return result


def _normalize_record(record: Mapping[str, Any]) -> dict[str, Any]:
    record_id = _require_id(record.get("id"), "record.id")
    kind = _safe_kind(record.get("kind"))
    node_type = _KIND_TO_NODE_TYPE[kind]
    if node_type not in NODE_TYPES:
        raise IndexedGraphSourceError("indexed record kind is unsupported")
    authority = record.get("authority")
    if authority not in AUTHORITY_LABELS:
        raise IndexedGraphSourceError("indexed record authority is invalid")
    privacy = record.get("privacy_class", "unknown")
    if privacy not in PRIVACY_CLASSES or privacy == "forbidden":
        raise IndexedGraphSourceError("indexed record privacy is invalid")
    node: dict[str, Any] = {
        "id": record_id,
        "type": node_type,
        "authority": authority,
        "privacy_class": privacy,
    }
    if privacy == "public_repo":
        _copy_public_record_fields(record, node, kind)
    node["freshness"] = _freshness(record.get("freshness"))
    node["confidence"] = _confidence(record.get("confidence"))
    if privacy == "public_repo":
        _copy_reference_fields(record, node)
    return node


def _copy_public_record_fields(
    record: Mapping[str, Any], node: dict[str, Any], kind: str
) -> None:
    label = _safe_text(record.get("label"), "label", allow_empty=True)
    if label:
        node["label"] = label
    source_ref = record.get("source_ref")
    if source_ref is not None:
        node["source_ref"] = _safe_public_ref(source_ref, "source_ref")
    source_kind = record.get("source_kind", kind)
    node["source_kind"] = _safe_text(source_kind, "source_kind")


def _copy_reference_fields(record: Mapping[str, Any], node: dict[str, Any]) -> None:
    for field_name in ("evidence_refs", "decision_refs", "provenance"):
        if field_name in record:
            node[field_name] = _safe_ref_list(record[field_name], field_name)


def _normalize_relations(
    relations: Sequence[Mapping[str, Any]],
    project_id: str,
    node_ids: set[str],
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in relations:
        relation = _mapping(raw, "relation")
        _allowlisted(relation, _RELATION_FIELDS, "relation")
        if _require_id(relation.get("project_id"), "relation.project_id") != project_id:
            continue
        normalized = _normalize_relation(relation, node_ids)
        if normalized["id"] in seen:
            raise IndexedGraphSourceError("duplicate indexed relation identity")
        seen.add(normalized["id"])
        result.append(normalized)
    return result


def _normalize_relation(
    relation: Mapping[str, Any], node_ids: set[str]
) -> dict[str, Any]:
    relation_id = _require_id(relation.get("id"), "relation.id")
    source = _require_id(relation.get("source"), "relation.source")
    target = _require_id(relation.get("target"), "relation.target")
    if source not in node_ids or target not in node_ids:
        raise IndexedGraphSourceError("relation endpoint is not in the project")
    relation_type = relation.get("type")
    if relation_type not in EDGE_TYPES:
        raise IndexedGraphSourceError("relation type is invalid")
    if relation_type == "cited":
        citation = _safe_reference(relation.get("citation_source"), "citation_source")
    else:
        citation = None
    privacy = relation.get("privacy_class", "unknown")
    if privacy not in PRIVACY_CLASSES or privacy == "forbidden":
        raise IndexedGraphSourceError("relation privacy is invalid")
    source_truth = _optional_bool(relation, "is_source_truth")
    promoted = _optional_bool(relation, "promoted_to_decision")
    if source_truth and relation_type == "inferred":
        raise IndexedGraphSourceError("inferred relation cannot be source truth")
    if promoted and relation_type == "annotated":
        raise IndexedGraphSourceError("annotated relation cannot become a decision")
    edge: dict[str, Any] = {
        "id": relation_id,
        "source": source,
        "target": target,
        "type": relation_type,
        "privacy_class": privacy,
    }
    if citation is not None:
        edge["citation_source"] = citation
    if privacy == "public_repo":
        source_ref = relation.get("source_ref")
        if source_ref is not None:
            edge["source_ref"] = _safe_public_ref(source_ref, "source_ref")
        if "authority" in relation:
            authority = relation["authority"]
            if authority not in _EDGE_AUTHORITY:
                raise IndexedGraphSourceError("relation authority is invalid")
            edge["authority"] = authority
        if "evidence_refs" in relation:
            edge["evidence_refs"] = _safe_ref_list(
                relation["evidence_refs"], "evidence_refs"
            )
        if "confidence" in relation:
            edge["confidence"] = _confidence(relation["confidence"])
    return edge


def _validate_projection(projection: dict[str, Any]) -> None:
    validation = validate_graph_projection(projection)
    if not validation.valid:
        raise IndexedGraphSourceError(
            "generated graph projection is invalid: "
            + "; ".join(validation.errors[:4])
        )


def _validate_sequence(value: object, name: str, limit: int) -> None:
    if isinstance(value, (str, bytes, bytearray)) or not isinstance(value, Sequence):
        raise IndexedGraphSourceError(f"{name} must be a list")
    if len(value) > limit:
        raise IndexedGraphSourceError(f"{name} exceeds hard limit {limit}")


def _mapping(value: object, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise IndexedGraphSourceError(f"{name} must be an object")
    return value


def _allowlisted(value: Mapping[str, Any], allowed: set[str], name: str) -> None:
    if set(value) - allowed:
        raise IndexedGraphSourceError(f"{name} contains unsupported fields")


def _safe_kind(value: object) -> str:
    if not isinstance(value, str) or value not in _KIND_TO_NODE_TYPE:
        raise IndexedGraphSourceError("indexed record kind is invalid")
    return value


def _optional_bool(record: Mapping[str, Any], field_name: str) -> bool:
    if field_name not in record:
        return False
    value = record[field_name]
    if type(value) is not bool:
        raise IndexedGraphSourceError(f"indexed {field_name} must be boolean")
    return value


def _freshness(value: object) -> str:
    if value is None:
        return "unknown"
    if value not in FRESHNESS_STATES:
        raise IndexedGraphSourceError("indexed freshness is invalid")
    return str(value)


def _confidence(value: object) -> float:
    if value is None:
        return 0.5
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise IndexedGraphSourceError("indexed confidence is invalid")
    confidence = float(value)
    if confidence < 0 or confidence > 1:
        raise IndexedGraphSourceError("indexed confidence is invalid")
    return confidence


def _safe_text(value: object, field_name: str, *, allow_empty: bool = False) -> str:
    if value in (None, "") and allow_empty:
        return ""
    if not isinstance(value, str) or len(value) > MAX_TEXT_LENGTH:
        raise IndexedGraphSourceError(f"indexed {field_name} is invalid")
    if any(ord(char) < 32 for char in value) or _SENSITIVE_RE.search(value):
        raise IndexedGraphSourceError(f"indexed {field_name} is unsafe")
    return value


def _safe_public_ref(value: object, field_name: str) -> str:
    reference = _safe_reference(value, field_name)
    match = _REF_RE.fullmatch(reference)
    if match is None or match.group("scheme") not in _PUBLIC_REF_SCHEMES:
        raise IndexedGraphSourceError(f"indexed {field_name} is unsafe")
    return reference


def _safe_reference(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value or len(value) > MAX_REF_LENGTH:
        raise IndexedGraphSourceError(f"indexed {field_name} is invalid")
    if any(ord(char) < 32 for char in value) or _SENSITIVE_RE.search(value):
        raise IndexedGraphSourceError(f"indexed {field_name} is unsafe")
    if _ID_RE.fullmatch(value) or _REF_RE.fullmatch(value):
        return value
    raise IndexedGraphSourceError(f"indexed {field_name} is unsafe")


def _safe_ref_list(value: object, field_name: str) -> list[str]:
    if not isinstance(value, list) or len(value) > MAX_REFS:
        raise IndexedGraphSourceError(f"indexed {field_name} is not bounded")
    result: list[str] = []
    for item in value:
        safe = _safe_reference(item, field_name)
        if safe not in result:
            result.append(safe)
    return result


def _safe_snapshot_refs(value: Sequence[str]) -> list[str]:
    _validate_sequence(value, "source_snapshot_refs", MAX_REFS)
    result: list[str] = []
    for item in value:
        safe = _safe_public_ref(item, "source snapshot reference")
        if safe not in result:
            result.append(safe)
    return result


def _require_id(value: object, field_name: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) > MAX_ID_LENGTH
        or not _ID_RE.fullmatch(value)
    ):
        raise IndexedGraphSourceError(f"{field_name} must be a safe ID")
    return value
