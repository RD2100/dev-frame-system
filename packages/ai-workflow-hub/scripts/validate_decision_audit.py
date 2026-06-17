"""validate_decision_audit.py — A14 Validation: Human Decision Audit Trail.

Validates:
  1. record_decision: persistence, fields, validation, atomic write
  2. read_decision_record: existing, missing, corrupt
  3. get_audit_trail: entries accumulation
  4. apply_human_decision: reviewer_id, timestamp, note, persist
  5. human_gate_node: audit field population on resume
  6. Graph resume with audit fields
  7. log_decision_audit: best-effort global audit
"""

from __future__ import annotations

import json
import sys
import tempfile
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
    from ai_workflow_hub.context_layer.adapters.paper_decision_audit import (
        record_decision,
        read_decision_record,
        get_audit_trail,
        log_decision_audit,
        VALID_DECISIONS,
        DECISION_SCHEMA_VERSION,
        _decision_path,
        _audit_trail_path,
    )
    from ai_workflow_hub.workflows.paper_graph import (
        human_gate_node,
        apply_human_decision,
        compile_paper_graph,
    )
    from ai_workflow_hub.workflows.paper_workflow_state import PaperWorkflowState
    check("Import all A14 modules", True)
except Exception as e:
    check("Import all A14 modules", False, str(e))
    print("\n".join(RESULTS))
    sys.exit(1)


# ---------------------------------------------------------------------------
# 1. record_decision — basic persistence
# ---------------------------------------------------------------------------
section("record_decision: basic persistence")

with tempfile.TemporaryDirectory() as td:
    rec = record_decision("V1", "approved", reviewer_id="alice@corp.com", note="LGTM", base_dir=td)
    check("Returns decision_id", rec["decision_id"] == "V1-decision")
    check("Returns task_id", rec["task_id"] == "V1")
    check("Returns decision", rec["decision"] == "approved")
    check("Returns reviewer_id", rec["reviewer_id"] == "alice@corp.com")
    check("Returns note", rec["note"] == "LGTM")
    check("Has timestamp", "T" in rec["timestamp"])
    check("Has schema_version", rec["schema_version"] == DECISION_SCHEMA_VERSION)

    # Verify file on disk
    path = _decision_path("V1", td)
    check("File exists on disk", path.exists())
    data = json.loads(path.read_text(encoding="utf-8"))
    check("Disk data matches", data["decision"] == "approved" and data["reviewer_id"] == "alice@corp.com")

    # No tmp file left
    import os
    from pathlib import Path
    d = Path(td) / "decisions"
    tmp_files = [f for f in d.iterdir() if f.suffix == ".tmp"]
    check("No .tmp file left (atomic write)", len(tmp_files) == 0)


# ---------------------------------------------------------------------------
# 2. record_decision — rejected
# ---------------------------------------------------------------------------
section("record_decision: rejected")

with tempfile.TemporaryDirectory() as td:
    rec = record_decision("V2", "rejected", reviewer_id="bob@corp.com", note="Bad data", base_dir=td)
    check("Rejected decision", rec["decision"] == "rejected")
    check("Rejected note", rec["note"] == "Bad data")


# ---------------------------------------------------------------------------
# 3. record_decision — validation
# ---------------------------------------------------------------------------
section("record_decision: validation")

with tempfile.TemporaryDirectory() as td:
    try:
        record_decision("V3", "maybe", base_dir=td)
        check("Invalid decision raises ValueError", False, "No exception")
    except ValueError:
        check("Invalid decision raises ValueError", True)

    try:
        record_decision("V4", "", base_dir=td)
        check("Empty string raises ValueError", False, "No exception")
    except ValueError:
        check("Empty string raises ValueError", True)


# ---------------------------------------------------------------------------
# 4. record_decision — overwrite
# ---------------------------------------------------------------------------
section("record_decision: overwrite")

with tempfile.TemporaryDirectory() as td:
    record_decision("V5", "approved", note="first", base_dir=td)
    record_decision("V5", "rejected", note="second", base_dir=td)
    rec = read_decision_record("V5", base_dir=td)
    check("Overwrite: latest wins", rec["decision"] == "rejected" and rec["note"] == "second")


# ---------------------------------------------------------------------------
# 5. read_decision_record — existing, missing, corrupt
# ---------------------------------------------------------------------------
section("read_decision_record")

with tempfile.TemporaryDirectory() as td:
    record_decision("V6", "approved", base_dir=td)
    rec = read_decision_record("V6", base_dir=td)
    check("Read existing: not None", rec is not None)
    check("Read existing: correct", rec["decision"] == "approved")

    rec_miss = read_decision_record("NONEXISTENT", base_dir=td)
    check("Read missing: None", rec_miss is None)

    # Corrupt file
    path = _decision_path("V_CORRUPT", td)
    path.write_text("not json {{{", encoding="utf-8")
    rec_corrupt = read_decision_record("V_CORRUPT", base_dir=td)
    check("Read corrupt: None", rec_corrupt is None)


# ---------------------------------------------------------------------------
# 6. get_audit_trail
# ---------------------------------------------------------------------------
section("get_audit_trail")

with tempfile.TemporaryDirectory() as td:
    trail_empty = get_audit_trail("V7", base_dir=td)
    check("Empty trail: []", trail_empty == [])

    record_decision("V7", "approved", reviewer_id="a", base_dir=td)
    record_decision("V7", "rejected", reviewer_id="b", base_dir=td)
    record_decision("V7", "approved", reviewer_id="c", base_dir=td)

    trail = get_audit_trail("V7", base_dir=td)
    check("Trail has 3 entries", len(trail) == 3)
    check("Trail ordered by time", [e["reviewer_id"] for e in trail] == ["a", "b", "c"])
    check("Trail has event field", trail[0].get("event") == "decision_recorded")
    check("Trail has timestamp", "timestamp" in trail[0])


# ---------------------------------------------------------------------------
# 7. apply_human_decision — A14 fields
# ---------------------------------------------------------------------------
section("apply_human_decision: A14 audit fields")

state_base = {"task_id": "V8", "acceptance_status": "human_required", "blocking_count": 0}

result = apply_human_decision(state_base, "approved", reviewer_id="dave@corp.com", note="All clear")
check("reviewer_id set", result["reviewer_id"] == "dave@corp.com")
check("decision_timestamp set", "T" in result["decision_timestamp"])
check("decision_note set", result["decision_note"] == "All clear")
check("human_gate_decision set", result["human_gate_decision"] == "approved")
check("error_message has note", "All clear" in result.get("error_message", ""))


# ---------------------------------------------------------------------------
# 8. apply_human_decision — persist=True
# ---------------------------------------------------------------------------
section("apply_human_decision: persist=True")

with tempfile.TemporaryDirectory() as td:
    state_persist = {"task_id": "V9", "acceptance_status": "human_required"}
    result_p = apply_human_decision(
        state_persist, "approved",
        reviewer_id="eve@corp.com",
        note="Verified",
        persist=True,
        base_dir=td,
    )
    check("persist: reviewer_id in state", result_p["reviewer_id"] == "eve@corp.com")

    rec_disk = read_decision_record("V9", base_dir=td)
    check("persist: file on disk", rec_disk is not None)
    check("persist: disk reviewer_id", rec_disk["reviewer_id"] == "eve@corp.com")
    check("persist: disk decision", rec_disk["decision"] == "approved")

    trail_disk = get_audit_trail("V9", base_dir=td)
    check("persist: audit trail entry", len(trail_disk) >= 1)


# ---------------------------------------------------------------------------
# 9. apply_human_decision — persist=False (no file)
# ---------------------------------------------------------------------------
section("apply_human_decision: persist=False")

with tempfile.TemporaryDirectory() as td:
    state_np = {"task_id": "V10"}
    apply_human_decision(state_np, "approved", persist=False)
    rec_np = read_decision_record("V10", base_dir=td)
    check("No persist: no file", rec_np is None)


# ---------------------------------------------------------------------------
# 10. human_gate_node — audit field population
# ---------------------------------------------------------------------------
section("human_gate_node: audit field population")

state_audit = {
    "human_gate_decision": "approved",
    "reviewer_id": "frank@corp.com",
    "decision_timestamp": "2026-06-11T12:00:00+00:00",
    "decision_note": "Manual review passed",
    "executed_nodes": [],
}
result_audit = human_gate_node(state_audit)
check("Node: reviewer_id propagated", result_audit["reviewer_id"] == "frank@corp.com")
check("Node: decision_timestamp propagated", result_audit["decision_timestamp"] == "2026-06-11T12:00:00+00:00")
check("Node: decision_note propagated", result_audit["decision_note"] == "Manual review passed")
check("Node: status=running", result_audit["status"] == "running")


# ---------------------------------------------------------------------------
# 11. human_gate_node — rejected audit fields
# ---------------------------------------------------------------------------
section("human_gate_node: rejected audit fields")

state_rej = {
    "human_gate_decision": "rejected",
    "reviewer_id": "grace@corp.com",
    "decision_timestamp": "2026-06-11T13:00:00+00:00",
    "decision_note": "Insufficient evidence",
    "executed_nodes": [],
}
result_rej = human_gate_node(state_rej)
check("Node rejected: reviewer_id", result_rej["reviewer_id"] == "grace@corp.com")
check("Node rejected: status=rejected", result_rej["status"] == "rejected")


# ---------------------------------------------------------------------------
# 12. human_gate_node — first-time (no audit fields)
# ---------------------------------------------------------------------------
section("human_gate_node: first-time (no audit)")

state_first = {"human_gate_decision": "", "executed_nodes": []}
result_first = human_gate_node(state_first)
check("First: reviewer_id empty", result_first.get("reviewer_id", "") == "")
check("First: decision=pending", result_first["human_gate_decision"] == "pending")


# ---------------------------------------------------------------------------
# 13. PaperWorkflowState — A14 fields exist
# ---------------------------------------------------------------------------
section("PaperWorkflowState: A14 fields")

pstate = PaperWorkflowState()
check("State has reviewer_id", hasattr(pstate, "reviewer_id"))
check("State has decision_timestamp", hasattr(pstate, "decision_timestamp"))
check("State has decision_note", hasattr(pstate, "decision_note"))
check("State reviewer_id default empty", pstate.reviewer_id == "")
check("State decision_timestamp default empty", pstate.decision_timestamp == "")
check("State decision_note default empty", pstate.decision_note == "")


# ---------------------------------------------------------------------------
# 14. log_decision_audit — best-effort (no crash)
# ---------------------------------------------------------------------------
section("log_decision_audit: best-effort")

try:
    log_decision_audit(
        task_id="V11",
        decision="approved",
        reviewer_id="hank@corp.com",
        note="Test audit",
    )
    check("log_decision_audit: no crash", True)
except Exception:
    check("log_decision_audit: no crash", False, "Raised exception")


# ---------------------------------------------------------------------------
# 15. Graph resume with audit fields
# ---------------------------------------------------------------------------
section("Graph resume: audit fields propagate")

try:
    thread_id = "val-a14-audit"
    compiled = compile_paper_graph(thread_id)
    config = {"configurable": {"thread_id": thread_id}}

    from ai_workflow_hub.context_layer.adapters.paper_acceptance_gate import compute_acceptance

    issue_hr = {
        "issue_id": "HR1", "issue_type": "citation", "severity": "major",
        "message": "Needs human review", "paragraph_index": 0,
        "human_required": True,
    }
    ar = compute_acceptance(issues=[issue_hr], reviewer="writelab_adapter", evidence_pack_ref="")

    initial = {
        "writelab_mode": "mock",
        "paragraph_issues": [issue_hr],
        "all_review_issues": [issue_hr],
        "acceptance_result": ar,
        "acceptance_status": ar["status"],
    }

    # First invoke: pause
    r1 = compiled.invoke(initial, config)
    check("Graph: first invoke pauses", r1["status"] == "human_required")

    # Resume with audit fields
    updated = apply_human_decision(
        r1, "approved",
        reviewer_id="iris@corp.com",
        note="Reviewed and approved",
    )
    r2 = compiled.invoke(updated, config)

    check("Graph: reviewer_id in result", r2.get("reviewer_id") == "iris@corp.com")
    check("Graph: decision_note in result", r2.get("decision_note") == "Reviewed and approved")
    check("Graph: decision_timestamp present", r2.get("decision_timestamp", "") != "")
    check("Graph: reaches finalizer", "paper_finalizer_node" in r2.get("executed_nodes", []))

except Exception as e:
    check("Graph resume with audit", False, f"{e}\n{traceback.format_exc()}")


# ---------------------------------------------------------------------------
# 16. Constants
# ---------------------------------------------------------------------------
section("Constants")

check("VALID_DECISIONS", VALID_DECISIONS == {"approved", "rejected"})
check("DECISION_SCHEMA_VERSION", DECISION_SCHEMA_VERSION == "1.0")


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
RESULTS.append(f"\n{'='*50}")
RESULTS.append(f"A14 Validation: {PASS} passed, {FAIL} failed, {PASS+FAIL} total")
RESULTS.append(f"{'='*50}")

output = "\n".join(RESULTS)
print(output)

if FAIL > 0:
    sys.exit(1)
