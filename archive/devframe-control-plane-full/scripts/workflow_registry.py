#!/usr/bin/env python3
"""workflow_registry.py — Discover and list available DevFrame workflows."""
import json, sys
from pathlib import Path

CTRL = Path(__file__).resolve().parent.parent
REGISTRY = {
    "generic": {"script": "scripts/generic_workflow.py", "desc": "Cross-repo health: tests + guard + smoke"},
    "paper_synthetic": {"repo": "D:/agent-acceptance", "script": "scripts/paper_pilot_runner.py", "desc": "Synthetic paper pilot (synthetic-only)"},
    "paper_preflight": {"repo": "D:/agent-acceptance", "script": "scripts/paper_pilot_preflight.py", "desc": "Paper pilot preflight checker"},
    "smoke": {"repo": "D:/agent-acceptance", "script": "scripts/smoke_suite.py", "desc": "Agent-acceptance smoke suite (9 checks)"},
    "pre_push": {"repo": "D:/agent-acceptance", "script": "scripts/pre_push_verify.py", "desc": "Pre-push verification (5 checks)"},
}

def main():
    if len(sys.argv) > 1:
        cmd = sys.argv[1]
        if cmd == "list":
            for name, info in sorted(REGISTRY.items()):
                print(f"  {name}: {info['desc']}")
        elif cmd in REGISTRY:
            info = REGISTRY[cmd]
            repo = Path(info.get("repo", str(CTRL)))
            import subprocess
            r = subprocess.run([sys.executable, info["script"]], cwd=str(repo))
            sys.exit(r.returncode)
        else:
            print(f"Unknown: {cmd}")
            sys.exit(1)
    else:
        print(json.dumps({"workflows": sorted(REGISTRY.keys()), "count": len(REGISTRY)}, indent=2))

if __name__ == "__main__":
    main()
