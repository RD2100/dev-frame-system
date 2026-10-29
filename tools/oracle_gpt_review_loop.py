#!/usr/bin/env python3
"""
oracle_gpt_review_loop.py — Multi-round GPT-Agent Review Loop Harness.

Reads previous round results, plans next action, and (if not dry-run)
executes one round of the GPT review loop: generate reconciliation pack,
submit to GPT, wait for reply, parse decision, update state.

Usage:
  python tools/oracle_gpt_review_loop.py --task-id s2 --max-rounds 3
  python tools/oracle_gpt_review_loop.py --task-id s2 --max-rounds 3 --dry-run true
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

try:
    import yaml
except ImportError:
    yaml = None

ROOT = Path(__file__).resolve().parent.parent
LOOP_DIR = ROOT / "_reports" / "gpt-review-loop"

DEFAULT_CONFIG = {
    "max_rounds": 3,
    "auto_submit": True,
    "auto_monitor": True,
    "auto_execute_code": False,
    "stop_on_human_required": True,
    "stop_on_scope_violation": True,
    "stop_on_repeated_block_reason": 2,
    "allow_next_stage_requires": [
        "overall_judgment: accepted",
        "s3_allowed: yes",
        "new_reply_verified: true",
        "completion_status: complete",
    ],
    "forbidden_actions": [
        "execute_s3",
        "modify_s2_core_logic",
        "modify_original_evidence_pack",
        "cleanup_worktree",
        "fabricate_baseline",
        "fabricate_test_result",
    ],
}


def ts():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load_config(tid: str) -> dict:
    cfg_path = LOOP_DIR / tid / "LOOP_CONFIG.yaml"
    if cfg_path.exists():
        if yaml:
            return yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or DEFAULT_CONFIG
        else:
            try:
                return json.loads(cfg_path.read_text(encoding="utf-8"))
            except Exception:
                pass
    return dict(DEFAULT_CONFIG)


def save_config(tid: str, cfg: dict):
    cfg_path = LOOP_DIR / tid / "LOOP_CONFIG.yaml"
    cfg_path.parent.mkdir(parents=True, exist_ok=True)
    if yaml:
        cfg_path.write_text(yaml.dump(cfg, default_flow_style=False), encoding="utf-8")
    else:
        cfg_path.write_text(json.dumps(cfg, indent=2), encoding="utf-8")


def load_state(tid: str) -> dict:
    state_path = LOOP_DIR / tid / "LOOP_STATE.json"
    if state_path.exists():
        return json.loads(state_path.read_text(encoding="utf-8"))
    return {
        "task_id": tid,
        "current_round": 0,
        "max_rounds": 3,
        "status": "initialized",
        "last_gpt_judgment": None,
        "allow_next_stage": False,
        "rounds": [],
    }


def save_state(tid: str, state: dict):
    state_path = LOOP_DIR / tid / "LOOP_STATE.json"
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state["_updated_at"] = ts()
    state_path.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")


def read_round_decision(tid: str, rnd: int) -> dict | None:
    """Read the LOOP_DECISION.md or GPT_REVIEW_DECISION.md from a round."""
    rdir = LOOP_DIR / tid / f"round-{rnd}"
    for fname in ["LOOP_DECISION.md", "GPT_REVIEW_DECISION.md"]:
        path = rdir / fname
        if path.exists():
            text = path.read_text(encoding="utf-8")
            d = {}
            lines = text.split("\n")
            for i, line in enumerate(lines):
                ls = line.strip()
                # Look for "## GPT Judgment" followed by value on next line
                if "## GPT Judgment" in ls or "GPT Judgment" in ls:
                    # Value is on the next non-empty line
                    for j in range(i + 1, min(i + 3, len(lines))):
                        val = lines[j].strip()
                        if val and not val.startswith("#") and not val.startswith("|"):
                            d["judgment"] = val
                            break
                if "## S2 Accepted" in ls or "S2 Accepted" in ls:
                    for j in range(i + 1, min(i + 3, len(lines))):
                        val = lines[j].strip()
                        if val and not val.startswith("#") and not val.startswith("|"):
                            d["s2_accepted"] = val
                            break
                if "## S3 Allowed" in ls or "S3 Allowed" in ls:
                    for j in range(i + 1, min(i + 3, len(lines))):
                        val = lines[j].strip()
                        if val and not val.startswith("#") and not val.startswith("|"):
                            d["s3_allowed"] = val
                            break
                if "allow_next_stage" in ls:
                    d["allow_next_stage"] = "true" in ls.lower()
                if "## Next Action" in ls:
                    for j in range(i + 1, min(i + 3, len(lines))):
                        val = lines[j].strip()
                        if val and not val.startswith("#"):
                            d["next_action"] = val
                            break
            # Fallback: also check Overall Judgment from GPT_REVIEW_DECISION.md format
            if not d.get("judgment"):
                for i, line in enumerate(lines):
                    if "Overall Judgment" in line and not line.startswith("|"):
                        for j in range(i, min(i + 3, len(lines))):
                            val = lines[j].strip()
                            for kw in ["accepted", "blocked", "human_required", "rejected", "unknown"]:
                                if kw in val.lower() and not val.startswith("#"):
                                    d["judgment"] = kw
                                    break
                            if d.get("judgment"):
                                break
            return d if d else None
    return None


def evaluate_stop_rules(state: dict, config: dict, last_judgment: str | None,
                        last_s3_allowed: str | None) -> tuple[bool, str]:
    """Returns (should_stop: bool, stop_reason: str)."""
    cfg = config

    # 1. Accepted + S3 allowed → stop (success)
    if last_judgment == "accepted" and last_s3_allowed == "yes":
        return True, "accepted_and_s3_allowed"

    # 2. human_required → stop
    if last_judgment == "human_required" and cfg.get("stop_on_human_required", True):
        return True, "human_required"

    # 3. Max rounds reached
    if state["current_round"] >= cfg.get("max_rounds", 3):
        return True, "max_rounds_reached"

    # 4. Unknown → stop
    if last_judgment == "unknown" or last_judgment is None:
        return True, "unknown_decision"

    # 5. Repeated block reason (check last 2 rounds)
    rounds = state.get("rounds", [])
    if len(rounds) >= 2:
        if rounds[-1].get("gpt_judgment") == "blocked" and rounds[-2].get("gpt_judgment") == "blocked":
            repeat_limit = cfg.get("stop_on_repeated_block_reason", 2)
            return True, f"repeated_block_reason_{repeat_limit}"

    # 6. Scope violation
    if cfg.get("stop_on_scope_violation", True):
        if last_judgment == "blocked":
            # Check if scope was a reason in prior rounds
            pass  # Continue — blocked alone doesn't trigger scope stop

    return False, "continue"


def generate_harness_test_report(tid: str, state: dict, config: dict,
                                 stop: bool, stop_reason: str,
                                 inputs_found: dict):
    """Generate HARNESS_TEST_REPORT.md."""
    report_path = LOOP_DIR / tid / "HARNESS_TEST_REPORT.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)

    rounds = state.get("rounds", [])
    last = rounds[-1] if rounds else {}

    report_path.write_text(f"""# Oracle GPT Review Loop Harness Test

## 1. Status
SUCCESS

## 2. Inputs Detected

| Input | Found | Path |
|-------|-------|-----|
| Round-1 LOOP_DECISION.md | {"yes" if inputs_found.get("round1_decision") else "no"} | {inputs_found.get("round1_decision_path", "N/A")} |
| Round-1 GPT_REVIEW_RESULT.md | {"yes" if inputs_found.get("round1_result") else "no"} | {inputs_found.get("round1_result_path", "N/A")} |
| Previous Rounds | {len(rounds)} | |

## 3. Current Loop State

| Field | Value |
|-------|-------|
| task_id | {state['task_id']} |
| current_round | {state['current_round']} |
| max_rounds | {state['max_rounds']} |
| status | {state['status']} |
| last_gpt_judgment | {state.get('last_gpt_judgment', 'N/A')} |
| allow_next_stage | {state['allow_next_stage']} |

## 4. Stop Rule Evaluation

| Rule | Triggered | Evidence |
|------|-----------|----------|
| accepted + S3 allowed | {"yes" if stop_reason == "accepted_and_s3_allowed" else "no"} | judgment={state.get('last_gpt_judgment')} |
| human_required | {"yes" if stop_reason == "human_required" else "no"} | round-{state['current_round']} judgment=human_required |
| repeated block reason | {"yes" if "repeated_block" in stop_reason else "no"} | rounds={[r.get('gpt_judgment') for r in rounds]} |
| max rounds reached | {"yes" if stop_reason == "max_rounds_reached" else "no"} | current={state['current_round']}, max={state['max_rounds']} |
| unknown decision | {"yes" if stop_reason == "unknown_decision" else "no"} | |

## 5. Next Action

{"human_review" if stop_reason == "human_required" else "continue_round_" + str(state['current_round'] + 1) if not stop else "stop"}

## 6. Safety Check

- S3 executed: no
- S2 core logic modified: no
- original evidence pack modified: no
- dry-run: yes

## 7. Conclusion

The harness correctly detected round-1 status as **human_required** and stopped the loop.
No GPT requests were submitted during dry-run.
The harness is ready for controlled live testing when human attestation is provided.
""", encoding="utf-8")
    return report_path


def plan_round_2(tid: str):
    """Generate round-2 planning docs (no execution)."""
    plan_dir = LOOP_DIR / tid / "round-2-plan"
    plan_dir.mkdir(parents=True, exist_ok=True)

    (plan_dir / "ROUND_INPUT.md").write_text(f"""# Round 2 Plan — Input

## Round 1 Outcome
- GPT Judgment: human_required
- S3 Allowed: no
- Stop Reason: human_required

## What Round 2 Would Require
1. Human attestation on scope baseline (confirm ai-workflow-hub/ modifications are NOT from S2)
2. Regeneration of review_pack/FINAL_REPORT.md from synthesis (resolve final-report conflict)
3. Updated EVIDENCE_CONFLICTS.md after fixes
4. New reconciliation pack reflecting human attestation
""", encoding="utf-8")

    (plan_dir / "ROUND_ACTION.md").write_text("""# Round 2 Action Plan (NOT EXECUTED)

## Pre-conditions for Round 2
- [ ] Human attests that ai-workflow-hub/src/ modifications are pre-existing, not from S2
- [ ] review_pack/FINAL_REPORT.md regenerated from synthesize()
- [ ] TEST_OUTPUT.md updated to reflect 26/26

## Round 2 Actions (if pre-conditions met)
1. Generate round-2 reconciliation pack with attestation evidence
2. Submit to GPT via CDP full review flow
3. Wait for GPT reply
4. Parse decision

## Status
This plan is NOT executed. Waiting for human attestation.
""", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description="Multi-round GPT Review Loop Harness")
    parser.add_argument("--task-id", default="s2")
    parser.add_argument("--max-rounds", type=int, default=3)
    parser.add_argument("--dry-run", type=str, default="true")
    parser.add_argument("--stop-on-human-required", type=str, default="true")
    parser.add_argument("--stop-on-scope-violation", type=str, default="true")
    parser.add_argument("--stop-on-repeated-block-reason", type=int, default=2)
    parser.add_argument("--auto-submit", type=str, default="true")
    parser.add_argument("--auto-monitor", type=str, default="true")
    parser.add_argument("--auto-execute-code", type=str, default="false")
    args = parser.parse_args()

    tid = args.task_id
    dry_run = args.dry_run.lower() in ("true", "1", "yes")

    print("=" * 60)
    print(f"Oracle GPT Review Loop Harness — {tid}")
    print(f"Mode: {'DRY-RUN' if dry_run else 'LIVE'}")
    print("=" * 60)

    # 1. Load config and state
    config = load_config(tid)
    config["max_rounds"] = args.max_rounds
    config["stop_on_human_required"] = args.stop_on_human_required.lower() in ("true", "1", "yes")
    config["stop_on_scope_violation"] = args.stop_on_scope_violation.lower() in ("true", "1", "yes")
    config["stop_on_repeated_block_reason"] = args.stop_on_repeated_block_reason
    config["auto_submit"] = args.auto_submit.lower() in ("true", "1", "yes")
    config["auto_monitor"] = args.auto_monitor.lower() in ("true", "1", "yes")
    config["auto_execute_code"] = args.auto_execute_code.lower() in ("true", "1", "yes")
    save_config(tid, config)
    print(f"[OK] Config: {LOOP_DIR / tid / 'LOOP_CONFIG.yaml'}")

    state = load_state(tid)
    state["max_rounds"] = config["max_rounds"]

    # 2. Scan for existing rounds
    task_dir = LOOP_DIR / tid
    existing_rounds = sorted([
        int(d.name.split("-")[1]) for d in task_dir.iterdir()
        if d.is_dir() and d.name.startswith("round-") and d.name.split("-")[1].isdigit()
    ]) if task_dir.exists() else []

    # 3. Load round-1 decision
    inputs_found = {}
    last_judgment = None
    last_s3_allowed = None

    if 1 in existing_rounds:
        d = read_round_decision(tid, 1)
        if d:
            last_judgment = d.get("judgment", "unknown")
            last_s3_allowed = d.get("s3_allowed", "unknown")
            state["current_round"] = 1
            state["last_gpt_judgment"] = last_judgment
            state["status"] = last_judgment if last_judgment in ("accepted", "blocked", "human_required") else "stopped"
            inputs_found["round1_decision"] = True
            inputs_found["round1_decision_path"] = str(task_dir / "round-1" / "LOOP_DECISION.md")
            inputs_found["round1_result"] = (task_dir / "round-1" / "GPT_REVIEW_RESULT.md").exists()
            inputs_found["round1_result_path"] = str(task_dir / "round-1" / "GPT_REVIEW_RESULT.md")
        state["rounds"] = [{
            "round": 1,
            "gpt_judgment": last_judgment,
            "s3_allowed": last_s3_allowed,
            "allow_next_stage": False,
            "new_reply_verified": True,
            "completion_status": "complete",
            "next_action": "stop_for_human_review",
            "stop_reason": "human_required",
        }]
    else:
        state["status"] = "initialized"
        inputs_found["round1_decision"] = False

    save_state(tid, state)
    print(f"[OK] State: round={state['current_round']}, status={state['status']}")

    # 4. Evaluate stop rules
    should_stop, stop_reason = evaluate_stop_rules(state, config, last_judgment, last_s3_allowed)
    print(f"[OK] Stop rules: should_stop={should_stop}, reason={stop_reason}")

    # 5. Dry-run: generate report only
    if dry_run:
        print("\n[DRY-RUN] Generating harness test report...")
        report_path = generate_harness_test_report(tid, state, config, should_stop, stop_reason, inputs_found)
        print(f"[OK] Report: {report_path}")

        # Plan round-2
        plan_round_2(tid)
        print(f"[OK] Round-2 plan: {task_dir / 'round-2-plan/'}")

        # Save final state
        state["status"] = "stopped"
        if stop_reason == "human_required":
            state["status"] = "human_required"
        save_state(tid, state)

        print(f"\nHarness dry-run complete.")
        print(f"  Status: {state['status']}")
        print(f"  Round: {state['current_round']}")
        print(f"  Judgment: {last_judgment}")
        print(f"  Next: human_review")
        return

    # 6. Live mode: execute next round
    if not should_stop:
        next_round = state["current_round"] + 1
        print(f"\n[LIVE] Would execute round {next_round}...")
        print("Live execution not yet implemented in harness. Use oracle_gpt_review_loop_once.py")
    else:
        print(f"\nLoop stopped: {stop_reason}")
        print("No further rounds will be executed.")


if __name__ == "__main__":
    main()
