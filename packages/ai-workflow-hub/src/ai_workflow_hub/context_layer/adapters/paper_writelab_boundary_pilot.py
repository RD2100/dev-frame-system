"""Controlled WriteLab boundary pilot for synthetic paper text only."""

from __future__ import annotations

import asyncio
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import httpx

from .paper_real_pilot_gate import validate_runtime_authorization
from .writelab_client import WriteLabLiteClient

PROFILE = "paper_writelab_boundary_pilot_report"
SCHEMA_VERSION = "1.0"
TASK_ID = "PAPER_WRITELAB_SYNTHETIC_LIVE_BOUNDARY_PILOT_A1"
PROJECT_ID = "dev-frame-opencode"
WORKFLOW_TYPE = "paper"
OPERATION = "live_writelab"
SOURCE = "writelab_live"
SYNTHETIC_TEXT = "Synthetic paragraph for WriteLab boundary pilot."


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _utc_now_text() -> str:
    return _utc_now().isoformat()


def _load_authorization(path: Path | None) -> dict[str, Any] | None:
    if path is None:
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    auth = payload.get("runtime_authorization") if isinstance(payload, dict) else None
    return auth if isinstance(auth, dict) else None


def build_writelab_boundary_runtime_authorization_decision(
    *,
    generated_at: str | None = None,
    authorized_by: str = "user_chat_authorization",
) -> dict[str, Any]:
    """Build RuntimeAuthorization for a synthetic WriteLab boundary pilot."""
    created = datetime.fromisoformat(generated_at) if generated_at else _utc_now()
    if created.tzinfo is None:
        created = created.replace(tzinfo=timezone.utc)
    expires = created + timedelta(hours=2)
    created_text = created.isoformat()
    expires_text = expires.isoformat()
    return {
        "profile": "paper_writelab_boundary_runtime_authorization_decision",
        "schema_version": SCHEMA_VERSION,
        "decision_id": "paper-writelab-boundary-human-decision-a1",
        "task_id": TASK_ID,
        "project_id": PROJECT_ID,
        "workflow_type": WORKFLOW_TYPE,
        "created_at": created_text,
        "decision_status": "APPROVED_SYNTHETIC_WRITELAB_BOUNDARY_PILOT",
        "authorization_granted": True,
        "approved_sources": [SOURCE],
        "approved_operations": [OPERATION],
        "approved_repo_paths": ["ai-workflow-hub/docs/paper"],
        "runtime_authorization": {
            "authorization_id": "paper-writelab-boundary-auth-a1",
            "task_id": TASK_ID,
            "project_id": PROJECT_ID,
            "workflow_type": WORKFLOW_TYPE,
            "authorized_by": authorized_by,
            "created_at": created_text,
            "expires_at": expires_text,
            "allowed_sources": [SOURCE],
            "allowed_repo_paths": ["ai-workflow-hub/docs/paper"],
            "allowed_operations": [OPERATION],
            "sensitive_fields": [
                "Authorization header",
                "matched_text",
                "paragraph_text",
                "text_span",
                "writelab_token",
            ],
            "redaction_policy_ref": "paper-writelab-boundary-redaction-a1",
            "human_gate_ref": "human-gate:chat-authorization:writelab-boundary-a1",
            "evidence_manifest_ref": "paper-writelab-boundary-evidence-manifest-a1",
            "authorization_kind": "human_runtime_authorization",
            "resource_binding": "live_resource",
            "fixture_authorization_reusable_for_real_access": False,
            "live_resource_access_permitted": True,
            "external_runtime_allowed": True,
            "live_writelab_allowed": True,
            "real_zotero_allowed": False,
            "real_obsidian_allowed": False,
            "real_pdf_allowed": False,
            "real_paper_excerpt_allowed": False,
            "preflight_status": "pass",
            "revocation_status": "active",
            "data_policy": {
                "paper_sensitive_input": "explicit_allow",
                "allowed_sensitive_fields": ["paragraph_text"],
                "redaction_required": True,
            },
            "notes": "Human approval for synthetic WriteLab boundary pilot only; real paper text remains blocked.",
        },
        "expires_at": expires_text,
        "final_acceptance_claimed": False,
        "real_pilot_execution_started": False,
    }


def _blocked_report(
    *,
    generated_at: str,
    transport_mode: str,
    authorization_result: dict[str, Any],
    reasons: list[str],
) -> dict[str, Any]:
    return {
        "profile": PROFILE,
        "schema_version": SCHEMA_VERSION,
        "task_id": TASK_ID,
        "project_id": PROJECT_ID,
        "workflow_type": WORKFLOW_TYPE,
        "generated_at": generated_at,
        "pilot_status": "BLOCKED",
        "validation_kind": "synthetic_writelab_boundary",
        "transport_mode": transport_mode,
        "human_required": True,
        "authorization_result": authorization_result,
        "reasons": reasons,
        "call_summary": {
            "writelab_called": False,
            "success": False,
            "diagnosis_source": "",
            "fallback_used": False,
            "issue_count": 0,
            "error_category": "authorization_required",
        },
        "privacy_boundary": {
            "synthetic_input_used": True,
            "real_paper_text_sent": False,
            "token_persisted": False,
            "raw_payload_persisted": False,
            "raw_response_persisted": False,
            "matched_text_persisted": False,
            "text_span_persisted": False,
        },
        "final_acceptance_claimed": False,
        "paper_quality_acceptance": False,
        "live_ready_claimed": False,
        "production_ready": False,
        "real_pilot_completed": False,
    }


def _mock_client() -> WriteLabLiteClient:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "expression_report": {
                    "sentence_count": 1,
                    "avg_sentence_length": 7,
                    "abstract_noun_density": 0,
                    "dunhao_density": 0,
                    "template_sentence_count": 0,
                    "normative_expression_count": 0,
                    "ai_like_risk": "low",
                    "risks": [],
                },
                "diagnosis": None,
            },
        )

    def factory(**kwargs: Any) -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=httpx.MockTransport(handler))

    return WriteLabLiteClient(_client_factory=factory)


async def _call_writelab(
    *,
    transport_mode: str,
    runtime_authorization: dict[str, Any],
    base_url: str,
    token: str | None,
) -> Any:
    client = _mock_client() if transport_mode == "mock" else WriteLabLiteClient(base_url=base_url, token=token)
    return await client.analyze_expression(
        text=SYNTHETIC_TEXT,
        runtime_authorization=runtime_authorization,
    )


def build_writelab_boundary_pilot_report(
    *,
    authorization_decision_path: Path | None,
    transport_mode: str = "mock",
    base_url: str = "http://127.0.0.1:8001",
    token_env: str = "WRITELAB_TOKEN",
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Build a minimized synthetic WriteLab boundary pilot report."""
    generated = generated_at or _utc_now_text()
    auth = _load_authorization(authorization_decision_path)
    auth_result = validate_runtime_authorization(
        auth,
        task_id=TASK_ID,
        project_id=PROJECT_ID,
        operation=OPERATION,
        source=SOURCE,
        repo_path="ai-workflow-hub/docs/paper",
    )
    if not auth_result["allowed"]:
        return _blocked_report(
            generated_at=generated,
            transport_mode=transport_mode,
            authorization_result=auth_result,
            reasons=["runtime_authorization_not_valid"],
        )
    if transport_mode not in {"mock", "live"}:
        return _blocked_report(
            generated_at=generated,
            transport_mode=transport_mode,
            authorization_result=auth_result,
            reasons=["invalid_transport_mode"],
        )

    token = os.environ.get(token_env) if transport_mode == "live" else None
    result = asyncio.run(
        _call_writelab(
            transport_mode=transport_mode,
            runtime_authorization=auth or {},
            base_url=base_url,
            token=token,
        )
    )
    status = "PASS_SYNTHETIC_WRITELAB_BOUNDARY" if result.success else "BLOCKED"
    error_category = result.error or result.diagnosis_source or ""
    manifest = {
        "manifest_id": "paper-writelab-boundary-evidence-manifest-a1",
        "schema_version": SCHEMA_VERSION,
        "task_id": TASK_ID,
        "producer": "dev-frame-opencode",
        "source_records": [
            {
                "source_type": "synthetic_paragraph",
                "privacy_level": "synthetic_only",
                "real_paper_text_sent": False,
            }
        ],
        "commands_run": ["aihub paper writelab-boundary-pilot"],
        "raw_sensitive_fields_absent": True,
        "token_persisted": False,
        "raw_payload_persisted": False,
        "raw_response_persisted": False,
        "matched_text_persisted": False,
    }
    return {
        "profile": PROFILE,
        "schema_version": SCHEMA_VERSION,
        "task_id": TASK_ID,
        "project_id": PROJECT_ID,
        "workflow_type": WORKFLOW_TYPE,
        "generated_at": generated,
        "pilot_status": status,
        "validation_kind": "synthetic_writelab_boundary",
        "transport_mode": transport_mode,
        "human_required": not result.success,
        "authorization_result": auth_result,
        "reasons": [] if result.success else [error_category or "writelab_call_not_successful"],
        "call_summary": {
            "writelab_called": result.diagnosis_source != "authorization_required",
            "success": result.success,
            "diagnosis_source": result.diagnosis_source,
            "fallback_used": result.fallback_used,
            "issue_count": len(result.issues),
            "error_category": error_category,
        },
        "privacy_boundary": {
            "synthetic_input_used": True,
            "real_paper_text_sent": False,
            "token_persisted": False,
            "raw_payload_persisted": False,
            "raw_response_persisted": False,
            "matched_text_persisted": False,
            "text_span_persisted": False,
        },
        "evidence_manifest": manifest,
        "final_acceptance_claimed": False,
        "paper_quality_acceptance": False,
        "live_ready_claimed": False,
        "production_ready": False,
        "real_pilot_completed": False,
    }
