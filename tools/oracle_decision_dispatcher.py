#!/usr/bin/env python3
"""
oracle_decision_dispatcher.py — Read outcome JSON and dispatch next action.

Usage:
    python tools/oracle_decision_dispatcher.py \
      --outcome _reports/oracle-flow-state/s2/FLOW_OUTCOME.json \
      --dry-run true

Rules:
    accepted + allow_next_stage=true → ready_to_dispatch
    blocked → stopped
    human_required → manual_confirm_required
    unknown → stopped
    destructive next action → manual_confirm_required
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

DESTRUCTIVE_KEYWORDS = {
    "delete", "remove", "rm ", "clean", "cleanup", "move", "rename",
    "overwrite", "fabricate", "force push", "reset --hard", "checkout --",
}

# Lazy import to avoid circular dependency
def _get_expected_taskspec_name(next_stage: str) -> str | None:
    from oracle_post_decision_driver import expected_taskspec_name
    return expected_taskspec_name(next_stage)


def ts():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def is_destructive(next_action: str) -> bool:
    lower = next_action.lower()
    return any(kw in lower for kw in DESTRUCTIVE_KEYWORDS)


def dispatch(outcome: dict) -> dict:
    """Return dispatch decision dict (GCA-2A: now includes terminal + should_execute_next)."""
    transport = outcome.get("transport_status", "failed")
    business = outcome.get("business_decision", "unknown")
    allow = outcome.get("allow_next_stage", False)

    result = {
        "dispatch_status": "stopped",
        "next_action": "",
        "reason": "",
        "manual_confirm_required": False,
        "timestamp": ts(),
        "terminal": True,
        "should_execute_next": False,
    }

    if transport == "failed":
        result["dispatch_status"] = "failed"
        result["reason"] = "transport_failed"
        return result

    if business == "accepted" and allow:
        # Phase Transition Hardening v2: validate next_stage must be explicit
        nts = outcome.get("next_task_spec_path", "")
        next_stage = outcome.get("next_stage", "")

        # Reject: missing next_stage
        if not next_stage:
            result["dispatch_status"] = "failed"
            result["reason"] = "MISSING_NEXT_STAGE: accepted+allow_next_stage but next_stage empty"
            result["terminal"] = True
            result["should_execute_next"] = False
            return result

        expected_name = _get_expected_taskspec_name(next_stage) if next_stage else None

        # Reject: no path
        if not nts:
            result["dispatch_status"] = "failed"
            result["reason"] = "accepted_without_valid_json_taskspec_path: empty"
            result["terminal"] = True
            result["should_execute_next"] = False
            return result

        # Reject: path points to .md
        if nts.endswith(".md"):
            result["dispatch_status"] = "failed"
            result["reason"] = f"accepted_without_valid_json_taskspec_path: markdown ({nts})"
            result["terminal"] = True
            result["should_execute_next"] = False
            return result

        # Reject: stage/path mismatch
        if expected_name and Path(nts).name != expected_name:
            result["dispatch_status"] = "failed"
            result["reason"] = f"stage_path_mismatch: stage={next_stage} expected={expected_name} actual={Path(nts).name}"
            result["terminal"] = True
            result["should_execute_next"] = False
            return result

        result["dispatch_status"] = "ready_to_dispatch"
        result["reason"] = "accepted_and_allow_next_stage"
        result["terminal"] = False
        result["should_execute_next"] = True
        result["next_task_spec_path"] = nts
        return result

    if business == "blocked":
        result["dispatch_status"] = "stopped"
        result["reason"] = "business_blocked"
        result["required_next_action"] = "reconciliation_required"
        return result

    if business == "human_required":
        result["dispatch_status"] = "manual_confirm_required"
        result["reason"] = "human_required"
        result["manual_confirm_required"] = True
        result["required_next_action"] = "human_scope_attestation_required"
        return result

    if business == "partial":
        nts = outcome.get("next_task_spec_path", "")
        nxt = outcome.get("next_stage", "")
        if allow and nxt and nts and nts.endswith(".json"):
            result["dispatch_status"] = "ready_to_dispatch"
            result["reason"] = "partial_remediation"
            result["terminal"] = False
            result["should_execute_next"] = True
            result["next_task_spec_path"] = nts
            return result
        result["dispatch_status"] = "stopped"
        result["reason"] = "partial_without_remediation_path"
        return result

    if business == "unknown":
        result["dispatch_status"] = "stopped"
        result["reason"] = "business_unknown"
        result["required_next_action"] = "rerun_review_or_human_review"
        return result

    result["dispatch_status"] = "stopped"
    result["reason"] = "no_matching_rule"
    result["required_next_action"] = "rerun_review_or_human_review"
    return result


def write_dispatch_result(log_dir: Path, dispatch_result: dict):
    """GCA-2A v3: Persist DISPATCH_RESULT.json with fail-closed schema validation.
    Schema missing/corrupt/invalid → RuntimeError (fail-closed)."""
    log_dir.mkdir(parents=True, exist_ok=True)
    dr_path = log_dir / "DISPATCH_RESULT.json"

    contracts_root = Path("D:/agent-acceptance/contracts")
    schema_path = contracts_root / "DISPATCH_RESULT.schema.json"

    if not schema_path.exists():
        raise RuntimeError(
            "GCA-2A FAIL-CLOSED: DISPATCH_RESULT.schema.json MISSING — cannot validate before write"
        )

    try:
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
    except Exception as e:
        raise RuntimeError(
            f"GCA-2A FAIL-CLOSED: DISPATCH_RESULT.schema.json CORRUPT/UNREADABLE: {e}"
        )

    try:
        from jsonschema import validate, ValidationError
        validate(instance=dispatch_result, schema=schema)
    except ValidationError as e:
        raise RuntimeError(
            f"GCA-2A FAIL-CLOSED: DISPATCH_RESULT schema validation failed: {e.message}"
        )
    except Exception as e:
        raise RuntimeError(
            f"GCA-2A FAIL-CLOSED: DISPATCH_RESULT schema check error: {e}"
        )

    dr_path.write_text(json.dumps(dispatch_result, indent=2, ensure_ascii=False), encoding="utf-8")


def write_action_log(log_path: Path, outcome: dict, dispatch_result: dict):
    log_path.parent.mkdir(parents=True, exist_ok=True)
    entries = [
        f"# Action Log",
        f"",
        f"## Input Outcome",
        f"```json",
        json.dumps(outcome, indent=2, ensure_ascii=False),
        f"```",
        f"",
        f"## Dispatch Decision",
        f"```json",
        json.dumps(dispatch_result, indent=2, ensure_ascii=False),
        f"```",
        f"",
        f"## Safety",
        f"- transport_status: {outcome.get('transport_status')}",
        f"- business_decision: {outcome.get('business_decision')}",
        f"- dispatch_status: {dispatch_result['dispatch_status']}",
        f"- manual_confirm_required: {dispatch_result['manual_confirm_required']}",
        f"- createdAt: {ts()}",
    ]
    log_path.write_text("\n".join(entries), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description="Decision Dispatcher")
    parser.add_argument("--outcome", required=True, help="Path to FLOW_OUTCOME.json")
    parser.add_argument("--action-log", default=None, help="Path to ACTION_LOG.md")
    parser.add_argument("--dry-run", default="true", help="dry-run mode")
    args = parser.parse_args()

    outcome_path = Path(args.outcome)
    if not outcome_path.exists():
        print(f"BLOCKED: outcome file not found: {outcome_path}")
        sys.exit(30)

    outcome = json.loads(outcome_path.read_text(encoding="utf-8"))
    dry_run = args.dry_run.lower() in ("true", "1", "yes")

    result = dispatch(outcome)

    # Check next action destructiveness
    next_action = outcome.get("required_next_action", "")
    if next_action and is_destructive(next_action):
        result["dispatch_status"] = "manual_confirm_required"
        result["reason"] = f"destructive_next_action: {next_action}"
        result["manual_confirm_required"] = True

    # Write action log
    log_dir = outcome_path.parent
    log_path = Path(args.action_log) if args.action_log else (
        log_dir / "ACTION_LOG.md")
    write_action_log(log_path, outcome, result)

    # GCA-2A: Persist DISPATCH_RESULT.json with schema validation
    try:
        write_dispatch_result(log_dir, result)
        print(f"DISPATCH_RESULT.json: written + schema-validated")
    except RuntimeError as e:
        print(f"FAIL-CLOSED: {e}")
        sys.exit(30)

    print(json.dumps(result, indent=2, ensure_ascii=False))
    print(f"\nDispatcher: {result['dispatch_status']} ({result['reason']})")

    if result["dispatch_status"] == "failed":
        sys.exit(30)
    if result["dispatch_status"] == "manual_confirm_required":
        sys.exit(10)
    sys.exit(0)


if __name__ == "__main__":
    main()
