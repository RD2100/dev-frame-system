"""Visual Control Plane read model built from local runtime state."""
from __future__ import annotations

import json
from html import escape
from pathlib import Path
from typing import Any
from urllib.parse import quote

import yaml

from .runtime_digest import build_runtime_digest
from .skill_registry import list_methodology_skills
from .team_runtime import build_team_runtime_view

ROOT = Path(__file__).resolve().parent.parent
ACTION_STATUSES = ("open", "blocked", "ready", "info")
ACTION_PRIORITIES = ("high", "medium", "low")
ACTION_SOURCE_TYPES = ("gate", "go_run", "run", "decision", "session")

_DASHBOARD_TRANSLATIONS: dict[str, dict[str, str]] = {
    "en": {
        "html_lang": "en",
        "title": "DevFrame Visual Control Plane",
        "eyebrow": "DevFrame Control Plane",
        "h1": "Visual State Snapshot",
        "lead": "A read-only view of projects, agents, runs, evidence gates, and controller decisions.",
        "projects_label": "projects",
        "runs_label": "runs",
        "language_label": "Language",
        "english_label": "English",
        "chinese_label": "中文",
        "gate_focus": "Gate Focus",
        "no_active_gates": "No active gates.",
        "control_workbench": "Control Plane Workbench",
        "workbench_intro": "Current project, agents, sessions, gates, and next action in one governed view.",
        "active_project": "Active Project",
        "agent_registry": "Agent Registry",
        "session_stream": "Session Stream",
        "gate_state": "Gate State",
        "primary_action": "Primary Action",
        "active_run": "Active Run",
        "no_project": "No project registered yet.",
        "no_run": "No active run.",
        "no_agents": "No agents registered.",
        "no_sessions": "No sessions imported yet.",
        "all_gates_clear": "All gates clear.",
        "action_queue": "Action Queue",
        "go_coding_agents": "/go Coding Agents",
        "go_run": "Go Run",
        "shard": "Shard",
        "targets": "Targets",
        "target_bytes": "Target Bytes",
        "changed_files": "Changed Files",
        "worker_command": "Worker Command",
        "go_status_command": "Status Command",
        "go_execute_command": "Execute Command",
        "metadata": "Metadata",
        "action_queue_handoff": "Action Queue Handoff",
        "readonly_queue_intro": "Read-only queue for manual resume, review, or Web AI handoff.",
        "do_not_execute": "Do not execute commands until the matching gate and risk boundary are cleared.",
        "state_json": "State JSON",
        "client_plan": "Client Plan",
        "client_manifest": "Client Manifest",
        "t3_bridge": "T3 Bridge",
        "t3_shell": "T3 Shell",
        "session_json": "Session JSON",
        "action_json": "Action JSON",
        "action_handoff": "Action Handoff",
        "endpoint_nav_label": "Read-only dashboard endpoints",
        "priority": "Priority",
        "status": "Status",
        "action": "Action",
        "source": "Source",
        "source_id": "Source ID",
        "action_id": "Action ID",
        "resume_filter": "Resume Filter",
        "resume_filter_label": "Resume filter",
        "detail": "Detail",
        "command": "Command",
        "handoff": "Handoff",
        "markdown_link": "Markdown",
        "no_actions": "(no actions)",
        "provider_bindings": "Provider Bindings",
        "binding": "Binding",
        "provider": "Provider",
        "mode": "Mode",
        "health": "Health",
        "adapter_config": "Adapter Config",
        "manual_fallback": "Manual Fallback",
        "notes": "Notes",
        "projects_section": "Projects",
        "project": "Project",
        "name": "Name",
        "id": "ID",
        "risk": "Risk",
        "goal": "Goal",
        "runs_section": "Runs",
        "run": "Run",
        "entry": "Entry",
        "taskspec": "TaskSpec",
        "evidence": "Evidence",
        "review": "Review",
        "run_details": "Run Details",
        "details": "Details",
        "taskspec_json": "TaskSpec JSON",
        "task_input": "Task Input",
        "execution_report": "ExecutionReport",
        "packet": "Packet",
        "current_decision": "Current Decision",
        "decision_next_action": "Decision Next Action",
        "next_command": "Next command",
        "missing": "missing",
        "resolve_gate": "Resolve gate before execution.",
        "agents": "Agents",
        "sessions": "Sessions",
        "session": "Session",
        "task_spec_id": "TaskSpec ID",
        "messages": "Messages",
        "tool_calls": "Tool Calls",
        "diff_summary": "Diff Summary",
        "cost": "Cost",
        "tokens": "Tokens",
        "role": "Role",
        "scope": "Scope",
        "binding_health": "Binding Health",
        "gates": "Gates",
        "kind": "Kind",
        "reason": "Reason",
        "next_action": "Next Action",
        "decisions": "Decisions",
        "safety_defaults": "Safety Defaults",
        "raw_transcripts_persisted": "Raw transcripts persisted",
        "remote_execution_default": "Remote execution default",
        "no_records": "No records",
        "registered_units": "registered units",
        "agent": "Agent",
        "gate": "Gate",
        "decision": "Decision",
        "methodology": "Methodology",
        "methodology_skills": "Methodology Skills",
        "skill_name": "Skill",
        "skill_triggers": "Triggers",
    },
    "zh-CN": {
        "html_lang": "zh-CN",
        "title": "DevFrame 可视化控制面",
        "eyebrow": "DevFrame 控制面",
        "h1": "可视化状态快照",
        "lead": "项目、智能体、运行、证据门控和控制器决策的只读视图。",
        "projects_label": "个项目",
        "runs_label": "个运行",
        "language_label": "语言",
        "english_label": "English",
        "chinese_label": "中文",
        "gate_focus": "门控聚焦",
        "no_active_gates": "无活跃门控。",
        "action_queue": "动作队列",
        "go_coding_agents": "/go 编码智能体",
        "go_run": "Go 运行",
        "shard": "分片",
        "targets": "目标",
        "target_bytes": "目标字节数",
        "changed_files": "变更文件",
        "worker_command": "Worker 命令",
        "go_status_command": "状态命令",
        "go_execute_command": "执行命令",
        "metadata": "元数据",
        "action_queue_handoff": "动作队列交接",
        "readonly_queue_intro": "用于手动恢复、审查或 Web AI 交接的只读队列。",
        "do_not_execute": "在匹配的门控和风险边界确认清除之前，不要执行命令。",
        "state_json": "状态 JSON",
        "client_plan": "客户端计划",
        "client_manifest": "Client Manifest",
        "t3_bridge": "T3 Bridge",
        "t3_shell": "T3 Shell",
        "session_json": "会话 JSON",
        "action_json": "动作 JSON",
        "action_handoff": "动作交接",
        "endpoint_nav_label": "只读看板端点",
        "priority": "优先级",
        "status": "状态",
        "action": "动作",
        "source": "来源",
        "source_id": "来源 ID",
        "action_id": "动作 ID",
        "resume_filter": "恢复过滤器",
        "resume_filter_label": "恢复过滤器",
        "detail": "详情",
        "command": "命令",
        "handoff": "交接",
        "markdown_link": "Markdown",
        "no_actions": "（无动作）",
        "provider_bindings": "提供者绑定",
        "binding": "绑定",
        "provider": "提供者",
        "mode": "模式",
        "health": "健康状态",
        "adapter_config": "适配器配置",
        "manual_fallback": "手动回退",
        "notes": "备注",
        "projects_section": "项目",
        "project": "项目",
        "name": "名称",
        "id": "ID",
        "risk": "风险",
        "goal": "目标",
        "runs_section": "运行",
        "run": "运行",
        "entry": "入口",
        "taskspec": "任务规格",
        "evidence": "证据",
        "review": "审查",
        "run_details": "运行详情",
        "details": "详情",
        "taskspec_json": "任务规格 JSON",
        "task_input": "任务输入",
        "execution_report": "执行报告",
        "packet": "数据包",
        "current_decision": "当前决策",
        "decision_next_action": "决策下一步",
        "next_command": "下一步命令",
        "missing": "缺失",
        "resolve_gate": "在执行前解决门控问题。",
        "agents": "智能体",
        "sessions": "会话",
        "session": "会话",
        "task_spec_id": "任务规格 ID",
        "messages": "消息",
        "tool_calls": "工具调用",
        "diff_summary": "差异摘要",
        "cost": "成本",
        "tokens": "Token",
        "role": "角色",
        "scope": "范围",
        "binding_health": "绑定健康状态",
        "gates": "门控",
        "kind": "类型",
        "reason": "原因",
        "next_action": "下一步动作",
        "decisions": "决策",
        "safety_defaults": "安全默认值",
        "raw_transcripts_persisted": "原始转录持久化",
        "remote_execution_default": "远程执行默认",
        "no_records": "无记录",
        "registered_units": "条记录",
        "agent": "智能体",
        "gate": "门控",
        "decision": "决策",
        "methodology": "方法学",
        "methodology_skills": "方法论技能",
        "skill_name": "技能",
        "skill_triggers": "触发词",
    },
}


def resolve_dashboard_lang(raw_lang: str | None) -> str:
    if not raw_lang:
        return "en"
    normalized = raw_lang.strip().lower()
    if normalized in {"zh-cn", "zh"}:
        return "zh-CN"
    if normalized == "en":
        return "en"
    return "en"


def dashboard_t(key: str, lang: str = "en") -> str:
    translations = _DASHBOARD_TRANSLATIONS.get(lang, _DASHBOARD_TRANSLATIONS["en"])
    return translations.get(key, _DASHBOARD_TRANSLATIONS["en"].get(key, key))


def _lang_switch(lang: str) -> str:
    label = dashboard_t("language_label", lang)
    options = [
        ("en", dashboard_t("english_label", lang)),
        ("zh-CN", dashboard_t("chinese_label", lang)),
    ]
    links = []
    for code, text in options:
        current = code == lang
        attrs = ' class="active" aria-current="true"' if current else ""
        links.append(f'<a{attrs} href="?lang={code}">{_h(text)}</a>')
    return f'<nav class="lang-switch" aria-label="{_h(label)}"><span>{_h(label)}</span>{"".join(links)}</nav>'


def _action_md_href(action_id: str, lang: str) -> str:
    href = f"/actions.md?action_id={quote(action_id)}"
    if lang == "zh-CN":
        href += f"&lang={lang}"
    return href


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
    go_runs = _go_run_states(digest.get("runtime_dir", ""))
    action_runs = _read_action_runs(digest.get("runtime_dir", ""))
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
    web_ai_sessions = _web_ai_session_states(runtime_dir)
    all_runs = runs + paper_runs
    all_gates = (
        _gate_states(dispatches, reports_by_packet)
        + [_paper_gate_state(path) for path in paper_roots]
        + paper_provider_gates
        + _web_ai_review_gate_states(web_ai_sessions)
    )
    all_decisions = (
        [_decision_state(dispatch, reports_by_packet) for dispatch in dispatches]
        + [_paper_decision_state(path) for path in paper_roots]
    )
    go_packet_dirs = _go_packet_dirs(go_runs)
    all_sessions = (
        [
            _rdgoal_session_state(dispatch, reports_by_packet.get(dispatch.get("packet_id", "")))
            for dispatch in dispatches
            if str(dispatch.get("packet_dir") or "") not in go_packet_dirs
        ]
        + _go_session_states(go_runs)
        + [
            _paper_session_state(root, binding)
            for root, binding in zip(paper_roots, paper_provider_bindings)
        ]
        + web_ai_sessions
        + _atgo_reviewer_session_states(digest.get("runtime_dir", ""), projects)
    )
    all_agents = _default_agents(paper_provider_bindings) + _web_ai_agents(web_ai_sessions)
    all_next_actions = _next_actions(all_runs, all_gates, all_decisions, all_sessions, go_runs)
    return {
        "version": 1,
        "projects": projects + paper_projects,
        "provider_bindings": _default_provider_bindings(web_ai_sessions) + paper_provider_bindings + _web_ai_provider_bindings(web_ai_sessions),
        "agents": all_agents,
        "sessions": all_sessions,
        "go_runs": go_runs,
        "runs": all_runs,
        "gates": all_gates,
        "decisions": all_decisions,
        "next_actions": all_next_actions,
        "team": _build_team_model(
            all_agents,
            all_sessions,
            go_runs,
            dispatches,
            all_gates,
            all_runs,
            all_decisions,
            paper_roots,
            reports_by_packet,
            all_next_actions,
            action_runs,
            digest.get("runtime_dir", ""),
        ),
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
        "skills": list_methodology_skills(),
    }


def render_visual_control_plane_state_json(state: dict[str, Any]) -> str:
    return json.dumps(state, indent=2, ensure_ascii=True)


def public_session_summaries(sessions: object) -> list[dict[str, Any]]:
    if not isinstance(sessions, list):
        return []
    return [
        _public_session_summary(session)
        for session in sessions
        if isinstance(session, dict)
    ]


def _public_session_summary(session: dict[str, Any]) -> dict[str, Any]:
    return {
        "session_id": str(session.get("session_id") or ""),
        "provider": str(session.get("provider") or ""),
        "binding_id": str(session.get("binding_id") or ""),
        "agent_id": str(session.get("agent_id") or ""),
        "agent_role": str(session.get("agent_role") or ""),
        "project_id": str(session.get("project_id") or ""),
        "run_id": str(session.get("run_id") or ""),
        "task_spec_id": _public_ref_label(session.get("task_spec_id")),
        "status": str(session.get("status") or "unknown"),
        "message_count": _public_count(session.get("messages")),
        "tool_call_count": _public_count(session.get("tool_calls")),
        "changed_files": _visible_changed_files(session.get("changed_files") or []),
        "diff_summary": str(session.get("diff_summary") or ""),
        "gates": [str(gate) for gate in session.get("gates", [])] if isinstance(session.get("gates"), list) else [],
        "actions": [str(action) for action in session.get("actions", [])] if isinstance(session.get("actions"), list) else [],
    }


def _public_ref_label(value: object) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    parts = [part for part in text.replace("\\", "/").split("/") if part]
    if not parts:
        return ""
    if len(parts) >= 2 and parts[-2] == "paper_task":
        return "/".join(parts[-2:])
    if len(parts) >= 2 and parts[-1] == "TASKSPEC.json":
        return "/".join(parts[-2:])
    return parts[-1]


def _public_count(value: object) -> int:
    return len(value) if isinstance(value, list) else 0


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


def render_action_queue_markdown(next_actions: list[dict[str, Any]], lang: str = "en") -> str:
    lang = resolve_dashboard_lang(lang)
    lines = [
        f"# {dashboard_t('action_queue_handoff', lang)}",
        "",
        dashboard_t("readonly_queue_intro", lang),
        dashboard_t("do_not_execute", lang),
        "",
    ]
    if not next_actions:
        lines.append(dashboard_t("no_actions", lang))
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
            f"- {dashboard_t('action_id', lang)}: `{action_id}`",
            f"- {dashboard_t('priority', lang)}: `{priority}`",
            f"- {dashboard_t('status', lang)}: `{status}`",
            f"- {dashboard_t('source', lang)}: `{source_type}` `{source_id}`",
        ])
        resume_filter = _action_resume_filter(action)
        if resume_filter:
            lines.append(f"- {dashboard_t('resume_filter', lang)}: `{resume_filter}`")
        if detail:
            lines.append(f"- {dashboard_t('detail', lang)}: {detail}")
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
    lang: str = "en",
    focus_go_run_id: str | None = None,
) -> str:
    lang = resolve_dashboard_lang(lang)
    projects = state.get("projects", [])
    provider_bindings = state.get("provider_bindings", [])
    sessions = state.get("sessions", [])
    runs = state.get("runs", [])
    gates = state.get("gates", [])
    decisions = state.get("decisions", [])
    next_actions = state.get("next_actions", [])
    agents = state.get("agents", [])
    safety = state.get("safety", {})
    return "\n".join([
        "<!doctype html>",
        f'<html lang="{dashboard_t("html_lang", lang)}">',
        "<head>",
        '<meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        _refresh_meta(refresh_seconds),
        f"<title>{_h(dashboard_t('title', lang))}</title>",
        "<style>",
        _html_styles(),
        "</style>",
        "</head>",
        "<body>",
        '<main class="shell">',
        '<section class="masthead">',
        "<div>",
        f'<p class="eyebrow">{_h(dashboard_t("eyebrow", lang))}</p>',
        f"<h1>{_h(dashboard_t('h1', lang))}</h1>",
        f'<p class="lead">{_h(dashboard_t("lead", lang))}</p>',
        _lang_switch(lang),
        _endpoint_links(endpoint_links, lang),
        "</div>",
        '<div class="stamp">',
        f"<span>{len(projects)} {dashboard_t('projects_label', lang)}</span>",
        f"<span>{len(runs)} {dashboard_t('runs_label', lang)}</span>",
        "</div>",
        "</section>",
        _summary_band(state, lang),
        _workbench_section(state, action_links=endpoint_links, lang=lang),
        _gate_focus_section(gates, next_actions, action_links=endpoint_links, lang=lang),
        _next_actions_section(next_actions, action_links=endpoint_links, lang=lang),
        _go_runs_section(state.get("go_runs", []), action_links=endpoint_links, lang=lang, focus_go_run_id=focus_go_run_id),
        _provider_bindings_section(provider_bindings, lang),
        _projects_section(projects, lang),
        _sessions_section(sessions, lang),
        _runs_section(runs, lang),
        _run_details_section(runs, decisions, lang),
        _agents_section(agents, provider_bindings, lang),
        _gates_section(gates, lang),
        _decisions_section(decisions, lang),
        _safety_section(safety, lang),
        _skills_section(state.get("skills", []), lang),
        "</main>",
        "</body>",
        "</html>",
        "",
    ])


def _refresh_meta(refresh_seconds: int | None) -> str:
    if refresh_seconds is None or refresh_seconds <= 0:
        return ""
    return f'<meta http-equiv="refresh" content="{refresh_seconds}">'


def _endpoint_links(enabled: bool, lang: str = "en") -> str:
    if not enabled:
        return ""
    links = [
        (dashboard_t("state_json", lang), "/state.json"),
        (dashboard_t("client_plan", lang), "/client-plan.json"),
        (dashboard_t("client_manifest", lang), "/client-manifest.json"),
        (dashboard_t("t3_bridge", lang), "/t3-bridge.json"),
        (dashboard_t("t3_shell", lang), "/t3-shell.json"),
        (dashboard_t("session_json", lang), "/sessions.json"),
        (dashboard_t("action_json", lang), "/actions.json"),
        (dashboard_t("action_handoff", lang), "/actions.md" if lang != "zh-CN" else f"/actions.md?lang={lang}"),
        ("/go Dispatch", "/go/dispatch" if lang != "zh-CN" else f"/go/dispatch?lang={lang}"),
    ]
    items = "\n".join(
        f'<a href="{_h(href)}">{_h(label)}</a>'
        for label, href in links
    )
    return f'<nav class="endpoint-links" aria-label="{_h(dashboard_t("endpoint_nav_label", lang))}">{items}</nav>'


def _default_provider_bindings(web_ai_sessions: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    bindings = [
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
    active_providers = {
        _safe_id(str(session.get("provider") or ""))
        for session in web_ai_sessions or []
        if _session_status(session.get("status")) in {"active", "completed", "idle"}
    }
    for binding in bindings:
        if _safe_id(str(binding.get("provider") or "")) in active_providers:
            binding["health"] = "ready"
            binding["notes"] = "Reference browser-hosted AI binding; summary-only imported session is available."
    return bindings


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


def _atgo_verdict_status(verdict: str) -> str:
    normalized = _safe_id(verdict)
    tokens = set(normalized.split("-"))
    negative_phrases = (
        "do-not",
        "not-proceed",
        "not-approve",
        "not-approved",
        "not-accept",
        "not-accepted",
        "cannot-proceed",
        "should-not-proceed",
    )
    if any(phrase in normalized for phrase in negative_phrases):
        return "blocked"
    if tokens & {"fail", "failed", "stop", "blocked", "reject", "rejected", "deny", "denied"}:
        return "blocked"
    if tokens & {"pass", "passed", "proceed", "approve", "approved", "accept", "accepted"}:
        return "pass"
    return "open"


def _atgo_ref_type(path: Path) -> str:
    name = path.name.lower()
    if name.endswith(".zip"):
        return "package"
    if path.is_dir() and name.startswith("web-gpt-package"):
        return "package"
    if name == "review.yaml":
        return "review_metadata"
    if name == "review.md":
        return "review"
    if name in {"execution-report.md", "final-report.md", "worker-report.md", "executor-report.md"}:
        return "report"
    if name == "safety-report.json":
        return "safety_report"
    if name == "chain-evidence.json":
        return "chain_evidence"
    if name == "diff.patch":
        return "diff"
    return "artifact"


def _atgo_run_artifacts(runtime_dir: str | Path | None = None) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    if not runtime_dir:
        return [], [], [], []
    candidate = Path(runtime_dir)
    if (candidate / "atgo-runs").exists():
        atgo_root = candidate / "atgo-runs"
    elif (candidate / ".devframe-runtime" / "atgo-runs").exists():
        atgo_root = candidate / ".devframe-runtime" / "atgo-runs"
    else:
        return [], [], [], []
    evidence: list[dict[str, Any]] = []
    review_gates: list[dict[str, Any]] = []
    messages: list[dict[str, Any]] = []
    events: list[dict[str, Any]] = []
    for run_dir in sorted(atgo_root.iterdir()):
        if not run_dir.is_dir():
            continue
        run_id = _safe_id(run_dir.name)
        review_yaml = run_dir / "review.yaml"
        review_data = _read_yaml(review_yaml)
        verdict = str(review_data.get("verdict", "")).strip() if review_data else ""
        if verdict:
            gate_status = _atgo_verdict_status(verdict)
            reason = f"ATGO review {run_id}: {verdict}"
        else:
            gate_status = "blocked"
            reason = f"ATGO review {run_id}: missing or corrupt review.yaml"
        review_gates.append({
            "gate_id": _safe_id(f"{run_id}-review-gate"),
            "kind": "acceptance",
            "status": gate_status,
            "reason": reason,
            "run_id": run_id,
        })
        review_md = run_dir / "review.md"
        review_md_added = False
        review_yaml_added = False
        if review_md.exists():
            evidence.append({
                "evidence_id": _safe_id(f"atgo-review-md-{run_id}"),
                "run_id": run_id,
                "ref_type": "review",
                "ref_path": str(review_md),
            })
            review_md_added = True
        if review_yaml.exists():
            evidence.append({
                "evidence_id": _safe_id(f"atgo-review-yaml-{run_id}"),
                "run_id": run_id,
                "ref_type": "review_metadata",
                "ref_path": str(review_yaml),
            })
            review_yaml_added = True
        for entry in sorted(run_dir.iterdir()):
            if entry.is_dir():
                if entry.name.startswith("web-gpt-package"):
                    evidence.append({
                        "evidence_id": _safe_id(f"atgo-{entry.stem}-{run_id}"),
                        "run_id": run_id,
                        "ref_type": "package",
                        "ref_path": str(entry),
                    })
                continue
            if entry == review_md and review_md_added:
                continue
            if entry == review_yaml and review_yaml_added:
                continue
            evidence.append({
                "evidence_id": _safe_id(f"atgo-{entry.stem}-{run_id}"),
                "run_id": run_id,
                "ref_type": _atgo_ref_type(entry),
                "ref_path": str(entry),
            })
        messages.append({
            "message_id": _safe_id(f"atgo-reviewer-to-team-{run_id}"),
            "from_role": "reviewer",
            "to_role": "team",
            "kind": "review-status",
            "run_id": run_id,
            "summary": f"ATGO review {run_id}: {verdict or 'unknown'}",
        })
        events.append({
            "event_id": _safe_id(f"atgo-review-{run_id}"),
            "kind": "atgo-review",
            "run_id": run_id,
            "summary": f"ATGO review run {run_id}: {verdict or 'unknown status'}",
        })
    return evidence, review_gates, messages, events


def _atgo_reviewer_session_states(runtime_dir: str | Path | None = None, projects: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    if not runtime_dir:
        return []
    candidate = Path(runtime_dir)
    if (candidate / "atgo-runs").exists():
        atgo_root = candidate / "atgo-runs"
    elif (candidate / ".devframe-runtime" / "atgo-runs").exists():
        atgo_root = candidate / ".devframe-runtime" / "atgo-runs"
    else:
        return []
    run_ids: list[str] = []
    for run_dir in sorted(atgo_root.iterdir()):
        if run_dir.is_dir():
            run_ids.append(_safe_id(run_dir.name))
    if not run_ids:
        return []
    project_id = _safe_id(str((projects or [{}])[0].get("project_id") or "dev-frame-system"))
    evidence_refs: list[str] = []
    for run_id in run_ids:
        run_dir = atgo_root / run_id
        for entry in sorted(run_dir.iterdir()):
            if entry.is_dir() and entry.name.startswith("web-gpt-package"):
                evidence_refs.append(str(entry))
            elif entry.is_file() and entry.name in {"review.md", "review.yaml"}:
                evidence_refs.append(str(entry))
    return [{
        "session_id": "web-gpt-review-board-session",
        "provider": "chatgpt",
        "binding_id": "chatgpt-web",
        "agent_id": "web-gpt-review-board",
        "agent_role": "reviewer",
        "project_id": project_id,
        "run_id": "",
        "task_spec_id": "",
        "status": "idle",
        "messages": [{
            "message_id": "web-gpt-review-board-summary",
            "role": "assistant",
            "content_summary": f"ATGO/Web-GPT review board session linked to {len(run_ids)} ATGO run(s): {', '.join(run_ids)}",
        }],
        "tool_calls": [],
        "changed_files": [],
        "diff_summary": "",
        "evidence_refs": evidence_refs,
        "cost": {},
        "tokens": {},
        "gates": [],
        "actions": [],
        "native_refs": {
            "related_run_ids": run_ids,
        },
    }]


def _build_team_model(
    agents: list[dict[str, Any]],
    sessions: list[dict[str, Any]],
    go_runs: list[dict[str, Any]],
    dispatches: list[dict[str, Any]],
    gates: list[dict[str, Any]],
    runs: list[dict[str, Any]],
    decisions: list[dict[str, Any]],
    paper_roots: list[Path],
    reports_by_packet: dict[str, dict[str, Any]],
    next_actions: list[dict[str, Any]],
    action_runs: list[dict[str, Any]] | None = None,
    runtime_dir: str | Path | None = None,
) -> dict[str, Any]:
    agent_registry = _team_agent_registry(agents, sessions, go_runs)
    task_board = _team_task_board(go_runs, dispatches, runs, sessions)
    message_bus = _team_message_bus(sessions, go_runs, dispatches)
    event_log = _team_event_log(dispatches, runs, gates, decisions, go_runs, action_runs)
    evidence_store = _team_evidence_store(go_runs, dispatches, runs, sessions, reports_by_packet)
    review_gates = _team_review_gates(gates, go_runs, next_actions)
    conflict_control = _team_conflict_control(go_runs, dispatches, paper_roots)
    atgo_evidence, atgo_gates, atgo_messages, atgo_events = _atgo_run_artifacts(runtime_dir)
    evidence_store.extend(atgo_evidence)
    review_gates.extend(atgo_gates)
    message_bus.extend(atgo_messages)
    event_log.extend(atgo_events)
    # Real team runtime objects: when a run recorded team events at execution
    # time, surface those durable, recorded facts alongside the read-time
    # projection. Empty when no run has recorded events, so default behavior is
    # unchanged.
    recorded = build_team_runtime_view(runtime_dir)
    message_bus.extend(recorded.get("message_bus", []))
    event_log.extend(recorded.get("event_log", []))
    conflict_control.extend(recorded.get("conflict_control", []))
    review_gates.extend(recorded.get("review_gates", []))
    # Real Agent Registry + Task Board: add recorded participants/tasks that the
    # read-time projection did not already surface (dedupe by id), so recorded
    # runtime facts win without double-listing the projection.
    _projected_agent_ids = {str(a.get("agent_id") or "") for a in agent_registry}
    for recorded_agent in recorded.get("agent_registry", []):
        if str(recorded_agent.get("agent_id") or "") not in _projected_agent_ids:
            agent_registry.append(recorded_agent)
    _projected_task_ids = {str(t.get("task_id") or "") for t in task_board}
    for recorded_task in recorded.get("task_board", []):
        if str(recorded_task.get("task_id") or "") not in _projected_task_ids:
            task_board.append(recorded_task)
    _projected_evidence_ids = {str(e.get("evidence_id") or "") for e in evidence_store}
    for recorded_evidence in recorded.get("evidence_store", []):
        if str(recorded_evidence.get("evidence_id") or "") not in _projected_evidence_ids:
            evidence_store.append(recorded_evidence)
    return {
        "agent_registry": agent_registry,
        "task_board": task_board,
        "message_bus": message_bus,
        "event_log": event_log,
        "evidence_store": evidence_store,
        "review_gates": review_gates,
        "conflict_control": conflict_control,
    }


def _team_agent_registry(
    agents: list[dict[str, Any]],
    sessions: list[dict[str, Any]],
    go_runs: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    seen: set[str] = set()
    for agent in agents:
        agent_id = str(agent.get("agent_id") or "")
        if not agent_id or agent_id in seen:
            continue
        seen.add(agent_id)
        agent_sessions = [
            _safe_id(str(s.get("session_id") or ""))
            for s in sessions
            if str(s.get("agent_id") or "") == agent_id
        ]
        entries.append({
            "agent_id": agent_id,
            "role": str(agent.get("role") or ""),
            "binding_id": str(agent.get("binding_id") or ""),
            "status": str(agent.get("status") or "idle"),
            "session_ids": agent_sessions,
        })
    for run in go_runs:
        for agent in run.get("agents", []):
            if not isinstance(agent, dict):
                continue
            agent_id = _safe_id(str(agent.get("agent_id") or ""))
            if not agent_id or agent_id in seen:
                continue
            seen.add(agent_id)
            go_run_id = _safe_id(str(run.get("go_run_id") or ""))
            agent_sessions = [
                _safe_id(str(s.get("session_id") or ""))
                for s in sessions
                if str(s.get("agent_id") or "") == agent_id
            ]
            entries.append({
                "agent_id": agent_id,
                "role": "go-worker",
                "binding_id": "local-executor",
                "status": str(agent.get("status") or agent.get("worker_status") or "idle"),
                "session_ids": agent_sessions,
            })
    return entries


def _team_task_board(
    go_runs: list[dict[str, Any]],
    dispatches: list[dict[str, Any]],
    runs: list[dict[str, Any]],
    sessions: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    tasks: list[dict[str, Any]] = []
    for run in go_runs:
        go_run_id = _safe_id(str(run.get("go_run_id") or ""))
        agent_ids = [
            _safe_id(str(a.get("agent_id") or ""))
            for a in run.get("agents", [])
            if isinstance(a, dict)
        ]
        session_ids = [
            _safe_id(str(s.get("session_id") or ""))
            for s in sessions
            if str(s.get("run_id") or "") == go_run_id
        ]
        targets: list[str] = []
        for a in run.get("agents", []):
            if isinstance(a, dict):
                targets.extend(str(t) for t in a.get("targets", []) if isinstance(a.get("targets"), list))
        task = {
            "task_id": go_run_id,
            "type": "go-run",
            "project_id": _safe_id(str(run.get("project_id") or "")),
            "status": str(run.get("status") or "queued"),
            "agent_ids": agent_ids,
            "session_ids": session_ids,
            "target_files": targets,
        }
        methodology = _go_methodology_state(run.get("methodology"))
        if methodology is not None:
            task["methodology"] = methodology
        tasks.append(task)
    for dispatch in dispatches:
        packet_id = dispatch.get("packet_id") or _fallback_id(dispatch, "run")
        dispatch_run = next(
            (r for r in runs if str(r.get("run_id") or "") == _safe_id(str(packet_id))),
            None,
        )
        dispatch_sessions = [
            _safe_id(str(s.get("session_id") or ""))
            for s in sessions
            if str(s.get("run_id") or "") == _safe_id(str(packet_id))
        ]
        tasks.append({
            "task_id": _safe_id(str(packet_id)),
            "type": "rdgoal-dispatch",
            "project_id": _safe_id(str(dispatch.get("project_id") or "")),
            "status": str(dispatch_run.get("status") or "pending") if dispatch_run else "pending",
            "agent_ids": ["executor"],
            "session_ids": dispatch_sessions,
            "target_files": [],
        })
    return tasks


def _team_message_bus(
    sessions: list[dict[str, Any]],
    go_runs: list[dict[str, Any]],
    dispatches: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    messages: list[dict[str, Any]] = []
    for run in go_runs:
        go_run_id = _safe_id(str(run.get("go_run_id") or ""))
        for agent in run.get("agents", []):
            if not isinstance(agent, dict):
                continue
            agent_id = _safe_id(str(agent.get("agent_id") or ""))
            messages.append({
                "message_id": _safe_id(f"planner-to-{agent_id}-{go_run_id}"),
                "from_role": "planner",
                "to_role": str(agent.get("agent_id") or "worker"),
                "kind": "handoff",
                "run_id": go_run_id,
                "summary": f"Shard {agent.get('shard_index', '?')}/{agent.get('shard_count', '?')}: {_safe_id(str(agent.get('agent_id', '')))} dispatched.",
            })
    for dispatch in dispatches:
        packet_id = dispatch.get("packet_id") or _fallback_id(dispatch, "run")
        status = "ready" if dispatch.get("dispatch_ready") else "pending"
        messages.append({
            "message_id": _safe_id(f"planner-to-executor-{packet_id}"),
            "from_role": "planner",
            "to_role": "executor",
            "kind": "handoff",
            "run_id": _safe_id(str(packet_id)),
            "summary": f"Dispatch {status}: {str(dispatch.get('operational_intent', ''))[:80]}",
        })
    _add_evidence_status_messages(messages, go_runs)
    return messages


def _add_evidence_status_messages(
    messages: list[dict[str, Any]],
    go_runs: list[dict[str, Any]],
) -> None:
    for run in go_runs:
        go_run_id = _safe_id(str(run.get("go_run_id") or ""))
        run_status = str(run.get("status") or "")
        if run_status in ("review-pass", "review-fail", "verified", "passed", "failed", "blocked"):
            messages.append({
                "message_id": _safe_id(f"reviewer-to-team-{go_run_id}"),
                "from_role": "reviewer",
                "to_role": "team",
                "kind": "review-status",
                "run_id": go_run_id,
                "summary": f"Review status for /go run {go_run_id}: {run_status}",
            })
        for agent in run.get("agents", []):
            if not isinstance(agent, dict):
                continue
            report_path = str(agent.get("report_path") or "")
            agent_status = str(agent.get("status") or "")
            agent_id = _safe_id(str(agent.get("agent_id") or ""))
            if report_path and agent_status in ("completed", "verified", "review-pass", "review-fail"):
                file_name = report_path.replace("\\", "/").rsplit("/", 1)[-1]
                role = "reviewer" if "review" in agent_status else "verifier"
                messages.append({
                    "message_id": _safe_id(f"{role}-to-team-{agent_id}-{go_run_id}"),
                    "from_role": role,
                    "to_role": "team",
                    "kind": "review-evidence",
                    "run_id": go_run_id,
                    "summary": f"Evidence for {agent_id} in /go run {go_run_id}: {file_name}",
                })


def _team_event_log(
    dispatches: list[dict[str, Any]],
    runs: list[dict[str, Any]],
    gates: list[dict[str, Any]],
    decisions: list[dict[str, Any]],
    go_runs: list[dict[str, Any]],
    action_runs: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for dispatch in dispatches:
        packet_id = dispatch.get("packet_id") or _fallback_id(dispatch, "run")
        events.append({
            "event_id": _safe_id(f"dispatch-{packet_id}"),
            "kind": "dispatch",
            "run_id": _safe_id(str(packet_id)),
            "summary": f"Packet dispatched: {str(dispatch.get('operational_intent', ''))[:80]}",
        })
    for run in go_runs:
        go_run_id = _safe_id(str(run.get("go_run_id") or ""))
        events.append({
            "event_id": _safe_id(f"go-run-created-{go_run_id}"),
            "kind": "go-run-created",
            "run_id": go_run_id,
            "summary": f"/go run {go_run_id} created with {len(run.get('agents', []))} agents",
        })
    for gate in gates:
        gate_id = _safe_id(str(gate.get("gate_id") or ""))
        events.append({
            "event_id": _safe_id(f"gate-{gate_id}"),
            "kind": "gate-state",
            "run_id": _safe_id(str(gate.get("run_id") or gate_id)),
            "summary": f"Gate {gate_id}: {str(gate.get('status', 'open'))}",
        })
    for decision in decisions:
        decision_id = _safe_id(str(decision.get("decision_id") or ""))
        events.append({
            "event_id": _safe_id(f"decision-{decision_id}"),
            "kind": "decision",
            "run_id": _safe_id(str(decision.get("run_id") or decision_id)),
            "summary": f"Decision {decision_id}: {str(decision.get('mode', ''))}/{str(decision.get('status', ''))}",
        })
    for record in (action_runs or []):
        action_id = _safe_id(str(record.get("action_id") or ""))
        run_id = _safe_id(str(record.get("action_run_id") or ""))
        go_run_id = _safe_id(str(record.get("go_run_id") or ""))
        raw_status = str(record.get("status") or "started").strip().lower()
        if raw_status in ("completed", "passed", "pass"):
            kind = "action-run-completed"
            exit_code = record.get("exit_code")
            completed_at = str(record.get("completed_at") or "")
            stdout_log = str(record.get("stdout_log") or "")
            stderr_log = str(record.get("stderr_log") or "")
            summary_parts = [f"Action {action_id} completed for /go run {go_run_id}"]
            if exit_code is not None:
                summary_parts.append(f"exit_code={exit_code}")
            if completed_at:
                summary_parts.append(f"completed_at={completed_at}")
            if stdout_log:
                summary_parts.append(f"stdout_log={stdout_log}")
            if stderr_log:
                summary_parts.append(f"stderr_log={stderr_log}")
            summary = "; ".join(summary_parts)
            events.append({
                "event_id": _safe_id(f"action-run-{action_id}-{run_id}"),
                "kind": kind,
                "run_id": go_run_id,
                "summary": summary,
            })
        elif raw_status in ("failed", "fail", "error"):
            kind = "action-run-failed"
            exit_code = record.get("exit_code")
            completed_at = str(record.get("completed_at") or "")
            stdout_log = str(record.get("stdout_log") or "")
            stderr_log = str(record.get("stderr_log") or "")
            summary_parts = [f"Action {action_id} failed for /go run {go_run_id}"]
            if exit_code is not None:
                summary_parts.append(f"exit_code={exit_code}")
            if completed_at:
                summary_parts.append(f"completed_at={completed_at}")
            if stdout_log:
                summary_parts.append(f"stdout_log={stdout_log}")
            if stderr_log:
                summary_parts.append(f"stderr_log={stderr_log}")
            summary = "; ".join(summary_parts)
            events.append({
                "event_id": _safe_id(f"action-run-{action_id}-{run_id}"),
                "kind": kind,
                "run_id": go_run_id,
                "summary": summary,
            })
        else:
            kind = "action-run-started"
            summary = f"Action {action_id} started for /go run {go_run_id}"
            events.append({
                "event_id": _safe_id(f"action-run-{action_id}-{run_id}"),
                "kind": kind,
                "run_id": go_run_id,
                "summary": summary,
            })
    return events


def _team_evidence_store(
    go_runs: list[dict[str, Any]],
    dispatches: list[dict[str, Any]],
    runs: list[dict[str, Any]],
    sessions: list[dict[str, Any]],
    reports_by_packet: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    evidence: list[dict[str, Any]] = []
    for run in go_runs:
        go_run_id = _safe_id(str(run.get("go_run_id") or ""))
        for agent in run.get("agents", []):
            if not isinstance(agent, dict):
                continue
            evidence.append({
                "evidence_id": _safe_id(f"go-{go_run_id}-{agent.get('agent_id', '')}"),
                "run_id": go_run_id,
                "ref_type": "packet",
                "ref_path": str(agent.get("packet_dir") or agent.get("task_spec_path") or ""),
            })
            report_path = str(agent.get("report_path") or "")
            if report_path:
                evidence.append({
                    "evidence_id": _safe_id(f"go-report-{go_run_id}-{agent.get('agent_id', '')}"),
                    "run_id": go_run_id,
                    "ref_type": "report",
                    "ref_path": report_path,
                })
    for dispatch in dispatches:
        packet_id = dispatch.get("packet_id") or _fallback_id(dispatch, "run")
        packet_dir = str(dispatch.get("packet_dir") or "")
        if packet_dir:
            evidence.append({
                "evidence_id": _safe_id(f"rdgoal-packet-{packet_id}"),
                "run_id": _safe_id(str(packet_id)),
                "ref_type": "packet",
                "ref_path": str(Path(packet_dir) / "TASKSPEC.json"),
            })
        report = reports_by_packet.get(str(packet_id) or dispatch.get("packet_id", ""))
        if report:
            report_path = str(report.get("report_path") or "")
            if report_path:
                evidence.append({
                    "evidence_id": _safe_id(f"rdgoal-report-{packet_id}"),
                    "run_id": _safe_id(str(packet_id)),
                    "ref_type": "report",
                    "ref_path": report_path,
                })
    for session in sessions:
        for ref in session.get("evidence_refs", []) if isinstance(session.get("evidence_refs"), list) else []:
            ref_text = str(ref or "")
            if ref_text:
                evidence.append({
                    "evidence_id": _safe_id(f"session-ref-{_safe_id(ref_text.rsplit('/', 1)[-1])}"),
                    "run_id": str(session.get("run_id") or ""),
                    "ref_type": "session_evidence",
                    "ref_path": ref_text,
                })
    for run in runs:
        report_path = str(run.get("report_path") or "")
        if report_path:
            evidence.append({
                "evidence_id": _safe_id(f"run-report-{run.get('run_id', '')}"),
                "run_id": _safe_id(str(run.get("run_id") or "")),
                "ref_type": "report",
                "ref_path": report_path,
            })
    return evidence


def _team_review_gates(
    gates: list[dict[str, Any]],
    go_runs: list[dict[str, Any]],
    next_actions: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = [
        {
            "gate_id": _safe_id(str(g.get("gate_id") or "")),
            "kind": str(g.get("kind") or "human"),
            "status": str(g.get("status") or "open"),
            "reason": str(g.get("reason") or ""),
            "run_id": _safe_id(str(g.get("run_id") or "")),
        }
        for g in gates
    ]
    for action in next_actions:
        if str(action.get("source_type") or "") != "go_run":
            continue
        go_run_id = _safe_id(str(action.get("source_id") or ""))
        action_id = _safe_id(str(action.get("action_id") or ""))
        if not go_run_id:
            continue
        entries.append({
            "gate_id": action_id,
            "kind": "action-gate",
            "status": str(action.get("status") or "ready"),
            "reason": str(action.get("label") or ""),
            "run_id": go_run_id,
        })
    existing_gate_ids = {e["gate_id"] for e in entries if isinstance(e, dict)}
    for run in go_runs:
        go_run_id = _safe_id(str(run.get("go_run_id") or ""))
        run_status = str(run.get("status") or "")
        if run_status not in ("passed", "failed", "blocked"):
            continue
        if not go_run_id:
            continue
        gate_id = _safe_id(f"{go_run_id}-outcome-gate")
        if gate_id in existing_gate_ids:
            continue
        if run_status == "passed":
            gate_status = "pass"
            reason = f"/go run {go_run_id} completed successfully."
        elif run_status == "failed":
            gate_status = "failed"
            reason = f"/go run {go_run_id} failed."
        else:
            gate_status = "blocked"
            reason = f"/go run {go_run_id} is blocked."
        entries.append({
            "gate_id": gate_id,
            "kind": "go-run-outcome",
            "status": gate_status,
            "reason": reason,
            "run_id": go_run_id,
        })
        existing_gate_ids.add(gate_id)
    return entries


def _team_conflict_control(
    go_runs: list[dict[str, Any]],
    dispatches: list[dict[str, Any]],
    paper_roots: list[Path],
) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for run in go_runs:
        go_run_id = _safe_id(str(run.get("go_run_id") or ""))
        for agent in run.get("agents", []):
            if not isinstance(agent, dict):
                continue
            for target in agent.get("targets", []) if isinstance(agent.get("targets"), list) else []:
                target_str = str(target or "")
                if target_str:
                    entries.append({
                        "file_path": target_str,
                        "owner_run_id": go_run_id,
                        "owner_agent_id": _safe_id(str(agent.get("agent_id") or "")),
                        "file_kind": "go-target",
                    })
    for dispatch in dispatches:
        packet_id = dispatch.get("packet_id") or _fallback_id(dispatch, "run")
        for target in dispatch.get("targets", []) if isinstance(dispatch.get("targets"), list) else []:
            target_str = str(target or "")
            if target_str:
                entries.append({
                    "file_path": target_str,
                    "owner_run_id": _safe_id(str(packet_id)),
                    "owner_agent_id": "executor",
                    "file_kind": "rdgoal-target",
                })
    return entries


def _rdgoal_session_state(dispatch: dict[str, Any], report: dict[str, Any] | None) -> dict[str, Any]:
    packet_id = dispatch.get("packet_id") or _fallback_id(dispatch, "run")
    packet_dir = str(dispatch.get("packet_dir") or "")
    changed_files = _visible_changed_files((report or {}).get("changed_files") or [])
    return {
        "session_id": _safe_id(f"{packet_id}-local-executor-session"),
        "provider": "local",
        "binding_id": "local-executor",
        "agent_id": "executor",
        "agent_role": "executor",
        "project_id": _safe_id(str(dispatch.get("project_id") or "unknown")),
        "run_id": _safe_id(packet_id),
        "task_spec_id": f"{Path(packet_dir).name}/TASKSPEC.json" if packet_dir else _safe_id(packet_id),
        "status": _session_status(_run_status(bool(dispatch.get("dispatch_ready")), (report or {}).get("status", ""))),
        "messages": [],
        "tool_calls": [],
        "changed_files": changed_files,
        "diff_summary": _diff_summary(changed_files),
        "evidence_refs": _existing_refs([
            (report or {}).get("report_path", ""),
            packet_dir,
        ]),
        "cost": {},
        "tokens": {},
        "gates": [_safe_id(f"{packet_id}-acceptance"), "human-gate"],
        "actions": ["human-gate-action"],
        "native_refs": {
            "runtime": "rdgoal",
            "packet_id": str(packet_id),
        },
    }


def _go_session_states(go_runs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    sessions: list[dict[str, Any]] = []
    for run in go_runs:
        for agent in run.get("agents", []):
            if not isinstance(agent, dict):
                continue
            provider = _worker_provider(agent.get("worker_command", []))
            agent_id = str(agent.get("agent_id") or "coding-agent")
            session_id = _safe_id(f"{run.get('go_run_id', 'go-run')}-{agent_id}-session")
            worker_status = str(agent.get("worker_status") or "")
            raw_status = worker_status if worker_status and worker_status != "unknown" else str(
                agent.get("status") or run.get("status") or "unknown"
            )
            status = _session_status(raw_status)
            changed_files = _visible_changed_files(agent.get("changed_files") or [])
            sessions.append({
                "session_id": session_id,
                "provider": provider,
                "binding_id": "local-executor",
                "agent_id": _safe_id(agent_id),
                "agent_role": "executor",
                "project_id": _safe_id(str(run.get("project_id") or "unknown")),
                "run_id": _safe_id(str(run.get("go_run_id") or "go-run")),
                "task_spec_id": Path(str(agent.get("task_spec_path") or "")).name if agent.get("task_spec_path") else "",
                "status": status,
                "messages": [],
                "tool_calls": [_command_tool_call(agent)] if agent.get("worker_command") else [],
                "changed_files": changed_files,
                "diff_summary": _diff_summary(changed_files),
                "evidence_refs": _existing_refs([
                    agent.get("report_path", ""),
                    agent.get("packet_dir", ""),
                    run.get("metadata_path", ""),
                ]),
                "cost": {},
                "tokens": {},
                "gates": [],
                "actions": [],
                "native_refs": {
                    "runtime": "devframe-code",
                    "go_run_id": str(run.get("go_run_id") or ""),
                },
            })
    return sessions


def _go_packet_dirs(go_runs: list[dict[str, Any]]) -> set[str]:
    return {
        str(agent.get("packet_dir") or "")
        for run in go_runs
        for agent in run.get("agents", [])
        if isinstance(agent, dict) and agent.get("packet_dir")
    }


def _web_ai_session_states(runtime_dir: str | Path) -> list[dict[str, Any]]:
    if not runtime_dir:
        return []
    sessions_dir = Path(runtime_dir) / "web-ai-sessions"
    if not sessions_dir.exists():
        return []
    sessions: list[dict[str, Any]] = []
    for path in sorted(sessions_dir.glob("*.json")):
        data = _read_json(path)
        if not data:
            continue
        provider = _safe_id(str(data.get("provider") or "web-ai"))
        agent_role = str(data.get("agent_role") or "custom")
        valid_roles = {"coordinator", "reviewer", "executor", "paper_reviewer", "human_reviewer", "custom"}
        if agent_role not in valid_roles:
            agent_role = "custom"
        raw_native_refs = data.get("native_refs") if isinstance(data.get("native_refs"), dict) else {}
        source_runtime = str(raw_native_refs.get("source_runtime") or "")
        runtime = str(raw_native_refs.get("runtime") or "")
        is_chatgpt_web_mcp = source_runtime == "chatgpt-web-mcp" or runtime == "chatgpt-web-mcp"
        is_mcp_live = source_runtime == "mcp-live-probe" or runtime == "mcp-live-probe"
        is_external_mcp = (source_runtime.endswith("-web-mcp") or runtime.endswith("-web-mcp")) and not is_chatgpt_web_mcp and not is_mcp_live
        if is_chatgpt_web_mcp:
            binding_id = _safe_id(f"{provider}-web-mcp")
        elif is_external_mcp:
            binding_id = _safe_id(f"{provider}-mcp-live")
        else:
            binding_id = _safe_id(f"{provider}-web")
        session: dict[str, Any] = {
            "session_id": _safe_id(str(data.get("session_id") or path.stem)),
            "provider": provider,
            "binding_id": binding_id,
            "agent_id": _safe_id(str(data.get("agent_id") or data.get("session_id") or path.stem)),
            "agent_role": agent_role,
            "project_id": _safe_id(str(data.get("project_id") or "unknown")),
            "run_id": _safe_id(str(data.get("run_id") or "")),
            "task_spec_id": str(data.get("task_spec_id") or ""),
            "status": _session_status(data.get("status") or "idle"),
            "messages": [_normalize_session_message(msg) for msg in data.get("messages", []) if isinstance(msg, dict)],
            "tool_calls": [_normalize_session_tool_call(tc) for tc in data.get("tool_calls", []) if isinstance(tc, dict)],
            "changed_files": [str(item) for item in data.get("changed_files", []) if str(item)],
            "diff_summary": str(data.get("diff_summary") or ""),
            "evidence_refs": [str(item) for item in data.get("evidence_refs", []) if str(item)],
            "cost": _normalize_cost(data.get("cost")),
            "tokens": _normalize_tokens(data.get("tokens")),
            "gates": [str(item) for item in data.get("gates", []) if str(item)],
            "actions": [str(item) for item in data.get("actions", []) if str(item)],
            "native_refs": _web_ai_native_refs(path, data.get("native_refs")),
        }
        sessions.append(session)
    return sessions


def _web_ai_provider_bindings(sessions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not sessions:
        return []
    default_bindings = _default_provider_bindings()
    existing_binding_ids = {
        _safe_id(str(binding.get("binding_id") or ""))
        for binding in default_bindings
    }
    bindings: list[dict[str, Any]] = []
    seen_binding_ids: set[str] = set()
    for session in sessions:
        native_refs = session.get("native_refs") if isinstance(session.get("native_refs"), dict) else {}
        source_runtime = str(native_refs.get("source_runtime") or "")
        runtime = str(native_refs.get("runtime") or "")
        is_chatgpt_web_mcp = source_runtime == "chatgpt-web-mcp" or runtime == "chatgpt-web-mcp"
        is_mcp_live = source_runtime == "mcp-live-probe" or runtime == "mcp-live-probe"
        is_external_mcp = (source_runtime.endswith("-web-mcp") or runtime.endswith("-web-mcp")) and not is_chatgpt_web_mcp and not is_mcp_live
        provider = _safe_id(str(session.get("provider") or "web-ai"))
        if is_chatgpt_web_mcp:
            binding_id = _safe_id(f"{provider}-web-mcp")
            mode = "mcp_web"
            notes = "Real ChatGPT Web MCP connector invocation; read-only summary."
        elif is_mcp_live:
            binding_id = _safe_id(f"{provider}-web")
            mode = "mcp_live"
            notes = "MCP live verified; read-only summary."
        elif is_external_mcp:
            binding_id = _safe_id(f"{provider}-mcp-live")
            mode = "mcp_live"
            notes = "MCP direct diagnostic; read-only summary."
        else:
            binding_id = _safe_id(f"{provider}-web")
            if binding_id in existing_binding_ids or binding_id in seen_binding_ids:
                continue
            mode = "context_only"
            notes = "Imported from web-ai-sessions; read-only summary."
        if binding_id in existing_binding_ids or binding_id in seen_binding_ids:
            continue
        seen_binding_ids.add(binding_id)
        bindings.append({
            "binding_id": binding_id,
            "provider": provider,
            "mode": mode,
            "health": "ready",
            "adapter_config_path": "",
            "manual_fallback_instructions": [],
            "notes": notes,
        })
    return bindings


def _web_ai_review_gate_states(sessions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    gates: list[dict[str, Any]] = []
    for session in sessions:
        native_refs = session.get("native_refs")
        if not _is_web_ai_import_native_refs(native_refs):
            continue
        marker = str(native_refs.get("review_marker") or "").strip()
        verdict = str(native_refs.get("review_verdict") or "").strip()
        if not marker or not verdict:
            continue
        session_id = _safe_id(str(session.get("session_id") or "web-ai-session"))
        gates.append({
            "gate_id": _safe_id(f"{session_id}-review-gate"),
            "kind": "acceptance",
            "status": _web_ai_review_gate_status(verdict),
            "reason": f"Web AI review {marker}: {verdict}",
            "next_action": _web_ai_review_next_action(session),
            "run_id": _safe_id(str(session.get("run_id") or session_id)),
        })
    return gates


def _web_ai_review_gate_status(verdict: str) -> str:
    normalized = _safe_id(verdict)
    tokens = set(normalized.split("-"))
    negative_phrases = (
        "do-not",
        "not-proceed",
        "not-approve",
        "not-approved",
        "not-accept",
        "not-accepted",
        "cannot-proceed",
        "should-not-proceed",
    )
    if any(phrase in normalized for phrase in negative_phrases):
        return "blocked"
    if tokens & {"fail", "failed", "stop", "blocked", "reject", "rejected", "deny", "denied"}:
        return "blocked"
    if tokens & {"pass", "passed", "proceed", "approve", "approved", "accept", "accepted"}:
        return "pass"
    return "open"


def _web_ai_review_next_action(session: dict[str, Any]) -> str:
    actions = session.get("actions")
    if isinstance(actions, list):
        for action in actions:
            text = str(action or "").strip()
            if text:
                return text
    return "Use the imported Web AI review to continue the local control-plane loop."


def _web_ai_agents(sessions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not sessions:
        return []
    default_bindings = _default_provider_bindings()
    web_bindings = _web_ai_provider_bindings(sessions)
    all_bindings = default_bindings + web_bindings
    bindings_by_provider = {
        _safe_id(str(binding.get("provider") or "")): _safe_id(str(binding.get("binding_id") or ""))
        for binding in all_bindings
    }
    agents: list[dict[str, Any]] = []
    seen_agent_ids: set[str] = set()
    for session in sessions:
        provider = _safe_id(str(session.get("provider") or "web-ai"))
        binding_id = _safe_id(str(session.get("binding_id") or bindings_by_provider.get(provider, _safe_id(f"{provider}-web"))))
        agent_id = _safe_id(str(session.get("agent_id") or session.get("session_id") or "web-ai-agent"))
        if agent_id in seen_agent_ids:
            continue
        seen_agent_ids.add(agent_id)
        native_refs = session.get("native_refs") if isinstance(session.get("native_refs"), dict) else {}
        source_runtime = str(native_refs.get("source_runtime") or "")
        runtime = str(native_refs.get("runtime") or "")
        is_chatgpt_web_mcp = source_runtime == "chatgpt-web-mcp" or runtime == "chatgpt-web-mcp"
        is_mcp_live = source_runtime == "mcp-live-probe" or runtime == "mcp-live-probe"
        is_external_mcp = (source_runtime.endswith("-web-mcp") or runtime.endswith("-web-mcp")) and not is_chatgpt_web_mcp and not is_mcp_live
        if is_chatgpt_web_mcp:
            permissions = ["read_context", "request_human_gate"]
        elif is_mcp_live or is_external_mcp:
            permissions = ["plan", "read_context", "request_human_gate"]
        else:
            permissions = ["read_context"]
        agents.append({
            "agent_id": agent_id,
            "binding_id": binding_id,
            "role": _agent_role_for_session(session.get("agent_role")),
            "scope": "project",
            "permissions": permissions,
            "status": _agent_status_from_session_status(session.get("status")),
        })
    return agents


def validate_web_ai_session_summary(data: dict[str, Any]) -> None:
    """Validate a web-ai session summary for import."""
    if not isinstance(data, dict):
        raise ValueError("session summary must be a JSON object")
    _validate_summary_only_fields(data)


def _validate_summary_only_fields(value: object, path: str = "$") -> None:
    forbidden_keys = {"raw_transcript", "transcript", "conversation", "raw_messages"}
    message_raw_keys = {"content", "text"}
    if isinstance(value, dict):
        for raw_key, child in value.items():
            key = str(raw_key)
            child_path = f"{path}.{key}"
            if key in forbidden_keys:
                raise ValueError(
                    f"raw transcript field '{key}' is not allowed in summary-only imports at {child_path}"
                )
            if ".messages[" in path and key in message_raw_keys:
                raise ValueError(
                    f"raw message field '{key}' is not allowed in summary-only imports at {child_path}; use content_summary"
                )
            _validate_summary_only_fields(child, child_path)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _validate_summary_only_fields(child, f"{path}[{index}]")


def _web_ai_native_refs(path: Path, value: object) -> dict[str, str]:
    refs = {"runtime": "web-ai-import", "source_file": path.name}
    if not isinstance(value, dict):
        return refs
    original_runtime = str(value.get("runtime") or "").strip()
    if original_runtime and not value.get("source_runtime"):
        refs["source_runtime"] = original_runtime
    for key, raw_value in value.items():
        text_key = str(key or "").strip()
        if not text_key or text_key == "runtime":
            continue
        if text_key in {"raw_transcript", "transcript", "conversation", "raw_messages"}:
            continue
        refs[text_key] = str(raw_value)
    return refs


def _is_web_ai_import_native_refs(value: object) -> bool:
    if not isinstance(value, dict):
        return False
    runtime = str(value.get("runtime") or "")
    source_runtime = str(value.get("source_runtime") or "")
    return runtime == "web-ai-import" or source_runtime == "mcp-live-probe" or source_runtime.endswith("-web-mcp")


def _agent_role_for_session(value: object) -> str:
    role = str(value or "").strip()
    if role in {"coordinator", "reviewer", "executor", "paper_reviewer", "human_reviewer"}:
        return role
    return "coordinator"


def _agent_status_from_session_status(value: object) -> str:
    status = _session_status(value)
    if status == "active":
        return "active"
    if status in {"blocked", "failed"}:
        return "blocked"
    if status == "needs_human":
        return "needs_human"
    return "idle"


def _normalize_session_message(message: dict[str, Any]) -> dict[str, Any]:
    role = str(message.get("role") or "unknown")
    if role not in {"system", "user", "assistant", "tool", "agent", "human", "unknown"}:
        role = "unknown"
    return {
        "message_id": _safe_id(str(message.get("message_id") or message.get("id") or "msg")),
        "role": role,
        "content_summary": str(message.get("content_summary") or ""),
        "created_at": str(message.get("created_at") or ""),
        "provider_message_id": str(message.get("provider_message_id") or message.get("id") or ""),
        "evidence_ref": str(message.get("evidence_ref") or ""),
    }


def _normalize_session_tool_call(tool_call: dict[str, Any]) -> dict[str, Any]:
    return {
        "tool_call_id": _safe_id(str(tool_call.get("tool_call_id") or tool_call.get("id") or "tool")),
        "name": str(tool_call.get("name") or ""),
        "status": _session_status(str(tool_call.get("status") or "unknown")),
        "command": str(tool_call.get("command") or ""),
        "evidence_ref": str(tool_call.get("evidence_ref") or ""),
    }


def _normalize_cost(value: object) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    amount = value.get("amount")
    currency = value.get("currency")
    try:
        normalized_amount = float(amount) if amount is not None else 0.0
    except (TypeError, ValueError):
        normalized_amount = 0.0
    return {
        "amount": max(0.0, normalized_amount),
        "currency": str(currency or ""),
    }


def _normalize_tokens(value: object) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    result: dict[str, Any] = {}
    for key in ("input", "output", "total"):
        val = value.get(key)
        try:
            normalized = int(val) if val is not None else 0
        except (TypeError, ValueError):
            normalized = 0
        result[key] = max(0, normalized)
    return result


def _paper_session_state(root: Path, binding: dict[str, Any]) -> dict[str, Any]:
    profile = _read_yaml(root / "PAPER_PROFILE.yaml")
    paper_id = _paper_id(root, profile)
    run_id = _safe_id(f"{paper_id}-paper-review")
    return {
        "session_id": _safe_id(f"{paper_id}-{binding.get('provider', 'web-ai')}-review-session"),
        "provider": str(binding.get("provider") or "web-ai"),
        "binding_id": str(binding.get("binding_id") or ""),
        "agent_id": _safe_id(f"paper-reviewer-{binding.get('binding_id', '')}"),
        "agent_role": "paper_reviewer",
        "project_id": paper_id,
        "run_id": run_id,
        "task_spec_id": str(root / "paper_task" / "PAPER_TASK_INPUT.yaml"),
        "status": _session_status(_paper_run_state(root).get("status", "pending")),
        "messages": [],
        "tool_calls": [],
        "changed_files": [],
        "diff_summary": "",
        "evidence_refs": _existing_refs([
            root / "review" / "REVIEW_REPORT.md",
            root / "closure" / "CLOSURE_REPORT.md",
            root / "evidence" / "ref-paper-review-pack.zip",
        ]),
        "cost": {},
        "tokens": {},
        "gates": [
            _safe_id(f"{paper_id}-privacy-gate"),
            _safe_id(f"{paper_id}-{binding.get('binding_id', 'provider')}-safety-gate"),
        ],
        "actions": [_safe_id(f"{run_id}-command-action")],
        "native_refs": {
            "runtime": "rdpaper",
            "adapter_config_path": str(root / "WEB_AI_ADAPTER.yaml"),
        },
    }


def _worker_provider(command: object) -> str:
    if not isinstance(command, list) or not command:
        return "local"
    executable = str(command[0]).replace("\\", "/").rsplit("/", 1)[-1].lower()
    if executable.endswith(".cmd"):
        executable = executable[:-4]
    if "." in executable:
        executable = executable.rsplit(".", 1)[0]
    if executable in {"opencode", "codex", "claude", "t3code"}:
        return executable
    return "custom"


def _command_tool_call(agent: dict[str, Any]) -> dict[str, Any]:
    command = [str(part) for part in agent.get("worker_command") or []]
    status = _session_status(str(agent.get("worker_status") or agent.get("status") or "unknown"))
    return {
        "tool_call_id": _safe_id(f"{agent.get('agent_id', 'agent')}-worker-command"),
        "name": "local-worker-command",
        "status": status,
        "command": " ".join(command),
        "evidence_ref": str(agent.get("report_path") or agent.get("packet_dir") or ""),
    }


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


def _diff_summary(changed_files: object) -> str:
    if not isinstance(changed_files, list) or not changed_files:
        return ""
    count = len(changed_files)
    if count == 1:
        return f"1 changed file: {changed_files[0]}"
    return f"{count} changed files"


def _visible_changed_files(changed_files: object) -> list[str]:
    if not isinstance(changed_files, list):
        return []
    files: list[str] = []
    for path in changed_files:
        label = _visible_file_label(path)
        if label and label.lower() not in {"(none)", "none", "(unknown)", "unknown"}:
            files.append(label)
    return files


def _visible_file_label(value: object) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    parts = text.split("`")
    if len(parts) >= 2 and _looks_like_path(parts[0]):
        return parts[0].lstrip("- ").strip()
    if len(parts) >= 3:
        return parts[1].strip()
    for separator in (" — ", " – ", " - ", " -- ", " -> ", " => "):
        if separator in text:
            return text.split(separator, 1)[0].strip()
    return text


def _looks_like_path(value: object) -> bool:
    text = str(value or "").strip()
    if not text:
        return False
    name = text.replace("\\", "/").rsplit("/", 1)[-1]
    return "/" in text.replace("\\", "/") or "." in name


def _existing_refs(values: list[object]) -> list[str]:
    refs: list[str] = []
    for value in values:
        text = str(value or "")
        if text:
            refs.append(text)
    return refs


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


def _go_run_states(runtime_dir: str | Path) -> list[dict[str, Any]]:
    if not runtime_dir:
        return []
    root = Path(runtime_dir)
    base = root / "go-runs"
    if not base.exists():
        return []
    runs: list[dict[str, Any]] = []
    for path in sorted(base.glob("*/go-run.json")):
        data = _read_json(path)
        if not data:
            continue
        agents = data.get("agents", [])
        go_run = {
            "go_run_id": _safe_id(data.get("go_run_id", path.parent.name)),
            "project_id": _safe_id(data.get("project_id", "")),
            "project_root": str(data.get("project_root", "")),
            "requirement": str(data.get("requirement", "")),
            "status": _go_status(data.get("status", "")),
            "execute": bool(data.get("execute", False)),
            "created_at": str(data.get("created_at", "")),
            "metadata_path": str(data.get("metadata_path") or path),
            "status_command": _go_run_status_command(path.parent.name, root),
            "execute_command": _go_run_execute_command(path.parent.name, root),
            "agents": [_go_agent_state(agent) for agent in agents if isinstance(agent, dict)],
        }
        methodology = _go_methodology_state(data.get("methodology"))
        if methodology is not None:
            go_run["methodology"] = methodology
        model_provider = str(data.get("model_provider", "")).strip()
        if model_provider:
            go_run["model_provider"] = model_provider
        runs.append(go_run)
    return runs


def _go_run_status_command(go_run_id: str, runtime_dir: str | Path) -> str:
    return f"devframe code status {_quote_arg(go_run_id)} --runtime-dir {_quote_arg(runtime_dir)}"


def _go_run_execute_command(go_run_id: str, runtime_dir: str | Path) -> str:
    return f"devframe code execute {_quote_arg(go_run_id)} --runtime-dir {_quote_arg(runtime_dir)}"


def _go_agent_state(agent: dict[str, Any]) -> dict[str, Any]:
    state = {
        "agent_id": _safe_id(agent.get("agent_id", "")),
        "shard_index": int(agent.get("shard_index") or 0),
        "shard_count": int(agent.get("shard_count") or 0),
        "status": _go_status(agent.get("status", "")),
        "worker_status": _go_worker_status(agent.get("worker_status", "")),
        "targets": [str(target) for target in agent.get("targets", []) if str(target)],
        "target_bytes": int(agent.get("target_bytes") or 0),
        "changed_files": [str(path) for path in agent.get("changed_files", []) if str(path)],
        "packet_dir": str(agent.get("packet_dir", "")),
        "task_spec_path": str(agent.get("task_spec_path", "")),
        "report_path": str(agent.get("report_path", "")),
        "worker_command": [str(part) for part in agent.get("worker_command", [])],
    }
    methodology = _go_methodology_state(agent.get("methodology"))
    if methodology is not None:
        state["methodology"] = methodology
    session_id = str(agent.get("session_id", ""))
    if session_id:
        state["session_id"] = session_id
    for key in ("input_tokens", "output_tokens", "total_tokens"):
        value = int(agent.get(key, 0) or 0)
        if value:
            state[key] = value
    cost = float(agent.get("cost", 0.0) or 0.0)
    if cost:
        state["cost"] = cost
    tool_calls = _go_tool_calls(agent.get("tool_calls"))
    if tool_calls:
        state["tool_calls"] = tool_calls
    model_provider = str(agent.get("model_provider", "")).strip()
    if model_provider:
        state["model_provider"] = model_provider
    # Surface only the boolean. The worktree path is a private local runtime
    # detail and must never enter the public read model (public-surface rule).
    if bool(agent.get("isolated", False)) and str(agent.get("worktree_path", "")).strip():
        state["isolated"] = True
    return state


def _go_tool_calls(value: object) -> list[dict[str, str]]:
    if not isinstance(value, list):
        return []
    calls: list[dict[str, str]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name", "")).strip()
        if not name:
            continue
        call = {"name": name}
        target = str(item.get("target", "")).strip()
        if target:
            call["target"] = target
        calls.append(call)
    return calls


def _go_status(value: object) -> str:
    normalized = _safe_id(str(value or "queued"))
    if normalized in {"queued", "running", "passed", "failed", "blocked", "review-pass", "review-fail", "verified"}:
        return normalized
    if normalized in {"pass", "completed"}:
        return "passed"
    return "queued"


def _go_worker_status(value: object) -> str:
    normalized = _safe_id(str(value or ""))
    if normalized in {"", "queued", "running", "passed", "failed", "blocked"}:
        return normalized
    if normalized in {"pass", "completed"}:
        return "passed"
    if normalized == "fail":
        return "failed"
    return normalized


def _go_methodology_state(value: object) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    skill_id = _safe_id(str(value.get("skill_id") or ""))
    if not skill_id:
        return None
    return {
        "skill_id": skill_id,
        "title": str(value.get("title") or skill_id),
        "source_path": str(value.get("source_path") or ""),
        "source_kind": str(value.get("source_kind") or "local_repository_asset"),
        "triggers": [str(trigger) for trigger in value.get("triggers", []) if str(trigger)],
        "status": str(value.get("status") or "registered"),
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


def _read_action_runs(runtime_dir: str) -> list[dict[str, Any]]:
    if not runtime_dir:
        return []
    root = Path(runtime_dir)
    base = root / "action-runs"
    if not base.exists():
        return []
    records: list[dict[str, Any]] = []
    for record_path in sorted(base.glob("*/*/action-run.json")):
        data = _read_json(record_path)
        if data:
            records.append(data)
    return records


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
    sessions: list[dict[str, Any]] | None = None,
    go_runs: list[dict[str, Any]] | None = None,
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
    actions.extend(_go_run_action_items(go_runs or []))
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
    actions.extend(_session_action_items(sessions or []))
    return sorted(actions, key=_action_sort_key)


def _go_run_action_items(go_runs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    for go_run in go_runs:
        go_run_id = str(go_run.get("go_run_id") or "")
        status = str(go_run.get("status") or "")
        if not go_run_id or status not in {"queued", "running", "blocked", "failed"}:
            continue
        status_command = str(go_run.get("status_command") or "")
        execute_command = str(go_run.get("execute_command") or "")
        blocked = status in {"blocked", "failed"}
        if status_command:
            actions.append({
                "action_id": _safe_id(f"{go_run_id}-status-action"),
                "source_type": "go_run",
                "source_id": go_run_id,
                "priority": "high" if blocked else "low",
                "status": "blocked" if blocked else "info",
                "label": "Inspect this DevFrame Code go-run.",
                "detail": status,
                "command": status_command,
            })
        if execute_command and status == "queued":
            actions.append({
                "action_id": _safe_id(f"{go_run_id}-execute-action"),
                "source_type": "go_run",
                "source_id": go_run_id,
                "priority": "medium",
                "status": "ready",
                "label": "Execute this go-run through DevFrame Code.",
                "detail": status,
                "command": execute_command,
            })
    return actions


def _session_action_items(sessions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    for session in sessions:
        native_refs = session.get("native_refs")
        if not _is_web_ai_import_native_refs(native_refs):
            continue
        session_id = str(session.get("session_id") or "")
        if not session_id:
            continue
        session_status = _session_status(session.get("status"))
        action_status = "open" if session_status in {"idle", "active", "needs_human"} else "info"
        priority = "medium" if session_status in {"active", "needs_human"} else "low"
        action_label = "Review imported web AI session action."
        if native_refs.get("outcome") == "task_intake_recorded":
            ref_priority = str(native_refs.get("priority") or "").strip()
            if ref_priority in ACTION_PRIORITIES:
                priority = ref_priority
            if native_refs.get("dispatch_go_run_id"):
                action_status = "info"
                priority = "low"
                action_label = "Web GPT task intake dispatched to local agents."
            else:
                action_status = "ready"
                action_label = "Execute Web GPT task intake through local agents."
        elif native_refs.get("tool_name") == "project_summary" and native_refs.get("outcome") == "completed":
            action_status = "open"
            priority = "medium"
            action_label = "Review imported project summary for next local handoff or task intake."
        for action in session.get("actions", []):
            action_text = str(action or "").strip()
            if not action_text:
                continue
            action_item = {
                "action_id": _safe_id(f"{session_id}-{action_text}"),
                "source_type": "session",
                "source_id": session_id,
                "priority": priority,
                "status": action_status,
                "label": action_label,
                "detail": action_text,
            }
            if native_refs.get("outcome") == "task_intake_recorded" and action_status == "ready":
                intake_id = str(native_refs.get("intake_id") or "").strip()
                if intake_id:
                    action_item["command"] = f"devframe web-ai dispatch-task-intakes --intake-id {intake_id}"
            actions.append(action_item)
    return actions


def _action_sort_key(action: dict[str, Any]) -> tuple[int, int, str]:
    priority_order = {"high": 0, "medium": 1, "low": 2}
    source_order = {"gate": 0, "go_run": 1, "run": 2, "decision": 3, "session": 4}
    return (
        priority_order.get(str(action.get("priority")), 3),
        source_order.get(str(action.get("source_type")), 3),
        str(action.get("action_id")),
    )


def _summary_band(state: dict[str, Any], lang: str = "en") -> str:
    projects = state.get("projects", [])
    sessions = state.get("sessions", [])
    runs = state.get("runs", [])
    gates = state.get("gates", [])
    decisions = state.get("decisions", [])
    metrics = [
        (dashboard_t("projects_section", lang), str(len(projects)), dashboard_t("registered_units", lang)),
        (dashboard_t("sessions", lang), str(len(sessions)), _count_by_status(sessions)),
        (dashboard_t("runs_section", lang), str(len(runs)), _count_by_status(runs)),
        (dashboard_t("gates", lang), str(len(gates)), _count_by_status(gates)),
        (dashboard_t("decisions", lang), str(len(decisions)), _count_by_status(decisions)),
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


def _workbench_section(state: dict[str, Any], action_links: bool = False, lang: str = "en") -> str:
    projects = state.get("projects", [])
    runs = state.get("runs", [])
    agents = state.get("agents", [])
    sessions = state.get("sessions", [])
    gates = state.get("gates", [])
    next_actions = state.get("next_actions", [])
    primary_project = _first_by_status(projects, ["active", "review_required", "initialized", "completed"])
    primary_run = _first_by_status(runs, ["running", "pending", "blocked", "completed"])
    primary_action = next_actions[0] if next_actions else None
    active_gates = [
        gate for gate in gates
        if str(gate.get("status", "")).lower() not in {"pass", "passed", "completed"}
    ]
    lanes = "\n".join([
        _workbench_project_lane(primary_project, primary_run, action_links, lang),
        _workbench_agent_lane(agents, lang),
        _workbench_session_lane(sessions, lang),
        _workbench_gate_lane(active_gates, primary_action, action_links, lang),
    ])
    return (
        '<section class="workbench">'
        '<div class="workbench-head">'
        f"<div><h2>{_h(dashboard_t('control_workbench', lang))}</h2>"
        f"<p>{_h(dashboard_t('workbench_intro', lang))}</p></div>"
        f"<span>{_h(str(len(next_actions)))} {_h(dashboard_t('action_queue', lang))}</span>"
        "</div>"
        f'<div class="workbench-grid">{lanes}</div>'
        "</section>"
    )


def _first_by_status(items: list[dict[str, Any]], statuses: list[str]) -> dict[str, Any] | None:
    status_rank = {status: index for index, status in enumerate(statuses)}
    if not items:
        return None
    return sorted(
        items,
        key=lambda item: (status_rank.get(str(item.get("status", "")).lower(), len(status_rank)), str(item)),
    )[0]


def _workbench_project_lane(
    project: dict[str, Any] | None,
    run: dict[str, Any] | None,
    action_links: bool,
    lang: str,
) -> str:
    if not project:
        project_body = f'<p class="empty">{_h(dashboard_t("no_project", lang))}</p>'
    else:
        project_body = (
            f'<strong class="workbench-title">{_h(project.get("display_name", ""))}</strong>'
            '<div class="workbench-badges">'
            f'{_badge(project.get("status", ""))}{_badge(project.get("risk_state", ""))}'
            '</div>'
            f'<p>{_h(project.get("goal", ""))}</p>'
            f'<code>{_h(project.get("project_id", ""))}</code>'
        )
    if not run:
        run_body = f'<p class="empty">{_h(dashboard_t("no_run", lang))}</p>'
    else:
        run_body = (
            '<div class="workbench-row">'
            f'<span>{_h(dashboard_t("active_run", lang))}</span>'
            f'<code>{_h(run.get("run_id", ""))}</code>'
            f'{_badge(run.get("status", ""))}'
            '</div>'
        )
    dispatch_link = ""
    if action_links:
        dispatch_href = "/go/dispatch" if lang != "zh-CN" else f"/go/dispatch?lang={lang}"
        dispatch_link = (
            '<div class="workbench-action">'
            '<span>/go</span>'
            f'<strong><a class="row-link" href="{_h(dispatch_href)}">Start dispatch</a></strong>'
            '<code>prepare or execute coding-agent shards</code>'
            '</div>'
        )
    return (
        '<article class="workbench-lane">'
        f'<h3>{_h(dashboard_t("active_project", lang))}</h3>'
        f'{project_body}{run_body}{dispatch_link}'
        '</article>'
    )


def _workbench_agent_lane(agents: list[dict[str, Any]], lang: str) -> str:
    if not agents:
        body = f'<p class="empty">{_h(dashboard_t("no_agents", lang))}</p>'
    else:
        body = '<ul class="workbench-list">' + "".join(
            '<li>'
            f'<span>{_h(agent.get("role", ""))}</span>'
            f'<code>{_h(agent.get("agent_id", ""))}</code>'
            f'{_badge(agent.get("status", ""))}'
            '</li>'
            for agent in agents[:5]
        ) + '</ul>'
    return (
        '<article class="workbench-lane">'
        f'<h3>{_h(dashboard_t("agent_registry", lang))}</h3>'
        f'{body}'
        '</article>'
    )


def _workbench_session_lane(sessions: list[dict[str, Any]], lang: str) -> str:
    if not sessions:
        body = f'<p class="empty">{_h(dashboard_t("no_sessions", lang))}</p>'
    else:
        body = '<ul class="workbench-list">' + "".join(
            '<li>'
            f'<span>{_h(session.get("provider", ""))} / {_h(session.get("agent_role", ""))}</span>'
            f'<code>{_h(session.get("session_id", ""))}</code>'
            f'{_badge(session.get("status", ""))}'
            '</li>'
            for session in sessions[:5]
        ) + '</ul>'
    return (
        '<article class="workbench-lane">'
        f'<h3>{_h(dashboard_t("session_stream", lang))}</h3>'
        f'{body}'
        '</article>'
    )


def _workbench_gate_lane(
    active_gates: list[dict[str, Any]],
    primary_action: dict[str, Any] | None,
    action_links: bool,
    lang: str,
) -> str:
    if active_gates:
        gate_lines = '<ul class="workbench-list">' + "".join(
            '<li>'
            f'<span>{_h(gate.get("kind", ""))}</span>'
            f'<code>{_h(gate.get("gate_id", ""))}</code>'
            f'{_badge(gate.get("status", ""))}'
            '</li>'
            for gate in active_gates[:4]
        ) + '</ul>'
    else:
        gate_lines = f'<p class="empty">{_h(dashboard_t("all_gates_clear", lang))}</p>'
    if not primary_action:
        action_html = ""
    else:
        action_id = str(primary_action.get("action_id") or "")
        link = _action_md_href(action_id, lang) if action_links and action_id else ""
        link_html = f'<a class="row-link" href="{_h(link)}">{_h(dashboard_t("markdown_link", lang))}</a>' if link else ""
        action_html = (
            '<div class="workbench-action">'
            f'<span>{_h(dashboard_t("primary_action", lang))}</span>'
            f'<strong>{_h(primary_action.get("label", ""))}</strong>'
            f'<code>{_h(_action_resume_filter(primary_action))}</code>'
            f'{link_html}'
            '</div>'
        )
    return (
        '<article class="workbench-lane">'
        f'<h3>{_h(dashboard_t("gate_state", lang))}</h3>'
        f'{gate_lines}{action_html}'
        '</article>'
    )


def _gate_focus_section(
    gates: list[dict[str, Any]],
    next_actions: list[dict[str, Any]],
    action_links: bool = False,
    lang: str = "en",
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
        rows = f'<p class="empty">{_h(dashboard_t("no_active_gates", lang))}</p>'
    else:
        rows = "\n".join(
            _gate_focus_card_html(
                gate,
                actions_by_gate.get(str(gate.get("gate_id") or "")),
                action_links,
                lang,
            )
            for gate in active_gates
        )
    return (
        '<section class="panel gate-focus">'
        f"<h2>{_h(dashboard_t('gate_focus', lang))}</h2>"
        f'<div class="gate-focus-grid">{rows}</div>'
        "</section>"
    )


def _gate_focus_card_html(
    gate: dict[str, Any],
    action: dict[str, Any] | None,
    action_links: bool,
    lang: str = "en",
) -> str:
    return (
        '<article class="gate-focus-card">'
        '<div class="gate-focus-head">'
        f"<code>{_h(gate.get('gate_id', ''))}</code>"
        f"{_badge(gate.get('status', ''))}"
        f"{_badge(gate.get('kind', ''))}"
        "</div>"
        f"<p>{_h(gate.get('reason', ''))}</p>"
        f"<p><strong>{_h(dashboard_t('next_action', lang))}</strong>{_h(gate.get('next_action', ''))}</p>"
        f"{_gate_focus_action_html(action, action_links, lang)}"
        "</article>"
    )


def _gate_focus_action_html(action: dict[str, Any] | None, action_links: bool, lang: str = "en") -> str:
    if not action:
        return ""
    action_id = str(action.get("action_id") or "")
    resume_filter = _action_resume_filter(action)
    parts = []
    if action_id:
        parts.append(f"<p><strong>{_h(dashboard_t('action_id', lang))}</strong><code>{_h(action_id)}</code></p>")
    if resume_filter:
        parts.append(
            f"<p><strong>{_h(dashboard_t('resume_filter_label', lang))}</strong><code>{_h(resume_filter)}</code></p>"
        )
    if action_links and action_id:
        href = _action_md_href(action_id, lang)
        parts.append(
            f'<p><strong>{_h(dashboard_t("handoff", lang))}</strong><a class="row-link" href="{_h(href)}">'
            f"{_h(dashboard_t('markdown_link', lang))}</a></p>"
        )
    return "".join(parts)


def _next_actions_section(next_actions: list[dict[str, Any]], action_links: bool = False, lang: str = "en") -> str:
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
        f"{_action_handoff_cell(action, action_links, lang)}"
        "</tr>"
        for action in next_actions
    )
    headers = [
        dashboard_t("priority", lang),
        dashboard_t("status", lang),
        dashboard_t("action", lang),
        dashboard_t("source", lang),
        dashboard_t("source_id", lang),
        dashboard_t("action_id", lang),
        dashboard_t("resume_filter", lang),
        dashboard_t("command", lang),
    ]
    if action_links:
        headers.append(dashboard_t("handoff", lang))
    return _table_section(
        dashboard_t("action_queue", lang),
        headers,
        rows,
    )


def _go_runs_section(go_runs: list[dict[str, Any]], action_links: bool = False, lang: str = "en", focus_go_run_id: str | None = None) -> str:
    if not go_runs:
        return ""
    cards = "\n".join(_go_run_card_html(run, action_links, lang, focus_go_run_id=focus_go_run_id) for run in go_runs)
    return (
        '<section class="panel" id="go-runs">'
        f"<h2>{_h(dashboard_t('go_coding_agents', lang))}</h2>"
        f'<div class="go-runs">{cards}</div>'
        "</section>"
    )


def _go_run_card_html(run: dict[str, Any], action_links: bool, lang: str = "en", focus_go_run_id: str | None = None) -> str:
    agents = run.get("agents", [])
    rows = "\n".join(_go_agent_row_html(agent, lang) for agent in agents)
    headers = [
        dashboard_t("agent", lang),
        dashboard_t("shard", lang),
        dashboard_t("status", lang),
        dashboard_t("targets", lang),
        dashboard_t("target_bytes", lang),
        dashboard_t("changed_files", lang),
        dashboard_t("packet", lang),
        dashboard_t("worker_command", lang),
    ]
    focused = str(run.get("go_run_id", "")) == focus_go_run_id
    methodology = run.get("methodology") if isinstance(run.get("methodology"), dict) else None
    methodology_html = ""
    if methodology:
        methodology_title = str(methodology.get("title") or methodology.get("skill_id") or "")
        methodology_html = f"<dt>{_h(dashboard_t('methodology', lang))}</dt><dd><code>{_h(methodology_title)}</code></dd>"
    return (
        f'<article class="go-run-card{" go-run-focused" if focused else ""}">'
        '<div class="go-run-head">'
        f"<div><strong>{_h(dashboard_t('go_run', lang))}</strong><code>{_h(run.get('go_run_id', ''))}</code></div>"
        f"{_status_badge(run.get('status', ''))}"
        f"{_status_badge('execute' if run.get('execute') else 'prepared')}"
        "</div>"
        f"<p>{_h(run.get('requirement', ''))}</p>"
        '<dl class="path-list">'
        f"<dt>{_h(dashboard_t('project', lang))}</dt><dd><code>{_h(run.get('project_id', ''))}</code></dd>"
        f"{methodology_html}"
        f"<dt>{_h(dashboard_t('metadata', lang))}</dt><dd><code>{_h(run.get('metadata_path', ''))}</code></dd>"
        "</dl>"
        f"{_go_run_command_list_html(run, action_links, lang)}"
        '<div class="table-wrap">'
        "<table>"
        f"<thead><tr>{''.join(f'<th>{_h(header)}</th>' for header in headers)}</tr></thead>"
        f"<tbody>{rows}</tbody>"
        "</table>"
        "</div>"
        "</article>"
    )


def _go_run_command_list_html(run: dict[str, Any], action_links: bool = False, lang: str = "en") -> str:
    status_link = ""
    execute_link = ""
    go_run_id = str(run.get("go_run_id", ""))
    status = str(run.get("status", ""))
    if action_links and go_run_id and status in {"queued", "running", "blocked", "failed"}:
        status_link = f' <a class="row-link" href="{_h(_action_open_href(f"{go_run_id}-status-action", lang))}">Open action</a>'
    if action_links and go_run_id and status == "queued":
        execute_link = f' <a class="row-link" href="{_h(_action_open_href(f"{go_run_id}-execute-action", lang))}">Open action</a>'
    return (
        '<dl class="command-list">'
        f"<dt>{_h(dashboard_t('go_status_command', lang))}</dt><dd><code>{_h(run.get('status_command', ''))}</code>{status_link}</dd>"
        f"<dt>{_h(dashboard_t('go_execute_command', lang))}</dt><dd><code>{_h(run.get('execute_command', ''))}</code>{execute_link}</dd>"
        "</dl>"
    )


def _go_agent_row_html(agent: dict[str, Any], lang: str = "en") -> str:
    shard = f"{agent.get('shard_index', 0)}/{agent.get('shard_count', 0)}"
    targets = agent.get("targets", [])
    target_html = "<br>".join(f"<code>{_h(target)}</code>" for target in targets) or _h(dashboard_t("missing", lang))
    changed_files = agent.get("changed_files", [])
    changed_html = "<br>".join(f"<code>{_h(path)}</code>" for path in changed_files) or _h(dashboard_t("missing", lang))
    worker_command = " ".join(str(part) for part in agent.get("worker_command", []))
    return (
        "<tr>"
        f"<td><code>{_h(agent.get('agent_id', ''))}</code></td>"
        f"<td>{_h(shard)}</td>"
        f"<td>{_status_badge(agent.get('status', ''))}{_status_badge(agent.get('worker_status', '')) if agent.get('worker_status') else ''}</td>"
        f"<td>{target_html}</td>"
        f"<td><code>{_h(str(agent.get('target_bytes', 0)))}</code></td>"
        f"<td>{changed_html}</td>"
        f"<td><code>{_h(agent.get('packet_dir', ''))}</code></td>"
        f"<td><code>{_h(worker_command)}</code></td>"
        "</tr>"
    )


def _action_handoff_cell(action: dict[str, Any], enabled: bool, lang: str = "en") -> str:
    if not enabled:
        return ""
    action_id = str(action.get("action_id") or "")
    if not action_id:
        return "<td></td>"
    href = _action_md_href(action_id, lang)
    return f'<td><a class="row-link" href="{_h(href)}">{_h(dashboard_t("markdown_link", lang))}</a></td>'


def _action_open_href(action_id: str, lang: str = "en") -> str:
    base = f"/actions/open?action_id={quote(action_id)}"
    return base if lang != "zh-CN" else f"{base}&lang={quote(lang)}"


def _provider_bindings_section(provider_bindings: list[dict[str, Any]], lang: str = "en") -> str:
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
        dashboard_t("provider_bindings", lang),
        [
            dashboard_t("binding", lang),
            dashboard_t("provider", lang),
            dashboard_t("mode", lang),
            dashboard_t("health", lang),
            dashboard_t("adapter_config", lang),
            dashboard_t("manual_fallback", lang),
            dashboard_t("notes", lang),
        ],
        rows,
    )


def _manual_fallback_html(binding: dict[str, Any]) -> str:
    instructions = binding.get("manual_fallback_instructions", [])
    if not isinstance(instructions, list) or not instructions:
        return ""
    return "<br>".join(_h(str(instruction)) for instruction in instructions)


def _projects_section(projects: list[dict[str, Any]], lang: str = "en") -> str:
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
    return _table_section(
        dashboard_t("projects_section", lang),
        [dashboard_t("name", lang), dashboard_t("id", lang), dashboard_t("status", lang), dashboard_t("risk", lang), dashboard_t("goal", lang)],
        rows,
    )


def _sessions_section(sessions: list[dict[str, Any]], lang: str = "en") -> str:
    rows = "\n".join(
        "<tr>"
        f"<td><code>{_h(session.get('session_id', ''))}</code></td>"
        f"<td>{_h(session.get('provider', ''))}</td>"
        f"<td><code>{_h(session.get('binding_id', ''))}</code></td>"
        f"<td>{_h(session.get('agent_role', ''))}</td>"
        f"<td>{_badge(session.get('status', ''))}</td>"
        f"<td><code>{_h(session.get('project_id', ''))}</code></td>"
        f"<td><code>{_h(session.get('run_id', ''))}</code></td>"
        f"<td><code>{_h(session.get('task_spec_id', ''))}</code></td>"
        f"<td>{_h(_session_count_label(session.get('messages', [])))}</td>"
        f"<td>{_h(_session_count_label(session.get('tool_calls', [])))}</td>"
        f"<td>{_h(_session_cost_label(session.get('cost', {})))}</td>"
        f"<td>{_h(_session_tokens_label(session.get('tokens', {})))}</td>"
        f"<td>{_h(session.get('diff_summary', ''))}</td>"
        "</tr>"
        for session in sessions
    )
    return _table_section(
        dashboard_t("sessions", lang),
        [
            dashboard_t("session", lang),
            dashboard_t("provider", lang),
            dashboard_t("binding", lang),
            dashboard_t("role", lang),
            dashboard_t("status", lang),
            dashboard_t("project", lang),
            dashboard_t("run", lang),
            dashboard_t("task_spec_id", lang),
            dashboard_t("messages", lang),
            dashboard_t("tool_calls", lang),
            dashboard_t("cost", lang),
            dashboard_t("tokens", lang),
            dashboard_t("diff_summary", lang),
        ],
        rows,
    )


def _session_count_label(value: object) -> str:
    if not isinstance(value, list):
        return "0"
    return str(len(value))


def _session_cost_label(value: object) -> str:
    if not isinstance(value, dict):
        return ""
    amount = value.get("amount")
    if amount is None:
        return ""
    currency = str(value.get("currency") or "").strip()
    return f"{amount} {currency}".strip()


def _session_tokens_label(value: object) -> str:
    if not isinstance(value, dict):
        return ""
    total = value.get("total")
    if total is not None:
        return str(total)
    input_tokens = value.get("input")
    output_tokens = value.get("output")
    if input_tokens is None and output_tokens is None:
        return ""
    return f"in {input_tokens or 0} / out {output_tokens or 0}"


def _runs_section(runs: list[dict[str, Any]], lang: str = "en") -> str:
    rows = "\n".join(
        "<tr>"
        f"<td><code>{_h(run.get('run_id', ''))}</code></td>"
        f"<td>{_h(run.get('entrypoint', ''))}</td>"
        f"<td>{_status_badge(run.get('status', ''))}</td>"
        f"<td>{_status_badge(run.get('taskspec_status', ''))}</td>"
        f"<td>{_status_badge(run.get('evidence_status', ''))}</td>"
        f"<td>{_status_badge(run.get('review_status', ''))}</td>"
        "</tr>"
        for run in runs
    )
    return _table_section(
        dashboard_t("runs_section", lang),
        [dashboard_t("run", lang), dashboard_t("entry", lang), dashboard_t("status", lang), dashboard_t("taskspec", lang), dashboard_t("evidence", lang), dashboard_t("review", lang)],
        rows,
    )


def _run_details_section(runs: list[dict[str, Any]], decisions: list[dict[str, Any]], lang: str = "en") -> str:
    if not runs:
        return _table_section(dashboard_t("run_details", lang), [dashboard_t("run", lang), dashboard_t("details", lang)], "")
    decisions_by_run = {
        str(decision.get("run_id") or ""): decision
        for decision in decisions
        if decision.get("run_id")
    }
    cards = "\n".join(
        '<article class="run-detail">'
        f"<h3>{_h(run.get('run_id', ''))}</h3>"
        f'{_run_lifecycle_strip(run, lang)}'
        '<dl class="path-list">'
        f"<dt>{_h(dashboard_t('taskspec', lang))}</dt><dd><code>{_h(run.get('taskspec_path', '')) or dashboard_t('missing', lang)}</code></dd>"
        f"<dt>{_h(dashboard_t('taskspec_json', lang))}</dt><dd><code>{_h(run.get('taskspec_json_path', '')) or dashboard_t('missing', lang)}</code></dd>"
        f"<dt>{_h(dashboard_t('task_input', lang))}</dt><dd><code>{_h(run.get('task_input_path', '')) or dashboard_t('missing', lang)}</code></dd>"
        f"<dt>{_h(dashboard_t('execution_report', lang))}</dt><dd><code>{_h(run.get('report_path', '')) or dashboard_t('missing', lang)}</code></dd>"
        f"<dt>{_h(dashboard_t('packet', lang))}</dt><dd><code>{_h(run.get('packet_path', '')) or dashboard_t('missing', lang)}</code></dd>"
        f"{_run_decision_details(decisions_by_run.get(str(run.get('run_id') or '')), lang)}"
        "</dl>"
        f"<p class=\"command\"><span>{_h(dashboard_t('next_command', lang))}</span><code>{_h(run.get('next_command', '')) or dashboard_t('resolve_gate', lang)}</code></p>"
        "</article>"
        for run in runs
    )
    return (
        '<section class="panel">'
        f"<h2>{_h(dashboard_t('run_details', lang))}</h2>"
        f'<div class="run-details">{cards}</div>'
        "</section>"
    )


def _run_lifecycle_strip(run: dict[str, Any], lang: str = "en") -> str:
    badges = [
        _labeled_status_badge(dashboard_t("status", lang), run.get("status", "")),
        _labeled_status_badge(dashboard_t("taskspec", lang), run.get("taskspec_status", "")),
        _labeled_status_badge(dashboard_t("evidence", lang), run.get("evidence_status", "")),
        _labeled_status_badge(dashboard_t("review", lang), run.get("review_status", "")),
    ]
    return f'<div class="chips status-strip">{"".join(badges)}</div>'


def _run_decision_details(decision: dict[str, Any] | None, lang: str = "en") -> str:
    if not decision:
        return (
            f"<dt>{_h(dashboard_t('current_decision', lang))}</dt><dd><code>{_h(dashboard_t('missing', lang))}</code></dd>"
            f"<dt>{_h(dashboard_t('decision_next_action', lang))}</dt><dd>{_h(dashboard_t('missing', lang))}</dd>"
        )
    mode = decision.get("mode", "")
    status = decision.get("status", "")
    label = " / ".join(part for part in [str(mode), str(status)] if part)
    return (
        f"<dt>{_h(dashboard_t('current_decision', lang))}</dt><dd><code>{_h(decision.get('decision_id', ''))}</code> "
        f"{_badge(label or 'unknown')}</dd>"
        f"<dt>{_h(dashboard_t('decision_next_action', lang))}</dt><dd>{_h(decision.get('next_action', '')) or dashboard_t('missing', lang)}</dd>"
    )


def _agents_section(
    agents: list[dict[str, Any]],
    provider_bindings: list[dict[str, Any]],
    lang: str = "en",
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
        dashboard_t("agents", lang),
        [
            dashboard_t("agent", lang),
            dashboard_t("role", lang),
            dashboard_t("scope", lang),
            dashboard_t("provider", lang),
            dashboard_t("binding", lang),
            dashboard_t("binding_health", lang),
            dashboard_t("status", lang),
        ],
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


def _gates_section(gates: list[dict[str, Any]], lang: str = "en") -> str:
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
    return _table_section(
        dashboard_t("gates", lang),
        [dashboard_t("gate", lang), dashboard_t("kind", lang), dashboard_t("status", lang), dashboard_t("reason", lang), dashboard_t("next_action", lang)],
        rows,
    )


def _decisions_section(decisions: list[dict[str, Any]], lang: str = "en") -> str:
    rows = "\n".join(
        "<tr>"
        f"<td><code>{_h(decision.get('decision_id', ''))}</code></td>"
        f"<td>{_h(decision.get('mode', ''))}</td>"
        f"<td>{_badge(decision.get('status', ''))}</td>"
        f"<td>{_h(decision.get('next_action', ''))}</td>"
        "</tr>"
        for decision in decisions
    )
    return _table_section(
        dashboard_t("decisions", lang),
        [dashboard_t("decision", lang), dashboard_t("mode", lang), dashboard_t("status", lang), dashboard_t("next_action", lang)],
        rows,
    )


def _safety_section(safety: dict[str, Any], lang: str = "en") -> str:
    required = safety.get("human_gate_required_for", [])
    chips = "\n".join(f'<span class="chip">{_h(item)}</span>' for item in required)
    return (
        '<section class="panel safety">'
        f"<h2>{_h(dashboard_t('safety_defaults', lang))}</h2>"
        '<div class="safety-grid">'
        f"<p><strong>{_h(dashboard_t('raw_transcripts_persisted', lang))}</strong><span>{_h(str(safety.get('raw_transcripts_persisted', '')))}</span></p>"
        f"<p><strong>{_h(dashboard_t('remote_execution_default', lang))}</strong><span>{_h(str(safety.get('remote_execution_default', '')))}</span></p>"
        "</div>"
        '<div class="chips">'
        f"{chips}"
        "</div>"
        "</section>"
    )


def _skills_section(skills: list[dict[str, Any]], lang: str = "en") -> str:
    if not skills:
        return ""
    rows = "\n".join(
        "<tr>"
        f"<td><code>{_h(skill.get('skill_id', ''))}</code></td>"
        f"<td>{_h(skill.get('title', ''))}</td>"
        f"<td><code>{_h(skill.get('source_path', ''))}</code></td>"
        f"<td>{_h(skill.get('source_kind', ''))}</td>"
        f"<td>{_h(', '.join(skill.get('triggers', []) or []))}</td>"
        f"<td>{_badge(skill.get('status', ''))}</td>"
        "</tr>"
        for skill in skills
    )
    return _table_section(
        dashboard_t("methodology_skills", lang),
        [
            dashboard_t("id", lang),
            dashboard_t("skill_name", lang),
            dashboard_t("source", lang),
            dashboard_t("kind", lang),
            dashboard_t("skill_triggers", lang),
            dashboard_t("status", lang),
        ],
        rows,
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


def _status_badge(value: str) -> str:
    raw = _safe_id(value)
    label = str(value or "")
    token = raw
    if raw in {"queued", "pending"}:
        label = "prepared"
        token = "prepared"
    elif raw in {"pass", "passed", "completed", "review-pass", "verified", "executed"}:
        label = "complete"
        token = "completed"
    elif raw in {"review-fail", "fail", "failed"}:
        label = "failed"
        token = "failed"
    elif raw == "collected":
        label = "collected"
        token = "completed"
    elif raw == "missing":
        label = "missing"
        token = "blocked"
    elif raw == "draft":
        label = "draft"
        token = "pending"
    elif raw == "ready":
        label = "ready"
        token = "ready"
    elif raw == "":
        label = "unknown"
        token = "pending"
    return f'<span class="badge badge-{_h(token)}">{_h(label)}</span>'


def _labeled_status_badge(prefix: str, value: str) -> str:
    raw = _safe_id(value)
    label = str(value or "")
    token = raw
    if raw in {"queued", "pending"}:
        label = "prepared"
        token = "prepared"
    elif raw in {"pass", "passed", "completed", "review-pass", "verified", "executed"}:
        label = "complete"
        token = "completed"
    elif raw in {"review-fail", "fail", "failed"}:
        label = "failed"
        token = "failed"
    elif raw == "collected":
        label = "collected"
        token = "completed"
    elif raw == "missing":
        label = "missing"
        token = "blocked"
    elif raw == "draft":
        label = "draft"
        token = "pending"
    elif raw == "ready":
        label = "ready"
        token = "ready"
    elif raw == "":
        label = "unknown"
        token = "pending"
    return f'<span class="badge badge-{_h(token)}">{_h(prefix)}: {_h(label)}</span>'


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
  --ink: #111827;
  --muted: #64748b;
  --paper: #f7f8fb;
  --panel: #ffffff;
  --line: #d9e1ea;
  --accent: #2563eb;
  --accent-strong: #1d4ed8;
  --accent-soft: #eaf2ff;
  --surface-soft: #f1f5f9;
  --warn: #b45309;
  --bad: #b91c1c;
  --good: #15803d;
  --shadow: 0 14px 36px rgba(15, 23, 42, 0.08);
}
* { box-sizing: border-box; }
html, body {
  max-width: 100%;
  overflow-x: hidden;
}
body {
  margin: 0;
  background:
    linear-gradient(135deg, rgba(37, 99, 235, 0.08), transparent 40%),
    repeating-linear-gradient(90deg, rgba(15, 23, 42, 0.035) 0, rgba(15, 23, 42, 0.035) 1px, transparent 1px, transparent 32px),
    var(--paper);
  color: var(--ink);
  font-family: "Aptos", "Segoe UI", sans-serif;
}
.shell {
  width: min(1180px, calc(100% - 32px));
  margin: 0 auto;
  padding: 24px 0 40px;
}
.masthead {
  min-height: 0;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 24px;
  border-bottom: 2px solid var(--ink);
  padding-bottom: 18px;
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
  margin-top: 12px;
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
  font-family: "Aptos", "Segoe UI", sans-serif;
  font-size: clamp(34px, 4vw, 56px);
  line-height: 1;
  letter-spacing: 0;
  font-weight: 850;
}
.lead {
  max-width: 720px;
  margin: 12px 0 0;
  color: var(--muted);
  font-size: 16px;
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
  background: var(--accent-soft);
}
.metrics {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 12px;
  margin: 16px 0;
}
.metric {
  min-height: 96px;
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: 8px;
  box-shadow: var(--shadow);
  padding: 16px;
}
.metric strong {
  display: block;
  font-size: 30px;
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
.workbench {
  margin: 22px 0;
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: 8px;
  box-shadow: var(--shadow);
  overflow: hidden;
}
.workbench-head {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  padding: 18px;
  border-bottom: 1px solid var(--line);
  background: linear-gradient(90deg, var(--panel), var(--accent-soft));
}
.workbench-head h2 {
  margin: 0;
  font-size: 22px;
}
.workbench-head p {
  margin: 6px 0 0;
  color: var(--muted);
}
.workbench-head > span {
  align-self: start;
  border: 1px solid var(--line);
  border-radius: 8px;
  padding: 8px 10px;
  color: var(--accent-strong);
  background: var(--panel);
  font-size: 12px;
  font-weight: 800;
  text-transform: uppercase;
  white-space: nowrap;
}
.workbench-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
}
.workbench-lane {
  min-height: 230px;
  padding: 16px;
  border-right: 1px solid var(--line);
}
.workbench-lane:last-child {
  border-right: 0;
}
.workbench-lane h3 {
  margin: 0 0 14px;
  color: var(--muted);
  font-size: 12px;
  letter-spacing: 0;
  text-transform: uppercase;
}
.workbench-title {
  display: block;
  margin-bottom: 8px;
  font-size: 18px;
}
.workbench-badges {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-bottom: 10px;
}
.workbench-lane p {
  margin: 10px 0;
  color: var(--muted);
  line-height: 1.45;
}
.workbench-row {
  display: grid;
  gap: 8px;
  margin-top: 14px;
  padding-top: 12px;
  border-top: 1px solid var(--line);
}
.workbench-row span,
.workbench-action span {
  color: var(--muted);
  font-size: 12px;
  font-weight: 800;
  text-transform: uppercase;
}
.workbench-list {
  display: grid;
  gap: 10px;
  margin: 0;
  padding: 0;
  list-style: none;
}
.workbench-list li {
  display: grid;
  gap: 5px;
  min-width: 0;
}
.workbench-list span {
  color: var(--muted);
  font-size: 12px;
  font-weight: 800;
  text-transform: uppercase;
}
.workbench-list code,
.workbench-lane code {
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}
.workbench-action {
  display: grid;
  gap: 8px;
  margin-top: 14px;
  padding-top: 12px;
  border-top: 1px solid var(--line);
}
.workbench-action strong {
  font-size: 15px;
}
.panel {
  margin-top: 16px;
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: 8px;
  box-shadow: var(--shadow);
  padding: 18px;
  min-width: 0;
  overflow-x: hidden;
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
  border-radius: 8px;
  padding: 14px;
  background: var(--surface-soft);
  min-width: 0;
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
.go-runs {
  display: grid;
  gap: 12px;
}
.go-run-card {
  border: 1px solid var(--line);
  border-radius: 8px;
  padding: 14px;
  background: var(--surface-soft);
  min-width: 0;
  overflow-x: hidden;
}
.go-run-focused {
  outline: 2px solid var(--accent);
  outline-offset: 2px;
}
.go-run-head {
  display: flex;
  flex-wrap: wrap;
  justify-content: space-between;
  gap: 10px;
}
.go-run-head strong,
.go-run-head code {
  display: block;
}
.go-run-card p {
  margin: 12px 0;
  color: var(--muted);
}
.run-detail {
  border: 1px solid var(--line);
  border-radius: 8px;
  padding: 14px;
  background: var(--surface-soft);
  min-width: 0;
  overflow-x: hidden;
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
.command-list {
  display: grid;
  grid-template-columns: 130px minmax(0, 1fr);
  gap: 8px 10px;
  margin: 12px 0 0;
  border-top: 1px solid var(--line);
  padding-top: 12px;
}
.command-list dt {
  color: var(--muted);
  font-size: 12px;
  font-weight: 800;
  text-transform: uppercase;
}
.command-list dd {
  margin: 0;
  min-width: 0;
}
.command-list code {
  white-space: pre-wrap;
  overflow-wrap: anywhere;
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
.table-wrap {
  display: block;
  width: 100%;
  max-width: 100%;
  min-width: 0;
  overflow-x: auto;
}
table {
  width: max-content;
  min-width: 100%;
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
.badge-open, .badge-pending, .badge-prepared, .badge-selected, .badge-medium, .badge-running, .badge-ready, .badge-draft { color: var(--warn); background: #f8ecdc; }
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
.status-strip {
  margin: 0 0 12px;
}
.lang-switch {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  margin-top: 12px;
  border: 1px solid var(--line);
  border-radius: 6px;
  background: rgba(255, 255, 255, 0.52);
  overflow: hidden;
}
.lang-switch span {
  padding: 7px 10px;
  color: var(--muted);
  font-size: 12px;
  font-weight: 800;
  text-transform: uppercase;
}
.lang-switch a {
  color: var(--accent);
  font-weight: 800;
  text-decoration: none;
  font-size: 14px;
  padding: 7px 10px;
}
.lang-switch a:hover,
.lang-switch a.active {
  color: var(--panel);
  background: var(--accent);
}
@media (max-width: 820px) {
  .masthead { display: block; }
  .stamp { margin-top: 18px; }
  .metrics { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .workbench-head { display: block; }
  .workbench-head > span { display: inline-block; margin-top: 12px; }
  .workbench-grid { grid-template-columns: 1fr; }
  .workbench-lane {
    min-height: 0;
    border-right: 0;
    border-bottom: 1px solid var(--line);
  }
  .workbench-lane:last-child { border-bottom: 0; }
  .safety-grid { grid-template-columns: 1fr; }
}
@media (max-width: 520px) {
  .shell { width: min(100% - 20px, 1180px); padding-top: 20px; }
  h1 { font-size: 42px; }
  .metrics { grid-template-columns: 1fr; }
  td, th { padding: 9px 8px; }
}
""".strip()
