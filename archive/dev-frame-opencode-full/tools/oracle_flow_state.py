#!/usr/bin/env python3
"""
oracle_flow_state.py — Unified state, checkpoint, idempotency, and outcome JSON.

Usage:
    from oracle_flow_state import FlowState, checkpoint, write_outcome

    state = FlowState(task_id="s2", round=1)
    checkpoint(state, "PAGE_READY", page_url="https://...")
    outcome = state.to_outcome(transport_status="success", business_decision="blocked")
    write_outcome("_reports/oracle-flow-state/s2/FLOW_OUTCOME.json", outcome)
"""

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


# ── Three-layer status ──────────────────────────────────────────────

TRANSPORT_STATUSES = {"success", "partial", "failed"}
BUSINESS_DECISIONS = {"accepted", "blocked", "human_required", "rejected", "unknown"}
DISPATCH_STATUSES = {"not_attempted", "dispatched", "stopped", "manual_confirm_required", "failed", "ready_to_dispatch"}

STAGES = [
    "PRECHECK", "PAGE_READY", "DRAFT_VERIFIED", "UPLOAD_VERIFIED",
    "SUBMIT_ACKED", "REPLY_WAIT", "REPLY_COMPLETE", "DECISION_PARSED",
    "NEXT_ACTION_DISPATCHED", "STOPPED", "MANUAL_CONFIRM", "FAILED",
]


def ts():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def normalize_status(transport: str, business: str, dispatch: str) -> str:
    """Compute overall_status from three layers."""
    if transport == "failure" or business == "unknown" and dispatch == "failed":
        return "technical_failure_or_incomplete"
    if transport == "success" and business == "accepted" and dispatch in ("dispatched", "ready_to_dispatch"):
        return "ready"
    if transport == "success" and business == "blocked":
        return "transport_success_business_blocked"
    if transport == "success" and business == "human_required":
        return "transport_success_business_human_required"
    if transport == "partial":
        return "transport_partial"
    if business == "unknown":
        return "business_unknown"
    if dispatch == "manual_confirm_required":
        return "manual_confirm_required"
    return "incomplete"


# ── Idempotency ─────────────────────────────────────────────────────

def compute_idempotency_key(task_id: str, round_num: int,
                            prompt_path: str, zip_path: str) -> str:
    raw = f"{task_id}|{round_num}|{prompt_path}|{zip_path}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


# ── FlowState ───────────────────────────────────────────────────────

class FlowState:
    def __init__(self, task_id: str, round_num: int = 1):
        self.task_id = task_id
        self.round = round_num
        self.stage = "PRECHECK"
        self.history: list[dict] = []
        self.errors: list[str] = []
        self.transport_status = "partial"
        self.business_decision = "unknown"
        self.dispatch_status = "not_attempted"
        self.overall_status = "incomplete"
        self.allow_next_stage = False
        self.safety_ok = True

        # ACK fields
        self.prompt_verified = False
        self.upload_result = "not_attempted"
        self.submit_acked = False
        self.new_reply_verified = False
        self.completion_status = "not_started"
        self.decision_parsed = False

        # Paths
        self.target_url = ""
        self.zip_path = ""
        self.zip_hash = ""
        self.prompt_path = ""
        self.prompt_hash = ""
        self.result_output = ""
        self.decision_output = ""

    def checkpoint(self, stage: str, **kwargs):
        self.stage = stage
        entry = {"stage": stage, "timestamp": ts(), **kwargs}
        self.history.append(entry)
        return entry

    def to_outcome(self) -> dict:
        return {
            "flow_run_id": hashlib.sha256(f"{self.task_id}|{self.round}|{ts()}".encode()).hexdigest()[:16],
            "idempotency_key": compute_idempotency_key(
                self.task_id, self.round, self.prompt_path, self.zip_path),
            "task_id": self.task_id,
            "round": self.round,
            "stage": self.stage,
            "transport_status": self.transport_status,
            "business_decision": self.business_decision,
            "dispatch_status": self.dispatch_status,
            "overall_status": self.overall_status,
            "terminal": False,
            "target_url": self.target_url,
            "target_session_id": "",
            "zip_path": self.zip_path,
            "zip_hash": self.zip_hash,
            "prompt_path": self.prompt_path,
            "prompt_hash": self.prompt_hash,
            "prompt_verified": self.prompt_verified,
            "upload_result": self.upload_result,
            "submit_acked": self.submit_acked,
            "new_reply_verified": self.new_reply_verified,
            "completion_status": self.completion_status,
            "decision_parsed": self.decision_parsed,
            "allow_next_stage": self.allow_next_stage,
            "required_next_action": "",
            "errors": self.errors,
            "safety": {
                "destructive_action": False,
                "manual_confirm_required": False,
                "s3_executed": False,
            },
        }

    def compute_statuses(self):
        self.overall_status = normalize_status(
            self.transport_status, self.business_decision, self.dispatch_status)


# ── Persistence ─────────────────────────────────────────────────────

DEFAULT_STATE_DIR = Path("_reports") / "oracle-flow-state"


def state_path(task_id: str) -> Path:
    return DEFAULT_STATE_DIR / task_id / "FLOW_STATE.json"


def outcome_path(task_id: str) -> Path:
    return DEFAULT_STATE_DIR / task_id / "FLOW_OUTCOME.json"


def save_state(state: FlowState, path: Path | None = None):
    p = path or state_path(state.task_id)
    p.parent.mkdir(parents=True, exist_ok=True)
    state_data = {
        "task_id": state.task_id, "round": state.round, "stage": state.stage,
        "transport_status": state.transport_status, "business_decision": state.business_decision,
        "dispatch_status": state.dispatch_status, "overall_status": state.overall_status,
        "allow_next_stage": state.allow_next_stage, "history": state.history,
        "errors": state.errors, "_updated_at": ts(),
    }
    p.write_text(json.dumps(state_data, indent=2, ensure_ascii=False), encoding="utf-8")


def load_state(path: Path) -> dict:
    if not path.exists():
        return {"task_id": "unknown", "round": 0, "stage": "PRECHECK",
                "history": [], "errors": [], "_updated_at": ts()}
    return json.loads(path.read_text(encoding="utf-8"))


def write_outcome(path: Path, outcome: dict):
    """GCA-2A v3: Validate against FLOW_OUTCOME.schema.json before write (fail-closed).
    Schema missing/corrupt/invalid → RuntimeError."""
    path.parent.mkdir(parents=True, exist_ok=True)

    contracts_root = Path("D:/agent-acceptance/contracts")
    schema_path = contracts_root / "FLOW_OUTCOME.schema.json"

    if not schema_path.exists():
        raise RuntimeError(
            "GCA-2A FAIL-CLOSED: FLOW_OUTCOME.schema.json MISSING — cannot validate before write"
        )

    try:
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
    except Exception as e:
        raise RuntimeError(
            f"GCA-2A FAIL-CLOSED: FLOW_OUTCOME.schema.json CORRUPT/UNREADABLE: {e}"
        )

    try:
        from jsonschema import validate, ValidationError
        validate(instance=outcome, schema=schema)
    except ValidationError as e:
        raise RuntimeError(
            f"GCA-2A FAIL-CLOSED: FLOW_OUTCOME schema validation failed before write: {e.message}"
        )
    except Exception as e:
        raise RuntimeError(
            f"GCA-2A FAIL-CLOSED: FLOW_OUTCOME schema check error: {e}"
        )

    path.write_text(json.dumps(outcome, indent=2, ensure_ascii=False), encoding="utf-8")


def read_outcome(path: Path) -> dict:
    if not path.exists():
        return {"transport_status": "failed", "business_decision": "unknown",
                "dispatch_status": "failed", "overall_status": "missing_outcome"}
    return json.loads(path.read_text(encoding="utf-8"))


# ── URL validation ──────────────────────────────────────────────────

def validate_target_url(url: str) -> tuple[bool, str]:
    """Returns (is_valid, reason)."""
    from urllib.parse import urlparse
    if not url or not url.strip():
        return False, "BLOCKED_TARGET_URL_MISSING"
    parsed = urlparse(url.strip())
    hostname = parsed.hostname or ""
    base = ".".join(hostname.split(".")[-2:]) if hostname.count(".") >= 1 else hostname
    if base not in ("chatgpt.com", "chat.openai.com"):
        return False, f"BLOCKED_TARGET_URL_INVALID: {base}"
    import re
    if not re.search(r"/c/[a-f0-9-]{20,}", url):
        return False, "BLOCKED_TARGET_SESSION_MISSING"
    return True, "valid"


# ── Exit codes ──────────────────────────────────────────────────────

EXIT_SUCCESS = 0               # transport ok, outcome generated
EXIT_MANUAL_CONFIRM = 10       # manual confirmation required
EXIT_BLOCKED = 20              # business blocked
EXIT_TECHNICAL_FAILURE = 30    # technical failure
EXIT_INVALID_INPUT = 40        # invalid input / safety failure
