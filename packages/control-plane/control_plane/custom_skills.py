"""User-customizable methodology skills (the visual, machine-readable layer).

Built-in skills under ``tools/skills/<name>/SKILL.md`` are read-only repo assets
whose behavior traits (read-only / network / red-green) are injected in
``methodology_dispatch``. That makes a "skill" impossible to author as a
complete unit. This module adds the customization layer: a machine-readable
store at ``<runtime>/skills.json`` where a user can create/edit a *complete*
skill — identity (id, title, triggers, description) plus its behavior profile
(read-only, network, red-green evidence) and instructions — visually from
RD-Code.

Same pattern as the cluster roster: config overrides/extends the hardcoded
default; a missing or malformed file safely falls back to "no custom skills".
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .scope_resolver import SKILL_POLICY, ResolvedConfig, Scope, resolve
from .scoped_store import ScopedStore

SKILLS_FILE = "skills.json"


class CustomSkillError(Exception):
    pass


def _slug(value: object) -> str:
    text = "".join(
        ch if (ch.isalnum() or ch == "-") else "-"
        for ch in str(value or "").strip().lower()
    ).strip("-")
    while "--" in text:
        text = text.replace("--", "-")
    return text


def _normalize_trigger(raw: object) -> str:
    token = str(raw or "").strip()
    if not token:
        return ""
    if not token.startswith("@"):
        token = "@" + token
    slug = _slug(token[1:])
    return f"@{slug}" if slug else ""


def _coerce_skill(raw: Any) -> dict[str, Any] | None:
    """Validate + normalize one custom skill, or None if structurally invalid."""
    if not isinstance(raw, dict):
        return None
    skill_id = _slug(raw.get("id") or raw.get("title"))
    title = str(raw.get("title") or "").strip()
    if not skill_id or not title:
        return None
    triggers: list[str] = []
    seen: set[str] = set()
    raw_triggers = raw.get("triggers")
    if isinstance(raw_triggers, list):
        for item in raw_triggers:
            trig = _normalize_trigger(item)
            if trig and trig not in seen:
                seen.add(trig)
                triggers.append(trig)
    if not triggers:
        # Default trigger derived from the id so the skill is always addressable.
        triggers = [f"@{skill_id}"]
    skill: dict[str, Any] = {"id": skill_id, "title": title, "triggers": triggers}
    for key in ("description", "instructions"):
        value = raw.get(key)
        if isinstance(value, str) and value.strip():
            skill[key] = value.strip()
    for key in ("readOnly", "networkEnabled", "requireRedGreenEvidence"):
        if isinstance(raw.get(key), bool):
            skill[key] = raw[key]
    return skill


def _skills_store(runtime_dir: str | Path | None) -> ScopedStore:
    """A scope-aware store for the skills file (object-backed envelope)."""
    return ScopedStore(runtime_dir, SKILLS_FILE, default_factory=dict)


def _skills_path(runtime_dir: str | Path | None) -> Path:
    """Global-scope skills file path (backwards-compatible helper)."""
    return _skills_store(runtime_dir).path(Scope.GLOBAL, None)


def _coerce_skills_list(data: Any) -> list[dict[str, Any]]:
    """Normalize a raw skills envelope dict into a validated skill list.

    Mirrors the historical ``load_custom_skills`` body: a non-dict envelope or
    a missing/invalid ``skills`` list degrades to ``[]``; malformed individual
    records are skipped; duplicate ids are dropped.
    """
    if not isinstance(data, dict) or not isinstance(data.get("skills"), list):
        return []
    skills: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in data["skills"]:
        skill = _coerce_skill(raw)
        if skill is None or skill["id"] in seen:
            continue
        seen.add(skill["id"])
        skills.append(skill)
    return skills


def load_skills_at(
    runtime_dir: str | Path | None,
    scope: Scope,
    project_id: str | None = None,
) -> list[dict[str, Any]]:
    """Load one scope's skills, never raising on missing/malformed input.

    ``BUILTIN`` yields the read-only built-in skills derived from
    ``tools/skills/*/SKILL.md`` (via the methodology dispatch table);
    ``GLOBAL``/``PROJECT`` read the corresponding runtime file via
    :class:`ScopedStore`, skipping malformed individual records.
    """
    if scope == Scope.BUILTIN:
        return _builtin_skills()
    data = _skills_store(runtime_dir).load(scope, project_id)
    return _coerce_skills_list(data)


def save_at(
    runtime_dir: str | Path | None,
    scope: Scope,
    project_id: str | None,
    skills: list[Any],
) -> list[dict[str, Any]]:
    """Validate + atomically persist skills at ``scope``. Returns the saved list.

    Raises :class:`CustomSkillError` on invalid input. The write is confined to
    the target scope's file (global or project); the other scope is untouched.
    """
    if not isinstance(skills, list):
        raise CustomSkillError("skills must be a list")
    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in skills:
        skill = _coerce_skill(raw)
        if skill is None:
            raise CustomSkillError("each skill requires a valid id/title and at least a derivable trigger")
        if skill["id"] in seen:
            raise CustomSkillError(f"duplicate skill id: {skill['id']}")
        seen.add(skill["id"])
        normalized.append(skill)
    _skills_store(runtime_dir).save(
        scope, {"version": 1, "skills": normalized}, project_id
    )
    return normalized


def load_custom_skills(runtime_dir: str | Path | None) -> list[dict[str, Any]]:
    """Load global-scope custom skills (backwards-compatible alias).

    Byte-for-byte identical behavior to the historical loader: reads
    ``<runtime>/skills.json`` and falls back to ``[]`` on a missing/malformed
    file.
    """
    return load_skills_at(runtime_dir, Scope.GLOBAL, None)


def save_custom_skills(
    runtime_dir: str | Path | None, skills: list[Any]
) -> list[dict[str, Any]]:
    """Persist global-scope custom skills (backwards-compatible alias)."""
    return save_at(runtime_dir, Scope.GLOBAL, None, skills)


def _builtin_skills() -> list[dict[str, Any]]:
    """Built-in skills surfaced for the editor (read-only), with known traits."""
    try:
        from .methodology_dispatch import METHODOLOGY_DISPATCH
    except Exception:  # noqa: BLE001
        return []
    out: list[dict[str, Any]] = []
    for entry in METHODOLOGY_DISPATCH.values():
        out.append({
            "id": str(entry.get("skill_id") or ""),
            "title": str(entry.get("title") or entry.get("skill_id") or ""),
            "triggers": list(entry.get("triggers") or []),
            "requireRedGreenEvidence": bool(entry.get("require_red_green_evidence")),
            "sourcePath": str(entry.get("source_path") or ""),
            "source": "builtin",
            "editable": False,
        })
    return sorted(out, key=lambda s: s["id"])


def list_all_skills(runtime_dir: str | Path | None) -> dict[str, Any]:
    """Combined view for the visual editor: read-only built-ins + custom skills.

    Custom skills override a built-in with the same id.
    """
    builtin = _builtin_skills()
    custom = load_custom_skills(runtime_dir)
    custom_ids = {s["id"] for s in custom}
    builtin = [s for s in builtin if s["id"] not in custom_ids]
    custom_view = [{**s, "source": "custom", "editable": True} for s in custom]
    return {"version": 1, "builtin": builtin, "custom": custom_view}


class _SkillLoaders:
    """Per-scope loaders for :func:`scope_resolver.resolve` (skills category)."""

    def __init__(self, runtime_dir: str | Path | None) -> None:
        self.runtime_dir = runtime_dir

    def builtin(self) -> list[dict[str, Any]]:
        return _builtin_skills()

    def global_(self) -> list[dict[str, Any]]:
        return load_skills_at(self.runtime_dir, Scope.GLOBAL, None)

    def project(self, project_id: str | None) -> list[dict[str, Any]]:
        return load_skills_at(self.runtime_dir, Scope.PROJECT, project_id)


def resolve_skills(
    runtime_dir: str | Path | None,
    project_id: str | None = None,
) -> ResolvedConfig:
    """Resolve effective skills across scopes, with deny-overrides constraints.

    Runs the scope merge (most-specific scope wins per skill id) and then the
    deny-overrides pass under :data:`scope_resolver.SKILL_POLICY`, so the
    returned ``constraints`` carry the most-restrictive ``readOnly`` /
    ``networkEnabled`` / ``requireRedGreenEvidence`` across the effective
    skills. When ``project_id`` is None or has no file, ``effective`` equals
    today's global-only result. (Rule-driven P0 hard denies are folded in at the
    run boundary; see ``methodology_dispatch.resolve_methodology``.)
    """
    return resolve(
        "skills", _SkillLoaders(runtime_dir), project_id, policy=SKILL_POLICY
    )
