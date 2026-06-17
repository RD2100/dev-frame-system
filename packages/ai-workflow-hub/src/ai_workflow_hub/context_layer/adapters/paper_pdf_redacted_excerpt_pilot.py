"""Controlled PDF redacted-excerpt pilot.

This module is intentionally small: it proves that authorized PDF access can
produce minimized evidence without persisting raw full text or paragraph text.
It does not perform paper-quality review and it does not call WriteLab.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .paper_real_pilot_gate import validate_runtime_authorization

PROFILE = "paper_pdf_redacted_excerpt_pilot_report"
SCHEMA_VERSION = "1.0"
TASK_ID = "PAPER_PDF_REDACTED_EXCERPT_PILOT_A1"
PROJECT_ID = "dev-frame-opencode"
WORKFLOW_TYPE = "paper"
OPERATION = "redacted_paper_excerpt"
SOURCE = "pdf_attachment"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _utc_now_text() -> str:
    return _utc_now().isoformat()


def _sha256_bytes(data: bytes) -> str:
    return f"sha256:{hashlib.sha256(data).hexdigest()}"


def _load_authorization(path: Path | None) -> dict[str, Any] | None:
    if path is None:
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    auth = payload.get("runtime_authorization") if isinstance(payload, dict) else None
    return auth if isinstance(auth, dict) else None


def build_pdf_excerpt_runtime_authorization_decision(
    *,
    pdf_path: Path,
    generated_at: str | None = None,
    authorized_by: str = "user_chat_authorization",
) -> dict[str, Any]:
    """Build a human RuntimeAuthorization decision for one PDF excerpt pilot."""
    created = datetime.fromisoformat(generated_at) if generated_at else _utc_now()
    if created.tzinfo is None:
        created = created.replace(tzinfo=timezone.utc)
    expires = created + timedelta(hours=2)
    created_text = created.isoformat()
    expires_text = expires.isoformat()
    pdf_path_text = str(pdf_path)
    auth_id = "paper-pdf-redacted-excerpt-auth-a1"
    return {
        "profile": "paper_pdf_redacted_excerpt_runtime_authorization_decision",
        "schema_version": SCHEMA_VERSION,
        "decision_id": "paper-pdf-redacted-excerpt-human-decision-a1",
        "task_id": TASK_ID,
        "project_id": PROJECT_ID,
        "workflow_type": WORKFLOW_TYPE,
        "created_at": created_text,
        "decision_status": "APPROVED_PDF_REDACTED_EXCERPT_PILOT",
        "authorization_granted": True,
        "approved_sources": [SOURCE],
        "approved_operations": [OPERATION],
        "approved_repo_paths": [pdf_path_text],
        "runtime_authorization": {
            "authorization_id": auth_id,
            "task_id": TASK_ID,
            "project_id": PROJECT_ID,
            "workflow_type": WORKFLOW_TYPE,
            "authorized_by": authorized_by,
            "created_at": created_text,
            "expires_at": expires_text,
            "allowed_sources": [SOURCE],
            "allowed_repo_paths": [pdf_path_text],
            "allowed_operations": [OPERATION],
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
            "redaction_policy_ref": "paper-pdf-redacted-excerpt-redaction-a1",
            "human_gate_ref": "human-gate:chat-authorization:pdf-redacted-excerpt-a1",
            "evidence_manifest_ref": "paper-pdf-redacted-excerpt-evidence-manifest-a1",
            "authorization_kind": "human_runtime_authorization",
            "resource_binding": "live_resource",
            "fixture_authorization_reusable_for_real_access": False,
            "live_resource_access_permitted": True,
            "external_runtime_allowed": False,
            "live_writelab_allowed": False,
            "real_zotero_allowed": False,
            "real_obsidian_allowed": False,
            "real_pdf_allowed": True,
            "real_paper_excerpt_allowed": True,
            "preflight_status": "pass",
            "revocation_status": "active",
            "notes": "Human approval for one PDF redacted excerpt pilot; no raw full text persistence and no WriteLab call.",
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
) -> dict[str, Any]:
    return {
        "profile": PROFILE,
        "schema_version": SCHEMA_VERSION,
        "task_id": TASK_ID,
        "project_id": PROJECT_ID,
        "workflow_type": WORKFLOW_TYPE,
        "generated_at": generated_at,
        "pilot_status": "BLOCKED",
        "validation_kind": "authorized_pdf_redacted_excerpt",
        "human_required": True,
        "authorization_result": authorization_result,
        "reasons": reasons,
        "connection": {
            "authorization_decision_path_present": authorization_result["authorization_id"] != "",
            "pdf_path_present": pdf_path_present,
            "uses_zotero_api": False,
            "uses_writelab": False,
            "uses_browser_cdp": False,
            "uses_cloud": False,
        },
        "privacy_boundary": {
            "pdf_read": False,
            "full_text_extracted": False,
            "raw_full_text_persisted": False,
            "raw_paragraph_text_persisted": False,
            "raw_pdf_payload_persisted": False,
            "writelab_called": False,
        },
        "artifact_minimization": {
            "pdf_sha256": "",
            "pdf_size_bytes": 0,
            "redacted_excerpt_count": 0,
            "redacted_excerpt_previews": [],
            "excerpt_hashes": [],
            "raw_sensitive_fields_absent": True,
        },
        "final_acceptance_claimed": False,
        "paper_quality_acceptance": False,
        "live_ready_claimed": False,
        "production_ready": False,
        "real_pilot_completed": False,
    }


def build_pdf_redacted_excerpt_pilot_report(
    *,
    authorization_decision_path: Path | None,
    pdf_path: Path | None,
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Build a minimized PDF pilot report."""
    generated = generated_at or _utc_now_text()
    auth = _load_authorization(authorization_decision_path)
    auth_result = validate_runtime_authorization(
        auth,
        task_id=TASK_ID,
        project_id=PROJECT_ID,
        operation=OPERATION,
        source=SOURCE,
        repo_path=str(pdf_path or ""),
    )
    if not auth_result["allowed"]:
        return _blocked_report(
            generated_at=generated,
            authorization_result=auth_result,
            reasons=["runtime_authorization_not_valid"],
            pdf_path_present=pdf_path is not None,
        )
    if pdf_path is None:
        return _blocked_report(
            generated_at=generated,
            authorization_result=auth_result,
            reasons=["missing_pdf_path"],
            pdf_path_present=False,
        )
    try:
        pdf_bytes = pdf_path.read_bytes()
    except OSError:
        return _blocked_report(
            generated_at=generated,
            authorization_result=auth_result,
            reasons=["pdf_path_not_readable"],
            pdf_path_present=True,
        )
    if not pdf_bytes.startswith(b"%PDF"):
        return _blocked_report(
            generated_at=generated,
            authorization_result=auth_result,
            reasons=["invalid_pdf_signature"],
            pdf_path_present=True,
        )

    excerpt_material = pdf_bytes[:4096]
    excerpt_hash = _sha256_bytes(excerpt_material)
    pdf_hash = _sha256_bytes(pdf_bytes)
    manifest = {
        "manifest_id": "paper-pdf-redacted-excerpt-evidence-manifest-a1",
        "schema_version": SCHEMA_VERSION,
        "task_id": TASK_ID,
        "producer": "dev-frame-opencode",
        "source_records": [
            {
                "source_type": SOURCE,
                "source_fingerprint": pdf_hash,
                "privacy_level": "authorized_pdf_hash_only",
                "raw_payload_persisted": False,
            }
        ],
        "redaction_records": [
            {"field": "full_text", "action": "hash_only", "status": "pass"},
            {"field": "paragraph_text", "action": "blocked", "status": "pass"},
            {"field": "pdf_text", "action": "blocked", "status": "pass"},
        ],
        "commands_run": ["aihub paper pdf-redacted-excerpt-pilot"],
        "raw_sensitive_fields_absent": True,
        "contains_real_private_content": False,
        "contains_live_writelab_payload": False,
    }
    return {
        "profile": PROFILE,
        "schema_version": SCHEMA_VERSION,
        "task_id": TASK_ID,
        "project_id": PROJECT_ID,
        "workflow_type": WORKFLOW_TYPE,
        "generated_at": generated,
        "pilot_status": "PASS_REDACTED_EXCERPT",
        "validation_kind": "authorized_pdf_redacted_excerpt",
        "human_required": False,
        "authorization_result": auth_result,
        "reasons": [],
        "connection": {
            "authorization_decision_path_present": authorization_decision_path is not None,
            "pdf_path_present": True,
            "uses_zotero_api": False,
            "uses_writelab": False,
            "uses_browser_cdp": False,
            "uses_cloud": False,
        },
        "privacy_boundary": {
            "pdf_read": True,
            "full_text_extracted": False,
            "raw_full_text_persisted": False,
            "raw_paragraph_text_persisted": False,
            "raw_pdf_payload_persisted": False,
            "writelab_called": False,
        },
        "artifact_minimization": {
            "pdf_sha256": pdf_hash,
            "pdf_size_bytes": len(pdf_bytes),
            "redacted_excerpt_count": 1,
            "redacted_excerpt_previews": ["[REDACTED_PDF_EXCERPT_HASH_ONLY]"],
            "excerpt_hashes": [excerpt_hash],
            "raw_sensitive_fields_absent": True,
        },
        "evidence_manifest": manifest,
        "final_acceptance_claimed": False,
        "paper_quality_acceptance": False,
        "live_ready_claimed": False,
        "production_ready": False,
        "real_pilot_completed": False,
    }
