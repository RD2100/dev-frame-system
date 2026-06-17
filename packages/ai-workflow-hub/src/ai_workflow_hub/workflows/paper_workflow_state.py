"""paper_workflow_state.py — A10 Paper Workflow State Model.

Pydantic BaseModel defining the state shared across all paper review
workflow nodes. Follows the same pattern as schemas.py:WorkflowState.

Design:
  - All fields default to empty/zero (LangGraph requirement)
  - Flat structure, no nested Pydantic models (keeps dict.update simple)
  - Integrates with A5-A9 components:
    * review_issues: from writelab_adapter / writelab_client
    * acceptance_result: from paper_acceptance_gate
    * evidence_manifest: from convert_handoff_zip
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field


class PaperWorkflowState(BaseModel):
    """State shared across all paper review workflow nodes."""

    # --- Runtime context (A16) ---
    run_id: str = ""  # unique run identifier
    run_dir: str = ""  # path to run directory on disk
    project_id: str = ""  # project identifier for daemon routing
    workflow_type: str = "paper"  # discriminator for multi-domain dispatch

    # --- Task context ---
    task_id: str = ""
    task_chapter: str = ""
    task_section: str = ""
    task_expected_function: str = ""
    paragraph_text: str = ""
    paragraph_index: int = 0

    # --- WriteLab configuration ---
    writelab_base_url: str = "http://127.0.0.1:8001"
    writelab_token: str = ""
    writelab_mode: str = "mock"  # "mock" | "live" | "offline"
    handoff_zip_path: str = ""  # for offline mode

    # --- Diagnosis results ---
    expression_issues: list[dict[str, Any]] = Field(default_factory=list)
    paragraph_issues: list[dict[str, Any]] = Field(default_factory=list)
    all_review_issues: list[dict[str, Any]] = Field(default_factory=list)
    diagnosis_source: str = ""  # "llm" | "rules_fallback" | "degraded" | "unavailable" | "offline"
    diagnosis_error: str = ""
    writelab_available: bool = True

    # --- Evidence manifest ---
    evidence_manifest: dict[str, Any] = Field(default_factory=dict)
    evidence_pack_ref: str = ""
    manifest_status: str = ""  # "complete" | "partial" | "failed" | ""

    # --- Acceptance result ---
    acceptance_status: str = ""  # "accepted" | "accepted_with_limitation" | "blocked" | ...
    acceptance_result: dict[str, Any] = Field(default_factory=dict)
    final_acceptance: bool = False  # true only for accepted, completed, unblocked runs
    blocking_count: int = 0
    non_blocking_count: int = 0

    # --- Human gate ---
    human_required: bool = False
    human_gate_decision: str = ""  # "" | "approved" | "rejected" | "pending"
    human_gate_triggered: bool = False

    # --- Human decision audit (A14/A15) ---
    reviewer_id: str = ""  # who made the human decision
    decision_timestamp: str = ""  # ISO timestamp of the decision
    decision_note: str = ""  # reason or comment for the decision
    decision_base_dir: str = ""  # base dir for decision file persistence (A15)
    decision_round: int = 0  # which round of decision (A15)

    # --- Privacy ---
    privacy_attestation: dict[str, bool] = Field(default_factory=dict)

    # --- Issue ledger (A12) ---
    ledger_dir: str = ""  # directory for ledger JSON files
    ledger_summary: dict[str, Any] = Field(default_factory=dict)  # from ledger_summary()
    ledger_issue_count: int = 0  # total issues ingested into ledger

    # --- Workflow control ---
    status: str = "pending"  # "pending" | "running" | "completed" | "blocked" | "error"
    error_message: str = ""
    fix_round: int = 0
    max_fix_rounds: int = 3
    executed_nodes: list[str] = Field(default_factory=list)

    # --- Audit ---
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
