"""Vendor-neutral semantic validation for executor contract payloads.

The canonical JSON Schema is the cross-tool contract.  These small validators
make the same boundary fail closed in the installed Python adapters before an
invalid TaskSpec is dispatched or an invalid ExecutionReport is written.
"""

from __future__ import annotations

from datetime import datetime, timezone
import math
import os
import re
from typing import Any
from urllib.parse import unquote


class ExecutorContractValidationError(ValueError):
    """Raised when executor requirements or observations are malformed."""


CONTRACT_VERSION = "executor-contract.v1"

_OPEN_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]*$")
_SENSITIVE_ENV_NAME = re.compile(r"(?:key|secret|token|password|credential)", re.IGNORECASE)
_SENSITIVE_TEXT_PATTERNS = (
    re.compile(r"\b(?:sk|ghp|github_pat|xox[baprs])[-_A-Za-z0-9]{8,}\b", re.IGNORECASE),
    re.compile(r"\bbearer\s+[A-Za-z0-9._~+/=-]{8,}\b", re.IGNORECASE),
    re.compile(r"-----BEGIN [A-Z ]+PRIVATE KEY-----"),
    re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\b", re.IGNORECASE),
    re.compile(r"(?<!\w)(?:\+?\d[\d .()\-]{7,}\d)(?!\w)"),
    re.compile(
        r"(?:\b[A-Za-z]:[\\/]|\\\\[^\\/\s]+[\\/][^\\/\s]+|file://|(?<![:/\w])/[^\s/]+(?:/[^\s]*)?)",
        re.IGNORECASE,
    ),
    re.compile(
        r"(?:[\"']\s*)?(?:password|passwd|pwd|secret|token|api[_-]?key|credential)(?:\s*[\"'])?\s*[:=]\s*\S+",
        re.IGNORECASE,
    ),
    re.compile(r"\b[a-z][a-z0-9+.-]*://[^/\s:@]+:[^@\s/]+@", re.IGNORECASE),
    re.compile(r"[\x00-\x1f\x7f]"),
)
_MAX_CAPABILITIES = 64
_MAX_ACCEPTED_PROTOCOLS = 16
_MAX_LIFECYCLE_EVENTS = 128
_MAX_BLOCKERS = 64
_LIFECYCLE_PHASES = frozenset({
    "discover", "prepare", "launch", "observe", "cancel", "collect", "close",
})
_LIFECYCLE_STATUSES = frozenset({
    "pending", "started", "completed", "failed", "blocked", "cancelled",
})
_QUOTA_STATUSES = frozenset({"unknown", "available", "limited", "exhausted"})
_BLOCKER_CATEGORIES = frozenset({
    "environment", "permission", "quota", "rate_limit", "toolchain", "timeout",
    "cancelled", "capability", "identity", "network", "unknown",
})
_IDENTITY_ATTESTATIONS = frozenset({
    "verified", "requested_unverified", "unavailable", "mismatch",
})


def validate_executor_requirements(value: Any) -> dict[str, Any]:
    """Validate the optional TaskSpec executor requirements object."""
    requirements = _mapping(value, "executor_requirements")
    _exact_keys(
        requirements,
        required={"required_capabilities", "required_lifecycle_operations"},
        allowed={
            "required_capabilities",
            "required_lifecycle_operations",
            "accepted_protocols",
        },
        label="executor_requirements",
    )
    _identifier_list(
        requirements["required_capabilities"],
        "executor_requirements.required_capabilities",
        maximum=_MAX_CAPABILITIES,
    )
    _enum_list(
        requirements["required_lifecycle_operations"],
        "executor_requirements.required_lifecycle_operations",
        _LIFECYCLE_PHASES,
        maximum=len(_LIFECYCLE_PHASES),
    )
    if "accepted_protocols" in requirements:
        _identifier_list(
            requirements["accepted_protocols"],
            "executor_requirements.accepted_protocols",
            maximum=_MAX_ACCEPTED_PROTOCOLS,
        )
    return requirements


def validate_executor_runtime(value: Any) -> dict[str, Any]:
    """Validate one executor runtime observation before it enters a report."""
    runtime = _mapping(value, "executor_runtime")
    _exact_keys(
        runtime,
        required={
            "contract_version", "adapter_id", "adapter_version", "protocol",
            "declared_capabilities", "negotiated_capabilities", "lifecycle", "quota",
            "blockers", "provenance",
        },
        allowed={
            "contract_version", "adapter_id", "adapter_version", "protocol",
            "declared_capabilities", "negotiated_capabilities", "lifecycle", "quota",
            "blockers", "provenance",
        },
        label="executor_runtime",
    )
    if runtime["contract_version"] != CONTRACT_VERSION:
        raise ExecutorContractValidationError("executor_runtime.contract_version is unsupported")
    _identifier(runtime["adapter_id"], "executor_runtime.adapter_id")
    _text(runtime["adapter_version"], "executor_runtime.adapter_version", 128)
    _validate_protocol(runtime["protocol"])
    _identifier_list(
        runtime["declared_capabilities"],
        "executor_runtime.declared_capabilities",
        maximum=_MAX_CAPABILITIES,
    )
    _identifier_list(
        runtime["negotiated_capabilities"],
        "executor_runtime.negotiated_capabilities",
        maximum=_MAX_CAPABILITIES,
    )
    if not set(runtime["negotiated_capabilities"]).issubset(runtime["declared_capabilities"]):
        raise ExecutorContractValidationError(
            "executor_runtime.negotiated_capabilities must be a subset of declared_capabilities"
        )
    _validate_lifecycle(runtime["lifecycle"])
    _validate_quota(runtime["quota"])
    _validate_blockers(runtime["blockers"])
    _validate_provenance(runtime["provenance"])
    return runtime


def _mapping(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ExecutorContractValidationError(f"{label} must be an object")
    return value


def _exact_keys(
    value: dict[str, Any], *, required: set[str], allowed: set[str], label: str
) -> None:
    missing = required - set(value)
    unknown = set(value) - allowed
    if missing:
        raise ExecutorContractValidationError(f"{label} is missing {sorted(missing)}")
    if unknown:
        raise ExecutorContractValidationError(f"{label} has unknown fields {sorted(unknown)}")


def _identifier(value: Any, label: str) -> None:
    if (
        not isinstance(value, str)
        or len(value) > 128
        or not _OPEN_IDENTIFIER.fullmatch(value)
    ):
        raise ExecutorContractValidationError(f"{label} must be a non-empty open identifier")
    _reject_sensitive_text(value, label)


def validate_open_identifier(value: Any, label: str) -> None:
    """Validate a schema ``open_identifier`` value at adapter boundaries."""
    _identifier(value, label)


def validate_public_text(value: Any, label: str, *, maximum: int) -> None:
    """Validate text that may be serialized into a public execution report."""
    _text(value, label, maximum)


def validate_nonnegative_number(value: Any, label: str) -> None:
    """Validate a finite numeric report field without leaking its raw value."""
    _nonnegative_number(value, label)


def _text(value: Any, label: str, maximum: int, *, allow_empty: bool = False) -> None:
    if not isinstance(value, str) or len(value) > maximum or (not allow_empty and not value):
        raise ExecutorContractValidationError(f"{label} must be a string up to {maximum} characters")
    _reject_sensitive_text(value, label)


def _reject_sensitive_text(value: str, label: str) -> None:
    candidates = (value, unquote(value))
    if any(pattern.search(candidate) for candidate in candidates for pattern in _SENSITIVE_TEXT_PATTERNS):
        raise ExecutorContractValidationError(f"{label} must not contain sensitive or personal text")
    for name, secret in os.environ.items():
        if (
            _SENSITIVE_ENV_NAME.search(name)
            and len(secret) >= 8
            and any(secret in candidate for candidate in candidates)
        ):
            raise ExecutorContractValidationError(f"{label} must not contain configured secret values")


def _identifier_list(value: Any, label: str, *, maximum: int) -> None:
    if not isinstance(value, list):
        raise ExecutorContractValidationError(f"{label} must be an array")
    if len(value) > maximum:
        raise ExecutorContractValidationError(f"{label} must contain at most {maximum} items")
    for item in value:
        _identifier(item, label)
    if len(set(value)) != len(value):
        raise ExecutorContractValidationError(f"{label} must not contain duplicates")


def _enum_list(
    value: Any,
    label: str,
    allowed: frozenset[str],
    *,
    maximum: int,
) -> None:
    if not isinstance(value, list):
        raise ExecutorContractValidationError(f"{label} must be an array")
    if len(value) > maximum:
        raise ExecutorContractValidationError(f"{label} must contain at most {maximum} items")
    if any(not isinstance(item, str) or item not in allowed for item in value):
        raise ExecutorContractValidationError(f"{label} contains unsupported values")
    if len(set(value)) != len(value):
        raise ExecutorContractValidationError(f"{label} must not contain duplicates")


def _validate_protocol(value: Any) -> None:
    protocol = _mapping(value, "executor_runtime.protocol")
    _exact_keys(
        protocol,
        required={"name", "version"},
        allowed={"name", "version"},
        label="executor_runtime.protocol",
    )
    _identifier(protocol["name"], "executor_runtime.protocol.name")
    _text(protocol["version"], "executor_runtime.protocol.version", 128)


def _validate_lifecycle(value: Any) -> None:
    if not isinstance(value, list) or not value:
        raise ExecutorContractValidationError("executor_runtime.lifecycle must be a non-empty array")
    if len(value) > _MAX_LIFECYCLE_EVENTS:
        raise ExecutorContractValidationError(
            f"executor_runtime.lifecycle must contain at most {_MAX_LIFECYCLE_EVENTS} items"
        )
    for index, item in enumerate(value):
        event = _mapping(item, f"executor_runtime.lifecycle[{index}]")
        _exact_keys(
            event,
            required={"phase", "status", "attempt", "observed_at"},
            allowed={"phase", "status", "attempt", "observed_at", "detail"},
            label=f"executor_runtime.lifecycle[{index}]",
        )
        if event["phase"] not in _LIFECYCLE_PHASES:
            raise ExecutorContractValidationError("executor_runtime lifecycle phase is unsupported")
        if event["status"] not in _LIFECYCLE_STATUSES:
            raise ExecutorContractValidationError("executor_runtime lifecycle status is unsupported")
        _positive_integer(event["attempt"], "executor_runtime lifecycle attempt")
        _timestamp(event["observed_at"], "executor_runtime lifecycle observed_at")
        if "detail" in event:
            _text(event["detail"], "executor_runtime lifecycle detail", 1000, allow_empty=True)


def _validate_quota(value: Any) -> None:
    quota = _mapping(value, "executor_runtime.quota")
    _exact_keys(
        quota,
        required={"status"},
        allowed={"status", "remaining", "unit", "retry_after_seconds"},
        label="executor_runtime.quota",
    )
    if quota["status"] not in _QUOTA_STATUSES:
        raise ExecutorContractValidationError("executor_runtime quota status is unsupported")
    if "remaining" in quota:
        _nonnegative_number(quota["remaining"], "executor_runtime quota remaining")
    if "unit" in quota:
        _text(quota["unit"], "executor_runtime quota unit", 64)
    if "retry_after_seconds" in quota:
        _nonnegative_integer(quota["retry_after_seconds"], "executor_runtime quota retry_after_seconds")


def _validate_blockers(value: Any) -> None:
    if not isinstance(value, list):
        raise ExecutorContractValidationError("executor_runtime.blockers must be an array")
    if len(value) > _MAX_BLOCKERS:
        raise ExecutorContractValidationError(
            f"executor_runtime.blockers must contain at most {_MAX_BLOCKERS} items"
        )
    for index, item in enumerate(value):
        blocker = _mapping(item, f"executor_runtime.blockers[{index}]")
        _exact_keys(
            blocker,
            required={"category", "phase", "retryable", "reason", "next_action"},
            allowed={"category", "phase", "retryable", "reason", "next_action", "retry_after_seconds"},
            label=f"executor_runtime.blockers[{index}]",
        )
        if blocker["category"] not in _BLOCKER_CATEGORIES:
            raise ExecutorContractValidationError("executor_runtime blocker category is unsupported")
        if blocker["phase"] not in _LIFECYCLE_PHASES:
            raise ExecutorContractValidationError("executor_runtime blocker phase is unsupported")
        if not isinstance(blocker["retryable"], bool):
            raise ExecutorContractValidationError("executor_runtime blocker retryable must be boolean")
        _text(blocker["reason"], "executor_runtime blocker reason", 1000)
        _text(blocker["next_action"], "executor_runtime blocker next_action", 1000)
        if "retry_after_seconds" in blocker:
            _nonnegative_integer(
                blocker["retry_after_seconds"], "executor_runtime blocker retry_after_seconds"
            )


def _validate_provenance(value: Any) -> None:
    provenance = _mapping(value, "executor_runtime.provenance")
    _exact_keys(
        provenance,
        required={"identity_attestation"},
        allowed={
            "session_id", "provider_requested", "provider_reported", "model_requested",
            "model_reported", "identity_attestation",
        },
        label="executor_runtime.provenance",
    )
    if provenance["identity_attestation"] not in _IDENTITY_ATTESTATIONS:
        raise ExecutorContractValidationError("executor_runtime identity attestation is unsupported")
    for field in (
        "session_id", "provider_requested", "provider_reported", "model_requested", "model_reported",
    ):
        if field in provenance:
            _text(provenance[field], f"executor_runtime provenance {field}", 256)


def _positive_integer(value: Any, label: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ExecutorContractValidationError(f"{label} must be a positive integer")


def _nonnegative_integer(value: Any, label: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ExecutorContractValidationError(f"{label} must be a non-negative integer")


def _nonnegative_number(value: Any, label: str) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
        raise ExecutorContractValidationError(f"{label} must be a non-negative finite number")


def _timestamp(value: Any, label: str) -> datetime:
    _text(value, label, 64)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ExecutorContractValidationError(f"{label} must be ISO-8601") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ExecutorContractValidationError(f"{label} must include a timezone offset")
    return parsed.astimezone(timezone.utc)
