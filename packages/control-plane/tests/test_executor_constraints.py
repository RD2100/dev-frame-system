"""Executor-packet constraint tests for the locked deny-overrides examples (task 8.3).

These assert that scope-resolved skills + P0 rules become hard constraints on the
methodology that go_dispatch hands to the executor (not model attention):
- read-only wins (skill A readOnly=true beats skill B readOnly=false)
- P0 no-network beats a methodology profile's network_enabled=true
"""
from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from control_plane.custom_skills import save_at as save_skills_at
from control_plane.go_dispatch import _shard_requirement
from control_plane.methodology_dispatch import resolve_methodology
from control_plane.rules_config import save_at as save_rules_at
from control_plane.scope_resolver import Scope


def test_read_only_wins_at_packet_boundary(tmp_path):
    runtime = tmp_path / "runtime"
    save_skills_at(
        runtime,
        Scope.GLOBAL,
        None,
        [
            {"id": "a", "title": "A", "readOnly": True},
            {"id": "b", "title": "B", "readOnly": False},
        ],
    )
    _effective, methodology = resolve_methodology(
        "@go edit implement feature", runtime_dir=runtime, project_id="demo"
    )
    assert methodology is not None
    assert methodology["read_only"] is True
    assert methodology["constraints"]["readOnly"] is True
    # The hard constraint is surfaced in the shard requirement, not left implicit.
    shard = _shard_requirement("impl", 1, 1, [], methodology)
    assert "READ-ONLY" in shard


def test_p0_no_network_beats_skill_network_enabled(tmp_path):
    runtime = tmp_path / "runtime"
    # A skill that wants network, plus a P0 rule that denies it.
    save_skills_at(
        runtime,
        Scope.GLOBAL,
        None,
        [{"id": "net", "title": "Net", "networkEnabled": True}],
    )
    save_rules_at(
        runtime,
        Scope.PROJECT,
        "demo",
        [{"id": "no-network", "priority": "P0", "rule": "no-network egress allowed"}],
    )
    # @go risky's profile sets network_enabled=True; the P0 deny must win.
    _effective, methodology = resolve_methodology(
        "@go risky do something", runtime_dir=runtime, project_id="demo"
    )
    assert methodology is not None
    assert methodology["network_enabled"] is False
    assert methodology["constraints"]["networkEnabled"] is False
    shard = _shard_requirement("do", 1, 1, [], methodology)
    assert "NO NETWORK" in shard


def test_no_project_id_is_unchanged(tmp_path):
    runtime = tmp_path / "runtime"
    save_skills_at(
        runtime, Scope.GLOBAL, None, [{"id": "a", "title": "A", "readOnly": True}]
    )
    # Without a project id, the result is byte-identical to today: no constraints
    # key and the @go edit profile's own read_only (False) is preserved.
    _effective, methodology = resolve_methodology("@go edit x", runtime_dir=runtime)
    assert methodology is not None
    assert "constraints" not in methodology
    assert methodology["read_only"] is False


@settings(max_examples=60)
@given(st.integers(min_value=0, max_value=6), st.booleans())
def test_p0_unoverridability_at_packet_boundary(tmp_path_factory, num_net_skills, with_p0):
    runtime = tmp_path_factory.mktemp("rt")
    skills = [
        {"id": f"s{i}", "title": f"S{i}", "networkEnabled": True}
        for i in range(num_net_skills)
    ]
    if skills:
        save_skills_at(runtime, Scope.GLOBAL, None, skills)
    if with_p0:
        save_rules_at(
            runtime,
            Scope.PROJECT,
            "demo",
            [{"id": "no-network", "priority": "P0", "rule": "no-network"}],
        )
    _effective, methodology = resolve_methodology(
        "@go risky go", runtime_dir=runtime, project_id="demo"
    )
    assert methodology is not None
    # @go risky starts network_enabled=True; permissive skill votes (networkEnabled
    # True) never tighten it, so network stays True unless a P0 deny forces it off.
    assert methodology["network_enabled"] is (not with_p0)
