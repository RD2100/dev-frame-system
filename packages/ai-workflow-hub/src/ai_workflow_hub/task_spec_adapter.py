"""Canonical TaskSpec adapter -- validates closed schema, separates operational envelope.

``from_task_spec`` accepts a canonical TaskSpec (matching
``schemas/agent-runtime/task-spec.schema.json`` with
``additionalProperties: false``), validates required semantic fields,
and returns an explicit structure that separates the *closed machine
contract* from *operational values* (allowed_files, forbidden_files,
verification, max_fix_rounds, mode) which come from a separate optional
envelope argument -- never invented as TaskSpec fields.
"""

from __future__ import annotations

from typing import Any


class TaskSpecValidationError(ValueError):
    """Raised when a TaskSpec violates canonical semantics."""


# -- Canonical closed-schema constants (mirror task-spec.schema.json) --

_TASK_SPEC_REQUIRED: tuple[str, ...] = (
    "task_id", "title", "priority", "status", "description",
)

#: Public set of canonical TaskSpec top-level field names (mirrors the
#: closed schema's ``properties`` keys).  Callers (e.g. ``cli.go_dispatch``)
#: use this to split a raw authoring spec into a canonical subset and a
#: separate operational envelope before validation.
CANONICAL_TASK_SPEC_FIELDS: frozenset[str] = frozenset({
    "task_id", "title", "priority", "status", "description",
    "depends_on", "assumptions", "risk_notes", "estimated_tools",
    "gate_0", "conflict_registry", "security_report",
})

_VALID_PRIORITIES: frozenset[str] = frozenset({"P0", "P1", "P2", "P3"})

_VALID_STATUSES: frozenset[str] = frozenset({
    "draft", "ready", "in_progress", "completed", "closed",
    "deferred", "rejected", "accepted_with_limitation",
    "pending_human_decision",
})

_PRIORITY_TO_RISK: dict[str, str] = {
    "P0": "high", "P1": "high", "P2": "medium", "P3": "low",
}


def _validate_canonical_task_spec(spec: Any) -> None:
    """Narrow deterministic validator for canonical TaskSpec semantics.

    Enforces the subset of the canonical schema needed by this adapter:
    required nonempty fields, valid enums, and ``additionalProperties:
    false`` (rejects unknown top-level fields).  Tests independently
    validate with canonical jsonschema.
    """
    if not isinstance(spec, dict):
        raise TaskSpecValidationError("TaskSpec must be a JSON object")

    unknown = set(spec.keys()) - CANONICAL_TASK_SPEC_FIELDS
    if unknown:
        raise TaskSpecValidationError(
            f"Unknown TaskSpec fields (additionalProperties is false): "
            f"{sorted(unknown)}"
        )

    for field in _TASK_SPEC_REQUIRED:
        if field not in spec:
            raise TaskSpecValidationError(
                f"Missing required TaskSpec field: {field}"
            )

    for field in ("task_id", "title", "description"):
        val = spec.get(field)
        if not isinstance(val, str) or not val.strip():
            raise TaskSpecValidationError(
                f"TaskSpec.{field} must be a non-empty string"
            )

    if spec["priority"] not in _VALID_PRIORITIES:
        raise TaskSpecValidationError(
            f"TaskSpec.priority must be one of "
            f"{sorted(_VALID_PRIORITIES)}, got: {spec['priority']!r}"
        )

    if spec["status"] not in _VALID_STATUSES:
        raise TaskSpecValidationError(
            f"TaskSpec.status must be one of the 9 canonical values, "
            f"got: {spec['status']!r}"
        )


def from_task_spec(
    spec: dict[str, Any],
    *,
    envelope: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Validate a canonical TaskSpec and separate it from operational values.

    Parameters
    ----------
    spec
        A canonical TaskSpec dict (must satisfy the closed schema).
    envelope
        Optional operational values: ``allowed_files``,
        ``forbidden_files``, ``verification``, ``max_fix_rounds``,
        ``mode``.  These are NOT TaskSpec fields -- they come from the
        caller (CLI flags, dispatch context).

    Returns
    -------
    dict
        ``{"task_spec": <closed canonical spec>, "operational": {...}}``

    The ``task_spec`` value is the validated input dict, byte-for-data
    equivalent / closed.  The ``operational`` dict carries convenience
    fields (``title``, ``description``, ``risk`` derived from priority)
    plus the envelope values (with sensible defaults).
    """
    _validate_canonical_task_spec(spec)

    env = envelope or {}

    # allowed_files: envelope takes precedence, then conflict_registry.write_set
    if "allowed_files" in env:
        allowed_files = list(env.get("allowed_files") or [])
    else:
        cr = spec.get("conflict_registry") or {}
        allowed_files = list(cr.get("write_set", []))

    forbidden_files = list(env.get("forbidden_files", []))
    verification = list(env.get("verification", []))
    mode = env.get("mode", "dry-run")

    # R-004 operational safety boundary: apply mode requires a declared
    # safety boundary.  An empty forbidden_files AND empty verification
    # means the caller has declared no safety guard for real changes,
    # which is unsafe.  Legitimate dry-run callers are unaffected.
    if mode == "apply" and not forbidden_files and not verification:
        raise TaskSpecValidationError(
            "apply mode requires a non-empty safety boundary: "
            "provide forbidden_files or verification"
        )

    operational = {
        "title": spec["title"],
        "description": spec["description"],
        "risk": _PRIORITY_TO_RISK.get(spec["priority"], "medium"),
        "allowed_files": allowed_files,
        "forbidden_files": forbidden_files,
        "verification": verification,
        "max_fix_rounds": env.get("max_fix_rounds", 3),
        "mode": mode,
    }

    return {
        "task_spec": spec,
        "operational": operational,
    }
