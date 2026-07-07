#!/usr/bin/env python3
import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
CONTROL_PLANE_PATH = REPO_ROOT / "packages" / "control-plane"
if str(CONTROL_PLANE_PATH) not in sys.path:
    sys.path.insert(0, str(CONTROL_PLANE_PATH))

from control_plane.evidence_gate import (  # noqa: E402
    FULL_EVIDENCE_FILES,
    REQUIRED_FILES,
    REQUIRED_INPUTS,
    ALLOWED_VERDICTS,
    BLOCKED_ROLES,
    build_evidence_manifest,
    build_failure_record,
    build_final_verdict,
    evaluate_evidence_dir,
    parse_review_yaml,
    write_json,
)

def validate(evidence_dir: str):
    result = evaluate_evidence_dir(evidence_dir)
    return result.status, result.reason, result.review


def write_final_report(evidence_dir: str, status: str, reason: str, review: dict, artifacts: dict | None = None) -> str:
    report_path = os.path.join(evidence_dir, "final-report.md")
    generated_at = datetime.now(timezone.utc).isoformat()
    artifacts = artifacts or {}
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

## Machine Artifacts

- evidence-manifest.json: {'present' if artifacts.get('evidence_manifest') else 'missing'}
- final-verdict.json: {'present' if artifacts.get('final_verdict') else 'missing'}
- failure-record.json: {'present' if artifacts.get('failure_record') else 'not applicable'}
"""
    with open(report_path, "w", encoding="utf-8") as fh:
        fh.write(content)
    return report_path


def write_governance_artifacts(evidence_dir: str):
    result = evaluate_evidence_dir(evidence_dir)
    generated_at = datetime.now(timezone.utc).isoformat()
    final_verdict = build_final_verdict(evidence_dir, result, generated_at)
    artifacts = {
        "final_verdict": write_json(os.path.join(evidence_dir, "final-verdict.json"), final_verdict),
        "evidence_manifest": os.path.join(evidence_dir, "evidence-manifest.json"),
    }
    if result.status != "pass":
        failure_record = build_failure_record(evidence_dir, result, generated_at)
        artifacts["failure_record"] = write_json(os.path.join(evidence_dir, "failure-record.json"), failure_record)
    write_final_report(
        evidence_dir,
        result.status,
        result.reason,
        result.review,
        artifacts,
    )
    manifest_path = os.path.join(evidence_dir, "evidence-manifest.json")
    write_json(manifest_path, build_evidence_manifest(evidence_dir, result, generated_at))
    artifacts["evidence_manifest"] = write_json(
        manifest_path,
        build_evidence_manifest(evidence_dir, result, generated_at),
    )
    return result, artifacts


def init_chain_evidence(run_evidence_dir: str, run_id: str, executor_id: str, mode: str | None = None, planner: str | None = None, task: str | None = None, methodology: dict | None = None) -> str:
    os.makedirs(run_evidence_dir, exist_ok=True)
    evidence = {
        "run_id": run_id,
        "executor_id": executor_id,
        "mode": mode,
        "planner": planner,
        "task": task,
        "methodology": methodology,
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

        result, _artifacts = write_governance_artifacts(args.run_evidence_dir)

        print(result.status.upper())
        if result.status != "pass":
            print(result.reason, file=sys.stderr)
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
