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
    profiles = _build_profiles(skill)
    return {
        **skill,
        "require_red_green_evidence": traits.get("require_red_green_evidence", False),
        "display_label": traits.get("display_label", skill.get("title") or skill.get("skill_id") or ""),
        **({"profiles": profiles} if profiles else {}),
    }


def _build_profiles(skill: dict[str, Any]) -> list[dict[str, Any]]:
    profiles: list[dict[str, Any]] = []
    seen_profiles: set[str] = set()
    for trigger in skill.get("triggers", []):
        for profile_trigger, traits in _GO_TRIGGER_PROFILES.items():
            if profile_trigger == trigger or profile_trigger.startswith(f"{trigger} "):
                if profile_trigger not in seen_profiles:
                    seen_profiles.add(profile_trigger)
                    profiles.append({
                        "profile_id": traits.get("dispatch_profile", profile_trigger),
                        "selected_trigger_label": profile_trigger,
                        "display_label": profile_trigger,
                        "read_only": traits.get("read_only", False),
                        "network_enabled": traits.get("network_enabled", False),
                    })
    return profiles


METHODOLOGY_DISPATCH: dict[str, dict[str, Any]] = {
    skill["skill_id"]: _enrich_skill(skill) for skill in list_methodology_skills()
}


def _custom_skill_to_methodology(skill: dict[str, Any]) -> dict[str, Any]:
    """Convert a runtime custom skill into a methodology entry (built-in shape).

    Keeps the same fields a built-in enriched skill exposes so downstream
    storage/validation treats custom skills identically.
    """
    triggers = list(skill.get("triggers") or [])
    return {
        "skill_id": str(skill.get("id") or ""),
        "title": str(skill.get("title") or skill.get("id") or ""),
        "source_path": "skills.json",
        "source_kind": "local_repository_asset",
        "triggers": triggers,
        "status": "registered",
        "require_red_green_evidence": bool(skill.get("requireRedGreenEvidence")),
        "display_label": triggers[0] if triggers else str(skill.get("title") or ""),
        "read_only": bool(skill.get("readOnly")),
        "network_enabled": bool(skill.get("networkEnabled")),
    }


def _custom_methodology_entries(runtime_dir: Any = None) -> list[dict[str, Any]]:
    """Load runtime custom skills as methodology entries; [] when none/unavailable."""
    if not runtime_dir:
        return []
    try:
        from .custom_skills import load_custom_skills

        return [_custom_skill_to_methodology(s) for s in load_custom_skills(runtime_dir)]
    except Exception:  # noqa: BLE001 - custom skills are optional, never break resolution
        return []


def _project_methodology_entries(
    runtime_dir: Any = None, project_id: str | None = None
) -> list[dict[str, Any]]:
    """Load project-scope custom skills as methodology entries; [] when none."""
    if not runtime_dir or not project_id:
        return []
    try:
        from .custom_skills import load_skills_at
        from .scope_resolver import Scope

        return [
            _custom_skill_to_methodology(s)
            for s in load_skills_at(runtime_dir, Scope.PROJECT, project_id)
        ]
    except Exception:  # noqa: BLE001 - project skills are optional, never break resolution
        return []


def _effective_run_constraints(
    runtime_dir: Any, project_id: str | None
) -> dict[str, Any] | None:
    """Deny-overrides constraints for a run: active skills + P0 rule hard denies.

    Returns ``{readOnly, networkEnabled, requireRedGreenEvidence}`` computed by
    folding the effective (scope-merged) skills under ``SKILL_POLICY`` and then
    applying every P0 rule (at any scope) as an unconditional hard deny. Returns
    ``None`` if resolution is unavailable, so callers degrade gracefully.
    """
    try:
        from .custom_skills import resolve_skills
        from .rules_config import collect_p0_rule_denies
        from .scope_resolver import SKILL_POLICY, resolve_capabilities

        skills = resolve_skills(runtime_dir, project_id)
        p0_denies = collect_p0_rule_denies(runtime_dir, project_id)
        return resolve_capabilities(skills.effective, SKILL_POLICY, hard_denies=p0_denies)
    except Exception:  # noqa: BLE001 - never break run dispatch on optional config
        return None


def resolve_methodology(
    requirement: str, runtime_dir: Any = None, project_id: str | None = None
) -> tuple[str, dict[str, Any] | None]:
    methodology = None
    effective = requirement
    selected_trigger = None
    custom_entries = _custom_methodology_entries(runtime_dir)
    project_entries = _project_methodology_entries(runtime_dir, project_id)
    if effective:
        stripped = effective.lstrip()
        leading = effective[: len(effective) - len(stripped)]
        first_token = stripped.split(None, 1)[0] if stripped.split(None, 1) else ""
        trigger_map: dict[str, dict[str, Any]] = {}
        for entry in METHODOLOGY_DISPATCH.values():
            for trigger in entry.get("triggers", []):
                trigger_map[trigger] = entry
        # Scope merge for the trigger map: global custom skills override built-ins,
        # then project-scope skills override global, so the most-specific scope's
        # @trigger wins and governs the run.
        for entry in custom_entries:
            for trigger in entry.get("triggers", []):
                trigger_map[trigger] = entry
        for entry in project_entries:
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

    # Deny-overrides: when resolving for a specific project, fold the effective
    # skills + P0 rules into hard constraints and tighten the methodology's
    # traits most-restrictively. Gated on project_id so that calls without a
    # project id stay byte-identical to today's behavior.
    if methodology is not None and project_id:
        constraints = _effective_run_constraints(runtime_dir, project_id)
        if constraints is not None:
            methodology = {
                **methodology,
                "constraints": constraints,
                # read-only wins; no-network wins; require-evidence wins.
                "read_only": bool(methodology.get("read_only")) or bool(constraints.get("readOnly")),
                "network_enabled": bool(methodology.get("network_enabled"))
                and bool(constraints.get("networkEnabled")),
                "require_red_green_evidence": bool(methodology.get("require_red_green_evidence"))
                or bool(constraints.get("requireRedGreenEvidence")),
            }
    return effective, methodology
