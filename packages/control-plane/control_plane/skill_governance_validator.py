"""P1-2: skill governance validator — fingerprints and promotion history.

Per design-coverage-gap-remediation-plan.md:175-193:

  1. Add a skill content fingerprint record that includes SKILL.md and
     relevant bundled references.
  2. Add revision and promotion metadata for custom/project skills.
  3. Tie future evaluation findings to proposed skill revisions, not just
     skill IDs.

Acceptance:
  - the same skill ID with changed content has a different fingerprint;
  - a learning proposal cannot update a skill without regression evidence
    and a promotion decision.
"""
from __future__ import annotations

from dataclasses import dataclass, field

VALID_PROMOTION_STATES = ("pending", "candidate", "adopted", "deprecated", "rejected")


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


def _canonical_skill_id(value: object) -> str:
    if isinstance(value, str):
        return value.strip()
    return str(value)


def _is_valid_skill_base(
    entry: dict,
    collect_errors: bool = False,
) -> tuple[bool, list[str]]:
    """Check fields required for any skill entry to be considered valid."""
    errors: list[str] = []
    skill_id = entry.get("skill_id", "")
    prefix = f"skill_governance[{skill_id or '<missing>'}]"

    for field in ("skill_id", "fingerprint", "source_path"):
        if not _has_required_value(entry.get(field)):
            if collect_errors:
                errors.append(f"{prefix}: {field} is required")
            else:
                return False, errors

    rev = entry.get("revision")
    if not isinstance(rev, int) or isinstance(rev, bool) or rev < 1:
        if collect_errors:
            errors.append(
                f"{prefix}: revision must be a positive integer, got {rev!r}"
            )
        else:
            return False, errors

    ps = entry.get("promotion_state", "")
    if ps and ps not in VALID_PROMOTION_STATES:
        if collect_errors:
            errors.append(
                f"{prefix}: promotion_state {ps!r} not in "
                f"{VALID_PROMOTION_STATES}"
            )
        else:
            return False, errors

    return len(errors) == 0, errors


def _check_fingerprint_uniqueness(
    entries: list[dict],
    collect_errors: bool = False,
) -> tuple[bool, list[str]]:
    """Per-skill_id uniqueness rules for (revision, fingerprint) pairs."""
    errors: list[str] = []
    seen: dict[str, dict[int, dict]] = {}  # skill_id -> {revision: entry}

    for e in entries:
        raw_sid = e.get("skill_id", "")
        rev = e.get("revision")
        fp = e.get("fingerprint", "")
        if not _has_required_value(raw_sid) or rev is None:
            continue
        if not isinstance(rev, int) or isinstance(rev, bool) or rev < 1:
            continue
        sid = _canonical_skill_id(raw_sid)
        if sid not in seen:
            seen[sid] = {}
        if rev in seen[sid]:
            existing = seen[sid][rev]
            existing_fp = existing.get("fingerprint", "")
            if fp != existing_fp:
                key_e = (
                    f"skill_governance: skill_id={sid!r} revision={rev}: "
                    f"conflicting fingerprints {existing_fp!r} vs {fp!r}"
                )
                if collect_errors:
                    errors.append(key_e)
                else:
                    return False, errors
            else:
                key_e = (
                    f"skill_governance: skill_id={sid!r} revision={rev}: "
                    f"duplicate entry (same revision and fingerprint)"
                )
                if collect_errors:
                    errors.append(key_e)
                else:
                    return False, errors
        seen[sid][rev] = e

    # Check: different revision, same fingerprint — content didn't change
    for sid, by_rev in seen.items():
        fps: dict[str, int] = {}
        for rev in sorted(by_rev):
            fp = by_rev[rev].get("fingerprint", "")
            if fp in fps:
                if collect_errors:
                    errors.append(
                        "skill_governance: skill_id=%r revision=%d "
                        "fingerprint unchanged from revision=%d; "
                        "revision bump requires content change"
                        % (sid, rev, fps[fp])
                    )
                else:
                    return False, errors
            else:
                fps[fp] = rev

    return True, errors


def _is_valid_adoption_decision(
    entry: dict,
    decision_by_id: dict,
    evidence_by_id: dict,
    artifact_ids: set,
    revision_counts: dict[str, int],
    collect_errors: bool = False,
) -> tuple[bool, list[str]]:
    """Validate the adoption/promotion decision chain for a skill entry.

    Only reaches the decision-chain checks when the entry has base validity
    and an adopted_by_decision_id — callers must do that gate first so
    that validate and derive share the same logic.

    When a skill has multiple revisions in the packet, the adoption decision
    must use a revision-scoped target_ref (e.g. "skill-a@rev:2") rather than
    a plain skill_id so that the authority is bound to a specific revision.
    """
    errors: list[str] = []
    raw_skill_id = entry.get("skill_id", "")
    skill_id = _canonical_skill_id(raw_skill_id)
    adopted_by = entry.get("adopted_by_decision_id") or ""
    prefix = f"skill_governance[{raw_skill_id or '<missing>'}]"

    if not _has_required_value(adopted_by):
        return True, errors

    dec = decision_by_id.get(adopted_by)
    if dec is None:
        if collect_errors:
            errors.append(
                f"{prefix}: adopted_by_decision_id {adopted_by!r} "
                f"does not resolve to a declared decision"
            )
        return False, errors

    dec_kind = dec.get("kind", "")
    dec_outcome = dec.get("outcome", "")
    dec_target_ref = _canonical_skill_id(dec.get("target_ref", ""))
    dec_evidence_ids = dec.get("evidence_ids") or []

    if dec_kind not in ("adopt", "promote"):
        if collect_errors:
            errors.append(
                f"{prefix}: adopting decision {adopted_by!r} "
                f"has kind={dec_kind!r}; must be 'adopt' or 'promote'"
            )
        return False, errors
    if dec_outcome != "pass":
        if collect_errors:
            errors.append(
                f"{prefix}: adopting decision {adopted_by!r} "
                f"has outcome={dec_outcome!r}; must be 'pass'"
            )
        return False, errors

    revision = entry.get("revision")
    scoped_ref = f"{skill_id}@rev:{revision}"
    multi_revision = revision_counts.get(skill_id, 0) > 1

    if dec_target_ref != scoped_ref:
        if multi_revision and dec_target_ref == skill_id:
            if collect_errors:
                errors.append(
                    f"{prefix}: adopting decision {adopted_by!r} "
                    f"has plain target_ref={dec_target_ref!r}; when "
                    f"skill_id={skill_id!r} has multiple revisions "
                    f"({revision_counts[skill_id]}), target_ref must be "
                    f"revision-scoped like {scoped_ref!r}"
                )
            return False, errors
        if dec_target_ref != skill_id:
            if collect_errors:
                errors.append(
                    f"{prefix}: adopting decision {adopted_by!r} "
                    f"has target_ref={dec_target_ref!r}; must equal "
                    f"skill_id={skill_id!r} or revision-scoped "
                    f"{scoped_ref!r}"
                )
            return False, errors
    if not dec_evidence_ids:
        if collect_errors:
            errors.append(
                f"{prefix}: adopting decision {adopted_by!r} "
                f"has no evidence_ids; adoption must be evidence-backed"
            )
        return False, errors

    for eid in dec_evidence_ids:
        ev = evidence_by_id.get(eid)
        if ev is None:
            if collect_errors:
                errors.append(
                    f"{prefix}: adopting decision {adopted_by!r} "
                    f"references missing evidence_id {eid!r}"
                )
                continue
            return False, errors
        if ev.get("supports") != "supports":
            if collect_errors:
                errors.append(
                    f"{prefix}: adopting decision {adopted_by!r} "
                    f"references evidence {eid!r} with supports="
                    f"{ev.get('supports')!r}; expected 'supports'"
                )
                continue
            return False, errors
        src = ev.get("source_artifact_id", "")
        if not _has_required_value(src):
            if collect_errors:
                errors.append(
                    f"{prefix}: adopting decision {adopted_by!r} "
                    f"evidence {eid!r} has no source_artifact_id"
                )
                continue
            return False, errors
        if src not in artifact_ids:
            if collect_errors:
                errors.append(
                    f"{prefix}: adopting decision {adopted_by!r} "
                    f"evidence {eid!r} source_artifact_id={src!r} "
                    f"does not resolve to a declared artifact"
                )
                continue
            return False, errors

    return True, errors


def validate_skill_governance(payload: dict) -> ValidationResult:
    errors: list[str] = []

    entries: list[dict] = payload.get("skill_registry") or []
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

    revision_counts: dict[str, int] = {}
    for e in entries:
        raw_sid = e.get("skill_id", "")
        if _has_required_value(raw_sid):
            sid = _canonical_skill_id(raw_sid)
            revision_counts[sid] = revision_counts.get(sid, 0) + 1

    for e in entries:
        skill_id = e.get("skill_id", "")
        prefix = f"skill_governance[{skill_id or '<missing>'}]"

        base_ok, base_errors = _is_valid_skill_base(e, collect_errors=True)
        errors.extend(base_errors)

        ps = e.get("promotion_state", "")
        adopted_by = e.get("adopted_by_decision_id") or ""

        if ps == "adopted" and not _has_required_value(adopted_by):
            errors.append(
                f"{prefix}: promotion_state='adopted' requires "
                f"adopted_by_decision_id"
            )

        if _has_required_value(adopted_by):
            _, dec_errors = _is_valid_adoption_decision(
                e, decision_by_id, evidence_by_id, artifact_ids,
                revision_counts,
                collect_errors=True,
            )
            errors.extend(dec_errors)

    _, fp_errors = _check_fingerprint_uniqueness(entries, collect_errors=True)
    errors.extend(fp_errors)

    return ValidationResult(valid=len(errors) == 0, errors=errors)


def derive_skill_governance(payload: dict) -> dict:
    entries: list[dict] = payload.get("skill_registry") or []
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

    revision_counts: dict[str, int] = {}
    for e in entries:
        raw_sid = e.get("skill_id", "")
        if _has_required_value(raw_sid):
            sid = _canonical_skill_id(raw_sid)
            revision_counts[sid] = revision_counts.get(sid, 0) + 1

    adopted_count = 0
    by_promotion_state: dict[str, int] = {}

    fp_ok, _ = _check_fingerprint_uniqueness(entries, collect_errors=False)
    if not fp_ok:
        stale: dict[str, int] = {}
        for e in entries:
            ps = e.get("promotion_state", "")
            if ps:
                stale[ps] = stale.get(ps, 0) + 1
        return {
            "total_skills": len(entries),
            "adopted_count": 0,
            "by_promotion_state": stale,
        }

    for e in entries:
        ps = e.get("promotion_state", "")
        if ps:
            by_promotion_state[ps] = by_promotion_state.get(ps, 0) + 1

        base_ok, _ = _is_valid_skill_base(e, collect_errors=False)
        if not base_ok:
            continue

        if ps != "adopted":
            continue

        adopted_by = e.get("adopted_by_decision_id") or ""
        if not _has_required_value(adopted_by):
            continue

        ok, _ = _is_valid_adoption_decision(
            e, decision_by_id, evidence_by_id, artifact_ids,
            revision_counts,
            collect_errors=False,
        )
        if ok:
            adopted_count += 1

    return {
        "total_skills": len(entries),
        "adopted_count": adopted_count,
        "by_promotion_state": by_promotion_state,
    }
