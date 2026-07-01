"""Record observed Web GPT MCP tool results as session + evidence files."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from .provider_binding_probe import _safe_id


_VALID_STATUSES = {"completed", "blocked", "failed", "web_host_completed", "web_host_no_result", "local_mcp_completed"}
_VALID_ORIGINS = {"web_host", "local_mcp"}
_VALID_OUTCOMES = {"completed", "blocked", "failed", "no_result"}
_VALID_PRIORITIES = {"high", "medium", "low"}
_VALID_SUGGESTED_AGENTS = {"opencode", "codex", "custom"}
_STATUS_TO_OUTCOME = {
    "completed": "completed",
    "passed": "completed",
    "pass": "completed",
    "executed": "completed",
    "web_host_completed": "completed",
    "local_mcp_completed": "completed",
    "blocked": "blocked",
    "failed": "failed",
    "fail": "failed",
    "web_host_no_result": "no_result",
}


def _outcome_for_status(status: str) -> str:
    return _STATUS_TO_OUTCOME.get(status.lower(), "blocked")


def _origin_for_status(status: str) -> str:
    if status.lower().startswith("local_mcp"):
        return "local_mcp"
    return "web_host"


def _validate_conversation_url(url: str) -> str:
    text = str(url or "").strip()
    if not text:
        raise ValueError("conversation_url is required")
    parsed = urlparse(text)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("conversation_url must be an http or https URL")
    if parsed.username or parsed.password:
        raise ValueError("conversation_url must not include credentials")
    if parsed.query:
        raise ValueError("conversation_url must not include query strings")
    if parsed.fragment:
        raise ValueError("conversation_url must not include fragments")
    return text


def _session_status(value: object) -> str:
    normalized = str(value or "").lower()
    if normalized in {"completed", "passed", "pass", "executed", "web_host_completed", "local_mcp_completed"}:
        return "completed"
    if normalized in {"failed", "fail", "web_host_no_result"}:
        return "blocked"
    if normalized == "blocked":
        return "blocked"
    if normalized in {"needs_human", "human_required", "review_required"}:
        return "needs_human"
    if normalized in {"running", "active"}:
        return "active"
    if normalized in {"pending", "prepared", "queued", "idle"}:
        return "idle"
    return "unknown"


def record_mcp_result(
    runtime_dir: str | Path | None = None,
    *,
    provider: str = "chatgpt",
    project: str = "dev-frame-system",
    conversation_url: str = "",
    connector_name: str | None = None,
    connector_app_id: str | None = None,
    tool_name: str = "",
    status: str = "completed",
    origin: str | None = None,
    outcome: str | None = None,
    marker: str | None = None,
    result_summary: str = "",
    output_id: str | None = None,
    output_name: str | None = None,
) -> dict[str, Any]:
    if status not in _VALID_STATUSES:
        raise ValueError(f"status must be one of {sorted(_VALID_STATUSES)}")
    resolved_origin = origin if origin is not None else _origin_for_status(status)
    if resolved_origin not in _VALID_ORIGINS:
        raise ValueError(f"origin must be one of {sorted(_VALID_ORIGINS)}")
    if outcome is not None and outcome not in _VALID_OUTCOMES:
        raise ValueError(f"outcome must be one of {sorted(_VALID_OUTCOMES)}")
    if not tool_name.strip():
        raise ValueError("tool_name is required")
    if not result_summary.strip():
        raise ValueError("result_summary is required")

    resolved_outcome = outcome if outcome is not None else _outcome_for_status(status)

    safe_conversation_url = _validate_conversation_url(conversation_url)
    safe_provider = _safe_id(provider)
    safe_project = _safe_id(project)
    safe_tool_name = _safe_id(tool_name)
    runtime_id = f"{safe_provider}-web-mcp"

    from .backup_guard import default_runtime_dir

    runtime_root = Path(runtime_dir).resolve() if runtime_dir else default_runtime_dir()
    sessions_dir = runtime_root / "web-ai-sessions"
    evidence_dir = runtime_root / "web-ai-mcp-results"
    sessions_dir.mkdir(parents=True, exist_ok=True)
    evidence_dir.mkdir(parents=True, exist_ok=True)

    session_id = (
        f"{safe_provider}-web-mcp-{safe_tool_name}-"
        f"{int(datetime.now(timezone.utc).timestamp() * 1000)}"
    )
    tool_call_id = f"{safe_provider}-{safe_tool_name}-call"

    session = {
        "session_id": session_id,
        "provider": safe_provider,
        "agent_id": f"{safe_provider}-web-mcp-agent",
        "agent_role": "executor",
        "project_id": safe_project,
        "run_id": "",
        "task_spec_id": "",
        "status": _session_status(status),
        "messages": [],
        "tool_calls": [
            {
                "tool_call_id": tool_call_id,
                "name": tool_name,
                "status": _session_status(status),
                "command": "",
                "evidence_ref": "",
            }
        ],
        "changed_files": [],
        "diff_summary": "",
        "evidence_refs": [],
        "cost": {},
        "tokens": {},
        "gates": [],
        "actions": (
            [
                "Review the imported bounded project summary to inform the next local handoff or task intake."
            ]
            if tool_name == "project_summary" and resolved_outcome == "completed"
            else []
        ),
        "native_refs": {
            "runtime": runtime_id,
            "source_runtime": runtime_id,
            "conversation_url": safe_conversation_url,
            "connector_name": connector_name or "",
            "connector_app_id": connector_app_id or "",
            "tool_name": tool_name,
            "marker": marker or "",
            "output_id": output_id or "",
            "output_name": output_name or "",
            "origin": resolved_origin,
            "outcome": resolved_outcome,
        },
    }

    evidence = {
        "session_id": session_id,
        "provider": safe_provider,
        "project_id": safe_project,
        "conversation_url": safe_conversation_url,
        "connector_name": connector_name or "",
        "connector_app_id": connector_app_id or "",
        "tool_name": tool_name,
        "status": status,
        "origin": resolved_origin,
        "outcome": resolved_outcome,
        "marker": marker or "",
        "result_summary": result_summary,
        "output_id": output_id or "",
        "output_name": output_name or "",
        "recorded_at": datetime.now(timezone.utc).isoformat(),
    }

    session_path = sessions_dir / f"{session_id}.json"
    evidence_path = evidence_dir / f"{session_id}-evidence.json"
    session["tool_calls"][0]["evidence_ref"] = str(evidence_path)

    session_path.write_text(
        json.dumps(session, indent=2, ensure_ascii=True) + "\n", encoding="utf-8"
    )
    evidence_path.write_text(
        json.dumps(evidence, indent=2, ensure_ascii=True) + "\n", encoding="utf-8"
    )

    session["evidence_refs"] = [str(evidence_path)]
    session_path.write_text(
        json.dumps(session, indent=2, ensure_ascii=True) + "\n", encoding="utf-8"
    )

    return {
        "session_id": session_id,
        "session_path": str(session_path),
        "evidence_path": str(evidence_path),
        "status": status,
        "origin": resolved_origin,
        "outcome": resolved_outcome,
    }


def record_task_intake(
    runtime_dir: str | Path | None = None,
    *,
    provider: str = "chatgpt",
    project: str = "dev-frame-system",
    conversation_url: str = "",
    connector_name: str | None = None,
    connector_app_id: str | None = None,
    task_title: str = "",
    task_summary: str = "",
    priority: str = "medium",
    suggested_agent: str = "opencode",
    marker: str | None = None,
) -> dict[str, Any]:
    if priority not in _VALID_PRIORITIES:
        raise ValueError(f"priority must be one of {sorted(_VALID_PRIORITIES)}")
    if suggested_agent not in _VALID_SUGGESTED_AGENTS:
        raise ValueError(f"suggested_agent must be one of {sorted(_VALID_SUGGESTED_AGENTS)}")
    if not task_title.strip():
        raise ValueError("task_title is required")
    if not task_summary.strip():
        raise ValueError("task_summary is required")

    safe_conversation_url = _validate_conversation_url(conversation_url)
    safe_provider = _safe_id(provider)
    safe_project = _safe_id(project)
    runtime_id = f"{safe_provider}-web-mcp"

    from .backup_guard import default_runtime_dir

    runtime_root = Path(runtime_dir).resolve() if runtime_dir else default_runtime_dir()
    sessions_dir = runtime_root / "web-ai-sessions"
    evidence_dir = runtime_root / "web-ai-mcp-results"
    sessions_dir.mkdir(parents=True, exist_ok=True)
    evidence_dir.mkdir(parents=True, exist_ok=True)

    session_id = (
        f"{safe_provider}-web-mcp-task-intake-"
        f"{int(datetime.now(timezone.utc).timestamp() * 1000)}"
    )
    intake_id = session_id
    tool_call_id = f"{safe_provider}-task-intake-call"
    action_text = (
        f"Execute task intake '{task_title.strip()}' through local DevFrame Code or @go "
        f"with suggested_agent={suggested_agent} priority={priority}."
    )

    session = {
        "session_id": session_id,
        "provider": safe_provider,
        "agent_id": f"{safe_provider}-web-mcp-agent",
        "agent_role": "executor",
        "project_id": safe_project,
        "run_id": "",
        "task_spec_id": "",
        "status": "idle",
        "messages": [],
        "tool_calls": [
            {
                "tool_call_id": tool_call_id,
                "name": "task_intake",
                "status": "completed",
                "command": "",
                "evidence_ref": "",
            }
        ],
        "changed_files": [],
        "diff_summary": "",
        "evidence_refs": [],
        "cost": {},
        "tokens": {},
        "gates": [],
        "actions": [action_text],
        "native_refs": {
            "runtime": runtime_id,
            "source_runtime": runtime_id,
            "conversation_url": safe_conversation_url,
            "connector_name": connector_name or "",
            "connector_app_id": connector_app_id or "",
            "tool_name": "task_intake",
            "task_title": task_title.strip(),
            "priority": priority,
            "suggested_agent": suggested_agent,
            "marker": marker or "",
            "origin": "web_host",
            "outcome": "task_intake_recorded",
            "intake_id": intake_id,
            "output_id": intake_id,
            "output_name": f"{session_id}.json",
        },
    }

    evidence = {
        "session_id": session_id,
        "provider": safe_provider,
        "project_id": safe_project,
        "conversation_url": safe_conversation_url,
        "connector_name": connector_name or "",
        "connector_app_id": connector_app_id or "",
        "task_title": task_title.strip(),
        "task_summary": task_summary.strip(),
        "priority": priority,
        "suggested_agent": suggested_agent,
        "origin": "web_host",
        "outcome": "task_intake_recorded",
        "marker": marker or "",
        "intake_id": intake_id,
        "output_id": intake_id,
        "output_name": f"{session_id}.json",
        "recorded_at": datetime.now(timezone.utc).isoformat(),
    }

    session_path = sessions_dir / f"{session_id}.json"
    evidence_path = evidence_dir / f"{session_id}-evidence.json"
    session["tool_calls"][0]["evidence_ref"] = str(evidence_path)

    session_path.write_text(
        json.dumps(session, indent=2, ensure_ascii=True) + "\n", encoding="utf-8"
    )
    evidence_path.write_text(
        json.dumps(evidence, indent=2, ensure_ascii=True) + "\n", encoding="utf-8"
    )

    session["evidence_refs"] = [str(evidence_path)]
    session_path.write_text(
        json.dumps(session, indent=2, ensure_ascii=True) + "\n", encoding="utf-8"
    )

    return {
        "session_id": session_id,
        "session_path": str(session_path),
        "evidence_path": str(evidence_path),
        "status": "idle",
        "origin": "web_host",
        "outcome": "task_intake_recorded",
    }


def _load_json_intake_file(path: Path) -> dict[str, Any] | None:
    raw = path.read_bytes()
    encoding = "utf-16" if raw.startswith((b"\xff\xfe", b"\xfe\xff")) else "utf-8-sig"
    try:
        data = json.loads(raw.decode(encoding))
        if not isinstance(data, dict):
            return None
        return data
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None


def _existing_intake_ids(runtime_dir: Path) -> set[str]:
    sessions_dir = runtime_dir / "web-ai-sessions"
    if not sessions_dir.is_dir():
        return set()
    ids: set[str] = set()
    for session_path in sorted(sessions_dir.glob("*.json")):
        data = _load_json_intake_file(session_path)
        if not data:
            continue
        native_refs = data.get("native_refs")
        if not isinstance(native_refs, dict):
            continue
        intake_id = str(native_refs.get("intake_id") or "").strip()
        intake_path = str(native_refs.get("intake_path") or "").strip()
        if intake_id:
            ids.add(intake_id)
        if intake_path:
            ids.add(intake_path)
    return ids


def import_task_intakes(
    project_root: str | Path,
    *,
    runtime_dir: str | Path | None = None,
    provider: str = "chatgpt",
    project: str = "dev-frame-system",
    connector_name: str | None = None,
    connector_app_id: str | None = None,
) -> dict[str, Any]:
    from .backup_guard import default_runtime_dir

    project_path = Path(project_root).resolve()
    intake_dir = project_path / ".ai-bridge" / "task-intakes"
    runtime_root = Path(runtime_dir).resolve() if runtime_dir else default_runtime_dir()
    sessions_dir = runtime_root / "web-ai-sessions"
    evidence_dir = runtime_root / "web-ai-mcp-results"
    sessions_dir.mkdir(parents=True, exist_ok=True)
    evidence_dir.mkdir(parents=True, exist_ok=True)

    existing_ids = _existing_intake_ids(runtime_root)

    imported: list[dict[str, str]] = []
    skipped: list[dict[str, str]] = []

    if not intake_dir.is_dir():
        return {"imported": imported, "skipped": skipped}

    for intake_path in sorted(intake_dir.glob("*.json")):
        intake_file = str(intake_path)
        try:
            intake_ref = intake_path.relative_to(project_path).as_posix()
        except ValueError:
            intake_ref = intake_path.name
        data = _load_json_intake_file(intake_path)
        if not data:
            skipped.append({"path": intake_file, "reason": "invalid JSON or not a JSON object"})
            continue

        intake_id = str(data.get("id") or "").strip()
        if not intake_id:
            skipped.append({"path": intake_file, "reason": "missing or empty id field"})
            continue

        if intake_id in existing_ids or intake_file in existing_ids:
            skipped.append({"path": intake_file, "reason": f"duplicate intake_id={intake_id}"})
            continue

        title = str(data.get("title") or "").strip()
        summary = str(data.get("summary") or "").strip()
        priority = str(data.get("priority") or "medium").strip()
        suggested_agent = str(data.get("suggested_agent") or "opencode").strip()
        conversation_url = str(data.get("conversation_url") or "").strip()
        marker = str(data.get("marker") or "").strip()

        if not title:
            skipped.append({"path": intake_file, "reason": "missing or empty title field", "intake_id": intake_id})
            continue
        if not summary:
            skipped.append({"path": intake_file, "reason": "missing or empty summary field", "intake_id": intake_id})
            continue

        if priority not in _VALID_PRIORITIES:
            priority = "medium"
        if suggested_agent not in _VALID_SUGGESTED_AGENTS:
            suggested_agent = "opencode"

        safe_provider = _safe_id(provider)
        safe_project = _safe_id(project)
        runtime_id = f"{safe_provider}-web-mcp"

        safe_conversation_url = ""
        if conversation_url:
            try:
                safe_conversation_url = _validate_conversation_url(conversation_url)
            except ValueError:
                pass

        session_id = (
            f"{safe_provider}-web-mcp-task-intake-"
            f"{int(datetime.now(timezone.utc).timestamp() * 1000)}"
        )
        tool_call_id = f"{safe_provider}-task-intake-call"
        action_text = (
            f"Execute task intake '{title}' through local DevFrame Code or @go "
            f"with suggested_agent={suggested_agent} priority={priority}."
        )

        session = {
            "session_id": session_id,
            "provider": safe_provider,
            "agent_id": f"{safe_provider}-web-mcp-agent",
            "agent_role": "executor",
            "project_id": safe_project,
            "run_id": "",
            "task_spec_id": "",
            "status": "idle",
            "messages": [],
            "tool_calls": [
                {
                    "tool_call_id": tool_call_id,
                    "name": "task_intake",
                    "status": "completed",
                    "command": "",
                    "evidence_ref": "",
                }
            ],
            "changed_files": [],
            "diff_summary": "",
            "evidence_refs": [],
            "cost": {},
            "tokens": {},
            "gates": [],
            "actions": [action_text],
            "native_refs": {
                "runtime": runtime_id,
                "source_runtime": runtime_id,
                "conversation_url": safe_conversation_url,
                "connector_name": connector_name or "",
                "connector_app_id": connector_app_id or "",
                "tool_name": "task_intake",
                "task_title": title,
                "priority": priority,
                "suggested_agent": suggested_agent,
                "marker": marker,
                "origin": "web_host",
                "outcome": "task_intake_recorded",
                "project_root": str(project_path),
                "intake_id": intake_id,
                "intake_path": intake_ref,
                "output_id": intake_id,
                "output_name": intake_ref,
            },
        }

        evidence = {
            "session_id": session_id,
            "provider": safe_provider,
            "project_id": safe_project,
            "conversation_url": safe_conversation_url,
            "connector_name": connector_name or "",
            "connector_app_id": connector_app_id or "",
            "task_title": title,
            "task_summary": summary,
            "priority": priority,
            "suggested_agent": suggested_agent,
            "origin": "web_host",
            "outcome": "task_intake_recorded",
            "project_root": str(project_path),
            "marker": marker,
            "intake_id": intake_id,
            "intake_path": intake_ref,
            "output_id": intake_id,
            "output_name": intake_ref,
            "recorded_at": datetime.now(timezone.utc).isoformat(),
        }

        session_path = sessions_dir / f"{session_id}.json"
        evidence_path = evidence_dir / f"{session_id}-evidence.json"
        session["tool_calls"][0]["evidence_ref"] = str(evidence_path)

        session_path.write_text(
            json.dumps(session, indent=2, ensure_ascii=True) + "\n", encoding="utf-8"
        )
        evidence_path.write_text(
            json.dumps(evidence, indent=2, ensure_ascii=True) + "\n", encoding="utf-8"
        )

        session["evidence_refs"] = [str(evidence_path)]
        session_path.write_text(
            json.dumps(session, indent=2, ensure_ascii=True) + "\n", encoding="utf-8"
        )

        existing_ids.add(intake_id)
        existing_ids.add(intake_file)

        imported.append({
            "session_id": session_id,
            "session_path": str(session_path),
            "intake_id": intake_id,
            "intake_path": intake_file,
            "title": title,
        })

    return {"imported": imported, "skipped": skipped}


def dispatch_task_intakes(
    project_root: str | Path,
    *,
    runtime_dir: str | Path | None = None,
    provider: str = "codexpro",
    project: str = "dev-frame-system",
    connector_name: str | None = None,
    connector_app_id: str | None = None,
    agents: int = 1,
    execute: bool = False,
    limit: int | None = None,
    intake_id: str | None = None,
    model: str | None = None,
    opencode_agent: str = "build",
    timeout_seconds: int = 900,
) -> dict[str, Any]:
    """Import queued Web GPT task intakes and prepare matching @go dispatches."""
    from .backup_guard import default_runtime_dir
    from .go_dispatch import run_go_dispatch

    project_path = Path(project_root).resolve()
    runtime_root = Path(runtime_dir).resolve() if runtime_dir else default_runtime_dir()
    import_result = import_task_intakes(
        project_path,
        runtime_dir=runtime_root,
        provider=provider,
        project=project,
        connector_name=connector_name,
        connector_app_id=connector_app_id,
    )
    sessions_dir = runtime_root / "web-ai-sessions"
    dispatched: list[dict[str, str]] = []
    skipped: list[dict[str, str]] = list(import_result.get("skipped", []))

    if not sessions_dir.is_dir():
        return {"imported": import_result.get("imported", []), "dispatched": dispatched, "skipped": skipped}

    remaining = limit if limit is not None else 999999
    for session_path in sorted(sessions_dir.glob("*.json")):
        if remaining <= 0:
            break
        session = _load_json_intake_file(session_path)
        if not session:
            continue
        native_refs = session.get("native_refs")
        if not isinstance(native_refs, dict) or native_refs.get("outcome") != "task_intake_recorded":
            continue

        current_intake_id = str(native_refs.get("intake_id") or "").strip()
        if intake_id and current_intake_id != intake_id:
            continue
        task_title = str(native_refs.get("task_title") or "").strip()
        suggested_agent = str(native_refs.get("suggested_agent") or "opencode").strip()
        existing_go_run = str(native_refs.get("dispatch_go_run_id") or "").strip()
        if existing_go_run:
            skipped.append({
                "path": str(session_path),
                "reason": f"already dispatched go_run_id={existing_go_run}",
            })
            continue
        if suggested_agent != "opencode":
            skipped.append({
                "path": str(session_path),
                "reason": f"unsupported suggested_agent={suggested_agent}",
            })
            continue

        task_summary = _task_summary_for_session(session, runtime_root)
        requirement = _dispatch_requirement_from_task_intake(
            title=task_title,
            summary=task_summary,
            intake_id=current_intake_id,
            priority=str(native_refs.get("priority") or "medium"),
            marker=str(native_refs.get("marker") or ""),
        )
        result = run_go_dispatch(
            project_path=project_path,
            requirement=requirement,
            runtime_dir=runtime_root,
            agents=agents,
            targets=[],
            execute=execute,
            worker="opencode",
            model=model,
            opencode_agent=opencode_agent,
            timeout_seconds=timeout_seconds,
            apply_rdinit=False,
        )
        native_refs["dispatch_go_run_id"] = result.go_run_id
        native_refs["dispatch_status"] = result.status
        native_refs["dispatch_metadata_path"] = result.metadata_path
        native_refs["dispatched_at"] = datetime.now(timezone.utc).isoformat()
        session["native_refs"] = native_refs
        session["status"] = "active" if execute else "queued"
        session["actions"] = [
            f"Inspect dispatched @go/OpenCode run {result.go_run_id} for task intake '{task_title}'."
        ]
        session_path.write_text(
            json.dumps(session, indent=2, ensure_ascii=True) + "\n", encoding="utf-8"
        )
        dispatched.append({
            "session_id": str(session.get("session_id") or session_path.stem),
            "intake_id": current_intake_id,
            "title": task_title,
            "go_run_id": result.go_run_id,
            "status": result.status,
            "metadata_path": result.metadata_path,
        })
        remaining -= 1

    return {"imported": import_result.get("imported", []), "dispatched": dispatched, "skipped": skipped}


def _task_summary_for_session(session: dict[str, Any], runtime_dir: Path) -> str:
    for ref in session.get("evidence_refs", []):
        ref_path = Path(str(ref))
        if not ref_path.is_absolute():
            ref_path = runtime_dir.parent / ref_path
        evidence = _load_json_intake_file(ref_path) if ref_path.exists() else None
        if isinstance(evidence, dict):
            summary = str(evidence.get("task_summary") or "").strip()
            if summary:
                return summary
    return str(session.get("diff_summary") or "").strip()


def _dispatch_requirement_from_task_intake(
    *,
    title: str,
    summary: str,
    intake_id: str,
    priority: str,
    marker: str,
) -> str:
    lines = [
        f"Web GPT task intake: {title or intake_id}",
        "",
        "Treat this as a planner/coordinator request submitted through ChatGPT Web MCP.",
        "Use the existing @go/OpenCode workflow: inspect the relevant project context, make scoped changes only when justified, run focused verification, and report evidence.",
        "",
        f"Priority: {priority or 'medium'}",
        f"Intake ID: {intake_id or 'unknown'}",
    ]
    if marker:
        lines.append(f"Marker: {marker}")
    if summary:
        lines.extend(["", "Task summary:", summary])
    return "\n".join(lines).strip()
