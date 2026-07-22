"""Read-only methodology dispatch matrix for dev-frame-system."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .skill_registry import REPO_ROOT, list_methodology_skills

WORKFLOW_PROFILE_CONTRACT_VERSION = "workflow-profile.v1"
WORKFLOW_PROFILE_RESOLVER_VERSION = "workflow-profile-resolver.v1"
WORKFLOW_CANARY_CONTRACT_VERSION = "coding-workflow-canary.v1"
WORKFLOW_CANARY_MODE = "canary_only"
WORKFLOW_CANARY_SELECTION_SOURCE = "explicit_cli_opt_in"

_WORKFLOW_CANARY_STAGES = (
    ("pre", "intent", "intent-framing-gate"),
    ("post", "evidence", "evidence-driven-acceptance"),
)
_WORKFLOW_CANARY_BINDING_KEYS = (
    "contract_version",
    "mode",
    "selection_source",
    "policy_binding",
    "profile_binding",
    "stage_bindings",
)
_WORKFLOW_CANARY_KEYS = {
    *_WORKFLOW_CANARY_BINDING_KEYS,
    "status",
    "binding_fingerprint",
    "stage_results",
}
_WORKFLOW_CANARY_STAGE_EVIDENCE = {
    "intent": "task_spec_profile_bound",
    "evidence": "draft_execution_report_only",
}


class WorkflowCanaryError(ValueError):
    """Fail-closed workflow-canary policy or immutable-binding failure."""

_WORKFLOW_PROFILE_DEFINITIONS: dict[str, dict[str, Any]] = {
    "coding": {
        "profile_id": "governed-coding-v1",
        "profile_version": "1.0.0",
        "selection_source": "coding_workflow_entrypoint",
        "network_enabled": False,
        "require_red_green_evidence": True,
        "stages": [
            {
                "stage_id": "intent",
                "skill_id": "intent-framing-gate",
                "execution_mode": "instruction",
                "permissions": {"read": True, "write": False, "network": False, "credentials": False},
                "human_gate": "none",
                "required_artifacts": ["task_spec"],
                "required_evidence": ["requirement_alignment"],
            },
            {
                "stage_id": "implementation",
                "skill_id": "tdd",
                "execution_mode": "instruction",
                "permissions": {"read": True, "write": True, "network": False, "credentials": False},
                "human_gate": "none",
                "required_artifacts": ["actual_diff", "test_results"],
                "required_evidence": ["red_green_or_direct_verification"],
            },
            {
                "stage_id": "evidence",
                "skill_id": "evidence-driven-acceptance",
                "execution_mode": "advisory",
                "permissions": {"read": True, "write": False, "network": False, "credentials": False},
                "human_gate": "none",
                "required_artifacts": ["execution_report"],
                "required_evidence": ["verification_results"],
            },
            {
                "stage_id": "review",
                "skill_id": "review-governance-kernel",
                "execution_mode": "advisory",
                "permissions": {"read": True, "write": False, "network": False, "credentials": False},
                "human_gate": "none",
                "required_artifacts": ["review_report"],
                "required_evidence": ["independent_review", "gate_decision"],
            },
        ],
    },
    "paper": {
        "profile_id": "governed-paper-v1",
        "profile_version": "1.0.0",
        "selection_source": "paper_pipeline_entrypoint",
        "network_enabled": True,
        "require_red_green_evidence": False,
        "stages": [
            {
                "stage_id": "public_source_acquisition",
                "skill_id": "agent-reach",
                "execution_mode": "tool",
                "permissions": {"read": True, "write": False, "network": True, "credentials": False},
                "human_gate": "required_before_execution",
                "required_artifacts": ["source_inventory"],
                "required_evidence": ["public_source_log"],
                "external_adoption_required": True,
            },
            {
                "stage_id": "citation_lock",
                "skill_id": "context-pack-builder",
                "execution_mode": "instruction",
                "permissions": {"read": True, "write": True, "network": False, "credentials": False},
                "human_gate": "none",
                "required_artifacts": ["citation_lock"],
                "required_evidence": ["source_hashes"],
            },
            {
                "stage_id": "draft",
                "skill_id": "external-brain",
                "execution_mode": "instruction",
                "permissions": {"read": True, "write": True, "network": False, "credentials": False},
                "human_gate": "none",
                "required_artifacts": ["paper_draft"],
                "required_evidence": ["citation_coverage"],
            },
            {
                "stage_id": "fact_check",
                "skill_id": "evidence-driven-acceptance",
                "execution_mode": "advisory",
                "permissions": {"read": True, "write": False, "network": False, "credentials": False},
                "human_gate": "none",
                "required_artifacts": ["fact_check_report"],
                "required_evidence": ["locked_claim_invariants"],
            },
            {
                "stage_id": "expression_refinement",
                "skill_id": "humanize",
                "execution_mode": "instruction",
                "permissions": {"read": True, "write": True, "network": False, "credentials": False},
                "human_gate": "required_before_execution",
                "required_artifacts": ["invariant_diff"],
                "required_evidence": ["citations_numbers_formulas_names_claims_unchanged"],
                "external_adoption_required": True,
            },
            {
                "stage_id": "style_lint",
                "skill_id": "ai-check",
                "execution_mode": "advisory",
                "permissions": {"read": True, "write": False, "network": False, "credentials": False},
                "human_gate": "required_before_execution",
                "required_artifacts": ["style_diagnostic"],
                "required_evidence": ["diagnostic_only_no_authorship_claim"],
                "external_adoption_required": True,
            },
            {
                "stage_id": "review",
                "skill_id": "review-governance-kernel",
                "execution_mode": "advisory",
                "permissions": {"read": True, "write": False, "network": False, "credentials": False},
                "human_gate": "none",
                "required_artifacts": ["review_report"],
                "required_evidence": ["independent_review", "gate_decision"],
            },
        ],
    },
}

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


def resolve_workflow_profile(
    work_type: str | None,
    *,
    runtime_dir: Any = None,
    project_id: str | None = None,
) -> dict[str, Any]:
    """Resolve a planned-only profile from trusted structured context."""
    normalized_work_type = str(work_type or "").strip().lower()
    definition = _WORKFLOW_PROFILE_DEFINITIONS.get(normalized_work_type)
    if definition is None:
        unresolved = {
            "contract_version": WORKFLOW_PROFILE_CONTRACT_VERSION,
            "resolver_version": WORKFLOW_PROFILE_RESOLVER_VERSION,
            "profile_id": "unresolved",
            "profile_version": "1.0.0",
            "work_type": "generic",
            "selection_source": "unresolved_structured_context",
            "resolution_status": "human_required",
            "execution_state": "planned_only",
            "human_gate_required": True,
            "constraints": {
                "read_only": True,
                "network_enabled": False,
                "require_red_green_evidence": False,
            },
            "ordered_stages": [],
        }
        return _with_profile_fingerprint(unresolved)

    constraints = _resolved_profile_constraints(
        definition,
        runtime_dir=runtime_dir,
        project_id=project_id,
    )
    ordered_stages = [
        _resolved_profile_stage(stage, constraints)
        for stage in definition["stages"]
    ]
    human_gate_required = any(
        stage["human_gate"] != "none" or stage["availability"] != "registered"
        for stage in ordered_stages
    )
    profile = {
        "contract_version": WORKFLOW_PROFILE_CONTRACT_VERSION,
        "resolver_version": WORKFLOW_PROFILE_RESOLVER_VERSION,
        "profile_id": definition["profile_id"],
        "profile_version": definition["profile_version"],
        "work_type": normalized_work_type,
        "selection_source": definition["selection_source"],
        "resolution_status": "selected",
        "execution_state": "planned_only",
        "human_gate_required": human_gate_required,
        "constraints": constraints,
        "ordered_stages": ordered_stages,
    }
    return _with_profile_fingerprint(profile)


def _resolved_profile_constraints(
    definition: dict[str, Any],
    *,
    runtime_dir: Any,
    project_id: str | None,
) -> dict[str, bool]:
    constraints = {
        "read_only": False,
        "network_enabled": bool(definition["network_enabled"]),
        "require_red_green_evidence": bool(
            definition["require_red_green_evidence"]
        ),
    }
    if not project_id:
        return constraints
    effective = _effective_run_constraints(runtime_dir, project_id)
    if effective is None:
        return constraints
    constraints["read_only"] = bool(effective.get("readOnly"))
    constraints["network_enabled"] = (
        constraints["network_enabled"]
        and bool(effective.get("networkEnabled"))
    )
    constraints["require_red_green_evidence"] = (
        constraints["require_red_green_evidence"]
        or bool(effective.get("requireRedGreenEvidence"))
    )
    return constraints


def _resolved_profile_stage(
    definition: dict[str, Any],
    constraints: dict[str, bool],
) -> dict[str, Any]:
    permissions = dict(definition["permissions"])
    if constraints["read_only"]:
        permissions["write"] = False
    if not constraints["network_enabled"]:
        permissions["network"] = False
    permissions["credentials"] = False

    availability, source_path, skill_fingerprint = _skill_snapshot(
        str(definition["skill_id"]),
        external_adoption_required=bool(
            definition.get("external_adoption_required")
        ),
    )
    human_gate = str(definition["human_gate"])
    if availability != "registered":
        human_gate = "required_before_execution"
    return {
        "stage_id": str(definition["stage_id"]),
        "skill_id": str(definition["skill_id"]),
        "skill_source_path": source_path,
        "skill_fingerprint": skill_fingerprint,
        "availability": availability,
        "execution_mode": str(definition["execution_mode"]),
        "permissions": permissions,
        "human_gate": human_gate,
        "required_artifacts": list(definition["required_artifacts"]),
        "required_evidence": list(definition["required_evidence"]),
    }


def _skill_snapshot(
    skill_id: str,
    *,
    external_adoption_required: bool,
) -> tuple[str, str | None, str | None]:
    if external_adoption_required:
        return "not_adopted", None, None
    entry = METHODOLOGY_DISPATCH.get(skill_id)
    if not entry:
        return "missing", None, None
    source_path = str(entry.get("source_path") or "").strip()
    if not source_path:
        return "missing", None, None
    source = _existing_skill_source(source_path)
    if source is None:
        return "missing", source_path, None
    try:
        raw = source.read_bytes()
    except OSError:
        return "missing", source_path, None
    return (
        "registered",
        source_path,
        f"sha256:{hashlib.sha256(raw).hexdigest()}",
    )


def _existing_skill_source(source_path: str) -> Path | None:
    package_root = Path(__file__).resolve().parents[1]
    for root in (REPO_ROOT.resolve(), package_root.resolve()):
        candidate = (root / source_path).resolve()
        try:
            candidate.relative_to(root)
        except ValueError:
            continue
        if candidate.is_file():
            return candidate
    return None


def _with_profile_fingerprint(profile: dict[str, Any]) -> dict[str, Any]:
    canonical = json.dumps(
        profile,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return {
        **profile,
        "profile_fingerprint": f"sha256:{hashlib.sha256(canonical).hexdigest()}",
    }


def _read_workflow_canary_policy(
    runtime_dir: Any,
    project_id: str | None,
) -> tuple[Path, bytes]:
    if runtime_dir is None or not project_id:
        raise WorkflowCanaryError(
            "workflow canary requires a runtime directory and project id"
        )
    from .custom_skills import SKILLS_FILE
    from .scope_resolver import Scope
    from .scoped_store import scoped_path

    try:
        path = scoped_path(runtime_dir, SKILLS_FILE, Scope.PROJECT, project_id)
        raw = path.read_bytes()
    except (OSError, ValueError) as exc:
        raise WorkflowCanaryError(
            "workflow canary project skill policy is missing or unreadable"
        ) from exc
    _validate_workflow_canary_policy(raw)
    return path.resolve(), raw


def _validate_workflow_canary_policy(raw: bytes) -> None:
    from .custom_skills import _coerce_skill

    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise WorkflowCanaryError(
            "workflow canary project skill policy is malformed"
        ) from exc
    if (
        not isinstance(payload, dict)
        or payload.get("version") != 1
        or not isinstance(payload.get("skills"), list)
        or not payload["skills"]
    ):
        raise WorkflowCanaryError(
            "workflow canary project skill policy has an invalid structure"
        )
    normalized = [_coerce_skill(item) for item in payload["skills"]]
    if any(item is None for item in normalized):
        raise WorkflowCanaryError(
            "workflow canary project skill policy contains an invalid skill"
        )
    skill_ids = [str(item["id"]) for item in normalized if item is not None]
    if len(skill_ids) != len(set(skill_ids)):
        raise WorkflowCanaryError(
            "workflow canary project skill policy contains duplicate skill ids"
        )


def _validate_workflow_canary_profile(profile: dict[str, Any]) -> None:
    constraints = profile.get("constraints")
    if (
        profile.get("profile_id") != "governed-coding-v1"
        or profile.get("work_type") != "coding"
        or profile.get("resolution_status") != "selected"
        or profile.get("execution_state") != "planned_only"
        or not isinstance(constraints, dict)
        or constraints.get("read_only") is not True
        or constraints.get("network_enabled") is not False
    ):
        raise WorkflowCanaryError(
            "workflow canary requires the offline read-only governed coding profile"
        )


def _workflow_canary_stage_binding(
    profile: dict[str, Any],
    phase: str,
    stage_id: str,
    skill_id: str,
) -> dict[str, str]:
    stages = profile.get("ordered_stages")
    stage = (
        next(
            (
                item
                for item in stages
                if isinstance(item, dict) and item.get("stage_id") == stage_id
            ),
            None,
        )
        if isinstance(stages, list)
        else None
    )
    if not isinstance(stage, dict) or stage.get("skill_id") != skill_id:
        raise WorkflowCanaryError(
            f"workflow canary stage binding is unavailable: {phase}:{stage_id}"
        )
    permissions = stage.get("permissions")
    if (
        stage.get("availability") != "registered"
        or stage.get("human_gate") != "none"
        or not isinstance(permissions, dict)
        or permissions.get("read") is not True
        or permissions.get("write") is not False
        or permissions.get("network") is not False
        or permissions.get("credentials") is not False
    ):
        raise WorkflowCanaryError(
            f"workflow canary stage is not offline read-only: {phase}:{stage_id}"
        )
    return _workflow_canary_skill_source(stage, phase, stage_id, skill_id)


def _workflow_canary_skill_source(
    stage: dict[str, Any],
    phase: str,
    stage_id: str,
    skill_id: str,
) -> dict[str, str]:
    source_path = str(stage.get("skill_source_path") or "").strip()
    source = _existing_skill_source(source_path) if source_path else None
    try:
        raw = source.read_bytes() if source is not None else None
    except OSError as exc:
        raise WorkflowCanaryError(
            f"workflow canary skill source is unreadable: {skill_id}"
        ) from exc
    if raw is None:
        raise WorkflowCanaryError(
            f"workflow canary skill source is missing: {skill_id}"
        )
    fingerprint = f"sha256:{hashlib.sha256(raw).hexdigest()}"
    if stage.get("skill_fingerprint") != fingerprint:
        raise WorkflowCanaryError(
            f"workflow canary skill fingerprint drifted: {skill_id}"
        )
    return {
        "phase": phase,
        "stage_id": stage_id,
        "skill_id": skill_id,
        "source_path": source_path,
        "skill_fingerprint": fingerprint,
    }


def prepare_workflow_canary_binding(
    *,
    runtime_dir: Any,
    project_id: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Resolve and bind one strict offline coding canary without side effects."""
    policy_path, policy_raw = _read_workflow_canary_policy(runtime_dir, project_id)
    profile = resolve_workflow_profile(
        "coding",
        runtime_dir=runtime_dir,
        project_id=project_id,
    )
    _validate_workflow_canary_profile(profile)
    stages = [
        _workflow_canary_stage_binding(profile, phase, stage_id, skill_id)
        for phase, stage_id, skill_id in _WORKFLOW_CANARY_STAGES
    ]
    confirmed_path, confirmed_raw = _read_workflow_canary_policy(
        runtime_dir,
        project_id,
    )
    if confirmed_path != policy_path or confirmed_raw != policy_raw:
        raise WorkflowCanaryError(
            "workflow canary project skill policy drifted during resolution"
        )
    binding = _workflow_canary_binding_payload(
        policy_path,
        policy_raw,
        profile,
        stages,
    )
    return profile, binding


def _workflow_canary_binding_payload(
    policy_path: Path,
    policy_raw: bytes,
    profile: dict[str, Any],
    stages: list[dict[str, str]],
) -> dict[str, Any]:
    canonical_binding = {
        "contract_version": WORKFLOW_CANARY_CONTRACT_VERSION,
        "mode": WORKFLOW_CANARY_MODE,
        "selection_source": WORKFLOW_CANARY_SELECTION_SOURCE,
        "policy_binding": {
            "resolved_path": str(policy_path),
            "sha256": f"sha256:{hashlib.sha256(policy_raw).hexdigest()}",
        },
        "profile_binding": {
            "profile_id": str(profile["profile_id"]),
            "profile_fingerprint": str(profile["profile_fingerprint"]),
        },
        "stage_bindings": stages,
    }
    canonical = json.dumps(
        canonical_binding,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return {
        **canonical_binding,
        "status": "prepared",
        "binding_fingerprint": f"sha256:{hashlib.sha256(canonical).hexdigest()}",
        "stage_results": [],
    }


def verify_workflow_canary_binding(
    prepared: dict[str, Any],
    *,
    runtime_dir: Any,
    project_id: str,
    task_spec_profile: dict[str, Any],
) -> dict[str, Any]:
    """Rebind immutable canary inputs before any report or stage side effect."""
    if not isinstance(prepared, dict):
        raise WorkflowCanaryError("workflow canary metadata is malformed")
    if set(prepared) != _WORKFLOW_CANARY_KEYS:
        raise WorkflowCanaryError("workflow canary metadata keys are malformed")
    fresh_profile, fresh = prepare_workflow_canary_binding(
        runtime_dir=runtime_dir,
        project_id=project_id,
    )
    immutable_keys = (*_WORKFLOW_CANARY_BINDING_KEYS, "binding_fingerprint")
    if any(prepared.get(key) != fresh.get(key) for key in immutable_keys):
        raise WorkflowCanaryError("workflow canary immutable binding drifted")
    if task_spec_profile != fresh_profile:
        raise WorkflowCanaryError("workflow canary TaskSpec profile drifted")
    status = prepared.get("status")
    stage_results = prepared.get("stage_results")
    if status not in {"prepared", "passed"}:
        raise WorkflowCanaryError("workflow canary status is invalid")
    if not isinstance(stage_results, list):
        raise WorkflowCanaryError("workflow canary stage results are malformed")
    if status == "prepared" and stage_results:
        raise WorkflowCanaryError("workflow canary prepared result must be empty")
    if status == "passed":
        expected_results = [
            {
                "phase": phase,
                "stage_id": stage_id,
                "skill_id": skill_id,
                "status": "passed",
                "evidence": _WORKFLOW_CANARY_STAGE_EVIDENCE[stage_id],
            }
            for phase, stage_id, skill_id in _WORKFLOW_CANARY_STAGES
        ]
        if stage_results != expected_results:
            raise WorkflowCanaryError(
                "workflow canary passed stage results are malformed"
            )
    return fresh_profile


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
