"""Build a bounded graph projection from an explicit governance digest.

The adapter is intentionally a source boundary, not a discovery service.  A
caller supplies the result of an existing read-only digest producer (such as
``Orchestrator.build_digest`` or ``build_runtime_digest``).  Only a small,
allowlisted subset is projected; paths, goals, reasons, and report contents
never enter the graph payload.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
import re
from typing import Any

from .graph_projection_validator import validate_graph_projection


ADAPTER_VERSION = "governance-digest-graph-source.0.1"
MAX_PROJECTS = 64
MAX_DISPATCHES = 256
MAX_REPORTS = 256
MAX_SNAPSHOT_REFS = 128
MAX_ID_LENGTH = 128
MAX_TEXT_LENGTH = 128
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

_DIGEST_FIELDS = {"projects", "dispatches", "reports", "runtime_dir"}
_PROJECT_FIELDS = {
    "project_id",
    "status",
    "priority",
    "autonomy_level",
    "goal",
    "blocked_reason",
    "project_root",
}
_DISPATCH_FIELDS = {
    "project_id",
    "operation",
    "decision_mode",
    "dispatch_ready",
    "reason",
    "snapshot",
    "recommended_path",
    "packet_dir",
    "packet_id",
    "timestamp",
}
_REPORT_FIELDS = {
    "packet_id",
    "project_id",
    "status",
    "changed_files",
    "report_path",
    "verification",
    "ingested_at",
}
_PASSED_REPORT_STATES = {"passed", "success", "succeeded"}


class GovernanceGraphSourceError(ValueError):
    """Raised when an explicit governance digest cannot be projected safely."""


def build_governance_graph_projection(
    digest: Mapping[str, Any],
    *,
    graph_projection_id: str,
    project_id: str,
    source_snapshot_refs: Sequence[str] = (),
) -> dict[str, Any]:
    """Return a project-scoped, read-only graph projection.

    The function performs no discovery or persistence.  It accepts only the
    stable digest fields produced by existing DevFrame readers and deliberately
    ignores path-bearing and free-form fields after validating the record
    shape.  The resulting graph is suitable for ``build_graph_slice`` and
    ``build_graph_context_selection``.
    """
    projection_id = _require_id(graph_projection_id, "graph_projection_id")
    selected_project_id = _require_id(project_id, "project_id")
    _validate_digest_shape(digest)
    snapshot_refs = _safe_snapshot_refs(source_snapshot_refs)

    project, selected_dispatches, selected_reports = _prepare_records(
        digest, selected_project_id
    )

    nodes, edges = _build_nodes_and_edges(
        project,
        selected_project_id,
        selected_dispatches,
        selected_reports,
    )

    projection = _assemble_projection(
        projection_id,
        selected_project_id,
        snapshot_refs,
        nodes,
        edges,
    )
    _validate_projection(projection)
    return projection


def _prepare_records(
    digest: Mapping[str, Any], project_id: str
) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    projects = _records(digest, "projects", MAX_PROJECTS, _PROJECT_FIELDS)
    dispatches = _records(digest, "dispatches", MAX_DISPATCHES, _DISPATCH_FIELDS)
    reports = _records(digest, "reports", MAX_REPORTS, _REPORT_FIELDS)
    project = _select_project(projects, project_id)
    return project, _select_records(dispatches, project_id), _select_records(reports, project_id)


def _assemble_projection(
    projection_id: str,
    project_id: str,
    snapshot_refs: list[str],
    nodes: list[dict[str, Any]],
    edges: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "graph_projection_id": projection_id,
        "project_id": project_id,
        "source_snapshot_refs": snapshot_refs,
        "nodes": nodes,
        "edges": edges,
        "operations": ["project", "query", "seed_context"],
        "source_adapter": {
            "id": ADAPTER_VERSION,
            "input": "explicit_governance_digest",
            "read_only": True,
        },
    }


def _validate_projection(projection: dict[str, Any]) -> None:
    validation = validate_graph_projection(projection)
    if not validation.valid:
        raise GovernanceGraphSourceError(
            "generated graph projection is invalid: "
            + "; ".join(validation.errors[:4])
        )


def _build_nodes_and_edges(
    project: Mapping[str, Any],
    project_id: str,
    dispatches: list[dict[str, Any]],
    reports: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    project_node_id = _node_id("project", project_id)
    nodes = [_project_node(project, project_id, project_node_id)]
    edges: list[dict[str, Any]] = []
    dispatch_nodes = _append_dispatch_nodes(
        nodes, edges, dispatches, project_id, project_node_id
    )
    _append_report_nodes(
        nodes, edges, reports, project_id, project_node_id, dispatch_nodes
    )
    return nodes, edges


def _append_dispatch_nodes(
    nodes: list[dict[str, Any]],
    edges: list[dict[str, Any]],
    dispatches: list[dict[str, Any]],
    project_id: str,
    project_node_id: str,
) -> dict[str, str]:
    dispatch_nodes: dict[str, str] = {}
    seen_node_ids: set[str] = set()
    for index, record in enumerate(dispatches, start=1):
        packet_id = _optional_id(record.get("packet_id"), "packet_id")
        node_id = _node_id("decision", packet_id or f"dispatch-{index}")
        if node_id in seen_node_ids:
            raise GovernanceGraphSourceError("duplicate dispatch identity")
        seen_node_ids.add(node_id)
        if packet_id:
            dispatch_nodes[packet_id] = node_id
        nodes.append(_dispatch_node(record, node_id))
        edges.append(_cited_edge(
            edge_id=f"edge-project-dispatch-{index}",
            source=project_node_id,
            target=node_id,
            citation_source=f"project://{project_id}",
        ))
    return dispatch_nodes


def _append_report_nodes(
    nodes: list[dict[str, Any]],
    edges: list[dict[str, Any]],
    reports: list[dict[str, Any]],
    project_id: str,
    project_node_id: str,
    dispatch_nodes: Mapping[str, str],
) -> None:
    seen_node_ids = {str(node["id"]) for node in nodes}
    for index, record in enumerate(reports, start=1):
        packet_id = _optional_id(record.get("packet_id"), "packet_id")
        node_id = _node_id("evidence", packet_id or f"report-{index}")
        if node_id in seen_node_ids:
            raise GovernanceGraphSourceError("duplicate report identity")
        seen_node_ids.add(node_id)
        nodes.append(_report_node(record, node_id))
        linked_dispatch = dispatch_nodes.get(packet_id) if packet_id else None
        if linked_dispatch:
            edges.append(_cited_edge(
                edge_id=f"edge-dispatch-report-{index}",
                source=linked_dispatch,
                target=node_id,
                citation_source=f"decision://{linked_dispatch}",
            ))
            continue
        edges.append(_cited_edge(
            edge_id=f"edge-project-report-{index}",
            source=project_node_id,
            target=node_id,
            citation_source=f"project://{project_id}",
        ))


def _validate_digest_shape(digest: Mapping[str, Any]) -> None:
    if not isinstance(digest, Mapping):
        raise GovernanceGraphSourceError("digest must be an object")
    if set(digest) - _DIGEST_FIELDS:
        raise GovernanceGraphSourceError("digest contains unsupported fields")
    for name in ("projects", "dispatches", "reports"):
        value = digest.get(name)
        if not isinstance(value, list):
            raise GovernanceGraphSourceError(f"digest.{name} must be a list")


def _records(
    digest: Mapping[str, Any],
    field_name: str,
    limit: int,
    allowed_fields: set[str],
) -> list[dict[str, Any]]:
    records = digest[field_name]
    if len(records) > limit:
        raise GovernanceGraphSourceError(
            f"digest.{field_name} exceeds hard limit {limit}"
        )
    result: list[dict[str, Any]] = []
    for record in records:
        if not isinstance(record, Mapping):
            raise GovernanceGraphSourceError(f"digest.{field_name} has invalid record")
        if set(record) - allowed_fields:
            raise GovernanceGraphSourceError(
                f"digest.{field_name} contains unsupported fields"
            )
        result.append(dict(record))
    return result


def _select_project(
    projects: list[dict[str, Any]], project_id: str
) -> dict[str, Any]:
    matches = [record for record in projects if _record_project_id(record) == project_id]
    if not matches:
        raise GovernanceGraphSourceError("requested project is absent from digest")
    if len(matches) != 1:
        raise GovernanceGraphSourceError("digest contains duplicate project identity")
    return matches[0]


def _select_records(
    records: list[dict[str, Any]], project_id: str
) -> list[dict[str, Any]]:
    return [record for record in records if _record_project_id(record) == project_id]


def _record_project_id(record: Mapping[str, Any]) -> str:
    return _require_id(record.get("project_id"), "record.project_id")


def _project_node(
    record: Mapping[str, Any], project_id: str, node_id: str
) -> dict[str, Any]:
    status = _safe_label(record.get("status"), default="unknown")
    return {
        "id": node_id,
        "type": "artifact",
        "authority": "governance_recorded",
        "privacy_class": "public_repo",
        "label": f"Project {project_id} [{status}]",
        "source_ref": f"project://{project_id}",
        "source_kind": "governance_digest",
        "freshness": "current",
        "confidence": 1.0,
    }


def _dispatch_node(record: Mapping[str, Any], node_id: str) -> dict[str, Any]:
    operation = _safe_label(record.get("operation"), default="dispatch")
    mode = _safe_label(record.get("decision_mode"), default="unknown")
    ready = record.get("dispatch_ready", False)
    if type(ready) is not bool:
        raise GovernanceGraphSourceError("dispatch_ready must be boolean")
    return {
        "id": node_id,
        "type": "decision",
        "authority": "governance_recorded",
        "privacy_class": "public_repo",
        "label": f"Dispatch {operation} [{mode}; {'ready' if ready else 'held'}]",
        "source_ref": f"decision://{node_id}",
        "source_kind": "rdgoal_dispatch",
        "freshness": "current",
        "confidence": 1.0,
    }


def _report_node(record: Mapping[str, Any], node_id: str) -> dict[str, Any]:
    status = _safe_label(record.get("status"), default="unknown")
    verified = status.casefold() in _PASSED_REPORT_STATES
    return {
        "id": node_id,
        "type": "evidence",
        "authority": "test_verified" if verified else "governance_recorded",
        "privacy_class": "public_repo",
        "label": f"Execution report [{status}]",
        "source_ref": f"evidence://{node_id}",
        "source_kind": "execution_report",
        "freshness": "current",
        "confidence": 1.0 if verified else 0.5,
    }


def _cited_edge(
    *, edge_id: str, source: str, target: str, citation_source: str
) -> dict[str, Any]:
    return {
        "id": edge_id,
        "source": source,
        "target": target,
        "type": "cited",
        "citation_source": citation_source,
        "privacy_class": "public_repo",
        "source_ref": citation_source,
    }


def _safe_snapshot_refs(value: Sequence[str]) -> list[str]:
    if isinstance(value, (str, bytes, bytearray)) or not isinstance(value, Sequence):
        raise GovernanceGraphSourceError("source_snapshot_refs must be a list")
    if len(value) > MAX_SNAPSHOT_REFS:
        raise GovernanceGraphSourceError("source_snapshot_refs exceeds hard limit")
    result: list[str] = []
    for item in value:
        if not isinstance(item, str) or len(item) > MAX_REF_LENGTH:
            raise GovernanceGraphSourceError("source snapshot reference is invalid")
        if _SENSITIVE_RE.search(item):
            raise GovernanceGraphSourceError("source snapshot reference is unsafe")
        match = _REF_RE.fullmatch(item)
        if match is None or match.group("scheme") not in _PUBLIC_REF_SCHEMES:
            raise GovernanceGraphSourceError("source snapshot reference is unsafe")
        if item not in result:
            result.append(item)
    return result


def _require_id(value: object, field_name: str) -> str:
    if not isinstance(value, str) or len(value) > MAX_ID_LENGTH or not _ID_RE.fullmatch(value):
        raise GovernanceGraphSourceError(f"{field_name} must be a safe ID")
    return value


def _optional_id(value: object, field_name: str) -> str | None:
    if value in (None, ""):
        return None
    return _require_id(value, field_name)


def _safe_label(value: object, *, default: str) -> str:
    if value in (None, ""):
        return default
    if not isinstance(value, str) or len(value) > MAX_TEXT_LENGTH:
        raise GovernanceGraphSourceError("digest label is invalid")
    if any(ord(char) < 32 for char in value) or _SENSITIVE_RE.search(value):
        raise GovernanceGraphSourceError("digest label is unsafe")
    return value


def _node_id(prefix: str, token: str) -> str:
    node_id = f"{prefix}-{token}"
    if len(node_id) > MAX_ID_LENGTH or not _ID_RE.fullmatch(node_id):
        raise GovernanceGraphSourceError("graph node identity is invalid")
    return node_id
