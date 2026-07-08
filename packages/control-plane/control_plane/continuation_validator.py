"""Phase 5: continuation boundary validator.

A `continuation` decision authorizes the system to proceed from one work
phase to the next. It is NOT a persistent supervisor — each continuation is
a one-shot gate decision under declared scope, policy, evidence, and context
boundaries.

Plan (document-driven-transformation-final-plan-20260705.md:224-231):
"After gates work, introduce higher-power continuation only as explicit gate
decisions under declared scope, policy, evidence, and context boundaries.
Goal-bound continuation is not a persistent supervisor."

A continuation decision is valid only when ALL hold:
  - kind == "continue"
  - outcome == "pass"
  - scope_from and scope_to are declared (non-empty)
  - policy_ref resolves to a declared artifact
  - evidence-backed (evidence_ids non-empty + each resolves + supports +
    source_artifact resolves)
  - prior_gate_ref resolves to a gate decision with outcome="pass" and
    evidence backing
  - max_iterations > 0 (finite — not a persistent supervisor)

Shared helpers (_is_valid_continuation_base + _is_valid_prior_gate) are
used by both validate_continuation() and derive_continuation() to prevent
projection divergence.
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
    "scope_from",
    "scope_to",
    "policy_ref",
    "prior_gate_ref",
    "max_iterations",
    "decided_at",
    "decider_principal_id",
)


def _has_required_value(value: object) -> bool:
    if isinstance(value, str):
        return bool(value.strip())
    return bool(value)


def _is_valid_continuation_base(
    cont: dict,
    evidence_by_id: dict,
    artifact_ids: set,
    collect_errors: bool = False,
) -> tuple[bool, list[str]]:
    """Base eligibility: does the continuation decision have valid shape?

    True only when ALL hold:
      - kind == "continue"
      - outcome == "pass"
      - all required scalar fields non-empty
      - max_iterations > 0 (finite continuation, not persistent supervisor)
      - policy_ref resolves to a declared artifact
      - evidence_ids non-empty + each resolves + supports + source_artifact resolves
    """
    errors: list[str] = []
    cont_id = cont.get("id", "")
    prefix = f"continuation[{cont_id or '<missing id>'}]"

    kind = cont.get("kind", "")
    outcome = cont.get("outcome", "")
    max_iterations = cont.get("max_iterations")
    policy_ref = cont.get("policy_ref", "")
    evidence_ids = cont.get("evidence_ids") or []

    if kind != "continue":
        if collect_errors:
            errors.append(
                f"{prefix}: kind={kind!r}; must be kind='continue'"
            )
        else:
            return False, errors

    if outcome != "pass":
        if collect_errors:
            errors.append(
                f"{prefix}: outcome={outcome!r}; must be outcome='pass'"
            )
        else:
            return False, errors

    for field_name in REQUIRED_SCALAR_FIELDS:
        val = cont.get(field_name)
        if not _has_required_value(val):
            if collect_errors:
                errors.append(f"{prefix}: {field_name} is required")
            else:
                return False, errors

    if not isinstance(max_iterations, int) or isinstance(max_iterations, bool) or max_iterations <= 0:
        if collect_errors:
            if max_iterations == -1:
                errors.append(
                    f"{prefix}: max_iterations=-1 (persistent supervisor) "
                    f"is forbidden; continuation must be finite"
                )
            else:
                errors.append(
                    f"{prefix}: max_iterations must be a positive integer; "
                    f"got {max_iterations!r}"
                )
        else:
            return False, errors

    if not _has_required_value(policy_ref):
        if collect_errors:
            errors.append(f"{prefix}: policy_ref is required")
        else:
            return False, errors
    elif policy_ref not in artifact_ids:
        if collect_errors:
            errors.append(
                f"{prefix}: policy_ref {policy_ref!r} does not resolve "
                f"to a declared artifact"
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
                errors.append(f"{prefix}: evidence_id is required")
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

    return True, errors


def _is_valid_prior_gate(
    cont: dict,
    decision_by_id: dict,
    evidence_by_id: dict,
    artifact_ids: set,
    collect_errors: bool = False,
) -> tuple[bool, list[str]]:
    """Validate that the prior gate referenced by this continuation is valid.

    True only when ALL hold:
      - prior_gate_ref resolves to a declared decision
      - decision.kind == "gate"
      - decision.outcome == "pass"
      - decision is evidence-backed (evidence_ids non-empty AND each resolves
        + supports="supports" + source_artifact_id resolves to declared artifact)
    """
    errors: list[str] = []
    cont_id = cont.get("id", "")
    prior_gate_ref = cont.get("prior_gate_ref", "")
    prefix = f"continuation[{cont_id or '<missing id>'}]"
    cont_project_id = cont.get("project_id", "")
    cont_scope_from = cont.get("scope_from", "")

    if not _has_required_value(prior_gate_ref):
        return False, errors  # caught by base scalars

    gate = decision_by_id.get(prior_gate_ref)
    if gate is None:
        if collect_errors:
            errors.append(
                f"{prefix}: prior_gate_ref {prior_gate_ref!r} does not "
                f"resolve to a declared decision"
            )
        return False, errors

    gate_kind = gate.get("kind", "")
    gate_outcome = gate.get("outcome", "")
    gate_evidence_ids = gate.get("evidence_ids") or []
    gate_project_id = gate.get("project_id", "")
    gate_target_ref = gate.get("target_ref", "")

    if gate_project_id != cont_project_id:
        if collect_errors:
            errors.append(
                f"{prefix}: prior gate {prior_gate_ref!r} has "
                f"project_id={gate_project_id!r}; must match continuation "
                f"project_id={cont_project_id!r}"
            )
        else:
            return False, errors
    if gate_target_ref != cont_scope_from:
        if collect_errors:
            errors.append(
                f"{prefix}: prior gate {prior_gate_ref!r} has "
                f"target_ref={gate_target_ref!r}; must match continuation "
                f"scope_from={cont_scope_from!r}"
            )
        else:
            return False, errors

    if gate_kind != "gate":
        if collect_errors:
            errors.append(
                f"{prefix}: prior gate {prior_gate_ref!r} has "
                f"kind={gate_kind!r}; must be kind='gate'"
            )
        return False, errors
    if gate_outcome != "pass":
        if collect_errors:
            errors.append(
                f"{prefix}: prior gate {prior_gate_ref!r} has "
                f"outcome={gate_outcome!r}; must be outcome='pass'"
            )
        return False, errors
    if not gate_evidence_ids:
        if collect_errors:
            errors.append(
                f"{prefix}: prior gate {prior_gate_ref!r} has no "
                f"evidence_ids; prior gate must be evidence-backed"
            )
        return False, errors

    for eid in gate_evidence_ids:
        if not _has_required_value(eid):
            if collect_errors:
                errors.append(
                    f"{prefix}: prior gate {prior_gate_ref!r} evidence_id "
                    f"is required"
                )
                continue
            return False, errors
        ev = evidence_by_id.get(eid)
        if ev is None:
            if collect_errors:
                errors.append(
                    f"{prefix}: prior gate {prior_gate_ref!r} evidence_id "
                    f"{eid!r} does not resolve to declared evidence"
                )
                continue
            return False, errors
        if ev.get("supports") != "supports":
            if collect_errors:
                errors.append(
                    f"{prefix}: prior gate {prior_gate_ref!r} evidence "
                    f"{eid!r} has supports={ev.get('supports')!r}; only "
                    f"supports='supports' counts"
                )
                continue
            return False, errors
        src = ev.get("source_artifact_id", "")
        if not _has_required_value(src):
            if collect_errors:
                errors.append(
                    f"{prefix}: prior gate {prior_gate_ref!r} evidence "
                    f"{eid!r} has no source_artifact_id"
                )
                continue
            return False, errors
        if src not in artifact_ids:
            if collect_errors:
                errors.append(
                    f"{prefix}: prior gate {prior_gate_ref!r} evidence "
                    f"{eid!r} source_artifact_id={src!r} does not resolve "
                    f"to a declared artifact"
                )
                continue
            return False, errors

    return True, errors


def _is_valid_continuation(
    cont: dict,
    decision_by_id: dict,
    evidence_by_id: dict,
    artifact_ids: set,
    collect_errors: bool = False,
) -> tuple[bool, list[str]]:
    """Full continuation judgment.

    True only when ALL hold:
      - base eligibility (kind/outcome/scalars/max_iterations/policy/evidence)
      - prior gate is valid (resolves, kind=gate, outcome=pass, evidence-backed)
    """
    errors: list[str] = []

    base_ok, base_errors = _is_valid_continuation_base(
        cont, evidence_by_id, artifact_ids, collect_errors=collect_errors
    )
    if collect_errors:
        errors.extend(base_errors)
    if not base_ok:
        return False, errors

    gate_ok, gate_errors = _is_valid_prior_gate(
        cont, decision_by_id, evidence_by_id, artifact_ids,
        collect_errors=collect_errors
    )
    if collect_errors:
        errors.extend(gate_errors)
    if not gate_ok:
        return False, errors

    return True, errors


def validate_continuation(payload: dict) -> ValidationResult:
    """Validate that continuation decisions are evidence-backed, scoped,
    finite, and cite a valid prior gate decision.

    Continuation is not a persistent supervisor — max_iterations must be
    positive and finite.
    """
    errors: list[str] = []

    cont_list: list[dict] = payload.get("continuation") or []
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

    for cont in cont_list:
        _, cont_errors = _is_valid_continuation(
            cont, decision_by_id, evidence_by_id, artifact_ids,
            collect_errors=True,
        )
        errors.extend(cont_errors)

    return ValidationResult(valid=len(errors) == 0, errors=errors)


def derive_continuation(payload: dict) -> dict:
    """Read-only projection: count continuations and active (valid) ones.

    Does NOT invent authority — a continuation is only counted as active
    when the FULL validation chain passes (base eligibility + prior gate).

    Persistent supervisors (max_iterations <= 0) are excluded.
    """
    cont_list: list[dict] = payload.get("continuation") or []
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

    active_count = 0
    by_scope: dict[str, dict] = {}

    for cont in cont_list:
        scope_to = cont.get("scope_to", "")
        is_valid, _ = _is_valid_continuation(
            cont, decision_by_id, evidence_by_id, artifact_ids,
            collect_errors=False,
        )
        if is_valid:
            active_count += 1

        if scope_to not in by_scope:
            by_scope[scope_to] = {
                "scope_to": scope_to,
                "count": 0,
                "active_count": 0,
            }
        by_scope[scope_to]["count"] += 1
        if is_valid:
            by_scope[scope_to]["active_count"] += 1

    return {
        "continuation_count": len(cont_list),
        "active_count": active_count,
        "by_scope": by_scope,
    }
