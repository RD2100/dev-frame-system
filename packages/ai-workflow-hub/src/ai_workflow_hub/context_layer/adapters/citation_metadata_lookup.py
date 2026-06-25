"""Offline citation metadata lookup for paper citation integrity.

This module only consumes caller-provided fixture or sanitized metadata records.
It does not read Zotero, PDFs, Obsidian vaults, RAG stores, browser state, cloud
services, or WriteLab.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Any

from .citation_integrity import (
    GENERAL_MODEL_SUGGESTION,
    NEEDS_VERIFICATION,
    SOURCE_NOT_AVAILABLE,
    USER_NOTE_LEAD,
    VERIFIED_SOURCE,
)

AMBIGUOUS_MATCH = "AMBIGUOUS_MATCH"
BLOCKED_RAW_METADATA = "BLOCKED_RAW_METADATA"

MATCH_STATUSES = {
    VERIFIED_SOURCE,
    AMBIGUOUS_MATCH,
    NEEDS_VERIFICATION,
    SOURCE_NOT_AVAILABLE,
    BLOCKED_RAW_METADATA,
}

TRUSTED_METADATA_SOURCE_TYPES = {
    "arxiv_public_metadata",
    "openalex_public_metadata",
    "export_metadata",
    "fixture_metadata",
    "sanitized_fixture_metadata",
    "synthetic_zotero_metadata",
    "zotero_metadata",
}

UNVERIFIED_SOURCE_TYPES = {
    "model_memory",
    "obsidian",
    "user_note",
}

FORBIDDEN_LOOKUP_FIELDS = {
    "abstract",
    "abstractNote",
    "annotation",
    "annotations",
    "annote",
    "attachmentPath",
    "attachments_raw",
    "file",
    "filePath",
    "full_text",
    "local_file_path_to_private_pdf",
    "matched_text",
    "note",
    "notes",
    "paragraph_text",
    "pdf",
    "pdf_full_text",
    "pdf_text",
    "private_notes_raw",
    "raw_bibtex",
    "raw_metadata_record",
    "raw_rdf_xml",
    "text_span",
    "user_annotations_raw",
    "writelab_token",
    "zotero_attachment_path",
}


def _utc_now_text() -> str:
    return datetime.now(timezone.utc).isoformat()


def _fingerprint(value: Any) -> str:
    text = json.dumps(value, sort_keys=True, ensure_ascii=False, default=str)
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def _iter_keys(value: Any) -> set[str]:
    if isinstance(value, dict):
        keys = set(value)
        for child in value.values():
            keys.update(_iter_keys(child))
        return keys
    if isinstance(value, list):
        keys: set[str] = set()
        for child in value:
            keys.update(_iter_keys(child))
        return keys
    return set()


def _has_forbidden_lookup_fields(records: list[dict[str, Any]]) -> list[str]:
    forbidden = {field.lower(): field for field in sorted(FORBIDDEN_LOOKUP_FIELDS)}
    found: set[str] = set()
    for record in records:
        for key in _iter_keys(record):
            canonical = forbidden.get(key.lower())
            if canonical:
                found.add(canonical)
    return sorted(found)


def _normalize_text(value: Any) -> str:
    text = str(value or "").casefold()
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def _normalize_doi(value: Any) -> str:
    text = str(value or "").strip().lower()
    text = re.sub(r"^https?://(dx\.)?doi\.org/", "", text)
    text = re.sub(r"^doi:\s*", "", text)
    return text


def _creator_names(value: Any) -> list[str]:
    if isinstance(value, str):
        return [_normalize_text(value)]
    if isinstance(value, list):
        names: list[str] = []
        for item in value:
            if isinstance(item, str):
                names.append(_normalize_text(item))
            elif isinstance(item, dict):
                parts = [
                    item.get("firstName") or item.get("given") or item.get("first"),
                    item.get("lastName") or item.get("family") or item.get("last"),
                    item.get("name"),
                ]
                names.append(_normalize_text(" ".join(str(part) for part in parts if part)))
        return [name for name in names if name]
    return []


def _record_year(record: dict[str, Any]) -> str:
    year = record.get("year")
    if year:
        return str(year)
    date_text = str(record.get("date", "") or "")
    return date_text[:4] if date_text[:4].isdigit() else ""


def _canonical_record(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "citation_key": str(
            record.get("citation_key") or record.get("citekey") or record.get("citationKey") or ""
        ),
        "creators": _creator_names(record.get("creators") or record.get("authors") or record.get("author")),
        "doi": _normalize_doi(record.get("doi") or record.get("DOI")),
        "item_type": str(record.get("item_type") or record.get("itemType") or record.get("type") or ""),
        "source_level": str(record.get("source_level") or VERIFIED_SOURCE),
        "source_type": str(record.get("source_type") or "fixture_metadata"),
        "title": _normalize_text(record.get("title")),
        "url": str(record.get("url") or record.get("URL") or ""),
        "year": _record_year(record),
    }


def _is_trusted_metadata(record: dict[str, Any]) -> bool:
    source_type = str(record.get("source_type") or "fixture_metadata")
    source_level = str(record.get("source_level") or VERIFIED_SOURCE)
    return source_type in TRUSTED_METADATA_SOURCE_TYPES and source_level == VERIFIED_SOURCE


def _redacted_sample(record: dict[str, Any], *, title_fragment_matched: bool, author_matched: bool) -> dict[str, Any]:
    canonical = _canonical_record(record)
    return {
        "item_type": canonical["item_type"],
        "year": canonical["year"],
        "has_doi": bool(canonical["doi"]),
        "has_url": bool(canonical["url"]),
        "title_fragment_matched": title_fragment_matched,
        "author_matched": author_matched,
    }


def _base_report(
    *,
    generated_at: str,
    metadata_records: list[dict[str, Any]],
    metadata_format: str,
) -> dict[str, Any]:
    return {
        "profile": "paper_citation_metadata_lookup_report",
        "schema_version": "1.0",
        "task_id": "OPENCODE_PAPER_CITATION_METADATA_LOOKUP_OFFLINE_A1",
        "project_id": "dev-frame-system",
        "workflow_type": "paper",
        "generated_at": generated_at,
        "metadata_format": metadata_format,
        "candidate_count": len(metadata_records),
        "privacy_boundary": {
            "external_runtime_executed": False,
            "real_zotero_app_accessed": False,
            "real_zotero_api_called": False,
            "real_zotero_storage_read": False,
            "real_metadata_export_read": False,
            "pdf_read": False,
            "full_text_read": False,
            "obsidian_accessed": False,
            "private_rag_executed": False,
            "live_writelab_called": False,
            "browser_cdp_called": False,
            "cloud_called": False,
        },
        "raw_sensitive_fields_absent": True,
        "final_acceptance_claimed": False,
    }


def _result(
    *,
    base: dict[str, Any],
    match_status: str,
    source_level: str,
    confidence_bucket: str,
    matched_fields: list[str] | None = None,
    record_fingerprint: str | None = None,
    redacted_sample: dict[str, Any] | None = None,
    warnings: list[str] | None = None,
) -> dict[str, Any]:
    report = {
        **base,
        "match_status": match_status,
        "source_level": source_level,
        "matched_fields": matched_fields or [],
        "confidence_bucket": confidence_bucket,
        "warnings": warnings or [],
    }
    if record_fingerprint:
        report["record_fingerprint"] = record_fingerprint
    if redacted_sample:
        report["redacted_sample"] = redacted_sample
    return report


def _unique_or_ambiguous(
    *,
    base: dict[str, Any],
    matches: list[tuple[dict[str, Any], list[str], bool, bool]],
) -> dict[str, Any]:
    trusted_matches = [
        (record, fields, title_fragment_matched, author_matched)
        for record, fields, title_fragment_matched, author_matched in matches
        if _is_trusted_metadata(record)
    ]
    if not trusted_matches:
        return _result(
            base=base,
            match_status=NEEDS_VERIFICATION,
            source_level=NEEDS_VERIFICATION,
            confidence_bucket="needs_verification",
            warnings=["matched_record_is_not_trusted_metadata"],
        )
    if len(trusted_matches) > 1:
        fingerprints = [_fingerprint(_canonical_record(record)) for record, *_ in trusted_matches]
        return _result(
            base={**base, "candidate_count": len(trusted_matches)},
            match_status=AMBIGUOUS_MATCH,
            source_level=NEEDS_VERIFICATION,
            confidence_bucket="ambiguous",
            matched_fields=sorted({field for _, fields, *_ in trusted_matches for field in fields}),
            record_fingerprint=_fingerprint(sorted(fingerprints)),
            warnings=["multiple_plausible_metadata_matches"],
        )
    record, fields, title_fragment_matched, author_matched = trusted_matches[0]
    return _result(
        base={**base, "candidate_count": 1},
        match_status=VERIFIED_SOURCE,
        source_level=VERIFIED_SOURCE,
        confidence_bucket="exact" if set(fields) & {"doi", "citation_key"} else "high",
        matched_fields=fields,
        record_fingerprint=_fingerprint(_canonical_record(record)),
        redacted_sample=_redacted_sample(
            record,
            title_fragment_matched=title_fragment_matched,
            author_matched=author_matched,
        ),
    )


def build_citation_metadata_lookup_report(
    *,
    citation_claim: dict[str, Any] | None,
    metadata_records: list[dict[str, Any]] | None,
    lookup_options: dict[str, Any] | None = None,
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Build a minimized citation lookup report from sanitized metadata."""
    records = [record for record in (metadata_records or []) if isinstance(record, dict)]
    options = lookup_options or {}
    metadata_format = str(options.get("metadata_format") or "fixture_metadata")
    generated = generated_at or _utc_now_text()
    base = _base_report(
        generated_at=generated,
        metadata_records=records,
        metadata_format=metadata_format,
    )
    forbidden = _has_forbidden_lookup_fields(records)
    if forbidden:
        return _result(
            base=base,
            match_status=BLOCKED_RAW_METADATA,
            source_level=NEEDS_VERIFICATION,
            confidence_bucket="blocked",
            warnings=[f"forbidden_raw_metadata_field:{field}" for field in forbidden],
        )

    claim = citation_claim or {}
    source_hint = str(claim.get("source_hint") or "").casefold()
    if source_hint in UNVERIFIED_SOURCE_TYPES or source_hint == "general_model_suggestion":
        return _result(
            base=base,
            match_status=NEEDS_VERIFICATION,
            source_level=GENERAL_MODEL_SUGGESTION if "model" in source_hint else USER_NOTE_LEAD,
            confidence_bucket="needs_verification",
            warnings=[f"unverified_source_hint:{source_hint}"],
        )

    claim_doi = _normalize_doi(claim.get("doi"))
    claim_key = str(claim.get("citation_key") or "").casefold()
    claim_author = _normalize_text(claim.get("author"))
    claim_year = str(claim.get("year") or "")
    title_fragment = _normalize_text(claim.get("title_fragment"))

    if not any([claim_doi, claim_key, claim_author, claim_year, title_fragment]):
        return _result(
            base=base,
            match_status=NEEDS_VERIFICATION,
            source_level=NEEDS_VERIFICATION,
            confidence_bucket="needs_verification",
            warnings=["citation_claim_has_no_lookup_keys"],
        )

    doi_matches: list[tuple[dict[str, Any], list[str], bool, bool]] = []
    key_matches: list[tuple[dict[str, Any], list[str], bool, bool]] = []
    fragment_matches: list[tuple[dict[str, Any], list[str], bool, bool]] = []
    for record in records:
        canonical = _canonical_record(record)
        if str(record.get("source_type") or "") in UNVERIFIED_SOURCE_TYPES:
            continue
        if claim_doi and canonical["doi"] and claim_doi == canonical["doi"]:
            doi_matches.append((record, ["doi"], False, False))
            continue
        if claim_key and canonical["citation_key"].casefold() == claim_key:
            key_matches.append((record, ["citation_key"], False, False))
            continue
        author_matched = bool(claim_author and any(claim_author in creator for creator in canonical["creators"]))
        year_matched = bool(claim_year and canonical["year"] == claim_year)
        title_matched = bool(title_fragment and title_fragment in canonical["title"])
        if author_matched and year_matched and title_matched:
            fragment_matches.append(
                (record, ["author", "year", "title_fragment"], title_matched, author_matched)
            )

    if doi_matches:
        return _unique_or_ambiguous(base=base, matches=doi_matches)
    if key_matches:
        return _unique_or_ambiguous(base=base, matches=key_matches)
    if fragment_matches:
        return _unique_or_ambiguous(base=base, matches=fragment_matches)

    return _result(
        base=base,
        match_status=SOURCE_NOT_AVAILABLE,
        source_level=SOURCE_NOT_AVAILABLE,
        confidence_bucket="not_found",
        warnings=["no_metadata_match_found"],
    )
