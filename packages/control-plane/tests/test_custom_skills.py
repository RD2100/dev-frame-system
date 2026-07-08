"""Tests for the user-customizable methodology skills layer.

A skill becomes a complete, machine-readable, editable unit: identity (id,
title, triggers, description) plus its behavior profile (read-only / network /
red-green). Built-in repo skills stay read-only; custom skills are stored under
the runtime dir and override built-ins by id.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from control_plane.custom_skills import (  # noqa: E402
    CustomSkillError,
    list_all_skills,
    load_custom_skills,
    save_custom_skills,
)


def test_save_and_load_custom_skill(tmp_path):
    runtime = tmp_path / "runtime"
    assert load_custom_skills(runtime) == []

    saved = save_custom_skills(runtime, [
        {
            "id": "Docs Discipline",
            "title": "Docs Discipline",
            "triggers": ["docs", "@doc-first"],
            "description": "Write docs before code.",
            "readOnly": False,
            "requireRedGreenEvidence": True,
        }
    ])
    assert len(saved) == 1
    skill = saved[0]
    assert skill["id"] == "docs-discipline"
    # Triggers are normalized to @-prefixed slugs.
    assert skill["triggers"] == ["@docs", "@doc-first"]
    assert skill["requireRedGreenEvidence"] is True

    reloaded = load_custom_skills(runtime)
    assert reloaded == saved


def test_skill_without_triggers_gets_default_from_id(tmp_path):
    runtime = tmp_path / "runtime"
    saved = save_custom_skills(runtime, [{"id": "qa-gate", "title": "QA Gate", "triggers": []}])
    assert saved[0]["triggers"] == ["@qa-gate"]


def test_save_custom_skills_validation(tmp_path):
    runtime = tmp_path / "runtime"
    with pytest.raises(CustomSkillError):
        save_custom_skills(runtime, [{"id": "", "title": ""}])
    with pytest.raises(CustomSkillError):
        save_custom_skills(runtime, [
            {"id": "dup", "title": "A", "triggers": ["@a"]},
            {"id": "dup", "title": "B", "triggers": ["@b"]},
        ])


def test_malformed_skills_file_falls_back(tmp_path):
    from control_plane.custom_skills import _skills_path

    runtime = tmp_path / "runtime"
    path = _skills_path(runtime)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{ broken json", encoding="utf-8")
    assert load_custom_skills(runtime) == []


def test_list_all_skills_merges_builtin_and_custom(tmp_path):
    runtime = tmp_path / "runtime"
    combined = list_all_skills(runtime)
    # Built-in skills (e.g. tdd) are present and read-only.
    builtin_ids = {s["id"] for s in combined["builtin"]}
    assert "tdd" in builtin_ids
    assert all(s["editable"] is False for s in combined["builtin"])
    assert combined["custom"] == []

    # A custom skill overriding a built-in id moves it to the editable custom list.
    save_custom_skills(runtime, [{"id": "tdd", "title": "My TDD", "triggers": ["@tdd"]}])
    combined = list_all_skills(runtime)
    assert "tdd" not in {s["id"] for s in combined["builtin"]}
    assert any(s["id"] == "tdd" and s["editable"] is True for s in combined["custom"])


def test_custom_skill_resolves_as_methodology(tmp_path):
    """A user-created custom skill's @trigger resolves through the same
    methodology resolver the executor uses, so it governs runs like a built-in."""
    from control_plane.custom_skills import save_custom_skills
    from control_plane.methodology_dispatch import resolve_methodology

    runtime = tmp_path / "runtime"
    save_custom_skills(runtime, [{
        "id": "doc-first",
        "title": "Docs First",
        "triggers": ["@doc-first"],
        "readOnly": True,
        "requireRedGreenEvidence": True,
    }])

    # Without runtime_dir the custom skill is unknown.
    _eff, none_method = resolve_methodology("@doc-first add a section")
    assert none_method is None

    # Runtime-aware resolution finds it and carries its behavior profile.
    effective, methodology = resolve_methodology("@doc-first add a section", runtime_dir=runtime)
    assert methodology is not None
    assert methodology["skill_id"] == "doc-first"
    assert methodology["read_only"] is True
    assert methodology["require_red_green_evidence"] is True
    assert effective == "add a section"  # trigger stripped from the effective goal


def test_cluster_run_records_governing_methodology(tmp_path, monkeypatch):
    """Starting a &goal with a methodology @trigger records it on the run so the
    detail view can show which methodology governs the run."""
    from control_plane import cluster_run as crm
    from control_plane.custom_skills import save_custom_skills

    monkeypatch.setattr(crm, "_run_cluster_workflow", lambda *a, **k: None)
    runtime = tmp_path / "runtime"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    save_custom_skills(runtime, [{
        "id": "doc-first", "title": "Docs First", "triggers": ["@doc-first"], "readOnly": True,
    }])

    started = crm.start_cluster_run(runtime, str(workspace), "coordinator", "@doc-first 修复登录报错")
    detail = crm.cluster_run_detail(runtime, started["runId"])
    assert detail.get("methodology")
    assert detail["methodology"]["id"] == "doc-first"
    assert detail["methodology"]["readOnly"] is True
    # The coordinator declares the governing methodology in the timeline.
    assert any(m["kind"] == "methodology" for m in detail["messages"])


# --- Scope-aware retrofit + constraints (task 3.4) ---------------------------

def _skills_project_path(runtime, project_id):
    from control_plane.scoped_store import ScopedStore
    from control_plane.scope_resolver import Scope

    return ScopedStore(runtime, "skills.json", default_factory=dict).path(
        Scope.PROJECT, project_id
    )


def test_resolve_skills_compat_no_project(tmp_path):
    from control_plane.custom_skills import resolve_skills, save_custom_skills

    runtime = tmp_path / "runtime"
    save_custom_skills(runtime, [{"id": "my-skill", "title": "My Skill"}])
    rc = resolve_skills(runtime)
    assert rc.project == []
    effective = {s["id"]: s for s in rc.effective}
    assert effective["my-skill"]["_scope"] == "global"


def test_resolve_skills_project_overrides_global(tmp_path):
    from control_plane.custom_skills import resolve_skills, save_at
    from control_plane.scope_resolver import Scope

    runtime = tmp_path / "runtime"
    save_at(runtime, Scope.GLOBAL, None, [{"id": "s", "title": "Global"}])
    save_at(runtime, Scope.PROJECT, "demo", [{"id": "s", "title": "Project"}])
    rc = resolve_skills(runtime, "demo")
    effective = {s["id"]: s for s in rc.effective}
    assert effective["s"]["title"] == "Project"
    assert effective["s"]["_scope"] == "project"


def test_resolve_skills_malformed_project_falls_back(tmp_path):
    from control_plane.custom_skills import resolve_skills, save_at
    from control_plane.scope_resolver import Scope

    runtime = tmp_path / "runtime"
    save_at(runtime, Scope.GLOBAL, None, [{"id": "s", "title": "Global"}])
    path = _skills_project_path(runtime, "demo")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{ broken", encoding="utf-8")
    rc = resolve_skills(runtime, "demo")
    effective = {s["id"]: s for s in rc.effective}
    assert effective["s"]["title"] == "Global"


def test_resolve_skills_constraints_read_only_wins(tmp_path):
    from control_plane.custom_skills import resolve_skills, save_at
    from control_plane.scope_resolver import Scope

    runtime = tmp_path / "runtime"
    save_at(
        runtime,
        Scope.GLOBAL,
        None,
        [
            {"id": "a", "title": "A", "readOnly": True},
            {"id": "b", "title": "B", "readOnly": False},
        ],
    )
    rc = resolve_skills(runtime)
    assert rc.constraints is not None
    assert rc.constraints["readOnly"] is True


def test_resolve_skills_per_record_skip(tmp_path):
    from control_plane.custom_skills import load_skills_at, save_at
    from control_plane.scope_resolver import Scope

    runtime = tmp_path / "runtime"
    # Save a valid one, then hand-write a file with one valid + one malformed.
    import json

    from control_plane.scoped_store import ScopedStore

    path = ScopedStore(runtime, "skills.json", default_factory=dict).path(Scope.GLOBAL, None)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"version": 1, "skills": [{"id": "ok", "title": "OK"}, {"no": "id"}]}),
        encoding="utf-8",
    )
    loaded = load_skills_at(runtime, Scope.GLOBAL, None)
    assert [s["id"] for s in loaded] == ["ok"]
