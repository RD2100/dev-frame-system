"""CLI entry: devframe init, doctor, run, code, go, handoff, pack, dashboard, and rdgoal."""
from __future__ import annotations

import sys
import ipaddress
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

HELP_TEXT = """DevFrame Control Plane CLI
  devframe init [template] [target]  - initialize project
  devframe doctor                    - check package health
  devframe code "<goal>"             - start a Codex-like coding session in the current repo
  devframe go <project> <goal>       - dispatch coding agents through /go
  devframe rdgoal <project> <goal>   - route work through rdgoal
  devframe visual-state              - export Visual Control Plane state
  devframe actions                   - show Visual Control Plane action queue
  devframe dashboard serve           - serve read-only local dashboard
  devframe run --pipeline <path>     - run pipeline
  devframe pack validate <zip>       - validate evidence pack
  devframe handoff generate          - generate handoff doc
  devframe handoff validate <file>   - validate handoff
  devframe handoff bootstrap         - dry-run bootstrap
  devframe handoff transfer --to <url> [--live --safety-flag] - transfer handoff
"""

RUN_USAGE = "Usage: devframe run --pipeline <path> [--execute] [--project <dir>]"
DASHBOARD_USAGE = "Usage: devframe dashboard serve [--runtime-dir <dir>] [--paper-project <dir>] [--host 127.0.0.1] [--port 8765] [--allow-remote]"
GO_USAGE = "Usage: devframe go <project> <goal> [--agents 2|auto] [--max-agents 4] [--target <path>] [--changed] [--execute] [--model provider/model]"
CODE_USAGE = "Usage: devframe code \"<goal>\" [--project <dir>] [--agents 1|auto] [--max-agents 4] [--target <path>] [--changed] [--execute] [--dashboard]"


def _wants_help(args: list[str]) -> bool:
    return any(arg in {"-h", "--help", "help"} for arg in args)


def _print_help() -> None:
    print(HELP_TEXT.rstrip())


def cmd_init(template: str = "code_project", target: str = ".") -> int:
    tpl_dir = ROOT / "templates" / template
    if not tpl_dir.exists():
        print(f"Unknown template: {template}")
        print(f"Available: {[d.name for d in (ROOT / 'templates').iterdir() if d.is_dir()]}")
        return 1
    target_dir = Path(target).resolve()
    target_dir.mkdir(parents=True, exist_ok=True)
    for src in tpl_dir.rglob("*"):
        if src.is_file():
            rel = src.relative_to(tpl_dir)
            dst = target_dir / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
            print(f"  created: {rel}")
    print(f"Project initialized from template '{template}' in {target_dir}")
    return 0


def _pipeline_file_valid(path: Path) -> bool:
    if not path.exists():
        return False
    try:
        from .pipeline_spec import load_pipeline, validate_pipeline
        return not validate_pipeline(load_pipeline(path))
    except Exception:
        return False


def cmd_doctor() -> int:
    gitignore_path = ROOT / ".gitignore"
    checks = {
        "templates/code_project/CURRENT_STATE.yaml": (ROOT / "templates" / "code_project" / "CURRENT_STATE.yaml").exists(),
        "templates/code_project/PIPELINE.yaml": _pipeline_file_valid(ROOT / "templates" / "code_project" / "PIPELINE.yaml"),
        "pipelines/example_pipeline.yaml": _pipeline_file_valid(ROOT / "pipelines" / "example_pipeline.yaml"),
        "pipelines/devframe_opencode.yaml": _pipeline_file_valid(ROOT / "pipelines" / "devframe_opencode.yaml"),
        "templates/code_project": (ROOT / "templates" / "code_project").is_dir(),
        "templates/paper_iteration": (ROOT / "templates" / "paper_iteration").is_dir(),
        "templates/context_handoff": (ROOT / "templates" / "context_handoff").is_dir(),
        "templates/visual_control_plane": (ROOT / "templates" / "visual_control_plane").is_dir(),
        "control_plane/rdgoal_cli.py": (ROOT / "control_plane" / "rdgoal_cli.py").exists(),
        ".gitignore covers .env": not gitignore_path.exists() or ".env" in gitignore_path.read_text(encoding="utf-8"),
    }
    passed = sum(1 for ok in checks.values() if ok)
    total = len(checks)
    for name, ok in checks.items():
        print(f"  {'PASS' if ok else 'FAIL'}: {name}")
    print(f"Doctor: {passed}/{total} checks passed")
    return 0 if passed == total else 1


def cmd_run(pipeline_path: str, dry_run: bool = True, with_submission: bool = False) -> int:
    from .pipeline_runner import dry_run as runner_dry_run
    return runner_dry_run(pipeline_path, with_submission=with_submission)


def cmd_handoff_generate(target: str = "new-conversation") -> int:
    from .handoff_generator import generate_handoff
    print(generate_handoff(target))
    return 0


def cmd_handoff_validate(path: str) -> int:
    from .handoff_verifier import validate_handoff
    text = Path(path).read_text(encoding="utf-8")
    ok, errors = validate_handoff(text)
    if ok:
        print("Handoff validation: PASSED")
        return 0
    for error in errors:
        print(f"  FAIL: {error}")
    return 1


def cmd_handoff_bootstrap(target: str = "new-conversation", dry_run: bool = True) -> int:
    from .conversation_bootstrap import run_bootstrap
    result = run_bootstrap(target, dry_run=dry_run)
    print(f"Mode: {result.mode}")
    print(f"Handoff generated: {result.handoff_generated} ({result.handoff_length} chars)")
    print(f"Submitted: {result.submitted}")
    print(f"Reply received: {result.reply_received}")
    print(f"Handoff verified: {result.handoff_verified}")
    return 0 if result.handoff_verified else 1


def cmd_handoff_transfer() -> int:
    """Transfer handoff document. Dry-run by default; --live requires safety flag."""
    import argparse

    parser = argparse.ArgumentParser(prog="devframe handoff transfer")
    parser.add_argument("--to", dest="target_url", default=None, help="Target conversation URL or ID")
    parser.add_argument("--file", dest="handoff_file", default="HANDOFF.md", help="Handoff file to transfer")
    parser.add_argument("--live", dest="live", action="store_true", default=False, help="Execute live CDP transfer")
    parser.add_argument("--safety-flag", dest="safety_flag", action="store_true", default=False, help="Required for live mode")

    args_list = sys.argv[sys.argv.index("transfer") + 1:]
    try:
        parsed = parser.parse_args(args_list)
    except SystemExit:
        return 1

    target = parsed.target_url or "new-conversation"
    handoff_file = parsed.handoff_file

    if not parsed.live:
        print(f"Handoff transfer (dry-run): would upload {handoff_file} to {target}")
        print("  Step 1: Verify HANDOFF.md exists")
        print("  Step 2: CDP connect and navigate to target")
        print("  Step 3: Upload HANDOFF.md as .md file attachment")
        print("  Step 4: Include bootstrap prompt")
        print("  Step 5: Click send")
        print("  Step 6: Capture reply and verify handoff_verified")
        return 0

    if not parsed.safety_flag:
        print("ERROR: --safety-flag required for live CDP transfer")
        return 1

    from .playwright_bridge import BridgeConfig, BridgeMode, health_check as bridge_health, submit_via_bridge
    from .submission_result import SubmissionRequest

    config = BridgeConfig(mode=BridgeMode.LIVE, safety_flag=True, conversation_id=target)
    ok, reason = bridge_health(config)
    if not ok:
        print(f"ERROR: Health check failed: {reason}")
        return 1

    req = SubmissionRequest(review_run_id=handoff_file)
    result = submit_via_bridge(req, config)
    print(f"Transfer result: success={result.success}, mode={result.mode}")
    print(f"Detail: {result.detail}")
    return 0 if result.success else 1


def cmd_pack_validate(zip_path: str) -> int:
    """Validate evidence pack: manifest consistency, no bypass, files present."""
    import subprocess
    import zipfile

    zp = Path(zip_path)
    if not zp.exists():
        print(f"ERROR: ZIP not found: {zip_path}")
        return 1

    errors = 0
    with zipfile.ZipFile(zp, "r") as zf:
        namelist = set(zf.namelist())
        print(f"  ZIP files: {len(namelist)}")

        if "PACK_MANIFEST.md" not in namelist:
            print("  FAIL: PACK_MANIFEST.md not in ZIP")
            errors += 1
        else:
            manifest_text = zf.read("PACK_MANIFEST.md").decode("utf-8")
            manifest_files = set()
            for line in manifest_text.split("\n"):
                if line.startswith("|") and "|" in line[1:]:
                    parts = [p.strip() for p in line.split("|")[1:-1]]
                    if parts and parts[0] and not parts[0].startswith("-"):
                        manifest_files.add(parts[0])
            manifest_files.discard("path")

            extra_in_zip = namelist - manifest_files - {"PACK_MANIFEST.md"}
            extra_in_manifest = manifest_files - namelist
            if extra_in_zip:
                print(f"  FAIL: Files in ZIP but not manifest: {extra_in_zip}")
                errors += 1
            if extra_in_manifest:
                print(f"  FAIL: Files in manifest but not ZIP: {extra_in_manifest}")
                errors += 1
            if not extra_in_zip and not extra_in_manifest:
                print(f"  PASS: Manifest <-> ZIP bidirectional match ({len(manifest_files)} files)")

            summary_files = {
                "GPT_REVIEW_PROMPT.md",
                "CLOSURE_REPORT.md",
                "CLOSURE_REPORT.yaml",
                "SAFETY_ATTESTATION.md",
                "PACK_MANIFEST.md",
                "WORKFLOW_CLOSURE_VALIDATION.yaml",
            }
            verify_files = {"TEST_OUTPUT.txt", "BYPASS_CHECK_OUTPUT.txt", "GATE_OUTPUT.txt", "DOCTOR_OUTPUT.txt"}
            actual_patterns = [
                "contracts/",
                "schemas/",
                "docs/",
                "templates/",
                "scripts/",
                "tests/",
                "pipelines/",
                "examples/",
                "review/",
                "input/",
                "closure/",
                "submission/",
                "control_plane/",
                "diff.patch",
            ]
            actual_deliverables = [
                file_name for file_name in namelist
                if file_name not in summary_files
                and file_name not in verify_files
                and any(file_name.startswith(pattern.rstrip("/")) or pattern.rstrip("/") in file_name for pattern in actual_patterns)
            ]
            if not actual_deliverables:
                print("  FAIL: Evidence pack is summary-only (no actual deliverables per A1 patterns)")
                errors += 1
            else:
                print(f"  PASS: Contains {len(actual_deliverables)} actual deliverable files (A1 patterns)")

    validator_script = ROOT.parent / "agent-acceptance" / "scripts" / "validate_workflow_closure.py"
    if validator_script.exists():
        print("  Running workflow closure validator...")
        result = subprocess.run(
            [sys.executable, str(validator_script), str(zp)],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        print(f"  {result.stdout.strip()}")
        if result.returncode != 0:
            errors += 1
            print("  FAIL: Workflow closure validation failed (SD-01/02/03 check)")
    else:
        print("  FAIL: agent-acceptance validator not found; cannot verify SD-01/02/03")
        errors += 1

    if errors:
        print(f"Pack validation: FAILED ({errors} errors)")
        return 1
    print("Pack validation: PASS")
    return 0


def cmd_rdgoal() -> int:
    from .rdgoal_cli import main as rdgoal_main
    return rdgoal_main(sys.argv[2:])


def cmd_go() -> int:
    import argparse

    from .go_dispatch import (
        DEFAULT_GO_MODEL,
        DEFAULT_OPENCODE_AGENT,
        render_go_dispatch_text,
        run_go_dispatch,
    )

    parser = argparse.ArgumentParser(prog="devframe go")
    parser.add_argument("project_path")
    parser.add_argument("requirement")
    parser.add_argument("--agents", default="2", help="Number of coding-agent shards, or auto")
    parser.add_argument("--max-agents", type=int, default=4, help="Maximum shards when --agents auto is used")
    parser.add_argument("--target", action="append", default=[], help="Target file or directory. May be repeated")
    parser.add_argument("--changed", action="store_true", help="Use changed git files as token-saving targets")
    parser.add_argument("--runtime-dir", default=None, help="Local runtime directory for go dispatch state")
    parser.add_argument("--execute", action="store_true", help="Run shard workers concurrently")
    parser.add_argument("--timeout", type=int, default=900, help="Per-worker timeout in seconds")
    parser.add_argument("--model", default=DEFAULT_GO_MODEL, help="OpenCode model id for default worker command")
    parser.add_argument("--opencode-agent", default=DEFAULT_OPENCODE_AGENT, help="OpenCode agent name")
    parser.add_argument(
        "--command",
        nargs=argparse.REMAINDER,
        default=[],
        help="Worker command for --execute. Omit to use opencode run.",
    )
    args = parser.parse_args(sys.argv[2:])
    try:
        targets = _resolve_coding_targets(args.project_path, args.target, changed=args.changed)
        agents = _resolve_agent_count(args.agents, targets, max_agents=args.max_agents)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    try:
        result = run_go_dispatch(
            args.project_path,
            args.requirement,
            runtime_dir=args.runtime_dir,
            agents=agents,
            targets=targets,
            execute=args.execute,
            worker_command=args.command or None,
            model=args.model,
            opencode_agent=args.opencode_agent,
            timeout_seconds=args.timeout,
        )
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    print(render_go_dispatch_text(result), end="")
    return 0 if result.status in {"queued", "passed"} else 1


def cmd_code() -> int:
    import argparse

    from .go_dispatch import (
        DEFAULT_GO_MODEL,
        DEFAULT_OPENCODE_AGENT,
        render_go_dispatch_text,
        run_go_dispatch,
    )

    parser = argparse.ArgumentParser(prog="devframe code")
    parser.add_argument("goal", nargs="?", help="Coding goal for the current repository")
    parser.add_argument("--project", default=".", help="Project/repository root. Defaults to the current directory")
    parser.add_argument("--agents", default="1", help="Number of coding-agent shards, or auto")
    parser.add_argument("--max-agents", type=int, default=4, help="Maximum shards when --agents auto is used")
    parser.add_argument("--target", action="append", default=[], help="Target file or directory. May be repeated")
    parser.add_argument("--changed", action="store_true", help="Use changed git files as token-saving targets")
    parser.add_argument("--runtime-dir", default=None, help="Local runtime directory for code session state")
    parser.add_argument("--execute", action="store_true", help="Run coding worker(s) instead of only preparing packets")
    parser.add_argument("--timeout", type=int, default=900, help="Per-worker timeout in seconds")
    parser.add_argument("--model", default=DEFAULT_GO_MODEL, help="OpenCode model id for default worker command")
    parser.add_argument("--opencode-agent", default=DEFAULT_OPENCODE_AGENT, help="OpenCode agent name")
    parser.add_argument("--dashboard", action="store_true", help="Serve the read-only dashboard after preparing the session")
    parser.add_argument("--host", default="127.0.0.1", help="Dashboard bind host when --dashboard is used")
    parser.add_argument("--port", type=int, default=8765, help="Dashboard bind port when --dashboard is used")
    parser.add_argument("--refresh-seconds", type=int, default=5, help="Dashboard refresh interval; use 0 to disable")
    parser.add_argument("--allow-remote", action="store_true", help="Allow --dashboard to bind outside loopback")
    parser.add_argument(
        "--command",
        nargs=argparse.REMAINDER,
        default=[],
        help="Worker command for --execute. Omit to use opencode run.",
    )
    args = parser.parse_args(sys.argv[2:])

    goal = args.goal
    if not goal and sys.stdin.isatty():
        goal = input("Goal: ").strip()
    if not goal:
        print(CODE_USAGE)
        return 2
    if args.dashboard and not args.allow_remote and not _is_loopback_host(args.host):
        print("ERROR: dashboard exposes local runtime paths; use --allow-remote to bind outside loopback.")
        return 1
    try:
        targets = _resolve_coding_targets(args.project, args.target, changed=args.changed)
        agents = _resolve_agent_count(args.agents, targets, max_agents=args.max_agents)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    try:
        result = run_go_dispatch(
            args.project,
            goal,
            runtime_dir=args.runtime_dir,
            agents=agents,
            targets=targets,
            execute=args.execute,
            worker_command=args.command or None,
            model=args.model,
            opencode_agent=args.opencode_agent,
            timeout_seconds=args.timeout,
        )
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    print("DevFrame Code session")
    print("Backend      : /go concurrent coding-agent dispatch")
    print("Default mode : prepare packets only; add --execute to spend worker tokens")
    print("")
    print(render_go_dispatch_text(result), end="")
    if args.dashboard:
        from .dashboard import serve_dashboard

        print("")
        print("Dashboard UI : starting read-only visual interface")
        print("Chinese UI   : append ?lang=zh-CN to the dashboard URL")
        serve_dashboard(
            runtime_dir=result.runtime_dir,
            host=args.host,
            port=args.port,
            refresh_seconds=args.refresh_seconds,
        )
    return 0 if result.status in {"queued", "passed"} else 1


def _resolve_coding_targets(project_path: str | Path, targets: list[str], *, changed: bool) -> list[str]:
    if not changed:
        return list(targets)
    git_targets = _git_changed_targets(project_path)
    merged = _dedupe_targets([*targets, *git_targets])
    if not merged:
        raise ValueError("--changed found no modified, staged, or untracked git files")
    return merged


def _resolve_agent_count(raw_agents: str, targets: list[str], *, max_agents: int) -> int:
    if max_agents < 1:
        raise ValueError("--max-agents must be >= 1")
    if raw_agents.strip().lower() == "auto":
        if not targets:
            return 1
        return max(1, min(len(targets), max_agents))
    try:
        agents = int(raw_agents)
    except ValueError as exc:
        raise ValueError("--agents must be a positive integer or auto") from exc
    if agents < 1:
        raise ValueError("--agents must be >= 1")
    return agents


def _git_changed_targets(project_path: str | Path) -> list[str]:
    project_root = Path(project_path).resolve()
    if not project_root.exists():
        raise ValueError(f"project path does not exist: {project_root}")
    inside = _git_output(project_root, ["rev-parse", "--is-inside-work-tree"])
    if inside.strip().lower() != "true":
        raise ValueError(f"--changed requires a git work tree: {project_root}")
    targets: list[str] = []
    for args in (
        ["diff", "--name-only", "--diff-filter=ACMR"],
        ["diff", "--cached", "--name-only", "--diff-filter=ACMR"],
        ["ls-files", "--others", "--exclude-standard"],
    ):
        targets.extend(line.strip() for line in _git_output(project_root, args).splitlines() if line.strip())
    return _dedupe_targets(targets)


def _git_output(project_root: Path, args: list[str]) -> str:
    result = subprocess.run(
        ["git", "-C", str(project_root), *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        raise ValueError(f"git {' '.join(args)} failed: {detail}")
    return result.stdout


def _dedupe_targets(targets: list[str]) -> list[str]:
    seen: set[str] = set()
    unique: list[str] = []
    for target in targets:
        text = str(target).strip()
        if text and text not in seen:
            seen.add(text)
            unique.append(text)
    return unique


def cmd_visual_state() -> int:
    import argparse
    import yaml

    from .visual_state import (
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

    from .visual_state import (
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


def _invalid_dynamic_action_filters(
    actions: list[dict],
    source_ids: list[str] | None,
    action_ids: list[str] | None,
) -> dict[str, list[str]]:
    from .visual_state import action_filter_values

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

    from .dashboard import serve_dashboard

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


def _is_loopback_host(host: str) -> bool:
    if host.lower() == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def main() -> int:
    if len(sys.argv) < 2 or _wants_help(sys.argv[1:2]):
        _print_help()
        return 0

    cmd = sys.argv[1]
    if cmd == "handoff":
        sub = sys.argv[2] if len(sys.argv) > 2 else "generate"
        if sub == "generate":
            return cmd_handoff_generate()
        if sub == "validate":
            return cmd_handoff_validate(sys.argv[3]) if len(sys.argv) > 3 else 1
        if sub == "bootstrap":
            return cmd_handoff_bootstrap()
        if sub == "transfer":
            return cmd_handoff_transfer()
        print(f"Unknown handoff subcommand: {sub}")
        return 1

    if cmd == "init":
        template = sys.argv[2] if len(sys.argv) > 2 else "code_project"
        target = sys.argv[3] if len(sys.argv) > 3 else "."
        return cmd_init(template, target)

    if cmd == "rdgoal":
        return cmd_rdgoal()

    if cmd == "code":
        if _wants_help(sys.argv[2:]):
            print(CODE_USAGE)
            return 0
        return cmd_code()

    if cmd == "go":
        if _wants_help(sys.argv[2:]):
            print(GO_USAGE)
            return 0
        return cmd_go()

    if cmd == "visual-state":
        return cmd_visual_state()

    if cmd == "actions":
        return cmd_actions()

    if cmd == "dashboard":
        return cmd_dashboard()

    if cmd == "doctor":
        return cmd_doctor()

    if cmd == "run":
        if _wants_help(sys.argv[2:]):
            print(RUN_USAGE)
            return 0
        if "--pipeline" not in sys.argv:
            print(RUN_USAGE)
            return 1
        index = sys.argv.index("--pipeline")
        if index + 1 >= len(sys.argv):
            print(RUN_USAGE)
            return 1
        path = sys.argv[index + 1]
        with_submission = "--with-submission" in sys.argv
        execute = "--execute" in sys.argv
        project_dir = None
        if "--project" in sys.argv:
            project_index = sys.argv.index("--project")
            if project_index + 1 >= len(sys.argv):
                print(RUN_USAGE)
                return 1
            project_dir = Path(sys.argv[project_index + 1]).resolve()

        if execute:
            from .stage_executor import execute_full_pipeline
            print(f"Pipeline: {path}")
            print("Mode: execute (via framework stage_executor)")
            if project_dir:
                print(f"Project: {project_dir}")
            results = execute_full_pipeline(project_dir=project_dir)
            total = len(results)
            completed = sum(1 for result in results if result.status == "completed")
            for result in results:
                status = "PASS" if result.status == "completed" else "FAIL"
                print(f"  [{status}] {result.stage_id} ({len(result.outputs)} outputs)")
            print(f"\nStages: {completed}/{total} completed")
            return 0 if completed == total else 1
        return cmd_run(path, with_submission=with_submission)

    if cmd == "pack":
        sub = sys.argv[2] if len(sys.argv) > 2 else ""
        if sub == "validate":
            if len(sys.argv) < 4:
                print("Usage: devframe pack validate <zip>")
                return 1
            return cmd_pack_validate(sys.argv[3])
        print("Usage: devframe pack validate <zip>")
        return 1

    print(f"Unknown command: {cmd}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
