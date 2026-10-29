#!/usr/bin/env python3
"""Test FlowState, checkpoint, idempotency, outcome, URL validation."""
import json
import sys
import tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from oracle_flow_state import (FlowState, save_state, load_state,
    write_outcome, read_outcome, compute_idempotency_key, validate_target_url)

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

# Test 1: checkpoint writes stage
state = FlowState("test", 1)
state.checkpoint("PAGE_READY", page_url="https://x.com/c/abc")
check("checkpoint stage", state.stage == "PAGE_READY")
check("history has entry", len(state.history) == 1)

# Test 2: idempotency key
k1 = compute_idempotency_key("s2", 1, "prompt.md", "zip.zip")
k2 = compute_idempotency_key("s2", 1, "prompt.md", "zip.zip")
k3 = compute_idempotency_key("s2", 2, "prompt.md", "zip.zip")
check("idempotency key same", k1 == k2)
check("idempotency key different round", k1 != k3)

# Test 3: outcome JSON
state.transport_status = "success"
state.business_decision = "blocked"
state.dispatch_status = "stopped"
state.compute_statuses()
outcome = state.to_outcome()
check("outcome has transport_status", outcome["transport_status"] == "success")
check("outcome has business_decision", outcome["business_decision"] == "blocked")
check("overall_status not SUCCESS", outcome["overall_status"] != "SUCCESS")
check("overall_status has transport_success_business_blocked",
      "blocked" in outcome["overall_status"])

# Test 4: save/load roundtrip
tmp = Path(tempfile.mkdtemp()) / "state.json"
save_state(state, tmp)
loaded = load_state(tmp)
check("load roundtrip task_id", loaded["task_id"] == "test")

# Test 5: write/read outcome
tmp_out = Path(tempfile.mkdtemp()) / "outcome.json"
write_outcome(tmp_out, outcome)
read = read_outcome(tmp_out)
check("outcome roundtrip", read["task_id"] == "test")

# Test 6: URL validation
v, r = validate_target_url("https://chatgpt.com/c/6a1d4a71-0064-83a2-b762-0987baccba8f")
check("valid URL", v and r == "valid", f"got {r}")

v, r = validate_target_url("")
check("empty URL fails", not v, f"got {v}")

v, r = validate_target_url("https://evil.com/c/123-456")
check("wrong domain fails", not v, f"got {r}")

v, r = validate_target_url("https://chatgpt.com/")
check("no session fails", not v, f"got {r}")

print(f"\nResults: {passed} passed, {failed} failed")
sys.exit(0 if failed == 0 else 1)
