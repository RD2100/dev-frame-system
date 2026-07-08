"""Phase 3: client governance projection boundary.

Clients (RDCode, T3, shells) may request, display, and propose. They must not
finalize completion, adoption, or policy. The projection is read-only.

This module combines Phase 1A work_item projection and Phase 2 document
authority into a single read-only client view, and validates that client
actions do not cross the write boundary.

Boundary rules:
  - Allowed (read/propose class): view, request_review, propose, escalate, gather_evidence
  - Forbidden (authority write class): finalize_completion, adopt_document,
    record_decision, set_status, promote_document, and any unknown action
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .review_governance_validator import derive_projection, validate_packet
from .document_authority import derive_authority, validate_promotion


# Closed set of actions a client is permitted to perform.
# None of these create authority — they only read or propose.
CLIENT_ALLOWED_ACTIONS: tuple[str, ...] = (
    "view",
    "request_review",
    "propose",
    "escalate",
    "gather_evidence",
)

# Closed set of actions that would create authority if a client could perform them.
# These are the write-boundary violations.
CLIENT_FORBIDDEN_ACTIONS: tuple[str, ...] = (
    "finalize_completion",
    "adopt_document",
    "record_decision",
    "set_status",
    "promote_document",
)


class ClientActionError(Exception):
    """Raised when a client action crosses the governance write boundary."""


@dataclass
class ClientActionResult:
    ok: bool
    action: str
    error: str = ""

    def __bool__(self) -> bool:
        return self.ok


def project_for_client(payload: dict) -> dict:
    """Project governance state into a read-only client view.

    Combines Phase 1A work_item projection (computed_status, decision_summary)
    and Phase 2 document authority (authority_state per document) into a single
    read-only view. The projection never invents authority — it is a derivation
    from packet facts.

    Clients consume this projection to display state. They cannot mutate
    authority through it.
    """
    kernel = payload.get("kernel") or {}
    documents_section = payload.get("documents") or {}

    # Validate kernel facts before projecting — invalid packets must not be
    # projected as authoritative/completed to clients.
    kernel_validation = validate_packet(kernel)
    source_errors: list[str] = list(kernel_validation.errors)

    # Validate document section if it carries documents
    doc_validation = None
    if documents_section.get("documents"):
        doc_validation = validate_promotion(documents_section)
        source_errors.extend(doc_validation.errors)

    source_valid = len(source_errors) == 0

    # Missing kernel (no work_item) cannot be projected as ready — downgrade.
    if not kernel.get("work_item"):
        derived = {
            "work_item_id": "",
            "computed_status": "missing_context",
            "blocked_reason": "no work_item in kernel",
            "evidence_summary": {"total_evidence_count": 0, "supporting_count": 0,
                                 "rejecting_count": 0, "inconclusive_count": 0},
            "decision_summary": {"review_outcome": "", "gate_outcome": "",
                                 "latest_decision_id": ""},
        }
        computed_status = "missing_context"
    else:
        derived = derive_projection(kernel)
        computed_status = derived["computed_status"]
        # If kernel is invalid, downgrade computed_status so clients never see
        # a trusted status from unverified facts — regardless of derived status.
        if not source_valid:
            computed_status = "invalid"

    # Filter allowed_actions to the client-safe subset
    client_actions = _client_safe_actions(computed_status)

    # Phase 2: derive document authority (read-only).
    # When document validation failed, do NOT surface trusted authoritative
    # projections — invalid facts must not appear authoritative to clients.
    if doc_validation is not None and not doc_validation.valid:
        docs = documents_section.get("documents") or []
        doc_authority = {
            "document_count": len(docs),
            "authoritative_count": 0,
            "documents": [
                {
                    "document_id": doc.get("id", ""),
                    "authority_state": "invalid",
                    "is_adopted": False,
                    "has_evidence": False,
                    "adopting_decision_id": doc.get("adopting_decision_id", ""),
                    "decision_outcome": "",
                }
                for doc in docs
            ],
        }
    else:
        doc_authority = derive_authority(documents_section)

    return {
        "read_only": True,
        "source_valid": source_valid,
        "source_errors": source_errors,
        "work_item_id": derived["work_item_id"],
        "work_item_status": (kernel.get("work_item") or {}).get("status", ""),
        "computed_status": computed_status,
        "blocked_reason": derived["blocked_reason"],
        "evidence_summary": derived["evidence_summary"],
        "decision_summary": derived["decision_summary"],
        "document_authority": doc_authority,
        "client_allowed_actions": client_actions,
    }


def validate_client_action(payload: dict, action: str,
                            raise_on_violation: bool = False) -> ClientActionResult:
    """Validate that a client action does not cross the governance write boundary.

    Returns ClientActionResult(ok=True) for allowed actions.
    Returns ClientActionResult(ok=False) for forbidden or unknown actions.
    When raise_on_violation=True, raises ClientActionError instead of returning ok=False.
    """
    if action in CLIENT_FORBIDDEN_ACTIONS:
        err = (
            f"client action {action!r} is forbidden: it would create authority "
            f"(finalize/adopt/decide/policy). Clients may only request, display, propose."
        )
        if raise_on_violation:
            raise ClientActionError(err)
        return ClientActionResult(ok=False, action=action, error=err)

    if action in CLIENT_ALLOWED_ACTIONS:
        return ClientActionResult(ok=True, action=action)

    # Unknown action — closed set, default to forbidden
    err = (
        f"client action {action!r} is not in the allowed set "
        f"{CLIENT_ALLOWED_ACTIONS}; unknown actions are forbidden by default"
    )
    if raise_on_violation:
        raise ClientActionError(err)
    return ClientActionResult(ok=False, action=action, error=err)


def _client_safe_actions(computed_status: str) -> list[str]:
    """Map computed_status to the client-safe subset of allowed actions.

    Never includes authority-write actions regardless of status.
    """
    status_to_actions: dict[str, list[str]] = {
        "completed": ["view"],
        "blocked": ["view", "escalate"],
        "insufficient_evidence": ["view", "escalate", "gather_evidence"],
        "reviewing": ["view", "request_review"],
        "ready": ["view", "propose", "request_review"],
        "missing_context": ["view"],
        "invalid": ["view"],
    }
    return status_to_actions.get(computed_status, ["view"])
