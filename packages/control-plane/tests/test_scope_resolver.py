"""Unit tests for the reusable scope_resolver engine and ScopedStore (tasks 1.4)."""
from __future__ import annotations

import json

import pytest

from control_plane.scope_resolver import (
    SKILL_POLICY,
    CapabilityFlag,
    CapabilityPolicy,
    Scope,
    SCOPE_ORDER,
    collect_p0_denies,
    deny_targets,
    merge_by_id,
    resolve,
    resolve_capabilities,
)
from control_plane.scoped_store import ScopedStore, scoped_path


# --- merge_by_id -------------------------------------------------------------

def test_merge_by_id_most_specific_wins():
    layers = {
        Scope.BUILTIN: [{"id": "a", "v": "builtin"}],
        Scope.GLOBAL: [{"id": "a", "v": "global"}, {"id": "b", "v": "global"}],
        Scope.PROJECT: [{"id": "a", "v": "project"}],
    }
    merged = {r["id"]: r for r in merge_by_id(layers)}
    assert merged["a"]["v"] == "project"
    assert merged["a"]["_scope"] == "project"
    assert merged["b"]["v"] == "global"
    assert merged["b"]["_scope"] == "global"


def test_merge_by_id_single_scope_passthrough():
    layers = {Scope.GLOBAL: [{"id": "x"}, {"id": "y"}]}
    merged = merge_by_id(layers)
    assert {r["id"] for r in merged} == {"x", "y"}
    assert all(r["_scope"] == "global" for r in merged)


def test_merge_by_id_one_record_per_id():
    layers = {
        Scope.BUILTIN: [{"id": "a"}],
        Scope.GLOBAL: [{"id": "a"}],
        Scope.PROJECT: [{"id": "a"}],
    }
    merged = merge_by_id(layers)
    assert len(merged) == 1
    assert merged[0]["_scope"] == "project"


def test_merge_by_id_skips_invalid_records():
    layers = {
        Scope.GLOBAL: ["not-a-dict", {"no_id": True}, {"id": "ok"}],
    }
    merged = merge_by_id(layers)
    assert [r["id"] for r in merged] == ["ok"]


# --- resolve_capabilities ----------------------------------------------------

def test_read_only_wins():
    units = [{"id": "a", "readOnly": True}, {"id": "b", "readOnly": False}]
    result = resolve_capabilities(units, SKILL_POLICY)
    assert result["readOnly"] is True


def test_no_network_wins():
    units = [{"id": "a", "networkEnabled": True}, {"id": "b", "networkEnabled": False}]
    result = resolve_capabilities(units, SKILL_POLICY)
    assert result["networkEnabled"] is False


def test_require_evidence_wins():
    units = [{"id": "a", "requireRedGreenEvidence": True}, {"id": "b"}]
    result = resolve_capabilities(units, SKILL_POLICY)
    assert result["requireRedGreenEvidence"] is True


def test_permissive_only_stays_permissive():
    units = [{"id": "a", "readOnly": False, "networkEnabled": True}]
    result = resolve_capabilities(units, SKILL_POLICY)
    assert result == {
        "readOnly": False,
        "networkEnabled": True,
        "requireRedGreenEvidence": False,
    }


def test_disabled_units_ignored():
    units = [{"id": "a", "readOnly": True, "enabled": False}]
    result = resolve_capabilities(units, SKILL_POLICY)
    assert result["readOnly"] is False


def test_p0_hard_deny_overrides_permissive_votes():
    units = [{"id": "a", "networkEnabled": True}, {"id": "b", "networkEnabled": True}]
    denies = [{"id": "no-network", "priority": "P0", "rule": "no-network egress"}]
    result = resolve_capabilities(units, SKILL_POLICY, hard_denies=denies)
    assert result["networkEnabled"] is False


def test_deny_targets_structured_and_alias():
    no_net = CapabilityFlag("networkEnabled", False)
    assert deny_targets({"flag": "networkEnabled"}, no_net) is True
    assert deny_targets({"id": "no-network"}, no_net) is True
    assert deny_targets({"id": "unrelated"}, no_net) is False


def test_collect_p0_denies_all_layers():
    layers = {
        Scope.BUILTIN: [{"id": "x", "priority": "P0"}],
        Scope.GLOBAL: [{"id": "y", "priority": "P1"}],
        Scope.PROJECT: [{"id": "z", "priority": "P0"}],
    }
    denies = collect_p0_denies(layers)
    assert {d["id"] for d in denies} == {"x", "z"}


# --- resolve orchestrator ----------------------------------------------------

class _Loaders:
    def __init__(self, builtin, glob, proj):
        self._b, self._g, self._p = builtin, glob, proj

    def builtin(self):
        return self._b

    def global_(self):
        return self._g

    def project(self, project_id):
        return self._p


def test_resolve_without_policy_has_no_constraints():
    loaders = _Loaders([{"id": "a"}], [{"id": "b"}], [{"id": "c"}])
    rc = resolve("team", loaders, project_id="proj")
    assert rc.constraints is None
    assert {r["id"] for r in rc.effective} == {"a", "b", "c"}


def test_resolve_with_policy_populates_constraints():
    loaders = _Loaders(
        [],
        [{"id": "a", "readOnly": True}],
        [{"id": "b", "readOnly": False}],
    )
    rc = resolve("skills", loaders, project_id="proj", policy=SKILL_POLICY)
    assert rc.constraints["readOnly"] is True


def test_resolve_no_project_id_skips_project_layer():
    loaders = _Loaders([], [{"id": "g"}], [{"id": "p"}])
    rc = resolve("team", loaders, project_id=None)
    assert rc.project == []
    assert {r["id"] for r in rc.effective} == {"g"}


# --- scoped_path / ScopedStore ----------------------------------------------

def test_scoped_path_mapping(tmp_path):
    runtime = tmp_path / "runtime"
    assert scoped_path(runtime, "skills.json", Scope.GLOBAL, None) == (runtime / "skills.json").resolve()
    assert scoped_path(runtime, "skills.json", Scope.PROJECT, "demo") == (runtime / "demo" / "skills.json").resolve()


def test_scoped_path_builtin_raises(tmp_path):
    with pytest.raises(ValueError):
        scoped_path(tmp_path, "skills.json", Scope.BUILTIN, None)


def test_scoped_path_project_requires_id(tmp_path):
    with pytest.raises(ValueError):
        scoped_path(tmp_path, "skills.json", Scope.PROJECT, None)


def test_scoped_path_rejects_escape(tmp_path):
    with pytest.raises(ValueError):
        scoped_path(tmp_path / "runtime", "skills.json", Scope.PROJECT, "../../etc")


def test_scoped_store_malformed_returns_default(tmp_path):
    store = ScopedStore(tmp_path / "runtime", "skills.json", default_factory=list)
    path = store.path(Scope.GLOBAL)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{ not valid json", encoding="utf-8")
    assert store.load(Scope.GLOBAL) == []


def test_scoped_store_wrong_root_type_returns_default(tmp_path):
    store = ScopedStore(tmp_path / "runtime", "x.json", default_factory=dict)
    path = store.path(Scope.GLOBAL)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps([1, 2, 3]), encoding="utf-8")
    assert store.load(Scope.GLOBAL) == {}


def test_scoped_store_atomic_ascii_write(tmp_path):
    store = ScopedStore(tmp_path / "runtime", "x.json", default_factory=dict)
    store.save(Scope.PROJECT, {"k": "café"}, project_id="demo")
    text = store.path(Scope.PROJECT, "demo").read_text(encoding="utf-8")
    assert "caf\\u00e9" in text  # ensure_ascii=True
    assert store.load(Scope.PROJECT, "demo") == {"k": "café"}


def test_scoped_store_builtin_load_is_default(tmp_path):
    store = ScopedStore(tmp_path, "x.json", default_factory=list)
    assert store.load(Scope.BUILTIN) == []
