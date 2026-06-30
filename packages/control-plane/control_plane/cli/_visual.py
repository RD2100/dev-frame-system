"""DevFrame read model commands: visual-state, actions, sessions, dashboard."""
from __future__ import annotations

import json
import sys
from pathlib import Path

from ._common import _is_loopback_host, _wants_help
from ._usage import DASHBOARD_USAGE


def cmd_visual_state() -> int:
    import argparse
    import yaml

    from ..visual_state import (
        build_visual_control_plane_state,
        render_visual_control_plane_state_html,
        render_visual_control_plane_state_json,
    )

    parser = argparse.ArgumentParser(prog="devframe visual-state")
    parser.add_argument("--runtime-dir", default=None, help="Local devframe runtime directory")
    parser.add_argument("--paper-project", action="append", default=[], help="Paper iteration project directory to include")
    parser.add_argument("--format", choices=["json", "yaml", "html"], default="json", help="Output format")
    parser.add_argument("--output", default=None, help="Write output to a file instead of stdout")
    args = parser.parse_args(sys.argv[2:])

    state = build_visual_control_plane_state(args.runtime_dir, paper_project_dirs=args.paper_project)
    if args.format == "yaml":
        rendered = yaml.safe_dump(state, sort_keys=False, allow_unicode=False)
    elif args.format == "html":
        rendered = render_visual_control_plane_state_html(state)
    else:
        rendered = render_visual_control_plane_state_json(state)
    if args.output:
        output_path = Path(args.output).resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(rendered, encoding="utf-8")
        print(f"Wrote {args.format} visual state to {output_path}")
    else:
        print(rendered, end="" if rendered.endswith("\n") else "\n")
    return 0


def cmd_actions() -> int:
    import argparse
    import json
    import yaml

    from ..visual_state import (
        ACTION_PRIORITIES,
        ACTION_SOURCE_TYPES,
        ACTION_STATUSES,
        action_filter_values,
        build_visual_control_plane_state,
        filter_action_queue,
        render_action_queue_markdown,
        render_action_queue_text,
    )

    parser = argparse.ArgumentParser(prog="devframe actions")
    parser.add_argument("--runtime-dir", default=None, help="Local devframe runtime directory")
    parser.add_argument("--paper-project", action="append", default=[], help="Paper iteration project directory to include")
    parser.add_argument("--format", choices=["text", "json", "yaml", "markdown"], default="text", help="Output format")
    parser.add_argument("--status", action="append", choices=ACTION_STATUSES, help="Only include actions with this status")
    parser.add_argument("--priority", action="append", choices=ACTION_PRIORITIES, help="Only include actions with this priority")
    parser.add_argument("--source-type", action="append", choices=ACTION_SOURCE_TYPES, help="Only include actions from this source type")
    parser.add_argument("--source-id", action="append", help="Only include actions with this source id")
    parser.add_argument("--action-id", action="append", help="Only include actions with this action id")
    parser.add_argument("--fail-on-match", action="store_true", help="Return non-zero when the filtered queue is not empty")
    parser.add_argument("--output", default=None, help="Write output to a file instead of stdout")
    args = parser.parse_args(sys.argv[2:])

    state = build_visual_control_plane_state(args.runtime_dir, paper_project_dirs=args.paper_project)
    next_actions = state.get("next_actions", [])
    invalid_filters = _invalid_dynamic_action_filters(next_actions, args.source_id, args.action_id)
    if invalid_filters:
        print(f"Invalid action filters: {invalid_filters}", file=sys.stderr)
        return 2
    actions = filter_action_queue(
        next_actions,
        statuses=args.status,
        priorities=args.priority,
        source_types=args.source_type,
        source_ids=args.source_id,
        action_ids=args.action_id,
    )
    payload = {"next_actions": actions}
    if args.format == "json":
        rendered = json.dumps(payload, indent=2, ensure_ascii=True)
    elif args.format == "yaml":
        rendered = yaml.safe_dump(payload, sort_keys=False, allow_unicode=False)
    elif args.format == "markdown":
        rendered = render_action_queue_markdown(payload["next_actions"])
    else:
        rendered = render_action_queue_text(payload["next_actions"])
    if args.output:
        output_path = Path(args.output).resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(rendered, encoding="utf-8")
        print(f"Wrote {args.format} action queue to {output_path}")
    else:
        print(rendered, end="" if rendered.endswith("\n") else "\n")
    if args.fail_on_match and actions:
        return 1
    return 0


def cmd_sessions() -> int:
    import argparse

    from ..backup_guard import default_runtime_dir
    from ..visual_state import (
        build_visual_control_plane_state,
        public_session_summaries,
    )

    parser = argparse.ArgumentParser(prog="devframe sessions")
    parser.add_argument("--runtime-dir", default=None, help="Local devframe runtime directory")
    parser.add_argument("--format", choices=["text", "json"], default="text", help="Output format")
    parser.add_argument("--output", default=None, help="Write output to a file instead of stdout")
    args = parser.parse_args(sys.argv[2:])

    runtime_dir = Path(args.runtime_dir).resolve() if args.runtime_dir else default_runtime_dir()
    state = build_visual_control_plane_state(runtime_dir)
    sessions = public_session_summaries(state.get("sessions", []))
    if args.format == "json":
        rendered = json.dumps({"sessions": sessions}, indent=2, ensure_ascii=False)
    else:
        lines = ["DevFrame sessions", "runtime_dir  : hidden; use --format json for machine-readable summaries", ""]
        if not sessions:
            lines.append("(no sessions)")
        for session in sessions:
            lines.append(
                f"- {session.get('session_id', '')} provider={session.get('provider', '')} "
                f"status={session.get('status', '')}"
            )
            agent_id = session.get("agent_id", "")
            if agent_id:
                lines.append(f"  agent_id    : {agent_id}")
            role = session.get("agent_role", "")
            if role:
                lines.append(f"  role        : {role}")
            task_spec = session.get("task_spec_id", "")
            if task_spec:
                lines.append(f"  task_spec   : {task_spec}")
            targets = session.get("targets") or []
            if targets:
                lines.append(f"  targets     : {', '.join(str(t) for t in targets)}")
            changed = session.get("changed_files") or []
            if changed:
                lines.append(f"  changed     : {', '.join(str(t) for t in changed)}")
        rendered = "\n".join(lines) + "\n"
    if args.output:
        output_path = Path(args.output).resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(rendered, encoding="utf-8")
        print(f"Wrote {args.format} sessions to {output_path}")
    else:
        print(rendered, end="" if rendered.endswith("\n") else "\n")
    return 0


def _invalid_dynamic_action_filters(
    actions: list[dict],
    source_ids: list[str] | None,
    action_ids: list[str] | None,
) -> dict[str, list[str]]:
    from ..visual_state import action_filter_values

    allowed = action_filter_values(actions)
    invalid: dict[str, list[str]] = {}
    _collect_unknown_filter_values(invalid, "source_id", source_ids or [], allowed["source_id"])
    _collect_unknown_filter_values(invalid, "action_id", action_ids or [], allowed["action_id"])
    return invalid


def _collect_unknown_filter_values(
    invalid: dict[str, list[str]],
    key: str,
    values: list[str],
    allowed: list[str],
) -> None:
    allowed_values = set(allowed)
    unknown = [value for value in values if value not in allowed_values]
    if unknown:
        invalid[key] = unknown


def cmd_dashboard() -> int:
    import argparse

    if len(sys.argv) < 3 or _wants_help(sys.argv[2:3]):
        print(DASHBOARD_USAGE)
        return 0
    if sys.argv[2] != "serve":
        print(f"Unknown dashboard subcommand: {sys.argv[2]}")
        print(DASHBOARD_USAGE)
        return 1

    from ..dashboard import serve_dashboard

    parser = argparse.ArgumentParser(prog="devframe dashboard serve")
    parser.add_argument("--runtime-dir", default=None, help="Local devframe runtime directory")
    parser.add_argument("--paper-project", action="append", default=[], help="Paper iteration project directory to include")
    parser.add_argument("--host", default="127.0.0.1", help="Bind host")
    parser.add_argument("--port", type=int, default=8765, help="Bind port")
    parser.add_argument("--refresh-seconds", type=int, default=5, help="Browser refresh interval; use 0 to disable")
    parser.add_argument("--allow-remote", action="store_true", help="Allow binding to a non-loopback host")
    args = parser.parse_args(sys.argv[3:])

    if not args.allow_remote and not _is_loopback_host(args.host):
        print("ERROR: dashboard exposes local runtime paths; use --allow-remote to bind outside loopback.")
        return 1

    serve_dashboard(
        runtime_dir=args.runtime_dir,
        host=args.host,
        port=args.port,
        refresh_seconds=args.refresh_seconds,
        paper_project_dirs=args.paper_project,
    )
    return 0
