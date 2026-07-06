"""P2-1: evaluation integrity validator — missing dimensions never default to pass.

Per design-coverage-gap-remediation-plan.md:233-255:

  1. Fix the missing schema package/import boundary or record a replacement
     disposition.
  2. Add tests proving absent code-review evidence is NOT_EVALUATED, BLOCKED,
     or equivalent, never PASS.
  3. Add subject snapshots, rubric versions, evaluation runs, observations,
     scorecards, improvement proposals, and promotion decisions only after the
     review lifecycle works.

Acceptance:
  - no missing dimension contributes to an aggregate score;
  - evaluation cannot override a blocked gate.
"""
from __future__ import annotations

from dataclasses import dataclass, field

VALID_EVALUATION_OUTCOMES = ("PASS", "FAIL", "NOT_EVALUATED", "BLOCKED")
PASS_EQUIVALENTS = ("PASS",)


@dataclass
class ValidationResult:
    valid: bool
    errors: list[str] = field(default_factory=list)

    def __bool__(self) -> bool:
        return self.valid


def _is_valid_evaluation_entry(
    entry: dict,
    collect_errors: bool = False,
) -> tuple[bool, list[str]]:
    """Base check: an evaluation entry must have valid shape.

    True only when:
      - id, evaluation_id, dimension, outcome all non-empty
      - outcome in VALID_EVALUATION_OUTCOMES
      - PASS/FAIL requires gate_ref to be non-empty (resolved later by caller)
      - if outcome is PASS_EQUIVALENT, must have evidence_refs non-empty
      - missing dimension (no evidence) -> NOT_EVALUATED or BLOCKED, never PASS
    """
    errors: list[str] = []
    eid = entry.get("id", "")
    prefix = f"evaluation[{eid or '<missing>'}]"

    for field in ("id", "evaluation_id", "dimension", "outcome"):
        if not entry.get(field):
            if collect_errors:
                errors.append(f"{prefix}: {field} is required")
            else:
                return False, errors

    outcome = entry.get("outcome", "")
    gate_ref = entry.get("gate_ref") or ""

    if outcome in ("PASS", "FAIL") and not gate_ref:
        if collect_errors:
            errors.append(
                f"{prefix}: outcome={outcome!r} requires gate_ref; "
                f"evaluated outcomes must reference a gate"
            )
        else:
            return False, errors

    if outcome not in VALID_EVALUATION_OUTCOMES:
        if collect_errors:
            errors.append(
                f"{prefix}: outcome={outcome!r} not in {VALID_EVALUATION_OUTCOMES}"
            )
        else:
            return False, errors

    evidence_refs = entry.get("evidence_refs") or []
    if outcome in PASS_EQUIVALENTS and not evidence_refs:
        if collect_errors:
            errors.append(
                f"{prefix}: outcome={outcome!r} but evidence_refs is empty; "
                f"PASS requires supporting evidence"
            )
        else:
            return False, errors

    if not evidence_refs and outcome not in ("NOT_EVALUATED", "BLOCKED"):
        if collect_errors:
            errors.append(
                f"{prefix}: no evidence_refs but outcome={outcome!r}; "
                f"missing dimensions must be NOT_EVALUATED or BLOCKED, never PASS or FAIL"
            )
        else:
            return False, errors

    return True, errors


def _is_valid_evaluation_evidence(
    entry: dict,
    evidence_by_id: dict,
    artifact_ids: set,
    collect_errors: bool = False,
) -> tuple[bool, list[str]]:
    """Validate that evaluation evidence refs resolve and support.

    True only when all evidence_refs:
      - resolve to declared evidence
      - have supports="supports"
      - source_artifact_id resolves to declared artifact
    """
    errors: list[str] = []
    eid = entry.get("id", "")
    prefix = f"evaluation[{eid or '<missing>'}]"
    evidence_refs = entry.get("evidence_refs") or []

    for ref_id in evidence_refs:
        ev = evidence_by_id.get(ref_id)
        if ev is None:
            if collect_errors:
                errors.append(
                    f"{prefix}: evidence_ref {ref_id!r} does not resolve"
                )
                continue
            return False, errors
        if ev.get("supports") != "supports":
            if collect_errors:
                errors.append(
                    f"{prefix}: evidence {ref_id!r} has supports="
                    f"{ev.get('supports')!r}; expected 'supports'"
                )
                continue
            return False, errors
        src = ev.get("source_artifact_id", "")
        if not src:
            if collect_errors:
                errors.append(
                    f"{prefix}: evidence {ref_id!r} has no source_artifact_id"
                )
                continue
            return False, errors
        if src not in artifact_ids:
            if collect_errors:
                errors.append(
                    f"{prefix}: evidence {ref_id!r} source_artifact_id="
                    f"{src!r} does not resolve to a declared artifact"
                )
                continue
            return False, errors

    return True, errors


def _check_gate_non_override(
    entry: dict,
    gate_by_id: dict,
    collect_errors: bool = False,
) -> tuple[bool, list[str]]:
    """An evaluation PASS cannot override a BLOCKED gate.

    gate_ref must resolve to a declared gate for both PASS and FAIL.
    BLOCKED override check applies only to PASS.
    """
    errors: list[str] = []
    eid = entry.get("id", "")
    prefix = f"evaluation[{eid or '<missing>'}]"
    gate_ref = entry.get("gate_ref") or ""
    outcome = entry.get("outcome", "")

    if outcome not in ("PASS", "FAIL"):
        return True, errors
    if not gate_ref:
        # Already caught by _is_valid_evaluation_entry for PASS/FAIL
        return True, errors

    gate = gate_by_id.get(gate_ref)
    if gate is None:
        if collect_errors:
            errors.append(
                f"{prefix}: gate_ref={gate_ref!r} does not resolve "
                f"to a declared gate"
            )
        return False, errors

    if outcome == "PASS" and gate.get("outcome") == "BLOCKED":
        if collect_errors:
            errors.append(
                f"{prefix}: outcome=PASS but referenced gate {gate_ref!r} "
                f"is BLOCKED; evaluation cannot override a blocked gate"
            )
        else:
            return False, errors

    return True, errors


def validate_evaluation_integrity(payload: dict) -> ValidationResult:
    errors: list[str] = []

    entries: list[dict] = payload.get("evaluations") or []
    evidence: list[dict] = payload.get("evidence") or []
    artifacts: list[dict] = payload.get("artifacts") or []
    gates: list[dict] = payload.get("gates") or []

    evidence_by_id = {e.get("id"): e for e in evidence if e.get("id")}
    artifact_ids = {a.get("id") for a in artifacts if a.get("id")}
    gate_by_id = {g.get("id"): g for g in gates if g.get("id")}

    for entry in entries:
        base_ok, base_errors = _is_valid_evaluation_entry(entry, collect_errors=True)
        errors.extend(base_errors)

        if not base_ok:
            continue

        _, ev_errors = _is_valid_evaluation_evidence(
            entry, evidence_by_id, artifact_ids, collect_errors=True,
        )
        errors.extend(ev_errors)

        _, gate_errors = _check_gate_non_override(
            entry, gate_by_id, collect_errors=True,
        )
        errors.extend(gate_errors)

    return ValidationResult(valid=len(errors) == 0, errors=errors)


def derive_evaluation_integrity(payload: dict) -> dict:
    entries: list[dict] = payload.get("evaluations") or []
    evidence: list[dict] = payload.get("evidence") or []
    artifacts: list[dict] = payload.get("artifacts") or []
    gates: list[dict] = payload.get("gates") or []

    evidence_by_id = {e.get("id"): e for e in evidence if e.get("id")}
    artifact_ids = {a.get("id") for a in artifacts if a.get("id")}
    gate_by_id = {g.get("id"): g for g in gates if g.get("id")}

    total = len(entries)
    pass_count = 0
    fail_count = 0
    not_evaluated_count = 0
    blocked_count = 0
    by_dimension: dict[str, dict] = {}

    for entry in entries:
        dim = entry.get("dimension", "")
        if dim not in by_dimension:
            by_dimension[dim] = {
                "dimension": dim,
                "total": 0,
                "pass": 0,
                "fail": 0,
                "not_evaluated": 0,
                "blocked": 0,
            }

        base_ok, _ = _is_valid_evaluation_entry(entry, collect_errors=False)
        if not base_ok:
            continue

        ev_ok, _ = _is_valid_evaluation_evidence(
            entry, evidence_by_id, artifact_ids, collect_errors=False,
        )
        gate_ok, _ = _check_gate_non_override(
            entry, gate_by_id, collect_errors=False,
        )
        is_valid = base_ok and ev_ok and gate_ok

        outcome = entry.get("outcome", "")
        if is_valid:
            if outcome == "PASS":
                pass_count += 1
            elif outcome == "FAIL":
                fail_count += 1
            elif outcome == "NOT_EVALUATED":
                not_evaluated_count += 1
            elif outcome == "BLOCKED":
                blocked_count += 1

        by_dimension[dim]["total"] += 1
        if is_valid and outcome == "PASS":
            by_dimension[dim]["pass"] += 1
        elif is_valid and outcome == "FAIL":
            by_dimension[dim]["fail"] += 1
        elif is_valid and outcome == "NOT_EVALUATED":
            by_dimension[dim]["not_evaluated"] += 1
        elif is_valid and outcome == "BLOCKED":
            by_dimension[dim]["blocked"] += 1

    return {
        "total": total,
        "pass_count": pass_count,
        "fail_count": fail_count,
        "not_evaluated_count": not_evaluated_count,
        "blocked_count": blocked_count,
        "by_dimension": by_dimension,
    }
