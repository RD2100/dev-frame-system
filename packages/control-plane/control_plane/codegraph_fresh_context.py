"""Explicit CodeGraph freshness-to-context composition.

The helper is opt-in caller plumbing.  It performs one read-only status query
before one no-code context query and forwards only the sanitized freshness
fields; it never refreshes the index or changes the default context path.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from .codegraph_json_transport import query_codegraph_context
from .codegraph_status_transport import query_codegraph_status


FRESHNESS_STATES = frozenset({"current", "stale", "unknown"})
INDEX_STATUSES = frozenset({"current", "stale", "missing", "unknown"})
MAX_PENDING_COUNT = 10_000_000


class CodeGraphFreshContextError(ValueError):
    """Raised when a status attestation cannot be safely composed."""


def query_codegraph_context_with_status(
    *,
    project_root: str | Path,
    task: str,
    graph_projection_id: str,
    project_id: str,
    resource_id: str,
    index_name: str,
    privacy_class: str = "local_path_only",
    source_snapshot_refs: Sequence[str] = (),
    max_nodes: int = 50,
    timeout_seconds: float = 15.0,
    executable: str | None = None,
) -> dict[str, Any]:
    """Query status first, then explicitly bind its freshness to context."""
    status_kwargs: dict[str, Any] = {
        "project_root": project_root,
        "project_id": project_id,
        "resource_id": resource_id,
        "index_name": index_name,
        "timeout_seconds": timeout_seconds,
    }
    context_kwargs: dict[str, Any] = {
        "project_root": project_root,
        "task": task,
        "graph_projection_id": graph_projection_id,
        "project_id": project_id,
        "resource_id": resource_id,
        "index_name": index_name,
        "privacy_class": privacy_class,
        "source_snapshot_refs": source_snapshot_refs,
        "max_nodes": max_nodes,
        "timeout_seconds": timeout_seconds,
    }
    if executable is not None:
        status_kwargs["executable"] = executable
        context_kwargs["executable"] = executable
    status = query_codegraph_status(**status_kwargs)
    _validate_attestation(status, project_id, resource_id, index_name)
    context_kwargs["index_status"] = status["index_status"]
    context_kwargs["index_freshness"] = status["index_freshness"]
    projection = query_codegraph_context(**context_kwargs)
    return _attach_attestation(projection, status)


def _validate_attestation(
    status: Mapping[str, Any],
    project_id: str,
    resource_id: str,
    index_name: str,
) -> None:
    if not isinstance(status, Mapping):
        raise CodeGraphFreshContextError("status attestation is invalid")
    if any(
        status.get(field) != expected
        for field, expected in (
            ("project_id", project_id),
            ("resource_id", resource_id),
            ("index_name", index_name),
        )
    ):
        raise CodeGraphFreshContextError("status attestation identity mismatch")
    if (
        not isinstance(status.get("index_status"), str)
        or status["index_status"] not in INDEX_STATUSES
    ):
        raise CodeGraphFreshContextError("status attestation status is invalid")
    if (
        not isinstance(status.get("index_freshness"), str)
        or status["index_freshness"] not in FRESHNESS_STATES
    ):
        raise CodeGraphFreshContextError("status attestation freshness is invalid")
    if status.get("trusted_for_current_run") is not False:
        raise CodeGraphFreshContextError("status attestation trust is invalid")
    _validate_pending(status.get("pending_changes"))


def _validate_pending(value: object) -> None:
    if not isinstance(value, Mapping):
        raise CodeGraphFreshContextError("status attestation pending changes are invalid")
    if set(value) != {"added", "modified", "removed"}:
        raise CodeGraphFreshContextError("status attestation pending changes are invalid")
    for count in value.values():
        if (
            isinstance(count, bool)
            or not isinstance(count, int)
            or count < 0
            or count > MAX_PENDING_COUNT
        ):
            raise CodeGraphFreshContextError("status attestation pending changes are invalid")


def _attach_attestation(
    projection: Mapping[str, Any], status: Mapping[str, Any]
) -> dict[str, Any]:
    if not isinstance(projection, Mapping):
        raise CodeGraphFreshContextError("context projection is invalid")
    adapter = projection.get("source_adapter")
    if not isinstance(adapter, Mapping):
        raise CodeGraphFreshContextError("context source metadata is invalid")
    result = dict(projection)
    result["source_adapter"] = {
        **adapter,
        "freshness_attestation": {
            "transport": "codegraph_status_json",
            "index_status": status["index_status"],
            "index_freshness": status["index_freshness"],
            "pending_changes": dict(status["pending_changes"]),
            "trusted_for_current_run": False,
        },
    }
    return result
