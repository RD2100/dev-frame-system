#!/usr/bin/env python3
import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone


REQUIRED_FILES = [
    "diff.patch",
    "test-output.md",
    "safety-report.json",
    "chain-evidence.json",
    "review.md",
    "review.yaml",
]
REQUIRED_INPUTS = [
    "diff.patch",
    "test-output.md",
    "safety-report.json",
    "chain-evidence.json",
]
FULL_EVIDENCE_FILES = REQUIRED_FILES + ["final-report.md"]
BLOCKED_ROLES = {"executor", "fixer", "coder"}
ALLOWED_VERDICTS = {"pass", "blocked", "fail", "escalate"}


def parse_review_yaml(path: str) -> dict:
    try:
        import yaml
    except ImportError:
        yaml = None

    if yaml is not None:
        with open(path, "r", encoding="utf-8") as fh:
            return yaml.safe_load(fh) or {}

    # Minimal fallback parser
    with open(path, "r", encoding="utf-8") as fh:
        text = fh.read()

    data = {}
    for line in text.splitlines():
        line = line.strip()
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key in ("reviewer_role", "reviewer_id", "executor_id", "verdict"):
            data[key] = value
        elif key == "reviewed_inputs":
            data[key] = [item.strip().strip("- ").strip('"').strip("'") for item in value.split(",")]
    return data


def validate(evidence_dir: str):
    missing = [name for name in REQUIRED_FILES if not os.path.exists(os.path.join(evidence_dir, name))]
    if missing:
        return "blocked", f"missing required files: {', '.join(missing)}", {}

    review = parse_review_yaml(os.path.join(evidence_dir, "review.yaml"))

    role = review.get("reviewer_role", "")
    if not role or role.lower() in BLOCKED_ROLES:
        return "blocked", f"reviewer_role '{role}' is not allowed", review

    reviewed = [item.strip() for item in review.get("reviewed_inputs", [])]
    missing_inputs = [name for name in REQUIRED_INPUTS if name not in reviewed]
    if missing_inputs:
        return "blocked", f"reviewed_inputs missing: {', '.join(missing_inputs)}", review

    verdict = review.get("verdict", "")
    if verdict not in ALLOWED_VERDICTS:
        return "blocked", f"verdict '{verdict}' is not allowed", review

    findings = review.get("findings", []) or []
    for finding in findings:
        severity = str(finding.get("severity", "")).upper()
        status = str(finding.get("status", "")).lower()
        if severity in {"P0", "P1"} and status == "open":
            return "blocked", f"open {severity} finding: {finding.get('id', 'unknown')}", review

    if verdict != "pass":
        return "fail" if verdict == "fail" else "blocked", f"verdict is '{verdict}'", review

    return "pass", "ok", review


def write_final_report(evidence_dir: str, status: str, reason: str, review: dict) -> str:
    report_path = os.path.join(evidence_dir, "final-report.md")
    generated_at = datetime.now(timezone.utc).isoformat()
    content = f"""# Final Report

- **Generated At**: {generated_at}
- **Status**: {status}
- **Reason**: {reason}

## Reviewer Summary

- **Reviewer Role**: {review.get('reviewer_role', 'N/A')}
- **Reviewer ID**: {review.get('reviewer_id', 'N/A')}
- **Executor ID**: {review.get('executor_id', 'N/A')}
- **Verdict**: {review.get('verdict', 'N/A')}

## Evidence Files

- diff.patch: {'present' if os.path.exists(os.path.join(evidence_dir, 'diff.patch')) else 'missing'}
- test-output.md: {'present' if os.path.exists(os.path.join(evidence_dir, 'test-output.md')) else 'missing'}
- safety-report.json: {'present' if os.path.exists(os.path.join(evidence_dir, 'safety-report.json')) else 'missing'}
- chain-evidence.json: {'present' if os.path.exists(os.path.join(evidence_dir, 'chain-evidence.json')) else 'missing'}
- review.md: {'present' if os.path.exists(os.path.join(evidence_dir, 'review.md')) else 'missing'}
- review.yaml: {'present' if os.path.exists(os.path.join(evidence_dir, 'review.yaml')) else 'missing'}
"""
    with open(report_path, "w", encoding="utf-8") as fh:
        fh.write(content)
    return report_path


def init_chain_evidence(run_evidence_dir: str, run_id: str, executor_id: str, mode: str | None = None, planner: str | None = None, task: str | None = None) -> str:
    os.makedirs(run_evidence_dir, exist_ok=True)
    evidence = {
        "run_id": run_id,
        "executor_id": executor_id,
        "mode": mode,
        "planner": planner,
        "task": task,
        "evidence_files": FULL_EVIDENCE_FILES[:],
        "timestamps": {
            "created_at": datetime.now(timezone.utc).isoformat(),
        },
    }
    path = os.path.join(run_evidence_dir, "chain-evidence.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(evidence, fh, indent=2)
        fh.write("\n")
    return path


def guard(run_evidence_dir: str, command: str) -> dict:
    generated_at = datetime.now(timezone.utc).isoformat()
    try:
        proc = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            check=False,
        )
        report = {
            "generated_at": generated_at,
            "producer": "go_evidence.py",
            "command": command,
            "exit_code": proc.returncode,
            "stdout": proc.stdout,
            "stderr": proc.stderr,
        }
    except Exception as exc:
        report = {
            "generated_at": generated_at,
            "producer": "go_evidence.py",
            "command": command,
            "exit_code": 1,
            "stdout": "",
            "stderr": str(exc),
        }

    os.makedirs(run_evidence_dir, exist_ok=True)
    report_path = os.path.join(run_evidence_dir, "safety-report.json")
    with open(report_path, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2)
        fh.write("\n")
    return report


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="SADP evidence tool")
    subparsers = parser.add_subparsers(dest="command")

    finalize_parser = subparsers.add_parser("finalize", help="Finalize evidence")
    finalize_parser.add_argument("run_evidence_dir", help="Path to run evidence directory")

    init_parser = subparsers.add_parser("init", help="Initialize run evidence")
    init_parser.add_argument("run_evidence_dir", help="Path to run evidence directory")
    init_parser.add_argument("--run-id", required=True, help="Run identifier")
    init_parser.add_argument("--executor-id", required=True, help="Executor identifier")
    init_parser.add_argument("--mode", default=None, help="Execution mode")
    init_parser.add_argument("--planner", default=None, help="Planner identifier")
    init_parser.add_argument("--task", default=None, help="Task path")

    guard_parser = subparsers.add_parser("guard", help="Guard a command")
    guard_parser.add_argument("run_evidence_dir", help="Path to run evidence directory")
    guard_parser.add_argument("--command", dest="guard_cmd", default=None, help="Command to guard (preferred)")
    guard_parser.add_argument("--cmd", dest="guard_cmd", default=None, help="Command to guard (backward-compatible alias)")

    args = parser.parse_args(argv)

    if args.command == "finalize":
        if not os.path.isdir(args.run_evidence_dir):
            print(f"evidence directory not found: {args.run_evidence_dir}", file=sys.stderr)
            return 2

        status, reason, review = validate(args.run_evidence_dir)
        write_final_report(args.run_evidence_dir, status, reason, review)

        print(status.upper())
        if status != "pass":
            print(reason, file=sys.stderr)
            return 1
        return 0

    if args.command == "init":
        init_chain_evidence(
            args.run_evidence_dir,
            args.run_id,
            args.executor_id,
            mode=args.mode,
            planner=args.planner,
            task=args.task,
        )
        return 0

    if args.command == "guard":
        command = args.guard_cmd
        if not command:
            print("guard requires --command or --cmd", file=sys.stderr)
            return 2
        report = guard(args.run_evidence_dir, command)
        return report.get("exit_code", 1)

    print(f"unknown command: {args.command}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
