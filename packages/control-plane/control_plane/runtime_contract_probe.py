"In-memory checks for Phase 1/2-pre control-plane runtime contracts."
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable


ACTIVE_ASSIGNMENT_STATUSES = {"created", "queued", "leased", "dispatched"}
ACTIVE_LOCK_STATUSES = {"requested", "active"}
WRITE_LOCK_MODES = {"write", "exclusive"}
PROMOTION_FIELDS = {
    "task_success",
    "task_accepted",
    "reviewer_accepted",
    "governance_accepted",
    "release_approved",
    "final_verdict",
}
PAPER_REAL_CONTENT_SCOPE = "paper_real_content"
WRITELAB_LIVE_SCOPE = "writelab_live_dispatch"
REAL_PAPER_CLASSIFICATIONS = {
    "real_content",
    "real_paper_full_text",
    "user_authorized_excerpt",
}
LIVE_DISPATCH_VALUES = {"live", "writelab_live", "live_writelab", "opencode_live"}


@dataclass(frozen=True)
class ProbeViolation:
    code: str
    message: str
    record_id: str = ""


@dataclass(frozen=True)
class TransitionResult:
    allowed: bool
    code: str
    message: str
    record_id: str = ""


class DryRunRuntimeStateMachine:
    """Minimal in-memory state machine for future lease/lock runtime checks."""

    def __init__(self, records: Iterable[dict[str, Any]] | None = None):
        self.records = list(records or [])

    def dispatch_assignment(self, assignment: dict[str, Any]) -> TransitionResult:
        auth_violation = _runtime_authorization_violation(assignment, self.records)
        if auth_violation:
            assignment_id = assignment.get("assignment_id", "")
            self._audit(
                "runtime_authorization_required",
                assignment_id=assignment_id,
                task_id=assignment.get("task_id"),
                result="blocked",
                notes=auth_violation.message,
            )
            self._failure(
                "runtime_authorization_missing",
                assignment_id=assignment_id,
                retryable=False,
                required_next_action="human_required",
                error_summary=auth_violation.message,
            )
            return TransitionResult(False, auth_violation.code, auth_violation.message, assignment_id)

        duplicate = self._active_assignment_by_idempotency(assignment.get("idempotency_key"))
        if duplicate:
            assignment_id = duplicate.get("assignment_id", "")
            self._audit(
                "duplicate_dispatch_detected",
                assignment_id=assignment_id,
                idempotency_key=assignment.get("idempotency_key"),
                result="blocked",
            )
            self._failure(
                "duplicate_dispatch",
                assignment_id=assignment_id,
                retryable=False,
                required_next_action="block_assignment",
            )
            return TransitionResult(False, "DUPLICATE_DISPATCH", "Duplicate dispatch blocked.", assignment_id)

        assignment = dict(assignment)
        assignment.setdefault("contract_type", "DispatchAssignment")
        assignment.setdefault("status", "dispatched")
        assignment["acceptance_authority"] = False
        for field in PROMOTION_FIELDS:
            assignment.pop(field, None)
        self.records.append(assignment)
        self._audit("assignment_created", assignment_id=assignment.get("assignment_id"), result="recorded")
        return TransitionResult(True, "ASSIGNMENT_DISPATCHED", "Assignment dispatched.", assignment.get("assignment_id", ""))

    def acquire_lease(self, lease: dict[str, Any]) -> TransitionResult:
        assignment = self._assignment(lease.get("assignment_id"))
        if not assignment:
            return TransitionResult(False, "ASSIGNMENT_NOT_FOUND", "Assignment not found.")
        lease = dict(lease)
        lease.setdefault("contract_type", "WorkerLease")
        lease["status"] = "active"
        self.records.append(lease)
        assignment["status"] = "leased"
        assignment["lease_id"] = lease.get("lease_id")
        self._audit("lease_acquired", assignment_id=assignment.get("assignment_id"), lease_id=lease.get("lease_id"))
        return TransitionResult(True, "LEASE_ACQUIRED", "WorkerLease acquired.", lease.get("lease_id", ""))

    def record_heartbeat(self, lease_id: str, heartbeat_at: str) -> TransitionResult:
        lease = self._lease(lease_id)
        if not lease:
            return TransitionResult(False, "LEASE_NOT_FOUND", "WorkerLease not found.", lease_id)
        if lease.get("status") not in {"active", "renewed"}:
            return TransitionResult(False, "LEASE_INACTIVE", "Heartbeat rejected for inactive WorkerLease.", lease_id)
        lease["heartbeat_at"] = heartbeat_at
        lease["status"] = "renewed"
        self._audit("heartbeat_recorded", assignment_id=lease.get("assignment_id"), lease_id=lease_id)
        return TransitionResult(True, "HEARTBEAT_RECORDED", "Heartbeat recorded.", lease_id)

    def acquire_source_lock(self, source_lock: dict[str, Any]) -> TransitionResult:
        source_lock = dict(source_lock)
        source_lock.setdefault("contract_type", "SourceLock")
        source_lock["status"] = "active"
        conflict = self._conflicting_lock(source_lock)
        if conflict:
            source_lock["status"] = "conflict"
            self.records.append(source_lock)
            self._audit(
                "source_lock_conflict",
                assignment_id=source_lock.get("assignment_id"),
                lease_id=source_lock.get("lease_id"),
                lock_id=source_lock.get("lock_id"),
                result="blocked",
            )
            self._failure(
                "source_lock_conflict",
                assignment_id=source_lock.get("assignment_id"),
                retryable=False,
                required_next_action="block_assignment",
            )
            return TransitionResult(False, "OVERLAP_SOURCE_LOCK", "Overlapping SourceLock blocked.", source_lock.get("lock_id", ""))

        self.records.append(source_lock)
        self._audit(
            "source_lock_acquired",
            assignment_id=source_lock.get("assignment_id"),
            lease_id=source_lock.get("lease_id"),
            lock_id=source_lock.get("lock_id"),
        )
        return TransitionResult(True, "SOURCE_LOCK_ACQUIRED", "SourceLock acquired.", source_lock.get("lock_id", ""))

    def complete_assignment(
        self,
        assignment_id: str,
        lease_id: str,
        completed_at: str,
        target_head: str,
    ) -> TransitionResult:
        assignment = self._assignment(assignment_id)
        lease = self._lease(lease_id)
        if not assignment or not lease:
            return TransitionResult(False, "COMPLETION_TARGET_NOT_FOUND", "Assignment or WorkerLease not found.", assignment_id)
        stale_reason = self._stale_completion_reason(lease, completed_at, target_head)
        if stale_reason:
            self._audit(
                "completion_rejected_stale",
                assignment_id=assignment_id,
                lease_id=lease_id,
                result="rejected",
                notes=stale_reason,
            )
            self._failure(
                "stale_completion",
                assignment_id=assignment_id,
                lease_id=lease_id,
                retryable=False,
                required_next_action="human_required",
                error_summary=stale_reason,
            )
            return TransitionResult(False, "STALE_LEASE_COMPLETION", stale_reason, assignment_id)

        assignment["status"] = "completed"
        assignment["lease_id"] = lease_id
        assignment["completed_at"] = completed_at
        assignment["target_head"] = target_head
        assignment["acceptance_authority"] = False
        for field in PROMOTION_FIELDS:
            assignment.pop(field, None)
        lease["status"] = "released"
        lease["released_at"] = completed_at
        self._audit("completion_received", assignment_id=assignment_id, lease_id=lease_id)
        return TransitionResult(True, "COMPLETION_RECORDED", "Mechanical completion recorded.", assignment_id)

    def cancel_assignment(self, assignment_id: str, cancellation_at: str, reason: str = "") -> TransitionResult:
        assignment = self._assignment(assignment_id)
        if not assignment:
            return TransitionResult(False, "ASSIGNMENT_NOT_FOUND", "Assignment not found.", assignment_id)
        assignment["cancellation_requested_at"] = cancellation_at
        if reason:
            assignment["cancellation_reason"] = reason
        completed_at = _parse_time(assignment.get("completed_at"))
        cancelled_at = _parse_time(cancellation_at)
        if completed_at and cancelled_at and cancelled_at > completed_at:
            self._audit("assignment_cancelled", assignment_id=assignment_id, result="recorded", notes="audit_only_after_completion")
            self._failure(
                "cancellation_after_completion",
                assignment_id=assignment_id,
                retryable=False,
                required_next_action="record_only",
            )
            return TransitionResult(True, "CANCELLATION_AUDIT_ONLY", "Cancellation after completion recorded as audit-only.", assignment_id)

        assignment["status"] = "cancelled"
        self._audit("assignment_cancelled", assignment_id=assignment_id)
        return TransitionResult(True, "ASSIGNMENT_CANCELLED", "Assignment cancelled.", assignment_id)

    def record_failure(self, failure: dict[str, Any]) -> TransitionResult:
        failure = dict(failure)
        failure.setdefault("contract_type", "FailureRecord")
        self.records.append(failure)
        self._audit("failure_recorded", assignment_id=failure.get("assignment_id"), failure_id=failure.get("failure_id"))
        return TransitionResult(True, "FAILURE_RECORDED", "FailureRecord recorded.", failure.get("failure_id", ""))

    def retry_assignment(self, assignment_id: str) -> TransitionResult:
        for failure in self._failures_for_assignment(assignment_id):
            if failure.get("retryable") is False:
                self._audit("retry_rejected", assignment_id=assignment_id, result="rejected")
                self._failure(
                    "retry_non_retryable",
                    assignment_id=assignment_id,
                    retryable=False,
                    required_next_action="human_required",
                )
                return TransitionResult(False, "RETRY_NON_RETRYABLE_FAILURE", "Retry blocked for non-retryable failure.", assignment_id)
        self._audit("retry_scheduled", assignment_id=assignment_id)
        return TransitionResult(True, "RETRY_SCHEDULED", "Retry scheduled.", assignment_id)

    def _assignment(self, assignment_id: Any) -> dict[str, Any] | None:
        return next(
            (
                record for record in self.records
                if record.get("contract_type") == "DispatchAssignment"
                and record.get("assignment_id") == assignment_id
            ),
            None,
        )

    def _lease(self, lease_id: Any) -> dict[str, Any] | None:
        return next(
            (
                record for record in self.records
                if record.get("contract_type") == "WorkerLease"
                and record.get("lease_id") == lease_id
            ),
            None,
        )

    def _active_assignment_by_idempotency(self, idempotency_key: Any) -> dict[str, Any] | None:
        if not idempotency_key:
            return None
        return next(
            (
                record for record in self.records
                if record.get("contract_type") == "DispatchAssignment"
                and record.get("idempotency_key") == idempotency_key
                and record.get("status") in ACTIVE_ASSIGNMENT_STATUSES
            ),
            None,
        )

    def _conflicting_lock(self, candidate: dict[str, Any]) -> dict[str, Any] | None:
        for record in self.records:
            if record.get("contract_type") != "SourceLock":
                continue
            if record.get("status") not in ACTIVE_LOCK_STATUSES:
                continue
            if record.get("repo_id") != candidate.get("repo_id"):
                continue
            if not _paths_overlap(record.get("path_set", []), candidate.get("path_set", [])):
                continue
            if {record.get("lock_mode"), candidate.get("lock_mode")}.isdisjoint(WRITE_LOCK_MODES):
                continue
            return record
        return None

    def _failures_for_assignment(self, assignment_id: str) -> list[dict[str, Any]]:
        return [
            record for record in self.records
            if record.get("contract_type") == "FailureRecord"
            and record.get("assignment_id") == assignment_id
        ]

    def _stale_completion_reason(self, lease: dict[str, Any], completed_at: str, target_head: str) -> str:
        completed = _parse_time(completed_at)
        expires = _parse_time(lease.get("expires_at"))
        if completed and expires and completed > expires:
            return "Completion arrived after WorkerLease expiry."
        if lease.get("status") in {"expired", "cancelled", "stale", "rejected"}:
            return f"Completion references inactive WorkerLease status: {lease.get('status')}."
        if lease.get("target_head") != target_head:
            return "Completion target_head does not match WorkerLease target_head."
        return ""

    def _audit(self, event_type: str, **fields: Any) -> None:
        event = {
            "contract_type": "AuditEvent",
            "event_id": self._next_id("audit", "AuditEvent", "event_id"),
            "event_type": event_type,
            "result": fields.pop("result", "recorded"),
        }
        event.update({key: value for key, value in fields.items() if value is not None})
        self.records.append(event)

    def _failure(
        self,
        failure_type: str,
        assignment_id: Any,
        retryable: bool,
        required_next_action: str,
        **fields: Any,
    ) -> None:
        failure = {
            "contract_type": "FailureRecord",
            "failure_id": self._next_id("failure", "FailureRecord", "failure_id"),
            "assignment_id": assignment_id,
            "failure_type": failure_type,
            "retryable": retryable,
            "required_next_action": required_next_action,
            "final_verdict_allowed": False,
        }
        failure.update({key: value for key, value in fields.items() if value is not None})
        self.records.append(failure)

    def _next_id(self, prefix: str, contract_type: str, id_field: str) -> str:
        count = sum(
            1 for record in self.records
            if record.get("contract_type") == contract_type
            and record.get(id_field)
        )
        return f"{prefix}-{count + 1}"


def probe_runtime_contracts(records: Iterable[dict[str, Any]]) -> list[ProbeViolation]:
    """Detect unsafe coordination states without touching external runtime."""
    record_list = list(records)
    assignments = _by_id(record_list, "DispatchAssignment", "assignment_id")
    leases = _by_id(record_list, "WorkerLease", "lease_id")
    failures = [r for r in record_list if r.get("contract_type") == "FailureRecord"]
    audits = [r for r in record_list if r.get("contract_type") == "AuditEvent"]
    violations: list[ProbeViolation] = []

    violations.extend(_check_dispatch_promotion(assignments.values()))
    violations.extend(_check_runtime_authorization(assignments.values(), record_list))
    violations.extend(_check_duplicate_dispatch(assignments.values()))
    violations.extend(_check_stale_completion(assignments.values(), leases))
    violations.extend(_check_overlap_locks(record_list))
    violations.extend(_check_cancellation_after_completion(assignments.values(), failures))
    violations.extend(_check_retry_non_retryable(failures, audits))
    return violations


def _by_id(records: list[dict[str, Any]], contract_type: str, id_field: str) -> dict[str, dict[str, Any]]:
    return {
        record[id_field]: record
        for record in records
        if record.get("contract_type") == contract_type and record.get(id_field)
    }


def _check_dispatch_promotion(assignments: Iterable[dict[str, Any]]) -> list[ProbeViolation]:
    violations: list[ProbeViolation] = []
    for assignment in assignments:
        assignment_id = assignment.get("assignment_id", "")
        if assignment.get("acceptance_authority") is not False:
            violations.append(ProbeViolation(
                "DISPATCH_PROMOTED_TO_TASK_SUCCESS",
                "DispatchAssignment must not carry acceptance authority.",
                assignment_id,
            ))
        promoted_fields = sorted(PROMOTION_FIELDS.intersection(assignment))
        if promoted_fields:
            violations.append(ProbeViolation(
                "DISPATCH_PROMOTED_TO_TASK_SUCCESS",
                f"DispatchAssignment contains final-success fields: {', '.join(promoted_fields)}.",
                assignment_id,
            ))
    return violations


def _check_runtime_authorization(
    assignments: Iterable[dict[str, Any]],
    records: list[dict[str, Any]],
) -> list[ProbeViolation]:
    violations: list[ProbeViolation] = []
    for assignment in assignments:
        violation = _runtime_authorization_violation(assignment, records)
        if violation:
            violations.append(violation)
    return violations


def _runtime_authorization_violation(
    assignment: dict[str, Any],
    records: list[dict[str, Any]],
) -> ProbeViolation | None:
    required_scopes = _required_runtime_authorization_scopes(assignment)
    if not required_scopes:
        return None
    if _has_fresh_runtime_authorization(assignment, records, required_scopes):
        return None
    return ProbeViolation(
        "RUNTIME_AUTHORIZATION_REQUIRED",
        f"Missing fresh RuntimeAuthorization for scopes: {', '.join(sorted(required_scopes))}.",
        assignment.get("assignment_id", ""),
    )


def _required_runtime_authorization_scopes(assignment: dict[str, Any]) -> set[str]:
    if not _is_paper_task(assignment):
        return set()
    scopes: set[str] = set()
    if _uses_real_paper_content(assignment):
        scopes.add(PAPER_REAL_CONTENT_SCOPE)
    if _uses_live_writelab_dispatch(assignment):
        scopes.add(WRITELAB_LIVE_SCOPE)
    return scopes


def _is_paper_task(assignment: dict[str, Any]) -> bool:
    values = [
        _metadata_value(assignment, "task_domain"),
        _metadata_value(assignment, "task_family"),
        _metadata_value(assignment, "task_type"),
        _metadata_value(assignment, "workflow"),
        _metadata_value(assignment, "target_system"),
    ]
    return any(value and ("paper" in value or "writelab" in value) for value in values)


def _uses_real_paper_content(assignment: dict[str, Any]) -> bool:
    classification = _metadata_value(assignment, "paper_data_classification")
    return (
        classification in REAL_PAPER_CLASSIFICATIONS
        or _metadata_bool(assignment, "contains_real_paper_full_text")
        or _metadata_bool(assignment, "real_content")
        or _metadata_bool(assignment, "uses_real_paper_content")
    )


def _uses_live_writelab_dispatch(assignment: dict[str, Any]) -> bool:
    dispatch_values = [
        _metadata_value(assignment, "dispatch_method"),
        _metadata_value(assignment, "dispatch_mode"),
        _metadata_value(assignment, "writelab_mode"),
        _metadata_value(assignment, "runtime_mode"),
    ]
    return (
        any(value in LIVE_DISPATCH_VALUES for value in dispatch_values)
        or _metadata_bool(assignment, "live_dispatch")
        or _metadata_bool(assignment, "live_writelab")
        or _metadata_bool(assignment, "writelab_live")
    )


def _has_fresh_runtime_authorization(
    assignment: dict[str, Any],
    records: list[dict[str, Any]],
    required_scopes: set[str],
) -> bool:
    dispatch_time = _parse_time(assignment.get("created_at")) or datetime.now(timezone.utc)
    for record in records:
        if record.get("contract_type") != "RuntimeAuthorization":
            continue
        if record.get("status") != "active":
            continue
        if not _authorization_targets_assignment(record, assignment):
            continue
        scopes = _authorization_scopes(record)
        if not required_scopes.issubset(scopes):
            continue
        authorized_at = _parse_time(record.get("authorized_at"))
        expires_at = _parse_time(record.get("expires_at"))
        if not authorized_at or not expires_at:
            continue
        if authorized_at <= dispatch_time <= expires_at:
            return True
    return False


def _authorization_targets_assignment(
    authorization: dict[str, Any],
    assignment: dict[str, Any],
) -> bool:
    assignment_id = authorization.get("assignment_id")
    task_id = authorization.get("task_id")
    target_repo = authorization.get("target_repo")
    if assignment_id and assignment_id != assignment.get("assignment_id"):
        return False
    if task_id and task_id != assignment.get("task_id"):
        return False
    if target_repo and target_repo != assignment.get("target_repo"):
        return False
    return bool(assignment_id or task_id or target_repo)


def _authorization_scopes(authorization: dict[str, Any]) -> set[str]:
    scopes = authorization.get("scopes", [])
    if isinstance(scopes, str):
        return {scopes}
    if isinstance(scopes, list):
        return {str(scope) for scope in scopes}
    scope = authorization.get("scope")
    if isinstance(scope, str):
        return {scope}
    return set()


def _metadata_value(assignment: dict[str, Any], key: str) -> str:
    metadata = assignment.get("task_metadata", {})
    value = metadata.get(key) if isinstance(metadata, dict) and key in metadata else assignment.get(key)
    return str(value).strip().lower() if value is not None else ""


def _metadata_bool(assignment: dict[str, Any], key: str) -> bool:
    metadata = assignment.get("task_metadata", {})
    value = metadata.get(key) if isinstance(metadata, dict) and key in metadata else assignment.get(key)
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y"}
    return False


def _check_duplicate_dispatch(assignments: Iterable[dict[str, Any]]) -> list[ProbeViolation]:
    active_by_key: dict[str, list[str]] = {}
    for assignment in assignments:
        if assignment.get("status") not in ACTIVE_ASSIGNMENT_STATUSES:
            continue
        key = assignment.get("idempotency_key")
        if not key:
            continue
        active_by_key.setdefault(key, []).append(assignment.get("assignment_id", ""))

    return [
        ProbeViolation(
            "DUPLICATE_DISPATCH",
            f"Active idempotency key is used by multiple assignments: {', '.join(ids)}.",
            key,
        )
        for key, ids in active_by_key.items()
        if len(ids) > 1
    ]


def _check_stale_completion(
    assignments: Iterable[dict[str, Any]],
    leases: dict[str, dict[str, Any]],
) -> list[ProbeViolation]:
    violations: list[ProbeViolation] = []
    for assignment in assignments:
        if assignment.get("status") != "completed":
            continue
        lease = leases.get(assignment.get("lease_id", ""))
        if not lease:
            continue
        assignment_id = assignment.get("assignment_id", "")
        completed_at = _parse_time(assignment.get("completed_at"))
        expires_at = _parse_time(lease.get("expires_at"))
        if completed_at and expires_at and completed_at > expires_at:
            violations.append(ProbeViolation(
                "STALE_LEASE_COMPLETION",
                "Completion arrived after WorkerLease expiry.",
                assignment_id,
            ))
        if lease.get("status") in {"expired", "cancelled", "stale", "rejected"}:
            violations.append(ProbeViolation(
                "STALE_LEASE_COMPLETION",
                f"Completion references inactive WorkerLease status: {lease.get('status')}.",
                assignment_id,
            ))
        if assignment.get("target_head") != lease.get("target_head"):
            violations.append(ProbeViolation(
                "STALE_LEASE_COMPLETION",
                "Completion target_head does not match WorkerLease target_head.",
                assignment_id,
            ))
    return violations


def _check_overlap_locks(records: list[dict[str, Any]]) -> list[ProbeViolation]:
    locks = [
        record for record in records
        if record.get("contract_type") == "SourceLock"
        and record.get("status") in ACTIVE_LOCK_STATUSES
    ]
    violations: list[ProbeViolation] = []
    for index, left in enumerate(locks):
        for right in locks[index + 1:]:
            if left.get("repo_id") != right.get("repo_id"):
                continue
            if not _paths_overlap(left.get("path_set", []), right.get("path_set", [])):
                continue
            if {left.get("lock_mode"), right.get("lock_mode")}.isdisjoint(WRITE_LOCK_MODES):
                continue
            violations.append(ProbeViolation(
                "OVERLAP_SOURCE_LOCK",
                f"Overlapping active SourceLock records: {left.get('lock_id')} and {right.get('lock_id')}.",
                left.get("lock_id", ""),
            ))
    return violations


def _check_cancellation_after_completion(
    assignments: Iterable[dict[str, Any]],
    failures: list[dict[str, Any]],
) -> list[ProbeViolation]:
    failure_keys = {
        failure.get("assignment_id")
        for failure in failures
        if failure.get("failure_type") == "cancellation_after_completion"
    }
    violations: list[ProbeViolation] = []
    for assignment in assignments:
        completed_at = _parse_time(assignment.get("completed_at"))
        cancellation_at = _parse_time(assignment.get("cancellation_requested_at"))
        assignment_id = assignment.get("assignment_id", "")
        if completed_at and cancellation_at and cancellation_at > completed_at and assignment_id not in failure_keys:
            violations.append(ProbeViolation(
                "CANCELLATION_AFTER_COMPLETION",
                "Cancellation after completion must be recorded as a FailureRecord.",
                assignment_id,
            ))
    return violations


def _check_retry_non_retryable(
    failures: list[dict[str, Any]],
    audits: list[dict[str, Any]],
) -> list[ProbeViolation]:
    non_retryable = {
        failure.get("assignment_id")
        for failure in failures
        if failure.get("retryable") is False
    }
    violations: list[ProbeViolation] = []
    for audit in audits:
        assignment_id = audit.get("assignment_id")
        if audit.get("event_type") == "retry_scheduled" and assignment_id in non_retryable:
            violations.append(ProbeViolation(
                "RETRY_NON_RETRYABLE_FAILURE",
                "Retry was scheduled for a non-retryable failure.",
                assignment_id or "",
            ))
    return violations


def _paths_overlap(left_paths: Iterable[str], right_paths: Iterable[str]) -> bool:
    for left in left_paths:
        left_norm = _normalize_path(left)
        for right in right_paths:
            right_norm = _normalize_path(right)
            if left_norm == right_norm:
                return True
            if left_norm.startswith(f"{right_norm}/") or right_norm.startswith(f"{left_norm}/"):
                return True
    return False


def _normalize_path(path: str) -> str:
    return path.replace("\\", "/").strip("/").lower()


def _parse_time(value: Any) -> datetime | None:
    if not value:
        return None
    if not isinstance(value, str):
        return None
    normalized = value.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed
