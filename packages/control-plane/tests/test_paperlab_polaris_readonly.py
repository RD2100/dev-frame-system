"""Fixture-only contract tests for PaperLab-Canary-0.

The fake is intentionally used in-process.  These tests exercise the
transport-neutral boundary that a future DSH MCP result adapter may consume;
they do not implement or imply a production adapter, network endpoint, or
Polaris authority.
"""
from __future__ import annotations

import inspect
import json
from datetime import datetime, timezone
import re
from typing import Any

import pytest

from fixtures.polaris_readonly_mcp import (
    EXPECTED_DOI,
    EXPECTED_PAPER_ID,
    EXPECTED_PROJECT_ID,
    EXPECTED_TITLE,
    FIXTURE_NOW_ISO,
    HIDDEN_TOOLS,
    MAX_ARGUMENT_JSON_CHARS,
    MAX_PASSAGE_CHARS,
    MAX_RESULT_JSON_CHARS,
    PAYLOAD_FIELDS,
    READONLY_TOOLS,
    FakePolarisReadonlyMcp,
    RpcResponse,
    canonical_json,
    canonical_sha256,
)
from fixtures.polaris_readonly_mcp.fake_server import FIXTURE_SOURCE


STRUCTURED_OPERATIONS = tuple(
    operation for operation in READONLY_TOOLS if operation != "read_fulltext"
)
ALLOWED_SOURCE_VALUES = frozenset(
    {"fixture", FIXTURE_SOURCE, "polaris-release-v0.3.8"}
)
STRUCTURED_PAYLOAD_FIELDS: dict[str, frozenset[str]] = {
    "search_papers": frozenset({"paper_id", "doi", "title", "snippet"}),
    "search_chunks": frozenset({"paper_id", "chunk_id", "text"}),
    "get_paper": frozenset({"paper_id", "doi", "title", "abstract"}),
    "lookup_paper": frozenset({"paper_id", "doi", "title", "abstract"}),
    "get_paper_citation": frozenset({"paper_id", "doi", "title", "year"}),
    "get_references": frozenset({"paper_id", "doi", "title", "year"}),
    "get_citations": frozenset({"paper_id", "doi", "title", "year"}),
}


class ContractBlocked(Exception):
    """Stable test-side reason for a candidate that must fail closed."""


def _request(
    operation: str,
    *,
    project_id: str = EXPECTED_PROJECT_ID,
    paper_id: str = EXPECTED_PAPER_ID,
    correlation_id: str = "corr-001",
    idempotency_key: str = "idem-001",
    arguments: dict[str, Any] | None = None,
    request_id: int = 1,
) -> dict[str, Any]:
    call_arguments: dict[str, Any] = {
        "project_id": project_id,
        "paper_id": paper_id,
        "correlation_id": correlation_id,
        "idempotency_key": idempotency_key,
        **(arguments or {}),
    }
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "method": "tools/call",
        "params": {"name": operation, "arguments": call_arguments},
    }


def _call(
    server: FakePolarisReadonlyMcp,
    operation: str,
    **kwargs: Any,
) -> RpcResponse:
    return server.handle(_request(operation, **kwargs))


def _with_rehashed_passage(response: RpcResponse, passage: str) -> RpcResponse:
    body = json.loads(canonical_json(response.body))
    result = body.get("result")
    assert isinstance(result, dict)
    result["passage"] = passage
    result_without_hashes = {
        key: value for key, value in result.items() if key not in {"request_hash", "result_hash"}
    }
    result["result_hash"] = canonical_sha256(result_without_hashes)
    return RpcResponse(status_code=response.status_code, body=body)


def _error_code(response: RpcResponse) -> int:
    error = response.body.get("error")
    assert isinstance(error, dict)
    code = error.get("code")
    assert isinstance(code, int)
    return code


def _result(response: RpcResponse) -> dict[str, Any]:
    assert response.status_code == 200
    result = response.body.get("result")
    if not isinstance(result, dict):
        raise ContractBlocked("missing-result")
    return result


def _validate_identifier(name: str, value: Any) -> str:
    if (
        not isinstance(value, str)
        or not value.strip()
        or len(value.strip()) > 128
        or "://" in value
        or "/" in value
        or "\\" in value
    ):
        raise ContractBlocked(f"{name}-identifier-invalid")
    return value.strip()


def _validate_paper_identity(
    value: Any,
    *,
    paper_id: str = EXPECTED_PAPER_ID,
    doi: str = EXPECTED_DOI,
    title: str = EXPECTED_TITLE,
) -> None:
    if not isinstance(value, dict):
        raise ContractBlocked("payload-shape")
    if (
        value.get("paper_id") != paper_id
        or value.get("doi") != doi
        or value.get("title") != title
    ):
        raise ContractBlocked("paper-mismatch")


def _reject_unknown_fields(value: Any, *, allowed_fields: frozenset[str]) -> None:
    if isinstance(value, dict) and set(value) - allowed_fields:
        raise ContractBlocked("payload-unknown-field")


def _validate_operation_payload(
    operation: str,
    result: dict[str, Any],
    *,
    paper_id: str = EXPECTED_PAPER_ID,
) -> str:
    field = PAYLOAD_FIELDS.get(operation)
    if field is None or field not in result:
        raise ContractBlocked("payload-shape")
    value = result[field]
    if operation == "read_fulltext":
        if not isinstance(value, str) or not value:
            raise ContractBlocked("payload-shape")
    elif operation in {"get_paper", "lookup_paper"}:
        if not isinstance(value, dict) or not isinstance(value.get("abstract"), str):
            raise ContractBlocked("payload-shape")
        _reject_unknown_fields(value, allowed_fields=STRUCTURED_PAYLOAD_FIELDS[operation])
        _validate_paper_identity(value, paper_id=paper_id)
    elif operation == "search_papers":
        if not isinstance(value, list) or not value:
            raise ContractBlocked("payload-shape")
        for item in value:
            _reject_unknown_fields(item, allowed_fields=STRUCTURED_PAYLOAD_FIELDS[operation])
            _validate_paper_identity(item, paper_id=paper_id)
            if not isinstance(item.get("snippet"), str):
                raise ContractBlocked("payload-shape")
    elif operation == "search_chunks":
        if not isinstance(value, list) or not value:
            raise ContractBlocked("payload-shape")
        for item in value:
            _reject_unknown_fields(item, allowed_fields=STRUCTURED_PAYLOAD_FIELDS[operation])
            if (
                not isinstance(item, dict)
                or item.get("paper_id") != paper_id
                or not isinstance(item.get("chunk_id"), str)
                or not isinstance(item.get("text"), str)
            ):
                raise ContractBlocked(
                    "paper-mismatch"
                    if isinstance(item, dict) and item.get("paper_id") != paper_id
                    else "payload-shape"
                )
    elif operation == "get_paper_citation":
        if not isinstance(value, dict) or type(value.get("year")) is not int:
            raise ContractBlocked("payload-shape")
        _reject_unknown_fields(value, allowed_fields=STRUCTURED_PAYLOAD_FIELDS[operation])
        _validate_paper_identity(value, paper_id=paper_id)
    elif operation in {"get_references", "get_citations"}:
        if not isinstance(value, list) or not value:
            raise ContractBlocked("payload-shape")
        for item in value:
            _reject_unknown_fields(item, allowed_fields=STRUCTURED_PAYLOAD_FIELDS[operation])
            if not isinstance(item, dict) or type(item.get("year")) is not int:
                raise ContractBlocked("payload-shape")
            _validate_paper_identity(item, paper_id=paper_id)
    else:
        raise ContractBlocked("operation-not-allowlisted")
    return value if isinstance(value, str) else canonical_json(value)


def _selected_payload(
    operation: str,
    result: dict[str, Any],
    *,
    paper_id: str = EXPECTED_PAPER_ID,
) -> str:
    return _validate_operation_payload(operation, result, paper_id=paper_id)


def _parse_fixture_time(name: str, value: Any) -> datetime:
    if not isinstance(value, str) or not value or len(value) > 64:
        raise ContractBlocked("freshness-invalid")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ContractBlocked("freshness-invalid") from exc
    if parsed.tzinfo is None:
        raise ContractBlocked("freshness-invalid")
    return parsed.astimezone(timezone.utc)


_SENSITIVE_MARKERS = ("token", "cookie", "bearer", "authorization", "api_key")
_URL_SCHEME = re.compile(r"https?://", re.IGNORECASE)
# A root may follow any non-path token; enumerating punctuation lets provider
# text hide a path behind a delimiter that the allowlist forgot to include.
_PATH_COMPONENT_CHARS = r'''[^\\/\s<>'"()\[\]{}]'''
_PATH_COMPONENT = rf"{_PATH_COMPONENT_CHARS}+"
# ``[^\W_]`` is the Unicode-aware word class with underscore removed, so an
# underscore or punctuation opens a fail-closed boundary while inline prose
# such as ``输入/输出`` is not mistaken for a root.
_PATH_ROOT_BOUNDARY = r"(?<![^\W_])"
_ABSOLUTE_PATH = re.compile(
    rf"{_PATH_ROOT_BOUNDARY}(?:"
    rf"/(?:{_PATH_COMPONENT}/)+{_PATH_COMPONENT}"
    rf"|/{_PATH_COMPONENT_CHARS}{{3,}}"
    rf"|[A-Za-z]:[\\/]{_PATH_COMPONENT}(?:[\\/]{_PATH_COMPONENT})*"
    rf"|\\\\{_PATH_COMPONENT}(?:\\{_PATH_COMPONENT})*"
    rf")"
)


def _assert_safe_provider_strings(
    value: Any,
    *,
    reason: str = "payload-not-sanitized",
) -> None:
    if isinstance(value, str):
        lowered = value.casefold()
        if any(marker in lowered for marker in _SENSITIVE_MARKERS):
            raise ContractBlocked(reason)
        if _URL_SCHEME.search(value) or _ABSOLUTE_PATH.search(value):
            raise ContractBlocked(reason)
    elif isinstance(value, dict):
        for nested in value.values():
            _assert_safe_provider_strings(nested, reason=reason)
    elif isinstance(value, list):
        for nested in value:
            _assert_safe_provider_strings(nested, reason=reason)


def _assert_safe_selected_payload(payload: str) -> None:
    _assert_safe_provider_strings(payload)


def normalize_for_fixture_contract(
    response: RpcResponse,
    *,
    operation: str,
    project_id: str = EXPECTED_PROJECT_ID,
    paper_id: str = EXPECTED_PAPER_ID,
    correlation_id: str = "corr-001",
    idempotency_key: str = "idem-001",
    arguments: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Test-local candidate normalizer; never imported by production code."""

    for name, value in (
        ("project", project_id),
        ("paper", paper_id),
        ("correlation", correlation_id),
        ("idempotency", idempotency_key),
    ):
        _validate_identifier(name, value)
    if response.status_code != 200:
        raise ContractBlocked(f"transport-{response.status_code}")
    result = _result(response)
    if operation not in READONLY_TOOLS:
        raise ContractBlocked("operation-not-allowlisted")
    for identity_field in ("project_id", "paper_id", "doi", "title"):
        _assert_safe_provider_strings(result.get(identity_field))
    _assert_safe_provider_strings(result.get("source"), reason="source-not-sanitized")
    _assert_safe_provider_strings(result.get("uncertainty"))
    if result.get("project_id") != project_id:
        raise ContractBlocked("project-mismatch")
    if result.get("paper_id") != paper_id:
        raise ContractBlocked("paper-mismatch")
    if result.get("doi") != EXPECTED_DOI or result.get("title") != EXPECTED_TITLE:
        raise ContractBlocked("paper-identity-mismatch")
    source = result.get("source")
    if not isinstance(source, str) or not source.strip():
        raise ContractBlocked("source-missing")
    source_folded = source.strip().casefold()
    if any(
        marker in source_folded
        for marker in (
            "token",
            "cookie",
            "bearer",
            "authorization",
            "://",
            "\\",
            "/",
        )
    ):
        raise ContractBlocked("source-not-sanitized")
    if source_folded not in {value.casefold() for value in ALLOWED_SOURCE_VALUES}:
        raise ContractBlocked("source-not-allowlisted")
    freshness = result.get("freshness")
    if not isinstance(freshness, dict):
        raise ContractBlocked("freshness-missing")
    if set(freshness) != {"retrieved_at", "expires_at"}:
        raise ContractBlocked("freshness-unknown-field")
    _assert_safe_provider_strings(freshness)
    retrieved_at = _parse_fixture_time("retrieved_at", freshness.get("retrieved_at"))
    expires_at = _parse_fixture_time("expires_at", freshness.get("expires_at"))
    fixture_now = _parse_fixture_time("fixture_now", FIXTURE_NOW_ISO)
    if retrieved_at > expires_at:
        raise ContractBlocked("freshness-invalid")
    if expires_at < fixture_now:
        raise ContractBlocked("freshness-expired")
    if not isinstance(result.get("uncertainty"), str) or not result["uncertainty"]:
        raise ContractBlocked("uncertainty-missing")

    remote_truncated = result.get("remote_truncated")
    remote_marker = result.get("truncated")
    if not isinstance(remote_truncated, bool) or remote_marker not in {"none", "remote"}:
        raise ContractBlocked("truncation-invalid")
    if (remote_marker == "remote") != remote_truncated:
        raise ContractBlocked("truncation-contradictory")

    payload = _selected_payload(operation, result, paper_id=paper_id)
    _assert_safe_selected_payload(payload)
    locally_truncated = len(payload) > MAX_PASSAGE_CHARS
    if locally_truncated:
        payload = payload[:MAX_PASSAGE_CHARS]
    truncation = (
        "both"
        if remote_truncated and locally_truncated
        else "remote"
        if remote_truncated
        else "local"
        if locally_truncated
        else "none"
    )

    result_without_hashes = {
        key: value for key, value in result.items() if key not in {"request_hash", "result_hash"}
    }
    request_identity = {
            "project_id": project_id,
            "paper_id": paper_id,
            "operation": operation,
            "arguments": {**(arguments or {})},
    }
    if len(canonical_json(request_identity)) > MAX_ARGUMENT_JSON_CHARS:
        raise ContractBlocked("request-too-large")
    expected_request_hash = canonical_sha256(request_identity)
    if result.get("request_hash") != expected_request_hash:
        raise ContractBlocked("request-hash-mismatch")
    if len(canonical_json(result_without_hashes)) > MAX_RESULT_JSON_CHARS:
        raise ContractBlocked("result-too-large")
    expected_result_hash = canonical_sha256(result_without_hashes)
    if result.get("result_hash") != expected_result_hash:
        raise ContractBlocked("result-hash-mismatch")

    candidate = {
        "artifact_id": canonical_sha256(
            {
                "project_id": project_id,
                "paper_id": paper_id,
                "request_hash": expected_request_hash,
                "result_hash": expected_result_hash,
            }
        ),
        "project_id": project_id,
        "paper_id": paper_id,
        "doi": result["doi"],
        "title": result["title"],
        "operation": operation,
        "correlation_id": correlation_id,
        "idempotency_key": idempotency_key,
        "request_hash": expected_request_hash,
        "result_hash": expected_result_hash,
        "bounded_passage_or_citation": payload,
        "truncated": truncation,
        "source": result["source"],
        "freshness": {
            "retrieved_at": freshness["retrieved_at"],
            "expires_at": freshness["expires_at"],
        },
        "uncertainty": result["uncertainty"],
        "content_is_untrusted": True,
        "status": "candidate",
    }
    if any(key in candidate for key in ("task", "run", "review", "final_verdict")):
        raise ContractBlocked("second-authority-field")
    return candidate


class CandidateStore:
    """Tiny in-test store proving exact replay does not duplicate artifacts."""

    def __init__(self) -> None:
        self.artifacts: dict[str, dict[str, Any]] = {}

    def ingest(self, candidate: dict[str, Any]) -> dict[str, Any]:
        key = candidate["idempotency_key"]
        existing = self.artifacts.get(key)
        if existing is None:
            self.artifacts[key] = candidate
            return candidate
        if (
            existing["request_hash"],
            existing["result_hash"],
        ) != (
            candidate["request_hash"],
            candidate["result_hash"],
        ):
            raise ContractBlocked("idempotency-conflict")
        return existing


def test_initialize_and_tools_list_are_jsonrpc_and_explicitly_read_only() -> None:
    server = FakePolarisReadonlyMcp()
    initialized = server.handle({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
    assert initialized.status_code == 200
    assert initialized.body["result"]["serverInfo"]["name"] == "polaris-fixture"

    listed = server.handle({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
    names = [entry["name"] for entry in listed.body["result"]["tools"]]
    assert names == list(READONLY_TOOLS)
    assert not set(names) & set(HIDDEN_TOOLS)


@pytest.mark.parametrize("operation", READONLY_TOOLS)
def test_all_eight_read_only_tools_produce_bounded_candidate(operation: str) -> None:
    server = FakePolarisReadonlyMcp()
    response = _call(server, operation, idempotency_key=f"idem-{operation}")
    candidate = normalize_for_fixture_contract(
        response,
        operation=operation,
        idempotency_key=f"idem-{operation}",
    )
    assert candidate["status"] == "candidate"
    assert candidate["project_id"] == EXPECTED_PROJECT_ID
    assert candidate["paper_id"] == EXPECTED_PAPER_ID
    assert candidate["bounded_passage_or_citation"]
    assert len(candidate["bounded_passage_or_citation"]) <= MAX_PASSAGE_CHARS
    assert candidate["truncated"] == "none"
    assert candidate["request_hash"].startswith("sha256:")
    assert candidate["result_hash"].startswith("sha256:")


@pytest.mark.parametrize("project_id", ["", "another-project"])
def test_missing_or_cross_project_request_fails_closed(project_id: str) -> None:
    response = _call(FakePolarisReadonlyMcp(), "read_fulltext", project_id=project_id)
    assert response.status_code == 200
    assert _error_code(response) == -32020


def test_path_derived_project_identity_fails_closed() -> None:
    response = _call(FakePolarisReadonlyMcp(), "read_fulltext", project_id="vault\\paperlab-project-001")
    assert _error_code(response) == -32020


def test_cross_project_response_is_not_accepted() -> None:
    server = FakePolarisReadonlyMcp(mode="wrong-project-result")
    response = _call(server, "read_fulltext")
    with pytest.raises(ContractBlocked, match="project-mismatch"):
        normalize_for_fixture_contract(response, operation="read_fulltext")


def test_unknown_write_and_hidden_tools_are_rejected_even_when_advertised() -> None:
    server = FakePolarisReadonlyMcp(advertised_tools=READONLY_TOOLS + HIDDEN_TOOLS)
    listed = server.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}})
    names = {entry["name"] for entry in listed.body["result"]["tools"]}
    assert set(HIDDEN_TOOLS) <= names
    for operation in (*HIDDEN_TOOLS, "unknown_tool"):
        response = _call(server, operation)
        assert _error_code(response) == -32010


def test_request_and_result_hashes_are_canonical_and_detect_tampering() -> None:
    server = FakePolarisReadonlyMcp()
    response = _call(server, "read_fulltext", arguments={"query": "stable"})
    candidate = normalize_for_fixture_contract(
        response,
        operation="read_fulltext",
        arguments={"query": "stable"},
    )
    assert candidate["request_hash"] == canonical_sha256(
        {
            "project_id": EXPECTED_PROJECT_ID,
            "paper_id": EXPECTED_PAPER_ID,
            "operation": "read_fulltext",
            "arguments": {"query": "stable"},
        }
    )

    body = json.loads(canonical_json(response.body))
    body["result"]["passage"] = "tampered"
    with pytest.raises(ContractBlocked, match="result-hash-mismatch"):
        normalize_for_fixture_contract(
            RpcResponse(status_code=200, body=body),
            operation="read_fulltext",
            arguments={"query": "stable"},
        )


def test_passage_bound_reports_none_local_remote_and_both() -> None:
    cases = (
        ("normal", "none"),
        ("local-truncated", "local"),
        ("remote-truncated", "remote"),
        ("both-truncated", "both"),
    )
    for mode, expected in cases:
        server = FakePolarisReadonlyMcp(mode=mode)
        response = _call(server, "read_fulltext", idempotency_key=f"idem-{mode}")
        candidate = normalize_for_fixture_contract(
            response,
            operation="read_fulltext",
            idempotency_key=f"idem-{mode}",
        )
        assert candidate["truncated"] == expected
        assert len(candidate["bounded_passage_or_citation"]) <= MAX_PASSAGE_CHARS


def test_missing_or_contradictory_truncation_is_blocked() -> None:
    malformed = _call(FakePolarisReadonlyMcp(mode="malformed"), "read_fulltext")
    with pytest.raises(ContractBlocked, match="truncation-invalid"):
        normalize_for_fixture_contract(malformed, operation="read_fulltext")
    contradictory = _call(FakePolarisReadonlyMcp(mode="contradictory-truncation"), "read_fulltext")
    with pytest.raises(ContractBlocked, match="truncation-contradictory"):
        normalize_for_fixture_contract(contradictory, operation="read_fulltext")


@pytest.mark.parametrize("mode", ["expired", "invalid-time"])
def test_invalid_or_expired_freshness_is_blocked(mode: str) -> None:
    response = _call(FakePolarisReadonlyMcp(mode=mode), "read_fulltext")
    expected = "freshness-expired" if mode == "expired" else "freshness-invalid"
    with pytest.raises(ContractBlocked, match=expected):
        normalize_for_fixture_contract(response, operation="read_fulltext")


@pytest.mark.parametrize("operation", READONLY_TOOLS)
def test_each_operation_requires_its_declared_payload_shape(operation: str) -> None:
    response = _call(FakePolarisReadonlyMcp(mode="wrong-shape"), operation)
    with pytest.raises(ContractBlocked, match="payload-shape"):
        normalize_for_fixture_contract(response, operation=operation)


@pytest.mark.parametrize("operation", STRUCTURED_OPERATIONS)
@pytest.mark.parametrize("mode", ["payload-unknown-field", "payload-sensitive-fields"])
def test_structured_payload_unknown_or_sensitive_fields_are_blocked(
    operation: str,
    mode: str,
) -> None:
    response = _call(FakePolarisReadonlyMcp(mode=mode), operation)
    with pytest.raises(ContractBlocked, match="payload-unknown-field"):
        normalize_for_fixture_contract(response, operation=operation)


def test_sensitive_content_in_allowed_paper_abstract_is_blocked() -> None:
    response = _call(
        FakePolarisReadonlyMcp(mode="payload-sensitive-allowed-field"),
        "get_paper",
    )
    with pytest.raises(ContractBlocked, match="payload-not-sanitized"):
        normalize_for_fixture_contract(response, operation="get_paper")


def test_unknown_freshness_fields_are_blocked_before_candidate_projection() -> None:
    response = _call(
        FakePolarisReadonlyMcp(mode="freshness-unknown-field"),
        "read_fulltext",
    )
    with pytest.raises(ContractBlocked, match="freshness-unknown-field"):
        normalize_for_fixture_contract(response, operation="read_fulltext")


def test_oversized_arguments_are_rejected_before_source_result() -> None:
    server = FakePolarisReadonlyMcp()
    response = _call(server, "search_papers", arguments={"query": "x" * 4_000})
    assert _error_code(response) == -32023
    assert server.call_count == 0


def test_oversized_complete_result_is_rejected_before_result_hash_acceptance() -> None:
    response = _call(FakePolarisReadonlyMcp(mode="oversized-result"), "read_fulltext")
    with pytest.raises(ContractBlocked, match="result-too-large"):
        normalize_for_fixture_contract(response, operation="read_fulltext")


@pytest.mark.parametrize("field", ["project_id", "paper_id", "correlation_id", "idempotency_key"])
def test_normalizer_rejects_oversized_identifiers(field: str) -> None:
    response = _call(FakePolarisReadonlyMcp(), "read_fulltext")
    kwargs = {field: "i" * 10_000}
    expected_name = {
        "project_id": "project",
        "paper_id": "paper",
        "correlation_id": "correlation",
        "idempotency_key": "idempotency",
    }[field]
    with pytest.raises(ContractBlocked, match=f"{expected_name}-identifier-invalid"):
        normalize_for_fixture_contract(response, operation="read_fulltext", **kwargs)


def test_exact_replay_is_bounded_idempotent_and_does_not_duplicate_candidate() -> None:
    server = FakePolarisReadonlyMcp()
    store = CandidateStore()
    first = _call(server, "read_fulltext", idempotency_key="idem-replay")
    second = _call(server, "read_fulltext", idempotency_key="idem-replay", request_id=2)
    assert _result(first) == _result(second)
    store.ingest(normalize_for_fixture_contract(first, operation="read_fulltext", idempotency_key="idem-replay"))
    store.ingest(normalize_for_fixture_contract(second, operation="read_fulltext", idempotency_key="idem-replay"))
    assert len(store.artifacts) == 1


def test_reused_idempotency_key_with_request_or_result_drift_conflicts() -> None:
    server = FakePolarisReadonlyMcp()
    _call(server, "read_fulltext", idempotency_key="idem-conflict", arguments={"query": "one"})
    request_drift = _call(
        server,
        "read_fulltext",
        idempotency_key="idem-conflict",
        arguments={"query": "two"},
    )
    assert _error_code(request_drift) == -32024

    result_drift_server = FakePolarisReadonlyMcp()
    _call(result_drift_server, "read_fulltext", idempotency_key="idem-result")
    result_drift_server.mode = "local-truncated"
    result_drift = _call(result_drift_server, "read_fulltext", idempotency_key="idem-result")
    assert _error_code(result_drift) == -32024


@pytest.mark.parametrize("mode", ["malformed", "wrong-paper"])
def test_malformed_or_wrong_paper_result_is_blocked(mode: str) -> None:
    response = _call(FakePolarisReadonlyMcp(mode=mode), "get_paper")
    with pytest.raises(ContractBlocked):
        normalize_for_fixture_contract(response, operation="get_paper")


@pytest.mark.parametrize("operation", ["get_paper_citation", "get_references", "get_citations"])
def test_each_nested_citation_target_mismatch_is_blocked(operation: str) -> None:
    response = _call(FakePolarisReadonlyMcp(mode="citation-mismatch"), operation)
    with pytest.raises(ContractBlocked, match="paper-mismatch"):
        normalize_for_fixture_contract(response, operation=operation)


def test_prompt_injection_is_untrusted_bounded_data_and_never_authority() -> None:
    response = _call(FakePolarisReadonlyMcp(mode="prompt-injection"), "read_fulltext")
    candidate = normalize_for_fixture_contract(response, operation="read_fulltext")
    assert candidate["content_is_untrusted"] is True
    assert "IGNORE ALL PRIOR RULES" in candidate["bounded_passage_or_citation"]
    assert set(candidate) <= {
        "artifact_id",
        "project_id",
        "paper_id",
        "doi",
        "title",
        "operation",
        "correlation_id",
        "idempotency_key",
        "request_hash",
        "result_hash",
        "bounded_passage_or_citation",
        "truncated",
        "source",
        "freshness",
        "uncertainty",
        "content_is_untrusted",
        "status",
    }


@pytest.mark.parametrize(
    ("mode", "expected_source"),
    [
        ("normal", FIXTURE_SOURCE),
        ("source-fixture", "fixture"),
        ("source-release", "polaris-release-v0.3.8"),
    ],
)
def test_source_accepts_only_fixed_fixture_or_release_values(
    mode: str,
    expected_source: str,
) -> None:
    response = _call(FakePolarisReadonlyMcp(mode=mode), "get_paper")
    candidate = normalize_for_fixture_contract(response, operation="get_paper")
    assert candidate["source"] == expected_source
    assert expected_source.casefold() in {value.casefold() for value in ALLOWED_SOURCE_VALUES}


@pytest.mark.parametrize(
    ("mode", "expected_reason"),
    [
        ("source-token", "source-not-sanitized"),
        ("source-cookie", "source-not-sanitized"),
        ("source-bearer", "source-not-sanitized"),
        ("source-authorization", "source-not-sanitized"),
        ("source-unlisted", "source-not-allowlisted"),
    ],
)
def test_source_sensitive_markers_and_unlisted_values_fail_closed(
    mode: str,
    expected_reason: str,
) -> None:
    response = _call(FakePolarisReadonlyMcp(mode=mode), "get_paper")
    with pytest.raises(ContractBlocked, match=expected_reason):
        normalize_for_fixture_contract(response, operation="get_paper")


def test_adversarial_passage_serialization_is_rejected_before_truncation() -> None:
    response = _call(FakePolarisReadonlyMcp(mode="adversarial-content"), "read_fulltext")
    with pytest.raises(ContractBlocked, match="payload-not-sanitized"):
        normalize_for_fixture_contract(response, operation="read_fulltext")


@pytest.mark.parametrize(
    "passage",
    [
        "reference,/synthetic-user/private.txt",
        "reference>/etc/passwd",
        "reference_/synthetic-user/private.txt",
        r"reference,C:\synthetic-user\private.txt",
        r"reference_C:\synthetic-user\private.txt",
        "reference,C:/synthetic-user/private.txt",
    ],
)
def test_rehashed_absolute_paths_after_arbitrary_punctuation_are_blocked(
    passage: str,
) -> None:
    response = _with_rehashed_passage(
        _call(FakePolarisReadonlyMcp(), "read_fulltext"),
        passage,
    )
    result = _result(response)
    expected_result_hash = canonical_sha256(
        {
            key: value
            for key, value in result.items()
            if key not in {"request_hash", "result_hash"}
        }
    )
    assert result["result_hash"] == expected_result_hash
    with pytest.raises(ContractBlocked, match="payload-not-sanitized"):
        normalize_for_fixture_contract(response, operation="read_fulltext")


@pytest.mark.parametrize(
    "passage",
    [
        "DOI 10.5555/paperlab.001 identifies the cited paper.",
        "Ordinary paper text compares input/output and reports a 1/2 ratio.",
        "普通论文文本可以讨论输入/输出，而不包含文件路径。",
    ],
)
def test_doi_and_ordinary_paper_text_are_not_misclassified_as_paths(
    passage: str,
) -> None:
    response = _with_rehashed_passage(
        _call(FakePolarisReadonlyMcp(), "read_fulltext"),
        passage,
    )
    candidate = normalize_for_fixture_contract(response, operation="read_fulltext")
    assert candidate["bounded_passage_or_citation"] == passage


@pytest.mark.parametrize("status_code", [401, 403])
def test_auth_and_revoke_are_blocked_without_fallback(status_code: int) -> None:
    server = FakePolarisReadonlyMcp()
    server.set_auth_status(status_code)
    response = _call(server, "search_papers")
    assert response.status_code == status_code
    with pytest.raises(ContractBlocked, match=f"transport-{status_code}"):
        normalize_for_fixture_contract(response, operation="search_papers")

    revoked = FakePolarisReadonlyMcp()
    revoked.revoke()
    response = _call(revoked, "search_papers")
    assert response.status_code == 401
    with pytest.raises(ContractBlocked, match="transport-401"):
        normalize_for_fixture_contract(response, operation="search_papers")


def test_outage_is_bounded_blocked_and_does_not_create_candidate() -> None:
    server = FakePolarisReadonlyMcp()
    server.set_outage()
    response = _call(server, "search_chunks")
    assert response.status_code == 503
    with pytest.raises(ContractBlocked, match="transport-503"):
        normalize_for_fixture_contract(response, operation="search_chunks")


def test_no_second_authority_or_private_payload_is_emitted() -> None:
    candidate = normalize_for_fixture_contract(
        _call(FakePolarisReadonlyMcp(), "get_paper"),
        operation="get_paper",
    )
    serialized = canonical_json(candidate)
    assert candidate["status"] == "candidate"
    assert not any(key in candidate for key in ("task", "run", "review", "final_verdict"))
    assert not any(secret in serialized for secret in ("https://", "http://", "Authorization", "Bearer", "C:\\", "/Users/"))
    assert "Vault" not in serialized
    assert "fulltext" not in serialized


def test_fixture_has_no_network_process_or_credential_side_effect_imports() -> None:
    source = inspect.getsource(FakePolarisReadonlyMcp)
    for forbidden in (
        "urlopen",
        "import requests",
        "from requests",
        "urllib",
        "subprocess",
        "socket",
        "os.environ",
    ):
        assert forbidden not in source
