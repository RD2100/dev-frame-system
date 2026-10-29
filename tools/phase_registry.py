"""Phase Registry Prototype v1 — Declarative stage graph resolver.
Shadow mode: compares registry decisions against current hardcoded logic.
Does NOT replace production dispatch paths.
"""
import json
import yaml
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


ROOT = Path(__file__).resolve().parent
REGISTRY_PATH = ROOT / "PHASE_REGISTRY.yaml"


@dataclass
class StageDef:
    name: str
    expected_taskspec: str
    generator: str
    auto_dispatch: bool
    requires_human_confirmation: bool
    production_promotion_allowed: bool
    contract_freeze_approved_required: bool
    unknown_stage_policy: str
    transitions: dict

    @classmethod
    def from_dict(cls, name: str, data: dict):
        return cls(
            name=name,
            expected_taskspec=data.get("expected_taskspec", ""),
            generator=data.get("generator", ""),
            auto_dispatch=data.get("auto_dispatch", False),
            requires_human_confirmation=data.get("requires_human_confirmation", False),
            production_promotion_allowed=data.get("production_promotion_allowed", False),
            contract_freeze_approved_required=data.get("contract_freeze_approved_required", False),
            unknown_stage_policy=data.get("unknown_stage_policy", "fail_closed"),
            transitions=data.get("transitions", {}),
        )


@dataclass
class RegistryDecision:
    """Decision produced by the registry resolver."""
    dispatch_status: str = "stopped"
    terminal: bool = True
    should_execute_next: bool = False
    next_stage: str = ""
    required_next_action: str = ""
    reason: str = ""
    production_promotion_allowed: bool = False
    expected_taskspec: str = ""
    generator: str = ""


@dataclass
class ShadowResult:
    """Result of shadow comparison between registry and current logic."""
    current_dispatch_status: str = ""
    registry_dispatch_status: str = ""
    current_terminal: bool = True
    registry_terminal: bool = True
    current_should_execute: bool = False
    registry_should_execute: bool = False
    match: bool = False
    mismatches: list = field(default_factory=list)


class PhaseRegistry:
    """Load and resolve the PHASE_REGISTRY.yaml."""

    def __init__(self, path: Path = REGISTRY_PATH):
        if not path.exists():
            raise RuntimeError("PHASE_REGISTRY.yaml MISSING — fail-closed")
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        self.version = data.get("registry_version", "unknown")
        self.mode = data.get("registry_mode", "shadow")
        self.global_rules = data.get("global", {})
        self.stages: dict[str, StageDef] = {}
        for name, stage_data in data.get("stages", {}).items():
            self.stages[name] = StageDef.from_dict(name, stage_data)

    def get_stage(self, name: str) -> Optional[StageDef]:
        return self.stages.get(name)

    def resolve(self, business_decision: str, allow_next_stage: bool,
                next_stage: str, next_task_spec_path: str = "",
                human_required: bool = False) -> RegistryDecision:
        """Resolve next action from registry. Follows global decision_priority."""
        decision = RegistryDecision()
        priority = self.global_rules.get("decision_priority", ["human_required", "blocked", "accepted"])

        # 1. human_required always stops
        if human_required or business_decision == "human_required":
            decision.dispatch_status = "manual_confirm_required"
            decision.terminal = True
            decision.should_execute_next = False
            decision.reason = "human_required — registry global rule"
            return decision

        # 2. blocked always stops
        if business_decision == "blocked":
            decision.dispatch_status = "stopped"
            decision.terminal = True
            decision.should_execute_next = False
            decision.reason = "business_blocked — registry global rule"
            return decision

        # 3. accepted + allow_next_stage=true
        if business_decision == "accepted" and allow_next_stage:
            # Reject .md TaskSpec paths
            if next_task_spec_path and next_task_spec_path.endswith(".md"):
                decision.dispatch_status = "failed"
                decision.terminal = True
                decision.reason = f"MARKDOWN_TASKSPEC_REJECTED: {next_task_spec_path} — registry rule"
                return decision

            # Require explicit next_stage
            if self.global_rules.get("require_explicit_next_stage_for_dispatch", True):
                if not next_stage:
                    decision.dispatch_status = "failed"
                    decision.terminal = True
                    decision.reason = "MISSING_NEXT_STAGE — registry rule"
                    return decision

            stage = self.get_stage(next_stage)
            if stage is None:
                decision.dispatch_status = "failed"
                decision.terminal = True
                decision.reason = f"UNMAPPED_NEXT_STAGE: {next_stage} — registry fail-closed"
                return decision

            # Registry safety enforcement: requires_human_confirmation → human_required
            if stage.requires_human_confirmation:
                decision.dispatch_status = "manual_confirm_required"
                decision.terminal = True
                decision.should_execute_next = False
                decision.next_stage = next_stage
                decision.expected_taskspec = stage.expected_taskspec
                decision.generator = stage.generator
                decision.reason = f"requires_human_confirmation: {next_stage} — registry forced human_required"
                return decision

            # Registry safety enforcement: auto_dispatch=false → stop (not auto-proceed)
            if not stage.auto_dispatch:
                decision.dispatch_status = "stopped"
                decision.terminal = True
                decision.should_execute_next = False
                decision.next_stage = next_stage
                decision.expected_taskspec = stage.expected_taskspec
                decision.generator = stage.generator
                decision.reason = f"auto_dispatch=false: {next_stage} — requires explicit confirmation"
                return decision

            # Registry safety enforcement: contract_freeze_approved_required
            if stage.contract_freeze_approved_required:
                decision.dispatch_status = "manual_confirm_required"
                decision.terminal = True
                decision.should_execute_next = False
                decision.next_stage = next_stage
                decision.expected_taskspec = stage.expected_taskspec
                decision.generator = stage.generator
                decision.reason = f"contract_freeze_approved_required: {next_stage} — must have explicit freeze approval"
                return decision

            # Registry safety enforcement: production_promotion not allowed → check
            if stage.production_promotion_allowed:
                decision.production_promotion_allowed = True  # flag for audit

            decision.dispatch_status = "ready_to_dispatch"
            decision.terminal = False
            decision.should_execute_next = True
            decision.next_stage = next_stage
            decision.expected_taskspec = stage.expected_taskspec
            decision.generator = stage.generator
            decision.reason = f"accepted — registry transition to {next_stage}"
            return decision

        # 4. unknown — fail-closed
        decision.dispatch_status = "stopped"
        decision.terminal = True
        decision.reason = f"no_matching_registry_rule: business={business_decision} allow={allow_next_stage}"
        return decision


def shadow_compare(registry: PhaseRegistry, business_decision: str,
                   allow_next_stage: bool, next_stage: str,
                   current_dispatch_status: str, current_terminal: bool,
                   current_should_execute: bool, next_task_spec_path: str = "",
                   human_required: bool = False) -> ShadowResult:
    """Compare registry decision against current hardcoded logic outcome.
    Returns ShadowResult with match/mismatch details."""
    reg = registry.resolve(business_decision, allow_next_stage, next_stage, next_task_spec_path, human_required)
    result = ShadowResult()
    result.current_dispatch_status = current_dispatch_status
    result.registry_dispatch_status = reg.dispatch_status
    result.current_terminal = current_terminal
    result.registry_terminal = reg.terminal
    result.current_should_execute = current_should_execute
    result.registry_should_execute = reg.should_execute_next

    mismatches = []
    if current_dispatch_status != reg.dispatch_status:
        mismatches.append(f"dispatch_status: current={current_dispatch_status} registry={reg.dispatch_status}")
    if current_terminal != reg.terminal:
        mismatches.append(f"terminal: current={current_terminal} registry={reg.terminal}")
    if current_should_execute != reg.should_execute_next:
        mismatches.append(f"should_execute_next: current={current_should_execute} registry={reg.should_execute_next}")

    result.match = len(mismatches) == 0
    result.mismatches = mismatches

    # In shadow mode, mismatch does NOT block — it only logs for audit
    return result


def load_registry() -> PhaseRegistry:
    """Load the PHASE_REGISTRY.yaml. Fail-closed if missing/corrupt."""
    return PhaseRegistry(REGISTRY_PATH)


# ==================================================================
# Guarded Enforcement
# ==================================================================

@dataclass
class GuardedResult:
    """Result of guarded enforcement: registry + hardcoded dual-path resolution."""
    mode: str = "guarded_enforcement"
    registry_decision: dict = field(default_factory=dict)
    hardcoded_decision: dict = field(default_factory=dict)
    agreement: bool = False
    dispatch_status: str = "failed"
    should_execute_next: bool = False
    terminal: bool = True
    next_stage: str = ""
    next_task_spec_path: str = ""
    reason: str = ""
    mismatch_fields: list = field(default_factory=list)


def resolve_guarded_transition(
    registry: PhaseRegistry,
    business_decision: str,
    allow_next_stage: bool,
    next_stage: str,
    next_task_spec_path: str,
    hardcoded_dispatch_status: str,
    hardcoded_terminal: bool,
    hardcoded_should_execute: bool,
    hardcoded_next_stage: str = "",
    human_required: bool = False,
) -> GuardedResult:
    """Guarded Enforcement: registry primary, hardcoded secondary guard.
    Both must agree. Mismatch = fail-closed, no fallback.
    """
    result = GuardedResult()

    # Registry decision (primary)
    reg_dec = registry.resolve(business_decision, allow_next_stage, next_stage, next_task_spec_path, human_required)
    result.registry_decision = {
        "dispatch_status": reg_dec.dispatch_status,
        "should_execute_next": reg_dec.should_execute_next,
        "terminal": reg_dec.terminal,
        "next_stage": reg_dec.next_stage,
        "next_task_spec_path": reg_dec.expected_taskspec,
        "reason": reg_dec.reason,
        "production_promotion_allowed": reg_dec.production_promotion_allowed,
    }

    # Hardcoded decision (secondary)
    result.hardcoded_decision = {
        "dispatch_status": hardcoded_dispatch_status,
        "should_execute_next": hardcoded_should_execute,
        "terminal": hardcoded_terminal,
        "next_stage": hardcoded_next_stage or next_stage,
        "next_task_spec_path": next_task_spec_path,
        "production_promotion_allowed": False,
        "reason": "hardcoded_driver",
    }

    # v2: Compare 6 key fields with normalization
    def _normalize_status(s):
        if s in ("dispatched", "ready_to_dispatch"):
            return "proceed"
        return s

    # Store normalized values
    result.registry_decision["dispatch_status_normalized"] = _normalize_status(result.registry_decision["dispatch_status"])
    result.hardcoded_decision["dispatch_status_normalized"] = _normalize_status(result.hardcoded_decision["dispatch_status"])
    result.registry_decision["next_task_spec_path_basename"] = Path(result.registry_decision.get("next_task_spec_path", "")).name
    result.hardcoded_decision["next_task_spec_path_basename"] = Path(result.hardcoded_decision.get("next_task_spec_path", "")).name

    mismatches = []
    # 1. dispatch_status_normalized
    if result.registry_decision["dispatch_status_normalized"] != result.hardcoded_decision["dispatch_status_normalized"]:
        mismatches.append("dispatch_status")
    # 2. should_execute_next
    if result.registry_decision["should_execute_next"] != result.hardcoded_decision["should_execute_next"]:
        mismatches.append("should_execute_next")
    # 3. terminal
    if result.registry_decision["terminal"] != result.hardcoded_decision["terminal"]:
        mismatches.append("terminal")
    # 4. next_stage
    if result.registry_decision["next_stage"] != result.hardcoded_decision["next_stage"]:
        mismatches.append("next_stage")
    # 5. next_task_spec_path basename
    if result.registry_decision["next_task_spec_path_basename"] != result.hardcoded_decision["next_task_spec_path_basename"]:
        mismatches.append("next_task_spec_path")
    # 6. production_promotion_allowed
    if result.registry_decision.get("production_promotion_allowed", False) != result.hardcoded_decision.get("production_promotion_allowed", False):
        mismatches.append("production_promotion_allowed")

    result.mismatch_fields = mismatches
    result.agreement = len(mismatches) == 0

    if result.agreement:
        result.dispatch_status = result.registry_decision["dispatch_status"]
        result.should_execute_next = result.registry_decision["should_execute_next"]
        result.terminal = result.registry_decision["terminal"]
        result.next_stage = result.registry_decision["next_stage"]
        result.next_task_spec_path = result.registry_decision["next_task_spec_path"]
        result.reason = "guarded_enforcement_agreement"
    else:
        # Mismatch: fail-closed, no fallback
        result.dispatch_status = "failed"
        result.should_execute_next = False
        result.terminal = True
        result.reason = f"REGISTRY_HARDCODED_MISMATCH: {', '.join(mismatches)}"

    return result
