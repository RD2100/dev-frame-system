"""Phase 4b: asset_utilization record validator.

An `asset_utilization` record accounts for the selection and outcome of a
reusable asset (skill, MCP tool, external-review bundle, plugin, schema, etc.).
It is NOT standalone authority — it must point to:

  - an existing artifact (produced_artifact)
  - existing supporting evidence (evidence_ids) — which themselves point to
    artifacts via source_artifact_id
  - a gate decision (gate_decision) that accepted the asset's output

An asset's `promotion_state` only advances to "adopted" when the gate decision
is evidence-backed (kind="gate", outcome="pass", target_ref==record id,
evidence_ids non-empty + resolving + supporting + covering the record's
evidence_ids).

The adoption judgment is centralized in `_is_valid_gate_adoption()` and base
eligibility in `_is_valid_asset_base()`. Both `validate_asset_utilization()`
and `derive_asset_utilization()` build on the SAME helpers, so projection
never invents adoption that the validator would reject.

Minimum record fields (per skill-asset-utilization-plan.md):
  id, project_id, asset_id, asset_type, source_tier,
  selected_for_work_type, selection_reason, produced_artifact,
  evidence_ids, gate_decision, last_used_at, promotion_state
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
    "asset_id",
    "asset_type",
    "source_tier",
    "selected_for_work_type",
    "selection_reason",
    "gate_decision",
    "last_used_at",
    "promotion_state",
)

VALID_PROMOTION_STATES = ("pending", "adopted", "quarantined", "deprecated", "rejected")


def _has_required_value(value: object) -> bool:
    if isinstance(value, str):
        return bool(value.strip())
    return bool(value)


def _is_valid_asset_base(
    au: dict,
    evidence_by_id: dict,
    artifact_ids: set,
    collect_errors: bool = False,
) -> tuple[bool, list[str]]:
    """Base eligibility: does the asset_utilization record itself point to
    valid artifacts and evidence (ignoring the gate decision)?

    True only when ALL hold:
      - all required scalar fields are non-empty
      - produced_artifact is non-empty and resolves to a declared artifact
      - evidence_ids is non-empty
      - every evidence resolves, supports="supports", source_artifact_id
        resolves to a declared artifact
    """
    errors: list[str] = []
    valid = True
    au_id = au.get("id", "")
    produced_artifact = au.get("produced_artifact", "")
    evidence_ids = au.get("evidence_ids") or []
    promotion_state = au.get("promotion_state", "")
    prefix_id = au_id if _has_required_value(au_id) else "<missing id>"
    prefix = f"asset_utilization[{prefix_id}]"

    for field_name in REQUIRED_SCALAR_FIELDS:
        if not _has_required_value(au.get(field_name, "")):
            if collect_errors:
                errors.append(f"{prefix}: {field_name} is required")
                valid = False
            else:
                return False, errors

    if not _has_required_value(produced_artifact):
        if collect_errors:
            errors.append(f"{prefix}: produced_artifact is required")
            valid = False
        else:
            return False, errors
    elif produced_artifact not in artifact_ids:
        if collect_errors:
            errors.append(
                f"{prefix}: produced_artifact {produced_artifact!r} "
                f"does not resolve to a declared artifact"
            )
            valid = False
        else:
            return False, errors

    if not evidence_ids:
        if collect_errors:
            errors.append(
                f"{prefix}: evidence_ids must include at least one "
                f"supporting evidence_id (standalone authority forbidden)"
            )
            valid = False
        else:
            return False, errors

    for eid in evidence_ids:
        if not _has_required_value(eid):
            if collect_errors:
                errors.append(f"{prefix}: evidence_id {eid!r} is required")
                valid = False
                continue
            return False, errors
        ev = evidence_by_id.get(eid)
        if ev is None:
            if collect_errors:
                errors.append(
                    f"{prefix}: evidence_id {eid!r} does not resolve "
                    f"to declared evidence"
                )
                valid = False
                continue
            return False, errors
        if ev.get("supports") != "supports":
            if collect_errors:
                errors.append(
                    f"{prefix}: evidence_id {eid!r} has supports="
                    f"{ev.get('supports')!r}; only supports='supports' counts"
                )
                valid = False
                continue
            return False, errors
        src = ev.get("source_artifact_id", "")
        if not _has_required_value(src):
            if collect_errors:
                errors.append(
                    f"{prefix}: evidence {eid!r} has no source_artifact_id"
                )
                valid = False
                continue
            return False, errors
        if src not in artifact_ids:
            if collect_errors:
                errors.append(
                    f"{prefix}: evidence {eid!r} source_artifact_id={src!r} "
                    f"does not resolve to a declared artifact"
                )
                valid = False
                continue
            return False, errors

    if (
        _has_required_value(promotion_state)
        and promotion_state not in VALID_PROMOTION_STATES
    ):
        if collect_errors:
            errors.append(
                f"{prefix}: promotion_state {promotion_state!r} is not in "
                f"valid set {VALID_PROMOTION_STATES}"
            )
            valid = False
        else:
            return False, errors

    return valid, errors


def _is_valid_gate_adoption(
    au: dict,
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
      - decision.target_ref == au["id"]
      - decision.evidence_ids is non-empty
      - every decision.evidence_id resolves, supports="supports",
        source_artifact_id resolves to a declared artifact
      - decision.evidence_ids ⊇ au.evidence_ids
    """
    errors: list[str] = []
    valid = True
    au_id = au.get("id", "")
    evidence_ids = au.get("evidence_ids") or []
    gate_decision = au.get("gate_decision", "") or ""
    prefix_id = au_id if _has_required_value(au_id) else "<missing id>"
    prefix = f"asset_utilization[{prefix_id}]"

    if not _has_required_value(gate_decision):
        return False, errors  # no gate claimed — not an error, just not adopted

    base_ok, base_errors = _is_valid_asset_base(
        au, evidence_by_id, artifact_ids, collect_errors=collect_errors
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
    if not _has_required_value(au_id):
        return False, errors
    if not _has_required_value(dec_target_ref) or dec_target_ref != au_id:
        if collect_errors:
            errors.append(
                f"{prefix}: gate decision {gate_decision!r} "
                f"has target_ref={dec_target_ref!r}; must equal asset_utilization "
                f"id {au_id!r}"
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
                    f"references blank evidence_id {eid!r}"
                )
                valid = False
                continue
            return False, errors
        ev = evidence_by_id.get(eid)
        if ev is None:
            if collect_errors:
                errors.append(
                    f"{prefix}: gate decision {gate_decision!r} "
                    f"references missing evidence_id {eid!r}"
                )
                valid = False
                continue
            return False, errors
        if ev.get("supports") != "supports":
            if collect_errors:
                errors.append(
                    f"{prefix}: gate decision {gate_decision!r} "
                    f"references evidence {eid!r} with supports="
                    f"{ev.get('supports')!r}; expected supports='supports'"
                )
                valid = False
                continue
            return False, errors
        dsrc = ev.get("source_artifact_id", "")
        if not _has_required_value(dsrc):
            if collect_errors:
                errors.append(
                    f"{prefix}: gate decision {gate_decision!r} "
                    f"evidence {eid!r} has no source_artifact_id"
                )
                valid = False
                continue
            return False, errors
        if dsrc not in artifact_ids:
            if collect_errors:
                errors.append(
                    f"{prefix}: gate decision {gate_decision!r} "
                    f"evidence {eid!r} source_artifact_id={dsrc!r} "
                    f"does not resolve to a declared artifact"
                )
                valid = False
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

    return valid, errors


def validate_asset_utilization(payload: dict) -> ValidationResult:
    """Validate that asset_utilization records point to existing artifacts,
    evidence, and gate decisions — and that promotion_state="adopted" requires
    an evidence-backed gate decision.
    """
    errors: list[str] = []

    au_list: list[dict] = payload.get("asset_utilization") or []
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

    for au in au_list:
        au_id = au.get("id", "")
        gate_decision = au.get("gate_decision", "") or ""
        promotion_state = au.get("promotion_state", "") or ""
        prefix_id = au_id if _has_required_value(au_id) else "<missing id>"
        prefix = f"asset_utilization[{prefix_id}]"

        # Base eligibility (required scalars + produced_artifact + evidence chain)
        _, base_errors = _is_valid_asset_base(
            au, evidence_by_id, artifact_ids, collect_errors=True
        )
        errors.extend(base_errors)

        # Gate adoption chain
        if _has_required_value(gate_decision):
            gate_ok, gate_errors = _is_valid_gate_adoption(
                au, decision_by_id, evidence_by_id, artifact_ids,
                collect_errors=True,
            )
            errors.extend(gate_errors)

            # promotion_state="adopted" requires a valid passing gate
            if promotion_state == "adopted" and not gate_ok:
                errors.append(
                    f"{prefix}: promotion_state='adopted' requires a valid "
                    f"evidence-backed gate decision with outcome='pass'"
                )

    return ValidationResult(valid=len(errors) == 0, errors=errors)


def derive_asset_utilization(payload: dict) -> dict:
    """Read-only projection: count asset utilization and adoptions.

    Does NOT invent authority — adoption only counts when the FULL gate
    adoption chain is valid, via _is_valid_gate_adoption() (which includes
    base eligibility + gate decision kind/outcome/target_ref + evidence chain
    + coverage).
    """
    au_list: list[dict] = payload.get("asset_utilization") or []
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

    utilized_count = 0
    adopted_count = 0
    by_asset_type: dict[str, dict] = {}

    for au in au_list:
        base_ok, _ = _is_valid_asset_base(
            au, evidence_by_id, artifact_ids, collect_errors=False,
        )
        if not base_ok:
            continue

        asset_type = au.get("asset_type", "")
        promotion_state = au.get("promotion_state", "")
        gate_ok, _ = _is_valid_gate_adoption(
            au, decision_by_id, evidence_by_id, artifact_ids,
            collect_errors=False,
        )
        # adoption in projection = declared adopted AND gate chain valid
        is_adopted = promotion_state == "adopted" and gate_ok
        if is_adopted:
            adopted_count += 1

        utilized_count += 1
        if asset_type not in by_asset_type:
            by_asset_type[asset_type] = {
                "asset_type": asset_type,
                "count": 0,
                "adopted_count": 0,
            }
        by_asset_type[asset_type]["count"] += 1
        if is_adopted:
            by_asset_type[asset_type]["adopted_count"] += 1

    return {
        "asset_utilization_count": utilized_count,
        "adopted_count": adopted_count,
        "by_asset_type": by_asset_type,
    }
