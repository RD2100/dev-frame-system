"""Focused tests for the pure PaperLab source-result contract."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator, FormatChecker

from control_plane.paperlab_adapter_contract import (
    AdapterContractError,
    MAX_ARGUMENT_JSON_CHARS,
    PUBLIC_TO_RAW,
    canonical_json,
    canonical_sha256,
    normalize_dsh_mcp_result,
)
from fixtures.polaris_compatibility_probe import (
    FakePolarisDshReadonlyProfile,
    PAPER_DOI,
    PROVIDER_PAPER_ID,
    expected_binding,
)


NOW = "2026-08-27T12:00:00Z"


def _subject(public_name: str) -> dict[str, str]:
    raw_name = PUBLIC_TO_RAW[public_name]
    if raw_name in {"search_papers", "search_chunks"}:
        return {"query": "attention"}
    if raw_name == "lookup_paper":
        return {"doi": PAPER_DOI}
    if raw_name in {"get_references", "get_citations"}:
        return {"paper_ref": PROVIDER_PAPER_ID}
    return {"provider_paper_id": PROVIDER_PAPER_ID}


def _result(public_name: str, *, mode: str = "normal") -> dict[str, Any]:
    response = FakePolarisDshReadonlyProfile(mode=mode).invoke_public(
        public_name,
        subject=_subject(public_name),
        arguments={"page": 1},
        correlation_id="corr-contract-001",
        idempotency_key=f"idem-{public_name}",
    )
    assert response.status_code == 200
    result = response.body.get("result")
    assert isinstance(result, dict)
    return result


def _normalize(public_name: str, *, mode: str = "normal"):
    return normalize_dsh_mcp_result(
        public_operation=public_name,
        binding=expected_binding(),
        subject=_subject(public_name),
        arguments={"page": 1},
        response=_result(public_name, mode=mode),
        correlation_id="corr-contract-001",
        idempotency_key=f"idem-{public_name}",
        retrieved_at=NOW,
    )


@pytest.mark.parametrize("public_name", tuple(PUBLIC_TO_RAW))
def test_all_eight_operations_normalize_to_non_authoritative_candidates(public_name: str) -> None:
    normalized = _normalize(public_name)

    assert normalized.artifact["kind"] == "ExternalSourceArtifact"
    assert normalized.artifact["status"] == "candidate"
    assert normalized.artifact["local_project_id"] == expected_binding()["local_project_id"]
    assert normalized.artifact["operation"] == PUBLIC_TO_RAW[public_name]
    assert normalized.artifact["content_is_untrusted"] is True
    assert normalized.artifact["truncated"] == "unknown"
    assert normalized.candidate == {
        "contract_version": "paperlab-external-evidence-v1",
        "candidate_id": normalized.artifact["artifact_id"],
        "kind": "EvidenceCandidate",
        "status": "candidate",
        "artifact_id": normalized.artifact["artifact_id"],
        "local_project_id": expected_binding()["local_project_id"],
        "promotion": "requires_devframe_review",
        "supports": "unreviewed",
    }


def test_output_matches_public_json_schema_and_hides_credential_identity() -> None:
    normalized = _normalize("mcp__polaris__get_paper")
    schema_path = Path(__file__).parents[1] / "control_plane" / "paperlab_adapter_contract.schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))

    Draft202012Validator(schema, format_checker=FormatChecker()).validate(normalized.to_dict())
    encoded = json.dumps(normalized.to_dict(), ensure_ascii=False, sort_keys=True)
    assert "credential_ref" not in encoded
    assert "authorization" not in encoded.casefold()
    assert "https://" not in encoded
    assert "final_verdict" not in encoded
    assert "task" not in normalized.artifact
    assert "run" not in normalized.artifact


def test_text_only_dsh_value_is_supported_when_it_matches_structured_content() -> None:
    response = _result("mcp__polaris__search_papers")
    response.pop("structuredContent")

    normalized = normalize_dsh_mcp_result(
        public_operation="mcp__polaris__search_papers",
        binding=expected_binding(),
        subject={"query": "attention"},
        arguments={"page": 1},
        response=response,
        correlation_id="corr-contract-001",
        idempotency_key="idem-text-only",
        retrieved_at=NOW,
    )

    assert normalized.artifact["operation"] == "search_papers"


def test_remote_truncation_projects_to_explicit_combined_state() -> None:
    normalized = _normalize("mcp__polaris__read_fulltext", mode="remote-truncated")

    assert normalized.artifact["remote_truncated"] is True
    assert normalized.artifact["truncated"] == "remote"


@pytest.mark.parametrize(
    ("mode", "code"),
    [
        ("malformed", "malformed_result"),
        ("error", "provider_error"),
        ("unknown-field", "unknown_shape"),
        ("missing-payload", "unknown_shape"),
        ("large-passage", "passage_too_large"),
    ],
)
def test_provider_failure_and_unbounded_shapes_fail_closed(mode: str, code: str) -> None:
    if mode == "large-passage":
        response = _result("mcp__polaris__read_fulltext")
        structured = response["structuredContent"]
        structured["payload"]["sections"][0]["text"] = "L" * 4_001
        structured["result_hash"] = canonical_sha256(
            {
                "contract_version": "paperlab-polaris-result-v1",
                "operation": "read_fulltext",
                "payload": structured["payload"],
                "remote_freshness": structured["remote_freshness"],
                "remote_truncated": structured["remote_truncated"],
                "provenance": structured["provenance"],
            }
        )
        response["content"][0]["text"] = canonical_json(structured)
        with pytest.raises(AdapterContractError) as exc_info:
            normalize_dsh_mcp_result(
                public_operation="mcp__polaris__read_fulltext",
                binding=expected_binding(),
                subject={"provider_paper_id": PROVIDER_PAPER_ID},
                arguments={"page": 1},
                response=response,
                correlation_id="corr-contract-001",
                idempotency_key="idem-large-passage",
                retrieved_at=NOW,
            )
        assert exc_info.value.code == code
        return

    with pytest.raises(AdapterContractError) as exc_info:
        _normalize("mcp__polaris__get_paper", mode=mode)

    assert exc_info.value.code == code


def test_unknown_public_operation_is_rejected_before_result_parsing() -> None:
    with pytest.raises(AdapterContractError, match="allowlist") as exc_info:
        normalize_dsh_mcp_result(
            public_operation="mcp__polaris__list_projects",
            binding=expected_binding(),
            subject={"query": "attention"},
            arguments={},
            response={},
            correlation_id="corr-contract-001",
            idempotency_key="idem-unknown",
            retrieved_at=NOW,
        )
    assert exc_info.value.code == "operation_not_allowed"


@pytest.mark.parametrize(
    "mutator,code",
    [
        (lambda value: value["content"].__setitem__(0, {"type": "text", "text": "not-json"}), "malformed_result"),
        (lambda value: value["structuredContent"].__setitem__("future", "field"), "result_mismatch"),
    ],
)
def test_malformed_or_disagreeing_content_is_rejected(mutator, code: str) -> None:
    response = _result("mcp__polaris__get_paper")
    mutator(response)

    with pytest.raises(AdapterContractError) as exc_info:
        normalize_dsh_mcp_result(
            public_operation="mcp__polaris__get_paper",
            binding=expected_binding(),
            subject={"provider_paper_id": PROVIDER_PAPER_ID},
            arguments={"page": 1},
            response=response,
            correlation_id="corr-contract-001",
            idempotency_key="idem-mutated",
            retrieved_at=NOW,
        )
    assert exc_info.value.code == code


def test_request_hash_and_result_hash_are_recomputed_not_trusted() -> None:
    response = _result("mcp__polaris__get_paper")
    structured = response["structuredContent"]
    structured["request_hash"] = "sha256:" + "0" * 64
    response["content"][0]["text"] = canonical_json(structured)

    with pytest.raises(AdapterContractError) as exc_info:
        normalize_dsh_mcp_result(
            public_operation="mcp__polaris__get_paper",
            binding=expected_binding(),
            subject={"provider_paper_id": PROVIDER_PAPER_ID},
            arguments={"page": 1},
            response=response,
            correlation_id="corr-contract-001",
            idempotency_key="idem-hash-mismatch",
            retrieved_at=NOW,
        )
    assert exc_info.value.code == "request_hash_mismatch"


def test_result_hash_covers_payload_freshness_truncation_and_provenance() -> None:
    response = _result("mcp__polaris__get_paper")
    structured = response["structuredContent"]
    structured["provenance"]["page"] = 2
    response["content"][0]["text"] = canonical_json(structured)

    with pytest.raises(AdapterContractError) as exc_info:
        normalize_dsh_mcp_result(
            public_operation="mcp__polaris__get_paper",
            binding=expected_binding(),
            subject={"provider_paper_id": PROVIDER_PAPER_ID},
            arguments={"page": 1},
            response=response,
            correlation_id="corr-contract-001",
            idempotency_key="idem-result-mismatch",
            retrieved_at=NOW,
        )
    assert exc_info.value.code == "result_hash_mismatch"


def test_known_paper_identity_mismatch_is_rejected_even_with_a_recomputed_hash() -> None:
    response = _result("mcp__polaris__get_paper")
    structured = response["structuredContent"]
    structured["payload"]["paper"]["provider_paper_id"] = "different-paper"
    structured["result_hash"] = canonical_sha256(
        {
            "contract_version": "paperlab-polaris-result-v1",
            "operation": "get_paper",
            "payload": structured["payload"],
            "remote_freshness": structured["remote_freshness"],
            "remote_truncated": structured["remote_truncated"],
            "provenance": structured["provenance"],
        }
    )
    response["content"][0]["text"] = canonical_json(structured)

    with pytest.raises(AdapterContractError) as exc_info:
        normalize_dsh_mcp_result(
            public_operation="mcp__polaris__get_paper",
            binding=expected_binding(),
            subject={"provider_paper_id": PROVIDER_PAPER_ID},
            arguments={"page": 1},
            response=response,
            correlation_id="corr-contract-001",
            idempotency_key="idem-paper-mismatch",
            retrieved_at=NOW,
        )
    assert exc_info.value.code == "paper_mismatch"


@pytest.mark.parametrize(
    ("field", "value", "code"),
    [
        ("remote_freshness", "invented", "freshness_invalid"),
        ("remote_truncated", "maybe", "truncation_invalid"),
        ("provenance", {"source_release": "pinned", "endpoint": "http://private"}, "provenance_invalid"),
    ],
)
def test_uncertain_or_sensitive_provider_metadata_is_not_fabricated(field: str, value: Any, code: str) -> None:
    response = _result("mcp__polaris__get_paper")
    structured = response["structuredContent"]
    structured[field] = value
    response["content"][0]["text"] = canonical_json(structured)

    with pytest.raises(AdapterContractError) as exc_info:
        normalize_dsh_mcp_result(
            public_operation="mcp__polaris__get_paper",
            binding=expected_binding(),
            subject={"provider_paper_id": PROVIDER_PAPER_ID},
            arguments={"page": 1},
            response=response,
            correlation_id="corr-contract-001",
            idempotency_key=f"idem-{field}",
            retrieved_at=NOW,
        )
    assert exc_info.value.code == code


def test_allowed_provenance_fields_still_reject_endpoint_urls() -> None:
    response = _result("mcp__polaris__get_paper")
    structured = response["structuredContent"]
    structured["provenance"]["source_kind"] = "https://private.example"
    response["content"][0]["text"] = canonical_json(structured)

    with pytest.raises(AdapterContractError) as exc_info:
        normalize_dsh_mcp_result(
            public_operation="mcp__polaris__get_paper",
            binding=expected_binding(),
            subject={"provider_paper_id": PROVIDER_PAPER_ID},
            arguments={"page": 1},
            response=response,
            correlation_id="corr-contract-001",
            idempotency_key="idem-url-metadata",
            retrieved_at=NOW,
        )
    assert exc_info.value.code == "sensitive_metadata"


@pytest.mark.parametrize("kind", ("items", "depth"))
def test_nested_provider_payload_limits_fail_closed(kind: str) -> None:
    response = _result("mcp__polaris__read_fulltext")
    structured = response["structuredContent"]
    if kind == "items":
        structured["payload"]["sections"] = [{"text": "bounded"}] * 257
        expected_code = "result_too_large"
    else:
        nested: dict[str, Any] = {"leaf": "bounded"}
        for _ in range(18):
            nested = {"nested": nested}
        structured["payload"]["sections"] = [nested]
        expected_code = "result_too_deep"
    structured["result_hash"] = canonical_sha256(
        {
            "contract_version": "paperlab-polaris-result-v1",
            "operation": "read_fulltext",
            "payload": structured["payload"],
            "remote_freshness": structured["remote_freshness"],
            "remote_truncated": structured["remote_truncated"],
            "provenance": structured["provenance"],
        }
    )
    response["content"][0]["text"] = canonical_json(structured)

    with pytest.raises(AdapterContractError) as exc_info:
        normalize_dsh_mcp_result(
            public_operation="mcp__polaris__read_fulltext",
            binding=expected_binding(),
            subject={"provider_paper_id": PROVIDER_PAPER_ID},
            arguments={"page": 1},
            response=response,
            correlation_id="corr-contract-001",
            idempotency_key=f"idem-nested-{kind}",
            retrieved_at=NOW,
        )
    assert exc_info.value.code == expected_code


def test_canonical_json_rejects_non_json_numbers() -> None:
    with pytest.raises(AdapterContractError) as exc_info:
        canonical_json({"not_json": float("nan")})
    assert exc_info.value.code == "non_json"


def test_project_and_profile_binding_fail_closed_before_provider_result() -> None:
    binding = expected_binding()
    binding["profile"] = "dsh-full-v1"

    with pytest.raises(AdapterContractError) as exc_info:
        normalize_dsh_mcp_result(
            public_operation="mcp__polaris__get_paper",
            binding=binding,
            subject={"provider_paper_id": PROVIDER_PAPER_ID},
            arguments={},
            response={},
            correlation_id="corr-contract-001",
            idempotency_key="idem-binding",
            retrieved_at=NOW,
        )
    assert exc_info.value.code == "profile_invalid"


@pytest.mark.parametrize(
    ("subject", "code"),
    [
        ({}, "subject_invalid"),
        ({"provider_paper_id": "C:\\private\\paper"}, "subject_invalid"),
        ({"provider_paper_id": "https://private/paper"}, "subject_invalid"),
    ],
)
def test_subject_identity_is_typed_and_pathless(subject: dict[str, str], code: str) -> None:
    with pytest.raises(AdapterContractError) as exc_info:
        normalize_dsh_mcp_result(
            public_operation="mcp__polaris__get_paper",
            binding=expected_binding(),
            subject=subject,
            arguments={},
            response={},
            correlation_id="corr-contract-001",
            idempotency_key="idem-subject",
            retrieved_at=NOW,
        )
    assert exc_info.value.code == code


@pytest.mark.parametrize("field", ("correlation_id", "idempotency_key", "retrieved_at"))
def test_audit_metadata_is_bounded_and_timestamped(field: str) -> None:
    kwargs: dict[str, Any] = {
        "public_operation": "mcp__polaris__get_paper",
        "binding": expected_binding(),
        "subject": {"provider_paper_id": PROVIDER_PAPER_ID},
        "arguments": {},
        "response": {},
        "correlation_id": "corr-contract-001",
        "idempotency_key": "idem-audit",
        "retrieved_at": NOW,
    }
    kwargs[field] = "x" * (MAX_ARGUMENT_JSON_CHARS + 1) if field != "retrieved_at" else "not-a-date"

    with pytest.raises(AdapterContractError) as exc_info:
        normalize_dsh_mcp_result(**kwargs)
    assert exc_info.value.code in {"audit_metadata_invalid", "timestamp_invalid"}


def test_candidate_id_is_deterministic_and_binding_fingerprint_is_not_credential() -> None:
    first = _normalize("mcp__polaris__search_papers")
    second = _normalize("mcp__polaris__search_papers")

    assert first.artifact["artifact_id"] == second.artifact["artifact_id"]
    assert first.artifact["binding_fingerprint"].startswith("sha256:")
    assert first.artifact["binding_fingerprint"] != expected_binding()["credential_ref"]
