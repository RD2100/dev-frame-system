"""Authorized PDF excerpt to local WriteLab pilot.

This module is intentionally narrow. It may read one explicitly authorized PDF
and send one short excerpt to a local WriteLab endpoint, but the generated
report only persists hashes, counts, booleans, and status metadata.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

from .paper_real_pilot_gate import validate_runtime_authorization
from .writelab_client import WriteLabLiteClient, WriteLabCallResult

PROFILE = "paper_pdf_writelab_live_pilot_report"
SCHEMA_VERSION = "1.0"
TASK_ID = "PAPER_PDF_REDACTED_EXCERPT_WRITELAB_LIVE_PILOT_A1"
PROJECT_ID = "dev-frame-opencode"
WORKFLOW_TYPE = "paper"
PDF_SOURCE = "pdf_attachment"
WRITELAB_SOURCE = "writelab_live"
PDF_OPERATION = "redacted_paper_excerpt"
WRITELAB_OPERATION = "live_writelab"
DEFAULT_BASE_URL = "http://127.0.0.1:8001"
DEFAULT_MAX_EXCERPT_CHARS = 600

Extractor = Callable[[Path, int], str]


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _utc_now_text() -> str:
    return _utc_now().isoformat()


def _sha256_text(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()


def _sha256_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _load_authorization(path: Path | None) -> dict[str, Any] | None:
    if path is None:
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    auth = payload.get("runtime_authorization") if isinstance(payload, dict) else None
    return auth if isinstance(auth, dict) else None


def build_pdf_writelab_runtime_authorization_decision(
    *,
    pdf_path: Path,
    generated_at: str | None = None,
    authorized_by: str = "user_chat_authorization",
    base_url: str = DEFAULT_BASE_URL,
) -> dict[str, Any]:
    """Build a scoped RuntimeAuthorization for one PDF excerpt WriteLab smoke."""
    created = datetime.fromisoformat(generated_at) if generated_at else _utc_now()
    if created.tzinfo is None:
        created = created.replace(tzinfo=timezone.utc)
    expires = created + timedelta(hours=2)
    created_text = created.isoformat()
    expires_text = expires.isoformat()
    return {
        "profile": "paper_pdf_writelab_live_runtime_authorization_decision",
        "schema_version": SCHEMA_VERSION,
        "decision_id": "paper-pdf-writelab-live-human-decision-a1",
        "task_id": TASK_ID,
        "project_id": PROJECT_ID,
        "workflow_type": WORKFLOW_TYPE,
        "created_at": created_text,
        "decision_status": "APPROVED_PDF_REDACTED_EXCERPT_WRITELAB_LIVE_PILOT",
        "authorization_granted": True,
        "approved_sources": [PDF_SOURCE, WRITELAB_SOURCE],
        "approved_operations": [PDF_OPERATION, WRITELAB_OPERATION],
        "approved_repo_paths": [str(pdf_path), "ai-workflow-hub/docs/paper"],
        "runtime_authorization": {
            "authorization_id": "paper-pdf-writelab-live-auth-a1",
            "task_id": TASK_ID,
            "project_id": PROJECT_ID,
            "workflow_type": WORKFLOW_TYPE,
            "authorized_by": authorized_by,
            "created_at": created_text,
            "expires_at": expires_text,
            "allowed_sources": [PDF_SOURCE, WRITELAB_SOURCE],
            "allowed_repo_paths": [str(pdf_path), "ai-workflow-hub/docs/paper"],
            "allowed_operations": [PDF_OPERATION, WRITELAB_OPERATION],
            "sensitive_fields": [
                "Authorization header",
                "full_text",
                "matched_text",
                "paragraph_text",
                "pdf_text",
                "text_span",
                "writelab_token",
                "zotero_attachment_path",
            ],
            "redaction_policy_ref": "paper-pdf-writelab-live-redaction-a1",
            "human_gate_ref": "human-gate:chat-authorization:pdf-writelab-live-a1",
            "evidence_manifest_ref": "paper-pdf-writelab-live-evidence-manifest-a1",
            "authorization_kind": "human_runtime_authorization",
            "resource_binding": "live_resource",
            "fixture_authorization_reusable_for_real_access": False,
            "live_resource_access_permitted": True,
            "external_runtime_allowed": True,
            "live_writelab_allowed": True,
            "real_zotero_allowed": False,
            "real_obsidian_allowed": False,
            "real_pdf_allowed": True,
            "real_paper_excerpt_allowed": True,
            "preflight_status": "pass",
            "revocation_status": "active",
            "data_policy": {
                "paper_sensitive_input": "explicit_allow",
                "allowed_sensitive_fields": ["paragraph_text"],
                "redaction_required": True,
            },
            "resource_endpoint": base_url,
            "notes": (
                "Human approval for one short PDF excerpt to local WriteLab. "
                "Reports must not persist raw excerpt text or raw WriteLab payloads."
            ),
        },
        "expires_at": expires_text,
        "final_acceptance_claimed": False,
        "real_pilot_execution_started": False,
    }


def _blocked_report(
    *,
    generated_at: str,
    authorization_result: dict[str, Any],
    reasons: list[str],
    pdf_path_present: bool,
    base_url: str,
) -> dict[str, Any]:
    return {
        "profile": PROFILE,
        "schema_version": SCHEMA_VERSION,
        "task_id": TASK_ID,
        "project_id": PROJECT_ID,
        "workflow_type": WORKFLOW_TYPE,
        "generated_at": generated_at,
        "pilot_status": "BLOCKED",
        "validation_kind": "authorized_pdf_excerpt_to_local_writelab",
        "human_required": True,
        "authorization_result": authorization_result,
        "reasons": reasons,
        "connection": {
            "authorization_decision_path_present": authorization_result["authorization_id"] != "",
            "pdf_path_present": pdf_path_present,
            "writelab_base_url": base_url,
            "uses_zotero_api": False,
            "uses_writelab": False,
            "uses_browser_cdp": False,
            "uses_cloud": False,
        },
        "privacy_boundary": {
            "pdf_read": False,
            "full_text_extracted": False,
            "redacted_excerpt_sent_to_writelab": False,
            "raw_full_text_persisted": False,
            "raw_excerpt_persisted": False,
            "raw_payload_persisted": False,
            "raw_response_persisted": False,
            "matched_text_persisted": False,
            "text_span_persisted": False,
            "token_persisted": False,
        },
        "artifact_minimization": {
            "pdf_sha256": "",
            "pdf_size_bytes": 0,
            "excerpt_char_count": 0,
            "excerpt_hash": "",
            "issue_count": 0,
            "diagnosis_source": "",
            "fallback_used": False,
            "raw_sensitive_fields_absent": True,
        },
        "final_acceptance_claimed": False,
        "paper_quality_acceptance": False,
        "live_ready_claimed": False,
        "production_ready": False,
        "real_pilot_completed": False,
    }


def _normalize_excerpt(text: str, max_chars: int) -> str:
    normalized = re.sub(r"\s+", " ", text).strip()
    return normalized[:max_chars].strip()


def _extract_pdf_excerpt(pdf_path: Path, max_chars: int) -> str:
    try:
        from PyPDF2 import PdfReader
    except ImportError as exc:  # pragma: no cover - depends on environment
        raise RuntimeError("pdf_text_extractor_unavailable") from exc

    try:
        reader = PdfReader(str(pdf_path))
        fragments: list[str] = []
        for page in reader.pages[:3]:
            page_text = page.extract_text() or ""
            if page_text:
                fragments.append(page_text)
            candidate = _normalize_excerpt(" ".join(fragments), max_chars)
            if len(candidate) >= min(max_chars, 120):
                return candidate
        return _normalize_excerpt(" ".join(fragments), max_chars)
    except Exception as exc:  # pragma: no cover - exercised by CLI smoke failures
        raise RuntimeError("pdf_text_extraction_failed") from exc


async def _call_writelab(
    *,
    excerpt: str,
    runtime_authorization: dict[str, Any],
    base_url: str,
    token: str | None,
) -> WriteLabCallResult:
    client = WriteLabLiteClient(base_url=base_url, token=token)
    return await client.analyze_expression(
        text=excerpt,
        chapter="authorized_pdf_excerpt",
        section="redacted_excerpt_smoke",
        paragraph_index=0,
        runtime_authorization=runtime_authorization,
    )


def _authorization_allowed(
    auth: dict[str, Any] | None,
    *,
    pdf_path: Path,
) -> dict[str, Any]:
    pdf_result = validate_runtime_authorization(
        auth,
        task_id=TASK_ID,
        project_id=PROJECT_ID,
        operation=PDF_OPERATION,
        source=PDF_SOURCE,
        repo_path=str(pdf_path),
    )
    if not pdf_result["allowed"]:
        return pdf_result
    return validate_runtime_authorization(
        auth,
        task_id=TASK_ID,
        project_id=PROJECT_ID,
        operation=WRITELAB_OPERATION,
        source=WRITELAB_SOURCE,
        repo_path="ai-workflow-hub/docs/paper",
    )


def build_pdf_writelab_live_pilot_report(
    *,
    authorization_decision_path: Path | None,
    pdf_path: Path | None,
    base_url: str = DEFAULT_BASE_URL,
    token_env: str = "WRITELAB_TOKEN",
    max_excerpt_chars: int = DEFAULT_MAX_EXCERPT_CHARS,
    generated_at: str | None = None,
    extractor: Extractor | None = None,
) -> dict[str, Any]:
    """Build a minimized report for one PDF excerpt sent to local WriteLab."""
    generated = generated_at or _utc_now_text()
    auth = _load_authorization(authorization_decision_path)
    if pdf_path is None:
        auth_result = validate_runtime_authorization(auth, task_id=TASK_ID, project_id=PROJECT_ID)
        return _blocked_report(
            generated_at=generated,
            authorization_result=auth_result,
            reasons=["missing_pdf_path"],
            pdf_path_present=False,
            base_url=base_url,
        )

    auth_result = _authorization_allowed(auth, pdf_path=pdf_path)
    if not auth_result["allowed"]:
        return _blocked_report(
            generated_at=generated,
            authorization_result=auth_result,
            reasons=["runtime_authorization_not_valid"],
            pdf_path_present=True,
            base_url=base_url,
        )
    try:
        pdf_bytes = pdf_path.read_bytes()
    except OSError:
        return _blocked_report(
            generated_at=generated,
            authorization_result=auth_result,
            reasons=["pdf_path_not_readable"],
            pdf_path_present=True,
            base_url=base_url,
        )
    if not pdf_bytes.startswith(b"%PDF"):
        return _blocked_report(
            generated_at=generated,
            authorization_result=auth_result,
            reasons=["invalid_pdf_signature"],
            pdf_path_present=True,
            base_url=base_url,
        )

    try:
        excerpt = (extractor or _extract_pdf_excerpt)(pdf_path, max_excerpt_chars)
    except RuntimeError as exc:
        return _blocked_report(
            generated_at=generated,
            authorization_result=auth_result,
            reasons=[str(exc)],
            pdf_path_present=True,
            base_url=base_url,
        )
    if not excerpt:
        return _blocked_report(
            generated_at=generated,
            authorization_result=auth_result,
            reasons=["empty_pdf_excerpt"],
            pdf_path_present=True,
            base_url=base_url,
        )

    token = os.environ.get(token_env)
    result = asyncio.run(
        _call_writelab(
            excerpt=excerpt,
            runtime_authorization=auth or {},
            base_url=base_url,
            token=token,
        )
    )
    pdf_hash = _sha256_bytes(pdf_bytes)
    excerpt_hash = _sha256_text(excerpt)
    status = "PASS_PDF_EXCERPT_WRITELAB_LIVE" if result.success else "BLOCKED"
    error_category = result.error or result.diagnosis_source or ""
    manifest = {
        "manifest_id": "paper-pdf-writelab-live-evidence-manifest-a1",
        "schema_version": SCHEMA_VERSION,
        "task_id": TASK_ID,
        "producer": "dev-frame-opencode",
        "source_records": [
            {
                "source_type": PDF_SOURCE,
                "source_fingerprint": pdf_hash,
                "privacy_level": "authorized_redacted_excerpt_hash_only",
                "raw_payload_persisted": False,
            },
            {
                "source_type": WRITELAB_SOURCE,
                "source_fingerprint": excerpt_hash,
                "privacy_level": "authorized_excerpt_hash_only",
                "raw_payload_persisted": False,
            },
        ],
        "commands_run": ["aihub paper pdf-writelab-live-pilot"],
        "raw_sensitive_fields_absent": True,
        "contains_real_private_content": False,
        "contains_live_writelab_payload": False,
        "reviewer_required": True,
    }
    return {
        "profile": PROFILE,
        "schema_version": SCHEMA_VERSION,
        "task_id": TASK_ID,
        "project_id": PROJECT_ID,
        "workflow_type": WORKFLOW_TYPE,
        "generated_at": generated,
        "pilot_status": status,
        "validation_kind": "authorized_pdf_excerpt_to_local_writelab",
        "human_required": not result.success,
        "authorization_result": auth_result,
        "reasons": [] if result.success else [error_category or "writelab_call_not_successful"],
        "connection": {
            "authorization_decision_path_present": authorization_decision_path is not None,
            "pdf_path_present": True,
            "writelab_base_url": base_url,
            "uses_zotero_api": False,
            "uses_writelab": result.diagnosis_source != "authorization_required",
            "uses_browser_cdp": False,
            "uses_cloud": False,
        },
        "privacy_boundary": {
            "pdf_read": True,
            "full_text_extracted": False,
            "redacted_excerpt_sent_to_writelab": result.diagnosis_source != "authorization_required",
            "raw_full_text_persisted": False,
            "raw_excerpt_persisted": False,
            "raw_payload_persisted": False,
            "raw_response_persisted": False,
            "matched_text_persisted": False,
            "text_span_persisted": False,
            "token_persisted": False,
        },
        "artifact_minimization": {
            "pdf_sha256": pdf_hash,
            "pdf_size_bytes": len(pdf_bytes),
            "excerpt_char_count": len(excerpt),
            "excerpt_hash": excerpt_hash,
            "issue_count": len(result.issues),
            "diagnosis_source": result.diagnosis_source,
            "fallback_used": result.fallback_used,
            "raw_sensitive_fields_absent": True,
        },
        "evidence_manifest": manifest,
        "final_acceptance_claimed": False,
        "paper_quality_acceptance": False,
        "live_ready_claimed": False,
        "production_ready": False,
        "real_pilot_completed": False,
    }
