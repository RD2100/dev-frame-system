#!/usr/bin/env python3
"""oracle_flow_runner.py v6 — Run-until-terminal with contract enforcement.

Key v6 changes:
  - Real run_until_terminal mode: CLI fallback FORBIDDEN. Only consumes
    FLOW_OUTCOME.next_task_spec_path.
  - Each step re-reads FLOW_OUTCOME to resolve the next TaskSpec chain.
  - RUNNER_CONTRACT is built and schema-validated before execution.
  - All 6 schemas + policies must be readable; missing/corrupt = fail-closed.
  - Terminal states do NOT hint Phase 4.
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# ── Policy file list (from agent-acceptance) ─────────────────────────
AA1_POLICIES = [
    "TERMINAL_STATE_POLICY.md",
    "DISPATCHER_POLICY.md",
    "AUTONOMOUS_PROGRESS_POLICY.md",
    "HUMAN_REQUIRED_TAXONOMY.md",
    "STAGE_GATE_POLICY.md",
    "EVIDENCE_PACK_CONTRACT.md",
]
AA2_POLICIES = [
    "FLOW_RUNNER_POLICY.md",
    "TASKSPEC_RUNNER_POLICY.md",
    "RUN_UNTIL_TERMINAL_POLICY.md",
    "NEXT_TASKSPEC_CONSUMPTION_POLICY.md",
    "RUNNER_FAILURE_POLICY.md",
]
ALL_POLICIES = AA1_POLICIES + AA2_POLICIES

ALL_SCHEMAS = [
    "FLOW_OUTCOME.schema.json",
    "TASKSPEC.schema.json",
    "DISPATCH_RESULT.schema.json",
    "RUNNER_CONTRACT.schema.json",
    "RUNNER_STATE.schema.json",
    "RUNNER_STEP_RESULT.schema.json",
]


def ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load_json(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


# ── Validation Helpers ───────────────────────────────────────────────

def validate_schema(instance: dict, schema_path: Path) -> tuple[bool, str]:
    if not schema_path.exists():
        return False, f"Schema file not found: {schema_path}"
    try:
        schema = load_json(schema_path)
        from jsonschema import validate, ValidationError
        validate(instance=instance, schema=schema)
        return True, ""
    except ValidationError as e:
        return False, f"{schema_path.name}: {e.message}"
    except Exception as e:
        return False, f"{schema_path.name}: {e}"


def check_schema_exists(contracts_root: Path, name: str) -> tuple[bool, str]:
    path = contracts_root / "contracts" / name
    if not path.exists():
        return False, f"{name}: schema file MISSING"
    try:
        load_json(path)
        return True, ""
    except Exception as e:
        return False, f"{name}: corrupt/unreadable — {e}"


def check_policies(contracts_root: Path) -> tuple[bool, list[str], list[dict]]:
    """Read all policy files. Returns (all_ok, errors, policy_records)."""
    errors = []
    records = []
    policies_dir = contracts_root / "policies"
    for name in ALL_POLICIES:
        pp = policies_dir / name
        record = {"name": name, "path": str(pp), "exists": False,
                  "size": 0, "readable": False}
        if not pp.exists():
            errors.append(f"policy MISSING: {name}")
            records.append(record)
            continue
        record["exists"] = True
        record["size"] = pp.stat().st_size
        if record["size"] == 0:
            errors.append(f"policy EMPTY: {name}")
            records.append(record)
            continue
        try:
            content = pp.read_text(encoding="utf-8")
            record["readable"] = True
            record["hash"] = __import__('hashlib').sha256(content.encode()).hexdigest()[:16]
        except Exception as e:
            errors.append(f"policy UNREADABLE: {name} — {e}")
            records.append(record)
            continue
        records.append(record)
    return len(errors) == 0, errors, records


def build_runner_contract(
    task_id: str,
    mode: str,
    outcome_path: str,
    taskspec_path: str,
    state_path: str,
    max_steps: int,
    max_rounds: int,
) -> dict:
    return {
        "runner_id": f"runner-{task_id}-{ts()}",
        "task_id": task_id,
        "mode": mode,
        "input_outcome_path": outcome_path,
        "input_taskspec_path": taskspec_path,
        "current_stage": task_id,
        "terminal": False,
        "next_action": "execute_flow",
        "allowed_actions": ["validate_schemas", "execute_taskspec", "generate_evidence_pack",
                           "submit_gpt_review", "write_outcome", "dispatch_next",
                           "generate_reports"],
        "forbidden_actions": ["delete", "move", "rename", "clean_worktree",
                             "overwrite_evidence", "fabricate_baseline",
                             "modify_agent_acceptance_contracts"],
        "max_steps": max_steps,
        "max_rounds": max_rounds,
        "resume_policy": {"resume_enabled": True, "state_path": state_path,
                         "heartbeat_seconds": 60, "max_retries": 3},
        "safety_policy": {"high_risk_triggers_human_required": True,
                         "fail_closed": True, "max_consecutive_failures": 3,
                         "require_schema_validation": True},
        "required_outputs": ["FLOW_OUTCOME.json", "RUNNER_STATE.json",
                            "RUNNER_STEP_RESULT.json"],
    }


# ── Runner State ─────────────────────────────────────────────────────

def init_runner_state(
    task_id: str, outcome: dict, taskspec_path: str,
    max_steps: int, max_rounds: int,
) -> dict:
    return {
        "runner_id": f"runner-{task_id}-{ts()}",
        "task_id": task_id,
        "current_step": 0,
        "current_round": 0,
        "terminal": False,
        "last_decision": outcome.get("business_decision", "accepted"),
        "next_action": "validate_schemas_and_execute",
        "next_task_spec_path": str(taskspec_path),
        "last_outcome_path": "",
        "last_dispatch_result_path": "",
        "errors": [],
        "retries": {"current_step_retries": 0, "current_round_retries": 0, "total_retries": 0},
        "heartbeat": ts(),
        "resume_command": f"python tools/oracle_flow_runner.py --task-id {task_id} --mode resume",
        "reason": "Runner initialized; awaiting review (not Phase 4)",
    }


def validate_runner_state(state: dict, schema_path: Path) -> tuple[bool, str]:
    return validate_schema(state, schema_path)


def save_state(state: dict, output_dir: Path, contracts_root: Path = None):
    state["heartbeat"] = ts()
    output_dir.mkdir(parents=True, exist_ok=True)
    if contracts_root:
        s_path = contracts_root / "contracts" / "RUNNER_STATE.schema.json"
        valid, err = validate_schema(state, s_path)
        if not valid:
            raise RuntimeError(f"RUNNER_STATE validation FAILED before save: {err}")
    (output_dir / "RUNNER_STATE.json").write_text(
        json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")


# ── Flow Execution ───────────────────────────────────────────────────

def execute_flow(
    task_id: str,
    outcome_path: Path,
    taskspec_path: Path,
    contracts_root: Path,
    output_dir: Path,
    mode: str = "run_until_terminal",
    max_steps: int = 3,
    max_rounds: int = 3,
    auto_submit: bool = False,
    on_step_complete: callable = None,
) -> dict:
    """Main flow runner loop.

    Args:
        on_step_complete: Optional callback(step_num, state, output_dir, outcome_path)
        called after each step's state save. Use for production chain tests
        that write fresh outcomes between steps.
    """

    log_lines: list[str] = []
    steps: list[dict] = []

    def log(evt: str, detail: str = ""):
        entry = f"| {ts()} | {evt} | {detail} |"
        log_lines.append(entry)
        print(f"  [{evt}] {detail}")

    output_dir.mkdir(parents=True, exist_ok=True)
    contracts = contracts_root / "contracts"

    # ── 0. Pre-flight: schema files & policies ──
    schema_errors = []
    for name in ALL_SCHEMAS:
        ok, err = check_schema_exists(contracts_root, name)
        if not ok:
            schema_errors.append(err)
    pol_ok, pol_errs, pol_records = check_policies(contracts_root)
    if schema_errors:
        return {"status": "step_failed", "terminal": True,
                "reason": f"Schema check failed: {'; '.join(schema_errors)}",
                "errors": schema_errors}
    if not pol_ok:
        return {"status": "step_failed", "terminal": True,
                "reason": f"Policy check failed: {'; '.join(pol_errs)}",
                "errors": pol_errs}
    log("preflight_ok", f"{len(ALL_SCHEMAS)} schemas + {len(pol_records)} policies")

    # ── 1. Load FLOW_OUTCOME ──
    if not outcome_path.exists():
        return {"status": "step_failed", "terminal": True,
                "reason": f"FLOW_OUTCOME not found: {outcome_path}"}

    outcome = load_json(outcome_path)
    business = outcome.get("business_decision", "unknown")
    allow_next = outcome.get("allow_next_stage", False)
    is_terminal = outcome.get("terminal", False)

    log("outcome_loaded", f"business={business} allow_next={allow_next} terminal={is_terminal}")

    # ── 2. Pre-conditions ──
    if business != "accepted":
        return {"status": "step_blocked", "terminal": True,
                "reason": f"business_decision={business}, not accepted."}
    if not allow_next:
        return {"status": "step_blocked", "terminal": True,
                "reason": "allow_next_stage=false. Cannot proceed."}

    # ── 3. Resolve TaskSpec — real mode MUST use FLOW_OUTCOME ──
    if mode in ("run_until_terminal", "resume"):
        # Real mode: CLI fallback forbidden
        outcome_ts = outcome.get("next_task_spec_path", "")
        if not outcome_ts:
            return {"status": "step_failed", "terminal": True,
                    "reason": "FLOW_OUTCOME.terminal=false but next_task_spec_path is empty. "
                             "CLI fallback forbidden by NEXT_TASKSPEC_CONSUMPTION_POLICY.",
                    "errors": ["CLI fallback forbidden in real mode"]}
        resolved_ts_path = Path(outcome_ts)
        log("taskspec_from_outcome", f"real mode: consuming {resolved_ts_path}")
    elif mode in ("single_step", "dry_run"):
        # Manual mode: CLI allowed, but must be explicitly acknowledged
        outcome_ts = outcome.get("next_task_spec_path", "")
        if outcome_ts:
            resolved_ts_path = Path(outcome_ts)
            log("taskspec_from_outcome", str(resolved_ts_path))
        elif taskspec_path and taskspec_path.exists():
            resolved_ts_path = taskspec_path
            log("taskspec_from_cli_manual", f"single_step/dry_run: {resolved_ts_path}")
        else:
            return {"status": "step_failed", "terminal": True,
                    "reason": "No valid TaskSpec path in manual mode"}
    else:
        return {"status": "step_failed", "terminal": True,
                "reason": f"Unknown mode: {mode}"}

    if not resolved_ts_path.exists():
        return {"status": "step_failed", "terminal": True,
                "reason": f"TaskSpec not found: {resolved_ts_path}"}
    if resolved_ts_path.suffix == ".md":
        return {"status": "step_failed", "terminal": True,
                "reason": f"Markdown-only TaskSpec rejected: {resolved_ts_path}"}

    try:
        taskspec = load_json(resolved_ts_path) if resolved_ts_path.suffix == ".json" else (
            __import__('yaml').safe_load(resolved_ts_path.read_text(encoding="utf-8")))
    except Exception as e:
        return {"status": "step_failed", "terminal": True,
                "reason": f"Failed to load TaskSpec: {e}"}
    log("taskspec_loaded", f"{len(str(taskspec))} chars from {resolved_ts_path.name}")

    # ── 4. Validate outcome + taskspec ──
    ok, err = validate_schema(outcome, contracts / "FLOW_OUTCOME.schema.json")
    if not ok:
        return {"status": "step_failed", "terminal": True, "reason": f"FLOW_OUTCOME invalid: {err}"}
    ok, err = validate_schema(taskspec, contracts / "TASKSPEC.schema.json")
    if not ok:
        return {"status": "step_failed", "terminal": True, "reason": f"TASKSPEC invalid: {err}"}
    log("schema_validated", "outcome + taskspec OK")

    # ── 5. Build & validate RUNNER_CONTRACT ──
    state_path_str = str(output_dir / "RUNNER_STATE.json")
    contract = build_runner_contract(
        task_id, mode, str(outcome_path), str(resolved_ts_path),
        state_path_str, max_steps, max_rounds,
    )
    ok, err = validate_schema(contract, contracts / "RUNNER_CONTRACT.schema.json")
    if not ok:
        return {"status": "step_failed", "terminal": True,
                "reason": f"RUNNER_CONTRACT invalid: {err}"}
    (output_dir / "RUNNER_CONTRACT.json").write_text(
        json.dumps(contract, indent=2, ensure_ascii=False), encoding="utf-8")
    log("runner_contract", "built + validated")

    # ── 6. Init state ──
    state = init_runner_state(task_id, outcome, str(resolved_ts_path),
                              max_steps, max_rounds)
    state["next_task_spec_path"] = str(resolved_ts_path)
    state["last_outcome_path"] = str(outcome_path)
    ok, err = validate_runner_state(state, contracts / "RUNNER_STATE.schema.json")
    if not ok:
        return {"status": "step_failed", "terminal": True,
                "reason": f"Initial RUNNER_STATE invalid: {err}"}
    save_state(state, output_dir, contracts_root)
    log("state_initialized", f"step=0 terminal=false")

    # ── 7. Main loop ──
    current_outcome = dict(outcome)
    current_outcome_path = outcome_path

    while state["terminal"] is False and state["current_step"] < max_steps:
        step_num = state["current_step"]
        log("step_start", f"step={step_num} round={state['current_round']}")
        log("consuming_ts", str(resolved_ts_path))

        # 7a. Execute
        try:
            from oracle_taskspec_runner import run_taskspec
            step_result = run_taskspec(
                task_id=task_id,
                taskspec_path=resolved_ts_path,
                contracts_root=contracts_root,
                output_dir=output_dir,
            )
        except Exception as e:
            step_result = {
                "step_id": f"{task_id}-step{step_num}", "step_type": "execute_taskspec",
                "status": "step_failed", "terminal": True,
                "errors": [str(e)], "reason": f"Step error: {e}", "next_action": "",
                "safety": {"high_risk_action_attempted": False, "human_confirmed": False,
                           "forbidden_action_blocked": False, "schema_validated": True},
            }

        step_result["step_id"] = step_result.get("step_id", f"{task_id}-step{step_num}")
        steps.append(step_result)
        step_status = step_result.get("status", "step_failed")
        step_terminal = step_result.get("terminal", True)

        # Validate step result — fail-closed on schema failure
        sr_ok, sr_err = validate_schema(step_result, contracts / "RUNNER_STEP_RESULT.schema.json")
        if not sr_ok:
            log("step_result_schema_fail", f"FAIL-CLOSED: {sr_err}")
            state["terminal"] = True
            state["last_decision"] = "partial"
            state["reason"] = f"RUNNER_STEP_RESULT schema validation failed: {sr_err}"
            state["errors"].append(state["reason"])
            state["next_action"] = ""
            save_state(state, output_dir, contracts_root)
            break

        # Save step result
        (output_dir / "RUNNER_STEP_RESULT.json").write_text(
            json.dumps(step_result, indent=2, ensure_ascii=False), encoding="utf-8")
        log("step_done", f"status={step_status} terminal={step_terminal}")

        # 7b. Update state
        state["current_step"] = step_num + 1
        state["terminal"] = step_terminal
        step_biz = step_result.get("business_decision")
        if step_biz and step_biz != "unknown":
            state["last_decision"] = step_biz
        if state["terminal"] and state["last_decision"] == "accepted":
            state["last_decision"] = "partial"
            state["reason"] = "Terminal with accepted → partial per RUNNER_STATE.schema.json"
        state["errors"].extend(step_result.get("errors", []))

        if step_status in ("step_blocked", "step_failed"):
            state["retries"]["current_step_retries"] += 1
            state["retries"]["total_retries"] += 1
            if state["retries"]["current_step_retries"] >= 3:
                state["terminal"] = True
                state["reason"] = f"Max retries exceeded for step {step_num}"
        else:
            state["retries"]["current_step_retries"] = 0

        save_state(state, output_dir, contracts_root)

        # Callback for production chain hooks (e.g., write fresh outcome between steps)
        if on_step_complete:
            try:
                on_step_complete(step_num, state, output_dir, outcome_path)
            except Exception as e:
                log("on_step_complete_error", str(e)[:100])

            # GCA-2B v2: Post-callback schema validation — fail-closed for all failure modes
            if not outcome_path.exists():
                state["terminal"] = True
                state["last_decision"] = "partial"
                state["reason"] = "GCA-2B FAIL-CLOSED: callback deleted or removed FLOW_OUTCOME"
                state["errors"].append(state["reason"])
                state["next_action"] = ""
                log("callback_file_missing", "FAIL-CLOSED: outcome deleted by callback")
                save_state(state, output_dir, contracts_root)
                break

            try:
                fresh = load_json(outcome_path)
            except Exception as e:
                state["terminal"] = True
                state["last_decision"] = "partial"
                state["reason"] = f"GCA-2B FAIL-CLOSED: callback produced corrupt/unreadable FLOW_OUTCOME: {e}"
                state["errors"].append(state["reason"])
                state["next_action"] = ""
                log("callback_file_corrupt", f"FAIL-CLOSED: {e}")
                save_state(state, output_dir, contracts_root)
                break

            ok, err = validate_schema(fresh, contracts / "FLOW_OUTCOME.schema.json")
            if not ok:
                state["terminal"] = True
                state["last_decision"] = "partial"
                state["reason"] = f"GCA-2B FAIL-CLOSED: callback produced schema-invalid FLOW_OUTCOME: {err}"
                state["errors"].append(state["reason"])
                state["next_action"] = ""
                log("callback_schema_fail", f"FAIL-CLOSED: {err}")
                save_state(state, output_dir, contracts_root)
                break

        # 7c. max_steps check
        if state["current_step"] >= max_steps and not state["terminal"]:
            state["terminal"] = True
            state["last_decision"] = "partial"
            state["reason"] = f"Max steps ({max_steps}) reached — safety stop, not accepted"
            state["resume_command"] = f"python tools/oracle_flow_runner.py --task-id {task_id} --mode resume"
            state["next_action"] = ""
            state["next_task_spec_path"] = ""
            save_state(state, output_dir, contracts_root)
            log("max_steps", f"safety stop at {max_steps}")
            break

        # 7d. terminal=true → stop
        if state["terminal"]:
            state["next_action"] = ""
            state["next_task_spec_path"] = ""
            state["reason"] = state.get("reason", "") or ("review_pack_ready_awaiting_gpt_review"
                                                          if step_status == "step_success_continue"
                                                          else "awaiting_gpt_review")
            save_state(state, output_dir, contracts_root)
            break

        # 7e. terminal=false: try to resolve next TaskSpec chain
        # Re-read FLOW_OUTCOME to see if a new outcome was produced
        if current_outcome_path.exists():
            try:
                fresh_outcome = load_json(current_outcome_path)
                new_ts = fresh_outcome.get("next_task_spec_path", "")
                repeat_allowed = fresh_outcome.get("repeat_allowed", False)
                if new_ts and Path(new_ts).exists():
                    if str(new_ts) != str(resolved_ts_path):
                        resolved_ts_path = Path(new_ts)
                        state["next_task_spec_path"] = str(resolved_ts_path)
                        state["next_action"] = "consume_next_taskspec"
                        state["last_outcome_path"] = str(current_outcome_path)
                        log("chain_resolve", f"next TaskSpec from fresh outcome: {resolved_ts_path}")
                        save_state(state, output_dir, contracts_root)
                        continue
                    elif repeat_allowed:
                        log("repeat_explicit", f"outcome repeat_allowed=true: re-executing {resolved_ts_path}")
                        state["next_action"] = "repeat_taskspec_per_outcome"
                        save_state(state, output_dir, contracts_root)
                        continue
                    else:
                        # Same path, no repeat directive → fail-closed
                        state["terminal"] = True
                        state["last_decision"] = "partial"
                        state["reason"] = (f"Fresh outcome still points to same TaskSpec ({new_ts}) "
                                           "without repeat_allowed=true — fail-closed")
                        state["errors"].append(state["reason"])
                        state["next_action"] = ""
                        save_state(state, output_dir, contracts_root)
                        log("fail_closed_same_path", state["reason"])
                        break
            except Exception:
                pass  # Outcome re-read failed; fall through to step result check

        # Use step result's next_action or outcome's next_task_spec_path
        next_action = step_result.get("next_action", "")
        # Try to find next TaskSpec from step context
        new_ts_from_state = state.get("next_task_spec_path", "")
        if new_ts_from_state and Path(new_ts_from_state).exists() and str(new_ts_from_state) != str(resolved_ts_path):
            resolved_ts_path = Path(new_ts_from_state)
            state["next_action"] = "consume_next_taskspec"
            log("chain_step", f"next TaskSpec from state chain: {resolved_ts_path}")
            save_state(state, output_dir, contracts_root)
            continue

        # 7f. No valid next TaskSpec → fail-closed
        if not state.get("next_task_spec_path") and not next_action:
            state["terminal"] = True
            state["reason"] = "terminal=false but no next_task_spec_path and no next_action — fail-closed per NEXT_TASKSPEC_CONSUMPTION_POLICY"
            state["errors"].append(state["reason"])
            state["next_action"] = ""
            save_state(state, output_dir, contracts_root)
            log("fail_closed_no_chain", state["reason"])
            break

        # If we have next_action but no new TaskSpec path, stop (max_steps safety)
        if not state.get("next_task_spec_path"):
            state["terminal"] = True
            state["reason"] = "terminal=false, has next_action but no next_task_spec_path — need outcome update"
            state["next_action"] = ""
            save_state(state, output_dir, contracts_root)
            log("stop_no_path", "has action but no new TaskSpec to consume")
            break

    # ── 8. Finalize ──
    state["heartbeat"] = ts()
    if state["terminal"]:
        state["next_action"] = ""  # Never hint Phase 4 before GPT accepted
        state["reason"] = state.get("reason", "") or "review_pack_ready_awaiting_gpt_review"
    save_state(state, output_dir, contracts_root)

    # ── 9. Save log ──
    log_path = output_dir / "FLOW_RUNNER_LOG.md"
    log_path.write_text("# Flow Runner Log (v6)\n\n| Time | Event | Details |\n|------|-------|---------|\n" +
                        "\n".join(log_lines), encoding="utf-8")
    log("log_saved", str(log_path))

    return {
        "runner_id": state["runner_id"],
        "task_id": task_id,
        "steps_executed": len(steps),
        "terminal": state["terminal"],
        "last_decision": state["last_decision"],
        "reason": state.get("reason", ""),
        "steps": steps,
        "state": state,
    }


# ── CLI ──────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Flow Runner v6 — run-until-terminal")
    parser.add_argument("--task-id", default="s3-phase3")
    parser.add_argument("--outcome", default="_reports/oracle-flow-state/s2/FLOW_OUTCOME.json")
    parser.add_argument("--contracts-root", default="D:/agent-acceptance")
    parser.add_argument("--taskspec", default="_reports/s3-phase3/S3_PHASE3_TASKSPEC.json")
    parser.add_argument("--output-dir", default="_reports/s3-phase3")
    parser.add_argument("--mode", default="run_until_terminal",
                        choices=["run_until_terminal", "single_step", "dry_run", "resume"])
    parser.add_argument("--max-steps", type=int, default=3)
    parser.add_argument("--max-rounds", type=int, default=3)
    parser.add_argument("--auto-submit", action="store_true", default=False)
    args = parser.parse_args()

    outcome_path = Path(args.outcome)
    taskspec_path = Path(args.taskspec)
    contracts_root = Path(args.contracts_root)
    output_dir = Path(args.output_dir)
    mode = args.mode

    print(f"Flow Runner v6 — {args.task_id}")
    print(f"  mode: {mode}")
    print(f"  outcome: {outcome_path}")
    print(f"  taskspec: {taskspec_path} (CLI fallback: {'forbidden' if mode in ('run_until_terminal', 'resume') else 'allowed'})")
    print(f"  contracts: {contracts_root}")
    print(f"  max_steps: {args.max_steps}")

    result = execute_flow(
        task_id=args.task_id, outcome_path=outcome_path,
        taskspec_path=taskspec_path, contracts_root=contracts_root,
        output_dir=output_dir, mode=mode,
        max_steps=args.max_steps, max_rounds=args.max_rounds,
        auto_submit=args.auto_submit,
    )

    print(f"\n=== Flow Runner v6 Result ===")
    print(f"  steps: {result['steps_executed']}")
    print(f"  terminal: {result['terminal']}")
    print(f"  decision: {result['last_decision']}")
    print(f"  reason: {result['reason']}")

    if result["terminal"]:
        sys.exit(0 if not result.get("errors") else 20)
    else:
        sys.exit(0)


if __name__ == "__main__":
    main()
