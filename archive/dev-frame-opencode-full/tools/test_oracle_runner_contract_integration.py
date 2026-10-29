#!/usr/bin/env python3
"""Tests for runner contract integration — S3 Phase 3.

Validates RUNNER_CONTRACT, RUNNER_STATE, and RUNNER_STEP_RESULT
against agent-acceptance schemas.
"""

import json
from pathlib import Path

import pytest

CONTRACTS = Path("D:/agent-acceptance/contracts")


# ── RUNNER_CONTRACT schema validation ───────────────────────────────

def test_runner_contract_schema_valid():
    """RUNNER_CONTRACT.schema.json is itself valid."""
    from jsonschema import Draft202012Validator
    schema = json.loads((CONTRACTS / "RUNNER_CONTRACT.schema.json").read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)  # raises if invalid


def test_runner_contract_minimal_valid():
    """A minimal runner contract validates."""
    from jsonschema import validate
    schema = json.loads((CONTRACTS / "RUNNER_CONTRACT.schema.json").read_text(encoding="utf-8"))
    contract = {
        "runner_id": "test-runner",
        "task_id": "test",
        "mode": "single_step",
        "terminal": True,
        "allowed_actions": ["validate"],
        "forbidden_actions": ["delete"],
        "resume_policy": {"resume_enabled": True, "state_path": "/tmp/state.json"},
        "safety_policy": {
            "high_risk_triggers_human_required": True,
            "fail_closed": True,
            "require_schema_validation": True,
        },
    }
    validate(instance=contract, schema=schema)


def test_runner_contract_terminal_false_requires_input():
    """terminal=false requires input_taskspec_path or next_action."""
    from jsonschema import validate, ValidationError
    schema = json.loads((CONTRACTS / "RUNNER_CONTRACT.schema.json").read_text(encoding="utf-8"))
    contract = {
        "runner_id": "r1", "task_id": "t1", "mode": "run_until_terminal",
        "terminal": False,
        "allowed_actions": ["test"], "forbidden_actions": ["delete"],
        "resume_policy": {"resume_enabled": True, "state_path": "/tmp/s.json"},
        "safety_policy": {"high_risk_triggers_human_required": True, "fail_closed": True,
                          "require_schema_validation": True},
    }
    with pytest.raises(ValidationError):
        validate(instance=contract, schema=schema)

    # With input_taskspec_path, should pass
    contract["input_taskspec_path"] = "/tmp/ts.json"
    validate(instance=contract, schema=schema)


# ── RUNNER_STATE schema validation ─────────────────────────────────

def test_runner_state_schema_valid():
    from jsonschema import Draft202012Validator
    schema = json.loads((CONTRACTS / "RUNNER_STATE.schema.json").read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)


def test_runner_state_terminal_false_requires_next_action():
    """terminal=false requires next_action."""
    from jsonschema import validate, ValidationError
    schema = json.loads((CONTRACTS / "RUNNER_STATE.schema.json").read_text(encoding="utf-8"))
    state = {
        "runner_id": "r1", "task_id": "t1", "current_step": 0, "current_round": 0,
        "terminal": False, "heartbeat": "2026-06-02T00:00:00Z",
        "last_decision": "accepted",
    }
    with pytest.raises(ValidationError):
        validate(instance=state, schema=schema)

    state["next_action"] = "do_something"
    validate(instance=state, schema=schema)


def test_runner_state_human_required_requires_resume():
    """last_decision=human_required + terminal=true requires resume_command."""
    from jsonschema import validate, ValidationError
    schema = json.loads((CONTRACTS / "RUNNER_STATE.schema.json").read_text(encoding="utf-8"))
    state = {
        "runner_id": "r1", "task_id": "t1", "current_step": 1, "current_round": 0,
        "terminal": True, "heartbeat": "2026-06-02T00:00:00Z",
        "last_decision": "human_required", "next_action": "wait",
    }
    with pytest.raises(ValidationError):
        validate(instance=state, schema=schema)

    state["resume_command"] = "python tools/runner.py --resume"
    validate(instance=state, schema=schema)


def test_runner_state_accepted_not_terminal():
    """last_decision=accepted forces terminal=false."""
    from jsonschema import validate, ValidationError
    schema = json.loads((CONTRACTS / "RUNNER_STATE.schema.json").read_text(encoding="utf-8"))
    state = {
        "runner_id": "r1", "task_id": "t1", "current_step": 0, "current_round": 0,
        "terminal": True, "heartbeat": "2026-06-02T00:00:00Z",
        "last_decision": "accepted", "next_action": "next",
    }
    with pytest.raises(ValidationError):
        validate(instance=state, schema=schema)


# ── RUNNER_STEP_RESULT schema validation ────────────────────────────

def test_runner_step_result_schema_valid():
    from jsonschema import Draft202012Validator
    schema = json.loads((CONTRACTS / "RUNNER_STEP_RESULT.schema.json").read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)


def test_step_success_continue_requires_next_action():
    """step_success_continue requires next_action and terminal=false."""
    from jsonschema import validate, ValidationError
    schema = json.loads((CONTRACTS / "RUNNER_STEP_RESULT.schema.json").read_text(encoding="utf-8"))
    step = {"step_id": "s1", "step_type": "validate_schemas",
            "status": "step_success_continue", "terminal": False}
    with pytest.raises(ValidationError):
        validate(instance=step, schema=schema)

    step["next_action"] = "continue_to_next"
    # Must also include safety to avoid allOf[4] matching when absent
    step["safety"] = {"high_risk_action_attempted": False, "human_confirmed": True,
                      "forbidden_action_blocked": False, "schema_validated": True}
    validate(instance=step, schema=schema)


def test_step_blocked_is_terminal():
    """step_blocked forces terminal=true."""
    from jsonschema import validate, ValidationError
    schema = json.loads((CONTRACTS / "RUNNER_STEP_RESULT.schema.json").read_text(encoding="utf-8"))
    step = {"step_id": "s1", "step_type": "schema_check",
            "status": "step_blocked", "terminal": False}
    with pytest.raises(ValidationError):
        validate(instance=step, schema=schema)


def test_high_risk_forces_human_required():
    """high_risk_action_attempted=true forces step_human_required."""
    from jsonschema import validate, ValidationError
    schema = json.loads((CONTRACTS / "RUNNER_STEP_RESULT.schema.json").read_text(encoding="utf-8"))
    step = {
        "step_id": "s1", "step_type": "safety_check",
        "status": "step_success_continue", "terminal": False,
        "next_action": "ok",
        "safety": {"high_risk_action_attempted": True, "human_confirmed": False}
    }
    with pytest.raises(ValidationError):
        validate(instance=step, schema=schema)


# ── Dispatcher Integration ──────────────────────────────────────────

def test_dispatch_result_schema_exists_and_valid():
    """DISPATCH_RESULT.schema.json is valid."""
    from jsonschema import Draft202012Validator
    schema = json.loads((CONTRACTS / "DISPATCH_RESULT.schema.json").read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
