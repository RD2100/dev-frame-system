"""Offline loader for the public agent-runtime JSON Schema bundle.

The canonical schemas intentionally use stable HTTPS identifiers so records are
portable.  Consumers must not fetch those URLs at validation time: this loader
builds a ``referencing.Registry`` only from the checked-out public schema
bundle selected by ``offline-schema-registry.json``.
"""

from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.exceptions import SchemaError
from referencing import Registry, Resource


class AgentRuntimeSchemaError(ValueError):
    """Raised when a local agent-runtime schema bundle is malformed."""


_MANIFEST_FILENAME = "offline-schema-registry.json"
_CANONICAL_AGENT_RUNTIME_BASE_URI = "https://rd2100.devframe/schemas/agent-runtime/"
_FORMAT_CHECKER = FormatChecker()


@_FORMAT_CHECKER.checks("date-time")
def _is_timezone_aware_datetime(value: object) -> bool:
    if not isinstance(value, str):
        return True
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return parsed.tzinfo is not None and parsed.utcoffset() is not None


def load_offline_validator(
    schema_filename: str,
    schema_dir: str | Path,
) -> Draft202012Validator:
    """Load one canonical schema with sibling references resolved locally.

    ``schema_dir`` must be the public ``schemas/agent-runtime`` directory
    supplied by the client.  No network retrieval or machine-specific path is
    used, so the same bundle works for Codex, RD-CODE, Claude Code, and other
    executor clients.
    """
    root = _schema_directory(schema_dir)
    entries = _load_manifest_entries(root)
    schema_path = _resource_path(root, schema_filename)
    if schema_filename not in {entry["file"] for entry in entries}:
        raise AgentRuntimeSchemaError("schema is not registered for offline validation")
    return Draft202012Validator(
        _load_json(schema_path),
        registry=_offline_registry(root, entries),
        format_checker=_FORMAT_CHECKER,
    )


def _offline_registry(root: Path, entries: list[dict[str, str]]) -> Registry:
    resources: list[tuple[str, Resource[Any]]] = []
    for entry in entries:
        contents = _load_json(_resource_path(root, entry["file"]))
        schema_id = contents.get("$id")
        if schema_id is not None and schema_id != entry["uri"]:
            raise AgentRuntimeSchemaError("offline schema registry URI does not match schema identifier")
        try:
            Draft202012Validator.check_schema(contents)
        except SchemaError as exc:
            raise AgentRuntimeSchemaError("offline schema resource is invalid") from exc
        resources.append(
            (
                entry["uri"],
                Resource.from_contents(contents),
            )
        )
    return Registry().with_resources(resources)


def _schema_directory(schema_dir: str | Path) -> Path:
    root = Path(schema_dir).resolve()
    if not root.is_dir():
        raise AgentRuntimeSchemaError("schema_dir must be an existing directory")
    return root


def _load_manifest_entries(root: Path) -> list[dict[str, str]]:
    manifest = _load_json(_resource_path(root, _MANIFEST_FILENAME))
    if not isinstance(manifest, dict) or manifest.get("version") != "agent-runtime-offline-registry.v1":
        raise AgentRuntimeSchemaError("offline schema registry version is unsupported")
    resources = manifest.get("resources")
    if not isinstance(resources, list) or not resources:
        raise AgentRuntimeSchemaError("offline schema registry resources must be a non-empty array")

    entries: list[dict[str, str]] = []
    seen_uris: set[str] = set()
    seen_files: set[str] = set()
    for item in resources:
        if not isinstance(item, dict):
            raise AgentRuntimeSchemaError("offline schema registry resource must be an object")
        uri = item.get("uri")
        filename = item.get("file")
        if not isinstance(uri, str) or not uri or not isinstance(filename, str) or not filename:
            raise AgentRuntimeSchemaError("offline schema registry resource is invalid")
        if uri != f"{_CANONICAL_AGENT_RUNTIME_BASE_URI}{filename}":
            raise AgentRuntimeSchemaError("offline schema registry URI must be canonical")
        if uri in seen_uris or filename in seen_files:
            raise AgentRuntimeSchemaError("offline schema registry contains duplicate resources")
        _resource_path(root, filename)
        seen_uris.add(uri)
        seen_files.add(filename)
        entries.append({"uri": uri, "file": filename})
    return entries


def _resource_path(root: Path, filename: str) -> Path:
    candidate = (root / filename).resolve()
    if (
        Path(filename).name != filename
        or candidate.parent != root
        or candidate.suffix != ".json"
        or not candidate.is_file()
    ):
        raise AgentRuntimeSchemaError("offline schema resource must be a sibling JSON file")
    return candidate


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AgentRuntimeSchemaError("offline schema resource cannot be loaded") from exc
    if not isinstance(value, dict):
        raise AgentRuntimeSchemaError("offline schema resource must be a JSON object")
    return value
