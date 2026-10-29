#!/usr/bin/env python3
"""
generic_workflow.py — Generic reusable workflow runner for DevFrame control-plane.
Bridges agent-acceptance validation + GPT review + evidence collection into a single pipeline.
"""
import json, subprocess, sys
from datetime import datetime, timezone
from pathlib import Path

CTRL = Path(__file__).resolve().parent.parent
ACCEPTANCE = Path("D:/agent-acceptance")

PIPELINE = [
    ("verify_acceptance", "python -m pytest tests/ -q --tb=line", ACCEPTANCE),
    ("verify_control", "python -m pytest tests/ -q --tb=line", CTRL),
    ("ai_guard_check", "python tools/ai_guard.py task .ai/current-task.yaml", ACCEPTANCE),
    ("smoke_check", "python scripts/smoke_suite.py", ACCEPTANCE),
]

def main():
    results = {}
    for name, cmd, cwd in PIPELINE:
        print(f"\n[{name}] {cmd}")
        r = subprocess.run(cmd.split(), cwd=str(cwd), capture_output=True, text=True, timeout=120)
        results[name] = {"exit": r.returncode, "tail": (r.stdout or r.stderr).strip().split("\n")[-1]}
        print(f"  -> exit={r.returncode}")

    # All repos should pass (control-plane: 72 PASS as of 2026-06-08)
    all_ok = all(v["exit"] == 0 for v in results.values())
    for k, v in results.items():
        status = "PASS" if v["exit"] == 0 else "FAIL"
        v["status"] = status
    report = {"workflow": "generic-workflow-v1", "timestamp": datetime.now(timezone.utc).isoformat(), "overall": "PASS" if all_ok else "FAIL", "stages": results}
    print(f"\n{'='*40}\nWORKFLOW: {'PASS' if all_ok else 'FAIL'}")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    sys.exit(0 if all_ok else 1)

if __name__ == "__main__":
    main()
