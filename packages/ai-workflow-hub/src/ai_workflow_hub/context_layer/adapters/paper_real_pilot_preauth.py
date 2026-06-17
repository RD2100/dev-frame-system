"""Local-only preauthorization packet for future paper real pilots."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .paper_real_pilot_gate import SENSITIVE_FIELDS

PREAUTH_PACKET_READY = "PREAUTH_PACKET_READY"

PILOT_SCENARIOS = [
    {
        "stage": "P1",
        "name": "zotero_metadata_only_pilot",
        "allowed_sources": ["zotero_metadata"],
        "allowed_operations": ["real_zotero_metadata"],
        "sensitive_fields": ["zotero_attachment_path", "user_identifier"],
        "redaction_required": True,
        "evidence_manifest_required": True,
        "reviewer_verdict_required": True,
        "agent_acceptance_rule_required": True,
        "blocking_conditions": [
            "missing_human_runtime_authorization",
            "zotero_attachment_or_full_text_requested",
            "expired_or_revoked_authorization",
        ],
    },
    {
        "stage": "P2",
        "name": "obsidian_allowlisted_note_pilot",
        "allowed_sources": ["obsidian_allowlisted_note"],
        "allowed_operations": ["real_obsidian_allowlisted_note"],
        "sensitive_fields": ["private_note_raw", "obsidian_absolute_path", "user_identifier"],
        "redaction_required": True,
        "evidence_manifest_required": True,
        "reviewer_verdict_required": True,
        "agent_acceptance_rule_required": True,
        "blocking_conditions": [
            "vault_wide_scan_requested",
            "obsidian_note_promoted_to_verified_source",
            "missing_allowlist",
        ],
    },
    {
        "stage": "P3",
        "name": "rag_retrieval_evidence_pilot",
        "allowed_sources": ["rag_private_source"],
        "allowed_operations": ["private_rag_retrieval"],
        "sensitive_fields": ["paragraph_text", "private_note_raw", "user_identifier"],
        "redaction_required": True,
        "evidence_manifest_required": True,
        "reviewer_verdict_required": True,
        "agent_acceptance_rule_required": True,
        "blocking_conditions": [
            "missing_evidence_manifest",
            "citation_without_verified_source",
            "raw_private_source_in_output",
        ],
    },
    {
        "stage": "P4",
        "name": "redacted_paper_excerpt_pilot",
        "allowed_sources": ["paper_redacted_excerpt"],
        "allowed_operations": ["redacted_paper_excerpt"],
        "sensitive_fields": ["paragraph_text", "full_text", "pdf_text", "user_identifier"],
        "redaction_required": True,
        "evidence_manifest_required": True,
        "reviewer_verdict_required": True,
        "agent_acceptance_rule_required": True,
        "blocking_conditions": [
            "full_text_requested",
            "raw_paragraph_text_persisted",
            "missing_redaction_record",
        ],
    },
    {
        "stage": "P5",
        "name": "live_writelab_pilot",
        "allowed_sources": ["writelab_live"],
        "allowed_operations": ["live_writelab"],
        "sensitive_fields": ["paragraph_text", "matched_text", "text_span", "writelab_token"],
        "redaction_required": True,
        "evidence_manifest_required": True,
        "reviewer_verdict_required": True,
        "agent_acceptance_rule_required": True,
        "blocking_conditions": [
            "missing_dedicated_live_writelab_authorization",
            "token_in_report",
            "matched_text_or_text_span_in_reviewer_pack",
        ],
    },
]

AGENT_ACCEPTANCE_RULE_HANDOFF = [
    {
        "rule_id": "paper-real-pilot-runtime-authorization-required",
        "description": "Private source access requires human RuntimeAuthorization.",
    },
    {
        "rule_id": "paper-real-pilot-evidence-manifest-required",
        "description": "Real pilot evidence requires an EvidenceManifest.",
    },
    {
        "rule_id": "paper-real-pilot-redaction-policy-required",
        "description": "Sensitive fields require a redaction policy.",
    },
    {
        "rule_id": "paper-real-pilot-fixture-auth-cannot-authorize-real-access",
        "description": "Fixture authorization must never authorize live resources.",
    },
    {
        "rule_id": "paper-real-pilot-non-final-local-evidence",
        "description": "Synthetic/offline/local dry-run evidence cannot be final acceptance.",
    },
    {
        "rule_id": "paper-real-pilot-source-level",
        "description": "Obsidian notes are leads; citation claims require VERIFIED_SOURCE.",
    },
    {
        "rule_id": "paper-real-pilot-sensitive-fields-absent",
        "description": "Raw sensitive fields must be absent or redacted.",
    },
]

REVIEWER_VERDICTS = [
    "APPROVED_FOR_METADATA_ONLY_PILOT",
    "APPROVED_FOR_ALLOWLISTED_NOTE_PILOT",
    "APPROVED_FOR_REDACTED_EXCERPT_PILOT",
    "APPROVED_FOR_LIVE_WRITELAB_PILOT",
    "HUMAN_REQUIRED",
    "BLOCKED",
    "REJECTED",
]


def build_human_authorization_request_template() -> dict[str, Any]:
    """Return a blank future human authorization template with no real data."""
    return {
        "authorization_id": "<to-be-issued-by-human-gate>",
        "authorization_kind": "human_runtime_authorization",
        "resource_binding": "live_resource",
        "task_id": "<future-real-pilot-task-id>",
        "workflow_type": "paper",
        "authorized_by": "<human-reviewer>",
        "human_gate_ref": "<required-human-gate-ref>",
        "reviewer_verdict_ref": "<required-reviewer-verdict-ref>",
        "expires_at": "<iso8601-expiry>",
        "allowed_sources": [],
        "allowed_repo_paths": [],
        "allowed_operations": [],
        "redaction_policy_ref": "<required-redaction-policy-ref>",
        "evidence_manifest_ref": "<required-evidence-manifest-ref>",
        "privacy_scope": "metadata_only_or_redacted_excerpt_only",
        "revocation_status": "active",
        "fixture_authorization_reusable_for_real_access": False,
        "live_resource_access_permitted": False,
    }


def build_reviewer_verdict_template() -> dict[str, Any]:
    """Return reviewer verdict format for future pilot approval."""
    return {
        "verdict_id": "<reviewer-verdict-id>",
        "reviewer": "<reviewer-id>",
        "reviewed_packet_id": "<preauth-packet-id>",
        "verdict": "HUMAN_REQUIRED",
        "allowed_verdicts": REVIEWER_VERDICTS,
        "approved_sources": [],
        "approved_operations": [],
        "approved_repo_paths": [],
        "redaction_policy_ref": "<required-redaction-policy-ref>",
        "evidence_manifest_ref": "<required-evidence-manifest-ref>",
        "expires_at": "<iso8601-expiry>",
        "limitations": [
            "No full-text access unless explicitly approved.",
            "No live WriteLab unless dedicated verdict approves it.",
        ],
    }


def build_preauth_packet(*, generated_at: str | None = None) -> dict[str, Any]:
    """Build a machine-checkable local preauthorization packet."""
    created_at = generated_at or datetime.now(timezone.utc).isoformat()
    return {
        "packet_id": "paper-real-pilot-preauth-a1",
        "task_id": "PAPER_REAL_PILOT_PREAUTH_PACKET_A1",
        "project_id": "dev-frame-opencode",
        "workflow_type": "paper",
        "created_at": created_at,
        "requested_pilot_stage": "preauth_only",
        "requested_sources": [
            "zotero_metadata",
            "obsidian_allowlisted_note",
            "rag_private_source",
            "paper_redacted_excerpt",
            "writelab_live",
        ],
        "requested_operations": [
            "real_zotero_metadata",
            "real_obsidian_allowlisted_note",
            "private_rag_retrieval",
            "redacted_paper_excerpt",
            "live_writelab",
        ],
        "requested_repo_paths": ["ai-workflow-hub/docs/paper"],
        "sensitive_fields": sorted(SENSITIVE_FIELDS),
        "redaction_policy_ref": "paper-real-pilot-redaction-policy-required",
        "evidence_manifest_required": True,
        "reviewer_verdict_required": True,
        "human_runtime_authorization_required": True,
        "agent_acceptance_rules_required": True,
        "fixture_authorization_reusable_for_real_access": False,
        "live_resource_access_permitted": False,
        "external_runtime_allowed": False,
        "known_blockers": [
            "agent_acceptance_rules_not_yet_synced",
            "human_runtime_authorization_not_yet_issued",
            "reviewer_verdict_not_yet_approved",
        ],
        "next_required_approval": "human_runtime_authorization",
        "human_runtime_authorization_request_template": (
            build_human_authorization_request_template()
        ),
        "pilot_scenario_matrix": PILOT_SCENARIOS,
        "agent_acceptance_rule_handoff": AGENT_ACCEPTANCE_RULE_HANDOFF,
        "reviewer_verdict_template": build_reviewer_verdict_template(),
        "preauth_status": PREAUTH_PACKET_READY,
        "non_claims": [
            "real_pilot_ready",
            "real_zotero_ready",
            "real_obsidian_ready",
            "real_pdf_full_text_ready",
            "live_writelab_ready",
            "final_governance_acceptance",
        ],
    }
