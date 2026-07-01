"""Read-only methodology skill registry for dev-frame-system."""
from __future__ import annotations

from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]


def _safe_id(value: str) -> str:
    normalized = "".join(
        char.lower() if "a" <= char.lower() <= "z" or "0" <= char <= "9" else "-"
        for char in value
    )
    normalized = "-".join(part for part in normalized.split("-") if part)
    return normalized or "unknown"


def _parse_frontmatter(text: str) -> dict[str, Any] | None:
    if not text.startswith("---"):
        return None
    try:
        _, fm, _ = text.split("---", 2)
    except ValueError:
        return None
    import yaml
    data = yaml.safe_load(fm)
    return data if isinstance(data, dict) else None


def _extract_triggers(description: str) -> list[str]:
    triggers: list[str] = []
    seen: set[str] = set()
    for token in description.replace(",", " ").replace(".", " ").split():
        token = token.strip().strip("\"'")
        if token.startswith("@") and token not in seen:
            seen.add(token)
            triggers.append(token)
    return triggers


def match_methodology_requirement(requirement: str) -> dict[str, Any] | None:
    if not requirement:
        return None
    for skill in list_methodology_skills():
        for trigger in skill.get("triggers", []):
            if requirement.startswith(trigger):
                return skill
    return None


def match_methodology(requirement: str) -> dict[str, Any] | None:
    skills = list_methodology_skills()
    trigger_map: dict[str, dict[str, Any]] = {}
    for skill in skills:
        for trigger in skill.get("triggers", []):
            trigger_map[trigger] = skill
    first_token = requirement.lstrip().split(None, 1)[0]
    return trigger_map.get(first_token)


def list_methodology_skills() -> list[dict[str, Any]]:
    skills: list[dict[str, Any]] = []
    seen: set[str] = set()

    tools_skills = REPO_ROOT / "tools" / "skills"
    if tools_skills.is_dir():
        for skill_dir in sorted(tools_skills.iterdir()):
            if not skill_dir.is_dir():
                continue
            skill_md = skill_dir / "SKILL.md"
            if not skill_md.exists():
                continue
            text = skill_md.read_text(encoding="utf-8")
            fm = _parse_frontmatter(text) or {}
            skill_id = _safe_id(str(fm.get("name") or skill_dir.name))
            if skill_id in seen:
                continue
            seen.add(skill_id)
            skills.append({
                "skill_id": skill_id,
                "title": str(fm.get("name") or skill_dir.name),
                "source_path": str(skill_md.relative_to(REPO_ROOT)),
                "source_kind": "local_repository_asset",
                "triggers": _extract_triggers(str(fm.get("description") or "")),
                "status": "registered",
            })

    shipped = REPO_ROOT / "templates" / "runtime-bootstrap" / "SKILL.md"
    if shipped.exists():
        text = shipped.read_text(encoding="utf-8")
        fm = _parse_frontmatter(text) or {}
        skill_id = _safe_id(str(fm.get("name") or "agent-acceptance"))
        if skill_id not in seen:
            seen.add(skill_id)
            skills.append({
                "skill_id": skill_id,
                "title": str(fm.get("name") or "agent-acceptance"),
                "source_path": str(shipped.relative_to(REPO_ROOT)),
                "source_kind": "local_repository_asset",
                "triggers": _extract_triggers(str(fm.get("description") or "")),
                "status": "registered",
            })

    return sorted(skills, key=lambda s: s["skill_id"])
