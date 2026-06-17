"""RAG retrieval evidence contract helpers for offline paper MVP validation."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any

from .citation_integrity import SOURCE_NOT_AVAILABLE

LOCAL_FIXTURE_PROFILE = "paper_rag_local_fixture_pilot_report"
LOCAL_FIXTURE_SCHEMA_VERSION = "1.0"
LOCAL_FIXTURE_TASK_ID = "PAPER_RAG_LOCAL_FIXTURE_PILOT_A1"


def _utc_now_text() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256_text(text: str) -> str:
    return f"sha256:{hashlib.sha256(text.encode('utf-8')).hexdigest()}"


def build_retrieval_evidence(
    *,
    source_id: str | None,
    source_type: str,
    source_level: str,
    privacy_level: str,
    snippet: str = "",
    citation_key: str | None = None,
    note_path: str | None = None,
    file_path: str | None = None,
    retrieval_score: float | None = None,
    retrieved_at: str | None = None,
    stale_status: str = "fresh",
) -> dict[str, Any]:
    """Build retrieval evidence without pretending model memory is a source."""
    if not source_id:
        return {
            "source_id": "",
            "source_type": source_type,
            "citation_key": citation_key,
            "note_path": note_path,
            "file_path": file_path,
            "snippet": "",
            "retrieval_score": None,
            "retrieved_at": retrieved_at,
            "stale_status": "unknown",
            "source_level": SOURCE_NOT_AVAILABLE,
            "privacy_level": privacy_level,
            "source_available": False,
            "human_required": True,
        }

    return {
        "source_id": source_id,
        "source_type": source_type,
        "citation_key": citation_key,
        "note_path": note_path,
        "file_path": file_path,
        "snippet": snippet,
        "retrieval_score": retrieval_score,
        "retrieved_at": retrieved_at,
        "stale_status": stale_status,
        "source_level": source_level,
        "privacy_level": privacy_level,
        "source_available": True,
        "human_required": privacy_level == "private_blocked",
    }


def mark_retrieval_stale(evidence: dict[str, Any], stale_status: str) -> dict[str, Any]:
    """Return a copy of evidence with explicit stale/deleted status."""
    updated = dict(evidence)
    updated["stale_status"] = stale_status
    return updated


def build_rag_local_fixture_pilot_report(
    *,
    query: str | None = None,
    fixture_sources: list[dict[str, Any]] | None = None,
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Build minimized evidence for local/offline RAG fixture retrieval.

    The report deliberately stores only counts and fingerprints. It does not
    persist the raw query, source text, titles, notes, or retrieval payload.
    """
    generated = generated_at or _utc_now_text()
    if fixture_sources is None:
        sources = [
            {
                "source_id": "fixture:zotero-metadata:metadata-grounding",
                "source_type": "zotero_metadata_fixture",
                "source_level": "VERIFIED_SOURCE",
                "privacy_level": "synthetic_metadata",
                "retrieval_score": 0.92,
            },
            {
                "source_id": "fixture:obsidian-note:writing-boundary",
                "source_type": "obsidian_note_fixture",
                "source_level": "USER_NOTE_LEAD",
                "privacy_level": "synthetic_note",
                "retrieval_score": 0.74,
            },
        ]
    else:
        sources = fixture_sources
    query_text = query or "metadata-only retrieval boundary"
    if not sources:
        pilot_status = "BLOCKED"
        human_required = True
        reasons = ["empty_fixture_sources"]
    else:
        pilot_status = "PASS_LOCAL_FIXTURE_RAG"
        human_required = False
        reasons = []

    source_type_counts: dict[str, int] = {}
    privacy_level_counts: dict[str, int] = {}
    for source in sources:
        source_type = str(source.get("source_type", "unknown"))
        privacy_level = str(source.get("privacy_level", "unknown"))
        source_type_counts[source_type] = source_type_counts.get(source_type, 0) + 1
        privacy_level_counts[privacy_level] = (
            privacy_level_counts.get(privacy_level, 0) + 1
        )

    source_fingerprints = [
        _sha256_text(
            "|".join(
                [
                    str(source.get("source_id", "")),
                    str(source.get("source_type", "")),
                    str(source.get("source_level", "")),
                    str(source.get("privacy_level", "")),
                ]
            )
        )
        for source in sources
    ]
    manifest = {
        "manifest_id": "paper-rag-local-fixture-evidence-manifest-a1",
        "schema_version": LOCAL_FIXTURE_SCHEMA_VERSION,
        "task_id": LOCAL_FIXTURE_TASK_ID,
        "producer": "dev-frame-opencode",
        "source_records": [
            {
                "source_type": "rag_local_fixture",
                "source_fingerprint": fingerprint,
                "privacy_level": "local_fixture_hash_only",
                "raw_payload_persisted": False,
            }
            for fingerprint in source_fingerprints
        ],
        "commands_run": ["aihub paper rag-local-fixture-pilot"],
        "raw_sensitive_fields_absent": True,
        "contains_private_rag_payload": False,
        "contains_raw_query": False,
        "contains_raw_source_text": False,
    }
    report = {
        "profile": LOCAL_FIXTURE_PROFILE,
        "schema_version": LOCAL_FIXTURE_SCHEMA_VERSION,
        "task_id": LOCAL_FIXTURE_TASK_ID,
        "project_id": "dev-frame-opencode",
        "workflow_type": "paper",
        "generated_at": generated,
        "pilot_status": pilot_status,
        "validation_kind": "rag_local_fixture_metadata",
        "human_required": human_required,
        "reasons": reasons,
        "connection": {
            "private_rag_used": False,
            "external_vector_db_used": False,
            "obsidian_vault_scanned": False,
            "pdf_or_full_text_read": False,
            "uses_cloud": False,
        },
        "retrieval_summary": {
            "query_fingerprint": _sha256_text(query_text),
            "raw_query_persisted": False,
            "candidate_count": len(sources),
            "selected_count": len(sources),
            "source_type_counts": source_type_counts,
            "privacy_level_counts": privacy_level_counts,
            "source_fingerprints": source_fingerprints,
        },
        "privacy_boundary": {
            "raw_query_persisted": False,
            "raw_source_text_persisted": False,
            "raw_titles_persisted": False,
            "raw_notes_persisted": False,
            "paragraph_text_persisted": False,
            "writelab_token_persisted": False,
            "private_rag_payload_persisted": False,
        },
        "evidence_manifest": manifest,
        "final_acceptance_claimed": False,
        "paper_quality_acceptance": False,
        "live_ready_claimed": False,
        "production_ready": False,
        "real_pilot_completed": False,
    }
    if pilot_status == "BLOCKED":
        report.pop("evidence_manifest")
    return report
