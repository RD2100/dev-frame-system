"""Read-only methodology skill registry for dev-frame-system."""
from __future__ import annotations

from pathlib import Path
from typing import Any

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
SOURCE_REPO_ROOT = Path(__file__).resolve().parents[3]
_SOURCE_CHECKOUT = (
    PACKAGE_ROOT.name == "control-plane"
    and PACKAGE_ROOT.parent.name == "packages"
    and (PACKAGE_ROOT / "setup.py").is_file()
)
REPO_ROOT = SOURCE_REPO_ROOT if _SOURCE_CHECKOUT else PACKAGE_ROOT


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


def _append_skill(
    skills: list[dict[str, Any]],
    seen: set[str],
    skill_md: Path,
    *,
    source_root: Path,
    fallback_name: str,
) -> None:
    text = skill_md.read_text(encoding="utf-8")
    fm = _parse_frontmatter(text) or {}
    skill_id = _safe_id(str(fm.get("name") or fallback_name))
    if skill_id in seen:
        return
    seen.add(skill_id)
    skills.append({
        "skill_id": skill_id,
        "title": str(fm.get("name") or fallback_name),
        "source_path": str(skill_md.relative_to(source_root)),
        "source_kind": "local_repository_asset",
        "triggers": _extract_triggers(str(fm.get("description") or "")),
        "status": "registered",
    })


def list_methodology_skills() -> list[dict[str, Any]]:
    skills: list[dict[str, Any]] = []
    seen: set[str] = set()

    packaged_skills = PACKAGE_ROOT / "templates" / "methodology-skills"
    tools_skills = REPO_ROOT / "tools" / "skills"
    skill_roots = (
        ((tools_skills, REPO_ROOT), (packaged_skills, PACKAGE_ROOT))
        if _SOURCE_CHECKOUT
        else ((packaged_skills, PACKAGE_ROOT), (tools_skills, REPO_ROOT))
    )
    for skills_root, source_root in skill_roots:
        if not skills_root.is_dir():
            continue
        for skill_dir in sorted(skills_root.iterdir()):
            if not skill_dir.is_dir():
                continue
            skill_md = skill_dir / "SKILL.md"
            if not skill_md.exists():
                continue
            _append_skill(
                skills,
                seen,
                skill_md,
                source_root=source_root,
                fallback_name=skill_dir.name,
            )

    shipped = PACKAGE_ROOT / "templates" / "runtime-bootstrap" / "SKILL.md"
    if shipped.exists():
        _append_skill(
            skills,
            seen,
            shipped,
            source_root=PACKAGE_ROOT,
            fallback_name="agent-acceptance",
        )

    return sorted(skills, key=lambda s: s["skill_id"])
