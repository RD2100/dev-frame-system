"""Control Plane Skeleton v2 — real historical pack replay + synthetic edge cases."""
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


ROOT = Path(__file__).resolve().parent.parent
REPORTS_ROOT = ROOT / "_reports"


@dataclass
class ReviewDecision:
    review_run_id: str = ""
    overall_judgment: str = "unknown"  # accepted | partial | blocked | human_required
    required_next_action: Optional[str] = None
    human_required: bool = False
    blocked: bool = False
    production_promotion_approved: bool = False
    contract_freeze_approved: bool = False


@dataclass
class FlowOutcomeDecision:
    business_decision: str = "unknown"
    allow_next_stage: bool = False
    next_stage: Optional[str] = None
    next_task_spec_path: Optional[str] = None
    terminal: bool = True


@dataclass
class DispatchDecision:
    dispatch_status: str = "stopped"  # ready_to_dispatch | stopped | failed | manual_confirm_required
    should_execute_next: bool = False
    terminal: bool = True
    next_task_spec_path: Optional[str] = None
    required_next_action: Optional[str] = None


@dataclass
class ContinuationDecision:
    should_continue: bool = False
    next_task_spec_path: Optional[str] = None
    reason: str = ""
    stop_reason: Optional[str] = None
    fail_closed: bool = False


@dataclass
class EvidenceState:
    tests_failed: int = 0
    evidence_gate_ready: bool = True
    registry_valid: bool = True
    shadow_matches: bool = True
    guarded_agreement: bool = True
    guarded_next_stage: str = ""
    flow_next_stage: str = ""
    dispatch_next_stage: str = ""
    flow_next_path: str = ""
    dispatch_next_path: str = ""


class RunUntilTerminalController:
    """Unified control plane for run-until-terminal automation.
    Shadow mode: only computes decisions, never executes real TaskSpecs.
    """

    def __init__(self, mode: str = "shadow_replay"):
        self.mode = mode  # shadow_replay | guarded | enforcement (future)
        self.log: list[dict] = []

    def decide_continuation(
        self,
        review: ReviewDecision,
        flow: FlowOutcomeDecision,
        dispatch: DispatchDecision,
        evidence: EvidenceState,
    ) -> ContinuationDecision:
        """Apply all continuation rules and return a decision."""

        # Normalize: strip trailing punctuation from overall_judgment
        review.overall_judgment = review.overall_judgment.rstrip(",:;.")

        # Rule 1: human_required has highest priority
        if review.human_required or review.overall_judgment == "human_required":
            return ContinuationDecision(
                should_continue=False, stop_reason="human_required",
                reason="human_required has highest priority")

        # Rule 2: blocked stops
        if review.blocked or review.overall_judgment == "blocked":
            return ContinuationDecision(
                should_continue=False, stop_reason="blocked",
                reason="blocked stops execution")

        # Rule 3: production promotion never auto-continues
        if flow.next_stage and "production_promotion" in flow.next_stage:
            return ContinuationDecision(
                should_continue=False, stop_reason="production_promotion_requires_human",
                reason="production promotion requires explicit human confirmation", fail_closed=True)

        # Rule 4: tests_failed fail-closed
        if evidence.tests_failed > 0:
            return ContinuationDecision(
                should_continue=False, stop_reason="tests_failed",
                reason=f"{evidence.tests_failed} tests failed", fail_closed=True)

        # Rule 5: evidence gate fail-closed
        if not evidence.evidence_gate_ready:
            return ContinuationDecision(
                should_continue=False, stop_reason="evidence_integrity_failed",
                reason="evidence integrity gate not ready_for_review", fail_closed=True)

        # Rule 6: split-brain fail-closed
        if flow.next_task_spec_path and dispatch.next_task_spec_path:
            fn = Path(flow.next_task_spec_path).name
            dn = Path(dispatch.next_task_spec_path).name
            if fn and dn and fn != dn:
                return ContinuationDecision(
                    should_continue=False, stop_reason="authority_split_brain",
                    reason=f"FLOW={fn} != DISPATCH={dn}", fail_closed=True)

        # Rule 7: guarded decision mismatch fail-closed
        if evidence.guarded_next_stage and evidence.flow_next_stage:
            if evidence.guarded_next_stage != evidence.flow_next_stage:
                return ContinuationDecision(
                    should_continue=False, stop_reason="guarded_decision_mismatch",
                    reason=f"guarded={evidence.guarded_next_stage} != flow={evidence.flow_next_stage}", fail_closed=True)

        # Rule 8: unknown next_stage fail-closed
        if flow.next_stage and flow.next_stage not in ("s3", "contract_freeze_review_preparation",
            "contract_freeze_review", "phase_registry_guarded_enforcement_v2_1_remediation",
            "phase_registry_guarded_enforcement", "record_contract_freeze_decision",
            "freeze_reconciliation_plan", "production_promotion_review",
            "phase_registry_prototype", "phase_registry_enforcement_preparation",
            "remediation"):  # generic remediation for partial
            return ContinuationDecision(
                should_continue=False, stop_reason="unknown_next_stage",
                reason=f"next_stage={flow.next_stage} not in known stages", fail_closed=True)

        # Rule 9: accepted can continue
        if review.overall_judgment == "accepted":
            ts_path = dispatch.next_task_spec_path or flow.next_task_spec_path or ""
            # Validate path
            if not ts_path:
                return ContinuationDecision(
                    should_continue=False, stop_reason="missing_next_task_spec_path",
                    reason="accepted but no next_task_spec_path", fail_closed=True)
            if ts_path.endswith(".md"):
                return ContinuationDecision(
                    should_continue=False, stop_reason="markdown_task_spec",
                    reason="next_task_spec_path is .md, must be .json", fail_closed=True)
            # Check dispatch ready
            if dispatch.dispatch_status == "ready_to_dispatch" and dispatch.should_execute_next and not dispatch.terminal:
                return ContinuationDecision(
                    should_continue=True, next_task_spec_path=ts_path,
                    reason="accepted_ready_to_dispatch")
            # Dispatched is also fine
            if dispatch.dispatch_status in ("dispatched",) and dispatch.terminal == False:
                return ContinuationDecision(
                    should_continue=True, next_task_spec_path=ts_path,
                    reason="accepted_dispatched")
            return ContinuationDecision(
                should_continue=False, stop_reason=f"dispatch_not_ready: {dispatch.dispatch_status}",
                reason="accepted but dispatch not in ready state")

        # Rule 10: partial can enter remediation
        if review.overall_judgment == "partial":
            ts_path = dispatch.next_task_spec_path or flow.next_task_spec_path or ""
            if not ts_path:
                return ContinuationDecision(
                    should_continue=False, stop_reason="partial_without_remediation_dispatch",
                    reason="partial but no remediation next_task_spec_path", fail_closed=True)
            if ts_path.endswith(".md"):
                return ContinuationDecision(
                    should_continue=False, stop_reason="markdown_remediation_task_spec",
                    reason="partial remediation path is .md", fail_closed=True)
            if dispatch.dispatch_status == "ready_to_dispatch" and dispatch.should_execute_next:
                return ContinuationDecision(
                    should_continue=True, next_task_spec_path=ts_path,
                    reason="partial_remediation_ready_to_dispatch")
            return ContinuationDecision(
                should_continue=False, stop_reason=f"remediation_dispatch_not_ready",
                reason="partial but dispatch not in ready state")

        return ContinuationDecision(
            should_continue=False, stop_reason="no_matching_rule",
            reason=f"unhandled state: {review.overall_judgment}", fail_closed=True)

    # ── Replay ────────────────────────────────────────────────────────

    def replay_pack(self, pack_name: str, review: ReviewDecision,
                    flow: FlowOutcomeDecision, dispatch: DispatchDecision,
                    evidence: EvidenceState, historical_observed: str) -> dict:
        """Replay a single historical pack through the controller."""
        decision = self.decide_continuation(review, flow, dispatch, evidence)
        return {
            "pack_name": pack_name,
            "observed_status": historical_observed,
            "controller_decision": {
                "should_continue": decision.should_continue,
                "next_task_spec_path": decision.next_task_spec_path,
                "reason": decision.reason,
                "stop_reason": decision.stop_reason,
                "fail_closed": decision.fail_closed,
            },
        }


def ingest_review_from_gpt_result(text: str) -> ReviewDecision:
    """Parse GPT_REVIEW_RESULT.md into structured ReviewDecision."""
    import re
    rd = ReviewDecision()
    m = re.search(r"REVIEW_RUN_ID:\s*(\S+)", text)
    if m: rd.review_run_id = m.group(1)
    m = re.search(r"Overall Judgment:\s*(\S+)", text)
    if m: rd.overall_judgment = m.group(1).lower().rstrip(",:;.")
    lower = text.lower()
    rd.human_required = "human_required" in lower and "human required: yes" in lower
    rd.blocked = rd.overall_judgment == "blocked"
    rd.production_promotion_approved = "production promotion approved: yes" in lower
    rd.contract_freeze_approved = "contract freeze approved: yes" in lower
    m = re.search(r"Required Next Action:\s*(.+)", text)
    if m: rd.required_next_action = m.group(1).strip()
    return rd


def replay_from_pack(controller: RunUntilTerminalController, pack_path: Path, case_id: str) -> dict:
    """Replay a real historical pack by reading its evidence files."""
    result = {
        "case_id": case_id,
        "source_pack": str(pack_path.relative_to(ROOT)),
        "files_found": [],
        "files_missing": [],
    }

    # Try to read FLOW_OUTCOME.json
    fo_path = pack_path / "FLOW_OUTCOME.json"
    if fo_path.exists():
        try:
            fo = json.loads(fo_path.read_text(encoding="utf-8", errors="replace"))
            result["files_found"].append("FLOW_OUTCOME.json")
            result["flow_business_decision"] = fo.get("business_decision", "unknown")
            result["flow_allow_next_stage"] = fo.get("allow_next_stage", False)
            result["flow_next_stage"] = fo.get("next_stage", "")
            result["flow_next_task_spec_path"] = fo.get("next_task_spec_path", "")
            result["flow_terminal"] = fo.get("terminal", True)
        except Exception as e:
            result["files_missing"].append("FLOW_OUTCOME.json (read error: %s)" % str(e)[:60])
    else:
        result["files_missing"].append("FLOW_OUTCOME.json")

    # Try to read DISPATCH_RESULT.json
    dr_path = pack_path / "DISPATCH_RESULT.json"
    if dr_path.exists():
        try:
            dr = json.loads(dr_path.read_text(encoding="utf-8", errors="replace"))
            result["files_found"].append("DISPATCH_RESULT.json")
            result["dispatch_status"] = dr.get("dispatch_status", "stopped")
            result["dispatch_terminal"] = dr.get("terminal", True)
            result["dispatch_should_execute_next"] = dr.get("should_execute_next", False)
            result["dispatch_next_task_spec_path"] = dr.get("next_task_spec_path", "")
        except Exception as e:
            result["files_missing"].append("DISPATCH_RESULT.json (read error: %s)" % str(e)[:60])
    else:
        result["files_missing"].append("DISPATCH_RESULT.json")

    # Try to read GPT_REVIEW_RESULT.md
    gr_path = pack_path / "GPT_REVIEW_RESULT.md"
    if gr_path.exists():
        try:
            result["files_found"].append("GPT_REVIEW_RESULT.md")
            gr_text = gr_path.read_text(encoding="utf-8", errors="replace")[:500]
            import re
            m = re.search(r"Overall Judgment:\s*(\S+)", gr_text)
            result["gpt_overall_judgment"] = m.group(1).lower().rstrip(",:;.") if m else "unknown"
        except Exception:
            result["files_missing"].append("GPT_REVIEW_RESULT.md (read error)")
    else:
        result["files_missing"].append("GPT_REVIEW_RESULT.md")

    # Try to read EVIDENCE_INTEGRITY_RESULT.json
    ei_path = pack_path / "EVIDENCE_INTEGRITY_RESULT.json"
    if ei_path.exists():
        try:
            ei = json.loads(ei_path.read_text(encoding="utf-8", errors="replace"))
            result["files_found"].append("EVIDENCE_INTEGRITY_RESULT.json")
            result["evidence_ready"] = ei.get("ready_for_review", False)
            result["evidence_failures"] = ei.get("failures", [])
        except Exception:
            result["files_missing"].append("EVIDENCE_INTEGRITY_RESULT.json (read error)")

    # Try to read TEST_OUTPUT.md
    to_path = pack_path / "TEST_OUTPUT.md"
    if to_path.exists():
        try:
            to_text = to_path.read_text(encoding="utf-8", errors="replace")[:500]
            result["files_found"].append("TEST_OUTPUT.md")
            import re
            m = re.search(r"(\d+) failed", to_text)
            result["tests_failed"] = int(m.group(1)) if m else 0
        except Exception:
            result["files_missing"].append("TEST_OUTPUT.md (read error)")

    # Build controller decision from extracted evidence
    review = ReviewDecision(
        overall_judgment=result.get("gpt_overall_judgment", "unknown"),
        human_required=False,
        blocked=result.get("gpt_overall_judgment") == "blocked",
    )
    flow = FlowOutcomeDecision(
        business_decision=result.get("flow_business_decision", "unknown"),
        allow_next_stage=result.get("flow_allow_next_stage", False),
        next_stage=result.get("flow_next_stage", ""),
        next_task_spec_path=result.get("flow_next_task_spec_path", ""),
        terminal=result.get("flow_terminal", True),
    )
    dispatch = DispatchDecision(
        dispatch_status=result.get("dispatch_status", "stopped"),
        should_execute_next=result.get("dispatch_should_execute_next", False),
        terminal=result.get("dispatch_terminal", True),
        next_task_spec_path=result.get("dispatch_next_task_spec_path", ""),
    )
    evidence = EvidenceState(
        tests_failed=result.get("tests_failed", 0),
        evidence_gate_ready=result.get("evidence_ready", True),
    )

    decision = controller.decide_continuation(review, flow, dispatch, evidence)
    result["controller_decision"] = {
        "should_continue": decision.should_continue,
        "next_task_spec_path": decision.next_task_spec_path,
        "reason": decision.reason,
        "stop_reason": decision.stop_reason,
        "fail_closed": decision.fail_closed,
    }
    return result


def replay_history_from_reports(controller: RunUntilTerminalController = None) -> list[dict]:
    """Scan _reports/ for real historical packs and replay each through the controller."""
    if controller is None:
        controller = RunUntilTerminalController()

    results = []

    # Scan known pack directories
    pack_dirs = [
        ("gca-phase1", ROOT / "_reports" / "gca-phase1"),
        ("gca-phase2a", ROOT / "_reports" / "gca-phase2a"),
        ("gca-phase2b", ROOT / "_reports" / "gca-phase2b"),
        ("gca-phase3", ROOT / "_reports" / "gca-phase3"),
        ("gca-phase3-freeze-prep", ROOT / "_reports" / "gca-phase3" / "freeze-review-prep"),
        ("gca-phase3-phase-transition", ROOT / "_reports" / "gca-phase3" / "phase-transition-hardening"),
        ("gca-phase3-registry-prototype", ROOT / "_reports" / "gca-phase3" / "phase-registry-prototype"),
        ("gca-phase3-registry-enforcement", ROOT / "_reports" / "gca-phase3" / "phase-registry-enforcement-prep"),
        ("gca-phase3-guarded-enforcement", ROOT / "_reports" / "gca-phase3" / "phase-registry-guarded-enforcement"),
        ("gca-phase3-partial-remediation", ROOT / "_reports" / "gca-phase3" / "partial-remediation"),
        ("control-plane-skeleton", ROOT / "_reports" / "gca-phase3" / "control-plane-skeleton"),
        ("global-control-plane-diagnostic", ROOT / "_reports" / "gca-phase3" / "global-control-plane-diagnostic"),
    ]

    for case_id, pack_dir in pack_dirs:
        if pack_dir.exists():
            results.append(replay_from_pack(controller, pack_dir, case_id))

    return results


def replay_history(controller: RunUntilTerminalController = None) -> list[dict]:
    """Replay both real packs AND synthetic edge cases for full coverage."""
    results = replay_history_from_reports(controller)

    # Add synthetic edge cases not covered by real packs
    if controller is None:
        controller = RunUntilTerminalController()

    # blocked synthetic
    results.append(controller.replay_pack(
        "synthetic-blocked-stop",
        ReviewDecision(overall_judgment="blocked", blocked=True),
        FlowOutcomeDecision(business_decision="blocked", terminal=True),
        DispatchDecision(dispatch_status="stopped", terminal=True),
        EvidenceState(),
        "SYNTHETIC: correctly blocked"))

    # tests_failed synthetic
    results.append(controller.replay_pack(
        "synthetic-tests-failed",
        ReviewDecision(overall_judgment="accepted"),
        FlowOutcomeDecision(business_decision="accepted", allow_next_stage=True, next_stage="s3", terminal=False),
        DispatchDecision(dispatch_status="ready_to_dispatch", should_execute_next=True, terminal=False, next_task_spec_path="/t/S3_TASKSPEC.json"),
        EvidenceState(tests_failed=2, evidence_gate_ready=True),
        "SYNTHETIC: should fail-closed"))

    # production promotion synthetic
    results.append(controller.replay_pack(
        "synthetic-production-promotion",
        ReviewDecision(overall_judgment="accepted"),
        FlowOutcomeDecision(business_decision="accepted", allow_next_stage=True, next_stage="production_promotion_review", terminal=False),
        DispatchDecision(dispatch_status="ready_to_dispatch", should_execute_next=True, terminal=False, next_task_spec_path="/t/PROMO.json"),
        EvidenceState(tests_failed=0, evidence_gate_ready=True),
        "SYNTHETIC: requires human confirmation"))

    return results
    """Replay known historical decision points through the controller."""
    if controller is None:
        controller = RunUntilTerminalController()

    results = []

    # Case 1: GCA Phase 3 accepted -> should continue to freeze prep
    results.append(controller.replay_pack(
        "gca-phase3-accepted",
        ReviewDecision(overall_judgment="accepted", review_run_id="gca-phase3-20260602"),
        FlowOutcomeDecision(business_decision="accepted", allow_next_stage=True,
                          next_stage="contract_freeze_review_preparation", terminal=False),
        DispatchDecision(dispatch_status="ready_to_dispatch", should_execute_next=True,
                        terminal=False, next_task_spec_path="/t/CONTRACT_FREEZE_REVIEW_PREPARATION_TASKSPEC.json"),
        EvidenceState(tests_failed=0, evidence_gate_ready=True),
        "HISTORICAL: agent stopped, should have continued"))

    # Case 2: Freeze prep accepted -> should continue to freeze review
    results.append(controller.replay_pack(
        "freeze-review-prep-accepted",
        ReviewDecision(overall_judgment="accepted", review_run_id="contract-freeze-review-prep-20260602"),
        FlowOutcomeDecision(business_decision="accepted", allow_next_stage=True,
                          next_stage="contract_freeze_review", terminal=False),
        DispatchDecision(dispatch_status="ready_to_dispatch", should_execute_next=True,
                        terminal=False, next_task_spec_path="/t/CONTRACT_FREEZE_REVIEW_TASKSPEC.json"),
        EvidenceState(tests_failed=0, evidence_gate_ready=True),
        "HISTORICAL: agent stopped after prep accepted"))

    # Case 3: Guarded Enforcement partial -> should remediation
    results.append(controller.replay_pack(
        "guarded-enforcement-partial",
        ReviewDecision(overall_judgment="partial", review_run_id="phase-registry-guarded-enforcement-v2-20260603"),
        FlowOutcomeDecision(business_decision="partial", allow_next_stage=True,
                          next_stage="phase_registry_guarded_enforcement_v2_1_remediation", terminal=False),
        DispatchDecision(dispatch_status="ready_to_dispatch", should_execute_next=True, terminal=False,
                        next_task_spec_path="/t/PHASE_REGISTRY_GUARDED_ENFORCEMENT_V2_1_REMEDIATION_TASKSPEC.json"),
        EvidenceState(tests_failed=0, evidence_gate_ready=True),
        "HISTORICAL: agent stopped, should have remediation-dispatched"))

    # Case 4: blocked -> should stop
    results.append(controller.replay_pack(
        "blocked-stop",
        ReviewDecision(overall_judgment="blocked", blocked=True),
        FlowOutcomeDecision(business_decision="blocked", terminal=True),
        DispatchDecision(dispatch_status="stopped", terminal=True),
        EvidenceState(),
        "HISTORICAL: stopped correctly"))

    # Case 5: human_required -> should stop
    results.append(controller.replay_pack(
        "human_required-stop",
        ReviewDecision(overall_judgment="human_required", human_required=True),
        FlowOutcomeDecision(business_decision="human_required", terminal=True),
        DispatchDecision(dispatch_status="manual_confirm_required", terminal=True),
        EvidenceState(),
        "HISTORICAL: stopped correctly"))

    # Case 6: tests_failed -> fail-closed
    results.append(controller.replay_pack(
        "tests-failed-fail-closed",
        ReviewDecision(overall_judgment="accepted"),
        FlowOutcomeDecision(business_decision="accepted", allow_next_stage=True, next_stage="s3", terminal=False),
        DispatchDecision(dispatch_status="ready_to_dispatch", should_execute_next=True, terminal=False,
                        next_task_spec_path="/t/S3_TASKSPEC.json"),
        EvidenceState(tests_failed=2, evidence_gate_ready=True),
        "HISTORICAL: should have been fail-closed due to test failures"))

    # Case 7: evidence gate fail -> fail-closed
    results.append(controller.replay_pack(
        "evidence-gate-fail",
        ReviewDecision(overall_judgment="accepted"),
        FlowOutcomeDecision(business_decision="accepted", allow_next_stage=True, next_stage="s3", terminal=False),
        DispatchDecision(dispatch_status="ready_to_dispatch", should_execute_next=True, terminal=False,
                        next_task_spec_path="/t/S3_TASKSPEC.json"),
        EvidenceState(tests_failed=0, evidence_gate_ready=False),
        "HISTORICAL: should have been fail-closed due to evidence gate"))

    # Case 8: split-brain fail-closed
    results.append(controller.replay_pack(
        "split-brain-fail-closed",
        ReviewDecision(overall_judgment="accepted"),
        FlowOutcomeDecision(business_decision="accepted", allow_next_stage=True, next_stage="s3",
                          terminal=False, next_task_spec_path="/t/S3_TASKSPEC.json"),
        DispatchDecision(dispatch_status="ready_to_dispatch", should_execute_next=True, terminal=False,
                        next_task_spec_path="/t/WRONG_TASKSPEC.json"),
        EvidenceState(tests_failed=0, evidence_gate_ready=True),
        "HISTORICAL: should have been fail-closed due to split-brain"))

    # Case 9: production promotion -> human_required stop
    results.append(controller.replay_pack(
        "production-promotion-human-required",
        ReviewDecision(overall_judgment="accepted"),
        FlowOutcomeDecision(business_decision="accepted", allow_next_stage=True,
                          next_stage="production_promotion_review", terminal=False),
        DispatchDecision(dispatch_status="ready_to_dispatch", should_execute_next=True, terminal=False,
                        next_task_spec_path="/t/PRODUCTION_PROMOTION_REVIEW_TASKSPEC.json"),
        EvidenceState(tests_failed=0, evidence_gate_ready=True),
        "HISTORICAL: should NOT auto-continue, requires human"))

    # Case 10: missing next_task_spec_path fail-closed
    results.append(controller.replay_pack(
        "missing-path-fail-closed",
        ReviewDecision(overall_judgment="accepted"),
        FlowOutcomeDecision(business_decision="accepted", allow_next_stage=True, next_stage="s3", terminal=False),
        DispatchDecision(dispatch_status="ready_to_dispatch", should_execute_next=True, terminal=False,
                        next_task_spec_path=""),
        EvidenceState(tests_failed=0, evidence_gate_ready=True),
        "HISTORICAL: should have been fail-closed"))

    return results
