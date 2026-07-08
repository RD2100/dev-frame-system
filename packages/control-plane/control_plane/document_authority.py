"""Phase 2: document authority and promotion validation.

Extends the review-governance pattern to document lifecycle management.
A document becomes authoritative when an evidence-backed decision adopts it,
not when it is polished.

Lifecycle states:
  draft -> current -> superseded -> archived

Promotion rules (must all pass):
  1. evidence_ids present and resolve to existing evidence
  2. adopting_decision_id present and resolves to a decision
  3. the adopting decision has outcome=pass
  4. the adopting decision's target_ref matches the document ID
  5. the adopting decision has kind="adopt" and evidence-backed adoption
  6. document content_hash is present (immutable artifact)
  5. if status=current, must have at least one adopting decision
  6. if status=superseded, must have a superseding_document_id
  7. a document cannot adopt itself
  8. superseding_document_id must exist in the documents list

derive_authority() computes the read-only authority projection from packet facts.
"""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field


@dataclass
class ValidationResult:
    valid: bool
    errors: list[str] = field(default_factory=list)

    def __bool__(self) -> bool:
        return self.valid


@dataclass(frozen=True)
class AdoptionEligibility:
    document_id: str
    evidence_ids: list[str]
    adopting_decision_id: str
    decision_outcome: object
    decision_target_ref: str
    decision_kind: object
    decision_evidence_ids: list[str]
    has_evidence: bool
    decision_backs_document: bool
    has_invalid_identity: bool
    is_adopted: bool


def _get(payload: dict, path: str) -> object | None:
    cur = payload
    for key in path.split("."):
        if isinstance(cur, dict) and key in cur:
            cur = cur[key]
        else:
            return None
    return cur


DOCUMENT_LIFECYCLE = ("draft", "current", "superseded", "archived")
ADOPTION_REQUIRED_STATUSES = ("current",)
SUPERSEDED_REQUIRES_SUCCESSOR = ("superseded",)


def _canonical_id(value: object) -> str:
    if not isinstance(value, str):
        return ""
    return value.strip()


def _canonical_id_refs(value: object) -> list[str]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        return []
    return [_canonical_id(item) for item in value]


def _has_blank_id_ref(value: object) -> bool:
    return any(not ref for ref in _canonical_id_refs(value))


def _index_by_canonical_id(records: Sequence[dict]) -> dict[str, dict]:
    indexed: dict[str, dict] = {}
    for record in records:
        record_id = _canonical_id(record.get("id", ""))
        if record_id:
            indexed[record_id] = record
    return indexed


def _canonical_doc_ids(documents: Sequence[dict]) -> set[str]:
    return {
        doc_id
        for doc_id in (_canonical_id(document.get("id", "")) for document in documents)
        if doc_id
    }


def _refs_resolve(refs: Sequence[str], records_by_id: dict[str, dict]) -> bool:
    return bool(refs) and all(ref and ref in records_by_id for ref in refs)


def _has_nonblank_content_hash(doc: dict) -> bool:
    content_hash = doc.get("content_hash", "")
    return isinstance(content_hash, str) and bool(content_hash.strip())


def _adoption_eligibility(
        doc: dict,
        evidence_by_id: dict[str, dict],
        decision_by_id: dict[str, dict]) -> AdoptionEligibility:
    document_id = _canonical_id(doc.get("id", ""))
    evidence_ids = _canonical_id_refs(doc.get("evidence_ids", []))
    adopting_decision_id = _canonical_id(doc.get("adopting_decision_id", ""))

    decision = decision_by_id.get(adopting_decision_id) if adopting_decision_id else None
    decision_outcome = decision.get("outcome", "") if decision else ""
    decision_target_ref = _canonical_id(decision.get("target_ref", "")) if decision else ""
    decision_kind = decision.get("kind", "") if decision else ""
    decision_evidence_ids = (
        _canonical_id_refs(decision.get("evidence_ids", [])) if decision else []
    )

    has_evidence = _refs_resolve(evidence_ids, evidence_by_id)
    decision_has_evidence = _refs_resolve(decision_evidence_ids, evidence_by_id)
    decision_backs_document = (
        bool(evidence_ids) and set(evidence_ids).issubset(set(decision_evidence_ids))
    )
    has_invalid_identity = bool(
        not document_id
        or _has_blank_id_ref(doc.get("evidence_ids", []))
        or (doc.get("adopting_decision_id") is not None and not adopting_decision_id)
        or (decision is not None and _has_blank_id_ref(decision.get("evidence_ids", [])))
    )
    is_adopted = bool(
        document_id
        and adopting_decision_id
        and decision is not None
        and decision_kind == "adopt"
        and decision_outcome == "pass"
        and decision_target_ref == document_id
        and has_evidence
        and decision_has_evidence
        and decision_backs_document
        and not has_invalid_identity
    )

    return AdoptionEligibility(
        document_id=document_id,
        evidence_ids=evidence_ids,
        adopting_decision_id=adopting_decision_id,
        decision_outcome=decision_outcome,
        decision_target_ref=decision_target_ref,
        decision_kind=decision_kind,
        decision_evidence_ids=decision_evidence_ids,
        has_evidence=has_evidence,
        decision_backs_document=decision_backs_document,
        has_invalid_identity=has_invalid_identity,
        is_adopted=is_adopted,
    )


def derive_authority(payload: dict) -> dict:
    """Compute read-only document authority projection from packet facts.

    Does not invent authority. Returns the authority state implied by
    the packet's own evidence and decisions.
    """
    documents: list[dict] = _get(payload, "documents") or []
    evidence: list[dict] = _get(payload, "evidence") or []
    decisions: list[dict] = _get(payload, "decisions") or []

    evidence_by_id = _index_by_canonical_id(evidence)
    decision_by_id = _index_by_canonical_id(decisions)
    doc_ids = _canonical_doc_ids(documents)

    doc_projections = []
    for doc in documents:
        eligibility = _adoption_eligibility(doc, evidence_by_id, decision_by_id)
        doc_id = eligibility.document_id
        adopting_decision_id = eligibility.adopting_decision_id
        superseding_id = _canonical_id(doc.get("superseding_document_id", ""))
        has_content_hash = _has_nonblank_content_hash(doc)

        has_evidence = eligibility.has_evidence
        is_adopted = eligibility.is_adopted
        has_self_loop = superseding_id == doc_id if superseding_id else False
        successor_exists = superseding_id in doc_ids if superseding_id else True

        status_val = doc.get("status", "")
        if eligibility.has_invalid_identity:
            authority_state = "invalid"
        elif status_val == "archived":
            authority_state = "archived"
        elif status_val == "draft":
            authority_state = "draft"
        elif status_val == "superseded":
            if superseding_id and not has_self_loop and successor_exists:
                authority_state = "superseded"
            else:
                authority_state = "invalid"
        elif status_val == "current" and is_adopted and has_evidence and has_content_hash:
            authority_state = "authoritative"
        else:
            authority_state = "pending"

        doc_projections.append({
            "document_id": doc_id,
            "authority_state": authority_state,
            "is_adopted": is_adopted,
            "has_evidence": has_evidence,
            "adopting_decision_id": adopting_decision_id,
            "decision_outcome": eligibility.decision_outcome,
        })

    return {
        "document_count": len(documents),
        "authoritative_count": sum(1 for p in doc_projections if p["authority_state"] == "authoritative"),
        "documents": doc_projections,
    }


def validate_promotion(payload: dict) -> ValidationResult:
    """Validate document authority and promotion rules.

    Returns ValidationResult with all violations accumulated.
    """
    errors: list[str] = []

    documents: list[dict] = _get(payload, "documents") or []
    evidence: list[dict] = _get(payload, "evidence") or []
    decisions: list[dict] = _get(payload, "decisions") or []

    if not documents:
        errors.append("documents list is empty — at least one document required")
        return ValidationResult(valid=False, errors=errors)

    evidence_by_id = _index_by_canonical_id(evidence)
    decision_by_id = _index_by_canonical_id(decisions)
    doc_ids = _canonical_doc_ids(documents)

    for index, evidence_item in enumerate(evidence):
        if not _canonical_id(evidence_item.get("id", "")):
            errors.append(
                f"evidence id at index {index} is required and must be nonblank"
            )

    for index, decision in enumerate(decisions):
        if not _canonical_id(decision.get("id", "")):
            errors.append(
                f"decision id at index {index} is required and must be nonblank"
            )

    for doc in documents:
        eligibility = _adoption_eligibility(doc, evidence_by_id, decision_by_id)
        doc_id = eligibility.document_id
        status = doc.get("status", "")
        evidence_ids = eligibility.evidence_ids
        adopting_decision_id = eligibility.adopting_decision_id
        superseding_id = _canonical_id(doc.get("superseding_document_id", ""))

        if not doc_id:
            errors.append("document id is required and must be nonblank")

        if status not in DOCUMENT_LIFECYCLE:
            errors.append(
                f"document {doc_id}: status={status!r} not in {DOCUMENT_LIFECYCLE}"
            )

        if not _has_nonblank_content_hash(doc):
            errors.append(f"document {doc_id}: content_hash is required for immutable artifact")

        if status in ADOPTION_REQUIRED_STATUSES:
            if not evidence_ids:
                errors.append(f"document {doc_id}: status={status!r} requires at least one evidence_id")
            elif any(not eid for eid in evidence_ids):
                errors.append(
                    f"document {doc_id}: evidence_ids must contain only nonblank ids"
                )
            for eid in evidence_ids:
                if eid and eid not in evidence_by_id:
                    errors.append(f"document {doc_id}: evidence_id {eid!r} not found in evidence list")
            if not adopting_decision_id:
                errors.append(
                    f"document {doc_id}: status={status!r} requires "
                    f"adopting_decision_id and it must be nonblank"
                )
            else:
                decision = decision_by_id.get(adopting_decision_id)
                if not decision:
                    errors.append(f"document {doc_id}: adopting_decision_id {adopting_decision_id!r} not found")
                elif eligibility.decision_outcome != "pass":
                    errors.append(
                        f"document {doc_id}: adopting decision {adopting_decision_id!r} "
                        f"has outcome={eligibility.decision_outcome!r}, expected 'pass'"
                    )
                elif eligibility.decision_target_ref != doc_id:
                    errors.append(
                        f"document {doc_id}: adopting decision {adopting_decision_id!r} "
                        f"has target_ref={eligibility.decision_target_ref!r}, "
                        f"expected {doc_id!r}"
                    )
                elif eligibility.decision_kind != "adopt":
                    errors.append(
                        f"document {doc_id}: adopting decision {adopting_decision_id!r} "
                        f"has kind={eligibility.decision_kind!r}, expected 'adopt'"
                    )
                else:
                    dec_evidence_ids = eligibility.decision_evidence_ids
                    if not dec_evidence_ids:
                        errors.append(
                            f"document {doc_id}: adopting decision {adopting_decision_id!r} "
                            f"has no evidence_ids"
                        )
                    elif any(not eid for eid in dec_evidence_ids):
                        errors.append(
                            f"document {doc_id}: adopting decision {adopting_decision_id!r} "
                            f"evidence_ids must contain only nonblank ids"
                        )
                    else:
                        for eid in dec_evidence_ids:
                            if eid and eid not in evidence_by_id:
                                errors.append(
                                    f"document {doc_id}: adopting decision evidence_id {eid!r} not found"
                                )
                    if evidence_ids and not eligibility.decision_backs_document:
                        errors.append(
                            f"document {doc_id}: document evidence_ids not subset of "
                            f"adopting decision evidence_ids"
                        )

        if status in SUPERSEDED_REQUIRES_SUCCESSOR:
            if not superseding_id:
                errors.append(f"document {doc_id}: status=superseded requires superseding_document_id")
            elif superseding_id == doc_id:
                errors.append(f"document {doc_id}: superseding_document_id cannot be self-referential")
            elif superseding_id not in doc_ids:
                errors.append(f"document {doc_id}: superseding_document_id {superseding_id!r} not in documents list")

    derived = derive_authority(payload)
    for doc_proj in derived["documents"]:
        if doc_proj["authority_state"] == "invalid":
            errors.append(f"document {doc_proj['document_id']}: derived authority_state is invalid")

    return ValidationResult(valid=len(errors) == 0, errors=errors)
