"""Offline paper workflow integration for citation metadata lookup."""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from typing import Any

from .citation_metadata_lookup import build_citation_metadata_lookup_report


def _utc_now_text() -> str:
    return datetime.now(timezone.utc).isoformat()


def _minimized_lookup_result(report: dict[str, Any]) -> dict[str, Any]:
    result = {
        "match_status": report["match_status"],
        "source_level": report["source_level"],
        "matched_fields": list(report.get("matched_fields", [])),
        "confidence_bucket": report["confidence_bucket"],
        "candidate_count": int(report.get("candidate_count", 0)),
        "warnings": list(report.get("warnings", [])),
    }
    if "record_fingerprint" in report:
        result["record_fingerprint"] = report["record_fingerprint"]
    if "redacted_sample" in report:
        result["redacted_sample"] = dict(report["redacted_sample"])
    return result


def build_citation_lookup_workflow_report(
    *,
    citation_claims: list[dict[str, Any]] | None,
    metadata_records: list[dict[str, Any]] | None,
    metadata_format: str = "fixture_metadata",
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Build a minimized local/offline paper workflow citation lookup report."""
    generated = generated_at or _utc_now_text()
    claims = [claim for claim in (citation_claims or []) if isinstance(claim, dict)]
    records = [record for record in (metadata_records or []) if isinstance(record, dict)]
    lookup_reports = [
        build_citation_metadata_lookup_report(
            citation_claim=claim,
            metadata_records=records,
            lookup_options={"metadata_format": metadata_format},
            generated_at=generated,
        )
        for claim in claims
    ]
    lookup_results = [_minimized_lookup_result(report) for report in lookup_reports]
    status_counts = Counter(result["match_status"] for result in lookup_results)
    source_counts = Counter(result["source_level"] for result in lookup_results)
    ambiguous_count = status_counts.get("AMBIGUOUS_MATCH", 0)
    source_not_available_count = status_counts.get("SOURCE_NOT_AVAILABLE", 0)
    blocked_count = status_counts.get("BLOCKED_RAW_METADATA", 0)
    verified_count = status_counts.get("VERIFIED_SOURCE", 0)
    if blocked_count:
        citation_lookup_status = "blocked_raw_metadata"
    elif ambiguous_count or source_not_available_count:
        citation_lookup_status = "needs_review"
    elif verified_count == len(lookup_results) and lookup_results:
        citation_lookup_status = "candidate_ready"
    else:
        citation_lookup_status = "needs_review"

    return {
        "profile": "paper_citation_lookup_workflow_report",
        "schema_version": "1.0",
        "task_id": "OPENCODE_PAPER_CITATION_LOOKUP_WORKFLOW_INTEGRATION_A1",
        "project_id": "dev-frame-opencode",
        "workflow_type": "paper",
        "generated_at": generated,
        "validation_mode": "synthetic_offline",
        "candidate_evidence_only": True,
        "citation_lookup_status": citation_lookup_status,
        "lookup_results": lookup_results,
        "summary_counts": {
            "claim_count": len(claims),
            "metadata_record_count": len(records),
            "verified_count": verified_count,
            "needs_verification_count": status_counts.get("NEEDS_VERIFICATION", 0),
            "ambiguous_count": ambiguous_count,
            "source_not_available_count": source_not_available_count,
            "blocked_raw_metadata_count": blocked_count,
        },
        "source_level_counts": {
            "VERIFIED_SOURCE": source_counts.get("VERIFIED_SOURCE", 0),
            "USER_NOTE_LEAD": source_counts.get("USER_NOTE_LEAD", 0),
            "NEEDS_VERIFICATION": source_counts.get("NEEDS_VERIFICATION", 0),
            "GENERAL_MODEL_SUGGESTION": source_counts.get("GENERAL_MODEL_SUGGESTION", 0),
            "SOURCE_NOT_AVAILABLE": source_counts.get("SOURCE_NOT_AVAILABLE", 0),
        },
        "ambiguous_count": ambiguous_count,
        "source_not_available_count": source_not_available_count,
        "raw_sensitive_fields_absent": True,
        "final_acceptance_claimed": False,
        "privacy_boundary": {
            "synthetic_or_fixture_only": True,
            "real_metadata_export_read": False,
            "real_zotero_app_accessed": False,
            "real_zotero_api_called": False,
            "pdf_read": False,
            "full_text_read": False,
            "obsidian_accessed": False,
            "private_rag_executed": False,
            "live_writelab_called": False,
            "browser_cdp_called": False,
            "cloud_called": False,
        },
        "known_limitations": [
            "This is local/offline citation lookup workflow evidence only.",
            "It does not prove content-level citation correctness.",
            "It does not read real Zotero app/API/storage, PDF/full text, Obsidian, RAG, or WriteLab.",
            "It cannot be treated as final governance acceptance.",
        ],
    }
