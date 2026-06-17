"""Synthetic Zotero metadata-only adapter candidate.

The adapter reads only caller-provided fixture files. It does not discover or
connect to a user's real Zotero database and it rejects attachment/full-text
fields.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .citation_integrity import (
    FORBIDDEN_CITATION_FIELDS,
    SOURCE_NOT_AVAILABLE,
    VERIFIED_SOURCE,
)

ALLOWED_ZOTERO_FIELDS = {
    "citation_key",
    "title",
    "authors",
    "year",
    "doi",
    "journal",
    "tags",
    "collections",
    "item_type",
    "source_id",
    "retrieved_at",
}

SANITIZABLE_ZOTERO_FIELDS = {
    "abstract",
    "abstractNote",
    "attachmentPath",
    "file",
    "filePath",
    "note",
    "notes",
}


def load_zotero_metadata_fixture(path: str | Path) -> dict[str, Any]:
    """Load synthetic Zotero metadata and return retrieval evidence."""
    fixture_path = Path(path)
    if not fixture_path.exists():
        return {
            "zotero_status": "SOURCE_NOT_AVAILABLE",
            "source_level": SOURCE_NOT_AVAILABLE,
            "source_available": False,
            "human_required": True,
            "known_gaps": ["fixture path not found; real Zotero access is blocked"],
        }

    data = json.loads(fixture_path.read_text(encoding="utf-8"))
    sanitized_data = {
        key: value
        for key, value in data.items()
        if key not in SANITIZABLE_ZOTERO_FIELDS
    }
    forbidden = sorted(FORBIDDEN_CITATION_FIELDS.intersection(sanitized_data))
    if forbidden:
        return {
            "zotero_status": "REJECTED_FORBIDDEN_FIELDS",
            "source_level": SOURCE_NOT_AVAILABLE,
            "source_available": False,
            "human_required": True,
            "forbidden_fields": forbidden,
            "known_gaps": ["fixture included private/full-text fields"],
        }

    metadata = {
        key: sanitized_data.get(key)
        for key in ALLOWED_ZOTERO_FIELDS
        if key in sanitized_data
    }
    return {
        "zotero_status": "FIXTURE_ONLY",
        "source_level": VERIFIED_SOURCE,
        "source_available": True,
        "metadata": metadata,
        "paper_retrieval_evidence": {
            "source_id": metadata.get("source_id", metadata.get("citation_key", "")),
            "source_type": "zotero_metadata_fixture",
            "citation_key": metadata.get("citation_key"),
            "note_path": None,
            "file_path": None,
            "snippet": "",
            "retrieval_score": 1.0,
            "retrieved_at": metadata.get("retrieved_at"),
            "stale_status": "fresh",
            "source_level": VERIFIED_SOURCE,
            "privacy_level": "public_metadata",
        },
        "human_required": False,
        "known_gaps": ["real Zotero library access requires a dedicated TaskSpec"],
    }
