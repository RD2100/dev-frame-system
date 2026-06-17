"""RuntimeAuthorization request packet for a future paper real pilot.

This module is local-only. It builds a machine-checkable request for human
approval and does not grant or exercise real Zotero, Obsidian, PDF, RAG, or
WriteLab access.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from .paper_real_pilot_gate import AGENT_ACCEPTANCE_RULES_READY

REQUEST_STATUS = "RUNTIME_AUTHORIZATION_REQUIRED"
DECISION_STATUS = "APPROVED_METADATA_ONLY_ZOTERO_PILOT"
REQUESTED_PILOT_STAGE = "zotero_metadata_only"

ZOTERO_METADATA_SENSITIVE_FIELDS = [
    "zotero_attachment_path",
    "user_identifier",
]

HUMAN_DECISION_OPTIONS = [
    "APPROVE_METADATA_ONLY_ZOTERO_PILOT",
    "REQUEST_MORE_REDACTION_DETAIL",
    "REQUEST_NARROWER_SCOPE",
    "REJECT_REAL_PILOT",
]


def _utc_now_text() -> str:
    return datetime.now(timezone.utc).isoformat()


def build_runtime_authorization_request(
    *,
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Build a request packet for a Zotero metadata-only real pilot."""
    created_at = generated_at or _utc_now_text()
    return {
        "profile": "paper_real_pilot_runtime_authorization_request",
        "schema_version": "1.0",
        "request_id": "paper-real-pilot-runtime-authorization-request-a1",
        "task_id": "PAPER_REAL_PILOT_RUNTIME_AUTHORIZATION_REQUEST_A1",
        "project_id": "dev-frame-opencode",
        "workflow_type": "paper",
        "created_at": created_at,
        "request_status": REQUEST_STATUS,
        "requested_pilot_stage": REQUESTED_PILOT_STAGE,
        "requested_sources": ["zotero_metadata"],
        "requested_operations": ["real_zotero_metadata"],
        "requested_repo_paths": ["ai-workflow-hub/docs/paper"],
        "authorization_kind": "human_runtime_authorization",
        "resource_binding": "live_resource",
        "live_resource_access_permitted": False,
        "real_zotero_allowed": False,
        "real_obsidian_allowed": False,
        "real_pdf_allowed": False,
        "real_paper_excerpt_allowed": False,
        "live_writelab_allowed": False,
        "external_runtime_allowed": False,
        "sensitive_fields": ZOTERO_METADATA_SENSITIVE_FIELDS,
        "redaction_policy": {
            "policy_id": "paper-real-pilot-zotero-metadata-redaction-a1",
            "sensitive_fields_blocked_by_default": True,
            "blocked_fields": [
                "zotero_attachment_path",
                "paragraph_text",
                "full_text",
                "pdf_text",
                "private_note_raw",
                "matched_text",
                "text_span",
                "writelab_token",
                "Authorization header",
            ],
            "allowed_output_fields": [
                "citation_key",
                "title",
                "creators",
                "year",
                "doi",
                "url",
                "item_type",
            ],
            "private_full_text_status": "blocked",
        },
        "evidence_manifest_required": True,
        "evidence_manifest_requirements": [
            "runtime_authorization_ref",
            "source_records",
            "retrieval_records",
            "redaction_records",
            "commands_run",
            "tests_run",
            "artifacts_generated",
            "raw_sensitive_fields_absent",
            "contains_real_private_content=false",
            "contains_live_writelab_payload=false",
        ],
        "reviewer_verdict_required": True,
        "reviewer_verdict_options": HUMAN_DECISION_OPTIONS,
        "default_recommended_decision": "APPROVE_METADATA_ONLY_ZOTERO_PILOT",
        "expiration_required": True,
        "revocation_required": True,
        "agent_acceptance_rules": dict(AGENT_ACCEPTANCE_RULES_READY),
        "request_is_authorization": False,
        "real_pilot_ready": False,
        "final_acceptance_claimed": False,
        "non_claims": [
            "runtime_authorization_issued",
            "real_pilot_ready",
            "real_zotero_access_ready",
            "real_obsidian_ready",
            "real_pdf_or_full_text_ready",
            "private_rag_ready",
            "live_writelab_ready",
            "final_governance_acceptance",
        ],
        "blocked_until_human_approval": [
            "live_resource_access_permitted",
            "real_zotero_allowed",
            "preflight_status=pass",
            "revocation_status=active",
            "human_gate_ref",
            "reviewer_verdict_ref",
            "evidence_manifest_ref",
            "expires_at",
        ],
    }


def build_human_runtime_authorization_decision(
    *,
    generated_at: str | None = None,
    authorized_by: str = "user_chat_authorization",
) -> dict[str, Any]:
    """Build a fresh human RuntimeAuthorization decision for metadata-only Zotero."""
    created = datetime.fromisoformat(generated_at) if generated_at else datetime.now(timezone.utc)
    if created.tzinfo is None:
        created = created.replace(tzinfo=timezone.utc)
    expires = created + timedelta(hours=24)
    created_text = created.isoformat()
    expires_text = expires.isoformat()
    authorization_id = "paper-real-pilot-zotero-metadata-auth-a1"
    human_gate_ref = "human-gate:chat-authorization:zotero-metadata-only-a1"
    evidence_manifest_ref = "paper-real-pilot-zotero-metadata-evidence-manifest-a1"
    reviewer_verdict_ref = "reviewer-verdict:metadata-only-zotero-a1"
    runtime_authorization = {
        "authorization_id": authorization_id,
        "task_id": "PAPER_REAL_ZOTERO_METADATA_ONLY_PILOT_A1",
        "project_id": "dev-frame-opencode",
        "workflow_type": "paper",
        "authorized_by": authorized_by,
        "created_at": created_text,
        "expires_at": expires_text,
        "allowed_sources": ["zotero_metadata"],
        "allowed_repo_paths": ["ai-workflow-hub/docs/paper"],
        "allowed_operations": ["real_zotero_metadata"],
        "sensitive_fields": [
            "Authorization header",
            "full_text",
            "matched_text",
            "obsidian_absolute_path",
            "paragraph_text",
            "pdf_text",
            "private_note_raw",
            "text_span",
            "user_identifier",
            "writelab_token",
            "zotero_attachment_path",
        ],
        "redaction_policy_ref": "paper-real-pilot-zotero-metadata-redaction-a1",
        "human_gate_ref": human_gate_ref,
        "evidence_manifest_ref": evidence_manifest_ref,
        "authorization_kind": "human_runtime_authorization",
        "resource_binding": "live_resource",
        "fixture_authorization_reusable_for_real_access": False,
        "live_resource_access_permitted": True,
        "external_runtime_allowed": False,
        "live_writelab_allowed": False,
        "real_zotero_allowed": True,
        "real_obsidian_allowed": False,
        "real_pdf_allowed": False,
        "real_paper_excerpt_allowed": False,
        "preflight_status": "pass",
        "revocation_status": "active",
        "notes": "Human approval for Zotero metadata-only pilot; no attachments, PDF, full text, Obsidian, RAG, excerpts, or WriteLab.",
    }
    return {
        "profile": "paper_real_pilot_human_runtime_authorization_decision",
        "schema_version": "1.0",
        "decision_id": "paper-real-pilot-human-runtime-authorization-decision-a1",
        "task_id": "PAPER_REAL_PILOT_HUMAN_RUNTIME_AUTHORIZATION_DECISION_A1",
        "project_id": "dev-frame-opencode",
        "workflow_type": "paper",
        "created_at": created_text,
        "decision_status": DECISION_STATUS,
        "authorization_granted": True,
        "approved_pilot_stage": REQUESTED_PILOT_STAGE,
        "approved_sources": ["zotero_metadata"],
        "approved_operations": ["real_zotero_metadata"],
        "approved_repo_paths": ["ai-workflow-hub/docs/paper"],
        "runtime_authorization": runtime_authorization,
        "human_gate_ref": human_gate_ref,
        "reviewer_verdict_ref": reviewer_verdict_ref,
        "evidence_manifest_ref": evidence_manifest_ref,
        "expires_at": expires_text,
        "revocation_status": "active",
        "redaction_policy_ref": "paper-real-pilot-zotero-metadata-redaction-a1",
        "agent_acceptance_rules": dict(AGENT_ACCEPTANCE_RULES_READY),
        "real_pilot_execution_started": False,
        "final_acceptance_claimed": False,
        "non_approved_resources": [
            "zotero_attachments",
            "pdf_metadata",
            "pdf_text",
            "paper_full_text",
            "obsidian_vault",
            "private_rag",
            "redacted_paper_excerpt",
            "live_writelab",
            "browser_cdp",
            "cloud",
        ],
    }
