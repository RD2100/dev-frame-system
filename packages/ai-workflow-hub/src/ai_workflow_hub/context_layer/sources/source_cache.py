"""
Source Cache (A4)
Persistent JSON cache of discovered sources. Supports incremental re-scan
by comparing checksums. Tracks scan timestamp and metadata summaries.
"""
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _empty_cache() -> dict[str, Any]:
    """Create an empty cache structure."""
    return {
        "schema_version": "1.0.0",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "scan_count": 0,
        "sources": {},
    }


def load_cache(cache_path: str | Path) -> dict[str, Any]:
    """Load source cache from disk, or create a new empty cache."""
    path = Path(cache_path)
    if path.exists():
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("schema_version", "") >= "1.0.0":
            return data
    return _empty_cache()


def save_cache(cache: dict[str, Any], cache_path: str | Path) -> None:
    """Save source cache to disk."""
    path = Path(cache_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    cache["updated_at"] = datetime.now(timezone.utc).isoformat()
    path.write_text(
        json.dumps(cache, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def update_cache(
    cache: dict[str, Any],
    discovered: list[dict[str, Any]],
    source_kind: str = "obsidian",
) -> dict[str, Any]:
    """Update cache with newly discovered sources.

    Uses checksum to detect changes. Returns the updated cache.

    Args:
        cache: Existing cache dict.
        discovered: List of discovered source records from vault_scanner.
        source_kind: "obsidian" or "bibtex" — used as a key prefix.

    Returns:
        Updated cache with new/changed sources, removed stale ones.
    """
    current_keys = set()

    for src in discovered:
        key = f"{source_kind}:{src.get('relative_path', src.get('path', ''))}"
        current_keys.add(key)
        checksum = src.get("checksum", "")
        metadata = src.get("metadata", {})

        existing = cache["sources"].get(key)
        if existing and existing.get("checksum") == checksum:
            # No change — keep existing
            continue

        cache["sources"][key] = {
            "path": src.get("path", ""),
            "relative_path": src.get("relative_path", ""),
            "checksum": checksum,
            "source_kind": source_kind,
            "metadata_summary": _summarize_metadata(metadata),
            "added_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

    # Remove stale entries (not in current scan)
    stale_keys = [
        k for k in cache["sources"]
        if k.startswith(f"{source_kind}:") and k not in current_keys
    ]
    for k in stale_keys:
        del cache["sources"][k]

    cache["scan_count"] = cache.get("scan_count", 0) + 1
    cache["updated_at"] = datetime.now(timezone.utc).isoformat()

    return cache


def get_source_paths(cache: dict[str, Any], source_kind: str | None = None) -> list[str]:
    """Get list of source paths from cache, optionally filtered by kind."""
    paths = []
    for key, entry in cache.get("sources", {}).items():
        if source_kind and not key.startswith(f"{source_kind}:"):
            continue
        if entry.get("path"):
            paths.append(entry["path"])
    return paths


def _summarize_metadata(meta: dict[str, Any]) -> dict[str, Any]:
    """Create a lightweight metadata summary for cache display."""
    summary: dict[str, Any] = {}
    for field in ("type", "note_id", "citekey", "title", "year", "chapter",
                  "status", "confidentiality", "tags", "item_type"):
        if field in meta:
            summary[field] = meta[field]
    return summary


def cache_stats(cache: dict[str, Any]) -> dict[str, Any]:
    """Return summary statistics for the source cache."""
    sources = cache.get("sources", {})
    kinds: dict[str, int] = {}
    types: dict[str, int] = {}
    for entry in sources.values():
        kind = entry.get("source_kind", "unknown")
        kinds[kind] = kinds.get(kind, 0) + 1
        note_type = entry.get("metadata_summary", {}).get("type") or entry.get("metadata_summary", {}).get("item_type", "unknown")
        types[note_type] = types.get(note_type, 0) + 1

    return {
        "total_sources": len(sources),
        "by_kind": kinds,
        "by_type": types,
        "scan_count": cache.get("scan_count", 0),
        "last_updated": cache.get("updated_at", ""),
    }
