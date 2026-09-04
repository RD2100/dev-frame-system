"""Pure PaperLab/Polaris result contract at the DSH MCP boundary.

This module deliberately owns no transport or persistence.  It validates one
already received DSH MCP ``ToolExecutionResult.value`` and returns bounded,
non-authoritative projections that a later DevFrame evidence path may review.
The remote service never becomes a project, task, run, review, gate, or
verdict authority.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime
import hashlib
import json
import re
from typing import Any, Mapping


CONTRACT_VERSION = "paperlab-external-evidence-v1"
REQUEST_CONTRACT_VERSION = "paperlab-polaris-request-v1"
RESULT_CONTRACT_VERSION = "paperlab-polaris-result-v1"
READONLY_PROFILE = "dsh-readonly-v1"
SERVER_ALIAS = "polaris"
MAX_IDENTIFIER_CHARS = 128
MAX_ARGUMENT_JSON_CHARS = 4_000
MAX_PASSAGE_CHARS = 4_000
MAX_RESULT_JSON_CHARS = 16_000
MAX_COLLECTION_ITEMS = 256
MAX_NESTING_DEPTH = 16

PUBLIC_TO_RAW: dict[str, str] = {
    "mcp__polaris__search_papers": "search_papers",
    "mcp__polaris__search_chunks": "search_chunks",
    "mcp__polaris__get_paper": "get_paper",
    "mcp__polaris__lookup_paper": "lookup_paper",
    "mcp__polaris__read_fulltext": "read_fulltext",
    "mcp__polaris__get_paper_citation": "get_paper_citation",
    "mcp__polaris__get_references": "get_references",
    "mcp__polaris__get_citations": "get_citations",
}

PAYLOAD_KEYS: dict[str, str] = {
    "search_papers": "results",
    "search_chunks": "chunks",
    "get_paper": "paper",
    "lookup_paper": "paper",
    "read_fulltext": "sections",
    "get_paper_citation": "citation",
    "get_references": "references",
    "get_citations": "citations",
}
_LIST_PAYLOAD_OPERATIONS = frozenset(
    {"search_papers", "search_chunks", "read_fulltext", "get_references", "get_citations"}
)
_DISCOVERY_OPERATIONS = frozenset({"search_papers", "search_chunks"})
_KNOWN_PAPER_OPERATIONS = frozenset(
    {"get_paper", "read_fulltext", "get_paper_citation"}
)
_GRAPH_OPERATIONS = frozenset({"get_references", "get_citations"})
_BINDING_FIELDS = (
    "local_project_id",
    "remote_project_id",
    "credential_ref",
    "release_commit",
    "profile",
    "server_alias",
)
_STRUCTURED_FIELDS = frozenset(
    {
        "contract_version",
        "operation",
        "payload",
        "remote_freshness",
        "remote_truncated",
        "provenance",
        "binding",
        "content_is_untrusted",
        "request_hash",
        "result_hash",
    }
)
_PROVENANCE_FIELDS = frozenset(
    {
        "source_release",
        "query",
        "provider_paper_id",
        "paper_ref",
        "doi",
        "page",
        "sequence",
        "source_kind",
    }
)
_FRESHNESS_VALUES = frozenset({"unknown", "current", "stale", "historical"})
_SECRET_KEY_RE = re.compile(
    r"(?:access[_-]?token|refresh[_-]?token|api[_-]?key|authorization|cookie|password|secret)",
    re.IGNORECASE,
)
_SECRET_VALUE_RE = re.compile(r"(?:bearer\s+|sk-[A-Za-z0-9]|gh[pousr]_[A-Za-z0-9])", re.IGNORECASE)
_ABSOLUTE_PATH_RE = re.compile(r"(?:^[A-Za-z]:[\\/]|^\\\\|^/[^/])")


class AdapterContractError(ValueError):
    """Stable fail-closed error for a rejected provider result."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class NormalizedPaperResult:
    """Non-authoritative adapter output."""

    artifact: dict[str, Any]
    candidate: dict[str, Any]

    def to_dict(self) -> dict[str, dict[str, Any]]:
        return {"artifact": deepcopy(self.artifact), "candidate": deepcopy(self.candidate)}


def canonical_json(value: Any) -> str:
    """Return the contract's deterministic JSON representation."""

    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (OverflowError, RecursionError, TypeError, ValueError) as exc:
        raise AdapterContractError("non_json", "value is not JSON serializable") from exc


def canonical_sha256(value: Any) -> str:
    digest = hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


def normalize_dsh_mcp_result(
    *,
    public_operation: str,
    binding: Mapping[str, Any],
    subject: Mapping[str, Any],
    arguments: Mapping[str, Any] | None,
    response: Mapping[str, Any],
    correlation_id: str,
    idempotency_key: str,
    retrieved_at: str,
) -> NormalizedPaperResult:
    """Validate and project one already received DSH MCP result.

    The function is intentionally side-effect free.  It accepts only the
    model-facing public operation name; transport code must enforce the same
    allowlist before calling it.
    """

    raw_operation = _validate_call_identity(
        public_operation=public_operation,
        binding=binding,
        subject=subject,
        arguments=arguments,
        correlation_id=correlation_id,
        idempotency_key=idempotency_key,
        retrieved_at=retrieved_at,
    )
    safe_arguments = dict(arguments or {})
    safe_subject = dict(subject)
    safe_binding = dict(binding)
    response_copy = _copy_json_mapping(response, "response")
    if response_copy.get("isError") is True:
        raise AdapterContractError("provider_error", "provider returned an error result")

    structured = _extract_structured_content(response_copy)
    _validate_structured_content(
        structured,
        raw_operation=raw_operation,
        binding=safe_binding,
        subject=safe_subject,
        arguments=safe_arguments,
    )
    payload = deepcopy(structured["payload"])
    provenance = deepcopy(structured["provenance"])
    remote_freshness = structured["remote_freshness"]
    remote_truncated = structured["remote_truncated"]
    request_hash = canonical_sha256(
        {
            "contract_version": REQUEST_CONTRACT_VERSION,
            "binding": safe_binding,
            "operation": raw_operation,
            "subject": safe_subject,
            "arguments": safe_arguments,
        }
    )
    if structured["request_hash"] != request_hash:
        raise AdapterContractError("request_hash_mismatch", "provider request hash does not match local identity")
    result_hash = canonical_sha256(
        {
            "contract_version": RESULT_CONTRACT_VERSION,
            "operation": raw_operation,
            "payload": payload,
            "remote_freshness": remote_freshness,
            "remote_truncated": remote_truncated,
            "provenance": provenance,
        }
    )
    if structured["result_hash"] != result_hash:
        raise AdapterContractError("result_hash_mismatch", "provider result hash does not match parsed payload")

    binding_fingerprint = canonical_sha256(safe_binding)
    candidate_id = "paperlab-candidate-" + canonical_sha256(
        {"request_hash": request_hash, "result_hash": result_hash}
    ).removeprefix("sha256:")[:32]
    artifact = {
        "contract_version": CONTRACT_VERSION,
        "artifact_id": candidate_id,
        "kind": "ExternalSourceArtifact",
        "status": "candidate",
        "local_project_id": safe_binding["local_project_id"],
        "operation": raw_operation,
        "subject": safe_subject,
        "payload": payload,
        "binding": {
            "local_project_id": safe_binding["local_project_id"],
            "remote_project_id": safe_binding["remote_project_id"],
            "provider_echoed_remote_project_id": structured["binding"][
                "provider_echoed_remote_project_id"
            ],
        },
        "source": {
            "provider": SERVER_ALIAS,
            "server_alias": safe_binding["server_alias"],
            "release_commit": safe_binding["release_commit"],
            "profile": safe_binding["profile"],
        },
        "provenance": provenance,
        "remote_freshness": remote_freshness,
        "remote_truncated": remote_truncated,
        "local_truncated": False,
        "truncated": _combined_truncation(remote_truncated, local_truncated=False),
        "content_is_untrusted": True,
        "correlation_id": correlation_id.strip(),
        "idempotency_key": idempotency_key.strip(),
        "retrieved_at": retrieved_at.strip(),
        "binding_fingerprint": binding_fingerprint,
        "arguments_hash": canonical_sha256(safe_arguments),
        "request_hash": request_hash,
        "result_hash": result_hash,
    }
    _reject_sensitive_metadata(artifact)
    encoded_artifact = canonical_json(artifact)
    if len(encoded_artifact) > MAX_RESULT_JSON_CHARS:
        raise AdapterContractError("result_too_large", "normalized artifact exceeds the bounded result limit")

    candidate = {
        "contract_version": CONTRACT_VERSION,
        "candidate_id": candidate_id,
        "kind": "EvidenceCandidate",
        "status": "candidate",
        "artifact_id": candidate_id,
        "local_project_id": safe_binding["local_project_id"],
        "promotion": "requires_devframe_review",
        "supports": "unreviewed",
    }
    return NormalizedPaperResult(artifact=artifact, candidate=candidate)


def _validate_call_identity(
    *,
    public_operation: str,
    binding: Mapping[str, Any],
    subject: Mapping[str, Any],
    arguments: Mapping[str, Any] | None,
    correlation_id: str,
    idempotency_key: str,
    retrieved_at: str,
) -> str:
    raw_operation = PUBLIC_TO_RAW.get(public_operation)
    if raw_operation is None:
        raise AdapterContractError("operation_not_allowed", "operation is outside the PaperLab read-only allowlist")
    if not isinstance(binding, Mapping) or set(binding) != set(_BINDING_FIELDS):
        raise AdapterContractError("binding_invalid", "binding must contain the exact authority fields")
    for field in _BINDING_FIELDS:
        value = _bounded_identifier(binding.get(field), field=field)
        if value is None:
            raise AdapterContractError("binding_invalid", f"binding field {field!r} is invalid")
    if binding["profile"] != READONLY_PROFILE or binding["server_alias"] != SERVER_ALIAS:
        raise AdapterContractError("profile_invalid", "only the pinned read-only Polaris profile is accepted")
    if not isinstance(subject, Mapping) or not _valid_subject(raw_operation, subject):
        raise AdapterContractError("subject_invalid", "operation subject is invalid or missing")
    safe_arguments = dict(arguments or {})
    encoded_arguments = canonical_json(safe_arguments)
    if len(encoded_arguments) > MAX_ARGUMENT_JSON_CHARS:
        raise AdapterContractError("arguments_too_large", "bounded arguments exceeded")
    _bounded_nested(safe_arguments, label="arguments")
    _reject_control_metadata(safe_arguments)
    for value, label in ((correlation_id, "correlation_id"), (idempotency_key, "idempotency_key")):
        if _bounded_identifier(value, field=label) is None:
            raise AdapterContractError("audit_metadata_invalid", f"{label} is invalid or unbounded")
    _validate_timestamp(retrieved_at)
    return raw_operation


def _extract_structured_content(response: Mapping[str, Any]) -> dict[str, Any]:
    content = response.get("content")
    if not isinstance(content, list) or len(content) != 1:
        raise AdapterContractError("malformed_result", "result must contain exactly one content block")
    block = content[0]
    if not isinstance(block, Mapping) or block.get("type") != "text" or not isinstance(block.get("text"), str):
        raise AdapterContractError("malformed_result", "result content must be one JSON text block")
    try:
        text_payload = json.loads(block["text"])
    except json.JSONDecodeError as exc:
        raise AdapterContractError("malformed_result", "result text is not JSON") from exc
    if not isinstance(text_payload, Mapping):
        raise AdapterContractError("malformed_result", "result text must decode to an object")
    structured = response.get("structuredContent")
    if structured is None:
        structured = text_payload
    if not isinstance(structured, Mapping):
        raise AdapterContractError("malformed_result", "structuredContent must be an object")
    if dict(text_payload) != dict(structured):
        raise AdapterContractError("result_mismatch", "content text and structuredContent differ")
    return _copy_json_mapping(structured, "structuredContent")


def _validate_structured_content(
    structured: Mapping[str, Any],
    *,
    raw_operation: str,
    binding: Mapping[str, Any],
    subject: Mapping[str, Any],
    arguments: Mapping[str, Any],
) -> None:
    if set(structured) != _STRUCTURED_FIELDS:
        raise AdapterContractError("unknown_shape", "result contains unknown or missing top-level fields")
    if structured["contract_version"] != RESULT_CONTRACT_VERSION:
        raise AdapterContractError("contract_version_invalid", "result contract version is unsupported")
    if structured["operation"] != raw_operation:
        raise AdapterContractError("operation_mismatch", "result operation does not match the requested operation")
    if structured["content_is_untrusted"] is not True:
        raise AdapterContractError("trust_boundary_invalid", "provider content must remain explicitly untrusted")
    freshness = structured["remote_freshness"]
    if not isinstance(freshness, str) or freshness not in _FRESHNESS_VALUES:
        raise AdapterContractError("freshness_invalid", "provider freshness must be explicit or unknown")
    truncated = structured["remote_truncated"]
    if type(truncated) is not bool and truncated != "unknown":
        raise AdapterContractError("truncation_invalid", "provider truncation must be true, false, or unknown")
    provenance = structured["provenance"]
    if not isinstance(provenance, Mapping) or not set(provenance).issubset(_PROVENANCE_FIELDS):
        raise AdapterContractError("provenance_invalid", "provenance contains unknown fields")
    if not isinstance(provenance.get("source_release"), str) or not provenance["source_release"]:
        raise AdapterContractError("provenance_invalid", "source release provenance is required")
    _bounded_nested(provenance, label="provenance")
    response_binding = structured["binding"]
    if not isinstance(response_binding, Mapping) or set(response_binding) != {
        "local_project_id",
        "remote_project_id",
        "provider_echoed_remote_project_id",
    }:
        raise AdapterContractError("binding_invalid", "result binding shape is invalid")
    if response_binding["local_project_id"] != binding["local_project_id"]:
        raise AdapterContractError("project_mismatch", "result local project does not match authority")
    if response_binding["remote_project_id"] != binding["remote_project_id"]:
        raise AdapterContractError("remote_project_mismatch", "result remote project does not match binding")
    if type(response_binding["provider_echoed_remote_project_id"]) is not bool:
        raise AdapterContractError("binding_invalid", "provider echo marker must be boolean")
    payload = structured["payload"]
    if not isinstance(payload, Mapping) or set(payload) != {PAYLOAD_KEYS[raw_operation]}:
        raise AdapterContractError("payload_shape_invalid", "payload does not match the operation mapping")
    value = payload[PAYLOAD_KEYS[raw_operation]]
    if raw_operation in _LIST_PAYLOAD_OPERATIONS:
        if not isinstance(value, list) or any(not isinstance(item, Mapping) for item in value):
            raise AdapterContractError("payload_shape_invalid", "operation requires a list of objects")
    elif not isinstance(value, Mapping):
        raise AdapterContractError("payload_shape_invalid", "operation requires an object")
    _bounded_nested(payload, label="payload")
    _ensure_subject_consistency(raw_operation, subject, payload)
    _reject_sensitive_metadata(
        {"provenance": provenance, "binding": response_binding},
        reject_urls=True,
    )
    _ = subject, arguments


def _valid_subject(operation: str, subject: Mapping[str, Any]) -> bool:
    if operation in _DISCOVERY_OPERATIONS:
        return set(subject) == {"query"} and _bounded_identifier(subject.get("query"), field="query") is not None
    if operation in _KNOWN_PAPER_OPERATIONS:
        return (
            set(subject) == {"provider_paper_id"}
            and _bounded_identifier(subject.get("provider_paper_id"), field="provider_paper_id") is not None
        )
    if operation == "lookup_paper":
        doi = _bounded_identifier(subject.get("doi"), field="doi")
        return set(subject) == {"doi"} and doi is not None and "/" in doi
    if operation in _GRAPH_OPERATIONS:
        return set(subject) == {"paper_ref"} and _bounded_identifier(subject.get("paper_ref"), field="paper_ref") is not None
    return False


def _bounded_identifier(value: Any, *, field: str) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text or len(text) > MAX_IDENTIFIER_CHARS:
        return None
    lowered = text.casefold()
    if (
        "\\" in text
        or "//" in text
        or lowered.startswith(("http:", "https:"))
        or text in {".", ".."}
    ):
        return None
    if field == "doi" and (text.startswith("/") or text.endswith("/") or text.count("/") != 1):
        return None
    if field != "doi" and "/" in text:
        return None
    if _SECRET_VALUE_RE.search(text) or _ABSOLUTE_PATH_RE.search(text):
        return None
    return text


def _bounded_nested(value: Any, *, label: str, depth: int = 0) -> None:
    if depth > MAX_NESTING_DEPTH:
        raise AdapterContractError("result_too_deep", f"{label} exceeds the nesting limit")
    if isinstance(value, str):
        if len(value) > MAX_PASSAGE_CHARS:
            raise AdapterContractError("passage_too_large", f"{label} contains an oversized text value")
        return
    if isinstance(value, Mapping):
        if len(value) > MAX_COLLECTION_ITEMS:
            raise AdapterContractError("result_too_large", f"{label} contains too many fields")
        for key, item in value.items():
            if not isinstance(key, str) or len(key) > MAX_IDENTIFIER_CHARS:
                raise AdapterContractError("field_invalid", f"{label} contains an invalid field name")
            _bounded_nested(item, label=label, depth=depth + 1)
        return
    if isinstance(value, list):
        if len(value) > MAX_COLLECTION_ITEMS:
            raise AdapterContractError("result_too_large", f"{label} contains too many items")
        for item in value:
            _bounded_nested(item, label=label, depth=depth + 1)
        return
    if value is None or isinstance(value, (bool, int, float)):
        return
    raise AdapterContractError("non_json", f"{label} contains a non-JSON value")


def _copy_json_mapping(value: Mapping[str, Any], label: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise AdapterContractError("malformed_result", f"{label} must be an object")
    try:
        copied = json.loads(canonical_json(dict(value)))
    except AdapterContractError as exc:
        raise AdapterContractError("malformed_result", f"{label} is not JSON") from exc
    if not isinstance(copied, dict):
        raise AdapterContractError("malformed_result", f"{label} must be an object")
    return copied


def _reject_control_metadata(value: Any, *, reject_urls: bool = False) -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            if isinstance(key, str) and _SECRET_KEY_RE.search(key):
                raise AdapterContractError("sensitive_metadata", "secret-bearing metadata is not accepted")
            if isinstance(item, str) and (
                _SECRET_VALUE_RE.search(item)
                or _ABSOLUTE_PATH_RE.search(item)
                or (reject_urls and item.casefold().startswith(("http:", "https:")))
            ):
                raise AdapterContractError("sensitive_metadata", "secret or absolute path metadata is not accepted")
            _reject_control_metadata(item, reject_urls=reject_urls)
    elif isinstance(value, list):
        for item in value:
            _reject_control_metadata(item, reject_urls=reject_urls)


def _reject_sensitive_metadata(value: Any, *, reject_urls: bool = False) -> None:
    _reject_control_metadata(value, reject_urls=reject_urls)


def _combined_truncation(remote_truncated: bool | str, *, local_truncated: bool) -> str:
    if remote_truncated == "unknown":
        return "unknown"
    if remote_truncated and local_truncated:
        return "both"
    if remote_truncated:
        return "remote"
    if local_truncated:
        return "local"
    return "none"


def _ensure_subject_consistency(
    operation: str,
    subject: Mapping[str, Any],
    payload: Mapping[str, Any],
) -> None:
    """Reject a provider payload that contradicts a known paper subject."""

    expected_provider_id = subject.get("provider_paper_id")
    expected_doi = subject.get("doi")

    def visit(value: Any) -> None:
        if isinstance(value, Mapping):
            for key, item in value.items():
                if key == "provider_paper_id" and expected_provider_id is not None:
                    if item != expected_provider_id:
                        raise AdapterContractError(
                            "paper_mismatch",
                            "provider paper identity does not match the requested subject",
                        )
                if (
                    key == "paper_ref"
                    and expected_provider_id is not None
                    and operation not in _GRAPH_OPERATIONS
                    and item != expected_provider_id
                ):
                    raise AdapterContractError(
                        "paper_mismatch",
                        "provider paper identity does not match the requested subject",
                    )
                if key == "doi" and expected_doi is not None and item != expected_doi:
                    raise AdapterContractError(
                        "paper_mismatch",
                        "provider DOI does not match the requested subject",
                    )
                visit(item)
        elif isinstance(value, list):
            for item in value:
                visit(item)

    visit(payload)


def _validate_timestamp(value: str) -> None:
    if not isinstance(value, str) or not 1 <= len(value.strip()) <= 64:
        raise AdapterContractError("timestamp_invalid", "retrieved_at must be a bounded timestamp")
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError as exc:
        raise AdapterContractError("timestamp_invalid", "retrieved_at must be ISO-8601") from exc
    if parsed.tzinfo is None:
        raise AdapterContractError("timestamp_invalid", "retrieved_at must include a timezone")


__all__ = [
    "AdapterContractError",
    "CONTRACT_VERSION",
    "MAX_ARGUMENT_JSON_CHARS",
    "MAX_COLLECTION_ITEMS",
    "MAX_NESTING_DEPTH",
    "MAX_PASSAGE_CHARS",
    "MAX_RESULT_JSON_CHARS",
    "NormalizedPaperResult",
    "PAYLOAD_KEYS",
    "PUBLIC_TO_RAW",
    "READONLY_PROFILE",
    "RESULT_CONTRACT_VERSION",
    "canonical_json",
    "canonical_sha256",
    "normalize_dsh_mcp_result",
]
