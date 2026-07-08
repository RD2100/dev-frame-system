"""Phase 4: skill_usage evidence validator.

A `skill_usage` record captures that a skill was invoked and produced an
artifact. It is NOT standalone authority — it must point to:

  - an existing artifact (produced_artifact_id)
  - existing supporting evidence (cited_evidence_ids) — which themselves point
    to artifacts via source_artifact_id
  - an optional adopt decision (adopted_by_decision_id)

A skill_usage only becomes an accountable asset when an evidence-backed
`adopt` decision with `outcome=pass` and `target_ref=<skill_usage_id>` adopts
it.

The adoption judgment is centralized in `_is_valid_adoption()` and the base
skill_usage eligibility in `_is_valid_skill_usage_base()`. Both
`validate_skill_usage()` and `derive_skill_utilization()` build on the SAME
helpers, so projection never invents adoption that the validator would reject.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ValidationResult:
    valid: bool
    errors: list[str] = field(default_factory=list)

    def __bool__(self) -> bool:
        return self.valid


def _has_required_value(value: object) -> bool:
    if isinstance(value, str):
        return bool(value.strip())
    return bool(value)


def _is_valid_skill_usage_base(
    su: dict,
    evidence_by_id: dict,
    artifact_ids: set,
    collect_errors: bool = False,
) -> tuple[bool, list[str]]:
    """Base eligibility: does the skill_usage itself point to valid artifacts
    and evidence (ignoring adoption)?

    True only when ALL hold:
      - id, skill_id, project_id, work_item_id, and invoked_at are non-empty
      - produced_artifact_id is non-empty and resolves to a declared artifact
      - cited_evidence_ids is non-empty
      - every cited evidence resolves, supports="supports", source_artifact_id
        resolves to a declared artifact

    When collect_errors=True, populates errors with per-field diagnostics
    (used by validate_skill_usage for reporting). When False, returns at first
    failure (fast path used by projection).
    """
    errors: list[str] = []
    su_id = su.get("id", "")
    skill_id = su.get("skill_id", "")
    project_id = su.get("project_id", "")
    work_item_id = su.get("work_item_id", "")
    invoked_at = su.get("invoked_at", "")
    produced_artifact_id = su.get("produced_artifact_id", "")
    cited_evidence_ids = su.get("cited_evidence_ids") or []
    prefix = (
        f"skill_usage[{su_id if _has_required_value(su_id) else '<missing id>'}]"
    )

    # Required scalar fields
    for field_name, field_val in (
        ("id", su_id),
        ("skill_id", skill_id),
        ("project_id", project_id),
        ("work_item_id", work_item_id),
        ("invoked_at", invoked_at),
    ):
        if not _has_required_value(field_val):
            if collect_errors:
                errors.append(f"{prefix}: {field_name} is required")
            else:
                return False, errors

    # produced_artifact_id must resolve
    if not _has_required_value(produced_artifact_id):
        if collect_errors:
            errors.append(f"{prefix}: produced_artifact_id is required")
        else:
            return False, errors
    elif produced_artifact_id not in artifact_ids:
        if collect_errors:
            errors.append(
                f"{prefix}: produced_artifact_id {produced_artifact_id!r} "
                f"does not resolve to a declared artifact"
            )
        else:
            return False, errors

    # cited_evidence_ids must be non-empty
    if not cited_evidence_ids or not any(
        _has_required_value(eid) for eid in cited_evidence_ids
    ):
        if collect_errors:
            errors.append(
                f"{prefix}: cited_evidence_ids must include at least one "
                f"supporting evidence_id (standalone authority forbidden)"
            )
        else:
            return False, errors

    # each cited evidence resolves + supports + source_artifact resolves
    for eid in cited_evidence_ids:
        if not _has_required_value(eid):
            if collect_errors:
                errors.append(f"{prefix}: cited_evidence_id is required")
                continue
            return False, errors
        ev = evidence_by_id.get(eid)
        if ev is None:
            if collect_errors:
                errors.append(
                    f"{prefix}: cited_evidence_id {eid!r} does not resolve "
                    f"to declared evidence"
                )
                continue
            return False, errors
        if ev.get("supports") != "supports":
            if collect_errors:
                errors.append(
                    f"{prefix}: cited_evidence_id {eid!r} has supports="
                    f"{ev.get('supports')!r}; only supports='supports' counts"
                )
                continue
            return False, errors
        src = ev.get("source_artifact_id", "")
        if not _has_required_value(src):
            if collect_errors:
                errors.append(
                    f"{prefix}: cited evidence {eid!r} has no source_artifact_id"
                )
                continue
            return False, errors
        if src not in artifact_ids:
            if collect_errors:
                errors.append(
                    f"{prefix}: cited evidence {eid!r} source_artifact_id={src!r} "
                    f"does not resolve to a declared artifact"
                )
                continue
            return False, errors

    return True, errors


def _is_valid_adoption(
    su: dict,
    decision_by_id: dict,
    evidence_by_id: dict,
    artifact_ids: set,
    collect_errors: bool = False,
) -> tuple[bool, list[str]]:
    """Full adoption-chain judgment.

    True only when ALL hold:
      - base skill_usage eligibility (_is_valid_skill_usage_base) holds
      - adopted_by_decision_id resolves to a declared decision
      - decision.kind == "adopt"
      - decision.outcome == "pass"
      - decision.target_ref == su["id"]
      - decision.evidence_ids is non-empty
      - every decision.evidence_id resolves, supports="supports",
        source_artifact_id resolves to a declared artifact
      - decision.evidence_ids ⊇ su.cited_evidence_ids

    Both validate_skill_usage() (collect_errors=True) and
    derive_skill_utilization() (collect_errors=False) use this helper, so
    projection cannot count an adoption the validator would reject.
    """
    errors: list[str] = []
    su_id = su.get("id", "")
    cited_evidence_ids = su.get("cited_evidence_ids") or []
    adopted_by_decision_id = su.get("adopted_by_decision_id") or ""
    prefix = (
        f"skill_usage[{su_id if _has_required_value(su_id) else '<missing id>'}]"
    )

    if not _has_required_value(adopted_by_decision_id):
        return False, errors  # not adopted — not an error

    # Base eligibility must hold first
    base_ok, base_errors = _is_valid_skill_usage_base(
        su, evidence_by_id, artifact_ids, collect_errors=collect_errors
    )
    if collect_errors:
        errors.extend(base_errors)
    if not base_ok:
        return False, errors

    dec = decision_by_id.get(adopted_by_decision_id)
    if dec is None:
        if collect_errors:
            errors.append(
                f"{prefix}: adopted_by_decision_id {adopted_by_decision_id!r} "
                f"does not resolve to a declared decision"
            )
        return False, errors

    dec_kind = dec.get("kind", "")
    dec_outcome = dec.get("outcome", "")
    dec_target_ref = dec.get("target_ref", "")
    dec_evidence_ids = dec.get("evidence_ids") or []

    if dec_kind != "adopt":
        if collect_errors:
            errors.append(
                f"{prefix}: adopting decision {adopted_by_decision_id!r} "
                f"has kind={dec_kind!r}; must be kind='adopt'"
            )
        return False, errors
    if dec_outcome != "pass":
        if collect_errors:
            errors.append(
                f"{prefix}: adopting decision {adopted_by_decision_id!r} "
                f"has outcome={dec_outcome!r}; must be outcome='pass'"
            )
        return False, errors
    if not _has_required_value(dec_target_ref):
        if collect_errors:
            errors.append(
                f"{prefix}: adopting decision {adopted_by_decision_id!r} "
                f"target_ref is required"
            )
        return False, errors
    if dec_target_ref != su_id:
        if collect_errors:
            errors.append(
                f"{prefix}: adopting decision {adopted_by_decision_id!r} "
                f"has target_ref={dec_target_ref!r}; must equal skill_usage "
                f"id {su_id!r}"
            )
        return False, errors
    if not dec_evidence_ids or not any(
        _has_required_value(eid) for eid in dec_evidence_ids
    ):
        if collect_errors:
            errors.append(
                f"{prefix}: adopting decision {adopted_by_decision_id!r} "
                f"has no evidence_ids; adoption must be evidence-backed"
            )
        return False, errors

    for eid in dec_evidence_ids:
        if not _has_required_value(eid):
            if collect_errors:
                errors.append(
                    f"{prefix}: adopting decision {adopted_by_decision_id!r} "
                    f"evidence_id is required"
                )
                continue
            return False, errors
        ev = evidence_by_id.get(eid)
        if ev is None:
            if collect_errors:
                errors.append(
                    f"{prefix}: adopting decision {adopted_by_decision_id!r} "
                    f"references missing evidence_id {eid!r}"
                )
                continue
            return False, errors
        if ev.get("supports") != "supports":
            if collect_errors:
                errors.append(
                    f"{prefix}: adopting decision {adopted_by_decision_id!r} "
                    f"references evidence {eid!r} with supports="
                    f"{ev.get('supports')!r}; expected supports='supports'"
                )
                continue
            return False, errors
        dsrc = ev.get("source_artifact_id", "")
        if not _has_required_value(dsrc):
            if collect_errors:
                errors.append(
                    f"{prefix}: adopting decision {adopted_by_decision_id!r} "
                    f"evidence {eid!r} has no source_artifact_id"
                )
                continue
            return False, errors
        if dsrc not in artifact_ids:
            if collect_errors:
                errors.append(
                    f"{prefix}: adopting decision {adopted_by_decision_id!r} "
                    f"evidence {eid!r} source_artifact_id={dsrc!r} "
                    f"does not resolve to a declared artifact"
                )
                continue
            return False, errors

    if not set(cited_evidence_ids).issubset(set(dec_evidence_ids)):
        if collect_errors:
            missing = set(cited_evidence_ids) - set(dec_evidence_ids)
            errors.append(
                f"{prefix}: adopting decision {adopted_by_decision_id!r} "
                f"evidence_ids must cover cited_evidence_ids; missing: "
                f"{sorted(missing)}"
            )
        return False, errors

    return True, errors


def validate_skill_usage(payload: dict) -> ValidationResult:
    """Validate that skill_usage records point to existing artifacts, evidence,
    and decisions — and that adoption is only claimed via an evidence-backed
    adopt decision (full chain, including produced artifact + source artifacts).

    Uses the SAME helpers as derive_skill_utilization(), so validator and
    projection cannot diverge.
    """
    errors: list[str] = []

    skill_usage_list: list[dict] = payload.get("skill_usage") or []
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

    for su in skill_usage_list:
        adopted_by_decision_id = su.get("adopted_by_decision_id") or ""

        # Base eligibility (required scalars + produced_artifact + cited evidence chain)
        _, base_errors = _is_valid_skill_usage_base(
            su, evidence_by_id, artifact_ids, collect_errors=True
        )
        errors.extend(base_errors)

        # Adoption chain — full check via shared helper
        if _has_required_value(adopted_by_decision_id):
            _, adoption_errors = _is_valid_adoption(
                su, decision_by_id, evidence_by_id, artifact_ids,
                collect_errors=True,
            )
            errors.extend(adoption_errors)

    return ValidationResult(valid=len(errors) == 0, errors=errors)


def derive_skill_utilization(payload: dict) -> dict:
    """Read-only projection: count skill invocations and adoptions.

    Does NOT invent authority — adoption only counts when the FULL adoption
    chain is valid, via _is_valid_adoption() (which includes base eligibility:
    produced_artifact_id resolves, cited evidence non-empty + resolving +
    source artifact; decision evidence non-empty + resolving + supporting +
    source artifact; coverage).
    """
    skill_usage_list: list[dict] = payload.get("skill_usage") or []
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
    by_skill: dict[str, dict] = {}

    for su in skill_usage_list:
        skill_id = su.get("skill_id", "")
        is_adopted, _ = _is_valid_adoption(
            su, decision_by_id, evidence_by_id, artifact_ids,
            collect_errors=False,
        )
        if is_adopted:
            adopted_count += 1

        if not _has_required_value(skill_id):
            continue

        if skill_id not in by_skill:
            by_skill[skill_id] = {
                "skill_id": skill_id,
                "invocation_count": 0,
                "adopted_count": 0,
            }
        by_skill[skill_id]["invocation_count"] += 1
        if is_adopted:
            by_skill[skill_id]["adopted_count"] += 1

    return {
        "skill_usage_count": len(skill_usage_list),
        "adopted_count": adopted_count,
        "skills": list(by_skill.values()),
    }
