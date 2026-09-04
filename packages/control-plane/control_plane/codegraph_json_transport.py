"""Read-only transport from CodeGraph JSON context to a graph projection.

The transport accepts only the bounded JSON emitted by ``codegraph context``
with ``--no-code``.  It never initializes, syncs, or reads the CodeGraph
database directly.  Normalization is delegated to the existing snapshot
adapter so authority, privacy, freshness, and graph validation stay in one
place.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
import json
import os
from pathlib import Path
import re
import subprocess
from typing import Any

from .codegraph_snapshot_source import (
    CodeGraphSnapshotError,
    FRESHNESS_STATES,
    INDEX_STATUSES,
    NODE_KINDS,
    PRIVACY_CLASSES,
    RELATION_KINDS,
    build_codegraph_snapshot_projection,
)


TRANSPORT_VERSION = "codegraph-json-context.0.1"
DEFAULT_EXECUTABLE = "codegraph.cmd" if os.name == "nt" else "codegraph"
MAX_NODES = 512
MAX_RELATIONS = 1024
MAX_ENTRY_POINTS = 128
MAX_OUTPUT_CHARS = 1_000_000
MAX_TASK_LENGTH = 512
MAX_TEXT_LENGTH = 256
MAX_PATH_LENGTH = 512
MAX_TIMEOUT_SECONDS = 30.0
_PAYLOAD_FIELDS = {
    "query",
    "summary",
    "entryPoints",
    "nodes",
    "edges",
    "codeBlocks",
    "relatedFiles",
    "stats",
}
_NODE_FIELDS = {
    "id",
    "kind",
    "name",
    "qualifiedName",
    "filePath",
    "language",
    "startLine",
    "endLine",
    "isAsync",
    "isExported",
    "isStatic",
    "signature",
    "visibility",
}
_EDGE_FIELDS = {"id", "source", "target", "kind", "line", "column"}
_STATS_FIELDS = {
    "nodeCount",
    "edgeCount",
    "fileCount",
    "codeBlockCount",
    "totalCodeSize",
    "truncated",
}
_PATH_RE = re.compile(r"^[A-Za-z0-9._~+/-]{1,512}$")
_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_SENSITIVE_RE = re.compile(
    r"(?i)(?:api[_-]?key|authorization|bearer|cookie|password|secret|token)"
    r"|sk-[A-Za-z0-9_-]{12,}"
)


class CodeGraphJsonTransportError(ValueError):
    """Raised when CodeGraph JSON cannot be read or safely projected."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def build_codegraph_context_projection(
    payload: Mapping[str, Any],
    *,
    graph_projection_id: str,
    project_id: str,
    resource_id: str,
    index_name: str,
    index_status: str = "unknown",
    index_freshness: str = "unknown",
    privacy_class: str = "local_path_only",
    source_snapshot_refs: Sequence[str] = (),
) -> dict[str, Any]:
    """Map one no-code CodeGraph JSON response into a governed projection."""
    _validate_metadata(
        resource_id,
        index_name,
        index_status,
        index_freshness,
        privacy_class,
    )
    nodes, relations, relation_kinds = _normalize_payload(payload, privacy_class)
    return _build_projection(
        nodes,
        relations,
        relation_kinds,
        graph_projection_id=graph_projection_id,
        project_id=project_id,
        resource_id=resource_id,
        index_name=index_name,
        index_status=index_status,
        index_freshness=index_freshness,
        source_snapshot_refs=source_snapshot_refs,
    )


def _build_projection(
    nodes: list[dict[str, Any]],
    relations: list[dict[str, Any]],
    relation_kinds: Mapping[str, str],
    *,
    graph_projection_id: str,
    project_id: str,
    resource_id: str,
    index_name: str,
    index_status: str,
    index_freshness: str,
    source_snapshot_refs: Sequence[str],
) -> dict[str, Any]:
    snapshot = {
        "project_id": project_id,
        "resource_id": resource_id,
        "index_name": index_name,
        "index_status": index_status,
        "index_freshness": index_freshness,
        "trusted_for_current_run": False,
        "nodes": nodes,
        "relations": relations,
    }
    try:
        projection = build_codegraph_snapshot_projection(
            snapshot,
            graph_projection_id=graph_projection_id,
            project_id=project_id,
            source_snapshot_refs=source_snapshot_refs,
        )
    except CodeGraphSnapshotError as exc:
        raise CodeGraphJsonTransportError("invalid_payload", str(exc)) from exc
    for edge in projection["edges"]:
        edge["relation_kind"] = relation_kinds[str(edge["id"])]
    projection["source_adapter"] = {
        **projection["source_adapter"],
        "id": TRANSPORT_VERSION,
        "transport": "codegraph_json_context",
        "trusted_for_current_run": False,
        "response_node_count": len(nodes),
        "response_relation_count": len(relations),
    }
    return projection


def query_codegraph_context(
    *,
    project_root: str | Path,
    task: str,
    graph_projection_id: str,
    project_id: str,
    resource_id: str,
    index_name: str,
    index_status: str = "unknown",
    index_freshness: str = "unknown",
    privacy_class: str = "local_path_only",
    source_snapshot_refs: Sequence[str] = (),
    max_nodes: int = 50,
    timeout_seconds: float = 15.0,
    executable: str = DEFAULT_EXECUTABLE,
) -> dict[str, Any]:
    """Run one bounded CodeGraph context query without shell or write access."""
    root = _project_root(project_root)
    safe_task = _task(task)
    safe_max_nodes = _max_nodes(max_nodes)
    safe_timeout = _timeout(timeout_seconds)
    safe_executable = _executable(executable)
    argv = _context_argv(safe_executable, safe_max_nodes, root, safe_task)
    stdout = _run_context(argv, root, safe_timeout)
    payload = _parse_context_output(stdout)
    return build_codegraph_context_projection(
        payload,
        graph_projection_id=graph_projection_id,
        project_id=project_id,
        resource_id=resource_id,
        index_name=index_name,
        index_status=index_status,
        index_freshness=index_freshness,
        privacy_class=privacy_class,
        source_snapshot_refs=source_snapshot_refs,
    )


def _context_argv(
    executable: str, max_nodes: int, root: Path, task: str
) -> list[str]:
    return [
        executable,
        "context",
        "--format",
        "json",
        "--max-nodes",
        str(max_nodes),
        "--no-code",
        "--path",
        str(root),
        task,
    ]


def _run_context(argv: list[str], root: Path, timeout: float) -> str:
    try:
        result = subprocess.run(
            argv,
            cwd=root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="strict",
            timeout=timeout,
            check=False,
            shell=False,
        )
    except (subprocess.TimeoutExpired, TimeoutError) as exc:
        raise CodeGraphJsonTransportError(
            "timeout", "CodeGraph context query timed out"
        ) from exc
    except (FileNotFoundError, OSError) as exc:
        raise CodeGraphJsonTransportError(
            "unavailable", "CodeGraph context command is unavailable"
        ) from exc
    if result.returncode != 0:
        raise CodeGraphJsonTransportError(
            "command_failed", "CodeGraph context command failed"
        )
    stdout = result.stdout
    if not isinstance(stdout, str) or len(stdout) > MAX_OUTPUT_CHARS:
        raise CodeGraphJsonTransportError(
            "output_too_large", "CodeGraph context output exceeds the limit"
        )
    return stdout


def _parse_context_output(stdout: str) -> Mapping[str, Any]:
    try:
        payload = json.loads(stdout)
    except (TypeError, json.JSONDecodeError) as exc:
        raise CodeGraphJsonTransportError(
            "malformed_json", "CodeGraph context returned malformed JSON"
        ) from exc
    return _mapping(payload, "CodeGraph JSON payload")


def _normalize_payload(
    payload: Mapping[str, Any], privacy_class: str
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, str]]:
    data = _mapping(payload, "CodeGraph JSON payload")
    _allowlisted(data, _PAYLOAD_FIELDS, "CodeGraph JSON payload")
    _validate_text(data.get("query"), "query", required=False)
    _validate_text(data.get("summary"), "summary", required=False)
    _validate_code_blocks(data.get("codeBlocks", []))
    _validate_related_files(data.get("relatedFiles", []))
    _validate_stats(data.get("stats", {}))
    raw_nodes = _bounded_list(data.get("nodes"), "nodes", MAX_NODES)
    raw_edges = _bounded_list(data.get("edges", []), "edges", MAX_RELATIONS)
    _validate_entry_points(data.get("entryPoints", []))
    if not raw_nodes:
        raise CodeGraphJsonTransportError("invalid_payload", "nodes must not be empty")
    nodes = [_node_record(raw, privacy_class) for raw in raw_nodes]
    node_ids = {node["id"] for node in nodes}
    relations: list[dict[str, Any]] = []
    relation_kinds: dict[str, str] = {}
    for index, raw in enumerate(raw_edges):
        relation, relation_kind = _edge_record(
            raw, index, node_ids, privacy_class
        )
        relations.append(relation)
        relation_kinds[relation["id"]] = relation_kind
    return nodes, relations, relation_kinds


def _node_record(raw: object, privacy_class: str) -> dict[str, Any]:
    node = _mapping(raw, "CodeGraph node")
    _allowlisted(node, _NODE_FIELDS, "CodeGraph node")
    node_id = _safe_id(node.get("id"), "node.id")
    kind = node.get("kind")
    if not isinstance(kind, str) or kind not in NODE_KINDS:
        raise CodeGraphJsonTransportError("invalid_payload", "CodeGraph node kind is invalid")
    path = _safe_relative_path(node.get("filePath"), "node file path")
    label = _node_label(node)
    record: dict[str, Any] = {
        "id": node_id,
        "kind": kind,
        "privacy_class": privacy_class,
        "source_ref": _source_ref(path, node_id),
    }
    if label is not None:
        record["label"] = label
    return record


def _edge_record(
    raw: object,
    index: int,
    node_ids: set[str],
    privacy_class: str,
) -> tuple[dict[str, Any], str]:
    edge = _mapping(raw, "CodeGraph edge")
    _allowlisted(edge, _EDGE_FIELDS, "CodeGraph edge")
    source = _safe_id(edge.get("source"), "edge.source")
    target = _safe_id(edge.get("target"), "edge.target")
    if source not in node_ids or target not in node_ids:
        raise CodeGraphJsonTransportError(
            "invalid_payload", "CodeGraph relation endpoint is not in snapshot"
        )
    relation_kind = edge.get("kind")
    if (
        not isinstance(relation_kind, str)
        or (relation_kind not in RELATION_KINDS and relation_kind != "contains")
    ):
        raise CodeGraphJsonTransportError(
            "invalid_payload", "CodeGraph relation kind is invalid"
        )
    relation_id = edge.get("id", f"edge-{index + 1:04d}")
    relation_id = _safe_id(relation_id, "edge.id")
    synthetic_kind = "depends_on" if relation_kind == "contains" else relation_kind
    relation = {
        "id": relation_id,
        "source": source,
        "target": target,
        "kind": synthetic_kind,
        "privacy_class": privacy_class,
    }
    return relation, str(relation_kind)


def _validate_metadata(
    resource_id: str,
    index_name: str,
    index_status: str,
    index_freshness: str,
    privacy_class: str,
) -> None:
    _safe_id(resource_id, "resource_id")
    _safe_text(index_name, "index_name")
    if not isinstance(index_status, str) or index_status not in INDEX_STATUSES:
        raise CodeGraphJsonTransportError("invalid_metadata", "index_status is invalid")
    if (
        not isinstance(index_freshness, str)
        or index_freshness not in FRESHNESS_STATES
    ):
        raise CodeGraphJsonTransportError("invalid_metadata", "index_freshness is invalid")
    if not isinstance(privacy_class, str) or privacy_class not in PRIVACY_CLASSES:
        raise CodeGraphJsonTransportError("invalid_metadata", "privacy_class is invalid")


def _project_root(value: str | Path) -> Path:
    try:
        root = Path(value).resolve(strict=True)
    except (TypeError, OSError, ValueError) as exc:
        raise CodeGraphJsonTransportError("invalid_project", "project root is invalid") from exc
    if not root.is_dir():
        raise CodeGraphJsonTransportError("invalid_project", "project root is invalid")
    return root


def _task(value: object) -> str:
    if not isinstance(value, str) or not value or len(value) > MAX_TASK_LENGTH:
        raise CodeGraphJsonTransportError("invalid_task", "task is invalid")
    if value.startswith("-") or any(ord(char) < 32 for char in value):
        raise CodeGraphJsonTransportError("invalid_task", "task is invalid")
    if _SENSITIVE_RE.search(value):
        raise CodeGraphJsonTransportError("invalid_task", "task is unsafe")
    return value


def _max_nodes(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= MAX_NODES:
        raise CodeGraphJsonTransportError("invalid_max_nodes", "max_nodes is invalid")
    return value


def _timeout(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise CodeGraphJsonTransportError("invalid_timeout", "timeout is invalid")
    result = float(value)
    if result <= 0 or result > MAX_TIMEOUT_SECONDS:
        raise CodeGraphJsonTransportError("invalid_timeout", "timeout is invalid")
    return result


def _executable(value: object) -> str:
    if not isinstance(value, str) or value not in {"codegraph", "codegraph.cmd"}:
        raise CodeGraphJsonTransportError("invalid_executable", "executable is not allowed")
    return str(value)


def _validate_code_blocks(value: object) -> None:
    if not isinstance(value, list):
        raise CodeGraphJsonTransportError("invalid_payload", "code blocks must be a list")
    if value:
        raise CodeGraphJsonTransportError("invalid_payload", "code blocks are not allowed")


def _validate_related_files(value: object) -> None:
    items = _bounded_list(value, "relatedFiles", MAX_NODES)
    for item in items:
        _safe_relative_path(item, "related file path")


def _validate_entry_points(value: object) -> None:
    items = _bounded_list(value, "entryPoints", MAX_ENTRY_POINTS)
    for item in items:
        node = _mapping(item, "CodeGraph entry point")
        _allowlisted(node, _NODE_FIELDS, "CodeGraph entry point")
        _safe_id(node.get("id"), "entry point.id")
        if not isinstance(node.get("kind"), str) or node.get("kind") not in NODE_KINDS:
            raise CodeGraphJsonTransportError("invalid_payload", "entry point kind is invalid")
        if node.get("filePath") is not None:
            _safe_relative_path(node["filePath"], "entry point file path")


def _validate_stats(value: object) -> None:
    stats = _mapping(value, "CodeGraph stats")
    _allowlisted(stats, _STATS_FIELDS, "CodeGraph stats")
    for key, item in stats.items():
        if key == "truncated":
            if type(item) is not bool:
                raise CodeGraphJsonTransportError("invalid_payload", "stats are invalid")
        elif isinstance(item, bool) or not isinstance(item, int) or item < 0 or item > 10_000_000:
            raise CodeGraphJsonTransportError("invalid_payload", "stats are invalid")


def _bounded_list(value: object, name: str, limit: int) -> list[object]:
    if isinstance(value, (str, bytes, bytearray)) or not isinstance(value, list):
        raise CodeGraphJsonTransportError("invalid_payload", f"{name} must be a list")
    if len(value) > limit:
        raise CodeGraphJsonTransportError("invalid_payload", f"{name} exceeds hard limit")
    return value


def _node_label(node: Mapping[str, Any]) -> str | None:
    value = node.get("name") or node.get("qualifiedName")
    if value in (None, ""):
        return None
    return _safe_text(value, "node label")


def _source_ref(path: str, node_id: str) -> str:
    fragment = node_id.replace(":", "-")
    return f"code://{path}#{fragment}"


def _safe_relative_path(value: object, field_name: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) > MAX_PATH_LENGTH
        or not _PATH_RE.fullmatch(value)
        or value.startswith(("/", "\\"))
        or re.match(r"^[A-Za-z]:", value)
        or "\\" in value
        or any(part in {".", ".."} for part in value.split("/"))
    ):
        raise CodeGraphJsonTransportError("invalid_payload", f"{field_name} is unsafe path")
    return value


def _safe_text(value: object, field_name: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or len(value) > MAX_TEXT_LENGTH
        or any(ord(char) < 32 for char in value)
        or _SENSITIVE_RE.search(value)
    ):
        raise CodeGraphJsonTransportError("invalid_payload", f"{field_name} is invalid")
    return value


def _safe_id(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not _ID_RE.fullmatch(value):
        raise CodeGraphJsonTransportError("invalid_payload", f"{field_name} must be a safe ID")
    return value


def _validate_text(value: object, field_name: str, *, required: bool) -> None:
    if value is None and not required:
        return
    _safe_text(value, field_name)


def _mapping(value: object, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise CodeGraphJsonTransportError("invalid_payload", f"{name} must be an object")
    return value


def _allowlisted(value: Mapping[str, Any], allowed: set[str], name: str) -> None:
    if set(value) - allowed:
        raise CodeGraphJsonTransportError(
            "invalid_payload", f"{name} contains unsupported fields"
        )
