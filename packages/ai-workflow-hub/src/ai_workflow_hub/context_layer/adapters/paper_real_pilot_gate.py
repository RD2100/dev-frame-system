"""Fail-closed contracts for paper real-pilot authorization.

This module is intentionally local and side-effect free. It does not read
Zotero, Obsidian, PDFs, WriteLab, network services, or private paper content.
It only validates whether a future real-pilot request has the structured
authorization, redaction policy, and evidence manifest needed before such
access could be attempted.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import PurePosixPath
from typing import Any

VERIFIED_SOURCE = "VERIFIED_SOURCE"
USER_NOTE_LEAD = "USER_NOTE_LEAD"
NEEDS_VERIFICATION = "NEEDS_VERIFICATION"
GENERAL_MODEL_SUGGESTION = "GENERAL_MODEL_SUGGESTION"
SOURCE_NOT_AVAILABLE = "SOURCE_NOT_AVAILABLE"

SOURCE_LEVELS = {
    VERIFIED_SOURCE,
    USER_NOTE_LEAD,
    NEEDS_VERIFICATION,
    GENERAL_MODEL_SUGGESTION,
    SOURCE_NOT_AVAILABLE,
}

SENSITIVE_FIELDS = {
    "paragraph_text",
    "full_text",
    "private_note_raw",
    "pdf_text",
    "matched_text",
    "text_span",
    "writelab_token",
    "Authorization header",
    "zotero_attachment_path",
    "obsidian_absolute_path",
    "user_identifier",
}

REAL_PILOT_FLAGS = {
    "external_runtime_allowed",
    "live_writelab_allowed",
    "real_zotero_allowed",
    "real_obsidian_allowed",
    "real_pdf_allowed",
    "real_paper_excerpt_allowed",
}

AUTHORIZATION_KINDS = {"fixture", "human_runtime_authorization"}
RESOURCE_BINDINGS = {"fixture_only", "live_resource"}

REAL_PILOT_OPERATIONS = {
    "real_zotero_metadata",
    "real_obsidian_allowlisted_note",
    "private_rag_retrieval",
    "real_pdf_metadata",
    "redacted_paper_excerpt",
    "live_writelab",
}

BLOCKED = "BLOCKED"
PASS = "PASS"
HUMAN_REQUIRED = "HUMAN_REQUIRED"
NEEDS_SOURCE_VERIFICATION = "NEEDS_VERIFICATION"
PASS_LOCAL_DRY_RUN = "PASS_LOCAL_DRY_RUN"

AGENT_ACCEPTANCE_RULES_READY = {
    "module": "agent-acceptance",
    "task_spec": "AGENT_ACCEPTANCE_PAPER_REAL_PILOT_RULES_A1",
    "commit": "fcb5ea837f99614e233622e3cd8e91c8f05327ff",
    "verdict": "accepted_with_limitations",
    "rules_ready": True,
    "rework_required": False,
    "parent_pin_required": False,
    "runtime_authorization_required_for_local_rules": False,
    "real_resource_authorization_granted": False,
    "evidence_artifact": "evidence-agent-acceptance-paper-real-pilot-rules-a1.zip",
}


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _utc_now_text() -> str:
    return _utc_now().isoformat()


def _parse_datetime(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _as_nonempty_str(value: Any) -> str:
    return value if isinstance(value, str) and value.strip() else ""


def _path_within_allowlist(path: str, allowed_paths: list[str]) -> bool:
    if not path:
        return True
    normalized = str(PurePosixPath(path.replace("\\", "/")))
    for allowed in allowed_paths:
        allowed_norm = str(PurePosixPath(str(allowed).replace("\\", "/")))
        if normalized == allowed_norm or normalized.startswith(f"{allowed_norm.rstrip('/')}/"):
            return True
    return False


def _result(
    *,
    allowed: bool,
    status: str,
    reasons: list[str],
    authorization_id: str = "",
) -> dict[str, Any]:
    return {
        "allowed": allowed,
        "status": status,
        "human_required": status == HUMAN_REQUIRED or not allowed,
        "authorization_id": authorization_id,
        "reasons": reasons,
    }


def _stable_manifest_item(value: Any) -> str:
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"))
    except TypeError:
        return repr(value)


def _has_duplicate_items(values: list[Any]) -> bool:
    seen: set[str] = set()
    for value in values:
        stable_value = _stable_manifest_item(value)
        if stable_value in seen:
            return True
        seen.add(stable_value)
    return False


def validate_runtime_authorization(
    authorization: dict[str, Any] | None,
    *,
    task_id: str = "",
    project_id: str = "",
    workflow_type: str = "paper",
    operation: str = "",
    source: str = "",
    repo_path: str = "",
    now: datetime | None = None,
) -> dict[str, Any]:
    """Validate paper real-pilot RuntimeAuthorization.

    Missing, expired, revoked, mismatched, or incomplete authorization fails
    closed. The returned dict is a reviewer-friendly decision, not a runtime
    side effect.
    """
    if not isinstance(authorization, dict):
        return _result(allowed=False, status=HUMAN_REQUIRED, reasons=["missing_authorization"])

    reasons: list[str] = []
    auth_id = _as_nonempty_str(authorization.get("authorization_id"))
    current_time = now or _utc_now()

    for field in (
        "authorization_id",
        "task_id",
        "authorized_by",
        "created_at",
        "expires_at",
        "redaction_policy_ref",
        "human_gate_ref",
        "evidence_manifest_ref",
    ):
        if not _as_nonempty_str(authorization.get(field)):
            reasons.append(f"missing_{field}")

    if authorization.get("preflight_status") != "pass":
        reasons.append("preflight_status_not_pass")
    if authorization.get("revocation_status") != "active":
        reasons.append("authorization_not_active")

    expires_at = _parse_datetime(authorization.get("expires_at"))
    if expires_at is None:
        reasons.append("invalid_expires_at")
    elif expires_at <= current_time:
        reasons.append("authorization_expired")

    if task_id and authorization.get("task_id") != task_id:
        reasons.append("task_id_mismatch")
    if project_id and authorization.get("project_id") not in (None, "", project_id):
        reasons.append("project_id_mismatch")
    if workflow_type and authorization.get("workflow_type", "paper") != workflow_type:
        reasons.append("workflow_type_mismatch")

    allowed_sources = authorization.get("allowed_sources")
    if not isinstance(allowed_sources, list) or not allowed_sources:
        reasons.append("missing_allowed_sources")
    else:
        if _has_duplicate_items(allowed_sources):
            reasons.append("duplicate_allowed_sources")
        if source and source not in allowed_sources:
            reasons.append("source_not_allowed")

    allowed_repo_paths = authorization.get("allowed_repo_paths")
    if not isinstance(allowed_repo_paths, list) or not allowed_repo_paths:
        reasons.append("missing_allowed_repo_paths")
    else:
        if _has_duplicate_items(allowed_repo_paths):
            reasons.append("duplicate_allowed_repo_paths")
        if not _path_within_allowlist(repo_path, allowed_repo_paths):
            reasons.append("repo_path_not_allowed")

    allowed_operations = authorization.get("allowed_operations")
    if not isinstance(allowed_operations, list) or not allowed_operations:
        reasons.append("missing_allowed_operations")
    else:
        if _has_duplicate_items(allowed_operations):
            reasons.append("duplicate_allowed_operations")
        if operation and operation not in allowed_operations:
            reasons.append("operation_not_allowed")

    sensitive_fields = authorization.get("sensitive_fields")
    if not isinstance(sensitive_fields, list):
        reasons.append("missing_sensitive_fields")
    else:
        if _has_duplicate_items(sensitive_fields):
            reasons.append("duplicate_sensitive_fields")
        if unknown := sorted(set(sensitive_fields) - SENSITIVE_FIELDS):
            reasons.append(f"unknown_sensitive_fields:{','.join(unknown)}")

    for flag in REAL_PILOT_FLAGS:
        if flag not in authorization:
            reasons.append(f"missing_{flag}")
        elif not isinstance(authorization.get(flag), bool):
            reasons.append(f"invalid_{flag}")

    if authorization.get("authorization_kind") not in AUTHORIZATION_KINDS:
        reasons.append("missing_or_invalid_authorization_kind")
    if authorization.get("resource_binding") not in RESOURCE_BINDINGS:
        reasons.append("missing_or_invalid_resource_binding")
    if authorization.get("fixture_authorization_reusable_for_real_access") is not False:
        reasons.append("fixture_authorization_reuse_not_blocked")
    if not isinstance(authorization.get("live_resource_access_permitted"), bool):
        reasons.append("missing_or_invalid_live_resource_access_permitted")

    return _result(
        allowed=not reasons,
        status=PASS if not reasons else HUMAN_REQUIRED,
        reasons=reasons,
        authorization_id=auth_id,
    )


def validate_redaction_policy(policy: dict[str, Any] | None) -> dict[str, Any]:
    """Validate that sensitive paper fields are blocked by default."""
    if not isinstance(policy, dict):
        return _result(allowed=False, status=HUMAN_REQUIRED, reasons=["missing_redaction_policy"])

    reasons: list[str] = []
    if not _as_nonempty_str(policy.get("policy_id")):
        reasons.append("missing_policy_id")
    if policy.get("sensitive_fields_blocked_by_default") is not True:
        reasons.append("sensitive_fields_not_blocked_by_default")
    if policy.get("redacted_excerpt_requires_runtime_authorization") is not True:
        reasons.append("redacted_excerpt_not_authorization_gated")
    if policy.get("private_full_text_status") != "human_required":
        reasons.append("private_full_text_not_human_required")

    fields = policy.get("sensitive_fields")
    if not isinstance(fields, list):
        reasons.append("missing_sensitive_fields")
    elif missing := sorted(SENSITIVE_FIELDS - set(fields)):
        reasons.append(f"missing_sensitive_fields:{','.join(missing)}")

    return _result(allowed=not reasons, status=PASS if not reasons else HUMAN_REQUIRED, reasons=reasons)


def validate_evidence_manifest(manifest: dict[str, Any] | None) -> dict[str, Any]:
    """Validate a paper real-pilot EvidenceManifest safety envelope."""
    if not isinstance(manifest, dict):
        return _result(allowed=False, status=HUMAN_REQUIRED, reasons=["missing_evidence_manifest"])

    reasons: list[str] = []
    for field in (
        "manifest_id",
        "task_id",
        "runtime_authorization_ref",
    ):
        if not _as_nonempty_str(manifest.get(field)):
            reasons.append(f"missing_{field}")

    for list_field in (
        "source_records",
        "retrieval_records",
        "redaction_records",
        "commands_run",
        "tests_run",
        "artifacts_generated",
    ):
        values = manifest.get(list_field)
        if not isinstance(values, list):
            reasons.append(f"missing_{list_field}")
            continue
        if _has_duplicate_items(values):
            reasons.append(f"duplicate_{list_field}")

    if manifest.get("raw_sensitive_fields_absent") is not True:
        reasons.append("raw_sensitive_fields_present")
    if manifest.get("contains_real_private_content") is True:
        reasons.append("contains_real_private_content")
    if manifest.get("contains_live_writelab_payload") is True:
        reasons.append("contains_live_writelab_payload")
    if manifest.get("reviewer_required") is not True:
        reasons.append("reviewer_not_required")

    for index, record in enumerate(manifest.get("source_records") or []):
        if not isinstance(record, dict):
            reasons.append(f"source_records[{index}]_invalid")
            continue
        source_level = record.get("source_level")
        if source_level not in SOURCE_LEVELS:
            reasons.append(f"source_records[{index}]_invalid_source_level")
        if record.get("source_type") == "obsidian_note" and source_level == VERIFIED_SOURCE:
            reasons.append(f"source_records[{index}]_obsidian_note_cannot_be_verified_source")

    return _result(allowed=not reasons, status=PASS if not reasons else HUMAN_REQUIRED, reasons=reasons)


def evaluate_real_pilot_request(request: dict[str, Any]) -> dict[str, Any]:
    """Evaluate whether a requested real-pilot operation can proceed locally."""
    reasons: list[str] = []
    auth_input = request.get("runtime_authorization")
    manifest = request.get("evidence_manifest")
    policy = request.get("redaction_policy")
    auth = auth_input if isinstance(auth_input, dict) else {}
    task_id = str(request.get("task_id", ""))
    project_id = str(request.get("project_id", ""))
    repo_path = str(request.get("repo_path", ""))
    requested_now = request.get("now")
    evaluation_time = requested_now if isinstance(requested_now, datetime) else None

    auth_result = validate_runtime_authorization(
        auth,
        task_id=task_id,
        project_id=project_id,
        operation=str(request.get("operation", "")),
        source=str(request.get("source", "")),
        repo_path=repo_path,
        now=evaluation_time,
    )
    policy_result = validate_redaction_policy(policy if isinstance(policy, dict) else None)
    manifest_result = validate_evidence_manifest(manifest if isinstance(manifest, dict) else None)

    if request.get("final_acceptance_requested") is True:
        reasons.append("synthetic_offline_candidate_cannot_be_final_acceptance")

    source_verification_reasons: list[str] = []
    source_level = request.get("citation_source_level")
    if source_level and source_level != VERIFIED_SOURCE:
        source_verification_reasons.append(f"citation_source_not_verified:{source_level}")

    if request.get("obsidian_note_as_verified_source") is True:
        reasons.append("obsidian_note_cannot_be_verified_source")

    real_resource_requested = any(
        request.get(key) is True
        for key in (
            "real_zotero_requested",
            "real_obsidian_requested",
            "real_pdf_requested",
            "real_paper_excerpt_requested",
            "live_writelab_requested",
            "rag_private_source_requested",
        )
    )
    if real_resource_requested:
        if auth.get("authorization_kind") != "human_runtime_authorization":
            reasons.append("real_resource_requires_human_runtime_authorization")
        if auth.get("resource_binding") != "live_resource":
            reasons.append("real_resource_requires_live_resource_binding")
        if auth.get("fixture_authorization_reusable_for_real_access") is not False:
            reasons.append("fixture_authorization_reuse_not_blocked")
        if auth.get("live_resource_access_permitted") is not True:
            reasons.append("live_resource_access_not_permitted")

    requested_operations = {
        "real_zotero_requested": "real_zotero_allowed",
        "real_obsidian_requested": "real_obsidian_allowed",
        "real_pdf_requested": "real_pdf_allowed",
        "real_paper_excerpt_requested": "real_paper_excerpt_allowed",
    }
    for request_key, auth_flag in requested_operations.items():
        if request.get(request_key) is True and not (
            auth_result["allowed"] and auth.get(auth_flag) is True
        ):
            reasons.append(f"{request_key}_without_authorization")

    if request.get("live_writelab_requested") is True:
        if not auth_result["allowed"]:
            reasons.append("live_writelab_without_authorization")
        elif auth.get("external_runtime_allowed") is not True or auth.get("live_writelab_allowed") is not True:
            reasons.append("live_writelab_without_dedicated_authorization")

    if request.get("rag_private_source_requested") is True:
        if not auth_result["allowed"]:
            reasons.append("private_rag_without_authorization")
        if not manifest_result["allowed"]:
            reasons.append("private_rag_without_evidence_manifest")

    if reasons:
        return _result(
            allowed=False,
            status=BLOCKED,
            reasons=reasons + source_verification_reasons,
        )

    boundary_failures = [
        f"authorization:{reason}" for reason in auth_result["reasons"]
    ] + [
        f"redaction_policy:{reason}" for reason in policy_result["reasons"]
    ] + [
        f"evidence_manifest:{reason}" for reason in manifest_result["reasons"]
    ]
    if boundary_failures:
        return _result(allowed=False, status=HUMAN_REQUIRED, reasons=boundary_failures)

    if source_verification_reasons:
        return _result(
            allowed=False,
            status=NEEDS_SOURCE_VERIFICATION,
            reasons=source_verification_reasons,
        )

    return _result(
        allowed=True,
        status=PASS,
        reasons=[],
        authorization_id=str(auth.get("authorization_id", "")),
    )


def build_fixture_runtime_authorization(**overrides: Any) -> dict[str, Any]:
    """Build a synthetic metadata-only RuntimeAuthorization fixture."""
    authorization = {
        "authorization_id": "fixture-auth-real-pilot-dry-run-a1",
        "task_id": "PAPER_REAL_PILOT_LOCAL_DRY_RUN_WIRING_A1",
        "project_id": "dev-frame-opencode",
        "workflow_type": "paper",
        "authorized_by": "fixture-module-gpt-reviewer",
        "created_at": "2026-06-15T00:00:00+00:00",
        "expires_at": "2099-06-16T00:00:00+00:00",
        "allowed_sources": ["zotero_metadata", "rag_private_source"],
        "allowed_repo_paths": ["ai-workflow-hub/docs/paper"],
        "allowed_operations": ["real_zotero_metadata", "private_rag_retrieval"],
        "sensitive_fields": sorted(SENSITIVE_FIELDS),
        "redaction_policy_ref": "fixture-redaction-policy-a1",
        "human_gate_ref": "fixture-human-gate-a1",
        "evidence_manifest_ref": "fixture-evidence-manifest-a1",
        "authorization_kind": "fixture",
        "resource_binding": "fixture_only",
        "fixture_authorization_reusable_for_real_access": False,
        "live_resource_access_permitted": False,
        "external_runtime_allowed": False,
        "live_writelab_allowed": False,
        "real_zotero_allowed": True,
        "real_obsidian_allowed": False,
        "real_pdf_allowed": False,
        "real_paper_excerpt_allowed": False,
        "preflight_status": "pass",
        "revocation_status": "active",
        "notes": "Fixture authorization for local dry-run only; no real resource access.",
    }
    authorization.update(overrides)
    return authorization


def build_fixture_redaction_policy(**overrides: Any) -> dict[str, Any]:
    """Build a redaction policy fixture that blocks sensitive fields by default."""
    policy = {
        "policy_id": "fixture-redaction-policy-a1",
        "sensitive_fields_blocked_by_default": True,
        "sensitive_fields": sorted(SENSITIVE_FIELDS),
        "redacted_excerpt_requires_runtime_authorization": True,
        "private_full_text_status": "human_required",
    }
    policy.update(overrides)
    return policy


def build_fixture_evidence_manifest(**overrides: Any) -> dict[str, Any]:
    """Build a synthetic EvidenceManifest fixture for local dry-run review."""
    manifest = {
        "manifest_id": "fixture-evidence-manifest-a1",
        "task_id": "PAPER_REAL_PILOT_LOCAL_DRY_RUN_WIRING_A1",
        "runtime_authorization_ref": "fixture-auth-real-pilot-dry-run-a1",
        "source_records": [
            {
                "source_id": "fixture:zotero:item:ABC123",
                "source_type": "zotero_metadata",
                "source_level": VERIFIED_SOURCE,
                "privacy_level": "metadata_only",
                "path_or_citation_key": "fixture2026metadata",
                "retrieved_at": "2026-06-15T00:00:00+00:00",
                "stale_status": "fresh",
                "hash_or_metadata_fingerprint": "sha256:fixture-metadata",
            }
        ],
        "retrieval_records": [
            {
                "retrieval_id": "fixture-retrieval-a1",
                "source_id": "fixture:zotero:item:ABC123",
                "source_level": VERIFIED_SOURCE,
                "privacy_level": "metadata_only",
            }
        ],
        "redaction_records": [
            {"field": "paragraph_text", "action": "blocked", "status": "pass"},
            {"field": "full_text", "action": "blocked", "status": "pass"},
            {"field": "private_note_raw", "action": "blocked", "status": "pass"},
            {"field": "pdf_text", "action": "blocked", "status": "pass"},
            {"field": "matched_text", "action": "blocked", "status": "pass"},
            {"field": "text_span", "action": "blocked", "status": "pass"},
            {"field": "writelab_token", "action": "blocked", "status": "pass"},
        ],
        "commands_run": ["aihub paper real-pilot-dry-run"],
        "tests_run": ["tests/test_paper_real_pilot_local_dry_run.py"],
        "artifacts_generated": ["paper-real-pilot-local-dry-run.json"],
        "raw_sensitive_fields_absent": True,
        "contains_real_private_content": False,
        "contains_live_writelab_payload": False,
        "reviewer_required": True,
    }
    manifest.update(overrides)
    return manifest


def _fixture_request_for_scenario(scenario: str) -> dict[str, Any]:
    authorization = build_fixture_runtime_authorization()
    redaction_policy = build_fixture_redaction_policy()
    evidence_manifest = build_fixture_evidence_manifest()
    request: dict[str, Any] = {
        "task_id": "PAPER_REAL_PILOT_LOCAL_DRY_RUN_WIRING_A1",
        "project_id": "dev-frame-opencode",
        "operation": "real_zotero_metadata",
        "source": "zotero_metadata",
        "repo_path": "ai-workflow-hub/docs/paper/PAPER_REAL_PILOT_AUTHORIZATION_GATE.md",
        "runtime_authorization": authorization,
        "redaction_policy": redaction_policy,
        "evidence_manifest": evidence_manifest,
        "fixture_metadata_simulation": True,
    }

    if scenario == "missing-authorization":
        request["runtime_authorization"] = None
        request["real_zotero_requested"] = True
    elif scenario == "live-writelab-blocked":
        request.update(
            {
                "operation": "live_writelab",
                "source": "writelab_live",
                "live_writelab_requested": True,
                "runtime_authorization": build_fixture_runtime_authorization(
                    allowed_sources=["writelab_live"],
                    allowed_operations=["live_writelab"],
                    real_zotero_allowed=False,
                ),
            }
        )
    elif scenario == "private-rag-blocked-without-manifest":
        request.update(
            {
                "operation": "private_rag_retrieval",
                "source": "rag_private_source",
                "rag_private_source_requested": True,
                "evidence_manifest": None,
            }
        )
    elif scenario == "unverified-citation":
        request.update({"citation_source_level": USER_NOTE_LEAD})
    elif scenario == "final-acceptance-blocked":
        request.update({"final_acceptance_requested": True})
    elif scenario != "metadata-only-pass":
        raise ValueError(f"unknown local dry-run scenario: {scenario}")

    return request


def build_local_dry_run_report(
    *,
    scenario: str = "metadata-only-pass",
    generated_at: str | None = None,
    agent_acceptance_rules: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a local-only real-pilot dry-run report."""
    request = _fixture_request_for_scenario(scenario)
    evaluation_time = _parse_datetime(generated_at) if generated_at else None
    if evaluation_time is not None:
        request["now"] = evaluation_time
    gate_result = evaluate_real_pilot_request(request)
    dry_run_status = PASS_LOCAL_DRY_RUN if gate_result["status"] == PASS else gate_result["status"]
    rules = dict(agent_acceptance_rules or AGENT_ACCEPTANCE_RULES_READY)
    return {
        "profile": "paper_real_pilot_local_dry_run",
        "schema_version": "1.0",
        "validation_mode": "local_fixture_only",
        "scenario": scenario,
        "generated_at": generated_at or _utc_now_text(),
        "dry_run_status": dry_run_status,
        "gate_result": gate_result,
        "runtime_authorization": request.get("runtime_authorization"),
        "redaction_policy": request.get("redaction_policy"),
        "evidence_manifest": request.get("evidence_manifest"),
        "privacy_boundary": {
            "real_zotero_accessed": False,
            "real_obsidian_accessed": False,
            "real_pdf_accessed": False,
            "real_paper_content_read": False,
            "live_writelab_called": False,
            "raw_sensitive_fields_absent": True,
            "contains_live_writelab_payload": False,
        },
        "final_acceptance_boundary": {
            "final_acceptance_claimed": False,
            "local_dry_run_is_final_acceptance": False,
            "real_pilot_ready": False,
        },
        "agent_acceptance_rules": rules,
        "agent_acceptance_rule_required_before_real_pilot": True,
        "schema_interface_dependency": {
            "local_contract_ready": True,
            "agent_acceptance_rules_synced_for_local_dry_run": rules.get("rules_ready") is True,
            "cross_module_sync_required_before_real_pilot": True,
            "cross_module_blocker_for_local_dry_run": False,
            "real_resource_authorization_required": True,
        },
        "known_gaps": [
            "No real Zotero private library access.",
            "No real Obsidian vault scan.",
            "No real PDF or paper full text read.",
            "No live WriteLab call.",
            "Local fixture authorization cannot be used for real resources.",
            "Agent-acceptance rules are local governance evidence, not RuntimeAuthorization.",
        ],
    }
