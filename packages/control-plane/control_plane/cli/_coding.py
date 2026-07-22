"""DevFrame coding-agent commands: code, go, atgo, and their helpers."""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from ..coding_dispatch import resolve_agent_count, resolve_coding_targets
from ._usage import CODE_USAGE


FINALIZER_REQUIRED_FILES = [
    "diff.patch",
    "test-output.md",
    "safety-report.json",
    "chain-evidence.json",
    "review.md",
    "review.yaml",
]


def cmd_go() -> int:
    import argparse

    from ..go_dispatch import (
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
    parser.add_argument("--model-provider", default=None, help="Model source behind OpenCode: opencode-api | local-ollama | web-chatgpt-shim. See 'devframe code providers'")
    parser.add_argument("--opencode-agent", default=DEFAULT_OPENCODE_AGENT, help="OpenCode agent name")
    parser.add_argument(
        "--driver",
        choices=["command", "acp"],
        default="command",
        help="Executor driver: command (default CLI worker) or acp (governed live ACP session)",
    )
    parser.add_argument(
        "--isolate",
        action="store_true",
        help="Run each agent in its own git worktree (opt-in; default off, byte-identical when unused)",
    )
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
            model_provider=args.model_provider,
            opencode_agent=args.opencode_agent,
            timeout_seconds=args.timeout,
            isolate=args.isolate,
            driver=args.driver,
        )
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    print(render_go_dispatch_text(result), end="")
    return 0 if result.status in {"queued", "passed"} else 1


def cmd_atgo() -> int:
    import argparse

    from ..backup_guard import default_runtime_dir
    from ..go_dispatch import resolve_methodology, run_go_dispatch

    parser = argparse.ArgumentParser(prog="devframe atgo")
    parser.add_argument("goal", help="Coding goal for the @go evidence + coding dispatch entrypoint")
    parser.add_argument("--project", default=".", help="Project/repository root. Defaults to the current directory")
    parser.add_argument("--runtime-dir", default=None, help="Local runtime directory for atgo evidence and dispatch state")
    parser.add_argument("--target", action="append", default=[], help="Target file or directory. May be repeated")
    parser.add_argument("--execute", action="store_true", help="Execute the prepared coding run after creating evidence")
    parser.add_argument(
        "--auto-finalize",
        action="store_true",
        help="After --execute, run the evidence finalizer only if required review evidence already exists",
    )
    args = parser.parse_args(sys.argv[2:])
    if args.auto_finalize and not args.execute:
        print("ERROR: --auto-finalize requires --execute", file=sys.stderr)
        return 2

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
            "- **Operation**: atgo coding shard 1/1",
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
    finalize_command_args = _go_finalize_command_args(evidence_dir, runtime_root)
    finalize_command = _render_go_finalize_command(evidence_dir, runtime_root)
    chain_evidence = {
        "run_id": result.go_run_id,
        "project_id": result.project_id or project_root.name,
        "executor_id": "opencode",
        "mode": "prepare",
        "planner": None,
        "task": str(task_spec_path),
        "methodology": methodology,
        "next_commands": {
            "finalize": {
                "command": finalize_command,
                "command_args": finalize_command_args,
                "cwd": str(project_root),
                "authority": "guidance_only",
                "creates_acceptance": False,
                "requires_independent_review": True,
                "manual": True,
            },
        },
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
    print("Next")
    print(f"Inspect   : devframe code status {result.go_run_id} --runtime-dir {runtime_root}")
    print(f"Resume    : devframe code execute {result.go_run_id} --runtime-dir {runtime_root}")
    print(f"Review    : devframe actions --runtime-dir {runtime_root}")
    print(f"Finalize  : {finalize_command}")

    if args.execute:
        from ..backup_guard import default_runtime_dir
        from ..go_dispatch import execute_go_run, render_go_dispatch_text
        try:
            exec_result = execute_go_run(runtime_root, result.go_run_id, timeout_seconds=900)
        except ValueError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 1
        print("")
        print("DevFrame @go execute")
        print(render_go_dispatch_text(exec_result), end="")
        finalize_rc = None
        if args.auto_finalize:
            finalize_rc = _maybe_auto_finalize_evidence_dir(
                evidence_dir=evidence_dir,
                runtime_root=runtime_root,
                project_root=project_root,
            )
        if finalize_rc is not None and finalize_rc != 0:
            return 1
        return 0 if exec_result.status in {"queued", "passed"} else 1

    return 0


def _maybe_auto_finalize_evidence_dir(
    *,
    evidence_dir: Path,
    runtime_root: Path,
    project_root: Path,
    label: str = "Auto-finalize",
) -> int | None:
    missing = [name for name in FINALIZER_REQUIRED_FILES if not (evidence_dir / name).exists()]
    if missing:
        print("")
        print(f"{label}: skipped; missing required review evidence: {', '.join(missing)}")
        print(f"Finalize     : {_render_go_finalize_command(evidence_dir, runtime_root)}")
        return None
    script = _go_evidence_script()
    if not script.exists():
        print("")
        print(f"{label}: failed; missing finalizer script: {script}", file=sys.stderr)
        return 1
    proc = subprocess.run(
        [
            sys.executable,
            str(script),
            "finalize",
            str(evidence_dir),
            "--team-runtime-dir",
            str(runtime_root),
        ],
        cwd=str(project_root),
        capture_output=True,
        text=True,
        check=False,
    )
    print("")
    print(f"{label}: {_render_go_finalize_command(evidence_dir, runtime_root)}")
    if proc.stdout:
        print(proc.stdout, end="" if proc.stdout.endswith("\n") else "\n")
    if proc.stderr:
        print(proc.stderr, end="" if proc.stderr.endswith("\n") else "\n", file=sys.stderr)
    return proc.returncode


def _write_json_file(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _unique_strings(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            result.append(value)
    return result


def _prepare_evidence_only(*, evidence_dir: Path, runtime_root: Path, result) -> None:
    from ..evidence_gate import EvidenceGateResult, REQUIRED_FILES, build_evidence_manifest

    evidence_dir.mkdir(parents=True, exist_ok=True)
    task_spec_path = evidence_dir / "task-spec.md"
    if not task_spec_path.exists():
        task_spec_path.write_text(
            f"# Prepare-Only Evidence Draft\n\n- go_run_id: {result.go_run_id}\n- project_id: {result.project_id}\n",
            encoding="utf-8",
        )
    chain_evidence = {
        "run_id": result.go_run_id,
        "executor_id": "devframe-go-execute",
        "mode": "prepare_evidence",
        "planner": "devframe code execute",
        "task": str(task_spec_path),
        "methodology": result.methodology,
        "evidence_files": _unique_strings([
            "diff.patch",
            "test-output.md",
            "safety-report.json",
            "chain-evidence.json",
            "review.md",
            "review.yaml",
        ]),
        "timestamps": {
            "created_at": datetime.now(timezone.utc).isoformat(),
        },
        "next_commands": {
            "finalize": {
                "command": _render_go_finalize_command(evidence_dir, runtime_root),
                "command_args": _go_finalize_command_args(evidence_dir, runtime_root),
                "authority": "guidance_only",
                "manual": True,
                "creates_acceptance": False,
                "requires_independent_review": True,
            }
        },
    }
    _write_json_file(evidence_dir / "chain-evidence.json", chain_evidence)
    gate_result = EvidenceGateResult(
        status="blocked",
        reason="prepare-only evidence draft requires independent review before finalization",
        review={},
        chain_evidence=chain_evidence,
        missing_files=[name for name in REQUIRED_FILES if not (evidence_dir / name).exists()],
        missing_inputs=[],
    )
    manifest = build_evidence_manifest(evidence_dir, gate_result)
    manifest["verdict_eligibility"]["status"] = "needs_more_evidence"
    manifest["verdict_eligibility"]["reasons"] = [gate_result.reason]
    manifest["verdict_eligibility"]["blocking_signals"] = [gate_result.reason]
    _write_json_file(evidence_dir / "evidence-manifest.json", manifest)


def _go_evidence_script() -> Path:
    repo_candidate = Path(__file__).resolve().parents[4] / "tools" / "go_evidence.py"
    if repo_candidate.exists():
        return repo_candidate
    return Path.cwd() / "tools" / "go_evidence.py"


def _go_finalize_command_args(evidence_dir: Path, runtime_root: Path) -> list[str]:
    return [
        "tools/go_evidence.py",
        "finalize",
        str(evidence_dir),
        "--team-runtime-dir",
        str(runtime_root),
    ]


def _render_go_finalize_command(evidence_dir: Path, runtime_root: Path) -> str:
    from ..go_dispatch import render_command

    return render_command(_go_finalize_command_args(evidence_dir, runtime_root))


def cmd_code() -> int:
    import argparse

    from ..go_dispatch import (
        DEFAULT_GO_WORKER,
        DEFAULT_OPENCODE_AGENT,
        GO_WORKERS,
        _resolve_workflow_canary_context,
        build_go_worker_command,
        describe_go_worker,
        estimate_target_bytes,
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
    parser.add_argument(
        "--workflow-canary",
        action="store_true",
        help=(
            "Opt in only for @go read: run canary-only pre:intent/post:evidence "
            "with no worker or ACP"
        ),
    )
    parser.add_argument("--timeout", type=int, default=900, help="Per-worker timeout in seconds")
    parser.add_argument("--worker", choices=GO_WORKERS, default=DEFAULT_GO_WORKER, help="Built-in coding worker profile")
    parser.add_argument("--model", default=None, help="Model id for the selected worker; opencode defaults to stepfun/step-3.7-flash")
    parser.add_argument("--model-provider", default=None, help="Model source behind OpenCode: opencode-api | local-ollama | web-chatgpt-shim. See 'devframe code providers'")
    parser.add_argument("--opencode-agent", default=DEFAULT_OPENCODE_AGENT, help="OpenCode agent name")
    parser.add_argument(
        "--driver",
        choices=["command", "acp"],
        default="command",
        help="Executor driver: command (default CLI worker) or acp (governed live ACP session)",
    )
    parser.add_argument(
        "--isolate",
        action="store_true",
        help="Run each agent in its own git worktree (opt-in; default off, byte-identical when unused)",
    )
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
    try:
        targets = resolve_coding_targets(args.project, args.target, changed=args.changed, since=args.since)
        agents = resolve_agent_count(args.agents, targets, max_agents=args.max_agents)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    workflow_canary = None
    if args.workflow_canary:
        try:
            canary_context = _resolve_workflow_canary_context(
                args.project,
                goal,
                runtime_dir=args.runtime_dir,
                agents=agents,
                targets=targets,
                worker_command=args.command or None,
                worker=args.worker,
                model=args.model,
                model_provider=args.model_provider,
                opencode_agent=args.opencode_agent,
                apply_rdinit=False,
                isolate=args.isolate,
                driver=args.driver,
                acp_command=None,
            )
        except ValueError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 2
        effective_goal = canary_context.requirement
        methodology = canary_context.methodology
        workflow_canary = canary_context.binding
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
            workflow_canary=workflow_canary,
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
            model_provider=args.model_provider,
            opencode_agent=args.opencode_agent,
            timeout_seconds=args.timeout,
            isolate=args.isolate,
            driver=args.driver,
            workflow_canary=args.workflow_canary,
        )
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    print("DevFrame Code session")
    print("Tool shape   : OpenCode-first local coding CLI")
    print("Backend      : /go concurrent coding-agent dispatch")
    print("Default mode : prepare first, inspect, then execute when you choose")
    print("")
    print(_render_code_dispatch_text(result), end="")
    return 0 if result.status in {"queued", "passed"} else 1


def cmd_code_status(*, prog: str = "devframe code status") -> int:
    import argparse

    from ..backup_guard import default_runtime_dir

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

    from ..backup_guard import default_runtime_dir

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
    methodology = run.get("methodology") if isinstance(run.get("methodology"), dict) else None
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
        session = {
            "session_id": session_id,
            "provider": provider,
            "agent_id": str(agent.get("agent_id", "")),
            "agent_role": "executor",
            "run_id": str(run.get("go_run_id", "")),
            "status": str(agent.get("worker_status") or agent.get("status") or "unknown"),
            "methodology": methodology,
            "task_spec": Path(task_spec_path).name if task_spec_path else "",
            "targets": agent.get("targets") or [],
            "changed_files": _public_changed_files(agent.get("changed_files") or []),
        }
        provider_session_id = str(agent.get("session_id", "")).strip()
        if provider_session_id:
            session["provider_session_id"] = provider_session_id
        model_provider = str(agent.get("model_provider", "")).strip()
        if model_provider:
            session["model_provider"] = model_provider
        input_tokens = int(agent.get("input_tokens", 0) or 0)
        output_tokens = int(agent.get("output_tokens", 0) or 0)
        total_tokens = int(agent.get("total_tokens", 0) or 0)
        if input_tokens or output_tokens or total_tokens:
            session["tokens"] = {
                "input": input_tokens,
                "output": output_tokens,
                "total": total_tokens,
            }
        cost_amount = float(agent.get("cost", 0.0) or 0.0)
        if cost_amount:
            session["cost"] = {"amount": cost_amount, "currency": "USD"}
        tool_calls = [
            {"name": str(call.get("name", "")), "target": str(call.get("target", ""))}
            for call in (agent.get("tool_calls") or [])
            if isinstance(call, dict) and call.get("name")
        ]
        if tool_calls:
            session["tool_calls"] = tool_calls
        sessions.append(session)
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


def _ui_status(value: object) -> str:
    status = str(value or "").strip().lower()
    if status in {"pass", "passed", "success", "completed", "complete", "executed", "review-pass", "verified"}:
        return "complete"
    if status in {"queued", "pending", "prepared", "running", "idle"}:
        return "prepared"
    return status


def _render_sessions(run: dict) -> str:
    sessions = _public_sessions(run)
    lines = [
        "DevFrame Code sessions",
        f"go_run_id    : {run.get('go_run_id', '')}",
        f"status       : {_ui_status(run.get('status', ''))}",
        f"requirement  : {run.get('requirement', '')}",
        "",
        "Sessions",
    ]
    for session in sessions:
        targets = ", ".join(str(t) for t in session.get("targets", [])) or "(project scope)"
        changed = ", ".join(str(t) for t in session.get("changed_files", []))
        methodology = session.get("methodology")
        lines.append(
            f"- {session.get('session_id', '')} provider={session.get('provider', '')} "
            f"status={_ui_status(session.get('status', ''))}"
        )
        lines.append(f"  agent_id    : {session.get('agent_id', '')}")
        lines.append(f"  role        : {session.get('agent_role', '')}")
        if isinstance(methodology, dict):
            lines.append(f"  methodology : {str((methodology or {}).get('title') or (methodology or {}).get('skill_id') or '')}")
        lines.append(f"  task_spec   : {session.get('task_spec', '')}")
        tokens = session.get("tokens")
        if isinstance(tokens, dict) and (tokens.get("total") or tokens.get("input") or tokens.get("output")):
            lines.append(
                f"  tokens      : in={tokens.get('input', 0)} out={tokens.get('output', 0)} total={tokens.get('total', 0)}"
            )
        cost = session.get("cost")
        if isinstance(cost, dict) and cost.get("amount"):
            lines.append(f"  cost        : {cost.get('amount')} {cost.get('currency', 'USD')}")
        tool_calls = session.get("tool_calls")
        if isinstance(tool_calls, list) and tool_calls:
            names = ", ".join(str(call.get("name", "")) for call in tool_calls if isinstance(call, dict))
            lines.append(f"  tools       : {names}")
        lines.append(f"  targets     : {targets}")
        if changed:
            lines.append(f"  changed     : {changed}")
    go_run_id = str(run.get("go_run_id", "")).strip()
    runtime_dir = str(run.get("runtime_dir", "")).strip()
    if go_run_id and runtime_dir:
        lines.extend([
            "",
            "Next",
            f"Inspect   : devframe code status {go_run_id} --runtime-dir {runtime_dir}",
            f"Resume    : devframe code execute {go_run_id} --runtime-dir {runtime_dir}",
            f"Control   : devframe dashboard serve --runtime-dir {runtime_dir}",
            f"Queue     : devframe actions --runtime-dir {runtime_dir}",
        ])
    compact = [line for line in lines if line != ""]
    return "\n".join(compact) + "\n"


def _render_code_dispatch_text(result) -> str:
    def _quote(value: object) -> str:
        text = str(value)
        if not text or any(ch.isspace() for ch in text) or any(ch in text for ch in ['"', "'", "&", "|"]):
            return '"' + text.replace('"', '\\"') + '"'
        return text

    def _summary(value: str) -> str:
        for line in value.splitlines():
            stripped = line.strip().lstrip("- ").replace("**", "")
            if stripped:
                return stripped
        return ""

    lines = [
        f"go_run_id    : {result.go_run_id}",
        f"status       : {result.status}",
        f"agents       : {len(result.agents)}",
        f"requirement  : {result.requirement}",
    ]
    if result.methodology:
        title = str(result.methodology.get("title") or result.methodology.get("skill_id") or "unknown")
        lines.append(f"methodology   : {title}")
    if result.workflow_canary:
        mode = str(result.workflow_canary.get("mode") or "unknown")
        status = str(result.workflow_canary.get("status") or "unknown")
        lines.append(f"workflow     : {mode} ({status})")
    lines.extend([
        "",
        "Agents",
    ])
    for agent in result.agents:
        worker_status = agent.worker_status or agent.status or "pending"
        lines.append(
            f"- {agent.agent_id} shard={agent.shard_index}/{agent.shard_count} status={worker_status}"
        )
        lines.append(f"  targets: {', '.join(agent.targets) if agent.targets else '(project scope)'}")
        if result.workflow_canary:
            lines.append("  run    : canary-only (no worker/ACP)")
        else:
            lines.append(
                f"  run    : {_render_code_worker_command(result.runtime_dir, agent)}"
            )
        if agent.report_path:
            lines.append(f"  report : {agent.report_path}")
        if agent.changed_files:
            lines.append(f"  changed: {', '.join(agent.changed_files)}")
        if agent.verification:
            lines.append(f"  evidence: {_summary(agent.verification)}")
    lines.extend([
        "",
        "Next",
        f"Inspect   : devframe code status {_quote(result.go_run_id)} --runtime-dir {_quote(result.runtime_dir)}",
        f"Resume    : devframe code execute {_quote(result.go_run_id)} --runtime-dir {_quote(result.runtime_dir)}",
        f"Control   : devframe dashboard serve --runtime-dir {_quote(result.runtime_dir)}",
        f"Queue     : devframe actions --runtime-dir {_quote(result.runtime_dir)}",
    ])
    return "\n".join(lines) + "\n"


def _render_code_worker_command(runtime_dir: str, agent) -> str:
    def _quote(value: object) -> str:
        text = str(value)
        if not text or any(ch.isspace() for ch in text) or any(ch in text for ch in ['"', "'", "&", "|"]):
            return '"' + text.replace('"', '\\"') + '"'
        return text

    command = " ".join(_quote(part) for part in list(agent.worker_command or []))
    return (
        f"rdgoal worker {_quote(agent.packet_dir)} "
        f"--runtime-dir {_quote(runtime_dir)} --command {command}"
    )


def cmd_code_execute(*, prog: str = "devframe code execute") -> int:
    import argparse

    from ..backup_guard import default_runtime_dir
    from ..go_dispatch import execute_go_run

    parser = argparse.ArgumentParser(prog=prog)
    parser.add_argument("run_id", nargs="?", default="latest", help="prepared go-run id to execute, or latest")
    parser.add_argument("--runtime-dir", default=None, help="Local runtime directory for code session state")
    parser.add_argument("--timeout", type=int, default=900, help="Per-worker timeout in seconds")
    parser.add_argument("--rerun-passed", action="store_true", help="Run agents even if their previous worker status passed")
    parser.add_argument(
        "--evidence-dir",
        default=None,
        help="Evidence directory to finalize after execution when --auto-finalize is explicitly set",
    )
    finalize_mode = parser.add_mutually_exclusive_group()
    finalize_mode.add_argument(
        "--auto-finalize",
        action="store_true",
        help="After execute, run the existing evidence finalizer only if the provided evidence dir already has independent review inputs",
    )
    finalize_mode.add_argument(
        "--prepare-evidence-dir",
        default=None,
        help="Write a prepare-only evidence draft after execution; does not create acceptance or final-ready state",
    )
    args = parser.parse_args(sys.argv[3:])
    if args.auto_finalize and not args.evidence_dir:
        print("ERROR: --auto-finalize requires --evidence-dir", file=sys.stderr)
        return 2
    if args.prepare_evidence_dir and (args.auto_finalize or args.evidence_dir):
        print("ERROR: --prepare-evidence-dir cannot be combined with --auto-finalize or --evidence-dir", file=sys.stderr)
        return 2

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
    print("Token mode   : resume a prepared run; skipped passed agents unless --rerun-passed")
    print("")
    print(_render_code_dispatch_text(result), end="")
    if args.prepare_evidence_dir:
        evidence_dir = Path(args.prepare_evidence_dir).resolve()
        _prepare_evidence_only(evidence_dir=evidence_dir, runtime_root=runtime_dir, result=result)
        print("")
        print(f"Prepare evidence: {evidence_dir}")
        print("Status          : draft; independent review required before finalization")
        print(f"Finalize        : {_render_go_finalize_command(evidence_dir, runtime_dir)}")
    finalize_rc = None
    if args.auto_finalize:
        finalize_rc = _maybe_auto_finalize_evidence_dir(
            evidence_dir=Path(args.evidence_dir).resolve(),
            runtime_root=runtime_dir,
            project_root=Path(result.project_root).resolve() if result.project_root else Path.cwd().resolve(),
        )
    if finalize_rc is not None and finalize_rc != 0:
        return 1
    return 0 if result.status in {"queued", "passed"} else 1


def cmd_code_providers(*, prog: str = "devframe code providers") -> int:
    import argparse

    from ..model_providers import list_model_providers, render_model_providers_text

    parser = argparse.ArgumentParser(prog=prog)
    parser.add_argument("--format", choices=["text", "json"], default="text", help="Output format")
    args = parser.parse_args(sys.argv[3:])
    providers = list_model_providers()
    if args.format == "json":
        print(json.dumps(
            {"providers": [provider.to_dict() for provider in providers]},
            indent=2,
            ensure_ascii=False,
        ))
    else:
        print(render_model_providers_text(providers))
    return 0


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
    status = _ui_status(run.get("status", ""))
    lines = [
        "DevFrame Code status",
        f"go_run_id    : {run.get('go_run_id', '')}",
        f"status       : {status}",
        f"agents       : {len(run.get('agents', []))}",
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
        worker_status = _ui_status(agent.get("worker_status") or "pending")
        agent_status = _ui_status(agent.get("status", ""))
        lines.append(
            f"- {agent.get('agent_id', '')} shard={agent.get('shard_index', 0)}/{agent.get('shard_count', 0)} "
            f"status={agent_status} worker={worker_status}"
        )
        targets = _metadata_strings(agent.get("targets"))
        if targets:
            lines.append(f"  targets: {', '.join(targets)}")
        changed_files = _metadata_strings(agent.get("changed_files"))
        if changed_files:
            lines.append(f"  changed: {', '.join(changed_files)}")
    if not agents:
        lines.append("- (no agents)")
    attention = _agent_attention_summary(agents)
    if attention:
        lines.extend(["", f"Needs attention: {attention}."])
    lines.extend(["", "Next", _status_recovery_guidance(status)])
    return "\n".join(lines) + "\n"


def _agent_attention_summary(agents: object) -> str:
    if not isinstance(agents, list):
        return ""
    summaries = []
    for agent in agents:
        if not isinstance(agent, dict):
            continue
        status = _ui_status(agent.get("worker_status") or agent.get("status") or "")
        if status in {"paused", "blocked", "failed"}:
            agent_id = str(agent.get("agent_id") or "").strip()
            if agent_id:
                summaries.append(f"{agent_id} ({status})")
    return ", ".join(summaries)


def _status_recovery_guidance(status: str) -> str:
    if status == "prepared":
        return "Ready to run: review the prepared work, then choose when to execute."
    if status in {"paused", "blocked", "failed"}:
        return "Needs attention: inspect the agent status and resolve the blocker before retrying."
    if status == "complete":
        return "Complete: review the result before starting new work."
    return "Needs attention: the run state is not recognized."


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
    workflow_canary: dict | None = None,
) -> str:
    from ..backup_guard import default_runtime_dir

    project_root = Path(project_path).resolve()
    runtime_root = Path(runtime_dir).resolve() if runtime_dir else default_runtime_dir()
    if workflow_canary:
        lines = [
            "DevFrame coding preview",
            f"entrypoint   : {entrypoint}",
            f"project_root : {project_root}",
            f"runtime_dir  : {runtime_root}",
            f"goal         : {goal}",
        ]
        if methodology:
            title = str(
                methodology.get("title")
                or methodology.get("skill_id")
                or "unknown"
            )
            lines.append(f"methodology  : {title}")
        lines.extend(
            [
                "workflow     : canary_only",
                f"execute      : {execute}",
                "agents       : 1",
                "targets      : 0",
                "target_bytes : 0",
                "worker       : none (canary-only; no command or ACP)",
                "",
                "Stages",
                "- pre:intent",
                "- post:evidence",
                "",
                "Next",
                "Prepare   : re-run without --preview to create a resumable coding run.",
                "Inspect   : use devframe code status after prepare.",
                "Resume    : use devframe code execute to consume draft-only canary evidence.",
            ]
        )
        return "\n".join(lines) + "\n"

    shards = split_targets(project_root, targets, agents)
    target_sizes = {target: estimate_target_bytes(project_root, target) for target in targets}
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
        "Next",
        "Prepare   : re-run without --preview to create a resumable coding run.",
        "Inspect   : use devframe code status after prepare.",
        "Resume    : use devframe code execute when you choose to spend worker tokens.",
    ])
    return "\n".join(lines) + "\n"


def cmd_workflow() -> int:
    """devframe workflow: run a recorded plan -> execute -> review coding workflow."""
    import argparse

    from ..workflow_engine import WorkflowEngine, render_workflow_result_text

    parser = argparse.ArgumentParser(prog="devframe workflow")
    parser.add_argument("goal", nargs="?", help="Coding goal for the workflow")
    parser.add_argument("--prompt-file", default=None, help="Read a multi-line goal from a file")
    parser.add_argument("--project", default=".", help="Project/repository root")
    parser.add_argument("--agents", default="2", help="Number of coding-agent shards, or auto")
    parser.add_argument("--max-agents", type=int, default=4, help="Maximum shards when --agents auto")
    parser.add_argument("--target", action="append", default=[], help="Target file or directory. May be repeated")
    parser.add_argument("--changed", action="store_true", help="Use changed git files as targets")
    parser.add_argument("--since", default=None, help="Use files changed since this git ref as targets")
    parser.add_argument("--runtime-dir", default=None, help="Local runtime directory for workflow state")
    parser.add_argument("--timeout", type=int, default=900, help="Per-worker timeout in seconds")
    parser.add_argument("--model", default=None, help="Model id for the executor")
    parser.add_argument("--model-provider", default=None, help="Model source behind OpenCode")
    parser.add_argument("--opencode-agent", default="build", help="OpenCode agent name")
    parser.add_argument("--isolate", action="store_true", help="Run each agent in its own git worktree")
    parser.add_argument(
        "--command",
        nargs=argparse.REMAINDER,
        default=[],
        help="Worker command for the execute phase. Omit to use opencode run.",
    )
    args = parser.parse_args(sys.argv[2:])

    try:
        goal = _resolve_code_goal(args.goal, args.prompt_file)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    if not goal:
        print("Usage: devframe workflow \"<goal>\" [--project .] [--target FILE]")
        return 2

    try:
        targets = resolve_coding_targets(args.project, args.target, changed=args.changed, since=args.since)
        agents = resolve_agent_count(args.agents, targets, max_agents=args.max_agents)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    engine = WorkflowEngine(runtime_dir=args.runtime_dir)
    try:
        result = engine.run_coding_workflow(
            args.project,
            goal,
            agents=agents,
            targets=targets,
            worker_command=args.command or None,
            model=args.model,
            model_provider=args.model_provider,
            opencode_agent=args.opencode_agent,
            timeout_seconds=args.timeout,
            isolate=args.isolate,
        )
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    print("DevFrame Workflow engine")
    print("Phases       : plan (coordinator) -> execute (executors) -> review (reviewer)")
    print("Recording    : real team events in the team runtime journal")
    print("")
    print(render_workflow_result_text(result), end="")
    return 0 if result.status in {"queued", "passed"} else 1
