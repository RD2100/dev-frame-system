"""Fixture contract for the first read-only graph projection slice.

The fixtures exercise the existing graph validator without creating a graph
store, UI, extractor, or new governance authority.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from control_plane.graph_projection_validator import (
    derive_graph_projection,
    validate_graph_projection,
)


ROOT = Path(__file__).resolve().parents[3]
FIXTURES = ROOT / "schemas" / "examples" / "review-governance"
VALID_FIXTURE = FIXTURES / "graph-projection-valid.json"
INVALID_FIXTURES = (
    "graph-projection-invalid-decision-from-annotation.json",
    "graph-projection-invalid-forbidden-export.json",
    "graph-projection-invalid-run-success-completion.json",
    "graph-projection-invalid-inferred-edge-as-source-truth.json",
    "graph-projection-invalid-graph-store-authority.json",
    "graph-projection-invalid-graph-driven-code-change.json",
)


def _load(name: str) -> dict:
    with (FIXTURES / name).open(encoding="utf-8") as stream:
        return json.load(stream)


def _serialized_strings(value: object) -> list[str]:
    if isinstance(value, dict):
        result: list[str] = []
        for key, item in value.items():
            result.extend(_serialized_strings(key))
            result.extend(_serialized_strings(item))
        return result
    if isinstance(value, list):
        result: list[str] = []
        for item in value:
            result.extend(_serialized_strings(item))
        return result
    if isinstance(value, str):
        return [value]
    return []


def test_valid_fixture_is_a_read_only_projection():
    payload = _load("graph-projection-valid.json")
    before = copy.deepcopy(payload)

    result = validate_graph_projection(payload)
    summary = derive_graph_projection(payload)

    assert result.valid, "\n".join(result.errors)
    assert summary["total_nodes"] == 4
    assert summary["total_edges"] == 3
    assert summary["authority_seeded_count"] == 1
    assert summary["inferred_truth_edges"] == 0
    assert payload == before


@pytest.mark.parametrize("name", INVALID_FIXTURES)
def test_invalid_fixture_fails_closed(name: str):
    payload = _load(name)
    result = validate_graph_projection(payload)

    assert not result.valid, f"fixture unexpectedly accepted: {name}"
    assert result.errors


def test_run_success_cannot_claim_completion_without_gate():
    payload = _load("graph-projection-invalid-run-success-completion.json")
    result = validate_graph_projection(payload)

    assert not result.valid
    assert any("gate" in error.lower() for error in result.errors)
    assert any("run success" in error.lower() for error in result.errors)


def test_gate_backed_completion_is_explicitly_accepted():
    payload = _load("graph-projection-valid.json")
    projection = payload["projection"]
    projection["gate_outcome"] = "pass"
    projection["gate_decision_id"] = "decision-gate-1"

    result = validate_graph_projection(payload)

    assert result.valid, "\n".join(result.errors)


def test_non_object_projection_fails_closed():
    payload = _load("graph-projection-valid.json")
    payload["projection"] = ["completed"]

    result = validate_graph_projection(payload)

    assert not result.valid
    assert any("projection must be an object" in error for error in result.errors)


def test_all_contract_fixtures_are_sanitized():
    for name in ("graph-projection-valid.json", *INVALID_FIXTURES):
        text = (FIXTURES / name).read_text(encoding="utf-8")
        payload = json.loads(text)
        strings = " ".join(_serialized_strings(payload)).lower()
        assert "c:\\" not in strings
        assert "d:\\" not in strings
        assert "token" not in strings
        assert "cookie" not in strings
        assert "password" not in strings


def test_fixture_set_is_complete():
    assert VALID_FIXTURE.is_file()
    for name in INVALID_FIXTURES:
        assert (FIXTURES / name).is_file(), name
