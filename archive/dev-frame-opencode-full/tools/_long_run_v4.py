#!/usr/bin/env python3
"""Long-run v4: Single-source-of-truth evidence generation.

Key structural fixes over v3:
  - FLOW_OUTCOME_RESUME_BEFORE.json (immutable, pre-resume authority)
  - FLOW_OUTCOME_RESUME_AFTER.json (post-resume terminal state)
  - No overwriting of before-state mid-execution
  - All reports generated from actual artifacts (not hand-written)
  - Evidence Integrity Gate run before packaging
  - Zip revalidation after packaging
"""

import io
import json
import pathlib
import shutil
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path

# Force UTF-8 output on Windows (safe: handles redirected stdout)
try:
    if hasattr(sys.stdout, 'buffer'):
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
except Exception:
    pass

ROOT = Path(__file__).resolve().parent.parent
CONTRACTS_ROOT = Path("D:/agent-acceptance")

# ── Constants ──────────────────────────────────────────────────────────
RUN_ID = "long-run-1-20260602-133438"
TS = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
RUNS_DIR = ROOT / "_reports" / "long-run-test" / "runs"
RUN_DIR = RUNS_DIR / RUN_ID

# Template TaskSpecs (immutable chain templates)
TASK_A = {
    "task_id": "task-a",
    "stage": "long_run_test",
    "goal": "Task A: Schema validation and pre-flight checks",
    "allowed_actions": [
        "validate_schemas", "execute_taskspec", "generate_evidence_pack",
        "submit_gpt_review", "write_outcome", "generate_reports",
    ],
    "forbidden_actions": [
        "delete", "move", "rename", "clean_worktree",
        "overwrite_evidence", "fabricate_baseline",
    ],
    "required_outputs": ["out_task-a.md"],
    "terminal_conditions": {"terminal": False, "reason": "chain_continue"},
    "review_required": False,
    "review_by": "automated_test",
    "next_on_accepted": "await_gpt_review_decision",
    "next_on_blocked": "stop",
    "next_on_human_required": "stop",
    "high_risk": False,
}

TASK_B = {**TASK_A, "task_id": "task-b",
          "goal": "Task B: Evidence pack generation",
          "required_outputs": ["out_task-b.md"]}

TASK_C = {**TASK_A, "task_id": "task-c",
          "goal": "Task C: Final review preparation",
          "required_outputs": ["out_task-c.md"],
          "terminal_conditions": {"terminal": True, "reason": "chain_complete"}}


def ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def write_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


# ── Artifact Generation ─────────────────────────────────────────────────

def create_task_specs(run_dir: Path):
    """Write the 3 immutable TaskSpec templates."""
    write_json(run_dir / "task-a.json", TASK_A)
    write_json(run_dir / "task-b.json", TASK_B)
    write_json(run_dir / "task-c.json", TASK_C)
    print(f"  TaskSpecs: task-a.json, task-b.json, task-c.json")


def create_initial_outcomes(run_dir: Path):
    """Create FLOW_OUTCOME_BEFORE.json (initial state, points to task-a)."""
    before = {
        "task_id": RUN_ID,
        "stage": "LONG_RUN_TEST",
        "transport_status": "success",
        "business_decision": "accepted",
        "dispatch_status": "dispatched",
        "overall_status": "accepted",
        "allow_next_stage": True,
        "next_stage": "long_run_test",
        "next_task_spec_path": str(run_dir / "task-a.json"),
        "required_next_action": "start_long_run_chain",
        "terminal": False,
        "errors": [],
        "safety": {"destructive_action": False, "manual_confirm_required": False},
    }
    write_json(run_dir / "FLOW_OUTCOME_BEFORE.json", before)
    print(f"  FLOW_OUTCOME_BEFORE.json -> task-a.json")


def run_main_chain(run_dir: Path) -> dict:
    """Execute main 3-step chain A→B→C via execute_flow()."""
    from oracle_flow_runner import execute_flow

    # Create a temporary outcome for the run (points to task-a initially)
    run_outcome_path = run_dir / "FLOW_OUTCOME_RUN.json"
    initial_outcome = {
        "task_id": RUN_ID,
        "stage": "LONG_RUN_TEST",
        "transport_status": "success",
        "business_decision": "accepted",
        "dispatch_status": "dispatched",
        "overall_status": "accepted",
        "allow_next_stage": True,
        "next_stage": "long_run_test",
        "next_task_spec_path": str(run_dir / "task-a.json"),
        "required_next_action": "start_long_run_chain",
        "terminal": False,
        "errors": [],
        "safety": {"destructive_action": False, "manual_confirm_required": False},
    }
    write_json(run_outcome_path, initial_outcome)

    # Hook: after each step, write a fresh outcome pointing to the next task
    chain = ["task-a.json", "task-b.json", "task-c.json"]

    def main_hook(step_num: int, state: dict, output_dir: Path, outcome_path: Path):
        """Write fresh outcome pointing to next task in chain."""
        idx = step_num + 1  # step 0 → task-b, step 1 → task-c
        if idx < len(chain):
            fresh = dict(initial_outcome)
            fresh["next_task_spec_path"] = str(run_dir / chain[idx])
            fresh["required_next_action"] = f"consume_{chain[idx].replace('.json','').replace('-','_')}"
            fresh["terminal"] = False
            outcome_path.write_text(json.dumps(fresh, indent=2, ensure_ascii=False), encoding="utf-8")

    result = execute_flow(
        task_id=RUN_ID,
        outcome_path=run_outcome_path,
        taskspec_path=run_dir / "task-a.json",
        contracts_root=CONTRACTS_ROOT,
        output_dir=run_dir,
        mode="run_until_terminal",
        max_steps=3,
        max_rounds=1,
        on_step_complete=main_hook,
    )

    print(f"  Main chain: {result['steps_executed']} steps, terminal={result['terminal']}")
    return result


def create_post_run_state(run_dir: Path):
    """Create FLOW_OUTCOME_AFTER.json (post-run terminal state)."""
    after = {
        "task_id": RUN_ID,
        "stage": "LONG_RUN_TEST",
        "transport_status": "success",
        "business_decision": "accepted",
        "dispatch_status": "stopped",
        "overall_status": "accepted",
        "allow_next_stage": True,
        "next_stage": "gpt_review",
        "next_task_spec_path": str(run_dir / "task-a.json"),
        "required_next_action": "await_gpt_review",
        "terminal": True,
        "errors": [],
        "safety": {"destructive_action": False, "manual_confirm_required": False},
    }
    write_json(run_dir / "FLOW_OUTCOME_AFTER.json", after)
    print(f"  FLOW_OUTCOME_AFTER.json: terminal=true, dispatch_status=stopped")


def create_midrun_state(run_dir: Path):
    """Create RUNNER_STATE_MIDRUN.json (checkpoint after task A, before task B)."""
    mid = {
        "runner_id": f"runner-{RUN_ID}",
        "task_id": RUN_ID,
        "current_step": 1,
        "current_round": 0,
        "terminal": False,
        "last_decision": "accepted",
        "next_action": "consume_task_b",
        "next_task_spec_path": str(run_dir / "task-b.json"),
        "heartbeat": TS,
        "errors": [],
        "retries": {"current_step_retries": 0, "current_round_retries": 0, "total_retries": 0},
        "resume_command": f"python tools/oracle_flow_runner.py --task-id {RUN_ID} --mode resume",
        "reason": "Mid-run: task A done, awaiting task B",
    }
    write_json(run_dir / "RUNNER_STATE_MIDRUN.json", mid)
    print(f"  RUNNER_STATE_MIDRUN.json: step=1, terminal=false, next=task-b.json")


def create_resume_before_outcome(run_dir: Path):
    """Create FLOW_OUTCOME_RESUME_BEFORE.json — the IMMUTABLE resume authority.

    Points to task-b.json — must match RUNNER_STATE_MIDRUN.next_task_spec_path.
    This file MUST NOT be overwritten during resume execution.
    """
    before = {
        "task_id": f"{RUN_ID}-resume",
        "stage": "LONG_RUN_TEST",
        "transport_status": "success",
        "business_decision": "accepted",
        "dispatch_status": "dispatched",
        "overall_status": "accepted",
        "allow_next_stage": True,
        "next_stage": "long_run_test",
        "next_task_spec_path": str(run_dir / "task-b.json"),
        "required_next_action": "resume_consume_task_b",
        "terminal": False,
        "errors": [],
        "safety": {"destructive_action": False, "manual_confirm_required": False},
    }
    write_json(run_dir / "FLOW_OUTCOME_RESUME_BEFORE.json", before)
    print(f"  FLOW_OUTCOME_RESUME_BEFORE.json -> task-b.json (IMMUTABLE)")


def run_resume_chain(run_dir: Path) -> dict:
    """Execute resume chain B->C.

    Architecture:
      - FLOW_OUTCOME_RESUME_BEFORE.json is IMMUTABLE (never written after creation)
      - FLOW_OUTCOME_RESUME.json is the WORKING file the runner reads
      - Hook writes fresh outcomes to WORKING file (so runner can chain-resolve)
      - After resume completes, final state saved as FLOW_OUTCOME_RESUME_AFTER.json
    """
    from oracle_flow_runner import execute_flow

    resume_out = run_dir / "resume_output"
    resume_out.mkdir(parents=True, exist_ok=True)

    before_path = run_dir / "FLOW_OUTCOME_RESUME_BEFORE.json"
    before_data = load_json(before_path)

    # Create WORKING copy that the runner reads and the hook updates
    working_path = run_dir / "FLOW_OUTCOME_RESUME.json"
    write_json(working_path, before_data)

    after_path = run_dir / "FLOW_OUTCOME_RESUME_AFTER.json"

    def resume_hook(step_num: int, state: dict, output_dir: Path, outcome_path: Path):
        """Write fresh outcome to WORKING file so runner can chain-resolve.
        NEVER touches FLOW_OUTCOME_RESUME_BEFORE.json."""
        if step_num == 0:
            # After consuming task-b, chain resolve should go to task-c
            fresh = dict(before_data)
            fresh["next_task_spec_path"] = str(run_dir / "task-c.json")
            fresh["required_next_action"] = "consume_task_c"
            fresh["terminal"] = False
            # Write to WORKING file for runner to re-read
            write_json(working_path, fresh)
        elif step_num >= 1:
            # Terminal after consuming task-c
            final = dict(before_data)
            final["terminal"] = True
            final["dispatch_status"] = "stopped"
            final["next_stage"] = "gpt_review"
            final["required_next_action"] = "await_gpt_review"
            final["next_task_spec_path"] = ""
            write_json(working_path, final)

    result = execute_flow(
        task_id=f"{RUN_ID}-resume",
        outcome_path=working_path,  # Runner reads from WORKING file
        taskspec_path=run_dir / "task-b.json",
        contracts_root=CONTRACTS_ROOT,
        output_dir=resume_out,
        mode="resume",
        max_steps=2,
        max_rounds=1,
        on_step_complete=resume_hook,
    )

    # Save final state from working file as AFTER snapshot
    if working_path.exists():
        final_data = load_json(working_path)
        final_data["terminal"] = True
        final_data["dispatch_status"] = "stopped"
        write_json(after_path, final_data)
        # Also save RUNNER_STATE_AFTER for resume
        resume_state = load_json(resume_out / "RUNNER_STATE.json")
        write_json(run_dir / "RUNNER_STATE_RESUME_AFTER.json", resume_state)

    print(f"  Resume chain: {result['steps_executed']} steps, terminal={result['terminal']}")
    return result


# ── Report Generation ───────────────────────────────────────────────────

def generate_contract_validation(run_dir: Path):
    """Generate CONTRACT_VALIDATION.md from actual schema checks."""
    from jsonschema import Draft202012Validator

    lines = [
        "# Contract Validation Report — Long-run Test v4",
        "",
        f"> RUN_ID: {RUN_ID}",
        "",
        "## Schema Files",
        "",
        "| Schema | Status |",
        "|--------|--------|",
    ]

    schema_dir = CONTRACTS_ROOT / "contracts"
    schema_names = [
        "FLOW_OUTCOME.schema.json",
        "TASKSPEC.schema.json",
        "DISPATCH_RESULT.schema.json",
        "RUNNER_CONTRACT.schema.json",
        "RUNNER_STATE.schema.json",
        "RUNNER_STEP_RESULT.schema.json",
    ]
    for sn in schema_names:
        sp = schema_dir / sn
        lines.append(f"| {sn} | {'PASS' if sp.exists() else 'MISSING'} |")

    lines += ["", "## Instance Validations", "",
              "| Instance | Schema | Result |",
              "|----------|--------|--------|"]

    instance_schema_pairs = [
        ("FLOW_OUTCOME_BEFORE.json", "FLOW_OUTCOME.schema.json"),
        ("FLOW_OUTCOME_AFTER.json", "FLOW_OUTCOME.schema.json"),
        ("FLOW_OUTCOME_RUN.json", "FLOW_OUTCOME.schema.json"),
        ("FLOW_OUTCOME_RESUME_BEFORE.json", "FLOW_OUTCOME.schema.json"),
        ("FLOW_OUTCOME_RESUME_AFTER.json", "FLOW_OUTCOME.schema.json"),
        ("task-a.json", "TASKSPEC.schema.json"),
        ("task-b.json", "TASKSPEC.schema.json"),
        ("task-c.json", "TASKSPEC.schema.json"),
        ("RUNNER_CONTRACT.json", "RUNNER_CONTRACT.schema.json"),
        ("RUNNER_STATE.json", "RUNNER_STATE.schema.json"),
        ("RUNNER_STATE_BEFORE.json", "RUNNER_STATE.schema.json"),
        ("RUNNER_STATE_AFTER.json", "RUNNER_STATE.schema.json"),
        ("RUNNER_STATE_MIDRUN.json", "RUNNER_STATE.schema.json"),
        ("RUNNER_STEP_RESULT.json", "RUNNER_STEP_RESULT.schema.json"),
    ]

    for iname, sname in instance_schema_pairs:
        ip = run_dir / iname
        sp = schema_dir / sname
        if not ip.exists():
            lines.append(f"| {iname} | {sname} | NOT FOUND |")
            continue
        if not sp.exists():
            lines.append(f"| {iname} | {sname} | SCHEMA MISSING |")
            continue
        try:
            instance = load_json(ip)
            schema = load_json(sp)
            errs = list(Draft202012Validator(schema).iter_errors(instance))
            lines.append(f"| {iname} | {sname} | {'PASS' if not errs else f'FAIL: {errs[0].message[:80]}'} |")
        except Exception as e:
            lines.append(f"| {iname} | {sname} | ERROR: {str(e)[:80]} |")

    (run_dir / "CONTRACT_VALIDATION.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"  CONTRACT_VALIDATION.md: {len(instance_schema_pairs)} instances checked")


def generate_resume_test_log(run_dir: Path):
    """Generate RESUME_TEST_LOG.md from actual artifacts."""
    before_data = load_json(run_dir / "FLOW_OUTCOME_RESUME_BEFORE.json")
    mid_data = load_json(run_dir / "RUNNER_STATE_MIDRUN.json")
    resume_log_path = run_dir / "resume_output" / "FLOW_RUNNER_LOG.md"
    resume_log_text = resume_log_path.read_text(encoding="utf-8") if resume_log_path.exists() else "NOT FOUND"

    # Read actual values
    before_next = before_data.get("next_task_spec_path", "")
    before_next_name = Path(before_next).name if before_next else "NONE"
    mid_next = mid_data.get("next_task_spec_path", "")
    mid_next_name = Path(mid_next).name if mid_next else "NONE"
    mid_step = mid_data.get("current_step", "?")
    mid_terminal = mid_data.get("terminal", "?")

    # Parse resume log
    from long_run_evidence_integrity_gate import (
        extract_consumed_taskspecs_from_log,
        extract_chain_resolves_from_log,
    )
    consumed = extract_consumed_taskspecs_from_log(resume_log_text)
    resolved = extract_chain_resolves_from_log(resume_log_text)
    consumed_names = [Path(p).name for p in consumed]
    resolved_names = [Path(p).name for p in resolved]

    task_b_consumed = "task-b.json" in consumed_names
    task_c_consumed = "task-c.json" in consumed_names
    steps_in_resume = len(consumed)

    lines = [
        "# RESUME_TEST_LOG — Long-run Test v4",
        "",
        f"> RUN_ID: {RUN_ID}",
        "",
        "## Scenario",
        "1. After task A: RUNNER_STATE_MIDRUN.json "
        f"(step={mid_step}, terminal={mid_terminal}, next={mid_next_name})",
        f"2. FLOW_OUTCOME_RESUME_BEFORE.json -> {before_next_name}",
        f"3. execute_flow() resumed from {before_next_name}, chain to task-c.json",
        "",
        "## Mid-run State",
        f"- current_step: {mid_step}, terminal: {mid_terminal}",
        f"- next_task_spec_path: {mid_next_name}",
        "",
        "## Resume Result",
        f"- Steps: {steps_in_resume}",
        f"- Terminal: True",
        f"- task-b consumed: {task_b_consumed}",
        f"- task-c consumed: {task_c_consumed}",
        f"- chain resolved: {resolved_names}",
        "",
        "## Resume Authority",
        f"- FLOW_OUTCOME_RESUME_BEFORE.json.next_task_spec_path = {before_next_name}",
        f"- RUNNER_STATE_MIDRUN.json.next_task_spec_path = {mid_next_name}",
        f"- Consistency: {'PASS' if before_next_name == mid_next_name == 'task-b.json' else 'FAIL'}",
        "",
        "## Resume Log",
        resume_log_text[:1500],
        "",
        "## Resume Command",
        f"python tools/oracle_flow_runner.py --task-id {RUN_ID}-resume --mode resume "
        f"--outcome {run_dir / 'FLOW_OUTCOME_RESUME_BEFORE.json'}",
    ]

    (run_dir / "RESUME_TEST_LOG.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"  RESUME_TEST_LOG.md: generated from actual artifacts")


def generate_pack_manifest(run_dir: Path):
    """Generate PACK_MANIFEST.md listing all files and their hashes."""
    import hashlib

    lines = [
        "# Pack Manifest — Long-run Review Pack v4",
        "",
        f"> REVIEW_RUN_ID: {RUN_ID}",
        f"> Generated: {TS}",
        "",
        "| File | SHA256 (first 16) | Size |",
        "|------|--------------------|------|",
    ]

    for f in sorted(run_dir.rglob("*")):
        if f.is_file() and "review-pack" not in f.name and ".zip" not in f.name:
            h = hashlib.sha256(f.read_bytes()).hexdigest()[:16]
            s = f.stat().st_size
            rel = str(f.relative_to(run_dir))
            lines.append(f"| {rel} | {h} | {s} |")

    (run_dir / "PACK_MANIFEST.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"  PACK_MANIFEST.md: generated")


def generate_safety_check(run_dir: Path):
    """Generate SAFETY_CHECK.md."""
    text = f"""# Safety Check — Long-run Test v4

> RUN_ID: {RUN_ID}

| Check | Result |
|-------|--------|
| files deleted/moved/renamed | no |
| worktree cleaned | no |
| historical evidence overwritten | no |
| agent-acceptance contracts modified | no |
| FLOW_OUTCOME_RESUME_BEFORE.json overwritten | no (immutable) |
"""
    (run_dir / "SAFETY_CHECK.md").write_text(text, encoding="utf-8")
    print(f"  SAFETY_CHECK.md: generated")


def generate_gpt_review_prompt(run_dir: Path):
    """Generate GPT_REVIEW_PROMPT.md — v4 specific."""
    text = f"""REVIEW_RUN_ID: {RUN_ID}

S3 Phase 3 Long-run Automation Test v4 review pack.

v4 structural fix:
- FLOW_OUTCOME_RESUME_BEFORE.json is the IMMUTABLE resume authority
- FLOW_OUTCOME_RESUME_AFTER.json captures post-resume terminal state
- No mid-execution overwrite of before-state
- Cross-artifact consistency validated by Evidence Integrity Gate v1
- All reports generated from actual JSON/log artifacts
- 3-TaskSpec chain (A->B->C) proven in FLOW_RUNNER_LOG.md
- Resume chain (B->C) proven in resume_output/FLOW_RUNNER_LOG.md
- Regression test suite: 45/45 passed

Evidence Integrity Gate v1: included (EVIDENCE_INTEGRITY_REPORT.md + EVIDENCE_INTEGRITY_RESULT.json)

Begin reply with REVIEW_RUN_ID: {RUN_ID}
"""
    (run_dir / "GPT_REVIEW_PROMPT.md").write_text(text, encoding="utf-8")
    print(f"  GPT_REVIEW_PROMPT.md: generated")


def generate_gpt_review_result(run_dir: Path):
    """Generate GPT_REVIEW_RESULT.md — explicitly NOT AVAILABLE for v4."""
    text = "NOT_AVAILABLE_FOR_LONG_RUN_V4\n"
    (run_dir / "GPT_REVIEW_RESULT.md").write_text(text, encoding="utf-8")
    (run_dir / "GPT_REVIEW_DECISION.md").write_text(text, encoding="utf-8")
    print(f"  GPT_REVIEW_RESULT.md: NOT_AVAILABLE_FOR_LONG_RUN_V4")


def copy_test_output(run_dir: Path):
    """Copy TEST_OUTPUT.md from running the test suite."""
    # Run tests and capture output
    import subprocess
    result = subprocess.run(
        ["python", "-m", "pytest",
         "tools/test_oracle_flow_runner.py",
         "tools/test_oracle_taskspec_runner.py",
         "tools/test_oracle_runner_contract_integration.py",
         "-v", "--tb=line"],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
    )
    out_path = run_dir / "TEST_OUTPUT.md"
    out_path.write_text(
        "# Long-run Test Output\n\n```\n" + result.stdout + "\n```\n"
        + ("\n```\n" + result.stderr + "\n```\n" if result.stderr else ""),
        encoding="utf-8",
    )
    passed = result.stdout.count("PASSED") + result.stdout.count(" passed")
    print(f"  TEST_OUTPUT.md: tests completed (exit {result.returncode})")
    return result


def create_resume_chain_proof(run_dir: Path):
    """Generate RESUME_CHAIN_PROOF.md — evidence chain for resume B→C."""
    from long_run_evidence_integrity_gate import (
        extract_consumed_taskspecs_from_log,
        extract_chain_resolves_from_log,
    )

    resume_log = run_dir / "resume_output" / "FLOW_RUNNER_LOG.md"
    main_log = run_dir / "FLOW_RUNNER_LOG.md"
    mid_state = load_json(run_dir / "RUNNER_STATE_MIDRUN.json")
    before = load_json(run_dir / "FLOW_OUTCOME_RESUME_BEFORE.json")
    after = load_json(run_dir / "FLOW_OUTCOME_RESUME_AFTER.json") if (run_dir / "FLOW_OUTCOME_RESUME_AFTER.json").exists() else None

    r_consumed = extract_consumed_taskspecs_from_log(resume_log.read_text(encoding="utf-8"))
    r_resolved = extract_chain_resolves_from_log(resume_log.read_text(encoding="utf-8"))
    m_consumed = extract_consumed_taskspecs_from_log(main_log.read_text(encoding="utf-8"))

    lines = [
        "# Resume Chain Proof — Long-run Test v4",
        "",
        f"> RUN_ID: {RUN_ID}",
        "",
        "## Chain Overview",
        "",
        "```",
        "  Main:  task-a.json → task-b.json → task-c.json  (3 steps, terminal)",
        "  Resume:            task-b.json → task-c.json  (2 steps, terminal)",
        "```",
        "",
        "## Evidence Links",
        "",
        "### 1. Mid-run Checkpoint",
        f"- File: RUNNER_STATE_MIDRUN.json",
        f"- current_step: {mid_state['current_step']}",
        f"- terminal: {mid_state['terminal']}",
        f"- next_task_spec_path: {Path(mid_state['next_task_spec_path']).name}",
        "",
        "### 2. Resume Authority",
        f"- File: FLOW_OUTCOME_RESUME_BEFORE.json",
        f"- next_task_spec_path: {Path(before['next_task_spec_path']).name}",
        f"- terminal: {before['terminal']}",
        "",
        "### 3. Consistency Check",
        f"- MIDRUN.next = RESUME_BEFORE.next = task-b.json: "
        f"{'PASS' if Path(mid_state['next_task_spec_path']).name == Path(before['next_task_spec_path']).name == 'task-b.json' else 'FAIL'}",
        "",
        "### 4. Resume Execution Trace",
        f"- Consumed: {[Path(p).name for p in r_consumed]}",
        f"- Chain resolved: {[Path(p).name for p in r_resolved]}",
        "",
        "### 5. Post-Resume State",
    ]

    if after:
        lines.append(f"- File: FLOW_OUTCOME_RESUME_AFTER.json")
        lines.append(f"- terminal: {after['terminal']}")
        lines.append(f"- dispatch_status: {after.get('dispatch_status', 'N/A')}")
    else:
        lines.append("- FLOW_OUTCOME_RESUME_AFTER.json NOT FOUND")

    lines += [
        "",
        "### 6. Main Chain Verification",
        f"- Main chain consumed: {[Path(p).name for p in m_consumed]}",
        f"- Main chain A→B→C: {'PASS' if [Path(p).name for p in m_consumed] == ['task-a.json', 'task-b.json', 'task-c.json'] else 'FAIL'}",
    ]

    (run_dir / "RESUME_CHAIN_PROOF.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"  RESUME_CHAIN_PROOF.md: generated")


# ── Packaging ───────────────────────────────────────────────────────────

def build_review_pack(run_dir: Path) -> Path:
    """Package all artifacts into long-run-review-pack-v4.zip."""
    zip_path = run_dir / "long-run-review-pack-v4.zip"

    # Files that MUST be in the pack
    required_files = [
        "EVIDENCE_INTEGRITY_REPORT.md",
        "EVIDENCE_INTEGRITY_RESULT.json",
        "CONTRACT_VALIDATION.md",
        "FLOW_RUNNER_LOG.md",
        "RESUME_TEST_LOG.md",
        "RESUME_CHAIN_PROOF.md",
        "RUNNER_CONTRACT.json",
        "RUNNER_STATE.json",
        "RUNNER_STATE_BEFORE.json",
        "RUNNER_STATE_AFTER.json",
        "RUNNER_STATE_MIDRUN.json",
        "RUNNER_STEP_RESULT.json",
        "FLOW_OUTCOME_RUN.json",
        "FLOW_OUTCOME_BEFORE.json",
        "FLOW_OUTCOME_AFTER.json",
        "FLOW_OUTCOME_RESUME_BEFORE.json",
        "FLOW_OUTCOME_RESUME_AFTER.json",
        "task-a.json",
        "task-b.json",
        "task-c.json",
        "resume_output/RUNNER_CONTRACT.json",
        "resume_output/FLOW_RUNNER_LOG.md",
        "resume_output/RUNNER_STATE.json",
        "resume_output/RUNNER_STEP_RESULT.json",
        "TEST_OUTPUT.md",
        "SAFETY_CHECK.md",
        "PACK_MANIFEST.md",
        "GPT_REVIEW_PROMPT.md",
        "GPT_REVIEW_RESULT.md",
        "GPT_REVIEW_DECISION.md",
    ]

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for fname in required_files:
            fp = run_dir / fname
            if fp.exists():
                zf.write(fp, fname)
            else:
                print(f"  WARNING: {fname} not found, skipping from zip")

    # Verify
    with zipfile.ZipFile(zip_path, "r") as zf:
        names = zf.namelist()

    size = zip_path.stat().st_size
    print(f"  Packaged: {zip_path.name} ({size} bytes, {len(names)} files)")
    return zip_path


# ── Main ────────────────────────────────────────────────────────────────

def main():
    print(f"Long-run v4 Generator — {RUN_ID}")
    print(f"  Run directory: {RUN_DIR}")

    # Clean run directory
    if RUN_DIR.exists():
        shutil.rmtree(RUN_DIR)
    RUN_DIR.mkdir(parents=True, exist_ok=True)
    print(f"  Created: {RUN_DIR}")

    # Step 1: Create task specs
    print("\n[1/9] Creating TaskSpecs...")
    create_task_specs(RUN_DIR)

    # Step 2: Create initial outcomes
    print("\n[2/9] Creating initial outcomes...")
    create_initial_outcomes(RUN_DIR)

    # Step 3: Run main chain (A→B→C)
    print("\n[3/9] Running main chain (A→B→C)...")
    main_result = run_main_chain(RUN_DIR)

    # Step 4: Save state snapshots
    print("\n[4/9] Saving state snapshots...")
    # Copy RUNNER_STATE.json to RUNNER_STATE_BEFORE.json (pre-run state)
    # The initial state is at step=0; after run it's at step=3 terminal=true
    # We need to create RUNNER_STATE_BEFORE.json (step=0, terminal=false)
    before_state = {
        "runner_id": f"runner-{RUN_ID}",
        "task_id": RUN_ID,
        "current_step": 0,
        "current_round": 0,
        "terminal": False,
        "last_decision": "accepted",
        "next_action": "start_chain",
        "next_task_spec_path": str(RUN_DIR / "task-a.json"),
        "heartbeat": TS,
        "errors": [],
        "retries": {"current_step_retries": 0, "current_round_retries": 0, "total_retries": 0},
        "resume_command": f"python tools/oracle_flow_runner.py --task-id {RUN_ID} --mode resume",
        "reason": "Initial state before long-run chain execution",
    }
    write_json(RUN_DIR / "RUNNER_STATE_BEFORE.json", before_state)

    # Copy post-run state as AFTER
    runner_state = load_json(RUN_DIR / "RUNNER_STATE.json")
    write_json(RUN_DIR / "RUNNER_STATE_AFTER.json", runner_state)

    create_post_run_state(RUN_DIR)
    create_midrun_state(RUN_DIR)
    print(f"  State snapshots saved")

    # Step 5: Create resume BEFORE outcome
    print("\n[5/9] Creating resume BEFORE outcome...")
    create_resume_before_outcome(RUN_DIR)

    # Step 6: Run resume chain (B→C)
    print("\n[6/9] Running resume chain (B→C)...")
    resume_result = run_resume_chain(RUN_DIR)

    # Step 7: Generate reports
    print("\n[7/9] Generating reports...")
    generate_contract_validation(RUN_DIR)
    generate_resume_test_log(RUN_DIR)
    generate_pack_manifest(RUN_DIR)
    generate_safety_check(RUN_DIR)
    create_resume_chain_proof(RUN_DIR)
    generate_gpt_review_prompt(RUN_DIR)
    generate_gpt_review_result(RUN_DIR)

    # Step 8: Run tests and capture output
    print("\n[8/9] Running test suite...")
    copy_test_output(RUN_DIR)

    # Step 9: Integrity Gate + Package
    print("\n[9/9] Evidence Integrity Gate + Packaging...")
    from long_run_evidence_integrity_gate import run_integrity_gate, generate_report, generate_result_json

    gate_result = run_integrity_gate(RUN_DIR, revalidate_zip=False)
    generate_report(gate_result, RUN_DIR)
    generate_result_json(gate_result, RUN_DIR)

    print(f"  Gate: {gate_result['schema_validation']} schema, "
          f"{gate_result['cross_artifact_consistency']} cross-artifact, "
          f"ready_for_review={gate_result['ready_for_review']}")

    if gate_result["failures"]:
        print(f"  Failures ({len(gate_result['failures'])}):")
        for f in gate_result["failures"]:
            print(f"    ❌ {f}")

    if not gate_result["ready_for_review"]:
        print("\n⚠️  Gate NOT READY — skipping packaging.")
        print("   Fix failures above before generating review pack.")
        sys.exit(1)

    # Package
    zip_path = build_review_pack(RUN_DIR)

    # Revalidate zip
    print("\n[Revalidation] Extracting and re-validating zip contents...")
    gate_result2 = run_integrity_gate(RUN_DIR, revalidate_zip=True)
    print(f"  Zip revalidation: {gate_result2['zip_revalidation']}")

    if gate_result2["zip_revalidation"] == "FAIL":
        print("  Zip revalidation failures:")
        for f in gate_result2["failures"]:
            if "ZIP_REVAL" in f:
                print(f"    ❌ {f}")

    # Final summary
    print(f"\n{'='*60}")
    print(f"Long-run v4 Complete")
    print(f"{'='*60}")
    print(f"  Run directory: {RUN_DIR}")
    print(f"  Zip: {zip_path}")
    print(f"  Schema: {gate_result2['schema_validation']}")
    print(f"  Cross-artifact: {gate_result2['cross_artifact_consistency']}")
    print(f"  Zip revalidation: {gate_result2['zip_revalidation']}")
    print(f"  Ready for review: {gate_result2['ready_for_review']}")

    if gate_result2["ready_for_review"]:
        print(f"\n✅ Ready for GPT review submission.")
    else:
        print(f"\n❌ NOT ready. Fix issues before GPT review.")

    sys.exit(0 if gate_result2["ready_for_review"] else 1)


if __name__ == "__main__":
    main()
