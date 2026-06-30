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
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DEFAULT_MAX_WRITEBACK_BYTES = 2_000_000

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
        "node_modules",
        "id_rsa",
        "credentials",
        "secrets",
    }
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


def safe_resolve_workspace_path(workspace_root: str | Path, relative_path: str) -> Path:
    """Resolve ``relative_path`` under ``workspace_root`` or raise WritebackError.

    The returned path is guaranteed (symlinks resolved) to be strictly under the
    real workspace root.
    """
    try:
        root = Path(workspace_root).resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise WritebackError(f"workspace root is not accessible: {exc}") from exc
    if not root.is_dir():
        raise WritebackError("workspace root is not a directory")

    rel = str(relative_path or "").strip()
    if not rel:
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
        if _is_sensitive_part(part):
            raise WritebackError(f"refusing to write sensitive path component: {part}")

    target = root / candidate

    # Reject if any existing ancestor (or the target) is a symlink, which could
    # redirect the write outside the workspace even if names look clean.
    probe = target
    while True:
        if probe == root:
            break
        if probe.is_symlink():
            raise WritebackError("refusing to write through a symlink")
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
    if target.is_symlink():
        raise WritebackError("refusing to write through a symlink")
    if target.exists() and target.is_dir():
        raise WritebackError("target path is an existing directory")

    existed = target.exists()
    before_size = target.stat().st_size if existed else 0
    target.parent.mkdir(parents=True, exist_ok=True)

    tmp = target.parent / (target.name + ".devframe-writeback.tmp")
    try:
        tmp.write_bytes(data)
        os.replace(tmp, target)
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
    if target.is_symlink():
        raise WritebackError("refusing to write through a symlink")
    if target.exists() and target.is_dir():
        raise WritebackError("target path is an existing directory")
    root = Path(workspace_root).resolve()
    existed = target.exists()
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
) -> dict[str, Any]:
    """Human-gated, audited single-file write-back.

    Without ``confirm`` this returns a ``human_required`` gate preview and writes
    nothing (the caller — a CLI ``--confirm`` flag or the dashboard
    ``confirm=execute`` / approval gate — must explicitly confirm). With
    ``confirm`` it applies the write and, when ``runtime_dir`` is given, persists
    an ``action-run.json`` audit record under ``writeback-runs/``.
    """
    preview = preview_single_file_writeback(
        workspace_root, relative_path, contents, max_bytes=max_bytes
    )
    if not confirm:
        return {
            "applied": False,
            "human_required": True,
            "confirm": "re-run with confirm=execute to apply this write-back through the human gate",
            **preview,
        }

    record = apply_single_file_writeback(
        workspace_root, relative_path, contents, max_bytes=max_bytes
    )
    stamp = time.strftime("%Y%m%d-%H%M%S")
    resolved_action_id = (action_id or "").strip() or f"writeback-{stamp}"
    audit: dict[str, Any] = {
        "applied": True,
        "action_id": resolved_action_id,
        "action_run_id": stamp,
        **record,
    }
    if runtime_dir is not None:
        runtime_root = Path(runtime_dir).resolve()
        audit_path = runtime_root / "writeback-runs" / resolved_action_id / f"{stamp}.json"
        _atomic_json_write(audit_path, audit)
        audit["audit_path"] = str(audit_path)
    return audit


import re
import secrets

_REQUEST_ID_RE = re.compile(r"^wb-[0-9a-f]{16}$")


def _proposals_dir(runtime_dir: str | Path) -> Path:
    return Path(runtime_dir).resolve() / "writeback-proposals"


def _safe_request_id(request_id: str) -> str:
    rid = str(request_id or "").strip()
    if not _REQUEST_ID_RE.match(rid):
        raise WritebackError("invalid write-back request id")
    return rid


def stage_writeback_proposal(
    runtime_dir: str | Path,
    workspace_root: str | Path,
    relative_path: str,
    contents: str,
    *,
    thread_id: str = "",
    project_id: str = "",
    max_bytes: int = DEFAULT_MAX_WRITEBACK_BYTES,
) -> dict[str, Any]:
    """Validate and stage a proposed write-back as a pending, human-gated item.

    Staging never writes to the workspace; it records the proposal so a later
    human approval can apply it. Returns ``{request_id, preview}``.
    """
    preview = preview_single_file_writeback(
        workspace_root, relative_path, contents, max_bytes=max_bytes
    )
    request_id = "wb-" + secrets.token_hex(8)
    proposal = {
        "request_id": request_id,
        "status": "pending",
        "workspace_root": str(Path(workspace_root).resolve()),
        "relative_path": preview["relative_path"],
        "contents": contents,
        "thread_id": str(thread_id or ""),
        "project_id": str(project_id or ""),
        "preview": preview,
        "staged_at": datetime.now(timezone.utc).isoformat(),
    }
    _atomic_json_write(_proposals_dir(runtime_dir) / f"{request_id}.json", proposal)
    return {"request_id": request_id, "preview": preview}


def load_writeback_proposal(runtime_dir: str | Path, request_id: str) -> dict[str, Any] | None:
    rid = _safe_request_id(request_id)
    path = _proposals_dir(runtime_dir) / f"{rid}.json"
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _set_proposal_status(runtime_dir: str | Path, proposal: dict[str, Any], status: str) -> None:
    rid = _safe_request_id(str(proposal.get("request_id") or ""))
    proposal = {**proposal, "status": status, "resolved_at": datetime.now(timezone.utc).isoformat()}
    _atomic_json_write(_proposals_dir(runtime_dir) / f"{rid}.json", proposal)


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
    proposal = load_writeback_proposal(runtime_dir, rid)
    if proposal is None:
        raise WritebackError("write-back proposal not found")
    status = str(proposal.get("status") or "")
    if status != "pending":
        return {
            "request_id": rid,
            "applied": False,
            "already_resolved": True,
            "status": status,
        }
    proposal_thread = str(proposal.get("thread_id") or "")
    if (
        expected_thread_id is not None
        and proposal_thread
        and str(expected_thread_id) != proposal_thread
    ):
        raise WritebackError("write-back thread mismatch")
    if decision == "reject":
        _set_proposal_status(runtime_dir, proposal, "rejected")
        return {"request_id": rid, "applied": False, "status": "rejected"}

    result = apply_writeback_with_audit(
        proposal["workspace_root"],
        proposal["relative_path"],
        proposal["contents"],
        runtime_dir=runtime_dir,
        action_id=rid,
        confirm=True,
    )
    _set_proposal_status(runtime_dir, proposal, "applied")
    return {"request_id": rid, "applied": True, "status": "applied", **result}


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
