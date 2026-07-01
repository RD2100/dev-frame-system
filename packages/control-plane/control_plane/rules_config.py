"""Machine-readable governance rules (the visual, enforceable layer).

Built-in rules under ``rules/*.md`` are prose with structured per-rule blocks
(``## RULE <id>: <title>`` + ``- **Priority/Trigger/Scope/Rule/Verification/...**``).
That is human/agent-read only — it cannot be enforced programmatically or edited
visually. This module:

- parses the built-in ``rules/*.md`` into structured, read-only records, and
- adds a customization store at ``<runtime>/rules.json`` where a user can
  create/edit rules visually as machine-readable records.

Same pattern as skills/roster: config overrides/extends the built-in default; a
missing or malformed file safely falls back to "no custom rules".
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .scope_resolver import (
    ResolvedConfig,
    Scope,
    collect_p0_denies,
    resolve,
)
from .scoped_store import ScopedStore

REPO_ROOT = Path(__file__).resolve().parents[3]
RULES_FILE = "rules.json"

_PRIORITIES = ("P0", "P1", "P2", "P3", "P4")
_RULE_HEADER_RE = re.compile(r"^##\s+RULE\s+([a-z0-9][a-z0-9-]*)\s*:?\s*(.*)$", re.IGNORECASE)
_FIELD_RE = re.compile(r"^-\s+\*\*([A-Za-z ]+)\*\*\s*:\s*(.*)$")


class CustomRuleError(Exception):
    pass


def _slug(value: object) -> str:
    text = "".join(
        ch if (ch.isalnum() or ch == "-") else "-"
        for ch in str(value or "").strip().lower()
    ).strip("-")
    while "--" in text:
        text = text.replace("--", "-")
    return text


def _priority(value: object) -> str:
    token = str(value or "").strip().upper()
    for pri in _PRIORITIES:
        if token.startswith(pri):
            return pri
    return ""


# --- Built-in rules: parse rules/*.md into structured read-only records -------

_FIELD_KEYS = {
    "priority": "priority",
    "trigger": "trigger",
    "scope": "scope",
    "rule": "rule",
    "verification": "verification",
    "conflict handling": "conflictHandling",
}


def _parse_rules_markdown(text: str, domain: str) -> list[dict[str, Any]]:
    rules: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None

    def _flush() -> None:
        if current is not None and current.get("id"):
            rules.append(current)

    for line in text.splitlines():
        header = _RULE_HEADER_RE.match(line.strip())
        if header:
            _flush()
            current = {
                "id": _slug(header.group(1)),
                "title": header.group(2).strip(),
                "priority": "",
                "trigger": "",
                "scope": "",
                "rule": "",
                "verification": "",
                "domain": domain,
                "source": "builtin",
                "editable": False,
            }
            continue
        if current is None:
            continue
        field = _FIELD_RE.match(line.strip())
        if not field:
            continue
        key = field.group(1).strip().lower()
        mapped = _FIELD_KEYS.get(key)
        if mapped is None:
            continue
        value = field.group(2).strip()
        if mapped == "priority":
            current["priority"] = _priority(value)
        elif mapped == "conflictHandling":
            current["conflictHandling"] = value
        else:
            current[mapped] = value
    _flush()
    return rules


def list_builtin_rules() -> list[dict[str, Any]]:
    """Parse the read-only built-in rule set (rules/*.md) into records."""
    rules_dir = REPO_ROOT / "rules"
    if not rules_dir.is_dir():
        return []
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for path in sorted(rules_dir.glob("*.md")):
        if path.name.lower() == "readme.md":
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        for rule in _parse_rules_markdown(text, domain=path.stem):
            if rule["id"] in seen:
                continue
            seen.add(rule["id"])
            out.append(rule)
    return out


# --- Custom rules: machine-readable store under the runtime dir ---------------

def _coerce_rule(raw: Any) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    rule_id = _slug(raw.get("id"))
    priority = _priority(raw.get("priority"))
    rule_text = str(raw.get("rule") or "").strip()
    if not rule_id or not priority or not rule_text:
        return None
    record: dict[str, Any] = {"id": rule_id, "priority": priority, "rule": rule_text}
    for key in ("title", "trigger", "scope", "verification", "domain"):
        value = raw.get(key)
        if isinstance(value, str) and value.strip():
            record[key] = value.strip()
    if isinstance(raw.get("enabled"), bool):
        record["enabled"] = raw["enabled"]
    return record


def _rules_store(runtime_dir: str | Path | None) -> ScopedStore:
    """A scope-aware store for the rules file (object-backed envelope)."""
    return ScopedStore(runtime_dir, RULES_FILE, default_factory=dict)


def _rules_path(runtime_dir: str | Path | None) -> Path:
    """Global-scope rules file path (backwards-compatible helper)."""
    return _rules_store(runtime_dir).path(Scope.GLOBAL, None)


def _coerce_rules_list(data: Any) -> list[dict[str, Any]]:
    """Normalize a raw rules envelope dict into a validated rule list.

    Mirrors the historical ``load_custom_rules`` body: a non-dict envelope or a
    missing/invalid ``rules`` list degrades to ``[]``; malformed individual
    records are skipped; duplicate ids are dropped.
    """
    if not isinstance(data, dict) or not isinstance(data.get("rules"), list):
        return []
    rules: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in data["rules"]:
        rule = _coerce_rule(raw)
        if rule is None or rule["id"] in seen:
            continue
        seen.add(rule["id"])
        rules.append(rule)
    return rules


def load_rules_at(
    runtime_dir: str | Path | None,
    scope: Scope,
    project_id: str | None = None,
) -> list[dict[str, Any]]:
    """Load one scope's rules, never raising on missing/malformed input.

    ``BUILTIN`` yields the read-only rules parsed from ``rules/*.md``;
    ``GLOBAL``/``PROJECT`` read the corresponding runtime file via
    :class:`ScopedStore`, skipping malformed individual records.
    """
    if scope == Scope.BUILTIN:
        return list_builtin_rules()
    data = _rules_store(runtime_dir).load(scope, project_id)
    return _coerce_rules_list(data)


def save_at(
    runtime_dir: str | Path | None,
    scope: Scope,
    project_id: str | None,
    rules: list[Any],
) -> list[dict[str, Any]]:
    """Validate + atomically persist rules at ``scope``. Returns the saved list.

    Raises :class:`CustomRuleError` on invalid input. The write is confined to
    the target scope's file (global or project); the other scope is untouched.
    """
    if not isinstance(rules, list):
        raise CustomRuleError("rules must be a list")
    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in rules:
        rule = _coerce_rule(raw)
        if rule is None:
            raise CustomRuleError("each rule requires a valid id, priority (P0-P4), and rule text")
        if rule["id"] in seen:
            raise CustomRuleError(f"duplicate rule id: {rule['id']}")
        seen.add(rule["id"])
        normalized.append(rule)
    _rules_store(runtime_dir).save(
        scope, {"version": 1, "rules": normalized}, project_id
    )
    return normalized


def load_custom_rules(runtime_dir: str | Path | None) -> list[dict[str, Any]]:
    """Load global-scope custom rules (backwards-compatible alias).

    Byte-for-byte identical behavior to the historical loader: reads
    ``<runtime>/rules.json`` and falls back to ``[]`` on a missing/malformed
    file.
    """
    return load_rules_at(runtime_dir, Scope.GLOBAL, None)


def save_custom_rules(
    runtime_dir: str | Path | None, rules: list[Any]
) -> list[dict[str, Any]]:
    """Persist global-scope custom rules (backwards-compatible alias)."""
    return save_at(runtime_dir, Scope.GLOBAL, None, rules)


def list_all_rules(runtime_dir: str | Path | None) -> dict[str, Any]:
    """Combined view for the visual editor: read-only built-ins + custom rules.

    Custom rules override a built-in with the same id.
    """
    builtin = list_builtin_rules()
    custom = load_custom_rules(runtime_dir)
    custom_ids = {r["id"] for r in custom}
    builtin = [r for r in builtin if r["id"] not in custom_ids]
    custom_view = [{**r, "source": "custom", "editable": True} for r in custom]
    return {"version": 1, "builtin": builtin, "custom": custom_view}


class _RuleLoaders:
    """Per-scope loaders for :func:`scope_resolver.resolve` (rules category)."""

    def __init__(self, runtime_dir: str | Path | None) -> None:
        self.runtime_dir = runtime_dir

    def builtin(self) -> list[dict[str, Any]]:
        return list_builtin_rules()

    def global_(self) -> list[dict[str, Any]]:
        return load_rules_at(self.runtime_dir, Scope.GLOBAL, None)

    def project(self, project_id: str | None) -> list[dict[str, Any]]:
        return load_rules_at(self.runtime_dir, Scope.PROJECT, project_id)


def rule_layers(
    runtime_dir: str | Path | None,
    project_id: str | None = None,
) -> dict[Scope, list[dict[str, Any]]]:
    """Build the per-scope rule layers (built-in/global/project).

    This is the shape :func:`scope_resolver.collect_p0_denies` and
    :func:`scope_resolver.merge_by_id` consume. The project layer is empty when
    ``project_id`` is falsy.
    """
    loaders = _RuleLoaders(runtime_dir)
    return {
        Scope.BUILTIN: loaders.builtin(),
        Scope.GLOBAL: loaders.global_(),
        Scope.PROJECT: loaders.project(project_id) if project_id else [],
    }


def resolve_rules(
    runtime_dir: str | Path | None,
    project_id: str | None = None,
) -> ResolvedConfig:
    """Resolve effective rules across built-in/global/project scopes.

    Numeric priority (P0–P4) lives only on rules. Resolution is a pure scope
    merge (most-specific scope wins per rule id); rules carry no capability
    flags of their own, so no deny-overrides pass runs here. P0 rules are
    surfaced as hard denies for capability resolution elsewhere via
    :func:`collect_p0_rule_denies`.
    """
    return resolve("rules", _RuleLoaders(runtime_dir), project_id, policy=None)


def collect_p0_rule_denies(
    runtime_dir: str | Path | None,
    project_id: str | None = None,
) -> list[dict[str, Any]]:
    """Collect P0 rule records across every scope as unconditional hard denies.

    A P0 rule at *any* scope is a hard deny (a lower scope can never weaken a P0
    governance rule), so this gathers from all layers, not just the
    most-specific defining scope.
    """
    return collect_p0_denies(rule_layers(runtime_dir, project_id))
