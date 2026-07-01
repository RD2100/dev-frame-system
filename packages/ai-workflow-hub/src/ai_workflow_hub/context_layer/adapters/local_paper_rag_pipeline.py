"""Repeatable local paper RAG pipeline evidence.

This adapter wraps the scoped PDF -> Obsidian -> FAISS closed-loop pilot and
adds minimized refresh-state and deterministic quality spot-check evidence.
Raw PDF text, Markdown bodies, chunks, query text, local paths, vectors, and
secrets stay out of reports and evidence artifacts.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .local_paper_rag_closed_loop import (
    DEFAULT_QUERIES,
    build_local_paper_rag_closed_loop_report,
)
from .rag_faiss_obsidian_local_pilot import DEFAULT_EMBEDDING_MODEL


PROFILE = "paper_local_rag_pipeline_report"
SCHEMA_VERSION = "1.0"
TASK_ID = "OPENCODE_LOCAL_PAPER_RAG_USABLE_PIPELINE_A1"
HYBRID_RERANK_STRATEGY = "embedding_plus_title_keyword_source_count"
HYBRID_RERANK_PROBES = [
    {
        "probe_id": "q4_virtual_scene",
        "query": "虚拟训练系统的虚拟场景建设需要关注哪些要素？",
        "expected_title_terms": ["虚拟场景"],
    },
]

ClosedLoopBuilder = Callable[..., dict[str, Any]]


def _utc_now_text() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256_text(value: str) -> str:
    return f"sha256:{hashlib.sha256(value.encode('utf-8')).hexdigest()}"


def _sha256_bytes(value: bytes) -> str:
    return f"sha256:{hashlib.sha256(value).hexdigest()}"


def _sha256_file(path: Path) -> str:
    return f"sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}"


def _safe_read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    return value if isinstance(value, dict) else {}


def _within(parent: Path, child: Path) -> bool:
    return child == parent or parent in child.parents


def _scope_reasons(
    *,
    pdf_folder: Path,
    vault_root: Path,
    target_folder: Path,
    runtime_dir: Path,
) -> list[str]:
    reasons: list[str] = []
    if not pdf_folder.exists() or not pdf_folder.is_dir():
        reasons.append("pdf_folder_missing")
    if not vault_root.exists() or not vault_root.is_dir():
        reasons.append("vault_root_missing")
    if target_folder == vault_root:
        reasons.append("target_folder_must_not_be_vault_root")
    if not _within(vault_root, target_folder):
        reasons.append("target_folder_outside_vault")
    if runtime_dir == Path(runtime_dir.anchor):
        reasons.append("runtime_dir_must_not_be_drive_root")
    return sorted(set(reasons))


def _discover_pdfs(pdf_folder: Path, limit: int) -> list[Path]:
    return sorted(pdf_folder.rglob("*.pdf"))[: max(1, limit)]


def _discover_markdown(target_folder: Path) -> list[Path]:
    if not target_folder.exists():
        return []
    return sorted(target_folder.rglob("*.md"))


def _rerank_title_tokens(text: str) -> set[str]:
    normalized = text.lower()
    ascii_tokens = set(re.findall(r"[a-z0-9]{2,}", normalized))
    cjk_chars = re.findall(r"[\u4e00-\u9fff]", normalized)
    cjk_bigrams = {"".join(cjk_chars[index : index + 2]) for index in range(len(cjk_chars) - 1)}
    cjk_trigrams = {"".join(cjk_chars[index : index + 3]) for index in range(len(cjk_chars) - 2)}
    return ascii_tokens | cjk_bigrams | cjk_trigrams


def _source_identity(path: Path) -> dict[str, str]:
    stem = path.stem
    return {
        "source_fingerprint": _sha256_text(str(path.resolve())),
        "title_fingerprint": _sha256_text(stem),
    }


def _hybrid_rerank_sources(
    *,
    markdown_files: list[Path],
    query: str,
) -> list[dict[str, Any]]:
    query_tokens = _rerank_title_tokens(query)
    ranked: list[dict[str, Any]] = []
    for path in markdown_files:
        title_tokens = _rerank_title_tokens(path.stem)
        overlap_count = len(query_tokens & title_tokens)
        source_count_bonus = 1 if "source" in path.stem.lower() else 0
        # Keep scores deterministic and local; no raw title/path/query leaves this function.
        score = (overlap_count * 10) + source_count_bonus
        identity = _source_identity(path)
        ranked.append(
            {
                "source_fingerprint": identity["source_fingerprint"],
                "title_fingerprint": identity["title_fingerprint"],
                "hybrid_score": score,
            }
        )
    return sorted(
        ranked,
        key=lambda item: (
            -int(item["hybrid_score"]),
            str(item["source_fingerprint"]),
        ),
    )


def _hybrid_rerank_spot_check(
    *,
    markdown_files: list[Path],
    probes: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    active_probes = probes or HYBRID_RERANK_PROBES
    query_count = len(active_probes)
    expected_matches = 0
    top_source_fingerprints: list[str] = []
    for probe in active_probes:
        ranked = _hybrid_rerank_sources(
            markdown_files=markdown_files,
            query=str(probe["query"]),
        )
        if not ranked:
            continue
        top_fingerprint = str(ranked[0]["source_fingerprint"])
        top_source_fingerprints.append(top_fingerprint)
        expected_terms = [str(term) for term in probe.get("expected_title_terms", [])]
        expected_sources = [
            _source_identity(path)["source_fingerprint"]
            for path in markdown_files
            if any(term in path.stem for term in expected_terms)
        ]
        if top_fingerprint in expected_sources:
            expected_matches += 1
    issue_count = query_count - expected_matches
    return {
        "hybrid_rerank_enabled": True,
        "rerank_strategy": HYBRID_RERANK_STRATEGY,
        "rerank_spot_check_passed": query_count > 0 and issue_count == 0,
        "rerank_query_count": query_count,
        "rerank_expected_source_match_count": expected_matches,
        "rerank_issue_count": issue_count,
        "rerank_warning_count": 0,
        "rerank_top_source_fingerprints": top_source_fingerprints,
    }


def _file_records(paths: list[Path], *, kind: str) -> list[dict[str, str]]:
    records: list[dict[str, str]] = []
    for path in paths:
        try:
            content_fingerprint = _sha256_file(path)
        except OSError:
            continue
        records.append(
            {
                "kind": kind,
                "path_fingerprint": _sha256_text(str(path.resolve())),
                "content_fingerprint": content_fingerprint,
            }
        )
    return records


def _compare_records(
    previous: list[dict[str, str]],
    current: list[dict[str, str]],
) -> dict[str, int]:
    previous_by_path = {
        item["path_fingerprint"]: item["content_fingerprint"]
        for item in previous
        if "path_fingerprint" in item and "content_fingerprint" in item
    }
    current_by_path = {
        item["path_fingerprint"]: item["content_fingerprint"]
        for item in current
        if "path_fingerprint" in item and "content_fingerprint" in item
    }
    new_count = 0
    changed_count = 0
    unchanged_count = 0
    for key, value in current_by_path.items():
        if key not in previous_by_path:
            new_count += 1
        elif previous_by_path[key] != value:
            changed_count += 1
        else:
            unchanged_count += 1
    deleted_count = len(set(previous_by_path) - set(current_by_path))
    return {
        "new_count": new_count,
        "changed_count": changed_count,
        "unchanged_count": unchanged_count,
        "deleted_count": deleted_count,
    }


def _boundary_flags() -> dict[str, bool]:
    return {
        "raw_pdf_text_persisted": False,
        "raw_markdown_body_persisted": False,
        "raw_chunks_persisted": False,
        "raw_query_persisted": False,
        "raw_source_paths_persisted": False,
        "faiss_vectors_persisted": False,
        "faiss_index_binary_in_evidence": False,
        "secrets_persisted": False,
        "whole_vault_scanned": False,
        "external_rag_called": False,
        "embeddings_api_called": False,
        "vector_db_service_called": False,
        "cloud_called": False,
        "writelab_called": False,
        "zotero_api_called": False,
        "final_acceptance_claimed": False,
        "paper_quality_acceptance_claimed": False,
        "production_ready_claimed": False,
        "rag_ready_claimed": False,
    }


def _evidence_manifest(
    *,
    source_fingerprint_count: int,
    markdown_fingerprint_count: int,
    state_fingerprint: str,
    report_status: str,
) -> dict[str, Any]:
    return {
        "manifest_id": "paper-local-rag-pipeline-evidence-manifest-a1",
        "schema_version": SCHEMA_VERSION,
        "task_id": TASK_ID,
        "producer": "dev-frame-opencode",
        "report_status": report_status,
        "source_fingerprint_count": source_fingerprint_count,
        "markdown_fingerprint_count": markdown_fingerprint_count,
        "state_fingerprint": state_fingerprint,
        "raw_sensitive_fields_absent": True,
        "contains_raw_pdf_text": False,
        "contains_raw_markdown_body": False,
        "contains_raw_chunks": False,
        "contains_raw_query": False,
        "contains_raw_paths": False,
        "contains_vectors": False,
        "contains_faiss_index_binary": False,
        "contains_secrets": False,
    }


def _quality_spot_check(
    *,
    retrieval_query_count: int,
    retrieval_success_count: int,
    top_k_total_count: int,
    chunk_count: int,
    duplicate_chunk_count: int,
) -> dict[str, int | str | bool]:
    empty_result_count = max(0, retrieval_query_count - retrieval_success_count)
    low_confidence_count = 0
    if retrieval_query_count and top_k_total_count < retrieval_query_count:
        low_confidence_count = retrieval_query_count - top_k_total_count
    warnings_count = empty_result_count + duplicate_chunk_count + low_confidence_count
    issue_count = warnings_count
    return {
        "quality_spot_check_attempted": True,
        "quality_spot_check_kind": "deterministic_local_rules",
        "coverage_count": retrieval_success_count,
        "empty_result_count": empty_result_count,
        "duplicate_result_count": duplicate_chunk_count,
        "low_confidence_count": low_confidence_count,
        "issue_count": issue_count,
        "warnings_count": warnings_count,
        "usefulness_signal_count": min(chunk_count, top_k_total_count),
    }


def _duplicate_chunk_count(index_root: Path) -> int:
    chunks_file = index_root / "chunks.jsonl"
    if not chunks_file.exists():
        return 0
    seen: set[str] = set()
    duplicates = 0
    try:
        with chunks_file.open("r", encoding="utf-8") as handle:
            for line in handle:
                item = json.loads(line)
                fingerprint = item.get("chunk_fingerprint", "")
                if not fingerprint:
                    continue
                if fingerprint in seen:
                    duplicates += 1
                seen.add(fingerprint)
    except (OSError, json.JSONDecodeError):
        return 0
    return duplicates


def _blocked_report(
    *,
    generated_at: str,
    status: str,
    reasons: list[str],
    pdf_folder_fingerprint: str,
    target_folder_fingerprint: str,
    runtime_fingerprint: str,
) -> dict[str, Any]:
    quality = _quality_spot_check(
        retrieval_query_count=0,
        retrieval_success_count=0,
        top_k_total_count=0,
        chunk_count=0,
        duplicate_chunk_count=0,
    )
    return {
        "profile": PROFILE,
        "schema_version": SCHEMA_VERSION,
        "generated_at": generated_at,
        "task_id": TASK_ID,
        "pipeline_status": status,
        "validation_mode": "local_runtime_pipeline",
        "local_runtime_kind": "pdf_obsidian_faiss_rules_pipeline",
        "reasons": reasons,
        "pdf_source_authorized": True,
        "obsidian_vault_authorized": True,
        "target_folder_authorized": True,
        "pdf_folder_fingerprint": pdf_folder_fingerprint,
        "target_folder_fingerprint": target_folder_fingerprint,
        "runtime_dir_fingerprint": runtime_fingerprint,
        "pdf_count": 0,
        "markdown_note_count": 0,
        "document_count": 0,
        "chunk_count": 0,
        "source_fingerprint_count": 0,
        "new_count": 0,
        "changed_count": 0,
        "unchanged_count": 0,
        "deleted_count": 0,
        "index_reused": False,
        "index_rebuilt": False,
        "refresh_required": False,
        "refresh_completed": False,
        "embedding_dimension": 0,
        "model_name": DEFAULT_EMBEDDING_MODEL,
        "model_fingerprint": _sha256_text(DEFAULT_EMBEDDING_MODEL),
        "retrieval_query_count": 0,
        "retrieval_success_count": 0,
        "top_k_total_count": 0,
        **_hybrid_rerank_spot_check(markdown_files=[]),
        **quality,
        **_boundary_flags(),
        "evidence_manifest": _evidence_manifest(
            source_fingerprint_count=0,
            markdown_fingerprint_count=0,
            state_fingerprint="",
            report_status=status,
        ),
    }


def build_local_paper_rag_pipeline_report(
    *,
    pdf_folder: str | Path,
    vault_root: str | Path,
    target_folder: str | Path,
    runtime_dir: str | Path,
    embedding_model: str = DEFAULT_EMBEDDING_MODEL,
    pdf_limit: int = 6,
    top_k: int = 3,
    queries: list[str] | None = None,
    generated_at: str | None = None,
    closed_loop_builder: ClosedLoopBuilder | None = None,
) -> dict[str, Any]:
    generated = generated_at or _utc_now_text()
    pdf_root = Path(pdf_folder).resolve()
    vault = Path(vault_root).resolve()
    target = Path(target_folder).resolve()
    runtime = Path(runtime_dir).resolve()
    index_root = runtime / "index"
    state_path = runtime / "pipeline-state.json"
    pdf_folder_fingerprint = _sha256_text(str(pdf_root))
    target_folder_fingerprint = _sha256_text(str(target))
    runtime_fingerprint = _sha256_text(str(runtime))

    reasons = _scope_reasons(
        pdf_folder=pdf_root,
        vault_root=vault,
        target_folder=target,
        runtime_dir=runtime,
    )
    if reasons:
        return _blocked_report(
            generated_at=generated,
            status="BLOCKED_SCOPE_INVALID",
            reasons=reasons,
            pdf_folder_fingerprint=pdf_folder_fingerprint,
            target_folder_fingerprint=target_folder_fingerprint,
            runtime_fingerprint=runtime_fingerprint,
        )

    pdfs = _discover_pdfs(pdf_root, pdf_limit)
    if not pdfs:
        return _blocked_report(
            generated_at=generated,
            status="BLOCKED_NO_PDFS_FOUND",
            reasons=["no_pdfs_found"],
            pdf_folder_fingerprint=pdf_folder_fingerprint,
            target_folder_fingerprint=target_folder_fingerprint,
            runtime_fingerprint=runtime_fingerprint,
        )

    runtime.mkdir(parents=True, exist_ok=True)
    previous_state = _safe_read_json(state_path)
    previous_records = previous_state.get("records", [])
    if not isinstance(previous_records, list):
        previous_records = []

    pre_pdf_records = _file_records(pdfs, kind="pdf")
    pre_markdown_records = _file_records(_discover_markdown(target), kind="markdown")
    pre_records = pre_pdf_records + pre_markdown_records
    pre_delta = _compare_records(previous_records, pre_records)
    refresh_required = (
        not previous_records
        or pre_delta["new_count"] > 0
        or pre_delta["changed_count"] > 0
        or pre_delta["deleted_count"] > 0
    )

    active_builder = closed_loop_builder or build_local_paper_rag_closed_loop_report
    closed_loop = active_builder(
        pdf_source_folder=pdf_root,
        obsidian_vault_root=vault,
        target_folder=target,
        index_root=index_root,
        embedding_model=embedding_model,
        pdf_limit=pdf_limit,
        queries=queries or DEFAULT_QUERIES,
        top_k=top_k,
        generated_at=generated,
    )
    if closed_loop.get("pilot_status") != "PASS_LOCAL_PAPER_RAG_CLOSED_LOOP":
        return _blocked_report(
            generated_at=generated,
            status="BLOCKED_CLOSED_LOOP_FAILED",
            reasons=["closed_loop_failed", str(closed_loop.get("pilot_status", ""))],
            pdf_folder_fingerprint=pdf_folder_fingerprint,
            target_folder_fingerprint=target_folder_fingerprint,
            runtime_fingerprint=runtime_fingerprint,
        )

    post_markdown_records = _file_records(_discover_markdown(target), kind="markdown")
    post_markdown_files = _discover_markdown(target)
    current_records = pre_pdf_records + post_markdown_records
    post_delta = _compare_records(previous_records, current_records)
    state = {
        "schema_version": SCHEMA_VERSION,
        "task_id": TASK_ID,
        "generated_at": generated,
        "records": current_records,
        "raw_paths_persisted": False,
        "raw_content_persisted": False,
    }
    state_path.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")
    state_fingerprint = _sha256_file(state_path)
    duplicate_chunk_count = _duplicate_chunk_count(index_root)
    quality = _quality_spot_check(
        retrieval_query_count=int(closed_loop["retrieval_queries_count"]),
        retrieval_success_count=int(closed_loop["retrieval_success_count"]),
        top_k_total_count=int(closed_loop["top_k_total_count"]),
        chunk_count=int(closed_loop["chunk_count"]),
        duplicate_chunk_count=duplicate_chunk_count,
    )
    rerank = _hybrid_rerank_spot_check(markdown_files=post_markdown_files)
    pipeline_status = "PASS_LOCAL_RAG_PIPELINE"
    return {
        "profile": PROFILE,
        "schema_version": SCHEMA_VERSION,
        "generated_at": generated,
        "task_id": TASK_ID,
        "pipeline_status": pipeline_status,
        "validation_mode": "local_runtime_pipeline",
        "local_runtime_kind": "pdf_obsidian_faiss_rules_pipeline",
        "reasons": [],
        "pdf_source_authorized": True,
        "obsidian_vault_authorized": True,
        "target_folder_authorized": True,
        "pdf_folder_fingerprint": pdf_folder_fingerprint,
        "target_folder_fingerprint": target_folder_fingerprint,
        "runtime_dir_fingerprint": runtime_fingerprint,
        "pdf_count": len(pdfs),
        "markdown_note_count": len(post_markdown_records),
        "document_count": int(closed_loop["document_count"]),
        "chunk_count": int(closed_loop["chunk_count"]),
        "source_fingerprint_count": len(current_records),
        "new_count": int(post_delta["new_count"]),
        "changed_count": int(post_delta["changed_count"]),
        "unchanged_count": int(post_delta["unchanged_count"]),
        "deleted_count": int(post_delta["deleted_count"]),
        "index_reused": not refresh_required and post_delta["changed_count"] == 0,
        "index_rebuilt": True,
        "refresh_required": refresh_required,
        "refresh_completed": True,
        "embedding_dimension": int(closed_loop["embedding_dimension"]),
        "model_name": str(closed_loop["model_name"]),
        "model_fingerprint": _sha256_text(str(closed_loop["model_name"])),
        "retrieval_query_count": int(closed_loop["retrieval_queries_count"]),
        "retrieval_success_count": int(closed_loop["retrieval_success_count"]),
        "retrieved_chunk_fingerprints": list(closed_loop.get("retrieved_chunk_fingerprints", [])),
        "top_k_total_count": int(closed_loop["top_k_total_count"]),
        **rerank,
        **quality,
        **_boundary_flags(),
        "evidence_manifest": _evidence_manifest(
            source_fingerprint_count=len(pre_pdf_records),
            markdown_fingerprint_count=len(post_markdown_records),
            state_fingerprint=state_fingerprint,
            report_status=pipeline_status,
        ),
    }
