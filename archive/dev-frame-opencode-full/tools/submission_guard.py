"""Submission guard — prevent duplicate GPT submissions and track attempts.

Usage:
    from tools.submission_guard import check_before_submit, record_submission

    ok, reason = check_before_submit(report_dir, review_run_id)
    if not ok:
        print(f"BLOCKED: {reason}")
        return

    # ... submit to GPT ...

    record_submission(report_dir, review_run_id, success=True)
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path

SUBMISSION_LOG = "SUBMISSION_LOG.jsonl"
MAX_RESUBMITS = 3
COOLDOWN_SECONDS = 30


def _log_path(report_dir: str | Path) -> Path:
    return Path(report_dir) / SUBMISSION_LOG


def _read_log(report_dir: str | Path) -> list[dict]:
    path = _log_path(report_dir)
    if not path.exists():
        return []
    entries = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return entries


def check_before_submit(
    report_dir: str | Path,
    review_run_id: str,
    max_resubmits: int = MAX_RESUBMITS,
    cooldown_seconds: int = COOLDOWN_SECONDS,
) -> tuple[bool, str]:
    """Check if submission is allowed for this REVIEW_RUN_ID.

    Returns:
        (ok: bool, reason: str)
    """
    entries = _read_log(report_dir)
    attempts = [e for e in entries if e.get("review_run_id") == review_run_id]

    if not attempts:
        return True, "first_submission"

    last = attempts[-1]
    last_time = last.get("timestamp", 0)

    # Cooldown check
    elapsed = time.time() - last_time
    if elapsed < cooldown_seconds:
        return False, f"cooldown_active: {elapsed:.0f}s elapsed, need {cooldown_seconds}s"

    # Resubmit count check
    submit_count = sum(1 for e in attempts if e.get("action") == "submit")
    if submit_count >= max_resubmits:
        return False, f"max_resubmits_exceeded: {submit_count}/{max_resubmits}"

    # Allowed: this is a re-submission within limits
    return True, f"resubmit_allowed: attempt {submit_count + 1}/{max_resubmits}"


def record_submission(
    report_dir: str | Path,
    review_run_id: str,
    success: bool = True,
    action: str = "submit",
    detail: str = "",
) -> Path:
    """Record a submission event in the log."""
    path = _log_path(report_dir)
    entry = {
        "review_run_id": review_run_id,
        "action": action,
        "success": success,
        "timestamp": time.time(),
        "iso": datetime.now(timezone.utc).isoformat(),
        "detail": detail,
    }
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return path


def pre_submit_gate(report_dir: Path, review_run_id: str) -> bool:
    """Gate check before CDP submission. Returns True or sys.exit(10)."""
    import sys
    # Pre-check: log directory must be writable
    log_path = Path(report_dir) / SUBMISSION_LOG
    if log_path.exists():
        try:
            log_path.open("a").close()
        except (OSError, PermissionError):
            print(f"GATE BLOCKED: submission log directory not writable: {report_dir}")
            sys.exit(10)
    else:
        try:
            log_path.parent.mkdir(parents=True, exist_ok=True)
            log_path.touch()
            log_path.unlink()
        except (OSError, PermissionError):
            print(f"GATE BLOCKED: cannot create submission log in: {report_dir}")
            sys.exit(10)

    ok, reason = check_before_submit(report_dir, review_run_id)
    if not ok:
        print(f"GATE BLOCKED: {reason}")
        sys.exit(10)
    print(f"GATE: allowed ({reason})")
    return True


def record_submission_result(
    report_dir: Path,
    review_run_id: str,
    success: bool,
    detail: str = "",
) -> bool:
    """Record submission in log. Returns True if logged, False if write failed."""
    try:
        record_submission(
            report_dir=report_dir,
            review_run_id=review_run_id,
            success=success,
            action="submit_cdp",
            detail=detail,
        )
        return True
    except (OSError, PermissionError, Exception) as e:
        print(f"SUBMISSION LOG WRITE FAILED: {e}")
        print(f"  REVIEW_RUN_ID={review_run_id} was sent but NOT logged.")
        print(f"  auto-chain MUST stop. review_unverified.")
        return False


def get_submission_summary(report_dir: str | Path) -> dict:
    """Return a summary of submissions for this pack."""
    entries = _read_log(report_dir)
    by_rid: dict[str, list[dict]] = {}
    for e in entries:
        rid = e.get("review_run_id", "unknown")
        by_rid.setdefault(rid, []).append(e)

    return {
        "total_entries": len(entries),
        "unique_rids": len(by_rid),
        "by_review_run_id": {
            rid: {
                "attempts": len(attempts),
                "last_success": any(e.get("success") for e in attempts),
            }
            for rid, attempts in by_rid.items()
        },
    }
