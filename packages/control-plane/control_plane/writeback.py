"""Governed write-back executor for the RD-Code editor loop (M8.2).

The bridge default policy stays read-only. A write-back is a per-action,
human-gated, audited exception: the dashboard POST endpoints
(``/api/t3/approval-response`` approve, or ``/actions/execute`` with
``confirm=execute``) own the human gate, and this module owns ONLY the safe
filesystem write plus an audit record. This executor must never be reachable
without that gate.

Safety contract (enforced here, independent of the caller):
- The target must resolve to a path strictly under the workspace root.
- Absolute paths, drive-qualified paths, and any ``..`` segment are rejected.
- Sensitive path components are refused (``.git``, ``.env*``, key/credential
  stores, generated runtime/state dirs, ``node_modules``).
- Symlinks (the target itself or any ancestor pointing outside the root) are
  rejected so a write can never escape the workspace through a link.
- Contents must be a UTF-8 string under a size cap.
"""
from __future__ import annotations

import json
import hashlib
import os
import re
import secrets
import stat
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DEFAULT_MAX_WRITEBACK_BYTES = 2_000_000
_PROCESS_INSTANCE_ID = secrets.token_hex(16)
_PROCESS_PID = os.getpid()
_RECOVERY_LOCK_STALE_SECONDS = 60

# Directory/file name components we refuse to write into, case-insensitive.
_SENSITIVE_PATH_PARTS = frozenset(
    {
        ".git",
        ".hg",
        ".svn",
        ".ssh",
        ".gnupg",
        ".aws",
        ".codexpro",
        ".cloudflared",
        ".devframe-runtime",
        ".codegraph",
        ".obsidian",
        "node_modules",
        "id_rsa",
        "credentials",
        "secrets",
    }
)

_WINDOWS_DEVICE_NAMES = frozenset(
    {"con", "prn", "aux", "nul", "clock$"}
    | {f"com{index}" for index in range(1, 10)}
    | {f"lpt{index}" for index in range(1, 10)}
)


class WritebackError(Exception):
    """Raised when a proposed write-back is unsafe or invalid."""


def _is_env_like(part: str) -> bool:
    lowered = part.lower()
    return lowered == ".env" or lowered.startswith(".env.") or lowered.endswith(".env")


def _is_sensitive_part(part: str) -> bool:
    # Windows silently strips trailing dots/spaces (".git " -> ".git"), so
    # normalize before comparing or the sensitive-name guard can be bypassed.
    norm = part.rstrip(" .").lower()
    if not norm:
        return False
    return norm in _SENSITIVE_PATH_PARTS or _is_env_like(norm)


def _is_reparse_point(path: Path) -> bool:
    try:
        if path.is_symlink():
            return True
        attributes = int(getattr(path.lstat(), "st_file_attributes", 0))
        return bool(attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400))
    except FileNotFoundError:
        return False
    except OSError:
        return True


def _directory_identity(path: Path) -> tuple[int, int]:
    if _is_reparse_point(path) or not path.is_dir():
        raise WritebackError("write-back parent directory is unsafe")
    try:
        identity = os.stat(path, follow_symlinks=False)
    except OSError as exc:
        raise WritebackError("write-back parent directory is unavailable") from exc
    return identity.st_dev, identity.st_ino


def safe_resolve_workspace_path(workspace_root: str | Path, relative_path: str) -> Path:
    """Resolve ``relative_path`` under ``workspace_root`` or raise WritebackError.

    The returned path is guaranteed (symlinks resolved) to be strictly under the
    real workspace root.
    """
    configured_root = Path(workspace_root)
    if _is_reparse_point(configured_root):
        raise WritebackError("workspace root must not be a symlink or junction")
    try:
        root = configured_root.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise WritebackError("workspace root is not accessible") from exc
    if not root.is_dir():
        raise WritebackError("workspace root is not a directory")

    rel = str(relative_path or "")
    if not rel or not rel.strip():
        raise WritebackError("relative path is required")

    candidate = Path(rel)
    if candidate.is_absolute() or candidate.drive or candidate.anchor:
        raise WritebackError("relative path must be workspace-relative, not absolute")

    parts = candidate.parts
    if not parts:
        raise WritebackError("relative path is required")
    for part in parts:
        if part == "..":
            raise WritebackError("relative path must not contain '..'")
        if part in {".", ""}:
            continue
        # Preserve the established sensitive-path diagnostic even when a
        # Windows trailing-dot/space alias is used (for example `.git `).
        if _is_sensitive_part(part):
            raise WritebackError(f"refusing to write sensitive path component: {part}")
        if part != part.rstrip(" ."):
            raise WritebackError("relative path components must not end with dots or spaces")
        if ":" in part:
            raise WritebackError("relative path must not contain NTFS alternate streams")
        if part.casefold().split(".", 1)[0] in _WINDOWS_DEVICE_NAMES:
            raise WritebackError("relative path must not use a Windows device name")

    target = root / candidate

    # Reject if any existing ancestor (or the target) is a symlink, which could
    # redirect the write outside the workspace even if names look clean.
    probe = target
    while True:
        if probe == root:
            break
        if _is_reparse_point(probe):
            raise WritebackError("refusing to write through a symlink or junction")
        parent = probe.parent
        if parent == probe:
            break
        probe = parent

    # Final guard: the fully resolved path must stay under the resolved root.
    resolved = target.resolve()
    try:
        relative_parts = resolved.relative_to(root).parts
    except ValueError as exc:
        raise WritebackError("resolved path escapes the workspace root") from exc
    # Re-check sensitive names against the RESOLVED components: this catches
    # Windows 8.3 short names (e.g. GIT~1 -> .git) that look innocuous before
    # resolution but expand into a sensitive directory.
    for part in relative_parts:
        if _is_sensitive_part(part):
            raise WritebackError(f"refusing to write sensitive path component: {part}")
    return resolved


def apply_single_file_writeback(
    workspace_root: str | Path,
    relative_path: str,
    contents: str,
    *,
    max_bytes: int = DEFAULT_MAX_WRITEBACK_BYTES,
    require_absent: bool = False,
) -> dict[str, Any]:
    """Atomically write ``contents`` to a safe path under ``workspace_root``.

    Returns an audit record describing the applied write. Raises WritebackError
    on any safety or validation failure (caller must have already passed the
    human gate before calling this).
    """
    if not isinstance(contents, str):
        raise WritebackError("contents must be a string")
    data = contents.encode("utf-8")
    if len(data) > max_bytes:
        raise WritebackError(
            f"contents exceed max write-back size ({len(data)} > {max_bytes} bytes)"
        )

    target = safe_resolve_workspace_path(workspace_root, relative_path)
    if _is_reparse_point(target):
        raise WritebackError("refusing to write through a symlink or junction")
    if target.exists() and target.is_dir():
        raise WritebackError("target path is an existing directory")

    target.parent.mkdir(parents=True, exist_ok=True)
    target = safe_resolve_workspace_path(workspace_root, relative_path)
    if _is_reparse_point(target):
        raise WritebackError("refusing to write through a symlink or junction")
    if target.exists() and target.is_dir():
        raise WritebackError("target path is an existing directory")
    existed = target.exists()
    if require_absent and existed:
        raise WritebackError("create-only target already exists")
    before_size = target.stat().st_size if existed else 0
    parent_identity = _directory_identity(target.parent)

    tmp = target.parent / (
        target.name + f".devframe-writeback.{secrets.token_hex(4)}.tmp"
    )
    try:
        tmp.write_bytes(data)
        if _directory_identity(target.parent) != parent_identity:
            raise WritebackError("write-back parent directory changed during write")
        if safe_resolve_workspace_path(workspace_root, relative_path) != target:
            raise WritebackError("write-back target changed during write")
        if require_absent:
            # Linking a fully written sibling temp file is an atomic,
            # create-only operation: it fails if the destination appeared
            # after preview/staging and never replaces user content.
            try:
                os.link(tmp, target)
            except FileExistsError as exc:
                raise WritebackError("create-only target already exists") from exc
            except OSError as exc:
                raise WritebackError("create-only target could not be created atomically") from exc
        else:
            os.replace(tmp, target)
        if _is_reparse_point(target):
            raise WritebackError("write-back target became a symlink or junction")
    finally:
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass

    root = Path(workspace_root).resolve()
    return {
        "kind": "writeback_apply_file",
        "workspace_root": str(root),
        "relative_path": str(target.relative_to(root).as_posix()),
        "resolved_path": str(target),
        "operation": "modified" if existed else "created",
        "bytes_written": len(data),
        "bytes_before": before_size,
        "content_sha256": hashlib.sha256(data).hexdigest(),
        "applied_at": datetime.now(timezone.utc).isoformat(),
    }


def _atomic_json_write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.parent / (path.name + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8")
    os.replace(tmp, path)


def preview_single_file_writeback(
    workspace_root: str | Path,
    relative_path: str,
    contents: str,
    *,
    max_bytes: int = DEFAULT_MAX_WRITEBACK_BYTES,
    require_absent: bool = False,
) -> dict[str, Any]:
    """Validate a proposed write-back WITHOUT writing; return a gate preview.

    Runs the full safety contract (path + size + type) so an unsafe proposal is
    rejected before it can reach the human gate. Never touches the filesystem.
    """
    if not isinstance(contents, str):
        raise WritebackError("contents must be a string")
    data = contents.encode("utf-8")
    if len(data) > max_bytes:
        raise WritebackError(
            f"contents exceed max write-back size ({len(data)} > {max_bytes} bytes)"
        )
    target = safe_resolve_workspace_path(workspace_root, relative_path)
    if _is_reparse_point(target):
        raise WritebackError("refusing to write through a symlink or junction")
    if target.exists() and target.is_dir():
        raise WritebackError("target path is an existing directory")
    root = Path(workspace_root).resolve()
    existed = target.exists()
    if require_absent and existed:
        raise WritebackError("create-only target already exists")
    return {
        "kind": "writeback_apply_file",
        "workspace_root": str(root),
        "relative_path": str(target.relative_to(root).as_posix()),
        "operation": "modified" if existed else "created",
        "bytes": len(data),
        "bytes_before": target.stat().st_size if existed else 0,
    }


def apply_writeback_with_audit(
    workspace_root: str | Path,
    relative_path: str,
    contents: str,
    *,
    runtime_dir: str | Path | None = None,
    action_id: str | None = None,
    confirm: bool = False,
    max_bytes: int = DEFAULT_MAX_WRITEBACK_BYTES,
    require_absent: bool = False,
    redact_audit_root: bool = False,
) -> dict[str, Any]:
    """Human-gated, audited single-file write-back.

    Without ``confirm`` this returns a ``human_required`` gate preview and writes
    nothing (the caller — a CLI ``--confirm`` flag or the dashboard
    ``confirm=execute`` / approval gate — must explicitly confirm). With
    ``confirm`` it applies the write and, when ``runtime_dir`` is given, persists
    an ``action-run.json`` audit record under ``writeback-runs/``.
    """
    preview = preview_single_file_writeback(
        workspace_root,
        relative_path,
        contents,
        max_bytes=max_bytes,
        require_absent=require_absent,
    )
    if not confirm:
        return {
            "applied": False,
            "human_required": True,
            "confirm": "re-run with confirm=execute to apply this write-back through the human gate",
            **preview,
        }

    record = apply_single_file_writeback(
        workspace_root,
        relative_path,
        contents,
        max_bytes=max_bytes,
        require_absent=require_absent,
    )
    stamp = time.strftime("%Y%m%d-%H%M%S")
    resolved_action_id = (action_id or "").strip() or f"writeback-{stamp}"
    audit: dict[str, Any] = {
        "applied": True,
        "action_id": resolved_action_id,
        "action_run_id": stamp,
        **record,
    }
    if redact_audit_root:
        audit.pop("workspace_root", None)
        audit.pop("resolved_path", None)
    if runtime_dir is not None:
        runtime_root = Path(runtime_dir).resolve()
        audit_path = runtime_root / "writeback-runs" / resolved_action_id / f"{stamp}.json"
        _atomic_json_write(audit_path, audit)
        audit["audit_path"] = str(audit_path)
    return audit


_REQUEST_ID_RE = re.compile(r"^wb-[0-9a-f]{16}$")
_PROPOSAL_LOCK = threading.RLock()


def _proposals_dir(runtime_dir: str | Path) -> Path:
    return Path(runtime_dir).resolve() / "writeback-proposals"


def _safe_request_id(request_id: str) -> str:
    rid = str(request_id or "").strip()
    if not _REQUEST_ID_RE.match(rid):
        raise WritebackError("invalid write-back request id")
    return rid


def _proposal_digest(proposal: dict[str, Any]) -> str:
    protected = {
        key: proposal.get(key)
        for key in (
            "request_id",
            "workspace_root",
            "relative_path",
            "contents",
            "thread_id",
            "project_id",
            "proposal_kind",
            "authority_fingerprint",
            "require_absent",
            "redact_preview_root",
            "content_sha256",
            "staged_at",
        )
    }
    for key in ("apply_contents", "apply_content_sha256"):
        if key in proposal:
            protected[key] = proposal.get(key)
    encoded = json.dumps(
        protected, sort_keys=True, ensure_ascii=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _proposal_path(runtime_dir: str | Path, request_id: str) -> Path:
    return _proposals_dir(runtime_dir) / f"{request_id}.json"


def _claim_path(runtime_dir: str | Path, request_id: str) -> Path:
    return _proposals_dir(runtime_dir) / f"{request_id}.applying.json"


def stage_writeback_proposal(
    runtime_dir: str | Path,
    workspace_root: str | Path,
    relative_path: str,
    contents: str,
    *,
    thread_id: str = "",
    project_id: str = "",
    max_bytes: int = DEFAULT_MAX_WRITEBACK_BYTES,
    require_absent: bool = False,
    redact_preview_root: bool = False,
    proposal_kind: str = "writeback",
    authority_fingerprint: str = "",
    apply_contents: str | None = None,
) -> dict[str, Any]:
    """Validate and stage a proposed write-back as a pending, human-gated item.

    Staging never writes to the workspace; it records the proposal so a later
    human approval can apply it. Returns ``{request_id, preview}``.
    """
    preview = preview_single_file_writeback(
        workspace_root,
        relative_path,
        contents,
        max_bytes=max_bytes,
        require_absent=require_absent,
    )
    public_preview = dict(preview)
    if redact_preview_root:
        public_preview.pop("workspace_root", None)
    request_id = "wb-" + secrets.token_hex(8)
    approved_contents = contents if apply_contents is None else apply_contents
    if not isinstance(approved_contents, str):
        raise WritebackError("apply_contents must be a string")
    if approved_contents != contents:
        raise WritebackError("apply_contents must match approved contents")
    if len(approved_contents.encode("utf-8")) > max_bytes:
        raise WritebackError("approved contents exceed max write-back size")
    proposal = {
        "request_id": request_id,
        "status": "pending",
        "workspace_root": str(Path(workspace_root).resolve()),
        "relative_path": preview["relative_path"],
        "contents": contents,
        "apply_contents": approved_contents,
        "thread_id": str(thread_id or ""),
        "project_id": str(project_id or ""),
        "proposal_kind": str(proposal_kind or "writeback"),
        "authority_fingerprint": str(authority_fingerprint or ""),
        "require_absent": bool(require_absent),
        "redact_preview_root": bool(redact_preview_root),
        "preview": public_preview,
        "content_sha256": hashlib.sha256(contents.encode("utf-8")).hexdigest(),
        "apply_content_sha256": hashlib.sha256(
            approved_contents.encode("utf-8")
        ).hexdigest(),
        "staged_at": datetime.now(timezone.utc).isoformat(),
    }
    proposal["proposal_digest"] = _proposal_digest(proposal)
    _atomic_json_write(_proposals_dir(runtime_dir) / f"{request_id}.json", proposal)
    return {"request_id": request_id, "preview": public_preview}


def load_writeback_proposal(runtime_dir: str | Path, request_id: str) -> dict[str, Any] | None:
    rid = _safe_request_id(request_id)
    path = _proposal_path(runtime_dir, rid)
    if not path.is_file():
        claim = _claim_path(runtime_dir, rid)
        if claim.is_file():
            try:
                applying = json.loads(claim.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                return None
            return {**applying, "status": "applying"}
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _set_proposal_status(
    runtime_dir: str | Path,
    proposal: dict[str, Any],
    status: str,
    *,
    failure: str = "",
) -> None:
    rid = _safe_request_id(str(proposal.get("request_id") or ""))
    resolved = {
        **proposal,
        "status": status,
        "resolved_at": datetime.now(timezone.utc).isoformat(),
    }
    if failure:
        resolved["failure"] = failure
    _atomic_json_write(_proposal_path(runtime_dir, rid), resolved)
    claim = _claim_path(runtime_dir, rid)
    if claim.exists():
        try:
            claim.unlink()
        except OSError:
            pass


def _validate_proposal_for_apply(
    proposal: dict[str, Any],
    *,
    expected_thread_id: str | None,
) -> bool:
    proposal_thread = str(proposal.get("thread_id") or "")
    is_memory_proposal = (
        str(proposal.get("proposal_kind") or "")
        == "obsidian_memory_candidate"
    )
    if is_memory_proposal and (
        not proposal_thread
        or not expected_thread_id
        or str(expected_thread_id) != proposal_thread
    ):
        raise WritebackError("write-back thread mismatch")
    if (
        not is_memory_proposal
        and expected_thread_id is not None
        and proposal_thread
        and str(expected_thread_id) != proposal_thread
    ):
        raise WritebackError("write-back thread mismatch")
    digest = str(proposal.get("proposal_digest") or "")
    if not digest or not secrets.compare_digest(digest, _proposal_digest(proposal)):
        raise WritebackError("write-back proposal integrity check failed")
    _proposal_apply_contents(proposal)
    if is_memory_proposal:
        expected_authority = str(proposal.get("authority_fingerprint") or "")
        if not expected_authority:
            raise WritebackError("write-back proposal integrity check failed")
        try:
            from .obsidian_memory import (
                ObsidianMemoryError,
                memory_authority_fingerprint,
            )

            current_authority = memory_authority_fingerprint(
                str(proposal.get("project_id") or "")
            )
        except ObsidianMemoryError as exc:
            raise WritebackError("memory proposal authority is unavailable") from exc
        if not secrets.compare_digest(expected_authority, current_authority):
            raise WritebackError("memory proposal authority changed")
    return is_memory_proposal


def _proposal_apply_contents(proposal: dict[str, Any]) -> str:
    approved_contents = proposal.get("contents")
    contents = proposal.get("apply_contents", approved_contents)
    if not isinstance(approved_contents, str) or not isinstance(contents, str):
        raise WritebackError("write-back proposal integrity check failed")
    if contents != approved_contents:
        raise WritebackError("write-back proposal approved contents mismatch")
    expected = proposal.get("apply_content_sha256")
    if expected is not None and (
        not isinstance(expected, str)
        or not secrets.compare_digest(
            expected,
            hashlib.sha256(contents.encode("utf-8")).hexdigest(),
        )
    ):
        raise WritebackError("write-back proposal integrity check failed")
    return approved_contents


def _claim_pending_proposal(
    runtime_dir: str | Path,
    request_id: str,
    *,
    expected_thread_id: str | None,
) -> tuple[dict[str, Any], bool]:
    """Atomically claim a pending proposal before any external write."""
    rid = _safe_request_id(request_id)
    path = _proposal_path(runtime_dir, rid)
    claim = _claim_path(runtime_dir, rid)
    with _PROPOSAL_LOCK:
        proposal = load_writeback_proposal(runtime_dir, rid)
        if proposal is None:
            raise WritebackError("write-back proposal not found")
        status = str(proposal.get("status") or "")
        if status != "pending":
            return proposal, False
        _validate_proposal_for_apply(
            proposal,
            expected_thread_id=expected_thread_id,
        )
        claim_metadata = {
            **proposal,
            "claim_owner": _PROCESS_INSTANCE_ID,
            "claim_pid": _PROCESS_PID,
            "claim_started_at": datetime.now(timezone.utc).isoformat(),
        }
        applying = {
            **claim_metadata,
            "status": "applying",
        }
        claim_candidate = claim.parent / (
            claim.name
            + f".{_PROCESS_INSTANCE_ID}.{secrets.token_hex(4)}.tmp"
        )
        try:
            # ``os.replace`` would overwrite an existing claim on POSIX (and
            # may do so on Windows), so it cannot represent an ownership
            # boundary.  Link a fully written ownership record instead: the
            # destination appears atomically with owner/pid metadata, and
            # exactly one process can create it.  Recovery can therefore
            # never mistake a live claimant for an ownerless crashed claim.
            claim_candidate.write_text(
                json.dumps(applying, indent=2, ensure_ascii=True),
                encoding="utf-8",
            )
            os.link(claim_candidate, claim)
        except FileExistsError:
            try:
                existing_claim = json.loads(claim.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                raise WritebackError("write-back proposal claim is unavailable")
            return {**existing_claim, "status": "applying"}, False
        except FileNotFoundError:
            latest = load_writeback_proposal(runtime_dir, rid)
            if latest is None:
                raise WritebackError("write-back proposal claim failed")
            return latest, False
        except OSError as exc:
            raise WritebackError("write-back proposal claim failed") from exc
        finally:
            if claim_candidate.exists():
                try:
                    claim_candidate.unlink()
                except OSError:
                    pass
        try:
            path.unlink()
        except OSError as exc:
            try:
                claim.unlink()
            except OSError:
                pass
            raise WritebackError("write-back proposal claim could not be finalized") from exc
        return applying, True


def _recovery_lock_path(runtime_dir: str | Path, request_id: str) -> Path:
    return _proposals_dir(runtime_dir) / f"{request_id}.recovering"


def _acquire_recovery_lock(runtime_dir: str | Path, request_id: str) -> Path | None:
    lock = _recovery_lock_path(runtime_dir, request_id)
    lock.parent.mkdir(parents=True, exist_ok=True)
    for _ in range(2):
        try:
            descriptor = os.open(
                str(lock),
                os.O_CREAT | os.O_EXCL | os.O_WRONLY,
                0o600,
            )
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                json.dump(
                    {
                        "owner": _PROCESS_INSTANCE_ID,
                        "acquired_at": datetime.now(timezone.utc).isoformat(),
                    },
                    handle,
                )
            return lock
        except FileExistsError:
            try:
                age = max(0.0, time.time() - lock.stat().st_mtime)
            except OSError:
                return None
            if age <= _RECOVERY_LOCK_STALE_SECONDS:
                return None
            try:
                lock.unlink()
            except OSError:
                return None
    return None


def _release_recovery_lock(lock: Path) -> None:
    try:
        lock.unlink()
    except OSError:
        pass


def _process_is_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name == "nt":
        # ``os.kill(pid, 0)`` is not a portable existence probe on Windows;
        # non-console signals can terminate the process.  Query a synchronize
        # handle instead and leave the claimant untouched.
        import ctypes

        synchronize = 0x00100000
        wait_timeout = 0x00000102
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.OpenProcess.argtypes = [ctypes.c_uint32, ctypes.c_int, ctypes.c_uint32]
        kernel32.OpenProcess.restype = ctypes.c_void_p
        kernel32.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
        kernel32.WaitForSingleObject.restype = ctypes.c_uint32
        kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
        kernel32.CloseHandle.restype = ctypes.c_int
        handle = kernel32.OpenProcess(synchronize, False, pid)
        if not handle:
            return False
        try:
            return kernel32.WaitForSingleObject(handle, 0) == wait_timeout
        finally:
            kernel32.CloseHandle(handle)
    try:
        os.kill(pid, 0)
    except (OSError, ProcessLookupError):
        return False
    return True


def _matching_apply_audit(
    runtime_dir: str | Path,
    proposal: dict[str, Any],
) -> dict[str, Any] | None:
    request_id = _safe_request_id(str(proposal.get("request_id") or ""))
    expected_digest = hashlib.sha256(
        _proposal_apply_contents(proposal).encode("utf-8")
    ).hexdigest()
    audit_dir = Path(runtime_dir).resolve() / "writeback-runs" / request_id
    if not audit_dir.is_dir():
        return None
    for path in sorted(audit_dir.glob("*.json")):
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if (
            record.get("applied") is True
            and str(record.get("action_id") or "") == request_id
            and str(record.get("relative_path") or "")
            == str(proposal.get("relative_path") or "")
            and str(record.get("content_sha256") or "") == expected_digest
        ):
            return record
    return None


def _write_recovery_audit(
    runtime_dir: str | Path,
    proposal: dict[str, Any],
) -> dict[str, Any]:
    request_id = _safe_request_id(str(proposal.get("request_id") or ""))
    contents = _proposal_apply_contents(proposal)
    record: dict[str, Any] = {
        "applied": True,
        "action_id": request_id,
        "action_run_id": "recovery",
        "kind": "writeback_apply_file",
        "relative_path": str(proposal.get("relative_path") or ""),
        "operation": "created",
        "bytes_written": len(contents.encode("utf-8")),
        "bytes_before": 0,
        "content_sha256": hashlib.sha256(contents.encode("utf-8")).hexdigest(),
        "recovered": True,
        "applied_at": datetime.now(timezone.utc).isoformat(),
    }
    if not proposal.get("redact_preview_root"):
        record["workspace_root"] = str(proposal.get("workspace_root") or "")
    audit_path = (
        Path(runtime_dir).resolve()
        / "writeback-runs"
        / request_id
        / "recovery.json"
    )
    _atomic_json_write(audit_path, record)
    return {**record, "audit_path": str(audit_path)}


def _finish_recovered_memory_proposal(
    runtime_dir: str | Path,
    proposal: dict[str, Any],
    target: Path,
) -> dict[str, Any]:
    try:
        data = target.read_bytes()
    except OSError as exc:
        raise WritebackError("create-only target could not be verified") from exc
    expected_digest = hashlib.sha256(
        _proposal_apply_contents(proposal).encode("utf-8")
    ).hexdigest()
    if hashlib.sha256(data).hexdigest() != expected_digest:
        _set_proposal_status(
            runtime_dir,
            proposal,
            "failed",
            failure="create_only_target_conflict",
        )
        raise WritebackError("create-only target content conflicts with proposal")
    audit = _matching_apply_audit(runtime_dir, proposal)
    if audit is None:
        audit = _write_recovery_audit(runtime_dir, proposal)
    _set_proposal_status(runtime_dir, proposal, "applied")
    return {
        "request_id": str(proposal.get("request_id") or ""),
        "applied": True,
        "status": "applied",
        **_public_apply_result(proposal, audit),
    }


def _recover_memory_proposal(
    runtime_dir: str | Path,
    proposal: dict[str, Any],
    *,
    expected_thread_id: str | None,
) -> dict[str, Any] | None:
    if str(proposal.get("proposal_kind") or "") != "obsidian_memory_candidate":
        return None
    if str(proposal.get("claim_owner") or "") == _PROCESS_INSTANCE_ID:
        return None
    try:
        claim_pid = int(proposal.get("claim_pid") or 0)
    except (TypeError, ValueError):
        claim_pid = 0
    if claim_pid and _process_is_alive(claim_pid):
        return None
    lock = _acquire_recovery_lock(
        runtime_dir,
        _safe_request_id(str(proposal.get("request_id") or "")),
    )
    if lock is None:
        return None
    try:
        _validate_proposal_for_apply(
            proposal,
            expected_thread_id=expected_thread_id,
        )
        target = safe_resolve_workspace_path(
            proposal["workspace_root"],
            proposal["relative_path"],
        )
        if target.exists():
            if target.is_dir() or _is_reparse_point(target):
                raise WritebackError("create-only target could not be verified")
            return _finish_recovered_memory_proposal(runtime_dir, proposal, target)
        try:
            result = apply_writeback_with_audit(
                proposal["workspace_root"],
                proposal["relative_path"],
                _proposal_apply_contents(proposal),
                runtime_dir=runtime_dir,
                action_id=str(proposal.get("request_id") or ""),
                confirm=True,
                require_absent=True,
                redact_audit_root=True,
            )
        except WritebackError as exc:
            if "already exists" not in str(exc):
                raise
            target = safe_resolve_workspace_path(
                proposal["workspace_root"],
                proposal["relative_path"],
            )
            return _finish_recovered_memory_proposal(runtime_dir, proposal, target)
        _set_proposal_status(runtime_dir, proposal, "applied")
        return {
            "request_id": str(proposal.get("request_id") or ""),
            "applied": True,
            "status": "applied",
            **_public_apply_result(proposal, result),
        }
    finally:
        _release_recovery_lock(lock)


def _public_apply_result(proposal: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    if str(proposal.get("proposal_kind") or "") != "obsidian_memory_candidate":
        return result
    allowed = {
        "applied",
        "action_id",
        "action_run_id",
        "kind",
        "relative_path",
        "operation",
        "bytes_written",
        "bytes_before",
        "applied_at",
    }
    return {key: value for key, value in result.items() if key in allowed}


def resolve_writeback_proposal(
    runtime_dir: str | Path,
    request_id: str,
    decision: str,
    *,
    expected_thread_id: str | None = None,
) -> dict[str, Any]:
    """Apply (approve) or discard (reject) a staged write-back proposal.

    The human gate lives at the caller (the approval endpoint); this consumes a
    proposal exactly once. When ``expected_thread_id`` is given it must match the
    proposal's recorded thread. Returns a summary describing what happened.
    """
    rid = _safe_request_id(request_id)
    if decision not in {"approve", "reject"}:
        raise WritebackError("invalid write-back decision")
    proposal, claimed = _claim_pending_proposal(
        runtime_dir,
        rid,
        expected_thread_id=expected_thread_id,
    )
    if not claimed:
        if decision == "approve" and str(proposal.get("status") or "") == "applying":
            recovered = _recover_memory_proposal(
                runtime_dir,
                proposal,
                expected_thread_id=expected_thread_id,
            )
            if recovered is not None:
                return recovered
        return {
            "request_id": rid,
            "applied": False,
            "already_resolved": True,
            "status": str(proposal.get("status") or "unknown"),
        }
    if decision == "reject":
        _set_proposal_status(runtime_dir, proposal, "rejected")
        return {"request_id": rid, "applied": False, "status": "rejected"}

    try:
        result = apply_writeback_with_audit(
            proposal["workspace_root"],
            proposal["relative_path"],
            _proposal_apply_contents(proposal),
            runtime_dir=runtime_dir,
            action_id=rid,
            confirm=True,
            require_absent=bool(proposal.get("require_absent")),
            redact_audit_root=bool(proposal.get("redact_preview_root")),
        )
    except (WritebackError, OSError, ValueError):
        _set_proposal_status(runtime_dir, proposal, "failed", failure="apply_rejected")
        raise
    _set_proposal_status(runtime_dir, proposal, "applied")
    return {
        "request_id": rid,
        "applied": True,
        "status": "applied",
        **_public_apply_result(proposal, result),
    }


def list_pending_writeback_proposals(runtime_dir: str | Path) -> list[dict[str, Any]]:
    """Return pending (not yet approved/rejected) write-back proposals."""
    directory = _proposals_dir(runtime_dir)
    if not directory.is_dir():
        return []
    pending: list[dict[str, Any]] = []
    for path in sorted(directory.glob("wb-*.json")):
        try:
            proposal = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if str(proposal.get("status") or "") != "pending":
            continue
        pending.append(
            {
                "request_id": proposal.get("request_id"),
                "relative_path": proposal.get("relative_path"),
                "project_id": proposal.get("project_id"),
                "thread_id": proposal.get("thread_id"),
                "preview": proposal.get("preview"),
                "staged_at": proposal.get("staged_at"),
            }
        )
    return pending
