"""Read-only CodeGraph index-status and freshness attestation.

This module consumes the machine-readable output of ``codegraph status`` only.
It reports bounded metadata for an explicitly bound project root; it never
reads the CodeGraph database directly and never starts an index or refresh.
"""
from __future__ import annotations

from collections.abc import Mapping
import json
import os
from pathlib import Path
import re
import subprocess
from typing import Any


TRANSPORT_VERSION = "codegraph-status-json.0.1"
DEFAULT_EXECUTABLE = "codegraph.cmd" if os.name == "nt" else "codegraph"
MAX_OUTPUT_CHARS = 256_000
MAX_COUNT = 100_000_000
MAX_PENDING_COUNT = 10_000_000
MAX_LIST_ITEMS = 512
MAX_TEXT_LENGTH = 128
MAX_DB_SIZE_BYTES = 10_000_000_000
_STATUS_FIELDS = {
    "initialized",
    "projectPath",
    "fileCount",
    "nodeCount",
    "edgeCount",
    "dbSizeBytes",
    "backend",
    "journalMode",
    "nodesByKind",
    "languages",
    "pendingChanges",
}
_PENDING_FIELDS = {"added", "modified", "removed"}
_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_LABEL_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:+/-]{0,127}$")
_LANGUAGE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+-]{0,63}$")
_SENSITIVE_RE = re.compile(
    r"(?i)(?:api[_-]?key|authorization|bearer|cookie|password|secret|token)"
    r"|sk-[A-Za-z0-9_-]{12,}"
)


class CodeGraphStatusTransportError(ValueError):
    """Raised when CodeGraph status cannot be read or safely attested."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def build_codegraph_status_attestation(
    payload: Mapping[str, Any],
    *,
    project_root: str | Path,
    project_id: str,
    resource_id: str,
    index_name: str,
) -> dict[str, Any]:
    """Build a pathless, conservative status record from one JSON response."""
    root = _project_root(project_root)
    _safe_id(project_id, "project_id")
    _safe_id(resource_id, "resource_id")
    _safe_text(index_name, "index_name")
    status = _normalize_status(payload, root)
    return {
        "project_id": project_id,
        "resource_id": resource_id,
        "index_name": index_name,
        "index_status": status["index_status"],
        "index_freshness": status["index_freshness"],
        "trusted_for_current_run": False,
        "pending_changes": status["pending_changes"],
        "counts": status["counts"],
        "source_adapter": {
            "id": TRANSPORT_VERSION,
            "transport": "codegraph_status_json",
            "read_only": True,
            "root_bound": True,
            "trusted_for_current_run": False,
        },
    }


def query_codegraph_status(
    *,
    project_root: str | Path,
    project_id: str,
    resource_id: str,
    index_name: str,
    timeout_seconds: float = 15.0,
    executable: str = DEFAULT_EXECUTABLE,
) -> dict[str, Any]:
    """Run one bounded ``codegraph status --json`` query without a shell."""
    root = _project_root(project_root)
    timeout = _timeout(timeout_seconds)
    executable_name = _executable(executable)
    argv = [executable_name, "status", "--json", str(root)]
    stdout = _run_status(argv, root, timeout)
    payload = _parse_status_output(stdout)
    return build_codegraph_status_attestation(
        payload,
        project_root=root,
        project_id=project_id,
        resource_id=resource_id,
        index_name=index_name,
    )


def _normalize_status(payload: Mapping[str, Any], root: Path) -> dict[str, Any]:
    data = _mapping(payload, "CodeGraph status payload")
    _allowlisted(data, _STATUS_FIELDS, "CodeGraph status payload")
    initialized = data.get("initialized")
    if type(initialized) is not bool:
        raise CodeGraphStatusTransportError(
            "invalid_status", "initialized status is invalid"
        )
    _verify_project_path(data.get("projectPath"), root)
    counts = _counts(data)
    pending = _pending_counts(data.get("pendingChanges"))
    _validate_metadata_lists(data)
    if not initialized:
        index_status, freshness = "missing", "unknown"
    elif sum(pending.values()) == 0:
        index_status, freshness = "current", "current"
    else:
        index_status, freshness = "stale", "stale"
    return {
        "index_status": index_status,
        "index_freshness": freshness,
        "pending_changes": pending,
        "counts": counts,
    }


def _counts(data: Mapping[str, Any]) -> dict[str, int]:
    fields = {
        "files": "fileCount",
        "nodes": "nodeCount",
        "edges": "edgeCount",
        "db_size_bytes": "dbSizeBytes",
    }
    result: dict[str, int] = {}
    for output_name, field_name in fields.items():
        value = data.get(field_name)
        if isinstance(value, bool) or not isinstance(value, int):
            raise CodeGraphStatusTransportError(
                "invalid_status", "status counts are invalid"
            )
        limit = MAX_DB_SIZE_BYTES if field_name == "dbSizeBytes" else MAX_COUNT
        if value < 0 or value > limit:
            raise CodeGraphStatusTransportError(
                "invalid_status", "status counts exceed the limit"
            )
        result[output_name] = value
    return result


def _pending_counts(value: object) -> dict[str, int]:
    pending = _mapping(value, "pendingChanges")
    _allowlisted(pending, _PENDING_FIELDS, "pendingChanges")
    result: dict[str, int] = {}
    for field_name in sorted(_PENDING_FIELDS):
        count = pending.get(field_name)
        if isinstance(count, bool) or not isinstance(count, int):
            raise CodeGraphStatusTransportError(
                "invalid_status", "pending change counts are invalid"
            )
        if count < 0 or count > MAX_PENDING_COUNT:
            raise CodeGraphStatusTransportError(
                "invalid_status", "pending change counts exceed the limit"
            )
        result[field_name] = count
    return result


def _validate_metadata_lists(data: Mapping[str, Any]) -> None:
    nodes_by_kind = _mapping(data.get("nodesByKind"), "nodesByKind")
    if len(nodes_by_kind) > MAX_LIST_ITEMS:
        raise CodeGraphStatusTransportError(
            "invalid_status", "nodesByKind exceeds the limit"
        )
    for key, value in nodes_by_kind.items():
        _safe_text(key, "node kind")
        if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= MAX_COUNT:
            raise CodeGraphStatusTransportError(
                "invalid_status", "nodesByKind counts are invalid"
            )
    languages = data.get("languages")
    if not isinstance(languages, list) or len(languages) > MAX_LIST_ITEMS:
        raise CodeGraphStatusTransportError(
            "invalid_status", "languages are invalid"
        )
    for language in languages:
        if not isinstance(language, str) or not _LANGUAGE_RE.fullmatch(language):
            raise CodeGraphStatusTransportError(
                "invalid_status", "languages are invalid"
            )
    _safe_label(data.get("backend"), "backend")
    _safe_label(data.get("journalMode"), "journalMode")


def _verify_project_path(value: object, root: Path) -> None:
    if not isinstance(value, str) or not value or len(value) > 1024:
        raise CodeGraphStatusTransportError(
            "invalid_status", "status project binding is invalid"
        )
    try:
        reported = Path(value).resolve(strict=False)
    except (OSError, ValueError) as exc:
        raise CodeGraphStatusTransportError(
            "invalid_status", "status project binding is invalid"
        ) from exc
    if _normalized_path(reported) != _normalized_path(root):
        raise CodeGraphStatusTransportError(
            "invalid_status", "status project binding does not match"
        )


def _run_status(argv: list[str], root: Path, timeout: float) -> str:
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
        raise CodeGraphStatusTransportError(
            "timeout", "CodeGraph status query timed out"
        ) from exc
    except (FileNotFoundError, OSError) as exc:
        raise CodeGraphStatusTransportError(
            "unavailable", "CodeGraph status command is unavailable"
        ) from exc
    if result.returncode != 0:
        raise CodeGraphStatusTransportError(
            "command_failed", "CodeGraph status command failed"
        )
    stdout = result.stdout
    if not isinstance(stdout, str) or len(stdout) > MAX_OUTPUT_CHARS:
        raise CodeGraphStatusTransportError(
            "output_too_large", "CodeGraph status output exceeds the limit"
        )
    return stdout


def _parse_status_output(stdout: str) -> Mapping[str, Any]:
    try:
        payload = json.loads(stdout)
    except (TypeError, json.JSONDecodeError) as exc:
        raise CodeGraphStatusTransportError(
            "malformed_json", "CodeGraph status returned malformed JSON"
        ) from exc
    return _mapping(payload, "CodeGraph status payload")


def _project_root(value: str | Path) -> Path:
    try:
        root = Path(value).resolve(strict=True)
    except (TypeError, OSError, ValueError) as exc:
        raise CodeGraphStatusTransportError(
            "invalid_project", "project root is invalid"
        ) from exc
    if not root.is_dir():
        raise CodeGraphStatusTransportError(
            "invalid_project", "project root is invalid"
        )
    return root


def _timeout(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise CodeGraphStatusTransportError("invalid_timeout", "timeout is invalid")
    result = float(value)
    if result <= 0 or result > 30:
        raise CodeGraphStatusTransportError("invalid_timeout", "timeout is invalid")
    return result


def _executable(value: object) -> str:
    if not isinstance(value, str) or value not in {"codegraph", "codegraph.cmd"}:
        raise CodeGraphStatusTransportError(
            "invalid_executable", "executable is not allowed"
        )
    return value


def _safe_id(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not _ID_RE.fullmatch(value):
        raise CodeGraphStatusTransportError(
            "invalid_metadata", f"{field_name} must be a safe ID"
        )
    return value


def _safe_text(value: object, field_name: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or len(value) > MAX_TEXT_LENGTH
        or any(ord(char) < 32 for char in value)
        or _SENSITIVE_RE.search(value)
        or value.startswith(("/", "\\"))
        or re.match(r"^[A-Za-z]:[\\/]", value)
        or "/" in value
        or "\\" in value
    ):
        raise CodeGraphStatusTransportError(
            "invalid_status", f"{field_name} is invalid"
        )
    return value


def _safe_label(value: object, field_name: str) -> str:
    if (
        not isinstance(value, str)
        or not _LABEL_RE.fullmatch(value)
        or _SENSITIVE_RE.search(value)
    ):
        raise CodeGraphStatusTransportError(
            "invalid_status", f"{field_name} is invalid"
        )
    return value


def _normalized_path(value: Path) -> str:
    return os.path.normcase(os.path.abspath(str(value)))


def _mapping(value: object, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise CodeGraphStatusTransportError("invalid_status", f"{name} must be an object")
    return value


def _allowlisted(value: Mapping[str, Any], allowed: set[str], name: str) -> None:
    if set(value) - allowed:
        raise CodeGraphStatusTransportError(
            "invalid_status", f"{name} contains unsupported fields"
        )
