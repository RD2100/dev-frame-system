"""Citation integrity helpers for offline paper MVP validation.

This module never queries external services. It classifies citation evidence
that has already been provided by synthetic fixtures or explicit caller input.
"""

from __future__ import annotations

from typing import Any

VERIFIED_SOURCE = "VERIFIED_SOURCE"
USER_NOTE_LEAD = "USER_NOTE_LEAD"
NEEDS_VERIFICATION = "NEEDS_VERIFICATION"
GENERAL_MODEL_SUGGESTION = "GENERAL_MODEL_SUGGESTION"
SOURCE_NOT_AVAILABLE = "SOURCE_NOT_AVAILABLE"

SOURCE_LEVELS = {
    VERIFIED_SOURCE,
    USER_NOTE_LEAD,
    NEEDS_VERIFICATION,
    GENERAL_MODEL_SUGGESTION,
    SOURCE_NOT_AVAILABLE,
}

FORBIDDEN_CITATION_FIELDS = {
    "abstract",
    "abstractNote",
    "attachmentPath",
    "file",
    "filePath",
    "note",
    "notes",
    "pdf_full_text",
    "private_notes_raw",
    "attachments_raw",
    "user_annotations_raw",
    "local_file_path_to_private_pdf",
}


def _has_forbidden_fields(record: dict[str, Any] | None) -> bool:
    return bool(record and FORBIDDEN_CITATION_FIELDS.intersection(record))


def classify_citation_evidence(
    *,
    zotero_metadata: dict[str, Any] | None = None,
    obsidian_note: dict[str, Any] | None = None,
    model_suggestion: str | None = None,
    citation_claim: dict[str, Any] | None = None,
    metadata_lookup_result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Classify citation evidence without fabricating source certainty."""
    if metadata_lookup_result:
        match_status = metadata_lookup_result.get("match_status")
        if match_status == VERIFIED_SOURCE:
            return {
                "source_level": VERIFIED_SOURCE,
                "source_available": True,
                "blocked": False,
                "reason": "metadata_lookup_verified_source",
                "record_fingerprint": metadata_lookup_result.get("record_fingerprint"),
            }
        if match_status == "AMBIGUOUS_MATCH":
            return {
                "source_level": NEEDS_VERIFICATION,
                "source_available": True,
                "blocked": False,
                "reason": "metadata_lookup_ambiguous_match",
                "record_fingerprint": metadata_lookup_result.get("record_fingerprint"),
            }
        if match_status == "BLOCKED_RAW_METADATA":
            return {
                "source_level": NEEDS_VERIFICATION,
                "source_available": False,
                "blocked": True,
                "reason": "metadata_lookup_blocked_raw_metadata",
            }
        if match_status == SOURCE_NOT_AVAILABLE:
            return {
                "source_level": SOURCE_NOT_AVAILABLE,
                "source_available": False,
                "blocked": True,
                "reason": "metadata_lookup_source_not_available",
            }
        return {
            "source_level": NEEDS_VERIFICATION,
            "source_available": False,
            "blocked": False,
            "reason": "metadata_lookup_needs_verification",
        }

    claim = citation_claim or {}
    fabricated_fields = [
        field for field in ("author", "year", "title", "journal", "doi", "page")
        if claim.get(field) and not (zotero_metadata or obsidian_note)
    ]

    if _has_forbidden_fields(zotero_metadata) or _has_forbidden_fields(obsidian_note):
        return {
            "source_level": NEEDS_VERIFICATION,
            "source_available": False,
            "blocked": True,
            "reason": "forbidden_private_source_field_present",
            "fabricated_fields": fabricated_fields,
        }

    if zotero_metadata:
        return {
            "source_level": VERIFIED_SOURCE,
            "source_available": True,
            "blocked": False,
            "reason": "zotero_metadata_available",
            "citation_key": zotero_metadata.get("citation_key")
            or zotero_metadata.get("citekey"),
            "doi": zotero_metadata.get("doi"),
        }

    if obsidian_note:
        return {
            "source_level": USER_NOTE_LEAD,
            "source_available": True,
            "blocked": False,
            "reason": "obsidian_note_is_lead_not_verified_source",
            "citation_key": obsidian_note.get("citation_key"),
        }

    if fabricated_fields:
        return {
            "source_level": SOURCE_NOT_AVAILABLE,
            "source_available": False,
            "blocked": True,
            "reason": "citation_claim_without_source",
            "fabricated_fields": fabricated_fields,
        }

    if model_suggestion:
        return {
            "source_level": GENERAL_MODEL_SUGGESTION,
            "source_available": False,
            "blocked": False,
            "reason": "model_suggestion_is_not_citation_evidence",
        }

    return {
        "source_level": SOURCE_NOT_AVAILABLE,
        "source_available": False,
        "blocked": True,
        "reason": "source_not_available",
    }
