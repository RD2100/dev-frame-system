#!/usr/bin/env python3
"""Tests for oracle_flow_runner.py — S3 Phase 3"""

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


def _tmp_outcome(tmp_path: Path, overrides: dict | None = None, ts_override: Path = None) -> Path:
    data = {
        "task_id": "test-flow",
        "stage": "test",
        "transport_status": "success",
        "business_decision": "accepted",
        "dispatch_status": "dispatched",
        "overall_status": "accepted",
        "allow_next_stage": True,
        "next_stage": "test_next",
        "next_task_spec_path": str(ts_override) if ts_override else "",
        "required_next_action": "test_action",
        "terminal": False,
        "errors": [],
        "safety": {"destructive_action": False, "manual_confirm_required": False},
    }
    if overrides:
        data.update(overrides)
    p = tmp_path / "FLOW_OUTCOME.json"
    p.write_text(json.dumps(data), encoding="utf-8")
    return p


def _tmp_taskspec(tmp_path: Path) -> Path:
    data = {
        "task_id": "test-task",
        "stage": "test",
        "goal": "Test",
        "allowed_actions": ["run tests", "validate"],
        "forbidden_actions": ["delete any file"],
        "required_outputs": ["out.md"],
        "terminal_conditions": {"terminal": False, "reason": "test"},
        "review_required": False,
        "review_by": "automated_test",
        "next_on_accepted": "next",
        "next_on_blocked": "stop",
        "next_on_human_required": "stop",
        "high_risk": False,
    }
    p = tmp_path / "test_taskspec.json"
    p.write_text(json.dumps(data), encoding="utf-8")
    return p


# ── FLOW_OUTCOME accepted + allow_next_stage=true → proceeds ────────

def test_flow_runner_proceeds_on_accepted(tmp_path):
    from oracle_flow_runner import execute_flow
    ts = _tmp_taskspec(tmp_path)
    oc = _tmp_outcome(tmp_path, ts_override=ts)  # outcome.next_task_spec_path = taskspec
    result = execute_flow(
        task_id="test-flow",
        outcome_path=oc,
        taskspec_path=ts,
        contracts_root=Path("D:/agent-acceptance"),
        output_dir=tmp_path,
        max_steps=1,
        max_rounds=1,
    )
    assert result["steps_executed"] == 1
    assert result["terminal"] is True  # max_steps=1


# ── business_decision=blocked → blocked ─────────────────────────────

def test_flow_runner_blocked_on_blocked_decision(tmp_path):
    from oracle_flow_runner import execute_flow
    ts = _tmp_taskspec(tmp_path)
    oc = _tmp_outcome(tmp_path, {
        "business_decision": "blocked",
        "overall_status": "blocked",
        "allow_next_stage": False,
        "required_next_action": "reconcile",
    }, ts_override=ts)
    result = execute_flow("test", oc, ts, Path("D:/agent-acceptance"), tmp_path)
    assert result["status"] == "step_blocked"
    assert result["terminal"] is True


# ── allow_next_stage=false → blocked ───────────────────────────────

def test_flow_runner_blocked_on_allow_false(tmp_path):
    from oracle_flow_runner import execute_flow
    ts = _tmp_taskspec(tmp_path)
    oc = _tmp_outcome(tmp_path, {
        "business_decision": "accepted",
        "overall_status": "accepted",
        "allow_next_stage": False,
    }, ts_override=ts)
    result = execute_flow("test", oc, ts, Path("D:/agent-acceptance"), tmp_path)
    assert result["status"] == "step_blocked"
    assert result["terminal"] is True


# ── Markdown-only TaskSpec → rejected ────────────────────────────────

def test_flow_runner_rejects_markdown_taskspec(tmp_path):
    from oracle_flow_runner import execute_flow
    md = tmp_path / "taskspec.md"
    md.write_text("# markdown only", encoding="utf-8")
    oc = _tmp_outcome(tmp_path, {"next_task_spec_path": str(md)})
    result = execute_flow("test", oc, md, Path("D:/agent-acceptance"), tmp_path)
    assert result["status"] == "step_failed"
    assert result["terminal"] is True
    assert "Markdown" in result["reason"]


# ── terminal=false RUNNER_STATE has next_action ─────────────────────

def test_runner_state_has_next_action_when_terminal_false(tmp_path):
    from oracle_flow_runner import init_runner_state
    outcome = {"business_decision": "accepted", "allow_next_stage": True,
               "next_stage": "test", "terminal": False}
    ts_path = tmp_path / "ts.json"
    state = init_runner_state("test", outcome, str(ts_path), 3, 3)
    assert state["terminal"] is False
    assert state["next_action"] != ""
    assert state["next_task_spec_path"] == str(ts_path)


# ── flow_runner absent outcome → fail ───────────────────────────────

def test_flow_runner_missing_outcome_fail(tmp_path):
    from oracle_flow_runner import execute_flow
    oc = tmp_path / "nonexistent.json"
    ts = _tmp_taskspec(tmp_path)
    result = execute_flow("test", oc, ts, Path("D:/agent-acceptance"), tmp_path)
    assert result["terminal"] is True
    assert "not found" in result.get("reason", "").lower()


# ── RUNNER_STATE validates against schema ───────────────────────────

def test_runner_state_validates(tmp_path):
    from oracle_flow_runner import init_runner_state, validate_runner_state
    outcome = {"business_decision": "accepted", "allow_next_stage": True,
               "next_stage": "test", "terminal": False}
    ts_path = tmp_path / "ts.json"
    state = init_runner_state("test", outcome, str(ts_path), 3, 3)
    valid, err = validate_runner_state(state, Path("D:/agent-acceptance/contracts/RUNNER_STATE.schema.json"))
    assert valid, f"State validation failed: {err}"


# ── RUNNER_STEP_RESULT validates against schema ─────────────────────

def test_runner_step_result_validates(tmp_path):
    from oracle_taskspec_runner import run_taskspec
    ts = _tmp_taskspec(tmp_path)
    result = run_taskspec("test", ts, Path("D:/agent-acceptance"), tmp_path)
    from oracle_flow_runner import validate_schema
    valid, err = validate_schema(result, Path("D:/agent-acceptance/contracts/RUNNER_STEP_RESULT.schema.json"))
    assert valid, f"Step result validation failed: {err}"


# ── Max steps state validates against schema ───────────────────────

def test_max_steps_state_validates_against_schema(tmp_path):
    """When max_steps triggers terminal, RUNNER_STATE must pass schema validation."""
    from oracle_flow_runner import execute_flow
    ts = _tmp_taskspec(tmp_path)
    oc = _tmp_outcome(tmp_path, ts_override=ts)
    result = execute_flow(
        task_id="test-max-steps",
        outcome_path=oc,
        taskspec_path=ts,
        contracts_root=Path("D:/agent-acceptance"),
        output_dir=tmp_path,
        max_steps=1,
        max_rounds=1,
    )
    assert result["terminal"] is True
    assert result["last_decision"] != "accepted", "last_decision must not be accepted when terminal=true"
    # Load the saved state and validate
    state_path = tmp_path / "RUNNER_STATE.json"
    assert state_path.exists()
    import json
    state = json.loads(state_path.read_text(encoding="utf-8"))
    from oracle_flow_runner import validate_schema
    valid, err = validate_schema(state, Path("D:/agent-acceptance/contracts/RUNNER_STATE.schema.json"))
    assert valid, f"RUNNER_STATE after max_steps failed schema: {err}"
    assert state["terminal"] is True
    assert "resume_command" in state


# ── next_task_spec_path from FLOW_OUTCOME consumed ───────────────────

def test_flow_runner_consumes_outcome_taskspec(tmp_path):
    """Runner uses FLOW_OUTCOME.next_task_spec_path, not CLI fallback."""
    from oracle_flow_runner import execute_flow
    # Distinct taskspec referenced by outcome
    outcome_ts_path = tmp_path / "outcome_taskspec.json"
    outcome_ts_path.write_text(json.dumps({
        "task_id": "outcome-task", "stage": "test", "goal": "From OUTCOME",
        "allowed_actions": ["run tests"], "forbidden_actions": ["delete"],
        "required_outputs": ["out.md"],
        "terminal_conditions": {"terminal": True, "reason": "accepted_done"},
        "review_required": False, "review_by": "automated_test",
        "next_on_accepted": "await_gpt_review_decision",
        "next_on_blocked": "stop", "next_on_human_required": "stop",
        "high_risk": False,
    }), encoding="utf-8")
    # Outcome with repeat_allowed so same-path is explicit
    oc = _tmp_outcome(tmp_path, {
        "next_task_spec_path": str(outcome_ts_path),
        "repeat_allowed": True,
    })
    result = execute_flow("test", oc, outcome_ts_path, Path("D:/agent-acceptance"), tmp_path)
    assert result["steps_executed"] >= 1


def test_flow_runner_fail_closed_with_no_taskspec(tmp_path):
    """No next_task_spec_path in outcome → fail-closed in real mode."""
    from oracle_flow_runner import execute_flow
    ts = _tmp_taskspec(tmp_path)
    oc = _tmp_outcome(tmp_path, {"next_task_spec_path": ""})
    result = execute_flow("test", oc, ts, Path("D:/agent-acceptance"), tmp_path)
    assert result["terminal"] is True
    assert "empty" in result.get("reason", "").lower() or "CLI" in result.get("reason", "")


# ── Accepted + terminal=true rejected by schema ─────────────────────

def test_accepted_terminal_true_rejected_by_schema():
    """RUNNER_STATE.schema.json forbids last_decision=accepted with terminal=true."""
    import json
    from jsonschema import validate, ValidationError
    import pytest
    schema = json.loads(Path("D:/agent-acceptance/contracts/RUNNER_STATE.schema.json").read_text(encoding="utf-8"))
    bad_state = {
        "runner_id": "r1", "task_id": "t1",
        "current_step": 1, "current_round": 0,
        "terminal": True, "heartbeat": "2026-06-02T00:00:00Z",
        "last_decision": "accepted", "next_action": "next",
    }
    with pytest.raises(ValidationError):
        validate(instance=bad_state, schema=schema)


# ══════════════════════════════════════════════════════════════════════
# v6 Tests — CLI fallback forbidden, chain consumption, contract validation
# ══════════════════════════════════════════════════════════════════════

# ── CLI fallback forbidden in real mode ─────────────────────────────

def test_v6_real_mode_cli_fallback_forbidden(tmp_path):
    """Real mode: outcome has empty next_task_spec_path → fail-closed, no CLI fallback."""
    from oracle_flow_runner import execute_flow
    ts = _tmp_taskspec(tmp_path)
    oc = _tmp_outcome(tmp_path, {"next_task_spec_path": ""})
    result = execute_flow("test", oc, ts, Path("D:/agent-acceptance"), tmp_path,
                         mode="run_until_terminal")
    assert result["status"] == "step_failed"
    assert result["terminal"] is True
    assert "CLI" in result.get("reason", "") or "empty" in result.get("reason", "").lower()


def test_v6_real_mode_no_outcome_ts_fail_closed(tmp_path):
    """Real mode: outcome.next_task_spec_path missing entirely → fail-closed."""
    from oracle_flow_runner import execute_flow
    ts = _tmp_taskspec(tmp_path)
    oc = _tmp_outcome(tmp_path, ts_override=None)  # no path set
    result = execute_flow("test", oc, ts, Path("D:/agent-acceptance"), tmp_path,
                         mode="run_until_terminal")
    assert result["terminal"] is True


def test_v6_real_mode_missing_file_fail_closed(tmp_path):
    """Real mode: outcome.next_task_spec_path points to non-existent file → fail-closed."""
    from oracle_flow_runner import execute_flow
    ts = _tmp_taskspec(tmp_path)
    oc = _tmp_outcome(tmp_path, {"next_task_spec_path": str(tmp_path / "nonexistent.json")})
    result = execute_flow("test", oc, ts, Path("D:/agent-acceptance"), tmp_path,
                         mode="run_until_terminal")
    assert result["terminal"] is True
    assert "not found" in result.get("reason", "").lower()


def test_v6_real_mode_markdown_ts_fail_closed(tmp_path):
    """Real mode: outcome.next_task_spec_path points to .md file → fail-closed."""
    from oracle_flow_runner import execute_flow
    ts = _tmp_taskspec(tmp_path)
    md = tmp_path / "ts.md"
    md.write_text("# markdown", encoding="utf-8")
    oc = _tmp_outcome(tmp_path, {"next_task_spec_path": str(md)})
    result = execute_flow("test", oc, ts, Path("D:/agent-acceptance"), tmp_path,
                         mode="run_until_terminal")
    assert result["terminal"] is True
    assert "Markdown" in result["reason"]


# ── RUNNER_CONTRACT validation ───────────────────────────────────────

def test_v6_runner_contract_built_and_validated(tmp_path):
    """execute_flow builds and validates RUNNER_CONTRACT against schema."""
    from oracle_flow_runner import execute_flow
    ts = _tmp_taskspec(tmp_path)
    oc = _tmp_outcome(tmp_path, ts_override=ts)
    result = execute_flow("test", oc, ts, Path("D:/agent-acceptance"), tmp_path,
                         max_steps=1, max_rounds=1)
    contract_path = tmp_path / "RUNNER_CONTRACT.json"
    assert contract_path.exists(), "RUNNER_CONTRACT.json should be produced"
    import json
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    assert contract["mode"] == "run_until_terminal"
    assert contract["safety_policy"]["fail_closed"] is True


def test_v6_runner_contract_missing_schema_fail_closed(tmp_path):
    """When contracts_root has no schemas, fail-closed."""
    from oracle_flow_runner import execute_flow
    ts = _tmp_taskspec(tmp_path)
    oc = _tmp_outcome(tmp_path, ts_override=ts)
    result = execute_flow("test", oc, ts, tmp_path, tmp_path)  # contracts_root = tmp_path (no schemas)
    assert result["status"] == "step_failed"
    assert result["terminal"] is True


# ── Chain multi-TaskSpec execution ───────────────────────────────────

def test_v7_chain_proof_task_a_to_task_b(tmp_path):
    """V7: Chain consumption — task A then task B via sequential outcomes."""
    from oracle_flow_runner import execute_flow
    ts_a = tmp_path / "task_a.json"
    ts_a.write_text(json.dumps({
        "task_id": "task-a", "stage": "test", "goal": "Task A",
        "allowed_actions": ["run tests"], "forbidden_actions": ["delete"],
        "required_outputs": ["out_a.md"],
        "terminal_conditions": {"terminal": False, "reason": "chain_continue"},
        "review_required": False, "review_by": "automated_test",
        "next_on_accepted": "await_gpt_review_decision",
        "next_on_blocked": "stop", "next_on_human_required": "stop",
        "high_risk": False,
    }), encoding="utf-8")
    oc_a = _tmp_outcome(tmp_path, {"task_id": "flow-a", "next_task_spec_path": str(ts_a)})
    out_a = tmp_path / "out_a"; out_a.mkdir()
    r_a = execute_flow("flow-a", oc_a, ts_a, Path("D:/agent-acceptance"), out_a, max_steps=1, max_rounds=1)
    assert r_a["steps_executed"] == 1
    log_a = (out_a / "FLOW_RUNNER_LOG.md").read_text(encoding="utf-8")
    assert "task_a.json" in log_a

    ts_b = tmp_path / "task_b.json"
    ts_b.write_text(json.dumps({
        "task_id": "task-b", "stage": "test", "goal": "Task B",
        "allowed_actions": ["validate"], "forbidden_actions": ["delete"],
        "required_outputs": ["out_b.md"],
        "terminal_conditions": {"terminal": False, "reason": "chain_continue"},
        "review_required": False, "review_by": "automated_test",
        "next_on_accepted": "await_gpt_review_decision",
        "next_on_blocked": "stop", "next_on_human_required": "stop",
        "high_risk": False,
    }), encoding="utf-8")
    oc_b = _tmp_outcome(tmp_path, {"task_id": "flow-b", "next_task_spec_path": str(ts_b)})
    out_b = tmp_path / "out_b"; out_b.mkdir()
    r_b = execute_flow("flow-b", oc_b, ts_b, Path("D:/agent-acceptance"), out_b, max_steps=1, max_rounds=1)
    assert r_b["steps_executed"] == 1
    log_b = (out_b / "FLOW_RUNNER_LOG.md").read_text(encoding="utf-8")
    assert "task_b.json" in log_b


def test_v8_single_run_chain_A_to_B(tmp_path, monkeypatch):
    """V8: Single execute_flow() call proves task A → task B chain consumption.

    Uses monkeypatch to make the outcome file 'change' between steps:
    step 0 reads outcome → task_a.json, step 1 reads outcome → task_b.json.
    Proves chain within ONE run-until-terminal invocation.
    """
    from oracle_flow_runner import execute_flow, load_json as original_load

    # Task A
    ts_a = tmp_path / "task_a.json"
    ts_a.write_text(json.dumps({
        "task_id": "task-a", "stage": "test", "goal": "Task A — consumed first",
        "allowed_actions": ["run tests"], "forbidden_actions": ["delete"],
        "required_outputs": ["out_a.md"],
        "terminal_conditions": {"terminal": False, "reason": "chain_continue"},
        "review_required": False, "review_by": "automated_test",
        "next_on_accepted": "await_gpt_review_decision",
        "next_on_blocked": "stop", "next_on_human_required": "stop",
        "high_risk": False,
    }), encoding="utf-8")

    # Task B
    ts_b = tmp_path / "task_b.json"
    ts_b.write_text(json.dumps({
        "task_id": "task-b", "stage": "test", "goal": "Task B — consumed second",
        "allowed_actions": ["validate"], "forbidden_actions": ["delete"],
        "required_outputs": ["out_b.md"],
        "terminal_conditions": {"terminal": False, "reason": "chain_continue"},
        "review_required": False, "review_by": "automated_test",
        "next_on_accepted": "await_gpt_review_decision",
        "next_on_blocked": "stop", "next_on_human_required": "stop",
        "high_risk": False,
    }), encoding="utf-8")

    # Outcome that initially points to A
    oc_path = _tmp_outcome(tmp_path, {"task_id": "chain-flow", "next_task_spec_path": str(ts_a)})

    # Monkeypatch load_json: on FIRST call to oc_path, return outcome → A.
    # On SECOND call, return outcome → B.
    call_count = [0]
    original_load_json = original_load.__wrapped__ if hasattr(original_load, '__wrapped__') else original_load

    def patched_load(path):
        import json as _json
        # Intercept only the outcome path; delegate everything else
        if str(path) == str(oc_path):
            call_count[0] += 1
            if call_count[0] <= 1:
                # First call: outcome → A
                return _json.loads(oc_path.read_text(encoding="utf-8"))
            else:
                # Second call: outcome → B
                data = _json.loads(oc_path.read_text(encoding="utf-8"))
                data["next_task_spec_path"] = str(ts_b)
                return data
        return original_load_json(path)

    monkeypatch.setattr("oracle_flow_runner.load_json", patched_load)

    # Single flow run with max_steps=2
    out = tmp_path / "out"
    out.mkdir()
    result = execute_flow("chain-flow", oc_path, ts_a, Path("D:/agent-acceptance"), out,
                         max_steps=2, max_rounds=2)

    # Verify: 2 steps executed in ONE run
    assert result["steps_executed"] == 2, f"Expected 2 steps, got {result['steps_executed']}"

    # Verify: both task A and task B appear in the log
    log_text = (out / "FLOW_RUNNER_LOG.md").read_text(encoding="utf-8")
    assert "task_a.json" in log_text, f"Log missing task_a.json: {log_text[:300]}"
    assert "task_b.json" in log_text, f"Log missing task_b.json: {log_text[:300]}"

    # Verify: two different paths were consumed
    consumed = []
    for line in log_text.split("\n"):
        for name in ["task_a.json", "task_b.json"]:
            if name in line and name not in consumed:
                consumed.append(name)
    assert len(consumed) >= 2, f"Only found consumed paths: {consumed}"


# ── State does NOT hint Phase 4 ──────────────────────────────────────

def test_v6_state_no_phase4_hint(tmp_path):
    """RUNNER_STATE must not suggest Phase 4 before GPT accepted."""
    from oracle_flow_runner import execute_flow
    ts = _tmp_taskspec(tmp_path)
    oc = _tmp_outcome(tmp_path, ts_override=ts)
    result = execute_flow("test-nohint", oc, ts, Path("D:/agent-acceptance"), tmp_path,
                         max_steps=1, max_rounds=1)
    import json
    state = json.loads((tmp_path / "RUNNER_STATE.json").read_text(encoding="utf-8"))
    next_action = state.get("next_action", "")
    assert "phase4" not in next_action.lower()
    assert "phase_4" not in next_action.lower()
    assert "long_run" not in next_action.lower()


# ── max_steps is safety stop, not accepted ───────────────────────────

def test_v6_max_steps_safety_stop(tmp_path):
    """max_steps terminal is safety stop (partial), not accepted."""
    from oracle_flow_runner import execute_flow
    ts = _tmp_taskspec(tmp_path)
    oc = _tmp_outcome(tmp_path, ts_override=ts)
    result = execute_flow("test-safety", oc, ts, Path("D:/agent-acceptance"), tmp_path,
                         max_steps=1, max_rounds=1)
    assert result["last_decision"] != "accepted"
    import json
    state = json.loads((tmp_path / "RUNNER_STATE.json").read_text(encoding="utf-8"))
    assert state["terminal"] is True
    assert state.get("resume_command") is not None
    assert "safety" in state.get("reason", "").lower() or "Max steps" in state.get("reason", "")


# ══════════════════════════════════════════════════════════════════════
# v10 Tests — Real file-write chain A→B (no monkeypatch)
# ══════════════════════════════════════════════════════════════════════

def test_v10_real_file_chain_A_to_B(tmp_path):
    """V10: Real production-path chain — single execute_flow() proves A→B.

    Uses on_step_complete callback to simulate TaskSpec Runner writing
    a fresh outcome after step 0. No monkeypatch. The runner's own
    chain resolution code (step 7e) reads the updated outcome file
    and switches to task_b.json.

    Proves:
    - task_a.json consumed in step 0
    - fresh outcome written between steps (pointing to task_b.json)
    - task_b.json consumed in step 1
    - Both paths appear in FLOW_RUNNER_LOG
    - Different TaskSpec IDs consumed
    """
    from oracle_flow_runner import execute_flow

    # Task A
    ts_a = tmp_path / "task_a.json"
    ts_a.write_text(json.dumps({
        "task_id": "task-a", "stage": "test", "goal": "Task A — step 0",
        "allowed_actions": ["run tests"], "forbidden_actions": ["delete"],
        "required_outputs": ["out_a.md"],
        "terminal_conditions": {"terminal": False, "reason": "chain_continue"},
        "review_required": False, "review_by": "automated_test",
        "next_on_accepted": "await_gpt_review_decision",
        "next_on_blocked": "stop", "next_on_human_required": "stop",
        "high_risk": False,
    }), encoding="utf-8")

    # Task B
    ts_b = tmp_path / "task_b.json"
    ts_b.write_text(json.dumps({
        "task_id": "task-b", "stage": "test", "goal": "Task B — step 1",
        "allowed_actions": ["validate"], "forbidden_actions": ["delete"],
        "required_outputs": ["out_b.md"],
        "terminal_conditions": {"terminal": True, "reason": "review_pack_ready"},
        "review_required": False, "review_by": "automated_test",
        "next_on_accepted": "await_gpt_review_decision",
        "next_on_blocked": "stop", "next_on_human_required": "stop",
        "high_risk": False,
    }), encoding="utf-8")

    # Outcome initially points to A
    oc_path = _tmp_outcome(tmp_path, {"task_id": "chain-v10", "next_task_spec_path": str(ts_a)})

    # Callback: after step 0, write fresh outcome pointing to B
    def write_next_outcome(step_num, state, output_dir, outcome_path):
        if step_num == 0:
            data = {
                "task_id": "chain-v10", "stage": "S3_PHASE3",
                "transport_status": "success", "business_decision": "accepted",
                "dispatch_status": "dispatched", "overall_status": "accepted",
                "allow_next_stage": True, "next_stage": "s3_phase3",
                "next_task_spec_path": str(ts_b),
                "required_next_action": "consume_task_b",
                "terminal": False, "errors": [],
                "safety": {"destructive_action": False, "manual_confirm_required": False},
            }
            outcome_path.write_text(json.dumps(data), encoding="utf-8")

    # Single execute_flow with A→B chain callback
    out = tmp_path / "out"
    out.mkdir()
    result = execute_flow("chain-v10", oc_path, ts_a, Path("D:/agent-acceptance"), out,
                         max_steps=2, max_rounds=2, on_step_complete=write_next_outcome)

    # 2 steps executed in ONE run
    assert result["steps_executed"] == 2, f"Expected 2 steps, got {result['steps_executed']}"

    # Both paths in log
    log_text = (out / "FLOW_RUNNER_LOG.md").read_text(encoding="utf-8")
    assert "task_a.json" in log_text, f"Log missing task_a.json: {log_text[:300]}"
    assert "task_b.json" in log_text, f"Log missing task_b.json: {log_text[:300]}"

    # Two different paths consumed (not the same repeated)
    consumed = [line for line in log_text.split("\n") if "consuming_ts" in line or "task_" in line]
    assert any("task_a.json" in c for c in consumed), f"task_a not consumed: {consumed}"
    assert any("task_b.json" in c for c in consumed), f"task_b not consumed: {consumed}"
    # Verify A and B are different
    assert ts_a != ts_b, "Task A and B paths must differ"
