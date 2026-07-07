"""Phase 4d: external-review feedback ledger validator.

An `external_review` record accounts for a GPT review round so it can be
audited offline. It is NOT standalone authority — it must point to:

  - an existing artifact (produced_artifact — the review bundle)
  - existing supporting evidence (evidence_ids) — which themselves point to
    artifacts via source_artifact_id
  - a gate decision (gate_decision) that accepted the review round's output

The review is only counted as `adopted` in projection when promotion_state=
"adopted" AND the full gate chain passes.

Plan: "External-review feedback ledger: Normalize accepted/rejected/deferred
GPT review feedback. Review bundle verdict maps to local decision without
becoming authority." (skill-asset-utilization-plan.md:247)

Stop line: "Do not treat GPT output as project authority" (line 270).
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ValidationResult:
    valid: bool
    errors: list[str] = field(default_factory=list)

    def __bool__(self) -> bool:
        return self.valid


REQUIRED_SCALAR_FIELDS = (
    "id",
    "project_id",
    "review_round",
    "review_url",
    "external_verdict",
    "last_used_at",
    "promotion_state",
)

VALID_EXTERNAL_VERDICTS = ("accepted", "rejected", "deferred", "conditional")
VALID_PROMOTION_STATES = ("pending", "adopted", "quarantined", "deprecated", "rejected")


def _has_required_value(value) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return value.strip() != ""
    return value != ""


def _id_label(value) -> str:
    if not _has_required_value(value):
        return "<missing id>"
    return str(value)


def _is_valid_review_base(
    rf: dict,
    evidence_by_id: dict,
    artifact_ids: set,
    collect_errors: bool = False,
) -> tuple[bool, list[str]]:
    """Base eligibility: does the review_feedback record itself point to
    valid artifacts and evidence (ignoring the gate decision)?

    True only when ALL hold:
      - all required scalar fields are non-empty
      - external_verdict is a valid verdict value
      - produced_artifact is non-empty and resolves to a declared artifact
      - evidence_ids is non-empty
      - every evidence resolves, supports="supports", source_artifact_id
        resolves to a declared artifact
    """
    errors: list[str] = []
    rf_id = rf.get("id", "")
    produced_artifact = rf.get("produced_artifact", "")
    evidence_ids = rf.get("evidence_ids") or []
    external_verdict = rf.get("external_verdict", "")
    promotion_state = rf.get("promotion_state", "")
    prefix = f"review_feedback[{_id_label(rf_id)}]"

    for field_name in REQUIRED_SCALAR_FIELDS:
        val = rf.get(field_name)
        if not _has_required_value(val):
            if collect_errors:
                errors.append(f"{prefix}: {field_name} is required")
            else:
                return False, errors

    if (
        _has_required_value(external_verdict)
        and external_verdict not in VALID_EXTERNAL_VERDICTS
    ):
        if collect_errors:
            errors.append(
                f"{prefix}: external_verdict {external_verdict!r} is not in "
                f"valid set {VALID_EXTERNAL_VERDICTS}"
            )
        else:
            return False, errors

    if not _has_required_value(produced_artifact):
        if collect_errors:
            errors.append(f"{prefix}: produced_artifact is required")
        else:
            return False, errors
    elif produced_artifact not in artifact_ids:
        if collect_errors:
            errors.append(
                f"{prefix}: produced_artifact {produced_artifact!r} "
                f"does not resolve to a declared artifact"
            )
        else:
            return False, errors

    if not evidence_ids:
        if collect_errors:
            errors.append(
                f"{prefix}: evidence_ids must include at least one "
                f"supporting evidence_id (standalone authority forbidden)"
            )
        else:
            return False, errors

    for eid in evidence_ids:
        if not _has_required_value(eid):
            if collect_errors:
                errors.append(f"{prefix}: evidence_ids contains blank evidence_id")
                continue
            return False, errors
        ev = evidence_by_id.get(eid)
        if ev is None:
            if collect_errors:
                errors.append(
                    f"{prefix}: evidence_id {eid!r} does not resolve "
                    f"to declared evidence"
                )
                continue
            return False, errors
        if ev.get("supports") != "supports":
            if collect_errors:
                errors.append(
                    f"{prefix}: evidence_id {eid!r} has supports="
                    f"{ev.get('supports')!r}; only supports='supports' counts"
                )
                continue
            return False, errors
        src = ev.get("source_artifact_id", "")
        if not _has_required_value(src):
            if collect_errors:
                errors.append(
                    f"{prefix}: evidence {eid!r} has no source_artifact_id"
                )
                continue
            return False, errors
        if src not in artifact_ids:
            if collect_errors:
                errors.append(
                    f"{prefix}: evidence {eid!r} source_artifact_id={src!r} "
                    f"does not resolve to a declared artifact"
                )
                continue
            return False, errors

    if _has_required_value(promotion_state) and promotion_state not in VALID_PROMOTION_STATES:
        if collect_errors:
            errors.append(
                f"{prefix}: promotion_state {promotion_state!r} is not in "
                f"valid set {VALID_PROMOTION_STATES}"
            )
        else:
            return False, errors

    if external_verdict == "rejected" and promotion_state == "adopted":
        if collect_errors:
            errors.append(
                f"{prefix}: external_verdict='rejected' cannot have "
                f"promotion_state='adopted'"
            )
        else:
            return False, errors

    return len(errors) == 0, errors


def _is_valid_gate_adoption(
    rf: dict,
    decision_by_id: dict,
    evidence_by_id: dict,
    artifact_ids: set,
    collect_errors: bool = False,
) -> tuple[bool, list[str]]:
    """Full gate-adoption judgment.

    True only when ALL hold:
      - base eligibility holds
      - gate_decision resolves to a declared decision
      - decision.kind == "gate"
      - decision.outcome == "pass"
      - decision.target_ref == rf["id"]
      - decision.evidence_ids is non-empty
      - every decision.evidence_id resolves, supports="supports",
        source_artifact_id resolves to a declared artifact
      - decision.evidence_ids covers rf.evidence_ids
    """
    errors: list[str] = []
    rf_id = rf.get("id", "")
    evidence_ids = rf.get("evidence_ids") or []
    gate_decision = rf.get("gate_decision", "") or ""
    prefix = f"review_feedback[{_id_label(rf_id)}]"

    if not _has_required_value(gate_decision):
        return False, errors

    base_ok, base_errors = _is_valid_review_base(
        rf, evidence_by_id, artifact_ids, collect_errors=collect_errors
    )
    if collect_errors:
        errors.extend(base_errors)
    if not base_ok:
        return False, errors

    dec = decision_by_id.get(gate_decision)
    if dec is None:
        if collect_errors:
            errors.append(
                f"{prefix}: gate_decision {gate_decision!r} "
                f"does not resolve to a declared decision"
            )
        return False, errors

    dec_kind = dec.get("kind", "")
    dec_outcome = dec.get("outcome", "")
    dec_target_ref = dec.get("target_ref", "")
    dec_evidence_ids = dec.get("evidence_ids") or []

    if dec_kind != "gate":
        if collect_errors:
            errors.append(
                f"{prefix}: gate decision {gate_decision!r} "
                f"has kind={dec_kind!r}; must be kind='gate'"
            )
        return False, errors
    if dec_outcome != "pass":
        if collect_errors:
            errors.append(
                f"{prefix}: gate decision {gate_decision!r} "
                f"has outcome={dec_outcome!r}; must be outcome='pass'"
            )
        return False, errors
    if not _has_required_value(rf_id):
        return False, errors
    if not _has_required_value(dec_target_ref):
        if collect_errors:
            errors.append(
                f"{prefix}: gate decision {gate_decision!r} "
                f"target_ref is required"
            )
        return False, errors
    if dec_target_ref != rf_id:
        if collect_errors:
            errors.append(
                f"{prefix}: gate decision {gate_decision!r} "
                f"has target_ref={dec_target_ref!r}; must equal review_feedback "
                f"id {rf_id!r}"
            )
        return False, errors
    if not dec_evidence_ids:
        if collect_errors:
            errors.append(
                f"{prefix}: gate decision {gate_decision!r} "
                f"has no evidence_ids; adoption must be evidence-backed"
            )
        return False, errors

    for eid in dec_evidence_ids:
        if not _has_required_value(eid):
            if collect_errors:
                errors.append(
                    f"{prefix}: gate decision {gate_decision!r} "
                    f"references blank evidence_id"
                )
                continue
            return False, errors
        ev = evidence_by_id.get(eid)
        if ev is None:
            if collect_errors:
                errors.append(
                    f"{prefix}: gate decision {gate_decision!r} "
                    f"references missing evidence_id {eid!r}"
                )
                continue
            return False, errors
        if ev.get("supports") != "supports":
            if collect_errors:
                errors.append(
                    f"{prefix}: gate decision {gate_decision!r} "
                    f"references evidence {eid!r} with supports="
                    f"{ev.get('supports')!r}; expected supports='supports'"
                )
                continue
            return False, errors
        dsrc = ev.get("source_artifact_id", "")
        if not _has_required_value(dsrc):
            if collect_errors:
                errors.append(
                    f"{prefix}: gate decision {gate_decision!r} "
                    f"evidence {eid!r} has no source_artifact_id"
                )
                continue
            return False, errors
        if dsrc not in artifact_ids:
            if collect_errors:
                errors.append(
                    f"{prefix}: gate decision {gate_decision!r} "
                    f"evidence {eid!r} source_artifact_id={dsrc!r} "
                    f"does not resolve to a declared artifact"
                )
                continue
            return False, errors

    if not set(evidence_ids).issubset(set(dec_evidence_ids)):
        if collect_errors:
            missing = set(evidence_ids) - set(dec_evidence_ids)
            errors.append(
                f"{prefix}: gate decision {gate_decision!r} "
                f"evidence_ids must cover record evidence_ids; missing: "
                f"{sorted(missing)}"
            )
        return False, errors

    return len(errors) == 0, errors


def validate_review_feedback(payload: dict) -> ValidationResult:
    """Validate that review_feedback records point to existing artifacts,
    evidence, and gate decisions — and that promotion_state="adopted" requires
    an evidence-backed gate decision.

    Additionally enforces the external-review plan invariant:
    - external_verdict="rejected" cannot have promotion_state="adopted"
    """
    errors: list[str] = []

    rf_list: list[dict] = payload.get("review_feedback") or []
    artifacts: list[dict] = payload.get("artifacts") or []
    evidence: list[dict] = payload.get("evidence") or []
    decisions: list[dict] = payload.get("decisions") or []

    artifact_ids = {
        a.get("id") for a in artifacts if _has_required_value(a.get("id"))
    }
    evidence_by_id = {
        e.get("id"): e for e in evidence if _has_required_value(e.get("id"))
    }
    decision_by_id = {
        d.get("id"): d for d in decisions if _has_required_value(d.get("id"))
    }

    for rf in rf_list:
        rf_id = rf.get("id", "")
        gate_decision = rf.get("gate_decision", "") or ""
        promotion_state = rf.get("promotion_state", "") or ""
        external_verdict = rf.get("external_verdict", "") or ""
        prefix = f"review_feedback[{_id_label(rf_id)}]"

        # Base eligibility (required scalars + produced_artifact + evidence chain)
        _, base_errors = _is_valid_review_base(
            rf, evidence_by_id, artifact_ids, collect_errors=True
        )
        errors.extend(base_errors)

        # Gate adoption chain
        if _has_required_value(gate_decision):
            gate_ok, gate_errors = _is_valid_gate_adoption(
                rf, decision_by_id, evidence_by_id, artifact_ids,
                collect_errors=True,
            )
            errors.extend(gate_errors)

            # promotion_state="adopted" requires a valid passing gate
            if promotion_state == "adopted" and not gate_ok:
                errors.append(
                    f"{prefix}: promotion_state='adopted' requires a valid "
                    f"evidence-backed gate decision with outcome='pass'"
                )

        # gate_decision is required
        if not _has_required_value(gate_decision):
            errors.append(f"{prefix}: gate_decision is required")

    return ValidationResult(valid=len(errors) == 0, errors=errors)


def derive_review_feedback(payload: dict) -> dict:
    """Read-only projection: count review feedback rounds and adoptions.

    Does NOT invent authority — adoption only counts when the FULL gate
    adoption chain is valid, via _is_valid_gate_adoption() (which includes
    base eligibility + gate decision kind/outcome/target_ref + evidence chain
    + coverage).
    """
    rf_list: list[dict] = payload.get("review_feedback") or []
    decisions: list[dict] = payload.get("decisions") or []
    evidence: list[dict] = payload.get("evidence") or []
    artifacts: list[dict] = payload.get("artifacts") or []
    decision_by_id = {
        d.get("id"): d for d in decisions if _has_required_value(d.get("id"))
    }
    evidence_by_id = {
        e.get("id"): e for e in evidence if _has_required_value(e.get("id"))
    }
    artifact_ids = {
        a.get("id") for a in artifacts if _has_required_value(a.get("id"))
    }

    adopted_count = 0
    by_verdict: dict[str, dict] = {}

    for rf in rf_list:
        external_verdict = rf.get("external_verdict", "")
        promotion_state = rf.get("promotion_state", "")
        gate_ok, _ = _is_valid_gate_adoption(
            rf, decision_by_id, evidence_by_id, artifact_ids,
            collect_errors=False,
        )
        is_adopted = promotion_state == "adopted" and gate_ok
        if is_adopted:
            adopted_count += 1

        if external_verdict not in by_verdict:
            by_verdict[external_verdict] = {
                "verdict": external_verdict,
                "count": 0,
                "adopted_count": 0,
            }
        by_verdict[external_verdict]["count"] += 1
        if is_adopted:
            by_verdict[external_verdict]["adopted_count"] += 1

    return {
        "review_feedback_count": len(rf_list),
        "adopted_count": adopted_count,
        "by_verdict": by_verdict,
    }
