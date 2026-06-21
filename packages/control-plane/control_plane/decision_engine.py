"""Decision engine for rdgoal total-control orchestration."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from .project_contract import ProjectContract


class DecisionMode(str, Enum):
    AUTO_EXECUTE = "auto_execute"
    SNAPSHOT_EXECUTE = "snapshot_execute"
    RECOMMEND_EXECUTE = "recommend_execute"
    DRAFT_ONLY = "draft_only"
    HARD_STOP = "hard_stop"


DESTRUCTIVE_LOCAL_KEYWORDS = {
    "delete",
    "remove",
    "overwrite",
    "replace",
    "refactor_destructive",
    "config_edit",
    "migration",
    "dep_upgrade",
}

DIRECTION_KEYWORDS = {
    "direction",
    "choose",
    "architecture",
    "design",
    "strategy",
    "unclear",
    "ambiguous",
}

EXTERNAL_SIDE_EFFECT_KEYWORDS = {
    "publish",
    "release",
    "deploy",
    "push",
    "remote",
    "production",
    "payment",
    "spend",
    "billing",
    "database drop",
    "drop database",
}

SECRET_KEYWORDS = {
    "secret",
    "token",
    ".env",
    ".pem",
    "api key",
    "credential",
}


@dataclass
class OperationRequest:
    operation: str
    targets: list[str] = field(default_factory=list)
    summary: str = ""

    @property
    def haystack(self) -> str:
        return " ".join([self.operation, self.summary, *self.targets]).lower()


@dataclass
class Decision:
    mode: DecisionMode
    operation: str
    reason: str
    recommended_path: str = ""
    requires_snapshot: bool = False
    dispatch_allowed: bool = True


class DecisionEngine:
    """Choose how the controller should proceed without routine human prompts."""

    def decide(self, contract: ProjectContract, request: OperationRequest) -> Decision:
        text = request.haystack

        if _hits_secret_boundary(text):
            return Decision(
                mode=DecisionMode.HARD_STOP,
                operation=request.operation,
                reason="Secret or credential boundary hit; do not draft, read, or expose secrets.",
                dispatch_allowed=False,
            )

        if _hits_stop_line(contract, text) or _hits_external_side_effect(text):
            return Decision(
                mode=DecisionMode.DRAFT_ONLY,
                operation=request.operation,
                reason="External or real-world irreversible effect; prepare an execution draft only.",
                recommended_path="Prepare scripts, checklist, and rollback notes without performing the live action.",
                dispatch_allowed=False,
            )

        if contract.autonomy_level == "green_only" and _hits_non_green(text):
            return Decision(
                mode=DecisionMode.DRAFT_ONLY,
                operation=request.operation,
                reason="Contract allows only fully reversible auto-execution.",
                recommended_path="Prepare the recommended change for later review.",
                dispatch_allowed=False,
            )

        if contract.autonomy_level == "supervised" and _hits_non_green(text):
            return Decision(
                mode=DecisionMode.DRAFT_ONLY,
                operation=request.operation,
                reason="Contract is supervised; non-routine actions become drafts.",
                recommended_path="Prepare a recommendation package instead of dispatching.",
                dispatch_allowed=False,
            )

        if _hits_destructive_local(text):
            return Decision(
                mode=DecisionMode.SNAPSHOT_EXECUTE,
                operation=request.operation,
                reason="Local destructive or costly action; snapshot first, then continue.",
                recommended_path="Use the smallest reversible change that preserves the working prototype.",
                requires_snapshot=True,
            )

        if _hits_direction_choice(text):
            return Decision(
                mode=DecisionMode.RECOMMEND_EXECUTE,
                operation=request.operation,
                reason="Direction choice delegated to controller policy.",
                recommended_path=_recommended_direction(contract),
            )

        return Decision(
            mode=DecisionMode.AUTO_EXECUTE,
            operation=request.operation,
            reason="Routine reversible work inside the project contract.",
            recommended_path="Proceed with the existing project workflow.",
        )


def _hits_any(text: str, words: set[str]) -> bool:
    return any(word in text for word in words)


def _hits_secret_boundary(text: str) -> bool:
    return _hits_any(text, SECRET_KEYWORDS) and ("read" in text or "expose" in text or ".env" in text)


def _hits_external_side_effect(text: str) -> bool:
    return _hits_any(text, EXTERNAL_SIDE_EFFECT_KEYWORDS)


def _hits_destructive_local(text: str) -> bool:
    return _hits_any(text, DESTRUCTIVE_LOCAL_KEYWORDS)


def _hits_direction_choice(text: str) -> bool:
    return _hits_any(text, DIRECTION_KEYWORDS)


def _hits_non_green(text: str) -> bool:
    return _hits_external_side_effect(text) or _hits_destructive_local(text) or _hits_direction_choice(text)


def _hits_stop_line(contract: ProjectContract, text: str) -> bool:
    return any(line.lower() in text for line in contract.stop_lines if line.strip())


def _recommended_direction(contract: ProjectContract) -> str:
    if contract.prototype_bias.prefer_existing_stack:
        return "Choose the path closest to the existing architecture and produce a working MVP first."
    return "Choose the smallest coherent MVP path and record alternatives for later tuning."
