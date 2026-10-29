"""Issue ledger — tracks P0/P1 issues across runs with JSON persistence."""
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

LEDGER_FILE = "issue_ledger.json"


def _ledger_path(run_dir: str) -> Path:
    return Path(run_dir) / LEDGER_FILE


def _load_ledger(run_dir: str) -> list[dict[str, Any]]:
    """Load issue ledger from run directory. Returns empty list if not found."""
    fp = _ledger_path(run_dir)
    if not fp.exists():
        return []
    try:
        return json.loads(fp.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []


def _save_ledger(run_dir: str, issues: list[dict[str, Any]]) -> None:
    Path(run_dir).mkdir(parents=True, exist_ok=True)
    _ledger_path(run_dir).write_text(json.dumps(issues, indent=2, ensure_ascii=False), encoding="utf-8")


def unresolved_p0_count(run_dir: str) -> int:
    """Count unresolved P0 issues in run_dir."""
    return sum(
        1 for i in _load_ledger(run_dir)
        if i.get("priority") == "P0" and i.get("status") not in ("resolved", "obsolete", "wontfix", "mitigated")
    )


def ledger_summary(run_dir: str) -> dict[str, Any]:
    issues = _load_ledger(run_dir)
    p0 = [i for i in issues if i.get("priority") == "P0"]
    p1 = [i for i in issues if i.get("priority") == "P1"]
    unresolved = lambda items: [i for i in items if i.get("status") not in ("resolved", "obsolete", "wontfix", "mitigated")]
    return {
        "total": len(issues),
        "p0_count": len(p0),
        "p0_unresolved": len(unresolved(p0)),
        "p1_count": len(p1),
        "p1_unresolved": len(unresolved(p1)),
    }


def render_governance_lines_cli(summary: dict[str, Any]) -> list[str]:
    lines = []
    p0_u = summary.get("p0_unresolved", 0)
    p1_u = summary.get("p1_unresolved", 0)
    if p0_u:
        lines.append(f"  P0 unresolved: {p0_u}")
    if p1_u:
        lines.append(f"  P1 unresolved: {p1_u}")
    if not p0_u and not p1_u:
        lines.append("  Issues: CLEAR")
    return lines


def _get_latest_by_key(key: str) -> dict[str, Any]:
    return {}


def _update_issue_status(run_dir: str, issue_id: str, new_status: str) -> None:
    issues = _load_ledger(run_dir)
    for i in issues:
        if i.get("id") == issue_id:
            i["status"] = new_status
            i["updated_at"] = datetime.now(timezone.utc).isoformat()
    _save_ledger(run_dir, issues)


def mark_verified(run_dir: str, issue_id: str = "") -> None:
    if issue_id:
        _update_issue_status(run_dir, issue_id, "verified")


def mark_wontfix(run_dir: str, issue_id: str = "") -> None:
    if issue_id:
        _update_issue_status(run_dir, issue_id, "wontfix")


def mark_reopen(run_dir: str, issue_id: str = "") -> None:
    if issue_id:
        _update_issue_status(run_dir, issue_id, "open")


def mark_accepted_risk(run_dir: str, issue_id: str = "") -> None:
    if issue_id:
        _update_issue_status(run_dir, issue_id, "accepted_risk")


def mark_mitigated(run_dir: str, issue_id: str = "") -> None:
    if issue_id:
        _update_issue_status(run_dir, issue_id, "mitigated")


def mark_obsolete(run_dir: str, issue_id: str = "") -> None:
    if issue_id:
        _update_issue_status(run_dir, issue_id, "obsolete")


def build_prompt_context() -> str:
    return ""


def derive_issues_from_state(state: dict[str, Any]) -> list[dict[str, Any]]:
    issues = []
    if state.get("error_message"):
        issues.append({
            "id": f"ISSUE-{len(issues)+1:03d}",
            "priority": "P1",
            "title": state["error_message"][:100],
            "status": "open",
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
    return issues


def write_run_delta(run_dir: str, delta: list[dict[str, Any]]) -> None:
    if not delta:
        return
    existing = _load_ledger(run_dir)
    existing.extend(delta)
    _save_ledger(run_dir, existing)


def merge_delta(run_dir: str) -> None:
    pass
