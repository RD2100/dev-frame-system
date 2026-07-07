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
from control_plane.team_runtime import TeamRuntime  # noqa: E402

FINALIZATION_ARTIFACT_FILES = [
    ("evidence_manifest", "evidence-manifest.json"),
    ("final_verdict", "final-verdict.json"),
    ("failure_record", "failure-record.json"),
]


def validate(evidence_dir: str):
    result = evaluate_evidence_dir(evidence_dir)
    return result.status, result.reason, result.review


def write_final_report(evidence_dir: str, status: str, reason: str, review: dict, artifacts: dict | None = None, generated_at: str | None = None) -> str:
    report_path = os.path.join(evidence_dir, "final-report.md")
    generated_at = generated_at or datetime.now(timezone.utc).isoformat()
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
    if not os.path.exists(report_path) or Path(report_path).read_text(encoding="utf-8") != content:
        with open(report_path, "w", encoding="utf-8") as fh:
            fh.write(content)
    return report_path


def write_governance_artifacts(evidence_dir: str):
    result = evaluate_evidence_dir(evidence_dir)
    generated_at = datetime.now(timezone.utc).isoformat()
    final_verdict = build_final_verdict(evidence_dir, result, generated_at)
    previous_final_verdict = _load_json_file(os.path.join(evidence_dir, "final-verdict.json"))
    if _same_final_verdict_except_timestamp(previous_final_verdict, final_verdict):
        generated_at = str(previous_final_verdict["produced_at"])
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
        generated_at,
    )
    manifest_path = os.path.join(evidence_dir, "evidence-manifest.json")
    write_json(manifest_path, build_evidence_manifest(evidence_dir, result, generated_at))
    artifacts["evidence_manifest"] = write_json(
        manifest_path,
        build_evidence_manifest(evidence_dir, result, generated_at),
    )
    return result, artifacts


def _load_json_file(path: str) -> dict:
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _same_final_verdict_except_timestamp(previous: dict, current: dict) -> bool:
    if not previous or not previous.get("produced_at"):
        return False
    previous_normalized = dict(previous)
    current_normalized = dict(current)
    previous_normalized.pop("produced_at", None)
    current_normalized.pop("produced_at", None)
    return previous_normalized == current_normalized


def record_team_runtime_finalization(
    evidence_dir: str,
    result,
    artifacts: dict,
    runtime_dir: str,
    repo_root: str | None = None,
) -> list[str]:
    """Record a successful evidence finalization in the TeamRuntime journal.

    This is intentionally opt-in from the CLI. The evidence artifacts remain the
    source of truth; TeamRuntime only receives references to the review and final
    verdict artifacts after the evidence gate has passed.
    """
    evidence_path = Path(evidence_dir)
    team = TeamRuntime(runtime_dir=runtime_dir, repo_root=repo_root)
    event_ids: list[str] = []
    if result.status != "pass":
        event_ids.extend(_record_blocked_finalization_evidence_refs(team, evidence_path, result, artifacts))
        if not _can_record_non_pass_final_verdict_ref(result):
            return event_ids
    final_verdict_path = Path(
        str(artifacts.get("final_verdict") or evidence_path / "final-verdict.json")
    )
    final_verdict = json.loads(final_verdict_path.read_text(encoding="utf-8"))
    review = result.review
    chain = result.chain_evidence
    run_id = str(chain.get("run_id") or evidence_path.name or "unknown-run")
    reviewer_id = str(review.get("reviewer_id") or "missing-reviewer")
    review_id = f"review-{_safe_token(run_id)}-{_safe_token(reviewer_id)}"
    if _team_runtime_has_finalization_refs(
        team,
        run_id=run_id,
        review_id=review_id,
        review_ref_path=str(evidence_path / "review.yaml"),
        verdict_id=str(final_verdict.get("verdict_id") or ""),
        final_verdict_ref_path=str(final_verdict_path),
    ):
        return event_ids
    reviewed_inputs = [
        str(item) for item in review.get("reviewed_inputs", [])
        if str(item)
    ]
    reviewed_evidence_refs = [
        str(evidence_path / name)
        for name in REQUIRED_INPUTS
        if (evidence_path / name).exists()
    ]
    event_ids.append(
        team.record_review_ref(
            run_id,
            reviewer_id,
            review_id=review_id,
            reviewer_role=str(review.get("reviewer_role") or ""),
            executor_id=str(
                review.get("executor_id") or chain.get("executor_id") or ""
            ),
            verdict=str(review.get("verdict") or ""),
            ref_path=str(evidence_path / "review.yaml"),
            reviewed_evidence_refs=reviewed_evidence_refs,
            reviewed_inputs=reviewed_inputs,
            source="go_evidence_finalize",
        )
    )
    gate_refs = [
        str(item.get("gate_id") or "")
        for item in final_verdict.get("gate_summary", [])
        if isinstance(item, dict) and str(item.get("gate_id") or "")
    ]
    event_ids.append(
        team.record_final_verdict_ref(
            run_id,
            str(final_verdict.get("produced_by") or "go-evidence-finalizer"),
            verdict_id=str(final_verdict.get("verdict_id") or ""),
            producer_role=str(final_verdict.get("producer_role") or ""),
            final_state=str(final_verdict.get("final_state") or ""),
            ref_path=str(final_verdict_path),
            review_ref=review_id,
            gate_refs=gate_refs,
            gate_summary=[
                item for item in final_verdict.get("gate_summary", [])
                if isinstance(item, dict)
            ],
            limitations=[
                str(item) for item in final_verdict.get("limitations", [])
                if str(item)
            ],
            human_or_governance_reference=str(
                final_verdict.get("human_or_governance_reference") or ""
            ),
        )
    )
    return event_ids


def _record_blocked_finalization_evidence_refs(
    team: TeamRuntime,
    evidence_path: Path,
    result,
    artifacts: dict,
) -> list[str]:
    chain = result.chain_evidence
    run_id = str(chain.get("run_id") or evidence_path.name or "unknown-run")
    event_ids: list[str] = []
    for ref_type, filename in FINALIZATION_ARTIFACT_FILES:
        path = Path(str(artifacts.get(ref_type) or evidence_path / filename))
        if not path.exists():
            continue
        if _team_runtime_has_evidence_ref(team, run_id, ref_type, str(path)):
            continue
        event_ids.append(
            team.record_evidence_ref(
                run_id,
                "go-evidence-finalizer",
                ref_type=ref_type,
                ref_path=str(path),
            )
        )
    return event_ids


def _can_record_non_pass_final_verdict_ref(result) -> bool:
    if result.status not in {"blocked", "fail"}:
        return False
    reason = str(result.reason or "")
    if reason.startswith("chain-evidence.json schema invalid"):
        return False
    if reason.startswith("review.yaml schema invalid"):
        return False
    if reason.startswith("reviewer_role"):
        return False
    if reason == "reviewer_id must differ from executor_id":
        return False
    return str(result.review.get("verdict") or "") in {"blocked", "fail", "escalate"}


def _team_runtime_has_evidence_ref(
    team: TeamRuntime,
    run_id: str,
    ref_type: str,
    ref_path: str,
) -> bool:
    for event in team.read_all():
        if not isinstance(event, dict) or str(event.get("run_id") or "") != run_id:
            continue
        payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
        if (
            str(event.get("event_type") or "") == "evidence_ref"
            and str(payload.get("ref_type") or "") == ref_type
            and str(payload.get("ref_path") or "") == ref_path
        ):
            return True
    return False


def _team_runtime_has_finalization_refs(
    team: TeamRuntime,
    *,
    run_id: str,
    review_id: str,
    review_ref_path: str,
    verdict_id: str,
    final_verdict_ref_path: str,
) -> bool:
    has_review = False
    has_final_verdict = False
    for event in team.read_all():
        if not isinstance(event, dict) or str(event.get("run_id") or "") != run_id:
            continue
        payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
        event_type = str(event.get("event_type") or "")
        if event_type == "review_ref":
            has_review = (
                str(payload.get("review_id") or "") == review_id
                and str(payload.get("ref_path") or "") == review_ref_path
                and str(payload.get("source") or "") == "go_evidence_finalize"
            ) or has_review
        elif event_type == "final_verdict_ref":
            has_final_verdict = (
                str(payload.get("verdict_id") or "") == verdict_id
                and str(payload.get("ref_path") or "") == final_verdict_ref_path
                and str(payload.get("review_ref") or "") == review_id
            ) or has_final_verdict
    return has_review and has_final_verdict


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


def _safe_token(value: object) -> str:
    token = "".join(
        ch if ch.isalnum() or ch in "._-" else "-"
        for ch in str(value or "")
    )
    token = token.strip("-._")
    return token or "unknown"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="SADP evidence tool")
    subparsers = parser.add_subparsers(dest="command")

    finalize_parser = subparsers.add_parser("finalize", help="Finalize evidence")
    finalize_parser.add_argument("run_evidence_dir", help="Path to run evidence directory")
    finalize_parser.add_argument(
        "--team-runtime-dir",
        default=None,
        help="Optional TeamRuntime directory to record review/final verdict refs",
    )

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

        result, artifacts = write_governance_artifacts(args.run_evidence_dir)
        if args.team_runtime_dir:
            try:
                record_team_runtime_finalization(
                    args.run_evidence_dir,
                    result,
                    artifacts,
                    args.team_runtime_dir,
                    repo_root=str(REPO_ROOT),
                )
            except Exception as exc:
                print(
                    "failed to record team runtime finalization: "
                    f"{type(exc).__name__}: {exc}",
                    file=sys.stderr,
                )
                return 2

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
