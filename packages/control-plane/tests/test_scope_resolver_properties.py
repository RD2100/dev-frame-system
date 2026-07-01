"""Hypothesis property tests for the scope_resolver engine (task 1.5).

Each property maps to a Correctness Property in the design document:
- Property 1 & 6: scope monotonicity + determinism
- Property 4: deny-overrides soundness
- Property 5: P0 unoverridability
- Property 3: malformed-injection safety
- Property 8: orthogonality
"""
from __future__ import annotations

import json
import random

from hypothesis import given, settings
from hypothesis import strategies as st

from control_plane.scope_resolver import (
    SKILL_POLICY,
    Scope,
    collect_p0_denies,
    merge_by_id,
    resolve_capabilities,
)
from control_plane.scoped_store import ScopedStore


_ids = st.text(alphabet="abcde", min_size=1, max_size=3)
_scopes = st.sampled_from([Scope.BUILTIN, Scope.GLOBAL, Scope.PROJECT])


def _record(rid, scope):
    return {"id": rid, "src": scope.value}


@st.composite
def _layered_records(draw):
    """Generate per-scope record lists keyed by small ids."""
    layers: dict[Scope, list[dict]] = {s: [] for s in Scope}
    n = draw(st.integers(min_value=0, max_value=12))
    for _ in range(n):
        rid = draw(_ids)
        scope = draw(_scopes)
        # dedupe within a layer (loaders guarantee this)
        if all(r["id"] != rid for r in layers[scope]):
            layers[scope].append(_record(rid, scope))
    return layers


# --- Property 1 & 6: scope monotonicity + determinism ------------------------

@settings(max_examples=200)
@given(_layered_records())
def test_scope_monotonicity_and_determinism(layers):
    order = (Scope.PROJECT, Scope.GLOBAL, Scope.BUILTIN)  # most- to least-specific

    def expected_scope(rid):
        for scope in order:
            if any(r["id"] == rid for r in layers[scope]):
                return scope.value
        return None

    merged = {r["id"]: r for r in merge_by_id(layers)}
    for rid, record in merged.items():
        assert record["_scope"] == expected_scope(rid)

    # Determinism: shuffling each layer's order yields identical effective output.
    shuffled = {}
    for scope, records in layers.items():
        copy = list(records)
        random.Random(123).shuffle(copy)
        shuffled[scope] = copy
    merged2 = {r["id"]: r["_scope"] for r in merge_by_id(shuffled)}
    assert {r["id"]: r["_scope"] for r in merged.values()} == merged2


# --- Property 4: deny-overrides soundness ------------------------------------

@settings(max_examples=200)
@given(
    st.lists(
        st.fixed_dictionaries(
            {
                "id": _ids,
                "networkEnabled": st.booleans(),
                "enabled": st.booleans(),
            }
        ),
        max_size=8,
    ),
    st.booleans(),
)
def test_deny_overrides_soundness(units, with_p0):
    denies = [{"id": "no-network", "priority": "P0"}] if with_p0 else []
    result = resolve_capabilities(units, SKILL_POLICY, hard_denies=denies)

    enabled_restrictive = any(
        u.get("enabled") is not False and u.get("networkEnabled") is False
        for u in units
    )
    expected_restrictive = enabled_restrictive or with_p0
    # restrictive value for networkEnabled is False
    assert (result["networkEnabled"] is False) == expected_restrictive


# --- Property 5: P0 unoverridability -----------------------------------------

@settings(max_examples=100)
@given(st.integers(min_value=0, max_value=10))
def test_p0_unoverridability(num_permissive_votes):
    units = [
        {"id": f"s{i}", "networkEnabled": True}
        for i in range(num_permissive_votes)
    ]
    denies = [{"id": "no-network", "priority": "P0"}]
    result = resolve_capabilities(units, SKILL_POLICY, hard_denies=denies)
    assert result["networkEnabled"] is False


# --- Property 3: malformed-injection safety ----------------------------------

@settings(max_examples=100)
@given(st.binary(max_size=40))
def test_malformed_injection_never_raises(tmp_path_factory, malformed):
    runtime = tmp_path_factory.mktemp("rt")
    store = ScopedStore(runtime, "x.json", default_factory=list)
    path = store.path(Scope.GLOBAL)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(malformed)
    # Never raises; result is the default unless the bytes happen to be a valid
    # JSON list (in which case the loaded list is returned).
    loaded = store.load(Scope.GLOBAL)
    assert isinstance(loaded, list)


# --- Property 8: orthogonality -----------------------------------------------

@settings(max_examples=150)
@given(_layered_records())
def test_orthogonality_scope_does_not_change_polarity(layers):
    # Annotate each record with a fixed capability vote; scope layering must not
    # change the capability resolution beyond which records are effective.
    for scope, records in layers.items():
        for r in records:
            r["networkEnabled"] = False  # all restrictive

    merged = merge_by_id(layers)
    caps = resolve_capabilities(merged, SKILL_POLICY)
    # With any effective record voting restrictive, network must be False;
    # with none, it stays permissive. Polarity depends only on votes.
    if merged:
        assert caps["networkEnabled"] is False
    else:
        assert caps["networkEnabled"] is True
