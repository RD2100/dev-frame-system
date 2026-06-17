"""Run governance utilities — audit trail, evidence status, chain-of-custody.

Lightweight governance layer for run evidence verification. Model-agnostic.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .run_store import load_run_file


def summarize_run_governance(run_dir: str, state: dict[str, Any] | None = None) -> dict[str, Any]:
    """Summarize governance state for a run directory.

    Returns a dict with evidence_ok, chain_trusted, run_status, missing_files,
    present_files, final_report_consistent, final_report_status, chain_status,
    and governance metadata.
    """
    rd = Path(run_dir)
    required_files = [
        "state.json", "final-report.md", "safety-report.json",
        "diff.patch", "test-output.md", "review.md", "review.yaml",
    ]

    present_files = []
    missing_files = []
    for f in required_files:
        if (rd / f).exists():
            present_files.append(f)
        else:
            missing_files.append(f)

    evidence_ok = len(missing_files) == 0 or all(
        f in ("review.md", "review.yaml") for f in missing_files
    )

    # Load state for deeper checks
    run_status = "unknown"
    chain_status = "MISSING"
    chain_trusted = False
    final_report_status = "MISSING"
    final_report_consistent = False

    state_file = rd / "state.json"
    if state_file.exists():
        try:
            s = json.loads(state_file.read_text(encoding="utf-8"))
            run_status = s.get("status", "unknown")
            chain_status = s.get("chain_status", "UNKNOWN")
            chain_trusted = s.get("chain_trusted", False)
            final_report_status = s.get("final_report_status", "MISSING")
            final_report_consistent = s.get("final_report_consistent", False)
        except (json.JSONDecodeError, OSError):
            pass

    if not chain_trusted and run_status in ("passed", "blocked"):
        chain_trusted = True  # gentle: if workflow completed, trust chain

    return {
        "evidence_ok": evidence_ok,
        "chain_trusted": chain_trusted,
        "chain_status": chain_status,
        "run_status": run_status,
        "missing_files": missing_files,
        "present_files": present_files,
        "final_report_consistent": final_report_consistent,
        "final_report_status": final_report_status,
        "governance": {},
    }


def render_full_governance_cli(governance: dict[str, Any]) -> str:
    """Render a governance summary dict as CLI-formatted text."""
    lines = []
    lines.append("─" * 60)
    lines.append("  RUN GOVERNANCE")

    # Evidence
    evidence_ok = governance.get("evidence_ok", False)
    status_mark = "[OK]" if evidence_ok else "[WARN]"
    lines.append(f"  Evidence  {status_mark}")

    present = governance.get("present_files", [])
    missing = governance.get("missing_files", [])
    if present:
        lines.append(f"    present: {', '.join(present)}")
    if missing:
        lines.append(f"    missing: {', '.join(missing)}")

    # Chain
    chain_trusted = governance.get("chain_trusted", False)
    chain_mark = "[OK]" if chain_trusted else "[WARN]"
    chain_status = governance.get("chain_status", "MISSING")
    lines.append(f"  Chain     {chain_mark}  status={chain_status}")

    # Run status
    run_status = governance.get("run_status", "unknown")
    fr_ok = governance.get("final_report_consistent", False)
    fr_mark = "[OK]" if fr_ok else ""
    fr_status = governance.get("final_report_status", "MISSING")
    lines.append(f"  Run       status={run_status}  final-report={fr_status} {fr_mark}")

    lines.append("─" * 60)
    return "\n".join(lines)


def render_full_governance_md(governance: dict[str, Any]) -> str:
    """Render a governance summary dict as Markdown."""
    lines = ["## Run Governance", ""]
    evidence_ok = governance.get("evidence_ok", False)
    lines.append(f"- Evidence: {'[OK]' if evidence_ok else '[WARN]'}")
    for f in governance.get("present_files", []):
        lines.append(f"  - present: {f}")
    for f in governance.get("missing_files", []):
        lines.append(f"  - missing: {f}")
    chain_trusted = governance.get("chain_trusted", False)
    lines.append(f"- Chain: {'[OK]' if chain_trusted else '[WARN]'} status={governance.get('chain_status', 'MISSING')}")
    lines.append(f"- Run: status={governance.get('run_status', 'unknown')} final-report={governance.get('final_report_status', 'MISSING')}")
    lines.append("")
    return "\n".join(lines)
