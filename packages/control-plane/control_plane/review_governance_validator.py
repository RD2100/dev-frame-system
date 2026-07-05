"""Semantic validator for review-governance kernel packets.

Complements draft-07 schema validation with cross-object constraints that
JSON Schema cannot express:

1. work_item.status=completed requires a gate decision with outcome=pass
2. Gate/review pass requires evidence_ids that resolve to existing evidence
   with supports="supports"
3. All principal_id references must resolve to declared principals
4. Projection computed_status must be consistent with decisions
5. evidence.source_artifact_id must resolve to existing artifacts
6. projection.computed_status=ready vs work_item.status=completed reverse check
7. latest_decision_id must belong to current work_item

Also provides derive_projection() — a read-only Phase 1B helper that computes
projection fields from packet facts without inventing authority.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence


@dataclass
class ValidationResult:
    valid: bool
    errors: list[str] = field(default_factory=list)

    def __bool__(self) -> bool:
        return self.valid


def validate_packet(payload: dict) -> ValidationResult:
    errors: list[str] = []

    # ---- helpers ----
    def _get(path: str) -> object | None:
        cur = payload
        for key in path.split("."):
            if isinstance(cur, dict) and key in cur:
                cur = cur[key]
            else:
                return None
        return cur

    principals: list[dict] = _get("principals") or []
    principal_ids = {p["id"] for p in principals if "id" in p}
    artifacts: list[dict] = _get("artifacts") or []
    artifact_ids = {a["id"] for a in artifacts if "id" in a}
    evidence: list[dict] = _get("evidence") or []
    evidence_by_id = {e["id"]: e for e in evidence if "id" in e}
    decisions: list[dict] = _get("decisions") or []
    projection: dict = _get("projection") or {}
    work_item: dict = _get("work_item") or {}
    project: dict = _get("project") or {}
    runs: list[dict] = _get("runs") or []

    # ---- P0: completed requires gate pass for THIS work item ----
    if work_item.get("status") == "completed":
        wi_id = work_item.get("id", "")
        gate_pass = any(
            d.get("kind") == "gate"
            and d.get("outcome") == "pass"
            and d.get("target_ref") == wi_id
            for d in decisions
        )
        if not gate_pass:
            errors.append(
                f"work_item.status=completed requires a Decision(kind=gate, "
                f"outcome=pass, target_ref={wi_id!r})"
            )

    # ---- P0: evidence_ids must resolve to real supporting evidence ----
    artifact_kind_by_id = {a["id"]: a.get("kind") for a in artifacts if "id" in a}
    for decision in decisions:
        if decision.get("kind") in ("review", "gate") and decision.get("outcome") == "pass":
            gate_evidence_ids = decision.get("evidence_ids", [])
            for eid in gate_evidence_ids:
                if eid not in evidence_by_id:
                    errors.append(
                        f"Decision {decision['id']} references missing "
                        f"evidence_id {eid}"
                    )
                else:
                    ev = evidence_by_id[eid]
                    if ev.get("supports") not in ("supports", "confirm"):
                        errors.append(
                            f"Decision {decision['id']} gate pass references "
                            f"evidence {eid} with supports={ev.get('supports')!r}, "
                            f"expected 'supports'"
                        )
                    # P0: gate pass must cite at least one non-report artifact
                    src_aid = ev.get("source_artifact_id")
                    if src_aid and artifact_kind_by_id.get(src_aid) == "review_report":
                        continue  # this one is report-only, check next
                    # Found a non-report evidence source for this gate decision
                    if decision.get("kind") == "gate" and decision.get("outcome") == "pass":
                        # mark that this gate has non-report evidence
                        pass  # handled via counter below

    # Check that each gate pass has at least one non-report evidence source
    for decision in decisions:
        if decision.get("kind") != "gate" or decision.get("outcome") != "pass":
            continue
        gate_evidence_ids = decision.get("evidence_ids", [])
        has_non_report = any(
            artifact_kind_by_id.get(evidence_by_id[eid].get("source_artifact_id", ""), "")
            != "review_report"
            for eid in gate_evidence_ids
            if eid in evidence_by_id
        )
        if not has_non_report:
            errors.append(
                f"Decision {decision['id']} gate pass must cite at least one "
                f"non-review_report artifact as evidence source"
            )

    # ---- P1: input_context_artifact_id must resolve if status is ready/completed ----
    ctx_artifact_id = work_item.get("input_context_artifact_id")
    if ctx_artifact_id and work_item.get("status") in ("ready", "completed"):
        if ctx_artifact_id not in artifact_ids:
            errors.append(
                f"work_item.input_context_artifact_id={ctx_artifact_id!r} "
                f"not found in artifacts; cannot be {work_item['status']}"
            )

    # ---- P1: evidence.source_artifact_id must resolve to existing artifacts ----
    for ev in evidence:
        src = ev.get("source_artifact_id")
        if src and src not in artifact_ids:
            errors.append(
                f"evidence {ev.get('id')} source_artifact_id={src!r} not found in artifacts"
            )

    # ---- P1: all principal references must resolve ----
    owner_pid = project.get("owner_principal_id")
    if owner_pid and owner_pid not in principal_ids:
        errors.append(f"project.owner_principal_id={owner_pid!r} not in principals")
    for run in runs:
        pid = run.get("principal_id")
        if pid and pid not in principal_ids:
            errors.append(f"run {run.get('id')} principal_id={pid!r} not in principals")
    for dec in decisions:
        pid = dec.get("decider_principal_id")
        if pid and pid not in principal_ids:
            errors.append(f"decision {dec.get('id')} decider_principal_id={pid!r} not in principals")

    # ---- P1: projection computed_status must be consistent ----
    computed = projection.get("computed_status", "")
    wi_id = work_item.get("id", "")
    has_gate_pass_for_wi = any(
        d.get("kind") == "gate"
        and d.get("outcome") == "pass"
        and d.get("target_ref") == wi_id
        for d in decisions
    )
    has_review_pass_for_wi = any(
        d.get("kind") == "review"
        and d.get("outcome") == "pass"
        and d.get("target_ref") == wi_id
        for d in decisions
    )

    expected_status = work_item.get("status", "")
    if computed == "completed" and not has_gate_pass_for_wi:
        errors.append(
            f"projection.computed_status=completed but no gate pass decision "
            f"found for work_item {wi_id!r}"
        )
    if computed == "completed" and expected_status != "completed":
        errors.append(
            f"projection.computed_status=completed but "
            f"work_item.status={expected_status!r}"
        )
    if computed == "ready" and expected_status == "completed":
        errors.append(
            f"projection.computed_status=ready but "
            f"work_item.status=completed (reverse inconsistency)"
        )
    if computed == "insufficient_evidence":
        has_ie_for_wi = any(
            d.get("outcome") == "insufficient_evidence"
            and d.get("target_ref") == wi_id
            for d in decisions
        )
        if not has_ie_for_wi:
            errors.append(
                "projection.computed_status=insufficient_evidence but no "
                "decision(outcome=insufficient_evidence, target_ref=work_item.id)"
            )
    if computed == "blocked" and decisions:
        has_blocked_for_wi = any(
            d.get("outcome") == "blocked"
            and d.get("target_ref") == wi_id
            for d in decisions
        )
        has_hr_for_wi = any(
            d.get("kind") == "gate"
            and d.get("outcome") == "human_required"
            and d.get("target_ref") == wi_id
            for d in decisions
        )
        if not has_blocked_for_wi and not has_hr_for_wi:
            errors.append(
                "projection.computed_status=blocked but no "
                "blocked/human_required decision for work_item"
            )

    # ---- P1: projection reference consistency ----
    proj_wi_id = projection.get("work_item_id", "")
    if proj_wi_id and proj_wi_id != wi_id:
        errors.append(
            f"projection.work_item_id={proj_wi_id!r} does not match "
            f"work_item.id={wi_id!r}"
        )
    decision_summary = projection.get("decision_summary", {})
    latest_id = decision_summary.get("latest_decision_id", "")
    if latest_id:
        decisions_by_id = {d.get("id"): d for d in decisions if "id" in d}
        if latest_id not in decisions_by_id:
            errors.append(
                f"projection.decision_summary.latest_decision_id={latest_id!r} "
                f"not found in decisions"
            )
        else:
            latest_dec = decisions_by_id[latest_id]
            if latest_dec.get("target_ref") != wi_id:
                errors.append(
                    f"projection.decision_summary.latest_decision_id={latest_id!r} "
                    f"targets work_item {latest_dec.get('target_ref')!r}, "
                    f"not current work_item {wi_id!r}"
                )
    rev_outcome = decision_summary.get("review_outcome", "")
    if rev_outcome:
        matching = [
            d for d in decisions
            if d.get("kind") == "review"
            and d.get("target_ref") == wi_id
            and d.get("outcome") == rev_outcome
        ]
        if not matching:
            errors.append(
                f"projection.decision_summary.review_outcome={rev_outcome!r} "
                f"does not match any review decision for work_item"
            )
    gate_outcome = decision_summary.get("gate_outcome", "")
    if gate_outcome:
        matching = [
            d for d in decisions
            if d.get("kind") == "gate"
            and d.get("target_ref") == wi_id
            and d.get("outcome") == gate_outcome
        ]
        if not matching:
            errors.append(
                f"projection.decision_summary.gate_outcome={gate_outcome!r} "
                f"does not match any gate decision for work_item"
            )

    return ValidationResult(valid=len(errors) == 0, errors=errors)


def derive_projection(payload: dict) -> dict:
    """Derive projection from packet facts (Phase 1B helper).

    Computes computed_status, blocked_reason, and decision_summary
    from the packet's decisions, work_item, and evidence. Does not
    invent authority — it is a read-only derivation from packet facts.
    """
    wi_id = (payload.get("work_item") or {}).get("id", "")
    decisions: list[dict] = payload.get("decisions") or []
    evidence: list[dict] = payload.get("evidence") or []
    evidence_by_id = {e["id"]: e for e in evidence if "id" in e}

    # Collect decisions for this work item
    wi_reviews = [
        d for d in decisions
        if d.get("kind") == "review" and d.get("target_ref") == wi_id
    ]
    wi_gates = [
        d for d in decisions
        if d.get("kind") == "gate" and d.get("target_ref") == wi_id
    ]

    # Latest decision (last in array for this work item)
    wi_decisions = wi_reviews + wi_gates
    latest_id = wi_decisions[-1]["id"] if wi_decisions else ""

    # Review outcome
    review_outcome = ""
    for d in reversed(wi_reviews):
        review_outcome = d.get("outcome", "")
        break

    # Gate outcome
    gate_outcome = ""
    for d in reversed(wi_gates):
        gate_outcome = d.get("outcome", "")
        break

    # Computed status
    if any(d.get("outcome") == "human_required" for d in wi_decisions):
        computed_status = "blocked"
        blocked_reason = "human_required"
    elif any(d.get("outcome") == "blocked" for d in wi_decisions):
        computed_status = "blocked"
        blocked_reason = next(
            (d.get("payload", {}).get("blocked_reasons", ["blocked"])[0]
             if isinstance(d.get("payload"), dict) else "blocked")
            for d in wi_decisions if d.get("outcome") == "blocked"
        )
    elif any(d.get("outcome") == "insufficient_evidence" for d in wi_decisions):
        computed_status = "insufficient_evidence"
        blocked_reason = "insufficient_evidence"
    elif any(d.get("outcome") == "pass" and d.get("kind") == "gate" for d in wi_decisions):
        computed_status = "completed"
        blocked_reason = ""
    elif any(d.get("outcome") == "pass" and d.get("kind") == "review" for d in wi_decisions):
        computed_status = "reviewing"
        blocked_reason = ""
    else:
        computed_status = "ready"
        blocked_reason = ""

    # Evidence summary
    total = len(evidence)
    supporting = sum(1 for e in evidence if e.get("supports") in ("supports", "confirm"))
    rejecting = sum(1 for e in evidence if e.get("supports") == "rejects")
    inconclusive = sum(1 for e in evidence if e.get("supports") == "inconclusive")

    return {
        "work_item_id": wi_id,
        "computed_status": computed_status,
        "blocked_reason": blocked_reason,
        "evidence_summary": {
            "total_evidence_count": total,
            "supporting_count": supporting,
            "rejecting_count": rejecting,
            "inconclusive_count": inconclusive,
        },
        "decision_summary": {
            "review_outcome": review_outcome,
            "gate_outcome": gate_outcome,
            "latest_decision_id": latest_id,
        },
        "allowed_actions": _derive_allowed_actions(computed_status),
    }


def _derive_allowed_actions(computed_status: str) -> list[str]:
    mapping = {
        "completed": ["view", "archive"],
        "blocked": ["view", "escalate"],
        "insufficient_evidence": ["view", "add_evidence", "review"],
        "reviewing": ["view"],
        "ready": ["view", "execute", "edit"],
    }
    return mapping.get(computed_status, ["view"])
