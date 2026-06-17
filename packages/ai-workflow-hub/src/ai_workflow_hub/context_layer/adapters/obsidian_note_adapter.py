"""Synthetic Obsidian markdown note adapter candidate.

This adapter reads only explicit markdown fixture paths. It does not scan a
real vault and notes are classified as USER_NOTE_LEAD, never VERIFIED_SOURCE.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
import re
from pathlib import Path
from typing import Any

try:
    import yaml
except Exception:  # pragma: no cover - yaml is already a project dependency.
    yaml = None

from .citation_integrity import USER_NOTE_LEAD

ALLOWLISTED_PROFILE = "paper_obsidian_allowlisted_note_pilot_report"
ALLOWLISTED_SCHEMA_VERSION = "1.0"
ALLOWLISTED_TASK_ID = "PAPER_OBSIDIAN_ALLOWLISTED_NOTE_PILOT_A1"


def _utc_now_text() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256_text(text: str) -> str:
    return f"sha256:{hashlib.sha256(text.encode('utf-8')).hexdigest()}"


def _sha256_bytes(data: bytes) -> str:
    return f"sha256:{hashlib.sha256(data).hexdigest()}"


def _split_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    if not text.startswith("---\n"):
        return {}, text
    _, frontmatter, body = text.split("---", 2)
    if yaml is None:
        return {}, body
    parsed = yaml.safe_load(frontmatter) or {}
    if not isinstance(parsed, dict):
        return {}, body
    return parsed, body


def _redact_excerpt(text: str, limit: int = 180) -> str:
    compact = re.sub(r"\s+", " ", text).strip()
    compact = re.sub(
        r"(paragraph_text|writelab_token)\s*:\s*\S+",
        "[REDACTED]",
        compact,
    )
    return compact[:limit]


def load_obsidian_note_fixture(path: str | Path) -> dict[str, Any]:
    """Load a synthetic markdown note fixture as a citation lead."""
    note_path = Path(path)
    text = note_path.read_text(encoding="utf-8")
    frontmatter, body = _split_frontmatter(text)
    citation_keys = sorted(set(re.findall(r"@([A-Za-z0-9:_-]+)", text)))
    links = sorted(set(re.findall(r"\[\[([^\]]+)\]\]", text)))

    return {
        "obsidian_status": "FIXTURE_ONLY",
        "source_level": USER_NOTE_LEAD,
        "note_title": frontmatter.get("title") or note_path.stem,
        "note_path": str(note_path),
        "frontmatter": frontmatter,
        "outbound_links": links,
        "citation_keys": citation_keys,
        "redacted_excerpt": _redact_excerpt(body),
        "paper_retrieval_evidence": {
            "source_id": frontmatter.get("note_id", note_path.stem),
            "source_type": "obsidian_note_fixture",
            "citation_key": citation_keys[0] if citation_keys else None,
            "note_path": str(note_path),
            "file_path": None,
            "snippet": _redact_excerpt(body),
            "retrieval_score": 0.75,
            "retrieved_at": frontmatter.get("updated_at"),
            "stale_status": "fresh",
            "source_level": USER_NOTE_LEAD,
            "privacy_level": "synthetic_note",
        },
        "human_required": False,
        "known_gaps": ["real Obsidian vault access requires explicit authorization"],
    }


def _blocked_allowlisted_report(
    *,
    generated_at: str,
    reasons: list[str],
    allowlist_count: int,
    note_path_present: bool,
    vault_path_present: bool = False,
    note_exists: bool = False,
) -> dict[str, Any]:
    return {
        "profile": ALLOWLISTED_PROFILE,
        "schema_version": ALLOWLISTED_SCHEMA_VERSION,
        "task_id": ALLOWLISTED_TASK_ID,
        "project_id": "dev-frame-opencode",
        "workflow_type": "paper",
        "generated_at": generated_at,
        "pilot_status": "BLOCKED",
        "validation_kind": "obsidian_allowlisted_note_metadata",
        "human_required": True,
        "reasons": reasons,
        "connection": {
            "vault_path_present": vault_path_present,
            "note_path_present": note_path_present,
            "allowlisted_note_path_present": note_path_present,
            "note_exists": note_exists,
            "allowlist_count": allowlist_count,
            "vault_scan_performed": False,
            "full_vault_scanned": False,
            "obsidian_app_opened": False,
            "attachments_read": False,
            "rag_executed": False,
            "uses_cloud": False,
        },
        "privacy_boundary": {
            "raw_note_persisted": False,
            "raw_note_path_persisted": False,
            "raw_title_persisted": False,
            "private_note_raw_persisted": False,
            "paragraph_text_persisted": False,
            "writelab_token_persisted": False,
        },
        "artifact_minimization": {
            "source_kind": "obsidian_allowlisted_note",
            "note_sha256": "",
            "note_size_bytes": 0,
            "note_bytes": 0,
            "note_path_fingerprint": "",
            "citation_key_count": 0,
            "outbound_link_count": 0,
            "link_count": 0,
            "heading_count": 0,
            "frontmatter_key_count": 0,
            "redaction_count": 0,
        },
        "final_acceptance_claimed": False,
        "paper_quality_acceptance": False,
        "live_ready_claimed": False,
        "production_ready": False,
        "real_pilot_completed": False,
    }


def build_obsidian_allowlisted_note_pilot_report(
    *,
    note_path: str | Path | None,
    allowlist_paths: list[str | Path] | None,
    vault_root: str | Path | None = None,
    command_name: str = "aihub paper obsidian-allowlisted-note-pilot",
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Build minimized evidence for one explicit allowlisted Obsidian note."""
    generated = generated_at or _utc_now_text()
    allowlist_paths = allowlist_paths or []
    vault = Path(vault_root).resolve() if vault_root is not None else None
    vault_path_present = vault.exists() if vault is not None else False
    if vault is not None and not vault_path_present:
        return _blocked_allowlisted_report(
            generated_at=generated,
            reasons=["vault_root_not_present"],
            allowlist_count=len(allowlist_paths),
            note_path_present=note_path is not None,
            vault_path_present=False,
        )
    if note_path is None:
        return _blocked_allowlisted_report(
            generated_at=generated,
            reasons=["missing_note_path"],
            allowlist_count=len(allowlist_paths),
            note_path_present=False,
            vault_path_present=vault_path_present,
        )

    candidate = Path(note_path).resolve()
    allowlist = {Path(path).resolve() for path in allowlist_paths}
    if vault is not None and not (
        candidate == vault or vault in candidate.parents
    ):
        return _blocked_allowlisted_report(
            generated_at=generated,
            reasons=["note_path_outside_vault"],
            allowlist_count=len(allowlist),
            note_path_present=True,
            vault_path_present=vault_path_present,
            note_exists=candidate.exists(),
        )
    if candidate not in allowlist:
        return _blocked_allowlisted_report(
            generated_at=generated,
            reasons=["note_path_not_allowlisted"],
            allowlist_count=len(allowlist),
            note_path_present=True,
            vault_path_present=vault_path_present,
            note_exists=candidate.exists(),
        )
    if candidate.suffix.lower() != ".md":
        return _blocked_allowlisted_report(
            generated_at=generated,
            reasons=["note_path_not_markdown"],
            allowlist_count=len(allowlist),
            note_path_present=True,
            vault_path_present=vault_path_present,
            note_exists=candidate.exists(),
        )
    if not candidate.exists():
        return _blocked_allowlisted_report(
            generated_at=generated,
            reasons=["note_path_not_readable"],
            allowlist_count=len(allowlist),
            note_path_present=True,
            vault_path_present=vault_path_present,
            note_exists=False,
        )
    try:
        raw_bytes = candidate.read_bytes()
        text = raw_bytes.decode("utf-8")
    except (OSError, UnicodeDecodeError):
        return _blocked_allowlisted_report(
            generated_at=generated,
            reasons=["note_path_not_readable"],
            allowlist_count=len(allowlist),
            note_path_present=True,
            vault_path_present=vault_path_present,
            note_exists=candidate.exists(),
        )
    frontmatter, body = _split_frontmatter(text)
    citation_keys = sorted(set(re.findall(r"@([A-Za-z0-9:_-]+)", text)))
    links = sorted(set(re.findall(r"\[\[([^\]]+)\]\]", text)))
    heading_count = len(re.findall(r"(?m)^#{1,6}\s+\S", text))
    redaction_count = len(
        re.findall(r"(paragraph_text|writelab_token)\s*:", body)
    )
    manifest = {
        "manifest_id": "paper-obsidian-allowlisted-note-evidence-manifest-a1",
        "schema_version": ALLOWLISTED_SCHEMA_VERSION,
        "task_id": ALLOWLISTED_TASK_ID,
        "producer": "dev-frame-opencode",
        "source_records": [
            {
                "source_type": "obsidian_allowlisted_note",
                "source_fingerprint": _sha256_bytes(raw_bytes),
                "privacy_level": "allowlisted_note_hash_only",
                "raw_payload_persisted": False,
            }
        ],
        "commands_run": [command_name],
        "raw_sensitive_fields_absent": True,
        "contains_private_note_raw": False,
        "contains_raw_note_path": False,
    }
    return {
        "profile": ALLOWLISTED_PROFILE,
        "schema_version": ALLOWLISTED_SCHEMA_VERSION,
        "task_id": ALLOWLISTED_TASK_ID,
        "project_id": "dev-frame-opencode",
        "workflow_type": "paper",
        "generated_at": generated,
        "pilot_status": "PASS_ALLOWLISTED_NOTE_METADATA",
        "validation_kind": "obsidian_allowlisted_note_metadata",
        "human_required": False,
        "reasons": [],
        "connection": {
            "vault_path_present": vault_path_present,
            "note_path_present": True,
            "allowlisted_note_path_present": True,
            "note_exists": True,
            "allowlist_count": len(allowlist),
            "vault_scan_performed": False,
            "full_vault_scanned": False,
            "obsidian_app_opened": False,
            "attachments_read": False,
            "rag_executed": False,
            "uses_cloud": False,
        },
        "privacy_boundary": {
            "raw_note_persisted": False,
            "raw_note_path_persisted": False,
            "raw_title_persisted": False,
            "private_note_raw_persisted": False,
            "paragraph_text_persisted": False,
            "writelab_token_persisted": False,
        },
        "artifact_minimization": {
            "source_kind": "obsidian_allowlisted_note",
            "note_sha256": _sha256_bytes(raw_bytes),
            "note_size_bytes": len(raw_bytes),
            "note_bytes": len(raw_bytes),
            "note_path_fingerprint": _sha256_text(str(candidate)),
            "citation_key_count": len(citation_keys),
            "outbound_link_count": len(links),
            "link_count": len(links),
            "heading_count": heading_count,
            "frontmatter_key_count": len(frontmatter),
            "redaction_count": redaction_count,
        },
        "evidence_manifest": manifest,
        "final_acceptance_claimed": False,
        "paper_quality_acceptance": False,
        "live_ready_claimed": False,
        "production_ready": False,
        "real_pilot_completed": False,
    }
