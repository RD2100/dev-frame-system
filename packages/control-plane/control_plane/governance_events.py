"""Durable, fail-closed governance event transitions.

This module owns root-gate and concurrent-slice allowlist event validation.
Persistence remains in ``TeamRuntime`` so governance facts do not acquire a
second journal or write authority.
"""
from __future__ import annotations

import hashlib
import json
import unicodedata
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any


ROOT_GATE_EVENT_TYPE = "root_gate_event"
ROOT_GATE_SUBJECT_TYPE = "RootGateRequest"
CONCURRENT_SLICE_ALLOWLIST_EVENT_TYPE = "concurrent_slice_allowlist_event"
CONCURRENT_SLICE_ALLOWLIST_SUBJECT_TYPE = "ConcurrentSliceAllowlist"
CONCURRENT_SLICE_ALLOWLIST_DELTA_SUBJECT_TYPE = "ConcurrentSliceAllowlistDelta"
_WINDOWS_RESERVED_PATH_NAMES = frozenset(
    {"con", "prn", "aux", "nul"}
    | {f"com{index}" for index in range(1, 10)}
    | {f"lpt{index}" for index in range(1, 10)}
)
_WINDOWS_FORBIDDEN_PATH_CHARACTERS = frozenset('<>:"|?*')


class RootGateLifecycleError(ValueError):
    """Raised when root-gate history or a requested transition is invalid."""


class ConcurrentSliceAllowlistError(ValueError):
    """Raised when concurrent-slice allowlist history or input is invalid."""


@dataclass(frozen=True)
class PreparedRootGateTransition:
    """A validated event ready for TeamRuntime to append atomically."""

    run_id: str
    audit_event: dict[str, Any] | None = None
    existing_event_id: str = ""


@dataclass(frozen=True)
class PreparedConcurrentSliceAllowlistEvent:
    """A validated allowlist event ready for TeamRuntime to append atomically."""

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


def prepare_concurrent_slice_allowlist_baseline(
    records: list[dict[str, Any]],
    *,
    run_id: str,
    actor: str,
    reviewer_task_id: str,
    dedupe_key: str,
    checkout_identity: str,
    exact_repo_paths: list[str],
    baseline_manifest: str,
    baseline_hash: str,
    version: int,
    reason: str,
) -> PreparedConcurrentSliceAllowlistEvent:
    """Validate and prepare a reviewer's initial concurrent-path baseline."""
    normalized_run_id = _allowlist_required_text("run_id", run_id)
    normalized_actor = _allowlist_required_text("actor", actor)
    normalized_reviewer_task_id = _allowlist_required_text(
        "reviewer_task_id", reviewer_task_id
    )
    normalized_dedupe_key = _allowlist_required_text("dedupe_key", dedupe_key)
    normalized_reason = _allowlist_required_text("reason", reason)
    payload = {
        "reviewer_task_id": normalized_reviewer_task_id,
        "checkout_identity": _allowlist_required_text(
            "checkout_identity", checkout_identity
        ),
        "exact_repo_paths": _normalized_repo_paths(
            "exact_repo_paths", exact_repo_paths, require_items=False
        ),
        "baseline_manifest": _allowlist_required_text(
            "baseline_manifest", baseline_manifest
        ),
        "baseline_hash": _allowlist_sha256("baseline_hash", baseline_hash),
        "version": _positive_version("version", version),
    }
    event_hash = _allowlist_event_hash(
        run_id=normalized_run_id,
        actor=normalized_actor,
        subject_type=CONCURRENT_SLICE_ALLOWLIST_SUBJECT_TYPE,
        subject_id=normalized_reviewer_task_id,
        action="created",
        reason=normalized_reason,
        dedupe_key=normalized_dedupe_key,
        payload=payload,
    )
    snapshots = fold_concurrent_slice_allowlists(records)
    existing = _allowlist_provenance_by_dedupe(snapshots).get(normalized_dedupe_key)
    if existing is not None:
        if existing["allowlist_hash"] == event_hash:
            return PreparedConcurrentSliceAllowlistEvent(
                run_id=existing["run_id"],
                existing_event_id=existing["event_id"],
            )
        raise ConcurrentSliceAllowlistError(
            f"Conflicting concurrent-slice allowlist event for dedupe key "
            f"{normalized_dedupe_key}."
        )
    if normalized_reviewer_task_id in snapshots:
        raise ConcurrentSliceAllowlistError(
            f"Concurrent reviewer {normalized_reviewer_task_id} is already registered."
        )

    return PreparedConcurrentSliceAllowlistEvent(
        run_id=normalized_run_id,
        audit_event=_new_allowlist_audit_event(
            actor=normalized_actor,
            action="created",
            subject_type=CONCURRENT_SLICE_ALLOWLIST_SUBJECT_TYPE,
            subject_id=normalized_reviewer_task_id,
            before_state="absent",
            after_state=_version_state(payload["version"]),
            reason=normalized_reason,
            dedupe_key=normalized_dedupe_key,
            allowlist_hash=event_hash,
            baseline=payload,
        ),
    )


def prepare_concurrent_slice_allowlist_delta(
    records: list[dict[str, Any]],
    *,
    actor: str,
    reviewer_task_id: str,
    writer_task_id: str,
    dedupe_key: str,
    checkout_identity: str,
    exact_repo_paths: list[str],
    baseline_manifest: str,
    baseline_hash: str,
    previous_version: int,
    new_version: int,
    delivered_at: str,
    first_file_change_at: str,
    reason: str,
) -> PreparedConcurrentSliceAllowlistEvent:
    """Validate one delivered writer authorization against its reviewer baseline."""
    normalized_actor = _allowlist_required_text("actor", actor)
    normalized_reviewer_task_id = _allowlist_required_text(
        "reviewer_task_id", reviewer_task_id
    )
    normalized_dedupe_key = _allowlist_required_text("dedupe_key", dedupe_key)
    normalized_reason = _allowlist_required_text("reason", reason)
    delivered_timestamp, delivered_moment = _allowlist_timestamp(
        "delivered_at", delivered_at
    )
    first_change_timestamp, first_change_moment = _allowlist_timestamp(
        "first_file_change_at", first_file_change_at
    )
    if delivered_moment >= first_change_moment:
        raise ConcurrentSliceAllowlistError(
            "Concurrent-slice allowlist delivered_at must be before "
            "first_file_change_at."
        )
    payload = {
        "reviewer_task_id": normalized_reviewer_task_id,
        "writer_task_id": _allowlist_required_text("writer_task_id", writer_task_id),
        "checkout_identity": _allowlist_required_text(
            "checkout_identity", checkout_identity
        ),
        "exact_repo_paths": _normalized_repo_paths(
            "exact_repo_paths", exact_repo_paths, require_items=True
        ),
        "baseline_manifest": _allowlist_required_text(
            "baseline_manifest", baseline_manifest
        ),
        "baseline_hash": _allowlist_sha256("baseline_hash", baseline_hash),
        "previous_version": _positive_version("previous_version", previous_version),
        "new_version": _positive_version("new_version", new_version),
        "delivered_at": delivered_timestamp,
        "first_file_change_at": first_change_timestamp,
    }
    snapshots = fold_concurrent_slice_allowlists(records)
    snapshot = snapshots.get(normalized_reviewer_task_id)
    if snapshot is None:
        raise ConcurrentSliceAllowlistError(
            f"Unknown concurrent reviewer {normalized_reviewer_task_id}."
        )
    event_hash = _allowlist_event_hash(
        run_id=snapshot["run_id"],
        actor=normalized_actor,
        subject_type=CONCURRENT_SLICE_ALLOWLIST_DELTA_SUBJECT_TYPE,
        subject_id=normalized_reviewer_task_id,
        action="authorized",
        reason=normalized_reason,
        dedupe_key=normalized_dedupe_key,
        payload=payload,
    )
    existing = _allowlist_provenance_by_dedupe(snapshots).get(normalized_dedupe_key)
    if existing is not None:
        if existing["allowlist_hash"] == event_hash:
            return PreparedConcurrentSliceAllowlistEvent(
                run_id=existing["run_id"],
                existing_event_id=existing["event_id"],
            )
        raise ConcurrentSliceAllowlistError(
            f"Conflicting concurrent-slice allowlist event for dedupe key "
            f"{normalized_dedupe_key}."
        )

    _validate_delta_against_snapshot(payload, snapshot)
    return PreparedConcurrentSliceAllowlistEvent(
        run_id=snapshot["run_id"],
        audit_event=_new_allowlist_audit_event(
            actor=normalized_actor,
            action="authorized",
            subject_type=CONCURRENT_SLICE_ALLOWLIST_DELTA_SUBJECT_TYPE,
            subject_id=normalized_reviewer_task_id,
            before_state=_version_state(payload["previous_version"]),
            after_state=_version_state(payload["new_version"]),
            reason=normalized_reason,
            dedupe_key=normalized_dedupe_key,
            allowlist_hash=event_hash,
            delta=payload,
        ),
    )


def fold_concurrent_slice_allowlists(
    records: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Reconstruct all current concurrent-path allowlists and provenance."""
    snapshots: dict[str, dict[str, Any]] = {}
    dedupe_keys: set[str] = set()
    for record in records:
        if (
            not isinstance(record, dict)
            or record.get("event_type") != CONCURRENT_SLICE_ALLOWLIST_EVENT_TYPE
        ):
            continue
        try:
            _fold_concurrent_slice_allowlist_record(record, snapshots, dedupe_keys)
        except ConcurrentSliceAllowlistError:
            raise
        except (KeyError, TypeError, ValueError) as exc:
            raise ConcurrentSliceAllowlistError(
                "Malformed concurrent-slice allowlist event in TeamRuntime journal."
            ) from exc
    return snapshots


def _fold_concurrent_slice_allowlist_record(
    record: dict[str, Any],
    snapshots: dict[str, dict[str, Any]],
    dedupe_keys: set[str],
) -> None:
    run_id = _allowlist_required_text("record.run_id", record.get("run_id"))
    audit_event = record.get("payload")
    if not isinstance(audit_event, dict):
        raise ConcurrentSliceAllowlistError(
            "Concurrent-slice allowlist event payload must be an object."
        )
    subject_type = _allowlist_required_text(
        "subject_type", audit_event.get("subject_type")
    )
    payload_field = {
        CONCURRENT_SLICE_ALLOWLIST_SUBJECT_TYPE: "concurrent_slice_allowlist",
        CONCURRENT_SLICE_ALLOWLIST_DELTA_SUBJECT_TYPE: (
            "concurrent_slice_allowlist_delta"
        ),
    }.get(subject_type)
    if payload_field is None:
        raise ConcurrentSliceAllowlistError(
            f"Unsupported concurrent-slice allowlist subject type {subject_type}."
        )
    expected_event_keys = {
        "event_id",
        "timestamp",
        "actor",
        "action",
        "subject_type",
        "subject_id",
        "before_state",
        "after_state",
        "reason",
        "dedupe_key",
        "allowlist_hash",
        payload_field,
    }
    if set(audit_event) != expected_event_keys:
        raise ConcurrentSliceAllowlistError(
            "Concurrent-slice allowlist event has unexpected or missing fields."
        )

    event_id = _allowlist_required_text("event_id", audit_event.get("event_id"))
    if event_id != _allowlist_required_text("record.event_id", record.get("event_id")):
        raise ConcurrentSliceAllowlistError(
            "Concurrent-slice allowlist event identity does not match its journal record."
        )
    timestamp = _allowlist_required_text("timestamp", audit_event.get("timestamp"))
    _allowlist_timestamp("timestamp", timestamp)
    if timestamp != _allowlist_required_text("record.timestamp", record.get("timestamp")):
        raise ConcurrentSliceAllowlistError(
            "Concurrent-slice allowlist timestamp does not match its journal record."
        )
    actor = _allowlist_required_text("actor", audit_event.get("actor"))
    if actor != _allowlist_required_text("record.agent_id", record.get("agent_id")):
        raise ConcurrentSliceAllowlistError(
            "Concurrent-slice allowlist actor does not match its journal record."
        )
    action = _allowlist_required_text("action", audit_event.get("action"))
    reviewer_task_id = _allowlist_required_text(
        "subject_id", audit_event.get("subject_id")
    )
    before_state = _allowlist_required_text(
        "before_state", audit_event.get("before_state")
    )
    after_state = _allowlist_required_text("after_state", audit_event.get("after_state"))
    reason = _allowlist_required_text("reason", audit_event.get("reason"))
    dedupe_key = _allowlist_required_text("dedupe_key", audit_event.get("dedupe_key"))
    allowlist_hash = _allowlist_sha256(
        "allowlist_hash", audit_event.get("allowlist_hash")
    )
    if dedupe_key in dedupe_keys:
        raise ConcurrentSliceAllowlistError(
            f"Duplicate concurrent-slice allowlist dedupe key {dedupe_key} in journal."
        )

    if subject_type == CONCURRENT_SLICE_ALLOWLIST_SUBJECT_TYPE:
        baseline = _normalize_allowlist_baseline(audit_event[payload_field])
        if action != "created" or before_state != "absent":
            raise ConcurrentSliceAllowlistError(
                "Concurrent-slice allowlist baseline has an invalid state transition."
            )
        if after_state != _version_state(baseline["version"]):
            raise ConcurrentSliceAllowlistError(
                "Concurrent-slice allowlist baseline state does not match its version."
            )
        if baseline["reviewer_task_id"] != reviewer_task_id:
            raise ConcurrentSliceAllowlistError(
                "Concurrent-slice allowlist baseline changed reviewer identity."
            )
        if reviewer_task_id in snapshots:
            raise ConcurrentSliceAllowlistError(
                f"Duplicate concurrent reviewer {reviewer_task_id} in journal."
            )
        expected_hash = _allowlist_event_hash(
            run_id=run_id,
            actor=actor,
            subject_type=subject_type,
            subject_id=reviewer_task_id,
            action=action,
            reason=reason,
            dedupe_key=dedupe_key,
            payload=baseline,
        )
        if allowlist_hash != expected_hash:
            raise ConcurrentSliceAllowlistError(
                "Concurrent-slice allowlist hash does not match its baseline payload."
            )
        snapshots[reviewer_task_id] = {
            "reviewer_task_id": reviewer_task_id,
            "run_id": run_id,
            "checkout_identity": baseline["checkout_identity"],
            "baseline_manifest": baseline["baseline_manifest"],
            "baseline_hash": baseline["baseline_hash"],
            "version": baseline["version"],
            "allowed_paths_by_task": {
                reviewer_task_id: list(baseline["exact_repo_paths"])
            },
            "allowed_concurrent_paths": list(baseline["exact_repo_paths"]),
            "event_ids": [event_id],
            "provenance": [
                {
                    "kind": "baseline",
                    "event_id": event_id,
                    "run_id": run_id,
                    "timestamp": timestamp,
                    "actor": actor,
                    "dedupe_key": dedupe_key,
                    "allowlist_hash": allowlist_hash,
                    "reviewer_task_id": reviewer_task_id,
                    "exact_repo_paths": list(baseline["exact_repo_paths"]),
                    "version": baseline["version"],
                }
            ],
        }
        dedupe_keys.add(dedupe_key)
        return

    delta = _normalize_allowlist_delta(audit_event[payload_field])
    if action != "authorized":
        raise ConcurrentSliceAllowlistError(
            "Concurrent-slice allowlist delta has an unsupported action."
        )
    if delta["reviewer_task_id"] != reviewer_task_id:
        raise ConcurrentSliceAllowlistError(
            "Concurrent-slice allowlist delta changed reviewer identity."
        )
    snapshot = snapshots.get(reviewer_task_id)
    if snapshot is None:
        raise ConcurrentSliceAllowlistError(
            f"Unknown concurrent reviewer {reviewer_task_id} in journal."
        )
    if snapshot["run_id"] != run_id:
        raise ConcurrentSliceAllowlistError(
            "Concurrent-slice allowlist delta changed run identity."
        )
    if (
        before_state != _version_state(delta["previous_version"])
        or after_state != _version_state(delta["new_version"])
    ):
        raise ConcurrentSliceAllowlistError(
            "Concurrent-slice allowlist delta state does not match its versions."
        )
    expected_hash = _allowlist_event_hash(
        run_id=run_id,
        actor=actor,
        subject_type=subject_type,
        subject_id=reviewer_task_id,
        action=action,
        reason=reason,
        dedupe_key=dedupe_key,
        payload=delta,
    )
    if allowlist_hash != expected_hash:
        raise ConcurrentSliceAllowlistError(
            "Concurrent-slice allowlist hash does not match its delta payload."
        )
    _validate_delta_against_snapshot(delta, snapshot)

    writer_task_id = delta["writer_task_id"]
    snapshot["version"] = delta["new_version"]
    snapshot["allowed_paths_by_task"][writer_task_id] = list(
        delta["exact_repo_paths"]
    )
    snapshot["allowed_concurrent_paths"] = [
        path
        for paths in snapshot["allowed_paths_by_task"].values()
        for path in paths
    ]
    snapshot["event_ids"].append(event_id)
    snapshot["provenance"].append(
        {
            "kind": "delta",
            "event_id": event_id,
            "run_id": run_id,
            "timestamp": timestamp,
            "actor": actor,
            "dedupe_key": dedupe_key,
            "allowlist_hash": allowlist_hash,
            "writer_task_id": writer_task_id,
            "exact_repo_paths": list(delta["exact_repo_paths"]),
            "previous_version": delta["previous_version"],
            "new_version": delta["new_version"],
            "delivered_at": delta["delivered_at"],
            "first_file_change_at": delta["first_file_change_at"],
        }
    )
    dedupe_keys.add(dedupe_key)


def _validate_delta_against_snapshot(
    delta: dict[str, Any],
    snapshot: dict[str, Any],
) -> None:
    if delta["checkout_identity"] != snapshot["checkout_identity"]:
        raise ConcurrentSliceAllowlistError(
            "Concurrent-slice allowlist checkout identity does not match its baseline."
        )
    if (
        delta["baseline_manifest"] != snapshot["baseline_manifest"]
        or delta["baseline_hash"] != snapshot["baseline_hash"]
    ):
        raise ConcurrentSliceAllowlistError(
            "Concurrent-slice allowlist baseline evidence does not match registration."
        )
    if delta["previous_version"] != snapshot["version"]:
        raise ConcurrentSliceAllowlistError(
            "Concurrent-slice allowlist previous_version does not match current version."
        )
    if delta["new_version"] != delta["previous_version"] + 1:
        raise ConcurrentSliceAllowlistError(
            "Concurrent-slice allowlist new_version must be contiguous with "
            "previous_version."
        )
    writer_task_id = delta["writer_task_id"]
    if writer_task_id in snapshot["allowed_paths_by_task"]:
        raise ConcurrentSliceAllowlistError(
            f"Concurrent writer {writer_task_id} is already registered."
        )
    existing_paths = {
        _repo_path_collision_key(path): path
        for path in snapshot["allowed_concurrent_paths"]
    }
    collisions: dict[str, str] = {}
    for path in delta["exact_repo_paths"]:
        collision_key = _repo_path_collision_key(path)
        if collision_key in existing_paths:
            collisions[path] = existing_paths[collision_key]
    if collisions:
        details = ", ".join(
            f"{path} -> {existing}"
            for path, existing in sorted(collisions.items())
        )
        raise ConcurrentSliceAllowlistError(
            "Concurrent-slice allowlist exact_repo_paths collision would overlap "
            f"existing paths: {details}."
        )


def _normalize_allowlist_baseline(value: object) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ConcurrentSliceAllowlistError(
            "Concurrent-slice allowlist baseline must be an object."
        )
    expected_keys = {
        "reviewer_task_id",
        "checkout_identity",
        "exact_repo_paths",
        "baseline_manifest",
        "baseline_hash",
        "version",
    }
    if set(value) != expected_keys:
        raise ConcurrentSliceAllowlistError(
            "Concurrent-slice allowlist baseline has unexpected or missing fields."
        )
    return {
        "reviewer_task_id": _allowlist_required_text(
            "reviewer_task_id", value.get("reviewer_task_id")
        ),
        "checkout_identity": _allowlist_required_text(
            "checkout_identity", value.get("checkout_identity")
        ),
        "exact_repo_paths": _normalized_repo_paths(
            "exact_repo_paths", value.get("exact_repo_paths"), require_items=False
        ),
        "baseline_manifest": _allowlist_required_text(
            "baseline_manifest", value.get("baseline_manifest")
        ),
        "baseline_hash": _allowlist_sha256(
            "baseline_hash", value.get("baseline_hash")
        ),
        "version": _positive_version("version", value.get("version")),
    }


def _normalize_allowlist_delta(value: object) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ConcurrentSliceAllowlistError(
            "Concurrent-slice allowlist delta must be an object."
        )
    expected_keys = {
        "reviewer_task_id",
        "writer_task_id",
        "checkout_identity",
        "exact_repo_paths",
        "baseline_manifest",
        "baseline_hash",
        "previous_version",
        "new_version",
        "delivered_at",
        "first_file_change_at",
    }
    if set(value) != expected_keys:
        raise ConcurrentSliceAllowlistError(
            "Concurrent-slice allowlist delta has unexpected or missing fields."
        )
    delivered_at, delivered_moment = _allowlist_timestamp(
        "delivered_at", value.get("delivered_at")
    )
    first_file_change_at, first_change_moment = _allowlist_timestamp(
        "first_file_change_at", value.get("first_file_change_at")
    )
    if delivered_moment >= first_change_moment:
        raise ConcurrentSliceAllowlistError(
            "Concurrent-slice allowlist delivered_at must be before "
            "first_file_change_at."
        )
    return {
        "reviewer_task_id": _allowlist_required_text(
            "reviewer_task_id", value.get("reviewer_task_id")
        ),
        "writer_task_id": _allowlist_required_text(
            "writer_task_id", value.get("writer_task_id")
        ),
        "checkout_identity": _allowlist_required_text(
            "checkout_identity", value.get("checkout_identity")
        ),
        "exact_repo_paths": _normalized_repo_paths(
            "exact_repo_paths", value.get("exact_repo_paths"), require_items=True
        ),
        "baseline_manifest": _allowlist_required_text(
            "baseline_manifest", value.get("baseline_manifest")
        ),
        "baseline_hash": _allowlist_sha256(
            "baseline_hash", value.get("baseline_hash")
        ),
        "previous_version": _positive_version(
            "previous_version", value.get("previous_version")
        ),
        "new_version": _positive_version("new_version", value.get("new_version")),
        "delivered_at": delivered_at,
        "first_file_change_at": first_file_change_at,
    }


def _new_allowlist_audit_event(
    *,
    actor: str,
    action: str,
    subject_type: str,
    subject_id: str,
    before_state: str,
    after_state: str,
    reason: str,
    dedupe_key: str,
    allowlist_hash: str,
    baseline: dict[str, Any] | None = None,
    delta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    version = (baseline or delta or {}).get("version") or (delta or {}).get(
        "new_version"
    )
    event = {
        "event_id": (
            f"ae-concurrent-allowlist-{_slug(subject_id)}-v{version}-"
            f"{uuid.uuid4().hex[:10]}"
        ),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "actor": actor,
        "action": action,
        "subject_type": subject_type,
        "subject_id": subject_id,
        "before_state": before_state,
        "after_state": after_state,
        "reason": reason,
        "dedupe_key": dedupe_key,
        "allowlist_hash": allowlist_hash,
    }
    if baseline is not None:
        event["concurrent_slice_allowlist"] = baseline
    if delta is not None:
        event["concurrent_slice_allowlist_delta"] = delta
    return event


def _allowlist_event_hash(
    *,
    run_id: str,
    actor: str,
    subject_type: str,
    subject_id: str,
    action: str,
    reason: str,
    dedupe_key: str,
    payload: dict[str, Any],
) -> str:
    material = {
        "run_id": run_id,
        "actor": actor,
        "subject_type": subject_type,
        "subject_id": subject_id,
        "action": action,
        "reason": reason,
        "dedupe_key": dedupe_key,
        "payload": payload,
    }
    encoded = json.dumps(material, ensure_ascii=True, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _allowlist_provenance_by_dedupe(
    snapshots: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    return {
        item["dedupe_key"]: item
        for snapshot in snapshots.values()
        for item in snapshot["provenance"]
    }


def _allowlist_required_text(name: str, value: object) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ConcurrentSliceAllowlistError(
            f"Concurrent-slice allowlist {name} must be a non-empty normalized string."
        )
    return value


def _allowlist_sha256(name: str, value: object) -> str:
    text = _allowlist_required_text(name, value)
    if len(text) != 64 or any(character not in "0123456789abcdef" for character in text):
        raise ConcurrentSliceAllowlistError(
            f"Concurrent-slice allowlist {name} must be a lowercase SHA-256 digest."
        )
    return text


def _positive_version(name: str, value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ConcurrentSliceAllowlistError(
            f"Concurrent-slice allowlist {name} must be a positive integer version."
        )
    return value


def _normalized_repo_paths(
    name: str,
    value: object,
    *,
    require_items: bool,
) -> list[str]:
    if not isinstance(value, list):
        raise ConcurrentSliceAllowlistError(
            f"Concurrent-slice allowlist {name} must be a list."
        )
    normalized: list[str] = []
    seen_collision_keys: set[str] = set()
    for item in value:
        if not isinstance(item, str) or not item or item != item.strip():
            raise ConcurrentSliceAllowlistError(
                f"Concurrent-slice allowlist {name} contains an invalid path."
            )
        parts = item.split("/")
        is_drive_path = len(item) >= 2 and item[0].isalpha() and item[1] == ":"
        if (
            item.startswith("/")
            or is_drive_path
            or "\\" in item
            or any(part in {"", ".", ".."} for part in parts)
            or any(_is_windows_ambiguous_segment(part) for part in parts)
        ):
            raise ConcurrentSliceAllowlistError(
                f"Concurrent-slice allowlist {name} must contain normalized "
                "repository-relative POSIX paths without Windows-ambiguous segments."
            )
        collision_key = _repo_path_collision_key(item)
        if collision_key in seen_collision_keys:
            raise ConcurrentSliceAllowlistError(
                f"Concurrent-slice allowlist {name} contains a case-insensitive "
                "path collision."
            )
        seen_collision_keys.add(collision_key)
        normalized.append(item)
    if require_items and not normalized:
        raise ConcurrentSliceAllowlistError(
            f"Concurrent-slice allowlist {name} must not be empty."
        )
    return normalized


def _allowlist_timestamp(name: str, value: object) -> tuple[str, datetime]:
    text = _allowlist_required_text(name, value)
    try:
        moment = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ConcurrentSliceAllowlistError(
            f"Concurrent-slice allowlist {name} must be an ISO8601 timestamp."
        ) from exc
    if moment.tzinfo is None or moment.utcoffset() is None:
        raise ConcurrentSliceAllowlistError(
            f"Concurrent-slice allowlist {name} must include a timezone."
        )
    normalized = moment.astimezone(timezone.utc)
    return normalized.isoformat(), normalized


def _version_state(version: int) -> str:
    return f"version:{version}"


def _repo_path_collision_key(path: str) -> str:
    return unicodedata.normalize("NFC", path).casefold()


def _is_windows_ambiguous_segment(segment: str) -> bool:
    if segment.endswith((".", " ")):
        return True
    if any(
        character in _WINDOWS_FORBIDDEN_PATH_CHARACTERS or ord(character) < 32
        for character in segment
    ):
        return True
    device_stem = segment.split(".", maxsplit=1)[0].rstrip(" .").casefold()
    return device_stem in _WINDOWS_RESERVED_PATH_NAMES


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
    source = str(value or "").strip()
    text = "".join(
        character.lower()
        if (character.isascii() and (character.isalnum() or character == "-"))
        else "-"
        for character in source
    ).strip("-")
    while "--" in text:
        text = text.replace("--", "-")
    text = text or "x"
    if any(not character.isascii() for character in source):
        digest = hashlib.sha256(source.encode("utf-8")).hexdigest()[:12]
        text = f"{text}-{digest}"
    return text
