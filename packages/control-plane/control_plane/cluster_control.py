"""Cluster control surface for the RD-Code editor (&-mention targets).

The editor lets a user `&`-mention a *cluster target* in the chat composer to
hand a goal to the orchestration coordinator (团队主控) or to a specific worker
role. This module owns the read-only piece:

- ``list_cluster_targets`` — enumerate the mentionable targets for a project
  (the coordinator, any agents already recorded by the team runtime, plus a
  documented default worker roster so ``&`` is useful before any run exists).
- ``is_valid_cluster_target`` — validate a chosen target id server-side.

Starting an actual run is owned by ``cluster_run.start_cluster_run``. There is no
dashboard-approval / task-proposal staging path for the editor cluster flow: a
human typing ``&target <goal>`` and confirming inline in the conversation is the
authorization. The dashboard is monitoring only.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .scope_resolver import ResolvedConfig, Scope, resolve
from .scoped_store import ScopedStore

__all__ = [
    "COORDINATOR_ID",
    "PAPER_TARGET_ID",
    "ClusterControlError",
    "ROSTER_FILE",
    "load_cluster_roster",
    "save_cluster_roster",
    "load_cluster_roster_at",
    "save_at",
    "resolve_roster",
    "list_cluster_targets",
    "is_valid_cluster_target",
]


COORDINATOR_ID = "coordinator"
PAPER_TARGET_ID = "rdpaper"

# Documented default worker roster, mirroring the /go orchestration phases
# (coordinator plans, executor edits, reviewer checks). These let the editor
# offer useful &-mention targets before any team run has been recorded.
_DEFAULT_AGENT_ROLES: tuple[tuple[str, str], ...] = (
    ("executor", "Executor (执行)"),
    ("reviewer", "Reviewer (复审)"),
)

_COORDINATOR_LABEL = "Coordinator (主控)"
_PAPER_TARGET_LABEL = "Paper Review (论文审查)"


class ClusterControlError(Exception):
    pass


ROSTER_FILE = "cluster-roster.json"


def _coerce_roster_agent(raw: Any) -> dict[str, Any] | None:
    """Validate + normalize one configured roster agent, or None if invalid."""
    if not isinstance(raw, dict):
        return None
    agent_id = _slug(raw.get("id"))
    role = str(raw.get("role") or "").strip()
    label = str(raw.get("label") or "").strip()
    if not agent_id or not role or not label:
        return None
    agent: dict[str, Any] = {"id": agent_id, "role": role, "label": label}
    for key in ("model", "provider", "methodology"):
        value = raw.get(key)
        if isinstance(value, str) and value.strip():
            agent[key] = value.strip()
    if isinstance(raw.get("enabled"), bool):
        agent["enabled"] = raw["enabled"]
    return agent


def _roster_store(runtime_dir: str | Path | None) -> ScopedStore:
    """A scope-aware store for the roster file (object-backed envelope)."""
    return ScopedStore(runtime_dir, ROSTER_FILE, default_factory=dict)


def _roster_path(runtime_dir: str | Path | None) -> Path:
    """Global-scope roster file path (backwards-compatible helper)."""
    return _roster_store(runtime_dir).path(Scope.GLOBAL, None)


def _coerce_roster_agents(data: Any) -> list[dict[str, Any]]:
    """Normalize a raw roster envelope dict into a validated agent list.

    Mirrors the historical ``load_cluster_roster`` body: a non-dict envelope or
    a missing/invalid ``agents`` list degrades to ``[]``; the coordinator id is
    reserved; duplicate ids are dropped.
    """
    if not isinstance(data, dict):
        return []
    agents_raw = data.get("agents")
    if not isinstance(agents_raw, list):
        return []
    roster: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in agents_raw:
        agent = _coerce_roster_agent(raw)
        if agent is None or agent["id"] in seen or agent["id"] == COORDINATOR_ID:
            continue
        seen.add(agent["id"])
        roster.append(agent)
    return roster


def _builtin_roster() -> list[dict[str, Any]]:
    """The built-in default worker roster as scope-merge records (read-only)."""
    return [
        {"id": _slug(role), "role": role, "label": label}
        for role, label in _DEFAULT_AGENT_ROLES
    ]


def load_cluster_roster_at(
    runtime_dir: str | Path | None,
    scope: Scope,
    project_id: str | None = None,
) -> list[dict[str, Any]]:
    """Load one scope's roster, never raising on missing/malformed input.

    ``BUILTIN`` yields the hardcoded default roster; ``GLOBAL``/``PROJECT`` read
    the corresponding runtime file via :class:`ScopedStore` and apply the same
    coercion/validation as the legacy loader.
    """
    if scope == Scope.BUILTIN:
        return _builtin_roster()
    data = _roster_store(runtime_dir).load(scope, project_id)
    return _coerce_roster_agents(data)


def save_at(
    runtime_dir: str | Path | None,
    scope: Scope,
    project_id: str | None,
    agents: list[Any],
) -> list[dict[str, Any]]:
    """Validate + atomically persist a roster at ``scope``. Returns the saved list.

    Raises :class:`ClusterControlError` on invalid input. The coordinator id is
    reserved and never stored as a roster agent. The write is confined to the
    target scope's file (global or project); the other scope is untouched.
    """
    if not isinstance(agents, list):
        raise ClusterControlError("agents must be a list")
    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in agents:
        agent = _coerce_roster_agent(raw)
        if agent is None:
            raise ClusterControlError("each agent requires a valid id, role, and label")
        if agent["id"] == COORDINATOR_ID:
            raise ClusterControlError("'coordinator' is reserved and cannot be a roster agent")
        if agent["id"] in seen:
            raise ClusterControlError(f"duplicate agent id: {agent['id']}")
        seen.add(agent["id"])
        normalized.append(agent)
    _roster_store(runtime_dir).save(
        scope, {"version": 1, "agents": normalized}, project_id
    )
    return normalized


def load_cluster_roster(runtime_dir: str | Path | None) -> list[dict[str, Any]]:
    """Load the global-scope customized roster (backwards-compatible alias).

    Byte-for-byte identical behavior to the historical loader: it reads the
    global ``<runtime>/cluster-roster.json`` and falls back to ``[]`` on a
    missing/malformed file.
    """
    return load_cluster_roster_at(runtime_dir, Scope.GLOBAL, None)


def save_cluster_roster(
    runtime_dir: str | Path | None, agents: list[Any]
) -> list[dict[str, Any]]:
    """Persist the global-scope roster (backwards-compatible alias)."""
    return save_at(runtime_dir, Scope.GLOBAL, None, agents)


class _RosterLoaders:
    """Per-scope loaders for :func:`scope_resolver.resolve` (team category)."""

    def __init__(self, runtime_dir: str | Path | None) -> None:
        self.runtime_dir = runtime_dir

    def builtin(self) -> list[dict[str, Any]]:
        return _builtin_roster()

    def global_(self) -> list[dict[str, Any]]:
        return load_cluster_roster_at(self.runtime_dir, Scope.GLOBAL, None)

    def project(self, project_id: str | None) -> list[dict[str, Any]]:
        return load_cluster_roster_at(self.runtime_dir, Scope.PROJECT, project_id)


def resolve_roster(
    runtime_dir: str | Path | None,
    project_id: str | None = None,
) -> ResolvedConfig:
    """Resolve the effective roster across built-in/global/project scopes.

    The team category has no capability flags or numeric priority, so no
    deny-overrides pass runs (``policy=None``); resolution is a pure scope merge
    where the most-specific scope wins per agent id. When ``project_id`` is None
    or has no file, ``effective`` equals today's global-only result.
    """
    return resolve("team", _RosterLoaders(runtime_dir), project_id, policy=None)


def _slug(value: object) -> str:
    text = "".join(
        ch if (ch.isalnum() or ch == "-") else "-"
        for ch in str(value or "").strip().lower()
    ).strip("-")
    while "--" in text:
        text = text.replace("--", "-")
    return text


def _recorded_agents(runtime_dir: str | Path | None) -> list[dict[str, Any]]:
    if not runtime_dir:
        return []
    try:
        from .team_runtime import build_team_runtime_view

        view = build_team_runtime_view(runtime_dir)
    except Exception:
        return []
    registry = view.get("agent_registry") if isinstance(view, dict) else None
    return list(registry) if isinstance(registry, list) else []


def list_cluster_targets(
    runtime_dir: str | Path | None,
    project_id: str = "",
) -> list[dict[str, Any]]:
    """Enumerate mentionable cluster targets for a project.

    Always includes the coordinator (主控) and the governed local paper product.
    Adds any agents recorded by the team runtime (source ``recorded``) and a
    default worker roster (source ``default``), deduped by stable mention id.
    """
    targets: list[dict[str, Any]] = []
    seen: set[str] = set()

    def _add(target: dict[str, Any]) -> None:
        tid = target["id"]
        if tid and tid not in seen:
            seen.add(tid)
            targets.append(target)

    _add({
        "id": COORDINATOR_ID,
        "kind": "coordinator",
        "role": "coordinator",
        "label": _COORDINATOR_LABEL,
        "source": "default",
    })
    _add({
        "id": PAPER_TARGET_ID,
        "kind": "product",
        "role": "paper_reviewer",
        "label": _PAPER_TARGET_LABEL,
        "source": "default",
    })

    for agent in _recorded_agents(runtime_dir):
        if not isinstance(agent, dict):
            continue
        agent_id = _slug(agent.get("agentId") or agent.get("agent_id"))
        if not agent_id or agent_id == COORDINATOR_ID:
            continue
        role = str(agent.get("role") or "agent").strip() or "agent"
        status = str(agent.get("status") or "").strip()
        label = agent.get("agentId") or agent_id
        if role and role.lower() not in str(label).lower():
            label = f"{label} ({role})"
        _add({
            "id": agent_id,
            "kind": "agent",
            "role": role,
            "label": str(label),
            "source": "recorded",
            "status": status,
        })

    configured = load_cluster_roster(runtime_dir)
    if configured:
        for agent in configured:
            if isinstance(agent.get("enabled"), bool) and not agent["enabled"]:
                continue
            _add({
                "id": agent["id"],
                "kind": "agent",
                "role": agent["role"],
                "label": agent["label"],
                "source": "configured",
                **({"model": agent["model"]} if agent.get("model") else {}),
                **({"provider": agent["provider"]} if agent.get("provider") else {}),
                **({"methodology": agent["methodology"]} if agent.get("methodology") else {}),
            })
    else:
        for role, label in _DEFAULT_AGENT_ROLES:
            _add({
                "id": _slug(role),
                "kind": "agent",
                "role": role,
                "label": label,
                "source": "default",
            })

    return targets


def is_valid_cluster_target(
    runtime_dir: str | Path | None,
    target: str,
    project_id: str = "",
) -> bool:
    tid = _slug(target)
    if not tid:
        return False
    return any(t["id"] == tid for t in list_cluster_targets(runtime_dir, project_id))
