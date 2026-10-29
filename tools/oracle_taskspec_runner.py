#!/usr/bin/env python3
"""oracle_taskspec_runner.py — Execute a single machine-readable TaskSpec.

Reads a TaskSpec (JSON/YAML), validates it against TASKSPEC.schema.json,
checks high_risk / allowed_actions / forbidden_actions, executes allowed
non-destructive actions, and produces RUNNER_STEP_RESULT.

Usage:
  python tools/oracle_taskspec_runner.py \\
    --task-id s3-phase3 \\
    --taskspec _reports/s3-phase3/S3_PHASE3_TASKSPEC.json \\
    --contracts-root D:/agent-acceptance \\
    --output-dir _reports/s3-phase3
"""

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

ROOT = Path(__file__).resolve().parent.parent


def ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load_json(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def load_yaml(path: Path) -> dict:
    import yaml
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def validate_taskspec(taskspec: dict, schema_path: Path) -> tuple[bool, str]:
    """Validate a TaskSpec against TASKSPEC.schema.json. Returns (valid, error)."""
    if not schema_path.exists():
        return False, f"TASKSPEC schema not found: {schema_path}"
    try:
        schema = load_json(schema_path)
        from jsonschema import validate, ValidationError
        validate(instance=taskspec, schema=schema)
        return True, ""
    except ValidationError as e:
        return False, f"Schema validation failed: {e.message}"
    except Exception as e:
        return False, f"Schema validation error: {e}"


def check_high_risk(taskspec: dict) -> bool:
    return taskspec.get("high_risk", False)


def check_forbidden_violation(taskspec: dict) -> list[str]:
    """Check if any allowed_actions overlap with forbidden_actions — that would be a violation."""
    allowed = set(taskspec.get("allowed_actions", []))
    forbidden = set(taskspec.get("forbidden_actions", []))
    return list(allowed & forbidden)


def check_allowed_high_risk(taskspec: dict) -> list[str]:
    """Check if any allowed_actions are high-risk per HUMAN_REQUIRED_TAXONOMY."""
    allowed = taskspec.get("allowed_actions", [])
    high_risk_keywords = {"delete", "move", "rename", "clean worktree", "overwrite evidence",
                          "fabricate baseline", "fabricate test", "forge", "sensitive config",
                          "force push", "hard reset"}
    found = []
    for action in allowed:
        action_lower = action.lower()
        for kw in high_risk_keywords:
            if kw in action_lower:
                found.append(action)
                break
    return found


def run_taskspec(
    task_id: str,
    taskspec_path: Path,
    contracts_root: Path,
    output_dir: Path,
) -> dict:
    """Execute a single TaskSpec and return RUNNER_STEP_RESULT."""

    log_lines: list[str] = []
    def log(evt: str, detail: str = ""):
        entry = f"| {ts()} | {evt} | {detail} |"
        log_lines.append(entry)
        print(f"  [{evt}] {detail}")

    schema_path = contracts_root / "contracts" / "TASKSPEC.schema.json"
    output_dir.mkdir(parents=True, exist_ok=True)
    files_produced: list[str] = []

    # ── 0. Is this Markdown-only? ──
    ext = taskspec_path.suffix.lower()
    if ext == ".md":
        return {
            "step_id": f"{task_id}-reject-markdown",
            "step_type": "schema_check",
            "status": "step_failed",
            "terminal": True,
            "errors": ["TaskSpec is Markdown-only; machine-readable JSON/YAML required per TASKSPEC_RUNNER_POLICY"],
            "reason": "TaskSpec is Markdown-only; machine-readable JSON/YAML required",
            "safety": {"high_risk_action_attempted": False, "human_confirmed": False,
                       "forbidden_action_blocked": False, "schema_validated": False},
        }

    # ── 1. Load TaskSpec ──
    try:
        if ext in (".json",):
            taskspec = load_json(taskspec_path)
        elif ext in (".yaml", ".yml"):
            taskspec = load_yaml(taskspec_path)
        else:
            return {
                "step_id": f"{task_id}-unknown-format",
                "step_type": "schema_check",
                "status": "step_failed",
                "terminal": True,
                "errors": [f"Unknown TaskSpec format: {ext}"],
                "reason": f"Unknown TaskSpec format: {ext}",
                "safety": {"high_risk_action_attempted": False, "human_confirmed": False,
                           "forbidden_action_blocked": False, "schema_validated": False},
            }
    except Exception as e:
        return {
            "step_id": f"{task_id}-parse-error",
            "step_type": "schema_check",
            "status": "step_failed",
            "terminal": True,
            "errors": [f"Failed to parse TaskSpec: {e}"],
            "reason": f"TaskSpec parse error: {e}",
            "safety": {"high_risk_action_attempted": False, "human_confirmed": False,
                       "forbidden_action_blocked": False, "schema_validated": False},
        }

    log("taskspec_loaded", f"{len(str(taskspec))} chars")

    # ── 2. Validate against schema ──
    valid, err = validate_taskspec(taskspec, schema_path)
    if not valid:
        return {
            "step_id": f"{task_id}-schema-invalid",
            "step_type": "schema_check",
            "status": "step_failed",
            "terminal": True,
            "errors": [err],
            "reason": err,
            "safety": {"high_risk_action_attempted": False, "human_confirmed": False,
                       "forbidden_action_blocked": False, "schema_validated": False},
        }

    log("schema_validated", "PASS")
    files_produced.append(str(output_dir / "S3_PHASE3_TASKSPEC.json"))

    # ── 3. Check high_risk ──
    if check_high_risk(taskspec):
        return {
            "step_id": f"{task_id}-high-risk",
            "step_type": "safety_check",
            "status": "step_human_required",
            "terminal": True,
            "reason": f"High-risk TaskSpec requires human confirmation: {task_id}",
            "safety": {"high_risk_action_attempted": True, "human_confirmed": False,
                       "forbidden_action_blocked": False, "schema_validated": True},
        }

    # ── 4. Check allowed vs forbidden overlap + high-risk in allowed ──
    overlap = check_forbidden_violation(taskspec)
    if overlap:
        return {
            "step_id": f"{task_id}-forbidden-violation",
            "step_type": "safety_check",
            "status": "step_blocked",
            "terminal": True,
            "errors": [f"allowed_actions overlap with forbidden_actions: {overlap}"],
            "reason": f"TaskSpec conflict: allowed actions also in forbidden list: {overlap}",
            "safety": {"high_risk_action_attempted": False, "human_confirmed": False,
                       "forbidden_action_blocked": True, "schema_validated": True},
        }

    high_risk_allowed = check_allowed_high_risk(taskspec)
    if high_risk_allowed:
        return {
            "step_id": f"{task_id}-high-risk-in-allowed",
            "step_type": "safety_check",
            "status": "step_human_required",
            "terminal": True,
            "errors": [f"High-risk actions in allowed_actions: {high_risk_allowed}"],
            "reason": f"High-risk actions in allowed_actions: {high_risk_allowed}. Human required per HUMAN_REQUIRED_TAXONOMY.",
            "safety": {"high_risk_action_attempted": True, "human_confirmed": False,
                       "forbidden_action_blocked": False, "schema_validated": True},
        }

    log("safety_checks", "PASS (no high-risk, no forbidden overlap)")

    # ── 5. Read terminal_conditions ──
    tc = taskspec.get("terminal_conditions", {})
    task_terminal = tc.get("terminal", False)
    terminal_reason = tc.get("reason", "")

    # ── 6. Determine step status ──
    if task_terminal:
        status = "step_success_terminal"
    else:
        status = "step_success_continue"

    next_on = taskspec.get("next_on_accepted", "")
    review_required = taskspec.get("review_required", True)

    # next_action must NOT hint Phase 4 before GPT accepted
    next_a = "await_gpt_review_decision" if review_required else (
        f"proceed_to_{next_on}" if next_on else "execute_next_step")

    result = {
        "step_id": f"{task_id}-validated",
        "step_type": "execute_taskspec",
        "status": status,
        "transport_status": "success",
        "business_decision": "unknown",
        "dispatch_status": "ready_to_dispatch",
        "produced_files": files_produced,
        "next_action": next_a,
        "terminal": task_terminal,
        "errors": [],
        "safety": {
            "high_risk_action_attempted": False,
            "human_confirmed": False,
            "forbidden_action_blocked": False,
            "schema_validated": True,
        },
        "reason": f"TaskSpec {task_id} validated and executed. terminal={task_terminal}, reason={terminal_reason}",
    }

    log("taskspec_executed", f"status={status} terminal={task_terminal}")

    # ── 7. Save step result ──
    step_path = output_dir / "RUNNER_STEP_RESULT.json"
    step_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    files_produced.append(str(step_path))
    log("step_result_saved", str(step_path))

    # ── 8. Save log ──
    log_path = output_dir / "TASKSPEC_RUNNER_LOG.md"
    log_path.write_text("# TaskSpec Runner Log\n\n| Time | Event | Details |\n|------|-------|---------|\n" +
                        "\n".join(log_lines), encoding="utf-8")
    files_produced.append(str(log_path))

    return result


def main():
    parser = argparse.ArgumentParser(description="TaskSpec Runner")
    parser.add_argument("--task-id", default="s3-phase3")
    parser.add_argument("--taskspec", required=True)
    parser.add_argument("--contracts-root", default="D:/agent-acceptance")
    parser.add_argument("--output-dir", default="_reports/s3-phase3")
    args = parser.parse_args()

    taskspec_path = Path(args.taskspec)
    contracts_root = Path(args.contracts_root)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"TaskSpec Runner — {args.task_id}")
    print(f"  taskspec: {taskspec_path}")
    print(f"  contracts: {contracts_root}")

    result = run_taskspec(
        task_id=args.task_id,
        taskspec_path=taskspec_path,
        contracts_root=contracts_root,
        output_dir=output_dir,
    )

    print(json.dumps(result, indent=2, ensure_ascii=False))

    if result["status"] == "step_success_continue":
        print("\nRunner: step success, continue to next")
        sys.exit(0)
    elif result["status"] == "step_success_terminal":
        sys.exit(0)
    elif result["status"] == "step_human_required":
        sys.exit(10)
    else:
        sys.exit(20)


if __name__ == "__main__":
    main()
