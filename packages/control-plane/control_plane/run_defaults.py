"""Run defaults: project-level visual config for default run parameters.

A "run default" answers the question *what should a run use when the user does
not say otherwise* — how many workers, which model, and which methodology
trigger. Unlike the list-backed categories (team / skills / rules), this is a
single object whose fields each inherit independently across scopes:

    built-in code constants  <  global (<runtime>/run-defaults.json)  <  project

An absent field at a more-specific scope inherits the next-less-specific scope's
value (per-field merge, not whole-object replace). The built-in layer supplies
the final fallback so every field always resolves to *something* or stays
``None`` (meaning "no opinion; let the caller decide").

Storage and malformed-safety reuse :class:`scoped_store.ScopedStore` exactly as
the other categories do; a bad edit at any scope silently degrades to the
next-less-specific value.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .scope_resolver import Scope
from .scoped_store import ScopedStore

RUN_DEFAULTS_FILE = "run-defaults.json"


class RunDefaultsError(Exception):
    pass


# Built-in fallbacks. ``None`` means "no built-in opinion" so a caller can apply
# its own default; ``agents`` defaults to a single worker.
_BUILTIN_AGENTS: int | None = 1
_BUILTIN_MODEL: str | None = None
_BUILTIN_METHODOLOGY: str | None = None


@dataclass(frozen=True)
class RunDefaults:
    """Resolved run defaults. Any field may be ``None`` (inherit / no opinion)."""

    agents: int | None = None
    model: str | None = None
    methodology: str | None = None


def _coerce_field(name: str, value: Any) -> Any:
    """Validate one field, returning the cleaned value or raising on bad input.

    ``None``/absent passes through (means "inherit"). ``agents`` must be an
    integer ``>= 1``; ``model``/``methodology`` must be non-empty strings.
    """
    if value is None:
        return None
    if name == "agents":
        # Reject bools (a bool is an int subclass) and anything < 1.
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            raise RunDefaultsError("agents must be an integer >= 1")
        return value
    # model / methodology
    if not isinstance(value, str) or not value.strip():
        raise RunDefaultsError(f"{name} must be a non-empty string when set")
    return value.strip()


def _coerce_run_defaults(raw: Any) -> dict[str, Any]:
    """Validate a raw run-defaults object into a clean field dict (raises on bad)."""
    if not isinstance(raw, dict):
        raise RunDefaultsError("run defaults must be a JSON object")
    out: dict[str, Any] = {}
    for name in ("agents", "model", "methodology"):
        cleaned = _coerce_field(name, raw.get(name))
        if cleaned is not None:
            out[name] = cleaned
    return out


def _store(runtime_dir: str | Path | None) -> ScopedStore:
    return ScopedStore(runtime_dir, RUN_DEFAULTS_FILE, default_factory=dict)


def _load_layer_safe(
    runtime_dir: str | Path | None, scope: Scope, project_id: str | None
) -> dict[str, Any]:
    """Load + validate one scope, degrading to ``{}`` on missing/malformed input."""
    raw = _store(runtime_dir).load(scope, project_id)
    try:
        return _coerce_run_defaults(raw)
    except RunDefaultsError:
        return {}


def load_defaults_at(
    runtime_dir: str | Path | None,
    scope: Scope,
    project_id: str | None = None,
) -> dict[str, Any]:
    """Load one scope's raw (validated) field dict.

    ``BUILTIN`` returns the built-in field dict; ``GLOBAL``/``PROJECT`` read the
    runtime file, degrading to ``{}`` on missing/malformed input.
    """
    if scope == Scope.BUILTIN:
        return _builtin_fields()
    return _load_layer_safe(runtime_dir, scope, project_id)


def save_at(
    runtime_dir: str | Path | None,
    scope: Scope,
    project_id: str | None,
    defaults: Any,
) -> dict[str, Any]:
    """Validate + atomically persist run defaults at ``scope``. Returns saved dict.

    Raises :class:`RunDefaultsError` on invalid input. The write is confined to
    the target scope's file; the other scope is untouched.
    """
    cleaned = _coerce_run_defaults(defaults)
    _store(runtime_dir).save(scope, {"version": 1, **cleaned}, project_id)
    return cleaned


def _builtin_fields() -> dict[str, Any]:
    out: dict[str, Any] = {}
    if _BUILTIN_AGENTS is not None:
        out["agents"] = _BUILTIN_AGENTS
    if _BUILTIN_MODEL is not None:
        out["model"] = _BUILTIN_MODEL
    if _BUILTIN_METHODOLOGY is not None:
        out["methodology"] = _BUILTIN_METHODOLOGY
    return out


def resolve_defaults(
    runtime_dir: str | Path | None,
    project_id: str | None = None,
) -> RunDefaults:
    """Resolve effective run defaults via per-field scope inheritance.

    Each field is taken from the most-specific scope that sets it
    (project > global > built-in); an absent field inherits the next-less-specific
    scope. When ``project_id`` is falsy the project layer is skipped.
    """
    builtin = _builtin_fields()
    global_ = _load_layer_safe(runtime_dir, Scope.GLOBAL, None)
    project = (
        _load_layer_safe(runtime_dir, Scope.PROJECT, project_id) if project_id else {}
    )

    merged: dict[str, Any] = {}
    for layer in (builtin, global_, project):  # least- to most-specific
        for key, value in layer.items():
            if value is not None:
                merged[key] = value
    return RunDefaults(
        agents=merged.get("agents"),
        model=merged.get("model"),
        methodology=merged.get("methodology"),
    )


def resolve_view(
    runtime_dir: str | Path | None,
    project_id: str | None = None,
) -> dict[str, Any]:
    """Build the ``{builtin, global, project, effective}`` view for the editor/API."""
    return {
        "version": 1,
        "projectId": project_id or "",
        "builtin": _builtin_fields(),
        "global": _load_layer_safe(runtime_dir, Scope.GLOBAL, None),
        "project": (
            _load_layer_safe(runtime_dir, Scope.PROJECT, project_id)
            if project_id
            else {}
        ),
        "effective": asdict(resolve_defaults(runtime_dir, project_id)),
    }
