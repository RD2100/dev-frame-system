"""Durable, fail-closed governance event transitions.

This module owns only the root-gate request lifecycle. Persistence remains in
``TeamRuntime`` so governance facts do not acquire a second journal or write
authority.
"""
from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any


ROOT_GATE_EVENT_TYPE = "root_gate_event"
ROOT_GATE_SUBJECT_TYPE = "RootGateRequest"


class RootGateLifecycleError(ValueError):
    """Raised when root-gate history or a requested transition is invalid."""


@dataclass(frozen=True)
class PreparedRootGateTransition:
    """A validated event ready for TeamRuntime to append atomically."""

    run_id: str
    audit_event: dict[str, Any] | None = None
    existing_event_id: str = ""


def prepare_root_gate_request(
    records: list[dict[str, Any]],
    *,
    run_id: str,
    actor: str,
    request_id: str,
    dedupe_key: str,
    project_id: str,
    gate: str,
    summary: str,
    exact_write_set: list[str],
    evidence_refs: list[str],
    reason: str,
) -> PreparedRootGateTransition:
    """Validate a new request, returning the original event for an exact retry."""
    normalized_run_id = _required_text("run_id", run_id)
    normalized_actor = _required_text("actor", actor)
    normalized_request_id = _required_text("request_id", request_id)
    normalized_dedupe_key = _required_text("dedupe_key", dedupe_key)
    normalized_reason = _required_text("reason", reason)
    request = {
        "project_id": _required_text("project_id", project_id),
        "gate": _required_text("gate", gate),
        "summary": _required_text("summary", summary),
        "exact_write_set": _string_list("exact_write_set", exact_write_set),
        "evidence_refs": _string_list("evidence_refs", evidence_refs),
    }
    request_hash = _request_hash(
        run_id=normalized_run_id,
        actor=normalized_actor,
        request_id=normalized_request_id,
        dedupe_key=normalized_dedupe_key,
        reason=normalized_reason,
        request=request,
    )
    snapshots = fold_root_gate_requests(records)
    by_dedupe_key = {snapshot["dedupe_key"]: snapshot for snapshot in snapshots.values()}

    existing = by_dedupe_key.get(normalized_dedupe_key)
    if existing is not None:
        if (
            existing["request_id"] == normalized_request_id
            and existing["request_hash"] == request_hash
        ):
            return PreparedRootGateTransition(
                run_id=existing["run_id"],
                existing_event_id=existing["event_ids"][0],
            )
        raise RootGateLifecycleError(
            f"Conflicting root-gate request for dedupe key {normalized_dedupe_key}."
        )
    if normalized_request_id in snapshots:
        raise RootGateLifecycleError(
            f"Conflicting root-gate request ID {normalized_request_id}."
        )

    audit_event = _new_audit_event(
        request_id=normalized_request_id,
        actor=normalized_actor,
        action="requested",
        before_state="absent",
        after_state="requested",
        reason=normalized_reason,
        dedupe_key=normalized_dedupe_key,
        request_hash=request_hash,
        root_gate_request=request,
    )
    return PreparedRootGateTransition(
        run_id=normalized_run_id,
        audit_event=audit_event,
    )


def prepare_root_gate_acknowledgement(
    records: list[dict[str, Any]],
    *,
    request_id: str,
    actor: str,
    reason: str,
) -> PreparedRootGateTransition:
    return _prepare_existing_transition(
        records,
        request_id=request_id,
        actor=actor,
        reason=reason,
        action="acknowledged",
        required_state="requested",
        after_state="acknowledged",
    )


def prepare_root_gate_decision(
    records: list[dict[str, Any]],
    *,
    request_id: str,
    actor: str,
    decision: str,
    reason: str,
) -> PreparedRootGateTransition:
    normalized_decision = _required_text("decision", decision).lower()
    if normalized_decision not in {"authorized", "rejected"}:
        raise RootGateLifecycleError("Root-gate decision must be authorized or rejected.")
    return _prepare_existing_transition(
        records,
        request_id=request_id,
        actor=actor,
        reason=reason,
        action=normalized_decision,
        required_state="acknowledged",
        after_state=normalized_decision,
    )


def prepare_root_gate_dispatch(
    records: list[dict[str, Any]],
    *,
    request_id: str,
    actor: str,
    task_ids: list[str],
    reason: str,
) -> PreparedRootGateTransition:
    normalized_task_ids = _string_list("task_ids", task_ids, require_items=True)
    return _prepare_existing_transition(
        records,
        request_id=request_id,
        actor=actor,
        reason=reason,
        action="dispatched",
        required_state="authorized",
        after_state="dispatched",
        dispatch_task_ids=normalized_task_ids,
    )


def fold_root_gate_requests(records: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Reconstruct root-gate state from TeamRuntime records.

    Any malformed root-gate event fails the whole projection closed. Unrelated
    TeamRuntime events are intentionally ignored.
    """
    snapshots: dict[str, dict[str, Any]] = {}
    dedupe_keys: dict[str, str] = {}
    for record in records:
        if not isinstance(record, dict) or record.get("event_type") != ROOT_GATE_EVENT_TYPE:
            continue
        try:
            _fold_root_gate_record(record, snapshots, dedupe_keys)
        except RootGateLifecycleError:
            raise
        except (KeyError, TypeError, ValueError) as exc:
            raise RootGateLifecycleError("Malformed root-gate event in TeamRuntime journal.") from exc
    return snapshots


def _prepare_existing_transition(
    records: list[dict[str, Any]],
    *,
    request_id: str,
    actor: str,
    reason: str,
    action: str,
    required_state: str,
    after_state: str,
    dispatch_task_ids: list[str] | None = None,
) -> PreparedRootGateTransition:
    normalized_request_id = _required_text("request_id", request_id)
    snapshots = fold_root_gate_requests(records)
    snapshot = snapshots.get(normalized_request_id)
    if snapshot is None:
        raise RootGateLifecycleError(f"Unknown root-gate request ID {normalized_request_id}.")
    if snapshot["state"] != required_state:
        raise RootGateLifecycleError(
            f"Root-gate transition {action} requires state {required_state}; "
            f"found {snapshot['state']}."
        )
    audit_event = _new_audit_event(
        request_id=normalized_request_id,
        actor=_required_text("actor", actor),
        action=action,
        before_state=required_state,
        after_state=after_state,
        reason=_required_text("reason", reason),
        dedupe_key=snapshot["dedupe_key"],
        request_hash=snapshot["request_hash"],
        dispatch_task_ids=dispatch_task_ids,
    )
    return PreparedRootGateTransition(run_id=snapshot["run_id"], audit_event=audit_event)


def _fold_root_gate_record(
    record: dict[str, Any],
    snapshots: dict[str, dict[str, Any]],
    dedupe_keys: dict[str, str],
) -> None:
    run_id = _required_text("record.run_id", record.get("run_id"))
    audit_event = record.get("payload")
    if not isinstance(audit_event, dict):
        raise RootGateLifecycleError("Root-gate event payload must be an object.")
    event_id = _required_text("event_id", audit_event.get("event_id"))
    if event_id != _required_text("record.event_id", record.get("event_id")):
        raise RootGateLifecycleError("Root-gate event identity does not match its journal record.")
    timestamp = _required_text("timestamp", audit_event.get("timestamp"))
    if timestamp != _required_text("record.timestamp", record.get("timestamp")):
        raise RootGateLifecycleError("Root-gate event timestamp does not match its journal record.")
    if audit_event.get("subject_type") != ROOT_GATE_SUBJECT_TYPE:
        raise RootGateLifecycleError("Root-gate journal record has the wrong subject type.")

    actor = _required_text("actor", audit_event.get("actor"))
    reason = _required_text("reason", audit_event.get("reason"))
    request_id = _required_text("subject_id", audit_event.get("subject_id"))
    dedupe_key = _required_text("dedupe_key", audit_event.get("dedupe_key"))
    request_hash = _required_text("request_hash", audit_event.get("request_hash"))
    action = _required_text("action", audit_event.get("action"))
    before_state = _required_text("before_state", audit_event.get("before_state"))
    after_state = _required_text("after_state", audit_event.get("after_state"))

    if action == "requested":
        if request_id in snapshots or dedupe_key in dedupe_keys:
            raise RootGateLifecycleError("Duplicate root-gate request event in TeamRuntime journal.")
        if before_state != "absent" or after_state != "requested":
            raise RootGateLifecycleError("Root-gate request has an invalid state transition.")
        request = _normalize_persisted_request(audit_event.get("root_gate_request"))
        expected_hash = _request_hash(
            run_id=run_id,
            actor=actor,
            request_id=request_id,
            dedupe_key=dedupe_key,
            reason=reason,
            request=request,
        )
        if request_hash != expected_hash:
            raise RootGateLifecycleError("Root-gate request hash does not match its persisted payload.")
        snapshots[request_id] = {
            "request_id": request_id,
            "run_id": run_id,
            "dedupe_key": dedupe_key,
            "request_hash": request_hash,
            "state": "requested",
            "decision": "",
            "request": request,
            "dispatch_task_ids": [],
            "created_at": timestamp,
            "root_ack_at": "",
            "decision_at": "",
            "dispatch_at": "",
            "event_ids": [event_id],
        }
        dedupe_keys[dedupe_key] = request_id
        return

    snapshot = snapshots.get(request_id)
    if snapshot is None:
        raise RootGateLifecycleError(f"Unknown root-gate request ID {request_id} in journal.")
    if snapshot["run_id"] != run_id:
        raise RootGateLifecycleError("Root-gate transition changed the request run ID.")
    if snapshot["dedupe_key"] != dedupe_key or snapshot["request_hash"] != request_hash:
        raise RootGateLifecycleError("Root-gate transition changed immutable request identity.")

    expected = {
        "acknowledged": ("requested", "acknowledged"),
        "authorized": ("acknowledged", "authorized"),
        "rejected": ("acknowledged", "rejected"),
        "dispatched": ("authorized", "dispatched"),
    }.get(action)
    if expected is None:
        raise RootGateLifecycleError(f"Unsupported root-gate action {action}.")
    if snapshot["state"] != expected[0] or before_state != expected[0] or after_state != expected[1]:
        raise RootGateLifecycleError(f"Root-gate event {action} is out of order.")

    snapshot["state"] = after_state
    snapshot["event_ids"].append(event_id)
    if action == "acknowledged":
        snapshot["root_ack_at"] = timestamp
    if action in {"authorized", "rejected"}:
        snapshot["decision"] = action
        snapshot["decision_at"] = timestamp
    if action == "dispatched":
        snapshot["dispatch_task_ids"] = _string_list(
            "dispatch_task_ids",
            audit_event.get("dispatch_task_ids"),
            require_items=True,
        )
        snapshot["dispatch_at"] = timestamp


def _new_audit_event(
    *,
    request_id: str,
    actor: str,
    action: str,
    before_state: str,
    after_state: str,
    reason: str,
    dedupe_key: str,
    request_hash: str,
    root_gate_request: dict[str, Any] | None = None,
    dispatch_task_ids: list[str] | None = None,
) -> dict[str, Any]:
    event = {
        "event_id": f"ae-root-gate-{_slug(request_id)}-{action}-{uuid.uuid4().hex[:10]}",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "actor": actor,
        "action": action,
        "subject_type": ROOT_GATE_SUBJECT_TYPE,
        "subject_id": request_id,
        "before_state": before_state,
        "after_state": after_state,
        "reason": reason,
        "dedupe_key": dedupe_key,
        "request_hash": request_hash,
    }
    if root_gate_request is not None:
        event["root_gate_request"] = root_gate_request
    if dispatch_task_ids is not None:
        event["dispatch_task_ids"] = dispatch_task_ids
    return event


def _normalize_persisted_request(value: object) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise RootGateLifecycleError("Root-gate request payload must be an object.")
    expected_keys = {"project_id", "gate", "summary", "exact_write_set", "evidence_refs"}
    if set(value) != expected_keys:
        raise RootGateLifecycleError("Root-gate request payload has unexpected or missing fields.")
    return {
        "project_id": _required_text("project_id", value.get("project_id")),
        "gate": _required_text("gate", value.get("gate")),
        "summary": _required_text("summary", value.get("summary")),
        "exact_write_set": _string_list("exact_write_set", value.get("exact_write_set")),
        "evidence_refs": _string_list("evidence_refs", value.get("evidence_refs")),
    }


def _request_hash(
    *,
    run_id: str,
    actor: str,
    request_id: str,
    dedupe_key: str,
    reason: str,
    request: dict[str, Any],
) -> str:
    material = {
        "run_id": run_id,
        "actor": actor,
        "request_id": request_id,
        "dedupe_key": dedupe_key,
        "reason": reason,
        "request": request,
    }
    encoded = json.dumps(material, ensure_ascii=True, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _required_text(name: str, value: object) -> str:
    text = str(value or "").strip()
    if not text:
        raise RootGateLifecycleError(f"Root-gate {name} must be non-empty.")
    return text


def _string_list(name: str, value: object, *, require_items: bool = False) -> list[str]:
    if not isinstance(value, list):
        raise RootGateLifecycleError(f"Root-gate {name} must be a list.")
    normalized: list[str] = []
    seen: set[str] = set()
    for item in value:
        text = _required_text(name, item)
        if text in seen:
            raise RootGateLifecycleError(f"Root-gate {name} must not contain duplicates.")
        seen.add(text)
        normalized.append(text)
    if require_items and not normalized:
        raise RootGateLifecycleError(f"Root-gate {name} must not be empty.")
    return normalized


def _slug(value: object) -> str:
    text = "".join(
        character if (character.isalnum() or character == "-") else "-"
        for character in str(value or "").strip().lower()
    ).strip("-")
    while "--" in text:
        text = text.replace("--", "-")
    return text or "x"
