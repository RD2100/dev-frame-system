"""Unit tests for memory_prefs (task 6.2)."""
from __future__ import annotations

import json

import pytest

from control_plane.memory_prefs import (
    MemoryPrefsError,
    load_memory,
    load_preferences,
    save_memory,
    save_preferences,
)
from control_plane.scope_resolver import Scope
from control_plane.scoped_store import ScopedStore


def test_two_layer_separation(tmp_path):
    runtime = tmp_path / "runtime"
    save_preferences(runtime, [{"id": "tone", "kind": "preference", "text": "be terse"}])
    save_memory(runtime, "demo", [{"id": "arch", "kind": "architecture", "text": "hexagonal"}])
    prefs = load_preferences(runtime)
    mem = load_memory(runtime, "demo")
    assert [e["id"] for e in prefs] == ["tone"]
    assert [e["id"] for e in mem] == ["arch"]
    # Preferences are not project memory and vice versa.
    assert load_memory(runtime, "other") == []


def test_id_and_text_validation(tmp_path):
    runtime = tmp_path / "runtime"
    with pytest.raises(MemoryPrefsError):
        save_preferences(runtime, [{"id": "", "kind": "preference", "text": "x"}])
    with pytest.raises(MemoryPrefsError):
        save_preferences(runtime, [{"id": "ok", "kind": "preference", "text": "  "}])


def test_unknown_kind_falls_back_to_generic(tmp_path):
    runtime = tmp_path / "runtime"
    save_preferences(runtime, [{"id": "x", "kind": "weird", "text": "hello"}])
    prefs = load_preferences(runtime)
    assert prefs[0]["kind"] == "note"


def test_malformed_entry_skipped_rest_loaded(tmp_path):
    runtime = tmp_path / "runtime"
    path = ScopedStore(runtime, "preferences.json", default_factory=dict).path(Scope.GLOBAL, None)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "version": 1,
                "preferences": [
                    {"id": "good", "kind": "preference", "text": "keep"},
                    {"id": "", "text": "drop"},
                    "not-a-dict",
                ],
            }
        ),
        encoding="utf-8",
    )
    prefs = load_preferences(runtime)
    assert [e["id"] for e in prefs] == ["good"]


def test_malformed_file_returns_empty(tmp_path):
    runtime = tmp_path / "runtime"
    path = ScopedStore(runtime, "memory.json", default_factory=dict).path(Scope.PROJECT, "demo")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{ broken", encoding="utf-8")
    assert load_memory(runtime, "demo") == []


def test_save_memory_requires_project_id(tmp_path):
    runtime = tmp_path / "runtime"
    with pytest.raises(MemoryPrefsError):
        save_memory(runtime, None, [{"id": "x", "kind": "term", "text": "y"}])


def test_load_memory_no_project_is_empty(tmp_path):
    runtime = tmp_path / "runtime"
    assert load_memory(runtime, None) == []
