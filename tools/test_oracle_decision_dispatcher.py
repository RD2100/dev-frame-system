#!/usr/bin/env python3
"""Test decision dispatcher rules."""
import json
import sys
import tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from oracle_decision_dispatcher import dispatch, is_destructive

passed = 0
failed = 0

def check(name, cond, detail=""):
    global passed, failed
    if cond:
        print(f"  PASS: {name}")
        passed += 1
    else:
        print(f"  FAIL: {name} — {detail}")
        failed += 1

# Test 1: accepted + allow_next_stage → ready_to_dispatch
r = dispatch({"transport_status": "success", "business_decision": "accepted",
              "allow_next_stage": True})
check("accepted+allow → ready_to_dispatch", r["dispatch_status"] == "ready_to_dispatch",
      str(r))

# Test 2: blocked → stopped
r = dispatch({"transport_status": "success", "business_decision": "blocked",
              "allow_next_stage": False})
check("blocked → stopped", r["dispatch_status"] == "stopped", str(r))

# Test 3: human_required → manual_confirm_required
r = dispatch({"transport_status": "success", "business_decision": "human_required",
              "allow_next_stage": False})
check("human_required → manual_confirm", r["dispatch_status"] == "manual_confirm_required",
      str(r))
check("human_required has manual_confirm=True", r["manual_confirm_required"] is True)

# Test 4: unknown → stopped
r = dispatch({"transport_status": "success", "business_decision": "unknown",
              "allow_next_stage": False})
check("unknown → stopped", r["dispatch_status"] == "stopped", str(r))

# Test 5: transport failed → failed
r = dispatch({"transport_status": "failed", "business_decision": "accepted",
              "allow_next_stage": True})
check("transport failed → failed", r["dispatch_status"] == "failed", str(r))

# Test 6: destructive keywords
check("delete is destructive", is_destructive("delete old files"))
check("clean is destructive", is_destructive("cleanup worktree"))
check("move is destructive", is_destructive("move file to archive"))
check("rename is destructive", is_destructive("rename report"))
check("generate report is NOT destructive", not is_destructive("generate reconciliation report"))
check("run tests is NOT destructive", not is_destructive("run tests"))

print(f"\nResults: {passed} passed, {failed} failed")
sys.exit(0 if failed == 0 else 1)
