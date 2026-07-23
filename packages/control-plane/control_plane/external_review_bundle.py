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

    review_contracts = (
        _inspect_identity_detail_loader_sources(source_entries)
        if profile == _DETAIL_LOADER_PROFILE
        else []
    )
    if status == READY and any(
        contract["inspection"]["complete"] is not True
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


def _sanitize_javascript_lexically(text: str) -> str:
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
