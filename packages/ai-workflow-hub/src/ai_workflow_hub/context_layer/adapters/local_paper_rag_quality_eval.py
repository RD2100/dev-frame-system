"""Local/offline quality evaluation for minimized paper RAG pipeline evidence."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PROFILE = "paper_local_rag_quality_eval_report"
SCHEMA_VERSION = "1.0"
TASK_ID = "OPENCODE_LOCAL_PAPER_RAG_QUALITY_EVAL_A1"
PIPELINE_TASK_ID = "OPENCODE_LOCAL_PAPER_RAG_USABLE_PIPELINE_A1"


def _utc_now_text() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256_text(value: str) -> str:
    return f"sha256:{hashlib.sha256(value.encode('utf-8')).hexdigest()}"


def _sha256_file(path: Path) -> str:
    return f"sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}"


def _safe_read_json(path: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def _boundary_flags() -> dict[str, bool]:
    return {
        "raw_pdf_text_persisted": False,
        "raw_markdown_body_persisted": False,
        "raw_chunks_persisted": False,
        "raw_query_persisted": False,
        "raw_source_paths_persisted": False,
        "vectors_persisted": False,
        "faiss_index_binary_in_evidence": False,
        "api_keys_or_secrets_persisted": False,
        "zotero_api_called": False,
        "cloud_llm_called": False,
        "cloud_vector_db_called": False,
        "external_rag_called": False,
        "browser_cdp_cloud_or_miniapp_called": False,
        "whole_vault_scanned": False,
        "runtime_authorization_granted": False,
        "final_acceptance_claimed": False,
        "paper_quality_acceptance_claimed": False,
        "production_ready_claimed": False,
        "broad_live_ready_claimed": False,
        "general_rag_ready_claimed": False,
        "whole_vault_ready_claimed": False,
        "external_rag_ready_claimed": False,
        "cloud_ready_claimed": False,
    }


def _evidence_manifest(
    *,
    status: str,
    pipeline_report_fingerprint: str,
    pipeline_schema_fingerprint: str,
) -> dict[str, Any]:
    return {
        "manifest_id": "paper-local-rag-quality-eval-evidence-manifest-a1",
        "schema_version": SCHEMA_VERSION,
        "task_id": TASK_ID,
        "producer": "dev-frame-opencode",
        "quality_eval_status": status,
        "pipeline_report_fingerprint": pipeline_report_fingerprint,
        "pipeline_schema_fingerprint": pipeline_schema_fingerprint,
        "raw_sensitive_fields_absent": True,
        "contains_raw_pdf_text": False,
        "contains_raw_markdown_body": False,
        "contains_raw_chunks": False,
        "contains_raw_query": False,
        "contains_raw_paths": False,
        "contains_vectors": False,
        "contains_faiss_index_binary": False,
        "contains_api_keys_or_secrets": False,
    }


def _base_report(
    *,
    generated_at: str,
    status: str,
    reasons: list[str],
    source_pipeline_commit: str,
    pipeline_report_fingerprint: str,
    pipeline_schema_fingerprint: str,
) -> dict[str, Any]:
    return {
        "profile": PROFILE,
        "schema_version": SCHEMA_VERSION,
        "generated_at": generated_at,
        "task_id": TASK_ID,
        "quality_eval_status": status,
        "validation_mode": "local_offline_quality_eval",
        "quality_eval_kind": "deterministic_local_rules",
        "source_pipeline_task_id": PIPELINE_TASK_ID,
        "source_pipeline_commit": source_pipeline_commit,
        "source_pipeline_report_fingerprint": pipeline_report_fingerprint,
        "source_pipeline_schema_fingerprint": pipeline_schema_fingerprint,
        "reasons": reasons,
        "document_count": 0,
        "chunk_count": 0,
        "query_count": 0,
        "retrieval_success_count": 0,
        "retrieval_coverage_count": 0,
        "retrieval_coverage_ratio": 0.0,
        "top_k_total_count": 0,
        "empty_result_count": 0,
        "duplicate_result_count": 0,
        "low_confidence_count": 0,
        "score_floor_violation_count": 0,
        "known_source_mapping_count": 0,
        "unknown_source_fingerprint_count": 0,
        "citation_source_consistency_passed": False,
        "answer_readiness_proxy_kind": "deterministic_local_rules",
        "answer_readiness_proxy_passed": False,
        "quality_gate_passed": False,
        "issue_count": len(reasons),
        "warnings_count": 0,
        **_boundary_flags(),
        "evidence_manifest": _evidence_manifest(
            status=status,
            pipeline_report_fingerprint=pipeline_report_fingerprint,
            pipeline_schema_fingerprint=pipeline_schema_fingerprint,
        ),
    }


def build_local_paper_rag_quality_eval_report(
    *,
    pipeline_report: str | Path,
    pipeline_schema: str | Path | None = None,
    source_pipeline_commit: str = "",
    generated_at: str | None = None,
) -> dict[str, Any]:
    generated = generated_at or _utc_now_text()
    report_path = Path(pipeline_report).resolve()
    schema_path = Path(pipeline_schema).resolve() if pipeline_schema else None
    pipeline_report_fingerprint = _sha256_file(report_path) if report_path.exists() else ""
    pipeline_schema_fingerprint = (
        _sha256_file(schema_path) if schema_path and schema_path.exists() else ""
    )
    pipeline = _safe_read_json(report_path)
    if pipeline is None:
        return _base_report(
            generated_at=generated,
            status="BLOCKED_MISSING_PIPELINE_REPORT",
            reasons=["pipeline_report_missing_or_unreadable"],
            source_pipeline_commit=source_pipeline_commit,
            pipeline_report_fingerprint=pipeline_report_fingerprint,
            pipeline_schema_fingerprint=pipeline_schema_fingerprint,
        )
    reasons: list[str] = []
    if pipeline.get("task_id") != PIPELINE_TASK_ID:
        reasons.append("pipeline_task_id_mismatch")
    if pipeline.get("profile") != "paper_local_rag_pipeline_report":
        reasons.append("pipeline_profile_mismatch")
    if pipeline.get("pipeline_status") != "PASS_LOCAL_RAG_PIPELINE":
        reasons.append("pipeline_status_not_pass")
    for flag in [
        "raw_pdf_text_persisted",
        "raw_markdown_body_persisted",
        "raw_chunks_persisted",
        "raw_query_persisted",
        "raw_source_paths_persisted",
        "faiss_vectors_persisted",
        "faiss_index_binary_in_evidence",
        "secrets_persisted",
        "whole_vault_scanned",
        "external_rag_called",
        "embeddings_api_called",
        "vector_db_service_called",
        "cloud_called",
        "writelab_called",
        "zotero_api_called",
        "final_acceptance_claimed",
        "paper_quality_acceptance_claimed",
        "production_ready_claimed",
        "rag_ready_claimed",
    ]:
        if pipeline.get(flag) is not False:
            reasons.append(f"pipeline_boundary_flag_not_false:{flag}")
    document_count = int(pipeline.get("document_count", 0))
    chunk_count = int(pipeline.get("chunk_count", 0))
    query_count = int(pipeline.get("retrieval_query_count", 0))
    retrieval_success_count = int(pipeline.get("retrieval_success_count", 0))
    top_k_total_count = int(pipeline.get("top_k_total_count", 0))
    empty_result_count = int(pipeline.get("empty_result_count", 0))
    duplicate_result_count = int(pipeline.get("duplicate_result_count", 0))
    low_confidence_count = int(pipeline.get("low_confidence_count", 0))
    source_fingerprint_count = int(pipeline.get("source_fingerprint_count", 0))
    if document_count <= 0:
        reasons.append("document_count_empty")
    if chunk_count <= 0:
        reasons.append("chunk_count_empty")
    if query_count <= 0:
        reasons.append("query_count_empty")
    if retrieval_success_count < query_count:
        reasons.append("retrieval_coverage_incomplete")
    if empty_result_count > 0:
        reasons.append("empty_retrieval_results")
    if duplicate_result_count > 0:
        reasons.append("duplicate_top_k_results")
    if low_confidence_count > 0:
        reasons.append("low_confidence_results")
    if top_k_total_count <= 0:
        reasons.append("top_k_results_empty")
    if source_fingerprint_count <= 0 and top_k_total_count > 0:
        reasons.append("unknown_source_fingerprints")

    known_source_mapping_count = top_k_total_count if source_fingerprint_count > 0 else 0
    unknown_source_fingerprint_count = 0 if source_fingerprint_count > 0 else top_k_total_count
    retrieval_coverage_ratio = (
        round(retrieval_success_count / query_count, 4) if query_count else 0.0
    )
    quality_gate_passed = not reasons
    status = "PASS_LOCAL_RAG_QUALITY_EVAL" if quality_gate_passed else "FAILED_QUALITY_GATE"
    issue_count = len(reasons)
    warnings_count = empty_result_count + duplicate_result_count + low_confidence_count
    return {
        "profile": PROFILE,
        "schema_version": SCHEMA_VERSION,
        "generated_at": generated,
        "task_id": TASK_ID,
        "quality_eval_status": status,
        "validation_mode": "local_offline_quality_eval",
        "quality_eval_kind": "deterministic_local_rules",
        "source_pipeline_task_id": PIPELINE_TASK_ID,
        "source_pipeline_commit": source_pipeline_commit,
        "source_pipeline_report_fingerprint": pipeline_report_fingerprint,
        "source_pipeline_schema_fingerprint": pipeline_schema_fingerprint,
        "reasons": reasons,
        "document_count": document_count,
        "chunk_count": chunk_count,
        "query_count": query_count,
        "retrieval_success_count": retrieval_success_count,
        "retrieval_coverage_count": retrieval_success_count,
        "retrieval_coverage_ratio": retrieval_coverage_ratio,
        "top_k_total_count": top_k_total_count,
        "empty_result_count": empty_result_count,
        "duplicate_result_count": duplicate_result_count,
        "low_confidence_count": low_confidence_count,
        "score_floor_violation_count": low_confidence_count,
        "known_source_mapping_count": known_source_mapping_count,
        "unknown_source_fingerprint_count": unknown_source_fingerprint_count,
        "citation_source_consistency_passed": unknown_source_fingerprint_count == 0,
        "answer_readiness_proxy_kind": "deterministic_local_rules",
        "answer_readiness_proxy_passed": quality_gate_passed,
        "quality_gate_passed": quality_gate_passed,
        "issue_count": issue_count,
        "warnings_count": warnings_count,
        **_boundary_flags(),
        "evidence_manifest": _evidence_manifest(
            status=status,
            pipeline_report_fingerprint=pipeline_report_fingerprint,
            pipeline_schema_fingerprint=pipeline_schema_fingerprint,
        ),
    }
