"""P2-2: policy and human escalation validator.

Per design-coverage-gap-remediation-plan.md:257-272:

  - a worker, browser, dashboard, model score, or external review cannot grant
    itself authority;
  - human-required states name the exact decision requested.

Policy rules (governance-rules-spec.md:260-281):
  POL-001: Confidence is not authority
  POL-002: High-power actions require explicit authority
  POL-003: Self-promotion is blocked by default
  POL-004: Human escalation must be visible
"""
from __future__ import annotations

from dataclasses import dataclass, field

# Entities that may NOT grant authority to themselves.
# Per POL-003: "An agent, coordinator, model route, or learning loop may not
# promote its own authority or default behavior without independent decision."
NON_AUTHORITY_SOURCES: tuple[str, ...] = (
    "worker",
    "browser",
    "dashboard",
    "model_score",
    "external_review",
    "evaluator",
    "learning_loop",
)

# High-power actions that require explicit authority (POL-002).
HIGH_POWER_ACTIONS: tuple[str, ...] = (
    "change_release_state",
    "change_default_rules",
    "change_project_memory",
    "change_writeback_behavior",
    "change_security_posture",
    "change_document_authority",
    "promote_authority",
    "adopt_rule",
)

# Valid policy decision outcomes.
VALID_POLICY_OUTCOMES: tuple[str, ...] = (
    "granted",
    "denied",
    "deferred",
    "escalated",
)

# Decider types that are considered authorized to grant policy decisions.
AUTHORIZED_DECIDER_TYPES: tuple[str, ...] = (
    "human",
    "policy_runtime",
)

# Policy decisions that need a decider: only "granted" creates authority.
GRANT_EQUIVALENTS: tuple[str, ...] = ("granted",)


@dataclass
class ValidationResult:
    valid: bool
    errors: list[str] = field(default_factory=list)

    def __bool__(self) -> bool:
        return self.valid


# ---------------------------------------------------------------------------
# Shared helpers — validate and derive use the same functions to prevent
# projection divergence (same pattern as P1-2, P1-4, P2-1).
# ---------------------------------------------------------------------------


def _is_valid_policy_entry(
    entry: dict,
    collect_errors: bool = False,
) -> tuple[bool, list[str]]:
    """Base shape check for a policy decision entry.

    True only when:
      - id, project_id, action, outcome, requested_by all non-empty
      - action is in HIGH_POWER_ACTIONS
      - outcome is in VALID_POLICY_OUTCOMES
      - if granted: decider_principal_id non-empty, decider_type authorized
      - requested_by == granted_to with non-authority source → self-promotion
    """
    errors: list[str] = []
    pid = entry.get("id", "")
    prefix = f"policy[{pid or '<missing>'}]"

    for field in ("id", "project_id", "action", "outcome", "requested_by"):
        if not entry.get(field):
            if collect_errors:
                errors.append(f"{prefix}: {field} is required")
            else:
                return False, errors

    action = entry.get("action", "")
    if action not in HIGH_POWER_ACTIONS:
        if collect_errors:
            errors.append(
                f"{prefix}: action={action!r} is not a high-power action; "
                f"must be one of {HIGH_POWER_ACTIONS}"
            )
        else:
            return False, errors

    outcome = entry.get("outcome", "")
    if outcome not in VALID_POLICY_OUTCOMES:
        if collect_errors:
            errors.append(
                f"{prefix}: outcome={outcome!r} not in {VALID_POLICY_OUTCOMES}"
            )
        else:
            return False, errors

    requested_by = entry.get("requested_by", "")
    granted_to = entry.get("granted_to", "")

    if outcome in GRANT_EQUIVALENTS:
        if not granted_to:
            if collect_errors:
                errors.append(
                    f"{prefix}: outcome='granted' requires granted_to"
                )
            else:
                return False, errors
        decider_principal_id = entry.get("decider_principal_id", "")
        decider_type = entry.get("decider_type", "")
        if not decider_principal_id:
            if collect_errors:
                errors.append(
                    f"{prefix}: outcome='granted' requires decider_principal_id"
                )
            else:
                return False, errors
        if decider_type not in AUTHORIZED_DECIDER_TYPES:
            if collect_errors:
                errors.append(
                    f"{prefix}: decider_type={decider_type!r} not authorized; "
                    f"must be one of {AUTHORIZED_DECIDER_TYPES} to grant authority"
                )
            else:
                return False, errors

        if (
            requested_by == granted_to
            and requested_by in NON_AUTHORITY_SOURCES
        ):
            if collect_errors:
                errors.append(
                    f"{prefix}: self-promotion blocked: {requested_by!r} cannot "
                    f"grant authority to itself (POL-003)"
                )
            else:
                return False, errors

    return True, errors


def _is_valid_escalation_entry(
    entry: dict,
    work_item_ids: set,
    collect_errors: bool = False,
) -> tuple[bool, list[str]]:
    """Base shape check for a human escalation entry.

    True only when:
      - id, project_id, work_item_id, decision_requested, why_required,
        consequence_if_declined, context_snapshot_artifact_id all non-empty
      - work_item_id resolves to a declared work item
    """
    errors: list[str] = []
    eid = entry.get("id", "")
    prefix = f"escalation[{eid or '<missing>'}]"

    for field in (
        "id", "project_id", "work_item_id", "decision_requested",
        "why_required", "consequence_if_declined",
        "context_snapshot_artifact_id",
    ):
        if not entry.get(field):
            if collect_errors:
                errors.append(f"{prefix}: {field} is required")
            else:
                return False, errors

    work_item_id = entry.get("work_item_id", "")
    if work_item_id and work_item_id not in work_item_ids:
        if collect_errors:
            errors.append(
                f"{prefix}: work_item_id={work_item_id!r} does not resolve "
                f"to a declared work item"
            )
        else:
            return False, errors

    return True, errors


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def validate_policy_escalation(payload: dict) -> ValidationResult:
    """Validate policy decisions and human escalations.

    Enforces:
      - Policy entries have valid shape and outcome
      - Self-promotion by non-authority sources is blocked (POL-003)
      - Granted outcomes require authorized decider (POL-002)
      - Escalation entries have required fields and resolve work items
    """
    errors: list[str] = []

    policy_decisions: list[dict] = payload.get("policy_decisions") or []
    escalations: list[dict] = payload.get("escalations") or []
    work_items: list[dict] = payload.get("work_items") or []
    work_item_ids = {wi.get("id") for wi in work_items if wi.get("id")}

    for entry in policy_decisions:
        _, entry_errors = _is_valid_policy_entry(entry, collect_errors=True)
        errors.extend(entry_errors)

    for entry in escalations:
        _, entry_errors = _is_valid_escalation_entry(
            entry, work_item_ids, collect_errors=True,
        )
        errors.extend(entry_errors)

    return ValidationResult(valid=len(errors) == 0, errors=errors)


def derive_policy_escalation(payload: dict) -> dict:
    """Read-only projection of policy decisions and human escalations.

    Does NOT invent authority. Returns the count of granted/denied/deferred/
    escalated decisions, self-promotion blocks, and pending human decisions.
    """
    policy_decisions: list[dict] = payload.get("policy_decisions") or []
    escalations: list[dict] = payload.get("escalations") or []
    work_items: list[dict] = payload.get("work_items") or []
    work_item_ids = {wi.get("id") for wi in work_items if wi.get("id")}

    granted = 0
    denied = 0
    deferred = 0
    escalated_count = 0
    self_promotion_blocked = 0

    for entry in policy_decisions:
        base_ok, _ = _is_valid_policy_entry(entry, collect_errors=False)

        # Count self-promotion when outcome=granted + non-authority self-grant
        # (self-promotion is one of the reasons an entry can be invalid).
        requested_by = entry.get("requested_by", "")
        granted_to = entry.get("granted_to", "")
        outcome = entry.get("outcome", "")
        if (
            outcome == "granted"
            and requested_by
            and requested_by == granted_to
            and requested_by in NON_AUTHORITY_SOURCES
        ):
            self_promotion_blocked += 1

        if not base_ok:
            continue

        if outcome == "granted":
            granted += 1
        elif outcome == "denied":
            denied += 1
        elif outcome == "deferred":
            deferred += 1
        elif outcome == "escalated":
            escalated_count += 1

    valid_escalations = 0
    pending_human_decisions = []
    for entry in escalations:
        esc_ok, _ = _is_valid_escalation_entry(
            entry, work_item_ids, collect_errors=False,
        )
        if esc_ok:
            valid_escalations += 1
            pending_human_decisions.append({
                "escalation_id": entry.get("id", ""),
                "decision_requested": entry.get("decision_requested", ""),
                "why_required": entry.get("why_required", ""),
                "consequence_if_declined": entry.get("consequence_if_declined", ""),
            })

    return {
        "total_policy_decisions": len(policy_decisions),
        "granted": granted,
        "denied": denied,
        "deferred": deferred,
        "escalated": escalated_count,
        "self_promotion_blocked": self_promotion_blocked,
        "total_escalations": len(escalations),
        "valid_escalations": valid_escalations,
        "pending_human_decisions": pending_human_decisions,
    }
