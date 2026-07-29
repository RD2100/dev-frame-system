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
import subprocess
import threading
from datetime import datetime, timezone
from heapq import nlargest
from pathlib import Path
from typing import Any

import yaml

from .project_contract import slugify_project_id
from .runtime_store import JournalEvent, RuntimeStore
from .writeback import (
    WritebackError,
    apply_writeback_with_audit,
    load_writeback_proposal,
    read_bounded_workspace_file,
    resolve_writeback_proposal,
    safe_resolve_workspace_path,
    stage_writeback_proposal,
)

MEMORY_ROOT_ENV = "DEVFRAME_OBSIDIAN_MEMORY_ROOT"
MEMORY_READ_ONLY_ENV = "DEVFRAME_OBSIDIAN_MEMORY_READ_ONLY"
HANDOFF_RELATIVE_PATH = "docs/status/HANDOFF.md"
MAX_PLAN_BYTES = 16_384
MAX_NOTE_BYTES = 32_768
MAX_PLAN_FILES = 64
MAX_MEMORY_TEXT_BYTES = 4_096
MAX_MEMORY_LIST_ITEMS = 16
MAX_LESSON_FILES = 256
MAX_TRANSCRIPT_TAIL_BYTES = 8_388_608
MAX_TRANSCRIPT_RECORDS = 20_000
PLAN_PROPOSAL_KIND = "obsidian_project_plan"
GLOBAL_PROMOTION_PROPOSAL_KIND = "obsidian_global_playbook_promotion"
GIT_ROOT_TIMEOUT_SECONDS = 3

_PROJECT_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,127}$")
_VERSION_ID_RE = re.compile(r"^[0-9]{8}T[0-9]{12}Z$")
_MEMORY_ID_RE = re.compile(r"^[0-9a-f]{64}$")
_TRIGGER_RE = re.compile(r"^[A-Za-z0-9._-]{1,32}$")
_MEMORY_CREATE_LOCK = threading.RLock()
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


def memory_writes_disabled() -> bool:
    return str(os.environ.get(MEMORY_READ_ONLY_ENV) or "").strip().casefold() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _require_memory_writable() -> None:
    if memory_writes_disabled():
        raise ObsidianMemoryError("Obsidian memory is read-only")


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


def _project_root_key(path: Path) -> str:
    normalized = os.path.normpath(str(path))
    return normalized.casefold() if os.name == "nt" else normalized


def _session_cwd(value: str | Path) -> Path:
    candidate = Path(value).expanduser()
    if not candidate.is_absolute():
        raise ObsidianMemoryError("session cwd must be an absolute local path")
    return _plain_directory(candidate, kind="session cwd")


def _git_project_root(cwd: Path) -> Path:
    try:
        result = subprocess.run(
            ["git", "-C", str(cwd), "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=GIT_ROOT_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return cwd
    output = result.stdout.rstrip("\r\n")
    if (
        result.returncode != 0
        or not output
        or len(output) > 32_768
        or "\r" in output
        or "\n" in output
        or "\x00" in output
    ):
        return cwd
    candidate = Path(output)
    if not candidate.is_absolute():
        return cwd
    try:
        root = _plain_directory(candidate, kind="Git project root")
        cwd.relative_to(root)
    except (ObsidianMemoryError, ValueError):
        return cwd
    return root


def _registered_project_roots(
    runtime_dir: str | Path,
) -> tuple[dict[str, tuple[str, int]], dict[str, str]]:
    try:
        events = RuntimeStore(runtime_dir=runtime_dir).read_all()
    except OSError as exc:
        raise ObsidianMemoryError("project registry is unavailable") from exc
    by_id: dict[str, tuple[str, int]] = {}
    for index, event in enumerate(events):
        if event.get("event_type") != "project_registered":
            continue
        project = str(event.get("project_id") or "").strip()
        payload = event.get("payload")
        root_value = payload.get("project_root") if isinstance(payload, dict) else ""
        if not _PROJECT_ID_RE.fullmatch(project) or not str(root_value or "").strip():
            continue
        candidate = Path(str(root_value)).expanduser()
        if not candidate.is_absolute():
            continue
        try:
            root_key = _project_root_key(candidate.resolve(strict=False))
        except (OSError, RuntimeError):
            continue
        by_id[project] = (root_key, index)
    by_root: dict[str, str] = {}
    for project, (root_key, _index) in sorted(
        by_id.items(),
        key=lambda item: item[1][1],
    ):
        by_root[root_key] = project
    return by_id, by_root


def _new_project_id(root: Path, by_id: dict[str, tuple[str, int]]) -> str:
    root_key = _project_root_key(root)
    digest = hashlib.sha256(root_key.encode("utf-8")).hexdigest()
    base = slugify_project_id(root)[:96] or "project"
    for suffix_length in range(12, len(digest) + 1, 4):
        suffix = digest[:suffix_length]
        prefix = base[: 127 - len(suffix)].rstrip("-") or "project"
        candidate = f"{prefix}-{suffix}"
        registered = by_id.get(candidate)
        if registered is None or registered[0] == root_key:
            return candidate
    raise ObsidianMemoryError("project identity collision could not be resolved")


def resolve_session_project(
    *,
    cwd: str | Path,
    runtime_dir: str | Path,
) -> dict[str, Any]:
    """Resolve and idempotently register one local SessionStart project."""
    session_cwd = _session_cwd(cwd)
    project_root = _git_project_root(session_cwd)
    root_key = _project_root_key(project_root)
    by_id, by_root = _registered_project_roots(runtime_dir)
    project = by_root.get(root_key)
    if project:
        return {
            "projectId": project,
            "projectRoot": str(project_root),
            "registered": False,
        }
    project = _new_project_id(project_root, by_id)
    try:
        RuntimeStore(runtime_dir=runtime_dir).append(
            JournalEvent(
                event_type="project_registered",
                project_id=project,
                payload={
                    "project_root": str(project_root),
                    "priority": 3,
                    "registration_source": "obsidian_session_start",
                },
            )
        )
    except OSError as exc:
        raise ObsidianMemoryError("project registry is unavailable") from exc
    return {
        "projectId": project,
        "projectRoot": str(project_root),
        "registered": True,
    }


def recall_session_project_plan(
    runtime_dir: str | Path,
    *,
    vault_root: str | Path | None,
    cwd: str | Path,
) -> dict[str, Any]:
    """Fail-open SessionStart adapter over project registration and recall."""
    try:
        context = resolve_session_project(cwd=cwd, runtime_dir=runtime_dir)
    except ObsidianMemoryError:
        return {
            "projectId": "",
            "status": "unavailable",
            "reason": "project_unavailable",
            "authority": "untrusted_guidance_only",
            "relativePath": "",
            "plan": "",
        }
    project = str(context["projectId"])
    try:
        recalled = recall_project_plan(
            vault_root=vault_root,
            project_root=str(context["projectRoot"]),
            project_id=project,
        )
    except ObsidianMemoryError:
        return {
            "projectId": project,
            "status": "unavailable",
            "reason": "memory_unavailable",
            "authority": "untrusted_guidance_only",
            "relativePath": "",
            "plan": "",
        }
    result = dict(recalled)
    if result.get("status") == "missing" and not result.get("reason"):
        result["reason"] = "no_current_plan"
    return result


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
    _require_memory_writable()
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
    _require_memory_writable()
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


def _registered_project(
    runtime_dir: str | Path,
    project_root: str | Path,
    project_id: str,
) -> tuple[str, Path]:
    project = _project_id(project_id)
    root = _plain_directory(project_root, kind="project root")
    by_id, _by_root = _registered_project_roots(runtime_dir)
    registered = by_id.get(project)
    if registered is None or registered[0] != _project_root_key(root):
        raise ObsidianMemoryError("project identity does not match the registered root")
    return project, root


def _validated_memory_text(
    value: Any,
    *,
    field: str,
    max_bytes: int = MAX_MEMORY_TEXT_BYTES,
    required: bool = False,
) -> str:
    if value is None and not required:
        return ""
    if not isinstance(value, str):
        raise ObsidianMemoryError(f"{field} must be a string")
    normalized = value.replace("\r\n", "\n")
    if "\r" in normalized:
        raise ObsidianMemoryError(f"{field} contains invalid line endings")
    text = normalized.strip()
    try:
        data = text.encode("utf-8")
    except UnicodeError as exc:
        raise ObsidianMemoryError(f"{field} must be valid UTF-8") from exc
    if (required and not text) or len(data) > max_bytes:
        raise ObsidianMemoryError(f"{field} is empty or exceeds the size limit")
    if _contains_unsafe_control(text):
        raise ObsidianMemoryError(f"{field} contains unsafe control characters")
    if text and any(pattern.search(text) for pattern in _SECRET_PATTERNS):
        raise ObsidianMemoryError(f"{field} contains a secret-like value")
    return text


def _validated_memory_list(
    value: Any,
    *,
    field: str,
    max_item_bytes: int = 1_024,
) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list) or len(value) > MAX_MEMORY_LIST_ITEMS:
        raise ObsidianMemoryError(f"{field} must be a bounded string list")
    return [
        _validated_memory_text(
            item,
            field=f"{field}[{index}]",
            max_bytes=max_item_bytes,
            required=True,
        )
        for index, item in enumerate(value)
    ]


def _idempotency_digest(project: str, kind: str, key: Any) -> str:
    if not isinstance(key, str):
        raise ObsidianMemoryError("idempotency_key must be a string")
    normalized = key.strip()
    try:
        data = normalized.encode("utf-8")
    except UnicodeError as exc:
        raise ObsidianMemoryError("idempotency_key must be valid UTF-8") from exc
    if not normalized or len(data) > 512 or _contains_unsafe_control(normalized):
        raise ObsidianMemoryError("idempotency_key is empty or exceeds the size limit")
    return hashlib.sha256(
        b"devframe-memory-v1\0"
        + project.encode("utf-8")
        + b"\0"
        + kind.encode("ascii")
        + b"\0"
        + data
    ).hexdigest()


def _metadata_note(metadata: dict[str, Any], body_lines: list[str]) -> str:
    lines = ["---"]
    lines.extend(
        f"{key}: {json.dumps(value, ensure_ascii=False)}"
        for key, value in metadata.items()
    )
    lines.extend(["---", "", *body_lines, ""])
    note = "\n".join(lines)
    try:
        data = note.encode("utf-8")
    except UnicodeError as exc:
        raise ObsidianMemoryError("managed memory note must be valid UTF-8") from exc
    if len(data) > MAX_NOTE_BYTES:
        raise ObsidianMemoryError("managed memory note exceeds the size limit")
    if _contains_unsafe_control(note):
        raise ObsidianMemoryError("managed memory note contains unsafe control characters")
    if any(pattern.search(note) for pattern in _SECRET_PATTERNS):
        raise ObsidianMemoryError("managed memory note contains a secret-like value")
    return note


def _checkpoint_relative_path(project: str, memory_id: str) -> str:
    if not _MEMORY_ID_RE.fullmatch(memory_id):
        raise ObsidianMemoryError("checkpoint memory id is invalid")
    return (
        "wiki/memories/devframe-agent/projects/"
        f"{project}/checkpoints/{memory_id}.md"
    )


def _lesson_relative_path(project: str, memory_id: str) -> str:
    if not _MEMORY_ID_RE.fullmatch(memory_id):
        raise ObsidianMemoryError("lesson memory id is invalid")
    return (
        "wiki/memories/devframe-agent/projects/"
        f"{project}/lessons/{memory_id}.md"
    )


def _global_playbook_relative_path(project: str, lesson_id: str) -> str:
    if not _MEMORY_ID_RE.fullmatch(lesson_id):
        raise ObsidianMemoryError("lesson memory id is invalid")
    return (
        "wiki/memories/devframe-agent/global-playbooks/"
        f"{project}-{lesson_id}.md"
    )


def _memory_payload_sha256(payload: dict[str, Any]) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _checkpoint_note(
    *,
    project: str,
    memory_id: str,
    session_id: str,
    trigger: str,
    goal: str,
    decisions: list[str],
    failed_attempts: list[str],
    verification: list[str],
    blockers: list[str],
    next_action: str,
) -> str:
    payload = {
        "goal": goal,
        "decisions": decisions,
        "failed_attempts": failed_attempts,
        "verification": verification,
        "blockers": blockers,
        "next_action": next_action,
    }
    session_digest = hashlib.sha256(
        ("devframe-session-v1\0" + session_id).encode("utf-8")
    ).hexdigest()
    metadata = {
        "type": "devframe_session_checkpoint",
        "project_id": project,
        "authority": "private_untrusted_guidance",
        "status": "active",
        "memory_id": memory_id,
        "session_sha256": session_digest,
        "trigger": trigger,
        "payload_sha256": _memory_payload_sha256(payload),
    }
    body = [
        f"# {project} Session Checkpoint",
        "",
        "> Private untrusted guidance only. Repository authority and evidence win.",
        "",
        "## Goal",
        "",
        goal or "_No bounded goal captured._",
    ]
    for title, values in (
        ("Decisions", decisions),
        ("Failed Attempts", failed_attempts),
        ("Verification", verification),
        ("Blockers", blockers),
    ):
        if values:
            body.extend(["", f"## {title}", "", *(f"- {item}" for item in values)])
    body.extend(
        [
            "",
            "## Next Action",
            "",
            next_action or "_No bounded next action captured._",
        ]
    )
    return _metadata_note(metadata, body)


def _create_immutable_memory_note(
    runtime_dir: str | Path,
    *,
    vault: Path,
    project: str,
    kind: str,
    memory_id: str,
    relative_path: str,
    contents: str,
) -> dict[str, Any]:
    _require_memory_writable()
    expected = contents.encode("utf-8")
    action_id = f"obsidian-{kind}-{memory_id[:24]}"
    with _MEMORY_CREATE_LOCK:
        try:
            result = apply_writeback_with_audit(
                vault,
                relative_path,
                contents,
                runtime_dir=runtime_dir,
                action_id=action_id,
                confirm=True,
                max_bytes=MAX_NOTE_BYTES,
                create_only=True,
                audit_fields={
                    "kind": "obsidian_memory_create",
                    "memory_kind": kind,
                    "memory_id": memory_id,
                    "project_id": project,
                },
            )
        except WritebackError as exc:
            try:
                existing = read_bounded_workspace_file(
                    vault,
                    relative_path,
                    max_bytes=MAX_NOTE_BYTES,
                )
            except WritebackError as read_exc:
                raise ObsidianMemoryError(
                    "managed memory path is unsafe or unavailable"
                ) from read_exc
            if existing != expected:
                raise ObsidianMemoryError(
                    "idempotency conflict: an immutable memory already exists"
                ) from exc
            if not _matching_memory_audit(
                runtime_dir,
                action_id=action_id,
                project=project,
                kind=kind,
                memory_id=memory_id,
                relative_path=relative_path,
                contents_sha256=hashlib.sha256(expected).hexdigest(),
                byte_count=len(expected),
            ):
                raise ObsidianMemoryError(
                    "idempotency conflict: existing memory has no matching audit"
                ) from exc
            return {
                "projectId": project,
                "memoryId": memory_id,
                "kind": kind,
                "created": False,
                "duplicate": True,
                "bytes": len(expected),
            }
    return {
        "projectId": project,
        "memoryId": memory_id,
        "kind": kind,
        "created": True,
        "duplicate": False,
        "bytes": int(result.get("bytes_written") or len(expected)),
    }


def _matching_memory_audit(
    runtime_dir: str | Path,
    *,
    action_id: str,
    project: str,
    kind: str,
    memory_id: str,
    relative_path: str,
    contents_sha256: str,
    byte_count: int,
) -> bool:
    directory = Path(runtime_dir).resolve() / "writeback-runs" / action_id
    try:
        candidates = sorted(directory.glob("*.json"))
    except OSError:
        return False
    if len(candidates) > 16:
        return False
    for audit_path in candidates:
        try:
            audit = json.loads(audit_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            continue
        if not isinstance(audit, dict):
            continue
        expected = {
            "applied": True,
            "action_id": action_id,
            "kind": "obsidian_memory_create",
            "memory_kind": kind,
            "memory_id": memory_id,
            "project_id": project,
            "relative_path": relative_path,
            "operation": "created",
            "contents_sha256": contents_sha256,
            "bytes_written": byte_count,
        }
        if all(audit.get(key) == value for key, value in expected.items()):
            return True
    return False


def capture_project_checkpoint(
    runtime_dir: str | Path,
    *,
    vault_root: str | Path | None,
    project_root: str | Path,
    project_id: str,
    idempotency_key: str,
    session_id: str,
    trigger: str,
    goal: str,
    decisions: list[str] | None,
    failed_attempts: list[str] | None,
    verification: list[str] | None,
    blockers: list[str] | None,
    next_action: str,
) -> dict[str, Any]:
    _require_memory_writable()
    project, _root = _registered_project(runtime_dir, project_root, project_id)
    vault = resolve_memory_root(vault_root)
    memory_id = _idempotency_digest(project, "checkpoint", idempotency_key)
    normalized_session = _validated_memory_text(
        session_id,
        field="session_id",
        max_bytes=512,
        required=True,
    )
    normalized_trigger = str(trigger or "").strip()
    if not _TRIGGER_RE.fullmatch(normalized_trigger):
        raise ObsidianMemoryError("checkpoint trigger is invalid")
    normalized_goal = _validated_memory_text(
        goal,
        field="goal",
        max_bytes=2_048,
    )
    normalized_decisions = _validated_memory_list(decisions, field="decisions")
    normalized_failed = _validated_memory_list(
        failed_attempts,
        field="failed_attempts",
    )
    normalized_verification = _validated_memory_list(
        verification,
        field="verification",
    )
    normalized_blockers = _validated_memory_list(blockers, field="blockers")
    normalized_next = _validated_memory_text(
        next_action,
        field="next_action",
        max_bytes=2_048,
    )
    if not (
        normalized_goal
        or normalized_decisions
        or normalized_failed
        or normalized_verification
        or normalized_blockers
        or normalized_next
    ):
        raise ObsidianMemoryError("checkpoint contains no bounded signal")
    note = _checkpoint_note(
        project=project,
        memory_id=memory_id,
        session_id=normalized_session,
        trigger=normalized_trigger,
        goal=normalized_goal,
        decisions=normalized_decisions,
        failed_attempts=normalized_failed,
        verification=normalized_verification,
        blockers=normalized_blockers,
        next_action=normalized_next,
    )
    return _create_immutable_memory_note(
        runtime_dir,
        vault=vault,
        project=project,
        kind="session_checkpoint",
        memory_id=memory_id,
        relative_path=_checkpoint_relative_path(project, memory_id),
        contents=note,
    )


def _lesson_note(
    *,
    project: str,
    memory_id: str,
    title: str,
    lesson: str,
    evidence: list[str],
    tags: list[str],
    global_candidate: bool,
) -> str:
    payload = {
        "title": title,
        "lesson": lesson,
        "evidence": evidence,
        "tags": tags,
        "global_candidate": global_candidate,
    }
    metadata = {
        "type": "devframe_project_lesson",
        "project_id": project,
        "authority": "private_untrusted_guidance",
        "status": "active",
        "memory_id": memory_id,
        "title": title,
        "lesson": lesson,
        "evidence": evidence,
        "tags": tags,
        "global_candidate": global_candidate,
        "payload_sha256": _memory_payload_sha256(payload),
    }
    body = [
        f"# {title}",
        "",
        "> Project-scoped private untrusted guidance only.",
        "",
        "## Lesson",
        "",
        lesson,
    ]
    if evidence:
        body.extend(["", "## Evidence", "", *(f"- {item}" for item in evidence)])
    if tags:
        body.extend(["", "## Tags", "", ", ".join(tags)])
    if global_candidate:
        body.extend(
            [
                "",
                "## Promotion",
                "",
                "Candidate only. Global publication requires explicit human approval.",
            ]
        )
    return _metadata_note(metadata, body)


def create_project_lesson(
    runtime_dir: str | Path,
    *,
    vault_root: str | Path | None,
    project_root: str | Path,
    project_id: str,
    idempotency_key: str,
    title: str,
    lesson: str,
    evidence: list[str] | None = None,
    tags: list[str] | None = None,
    global_candidate: bool = False,
) -> dict[str, Any]:
    _require_memory_writable()
    project, _root = _registered_project(runtime_dir, project_root, project_id)
    vault = resolve_memory_root(vault_root)
    memory_id = _idempotency_digest(project, "lesson", idempotency_key)
    normalized_title = _validated_memory_text(
        title,
        field="title",
        max_bytes=256,
        required=True,
    )
    normalized_lesson = _validated_memory_text(
        lesson,
        field="lesson",
        max_bytes=8_192,
        required=True,
    )
    normalized_evidence = _validated_memory_list(evidence, field="evidence")
    normalized_tags = _validated_memory_list(
        tags,
        field="tags",
        max_item_bytes=64,
    )
    if not isinstance(global_candidate, bool):
        raise ObsidianMemoryError("global_candidate must be a boolean")
    note = _lesson_note(
        project=project,
        memory_id=memory_id,
        title=normalized_title,
        lesson=normalized_lesson,
        evidence=normalized_evidence,
        tags=normalized_tags,
        global_candidate=global_candidate,
    )
    result = _create_immutable_memory_note(
        runtime_dir,
        vault=vault,
        project=project,
        kind="project_lesson",
        memory_id=memory_id,
        relative_path=_lesson_relative_path(project, memory_id),
        contents=note,
    )
    result["globalCandidate"] = global_candidate
    return result


def _parse_memory_metadata(data: bytes, *, kind: str) -> tuple[dict[str, Any], str]:
    try:
        text = data.decode("utf-8")
    except UnicodeError as exc:
        raise ObsidianMemoryError(f"{kind} is not valid UTF-8") from exc
    text = text.replace("\r\n", "\n")
    if "\r" in text or "\x00" in text or not text.startswith("---\n"):
        raise ObsidianMemoryError(f"{kind} format is invalid")
    end = text.find("\n---\n", 4)
    if end < 0 or end > 16_384:
        raise ObsidianMemoryError(f"{kind} frontmatter is invalid")
    try:
        metadata = yaml.safe_load(text[4:end])
    except yaml.YAMLError as exc:
        raise ObsidianMemoryError(f"{kind} frontmatter is invalid") from exc
    if not isinstance(metadata, dict):
        raise ObsidianMemoryError(f"{kind} frontmatter is invalid")
    return metadata, text


def _parse_lesson(data: bytes, project: str, memory_id: str) -> dict[str, Any]:
    metadata, text = _parse_memory_metadata(data, kind="project lesson")
    if any(pattern.search(text) for pattern in _SECRET_PATTERNS):
        raise ObsidianMemoryError("project lesson contains a secret-like value")
    expected_fixed = {
        "type": "devframe_project_lesson",
        "project_id": project,
        "authority": "private_untrusted_guidance",
        "status": "active",
        "memory_id": memory_id,
    }
    if any(metadata.get(key) != value for key, value in expected_fixed.items()):
        raise ObsidianMemoryError("project lesson metadata is invalid")
    title = _validated_memory_text(
        metadata.get("title"),
        field="lesson title",
        max_bytes=256,
        required=True,
    )
    lesson = _validated_memory_text(
        metadata.get("lesson"),
        field="lesson body",
        max_bytes=8_192,
        required=True,
    )
    evidence = _validated_memory_list(metadata.get("evidence"), field="lesson evidence")
    tags = _validated_memory_list(
        metadata.get("tags"),
        field="lesson tags",
        max_item_bytes=64,
    )
    global_candidate = metadata.get("global_candidate")
    if not isinstance(global_candidate, bool):
        raise ObsidianMemoryError("project lesson promotion marker is invalid")
    payload = {
        "title": title,
        "lesson": lesson,
        "evidence": evidence,
        "tags": tags,
        "global_candidate": global_candidate,
    }
    if metadata.get("payload_sha256") != _memory_payload_sha256(payload):
        raise ObsidianMemoryError("project lesson payload hash is invalid")
    expected = _lesson_note(
        project=project,
        memory_id=memory_id,
        title=title,
        lesson=lesson,
        evidence=evidence,
        tags=tags,
        global_candidate=global_candidate,
    )
    if text != expected:
        raise ObsidianMemoryError("project lesson rendered bytes are invalid")
    return {
        "memoryId": memory_id,
        "title": title,
        "lesson": lesson,
        "evidence": evidence,
        "tags": tags,
        "globalCandidate": global_candidate,
        "authority": "untrusted_guidance_only",
    }


def _read_project_lessons(
    *,
    vault_root: str | Path | None,
    project_id: str,
) -> tuple[str, list[dict[str, Any]]]:
    project = _project_id(project_id)
    vault = resolve_memory_root(vault_root)
    relative_dir = f"wiki/memories/devframe-agent/projects/{project}/lessons"
    try:
        directory = safe_resolve_workspace_path(vault, relative_dir)
    except WritebackError as exc:
        raise ObsidianMemoryError("project lesson directory is unsafe") from exc
    if not directory.exists():
        return project, []
    if not directory.is_dir() or _is_link_or_reparse(directory):
        raise ObsidianMemoryError("project lesson directory is unavailable")
    candidates = sorted(directory.glob("*.md"))
    if len(candidates) > MAX_LESSON_FILES:
        raise ObsidianMemoryError("project lesson directory exceeds the file limit")
    lessons: list[dict[str, Any]] = []
    for target in candidates:
        memory_id = target.stem
        if not _MEMORY_ID_RE.fullmatch(memory_id):
            raise ObsidianMemoryError("project lesson filename is invalid")
        relative_path = _lesson_relative_path(project, memory_id)
        data = _read_bounded(
            vault,
            target,
            max_bytes=MAX_NOTE_BYTES,
            kind="project lesson",
        )
        if target.relative_to(vault).as_posix() != relative_path:
            raise ObsidianMemoryError("project lesson path is invalid")
        lessons.append(_parse_lesson(data, project, memory_id))
    return project, lessons


def _bounded_limit(value: Any, *, default: int, maximum: int) -> int:
    if value is None:
        return default
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= maximum:
        raise ObsidianMemoryError(f"limit must be between 1 and {maximum}")
    return value


def list_project_lessons(
    *,
    vault_root: str | Path | None,
    project_id: str,
    limit: int = 20,
) -> dict[str, Any]:
    resolved_limit = _bounded_limit(limit, default=20, maximum=100)
    project, lessons = _read_project_lessons(
        vault_root=vault_root,
        project_id=project_id,
    )
    return {
        "projectId": project,
        "lessons": lessons[:resolved_limit],
        "truncated": len(lessons) > resolved_limit,
        "authority": "untrusted_guidance_only",
    }


def search_project_lessons(
    *,
    vault_root: str | Path | None,
    project_id: str,
    query: str,
    limit: int = 10,
) -> dict[str, Any]:
    resolved_limit = _bounded_limit(limit, default=10, maximum=50)
    needle = _validated_memory_text(
        query,
        field="query",
        max_bytes=256,
        required=True,
    ).casefold()
    project, lessons = _read_project_lessons(
        vault_root=vault_root,
        project_id=project_id,
    )
    ranked: list[tuple[int, str, dict[str, Any]]] = []
    for lesson in lessons:
        title = str(lesson["title"])
        haystack = "\n".join(
            [
                title,
                str(lesson["lesson"]),
                *[str(item) for item in lesson["evidence"]],
                *[str(item) for item in lesson["tags"]],
            ]
        ).casefold()
        score = haystack.count(needle)
        if score:
            ranked.append((-score, title.casefold(), lesson))
    ranked.sort(key=lambda item: (item[0], item[1], item[2]["memoryId"]))
    matches = [item[2] for item in ranked[:resolved_limit]]
    return {
        "projectId": project,
        "query": query,
        "lessons": matches,
        "truncated": len(ranked) > resolved_limit,
        "authority": "untrusted_guidance_only",
    }


def _global_playbook_note(
    *,
    project: str,
    lesson_id: str,
    lesson_sha256: str,
    lesson: dict[str, Any],
) -> str:
    metadata = {
        "type": "devframe_global_playbook",
        "authority": "human_promoted_untrusted_guidance",
        "status": "active",
        "source_project_id": project,
        "source_lesson_id": lesson_id,
        "source_lesson_sha256": lesson_sha256,
        "title": lesson["title"],
        "lesson": lesson["lesson"],
        "evidence": lesson["evidence"],
        "tags": lesson["tags"],
    }
    body = [
        f"# {lesson['title']}",
        "",
        "> Human-promoted global guidance. Still untrusted and subordinate to project authority.",
        "",
        "## Playbook",
        "",
        str(lesson["lesson"]),
    ]
    if lesson["evidence"]:
        body.extend(
            [
                "",
                "## Evidence",
                "",
                *(f"- {item}" for item in lesson["evidence"]),
            ]
        )
    if lesson["tags"]:
        body.extend(["", "## Tags", "", ", ".join(lesson["tags"])])
    return _metadata_note(metadata, body)


def stage_global_playbook_promotion(
    runtime_dir: str | Path,
    *,
    vault_root: str | Path | None,
    project_root: str | Path,
    project_id: str,
    lesson_id: str,
    thread_id: str = "",
) -> dict[str, Any]:
    _require_memory_writable()
    project, _root = _registered_project(runtime_dir, project_root, project_id)
    vault = resolve_memory_root(vault_root)
    if not _MEMORY_ID_RE.fullmatch(str(lesson_id or "")):
        raise ObsidianMemoryError("lesson memory id is invalid")
    source_path = _lesson_relative_path(project, lesson_id)
    try:
        data = read_bounded_workspace_file(
            vault,
            source_path,
            max_bytes=MAX_NOTE_BYTES,
        )
    except WritebackError as exc:
        raise ObsidianMemoryError("project lesson is unavailable") from exc
    lesson = _parse_lesson(data, project, lesson_id)
    if lesson["globalCandidate"] is not True:
        raise ObsidianMemoryError("project lesson is not a global candidate")
    lesson_sha256 = hashlib.sha256(data).hexdigest()
    target_path = _global_playbook_relative_path(project, lesson_id)
    contents = _global_playbook_note(
        project=project,
        lesson_id=lesson_id,
        lesson_sha256=lesson_sha256,
        lesson=lesson,
    )
    try:
        staged = stage_writeback_proposal(
            runtime_dir,
            vault,
            target_path,
            contents,
            thread_id=thread_id,
            project_id=project,
            max_bytes=MAX_NOTE_BYTES,
            redact_paths=True,
            create_only=True,
            proposal_kind=GLOBAL_PROMOTION_PROPOSAL_KIND,
            source_preconditions=[
                {
                    "workspace_root": str(vault),
                    "relative_path": source_path,
                    "sha256": lesson_sha256,
                }
            ],
        )
    except WritebackError as exc:
        raise ObsidianMemoryError(
            "global playbook proposal was rejected"
        ) from exc
    return {
        "staged": True,
        "humanRequired": True,
        "request_id": staged["request_id"],
        "project_id": project,
        "lesson_id": lesson_id,
        "operation": staged["preview"]["operation"],
        "bytes": staged["preview"]["bytes"],
    }


def _validate_global_playbook_proposal(proposal: dict[str, Any]) -> tuple[str, str]:
    _require_memory_writable()
    if proposal.get("proposal_kind") != GLOBAL_PROMOTION_PROPOSAL_KIND:
        raise ObsidianMemoryError("request is not a global playbook promotion")
    if proposal.get("create_only") is not True or proposal.get("redact_paths") is not True:
        raise ObsidianMemoryError("global playbook publication policy is invalid")
    project = _project_id(str(proposal.get("project_id") or ""))
    preconditions = proposal.get("source_preconditions")
    if (
        not isinstance(preconditions, list)
        or len(preconditions) != 1
        or not isinstance(preconditions[0], dict)
    ):
        raise ObsidianMemoryError("global playbook source precondition is invalid")
    source = preconditions[0]
    source_path = str(source.get("relative_path") or "")
    match = re.fullmatch(
        re.escape(
            f"wiki/memories/devframe-agent/projects/{project}/lessons/"
        )
        + r"([0-9a-f]{64})\.md",
        source_path,
    )
    if match is None:
        raise ObsidianMemoryError("global playbook source path is invalid")
    lesson_id = match.group(1)
    source_root = str(source.get("workspace_root") or "")
    if os.path.normcase(source_root) != os.path.normcase(
        str(proposal.get("workspace_root") or "")
    ):
        raise ObsidianMemoryError("global playbook source Vault is invalid")
    try:
        source_data = read_bounded_workspace_file(
            source_root,
            source_path,
            max_bytes=MAX_NOTE_BYTES,
        )
    except WritebackError as exc:
        raise ObsidianMemoryError("global playbook source is unavailable") from exc
    lesson_sha256 = hashlib.sha256(source_data).hexdigest()
    if lesson_sha256 != source.get("sha256"):
        raise ObsidianMemoryError("global playbook source hash is invalid")
    lesson = _parse_lesson(source_data, project, lesson_id)
    if lesson["globalCandidate"] is not True:
        raise ObsidianMemoryError("global playbook source is not a candidate")
    expected_path = _global_playbook_relative_path(project, lesson_id)
    expected_contents = _global_playbook_note(
        project=project,
        lesson_id=lesson_id,
        lesson_sha256=lesson_sha256,
        lesson=lesson,
    )
    if (
        proposal.get("relative_path") != expected_path
        or proposal.get("contents") != expected_contents
    ):
        raise ObsidianMemoryError("global playbook proposal binding is invalid")
    return project, expected_path


def _bounded_transcript_tail(
    transcript_path: str | Path,
    *,
    codex_home: str | Path | None,
) -> bytes:
    home = Path(codex_home).expanduser() if codex_home else Path(
        os.environ.get("CODEX_HOME") or (Path.home() / ".codex")
    ).expanduser()
    sessions = _plain_directory(home / "sessions", kind="Codex sessions directory")
    candidate = Path(transcript_path).expanduser()
    if not candidate.is_absolute():
        raise ObsidianMemoryError("transcript path must be absolute")
    try:
        absolute_candidate = Path(os.path.abspath(candidate))
        relative = absolute_candidate.relative_to(sessions)
        resolved = safe_resolve_workspace_path(sessions, relative.as_posix())
        if resolved != candidate.resolve(strict=True):
            raise ObsidianMemoryError("transcript path changed during resolution")
    except (OSError, RuntimeError, WritebackError, ValueError) as exc:
        raise ObsidianMemoryError("transcript path is outside Codex sessions") from exc
    if relative.as_posix().startswith("../") or not resolved.is_file() or _is_link_or_reparse(resolved):
        raise ObsidianMemoryError("transcript path is unavailable")
    try:
        with resolved.open("rb") as handle:
            before = os.fstat(handle.fileno())
            offset = max(0, int(before.st_size) - MAX_TRANSCRIPT_TAIL_BYTES)
            handle.seek(offset)
            if offset:
                handle.readline()
            data = handle.read(MAX_TRANSCRIPT_TAIL_BYTES + 1)
            after = os.fstat(handle.fileno())
    except OSError as exc:
        raise ObsidianMemoryError("transcript is unavailable") from exc
    if (
        before.st_dev != after.st_dev
        or before.st_ino != after.st_ino
        or after.st_size != before.st_size
        or len(data) > MAX_TRANSCRIPT_TAIL_BYTES
    ):
        raise ObsidianMemoryError("transcript changed during bounded read")
    return data


def _clip_transcript_signal(value: Any, max_chars: int = 1_200) -> str:
    if not isinstance(value, str):
        return ""
    collapsed = re.sub(r"\s+", " ", value).strip()
    return collapsed[:max_chars].strip()


def _extract_checkpoint_signals(data: bytes) -> dict[str, Any]:
    last_user = ""
    agent_messages: list[str] = []
    for raw_line in data.splitlines()[-MAX_TRANSCRIPT_RECORDS:]:
        if not raw_line or len(raw_line) > 262_144:
            continue
        try:
            record = json.loads(raw_line)
        except (UnicodeError, json.JSONDecodeError):
            continue
        if not isinstance(record, dict) or record.get("type") != "event_msg":
            continue
        payload = record.get("payload")
        if not isinstance(payload, dict):
            continue
        message_type = payload.get("type")
        message = payload.get("message")
        if message_type == "user_message" and isinstance(message, str):
            last_user = _clip_transcript_signal(message, 1_200)
        elif message_type == "agent_message" and isinstance(message, str):
            agent_messages.append(message)
            agent_messages = agent_messages[-12:]
    categories: dict[str, list[str]] = {
        "decisions": [],
        "failed_attempts": [],
        "verification": [],
        "blockers": [],
        "next_actions": [],
    }
    patterns = (
        ("decisions", re.compile(r"^(?:decision|decided|决定|选择)\b", re.IGNORECASE)),
        (
            "failed_attempts",
            re.compile(r"^(?:failed|failure|error|失败|未通过)\b", re.IGNORECASE),
        ),
        (
            "verification",
            re.compile(r"^(?:verification|verified|test|tests|pass|验证|测试)\b", re.IGNORECASE),
        ),
        (
            "blockers",
            re.compile(r"^(?:blocker|blocked|blocking|阻塞|阻碍)\b", re.IGNORECASE),
        ),
        (
            "next_actions",
            re.compile(r"^(?:next action|next|todo|下一步|后续)\b", re.IGNORECASE),
        ),
    )
    for message in agent_messages:
        for raw in message.splitlines():
            line = re.sub(r"^[\s#>*+-]+", "", raw).strip()
            if not line:
                continue
            for category, pattern in patterns:
                if pattern.search(line):
                    clipped = _clip_transcript_signal(line, 600)
                    if clipped and clipped not in categories[category]:
                        categories[category].append(clipped)
                        categories[category] = categories[category][-6:]
                    break
    return {
        "goal": last_user,
        "decisions": categories["decisions"],
        "failed_attempts": categories["failed_attempts"],
        "verification": categories["verification"],
        "blockers": categories["blockers"],
        "next_action": categories["next_actions"][-1]
        if categories["next_actions"]
        else "",
    }


def capture_session_checkpoint_from_transcript(
    runtime_dir: str | Path,
    *,
    vault_root: str | Path | None,
    cwd: str | Path,
    transcript_path: str | Path,
    session_id: str,
    turn_id: str,
    trigger: str,
    codex_home: str | Path | None = None,
) -> dict[str, Any]:
    _require_memory_writable()
    context = resolve_session_project(cwd=cwd, runtime_dir=runtime_dir)
    data = _bounded_transcript_tail(transcript_path, codex_home=codex_home)
    signals = _extract_checkpoint_signals(data)
    if not any(
        [
            signals["goal"],
            signals["decisions"],
            signals["failed_attempts"],
            signals["verification"],
            signals["blockers"],
            signals["next_action"],
        ]
    ):
        return {
            "projectId": str(context["projectId"]),
            "status": "no_signal",
            "created": False,
            "duplicate": False,
        }
    event_key = json.dumps(
        [
            _validated_memory_text(
                session_id,
                field="session_id",
                max_bytes=512,
                required=True,
            ),
            _validated_memory_text(
                turn_id,
                field="turn_id",
                max_bytes=512,
                required=True,
            ),
            str(trigger or "").strip(),
        ],
        ensure_ascii=True,
        separators=(",", ":"),
    )
    result = capture_project_checkpoint(
        runtime_dir,
        vault_root=vault_root,
        project_root=str(context["projectRoot"]),
        project_id=str(context["projectId"]),
        idempotency_key=event_key,
        session_id=session_id,
        trigger=trigger,
        goal=signals["goal"],
        decisions=signals["decisions"],
        failed_attempts=signals["failed_attempts"],
        verification=signals["verification"],
        blockers=signals["blockers"],
        next_action=signals["next_action"],
    )
    result["status"] = "captured" if result["created"] else "duplicate"
    return result
