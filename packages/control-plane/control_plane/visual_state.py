"""Visual Control Plane read model built from local runtime state."""
from __future__ import annotations

import json
from html import escape
from pathlib import Path
from typing import Any
from urllib.parse import quote

import yaml

from .runtime_digest import build_runtime_digest

ROOT = Path(__file__).resolve().parent.parent
ACTION_STATUSES = ("open", "blocked", "ready", "info")
ACTION_PRIORITIES = ("high", "medium", "low")
ACTION_SOURCE_TYPES = ("gate", "run", "decision")


def build_visual_control_plane_state(
    runtime_dir: str | Path | None = None,
    paper_project_dirs: list[str | Path] | None = None,
) -> dict[str, Any]:
    """Build a schema-compatible state snapshot for GUI or CLI inspection."""
    paper_roots = [Path(path).resolve() for path in paper_project_dirs or []]
    digest = build_runtime_digest(runtime_dir)
    reports_by_packet = {
        report.get("packet_id", ""): report
        for report in digest.get("reports", [])
    }
    projects = [
        _project_state(project, digest.get("dispatches", []), digest.get("reports", []))
        for project in digest.get("projects", [])
    ]
    dispatches = digest.get("dispatches", [])
    runs = [
        _run_state(dispatch, reports_by_packet.get(dispatch.get("packet_id", "")), digest.get("runtime_dir", ""))
        for dispatch in dispatches
    ]
    paper_projects = [_paper_project_state(path) for path in paper_roots]
    paper_runs = [_paper_run_state(path) for path in paper_roots]
    paper_provider_bindings = [_paper_provider_binding_state(path) for path in paper_roots]
    paper_provider_gates = [
        _paper_provider_gate_state(root, binding)
        for root, binding in zip(paper_roots, paper_provider_bindings)
    ]
    all_runs = runs + paper_runs
    all_gates = (
        _gate_states(dispatches, reports_by_packet)
        + [_paper_gate_state(path) for path in paper_roots]
        + paper_provider_gates
    )
    all_decisions = (
        [_decision_state(dispatch, reports_by_packet) for dispatch in dispatches]
        + [_paper_decision_state(path) for path in paper_roots]
    )
    return {
        "version": 1,
        "projects": projects + paper_projects,
        "provider_bindings": _default_provider_bindings() + paper_provider_bindings,
        "agents": _default_agents(paper_provider_bindings),
        "runs": all_runs,
        "gates": all_gates,
        "decisions": all_decisions,
        "next_actions": _next_actions(all_runs, all_gates, all_decisions),
        "safety": {
            "raw_transcripts_persisted": False,
            "remote_execution_default": False,
            "human_gate_required_for": [
                "browser_profile_access",
                "credential_access",
                "external_side_effect",
                "payment",
                "production_deploy",
                "publication_submission",
                "raw_transcript_persistence",
                "real_paper_full_text",
                "remote_execution",
                "secret_exposure",
            ],
        },
    }


def render_visual_control_plane_state_json(state: dict[str, Any]) -> str:
    return json.dumps(state, indent=2, ensure_ascii=True)


def render_action_queue_text(next_actions: list[dict[str, Any]]) -> str:
    lines = ["Action Queue"]
    if not next_actions:
        lines.append("(no actions)")
        return "\n".join(lines) + "\n"
    for action in next_actions:
        priority = action.get("priority", "")
        status = action.get("status", "")
        source_type = action.get("source_type", "")
        source_id = action.get("source_id", "")
        action_id = action.get("action_id", "")
        lines.append(f"- [{priority}/{status}] {source_type} {source_id}")
        if action_id:
            lines.append(f"  id: {action_id}")
        resume_filter = _action_resume_filter(action)
        if resume_filter:
            lines.append(f"  resume: {resume_filter}")
        label = str(action.get("label") or "")
        if label:
            lines.append(f"  {label}")
        detail = str(action.get("detail") or "")
        if detail:
            lines.append(f"  detail: {detail}")
        command = str(action.get("command") or "")
        if command:
            lines.append(f"  command: {command}")
    return "\n".join(lines) + "\n"


def render_action_queue_markdown(next_actions: list[dict[str, Any]]) -> str:
    lines = [
        "# Action Queue Handoff",
        "",
        "Read-only queue for manual resume, review, or Web AI handoff.",
        "Do not execute commands until the matching gate and risk boundary are cleared.",
        "",
    ]
    if not next_actions:
        lines.append("(no actions)")
        return "\n".join(lines) + "\n"
    for index, action in enumerate(next_actions, start=1):
        priority = str(action.get("priority") or "")
        status = str(action.get("status") or "")
        source_type = str(action.get("source_type") or "")
        source_id = str(action.get("source_id") or "")
        action_id = str(action.get("action_id") or "")
        label = str(action.get("label") or "")
        detail = str(action.get("detail") or "")
        command = str(action.get("command") or "")
        lines.extend([
            f"## {index}. {label or source_id}",
            "",
            f"- Action ID: `{action_id}`",
            f"- Priority: `{priority}`",
            f"- Status: `{status}`",
            f"- Source: `{source_type}` `{source_id}`",
        ])
        resume_filter = _action_resume_filter(action)
        if resume_filter:
            lines.append(f"- Resume Filter: `{resume_filter}`")
        if detail:
            lines.append(f"- Detail: {detail}")
        if command:
            lines.extend([
                "",
                "```powershell",
                command,
                "```",
            ])
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def filter_action_queue(
    actions: list[dict[str, Any]],
    statuses: list[str] | None = None,
    priorities: list[str] | None = None,
    source_types: list[str] | None = None,
    source_ids: list[str] | None = None,
    action_ids: list[str] | None = None,
) -> list[dict[str, Any]]:
    status_filter = set(statuses or [])
    priority_filter = set(priorities or [])
    source_type_filter = set(source_types or [])
    source_id_filter = set(source_ids or [])
    action_id_filter = set(action_ids or [])
    return [
        action for action in actions
        if (not status_filter or action.get("status") in status_filter)
        and (not priority_filter or action.get("priority") in priority_filter)
        and (not source_type_filter or action.get("source_type") in source_type_filter)
        and (not source_id_filter or action.get("source_id") in source_id_filter)
        and (not action_id_filter or action.get("action_id") in action_id_filter)
    ]


def _action_resume_filter(action: dict[str, Any]) -> str:
    action_id = str(action.get("action_id") or "")
    if not action_id:
        return ""
    return f"devframe actions --action-id {action_id} --format markdown"


def action_filter_values(actions: list[dict[str, Any]]) -> dict[str, list[str]]:
    return {
        "action_id": _unique_action_values(actions, "action_id"),
        "source_id": _unique_action_values(actions, "source_id"),
    }


def _unique_action_values(actions: list[dict[str, Any]], key: str) -> list[str]:
    return sorted({
        str(action.get(key))
        for action in actions
        if action.get(key)
    })


def render_visual_control_plane_state_html(
    state: dict[str, Any],
    refresh_seconds: int | None = None,
    endpoint_links: bool = False,
) -> str:
    projects = state.get("projects", [])
    provider_bindings = state.get("provider_bindings", [])
    runs = state.get("runs", [])
    gates = state.get("gates", [])
    decisions = state.get("decisions", [])
    next_actions = state.get("next_actions", [])
    agents = state.get("agents", [])
    safety = state.get("safety", {})
    return "\n".join([
        "<!doctype html>",
        '<html lang="en">',
        "<head>",
        '<meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        _refresh_meta(refresh_seconds),
        "<title>DevFrame Visual Control Plane</title>",
        "<style>",
        _html_styles(),
        "</style>",
        "</head>",
        "<body>",
        '<main class="shell">',
        '<section class="masthead">',
        "<div>",
        '<p class="eyebrow">DevFrame Control Plane</p>',
        "<h1>Visual State Snapshot</h1>",
        '<p class="lead">A read-only view of projects, agents, runs, evidence gates, and controller decisions.</p>',
        _endpoint_links(endpoint_links),
        "</div>",
        '<div class="stamp">',
        f"<span>{len(projects)} projects</span>",
        f"<span>{len(runs)} runs</span>",
        "</div>",
        "</section>",
        _summary_band(state),
        _gate_focus_section(gates, next_actions, action_links=endpoint_links),
        _next_actions_section(next_actions, action_links=endpoint_links),
        _provider_bindings_section(provider_bindings),
        _projects_section(projects),
        _runs_section(runs),
        _run_details_section(runs, decisions),
        _agents_section(agents, provider_bindings),
        _gates_section(gates),
        _decisions_section(decisions),
        _safety_section(safety),
        "</main>",
        "</body>",
        "</html>",
        "",
    ])


def _refresh_meta(refresh_seconds: int | None) -> str:
    if refresh_seconds is None or refresh_seconds <= 0:
        return ""
    return f'<meta http-equiv="refresh" content="{refresh_seconds}">'


def _endpoint_links(enabled: bool) -> str:
    if not enabled:
        return ""
    links = [
        ("State JSON", "/state.json"),
        ("Action JSON", "/actions.json"),
        ("Action Handoff", "/actions.md"),
    ]
    items = "\n".join(
        f'<a href="{_h(href)}">{_h(label)}</a>'
        for label, href in links
    )
    return f'<nav class="endpoint-links" aria-label="Read-only dashboard endpoints">{items}</nav>'


def _default_provider_bindings() -> list[dict[str, Any]]:
    return [
        {
            "binding_id": "chatgpt-web",
            "provider": "chatgpt",
            "mode": "browser_cdp",
            "health": "unknown",
            "adapter_config_path": "WEB_AI_ADAPTER.yaml",
            "manual_fallback_instructions": [
                "Prepare a minimized prompt packet.",
                "Paste it into the configured web AI manually.",
                "Copy the latest response back into the governed run.",
            ],
            "notes": "Reference browser-hosted AI binding; replace per project.",
        },
        {
            "binding_id": "local-executor",
            "provider": "local",
            "mode": "custom",
            "health": "ready",
            "manual_fallback_instructions": [],
            "notes": "Local execution gateway for rdgoal workers.",
        },
    ]


def _default_agents(paper_provider_bindings: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    agents = [
        {
            "agent_id": "coordinator",
            "binding_id": "chatgpt-web",
            "role": "coordinator",
            "scope": "project",
            "permissions": ["plan", "read_context", "request_human_gate"],
            "status": "idle",
        },
        {
            "agent_id": "reviewer",
            "binding_id": "chatgpt-web",
            "role": "reviewer",
            "scope": "review",
            "permissions": ["review", "read_context", "request_human_gate"],
            "status": "idle",
        },
        {
            "agent_id": "executor",
            "binding_id": "local-executor",
            "role": "executor",
            "scope": "run",
            "permissions": ["execute", "read_context", "request_human_gate"],
            "status": "idle",
        },
    ]
    for binding in paper_provider_bindings or []:
        binding_id = str(binding.get("binding_id", ""))
        agents.append({
            "agent_id": _safe_id(f"paper-reviewer-{binding_id}"),
            "binding_id": binding_id,
            "role": "paper_reviewer",
            "scope": "paper",
            "permissions": ["review", "read_context", "request_human_gate"],
            "status": _agent_status_for_provider(binding),
        })
    return agents


def _agent_status_for_provider(binding: dict[str, Any]) -> str:
    health = str(binding.get("health") or "")
    if health == "blocked":
        return "blocked"
    if health == "needs_login":
        return "needs_human"
    if health == "disabled":
        return "disabled"
    return "idle"


def _project_state(project: dict[str, Any], dispatches: list[dict[str, Any]],
                   reports: list[dict[str, Any]]) -> dict[str, Any]:
    project_id = project.get("project_id", "")
    project_dispatches = [item for item in dispatches if item.get("project_id") == project_id]
    project_reports = [item for item in reports if item.get("project_id") == project_id]
    goal = _goal_from_dispatch(project_dispatches) or "No active goal recorded yet."
    return {
        "project_id": project_id,
        "display_name": project_id.replace("-", " ").title() or "Unregistered Project",
        "goal": goal,
        "status": _project_status(project_dispatches, project_reports),
        "risk_state": _risk_state(project_dispatches),
        "contract_path": _contract_path(project),
    }


def _run_state(dispatch: dict[str, Any], report: dict[str, Any] | None,
               runtime_dir: str) -> dict[str, Any]:
    dispatch_ready = bool(dispatch.get("dispatch_ready"))
    report_status = (report or {}).get("status", "")
    packet_id = dispatch.get("packet_id") or _fallback_id(dispatch, "run")
    packet_dir = dispatch.get("packet_dir", "")
    return {
        "run_id": _safe_id(packet_id),
        "entrypoint": "rdgoal",
        "status": _run_status(dispatch_ready, report_status),
        "taskspec_status": "ready" if dispatch_ready else "draft",
        "evidence_status": "collected" if report else "missing",
        "review_status": _review_status(report_status),
        "report_path": (report or {}).get("report_path", ""),
        "packet_path": packet_dir,
        "taskspec_path": str(Path(packet_dir) / "TASKSPEC.md") if packet_dir else "",
        "taskspec_json_path": str(Path(packet_dir) / "TASKSPEC.json") if packet_dir else "",
        "task_input_path": str(Path(packet_dir) / "TASKSPEC.json") if packet_dir else "",
        "next_command": _next_command_text(dispatch, report, runtime_dir),
    }


def _paper_project_state(project_dir: str | Path) -> dict[str, Any]:
    root = Path(project_dir).resolve()
    profile = _read_yaml(root / "PAPER_PROFILE.yaml")
    state = _read_yaml(root / "PAPER_STATE.yaml")
    paper_id = _paper_id(root, profile)
    title = _template_text(profile.get("title")) or root.name
    current_stage = (
        _template_text(state.get("current_stage"))
        or _template_text(profile.get("current_stage"))
        or "drafting"
    )
    status = _template_text(state.get("status")) or current_stage
    return {
        "project_id": paper_id,
        "display_name": title,
        "goal": f"Paper review workspace: {title}",
        "status": _paper_project_status(status),
        "risk_state": "human_required",
        "contract_path": str(root / "PAPER_REVIEW_SPEC.md"),
    }


def _paper_provider_binding_state(project_dir: str | Path) -> dict[str, Any]:
    root = Path(project_dir).resolve()
    profile = _read_yaml(root / "PAPER_PROFILE.yaml")
    adapter_path = root / "WEB_AI_ADAPTER.yaml"
    adapter = _read_yaml(adapter_path)
    browser = _as_dict(adapter.get("browser"))
    web_ai = _as_dict(adapter.get("web_ai"))
    provider = _safe_id(str(web_ai.get("provider") or "web-ai"))
    return {
        "binding_id": _safe_id(f"{_paper_id(root, profile)}-{provider}-web"),
        "provider": provider,
        "mode": _adapter_mode(browser, web_ai),
        "health": _adapter_health(adapter),
        "adapter_config_path": str(adapter_path),
        "manual_fallback_instructions": _manual_fallback_instructions(adapter),
        "notes": _adapter_notes(adapter),
    }


def _adapter_mode(browser: dict[str, Any], web_ai: dict[str, Any]) -> str:
    browser_mode = str(browser.get("mode") or "").lower()
    browser_provider = str(browser.get("provider") or "").lower()
    submit_strategy = str(web_ai.get("submit_strategy") or "").lower()
    if browser_mode == "manual" or browser_provider == "manual" or submit_strategy == "manual_copy":
        return "manual"
    if browser_mode == "cdp":
        return "browser_cdp"
    return "custom"


def _adapter_health(adapter: dict[str, Any]) -> str:
    if not adapter:
        return "blocked"
    safety = _as_dict(adapter.get("safety"))
    unsafe_flags = [
        "persist_raw_transcript",
        "allow_real_paper_full_text",
        "allow_pdf_upload",
        "allow_browser_profile_export",
    ]
    if any(safety.get(flag) is True for flag in unsafe_flags):
        return "blocked"
    capabilities = _as_dict(_as_dict(adapter.get("web_ai")).get("capabilities"))
    if capabilities.get("manual_login_required") is True:
        return "needs_login"
    return "ready"


def _adapter_notes(adapter: dict[str, Any]) -> str:
    if not adapter:
        return "WEB_AI_ADAPTER.yaml is missing or invalid; configure provider before review."
    browser = _as_dict(adapter.get("browser"))
    web_ai = _as_dict(adapter.get("web_ai"))
    capabilities = _as_dict(web_ai.get("capabilities"))
    manual_fallback = _as_dict(adapter.get("manual_fallback"))
    parts = [
        f"browser={browser.get('provider', 'unknown')}/{browser.get('mode', 'unknown')}",
        f"url={web_ai.get('url', 'unknown')}",
        f"file_upload={capabilities.get('file_upload', 'unknown')}",
    ]
    if capabilities.get("manual_login_required") is True:
        parts.append("manual_login_required")
    if manual_fallback.get("enabled") is True:
        parts.append("manual_fallback_enabled")
    return "; ".join(str(part) for part in parts)


def _manual_fallback_instructions(adapter: dict[str, Any]) -> list[str]:
    manual_fallback = _as_dict(adapter.get("manual_fallback"))
    if manual_fallback.get("enabled") is not True:
        return []
    instructions = manual_fallback.get("instructions")
    if not isinstance(instructions, list):
        return []
    return [
        str(instruction)
        for instruction in instructions
        if str(instruction).strip()
    ]


def _paper_run_state(project_dir: str | Path) -> dict[str, Any]:
    root = Path(project_dir).resolve()
    profile = _read_yaml(root / "PAPER_PROFILE.yaml")
    state = _read_yaml(root / "PAPER_STATE.yaml")
    paper_id = _paper_id(root, profile)
    run_id = _safe_id(f"{paper_id}-paper-review")
    paper_task = root / "paper_task"
    task_input = paper_task / "PAPER_TASK_INPUT.yaml"
    review_report = root / "review" / "REVIEW_REPORT.md"
    closure_report = root / "closure" / "CLOSURE_REPORT.md"
    evidence_pack = root / "evidence" / "ref-paper-review-pack.zip"
    report_path = closure_report if closure_report.exists() else review_report
    return {
        "run_id": run_id,
        "entrypoint": "rdpaper",
        "status": _paper_run_status(root, state),
        "taskspec_status": "ready" if task_input.exists() else "draft",
        "evidence_status": _paper_evidence_status(root),
        "review_status": _paper_review_status(root),
        "report_path": str(report_path) if report_path.exists() else str(root / "PAPER_LEDGER.md"),
        "packet_path": str(paper_task) if paper_task.exists() else str(root),
        "taskspec_path": str(root / "PAPER_NEXT_TASK.md"),
        "taskspec_json_path": str(task_input) if task_input.exists() else "",
        "task_input_path": str(task_input) if task_input.exists() else "",
        "next_command": _paper_next_command(root, evidence_pack),
    }


def _paper_gate_state(project_dir: str | Path) -> dict[str, Any]:
    root = Path(project_dir).resolve()
    profile = _read_yaml(root / "PAPER_PROFILE.yaml")
    paper_id = _paper_id(root, profile)
    attestation = root / "paper_task" / "PRIVACY_ATTESTATION.yaml"
    attestation_path = root / "paper_task" / "PRIVACY_ATTESTATION.yaml"
    return {
        "gate_id": _safe_id(f"{paper_id}-privacy-gate"),
        "kind": "privacy",
        "status": "pass" if attestation.exists() else "open",
        "reason": "Real paper full text, PDF upload, raw transcripts, and browser profile access require human approval.",
        "next_action": (
            "Continue with provider safety review."
            if attestation.exists()
            else f"Create {_quote_arg(attestation_path)} with privacy-safe review attestation before sending paper context."
        ),
        "run_id": _safe_id(f"{paper_id}-paper-review"),
    }


def _paper_provider_gate_state(project_dir: str | Path, binding: dict[str, Any]) -> dict[str, Any]:
    root = Path(project_dir).resolve()
    profile = _read_yaml(root / "PAPER_PROFILE.yaml")
    paper_id = _paper_id(root, profile)
    binding_id = str(binding.get("binding_id") or _safe_id(f"{paper_id}-provider"))
    health = str(binding.get("health") or "unknown")
    return {
        "gate_id": _safe_id(f"{binding_id}-safety-gate"),
        "kind": "safety",
        "status": _provider_gate_status(health),
        "reason": _provider_gate_reason(health, binding),
        "next_action": _provider_gate_next_action(health, binding),
        "run_id": _safe_id(f"{paper_id}-paper-review"),
    }


def _provider_gate_status(health: str) -> str:
    if health in {"ready", "unknown"}:
        return "pass"
    if health == "needs_login":
        return "open"
    if health in {"blocked", "disabled"}:
        return "blocked"
    return "open"


def _provider_gate_reason(health: str, binding: dict[str, Any]) -> str:
    path = binding.get("adapter_config_path", "WEB_AI_ADAPTER.yaml")
    if health == "ready":
        return f"Provider adapter config is privacy-safe for local read-model use: {path}."
    if health == "needs_login":
        return "Provider requires manual login or human confirmation before a paper review can be sent."
    if health == "blocked":
        return "Provider adapter is missing, invalid, or allows unsafe paper data flow; fix WEB_AI_ADAPTER.yaml before review."
    if health == "disabled":
        return "Provider adapter is disabled."
    return "Provider adapter health is unknown; review configuration before use."


def _provider_gate_next_action(health: str, binding: dict[str, Any]) -> str:
    path = binding.get("adapter_config_path", "WEB_AI_ADAPTER.yaml")
    if health == "ready":
        return "Continue with the rdpaper command shown in Run Details."
    if health == "needs_login":
        return "Open the configured provider, complete manual login, then continue through the documented manual fallback."
    if health == "blocked":
        return (
            f"Edit {_quote_arg(path)} so raw transcript persistence, real paper full text, "
            "PDF upload, and browser profile export are disabled."
        )
    if health == "disabled":
        return f"Enable or replace the provider in {_quote_arg(path)} before review."
    return f"Review {_quote_arg(path)} and classify provider readiness before review."


def _paper_decision_state(project_dir: str | Path) -> dict[str, Any]:
    root = Path(project_dir).resolve()
    profile = _read_yaml(root / "PAPER_PROFILE.yaml")
    paper_id = _paper_id(root, profile)
    flow = _read_json(root / "closure" / "FLOW_OUTCOME.json")
    completed = flow.get("final_status") == "completed"
    provider_binding = _paper_provider_binding_state(root)
    provider_health = str(provider_binding.get("health") or "")
    if provider_health == "blocked":
        return {
            "decision_id": _safe_id(f"{paper_id}-paper-decision"),
            "mode": "revise",
            "status": "blocked",
            "next_action": _provider_gate_next_action(provider_health, provider_binding),
            "run_id": _safe_id(f"{paper_id}-paper-review"),
        }
    if provider_health == "needs_login":
        next_action = "Complete the provider safety gate, then prepare the privacy-safe paper task packet."
    else:
        next_action = "Review paper closure outcome." if completed else "Prepare privacy-safe paper task packet."
    return {
        "decision_id": _safe_id(f"{paper_id}-paper-decision"),
        "mode": "continue" if completed or (root / "paper_task" / "PAPER_TASK_INPUT.yaml").exists() else "revise",
        "status": "executed" if completed else "selected",
        "next_action": next_action,
        "run_id": _safe_id(f"{paper_id}-paper-review"),
    }


def _paper_id(root: Path, profile: dict[str, Any]) -> str:
    raw_id = _template_text(profile.get("paper_id")) or root.name
    return _safe_id(raw_id)


def _template_text(value: object) -> str:
    text = str(value or "").strip()
    if text.startswith("{{") and text.endswith("}}"):
        return ""
    return text


def _paper_project_status(status: str) -> str:
    normalized = status.lower()
    if normalized in {"accepted", "completed"}:
        return "completed"
    if normalized in {"rejected", "blocked"}:
        return "blocked"
    if normalized in {"review_requested", "review_received", "revision"}:
        return "review_required"
    if normalized in {"drafting", "in_progress"}:
        return "active"
    return "initialized"


def _paper_run_status(root: Path, state: dict[str, Any]) -> str:
    flow = _read_json(root / "closure" / "FLOW_OUTCOME.json")
    if flow.get("final_status") == "completed":
        return "completed"
    pre_submission = _read_yaml(root / "evidence" / "PRE_SUBMISSION_CHECK.yaml")
    if pre_submission.get("result") == "fail":
        return "blocked"
    if (root / "review" / "REVIEW_REPORT.md").exists():
        return "review_required"
    if (root / "paper_task" / "PAPER_TASK_INPUT.yaml").exists():
        return "pending"
    project_status = _paper_project_status(str(state.get("status") or "initialized"))
    return {
        "initialized": "pending",
        "active": "running",
        "review_required": "review_required",
        "blocked": "blocked",
        "completed": "completed",
    }.get(project_status, "pending")


def _paper_evidence_status(root: Path) -> str:
    if (root / "evidence" / "ref-paper-review-pack.zip").exists():
        return "collected"
    if (root / "paper_task" / "PAPER_TASK_INPUT.yaml").exists() or (root / "review" / "REVIEW_REPORT.md").exists():
        return "partial"
    return "missing"


def _paper_review_status(root: Path) -> str:
    flow = _read_json(root / "closure" / "FLOW_OUTCOME.json")
    if flow.get("final_status") == "completed":
        return "pass"
    if (root / "review" / "REVIEW_REPORT.md").exists():
        return "pending"
    return "missing"


def _paper_next_command(root: Path, evidence_pack: Path) -> str:
    if evidence_pack.exists():
        return f"devframe pack validate {_quote_arg(evidence_pack)}"
    pipeline = ROOT / "pipelines" / "reference_paper_review.yaml"
    return f"devframe run --pipeline {_quote_arg(pipeline)} --execute --project {_quote_arg(root)}"


def _read_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8-sig"))
    except (OSError, yaml.YAMLError):
        return {}
    return data if isinstance(data, dict) else {}


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _as_dict(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _gate_states(dispatches: list[dict[str, Any]],
                 reports_by_packet: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    gates: list[dict[str, Any]] = [
        {
            "gate_id": "human-gate",
            "kind": "human",
            "status": "open",
            "reason": "Required before secrets, browser profiles, external side effects, or production actions.",
            "next_action": "Confirm human approval before continuing with high-risk work.",
        }
    ]
    for dispatch in dispatches:
        packet_id = dispatch.get("packet_id") or _fallback_id(dispatch, "gate")
        report = reports_by_packet.get(dispatch.get("packet_id", ""))
        gates.append({
            "gate_id": _safe_id(f"{packet_id}-acceptance"),
            "kind": "acceptance",
            "status": _gate_status(dispatch, report),
            "reason": dispatch.get("reason", ""),
            "next_action": _gate_next_action(dispatch, report),
            "run_id": _safe_id(packet_id),
        })
    return gates


def _gate_next_action(dispatch: dict[str, Any], report: dict[str, Any] | None) -> str:
    if report:
        return f"Review ExecutionReport status: {report.get('status', 'unknown')}."
    if dispatch.get("dispatch_ready"):
        packet_dir = dispatch.get("packet_dir", "")
        if packet_dir:
            return f"Run rdgoal worker for {_quote_arg(packet_dir)}."
        return "Run a worker against the ready dispatch packet."
    reason = dispatch.get("reason", "")
    return reason or "Resolve the blocking gate before execution."


def _decision_state(dispatch: dict[str, Any],
                    reports_by_packet: dict[str, dict[str, Any]]) -> dict[str, Any]:
    packet_id = dispatch.get("packet_id") or _fallback_id(dispatch, "decision")
    report = reports_by_packet.get(dispatch.get("packet_id", ""))
    return {
        "decision_id": _safe_id(f"{packet_id}-decision"),
        "mode": _decision_mode(dispatch.get("decision_mode", "")),
        "status": _decision_status(dispatch, report),
        "next_action": _next_action(dispatch, report),
        "run_id": _safe_id(packet_id),
    }


def _goal_from_dispatch(dispatches: list[dict[str, Any]]) -> str:
    for dispatch in reversed(dispatches):
        packet = _read_packet(dispatch.get("packet_dir", ""))
        requirement = packet.get("requirement", "")
        if requirement:
            return requirement
    return ""


def _read_packet(packet_dir: str) -> dict[str, Any]:
    if not packet_dir:
        return {}
    path = Path(packet_dir) / "packet.json"
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _project_status(dispatches: list[dict[str, Any]], reports: list[dict[str, Any]]) -> str:
    if any(report.get("status") in {"failed", "fail", "blocked"} for report in reports):
        return "blocked"
    if reports and all(report.get("status") == "passed" for report in reports):
        return "completed"
    if any(dispatch.get("dispatch_ready") for dispatch in dispatches):
        return "active"
    if dispatches:
        return "review_required"
    return "initialized"


def _risk_state(dispatches: list[dict[str, Any]]) -> str:
    decision_modes = {dispatch.get("decision_mode") for dispatch in dispatches}
    if "hard_stop" in decision_modes or "draft_only" in decision_modes:
        return "human_required"
    if "snapshot_execute" in decision_modes:
        return "high"
    if decision_modes:
        return "medium"
    return "low"


def _contract_path(project: dict[str, Any]) -> str:
    root = project.get("project_root", "")
    if not root:
        return ""
    project_id = project.get("project_id", "")
    return str(Path(root) / "rules" / "project-contracts" / f"{project_id}.md")


def _run_status(dispatch_ready: bool, report_status: str) -> str:
    if report_status == "passed":
        return "completed"
    if report_status in {"failed", "fail"}:
        return "failed"
    if report_status == "blocked":
        return "blocked"
    if not dispatch_ready:
        return "blocked"
    return "pending"


def _review_status(report_status: str) -> str:
    if report_status == "passed":
        return "pass"
    if report_status == "blocked":
        return "blocked"
    if report_status in {"failed", "fail"}:
        return "fail"
    return "missing"


def _gate_status(dispatch: dict[str, Any], report: dict[str, Any] | None) -> str:
    if not dispatch.get("dispatch_ready"):
        return "blocked"
    if not report:
        return "open"
    if report.get("status") == "passed":
        return "pass"
    if report.get("status") == "blocked":
        return "blocked"
    return "failed"


def _decision_mode(decision_mode: str) -> str:
    if decision_mode in {"auto_execute", "snapshot_execute", "recommend_execute"}:
        return "continue"
    if decision_mode == "draft_only":
        return "stop"
    if decision_mode == "hard_stop":
        return "escalate"
    return "revise"


def _decision_status(dispatch: dict[str, Any], report: dict[str, Any] | None) -> str:
    if not dispatch.get("dispatch_ready"):
        return "blocked"
    if report:
        return "executed"
    return "selected"


def _next_action(dispatch: dict[str, Any], report: dict[str, Any] | None) -> str:
    if report:
        return f"Review report status: {report.get('status', 'unknown')}."
    if dispatch.get("dispatch_ready"):
        return "Run a worker against the dispatch packet."
    reason = dispatch.get("reason", "")
    return reason or "Resolve the blocking gate before execution."


def _next_command_text(dispatch: dict[str, Any], report: dict[str, Any] | None,
                       runtime_dir: str) -> str:
    if report:
        return f"rdgoal digest --runtime-dir {_quote_arg(runtime_dir)}"
    if dispatch.get("dispatch_ready") and dispatch.get("packet_dir"):
        return (
            f"rdgoal worker {_quote_arg(dispatch.get('packet_dir', ''))} "
            f"--runtime-dir {_quote_arg(runtime_dir)}"
        )
    return ""


def _quote_arg(value: object) -> str:
    text = str(value)
    if not text:
        return '""'
    escaped = text.replace('"', '\\"')
    return f'"{escaped}"'


def _fallback_id(item: dict[str, Any], suffix: str) -> str:
    base = item.get("project_id") or "unknown"
    return f"{base}-{suffix}"


def _safe_id(value: str) -> str:
    normalized = "".join(
        char.lower() if "a" <= char.lower() <= "z" or "0" <= char <= "9" else "-"
        for char in value
    )
    normalized = "-".join(part for part in normalized.split("-") if part)
    return normalized or "unknown"


def _next_actions(
    runs: list[dict[str, Any]],
    gates: list[dict[str, Any]],
    decisions: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    for gate in gates:
        status = str(gate.get("status") or "")
        if status not in {"open", "blocked", "failed"}:
            continue
        label = str(gate.get("next_action") or gate.get("reason") or "")
        if not label:
            continue
        gate_id = str(gate.get("gate_id") or "gate")
        actions.append({
            "action_id": _safe_id(f"{gate_id}-action"),
            "source_type": "gate",
            "source_id": gate_id,
            "priority": "high" if status in {"blocked", "failed"} else "medium",
            "status": "blocked" if status in {"blocked", "failed"} else "open",
            "label": label,
            "detail": str(gate.get("reason") or ""),
        })
    for run in runs:
        status = str(run.get("status") or "")
        command = str(run.get("next_command") or "")
        if status not in {"pending", "running", "blocked", "failed"} or not command:
            continue
        run_id = str(run.get("run_id") or "run")
        actions.append({
            "action_id": _safe_id(f"{run_id}-command-action"),
            "source_type": "run",
            "source_id": run_id,
            "priority": "high" if status in {"blocked", "failed"} else "medium",
            "status": "blocked" if status in {"blocked", "failed"} else "ready",
            "label": "Run or inspect the next local command.",
            "detail": str(run.get("entrypoint") or ""),
            "command": command,
        })
    for decision in decisions:
        status = str(decision.get("status") or "")
        if status not in {"proposed", "selected", "blocked"}:
            continue
        label = str(decision.get("next_action") or "")
        if not label:
            continue
        decision_id = str(decision.get("decision_id") or "decision")
        actions.append({
            "action_id": _safe_id(f"{decision_id}-action"),
            "source_type": "decision",
            "source_id": decision_id,
            "priority": "high" if status == "blocked" else "low",
            "status": "blocked" if status == "blocked" else "info",
            "label": label,
            "detail": str(decision.get("mode") or ""),
        })
    return sorted(actions, key=_action_sort_key)


def _action_sort_key(action: dict[str, Any]) -> tuple[int, int, str]:
    priority_order = {"high": 0, "medium": 1, "low": 2}
    source_order = {"gate": 0, "run": 1, "decision": 2}
    return (
        priority_order.get(str(action.get("priority")), 3),
        source_order.get(str(action.get("source_type")), 3),
        str(action.get("action_id")),
    )


def _summary_band(state: dict[str, Any]) -> str:
    projects = state.get("projects", [])
    runs = state.get("runs", [])
    gates = state.get("gates", [])
    decisions = state.get("decisions", [])
    metrics = [
        ("Projects", str(len(projects)), "registered units"),
        ("Runs", str(len(runs)), _count_by_status(runs)),
        ("Gates", str(len(gates)), _count_by_status(gates)),
        ("Decisions", str(len(decisions)), _count_by_status(decisions)),
    ]
    items = "\n".join(
        '<article class="metric">'
        f"<strong>{_h(value)}</strong>"
        f"<span>{_h(label)}</span>"
        f"<em>{_h(detail)}</em>"
        "</article>"
        for label, value, detail in metrics
    )
    return f'<section class="metrics">{items}</section>'


def _gate_focus_section(
    gates: list[dict[str, Any]],
    next_actions: list[dict[str, Any]],
    action_links: bool = False,
) -> str:
    active_gates = [
        gate for gate in gates
        if str(gate.get("status", "")).lower() not in {"pass", "passed", "completed"}
    ]
    actions_by_gate = {
        str(action.get("source_id") or ""): action
        for action in next_actions
        if action.get("source_type") == "gate" and action.get("source_id")
    }
    if not active_gates:
        rows = '<p class="empty">No active gates.</p>'
    else:
        rows = "\n".join(
            _gate_focus_card_html(
                gate,
                actions_by_gate.get(str(gate.get("gate_id") or "")),
                action_links,
            )
            for gate in active_gates
        )
    return (
        '<section class="panel gate-focus">'
        "<h2>Gate Focus</h2>"
        f'<div class="gate-focus-grid">{rows}</div>'
        "</section>"
    )


def _gate_focus_card_html(
    gate: dict[str, Any],
    action: dict[str, Any] | None,
    action_links: bool,
) -> str:
    return (
        '<article class="gate-focus-card">'
        '<div class="gate-focus-head">'
        f"<code>{_h(gate.get('gate_id', ''))}</code>"
        f"{_badge(gate.get('status', ''))}"
        f"{_badge(gate.get('kind', ''))}"
        "</div>"
        f"<p>{_h(gate.get('reason', ''))}</p>"
        f"<p><strong>Next action</strong>{_h(gate.get('next_action', ''))}</p>"
        f"{_gate_focus_action_html(action, action_links)}"
        "</article>"
    )


def _gate_focus_action_html(action: dict[str, Any] | None, action_links: bool) -> str:
    if not action:
        return ""
    action_id = str(action.get("action_id") or "")
    resume_filter = _action_resume_filter(action)
    parts = []
    if action_id:
        parts.append(f"<p><strong>Action ID</strong><code>{_h(action_id)}</code></p>")
    if resume_filter:
        parts.append(
            f"<p><strong>Resume filter</strong><code>{_h(resume_filter)}</code></p>"
        )
    if action_links and action_id:
        href = f"/actions.md?action_id={quote(action_id)}"
        parts.append(
            f'<p><strong>Handoff</strong><a class="row-link" href="{_h(href)}">'
            "Markdown</a></p>"
        )
    return "".join(parts)


def _next_actions_section(next_actions: list[dict[str, Any]], action_links: bool = False) -> str:
    rows = "\n".join(
        "<tr>"
        f"<td>{_badge(action.get('priority', ''))}</td>"
        f"<td>{_badge(action.get('status', ''))}</td>"
        f"<td>{_h(action.get('label', ''))}</td>"
        f"<td>{_h(action.get('source_type', ''))}</td>"
        f"<td><code>{_h(action.get('source_id', ''))}</code></td>"
        f"<td><code>{_h(action.get('action_id', ''))}</code></td>"
        f"<td><code>{_h(_action_resume_filter(action))}</code></td>"
        f"<td><code>{_h(action.get('command', ''))}</code></td>"
        f"{_action_handoff_cell(action, action_links)}"
        "</tr>"
        for action in next_actions
    )
    headers = ["Priority", "Status", "Action", "Source", "Source ID", "Action ID", "Resume Filter", "Command"]
    if action_links:
        headers.append("Handoff")
    return _table_section(
        "Action Queue",
        headers,
        rows,
    )


def _action_handoff_cell(action: dict[str, Any], enabled: bool) -> str:
    if not enabled:
        return ""
    action_id = str(action.get("action_id") or "")
    if not action_id:
        return "<td></td>"
    href = f"/actions.md?action_id={quote(action_id)}"
    return f'<td><a class="row-link" href="{_h(href)}">Markdown</a></td>'


def _provider_bindings_section(provider_bindings: list[dict[str, Any]]) -> str:
    rows = "\n".join(
        "<tr>"
        f"<td><code>{_h(binding.get('binding_id', ''))}</code></td>"
        f"<td>{_h(binding.get('provider', ''))}</td>"
        f"<td>{_h(binding.get('mode', ''))}</td>"
        f"<td>{_badge(binding.get('health', ''))}</td>"
        f"<td><code>{_h(binding.get('adapter_config_path', ''))}</code></td>"
        f"<td>{_manual_fallback_html(binding)}</td>"
        f"<td>{_h(binding.get('notes', ''))}</td>"
        "</tr>"
        for binding in provider_bindings
    )
    return _table_section(
        "Provider Bindings",
        ["Binding", "Provider", "Mode", "Health", "Adapter Config", "Manual Fallback", "Notes"],
        rows,
    )


def _manual_fallback_html(binding: dict[str, Any]) -> str:
    instructions = binding.get("manual_fallback_instructions", [])
    if not isinstance(instructions, list) or not instructions:
        return ""
    return "<br>".join(_h(str(instruction)) for instruction in instructions)


def _projects_section(projects: list[dict[str, Any]]) -> str:
    rows = "\n".join(
        "<tr>"
        f"<td>{_h(project.get('display_name', ''))}</td>"
        f"<td><code>{_h(project.get('project_id', ''))}</code></td>"
        f"<td>{_badge(project.get('status', ''))}</td>"
        f"<td>{_badge(project.get('risk_state', ''))}</td>"
        f"<td>{_h(project.get('goal', ''))}</td>"
        "</tr>"
        for project in projects
    )
    return _table_section("Projects", ["Name", "ID", "Status", "Risk", "Goal"], rows)


def _runs_section(runs: list[dict[str, Any]]) -> str:
    rows = "\n".join(
        "<tr>"
        f"<td><code>{_h(run.get('run_id', ''))}</code></td>"
        f"<td>{_h(run.get('entrypoint', ''))}</td>"
        f"<td>{_badge(run.get('status', ''))}</td>"
        f"<td>{_h(run.get('taskspec_status', ''))}</td>"
        f"<td>{_h(run.get('evidence_status', ''))}</td>"
        f"<td>{_h(run.get('review_status', ''))}</td>"
        "</tr>"
        for run in runs
    )
    return _table_section("Runs", ["Run", "Entry", "Status", "TaskSpec", "Evidence", "Review"], rows)


def _run_details_section(runs: list[dict[str, Any]], decisions: list[dict[str, Any]]) -> str:
    if not runs:
        return _table_section("Run Details", ["Run", "Details"], "")
    decisions_by_run = {
        str(decision.get("run_id") or ""): decision
        for decision in decisions
        if decision.get("run_id")
    }
    cards = "\n".join(
        '<article class="run-detail">'
        f"<h3>{_h(run.get('run_id', ''))}</h3>"
        '<dl class="path-list">'
        f"<dt>TaskSpec</dt><dd><code>{_h(run.get('taskspec_path', '')) or 'missing'}</code></dd>"
        f"<dt>TaskSpec JSON</dt><dd><code>{_h(run.get('taskspec_json_path', '')) or 'missing'}</code></dd>"
        f"<dt>Task Input</dt><dd><code>{_h(run.get('task_input_path', '')) or 'missing'}</code></dd>"
        f"<dt>ExecutionReport</dt><dd><code>{_h(run.get('report_path', '')) or 'missing'}</code></dd>"
        f"<dt>Packet</dt><dd><code>{_h(run.get('packet_path', '')) or 'missing'}</code></dd>"
        f"{_run_decision_details(decisions_by_run.get(str(run.get('run_id') or '')))}"
        "</dl>"
        f"<p class=\"command\"><span>Next command</span><code>{_h(run.get('next_command', '')) or 'Resolve gate before execution.'}</code></p>"
        "</article>"
        for run in runs
    )
    return (
        '<section class="panel">'
        "<h2>Run Details</h2>"
        f'<div class="run-details">{cards}</div>'
        "</section>"
    )


def _run_decision_details(decision: dict[str, Any] | None) -> str:
    if not decision:
        return (
            "<dt>Current Decision</dt><dd><code>missing</code></dd>"
            "<dt>Decision Next Action</dt><dd>missing</dd>"
        )
    mode = decision.get("mode", "")
    status = decision.get("status", "")
    label = " / ".join(part for part in [str(mode), str(status)] if part)
    return (
        f"<dt>Current Decision</dt><dd><code>{_h(decision.get('decision_id', ''))}</code> "
        f"{_badge(label or 'unknown')}</dd>"
        f"<dt>Decision Next Action</dt><dd>{_h(decision.get('next_action', '')) or 'missing'}</dd>"
    )


def _agents_section(
    agents: list[dict[str, Any]],
    provider_bindings: list[dict[str, Any]],
) -> str:
    bindings_by_id = {
        str(binding.get("binding_id") or ""): binding
        for binding in provider_bindings
        if binding.get("binding_id")
    }
    rows = "\n".join(
        _agent_row_html(agent, bindings_by_id)
        for agent in agents
    )
    return _table_section(
        "Agents",
        ["Agent", "Role", "Scope", "Provider", "Binding", "Binding Health", "Status"],
        rows,
    )


def _agent_row_html(
    agent: dict[str, Any],
    bindings_by_id: dict[str, dict[str, Any]],
) -> str:
    binding = _agent_binding(agent, bindings_by_id)
    return (
        "<tr>"
        f"<td><code>{_h(agent.get('agent_id', ''))}</code></td>"
        f"<td>{_h(agent.get('role', ''))}</td>"
        f"<td>{_h(agent.get('scope', ''))}</td>"
        f"<td>{_h(binding.get('provider', ''))}</td>"
        f"<td><code>{_h(agent.get('binding_id', ''))}</code></td>"
        f"<td>{_badge(binding.get('health', 'unknown'))}</td>"
        f"<td>{_badge(agent.get('status', ''))}</td>"
        "</tr>"
    )


def _agent_binding(
    agent: dict[str, Any],
    bindings_by_id: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    return bindings_by_id.get(str(agent.get("binding_id") or ""), {})


def _gates_section(gates: list[dict[str, Any]]) -> str:
    rows = "\n".join(
        "<tr>"
        f"<td><code>{_h(gate.get('gate_id', ''))}</code></td>"
        f"<td>{_h(gate.get('kind', ''))}</td>"
        f"<td>{_badge(gate.get('status', ''))}</td>"
        f"<td>{_h(gate.get('reason', ''))}</td>"
        f"<td>{_h(gate.get('next_action', ''))}</td>"
        "</tr>"
        for gate in gates
    )
    return _table_section("Gates", ["Gate", "Kind", "Status", "Reason", "Next Action"], rows)


def _decisions_section(decisions: list[dict[str, Any]]) -> str:
    rows = "\n".join(
        "<tr>"
        f"<td><code>{_h(decision.get('decision_id', ''))}</code></td>"
        f"<td>{_h(decision.get('mode', ''))}</td>"
        f"<td>{_badge(decision.get('status', ''))}</td>"
        f"<td>{_h(decision.get('next_action', ''))}</td>"
        "</tr>"
        for decision in decisions
    )
    return _table_section("Decisions", ["Decision", "Mode", "Status", "Next Action"], rows)


def _safety_section(safety: dict[str, Any]) -> str:
    required = safety.get("human_gate_required_for", [])
    chips = "\n".join(f'<span class="chip">{_h(item)}</span>' for item in required)
    return (
        '<section class="panel safety">'
        "<h2>Safety Defaults</h2>"
        '<div class="safety-grid">'
        f"<p><strong>Raw transcripts persisted</strong><span>{_h(str(safety.get('raw_transcripts_persisted', '')))}</span></p>"
        f"<p><strong>Remote execution default</strong><span>{_h(str(safety.get('remote_execution_default', '')))}</span></p>"
        "</div>"
        '<div class="chips">'
        f"{chips}"
        "</div>"
        "</section>"
    )


def _table_section(title: str, headers: list[str], rows: str) -> str:
    header_html = "".join(f"<th>{_h(header)}</th>" for header in headers)
    body = rows or f'<tr><td colspan="{len(headers)}" class="empty">No records</td></tr>'
    return (
        '<section class="panel">'
        f"<h2>{_h(title)}</h2>"
        '<div class="table-wrap">'
        "<table>"
        f"<thead><tr>{header_html}</tr></thead>"
        f"<tbody>{body}</tbody>"
        "</table>"
        "</div>"
        "</section>"
    )


def _badge(value: str) -> str:
    token = _safe_id(value)
    return f'<span class="badge badge-{_h(token)}">{_h(value)}</span>'


def _count_by_status(items: list[dict[str, Any]]) -> str:
    counts: dict[str, int] = {}
    for item in items:
        status = str(item.get("status", "unknown"))
        counts[status] = counts.get(status, 0) + 1
    if not counts:
        return "no records"
    return ", ".join(f"{count} {status}" for status, count in sorted(counts.items()))


def _h(value: object) -> str:
    return escape(str(value), quote=True)


def _html_styles() -> str:
    return """
:root {
  --ink: #17211b;
  --muted: #627069;
  --paper: #f4f0e8;
  --panel: #fffdf8;
  --line: #d7d0c2;
  --accent: #0f7b63;
  --warn: #a05318;
  --bad: #9f2727;
  --good: #1d6b43;
  --shadow: 0 18px 45px rgba(27, 35, 30, 0.12);
}
* { box-sizing: border-box; }
body {
  margin: 0;
  background:
    linear-gradient(135deg, rgba(15, 123, 99, 0.08), transparent 38%),
    repeating-linear-gradient(90deg, rgba(23, 33, 27, 0.035) 0, rgba(23, 33, 27, 0.035) 1px, transparent 1px, transparent 28px),
    var(--paper);
  color: var(--ink);
  font-family: "Aptos", "Segoe UI", sans-serif;
}
.shell {
  width: min(1180px, calc(100% - 32px));
  margin: 0 auto;
  padding: 32px 0 48px;
}
.masthead {
  min-height: 210px;
  display: flex;
  align-items: end;
  justify-content: space-between;
  gap: 24px;
  border-bottom: 2px solid var(--ink);
  padding-bottom: 22px;
}
.eyebrow {
  margin: 0 0 12px;
  color: var(--accent);
  font-size: 13px;
  font-weight: 800;
  letter-spacing: 0;
  text-transform: uppercase;
}
.endpoint-links {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  margin-top: 18px;
}
.endpoint-links a {
  color: var(--ink);
  border: 1px solid var(--line);
  border-radius: 6px;
  padding: 8px 10px;
  text-decoration: none;
  background: rgba(255, 255, 255, 0.52);
  font-size: 14px;
  font-weight: 700;
}
.endpoint-links a:hover {
  border-color: var(--accent);
  color: var(--accent);
}
.row-link {
  color: var(--accent);
  font-weight: 800;
  text-decoration: none;
}
.row-link:hover {
  text-decoration: underline;
}
h1 {
  max-width: 850px;
  margin: 0;
  font-family: Georgia, "Times New Roman", serif;
  font-size: clamp(46px, 7vw, 96px);
  line-height: 0.92;
  letter-spacing: 0;
}
.lead {
  max-width: 720px;
  margin: 18px 0 0;
  color: var(--muted);
  font-size: 18px;
  line-height: 1.5;
}
.stamp {
  flex: 0 0 172px;
  display: grid;
  gap: 8px;
  font-weight: 800;
  text-transform: uppercase;
}
.stamp span {
  border: 2px solid var(--ink);
  padding: 10px 12px;
  background: #e2f2ec;
}
.metrics {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
  margin: 22px 0;
}
.metric {
  min-height: 120px;
  background: var(--panel);
  border: 1px solid var(--line);
  box-shadow: var(--shadow);
  padding: 18px;
}
.metric strong {
  display: block;
  font-size: 38px;
  line-height: 1;
}
.metric span {
  display: block;
  margin-top: 12px;
  font-weight: 800;
}
.metric em {
  display: block;
  margin-top: 4px;
  color: var(--muted);
  font-style: normal;
  font-size: 13px;
}
.panel {
  margin-top: 16px;
  background: var(--panel);
  border: 1px solid var(--line);
  box-shadow: var(--shadow);
  padding: 18px;
}
.panel h2 {
  margin: 0 0 14px;
  font-size: 20px;
  letter-spacing: 0;
}
.gate-focus-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
  gap: 12px;
}
.gate-focus-card {
  border: 1px solid var(--line);
  padding: 14px;
  background: #fffaf0;
}
.gate-focus-card p {
  margin: 10px 0 0;
  color: var(--muted);
}
.gate-focus-card strong {
  display: block;
  color: var(--ink);
  font-size: 12px;
  text-transform: uppercase;
}
.gate-focus-card code {
  overflow-wrap: anywhere;
}
.gate-focus-head {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
}
.gate-focus-head code {
  overflow-wrap: anywhere;
}
.run-details {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
  gap: 12px;
}
.run-detail {
  border: 1px solid var(--line);
  padding: 14px;
  background: #fffaf0;
}
.run-detail h3 {
  margin: 0 0 12px;
  font-size: 15px;
  overflow-wrap: anywhere;
}
.path-list {
  display: grid;
  grid-template-columns: 110px minmax(0, 1fr);
  gap: 8px 10px;
  margin: 0;
}
.path-list dt {
  color: var(--muted);
  font-size: 12px;
  font-weight: 800;
  text-transform: uppercase;
}
.path-list dd {
  margin: 0;
  min-width: 0;
}
.run-detail code {
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}
.command {
  margin: 14px 0 0;
  border-top: 1px solid var(--line);
  padding-top: 12px;
}
.command span {
  display: block;
  margin-bottom: 6px;
  color: var(--muted);
  font-size: 12px;
  font-weight: 800;
  text-transform: uppercase;
}
.table-wrap { overflow-x: auto; }
table {
  width: 100%;
  border-collapse: collapse;
  font-size: 14px;
}
th {
  color: var(--muted);
  font-size: 12px;
  text-align: left;
  text-transform: uppercase;
  letter-spacing: 0;
}
td, th {
  border-bottom: 1px solid var(--line);
  padding: 11px 10px;
  vertical-align: top;
}
td:last-child { min-width: 260px; }
code {
  font-family: "Cascadia Mono", "Consolas", monospace;
  font-size: 12px;
}
.badge, .chip {
  display: inline-block;
  border: 1px solid var(--line);
  padding: 4px 8px;
  font-size: 12px;
  font-weight: 800;
  white-space: nowrap;
}
.badge-completed, .badge-pass, .badge-executed { color: var(--good); background: #e6f2ec; }
.badge-blocked, .badge-failed, .badge-fail { color: var(--bad); background: #fae8e4; }
.badge-open, .badge-pending, .badge-selected, .badge-medium { color: var(--warn); background: #f8ecdc; }
.badge-low, .badge-idle { color: var(--accent); background: #e2f2ec; }
.empty { color: var(--muted); }
.safety-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}
.safety-grid p {
  margin: 0;
  border: 1px solid var(--line);
  padding: 14px;
}
.safety-grid strong, .safety-grid span { display: block; }
.safety-grid span {
  margin-top: 8px;
  color: var(--accent);
  font-weight: 800;
}
.chips {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 14px;
}
@media (max-width: 820px) {
  .masthead { display: block; }
  .stamp { margin-top: 18px; }
  .metrics { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .safety-grid { grid-template-columns: 1fr; }
}
@media (max-width: 520px) {
  .shell { width: min(100% - 20px, 1180px); padding-top: 20px; }
  h1 { font-size: 42px; }
  .metrics { grid-template-columns: 1fr; }
  td, th { padding: 9px 8px; }
}
""".strip()
