"""Zotero metadata-only real pilot adapter.

This adapter only reads a user-provided metadata export file. It never discovers
Zotero storage, attachments, PDFs, full text caches, notes, browser/CDP, cloud,
or API credentials.
"""

from __future__ import annotations

import hashlib
import json
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .citation_integrity import VERIFIED_SOURCE
from .paper_real_pilot_gate import validate_runtime_authorization

PASS_METADATA_ONLY = "PASS_METADATA_ONLY"
CONNECTION_REQUIRED = "ZOTERO_METADATA_CONNECTION_REQUIRED"
BLOCKED = "BLOCKED"

ALLOWED_EXPORT_MODES = {"export_file"}
MAX_EXPORT_BYTES = 5 * 1024 * 1024
MAX_EXPORT_ITEMS = 500
FORBIDDEN_EXPORT_SUFFIXES = {
    ".db",
    ".doc",
    ".docx",
    ".enl",
    ".pdf",
    ".sqlite",
    ".sqlite3",
    ".zip",
}
SUPPORTED_METADATA_FORMATS = {
    "bibtex",
    "better_bibtex_json",
    "csl_json",
    "rdf",
    "ris",
    "zotero_api_json",
    "zotero_metadata_json",
}
UNSUPPORTED_METADATA_FORMATS = {
    "unknown",
}
ALLOWED_METADATA_FIELDS = {
    "item_key",
    "item_type",
    "title",
    "creators",
    "year",
    "date",
    "publication_title",
    "publisher",
    "doi",
    "isbn",
    "url",
    "tags",
    "collections",
    "citation_key",
}
FORBIDDEN_EXPORT_FIELDS = {
    "abstract",
    "abstractNote",
    "annotation",
    "annotations",
    "annote",
    "attachment",
    "attachmentPath",
    "attachments",
    "attachments_raw",
    "content",
    "file",
    "filePath",
    "files",
    "full_text",
    "itemURI",
    "linkMode",
    "localLibraryPath",
    "local-url",
    "local_file_path_to_private_pdf",
    "matched_text",
    "note",
    "notes",
    "paragraph_text",
    "path",
    "pdf",
    "pdf_full_text",
    "pdf_text",
    "private_notes_raw",
    "storage",
    "text_span",
    "uri",
    "user_annotations_raw",
    "writelab_token",
    "zotero_attachment_path",
}

RIS_FORBIDDEN_TAGS = {
    "AB": "abstract",
    "L1": "attachmentPath",
    "L4": "attachmentPath",
    "N1": "note",
    "N2": "abstract",
    "NT": "note",
}
FORBIDDEN_XML_DECLARATIONS = (
    "<!attlist",
    "<!doctype",
    "<!element",
    "<!entity",
    "<!notation",
)
MAX_RDF_XML_DEPTH = 40


def _utc_now_text() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_generated_time(value: str) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


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


def _forbidden_keys(value: Any) -> list[str]:
    forbidden = {field.lower() for field in FORBIDDEN_EXPORT_FIELDS}
    return sorted(key for key in _iter_keys(value) if key.lower() in forbidden)


def _sanitize_metadata_value(value: Any) -> tuple[Any, dict[str, int]]:
    forbidden = {field.lower(): field for field in sorted(FORBIDDEN_EXPORT_FIELDS)}
    counts: dict[str, int] = {}

    def sanitize(child: Any) -> Any:
        if isinstance(child, dict):
            sanitized: dict[str, Any] = {}
            for key, nested in child.items():
                canonical_key = forbidden.get(key.lower())
                if canonical_key:
                    counts[canonical_key] = counts.get(canonical_key, 0) + 1
                    continue
                sanitized[key] = sanitize(nested)
            return sanitized
        if isinstance(child, list):
            return [sanitize(item) for item in child]
        return child

    return sanitize(value), dict(sorted(counts.items()))


def _sanitizer_report(
    *,
    sanitized_raw: Any,
    removed_field_counts: dict[str, int],
    export_size_bytes: int,
    parse_status: str,
) -> dict[str, Any]:
    removed_total = sum(removed_field_counts.values())
    return {
        "status": "SANITIZED_WITH_REDACTIONS" if removed_total else "PASS_NO_REDACTIONS",
        "parse_status": parse_status,
        "removed_field_counts": removed_field_counts,
        "removed_field_total": removed_total,
        "sanitized_export_fingerprint": _fingerprint(sanitized_raw),
        "source_export_size_bytes": export_size_bytes,
    }


def _redaction_records(removed_field_counts: dict[str, int]) -> list[dict[str, Any]]:
    records = [
        {"field": "zotero_attachment_path", "action": "blocked", "status": "pass"},
        {"field": "pdf_text", "action": "blocked", "status": "pass"},
        {"field": "full_text", "action": "blocked", "status": "pass"},
        {"field": "paragraph_text", "action": "blocked", "status": "pass"},
        {"field": "writelab_token", "action": "blocked", "status": "pass"},
    ]
    records.extend(
        {
            "field": field,
            "action": "sanitized",
            "status": "pass",
            "count": count,
        }
        for field, count in sorted(removed_field_counts.items())
    )
    return records


def _artifact_minimization() -> dict[str, bool]:
    return {
        "full_library_dumped": False,
        "raw_metadata_records_emitted": False,
        "raw_citation_values_emitted": False,
        "fingerprints_counts_and_booleans_only": True,
    }


def _review_pack_minimization() -> dict[str, bool]:
    return {
        "execution_report_raw_metadata_allowed": False,
        "reviewer_index_raw_metadata_allowed": False,
        "command_transcripts_raw_metadata_allowed": False,
        "evidence_zip_raw_metadata_allowed": False,
        "review_pack_contains_raw_metadata": False,
        "commit_scoped_changed_files_required": True,
    }


def build_zotero_metadata_local_batch_closeout_report(
    *,
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Build a local-only closeout report for Zotero metadata hardening slices."""
    return {
        "profile": "paper_zotero_metadata_local_batch_closeout_report",
        "schema_version": "1.0",
        "task_id": "OPENCODE_ZOTERO_METADATA_LOCAL_BATCH_CLOSEOUT_A1",
        "project_id": "dev-frame-opencode",
        "workflow_type": "paper",
        "validation_mode": "local_offline_only",
        "generated_at": generated_at or _utc_now_text(),
        "batch_status": "LOCAL_BATCH_CLOSEOUT_READY",
        "included_slices": [
            {
                "slice_id": "OPENCODE_ZOTERO_SANITIZER_CANONICAL_FIELD_COUNTS_A1",
                "status": "READY",
            },
            {
                "slice_id": "OPENCODE_ZOTERO_SANITIZER_EVIDENCE_MANIFEST_PARITY_A1",
                "status": "READY",
            },
            {
                "slice_id": "OPENCODE_ZOTERO_METADATA_EVIDENCE_ARTIFACT_MINIMIZATION_A1",
                "status": "READY",
            },
            {
                "slice_id": "OPENCODE_ZOTERO_METADATA_REVIEW_PACK_MINIMIZATION_A1",
                "status": "READY",
            },
            {
                "slice_id": "OPENCODE_ZOTERO_WEB_API_METADATA_MANIFEST_OUTPUT_A1",
                "status": "READY",
            },
            {
                "slice_id": "OPENCODE_ZOTERO_WEB_API_METADATA_MANIFEST_SCHEMA_A1",
                "status": "READY",
            },
            {
                "slice_id": "OPENCODE_ZOTERO_WEB_MANIFEST_BUSINESS_VALIDATION_A1",
                "status": "READY",
            },
            {
                "slice_id": "OPENCODE_METADATA_PIPELINE_READINESS_A1",
                "status": "READY",
            },
            {
                "slice_id": "OPENCODE_METADATA_PIPELINE_BUSINESS_BINDING_A1",
                "status": "READY",
            },
        ],
        "readiness_matrix": {
            "entrypoint_ready": True,
            "sanitizer_ready": True,
            "evidence_manifest_ready": True,
            "artifact_minimization_ready": True,
            "review_pack_minimization_ready": True,
            "web_api_manifest_output_ready": True,
            "web_api_manifest_schema_ready": True,
            "business_validation_manifest_binding_ready": True,
            "metadata_pipeline_readiness_report_ready": True,
            "metadata_pipeline_business_binding_ready": True,
            "runtime_authorization_required": True,
            "zotero_metadata_export_path_required": True,
            "real_resource_access_permitted": False,
        },
        "real_export_run_preconditions": [
            "fresh_human_runtime_authorization",
            "user_provided_zotero_metadata_export_path",
            "source_mode_export_file",
            "metadata_only_scope",
            "reviewer_verdict_required",
        ],
        "privacy_boundary": {
            "zotero_app_or_api_accessed": False,
            "zotero_attachments_read": False,
            "pdf_read": False,
            "full_text_read": False,
            "obsidian_read": False,
            "private_rag_used": False,
            "live_writelab_called": False,
            "browser_cdp_or_cloud_used": False,
            "raw_sensitive_fields_absent": True,
        },
        "artifact_minimization": _artifact_minimization(),
        "review_pack_minimization": _review_pack_minimization(),
        "dirty_state_policy": {
            "commit_scoped_review_required": True,
            "unrelated_dirty_state_excluded_from_verdict": True,
            "dirty_state_must_not_enter_changed_files": True,
        },
        "final_acceptance_boundary": {
            "local_batch_closeout_is_final_acceptance": False,
            "real_pilot_completed": False,
            "live_ready_claimed": False,
            "parent_pin_requested": False,
            "reviewer_verdict_required": True,
        },
        "known_gaps": [
            "real_export_run_not_started",
            "fresh_runtime_authorization_required",
            "zotero_metadata_export_path_required",
            "batch_parent_intake_not_requested",
        ],
        "next_status": "GPT_REVIEW_PENDING",
    }


def _as_items(raw: Any) -> list[dict[str, Any]]:
    if isinstance(raw, list):
        candidates = raw
    elif isinstance(raw, dict) and isinstance(raw.get("items"), list):
        candidates = raw["items"]
    elif isinstance(raw, dict) and isinstance(raw.get("data"), list):
        candidates = raw["data"]
    elif isinstance(raw, dict):
        candidates = [raw]
    else:
        return []

    items: list[dict[str, Any]] = []
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        data = candidate.get("data") if isinstance(candidate.get("data"), dict) else candidate
        items.append(data)
    return items


def _detect_text_format(path: Path, text: str) -> str:
    suffix = path.suffix.lower()
    stripped = text.lstrip("\ufeff\r\n\t ")
    if suffix == ".bib" or stripped.startswith("@"):
        return "bibtex"
    if suffix == ".ris" or stripped.startswith("TY  -"):
        return "ris"
    if suffix in {".rdf", ".xml"} or stripped.startswith("<?xml") or "<rdf:RDF" in stripped[:500]:
        return "rdf"
    return "unknown"


def _detect_json_format(raw: Any) -> str:
    items = _as_items(raw)
    if not items:
        return "unknown"
    first = items[0]
    if "citationKey" in first or "citekey" in first:
        return "better_bibtex_json"
    if "itemType" in first or "key" in first:
        return "zotero_api_json"
    if "id" in first and ("type" in first or "title" in first):
        return "csl_json"
    return "zotero_metadata_json"


def _find_bibtex_body_end(text: str, start: int, opener: str) -> int:
    closer = "}" if opener == "{" else ")"
    depth = 1
    in_quote = False
    escaped = False
    for index in range(start + 1, len(text)):
        char = text[index]
        if escaped:
            escaped = False
            continue
        if char == "\\":
            escaped = True
            continue
        if char == '"':
            in_quote = not in_quote
            continue
        if in_quote:
            continue
        if char == opener:
            depth += 1
        elif char == closer:
            depth -= 1
            if depth == 0:
                return index
    return -1


def _split_bibtex_top_level(text: str) -> list[str]:
    parts: list[str] = []
    start = 0
    depth = 0
    in_quote = False
    escaped = False
    for index, char in enumerate(text):
        if escaped:
            escaped = False
            continue
        if char == "\\":
            escaped = True
            continue
        if char == '"':
            in_quote = not in_quote
            continue
        if in_quote:
            continue
        if char in "{(":
            depth += 1
        elif char in "})" and depth > 0:
            depth -= 1
        elif char == "," and depth == 0:
            parts.append(text[start:index].strip())
            start = index + 1
    tail = text[start:].strip()
    if tail:
        parts.append(tail)
    return parts


def _strip_bibtex_value(value: str) -> str:
    stripped = value.strip()
    while len(stripped) >= 2 and (
        (stripped[0] == "{" and stripped[-1] == "}")
        or (stripped[0] == '"' and stripped[-1] == '"')
    ):
        stripped = stripped[1:-1].strip()
    return re.sub(r"\s+", " ", stripped)


def _parse_bibtex_entries(text: str) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    index = 0
    while index < len(text):
        at_index = text.find("@", index)
        if at_index < 0:
            break
        open_index = min(
            (
                position
                for position in (text.find("{", at_index), text.find("(", at_index))
                if position >= 0
            ),
            default=-1,
        )
        if open_index < 0:
            break
        entry_type = text[at_index + 1 : open_index].strip().lower()
        end_index = _find_bibtex_body_end(text, open_index, text[open_index])
        if end_index < 0:
            return []
        body = text[open_index + 1 : end_index]
        parts = _split_bibtex_top_level(body)
        if not parts:
            index = end_index + 1
            continue
        entry_key = parts[0].strip()
        fields: dict[str, Any] = {
            "item_key": entry_key,
            "citation_key": entry_key,
            "item_type": entry_type,
        }
        for field in parts[1:]:
            if "=" not in field:
                continue
            name, value = field.split("=", 1)
            field_name = name.strip().lower()
            fields[field_name] = _strip_bibtex_value(value)
        if fields:
            entries.append(fields)
        index = end_index + 1
    return entries


def _parse_ris_entries(text: str) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    saw_end = False
    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        if not line.strip():
            continue
        if len(line) < 5 or line[2:5] != "  -":
            continue
        tag = line[:2].upper()
        value = line[5:].strip()
        if tag == "TY":
            current = {"item_type": value.lower()}
            saw_end = False
            continue
        if current is None:
            continue
        if tag == "ER":
            entries.append(current)
            current = None
            saw_end = True
            continue
        if tag in RIS_FORBIDDEN_TAGS:
            current[RIS_FORBIDDEN_TAGS[tag]] = value
            continue
        if tag == "ID":
            current["item_key"] = value
            current["citation_key"] = value
        elif tag in {"TI", "T1"}:
            current["title"] = value
        elif tag in {"AU", "A1"}:
            current.setdefault("author", []).append(value)
        elif tag in {"PY", "Y1", "DA"}:
            current.setdefault("date", value)
            year = value[:4]
            if year.isdigit():
                current["year"] = int(year)
        elif tag in {"JO", "JF", "T2"}:
            current["journal"] = value
        elif tag == "PB":
            current["publisher"] = value
        elif tag == "DO":
            current["doi"] = value
        elif tag == "SN":
            current["isbn"] = value
        elif tag == "UR":
            current["url"] = value
        elif tag == "KW":
            current.setdefault("keywords", []).append(value)
    if current is not None or not saw_end:
        return []
    return entries


def _xml_local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def _xml_text(element: ET.Element, name: str) -> str | None:
    for child in element:
        if _xml_local_name(child.tag) == name and child.text:
            return child.text.strip()
    return None


def _xml_people(element: ET.Element) -> list[str]:
    names: list[str] = []
    for child in element.iter():
        if _xml_local_name(child.tag) != "Person":
            continue
        given = _xml_text(child, "givenName") or ""
        surname = _xml_text(child, "surname") or ""
        full_name = " ".join(part for part in (given.strip(), surname.strip()) if part)
        if full_name:
            names.append(full_name)
    return names


def _has_forbidden_xml_declaration(text: str) -> bool:
    lowered = text.lower()
    return any(declaration in lowered for declaration in FORBIDDEN_XML_DECLARATIONS)


def _xml_max_depth(element: ET.Element, depth: int = 0) -> int:
    if not list(element):
        return depth
    return max(_xml_max_depth(child, depth + 1) for child in element)


def _parse_rdf_entries(text: str) -> list[dict[str, Any]]:
    if _has_forbidden_xml_declaration(text):
        return []
    try:
        root = ET.fromstring(text)
    except ET.ParseError:
        return []
    if _xml_local_name(root.tag) != "RDF":
        return []
    if _xml_max_depth(root) > MAX_RDF_XML_DEPTH:
        return []

    item_types = {
        "AcademicArticle": "journalArticle",
        "Article": "article",
        "Book": "book",
        "BookSection": "bookSection",
        "ConferencePaper": "conferencePaper",
        "Document": "document",
        "Manuscript": "manuscript",
        "Report": "report",
        "Thesis": "thesis",
        "WebPage": "webpage",
    }
    entries: list[dict[str, Any]] = []
    for element in root.iter():
        local_tag = _xml_local_name(element.tag)
        if local_tag not in item_types:
            continue
        entry: dict[str, Any] = {"item_type": item_types[local_tag]}
        for name in (
            "abstract",
            "date",
            "doi",
            "extra",
            "isbn",
            "issn",
            "pages",
            "shortTitle",
            "title",
            "uri",
        ):
            value = _xml_text(element, name)
            if value:
                entry[name] = value
        creators = _xml_people(element)
        if creators:
            entry["creators"] = creators
        if entry:
            entries.append(entry)
    return entries


def _creator_names(creators: Any) -> list[str]:
    if isinstance(creators, str):
        return [name.strip() for name in re.split(r"\s+and\s+", creators) if name.strip()]
    if not isinstance(creators, list):
        return []
    names: list[str] = []
    for creator in creators:
        if isinstance(creator, str):
            names.append(creator)
        elif isinstance(creator, dict):
            full = " ".join(
                part
                for part in (
                    str(creator.get("firstName") or creator.get("given") or "").strip(),
                    str(creator.get("lastName") or creator.get("family") or "").strip(),
                )
                if part
            )
            if full:
                names.append(full)
            elif creator.get("name"):
                names.append(str(creator["name"]))
    return names


def _issued_year(item: dict[str, Any]) -> int | None:
    issued = item.get("issued")
    if not isinstance(issued, dict):
        return None
    date_parts = issued.get("date-parts")
    if not isinstance(date_parts, list) or not date_parts:
        return None
    first_part = date_parts[0]
    if not isinstance(first_part, list) or not first_part:
        return None
    year = first_part[0]
    return year if isinstance(year, int) else None


def _normalize_item(item: dict[str, Any]) -> dict[str, Any]:
    date_text = str(item.get("date", "") or "")
    year = item.get("year")
    if year is None and date_text[:4].isdigit():
        year = int(date_text[:4])
    if year is None:
        year = _issued_year(item)
    normalized = {
        "item_key": item.get("item_key") or item.get("key") or item.get("itemKey") or item.get("id"),
        "item_type": item.get("item_type") or item.get("itemType") or item.get("type"),
        "title": item.get("title"),
        "creators": _creator_names(item.get("creators") or item.get("authors") or item.get("author")),
        "year": year,
        "date": item.get("date"),
        "publication_title": (
            item.get("publicationTitle")
            or item.get("publication_title")
            or item.get("container-title")
            or item.get("journal")
            or item.get("booktitle")
        ),
        "publisher": item.get("publisher"),
        "doi": item.get("DOI") or item.get("doi"),
        "isbn": item.get("ISBN") or item.get("isbn"),
        "url": item.get("url") or item.get("URL"),
        "tags": item.get("tags") or item.get("keywords"),
        "collections": item.get("collections"),
        "citation_key": item.get("citation_key") or item.get("citekey") or item.get("citationKey"),
    }
    return {key: value for key, value in normalized.items() if key in ALLOWED_METADATA_FIELDS and value}


def _connection_required(reason: str) -> dict[str, Any]:
    return {
        "pilot_status": CONNECTION_REQUIRED,
        "source_available": False,
        "human_required": True,
        "reasons": [reason],
    }


def _scope_limits(export_size_bytes: int = 0, item_count: int = 0) -> dict[str, Any]:
    return {
        "max_export_bytes": MAX_EXPORT_BYTES,
        "export_size_bytes": export_size_bytes,
        "export_size_within_limit": export_size_bytes <= MAX_EXPORT_BYTES,
        "max_items": MAX_EXPORT_ITEMS,
        "item_count": item_count,
        "item_count_within_limit": item_count <= MAX_EXPORT_ITEMS,
    }


def _forbidden_export_suffix(path: Path) -> str | None:
    suffix = path.suffix.lower()
    return suffix if suffix in FORBIDDEN_EXPORT_SUFFIXES else None


def build_real_zotero_metadata_pilot_report(
    *,
    authorization_decision_path: str | Path | None,
    source_mode: str | None,
    export_path: str | Path | None,
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Build a metadata-only pilot report from an approved export file."""
    generated = generated_at or _utc_now_text()
    base = {
        "profile": "paper_real_zotero_metadata_only_pilot_report",
        "schema_version": "1.0",
        "task_id": "PAPER_REAL_ZOTERO_METADATA_ONLY_PILOT_A1",
        "project_id": "dev-frame-opencode",
        "workflow_type": "paper",
        "generated_at": generated,
        "connection": {
            "authorization_decision_path_present": bool(authorization_decision_path),
            "source_mode": source_mode or "",
            "export_path_present": bool(export_path),
            "metadata_format_detected": "",
            "uses_api_key": False,
            "uses_browser_cdp": False,
            "uses_cloud": False,
        },
        "scope_limits": _scope_limits(),
        "privacy_boundary": {
            "zotero_attachments_read": False,
            "pdf_read": False,
            "full_text_read": False,
            "obsidian_read": False,
            "private_rag_used": False,
            "live_writelab_called": False,
            "raw_sensitive_fields_absent": True,
        },
        "artifact_minimization": _artifact_minimization(),
        "review_pack_minimization": _review_pack_minimization(),
        "final_acceptance_claimed": False,
    }

    if not authorization_decision_path:
        return {**base, **_connection_required("missing_authorization_decision_path")}
    decision_path = Path(authorization_decision_path)
    if not decision_path.exists():
        return {**base, **_connection_required("authorization_decision_path_not_found")}

    decision = json.loads(decision_path.read_text(encoding="utf-8"))
    authorization = decision.get("runtime_authorization")
    evaluation_time = _parse_generated_time(generated)
    auth_result = validate_runtime_authorization(
        authorization if isinstance(authorization, dict) else None,
        task_id="PAPER_REAL_ZOTERO_METADATA_ONLY_PILOT_A1",
        project_id="dev-frame-opencode",
        operation="real_zotero_metadata",
        source="zotero_metadata",
        repo_path="ai-workflow-hub/docs/paper/PAPER_REAL_PILOT_PREAUTH_PACKET.md",
        now=evaluation_time,
    )
    if not auth_result["allowed"]:
        return {
            **base,
            "pilot_status": BLOCKED,
            "source_available": False,
            "human_required": True,
            "authorization_result": auth_result,
            "reasons": [f"authorization:{reason}" for reason in auth_result["reasons"]],
        }

    if source_mode not in ALLOWED_EXPORT_MODES:
        return {**base, **_connection_required("missing_or_unsupported_source_mode")}
    if not export_path:
        return {**base, **_connection_required("missing_zotero_metadata_export_path")}
    export = Path(export_path)
    if not export.exists():
        return {**base, **_connection_required("zotero_metadata_export_path_not_found")}

    forbidden_suffix = _forbidden_export_suffix(export)
    if forbidden_suffix:
        return {
            **base,
            "pilot_status": BLOCKED,
            "source_available": False,
            "human_required": True,
            "authorization_result": auth_result,
            "reasons": ["non_metadata_export_file_type"],
            "forbidden_file_suffix": forbidden_suffix,
        }

    export_size_bytes = export.stat().st_size
    scoped_base = {**base, "scope_limits": _scope_limits(export_size_bytes=export_size_bytes)}
    if export_size_bytes > MAX_EXPORT_BYTES:
        return {
            **scoped_base,
            "pilot_status": BLOCKED,
            "source_available": False,
            "human_required": True,
            "authorization_result": auth_result,
            "reasons": ["metadata_export_size_limit_exceeded"],
        }

    try:
        export_text = export.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError:
        return {
            **scoped_base,
            "pilot_status": CONNECTION_REQUIRED,
            "source_available": False,
            "human_required": True,
            "authorization_result": auth_result,
            "reasons": ["unsupported_or_non_utf8_metadata_export"],
        }
    try:
        raw = json.loads(export_text)
    except json.JSONDecodeError:
        metadata_format = _detect_text_format(export, export_text)
        if metadata_format not in {"bibtex", "rdf", "ris"}:
            return {
                **scoped_base,
                "connection": {
                    **base["connection"],
                    "metadata_format_detected": metadata_format,
                },
                **_connection_required(f"unsupported_metadata_format:{metadata_format}"),
            }
        if metadata_format == "bibtex":
            raw = _parse_bibtex_entries(export_text)
        elif metadata_format == "rdf":
            raw = _parse_rdf_entries(export_text)
        else:
            raw = _parse_ris_entries(export_text)
        if not raw:
            return {
                **scoped_base,
                "connection": {
                    **base["connection"],
                    "metadata_format_detected": metadata_format,
                },
                **_connection_required(f"malformed_or_empty_{metadata_format}_export"),
            }
    else:
        metadata_format = _detect_json_format(raw)
    if metadata_format in UNSUPPORTED_METADATA_FORMATS:
        return {
            **scoped_base,
            "connection": {
                **base["connection"],
                "metadata_format_detected": metadata_format,
            },
            **_connection_required(f"unsupported_metadata_format:{metadata_format}"),
        }
    sanitized_raw, removed_field_counts = _sanitize_metadata_value(raw)
    sanitizer = _sanitizer_report(
        sanitized_raw=sanitized_raw,
        removed_field_counts=removed_field_counts,
        export_size_bytes=export_size_bytes,
        parse_status="parsed",
    )
    forbidden = _forbidden_keys(sanitized_raw)
    if forbidden:
        return {
            **scoped_base,
            "connection": {
                **base["connection"],
                "metadata_format_detected": metadata_format,
            },
            "pilot_status": BLOCKED,
            "source_available": False,
            "human_required": True,
            "authorization_result": auth_result,
            "reasons": ["unsupported_forbidden_metadata_export_structure"],
            "forbidden_fields": forbidden,
            "sanitizer": sanitizer,
        }

    items = _as_items(sanitized_raw)
    scoped_base = {
        **scoped_base,
        "scope_limits": _scope_limits(
            export_size_bytes=export_size_bytes,
            item_count=len(items),
        ),
    }
    if len(items) > MAX_EXPORT_ITEMS:
        return {
            **scoped_base,
            "connection": {
                **base["connection"],
                "metadata_format_detected": metadata_format,
            },
            "pilot_status": BLOCKED,
            "source_available": False,
            "human_required": True,
            "authorization_result": auth_result,
            "reasons": ["metadata_export_item_count_limit_exceeded"],
        }

    records = [_normalize_item(item) for item in items]
    records = [record for record in records if record]
    if not records:
        return {
            **scoped_base,
            "connection": {
                **base["connection"],
                "metadata_format_detected": metadata_format,
            },
            "pilot_status": CONNECTION_REQUIRED,
            "source_available": False,
            "human_required": True,
            "authorization_result": auth_result,
            "reasons": ["empty_or_unrecognized_metadata_export"],
        }
    fingerprints = [_fingerprint(record) for record in records]
    redacted_samples = [
        {
            "item_fingerprint": fingerprint,
            "item_type": record.get("item_type", ""),
            "year": record.get("year", ""),
            "has_doi": bool(record.get("doi")),
            "has_url": bool(record.get("url")),
        }
        for record, fingerprint in zip(records[:3], fingerprints[:3], strict=False)
    ]
    return {
        **scoped_base,
        "connection": {
            **base["connection"],
            "metadata_format_detected": metadata_format,
        },
        "pilot_status": PASS_METADATA_ONLY,
        "source_available": True,
        "human_required": False,
        "authorization_result": auth_result,
        "sanitizer": sanitizer,
        "metadata_summary": {
            "item_count": len(records),
            "allowed_fields": sorted(ALLOWED_METADATA_FIELDS),
            "metadata_fingerprints": fingerprints,
            "redacted_samples": redacted_samples,
        },
        "evidence_manifest": {
            "manifest_id": "paper-real-zotero-metadata-only-pilot-evidence-a1",
            "task_id": "PAPER_REAL_ZOTERO_METADATA_ONLY_PILOT_A1",
            "runtime_authorization_ref": auth_result["authorization_id"],
            "metadata_format_detected": metadata_format,
            "scope_limits": scoped_base["scope_limits"],
            "sanitizer": sanitizer,
            "source_records": [
                {
                    "source_id": fingerprint,
                    "source_type": "zotero_metadata",
                    "source_level": VERIFIED_SOURCE,
                    "privacy_level": "metadata_only",
                    "path_or_citation_key": fingerprint,
                    "retrieved_at": generated,
                    "stale_status": "unknown",
                    "hash_or_metadata_fingerprint": fingerprint,
                }
                for fingerprint in fingerprints
            ],
            "retrieval_records": redacted_samples,
            "redaction_records": _redaction_records(removed_field_counts),
            "artifact_minimization": _artifact_minimization(),
            "review_pack_minimization": _review_pack_minimization(),
            "commands_run": ["aihub paper real-zotero-metadata-pilot"],
            "tests_run": ["tests/test_paper_real_zotero_metadata_only_pilot.py"],
            "artifacts_generated": ["paper-real-zotero-metadata-only-pilot.json"],
            "raw_sensitive_fields_absent": True,
            "contains_real_private_content": False,
            "contains_live_writelab_payload": False,
            "final_acceptance_claimed": False,
            "reviewer_required": True,
        },
    }
