"""validate_paper_graph_ledger.py — A12 Validation Script.

Validates the Paper Graph + Ledger Integration:
  1. Module structure
  2. State model (ledger fields)
  3. ledger_ingest_node function
  4. Graph construction (5 nodes)
  5. Graph execution with ledger
  6. Finalizer ledger enrichment
  7. Integration end-to-end
  8. Test suite
"""

from __future__ import annotations

import importlib
import json
import subprocess
import sys
import tempfile
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
print("A12 Validation: Paper Graph + Ledger Integration")
print("=" * 60)

# ---------------------------------------------------------------------------
print("\n[1] Module Structure")
# ---------------------------------------------------------------------------
graph_path = SRC_DIR / "workflows" / "paper_graph.py"
state_path = SRC_DIR / "workflows" / "paper_workflow_state.py"
ledger_path = SRC_DIR / "context_layer" / "adapters" / "paper_issue_ledger.py"
check("paper_graph.py exists", graph_path.exists())
check("paper_workflow_state.py exists", state_path.exists())
check("paper_issue_ledger.py exists", ledger_path.exists())

try:
    sys.path.insert(0, str(HUB_DIR / "src"))
    mod_graph = importlib.import_module("ai_workflow_hub.workflows.paper_graph")
    mod_state = importlib.import_module("ai_workflow_hub.workflows.paper_workflow_state")
    mod_ledger = importlib.import_module("ai_workflow_hub.context_layer.adapters.paper_issue_ledger")
    check("all modules importable", True)
except Exception as e:
    check("modules importable", False, str(e))
    sys.exit(1)

# ---------------------------------------------------------------------------
print("[2] State Model (A12 ledger fields)")
# ---------------------------------------------------------------------------
PaperWorkflowState = mod_state.PaperWorkflowState
state = PaperWorkflowState()
d = state.model_dump()
check("ledger_dir field exists", "ledger_dir" in d)
check("ledger_summary field exists", "ledger_summary" in d)
check("ledger_issue_count field exists", "ledger_issue_count" in d)
check("ledger_dir default empty", d["ledger_dir"] == "")
check("ledger_summary default empty", d["ledger_summary"] == {})
check("ledger_issue_count default 0", d["ledger_issue_count"] == 0)

# ---------------------------------------------------------------------------
print("[3] ledger_ingest_node")
# ---------------------------------------------------------------------------
tmp = Path(tempfile.mkdtemp())

def make_issue(iid, blocking=False, severity="minor", issue_type="expression"):
    return {"issue_id": iid, "issue_type": issue_type, "severity": severity,
            "evidence": "test", "blocking": blocking, "recommendation": "fix",
            "human_required": False}

ar = {
    "status": "blocked", "reasons": ["test"],
    "blocking_issues": [make_issue("v-b1", blocking=True, severity="critical")],
    "non_blocking_issues": [make_issue("v-nb1"), make_issue("v-nb2")],
    "required_next_actions": [], "reviewer": "writelab_adapter", "evidence_pack_ref": "ep-v",
}
state_dict = {
    "task_id": "val-ingest", "acceptance_result": ar,
    "ledger_dir": str(tmp), "executed_nodes": [],
}
result = mod_graph.ledger_ingest_node(state_dict)
check("ingest returns count=3", result.get("ledger_issue_count") == 3)
check("ingest returns summary", result.get("ledger_summary", {}).get("total") == 3)
check("ingest marks node executed", "ledger_ingest_node" in result.get("executed_nodes", []))

# ---------------------------------------------------------------------------
print("[4] Graph Construction (5 nodes)")
# ---------------------------------------------------------------------------
graph = mod_graph.create_paper_graph()
node_names = set(graph.nodes.keys())
check("5 nodes", len(node_names) == 5)
check("ledger_ingest node present", "ledger_ingest" in node_names)

# ---------------------------------------------------------------------------
print("[5] Graph Execution with Ledger")
# ---------------------------------------------------------------------------
compiled = mod_graph.compile_paper_graph("val-exec-a12")
config = {"configurable": {"thread_id": "val-exec-a12"}}
result = compiled.invoke({
    "task_id": "graph-ledger-1",
    "writelab_mode": "mock",
    "ledger_dir": str(tmp),
    "expression_issues": [make_issue("gl-1"), make_issue("gl-2", issue_type="citation")],
}, config)
check("invoke completed", result.get("status") == "completed")
check("ledger_issue_count=2", result.get("ledger_issue_count") == 2)
check("ledger_summary total=2", result.get("ledger_summary", {}).get("total") == 2)
check("ledger_ingest_node in executed", "ledger_ingest_node" in result.get("executed_nodes", []))

# ---------------------------------------------------------------------------
print("[6] Finalizer Ledger Enrichment")
# ---------------------------------------------------------------------------
ls = result.get("ledger_summary", {})
check("finalizer has type_breakdown", "type_breakdown" in ls)
check("citation type tracked", ls.get("type_breakdown", {}).get("citation", 0) >= 1)

# ---------------------------------------------------------------------------
print("[7] Integration End-to-End")
# ---------------------------------------------------------------------------
# Verify ledger file persisted
ledger_file = tmp / "graph-ledger-1.json"
check("ledger JSON file created", ledger_file.exists())
if ledger_file.exists():
    data = json.loads(ledger_file.read_text(encoding="utf-8"))
    check("ledger has 2 entries", len(data) == 2)

# Blocked path with ledger
compiled2 = mod_graph.compile_paper_graph("val-block-a12")
config2 = {"configurable": {"thread_id": "val-block-a12"}}
result2 = compiled2.invoke({
    "task_id": "block-ledger-1",
    "writelab_mode": "mock",
    "ledger_dir": str(tmp),
    "expression_issues": [make_issue("bl-1", blocking=True, severity="critical")],
}, config2)
check("blocked path: status=blocked", result2.get("status") == "blocked")
check("blocked path: ledger has blocking", result2.get("ledger_summary", {}).get("blocking", 0) >= 1)

# ---------------------------------------------------------------------------
print("[8] Test Suite")
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

output_path = Path(__file__).resolve().parent / "VALIDATION_OUTPUT_A12.txt"
with open(output_path, "w") as f:
    f.write(f"A12 Validation: {PASS} passed, {FAIL} failed\n")
    f.write("=" * 60 + "\n")
    for r in results:
        f.write(r + "\n")
    if "test_output" in dir():
        f.write("\n--- Test Suite Output ---\n")
        f.write(test_output)
print(f"\nOutput saved to: {output_path}")
sys.exit(0 if FAIL == 0 else 1)
