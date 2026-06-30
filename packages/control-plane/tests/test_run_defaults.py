"""Unit tests for run_defaults (task 5.2)."""
from __future__ import annotations

import json

import pytest

from control_plane.run_defaults import (
    RunDefaultsError,
    resolve_defaults,
    resolve_view,
    save_at,
)
from control_plane.scope_resolver import Scope
from control_plane.scoped_store import ScopedStore


def test_builtin_default_when_nothing_configured(tmp_path):
    runtime = tmp_path / "runtime"
    rd = resolve_defaults(runtime)
    assert rd.agents == 1  # built-in fallback
    assert rd.model is None
    assert rd.methodology is None


def test_global_overrides_builtin(tmp_path):
    runtime = tmp_path / "runtime"
    save_at(runtime, Scope.GLOBAL, None, {"agents": 3, "model": "gpt-x"})
    rd = resolve_defaults(runtime)
    assert rd.agents == 3
    assert rd.model == "gpt-x"


def test_project_overrides_global_per_field(tmp_path):
    runtime = tmp_path / "runtime"
    save_at(runtime, Scope.GLOBAL, None, {"agents": 3, "model": "gpt-x"})
    save_at(runtime, Scope.PROJECT, "demo", {"agents": 5})
    rd = resolve_defaults(runtime, "demo")
    assert rd.agents == 5         # overridden by project
    assert rd.model == "gpt-x"    # inherited from global


def test_absent_project_inherits_global(tmp_path):
    runtime = tmp_path / "runtime"
    save_at(runtime, Scope.GLOBAL, None, {"methodology": "@go edit"})
    rd = resolve_defaults(runtime, "demo")  # no project file
    assert rd.methodology == "@go edit"


def test_validation_rejects_agents_below_one(tmp_path):
    runtime = tmp_path / "runtime"
    with pytest.raises(RunDefaultsError):
        save_at(runtime, Scope.GLOBAL, None, {"agents": 0})


def test_validation_rejects_bool_agents(tmp_path):
    runtime = tmp_path / "runtime"
    with pytest.raises(RunDefaultsError):
        save_at(runtime, Scope.GLOBAL, None, {"agents": True})


def test_validation_rejects_empty_strings(tmp_path):
    runtime = tmp_path / "runtime"
    with pytest.raises(RunDefaultsError):
        save_at(runtime, Scope.GLOBAL, None, {"model": "   "})


def test_malformed_global_degrades_to_builtin(tmp_path):
    runtime = tmp_path / "runtime"
    path = ScopedStore(runtime, "run-defaults.json", default_factory=dict).path(Scope.GLOBAL, None)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{ broken", encoding="utf-8")
    rd = resolve_defaults(runtime)
    assert rd.agents == 1  # falls back to built-in


def test_invalid_field_in_file_degrades_safely(tmp_path):
    runtime = tmp_path / "runtime"
    path = ScopedStore(runtime, "run-defaults.json", default_factory=dict).path(Scope.GLOBAL, None)
    path.parent.mkdir(parents=True, exist_ok=True)
    # agents is invalid (0); the whole layer degrades to {} rather than raising.
    path.write_text(json.dumps({"version": 1, "agents": 0}), encoding="utf-8")
    rd = resolve_defaults(runtime)
    assert rd.agents == 1


def test_resolve_view_shape(tmp_path):
    runtime = tmp_path / "runtime"
    save_at(runtime, Scope.GLOBAL, None, {"agents": 2})
    view = resolve_view(runtime, "demo")
    assert set(view) >= {"builtin", "global", "project", "effective"}
    assert view["global"] == {"agents": 2}
    assert view["effective"]["agents"] == 2
