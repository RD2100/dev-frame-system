"""Read-only methodology dispatch matrix for dev-frame-system."""
from __future__ import annotations

from typing import Any

from .skill_registry import list_methodology_skills

_METHODOLOGY_TRAIT_OVERRIDES: dict[str, dict[str, Any]] = {
    "tdd": {
        "require_red_green_evidence": True,
        "display_label": "@tdd",
    },
    "go": {
        "display_label": "@go",
    },
}

_GO_TRIGGER_PROFILES: dict[str, dict[str, Any]] = {
    "@go read": {
        "dispatch_profile": "read-only",
        "read_only": True,
        "network_enabled": False,
    },
    "@go edit": {
        "dispatch_profile": "ai-dev",
        "read_only": False,
        "network_enabled": False,
    },
    "@go risky": {
        "dispatch_profile": "ai-risky",
        "read_only": False,
        "network_enabled": True,
    },
    "@go": {
        "dispatch_profile": "ai-dev",
        "read_only": False,
        "network_enabled": False,
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
    selected_trigger = None
    if effective:
        stripped = effective.lstrip()
        leading = effective[: len(effective) - len(stripped)]
        first_token = stripped.split(None, 1)[0] if stripped.split(None, 1) else ""
        trigger_map: dict[str, dict[str, Any]] = {}
        for entry in METHODOLOGY_DISPATCH.values():
            for trigger in entry.get("triggers", []):
                trigger_map[trigger] = entry

        matched_trigger = None
        for trigger in sorted(_GO_TRIGGER_PROFILES.keys(), key=len, reverse=True):
            if stripped.startswith(trigger):
                matched_trigger = trigger
                break

        if matched_trigger:
            methodology = trigger_map.get(matched_trigger) or trigger_map.get(first_token)
            if methodology:
                selected_trigger = matched_trigger
                effective = leading + stripped[len(matched_trigger):].lstrip()
        elif first_token:
            methodology = trigger_map.get(first_token)
            if methodology:
                for trigger in methodology.get("triggers", []):
                    if stripped.startswith(trigger):
                        effective = leading + stripped[len(trigger):].lstrip()
                        selected_trigger = trigger
                        break

        if methodology and selected_trigger and selected_trigger in _GO_TRIGGER_PROFILES:
            profile_traits = _GO_TRIGGER_PROFILES[selected_trigger]
            methodology = {
                **methodology,
                "selected_trigger": selected_trigger,
                "dispatch_profile": profile_traits.get("dispatch_profile"),
                "read_only": profile_traits.get("read_only", False),
                "network_enabled": profile_traits.get("network_enabled", False),
            }
    return effective, methodology
