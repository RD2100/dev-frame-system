"""Local single-note retrieval manifest pilot for paper workflow.

This adapter deliberately avoids external/private RAG execution. It reads one
explicit allowlisted markdown note, builds deterministic local chunk
fingerprints, and emits minimized evidence only.
"""

from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PROFILE = "paper_rag_single_note_retrieval_pilot_report"
SCHEMA_VERSION = "1.0"
TASK_ID = "PAPER_RAG_SINGLE_OBSIDIAN_NOTE_LOCAL_RETRIEVAL_PILOT_A1"
DEFAULT_QUERY = "local retrieval boundary"


def _utc_now_text() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256_text(text: str) -> str:
    return f"sha256:{hashlib.sha256(text.encode('utf-8')).hexdigest()}"


def _sha256_bytes(data: bytes) -> str:
    return f"sha256:{hashlib.sha256(data).hexdigest()}"


def _normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _chunk_markdown(text: str, *, max_chars: int = 900) -> list[str]:
    chunks: list[str] = []
    blocks = [block.strip() for block in re.split(r"\n\s*\n", text) if block.strip()]
    for block in blocks:
        normalized = _normalize_text(block)
        while len(normalized) > max_chars:
            chunks.append(normalized[:max_chars])
            normalized = normalized[max_chars:].strip()
        if normalized:
            chunks.append(normalized)
    return chunks


def _query_terms(query: str) -> set[str]:
    return {
        term.lower()
        for term in re.findall(r"[A-Za-z0-9_\-\u4e00-\u9fff]+", query)
        if len(term) >= 2
    }


def _select_top_chunk_fingerprints(
    *,
    chunks: list[str],
    query: str,
    top_k: int,
) -> list[str]:
    terms = _query_terms(query)
    scored: list[tuple[int, int, str]] = []
    for index, chunk in enumerate(chunks):
        lowered = chunk.lower()
        score = sum(1 for term in terms if term in lowered)
        scored.append((score, -index, _sha256_text(f"{index}:{chunk}")))
    scored.sort(reverse=True)
    return [fingerprint for _, _, fingerprint in scored[:top_k]]


def _blocked_report(
    *,
    generated_at: str,
    status: str,
    reasons: list[str],
    vault_path_present: bool,
    note_path_present: bool,
    note_exists: bool,
    allowlist_count: int,
) -> dict[str, Any]:
    return {
        "profile": PROFILE,
        "schema_version": SCHEMA_VERSION,
        "task_id": TASK_ID,
        "project_id": "dev-frame-opencode",
        "workflow_type": "paper",
        "generated_at": generated_at,
        "pilot_status": status,
        "validation_kind": "local_single_note_retrieval_manifest",
        "source_kind": "obsidian_allowlisted_note",
        "human_required": True,
        "reasons": reasons,
        "source_summary": {
            "vault_path_present": vault_path_present,
            "note_path_present": note_path_present,
            "allowlisted_note_path_present": note_path_present,
            "note_exists": note_exists,
            "allowlist_count": allowlist_count,
            "note_size_bytes": 0,
            "note_sha256": "",
            "note_path_fingerprint": "",
        },
        "retrieval_manifest": {
            "retrieval_index_kind": "deterministic_local",
            "chunk_count": 0,
            "chunk_fingerprint_count": 0,
            "top_k": 0,
            "top_k_count": 0,
            "query_fingerprint": "",
            "chunk_fingerprints": [],
            "selected_chunk_fingerprints": [],
        },
        "runtime_boundary": {
            "whole_vault_scanned": False,
            "external_rag_called": False,
            "embeddings_api_called": False,
            "vector_db_called": False,
            "browser_cdp_or_cloud_used": False,
            "attachments_read": False,
            "pdf_or_full_text_read": False,
            "zotero_key_or_api_used": False,
            "writelab_called": False,
        },
        "privacy_boundary": {
            "raw_note_persisted": False,
            "raw_chunks_persisted": False,
            "raw_query_persisted": False,
            "raw_note_path_persisted": False,
            "raw_payload_persisted": False,
        },
        "final_acceptance_claimed": False,
        "paper_quality_acceptance": False,
        "production_ready": False,
        "live_ready_claimed": False,
        "rag_ready_claimed": False,
    }


def build_rag_single_note_retrieval_pilot_report(
    *,
    note_path: str | Path | None,
    allowlist_paths: list[str | Path] | None,
    vault_root: str | Path | None,
    query: str | None = None,
    top_k: int = 3,
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Build a minimized local retrieval manifest for one allowlisted note."""
    generated = generated_at or _utc_now_text()
    allowlist_paths = allowlist_paths or []
    vault = Path(vault_root).resolve() if vault_root is not None else None
    vault_path_present = vault.exists() if vault is not None else False
    if vault is None or not vault_path_present:
        return _blocked_report(
            generated_at=generated,
            status="BLOCKED_VAULT_MISSING",
            reasons=["vault_root_not_present"],
            vault_path_present=False,
            note_path_present=note_path is not None,
            note_exists=False,
            allowlist_count=len(allowlist_paths),
        )
    if note_path is None:
        return _blocked_report(
            generated_at=generated,
            status="BLOCKED_MISSING_NOTE",
            reasons=["missing_note_path"],
            vault_path_present=vault_path_present,
            note_path_present=False,
            note_exists=False,
            allowlist_count=len(allowlist_paths),
        )

    candidate = Path(note_path).resolve()
    allowlist = {Path(path).resolve() for path in allowlist_paths}
    if candidate not in allowlist:
        return _blocked_report(
            generated_at=generated,
            status="BLOCKED_NOTE_NOT_ALLOWLISTED",
            reasons=["note_path_not_allowlisted"],
            vault_path_present=vault_path_present,
            note_path_present=True,
            note_exists=candidate.exists(),
            allowlist_count=len(allowlist),
        )
    if not (candidate == vault or vault in candidate.parents):
        return _blocked_report(
            generated_at=generated,
            status="BLOCKED_NOTE_OUTSIDE_VAULT",
            reasons=["note_path_outside_vault"],
            vault_path_present=vault_path_present,
            note_path_present=True,
            note_exists=candidate.exists(),
            allowlist_count=len(allowlist),
        )
    if candidate.suffix.lower() != ".md":
        return _blocked_report(
            generated_at=generated,
            status="BLOCKED_NOT_MARKDOWN",
            reasons=["note_path_not_markdown"],
            vault_path_present=vault_path_present,
            note_path_present=True,
            note_exists=candidate.exists(),
            allowlist_count=len(allowlist),
        )
    if not candidate.exists():
        return _blocked_report(
            generated_at=generated,
            status="BLOCKED_MISSING_NOTE",
            reasons=["note_path_not_readable"],
            vault_path_present=vault_path_present,
            note_path_present=True,
            note_exists=False,
            allowlist_count=len(allowlist),
        )

    try:
        raw_bytes = candidate.read_bytes()
        text = raw_bytes.decode("utf-8")
    except (OSError, UnicodeDecodeError):
        return _blocked_report(
            generated_at=generated,
            status="BLOCKED_UNREADABLE_NOTE",
            reasons=["note_path_not_readable"],
            vault_path_present=vault_path_present,
            note_path_present=True,
            note_exists=candidate.exists(),
            allowlist_count=len(allowlist),
        )

    chunks = _chunk_markdown(text)
    if not chunks:
        return _blocked_report(
            generated_at=generated,
            status="BLOCKED_EMPTY_NOTE",
            reasons=["empty_note_after_chunking"],
            vault_path_present=vault_path_present,
            note_path_present=True,
            note_exists=True,
            allowlist_count=len(allowlist),
        )

    chunk_fingerprints = [
        _sha256_text(f"{index}:{chunk}") for index, chunk in enumerate(chunks)
    ]
    if len(set(chunk_fingerprints)) != len(chunk_fingerprints):
        return _blocked_report(
            generated_at=generated,
            status="BLOCKED_DUPLICATE_CHUNK_FINGERPRINT",
            reasons=["duplicate_chunk_fingerprint"],
            vault_path_present=vault_path_present,
            note_path_present=True,
            note_exists=True,
            allowlist_count=len(allowlist),
        )

    safe_top_k = max(1, min(top_k, len(chunks)))
    query_text = query or DEFAULT_QUERY
    selected = _select_top_chunk_fingerprints(
        chunks=chunks,
        query=query_text,
        top_k=safe_top_k,
    )
    manifest = {
        "manifest_id": "paper-rag-single-note-retrieval-manifest-a1",
        "schema_version": SCHEMA_VERSION,
        "task_id": TASK_ID,
        "producer": "dev-frame-opencode",
        "source_records": [
            {
                "source_type": "obsidian_allowlisted_note",
                "source_fingerprint": _sha256_bytes(raw_bytes),
                "privacy_level": "single_note_hash_only",
                "raw_payload_persisted": False,
            }
        ],
        "commands_run": ["aihub paper rag-single-note-pilot"],
        "raw_sensitive_fields_absent": True,
        "contains_raw_note": False,
        "contains_raw_chunks": False,
        "contains_raw_query": False,
        "contains_raw_note_path": False,
    }
    return {
        "profile": PROFILE,
        "schema_version": SCHEMA_VERSION,
        "task_id": TASK_ID,
        "project_id": "dev-frame-opencode",
        "workflow_type": "paper",
        "generated_at": generated,
        "pilot_status": "PASS_SINGLE_NOTE_RETRIEVAL_MANIFEST",
        "validation_kind": "local_single_note_retrieval_manifest",
        "source_kind": "obsidian_allowlisted_note",
        "human_required": False,
        "reasons": [],
        "source_summary": {
            "vault_path_present": True,
            "note_path_present": True,
            "allowlisted_note_path_present": True,
            "note_exists": True,
            "allowlist_count": len(allowlist),
            "note_size_bytes": len(raw_bytes),
            "note_sha256": _sha256_bytes(raw_bytes),
            "note_path_fingerprint": _sha256_text(str(candidate)),
        },
        "retrieval_manifest": {
            "retrieval_index_kind": "deterministic_local",
            "chunk_count": len(chunks),
            "chunk_fingerprint_count": len(chunk_fingerprints),
            "top_k": safe_top_k,
            "top_k_count": len(selected),
            "query_fingerprint": _sha256_text(query_text),
            "chunk_fingerprints": chunk_fingerprints,
            "selected_chunk_fingerprints": selected,
        },
        "runtime_boundary": {
            "whole_vault_scanned": False,
            "external_rag_called": False,
            "embeddings_api_called": False,
            "vector_db_called": False,
            "browser_cdp_or_cloud_used": False,
            "attachments_read": False,
            "pdf_or_full_text_read": False,
            "zotero_key_or_api_used": False,
            "writelab_called": False,
        },
        "privacy_boundary": {
            "raw_note_persisted": False,
            "raw_chunks_persisted": False,
            "raw_query_persisted": False,
            "raw_note_path_persisted": False,
            "raw_payload_persisted": False,
        },
        "evidence_manifest": manifest,
        "final_acceptance_claimed": False,
        "paper_quality_acceptance": False,
        "production_ready": False,
        "live_ready_claimed": False,
        "rag_ready_claimed": False,
    }
