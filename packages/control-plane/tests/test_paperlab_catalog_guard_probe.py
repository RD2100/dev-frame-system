"""Focused tests for the PaperLab catalog and invocation guard boundary."""
from __future__ import annotations

import pytest

from fixtures.polaris_catalog_guard_probe import (
    BROAD_READONLY_EXTRA_NAMES,
    DEFAULT_BROAD_CATALOG,
    FOREIGN_NAMES,
    HIDDEN_OR_AUTHORITY_NAMES,
    MAX_CATALOG_ENTRIES,
    PAPERLAB_RAW_OPERATIONS,
    PUBLIC_OPERATIONS,
    WRITE_NAMES,
    FakeCatalogGuard,
)


def _namespaced_catalog() -> list[dict[str, str]]:
    return [{"name": public_name} for public_name in PUBLIC_OPERATIONS]


def test_broad_catalog_is_narrowed_to_exact_eight_stable_names() -> None:
    guard = FakeCatalogGuard()

    snapshot = guard.publish(DEFAULT_BROAD_CATALOG, generation=1)

    assert snapshot.status == "ready"
    assert snapshot.generation == 1
    assert snapshot.candidate_available is True
    assert guard.model_facing_catalog() == PUBLIC_OPERATIONS
    assert set(snapshot.public_names) == set(PUBLIC_OPERATIONS)


@pytest.mark.parametrize(
    "raw_name",
    (*BROAD_READONLY_EXTRA_NAMES, *HIDDEN_OR_AUTHORITY_NAMES, *WRITE_NAMES),
)
def test_non_canary_polaris_names_disappear_from_model_catalog(raw_name: str) -> None:
    guard = FakeCatalogGuard()
    guard.publish(DEFAULT_BROAD_CATALOG, generation=1)

    assert f"mcp__polaris__{raw_name}" not in guard.model_facing_catalog()


@pytest.mark.parametrize("foreign_name", FOREIGN_NAMES)
def test_foreign_server_names_are_not_callable(foreign_name: str) -> None:
    guard = FakeCatalogGuard()
    guard.publish(DEFAULT_BROAD_CATALOG, generation=1)

    result = guard.invoke(foreign_name)

    assert result.ok is False
    assert result.error == "name_not_allowlisted"
    assert result.candidate is None
    assert guard.provider_call_count == 0


@pytest.mark.parametrize("public_name", PUBLIC_OPERATIONS)
def test_each_allowlisted_name_reaches_provider_after_guard(public_name: str) -> None:
    guard = FakeCatalogGuard()
    guard.publish(DEFAULT_BROAD_CATALOG, generation=1)

    result = guard.invoke(public_name)

    assert result.ok is True
    assert result.error is None
    assert result.candidate == {
        "source": "fixture",
        "operation": public_name.removeprefix("mcp__polaris__"),
        "authority": "devframe",
    }
    assert guard.provider_call_count == 1


def test_provider_entries_may_be_namespaced_but_output_stays_stable() -> None:
    guard = FakeCatalogGuard()

    guard.publish(_namespaced_catalog(), generation=1)

    assert guard.model_facing_catalog() == PUBLIC_OPERATIONS


def test_missing_allowlisted_operation_is_unavailable_and_cannot_call() -> None:
    guard = FakeCatalogGuard()
    incomplete = [
        entry
        for entry in DEFAULT_BROAD_CATALOG
        if entry["name"] != PAPERLAB_RAW_OPERATIONS[-1]
    ]

    snapshot = guard.publish(incomplete, generation=1)
    result = guard.invoke(PUBLIC_OPERATIONS[-1])

    assert snapshot.status == "unavailable"
    assert snapshot.reason == "missing_allowlisted_operation"
    assert snapshot.candidate_available is False
    assert result.ok is False
    assert result.error == "catalog_unavailable"
    assert result.candidate is None
    assert guard.provider_call_count == 0


def test_disabled_allowlisted_entry_is_not_treated_as_callable() -> None:
    guard = FakeCatalogGuard()
    disabled = [
        {"name": name, "enabled": name != PAPERLAB_RAW_OPERATIONS[0]}
        for name in PAPERLAB_RAW_OPERATIONS
    ]

    snapshot = guard.publish(disabled, generation=1)
    result = guard.invoke(PUBLIC_OPERATIONS[0])

    assert snapshot.status == "unavailable"
    assert snapshot.reason == "missing_allowlisted_operation"
    assert result.error == "catalog_unavailable"
    assert guard.provider_call_count == 0


@pytest.mark.parametrize(
    ("catalog", "stale", "reason"),
    [
        ([], False, "empty_catalog"),
        (object(), False, "malformed_catalog"),
        ([{"description": "missing name"}], False, "malformed_catalog"),
        ([{"name": 42}], False, "malformed_catalog"),
        (DEFAULT_BROAD_CATALOG, True, "stale_catalog"),
    ],
)
def test_degraded_generation_is_unavailable_without_candidate(
    catalog: object,
    stale: bool,
    reason: str,
) -> None:
    guard = FakeCatalogGuard()

    snapshot = guard.publish(catalog, generation=1, stale=stale)
    result = guard.invoke(PUBLIC_OPERATIONS[0])

    assert snapshot.status == "unavailable"
    assert snapshot.reason == reason
    assert snapshot.public_names == ()
    assert snapshot.candidate_available is False
    assert result.candidate is None
    assert guard.provider_call_count == 0


def test_replacement_clears_old_names_and_reconnect_restores_only_new_generation() -> None:
    guard = FakeCatalogGuard()
    guard.publish(DEFAULT_BROAD_CATALOG, generation=1)

    unavailable = guard.reconnect([], generation=2)
    denied_while_empty = guard.invoke(PUBLIC_OPERATIONS[0])
    restored = guard.reconnect(_namespaced_catalog(), generation=3)
    allowed_after_restore = guard.invoke(PUBLIC_OPERATIONS[0])

    assert unavailable.reason == "empty_catalog"
    assert denied_while_empty.error == "catalog_unavailable"
    assert denied_while_empty.candidate is None
    assert restored.status == "ready"
    assert restored.generation == 3
    assert restored.public_names == PUBLIC_OPERATIONS
    assert allowed_after_restore.ok is True
    assert guard.provider_calls == (PUBLIC_OPERATIONS[0],)


def test_stale_generation_cannot_retain_a_callable_catalog() -> None:
    guard = FakeCatalogGuard()
    guard.publish(DEFAULT_BROAD_CATALOG, generation=2)

    snapshot = guard.publish(DEFAULT_BROAD_CATALOG, generation=1)
    result = guard.invoke(PUBLIC_OPERATIONS[0])

    assert snapshot.status == "unavailable"
    assert snapshot.reason == "stale_generation"
    assert result.error == "catalog_unavailable"
    assert guard.provider_call_count == 0


def test_generation_watermark_never_moves_back_after_stale_input() -> None:
    guard = FakeCatalogGuard()
    guard.publish(DEFAULT_BROAD_CATALOG, generation=2)

    stale = guard.publish(DEFAULT_BROAD_CATALOG, generation=1)
    replay = guard.publish(DEFAULT_BROAD_CATALOG, generation=2)
    restored = guard.publish(DEFAULT_BROAD_CATALOG, generation=3)

    assert stale.reason == "stale_generation"
    assert replay.reason == "stale_generation"
    assert replay.generation == 2
    assert restored.status == "ready"
    assert restored.generation == 3


def test_oversized_catalog_is_malformed_before_filtering() -> None:
    guard = FakeCatalogGuard()
    oversized = list(DEFAULT_BROAD_CATALOG) + [
        {"name": f"extra_{index}"} for index in range(MAX_CATALOG_ENTRIES)
    ]

    snapshot = guard.publish(oversized, generation=1)

    assert snapshot.status == "unavailable"
    assert snapshot.reason == "malformed_catalog"
    assert snapshot.candidate_available is False


def test_exhausted_reconnect_is_bounded_and_fail_closed() -> None:
    guard = FakeCatalogGuard()
    guard.publish(DEFAULT_BROAD_CATALOG, generation=1)

    snapshot = guard.exhaust(generation=2)
    result = guard.invoke(PUBLIC_OPERATIONS[0])

    assert snapshot.status == "unavailable"
    assert snapshot.reason == "reconnect_exhausted"
    assert result.candidate is None
    assert guard.provider_call_count == 0


def test_raw_names_and_wrong_namespace_cannot_bypass_invocation_guard() -> None:
    guard = FakeCatalogGuard()
    guard.publish(DEFAULT_BROAD_CATALOG, generation=1)

    raw_result = guard.invoke(PAPERLAB_RAW_OPERATIONS[0])
    foreign_result = guard.invoke("mcp__other__search_papers")

    assert raw_result.error == "name_not_allowlisted"
    assert foreign_result.error == "name_not_allowlisted"
    assert guard.provider_call_count == 0


def test_malformed_reconnect_does_not_reuse_previous_candidate() -> None:
    guard = FakeCatalogGuard()
    guard.publish(DEFAULT_BROAD_CATALOG, generation=1)

    snapshot = guard.reconnect(["search_papers", None], generation=2)
    result = guard.invoke(PUBLIC_OPERATIONS[0])

    assert snapshot.status == "unavailable"
    assert snapshot.reason == "malformed_catalog"
    assert result.candidate is None
    assert guard.provider_call_count == 0
