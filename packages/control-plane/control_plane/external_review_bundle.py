"""Prepare and validate external Web AI review bundles.

The bundle is a prepare-only artifact. It proves what the external reviewer was
given; it does not submit to a provider and it does not make review output
authoritative.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import posixpath
import re
import zipfile
from typing import Any

from jsonschema import Draft7Validator

from .backup_guard import default_runtime_dir


MANIFEST_NAME = "PACK_MANIFEST.json"
PROMPT_NAME = "REVIEW_PROMPT.md"
LEDGER_NAME = "CONTEXT_LEDGER.md"
REDACTION_NAME = "REDACTION_REPORT.md"
VERIFICATION_NAME = "VERIFICATION.md"

READY = "ready_for_review"
INCOMPLETE = "context_incomplete"
BLOCKED = "blocked"
SCHEMA_VERSION = 2

FORBIDDEN_PARTS = {
    ".git",
    ".devframe-runtime",
    ".codex",
    ".agents",
    ".claude",
    ".ssh",
    ".venv",
    "node_modules",
    "__pycache__",
    "secrets",
    "credentials",
    "browser-profiles",
}

FORBIDDEN_FILENAMES = {
    ".env",
    ".env.local",
    ".env.production",
    "auth.json",
    "credentials.json",
}

FORBIDDEN_EXTENSIONS = {
    ".zip",
    ".7z",
    ".rar",
    ".tar",
    ".gz",
}

SENSITIVE_CONTENT_PATTERNS = [
    re.compile(r"(?i)\b(api[_-]?key|secret|password|token)\s*[:=]\s*['\"][^'\"]{8,}['\"]"),
    re.compile(r"sk-[A-Za-z0-9_-]{20,}"),
]

_DETAIL_LOADER_CONTRACT_ID = "identity-detail-loader.v1"
_DETAIL_LOADER_PROFILE = "identity_detail_contract"
_REVIEW_PROFILE_MARKER_PREFIX = "<!-- devframe-review-metadata: "
_REVIEW_PROFILE_MARKER_SUFFIX = " -->"
_REVIEW_CONTRACT_MARKER_PREFIX = "Executable review contract: "
_DETAIL_LOADER_SOURCE_EXTENSIONS = frozenset(
    {".cjs", ".js", ".jsx", ".mjs", ".svelte", ".ts", ".tsx", ".vue"}
)
_DETAIL_LOADER_INSPECTION_LIMIT = 512_000
_DETAIL_LOADER_REQUIRED_MATRIX = (
    ("null_response", "null response"),
    ("truthy_malformed_response", "truthy malformed response"),
    ("mismatched_requested_identity", "mismatched requested identity"),
    ("current_valid_response", "current valid response"),
    ("deep_link_loading", "direct/deep-link loading"),
    ("transport_failure", "transport failure"),
    ("business_failure", "business failure"),
    ("one_step_retry", "one-step retry"),
    ("hide_invalidation", "hide invalidation"),
    ("unload_invalidation", "unload invalidation"),
)
_DETAIL_LOADER_REQUIRED_PROBES = (
    "real_adapter_deferred_success_at_earliest_state_await",
    "real_adapter_deferred_failure_at_earliest_state_await",
)
_DETAIL_LOADER_MANUAL_FINDINGS = (
    "detail_assignment_missing_shape_guard",
    "detail_assignment_missing_identity_guard",
    "route_loader_missing_retry_context",
    "route_loader_missing_lifecycle_invalidation",
)
_AUTH_FAIL_CLOSED_CONTRACT_ID = "auth-fail-closed-top-level-side-effect.v1"
_AUTH_FAIL_CLOSED_PROFILE = "auth_fail_closed_contract"
_AUTH_FAIL_CLOSED_ZERO_COUNTERS = (
    "init",
    "collection",
    "read",
    "write",
    "transaction",
)
_AUTH_FAIL_CLOSED_REQUIRED_PROBES = (
    "empty_identity_injected_before_fresh_module_load",
    "handler_invoked_with_sdk_side_effect_counters_all_zero",
)

# The repository-root schema is not installed by the control-plane wheel. Keep
# this runtime mirror equal to schemas/external_review_bundle.schema.json; a
# focused test locks the two representations together.
_PUBLIC_MANIFEST_SCHEMA = json.loads(
    r"""
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "$id": "https://rd2100.devframe/schemas/external-review-bundle",
  "title": "External Review Bundle Manifest",
  "description": "Prepare-only manifest for ZIP bundles sent to a browser-hosted external reviewer. The manifest proves what was included; it is not review authority.",
  "type": "object",
  "required": [
    "schema_version",
    "bundle_id",
    "created_at",
    "status",
    "profile",
    "review_question",
    "required_roles",
    "included_roles",
    "missing_required_roles",
    "blocking_issues",
    "review_contracts",
    "package_files",
    "trust_statement"
  ],
  "properties": {
    "schema_version": { "type": "integer", "const": 2 },
    "bundle_id": { "type": "string", "minLength": 1 },
    "created_at": { "type": "string", "minLength": 1 },
    "status": {
      "type": "string",
      "enum": ["ready_for_review", "context_incomplete", "blocked"]
    },
    "profile": { "type": "string", "minLength": 1 },
    "project_root_name": { "type": "string" },
    "review_question": { "type": "string", "minLength": 1 },
    "required_roles": {
      "type": "array",
      "items": { "type": "string", "minLength": 1 }
    },
    "included_roles": {
      "type": "array",
      "items": { "type": "string", "minLength": 1 }
    },
    "missing_required_roles": {
      "type": "array",
      "items": { "type": "string", "minLength": 1 }
    },
    "blocking_issues": {
      "type": "array",
      "items": { "type": "string", "minLength": 1 }
    },
    "review_contracts": {
      "type": "array",
      "items": { "$ref": "#/definitions/review_contract" }
    },
    "package_files": {
      "type": "array",
      "minItems": 4,
      "items": {
        "type": "object",
        "required": ["path", "role", "sha256", "size_bytes", "generated"],
        "properties": {
          "path": { "type": "string", "minLength": 1 },
          "role": { "type": "string", "minLength": 1 },
          "authority": { "type": "string" },
          "sha256": { "type": "string", "pattern": "^[a-f0-9]{64}$" },
          "size_bytes": { "type": "integer", "minimum": 0 },
          "generated": { "type": "boolean" },
          "source_path": { "type": "string" },
          "why": { "type": "string" }
        },
        "additionalProperties": false
      }
    },
    "trust_statement": { "type": "string", "minLength": 1 },
    "zip_path": { "type": "string" },
    "manifest_path": { "type": "string" },
    "validator": {
      "type": "object",
      "properties": {
        "valid": { "type": "boolean" },
        "status": {
          "type": "string",
          "enum": ["ready_for_review", "context_incomplete", "blocked"]
        },
        "issues": {
          "type": "array",
          "items": { "type": "string" }
        }
      },
      "additionalProperties": true
    }
  },
  "definitions": {
    "finding": {
      "type": "object",
      "required": ["code", "source_path"],
      "properties": {
        "code": { "type": "string", "minLength": 1 },
        "source_path": { "type": "string", "minLength": 1 }
      },
      "additionalProperties": false
    },
    "inspection_issue": {
      "type": "object",
      "required": ["code", "source_path"],
      "properties": {
        "code": { "type": "string", "minLength": 1 },
        "source_path": { "type": "string", "minLength": 1 },
        "inspected_bytes": { "type": "integer", "minimum": 0 },
        "source_size_bytes": { "type": "integer", "minimum": 0 }
      },
      "additionalProperties": false
    },
    "review_contract": {
      "if": {
        "required": ["contract_id"],
        "properties": {
          "contract_id": {
            "const": "auth-fail-closed-top-level-side-effect.v1"
          }
        }
      },
      "then": { "$ref": "#/definitions/auth_fail_closed_review_contract" },
      "else": { "$ref": "#/definitions/identity_detail_review_contract" }
    },
    "identity_detail_review_contract": {
      "type": "object",
      "required": [
        "contract_id",
        "applicable",
        "source_paths",
        "findings",
        "inspection",
        "probe_evidence",
        "required_matrix",
        "required_probes"
      ],
      "properties": {
        "contract_id": { "type": "string", "const": "identity-detail-loader.v1" },
        "applicable": { "type": "boolean", "const": true },
        "source_paths": {
          "type": "array",
          "minItems": 1,
          "uniqueItems": true,
          "items": { "type": "string", "minLength": 1 }
        },
        "findings": {
          "type": "array",
          "items": { "$ref": "#/definitions/finding" }
        },
        "inspection": {
          "type": "object",
          "required": ["complete", "issues"],
          "properties": {
            "complete": { "type": "boolean" },
            "issues": {
              "type": "array",
              "items": { "$ref": "#/definitions/inspection_issue" }
            }
          },
          "additionalProperties": false
        },
        "probe_evidence": {
          "type": "object",
          "required": ["status", "source_paths"],
          "properties": {
            "status": {
              "type": "string",
              "enum": ["present", "missing", "unverified"]
            },
            "source_paths": {
              "type": "array",
              "uniqueItems": true,
              "items": { "type": "string", "minLength": 1 }
            },
            "matched_source_paths": {
              "type": "array",
              "uniqueItems": true,
              "items": { "type": "string", "minLength": 1 }
            }
          },
          "additionalProperties": false
        },
        "required_matrix": {
          "type": "array",
          "minItems": 10,
          "maxItems": 10,
          "uniqueItems": true,
          "items": {
            "type": "string",
            "enum": [
              "null_response",
              "truthy_malformed_response",
              "mismatched_requested_identity",
              "current_valid_response",
              "deep_link_loading",
              "transport_failure",
              "business_failure",
              "one_step_retry",
              "hide_invalidation",
              "unload_invalidation"
            ]
          }
        },
        "required_probes": {
          "type": "array",
          "minItems": 2,
          "maxItems": 2,
          "uniqueItems": true,
          "items": {
            "type": "string",
            "enum": [
              "real_adapter_deferred_success_at_earliest_state_await",
              "real_adapter_deferred_failure_at_earliest_state_await"
            ]
          }
        }
      },
      "additionalProperties": false
    },
    "auth_fail_closed_review_contract": {
      "type": "object",
      "required": [
        "contract_id",
        "applicable",
        "source_paths",
        "findings",
        "inspection",
        "probe_evidence",
        "required_probes"
      ],
      "properties": {
        "contract_id": {
          "type": "string",
          "const": "auth-fail-closed-top-level-side-effect.v1"
        },
        "applicable": { "type": "boolean", "const": true },
        "source_paths": {
          "type": "array",
          "minItems": 1,
          "uniqueItems": true,
          "items": { "type": "string", "minLength": 1 }
        },
        "findings": {
          "type": "array",
          "minItems": 1,
          "items": { "$ref": "#/definitions/finding" }
        },
        "inspection": {
          "type": "object",
          "required": ["complete", "issues"],
          "properties": {
            "complete": { "type": "boolean" },
            "issues": {
              "type": "array",
              "items": { "$ref": "#/definitions/inspection_issue" }
            }
          },
          "additionalProperties": false
        },
        "probe_evidence": {
          "type": "object",
          "required": [
            "status",
            "source_paths",
            "matched_source_paths",
            "required_zero_counters"
          ],
          "properties": {
            "status": {
              "type": "string",
              "enum": ["present", "unverified"]
            },
            "source_paths": {
              "type": "array",
              "uniqueItems": true,
              "items": { "type": "string", "minLength": 1 }
            },
            "matched_source_paths": {
              "type": "array",
              "uniqueItems": true,
              "items": { "type": "string", "minLength": 1 }
            },
            "required_zero_counters": {
              "type": "array",
              "minItems": 5,
              "maxItems": 5,
              "uniqueItems": true,
              "items": {
                "type": "string",
                "enum": ["init", "collection", "read", "write", "transaction"]
              }
            }
          },
          "additionalProperties": false
        },
        "required_probes": {
          "type": "array",
          "minItems": 2,
          "maxItems": 2,
          "uniqueItems": true,
          "items": {
            "type": "string",
            "enum": [
              "empty_identity_injected_before_fresh_module_load",
              "handler_invoked_with_sdk_side_effect_counters_all_zero"
            ]
          }
        }
      },
      "additionalProperties": false
    }
  },
  "additionalProperties": false
}
"""
)
_PUBLIC_MANIFEST_VALIDATOR = Draft7Validator(_PUBLIC_MANIFEST_SCHEMA)


@dataclass(frozen=True)
class ReviewSource:
    path: str | Path
    role: str
    authority: str = "unspecified"
    required: bool = True
    why: str = ""


class ReviewBundleError(ValueError):
    """Raised when a review bundle cannot be prepared or trusted."""


def prepare_external_review_bundle(
    *,
    project_root: str | Path,
    review_question: str,
    sources: list[ReviewSource],
    required_roles: list[str] | None = None,
    runtime_dir: str | Path | None = None,
    output_id: str | None = None,
    profile: str = "external_review",
) -> dict[str, Any]:
    """Create a prepare-only ZIP bundle plus manifest in the runtime dir."""

    root = Path(project_root).resolve()
    if not root.exists() or not root.is_dir():
        raise ReviewBundleError(f"project root not found: {root}")
    if not review_question.strip():
        raise ReviewBundleError("review_question is required")
    if not sources:
        raise ReviewBundleError("at least one explicit source is required")

    required_roles = [role.strip() for role in (required_roles or []) if role.strip()]
    runtime_root = Path(runtime_dir).resolve() if runtime_dir else default_runtime_dir()
    bundle_id = _safe_id(output_id or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ-external-review"))
    out_dir = runtime_root / "external-review-bundles" / bundle_id
    out_dir.mkdir(parents=True, exist_ok=True)

    source_entries: list[dict[str, Any]] = []
    blocking_issues: list[str] = []
    for source in sources:
        try:
            source_entries.append(_source_entry(root, source))
        except ReviewBundleError as exc:
            blocking_issues.append(str(exc))

    included_roles = {entry["role"] for entry in source_entries}
    missing_roles = [role for role in required_roles if role not in included_roles]
    if missing_roles:
        blocking_issues.extend(f"missing_required_role:{role}" for role in missing_roles)

    status = READY
    if blocking_issues:
        status = BLOCKED if any(issue.startswith("forbidden_") or issue.startswith("sensitive_") for issue in blocking_issues) else INCOMPLETE

    if profile == _DETAIL_LOADER_PROFILE:
        review_contracts = _inspect_identity_detail_loader_sources(source_entries)
    elif profile == _AUTH_FAIL_CLOSED_PROFILE:
        review_contracts = _inspect_auth_fail_closed_sources(source_entries)
    else:
        review_contracts = []
    if status == READY and any(
        contract["inspection"]["complete"] is not True
        for contract in review_contracts
    ):
        status = INCOMPLETE
    if status == READY and any(
        contract["contract_id"] == _AUTH_FAIL_CLOSED_CONTRACT_ID
        for contract in review_contracts
    ):
        status = INCOMPLETE
    prompt_text = _render_prompt(
        profile,
        review_question,
        source_entries,
        status,
        blocking_issues,
        review_contracts,
    )
    ledger_text = _render_ledger(profile, review_question, source_entries, missing_roles, blocking_issues)
    redaction_text = _render_redaction(source_entries, blocking_issues)
    verification_text = _render_verification(status, blocking_issues)

    generated = {
        PROMPT_NAME: prompt_text.encode("utf-8"),
        LEDGER_NAME: ledger_text.encode("utf-8"),
        REDACTION_NAME: redaction_text.encode("utf-8"),
        VERIFICATION_NAME: verification_text.encode("utf-8"),
    }

    package_files: list[dict[str, Any]] = []
    for zip_path, content in generated.items():
        package_files.append({
            "path": zip_path,
            "role": _role_for_generated(zip_path),
            "sha256": _sha256_bytes(content),
            "size_bytes": len(content),
            "generated": True,
        })
    for entry in source_entries:
        package_files.append({
            "path": entry["bundle_path"],
            "role": entry["role"],
            "authority": entry["authority"],
            "sha256": entry["sha256"],
            "size_bytes": entry["size_bytes"],
            "generated": False,
            "source_path": entry["source_path"],
            "why": entry["why"],
        })

    manifest = {
        "schema_version": SCHEMA_VERSION,
        "bundle_id": bundle_id,
        "created_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "status": status,
        "profile": profile,
        "project_root_name": root.name,
        "review_question": review_question,
        "required_roles": required_roles,
        "included_roles": sorted(included_roles),
        "missing_required_roles": missing_roles,
        "blocking_issues": blocking_issues,
        "review_contracts": review_contracts,
        "package_files": package_files,
        "trust_statement": _trust_statement(status),
    }

    manifest_bytes = json.dumps(manifest, indent=2, ensure_ascii=True).encode("utf-8")
    zip_path = out_dir / f"{bundle_id}.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for path, content in generated.items():
            zf.writestr(path, content)
        for entry in source_entries:
            zf.write(entry["absolute_path"], entry["bundle_path"])
        zf.writestr(MANIFEST_NAME, manifest_bytes)

    manifest_path = out_dir / MANIFEST_NAME
    manifest_path.write_bytes(manifest_bytes)
    (out_dir / PROMPT_NAME).write_bytes(generated[PROMPT_NAME])
    (out_dir / LEDGER_NAME).write_bytes(generated[LEDGER_NAME])
    (out_dir / REDACTION_NAME).write_bytes(generated[REDACTION_NAME])
    (out_dir / VERIFICATION_NAME).write_bytes(generated[VERIFICATION_NAME])

    validation = validate_external_review_bundle(zip_path)
    manifest["zip_path"] = str(zip_path)
    manifest["manifest_path"] = str(manifest_path)
    manifest["validator"] = validation
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    return manifest


def validate_external_review_bundle(zip_path: str | Path) -> dict[str, Any]:
    """Validate manifest/ZIP consistency without trusting narrative content."""

    zp = Path(zip_path).resolve()
    issues: list[str] = []
    if not zp.exists():
        return {"valid": False, "status": BLOCKED, "issues": [f"zip_not_found:{zp}"]}

    try:
        with zipfile.ZipFile(zp, "r") as zf:
            names = {name.replace("\\", "/") for name in zf.namelist()}
            if MANIFEST_NAME not in names:
                return {"valid": False, "status": BLOCKED, "issues": ["manifest_missing"]}
            manifest = json.loads(zf.read(MANIFEST_NAME).decode("utf-8"))
            if not isinstance(manifest, dict):
                return {"valid": False, "status": BLOCKED, "issues": ["manifest_invalid"]}
            issues.extend(_manifest_schema_issues(manifest))
            package_files = manifest.get("package_files")
            if not isinstance(package_files, list) or not all(
                isinstance(entry, dict) for entry in package_files
            ):
                return {"valid": False, "status": BLOCKED, "issues": ["manifest_package_files_invalid"]}
            listed = {str(entry.get("path", "")).replace("\\", "/") for entry in package_files}
            expected = listed | {MANIFEST_NAME}
            extra_zip = sorted(names - expected)
            missing_zip = sorted(expected - names)
            if extra_zip:
                issues.append(f"zip_has_unlisted_files:{','.join(extra_zip)}")
            if missing_zip:
                issues.append(f"manifest_lists_missing_files:{','.join(missing_zip)}")
            for entry in package_files:
                path = str(entry.get("path", "")).replace("\\", "/")
                expected_hash = str(entry.get("sha256", ""))
                if path in names and expected_hash:
                    actual_hash = _sha256_bytes(zf.read(path))
                    if actual_hash != expected_hash:
                        issues.append(f"sha256_mismatch:{path}")
            prompt_raw = zf.read(PROMPT_NAME) if PROMPT_NAME in names else None
            issues.extend(_review_prompt_profile_issues(manifest, prompt_raw))
            issues.extend(
                _identity_manifest_coherence_issues(manifest, package_files)
            )
            issues.extend(
                _auth_manifest_coherence_issues(manifest, package_files)
            )
    except (OSError, zipfile.BadZipFile, UnicodeDecodeError, json.JSONDecodeError) as exc:
        return {"valid": False, "status": BLOCKED, "issues": [f"zip_validation_error:{exc}"]}

    manifest_status = str(manifest.get("status") or INCOMPLETE)
    if manifest_status not in {READY, INCOMPLETE, BLOCKED}:
        issues.append(f"invalid_manifest_status:{manifest_status}")
        manifest_status = BLOCKED
    if issues:
        return {"valid": False, "status": BLOCKED, "issues": issues}
    return {
        "valid": manifest_status == READY,
        "status": manifest_status,
        "issues": list(manifest.get("blocking_issues") or []),
    }


def _manifest_schema_issues(manifest: dict[str, Any]) -> list[str]:
    errors = sorted(
        _PUBLIC_MANIFEST_VALIDATOR.iter_errors(manifest),
        key=lambda error: tuple(str(part) for part in error.absolute_path),
    )
    issue_paths = dict.fromkeys(_schema_error_path(error.absolute_path) for error in errors)
    return [f"manifest_schema_invalid:{path}" for path in issue_paths]


def _schema_error_path(path_parts: Any) -> str:
    path = ""
    for part in path_parts:
        path += f"[{part}]" if isinstance(part, int) else f".{part}"
    return path.removeprefix(".") or "$"


def _review_prompt_profile_issues(
    manifest: dict[str, Any],
    prompt_raw: bytes | None,
) -> list[str]:
    mismatch = "review_profile_manifest_incoherent:prompt_profile_mismatch"
    contract_mismatch = (
        "review_profile_manifest_incoherent:prompt_contract_mismatch"
    )
    profile = manifest.get("profile")
    if not isinstance(profile, str) or prompt_raw is None:
        return [mismatch]
    try:
        prompt_lines = prompt_raw.decode("utf-8").splitlines()
    except UnicodeDecodeError:
        return [mismatch]
    expected = _review_profile_marker(profile)
    marker_lines = [
        line
        for line in prompt_lines
        if line.startswith(_REVIEW_PROFILE_MARKER_PREFIX)
    ]
    if len(prompt_lines) < 2 or prompt_lines[1] != expected or marker_lines != [expected]:
        return [mismatch]
    contracts = manifest.get("review_contracts")
    manifest_contract_ids = [
        contract.get("contract_id")
        for contract in contracts
        if isinstance(contract, dict)
        and isinstance(contract.get("contract_id"), str)
    ] if isinstance(contracts, list) else []
    prompt_contract_ids = [
        line.removeprefix(_REVIEW_CONTRACT_MARKER_PREFIX)
        for line in prompt_lines
        if line.startswith(_REVIEW_CONTRACT_MARKER_PREFIX)
    ]
    if prompt_contract_ids != manifest_contract_ids:
        return [contract_mismatch]
    return []


def _identity_manifest_coherence_issues(
    manifest: dict[str, Any],
    package_files: list[dict[str, Any]],
) -> list[str]:
    contracts = manifest.get("review_contracts")
    identity_contracts = [
        contract
        for contract in contracts if isinstance(contract, dict)
        and contract.get("contract_id") == _DETAIL_LOADER_CONTRACT_ID
    ] if isinstance(contracts, list) else []
    if manifest.get("profile") != _DETAIL_LOADER_PROFILE:
        return (
            ["identity_contract_manifest_incoherent:profile_contract_mismatch"]
            if identity_contracts else []
        )

    issues: list[str] = []
    if manifest.get("schema_version") != SCHEMA_VERSION:
        issues.append("identity_contract_manifest_incoherent:schema_version")
    if manifest.get("status") != INCOMPLETE:
        issues.append("identity_contract_manifest_incoherent:status")
    if not isinstance(contracts, list) or len(contracts) != 1 or len(identity_contracts) != 1:
        issues.append("identity_contract_manifest_incoherent:contract_selection")
        return issues

    source_entries = [
        entry for entry in package_files if entry.get("generated") is False
    ]
    source_paths = [entry.get("source_path") for entry in source_entries]
    if (
        not source_paths
        or any(not isinstance(path, str) or not path for path in source_paths)
        or len(set(source_paths)) != len(source_paths)
    ):
        issues.append("identity_contract_manifest_incoherent:supplied_sources")
        return issues
    issues.extend(
        _identity_contract_coherence_issues(
            identity_contracts[0],
            source_entries,
            sorted(source_paths),
        )
    )
    return issues


def _identity_contract_coherence_issues(
    contract: dict[str, Any],
    source_entries: list[dict[str, Any]],
    source_paths: list[str],
) -> list[str]:
    issues: list[str] = []
    contract_paths = contract.get("source_paths")
    if contract.get("applicable") is not True or contract_paths != source_paths:
        issues.append("identity_contract_manifest_incoherent:source_paths")

    finding_pairs = _manifest_code_pairs(contract.get("findings"))
    expected_pairs = {
        (source_path, code)
        for source_path in source_paths
        for code in _DETAIL_LOADER_MANUAL_FINDINGS
    }
    if not expected_pairs.issubset(finding_pairs):
        issues.append("identity_contract_manifest_incoherent:manual_findings")

    inspection = contract.get("inspection")
    inspection_items = inspection.get("issues") if isinstance(inspection, dict) else None
    inspection_pairs = _manifest_code_pairs(inspection_items)
    expected_inspection = {
        (source_path, "detail_loader_analysis_unverified")
        for source_path in source_paths
    }
    if (
        not isinstance(inspection, dict)
        or inspection.get("complete") is not False
        or not expected_inspection.issubset(inspection_pairs)
    ):
        issues.append("identity_contract_manifest_incoherent:inspection")

    if contract.get("required_matrix") != [
        item_id for item_id, _ in _DETAIL_LOADER_REQUIRED_MATRIX
    ]:
        issues.append("identity_contract_manifest_incoherent:required_matrix")
    if contract.get("required_probes") != list(_DETAIL_LOADER_REQUIRED_PROBES):
        issues.append("identity_contract_manifest_incoherent:required_probes")
    issues.extend(
        _identity_probe_coherence_issues(
            contract.get("probe_evidence"),
            source_entries,
            finding_pairs,
        )
    )
    return issues


def _manifest_code_pairs(items: Any) -> set[tuple[str, str]]:
    if not isinstance(items, list):
        return set()
    return {
        (source_path, code)
        for item in items if isinstance(item, dict)
        for source_path, code in [(item.get("source_path"), item.get("code"))]
        if isinstance(source_path, str) and isinstance(code, str)
    }


def _identity_probe_coherence_issues(
    probe_evidence: Any,
    source_entries: list[dict[str, Any]],
    finding_pairs: set[tuple[str, str]],
) -> list[str]:
    if not isinstance(probe_evidence, dict):
        return ["identity_contract_manifest_incoherent:probe_evidence"]
    expected_paths = sorted(
        str(entry["source_path"])
        for entry in source_entries if _is_probe_source(entry)
    )
    probe_paths = probe_evidence.get("source_paths")
    matched_paths = probe_evidence.get("matched_source_paths", [])
    status = probe_evidence.get("status")
    missing_finding = any(
        code == "real_adapter_deferred_probe_missing"
        for _, code in finding_pairs
    )
    coherent = (
        probe_paths == expected_paths
        and isinstance(matched_paths, list)
        and all(isinstance(path, str) for path in matched_paths)
        and set(matched_paths).issubset(expected_paths)
    )
    if expected_paths:
        coherent = coherent and (
            (status == "present" and bool(matched_paths))
            or (status == "unverified" and not matched_paths)
        ) and not missing_finding
    else:
        coherent = coherent and status == "missing" and not matched_paths and missing_finding
    return [] if coherent else ["identity_contract_manifest_incoherent:probe_evidence"]


def _auth_manifest_coherence_issues(
    manifest: dict[str, Any],
    package_files: list[dict[str, Any]],
) -> list[str]:
    contracts = manifest.get("review_contracts")
    auth_contracts = [
        contract
        for contract in contracts
        if isinstance(contract, dict)
        and contract.get("contract_id") == _AUTH_FAIL_CLOSED_CONTRACT_ID
    ] if isinstance(contracts, list) else []
    if manifest.get("profile") != _AUTH_FAIL_CLOSED_PROFILE:
        return (
            ["auth_contract_manifest_incoherent:profile_contract_mismatch"]
            if auth_contracts else []
        )
    if not auth_contracts:
        return []

    issues: list[str] = []
    if manifest.get("status") != INCOMPLETE:
        issues.append("auth_contract_manifest_incoherent:status")
    if not isinstance(contracts, list) or len(contracts) != 1 or len(auth_contracts) != 1:
        issues.append("auth_contract_manifest_incoherent:contract_selection")
        return issues

    contract = auth_contracts[0]
    production_paths = sorted(
        source_path
        for entry in package_files
        if entry.get("generated") is False and not _is_probe_source(entry)
        for source_path in [entry.get("source_path")]
        if isinstance(source_path, str) and source_path
    )
    source_paths = contract.get("source_paths")
    source_path_items = (
        source_paths
        if isinstance(source_paths, list)
        and all(isinstance(path, str) and path for path in source_paths)
        else []
    )
    if (
        contract.get("applicable") is not True
        or not source_path_items
        or source_paths != sorted(set(source_paths))
        or not set(source_paths).issubset(production_paths)
    ):
        issues.append("auth_contract_manifest_incoherent:source_paths")

    finding_pairs = _manifest_code_pairs(contract.get("findings"))
    toplevel_paths = {
        source_path
        for source_path, code in finding_pairs
        if code == "module_toplevel_sdk_handle_before_handler_auth"
    }
    analysis_unverified_paths = {
        source_path
        for source_path, code in finding_pairs
        if code == "auth_fail_closed_analysis_unverified"
    }
    if (
        toplevel_paths & analysis_unverified_paths
        or toplevel_paths | analysis_unverified_paths != set(source_path_items)
    ):
        issues.append("auth_contract_manifest_incoherent:findings")

    inspection = contract.get("inspection")
    inspection_items = (
        inspection.get("issues")
        if isinstance(inspection, dict)
        and isinstance(inspection.get("issues"), list)
        else []
    )
    inspected_issue_paths = {
        source_path
        for source_path, _ in _manifest_code_pairs(inspection_items)
    }
    coherent_inspection = (
        isinstance(inspection, dict)
        and (
            (
                bool(analysis_unverified_paths)
                and inspection.get("complete") is False
                and analysis_unverified_paths.issubset(inspected_issue_paths)
            )
            or (
                not analysis_unverified_paths
                and inspection == {"complete": True, "issues": []}
            )
        )
    )
    if not coherent_inspection:
        issues.append("auth_contract_manifest_incoherent:inspection")
    if contract.get("required_probes") != list(_AUTH_FAIL_CLOSED_REQUIRED_PROBES):
        issues.append("auth_contract_manifest_incoherent:required_probes")

    probe_evidence = contract.get("probe_evidence")
    probe_paths = sorted(
        source_path
        for entry in package_files
        if entry.get("generated") is False and _is_probe_source(entry)
        for source_path in [entry.get("source_path")]
        if isinstance(source_path, str) and source_path
    )
    coherent_probe = isinstance(probe_evidence, dict)
    if coherent_probe:
        matched_paths = probe_evidence.get("matched_source_paths")
        status = probe_evidence.get("status")
        coherent_probe = (
            probe_evidence.get("source_paths") == probe_paths
            and isinstance(matched_paths, list)
            and all(isinstance(path, str) and path for path in matched_paths)
            and matched_paths == sorted(set(matched_paths))
            and set(matched_paths).issubset(probe_paths)
            and probe_evidence.get("required_zero_counters")
            == list(_AUTH_FAIL_CLOSED_ZERO_COUNTERS)
            and (
                (status == "present" and bool(matched_paths))
                or (status == "unverified" and not matched_paths)
            )
        )
        unverified_findings = {
            source_path
            for source_path, code in finding_pairs
            if code == "auth_fail_closed_probe_unverified"
        }
        expected_unverified = (
            set(source_path_items) if status == "unverified" else set()
        )
        coherent_probe = coherent_probe and unverified_findings == expected_unverified
    if not coherent_probe:
        issues.append("auth_contract_manifest_incoherent:probe_evidence")
    return issues


def _source_entry(project_root: Path, source: ReviewSource) -> dict[str, Any]:
    candidate = (project_root / source.path).resolve() if not Path(source.path).is_absolute() else Path(source.path).resolve()
    try:
        relative = candidate.relative_to(project_root)
    except ValueError as exc:
        raise ReviewBundleError(f"forbidden_path_outside_project:{source.path}") from exc
    if not candidate.exists() or not candidate.is_file():
        raise ReviewBundleError(f"missing_source:{relative.as_posix()}")
    lowered_parts = {part.lower() for part in relative.parts}
    if lowered_parts & FORBIDDEN_PARTS or relative.name.lower() in FORBIDDEN_FILENAMES:
        raise ReviewBundleError(f"forbidden_sensitive_path:{relative.as_posix()}")
    if relative.suffix.lower() in FORBIDDEN_EXTENSIONS:
        raise ReviewBundleError(f"forbidden_nested_archive:{relative.as_posix()}")
    raw = candidate.read_bytes()
    if _looks_sensitive(raw):
        raise ReviewBundleError(f"sensitive_content_detected:{relative.as_posix()}")
    rel_text = relative.as_posix()
    return {
        "source_path": rel_text,
        "bundle_path": f"sources/{rel_text}",
        "absolute_path": candidate,
        "role": _safe_id(source.role or "source"),
        "authority": source.authority or "unspecified",
        "required": bool(source.required),
        "why": source.why,
        "sha256": _sha256_bytes(raw),
        "size_bytes": len(raw),
        "inspection": _detail_loader_inspection(relative, raw),
    }


def _looks_sensitive(raw: bytes) -> bool:
    if len(raw) > 2_000_000:
        return False
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        return False
    return any(pattern.search(text) for pattern in SENSITIVE_CONTENT_PATTERNS)


def _detail_loader_inspection(relative: Path, raw: bytes) -> dict[str, Any] | None:
    if relative.suffix.lower() not in _DETAIL_LOADER_SOURCE_EXTENSIONS:
        return None
    truncated = len(raw) > _DETAIL_LOADER_INSPECTION_LIMIT
    inspected = raw[:_DETAIL_LOADER_INSPECTION_LIMIT]
    try:
        text = inspected.decode("utf-8-sig", errors="ignore" if truncated else "strict")
    except UnicodeDecodeError:
        return {
            "text": None,
            "complete": False,
            "issue": {
                "code": "detail_loader_inspection_decode_error",
                "source_path": relative.as_posix(),
                "inspected_bytes": len(inspected),
                "source_size_bytes": len(raw),
            },
        }
    return {
        "text": _sanitize_javascript_lexically(text),
        "probe_text": _sanitize_javascript_lexically(
            text,
            preserve_strings=True,
        ),
        "complete": not truncated,
        "issue": {
            "code": "detail_loader_inspection_truncated",
            "source_path": relative.as_posix(),
            "inspected_bytes": len(inspected),
            "source_size_bytes": len(raw),
        } if truncated else None,
    }


def _inspect_identity_detail_loader_sources(
    sources: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    findings: list[dict[str, str]] = []
    source_paths: set[str] = set()
    inspection_issues: list[dict[str, Any]] = []
    for entry in sources:
        source_path = str(entry["source_path"])
        source_paths.add(source_path)
        findings.extend(
            {"code": code, "source_path": source_path}
            for code in _DETAIL_LOADER_MANUAL_FINDINGS
        )
        inspection_issues.append(
            {
                "code": "detail_loader_analysis_unverified",
                "source_path": source_path,
            }
        )
        inspection = entry.get("inspection")
        if isinstance(inspection, dict) and inspection.get("complete") is not True:
            issue = inspection.get("issue")
            if isinstance(issue, dict):
                inspection_issues.append(issue)

    if not source_paths:
        return []

    probe_evidence, probe_issues = _detail_loader_probe_evidence(sources)
    inspection_issues.extend(probe_issues)
    if probe_evidence["status"] == "missing":
        findings.append(
            {
                "code": "real_adapter_deferred_probe_missing",
                "source_path": sorted(source_paths)[0],
            }
        )
    return [
        {
            "contract_id": _DETAIL_LOADER_CONTRACT_ID,
            "applicable": True,
            "source_paths": sorted(source_paths),
            "findings": findings,
            "inspection": {
                "complete": not inspection_issues,
                "issues": inspection_issues,
            },
            "probe_evidence": probe_evidence,
            "required_matrix": [item_id for item_id, _ in _DETAIL_LOADER_REQUIRED_MATRIX],
            "required_probes": list(_DETAIL_LOADER_REQUIRED_PROBES),
        }
    ]


def _inspect_auth_fail_closed_sources(
    sources: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    applicable_paths: list[str] = []
    unverified_paths: list[str] = []
    inspection_issues: list[dict[str, Any]] = []
    for entry in sources:
        if _is_probe_source(entry):
            continue
        source_path = str(entry["source_path"])
        inspection = entry.get("inspection")
        if not isinstance(inspection, dict) or inspection.get("complete") is not True:
            unverified_paths.append(source_path)
            issue = inspection.get("issue") if isinstance(inspection, dict) else None
            inspection_issues.append(
                issue if isinstance(issue, dict) else {
                    "code": "auth_fail_closed_inspection_unavailable",
                    "source_path": source_path,
                }
            )
        elif _has_toplevel_sdk_handle_before_auth(entry):
            applicable_paths.append(source_path)
    source_paths = sorted(set(applicable_paths) | set(unverified_paths))
    applicable_paths = sorted(set(applicable_paths))
    unverified_paths = sorted(set(unverified_paths))
    if not source_paths:
        return []

    probe_paths = sorted(
        str(entry["source_path"])
        for entry in sources if _is_probe_source(entry)
    )
    matched_probe_paths = sorted(
        str(entry["source_path"])
        for entry in sources
        if _is_probe_source(entry)
        and _has_direct_auth_fail_closed_probe(entry, source_paths)
    )
    probe_status = "present" if matched_probe_paths else "unverified"
    findings = [
        {
            "code": "module_toplevel_sdk_handle_before_handler_auth",
            "source_path": source_path,
        }
        for source_path in applicable_paths
    ]
    findings.extend(
        {
            "code": "auth_fail_closed_analysis_unverified",
            "source_path": source_path,
        }
        for source_path in unverified_paths
    )
    if probe_status == "unverified":
        findings.extend(
            {
                "code": "auth_fail_closed_probe_unverified",
                "source_path": source_path,
            }
            for source_path in source_paths
        )
    return [
        {
            "contract_id": _AUTH_FAIL_CLOSED_CONTRACT_ID,
            "applicable": True,
            "source_paths": source_paths,
            "findings": findings,
            "inspection": {
                "complete": not inspection_issues,
                "issues": inspection_issues,
            },
            "probe_evidence": {
                "status": probe_status,
                "source_paths": probe_paths,
                "matched_source_paths": matched_probe_paths,
                "required_zero_counters": list(_AUTH_FAIL_CLOSED_ZERO_COUNTERS),
            },
            "required_probes": list(_AUTH_FAIL_CLOSED_REQUIRED_PROBES),
        }
    ]


def _has_toplevel_sdk_handle_before_auth(entry: dict[str, Any]) -> bool:
    inspection = entry.get("inspection")
    if not isinstance(inspection, dict) or inspection.get("complete") is not True:
        return False
    text = inspection.get("text")
    if not isinstance(text, str):
        return False
    top_level = _javascript_top_level_text(text)
    identifier = r"[A-Za-z_$][\w$]*"
    assignment = (
        rf"(?:\b(?:const|let|var)\s+{identifier}\s*=\s*|"
        rf"\b{identifier}\s*=\s*)"
    )
    creates_handle = bool(
        re.search(
            assignment + rf"(?:{identifier}\.)?database\s*\(",
            top_level,
        )
        or re.search(
            assignment + rf"{identifier}\.collection\s*\(",
            top_level,
        )
    )
    if not creates_handle:
        return False
    return any(
        "getWXContext" in block
        and re.search(r"\bOPENID\b", block, re.IGNORECASE)
        and re.search(r"if\s*\(\s*!\s*[A-Za-z_$][\w$]*\b", block)
        for block in _javascript_handler_blocks(text)
    )


def _javascript_top_level_text(text: str) -> str:
    output = list(text)
    depth = 0
    for index, character in enumerate(text):
        if character == "{":
            depth += 1
        elif character == "}":
            depth = max(0, depth - 1)
        elif depth:
            if character not in {"\r", "\n"}:
                output[index] = " "
    return "".join(output)


def _javascript_handler_blocks(text: str) -> list[str]:
    blocks: list[str] = []
    for match in re.finditer(
        r"\b(?:exports\.[A-Za-z_$][\w$]*|module\.exports)\s*=",
        text,
    ):
        brace = text.find("{", match.end())
        if brace >= 0:
            block = _balanced_javascript_block(text, brace)
            if block is not None:
                blocks.append(block)
    return blocks


def _balanced_javascript_block(text: str, opening_brace: int) -> str | None:
    depth = 0
    for index in range(opening_brace, len(text)):
        if text[index] == "{":
            depth += 1
        elif text[index] == "}":
            depth -= 1
            if depth == 0:
                return text[opening_brace:index + 1]
    return None


def _has_direct_auth_fail_closed_probe(
    entry: dict[str, Any],
    reviewed_source_paths: list[str],
) -> bool:
    inspection = entry.get("inspection")
    if not isinstance(inspection, dict) or inspection.get("complete") is not True:
        return False
    text = inspection.get("probe_text")
    if not isinstance(text, str):
        return False
    for raw_block in _javascript_test_blocks(text):
        block = _without_static_false_blocks(raw_block)
        reset = re.search(r"\b(?:jest|vi)\.resetModules\s*\(", block)
        empty_identity = re.search(
            r"\b(?P<identity_sdk>[A-Za-z_$][\w$]*)"
            r"\.getWXContext\.mockReturnValue(?:Once)?\s*\(\s*"
            r"\{\s*OPENID\s*:\s*(?:\"\"|''|``)\s*\}\s*\)",
            block,
        )
        sdk_mock = re.search(
            r"\b(?:jest|vi)\.doMock\s*\(\s*"
            r"[\"'](?P<sdk>[^\"']+)[\"']\s*,\s*"
            r"\(\s*\)\s*=>\s*(?P<sdk_object>[A-Za-z_$][\w$]*)\s*\)",
            block,
        )
        module_load = re.search(
            r"\b(?:const|let)\s+(?P<handler>[A-Za-z_$][\w$]*)\s*=\s*"
            r"require\s*\(\s*[\"'](?P<module>[^\"']+)[\"']\s*\)",
            block,
        )
        if not all((reset, empty_identity, sdk_mock, module_load)):
            continue
        handler_call = re.search(
            rf"\bawait\s+{re.escape(module_load.group('handler'))}\."
            r"[A-Za-z_$][\w$]*\s*\(",
            block,
        )
        assertion = re.search(
            r"\bexpect\s*\(\s*(?P<counter>[A-Za-z_$][\w$]*)\s*\)"
            r"\.toEqual\s*"
            r"\(\s*\{(?P<counters>[\s\S]*?)\}\s*\)",
            block,
        )
        if not handler_call or not assertion:
            continue
        counters = assertion.group("counters")
        counter_name = assertion.group("counter")
        sdk_counters_bound = _sdk_counters_are_directly_bound(
            block,
            counter_name,
            sdk_mock.group("sdk_object"),
        )
        asserts_all_zero = all(
            re.search(rf"\b{counter}\s*:\s*0\b", counters)
            for counter in _AUTH_FAIL_CLOSED_ZERO_COUNTERS
        )
        if (
            reset.start() < empty_identity.start() < sdk_mock.start() < module_load.start()
            and module_load.end() < handler_call.start() < assertion.start()
            and sdk_mock.group("sdk") in {"wx-server-sdk", "@cloudbase/node-sdk"}
            and empty_identity.group("identity_sdk")
            == sdk_mock.group("sdk_object")
            and _required_module_matches_reviewed_source(
                str(entry["source_path"]),
                module_load.group("module"),
                reviewed_source_paths,
            )
            and sdk_counters_bound
            and asserts_all_zero
        ):
            return True
    return False


def _sdk_counters_are_directly_bound(
    block: str,
    counter_name: str,
    sdk_object_name: str,
) -> bool:
    counter = re.escape(counter_name)
    sdk_object = _javascript_object_literal(block, sdk_object_name)
    if sdk_object is None or not _counter_callback_is_bound(
        sdk_object,
        r"\binit",
        counter,
        "init",
    ):
        return False
    database_binding = re.search(
        r"\bdatabase\s*:\s*(?:jest|vi)\.fn\s*\(\s*"
        r"\([^)]*\)\s*=>\s*(?P<database>[A-Za-z_$][\w$]*)\s*\)",
        sdk_object,
    )
    if database_binding is None:
        return False
    database_object = _javascript_object_literal(
        block,
        database_binding.group("database"),
    )
    if database_object is None or not _counter_callback_is_bound(
        database_object,
        r"\b(?:runTransaction|startTransaction)",
        counter,
        "transaction",
    ):
        return False
    collection_binding = re.search(
        r"\bcollection\s*:\s*(?:jest|vi)\.fn\s*\(\s*"
        r"\([^)]*\)\s*=>\s*\{(?P<body>[^{}]{0,2048}?)\}\s*\)",
        database_object,
    )
    if collection_binding is None:
        return False
    collection_body = collection_binding.group("body")
    collection_return = re.search(
        r"\breturn\s+(?P<collection>[A-Za-z_$][\w$]*)\s*;",
        collection_body,
    )
    if (
        collection_return is None
        or re.match(
            rf"\s*\b{counter}\.collection\s*\+=\s*1\s*;",
            collection_body,
        ) is None
    ):
        return False
    collection_object = _javascript_object_literal(
        block,
        collection_return.group("collection"),
    )
    return (
        collection_object is not None
        and _counter_callback_is_bound(
            collection_object,
            r"\b(?:get|find|query)",
            counter,
            "read",
        )
        and _counter_callback_is_bound(
            collection_object,
            r"\b(?:add|set|update|remove|delete)",
            counter,
            "write",
        )
    )


def _counter_callback_is_bound(
    object_text: str,
    property_pattern: str,
    counter_name: str,
    counter_part: str,
) -> bool:
    return bool(
        re.search(
            property_pattern
            + r"\s*:\s*(?:jest|vi)\.fn\s*\(\s*(?:async\s*)?"
            r"\([^)]*\)\s*=>\s*\{\s*"
            + rf"\b{counter_name}\.{counter_part}\s*\+=\s*1\s*;",
            object_text,
        )
    )


def _javascript_object_literal(text: str, variable_name: str) -> str | None:
    declaration = re.search(
        rf"\b(?:const|let|var)\s+{re.escape(variable_name)}\s*=\s*\{{",
        text,
    )
    if declaration is None:
        return None
    return _balanced_javascript_block(text, declaration.end() - 1)


def _required_module_matches_reviewed_source(
    probe_source_path: str,
    required_module: str,
    reviewed_source_paths: list[str],
) -> bool:
    if not required_module.startswith("."):
        return False
    resolved = posixpath.normpath(
        posixpath.join(
            posixpath.dirname(probe_source_path.replace("\\", "/")),
            required_module,
        )
    )
    resolved_stem = posixpath.splitext(resolved)[0]
    return any(
        posixpath.splitext(source_path.replace("\\", "/"))[0] == resolved_stem
        for source_path in reviewed_source_paths
    )


def _without_static_false_blocks(text: str) -> str:
    output = list(text)
    for match in re.finditer(r"\bif\s*\(\s*false\s*\)\s*\{", text):
        block = _balanced_javascript_block(text, match.end() - 1)
        if block is None:
            continue
        stop = match.end() - 1 + len(block)
        for index in range(match.start(), stop):
            if output[index] not in {"\r", "\n"}:
                output[index] = " "
    return "".join(output)


def _javascript_test_blocks(text: str) -> list[str]:
    blocks: list[str] = []
    for match in re.finditer(
        r"\b(?:test|it)\s*\([\s\S]{0,1024}?=>\s*\{",
        text,
    ):
        brace = match.end() - 1
        block = _balanced_javascript_block(text, brace)
        if block is not None:
            blocks.append(block)
    return blocks


def _sanitize_javascript_lexically(
    text: str,
    *,
    preserve_strings: bool = False,
) -> str:
    output = list(text)
    index = 0
    while index < len(text):
        if text.startswith("//", index):
            stop = text.find("\n", index + 2)
            stop = len(text) if stop < 0 else stop
        elif text.startswith("/*", index):
            stop = text.find("*/", index + 2)
            stop = len(text) if stop < 0 else stop + 2
        elif text[index] in {"'", '"', "`"}:
            quote = text[index]
            stop = index + 1
            while stop < len(text):
                if text[stop] == "\\":
                    stop += 2
                    continue
                stop += 1
                if text[stop - 1] == quote:
                    break
            if preserve_strings:
                index = stop
                continue
        else:
            index += 1
            continue
        for offset in range(index, min(stop, len(text))):
            if text[offset] not in {"\r", "\n"}:
                output[offset] = " "
        index = stop
    return "".join(output)


def _is_probe_source(entry: dict[str, Any]) -> bool:
    role = str(entry.get("role") or "").lower()
    path = str(entry.get("source_path") or "").replace("\\", "/").lower()
    role_tokens = set(re.findall(r"[a-z0-9]+", role))
    return any(
        marker in f"/{path}"
        for marker in ("/tests/", "/__tests__/", ".test.", ".spec.")
    ) or bool(role_tokens & {"test", "tests", "probe", "probes"})


def _detail_loader_probe_evidence(
    sources: list[dict[str, Any]],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    probes = [entry for entry in sources if _is_probe_source(entry)]
    if not probes:
        return {"status": "missing", "source_paths": []}, []

    present_paths: list[str] = []
    issues: list[dict[str, Any]] = []
    for entry in probes:
        source_path = str(entry["source_path"])
        inspection = entry.get("inspection")
        if not isinstance(inspection, dict) or inspection.get("complete") is not True:
            issue = inspection.get("issue") if isinstance(inspection, dict) else None
            issues.append(issue if isinstance(issue, dict) else {
                    "code": "detail_loader_probe_inspection_unavailable",
                    "source_path": source_path,
                    "inspected_bytes": 0,
                    "source_size_bytes": int(entry.get("size_bytes") or 0),
                })
            continue
        text = inspection.get("text")
        if isinstance(text, str) and "/" in text:
            issues.append(
                {
                    "code": "detail_loader_lexical_ambiguity",
                    "source_path": source_path,
                }
            )
            continue
        if isinstance(text, str) and _has_real_adapter_deferred_probes(text):
            present_paths.append(source_path)
    status = "present" if present_paths else "unverified"
    return {
        "status": status,
        "source_paths": sorted({str(entry["source_path"]) for entry in probes}),
        "matched_source_paths": sorted(set(present_paths)),
    }, issues


def _has_real_adapter_deferred_probes(text: str) -> bool:
    return bool(
        _deferred_probe_adapters(text, "resolve")
        & _deferred_probe_adapters(text, "reject")
    )


def _deferred_probe_adapters(text: str, settlement: str) -> set[str]:
    identifier = r"[A-Za-z_$][\w$]*"
    gap = r"[\s\S]{0,4096}?"
    chain = re.compile(
        rf"^[ \t]*(?:const|let)\s+(?P<deferred>{identifier})\s*=\s*"
        rf"deferred\w*\s*\(\s*\)\s*;{gap}"
        rf"^[ \t]*(?P<adapter>{identifier})\.loadDetail\.mockReturnValueOnce\s*"
        rf"\(\s*(?P=deferred)\.promise\s*\)\s*;{gap}"
        rf"^[ \t]*(?:const|let)\s+(?P<pending>{identifier})\s*=\s*{identifier}\."
        rf"(?:onRoute\w*|load\w*Detail|openDeepLink|handleDeepLink)\s*\([^;]*;{gap}"
        rf"^[ \t]*(?P=deferred)\.{settlement}\s*\([^;]*;{gap}"
        rf"^[ \t]*await\s+(?P=pending)\b",
        re.IGNORECASE | re.MULTILINE,
    )
    return {match.group("adapter") for match in chain.finditer(text)}


def _render_prompt(
    profile: str,
    review_question: str,
    sources: list[dict[str, Any]],
    status: str,
    issues: list[str],
    review_contracts: list[dict[str, Any]],
) -> str:
    lines = [
        "# External Review Prompt",
        _review_profile_marker(profile),
        "",
        "Before answering the review question, audit the bundle itself.",
        "",
        "Required reviewer behavior:",
        "1. List which files you inspected.",
        "2. Identify the authority level of the inspected files.",
        "3. Report missing or stale context before giving conclusions.",
        "4. Cite bundle file paths for every important claim.",
        "5. Return GO/NO-GO only after the context audit.",
        "",
        f"Bundle status: {status}",
        f"Review question: {review_question}",
        "",
        "Selected sources:",
    ]
    for entry in sources:
        lines.append(f"- {entry['bundle_path']} | role={entry['role']} | authority={entry['authority']} | why={entry['why'] or 'not stated'}")
    if issues:
        lines.extend(["", "Known blocking or context issues:"])
        lines.extend(f"- {issue}" for issue in issues)
    for contract in review_contracts:
        lines.extend(["", f"Executable review contract: {contract['contract_id']}"])
        if contract["contract_id"] == _AUTH_FAIL_CLOSED_CONTRACT_ID:
            inspection = contract["inspection"]
            if not inspection["complete"]:
                lines.append(
                    "Automated inspection incomplete; treat every affected "
                    "source as applicable and unverified."
                )
                for issue in inspection["issues"]:
                    lines.append(
                        f"- {issue['code']} | source={issue['source_path']}"
                    )
            if contract["findings"]:
                lines.append(
                    "Automated findings are review requirements, not a code verdict:"
                )
                for finding in contract["findings"]:
                    lines.append(
                        f"- {finding['code']} | source={finding['source_path']}"
                    )
            lines.extend(
                [
                    "",
                    "Required auth fail-closed probe:",
                    "- Reset module state, inject an empty OPENID, then perform a "
                    "fresh module load and invoke the exported handler.",
                    "- Use SDK-bound counters; helper-only or mock-only assertions "
                    "are not evidence.",
                    "- Required zero-call result: init=0, collection=0, read=0, "
                    "write=0, transaction=0.",
                    f"- Structured probe evidence: "
                    f"{contract['probe_evidence']['status']}.",
                ]
            )
            continue
        inspection = contract["inspection"]
        if not inspection["complete"]:
            lines.append(
                "Automated inspection incomplete; inspect every affected source "
                "before making a clean finding."
            )
            for issue in inspection["issues"]:
                lines.append(f"- {issue['code']} | source={issue['source_path']}")
        if contract["findings"]:
            lines.append("Automated findings are review requirements, not a code verdict:")
            for finding in contract["findings"]:
                lines.append(f"- {finding['code']} | source={finding['source_path']}")
        lines.append(
            "Deferred adapter probe evidence: "
            f"{contract['probe_evidence']['status']}."
        )
        lines.extend(["", "Required identity-detail response matrix:"])
        lines.append(
            "- Permit visible detail assignment only after both response-shape "
            "validation and requested-identity equality."
        )
        lines.extend(f"- {label}" for _, label in _DETAIL_LOADER_REQUIRED_MATRIX)
        lines.extend(
            [
                "",
                "Required real-adapter probes:",
                "- Use real adapter-controlled deferred promises at the earliest "
                "state-producing await.",
                "- Exercise both success and failure settlement before accepting "
                "the implementation.",
            ]
        )
    lines.extend([
        "",
        "Required output:",
        "- context_sufficient: yes | no",
        "- missing_context:",
        "- inspected_files:",
        "- major_risks:",
        "- recommendation: GO | NO-GO | NEEDS_MORE_CONTEXT",
        "- cited_basis:",
    ])
    return "\n".join(lines) + "\n"


def _review_profile_marker(profile: str) -> str:
    metadata = json.dumps(
        {"profile": profile},
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )
    return f"{_REVIEW_PROFILE_MARKER_PREFIX}{metadata}{_REVIEW_PROFILE_MARKER_SUFFIX}"


def _render_ledger(
    profile: str,
    review_question: str,
    sources: list[dict[str, Any]],
    missing_roles: list[str],
    issues: list[str],
) -> str:
    lines = [
        "# Context Ledger",
        "",
        f"Profile: {profile}",
        f"Decision needed: {review_question}",
        "",
        "Selected sources:",
    ]
    for entry in sources:
        lines.append(f"- {entry['bundle_path']} | role={entry['role']} | authority={entry['authority']} | sha256={entry['sha256']} | why={entry['why'] or 'not stated'}")
    lines.extend(["", "Omitted or missing relevant sources:"])
    if missing_roles:
        lines.extend(f"- required role missing: {role}" for role in missing_roles)
    else:
        lines.append("- none declared")
    lines.extend(["", "Known gaps:"])
    if issues:
        lines.extend(f"- {issue}" for issue in issues)
    else:
        lines.append("- none declared")
    return "\n".join(lines) + "\n"


def _render_redaction(sources: list[dict[str, Any]], issues: list[str]) -> str:
    sensitive = [issue for issue in issues if issue.startswith("sensitive_") or issue.startswith("forbidden_sensitive")]
    lines = [
        "# Redaction Report",
        "",
        f"Source files scanned: {len(sources)}",
        f"Sensitive issue count: {len(sensitive)}",
        "",
        "Policy: browser profiles, credentials, raw private transcripts, secrets, and local agent state are forbidden.",
    ]
    if sensitive:
        lines.extend(["", "Blocking sensitive findings:"])
        lines.extend(f"- {issue}" for issue in sensitive)
    return "\n".join(lines) + "\n"


def _render_verification(status: str, issues: list[str]) -> str:
    lines = [
        "# Verification",
        "",
        f"Bundle gate status: {status}",
        "Validator: manifest/ZIP bidirectional consistency and per-file sha256 checks.",
    ]
    if issues:
        lines.extend(["", "Issues:"])
        lines.extend(f"- {issue}" for issue in issues)
    return "\n".join(lines) + "\n"


def _trust_statement(status: str) -> str:
    if status == READY:
        return "Manifest, selected sources, required roles, redaction scan, and ZIP consistency are sufficient for external review."
    if status == INCOMPLETE:
        return "Bundle is inspectable, but declared required context is incomplete. External reviewer must ask for missing context."
    return "Bundle is blocked and must not be submitted to an external Web AI."


def _role_for_generated(path: str) -> str:
    return {
        PROMPT_NAME: "review_prompt",
        LEDGER_NAME: "context_ledger",
        REDACTION_NAME: "redaction_report",
        VERIFICATION_NAME: "verification",
    }.get(path, "generated")


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _safe_id(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9_.-]+", "-", str(value).strip()).strip("-._").lower()
    return slug or "external-review"
