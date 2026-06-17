"""Zotero Web API metadata-only pilot adapter.

This adapter is intentionally narrow: it reads only personal-library metadata
through api.zotero.org and returns minimized evidence. It never persists raw
Zotero item JSON, raw titles, raw abstracts, notes, attachments, PDFs, full
text, browser/CDP state, or API credentials.
"""

from __future__ import annotations

import hashlib
import json
import re
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from .citation_integrity import VERIFIED_SOURCE

PASS_METADATA_ONLY = "PASS_METADATA_ONLY"
CONNECTION_REQUIRED = "ZOTERO_WEB_API_CONNECTION_REQUIRED"
BLOCKED = "BLOCKED"
EMPTY_REMOTE_LIBRARY = "EMPTY_REMOTE_LIBRARY"

API_HOST = "api.zotero.org"
MAX_METADATA_ITEMS = 500
DEFAULT_KEY_FILE = Path(r"C:\Users\RD\key\zotero.txt")
FORBIDDEN_ITEM_TYPES = {"note", "attachment"}
REDACTED_FIELDS = {
    "abstractNote",
    "accessDate",
    "attachments",
    "file",
    "full_text",
    "itemURI",
    "note",
    "notes",
    "pdf",
    "pdf_text",
    "title",
    "url",
}
MINIMIZED_FIELD_WHITELIST = {
    "DOI",
    "ISSN",
    "PMCID",
    "PMID",
    "citationKey",
    "creators",
    "date",
    "itemType",
    "key",
    "publicationTitle",
    "version",
}

Fetcher = Callable[[str, dict[str, str]], tuple[int, dict[str, str], str]]
DEFAULT_PAGE_LIMIT = 100


class ZoteroWebApiError(ValueError):
    def __init__(
        self,
        reason: str,
        *,
        stage: str,
        http_status: int = 0,
        retry_after_present: bool = False,
    ) -> None:
        super().__init__(reason)
        self.reason = reason
        self.stage = stage
        self.http_status = http_status
        self.retry_after_present = retry_after_present


def _utc_now_text() -> str:
    return datetime.now(timezone.utc).isoformat()


def _fingerprint(value: Any) -> str:
    text = json.dumps(value, sort_keys=True, ensure_ascii=False, default=str)
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def _short_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]


def _empty_base(*, key_file_path: str | Path | None, generated_at: str | None) -> dict[str, Any]:
    return {
        "profile": "paper_zotero_web_api_metadata_only_pilot_report",
        "schema_version": "1.0",
        "task_id": "OPENCODE_ZOTERO_WEB_API_METADATA_ONLY_ADAPTER_A1",
        "project_id": "dev-frame-opencode",
        "workflow_type": "paper",
        "generated_at": generated_at or _utc_now_text(),
        "pilot_status": CONNECTION_REQUIRED,
        "source_available": False,
        "human_required": True,
        "connection": {
            "zotero_web_api_called": False,
            "api_host": API_HOST,
            "library_type": "user",
            "key_file_path_present": bool(key_file_path),
            "user_id_present": False,
            "user_id_sha256_12": "",
            "api_key_present": False,
            "api_key_printed_or_persisted": False,
            "uses_browser_cdp": False,
            "uses_cloud": False,
        },
        "scope": {
            "metadata_only": True,
            "personal_library_only": True,
            "notes_read": False,
            "attachments_read": False,
            "pdf_read": False,
            "full_text_read": False,
            "obsidian_accessed": False,
            "rag_executed": False,
            "writelab_called": False,
            "browser_cdp_called": False,
            "cloud_called": False,
        },
        "minimization": {
            "raw_items_persisted": False,
            "raw_titles_persisted": False,
            "raw_abstracts_persisted": False,
            "api_key_persisted": False,
            "raw_user_id_persisted": False,
            "fingerprints_counts_and_booleans_only": True,
        },
        "final_acceptance_claimed": False,
    }


def _parse_key_file(path: Path) -> tuple[str, str]:
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        raise ValueError("empty_key_file")

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        data = None

    if isinstance(data, dict):
        user_id = str(data.get("user_id") or data.get("zotero_user_id") or "").strip()
        api_key = str(data.get("api_key") or data.get("zotero_api_key") or "").strip()
        if user_id and api_key:
            return user_id, api_key

    values: dict[str, str] = {}
    loose_tokens: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line or ":" in line:
            delimiter = "=" if "=" in line else ":"
            key, value = line.split(delimiter, 1)
            values[key.strip().lower().replace("-", "_")] = value.strip().strip('"')
        else:
            loose_tokens.append(line.strip().strip('"'))

    user_id = (
        values.get("user_id")
        or values.get("zotero_user_id")
        or values.get("userid")
        or values.get("uid")
        or ""
    )
    api_key = (
        values.get("api_key")
        or values.get("zotero_api_key")
        or values.get("key")
        or values.get("token")
        or ""
    )
    if not user_id:
        for token in loose_tokens:
            digit_match = re.search(r"\d{3,}", token)
            if digit_match:
                user_id = digit_match.group(0)
                break
            safe_match = re.search(r"[A-Za-z0-9_-]{3,}", token)
            if safe_match:
                user_id = safe_match.group(0)
                break
    if not api_key:
        for token in loose_tokens:
            if not re.fullmatch(r"\d+", token) and len(token) >= 8:
                api_key = token
                break
    if not user_id or not api_key:
        raise ValueError("missing_user_id_or_api_key")
    if not re.fullmatch(r"[A-Za-z0-9_-]+", user_id):
        raise ValueError("invalid_user_id")
    return user_id, api_key


def _urllib_fetch(url: str, headers: dict[str, str]) -> tuple[int, dict[str, str], str]:
    request = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            body = response.read().decode("utf-8")
            return response.status, dict(response.headers.items()), body
    except urllib.error.HTTPError as error:
        body = error.read().decode("utf-8", errors="replace")
        return error.code, dict(error.headers.items()), body


def _zotero_url(user_id: str, path: str, query: dict[str, str | int]) -> str:
    encoded_query = urllib.parse.urlencode(query)
    return f"https://{API_HOST}/users/{user_id}/{path}?{encoded_query}"


def _total_results(headers: dict[str, str]) -> int:
    for key, value in headers.items():
        if key.lower() == "total-results":
            try:
                return int(value)
            except ValueError:
                return 0
    return 0


def _header_present(headers: dict[str, str], header_name: str) -> bool:
    return any(key.lower() == header_name.lower() for key in headers)


def _json_or_block(body: str, *, stage: str, http_status: int) -> Any:
    try:
        return json.loads(body)
    except json.JSONDecodeError as exc:
        raise ZoteroWebApiError(
            "zotero_api_returned_non_json",
            stage=stage,
            http_status=http_status,
        ) from exc


def _item_data(item: dict[str, Any]) -> dict[str, Any]:
    data = item.get("data")
    return data if isinstance(data, dict) else item


def _field_presence_counts(items: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in items:
        for field in _item_data(item):
            counts[field] = counts.get(field, 0) + 1
    return dict(sorted(counts.items()))


def _redaction_counts(items: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in items:
        data = _item_data(item)
        for field in REDACTED_FIELDS:
            value = data.get(field)
            if value not in (None, "", [], {}):
                counts[field] = counts.get(field, 0) + 1
    return dict(sorted(counts.items()))


def _item_type_counts(items: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in items:
        item_type = str(_item_data(item).get("itemType") or "unknown")
        counts[item_type] = counts.get(item_type, 0) + 1
    return dict(sorted(counts.items()))


def _forbidden_item_type_counts(items: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in items:
        item_type = str(_item_data(item).get("itemType") or "")
        if item_type in FORBIDDEN_ITEM_TYPES:
            counts[item_type] = counts.get(item_type, 0) + 1
    return dict(sorted(counts.items()))


def _version_range(items: list[dict[str, Any]]) -> dict[str, int]:
    versions = [
        int(_item_data(item).get("version"))
        for item in items
        if isinstance(_item_data(item).get("version"), int)
    ]
    return {
        "min_version": min(versions) if versions else 0,
        "max_version": max(versions) if versions else 0,
    }


def _minimized_records(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for item in items:
        data = _item_data(item)
        record: dict[str, Any] = {
            key: data.get(key)
            for key in sorted(MINIMIZED_FIELD_WHITELIST)
            if data.get(key) not in (None, "", [], {})
        }
        record["has_doi"] = bool(data.get("DOI"))
        record["has_url"] = bool(data.get("url"))
        records.append(record)
    return records


def _fetch_json(
    *,
    user_id: str,
    api_key: str,
    path: str,
    query: dict[str, str | int],
    fetcher: Fetcher,
    stage: str,
) -> tuple[int, dict[str, str], Any]:
    url = _zotero_url(user_id, path, query)
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "https" or parsed.hostname != API_HOST:
        raise ZoteroWebApiError("zotero_api_host_not_allowed", stage=stage)
    try:
        status, headers, body = fetcher(url, {"Zotero-API-Key": api_key})
    except (OSError, TimeoutError, urllib.error.URLError) as exc:
        raise ZoteroWebApiError("zotero_api_network_error", stage=stage) from exc
    if status >= 400:
        raise ZoteroWebApiError(
            f"zotero_api_http_{status}",
            stage=stage,
            http_status=status,
            retry_after_present=_header_present(headers, "retry-after"),
        )
    return status, headers, _json_or_block(body, stage=stage, http_status=status)


def _fetch_metadata_pages(
    *,
    user_id: str,
    api_key: str,
    fetcher: Fetcher,
    limit: int,
) -> tuple[list[dict[str, Any]], int]:
    page_limit = min(max(1, limit), DEFAULT_PAGE_LIMIT)
    items: list[dict[str, Any]] = []
    start = 0
    calls = 0

    while True:
        _, headers, page = _fetch_json(
            user_id=user_id,
            api_key=api_key,
            path="items/top",
            query={
                "format": "json",
                "limit": page_limit,
                "start": start,
            },
            fetcher=fetcher,
            stage="metadata_page",
        )
        calls += 1
        if not isinstance(page, list):
            raise ZoteroWebApiError(
                "zotero_api_metadata_response_not_list",
                stage="metadata_page",
            )
        items.extend(page)
        total_results = _total_results(headers)
        if total_results > MAX_METADATA_ITEMS or len(items) > MAX_METADATA_ITEMS:
            raise ZoteroWebApiError(
                "remote_library_item_limit_exceeded",
                stage="metadata_page",
            )
        if not page:
            break
        if total_results and len(items) >= total_results:
            break
        if len(page) < page_limit:
            break
        start += page_limit

    return items, calls


def build_zotero_web_metadata_pilot_report(
    *,
    key_file_path: str | Path | None = None,
    generated_at: str | None = None,
    fetcher: Fetcher | None = None,
    limit: int = 100,
) -> dict[str, Any]:
    """Build a minimized Zotero Web API metadata-only report."""
    key_path = Path(key_file_path) if key_file_path else DEFAULT_KEY_FILE
    base = _empty_base(key_file_path=key_path, generated_at=generated_at)
    if not key_path.exists():
        return {**base, "reasons": ["key_file_not_found"]}

    try:
        user_id, api_key = _parse_key_file(key_path)
    except ValueError as exc:
        return {**base, "reasons": [str(exc)]}

    connection = {
        **base["connection"],
        "user_id_present": True,
        "user_id_sha256_12": _short_hash(user_id),
        "api_key_present": True,
    }
    active_fetcher = fetcher or _urllib_fetch

    try:
        _, all_headers, _ = _fetch_json(
            user_id=user_id,
            api_key=api_key,
            path="items",
            query={"format": "versions", "limit": 1},
            fetcher=active_fetcher,
            stage="all_items_versions_probe",
        )
        _, top_headers, _ = _fetch_json(
            user_id=user_id,
            api_key=api_key,
            path="items/top",
            query={"format": "versions", "limit": 1},
            fetcher=active_fetcher,
            stage="top_items_versions_probe",
        )
        metadata, metadata_api_calls = _fetch_metadata_pages(
            user_id=user_id,
            api_key=api_key,
            fetcher=active_fetcher,
            limit=limit,
        )
    except ZoteroWebApiError as exc:
        reason = exc.reason
        pilot_status = (
            BLOCKED
            if reason
            in {
                "remote_library_item_limit_exceeded",
                "zotero_api_metadata_response_not_list",
            }
            else CONNECTION_REQUIRED
        )
        return {
            **base,
            "connection": {**connection, "zotero_web_api_called": True},
            "pilot_status": pilot_status,
            "reasons": [reason],
            "failure_summary": {
                "failure_stage": exc.stage,
                "reason": reason,
                "http_status": exc.http_status,
                "retry_after_present": exc.retry_after_present,
                "response_body_persisted": False,
            },
        }

    if not metadata:
        return {
            **base,
            "connection": {**connection, "zotero_web_api_called": True},
            "pilot_status": EMPTY_REMOTE_LIBRARY,
            "reasons": ["empty_remote_library"],
        }
    if len(metadata) > MAX_METADATA_ITEMS:
        return {
            **base,
            "connection": {**connection, "zotero_web_api_called": True},
            "pilot_status": BLOCKED,
            "reasons": ["remote_library_item_limit_exceeded"],
        }

    forbidden_item_types = _forbidden_item_type_counts(metadata)
    field_counts = _field_presence_counts(metadata)
    redaction_counts = _redaction_counts(metadata)
    item_counts = _item_type_counts(metadata)
    version_range = _version_range(metadata)
    minimized_records = _minimized_records(metadata)
    fingerprints = [_fingerprint(record) for record in minimized_records]

    common = {
        **base,
        "connection": {**connection, "zotero_web_api_called": True},
        "remote_summary": {
            "all_items_total_results_probe": _total_results(all_headers),
            "top_items_total_results_probe": _total_results(top_headers),
            "metadata_api_calls": metadata_api_calls,
            "metadata_page_limit": min(max(1, limit), DEFAULT_PAGE_LIMIT),
            "metadata_pages_read": metadata_api_calls,
            "metadata_pagination_complete": True,
            "metadata_records_read": len(metadata),
            "item_type_counts": item_counts,
            "field_presence_counts": field_counts,
            "redaction_counts": redaction_counts,
            "returned_forbidden_item_type_counts": forbidden_item_types,
            "item_fingerprints": fingerprints,
            "item_keys_fingerprint": _fingerprint(
                [str(_item_data(item).get("key") or "") for item in metadata]
            ),
            **version_range,
        },
    }
    if forbidden_item_types:
        return {
            **common,
            "pilot_status": BLOCKED,
            "source_available": False,
            "human_required": True,
            "reasons": ["forbidden_item_type_returned"],
        }

    return {
        **common,
        "pilot_status": PASS_METADATA_ONLY,
        "source_available": True,
        "human_required": False,
        "evidence_manifest": {
            "manifest_id": "paper-zotero-web-api-metadata-only-evidence-a1",
            "task_id": "OPENCODE_ZOTERO_WEB_API_METADATA_ONLY_ADAPTER_A1",
            "source_type": "zotero_web_api_metadata",
            "source_level": VERIFIED_SOURCE,
            "privacy_level": "metadata_only",
            "metadata_only": True,
            "source_records": [
                {
                    "source_id": fingerprint,
                    "source_type": "zotero_web_api_metadata",
                    "source_level": VERIFIED_SOURCE,
                    "privacy_level": "metadata_only",
                    "hash_or_metadata_fingerprint": fingerprint,
                }
                for fingerprint in fingerprints
            ],
            "redaction_counts": redaction_counts,
            "item_type_counts": item_counts,
            "field_presence_counts": field_counts,
            "raw_sensitive_fields_absent": True,
            "final_acceptance_claimed": False,
            "reviewer_required": True,
        },
    }
