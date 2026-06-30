"""Memory / preferences: two-layer working context (Claude-Code-style).

This category is deliberately *not* a scope-merge stack. It models two distinct
layers that serve different purposes and never override each other:

- **Global preferences** (``<runtime>/preferences.json``): cross-project working
  style, tone, and standing instructions.
- **Project memory** (``<runtime>/{project_id}/memory.json``): per-project
  architecture notes, domain terms, and decisions.

There is no built-in memory layer (built-in is empty). Both layers are lists of
:class:`MemoryEntry` records. Loading is malformed-safe: a bad file degrades to
an empty list, and individual malformed entries are skipped while the rest of
the file still loads.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .scope_resolver import Scope
from .scoped_store import ScopedStore

PREFERENCES_FILE = "preferences.json"
MEMORY_FILE = "memory.json"

_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
_KNOWN_KINDS = ("preference", "architecture", "term", "decision")
_GENERIC_KIND = "note"


class MemoryPrefsError(Exception):
    pass


@dataclass(frozen=True)
class MemoryEntry:
    id: str
    kind: str
    text: str
    enabled: bool = True


def _slug(value: object) -> str:
    text = "".join(
        ch if (ch.isalnum() or ch == "-") else "-"
        for ch in str(value or "").strip().lower()
    ).strip("-")
    while "--" in text:
        text = text.replace("--", "-")
    return text


def _coerce_entry(raw: Any) -> dict[str, Any] | None:
    """Validate + normalize one memory/preference entry, or None if invalid.

    Requires a slug ``id`` matching ``^[a-z0-9][a-z0-9-]*$`` and a non-empty
    ``text``. An unknown ``kind`` falls back to a generic kind rather than being
    rejected.
    """
    if not isinstance(raw, dict):
        return None
    entry_id = _slug(raw.get("id"))
    if not entry_id or not _ID_RE.match(entry_id):
        return None
    text = raw.get("text")
    if not isinstance(text, str) or not text.strip():
        return None
    kind = str(raw.get("kind") or "").strip().lower()
    if kind not in _KNOWN_KINDS:
        kind = _GENERIC_KIND
    entry: dict[str, Any] = {"id": entry_id, "kind": kind, "text": text.strip()}
    entry["enabled"] = raw["enabled"] if isinstance(raw.get("enabled"), bool) else True
    return entry


def _coerce_entries(data: Any, items_key: str) -> list[dict[str, Any]]:
    """Normalize a raw envelope dict into a validated, deduped entry list."""
    if not isinstance(data, dict) or not isinstance(data.get(items_key), list):
        return []
    entries: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in data[items_key]:
        entry = _coerce_entry(raw)
        if entry is None or entry["id"] in seen:
            continue
        seen.add(entry["id"])
        entries.append(entry)
    return entries


def _prefs_store(runtime_dir: str | Path | None) -> ScopedStore:
    return ScopedStore(runtime_dir, PREFERENCES_FILE, default_factory=dict)


def _memory_store(runtime_dir: str | Path | None) -> ScopedStore:
    return ScopedStore(runtime_dir, MEMORY_FILE, default_factory=dict)


def _validate_and_normalize(entries: Any, items_key: str) -> list[dict[str, Any]]:
    if not isinstance(entries, list):
        raise MemoryPrefsError(f"{items_key} must be a list")
    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in entries:
        entry = _coerce_entry(raw)
        if entry is None:
            raise MemoryPrefsError("each entry requires a valid slug id and non-empty text")
        if entry["id"] in seen:
            raise MemoryPrefsError(f"duplicate entry id: {entry['id']}")
        seen.add(entry["id"])
        normalized.append(entry)
    return normalized


# --- Global preferences (no project scope) -----------------------------------

def load_preferences(runtime_dir: str | Path | None) -> list[dict[str, Any]]:
    """Load global preferences, or [] on missing/malformed input."""
    data = _prefs_store(runtime_dir).load(Scope.GLOBAL, None)
    return _coerce_entries(data, "preferences")


def save_preferences(
    runtime_dir: str | Path | None, entries: Any
) -> list[dict[str, Any]]:
    """Validate + atomically persist global preferences. Returns the saved list."""
    normalized = _validate_and_normalize(entries, "preferences")
    _prefs_store(runtime_dir).save(
        Scope.GLOBAL, {"version": 1, "preferences": normalized}, None
    )
    return normalized


# --- Project memory (project scope only) -------------------------------------

def load_memory(
    runtime_dir: str | Path | None, project_id: str | None
) -> list[dict[str, Any]]:
    """Load project memory, or [] when no project id / missing / malformed."""
    if not project_id:
        return []
    data = _memory_store(runtime_dir).load(Scope.PROJECT, project_id)
    return _coerce_entries(data, "memory")


def save_memory(
    runtime_dir: str | Path | None, project_id: str | None, entries: Any
) -> list[dict[str, Any]]:
    """Validate + atomically persist project memory. Returns the saved list.

    Raises :class:`MemoryPrefsError` when no project id is supplied or input is
    invalid.
    """
    if not project_id:
        raise MemoryPrefsError("project memory requires a project id")
    normalized = _validate_and_normalize(entries, "memory")
    _memory_store(runtime_dir).save(
        Scope.PROJECT, {"version": 1, "memory": normalized}, project_id
    )
    return normalized


def resolve_view(
    runtime_dir: str | Path | None,
    project_id: str | None = None,
) -> dict[str, Any]:
    """Build the editor/API view: global preferences + project memory.

    Project memory is empty unless a ``project_id`` is supplied.
    """
    return {
        "version": 1,
        "projectId": project_id or "",
        "preferences": load_preferences(runtime_dir),
        "memory": load_memory(runtime_dir, project_id),
    }
