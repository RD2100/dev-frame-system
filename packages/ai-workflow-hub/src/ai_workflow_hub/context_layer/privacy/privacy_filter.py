"""
Privacy Filter
Filters context sources by confidentiality level.
Fail-closed: missing confidentiality => treated as excluded.
"""
from typing import Any


# Confidentiality levels that are allowed into the context pack
ALLOWED_LEVELS = {"public", "private"}

# Levels that must be excluded
BLOCKED_LEVELS = {"sensitive"}


def classify_source(source: dict[str, Any]) -> dict[str, Any]:
    """Classify a single source record for inclusion or exclusion.

    Args:
        source: dict with at least a "metadata" key containing parsed metadata.
                The metadata must contain a "confidentiality" field.

    Returns:
        {
            "source": source,
            "allowed": bool,
            "reason": str
        }
    """
    metadata = source.get("metadata", {})
    confidentiality = metadata.get("confidentiality")

    # Fail-closed: if confidentiality is missing, treat as excluded
    if confidentiality is None:
        return {
            "source": source,
            "allowed": False,
            "reason": "missing confidentiality field — fail-closed exclusion",
        }

    if confidentiality in BLOCKED_LEVELS:
        return {
            "source": source,
            "allowed": False,
            "reason": f"confidentiality='{confidentiality}' is blocked",
        }

    if confidentiality in ALLOWED_LEVELS:
        return {
            "source": source,
            "allowed": True,
            "reason": f"confidentiality='{confidentiality}' is allowed",
        }

    # Unknown value — fail-closed
    return {
        "source": source,
        "allowed": False,
        "reason": f"unknown confidentiality value '{confidentiality}' — fail-closed exclusion",
    }


def filter_sources(
    obsidian_records: list[dict[str, Any]],
    zotero_records: list[dict[str, Any]],
) -> dict[str, Any]:
    """Apply privacy filtering to all source records.

    Returns:
        {
            "passed": bool,
            "allowed_obsidian": [...],
            "allowed_zotero": [...],
            "excluded_sources": [source_id, ...],
            "excluded_sensitive_sources": [source_id, ...],
        }
    """
    allowed_obsidian = []
    allowed_zotero = []
    excluded_sources: list[str] = []
    excluded_sensitive: list[str] = []

    for record in obsidian_records:
        result = classify_source(record)
        source_id = record.get("metadata", {}).get("note_id", record.get("source_path", "unknown"))
        if result["allowed"]:
            allowed_obsidian.append(record)
        else:
            excluded_sources.append(source_id)
            meta_conf = record.get("metadata", {}).get("confidentiality")
            if meta_conf == "sensitive":
                excluded_sensitive.append(source_id)

    for record in zotero_records:
        result = classify_source(record)
        source_id = record.get("metadata", {}).get("citekey", record.get("source_path", "unknown"))
        if result["allowed"]:
            allowed_zotero.append(record)
        else:
            excluded_sources.append(source_id)
            meta_conf = record.get("metadata", {}).get("confidentiality")
            if meta_conf == "sensitive":
                excluded_sensitive.append(source_id)

    # passed = True if at least some sources are allowed
    passed = len(allowed_obsidian) > 0 or len(allowed_zotero) > 0

    return {
        "passed": passed,
        "allowed_obsidian": allowed_obsidian,
        "allowed_zotero": allowed_zotero,
        "excluded_sources": excluded_sources,
        "excluded_sensitive_sources": excluded_sensitive,
    }
