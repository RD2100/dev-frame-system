"""Project contracts for rdgoal total-control orchestration.

A contract tells the controller how to make routine direction and risk
decisions without asking the human on every step.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml


DEFAULT_STOP_LINES = [
    "spend money",
    "publish production release",
    "delete remote production data",
    "expose secrets",
]

DEFAULT_NON_GOALS = [
    "Anything outside the stated requirement until the contract is updated.",
]


@dataclass
class DecisionPolicy:
    direction_choice: str = "choose_recommended_path"
    unclear_requirement: str = "infer_minimal_prototype"
    destructive_local_change: str = "snapshot_then_execute"
    architecture_choice: str = "prefer_existing_project_style"
    external_side_effect: str = "draft_only"


@dataclass
class PrototypeBias:
    prefer_working_mvp: bool = True
    prefer_existing_stack: bool = True
    leave_adjustment_notes: bool = True


@dataclass
class ProjectContract:
    project_id: str
    goal: str
    title: str = ""
    non_goals: list[str] = field(default_factory=lambda: list(DEFAULT_NON_GOALS))
    autonomy_level: str = "total_control"
    decision_policy: DecisionPolicy = field(default_factory=DecisionPolicy)
    prototype_bias: PrototypeBias = field(default_factory=PrototypeBias)
    stop_lines: list[str] = field(default_factory=lambda: list(DEFAULT_STOP_LINES))
    priority: int = 3
    owner: str = "you"
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    notes: str = ""

    @property
    def display_title(self) -> str:
        return self.title or self.project_id


def slugify_project_id(project_path: str | Path) -> str:
    """Create a stable schema-friendly id from a project path."""
    name = Path(project_path).resolve().name or "project"
    slug = re.sub(r"[^a-z0-9-]+", "-", name.lower()).strip("-")
    return slug or "project"


def _extract_yaml_block(text: str) -> dict[str, Any]:
    lines = text.splitlines()
    inside = False
    block: list[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("```yaml"):
            inside = True
            block = []
            continue
        if inside and stripped.startswith("```"):
            return yaml.safe_load("\n".join(block)) or {}
        if inside:
            block.append(line)
    raise ValueError("No fenced yaml contract block found.")


def _policy_from_dict(data: dict[str, Any] | None) -> DecisionPolicy:
    values = data or {}
    return DecisionPolicy(
        direction_choice=values.get("direction_choice", "choose_recommended_path"),
        unclear_requirement=values.get("unclear_requirement", "infer_minimal_prototype"),
        destructive_local_change=values.get("destructive_local_change", "snapshot_then_execute"),
        architecture_choice=values.get("architecture_choice", "prefer_existing_project_style"),
        external_side_effect=values.get("external_side_effect", "draft_only"),
    )


def _bias_from_dict(data: dict[str, Any] | None) -> PrototypeBias:
    values = data or {}
    return PrototypeBias(
        prefer_working_mvp=bool(values.get("prefer_working_mvp", True)),
        prefer_existing_stack=bool(values.get("prefer_existing_stack", True)),
        leave_adjustment_notes=bool(values.get("leave_adjustment_notes", True)),
    )


def contract_from_dict(data: dict[str, Any]) -> ProjectContract:
    return ProjectContract(
        project_id=data["project_id"],
        title=data.get("title", ""),
        goal=data["goal"],
        non_goals=list(data.get("non_goals") or DEFAULT_NON_GOALS),
        autonomy_level=data.get("autonomy_level", "total_control"),
        decision_policy=_policy_from_dict(data.get("decision_policy")),
        prototype_bias=_bias_from_dict(data.get("prototype_bias")),
        stop_lines=list(data.get("stop_lines") or DEFAULT_STOP_LINES),
        priority=int(data.get("priority", 3)),
        owner=data.get("owner", "you"),
        created_at=data.get("created_at", datetime.now(timezone.utc).isoformat()),
        notes=data.get("notes", ""),
    )


def validate_contract(contract: ProjectContract) -> list[str]:
    errors: list[str] = []
    if not re.match(r"^[a-z0-9][a-z0-9-]*$", contract.project_id):
        errors.append("project_id must be a lowercase slug.")
    if not contract.goal.strip():
        errors.append("goal is required.")
    if contract.autonomy_level not in {"total_control", "supervised", "green_only"}:
        errors.append(f"invalid autonomy_level: {contract.autonomy_level}")
    if contract.priority < 1:
        errors.append("priority must be >= 1.")
    return errors


def load_contract(path: str | Path) -> ProjectContract:
    text = Path(path).read_text(encoding="utf-8")
    data = _extract_yaml_block(text) if "```yaml" in text else yaml.safe_load(text)
    contract = contract_from_dict(data or {})
    errors = validate_contract(contract)
    if errors:
        raise ValueError(f"Invalid project contract {path}: {errors}")
    return contract


def render_contract_markdown(project_id: str, requirement: str) -> str:
    goal = " ".join(requirement.strip().split())
    now = datetime.now(timezone.utc).isoformat()
    data = {
        "project_id": project_id,
        "title": project_id,
        "goal": goal,
        "non_goals": list(DEFAULT_NON_GOALS),
        "autonomy_level": "total_control",
        "decision_policy": {
            "direction_choice": "choose_recommended_path",
            "unclear_requirement": "infer_minimal_prototype",
            "destructive_local_change": "snapshot_then_execute",
            "architecture_choice": "prefer_existing_project_style",
            "external_side_effect": "draft_only",
        },
        "prototype_bias": {
            "prefer_working_mvp": True,
            "prefer_existing_stack": True,
            "leave_adjustment_notes": True,
        },
        "stop_lines": list(DEFAULT_STOP_LINES),
        "priority": 3,
        "owner": "you",
        "created_at": now,
    }
    yaml_text = yaml.safe_dump(data, sort_keys=False, allow_unicode=False)
    return (
        f"# Project Contract -- {project_id}\n\n"
        "> Auto-derived by rdgoal. Edit this file when the project's direction changes.\n\n"
        "```yaml\n"
        f"{yaml_text}"
        "```\n\n"
        "## Operating intent\n\n"
        "The controller should keep moving toward a complete prototype. Directional "
        "choices use the recommended path, local destructive work is snapshotted "
        "before dispatch, and external irreversible work is prepared as a draft.\n"
    )
