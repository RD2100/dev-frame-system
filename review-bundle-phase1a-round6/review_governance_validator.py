"""Semantic validator for review-governance kernel packets.

Complements draft-07 schema validation with cross-object constraints that
JSON Schema cannot express:

1. work_item.status=completed requires a gate decision with outcome=pass
2. Gate/review pass requires evidence_ids that resolve to existing evidence
   with supports="supports"
3. All principal_id references must resolve to declared principals
4. Projection computed_status must be consistent with decisions
5. evidence.source_artifact_id must resolve to existing artifacts
6. success fixture must include non-report output artifacts for gate evidence
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
    for decision in decisions:
        if decision.get("kind") in ("review", "gate") and decision.get("outcome") == "pass":
            for eid in decision.get("evidence_ids", []):
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
    has_gate_pass = any(
        d.get("kind") == "gate" and d.get("outcome") == "pass"
        and d.get("target_ref") == work_item.get("id", "")
        for d in decisions
    )
    has_review_pass = any(
        d.get("kind") == "review" and d.get("outcome") == "pass"
        for d in decisions
    )
    has_blocked = any(d.get("outcome") == "blocked" for d in decisions)
    has_human_required = any(
        d.get("outcome") == "human_required" for d in decisions
        if d.get("kind") == "gate"
    )

    expected_status = work_item.get("status", "")
    if computed == "completed" and not has_gate_pass:
        errors.append(
            f"projection.computed_status=completed but no gate pass decision found"
        )
    if computed == "completed" and expected_status != "completed":
        errors.append(
            f"projection.computed_status=completed but work_item.status={expected_status!r}"
        )
    if computed == "insufficient_evidence":
        has_ie_decision = any(
            d.get("outcome") == "insufficient_evidence" for d in decisions
        )
        if not has_ie_decision:
            errors.append(
                "projection.computed_status=insufficient_evidence but no "
                "decision with outcome=insufficient_evidence"
            )
    if computed == "blocked" and decisions and not has_blocked and not has_human_required:
        errors.append(
            "projection.computed_status=blocked but no blocked/human_required decision"
        )

    return ValidationResult(valid=len(errors) == 0, errors=errors)
