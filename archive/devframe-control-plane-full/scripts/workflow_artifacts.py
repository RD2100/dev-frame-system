#!/usr/bin/env python3
"""workflow_artifacts.py — Save and retrieve workflow run artifacts."""
import json, hashlib, sys
from datetime import datetime, timezone
from pathlib import Path

CTRL = Path(__file__).resolve().parent.parent
ARTIFACTS = CTRL / "artifacts"
ARTIFACTS.mkdir(exist_ok=True)

def save(run_name, data):
    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    file = ARTIFACTS / f"{run_name}-{ts}.json"
    record = {"run": run_name, "timestamp": ts, "data": data, "sha256": hashlib.sha256(json.dumps(data).encode()).hexdigest()}
    file.write_text(json.dumps(record, indent=2, ensure_ascii=False))
    return str(file)

def list_runs():
    return sorted([f.name for f in ARTIFACTS.glob("*.json")])

def latest(run_name=None):
    files = sorted(ARTIFACTS.glob("*.json"), reverse=True)
    if run_name:
        files = [f for f in files if f.name.startswith(run_name)]
    return json.loads(files[0].read_text()) if files else None

def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "list"
    if cmd == "list":
        for f in list_runs(): print(f"  {f}")
    elif cmd == "latest":
        r = latest(sys.argv[2] if len(sys.argv) > 2 else None)
        print(json.dumps(r, indent=2) if r else "no artifacts")
    elif cmd == "save":
        if len(sys.argv) < 3: print("Usage: save <name>"); sys.exit(1)
        data = json.loads(sys.stdin.read()) if not sys.stdin.isatty() else {"status": "manual"}
        print(save(sys.argv[2], data))
    else:
        print(f"Unknown: {cmd}"); sys.exit(1)

if __name__ == "__main__":
    main()
