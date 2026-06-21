"""Persistent rdgoal digest built from runtime files."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .backup_guard import default_runtime_dir
from .runtime_store import RuntimeStore


def build_runtime_digest(runtime_dir: str | Path | None = None) -> dict[str, Any]:
    runtime = Path(runtime_dir).resolve() if runtime_dir else default_runtime_dir()
    events = RuntimeStore(runtime_dir=runtime).read_all()
    projects: dict[str, dict[str, Any]] = {}
    dispatches: list[dict[str, Any]] = []

    for event in events:
        project_id = event.get("project_id", "")
        payload = event.get("payload", {})
        if event.get("event_type") == "project_registered":
            projects[project_id] = {
                "project_id": project_id,
                "project_root": payload.get("project_root", ""),
                "priority": payload.get("priority", ""),
            }
        elif event.get("event_type") == "decision_made":
            packet_dir = payload.get("packet_dir", "")
            dispatches.append({
                "project_id": project_id,
                "operation": payload.get("operation", ""),
                "decision_mode": payload.get("decision_mode", ""),
                "dispatch_ready": payload.get("dispatch_ready", False),
                "reason": payload.get("reason", ""),
                "snapshot": payload.get("snapshot"),
                "packet_dir": packet_dir,
                "packet_id": Path(packet_dir).name if packet_dir else "",
                "timestamp": event.get("timestamp", ""),
            })

    reports = _read_report_summaries(runtime)
    return {
        "runtime_dir": str(runtime),
        "projects": sorted(projects.values(), key=lambda item: item["project_id"]),
        "dispatches": dispatches,
        "reports": reports,
    }


def _read_report_summaries(runtime_dir: Path) -> list[dict[str, Any]]:
    summaries: list[dict[str, Any]] = []
    reports_dir = runtime_dir / "rdgoal-reports"
    if not reports_dir.exists():
        return summaries
    for path in reports_dir.glob("*/*/execution-summary.json"):
        try:
            summaries.append(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError):
            summaries.append({
                "packet_id": path.parent.name,
                "project_id": path.parent.parent.name,
                "status": "unreadable",
                "changed_files": [],
                "report_path": str(path),
            })
    return sorted(summaries, key=lambda item: (item.get("project_id", ""), item.get("packet_id", "")))


def render_runtime_digest_markdown(digest: dict[str, Any]) -> str:
    lines = ["# rdgoal Runtime Digest", ""]
    lines.append(f"- runtime: `{digest['runtime_dir']}`")
    lines.append("")

    lines.append("## Projects")
    if not digest["projects"]:
        lines.append("- none")
    for project in digest["projects"]:
        root = f" root=`{project['project_root']}`" if project.get("project_root") else ""
        priority = f" prio={project['priority']}" if project.get("priority") != "" else ""
        lines.append(f"- {project['project_id']}{priority}{root}")
    lines.append("")

    lines.append("## Decisions")
    if not digest["dispatches"]:
        lines.append("- none")
    for dispatch in digest["dispatches"]:
        ready = "ready" if dispatch.get("dispatch_ready") else "draft/held"
        lines.append(
            f"- {dispatch['project_id']}: {dispatch['operation']} -> "
            f"{dispatch['decision_mode']} ({ready})"
        )
        if dispatch.get("packet_dir"):
            lines.append(f"  packet: `{dispatch['packet_dir']}`")
    lines.append("")

    lines.append("## Execution Reports")
    if not digest["reports"]:
        lines.append("- none")
    for report in digest["reports"]:
        changed_count = len(report.get("changed_files") or [])
        lines.append(
            f"- {report.get('project_id', '')}: {report.get('packet_id', '')} -> "
            f"{report.get('status', 'unknown')} ({changed_count} changed file entries)"
        )
        if report.get("report_path"):
            lines.append(f"  report: `{report['report_path']}`")
    lines.append("")
    return "\n".join(lines)
