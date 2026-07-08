"""DevFrame web-ai commands: import, bind, probe, live-check, MCP recorders."""
from __future__ import annotations

import json
import sys
from pathlib import Path


def _json_output(value: object) -> str:
    return json.dumps(value, indent=2, ensure_ascii=True, default=str)


def cmd_web_ai_import(*, prog: str = "devframe web-ai import") -> int:
    import argparse

    from ..backup_guard import default_runtime_dir
    from ..visual_state import validate_web_ai_session_summary

    parser = argparse.ArgumentParser(prog=prog)
    parser.add_argument("source", help="Path to a summary-only web AI session JSON file")
    parser.add_argument("--runtime-dir", default=None, help="Local devframe runtime directory")
    args = parser.parse_args(sys.argv[3:])

    source_path = Path(args.source).resolve()
    if not source_path.exists():
        print(f"ERROR: source JSON not found: {source_path}", file=sys.stderr)
        return 1

    try:
        data = _load_json_summary_file(source_path)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        print(f"ERROR: unable to read source JSON: {exc}", file=sys.stderr)
        return 1

    try:
        validate_web_ai_session_summary(data)
    except ValueError as exc:
        print(f"ERROR: invalid session summary: {exc}", file=sys.stderr)
        return 1

    runtime_dir = Path(args.runtime_dir).resolve() if args.runtime_dir else default_runtime_dir()
    sessions_dir = runtime_dir / "web-ai-sessions"
    sessions_dir.mkdir(parents=True, exist_ok=True)
    destination = sessions_dir / source_path.name
    destination.write_text(json.dumps(data, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    print(f"Imported web-ai session: {destination}")
    return 0


def cmd_web_ai_bind_chrome(*, prog: str = "devframe web-ai bind-chrome") -> int:
    import argparse

    from ..backup_guard import default_runtime_dir
    from ..chrome_binding_probe import (
        ChromeBindingError,
        build_chrome_chatgpt_session_summary,
        render_chrome_binding_text,
    )
    from ..visual_state import validate_web_ai_session_summary

    parser = argparse.ArgumentParser(prog=prog)
    parser.add_argument("--runtime-dir", default=None, help="Local devframe runtime directory")
    parser.add_argument("--project", default="dev-frame-system", help="DevFrame project id")
    parser.add_argument("--cdp-endpoint", default="http://127.0.0.1:9222", help="Loopback Chrome CDP endpoint")
    parser.add_argument("--output-name", default="chatgpt-chrome-binding.json", help="Runtime session JSON file name")
    parser.add_argument("--dry-run", action="store_true", help="Print the summary without writing runtime state")
    parser.add_argument("--format", choices=["text", "json"], default="text", help="Output format")
    args = parser.parse_args(sys.argv[3:])

    try:
        summary = build_chrome_chatgpt_session_summary(
            project_id=args.project,
            cdp_endpoint=args.cdp_endpoint,
        )
        validate_web_ai_session_summary(summary)
    except (ChromeBindingError, OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"ERROR: unable to bind Chrome web AI session: {exc}", file=sys.stderr)
        return 2

    if args.format == "json":
        print(json.dumps(summary, indent=2, ensure_ascii=True))
    else:
        print(render_chrome_binding_text(summary), end="")

    if args.dry_run:
        return 0

    runtime_dir = Path(args.runtime_dir).resolve() if args.runtime_dir else default_runtime_dir()
    sessions_dir = runtime_dir / "web-ai-sessions"
    sessions_dir.mkdir(parents=True, exist_ok=True)
    output_name = Path(str(args.output_name)).name or "chatgpt-chrome-binding.json"
    destination = sessions_dir / output_name
    destination.write_text(json.dumps(summary, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    print(f"Imported Chrome web AI session: {destination}")
    return 0


def cmd_web_ai_bind_conversation(*, prog: str = "devframe web-ai bind-conversation") -> int:
    import argparse

    from ..backup_guard import default_runtime_dir
    from ..chrome_binding_probe import (
        ChromeBindingError,
        build_chatgpt_conversation_session_summary,
        render_chrome_binding_text,
    )
    from ..conversation_binding import write_conversation_binding
    from ..visual_state import validate_web_ai_session_summary

    parser = argparse.ArgumentParser(prog=prog)
    parser.add_argument("--conversation", required=True, help="ChatGPT conversation URL")
    parser.add_argument("--runtime-dir", default=None, help="Local devframe runtime directory")
    parser.add_argument("--project", default="dev-frame-system", help="DevFrame project id")
    parser.add_argument("--project-root", default=None, help="Project root directory (default: cwd)")
    parser.add_argument("--binding-root", default=None, help="User-level binding root (default: ~/.agents/bindings)")
    parser.add_argument("--output-name", default=None, help="Runtime session JSON file name")
    parser.add_argument("--format", choices=["text", "json"], default="text", help="Output format")
    args = parser.parse_args(sys.argv[3:])

    project_root = Path(args.project_root).resolve() if args.project_root else Path.cwd().resolve()

    try:
        summary = build_chatgpt_conversation_session_summary(
            project_id=args.project,
            conversation_url=args.conversation,
        )
        validate_web_ai_session_summary(summary)
        binding = write_conversation_binding(
            project_id=args.project,
            project_root=project_root,
            chat_url=summary["native_refs"]["conversation_url"],
            binding_root=args.binding_root,
        )
    except (ChromeBindingError, ValueError) as exc:
        print(f"ERROR: unable to bind ChatGPT conversation: {exc}", file=sys.stderr)
        return 2

    runtime_dir = Path(args.runtime_dir).resolve() if args.runtime_dir else default_runtime_dir()
    sessions_dir = runtime_dir / "web-ai-sessions"
    sessions_dir.mkdir(parents=True, exist_ok=True)
    output_name = Path(str(args.output_name or f"{summary['session_id']}.json")).name
    destination = sessions_dir / output_name
    destination.write_text(json.dumps(summary, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")

    result = {
        "session_path": str(destination),
        "registry_path": binding["registry_path"],
        "binding_path": binding["binding_path"],
        "session": summary,
        "binding": binding,
    }
    if args.format == "json":
        print(_json_output(result))
    else:
        print(render_chrome_binding_text(summary), end="")
        print(f"Imported ChatGPT conversation session: {destination}")
        print(f"Binding registry: {binding['registry_path']}")
        print(f"Binding file    : {binding['binding_path']}")
    return 0


def cmd_web_ai_ensure_browser(*, prog: str = "devframe web-ai ensure-browser") -> int:
    import argparse

    from ..backup_guard import default_runtime_dir
    from ..web_ai_browser_launcher import (
        BrowserLaunchError,
        ensure_web_ai_browser,
        render_browser_launch_text,
    )

    parser = argparse.ArgumentParser(prog=prog)
    parser.add_argument("--runtime-dir", default=None, help="Local devframe runtime directory")
    parser.add_argument("--config", default=None, help="Local browser launcher config JSON")
    parser.add_argument("--browser-exe", default=None, help="Browser executable path")
    parser.add_argument("--profile-dir", default=None, help="Dedicated persistent browser profile directory")
    parser.add_argument("--cdp-endpoint", default=None, help="Loopback CDP endpoint")
    parser.add_argument("--url", default=None, help="Web AI URL to open")
    parser.add_argument("--no-open", action="store_true", help="Ensure CDP only; do not open a URL")
    parser.add_argument("--write-config", action="store_true", help="Write the resolved local browser config")
    parser.add_argument("--format", choices=["text", "json"], default="text", help="Output format")
    args = parser.parse_args(sys.argv[3:])

    runtime_dir = Path(args.runtime_dir).resolve() if args.runtime_dir else default_runtime_dir()
    try:
        result = ensure_web_ai_browser(
            runtime_dir=runtime_dir,
            config_path=args.config,
            browser_exe=args.browser_exe,
            cdp_endpoint=args.cdp_endpoint,
            profile_dir=args.profile_dir,
            url=args.url,
            open_url=not args.no_open,
            write_config=args.write_config,
        )
    except (BrowserLaunchError, ValueError) as exc:
        print(f"ERROR: unable to ensure Web AI browser: {exc}", file=sys.stderr)
        return 2

    if args.format == "json":
        print(_json_output(result))
    else:
        print(render_browser_launch_text(result), end="")
    return 0 if result["status"] in {"already_running", "started"} else 1


def cmd_web_ai_submit_review(*, prog: str = "devframe web-ai submit-review") -> int:
    import argparse

    from ..backup_guard import default_runtime_dir
    from ..playwright_bridge import BridgeConfig, BridgeMode, health_check as bridge_health, submit_via_bridge, _read_prompt_text
    from ..submission_result import SubmissionRequest

    parser = argparse.ArgumentParser(prog=prog)
    parser.add_argument("--zip", dest="zip_path", required=True, help="ZIP or markdown file to upload")
    parser.add_argument("--prompt-file", dest="prompt_file", default=None, help="Prompt text file (UTF-8/UTF-8-SIG or UTF-16 BOM)")
    parser.add_argument("--conversation", dest="conversation_id", default=None, help="Target conversation URL or ID")
    parser.add_argument("--cdp-endpoint", default="http://127.0.0.1:9222", help="Chrome CDP endpoint")
    parser.add_argument("--execute", dest="execute", action="store_true", default=False, help="Execute live CDP transfer")
    args = parser.parse_args(sys.argv[3:])

    prompt_text = ""
    if args.prompt_file:
        try:
            prompt_text = _read_prompt_text(args.prompt_file)
        except OSError as exc:
            print(f"ERROR: unable to read --prompt-file: {exc}", file=sys.stderr)
            return 2

    mode = BridgeMode.LIVE if args.execute else BridgeMode.DRY_RUN
    cdp_host = "localhost"
    cdp_port = 9222
    if args.cdp_endpoint.startswith("http://"):
        try:
            rest = args.cdp_endpoint.split("://", 1)[1]
            host_port = rest.split("/", 1)[0]
            if ":" in host_port:
                cdp_host, port_str = host_port.split(":", 1)
                cdp_port = int(port_str)
            else:
                cdp_host = host_port
        except (ValueError, IndexError):
            pass

    config = BridgeConfig(
        mode=mode,
        safety_flag=args.execute,
        conversation_id=args.conversation_id or "",
        cdp_host=cdp_host,
        cdp_port=cdp_port,
    )

    if mode == BridgeMode.LIVE:
        ok, reason = bridge_health(config)
        if not ok:
            print(f"ERROR: Health check failed: {reason}")
            return 1

    req = SubmissionRequest(zip_path=args.zip_path, prompt_text=prompt_text, conversation_id=args.conversation_id or "")
    result = submit_via_bridge(req, config)
    print(f"Submission result: success={result.success}, mode={result.mode}")
    print(f"Detail: {result.detail}")
    return 0 if result.success else 1


def cmd_web_ai_prepare_review_bundle(*, prog: str = "devframe web-ai prepare-review-bundle") -> int:
    import argparse

    from ..external_review_bundle import (
        ReviewBundleError,
        prepare_external_review_bundle,
    )

    parser = argparse.ArgumentParser(prog=prog)
    parser.add_argument("--project-root", default=None, help="Project root directory (default: cwd)")
    parser.add_argument("--runtime-dir", default=None, help="Local devframe runtime directory")
    parser.add_argument("--question", required=True, help="External reviewer question")
    parser.add_argument("--source", action="append", default=[], help="Explicit source as role=path; repeatable")
    parser.add_argument("--required-role", action="append", default=[], help="Role that must be present for ready_for_review")
    parser.add_argument("--profile", default="external_review", help="Context profile label")
    parser.add_argument("--output-id", default=None, help="Stable output id for the bundle directory")
    args = parser.parse_args(sys.argv[3:])

    try:
        sources = [_parse_review_source(item) for item in args.source]
        result = prepare_external_review_bundle(
            project_root=Path(args.project_root).resolve() if args.project_root else Path.cwd(),
            runtime_dir=args.runtime_dir,
            review_question=args.question,
            sources=sources,
            required_roles=args.required_role,
            profile=args.profile,
            output_id=args.output_id,
        )
    except ReviewBundleError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    print(f"Prepared external review bundle: {result['status']}")
    print(f"  zip      : {result['zip_path']}")
    print(f"  manifest : {result['manifest_path']}")
    if result.get("blocking_issues"):
        print("  issues   :")
        for issue in result["blocking_issues"]:
            print(f"    - {issue}")
    return 0 if result["status"] == "ready_for_review" else 1


def cmd_web_ai_validate_review_bundle(*, prog: str = "devframe web-ai validate-review-bundle") -> int:
    import argparse

    from ..external_review_bundle import validate_external_review_bundle

    parser = argparse.ArgumentParser(prog=prog)
    parser.add_argument("--zip", dest="zip_path", required=True, help="External review bundle ZIP")
    args = parser.parse_args(sys.argv[3:])

    result = validate_external_review_bundle(args.zip_path)
    print(_json_output(result))
    return 0 if result.get("valid") else 1


def cmd_web_ai_record_mcp_result(*, prog: str = "devframe web-ai record-mcp-result") -> int:
    import argparse

    from ..backup_guard import default_runtime_dir
    from ..web_ai_mcp_recorder import record_mcp_result

    parser = argparse.ArgumentParser(prog=prog)
    parser.add_argument("--conversation", required=True, help="ChatGPT conversation URL (no credentials, query, or fragment)")
    parser.add_argument("--tool-name", required=True, help="Observed MCP tool name")
    parser.add_argument("--status", required=True, choices=["completed", "blocked", "failed", "web_host_completed", "web_host_no_result", "local_mcp_completed"], help="Observed tool call status")
    parser.add_argument("--provider", default="chatgpt", help="Provider id (default: chatgpt)")
    parser.add_argument("--project", default="dev-frame-system", help="DevFrame project id (default: dev-frame-system)")
    parser.add_argument("--connector-name", default=None, help="Optional connector name")
    parser.add_argument("--connector-app-id", default=None, help="Optional connector app id")
    parser.add_argument("--marker", default=None, help="Optional marker text")
    parser.add_argument("--result", required=True, help="Result or block summary")
    parser.add_argument("--output-id", default=None, help="Optional output id")
    parser.add_argument("--output-name", default=None, help="Optional output name")
    parser.add_argument("--runtime-dir", default=None, help="Local devframe runtime directory")
    parser.add_argument("--origin", default=None, choices=["web_host", "local_mcp"], help="MCP result origin (default: derived from --status)")
    parser.add_argument("--outcome", default=None, choices=["completed", "blocked", "failed", "no_result"], help="Observed tool outcome (default: derived from --status)")
    args = parser.parse_args(sys.argv[3:])

    try:
        result = record_mcp_result(
            runtime_dir=args.runtime_dir,
            provider=args.provider,
            project=args.project,
            conversation_url=args.conversation,
            connector_name=args.connector_name,
            connector_app_id=args.connector_app_id,
            tool_name=args.tool_name,
            status=args.status,
            origin=args.origin,
            outcome=args.outcome,
            marker=args.marker,
            result_summary=args.result,
            output_id=args.output_id,
            output_name=args.output_name,
        )
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    print(f"Recorded MCP result: {result['session_id']}")
    print(f"  session   : {result['session_path']}")
    print(f"  evidence  : {result['evidence_path']}")
    print(f"  status    : {result['status']}")
    return 0


def cmd_web_ai_record_task_intake(*, prog: str = "devframe web-ai record-task-intake") -> int:
    import argparse

    from ..backup_guard import default_runtime_dir
    from ..web_ai_mcp_recorder import record_task_intake

    parser = argparse.ArgumentParser(prog=prog)
    parser.add_argument("--conversation", required=True, help="ChatGPT conversation URL (no credentials, query, or fragment)")
    parser.add_argument("--task-title", required=True, help="Short task title for the intake")
    parser.add_argument("--task-summary", required=True, help="Full task summary or intent description")
    parser.add_argument("--provider", default="chatgpt", help="Provider id (default: chatgpt)")
    parser.add_argument("--project", default="dev-frame-system", help="DevFrame project id (default: dev-frame-system)")
    parser.add_argument("--connector-name", default=None, help="Optional connector name")
    parser.add_argument("--connector-app-id", default=None, help="Optional connector app id")
    parser.add_argument("--priority", default="medium", choices=["high", "medium", "low"], help="Task priority (default: medium)")
    parser.add_argument("--suggested-agent", default="opencode", choices=["opencode", "codex", "custom"], help="Suggested local agent (default: opencode)")
    parser.add_argument("--marker", default=None, help="Optional marker text")
    parser.add_argument("--runtime-dir", default=None, help="Local devframe runtime directory")
    args = parser.parse_args(sys.argv[3:])

    try:
        result = record_task_intake(
            runtime_dir=args.runtime_dir,
            provider=args.provider,
            project=args.project,
            conversation_url=args.conversation,
            connector_name=args.connector_name,
            connector_app_id=args.connector_app_id,
            task_title=args.task_title,
            task_summary=args.task_summary,
            priority=args.priority,
            suggested_agent=args.suggested_agent,
            marker=args.marker,
        )
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    print(f"Recorded task intake: {result['session_id']}")
    print(f"  session   : {result['session_path']}")
    print(f"  evidence  : {result['evidence_path']}")
    print(f"  status    : {result['status']}")
    return 0


def cmd_web_ai_import_task_intakes(*, prog: str = "devframe web-ai import-task-intakes") -> int:
    import argparse

    from ..backup_guard import default_runtime_dir
    from ..web_ai_mcp_recorder import import_task_intakes

    parser = argparse.ArgumentParser(prog=prog)
    parser.add_argument("--project-root", default=None, help="Project root directory (default: cwd)")
    parser.add_argument("--runtime-dir", default=None, help="Local devframe runtime directory")
    parser.add_argument("--provider", default="chatgpt", help="Provider id (default: chatgpt)")
    parser.add_argument("--project", default="dev-frame-system", help="DevFrame project id (default: dev-frame-system)")
    parser.add_argument("--connector-name", default=None, help="Optional connector name")
    parser.add_argument("--connector-app-id", default=None, help="Optional connector app id")
    args = parser.parse_args(sys.argv[3:])

    project_root = Path(args.project_root).resolve() if args.project_root else Path.cwd()
    runtime_dir = args.runtime_dir

    result = import_task_intakes(
        project_root=project_root,
        runtime_dir=runtime_dir,
        provider=args.provider,
        project=args.project,
        connector_name=args.connector_name,
        connector_app_id=args.connector_app_id,
    )

    imported = result["imported"]
    skipped = result["skipped"]
    print(f"Imported {len(imported)} task intake(s), skipped {len(skipped)}")
    for entry in imported:
        print(f"  imported: {entry['title']}")
        print(f"    session  : {entry['session_path']}")
        print(f"    intake   : {entry['intake_path']}")
    for entry in skipped:
        print(f"  skipped : {entry['path']}")
        print(f"    reason : {entry['reason']}")

    if len(imported) == 0 and len(skipped) == 0:
        intake_dir = project_root / ".ai-bridge" / "task-intakes"
        print(f"No intake files found in: {intake_dir}")
    return 0


def cmd_web_ai_dispatch_task_intakes(*, prog: str = "devframe web-ai dispatch-task-intakes") -> int:
    import argparse

    from ..go_dispatch import DEFAULT_OPENCODE_AGENT
    from ..web_ai_mcp_recorder import dispatch_task_intakes

    parser = argparse.ArgumentParser(prog=prog)
    parser.add_argument("--project-root", default=None, help="Project root directory (default: cwd)")
    parser.add_argument("--runtime-dir", default=None, help="Local devframe runtime directory")
    parser.add_argument("--provider", default="codexpro", help="Provider id (default: codexpro)")
    parser.add_argument("--project", default="dev-frame-system", help="DevFrame project id (default: dev-frame-system)")
    parser.add_argument("--connector-name", default=None, help="Optional connector name")
    parser.add_argument("--connector-app-id", default=None, help="Optional connector app id")
    parser.add_argument("--intake-id", default=None, help="Only dispatch this task intake id")
    parser.add_argument("--agents", type=int, default=1, help="Number of @go coding agents per intake")
    parser.add_argument("--limit", type=int, default=None, help="Maximum number of undispatched intakes to dispatch")
    parser.add_argument("--execute", action="store_true", help="Execute OpenCode workers after preparing @go packets")
    parser.add_argument("--model", default=None, help="Model id for the OpenCode worker")
    parser.add_argument("--opencode-agent", default=DEFAULT_OPENCODE_AGENT, help="OpenCode agent name")
    parser.add_argument("--timeout", type=int, default=900, help="Worker timeout when --execute is used")
    args = parser.parse_args(sys.argv[3:])

    project_root = Path(args.project_root).resolve() if args.project_root else Path.cwd()
    result = dispatch_task_intakes(
        project_root=project_root,
        runtime_dir=args.runtime_dir,
        provider=args.provider,
        project=args.project,
        connector_name=args.connector_name,
        connector_app_id=args.connector_app_id,
        agents=args.agents,
        execute=args.execute,
        limit=args.limit,
        intake_id=args.intake_id,
        model=args.model,
        opencode_agent=args.opencode_agent,
        timeout_seconds=args.timeout,
    )

    imported = result["imported"]
    dispatched = result["dispatched"]
    skipped = result["skipped"]
    print(f"Imported {len(imported)} task intake(s), dispatched {len(dispatched)}, skipped {len(skipped)}")
    for entry in dispatched:
        print(f"  dispatched: {entry['title']}")
        print(f"    intake   : {entry['intake_id']}")
        print(f"    go_run   : {entry['go_run_id']}")
        print(f"    status   : {entry['status']}")
        print(f"    metadata : {entry['metadata_path']}")
    for entry in skipped:
        reason = entry.get("reason", "skipped")
        path = entry.get("path") or entry.get("intake_id") or ""
        print(f"  skipped : {path}")
        print(f"    reason : {reason}")
    return 0


def _load_json_summary_file(source_path: Path) -> object:
    raw = source_path.read_bytes()
    encoding = "utf-16" if raw.startswith((b"\xff\xfe", b"\xfe\xff")) else "utf-8-sig"
    return json.loads(raw.decode(encoding))


def _parse_review_source(value: str):
    from ..external_review_bundle import ReviewSource

    if "=" not in value:
        raise SystemExit("--source must use role=path")
    role, path = value.split("=", 1)
    role = role.strip()
    path = path.strip()
    if not role or not path:
        raise SystemExit("--source must use non-empty role=path")
    return ReviewSource(path=path, role=role, authority="explicit", required=True)


def cmd_web_ai_probe(*, prog: str = "devframe web-ai probe") -> int:
    import argparse

    from ..provider_binding_probe import (
        build_provider_binding_probe,
        render_provider_binding_probe_json,
        render_provider_binding_probe_text,
    )

    parser = argparse.ArgumentParser(prog=prog)
    parser.add_argument("provider", choices=["codexpro", "devspace"], help="External bridge provider profile")
    parser.add_argument("--endpoint", required=True, help="Local or tunnel MCP endpoint URL without credentials")
    parser.add_argument("--project", default="unknown", help="DevFrame project id")
    parser.add_argument("--session-id", default=None, help="Optional DevFrameSession id")
    parser.add_argument("--agent-id", default=None, help="Optional agent id")
    parser.add_argument("--role", default=None, help="Optional agent role")
    parser.add_argument("--health", default=None, help="Optional binding health")
    parser.add_argument("--format", choices=["text", "json", "session-json"], default="text", help="Output format")
    args = parser.parse_args(sys.argv[3:])

    try:
        probe = build_provider_binding_probe(
            args.provider,
            args.endpoint,
            project_id=args.project,
            session_id=args.session_id,
            agent_id=args.agent_id,
            agent_role=args.role,
            health=args.health,
        )
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    if args.format == "json":
        print(render_provider_binding_probe_json(probe), end="")
    elif args.format == "session-json":
        print(json.dumps(probe["session_summary"], indent=2, ensure_ascii=True) + "\n", end="")
    else:
        print(render_provider_binding_probe_text(probe), end="")
    return 0


def cmd_web_ai_live_check(*, prog: str = "devframe web-ai live-check") -> int:
    import argparse

    from ..mcp_live_probe import (
        mcp_live_probe,
        render_mcp_live_probe_json,
        render_mcp_live_probe_text,
    )

    parser = argparse.ArgumentParser(prog=prog)
    parser.add_argument("provider", choices=["codexpro", "devspace"], help="External bridge provider profile")
    parser.add_argument("--endpoint", required=True, help="Local or tunnel MCP endpoint URL without credentials")
    parser.add_argument("--token", default=None, help="Optional bearer token for the MCP endpoint")
    parser.add_argument("--project", default="unknown", help="DevFrame project id")
    parser.add_argument("--tool", default=None, help="Optional safe tool to call (allowlist: server_config, handoff_to_agent, task_intake, project_summary)")
    parser.add_argument("--format", choices=["text", "json", "session-json"], default="text", help="Output format")
    parser.add_argument("--import", dest="import_session", action="store_true", default=False, help="Import the live-check session summary into the runtime when status is live_ok")
    parser.add_argument("--runtime-dir", default=None, help="Local devframe runtime directory")
    args = parser.parse_args(sys.argv[3:])

    try:
        probe = mcp_live_probe(
            args.endpoint,
            provider=args.provider,
            project_id=args.project,
            token=args.token,
            tool=args.tool,
        )
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    imported_session_path = ""
    if args.import_session and probe["status"] == "live_ok":
        from ..backup_guard import default_runtime_dir
        from ..visual_state import validate_web_ai_session_summary

        runtime_dir = Path(args.runtime_dir).resolve() if args.runtime_dir else default_runtime_dir()
        sessions_dir = runtime_dir / "web-ai-sessions"
        sessions_dir.mkdir(parents=True, exist_ok=True)

        session_summary = probe["session_summary"]
        native_refs = dict(session_summary.get("native_refs") or {})
        native_refs.setdefault("source_runtime", "mcp-live-probe")
        session_summary["native_refs"] = native_refs

        try:
            validate_web_ai_session_summary(session_summary)
        except ValueError as exc:
            print(f"ERROR: invalid live-check session summary: {exc}", file=sys.stderr)
            return 2

        safe_session_id = str(session_summary.get("session_id") or "live-session")
        destination = sessions_dir / f"{safe_session_id}.json"
        destination.write_text(json.dumps(session_summary, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
        imported_session_path = str(destination)
        probe["imported_session_path"] = imported_session_path

    if args.format == "json":
        print(render_mcp_live_probe_json(probe), end="")
    elif args.format == "session-json":
        print(json.dumps(probe["session_summary"], indent=2, ensure_ascii=True) + "\n", end="")
    else:
        print(render_mcp_live_probe_text(probe), end="")
        if imported_session_path:
            print(f"Imported MCP live-check session: {imported_session_path}")

    return 0 if probe["status"] == "live_ok" else 1
