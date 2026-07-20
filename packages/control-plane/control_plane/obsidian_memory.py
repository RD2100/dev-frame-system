"""One governed Obsidian working-plan path for the Memory MVP.

``HANDOFF.md`` remains project authority. The Vault note is bounded working
guidance, and all mutation is delegated to the existing writeback lifecycle.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import stat
from datetime import datetime, timezone
from heapq import nlargest
from pathlib import Path
from typing import Any

import yaml

from .writeback import (
    WritebackError,
    load_writeback_proposal,
    read_bounded_workspace_file,
    resolve_writeback_proposal,
    safe_resolve_workspace_path,
    stage_writeback_proposal,
)

MEMORY_ROOT_ENV = "DEVFRAME_OBSIDIAN_MEMORY_ROOT"
HANDOFF_RELATIVE_PATH = "docs/status/HANDOFF.md"
MAX_PLAN_BYTES = 16_384
MAX_NOTE_BYTES = 32_768
MAX_PLAN_FILES = 64
PLAN_PROPOSAL_KIND = "obsidian_project_plan"

_PROJECT_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,127}$")
_VERSION_ID_RE = re.compile(r"^[0-9]{8}T[0-9]{12}Z$")
_SECRET_PATTERNS = (
    re.compile(
        r"-----BEGIN (?:RSA |EC |OPENSSH |ENCRYPTED )?PRIVATE KEY-----",
        re.IGNORECASE,
    ),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\b(?:sk|gh[opusr]|github_pat)[-_]?[A-Za-z0-9_-]{20,}\b"),
    re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{20,}\b", re.IGNORECASE),
    re.compile(
        r"[?&#;](?:api[_-]?key|access[_-]?token|auth[_-]?token|"
        r"client[_-]?secret|refresh[_-]?token|credentials?|"
        r"private[_-]?key|password|secret|token)\s*=\s*"
        r"[^&#\s]{8,}",
        re.IGNORECASE,
    ),
    re.compile(r"\bBearer\s+[A-Za-z0-9._~+/=-]{12,}\b", re.IGNORECASE),
    re.compile(
        r"(?im)(?:^|[{,])\s*(?:[-*+]\s+|export\s+|\$env:)?"
        r"[\"']?(?:[a-z0-9]+\s*[._-]\s*){0,4}"
        r"(?:api[_-]?key|access[_-]?token|"
        r"auth[_-]?token|client[_-]?secret|refresh[_-]?token|credentials?|"
        r"private[_-]?key|password|secret|token)[\"']?\s*[:=]\s*"
        r"(?:[\"'][^\"'\r\n]{8,}[\"']|[^\s#]{8,})"
    ),
)


def _contains_unsafe_control(value: str) -> bool:
    return any(
        (ord(char) < 0x20 and char not in {"\n", "\t"})
        or 0x7F <= ord(char) <= 0x9F
        for char in value
    )


class ObsidianMemoryError(Exception):
    """Raised when a project plan cannot safely enter or leave the Vault."""


def _is_link_or_reparse(path: Path) -> bool:
    try:
        if path.is_symlink():
            return True
        is_junction = getattr(path, "is_junction", None)
        if is_junction and is_junction():
            return True
        attributes = int(getattr(path.lstat(), "st_file_attributes", 0))
        return bool(attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400))
    except OSError:
        return True


def _plain_directory(value: str | Path, *, kind: str) -> Path:
    path = Path(value).expanduser()
    if _is_link_or_reparse(path):
        raise ObsidianMemoryError(f"{kind} must not be a link or reparse point")
    try:
        resolved = path.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise ObsidianMemoryError(f"{kind} is not accessible") from exc
    if not resolved.is_dir():
        raise ObsidianMemoryError(f"{kind} is not a directory")
    return resolved


def resolve_memory_root(vault_root: str | Path | None = None) -> Path:
    configured = str(vault_root or os.environ.get(MEMORY_ROOT_ENV) or "").strip()
    if not configured:
        raise ObsidianMemoryError(f"{MEMORY_ROOT_ENV} is required")
    root = _plain_directory(configured, kind="Obsidian Vault")
    obsidian_dir = root / ".obsidian"
    if not obsidian_dir.is_dir() or _is_link_or_reparse(obsidian_dir):
        raise ObsidianMemoryError("configured root is not a plain Obsidian Vault")
    return root


def _project_id(value: str) -> str:
    project = str(value or "").strip()
    if not _PROJECT_ID_RE.fullmatch(project):
        raise ObsidianMemoryError(
            "project_id must be lower-case and use only letters, digits, dot, underscore, or dash"
        )
    return project


def managed_plan_relative_path(
    project_id: str,
    source_sha256: str,
    plan_sha256: str,
    version_id: str,
) -> str:
    project = _project_id(project_id)
    if not re.fullmatch(r"[0-9a-f]{64}", source_sha256):
        raise ObsidianMemoryError("source_sha256 is invalid")
    if not re.fullmatch(r"[0-9a-f]{64}", plan_sha256):
        raise ObsidianMemoryError("plan_sha256 is invalid")
    if not _VERSION_ID_RE.fullmatch(version_id):
        raise ObsidianMemoryError("version_id is invalid")
    return (
        f"wiki/memories/{project}-now-"
        f"{source_sha256[:16]}-{version_id}-{plan_sha256[:16]}.md"
    )


def _read_bounded(
    root: Path,
    path: Path,
    *,
    max_bytes: int,
    kind: str,
) -> bytes:
    try:
        relative_path = path.relative_to(root).as_posix()
        return read_bounded_workspace_file(
            root,
            relative_path,
            max_bytes=max_bytes,
        )
    except (ValueError, WritebackError) as exc:
        raise ObsidianMemoryError(f"{kind} is unavailable") from exc


def _handoff_state(project_root: str | Path) -> tuple[Path, str, tuple[int, int]]:
    root = _plain_directory(project_root, kind="project root")
    try:
        handoff = safe_resolve_workspace_path(root, HANDOFF_RELATIVE_PATH)
    except WritebackError as exc:
        raise ObsidianMemoryError("HANDOFF.md is unavailable") from exc
    data = _read_bounded(root, handoff, max_bytes=1_000_000, kind="HANDOFF.md")
    try:
        root_state = root.stat()
    except OSError as exc:
        raise ObsidianMemoryError("project root identity is unavailable") from exc
    return root, hashlib.sha256(data).hexdigest(), (int(root_state.st_dev), int(root_state.st_ino))


def _validate_plan(value: str) -> str:
    if not isinstance(value, str):
        raise ObsidianMemoryError("plan_markdown must be a string")
    normalized = value.replace("\r\n", "\n")
    if "\r" in normalized:
        raise ObsidianMemoryError("plan_markdown contains invalid line endings")
    plan = normalized.strip()
    try:
        data = plan.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise ObsidianMemoryError("plan_markdown must be valid UTF-8") from exc
    if _contains_unsafe_control(plan):
        raise ObsidianMemoryError("plan_markdown contains unsafe control characters")
    if not plan or "\x00" in plan or len(data) > MAX_PLAN_BYTES:
        raise ObsidianMemoryError("plan_markdown is empty or exceeds the size limit")
    if any(pattern.search(plan) for pattern in _SECRET_PATTERNS):
        raise ObsidianMemoryError("plan contains a secret-like value")
    return plan


def _plan_note(
    project_id: str,
    plan: str,
    source_sha256: str,
) -> tuple[str, str, str]:
    plan_sha256 = hashlib.sha256(plan.encode("utf-8")).hexdigest()
    instant = datetime.now(timezone.utc)
    updated_at = instant.isoformat(timespec="microseconds")
    version_id = instant.strftime("%Y%m%dT%H%M%S%fZ")
    metadata = {
        "type": "devframe_working_plan",
        "project_id": project_id,
        "authority": "working_only",
        "status": "active",
        "source_path": HANDOFF_RELATIVE_PATH,
        "source_sha256": source_sha256,
        "plan_sha256": plan_sha256,
        "version_id": version_id,
        "updated_at": updated_at,
    }
    lines = ["---"]
    lines.extend(f"{key}: {json.dumps(value, ensure_ascii=False)}" for key, value in metadata.items())
    lines.extend(
        [
            "---",
            "",
            f"# {project_id} Working Plan",
            "",
            "> Working guidance only. `docs/status/HANDOFF.md` remains authoritative.",
            "",
            plan,
            "",
        ]
    )
    return "\n".join(lines), plan_sha256, version_id


def _prepare_project_plan(
    *,
    vault_root: str | Path | None,
    project_root: str | Path,
    project_id: str,
    plan_markdown: str,
) -> dict[str, Any]:
    project = _project_id(project_id)
    vault = resolve_memory_root(vault_root)
    project_root_path, source_sha256, _root_identity = _handoff_state(project_root)
    plan = _validate_plan(plan_markdown)
    note, plan_sha256, version_id = _plan_note(project, plan, source_sha256)
    return {
        "project_id": project,
        "project_root": project_root_path,
        "vault_root": vault,
        "relative_path": managed_plan_relative_path(
            project,
            source_sha256,
            plan_sha256,
            version_id,
        ),
        "contents": note,
        "source_sha256": source_sha256,
        "plan_sha256": plan_sha256,
        "version_id": version_id,
    }


def stage_project_plan(
    runtime_dir: str | Path,
    *,
    vault_root: str | Path | None,
    project_root: str | Path,
    project_id: str,
    plan_markdown: str,
    thread_id: str = "",
) -> dict[str, Any]:
    prepared = _prepare_project_plan(
        vault_root=vault_root,
        project_root=project_root,
        project_id=project_id,
        plan_markdown=plan_markdown,
    )
    try:
        staged = stage_writeback_proposal(
            runtime_dir,
            prepared["vault_root"],
            prepared["relative_path"],
            prepared["contents"],
            thread_id=thread_id,
            project_id=prepared["project_id"],
            max_bytes=MAX_NOTE_BYTES,
            redact_paths=True,
            create_only=True,
            proposal_kind=PLAN_PROPOSAL_KIND,
            source_preconditions=[
                {
                    "workspace_root": str(prepared["project_root"]),
                    "relative_path": HANDOFF_RELATIVE_PATH,
                    "sha256": prepared["source_sha256"],
                }
            ],
        )
    except WritebackError as exc:
        raise ObsidianMemoryError(str(exc)) from exc
    return {
        "request_id": staged["request_id"],
        "project_id": prepared["project_id"],
        "relative_path": prepared["relative_path"],
        "operation": staged["preview"]["operation"],
        "bytes": staged["preview"]["bytes"],
        "source_sha256": prepared["source_sha256"],
        "plan_sha256": prepared["plan_sha256"],
        "version_id": prepared["version_id"],
    }


def _validate_project_plan_proposal(proposal: dict[str, Any]) -> tuple[str, str]:
    if proposal.get("proposal_kind") != PLAN_PROPOSAL_KIND:
        raise ObsidianMemoryError("request is not a project plan proposal")
    if proposal.get("create_only") is not True or proposal.get("redact_paths") is not True:
        raise ObsidianMemoryError("project plan proposal publication policy is invalid")
    project = _project_id(str(proposal.get("project_id") or ""))
    preconditions = proposal.get("source_preconditions")
    if (
        not isinstance(preconditions, list)
        or len(preconditions) != 1
        or not isinstance(preconditions[0], dict)
    ):
        raise ObsidianMemoryError("project plan source precondition is invalid")
    contents = proposal.get("contents")
    if not isinstance(contents, str):
        raise ObsidianMemoryError("project plan proposal contents are invalid")
    try:
        contents_bytes = contents.encode("utf-8")
    except UnicodeError as exc:
        raise ObsidianMemoryError("project plan proposal contents are not valid UTF-8") from exc
    _metadata, _plan, source_sha256, plan_sha256, version_id = _validate_managed_note(
        contents_bytes,
        project,
    )
    if source_sha256 != preconditions[0].get("sha256"):
        raise ObsidianMemoryError("project plan proposal source binding is invalid")
    expected_path = managed_plan_relative_path(
        project,
        source_sha256,
        plan_sha256,
        version_id,
    )
    if proposal.get("relative_path") != expected_path:
        raise ObsidianMemoryError("project plan proposal target is invalid")
    return project, expected_path


def approve_project_plan(
    runtime_dir: str | Path,
    request_id: str,
    *,
    confirm: bool,
    expected_thread_id: str | None = None,
) -> dict[str, Any]:
    try:
        proposal = load_writeback_proposal(runtime_dir, request_id)
    except WritebackError as exc:
        raise ObsidianMemoryError(str(exc)) from exc
    if proposal is None:
        raise ObsidianMemoryError("project plan proposal not found")
    project, expected_path = _validate_project_plan_proposal(proposal)
    status = str(proposal.get("status") or "")
    if status == "applied":
        try:
            verified = resolve_writeback_proposal(
                runtime_dir,
                request_id,
                "approve",
                expected_thread_id=expected_thread_id,
                proposal_validator=_validate_project_plan_proposal,
            )
        except WritebackError as exc:
            raise ObsidianMemoryError(str(exc)) from exc
        if verified.get("status") != "applied":
            raise ObsidianMemoryError("project plan proposal could not be verified as applied")
        return {
            "applied": False,
            "humanRequired": False,
            "alreadyResolved": True,
            "status": "applied",
            "requestId": request_id,
            "projectId": project,
            "relativePath": expected_path,
        }
    if status != "pending":
        raise ObsidianMemoryError(f"project plan proposal is already {status or 'invalid'}")
    if not confirm:
        return {
            "applied": False,
            "humanRequired": True,
            "status": "pending",
            "requestId": request_id,
            "projectId": project,
            "relativePath": expected_path,
        }
    try:
        result = resolve_writeback_proposal(
            runtime_dir,
            request_id,
            "approve",
            expected_thread_id=expected_thread_id,
            proposal_validator=_validate_project_plan_proposal,
        )
    except WritebackError as exc:
        raise ObsidianMemoryError(str(exc)) from exc
    if not result.get("applied"):
        result_status = str(result.get("status") or "not_applied")
        if result.get("already_resolved") and result_status == "applied":
            return {
                "applied": False,
                "humanRequired": False,
                "alreadyResolved": True,
                "status": "applied",
                "requestId": request_id,
                "projectId": project,
                "relativePath": expected_path,
            }
        raise ObsidianMemoryError(f"project plan proposal was not applied: {result_status}")
    return {
        "applied": bool(result.get("applied")),
        "humanRequired": False,
        "alreadyResolved": False,
        "status": "applied",
        "requestId": request_id,
        "projectId": project,
        "relativePath": expected_path,
        "operation": result.get("operation", "created"),
        "bytes": result.get("bytes_written", 0),
    }


def _parse_note(data: bytes) -> tuple[dict[str, Any], str]:
    try:
        text = data.decode("utf-8")
    except UnicodeError as exc:
        raise ObsidianMemoryError("managed plan is not valid UTF-8") from exc
    text = text.replace("\r\n", "\n")
    if "\r" in text:
        raise ObsidianMemoryError("managed plan contains invalid line endings")
    if "\x00" in text or not text.startswith("---\n"):
        raise ObsidianMemoryError("managed plan format is invalid")
    end = text.find("\n---\n", 4)
    if end < 0 or end > 8_192:
        raise ObsidianMemoryError("managed plan frontmatter is invalid")
    try:
        metadata = yaml.safe_load(text[4:end])
    except yaml.YAMLError as exc:
        raise ObsidianMemoryError("managed plan frontmatter is invalid") from exc
    if not isinstance(metadata, dict):
        raise ObsidianMemoryError("managed plan frontmatter is invalid")
    body = text[end + 5 :].strip()
    marker = "Working guidance only. `docs/status/HANDOFF.md` remains authoritative."
    expected_header = f"# {metadata.get('project_id')} Working Plan\n\n> {marker}\n\n"
    if not body.startswith(expected_header):
        raise ObsidianMemoryError("managed plan body header is invalid")
    body = body[len(expected_header) :].strip()
    return metadata, body


def _validate_managed_note(
    data: bytes,
    project: str,
) -> tuple[dict[str, Any], str, str, str, str]:
    metadata, plan = _parse_note(data)
    required_metadata = {
        "type": "devframe_working_plan",
        "project_id": project,
        "authority": "working_only",
        "status": "active",
        "source_path": HANDOFF_RELATIVE_PATH,
    }
    if any(metadata.get(key) != value for key, value in required_metadata.items()):
        raise ObsidianMemoryError("managed plan metadata is invalid")
    if not plan or len(plan.encode("utf-8")) > MAX_PLAN_BYTES:
        raise ObsidianMemoryError("managed plan body exceeds the size limit")
    if _contains_unsafe_control(plan):
        raise ObsidianMemoryError("managed plan contains unsafe control characters")
    if any(pattern.search(plan) for pattern in _SECRET_PATTERNS):
        raise ObsidianMemoryError("managed plan contains a secret-like value")
    plan_sha256 = hashlib.sha256(plan.encode("utf-8")).hexdigest()
    source_sha256 = str(metadata.get("source_sha256") or "")
    if not re.fullmatch(r"[0-9a-f]{64}", source_sha256):
        raise ObsidianMemoryError("managed plan source hash is invalid")
    if metadata.get("plan_sha256") != plan_sha256:
        raise ObsidianMemoryError("managed plan body hash is invalid")
    updated_at = str(metadata.get("updated_at") or "")
    try:
        instant = datetime.fromisoformat(updated_at)
    except ValueError as exc:
        raise ObsidianMemoryError("managed plan updated_at is invalid") from exc
    if instant.tzinfo is None:
        raise ObsidianMemoryError("managed plan updated_at must include a timezone")
    canonical_updated_at = instant.astimezone(timezone.utc).isoformat(timespec="microseconds")
    version_id = instant.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    if updated_at != canonical_updated_at or metadata.get("version_id") != version_id:
        raise ObsidianMemoryError("managed plan version metadata is invalid")
    return metadata, plan, source_sha256, plan_sha256, version_id


def recall_project_plan(
    *,
    vault_root: str | Path | None,
    project_root: str | Path,
    project_id: str,
) -> dict[str, Any]:
    project = _project_id(project_id)
    vault = resolve_memory_root(vault_root)
    try:
        memory_dir = safe_resolve_workspace_path(vault, "wiki/memories")
    except WritebackError as exc:
        raise ObsidianMemoryError("managed plan directory is unsafe") from exc
    if not memory_dir.exists():
        return {
            "projectId": project,
            "status": "missing",
            "authority": "untrusted_guidance_only",
            "relativePath": "",
            "plan": "",
        }
    if not memory_dir.is_dir() or _is_link_or_reparse(memory_dir):
        raise ObsidianMemoryError("managed plan directory is unavailable")
    if next(memory_dir.glob(f"{project}-now-*.md"), None) is None:
        return {
            "projectId": project,
            "status": "missing",
            "authority": "untrusted_guidance_only",
            "relativePath": "",
            "plan": "",
        }
    root, current_source_sha256, root_identity = _handoff_state(project_root)
    candidates = nlargest(
        MAX_PLAN_FILES,
        memory_dir.glob(f"{project}-now-{current_source_sha256[:16]}-*.md"),
        key=lambda path: path.name,
    )
    if not candidates:
        return {
            "projectId": project,
            "status": "stale",
            "reason": "source_changed",
            "authority": "untrusted_guidance_only",
            "relativePath": "",
            "currentSourceSha256": current_source_sha256,
            "plan": "",
        }
    current: list[tuple[str, str, bytes, str, str]] = []
    saw_stale_source = False
    for target in candidates:
        relative_path = target.relative_to(vault).as_posix()
        try:
            resolved = safe_resolve_workspace_path(vault, relative_path)
        except WritebackError as exc:
            raise ObsidianMemoryError("managed plan path is unsafe") from exc
        if resolved != target.resolve():
            raise ObsidianMemoryError("managed plan path changed during recall")
        data = _read_bounded(
            vault,
            target,
            max_bytes=MAX_NOTE_BYTES,
            kind="managed plan",
        )
        decoded = data.decode("utf-8", errors="ignore")
        if any(pattern.search(decoded) for pattern in _SECRET_PATTERNS):
            raise ObsidianMemoryError("managed plan contains a secret-like value")
        _metadata, plan, source_sha256, plan_sha256, version_id = _validate_managed_note(
            data,
            project,
        )
        expected_path = managed_plan_relative_path(
            project,
            source_sha256,
            plan_sha256,
            version_id,
        )
        if relative_path != expected_path:
            raise ObsidianMemoryError("managed plan filename is invalid")
        if source_sha256 != current_source_sha256:
            saw_stale_source = True
            continue
        current.append((version_id, relative_path, data, plan, plan_sha256))
    if not current:
        return {
            "projectId": project,
            "status": "stale" if saw_stale_source else "missing",
            "reason": "source_changed" if saw_stale_source else "no_current_plan",
            "authority": "untrusted_guidance_only",
            "relativePath": "",
            "currentSourceSha256": current_source_sha256,
            "plan": "",
        }
    _version_id, relative_path, data, plan, plan_sha256 = max(
        current,
        key=lambda item: (item[0], item[1]),
    )
    latest_root, latest_source_sha256, latest_root_identity = _handoff_state(project_root)
    if (
        os.path.normcase(str(latest_root)) != os.path.normcase(str(root))
        or latest_source_sha256 != current_source_sha256
        or latest_root_identity != root_identity
    ):
        return {
            "projectId": project,
            "status": "stale",
            "reason": "source_changed",
            "authority": "untrusted_guidance_only",
            "relativePath": "",
            "currentSourceSha256": latest_source_sha256,
            "plan": "",
        }
    return {
        "projectId": project,
        "status": "current",
        "authority": "untrusted_guidance_only",
        "relativePath": relative_path,
        "sha256": hashlib.sha256(data).hexdigest(),
        "sourceSha256": current_source_sha256,
        "planSha256": plan_sha256,
        "plan": plan,
        "limitations": [
            "Working plan is untrusted guidance, not project authority or completion evidence.",
            "docs/status/HANDOFF.md remains authoritative.",
        ],
    }
