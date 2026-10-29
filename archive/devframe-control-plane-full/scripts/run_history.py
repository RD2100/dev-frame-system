#!/usr/bin/env python3
"""run_history.py — Workflow run history tracker."""
import json, sys
from datetime import datetime, timezone
from pathlib import Path
CTRL = Path(__file__).resolve().parent.parent
HISTORY = CTRL / "artifacts" / "run_history.jsonl"

def log(workflow, status, details=""):
    entry = {"workflow": workflow, "status": status, "timestamp": datetime.now(timezone.utc).isoformat(), "details": details}
    with open(HISTORY, "a") as f: f.write(json.dumps(entry) + "\n")
    return entry

def tail(n=5):
    if not HISTORY.exists(): return []
    lines = HISTORY.read_text().strip().split("\n")[-n:]
    return [json.loads(l) for l in lines if l.strip()]

def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "tail"
    if cmd == "log":
        log(sys.argv[2] if len(sys.argv) > 2 else "manual", sys.argv[3] if len(sys.argv) > 3 else "PASS")
        print("logged")
    elif cmd == "tail":
        for e in tail(int(sys.argv[2]) if len(sys.argv) > 2 else 5):
            print(f"  [{e['status']}] {e['workflow']} @ {e['timestamp'][:19]}")
    else: print("Usage: log|tail [n]")
if __name__ == "__main__": main()
