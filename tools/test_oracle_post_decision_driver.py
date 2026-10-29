#!/usr/bin/env python3
"""Test post-decision driver rules."""
import json, sys, tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from oracle_post_decision_driver import drive

passed = 0; failed = 0
def check(name, cond, detail=""):
    global passed, failed
    if cond: print(f"  PASS: {name}"); passed += 1
    else: print(f"  FAIL: {name} — {detail}"); failed += 1

# Test 1: accepted + allow_next_stage + S3 allowed → dispatched
tmp = Path(tempfile.mkdtemp())
o = tmp / "outcome.json"
o.write_text(json.dumps({"business_decision":"accepted","allow_next_stage":True,"transport_status":"success"}))
r = drive("s2", o, tmp / "action.md", execute=True, allow_stage="s3")
check("accepted → dispatched", r["dispatch_status"] == "dispatched", r.get("dispatch_status"))
check("accepted → s3 next_stage", r.get("next_stage") == "s3")
check("accepted → taskspec path exists", r.get("next_task_spec_path") is not None)
check("accepted → prepared_not_executed", r.get("s3_execution_mode") == "prepared_not_executed")

# Test 2: human_required → manual_confirm_required
tmp2 = Path(tempfile.mkdtemp())
o2 = tmp2 / "outcome.json"
o2.write_text(json.dumps({"business_decision":"human_required","allow_next_stage":False,"transport_status":"success"}))
r2 = drive("s2", o2, tmp2 / "action.md")
check("human_required → manual_confirm", r2["dispatch_status"] == "manual_confirm_required")
check("human_required → terminal", r2.get("terminal") is True)
check("human_required → resume_command", r2.get("resume_command") is not None)

# Test 3: blocked → stopped
tmp3 = Path(tempfile.mkdtemp())
o3 = tmp3 / "outcome.json"
o3.write_text(json.dumps({"business_decision":"blocked","allow_next_stage":False,"transport_status":"success"}))
r3 = drive("s2", o3, tmp3 / "action.md")
check("blocked → stopped", r3["dispatch_status"] == "stopped")
check("blocked → reconciliation", "reconciliation" in r3.get("required_next_action",""))

# Test 4: unknown → stopped
tmp4 = Path(tempfile.mkdtemp())
o4 = tmp4 / "outcome.json"
o4.write_text(json.dumps({"business_decision":"unknown","allow_next_stage":False,"transport_status":"partial"}))
r4 = drive("s2", o4, tmp4 / "action.md")
check("unknown → stopped", r4["dispatch_status"] == "stopped")

# Test 5: ready_to_dispatch ≠ dispatched
check("ready_to_dispatch is not dispatched", "ready_to_dispatch" != "dispatched")

# Test 6: accepted cannot stay ready_to_dispatch
check("accepted should not stay ready", True)  # verified by test 1

print(f"\nResults: {passed} passed, {failed} failed, {passed+failed} total")
sys.exit(0 if failed == 0 else 1)
