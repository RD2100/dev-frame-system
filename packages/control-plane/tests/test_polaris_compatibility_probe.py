"""Focused, local-only tests for the pinned Polaris/DSH compatibility shape.

This module deliberately stops at the transport-neutral contract boundary.  It
does not create a Polaris client, make a network request, or normalize data for
production.  The fixture is evidence about the exact ``dsh-readonly-v1``
profile and its eight model-facing operation names only.
"""
from __future__ import annotations

import json
from typing import Any

import pytest

from fixtures.polaris_compatibility_probe import (
    MAX_ARGUMENT_JSON_CHARS,
    NON_ALLOWLISTED_PUBLIC_NAME,
    PAPER_DOI,
    PROVIDER_PAPER_ID,
    PUBLIC_OPERATIONS,
    PUBLIC_TO_RAW,
    READONLY_PROFILE,
    RESULT_CONTRACT_VERSION,
    FakePolarisDshReadonlyProfile,
    expected_binding,
)


def _subject(public_name: str) -> dict[str, str]:
    raw_name = PUBLIC_TO_RAW[public_name]
    if raw_name in {"search_papers", "search_chunks"}:
        return {"query": "attention"}
    if raw_name == "lookup_paper":
        return {"doi": PAPER_DOI}
    if raw_name in {"get_references", "get_citations"}:
        return {"paper_ref": PROVIDER_PAPER_ID}
    return {"provider_paper_id": PROVIDER_PAPER_ID}


def _structured(response: Any) -> dict[str, Any]:
    result = response.body.get("result")
    assert isinstance(result, dict)
    structured = result.get("structuredContent")
    assert isinstance(structured, dict)
    return structured


def test_initialize_reports_pinned_profile_and_protocol() -> None:
    response = FakePolarisDshReadonlyProfile().initialize()

    assert response.status_code == 200
    result = response.body["result"]
    assert result["_meta"]["profile"] == READONLY_PROFILE
    assert result["protocolVersion"] == "2024-11-05"
    assert result["serverInfo"] == {"name": "polaris", "version": "v0.3.8"}


def test_catalog_is_complete_paginated_and_model_view_is_exactly_eight() -> None:
    server = FakePolarisDshReadonlyProfile()

    raw_catalog = server.complete_catalog()
    raw_names = tuple(item["name"] for item in raw_catalog)

    assert raw_names == (
        "search_papers",
        "search_chunks",
        "get_paper",
        "lookup_paper",
        "read_fulltext",
        "get_paper_citation",
        "get_references",
        "get_citations",
    )
    assert server.model_facing_catalog() == PUBLIC_OPERATIONS


def test_non_allowlisted_public_name_is_rejected_before_remote_call() -> None:
    server = FakePolarisDshReadonlyProfile()

    response = server.invoke_public(NON_ALLOWLISTED_PUBLIC_NAME)

    assert response.body["error"]["code"] == -32030
    assert server.call_count == 0
    assert server.raw_calls == []


@pytest.mark.parametrize("public_name", PUBLIC_OPERATIONS)
def test_each_public_operation_returns_bounded_untrusted_result(public_name: str) -> None:
    server = FakePolarisDshReadonlyProfile()

    response = server.invoke_public(
        public_name,
        subject=_subject(public_name),
        arguments={"page": 1},
        idempotency_key=f"idem-{public_name}",
    )
    structured = _structured(response)

    assert structured["contract_version"] == RESULT_CONTRACT_VERSION
    assert structured["operation"] == PUBLIC_TO_RAW[public_name]
    assert structured["content_is_untrusted"] is True
    assert structured["remote_freshness"] == "unknown"
    assert structured["remote_truncated"] == "unknown"
    assert structured["binding"] == {
        "local_project_id": expected_binding()["local_project_id"],
        "remote_project_id": expected_binding()["remote_project_id"],
        "provider_echoed_remote_project_id": False,
    }
    assert structured["request_hash"].startswith("sha256:")
    assert structured["result_hash"].startswith("sha256:")
    assert server.call_count == 1


def test_project_binding_mismatch_fails_closed_before_provider_call() -> None:
    server = FakePolarisDshReadonlyProfile()
    binding = expected_binding()
    binding["remote_project_id"] = "another-remote-project"

    response = server.invoke_public(
        "mcp__polaris__search_papers",
        binding=binding,
        subject={"query": "attention"},
    )

    assert response.body["error"]["code"] == -32041
    assert server.call_count == 0


def test_subject_rules_separate_discovery_lookup_known_paper_and_graph() -> None:
    server = FakePolarisDshReadonlyProfile()

    missing_known = server.invoke_public(
        "mcp__polaris__get_paper", subject={}, idempotency_key="missing-known"
    )
    invalid_graph = server.invoke_public(
        "mcp__polaris__get_references",
        subject={"paper_ref": "other-paper"},
        idempotency_key="invalid-graph",
    )
    valid_lookup = server.invoke_public(
        "mcp__polaris__lookup_paper",
        subject={"doi": PAPER_DOI},
        idempotency_key="valid-lookup",
    )

    assert missing_known.body["error"]["code"] == -32050
    assert invalid_graph.body["error"]["code"] == -32053
    assert _structured(valid_lookup)["payload"]["paper"]["external_ids"]["doi"] == PAPER_DOI


def test_request_and_result_hashes_are_deterministic_and_include_arguments() -> None:
    first = FakePolarisDshReadonlyProfile().invoke_public(
        "mcp__polaris__search_papers",
        subject={"query": "attention"},
        arguments={"page": 1},
        idempotency_key="hash-1",
    )
    second = FakePolarisDshReadonlyProfile().invoke_public(
        "mcp__polaris__search_papers",
        subject={"query": "attention"},
        arguments={"page": 1},
        idempotency_key="hash-1",
    )
    changed = FakePolarisDshReadonlyProfile().invoke_public(
        "mcp__polaris__search_papers",
        subject={"query": "attention"},
        arguments={"page": 2},
        idempotency_key="hash-2",
    )

    first_structured = _structured(first)
    second_structured = _structured(second)
    changed_structured = _structured(changed)
    assert first_structured["request_hash"] == second_structured["request_hash"]
    assert first_structured["result_hash"] == second_structured["result_hash"]
    assert first_structured["request_hash"] != changed_structured["request_hash"]
    assert first_structured["result_hash"] != changed_structured["result_hash"]


def test_replay_is_idempotent_but_same_key_with_changed_request_is_rejected() -> None:
    server = FakePolarisDshReadonlyProfile()
    kwargs = {
        "subject": {"query": "attention"},
        "arguments": {"page": 1},
        "idempotency_key": "replay-1",
    }

    first = server.invoke_public("mcp__polaris__search_papers", **kwargs)
    replay = server.invoke_public("mcp__polaris__search_papers", **kwargs)
    conflict = server.invoke_public(
        "mcp__polaris__search_papers",
        subject={"query": "different"},
        arguments={"page": 1},
        idempotency_key="replay-1",
    )

    assert replay.body == first.body
    assert server.call_count == 1
    assert conflict.body["error"]["code"] == -32060


def test_remote_truncation_and_prompt_injection_remain_explicit_untrusted_data() -> None:
    truncated = FakePolarisDshReadonlyProfile(mode="remote-truncated").invoke_public(
        "mcp__polaris__read_fulltext",
        subject={"provider_paper_id": PROVIDER_PAPER_ID},
        idempotency_key="truncated-1",
    )
    injected = FakePolarisDshReadonlyProfile(mode="prompt-injection").invoke_public(
        "mcp__polaris__read_fulltext",
        subject={"provider_paper_id": PROVIDER_PAPER_ID},
        idempotency_key="injected-1",
    )

    assert _structured(truncated)["remote_truncated"] is True
    injected_structured = _structured(injected)
    assert injected_structured["content_is_untrusted"] is True
    assert "IGNORE ALL PRIOR RULES" in injected_structured["payload"]["sections"][0]["text"]


def test_oversized_passage_and_structured_result_fail_closed() -> None:
    oversized_passage = FakePolarisDshReadonlyProfile(mode="large-passage").invoke_public(
        "mcp__polaris__read_fulltext",
        subject={"provider_paper_id": PROVIDER_PAPER_ID},
        idempotency_key="oversized-passage",
    )
    oversized_result = FakePolarisDshReadonlyProfile(mode="large-result").invoke_public(
        "mcp__polaris__get_paper",
        subject={"provider_paper_id": PROVIDER_PAPER_ID},
        idempotency_key="oversized-result",
    )

    assert oversized_passage.body["error"]["code"] == -32054
    assert oversized_result.body["error"]["code"] == -32055


@pytest.mark.parametrize("mode", ("malformed", "error", "unknown-field", "missing-payload"))
def test_failure_modes_are_visible_to_a_future_adapter(mode: str) -> None:
    server = FakePolarisDshReadonlyProfile(mode=mode)
    response = server.invoke_public(
        "mcp__polaris__get_paper",
        subject={"provider_paper_id": PROVIDER_PAPER_ID},
        idempotency_key=f"mode-{mode}",
    )

    assert response.status_code == 200
    result = response.body["result"]
    if mode == "malformed":
        assert "structuredContent" not in result
    elif mode == "error":
        assert result["isError"] is True
    elif mode == "unknown-field":
        assert "future_provider_field" in result["structuredContent"]
    else:
        assert "payload" not in result["structuredContent"]


def test_transport_error_is_bounded_and_profile_mismatch_fails_closed() -> None:
    unavailable = FakePolarisDshReadonlyProfile(mode="transport-error").invoke_public(
        "mcp__polaris__search_papers",
        subject={"query": "attention"},
        idempotency_key="transport-1",
    )
    wrong_profile = FakePolarisDshReadonlyProfile(profile="dsh-full-v1").invoke_public(
        "mcp__polaris__search_papers",
        subject={"query": "attention"},
        idempotency_key="profile-1",
    )

    assert unavailable.status_code == 503
    assert wrong_profile.body["error"]["code"] == -32031


def test_private_paths_and_urls_are_rejected_from_binding() -> None:
    server = FakePolarisDshReadonlyProfile()
    binding = expected_binding()
    binding["server_alias"] = "https://private.example/mcp"

    response = server.invoke_public(
        "mcp__polaris__search_papers",
        binding=binding,
        subject={"query": "attention"},
        idempotency_key="private-binding",
    )

    assert response.body["error"]["code"] == -32041
    assert server.call_count == 0


def test_argument_budget_is_bounded() -> None:
    server = FakePolarisDshReadonlyProfile()
    oversized = {"text": "x" * (MAX_ARGUMENT_JSON_CHARS + 1)}

    response = server.invoke_public(
        "mcp__polaris__search_papers",
        subject={"query": "attention"},
        arguments=oversized,
        idempotency_key="oversized-arguments",
    )

    assert response.body["error"]["code"] == -32052
    assert server.call_count == 0


def test_fixture_does_not_create_second_authority_or_execute_provider_text() -> None:
    server = FakePolarisDshReadonlyProfile(mode="prompt-injection")
    structured = _structured(
        server.invoke_public(
            "mcp__polaris__search_papers",
            subject={"query": "attention"},
            idempotency_key="authority-1",
        )
    )

    assert "task" not in structured
    assert "run" not in structured
    assert "final_verdict" not in structured
    assert structured["content_is_untrusted"] is True


def test_unexpected_catalog_cursor_fails_closed() -> None:
    server = FakePolarisDshReadonlyProfile()
    response = server.handle(
        {
            "jsonrpc": "2.0",
            "id": 99,
            "method": "tools/list",
            "params": {"cursor": "not-a-page"},
        }
    )

    assert response.body["error"]["code"] == -32602


def test_response_is_json_serializable_without_provider_metadata_leak() -> None:
    response = FakePolarisDshReadonlyProfile().invoke_public(
        "mcp__polaris__get_paper_citation",
        subject={"provider_paper_id": PROVIDER_PAPER_ID},
        idempotency_key="json-1",
    )

    encoded = json.dumps(response.body, ensure_ascii=False, sort_keys=True)
    assert "credential_ref" not in encoded
    assert "authorization" not in encoded
    assert "https://" not in encoded
