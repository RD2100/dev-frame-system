"Validate state transitions and blocked item invariants."
from __future__ import annotations
from pathlib import Path
from typing import Any
import yaml

VALID_STATUSES = {"initialized", "planned", "in_progress", "completed", "blocked", "failed"}
VALID_TRANSITIONS = {
    "initialized": {"planned", "in_progress"},
    "planned": {"in_progress"},
    "in_progress": {"completed", "blocked", "failed"},
    "blocked": {"in_progress", "failed"},
    "failed": set(),
    "completed": set(),
}

PERMANENTLY_BLOCKED = {"guard_removal_approved", "evidence_cleanup_approved"}


def load_state(path: str | Path) -> dict[str, Any]:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def validate_transition(current_status: str, next_status: str) -> tuple[bool, str]:
    if current_status not in VALID_STATUSES:
        return False, f"Invalid current status: {current_status}"
    if next_status not in VALID_STATUSES:
        return False, f"Invalid next status: {next_status}"
    allowed = VALID_TRANSITIONS.get(current_status, set())
    if next_status not in allowed:
        return False, f"Transition {current_status} -> {next_status} not allowed"
    return True, "ok"


def check_blocked_items(state: dict[str, Any]) -> list[str]:
    violations = []
    blocked = state.get("blocked_items", {})
    for key in PERMANENTLY_BLOCKED:
        if blocked.get(key) is not False:
            violations.append(f"{key} must be false, got {blocked.get(key)}")
    return violations
