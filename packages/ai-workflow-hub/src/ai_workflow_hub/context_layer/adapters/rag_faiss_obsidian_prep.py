"""FAISS Obsidian allowlist prep report for paper RAG.

This adapter performs dependency and scope preflight only. It does not build a
FAISS index, download embedding models, read note bodies, or scan a vault.
"""

from __future__ import annotations

import hashlib
import importlib.util
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PROFILE = "paper_rag_faiss_obsidian_prep_report"
SCHEMA_VERSION = "1.0"
TASK_ID = "OPENCODE_RAG_FAISS_OBSIDIAN_ALLOWLISTED_FOLDER_PREP_A1"
DEFAULT_EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"


DependencyProbe = Callable[[], dict[str, bool]]


def _utc_now_text() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256_text(text: str) -> str:
    return f"sha256:{hashlib.sha256(text.encode('utf-8')).hexdigest()}"


def probe_faiss_dependencies() -> dict[str, bool]:
    """Return import availability without importing heavy runtime modules."""
    return {
        "faiss_present": importlib.util.find_spec("faiss") is not None,
        "sentence_transformers_present": (
            importlib.util.find_spec("sentence_transformers") is not None
        ),
    }


def _pilot_status(*, faiss_present: bool, sentence_transformers_present: bool) -> str:
    if faiss_present and sentence_transformers_present:
        return "READY_FOR_FAISS_PILOT_PREAUTH"
    if not faiss_present and not sentence_transformers_present:
        return "DEPENDENCY_INSTALL_REQUIRED"
    if not faiss_present:
        return "FAISS_DEPENDENCY_MISSING"
    return "EMBEDDING_DEPENDENCY_MISSING"


def _dependency_reasons(
    *, faiss_present: bool, sentence_transformers_present: bool
) -> list[str]:
    reasons: list[str] = []
    if not faiss_present:
        reasons.append("faiss_dependency_missing")
    if not sentence_transformers_present:
        reasons.append("sentence_transformers_dependency_missing")
    return reasons


def _path_kind(path: Path) -> str:
    if path.is_file():
        return "file"
    if path.is_dir():
        return "folder"
    return "missing"


def _scope_summary(
    *,
    vault_root: str | Path | None,
    allowlist_paths: list[str | Path],
) -> dict[str, Any]:
    vault = Path(vault_root).resolve() if vault_root is not None else None
    vault_present = bool(vault and vault.exists() and vault.is_dir())
    file_count = 0
    folder_count = 0
    missing_count = 0
    outside_count = 0
    whole_vault_requested = False
    fingerprints: list[str] = []

    for raw_path in allowlist_paths:
        path = Path(raw_path).resolve()
        fingerprints.append(_sha256_text(str(path)))
        kind = _path_kind(path)
        if kind == "file":
            file_count += 1
        elif kind == "folder":
            folder_count += 1
        else:
            missing_count += 1
        if vault is not None:
            if path == vault:
                whole_vault_requested = True
            if not (path == vault or vault in path.parents):
                outside_count += 1

    scope_valid = (
        len(allowlist_paths) > 0
        and vault_present
        and missing_count == 0
        and outside_count == 0
        and not whole_vault_requested
    )
    return {
        "vault_root_present": vault_present,
        "allowlist_entry_count": len(allowlist_paths),
        "allowlisted_file_count": file_count,
        "allowlisted_folder_count": folder_count,
        "missing_allowlist_entry_count": missing_count,
        "outside_vault_entry_count": outside_count,
        "whole_vault_allowlist_requested": whole_vault_requested,
        "whole_vault_allowed": False,
        "scope_valid": scope_valid,
        "allowlist_path_fingerprints": fingerprints,
    }


def build_rag_faiss_obsidian_prep_report(
    *,
    vault_root: str | Path | None,
    allowlist_paths: list[str | Path] | None,
    index_root: str | Path,
    embedding_model: str = DEFAULT_EMBEDDING_MODEL,
    query: str | None = None,
    dependency_probe: DependencyProbe = probe_faiss_dependencies,
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Build a minimized FAISS prep report without runtime index execution."""
    generated = generated_at or _utc_now_text()
    allowlist = allowlist_paths or []
    dependencies = dependency_probe()
    faiss_present = bool(dependencies.get("faiss_present", False))
    st_present = bool(dependencies.get("sentence_transformers_present", False))
    status = _pilot_status(
        faiss_present=faiss_present,
        sentence_transformers_present=st_present,
    )
    reasons = _dependency_reasons(
        faiss_present=faiss_present,
        sentence_transformers_present=st_present,
    )
    scope = _scope_summary(vault_root=vault_root, allowlist_paths=allowlist)
    if not scope["scope_valid"]:
        reasons.append("allowlist_scope_requires_review")

    index_fingerprint = _sha256_text(str(Path(index_root).resolve()))
    query_fingerprint = _sha256_text(query) if query else ""
    human_required = status != "READY_FOR_FAISS_PILOT_PREAUTH" or not scope["scope_valid"]
    manifest = {
        "manifest_id": "paper-rag-faiss-obsidian-prep-evidence-manifest-a1",
        "schema_version": SCHEMA_VERSION,
        "task_id": TASK_ID,
        "producer": "dev-frame-opencode",
        "source_scope": "obsidian_allowlisted_folder_or_files",
        "commands_run": ["aihub paper rag-faiss-obsidian-prep"],
        "raw_sensitive_fields_absent": True,
        "contains_raw_note": False,
        "contains_raw_chunks": False,
        "contains_raw_query": False,
        "contains_raw_paths": False,
        "contains_embedding_vectors": False,
        "planned_artifact_fingerprints": [index_fingerprint],
    }
    return {
        "profile": PROFILE,
        "schema_version": SCHEMA_VERSION,
        "task_id": TASK_ID,
        "project_id": "dev-frame-opencode",
        "workflow_type": "paper",
        "generated_at": generated,
        "pilot_status": status,
        "validation_kind": "rag_faiss_obsidian_prep",
        "source_scope": "obsidian_allowlisted_folder_or_files",
        "human_required": human_required,
        "reasons": reasons,
        "dependencies": {
            "faiss_present": faiss_present,
            "sentence_transformers_present": st_present,
            "package_install_performed": False,
            "model_download_performed": False,
        },
        "allowlist_scope": scope,
        "planned_artifacts": {
            "index_root_fingerprint": index_fingerprint,
            "index_file_name": "index.faiss",
            "chunks_file_name": "chunks.jsonl",
            "manifest_file_name": "manifest.json",
            "raw_vectors_in_evidence": False,
            "raw_chunks_in_evidence": False,
            "raw_paths_in_evidence": False,
        },
        "embedding_plan": {
            "embedding_model_name": embedding_model,
            "embedding_model_fingerprint": _sha256_text(embedding_model),
            "model_download_required_for_future_pilot": True,
            "model_download_performed": False,
        },
        "query_plan": {
            "query_provided": query is not None,
            "query_fingerprint": query_fingerprint,
            "raw_query_persisted": False,
        },
        "privacy_boundary": {
            "raw_note_persisted": False,
            "raw_chunks_persisted": False,
            "raw_query_persisted": False,
            "raw_paths_persisted": False,
            "embedding_vectors_persisted_in_evidence": False,
        },
        "runtime_boundary": {
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
        },
        "install_preflight": {
            "packages_needed": [
                package
                for package, present in [
                    ("faiss-cpu", faiss_present),
                    ("sentence-transformers", st_present),
                ]
                if not present
            ],
            "install_command_suggestion": (
                "python -m pip install faiss-cpu sentence-transformers"
            ),
            "model_download_risk": (
                "sentence-transformers may download model weights during future use"
            ),
            "explicit_user_runtime_authorization_required": True,
            "package_install_performed": False,
            "model_download_performed": False,
        },
        "evidence_manifest": manifest,
        "final_acceptance_claimed": False,
        "paper_quality_acceptance": False,
        "production_ready": False,
        "live_ready_claimed": False,
        "rag_ready_claimed": False,
        "whole_vault_ready_claimed": False,
    }
