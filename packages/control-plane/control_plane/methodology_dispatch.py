"""Read-only methodology dispatch matrix for dev-frame-system."""
from __future__ import annotations

from typing import Any

from .skill_registry import list_methodology_skills

_METHODOLOGY_TRAIT_OVERRIDES: dict[str, dict[str, Any]] = {
    "tdd": {
        "require_red_green_evidence": True,
        "display_label": "@tdd",
    },
}


def _enrich_skill(skill: dict[str, Any]) -> dict[str, Any]:
    traits = _METHODOLOGY_TRAIT_OVERRIDES.get(skill.get("skill_id"), {})
    return {
        **skill,
        "require_red_green_evidence": traits.get("require_red_green_evidence", False),
        "display_label": traits.get("display_label", skill.get("title") or skill.get("skill_id") or ""),
    }


METHODOLOGY_DISPATCH: dict[str, dict[str, Any]] = {
    skill["skill_id"]: _enrich_skill(skill) for skill in list_methodology_skills()
}


def resolve_methodology(requirement: str) -> tuple[str, dict[str, Any] | None]:
    methodology = None
    effective = requirement
    if effective:
        stripped = effective.lstrip()
        leading = effective[: len(effective) - len(stripped)]
        first_token = stripped.split(None, 1)[0] if stripped.split(None, 1) else ""
        trigger_map: dict[str, dict[str, Any]] = {}
        for entry in METHODOLOGY_DISPATCH.values():
            for trigger in entry.get("triggers", []):
                trigger_map[trigger] = entry
        methodology = trigger_map.get(first_token)
        if methodology:
            for trigger in methodology.get("triggers", []):
                if stripped.startswith(trigger):
                    effective = leading + stripped[len(trigger):].lstrip()
                    break
    return effective, methodology
