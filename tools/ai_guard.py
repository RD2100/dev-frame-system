#!/usr/bin/env python3
import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone


def capture(command: str) -> dict:
    generated_at = datetime.now(timezone.utc).isoformat()
    try:
        proc = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            check=False,
        )
        return {
            "generated_at": generated_at,
            "producer": "ai_guard.py",
            "command": command,
            "exit_code": proc.returncode,
            "stdout": proc.stdout,
            "stderr": proc.stderr,
        }
    except Exception as exc:
        return {
            "generated_at": generated_at,
            "producer": "ai_guard.py",
            "command": command,
            "exit_code": 1,
            "stdout": "",
            "stderr": str(exc),
        }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Deterministic safety capture tool")
    parser.add_argument("command", help="Shell command to capture")
    parser.add_argument(
        "--output",
        default="safety-report.json",
        help="Output path for safety-report.json",
    )
    args = parser.parse_args(argv)

    report = capture(args.command)
    os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2)
        fh.write("\n")
    return report["exit_code"]


if __name__ == "__main__":
    sys.exit(main())
