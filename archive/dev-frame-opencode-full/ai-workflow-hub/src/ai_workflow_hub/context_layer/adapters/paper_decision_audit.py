"""paper_decision_audit.py — A14/A15: Human Decision Audit Trail for Paper Workflow.

Provides structured decision persistence and audit logging for the paper
domain's human gate. Follows the coding domain's patterns:

  - Decision file: {decisions_dir}/{task_id}-decision.json (atomic write)
  - Audit log: JSONL append-only entries with file locking (A15)
  - audit_log() integration for global audit trail

A15 Hardening:
  - task_id sanitization (prevent path traversal)
  - reviewer_id enforcement (require_reviewer flag)
  - Atomic JSONL append via file locking
  - Stale decision detection
  - Decision round tracking

Public API:
  sanitize_task_id(...)      → safe filename from task_id
  record_decision(...)       → persist decision record to JSON file
  read_decision_record(...)  → read decision record from disk
  get_audit_trail(...)       → read all audit entries for a task
  log_decision_audit(...)    → emit global audit_log entry
  is_decision_stale(...)     → check if decision exceeds max age
  get_decision_count(...)    → count decision rounds for a task
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

VALID_DECISIONS = {"approved", "rejected"}
DECISION_SCHEMA_VERSION = "2.0"
_MAX_TASK_ID_LEN = 128
_SAFE_CHARS = re.compile(r"[^a-zA-Z0-9_\-\.]")
_STALE_SECONDS_DEFAULT = 7 * 24 * 3600  # 7 days


# ---------------------------------------------------------------------------
# task_id sanitization (A15)
# ---------------------------------------------------------------------------

def sanitize_task_id(task_id: str) -> str:
    """Sanitize task_id for safe use in filesystem paths (A15).

    Rules:
      - Replace unsafe chars (path separators, etc.) with underscore
      - Collapse consecutive underscores
      - Strip leading dots (prevent hidden files)
      - Truncate to _MAX_TASK_ID_LEN characters
      - Raise ValueError for empty result

    Args:
        task_id: Raw task identifier.

    Returns:
        Sanitized string safe for use in filenames.

    Raises:
        ValueError: If task_id is empty or produces empty after sanitization.
    """
    if not task_id or not task_id.strip():
        raise ValueError("task_id must be a non-empty string")

    safe = _SAFE_CHARS.sub("_", task_id.strip())
    safe = re.sub(r"_+", "_", safe)
    # Strip leading dots and remove ".." sequences (prevent path traversal)
    safe = safe.replace("..", "_")
    safe = re.sub(r"_+", "_", safe)
    safe = safe.lstrip(".")
    safe = safe[:_MAX_TASK_ID_LEN]

    if not safe:
        raise ValueError(
            f"task_id {task_id!r} produces empty string after sanitization"
        )
    return safe


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _decisions_dir(base_dir: str | None = None) -> Path:
    """Resolve the decisions directory, creating if needed."""
    if base_dir:
        d = Path(base_dir) / "decisions"
    else:
        # Default: hub_dir/runs/audit/paper-decisions
        from ...config_loader import _hub_dir
        d = _hub_dir() / "runs" / "audit" / "paper-decisions"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _decision_path(task_id: str, base_dir: str | None = None) -> Path:
    """Path to the decision record JSON file (sanitized task_id)."""
    safe_id = sanitize_task_id(task_id)
    return _decisions_dir(base_dir) / f"{safe_id}-decision.json"


def _audit_trail_path(task_id: str, base_dir: str | None = None) -> Path:
    """Path to the per-task audit trail JSONL file (sanitized task_id)."""
    safe_id = sanitize_task_id(task_id)
    d = _decisions_dir(base_dir)
    return d / f"{safe_id}-audit.jsonl"


# ---------------------------------------------------------------------------
# record_decision — persist decision record (A15: hardened)
# ---------------------------------------------------------------------------

def record_decision(
    task_id: str,
    decision: str,
    reviewer_id: str = "",
    note: str = "",
    context: dict[str, Any] | None = None,
    base_dir: str | None = None,
    require_reviewer: bool = False,
) -> dict[str, Any]:
    """Persist a human gate decision record to disk (atomic write, A15 hardened).

    Args:
        task_id: Task identifier (will be sanitized for filesystem safety).
        decision: "approved" or "rejected".
        reviewer_id: Who made the decision (email, username, or role).
        note: Optional reason or comment.
        context: Optional dict with task metadata (blocking_count, etc.).
        base_dir: Override for decisions directory.
        require_reviewer: If True, raise ValueError when reviewer_id is empty.

    Returns:
        The decision record dict that was written.

    Raises:
        ValueError: If decision is invalid or reviewer_id is empty
                    when require_reviewer=True.
    """
    if decision not in VALID_DECISIONS:
        raise ValueError(
            f"Invalid decision: {decision!r}. Must be one of {VALID_DECISIONS}"
        )
    if require_reviewer and not reviewer_id.strip():
        raise ValueError(
            "reviewer_id is required when require_reviewer=True"
        )

    safe_id = sanitize_task_id(task_id)
    now = datetime.now(timezone.utc).isoformat()

    # Count existing rounds for this task
    round_num = get_decision_count(task_id, base_dir) + 1

    record = {
        "decision_id": f"{safe_id}-decision",
        "task_id": task_id,
        "decision": decision,
        "reviewer_id": reviewer_id,
        "timestamp": now,
        "note": note,
        "context": context or {},
        "schema_version": DECISION_SCHEMA_VERSION,
        "round": round_num,
    }

    path = _decision_path(task_id, base_dir)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(
        json.dumps(record, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    tmp.replace(path)

    # Also append to per-task audit trail (with file locking)
    _append_audit_entry(task_id, record, base_dir)

    return record


# ---------------------------------------------------------------------------
# read_decision_record — read from disk
# ---------------------------------------------------------------------------

def read_decision_record(
    task_id: str,
    base_dir: str | None = None,
) -> dict[str, Any] | None:
    """Read a decision record from disk.

    Returns:
        The decision record dict, or None if file does not exist.
    """
    path = _decision_path(task_id, base_dir)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


# ---------------------------------------------------------------------------
# get_audit_trail — read all audit entries
# ---------------------------------------------------------------------------

def get_audit_trail(
    task_id: str,
    base_dir: str | None = None,
) -> list[dict[str, Any]]:
    """Read all audit trail entries for a task.

    Returns:
        List of audit entries (JSONL parsed), empty list if none.
    """
    path = _audit_trail_path(task_id, base_dir)
    if not path.exists():
        return []
    entries = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                entries.append(json.loads(line))
    except (json.JSONDecodeError, OSError):
        pass
    return entries


# ---------------------------------------------------------------------------
# log_decision_audit — global audit_log integration
# ---------------------------------------------------------------------------

def log_decision_audit(
    task_id: str,
    decision: str,
    reviewer_id: str = "",
    note: str = "",
    run_id: str = "",
    project_id: str = "",
) -> None:
    """Emit a global audit_log entry for the human gate decision.

    Calls audit_log() from the core audit module.
    """
    try:
        from ...audit import audit_log
        audit_log(
            action="paper_human_gate_decision",
            result=decision,
            allowed=(decision == "approved"),
            reason=note,
            project_id=project_id,
            task_id=task_id,
            run_id=run_id,
            reviewer_id=reviewer_id,
        )
    except Exception:
        # audit_log is best-effort; don't block workflow on failure
        pass


# ---------------------------------------------------------------------------
# is_decision_stale — stale decision detection (A15)
# ---------------------------------------------------------------------------

def is_decision_stale(
    task_id: str,
    base_dir: str | None = None,
    max_age_seconds: int = _STALE_SECONDS_DEFAULT,
) -> bool:
    """Check if the latest decision for a task exceeds max age (A15).

    Args:
        task_id: Task identifier.
        base_dir: Override for decisions directory.
        max_age_seconds: Maximum age in seconds (default: 7 days).

    Returns:
        True if the decision is older than max_age_seconds, False otherwise.
        Returns False if no decision exists.
    """
    rec = read_decision_record(task_id, base_dir)
    if rec is None:
        return False
    ts_str = rec.get("timestamp", "")
    if not ts_str:
        return True  # no timestamp → treat as stale
    try:
        ts = datetime.fromisoformat(ts_str)
        age = (datetime.now(timezone.utc) - ts).total_seconds()
        return age > max_age_seconds
    except (ValueError, TypeError):
        return True  # unparseable timestamp → stale


# ---------------------------------------------------------------------------
# get_decision_count — count decision rounds (A15)
# ---------------------------------------------------------------------------

def get_decision_count(
    task_id: str,
    base_dir: str | None = None,
) -> int:
    """Count the number of decision rounds recorded in the audit trail (A15).

    Returns:
        Number of entries in the audit trail for this task.
    """
    return len(get_audit_trail(task_id, base_dir))


# ---------------------------------------------------------------------------
# Internal: append to per-task audit trail (A15: file locking)
# ---------------------------------------------------------------------------

def _append_audit_entry(
    task_id: str,
    record: dict[str, Any],
    base_dir: str | None = None,
) -> None:
    """Append a JSONL entry to the per-task audit trail file (A15: locked)."""
    path = _audit_trail_path(task_id, base_dir)
    entry = {
        "timestamp": record.get("timestamp", ""),
        "event": "decision_recorded",
        "decision": record.get("decision", ""),
        "reviewer_id": record.get("reviewer_id", ""),
        "note": record.get("note", ""),
        "round": record.get("round", 1),
    }
    try:
        _locked_append(path, json.dumps(entry, ensure_ascii=False) + "\n")
    except OSError:
        pass


def _locked_append(path: Path, data: str) -> None:
    """Append data to a file with advisory file locking (A15).

    Uses msvcrt on Windows, fcntl on Unix. Falls back to plain append
    if locking is unavailable.
    """
    try:
        import msvcrt
        with open(path, "a", encoding="utf-8") as f:
            try:
                msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
            except (OSError, IOError):
                pass  # lock unavailable, proceed without
            f.write(data)
            try:
                f.seek(0)
                msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
            except (OSError, IOError):
                pass
    except ImportError:
        # Unix: try fcntl
        try:
            import fcntl
            with open(path, "a", encoding="utf-8") as f:
                try:
                    fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                except (OSError, IOError):
                    pass
                f.write(data)
                try:
                    fcntl.flock(f.fileno(), fcntl.LOCK_UN)
                except (OSError, IOError):
                    pass
        except ImportError:
            # No locking available at all
            with open(path, "a", encoding="utf-8") as f:
                f.write(data)
