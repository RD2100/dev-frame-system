"""CLI entry: devframe init, doctor, run, code, go, handoff, pack, dashboard, and rdgoal."""
from __future__ import annotations

import sys
import ipaddress
import json
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

from .coding_dispatch import resolve_agent_count, resolve_coding_targets

HELP_TEXT = """DevFrame Code CLI
  Primary workflow: use devframe code as an OpenCode-first local coding tool.

  devframe init [template] [target]  - initialize project
  devframe doctor                    - check package health
  devframe code [[<goal>] | --prompt-file <path>] - start an OpenCode-backed coding session
  devframe code workers              - show available coding worker profiles
  devframe code status [latest|<go-run-id>] - inspect a previous /go coding run without spending worker tokens
  devframe code execute [latest|<go-run-id>] - execute a prepared /go run without creating packets
  devframe code session [latest|<go-run-id>] - inspect a previous /go coding run sessions
  devframe client                    - launch the zero-config local Agent client
  devframe sessions                  - show all Visual Control Plane sessions (including imported web AI sessions)
  devframe web-ai import <source>    - import a summary-only web AI session JSON into the runtime
  devframe web-ai probe <provider>   - build an importable CodexPro/DevSpace binding probe
   devframe web-ai live-check codexpro|devspace --endpoint <url> [--token <token>] [--project <id>] [--tool server_config|handoff_to_agent|task_intake|project_summary] [--format text|json|session-json] - live-check an MCP endpoint
  devframe web-ai bind-chrome        - bind an already-open ChatGPT Chrome tab as a summary-only session
  devframe web-ai submit-review --zip <path> --prompt-file <path> --conversation <url-or-id> [--cdp-endpoint <url>] [--execute] - submit a review zip to a web AI conversation
  devframe web-ai record-mcp-result --conversation <url> --tool-name <name> --status completed|blocked|failed|web_host_completed|web_host_no_result|local_mcp_completed [--provider chatgpt] [--project dev-frame-system] [--connector-name <name>] [--connector-app-id <id>] [--marker <text>] --result <summary> [--output-id <id>] [--output-name <name>] [--runtime-dir <dir>] - record an observed Web GPT MCP tool result
  devframe web-ai record-task-intake --conversation <url> --task-title <text> --task-summary <text> [--provider chatgpt] [--project dev-frame-system] [--connector-name <name>] [--connector-app-id <id>] [--priority high|medium|low] [--suggested-agent opencode|codex|custom] [--marker <text>] [--runtime-dir <dir>] - record a safe Web GPT task intake summary
  devframe web-ai import-task-intakes --project-root <dir> [--runtime-dir <dir>] [--provider codexpro] [--project dev-frame-system] [--connector-name <name>] [--connector-app-id <id>] - import .ai-bridge/task-intakes/*.json into the runtime
  devframe web-ai dispatch-task-intakes --project-root <dir> [--runtime-dir <dir>] [--intake-id <id>] [--agents 1] [--execute] - dispatch imported Web GPT task intakes into @go/OpenCode
  devframe go <project> <goal>       - dispatch coding agents through /go
  devframe atgo <goal>               - @go evidence + coding dispatch entrypoint
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
GO_USAGE = "Usage: devframe go <project> <goal> [--agents 2|auto] [--max-agents 4] [--target <path>] [--changed] [--since <git-ref>] [--preview] [--execute] [--worker opencode] [--model provider/model]"
ATGO_USAGE = "Usage: devframe atgo \"<goal>\" [--project <dir>] [--runtime-dir <dir>] [--target <path>] [--execute]"
CODE_USAGE = "Usage: devframe code [[\"<goal>\"] | --prompt-file <path>] [--project <dir>] [--agents 1|auto] [--max-agents 4] [--target <path>] [--changed] [--since <git-ref>] [--preview] [--execute] [--worker opencode] [--dashboard]"
CODE_WORKERS_USAGE = "Usage: devframe code workers [--format text|json]"
CODE_STATUS_USAGE = "Usage: devframe code status [latest|<go-run-id>] [--runtime-dir <dir>] [--format text|json]"
CODE_EXECUTE_USAGE = "Usage: devframe code execute [latest|<go-run-id>] [--runtime-dir <dir>] [--timeout <seconds>] [--rerun-passed]"
SESSION_USAGE = "Usage: devframe code session [latest|<go-run-id>] [--runtime-dir <dir>] [--format text|json]"
CLIENT_USAGE = "Usage: devframe client [serve|plan|bridge|t3desktop|smoke|doctor] [--runtime-dir <dir>] [--paper-project <dir>] [--host 127.0.0.1] [--port 8765] [--lang en|zh-CN] [--dry-run] [--format text|json] [--open] [--allow-remote] [--output <dir>] [--t3-root <dir>] [--force]"
SESSIONS_USAGE = "Usage: devframe sessions [--runtime-dir <dir>] [--format text|json]"
WEB_AI_IMPORT_USAGE = "Usage: devframe web-ai import <source> [--runtime-dir <dir>]"
WEB_AI_PROBE_USAGE = "Usage: devframe web-ai probe codexpro|devspace --endpoint <url> [--project <id>] [--format text|json|session-json]"
WEB_AI_LIVE_CHECK_USAGE = "Usage: devframe web-ai live-check codexpro|devspace --endpoint <url> [--token <token>] [--project <id>] [--tool server_config|handoff_to_agent|task_intake|project_summary] [--format text|json|session-json] [--import] [--runtime-dir <dir>]"
WEB_AI_BIND_CHROME_USAGE = "Usage: devframe web-ai bind-chrome [--runtime-dir <dir>] [--project <id>] [--cdp-endpoint http://127.0.0.1:9222] [--dry-run] [--format text|json]"
WEB_AI_SUBMIT_REVIEW_USAGE = "Usage: devframe web-ai submit-review --zip <path> --prompt-file <path> (UTF-8/UTF-8-SIG or UTF-16 BOM) --conversation <url-or-id> [--cdp-endpoint http://127.0.0.1:9222] [--execute]"
WEB_AI_RECORD_MCP_RESULT_USAGE = "Usage: devframe web-ai record-mcp-result --conversation <url> --tool-name <name> --status completed|blocked|failed|web_host_completed|web_host_no_result|local_mcp_completed [--origin web_host|local_mcp] [--outcome completed|blocked|failed|no_result] [--provider chatgpt] [--project dev-frame-system] [--connector-name <name>] [--connector-app-id <id>] [--marker <text>] --result <summary> [--output-id <id>] [--output-name <name>] [--runtime-dir <dir>]"
WEB_AI_RECORD_TASK_INTAKE_USAGE = "Usage: devframe web-ai record-task-intake --conversation <url> --task-title <text> --task-summary <text> [--provider chatgpt] [--project dev-frame-system] [--connector-name <name>] [--connector-app-id <id>] [--priority high|medium|low] [--suggested-agent opencode|codex|custom] [--marker <text>] [--runtime-dir <dir>]"
WEB_AI_IMPORT_TASK_INTAKES_USAGE = "Usage: devframe web-ai import-task-intakes [--project-root <dir>] [--runtime-dir <dir>] [--provider codexpro] [--project dev-frame-system] [--connector-name <name>] [--connector-app-id <id>]"
WEB_AI_DISPATCH_TASK_INTAKES_USAGE = "Usage: devframe web-ai dispatch-task-intakes [--project-root <dir>] [--runtime-dir <dir>] [--provider codexpro] [--project dev-frame-system] [--connector-name <name>] [--connector-app-id <id>] [--intake-id <id>] [--agents 1] [--limit <n>] [--execute] [--model provider/model] [--opencode-agent build]"


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

    req = SubmissionRequest(zip_path=handoff_file, review_run_id=handoff_file)
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
        DEFAULT_GO_WORKER,
        DEFAULT_OPENCODE_AGENT,
        GO_WORKERS,
        build_go_worker_command,
        describe_go_worker,
        estimate_target_bytes,
        render_go_dispatch_text,
        render_command,
        resolve_methodology,
        run_go_dispatch,
        split_targets_by_size,
    )

    parser = argparse.ArgumentParser(prog="devframe go")
    parser.add_argument("project_path")
    parser.add_argument("requirement")
    parser.add_argument("--agents", default="2", help="Number of coding-agent shards, or auto")
    parser.add_argument("--max-agents", type=int, default=4, help="Maximum shards when --agents auto is used")
    parser.add_argument("--target", action="append", default=[], help="Target file or directory. May be repeated")
    parser.add_argument("--changed", action="store_true", help="Use changed git files as token-saving targets")
    parser.add_argument("--since", default=None, help="Use files changed since this git ref as token-saving targets")
    parser.add_argument("--preview", action="store_true", help="Print the shard plan without creating packets")
    parser.add_argument("--runtime-dir", default=None, help="Local runtime directory for go dispatch state")
    parser.add_argument("--execute", action="store_true", help="Run shard workers concurrently")
    parser.add_argument("--timeout", type=int, default=900, help="Per-worker timeout in seconds")
    parser.add_argument("--worker", choices=GO_WORKERS, default=DEFAULT_GO_WORKER, help="Built-in coding worker profile")
    parser.add_argument("--model", default=None, help="Model id for the selected worker; opencode defaults to stepfun/step-3.7-flash")
    parser.add_argument("--opencode-agent", default=DEFAULT_OPENCODE_AGENT, help="OpenCode agent name")
    parser.add_argument(
        "--command",
        nargs=argparse.REMAINDER,
        default=[],
        help="Worker command for --execute. Omit to use opencode run.",
    )
    args = parser.parse_args(sys.argv[2:])
    try:
        targets = resolve_coding_targets(args.project_path, args.target, changed=args.changed, since=args.since)
        agents = resolve_agent_count(args.agents, targets, max_agents=args.max_agents)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    effective_requirement, methodology = resolve_methodology(args.requirement)
    if args.preview:
        print(_render_coding_preview(
            entrypoint="devframe go",
            project_path=args.project_path,
            goal=effective_requirement,
            targets=targets,
            agents=agents,
            execute=args.execute,
            runtime_dir=args.runtime_dir,
            worker_command=args.command or None,
            worker=args.worker,
            model=args.model,
            opencode_agent=args.opencode_agent,
            build_worker_command=build_go_worker_command,
            describe_worker=describe_go_worker,
            render_worker_command=render_command,
            split_targets=split_targets_by_size,
            estimate_target_bytes=estimate_target_bytes,
            methodology=methodology,
        ), end="")
        return 0

    try:
        result = run_go_dispatch(
            args.project_path,
            args.requirement,
            runtime_dir=args.runtime_dir,
            agents=agents,
            targets=targets,
            execute=args.execute,
            worker_command=args.command or None,
            worker=args.worker,
            model=args.model,
            opencode_agent=args.opencode_agent,
            timeout_seconds=args.timeout,
        )
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    print(render_go_dispatch_text(result), end="")
    return 0 if result.status in {"queued", "passed"} else 1


def cmd_atgo() -> int:
    import argparse

    from .backup_guard import default_runtime_dir
    from .go_dispatch import resolve_methodology, run_go_dispatch

    parser = argparse.ArgumentParser(prog="devframe atgo")
    parser.add_argument("goal", help="Coding goal for the @go evidence + coding dispatch entrypoint")
    parser.add_argument("--project", default=".", help="Project/repository root. Defaults to the current directory")
    parser.add_argument("--runtime-dir", default=None, help="Local runtime directory for atgo evidence and dispatch state")
    parser.add_argument("--target", action="append", default=[], help="Target file or directory. May be repeated")
    parser.add_argument("--execute", action="store_true", help="Execute the prepared coding run after creating evidence")
    args = parser.parse_args(sys.argv[2:])

    runtime_root = Path(args.runtime_dir).resolve() if args.runtime_dir else default_runtime_dir()
    project_root = Path(args.project).resolve()

    try:
        targets = resolve_coding_targets(args.project, args.target, changed=False, since=None)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    effective_goal, methodology = resolve_methodology(args.goal)

    try:
        result = run_go_dispatch(
            args.project,
            args.goal,
            runtime_dir=args.runtime_dir,
            agents=1,
            targets=targets,
            execute=False,
        )
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    evidence_dir = runtime_root / "atgo-runs" / result.go_run_id
    evidence_dir.mkdir(parents=True, exist_ok=True)

    task_spec_path = evidence_dir / "task-spec.md"
    task_spec_path.write_text(
        "\n".join([
            f"# TaskSpec: {result.go_run_id}",
            "",
            f"- **Project**: {result.project_id or project_root.name}",
            f"- **Operation**: atgo coding shard 1/1",
            f"- **Project Root**: {project_root}",
            f"- **Requirement**: {result.requirement}",
            (
                f"- **Methodology**: {methodology.get('title') or methodology.get('skill_id')}"
                if methodology else ""
            ),
            f"- **Targets**: {', '.join(targets) if targets else '(project scope)'}",
        ]).replace("\n\n- **Targets**", "\n- **Targets**") + "\n",
        encoding="utf-8",
    )

    chain_evidence_path = evidence_dir / "chain-evidence.json"
    chain_evidence = {
        "run_id": result.go_run_id,
        "executor_id": "opencode",
        "mode": "prepare",
        "planner": None,
        "task": str(task_spec_path),
        "evidence_files": [
            "diff.patch",
            "test-output.md",
            "safety-report.json",
            "chain-evidence.json",
            "review.md",
            "review.yaml",
            "final-report.md",
        ],
        "timestamps": {
            "created_at": datetime.now(timezone.utc).isoformat(),
        },
    }
    chain_evidence_path.write_text(json.dumps(chain_evidence, indent=2) + "\n", encoding="utf-8")

    print("DevFrame @go")
    print(f"evidence_dir : {evidence_dir}")
    print(f"task_spec    : {task_spec_path}")
    print(f"chain_evidence: {chain_evidence_path}")
    print(f"go_run_id    : {result.go_run_id}")
    print("")
    print(f"Status   : devframe code status {result.go_run_id} --runtime-dir {runtime_root}")
    print(f"Execute  : devframe code execute {result.go_run_id} --runtime-dir {runtime_root}")
    print(f"Reviewer : devframe actions --runtime-dir {runtime_root}")
    print(f"Finalize : tools/go_evidence.py finalize {evidence_dir}")

    if args.execute:
        from .backup_guard import default_runtime_dir
        from .go_dispatch import execute_go_run, render_go_dispatch_text
        try:
            exec_result = execute_go_run(runtime_root, result.go_run_id, timeout_seconds=900)
        except ValueError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 1
        print("")
        print("DevFrame @go execute")
        print(render_go_dispatch_text(exec_result), end="")
        return 0 if exec_result.status in {"queued", "passed"} else 1

    return 0


def cmd_code() -> int:
    import argparse

    from .go_dispatch import (
        DEFAULT_GO_WORKER,
        DEFAULT_OPENCODE_AGENT,
        GO_WORKERS,
        build_go_worker_command,
        describe_go_worker,
        estimate_target_bytes,
        render_go_dispatch_text,
        render_command,
        resolve_methodology,
        run_go_dispatch,
        split_targets_by_size,
    )

    parser = argparse.ArgumentParser(prog="devframe code")
    parser.add_argument("goal", nargs="?", help="Coding goal for the current repository")
    parser.add_argument("--prompt-file", default=None, help="Read a multi-line coding goal from a text file")
    parser.add_argument("--project", default=".", help="Project/repository root. Defaults to the current directory")
    parser.add_argument("--agents", default="1", help="Number of coding-agent shards, or auto")
    parser.add_argument("--max-agents", type=int, default=4, help="Maximum shards when --agents auto is used")
    parser.add_argument("--target", action="append", default=[], help="Target file or directory. May be repeated")
    parser.add_argument("--changed", action="store_true", help="Use changed git files as token-saving targets")
    parser.add_argument("--since", default=None, help="Use files changed since this git ref as token-saving targets")
    parser.add_argument("--preview", action="store_true", help="Print the shard plan without creating packets")
    parser.add_argument("--runtime-dir", default=None, help="Local runtime directory for code session state")
    parser.add_argument("--execute", action="store_true", help="Run coding worker(s) instead of only preparing packets")
    parser.add_argument("--timeout", type=int, default=900, help="Per-worker timeout in seconds")
    parser.add_argument("--worker", choices=GO_WORKERS, default=DEFAULT_GO_WORKER, help="Built-in coding worker profile")
    parser.add_argument("--model", default=None, help="Model id for the selected worker; opencode defaults to stepfun/step-3.7-flash")
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

    try:
        goal = _resolve_code_goal(args.goal, args.prompt_file)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    if not goal:
        print(CODE_USAGE)
        return 2
    effective_goal, methodology = resolve_methodology(goal)
    if args.dashboard and not args.allow_remote and not _is_loopback_host(args.host):
        print("ERROR: dashboard exposes local runtime paths; use --allow-remote to bind outside loopback.")
        return 1
    try:
        targets = resolve_coding_targets(args.project, args.target, changed=args.changed, since=args.since)
        agents = resolve_agent_count(args.agents, targets, max_agents=args.max_agents)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    if args.preview:
        print(_render_coding_preview(
            entrypoint="devframe code",
            project_path=args.project,
            goal=effective_goal,
            targets=targets,
            agents=agents,
            execute=args.execute,
            runtime_dir=args.runtime_dir,
            worker_command=args.command or None,
            worker=args.worker,
            model=args.model,
            opencode_agent=args.opencode_agent,
            build_worker_command=build_go_worker_command,
            describe_worker=describe_go_worker,
            render_worker_command=render_command,
            split_targets=split_targets_by_size,
            estimate_target_bytes=estimate_target_bytes,
            methodology=methodology,
        ), end="")
        return 0

    try:
        result = run_go_dispatch(
            args.project,
            goal,
            runtime_dir=args.runtime_dir,
            agents=agents,
            targets=targets,
            execute=args.execute,
            worker_command=args.command or None,
            worker=args.worker,
            model=args.model,
            opencode_agent=args.opencode_agent,
            timeout_seconds=args.timeout,
        )
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    print("DevFrame Code session")
    print("Tool shape   : OpenCode-first local coding CLI")
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


def cmd_code_status(*, prog: str = "devframe code status") -> int:
    import argparse

    from .backup_guard import default_runtime_dir

    parser = argparse.ArgumentParser(prog=prog)
    parser.add_argument("run_id", nargs="?", default="latest", help="go-run id to inspect, or latest")
    parser.add_argument("--runtime-dir", default=None, help="Local runtime directory for code session state")
    parser.add_argument("--format", choices=["text", "json"], default="text", help="Output format")
    args = parser.parse_args(sys.argv[3:])

    runtime_dir = Path(args.runtime_dir).resolve() if args.runtime_dir else default_runtime_dir()
    try:
        run = _load_go_run_status(runtime_dir, args.run_id)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    if args.format == "json":
        print(json.dumps(run, indent=2, ensure_ascii=False))
    else:
        print(_render_go_run_status(run))
    return 0


def cmd_code_session(*, prog: str = "devframe code session") -> int:
    import argparse

    from .backup_guard import default_runtime_dir

    parser = argparse.ArgumentParser(prog=prog)
    parser.add_argument("run_id", nargs="?", default="latest", help="go-run id to inspect, or latest")
    parser.add_argument("--runtime-dir", default=None, help="Local runtime directory for code session state")
    parser.add_argument("--format", choices=["text", "json"], default="text", help="Output format")
    args = parser.parse_args(sys.argv[3:])

    runtime_dir = Path(args.runtime_dir).resolve() if args.runtime_dir else default_runtime_dir()
    try:
        run = _load_go_run_status(runtime_dir, args.run_id)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    if args.format == "json":
        print(json.dumps(_public_sessions(run), indent=2, ensure_ascii=False))
    else:
        print(_render_sessions(run))
    return 0


def _public_sessions(run: dict) -> list[dict]:
    sessions: list[dict[str, object]] = []
    for agent in run.get("agents", []):
        if not isinstance(agent, dict):
            continue
        worker_command = agent.get("worker_command") or []
        executable = str(worker_command[0]).replace("\\", "/").rsplit("/", 1)[-1].lower() if worker_command else ""
        if executable.endswith(".cmd"):
            executable = executable[:-4]
        provider = executable.split(".")[0] if "." in executable else (executable or "local")
        session_id = f"{run.get('go_run_id', 'go-run')}-{agent.get('agent_id', 'agent')}"
        task_spec_path = str(agent.get("task_spec_path") or "")
        sessions.append({
            "session_id": session_id,
            "provider": provider,
            "agent_id": str(agent.get("agent_id", "")),
            "agent_role": "executor",
            "run_id": str(run.get("go_run_id", "")),
            "status": str(agent.get("worker_status") or agent.get("status") or "unknown"),
            "task_spec": Path(task_spec_path).name if task_spec_path else "",
            "targets": agent.get("targets") or [],
            "changed_files": _public_changed_files(agent.get("changed_files") or []),
        })
    return sessions


def _public_changed_files(changed_files: object) -> list[str]:
    if not isinstance(changed_files, list):
        return []
    files: list[str] = []
    for changed_file in changed_files:
        label = _public_file_label(changed_file)
        if label and label.lower() not in {"(none)", "none", "(unknown)", "unknown"}:
            files.append(label)
    return files


def _public_file_label(value: object) -> str:
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


def _render_sessions(run: dict) -> str:
    sessions = _public_sessions(run)
    lines = [
        "DevFrame Code sessions",
        f"go_run_id    : {run.get('go_run_id', '')}",
        f"status       : {run.get('status', '')}",
        f"requirement  : {run.get('requirement', '')}",
        "",
        "Sessions",
    ]
    for session in sessions:
        targets = ", ".join(str(t) for t in session.get("targets", [])) or "(project scope)"
        changed = ", ".join(str(t) for t in session.get("changed_files", []))
        lines.extend([
            f"- {session.get('session_id', '')} provider={session.get('provider', '')} status={session.get('status', '')}",
            f"  agent_id    : {session.get('agent_id', '')}",
            f"  role        : {session.get('agent_role', '')}",
            f"  task_spec   : {session.get('task_spec', '')}",
            f"  targets     : {targets}",
        ])
        if changed:
            lines.append(f"  changed     : {changed}")
    return "\n".join(lines) + "\n"


def cmd_code_execute(*, prog: str = "devframe code execute") -> int:
    import argparse

    from .backup_guard import default_runtime_dir
    from .go_dispatch import execute_go_run, render_go_dispatch_text

    parser = argparse.ArgumentParser(prog=prog)
    parser.add_argument("run_id", nargs="?", default="latest", help="prepared go-run id to execute, or latest")
    parser.add_argument("--runtime-dir", default=None, help="Local runtime directory for code session state")
    parser.add_argument("--timeout", type=int, default=900, help="Per-worker timeout in seconds")
    parser.add_argument("--rerun-passed", action="store_true", help="Run agents even if their previous worker status passed")
    args = parser.parse_args(sys.argv[3:])

    runtime_dir = Path(args.runtime_dir).resolve() if args.runtime_dir else default_runtime_dir()
    try:
        result = execute_go_run(
            runtime_dir,
            args.run_id,
            timeout_seconds=args.timeout,
            rerun_passed=args.rerun_passed,
        )
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print("DevFrame Code execute")
    print("Tool shape   : reusing prepared coding-agent packets")
    print("Backend      : existing /go run packets")
    print("Token mode   : reuse prepared packets; skipped passed agents unless --rerun-passed")
    print("")
    print(render_go_dispatch_text(result), end="")
    return 0 if result.status in {"queued", "passed"} else 1


def cmd_code_workers(*, prog: str = "devframe code workers") -> int:
    import argparse

    parser = argparse.ArgumentParser(prog=prog)
    parser.add_argument("--format", choices=["text", "json"], default="text", help="Output format")
    args = parser.parse_args(sys.argv[3:])
    workers = _coding_worker_statuses()
    if args.format == "json":
        print(json.dumps({"workers": workers}, indent=2, ensure_ascii=False))
    else:
        print(_render_coding_worker_statuses(workers))
    return 0


def _coding_worker_statuses() -> list[dict[str, object]]:
    profiles = [
        {
            "name": "opencode",
            "kind": "built-in",
            "command": "opencode",
            "usage": "--worker opencode",
            "notes": "Default low-cost worker profile.",
        },
        {
            "name": "t3code",
            "kind": "custom",
            "command": "t3code",
            "usage": "--command t3code <args...>",
            "notes": "Custom command path; confirm its non-interactive syntax before --execute.",
        },
    ]
    statuses: list[dict[str, object]] = []
    for profile in profiles:
        command = str(profile["command"])
        path = shutil.which(command) or ""
        statuses.append({
            **profile,
            "available": bool(path),
            "path": path,
        })
    return statuses


def _render_coding_worker_statuses(workers: list[dict[str, object]]) -> str:
    lines = [
        "DevFrame Code workers",
        "Token mode   : status-only; no packets are created and no workers run",
        "",
        "Workers",
    ]
    for worker in workers:
        status = "ready" if worker.get("available") else "missing"
        path = str(worker.get("path") or "-")
        lines.extend([
            f"- {worker.get('name')} [{worker.get('kind')}] {status}",
            f"  command: {worker.get('command')}",
            f"  path   : {path}",
            f"  use    : devframe code \"<goal>\" {worker.get('usage')} --preview",
            f"  note   : {worker.get('notes')}",
        ])
    return "\n".join(lines) + "\n"


def _resolve_code_goal(goal: str | None, prompt_file: str | None) -> str:
    if goal and prompt_file:
        raise ValueError("pass either a positional goal or --prompt-file, not both")
    if goal:
        return goal.strip()
    if prompt_file:
        try:
            return Path(prompt_file).read_text(encoding="utf-8").strip()
        except OSError as exc:
            raise ValueError(f"unable to read --prompt-file: {exc}") from exc
    if not sys.stdin.isatty():
        return sys.stdin.read().strip()
    return input("Goal: ").strip()


def _load_go_run_status(runtime_dir: Path, run_id: str) -> dict:
    base = runtime_dir / "go-runs"
    if not base.exists():
        raise ValueError(f"no go runs found in {runtime_dir}")
    if run_id == "latest":
        runs = [_read_go_run_json(path) for path in base.glob("*/go-run.json")]
        runs = [run for run in runs if run]
        if not runs:
            raise ValueError(f"no go runs found in {runtime_dir}")
        return sorted(runs, key=lambda run: str(run.get("created_at", "")))[-1]
    path = base / run_id / "go-run.json"
    if not path.exists():
        raise ValueError(f"go run not found: {run_id}")
    run = _read_go_run_json(path)
    if not run:
        raise ValueError(f"go run metadata is unreadable: {path}")
    return run


def _read_go_run_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _render_go_run_status(run: dict) -> str:
    lines = [
        "DevFrame Code status",
        f"go_run_id    : {run.get('go_run_id', '')}",
        f"status       : {run.get('status', '')}",
        f"execute      : {run.get('execute', False)}",
        f"project_root : {run.get('project_root', '')}",
        f"runtime_dir  : {run.get('runtime_dir', '')}",
        f"metadata     : {run.get('metadata_path', '')}",
        f"requirement  : {run.get('requirement', '')}",
    ]
    methodology = run.get("methodology")
    if isinstance(methodology, dict):
        title = str(methodology.get("title") or methodology.get("skill_id") or "unknown")
        lines.append(f"methodology   : {title}")
    lines.extend([
        "",
        "Agents",
    ])
    agents = run.get("agents", [])
    for agent in agents:
        worker_status = agent.get("worker_status") or "pending"
        lines.append(
            f"- {agent.get('agent_id', '')} shard={agent.get('shard_index', 0)}/{agent.get('shard_count', 0)} "
            f"status={agent.get('status', '')} worker={worker_status}"
        )
        targets = _metadata_strings(agent.get("targets"))
        if targets:
            lines.append(f"  targets: {', '.join(targets)}")
        changed_files = _metadata_strings(agent.get("changed_files"))
        if changed_files:
            lines.append(f"  changed: {', '.join(changed_files)}")
        if agent.get("report_path"):
            lines.append(f"  report : {agent.get('report_path')}")
    if not agents:
        lines.append("- (no agents)")
    return "\n".join(lines) + "\n"


def _metadata_strings(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value]
    if value:
        return [str(value)]
    return []


def _render_coding_preview(
    *,
    entrypoint: str,
    project_path: str | Path,
    goal: str,
    targets: list[str],
    agents: int,
    execute: bool,
    runtime_dir: str | Path | None,
    worker_command: list[str] | None,
    worker: str,
    model: str,
    opencode_agent: str,
    build_worker_command,
    describe_worker,
    render_worker_command,
    split_targets,
    estimate_target_bytes,
    methodology: dict | None = None,
) -> str:
    from .backup_guard import default_runtime_dir

    project_root = Path(project_path).resolve()
    shards = split_targets(project_root, targets, agents)
    target_sizes = {target: estimate_target_bytes(project_root, target) for target in targets}
    runtime_root = Path(runtime_dir).resolve() if runtime_dir else default_runtime_dir()
    worker_label = describe_worker(
        worker_command=worker_command,
        worker=worker,
        model=model,
        opencode_agent=opencode_agent,
    )
    lines = [
        "DevFrame coding preview",
        f"entrypoint   : {entrypoint}",
        f"project_root : {Path(project_path).resolve()}",
        f"runtime_dir  : {runtime_root}",
        f"goal         : {goal}",
    ]
    if methodology:
        title = str(methodology.get("title") or methodology.get("skill_id") or "unknown")
        lines.append(f"methodology  : {title}")
    lines.extend([
        f"execute      : {execute}",
        f"agents       : {agents}",
        f"targets      : {len(targets)}",
        f"target_bytes : {sum(target_sizes.values())}",
        f"worker       : {worker_label}",
        "",
        "Shards",
    ])
    for index, shard_targets in enumerate(shards, start=1):
        command = build_worker_command(
            worker_command=worker_command,
            worker=worker,
            model=model,
            opencode_agent=opencode_agent,
            shard_number=index,
            shard_count=agents,
        )
        shard_bytes = sum(target_sizes.get(target, 0) for target in shard_targets)
        lines.append(f"- coding-agent-{index} shard={index}/{agents} bytes={shard_bytes}")
        if shard_targets:
            lines.extend(f"  - {target}" for target in shard_targets)
        else:
            lines.append("  - (project scope)")
        lines.append(f"  command: {render_worker_command(command)}")
    lines.extend([
        "",
        "No packets were created. Re-run without --preview to prepare dispatch packets and rdgoal worker commands.",
    ])
    return "\n".join(lines) + "\n"


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


def cmd_sessions() -> int:
    import argparse

    from .backup_guard import default_runtime_dir
    from .visual_state import (
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


def cmd_web_ai_import(*, prog: str = "devframe web-ai import") -> int:
    import argparse

    from .backup_guard import default_runtime_dir
    from .visual_state import validate_web_ai_session_summary

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

    from .backup_guard import default_runtime_dir
    from .chrome_binding_probe import (
        ChromeBindingError,
        build_chrome_chatgpt_session_summary,
        render_chrome_binding_text,
    )
    from .visual_state import validate_web_ai_session_summary

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


def cmd_web_ai_submit_review(*, prog: str = "devframe web-ai submit-review") -> int:
    import argparse

    from .backup_guard import default_runtime_dir
    from .playwright_bridge import BridgeConfig, BridgeMode, health_check as bridge_health, submit_via_bridge, _read_prompt_text
    from .submission_result import SubmissionRequest

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


def cmd_web_ai_record_mcp_result(*, prog: str = "devframe web-ai record-mcp-result") -> int:
    import argparse

    from .backup_guard import default_runtime_dir
    from .web_ai_mcp_recorder import record_mcp_result

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

    from .backup_guard import default_runtime_dir
    from .web_ai_mcp_recorder import record_task_intake

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

    from .backup_guard import default_runtime_dir
    from .web_ai_mcp_recorder import import_task_intakes

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

    from .go_dispatch import DEFAULT_OPENCODE_AGENT
    from .web_ai_mcp_recorder import dispatch_task_intakes

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


def cmd_web_ai_probe(*, prog: str = "devframe web-ai probe") -> int:
    import argparse

    from .provider_binding_probe import (
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

    from .mcp_live_probe import (
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
        from .backup_guard import default_runtime_dir
        from .visual_state import validate_web_ai_session_summary

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


def cmd_client_doctor(*, prog: str = "devframe client doctor") -> int:
    import argparse

    parser = argparse.ArgumentParser(prog=prog)
    parser.add_argument("--runtime-dir", default=None, help="Local devframe runtime directory")
    parser.add_argument("--t3-root", default=None, help="T3 Code checkout root")
    parser.add_argument("--host", default="127.0.0.1", help="Expected dashboard bind host")
    parser.add_argument("--port", type=int, default=8765, help="Expected dashboard bind port")
    parser.add_argument("--lang", choices=["en", "zh-CN"], default="zh-CN", help="Expected dashboard language")
    parser.add_argument("--format", choices=["text", "json"], default="text", help="Doctor output format")
    parser.add_argument("--force", action="store_true", help="Allow overwriting existing T3 bridge files")
    parser.add_argument("--allow-remote", action="store_true", help="Allow binding to a non-loopback host")
    parser.add_argument("--cdp-endpoint", default=None, help="Loopback Electron/T3 CDP endpoint for renderer state probing (e.g. http://127.0.0.1:9222)")
    args = parser.parse_args(sys.argv[3:])

    from .client_launcher import check_client_readiness, render_client_readiness_text

    try:
        result = check_client_readiness(
            args.runtime_dir,
            t3_root=args.t3_root,
            host=args.host,
            port=args.port,
            lang=args.lang,
            force=args.force,
            allow_remote=args.allow_remote,
            cdp_endpoint=args.cdp_endpoint,
        )
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    if args.format == "json":
        print(json.dumps(result, indent=2, ensure_ascii=True))
    else:
        print(render_client_readiness_text(result), end="")
    return 0 if result.get("status") in {"pass", "pass-with-warnings"} else 1


def cmd_client() -> int:
    import argparse

    raw_args = sys.argv[2:]
    if _wants_help(raw_args[:1]):
        print(CLIENT_USAGE)
        return 0

    subcommand = "serve"
    if raw_args and raw_args[0] in {"serve", "plan", "bridge", "t3desktop", "smoke", "doctor"}:
        subcommand = raw_args[0]
        raw_args = raw_args[1:]
    elif raw_args and not raw_args[0].startswith("-"):
        print(f"Unknown client subcommand: {raw_args[0]}")
        print(CLIENT_USAGE)
        return 1

    from .client_launcher import (
        build_client_launch_plan,
        render_client_launch_plan_json,
        render_client_launch_plan_text,
        serve_local_agent_client,
        serve_t3_desktop_client,
    )
    from .t3_bridge_bundle import (
        build_t3_bridge_bundle,
        install_t3_bridge_bundle,
        render_t3_bridge_bundle_json,
        render_t3_bridge_bundle_text,
        write_t3_bridge_bundle,
    )

    parser = argparse.ArgumentParser(prog=f"devframe client {subcommand}")
    parser.add_argument("--runtime-dir", default=None, help="Local devframe runtime directory")
    parser.add_argument("--paper-project", action="append", default=[], help="Paper iteration project directory to include")
    parser.add_argument("--host", default="127.0.0.1", help="Bind host")
    parser.add_argument("--port", type=int, default=8765, help="Bind port")
    parser.add_argument("--lang", choices=["en", "zh-CN"], default="zh-CN", help="Initial dashboard language")
    parser.add_argument("--refresh-seconds", type=int, default=5, help="Browser refresh interval; use 0 to disable")
    parser.add_argument("--dry-run", action="store_true", help="Print the launch plan without starting the server")
    parser.add_argument("--format", choices=["text", "json"], default="text", help="Plan output format for --dry-run or plan")
    parser.add_argument("--open", action="store_true", help="Open the local client URL in the default browser")
    parser.add_argument("--allow-remote", action="store_true", help="Allow binding to a non-loopback host")
    parser.add_argument("--output", default=None, help="Write a standalone T3 bridge bundle directory")
    parser.add_argument("--t3-root", default=None, help="Install bridge files into a local T3 Code checkout")
    parser.add_argument("--force", action="store_true", help="Overwrite existing generated bridge files")
    parser.add_argument("--cdp-endpoint", default=None, help="Loopback CDP endpoint for renderer state probing")
    args = parser.parse_args(raw_args)

    if not args.allow_remote and not _is_loopback_host(args.host):
        print("ERROR: client exposes local runtime paths; use --allow-remote to bind outside loopback.")
        return 1

    if subcommand == "bridge":
        plan = build_client_launch_plan(
            args.runtime_dir,
            host=args.host,
            port=args.port,
            lang=args.lang,
            paper_project_dirs=args.paper_project,
        )
        bundle = build_t3_bridge_bundle(plan)
        written_paths: list[Path] = []
        try:
            if args.output:
                written_paths.extend(write_t3_bridge_bundle(args.output, bundle))
            if args.t3_root:
                written_paths.extend(install_t3_bridge_bundle(args.t3_root, bundle, force=args.force))
        except (FileExistsError, ValueError) as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 2
        if args.format == "json":
            print(render_t3_bridge_bundle_json(bundle))
        else:
            print(render_t3_bridge_bundle_text(bundle), end="")
            if written_paths:
                for path in written_paths:
                    print(f"wrote       : {path}")
            else:
                print("No files written; pass --output or --t3-root to materialize the bridge.")
        return 0

    if subcommand == "t3desktop":
        return serve_t3_desktop_client(
            args.runtime_dir,
            t3_root=args.t3_root,
            host=args.host,
            port=args.port,
            lang=args.lang,
            paper_project_dirs=args.paper_project,
            force=args.force,
            open_browser=args.open,
            refresh_seconds=args.refresh_seconds,
        )

    if subcommand == "doctor":
        return cmd_client_doctor()

    if subcommand == "smoke":
        parser = argparse.ArgumentParser(prog="devframe client smoke")
        parser.add_argument("--runtime-dir", default=None, help="Local devframe runtime directory")
        parser.add_argument("--paper-project", action="append", default=[], help="Paper iteration project directory to include")
        parser.add_argument("--host", default="127.0.0.1", help="Bind host")
        parser.add_argument("--port", type=int, default=0, help="Bind port; 0 for auto-selection")
        parser.add_argument("--lang", choices=["en", "zh-CN"], default="zh-CN", help="Initial dashboard language")
        parser.add_argument("--format", choices=["text", "json"], default="text", help="Smoke output format")
        parser.add_argument("--t3-root", default=None, help="Install bridge files into a local T3 Code checkout")
        parser.add_argument("--force", action="store_true", help="Overwrite existing generated bridge files")
        parser.add_argument("--allow-remote", action="store_true", help="Allow binding to a non-loopback host")
        args = parser.parse_args(raw_args)

        if not args.allow_remote and not _is_loopback_host(args.host):
            print("ERROR: client exposes local runtime paths; use --allow-remote to bind outside loopback.")
            return 1

        from .client_launcher import smoke_local_agent_client
        return smoke_local_agent_client(
            args.runtime_dir,
            host=args.host,
            port=args.port,
            lang=args.lang,
            paper_project_dirs=args.paper_project,
            output_format=args.format,
            t3_root=args.t3_root,
            force=args.force,
        )

    if subcommand == "plan" or args.dry_run:
        plan = build_client_launch_plan(
            args.runtime_dir,
            host=args.host,
            port=args.port,
            lang=args.lang,
            paper_project_dirs=args.paper_project,
        )
        if args.format == "json":
            print(render_client_launch_plan_json(plan))
        else:
            print(render_client_launch_plan_text(plan), end="")
        return 0

    serve_local_agent_client(
        args.runtime_dir,
        host=args.host,
        port=args.port,
        refresh_seconds=args.refresh_seconds,
        lang=args.lang,
        paper_project_dirs=args.paper_project,
        open_browser=args.open,
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
        if len(sys.argv) > 2 and sys.argv[2] == "workers":
            if _wants_help(sys.argv[3:]):
                print(CODE_WORKERS_USAGE)
                return 0
            return cmd_code_workers(prog="devframe code workers")
        if len(sys.argv) > 2 and sys.argv[2] == "status":
            if _wants_help(sys.argv[3:]):
                print(CODE_STATUS_USAGE)
                return 0
            return cmd_code_status(prog="devframe code status")
        if len(sys.argv) > 2 and sys.argv[2] == "execute":
            if _wants_help(sys.argv[3:]):
                print(CODE_EXECUTE_USAGE)
                return 0
            return cmd_code_execute(prog="devframe code execute")
        if len(sys.argv) > 2 and sys.argv[2] == "session":
            if _wants_help(sys.argv[3:]):
                print(SESSION_USAGE)
                return 0
            return cmd_code_session(prog="devframe code session")
        if _wants_help(sys.argv[2:]):
            print(CODE_USAGE)
            return 0
        return cmd_code()

    if cmd == "go":
        if len(sys.argv) > 2 and sys.argv[2] == "workers":
            if _wants_help(sys.argv[3:]):
                print(CODE_WORKERS_USAGE.replace("devframe code", "devframe go"))
                return 0
            return cmd_code_workers(prog="devframe go workers")
        if len(sys.argv) > 2 and sys.argv[2] == "status":
            if _wants_help(sys.argv[3:]):
                print(CODE_STATUS_USAGE.replace("devframe code", "devframe go"))
                return 0
            return cmd_code_status(prog="devframe go status")
        if len(sys.argv) > 2 and sys.argv[2] == "execute":
            if _wants_help(sys.argv[3:]):
                print(CODE_EXECUTE_USAGE.replace("devframe code", "devframe go"))
                return 0
            return cmd_code_execute(prog="devframe go execute")
        if _wants_help(sys.argv[2:]):
            print(GO_USAGE)
            return 0
        return cmd_go()

    if cmd == "atgo":
        if _wants_help(sys.argv[2:]):
            print(ATGO_USAGE)
            return 0
        return cmd_atgo()

    if cmd == "visual-state":
        return cmd_visual_state()

    if cmd == "actions":
        return cmd_actions()

    if cmd == "sessions":
        if _wants_help(sys.argv[2:]):
            print(SESSIONS_USAGE)
            return 0
        return cmd_sessions()

    if cmd == "client":
        return cmd_client()

    if cmd == "web-ai":
        if _wants_help(sys.argv[2:3]):
            print(WEB_AI_IMPORT_USAGE)
            print(WEB_AI_PROBE_USAGE)
            print(WEB_AI_LIVE_CHECK_USAGE)
            print(WEB_AI_BIND_CHROME_USAGE)
            print(WEB_AI_IMPORT_TASK_INTAKES_USAGE)
            return 0
        if len(sys.argv) > 2 and sys.argv[2] == "import":
            if _wants_help(sys.argv[3:]):
                print(WEB_AI_IMPORT_USAGE)
                return 0
            return cmd_web_ai_import(prog="devframe web-ai import")
        if len(sys.argv) > 2 and sys.argv[2] == "probe":
            if _wants_help(sys.argv[3:]):
                print(WEB_AI_PROBE_USAGE)
                return 0
            return cmd_web_ai_probe(prog="devframe web-ai probe")
        if len(sys.argv) > 2 and sys.argv[2] == "live-check":
            if _wants_help(sys.argv[3:]):
                print(WEB_AI_LIVE_CHECK_USAGE)
                return 0
            return cmd_web_ai_live_check(prog="devframe web-ai live-check")
        if len(sys.argv) > 2 and sys.argv[2] == "bind-chrome":
            if _wants_help(sys.argv[3:]):
                print(WEB_AI_BIND_CHROME_USAGE)
                return 0
            return cmd_web_ai_bind_chrome(prog="devframe web-ai bind-chrome")
        if len(sys.argv) > 2 and sys.argv[2] == "submit-review":
            if _wants_help(sys.argv[3:]):
                print(WEB_AI_SUBMIT_REVIEW_USAGE)
                return 0
            return cmd_web_ai_submit_review(prog="devframe web-ai submit-review")
        if len(sys.argv) > 2 and sys.argv[2] == "record-mcp-result":
            if _wants_help(sys.argv[3:]):
                print(WEB_AI_RECORD_MCP_RESULT_USAGE)
                return 0
            return cmd_web_ai_record_mcp_result(prog="devframe web-ai record-mcp-result")
        if len(sys.argv) > 2 and sys.argv[2] == "record-task-intake":
            if _wants_help(sys.argv[3:]):
                print(WEB_AI_RECORD_TASK_INTAKE_USAGE)
                return 0
            return cmd_web_ai_record_task_intake(prog="devframe web-ai record-task-intake")
        if len(sys.argv) > 2 and sys.argv[2] == "import-task-intakes":
            if _wants_help(sys.argv[3:]):
                print(WEB_AI_IMPORT_TASK_INTAKES_USAGE)
                return 0
            return cmd_web_ai_import_task_intakes(prog="devframe web-ai import-task-intakes")
        if len(sys.argv) > 2 and sys.argv[2] == "dispatch-task-intakes":
            if _wants_help(sys.argv[3:]):
                print(WEB_AI_DISPATCH_TASK_INTAKES_USAGE)
                return 0
            return cmd_web_ai_dispatch_task_intakes(prog="devframe web-ai dispatch-task-intakes")
        print(f"Unknown web-ai subcommand: {sys.argv[2] if len(sys.argv) > 2 else ''}")
        return 1

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
