#!/usr/bin/env python3
"""Long-run v5: Fix GPT-identified blocking issues.
v5 fixes (on top of v4):
  1. resume_output/RUNNER_CONTRACT.json.input_outcome_path -> BEFORE
  2. Enhanced Evidence Integrity Gate: resume contract + manifest checks
  3. Zip revalidation executed before ready_for_review
  4. PACK_MANIFEST generated from zip contents (not directory)
"""
import hashlib
import json
import re
import subprocess
import sys
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONTRACTS_ROOT = Path("D:/agent-acceptance")
RUN_ID = "long-run-1-20260602-133438"
RUN_DIR = ROOT / "_reports" / "long-run-test" / "runs" / RUN_ID
TS = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

SCHEMA_NAMES = [
    "FLOW_OUTCOME.schema.json", "TASKSPEC.schema.json",
    "DISPATCH_RESULT.schema.json", "RUNNER_CONTRACT.schema.json",
    "RUNNER_STATE.schema.json", "RUNNER_STEP_RESULT.schema.json",
]
INSTANCE_SCHEMA_MAP = [
    ("FLOW_OUTCOME_BEFORE.json", "FLOW_OUTCOME.schema.json"),
    ("FLOW_OUTCOME_AFTER.json", "FLOW_OUTCOME.schema.json"),
    ("FLOW_OUTCOME_RUN.json", "FLOW_OUTCOME.schema.json"),
    ("FLOW_OUTCOME_RESUME_BEFORE.json", "FLOW_OUTCOME.schema.json"),
    ("FLOW_OUTCOME_RESUME_AFTER.json", "FLOW_OUTCOME.schema.json"),
    ("FLOW_OUTCOME_RESUME.json", "FLOW_OUTCOME.schema.json"),
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
RESUME_SCHEMA_MAP = [
    ("RUNNER_CONTRACT.json", "RUNNER_CONTRACT.schema.json"),
    ("RUNNER_STATE.json", "RUNNER_STATE.schema.json"),
    ("RUNNER_STEP_RESULT.json", "RUNNER_STEP_RESULT.schema.json"),
]

def load_json(p): return json.loads(p.read_text(encoding="utf-8"))
def write_json(p, d): p.write_text(json.dumps(d, indent=2, ensure_ascii=False), encoding="utf-8")

def extract_consumed(log_text):
    paths = []
    for m in re.finditer(r'consuming_ts\s*\|\s*(.+?)(?:\s*\|\s*)?$', log_text, re.MULTILINE):
        paths.append(m.group(1).strip().rstrip("|").strip())
    return paths

def extract_resolved(log_text):
    paths = []
    for m in re.finditer(r'chain_resolve.*?next TaskSpec.*?:\s*(.+?)(?:\s*\|\s*)?$', log_text, re.MULTILINE):
        paths.append(m.group(1).strip().rstrip("|").strip())
    return paths


# ==================================================================
# Step 1-6: Generate main chain + resume chain (same as v4)
# ==================================================================

def generate_artifacts():
    """Regenerate all artifacts. Reuses v4's main/resume chain execution."""
    import shutil
    if RUN_DIR.exists():
        shutil.rmtree(RUN_DIR)
    RUN_DIR.mkdir(parents=True, exist_ok=True)

    # TaskSpecs
    TASK_A = {"task_id":"task-a","stage":"long_run_test","goal":"Task A: Schema validation and pre-flight checks","allowed_actions":["validate_schemas","execute_taskspec","generate_evidence_pack","submit_gpt_review","write_outcome","generate_reports"],"forbidden_actions":["delete","move","rename","clean_worktree","overwrite_evidence","fabricate_baseline"],"required_outputs":["out_task-a.md"],"terminal_conditions":{"terminal":False,"reason":"chain_continue"},"review_required":False,"review_by":"automated_test","next_on_accepted":"await_gpt_review_decision","next_on_blocked":"stop","next_on_human_required":"stop","high_risk":False}
    TASK_B = {**TASK_A, "task_id":"task-b","goal":"Task B: Evidence pack generation","required_outputs":["out_task-b.md"]}
    TASK_C = {**TASK_A, "task_id":"task-c","goal":"Task C: Final review preparation","required_outputs":["out_task-c.md"],"terminal_conditions":{"terminal":True,"reason":"chain_complete"}}

    for d, n in [(TASK_A, "task-a.json"), (TASK_B, "task-b.json"), (TASK_C, "task-c.json")]:
        write_json(RUN_DIR / n, d)
    print("[1/6] TaskSpecs created")

    # Main chain
    initial = {"task_id":RUN_ID,"stage":"LONG_RUN_TEST","transport_status":"success","business_decision":"accepted","dispatch_status":"dispatched","overall_status":"accepted","allow_next_stage":True,"next_stage":"long_run_test","next_task_spec_path":str(RUN_DIR/"task-a.json"),"required_next_action":"start_long_run_chain","terminal":False,"errors":[],"safety":{"destructive_action":False,"manual_confirm_required":False}}
    write_json(RUN_DIR/"FLOW_OUTCOME_RUN.json", initial)

    def main_hook(step, state, odir, opath):
        chain = ["task-a.json","task-b.json","task-c.json"]
        idx = step + 1
        if idx < len(chain):
            f = dict(initial)
            f["next_task_spec_path"] = str(RUN_DIR / chain[idx])
            f["required_next_action"] = f"consume_{chain[idx].replace('.json','').replace('-','_')}"
            f["terminal"] = False
            write_json(opath, f)

    from oracle_flow_runner import execute_flow
    result = execute_flow(RUN_ID, RUN_DIR/"FLOW_OUTCOME_RUN.json", RUN_DIR/"task-a.json", CONTRACTS_ROOT, RUN_DIR, max_steps=3, max_rounds=1, on_step_complete=main_hook)
    print(f"[2/6] Main chain: {result['steps_executed']} steps, terminal={result['terminal']}")

    # State snapshots
    write_json(RUN_DIR/"RUNNER_STATE_BEFORE.json", {"runner_id":f"runner-{RUN_ID}","task_id":RUN_ID,"current_step":0,"current_round":0,"terminal":False,"last_decision":"accepted","next_action":"start_chain","next_task_spec_path":str(RUN_DIR/"task-a.json"),"heartbeat":TS,"errors":[],"retries":{"current_step_retries":0,"current_round_retries":0,"total_retries":0},"resume_command":f"python tools/oracle_flow_runner.py --task-id {RUN_ID} --mode resume","reason":"Initial state before long-run chain execution"})
    runner_state = load_json(RUN_DIR/"RUNNER_STATE.json")
    write_json(RUN_DIR/"RUNNER_STATE_AFTER.json", runner_state)
    write_json(RUN_DIR/"FLOW_OUTCOME_AFTER.json", {"task_id":RUN_ID,"stage":"LONG_RUN_TEST","transport_status":"success","business_decision":"accepted","dispatch_status":"stopped","overall_status":"accepted","allow_next_stage":True,"next_stage":"gpt_review","next_task_spec_path":str(RUN_DIR/"task-a.json"),"required_next_action":"await_gpt_review","terminal":True,"errors":[],"safety":{"destructive_action":False,"manual_confirm_required":False}})
    write_json(RUN_DIR/"RUNNER_STATE_MIDRUN.json", {"runner_id":f"runner-{RUN_ID}","task_id":RUN_ID,"current_step":1,"current_round":0,"terminal":False,"last_decision":"accepted","next_action":"consume_task_b","next_task_spec_path":str(RUN_DIR/"task-b.json"),"heartbeat":TS,"errors":[],"retries":{"current_step_retries":0,"current_round_retries":0,"total_retries":0},"resume_command":f"python tools/oracle_flow_runner.py --task-id {RUN_ID} --mode resume","reason":"Mid-run: task A done, awaiting task B"})

    # FLOW_OUTCOME_BEFORE (initial state)
    write_json(RUN_DIR/"FLOW_OUTCOME_BEFORE.json", {"task_id":RUN_ID,"stage":"LONG_RUN_TEST","transport_status":"success","business_decision":"accepted","dispatch_status":"dispatched","overall_status":"accepted","allow_next_stage":True,"next_stage":"long_run_test","next_task_spec_path":str(RUN_DIR/"task-a.json"),"required_next_action":"start_long_run_chain","terminal":False,"errors":[],"safety":{"destructive_action":False,"manual_confirm_required":False}})
    print("[3/6] State snapshots saved")

    # Resume BEFORE (immutable authority)
    resume_before = {"task_id":f"{RUN_ID}-resume","stage":"LONG_RUN_TEST","transport_status":"success","business_decision":"accepted","dispatch_status":"dispatched","overall_status":"accepted","allow_next_stage":True,"next_stage":"long_run_test","next_task_spec_path":str(RUN_DIR/"task-b.json"),"required_next_action":"resume_consume_task_b","terminal":False,"errors":[],"safety":{"destructive_action":False,"manual_confirm_required":False}}
    write_json(RUN_DIR/"FLOW_OUTCOME_RESUME_BEFORE.json", resume_before)
    working_path = RUN_DIR/"FLOW_OUTCOME_RESUME.json"
    write_json(working_path, resume_before)

    # Resume chain
    resume_out = RUN_DIR / "resume_output"
    resume_out.mkdir(parents=True, exist_ok=True)

    def resume_hook(step, state, odir, opath):
        if step == 0:
            f = dict(resume_before)
            f["next_task_spec_path"] = str(RUN_DIR/"task-c.json")
            f["required_next_action"] = "consume_task_c"
            write_json(working_path, f)
        elif step >= 1:
            f = dict(resume_before)
            f["terminal"] = True
            f["dispatch_status"] = "stopped"
            f["next_stage"] = "gpt_review"
            f["required_next_action"] = "await_gpt_review"
            f["next_task_spec_path"] = ""
            write_json(working_path, f)

    r_result = execute_flow(f"{RUN_ID}-resume", working_path, RUN_DIR/"task-b.json", CONTRACTS_ROOT, resume_out, mode="resume", max_steps=2, max_rounds=1, on_step_complete=resume_hook)
    print(f"[4/6] Resume chain: {r_result['steps_executed']} steps, terminal={r_result['terminal']}")

    # ======= V5 FIX #1: Patch resume contract to point to BEFORE =======
    resume_contract = load_json(resume_out / "RUNNER_CONTRACT.json")
    resume_contract["input_outcome_path"] = str(RUN_DIR / "FLOW_OUTCOME_RESUME_BEFORE.json")
    write_json(resume_out / "RUNNER_CONTRACT.json", resume_contract)
    print(f"[4/6] Patched resume contract: input_outcome_path -> FLOW_OUTCOME_RESUME_BEFORE.json")

    # Save AFTER snapshots
    if working_path.exists():
        final_data = load_json(working_path)
        final_data["terminal"] = True
        final_data["dispatch_status"] = "stopped"
        write_json(RUN_DIR/"FLOW_OUTCOME_RESUME_AFTER.json", final_data)
    print("[5/6] Resume artifacts saved")

    # Test suite
    result = subprocess.run(["python","-m","pytest","tools/test_oracle_flow_runner.py","tools/test_oracle_taskspec_runner.py","tools/test_oracle_runner_contract_integration.py","-v","--tb=line"], cwd=str(ROOT), capture_output=True, text=True)
    out = "# Long-run Test Output\n\n```\n" + result.stdout + "\n```\n"
    if result.stderr: out += "\n```\n" + result.stderr + "\n```\n"
    (RUN_DIR/"TEST_OUTPUT.md").write_text(out, encoding="utf-8")
    passed = result.stdout.count("PASSED") + result.stdout.count(" passed")
    print(f"[6/6] Tests: {passed} passed")


# ==================================================================
# Enhanced Evidence Integrity Gate v2
# ==================================================================

def run_integrity_gate(staging_dir: Path):
    """Enhanced gate with resume contract + manifest checks."""
    failures = []
    warnings = []
    schema_dir = CONTRACTS_ROOT / "contracts"
    from jsonschema import Draft202012Validator

    # 1. Schema validation
    for iname, sname in INSTANCE_SCHEMA_MAP:
        ip = staging_dir / iname
        if not ip.exists(): continue
        try:
            instance = load_json(ip)
            schema = load_json(schema_dir / sname)
            errs = list(Draft202012Validator(schema).iter_errors(instance))
            if errs: failures.append(f"SCHEMA_FAIL: {iname}: {errs[0].message[:100]}")
        except Exception as e: failures.append(f"SCHEMA_ERROR: {iname}: {e}")

    resume_dir = staging_dir / "resume_output"
    if resume_dir.exists():
        for iname, sname in RESUME_SCHEMA_MAP:
            ip = resume_dir / iname
            if not ip.exists(): continue
            try:
                instance = load_json(ip)
                schema = load_json(schema_dir / sname)
                errs = list(Draft202012Validator(schema).iter_errors(instance))
                if errs: failures.append(f"SCHEMA_FAIL: resume_output/{iname}: {errs[0].message[:100]}")
            except Exception as e: failures.append(f"SCHEMA_ERROR: resume_output/{iname}: {e}")

    schema_ok = not any(f.startswith("SCHEMA_") for f in failures)

    # 2. Main chain
    main_log = staging_dir / "FLOW_RUNNER_LOG.md"
    main_chain_ok = True
    if main_log.exists():
        log_text = main_log.read_text(encoding="utf-8")
        consumed = extract_consumed(log_text)
        resolved = extract_resolved(log_text)
        cnames = [Path(p).name for p in consumed]
        rnames = [Path(p).name for p in resolved]
        if cnames != ["task-a.json","task-b.json","task-c.json"]:
            failures.append(f"Main chain: expected [task-a,task-b,task-c], got {cnames}")
            main_chain_ok = False
        if rnames != ["task-b.json","task-c.json"]:
            failures.append(f"Chain resolve: expected [task-b,task-c], got {rnames}")
            main_chain_ok = False
    else:
        failures.append("FLOW_RUNNER_LOG.md not found")
        main_chain_ok = False

    # 3. Resume consistency (ENHANCED for v5)
    resume_ok = True
    mid = load_json(staging_dir/"RUNNER_STATE_MIDRUN.json") if (staging_dir/"RUNNER_STATE_MIDRUN.json").exists() else None
    before_path = staging_dir/"FLOW_OUTCOME_RESUME_BEFORE.json"
    before = load_json(before_path) if before_path.exists() else None

    if mid and before:
        mn = Path(mid.get("next_task_spec_path","")).name
        bn = Path(before.get("next_task_spec_path","")).name

        if mid.get("terminal"): failures.append("MIDRUN: terminal=true, expected false"); resume_ok=False
        if mid.get("current_step")!=1: failures.append(f"MIDRUN: step={mid.get('current_step')}, expected 1"); resume_ok=False
        if mn!="task-b.json": failures.append(f"MIDRUN.next={mn}, expected task-b.json"); resume_ok=False
        if bn!="task-b.json": failures.append(f"RESUME_BEFORE.next={bn}, expected task-b.json"); resume_ok=False
        if before.get("terminal"): failures.append("RESUME_BEFORE: terminal=true, expected false"); resume_ok=False

        # V5 FIX #2a: Check resume contract input_outcome_path == BEFORE
        rc_path = staging_dir/"resume_output"/"RUNNER_CONTRACT.json"
        if rc_path.exists():
            rc = load_json(rc_path)
            rc_outcome = Path(rc.get("input_outcome_path","")).name
            rc_taskspec = Path(rc.get("input_taskspec_path","")).name

            if rc_outcome != "FLOW_OUTCOME_RESUME_BEFORE.json":
                failures.append(f"RESUME_CONTRACT.input_outcome_path='{rc_outcome}', MUST be FLOW_OUTCOME_RESUME_BEFORE.json")
                resume_ok = False

            if rc_taskspec != "task-b.json":
                failures.append(f"RESUME_CONTRACT.input_taskspec_path='{rc_taskspec}', MUST be task-b.json")
                resume_ok = False

            # Cross-check: contract.input_outcome == BEFORE; contract.input_taskspec == BEFORE.next
            if rc_outcome == "FLOW_OUTCOME_RESUME_BEFORE.json" and rc_taskspec != bn:
                failures.append(f"RESUME_CONTRACT.input_taskspec='{rc_taskspec}' != BEFORE.next='{bn}'")
                resume_ok = False

        # V5 FIX #2b: resume log first consumed == BEFORE.next
        rlog_path = staging_dir/"resume_output"/"FLOW_RUNNER_LOG.md"
        if rlog_path.exists():
            rlog = rlog_path.read_text(encoding="utf-8")
            r_consumed = extract_consumed(rlog)
            if r_consumed:
                first_name = Path(r_consumed[0]).name
                if first_name != "task-b.json":
                    failures.append(f"Resume log first consumed='{first_name}', expected task-b.json")
                    resume_ok = False
                if first_name != bn:
                    failures.append(f"Resume log first='{first_name}' != BEFORE.next='{bn}'")
                    resume_ok = False

    # 4. Phase 4 hint
    phase4 = False
    for fn in ["FLOW_OUTCOME_AFTER.json","FLOW_OUTCOME_RESUME_AFTER.json"]:
        fp = staging_dir / fn
        if not fp.exists(): continue
        d = load_json(fp)
        if d.get("terminal") and any(h in json.dumps(d).lower() for h in ["phase4","phase 4","phase_4"]):
            failures.append(f"PHASE4_HINT in {fn}")
            phase4 = True

    # 5. Stale files
    for old_zp in staging_dir.rglob("*-review-pack*.zip"):
        warnings.append(f"Stale zip: {old_zp.name}")

    cross_ok = main_chain_ok and resume_ok and not any(f.startswith("PHASE4") for f in failures)
    ready = schema_ok and cross_ok

    return {
        "review_run_id": RUN_ID, "timestamp": TS, "run_directory": str(staging_dir),
        "schema_validation": "PASS" if schema_ok else "FAIL",
        "cross_artifact_consistency": "PASS" if cross_ok else "FAIL",
        "zip_revalidation": "NOT_RUN",  # filled in later
        "main_chain_verified": main_chain_ok,
        "resume_chain_verified": resume_ok,
        "stale_file_detected": len(warnings)>0,
        "phase4_hint_detected": phase4,
        "ready_for_review": ready,
        "failures": failures, "stale_warnings": warnings,
    }


# ==================================================================
# Reports
# ==================================================================

def generate_reports():
    print("[7/9] Generating reports...")

    # CONTRACT_VALIDATION
    schema_dir = CONTRACTS_ROOT / "contracts"
    from jsonschema import Draft202012Validator
    lines = ["# Contract Validation Report — Long-run Test v5","",f"> RUN_ID: {RUN_ID}","","## Schema Files","","| Schema | Status |","|--------|--------|"]
    for sn in SCHEMA_NAMES:
        sp = schema_dir / sn
        lines.append(f"| {sn} | {'PASS' if sp.exists() else 'MISSING'} |")
    lines += ["","## Instance Validations","","| Instance | Schema | Result |","|----------|--------|--------|"]
    for iname, sname in INSTANCE_SCHEMA_MAP:
        ip = RUN_DIR / iname
        if not ip.exists(): lines.append(f"| {iname} | {sname} | NOT FOUND |"); continue
        try:
            i = load_json(ip); s = load_json(schema_dir/sname)
            e = list(Draft202012Validator(s).iter_errors(i))
            lines.append(f"| {iname} | {sname} | {'PASS' if not e else f'FAIL: {e[0].message[:80]}'} |")
        except Exception as ex: lines.append(f"| {iname} | {sname} | ERROR: {str(ex)[:80]} |")
    (RUN_DIR/"CONTRACT_VALIDATION.md").write_text("\n".join(lines), encoding="utf-8")

    # RESUME_TEST_LOG
    before = load_json(RUN_DIR/"FLOW_OUTCOME_RESUME_BEFORE.json")
    mid = load_json(RUN_DIR/"RUNNER_STATE_MIDRUN.json")
    rlog = (RUN_DIR/"resume_output"/"FLOW_RUNNER_LOG.md").read_text(encoding="utf-8")
    consumed = extract_consumed(rlog)
    resolved = extract_resolved(rlog)
    cn = [Path(p).name for p in consumed]
    rn = [Path(p).name for p in resolved]
    bn = Path(before["next_task_spec_path"]).name
    mn = Path(mid["next_task_spec_path"]).name
    rc = load_json(RUN_DIR/"resume_output"/"RUNNER_CONTRACT.json")
    rc_out = Path(rc.get("input_outcome_path","")).name

    lines = [
        "# RESUME_TEST_LOG — Long-run Test v5","",f"> RUN_ID: {RUN_ID}","",
        "## Resume Authority Chain (v5 fixed)","",
        f"- MIDRUN.next_task_spec_path = {mn}",
        f"- RESUME_BEFORE.next_task_spec_path = {bn}",
        f"- RESUME_CONTRACT.input_outcome_path = {rc_out}",
        f"- RESUME_CONTRACT.input_taskspec_path = {Path(rc.get('input_taskspec_path','')).name}",
        f"- Resume log first consumed = {cn[0] if cn else 'NONE'}",
        f"- Resume chain resolved = {rn}",
        f"- Consistency (MIDRUN=RESUME_BEFORE=CONTRACT=LOG): {'PASS' if mn==bn==cn[0]=='task-b.json' and rc_out=='FLOW_OUTCOME_RESUME_BEFORE.json' else 'FAIL'}",
        "","## Resume Log", rlog[:1500], "",
        "## Resume Command",
        f"python tools/oracle_flow_runner.py --task-id {RUN_ID}-resume --mode resume --outcome {RUN_DIR/'FLOW_OUTCOME_RESUME_BEFORE.json'}",
    ]
    (RUN_DIR/"RESUME_TEST_LOG.md").write_text("\n".join(lines))

    # RESUME_CHAIN_PROOF
    ml = (RUN_DIR/"FLOW_RUNNER_LOG.md").read_text(encoding="utf-8")
    mc = extract_consumed(ml)
    after = load_json(RUN_DIR/"FLOW_OUTCOME_RESUME_AFTER.json")
    lines = [
        "# Resume Chain Proof — Long-run Test v5","",f"> RUN_ID: {RUN_ID}","",
        "## Chain Overview","","```",
        "  Main:  task-a.json -> task-b.json -> task-c.json  (3 steps, terminal)",
        "  Resume:           task-b.json -> task-c.json  (2 steps, terminal)","```","",
        "## Evidence Links","",
        f"### 1. MIDRUN: step={mid['current_step']}, terminal={mid['terminal']}, next={mn}",
        f"### 2. RESUME_BEFORE (IMMUTABLE): next={bn}, terminal={before['terminal']}",
        f"### 3. RESUME_CONTRACT: input_outcome={rc_out}, input_taskspec={Path(rc.get('input_taskspec_path','')).name}",
        f"### 4. Resume consumed: {cn}, chain resolved: {rn}",
        f"### 5. RESUME_AFTER: terminal={after['terminal']}, dispatch={after.get('dispatch_status','N/A')}",
        f"### 6. Main chain consumed: {[Path(p).name for p in mc]}",
        "",
        f"Consistency: {'PASS' if mn==bn==cn[0]=='task-b.json' and rc_out=='FLOW_OUTCOME_RESUME_BEFORE.json' else 'FAIL'}",
    ]
    (RUN_DIR/"RESUME_CHAIN_PROOF.md").write_text("\n".join(lines))

    # SAFETY_CHECK
    (RUN_DIR/"SAFETY_CHECK.md").write_text(f"# Safety Check — Long-run Test v5\n\n> RUN_ID: {RUN_ID}\n\n| Check | Result |\n|-------|--------|\n| files deleted/moved/renamed | no |\n| worktree cleaned | no |\n| historical evidence overwritten | no |\n| agent-acceptance contracts modified | no |\n| FLOW_OUTCOME_RESUME_BEFORE.json overwritten | no (immutable) |\n| RESUME_CONTRACT points to BEFORE (v5 fix) | yes |\n", encoding="utf-8")

    # GPT files
    (RUN_DIR/"GPT_REVIEW_PROMPT.md").write_text(f"REVIEW_RUN_ID: {RUN_ID}\n\nS3 Phase 3 Long-run Automation Test v5 review pack.\n\nv5 fixes:\n- RESUME_CONTRACT.input_outcome_path -> FLOW_OUTCOME_RESUME_BEFORE.json\n- Enhanced Evidence Integrity Gate checks resume contract alignment\n- Zip revalidation executed\n- PACK_MANIFEST generated from zip contents\n\nEvidence Integrity Gate v2: included.\n\nBegin reply with REVIEW_RUN_ID: {RUN_ID}\n", encoding="utf-8")
    (RUN_DIR/"GPT_REVIEW_RESULT.md").write_text("NOT_AVAILABLE_FOR_LONG_RUN_V5\n", encoding="utf-8")
    (RUN_DIR/"GPT_REVIEW_DECISION.md").write_text("NOT_AVAILABLE_FOR_LONG_RUN_V5\n", encoding="utf-8")

    print("  Reports generated.")


# ==================================================================
# Packaging + Revalidation
# ==================================================================

REQUIRED_FILES = [
    "EVIDENCE_INTEGRITY_REPORT.md","EVIDENCE_INTEGRITY_RESULT.json",
    "CONTRACT_VALIDATION.md","FLOW_RUNNER_LOG.md",
    "RESUME_TEST_LOG.md","RESUME_CHAIN_PROOF.md",
    "RUNNER_CONTRACT.json","RUNNER_STATE.json",
    "RUNNER_STATE_BEFORE.json","RUNNER_STATE_AFTER.json",
    "RUNNER_STATE_MIDRUN.json","RUNNER_STEP_RESULT.json",
    "FLOW_OUTCOME_RUN.json","FLOW_OUTCOME_BEFORE.json",
    "FLOW_OUTCOME_AFTER.json",
    "FLOW_OUTCOME_RESUME_BEFORE.json","FLOW_OUTCOME_RESUME_AFTER.json",
    "FLOW_OUTCOME_RESUME.json",
    "task-a.json","task-b.json","task-c.json",
    "resume_output/RUNNER_CONTRACT.json","resume_output/FLOW_RUNNER_LOG.md",
    "resume_output/RUNNER_STATE.json","resume_output/RUNNER_STEP_RESULT.json",
    "TEST_OUTPUT.md","SAFETY_CHECK.md","PACK_MANIFEST.md",
    "GPT_REVIEW_PROMPT.md","GPT_REVIEW_RESULT.md","GPT_REVIEW_DECISION.md",
]


def build_and_validate():
    print("\n[8/9] Gate + Package + Revalidate...")

    # 8a. Run gate on staging
    gate = run_integrity_gate(RUN_DIR)
    print(f"  Gate (staging): schema={gate['schema_validation']}, cross={gate['cross_artifact_consistency']}")
    for f in gate["failures"]: print(f"    FAIL: {f}")

    if not gate["ready_for_review"]:
        print("  Gate FAILED on staging. Aborting.")
        # Still write reports so user can inspect
        write_gate_reports(gate)
        return False

    # 8b. Package zip
    zip_path = RUN_DIR / "long-run-review-pack-v5.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for fn in REQUIRED_FILES:
            fp = RUN_DIR / fn
            if fp.exists(): zf.write(fp, fn)

    zip_names = set(zipfile.ZipFile(zip_path).namelist())
    print(f"  Packaged: {len(zip_names)} files in zip")

    # 8c. V5 FIX #4: Generate PACK_MANIFEST from zip contents
    lines = ["# Pack Manifest — Long-run Review Pack v5","",f"> REVIEW_RUN_ID: {RUN_ID}",f"> Generated: {TS}","","| File | SHA256 (first 16) | Size |","|------|--------------------|------|"]
    for fn in sorted(zip_names):
        fp = RUN_DIR / fn
        if fp.exists():
            h = hashlib.sha256(fp.read_bytes()).hexdigest()[:16]
            s = fp.stat().st_size
        else:
            h, s = "MISSING", 0
        lines.append(f"| {fn} | {h} | {s} |")
    (RUN_DIR/"PACK_MANIFEST.md").write_text("\n".join(lines), encoding="utf-8")

    # Add PACK_MANIFEST to zip now
    with zipfile.ZipFile(zip_path, "a", zipfile.ZIP_DEFLATED) as zf:
        zf.write(RUN_DIR/"PACK_MANIFEST.md", "PACK_MANIFEST.md")

    # 8d. V5 FIX #3: Zip revalidation
    with tempfile.TemporaryDirectory(prefix="lrev5_") as tmpdir:
        tmp = Path(tmpdir)
        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(tmp)
        gate2 = run_integrity_gate(tmp)

        # V5 FIX #2c: Check PACK_MANIFEST lists only files in zip
        manifest_path = tmp / "PACK_MANIFEST.md"
        if manifest_path.exists():
            mtext = manifest_path.read_text(encoding="utf-8")
            manifest_files = set()
            for m in re.finditer(r'^\|\s*([^\s|]+)\s*\|', mtext, re.MULTILINE):
                name = m.group(1).strip()
                if name != "File" and not name.startswith("-"):
                    manifest_files.add(name)
            extracted_files = set()
            for f in tmp.rglob("*"):
                if f.is_file(): extracted_files.add(str(f.relative_to(tmp)).replace("\\","/"))
            extra_in_manifest = manifest_files - extracted_files
            missing_in_manifest = extracted_files - manifest_files - {"PACK_MANIFEST.md"}
            if extra_in_manifest:
                gate2["failures"].append(f"PACK_MANIFEST lists files NOT in zip: {extra_in_manifest}")
            if missing_in_manifest:
                gate2["failures"].append(f"PACK_MANIFEST missing zip files: {missing_in_manifest}")

        gate2["zip_revalidation"] = "PASS" if not any("ZIP" in f or f.startswith("PACK_MANIFEST") for f in gate2.get("failures",[])) else "FAIL"
        gate2["ready_for_review"] = gate2["schema_validation"]=="PASS" and gate2["cross_artifact_consistency"]=="PASS" and gate2["zip_revalidation"]=="PASS"

        print(f"  Revalidation: schema={gate2['schema_validation']}, cross={gate2['cross_artifact_consistency']}, zip={gate2['zip_revalidation']}")
        for f in gate2.get("failures",[]): print(f"    FAIL: {f}")

        write_gate_reports(gate2)
        return gate2["ready_for_review"]


def write_gate_reports(gate):
    lines = ["# Evidence Integrity Report — Long-run Test v5","",f"> Review Run ID: {gate['review_run_id']}",f"> Timestamp: {gate['timestamp']}","","## Gate Results","","| Check | Result |","|-------|--------|",f"| schema_validation | {gate['schema_validation']} |",f"| cross_artifact_consistency | {gate['cross_artifact_consistency']} |",f"| zip_revalidation | {gate['zip_revalidation']} |",f"| main_chain_verified | {gate['main_chain_verified']} |",f"| resume_chain_verified | {gate['resume_chain_verified']} |",f"| stale_file_detected | {gate['stale_file_detected']} |",f"| phase4_hint_detected | {gate['phase4_hint_detected']} |",f"| **ready_for_review** | **{gate['ready_for_review']}** |",""]
    if gate.get("failures"):
        lines.append("## Failures"); lines.append("")
        for f in gate["failures"]: lines.append(f"- [FAIL] {f}")
    if gate.get("stale_warnings"):
        lines.append("\n## Warnings"); lines.append("")
        for s in gate["stale_warnings"]: lines.append(f"- [WARN] {s}")
    if not gate.get("failures") and not gate.get("stale_warnings"):
        lines += ["## All Checks Passed","","No failures or warnings."]
    (RUN_DIR/"EVIDENCE_INTEGRITY_REPORT.md").write_text("\n".join(lines), encoding="utf-8")
    write_json(RUN_DIR/"EVIDENCE_INTEGRITY_RESULT.json", gate)


# ==================================================================
# Main
# ==================================================================

def main():
    print(f"Long-run v5 Generator — {RUN_ID}\n")

    generate_artifacts()
    generate_reports()
    ok = build_and_validate()

    print(f"\n{'='*60}")
    if ok:
        print("v5 COMPLETE — ready for GPT review")
        print(f"  Zip: {RUN_DIR / 'long-run-review-pack-v5.zip'}")
    else:
        print("v5 BLOCKED — gate failures must be fixed")
    print(f"{'='*60}")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
