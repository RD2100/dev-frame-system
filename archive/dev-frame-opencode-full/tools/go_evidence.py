#!/usr/bin/env python3
"""
go_evidence.py — Verify evidence integrity and replay status synthesis.

Two modes:
  --verify  : Check evidence artifacts exist, validate schemas,
              distinguish reviewer_invalid/reviewer_rejected/reviewer_timeout.
  --replay  : Re-run synthesis to confirm deterministic output.

Usage:
  python tools/go_evidence.py <run_dir> --verify
  python tools/go_evidence.py <run_dir> --replay
  python tools/go_evidence.py <run_dir> --all
  python tools/go_evidence.py --help
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Optional

import yaml

# Reuse ai_guard synthesis engine
from ai_guard import (
    synthesize,
    validate_result,
    generate_report,
    extract_reviewer_verdict,
    extract_human_required,
    VALID_BLOCK_CATEGORIES,
    VALID_BLOCK_REASONS,
)

# ── file readers (same as ai_guard) ─────────────────────────────────

def read_json(path: Path) -> Optional[dict]:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (json.JSONDecodeError, UnicodeDecodeError, OSError):
        return None


def read_yaml(path: Path) -> Optional[dict]:
    if not path.exists():
        return None
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8"))
    except (yaml.YAMLError, UnicodeDecodeError, OSError):
        return None


def read_text(path: Path) -> Optional[str]:
    if not path.exists():
        return None
    try:
        return path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return None


# ── verify mode ─────────────────────────────────────────────────────

def verify_evidence(run_dir: Path) -> dict:
    """
    Verify evidence integrity for a run directory.

    Checks:
      - chain-evidence.json presence and schema
      - review.yaml presence and validity
      - reviewer verdict classification (invalid/rejected/timeout)
      - Evidence artifact cross-references
    """
    findings = {
        "run_dir": str(run_dir),
        "artifacts": {},
        "reviewer_classification": {},
        "issues": [],
        "verdict": "undetermined",
    }

    # 1. chain-evidence.json
    chain = read_json(run_dir / "chain-evidence.json")
    findings["artifacts"]["chain-evidence.json"] = {
        "present": chain is not None,
        "valid": False,
        "has_run_id": False,
        "has_task_id": False,
    }
    if chain is not None:
        findings["artifacts"]["chain-evidence.json"]["valid"] = True
        findings["artifacts"]["chain-evidence.json"]["has_run_id"] = bool(chain.get("run_id"))
        findings["artifacts"]["chain-evidence.json"]["has_task_id"] = bool(chain.get("task_id"))

    # 2. state.json
    state = read_json(run_dir / "state.json")
    findings["artifacts"]["state.json"] = {
        "present": state is not None,
        "has_evidence_ok": False,
        "evidence_ok_value": None,
    }
    if state is not None and "evidence_ok" in state:
        findings["artifacts"]["state.json"]["has_evidence_ok"] = True
        findings["artifacts"]["state.json"]["evidence_ok_value"] = state["evidence_ok"]

    # 3. review.yaml
    review = read_yaml(run_dir / "review.yaml")
    findings["artifacts"]["review.yaml"] = {
        "present": review is not None,
        "valid_schema": False,
        "format": None,
    }
    if review is not None and isinstance(review, dict):
        if "passed" in review:
            findings["artifacts"]["review.yaml"]["format"] = "model-parsed"
            findings["artifacts"]["review.yaml"]["valid_schema"] = isinstance(review.get("passed"), bool)
            findings["artifacts"]["review.yaml"]["passed_value"] = review.get("passed")
            findings["artifacts"]["review.yaml"]["recommendation"] = review.get("recommendation")
        elif "verdict" in review:
            findings["artifacts"]["review.yaml"]["format"] = "human-written"
            findings["artifacts"]["review.yaml"]["valid_schema"] = review.get("verdict") in ("pass", "fail", "blocked", "rejected")
            findings["artifacts"]["review.yaml"]["verdict_value"] = review.get("verdict")
            findings["artifacts"]["review.yaml"]["findings_count"] = len(review.get("findings", []))
        else:
            findings["artifacts"]["review.yaml"]["format"] = "unknown"

    # 4. Reviewer classification (invalid vs rejected vs timeout)
    reviewer_verdict, _ = extract_reviewer_verdict(run_dir)
    findings["reviewer_classification"] = {
        "verdict": reviewer_verdict,
        "is_invalid": reviewer_verdict == "reviewer_invalid",
        "is_rejected": reviewer_verdict == "reviewer_rejected",
        "is_timeout": reviewer_verdict == "reviewer_timeout",
        "is_pass": reviewer_verdict == "pass",
        "is_not_applicable": reviewer_verdict == "not_applicable",
    }

    # 5. human_required check
    human_required, _ = extract_human_required(run_dir)
    findings["human_required"] = human_required
    if human_required:
        findings["issues"].append({
            "severity": "blocking",
            "message": "human_required flag set without explicit approval",
            "category": "policy/blocking",
            "reason": "human_required",
        })

    # 6. Supporting artifacts
    for name in ["review.md", "review-issues.json", "final-report.md", "task-spec.yaml",
                  "diff.patch", "test-output.md", "state.json"]:
        path = run_dir / name
        if path.exists():
            findings["artifacts"][name] = {"present": True}
        # Don't report absent supporting artifacts as issues — focus on core artifacts

    # 7. Cross-reference checks
    if findings["artifacts"]["chain-evidence.json"]["present"]:
        if not findings["artifacts"]["chain-evidence.json"]["has_run_id"]:
            findings["issues"].append("chain-evidence.json missing run_id")

    if findings["artifacts"]["review.yaml"]["present"]:
        if not findings["artifacts"]["review.yaml"]["valid_schema"]:
            findings["issues"].append({
                "severity": "fail",
                "message": "review.yaml present but schema invalid",
                "classification": reviewer_verdict,
            })

    if reviewer_verdict == "reviewer_invalid":
        findings["issues"].append({
            "severity": "blocking",
            "message": "reviewer artifact exists but is invalid/unparseable",
            "details": "Cannot derive machine-readable verdict from review.yaml",
        })
    elif reviewer_verdict == "reviewer_timeout":
        findings["issues"].append({
            "severity": "blocking",
            "message": "no reviewer artifact produced — fail-closed timeout",
        })

    # 8. Final verdict
    has_blocking = any(
        isinstance(i, dict) and i.get("severity") in ("fail", "blocking")
        for i in findings["issues"]
    )
    findings["verdict"] = "blocked" if has_blocking else "pass"

    return findings


# ── replay mode ─────────────────────────────────────────────────────

def replay_synthesis(run_dir: Path) -> dict:
    """
    Re-run synthesis to confirm deterministic output.

    Runs synthesize() twice and compares results.
    """
    result1 = synthesize(run_dir)
    result2 = synthesize(run_dir)

    identical = json.dumps(result1, sort_keys=True) == json.dumps(result2, sort_keys=True)

    return {
        "run_dir": str(run_dir),
        "deterministic": identical,
        "pass1": result1,
        "pass2": result2,
        "final_batch_status": result1["final_batch_status"],
        "blocked_by": result1["blocked_by"],
        "source_status": result1["source_status"],
    }


# ── CLI ─────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Verify evidence integrity and replay status synthesis."
    )
    parser.add_argument(
        "run_dir",
        help="Path to run directory",
    )
    parser.add_argument(
        "--verify", "-V",
        action="store_true",
        help="Run evidence integrity verification",
    )
    parser.add_argument(
        "--replay", "-R",
        action="store_true",
        help="Re-run synthesis to confirm deterministic output",
    )
    parser.add_argument(
        "--all", "-A",
        action="store_true",
        help="Run both verify and replay",
    )
    parser.add_argument(
        "--output", "-o",
        choices=["json", "text"],
        default="json",
        help="Output format (default: json)",
    )
    args = parser.parse_args()

    run_dir = Path(args.run_dir)
    if not run_dir.is_dir():
        print("ERROR: run_dir not found: " + str(run_dir), file=sys.stderr)
        sys.exit(2)

    do_verify = args.verify or args.all
    do_replay = args.replay or args.all

    if not do_verify and not do_replay:
        parser.print_help()
        print("\nERROR: at least one of --verify, --replay, --all is required", file=sys.stderr)
        sys.exit(2)

    output = {}

    if do_verify:
        verify_result = verify_evidence(run_dir)
        output["verify"] = verify_result

    if do_replay:
        replay_result = replay_synthesis(run_dir)
        output["replay"] = replay_result

    # Summary
    if do_verify and do_replay:
        v_pass = output["verify"]["verdict"] == "pass"
        r_det = output["replay"]["deterministic"]
        r_status = output["replay"]["final_batch_status"]
        output["summary"] = {
            "verify_passed": v_pass,
            "replay_deterministic": r_det,
            "final_batch_status": r_status,
        }

    if args.output == "json":
        print(json.dumps(output, indent=2, ensure_ascii=False))
    else:
        _print_text(output)

    # Exit codes
    if do_verify and output["verify"]["verdict"] != "pass":
        sys.exit(1)
    if do_replay and not output["replay"]["deterministic"]:
        sys.exit(2)
    sys.exit(0)


def _print_text(output: dict):
    """Human-readable text output."""
    if "verify" in output:
        v = output["verify"]
        print("[verify] run_dir: " + v["run_dir"])
        print("[verify] verdict: " + v["verdict"])
        print("[verify] reviewer classification: " + v["reviewer_classification"]["verdict"])
        for issue in v.get("issues", []):
            if isinstance(issue, str):
                print("  - " + issue)
            else:
                print("  - [" + issue.get("severity", "?") + "] " + issue.get("message", ""))
        for name, info in v.get("artifacts", {}).items():
            status = "OK" if info.get("present") else "MISSING"
            extra = ""
            if info.get("valid_schema") is False:
                extra = " (INVALID SCHEMA)"
            print("  artifact: " + name + " -> " + status + extra)

    if "replay" in output:
        r = output["replay"]
        print("[replay] deterministic: " + str(r["deterministic"]))
        print("[replay] final_batch_status: " + r["final_batch_status"])
        print("[replay] blocked_by: " + json.dumps(r["blocked_by"]))
        print("[replay] source_status: " + json.dumps(r["source_status"]))

    if "summary" in output:
        s = output["summary"]
        print("[summary] verify_passed: " + str(s["verify_passed"]))
        print("[summary] replay_deterministic: " + str(s["replay_deterministic"]))
        print("[summary] final_batch_status: " + s["final_batch_status"])


if __name__ == "__main__":
    main()
