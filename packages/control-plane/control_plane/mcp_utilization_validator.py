"""Phase 4c: MCP offline utilization ledger validator.

An `mcp_utilization` record accounts for an MCP server/tool call so it can be
audited offline — no live dashboard required. Per the plan
(skill-asset-utilization-plan.md:246, document-driven plan:216), each record
links session, tool, consent, result, and downstream artifact.

It is NOT standalone authority. It must point to:

  - MCP-specific scalars: session_id, tool_id, consent_id, result_artifact
  - produced_artifact resolving to a declared artifact
  - evidence_ids non-empty + each resolves + supports="supports" +
    source_artifact_id resolves to a declared artifact
  - gate_decision required, evidence-backed (kind="gate", outcome="pass",
    target_ref == record id, evidence coverage of record evidence_ids)

`promotion_state="adopted"` is only valid when the full gate chain passes.

The adoption judgment is centralized in `_is_valid_gate_adoption()` and base
eligibility in `_is_valid_mcp_base()`. Both `validate_mcp_utilization()` and
`derive_mcp_utilization()` build on the SAME helpers, so projection never
invents adoption that the validator would reject.
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
    "session_id",
    "tool_id",
    "consent_id",
    "result_artifact",
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


def _required_value(value):
    if isinstance(value, str):
        return value.strip()
    return value


def _has_required_value(value) -> bool:
    return bool(_required_value(value))


def _id_set(records: list[dict]) -> set:
    return {
        _required_value(record.get("id"))
        for record in records
        if _has_required_value(record.get("id"))
    }


def _id_map(records: list[dict]) -> dict:
    return {
        _required_value(record.get("id")): record
        for record in records
        if _has_required_value(record.get("id"))
    }


def _is_valid_mcp_base(
    mu: dict,
    evidence_by_id: dict,
    artifact_ids: set,
    collect_errors: bool = False,
) -> tuple[bool, list[str]]:
    """Base eligibility: required scalars + produced_artifact resolution +
    result_artifact resolution + evidence chain. Ignores the gate decision.

    True only when ALL hold:
      - all required scalar fields are non-empty (incl. session_id, tool_id,
        consent_id, result_artifact, gate_decision)
      - produced_artifact is non-empty and resolves to a declared artifact
      - result_artifact is non-empty and resolves to a declared artifact
      - evidence_ids is non-empty
      - every evidence resolves, supports="supports", source_artifact_id
        resolves to a declared artifact
    """
    errors: list[str] = []
    valid = True
    mu_id = _required_value(mu.get("id", ""))
    produced_artifact = _required_value(mu.get("produced_artifact", ""))
    result_artifact = _required_value(mu.get("result_artifact", ""))
    evidence_ids = mu.get("evidence_ids") or []
    promotion_state = _required_value(mu.get("promotion_state", ""))
    prefix = f"mcp_utilization[{mu_id or '<missing id>'}]"

    for field_name in REQUIRED_SCALAR_FIELDS:
        if not _has_required_value(mu.get(field_name, "")):
            valid = False
            if collect_errors:
                errors.append(f"{prefix}: {field_name} is required")
            else:
                return False, errors

    if not _has_required_value(produced_artifact):
        valid = False
        if collect_errors:
            errors.append(f"{prefix}: produced_artifact is required")
        else:
            return False, errors
    elif produced_artifact not in artifact_ids:
        valid = False
        if collect_errors:
            errors.append(
                f"{prefix}: produced_artifact {produced_artifact!r} "
                f"does not resolve to a declared artifact"
            )
        else:
            return False, errors

    if not _has_required_value(result_artifact):
        valid = False
        if collect_errors:
            errors.append(f"{prefix}: result_artifact is required")
        else:
            return False, errors
    elif result_artifact not in artifact_ids:
        valid = False
        if collect_errors:
            errors.append(
                f"{prefix}: result_artifact {result_artifact!r} "
                f"does not resolve to a declared artifact"
            )
        else:
            return False, errors

    if (
        _has_required_value(result_artifact)
        and _has_required_value(produced_artifact)
        and result_artifact == produced_artifact
    ):
        valid = False
        if collect_errors:
            errors.append(
                f"{prefix}: result_artifact {result_artifact!r} must be "
                f"distinct from produced_artifact"
            )
        else:
            return False, errors

    if not evidence_ids:
        valid = False
        if collect_errors:
            errors.append(
                f"{prefix}: evidence_ids must include at least one "
                f"supporting evidence_id (standalone authority forbidden)"
            )
        else:
            return False, errors

    for raw_eid in evidence_ids:
        if not _has_required_value(raw_eid):
            valid = False
            if collect_errors:
                errors.append(f"{prefix}: evidence_id is required")
                continue
            return False, errors
        eid = _required_value(raw_eid)
        ev = evidence_by_id.get(eid)
        if ev is None:
            valid = False
            if collect_errors:
                errors.append(
                    f"{prefix}: evidence_id {eid!r} does not resolve "
                    f"to declared evidence"
                )
                continue
            return False, errors
        if ev.get("supports") != "supports":
            valid = False
            if collect_errors:
                errors.append(
                    f"{prefix}: evidence_id {eid!r} has supports="
                    f"{ev.get('supports')!r}; only supports='supports' counts"
                )
                continue
            return False, errors
        src = _required_value(ev.get("source_artifact_id", ""))
        if not _has_required_value(src):
            valid = False
            if collect_errors:
                errors.append(
                    f"{prefix}: evidence {eid!r} has no source_artifact_id"
                )
                continue
            return False, errors
        if src not in artifact_ids:
            valid = False
            if collect_errors:
                errors.append(
                    f"{prefix}: evidence {eid!r} source_artifact_id={src!r} "
                    f"does not resolve to a declared artifact"
                )
                continue
            return False, errors

    if promotion_state and promotion_state not in VALID_PROMOTION_STATES:
        valid = False
        if collect_errors:
            errors.append(
                f"{prefix}: promotion_state {promotion_state!r} is not in "
                f"valid set {VALID_PROMOTION_STATES}"
            )
        else:
            return False, errors

    return valid, errors


def _is_valid_gate_adoption(
    mu: dict,
    decision_by_id: dict,
    evidence_by_id: dict,
    artifact_ids: set,
    collect_errors: bool = False,
) -> tuple[bool, list[str]]:
    """Full gate-adoption judgment for an MCP utilization record.

    True only when ALL hold:
      - base eligibility holds
      - gate_decision resolves to a declared decision
      - decision.kind == "gate"
      - decision.outcome == "pass"
      - decision.target_ref == mu["id"]
      - decision.evidence_ids is non-empty
      - every decision.evidence_id resolves, supports="supports",
        source_artifact_id resolves to a declared artifact
      - decision.evidence_ids ⊇ mu.evidence_ids
    """
    errors: list[str] = []
    mu_id = _required_value(mu.get("id", ""))
    evidence_ids = mu.get("evidence_ids") or []
    gate_decision = _required_value(mu.get("gate_decision", "") or "")
    prefix = f"mcp_utilization[{mu_id or '<missing id>'}]"

    if not _has_required_value(gate_decision):
        return False, errors  # required-scalar error surfaced by base helper

    base_ok, base_errors = _is_valid_mcp_base(
        mu, evidence_by_id, artifact_ids, collect_errors=collect_errors
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

    dec_kind = _required_value(dec.get("kind", ""))
    dec_outcome = _required_value(dec.get("outcome", ""))
    dec_target_ref = _required_value(dec.get("target_ref", ""))
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
    if not _has_required_value(mu_id):
        return False, errors
    if dec_target_ref != mu_id:
        if collect_errors:
            errors.append(
                f"{prefix}: gate decision {gate_decision!r} "
                f"has target_ref={dec_target_ref!r}; must equal mcp_utilization "
                f"id {mu_id!r}"
            )
        return False, errors
    if not dec_evidence_ids:
        if collect_errors:
            errors.append(
                f"{prefix}: gate decision {gate_decision!r} "
                f"has no evidence_ids; adoption must be evidence-backed"
            )
        return False, errors

    normalized_dec_evidence_ids = []
    for raw_eid in dec_evidence_ids:
        if not _has_required_value(raw_eid):
            if collect_errors:
                errors.append(
                    f"{prefix}: gate decision {gate_decision!r} "
                    f"evidence_id is required"
                )
                continue
            return False, errors
        eid = _required_value(raw_eid)
        normalized_dec_evidence_ids.append(eid)
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
        dsrc = _required_value(ev.get("source_artifact_id", ""))
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

    normalized_evidence_ids = [
        _required_value(eid) for eid in evidence_ids if _has_required_value(eid)
    ]
    if not set(normalized_evidence_ids).issubset(set(normalized_dec_evidence_ids)):
        if collect_errors:
            missing = set(normalized_evidence_ids) - set(normalized_dec_evidence_ids)
            errors.append(
                f"{prefix}: gate decision {gate_decision!r} "
                f"evidence_ids must cover record evidence_ids; missing: "
                f"{sorted(missing)}"
            )
        return False, errors

    return True, errors


def validate_mcp_utilization(payload: dict) -> ValidationResult:
    """Validate that mcp_utilization records link session, tool, consent,
    result, and downstream artifact, and point to existing evidence and
    evidence-backed gate decisions. promotion_state="adopted" requires a
    valid passing gate chain.
    """
    errors: list[str] = []

    mu_list: list[dict] = payload.get("mcp_utilization") or []
    artifacts: list[dict] = payload.get("artifacts") or []
    evidence: list[dict] = payload.get("evidence") or []
    decisions: list[dict] = payload.get("decisions") or []

    artifact_ids = _id_set(artifacts)
    evidence_by_id = _id_map(evidence)
    decision_by_id = _id_map(decisions)

    for mu in mu_list:
        mu_id = _required_value(mu.get("id", ""))
        gate_decision = _required_value(mu.get("gate_decision", "") or "")
        promotion_state = _required_value(mu.get("promotion_state", "") or "")
        prefix = f"mcp_utilization[{mu_id or '<missing id>'}]"

        # Base eligibility (required scalars + produced_artifact + result_artifact
        # + evidence chain). When a gate_decision is present, the gate helper
        # also calls base and surfaces its errors, so we only call base
        # independently when there is no gate_decision to avoid duplicate errors.
        if _has_required_value(gate_decision):
            gate_ok, gate_errors = _is_valid_gate_adoption(
                mu, decision_by_id, evidence_by_id, artifact_ids,
                collect_errors=True,
            )
            errors.extend(gate_errors)
            if promotion_state == "adopted" and not gate_ok:
                errors.append(
                    f"{prefix}: promotion_state='adopted' requires a valid "
                    f"evidence-backed gate decision with outcome='pass'"
                )
        else:
            _, base_errors = _is_valid_mcp_base(
                mu, evidence_by_id, artifact_ids, collect_errors=True
            )
            errors.extend(base_errors)

    return ValidationResult(valid=len(errors) == 0, errors=errors)


def derive_mcp_utilization(payload: dict) -> dict:
    """Read-only projection: count valid MCP utilization and adoptions by tool.

    Does NOT invent authority — adoption only counts when the FULL gate
    adoption chain is valid, via _is_valid_gate_adoption() (which includes
    base eligibility + gate decision kind/outcome/target_ref + evidence chain
    + coverage). Invalid records are not counted as utilized.
    """
    mu_list: list[dict] = payload.get("mcp_utilization") or []
    decisions: list[dict] = payload.get("decisions") or []
    evidence: list[dict] = payload.get("evidence") or []
    artifacts: list[dict] = payload.get("artifacts") or []
    decision_by_id = _id_map(decisions)
    evidence_by_id = _id_map(evidence)
    artifact_ids = _id_set(artifacts)

    utilized_count = 0
    adopted_count = 0
    by_tool_id: dict[str, dict] = {}

    for mu in mu_list:
        gate_ok, _ = _is_valid_gate_adoption(
            mu, decision_by_id, evidence_by_id, artifact_ids,
            collect_errors=False,
        )
        if not gate_ok:
            continue

        utilized_count += 1
        tool_id = _required_value(mu.get("tool_id", ""))
        promotion_state = _required_value(mu.get("promotion_state", ""))
        is_adopted = promotion_state == "adopted"
        if is_adopted:
            adopted_count += 1

        if tool_id not in by_tool_id:
            by_tool_id[tool_id] = {
                "tool_id": tool_id,
                "count": 0,
                "adopted_count": 0,
            }
        by_tool_id[tool_id]["count"] += 1
        if is_adopted:
            by_tool_id[tool_id]["adopted_count"] += 1

    return {
        "mcp_utilization_count": utilized_count,
        "adopted_count": adopted_count,
        "by_tool_id": by_tool_id,
    }
