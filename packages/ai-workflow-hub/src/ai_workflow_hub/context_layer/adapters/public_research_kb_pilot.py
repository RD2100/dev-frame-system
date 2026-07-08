"""Public research knowledge-base pilot for the paper module.

Fetches PUBLIC research metadata from arXiv or OpenAlex, writes Obsidian-
compatible markdown notes with stable metadata schema into a caller-provided
vault/target folder, runs the existing local paper RAG pipeline where possible,
runs local citation lookup evidence, and emits a minimized report and evidence
manifest.

This adapter does NOT read private Zotero/Obsidian/user paper data. It uses
only public scholarly APIs and local deterministic processing. For tests, the
metadata fetcher is injectable to avoid network calls.
"""

from __future__ import annotations

import hashlib
import json
import re
import time
import xml.etree.ElementTree as ET
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlencode, urlparse

ARXIV_BASE = "https://export.arxiv.org/api/query"
OPENALEX_WORKS_URL = "https://api.openalex.org/works"
ARXIV_USER_AGENT = "dev-frame-system/0.1 paper-public-research-kb-pilot"
OPENALEX_USER_AGENT = "dev-frame-system/0.1 paper-public-research-kb-pilot"
ARXIV_RETRY_STATUS_CODES = {429, 503}
OPENALEX_RETRY_STATUS_CODES = {429, 503}
ARXIV_NS = "{http://www.w3.org/2005/Atom}"
ARXIV_NS_OPENSEARCH = "{http://a9.com/-/spec/opensearch/1.1/}"
ARXIV_NS_ARXIV = "{http://arxiv.org/schemas/atom}"

PROFILE = "paper_public_research_kb_pilot_report"
SCHEMA_VERSION = "1.0"
TASK_ID = "OPENCODE_PUBLIC_RESEARCH_KB_PILOT_A1"
MANAGED_BLOCK_START = "<!-- devframe:paper-metadata:start -->"
MANAGED_BLOCK_END = "<!-- devframe:paper-metadata:end -->"
DASHBOARD_FILENAME = "_Research KB Dashboard.md"


def _utc_now_text() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256_text(value: str) -> str:
    return f"sha256:{hashlib.sha256(value.encode('utf-8')).hexdigest()}"


def _sha256_bytes(data: bytes) -> str:
    return f"sha256:{hashlib.sha256(data).hexdigest()}"


def _sha256_file(path: Path) -> str:
    return f"sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}"


def _safe_arxiv_id(arxiv_id: str) -> str:
    return re.sub(r"[^a-zA-Z0-9._-]", "_", arxiv_id)


def _safe_paper_id(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9._-]", "_", value)


def _normalize_openalex_id(value: str) -> str:
    stripped = str(value or "").strip()
    if not stripped:
        return ""
    return stripped.rstrip("/").split("/")[-1]


def _normalize_doi(value: str) -> str:
    stripped = str(value or "").strip()
    return stripped.replace("https://doi.org/", "").replace("http://dx.doi.org/", "")


def _source_kind(source: str) -> str:
    normalized = source.strip().lower()
    if normalized == "openalex":
        return "openalex_public_api"
    if normalized == "arxiv":
        return "arxiv_public_api"
    return "unsupported_public_api"


def _paper_source_id(paper: dict[str, Any]) -> str:
    if paper.get("source_type") == "openalex_public_metadata" and paper.get("openalex_id"):
        return str(paper["openalex_id"])
    return str(
        paper.get("arxiv_id")
        or paper.get("openalex_id")
        or paper.get("paper_id")
        or ""
    )


def _paper_source_prefix(paper: dict[str, Any]) -> str:
    if paper.get("source_type") == "openalex_public_metadata":
        return "openalex"
    if paper.get("arxiv_id"):
        return "arxiv"
    if paper.get("openalex_id"):
        return "openalex"
    return str(paper.get("source_type") or "paper").replace("_public_metadata", "")


def _paper_note_stem(paper: dict[str, Any]) -> str:
    return f"{_paper_source_prefix(paper)}-{_safe_paper_id(_paper_source_id(paper))}"


def _paper_id_value(paper: dict[str, Any]) -> str:
    return f"{_paper_source_prefix(paper)}:{_paper_source_id(paper)}"


def _paper_source_url(paper: dict[str, Any]) -> str:
    if paper.get("source_url"):
        return str(paper["source_url"])
    if paper.get("arxiv_id"):
        return f"https://arxiv.org/abs/{paper['arxiv_id']}"
    if paper.get("openalex_id"):
        return f"https://openalex.org/{paper['openalex_id']}"
    return ""


def _paper_source_label(paper: dict[str, Any]) -> str:
    if paper.get("source_type") == "openalex_public_metadata":
        return "OpenAlex ID"
    if paper.get("arxiv_id"):
        return "arXiv ID"
    if paper.get("openalex_id"):
        return "OpenAlex ID"
    return "Source ID"


def _paper_source_type(paper: dict[str, Any]) -> str:
    return str(paper.get("source_type") or f"{_paper_source_prefix(paper)}_public_metadata")


def _paper_venue(paper: dict[str, Any]) -> str:
    return str(paper.get("venue") or ("arXiv" if paper.get("arxiv_id") else ""))


def _boundary_flags(*, obsidian_rest_api_called: bool = False) -> dict[str, bool]:
    return {
        "raw_pdf_text_persisted": False,
        "raw_markdown_body_persisted": False,
        "raw_arxiv_response_persisted": False,
        "raw_query_persisted": False,
        "raw_source_paths_persisted": False,
        "secrets_persisted": False,
        "private_zotero_accessed": False,
        "private_obsidian_accessed": False,
        "real_metadata_export_read": False,
        "external_rag_called": False,
        "cloud_called": False,
        "obsidian_rest_api_called": obsidian_rest_api_called,
        "writelab_called": False,
        "browser_cdp_called": False,
        "final_acceptance_claimed": False,
        "production_ready_claimed": False,
    }


def _evidence_manifest(
    *,
    source_fingerprint_count: int,
    note_count: int,
    report_status: str,
    state_fingerprint: str,
) -> dict[str, Any]:
    return {
        "manifest_id": "paper-public-research-kb-evidence-manifest-a1",
        "schema_version": SCHEMA_VERSION,
        "task_id": TASK_ID,
        "producer": "dev-frame-system",
        "report_status": report_status,
        "source_fingerprint_count": source_fingerprint_count,
        "note_count": note_count,
        "state_fingerprint": state_fingerprint,
        "raw_sensitive_fields_absent": True,
        "contains_raw_pdf_text": False,
        "contains_raw_markdown_body": False,
        "contains_raw_arxiv_response": False,
        "contains_raw_query": False,
        "contains_raw_paths": False,
        "contains_secrets": False,
    }


def _arxiv_search_query(query: str) -> str:
    stripped = query.strip()
    if re.search(r"\b(AND|OR|ANDNOT)\b|[a-zA-Z_]+:", stripped):
        return stripped
    return f"all:{stripped}"


def _blocked_report(
    *,
    generated_at: str,
    status: str,
    reasons: list[str],
    source_kind: str = "arxiv_public_api",
) -> dict[str, Any]:
    return {
        "profile": PROFILE,
        "schema_version": SCHEMA_VERSION,
        "task_id": TASK_ID,
        "project_id": "dev-frame-system",
        "workflow_type": "paper",
        "generated_at": generated_at,
        "pilot_status": status,
        "reasons": reasons,
        "source_kind": source_kind,
        "source_status": "BLOCKED" if status.startswith("BLOCKED") else "NOT_RUN",
        "arxiv_status": "BLOCKED" if "arxiv" in " ".join(reasons).lower() else "NOT_RUN",
        "obsidian_status": "NOT_RUN",
        "pdf_download_status": "NOT_RUN",
        "rag_status": "NOT_RUN",
        "citation_lookup_status": "NOT_RUN",
        "paper_count": 0,
        "note_count": 0,
        "pdf_count": 0,
        "note_paths": [],
        "note_links": [],
        "dashboard_status": "NOT_RUN",
        "dashboard_path": "",
        "dashboard_uri": "",
        "obsidian_rest_status": "NOT_RUN",
        "obsidian_rest_summary": {},
        "paper_fingerprints": [],
        "pdf_fingerprints": [],
        "pdf_download_failure_count": 0,
        "pdf_download_failures": [],
        "privacy_boundary": _boundary_flags(),
        "artifact_minimization": {
            "source_kind": source_kind,
            "paper_count": 0,
            "note_count": 0,
            "pdf_count": 0,
            "note_path_fingerprint_count": 0,
            "citation_claim_count": 0,
        },
        "evidence_manifest": _evidence_manifest(
            source_fingerprint_count=0,
            note_count=0,
            report_status=status,
            state_fingerprint="",
        ),
        "known_limitations": [
            "Public scholarly metadata only; no private paper data is read.",
            "RAG pipeline integration depends on local FAISS and sentence-transformers.",
            "Citation lookup uses fixture-mode metadata derived from public source records.",
        ],
    }


MetadataFetcher = Callable[[str], bytes]
PdfFetcher = Callable[[dict[str, Any]], bytes]
RagBuilder = Callable[..., dict[str, Any]]


def _fetch_arxiv_metadata(
    query: str,
    max_results: int = 5,
    *,
    fetcher: MetadataFetcher | None = None,
) -> list[dict[str, Any]]:
    if fetcher is None:
        import httpx

        params = urlencode({
            "search_query": _arxiv_search_query(query),
            "start": 0,
            "max_results": max_results,
        })
        url = f"{ARXIV_BASE}?{params}"
        response = None
        for attempt in range(3):
            response = httpx.get(
                url,
                timeout=30.0,
                headers={"User-Agent": ARXIV_USER_AGENT},
            )
            if response.status_code not in ARXIV_RETRY_STATUS_CODES or attempt == 2:
                break
            time.sleep(3.0)
        if response is None:
            raise RuntimeError("arxiv_response_missing")
        response.raise_for_status()
        raw = response.content
    else:
        raw = fetcher(query)

    papers: list[dict[str, Any]] = []
    root = ET.fromstring(raw)
    for entry in root.findall(f"{ARXIV_NS}entry"):
        arxiv_id_text = ""
        id_elem = entry.find(f"{ARXIV_NS}id")
        if id_elem is not None and id_elem.text:
            arxiv_id_text = id_elem.text.strip()
            if "abs/" in arxiv_id_text:
                arxiv_id_text = arxiv_id_text.split("abs/")[-1]

        title_text = ""
        title_elem = entry.find(f"{ARXIV_NS}title")
        if title_elem is not None and title_elem.text:
            title_text = re.sub(r"\s+", " ", title_elem.text).strip()

        summary_text = ""
        summary_elem = entry.find(f"{ARXIV_NS}summary")
        if summary_elem is not None and summary_elem.text:
            summary_text = re.sub(r"\s+", " ", summary_elem.text).strip()

        published_text = ""
        published_elem = entry.find(f"{ARXIV_NS}published")
        if published_elem is not None and published_elem.text:
            published_text = published_elem.text.strip()

        updated_text = ""
        updated_elem = entry.find(f"{ARXIV_NS}updated")
        if updated_elem is not None and updated_elem.text:
            updated_text = updated_elem.text.strip()

        authors: list[str] = []
        for author_elem in entry.findall(f"{ARXIV_NS}author"):
            name_elem = author_elem.find(f"{ARXIV_NS}name")
            if name_elem is not None and name_elem.text:
                authors.append(name_elem.text.strip())

        categories: list[str] = []
        for cat_elem in entry.findall(f"{ARXIV_NS}category"):
            term = cat_elem.get("term")
            if term:
                categories.append(term)

        links: list[str] = []
        pdf_url = ""
        for link_elem in entry.findall(f"{ARXIV_NS}link"):
            href = link_elem.get("href")
            title_attr = link_elem.get("title", "")
            if href:
                links.append(href)
            if href and title_attr == "pdf":
                pdf_url = href

        doi_text = ""
        doi_elem = entry.find(f"{ARXIV_NS_ARXIV}doi")
        if doi_elem is not None and doi_elem.text:
            doi_text = doi_elem.text.strip()
        for link_elem in entry.findall(f"{ARXIV_NS}link"):
            title_attr = link_elem.get("title", "")
            href_val = link_elem.get("href", "")
            if title_attr == "doi" and href_val:
                doi_text = href_val.replace("http://dx.doi.org/", "").replace("https://doi.org/", "")

        primary_category = ""
        primary_elem = entry.find(f"{ARXIV_NS_ARXIV}primary_category")
        if primary_elem is not None:
            primary_category = primary_elem.get("term", "")
        if pdf_url.startswith("http://arxiv.org/"):
            pdf_url = pdf_url.replace("http://arxiv.org/", "https://arxiv.org/", 1)

        papers.append({
            "arxiv_id": arxiv_id_text,
            "title": title_text,
            "authors": authors,
            "summary": summary_text,
            "published": published_text,
            "updated": updated_text or published_text,
            "categories": categories,
            "primary_category": primary_category,
            "doi": doi_text,
            "links": links,
            "pdf_url": pdf_url or f"https://arxiv.org/pdf/{arxiv_id_text}",
            "source_level": "VERIFIED_SOURCE",
            "source_type": "arxiv_public_metadata",
        })

    return papers


def _openalex_abstract_text(inverted_index: Any) -> str:
    if not isinstance(inverted_index, dict) or not inverted_index:
        return ""
    positioned: list[tuple[int, str]] = []
    for word, positions in inverted_index.items():
        if not isinstance(positions, list):
            continue
        for position in positions:
            if isinstance(position, int):
                positioned.append((position, str(word)))
    positioned.sort(key=lambda item: item[0])
    return " ".join(word for _, word in positioned)


def _openalex_source_name(work: dict[str, Any]) -> str:
    primary = work.get("primary_location") or {}
    if not isinstance(primary, dict):
        return ""
    source = primary.get("source") or {}
    if isinstance(source, dict):
        return str(source.get("display_name") or "")
    return ""


def _openalex_pdf_url(work: dict[str, Any]) -> str:
    primary = work.get("primary_location") or {}
    if not isinstance(primary, dict):
        return ""
    pdf_url = str(primary.get("pdf_url") or "")
    if pdf_url.startswith("http://arxiv.org/"):
        pdf_url = pdf_url.replace("http://arxiv.org/", "https://arxiv.org/", 1)
    return pdf_url


def _fetch_openalex_metadata(
    query: str,
    max_results: int = 5,
    *,
    fetcher: MetadataFetcher | None = None,
) -> list[dict[str, Any]]:
    if fetcher is None:
        import httpx

        response = None
        params = {"search": query.strip(), "per-page": max_results}
        for attempt in range(3):
            response = httpx.get(
                OPENALEX_WORKS_URL,
                params=params,
                timeout=30.0,
                headers={"User-Agent": OPENALEX_USER_AGENT},
            )
            if response.status_code not in OPENALEX_RETRY_STATUS_CODES or attempt == 2:
                break
            time.sleep(3.0)
        if response is None:
            raise RuntimeError("openalex_response_missing")
        response.raise_for_status()
        raw = response.content
    else:
        raw = fetcher(query)

    payload = json.loads(raw.decode("utf-8") if isinstance(raw, bytes) else raw)
    results = payload.get("results", [])
    if not isinstance(results, list):
        return []

    papers: list[dict[str, Any]] = []
    for work in results:
        if not isinstance(work, dict):
            continue
        openalex_id = _normalize_openalex_id(str(work.get("id") or ""))
        if not openalex_id:
            continue
        ids = work.get("ids") or {}
        arxiv_id = ""
        if isinstance(ids, dict):
            arxiv_id = _normalize_openalex_id(str(ids.get("arxiv") or ""))
        title = str(work.get("display_name") or work.get("title") or "").strip()
        authors: list[str] = []
        for authorship in work.get("authorships") or []:
            if not isinstance(authorship, dict):
                continue
            author = authorship.get("author") or {}
            if isinstance(author, dict) and author.get("display_name"):
                authors.append(str(author["display_name"]).strip())
        topics = []
        for topic in work.get("topics") or []:
            if isinstance(topic, dict) and topic.get("display_name"):
                topics.append(str(topic["display_name"]))
        concepts = []
        for concept in work.get("concepts") or []:
            if isinstance(concept, dict) and concept.get("display_name"):
                concepts.append(str(concept["display_name"]))
        categories = topics or concepts
        primary_category = categories[0] if categories else str(work.get("type") or "")
        published = str(work.get("publication_date") or work.get("publication_year") or "")
        updated = str(work.get("updated_date") or published)
        doi = _normalize_doi(str(work.get("doi") or ""))
        source_url = str(work.get("id") or f"https://openalex.org/{openalex_id}")
        pdf_url = _openalex_pdf_url(work)
        host_venue = work.get("host_venue") or {}
        host_venue_name = (
            str(host_venue.get("display_name") or "")
            if isinstance(host_venue, dict)
            else ""
        )
        papers.append({
            "arxiv_id": arxiv_id,
            "openalex_id": openalex_id,
            "title": title,
            "authors": authors,
            "summary": _openalex_abstract_text(work.get("abstract_inverted_index")),
            "published": published,
            "updated": updated,
            "categories": categories,
            "primary_category": primary_category,
            "doi": doi,
            "links": [source_url],
            "source_url": source_url,
            "pdf_url": pdf_url,
            "venue": _openalex_source_name(work) or host_venue_name,
            "source_level": "VERIFIED_SOURCE",
            "source_type": "openalex_public_metadata",
        })

    return papers


def _fetch_public_metadata(
    *,
    source: str,
    query: str,
    max_results: int,
    fetcher: MetadataFetcher | None,
) -> list[dict[str, Any]]:
    normalized = source.strip().lower()
    if normalized == "arxiv":
        return _fetch_arxiv_metadata(query=query, max_results=max_results, fetcher=fetcher)
    if normalized == "openalex":
        return _fetch_openalex_metadata(query=query, max_results=max_results, fetcher=fetcher)
    raise ValueError("unsupported_public_research_source")


def _obsidian_open_uri(*, vault_name: str, relative_path: str) -> str:
    if not relative_path:
        return ""
    params: dict[str, str] = {"file": relative_path}
    if vault_name:
        params["vault"] = vault_name
    return "obsidian://open?" + urlencode(params, quote_via=quote)


def _frontmatter_payload(lines: list[str]) -> list[str]:
    if lines and lines[0] == "---":
        lines = lines[1:]
    if lines and lines[-1] == "---":
        lines = lines[:-1]
    return lines


def _frontmatter_key(line: str) -> str:
    match = re.match(r"^([A-Za-z0-9_-]+)\s*:", line)
    return match.group(1) if match else ""


def _split_note(text: str) -> tuple[list[str], str]:
    if not text.startswith("---\n"):
        return [], text
    closing = text.find("\n---", 4)
    if closing == -1:
        return [], text
    payload = text[4:closing].splitlines()
    body_start = closing + len("\n---")
    if text[body_start:body_start + 1] == "\n":
        body_start += 1
    return payload, text[body_start:]


def _compose_frontmatter(
    generated_lines: list[str],
    existing_payload: list[str] | None = None,
) -> str:
    generated_payload = _frontmatter_payload(generated_lines)
    generated_keys = {
        key for key in (_frontmatter_key(line) for line in generated_payload) if key
    }
    preserved: list[str] = []
    skip_current_block = False
    for line in existing_payload or []:
        key = _frontmatter_key(line)
        if key:
            skip_current_block = key in generated_keys
            if not skip_current_block and line.strip():
                preserved.append(line)
            continue
        if not skip_current_block and line.strip():
            preserved.append(line)
    payload = generated_payload + preserved
    return "---\n" + "\n".join(payload) + "\n---"


def _managed_summary_block(paper: dict[str, Any]) -> str:
    authors_text = ", ".join(paper["authors"])
    source_id = _paper_source_id(paper)
    source_url = _paper_source_url(paper)
    lines = [
        MANAGED_BLOCK_START,
        "## Paper Metadata",
        "",
        f"**Authors**: {authors_text}",
        "",
        f"**{_paper_source_label(paper)}**: [{source_id}]({source_url})",
        "",
    ]
    if paper["doi"]:
        lines.extend([
            f"**DOI**: [{paper['doi']}](https://doi.org/{paper['doi']})",
            "",
        ])
    lines.extend([
        f"**Published**: {paper['published']}",
        "",
        f"**Primary Category**: {paper['primary_category']}",
        "",
        f"**Categories**: {', '.join(paper['categories'])}",
        "",
        "## Abstract",
        "",
        paper["summary"],
        "",
        MANAGED_BLOCK_END,
    ])
    return "\n".join(lines)


def _replace_managed_block(body: str, managed_block: str) -> str:
    pattern = re.compile(
        re.escape(MANAGED_BLOCK_START) + r".*?" + re.escape(MANAGED_BLOCK_END),
        flags=re.DOTALL,
    )
    if pattern.search(body):
        return pattern.sub(managed_block, body, count=1)
    return body.rstrip() + "\n\n" + managed_block + "\n"


def _generate_obsidian_note(
    paper: dict[str, Any],
    note_dir: Path,
    *,
    vault_name: str = "",
    relative_path: str = "",
) -> Path:
    source_id = _paper_source_id(paper)
    note_stem = _paper_note_stem(paper)
    note_path = note_dir / f"{note_stem}.md"

    authors_text = ", ".join(paper["authors"])
    year_text = str(paper.get("published") or "")[:4]
    paper_id = _paper_id_value(paper)
    effective_relative_path = relative_path or note_path.name
    open_uri = _obsidian_open_uri(
        vault_name=vault_name,
        relative_path=effective_relative_path,
    )
    source_prefix = _paper_source_prefix(paper)
    source_type = _paper_source_type(paper)
    source_url = _paper_source_url(paper)

    frontmatter_lines = [
        "---",
        f"note_id: {_yaml_scalar(note_stem)}",
        "schema_type: \"research_paper\"",
        "schema_name: \"devframe.paper.research_paper\"",
        f"title: {_yaml_scalar(paper['title'])}",
        f"paper_id: {_yaml_scalar(paper_id)}",
        f"paper_key: {_yaml_scalar(note_stem)}",
        f"authors: {_yaml_scalar(authors_text)}",
        f"author_list: {json_dumps_safe(paper['authors'])}",
        f"source_id: {_yaml_scalar(source_id)}",
        f"arxiv_id: {_yaml_scalar(paper.get('arxiv_id', ''))}",
        f"openalex_id: {_yaml_scalar(paper.get('openalex_id', ''))}",
        f"year: {_yaml_scalar(year_text)}",
        f"published: {_yaml_scalar(paper['published'])}",
        f"updated: {_yaml_scalar(paper['updated'])}",
        f"primary_category: {_yaml_scalar(paper['primary_category'])}",
        f"venue: {_yaml_scalar(_paper_venue(paper))}",
        f'categories: {json_dumps_safe(paper["categories"])}',
        f"doi: {_yaml_scalar(paper['doi'])}",
        f"source_url: {_yaml_scalar(source_url)}",
        f"pdf_url: {_yaml_scalar(paper['pdf_url'])}",
        "status: \"source_verified\"",
        "kb_status: \"captured\"",
        "read_status: \"unread\"",
        "review_status: \"needs_review\"",
        "evidence_count: 0",
        "diagnosis_issue_count: 0",
        "evidence_refs: []",
        f"source_type: {_yaml_scalar(source_type)}",
        "source_level: \"VERIFIED_SOURCE\"",
        f"obsidian_uri: {_yaml_scalar(open_uri)}",
        f"generated_at: {_yaml_scalar(_utc_now_text())}",
        f"schema_version: {_yaml_scalar(SCHEMA_VERSION)}",
        f"task_id: {_yaml_scalar(TASK_ID)}",
        f"tags: [{source_prefix}, public-research, kb-pilot, research-paper]",
        "---",
    ]

    managed_block = _managed_summary_block(paper)
    body_lines = [
        "",
        f"# {paper['title']}",
        "",
        managed_block,
        "",
        "## Reading Notes",
        "",
    ]

    note_dir.mkdir(parents=True, exist_ok=True)
    if note_path.exists():
        existing_payload, existing_body = _split_note(note_path.read_text(encoding="utf-8"))
        frontmatter = _compose_frontmatter(frontmatter_lines, existing_payload)
        body = _replace_managed_block(existing_body, managed_block)
        note_content = frontmatter + "\n" + body.lstrip("\n")
    else:
        note_content = "\n".join(frontmatter_lines) + "\n".join(body_lines)
    note_path.write_text(note_content, encoding="utf-8")
    return note_path


def json_dumps_safe(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False)


def _yaml_scalar(value: Any) -> str:
    return json.dumps(str(value), ensure_ascii=False)


def _vault_relative_text(vault_root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(vault_root.resolve()).as_posix()
    except ValueError:
        return _sha256_text(str(path.resolve()))


def _dataview_folder_literal(relative_folder: str) -> str:
    return relative_folder.replace("\\", "/").replace('"', '\\"')


def _generate_obsidian_dashboard(
    *,
    vault_root: Path,
    target_folder: Path,
    vault_name: str,
    paper_count: int,
    generated_at: str,
) -> dict[str, Any]:
    target_folder.mkdir(parents=True, exist_ok=True)
    dashboard_path = target_folder / DASHBOARD_FILENAME
    relative_path = _vault_relative_text(vault_root, dashboard_path)
    relative_folder = _vault_relative_text(vault_root, target_folder)
    folder_literal = _dataview_folder_literal(relative_folder)
    dashboard_uri = _obsidian_open_uri(vault_name=vault_name, relative_path=relative_path)
    content = "\n".join([
        "---",
        'note_id: "devframe-research-kb-dashboard"',
        'schema_type: "research_kb_dashboard"',
        'schema_name: "devframe.paper.research_kb_dashboard"',
        f"paper_note_count: {paper_count}",
        f"target_folder: {_yaml_scalar(relative_folder)}",
        f"obsidian_uri: {_yaml_scalar(dashboard_uri)}",
        f"generated_at: {_yaml_scalar(generated_at)}",
        f"schema_version: {_yaml_scalar(SCHEMA_VERSION)}",
        f"task_id: {_yaml_scalar(TASK_ID)}",
        "tags: [devframe, research-kb, dashboard]",
        "---",
        "",
        "# Research KB Dashboard",
        "",
        "## Papers",
        "",
        "```dataview",
        "TABLE year, primary_category, read_status, review_status, kb_status, source_url",
        f'FROM "{folder_literal}"',
        'WHERE schema_type = "research_paper"',
        "SORT year DESC, title ASC",
        "```",
        "",
        "## Review Queue",
        "",
        "```dataview",
        "TABLE year, primary_category, evidence_count, diagnosis_issue_count",
        f'FROM "{folder_literal}"',
        'WHERE schema_type = "research_paper" AND review_status != "accepted"',
        "SORT year DESC",
        "```",
        "",
        "## Notes",
        "",
        "- This dashboard is plain Markdown. Dataview renders the tables when installed.",
        "- Generated paper notes are updated through DevFrame managed blocks; user notes outside those blocks are preserved.",
        "",
    ])
    dashboard_path.write_text(content, encoding="utf-8")
    return {
        "relative_path": relative_path,
        "dashboard_uri": dashboard_uri,
        "dashboard_sha256": _sha256_file(dashboard_path),
        "path": dashboard_path,
    }


def _download_public_arxiv_pdfs(
    *,
    papers: list[dict[str, Any]],
    pdf_dir: Path,
    pdf_fetcher: PdfFetcher | None = None,
) -> tuple[list[Path], list[dict[str, Any]], list[str]]:
    pdf_dir.mkdir(parents=True, exist_ok=True)
    downloaded: list[Path] = []
    fingerprints: list[dict[str, Any]] = []
    failures: list[str] = []

    for paper in papers:
        arxiv_id = str(paper.get("arxiv_id") or "")
        pdf_url = str(paper.get("pdf_url") or "")
        if not arxiv_id and "/pdf/" in pdf_url:
            arxiv_id = _normalize_openalex_id(pdf_url.split("/pdf/", 1)[-1])
        if not arxiv_id:
            failures.append(f"{_paper_source_id(paper) or 'missing_source_id'}:ValueError")
            continue
        safe_id = _safe_arxiv_id(arxiv_id)
        pdf_path = pdf_dir / f"arxiv-{safe_id}.pdf"
        try:
            parsed = urlparse(pdf_url)
            if parsed.scheme != "https" or parsed.netloc not in {"arxiv.org", "www.arxiv.org"} or not parsed.path.startswith("/pdf/"):
                raise ValueError("pdf_url_not_arxiv_https_pdf")
            if pdf_fetcher is None:
                import httpx

                response = httpx.get(pdf_url, timeout=60.0, follow_redirects=True)
                response.raise_for_status()
                final_url = str(response.url)
                final = urlparse(final_url)
                if final.scheme != "https" or final.netloc not in {"arxiv.org", "www.arxiv.org"} or not final.path.startswith("/pdf/"):
                    raise ValueError("pdf_redirect_left_arxiv")
                content_type = str(response.headers.get("content-type") or "").lower()
                if content_type and "pdf" not in content_type:
                    raise ValueError("pdf_content_type_invalid")
                pdf_bytes = response.content
            else:
                pdf_bytes = pdf_fetcher(paper)
            if len(pdf_bytes) < 32:
                raise ValueError("pdf_too_small")
            if not pdf_bytes.startswith(b"%PDF"):
                raise ValueError("downloaded_content_is_not_pdf")
            pdf_path.write_bytes(pdf_bytes)
            downloaded.append(pdf_path)
            fingerprints.append({
                "arxiv_id": arxiv_id,
                "source_id": _paper_source_id(paper),
                "openalex_id": str(paper.get("openalex_id") or ""),
                "source_type": _paper_source_type(paper),
                "pdf_url_fingerprint": _sha256_text(str(paper.get("pdf_url") or "")),
                "pdf_sha256": _sha256_bytes(pdf_bytes),
                "pdf_size_bytes": len(pdf_bytes),
            })
        except Exception as exc:
            failures.append(f"{arxiv_id}:{type(exc).__name__}")

    return downloaded, fingerprints, failures


def _build_citation_evidence_map(
    *,
    papers: list[dict[str, Any]],
    pdf_fingerprints: list[dict[str, Any]],
    paper_fingerprints: list[dict[str, Any]],
    rag_report: dict[str, Any],
    rag_index_root: Path,
    target_folder: Path,
) -> list[dict[str, Any]]:
    pdf_by_id: dict[str, Any] = {}
    paper_by_id: dict[str, Any] = {}
    for item in pdf_fingerprints:
        sid = str(item.get("source_id") or "")
        aid = str(item.get("arxiv_id") or "")
        if sid and sid not in pdf_by_id:
            pdf_by_id[sid] = item
        if aid and aid not in pdf_by_id:
            pdf_by_id.setdefault(aid, item)
    for item in paper_fingerprints:
        sid = str(item.get("source_id") or "")
        aid = str(item.get("arxiv_id") or "")
        if sid and sid not in paper_by_id:
            paper_by_id[sid] = item
        if aid and aid not in paper_by_id:
            paper_by_id.setdefault(aid, item)
    retrieved_fingerprints = {
        str(item)
        for item in rag_report.get("retrieved_chunk_fingerprints", [])
        if str(item)
    }
    if not retrieved_fingerprints:
        return []

    chunks_by_source: dict[str, list[dict[str, Any]]] = {}
    chunks_path = rag_index_root / "chunks.jsonl"
    try:
        for line in chunks_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            record = json.loads(line)
            source_fingerprint = str(record.get("source_fingerprint") or "")
            if source_fingerprint:
                chunks_by_source.setdefault(source_fingerprint, []).append(record)
    except (OSError, json.JSONDecodeError):
        return []

    closed_loop_note_by_pdf: dict[str, str] = {}
    for note_path in target_folder.glob("closed-loop-*.md"):
        try:
            text = note_path.read_text(encoding="utf-8")
        except OSError:
            continue
        match = re.search(r"^source_pdf_fingerprint:\s*(sha256:[a-fA-F0-9]+)\s*$", text, flags=re.MULTILINE)
        if match:
            closed_loop_note_by_pdf[match.group(1)] = _sha256_file(note_path)

    rows: list[dict[str, Any]] = []
    for paper in papers:
        source_id = _paper_source_id(paper)
        arxiv_id = str(paper.get("arxiv_id") or "")
        pdf_record = pdf_by_id.get(source_id) or pdf_by_id.get(arxiv_id)
        paper_record = paper_by_id.get(source_id) or paper_by_id.get(arxiv_id)
        if not pdf_record or not paper_record:
            continue
        source_note_fingerprint = (
            closed_loop_note_by_pdf.get(str(pdf_record.get("pdf_sha256") or ""))
            or str(paper_record.get("note_sha256") or "")
        )
        source_chunks = chunks_by_source.get(source_note_fingerprint, [])
        chunk_record = next(
            (
                record
                for record in source_chunks
                if str(record.get("chunk_fingerprint") or "") in retrieved_fingerprints
            ),
            None,
        )
        if not chunk_record:
            continue
        chunk_fingerprint = str(chunk_record.get("chunk_fingerprint") or "")
        evidence_basis = "|".join([
            source_id,
            arxiv_id,
            str(pdf_record.get("pdf_sha256") or ""),
            str(paper_record.get("note_path_fingerprint") or ""),
            str(chunk_record.get("chunk_id") or ""),
            chunk_fingerprint,
        ])
        rows.append({
            "evidence_id": _sha256_text(evidence_basis),
            "citation_id": source_id,
            "source_id": source_id,
            "openalex_id": str(paper.get("openalex_id") or ""),
            "source_type": _paper_source_type(paper),
            "arxiv_id": arxiv_id,
            "pdf_sha256": pdf_record["pdf_sha256"],
            "note_path_fingerprint": paper_record["note_path_fingerprint"],
            "chunk_id": str(chunk_record.get("chunk_id") or ""),
            "chunk_fingerprint": chunk_fingerprint,
            "retrieval_hit": True,
            "source_level": "VERIFIED_SOURCE",
        })
    return rows


def _citation_record_from_public_source(paper: dict[str, Any]) -> dict[str, Any]:
    source_id = _paper_source_id(paper)
    return {
        "citation_key": source_id,
        "title": str(paper.get("title") or ""),
        "authors": list(paper.get("authors") or []),
        "year": str(paper.get("published") or "")[:4],
        "doi": str(paper.get("doi") or ""),
        "url": _paper_source_url(paper),
        "source_level": "VERIFIED_SOURCE",
        "source_type": _paper_source_type(paper),
    }


def build_public_research_kb_pilot_report(
    *,
    query: str = "",
    source: str = "arxiv",
    max_results: int = 5,
    vault_root: str | Path = "",
    target_folder: str | Path = "",
    runtime_dir: str | Path = "",
    vault_uri_name: str = "",
    obsidian_rest: bool = False,
    obsidian_rest_base_url: str = "https://127.0.0.1:27124",
    obsidian_rest_token_env: str = "OBSIDIAN_REST_API_KEY",
    obsidian_rest_open: bool = False,
    obsidian_rest_verify_tls: bool = False,
    obsidian_rest_http_client: Any | None = None,
    fetcher: MetadataFetcher | None = None,
    pdf_fetcher: PdfFetcher | None = None,
    rag_builder: RagBuilder | None = None,
    download_pdfs: bool = True,
    generated_at: str | None = None,
) -> dict[str, Any]:
    generated = generated_at or _utc_now_text()
    normalized_source = source.strip().lower() or "arxiv"
    source_kind = _source_kind(normalized_source)

    if normalized_source not in {"arxiv", "openalex"}:
        return _blocked_report(
            generated_at=generated,
            status="BLOCKED_UNSUPPORTED_SOURCE",
            reasons=[f"unsupported_source:{normalized_source}"],
            source_kind=source_kind,
        )

    if not query.strip():
        return _blocked_report(
            generated_at=generated,
            status="BLOCKED_MISSING_QUERY",
            reasons=["query_is_empty"],
            source_kind=source_kind,
        )

    vault = Path(vault_root).resolve() if vault_root else None
    target = Path(target_folder).resolve() if target_folder else None
    runtime = Path(runtime_dir).resolve() if runtime_dir else None

    vault_present = vault is not None and vault.exists() and vault.is_dir()
    target_in_vault = (
        vault is not None
        and target is not None
        and (target == vault or vault in target.parents)
    )
    runtime_ok = (
        runtime is not None
        and runtime != Path(runtime.anchor)
        and str(runtime).strip() != ""
    )

    if not vault_present:
        return _blocked_report(
            generated_at=generated,
            status="BLOCKED_VAULT_MISSING",
            reasons=["vault_root_not_present"],
            source_kind=source_kind,
        )
    if not target_in_vault:
        return _blocked_report(
            generated_at=generated,
            status="BLOCKED_TARGET_OUTSIDE_VAULT",
            reasons=["target_folder_outside_vault"],
            source_kind=source_kind,
        )
    if not runtime_ok:
        return _blocked_report(
            generated_at=generated,
            status="BLOCKED_RUNTIME_INVALID",
            reasons=["runtime_dir_invalid"],
            source_kind=source_kind,
        )

    papers: list[dict[str, Any]] = []
    source_status = "NOT_RUN"
    source_error = None
    try:
        papers = _fetch_public_metadata(
            source=normalized_source,
            query=query,
            max_results=max_results,
            fetcher=fetcher,
        )
        source_status = "PASS" if papers else "NO_RESULTS"
    except Exception as exc:
        source_status = "FAILED"
        source_error = str(exc)

    if not papers:
        if normalized_source == "arxiv":
            blocked_status = (
                "BLOCKED_ARXIV_UNAVAILABLE"
                if source_status == "FAILED"
                else "BLOCKED_NO_ARXIV_RESULTS"
            )
        else:
            blocked_status = (
                "BLOCKED_PUBLIC_SOURCE_UNAVAILABLE"
                if source_status == "FAILED"
                else "BLOCKED_NO_PUBLIC_SOURCE_RESULTS"
            )
        return {
            **_blocked_report(
                generated_at=generated,
                status=blocked_status,
                reasons=[f"source_status:{source_status}"]
                + ([f"source_error:{source_error}"] if source_error else []),
                source_kind=source_kind,
            ),
            "source_status": source_status,
            "arxiv_status": source_status if normalized_source == "arxiv" else "NOT_RUN",
        }

    note_records: list[dict[str, Any]] = []
    effective_vault_name = vault_uri_name.strip() if vault_uri_name.strip() else vault.name
    for paper in papers:
        try:
            note_stem = _paper_note_stem(paper)
            relative_path = _vault_relative_text(vault, target / f"{note_stem}.md")
            note_path = _generate_obsidian_note(
                paper,
                target,
                vault_name=effective_vault_name,
                relative_path=relative_path,
            )
            note_records.append({
                "arxiv_id": paper.get("arxiv_id", ""),
                "openalex_id": paper.get("openalex_id", ""),
                "source_id": _paper_source_id(paper),
                "relative_path": relative_path,
                "obsidian_uri": _obsidian_open_uri(
                    vault_name=effective_vault_name,
                    relative_path=relative_path,
                ),
                "note_sha256": _sha256_file(note_path),
                "path": note_path,
            })
        except OSError:
            continue

    note_paths = [record["relative_path"] for record in note_records]
    note_links = [
        {
            "arxiv_id": record["arxiv_id"],
            "openalex_id": record.get("openalex_id", ""),
            "source_id": record.get("source_id", record["arxiv_id"]),
            "relative_path": record["relative_path"],
            "obsidian_uri": record["obsidian_uri"],
        }
        for record in note_records
    ]
    obsidian_status = "PASS" if note_paths else "FAILED_WRITES"
    note_by_id = {record["source_id"]: record for record in note_records}
    dashboard_record: dict[str, str] = {}
    dashboard_status = "NOT_RUN"

    downloaded_pdfs: list[Path] = []
    pdf_fingerprints: list[dict[str, Any]] = []
    pdf_download_failures: list[str] = []
    pdf_download_status = "NOT_RUN"
    pdf_dir = runtime / "public-arxiv-pdfs"
    if download_pdfs:
        downloaded_pdfs, pdf_fingerprints, pdf_download_failures = _download_public_arxiv_pdfs(
            papers=papers,
            pdf_dir=pdf_dir,
            pdf_fetcher=pdf_fetcher,
        )
        if len(downloaded_pdfs) == len(papers):
            pdf_download_status = "PASS"
        elif downloaded_pdfs:
            pdf_download_status = "PARTIAL"
        else:
            pdf_download_status = "FAILED"

    paper_fingerprints = [
        {
            "arxiv_id": p.get("arxiv_id", ""),
            "openalex_id": p.get("openalex_id", ""),
            "source_id": _paper_source_id(p),
            "source_type": _paper_source_type(p),
            "title_fingerprint": _sha256_text(p["title"]),
            "doi": p["doi"] or "",
            "authors_count": len(p["authors"]),
            "note_path_fingerprint": _sha256_text(str(target / f"{_paper_note_stem(p)}.md")),
            "note_sha256": str(note_by_id.get(_paper_source_id(p), {}).get("note_sha256", "")),
        }
        for p in papers
    ]

    rag_status = "NOT_RUN"
    rag_report: dict[str, Any] = {}
    try:
        active_rag_builder = rag_builder
        if active_rag_builder is None:
            from .local_paper_rag_pipeline import (
                build_local_paper_rag_pipeline_report,
            )
            active_rag_builder = build_local_paper_rag_pipeline_report
        if download_pdfs and not downloaded_pdfs:
            rag_status = "BLOCKED"
            rag_report = {"pipeline_status": "BLOCKED_NO_PUBLIC_PDFS_DOWNLOADED"}
        else:
            rag_report = active_rag_builder(
                pdf_folder=pdf_dir if download_pdfs else vault,
                vault_root=vault,
                target_folder=target,
                runtime_dir=runtime / "rag",
                pdf_limit=max(1, len(downloaded_pdfs)) if download_pdfs else 0,
                top_k=3,
                queries=[query] if query else [],
            )
    except ImportError:
        rag_status = "FAILED_IMPORT"
        rag_report = {"error": "local_paper_rag_pipeline module unavailable"}
    except Exception as exc:
        rag_status = "FAILED_RUNTIME"
        rag_report = {"error": str(exc)}
    else:
        pipeline_status = str(rag_report.get("pipeline_status", ""))
        if pipeline_status.startswith("BLOCKED"):
            rag_status = "BLOCKED"
        elif pipeline_status.startswith("PASS"):
            rag_status = "PASS"
        else:
            rag_status = "DEGRADED"

    citation_lookup_status = "NOT_RUN"
    lookup_results: list[dict[str, Any]] = []
    citation_evidence_map: list[dict[str, Any]] = []
    try:
        from .citation_metadata_lookup import build_citation_metadata_lookup_report
        citation_records = [_citation_record_from_public_source(p) for p in papers]
        claims = [
            {
                "citation_key": _paper_source_id(p),
                "title_fragment": p["title"],
                "author": p["authors"][0] if p["authors"] else "",
                "year": p["published"][:4] if p["published"] else "",
                "doi": p["doi"],
                "source_hint": "fixture_metadata",
            }
            for p in papers
        ]
        for claim in claims:
            lookup = build_citation_metadata_lookup_report(
                citation_claim=claim,
                metadata_records=citation_records,
                lookup_options={"metadata_format": source_kind},
                generated_at=generated,
            )
            lookup_results.append(lookup)
        if lookup_results:
            citation_evidence_map = _build_citation_evidence_map(
                papers=papers,
                pdf_fingerprints=pdf_fingerprints,
                paper_fingerprints=paper_fingerprints,
                rag_report=rag_report,
                rag_index_root=runtime / "rag" / "index",
                target_folder=target,
            )
            statuses = {r["match_status"] for r in lookup_results}
            if (
                statuses == {"VERIFIED_SOURCE"}
                and len(citation_evidence_map) == len(lookup_results) == len(papers)
            ):
                citation_lookup_status = "PASS"
            elif "AMBIGUOUS_MATCH" in statuses:
                citation_lookup_status = "AMBIGUOUS"
            else:
                citation_lookup_status = "NEEDS_REVIEW"
    except ImportError:
        citation_lookup_status = "FAILED_IMPORT"
        lookup_results = [{"error": "citation_metadata_lookup module unavailable"}]
    except Exception:
        citation_lookup_status = "FAILED_RUNTIME"

    if note_paths:
        try:
            dashboard_record = _generate_obsidian_dashboard(
                vault_root=vault,
                target_folder=target,
                vault_name=effective_vault_name,
                paper_count=len(note_paths),
                generated_at=generated,
            )
            dashboard_status = "PASS"
        except OSError:
            dashboard_status = "FAILED_WRITES"

    obsidian_rest_status = "NOT_RUN"
    obsidian_rest_summary: dict[str, Any] = {}
    if obsidian_rest:
        try:
            from .obsidian_rest_api import sync_markdown_files_to_obsidian_rest

            files: list[tuple[str, Path]] = [
                (record["relative_path"], record["path"])
                for record in note_records
                if isinstance(record.get("path"), Path)
            ]
            dashboard_path = dashboard_record.get("path")
            if isinstance(dashboard_path, Path):
                files.append((str(dashboard_record.get("relative_path", "")), dashboard_path))
            obsidian_rest_summary = sync_markdown_files_to_obsidian_rest(
                files=files,
                base_url=obsidian_rest_base_url,
                token_env=obsidian_rest_token_env,
                verify_tls=obsidian_rest_verify_tls,
                open_relative_path=(
                    str(dashboard_record.get("relative_path", ""))
                    if obsidian_rest_open and dashboard_record
                    else ""
                ),
                http_client=obsidian_rest_http_client,
            )
            obsidian_rest_status = str(obsidian_rest_summary.get("status") or "FAILED_RUNTIME")
        except ImportError:
            obsidian_rest_status = "FAILED_IMPORT"
            obsidian_rest_summary = {
                "status": obsidian_rest_status,
                "token_persisted": False,
                "first_error": "obsidian_rest_api_module_unavailable",
            }
        except Exception as exc:
            obsidian_rest_status = "FAILED_RUNTIME"
            obsidian_rest_summary = {
                "status": obsidian_rest_status,
                "token_persisted": False,
                "first_error": type(exc).__name__,
            }

    arxiv_status = source_status if normalized_source == "arxiv" else "NOT_RUN"
    overall_status = "PASS"
    if source_status != "PASS":
        overall_status = "BLOCKED"
    elif obsidian_status != "PASS" or dashboard_status == "FAILED_WRITES":
        overall_status = "DEGRADED_OBSIDIAN"
    elif obsidian_rest and obsidian_rest_status != "PASS":
        overall_status = "DEGRADED_OBSIDIAN_REST"
    elif citation_lookup_status in ("FAILED_IMPORT", "FAILED_RUNTIME"):
        overall_status = "BLOCKED_CITATION_LOOKUP"
    elif pdf_download_status in ("FAILED", "PARTIAL"):
        overall_status = "PASS_DEGRADED_PUBLIC_PDF"
    elif citation_lookup_status in ("AMBIGUOUS", "NEEDS_REVIEW"):
        overall_status = "DEGRADED_CITATION_LOOKUP"
    elif rag_status in ("FAILED_IMPORT", "FAILED_RUNTIME"):
        overall_status = "PASS_DEGRADED_RAG"

    state_fingerprint = _sha256_text(
        f"{source_kind}|{source_status}|{obsidian_status}|{dashboard_status}|{obsidian_rest_status}|{pdf_download_status}|{rag_status}|{citation_lookup_status}|{len(papers)}|{len(note_paths)}"
    )

    return {
        "profile": PROFILE,
        "schema_version": SCHEMA_VERSION,
        "task_id": TASK_ID,
        "project_id": "dev-frame-system",
        "workflow_type": "paper",
        "generated_at": generated,
        "pilot_status": overall_status,
        "reasons": [],
        "source_kind": source_kind,
        "source_status": source_status,
        "arxiv_status": arxiv_status,
        "obsidian_status": obsidian_status,
        "pdf_download_status": pdf_download_status,
        "rag_status": rag_status,
        "citation_lookup_status": citation_lookup_status,
        "paper_count": len(papers),
        "note_count": len(note_paths),
        "pdf_count": len(downloaded_pdfs),
        "note_paths": note_paths,
        "note_links": note_links,
        "dashboard_status": dashboard_status,
        "dashboard_path": dashboard_record.get("relative_path", ""),
        "dashboard_uri": dashboard_record.get("dashboard_uri", ""),
        "obsidian_rest_status": obsidian_rest_status,
        "obsidian_rest_summary": obsidian_rest_summary,
        "paper_fingerprints": paper_fingerprints,
        "pdf_fingerprints": pdf_fingerprints,
        "pdf_download_failure_count": len(pdf_download_failures),
        "pdf_download_failures": pdf_download_failures[:5],
        "citation_lookup_results": lookup_results,
        "citation_evidence_map": citation_evidence_map,
        "rag_report_summary": {
            "pipeline_status": rag_report.get("pipeline_status", "UNKNOWN"),
            "pdf_count": rag_report.get("pdf_count", 0),
            "markdown_note_count": rag_report.get("markdown_note_count", 0),
            "chunk_count": rag_report.get("chunk_count", 0),
            "retrieval_query_count": rag_report.get("retrieval_query_count", 0),
            "retrieval_success_count": rag_report.get("retrieval_success_count", 0),
            "retrieved_chunk_fingerprint_count": len(rag_report.get("retrieved_chunk_fingerprints", [])),
            "retrieved_chunk_fingerprints": list(rag_report.get("retrieved_chunk_fingerprints", [])),
            "index_reused": rag_report.get("index_reused", False),
            "error": rag_report.get("error", ""),
        },
        "privacy_boundary": _boundary_flags(obsidian_rest_api_called=obsidian_rest),
        "artifact_minimization": {
            "source_kind": source_kind,
            "paper_count": len(papers),
            "note_count": len(note_paths),
            "pdf_count": len(downloaded_pdfs),
            "note_path_fingerprint_count": len(note_paths),
            "citation_claim_count": len(lookup_results),
        },
        "evidence_manifest": _evidence_manifest(
            source_fingerprint_count=len(papers),
            note_count=len(note_paths),
            report_status=overall_status,
            state_fingerprint=state_fingerprint,
        ),
        "known_limitations": [
            "Public scholarly metadata and public arXiv PDFs only; no private paper data is read.",
            "RAG pipeline integration depends on local FAISS and sentence-transformers.",
            "Citation lookup uses fixture-mode metadata derived from public source records.",
        ],
    }
