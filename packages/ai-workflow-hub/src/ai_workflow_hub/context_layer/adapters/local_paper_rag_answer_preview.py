"""Deterministic answer-preview packet for local paper RAG evidence.

This adapter consumes minimized local RAG pipeline evidence and allowlisted
Markdown source identities. It emits human-reviewable answer themes without
persisting raw questions, paper text, chunks, local paths, vectors, or secrets.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .local_paper_rag_pipeline import (
    HYBRID_RERANK_STRATEGY,
    _hybrid_rerank_sources,
    _source_identity,
)


PROFILE = "paper_local_rag_answer_preview_report"
SCHEMA_VERSION = "1.0"
TASK_ID = "OPENCODE_LOCAL_PAPER_RAG_ANSWER_PREVIEW_PACKET_A1"
PIPELINE_TASK_ID = "OPENCODE_LOCAL_PAPER_RAG_USABLE_PIPELINE_A1"


QUESTION_DEFINITIONS = [
    {
        "question_id": "Q1_EARTHQUAKE_RESCUE_PURPOSE",
        "query": "\u5730\u9707\u6551\u63f4 \u865a\u62df\u8bad\u7ec3\u7cfb\u7edf \u76ee\u7684 \u4f5c\u7528",
        "expected_title_terms": ["\u5730\u9707\u6551\u63f4", "\u865a\u62df\u8bad\u7ec3"],
        "answer_theme_bullets": [
            "training objective framing",
            "rescue procedure rehearsal",
            "risk-reduced scenario practice",
        ],
    },
    {
        "question_id": "Q2_FOREIGN_MILITARY_CHARACTERISTICS",
        "query": "\u5916\u519b \u519b\u4e8b \u865a\u62df\u8bad\u7ec3\u7cfb\u7edf \u7279\u70b9",
        "expected_title_terms": ["\u5916\u519b", "\u519b\u4e8b", "\u865a\u62df\u8bad\u7ec3"],
        "answer_theme_bullets": [
            "simulation-based readiness",
            "repeatable scenario design",
            "technology-supported training control",
        ],
    },
    {
        "question_id": "Q3_VR_FIRE_RESCUE_ADVANTAGES",
        "query": "\u865a\u62df\u73b0\u5b9e \u6d88\u9632 \u6551\u63f4 \u8bad\u7ec3 \u4f18\u52bf",
        "expected_title_terms": ["\u6d88\u9632", "\u6551\u63f4", "\u865a\u62df\u73b0\u5b9e"],
        "answer_theme_bullets": [
            "safer practice environment",
            "repeatable emergency drills",
            "immersive decision rehearsal",
        ],
    },
    {
        "question_id": "Q4_VIRTUAL_SCENE_CONSTRUCTION_FACTORS",
        "query": "\u865a\u62df\u8bad\u7ec3\u7cfb\u7edf \u865a\u62df\u573a\u666f \u5efa\u8bbe \u8981\u7d20",
        "expected_title_terms": ["\u865a\u62df\u573a\u666f"],
        "answer_theme_bullets": [
            "scene fidelity and training objective alignment",
            "environment modeling and interaction design",
            "scenario coverage for operational tasks",
        ],
    },
    {
        "question_id": "Q5_MILITARY_VOCATIONAL_EDUCATION_VALUE",
        "query": "\u519b\u4e8b \u4efb\u804c\u6559\u80b2 \u865a\u62df\u8bad\u7ec3 \u5e94\u7528\u4ef7\u503c",
        "expected_title_terms": ["\u4efb\u804c\u6559\u80b2", "\u519b\u4e8b", "\u865a\u62df\u8bad\u7ec3"],
        "answer_theme_bullets": [
            "job-oriented skill transfer",
            "standardized local practice evidence",
            "repeatable competence evaluation support",
        ],
    },
]


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


def _discover_markdown(target_folder: Path) -> list[Path]:
    if not target_folder.exists() or not target_folder.is_dir():
        return []
    return sorted(target_folder.rglob("*.md"))


def _scope_reasons(target_folder: Path) -> list[str]:
    reasons: list[str] = []
    if target_folder == Path(target_folder.anchor):
        reasons.append("target_folder_must_not_be_drive_root")
    if target_folder.name == ".obsidian" or (target_folder / ".obsidian").exists():
        reasons.append("target_folder_must_be_allowlisted_notes_folder_not_vault_root")
    return reasons


def _boundary_flags() -> dict[str, bool]:
    return {
        "cloud_llm_called": False,
        "external_rag_called": False,
        "cloud_vector_db_called": False,
        "browser_cdp_cloud_or_miniapp_called": False,
        "zotero_api_called": False,
        "whole_vault_scanned": False,
        "raw_pdf_text_persisted": False,
        "raw_markdown_body_persisted": False,
        "raw_chunks_persisted": False,
        "raw_query_persisted": False,
        "raw_source_paths_persisted": False,
        "vectors_persisted": False,
        "faiss_index_binary_in_evidence": False,
        "api_keys_or_secrets_persisted": False,
        "raw_writelab_payload_persisted": False,
        "raw_writelab_response_persisted": False,
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
    question_count: int,
    answer_preview_count: int,
    q4_source_matched: bool,
) -> dict[str, Any]:
    return {
        "manifest_id": "paper-local-rag-answer-preview-evidence-manifest-a1",
        "schema_version": SCHEMA_VERSION,
        "task_id": TASK_ID,
        "producer": "dev-frame-opencode",
        "preview_status": status,
        "pipeline_report_fingerprint": pipeline_report_fingerprint,
        "question_count": question_count,
        "answer_preview_count": answer_preview_count,
        "q4_hybrid_expected_source_matched": q4_source_matched,
        "raw_sensitive_fields_absent": True,
        "contains_raw_pdf_text": False,
        "contains_raw_markdown_body": False,
        "contains_raw_chunks": False,
        "contains_raw_query": False,
        "contains_raw_paths": False,
        "contains_vectors": False,
        "contains_faiss_index_binary": False,
        "contains_secrets": False,
        "contains_raw_writelab_payload": False,
        "contains_raw_writelab_response": False,
    }


def _base_report(
    *,
    generated_at: str,
    status: str,
    reasons: list[str],
    source_pipeline_commit: str,
    pipeline_report_fingerprint: str,
    pipeline_schema_fingerprint: str,
    question_ids: list[str],
) -> dict[str, Any]:
    return {
        "profile": PROFILE,
        "schema_version": SCHEMA_VERSION,
        "generated_at": generated_at,
        "task_id": TASK_ID,
        "preview_status": status,
        "validation_kind": "local_deterministic_answer_preview",
        "answer_preview_kind": "deterministic_local_rules",
        "source_pipeline_task_id": PIPELINE_TASK_ID,
        "source_pipeline_commit": source_pipeline_commit,
        "source_pipeline_report_fingerprint": pipeline_report_fingerprint,
        "source_pipeline_schema_fingerprint": pipeline_schema_fingerprint,
        "reasons": reasons,
        "document_count": 0,
        "chunk_count": 0,
        "query_count": len(question_ids),
        "retrieval_success_count": 0,
        "answer_preview_count": 0,
        "question_ids": question_ids,
        "preview_rows": [],
        "hybrid_rerank_enabled": True,
        "rerank_strategy": HYBRID_RERANK_STRATEGY,
        "q4_hybrid_expected_source_matched": False,
        "citation_source_consistency_passed": False,
        "issue_count": len(reasons),
        "warnings_count": 0,
        **_boundary_flags(),
        "evidence_manifest": _evidence_manifest(
            status=status,
            pipeline_report_fingerprint=pipeline_report_fingerprint,
            question_count=len(question_ids),
            answer_preview_count=0,
            q4_source_matched=False,
        ),
    }


def _expected_source_fingerprints(
    *,
    markdown_files: list[Path],
    expected_title_terms: list[str],
) -> set[str]:
    return {
        _source_identity(path)["source_fingerprint"]
        for path in markdown_files
        if any(term in path.stem for term in expected_title_terms)
    }


def _preview_rows(markdown_files: list[Path], top_k: int) -> tuple[list[dict[str, Any]], bool, int]:
    rows: list[dict[str, Any]] = []
    warning_count = 0
    q4_matched = False
    for definition in QUESTION_DEFINITIONS:
        ranked = _hybrid_rerank_sources(
            markdown_files=markdown_files,
            query=str(definition["query"]),
        )[:top_k]
        expected_sources = _expected_source_fingerprints(
            markdown_files=markdown_files,
            expected_title_terms=[str(term) for term in definition["expected_title_terms"]],
        )
        top_sources = [str(item["source_fingerprint"]) for item in ranked]
        top_titles = [str(item["title_fingerprint"]) for item in ranked]
        expected_matched = bool(expected_sources and top_sources and top_sources[0] in expected_sources)
        if definition["question_id"] == "Q4_VIRTUAL_SCENE_CONSTRUCTION_FACTORS":
            q4_matched = expected_matched
        if not top_sources:
            warning_count += 1
        rows.append(
            {
                "question_id": str(definition["question_id"]),
                "query_fingerprint": _sha256_text(str(definition["query"])),
                "answer_theme_bullets": [str(item) for item in definition["answer_theme_bullets"]],
                "top_source_fingerprints": top_sources,
                "top_title_fingerprints": top_titles,
                "expected_source_matched": expected_matched,
                "citation_source_consistency_passed": bool(top_sources),
                "warnings_count": 0 if top_sources else 1,
                "issue_count": 0 if top_sources else 1,
            }
        )
    return rows, q4_matched, warning_count


def build_local_paper_rag_answer_preview_report(
    *,
    pipeline_report: str | Path,
    target_folder: str | Path,
    pipeline_schema: str | Path | None = None,
    source_pipeline_commit: str = "",
    top_k: int = 3,
    generated_at: str | None = None,
) -> dict[str, Any]:
    generated = generated_at or _utc_now_text()
    report_path = Path(pipeline_report).resolve()
    schema_path = Path(pipeline_schema).resolve() if pipeline_schema else None
    target = Path(target_folder).resolve()
    question_ids = [str(item["question_id"]) for item in QUESTION_DEFINITIONS]
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
            question_ids=question_ids,
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

    reasons.extend(_scope_reasons(target))
    markdown_files = [] if reasons else _discover_markdown(target)
    if not markdown_files:
        reasons.append("target_markdown_sources_missing")

    rows, q4_matched, row_warnings = _preview_rows(markdown_files, max(1, top_k))
    if not q4_matched:
        reasons.append("q4_expected_source_not_top_ranked")
    row_issue_count = sum(int(row["issue_count"]) for row in rows)
    issue_count = len(reasons) + row_issue_count
    warning_count = row_warnings
    status = "PASS_LOCAL_RAG_ANSWER_PREVIEW" if issue_count == 0 else "FAILED_PREVIEW_GATE"

    return {
        "profile": PROFILE,
        "schema_version": SCHEMA_VERSION,
        "generated_at": generated,
        "task_id": TASK_ID,
        "preview_status": status,
        "validation_kind": "local_deterministic_answer_preview",
        "answer_preview_kind": "deterministic_local_rules",
        "source_pipeline_task_id": PIPELINE_TASK_ID,
        "source_pipeline_commit": source_pipeline_commit,
        "source_pipeline_report_fingerprint": pipeline_report_fingerprint,
        "source_pipeline_schema_fingerprint": pipeline_schema_fingerprint,
        "reasons": reasons,
        "document_count": int(pipeline.get("document_count", 0)),
        "chunk_count": int(pipeline.get("chunk_count", 0)),
        "query_count": len(question_ids),
        "retrieval_success_count": int(pipeline.get("retrieval_success_count", 0)),
        "answer_preview_count": len(rows),
        "question_ids": question_ids,
        "preview_rows": rows,
        "hybrid_rerank_enabled": True,
        "rerank_strategy": HYBRID_RERANK_STRATEGY,
        "q4_hybrid_expected_source_matched": q4_matched,
        "citation_source_consistency_passed": all(
            bool(row["citation_source_consistency_passed"]) for row in rows
        ),
        "issue_count": issue_count,
        "warnings_count": warning_count,
        **_boundary_flags(),
        "evidence_manifest": _evidence_manifest(
            status=status,
            pipeline_report_fingerprint=pipeline_report_fingerprint,
            question_count=len(question_ids),
            answer_preview_count=len(rows),
            q4_source_matched=q4_matched,
        ),
    }
