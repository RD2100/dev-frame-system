"""Test-only PaperLab/Polaris read-only MCP fixtures."""

from .fake_server import (
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

__all__ = [
    "EXPECTED_DOI",
    "EXPECTED_PAPER_ID",
    "EXPECTED_PROJECT_ID",
    "EXPECTED_TITLE",
    "FIXTURE_NOW_ISO",
    "HIDDEN_TOOLS",
    "MAX_ARGUMENT_JSON_CHARS",
    "MAX_PASSAGE_CHARS",
    "MAX_RESULT_JSON_CHARS",
    "PAYLOAD_FIELDS",
    "READONLY_TOOLS",
    "FakePolarisReadonlyMcp",
    "RpcResponse",
    "canonical_json",
    "canonical_sha256",
]
