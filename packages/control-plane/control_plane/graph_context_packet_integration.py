"""Amend a context packet with a bounded graph selection in memory.

The adapter deliberately stops before the existing packet writers.  It creates
an immutable derived packet and appends one hash-linked ledger entry without
mutating either input object or creating a new authority source.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import re
from typing import Any


MAX_REFS = 256
MAX_LIST_ITEMS = 512
MAX_LEDGER_ENTRIES = 2048
MAX_ID_LENGTH = 128
MAX_TEXT_LENGTH = 512

_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_URI_RE = re.compile(
    r"^(?P<scheme>[A-Za-z][A-Za-z0-9+.-]{1,31})://"
    r"(?P<body>[A-Za-z0-9][A-Za-z0-9._~:/#?&=+\-]{0,511})$"
)
_URI_SCHEMES = {
    "artifact",
    "code",
    "decision",
    "doc",
    "evidence",
    "graph",
    "paper",
    "project",
    "repo",
    "review",
    "run",
    "skill",
}
_SENSITIVE_RE = re.compile(
    r"(?i)(?:api[_-]?key|authorization|bearer|cookie|password|secret|token)"
    r"|sk-[A-Za-z0-9_-]{12,}"
)
_REF_KINDS = {
    "artifact",
    "directory",
    "evidence",
    "file",
    "final_verdict",
    "note",
    "review",
    "url",
}
_COMPLETENESS_ORDER = {
    "complete": 0,
    "incomplete": 1,
    "insufficient_evidence": 2,
}
_PRIVACY_ORDER = {
    "redacted": 0,
    "contains_sensitive_summary": 1,
    "blocked_sensitive_source": 2,
}


class GraphContextPacketIntegrationError(ValueError):
    """Raised when a graph selection cannot safely amend a context packet."""


def integrate_graph_context_selection(
    packet: dict[str, Any],
    ledger: dict[str, Any],
    selection: dict[str, Any],
    *,
    actor_id: str,
    actor_role: str,
    occurred_at: str | None = None,
) -> dict[str, dict[str, Any]]:
    """Return a derived packet and append-only ledger without side effects."""
    _validate_packet(packet)
    _validate_ledger(ledger, packet)
    selection = canonicalize_graph_context_selection(
        selection, project_id=packet["project_id"]
    )
    selection_id = selection["context_selection_id"]
    event_time = _validated_time(occurred_at)
    actor_id = _required_text(actor_id, "actor_id")
    actor_role = _required_text(actor_role, "actor_role")
    if actor_role.casefold() in {"worker", "executor", "coder", "fixer"}:
        raise GraphContextPacketIntegrationError("actor role cannot amend context authority")
    new_packet = _amend_packet(packet, selection, selection_id, event_time)
    if _has_amendment(
        ledger,
        packet["context_packet_id"],
        new_packet["context_packet_id"],
        selection_id,
    ):
        return {
            "context_packet": new_packet,
            "context_ledger": deepcopy(ledger),
        }
    new_ledger = _append_amendment(
        ledger,
        packet_id=packet["context_packet_id"],
        resulting_packet_id=new_packet["context_packet_id"],
        selection=selection,
        actor_id=actor_id,
        actor_role=actor_role,
        occurred_at=event_time,
    )
    return {"context_packet": new_packet, "context_ledger": new_ledger}


def canonicalize_graph_context_selection(
    selection: dict[str, Any], *, project_id: str
) -> dict[str, Any]:
    """Validate and return only the graph fields the packet adapter consumes."""
    _required_id(project_id, "project_id")
    _validate_selection(selection, project_id)
    fields = (
        "context_selection_id",
        "graph_projection_id",
        "graph_slice_ref",
        "project_id",
        "selected_node_ids",
        "candidate_roles",
        "source_refs",
        "omitted_required_refs",
        "omitted_context",
        "forbidden_refs",
        "assumption_claims",
        "omitted_assumptions",
        "freshness",
        "completeness_state",
        "privacy_state",
        "authority_boundary",
    )
    return {field: deepcopy(selection[field]) for field in fields}


def _validate_packet(packet: object) -> None:
    if not isinstance(packet, dict):
        raise GraphContextPacketIntegrationError("context packet must be an object")
    for field in ("context_packet_id", "project_id", "goal_id", "task_id"):
        _required_id(packet.get(field), field)
    if not str(packet["context_packet_id"]).startswith("cp-"):
        raise GraphContextPacketIntegrationError("context_packet_id is invalid")
    if packet.get("seal_state") not in {
        "draft",
        "sealed",
        "superseded_by_amendment",
    }:
        raise GraphContextPacketIntegrationError("context packet seal_state is invalid")
    immutability = packet.get("immutability")
    if not isinstance(immutability, dict) or immutability.get("immutable") is not True:
        raise GraphContextPacketIntegrationError("context packet must be immutable")
    _validate_ref_list(
        packet.get("source_refs"), "source_refs", allow_empty=False, strict_uri=False
    )
    _validate_omission_list(packet.get("omitted_required_refs", []), "omitted_required_refs")
    _validate_forbidden_list(packet.get("forbidden_refs", []))
    _validate_packet_boundary(packet.get("constraints"))


def _validate_packet_boundary(value: object) -> None:
    if not isinstance(value, dict):
        raise GraphContextPacketIntegrationError("context packet constraints are invalid")
    boundary = value.get("authority_boundary")
    if not isinstance(boundary, dict):
        raise GraphContextPacketIntegrationError("context packet authority boundary is missing")
    if boundary.get("can_claim_final_acceptance") is not False:
        raise GraphContextPacketIntegrationError("context packet can claim acceptance")
    if boundary.get("final_verdict_required") is not True:
        raise GraphContextPacketIntegrationError("context packet final verdict rule is missing")


def _validate_ledger(ledger: object, packet: dict[str, Any]) -> None:
    if not isinstance(ledger, dict) or ledger.get("append_only") is not True:
        raise GraphContextPacketIntegrationError("context ledger must be append-only")
    for field in ("context_ledger_id", "project_id", "goal_id", "task_id"):
        _required_id(ledger.get(field), f"ledger.{field}")
    if not str(ledger["context_ledger_id"]).startswith("cl-"):
        raise GraphContextPacketIntegrationError("ledger.context_ledger_id is invalid")
    if ledger["project_id"] != packet["project_id"]:
        raise GraphContextPacketIntegrationError("packet and ledger project mismatch")
    if ledger["goal_id"] != packet["goal_id"] or ledger["task_id"] != packet["task_id"]:
        raise GraphContextPacketIntegrationError("packet and ledger identity mismatch")
    entries = ledger.get("entries")
    if not isinstance(entries, list) or not entries or len(entries) > MAX_LEDGER_ENTRIES:
        raise GraphContextPacketIntegrationError("context ledger entries are invalid")
    previous: str | None = None
    for index, entry in enumerate(entries):
        _validate_ledger_entry(entry, index, previous)
        previous = entry["entry_hash"]


def _validate_ledger_entry(entry: object, index: int, previous: str | None) -> None:
    if not isinstance(entry, dict) or entry.get("entry_index") != index:
        raise GraphContextPacketIntegrationError("context ledger index is not monotonic")
    if entry.get("previous_entry_hash") != previous:
        raise GraphContextPacketIntegrationError("context ledger hash chain is broken")
    entry_hash = entry.get("entry_hash")
    if not isinstance(entry_hash, str) or not re.fullmatch(r"sha256:[a-f0-9]{64}", entry_hash):
        raise GraphContextPacketIntegrationError("context ledger entry hash is invalid")
    seed = {key: value for key, value in entry.items() if key != "entry_hash"}
    if _digest(seed) != entry_hash:
        raise GraphContextPacketIntegrationError("context ledger hash chain entry does not verify")


def _validate_selection(selection: object, project_id: str) -> str:
    if not isinstance(selection, dict):
        raise GraphContextPacketIntegrationError("graph selection must be an object")
    selection_id = _required_id(selection.get("context_selection_id"), "context_selection_id")
    graph_id = _required_id(selection.get("graph_projection_id"), "graph_projection_id")
    if selection.get("project_id") != project_id:
        raise GraphContextPacketIntegrationError("graph selection project mismatch")
    _safe_uri(selection.get("graph_slice_ref"), "graph_slice_ref")
    if selection.get("graph_slice_ref") != f"graph://projection/{graph_id}":
        raise GraphContextPacketIntegrationError("graph slice reference does not match projection")
    _validate_ref_list(
        selection.get("source_refs"), "selection.source_refs", allow_empty=False, strict_uri=True
    )
    _validate_omission_list(selection.get("omitted_required_refs", []), "selection.omitted_required_refs")
    _validate_omission_list(selection.get("omitted_context", []), "selection.omitted_context")
    _validate_forbidden_list(selection.get("forbidden_refs", []))
    _validate_selection_lists(selection)
    _validate_selection_boundary(selection.get("authority_boundary"))
    if selection.get("completeness_state") != "incomplete":
        raise GraphContextPacketIntegrationError("graph selection completeness must be incomplete")
    if selection.get("privacy_state") != "redacted":
        raise GraphContextPacketIntegrationError("graph selection privacy state is invalid")
    return selection_id


def _validate_selection_lists(selection: dict[str, Any]) -> None:
    roles = selection.get("candidate_roles")
    if not isinstance(roles, dict) or len(roles) > MAX_REFS:
        raise GraphContextPacketIntegrationError("graph candidate roles are invalid")
    for node_id, role in roles.items():
        _required_id(node_id, "candidate node ID")
        if role not in {"selected", "neighbor"}:
            raise GraphContextPacketIntegrationError("graph candidate role is invalid")
    selected_ids = selection.get("selected_node_ids")
    if not isinstance(selected_ids, list) or not selected_ids:
        raise GraphContextPacketIntegrationError("selected_node_ids is not bounded")
    _validate_id_list(selected_ids, "selected_node_ids")
    if any(node_id not in roles or roles[node_id] != "selected" for node_id in selected_ids):
        raise GraphContextPacketIntegrationError("selected graph node role is inconsistent")
    freshness = selection.get("freshness")
    if not isinstance(freshness, dict):
        raise GraphContextPacketIntegrationError("graph freshness is invalid")
    _validate_id_list(freshness.get("stale_refs", []), "stale_refs")
    _validate_id_list(freshness.get("unknown_refs", []), "unknown_refs")
    assumptions = selection.get("assumption_claims", [])
    omitted = selection.get("omitted_assumptions", [])
    if not isinstance(assumptions, list) or len(assumptions) > MAX_LIST_ITEMS:
        raise GraphContextPacketIntegrationError("graph assumptions are invalid")
    if not isinstance(omitted, list) or len(omitted) > MAX_LIST_ITEMS:
        raise GraphContextPacketIntegrationError("omitted graph assumptions are invalid")
    for claim in assumptions:
        _validate_assumption(claim)
    _validate_omission_list(omitted, "selection.omitted_assumptions")


def _validate_assumption(value: object) -> None:
    if not isinstance(value, dict):
        raise GraphContextPacketIntegrationError("graph assumption is invalid")
    if set(value) - {"edge_id", "source", "target", "kind", "authority"}:
        raise GraphContextPacketIntegrationError("graph assumption contains unknown fields")
    for field in ("edge_id", "source", "target"):
        _required_id(value.get(field), f"assumption.{field}")
    if value.get("kind") not in {"inferred", "annotated"}:
        raise GraphContextPacketIntegrationError("graph assumption kind is invalid")
    if value.get("authority") != "assumption":
        raise GraphContextPacketIntegrationError("graph assumption authority is invalid")


def _validate_selection_boundary(value: object) -> None:
    if not isinstance(value, dict):
        raise GraphContextPacketIntegrationError("graph selection authority boundary is missing")
    expected = {
        "can_execute": False,
        "can_review": True,
        "can_claim_final_acceptance": False,
        "final_verdict_required": True,
    }
    if value != expected:
        raise GraphContextPacketIntegrationError("graph selection authority boundary is unsafe")


def _validate_ref_list(
    value: object, field_name: str, *, allow_empty: bool, strict_uri: bool
) -> None:
    if not isinstance(value, list) or len(value) > MAX_REFS or (not allow_empty and not value):
        raise GraphContextPacketIntegrationError(f"{field_name} is not a bounded reference list")
    seen: set[str] = set()
    for item in value:
        if not isinstance(item, dict):
            raise GraphContextPacketIntegrationError(f"{field_name} contains a non-object")
        if strict_uri and set(item) - {
            "ref_id",
            "kind",
            "uri",
            "content_hash",
            "included",
            "required",
            "freshness_state",
        }:
            raise GraphContextPacketIntegrationError(f"{field_name} contains unknown fields")
        ref_id = _required_id(item.get("ref_id"), f"{field_name}.ref_id")
        if ref_id in seen:
            raise GraphContextPacketIntegrationError(f"{field_name} contains duplicate refs")
        seen.add(ref_id)
        if item.get("kind") not in _REF_KINDS:
            raise GraphContextPacketIntegrationError(f"{field_name} contains an invalid kind")
        if strict_uri:
            if not isinstance(item.get("included"), bool) or not isinstance(item.get("required"), bool):
                raise GraphContextPacketIntegrationError(f"{field_name} contains invalid inclusion flags")
            if item.get("freshness_state") not in {
                "current",
                "stale",
                "unknown",
                "omitted",
            }:
                raise GraphContextPacketIntegrationError(f"{field_name} contains invalid freshness")
            if "content_hash" in item and not re.fullmatch(
                r"sha256:[a-f0-9]{64}", str(item["content_hash"])
            ):
                raise GraphContextPacketIntegrationError(f"{field_name} contains invalid content hash")
            _safe_uri(item.get("uri"), f"{field_name}.uri")
        else:
            _bounded_text(item.get("uri"), f"{field_name}.uri")


def _validate_omission_list(value: object, field_name: str) -> None:
    if not isinstance(value, list) or len(value) > MAX_LIST_ITEMS:
        raise GraphContextPacketIntegrationError(f"{field_name} is not bounded")
    for item in value:
        if not isinstance(item, dict):
            raise GraphContextPacketIntegrationError(f"{field_name} contains a non-object")
        if set(item) - {"ref", "omission_reason", "impact"}:
            raise GraphContextPacketIntegrationError(f"{field_name} contains unknown fields")
        _safe_reference_text(item.get("ref"), f"{field_name}.ref")
        _safe_reference_text(item.get("omission_reason"), f"{field_name}.omission_reason")
        _safe_reference_text(item.get("impact"), f"{field_name}.impact")


def _validate_forbidden_list(value: object) -> None:
    if not isinstance(value, list) or len(value) > MAX_LIST_ITEMS:
        raise GraphContextPacketIntegrationError("forbidden refs are not bounded")
    for item in value:
        if not isinstance(item, dict):
            raise GraphContextPacketIntegrationError("forbidden refs contain a non-object")
        if set(item) - {"ref", "reason"}:
            raise GraphContextPacketIntegrationError("forbidden refs contain unknown fields")
        _safe_reference_text(item.get("ref"), "forbidden.ref")
        _safe_reference_text(item.get("reason"), "forbidden.reason")


def _validate_id_list(value: object, field_name: str) -> None:
    if not isinstance(value, list) or len(value) > MAX_LIST_ITEMS:
        raise GraphContextPacketIntegrationError(f"{field_name} is not bounded")
    for item in value:
        _required_id(item, field_name)


def _amend_packet(
    packet: dict[str, Any],
    selection: dict[str, Any],
    selection_id: str,
    occurred_at: str,
) -> dict[str, Any]:
    result = deepcopy(packet)
    old_id = packet["context_packet_id"]
    result["context_packet_id"] = _derived_packet_id(old_id, selection_id)
    result["source_refs"] = _merge_refs(packet["source_refs"], selection["source_refs"])
    result["omitted_required_refs"] = _merge_records(
        packet.get("omitted_required_refs", []), selection.get("omitted_required_refs", [])
    )
    result["forbidden_refs"] = _merge_records(
        packet.get("forbidden_refs", []), selection.get("forbidden_refs", []), key="ref"
    )
    result["freshness"] = _merge_freshness(packet.get("freshness", {}), selection, occurred_at)
    result["completeness_state"] = _merged_completeness(
        packet.get("completeness_state"), selection["completeness_state"]
    )
    result["privacy_state"] = _merged_privacy(packet.get("privacy_state"), selection["privacy_state"])
    result["seal_state"] = "sealed"
    result["limitations"] = _append_limitations(result.get("limitations", []))
    result["constraints"] = _amended_constraints(result.get("constraints", {}))
    result["domain_refs"] = _graph_domain_refs(result.get("domain_refs", {}), selection)
    result["immutability"] = {"immutable": True, "content_hash": ""}
    result["immutability"]["content_hash"] = _packet_hash(result)
    return result


def _merge_refs(base: list[dict[str, Any]], additions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result = [deepcopy(item) for item in base]
    by_id = {item["ref_id"]: item for item in result}
    for item in additions:
        existing = by_id.get(item["ref_id"])
        if existing is not None and existing != item:
            raise GraphContextPacketIntegrationError("graph ref conflicts with packet ref")
        if existing is None:
            if len(result) >= MAX_REFS:
                raise GraphContextPacketIntegrationError("amended packet refs exceed limit")
            copied = deepcopy(item)
            result.append(copied)
            by_id[copied["ref_id"]] = copied
    return result


def _merge_records(
    base: list[dict[str, Any]], additions: list[dict[str, Any]], *, key: str = "ref"
) -> list[dict[str, Any]]:
    result = [deepcopy(item) for item in base]
    seen = {item.get(key) for item in result if isinstance(item, dict)}
    for item in additions:
        marker = item.get(key)
        if marker in seen:
            continue
        if len(result) >= MAX_LIST_ITEMS:
            raise GraphContextPacketIntegrationError("amended packet records exceed limit")
        result.append(deepcopy(item))
        seen.add(marker)
    return result


def _merge_freshness(
    base: object, selection: dict[str, Any], occurred_at: str
) -> dict[str, Any]:
    if not isinstance(base, dict):
        raise GraphContextPacketIntegrationError("packet freshness is invalid")
    stale = _string_list(base.get("stale_refs", []), "packet stale refs")
    unknown = _string_list(base.get("unknown_refs", []), "packet unknown refs")
    selected_freshness = selection.get("freshness", {})
    stale = _unique_append(stale, selected_freshness.get("stale_refs", []))
    unknown = _unique_append(unknown, selected_freshness.get("unknown_refs", []))
    return {"checked_at": occurred_at, "stale_refs": stale, "unknown_refs": unknown}


def _append_limitations(value: object) -> list[str]:
    if not isinstance(value, list) or len(value) > MAX_LIST_ITEMS:
        raise GraphContextPacketIntegrationError("packet limitations are invalid")
    result = [item for item in value if isinstance(item, str)]
    additions = [
        "Graph context is a bounded, incomplete selection and must not be treated as authority.",
        "Inferred and annotated graph relationships remain assumptions pending review.",
    ]
    for item in additions:
        if item not in result:
            result.append(item)
    return result[:MAX_LIST_ITEMS]


def _amended_constraints(value: object) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise GraphContextPacketIntegrationError("packet constraints are invalid")
    result = deepcopy(value)
    for field, addition in (
        ("allowed_actions", "inspect graph-derived context candidates"),
        ("forbidden_actions", "treat graph assumptions as source truth"),
        ("stop_lines", "Stop if graph context is treated as complete or authoritative."),
    ):
        items = result.get(field)
        if not isinstance(items, list) or len(items) > MAX_LIST_ITEMS:
            raise GraphContextPacketIntegrationError(f"packet constraints.{field} is invalid")
        if addition not in items:
            items.append(addition)
    _validate_packet_boundary(result)
    return result


def _graph_domain_refs(base: object, selection: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(base, dict):
        raise GraphContextPacketIntegrationError("packet domain_refs are invalid")
    result = deepcopy(base)
    result["graph_context_selection"] = {
        "context_selection_id": selection["context_selection_id"],
        "graph_projection_id": selection["graph_projection_id"],
        "graph_slice_ref": selection["graph_slice_ref"],
        "candidate_roles": deepcopy(selection["candidate_roles"]),
        "assumption_claims": deepcopy(selection.get("assumption_claims", [])),
        "omitted_context": deepcopy(selection.get("omitted_context", [])),
    }
    return result


def _append_amendment(
    ledger: dict[str, Any],
    *,
    packet_id: str,
    resulting_packet_id: str,
    selection: dict[str, Any],
    actor_id: str,
    actor_role: str,
    occurred_at: str,
) -> dict[str, Any]:
    result = deepcopy(ledger)
    entries = result["entries"]
    if len(entries) >= MAX_LEDGER_ENTRIES:
        raise GraphContextPacketIntegrationError("context ledger entries exceed limit")
    previous = entries[-1]["entry_hash"] if entries else None
    seed = {
        "ledger_entry_id": f"cle-{_safe_token(resulting_packet_id)}-graph",
        "entry_index": len(entries),
        "previous_entry_hash": previous,
        "occurred_at": occurred_at,
        "actor_id": actor_id,
        "actor_role": actor_role,
        "event_type": "amendment_recorded",
        "context_packet_id": resulting_packet_id,
        "summary": "Recorded a bounded graph context selection as an immutable packet amendment.",
        "source_refs": [_ledger_ref(ref) for ref in selection["source_refs"]],
        "resulting_context_packet_id": resulting_packet_id,
        "superseded_context_packet_id": packet_id,
        "domain_refs": {
            "context_selection_id": selection["context_selection_id"],
            "graph_projection_id": selection["graph_projection_id"],
            "candidate_count": len(selection.get("candidate_roles", {})),
            "omitted_count": len(selection.get("omitted_required_refs", [])),
            "assumption_count": len(selection.get("assumption_claims", [])),
        },
    }
    entries.append({**seed, "entry_hash": _digest(seed)})
    return result


def _has_amendment(
    ledger: dict[str, Any],
    packet_id: str,
    resulting_packet_id: str,
    selection_id: str,
) -> bool:
    for entry in ledger["entries"]:
        if not isinstance(entry, dict):
            continue
        if (
            entry.get("event_type") != "amendment_recorded"
            or entry.get("context_packet_id") != resulting_packet_id
            or entry.get("resulting_context_packet_id") != resulting_packet_id
            or entry.get("superseded_context_packet_id") != packet_id
        ):
            continue
        refs = entry.get("domain_refs")
        if isinstance(refs, dict) and refs.get("context_selection_id") == selection_id:
            return True
    return False


def _ledger_ref(ref: dict[str, Any]) -> dict[str, Any]:
    result = {key: ref[key] for key in ("ref_id", "kind", "uri")}
    if "content_hash" in ref:
        result["content_hash"] = ref["content_hash"]
    return result


def _packet_hash(packet: dict[str, Any]) -> str:
    seed = deepcopy(packet)
    seed["immutability"] = {"immutable": True, "content_hash": ""}
    return _digest(seed)


def _derived_packet_id(packet_id: str, selection_id: str) -> str:
    digest = hashlib.sha256(f"{packet_id}\0{selection_id}".encode("utf-8")).hexdigest()[:20]
    token = _safe_token(packet_id.removeprefix("cp-"))[:64]
    return f"cp-{token}-graph-{digest}"


def _merged_completeness(base: object, selection: str) -> str:
    if base not in _COMPLETENESS_ORDER:
        raise GraphContextPacketIntegrationError("packet completeness state is invalid")
    return max((base, selection), key=lambda value: _COMPLETENESS_ORDER[value])


def _merged_privacy(base: object, selection: str) -> str:
    if base not in _PRIVACY_ORDER:
        raise GraphContextPacketIntegrationError("packet privacy state is invalid")
    if selection not in _PRIVACY_ORDER:
        raise GraphContextPacketIntegrationError("selection privacy state is invalid")
    return max((base, selection), key=lambda value: _PRIVACY_ORDER[value])


def _validated_time(value: str | None) -> str:
    result = datetime.now(timezone.utc).isoformat() if value is None else value
    if not isinstance(result, str) or not result:
        raise GraphContextPacketIntegrationError("occurred_at must be a date-time")
    try:
        parsed = datetime.fromisoformat(result.replace("Z", "+00:00"))
    except ValueError as exc:
        raise GraphContextPacketIntegrationError("occurred_at must be a date-time") from exc
    if parsed.tzinfo is None:
        raise GraphContextPacketIntegrationError("occurred_at must include a timezone")
    return result


def _required_id(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not _ID_RE.fullmatch(value):
        raise GraphContextPacketIntegrationError(f"{field_name} must be an opaque ID")
    return value


def _required_text(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value or len(value) > MAX_TEXT_LENGTH:
        raise GraphContextPacketIntegrationError(f"{field_name} must be bounded text")
    if _SENSITIVE_RE.search(value) or any(ord(char) < 32 for char in value):
        raise GraphContextPacketIntegrationError(f"{field_name} contains unsafe text")
    return value


def _safe_uri(value: object, field_name: str) -> str:
    if not isinstance(value, str) or len(value) > MAX_TEXT_LENGTH or "\\" in value:
        raise GraphContextPacketIntegrationError(f"{field_name} is unsafe")
    match = _URI_RE.fullmatch(value)
    if match is None or match.group("scheme") not in _URI_SCHEMES:
        raise GraphContextPacketIntegrationError(f"{field_name} is unsafe")
    if ".." in value or _SENSITIVE_RE.search(value):
        raise GraphContextPacketIntegrationError(f"{field_name} is unsafe")
    return value


def _bounded_text(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value or len(value) > MAX_TEXT_LENGTH:
        raise GraphContextPacketIntegrationError(f"{field_name} is invalid")
    if any(ord(char) < 32 for char in value):
        raise GraphContextPacketIntegrationError(f"{field_name} is invalid")
    return value


def _safe_reference_text(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value or len(value) > MAX_TEXT_LENGTH:
        raise GraphContextPacketIntegrationError(f"{field_name} is unsafe")
    if (
        _SENSITIVE_RE.search(value)
        or "\\" in value
        or ".." in value
        or any(ord(char) < 32 for char in value)
    ):
        raise GraphContextPacketIntegrationError(f"{field_name} is unsafe")
    return value


def _string_list(value: object, field_name: str) -> list[str]:
    if not isinstance(value, list) or len(value) > MAX_LIST_ITEMS:
        raise GraphContextPacketIntegrationError(f"{field_name} is invalid")
    result: list[str] = []
    for item in value:
        result.append(_safe_reference_text(item, field_name))
    return result


def _unique_append(base: list[str], additions: object) -> list[str]:
    result = list(base)
    if not isinstance(additions, list):
        raise GraphContextPacketIntegrationError("selection freshness list is invalid")
    for item in additions:
        text = _safe_reference_text(item, "selection freshness ref")
        if text not in result:
            result.append(text)
        if len(result) > MAX_LIST_ITEMS:
            raise GraphContextPacketIntegrationError("freshness refs exceed limit")
    return result


def _safe_token(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "-", value).strip("-._") or "graph"


def _digest(value: object) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return "sha256:" + hashlib.sha256(encoded.encode("utf-8")).hexdigest()


__all__ = [
    "canonicalize_graph_context_selection",
    "GraphContextPacketIntegrationError",
    "integrate_graph_context_selection",
]
