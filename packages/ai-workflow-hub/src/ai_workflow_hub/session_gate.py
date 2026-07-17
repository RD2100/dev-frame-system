"""Fail-closed validation for .aiworkflow/session/current.json."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REQUIRED_FACTS: dict[str, Any] = {
    "status": "ready_for_file_edits",
    "startup_gate.active_memory_loaded": True,
    "startup_gate.project_conventions_loaded": True,
    "startup_gate.required_skills_loaded": True,
    "startup_gate.slice_plan_created": True,
}

# Compatibility for callers that imported the previous constant.
REQUIRED_FIELDS = REQUIRED_FACTS


def _marker_path(project_path: str) -> Path:
    return Path(project_path) / ".aiworkflow" / "session" / "current.json"


def _get_nested(data: Any, key: str) -> Any:
    value = data
    for part in key.split("."):
        if not isinstance(value, dict):
            return None
        value = value.get(part)
    return value


def _fact_passes(actual: Any, expected: Any) -> bool:
    if isinstance(expected, bool):
        return actual is True
    return actual == expected


def initialize_session_marker(
    project_path: str, created_by: str = "aihub"
) -> dict[str, Any]:
    """Create a marker with pending facts; never attest work automatically."""
    marker = _marker_path(project_path)
    marker.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "status": "pending",
        "startup_gate": {
            "active_memory_loaded": False,
            "project_conventions_loaded": False,
            "required_skills_loaded": False,
            "slice_plan_created": False,
        },
        "project_path": str(Path(project_path).resolve()),
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "auto_created_by": created_by,
    }
    marker.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    return {
        "path": str(marker),
        "initialized": True,
        "complete": False,
        "missing_fields": list(REQUIRED_FACTS),
        "malformed": False,
        "stale": False,
        "reason": "initialized",
    }


def validate_session_marker(project_path: str) -> dict[str, Any]:
    """Validate the existing marker without mutating or repairing it."""
    marker = _marker_path(project_path)
    if not marker.exists():
        return {
            "path": str(marker),
            "complete": False,
            "missing_fields": list(REQUIRED_FACTS),
            "malformed": False,
            "stale": False,
            "reason": "marker_missing",
        }

    try:
        data = json.loads(marker.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return {
            "path": str(marker),
            "complete": False,
            "missing_fields": list(REQUIRED_FACTS),
            "malformed": True,
            "stale": False,
            "reason": "malformed_json",
        }

    if not isinstance(data, dict):
        return {
            "path": str(marker),
            "complete": False,
            "missing_fields": list(REQUIRED_FACTS),
            "malformed": True,
            "stale": False,
            "reason": "not_object",
        }

    stored_project = data.get("project_path")
    stale = (
        stored_project is not None
        and stored_project != str(Path(project_path).resolve())
    )
    missing_fields = [
        key
        for key, expected in REQUIRED_FACTS.items()
        if not _fact_passes(_get_nested(data, key), expected)
    ]
    complete = not missing_fields and not stale
    reason = "stale" if stale else "incomplete" if missing_fields else "ok"
    return {
        "path": str(marker),
        "complete": complete,
        "missing_fields": missing_fields,
        "malformed": False,
        "stale": stale,
        "reason": reason,
    }


def ensure_session_marker(
    project_path: str, created_by: str = "aihub"
) -> dict[str, Any]:
    """Initialize only a missing marker, then validate its actual facts."""
    marker = _marker_path(project_path)
    initialized = False
    if not marker.exists():
        initialize_session_marker(project_path, created_by)
        initialized = True
    result = validate_session_marker(project_path)
    result["initialized"] = initialized
    return result
