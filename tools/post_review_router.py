"""Post-GPT Review Router: decide continue/remediation/stop/fail-closed."""
import json
from dataclasses import dataclass, asdict
from pathlib import Path
from gpt_review_decision_parser import GPTReviewDecision


@dataclass
class PostReviewRoute:
    review_run_id: str = ""
    route: str = "stop"  # continue | remediation | stop | human_required | fail_closed
    should_continue: bool = False
    next_stage: str = ""
    next_task_spec_path: str = ""
    reason: str = ""
    stop_reason: str = ""
    requires_taskspec_runner: bool = False
    safe_to_execute: bool = False
    forbidden_actions_detected: list = None
    terminal: bool = True

    def __post_init__(self):
        if self.forbidden_actions_detected is None:
            self.forbidden_actions_detected = []

    def to_dict(self):
        d = asdict(self)
        return d


def route_post_review(
    decision: GPTReviewDecision,
    dispatch_status: str = "",
    dispatch_terminal: bool = True,
    dispatch_should_execute_next: bool = False,
    dispatch_next_task_spec_path: str = "",
    flow_next_stage: str = "",
    high_risk: bool = False,
    tests_failed: int = 0,
) -> PostReviewRoute:
    """Route post-GPT-review decision to appropriate action."""
    r = PostReviewRoute()
    r.review_run_id = decision.review_run_id

    PRODUCTION_KEYWORDS = ["production_promotion", "production promotion", "contract_freeze_final"]

    # 1. Parse failure = fail-closed
    if decision.parse_status == "parse_failed":
        r.route = "fail_closed"
        r.should_continue = False
        r.terminal = True
        r.stop_reason = "gpt_review_parse_failed: " + (decision.parse_fail_reason or "unknown parse error")
        r.reason = r.stop_reason
        return r

    # 2. human_required = stop
    if decision.human_required or decision.overall_judgment == "human_required":
        r.route = "human_required"
        r.should_continue = False
        r.terminal = True
        r.stop_reason = "human_required"
        return r

    # 3. blocked = stop
    if decision.blocked or decision.overall_judgment == "blocked":
        r.route = "stop"
        r.should_continue = False
        r.terminal = True
        r.stop_reason = "blocked"
        return r

    # 4. production promotion = human_required stop
    if decision.production_promotion_approved:
        r.route = "human_required"
        r.should_continue = False
        r.terminal = True
        r.stop_reason = "production_promotion_requires_explicit_human_confirmation"
        return r

    # 5. tests_failed = fail-closed
    if tests_failed > 0:
        r.route = "fail_closed"
        r.should_continue = False
        r.terminal = True
        r.stop_reason = "tests_failed: %d" % tests_failed
        return r

    # 6. production promotion in next_stage = human_required
    if any(kw in (flow_next_stage or "").lower() for kw in PRODUCTION_KEYWORDS):
        r.route = "human_required"
        r.should_continue = False
        r.terminal = True
        r.stop_reason = "production_promotion_requires_human"
        return r

    # 7. high_risk = human_required
    if high_risk:
        r.route = "human_required"
        r.should_continue = False
        r.terminal = True
        r.stop_reason = "high_risk_requires_human"
        return r

    # 8. Validate next_task_spec_path
    ts_path = dispatch_next_task_spec_path
    if not ts_path:
        r.route = "fail_closed"
        r.should_continue = False
        r.terminal = True
        r.stop_reason = "missing_next_task_spec_path"
        return r
    if ts_path.endswith(".md"):
        r.route = "fail_closed"
        r.should_continue = False
        r.terminal = True
        r.stop_reason = "markdown_task_spec_rejected"
        return r

    # 9. accepted + ready_to_dispatch = continue
    if decision.accepted:
        if dispatch_status in ("ready_to_dispatch", "dispatched") and dispatch_should_execute_next and not dispatch_terminal:
            r.route = "continue"
            r.should_continue = True
            r.terminal = False
            r.next_task_spec_path = ts_path
            r.next_stage = flow_next_stage
            r.requires_taskspec_runner = True
            r.safe_to_execute = True
            r.reason = "accepted_ready_to_dispatch"
            return r
        r.route = "stop"
        r.should_continue = False
        r.terminal = True
        r.stop_reason = "dispatch_not_ready"
        return r

    # 10. partial + remediation = continue
    if decision.partial and decision.ready_for_remediation:
        if dispatch_status in ("ready_to_dispatch", "dispatched") and dispatch_should_execute_next and not dispatch_terminal:
            r.route = "remediation"
            r.should_continue = True
            r.terminal = False
            r.next_task_spec_path = ts_path
            r.next_stage = flow_next_stage
            r.requires_taskspec_runner = True
            r.safe_to_execute = True
            r.reason = "partial_remediation_ready_to_dispatch"
            return r

    # 11. partial without remediation = fail-closed
    if decision.partial and not decision.ready_for_remediation:
        r.route = "fail_closed"
        r.should_continue = False
        r.terminal = True
        r.stop_reason = "partial_without_remediation_taskspec"
        return r

    # 12. default = stop
    r.route = "stop"
    r.should_continue = False
    r.terminal = True
    r.stop_reason = "no_matching_routing_rule"
    return r
