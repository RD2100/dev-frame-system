"""One-command local paper RAG runner.

This adapter chains the existing minimized local RAG pipeline, quality eval,
and answer-preview adapters. It only emits status, counts, fingerprints, and
boundary flags; raw PDF text, Markdown bodies, chunks, queries, source paths,
vectors, index binaries, WriteLab payloads, and secrets stay out of reports.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .local_paper_rag_answer_preview import build_local_paper_rag_answer_preview_report
from .local_paper_rag_pipeline import build_local_paper_rag_pipeline_report
from .local_paper_rag_quality_eval import build_local_paper_rag_quality_eval_report


PROFILE = "paper_local_rag_one_command_runner_report"
SCHEMA_VERSION = "1.0"
TASK_ID = "OPENCODE_LOCAL_PAPER_RAG_ONE_COMMAND_RUNNER_A1"

PipelineBuilder = Callable[..., dict[str, Any]]
QualityEvalBuilder = Callable[..., dict[str, Any]]
AnswerPreviewBuilder = Callable[..., dict[str, Any]]


def _utc_now_text() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256_file(path: Path) -> str:
    return f"sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}"


def _sha256_text(value: str) -> str:
    return f"sha256:{hashlib.sha256(value.encode('utf-8')).hexdigest()}"


def _write_json(path: Path, value: dict[str, Any]) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding="utf-8")
    return _sha256_file(path)


def _status(value: dict[str, Any], key: str) -> str:
    status = value.get(key)
    return str(status) if status else "NOT_RUN"


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
        "raw_writelab_payload_persisted": False,
        "raw_writelab_response_persisted": False,
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
    runner_status: str,
    pipeline_report_fingerprint: str,
    quality_eval_report_fingerprint: str,
    answer_preview_report_fingerprint: str,
    stage_manifest_fingerprints: list[str],
) -> dict[str, Any]:
    return {
        "manifest_id": "paper-local-rag-one-command-runner-evidence-manifest-a1",
        "schema_version": SCHEMA_VERSION,
        "task_id": TASK_ID,
        "producer": "dev-frame-opencode",
        "runner_status": runner_status,
        "pipeline_report_fingerprint": pipeline_report_fingerprint,
        "quality_eval_report_fingerprint": quality_eval_report_fingerprint,
        "answer_preview_report_fingerprint": answer_preview_report_fingerprint,
        "stage_manifest_fingerprints": stage_manifest_fingerprints,
        "raw_sensitive_fields_absent": True,
        "contains_raw_pdf_text": False,
        "contains_raw_markdown_body": False,
        "contains_raw_chunks": False,
        "contains_raw_query": False,
        "contains_raw_paths": False,
        "contains_vectors": False,
        "contains_faiss_index_binary": False,
        "contains_api_keys_or_secrets": False,
        "contains_raw_writelab_payload": False,
        "contains_raw_writelab_response": False,
    }


def _stage_manifest_fingerprint(stage_report: dict[str, Any]) -> str:
    manifest = stage_report.get("evidence_manifest")
    if not isinstance(manifest, dict):
        return ""
    return _sha256_text(json.dumps(manifest, sort_keys=True, ensure_ascii=False))


def build_local_paper_rag_one_command_runner_report(
    *,
    pdf_folder: str | Path,
    vault_root: str | Path,
    target_folder: str | Path,
    runtime_dir: str | Path,
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2",
    pdf_limit: int = 6,
    top_k: int = 3,
    pipeline_schema: str | Path | None = None,
    source_pipeline_commit: str = "",
    generated_at: str | None = None,
    pipeline_builder: PipelineBuilder | None = None,
    quality_eval_builder: QualityEvalBuilder | None = None,
    answer_preview_builder: AnswerPreviewBuilder | None = None,
) -> dict[str, Any]:
    generated = generated_at or _utc_now_text()
    runtime = Path(runtime_dir).resolve()
    stage_dir = runtime / "one-command-runner"
    pipeline_path = stage_dir / "pipeline-report.json"
    quality_path = stage_dir / "quality-eval-report.json"
    preview_path = stage_dir / "answer-preview-report.json"

    active_pipeline_builder = pipeline_builder or build_local_paper_rag_pipeline_report
    active_quality_builder = quality_eval_builder or build_local_paper_rag_quality_eval_report
    active_preview_builder = answer_preview_builder or build_local_paper_rag_answer_preview_report

    pipeline_report = active_pipeline_builder(
        pdf_folder=pdf_folder,
        vault_root=vault_root,
        target_folder=target_folder,
        runtime_dir=runtime,
        embedding_model=embedding_model,
        pdf_limit=pdf_limit,
        top_k=top_k,
        generated_at=generated,
    )
    pipeline_report_fingerprint = _write_json(pipeline_path, pipeline_report)

    quality_report = active_quality_builder(
        pipeline_report=pipeline_path,
        pipeline_schema=pipeline_schema,
        source_pipeline_commit=source_pipeline_commit,
        generated_at=generated,
    )
    quality_report_fingerprint = _write_json(quality_path, quality_report)

    preview_report = active_preview_builder(
        pipeline_report=pipeline_path,
        target_folder=target_folder,
        pipeline_schema=pipeline_schema,
        source_pipeline_commit=source_pipeline_commit,
        top_k=top_k,
        generated_at=generated,
    )
    preview_report_fingerprint = _write_json(preview_path, preview_report)

    pipeline_status = _status(pipeline_report, "pipeline_status")
    quality_eval_status = _status(quality_report, "quality_eval_status")
    answer_preview_status = _status(preview_report, "preview_status")
    reasons: list[str] = []
    if pipeline_status != "PASS_LOCAL_RAG_PIPELINE":
        reasons.append("pipeline_stage_not_pass")
    if quality_eval_status != "PASS_LOCAL_RAG_QUALITY_EVAL":
        reasons.append("quality_eval_stage_not_pass")
    if quality_report.get("quality_gate_passed") is not True:
        reasons.append("quality_gate_not_passed")
    if answer_preview_status != "PASS_LOCAL_RAG_ANSWER_PREVIEW":
        reasons.append("answer_preview_stage_not_pass")
    for artifact_fingerprint in [
        pipeline_report_fingerprint,
        quality_report_fingerprint,
        preview_report_fingerprint,
    ]:
        if not artifact_fingerprint:
            reasons.append("stage_output_missing")

    runner_status = "PASS_LOCAL_RAG_RUN" if not reasons else "FAILED_LOCAL_RAG_RUN"
    stage_manifest_fingerprints = [
        item
        for item in [
            _stage_manifest_fingerprint(pipeline_report),
            _stage_manifest_fingerprint(quality_report),
            _stage_manifest_fingerprint(preview_report),
        ]
        if item
    ]
    return {
        "profile": PROFILE,
        "schema_version": SCHEMA_VERSION,
        "generated_at": generated,
        "task_id": TASK_ID,
        "runner_status": runner_status,
        "validation_mode": "local_one_command_runner",
        "runner_kind": "pipeline_quality_eval_answer_preview_chain",
        "reasons": sorted(set(reasons)),
        "pipeline_status": pipeline_status,
        "quality_eval_status": quality_eval_status,
        "answer_preview_status": answer_preview_status,
        "quality_gate_passed": bool(quality_report.get("quality_gate_passed") is True),
        "index_reused": bool(pipeline_report.get("index_reused") is True),
        "index_rebuilt": bool(pipeline_report.get("index_rebuilt") is True),
        "refresh_required": bool(pipeline_report.get("refresh_required") is True),
        "refresh_completed": bool(pipeline_report.get("refresh_completed") is True),
        "document_count": int(pipeline_report.get("document_count", 0)),
        "chunk_count": int(pipeline_report.get("chunk_count", 0)),
        "retrieval_query_count": int(pipeline_report.get("retrieval_query_count", 0)),
        "retrieval_success_count": int(pipeline_report.get("retrieval_success_count", 0)),
        "top_k_total_count": int(pipeline_report.get("top_k_total_count", 0)),
        "answer_preview_count": int(preview_report.get("answer_preview_count", 0)),
        "pipeline_report_fingerprint": pipeline_report_fingerprint,
        "quality_eval_report_fingerprint": quality_report_fingerprint,
        "answer_preview_report_fingerprint": preview_report_fingerprint,
        "stage_manifest_fingerprints": stage_manifest_fingerprints,
        **_boundary_flags(),
        "evidence_manifest": _evidence_manifest(
            runner_status=runner_status,
            pipeline_report_fingerprint=pipeline_report_fingerprint,
            quality_eval_report_fingerprint=quality_report_fingerprint,
            answer_preview_report_fingerprint=preview_report_fingerprint,
            stage_manifest_fingerprints=stage_manifest_fingerprints,
        ),
    }
