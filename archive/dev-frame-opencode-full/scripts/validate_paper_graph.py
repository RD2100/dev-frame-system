"""validate_paper_graph.py — A10 Validation Script.

Validates the Paper Workflow State Graph implementation:
  1. Module structure
  2. PaperWorkflowState model
  3. Graph construction
  4. Node functions
  5. Graph execution
  6. Integration
  7. Test suite
"""

from __future__ import annotations

import importlib
import json
import os
import subprocess
import sys
import traceback
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


# ===========================================================================
print("=" * 60)
print("A10 Validation: Paper Workflow State Graph")
print("=" * 60)

# ---------------------------------------------------------------------------
print("\n[1] Module Structure")
# ---------------------------------------------------------------------------
state_path = SRC_DIR / "workflows" / "paper_workflow_state.py"
graph_path = SRC_DIR / "workflows" / "paper_graph.py"

check("paper_workflow_state.py exists", state_path.exists())
check("paper_graph.py exists", graph_path.exists())

try:
    sys.path.insert(0, str(HUB_DIR / "src"))
    mod_state = importlib.import_module("ai_workflow_hub.workflows.paper_workflow_state")
    mod_graph = importlib.import_module("ai_workflow_hub.workflows.paper_graph")
    check("modules importable", True)
except Exception as e:
    check("modules importable", False, str(e))
    print("\nFATAL: cannot import modules")
    sys.exit(1)

# ---------------------------------------------------------------------------
print("[2] PaperWorkflowState Model")
# ---------------------------------------------------------------------------
PaperWorkflowState = mod_state.PaperWorkflowState

state = PaperWorkflowState()
d = state.model_dump()

check("default status=pending", state.status == "pending")
check("default writelab_mode=mock", state.writelab_mode == "mock")
check("default fix_round=0", state.fix_round == 0)
check("default max_fix_rounds=3", state.max_fix_rounds == 3)

required_keys = [
    "task_id", "writelab_mode", "all_review_issues", "acceptance_result",
    "acceptance_status", "blocking_count", "non_blocking_count",
    "human_required", "human_gate_triggered", "executed_nodes",
    "privacy_attestation", "evidence_manifest", "evidence_pack_ref",
]
missing = [k for k in required_keys if k not in d]
check("all required fields present", len(missing) == 0, f"missing: {missing}")

# ---------------------------------------------------------------------------
print("[3] Graph Construction")
# ---------------------------------------------------------------------------
create_paper_graph = mod_graph.create_paper_graph
compile_paper_graph = mod_graph.compile_paper_graph

graph = create_paper_graph()
node_names = set(graph.nodes.keys())
check("4 nodes in graph", len(node_names) == 4, f"found {len(node_names)}")
check("diagnosis node", "diagnosis" in node_names)
check("acceptance_gate node", "acceptance_gate" in node_names)
check("human_gate node", "human_gate" in node_names)
check("finalizer node", "finalizer" in node_names)

compiled = compile_paper_graph("validation-test")
check("graph compiles", compiled is not None)

# ---------------------------------------------------------------------------
print("[4] Node Functions")
# ---------------------------------------------------------------------------
diagnosis_node = mod_graph.diagnosis_node
acceptance_gate_node = mod_graph.acceptance_gate_node
human_gate_node = mod_graph.human_gate_node
paper_finalizer_node = mod_graph.paper_finalizer_node

# Mock mode diagnosis
result = diagnosis_node({
    "writelab_mode": "mock",
    "expression_issues": [{"issue_id": "e1", "issue_type": "expression", "severity": "minor",
                            "evidence": "test", "blocking": False}],
    "paragraph_issues": [],
    "executed_nodes": [],
})
check("mock diagnosis: combines issues", len(result.get("all_review_issues", [])) == 1)
check("mock diagnosis: source=mock", result.get("diagnosis_source") == "mock")

# Acceptance gate
result = acceptance_gate_node({
    "all_review_issues": [],
    "evidence_pack_ref": "ep-val",
    "executed_nodes": ["diagnosis_node"],
})
check("acceptance gate: no issues → accepted", result.get("acceptance_status") == "accepted")

result = acceptance_gate_node({
    "all_review_issues": [{"issue_id": "b1", "issue_type": "expression", "severity": "critical",
                            "evidence": "blocking", "blocking": True}],
    "evidence_pack_ref": "ep-val",
    "executed_nodes": [],
})
check("acceptance gate: blocking → blocked", result.get("acceptance_status") == "blocked")

# Human gate
result = human_gate_node({"executed_nodes": []})
check("human gate: triggered", result.get("human_gate_triggered") is True)
check("human gate: status=human_required", result.get("status") == "human_required")

# Finalizer
result = paper_finalizer_node({
    "acceptance_result": {"status": "accepted"},
    "acceptance_status": "accepted",
    "blocking_count": 0,
    "executed_nodes": [],
})
check("finalizer: accepted → completed", result.get("status") == "completed")

result = paper_finalizer_node({
    "acceptance_result": {"status": "blocked"},
    "acceptance_status": "blocked",
    "blocking_count": 1,
    "executed_nodes": [],
})
check("finalizer: blocked → blocked", result.get("status") == "blocked")

# ---------------------------------------------------------------------------
print("[5] Graph Execution (compile + invoke)")
# ---------------------------------------------------------------------------
config = {"configurable": {"thread_id": "val-exec"}}
compiled2 = compile_paper_graph("val-exec")

# Test: accepted path
result = compiled2.invoke({
    "writelab_mode": "mock",
    "all_review_issues": [],
}, config)
check("invoke accepted: status=completed", result.get("status") == "completed")

# Test: blocked path
config3 = {"configurable": {"thread_id": "val-block"}}
compiled3 = compile_paper_graph("val-block")
result = compiled3.invoke({
    "writelab_mode": "mock",
    "expression_issues": [{"issue_id": "b1", "issue_type": "expression", "severity": "critical",
                            "evidence": "blocking issue", "blocking": True}],
}, config3)
check("invoke blocked: status=blocked", result.get("status") == "blocked")

# Test: human_required path
config4 = {"configurable": {"thread_id": "val-human"}}
compiled4 = compile_paper_graph("val-human")
result = compiled4.invoke({
    "writelab_mode": "mock",
    "expression_issues": [{"issue_id": "h1", "issue_type": "expression", "severity": "major",
                            "evidence": "human needed", "blocking": False, "human_required": True}],
}, config4)
check("invoke human_required: status=human_required", result.get("status") == "human_required")
check("invoke human_required: gate triggered", result.get("human_gate_triggered") is True)

# ---------------------------------------------------------------------------
print("[6] Integration (cross-component)")
# ---------------------------------------------------------------------------
# Wire: mock diagnosis → acceptance gate → routing → finalizer
state = {"writelab_mode": "mock", "expression_issues": [], "paragraph_issues": [],
         "executed_nodes": [], "privacy_attestation": {}}

d_result = diagnosis_node(state)
state.update(d_result)

ag_result = acceptance_gate_node(state)
state.update(ag_result)

route = mod_graph._route_after_acceptance(state)
check("integration: routing correct for accepted", route == "finalizer")

f_result = paper_finalizer_node(state)
state.update(f_result)
check("integration: final status=completed", state.get("status") == "completed")
check("integration: executed_nodes has 3 entries", len(state.get("executed_nodes", [])) == 3)

# ---------------------------------------------------------------------------
print("[7] Test Suite")
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
    # Extract pass count
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

# Save output
output_path = Path(__file__).resolve().parent / "VALIDATION_OUTPUT_A10.txt"
with open(output_path, "w") as f:
    f.write(f"A10 Validation: {PASS} passed, {FAIL} failed\n")
    f.write("=" * 60 + "\n")
    for r in results:
        f.write(r + "\n")
    f.write("\n--- Test Suite Output ---\n")
    if "test_output" in dir():
        f.write(test_output)
print(f"\nOutput saved to: {output_path}")

sys.exit(0 if FAIL == 0 else 1)
