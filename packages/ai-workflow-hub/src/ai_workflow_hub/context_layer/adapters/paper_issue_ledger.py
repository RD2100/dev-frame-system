"""paper_issue_ledger.py — A11 Paper Issue Ledger.

Persistent tracking of PaperReviewIssue items across paper review tasks.
Adapted from the coding domain's issue_ledger.py but tailored for the
PaperReviewIssue schema (issue_type, severity, blocking, human_required).

Design:
  - JSON file persistence per task_id in a configurable ledger directory
  - Severity levels: critical / major / minor / info (mapping to P0/P1 equivalents)
  - Blocking issues are the primary gate (P0 equivalent)
  - Status lifecycle: open → resolved | wontfix | accepted_risk | mitigated | obsolete
  - Integration with A8 (acceptance gate) and A9 (evidence pipeline)
  - Pattern learning: frequency counts by issue_type for feedback loop

File layout:
  {ledger_dir}/{task_id}.json → list of PaperLedgerEntry dicts

PaperLedgerEntry:
  {
    "issue_id": str,           # from PaperReviewIssue
    "issue_type": str,         # structure|argument|citation|...
    "severity": str,           # critical|major|minor|info
    "blocking": bool,
    "evidence": str,
    "recommendation": str,
    "human_required": bool,
    "status": str,             # open|resolved|wontfix|accepted_risk|mitigated|obsolete
    "source": str,             # reviewer name (deterministic_gate, gpt, etc.)
    "evidence_pack_ref": str,  # from acceptance result
    "created_at": str,
    "updated_at": str,
    "resolution_note": str,
  }
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

RESOLVED_STATUSES = {"resolved", "wontfix", "accepted_risk", "mitigated", "obsolete"}
VALID_STATUSES = {"open", "resolved", "wontfix", "accepted_risk", "mitigated", "obsolete"}
SEVERITY_RANK = {"critical": 4, "major": 3, "minor": 2, "info": 1}


# ---------------------------------------------------------------------------
# Internal I/O
# ---------------------------------------------------------------------------

def _ledger_dir_default() -> Path:
    """Default ledger directory under the hub's working area."""
    return Path(__file__).resolve().parent.parent.parent.parent / "paper_ledger"


def _ledger_path(task_id: str, ledger_dir: str | Path | None = None) -> Path:
    base = Path(ledger_dir) if ledger_dir else _ledger_dir_default()
    return base / f"{task_id}.json"


def _load(task_id: str, ledger_dir: str | Path | None = None) -> list[dict[str, Any]]:
    """Load ledger entries for a task. Returns empty list if not found."""
    fp = _ledger_path(task_id, ledger_dir)
    if not fp.exists():
        return []
    try:
        data = json.loads(fp.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return data
        return []
    except (json.JSONDecodeError, OSError):
        return []


def _save(task_id: str, entries: list[dict[str, Any]], ledger_dir: str | Path | None = None) -> None:
    """Save ledger entries for a task."""
    fp = _ledger_path(task_id, ledger_dir)
    fp.parent.mkdir(parents=True, exist_ok=True)
    fp.write_text(
        json.dumps(entries, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# Public API: Ingestion
# ---------------------------------------------------------------------------

def ingest_issues(
    task_id: str,
    issues: list[dict[str, Any]],
    source: str = "deterministic_gate",
    evidence_pack_ref: str = "",
    ledger_dir: str | Path | None = None,
) -> int:
    """Ingest PaperReviewIssue dicts into the ledger.

    Creates new entries for issues not yet in the ledger.
    Existing issues (matched by issue_id) are not duplicated.

    Args:
        task_id: Task identifier for this ledger.
        issues: List of PaperReviewIssue dicts (from A5/A8/A9).
        source: Reviewer source tag.
        evidence_pack_ref: Reference to the evidence pack.
        ledger_dir: Optional override for ledger storage directory.

    Returns:
        Number of new entries added.
    """
    existing = _load(task_id, ledger_dir)
    existing_ids = {e.get("issue_id") for e in existing}
    now = datetime.now(timezone.utc).isoformat()
    added = 0

    for issue in issues:
        iid = issue.get("issue_id", "")
        if not iid or iid in existing_ids:
            continue
        entry = {
            "issue_id": iid,
            "issue_type": issue.get("issue_type", ""),
            "severity": issue.get("severity", "info"),
            "blocking": issue.get("blocking", False),
            "evidence": issue.get("evidence", ""),
            "recommendation": issue.get("recommendation", ""),
            "human_required": issue.get("human_required", False),
            "status": "open",
            "source": source,
            "evidence_pack_ref": evidence_pack_ref,
            "created_at": now,
            "updated_at": now,
            "resolution_note": "",
        }
        existing.append(entry)
        existing_ids.add(iid)
        added += 1

    if added > 0:
        _save(task_id, existing, ledger_dir)

    return added


# ---------------------------------------------------------------------------
# Public API: Query
# ---------------------------------------------------------------------------

def get_all_issues(
    task_id: str,
    ledger_dir: str | Path | None = None,
) -> list[dict[str, Any]]:
    """Get all ledger entries for a task."""
    return _load(task_id, ledger_dir)


def get_open_issues(
    task_id: str,
    ledger_dir: str | Path | None = None,
) -> list[dict[str, Any]]:
    """Get unresolved (status=open) entries for a task."""
    return [e for e in _load(task_id, ledger_dir) if e.get("status") == "open"]


def blocking_count(
    task_id: str,
    ledger_dir: str | Path | None = None,
) -> int:
    """Count unresolved blocking issues."""
    return sum(
        1 for e in _load(task_id, ledger_dir)
        if e.get("blocking") and e.get("status") not in RESOLVED_STATUSES
    )


def critical_count(
    task_id: str,
    ledger_dir: str | Path | None = None,
) -> int:
    """Count unresolved critical-severity issues."""
    return sum(
        1 for e in _load(task_id, ledger_dir)
        if e.get("severity") == "critical" and e.get("status") not in RESOLVED_STATUSES
    )


def is_clear(
    task_id: str,
    ledger_dir: str | Path | None = None,
) -> bool:
    """Check if all blocking/critical issues are resolved."""
    entries = _load(task_id, ledger_dir)
    for e in entries:
        if e.get("status") in RESOLVED_STATUSES:
            continue
        if e.get("blocking") or e.get("severity") == "critical":
            return False
    return True


def ledger_summary(
    task_id: str,
    ledger_dir: str | Path | None = None,
) -> dict[str, Any]:
    """Generate a summary of the issue ledger for a task.

    Returns:
        dict with total, blocking, critical, open, resolved counts
        and severity/type breakdowns.
    """
    entries = _load(task_id, ledger_dir)
    open_entries = [e for e in entries if e.get("status") == "open"]
    resolved_entries = [e for e in entries if e.get("status") in RESOLVED_STATUSES]

    # Severity breakdown (open only)
    severity_breakdown: dict[str, int] = {}
    for e in open_entries:
        sev = e.get("severity", "info")
        severity_breakdown[sev] = severity_breakdown.get(sev, 0) + 1

    # Type breakdown (open only)
    type_breakdown: dict[str, int] = {}
    for e in open_entries:
        it = e.get("issue_type", "unknown")
        type_breakdown[it] = type_breakdown.get(it, 0) + 1

    return {
        "task_id": task_id,
        "total": len(entries),
        "open": len(open_entries),
        "resolved": len(resolved_entries),
        "blocking": sum(1 for e in open_entries if e.get("blocking")),
        "critical": sum(1 for e in open_entries if e.get("severity") == "critical"),
        "human_required": sum(1 for e in open_entries if e.get("human_required")),
        "severity_breakdown": severity_breakdown,
        "type_breakdown": type_breakdown,
    }


# ---------------------------------------------------------------------------
# Public API: Status Updates
# ---------------------------------------------------------------------------

def update_issue_status(
    task_id: str,
    issue_id: str,
    new_status: str,
    resolution_note: str = "",
    ledger_dir: str | Path | None = None,
) -> bool:
    """Update the status of a specific issue.

    Args:
        task_id: Task identifier.
        issue_id: Issue to update.
        new_status: New status (must be in VALID_STATUSES).
        resolution_note: Optional note explaining the resolution.
        ledger_dir: Optional override for ledger directory.

    Returns:
        True if the issue was found and updated, False otherwise.
    """
    if new_status not in VALID_STATUSES:
        raise ValueError(f"Invalid status: {new_status}. Must be one of {VALID_STATUSES}")

    entries = _load(task_id, ledger_dir)
    now = datetime.now(timezone.utc).isoformat()
    found = False

    for e in entries:
        if e.get("issue_id") == issue_id:
            e["status"] = new_status
            e["updated_at"] = now
            if resolution_note:
                e["resolution_note"] = resolution_note
            found = True
            break

    if found:
        _save(task_id, entries, ledger_dir)

    return found


def mark_resolved(task_id: str, issue_id: str, note: str = "",
                 ledger_dir: str | Path | None = None) -> bool:
    """Mark an issue as resolved."""
    return update_issue_status(task_id, issue_id, "resolved", note, ledger_dir)


def mark_wontfix(task_id: str, issue_id: str, note: str = "",
                 ledger_dir: str | Path | None = None) -> bool:
    """Mark an issue as won't fix."""
    return update_issue_status(task_id, issue_id, "wontfix", note, ledger_dir)


def mark_accepted_risk(task_id: str, issue_id: str, note: str = "",
                       ledger_dir: str | Path | None = None) -> bool:
    """Mark an issue as accepted risk."""
    return update_issue_status(task_id, issue_id, "accepted_risk", note, ledger_dir)


def mark_mitigated(task_id: str, issue_id: str, note: str = "",
                   ledger_dir: str | Path | None = None) -> bool:
    """Mark an issue as mitigated."""
    return update_issue_status(task_id, issue_id, "mitigated", note, ledger_dir)


def mark_obsolete(task_id: str, issue_id: str, note: str = "",
                  ledger_dir: str | Path | None = None) -> bool:
    """Mark an issue as obsolete."""
    return update_issue_status(task_id, issue_id, "obsolete", note, ledger_dir)


def reopen_issue(task_id: str, issue_id: str,
                 ledger_dir: str | Path | None = None) -> bool:
    """Reopen a previously resolved issue."""
    return update_issue_status(task_id, issue_id, "open", "", ledger_dir)


# ---------------------------------------------------------------------------
# Public API: Batch Operations
# ---------------------------------------------------------------------------

def resolve_all(
    task_id: str,
    status: str = "resolved",
    ledger_dir: str | Path | None = None,
) -> int:
    """Resolve all open issues with a given status.

    Returns:
        Number of issues resolved.
    """
    if status not in RESOLVED_STATUSES:
        raise ValueError(f"Status must be a resolved status: {RESOLVED_STATUSES}")

    entries = _load(task_id, ledger_dir)
    now = datetime.now(timezone.utc).isoformat()
    count = 0

    for e in entries:
        if e.get("status") == "open":
            e["status"] = status
            e["updated_at"] = now
            count += 1

    if count > 0:
        _save(task_id, entries, ledger_dir)

    return count


def delete_ledger(
    task_id: str,
    ledger_dir: str | Path | None = None,
) -> bool:
    """Delete the entire ledger for a task.

    Returns:
        True if ledger existed and was deleted.
    """
    fp = _ledger_path(task_id, ledger_dir)
    if fp.exists():
        fp.unlink()
        return True
    return False


# ---------------------------------------------------------------------------
# Public API: Learning / Pattern Detection
# ---------------------------------------------------------------------------

def issue_type_frequency(
    task_id: str,
    ledger_dir: str | Path | None = None,
) -> dict[str, dict[str, int]]:
    """Compute issue type frequency (total and resolved) for feedback loop.

    Returns:
        dict of {issue_type: {"total": N, "resolved": N, "open": N}}
    """
    entries = _load(task_id, ledger_dir)
    freq: dict[str, dict[str, int]] = {}

    for e in entries:
        it = e.get("issue_type", "unknown")
        if it not in freq:
            freq[it] = {"total": 0, "resolved": 0, "open": 0}
        freq[it]["total"] += 1
        if e.get("status") in RESOLVED_STATUSES:
            freq[it]["resolved"] += 1
        elif e.get("status") == "open":
            freq[it]["open"] += 1

    return freq


def build_prompt_context(
    task_id: str,
    ledger_dir: str | Path | None = None,
    max_lines: int = 20,
) -> str:
    """Build a prompt context string from the ledger for GPT review.

    Includes unresolved blocking/critical issues and type frequency.

    Args:
        task_id: Task identifier.
        ledger_dir: Optional ledger directory override.
        max_lines: Maximum number of issue lines to include.

    Returns:
        Multi-line string suitable for inclusion in a prompt.
    """
    entries = _load(task_id, ledger_dir)
    if not entries:
        return ""

    lines: list[str] = []

    # Unresolved blocking/critical first
    blocking_open = [
        e for e in entries
        if e.get("status") == "open" and (e.get("blocking") or e.get("severity") == "critical")
    ]
    if blocking_open:
        lines.append(f"## Unresolved Blocking/Critical Issues ({len(blocking_open)})")
        for e in blocking_open[:max_lines]:
            lines.append(
                f"  [{e['issue_id']}] {e.get('issue_type', '?')}/{e.get('severity', '?')}: "
                f"{e.get('evidence', '')[:80]}"
            )
        if len(blocking_open) > max_lines:
            lines.append(f"  ... and {len(blocking_open) - max_lines} more")

    # Type frequency summary
    freq = issue_type_frequency(task_id, ledger_dir)
    if freq:
        lines.append("## Issue Type Frequency")
        for it, counts in sorted(freq.items()):
            lines.append(f"  {it}: {counts['total']} total, {counts['resolved']} resolved, {counts['open']} open")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Public API: Integration with A8/A9
# ---------------------------------------------------------------------------

def ingest_from_acceptance_result(
    task_id: str,
    acceptance_result: dict[str, Any],
    ledger_dir: str | Path | None = None,
) -> int:
    """Ingest issues from a PaperAcceptanceResult (A8 output).

    Extracts both blocking_issues and non_blocking_issues and adds
    them to the ledger.

    Args:
        task_id: Task identifier.
        acceptance_result: PaperAcceptanceResult dict from compute_acceptance.
        ledger_dir: Optional ledger directory override.

    Returns:
        Number of new entries added.
    """
    all_issues = (
        acceptance_result.get("blocking_issues", [])
        + acceptance_result.get("non_blocking_issues", [])
    )
    source = acceptance_result.get("reviewer", "deterministic_gate")
    ref = acceptance_result.get("evidence_pack_ref", "")

    return ingest_issues(task_id, all_issues, source=source,
                        evidence_pack_ref=ref, ledger_dir=ledger_dir)
