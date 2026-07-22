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

from .backup_guard import default_runtime_dir


MANIFEST_NAME = "PACK_MANIFEST.json"
PROMPT_NAME = "REVIEW_PROMPT.md"
LEDGER_NAME = "CONTEXT_LEDGER.md"
REDACTION_NAME = "REDACTION_REPORT.md"
VERIFICATION_NAME = "VERIFICATION.md"

READY = "ready_for_review"
INCOMPLETE = "context_incomplete"
BLOCKED = "blocked"

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

    prompt_text = _render_prompt(review_question, source_entries, status, blocking_issues)
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
        "schema_version": 1,
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
            package_files = manifest.get("package_files")
            if not isinstance(package_files, list):
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
    }


def _looks_sensitive(raw: bytes) -> bool:
    if len(raw) > 2_000_000:
        return False
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        return False
    return any(pattern.search(text) for pattern in SENSITIVE_CONTENT_PATTERNS)


def _render_prompt(review_question: str, sources: list[dict[str, Any]], status: str, issues: list[str]) -> str:
    lines = [
        "# External Review Prompt",
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
        "Conditional async latest-wins review (apply only when the reviewed code contains an async latest-wins state handler; otherwise skip this section):",
        "- Identify the earliest await capable of producing page or application state.",
        "- Require deferred out-of-order success and deferred out-of-order failure or rejection probes at that earliest boundary. Downstream-only deferral is insufficient when an upstream await exists.",
        "- Fail the review if request ownership or generation is introduced below an upstream await. Warn when there are two or more awaits but tests control only the later await.",
        "- When a handler releases busy or lock in a finally block, require that every downstream Promise-returning `load*` or `refresh*` boundary that defines operation completion is awaited or returned.",
        "- Require a deferred probe at each such completion boundary. Downstream-only or mutation-only evidence is insufficient.",
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
