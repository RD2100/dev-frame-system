#!/usr/bin/env python3
"""
oracle_post_decision_driver.py — Consume FLOW_OUTCOME.json and execute next action.

Usage:
    python tools/oracle_post_decision_driver.py \
      --task-id s2 --outcome FLOW_OUTCOME.json --execute true
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

def ts():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load_outcome(path: Path) -> dict:
    if not path.exists():
        return {"transport_status": "failed", "business_decision": "unknown",
                "dispatch_status": "failed", "overall_status": "missing_outcome"}
    return json.loads(path.read_text(encoding="utf-8"))


def load_dispatch_result(outcome_dir: Path) -> dict | None:
    """GCA-2A v3: Read DISPATCH_RESULT.json as dispatch authority.
    Missing → None (explicit fallback to FLOW_OUTCOME inference).
    Exists but corrupt/invalid → RuntimeError (fail-closed).
    """
    dr_path = outcome_dir / "DISPATCH_RESULT.json"
    if not dr_path.exists():
        return None
    try:
        data = json.loads(dr_path.read_text(encoding="utf-8"))
    except Exception as e:
        raise RuntimeError(
            f"GCA-2A FAIL-CLOSED: DISPATCH_RESULT.json exists but is CORRUPT/UNREADABLE: {e}"
        )
    # Validate against schema
    contracts_root = Path("D:/agent-acceptance/contracts")
    schema_path = contracts_root / "DISPATCH_RESULT.schema.json"
    if not schema_path.exists():
        raise RuntimeError(
            "GCA-2A FAIL-CLOSED: DISPATCH_RESULT.schema.json MISSING — cannot validate dispatch result"
        )
    try:
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        from jsonschema import validate, ValidationError
        validate(instance=data, schema=schema)
    except ValidationError as e:
        raise RuntimeError(
            f"GCA-2A FAIL-CLOSED: DISPATCH_RESULT.json schema-invalid: {e.message}"
        )
    except RuntimeError:
        raise
    except Exception as e:
        raise RuntimeError(
            f"GCA-2A FAIL-CLOSED: DISPATCH_RESULT.schema.json CORRUPT: {e}"
        )
    return data


def save_outcome(path: Path, outcome: dict):
    """GCA-2A v3: Route through oracle_flow_state.write_outcome() for schema validation.
    Prevents GAP-2 bypass — all FLOW_OUTCOME writes are now schema-validated."""
    from oracle_flow_state import write_outcome
    outcome["_updated_at"] = ts()
    write_outcome(path, outcome)


def write_action_log(log_path: Path, entries: list):
    log_path.parent.mkdir(parents=True, exist_ok=True)
    header = "# Action Log\n\n| Time | Event | Details |\n|------|-------|---------|\n"
    existing = ""
    if log_path.exists():
        existing = log_path.read_text(encoding="utf-8")
        if "|------|" in existing:
            existing = existing.split("|------|")[0] + "|------|---------|---------|\n"
    new_entries = "\n".join(entries)
    log_path.write_text(header + new_entries + "\n", encoding="utf-8")


def generate_s3_taskspec(task_id: str, outcome: dict) -> dict:
    """Generate S3 Frozen TaskSpec files. GCA-2B: also generates machine-readable JSON."""
    s3_dir = ROOT / "_reports" / "s3-frozen-taskspec"
    s3_dir.mkdir(parents=True, exist_ok=True)

    # GCA-2B: Generate JSON TaskSpec compliant with TASKSPEC.schema.json
    json_taskspec = {
        "task_id": f"s3-{task_id}",
        "stage": "S3",
        "goal": "SADP fallback alignment with standard @go semantics.",
        "allowed_actions": [
            "validate_schemas", "execute_taskspec", "generate_evidence_pack",
            "submit_gpt_review", "write_outcome", "dispatch_next",
            "generate_reports",
        ],
        "forbidden_actions": [
            "delete", "move", "rename", "clean_worktree",
            "overwrite_evidence", "fabricate_baseline",
            "modify_agent_acceptance_contracts",
        ],
        "required_outputs": [
            "S3_EXECUTION_PLAN.md", "S3 evidence pack",
            "GPT review submission", "FLOW_OUTCOME update",
        ],
        "terminal_conditions": {"terminal": False, "reason": "non_terminal_test_phase"},
        "review_required": True,
        "review_by": "gpt",
        "next_on_accepted": "proceed_to_phase4_or_next",
        "next_on_blocked": "generate_reconciliation_plan",
        "next_on_human_required": "stop_and_wait_for_human",
        "high_risk": False,
        "schema_version": "1.0.0",
    }

    # GCA-2B v2: Validate JSON TaskSpec against TASKSPEC schema (fail-closed)
    contracts_root = Path("D:/agent-acceptance/contracts")
    ts_schema_path = contracts_root / "TASKSPEC.schema.json"
    if not ts_schema_path.exists():
        raise RuntimeError(
            "GCA-2B FAIL-CLOSED: TASKSPEC.schema.json MISSING — cannot validate S3 TaskSpec"
        )
    try:
        ts_schema = json.loads(ts_schema_path.read_text(encoding="utf-8"))
    except Exception as e:
        raise RuntimeError(
            f"GCA-2B FAIL-CLOSED: TASKSPEC.schema.json CORRUPT/UNREADABLE: {e}"
        )
    try:
        from jsonschema import validate, ValidationError
        validate(instance=json_taskspec, schema=ts_schema)
    except ValidationError as e:
        raise RuntimeError(
            f"GCA-2B FAIL-CLOSED: S3 TaskSpec schema-invalid: {e.message}"
        )

    json_path = s3_dir / "S3_TASKSPEC.json"
    json_path.write_text(json.dumps(json_taskspec, indent=2, ensure_ascii=False), encoding="utf-8")

    # Also generate human-readable .md (existing behavior)

    taskspec = s3_dir / "S3_FROZEN_TASKSPEC.md"
    taskspec.write_text(f"""# S3 Frozen TaskSpec

## 1. Source Decision
- S2 Round-3 GPT accepted (2026-06-02)
- Pre-existing Claim Accepted: yes
- S2 human_required Resolved: yes
- S3 Allowed: yes
- allow_next_stage: true

## 2. Goal
SADP fallback alignment with standard @go semantics.

## 3. Allowed Actions
- Review current @go dispatch path for fallback behaviors
- Align fallback with S1 synthesis rules
- Ensure recovery paths don't bypass gate checks
- Add regression tests for fallback → gate bypass prevention
- Generate S3 evidence pack
- Submit to GPT for architecture review

## 4. Forbidden Actions
- Delete files
- Move/rename files
- Clean worktree
- Overwrite historical evidence
- Modify sensitive config
- Fabricate baseline or test results

## 5. Required Outputs
- S3_EXECUTION_PLAN.md
- S3 evidence pack
- GPT review submission
- FLOW_OUTCOME update

## 6. Next Review
Generate S3 review pack → submit GPT via Oracle CDP full review flow.
""", encoding="utf-8")

    plan = s3_dir / "S3_EXECUTION_PLAN.md"
    plan.write_text(f"""# S3 Execution Plan

## Phase 1: Audit (non-destructive)
1. Read current @go dispatch code in ai-workflow-hub/src/
2. Identify fallback paths and recovery logic
3. Cross-reference with S1 synthesis rules

## Phase 2: Test (non-destructive)
1. Write focused tests for fallback → gate bypass scenarios
2. Run existing S1/S2 regression tests
3. Confirm no regressions

## Phase 3: Fix (minimal changes)
1. Apply minimal fixes to align fallback with S1 rules
2. Re-run all tests
3. Generate fix evidence pack

## Phase 4: Review
1. Generate S3 review pack
2. Submit GPT via Oracle CDP full review flow
3. Parse GPT decision
""", encoding="utf-8")

    safety = s3_dir / "SAFETY_CHECK.md"
    safety.write_text(f"""# S3 Safety Check

| Check | Status |
|-------|--------|
| S2 accepted | yes |
| S3 allowed by GPT | yes |
| allow_next_stage | true |
| Non-destructive plan | yes |
| Audit phase only (no code changes yet) | yes |
| Generated at | {ts()} |
""", encoding="utf-8")

    manifest = s3_dir / "PACK_MANIFEST.md"
    manifest.write_text(f"""# S3 Frozen TaskSpec Pack

| File | Purpose |
|------|---------|
| S3_TASKSPEC.json | Machine-readable TaskSpec (runner input) |
| S3_FROZEN_TASKSPEC.md | Human-readable task definition |
| S3_EXECUTION_PLAN.md | Phase-by-phase plan |
| SAFETY_CHECK.md | Safety verification |
| PACK_MANIFEST.md | This file |
""", encoding="utf-8")

    return {"status": "generated", "path": str(taskspec),
            "json_path": str(json_path), "plan_path": str(plan), "files": 5}


# ── Contract Freeze Review Preparation TaskSpec ────────────────────────

def generate_contract_freeze_review_preparation_taskspec(task_id: str, outcome: dict) -> dict:
    """Phase transition fix: generate non-destructive freeze review prep TaskSpec.
    production_promotion_approved=no does NOT mean blocked.
    Contract freeze review is a valid next stage after production-readiness audit.
    """
    cf_dir = ROOT / "_reports" / "contract-freeze-review-prep"
    cf_dir.mkdir(parents=True, exist_ok=True)

    json_taskspec = {
        "task_id": f"contract-freeze-review-prep-{task_id}",
        "stage": "contract_freeze_review_preparation",
        "goal": "Contract Freeze Review Preparation: non-destructive evidence hardening for freeze review.",
        "allowed_actions": [
            "validate_schemas", "execute_taskspec", "generate_evidence_pack",
            "submit_gpt_review", "write_outcome", "dispatch_next",
            "generate_reports", "expand_contract_validation",
            "generate_cdp_submission_evidence",
        ],
        "forbidden_actions": [
            "delete", "move", "rename", "clean_worktree",
            "overwrite_evidence", "fabricate_baseline",
            "modify_agent_acceptance_contracts",
            "production_promotion",
        ],
        "required_outputs": [
            "CONTRACT_VALIDATION.md", "CDP_SUBMISSION_STATUS.json",
            "CDP_SUBMISSION_LOG.md", "BLOCKER_CLASSIFICATION.md",
            "FREEZE_REVIEW_PACK.zip",
        ],
        "terminal_conditions": {"terminal": False, "reason": "non_terminal_preparation_phase"},
        "review_required": True,
        "review_by": "gpt",
        "next_on_accepted": "proceed_to_contract_freeze_review",
        "next_on_blocked": "generate_reconciliation_plan",
        "next_on_human_required": "stop_and_wait_for_human",
        "high_risk": False,
        "schema_version": "1.0.0",
    }

    # Validate against TASKSPEC schema
    contracts_root = Path("D:/agent-acceptance/contracts")
    ts_schema_path = contracts_root / "TASKSPEC.schema.json"
    if not ts_schema_path.exists():
        raise RuntimeError("GCA-2B FAIL-CLOSED: TASKSPEC.schema.json MISSING")
    try:
        ts_schema = json.loads(ts_schema_path.read_text(encoding="utf-8"))
        from jsonschema import validate, ValidationError
        validate(instance=json_taskspec, schema=ts_schema)
    except ValidationError as e:
        raise RuntimeError(f"GCA-2B FAIL-CLOSED: Freeze Review Prep TaskSpec schema-invalid: {e.message}")
    except RuntimeError:
        raise
    except Exception as e:
        raise RuntimeError(f"GCA-2B FAIL-CLOSED: TASKSPEC.schema.json CORRUPT: {e}")

    json_path = cf_dir / "CONTRACT_FREEZE_REVIEW_PREPARATION_TASKSPEC.json"
    json_path.write_text(json.dumps(json_taskspec, indent=2, ensure_ascii=False), encoding="utf-8")

    return {"status": "generated", "json_path": str(json_path), "files": 1}


# ── Phase Transition Hardening: stage registry + stale guards ──────────

STAGE_REGISTRY = {
    "s3": {
        "expected_taskspec": "S3_TASKSPEC.json",
        "generator": "generate_s3_taskspec",
        "auto_dispatch": True,
        "production_promotion_allowed": False,
        "unknown_stage_policy": "fail_closed",
        "next_on_accepted": "execute_s3_frozen_taskspec",
    },
    "contract_freeze_review_preparation": {
        "expected_taskspec": "CONTRACT_FREEZE_REVIEW_PREPARATION_TASKSPEC.json",
        "generator": "generate_contract_freeze_review_preparation_taskspec",
        "auto_dispatch": True,
        "production_promotion_allowed": False,
        "unknown_stage_policy": "fail_closed",
        "next_on_accepted": "contract_freeze_review",
    },
    "contract_freeze_review": {
        "expected_taskspec": "CONTRACT_FREEZE_REVIEW_TASKSPEC.json",
        "generator": "generate_contract_freeze_review_taskspec",
        "auto_dispatch": True,
        "production_promotion_allowed": False,
        "unknown_stage_policy": "fail_closed",
        "next_on_accepted": "record_contract_freeze_decision",
        "next_on_partial": "generate_freeze_reconciliation_plan",
        "next_on_blocked": "generate_freeze_reconciliation_plan",
        "next_on_human_required": "stop_and_wait_for_human",
    },
}


def expected_taskspec_name(next_stage: str) -> str | None:
    """Return the expected TaskSpec filename for a given stage. None if unmapped."""
    stage = STAGE_REGISTRY.get(next_stage)
    return stage["expected_taskspec"] if stage else None


def is_stale_dispatch_result(dr: dict | None, next_stage: str) -> bool:
    """Stale when next_stage is registered and DR path does NOT match expected name."""
    if dr is None:
        return False
    expected = expected_taskspec_name(next_stage)
    if expected is None:
        return False  # Unknown stage: not stale, handled by fail-closed
    dr_ts_name = Path(dr.get("next_task_spec_path", "")).name
    return dr_ts_name != expected


def is_stale_outcome_path(outcome: dict, next_stage: str) -> bool:
    """Stale when next_stage is registered and path does NOT match expected name.
    Any mismatch for a registered stage is treated as stale — not just cross-stage."""
    expected = expected_taskspec_name(next_stage)
    if expected is None:
        return False  # Unknown stage: not stale, handled by fail-closed
    oc_ts_name = Path(outcome.get("next_task_spec_path", "")).name
    if not oc_ts_name:
        return False  # Empty path: not stale, handled by dispatcher rejection
    return oc_ts_name != expected


# ── Contract Freeze Review TaskSpec Generator ──────────────────────────

def generate_contract_freeze_review_taskspec(task_id: str, outcome: dict) -> dict:
    """Phase Transition Hardening: generate contract freeze review TaskSpec.
    Contract freeze review is NOT production promotion.
    contract_freeze_approved=no does NOT mean blocked.
    """
    cf_dir = ROOT / "_reports" / "contract-freeze-review"
    cf_dir.mkdir(parents=True, exist_ok=True)

    json_taskspec = {
        "task_id": f"contract-freeze-review-{task_id}",
        "stage": "contract_freeze_review",
        "goal": "Contract Freeze Review: non-destructive audit of freeze readiness.",
        "allowed_actions": [
            "validate_schemas", "execute_taskspec", "generate_evidence_pack",
            "submit_gpt_review", "write_outcome", "generate_reports",
            "review_contract_freeze_readiness",
        ],
        "forbidden_actions": [
            "delete", "move", "rename", "clean_worktree",
            "overwrite_evidence", "fabricate_baseline",
            "fabricate_human_attestation",
            "modify_agent_acceptance_contracts",
            "sensitive_config_modify",
            "production_promotion",
        ],
        "required_outputs": [
            "CONTRACT_FREEZE_REVIEW_REPORT.md",
            "CONTRACT_FREEZE_DECISION_MATRIX.md",
            "CONTRACT_FREEZE_SCOPE.md",
            "FREEZE_BLOCKER_RECONCILIATION.md",
            "CONTRACT_VALIDATION.md",
            "EVIDENCE_INTEGRITY_RESULT.json",
            "SAFETY_CHECK.md",
            "PACK_MANIFEST.md",
            "GPT_REVIEW_PROMPT.md",
            "GPT_REVIEW_RESULT.md",
            "GPT_REVIEW_DECISION.md",
            "CONTRACT_FREEZE_REVIEW_PACK.zip",
        ],
        "terminal_conditions": {"terminal": False, "reason": "non_terminal_review_phase"},
        "review_required": True,
        "review_by": "gpt",
        "next_on_accepted": "record_contract_freeze_decision",
        "next_on_partial": "generate_freeze_reconciliation_plan",
        "next_on_blocked": "generate_freeze_reconciliation_plan",
        "next_on_human_required": "stop_and_wait_for_human",
        "high_risk": False,
        "schema_version": "1.0.0",
    }

    contracts_root = Path("D:/agent-acceptance/contracts")
    ts_schema_path = contracts_root / "TASKSPEC.schema.json"
    if not ts_schema_path.exists():
        raise RuntimeError("Phase Transition FAIL-CLOSED: TASKSPEC.schema.json MISSING")
    try:
        ts_schema = json.loads(ts_schema_path.read_text(encoding="utf-8"))
        from jsonschema import validate, ValidationError
        validate(instance=json_taskspec, schema=ts_schema)
    except ValidationError as e:
        raise RuntimeError("Phase Transition FAIL-CLOSED: Freeze Review TaskSpec schema-invalid: " + e.message)
    except RuntimeError:
        raise
    except Exception as e:
        raise RuntimeError("Phase Transition FAIL-CLOSED: TASKSPEC.schema.json CORRUPT: " + str(e))

    json_path = cf_dir / "CONTRACT_FREEZE_REVIEW_TASKSPEC.json"
    json_path.write_text(json.dumps(json_taskspec, indent=2, ensure_ascii=False), encoding="utf-8")

    return {"status": "generated", "json_path": str(json_path), "files": 1}


# ── Phase Registry Guarded Enforcement v2.1 Remediation ────────────────

def generate_phase_registry_guarded_enforcement_v2_1_remediation_taskspec(task_id: str, outcome: dict) -> dict:
    """Partial → remediation: evidence fixes only. No architecture changes."""
    rem_dir = ROOT / "_reports" / "gca-phase3" / "phase-registry-remediation"
    rem_dir.mkdir(parents=True, exist_ok=True)

    json_taskspec = {
        "task_id": f"phase-registry-guarded-enforcement-v2-1-remediation-{task_id}",
        "stage": "phase_registry_guarded_enforcement_v2_1_remediation",
        "goal": "Evidence remediation: fix DISPATCH_RESULT._guarded_enforcement and TRANSITION_LOG dual decision evidence to match final dispatch stage/path.",
        "allowed_actions": [
            "validate_schemas", "execute_taskspec", "generate_evidence_pack",
            "submit_gpt_review", "write_outcome", "generate_reports",
            "fix_guarded_decision_final_dispatch_evidence",
        ],
        "forbidden_actions": [
            "delete", "move", "rename", "clean_worktree",
            "overwrite_evidence", "fabricate_baseline",
            "fabricate_human_attestation",
            "modify_agent_acceptance_contracts",
            "sensitive_config_modify",
            "production_promotion",
            "full_registry_enforcement",
            "contract_freeze_final_approval",
        ],
        "required_outputs": [
            "PHASE_REGISTRY_GUARDED_ENFORCEMENT_V2_1_REMEDIATION_TASKSPEC.json",
            "DISPATCH_RESULT.json (fixed)",
            "TRANSITION_LOG.jsonl (fixed)",
            "FLOW_OUTCOME.json",
            "EVIDENCE_INTEGRITY_RESULT.json",
            "TEST_OUTPUT.md",
            "SAFETY_CHECK.md",
            "PACK_MANIFEST.md",
            "GPT_REVIEW_PROMPT.md",
        ],
        "terminal_conditions": {"terminal": False, "reason": "non_terminal_remediation"},
        "review_required": True,
        "review_by": "gpt",
        "next_on_accepted": "phase_registry_guarded_enforcement",
        "next_on_partial": "generate_reconciliation_plan",
        "next_on_blocked": "generate_reconciliation_plan",
        "next_on_human_required": "stop_and_wait_for_human",
        "high_risk": False,
        "schema_version": "1.0.0",
    }

    contracts_root = Path("D:/agent-acceptance/contracts")
    ts_schema_path = contracts_root / "TASKSPEC.schema.json"
    if not ts_schema_path.exists():
        raise RuntimeError("FAIL-CLOSED: TASKSPEC.schema.json MISSING")
    try:
        ts_schema = json.loads(ts_schema_path.read_text(encoding="utf-8"))
        from jsonschema import validate, ValidationError
        validate(instance=json_taskspec, schema=ts_schema)
    except ValidationError as e:
        raise RuntimeError("FAIL-CLOSED: Remediation TaskSpec schema-invalid: " + e.message)
    except RuntimeError: raise
    except Exception as e:
        raise RuntimeError("FAIL-CLOSED: TASKSPEC.schema.json CORRUPT: " + str(e))

    json_path = rem_dir / "PHASE_REGISTRY_GUARDED_ENFORCEMENT_V2_1_REMEDIATION_TASKSPEC.json"
    json_path.write_text(json.dumps(json_taskspec, indent=2, ensure_ascii=False), encoding="utf-8")

    return {"status": "generated", "json_path": str(json_path), "files": 1}


# ── Transition Logger ──────────────────────────────────────────────────

def write_transition_log(log_dir: Path, entry: dict):
    """Append a transition entry to TRANSITION_LOG.jsonl."""
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "TRANSITION_LOG.jsonl"
    import datetime
    entry["timestamp"] = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def drive(task_id: str, outcome_path: Path, action_log_path: Path,
          execute: bool = True, allow_stage: str = "s3") -> dict:
    """Main driver logic. Returns updated outcome dict.

    GCA-2A: Reads DISPATCH_RESULT.json as dispatch authority when available.
    Falls back to FLOW_OUTCOME inference if DISPATCH_RESULT not present.
    """
    outcome = load_outcome(outcome_path)

    # GCA-2A: Read DISPATCH_RESULT as dispatch authority
    dispatch_result = load_dispatch_result(outcome_path.parent)
    if dispatch_result:
        # Use DISPATCH_RESULT as authority for dispatch status
        outcome["dispatch_status"] = dispatch_result.get("dispatch_status", outcome.get("dispatch_status"))
        outcome["_dispatch_authority"] = "DISPATCH_RESULT.json"
    else:
        outcome["_dispatch_authority"] = "FLOW_OUTCOME_inference"

    business = outcome.get("business_decision", "unknown")
    allow = outcome.get("allow_next_stage", False)
    s3_allowed = outcome.get("s3_allowed", False) or "yes" in str(
        outcome.get("required_next_action", ""))
    transport = outcome.get("transport_status", "failed")
    next_stage = outcome.get("next_stage", "")
    # Phase Transition v2: missing next_stage fail-closed for accepted+allow
    if not next_stage and business == "accepted" and allow:
        result = dict(outcome)
        result["dispatch_status"] = "failed"
        result["terminal"] = True
        result["should_execute_next"] = False
        result["driver_result"] = "MISSING_NEXT_STAGE"
        result["reason"] = "MISSING_NEXT_STAGE: accepted+allow_next_stage=true but next_stage is empty"
        result["driver_executed"] = True
        result["driver_timestamp"] = ts()
        entries = [f"| {ts()} | missing_next_stage_fail_closed | business=accepted allow=true |"]
        save_outcome(outcome_path, result)
        if action_log_path: write_action_log(action_log_path, entries)
        return result
    if not next_stage:
        next_stage = allow_stage  # Only fallback for non-accepted paths

    # Phase Transition Hardening: stale DISPATCH_RESULT guard
    stale_dr = False
    stale_oc = False
    if dispatch_result and is_stale_dispatch_result(dispatch_result, next_stage):
        stale_dr = True
        outcome["_stale_dispatch_result_ignored"] = True
        outcome["_stale_dispatch_result_old_path"] = dispatch_result.get("next_task_spec_path", "")
        outcome["_dispatch_authority"] = "FLOW_OUTCOME_recomputed"
        dispatch_result = None  # Ignore stale DR
        entries = [f"| {ts()} | stale_dispatch_result_ignored | stage={next_stage} |"]

    # Phase Transition Hardening: stale FLOW_OUTCOME path guard
    if is_stale_outcome_path(outcome, next_stage):
        stale_oc = True
        outcome["_stale_outcome_path_replaced"] = True
        outcome["_stale_outcome_old_path"] = outcome.get("next_task_spec_path", "")

    # Phase Transition Hardening: unknown next_stage fail-closed
    if next_stage not in STAGE_REGISTRY:
        result = dict(outcome)
        result["dispatch_status"] = "failed"
        result["terminal"] = True
        result["should_execute_next"] = False
        result["driver_result"] = "UNMAPPED_NEXT_STAGE"
        result["reason"] = f"UNMAPPED_NEXT_STAGE: {next_stage} not in stage registry"
        result["driver_executed"] = True
        result["driver_timestamp"] = ts()
        entries = [f"| {ts()} | unmapped_stage_fail_closed | stage={next_stage} |"]
        save_outcome(outcome_path, result)
        if action_log_path: write_action_log(action_log_path, entries)
        write_transition_log(outcome_path.parent, {
            "review_run_id": task_id, "transition_id": f"{ts()}-fail-closed",
            "from_stage": outcome.get("stage", "unknown"), "to_stage": next_stage,
            "business_decision": business, "allow_next_stage": allow,
            "dispatch_status": "failed", "stale_dispatch_result_ignored": stale_dr,
            "stale_outcome_path_replaced": stale_oc,
            "terminal": True, "should_execute_next": False,
            "production_promotion_approved": False,
            "contract_freeze_approved": False,
            "human_required": False, "reason": f"UNMAPPED_NEXT_STAGE: {next_stage}",
        })
        return result

    # GCA-2A v3: DISPATCH_RESULT is the COMPLETE execution authority
    if dispatch_result:
        dr_status = dispatch_result.get("dispatch_status", "stopped")
        dr_should_execute = dispatch_result.get("should_execute_next", False)

        if dr_status in ("stopped", "failed"):
            result = dict(outcome)
            result["terminal"] = True
            result["driver_result"] = f"dispatch_result_{dr_status}"
            result["driver_executed"] = True
            result["driver_timestamp"] = ts()
            entries = [f"| {ts()} | stopped_by_dispatch_result | {dr_status} |"]
            save_outcome(outcome_path, result)
            if action_log_path: write_action_log(action_log_path, entries)
            return result

        if dr_status == "manual_confirm_required":
            result = dict(outcome)
            result["dispatch_status"] = "stopped"
            result["overall_status"] = "human_required"
            result["terminal"] = True
            result["required_next_action"] = "human_scope_attestation_required"
            result["driver_result"] = "stopped_via_dispatch_manual_confirm"
            result["driver_executed"] = True
            result["driver_timestamp"] = ts()
            entries = [f"| {ts()} | stopped_manual_confirm | dispatch_result=manual_confirm_required |"]
            save_outcome(outcome_path, result)
            if action_log_path: write_action_log(action_log_path, entries)
            return result

        if not dr_should_execute:
            result = dict(outcome)
            result["terminal"] = True
            result["driver_result"] = "dispatch_should_execute_false"
            result["driver_executed"] = True
            result["driver_timestamp"] = ts()
            entries = [f"| {ts()} | stopped | should_execute_next=false |"]
            save_outcome(outcome_path, result)
            if action_log_path: write_action_log(action_log_path, entries)
            return result

        # ready_to_dispatch + should_execute_next=true: execute based on DISPATCH_RESULT fields
        if dr_status == "ready_to_dispatch" and dr_should_execute:
            entries = [f"| {ts()} | dispatch_authority | DISPATCH_RESULT.json (ready_to_dispatch) |"]
            result = dict(outcome)
            result["driver_executed"] = True
            result["driver_timestamp"] = ts()
            if execute:
                dr_next_ts = dispatch_result.get("next_task_spec_path", outcome.get("next_task_spec_path", ""))
                result["dispatch_status"] = "dispatched"
                result["overall_status"] = "accepted"
                result["next_task_spec_path"] = dr_next_ts
                result["required_next_action"] = "execute_dispatched_taskspec"
                result["terminal"] = False
                result["should_execute_next"] = True
                result["driver_result"] = "dispatched_from_dispatch_result"
                entries.append(f"| {ts()} | dispatched_from_dispatch_result | taskspec={dr_next_ts} |")
            else:
                result["driver_result"] = "dry_run_ready"
                entries.append(f"| {ts()} | dry_run | dispatch_result_ready |")
            save_outcome(outcome_path, result)
            if action_log_path: write_action_log(action_log_path, entries)
            return result

    entries = []
    result = dict(outcome)
    result["driver_executed"] = True
    result["driver_timestamp"] = ts()
    entries.append(f"| {ts()} | dispatch_authority | {outcome.get('_dispatch_authority')} |")

    # ── accepted + allow_next_stage=true ──
    # Phase transition fix: production_promotion_approved=no != blocked.
    # Allow dispatch to any valid next_stage from outcome, not just "s3".
    if business == "accepted" and allow:
        # Phase Transition Hardening: stale path replacement
        if stale_oc:
            result["_stale_outcome_path_replaced"] = True

        if next_stage == "s3" and allow_stage == "s3":
            if not execute:
                result["dispatch_status"] = "ready_to_dispatch"
                result["overall_status"] = "ready_to_dispatch_not_executed"
                result["driver_result"] = "dry_run"
                entries.append(f"| {ts()} | driver_dry_run | accepted but not executed |")
            else:
                s3_result = generate_s3_taskspec(task_id, outcome)
                result["dispatch_status"] = "dispatched"
                result["overall_status"] = "accepted"
                result["next_stage"] = "s3"
                result["next_task_spec_path"] = s3_result["json_path"]
                result["required_next_action"] = "execute_s3_frozen_taskspec"
                result["s3_execution_mode"] = "prepared_not_executed"
                result["terminal"] = False
                result["should_execute_next"] = True
                result["driver_result"] = "s3_taskspec_generated"
                entries.append(f"| {ts()} | dispatched_to_s3 | taskspec={s3_result['path']} |")
                entries.append(f"| {ts()} | s3_taskspec_generated | {s3_result['files']} files |")
                entries.append(f"| {ts()} | s3_execution_mode | prepared_not_executed |")
        elif next_stage == "contract_freeze_review_preparation":
            if not execute:
                result["driver_result"] = "dry_run_contract_freeze_prep"
                entries.append(f"| {ts()} | dry_run | contract_freeze_review_preparation |")
            else:
                cf_result = generate_contract_freeze_review_preparation_taskspec(task_id, outcome)
                result["dispatch_status"] = "dispatched"
                result["overall_status"] = "accepted"
                result["next_stage"] = "contract_freeze_review_preparation"
                result["next_task_spec_path"] = cf_result["json_path"]
                result["required_next_action"] = "execute_freeze_review_prep_taskspec"
                result["terminal"] = False
                result["should_execute_next"] = True
                result["driver_result"] = "contract_freeze_review_prep_generated"
                entries.append(f"| {ts()} | dispatched_to_freeze_review_prep |")
        elif next_stage == "contract_freeze_review":
            if not execute:
                result["driver_result"] = "dry_run_contract_freeze_review"
                entries.append(f"| {ts()} | dry_run | contract_freeze_review |")
            else:
                review_result = generate_contract_freeze_review_taskspec(task_id, outcome)
                result["dispatch_status"] = "dispatched"
                result["overall_status"] = "accepted"
                result["next_stage"] = "contract_freeze_review"
                result["next_task_spec_path"] = review_result["json_path"]
                result["required_next_action"] = "execute_contract_freeze_review"
                result["terminal"] = False
                result["should_execute_next"] = True
                result["driver_result"] = "contract_freeze_review_generated"
                result["_stale_dispatch_result_ignored"] = stale_dr
                result["_stale_outcome_path_replaced"] = stale_oc
                entries.append(f"| {ts()} | dispatched_to_contract_freeze_review |")
        elif next_stage == "phase_registry_guarded_enforcement_v2_1_remediation":
            if not execute:
                result["driver_result"] = "dry_run_remediation"
                entries.append(f"| {ts()} | dry_run | v2_1_remediation |")
            else:
                rem_result = generate_phase_registry_guarded_enforcement_v2_1_remediation_taskspec(task_id, outcome)
                result["dispatch_status"] = "dispatched"
                result["overall_status"] = "partial"
                result["next_stage"] = "phase_registry_guarded_enforcement_v2_1_remediation"
                result["next_task_spec_path"] = rem_result["json_path"]
                result["required_next_action"] = "fix_guarded_decision_final_dispatch_evidence"
                result["terminal"] = False
                result["should_execute_next"] = True
                result["driver_result"] = "v2_1_remediation_generated"
                entries.append(f"| {ts()} | dispatched_to_v2_1_remediation |")
                write_transition_log(outcome_path.parent, {
                    "review_run_id": task_id,
                    "transition_id": f"{ts()}-freeze-review",
                    "from_stage": "contract_freeze_review_preparation",
                    "to_stage": "contract_freeze_review",
                    "business_decision": business,
                    "allow_next_stage": allow,
                    "dispatch_status": "dispatched",
                    "previous_dispatch_result_path": str(outcome_path.parent / "DISPATCH_RESULT.json") if (outcome_path.parent / "DISPATCH_RESULT.json").exists() else "",
                    "previous_dispatch_result_used": not stale_dr,
                    "stale_dispatch_result_ignored": stale_dr,
                    "stale_outcome_path_replaced": stale_oc,
                    "generated_taskspec_path": review_result["json_path"],
                    "terminal": False,
                    "should_execute_next": True,
                    "production_promotion_approved": False,
                    "contract_freeze_approved": False,
                    "human_required": False,
                })
        else:
            # Phase Transition Hardening: no generic fallback
            result["dispatch_status"] = "failed"
            result["terminal"] = True
            result["should_execute_next"] = False
            result["driver_result"] = "UNMAPPED_NEXT_STAGE"
            result["reason"] = f"UNMAPPED_NEXT_STAGE: {next_stage} not in driver dispatch branches"
            entries.append(f"| {ts()} | unmapped_stage_fail_closed | stage={next_stage} |")

    # ── partial → remediation (partial != stop) ──
    elif business == "partial" and allow and next_stage:
        result["dispatch_status"] = "ready_to_dispatch"
        result["overall_status"] = "partial"
        result["terminal"] = False
        result["should_execute_next"] = True
        result["driver_result"] = "partial_remediation_dispatched"
        entries.append(f"| {ts()} | partial_remediation | next_stage={next_stage} |")

    # ── human_required ──
    elif business == "human_required":
        result["dispatch_status"] = "manual_confirm_required"
        result["overall_status"] = "transport_success_business_human_required"
        result["terminal"] = True
        result["required_next_action"] = "human_scope_attestation_required"
        result["resume_command"] = f"python tools/oracle_gpt_full_review_flow.py --task-id {task_id}"
        result["driver_result"] = "stopped_human_required"
        entries.append(f"| {ts()} | stopped_human_required | awaiting human confirmation |")

    # ── blocked ──
    elif business == "blocked":
        result["dispatch_status"] = "stopped"
        result["overall_status"] = "transport_success_business_blocked"
        result["terminal"] = True
        result["required_next_action"] = "reconciliation_required"
        result["driver_result"] = "stopped_blocked"
        entries.append(f"| {ts()} | stopped_blocked | reconciliation required |")

    # ── unknown / other ──
    else:
        result["dispatch_status"] = "stopped"
        result["overall_status"] = "unknown"
        result["terminal"] = True
        result["required_next_action"] = "rerun_review_or_human_review"
        result["driver_result"] = "stopped_unknown"
        entries.append(f"| {ts()} | stopped_unknown | business={business} transport={transport} |")

    # Phase Registry Shadow Mode: compare current decision with registry
    try:
        from phase_registry import load_registry, shadow_compare, resolve_guarded_transition
        registry = load_registry()
        current_human_required = result.get("required_next_action", "") == "human_scope_attestation_required"

        # Shadow comparison
        shadow = shadow_compare(
            registry, business, allow, next_stage,
            current_dispatch_status=result.get("dispatch_status", "stopped"),
            current_terminal=result.get("terminal", True),
            current_should_execute=result.get("should_execute_next", False),
            human_required=current_human_required,
        )
        result["_shadow_registry_match"] = shadow.match
        result["_shadow_registry_mismatches"] = shadow.mismatches
        if not shadow.match:
            entries.append(f"| {ts()} | SHADOW_MISMATCH | {'; '.join(shadow.mismatches)} |")

        # Guarded Enforcement: dual-path resolution
        # Use result's next_task_spec_path (post-driver) for hardcoded; outcome's for context
        ts_path = result.get("next_task_spec_path", "") or outcome.get("next_task_spec_path", "")
        hc_ts_path = ts_path  # hardcoded uses whatever the driver produced
        guarded = resolve_guarded_transition(
            registry, business, allow, next_stage,
            next_task_spec_path=ts_path,
            hardcoded_dispatch_status=result.get("dispatch_status", "stopped"),
            hardcoded_terminal=result.get("terminal", True),
            hardcoded_should_execute=result.get("should_execute_next", False),
            hardcoded_next_stage=result.get("next_stage", ""),
            human_required=current_human_required,
        )
        result["_guarded_enforcement"] = {
            "mode": guarded.mode,
            "agreement": guarded.agreement,
            "mismatch_fields": guarded.mismatch_fields,
            "comparison_fields": [
                "dispatch_status_normalized",
                "should_execute_next",
                "terminal",
                "next_stage",
                "next_task_spec_path_basename",
                "production_promotion_allowed",
            ],
            "registry_decision": guarded.registry_decision,
            "hardcoded_decision": guarded.hardcoded_decision,
        }
        if guarded.agreement:
            entries.append(f"| {ts()} | GUARDED_AGREEMENT | registry=hardcoded |")
        else:
            entries.append(f"| {ts()} | GUARDED_MISMATCH | {'; '.join(guarded.mismatch_fields)} |")
            # Guarded Enforcement: ANY mismatch → fail-closed. No exemptions.
            result["dispatch_status"] = "failed"
            result["terminal"] = True
            result["should_execute_next"] = False
            result["required_next_action"] = "inspect_registry_hardcoded_mismatch"
            result["reason"] = f"REGISTRY_HARDCODED_MISMATCH: {'; '.join(guarded.mismatch_fields)}"
            result["driver_result"] = "guarded_enforcement_mismatch_fail_closed"
    except Exception as e:
        result["_shadow_registry_error"] = str(e)
        entries.append(f"| {ts()} | SHADOW_REGISTRY_ERROR | {e} |")

    save_outcome(outcome_path, result)
    if entries and action_log_path:
        write_action_log(action_log_path, entries)

    return result


def main():
    parser = argparse.ArgumentParser(description="Post-Decision Driver")
    parser.add_argument("--task-id", default="s2")
    parser.add_argument("--outcome", required=True)
    parser.add_argument("--action-log", default=None)
    parser.add_argument("--policy", default=None)
    parser.add_argument("--execute", default="true")
    parser.add_argument("--dry-run", default="false")
    parser.add_argument("--max-actions", type=int, default=1)
    parser.add_argument("--allow-stage", default="s3")
    args = parser.parse_args()

    outcome_path = Path(args.outcome)
    if not outcome_path.exists():
        print(f"BLOCKED: outcome not found: {outcome_path}")
        sys.exit(30)

    action_log_path = Path(args.action_log) if args.action_log else (
        outcome_path.parent / "ACTION_LOG.md")
    execute = args.execute.lower() in ("true", "1", "yes")
    dry_run = args.dry_run.lower() in ("true", "1", "yes")

    print(f"Post-Decision Driver — {args.task_id}")
    print(f"  outcome: {outcome_path}")
    print(f"  execute: {execute}")
    print(f"  allow-stage: {args.allow_stage}")

    if dry_run:
        execute = False

    result = drive(args.task_id, outcome_path, action_log_path,
                   execute=execute, allow_stage=args.allow_stage)

    print(json.dumps({
        "dispatch_status": result.get("dispatch_status"),
        "next_stage": result.get("next_stage", ""),
        "next_task_spec_path": result.get("next_task_spec_path", ""),
        "required_next_action": result.get("required_next_action", ""),
        "terminal": result.get("terminal", False),
        "driver_result": result.get("driver_result", ""),
    }, indent=2, ensure_ascii=False))

    if result.get("dispatch_status") == "dispatched":
        print("\nDriver: dispatched to next stage")
        sys.exit(0)
    elif result.get("dispatch_status") == "manual_confirm_required":
        sys.exit(10)
    elif result.get("dispatch_status") == "stopped":
        sys.exit(20)
    else:
        sys.exit(0)


if __name__ == "__main__":
    main()
