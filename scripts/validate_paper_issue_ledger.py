"""validate_paper_issue_ledger.py — A11 Validation Script.

Validates the Paper Issue Ledger implementation:
  1. Module structure
  2. Ingestion
  3. Query
  4. Status updates
  5. Batch operations
  6. Learning / patterns
  7. Integration with A8/A9
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
print("A11 Validation: Paper Issue Ledger")
print("=" * 60)

# ---------------------------------------------------------------------------
print("\n[1] Module Structure")
# ---------------------------------------------------------------------------
mod_path = SRC_DIR / "context_layer" / "adapters" / "paper_issue_ledger.py"
check("paper_issue_ledger.py exists", mod_path.exists())

try:
    sys.path.insert(0, str(HUB_DIR / "src"))
    mod = importlib.import_module("ai_workflow_hub.context_layer.adapters.paper_issue_ledger")
    check("module importable", True)
except Exception as e:
    check("module importable", False, str(e))
    sys.exit(1)

tmp = Path(tempfile.mkdtemp())

# ---------------------------------------------------------------------------
print("[2] Ingestion")
# ---------------------------------------------------------------------------
def make_issue(iid, blocking=False, severity="minor", issue_type="expression"):
    return {"issue_id": iid, "issue_type": issue_type, "severity": severity,
            "evidence": "test", "blocking": blocking, "recommendation": "fix",
            "human_required": False}

added = mod.ingest_issues("v1", [make_issue("a"), make_issue("b")], ledger_dir=tmp)
check("ingest 2 issues", added == 2)

added2 = mod.ingest_issues("v1", [make_issue("b"), make_issue("c")], ledger_dir=tmp)
check("no duplicate ingestion", added2 == 1)
check("total entries = 3", len(mod.get_all_issues("v1", ledger_dir=tmp)) == 3)

# ---------------------------------------------------------------------------
print("[3] Query")
# ---------------------------------------------------------------------------
check("open issues = 3", len(mod.get_open_issues("v1", ledger_dir=tmp)) == 3)
check("blocking_count = 0", mod.blocking_count("v1", ledger_dir=tmp) == 0)

mod.ingest_issues("v2", [make_issue("b1", blocking=True, severity="critical")], ledger_dir=tmp)
check("blocking_count with blocking", mod.blocking_count("v2", ledger_dir=tmp) == 1)
check("critical_count", mod.critical_count("v2", ledger_dir=tmp) == 1)
check("is_clear = False with blocking", not mod.is_clear("v2", ledger_dir=tmp))
check("is_clear = True empty", mod.is_clear("empty-task", ledger_dir=tmp))

# ---------------------------------------------------------------------------
print("[4] Status Updates")
# ---------------------------------------------------------------------------
check("mark_resolved returns True", mod.mark_resolved("v1", "a", ledger_dir=tmp))
check("resolved issue not in open", len(mod.get_open_issues("v1", ledger_dir=tmp)) == 2)
check("mark_wontfix", mod.mark_wontfix("v1", "b", ledger_dir=tmp))
check("reopen_issue", mod.reopen_issue("v1", "b", ledger_dir=tmp))

# ---------------------------------------------------------------------------
print("[5] Summary")
# ---------------------------------------------------------------------------
s = mod.ledger_summary("v1", ledger_dir=tmp)
check("summary total=3", s["total"] == 3)
check("summary open=2", s["open"] == 2)
check("summary resolved=1", s["resolved"] == 1)

# ---------------------------------------------------------------------------
print("[6] Learning / Patterns")
# ---------------------------------------------------------------------------
mod.ingest_issues("learn", [
    make_issue("e1", issue_type="expression"),
    make_issue("e2", issue_type="expression"),
    make_issue("c1", issue_type="citation"),
], ledger_dir=tmp)
mod.mark_resolved("learn", "e1", ledger_dir=tmp)

freq = mod.issue_type_frequency("learn", ledger_dir=tmp)
check("frequency expression total=2", freq["expression"]["total"] == 2)
check("frequency expression resolved=1", freq["expression"]["resolved"] == 1)

ctx = mod.build_prompt_context("v2", ledger_dir=tmp)
check("prompt_context contains blocking", "Blocking" in ctx or "blocking" in ctx.lower())

# ---------------------------------------------------------------------------
print("[7] Integration with A8")
# ---------------------------------------------------------------------------
ar = {
    "status": "blocked",
    "reasons": ["test"],
    "blocking_issues": [make_issue("ar-b1", blocking=True, severity="critical")],
    "non_blocking_issues": [make_issue("ar-nb1"), make_issue("ar-nb2")],
    "required_next_actions": [],
    "reviewer": "writelab_adapter",
    "evidence_pack_ref": "ep-integration",
}
added = mod.ingest_from_acceptance_result("integration", ar, ledger_dir=tmp)
check("ingest_from_acceptance: 3 added", added == 3)
check("integration blocking_count=1", mod.blocking_count("integration", ledger_dir=tmp) == 1)

mod.mark_resolved("integration", "ar-b1", note="Fixed", ledger_dir=tmp)
check("after resolve: is_clear", mod.is_clear("integration", ledger_dir=tmp))

# ---------------------------------------------------------------------------
print("[8] Test Suite")
# ---------------------------------------------------------------------------
test_file = HUB_DIR / "tests" / "test_paper_issue_ledger.py"
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

output_path = Path(__file__).resolve().parent / "VALIDATION_OUTPUT_A11.txt"
with open(output_path, "w") as f:
    f.write(f"A11 Validation: {PASS} passed, {FAIL} failed\n")
    f.write("=" * 60 + "\n")
    for r in results:
        f.write(r + "\n")
    if "test_output" in dir():
        f.write("\n--- Test Suite Output ---\n")
        f.write(test_output)
print(f"\nOutput saved to: {output_path}")

sys.exit(0 if FAIL == 0 else 1)
