#!/usr/bin/env python3
"""devframe_cli.py — DevFrame Control Plane CLI entry point."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent / "scripts"))
from workflow_registry import REGISTRY, main as registry_main

HELP = """DevFrame Control Plane CLI
  devframe run <workflow>   Run a workflow (see list)
  devframe list             List available workflows
  devframe smoke            Run agent-acceptance smoke suite
  devframe status           Show cross-repo health
"""

def main():
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help"):
        print(HELP); return
    cmd = sys.argv[1]
    if cmd == "list":
        registry_main()
    elif cmd == "run":
        if len(sys.argv) < 3: print("Usage: devframe run <workflow>"); sys.exit(1)
        sys.argv = ["workflow_registry.py", sys.argv[2]]
        registry_main()
    elif cmd == "smoke":
        import subprocess
        subprocess.run([sys.executable, "D:/agent-acceptance/scripts/smoke_suite.py"])
    elif cmd == "status":
        import subprocess, json
        r = subprocess.run([sys.executable, "D:/agent-acceptance/scripts/smoke_suite.py"], capture_output=True, text=True)
        data = json.loads(r.stdout) if r.stdout.strip().startswith("{") else {"error": "parse failed"}
        print(f"agent-acceptance: {data.get('overall', '?')}")
        r2 = subprocess.run([sys.executable, "scripts/generic_workflow.py"], capture_output=True, text=True)
        print(f"control-plane: {'PASS' if r2.returncode==0 else 'KNOWN_ISSUES'}")
    else:
        print(f"Unknown: {cmd}"); print(HELP)

if __name__ == "__main__":
    main()
