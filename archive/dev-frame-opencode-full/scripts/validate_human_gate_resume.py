"""validate_human_gate_resume.py — A13 Validation Script.

Validates the Paper Human Gate Resume implementation:
  1. Module structure
  2. human_gate_node idempotency
  3. apply_human_decision helper
  4. Routing after human gate
  5. Graph resume execution
  6. Test suite
"""

from __future__ import annotations

import importlib
import subprocess
import sys
from pathlib import Path

HUB_DIR = Path(__file__).resolve().parent.parent / "ai-workflow-hub"
SRC_DIR = HUB_DIR / "src" / "ai_workflow_hub"
PASS = 0
FAIL = 0
results: list[str] = []


def check(name: str, condition: bool, detail: str = ""):
    global PASS, FAIL
    if condition:
        PASS += 1
        results.append(f"  PASS  {name}")
    else:
        FAIL += 1
        results.append(f"  FAIL  {name}" + (f" — {detail}" if detail else ""))


print("=" * 60)
print("A13 Validation: Paper Human Gate Resume")
print("=" * 60)

# ---------------------------------------------------------------------------
print("\n[1] Module Structure")
# ---------------------------------------------------------------------------
graph_path = SRC_DIR / "workflows" / "paper_graph.py"
check("paper_graph.py exists", graph_path.exists())

try:
    sys.path.insert(0, str(HUB_DIR / "src"))
    mod = importlib.import_module("ai_workflow_hub.workflows.paper_graph")
    mod_state = importlib.import_module("ai_workflow_hub.workflows.paper_workflow_state")
    check("modules importable", True)
except Exception as e:
    check("modules importable", False, str(e))
    sys.exit(1)

# ---------------------------------------------------------------------------
print("[2] human_gate_node Idempotency")
# ---------------------------------------------------------------------------
human_gate_node = mod.human_gate_node

# First time: pause
r1 = human_gate_node({"human_gate_decision": "", "executed_nodes": []})
check("first time: human_required=True", r1.get("human_required") is True)
check("first time: decision=pending", r1.get("human_gate_decision") == "pending")
check("first time: status=human_required", r1.get("status") == "human_required")

# Resume approved
r2 = human_gate_node({"human_gate_decision": "approved", "executed_nodes": []})
check("resume approved: human_required=False", r2.get("human_required") is False)
check("resume approved: status=running", r2.get("status") == "running")

# Resume rejected
r3 = human_gate_node({"human_gate_decision": "rejected", "executed_nodes": []})
check("resume rejected: status=rejected", r3.get("status") == "rejected")

# ---------------------------------------------------------------------------
print("[3] apply_human_decision")
# ---------------------------------------------------------------------------
apply_human_decision = mod.apply_human_decision

state = {"task_id": "t1", "human_gate_decision": "pending"}
updated = apply_human_decision(state, "approved")
check("apply approved", updated["human_gate_decision"] == "approved")

updated = apply_human_decision(state, "rejected", note="Too risky")
check("apply rejected with note", "Too risky" in updated.get("error_message", ""))

try:
    apply_human_decision(state, "invalid")
    check("reject invalid decision", False, "should have raised ValueError")
except ValueError:
    check("reject invalid decision", True)

# Pydantic state
PaperWorkflowState = mod_state.PaperWorkflowState
ps = PaperWorkflowState(task_id="t1")
updated = apply_human_decision(ps, "approved")
check("apply to Pydantic state", updated["human_gate_decision"] == "approved")

# ---------------------------------------------------------------------------
print("[4] Routing After Human Gate")
# ---------------------------------------------------------------------------
route_fn = mod._route_after_human_gate
check("route approved → finalizer", route_fn({"human_gate_decision": "approved"}) == "finalizer")
check("route rejected → __end__", route_fn({"human_gate_decision": "rejected"}) == "__end__")
check("route pending → __end__", route_fn({"human_gate_decision": "pending"}) == "__end__")
check("route empty → __end__", route_fn({}) == "__end__")

# ---------------------------------------------------------------------------
print("[5] Graph Resume Execution")
# ---------------------------------------------------------------------------
compiled = mod.compile_paper_graph("val-resume-13")
config = {"configurable": {"thread_id": "val-resume-13"}}

def make_issue(iid, human_required=False, severity="minor", blocking=False):
    return {"issue_id": iid, "issue_type": "expression", "severity": severity,
            "evidence": "test", "blocking": blocking, "recommendation": "fix",
            "human_required": human_required}

# First invoke: pause
result = compiled.invoke({
    "writelab_mode": "mock",
    "expression_issues": [make_issue("h1", human_required=True, severity="major")],
}, config)
check("invoke pauses: status=human_required", result.get("status") == "human_required")
check("invoke pauses: gate triggered", result.get("human_gate_triggered") is True)

# Resume with approval
updated = apply_human_decision(result, "approved")
result2 = compiled.invoke(updated, config)
check("resume: decision=approved preserved", result2.get("human_gate_decision") == "approved")

# ---------------------------------------------------------------------------
print("[6] Test Suite")
# ---------------------------------------------------------------------------
test_file = HUB_DIR / "tests" / "test_paper_graph.py"
check("test file exists", test_file.exists())

try:
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", str(test_file), "-q", "--tb=line"],
        capture_output=True, text=True, timeout=60, cwd=str(HUB_DIR),
    )
    test_output = proc.stdout + proc.stderr
    test_pass = proc.returncode == 0
    import re
    match = re.search(r"(\d+) passed", test_output)
    pass_count = int(match.group(1)) if match else 0
    check(f"all tests pass ({pass_count} tests)", test_pass,
          test_output[-200:] if not test_pass else "")
except Exception as e:
    check("test suite runs", False, str(e))

# ===========================================================================
print("\n" + "=" * 60)
print(f"Results: {PASS} passed, {FAIL} failed")
print("=" * 60)
for r in results:
    print(r)

output_path = Path(__file__).resolve().parent / "VALIDATION_OUTPUT_A13.txt"
with open(output_path, "w") as f:
    f.write(f"A13 Validation: {PASS} passed, {FAIL} failed\n")
    f.write("=" * 60 + "\n")
    for r in results:
        f.write(r + "\n")
    if "test_output" in dir():
        f.write("\n--- Test Suite Output ---\n")
        f.write(test_output)
print(f"\nOutput saved to: {output_path}")
sys.exit(0 if FAIL == 0 else 1)
