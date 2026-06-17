"""Local FAISS pilot for an allowlisted Obsidian Markdown scope.

The pilot reads only explicitly allowlisted Markdown files, builds a local
FAISS index, and emits minimized evidence. Raw note text, chunks, queries,
paths, and vectors are kept out of reports and evidence manifests.
"""

from __future__ import annotations

import hashlib
import importlib.metadata as metadata
import json
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np


PROFILE = "paper_rag_faiss_obsidian_local_pilot_report"
SCHEMA_VERSION = "1.0"
TASK_ID = "OPENCODE_RAG_FAISS_OBSIDIAN_LOCAL_INDEX_PILOT_A1"
DEFAULT_EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
DEFAULT_QUERY = "virtual training retrieval boundary"


Embedder = Callable[[list[str]], np.ndarray]


@dataclass(frozen=True)
class _Chunk:
    chunk_id: str
    source_fingerprint: str
    chunk_fingerprint: str
    text: str
    char_count: int


def _utc_now_text() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256_text(text: str) -> str:
    return f"sha256:{hashlib.sha256(text.encode('utf-8')).hexdigest()}"


def _sha256_bytes(data: bytes) -> str:
    return f"sha256:{hashlib.sha256(data).hexdigest()}"


def _sha256_file(path: Path) -> str:
    return f"sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}"


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


def _safe_version(package_name: str) -> str:
    try:
        return metadata.version(package_name)
    except metadata.PackageNotFoundError:
        return ""


def _blocked_report(
    *,
    generated_at: str,
    status: str,
    reasons: list[str],
    index_root: str | Path,
    embedding_model: str,
    install_command_summary: str,
    install_attempted: bool,
    install_performed: bool,
    model_download_performed: bool,
    faiss_present: bool | None = None,
    sentence_transformers_present: bool | None = None,
    source_scope_summary: dict[str, Any] | None = None,
) -> dict[str, Any]:
    faiss_version = _safe_version("faiss-cpu")
    st_version = _safe_version("sentence-transformers")
    faiss_available = bool(faiss_version) if faiss_present is None else faiss_present
    st_available = bool(st_version) if sentence_transformers_present is None else sentence_transformers_present
    return {
        "profile": PROFILE,
        "schema_version": SCHEMA_VERSION,
        "task_id": TASK_ID,
        "project_id": "dev-frame-opencode",
        "workflow_type": "paper",
        "generated_at": generated_at,
        "pilot_status": status,
        "validation_kind": "rag_faiss_obsidian_local_index_pilot",
        "source_scope": "obsidian_allowlisted_folder_or_files",
        "human_required": True,
        "reasons": reasons,
        "dependency_summary": {
            "faiss_present": faiss_available,
            "sentence_transformers_present": st_available,
            "faiss_cpu_version": faiss_version if faiss_available else "",
            "sentence_transformers_version": st_version if st_available else "",
            "install_attempted": install_attempted,
            "install_performed": install_performed,
            "install_command_fingerprint": (
                _sha256_text(install_command_summary) if install_command_summary else ""
            ),
            "install_command_summary": install_command_summary,
        },
        "model_summary": {
            "embedding_model_name": embedding_model,
            "embedding_model_fingerprint": _sha256_text(embedding_model),
            "model_load_attempted": False,
            "model_download_performed": model_download_performed,
            "local_cache_used": False,
            "remote_token_used": False,
        },
        "source_scope_summary": source_scope_summary or {
            "vault_present": False,
            "allowlist_entry_count": 0,
            "markdown_file_count": 0,
            "outside_vault_count": 0,
            "missing_allowlist_entry_count": 0,
            "whole_vault_allowlist_requested": False,
            "whole_vault_scanned": False,
            "allowlist_path_fingerprints": [],
        },
        "index_summary": {
            "index_root_fingerprint": _sha256_text(str(Path(index_root).resolve())),
            "document_count": 0,
            "chunk_count": 0,
            "embedding_dimension": 0,
            "faiss_index_kind": "",
            "index_artifact_fingerprint": "",
            "chunks_manifest_fingerprint": "",
            "manifest_fingerprint": "",
        },
        "query_smoke": {
            "query_fingerprint": "",
            "top_k": 0,
            "retrieved_count": 0,
            "retrieved_chunk_fingerprints": [],
        },
        "privacy_boundary": _privacy_boundary(),
        "runtime_boundary": _runtime_boundary(),
        "evidence_manifest": _evidence_manifest(
            source_fingerprints=[],
            artifact_fingerprints=[],
        ),
        "final_acceptance_claimed": False,
        "paper_quality_acceptance": False,
        "production_ready": False,
        "live_ready_claimed": False,
        "rag_ready_claimed": False,
        "whole_vault_ready_claimed": False,
    }


def _privacy_boundary() -> dict[str, bool]:
    return {
        "raw_note_persisted_in_report_or_evidence": False,
        "raw_chunks_persisted_in_report_or_evidence": False,
        "raw_query_persisted": False,
        "raw_paths_persisted": False,
        "embedding_vectors_persisted_in_evidence": False,
        "api_key_persisted": False,
        "zotero_key_persisted": False,
    }


def _runtime_boundary() -> dict[str, bool]:
    return {
        "whole_vault_scanned": False,
        "external_rag_called": False,
        "embeddings_api_called": False,
        "vector_db_service_called": False,
        "cloud_called": False,
        "browser_cdp_or_cloud_used": False,
        "attachments_read": False,
        "pdf_or_full_text_read": False,
        "zotero_key_or_api_used": False,
        "writelab_called": False,
    }


def _evidence_manifest(
    *,
    source_fingerprints: list[str],
    artifact_fingerprints: list[str],
) -> dict[str, Any]:
    return {
        "manifest_id": "paper-rag-faiss-obsidian-local-pilot-evidence-manifest-a1",
        "schema_version": SCHEMA_VERSION,
        "task_id": TASK_ID,
        "producer": "dev-frame-opencode",
        "source_scope": "obsidian_allowlisted_folder_or_files",
        "commands_run": ["aihub paper rag-faiss-obsidian-local-pilot"],
        "source_fingerprints": source_fingerprints,
        "artifact_fingerprints": artifact_fingerprints,
        "raw_sensitive_fields_absent": True,
        "contains_raw_note": False,
        "contains_raw_chunks": False,
        "contains_raw_query": False,
        "contains_raw_paths": False,
        "contains_embedding_vectors": False,
    }


def _collect_markdown_files(
    *,
    vault_root: str | Path,
    allowlist_paths: list[str | Path],
) -> tuple[list[Path], dict[str, Any], list[str]]:
    vault = Path(vault_root).resolve()
    reasons: list[str] = []
    markdown_files: list[Path] = []
    fingerprints: list[str] = []
    outside_count = 0
    missing_count = 0
    whole_vault_requested = False

    if not vault.exists() or not vault.is_dir():
        reasons.append("vault_root_missing")

    for raw_path in allowlist_paths:
        path = Path(raw_path).resolve()
        fingerprints.append(_sha256_text(str(path)))
        if path == vault:
            whole_vault_requested = True
            reasons.append("whole_vault_allowlist_forbidden")
            continue
        if not (path == vault or vault in path.parents):
            outside_count += 1
            reasons.append("allowlist_path_outside_vault")
            continue
        if not path.exists():
            missing_count += 1
            reasons.append("allowlist_path_missing")
            continue
        if path.is_file():
            if path.suffix.lower() != ".md":
                reasons.append("allowlist_file_not_markdown")
                continue
            markdown_files.append(path)
        elif path.is_dir():
            markdown_files.extend(sorted(path.rglob("*.md")))
        else:
            reasons.append("allowlist_path_unsupported")

    unique_files = sorted({path.resolve() for path in markdown_files})
    summary = {
        "vault_present": vault.exists() and vault.is_dir(),
        "allowlist_entry_count": len(allowlist_paths),
        "markdown_file_count": len(unique_files),
        "outside_vault_count": outside_count,
        "missing_allowlist_entry_count": missing_count,
        "whole_vault_allowlist_requested": whole_vault_requested,
        "whole_vault_scanned": False,
        "allowlist_path_fingerprints": fingerprints,
    }
    if not unique_files and "no_markdown_files_found" not in reasons:
        reasons.append("no_markdown_files_found")
    return unique_files, summary, sorted(set(reasons))


def _load_chunks(markdown_files: list[Path]) -> tuple[list[_Chunk], list[str], int]:
    chunks: list[_Chunk] = []
    source_fingerprints: list[str] = []
    total_bytes = 0
    for file_index, path in enumerate(markdown_files):
        raw_bytes = path.read_bytes()
        total_bytes += len(raw_bytes)
        source_fingerprint = _sha256_bytes(raw_bytes)
        source_fingerprints.append(source_fingerprint)
        text = raw_bytes.decode("utf-8")
        for chunk_index, chunk_text in enumerate(_chunk_markdown(text)):
            chunk_fingerprint = _sha256_text(f"{source_fingerprint}:{chunk_index}:{chunk_text}")
            chunks.append(
                _Chunk(
                    chunk_id=f"doc{file_index:04d}-chunk{chunk_index:04d}",
                    source_fingerprint=source_fingerprint,
                    chunk_fingerprint=chunk_fingerprint,
                    text=chunk_text,
                    char_count=len(chunk_text),
                )
            )
    return chunks, source_fingerprints, total_bytes


def _default_embedder(model_name: str) -> Embedder:
    from sentence_transformers import SentenceTransformer

    model = SentenceTransformer(model_name)

    def embed(texts: list[str]) -> np.ndarray:
        return np.asarray(model.encode(texts, convert_to_numpy=True), dtype="float32")

    return embed


def _write_minimized_chunks(path: Path, chunks: list[_Chunk]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for chunk in chunks:
            handle.write(
                json.dumps(
                    {
                        "chunk_id": chunk.chunk_id,
                        "source_fingerprint": chunk.source_fingerprint,
                        "chunk_fingerprint": chunk.chunk_fingerprint,
                        "char_count": chunk.char_count,
                        "raw_text_persisted": False,
                    },
                    sort_keys=True,
                )
                + "\n"
            )


def build_rag_faiss_obsidian_local_pilot_report(
    *,
    vault_root: str | Path,
    allowlist_paths: list[str | Path],
    index_root: str | Path,
    embedding_model: str = DEFAULT_EMBEDDING_MODEL,
    query: str = DEFAULT_QUERY,
    top_k: int = 3,
    install_attempted: bool = True,
    install_performed: bool = True,
    install_command_summary: str = "python -m pip install faiss-cpu sentence-transformers",
    model_download_performed: bool = True,
    embedder: Embedder | None = None,
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Build a local FAISS index and emit minimized pilot evidence."""
    generated = generated_at or _utc_now_text()
    index_dir = Path(index_root).resolve()
    faiss_version = _safe_version("faiss-cpu")
    st_version = _safe_version("sentence-transformers")
    if not faiss_version or not st_version:
        return _blocked_report(
            generated_at=generated,
            status="BLOCKED_DEPENDENCY_MISSING",
            reasons=["faiss_or_sentence_transformers_missing"],
            index_root=index_dir,
            embedding_model=embedding_model,
            install_command_summary=install_command_summary,
            install_attempted=install_attempted,
            install_performed=install_performed,
            model_download_performed=model_download_performed,
            faiss_present=bool(faiss_version),
            sentence_transformers_present=bool(st_version),
        )

    markdown_files, scope_summary, reasons = _collect_markdown_files(
        vault_root=vault_root,
        allowlist_paths=allowlist_paths,
    )
    if reasons:
        return _blocked_report(
            generated_at=generated,
            status="BLOCKED_SCOPE_INVALID",
            reasons=reasons,
            index_root=index_dir,
            embedding_model=embedding_model,
            install_command_summary=install_command_summary,
            install_attempted=install_attempted,
            install_performed=install_performed,
            model_download_performed=model_download_performed,
            source_scope_summary=scope_summary,
        )

    try:
        chunks, source_fingerprints, _total_bytes = _load_chunks(markdown_files)
    except (OSError, UnicodeDecodeError) as exc:
        return _blocked_report(
            generated_at=generated,
            status="BLOCKED_SOURCE_READ_FAILED",
            reasons=[type(exc).__name__],
            index_root=index_dir,
            embedding_model=embedding_model,
            install_command_summary=install_command_summary,
            install_attempted=install_attempted,
            install_performed=install_performed,
            model_download_performed=model_download_performed,
            source_scope_summary=scope_summary,
        )
    if not chunks:
        return _blocked_report(
            generated_at=generated,
            status="BLOCKED_EMPTY_INDEX_INPUT",
            reasons=["no_chunks_after_chunking"],
            index_root=index_dir,
            embedding_model=embedding_model,
            install_command_summary=install_command_summary,
            install_attempted=install_attempted,
            install_performed=install_performed,
            model_download_performed=model_download_performed,
            source_scope_summary=scope_summary,
        )
    if len({chunk.chunk_fingerprint for chunk in chunks}) != len(chunks):
        return _blocked_report(
            generated_at=generated,
            status="BLOCKED_DUPLICATE_CHUNK_FINGERPRINT",
            reasons=["duplicate_chunk_fingerprint"],
            index_root=index_dir,
            embedding_model=embedding_model,
            install_command_summary=install_command_summary,
            install_attempted=install_attempted,
            install_performed=install_performed,
            model_download_performed=model_download_performed,
            source_scope_summary=scope_summary,
        )

    embed = embedder or _default_embedder(embedding_model)
    chunk_embeddings = np.asarray(embed([chunk.text for chunk in chunks]), dtype="float32")
    query_embedding = np.asarray(embed([query]), dtype="float32")
    if chunk_embeddings.ndim != 2 or query_embedding.ndim != 2:
        raise ValueError("embedding output must be 2-dimensional")
    dimension = int(chunk_embeddings.shape[1])

    import faiss

    faiss.normalize_L2(chunk_embeddings)
    faiss.normalize_L2(query_embedding)
    index = faiss.IndexFlatIP(dimension)
    index.add(chunk_embeddings)
    safe_top_k = max(1, min(top_k, len(chunks)))
    _scores, indices = index.search(query_embedding, safe_top_k)
    retrieved_indices = [int(index_value) for index_value in indices[0] if index_value >= 0]
    retrieved = [chunks[index_value].chunk_fingerprint for index_value in retrieved_indices]

    index_dir.mkdir(parents=True, exist_ok=True)
    index_file = index_dir / "index.faiss"
    chunks_file = index_dir / "chunks.jsonl"
    manifest_file = index_dir / "manifest.json"
    faiss.write_index(index, str(index_file))
    _write_minimized_chunks(chunks_file, chunks)
    runtime_manifest = {
        "schema_version": SCHEMA_VERSION,
        "task_id": TASK_ID,
        "document_count": len(markdown_files),
        "chunk_count": len(chunks),
        "embedding_dimension": dimension,
        "source_fingerprints": sorted(set(source_fingerprints)),
        "raw_text_persisted": False,
        "raw_paths_persisted": False,
        "embedding_vectors_persisted_in_manifest": False,
    }
    manifest_file.write_text(
        json.dumps(runtime_manifest, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    artifact_fingerprints = [
        _sha256_file(index_file),
        _sha256_file(chunks_file),
        _sha256_file(manifest_file),
    ]
    return {
        "profile": PROFILE,
        "schema_version": SCHEMA_VERSION,
        "task_id": TASK_ID,
        "project_id": "dev-frame-opencode",
        "workflow_type": "paper",
        "generated_at": generated,
        "pilot_status": "PASS_FAISS_LOCAL_INDEX_SMOKE",
        "validation_kind": "rag_faiss_obsidian_local_index_pilot",
        "source_scope": "obsidian_allowlisted_folder_or_files",
        "human_required": False,
        "reasons": [],
        "dependency_summary": {
            "faiss_present": True,
            "sentence_transformers_present": True,
            "faiss_cpu_version": faiss_version,
            "sentence_transformers_version": st_version,
            "install_attempted": install_attempted,
            "install_performed": install_performed,
            "install_command_fingerprint": _sha256_text(install_command_summary),
            "install_command_summary": install_command_summary,
        },
        "model_summary": {
            "embedding_model_name": embedding_model,
            "embedding_model_fingerprint": _sha256_text(embedding_model),
            "model_load_attempted": True,
            "model_download_performed": model_download_performed,
            "local_cache_used": True,
            "remote_token_used": False,
        },
        "source_scope_summary": scope_summary,
        "index_summary": {
            "index_root_fingerprint": _sha256_text(str(index_dir)),
            "document_count": len(markdown_files),
            "chunk_count": len(chunks),
            "embedding_dimension": dimension,
            "faiss_index_kind": "IndexFlatIP",
            "index_artifact_fingerprint": artifact_fingerprints[0],
            "chunks_manifest_fingerprint": artifact_fingerprints[1],
            "manifest_fingerprint": artifact_fingerprints[2],
        },
        "query_smoke": {
            "query_fingerprint": _sha256_text(query),
            "top_k": safe_top_k,
            "retrieved_count": len(retrieved),
            "retrieved_chunk_fingerprints": retrieved,
        },
        "privacy_boundary": _privacy_boundary(),
        "runtime_boundary": _runtime_boundary(),
        "evidence_manifest": _evidence_manifest(
            source_fingerprints=sorted(set(source_fingerprints)),
            artifact_fingerprints=artifact_fingerprints,
        ),
        "final_acceptance_claimed": False,
        "paper_quality_acceptance": False,
        "production_ready": False,
        "live_ready_claimed": False,
        "rag_ready_claimed": False,
        "whole_vault_ready_claimed": False,
    }
