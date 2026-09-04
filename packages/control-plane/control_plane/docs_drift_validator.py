"""Validate the repository's single-plan documentation model.

Human-facing planning content has one authority: ``PLAN.md`` at the repository
root. Markdown used as a rule, contract, prompt, template, skill, or fixture is
code-like input and is outside this validator's authority check.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import re


@dataclass
class ValidationResult:
    valid: bool
    errors: list[str] = field(default_factory=list)

    def __bool__(self) -> bool:
        return self.valid


MAX_PLAN_BYTES = 1_000_000
LEGACY_ROOT_DOCS = (
    "README.md",
    "README.zh-CN.md",
    "AGENT_HANDOFF.md",
)
REQUIRED_PLAN_HEADINGS = (
    "Next Action",
    "Authority",
    "Product Decision",
    "Verified Baseline",
    "Current Risk Register",
    "Delivery Roadmap",
    "Execution Protocol",
    "Human Gates",
    "Documentation Policy",
    "Decision Log",
)


def _read_utf8(path: Path) -> tuple[bool, str, str | None]:
    if not path.is_file():
        return False, "", None
    try:
        return True, path.read_text(encoding="utf-8-sig"), None
    except (OSError, UnicodeError) as exc:
        return True, "", f"{type(exc).__name__}: {exc}"


def _heading_count(text: str, heading: str) -> int:
    pattern = rf"^##(?:\s+\d+\.)?\s+{re.escape(heading)}\s*$"
    return len(re.findall(pattern, text, flags=re.MULTILINE))


def build_docs_drift_payload(repo_root: str | Path) -> dict:
    """Read the real repository paths needed by the single-plan gate."""
    root = Path(repo_root)
    plan_path = root / "PLAN.md"
    agents_path = root / "AGENTS.md"
    plan_exists, plan_text, plan_read_error = _read_utf8(plan_path)
    agents_exists, agents_text, agents_read_error = _read_utf8(agents_path)
    docs_root = root / "docs"
    docs_files = (
        sorted(
            path.relative_to(root).as_posix()
            for path in docs_root.rglob("*")
            if path.is_file()
        )
        if docs_root.exists()
        else []
    )

    return {
        "plan_exists": plan_exists,
        "plan_text": plan_text,
        "plan_size": plan_path.stat().st_size if plan_exists else 0,
        "plan_read_error": plan_read_error,
        "agents_exists": agents_exists,
        "agents_text": agents_text,
        "agents_read_error": agents_read_error,
        "docs_files": docs_files,
        "legacy_root_files": [
            name for name in LEGACY_ROOT_DOCS if (root / name).exists()
        ],
    }


def _check_single_plan(payload: dict) -> list[str]:
    errors: list[str] = []
    plan_exists = bool(payload.get("plan_exists"))
    plan_text = str(payload.get("plan_text") or "")
    plan_size = int(payload.get("plan_size") or 0)
    plan_read_error = payload.get("plan_read_error")
    agents_exists = bool(payload.get("agents_exists"))
    agents_text = str(payload.get("agents_text") or "")
    agents_read_error = payload.get("agents_read_error")
    docs_files = sorted(str(item) for item in (payload.get("docs_files") or []))
    legacy_root_files = sorted(
        str(item) for item in (payload.get("legacy_root_files") or [])
    )

    if not plan_exists:
        errors.append("docs_drift: root PLAN.md is missing")
    if plan_read_error:
        errors.append(f"docs_drift: PLAN.md is not readable UTF-8: {plan_read_error}")
    if plan_exists and not plan_text.strip() and not plan_read_error:
        errors.append("docs_drift: PLAN.md is empty")
    if plan_size > MAX_PLAN_BYTES:
        errors.append(
            f"docs_drift: PLAN.md is {plan_size} bytes; limit is {MAX_PLAN_BYTES}"
        )

    verdict_count = len(re.findall(r"^Current verdict:", plan_text, re.MULTILINE))
    if plan_exists and verdict_count != 1:
        errors.append(
            "docs_drift: PLAN.md must contain exactly one 'Current verdict:' line "
            f"(found {verdict_count})"
        )
    for heading in REQUIRED_PLAN_HEADINGS:
        count = _heading_count(plan_text, heading)
        if plan_exists and count != 1:
            errors.append(
                f"docs_drift: PLAN.md must contain exactly one '## {heading}' "
                f"heading (found {count})"
            )

    if not agents_exists:
        errors.append("docs_drift: root AGENTS.md entrypoint is missing")
    if agents_read_error:
        errors.append(f"docs_drift: AGENTS.md is not readable UTF-8: {agents_read_error}")
    if agents_exists and "PLAN.md" not in agents_text:
        errors.append("docs_drift: AGENTS.md does not point to PLAN.md")
    if agents_exists and "only human development authority" not in agents_text:
        errors.append(
            "docs_drift: AGENTS.md does not declare PLAN.md as the only human "
            "development authority"
        )

    for path in docs_files:
        errors.append(f"docs_drift: retired docs/ tree still contains {path!r}")
    for path in legacy_root_files:
        errors.append(f"docs_drift: retired root document still exists: {path!r}")
    return errors


def validate_docs_drift(payload: dict) -> ValidationResult:
    """Validate that the single-plan authority is complete and unique."""
    errors = _check_single_plan(payload)
    return ValidationResult(valid=not errors, errors=errors)


def derive_docs_drift(payload: dict) -> dict:
    """Return a read-only projection of the same checks used by validation."""
    plan_text = str(payload.get("plan_text") or "")
    errors = _check_single_plan(payload)
    heading_counts = {
        heading: _heading_count(plan_text, heading)
        for heading in REQUIRED_PLAN_HEADINGS
    }
    return {
        "valid": not errors,
        "errors": errors,
        "plan_exists": bool(payload.get("plan_exists")),
        "plan_size": int(payload.get("plan_size") or 0),
        "current_verdict_count": len(
            re.findall(r"^Current verdict:", plan_text, re.MULTILINE)
        ),
        "heading_counts": heading_counts,
        "docs_file_count": len(payload.get("docs_files") or []),
        "legacy_root_file_count": len(payload.get("legacy_root_files") or []),
    }
