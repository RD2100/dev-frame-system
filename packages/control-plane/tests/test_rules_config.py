"""Tests for the machine-readable governance rules layer.

Built-in prose rules (rules/*.md) are parsed into structured read-only records;
custom rules are stored under the runtime dir, editable, and override built-ins
by id. This makes rules machine-readable (a prerequisite for enforcement) and
visually editable.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from control_plane.rules_config import (  # noqa: E402
    CustomRuleError,
    list_all_rules,
    list_builtin_rules,
    load_custom_rules,
    save_custom_rules,
)


def test_builtin_rules_parse_from_markdown():
    rules = list_builtin_rules()
    by_id = {r["id"]: r for r in rules}
    # core-001 is a known P0 hard stop in rules/core.md.
    assert "core-001" in by_id
    core1 = by_id["core-001"]
    assert core1["priority"] == "P0"
    assert core1["domain"] == "core"
    assert core1["editable"] is False
    assert core1["rule"]  # rule text was captured
    assert core1["title"]
    # A range of priorities is parsed across the rule set.
    assert {"P0", "P1", "P2"} <= {r["priority"] for r in rules}


def test_save_and_load_custom_rule(tmp_path):
    runtime = tmp_path / "runtime"
    assert load_custom_rules(runtime) == []
    saved = save_custom_rules(runtime, [
        {
            "id": "Team No Direct Main",
            "priority": "P1",
            "rule": "Never push directly to main.",
            "trigger": "git push",
            "verification": "branch != main",
        }
    ])
    assert len(saved) == 1
    assert saved[0]["id"] == "team-no-direct-main"
    assert saved[0]["priority"] == "P1"
    assert load_custom_rules(runtime) == saved


def test_save_custom_rules_validation(tmp_path):
    runtime = tmp_path / "runtime"
    with pytest.raises(CustomRuleError):
        save_custom_rules(runtime, [{"id": "x", "priority": "P9", "rule": "bad priority"}])
    with pytest.raises(CustomRuleError):
        save_custom_rules(runtime, [{"id": "x", "priority": "P0", "rule": ""}])
    with pytest.raises(CustomRuleError):
        save_custom_rules(runtime, [
            {"id": "dup", "priority": "P0", "rule": "a"},
            {"id": "dup", "priority": "P1", "rule": "b"},
        ])


def test_malformed_rules_file_falls_back(tmp_path):
    from control_plane.rules_config import _rules_path

    runtime = tmp_path / "runtime"
    path = _rules_path(runtime)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{ broken", encoding="utf-8")
    assert load_custom_rules(runtime) == []


def test_list_all_rules_merges_and_overrides(tmp_path):
    runtime = tmp_path / "runtime"
    combined = list_all_rules(runtime)
    assert any(r["id"] == "core-001" for r in combined["builtin"])
    assert combined["custom"] == []

    # Overriding a built-in id moves it into the editable custom list.
    save_custom_rules(runtime, [{"id": "core-001", "priority": "P0", "rule": "My override."}])
    combined = list_all_rules(runtime)
    assert not any(r["id"] == "core-001" for r in combined["builtin"])
    assert any(r["id"] == "core-001" and r["editable"] is True for r in combined["custom"])


# --- Scope-aware retrofit + P0 collection (task 3.6) -------------------------

def _rules_global_path(runtime):
    from control_plane.scoped_store import ScopedStore
    from control_plane.scope_resolver import Scope

    return ScopedStore(runtime, "rules.json", default_factory=dict).path(Scope.GLOBAL, None)


def _rules_project_path(runtime, project_id):
    from control_plane.scoped_store import ScopedStore
    from control_plane.scope_resolver import Scope

    return ScopedStore(runtime, "rules.json", default_factory=dict).path(Scope.PROJECT, project_id)


def test_resolve_rules_compat_no_project(tmp_path):
    from control_plane.rules_config import resolve_rules, save_custom_rules

    runtime = tmp_path / "runtime"
    save_custom_rules(runtime, [{"id": "my-rule", "priority": "P2", "rule": "do a thing"}])
    rc = resolve_rules(runtime)
    assert rc.project == []
    effective = {r["id"]: r for r in rc.effective}
    assert effective["my-rule"]["_scope"] == "global"


def test_resolve_rules_project_overrides_global(tmp_path):
    from control_plane.rules_config import resolve_rules, save_at
    from control_plane.scope_resolver import Scope

    runtime = tmp_path / "runtime"
    save_at(runtime, Scope.GLOBAL, None, [{"id": "r", "priority": "P2", "rule": "global text"}])
    save_at(runtime, Scope.PROJECT, "demo", [{"id": "r", "priority": "P1", "rule": "project text"}])
    rc = resolve_rules(runtime, "demo")
    effective = {r["id"]: r for r in rc.effective}
    assert effective["r"]["rule"] == "project text"
    assert effective["r"]["priority"] == "P1"
    assert effective["r"]["_scope"] == "project"


def test_resolve_rules_malformed_project_falls_back(tmp_path):
    from control_plane.rules_config import resolve_rules, save_at
    from control_plane.scope_resolver import Scope

    runtime = tmp_path / "runtime"
    save_at(runtime, Scope.GLOBAL, None, [{"id": "r", "priority": "P2", "rule": "global text"}])
    path = _rules_project_path(runtime, "demo")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{ broken", encoding="utf-8")
    rc = resolve_rules(runtime, "demo")
    effective = {r["id"]: r for r in rc.effective}
    assert effective["r"]["rule"] == "global text"


def test_p0_rule_drives_hard_deny(tmp_path):
    from control_plane.rules_config import collect_p0_rule_denies, save_at
    from control_plane.scope_resolver import SKILL_POLICY, Scope, resolve_capabilities

    runtime = tmp_path / "runtime"
    save_at(
        runtime,
        Scope.PROJECT,
        "demo",
        [{"id": "no-network", "priority": "P0", "rule": "no-network egress allowed"}],
    )
    denies = collect_p0_rule_denies(runtime, "demo")
    assert any(d["id"] == "no-network" for d in denies)
    # A permissive skill vote must lose to the P0 rule deny.
    units = [{"id": "s", "networkEnabled": True}]
    result = resolve_capabilities(units, SKILL_POLICY, hard_denies=denies)
    assert result["networkEnabled"] is False
