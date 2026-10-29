#!/usr/bin/env python3
"""Test three-layer status semantics."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from oracle_flow_state import normalize_status

tests = [
    ("transport_success_business_blocked", "success", "blocked", "stopped"),
    ("transport_success_business_human_required", "success", "human_required", "manual_confirm_required"),
    ("ready", "success", "accepted", "ready_to_dispatch"),
    ("transport_partial", "partial", "blocked", "stopped"),
    ("business_unknown", "success", "unknown", "stopped"),
    ("transport_success_business_blocked", "success", "blocked", "dispatched"),
    ("technical_failure_or_incomplete", "failed", "unknown", "failed"),
]

passed = 0
failed = 0
for expected, transport, business, dispatch in tests:
    result = normalize_status(transport, business, dispatch)
    if result == expected:
        print(f"  PASS: {transport}+{business}+{dispatch} = {result}")
        passed += 1
    else:
        print(f"  FAIL: {transport}+{business}+{dispatch} = {result}, expected {expected}")
        failed += 1

# Additional: reject bare "SUCCESS"
assert normalize_status("success", "blocked", "stopped") != "SUCCESS"
assert normalize_status("partial", "unknown", "stopped") != "SUCCESS"
print(f"  PASS: no bare SUCCESS produced")

print(f"\nResults: {passed} passed, {failed} failed, {len(tests)} total")
sys.exit(0 if failed == 0 else 1)
