"""validate_human_gate_resume.py — A13 Validation: Human Gate Resume.

Validates:
  1. human_gate_node idempotency (first-run vs resume)
  2. apply_human_decision() helper
  3. _route_after_human_gate routing logic
  4. Graph compile + invoke: first run (pause at human_gate)
  5. Graph resume: approved → finalizer → END
  6. Graph resume: rejected → END (no finalizer)
  7. State transitions and field correctness
  8. Edge cases: invalid decision, empty state
"""

from __future__ import annotations

import sys
import traceback

PASS = 0
FAIL = 0
RESULTS: list[str] = []


def check(label: str, condition: bool, detail: str = ""):
    global PASS, FAIL
    if condition:
        PASS += 1
        RESULTS.append(f"  [PASS] {label}")
    else:
        FAIL += 1
        RESULTS.append(f"  [FAIL] {label}" + (f"  -- {detail}" if detail else ""))


def section(title: str):
    RESULTS.append(f"\n=== {title} ===")


# ---------------------------------------------------------------------------
# Import validation
# ---------------------------------------------------------------------------
section("Import validation")

try:
    from ai_workflow_hub.workflows.paper_graph import (
        human_gate_node,
        apply_human_decision,
        _route_after_human_gate,
        _wrap,
        create_paper_graph,
        compile_paper_graph,
        _append_node,
    )
    from ai_workflow_hub.workflows.paper_workflow_state import PaperWorkflowState
    from langgraph.checkpoint.memory import MemorySaver
    check("Import paper_graph modules", True)
except Exception as e:
    check("Import paper_graph modules", False, str(e))
    print("\n".join(RESULTS))
    sys.exit(1)

# ---------------------------------------------------------------------------
# 1. human_gate_node: first-run (no decision)
# ---------------------------------------------------------------------------
section("human_gate_node: first-run")

state_empty = {}
result_first = human_gate_node(state_empty)
check("First run: human_required=True", result_first["human_required"] is True)
check("First run: human_gate_triggered=True", result_first["human_gate_triggered"] is True)
check("First run: decision=pending", result_first["human_gate_decision"] == "pending")
check("First run: status=human_required", result_first["status"] == "human_required")
check("First run: executed_nodes contains human_gate_node",
      "human_gate_node" in result_first["executed_nodes"])

# ---------------------------------------------------------------------------
# 2. human_gate_node: resume with "approved"
# ---------------------------------------------------------------------------
section("human_gate_node: resume approved")

state_approved = {"human_gate_decision": "approved"}
result_approved = human_gate_node(state_approved)
check("Approved: human_required=False", result_approved["human_required"] is False)
check("Approved: status=running", result_approved["status"] == "running")
check("Approved: decision=approved", result_approved["human_gate_decision"] == "approved")
check("Approved: triggered=True", result_approved["human_gate_triggered"] is True)

# ---------------------------------------------------------------------------
# 3. human_gate_node: resume with "rejected"
# ---------------------------------------------------------------------------
section("human_gate_node: resume rejected")

state_rejected = {"human_gate_decision": "rejected"}
result_rejected = human_gate_node(state_rejected)
check("Rejected: human_required=False", result_rejected["human_required"] is False)
check("Rejected: status=rejected", result_rejected["status"] == "rejected")
check("Rejected: decision=rejected", result_rejected["human_gate_decision"] == "rejected")

# ---------------------------------------------------------------------------
# 4. human_gate_node: idempotency (already executed)
# ---------------------------------------------------------------------------
section("human_gate_node: idempotency")

state_already = {
    "human_gate_decision": "approved",
    "executed_nodes": ["human_gate_node"],
}
result_idem = human_gate_node(state_already)
check("Idempotent: executed_nodes no duplicate",
      result_idem["executed_nodes"].count("human_gate_node") == 1)

# ---------------------------------------------------------------------------
# 5. apply_human_decision helper
# ---------------------------------------------------------------------------
section("apply_human_decision")

base_state = {"task_id": "T1", "status": "human_required", "human_gate_decision": "pending"}

# Approved
updated = apply_human_decision(base_state, "approved")
check("apply approved: decision set", updated["human_gate_decision"] == "approved")
check("apply approved: other fields preserved", updated["task_id"] == "T1")

# Rejected with note
updated_r = apply_human_decision(base_state, "rejected", note="Insufficient evidence")
check("apply rejected: decision set", updated_r["human_gate_decision"] == "rejected")
check("apply rejected: note in error_message",
      "rejected" in updated_r.get("error_message", "") and "Insufficient evidence" in updated_r.get("error_message", ""))

# Invalid decision
try:
    apply_human_decision(base_state, "maybe")
    check("apply invalid: raises ValueError", False, "No exception raised")
except ValueError as e:
    check("apply invalid: raises ValueError", True)

# Pydantic state input
pstate = PaperWorkflowState(task_id="T2", human_gate_decision="pending")
updated_p = apply_human_decision(pstate, "approved")
check("apply Pydantic: decision set", updated_p["human_gate_decision"] == "approved")
check("apply Pydantic: task_id preserved", updated_p["task_id"] == "T2")

# ---------------------------------------------------------------------------
# 6. _route_after_human_gate
# ---------------------------------------------------------------------------
section("_route_after_human_gate routing")

check("Route approved → finalizer",
      _route_after_human_gate({"human_gate_decision": "approved"}) == "finalizer")
check("Route rejected → __end__",
      _route_after_human_gate({"human_gate_decision": "rejected"}) == "__end__")
check("Route pending → __end__",
      _route_after_human_gate({"human_gate_decision": "pending"}) == "__end__")
check("Route empty → __end__",
      _route_after_human_gate({}) == "__end__")

# Pydantic state routing
pstate_route = PaperWorkflowState(human_gate_decision="approved")
check("Route Pydantic approved → finalizer",
      _route_after_human_gate(pstate_route) == "finalizer")

# ---------------------------------------------------------------------------
# 7. Graph construction with conditional edges
# ---------------------------------------------------------------------------
section("Graph construction (A13)")

graph = create_paper_graph()
nodes = set(graph.nodes.keys())
check("Graph has 5 nodes", len(nodes) == 5, f"Got {len(nodes)}: {nodes}")
check("human_gate node present", "human_gate" in nodes)
check("finalizer node present", "finalizer" in nodes)

# ---------------------------------------------------------------------------
# 8. Graph execution: first run (pause at human_gate)
# ---------------------------------------------------------------------------
section("Graph execution: first run (mock, human_required)")

try:
    compiled = compile_paper_graph("val-a13-first")
    from ai_workflow_hub.context_layer.adapters.paper_acceptance_gate import compute_acceptance

    # Create an issue that triggers human_required (human_required=True field)
    human_issue = {
        "issue_id": "H1",
        "issue_type": "citation",
        "severity": "major",
        "message": "Missing citation — needs human review",
        "paragraph_index": 0,
        "human_required": True,
    }
    ar = compute_acceptance(
        issues=[human_issue],
        reviewer="writelab_adapter",
        evidence_pack_ref="",
    )

    initial = {
        "writelab_mode": "mock",
        "expression_issues": [],
        "paragraph_issues": [human_issue],
        "all_review_issues": [human_issue],
    }
    # Pre-set acceptance_result to control the route
    initial["acceptance_result"] = ar
    initial["acceptance_status"] = ar.get("status", "")

    config = {"configurable": {"thread_id": "val-a13-first"}}
    result = compiled.invoke(initial, config)

    check("First run: human_gate_triggered",
          result.get("human_gate_triggered") is True)
    check("First run: human_required",
          result.get("human_required") is True)
    check("First run: decision=pending",
          result.get("human_gate_decision") == "pending")
    check("First run: status=human_required",
          result.get("status") == "human_required")
    check("First run: human_gate_node in executed",
          "human_gate_node" in result.get("executed_nodes", []))
    check("First run: finalizer NOT executed (paused before)",
          "paper_finalizer_node" not in result.get("executed_nodes", []))

except Exception as e:
    check("First run graph execution", False, f"{e}\n{traceback.format_exc()}")

# ---------------------------------------------------------------------------
# 9. Graph execution: resume approved → finalizer → END
# ---------------------------------------------------------------------------
section("Graph resume: approved → finalizer")

try:
    compiled2 = compile_paper_graph("val-a13-resume-ok")

    human_issue2 = {
        "issue_id": "H2",
        "issue_type": "citation",
        "severity": "major",
        "message": "Missing citation for claim — human check",
        "paragraph_index": 0,
        "human_required": True,
    }
    ar2 = compute_acceptance(
        issues=[human_issue2],
        reviewer="writelab_adapter",
        evidence_pack_ref="",
    )

    initial2 = {
        "writelab_mode": "mock",
        "expression_issues": [],
        "paragraph_issues": [human_issue2],
        "all_review_issues": [human_issue2],
        "acceptance_result": ar2,
        "acceptance_status": ar2.get("status", ""),
    }

    config2 = {"configurable": {"thread_id": "val-a13-resume-ok"}}
    # First run: pause
    compiled2.invoke(initial2, config2)

    # Resume: set decision to approved
    resume_state = {"human_gate_decision": "approved"}
    result2 = compiled2.invoke(resume_state, config2)

    check("Resume approved: decision=approved",
          result2.get("human_gate_decision") == "approved")
    check("Resume approved: finalizer executed",
          "paper_finalizer_node" in result2.get("executed_nodes", []))
    check("Resume approved: status is terminal",
          result2.get("status") in ("completed", "blocked", "error"))

except Exception as e:
    check("Resume approved graph", False, f"{e}\n{traceback.format_exc()}")

# ---------------------------------------------------------------------------
# 10. Graph execution: resume rejected → END
# ---------------------------------------------------------------------------
section("Graph resume: rejected → END")

try:
    compiled3 = compile_paper_graph("val-a13-resume-rej")

    human_issue3 = {
        "issue_id": "H3",
        "issue_type": "citation",
        "severity": "major",
        "message": "Another missing citation — human review",
        "paragraph_index": 0,
        "human_required": True,
    }
    ar3 = compute_acceptance(
        issues=[human_issue3],
        reviewer="writelab_adapter",
        evidence_pack_ref="",
    )

    initial3 = {
        "writelab_mode": "mock",
        "expression_issues": [],
        "paragraph_issues": [human_issue3],
        "all_review_issues": [human_issue3],
        "acceptance_result": ar3,
        "acceptance_status": ar3.get("status", ""),
    }

    config3 = {"configurable": {"thread_id": "val-a13-resume-rej"}}
    compiled3.invoke(initial3, config3)

    resume_state3 = {"human_gate_decision": "rejected"}
    result3 = compiled3.invoke(resume_state3, config3)

    check("Resume rejected: decision=rejected",
          result3.get("human_gate_decision") == "rejected")
    check("Resume rejected: status=rejected",
          result3.get("status") == "rejected")
    check("Resume rejected: finalizer NOT executed",
          "paper_finalizer_node" not in result3.get("executed_nodes", []))

except Exception as e:
    check("Resume rejected graph", False, f"{e}\n{traceback.format_exc()}")

# ---------------------------------------------------------------------------
# 11. Edge cases
# ---------------------------------------------------------------------------
section("Edge cases")

# human_gate_node with PaperWorkflowState
pstate_edge = PaperWorkflowState(human_gate_decision="approved")
wrapped = _wrap(human_gate_node)
result_wrapped = wrapped(pstate_edge)
check("Wrapped human_gate with Pydantic",
      result_wrapped.get("human_gate_decision") == "approved")

# apply_human_decision preserves existing fields
full_state = {
    "task_id": "T3",
    "acceptance_status": "human_required",
    "blocking_count": 0,
    "human_gate_decision": "pending",
    "executed_nodes": ["diagnosis_node", "acceptance_gate_node"],
}
updated_full = apply_human_decision(full_state, "approved", note="All checks passed")
check("Preserve executed_nodes", len(updated_full["executed_nodes"]) == 2)
check("Preserve acceptance_status", updated_full["acceptance_status"] == "human_required")

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
RESULTS.append(f"\n{'='*50}")
RESULTS.append(f"A13 Validation: {PASS} passed, {FAIL} failed, {PASS+FAIL} total")
RESULTS.append(f"{'='*50}")

output = "\n".join(RESULTS)
print(output)

if FAIL > 0:
    sys.exit(1)
