import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from control_plane.state_machine import (
    load_state, validate_transition, check_blocked_items
)


def test_load_current_state():
    state = load_state("CURRENT_STATE.yaml")
    assert state["project"] == "devframe-control-plane"
    assert state["current_stage"][0] in ("G","H","R","T") and "_" in state["current_stage"]


def test_valid_transition_in_progress_to_completed():
    ok, msg = validate_transition("in_progress", "completed")
    assert ok
    assert msg == "ok"


def test_invalid_transition_completed_to_in_progress():
    ok, msg = validate_transition("completed", "in_progress")
    assert not ok


def test_invalid_status():
    ok, msg = validate_transition("invalid", "in_progress")
    assert not ok


def test_permanently_blocked_items_must_be_false():
    violations = check_blocked_items({
        "blocked_items": {
            "guard_removal_approved": False,
            "evidence_cleanup_approved": False
        }
    })
    assert len(violations) == 0


def test_blocked_item_true_is_violation():
    violations = check_blocked_items({
        "blocked_items": {
            "guard_removal_approved": True,
            "evidence_cleanup_approved": False
        }
    })
    assert len(violations) > 0
