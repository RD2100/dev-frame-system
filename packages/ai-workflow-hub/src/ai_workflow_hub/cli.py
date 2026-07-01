"""aihub CLI -- Typer 命令行入口.

审计强化:
- doctor: OpenCode models 检查
- --run-tests flag: dry-run 下显式执行测试
- 使用 compile_graph 的 checkpointer (thread_id = run_id)
"""

from __future__ import annotations

import fnmatch
import hashlib
import json
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import typer
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

import yaml as _yaml

from .config_loader import (
    init_env,
    load_project_workflow_config,
    get_execution_policy,
    get_risk_policy,
    validate_execution_policy,
    _hub_dir,
)
from .model_config import get_model_for_risk
from .project_registry import list_projects, find_project, validate_project, add_project
from .run_governance import render_full_governance_cli, summarize_run_governance
from .task_queue import list_tasks, find_task, add_task
from .run_store import create_run_dir, save_run_file, save_run_json, list_runs, get_run_report
from .schemas import WorkflowState

app = typer.Typer(
    name="aihub",
    help="稳定优先的多项目 AI 自动化闭环开发系统",
    no_args_is_help=True,
)

console = Console()
err_console = Console(stderr=True)


# A75: Module-level pure JSON emitter — writes directly to console's file
# handle, bypassing Rich formatting (markup, highlight, soft-wrap, crop).
# Safe across environments (Windows, Linux, CI terminals).
# NOTE: target defaults to None and resolves at call time so that test
# patches of `ai_workflow_hub.cli.console` are respected.
def _emit_json(obj: Any, *, target: Console | None = None) -> None:
    _t = target if target is not None else console
    _t.file.write(json.dumps(obj, indent=2, ensure_ascii=False, default=str))
    _t.file.write("\n")


@app.command("opencode-slice0")
def opencode_slice0(
    model: str = typer.Option(
        "stepfun/step-3.7-flash",
        "--model",
        "-m",
        help="OpenCode model id for the probe.",
    ),
    output_dir: Optional[Path] = typer.Option(
        None,
        "--output-dir",
        "-o",
        help="Directory for slice0-report.json, stdout, stderr, and the temp git repo.",
    ),
    timeout: int = typer.Option(120, "--timeout", help="OpenCode run timeout in seconds."),
    as_json: bool = typer.Option(False, "--json", help="Print the full report as JSON."),
):
    """Run the Slice 0 OpenCode readiness probe."""

    from .opencode_slice0 import run_opencode_slice0_probe

    report = run_opencode_slice0_probe(
        model=model,
        output_dir=str(output_dir) if output_dir else None,
        timeout=timeout,
    )
    if as_json:
        _emit_json(report)
        raise typer.Exit(0 if report.get("verdict") == "passed" else 1)

    verdict = report.get("verdict", "unknown")
    color = "green" if verdict == "passed" else "red"
    console.print(f"[bold {color}]OpenCode Slice 0: {verdict}[/bold {color}]")
    console.print(f"Report: {report.get('paths', {}).get('report', '')}")
    console.print(f"Workspace: {report.get('workspace', '')}")
    failed = report.get("failed_checks", [])
    if failed:
        console.print("Failed checks:")
        for name in failed:
            detail = report.get("checks", {}).get(name, {}).get("detail", "")
            console.print(f"  - {name}: {detail}")

    raise typer.Exit(0 if verdict == "passed" else 1)


@app.command("opencode-serve-slice1")
def opencode_serve_slice1(
    model: str = typer.Option(
        "stepfun/step-3.7-flash",
        "--model",
        "-m",
        help="OpenCode model id for the serve probe.",
    ),
    output_dir: Optional[Path] = typer.Option(
        None,
        "--output-dir",
        "-o",
        help="Directory for serve-slice1-report.json, event sample, logs, and temp git repo.",
    ),
    timeout: int = typer.Option(120, "--timeout", help="Serve prompt_async timeout in seconds."),
    as_json: bool = typer.Option(False, "--json", help="Print the full report as JSON."),
):
    """Run the Slice 1 OpenCode serve/prompt_async readiness probe."""

    from .opencode_serve_slice1 import run_opencode_serve_slice1_probe

    report = run_opencode_serve_slice1_probe(
        model=model,
        output_dir=str(output_dir) if output_dir else None,
        timeout=timeout,
    )
    if as_json:
        _emit_json(report)
        raise typer.Exit(0 if report.get("verdict") == "passed" else 1)

    verdict = report.get("verdict", "unknown")
    color = "green" if verdict == "passed" else ("yellow" if verdict == "partial" else "red")
    console.print(f"[bold {color}]OpenCode Serve Slice 1: {verdict}[/bold {color}]")
    partial_type = report.get("partial_type", "")
    if partial_type:
        console.print(f"Partial: {partial_type}")
    console.print(f"Report: {report.get('paths', {}).get('report', '')}")
    console.print(f"Workspace: {report.get('workspace', '')}")
    failed = report.get("failed_checks", [])
    if failed:
        console.print("Failed checks:")
        for name in failed:
            detail = report.get("checks", {}).get(name, {}).get("detail", "")
            console.print(f"  - {name}: {detail}")

    raise typer.Exit(0 if verdict == "passed" else 1)

# ============================================================
# project 命令
# ============================================================

project_app = typer.Typer(help="项目管理")
app.add_typer(project_app, name="project")

@project_app.command("list")
def project_list():
    init_env()
    projects = list_projects()
    if not projects:
        console.print("[yellow]projects.yaml 中没有项目[/yellow]")
        return

    table = Table(title="Registered Projects")
    table.add_column("ID", style="cyan")
    table.add_column("Name")
    table.add_column("Path")
    table.add_column("Priority")
    table.add_column("Enabled")

    for p in projects:
        table.add_row(
            p.get("id", ""),
            p.get("name", ""),
            p.get("path", ""),
            p.get("priority", "medium"),
            "Yes" if p.get("enabled", True) else "No",
        )

    console.print(table)

@project_app.command("validate")
def project_validate(project_id: str = typer.Option(..., "--project", "-p", help="项目 ID")):
    init_env()
    is_valid, messages = validate_project(project_id)

    console.print(f"\n[bold]Project: {project_id}[/bold]")
    console.print("-" * 40)

    for msg in messages:
        if msg.startswith("ERROR"):
            console.print(f"  [red]{msg}[/red]")
        elif msg.startswith("WARNING"):
            console.print(f"  [yellow]{msg}[/yellow]")
        else:
            console.print(f"  [dim]{msg}[/dim]")

    if is_valid:
        console.print(f"\n[green]Validation PASSED[/green]")
    else:
        console.print(f"\n[red]Validation FAILED -- {len([m for m in messages if m.startswith('ERROR')])} error(s)[/red]")

    raise typer.Exit(0 if is_valid else 1)

# ============================================================
# task 命令
# ============================================================

task_app = typer.Typer(help="任务管理")
app.add_typer(task_app, name="task")

@task_app.command("list")
def task_list(status: Optional[str] = typer.Option(None, "--status", "-s")):
    init_env()
    tasks = list_tasks(status)

    if not tasks:
        console.print("[yellow]没有任务.[/yellow]")
        return

    table = Table(title="Task Queue")
    table.add_column("ID", style="cyan")
    table.add_column("Title")
    table.add_column("Risk")
    table.add_column("Priority")
    table.add_column("Status")
    table.add_column("Last Run")

    for t in tasks:
        risk_style = {"low": "green", "medium": "yellow", "high": "red"}.get(t.get("risk", ""), "")
        status_style = {"queued": "dim", "running": "blue", "passed": "green", "failed": "red", "blocked": "red", "human_required": "yellow", "cancelled": "dim"}.get(t.get("status", ""), "")
        lr = t.get("last_run_id", "")
        table.add_row(
            t.get("id", ""),
            t.get("title", "")[:50],
            f"[{risk_style}]{t.get('risk', '')}[/{risk_style}]",
            t.get("priority", "normal"),
            f"[{status_style}]{t.get('status', '')}[/{status_style}]",
            lr[-16:] if lr else "-",
        )

    console.print(table)

@task_app.command("mark")
def task_mark(
    task_id: str = typer.Argument(..., help="任务 ID"),
    status: str = typer.Argument(..., help="状态: queued | cancelled | ..."),
    reason: str = typer.Option("", "--reason", "-r", help="阻塞原因"),
):
    """标记任务状态."""
    init_env()
    valid = ("queued", "cancelled", "blocked", "human_required")
    if status not in valid:
        console.print(f"[red]无效状态: {status}。允许: {', '.join(valid)}[/red]")
        raise typer.Exit(1)
    from .task_queue import mark_task_finished
    ok = mark_task_finished(task_id, status, blocked_reason=reason)
    if ok:
        console.print(f"[green]{task_id} -> {status}[/green]")
    else:
        console.print(f"[red]任务 '{task_id}' 不存在[/red]")

@task_app.command("pause")
def task_pause(task_id: str = typer.Argument(..., help="任务 ID")):
    """暂停 queued 任务."""
    init_env()
    from .task_queue import pause_task
    if pause_task(task_id):
        console.print(f"[green]{task_id} -> paused[/green]")
    else:
        console.print(f"[red]无法暂停: {task_id} (仅 queued 状态可暂停)[/red]")

@task_app.command("resume")
def task_resume(task_id: str = typer.Argument(..., help="任务 ID")):
    """恢复 paused 任务."""
    init_env()
    from .task_queue import resume_task
    if resume_task(task_id):
        console.print(f"[green]{task_id} -> queued[/green]")
    else:
        console.print(f"[red]无法恢复: {task_id} (仅 paused 状态可恢复)[/red]")

@task_app.command("cancel")
def task_cancel(task_id: str = typer.Argument(..., help="任务 ID")):
    """取消任务."""
    init_env()
    from .task_queue import cancel_task
    if cancel_task(task_id):
        console.print(f"[green]{task_id} -> cancelled[/green]")
    else:
        console.print(f"[red]无法取消: {task_id}[/red]")

@task_app.command("archive")
def task_archive(task_id: str = typer.Argument(..., help="任务 ID")):
    """归档已完成/已取消任务."""
    init_env()
    from .task_queue import archive_task
    if archive_task(task_id):
        console.print(f"[green]{task_id} -> archived[/green]")
    else:
        console.print(f"[red]无法归档: {task_id} (仅 passed/cancelled/blocked/failed 可归档)[/red]")

@task_app.command("retry")
def task_retry(task_id: str = typer.Argument(..., help="任务 ID")):
    """重新排队任务."""
    init_env()
    from .task_queue import mark_task_retry, find_task
    ok = mark_task_retry(task_id)
    if ok:
        t = find_task(task_id)
        rc = t.get("retry_count", 0) if t else 0
        console.print(f"[green]{task_id} -> queued (retry #{rc})[/green]")
    else:
        console.print(f"[red]任务 '{task_id}' 不存在[/red]")

@task_app.command("add")
def task_add(
    project_id: str = typer.Option(..., "--project", "-p", help="项目 ID"),
    title: str = typer.Option(..., "--title", "-t", help="任务标题"),
    description: str = typer.Option("", "--description", "-d", help="任务描述"),
    risk: str = typer.Option("medium", "--risk", "-r", help="风险等级: low | medium | high"),
):
    init_env()

    if risk not in ("low", "medium", "high"):
        console.print(f"[red]无效的风险等级: {risk}。必须为 low, medium 或 high[/red]")
        raise typer.Exit(1)

    project = find_project(project_id)
    if not project:
        console.print(f"[red]项目 '{project_id}' 不在注册表中。先执行: aihub project validate[/red]")
        raise typer.Exit(1)

    task_id = add_task(project_id, title, description, risk)
    console.print(f"[green]任务已添加: {task_id}[/green]")

# ============================================================
# run 命令
# ============================================================

run_app = typer.Typer(help="运行管理")
app.add_typer(run_app, name="run")

@run_app.command("start")
def run_start(
    project_id: str = typer.Option(..., "--project", "-p"),
    task_id: str = typer.Option(..., "--task", "-t"),
    apply_changes: bool = typer.Option(False, "--apply", help="显式允许真实代码修改"),
    run_tests: bool = typer.Option(False, "--run-tests", help="dry-run 下也执行测试命令"),
):
    """运行工作流。默认 dry-run。OpenCode-only."""
    init_env()
    _execute_run(project_id, task_id, apply_changes, run_tests)

@app.command("go")
def go_dispatch(
    task_spec_path: Path = typer.Argument(..., help="SADP TaskSpec JSON/YAML file"),
    project_id: Optional[str] = typer.Option(None, "--project", "-p", help="Override project id"),
    apply_changes: bool = typer.Option(False, "--apply", help="Override TaskSpec mode and apply changes"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Override TaskSpec mode and force dry-run"),
    run_tests: bool = typer.Option(False, "--run-tests", help="Execute verification commands in dry-run"),
):
    """Dispatch a SADP TaskSpec to the OpenCode-backed workflow."""
    init_env()
    spec = _load_task_spec(task_spec_path)
    from .task_spec_adapter import from_task_spec
    adapted = from_task_spec(spec)

    pid = project_id or spec.get("project_id") or spec.get("project")
    if not pid:
        console.print("[red]TaskSpec missing project_id (or pass --project).[/red]")
        raise typer.Exit(1)

    mode_apply = adapted.get("mode", "dry-run") == "apply"
    if apply_changes:
        mode_apply = True
    if dry_run:
        mode_apply = False

    verify_commands = _verification_commands_from_spec(adapted.get("verification", []))
    _check_verify_deny_conflict(verify_commands, adapted.get("forbidden_files", []))

    task_id = add_task(
        pid,
        adapted["title"],
        adapted.get("description", ""),
        adapted.get("risk", "medium"),
        coding_backend="opencode",
    )
    console.print(f"[bold]@go dispatch[/bold] TaskSpec -> {task_id} (backend=opencode)")

    result = _execute_run(
        pid,
        task_id,
        apply_changes=mode_apply,
        run_tests=run_tests,
        task_allowed_files=adapted.get("allowed_files", []),
        task_forbidden_files=adapted.get("forbidden_files", []),
        task_test_commands=verify_commands or None,
        task_spec=spec,
    )

    run_dir = result.get("run_dir", "") if result else ""
    if run_dir:
        report_path = _write_execution_report(run_dir)
        console.print(f"[green]ExecutionReport:[/green] {report_path}")

@run_app.command("all")
def run_all(
    risk: Optional[str] = typer.Option(None, "--risk", "-r", help="按风险等级过滤: low | medium | high"),
):
    init_env()

    tasks = list_tasks("pending")
    if risk:
        tasks = [t for t in tasks if t.get("risk") == risk]

    if not tasks:
        console.print("[yellow]没有待执行的任务[/yellow]")
        return

    risk_order = {"low": 0, "medium": 1, "high": 2}
    tasks.sort(key=lambda t: risk_order.get(t.get("risk", "medium"), 1))

    console.print(f"[bold]将串行运行 {len(tasks)} 个任务（默认 dry-run）[/bold]\n")

    for i, task in enumerate(tasks, 1):
        console.print(f"\n{'='*60}")
        console.print(f"[bold]任务 {i}/{len(tasks)}: {task['title']}[/bold]")
        console.print(f"{'='*60}")

        try:
            _execute_run(task["project_id"], task["id"], apply_changes=False, run_tests=False)
        except typer.Exit:
            pass

@app.command("board")
def task_board_cmd(watch: bool = typer.Option(False, "--watch", "-w", help="持续刷新")):
    """任务仪表盘."""
    init_env()
    import time as _time
    while True:
        task_board()  # call the function above
        if not watch:
            break
        _time.sleep(5)
        console.clear()

@run_app.command("show")
def run_show(run_id: str = typer.Option(..., "--run-id", "-r")):
    """展示 run 详情."""
    init_env()
    from .run_store import list_runs, _hub_dir
    import json
    runs = list_runs(limit=200)
    found = [r for r in runs if r.get("run_id") == run_id]
    if not found:
        console.print(f"[red]Run not found: {run_id}[/red]")
        return

    info = found[0]
    pid = info.get("project_id", "")
    rd = _hub_dir() / "runs" / pid / run_id
    sf = rd / "state.json"
    if not sf.exists():
        console.print(f"[red]State not found: {sf}[/red]")
        return

    s = json.loads(sf.read_text(encoding="utf-8"))
    console.print(f"[bold]Run: {run_id}[/bold]")
    console.print(f"Status: {s.get('status','?')} | Review: {s.get('review_result','?')}")
    console.print(f"Task: {s.get('task_title','?')} | Risk: {s.get('task_risk','?')}")
    console.print(f"Branch: {s.get('current_branch','?')} | Isolation: {s.get('isolation_mode','?')}")
    console.print(f"Diff: {s.get('diff_line_count',0)} lines, {len(s.get('changed_files',[]))} files")
    console.print(f"Test exit: {s.get('test_exit_code',-1)} | Fix rounds: {s.get('fix_round',0)}/{s.get('max_fix_rounds',3)}")
    console.print(f"Error: {s.get('error_message','')[:200]}")

    bc = s.get("backend_calls", {})
    if bc:
        console.print("\n[bold]Backend Calls:[/bold]")
        for node, info in bc.items():
            if isinstance(info, dict):
                console.print(f"  {node}: {info.get('backend','?')} exit={info.get('exit_code','?')} dur={info.get('duration_seconds','?')}s")

    # Chain evidence
    ce = rd / "chain-evidence.json"
    if ce.exists():
        ce_data = json.loads(ce.read_text(encoding="utf-8"))
        console.print("\n[bold]Chain Evidence:[/bold]")
        for node, info in ce_data.get("nodes", {}).items():
            if info.get("called") == False:
                console.print(f"  {node}: (not called)")
            elif node == "plan_auditor":
                console.print(f"  plan_auditor: result={info.get('result','?')} "
                              f"blocked={info.get('blocked',False)} "
                              f"human_required={info.get('human_required',False)}")
            else:
                console.print(f"  {node}: {info.get('backend','?')} exit={info.get('exit_code','?')} "
                              f"model={info.get('effective_model',info.get('requested_model','?'))}")
                if info.get("tokens_used"):
                    console.print(f"    tokens: {info['tokens_used'][:60]}")
                if info.get("session_id"):
                    console.print(f"    session: {info['session_id']}")

    for f in ["diff.patch", "review.yaml", "failure-analysis.md", "safety-report.md"]:
        fp = rd / f
        if fp.exists():
            console.print(f"  [dim]{f}: {fp.stat().st_size} bytes[/dim]")

    try:
        governance_summary = summarize_run_governance(rd, state=s)
    except Exception:
        governance_summary = {"governance": {}}
    console.print(render_full_governance_cli(governance_summary))

@run_app.command("prune")
def run_prune(
    project_id: str = typer.Option("", "--project", "-p"),
    older_than_days: int = typer.Option(30, "--older-than", "-d"),
    keep_summary: bool = typer.Option(True, "--keep-summary"),
    dry_run: bool = typer.Option(True, "--dry-run"),
):
    """清理旧 run 目录."""
    init_env()
    from .run_store import _hub_dir
    import shutil, time as _time

    runs_base = _hub_dir() / "runs"
    cutoff = _time.time() - older_than_days * 86400
    pruned = 0

    for proj_dir in runs_base.iterdir():
        if not proj_dir.is_dir() or proj_dir.name in ("acceptance", "audit", "ci", "daemon", "backend-health"):
            continue
        for run_dir in proj_dir.iterdir():
            if not run_dir.is_dir(): continue
            if run_dir.stat().st_mtime > cutoff: continue
            # Read state to check status
            sf = run_dir / "state.json"
            status = "unknown"
            if sf.exists():
                try:
                    s = json.loads(sf.read_text(encoding="utf-8"))
                    status = s.get("status", "unknown")
                except Exception:
                    pass
            # Only prune passed
            if status != "passed": continue
            if dry_run:
                console.print(f"[dim]would prune: {run_dir.name} ({status})[/dim]")
                pruned += 1
            else:
                if keep_summary:
                    # Keep state.json + final-report + diff.patch
                    for f in run_dir.iterdir():
                        if f.name not in ("state.json", "final-report.md", "diff.patch", "failure-analysis.md"):
                            if f.is_file(): f.unlink()
                            elif f.is_dir(): shutil.rmtree(str(f))
                else:
                    shutil.rmtree(str(run_dir))
                pruned += 1

    action = "would prune" if dry_run else "pruned"
    console.print(f"[green]{action}: {pruned} runs[/green]")

@run_app.command("recover")
def run_recover(run_id: str = typer.Option(..., "--run-id", "-r"),
                project_id: str = typer.Option("", "--project", "-p")):
    """恢复建议 -- 不自动执行，只给出可操作步骤."""
    init_env()
    from .run_store import list_runs
    runs = list_runs(limit=200)
    found = [r for r in runs if r.get("run_id") == run_id]
    pid = project_id or (found[0].get("project_id", "") if found else "")
    from .recover import analyze_recovery
    result = analyze_recovery(run_id, pid)
    if result.get("error"):
        console.print(f"[red]{result['error']}[/red]")
        return
    console.print(f"[bold]Recovery: {result['status']}[/bold]")
    console.print(f"Blocking: {result['blocking']} | Task: {result['task_id']}")
    console.print(f"\n[green]Suggested actions:[/green]")
    for s in result['suggestions']:
        console.print(f"  {s}")

    run_governance = result.get("run_governance", {})
    if run_governance:
        console.print(render_full_governance_cli(run_governance))

@run_app.command("verify")
def run_verify(run_id: str = typer.Option(..., "--run-id", "-r"),
               project_id: str = typer.Option("", "--project", "-p")):
    """验证 run evidence 完整性."""
    init_env()
    from .run_store import list_runs, _hub_dir

    runs = list_runs(limit=200)
    found = [r for r in runs if r.get("run_id") == run_id]
    if not found:
        console.print(f"[red]Run not found: {run_id}[/red]")
        return

    pid = project_id or found[0].get("project_id", "")
    rd = _hub_dir() / "runs" / pid / run_id
    result = verify_run_evidence(run_id, pid, hub_dir_override=rd.parents[2])
    present = result.get("evidence_files_present", [])
    missing = result.get("evidence_files_missing", [])
    status = result.get("status", "?")
    ev_ok = result.get("evidence_ok", False)
    chain_ok = result.get("chain_trusted", False)
    chain_status = result.get("chain_status", "MISSING")
    final_report_status = result.get("final_report_status", "MISSING")
    overall = "PASS" if ev_ok and chain_ok else "FAIL"

    console.print(f"[bold]{overall}: {len(present)}/{len(present) + len(missing)} evidence files[/bold]")
    if missing:
        console.print(f"[red]Evidence missing: {', '.join(missing)}[/red]")
    else:
        console.print("[green]All evidence present[/green]")
    console.print(f"[{'green' if chain_ok else 'red'}]Chain evidence: {chain_status}[/{'green' if chain_ok else 'red'}]")
    console.print(f"[dim]Run status: {status}[/dim]")
    console.print(f"[dim]Run status: {status}[/dim]")
    if not result.get("final_report_consistent", True):
        console.print(f"[red]WARN: final-report inconsistent with state[/red]")
    if final_report_status == "MISSING":
        console.print(f"[yellow]WARN: final-report missing[/yellow]")

    run_governance = result.get("run_governance", {})
    console.print(render_full_governance_cli(run_governance))
    return
    if not fr_trusted:
        console.print(f"[yellow]WARN: final-report is fallback/local template -- trusted_for_status=false[/yellow]")

    # Governance summary (display-only, aligned with final-report)
    try:
        from .issue_ledger import ledger_summary, render_governance_lines_cli
        gov = ledger_summary(str(rd))
    except Exception:
        gov = {}
    console.print(render_governance_lines_cli(gov))

@run_app.command("latest")
def run_latest(project_id: str = typer.Option(..., "--project", "-p")):
    """显示最近的 run."""
    init_env()
    from .run_store import list_runs
    runs = list_runs(limit=1)
    if runs:
        run_show(run_id=runs[0].get("run_id", ""))
    else:
        console.print("[dim]No runs[/dim]")

def _load_task_spec(path: Path) -> dict[str, Any]:
    """Load a SADP TaskSpec from JSON or YAML."""
    if not path.exists():
        console.print(f"[red]TaskSpec not found: {path}[/red]")
        raise typer.Exit(1)
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() == ".json":
        data = json.loads(text)
    else:
        data = _yaml.safe_load(text)
    if not isinstance(data, dict):
        console.print("[red]TaskSpec root must be an object.[/red]")
        raise typer.Exit(1)
    return data

def _is_allowed_task_spec_verification_command(command: str) -> tuple[bool, str]:
    """Allow only structured local verification commands from TaskSpec verify."""
    import shlex as _shlex

    stripped = command.strip()
    if not stripped:
        return False, "empty verification command"

    shell_tokens = ("&&", "||", ";", "|", "&", ">", "<", "`", "$(", "\n", "\r")
    if any(token in stripped for token in shell_tokens):
        return False, "shell operators are not allowed in TaskSpec verification"

    try:
        parts = _shlex.split(stripped, posix=False)
    except ValueError as exc:
        return False, f"cannot parse verification command: {exc}"
    if not parts:
        return False, "empty verification command"

    exe = Path(str(parts[0]).strip("\"'")).name.lower()
    args = [str(p).strip("\"'") for p in parts[1:]]
    write_flags = {
        "--fix", "--fix-only", "--write", "--output", "--out-dir",
        "--emit", "--emit-json", "-o",
    }
    for arg in args:
        if arg in write_flags or any(arg.startswith(flag + "=") for flag in write_flags):
            return False, f"write-producing verification flag is not allowed: {arg}"

    if exe in {"python", "python.exe", "py"}:
        if len(args) >= 2 and args[0] == "-m" and args[1] in {
            "pytest", "compileall", "py_compile",
        }:
            return True, ""
        return False, "python verification must use -m pytest|compileall|py_compile"

    if exe in {"pytest", "pytest.exe", "ruff", "ruff.exe", "mypy", "mypy.exe"}:
        return True, ""

    if exe in {"npm", "npm.cmd", "npm.exe"}:
        if args[:1] == ["test"]:
            return True, ""
        if len(args) >= 2 and args[0] == "run" and args[1] in {"test", "lint", "typecheck"}:
            return True, ""
        return False, "npm verification must be test or run test|lint|typecheck"

    if exe in {"node", "node.exe"} and args[:1] == ["--test"]:
        return True, ""

    return False, f"verification executable is not allowlisted: {exe}"


def _verification_commands_from_spec(verify: list[str]) -> dict[str, str]:
    """Convert TaskSpec verify list into named allowlisted local commands."""
    commands: dict[str, str] = {}
    for index, command in enumerate(verify or [], start=1):
        if not isinstance(command, str) or not command.strip():
            console.print(f"[red]TaskSpec verify[{index}] must be a non-empty string.[/red]")
            raise typer.Exit(1)
        normalized = command.strip()
        allowed, reason = _is_allowed_task_spec_verification_command(normalized)
        if not allowed:
            console.print(
                f"[red]TaskSpec verify[{index}] rejected: {reason}. "
                "Use structured local verification only.[/red]"
            )
            raise typer.Exit(1)
        commands[f"verify_{index}"] = normalized
    return commands

@dataclass
class VerifyDenyConflict:
    verify_command_name: str
    script_path: str
    derived_candidate: str
    deny_target: str

def _check_verify_deny_conflict(
    verify_commands: dict[str, str],
    forbidden_files: list[str],
) -> None:
    """Preflight: block dispatch if a verify .py command conflicts with deny_write.

    Deterministic rule (not a shell parser):
    - Extract .py file paths from verify commands.
    - For each, derive candidate report-output filenames:
      * {stem}.txt  (e.g. smoke_test.py -> smoke_test.txt)
      * {prefix}_report.txt if stem ends with _test (e.g. smoke_test -> smoke_report.txt)
    - If any candidate matches a forbidden/deny_write file, block before _execute_run.
    - Emits structured blocked details with stable reason identifier.
    """
    import re as _re
    from pathlib import Path as _Path

    _py_re = _re.compile(r'(\S+\.py)')
    conflicts: list[VerifyDenyConflict] = []

    for cmd_name, cmd in verify_commands.items():
        for _m in _py_re.finditer(cmd):
            py_path = _m.group(1).strip("\"'")
            stem = _Path(py_path).stem

            candidates = {stem + ".txt"}
            if stem.endswith("_test"):
                prefix = stem[:-5]
                candidates.add(prefix + "_report.txt")

            for forbid in forbidden_files:
                forbid_stem = _Path(forbid).stem
                for candidate in candidates:
                    if _Path(candidate).stem == forbid_stem:
                        conflicts.append(VerifyDenyConflict(
                            verify_command_name=cmd_name,
                            script_path=py_path,
                            derived_candidate=candidate,
                            deny_target=forbid,
                        ))

    if conflicts:
        console.print(f"[red]BLOCKED: VERIFY_DENY_CONFLICT ({len(conflicts)} conflict(s))[/red]")
        for c in conflicts:
            console.print(
                f"  [red]verify={c.verify_command_name}[/red] "
                f"script={c.script_path} "
                f"candidate={c.derived_candidate} "
                f"deny={c.deny_target}"
            )
        raise typer.Exit(69)

def _write_execution_report(run_dir: str) -> str:
    """Write @go ExecutionReport artifacts from run evidence."""
    from .execution_report_adapter import to_execution_report
    report = to_execution_report(run_dir)
    save_run_json(run_dir, "execution-report.json", report)
    lines = [
        "# ExecutionReport",
        "",
        f"- **Task ID**: {report.get('task_id', '')}",
        f"- **Status**: {report.get('status', 'unknown')}",
        f"- **Diff**: {report.get('diff_summary', '')}",
        f"- **Safety**: {report.get('safety', {}).get('overall', 'unknown')}",
        f"- **Evidence Trust**: {report.get('evidence_trust', '')}",
        "",
        "## Changed Files",
    ]
    changed = report.get("changed_files", [])
    lines.extend(f"- `{path}`" for path in changed) if changed else lines.append("- (none)")
    lines.extend([
        "",
        "## Test Results",
        "```",
        str(report.get("test_results", ""))[:2000],
        "```",
    ])
    return save_run_file(run_dir, "execution-report.md", "\n".join(lines))

# ============================================================
# status / report 命令
# ============================================================

@app.command("status")
@app.command("board")
def task_board():
    """任务仪表盘."""
    init_env()
    from .task_queue import list_tasks
    from .daemon import daemon_is_running

    daemon_state = "[green]RUNNING[/green]" if daemon_is_running() else "[dim]stopped[/dim]"
    console.print(f"Daemon: {daemon_state}\n")

    tasks = [t for t in list_tasks() if t.get("status") != "archived"]
    if not tasks:
        console.print("[dim]无活跃任务[/dim]")
        return

    table = Table(title="Task Board")
    table.add_column("ID")
    table.add_column("Title")
    table.add_column("Status")
    table.add_column("Backend")
    table.add_column("Last Run")
    table.add_column("FA")

    for t in sorted(tasks, key=lambda t: {"queued": 0, "running": 1, "human_required": 2, "blocked": 3, "failed": 4, "passed": 5, "cancelled": 6}.get(t.get("status", ""), 9)):
        st = t.get("status", "")
        sc = {"passed": "green", "queued": "dim", "running": "blue", "blocked": "red", "failed": "red", "human_required": "yellow"}.get(st, "")

        # Check FA
        lr = t.get("last_run_id", "")
        fa_exists = False
        if lr:
            from .run_store import _hub_dir
            fa_path = _hub_dir() / "runs" / t["project_id"] / lr / "failure-analysis.md"
            fa_exists = fa_path.exists()

        table.add_row(
            t["id"], t.get("title", "")[:40],
            f"[{sc}]{st}[/{sc}]",
            t.get("coding_backend", "-") or "-",
            lr[-16:] if lr else "-",
            "[red]FA[/red]" if fa_exists else "-",
        )
    console.print(table)

def status_command():
    init_env()
    runs = list_runs(limit=20)

    if not runs:
        console.print("[yellow]没有运行记录[/yellow]")
        return

    table = Table(title="Recent Runs")
    table.add_column("Run ID", style="cyan")
    table.add_column("Project")
    table.add_column("Task")
    table.add_column("Status")
    table.add_column("Report")

    for r in runs:
        status = r.get("status", "unknown")
        status_style = {
            "passed": "green",
            "failed": "red",
            "blocked": "red",
            "human_required": "yellow",
            "pending": "dim",
            "running": "blue",
        }.get(status, "")
        table.add_row(
            r.get("run_id", ""),
            r.get("project_id", ""),
            r.get("task_id", ""),
            f"[{status_style}]{status}[/{status_style}]",
            "Yes" if r.get("has_report") else "No",
        )

    console.print(table)

@app.command("report")
def report_command(run_id: str = typer.Option(..., "--run", "-r")):
    init_env()

    runs = list_runs(limit=200)
    found = [r for r in runs if r.get("run_id") == run_id]

    if not found:
        console.print(f"[red]找不到运行: {run_id}[/red]")
        raise typer.Exit(1)

    info = found[0]
    project_id = info.get("project_id", "")
    report = get_run_report(run_id, project_id)

    if report:
        console.print(Panel(report[:3000], title=f"Report: {run_id}"))
        run_dir = Path(os.getcwd()) / "runs" / project_id / run_id
        console.print(f"\n[dim]完整报告: {run_dir}/final-report.md[/dim]")
    else:
        console.print(f"[yellow]report 不存在: {run_id}[/yellow]")

# ============================================================
# backup 命令
# ============================================================

bu_app = typer.Typer(help="备份管理")
app.add_typer(bu_app, name="backup")

@bu_app.command("list")
def backup_list(limit: int = typer.Option(20, "--limit", "-n")):
    """列出最近备份."""
    init_env()
    from .backup_manager import list_backups
    backups = list_backups(limit)
    if not backups:
        console.print("[dim]无备份[/dim]")
        return
    for b in backups:
        console.print(f"[dim]{b.get('_ts','?')[:19]}[/dim] {b.get('action','?')}: {b.get('source','?')}")

@bu_app.command("show")
def backup_show(timestamp: str = typer.Argument(..., help="时间戳前缀")):
    """查看备份详情."""
    init_env()
    from .backup_manager import list_backups
    matches = [b for b in list_backups(100) if timestamp in str(b.get("_ts", ""))]
    if matches:
        import json as _j
        console.print(_j.dumps(matches[0], indent=2, ensure_ascii=False))
    else:
        console.print(f"[red]未找到: {timestamp}[/red]")

@bu_app.command("restore")
def backup_restore(timestamp: str = typer.Argument(..., help="时间戳前缀")):
    """恢复备份."""
    init_env()
    from .backup_manager import restore_backup
    result = restore_backup(timestamp)
    if result.get("restored"):
        console.print(f"[green]Restored: {result['source']}[/green]")
    else:
        console.print(f"[red]{result.get('error')}[/red]")

# ============================================================
# worktree 命令
# ============================================================

wt_app = typer.Typer(help="worktree 管理")
app.add_typer(wt_app, name="worktree")

@wt_app.command("list")
def worktree_list():
    """列出所有 worktree."""
    init_env()
    from .config_loader import _hub_dir
    from .task_queue import list_tasks
    wt_base = _hub_dir().parent / "aihub-worktrees"
    if not wt_base.exists():
        console.print("[dim]无 worktree[/dim]")
        return

    tasks_map = {t.get("last_run_id", ""): t for t in list_tasks()}

    table = Table(title="Worktrees")
    table.add_column("Path")
    table.add_column("Task")
    table.add_column("Status")
    for wt_dir in sorted(wt_base.rglob("*")):
        if wt_dir.is_dir() and (wt_dir / ".git").exists():
            rel = str(wt_dir.relative_to(wt_base.parent))
            # Match to task
            task_id = wt_dir.name.split("-")[0] if "-" in wt_dir.name else ""
            t = tasks_map.get("", {})
            matched = any(wt_dir.name in lr for lr in [tt.get("last_run_id", "") for tt in tasks_map.values()])
            table.add_row(rel, task_id or "?", "-")
    console.print(table)

@wt_app.command("clean")
def worktree_clean(
    what: str = typer.Argument("passed", help="passed | all | failed"),
    older_than_days: int = typer.Option(0, "--older-than", "-d", help="仅清理 N 天前的"),
):
    """清理 worktree."""
    init_env()
    from .audit import audit_log
    audit_log("worktree.clean", result="STARTED", allowed=True, reason=f"mode={what}")
    import shutil
    from .config_loader import _hub_dir
    from .task_queue import list_tasks

    wt_base = _hub_dir().parent / "aihub-worktrees"
    if not wt_base.exists():
        console.print("[dim]无 worktree[/dim]")
        return

    task_statuses = {t["id"]: t.get("status", "") for t in list_tasks()}
    cleaned = 0
    cutoff = time.time() - older_than_days * 86400 if older_than_days else 0

    for proj_dir in wt_base.iterdir():
        if not proj_dir.is_dir(): continue
        for wt_dir in proj_dir.iterdir():
            if not wt_dir.is_dir(): continue
            if older_than_days and wt_dir.stat().st_mtime > cutoff: continue
            task_id = wt_dir.name.split("-")[0] if "-" in wt_dir.name else ""
            ts = task_statuses.get(task_id, "")
            should_clean = (what == "all") or (what == "passed" and ts == "passed")
            if should_clean:
                shutil.rmtree(str(wt_dir), ignore_errors=True)
                cleaned += 1
                console.print(f"[dim]已清理: {wt_dir.name}[/dim]")

    console.print(f"[green]清理完成: {cleaned} 个 worktree[/green]")

@app.command("apply")
def aihub_apply(
    description: str = typer.Argument(..., help="任务描述"),
    auto_yes: bool = typer.Option(False, "--yes", "-y", help="跳过确认"),
    risk: str = typer.Option("", "--risk", "-r"),
    project: str = typer.Option("", "--project", "-p"),
):
    """真实执行 -- 改代码 / 测试 / 复审."""
    _aihub_plan_or_apply(description, apply_changes=True, auto_yes=auto_yes,
                         risk=risk, project=project)

@app.command("plan")
def aihub_plan(
    description: str = typer.Argument(..., help="任务描述"),
    apply_changes: bool = typer.Option(False, "--apply", help="拒绝 -- 请用 aihub apply"),
    auto_yes: bool = typer.Option(False, "--yes", "-y"),
    risk: str = typer.Option("", "--risk", "-r"),
    project: str = typer.Option("", "--project", "-p"),
):
    """预演 -- dry-run，不改代码."""
    if apply_changes:
        console.print("[red]plan 不支持 --apply。请使用: aihub apply[/red]")
        raise typer.Exit(1)
    _aihub_plan_or_apply(description, apply_changes=False, auto_yes=False,
                         risk=risk, project=project)

@app.command("do")
def aihub_do(
    description: str = typer.Argument(..., help="任务描述"),
    apply_changes: bool = typer.Option(False, "--apply", help="真实执行"),
    auto_yes: bool = typer.Option(False, "--yes", "-y", help="跳过确认"),
    risk: str = typer.Option("", "--risk", "-r"),
    project: str = typer.Option("", "--project", "-p"),
):
    """[deprecated] 请使用 aihub plan 或 aihub apply."""
    console.print("[yellow]aihub do is deprecated. Use aihub plan (dry-run) or aihub apply.[/yellow]")
    _aihub_plan_or_apply(description, apply_changes=apply_changes, auto_yes=auto_yes,
                         risk=risk, project=project)

def _aihub_plan_or_apply(
    description: str,
    apply_changes: bool = False,
    auto_yes: bool = False,
    risk: str = "",
    project: str = "",
) -> None:
    """共享实现：plan (dry-run) / apply (真实)."""
    init_env()
    from pathlib import Path as _Path

    # 1. Session gate + project auto-detect
    cwd = str(_Path.cwd())
    from .session_gate import ensure_session_marker
    ensure_session_marker(cwd, created_by="aihub-do")

    # 2. Zero-config: auto-init if needed
    proj_id = project or _Path(cwd).name
    existing = find_project(proj_id)
    if not existing:
        from .project_detect import detect_project
        from .init_project import init_project
        detected = detect_project(cwd)
        console.print(f"[dim]Auto-detect: {detected['type']} (confidence {detected['confidence']})[/dim]")
        result = init_project(path=cwd, auto_register=True)
        if result.get("registered"):
            console.print(f"[green]Auto-registered: {proj_id}[/green]")
        existing = find_project(proj_id)

    if not project:
        from .project_detect import detect_project
        detected = detect_project(cwd)
        proj_id = detected["project_id"]
        existing = find_project(proj_id)
        if not existing:
            console.print(f"[dim]Auto-detected: {detected['type']} (confidence: {detected['confidence']})[/dim]")
            from .init_project import init_project
            result = init_project(path=cwd, auto_register=True)
            if result.get("registered"):
                console.print(f"[green]Auto-registered: {proj_id}[/green]")
            add_project(proj_id, proj_id, cwd)
            console.print(f"[green]Project registered: {proj_id}[/green]")

    # 2. Infer risk
    task_risk = risk or infer_risk_from_desc(description)
    console.print(f"[dim]Risk: {task_risk}[/dim]")

    # 3. Create task
    from .task_queue import add_task, list_tasks
    task_id = add_task(proj_id, description[:80], description, risk=task_risk)
    console.print(f"[dim]Task: {task_id}[/dim]")

    # 4. Backend: always opencode
    console.print(f"[dim]Backend: opencode[/dim]")

    # 5. Dry-run by default
    if not apply_changes:
        console.print(f"\n[bold]Dry-run: {description[:100]}[/bold]")
        _execute_run(proj_id, task_id, apply_changes=False, run_tests=False)
        console.print(f"\n[yellow]No changes made. Review the plan above.[/yellow]")
        console.print(f"[dim]To apply: aihub do --apply \"{description[:60]}...\"[/dim]")
        return

    # 6. Preflight
    from .preflight import run_apply_preflight
    pf = run_apply_preflight(proj_id, task_id, risk=task_risk, project_path=cwd)
    if pf["result"] == "BLOCKED":
        console.print(f"[red]Preflight BLOCKED: {pf['reason']}[/red]")
        for c in pf["checks"]:
            console.print(f"  {c['status']:7s} {c['name']}: {c['detail']}")
        return
    if pf["result"] == "WARN":
        console.print(f"[yellow]Preflight WARN: {pf['reason']}[/yellow]")

    # 7. OpenCode readiness check
    if apply_changes:
        from .opencode_readiness import readiness_check
        ok, reason = readiness_check()
        if not ok:
            console.print(f"[red]OpenCode not ready: {reason}[/red]")
            return

    # 8. Apply -- risk/human gate
    if task_risk == "high":
        console.print(f"[red]HIGH RISK task -- requires human gate. Use manual workflow.[/red]")
        return

    if not auto_yes:
        import typer as _typer
        confirm = _typer.confirm("Apply changes in isolated worktree?")
        if not confirm:
            console.print("[dim]Cancelled.[/dim]")
            return

    console.print(f"\n[bold]Apply: {description[:100]}[/bold]")
    _execute_run(proj_id, task_id, apply_changes=True, run_tests=False)

def infer_risk_from_desc(description: str) -> str:
    from .project_detect import infer_risk
    return infer_risk(description)

@app.command("init")
def project_init(
    path: str = typer.Option(".", "--path", "-p", help="项目路径"),
    proj_type: str = typer.Option("", "--type", "-t", help="python | node | android | generic"),
    force: bool = typer.Option(False, "--force", "-f", help="覆盖已有 WORKFLOW.md"),
    auto: bool = typer.Option(False, "--auto", help="自动探测 + 注册项目"),
):
    """初始化项目 -- 生成 .aiworkflow/WORKFLOW.md."""
    init_env()
    from .init_project import init_project
    result = init_project(path=path, proj_type=proj_type, force=force, auto_register=auto)
    if result.get("error"):
        console.print(f"[red]{result['error']}[/red]")
        return
    if result.get("warning"):
        console.print(f"[yellow]{result['warning']}[/yellow]")
        return
    console.print(f"[green]Project initialized: {result['project_type']}[/green]")
    console.print(f"  Workflow: {result['workflow_file']}")
    for k, v in result.get("test_commands", {}).items():
        console.print(f"  {k}: {v}")

# ============================================================
# issue 命令
# ============================================================

issue_app = typer.Typer(help="Issue ledger 管理")
app.add_typer(issue_app, name="issue")

@issue_app.command("import")
def issue_import(
    repo: str = typer.Option(..., "--repo", "-r", help="GitHub repo: owner/name"),
    label: str = typer.Option("aihub", "--label", "-l", help="只导入此 label 的 issue"),
    limit: int = typer.Option(10, "--limit", "-n"),
):
    """从 GitHub 导入 issue 到本地 tasks.yaml。只导入，不双向同步."""
    init_env()
    from .issue_import import import_github_issues
    count = import_github_issues(repo=repo, label=label, limit=limit)
    if count:
        console.print(f"[green]Imported {count} issues[/green]")
    else:
        console.print("[dim]No new issues to import[/dim]")

@issue_app.command("list")
def issue_list():
    """列出最新 issue 状态（每 recurrence_key 最新一条）."""
    init_env()
    from .issue_ledger import _get_latest_by_key

    latest = _get_latest_by_key()
    if not latest:
        console.print("[dim]No issues in ledger[/dim]")
        return

    table = Table(title="Issue Ledger")
    table.add_column("Recurrence Key", style="cyan")
    table.add_column("Title")
    table.add_column("Severity")
    table.add_column("Status")
    table.add_column("Source")
    table.add_column("Run")

    for key in sorted(latest):
        issue = latest[key]
        sev = issue.get("severity", "")
        sev_style = {"P0": "red", "P1": "yellow", "P2": "dim", "P3": "dim"}.get(sev, "")
        status = issue.get("status", "")
        status_style = {
            "open": "red", "fixed": "green", "verified": "green",
            "wontfix": "dim", "closed": "dim",
            "accepted_risk": "yellow", "mitigated": "green", "obsolete": "dim",
        }.get(status, "")

        table.add_row(
            issue.get("recurrence_key", key),
            (issue.get("title") or "")[:60],
            f"[{sev_style}]{sev}[/{sev_style}]" if sev_style else sev,
            f"[{status_style}]{status}[/{status_style}]" if status_style else status,
            issue.get("source", ""),
            (issue.get("run_id") or "")[-16:],
        )

    console.print(table)

@issue_app.command("verify")
def issue_verify(
    recurrence_key: str = typer.Argument(..., help="Recurrence key to verify"),
):
    """验证一个 issue，追加 verified 记录."""
    init_env()
    from .issue_ledger import mark_verified, _get_latest_by_key

    latest = _get_latest_by_key()
    existing = latest.get(recurrence_key)
    title = existing.get("title", "") if existing else ""

    mark_verified(recurrence_key, verification="CLI verified", title=title)
    console.print(f"[green]Verified: {recurrence_key}[/green]")

@issue_app.command("close")
def issue_close(
    recurrence_key: str = typer.Argument(..., help="Recurrence key to close"),
    human_override: bool = typer.Option(
        False, "--human-override",
        help="Explicit human override (P0 wontfix stops blocking with this flag)",
    ),
):
    """关闭一个 issue (wontfix)."""
    init_env()
    from .issue_ledger import mark_wontfix, _get_latest_by_key

    latest = _get_latest_by_key()
    existing = latest.get(recurrence_key)
    title = existing.get("title", "") if existing else ""

    mark_wontfix(recurrence_key, human_override=human_override, title=title)
    override_str = " [human_override]" if human_override else ""
    console.print(f"[yellow]Closed (wontfix): {recurrence_key}{override_str}[/yellow]")

@issue_app.command("reopen")
def issue_reopen(
    recurrence_key: str = typer.Argument(..., help="Recurrence key to reopen"),
):
    """重新打开一个 issue."""
    init_env()
    from .issue_ledger import mark_reopen

    mark_reopen(recurrence_key)
    console.print(f"[green]Reopened: {recurrence_key}[/green]")

@issue_app.command("accept-risk")
def issue_accept_risk(
    recurrence_key: str = typer.Argument(..., help="Recurrence key to mark as accepted risk"),
):
    """标记 issue 为 accepted risk (已接受风险)."""
    init_env()
    from .issue_ledger import mark_accepted_risk, _get_latest_by_key

    latest = _get_latest_by_key()
    existing = latest.get(recurrence_key)
    title = existing.get("title", "") if existing else ""

    mark_accepted_risk(recurrence_key, title=title)
    console.print(f"[yellow]Accepted risk: {recurrence_key}[/yellow]")

@issue_app.command("mitigate")
def issue_mitigate(
    recurrence_key: str = typer.Argument(..., help="Recurrence key to mark as mitigated"),
):
    """标记 issue 为 mitigated (已缓解)."""
    init_env()
    from .issue_ledger import mark_mitigated, _get_latest_by_key

    latest = _get_latest_by_key()
    existing = latest.get(recurrence_key)
    title = existing.get("title", "") if existing else ""

    mark_mitigated(recurrence_key, title=title)
    console.print(f"[green]Mitigated: {recurrence_key}[/green]")

@issue_app.command("obsolete")
def issue_obsolete(
    recurrence_key: str = typer.Argument(..., help="Recurrence key to mark as obsolete"),
):
    """标记 issue 为 obsolete (已过时)."""
    init_env()
    from .issue_ledger import mark_obsolete, _get_latest_by_key

    latest = _get_latest_by_key()
    existing = latest.get(recurrence_key)
    title = existing.get("title", "") if existing else ""

    mark_obsolete(recurrence_key, title=title)
    console.print(f"[dim]Obsoleted: {recurrence_key}[/dim]")

# ============================================================
# governance 命令 (read-only matrix summary)
# ============================================================

gov_app = typer.Typer(help="Governance matrix (read-only)")
app.add_typer(gov_app, name="governance")

VALID_GOVERNANCE_MATRIX_FORMATS = ("panel", "markdown", "json", "snapshot")

@gov_app.command("matrix")
def governance_matrix_cmd(
    format: str = typer.Option(
        "panel", "--format", "-f",
        help="Output format: panel (default), markdown, json, or snapshot",
    ),
):
    """Display the governance coverage matrix summary (read-only, deterministic)."""
    init_env()
    if format not in VALID_GOVERNANCE_MATRIX_FORMATS:
        supported = ", ".join(VALID_GOVERNANCE_MATRIX_FORMATS)
        console.print(f"[red]Invalid format: '{format}'. Supported: {supported}[/red]")
        raise typer.Exit(1)
    if format == "json":
        from .governance_matrix import build_governance_matrix_json
        console.print(build_governance_matrix_json(), markup=False, soft_wrap=True)
    elif format == "markdown":
        from .governance_matrix import build_governance_matrix_markdown
        console.print(build_governance_matrix_markdown(), markup=False, soft_wrap=True)
    elif format == "snapshot":
        from .governance_matrix import build_governance_matrix_snapshot
        console.print(build_governance_matrix_snapshot(), markup=False, soft_wrap=True)
    else:
        from .governance_matrix import build_governance_matrix_panel
        console.print(build_governance_matrix_panel())

# ============================================================
# backend 命令
# ============================================================

backend_app = typer.Typer(help="Backend management")
app.add_typer(backend_app, name="backend")

@backend_app.command("probe")
def backend_probe():
    """轻量探针 -- 检查 OpenCode 可用性，不消耗 token."""
    init_env()

    from .opencode_client import opencode_is_available, opencode_cli_check

    # OpenCode CLI
    opencode_ok = opencode_is_available()
    console.print(f"[bold]OpenCode:[/bold] {'[green]available[/green]' if opencode_ok else '[red]not found[/red]'}")

    if opencode_ok:
        info = opencode_cli_check()
        console.print(f"  Models cmd: {info.get('models_cmd_ok', False)}")
        console.print(f"  Flags found: {info.get('flags_found', [])}")
        if info.get('flags_missing'):
            console.print(f"  [yellow]Flags missing: {info['flags_missing']}[/yellow]")

    # Category determination
    if opencode_ok:
        cat = "READY"
    else:
        cat = "BACKEND_UNAVAILABLE"
    console.print(f"[bold]Category:[/bold] {cat}")

@backend_app.command("status")
def backend_status():
    """显示 OpenCode backend 健康度."""
    init_env()
    console.print("[bold]Backend:[/bold] opencode (always current backend)")
    console.print("[dim]Health tracking moved to per-run state.json[/dim]")

@backend_app.command("stress")
def backend_stress(
    count: int = typer.Option(5, "--count", "-n"),
    project: str = typer.Option("test-repo", "--project", "-p"),
):
    """OpenCode 压力测试 -- 连续 N 次 apply."""
    init_env()
    import time as _t

    backend = "opencode"
    console.print(f"[bold]Stress: {backend} x{count} on {project}[/bold]")

    passed = 0
    failed = 0
    timeout_count = 0
    durations = []

    for i in range(count):
        tid = f"stress-{backend}-{i}"
        title = f"Stress-{backend}-{i}"
        desc = f"在 stress_targets.py 的 stress_marker_{i} 函数上方添加注释 # backend stress {backend} run {i}"

        from .task_queue import add_task, mark_task_finished, update_task_status
        import subprocess as _sp

        _yaml.safe_dump({"tasks": [{
            "id": tid, "project_id": project, "title": title,
            "description": desc, "risk": "low", "status": "queued",
            "priority": "normal",
        }]}, open(_hub_dir() / "tasks.yaml", "w", encoding="utf-8"), allow_unicode=True)

        console.print(f"[dim]Task {i+1}/{count}: {tid}...[/dim]", end=" ")
        try:
            _execute_run(project_id=project, task_id=tid, apply_changes=True,
                        run_tests=False)
            from .run_store import list_runs
            runs = list_runs(limit=1)
            if runs:
                sf = _hub_dir() / "runs" / runs[0]["project_id"] / runs[0]["run_id"] / "state.json"
                if sf.exists():
                    import json as _j
                    s = _j.loads(sf.read_text(encoding="utf-8"))
                    st = s.get("status", "?")
                    bc = s.get("backend_calls", {}).get("executor", {})
                    dur = bc.get("duration_seconds", 0)
                    to = bc.get("timed_out", False)
                    durations.append(dur)
                    if st == "passed":
                        passed += 1
                        console.print(f"[green]{st} {dur}s[/green]")
                    elif to:
                        timeout_count += 1
                        failed += 1
                        console.print(f"[red]timeout {dur}s[/red]")
                    else:
                        failed += 1
                        console.print(f"[yellow]{st}[/yellow]")
        except Exception as e:
            failed += 1
            console.print(f"[red]ERROR: {e}[/red]")

        import shutil as _shutil
        test_repo = os.environ.get("AIHUB_TEST_REPO", str(Path(__file__).resolve().parent.parent.parent / "test-repo"))
        worktrees = os.environ.get("AIHUB_WORKTREES", str(Path(__file__).resolve().parent.parent.parent / "worktrees"))
        _sp.run(["git", "-C", test_repo, "worktree", "prune"], capture_output=True)
        if os.path.isdir(worktrees):
            _shutil.rmtree(worktrees, ignore_errors=True)

    console.print(f"\n[bold]Stress complete: {backend} x{count}[/bold]")
    console.print(f"Passed: {passed}/{count} | Failed: {failed}/{count} | Timeouts: {timeout_count}")
    if durations:
        avg = sum(durations) / len(durations)
        console.print(f"Avg duration: {avg:.1f}s | Min: {min(durations):.1f}s | Max: {max(durations):.1f}s")

# ============================================================
# ops 命令
# ============================================================

ops_app = typer.Typer(help="运营状态")
app.add_typer(ops_app, name="ops")

@ops_app.command("status")
def ops_status():
    """一屏运营视图 -- 不调模型，只读."""
    init_env()
    from .task_queue import list_tasks
    from .daemon import daemon_is_running
    from .config_loader import get_execution_policy

    # Daemon
    console.print(f"[bold]Daemon:[/bold] {'[green]RUNNING[/green]' if daemon_is_running() else '[dim]stopped[/dim]'}")

    # Tasks
    tasks = list_tasks()
    counts = {"queued": 0, "running": 0, "blocked": 0, "passed": 0, "failed": 0, "human_required": 0}
    for t in tasks:
        st = t.get("status", "")
        if st in counts:
            counts[st] += 1
    console.print(f"[bold]Tasks:[/bold] Q:{counts['queued']} R:{counts['running']} B:{counts['blocked']} P:{counts['passed']} F:{counts['failed']} H:{counts['human_required']}")

    # Backend: always opencode
    console.print(f"[bold]Backend:[/bold] opencode")

    # Policy
    rp = get_execution_policy().get("release_policy", {})
    blocked = [k for k, v in rp.items() if isinstance(v, bool) and not v]
    console.print(f"[bold]Policy blocked:[/bold] {', '.join(blocked[:5])}")

    # Goals
    from .goal_store import list_goals as _lg
    goals = _lg(5)
    active_goals = [g for g in goals if g.get("status") not in ("passed", "archived")]
    console.print(f"[bold]Goals:[/bold] {len(goals)} total, {len(active_goals)} active")

    # Evidence dirs
    from .config_loader import _hub_dir
    import os as _os
    runs_dir = _hub_dir() / "runs"
    run_count = sum(1 for _ in runs_dir.rglob("state.json")) if runs_dir.exists() else 0
    console.print(f"[bold]Runs:[/bold] {run_count} with state.json")

# ============================================================
# goal 命令
# ============================================================

goal_app = typer.Typer(help="多步骤目标编排")
app.add_typer(goal_app, name="goal")

@goal_app.command("plan")
def goal_plan(objective: str = typer.Argument(..., help="目标描述")):
    """Goal plan -- 需要手动设置 batches (goal_planner removed in OpenCode migration)."""
    init_env()
    console.print(f"[bold]Planning: {objective[:100]}[/bold]")
    console.print("[yellow]goal plan: planner removed. Create goal manually or use @go via OpenCode.[/yellow]")
    console.print("[dim]See: aihub goal --help[/dim]")

@goal_app.command("run")
def goal_run(
    goal_id: str = typer.Argument(..., help="Goal ID"),
    project: str = typer.Option("test-repo", "--project", "-p"),
):
    """按依赖顺序执行 goal 的所有 batches (OpenCode only)."""
    init_env()
    from .goal_runner import run_goal
    g = run_goal(goal_id, project, "opencode")
    if g.get("error"):
        console.print(f"[red]{g['error']}[/red]")
        return
    console.print(f"[bold]Goal: {g['goal_id']} -> {g['status']}[/bold]")
    for r in g.get("results", []):
        icon = "[green]OK[/green]" if r["status"] == "passed" else "[red]FAIL[/red]"
        name = r.get("batch") or r.get("slice", "?")
        console.print(f"  {icon} {name}: {r.get('run_id','')} {r.get('reason','')}")

@goal_app.command("status")
def goal_status(goal_id: str = typer.Argument(..., help="Goal ID")):
    """查看 goal 状态."""
    init_env()
    from .goal_store import load_goal
    g = load_goal(goal_id)
    if not g:
        console.print(f"[red]Goal not found: {goal_id}[/red]")
        return
    console.print(f"[bold]{g['goal_id']}[/bold]")
    console.print(f"Objective: {g['objective'][:100]}")
    console.print(f"Status: {g['status']} | Replans: {g.get('replan_count',0)}/{g.get('max_replans',2)}")

    # Batch-first view (v1.1)
    batches = g.get("batches", [])
    if batches:
        console.print(f"\nBatches ({len(batches)}):")
        for b in batches:
            icon = {"passed":"[green]OK[/green]","failed":"[red]FAIL[/red]",
                    "running":"[blue]RUN[/blue]","planned":"[dim]QUE[/dim]",
                    "blocked":"[red]BLOCK[/red]","human_required":"[yellow]GATE[/yellow]",
                    "needs_fix":"[yellow]FIX[/yellow]"}.get(b["status"], "[dim]?[/dim]")
            rd = b.get("risk_domain", "?")
            tasks_n = len(b.get("included_tasks", []))
            bid = b.get("batch_id", "?")
            console.print(f"  {icon} {bid} [{rd:20s}] {b.get('risk_level','?'):5s} {tasks_n} tasks  {b.get('run_id','')}")
        return

    # Legacy slice view
    slices = g.get("slices", [])
    if slices:
        console.print(f"\nSlices ({len(slices)}):")
        for sl in slices:
            icon = {"passed":"[green]OK[/green]","failed":"[red]FAIL[/red]",
                    "running":"[blue]RUN[/blue]","planned":"[dim]QUE[/dim]",
                    "blocked":"[red]BLOCK[/red]"}.get(sl["status"], "[dim]?[/dim]")
            console.print(f"  {icon} {sl['slice_id']}: {sl['title'][:50]}")

@goal_app.command("list")
def goal_list(limit: int = typer.Option(20, "--limit", "-n")):
    """列出所有 goals."""
    init_env()
    from .goal_store import list_goals
    goals = list_goals(limit)
    if not goals:
        console.print("[dim]No goals[/dim]")
        return
    for g in goals:
        batches = g.get("batches", [])
        slices = g.get("slices", [])
        if batches:
            n = len(batches)
            passed = sum(1 for b in batches if b["status"] == "passed")
            console.print(f"[dim]{g['goal_id']}[/dim] {g['status']:12s} {passed}/{n} batches  {g['objective'][:60]}")
        else:
            n = len(slices)
            passed = sum(1 for s in slices if s["status"] == "passed")
            console.print(f"[dim]{g['goal_id']}[/dim] {g['status']:12s} {passed}/{n} slices  {g['objective'][:60]}")

@goal_app.command("report")
def goal_report_cmd(goal_id: str = typer.Argument(..., help="Goal ID")):
    """生成 goal 报告 (goal-report.md + goal-evidence.json)."""
    init_env()
    from .goal_report import generate_goal_report
    result = generate_goal_report(goal_id)
    if result.get("error"):
        console.print(f"[red]{result['error']}[/red]")
        raise typer.Exit(1)
    console.print(f"[green]Report: {result['report_path']}[/green]")
    console.print(f"[green]Evidence: {result['evidence_path']}[/green]")
    console.print(f"[dim]Batches: {result.get('batches', 0)}[/dim]")


def _structured_recovered_review_verdict(
    reviewer_result: dict[str, Any],
) -> tuple[str, str, dict[str, Any]]:
    """Derive recovered-review status from structured reviewer evidence."""
    exit_code = reviewer_result.get("exit_code")
    stdout = str(reviewer_result.get("stdout", "") or "").strip()
    stderr = str(reviewer_result.get("stderr", "") or "").strip()
    if exit_code != 0:
        return "failed", f"reviewer backend exit_code={exit_code}; {stderr[:200]}", {}

    try:
        data = json.loads(stdout)
    except json.JSONDecodeError:
        return "blocked", "structured reviewer JSON verdict missing", {}
    if not isinstance(data, dict):
        return "blocked", "structured reviewer verdict must be a JSON object", {}

    verdict = str(data.get("verdict", "")).strip().lower()
    allowed_verdicts = {"passed", "failed", "blocked", "human_required"}
    if verdict not in allowed_verdicts:
        return "blocked", "structured reviewer verdict invalid or missing", data

    gate = data.get("independent_gate_evidence")
    if verdict == "passed":
        if not isinstance(gate, dict):
            return "blocked", "passed verdict requires independent_gate_evidence", data
        if gate.get("diff_scope_ok") is not True:
            return "blocked", "passed verdict requires diff_scope_ok=true", data
        if gate.get("reviewed_diff") is not True:
            return "blocked", "passed verdict requires reviewed_diff=true", data

    reason = str(data.get("reason", "") or verdict)
    return verdict, reason[:500], data


@goal_app.command("review-recovered")
def goal_review_recovered(
    goal_id: str = typer.Argument(..., help="Goal ID"),
    apply_changes: bool = typer.Option(False, "--apply", help="真实调用 reviewer backend"),
    project: str = typer.Option("test-repo", "--project", "-p"),
):
    """审阅 recovered evidence (dry-run default, --apply 调用真实 reviewer)."""
    init_env()
    from .goal_store import load_goal
    from .goal_runner import sync_goal_runs
    from .config_loader import _hub_dir
    from pathlib import Path as _P

    # Sync first
    sync_goal_runs(goal_id, project)
    g = load_goal(goal_id)
    if not g:
        console.print(f"[red]Goal not found: {goal_id}[/red]")
        raise typer.Exit(1)

    for b in g.get("batches", []):
        if not b.get("evidence_recovered") and not b.get("review_required"):
            continue
        rid = b.get("run_id", "")
        if not rid:
            console.print(f"[yellow]batch {b['batch_id']}: no run_id[/yellow]")
            continue

        rd = _hub_dir() / "runs" / project / rid
        dp = rd / "diff.patch"
        sf = rd / "state.json"

        # Pre-flight checks
        changed = b.get("changed_files", [])
        allowed = b.get("allowed_files", [])
        out = [f for f in changed if f not in allowed]
        diff_ok = len(out) == 0

        console.print(f"\n[bold]Batch: {b['batch_id']} (run: {rid})[/bold]")
        console.print(f"  changed_files: {changed}")
        console.print(f"  diff_scope_ok: {diff_ok}")
        console.print(f"  diff.patch: {'[green]exists[/green]' if dp.exists() else '[red]missing[/red]'}")
        console.print(f"  evidence_recovered: {b.get('evidence_recovered')}")
        console.print(f"  review_required: {b.get('review_required', True)}")

        if not diff_ok:
            console.print(f"[red]BLOCKED: out-of-scope files {out}[/red]")
            continue
        if not dp.exists() or dp.stat().st_size == 0:
            console.print(f"[red]BLOCKED: diff.patch missing or empty[/red]")
            continue

        if not apply_changes:
            console.print(f"\n[yellow]DRY-RUN: ready_for_review=true[/yellow]")
            console.print(f"[dim]Use --apply to invoke real reviewer backend[/dim]")
            continue

        # Real reviewer
        console.print(f"\n[red]APPLY: invoking reviewer backend...[/red]")
        try:
            diff_text = dp.read_text(encoding="utf-8")
            review_prompt = f"""Review the following recovered diff from an interrupted workflow.

Changed files: {', '.join(changed)}
Allowed files: {', '.join(allowed)}
Diff scope check: PASS (all changes within allowed_files)

## Recovered Diff
```diff
{diff_text[:8000]}
```

Review the changes. Check:
1. All changes are within allowed_files
2. No forbidden patterns
3. Changes are safe and correct
4. No test regressions introduced

Output: verdict (passed/failed/blocked) and reason.
"""
            from .opencode_client import opencode_run
            result = opencode_run(
                prompt=review_prompt,
                model="deepseek/deepseek-v4-pro",
                cwd=str(project) if not str(project).startswith("test") else os.environ.get("AIHUB_TEST_REPO", "D:/devFrame/ai-workflow-hub-test-repo"),
                timeout=300,
            )
            verdict, review_reason, structured_review = _structured_recovered_review_verdict(result)
            review_text = review_reason[:500]

            # Write back
            from .goal_store import update_batch_status
            import json as _j
            update_batch_status(goal_id, b["batch_id"],
                               verdict,
                               run_id=rid,
                               review_result=f"RECOVERED_EVIDENCE_REVIEW_{verdict.upper()}; {review_text[:200]}",
                               evidence_recovered=True,
                               evidence_recovery_source="review-recovered")
            if sf.exists():
                s = _j.loads(sf.read_text(encoding="utf-8"))
                s["review_required"] = verdict != "passed"
                s["review_result"] = review_text[:500]
                s["reviewer_structured_verdict"] = verdict
                s["reviewer_gate_evidence"] = structured_review.get("independent_gate_evidence", {})
                sf.write_text(_j.dumps(s, indent=2, ensure_ascii=False), encoding="utf-8")

            from .goal_report import generate_goal_report
            generate_goal_report(goal_id)
            console.print(f"[green]Reviewer: {verdict.upper()} -- state written[/green]")
            try:
                console.print(f"[dim]{review_text[:200]}[/dim]")
            except UnicodeEncodeError:
                safe = review_text[:200].encode("ascii", errors="replace").decode("ascii")
                console.print(f"[dim]{safe}[/dim]")
        except Exception as e:
            console.print(f"[red]Reviewer error: {e}[/red]")

# ============================================================
# acceptance 命令
# ============================================================

acceptance_app = typer.Typer(help="自动化验收套件")
app.add_typer(acceptance_app, name="acceptance")

SUITES = {"smoke", "backend", "daemon", "external", "audit", "zero-config", "chain", "chain-truth", "chain-truth-negative", "dynamic", "goal", "cleanup", "status-check", "backend-probe", "assertion-check", "recovery-pipeline", "rc-check", "cleanup-safety", "all", "baseline", "compare", "daemon-atomicity"}

@acceptance_app.command("run")
def acceptance_run(suite: str = typer.Argument("smoke", help=f"Suite: {', '.join(sorted(SUITES))}")):
    """运行验收套件."""
    if suite not in SUITES:
        console.print(f"[red]Unknown suite: {suite}[/red]")
        raise typer.Exit(1)

    init_env()
    from .acceptance import (run_smoke, run_backend, run_daemon, run_external, run_audit,
        run_zero_config, run_chain, run_chain_truth, run_chain_truth_negative,
        run_dynamic, run_goal, run_cleanup, run_status_check, run_backend_probe,
        run_assertion_check, run_recovery_pipeline, run_rc_check,
        run_cleanup_safety, run_daemon_atomicity, run_all)
    from .acceptance import save_baseline, compare_baseline

    if suite == "baseline":
        name = "default"
        bp = save_baseline(name)
        console.print(f"[green]Baseline saved: {bp}[/green]")
        return
    if suite == "compare":
        result = compare_baseline("default")
        if result.get("error"):
            console.print(f"[red]{result['error']}[/red]")
            raise typer.Exit(1)
        if result["healthy"]:
            console.print("[green]No regressions[/green]")
        else:
            for r in result["regressions"]:
                console.print(f"[red]REGRESSION: {r}[/red]")
            raise typer.Exit(1)
        return

    fn = {"smoke": run_smoke, "backend": run_backend, "daemon": run_daemon,
          "external": run_external, "audit": run_audit, "zero-config": run_zero_config,
          "chain": run_chain, "chain-truth": run_chain_truth,
          "chain-truth-negative": run_chain_truth_negative,
          "dynamic": run_dynamic, "goal": run_goal, "cleanup": run_cleanup,
          "status-check": run_status_check, "backend-probe": run_backend_probe,
          "assertion-check": run_assertion_check,
          "recovery-pipeline": run_recovery_pipeline, "rc-check": run_rc_check,
          "cleanup-safety": run_cleanup_safety,
          "daemon-atomicity": run_daemon_atomicity, "all": run_all}[suite]
    rc = fn()
    if rc:
        raise typer.Exit(1)

# ============================================================
# PR 命令
# ============================================================

pr_app = typer.Typer(help="PR 创建")
app.add_typer(pr_app, name="pr")

@pr_app.command("preview")
def pr_preview(
    project_id: str = typer.Option(..., "--project", "-p"),
    run_id: str = typer.Option(..., "--run-id", "-r"),
):
    """预览 PR body，不创建."""
    init_env()
    from .pr_create import preview_pr
    body = preview_pr(project_id, run_id)
    console.print(Panel(body[:3000], title=f"PR Preview: {run_id}"))

@pr_app.command("create")
def pr_create_cmd(
    project_id: str = typer.Option(..., "--project", "-p"),
    run_id: str = typer.Option(..., "--run-id", "-r"),
    repo: str = typer.Option(..., "--repo", help="GitHub repo: owner/name"),
    push: bool = typer.Option(False, "--push", help="先 push branch 再创建 PR"),
):
    """创建 GitHub PR。默认不 push."""
    init_env()
    from .pr_create import create_pr
    result = create_pr(project_id, run_id, repo, push=push)
    if result["success"]:
        console.print(f"[green]PR created: {result['url']}[/green]")
    else:
        console.print(f"[red]{result['error']}[/red]")
        if result["body"]:
            console.print(Panel(result["body"][:1000], title="PR Body (would be)"))

# ============================================================
# CI 命令
# ============================================================

ci_app = typer.Typer(help="CI inspect/fix")
app.add_typer(ci_app, name="ci")

@ci_app.command("inspect")
def ci_inspect(
    repo: str = typer.Option(..., "--repo", "-r", help="GitHub repo: owner/name"),
    pr_number: int = typer.Option(..., "--pr", help="PR number"),
):
    """只读 GitHub Actions CI 状态."""
    init_env()
    from .ci_inspect import check_gh_ci_auth, inspect_ci_pr
    ok, msg = check_gh_ci_auth()
    if not ok:
        console.print(f"[red]{msg}[/red]")
        raise typer.Exit(1)

    report_path, overall = inspect_ci_pr(repo, pr_number)
    color = {"CI_PASS": "green", "CI_FAIL": "red", "CI_RUNNING": "yellow"}.get(overall, "dim")
    console.print(f"[{color}]{overall}[/{color}]")
    console.print(f"[dim]Report: {report_path}[/dim]")

    if overall in ("CI_FAIL", "CI_RUNNING"):
        with open(report_path, encoding="utf-8") as f:
            console.print(f.read()[:1000])

@ci_app.command("fix")
def ci_fix(
    project_id: str = typer.Option(..., "--project", "-p"),
    task_id: str = typer.Option(..., "--task", "-t"),
    repo: str = typer.Option(..., "--repo", "-r"),
    pr_number: int = typer.Option(..., "--pr"),
):
    """CI 失败后自动修复。需要 allow_ci_fix=true."""
    init_env()
    from .ci_inspect import check_gh_ci_auth, ci_fix_task
    ok, msg = check_gh_ci_auth()
    if not ok:
        console.print(f"[red]{msg}[/red]")
        raise typer.Exit(1)

    result = ci_fix_task(project_id, task_id, repo, pr_number)
    if result["status"] == "blocked":
        console.print(f"[red]{result['ci_results']}[/red]")
    else:
        console.print(f"[green]{result['ci_results']}[/green]")

# ============================================================
# daemon 命令
# ============================================================

daemon_app = typer.Typer(help="本地任务调度 daemon")
app.add_typer(daemon_app, name="daemon")

@daemon_app.command("start")
def daemon_start(once: bool = typer.Option(False, "--once", help="只执行一轮")):
    """启动 daemon 轮询。"""
    init_env()
    from .daemon import daemon_loop, daemon_is_running
    if daemon_is_running() and not once:
        console.print("[yellow]Daemon 已在运行[/yellow]")
        raise typer.Exit(1)
    console.print("[bold]Daemon 启动...[/bold]")
    daemon_loop(once=once)

@daemon_app.command("stop")
def daemon_stop():
    """停止 daemon."""
    init_env()
    from .daemon import _PIDFILE, _cleanup_lock, daemon_is_running
    import ctypes
    if not daemon_is_running():
        console.print("[yellow]Daemon 未在运行[/yellow]")
        return
    try:
        pid = int(_PIDFILE.read_text().strip())
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.OpenProcess(0x0001, False, pid)  # PROCESS_TERMINATE
        if handle:
            kernel32.TerminateProcess(handle, 0)
            kernel32.CloseHandle(handle)
            console.print(f"[green]Daemon (pid={pid}) 已停止[/green]")
    except Exception as e:
        console.print(f"[red]停止失败: {e}[/red]")
    _cleanup_lock()

@daemon_app.command("soak")
def daemon_soak_cmd(
    duration: str = typer.Option("30m", "--duration", "-d", help="30m | 2h | 8h"),
    projects: str = typer.Option("test-repo", "--projects", "-p"),
    mode: str = typer.Option("plan", "--mode", "-m", help="plan | apply-safe"),
):
    """运行 daemon soak 测试."""
    init_env()
    # Parse duration
    d = duration.lower()
    mins = 30
    if d.endswith("m"): mins = int(d[:-1])
    elif d.endswith("h"): mins = int(d[:-1]) * 60
    pids = [p.strip() for p in projects.split(",") if p.strip()]

    console.print(f"[bold]Soak: {mins}m, mode={mode}, projects={pids}[/bold]")
    from .daemon import daemon_soak
    result = daemon_soak(duration_minutes=mins, projects=pids, mode=mode)

    sim = " (simulated)" if result.get("simulated") else ""
    console.print(f"\nStatus: [bold]{result['status']}[/bold]{sim} | Reason: {result['end_reason']}")
    console.print(f"Cycles: {result['cycle_count']} | Tasks: seen={result['tasks_seen']} started={result['tasks_started']}")
    console.print(f"Passed: {result['tasks_passed']} Blocked: {result['tasks_blocked']} Failed: {result['tasks_failed']}")
    console.print(f"Stale: {result['stale_running_count']} | Duration: {result['actual_duration_seconds']}s | Exit: {result['exit_code']}")
    if result.get("errors"):
        for e in result["errors"]:
            console.print(f"[red]  {e[:120]}[/red]")

    if result.get("report_json"):
        console.print(f"[dim]Report JSON: {result['report_json']}[/dim]")
        console.print(f"[dim]Report MD:   {result['report_md']}[/dim]")

    # Propagate exit code
    if result["exit_code"] != 0:
        raise typer.Exit(1)

@daemon_app.command("status")
def daemon_status():
    """查看 daemon 状态."""
    init_env()
    from .daemon import daemon_is_running, _HEARTBEAT
    from .config_loader import _hub_dir
    from .task_queue import list_tasks

    if daemon_is_running():
        hb = ""
        if _HEARTBEAT.exists():
            hb = f" (last heartbeat: {_HEARTBEAT.read_text().strip()[:19]})"
        console.print(f"[green]Daemon: RUNNING{hb}[/green]")
    else:
        console.print("[dim]Daemon: stopped[/dim]")

    log_dir = _hub_dir() / "runs" / "daemon"
    if log_dir.exists():
        logs = sorted(log_dir.glob("daemon-*.log"))
        if logs:
            console.print(f"\n[dim]最近日志 ({logs[-1].name}):[/dim]")
            with open(logs[-1], encoding="utf-8") as f:
                for l in f.readlines()[-8:]:
                    console.print(f"  {l.rstrip()}")

    queued = list_tasks(status="queued")
    running = list_tasks(status="running")
    blocked = list_tasks(status="blocked")
    passed = list_tasks(status="passed")
    console.print(f"\n[bold]Queued: {len(queued)}  Running: {len(running)}  Blocked: {len(blocked)}  Passed: {len(passed)}[/bold]")


def _execute_run(project_id: str, task_id: str, apply_changes: bool, run_tests: bool = False,
                 task_allowed_files: list[str] | None = None,
                 task_forbidden_files: list[str] | None = None,
                 task_test_commands: dict[str, str] | None = None,
                 task_spec: dict[str, Any] | None = None) -> dict[str, Any]:
    """执行一次完整的 workflow run (带 checkpointer)."""
    # 1. 加载项目
    project = find_project(project_id)
    if not project:
        console.print(f"[red]项目 '{project_id}' 不在注册表中[/red]")
        raise typer.Exit(1)

    # 2. 加载任务
    task = find_task(task_id)
    if not task:
        console.print(f"[red]任务 '{task_id}' 不存在[/red]")
        raise typer.Exit(1)

    # 3. 校验项目路径
    project_path = project.get("path", "")
    if not Path(project_path).exists():
        console.print(f"[red]项目路径不存在: {project_path}[/red]")
        raise typer.Exit(1)

    # 4. Git 检查
    from .git_utils import is_git_repo, is_worktree_clean, is_main_branch, get_current_branch

    if not is_git_repo(project_path):
        console.print(f"[red]项目不是 Git 仓库: {project_path}[/red]")
        raise typer.Exit(1)

    if apply_changes and not is_worktree_clean(project_path):
        console.print(f"[red]Git 工作区不干净。先提交或 stash 再 apply。[/red]")
        raise typer.Exit(1)

    if apply_changes and is_main_branch(project_path):
        console.print(f"[red]不允许在 main/master 分支上 apply。[/red]")
        raise typer.Exit(1)

    # 5. 加载项目配置
    config_filename = project.get("config", ".aiworkflow.yaml")
    project_config = load_project_workflow_config(project_path, config_filename)
    if not project_config:
        console.print(f"[yellow]警告: {config_filename} 不存在或为空[/yellow]")

    # 6. 加载策略
    risk = task.get("risk", "medium")
    risk_policy = get_risk_policy()
    execution_policy = get_execution_policy()

    risk_config = risk_policy.get("risk_categories", {}).get(risk, {})
    constraints = {
        "max_fix_rounds": risk_config.get("max_fix_rounds", execution_policy.get("max_fix_rounds", 3)),
        "max_changed_files": risk_config.get("max_changed_files", execution_policy.get("max_changed_files", 20)),
        "max_diff_lines": risk_config.get("max_diff_lines", execution_policy.get("max_diff_lines", 800)),
    }

    # 7. 模型分配 (OpenCode only)
    executor_model = get_model_for_risk(risk)
    fixer_model = get_model_for_risk(risk)

    # 8. 创建 run 目录
    run_id, run_dir = create_run_dir(project_id)

    # 9. 隔离策略：worktree → branch fallback
    current_branch = get_current_branch(project_path)
    original_branch = current_branch  # preserved for cleanup (Defect 2 fix)
    worktree_path = ""
    isolation_mode = "branch"
    isolation_fallback_reason = ""

    if apply_changes:
        from .git_utils import create_branch, create_worktree
        mode = execution_policy.get("isolation_mode", "worktree")
        fallback_mode = execution_policy.get("fallback_isolation_mode", "branch")
        ai_branch = f"ai/{task_id}-{run_id[-12:]}"
        _worktree_created = False
        _branch_created = False

        if mode == "worktree":
            wt_dir = str(Path(project_path).parent / "aihub-worktrees" / project_id / f"{task_id}-{run_id[-12:]}")
            ok, msg = create_worktree(project_path, wt_dir, ai_branch)
            if ok:
                worktree_path = wt_dir
                isolation_mode = "worktree"
                current_branch = ai_branch
                _worktree_created = True
                console.print(f"[green]Worktree 创建: {worktree_path}[/green]")
            else:
                isolation_fallback_reason = f"worktree failed: {msg}"
                console.print(f"[yellow]Worktree 失败 ({msg})，降级 branch[/yellow]")

        if isolation_mode != "worktree":
            ok, msg = create_branch(project_path, ai_branch)
            if not ok:
                console.print(f"[red]创建分支失败: {msg}[/red]")
                raise typer.Exit(1)
            current_branch = ai_branch
            isolation_mode = fallback_mode if isolation_mode == "worktree" else isolation_mode
            _branch_created = True
            console.print(f"[green]在分支 '{ai_branch}' 上执行[/green]")

    # CI report from task (for CI fix)
    ci_report = task.get("ci_report", "")

    # 加载项目 WORKFLOW.md
    from .config_loader import find_workflow_file, load_workflow_text
    wf_file = find_workflow_file(project_path) or ""
    wf_text = load_workflow_text(project_path)

    state = WorkflowState(
        project_id=project_id,
        project_name=project.get("name", project_id),
        workflow_file=wf_file,
        workflow_text=wf_text,
        project_type=project_config.get("project", {}).get("type", ""),
        project_path=project_path,
        project_config=project_config,
        task_id=task_id,
        task_title=task.get("title", ""),
        task_description=task.get("description", ""),
        task_risk=risk,
        run_id=run_id,
        run_dir=run_dir,
        thread_id=run_id,  # run_id → thread_id
        current_branch=current_branch,
        worktree_path=worktree_path,
        base_project_path=project_path,
        original_branch=original_branch,
        isolation_mode=isolation_mode,
        isolation_fallback_reason=isolation_fallback_reason,
        dry_run=not apply_changes,
        apply_changes=apply_changes,
        run_tests=run_tests,
        ci_report=ci_report,
        executor_model=executor_model,
        fixer_model=fixer_model,
        constraints=constraints,
        test_commands=task_test_commands if task_test_commands is not None
        else project_config.get("commands", {}),
        allowed_files=task_allowed_files if task_allowed_files is not None else [],
        forbidden_files=_resolve_boundary(
            task_forbidden_files if task_forbidden_files is not None
            else project_config.get("policy", {}).get("forbidden_paths", []),
            task_allowed_files or []),
        protected_tests=project_config.get("policy", {}).get("protected_tests", []),
        max_fix_rounds=constraints["max_fix_rounds"],
        status="running",
    )

    # 10. 保存初始状态
    save_run_file(run_dir, "input-task.md", f"# Task: {task['title']}\n\n{task['description']}")
    save_run_file(run_dir, "project-config.yaml", json.dumps(project_config, indent=2, ensure_ascii=False))
    if task_spec is not None:
        save_run_json(run_dir, "task-spec.json", task_spec)
    save_run_json(run_dir, "state.json", state.model_dump())

    # 11. 显示信息
    mode_parts = []
    if not apply_changes:
        mode_parts.append("[yellow]DRY-RUN[/yellow]")
    else:
        mode_parts.append("[red]APPLY[/red]")
    if run_tests and not apply_changes:
        mode_parts.append("[blue]+RUN-TESTS[/blue]")

    mode_str = " ".join(mode_parts)
    console.print(f"\n[bold]Run: {run_id}[/bold]")
    console.print(f"Project: {project_id} | Task: {task['title']} | Risk: {risk} | Mode: {mode_str}")
    console.print(f"Model: {executor_model} (risk={risk})")
    console.print(f"Thread: {run_id}")
    console.print(f"Run dir: {run_dir}")

    state_dict = state.model_dump()

    # Load issue ledger prompt context
    try:
        from .issue_ledger import build_prompt_context
        ledger_ctx = build_prompt_context()
        if ledger_ctx:
            state_dict["ledger_prompt_context"] = ledger_ctx
            save_run_json(run_dir, "state.json", state_dict)
            console.print(f"[dim]Ledger: {len(ledger_ctx.splitlines())} lines of known issues[/dim]")
    except Exception as e:
        console.print(f"[yellow]Ledger context unavailable: {e}[/yellow]")

    # 12. 执行 LangGraph 工作流 (带 checkpointer)
    console.print("\n[bold]执行工作流...[/bold]\n")

    from .workflows.coding_graph import compile_graph
    app_graph = compile_graph(thread_id=run_id)

    # Trace marker: persist diagnostic snapshot before workflow starts
    _write_trace(run_dir, last_node="", last_event="workflow_started",
                 last_model="", last_backend="",
                 started_at=datetime.now(timezone.utc).isoformat())

    final_state = None
    from .task_queue import mark_task_running, mark_task_finished
    mark_task_running(task_id, run_id)

    final_state = None
    _should_cleanup = False  # set to True only for non-deliverable outcomes (Defect 1 fix)

    try:
        final_state = app_graph.invoke(
            state_dict,
            config={"configurable": {"thread_id": run_id}, "recursion_limit": 50},
        )
    except Exception as e:
        console.print(f"[red]工作流执行错误: {e}[/red]")
        # Classify timeout/blocker category for diagnostics
        msg = str(e).lower()
        if "timeout" in msg or "timed out" in msg:
            if "proxy" in msg or "127.0.0.1" in msg or "localhost" in msg:
                category = "PROXY_TIMEOUT"
            else:
                category = "MODEL_TIMEOUT"
        elif any(w in msg for w in ("connection refused", "unreachable", "name resolution",
                                      "no route", "econnrefused", "could not connect")):
            category = "BACKEND_UNAVAILABLE"
        elif any(w in msg for w in ("unauthorized", "auth", "forbidden", "permission")):
            category = "BACKEND_UNAVAILABLE"
        else:
            category = "UNKNOWN_TIMEOUT"
        _write_trace(run_dir, last_node="workflow", last_event="exception",
                     last_model=state_dict.get("executor_model", ""),
                     last_backend="workflow_executor",
                     started_at=state_dict.get("started_at", ""))
        mark_task_finished(task_id, "failed", run_id)
        # 保存错误状态
        state_dict["status"] = "failed"
        state_dict["error_message"] = str(e)
        state_dict["timeout_category"] = category
        state_dict["updated_at"] = WorkflowState().updated_at
        save_run_json(run_dir, "state.json", state_dict)
        _should_cleanup = True  # exception = non-deliverable (Defect 1 fix)
        cleanup_result = _cleanup_isolation(project_path, worktree_path, ai_branch,
                                           original_branch, _worktree_created,
                                           _branch_created, run_dir, apply_changes)
        state_dict.update(cleanup_result)
        save_run_json(run_dir, "state.json", state_dict)
        raise typer.Exit(1)

    # Defect 1 fix: only cleanup for non-deliverable statuses (not "passed")
    cleanup_result = {"cleanup_success": True, "cleanup_error": ""}
    if apply_changes and (_worktree_created or _branch_created):
        status = final_state.get("status", "unknown")
        if status in ("failed", "blocked", "human_required", "running", "pending"):
            _should_cleanup = True
            cleanup_result = _cleanup_isolation(project_path, worktree_path, ai_branch,
                                               original_branch, _worktree_created,
                                               _branch_created, run_dir, apply_changes)

    # 统一持久化最终状态 — 无论 workflow 走到哪个节点结束
    status = final_state.get("status", "unknown")
    if status in ("running", "pending"):
        # workflow 未正常结束，视为 failed
        status = "failed"
        final_state["status"] = "failed"

    # Defect 3RR fix: merge cleanup result into final_state before persisting,
    # so cleanup fields are not lost when final_state overwrites state.json
    final_state.update(cleanup_result)
    final_state["updated_at"] = WorkflowState().updated_at
    save_run_json(run_dir, "state.json", final_state)
    mark_task_finished(task_id, status, run_id,
                       blocked_reason=final_state.get("error_message", ""))
    # Chain evidence
    _write_chain_evidence(run_dir, final_state)

    # Evidence verification
    _evidence_result = verify_run_evidence(run_id, project_id)
    final_state["evidence_verified"] = _evidence_result
    if not _evidence_result["evidence_ok"] or not _evidence_result["chain_trusted"]:
        console.print(f"[yellow]Evidence incomplete: {_evidence_result.get('reasons', [])}[/yellow]")
    save_run_json(run_dir, "state.json", final_state)

    # Derive and merge issue ledger delta
    try:
        from .issue_ledger import derive_issues_from_state, write_run_delta, merge_delta
        run_issues = derive_issues_from_state(final_state)
        if run_issues:
            write_run_delta(run_dir, run_issues)
            merge_result = merge_delta({"issues": run_issues}, run_id)
            console.print(f"[dim]Ledger: {merge_result['merged']} issues recorded[/dim]")
    except Exception as e:
        console.print(f"[yellow]Ledger update failed: {e}[/yellow]")

    # 如果 human_gate 结束但 finalizer 没走到，补生成 final-report
    final_report_path = Path(run_dir) / "final-report.md"
    if not final_report_path.exists() and status in ("human_required", "blocked", "failed"):
        _generate_fallback_final_report(run_dir, final_state)

    status_styles = {
        "passed": "green",
        "failed": "red",
        "blocked": "red",
        "human_required": "yellow",
    }
    style = status_styles.get(status, "")
    console.print(f"\n[bold {style}]最终状态: {status}[/bold {style}]")
    console.print(f"[dim]报告: {run_dir}/final-report.md[/dim]")

    if status == "human_required":
        console.print(f"\n[yellow]Human gate required. 查看: {run_dir}/human-gate.md[/yellow]")
        console.print(f"[dim]当前运行已通过 checkpointer 保存 (thread_id={run_id})[/dim]")
        console.print(f"[dim]审批后，重新运行 aihub run start --apply 继续[/dim]")

    return {"run_id": run_id, "run_dir": run_dir, "status": status}


def _cleanup_isolation(project_path: str, worktree_path: str, ai_branch: str,
                      original_branch: str, _worktree_created: bool,
                      _branch_created: bool, run_dir: str,
                      apply_changes: bool) -> dict[str, Any]:
    """Clean up isolation resources (worktree/branch) for non-deliverable outcomes.

    Returns a dict with keys cleanup_success (bool) and cleanup_error (str).
    Caller is responsible for merging these into the final state before persisting.

    Does NOT write state.json — that is the caller's responsibility so the
    cleanup fields are not overwritten by a subsequent final_state save.

    Defect 1 fix: Only called when status is non-deliverable (failed/blocked/human_required/exception).
    Defect 2 fix: Checkout original_branch before deleting temp branch to avoid
    "cannot delete branch you are on" errors.
    Defect 3RR fix: Returns cleanup result instead of writing state.json internally.
    """
    if not apply_changes or not (_worktree_created or _branch_created):
        return {"cleanup_success": True, "cleanup_error": ""}

    from .git_utils import remove_worktree, delete_branch, checkout_branch
    cleanup_success = True
    cleanup_error = ""

    if _worktree_created and worktree_path:
        ok, msg = remove_worktree(project_path, worktree_path)
        if not ok:
            cleanup_success = False
            cleanup_error = f"worktree_remove: {msg}"
            console.print(f"[yellow]Worktree 清理失败: {msg}[/yellow]")
        else:
            console.print(f"[dim]Worktree 已清理: {worktree_path}[/dim]")

    if _branch_created:
        # Defect 2 fix: checkout original_branch first so delete_branch can succeed
        if original_branch:
            co_ok, co_msg = checkout_branch(project_path, original_branch)
            if not co_ok:
                # Defect 3RR fix: checkout failure must be recorded as cleanup failure
                cleanup_success = False
                if cleanup_error:
                    cleanup_error += f"; checkout_original: {co_msg}"
                else:
                    cleanup_error = f"checkout_original: {co_msg}"
                console.print(f"[yellow]Checkout 回 {original_branch} 失败: {co_msg}[/yellow]")
        ok, msg = delete_branch(project_path, ai_branch)
        if not ok:
            cleanup_success = False
            if cleanup_error:
                cleanup_error += f"; branch_delete: {msg}"
            else:
                cleanup_error = f"branch_delete: {msg}"
            console.print(f"[yellow]分支清理失败: {msg}[/yellow]")
        else:
            console.print(f"[dim]分支已清理: {ai_branch}[/dim]")

    # Persist cleanup result to isolation-cleanup.json (dedicated artifact)
    # state.json persistence is handled by the caller to prevent overwrite
    save_run_json(run_dir, "isolation-cleanup.json", {
        "cleanup_success": cleanup_success,
        "cleanup_error": cleanup_error,
        "worktree_created": _worktree_created,
        "branch_created": _branch_created,
        "cleaned_at": datetime.now(timezone.utc).isoformat(),
    })
    return {"cleanup_success": cleanup_success, "cleanup_error": cleanup_error}


def _generate_fallback_final_report(run_dir: str, state: dict[str, Any]) -> None:
    """当 finalizer 未走到时，生成基础 final-report."""
    from datetime import datetime, timezone
    status = state.get("status", "unknown")
    state["updated_at"] = datetime.now(timezone.utc).isoformat()
    content = f"""# Final Report (auto-generated)

## Run Info
- **Run ID**: {state.get("run_id", "")}
- **Project**: {state.get("project_name", "")} ({state.get("project_id", "")})
- **Task**: {state.get("task_title", "")} ({state.get("task_id", "")})
- **Risk**: {state.get("task_risk", "medium")}
- **Mode**: {'dry-run' if state.get("dry_run", True) else 'apply'}
- **Status**: {status}

## Reason
The workflow ended with status `{status}` before reaching the finalizer node.
This is normal for human_gate and blocked outcomes.

## Backend Calls
{_render_cli_backend_calls(state.get("backend_calls", {}))}

## Evidence Files
All evidence is in: {run_dir}
"""
    save_run_file(run_dir, "final-report.md", content)
    # 生成 failure-analysis.md（human_gate 路径不经过 finalizer）
    from .nodes.finalizer import build_failure_analysis
    fa = build_failure_analysis(state)
    save_run_file(run_dir, "failure-analysis.md", fa)


def _resolve_boundary(forbidden_files: list[str], allowed_files: list[str]) -> list[str]:
    """Remove exact file matches from forbidden_files. allowed_files win.

    Directory patterns (e.g. src/) are preserved — only exact file paths are removed.
    """
    allowed_set = {f.strip() for f in allowed_files if f.strip()
                   and not f.strip().endswith("/")}  # exact files only, not dirs
    return [f for f in forbidden_files
            if f.strip() not in allowed_set or f.strip().endswith("/")]


def _write_trace(run_dir: str, *, last_node: str, last_event: str,
                 last_model: str, last_backend: str,
                 started_at: str = "", updated_at: str = "",
                 timeout_budget_seconds: int = 0,
                 timeout_source: str = "",
                 elapsed_seconds: float = 0.0,
                 planner_prompt_chars: int = 0,
                 workflow_text_chars: int = 0,
                 task_description_chars: int = 0,
                 allowed_files_count: int = 0,
                 forbidden_files_count: int = 0) -> None:
    """Write diagnostic trace to run_dir/trace.json. Survives node crashes."""
    from datetime import datetime, timezone
    trace_path = Path(run_dir) / "trace.json"
    trace = {}
    if trace_path.exists():
        try:
            trace = json.loads(trace_path.read_text(encoding="utf-8"))
        except Exception:
            pass
    trace["last_node"] = last_node or trace.get("last_node", "")
    trace["last_event"] = last_event
    trace["last_model"] = last_model or trace.get("last_model", "")
    trace["last_backend"] = last_backend or trace.get("last_backend", "")
    trace["started_at"] = started_at or trace.get("started_at", "")
    trace["updated_at"] = updated_at or datetime.now(timezone.utc).isoformat()
    # v1.5: timeout budget + prompt metrics (preserve existing if zero)
    if timeout_budget_seconds:
        trace["timeout_budget_seconds"] = timeout_budget_seconds
    if timeout_source:
        trace["timeout_source"] = timeout_source
    if elapsed_seconds:
        trace["elapsed_seconds"] = elapsed_seconds
    if planner_prompt_chars:
        trace["planner_prompt_chars"] = planner_prompt_chars
    if workflow_text_chars:
        trace["workflow_text_chars"] = workflow_text_chars
    if task_description_chars:
        trace["task_description_chars"] = task_description_chars
    if allowed_files_count or "allowed_files_count" not in trace:
        trace["allowed_files_count"] = allowed_files_count
    if forbidden_files_count or "forbidden_files_count" not in trace:
        trace["forbidden_files_count"] = forbidden_files_count
    trace_path.write_text(json.dumps(trace, indent=2, ensure_ascii=False), encoding="utf-8")


def verify_run_evidence(run_id: str, project_id: str, hub_dir_override: Path | None = None) -> dict:
    """共享函数：run verify 三态判定。run verify CLI 和 goal_runner 共用."""
    if hub_dir_override is None:
        from .config_loader import _hub_dir as _config_hub_dir
        hub_dir = _config_hub_dir()
    else:
        hub_dir = Path(hub_dir_override)
    rd = hub_dir / "runs" / project_id / run_id
    if not rd.exists():
        return {"evidence_ok": False, "chain_trusted": False, "final_report_consistent": False,
                "status": "unknown", "reasons": ["run directory not found"]}
    run_governance = summarize_run_governance(rd)
    missing = run_governance.get("missing_files", [])
    reasons = []
    if not run_governance.get("evidence_ok", False):
        reasons.append(f"evidence missing: {', '.join(missing)}")
    if not run_governance.get("chain_trusted", False):
        reasons.append(
            f"chain {run_governance.get('chain_status', 'MISSING')} "
            f"(status={run_governance.get('run_status', 'unknown')})"
        )
    if not run_governance.get("final_report_consistent", False):
        reasons.append("final report inconsistent with state.status")

    return {
        "evidence_ok": run_governance.get("evidence_ok", False),
        "chain_trusted": run_governance.get("chain_trusted", False),
        "final_report_consistent": run_governance.get("final_report_consistent", False),
        "status": run_governance.get("run_status", "unknown"),
        "reasons": reasons,
        "evidence_files_present": run_governance.get("present_files", []),
        "evidence_files_missing": missing,
        "chain_status": run_governance.get("chain_status", "MISSING"),
        "final_report_status": run_governance.get("final_report_status", "MISSING"),
        "governance": run_governance.get("governance", {}),
        "run_governance": run_governance,
    }


def _write_chain_evidence(run_dir: str, state: dict) -> None:
    """生成 chain-evidence.json."""
    import json as _j, hashlib as _hl, os as _os
    bc = state.get("backend_calls", {})
    evidence = {
        "run_id": state.get("run_id", ""),
        "status": state.get("status", ""),
        "backend": "opencode",
        "nodes": {},
    }
    for node in ["planner", "executor", "reviewer", "fixer", "finalizer"]:
        info = bc.get(node, {})
        if not isinstance(info, dict):
            evidence["nodes"][node] = {"called": False}
            continue
        entry = {
            "backend": info.get("backend", "?"),
            "requested_model": info.get("requested_model", info.get("model", "?")),
            "effective_model": info.get("effective_model", info.get("model", "?")),
            "exit_code": info.get("exit_code", -1),
            "fallback_from": info.get("fallback_from", ""),
        }
        # Log hashes
        for log_name in ["stdout_log", "stderr_log"]:
            path = info.get(log_name, "")
            if path and _os.path.exists(path):
                entry[f"{log_name}_sha256"] = _hl.sha256(Path(path).read_bytes()).hexdigest()[:16]
        # Parse tokens from stderr
        stderr_path = info.get("stderr_log", "")
        if stderr_path and _os.path.exists(stderr_path):
            try:
                for line in Path(stderr_path).read_text(encoding="utf-8", errors="replace").split("\n"):
                    if "tokens used" in line.lower():
                        entry["tokens_used"] = line.strip()
                    if "session id" in line.lower():
                        entry["session_id"] = line.split(":")[-1].strip()
            except Exception:
                pass
        evidence["nodes"][node] = entry

    plan_audit_result = state.get("plan_audit_result")
    if plan_audit_result:
        evidence["nodes"]["plan_auditor"] = {
            "called": True,
            "result": plan_audit_result,
            "blocked": plan_audit_result == "blocked",
            "human_required": plan_audit_result == "human_required",
        }

    Path(run_dir, "chain-evidence.json").write_text(
        _j.dumps(evidence, indent=2, ensure_ascii=False), encoding="utf-8")


# ============================================================
# paper 命令 (A17: Paper Review Workflow CLI)
# ============================================================

paper_app = typer.Typer(help="Paper review workflow management")
app.add_typer(paper_app, name="paper")

def _paper_runtime():
    """Lazy import of paper_runtime (avoids circular / heavy import at CLI load)."""
    from .context_layer.adapters.paper_runtime import (
        create_paper_run,
        execute_paper_run,
        resume_paper_run,
        get_paper_run_status,
        sanitize_run_id,
        redact_state,
    )
    return {
        "create": create_paper_run,
        "execute": execute_paper_run,
        "resume": resume_paper_run,
        "status": get_paper_run_status,
        "sanitize": sanitize_run_id,
        "redact": redact_state,
    }

def _redact_str(text: str) -> str:
    """Redact sensitive field names from free-form strings (A17 L3 + A18B fix).

    Handles both simple patterns (paragraph_text: ...) and JSON/dict quoted
    forms ("paragraph_text": "...").  Prevents accidental leakage of sensitive
    field values in warnings/errors/issue descriptions.
    """
    import re as _re
    for field in ("paragraph_text", "writelab_token"):
        # Simple: field: value  or  field=value  (to end of line)
        text = _re.sub(
            rf"({field})\s*[:=]\s*.+",
            rf"\1: [REDACTED]",
            text,
            flags=_re.IGNORECASE,
        )
        # JSON-quoted: "field": "..."  or  "field": <any-value>
        text = _re.sub(
            rf'("{field}")\s*:\s*"[^"]*"',
            rf'\1: "[REDACTED]"',
            text,
            flags=_re.IGNORECASE,
        )
    for field in ("paragraph", "matched_text", "text_span"):
        text = _re.sub(
            rf"({field})\s*[:=]\s*.+",
            rf"\1: [REDACTED]",
            text,
            flags=_re.IGNORECASE,
        )
        text = _re.sub(
            rf'("{field}")\s*:\s*"[^"]*"',
            rf'\1: "[REDACTED]"',
            text,
            flags=_re.IGNORECASE,
        )
    text = _re.sub(
        r"\bAuthorization\s*:\s*Bearer\s+[A-Za-z0-9._-]+",
        "Authorization: Bearer [REDACTED]",
        text,
        flags=_re.IGNORECASE,
    )
    return text

def _deep_redact(obj):
    """Recursively redact sensitive fields in a JSON-serialisable object (A18B).

    Replaces values of known sensitive keys with '[REDACTED]'.
    Also applies _redact_str to all string values to catch embedded patterns.
    """
    _SENSITIVE_KEYS = {
        "paragraph_text",
        "writelab_token",
        "paragraph",
        "matched_text",
        "text_span",
    }
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            if k.lower() in _SENSITIVE_KEYS:
                out[k] = "[REDACTED]"
            else:
                out[k] = _deep_redact(v)
        return out
    if isinstance(obj, list):
        return [_deep_redact(item) for item in obj]
    if isinstance(obj, str):
        return _redact_str(obj)
    return obj

def _paper_acceptance_status(state: dict[str, Any]) -> str:
    """Return the acceptance status, independent from workflow status."""
    status = state.get("acceptance_status", "")
    if status:
        return str(status)
    acceptance = state.get("acceptance_result", {})
    if isinstance(acceptance, dict):
        return str(acceptance.get("status", "") or "")
    return ""

def _paper_is_final_acceptance(acceptance_status: str) -> bool:
    """Only a structured accepted status can be treated as final acceptance."""
    return acceptance_status == "accepted"

def _paper_final_acceptance_label(acceptance_status: str) -> str:
    return "yes" if _paper_is_final_acceptance(acceptance_status) else "no"

def _print_paper_acceptance_boundary(state: dict[str, Any]) -> None:
    """Print CLI-safe acceptance fields without upgrading workflow status."""
    acceptance_status = _paper_acceptance_status(state)
    if acceptance_status:
        console.print(f"  Acceptance: {acceptance_status}")
    console.print(f"  Final acceptance: {_paper_final_acceptance_label(acceptance_status)}")

def _scan_paper_sensitive_text(text: str, path: str) -> list[dict[str, str]]:
    """Return privacy findings for text without including matched payloads."""
    import re as _re

    q = r'(?:\\"|")'
    rules = [
        (
            "unredacted_sensitive_json_field",
            _re.compile(
                rf"{q}(?:paragraph_text|writelab_token){q}\s*:\s*"
                rf"{q}(?!\[REDACTED\]{q}|{q}\s*)[^\"\\]+{q}",
                _re.IGNORECASE,
            ),
        ),
        (
            "bearer_token",
            _re.compile(r"\bAuthorization\s*:\s*Bearer\s+[A-Za-z0-9._-]+", _re.IGNORECASE),
        ),
        (
            "writelab_live_paragraph_payload",
            _re.compile(
                rf"{q}paragraph{q}\s*:\s*{q}(?!\[REDACTED\]{q}|{q}\s*)[^\"\\]+{q}",
                _re.IGNORECASE,
            ),
        ),
        (
            "writelab_matched_text_payload",
            _re.compile(
                rf"{q}(?:matched_text|text_span){q}\s*:\s*"
                rf"{q}(?!\[REDACTED\]{q}|{q}\s*)[^\"\\]+{q}",
                _re.IGNORECASE,
            ),
        ),
    ]

    findings: list[dict[str, str]] = []
    for rule_name, pattern in rules:
        if pattern.search(text):
            findings.append({"path": path, "rule": rule_name})
    labeled_pattern = _re.compile(
        r"\b(?:paragraph_text|writelab_token|paragraph|matched_text|text_span)\b"
        r"[ \t]*[:=][ \t]*(?P<value>[^,\n;`}{]+)",
        _re.IGNORECASE,
    )
    for match in labeled_pattern.finditer(text):
        value = match.group("value").strip().strip('"').strip("\\")
        if not value.startswith("[REDACTED]"):
            findings.append({"path": path, "rule": "unredacted_sensitive_labeled_value"})
            break
    return findings

def _paper_runtime_authorization_summary(state: dict[str, Any]) -> dict[str, Any]:
    """Return reviewer-safe RuntimeAuthorization metadata without raw data fields."""
    auth = state.get("runtime_authorization")
    if not isinstance(auth, dict):
        return {
            "present": False,
            "authorization_id": "",
            "preflight_status": "",
            "human_gate_ref": "",
            "paper_sensitive_input_policy": "",
            "redaction_required": False,
            "allowed_sensitive_field_count": 0,
        }

    data_policy = auth.get("data_policy")
    if not isinstance(data_policy, dict):
        data_policy = {}
    allowed_fields = data_policy.get("allowed_sensitive_fields") or []
    if not isinstance(allowed_fields, list):
        allowed_fields = []
    return {
        "present": True,
        "authorization_id": _redact_str(str(auth.get("authorization_id", ""))),
        "preflight_status": str(auth.get("preflight_status", "")),
        "human_gate_ref": _redact_str(str(auth.get("human_gate_ref", ""))),
        "paper_sensitive_input_policy": str(data_policy.get("paper_sensitive_input", "")),
        "redaction_required": data_policy.get("redaction_required") is True,
        "allowed_sensitive_field_count": len(allowed_fields),
    }

def _build_paper_reviewer_pack(
    state: dict[str, Any],
    report: dict[str, Any],
    artifact_chain: list[dict[str, str]],
    warnings_list: list[dict[str, str]],
) -> dict[str, Any]:
    """Build a redacted reviewer pack boundary for closeout reports."""
    acceptance_status = str(report.get("acceptance", {}).get("status", "unknown"))
    workflow_final_acceptance = _paper_is_final_acceptance(acceptance_status)
    report_text = json.dumps(report, sort_keys=True, ensure_ascii=False, default=str)
    privacy_findings = _scan_paper_sensitive_text(report_text, "closeout-report")
    evidence_manifest = report.get("evidence_manifest", {})

    return {
        "pack_version": "1.0",
        "profile": "paper_redacted_reviewer_pack",
        "run_id": report.get("run_id", ""),
        "task_id": report.get("task_id", ""),
        "contains_real_paper_full_text": False,
        "contains_user_private_text": False,
        "contains_raw_transcript": False,
        "contains_memory_write": False,
        "contains_external_upload": False,
        "redaction_applied": True,
        "manual_review_required": (
            bool(state.get("human_required", False)) or not workflow_final_acceptance
        ),
        "memory_write_policy": "none",
        "summary_is_non_authoritative": True,
        "cannot_claim_final_success": True,
        "reviewer_pack_is_final_verdict": False,
        "workflow_report_is_final_verdict": False,
        "test_summary_is_final_acceptance": False,
        "zip_validation_is_final_acceptance": False,
        "final_verdict_source": "agent_acceptance_final_verdict",
        "workflow_final_acceptance_source": "acceptance.status",
        "workflow_final_acceptance": workflow_final_acceptance,
        "runtime_authorization": _paper_runtime_authorization_summary(state),
        "privacy_scan": {
            "passed": len(privacy_findings) == 0,
            "finding_count": len(privacy_findings),
            "findings": privacy_findings[:20],
        },
        "evidence_pointers": {
            "content_hash_field": "content_hash",
            "artifact_chain_field": "artifact_chain",
            "artifact_count": len(artifact_chain),
            "evidence_manifest_file_count": evidence_manifest.get("file_count", 0)
            if isinstance(evidence_manifest, dict) else 0,
            "warning_count": len(warnings_list),
        },
    }

def _scan_paper_audit_sensitive_file(path: Path, arcname: str) -> list[dict[str, str]]:
    """Return privacy findings for a text artifact before audit ZIP packaging.

    The finding deliberately omits matched values so the audit failure path does
    not echo private paper text or tokens while explaining which artifact failed.
    """
    if path.suffix.lower() not in {".json", ".md", ".txt", ".yaml", ".yml"}:
        return []

    text = path.read_text(encoding="utf-8", errors="replace")
    return _scan_paper_sensitive_text(text, arcname)

_PAPER_BUSINESS_COMMAND_CHAIN = [
    "paper create",
    "paper run",
    "paper go",
    "paper resume",
    "paper status",
    "paper list",
    "paper ledger",
    "paper evidence",
    "paper validate",
    "paper report",
    "paper audit",
    "paper verify",
    "paper checkpoint",
    "paper verify-chain",
]

_PAPER_BUSINESS_EVIDENCE_MATRIX = [
    {
        "capability": "create",
        "command": "paper create",
        "evidence": ["tests/test_paper_cli.py::TestPaperCreate"],
        "validation_kind": "mock_cli",
    },
    {
        "capability": "run",
        "command": "paper run",
        "evidence": ["tests/test_paper_cli.py::TestPaperRun"],
        "validation_kind": "mock_cli",
    },
    {
        "capability": "go_resume_lifecycle",
        "command": "paper go -> paper resume",
        "evidence": ["tests/test_paper_a19_safe_e2e.py::TestA19LifecycleChain"],
        "validation_kind": "synthetic_offline",
    },
    {
        "capability": "status_list",
        "command": "paper status -> paper list",
        "evidence": ["tests/test_paper_a19_safe_e2e.py::TestA19LifecycleChain"],
        "validation_kind": "synthetic_offline",
    },
    {
        "capability": "ledger_evidence_validate",
        "command": "paper ledger -> paper evidence -> paper validate",
        "evidence": ["tests/test_paper_a19_safe_e2e.py::TestA19LifecycleChain"],
        "validation_kind": "synthetic_offline",
    },
    {
        "capability": "report_reviewer_pack",
        "command": "paper report",
        "evidence": [
            "tests/test_paper_a23_closeout_report.py",
            "tests/test_paper_a23b_closeout_hardening.py::TestA23BReviewerPackBoundary",
        ],
        "validation_kind": "synthetic_offline",
    },
    {
        "capability": "audit_privacy_gate",
        "command": "paper audit",
        "evidence": [
            "tests/test_paper_a25_audit_package.py",
            "tests/test_paper_a26_audit_hardening.py::TestA26SensitivePayloadGuard",
        ],
        "validation_kind": "synthetic_offline",
    },
    {
        "capability": "verify",
        "command": "paper verify",
        "evidence": ["tests/test_paper_a28_verify_command.py"],
        "validation_kind": "synthetic_offline",
    },
    {
        "capability": "checkpoint_verify_chain",
        "command": "paper checkpoint -> paper verify-chain",
        "evidence": [
            "tests/test_paper_a32_anchor_chain_verify.py",
            "tests/test_paper_a34_external_checkpoint.py",
            "tests/test_paper_a35_checkpoint_strict_verify.py",
        ],
        "validation_kind": "synthetic_offline",
    },
    {
        "capability": "paper_graph_offline",
        "command": "paper runtime graph",
        "evidence": ["tests/test_paper_graph.py"],
        "validation_kind": "synthetic_offline",
    },
    {
        "capability": "real_pilot_local_dry_run",
        "command": "paper real-pilot-dry-run",
        "evidence": ["tests/test_paper_real_pilot_local_dry_run.py"],
        "validation_kind": "synthetic_offline",
    },
    {
        "capability": "real_pilot_preauth_packet",
        "command": "paper real-pilot-preauth",
        "evidence": ["tests/test_paper_real_pilot_preauth_packet.py"],
        "validation_kind": "synthetic_offline",
    },
    {
        "capability": "schema_privacy_guards",
        "command": "paper business-validate",
        "evidence": ["tests/test_paper_schema_raw_payload_guards.py"],
        "validation_kind": "synthetic_offline",
    },
    {
        "capability": "capability_map_artifact",
        "command": "paper capability-map",
        "evidence": [
            "tests/test_paper_business_capability_validation.py::test_capability_map_cli_emits_schema_valid_json",
            "tests/test_paper_mvp_contracts.py::test_capability_map_json_matches_markdown_and_schema",
            "tests/test_paper_mvp_contracts.py::test_capability_map_schema_rejects_missing_or_duplicate_capabilities",
        ],
        "validation_kind": "synthetic_offline",
    },
    {
        "capability": "citation_lookup_workflow",
        "command": "paper citation-lookup-workflow",
        "evidence": ["tests/test_paper_citation_lookup_workflow_integration.py"],
        "validation_kind": "synthetic_offline",
    },
    {
        "capability": "zotero_web_api_metadata_manifest",
        "command": "paper zotero-web-metadata-pilot --manifest-output",
        "evidence": ["tests/test_zotero_web_metadata_pilot.py"],
        "validation_kind": "mock_transport_or_fixture",
    },
    {
        "capability": "metadata_pipeline_readiness",
        "command": "paper metadata-pipeline-readiness",
        "evidence": ["tests/test_paper_metadata_pipeline_readiness.py"],
        "validation_kind": "synthetic_offline",
    },
    {
        "capability": "zotero_metadata_closeout_cli",
        "command": "paper zotero-metadata-closeout",
        "evidence": ["tests/test_paper_zotero_metadata_local_batch_closeout.py"],
        "validation_kind": "synthetic_offline",
    },
    {
        "capability": "pdf_redacted_excerpt_pilot",
        "command": "paper pdf-redacted-excerpt-pilot",
        "evidence": ["tests/test_paper_pdf_redacted_excerpt_pilot.py"],
        "validation_kind": "synthetic_offline",
    },
    {
        "capability": "obsidian_allowlisted_note_pilot",
        "command": "paper obsidian-allowlisted-note-pilot",
        "evidence": ["tests/test_obsidian_note_adapter.py"],
        "validation_kind": "synthetic_offline",
    },
    {
        "capability": "rag_local_fixture_pilot",
        "command": "paper rag-local-fixture-pilot",
        "evidence": ["tests/test_paper_rag_evidence.py"],
        "validation_kind": "synthetic_offline",
    },
]

_PAPER_BUSINESS_SD07_GATE = {
    "gate_id": "SD-07",
    "task_spec_id": "TS-OPENCODE-PAPER-SD07-REPORT-UX",
    "gate_status": "visible_candidate_gate",
    "candidate_evidence_only": True,
    "real_paper_content_status": "blocked_until_fresh_runtime_authorization",
    "live_writelab_status": "retired_non_core",
    "fresh_runtime_authorization_required": True,
    "dedicated_pilot_taskspec_required_for_live_writelab": False,
}

_PAPER_MVP_STATUS = {
    "paper_capability_map_status": "candidate_ready",
    "citation_integrity_gate_status": "candidate_ready",
    "zotero_metadata_adapter_status": "metadata_only_candidate",
    "obsidian_note_adapter_status": "fixture_only_candidate",
    "rag_evidence_contract_status": "candidate_ready",
    "citation_lookup_workflow_status": "candidate_ready",
    "writelab_diagnostic_boundary_status": "retired_non_core",
    "privacy_boundary_status": "private_sources_blocked_without_authorization",
    "human_authorization_required_for_private_sources": True,
}

_PAPER_REAL_PILOT_PROGRESS = {
    "offline_mvp_candidate_ready": True,
    "real_pilot_authorization_gate_ready": True,
    "local_real_pilot_dry_run_ready": True,
    "real_pilot_preauth_packet_ready": True,
    "agent_acceptance_paper_real_pilot_rules_ready": True,
    "local_only_dry_run_after_agent_acceptance_ready": True,
    "runtime_authorization_request_ready": True,
    "human_runtime_authorization_decision_ready": True,
    "real_zotero_metadata_only_pilot_entrypoint_ready": True,
    "zotero_web_api_metadata_manifest_ready": True,
    "metadata_pipeline_readiness_ready": True,
    "pdf_redacted_excerpt_pilot_entrypoint_ready": True,
    "obsidian_allowlisted_note_pilot_entrypoint_ready": True,
    "rag_local_fixture_pilot_entrypoint_ready": True,
    "real_private_source_access_blocked": True,
    "live_writelab_blocked": True,
    "final_acceptance_not_claimed": True,
    "agent_acceptance_rule_required_before_real_pilot": True,
}

_PAPER_ZOTERO_WEB_API_METADATA_MANIFEST = {
    "cli_command": "paper zotero-web-metadata-pilot --manifest-output",
    "report_schema_path": "schemas/paper_zotero_web_api_metadata_only_pilot_report.schema.json",
    "manifest_schema_path": "schemas/paper_zotero_web_api_metadata_only_evidence_manifest.schema.json",
    "manifest_written_only_for_pass": True,
    "blocked_reports_write_manifest": False,
    "live_api_required_for_business_validation": False,
    "raw_payloads_persisted": False,
    "candidate_evidence_only": True,
    "final_acceptance_claimed": False,
}

_PAPER_PDF_REDACTED_EXCERPT_PILOT = {
    "cli_command": "paper pdf-redacted-excerpt-pilot",
    "authorization_command": "paper real-pilot-authorize-pdf-excerpt",
    "report_schema_path": "schemas/paper_pdf_redacted_excerpt_pilot_report.schema.json",
    "runtime_smoke_status": "PASS_REDACTED_EXCERPT",
    "live_pdf_required_for_business_validation": False,
    "raw_full_text_persisted": False,
    "raw_paragraph_text_persisted": False,
    "live_writelab_called": False,
    "candidate_evidence_only": True,
    "final_acceptance_claimed": False,
}

_PAPER_OBSIDIAN_ALLOWLISTED_NOTE_PILOT = {
    "cli_command": "paper obsidian-allowlisted-note-pilot",
    "report_schema_path": "schemas/paper_obsidian_allowlisted_note_pilot_report.schema.json",
    "vault_scan_required_for_business_validation": False,
    "raw_note_persisted": False,
    "raw_note_path_persisted": False,
    "candidate_evidence_only": True,
    "final_acceptance_claimed": False,
}

_PAPER_RAG_LOCAL_FIXTURE_PILOT = {
    "cli_command": "paper rag-local-fixture-pilot",
    "report_schema_path": "schemas/paper_rag_local_fixture_pilot_report.schema.json",
    "private_rag_required_for_business_validation": False,
    "raw_query_persisted": False,
    "raw_source_text_persisted": False,
    "private_rag_payload_persisted": False,
    "candidate_evidence_only": True,
    "final_acceptance_claimed": False,
}

def _paper_capability_map_artifact_path() -> Path:
    """Return the checked-in synthetic/offline paper capability map artifact."""
    return (
        Path(__file__).resolve().parents[2]
        / "docs"
        / "paper"
        / "PAPER_CAPABILITY_MAP.json"
    )

def _build_paper_business_validation_report(
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Build the synthetic/offline paper business validation report."""
    generated = generated_at or datetime.now(timezone.utc).isoformat()
    capability_map_artifact = _paper_capability_map_artifact_path()
    capability_map_sha256 = hashlib.sha256(
        capability_map_artifact.read_bytes()
    ).hexdigest()
    return {
        "profile": "paper_business_validation_report",
        "schema_version": "1.0",
        "validation_mode": "synthetic_offline",
        "candidate_status": "BUSINESS_CAPABILITY_VALIDATION_CANDIDATE",
        "generated_at": generated,
        "sd07_governance_gate": dict(_PAPER_BUSINESS_SD07_GATE),
        "real_pilot_progress": dict(_PAPER_REAL_PILOT_PROGRESS),
        **_PAPER_MVP_STATUS,
        "capability_map_artifact": {
            "artifact_path": "ai-workflow-hub/docs/paper/PAPER_CAPABILITY_MAP.json",
            "schema_path": "schemas/paper_capability_map.schema.json",
            "sha256": capability_map_sha256,
            "machine_readable": True,
            "closed_schema": True,
            "candidate_evidence_only": True,
        },
        "zotero_web_api_metadata_manifest": dict(
            _PAPER_ZOTERO_WEB_API_METADATA_MANIFEST
        ),
        "pdf_redacted_excerpt_pilot": dict(_PAPER_PDF_REDACTED_EXCERPT_PILOT),
        "obsidian_allowlisted_note_pilot": dict(
            _PAPER_OBSIDIAN_ALLOWLISTED_NOTE_PILOT
        ),
        "rag_local_fixture_pilot": dict(_PAPER_RAG_LOCAL_FIXTURE_PILOT),
        "command_chain": list(_PAPER_BUSINESS_COMMAND_CHAIN),
        "evidence_matrix": list(_PAPER_BUSINESS_EVIDENCE_MATRIX),
        "schema_privacy_guards": {
            "raw_payload_guard_ready": True,
            "object_closure_guard_ready": True,
            "guard_test": "tests/test_paper_schema_raw_payload_guards.py",
            "guarded_raw_fields": ["paragraph_text", "writelab_token"],
            "open_object_allowlist_policy": "documented_mvp_base_allof_fragments_only",
            "candidate_evidence_only": True,
        },
        "privacy_boundary": {
            "synthetic_or_mock_only": True,
            "contains_real_paper_full_text": False,
            "contains_live_writelab_payload": False,
            "raw_sensitive_fields_absent": True,
            "sensitive_fields_blocked_or_redacted": [
                "paragraph_text",
                "writelab_token",
                "paragraph",
                "matched_text",
                "text_span",
                "Authorization: Bearer",
            ],
        },
        "final_acceptance_boundary": {
            "candidate_evidence_is_final_acceptance": False,
            "workflow_status_is_final_acceptance": False,
            "reviewer_pack_is_final_verdict": False,
            "workflow_report_is_final_verdict": False,
            "audit_zip_validation_is_final_acceptance": False,
            "test_summary_is_final_acceptance": False,
            "final_acceptance_requires": "acceptance.status == accepted",
            "non_final_statuses": [
                "completed",
                "accepted_with_limitation",
                "needs_more_evidence",
                "human_required",
                "blocked",
                "failed",
            ],
        },
        "runtime_authorization_required_for_real_content": True,
        "known_gaps": [
            "No real paper/full-text validation in this report.",
            "No unrestricted live WriteLab or full paper review validation in this report.",
            "No live OpenCode, daemon worker, ChatGPT/CDP, or cloud execution.",
            "This report is candidate evidence and cannot claim final acceptance.",
            "Real Zotero library and real Obsidian vault access require future authorization.",
            "Agent-acceptance paper real pilot rules are ready but do not authorize real resources.",
            "RuntimeAuthorization request is metadata-only and still requires human approval.",
        ],
    }

def _build_paper_capability_map() -> dict[str, Any]:
    """Load the checked-in synthetic/offline paper capability map artifact."""
    artifact = _paper_capability_map_artifact_path()
    return json.loads(artifact.read_text(encoding="utf-8"))

def _build_paper_citation_lookup_workflow_report(
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Build the synthetic/offline citation lookup workflow report."""
    from ai_workflow_hub.context_layer.adapters.citation_lookup_workflow import (
        build_citation_lookup_workflow_report,
    )

    fixture_records = [
        {
            "source_type": "fixture_metadata",
            "source_level": "VERIFIED_SOURCE",
            "item_type": "journalArticle",
            "title": "Conservative Metadata Grounding for Paper Workflows",
            "creators": [{"firstName": "Ada", "lastName": "Lovelace"}],
            "year": 2026,
            "doi": "10.1234/metadata.grounding",
            "url": "https://example.invalid/paper",
            "citation_key": "Lovelace2026MetadataGrounding",
        },
        {
            "source_type": "fixture_metadata",
            "source_level": "VERIFIED_SOURCE",
            "item_type": "conferencePaper",
            "title": "Ambiguous Synthetic Citation Record",
            "creators": [{"firstName": "Grace", "lastName": "Hopper"}],
            "year": 2025,
            "doi": "10.4242/ambiguous.lookup",
            "citation_key": "Hopper2025AmbiguousA",
        },
        {
            "source_type": "fixture_metadata",
            "source_level": "VERIFIED_SOURCE",
            "item_type": "conferencePaper",
            "title": "Ambiguous Synthetic Citation Record",
            "creators": [{"firstName": "Grace", "lastName": "Hopper"}],
            "year": 2025,
            "doi": "10.4242/ambiguous.lookup",
            "citation_key": "Hopper2025AmbiguousB",
        },
    ]
    citation_claims = [
        {"citation_key": "Lovelace2026MetadataGrounding"},
        {"doi": "10.4242/ambiguous.lookup"},
        {"doi": "10.9999/not.available"},
    ]
    return build_citation_lookup_workflow_report(
        citation_claims=citation_claims,
        metadata_records=fixture_records,
        metadata_format="fixture_metadata",
        generated_at=generated_at,
    )

def _build_paper_metadata_pipeline_readiness_report(
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Build a local/offline metadata-only pipeline readiness report."""
    from ai_workflow_hub.context_layer.adapters.zotero_metadata_real_pilot import (
        build_zotero_metadata_local_batch_closeout_report,
    )

    generated = generated_at or datetime.now(timezone.utc).isoformat()
    business_report = _build_paper_business_validation_report(generated_at=generated)
    citation_report = _build_paper_citation_lookup_workflow_report(
        generated_at=generated
    )
    closeout_report = build_zotero_metadata_local_batch_closeout_report(
        generated_at=generated
    )
    return {
        "profile": "paper_metadata_only_pipeline_readiness_report",
        "schema_version": "1.0",
        "validation_mode": "local_offline_only",
        "pipeline_status": "METADATA_ONLY_PIPELINE_READINESS_CANDIDATE",
        "generated_at": generated,
        "task_id": "OPENCODE_PAPER_METADATA_ONLY_PIPELINE_READINESS_A1",
        "project_id": "dev-frame-opencode",
        "workflow_type": "paper",
        "command_chain": [
            "paper business-validate",
            "paper citation-lookup-workflow",
            "paper zotero-web-metadata-pilot --manifest-output",
            "paper zotero-metadata-closeout",
            "paper metadata-pipeline-readiness",
        ],
        "component_reports": [
            {
                "component_id": "business_validation",
                "command": "paper business-validate",
                "schema_path": "schemas/paper_business_validation_report.schema.json",
                "component_status": business_report["candidate_status"],
                "machine_readable": True,
                "candidate_evidence_only": True,
                "final_acceptance_claimed": False,
            },
            {
                "component_id": "citation_lookup_workflow",
                "command": "paper citation-lookup-workflow",
                "schema_path": "schemas/paper_citation_lookup_workflow_report.schema.json",
                "component_status": citation_report["citation_lookup_status"],
                "machine_readable": True,
                "candidate_evidence_only": True,
                "final_acceptance_claimed": False,
            },
            {
                "component_id": "zotero_web_api_metadata_manifest",
                "command": "paper zotero-web-metadata-pilot --manifest-output",
                "schema_path": "schemas/paper_zotero_web_api_metadata_only_evidence_manifest.schema.json",
                "component_status": "SCHEMA_BOUND_MINIMIZED_MANIFEST_READY",
                "machine_readable": True,
                "candidate_evidence_only": True,
                "final_acceptance_claimed": False,
            },
            {
                "component_id": "local_batch_closeout",
                "command": "paper zotero-metadata-closeout",
                "schema_path": "schemas/paper_zotero_metadata_local_batch_closeout_report.schema.json",
                "component_status": closeout_report["batch_status"],
                "machine_readable": True,
                "candidate_evidence_only": True,
                "final_acceptance_claimed": False,
            },
        ],
        "readiness_matrix": {
            "business_validation_manifest_bound": True,
            "citation_lookup_workflow_bound": True,
            "standalone_manifest_schema_bound": True,
            "local_closeout_manifest_bound": True,
            "reviewer_pack_boundary_bound": True,
            "runtime_authorization_required_for_real_sources": True,
            "live_resource_access_permitted": False,
            "parent_pin_requested": False,
            "final_acceptance_claimed": False,
        },
        "privacy_boundary": {
            "local_offline_only": True,
            "zotero_web_api_called": False,
            "zotero_key_file_read": False,
            "notes_read": False,
            "attachments_read": False,
            "pdf_read": False,
            "full_text_read": False,
            "obsidian_read": False,
            "private_rag_used": False,
            "live_writelab_called": False,
            "browser_cdp_or_cloud_used": False,
        },
        "evidence_manifest_policy": {
            "minimized_values_only": True,
            "raw_items_persisted": False,
            "raw_titles_persisted": False,
            "raw_abstracts_persisted": False,
            "raw_citation_values_emitted": False,
            "api_key_persisted": False,
            "raw_user_id_persisted": False,
        },
        "reviewer_boundary": {
            "pipeline_report_is_final_verdict": False,
            "test_pass_is_final_acceptance": False,
            "reviewer_pack_is_final_verdict": False,
            "agent_acceptance_required_for_final_verdict": True,
            "fresh_runtime_authorization_required_for_live_resources": True,
        },
        "known_gaps": [
            "live_zotero_api_not_called_by_this_report",
            "real_pdf_full_text_not_validated",
            "obsidian_rag_writelab_not_executed",
            "final_governance_acceptance_not_claimed",
        ],
    }

def _build_paper_plugin_pilot_closeout_report(
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Build a local/offline closeout report for plugin pilot entrypoints."""
    generated = generated_at or datetime.now(timezone.utc).isoformat()
    business_report = _build_paper_business_validation_report(generated_at=generated)
    plugin_matrix = [
        {
            "plugin_id": "pdf_redacted_excerpt_pilot",
            "command": "paper pdf-redacted-excerpt-pilot",
            "report_schema_path": "schemas/paper_pdf_redacted_excerpt_pilot_report.schema.json",
            "entrypoint_ready": business_report["real_pilot_progress"][
                "pdf_redacted_excerpt_pilot_entrypoint_ready"
            ],
            "local_offline_or_mock_only": True,
            "raw_payload_persisted": False,
            "runtime_authorization_required_for_live": True,
            "final_acceptance_claimed": False,
        },
        {
            "plugin_id": "obsidian_allowlisted_note_pilot",
            "command": "paper obsidian-allowlisted-note-pilot",
            "report_schema_path": "schemas/paper_obsidian_allowlisted_note_pilot_report.schema.json",
            "entrypoint_ready": business_report["real_pilot_progress"][
                "obsidian_allowlisted_note_pilot_entrypoint_ready"
            ],
            "local_offline_or_mock_only": True,
            "raw_payload_persisted": False,
            "runtime_authorization_required_for_live": True,
            "final_acceptance_claimed": False,
        },
        {
            "plugin_id": "rag_local_fixture_pilot",
            "command": "paper rag-local-fixture-pilot",
            "report_schema_path": "schemas/paper_rag_local_fixture_pilot_report.schema.json",
            "entrypoint_ready": business_report["real_pilot_progress"][
                "rag_local_fixture_pilot_entrypoint_ready"
            ],
            "local_offline_or_mock_only": True,
            "raw_payload_persisted": False,
            "runtime_authorization_required_for_live": True,
            "final_acceptance_claimed": False,
        },
    ]
    return {
        "profile": "paper_plugin_pilot_closeout_report",
        "schema_version": "1.0",
        "validation_mode": "local_offline_only",
        "closeout_status": "PLUGIN_PILOT_BOUNDARY_CANDIDATE",
        "generated_at": generated,
        "task_id": "OPENCODE_PLUGIN_PILOT_CLOSEOUT_A1",
        "project_id": "dev-frame-opencode",
        "workflow_type": "paper",
        "command_chain": [
            "paper business-validate",
            "paper pdf-redacted-excerpt-pilot",
            "paper obsidian-allowlisted-note-pilot",
            "paper rag-local-fixture-pilot",
            "paper plugin-pilot-closeout",
        ],
        "plugin_matrix": plugin_matrix,
        "readiness_matrix": {
            "business_validation_bound": True,
            "all_local_entrypoints_bound": all(
                row["entrypoint_ready"] for row in plugin_matrix
            ),
            "local_offline_or_mock_only": True,
            "scoped_live_smoke_bound": True,
            "runtime_authorization_required_for_live_sources": True,
            "parent_pin_requested": False,
            "final_acceptance_claimed": False,
        },
        "privacy_boundary": {
            "zotero_key_file_read": False,
            "live_zotero_api_called": False,
            "obsidian_vault_scanned": False,
            "private_rag_used": False,
            "live_writelab_called_by_closeout_report": False,
            "scoped_pdf_writelab_live_smoke_available": False,
            "pdf_full_text_persisted": False,
            "raw_query_persisted": False,
            "raw_note_persisted": False,
            "raw_payload_persisted": False,
            "browser_cdp_or_cloud_used": False,
        },
        "reviewer_boundary": {
            "closeout_report_is_final_verdict": False,
            "test_pass_is_final_acceptance": False,
            "plugin_entrypoint_ready_is_live_ready": False,
            "fresh_runtime_authorization_required_for_live_resources": True,
        },
        "known_gaps": [
            "live_zotero_api_not_called_by_this_report",
            "real_obsidian_vault_not_scanned",
            "private_rag_not_used",
            "real_pdf_full_text_not_validated",
            "final_governance_acceptance_not_claimed",
        ],
    }

def _build_paper_mvp_end_to_end_closeout_report(
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Build a compact machine-readable MVP closeout report.

    This report is a local aggregation of existing minimized reports. It does
    not read Zotero keys, PDFs, Obsidian notes, RAG sources, or call external
    diagnosis services.
    """
    generated = generated_at or datetime.now(timezone.utc).isoformat()
    business_report = _build_paper_business_validation_report(generated_at=generated)
    metadata_readiness = _build_paper_metadata_pipeline_readiness_report(
        generated_at=generated
    )
    plugin_closeout = _build_paper_plugin_pilot_closeout_report(
        generated_at=generated
    )
    return {
        "profile": "paper_mvp_end_to_end_closeout_report",
        "schema_version": "1.0",
        "validation_mode": "local_evidence_closeout",
        "closeout_status": "PAPER_MVP_END_TO_END_CLOSEOUT_CANDIDATE",
        "generated_at": generated,
        "task_id": "OPENCODE_PAPER_MVP_END_TO_END_CLOSEOUT_A1",
        "project_id": "dev-frame-opencode",
        "workflow_type": "paper",
        "component_statuses": {
            "zotero_metadata_only": {
                "status": "PASS_METADATA_ONLY",
                "source": "zotero_web_api_metadata_manifest",
                "schema_path": "schemas/paper_zotero_web_api_metadata_only_pilot_report.schema.json",
                "raw_items_persisted": False,
                "raw_titles_persisted": False,
                "raw_abstracts_persisted": False,
            },
            "pdf_redacted_excerpt": {
                "status": "PASS_REDACTED_EXCERPT",
                "source": "pdf_redacted_excerpt_pilot",
                "schema_path": "schemas/paper_pdf_redacted_excerpt_pilot_report.schema.json",
                "raw_full_text_persisted": False,
                "raw_excerpt_persisted": False,
            },
            "business_validation": {
                "status": business_report["candidate_status"],
                "schema_path": "schemas/paper_business_validation_report.schema.json",
                "candidate_evidence_only": True,
                "final_acceptance_claimed": False,
            },
            "plugin_closeout": {
                "status": plugin_closeout["closeout_status"],
                "schema_path": "schemas/paper_plugin_pilot_closeout_report.schema.json",
                "candidate_evidence_only": True,
                "final_acceptance_claimed": False,
            },
            "metadata_pipeline_readiness": {
                "status": metadata_readiness["pipeline_status"],
                "schema_path": "schemas/paper_metadata_only_pipeline_readiness_report.schema.json",
                "candidate_evidence_only": True,
                "final_acceptance_claimed": False,
            },
        },
        "command_chain": [
            "paper zotero-web-metadata-pilot --manifest-output",
            "paper pdf-redacted-excerpt-pilot",
            "paper business-validate",
            "paper plugin-pilot-closeout",
            "paper metadata-pipeline-readiness",
            "paper mvp-end-to-end-closeout",
        ],
        "evidence_zip_refs": [],
        "privacy_boundary": {
            "report_reads_live_resources": False,
            "zotero_key_file_read": False,
            "zotero_notes_or_attachments_read": False,
            "pdf_read_by_closeout_report": False,
            "external_diagnosis_called_by_closeout_report": False,
            "raw_full_text_persisted": False,
            "raw_excerpt_persisted": False,
            "raw_writelab_payload_persisted": False,
            "obsidian_vault_scanned": False,
            "private_rag_used": False,
            "browser_cdp_or_cloud_used": False,
        },
        "final_acceptance_boundary": {
            "mvp_closeout_is_final_acceptance": False,
            "mvp_closeout_is_live_ready": False,
            "paper_quality_acceptance_claimed": False,
            "production_ready_claimed": False,
            "requires_gpt_or_agent_acceptance_review": True,
            "requires_parent_pin_for_milestone": True,
        },
        "next_recommended_steps": [
            "bound_gpt_review_for_mvp_closeout",
            "agent_acceptance_rule_consumption_if_needed",
        ],
        "known_gaps": [
            "No full paper quality acceptance.",
            "No unrestricted PDF full-text pipeline.",
            "No Obsidian vault scan.",
            "No private RAG execution.",
            "No production readiness claim.",
            "Final governance acceptance remains external to this report.",
        ],
    }

def _build_paper_next_plugin_readiness_report(
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Build a local/offline queue for the next paper plugin integrations."""
    generated = generated_at or datetime.now(timezone.utc).isoformat()
    mvp_closeout = _build_paper_mvp_end_to_end_closeout_report(
        generated_at=generated
    )
    plugin_closeout = _build_paper_plugin_pilot_closeout_report(
        generated_at=generated
    )
    plugin_queue = [
        {
            "plugin_id": "zotero_metadata_web_api",
            "priority": 1,
            "recommended_action": "keep_metadata_only_as_baseline",
            "current_state": "scoped_live_smoke_available",
            "next_gate": "no_new_gate_needed_for_metadata_only_regression",
            "runtime_authorization_required": False,
            "expected_user_input": "none",
            "raw_payload_persisted": False,
            "final_acceptance_claimed": False,
        },
        {
            "plugin_id": "pdf_redacted_excerpt",
            "priority": 2,
            "recommended_action": "keep_single_pdf_excerpt_gate",
            "current_state": "scoped_pdf_excerpt_available",
            "next_gate": "fresh_single_pdf_authorization_for_new_documents",
            "runtime_authorization_required": True,
            "expected_user_input": "single_pdf_or_allowlisted_pdf_folder",
            "raw_payload_persisted": False,
            "final_acceptance_claimed": False,
        },
        {
            "plugin_id": "obsidian_allowlisted_note",
            "priority": 3,
            "recommended_action": "next_high_value_plugin_pilot",
            "current_state": "entrypoint_ready_local_fixture_only",
            "next_gate": "fresh_allowlisted_single_note_authorization",
            "runtime_authorization_required": True,
            "expected_user_input": "one_markdown_note_path_and_exact_allowlist",
            "raw_payload_persisted": False,
            "final_acceptance_claimed": False,
        },
        {
            "plugin_id": "rag_local_or_private_retrieval",
            "priority": 4,
            "recommended_action": "defer_until_obsidian_allowlist_passes",
            "current_state": "local_fixture_only",
            "next_gate": "retrieval_manifest_with_no_raw_note_or_query_payload",
            "runtime_authorization_required": True,
            "expected_user_input": "allowlisted_local_corpus_or_private_rag_manifest",
            "raw_payload_persisted": False,
            "final_acceptance_claimed": False,
        },
        {
            "plugin_id": "broad_pdf_full_text_or_vault_scan",
            "priority": 5,
            "recommended_action": "defer_low_value_high_risk_scope",
            "current_state": "blocked_by_privacy_boundary",
            "next_gate": "separate_task_spec_and_explicit_human_authorization",
            "runtime_authorization_required": True,
            "expected_user_input": "explicit_scope_if_ever_needed",
            "raw_payload_persisted": False,
            "final_acceptance_claimed": False,
        },
    ]
    return {
        "profile": "paper_next_plugin_readiness_report",
        "schema_version": "1.0",
        "validation_mode": "local_decision_support_only",
        "readiness_status": "NEXT_PLUGIN_SEQUENCE_CANDIDATE",
        "generated_at": generated,
        "task_id": "OPENCODE_PAPER_NEXT_PLUGIN_READINESS_A1",
        "project_id": "dev-frame-opencode",
        "workflow_type": "paper",
        "source_closeout_status": mvp_closeout["closeout_status"],
        "source_plugin_closeout_status": plugin_closeout["closeout_status"],
        "next_recommended_plugin": "obsidian_allowlisted_note",
        "batching_policy": {
            "do_not_request_parent_pin_per_small_slice": True,
            "batch_parent_intake_after_milestone": True,
            "bound_gpt_review_required_for_scope_expansion": True,
            "human_required_for_real_resource_expansion": True,
        },
        "plugin_queue": plugin_queue,
        "low_value_deferred_work": [
            "additional_schema_hardening_without_new_runtime_or_review_findings",
            "broad_full_text_pdf_processing",
            "whole_obsidian_vault_scan",
            "private_rag_without_evidence_manifest",
            "paper_quality_acceptance_claim_without_human_review",
        ],
        "privacy_boundary": {
            "report_reads_live_resources": False,
            "zotero_key_file_read": False,
            "pdf_read": False,
            "write_lab_called": False,
            "obsidian_vault_scanned": False,
            "private_rag_used": False,
            "browser_cdp_or_cloud_used": False,
            "raw_titles_persisted": False,
            "raw_abstracts_persisted": False,
            "raw_pdf_text_persisted": False,
            "raw_note_persisted": False,
            "raw_query_persisted": False,
            "raw_payload_persisted": False,
        },
        "reviewer_boundary": {
            "readiness_report_is_final_verdict": False,
            "plugin_sequence_is_runtime_authorization": False,
            "local_tests_are_paper_quality_acceptance": False,
            "fresh_runtime_authorization_required_for_next_real_plugin": True,
        },
        "known_gaps": [
            "bound_gpt_review_not_captured_by_this_report",
            "real_obsidian_note_not_authorized_by_this_report",
            "private_rag_not_authorized_by_this_report",
            "write_lab_quality_acceptance_not_claimed",
            "final_governance_acceptance_not_claimed",
        ],
    }

def _paper_runs_root() -> Path:
    """Return the paper runs root directory (shared with paper_runtime)."""
    return Path.home() / ".ai_workflow_hub" / "runs" / "paper"

@paper_app.command("capability-map")
def paper_capability_map(
    output: Optional[Path] = typer.Option(
        None, "--output", "-o", help="Optional path to write JSON capability map",
    ),
):
    """Emit the synthetic/offline paper capability map JSON artifact."""
    init_env()
    capability_map = _build_paper_capability_map()
    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps(capability_map, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    _emit_json(capability_map)

@paper_app.command("business-validate")
def paper_business_validate(
    output: Optional[Path] = typer.Option(
        None, "--output", "-o", help="Optional path to write JSON report",
    ),
):
    """Emit a synthetic/offline paper business validation JSON report."""
    init_env()
    report = _build_paper_business_validation_report()
    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps(report, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    _emit_json(report)

@paper_app.command("citation-lookup-workflow")
def paper_citation_lookup_workflow(
    output: Optional[Path] = typer.Option(
        None, "--output", "-o", help="Optional path to write JSON report",
    ),
):
    """Emit a synthetic/offline citation lookup workflow JSON report."""
    init_env()
    report = _build_paper_citation_lookup_workflow_report()
    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps(report, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    _emit_json(report)

@paper_app.command("metadata-pipeline-readiness")
def paper_metadata_pipeline_readiness(
    output: Optional[Path] = typer.Option(
        None, "--output", "-o", help="Optional path to write JSON report",
    ),
):
    """Emit a local/offline metadata-only paper pipeline readiness report."""
    init_env()
    report = _build_paper_metadata_pipeline_readiness_report()
    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps(report, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    _emit_json(report)

@paper_app.command("plugin-pilot-closeout")
def paper_plugin_pilot_closeout(
    output: Optional[Path] = typer.Option(
        None, "--output", "-o", help="Optional path to write JSON report",
    ),
):
    """Emit a local/offline closeout report for plugin pilot entrypoints."""
    init_env()
    report = _build_paper_plugin_pilot_closeout_report()
    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps(report, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    _emit_json(report)

@paper_app.command("next-plugin-readiness")
def paper_next_plugin_readiness(
    output: Optional[Path] = typer.Option(
        None, "--output", "-o", help="Optional path to write JSON report",
    ),
):
    """Emit a local decision-support queue for next paper plugin pilots."""
    init_env()
    report = _build_paper_next_plugin_readiness_report()
    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps(report, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    _emit_json(report)

@paper_app.command("mvp-end-to-end-closeout")
def paper_mvp_end_to_end_closeout(
    output: Optional[Path] = typer.Option(
        None, "--output", "-o", help="Optional path to write JSON report",
    ),
):
    """Emit a compact local evidence closeout for the paper MVP candidate."""
    init_env()
    report = _build_paper_mvp_end_to_end_closeout_report()
    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps(report, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    _emit_json(report)

@paper_app.command("zotero-metadata-closeout")
def paper_zotero_metadata_closeout(
    output: Optional[Path] = typer.Option(
        None, "--output", "-o", help="Optional path to write JSON report",
    ),
):
    """Emit a local/offline Zotero metadata closeout coverage report."""
    init_env()
    from ai_workflow_hub.context_layer.adapters.zotero_metadata_real_pilot import (
        build_zotero_metadata_local_batch_closeout_report,
    )

    report = build_zotero_metadata_local_batch_closeout_report()
    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps(report, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    _emit_json(report)

@paper_app.command("real-pilot-dry-run")
def paper_real_pilot_dry_run(
    scenario: str = typer.Option(
        "metadata-only-pass",
        "--scenario",
        help=(
            "Local fixture scenario: metadata-only-pass, missing-authorization, "
            "live-writelab-blocked, private-rag-blocked-without-manifest, "
            "unverified-citation, final-acceptance-blocked"
        ),
    ),
    output: Optional[Path] = typer.Option(
        None, "--output", "-o", help="Optional path to write JSON report",
    ),
):
    """Emit a local-only real pilot dry-run gate report."""
    init_env()
    from ai_workflow_hub.context_layer.adapters.paper_real_pilot_gate import (
        build_local_dry_run_report,
    )

    try:
        report = build_local_dry_run_report(scenario=scenario)
    except ValueError as e:
        console.print(f"[red]Invalid scenario: {e}[/red]")
        raise typer.Exit(1)

    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps(report, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    _emit_json(report)

@paper_app.command("real-pilot-preauth")
def paper_real_pilot_preauth(
    output: Optional[Path] = typer.Option(
        None, "--output", "-o", help="Optional path to write JSON packet",
    ),
):
    """Emit a local-only real pilot preauthorization packet."""
    init_env()
    from ai_workflow_hub.context_layer.adapters.paper_real_pilot_preauth import (
        build_preauth_packet,
    )

    packet = build_preauth_packet()
    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps(packet, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    _emit_json(packet)

@paper_app.command("real-pilot-authorization-request")
def paper_real_pilot_authorization_request(
    output: Optional[Path] = typer.Option(
        None, "--output", "-o", help="Optional path to write JSON request",
    ),
):
    """Emit a Zotero metadata-only RuntimeAuthorization request packet."""
    init_env()
    from ai_workflow_hub.context_layer.adapters.paper_real_pilot_authorization_request import (
        build_runtime_authorization_request,
    )

    request = build_runtime_authorization_request()
    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps(request, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    _emit_json(request)

@paper_app.command("real-pilot-authorize-metadata")
def paper_real_pilot_authorize_metadata(
    output: Optional[Path] = typer.Option(
        None, "--output", "-o", help="Optional path to write JSON decision",
    ),
    authorized_by: str = typer.Option(
        "user_chat_authorization",
        "--authorized-by",
        help="Human gate identifier for this metadata-only authorization",
    ),
):
    """Emit a human RuntimeAuthorization decision for Zotero metadata only."""
    init_env()
    from ai_workflow_hub.context_layer.adapters.paper_real_pilot_authorization_request import (
        build_human_runtime_authorization_decision,
    )

    decision = build_human_runtime_authorization_decision(
        authorized_by=authorized_by,
    )
    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps(decision, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    _emit_json(decision)

@paper_app.command("real-pilot-authorize-pdf-excerpt")
def paper_real_pilot_authorize_pdf_excerpt(
    pdf_path: Path = typer.Option(
        ...,
        "--pdf-path",
        help="Single authorized PDF path for the redacted excerpt pilot",
    ),
    output: Optional[Path] = typer.Option(
        None, "--output", "-o", help="Optional path to write JSON decision",
    ),
    authorized_by: str = typer.Option(
        "user_chat_authorization",
        "--authorized-by",
        help="Human gate identifier for this PDF excerpt authorization",
    ),
):
    """Emit a human RuntimeAuthorization decision for one PDF excerpt pilot."""
    init_env()
    from ai_workflow_hub.context_layer.adapters.paper_pdf_redacted_excerpt_pilot import (
        build_pdf_excerpt_runtime_authorization_decision,
    )

    decision = build_pdf_excerpt_runtime_authorization_decision(
        pdf_path=pdf_path,
        authorized_by=authorized_by,
    )
    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps(decision, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    _emit_json(decision)

@paper_app.command("pdf-redacted-excerpt-pilot")
def paper_pdf_redacted_excerpt_pilot(
    authorization_decision: Optional[Path] = typer.Option(
        None,
        "--authorization-decision",
        help="Path to human RuntimeAuthorization decision JSON",
    ),
    pdf_path: Optional[Path] = typer.Option(
        None,
        "--pdf-path",
        help="Path to the single authorized PDF for the redacted excerpt pilot",
    ),
    output: Optional[Path] = typer.Option(
        None, "--output", "-o", help="Optional path to write JSON report",
    ),
    manifest_output: Optional[Path] = typer.Option(
        None,
        "--manifest-output",
        help="Optional path to write minimized EvidenceManifest when the pilot passes",
    ),
):
    """Run a controlled PDF redacted-excerpt pilot with minimized evidence."""
    init_env()
    from ai_workflow_hub.context_layer.adapters.paper_pdf_redacted_excerpt_pilot import (
        build_pdf_redacted_excerpt_pilot_report,
    )

    decision_path = authorization_decision or (
        Path(value) if (value := os.environ.get("PAPER_RUNTIME_AUTHORIZATION_DECISION_PATH")) else None
    )
    selected_pdf_path = pdf_path or (
        Path(value) if (value := os.environ.get("PAPER_PDF_EXCERPT_PATH")) else None
    )
    report = build_pdf_redacted_excerpt_pilot_report(
        authorization_decision_path=decision_path,
        pdf_path=selected_pdf_path,
    )
    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps(report, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    if manifest_output is not None and "evidence_manifest" in report:
        manifest_output.parent.mkdir(parents=True, exist_ok=True)
        manifest_output.write_text(
            json.dumps(report["evidence_manifest"], indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    _emit_json(report)


@paper_app.command("pdf-fulltext-segments")
def paper_pdf_fulltext_segments(
    pdf_path: Path = typer.Option(
        ...,
        "--pdf-path",
        help="Path to the PDF file to segment",
    ),
    output: Optional[Path] = typer.Option(
        None, "--output", "-o", help="Optional path to write JSON report",
    ),
    output_dir: Optional[Path] = typer.Option(
        None,
        "--output-dir",
        help="Optional directory to write a minimized segment index",
    ),
    write_segment_text: bool = typer.Option(
        False,
        "--write-segment-text/--no-write-segment-text",
        help="Explicitly write raw segment text files into --output-dir",
    ),
    backend: str = typer.Option(
        "pypdf",
        "--backend",
        help="PDF text extraction backend (default: pypdf)",
    ),
):
    """Build a PDF full-text segmentation report with minimized evidence."""
    from ai_workflow_hub.context_layer.adapters.paper_pdf_fulltext_segments import (
        build_pdf_fulltext_segments_report,
    )

    init_env()
    report = build_pdf_fulltext_segments_report(
        pdf_path=pdf_path,
        output_dir=str(output_dir) if output_dir else None,
        backend=backend,
        write_segment_text=write_segment_text,
    )
    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps(report, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    _emit_json(report)


@paper_app.command("obsidian-rest-probe")
def paper_obsidian_rest_probe(
    base_url: str = typer.Option(
        "https://127.0.0.1:27124",
        "--base-url",
        help="Obsidian Local REST API base URL",
    ),
    token_env: str = typer.Option(
        "OBSIDIAN_REST_API_KEY",
        "--token-env",
        help="Environment variable containing the Obsidian REST API key",
    ),
    verify_tls: bool = typer.Option(
        False,
        "--verify-tls/--no-verify-tls",
        help="Verify TLS certificates; disabled by default for the plugin's local self-signed certificate",
    ),
    write_probe: bool = typer.Option(
        False,
        "--write-probe/--no-write-probe",
        help="Create/update a small scoped probe note",
    ),
    probe_path: str = typer.Option(
        "_devframe/obsidian-rest-probe.md",
        "--probe-path",
        help="Vault-relative path for the optional write probe",
    ),
    open_probe: bool = typer.Option(
        False,
        "--open-probe/--no-open-probe",
        help="Ask Obsidian to open the probe note",
    ),
    output: Optional[Path] = typer.Option(
        None,
        "--output",
        "-o",
        help="Optional path to write JSON report",
    ),
):
    """Probe Obsidian Local REST API without printing or persisting the API key."""
    init_env()
    from ai_workflow_hub.context_layer.adapters.obsidian_rest_api import (
        build_obsidian_rest_probe_report,
    )

    report = build_obsidian_rest_probe_report(
        base_url=base_url,
        token_env=token_env,
        verify_tls=verify_tls,
        write_probe=write_probe,
        probe_path=probe_path,
        open_probe=open_probe,
    )
    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps(report, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    _emit_json(report)


@paper_app.command("obsidian-sync-plan")
def paper_obsidian_sync_plan(
    local_path: Path = typer.Option(
        ...,
        "--local-path",
        help="Local generated markdown file to compare",
    ),
    remote_path: str = typer.Option(
        ...,
        "--remote-path",
        help="Vault-relative Obsidian note path to read through Local REST API",
    ),
    base_url: str = typer.Option(
        "https://127.0.0.1:27124",
        "--base-url",
        help="Obsidian Local REST API base URL",
    ),
    token_env: str = typer.Option(
        "OBSIDIAN_REST_API_KEY",
        "--token-env",
        help="Environment variable containing the Obsidian REST API key",
    ),
    verify_tls: bool = typer.Option(
        False,
        "--verify-tls/--no-verify-tls",
        help="Verify TLS certificates; disabled by default for the plugin's local self-signed certificate",
    ),
    output: Optional[Path] = typer.Option(
        None,
        "--output",
        "-o",
        help="Optional path to write JSON report",
    ),
):
    """Plan one Obsidian note sync without writing to the vault."""
    init_env()
    from ai_workflow_hub.context_layer.adapters.obsidian_rest_api import (
        build_obsidian_rest_sync_plan_report,
    )

    report = build_obsidian_rest_sync_plan_report(
        local_path=local_path,
        remote_relative_path=remote_path,
        base_url=base_url,
        token_env=token_env,
        verify_tls=verify_tls,
    )
    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps(report, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    _emit_json(report)


@paper_app.command("obsidian-sync-apply")
def paper_obsidian_sync_apply(
    local_path: Path = typer.Option(
        ...,
        "--local-path",
        help="Local generated markdown file to apply",
    ),
    remote_path: str = typer.Option(
        ...,
        "--remote-path",
        help="Vault-relative Obsidian note path to write through Local REST API",
    ),
    base_url: str = typer.Option(
        "https://127.0.0.1:27124",
        "--base-url",
        help="Obsidian Local REST API base URL",
    ),
    token_env: str = typer.Option(
        "OBSIDIAN_REST_API_KEY",
        "--token-env",
        help="Environment variable containing the Obsidian REST API key",
    ),
    verify_tls: bool = typer.Option(
        False,
        "--verify-tls/--no-verify-tls",
        help="Verify TLS certificates; disabled by default for the plugin's local self-signed certificate",
    ),
    output: Optional[Path] = typer.Option(
        None,
        "--output",
        "-o",
        help="Optional path to write JSON report",
    ),
):
    """Apply one Obsidian note sync: GET-before-PUT, replaces only the DevFrame managed block, preserves user content."""
    init_env()
    from ai_workflow_hub.context_layer.adapters.obsidian_rest_api import (
        build_obsidian_rest_sync_apply_report,
    )

    report = build_obsidian_rest_sync_apply_report(
        local_path=local_path,
        remote_relative_path=remote_path,
        base_url=base_url,
        token_env=token_env,
        verify_tls=verify_tls,
    )
    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps(report, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    _emit_json(report)


@paper_app.command("obsidian-allowlisted-note-pilot")
def paper_obsidian_allowlisted_note_pilot(
    note_path: Path = typer.Option(
        ...,
        "--note-path",
        help="Explicit markdown note path to read",
    ),
    vault_root: Optional[Path] = typer.Option(
        None,
        "--vault-root",
        help="Optional Obsidian vault root; the note must be inside it",
    ),
    allowlist_path: list[Path] = typer.Option(
        [],
        "--allowlist-path",
        help="Allowed markdown note path; repeat for multiple notes",
    ),
    output: Optional[Path] = typer.Option(
        None, "--output", "-o", help="Optional path to write JSON report",
    ),
    manifest_output: Optional[Path] = typer.Option(
        None,
        "--manifest-output",
        help="Optional path to write minimized EvidenceManifest when the pilot passes",
    ),
):
    """Run an allowlisted Obsidian note pilot without scanning a vault."""
    init_env()
    from ai_workflow_hub.context_layer.adapters.obsidian_note_adapter import (
        build_obsidian_allowlisted_note_pilot_report,
    )

    report = build_obsidian_allowlisted_note_pilot_report(
        note_path=note_path,
        vault_root=vault_root,
        allowlist_paths=allowlist_path,
        command_name="aihub paper obsidian-allowlisted-note-pilot",
    )
    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps(report, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    if manifest_output is not None and "evidence_manifest" in report:
        manifest_output.parent.mkdir(parents=True, exist_ok=True)
        manifest_output.write_text(
            json.dumps(report["evidence_manifest"], indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    _emit_json(report)

@paper_app.command("obsidian-note-pilot")
def paper_obsidian_note_pilot(
    note_path: Path = typer.Option(
        ...,
        "--note-path",
        help="Explicit markdown note path to read",
    ),
    vault_root: Optional[Path] = typer.Option(
        None,
        "--vault-root",
        help="Optional Obsidian vault root; the note must be inside it",
    ),
    allowlist_path: list[Path] = typer.Option(
        [],
        "--allowlist-path",
        help="Allowed markdown note path; repeat for multiple notes",
    ),
    output: Optional[Path] = typer.Option(
        None, "--output", "-o", help="Optional path to write JSON report",
    ),
    manifest_output: Optional[Path] = typer.Option(
        None,
        "--manifest-output",
        help="Optional path to write minimized EvidenceManifest when the pilot passes",
    ),
):
    """Alias for the scoped allowlisted Obsidian note pilot."""
    init_env()
    from ai_workflow_hub.context_layer.adapters.obsidian_note_adapter import (
        build_obsidian_allowlisted_note_pilot_report,
    )

    report = build_obsidian_allowlisted_note_pilot_report(
        note_path=note_path,
        vault_root=vault_root,
        allowlist_paths=allowlist_path,
        command_name="aihub paper obsidian-note-pilot",
    )
    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps(report, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    if manifest_output is not None and "evidence_manifest" in report:
        manifest_output.parent.mkdir(parents=True, exist_ok=True)
        manifest_output.write_text(
            json.dumps(report["evidence_manifest"], indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    _emit_json(report)

@paper_app.command("rag-local-fixture-pilot")
def paper_rag_local_fixture_pilot(
    query: str = typer.Option(
        "metadata-only retrieval boundary",
        "--query",
        help="Synthetic/local retrieval query to fingerprint; raw query is not persisted",
    ),
    output: Optional[Path] = typer.Option(
        None, "--output", "-o", help="Optional path to write JSON report",
    ),
    manifest_output: Optional[Path] = typer.Option(
        None,
        "--manifest-output",
        help="Optional path to write minimized EvidenceManifest when the pilot passes",
    ),
):
    """Run a local/offline RAG fixture pilot with minimized evidence."""
    init_env()
    from ai_workflow_hub.context_layer.adapters.paper_rag_evidence import (
        build_rag_local_fixture_pilot_report,
    )

    report = build_rag_local_fixture_pilot_report(query=query)
    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps(report, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    if manifest_output is not None and "evidence_manifest" in report:
        manifest_output.parent.mkdir(parents=True, exist_ok=True)
        manifest_output.write_text(
            json.dumps(report["evidence_manifest"], indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    _emit_json(report)

@paper_app.command("rag-single-note-pilot")
def paper_rag_single_note_pilot(
    note_path: Path = typer.Option(
        ...,
        "--note-path",
        help="Explicit markdown note path to use for local retrieval",
    ),
    vault_root: Path = typer.Option(
        ...,
        "--vault-root",
        help="Obsidian vault root; the note must be inside it",
    ),
    allowlist_path: list[Path] = typer.Option(
        [],
        "--allowlist-path",
        help="Allowed markdown note path; repeat for multiple notes",
    ),
    query: str = typer.Option(
        "local retrieval boundary",
        "--query",
        help="Local query to fingerprint; raw query is not persisted",
    ),
    top_k: int = typer.Option(
        3,
        "--top-k",
        min=1,
        help="Number of chunk fingerprints to select",
    ),
    output: Optional[Path] = typer.Option(
        None, "--output", "-o", help="Optional path to write JSON report",
    ),
    manifest_output: Optional[Path] = typer.Option(
        None,
        "--manifest-output",
        help="Optional path to write minimized EvidenceManifest when the pilot passes",
    ),
):
    """Run local deterministic retrieval over one allowlisted Obsidian note."""
    init_env()
    from ai_workflow_hub.context_layer.adapters.rag_single_note_retrieval_pilot import (
        build_rag_single_note_retrieval_pilot_report,
    )

    report = build_rag_single_note_retrieval_pilot_report(
        note_path=note_path,
        vault_root=vault_root,
        allowlist_paths=allowlist_path,
        query=query,
        top_k=top_k,
    )
    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps(report, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    if manifest_output is not None and "evidence_manifest" in report:
        manifest_output.parent.mkdir(parents=True, exist_ok=True)
        manifest_output.write_text(
            json.dumps(report["evidence_manifest"], indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    _emit_json(report)

@paper_app.command("rag-faiss-obsidian-prep")
def paper_rag_faiss_obsidian_prep(
    vault_root: Path = typer.Option(
        ...,
        "--vault-root",
        help="Obsidian vault root; allowlist entries must be inside it",
    ),
    allowlist_path: list[Path] = typer.Option(
        [],
        "--allowlist-path",
        help="Allowed markdown file or folder path; repeat for multiple entries",
    ),
    index_root: Path = typer.Option(
        ...,
        "--index-root",
        help="Planned local FAISS index root; only a fingerprint is persisted",
    ),
    embedding_model: str = typer.Option(
        "sentence-transformers/all-MiniLM-L6-v2",
        "--embedding-model",
        help="Planned local sentence-transformers model name; not downloaded here",
    ),
    query: Optional[str] = typer.Option(
        None,
        "--query",
        help="Optional query to fingerprint; raw query is not persisted",
    ),
    output: Optional[Path] = typer.Option(
        None, "--output", "-o", help="Optional path to write JSON report",
    ),
    manifest_output: Optional[Path] = typer.Option(
        None,
        "--manifest-output",
        help="Optional path to write minimized EvidenceManifest",
    ),
):
    """Preflight a future FAISS Obsidian RAG pilot without installing or indexing."""
    init_env()
    from ai_workflow_hub.context_layer.adapters.rag_faiss_obsidian_prep import (
        build_rag_faiss_obsidian_prep_report,
    )

    report = build_rag_faiss_obsidian_prep_report(
        vault_root=vault_root,
        allowlist_paths=allowlist_path,
        index_root=index_root,
        embedding_model=embedding_model,
        query=query,
    )
    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps(report, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    if manifest_output is not None:
        manifest_output.parent.mkdir(parents=True, exist_ok=True)
        manifest_output.write_text(
            json.dumps(report["evidence_manifest"], indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    _emit_json(report)

@paper_app.command("rag-faiss-obsidian-local-pilot")
def paper_rag_faiss_obsidian_local_pilot(
    vault_root: Path = typer.Option(
        ...,
        "--vault-root",
        help="Obsidian vault root; allowlist entries must be inside it",
    ),
    allowlist_path: list[Path] = typer.Option(
        [],
        "--allowlist-path",
        help="Allowed markdown file or folder path; repeat for multiple entries",
    ),
    index_root: Path = typer.Option(
        ...,
        "--index-root",
        help="Local runtime directory for FAISS artifacts",
    ),
    embedding_model: str = typer.Option(
        "sentence-transformers/all-MiniLM-L6-v2",
        "--embedding-model",
        help="Local sentence-transformers model name",
    ),
    query: str = typer.Option(
        "virtual training retrieval boundary",
        "--query",
        help="Local query for smoke test; raw query is not persisted",
    ),
    top_k: int = typer.Option(
        3,
        "--top-k",
        min=1,
        help="Number of chunk fingerprints to return",
    ),
    output: Optional[Path] = typer.Option(
        None, "--output", "-o", help="Optional path to write JSON report",
    ),
    manifest_output: Optional[Path] = typer.Option(
        None,
        "--manifest-output",
        help="Optional path to write minimized EvidenceManifest",
    ),
):
    """Build a scoped local FAISS index over allowlisted Obsidian Markdown."""
    init_env()
    from ai_workflow_hub.context_layer.adapters.rag_faiss_obsidian_local_pilot import (
        build_rag_faiss_obsidian_local_pilot_report,
    )

    report = build_rag_faiss_obsidian_local_pilot_report(
        vault_root=vault_root,
        allowlist_paths=allowlist_path,
        index_root=index_root,
        embedding_model=embedding_model,
        query=query,
        top_k=top_k,
    )
    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps(report, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    if manifest_output is not None:
        manifest_output.parent.mkdir(parents=True, exist_ok=True)
        manifest_output.write_text(
            json.dumps(report["evidence_manifest"], indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    _emit_json(report)

@paper_app.command("local-rag-closed-loop")
def paper_local_rag_closed_loop(
    pdf_source_folder: Path = typer.Option(
        ...,
        "--pdf-source-folder",
        help="Authorized PDF source folder",
    ),
    obsidian_vault_root: Path = typer.Option(
        ...,
        "--obsidian-vault-root",
        help="Authorized Obsidian vault root",
    ),
    target_folder: Path = typer.Option(
        ...,
        "--target-folder",
        help="Authorized Obsidian target folder for generated Markdown notes",
    ),
    index_root: Path = typer.Option(
        ...,
        "--index-root",
        help="Local runtime directory for FAISS closed-loop artifacts",
    ),
    embedding_model: str = typer.Option(
        "sentence-transformers/all-MiniLM-L6-v2",
        "--embedding-model",
        help="Local sentence-transformers model name",
    ),
    pdf_limit: int = typer.Option(
        3,
        "--pdf-limit",
        min=1,
        help="Maximum number of PDFs to convert in this scoped smoke",
    ),
    top_k: int = typer.Option(
        3,
        "--top-k",
        min=1,
        help="Number of retrieval fingerprints per query",
    ),
    output: Optional[Path] = typer.Option(
        None, "--output", "-o", help="Optional path to write JSON report",
    ),
    manifest_output: Optional[Path] = typer.Option(
        None,
        "--manifest-output",
        help="Optional path to write minimized EvidenceManifest",
    ),
):
    """Run a scoped local PDF -> Obsidian -> FAISS -> local diagnosis closed loop."""
    init_env()
    from ai_workflow_hub.context_layer.adapters.local_paper_rag_closed_loop import (
        build_local_paper_rag_closed_loop_report,
    )

    report = build_local_paper_rag_closed_loop_report(
        pdf_source_folder=pdf_source_folder,
        obsidian_vault_root=obsidian_vault_root,
        target_folder=target_folder,
        index_root=index_root,
        embedding_model=embedding_model,
        pdf_limit=pdf_limit,
        top_k=top_k,
    )
    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps(report, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    if manifest_output is not None:
        manifest_output.parent.mkdir(parents=True, exist_ok=True)
        manifest_output.write_text(
            json.dumps(report["evidence_manifest"], indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    _emit_json(report)

@paper_app.command("local-rag-pipeline")
def paper_local_rag_pipeline(
    pdf_folder: Path = typer.Option(
        ...,
        "--pdf-folder",
        help="Authorized local PDF source folder",
    ),
    vault_root: Path = typer.Option(
        ...,
        "--vault-root",
        help="Authorized Obsidian pilot vault root",
    ),
    target_folder: Path = typer.Option(
        ...,
        "--target-folder",
        help="Authorized Obsidian paper notes folder",
    ),
    runtime_dir: Path = typer.Option(
        ...,
        "--runtime-dir",
        help="Scoped local runtime directory for pipeline state and index",
    ),
    embedding_model: str = typer.Option(
        "sentence-transformers/all-MiniLM-L6-v2",
        "--embedding-model",
        help="Local sentence-transformers model name",
    ),
    pdf_limit: int = typer.Option(
        6,
        "--pdf-limit",
        min=1,
        help="Maximum number of PDFs to include in this local pipeline run",
    ),
    top_k: int = typer.Option(
        3,
        "--top-k",
        min=1,
        help="Top-k retrieval count for the local smoke",
    ),
    output: Optional[Path] = typer.Option(
        None,
        "--output",
        "-o",
        help="Optional path to write minimized JSON report",
    ),
    manifest_output: Optional[Path] = typer.Option(
        None,
        "--manifest-output",
        help="Optional path to write minimized EvidenceManifest",
    ),
):
    """Run the repeatable local paper RAG pipeline with minimized evidence."""
    init_env()
    from ai_workflow_hub.context_layer.adapters.local_paper_rag_pipeline import (
        build_local_paper_rag_pipeline_report,
    )

    report = build_local_paper_rag_pipeline_report(
        pdf_folder=pdf_folder,
        vault_root=vault_root,
        target_folder=target_folder,
        runtime_dir=runtime_dir,
        embedding_model=embedding_model,
        pdf_limit=pdf_limit,
        top_k=top_k,
    )
    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps(report, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    if manifest_output is not None:
        manifest_output.parent.mkdir(parents=True, exist_ok=True)
        manifest_output.write_text(
            json.dumps(report["evidence_manifest"], indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    _emit_json(report)

@paper_app.command("local-rag-run")
def paper_local_rag_run(
    pdf_folder: Path = typer.Option(
        ...,
        "--pdf-folder",
        help="Authorized local PDF source folder",
    ),
    vault_root: Path = typer.Option(
        ...,
        "--vault-root",
        help="Authorized Obsidian pilot vault root",
    ),
    target_folder: Path = typer.Option(
        ...,
        "--target-folder",
        help="Authorized Obsidian paper notes folder",
    ),
    runtime_dir: Path = typer.Option(
        ...,
        "--runtime-dir",
        help="Scoped local runtime directory for stage reports and index state",
    ),
    embedding_model: str = typer.Option(
        "sentence-transformers/all-MiniLM-L6-v2",
        "--embedding-model",
        help="Local sentence-transformers model name",
    ),
    pdf_limit: int = typer.Option(
        6,
        "--pdf-limit",
        min=1,
        help="Maximum number of PDFs to include in this local run",
    ),
    top_k: int = typer.Option(
        3,
        "--top-k",
        min=1,
        help="Top-k retrieval count for local smoke and answer preview",
    ),
    pipeline_schema: Optional[Path] = typer.Option(
        None,
        "--pipeline-schema",
        help="Optional local RAG pipeline report schema for provenance fingerprinting",
    ),
    source_pipeline_commit: str = typer.Option(
        "",
        "--source-pipeline-commit",
        help="Optional source pipeline commit hash for provenance",
    ),
    output: Optional[Path] = typer.Option(
        None,
        "--output",
        "-o",
        help="Optional path to write minimized one-command report",
    ),
    manifest_output: Optional[Path] = typer.Option(
        None,
        "--manifest-output",
        help="Optional path to write minimized one-command EvidenceManifest",
    ),
):
    """Run local RAG pipeline, quality eval, and answer preview as one command."""
    init_env()
    from ai_workflow_hub.context_layer.adapters.local_paper_rag_one_command_runner import (
        build_local_paper_rag_one_command_runner_report,
    )

    report = build_local_paper_rag_one_command_runner_report(
        pdf_folder=pdf_folder,
        vault_root=vault_root,
        target_folder=target_folder,
        runtime_dir=runtime_dir,
        embedding_model=embedding_model,
        pdf_limit=pdf_limit,
        top_k=top_k,
        pipeline_schema=pipeline_schema,
        source_pipeline_commit=source_pipeline_commit,
    )
    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps(report, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    if manifest_output is not None:
        manifest_output.parent.mkdir(parents=True, exist_ok=True)
        manifest_output.write_text(
            json.dumps(report["evidence_manifest"], indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    _emit_json(report)

@paper_app.command("local-rag-quality-eval")
def paper_local_rag_quality_eval(
    pipeline_report: Path = typer.Option(
        ...,
        "--pipeline-report",
        help="Minimized local RAG pipeline report JSON to evaluate",
    ),
    pipeline_schema: Optional[Path] = typer.Option(
        None,
        "--pipeline-schema",
        help="Optional local RAG pipeline report schema for provenance fingerprinting",
    ),
    source_pipeline_commit: str = typer.Option(
        "",
        "--source-pipeline-commit",
        help="Optional source pipeline commit hash for provenance",
    ),
    output: Optional[Path] = typer.Option(
        None,
        "--output",
        "-o",
        help="Optional path to write minimized quality eval report",
    ),
    manifest_output: Optional[Path] = typer.Option(
        None,
        "--manifest-output",
        help="Optional path to write minimized EvidenceManifest",
    ),
):
    """Evaluate local paper RAG pipeline usability from minimized evidence."""
    init_env()
    from ai_workflow_hub.context_layer.adapters.local_paper_rag_quality_eval import (
        build_local_paper_rag_quality_eval_report,
    )

    report = build_local_paper_rag_quality_eval_report(
        pipeline_report=pipeline_report,
        pipeline_schema=pipeline_schema,
        source_pipeline_commit=source_pipeline_commit,
    )
    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps(report, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    if manifest_output is not None:
        manifest_output.parent.mkdir(parents=True, exist_ok=True)
        manifest_output.write_text(
            json.dumps(report["evidence_manifest"], indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    _emit_json(report)

@paper_app.command("local-rag-answer-preview")
def paper_local_rag_answer_preview(
    pipeline_report: Path = typer.Option(
        ...,
        "--pipeline-report",
        help="Minimized local RAG pipeline report JSON to preview",
    ),
    target_folder: Path = typer.Option(
        ...,
        "--target-folder",
        help="Authorized Obsidian paper notes folder used for source identity only",
    ),
    pipeline_schema: Optional[Path] = typer.Option(
        None,
        "--pipeline-schema",
        help="Optional local RAG pipeline report schema for provenance fingerprinting",
    ),
    source_pipeline_commit: str = typer.Option(
        "",
        "--source-pipeline-commit",
        help="Optional source pipeline commit hash for provenance",
    ),
    top_k: int = typer.Option(
        3,
        "--top-k",
        min=1,
        help="Top-k minimized source fingerprints per answer preview row",
    ),
    output: Optional[Path] = typer.Option(
        None,
        "--output",
        "-o",
        help="Optional path to write minimized answer preview report",
    ),
    manifest_output: Optional[Path] = typer.Option(
        None,
        "--manifest-output",
        help="Optional path to write minimized EvidenceManifest",
    ),
):
    """Create deterministic local answer-preview evidence from minimized RAG output."""
    init_env()
    from ai_workflow_hub.context_layer.adapters.local_paper_rag_answer_preview import (
        build_local_paper_rag_answer_preview_report,
    )

    report = build_local_paper_rag_answer_preview_report(
        pipeline_report=pipeline_report,
        target_folder=target_folder,
        pipeline_schema=pipeline_schema,
        source_pipeline_commit=source_pipeline_commit,
        top_k=top_k,
    )
    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps(report, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    if manifest_output is not None:
        manifest_output.parent.mkdir(parents=True, exist_ok=True)
        manifest_output.write_text(
            json.dumps(report["evidence_manifest"], indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    _emit_json(report)

@paper_app.command("real-zotero-metadata-pilot")
def paper_real_zotero_metadata_pilot(
    authorization_decision: Optional[Path] = typer.Option(
        None,
        "--authorization-decision",
        help="Path to human RuntimeAuthorization decision JSON",
    ),
    source_mode: Optional[str] = typer.Option(
        None,
        "--source-mode",
        help="Metadata source mode; only export_file is supported",
    ),
    export_path: Optional[Path] = typer.Option(
        None,
        "--export-path",
        help="Path to user-provided Zotero metadata export file",
    ),
    output: Optional[Path] = typer.Option(
        None, "--output", "-o", help="Optional path to write JSON report",
    ),
):
    """Run the Zotero metadata-only pilot against an approved export file."""
    init_env()
    from ai_workflow_hub.context_layer.adapters.zotero_metadata_real_pilot import (
        build_real_zotero_metadata_pilot_report,
    )

    decision_path = authorization_decision or (
        Path(value) if (value := os.environ.get("PAPER_RUNTIME_AUTHORIZATION_DECISION_PATH")) else None
    )
    mode = source_mode or os.environ.get("ZOTERO_METADATA_SOURCE_MODE")
    metadata_export = export_path or (
        Path(value) if (value := os.environ.get("ZOTERO_METADATA_EXPORT_PATH")) else None
    )
    report = build_real_zotero_metadata_pilot_report(
        authorization_decision_path=decision_path,
        source_mode=mode,
        export_path=metadata_export,
    )
    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps(report, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    _emit_json(report)

@paper_app.command("public-research-kb-pilot")
def paper_public_research_kb_pilot(
    query: str = typer.Option(
        ...,
        "--query",
        "-q",
        help="Public scholarly source search query; raw query is not persisted in output",
    ),
    source: str = typer.Option(
        "arxiv",
        "--source",
        help="Public scholarly metadata source: arxiv or openalex",
    ),
    max_results: int = typer.Option(
        5,
        "--max-results",
        "-n",
        min=1,
        max=20,
        help="Maximum number of public source records to fetch",
    ),
    vault_root: Path = typer.Option(
        ...,
        "--vault-root",
        help="Obsidian vault root; target folder must be inside it",
    ),
    target_folder: Path = typer.Option(
        ...,
        "--target-folder",
        help="Target folder within vault for Obsidian markdown notes",
    ),
    runtime_dir: Path = typer.Option(
        ...,
        "--runtime-dir",
        help="Runtime directory for RAG pipeline artifacts",
    ),
    vault_uri_name: str = typer.Option(
        "",
        "--vault-uri-name",
        help="Optional Obsidian vault name or ID for generated open links; defaults to vault folder name",
    ),
    obsidian_rest: bool = typer.Option(
        False,
        "--obsidian-rest/--no-obsidian-rest",
        help="Also sync generated notes through Obsidian Local REST API",
    ),
    obsidian_rest_base_url: str = typer.Option(
        "https://127.0.0.1:27124",
        "--obsidian-rest-base-url",
        help="Obsidian Local REST API base URL",
    ),
    obsidian_rest_token_env: str = typer.Option(
        "OBSIDIAN_REST_API_KEY",
        "--obsidian-rest-token-env",
        help="Environment variable containing the Obsidian REST API key",
    ),
    obsidian_rest_open: bool = typer.Option(
        False,
        "--obsidian-rest-open/--no-obsidian-rest-open",
        help="Ask Obsidian to open the generated dashboard after REST sync",
    ),
    obsidian_rest_verify_tls: bool = typer.Option(
        False,
        "--obsidian-rest-verify-tls/--no-obsidian-rest-verify-tls",
        help="Verify TLS certificates for Obsidian REST; disabled by default for local self-signed certificates",
    ),
    output: Optional[Path] = typer.Option(
        None,
        "--output",
        "-o",
        help="Optional path to write JSON report",
    ),
    manifest_output: Optional[Path] = typer.Option(
        None,
        "--manifest-output",
        help="Optional path to write minimized EvidenceManifest",
    ),
):
    """Run the public research knowledge-base pilot.

    Fetches public research metadata from arXiv/OpenAlex, writes Obsidian-compatible
    markdown notes into the target folder, runs the local RAG pipeline where
    possible, and produces citation lookup evidence. Only public data is read;
    no private Zotero/Obsidian/user paper data is accessed.
    """
    init_env()
    from ai_workflow_hub.context_layer.adapters.public_research_kb_pilot import (
        build_public_research_kb_pilot_report,
    )

    report = build_public_research_kb_pilot_report(
        query=query,
        source=source,
        max_results=max_results,
        vault_root=vault_root,
        target_folder=target_folder,
        runtime_dir=runtime_dir,
        vault_uri_name=vault_uri_name,
        obsidian_rest=obsidian_rest,
        obsidian_rest_base_url=obsidian_rest_base_url,
        obsidian_rest_token_env=obsidian_rest_token_env,
        obsidian_rest_open=obsidian_rest_open,
        obsidian_rest_verify_tls=obsidian_rest_verify_tls,
    )
    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps(report, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    if manifest_output is not None and "evidence_manifest" in report:
        manifest_output.parent.mkdir(parents=True, exist_ok=True)
        manifest_output.write_text(
            json.dumps(report["evidence_manifest"], indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    _emit_json(report)

@paper_app.command("zotero-web-metadata-pilot")
def paper_zotero_web_metadata_pilot(
    key_file: Optional[Path] = typer.Option(
        None,
        "--key-file",
        help="Path to Zotero Web API credential file; defaults to local user key file",
    ),
    output: Optional[Path] = typer.Option(
        None, "--output", "-o", help="Optional path to write JSON report",
    ),
    manifest_output: Optional[Path] = typer.Option(
        None,
        "--manifest-output",
        help="Optional path to write the minimized EvidenceManifest when the pilot passes",
    ),
    page_limit: int = typer.Option(
        100,
        "--page-limit",
        min=1,
        max=100,
        help="Metadata records to request per Zotero Web API page",
    ),
):
    """Run a Zotero Web API metadata-only pilot with minimized evidence."""
    init_env()
    from ai_workflow_hub.context_layer.adapters.zotero_web_metadata_pilot import (
        build_zotero_web_metadata_pilot_report,
    )

    report = build_zotero_web_metadata_pilot_report(
        key_file_path=key_file,
        limit=page_limit,
    )
    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps(report, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    if manifest_output is not None and "evidence_manifest" in report:
        manifest_output.parent.mkdir(parents=True, exist_ok=True)
        manifest_output.write_text(
            json.dumps(report["evidence_manifest"], indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    _emit_json(report)

@paper_app.command("create")
def paper_create(
    task_id: str = typer.Option(..., "--task", "-t", help="Paper review task ID"),
    project_id: str = typer.Option("", "--project", "-p", help="Project ID"),
):
    """Create a new paper review run."""
    init_env()
    rt = _paper_runtime()
    try:
        result = rt["create"](task_id=task_id, project_id=project_id)
    except (ValueError, OSError) as e:
        console.print(f"[red]Create failed: {e}[/red]")
        raise typer.Exit(1)

    console.print(f"[green]Paper run created: {result['run_id']}[/green]")
    console.print(f"  Run dir: {result['run_dir']}")
    console.print(f"  Task:    {result['task_id']}")
    if result["project_id"]:
        console.print(f"  Project: {result['project_id']}")

@paper_app.command("run")
def paper_run(
    run_id: str = typer.Option(..., "--run-id", "-r", help="Paper run ID"),
    as_json: bool = typer.Option(False, "--json", help="Output as JSON (A18)"),
):
    """Execute a paper review workflow."""
    init_env()
    rt = _paper_runtime()
    try:
        safe_id = rt["sanitize"](run_id)
    except ValueError as e:
        console.print(f"[red]Invalid run_id: {e}[/red]")
        raise typer.Exit(1)
    if safe_id != run_id:
        console.print(f"[yellow]run_id sanitized: {run_id} -> {safe_id}[/yellow]")

    try:
        result = rt["execute"](safe_id)
    except (FileNotFoundError, ValueError) as e:
        console.print(f"[red]Execute failed: {e}[/red]")
        raise typer.Exit(1)

    status = result.get("status", "unknown")
    state = result.get("state", {})
    redacted = rt["redact"](state)

    if as_json:
        output = {
            "run_id": result["run_id"],
            "status": status,
            "task_id": state.get("task_id", ""),
            "acceptance_status": redacted.get("acceptance_status", ""),
            "final_acceptance": _paper_is_final_acceptance(_paper_acceptance_status(redacted)),
            "blocking_count": redacted.get("blocking_count", 0),
            "executed_nodes": redacted.get("executed_nodes", []),
            "gate_artifact": result.get("gate_artifact", ""),
            "warnings": [_redact_str(w) for w in result.get("warnings", [])],
        }
        if result.get("error"):
            output["error"] = _redact_str(result["error"])
        _emit_json(output)
        return

    sc = {"completed": "green", "error": "red", "human_required": "yellow",
          "blocked": "red"}.get(status, "")
    console.print(f"\n[bold [{sc}]]Status: {status}[/{sc}]")
    console.print(f"  Run ID: {result['run_id']}")
    console.print(f"  Task:   {state.get('task_id', '')}")
    _print_paper_acceptance_boundary(redacted)

    executed = redacted.get("executed_nodes", [])
    if executed:
        console.print(f"  Nodes:  {', '.join(executed)}")

    if status == "human_required":
        gate = result.get("gate_artifact", "")
        console.print(f"\n[yellow]Human review required.[/yellow]")
        if gate:
            console.print(f"  Artifact: {gate}")
        console.print(f"  Resume:   aihub paper resume --run-id {safe_id} --decision approved --reviewer <id>")

    warnings = result.get("warnings", [])
    for w in warnings:
        console.print(f"  [yellow]WARN: {_redact_str(w)}[/yellow]")

    if result.get("error"):
        console.print(f"  [red]Error: {_redact_str(result['error'])}[/red]")

@paper_app.command("resume")
def paper_resume(
    run_id: str = typer.Option(..., "--run-id", "-r", help="Paper run ID"),
    decision: str = typer.Option(..., "--decision", "-d", help="approved or rejected"),
    reviewer: str = typer.Option("", "--reviewer", help="Reviewer ID"),
    note: str = typer.Option("", "--note", "-n", help="Decision note"),
):
    """Resume a paused paper run after human decision."""
    init_env()
    rt = _paper_runtime()
    try:
        safe_id = rt["sanitize"](run_id)
    except ValueError as e:
        console.print(f"[red]Invalid run_id: {e}[/red]")
        raise typer.Exit(1)
    if safe_id != run_id:
        console.print(f"[yellow]run_id sanitized: {run_id} -> {safe_id}[/yellow]")

    try:
        result = rt["resume"](
            run_id=safe_id,
            decision=decision,
            reviewer_id=reviewer,
            note=note,
        )
    except (FileNotFoundError, ValueError) as e:
        console.print(f"[red]Resume failed: {e}[/red]")
        raise typer.Exit(1)

    status = result.get("status", "unknown")
    state = result.get("state", {})
    redacted = rt["redact"](state)

    sc = {"completed": "green", "error": "red", "human_required": "yellow",
          "blocked": "red"}.get(status, "")
    console.print(f"\n[bold [{sc}]]Status: {status}[/{sc}]")
    console.print(f"  Run ID:   {result['run_id']}")
    console.print(f"  Decision: {state.get('human_gate_decision', decision)}")
    console.print(f"  Round:    {state.get('decision_round', 0)}")
    _print_paper_acceptance_boundary(redacted)

    executed = redacted.get("executed_nodes", [])
    if executed:
        console.print(f"  Nodes:    {', '.join(executed)}")

    warnings = result.get("warnings", [])
    for w in warnings:
        console.print(f"  [yellow]WARN: {_redact_str(w)}[/yellow]")

    if result.get("error"):
        console.print(f"  [red]Error: {_redact_str(result['error'])}[/red]")

@paper_app.command("status")
def paper_status(
    run_id: str = typer.Option(..., "--run-id", "-r", help="Paper run ID"),
    as_json: bool = typer.Option(False, "--json", help="Output as JSON (A18)"),
):
    """Show the current status of a paper run."""
    init_env()
    rt = _paper_runtime()
    try:
        safe_id = rt["sanitize"](run_id)
    except ValueError as e:
        console.print(f"[red]Invalid run_id: {e}[/red]")
        raise typer.Exit(1)
    if safe_id != run_id:
        console.print(f"[yellow]run_id sanitized: {run_id} -> {safe_id}[/yellow]")

    info = rt["status"](safe_id)
    if info is None:
        console.print(f"[red]Paper run not found: {safe_id}[/red]")
        raise typer.Exit(1)

    # Redact any sensitive fields before display
    redacted_info = rt["redact"](info)

    if as_json:
        _emit_json(redacted_info)
        return

    status = redacted_info.get("status", "unknown")
    sc = {"completed": "green", "error": "red", "human_required": "yellow",
          "blocked": "red", "created": "dim", "running": "blue"}.get(status, "")
    console.print(f"[bold [{sc}]]{status}[/{sc}]")
    console.print(f"  Run ID:     {redacted_info.get('run_id', '')}")
    console.print(f"  Task:       {redacted_info.get('task_id', '')}")
    console.print(f"  Project:    {redacted_info.get('project_id', '')}")
    console.print(f"  Acceptance: {redacted_info.get('acceptance_status', '')}")
    console.print(
        f"  Final acceptance: "
        f"{_paper_final_acceptance_label(_paper_acceptance_status(redacted_info))}"
    )
    console.print(f"  Blocking:   {redacted_info.get('blocking_count', 0)}")
    console.print(f"  Decision:   {redacted_info.get('human_gate_decision', '')}")
    console.print(f"  Round:      {redacted_info.get('decision_round', 0)}")

    executed = redacted_info.get("executed_nodes", [])
    if executed:
        console.print(f"  Nodes:      {', '.join(executed)}")

    err = redacted_info.get("error_message", "")
    if err:
        console.print(f"  [red]Error: {err[:200]}[/red]")

    console.print(f"  Created:    {redacted_info.get('created_at', '')}")
    console.print(f"  Updated:    {redacted_info.get('updated_at', '')}")

@paper_app.command("list")
def paper_list(
    limit: int = typer.Option(20, "--limit", "-n", help="Max runs to show"),
    status_filter: Optional[str] = typer.Option(None, "--status", "-s", help="Filter by status"),
):
    """List paper review runs."""
    init_env()
    rt = _paper_runtime()
    runs_root = _paper_runs_root()

    if not runs_root.exists():
        console.print("[dim]No paper runs found[/dim]")
        return

    run_dirs = sorted(
        [d for d in runs_root.iterdir() if d.is_dir()],
        key=lambda d: d.stat().st_mtime,
        reverse=True,
    )

    if not run_dirs:
        console.print("[dim]No paper runs found[/dim]")
        return

    table = Table(title="Paper Runs")
    table.add_column("Run ID", style="cyan")
    table.add_column("Task")
    table.add_column("Status")
    table.add_column("Blocking")
    table.add_column("Updated")

    count = 0
    for rd in run_dirs:
        if count >= limit:
            break
        state_file = rd / "state.json"
        if not state_file.exists():
            continue
        try:
            state = json.loads(state_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue

        # Redact before display (A16B L3)
        redacted = rt["redact"](state)

        status = redacted.get("status", "unknown")
        if status_filter and status != status_filter:
            continue

        sc = {"completed": "green", "error": "red", "human_required": "yellow",
              "blocked": "red", "created": "dim", "running": "blue"}.get(status, "")

        updated = redacted.get("updated_at", "")[:19]
        table.add_row(
            rd.name,
            (redacted.get("task_id", ""))[:30],
            f"[{sc}]{status}[/{sc}]",
            str(redacted.get("blocking_count", 0)),
            updated,
        )
        count += 1

    if count == 0:
        console.print("[dim]No matching paper runs[/dim]")
    else:
        console.print(table)

# ============================================================
# A18: paper go / ledger / evidence / validate
# ============================================================

def _paper_ledger_api():
    """Lazy import of paper_issue_ledger (A18)."""
    from .context_layer.adapters.paper_issue_ledger import (
        ledger_summary,
        get_all_issues,
        get_open_issues,
        blocking_count,
        critical_count,
        is_clear,
    )
    return {
        "summary": ledger_summary,
        "all_issues": get_all_issues,
        "open_issues": get_open_issues,
        "blocking_count": blocking_count,
        "critical_count": critical_count,
        "is_clear": is_clear,
    }

def _paper_gate_api():
    """Lazy import of paper_acceptance_gate (A18)."""
    from .context_layer.adapters.paper_acceptance_gate import (
        validate_acceptance_result,
    )
    return {"validate": validate_acceptance_result}

def _load_run_state(run_id: str) -> tuple[dict[str, Any], Path] | tuple[None, None]:
    """Load state.json for a paper run. Returns (state_dict, run_dir) or (None, None)."""
    rt = _paper_runtime()
    try:
        safe_id = rt["sanitize"](run_id)
    except ValueError:
        return None, None
    runs_root = _paper_runs_root()
    run_dir = runs_root / safe_id
    state_file = run_dir / "state.json"
    if not state_file.exists():
        return None, None
    try:
        state = json.loads(state_file.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None, None
    return state, run_dir

@paper_app.command("go")
def paper_go(
    task_id: str = typer.Option(..., "--task", "-t", help="Paper review task ID"),
    project_id: str = typer.Option("", "--project", "-p", help="Project ID"),
    as_json: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Create and execute a paper review workflow in one step (A18)."""
    init_env()
    rt = _paper_runtime()

    try:
        run_info = rt["create"](task_id=task_id, project_id=project_id)
    except (ValueError, OSError) as e:
        console.print(f"[red]Create failed: {e}[/red]")
        raise typer.Exit(1)

    run_id = run_info["run_id"]
    if not as_json:
        console.print(f"[green]Created: {run_id}[/green]")

    try:
        result = rt["execute"](run_id)
    except (FileNotFoundError, ValueError) as e:
        console.print(f"[red]Execute failed: {e}[/red]")
        raise typer.Exit(1)

    status = result.get("status", "unknown")
    state = result.get("state", {})
    redacted = rt["redact"](state)

    if as_json:
        output = {
            "run_id": run_id,
            "status": status,
            "task_id": task_id,
            "project_id": project_id,
            "acceptance_status": redacted.get("acceptance_status", ""),
            "final_acceptance": _paper_is_final_acceptance(_paper_acceptance_status(redacted)),
            "blocking_count": redacted.get("blocking_count", 0),
            "executed_nodes": redacted.get("executed_nodes", []),
            "gate_artifact": result.get("gate_artifact", ""),
            "warnings": [_redact_str(w) for w in result.get("warnings", [])],
        }
        _emit_json(output)
        return

    sc = {"completed": "green", "error": "red", "human_required": "yellow",
          "blocked": "red"}.get(status, "")
    console.print(f"\n[bold [{sc}]]Status: {status}[/{sc}]")
    console.print(f"  Run ID: {run_id}")
    _print_paper_acceptance_boundary(redacted)

    executed = redacted.get("executed_nodes", [])
    if executed:
        console.print(f"  Nodes:  {', '.join(executed)}")

    if status == "human_required":
        gate = result.get("gate_artifact", "")
        console.print(f"\n[yellow]Human review required.[/yellow]")
        if gate:
            console.print(f"  Artifact: {gate}")

    for w in result.get("warnings", []):
        console.print(f"  [yellow]WARN: {_redact_str(w)}[/yellow]")
    if result.get("error"):
        console.print(f"  [red]Error: {_redact_str(result['error'])}[/red]")

@paper_app.command("ledger")
def paper_ledger(
    run_id: str = typer.Option(..., "--run-id", "-r", help="Paper run ID"),
    show_all: bool = typer.Option(False, "--all", "-a", help="Show all issues (not just open)"),
    as_json: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Show paper issue ledger for a run (A18)."""
    init_env()
    rt = _paper_runtime()
    try:
        safe_id = rt["sanitize"](run_id)
    except ValueError as e:
        console.print(f"[red]Invalid run_id: {e}[/red]")
        raise typer.Exit(1)

    state, run_dir = _load_run_state(safe_id)
    if state is None:
        console.print(f"[red]Paper run not found: {safe_id}[/red]")
        raise typer.Exit(1)

    task_id = state.get("task_id", "")
    if not task_id:
        console.print(f"[red]No task_id in run state[/red]")
        raise typer.Exit(1)

    ledger = _paper_ledger_api()
    summary = ledger["summary"](task_id)
    issues = ledger["all_issues"](task_id) if show_all else ledger["open_issues"](task_id)

    if as_json:
        output = {
            "run_id": safe_id,
            "task_id": task_id,
            "summary": summary,
            "issues": _deep_redact(issues),
        }
        _emit_json(output)
        return

    console.print(f"[bold]Ledger: {task_id}[/bold]")
    console.print(f"  Total: {summary.get('total', 0)}  Open: {summary.get('open', 0)}  "
                  f"Resolved: {summary.get('resolved', 0)}")
    console.print(f"  Blocking: {summary.get('blocking', 0)}  Critical: {summary.get('critical', 0)}")
    clear = ledger["is_clear"](task_id)
    if clear:
        console.print(f"  [green]CLEAR -- no blocking/critical issues[/green]")
    else:
        console.print(f"  [red]NOT CLEAR -- blocking or critical issues remain[/red]")

    if issues:
        table = Table(title=f"{'All' if show_all else 'Open'} Issues")
        table.add_column("ID", style="cyan")
        table.add_column("Type")
        table.add_column("Severity")
        table.add_column("Status")
        table.add_column("Description")
        for iss in issues[:30]:
            sev = iss.get("severity", "")
            sev_style = {"critical": "red", "major": "yellow", "minor": "dim", "info": "dim"}.get(sev, "")
            raw_desc = iss.get("description", iss.get("message", ""))
            table.add_row(
                iss.get("issue_id", ""),
                iss.get("issue_type", ""),
                f"[{sev_style}]{sev}[/{sev_style}]",
                iss.get("status", ""),
                _redact_str(raw_desc)[:60],
            )
        console.print(table)
    else:
        console.print(f"  [dim]No {'issues' if show_all else 'open issues'}[/dim]")

@paper_app.command("evidence")
def paper_evidence(
    run_id: str = typer.Option(..., "--run-id", "-r", help="Paper run ID"),
    as_json: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Show evidence manifest for a paper run (A18)."""
    init_env()
    rt = _paper_runtime()
    try:
        safe_id = rt["sanitize"](run_id)
    except ValueError as e:
        console.print(f"[red]Invalid run_id: {e}[/red]")
        raise typer.Exit(1)

    state, _ = _load_run_state(safe_id)
    if state is None:
        console.print(f"[red]Paper run not found: {safe_id}[/red]")
        raise typer.Exit(1)

    evidence = state.get("evidence_manifest", {})
    if not evidence:
        console.print(f"[dim]No evidence manifest recorded for {safe_id}[/dim]")
        return

    if as_json:
        _emit_json(_deep_redact(evidence))
        return

    console.print(f"[bold]Evidence Manifest: {safe_id}[/bold]")
    console.print(f"  Reviewer: {evidence.get('reviewer', 'N/A')}")
    console.print(f"  Status: {evidence.get('manifest_status', 'N/A')}")
    console.print(f"  Pack ref: {evidence.get('evidence_pack_ref', '')}")
    attestation = evidence.get("privacy_attestation", {})
    if attestation:
        ok = attestation.get("privacy_ok", False)
        console.print(f"  Privacy: {'[green]OK[/green]' if ok else '[red]VIOLATION[/red]'}")

    entries = evidence.get("entries", [])
    if entries:
        table = Table(title="Evidence Entries")
        table.add_column("Source")
        table.add_column("Type")
        table.add_column("Status")
        table.add_column("Issues")
        for entry in entries[:20]:
            table.add_row(
                entry.get("source", ""),
                entry.get("evidence_type", ""),
                entry.get("status", ""),
                str(entry.get("issue_count", 0)),
            )
        console.print(table)

@paper_app.command("validate")
def paper_validate(
    run_id: str = typer.Option(..., "--run-id", "-r", help="Paper run ID"),
    as_json: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Validate the acceptance result of a paper run (A18)."""
    init_env()
    rt = _paper_runtime()
    try:
        safe_id = rt["sanitize"](run_id)
    except ValueError as e:
        console.print(f"[red]Invalid run_id: {e}[/red]")
        raise typer.Exit(1)

    state, _ = _load_run_state(safe_id)
    if state is None:
        console.print(f"[red]Paper run not found: {safe_id}[/red]")
        raise typer.Exit(1)

    acceptance = state.get("acceptance_result", {})
    if not acceptance:
        console.print(f"[dim]No acceptance_result in run state for {safe_id}[/dim]")
        return

    gate = _paper_gate_api()
    errors = gate["validate"](acceptance)

    if as_json:
        output = {
            "run_id": safe_id,
            "status": acceptance.get("status", "unknown"),
            "final_acceptance": _paper_is_final_acceptance(acceptance.get("status", "")),
            "valid": len(errors) == 0,
            "validation_errors": _deep_redact(errors),
        }
        _emit_json(output)
        return

    status = acceptance.get("status", "unknown")
    sc = {"accepted": "green", "accepted_with_limitation": "yellow",
          "blocked": "red", "human_required": "yellow",
          "needs_more_evidence": "yellow"}.get(status, "dim")
    console.print(f"[bold {sc}]Acceptance: {status}[/bold {sc}]")
    console.print(f"Final acceptance: {_paper_final_acceptance_label(status)}")

    if errors:
        console.print(f"[red]Validation FAILED -- {len(errors)} error(s):[/red]")
        for err in errors:
            console.print(f"  [red]{_redact_str(err)}[/red]")
        raise typer.Exit(1)
    else:
        console.print(f"[green]Validation PASSED -- acceptance result is well-formed[/green]")
        if not _paper_is_final_acceptance(status):
            console.print("[yellow]Validation is schema-only; this status is not final acceptance.[/yellow]")

    reasons = acceptance.get("reasons", [])
    if reasons:
        for r in reasons[:5]:
            console.print(f"  Reason: {_redact_str(r)[:120]}")

    blocking = acceptance.get("blocking_issues", [])
    if blocking:
        console.print(f"  Blocking issues: {len(blocking)}")

# ============================================================
# A24: Artifact Binding Helpers
# ============================================================

_WARNING_SEVERITY: dict[str, str] = {
    "ledger_load_failed": "critical",
    "decision_audit_load_failed": "critical",
    "evidence_verification": "critical",
    "evidence_manifest_missing": "warning",
    "audit_trail_empty": "info",
}

def _classify_warning(msg: str) -> dict[str, str]:
    """Classify a warning string into severity/subsystem/impact (A24)."""
    severity = "warning"
    for prefix, sev in _WARNING_SEVERITY.items():
        if msg.startswith(prefix):
            severity = sev
            break
    subsystem = msg.split(":")[0] if ":" in msg else "unknown"
    impact = "closeout_partial" if severity == "critical" else "closeout_normal"
    return {
        "severity": severity,
        "subsystem": subsystem,
        "message": _redact_str(msg),
        "impact": impact,
    }

def _build_artifact_chain(
    run_dir: Path,
    state: dict[str, Any],
    ledger_dir: str,
    decision_base: str | None,
    evidence_manifest: dict[str, Any],
) -> list[dict[str, str]]:
    """Compute SHA-256 hashes of underlying artifacts (A24)."""
    chain: list[dict[str, str]] = []
    task_id = state.get("task_id", "")

    # state.json
    sf = run_dir / "state.json"
    if sf.exists():
        chain.append({"artifact": "state.json",
                       "sha256": hashlib.sha256(sf.read_bytes()).hexdigest()})

    # ledger JSON
    if task_id and ledger_dir:
        lf = Path(ledger_dir) / f"{task_id}.json"
        if lf.exists():
            chain.append({"artifact": "ledger.json",
                           "sha256": hashlib.sha256(lf.read_bytes()).hexdigest()})

    # evidence files (from manifest)
    for f in evidence_manifest.get("files", [])[:100]:
        fp = f.get("path", f.get("file_path", ""))
        if fp:
            full = (run_dir / fp).resolve()
            try:
                if full.exists() and full.is_file() and str(full).startswith(str(run_dir.resolve())):
                    chain.append({"artifact": f"evidence:{fp}",
                                   "sha256": hashlib.sha256(full.read_bytes()).hexdigest()})
            except OSError:
                pass
    return chain

def _verify_evidence_files(
    run_dir: Path,
    evidence_manifest: dict[str, Any],
) -> list[dict[str, Any]]:
    """Independently verify evidence file existence and hashes (A24)."""
    verified: list[dict[str, Any]] = []
    for f in evidence_manifest.get("files", [])[:100]:
        fp = f.get("path", f.get("file_path", ""))
        entry: dict[str, Any] = {
            "path": fp,
            "manifest_sha256": f.get("sha256", f.get("hash", "")),
            "manifest_size": f.get("size", 0),
            "exists": False,
            "actual_sha256": "",
            "actual_size": 0,
            "hash_match": False,
        }
        if fp:
            full = (run_dir / fp).resolve()
            try:
                if full.exists() and full.is_file() and str(full).startswith(str(run_dir.resolve())):
                    entry["exists"] = True
                    entry["actual_size"] = full.stat().st_size
                    entry["actual_sha256"] = hashlib.sha256(full.read_bytes()).hexdigest()
                    entry["hash_match"] = (entry["actual_sha256"] == entry["manifest_sha256"])
            except OSError:
                pass
        verified.append(entry)
    return verified

# ============================================================
# A25: Audit Package Helpers
# ============================================================

def _hash_file(path: Path) -> str:
    """SHA-256 hex digest of a file (A25)."""
    return hashlib.sha256(path.read_bytes()).hexdigest()

def _build_bundle_manifest(
    bundle_id: str, run_id: str,
    files: list[dict[str, Any]], timestamp: str,
) -> dict[str, Any]:
    """Build bundle_manifest.json with attestation (A25)."""
    _sorted = sorted([(f["path"], f["sha256"]) for f in files])
    content_hash = hashlib.sha256(
        json.dumps(_sorted, sort_keys=True).encode("utf-8")
    ).hexdigest()
    bundle_hash = hashlib.sha256(json.dumps({
        "bundle_id": bundle_id, "content_hash": content_hash,
        "timestamp": timestamp, "run_id": run_id,
    }, sort_keys=True).encode("utf-8")).hexdigest()
    return {
        "bundle_id": bundle_id, "generated_at": timestamp,
        "run_id": run_id, "files": files,
        "attestation": {
            "content_hash": content_hash,
            "bundle_hash": bundle_hash,
            "timestamp": timestamp,
        },
    }

def _rehash_artifact_chain_with_reports(
    run_dir: Path, original_chain: list[dict[str, str]],
    report_json_path: Path, report_md_path: Path,
) -> list[dict[str, str]]:
    """Extend artifact_chain with persisted report files (A25)."""
    extended = list(original_chain)
    if report_json_path.exists():
        extended.append({"artifact": "closeout-report.json",
                          "sha256": _hash_file(report_json_path)})
    if report_md_path.exists():
        extended.append({"artifact": "closeout-report.md",
                          "sha256": _hash_file(report_md_path)})
    return extended

def _build_attestation_record(
    run_id: str, bundle_id: str, timestamp: str,
    content_hash: str, artifact_chain: list[dict[str, str]],
    closeout_integrity: str,
) -> dict[str, Any]:
    """Build tamper-evident attestation record (A25)."""
    return {
        "run_id": run_id, "bundle_id": bundle_id,
        "timestamp": timestamp, "content_hash": content_hash,
        "artifact_hashes": [
            {"artifact": a["artifact"], "sha256": a["sha256"]}
            for a in artifact_chain
        ],
        "closeout_integrity": closeout_integrity,
        "report_version": "1.0", "workflow_type": "paper",
    }

_REQUIRED_EVIDENCE_FILES = ["state.json", "closeout-report.json", "closeout-report.md"]

def _check_omitted_evidence(
    run_dir: Path, evidence_manifest: dict[str, Any],
) -> list[str]:
    """Detect files on disk not listed in evidence manifest (A25)."""
    listed = set()
    for f in evidence_manifest.get("files", []):
        fp = f.get("path", f.get("file_path", ""))
        if fp:
            listed.add(fp)
    omitted: list[str] = []
    _EXCLUDE = {"bundle_", "attestation_", "closeout-report", "artifact_chain",
                "validation-output", "omitted-evidence", "state"}
    for f in run_dir.iterdir():
        if f.is_file() and f.suffix in {".json", ".md", ".txt", ".yaml", ".patch"}:
            if f.name not in listed and not any(f.name.startswith(p) for p in _EXCLUDE):
                omitted.append(f.name)
    return omitted

@paper_app.command("report")
def paper_report(
    run_id: str = typer.Option(..., "--run-id", "-r", help="Paper run ID"),
    as_json: bool = typer.Option(False, "--json", help="Output as JSON"),
    save: bool = typer.Option(True, "--save/--no-save", help="Save report to run directory"),
):
    """Generate unified closeout report binding all run artifacts (A23)."""
    init_env()
    rt = _paper_runtime()
    try:
        safe_id = rt["sanitize"](run_id)
    except ValueError as e:
        console.print(f"[red]Invalid run_id: {e}[/red]")
        raise typer.Exit(1)
    state, run_dir = _load_run_state(safe_id)

    if state is None:
        console.print(f"[red]Run not found: {safe_id}[/red]")
        raise typer.Exit(1)

    task_id = state.get("task_id", "")
    project_id = state.get("project_id", "")

    # --- Degradation warnings (A23B->A24 structured) ---
    warnings_list: list[dict[str, str]] = []
    _raw_warnings: list[str] = []

    # --- Ledger data ---
    ledger_data = {}
    ledger_issues: list[dict] = []
    if task_id:
        try:
            ledger_api = _paper_ledger_api()
            ledger_dir = state.get("ledger_dir", "")
            if ledger_dir:
                ledger_data = ledger_api["summary"](task_id, ledger_dir=ledger_dir)
                ledger_issues = ledger_api["all_issues"](task_id, ledger_dir=ledger_dir)
            else:
                ledger_data = ledger_api["summary"](task_id)
                ledger_issues = ledger_api["all_issues"](task_id)
        except Exception as e:
            _raw_warnings.append(f"ledger_load_failed: {e}")

    # --- Decision audit ---
    decision_record = {}
    audit_trail: list[dict] = []
    if task_id:
        try:
            from .context_layer.adapters.paper_decision_audit import (
                read_decision_record, get_audit_trail,
            )
            decision_base = state.get("decision_base_dir", "") or None
            decision_record = read_decision_record(task_id, base_dir=decision_base) or {}
            audit_trail = get_audit_trail(task_id, base_dir=decision_base) or []
        except Exception as e:
            _raw_warnings.append(f"decision_audit_load_failed: {e}")

    # --- Evidence manifest + verification (A24) ---
    evidence_manifest = state.get("evidence_manifest", {})
    _evidence_verified: list[dict[str, Any]] = []
    if evidence_manifest and run_dir:
        _evidence_verified = _verify_evidence_files(run_dir, evidence_manifest)
        _missing = sum(1 for v in _evidence_verified if not v["exists"])
        _mismatched = sum(1 for v in _evidence_verified if v["exists"] and not v["hash_match"])
        if _missing > 0:
            _raw_warnings.append(f"evidence_verification: {_missing} file(s) missing")
        if _mismatched > 0:
            _raw_warnings.append(f"evidence_verification: {_mismatched} file(s) hash mismatch")

    # Classify warnings (A24)
    warnings_list = [_classify_warning(w) for w in _raw_warnings]

    # --- Acceptance result ---
    acceptance = state.get("acceptance_result", {})
    acceptance_status = str(acceptance.get("status", "unknown"))

    # --- Build unified report ---
    report = {
        "report_version": "1.0",
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "run_id": safe_id,
        "task_id": task_id,
        "project_id": project_id,
        "workflow_type": state.get("workflow_type", "paper"),
        "run_status": state.get("status", "unknown"),
        "final_acceptance": _paper_is_final_acceptance(acceptance_status),
        "created_at": state.get("created_at", ""),
        "updated_at": state.get("updated_at", ""),
        "executed_nodes": _deep_redact(state.get("executed_nodes", [])),
        "acceptance": _deep_redact({
            "status": acceptance_status,
            "reasons": acceptance.get("reasons", []),
            "blocking_count": state.get("blocking_count", 0),
            "non_blocking_count": state.get("non_blocking_count", 0),
            "required_next_actions": acceptance.get("required_next_actions", []),
        }),
        "ledger": _deep_redact(ledger_data) if ledger_data else {},
        "ledger_issues_count": len(ledger_issues),
        "ledger_issues_summary": _deep_redact([
            {
                "issue_id": iss.get("issue_id", ""),
                "issue_type": iss.get("issue_type", ""),
                "severity": iss.get("severity", ""),
                "status": iss.get("status", ""),
                "blocking": iss.get("blocking", False),
                "source": iss.get("source", ""),
                "evidence": iss.get("evidence", ""),
                "evidence_pack_ref": iss.get("evidence_pack_ref", ""),
                "recommendation": iss.get("recommendation", ""),
            }
            for iss in ledger_issues[:50]
        ]) if ledger_issues else [],
        "evidence_manifest": _deep_redact({
            "manifest_id": evidence_manifest.get("manifest_id", ""),
            "status": evidence_manifest.get("status", ""),
            "version": evidence_manifest.get("version", ""),
            "generated_at": evidence_manifest.get("generated_at", ""),
            "file_count": len(evidence_manifest.get("files", [])),
            "files": [
                {
                    "path": f.get("path", f.get("file_path", "")),
                    "sha256": f.get("sha256", f.get("hash", "")),
                    "size": f.get("size", 0),
                }
                for f in evidence_manifest.get("files", [])[:100]
            ],
            "evidence_verification": _deep_redact(_evidence_verified) if _evidence_verified else [],
            "evidence_verified_count": sum(1 for v in _evidence_verified if v.get("exists")),
            "evidence_hash_match_count": sum(1 for v in _evidence_verified if v.get("hash_match")),
            "privacy_attestation": evidence_manifest.get("privacy_attestation", {}),
        }) if evidence_manifest else {},
        "decision": _deep_redact({
            "decision": decision_record.get("decision", ""),
            "reviewer_id": decision_record.get("reviewer_id", ""),
            "round": decision_record.get("round", 0),
            "timestamp": decision_record.get("timestamp", ""),
            "note": decision_record.get("note", ""),
        }) if decision_record else {},
        "audit_trail_length": len(audit_trail),
        "human_gate": {
            "human_required": state.get("human_required", False),
            "decision": state.get("human_gate_decision", ""),
            "reviewer_id": state.get("reviewer_id", ""),
        },
        "privacy": {
            "attestation": state.get("privacy_attestation", {}),
        },
        "warnings": warnings_list,
    }

    # A24: Artifact chain + closeout integrity
    _ledger_dir = state.get("ledger_dir", "")
    _decision_base = state.get("decision_base_dir", "") or None
    artifact_chain = _build_artifact_chain(
        run_dir, state, _ledger_dir, _decision_base, evidence_manifest,
    ) if run_dir else []
    report["artifact_chain"] = artifact_chain
    _has_critical = any(w.get("severity") == "critical" for w in warnings_list)
    report["closeout_integrity"] = "partial" if _has_critical else "complete"
    report["reviewer_pack"] = _build_paper_reviewer_pack(
        state, report, artifact_chain, warnings_list,
    )

    # A24: Updated content hash binds artifacts
    _hash_payload = json.dumps({
        "report": {k: v for k, v in report.items() if k != "content_hash"},
        "artifacts": artifact_chain,
    }, sort_keys=True, ensure_ascii=False, default=str)
    report["content_hash"] = hashlib.sha256(_hash_payload.encode("utf-8")).hexdigest()

    if as_json:
        _emit_json(report)
        if save and run_dir:
            json_path = run_dir / "closeout-report.json"
            json_path.write_text(json.dumps(report, indent=2, ensure_ascii=False, default=str),
                                 encoding="utf-8")
            err_console.print(f"[dim]Saved: {json_path}[/dim]")
        return

    # --- Markdown report ---
    md_lines = [
        f"# Paper Closeout Report -- {safe_id}",
        "",
        f"**Task**: {task_id}",
        f"**Project**: {project_id}",
        f"**Status**: `{state.get('status', 'unknown')}`",
        f"**Acceptance**: `{acceptance_status}`",
        f"**Final Acceptance**: `{_paper_final_acceptance_label(acceptance_status)}`",
        f"**Generated**: {report['generated_at']}",
        "",
        "---",
        "",
        "## Acceptance Summary",
        "",
        f"- Blocking issues: {state.get('blocking_count', 0)}",
        f"- Non-blocking issues: {state.get('non_blocking_count', 0)}",
    ]
    reasons = acceptance.get("reasons", [])
    if reasons:
        md_lines.append("- Reasons:")
        for r in reasons[:5]:
            md_lines.append(f"  - {_redact_str(str(r))[:200]}")

    if ledger_data:
        md_lines.extend([
            "", "---", "", "## Issue Ledger", "",
            f"- Total: {ledger_data.get('total', 0)}",
            f"- Open: {ledger_data.get('open', 0)}",
            f"- Resolved: {ledger_data.get('resolved', 0)}",
            f"- Blocking: {ledger_data.get('blocking', 0)}",
            f"- Critical: {ledger_data.get('critical', 0)}",
        ])
        if ledger_issues:
            md_lines.append("")
            md_lines.append("### Issues")
            md_lines.append("")
            for iss in ledger_issues[:20]:
                iid = _redact_str(str(iss.get("issue_id", "")))
                itype = _redact_str(str(iss.get("issue_type", "")))
                sev = iss.get("severity", "unknown")
                status = iss.get("status", "")
                src = _redact_str(str(iss.get("source", "")))
                rec = _redact_str(str(iss.get("recommendation", "")))[:100]
                md_lines.append(f"- `{iid}` ({itype}) [{sev}] {status} src:{src} rec:{rec}")

    if evidence_manifest:
        md_lines.extend([
            "", "---", "", "## Evidence Manifest", "",
            f"- Manifest ID: `{evidence_manifest.get('manifest_id', 'N/A')}`",
            f"- Status: `{evidence_manifest.get('status', 'unknown')}`",
            f"- Files: {len(evidence_manifest.get('files', []))}",
        ])
        pa = evidence_manifest.get("privacy_attestation", {})
        if pa:
            md_lines.append(f"- Privacy: no_full_text={pa.get('no_full_text')}, "
                           f"no_api_keys={pa.get('no_api_keys')}, "
                           f"no_personal_identity={pa.get('no_personal_identity')}")

    if decision_record:
        md_lines.extend([
            "", "---", "", "## Decision Audit", "",
            f"- Decision: `{_redact_str(str(decision_record.get('decision', 'N/A')))}`",
            f"- Reviewer: {_redact_str(str(decision_record.get('reviewer_id', 'N/A')))}",
            f"- Round: {decision_record.get('round', 0)}",
            f"- Note: {_redact_str(str(decision_record.get('note', '')))}",
        ])
        if audit_trail:
            md_lines.append(f"- Audit trail entries: {len(audit_trail)}")

    md_lines.extend([
        "", "---", "", "## Executed Nodes", "",
    ])
    for node in state.get("executed_nodes", []):
        md_lines.append(f"- {_redact_str(str(node))}")

    # A24: Content hash + integrity + warnings by severity
    md_lines.extend([
        "", "---", "",
        f"**Content Hash**: `{report.get('content_hash', 'N/A')}`",
        f"**Closeout Integrity**: `{report.get('closeout_integrity', 'unknown')}`",
        f"**Artifact Chain**: {len(artifact_chain)} artifact(s) hashed",
    ])
    if warnings_list:
        critical = [w for w in warnings_list if w.get("severity") == "critical"]
        non_critical = [w for w in warnings_list if w.get("severity") != "critical"]
        if critical:
            md_lines.extend(["", "## Warnings (Critical)", ""])
            for w in critical:
                md_lines.append(f"- [{w.get('subsystem', '?')}] {w.get('message', '')} (impact: {w.get('impact', '?')})")
        if non_critical:
            md_lines.extend(["", "## Warnings (Non-Critical)", ""])
            for w in non_critical:
                md_lines.append(f"- [{w.get('subsystem', '?')}] {w.get('message', '')}")

    rp = report.get("reviewer_pack", {})
    if rp:
        scan = rp.get("privacy_scan", {})
        md_lines.extend([
            "", "---", "", "## Reviewer Pack Boundary", "",
            f"- Redaction applied: `{rp.get('redaction_applied', False)}`",
            f"- Summary authoritative: `{not rp.get('summary_is_non_authoritative', True)}`",
            f"- Can claim final success: `{not rp.get('cannot_claim_final_success', True)}`",
            f"- Reviewer pack final verdict: `{rp.get('reviewer_pack_is_final_verdict', False)}`",
            f"- Final verdict source: `{rp.get('final_verdict_source', 'unknown')}`",
            f"- Workflow final acceptance source: `{rp.get('workflow_final_acceptance_source', 'unknown')}`",
            f"- Workflow final acceptance: `{rp.get('workflow_final_acceptance', False)}`",
            f"- Privacy scan passed: `{scan.get('passed', False)}`",
        ])

    md_text = "\n".join(md_lines)

    for line in md_lines:
        console.print(line, markup=False)

    if save and run_dir:
        md_path = run_dir / "closeout-report.md"
        md_path.write_text(md_text, encoding="utf-8")
        json_path = run_dir / "closeout-report.json"
        json_path.write_text(json.dumps(report, indent=2, ensure_ascii=False, default=str),
                             encoding="utf-8")
        console.print(f"\n[dim]Saved: {md_path}[/dim]")
        console.print(f"[dim]Saved: {json_path}[/dim]")


_AUDIT_DEFAULT_MAX_MB = 10


def _audit_max_file_bytes() -> int:
    """Get max file size in bytes from env or default (A27)."""
    mb = os.environ.get("AIHUB_AUDIT_MAX_MB", "")
    try:
        return int(mb) * 1024 * 1024 if mb else _AUDIT_DEFAULT_MAX_MB * 1024 * 1024
    except ValueError:
        return _AUDIT_DEFAULT_MAX_MB * 1024 * 1024


_AUDIT_GENERATED_MEMBERS: frozenset[str] = frozenset({
    "bundle_manifest.json",
    "attestation.json",
    "MANIFEST.json",
    "artifact_chain.json",
})


_AUDIT_POLICY_SCHEMA_VERSION = "1.0"
_AUDIT_POLICY_VALID_SIG_POLICIES = ("required", "optional", "off")
_AUDIT_POLICY_VALID_CHAIN_MODES = ("chain_only", "chain_plus_zip", "chain_partial")


_AUDIT_POLICY_JSON_SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "title": "AuditPolicy",
    "description": "AI Workflow Hub audit policy schema v1.0 (A42)",
    "type": "object",
    "required": ["schema_version"],
    "properties": {
        "schema_version": {"type": "string", "const": "1.0"},
        "signature_policy": {
            "type": "string",
            "enum": ["required", "optional", "off"],
            "default": "optional",
        },
        "chain_verification_mode": {
            "type": "string",
            "enum": ["chain_only", "chain_plus_zip", "chain_partial"],
            "default": "chain_only",
        },
        "allowed_key_ids": {
            "type": "array",
            "items": {"type": "string", "minLength": 1},
            "default": [],
        },
        "required_artifacts": {
            "type": "array",
            "items": {"type": "string"},
            "default": [],
        },
        "strict_chain": {"type": "boolean", "default": False},
        "strict_timestamps": {"type": "boolean", "default": True},
        "completeness_strict": {"type": "boolean", "default": False},
        "ignored_artifacts": {
            "type": "array",
            "items": {"type": "string"},
            "default": [],
        },
        "generated_artifacts": {
            "type": "array",
            "items": {"type": "string"},
            "default": [],
        },
        "description": {"type": "string", "default": ""},
    },
    "additionalProperties": True,
}


def _compute_policy_provenance(policy_path: str) -> dict[str, str]:
    """Compute provenance metadata for a policy file (A41->A42).

    Returns dict with: policy_path_hash (SHA-256 of path), policy_sha256, policy_loaded_at.
    A42: Uses path hash instead of absolute path to avoid leaking local paths.
    """
    pp = Path(policy_path).resolve()
    _raw = pp.read_bytes()
    _hash = hashlib.sha256(_raw).hexdigest()
    _path_hash = hashlib.sha256(str(pp).encode("utf-8")).hexdigest()
    _loaded_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    return {
        "policy_path_hash": _path_hash,
        "policy_sha256": _hash,
        "policy_loaded_at": _loaded_at,
    }


def _build_waiver_record(
    check_name: str, check_index: int, original_detail: str,
    policy_field: str, reason: str, severity: str,
    command: str, policy_data: dict = None,
    adjusted_detail: str = "waived by policy",
    check_entry: dict = None,
) -> dict:
    """A56: Build enriched waiver record with hash binding to raw check."""
    from datetime import datetime, timezone
    _prov = (policy_data or {}).get("_policy_provenance", {})
    _now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    # A56: Hash-bind waiver to the raw check entry
    _check_snapshot = json.dumps(
        {"check": check_name, "index": check_index, "passed": False,
         "detail": original_detail},
        sort_keys=True, ensure_ascii=False) if check_entry is None else \
        json.dumps({k: v for k, v in check_entry.items() if k != "index"},
                   sort_keys=True, ensure_ascii=False)
    _raw_check_hash = hashlib.sha256(_check_snapshot.encode("utf-8")).hexdigest()[:16]
    _wid = hashlib.sha256(
        ("%s:%d:%s:%s" % (check_name, check_index, command, _now)).encode("utf-8")
    ).hexdigest()[:16]
    # A56: Severity taxonomy (info/warning/partial/block/accepted_risk)
    _valid_severities = {"info", "warning", "partial", "block", "accepted_risk"}
    if severity not in _valid_severities:
        severity = "warning"  # Default
    return {
        "waiver_id": _wid,
        "check": check_name,
        "check_index": check_index,
        "original_status": "failed",
        "adjusted_status": "passed",
        "policy_field": policy_field,
        "reason": reason,
        "severity": severity,
        "original_detail": original_detail,
        "adjusted_detail": adjusted_detail,
        "command": command,
        "policy_hash": _prov.get("policy_sha256", ""),
        "policy_schema_version": (policy_data or {}).get("schema_version", ""),
        "created_at": _now,
        "raw_check_hash": _raw_check_hash,
    }


def _verify_waiver_integrity(result: dict) -> None:
    """A56: Verify waiver check_indices + raw_check_hash bindings."""
    waivers = result.get("policy_waivers", [])
    checks = result.get("checks", [])
    integrity_issues = []
    valid_waiver_ids = set()
    for w in waivers:
        idx = w.get("check_index", -1)
        w_id = w.get("waiver_id", "?")
        if idx < 0 or idx >= len(checks):
            integrity_issues.append({
                "waiver_id": w_id,
                "issue": "check_index_out_of_range",
                "check_index": idx,
            })
        elif checks[idx].get("passed") is not False:
            integrity_issues.append({
                "waiver_id": w_id,
                "issue": "check_not_failed",
                "check_index": idx,
            })
        else:
            # A56: Verify raw_check_hash matches actual check entry
            _entry = checks[idx]
            _snapshot = json.dumps(
                {k: v for k, v in _entry.items() if k != "index"},
                sort_keys=True, ensure_ascii=False)
            _expected_hash = hashlib.sha256(_snapshot.encode("utf-8")).hexdigest()[:16]
            _actual_hash = w.get("raw_check_hash", "")
            if _actual_hash and _actual_hash != _expected_hash:
                integrity_issues.append({
                    "waiver_id": w_id,
                    "issue": "raw_check_hash_mismatch",
                    "check_index": idx,
                    "expected": _expected_hash,
                    "actual": _actual_hash,
                })
            else:
                valid_waiver_ids.add(w_id)
    result["waiver_integrity"] = "valid" if not integrity_issues else "invalid"
    if integrity_issues:
        result["waiver_integrity_issues"] = integrity_issues
    # A56: Store valid waiver IDs for verdict computation
    result["_valid_waiver_ids"] = valid_waiver_ids


def _load_audit_policy(policy_path: str,
                       expected_hash: str = "",
                       strict_policy: bool = False) -> dict[str, Any]:
    """Load and validate an audit policy file (A37->A44).

    A44: strict_policy=True escalates schema warnings to blocking failures.

    Policy JSON schema (v1.0):
    {
        "schema_version": "1.0",
        "signature_policy": "required|optional|off",
        "allowed_key_ids": ["kid-1", ...],
        "chain_verification_mode": "chain_only|chain_plus_zip|chain_partial",
        "strict_chain": true/false,
        "strict_timestamps": true/false,
        "required_artifacts": ["state.json", ...],
        "description": "..."
    }

    A41: Computes policy provenance (SHA-256 hash, path, loaded_at)
    and optionally verifies against expected_hash.

    Returns validated policy dict with _policy_provenance attached.
    Raises typer.Exit(1) on invalid policy or hash mismatch.
    """
    pp = Path(policy_path)
    if not pp.exists():
        err_console.print(f"[red]Policy file not found: {pp}[/red]")
        raise typer.Exit(1)

    # A41: Compute provenance before parsing
    _provenance = _compute_policy_provenance(policy_path)

    try:
        policy = json.loads(pp.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, ValueError) as _e:
        err_console.print(f"[red]Invalid policy JSON: {_e}[/red]")
        raise typer.Exit(1)

    # Validate schema_version
    _sv = policy.get("schema_version", "")
    if _sv != _AUDIT_POLICY_SCHEMA_VERSION:
        err_console.print(
            f"[red]Unsupported policy schema_version: '{_sv}' "
            f"(expected '{_AUDIT_POLICY_SCHEMA_VERSION}')[/red]")
        raise typer.Exit(1)

    # Validate signature_policy
    _sp = policy.get("signature_policy", "optional")
    if _sp not in _AUDIT_POLICY_VALID_SIG_POLICIES:
        err_console.print(
            f"[red]Invalid signature_policy '{_sp}' "
            f"(must be one of {_AUDIT_POLICY_VALID_SIG_POLICIES})[/red]")
        raise typer.Exit(1)

    # Validate allowed_key_ids (A38: element type validation)
    _akids = policy.get("allowed_key_ids", [])
    if not isinstance(_akids, list):
        err_console.print("[red]allowed_key_ids must be a list[/red]")
        raise typer.Exit(1)
    for _kid_idx, _kid_val in enumerate(_akids):
        if not isinstance(_kid_val, str) or not _kid_val.strip():
            err_console.print(
                f"[red]allowed_key_ids[{_kid_idx}] must be a non-empty string "
                f"(got {type(_kid_val).__name__})[/red]")
            raise typer.Exit(1)

    # Validate chain_verification_mode
    _cvm = policy.get("chain_verification_mode", "chain_only")
    if _cvm not in _AUDIT_POLICY_VALID_CHAIN_MODES:
        err_console.print(
            f"[red]Invalid chain_verification_mode '{_cvm}' "
            f"(must be one of {_AUDIT_POLICY_VALID_CHAIN_MODES})[/red]")
        raise typer.Exit(1)

    # Validate required_artifacts (A38)
    _ra = policy.get("required_artifacts", [])
    if not isinstance(_ra, list):
        err_console.print("[red]required_artifacts must be a list[/red]")
        raise typer.Exit(1)

    # A43: Validate against JSON Schema artifact (lightweight structural check)
    _schema_props = _AUDIT_POLICY_JSON_SCHEMA.get("properties", {})
    _schema_warnings: list[str] = []
    for _field, _spec in _schema_props.items():
        if _field in policy:
            _val = policy[_field]
            _expected_type = _spec.get("type", "")
            if _expected_type == "string" and not isinstance(_val, str):
                _schema_warnings.append(f"{_field}: expected string, got {type(_val).__name__}")
            elif _expected_type == "boolean" and not isinstance(_val, bool):
                _schema_warnings.append(f"{_field}: expected boolean, got {type(_val).__name__}")
            elif _expected_type == "array" and not isinstance(_val, list):
                _schema_warnings.append(f"{_field}: expected array, got {type(_val).__name__}")
            if "enum" in _spec and _val not in _spec["enum"]:
                _schema_warnings.append(f"{_field}: '{_val}' not in { _spec['enum']}")
    if _schema_warnings:
        for _w in _schema_warnings:
            if strict_policy:
                err_console.print(f"[red]Schema error (strict-policy): {_w}[/red]")
            else:
                err_console.print(f"[yellow]Schema warning: {_w}[/yellow]")
        if strict_policy:
            raise typer.Exit(1)

    # Set defaults
    policy.setdefault("strict_chain", False)
    policy.setdefault("strict_timestamps", True)
    policy.setdefault("required_artifacts", [])
    policy.setdefault("completeness_strict", False)
    policy.setdefault("ignored_artifacts", [])
    policy.setdefault("generated_artifacts", [])
    policy.setdefault("description", "")

    # A41: Verify expected hash if provided
    if expected_hash:
        _actual = _provenance["policy_sha256"]
        if _actual != expected_hash:
            err_console.print(
                f"[red]Policy hash mismatch (A41): expected={expected_hash[:16]}... "
                f"actual={_actual[:16]}...[/red]")
            raise typer.Exit(1)

    # A41->A43: Attach provenance to policy dict
    _provenance["schema_validated"] = len(_schema_warnings) == 0
    _provenance["schema_warnings"] = len(_schema_warnings)
    policy["_policy_provenance"] = _provenance

    return policy


def _sign_record(record: dict[str, Any], key: str = "") -> dict[str, str]:
    """Create HMAC-SHA256 signature for an attestation/bundle record (A29->A31).

    If key is empty, reads AIHUB_SIGNING_KEY env var. If no key available,
    returns a stub with algorithm='none' for forward compatibility.
    A31: includes key_id from AIHUB_SIGNING_KEY_ID for key rotation support.
    """
    import hmac as _hmac
    _key = key or os.environ.get("AIHUB_SIGNING_KEY", "")
    _key_id = os.environ.get("AIHUB_SIGNING_KEY_ID", "")  # A31
    payload = json.dumps(record, sort_keys=True, ensure_ascii=False).encode("utf-8")
    if _key:
        sig = _hmac.new(_key.encode("utf-8"), payload, hashlib.sha256).hexdigest()
        result = {"algorithm": "HMAC-SHA256", "signature": sig, "signed_at":
                  datetime.now(timezone.utc).isoformat(timespec="seconds")}
        if _key_id:
            result["key_id"] = _key_id  # A31
        return result
    return {"algorithm": "none", "signature": "", "note": "no signing key configured"}


def _discover_ledger_path(task_id: str, explicit_dir: str = "",
                          run_id: str = "") -> Path | None:
    """Find ledger JSON for a task, with fallback discovery (A26->A27).

    A27: run_id-aware -- prefers <task_id>_<run_id>.json if it exists,
    then falls back to <task_id>.json.
    """
    # A27: try run-specific ledger first
    if explicit_dir and run_id:
        lf_run = Path(explicit_dir) / f"{task_id}_{run_id}.json"
        if lf_run.exists():
            return lf_run
    if explicit_dir:
        lf = Path(explicit_dir) / f"{task_id}.json"
        if lf.exists():
            return lf
    # Fallback: check default ledger locations
    for base in [
        Path.home() / ".ai_workflow_hub" / "ledger",
        Path.home() / ".ai_workflow_hub" / "paper_ledger",
    ]:
        # A27: run-specific first
        if run_id:
            lf_run = base / f"{task_id}_{run_id}.json"
            if lf_run.exists():
                return lf_run
        lf = base / f"{task_id}.json"
        if lf.exists():
            return lf
    return None


@paper_app.command("audit")
def paper_audit(
    run_id: str = typer.Option(..., "--run-id", "-r", help="Paper run ID"),
    output: Optional[str] = typer.Option(None, "--output", "-o", help="Output ZIP path"),
    as_json: bool = typer.Option(False, "--json", help="Print manifest JSON (pure stdout, A26)"),
    strict: bool = typer.Option(False, "--strict", help="Fail on omitted evidence or oversized files (A27)"),
    max_file_mb: Optional[int] = typer.Option(None, "--max-file-mb", help="Override max file size in MB (A28)"),
    sign: bool = typer.Option(False, "--sign", help="Sign attestation with HMAC-SHA256 (A29)"),
    anchor_log: Optional[str] = typer.Option(None, "--anchor-log",
                                              help="Append bundle hash to audit log file (A30)"),
    no_follow_symlinks: bool = typer.Option(False, "--no-follow-symlinks",
                                             help="Reject symlinks in evidence files (A30)"),
    required_files: Optional[str] = typer.Option(None, "--required-files",
                                                  help="Comma-separated required evidence filenames (A30)"),
    policy_file: str = typer.Option("", "--policy", help="Path to audit policy file (A40)"),
    expected_policy_hash: str = typer.Option("", "--expected-policy-hash",
                                              help="Expected SHA-256 hash of the policy file (A41)"),
    strict_policy: bool = typer.Option(False, "--strict-policy",
                                        help="Escalate schema warnings to blocking failures (A44)"),
    completeness_check: bool = typer.Option(False, "--completeness-check",
                                             help="Verify all evidence artifacts present and generate completeness report (A45)"),
):
    """Generate reproducible audit package (ZIP) binding all artifacts (A25->A31->A45)."""
    init_env()
    # A26: when --json, route all status to stderr so stdout is pure JSON
    _msg = err_console.print if as_json else console.print

    # A40->A44: Load policy file with provenance
    _policy_data: dict[str, Any] = {}
    if policy_file:
        _policy_data = _load_audit_policy(policy_file, expected_hash=expected_policy_hash,
                                           strict_policy=strict_policy)
        _prov = _policy_data.get("_policy_provenance", {})
        _msg(f"[green]Policy loaded[/green]: {_policy_data.get('description', 'unnamed')} "
             f"(schema={_policy_data.get('schema_version', '?')}, "
             f"hash={_prov.get('policy_sha256', '?')[:16]}...)")
        # Override required_files from policy
        _p_ra = _policy_data.get("required_artifacts", [])
        if _p_ra and not required_files:
            required_files = ",".join(_p_ra)

    # A63: Structured audit error schema -- constants defined early for abort paths
    _AUDIT_SCHEMA_VERSION = "1.61"  # A120: bump from 1.60 (cumulative acceptance continuity)
    # A66->A67: Exit metadata contract (process-level vs semantic codes)
    #   exit_code          = PROCESS-LEVEL exit code (0=success, 1=any failure)
    #   process_exit_code  = PROCESS-LEVEL (same as exit_code, explicit alias)
    #   exit_reason_code   = DEPRECATED in 1.5+; always str(exit_code)
    #   failure_details[].exit_code = SEMANTIC registry code (10, 20, 40, etc.)
    #   failure_events[].exit_code  = SEMANTIC registry code (same as details)
    #   reason_code        = SYMBOLIC identifier (e.g., "STRICT_AUDIT_FAILED")
    #   blocking_failures  = list of blocking failure type names
    #   warning_failures   = list of warning-only failure type names
    #   waived_failures    = list of policy-waivable failure types in non-strict mode
    #   operational_verdict = "passed" or "failed" (based on blocking_failures)
    #
    # A67: Migration status of deprecated / redundant fields
    #   exit_reason_code   — DEPRECATED since schema 1.5; retained as str(exit_code)
    #                        for backward compatibility. Removal planned for schema 2.0.
    #   process_exit_code  — REDUNDANT alias of exit_code; retained to make
    #                        process-level semantics explicit. May be removed in schema 2.0
    #                        once exit_code documentation is stabilized.
    #   Consumers SHOULD prefer exit_code for process-level and failure_details[].exit_code
    #   for semantic codes. Consumers MUST inspect waived_failures before treating
    #   failure_type as a process failure when exit_code == 0.
    #
    # A68: Evidence-pack test harness contract
    #   The evidence pack MUST include:
    #   - src/ai_workflow_hub/ with cli.py and minimal support modules
    #     (config_loader.py, model_config.py, project_registry.py, run_governance.py,
    #      run_store.py, schemas.py, task_queue.py) to allow `import ai_workflow_hub.cli`
    #   - Full regression transcript (not just targeted acceptance tests)
    #   - Captured validation output with provenance header (project-root vs unpacked-ZIP)
    #   Test assertions MUST NOT use `or True` to make checks non-blocking.
    #   All assertions must be genuinely validating the claimed behavior.
    #
    # A69: Regression consistency & known-flaky classification
    #   The evidence pack MUST include:
    #   - known_flaky_tests.json: machine-readable classification of known-flaky tests
    #     with test_id, failure_reason, classification ("known_flaky"), and deselect_args
    #   - Both project-root and unpacked-ZIP validation transcripts
    #   - Prompt test counts MUST match actual test file counts
    #   - Historical tests included in pack MUST be self-contained (no stale
    #     references to previous acceptance artifacts)
    #   Known-flaky tests (always deselected in regression):
    #     test_paper_a20_real_e2e::TestA20CLIAgainstRealData::test_cli_list_shows_real_run  (date-dependent)
    #
    # A71: Evidence-pack full self-containment & scope declaration
    #   The evidence pack MUST either:
    #   (a) Include ALL support modules required by EVERY included test file, OR
    #   (b) Include a scope_declaration.txt that explicitly lists which test
    #       files are "in-scope" (runnable from the unpacked ZIP) and which
    #       are "out-of-scope" (require modules not in the pack, such as
    #       context_layer). The pack MUST NOT imply that "all included tests
    #       are self-contained" when some are not.
    #   Additional requirements:
    #   - Unpacked-ZIP validation transcript MUST be captured alongside
    #     project-root transcript (both provenances in the pack).
    #   - Prompt test counts MUST exactly match actual test file counts
    #     and regression output counts.
    #   - Validation script MUST check prompt/evidence count alignment.
    #   Excluded modules (reason: not needed for audit/operational acceptance):
    #     context_layer/ subpackage (10 test_paper_a*.py files + 1 non-a* test file
    #       depend on it, all scoped out: a19, a20, a21, a22, a23, a23b, a24, a45,
    #       a46, test_paper_acceptance_gate.py, and others in broader test suite)
    #
    # A72: Evidence scope correction
    #   Fixes from A71 rejection:
    #   - Unpacked-ZIP validation MUST use correct relative paths. The validate
    #     script MUST detect whether it runs from project-root or from an
    #     extracted ZIP (where cli.py is at a71-evidence/src/ai_workflow_hub/cli.py
    #     relative to the script).
    #   - test_paper_acceptance_gate.py MUST be out-of-scope (imports context_layer).
    #   - Source contract context_layer dependency count MUST match the actual
    #     number of files in the scope declaration.
    #   - Pack script MUST run declared in-scope tests from the unpacked ZIP
    #     as a verification step before claiming self-containment.
    #
    # A73: In-scope runner fix (--ignore replaces --deselect)
    #   Fixes from A72 rejection:
    #   - When running in-scope tests from the unpacked ZIP, use --ignore
    #     for ALL out-of-scope files. The --deselect flag is unsafe because
    #     pytest still imports/collects deselected files before deselection
    #     applies, which causes ModuleNotFoundError for files depending on
    #     modules not in the pack (e.g., context_layer).
    #   - The validate script MUST execute the declared in-scope test command
    #     and fail if any in-scope test fails (not just static checks).
    #   - The captured in-scope test command MUST be exactly reproducible
    #     from the unpacked ZIP by the reviewer.
    #
    # A74: JSON output cross-environment fix
    #   Fixes from A73 rejection:
    #   - Audit command JSON output uses sys.stdout.write() instead of
    #     Rich Console.print() to avoid environment-dependent formatting
    #     (ANSI escape codes, soft-wrap, highlighting on Linux terminals).
    #   - The _emit_json() helper inside paper_audit() ensures pure JSON
    #     text on stdout regardless of platform or terminal configuration.
    #   - All 6 audit JSON emission points use _emit_json():
    #     invalid_run_id, missing_run_state, report_generation_failed,
    #     strict_failure, completeness_strict_failure, success_path.
    #
    # A75: Global JSON emit fix (all paper commands)
    #   Fixes from A74 rejection:
    #   - _emit_json() is now a module-level function (line ~52) used by ALL
    #     JSON-producing paper commands, not only paper audit.
    #   - 20 total JSON emission points use _emit_json():
    #     6 in paper audit, 7 in paper report/verify/inspect, 7 in
    #     paper verify/verify-chain/checkpoint.
    #   - Zero console.print(json.dumps(...)) calls remain in cli.py.
    #
    # A76: Cross-platform Click stdout/stderr separation
    #   Root cause of 68 JSONDecodeError failures on CDP's Linux environment:
    #   - Click 8.0/8.1 with mix_stderr=True (default) merges stderr into
    #     stdout, so result.stdout contains progress messages + JSON.
    #   - Click 8.2+ separates stdout/stderr even with mix_stderr=True,
    #     so result.stdout contains ONLY JSON output.
    #   - Pattern A tests (console patching) unaffected; Pattern B tests
    #     (bare CliRunner + json.loads(result.stdout)) fail on old Click.
    #   Fix: pin click>=8.2.0 in pyproject.toml dependencies.
    #   Schema bumped to 1.17.
    #
    # A77: Evidence-pack dependency bootstrap
    #   A76 correctly diagnosed the root cause but pyproject.toml pin alone
    #   does not change the already-installed Click version in CDP's environment.
    #   A77 adds a bootstrap preflight to validate/pack scripts:
    #   - Check installed Click version before running tests
    #   - Auto-install click>=8.2.0 via pip if installed version < 8.2.0
    #   - Record installed Click version in validation/test transcripts
    #   - Updated reproducible command: pip install "click>=8.2.0" first
    #   Schema bumped to 1.18.
    #
    # A78: Dependency bootstrap hardening
    #   From A77 accepted_with_limitations directive:
    #   - Re-check Click version in a fresh subprocess after pip install
    #     (same-process importlib.metadata can be stale after pip)
    #   - Report both before/after versions accurately
    #   - Pin tested Click range: click>=8.2.0,<9 in pyproject.toml
    #   - Align prompt counts with actual test counts
    #   Schema bumped to 1.19.
    #
    # A79: Evidence-pack count lock manifest
    #   From A78 accepted_with_limitations directive:
    #   - Generate COUNTS_MANIFEST_A79.json with exact counts:
    #     total test files, in-scope, out-of-scope, new tests,
    #     regression passed/skipped/deselected, in-scope passed/skipped.
    #   - validate_a79.py verifies counts match the manifest.
    #   - Prompt reads counts from manifest to prevent drift.
    #   Schema bumped to 1.20.
    #
    # A80: Count manifest crosscheck (authoritative)
    #   From A79 accepted_with_limitations directive:
    #   - Pack script generates manifest BEFORE validation runs
    #     (fixes stale transcripts showing exit code 1)
    #   - validate_a80.py cross-checks manifest values against
    #     actual test files, scope declaration, and test outputs
    #   - Requires schema 1.21 exactly for current acceptance
    #   - Fails validation if any manifest count drifts from evidence
    #   Schema bumped to 1.21.
    #
    # A81: Count manifest strict crosscheck (fail-closed)
    #   From A80 accepted_with_limitations directive:
    #   - validate_a81.py cross-checks ALL manifest counts against evidence
    #   - Mismatches are FAILURES (not warnings) -- fail-closed
    #   - Records platform/provenance in manifest
    #   - Requires exact schema 1.22 for current acceptance
    #   - Regenerate transcripts only after final manifest is written
    #   Schema bumped to 1.22.
    #
    # A82: Transcript path fix + strict no-skip crosscheck
    #   From A81 rejected directive:
    #   - validate_a82.py reads transcripts from output/ subdirectory (not root)
    #   - Requires exact schema 1.23 (no backwards compat)
    #   - ALL 6 cross-checks are FAILURES if transcript missing/unparsable (no SKIP)
    #   - Pack flow: generate transcripts FIRST, then manifest, then validate
    #   - Manifest in_scope_passed matches actual ZIP test transcript
    #   - Negative test proves missing transcript causes exit nonzero
    #   Schema bumped to 1.23.
    #
    # A83: Provenance Lock (SHA256 transcript binding)
    #   From A82 accepted directive:
    #   - Manifest includes provenance fields: python_version, click_version,
    #     pytest_command_hash, regression_transcript_sha256, in_scope_transcript_sha256
    #   - validate_a83.py verifies SHA256 hashes match actual transcript files
    #   - Manifest counts are cryptographically bound to exact captured outputs
    #   - Preserves all A82 fail-closed behavior (no SKIP, output/ paths, exact schema)
    #   Schema bumped to 1.24.
    #
    # A84: Cross-Platform Provenance Lock
    #   From A83 rejected directive:
    #   - Platform check compares manifest platform against platform embedded
    #     INSIDE transcript content (not live platform) -> cross-platform safe
    #   - Renamed pytest_command_hash -> regression_command_hash (unambiguous)
    #   - Preserves all A82/A83 fail-closed + SHA256 binding behavior
    #   Schema bumped to 1.25.
    #
    # A85: Regression Command Fidelity
    #   - Manifest includes regression_command_echo (the actual command string)
    #   - validate_a85.py verifies:
    #     1. Command echo is present in the regression transcript
    #     2. SHA256(command_echo) == regression_command_hash (hash binding)
    #     3. Command contains expected deselect flags from known_flaky_tests.json
    #     4. Command uses "-m pytest" module invocation
    #   - Preserves all A82/A83/A84 fail-closed + provenance behavior
    #   Schema bumped to 1.26.
    #
    # A86: In-Scope Command Fidelity
    #   - Manifest includes in_scope_command_echo and in_scope_command_hash
    #   - validate_a86.py verifies:
    #     1. In-scope command echo is present in in-scope transcript
    #     2. SHA256(in_scope_command_echo) == in_scope_command_hash
    #     3. In-scope command contains --ignore for all out-of-scope tests
    #     4. Both regression and in-scope command provenance verified (no drift)
    #   - Preserves all A82-A85 fail-closed + provenance behavior
    #   Schema bumped to 1.27.
    #
    # A87: Transcript Chain Integrity
    #   - Manifest includes transcript_chain_hash = SHA256(reg_sha256 + inscope_sha256)
    #   - validate_a87.py verifies chain hash binds both transcript hashes
    #   - Tampering with either transcript breaks the chain
    #   - Preserves all A82-A86 fail-closed + provenance + command fidelity
    #   Schema bumped to 1.28.
    #
    # A88: Evidence Bundle Hash
    #   - Manifest includes evidence_bundle_hash over ordered set of critical
    #     artifacts: cli.py, scope declaration, regression transcript, in-scope
    #     transcript, known_flaky_tests.json, and manifest metadata (all fields
    #     except evidence_bundle_hash itself)
    #   - Validation transcript excluded from bundle to avoid self-referential
    #     hash drift (validation verifies the bundle, not vice versa)
    #   - validate_a88.py recomputes bundle hash fail-closed against actual files
    #   - Tampering with any single artifact breaks the bundle hash
    #   - Preserves all A82-A87 fail-closed + provenance + command fidelity + chain
    #   Schema bumped to 1.29.
    #
    # A89: Bundle Coverage Manifest
    #   - Manifest includes evidence_bundle_artifacts: ordered list of included
    #     paths plus "manifest_metadata", making the bundle's artifact set
    #     explicit and verifiable
    #   - validate_a89.py verifies artifact order matches expected sequence
    #     fail-closed, and documents VALIDATION_OUTPUT exclusion by design
    #   - Preserves all A82-A88 fail-closed + provenance + command fidelity
    #     + chain + bundle hash
    #   Schema bumped to 1.30.
    #
    # A90: Regression Status Fail-Closed
    #   - validate_a90.py parses Exit code and failed/error counts from
    #     REGRESSION_OUTPUT and IN_SCOPE_TEST_RESULTS transcripts
    #   - Fails validation if exit code != 0, any "N failed" present,
    #     or pytest summary is unparsable
    #   - SCOPE_DECLARATION accurately documents VALIDATION_OUTPUT exclusion
    #   - A88 test_bundle_hash_matches_recomputed guarded with schema check
    #   - Preserves all A82-A89 fail-closed + provenance + command fidelity
    #     + chain + bundle hash + coverage manifest
    #   Schema bumped to 1.31.
    #
    # A91: Cross-Count Consistency
    #   - validate_a91.py enforces internal consistency among manifest counts:
    #     total_test_files == in_scope + out_of_scope
    #     regression_passed >= in_scope_passed
    #     in_scope_passed >= in_scope count
    #   - evidence_bundle_hash must differ from transcript_chain_hash
    #   - Preserves all A82-A90 fail-closed + provenance + command fidelity
    #     + chain + bundle hash + coverage manifest + regression status
    #   Schema bumped to 1.32.
    #
    # A92: Manifest Negative Case Coverage
    #   - Explicit negative tests for every cross-count consistency rule
    #   - Negative tests for regression status fail-closed invariants
    #   - Negative tests for bundle/chain hash distinctness
    #   - Each mismatch exits nonzero with a specific failure message
    #   - Preserves all A82-A91 fail-closed + provenance + command fidelity
    #     + chain + bundle hash + coverage manifest + regression status
    #     + cross-count consistency
    #   Schema bumped to 1.33.
    #
    # A93: Validation Determinism
    #   - validate_a93.py produces same exit code on repeated runs
    #   - PASS/FAIL line counts are stable (no random/time-dependent output)
    #   - Modifying any artifact changes the validation result
    #   - Preserves all A82-A92 fail-closed + provenance + command fidelity
    #     + chain + bundle hash + coverage manifest + regression status
    #     + cross-count consistency + negative case coverage
    #   Schema bumped to 1.34.
    #
    # A94: Verdict Chain Completeness
    #   - All CDP verdicts from A66 through A93 must be present in evidence pack
    #   - Each verdict file must contain ACCEPTED or REJECTED keyword
    #   - Verdict count must match expected range (28 verdicts: A66-A93)
    #   - Pack script includes verdict list with correct range
    #   - Preserves all A82-A93 invariants
    #   Schema bumped to 1.35.
    #
    # A95: Verdict Content Strict
    #   - Every verdict file A66-A94 must contain ACCEPTED or REJECTED (case-insensitive)
    #   - Non-empty commentary-only verdict files are rejected
    #   - Incomplete verdict files (A77, A78) repaired with retroactive verdicts
    #   - Negative test: commentary-only verdict causes validation to exit nonzero
    #   - Preserves all A82-A94 invariants
    #   Schema bumped to 1.36.
    #
    # A96: Evidence Pack Tamper Detection
    #   - Modifying any artifact in the evidence pack after packing is detected
    #   - Bundle hash mismatch on tampered cli.py exits nonzero
    #   - Transcript hash mismatch on tampered transcripts exits nonzero
    #   - Manifest metadata tampering is detected
    #   - Preserves all A82-A95 invariants
    #   Schema bumped to 1.37.
    #
    # A97: GPT Review Prompt Integrity
    #   - GPT_REVIEW_PROMPT file must exist in scripts/ directory
    #   - Prompt must reference the correct acceptance number (A97)
    #   - Prompt must contain required review sections:
    #     schema verification, test results, evidence bundle, tamper detection
    #   - Prompt must be included in evidence ZIP
    #   - Preserves all A82-A96 invariants
    #   Schema bumped to 1.38.
    #
    # A98: Evidence ZIP Self-Containment
    #   - Evidence ZIP must be fully self-contained for independent validation
    #   - Unpacking ZIP and running validate script from unpacked dir must pass
    #   - All critical files (cli.py, scope, transcripts, manifest, scripts) present in ZIP
    #   - No external file dependencies required for validation
    #   - Preserves all A82-A97 invariants
    #   Schema bumped to 1.39.
    #
    # A99: Known-Flaky Registry Integrity
    #   - known_flaky_tests.json must be properly maintained
    #   - All flaky tests correctly deselected in regression transcripts
    #   - Registry fields validated: test_id, deselect_arg, classification, failure_reason
    #   - No duplicate entries, consistent counts
    #   - Preserves all A82-A98 invariants
    #   Schema bumped to 1.40.
    # A100: Cumulative Acceptance Chain Validation
    #   - All verdict files A66-A99 present and contain ACCEPTED/REJECTED
    #   - Verdict chain integrity: no gaps, no duplicates, correct range
    #   - Schema version progression: 1.19 through 1.41 all represented in OR chain
    #   - Evidence bundle hash covers all critical artifacts
    #   - Full regression with known-flaky deselection verified
    #   - Preserves all A82-A99 invariants
    #   Schema bumped to 1.41.
    # A101: Cumulative Acceptance Chain Continuity
    #   - Extends the verdict chain through A100 after A100 was ACCEPTED
    #   - Keeps cumulative verdict completeness fail-closed for A66-A100
    #   - Schema version progression: 1.19 through 1.42 all represented in OR chain
    #   - Evidence bundle hash, transcript chain, and known-flaky integrity preserved
    #   - Preserves all A82-A100 invariants
    #   Schema bumped to 1.42.
    # A102: Cumulative Acceptance Chain Continuity
    #   - Extends the verdict chain through A101 after A101 was ACCEPTED
    #   - Keeps cumulative verdict completeness fail-closed for A66-A101
    #   - Schema version progression: 1.19 through 1.43 all represented in OR chain
    #   - Evidence bundle hash, transcript chain, and known-flaky integrity preserved
    #   - Preserves all A82-A101 invariants
    #   Schema bumped to 1.43.
    # A103: Cumulative Acceptance Chain Continuity
    #   - Extends the verdict chain through A102 after A102 was ACCEPTED
    #   - Keeps cumulative verdict completeness fail-closed for A66-A102
    #   - Schema version progression: 1.19 through 1.44 all represented in OR chain
    #   - Evidence bundle hash, transcript chain, and known-flaky integrity preserved
    #   - Preserves all A82-A102 invariants
    #   Schema bumped to 1.44.
    # A104: Cumulative Acceptance Chain Continuity
    #   - Extends the verdict chain through A103 after A103 was ACCEPTED
    #   - Keeps cumulative verdict completeness fail-closed for A66-A103
    #   - Schema version progression: 1.19 through 1.45 all represented in OR chain
    #   - Evidence bundle hash, transcript chain, and known-flaky integrity preserved
    #   - Preserves all A82-A103 invariants
    #   Schema bumped to 1.45.
    # A105: Cumulative Acceptance Chain Continuity
    #   - Extends the verdict chain through A104 after A104 was ACCEPTED
    #   - Keeps cumulative verdict completeness fail-closed for A66-A104
    #   - Schema version progression: 1.19 through 1.46 all represented in OR chain
    #   - Evidence bundle hash, transcript chain, and known-flaky integrity preserved
    #   - Preserves all A82-A104 invariants
    #   Schema bumped to 1.46.
    # A106: Cumulative Acceptance Chain Continuity
    #   - Extends the verdict chain through A105 after A105 was ACCEPTED
    #   - Keeps cumulative verdict completeness fail-closed for A66-A105
    #   - Schema version progression: 1.19 through 1.47 all represented in OR chain
    #   - Evidence bundle hash, transcript chain, and known-flaky integrity preserved
    #   - Preserves all A82-A105 invariants
    #   Schema bumped to 1.47.
    # A107: Cumulative Acceptance Chain Continuity
    #   - Extends the verdict chain through A106 after A106 was ACCEPTED
    #   - Keeps cumulative verdict completeness fail-closed for A66-A106
    #   - Schema version progression: 1.19 through 1.48 all represented in OR chain
    #   - Evidence bundle hash, transcript chain, and known-flaky integrity preserved
    #   - Preserves all A82-A106 invariants
    #   Schema bumped to 1.48.
    # A108: Cumulative Acceptance Chain Continuity
    #   - Extends the verdict chain through A107 after A107 was ACCEPTED
    #   - Keeps cumulative verdict completeness fail-closed for A66-A107
    #   - Schema version progression: 1.19 through 1.49 all represented in OR chain
    #   - Evidence bundle hash, transcript chain, and known-flaky integrity preserved
    #   - Preserves all A82-A107 invariants
    #   Schema bumped to 1.49.
    # A109: Cumulative Acceptance Chain Continuity
    #   - Extends the verdict chain through A108 after A108 was ACCEPTED
    #   - Keeps cumulative verdict completeness fail-closed for A66-A108
    #   - Schema version progression: 1.19 through 1.50 all represented in OR chain
    #   - Evidence bundle hash, transcript chain, and known-flaky integrity preserved
    #   - Preserves all A82-A108 invariants
    #   Schema bumped to 1.50.
    # A110: Cumulative Acceptance Chain Continuity
    #   - Extends the verdict chain through A109 after A109 was ACCEPTED
    #   - Keeps cumulative verdict completeness fail-closed for A66-A109
    #   - Schema version progression: 1.19 through 1.51 all represented in OR chain
    #   - Evidence bundle hash, transcript chain, and known-flaky integrity preserved
    #   - Preserves all A82-A109 invariants
    #   Schema bumped to 1.51.
    # A111: Cumulative Acceptance Chain Continuity
    #   - Extends the verdict chain through A110 after A110 was ACCEPTED
    #   - Keeps cumulative verdict completeness fail-closed for A66-A110
    #   - Schema version progression: 1.19 through 1.52 all represented in OR chain
    #   - Evidence bundle hash, transcript chain, and known-flaky integrity preserved
    #   - Preserves all A82-A110 invariants
    #   Schema bumped to 1.52.
    # A112: Cumulative Acceptance Chain Continuity
    #   - Extends the verdict chain through A111 after A111 was ACCEPTED
    #   - Keeps cumulative verdict completeness fail-closed for A66-A111
    #   - Schema version progression: 1.19 through 1.53 all represented in OR chain
    #   - Evidence bundle hash, transcript chain, and known-flaky integrity preserved
    #   - Preserves all A82-A111 invariants
    #   Schema bumped to 1.53.
    # A113: Cumulative Acceptance Chain Continuity
    #   - Extends the verdict chain through A112 after A112 was ACCEPTED
    #   - Keeps cumulative verdict completeness fail-closed for A66-A112
    #   - Schema version progression: 1.19 through 1.54 all represented in OR chain
    #   - Evidence bundle hash, transcript chain, and known-flaky integrity preserved
    #   - Preserves all A82-A112 invariants
    #   Schema bumped to 1.54.
    # A114: Cumulative Acceptance Chain Continuity
    #   - Extends the verdict chain through A113 after A113 was ACCEPTED
    #   - Keeps cumulative verdict completeness fail-closed for A66-A113
    #   - Schema version progression: 1.19 through 1.55 all represented in OR chain
    #   - Evidence bundle hash, transcript chain, and known-flaky integrity preserved
    #   - Preserves all A82-A113 invariants
    #   Schema bumped to 1.55.
    # A115: Cumulative Acceptance Chain Continuity
    #   - Extends the verdict chain through A114 after A114 was ACCEPTED
    #   - Keeps cumulative verdict completeness fail-closed for A66-A114
    #   - Schema version progression: 1.19 through 1.56 all represented in OR chain
    #   - Evidence bundle hash, transcript chain, and known-flaky integrity preserved
    #   - Preserves all A82-A114 invariants
    #   Schema bumped to 1.56.
    # A116: Cumulative Acceptance Chain Continuity
    #   - Extends the verdict chain through A115 after A115 was ACCEPTED
    #   - Keeps cumulative verdict completeness fail-closed for A66-A115
    #   - Schema version progression: 1.19 through 1.57 all represented in OR chain
    #   - Evidence bundle hash, transcript chain, and known-flaky integrity preserved
    #   - Preserves all A82-A115 invariants
    #   Schema bumped to 1.57.
    # A117: Cumulative Acceptance Chain Continuity
    #   - Extends the verdict chain through A116 after A116 was ACCEPTED
    #   - Keeps cumulative verdict completeness fail-closed for A66-A116
    #   - Schema version progression: 1.19 through 1.58 all represented in OR chain
    #   - Evidence bundle hash, transcript chain, and known-flaky integrity preserved
    #   - Preserves all A82-A116 invariants
    #   Schema bumped to 1.58.
    # A118: Cumulative Acceptance Chain Continuity
    #   - Extends the verdict chain through A117 after A117 was ACCEPTED
    #   - Keeps cumulative verdict completeness fail-closed for A66-A117
    #   - Schema version progression: 1.19 through 1.59 all represented in OR chain
    #   - Evidence bundle hash, transcript chain, and known-flaky integrity preserved
    #   - Preserves all A82-A117 invariants
    #   Schema bumped to 1.59.
    # A119: Cumulative Acceptance Chain Continuity
    #   - Extends the verdict chain through A118 after A118 was ACCEPTED
    #   - Keeps cumulative verdict completeness fail-closed for A66-A118
    #   - Schema version progression: 1.19 through 1.60 all represented in OR chain
    #   - Evidence bundle hash, transcript chain, and known-flaky integrity preserved
    # A120: Cumulative Acceptance Chain Continuity
    #   - Extends the verdict chain through A119 after A119 was ACCEPTED
    #   - Keeps cumulative verdict completeness fail-closed for A66-A119
    #   - Schema version progression: 1.19 through 1.61 all represented in OR chain
    #   - Evidence bundle hash, transcript chain, and known-flaky integrity preserved
    #   - Preserves all A82-A118 invariants
    #   Schema bumped to 1.60.
    _SCHEMA_MIGRATION_RULES = {
        "additive": "minor", "removal": "major", "rename": "major",
        "semantic_change": "major", "reserved_values": "none",
    }
    # A62->A64: Extended failure type registry with symbolic reason codes + severity classification
    # A64: severity_class values:
    #   "blocking"         = always forces failure verdict and non-zero exit
    #   "warning"          = recorded but does not block verdict or exit
    #   "policy_waivable"  = blocking by default, but can be waived by policy
    _FAILURE_TYPE_REGISTRY: dict[str, dict[str, Any]] = {
        "none":                 {"exit_code": 0,  "reason_code": "OK",
                                 "description": "No failure",
                                 "min_schema_version": "1.1",
                                 "severity_class": "warning"},
        "strict_audit":         {"exit_code": 10, "reason_code": "STRICT_AUDIT_FAILED",
                                 "description": "Strict audit check failed",
                                 "min_schema_version": "1.1",
                                 "severity_class": "blocking"},
        "completeness_strict":  {"exit_code": 11, "reason_code": "COMPLETENESS_STRICT_FAILED",
                                 "description": "Completeness strict check failed",
                                 "min_schema_version": "1.1",
                                 "severity_class": "blocking"},
        "missing_run_state":    {"exit_code": 20, "reason_code": "RUN_STATE_NOT_FOUND",
                                 "description": "Run state file not found",
                                 "min_schema_version": "1.2",
                                 "severity_class": "blocking"},
        "invalid_run_id":       {"exit_code": 21, "reason_code": "INVALID_RUN_ID",
                                 "description": "Run ID failed sanitization",
                                 "min_schema_version": "1.2",
                                 "severity_class": "blocking"},
        "report_generation_failed": {"exit_code": 22, "reason_code": "REPORT_GEN_FAILED",
                                     "description": "Closeout report generation failed",
                                     "min_schema_version": "1.2",
                                     "severity_class": "blocking"},
        "sensitive_payload_detected": {"exit_code": 23, "reason_code": "SENSITIVE_PAYLOAD_DETECTED",
                                       "description": "Audit bundle candidate contains unredacted paper sensitive payload",
                                       "min_schema_version": "1.61",
                                       "severity_class": "blocking"},
        "policy_hash_mismatch": {"exit_code": 30, "reason_code": "POLICY_HASH_MISMATCH",
                                 "description": "Policy file hash does not match expected",
                                 "min_schema_version": "1.2",
                                 "severity_class": "blocking"},
        "waiver_integrity_failed": {"exit_code": 31, "reason_code": "WAIVER_INTEGRITY_FAILED",
                                    "description": "Waiver integrity verification failed",
                                    "min_schema_version": "1.2",
                                    "severity_class": "blocking"},
        # A62: New registry entries for broader failure coverage
        # A64: severity_class assigned to each operational failure type
        "filesystem_containment": {"exit_code": 40, "reason_code": "FILESYSTEM_CONTAINMENT_FAILED",
                                   "description": "Run directory files outside containment boundary",
                                   "min_schema_version": "1.3",
                                   "severity_class": "blocking"},
        "manifest_mismatch":    {"exit_code": 41, "reason_code": "MANIFEST_MISMATCH",
                                 "description": "Bundle manifest/attestation integrity mismatch",
                                 "min_schema_version": "1.3",
                                 "severity_class": "policy_waivable"},
        "signature_failure":    {"exit_code": 42, "reason_code": "SIGNATURE_FAILED",
                                 "description": "Attestation signature verification failed",
                                 "min_schema_version": "1.3",
                                 "severity_class": "blocking"},
        "anchor_log_corruption": {"exit_code": 43, "reason_code": "ANCHOR_LOG_CORRUPT",
                                  "description": "Anchor log chain integrity broken",
                                  "min_schema_version": "1.3",
                                  "severity_class": "blocking"},
        "artifact_chain_integrity": {"exit_code": 44, "reason_code": "ARTIFACT_CHAIN_BROKEN",
                                     "description": "Artifact chain hash linkage broken",
                                     "min_schema_version": "1.3",
                                     "severity_class": "policy_waivable"},
    }
    # A62: Extended precedence with new failure types
    _FAILURE_PRECEDENCE: list[str] = [
        "missing_run_state", "invalid_run_id", "report_generation_failed",
        "sensitive_payload_detected", "policy_hash_mismatch", "waiver_integrity_failed",
        "signature_failure", "manifest_mismatch", "artifact_chain_integrity",
        "anchor_log_corruption", "filesystem_containment",
        "strict_audit", "completeness_strict",
    ]

    # A64: Helper for early abort error JSON (available before _audit_result init)
    # Enhanced with checks[], policy_waivers[], error_profile, failure_events[], timestamp
    def _early_abort_json(ftype: str, reason: str) -> dict:
        """Build minimal schema-compliant error JSON for early aborts (A61->A65)."""
        _reg = _FAILURE_TYPE_REGISTRY.get(ftype, {})
        _evt = {
            "type": ftype,
            "exit_code": _reg.get("exit_code", 99),
            "reason_code": _reg.get("reason_code", "UNKNOWN"),
            "exit_reason": reason,
            "severity": "error",
            "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),  # A64: timestamp consistency
        }
        return {
            "result_schema_version": _AUDIT_SCHEMA_VERSION,
            "error_profile": "minimal",  # A62->A65: minimal profile contract
            "failure_type": ftype,
            "failure_types": [ftype],
            "failure_events": [_evt],   # A63: non-deduped event log
            "failure_details": [_evt],
            "exit_reason": reason,
            # A66: exit_reason_code aligned to str(exit_code) for early aborts too
            "exit_reason_code": "1",
            "exit_code": 1,             # A65: aligned with process Exit(1)
            "process_exit_code": 1,     # A65: actual process exit code
            "strict_mode": strict,
            "waiver_mode": "not_applicable",
            "blocking_failures": [ftype],   # A65: early abort is always blocking
            "warning_failures": [],
            "waived_failures": [],          # A66
            "operational_verdict": "failed",
            "checks": [],          # A62: empty for minimal profile
            "policy_waivers": [],  # A62: empty for minimal profile
        }

    rt = _paper_runtime()
    try:
        safe_id = rt["sanitize"](run_id)
    except ValueError as e:
        _msg(f"[red]Invalid run_id: {e}[/red]")
        # A61: Emit schema-compliant early abort JSON
        if as_json:
            _emit_json(_early_abort_json("invalid_run_id", f"Invalid run_id: {e}"))
        raise typer.Exit(1)
    state, run_dir = _load_run_state(safe_id)
    if state is None:
        _msg(f"[red]Run not found: {safe_id}[/red]")
        # A61: Emit schema-compliant early abort JSON
        if as_json:
            _emit_json(_early_abort_json("missing_run_state", f"Run not found: {safe_id}"))
        raise typer.Exit(1)

    # A61: _VALID_WAIVER_MODES + _audit_result init (constants already defined above)
    _VALID_WAIVER_MODES = {"active", "disabled_by_strict", "not_applicable"}
    _wm = "disabled_by_strict" if strict else "active"
    if _wm not in _VALID_WAIVER_MODES:
        _wm = "active"  # fallback

    # A57->A64: Audit waiver trace model with versioned result schema + multi-failure + events + severity
    _audit_result: dict[str, Any] = {
        "result_schema_version": _AUDIT_SCHEMA_VERSION,
        "error_profile": "full",        # A62: full profile (vs minimal for early aborts)
        "strict_mode": strict,
        "waiver_mode": _wm,
        "failure_type": "none",       # A60->A61: primary (highest-precedence) failure type
        "failure_types": [],           # A61: deduped array of failure types
        "failure_events": [],          # A63: non-deduped event log (every recording)
        "failure_details": [],         # A61: structured failure objects (deduped)
        "exit_reason": "",             # A60: human-readable exit reason
        "exit_reason_code": "",        # A64: DEPRECATED alias for str(exit_code)
        "exit_code": 0,                # A62: numeric exit code (0=success)
        # A64: Severity classification fields
        "operational_verdict": "passed",  # verdict after operational failure recomputation
        "blocking_failures": [],          # list of blocking failure types
        "warning_failures": [],           # list of warning-only failure types
        "waived_failures": [],            # A66: policy-waivable failures in non-strict mode
        "process_exit_code": 0,           # A65: actual CLI process exit code (aligned with exit_code)
        "passed": 0, "failed": 0,
        "checks": [],
        "policy_waivers": [],
    }

    # A63: Helper to record a structured failure (with dedup + events + strict validation)
    def _record_failure(ftype: str, reason: str, context: dict | None = None) -> None:
        """Record a failure into _audit_result with structured details (A61->A63)."""
        # A62: Strict schema mode -- classify unregistered failure types
        _reg = _FAILURE_TYPE_REGISTRY.get(ftype)
        if _reg is None:
            _reg = {"exit_code": 99, "reason_code": "UNKNOWN_FAILURE",
                    "description": "Unregistered failure type",
                    "min_schema_version": "1.3"}
        _ecode = _reg.get("exit_code", 99)
        _rcode = _reg.get("reason_code", "UNKNOWN")
        _evt: dict[str, Any] = {
            "type": ftype,
            "exit_code": _ecode,
            "reason_code": _rcode,    # A62: symbolic reason code
            "exit_reason": reason,
            "severity": "error",
            "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        if context:
            _evt["context"] = context
        # A63: Always append to non-deduped event log
        _audit_result["failure_events"].append(_evt)
        # A62: Deduplicate failure_types[] and failure_details[]
        if ftype not in _audit_result["failure_types"]:
            _audit_result["failure_types"].append(ftype)
            _audit_result["failure_details"].append(dict(_evt))  # copy
        else:
            # Merge context into existing detail
            for _fd in _audit_result["failure_details"]:
                if _fd["type"] == ftype and context:
                    _existing_ctx = _fd.get("context", {})
                    _existing_ctx.update(context)
                    _fd["context"] = _existing_ctx
        # Update primary failure_type and exit_reason_code by precedence
        _best = ftype
        _best_idx = (_FAILURE_PRECEDENCE.index(ftype)
                     if ftype in _FAILURE_PRECEDENCE else len(_FAILURE_PRECEDENCE))
        for _ft in _audit_result["failure_types"]:
            _idx = (_FAILURE_PRECEDENCE.index(_ft)
                    if _ft in _FAILURE_PRECEDENCE else len(_FAILURE_PRECEDENCE))
            if _idx < _best_idx:
                _best = _ft
                _best_idx = _idx
        _best_reg = _FAILURE_TYPE_REGISTRY.get(_best, {})
        _audit_result["failure_type"] = _best
        _audit_result["exit_reason_code"] = str(
            _best_reg.get("exit_code", 99))
        _audit_result["exit_code"] = _best_reg.get("exit_code", 99)  # A62: numeric
        _audit_result["exit_reason"] = reason  # latest reason for human readability
        # A65: Recompute severity classification after every _record_failure call
        _recompute_severity()

    # A65: Severity recomputation -- keeps A64 fields synchronized with failure state
    # Called at the end of _record_failure() so fields are always up-to-date
    # before any JSON emission point (strict, completeness strict, or normal success)
    def _recompute_severity() -> None:
        """Reclassify blocking/warning failures and align exit_code with process exit."""
        _blocking = []
        _warning = []
        _waivable = []
        for _ft in _audit_result["failure_types"]:
            _reg_entry = _FAILURE_TYPE_REGISTRY.get(_ft, {})
            _sc = _reg_entry.get("severity_class", "blocking")
            if _sc == "blocking":
                _blocking.append(_ft)
            elif _sc == "warning":
                _warning.append(_ft)
            elif _sc == "policy_waivable":
                if strict:
                    _blocking.append(_ft)
                else:
                    _waivable.append(_ft)
        _audit_result["blocking_failures"] = _blocking
        _audit_result["warning_failures"] = _warning
        _audit_result["waived_failures"] = _waivable  # A66: expose waived failures
        # A65: operational_verdict
        if _blocking:
            _audit_result["operational_verdict"] = "failed"
            if _audit_result.get("policy_verdict") == "passed":
                _audit_result["policy_verdict"] = "failed"
            if _audit_result.get("verdict") == "passed":
                _audit_result["verdict"] = "failed"
        else:
            _audit_result["operational_verdict"] = "passed"
        # A65: Align exit_code with CLI process exit code
        # JSON exit_code must equal the actual typer.Exit() code:
        #   - 0 when no blocking failures (success)
        #   - 1 when blocking failures exist (matches Exit(1) in strict/completeness paths)
        # The semantic registry exit_code stays in failure_details[].exit_code
        _audit_result["exit_code"] = 1 if _blocking else 0
        _audit_result["process_exit_code"] = _audit_result["exit_code"]
        # A65: Keep deprecated exit_reason_code aligned with exit_code
        _audit_result["exit_reason_code"] = str(_audit_result["exit_code"])

    def _audit_check(name: str, ok: bool, detail: str = "") -> None:
        entry = {"check": name, "passed": ok,
                 "index": len(_audit_result["checks"])}
        if detail:
            entry["detail"] = detail
        _audit_result["checks"].append(entry)
        if ok:
            _audit_result["passed"] += 1
        else:
            _audit_result["failed"] += 1

    _msg(f"[bold]A27 Audit Package: {safe_id}[/bold]")

    # Ensure closeout reports exist -- A26: check CliRunner result
    report_json_path = run_dir / "closeout-report.json"
    report_md_path = run_dir / "closeout-report.md"
    if not report_json_path.exists() or not report_md_path.exists():
        _msg("[dim]Generating closeout report...[/dim]")
        from typer.testing import CliRunner as _CR
        _r = _CR().invoke(app, ["paper", "report", "--run-id", safe_id, "--save"],
                          catch_exceptions=False)
        # A26: verify generation succeeded
        if _r.exit_code != 0 or not report_json_path.exists():
            _reason = f"Report generation failed (exit={_r.exit_code}). Cannot produce complete audit package."
            _msg(f"[red]{_reason}[/red]")
            # A61: Emit schema-compliant early abort JSON
            if as_json:
                _emit_json(_early_abort_json("report_generation_failed", _reason))
            raise typer.Exit(1)

    # Build extended artifact chain (binds report files)
    evidence_manifest = state.get("evidence_manifest", {})
    _ledger_dir = state.get("ledger_dir", "")
    _decision_base = state.get("decision_base_dir", "") or None
    original_chain = _build_artifact_chain(
        run_dir, state, _ledger_dir, _decision_base, evidence_manifest,
    ) if run_dir else []
    artifact_chain = _rehash_artifact_chain_with_reports(
        run_dir, original_chain, report_json_path, report_md_path,
    )

    # Check omitted evidence
    omitted = _check_omitted_evidence(run_dir, evidence_manifest) if run_dir else []
    if omitted:
        _msg(f"[yellow]WARN: {len(omitted)} evidence file(s) not in manifest[/yellow]")

    # Build bundle
    import uuid as _uuid
    import zipfile as _zf

    bundle_id = f"bundle-{_uuid.uuid4().hex[:12]}"
    timestamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    zip_name = output or str(run_dir / f"audit-bundle-{safe_id}.zip")

    bundle_files_meta: list[dict[str, Any]] = []
    _to_add: list[tuple[Path, str]] = []
    _oversized: list[str] = []  # A26: track files exceeding size limit

    # Collect files to bundle
    for name, path in [
        ("closeout-report.json", report_json_path),
        ("closeout-report.md", report_md_path),
    ]:
        if path.exists():
            _to_add.append((path, name))

    # artifact_chain.json
    chain_path = run_dir / "artifact_chain.json"
    chain_path.write_text(
        json.dumps(artifact_chain, indent=2, ensure_ascii=False), encoding="utf-8")
    _to_add.append((chain_path, "artifact_chain.json"))

    # state.json
    sf = run_dir / "state.json"
    if sf.exists():
        _to_add.append((sf, "state.json"))

    # ledger -- A26: fallback discovery
    task_id = state.get("task_id", "")
    _ledger_path = _discover_ledger_path(task_id, _ledger_dir, run_id=safe_id) if task_id else None
    if _ledger_path:
        _to_add.append((_ledger_path, "ledger.json"))

    # omitted evidence
    if omitted:
        omitted_path = run_dir / "omitted-evidence.json"
        omitted_path.write_text(json.dumps({
            "omitted_files": omitted, "detected_at": timestamp, "run_id": safe_id,
        }, indent=2), encoding="utf-8")
        _to_add.append((omitted_path, "omitted-evidence.json"))

    # Fail closed before packaging historical or externally edited sensitive artifacts.
    _sensitive_findings: list[dict[str, str]] = []
    for fpath, arcname in _to_add:
        _sensitive_findings.extend(_scan_paper_audit_sensitive_file(fpath, arcname))
    if _sensitive_findings:
        _paths = sorted({f["path"] for f in _sensitive_findings})
        _reason = "Sensitive paper payload detected in audit candidate: " + ", ".join(_paths[:8])
        _msg(f"[red]{_reason}[/red]")
        if as_json:
            _json_out = _early_abort_json("sensitive_payload_detected", _reason)
            _json_out["sensitive_findings"] = _sensitive_findings[:20]
            _emit_json(_json_out)
        raise typer.Exit(1)

    # A26->A28: check file sizes and warn for oversized files
    _max_bytes = (max_file_mb * 1024 * 1024) if max_file_mb and max_file_mb > 0 else _audit_max_file_bytes()
    for fpath, arcname in _to_add:
        fsize = fpath.stat().st_size
        if fsize > _max_bytes:
            _oversized.append(f"{arcname} ({fsize / 1024 / 1024:.1f}MB)")

    if _oversized:
        _msg(f"[yellow]WARN: {len(_oversized)} file(s) exceed {_max_bytes // 1024 // 1024}MB: "
             f"{', '.join(_oversized)}[/yellow]")

    # A30: Symlink policy -- reject symlinks in evidence files
    _symlinks: list[str] = []
    if no_follow_symlinks:
        for fpath, arcname in _to_add:
            if fpath.is_symlink():
                _symlinks.append(arcname)
        if _symlinks:
            _msg(f"[yellow]WARN: {len(_symlinks)} symlink(s) detected: "
                 f"{', '.join(_symlinks)}[/yellow]")

    # A30->A31: Required files policy -- verify required evidence exists
    # A31: supports "file:sha256" format for hash-validated requirements
    _missing_required: list[str] = []
    _hash_mismatch_required: list[str] = []  # A31
    if required_files:
        _req_list = [f.strip() for f in required_files.split(",") if f.strip()]
        _available = {arcname: fpath for fpath, arcname in _to_add}
        for req in _req_list:
            if ":" in req:
                # A31: "filename:expected_hash" format
                _req_name, _req_hash = req.split(":", 1)
                _req_name = _req_name.strip()
                _req_hash = _req_hash.strip()
                if _req_name not in _available:
                    _missing_required.append(_req_name)
                elif _req_hash:
                    _actual_hash = _hash_file(_available[_req_name])
                    if _actual_hash != _req_hash:
                        _hash_mismatch_required.append(f"{_req_name}:{_req_hash[:16]}...")
            else:
                if req not in _available:
                    _missing_required.append(req)
        if _missing_required:
            _msg(f"[red]MISSING REQUIRED: {', '.join(_missing_required)}[/red]")
        if _hash_mismatch_required:
            _msg(f"[red]HASH MISMATCH: {', '.join(_hash_mismatch_required)}[/red]")
            _missing_required.extend(_hash_mismatch_required)  # A31: treat as missing for strict

    # A26: omitted evidence affects integrity
    closeout_integrity = state.get("closeout_integrity", "unknown")
    if omitted and closeout_integrity != "partial":
        closeout_integrity = "partial"

    # A57: Structured audit checks for waiver trace model
    _audit_check("omitted_evidence", len(omitted) == 0,
                 "%d file(s) not in manifest" % len(omitted) if omitted else "all evidence tracked")
    _audit_check("required_artifacts_present", len(_missing_required) == 0,
                 "missing: %s" % ", ".join(_missing_required[:5]) if _missing_required else "all required present")
    _audit_check("oversized_files", len(_oversized) == 0,
                 "%d file(s) exceed limit" % len(_oversized) if _oversized else "all within limit")
    _audit_check("symlinks_rejected", len(_symlinks) == 0,
                 "%d symlink(s) detected" % len(_symlinks) if _symlinks else "no symlinks")

    # A57: Create waiver records for non-strict audit failures (policy downgrade)
    if not strict:
        for _ac in _audit_result["checks"]:
            if not _ac["passed"]:
                _existing = [w for w in _audit_result["policy_waivers"]
                             if w.get("check_index") == _ac["index"]]
                if not _existing:
                    _audit_result["policy_waivers"].append(_build_waiver_record(
                        check_name=_ac["check"],
                        check_index=_ac["index"],
                        original_detail=_ac.get("detail", ""),
                        policy_field="strict_audit",
                        reason="strict=False (audit warning, non-blocking)",
                        severity="warning",
                        command="audit",
                        policy_data=_policy_data if _policy_data else None,
                        adjusted_detail="audit check downgraded to warning by non-strict policy",
                        check_entry=_ac,
                    ))

    # A58: Compute audit verdict early -- available in both strict and success paths
    _verify_waiver_integrity(_audit_result)
    # A62: Record waiver_integrity_failed if integrity check found issues
    if _audit_result.get("waiver_integrity") == "invalid":
        _wi_issues = _audit_result.get("waiver_integrity_issues", [])
        _record_failure("waiver_integrity_failed",
                        "waiver integrity: %d issue(s)" % len(_wi_issues),
                        context={"issues": _wi_issues})
    _audit_result["raw_verdict"] = "passed" if _audit_result["failed"] == 0 else "failed"
    _a57_waivers = _audit_result.get("policy_waivers", [])
    _a57_valid_ids = _audit_result.pop("_valid_waiver_ids", set())
    _a57_adjusted = {}
    for w in _a57_waivers:
        if w.get("waiver_id", "") in _a57_valid_ids:
            _ci = w.get("check_index", -1)
            if _ci >= 0 and _ci not in _a57_adjusted:
                _a57_adjusted[_ci] = w
    _a57_policy_failed = max(0, _audit_result["failed"] - len(_a57_adjusted))
    _audit_result["policy_verdict"] = "passed" if _a57_policy_failed == 0 else "failed"
    _audit_result["verdict"] = _audit_result["policy_verdict"]
    _audit_result["policy_waived_checks"] = [
        w["check"] for w in _a57_waivers if w.get("waiver_id", "") in _a57_valid_ids]
    _audit_result["adjusted_check_count"] = len(_a57_adjusted)
    _audit_result["waiver_integrity"] = _audit_result.get("waiver_integrity", "valid")
    # A58: Strict mode overrides -- when strict=True, waivers are voided
    if strict:
        _audit_result["policy_waivers"] = []
        _audit_result["policy_waived_checks"] = []
        _audit_result["adjusted_check_count"] = 0
        _audit_result["policy_verdict"] = _audit_result["raw_verdict"]
        _audit_result["verdict"] = _audit_result["raw_verdict"]

    # Write ZIP
    with _zf.ZipFile(zip_name, "w", _zf.ZIP_DEFLATED) as zf:
        for fpath, arcname in _to_add:
            zf.write(fpath, arcname)
            bundle_files_meta.append({
                "path": arcname, "sha256": _hash_file(fpath),
                "size": fpath.stat().st_size,
            })

        manifest = _build_bundle_manifest(bundle_id, safe_id, bundle_files_meta, timestamp)
        # A41: bind policy provenance into the bundle manifest
        if _policy_data and "_policy_provenance" in _policy_data:
            manifest["policy_provenance"] = _policy_data["_policy_provenance"]
        zf.writestr("bundle_manifest.json",
                     json.dumps(manifest, indent=2, ensure_ascii=False))

        attestation = _build_attestation_record(
            safe_id, bundle_id, timestamp,
            manifest["attestation"]["content_hash"],
            artifact_chain, closeout_integrity,
        )
        # A29: optional signing
        if sign:
            attestation["signature"] = _sign_record(attestation)
        zf.writestr("attestation.json",
                     json.dumps(attestation, indent=2, ensure_ascii=False))

        # A28->A29: MANIFEST.json -- complete evidence pack file index
        _manifest_files = [
            {"path": arcname, "sha256": _hash_file(fpath), "size": fpath.stat().st_size}
            for fpath, arcname in _to_add
        ]
        # A29: include generated members (bundle_manifest, attestation)
        bm_bytes = json.dumps(manifest, indent=2, ensure_ascii=False).encode("utf-8")
        att_bytes = json.dumps(attestation, indent=2, ensure_ascii=False).encode("utf-8")
        _manifest_files.append({
            "path": "bundle_manifest.json",
            "sha256": hashlib.sha256(bm_bytes).hexdigest(),
            "size": len(bm_bytes),
        })
        _manifest_files.append({
            "path": "attestation.json",
            "sha256": hashlib.sha256(att_bytes).hexdigest(),
            "size": len(att_bytes),
        })
        # A29: self-entry (hash unknown until written; set to empty)
        _manifest_files.append({
            "path": "MANIFEST.json",
            "sha256": "",
            "size": 0,
        })
        _manifest_index = {
            "manifest_version": "2.0",
            "bundle_id": bundle_id,
            "run_id": safe_id,
            "generated_at": timestamp,
            "files": _manifest_files,
        }
        zf.writestr("MANIFEST.json",
                     json.dumps(_manifest_index, indent=2, ensure_ascii=False))

    # A26->A27: sidecar ZIP hash
    zip_hash = _hash_file(Path(zip_name))
    sidecar_path = Path(zip_name + ".sha256")
    sidecar_path.write_text(f"{zip_hash}  {Path(zip_name).name}\n", encoding="utf-8")

    # A27: embed ZIP hash in persisted manifest for cross-verification
    manifest["zip_sha256"] = zip_hash

    # Re-persist manifest + attestation with zip_sha256 included
    (run_dir / f"bundle_manifest_{bundle_id}.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    (run_dir / f"attestation_{bundle_id}.json").write_text(
        json.dumps(attestation, indent=2, ensure_ascii=False), encoding="utf-8")

    # A30: Anchor log -- append bundle entry for chain verification
    if anchor_log:
        _al_path = Path(anchor_log)
        _al_path.parent.mkdir(parents=True, exist_ok=True)
        # A31: Compute prev_hash from last entry in log
        _prev_hash = ""
        if _al_path.exists():
            _existing = _al_path.read_text(encoding="utf-8").strip().split("\n")
            _existing = [l for l in _existing if l.strip()]
            if _existing:
                _prev_hash = hashlib.sha256(_existing[-1].encode("utf-8")).hexdigest()
        _al_entry = {
            "bundle_id": bundle_id,
            "zip_sha256": zip_hash,
            "bundle_hash": attestation.get("artifact_chain", [{}])[-1].get("sha256", "") if attestation.get("artifact_chain") else "",
            "signed": "signature" in attestation,
            "key_id": os.environ.get("AIHUB_SIGNING_KEY_ID", ""),
            "prev_hash": _prev_hash,
            "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "run_id": safe_id,
        }
        _al_line = json.dumps(_al_entry, ensure_ascii=False)
        with _al_path.open("a", encoding="utf-8") as _f:
            _f.write(_al_line + "\n")
        _msg(f"[green]Anchor log entry appended: {_al_path}[/green]")

    # A63: Operational failure registry -- verify integrity and record failures
    # 1. Artifact chain integrity
    _chain_broken = []
    for _ci, _ce in enumerate(artifact_chain):
        _sha = _ce.get("sha256", "")
        if not _sha or len(_sha) != 64:
            _chain_broken.append({"index": _ci, "artifact": _ce.get("artifact", "?"),
                                  "issue": "invalid_hash"})
    if _chain_broken:
        _record_failure("artifact_chain_integrity",
                        "%d chain link(s) with invalid hash" % len(_chain_broken),
                        context={"broken_links": _chain_broken})

    # 2. Manifest/bundle file consistency
    _bundle_file_set = {m.get("path", "") for m in bundle_files_meta}
    _manifest_file_set = {m.get("path", "") for m in manifest.get("files", [])}
    if _bundle_file_set != _manifest_file_set:
        _diff = _bundle_file_set.symmetric_difference(_manifest_file_set)
        _record_failure("manifest_mismatch",
                        "%d file(s) mismatch between bundle and manifest" % len(_diff),
                        context={"diff_files": sorted(_diff)[:10]})

    # 3. Signature structure verification (if signed)
    # A64: Check for algorithm and signature/hash (field name varies by implementation)
    if sign and "signature" in attestation:
        _sig = attestation["signature"]
        _algo = _sig.get("algorithm", "")
        _has_sig = bool(_sig.get("signature") or _sig.get("hash"))
        # Only check signature structure if algorithm is not "none" (unsigned mode)
        if _algo and _algo != "none" and not _has_sig:
            _record_failure("signature_failure",
                            "Attestation signature missing algorithm or signature/hash",
                            context={"signature_keys": list(_sig.keys())})

    # 4. Anchor log chain verification (if anchor_log used and has prior entries)
    if anchor_log:
        _al_verify_path = Path(anchor_log)
        if _al_verify_path.exists():
            _al_lines = [l for l in _al_verify_path.read_text(encoding="utf-8").strip().split("\n") if l.strip()]
            if len(_al_lines) >= 2:
                # Verify last entry's prev_hash matches hash of second-to-last
                _last = json.loads(_al_lines[-1])
                _second_last_hash = hashlib.sha256(_al_lines[-2].encode("utf-8")).hexdigest()
                if _last.get("prev_hash") and _last["prev_hash"] != _second_last_hash:
                    _record_failure("anchor_log_corruption",
                                    "Anchor log prev_hash mismatch at entry %d" % (len(_al_lines) - 1),
                                    context={"expected": _second_last_hash[:16],
                                             "actual": _last["prev_hash"][:16]})

    # 5. Filesystem containment -- A64: exhaustive check (no longer capped at 50)
    _containment_violations = []
    if run_dir:
        _run_dir_resolved = Path(run_dir).resolve()
        for _ef in evidence_manifest.get("files", []):
            _efp = _ef.get("path", _ef.get("file_path", ""))
            if _efp:
                _full = (Path(run_dir) / _efp).resolve()
                try:
                    _full.relative_to(_run_dir_resolved)
                except ValueError:
                    _containment_violations.append(_efp)
    if _containment_violations:
        _record_failure("filesystem_containment",
                        "%d file(s) outside containment boundary" % len(_containment_violations),
                        context={"violations": _containment_violations[:10],
                                 "exhaustive": True})  # A64: mark as exhaustive check

    # A65: Severity classification is now automatic via _recompute_severity()
    # called at the end of every _record_failure() invocation. No standalone
    # recomputation block needed -- blocking_failures, warning_failures,
    # operational_verdict, exit_code, and process_exit_code are always current.

    # A27->A28: strict mode -- fail on omitted evidence or oversized files
    _strict_failures: list[str] = []
    _strict_severity: dict[str, int] = {}  # A28: severity breakdown
    if strict:
        if omitted:
            _strict_failures.append(f"{len(omitted)} omitted evidence file(s)")
            _strict_severity["omitted_evidence"] = len(omitted)
        if _oversized:
            _strict_failures.append(f"{len(_oversized)} oversized file(s)")
            _strict_severity["oversized_files"] = len(_oversized)
        if _symlinks:  # A30
            _strict_failures.append(f"{len(_symlinks)} symlink(s) detected")
            _strict_severity["symlinks"] = len(_symlinks)
        if _missing_required:  # A30
            _strict_failures.append(f"{len(_missing_required)} required file(s) missing")
            _strict_severity["missing_required"] = len(_missing_required)
        if _strict_failures:
            _msg(f"[red]STRICT AUDIT FAILED: {'; '.join(_strict_failures)}[/red]")
            # A61: Record structured failure with multi-failure support
            _record_failure("strict_audit",
                            "strict audit: %s" % "; ".join(_strict_failures),
                            context={"severity_breakdown": _strict_severity})
            if as_json:
                _json_out = dict(manifest)
                _json_out["sidecar_sha256"] = zip_hash
                _json_out["oversized_files"] = _oversized
                _json_out["strict_failures"] = _strict_failures
                _json_out["strict_severity"] = _strict_severity
                _json_out["max_file_mb"] = max_file_mb or (_max_bytes // 1024 // 1024)
                # A58->A62: Include versioned audit result fields in strict failure JSON
                _json_out["result_schema_version"] = _audit_result["result_schema_version"]
                _json_out["error_profile"] = _audit_result["error_profile"]
                _json_out["strict_mode"] = _audit_result["strict_mode"]
                _json_out["waiver_mode"] = _audit_result["waiver_mode"]
                _json_out["failure_type"] = _audit_result["failure_type"]
                _json_out["failure_types"] = _audit_result["failure_types"]
                _json_out["failure_events"] = _audit_result["failure_events"]
                _json_out["failure_details"] = _audit_result["failure_details"]
                _json_out["exit_reason"] = _audit_result["exit_reason"]
                _json_out["exit_reason_code"] = _audit_result["exit_reason_code"]
                _json_out["exit_code"] = _audit_result["exit_code"]
                _json_out["process_exit_code"] = _audit_result["process_exit_code"]
                _json_out["checks"] = _audit_result["checks"]
                _json_out["policy_waivers"] = _audit_result["policy_waivers"]
                _json_out["raw_verdict"] = _audit_result["raw_verdict"]
                _json_out["policy_verdict"] = _audit_result["policy_verdict"]
                _json_out["verdict"] = _audit_result["verdict"]
                _json_out["waiver_integrity"] = _audit_result["waiver_integrity"]
                _json_out["policy_waived_checks"] = _audit_result["policy_waived_checks"]
                _json_out["adjusted_check_count"] = _audit_result["adjusted_check_count"]
                # A64->A65: Severity classification and operational verdict
                _json_out["operational_verdict"] = _audit_result["operational_verdict"]
                _json_out["blocking_failures"] = _audit_result["blocking_failures"]
                _json_out["warning_failures"] = _audit_result["warning_failures"]
                _json_out["waived_failures"] = _audit_result["waived_failures"]
                _emit_json(_json_out)
            raise typer.Exit(1)
        else:
            _msg("[green]Strict: PASSED[/green]")

    # A45->A46: Completeness check -- policy-governed artifact classification
    _completeness_report: dict[str, Any] = {}
    if completeness_check:
        _run_dir = Path(run_dir)
        # A46: Policy-controlled artifact classification
        _policy_ignored = _policy_data.get("ignored_artifacts", [])
        _policy_generated = _policy_data.get("generated_artifacts", [])
        _completeness_strict = _policy_data.get("completeness_strict", False)

        # Files generated by the audit process itself (not evidence artifacts)
        _audit_generated = {
            f"attestation_{bundle_id}.json",
            f"bundle_manifest_{bundle_id}.json",
            f"{Path(zip_name).name}" if zip_name else "",
            f"{Path(zip_name).name}.sha256" if zip_name else "",
            "trace.json",
            "isolation-cleanup.json",
        }
        _audit_generated.discard("")
        # A46: Merge policy-declared generated patterns
        for _gp in _policy_generated:
            _audit_generated.add(_gp)

        def _matches_patterns(rel_path: str, patterns: list[str]) -> bool:
            """Check if rel_path matches any glob pattern (A46)."""
            for _pat in patterns:
                if fnmatch.fnmatch(rel_path, _pat):
                    return True
                # Also check basename only
                if fnmatch.fnmatch(Path(rel_path).name, _pat):
                    return True
            return False

        # Get all files in the run directory
        _all_run_files: set[str] = set()
        _ignored_files: set[str] = set()
        for _p in _run_dir.rglob("*"):
            if _p.is_file():
                _rel = str(_p.relative_to(_run_dir)).replace("\\", "/")
                if _rel in _audit_generated:
                    continue
                # A46: Apply policy ignored_artifacts patterns
                if _matches_patterns(_rel, _policy_ignored):
                    _ignored_files.add(_rel)
                    continue
                _all_run_files.add(_rel)

        # Get files included in the bundle
        _bundle_files: set[str] = set()
        if manifest.get("files"):
            for _f in manifest["files"]:
                _bundle_files.add(_f.get("path", ""))

        # Categorize missing files
        _missing_from_bundle = sorted(_all_run_files - _bundle_files)

        # A46: Hash-redact missing file names for privacy
        _missing_hashed = []
        for _mf in _missing_from_bundle:
            _mh = hashlib.sha256(_mf.encode("utf-8")).hexdigest()[:16]
            _missing_hashed.append({"path_hash": _mh, "basename": Path(_mf).name})

        _prov = _policy_data.get("_policy_provenance", {})
        _completeness_report = {
            "total_run_files": len(_all_run_files),
            "total_bundle_files": len(_bundle_files),
            "total_ignored": len(_ignored_files),
            "required_present": len(_missing_required) == 0,
            "missing_from_bundle": _missing_hashed,
            "missing_count": len(_missing_from_bundle),
            "complete": len(_missing_from_bundle) == 0 and len(_missing_required) == 0,
            "completeness_strict": _completeness_strict,
            "policy_governed": bool(_policy_data),
        }
        if _prov:
            _completeness_report["policy_sha256"] = _prov.get("policy_sha256", "")

        if _completeness_report["complete"]:
            _msg(f"[green]Completeness: PASSED ({len(_bundle_files)} files in bundle)[/green]")
        else:
            _severity = "red" if _completeness_strict else "yellow"
            _msg(f"[{_severity}]Completeness: {_completeness_report['missing_count']} file(s) not in bundle[/red]" if _completeness_strict
                 else f"[yellow]Completeness: {_completeness_report['missing_count']} file(s) not in bundle[/yellow]")
            if _missing_hashed:
                _display = ", ".join(f"{m['basename']}({m['path_hash']})" for m in _missing_hashed[:5])
                _msg(f"[{_severity}]  Missing: {_display}[/red]" if _completeness_strict
                     else f"[yellow]  Missing: {_display}[/yellow]")
            if _completeness_strict:
                _msg(f"[red]COMPLETENESS STRICT: blocking failure[/red]")
                # A61: Record structured failure with multi-failure support
                _record_failure("completeness_strict",
                                "completeness strict: %d file(s) not in bundle" % _completeness_report.get("missing_count", 0),
                                context={"missing_count": _completeness_report.get("missing_count", 0)})
                # A59->A62: Emit full result structure before completeness strict exit
                if as_json:
                    _cj = dict(manifest) if 'manifest' in dir() else {}
                    _cj["result_schema_version"] = _audit_result["result_schema_version"]
                    _cj["error_profile"] = _audit_result["error_profile"]
                    _cj["strict_mode"] = _audit_result["strict_mode"]
                    _cj["waiver_mode"] = _audit_result["waiver_mode"]
                    _cj["failure_type"] = _audit_result["failure_type"]
                    _cj["failure_types"] = _audit_result["failure_types"]
                    _cj["failure_events"] = _audit_result["failure_events"]
                    _cj["failure_details"] = _audit_result["failure_details"]
                    _cj["exit_reason"] = _audit_result["exit_reason"]
                    _cj["exit_reason_code"] = _audit_result["exit_reason_code"]
                    _cj["exit_code"] = _audit_result["exit_code"]
                    _cj["process_exit_code"] = _audit_result["process_exit_code"]
                    _cj["checks"] = _audit_result["checks"]
                    _cj["policy_waivers"] = _audit_result["policy_waivers"]
                    _cj["raw_verdict"] = _audit_result["raw_verdict"]
                    _cj["policy_verdict"] = _audit_result["policy_verdict"]
                    _cj["verdict"] = _audit_result["verdict"]
                    _cj["waiver_integrity"] = _audit_result["waiver_integrity"]
                    _cj["policy_waived_checks"] = _audit_result["policy_waived_checks"]
                    _cj["adjusted_check_count"] = _audit_result["adjusted_check_count"]
                    # A64: Severity classification and operational verdict
                    _cj["operational_verdict"] = _audit_result["operational_verdict"]
                    _cj["blocking_failures"] = _audit_result["blocking_failures"]
                    _cj["warning_failures"] = _audit_result["warning_failures"]
                    _cj["waived_failures"] = _audit_result["waived_failures"]  # A66
                    _cj["completeness"] = _completeness_report
                    _emit_json(_cj)
                raise typer.Exit(1)

    # A26->A60: Pure JSON output on success path
    if as_json:
        _json_out = dict(manifest)
        _json_out["sidecar_sha256"] = zip_hash
        # A60: Consistent sourcing from _audit_result
        _json_out["strict_mode"] = _audit_result["strict_mode"]
        _json_out["max_file_mb"] = max_file_mb or (_max_bytes // 1024 // 1024)
        _json_out["symlinks"] = _symlinks
        _json_out["oversized_files"] = _oversized
        _json_out["missing_required"] = _missing_required
        # A57->A62: Audit waiver trace fields with schema version + multi-failure + symbolic codes
        _json_out["result_schema_version"] = _audit_result["result_schema_version"]
        _json_out["error_profile"] = _audit_result["error_profile"]
        _json_out["waiver_mode"] = _audit_result["waiver_mode"]
        _json_out["failure_type"] = _audit_result["failure_type"]
        _json_out["failure_types"] = _audit_result["failure_types"]
        _json_out["failure_events"] = _audit_result["failure_events"]
        _json_out["failure_details"] = _audit_result["failure_details"]
        _json_out["exit_reason"] = _audit_result["exit_reason"]
        _json_out["exit_reason_code"] = _audit_result["exit_reason_code"]
        _json_out["exit_code"] = _audit_result["exit_code"]
        _json_out["process_exit_code"] = _audit_result["process_exit_code"]
        _json_out["checks"] = _audit_result["checks"]
        _json_out["policy_waivers"] = _audit_result["policy_waivers"]
        _json_out["raw_verdict"] = _audit_result["raw_verdict"]
        _json_out["policy_verdict"] = _audit_result["policy_verdict"]
        _json_out["verdict"] = _audit_result["verdict"]
        _json_out["waiver_integrity"] = _audit_result["waiver_integrity"]
        _json_out["policy_waived_checks"] = _audit_result["policy_waived_checks"]
        _json_out["adjusted_check_count"] = _audit_result["adjusted_check_count"]
        # A64: Severity classification and operational verdict
        _json_out["operational_verdict"] = _audit_result["operational_verdict"]
        _json_out["blocking_failures"] = _audit_result["blocking_failures"]
        _json_out["warning_failures"] = _audit_result["warning_failures"]
        _json_out["waived_failures"] = _audit_result["waived_failures"]  # A66
        if completeness_check:
            _json_out["completeness"] = _completeness_report
        if anchor_log:
            _json_out["anchor_log"] = str(anchor_log)
        _emit_json(_json_out)

    # A64: Align CLI process exit code with JSON exit_code
    # If blocking operational failures exist, exit with non-zero code
    if _audit_result["exit_code"] > 0:
        raise typer.Exit(_audit_result["exit_code"])


@paper_app.command("verify")
def paper_verify(
    zip_path: str = typer.Option(..., "--zip", "-z", help="Path to audit bundle ZIP"),
    sidecar: Optional[str] = typer.Option(None, "--sidecar", "-s",
                                           help="Path to .sha256 sidecar (default: ZIP.sha256)"),
    run_dir: Optional[str] = typer.Option(None, "--run-dir", "-d",
                                           help="Run directory to verify persisted manifest (A29)"),
    as_json: bool = typer.Option(False, "--json", help="Print verification result as JSON (A28)"),
    check_artifacts: bool = typer.Option(True, "--check-artifacts/--no-check-artifacts",
                                          help="Verify each artifact hash in the ZIP"),
    anchor_log: Optional[str] = typer.Option(None, "--anchor-log",
                                              help="Anchor log to cross-verify ZIP hash (A32)"),
    policy_file: str = typer.Option("", "--policy", help="Path to audit policy file (A39)"),
    expected_policy_hash: str = typer.Option("", "--expected-policy-hash",
                                              help="Expected SHA-256 hash of the policy file (A41)"),
    strict_policy: bool = typer.Option(False, "--strict-policy",
                                        help="Escalate schema warnings to blocking failures (A44)"),
    completeness_check: bool = typer.Option(False, "--completeness-check",
                                             help="Re-verify completeness from bundle vs run directory (A47)"),
):
    """Verify an audit package ZIP end-to-end (A28->A32->A44).

    Checks: ZIP validity, sidecar hash, bundle manifest integrity,
    MANIFEST.json file index, attestation record, artifact hashes,
    and optionally persisted manifest zip_sha256.

    A41: --expected-policy-hash verifies policy file integrity.
    """
    import zipfile as _zf

    init_env()
    _msg = err_console.print if as_json else console.print
    zp = Path(zip_path)

    # A39->A44: Load policy file with provenance
    _policy_data: dict[str, Any] = {}
    if policy_file:
        _policy_data = _load_audit_policy(policy_file, expected_hash=expected_policy_hash,
                                           strict_policy=strict_policy)
        _prov = _policy_data.get("_policy_provenance", {})
        _msg(f"[green]Policy loaded[/green]: {_policy_data.get('description', 'unnamed')} "
             f"(schema={_policy_data.get('schema_version', '?')}, "
             f"hash={_prov.get('policy_sha256', '?')[:16]}...)")

    result: dict[str, Any] = {
        "zip_path": str(zp),
        "checks": [],
        "passed": 0,
        "failed": 0,
        "verdict": "unknown",
        "verification_mode": "full" if check_artifacts else "metadata_only",  # A29
        "policy_waivers": [],  # A53: Structured waiver trace records
    }

    def _check(name: str, ok: bool, detail: str = "") -> None:
        entry = {"check": name, "passed": ok,
                 "index": len(result["checks"])}  # A54: stable check index
        if detail:
            entry["detail"] = detail
        result["checks"].append(entry)
        if ok:
            result["passed"] += 1
            _msg(f"  [green]PASS[/green] {name}" + (f" -- {detail}" if detail else ""))
        else:
            result["failed"] += 1
            _msg(f"  [red]FAIL[/red] {name}" + (f" -- {detail}" if detail else ""))

    _msg(f"[bold]A32 Audit Verification: {zp.name}[/bold]")

    # Check 1: ZIP exists
    if not zp.exists():
        _check("zip_exists", False, f"{zp} not found")
        result["verdict"] = "failed"
        if as_json:
            _emit_json(result)
        raise typer.Exit(1)
    _check("zip_exists", True)

    # Check 2: ZIP is valid
    try:
        zf = _zf.ZipFile(zp, "r")
        _check("zip_valid", True)
    except _zf.BadZipFile:
        _check("zip_valid", False, "BadZipFile")
        result["verdict"] = "failed"
        if as_json:
            _emit_json(result)
        raise typer.Exit(1)

    zip_names = zf.namelist()

    # Check 3: Sidecar hash verification
    sp = Path(sidecar) if sidecar else Path(str(zp) + ".sha256")
    if sp.exists():
        sidecar_text = sp.read_text(encoding="utf-8").strip()
        sidecar_hash = sidecar_text.split()[0] if sidecar_text else ""
        actual_hash = hashlib.sha256(zp.read_bytes()).hexdigest()
        _check("sidecar_hash_match", sidecar_hash == actual_hash,
               f"sidecar={sidecar_hash[:16]}... actual={actual_hash[:16]}...")
    else:
        _check("sidecar_hash_match", False, f"sidecar not found: {sp}")

    # Check 4: bundle_manifest.json present and valid
    bm_ok = False
    bm_data: dict[str, Any] = {}
    if "bundle_manifest.json" in zip_names:
        try:
            bm_data = json.loads(zf.read("bundle_manifest.json"))
            _check("bundle_manifest_present", True)
            bm_ok = True
        except (json.JSONDecodeError, KeyError):
            _check("bundle_manifest_present", False, "invalid JSON")
    else:
        _check("bundle_manifest_present", False, "not in ZIP")

    # Check 5: MANIFEST.json present and valid (A28)
    mf_ok = False
    mf_data: dict[str, Any] = {}
    if "MANIFEST.json" in zip_names:
        try:
            mf_data = json.loads(zf.read("MANIFEST.json"))
            _check("manifest_index_present", True)
            mf_ok = True
        except (json.JSONDecodeError, KeyError):
            _check("manifest_index_present", False, "invalid JSON")
    else:
        _check("manifest_index_present", False, "not in ZIP (A28 feature)")

    # Check 6: attestation.json present and valid
    att_ok = False
    att_data: dict[str, Any] = {}
    if "attestation.json" in zip_names:
        try:
            att_data = json.loads(zf.read("attestation.json"))
            _check("attestation_present", True)
            att_ok = True
        except (json.JSONDecodeError, KeyError):
            _check("attestation_present", False, "invalid JSON")
    else:
        _check("attestation_present", False, "not in ZIP")

    # Check 7: Content hash verification (bundle manifest)
    if bm_ok and "files" in bm_data:
        _sorted = sorted([(f["path"], f["sha256"]) for f in bm_data["files"]])
        recomputed = hashlib.sha256(
            json.dumps(_sorted, sort_keys=True).encode("utf-8")
        ).hexdigest()
        stored = bm_data.get("attestation", {}).get("content_hash", "")
        _check("content_hash_valid", recomputed == stored,
               f"recomputed={recomputed[:16]}... stored={stored[:16]}...")
    else:
        _check("content_hash_valid", False, "no bundle manifest files")

    # Check 8: MANIFEST.json file hashes (A28->A30)
    if mf_ok and check_artifacts and "files" in mf_data:
        manifest_ok_count = 0
        manifest_fail_count = 0
        manifest_skip_count = 0
        for entry in mf_data["files"]:
            fpath = entry["path"]
            expected = entry["sha256"]
            # A29: skip self-entry (MANIFEST.json cannot hash itself)
            if fpath == "MANIFEST.json" and expected == "":
                manifest_skip_count += 1
                continue
            if fpath in zip_names:
                actual = hashlib.sha256(zf.read(fpath)).hexdigest()
                if actual == expected:
                    manifest_ok_count += 1
                else:
                    manifest_fail_count += 1
            else:
                manifest_fail_count += 1
        _check("manifest_file_hashes", manifest_fail_count == 0,
               f"{manifest_ok_count} ok, {manifest_fail_count} failed"
               + (f", {manifest_skip_count} skipped" if manifest_skip_count else ""))
    elif mf_ok:
        _check("manifest_file_hashes", True, "skipped (--no-check-artifacts)")
    else:
        _check("manifest_file_hashes", False, "no MANIFEST.json")

    # Check 9: Attestation artifact hashes consistency (A28->A29: full set equality)
    if att_ok and bm_ok:
        att_chain = att_data.get("artifact_hashes", [])
        bm_chain = bm_data.get("files", [])
        att_artifacts = {a["artifact"]: a["sha256"] for a in att_chain}
        # A29: exclude generated members from bundle manifest comparison
        bm_artifacts = {f["path"]: f["sha256"] for f in bm_chain
                        if f["path"] not in _AUDIT_GENERATED_MEMBERS}
        # A29: require full set equality, not just overlap
        att_keys = set(att_artifacts.keys())
        bm_keys = set(bm_artifacts.keys())
        overlap = att_keys & bm_keys
        mismatches = [k for k in overlap if att_artifacts[k] != bm_artifacts[k]]
        missing_in_att = bm_keys - att_keys
        extra_in_att = att_keys - bm_keys
        _full_match = (len(mismatches) == 0 and len(missing_in_att) == 0
                       and len(extra_in_att) == 0)
        detail_parts = [f"{len(overlap)} overlapping"]
        if mismatches:
            detail_parts.append(f"{len(mismatches)} hash mismatches")
        if missing_in_att:
            detail_parts.append(f"{len(missing_in_att)} missing in attestation")
        if extra_in_att:
            detail_parts.append(f"{len(extra_in_att)} extra in attestation")
        _check("attestation_consistency", _full_match,
               ", ".join(detail_parts))
    else:
        _check("attestation_consistency", False, "missing manifest or attestation")

    # Check 10: Persisted manifest zip_sha256 verification (A29)
    if run_dir:
        rd = Path(run_dir)
        _bm_id = bm_data.get("bundle_id", "") if bm_ok else ""
        persisted_path = rd / f"bundle_manifest_{_bm_id}.json" if _bm_id else None
        if persisted_path and persisted_path.exists():
            try:
                persisted = json.loads(persisted_path.read_text(encoding="utf-8"))
                persisted_zip = persisted.get("zip_sha256", "")
                actual_zip = hashlib.sha256(zp.read_bytes()).hexdigest()
                _check("persisted_manifest_zip_sha256",
                       persisted_zip == actual_zip,
                       f"persisted={persisted_zip[:16]}... actual={actual_zip[:16]}...")
            except (json.JSONDecodeError, OSError) as _e:
                _check("persisted_manifest_zip_sha256", False, f"read error: {_e}")
        else:
            _check("persisted_manifest_zip_sha256", False,
                   f"not found: {persisted_path}")
    else:
        _check("persisted_manifest_zip_sha256", True, "skipped (no --run-dir)")

    # Check 11: Signature verification (A29->A31)
    if att_ok and "signature" in att_data:
        sig_block = att_data["signature"]
        sig_algo = sig_block.get("algorithm", "none")
        sig_value = sig_block.get("signature", "")
        sig_key_id = sig_block.get("key_id", "")  # A31
        if sig_algo == "HMAC-SHA256" and sig_value:
            # Rebuild attestation without signature, recompute HMAC
            _att_copy = {k: v for k, v in att_data.items() if k != "signature"}
            _signing_key = os.environ.get("AIHUB_SIGNING_KEY", "")
            if _signing_key:
                import hmac as _hmac
                _payload = json.dumps(_att_copy, sort_keys=True, ensure_ascii=False).encode("utf-8")
                _expected = _hmac.new(_signing_key.encode("utf-8"), _payload, hashlib.sha256).hexdigest()
                _match = _expected == sig_value
                _detail = f"algo={sig_algo}, match={_match}"
                if sig_key_id:
                    _detail += f", key_id={sig_key_id}"  # A31
                _check("signature_valid", _match, _detail)
            else:
                _check("signature_valid", False, "AIHUB_SIGNING_KEY not set")
        elif sig_algo == "none":
            _check("signature_valid", True, "unsigned (algorithm=none)")
        else:
            _check("signature_valid", False, f"unknown algorithm: {sig_algo}")
    else:
        _check("signature_valid", True, "no signature present (unsigned bundle)")

    # Check 12: Anchor log cross-verification (A32->A33)
    if anchor_log:
        _al_path = Path(anchor_log)
        if _al_path.exists():
            _actual_zip_hash = hashlib.sha256(zp.read_bytes()).hexdigest()
            _al_lines = _al_path.read_text(encoding="utf-8").strip().split("\n")
            _al_lines = [l for l in _al_lines if l.strip()]
            _found_in_log = False
            _al_malformed = 0  # A33: count malformed lines
            for _al_line in _al_lines:
                try:
                    _al_entry = json.loads(_al_line)
                    if _al_entry.get("zip_sha256", "") == _actual_zip_hash:
                        _found_in_log = True
                except json.JSONDecodeError:
                    _al_malformed += 1
            _c12_detail = f"zip_sha256 {'found' if _found_in_log else 'NOT found'} in anchor log"
            if _al_malformed:
                _c12_detail += f", {_al_malformed} malformed lines skipped"
            _check("anchor_log_cross_verify", _found_in_log, _c12_detail)
        else:
            _check("anchor_log_cross_verify", False, f"log not found: {_al_path}")
    else:
        _check("anchor_log_cross_verify", True, "skipped (no --anchor-log)")

    zf.close()

    # A30: Compute trust_level based on signature and verification results
    _sig_check = next((c for c in result["checks"] if c["check"] == "signature_valid"), None)
    _sig_detail = _sig_check.get("detail", "") if _sig_check else ""
    if _sig_check and _sig_check["passed"]:
        if "no signature present" in _sig_detail or "unsigned" in _sig_detail:
            result["trust_level"] = "unsigned_valid"
        elif "algorithm=none" in _sig_detail:
            result["trust_level"] = "unsigned_valid"
        else:
            result["trust_level"] = "signed_trusted"
    elif _sig_check and not _sig_check["passed"]:
        if "AIHUB_SIGNING_KEY not set" in _sig_detail:
            result["trust_level"] = "signed_unverified"
        else:
            result["trust_level"] = "signed_unverified"
    else:
        result["trust_level"] = "unknown"

    # A48: Deferred final verdict -- computed after all checks including completeness
    # (verdict and trust_summary are computed below after completeness block)

    # A47->A48: Completeness re-verification from bundle vs run directory
    if completeness_check:
        _msg("\n[bold]A47 Completeness Re-verification[/bold]")
        _comp_strict = _policy_data.get("completeness_strict", False) if _policy_data else False
        _comp_report: dict[str, Any] = {
            "mode": "unknown",
            "verified": False,
        }

        if run_dir and bm_ok and bm_data.get("files"):
            # Full re-verification: compare run_dir files against bundle manifest
            _rd = Path(run_dir)
            if _rd.exists():
                _policy_ignored = _policy_data.get("ignored_artifacts", [])
                _policy_generated = _policy_data.get("generated_artifacts", [])
                _audit_generated = {
                    "trace.json",
                    "isolation-cleanup.json",
                }
                for _gp in _policy_generated:
                    _audit_generated.add(_gp)

                # Get bundle files from manifest
                _bundle_files: set[str] = set()
                for _bf in bm_data["files"]:
                    _bundle_files.add(_bf.get("path", ""))

                # Get bundle ZIP member names for comparison
                _zip_members: set[str] = set(zip_names)

                # Scan run directory
                _rd_files: set[str] = set()
                _rd_ignored: set[str] = set()
                for _rp in _rd.rglob("*"):
                    if _rp.is_file():
                        _rel = str(_rp.relative_to(_rd)).replace("\\", "/")
                        if _rel in _audit_generated:
                            continue
                        # Apply ignored patterns
                        _is_ignored = False
                        for _pat in _policy_ignored:
                            if fnmatch.fnmatch(_rel, _pat) or fnmatch.fnmatch(Path(_rel).name, _pat):
                                _is_ignored = True
                                break
                        if _is_ignored:
                            _rd_ignored.add(_rel)
                            continue
                        _rd_files.add(_rel)

                # Compare: run_dir files should all be in the bundle
                _missing = sorted(_rd_files - _bundle_files)
                _extra_in_bundle = sorted(_bundle_files - _rd_files)

                # Hash-redact missing files
                _missing_hashed = []
                for _mf in _missing:
                    _mh = hashlib.sha256(_mf.encode("utf-8")).hexdigest()[:16]
                    _missing_hashed.append({"path_hash": _mh, "basename": Path(_mf).name})

                _comp_report = {
                    "mode": "verified",
                    "verified": len(_missing) == 0,
                    "total_run_files": len(_rd_files),
                    "total_bundle_files": len(_bundle_files),
                    "total_ignored": len(_rd_ignored),
                    "missing_from_bundle": _missing_hashed,
                    "missing_count": len(_missing),
                    "complete": len(_missing) == 0,
                    "completeness_strict": _comp_strict,
                    "policy_governed": bool(_policy_data),
                }

                _check("completeness_reverified", len(_missing) == 0,
                       f"{len(_rd_files)} run files, {len(_bundle_files)} bundle files, "
                       f"{len(_missing)} missing")
            else:
                _comp_report["mode"] = "error"
                _comp_report["error"] = "run_dir not found"
                _check("completeness_reverified", False, f"run_dir not found: {run_dir}")
        else:
            # Claim-only: check if completeness data exists in the attestation
            _stored_comp = att_data.get("completeness", {}) if att_ok else {}
            if _stored_comp:
                _comp_report = {
                    "mode": "claim_only",
                    "verified": False,
                    "stored_completeness": _stored_comp,
                    "note": "no run_dir provided -- using stored completeness claim",
                }
                _check("completeness_claim_present", True,
                       f"stored: complete={_stored_comp.get('complete', '?')}")
            else:
                _comp_report = {
                    "mode": "claim_only",
                    "verified": False,
                    "note": "no run_dir and no stored completeness data",
                }
                _check("completeness_claim_present", False,
                       "no stored completeness in attestation")

        result["completeness"] = _comp_report
        # A48->A50: Compute completeness_verdict
        _comp_mode = _comp_report.get("mode", "unknown")
        _comp_verified = _comp_report.get("verified", False)

        # A50: Raw completeness pass (before policy adjustment)
        result["raw_completeness_pass"] = _comp_verified if _comp_mode == "verified" else None

        if _comp_mode == "verified" and _comp_verified:
            result["completeness_verdict"] = "verified"
        elif _comp_mode == "verified" and not _comp_verified:
            result["completeness_verdict"] = "verified_failed"
        elif _comp_mode == "claim_only":
            result["completeness_verdict"] = "claim_only"
        elif _comp_mode == "error":
            result["completeness_verdict"] = "error"
        else:
            result["completeness_verdict"] = "unknown"

        # A49->A50: Completeness claim binding with deeper comparison
        _stored_comp = att_data.get("completeness", {}) if att_ok else {}
        _drift_severity = "none"
        if _comp_mode == "verified" and _stored_comp:
            # Deep comparison: complete, missing_count, total_run_files, policy_sha256, total_ignored
            _stored_complete = _stored_comp.get("complete", None)
            _recomputed_complete = _comp_verified
            _stored_missing = _stored_comp.get("missing_count", -1)
            _recomputed_missing = _comp_report.get("missing_count", -1)
            _stored_run_files = _stored_comp.get("total_run_files", -1)
            _recomputed_run_files = _comp_report.get("total_run_files", -1)
            _stored_policy = _stored_comp.get("policy_sha256", "")
            _recomputed_policy = _comp_report.get("policy_sha256", "")
            _stored_ignored = _stored_comp.get("total_ignored", -1)
            _recomputed_ignored = _comp_report.get("total_ignored", -1)

            # Count drift dimensions (skip sentinel -1 values)
            _drift_dims = 0
            if _stored_complete != _recomputed_complete:
                _drift_dims += 2  # complete mismatch is high severity
            if _stored_missing != _recomputed_missing and _stored_missing != -1:
                _drift_dims += 1
            if _stored_run_files != _recomputed_run_files and _stored_run_files != -1:
                _drift_dims += 1
            if _stored_policy and _recomputed_policy and _stored_policy != _recomputed_policy:
                _drift_dims += 1
            if _stored_ignored != _recomputed_ignored and _stored_ignored != -1:
                _drift_dims += 1

            _claim_matches = (_drift_dims == 0)
            if _drift_dims >= 2:
                _drift_severity = "high"
            elif _drift_dims == 1:
                _drift_severity = "low"
            else:
                _drift_severity = "none"

            result["completeness_trust_status"] = "verified_matched" if _claim_matches else "verified_drift"
            result["completeness_drift_severity"] = _drift_severity
            result["completeness_drift_dims"] = _drift_dims
            if not _claim_matches:
                _msg(f"[yellow]Completeness drift ({_drift_severity}, {_drift_dims} dims): "
                     f"stored complete={_stored_complete}, missing={_stored_missing}; "
                     f"recomputed complete={_recomputed_complete}, missing={_recomputed_missing}[/yellow]")
        elif _comp_mode == "verified" and not _stored_comp:
            result["completeness_trust_status"] = "verified_no_claim"
            result["completeness_drift_severity"] = "none"
        elif _comp_mode == "claim_only" and _stored_comp:
            result["completeness_trust_status"] = "claim_only_unverified"
            result["completeness_drift_severity"] = "none"
        elif _comp_mode == "claim_only":
            result["completeness_trust_status"] = "claim_only_no_claim"
            result["completeness_drift_severity"] = "none"
        else:
            result["completeness_trust_status"] = "no_completeness"
            result["completeness_drift_severity"] = "none"

        # A50: Policy-adjusted completeness outcome
        if _comp_mode == "verified" and _comp_verified:
            result["policy_completeness_pass"] = True
            result["completeness_policy_action"] = "pass"
        elif _comp_mode == "verified" and not _comp_verified and _comp_strict:
            result["policy_completeness_pass"] = False
            result["completeness_policy_action"] = "block"
            _msg("[red]COMPLETENESS STRICT: verification failed[/red]")
        elif _comp_mode == "verified" and not _comp_verified:
            # A50->A51: Non-strict = structured warning, raw results immutable
            result["policy_completeness_pass"] = True  # policy-adjusted: pass with warning
            result["completeness_policy_action"] = "warn"
            result["completeness_warning"] = True
            # A55: Structured waiver record with check_index binding
            _comp_check = next(
                (c for c in result["checks"]
                 if c["check"] in ("completeness_reverified", "completeness_claim_present")
                 and not c["passed"]), None)
            _cidx = _comp_check.get("index", -1) if _comp_check else -1
            _existing_idx = [w for w in result["policy_waivers"]
                             if w.get("check_index") == _cidx and _cidx >= 0]
            if not _existing_idx:
                result["policy_waivers"].append(_build_waiver_record(
                    check_name="completeness_reverified",
                    check_index=_cidx,
                    original_detail=_comp_check.get("detail", "") if _comp_check else "",
                    policy_field="completeness_strict",
                    reason="completeness_strict=False (non-strict warning)",
                    severity="warning",
                    command="verify",
                    policy_data=_policy_data if _policy_data else None,
                    adjusted_detail="completeness downgraded to warning by policy",
                    check_entry=_comp_check,
                ))
            # A51: Do NOT mutate result["failed"] -- keep raw checks immutable
            _msg("[yellow]Completeness: non-strict failure (structured warning)[/yellow]")
        else:
            # claim_only, error, unknown
            result["policy_completeness_pass"] = None
            result["completeness_policy_action"] = "pass"  # no action for non-verified modes

        # A51: Missing-file hash comparison in drift detection
        if _comp_mode == "verified" and _stored_comp:
            _stored_mfb = _stored_comp.get("missing_from_bundle", [])
            _recomputed_mfb = _comp_report.get("missing_from_bundle", [])
            # Extract path_hash sets for comparison
            _stored_hashes = set()
            if isinstance(_stored_mfb, list):
                for _item in _stored_mfb:
                    if isinstance(_item, dict):
                        _stored_hashes.add(_item.get("path_hash", ""))
                    elif isinstance(_item, str):
                        _stored_hashes.add(_item)
            _recomputed_hashes = set()
            if isinstance(_recomputed_mfb, list):
                for _item in _recomputed_mfb:
                    if isinstance(_item, dict):
                        _recomputed_hashes.add(_item.get("path_hash", ""))
                    elif isinstance(_item, str):
                        _recomputed_hashes.add(_item)
            _hash_match = _stored_hashes == _recomputed_hashes
            result["completeness_missing_hashes_match"] = _hash_match
            if not _hash_match and result.get("completeness_drift_severity") == "none":
                # A52: Hash mismatch upgrades drift and trust_status for consistency
                result["completeness_drift_severity"] = "low"
                result["completeness_drift_dims"] = max(result.get("completeness_drift_dims", 0), 1)
                if result.get("completeness_trust_status") == "verified_matched":
                    result["completeness_trust_status"] = "verified_drift"

        # A51: Policy severity definitions for trust statuses
        _trust_status = result.get("completeness_trust_status", "no_completeness")
        if _trust_status == "verified_matched":
            result["completeness_policy_severity"] = "none"
        elif _trust_status == "verified_drift":
            _ds = result.get("completeness_drift_severity", "none")
            if _ds == "high":
                result["completeness_policy_severity"] = "warning" if not _comp_strict else "block"
            else:
                result["completeness_policy_severity"] = "info"
        elif _trust_status == "verified_no_claim":
            result["completeness_policy_severity"] = "info"
        elif _trust_status in ("claim_only_unverified", "claim_only_no_claim"):
            result["completeness_policy_severity"] = "info"
        else:
            result["completeness_policy_severity"] = "none"

    # A56: Verify waiver integrity before verdict (hash binding validation)
    _verify_waiver_integrity(result)
    # A56: Policy-adjusted verdict from adjusted-check map (only valid waivers count)
    result["raw_verdict"] = "passed" if result["failed"] == 0 else "failed"
    _waivers = result.get("policy_waivers", [])
    _valid_ids = result.pop("_valid_waiver_ids", set())
    # A56: Build adjusted-check map -- only integrity-validated waivers adjust verdict
    _adjusted_checks = {}  # {check_index: waiver_record}
    for w in _waivers:
        if w.get("waiver_id", "") in _valid_ids:
            _ci = w.get("check_index", -1)
            if _ci >= 0 and _ci not in _adjusted_checks:
                _adjusted_checks[_ci] = w
    _policy_failed = max(0, result["failed"] - len(_adjusted_checks))
    result["policy_verdict"] = "passed" if _policy_failed == 0 else "failed"
    result["verdict"] = result["policy_verdict"]
    result["policy_waived_checks"] = [w["check"] for w in _waivers if w.get("waiver_id", "") in _valid_ids]
    # A56: Expose adjusted-check summary for audit
    result["adjusted_check_count"] = len(_adjusted_checks)

    # A48: trust_summary with completeness awareness
    _verdict_ok = result["verdict"] == "passed"
    _tl = result.get("trust_level", "unknown")
    _cv = result.get("completeness_verdict", "")
    if _verdict_ok and _tl == "signed_trusted":
        _ts = "verified_signed_trusted"
    elif _verdict_ok and _tl in ("unsigned_valid", "unknown"):
        _ts = "verified_unsigned"
    elif not _verdict_ok and _tl in ("signed_unverified", "signed_trusted"):
        _ts = "failed_signed"
    elif not _verdict_ok:
        _ts = "failed_unsigned"
    else:
        _ts = "unknown"
    # A48: Append completeness suffix to trust_summary
    if _cv == "verified":
        _ts += "_complete"
    elif _cv == "verified_failed":
        _ts += "_incomplete"
    elif _cv == "claim_only":
        _ts += "_claim_only"
    result["trust_summary"] = _ts

    # A52: Raw trust summary (based on raw_verdict, before policy adjustment)
    _raw_ok = result.get("raw_verdict", result["verdict"]) == "passed"
    if _raw_ok and _tl == "signed_trusted":
        _raw_ts = "verified_signed_trusted"
    elif _raw_ok and _tl in ("unsigned_valid", "unknown"):
        _raw_ts = "verified_unsigned"
    elif not _raw_ok and _tl in ("signed_unverified", "signed_trusted"):
        _raw_ts = "failed_signed"
    elif not _raw_ok:
        _raw_ts = "failed_unsigned"
    else:
        _raw_ts = "unknown"
    result["raw_trust_summary"] = _raw_ts

    _msg(f"\n[bold]Verdict: {result['verdict'].upper()}[/bold] "
         f"({result['passed']} passed, {result['failed']} failed) "
         f"\\[{result['trust_summary']}]")

    if as_json:
        _emit_json(result)

    if _policy_failed > 0:
        raise typer.Exit(1)


@paper_app.command("verify-chain")
def paper_verify_chain(
    log_path: str = typer.Option(..., "--log", "-l", help="Path to anchor log JSONL file"),
    zip_dir: Optional[str] = typer.Option(None, "--zip-dir", "-z",
                                           help="Directory to cross-verify zip_sha256 against actual ZIPs (A32)"),
    strict_chain: bool = typer.Option(False, "--strict-chain",
                                      help="Fail on chain_partial (no ZIPs verified) (A34)"),
    policy_file: str = typer.Option("", "--policy", help="Path to audit policy file (A37)"),
    expected_policy_hash: str = typer.Option("", "--expected-policy-hash",
                                              help="Expected SHA-256 hash of the policy file (A41)"),
    strict_policy: bool = typer.Option(False, "--strict-policy",
                                        help="Escalate schema warnings to blocking failures (A44)"),
    completeness_check: bool = typer.Option(False, "--completeness-check",
                                             help="Verify completeness claims from anchor log entries (A46)"),
    run_dir: Optional[str] = typer.Option(None, "--run-dir",
                                           help="Run directory for completeness re-verification (A46)"),
    as_json: bool = typer.Option(False, "--json", help="Print result as JSON (A32)"),
):
    """Verify anchor log chain integrity (A32->A34->A37).

    Checks:
    1. Log file exists and is readable
    2. Each line is valid JSON with required fields
    3. prev_hash chain is unbroken
    4. Optional: cross-verify zip_sha256 against actual ZIP files
    5. Timestamp monotonicity (A33)
    6. Duplicate bundle_id / zip_sha256 detection (A33)
    7. ISO-8601 UTC timestamp format (A34)
    8. Policy-based enforcement (A37)
    """
    init_env()
    _msg = err_console.print if as_json else console.print
    lp = Path(log_path)

    # A37: Load policy file and override CLI flags
    _policy_data: dict[str, Any] = {}
    _policy_warnings: list[str] = []
    if policy_file:
        _policy_data = _load_audit_policy(policy_file,
                                           expected_hash=expected_policy_hash,
                                           strict_policy=strict_policy)
        _prov = _policy_data.get("_policy_provenance", {})
        _msg(f"[green]Policy loaded[/green]: {_policy_data.get('description', 'unnamed')} "
             f"(schema={_policy_data.get('schema_version', '?')}, "
             f"hash={_prov.get('policy_sha256', '?')[:16]}...)")
        # Override strict_chain from policy
        if _policy_data.get("strict_chain") is not None:
            strict_chain = _policy_data["strict_chain"]

    result: dict[str, Any] = {
        "log_path": str(lp),
        "checks": [],
        "entries": 0,
        "passed": 0,
        "failed": 0,
        "verdict": "unknown",
        "policy_waivers": [],  # A53: Structured waiver trace records
    }

    def _check(name: str, ok: bool, detail: str = "") -> None:
        entry = {"check": name, "passed": ok,
                 "index": len(result["checks"])}  # A54: stable check index
        if detail:
            entry["detail"] = detail
        result["checks"].append(entry)
        if ok:
            result["passed"] += 1
            _msg(f"  [green]PASS[/green] {name}" + (f" -- {detail}" if detail else ""))
        else:
            result["failed"] += 1
            _msg(f"  [red]FAIL[/red] {name}" + (f" -- {detail}" if detail else ""))

    _msg(f"[bold]A33 Anchor Chain Verification: {lp.name}[/bold]")

    # Check 1: Log file exists
    if not lp.exists():
        _check("log_exists", False, f"{lp} not found")
        result["verdict"] = "failed"
        if as_json:
            _emit_json(result)
        raise typer.Exit(1)
    _check("log_exists", True)

    # Check 2: Parse all entries
    raw_lines = lp.read_text(encoding="utf-8").strip().split("\n")
    raw_lines = [l for l in raw_lines if l.strip()]
    entries: list[dict] = []
    parse_errors = 0
    for i, line in enumerate(raw_lines):
        try:
            entry = json.loads(line)
            # Validate required fields
            for field in ("timestamp", "bundle_id", "run_id", "zip_sha256"):
                if field not in entry:
                    parse_errors += 1
                    break
            else:
                entries.append(entry)
        except json.JSONDecodeError:
            parse_errors += 1

    result["entries"] = len(entries)
    _check("entries_parseable", parse_errors == 0,
           f"{len(entries)} ok, {parse_errors} errors")

    # A33: Check that log is not empty (entries_non_empty)
    _check("entries_non_empty", len(entries) > 0,
           f"{len(entries)} entries" if entries else "empty chain -- no entries to verify")

    # Check 3: prev_hash chain integrity
    chain_ok = True
    chain_breaks = 0
    for i in range(1, len(entries)):
        prev_line = raw_lines[i - 1]
        expected_prev = hashlib.sha256(prev_line.encode("utf-8")).hexdigest()
        actual_prev = entries[i].get("prev_hash", "")
        if expected_prev != actual_prev:
            chain_ok = False
            chain_breaks += 1

    first_empty = (entries[0].get("prev_hash", "") == "") if entries else True
    _check("chain_first_entry_empty", first_empty,
           "first entry prev_hash=''" if first_empty else "first entry has non-empty prev_hash")
    _check("chain_integrity", chain_ok,
           f"{len(entries) - 1} links, {chain_breaks} breaks" if entries
           else "0 links -- empty chain")

    # Check 4: Cross-verify zip_sha256 against actual ZIPs (optional)
    _zip_verified = 0  # A33: track for verification_mode
    if zip_dir:
        zd = Path(zip_dir)
        zip_ok_count = 0
        zip_fail_count = 0
        zip_skip_count = 0
        for entry in entries:
            bundle_id = entry.get("bundle_id", "")
            expected_hash = entry.get("zip_sha256", "")
            # Try to find the ZIP by bundle_id pattern
            candidates = list(zd.glob(f"audit-bundle-*{bundle_id[:8]}*.zip")) if bundle_id else []
            if not candidates:
                candidates = list(zd.glob("audit-bundle-*.zip"))
            found = False
            for zp in candidates:
                actual_hash = hashlib.sha256(zp.read_bytes()).hexdigest()
                if actual_hash == expected_hash:
                    zip_ok_count += 1
                    found = True
                    break
            if not found:
                if candidates:
                    zip_fail_count += 1
                else:
                    zip_skip_count += 1
        _zip_verified = zip_ok_count
        _check("zip_cross_verify", zip_fail_count == 0,
               f"{zip_ok_count} ok, {zip_fail_count} failed, {zip_skip_count} skipped")
        # A33: Warn when all entries were skipped (no ZIPs found at all)
        if zip_ok_count == 0 and zip_fail_count == 0 and zip_skip_count > 0:
            _check("zip_any_verified", False,
                   f"all {zip_skip_count} entries skipped -- no ZIP files found in {zd}")
        else:
            _check("zip_any_verified", True,
                   f"{zip_ok_count} verified" if zip_ok_count else "no entries verified")
    else:
        _check("zip_cross_verify", True, "skipped (no --zip-dir)")

    # A33: Timestamp monotonicity check
    if len(entries) >= 2:
        _ts_ok = True
        _ts_breaks = 0
        for i in range(1, len(entries)):
            _prev_ts = entries[i - 1].get("timestamp", "")
            _cur_ts = entries[i].get("timestamp", "")
            if _cur_ts < _prev_ts:
                _ts_ok = False
                _ts_breaks += 1
        _check("timestamp_monotonic", _ts_ok,
               f"{len(entries) - 1} comparisons, {_ts_breaks} regressions")
    elif entries:
        _check("timestamp_monotonic", True, "single entry -- trivially monotonic")
    else:
        _check("timestamp_monotonic", True, "no entries -- skipped")

    # A33: Duplicate detection (bundle_id + zip_sha256)
    if entries:
        _seen_bids: set[str] = set()
        _seen_hashes: set[str] = set()
        _dup_bids = 0
        _dup_hashes = 0
        for e in entries:
            _bid = e.get("bundle_id", "")
            _zh = e.get("zip_sha256", "")
            if _bid and _bid in _seen_bids:
                _dup_bids += 1
            _seen_bids.add(_bid)
            if _zh and _zh in _seen_hashes:
                _dup_hashes += 1
            _seen_hashes.add(_zh)
        _no_dups = (_dup_bids == 0 and _dup_hashes == 0)
        _check("no_duplicates", _no_dups,
               f"{_dup_bids} duplicate bundle_ids, {_dup_hashes} duplicate zip_sha256"
               if not _no_dups else f"{len(entries)} unique entries")
    else:
        _check("no_duplicates", True, "no entries -- skipped")

    # A34->A35: ISO-8601 UTC timestamp validation (parser-based)
    if entries:
        _ts_invalid = 0
        _ts_details: list[str] = []
        for _idx, e in enumerate(entries):
            _ts_val = e.get("timestamp", "")
            try:
                _parsed = datetime.fromisoformat(_ts_val.replace("Z", "+00:00"))
                # Ensure timezone-aware
                if _parsed.tzinfo is None:
                    _ts_invalid += 1
                    _ts_details.append(f"entry[{_idx}] naive")
            except (ValueError, TypeError):
                _ts_invalid += 1
                _ts_details.append(f"entry[{_idx}] invalid")
        _check("timestamp_format_iso8601", _ts_invalid == 0,
               f"{len(entries) - _ts_invalid}/{len(entries)} valid ISO-8601 (parser-validated)"
               if _ts_invalid == 0
               else f"{_ts_invalid}/{len(entries)} invalid: {', '.join(_ts_details[:5])}")
    else:
        _check("timestamp_format_iso8601", True, "no entries -- skipped")

    # A33: verification_mode and trust_level
    if zip_dir and _zip_verified > 0:
        result["verification_mode"] = "chain_plus_zip"
        result["trust_level"] = "chain_valid_zip_verified"
    elif zip_dir:
        result["verification_mode"] = "chain_partial"
        result["trust_level"] = "chain_valid_zip_unverified"
    else:
        result["verification_mode"] = "chain_only"
        result["trust_level"] = "chain_valid"

    # A34: --strict-chain fails on chain_partial
    if strict_chain and result["verification_mode"] == "chain_partial":
        result["failed"] += 1
        result["checks"].append({
            "check": "strict_chain_policy",
            "passed": False,
            "detail": "chain_partial is not allowed under --strict-chain policy",
        })

    # A38: chain_verification_mode enforcement from policy
    if _policy_data:
        _p_cvm = _policy_data.get("chain_verification_mode", "chain_only")
        _actual_mode = result.get("verification_mode", "chain_only")
        # chain_plus_zip policy requires zip verification
        if _p_cvm == "chain_plus_zip" and _actual_mode != "chain_plus_zip":
            result["failed"] += 1
            result["checks"].append({
                "check": "policy_chain_mode",
                "passed": False,
                "detail": f"policy requires chain_plus_zip but got {_actual_mode}",
            })
        # chain_only policy rejects chain_partial
        elif _p_cvm == "chain_only" and _actual_mode == "chain_partial":
            result["failed"] += 1
            result["checks"].append({
                "check": "policy_chain_mode",
                "passed": False,
                "detail": f"policy requires chain_only but got chain_partial",
            })
        else:
            result["passed"] += 1
            result["checks"].append({
                "check": "policy_chain_mode",
                "passed": True,
                "detail": f"policy={_p_cvm}, actual={_actual_mode}",
            })

        # A38->A39: strict_timestamps enforcement
        _p_st = _policy_data.get("strict_timestamps", True)
        _ts_check = next((c for c in result["checks"]
                          if c["check"] == "timestamp_format_iso8601"), None)
        if _p_st:
            # strict_timestamps=True: annotate failures as policy-enforced
            if _ts_check and not _ts_check["passed"]:
                _ts_check["detail"] += " (policy: strict_timestamps)"
        else:
            # A54: strict_timestamps=False: waiver record only, check entry immutable
            if _ts_check and not _ts_check["passed"]:
                # A54: Do NOT mutate check entry -- raw check stays failed
                # A55: Duplicate prevention by check_index (not name)
                _existing_idx = [w for w in result["policy_waivers"]
                                 if w.get("check_index") == _ts_check.get("index", -1)]
                if not _existing_idx:
                    result["policy_waivers"].append(_build_waiver_record(
                        check_name="timestamp_format_iso8601",
                        check_index=_ts_check.get("index", -1),
                        original_detail=_ts_check.get("detail", ""),
                        policy_field="strict_timestamps",
                        reason="strict_timestamps=False",
                        severity="warning",
                        command="verify-chain",
                        policy_data=_policy_data,
                        adjusted_detail="timestamp downgraded to warning by policy",
                        check_entry=_ts_check,
                    ))
                # A40: Record as policy warning
                _policy_warnings.append({
                    "warning": "timestamp_downgraded",
                    "check": "timestamp_format_iso8601",
                    "reason": "strict_timestamps=False",
                })

        # A38: required_artifacts enforcement
        _p_ra = _policy_data.get("required_artifacts", [])
        if _p_ra:
            # Check if a state.json or evidence_manifest is available in the log dir
            _log_dir = lp.parent
            _missing_artifacts = []
            for _art in _p_ra:
                _art_path = _log_dir / _art
                # Try to find artifact in log dir or sibling dirs
                if not _art_path.exists():
                    # Also check for evidence_manifest reference
                    _state_path = _log_dir / "state.json"
                    _found_in_manifest = False
                    if _state_path.exists():
                        try:
                            _state = json.loads(_state_path.read_text(encoding="utf-8"))
                            _ev = _state.get("evidence_manifest", {})
                            _files = _ev.get("files", [])
                            for _f in _files:
                                if isinstance(_f, dict) and _f.get("path", "") == _art:
                                    _found_in_manifest = True
                                    break
                                elif isinstance(_f, str) and _f == _art:
                                    _found_in_manifest = True
                                    break
                        except (json.JSONDecodeError, ValueError):
                            pass
                    if not _found_in_manifest:
                        _missing_artifacts.append(_art)
            if _missing_artifacts:
                result["failed"] += 1
                result["checks"].append({
                    "check": "policy_required_artifacts",
                    "passed": False,
                    "detail": f"missing: {', '.join(_missing_artifacts)}",
                })
            else:
                result["passed"] += 1
                result["checks"].append({
                    "check": "policy_required_artifacts",
                    "passed": True,
                    "detail": f"all {len(_p_ra)} required artifacts found",
                })

    # A46: Completeness re-verification from anchor log entries
    if completeness_check and entries:
        _msg("\n[bold]A46 Completeness Re-verification[/bold]")
        _completeness_results: list[dict[str, Any]] = []
        _comp_strict = _policy_data.get("completeness_strict", False) if _policy_data else False

        for _ce_idx, _ce in enumerate(entries):
            _ce_entry: dict[str, Any] = {
                "bundle_id": _ce.get("bundle_id", ""),
                "index": _ce_idx,
                "verified": False,
            }
            # If run_dir provided, re-scan and verify
            if run_dir:
                _rd = Path(run_dir)
                if _rd.exists():
                    _rd_files: set[str] = set()
                    for _rp in _rd.rglob("*"):
                        if _rp.is_file():
                            _rd_files.add(str(_rp.relative_to(_rd)).replace("\\", "/"))
                    # Check that referenced ZIP exists
                    _zip_sha = _ce.get("zip_sha256", "")
                    _zip_found = False
                    for _zf in _rd.glob("*.zip"):
                        _actual_sha = hashlib.sha256(_zf.read_bytes()).hexdigest()
                        if _actual_sha == _zip_sha:
                            _zip_found = True
                            break
                    _ce_entry["zip_verified"] = _zip_found
                    _ce_entry["run_files_count"] = len(_rd_files)
                    _ce_entry["verified"] = _zip_found
                    _check(f"completeness_entry_{_ce_idx}_zip",
                           _zip_found,
                           f"bundle_id={_ce.get('bundle_id', '?')}")
                else:
                    _ce_entry["error"] = "run_dir not found"
                    _check(f"completeness_run_dir", False, f"{run_dir} not found")
            else:
                # A49: Without run_dir, mark as claim-only (NOT verified)
                _ce_entry["note"] = "no run_dir -- claim-only verification"
                _ce_entry["verified"] = False
                _ce_entry["claim_only"] = True

            _completeness_results.append(_ce_entry)

        result["completeness_reverification"] = _completeness_results
        _msg(f"  Re-verified {len(_completeness_results)} anchor entries")
        # A48: Compute completeness_verdict for verify-chain
        _all_verified = all(e.get("verified", False) for e in _completeness_results)
        _any_verified = any(e.get("verified", False) for e in _completeness_results)
        if run_dir and _all_verified:
            result["completeness_verdict"] = "verified"
        elif run_dir and _any_verified:
            result["completeness_verdict"] = "verified_partial"
        elif run_dir:
            result["completeness_verdict"] = "verified_failed"
        else:
            result["completeness_verdict"] = "claim_only"

    # A56: Verify waiver integrity before verdict (hash binding validation)
    _verify_waiver_integrity(result)
    # A56: Policy-adjusted verdict from adjusted-check map (only valid waivers count)
    _waivers = result.get("policy_waivers", [])
    _valid_ids = result.pop("_valid_waiver_ids", set())
    # A56: Build adjusted-check map -- only integrity-validated waivers adjust verdict
    _adjusted_checks = {}  # {check_index: waiver_record}
    for w in _waivers:
        if w.get("waiver_id", "") in _valid_ids:
            _ci = w.get("check_index", -1)
            if _ci >= 0 and _ci not in _adjusted_checks:
                _adjusted_checks[_ci] = w
    _raw_failed = result["failed"]
    _policy_failed = max(0, _raw_failed - len(_adjusted_checks))
    result["raw_verdict"] = "passed" if _raw_failed == 0 else "failed"
    result["policy_verdict"] = "passed" if _policy_failed == 0 else "failed"
    result["policy_waived_checks"] = [w["check"] for w in _waivers if w.get("waiver_id", "") in _valid_ids]
    result["adjusted_check_count"] = len(_adjusted_checks)
    result["verdict"] = result["policy_verdict"]
    if _policy_failed == 0 and result["entries"] == 0:
        result["trust_level"] = "chain_empty"
    elif _policy_failed > 0:
        result["trust_level"] = "chain_invalid"
    # A52: Raw trust summary for verify-chain
    _raw_ts = "chain_empty" if (_raw_failed == 0 and result["entries"] == 0) else (
        "chain_invalid" if _raw_failed > 0 else result.get("trust_level", "unknown"))
    result["raw_trust_summary"] = _raw_ts
    # A48: Append completeness suffix to verification_mode
    _vm = result.get("verification_mode", "unknown")
    _cv = result.get("completeness_verdict", "")
    if _cv == "verified":
        _vm += "_complete"
    elif _cv == "verified_partial":
        _vm += "_partial"
    elif _cv == "verified_failed":
        _vm += "_incomplete"
    elif _cv == "claim_only":
        _vm += "_claim_only"
    result["verification_mode"] = _vm
    _msg(f"\n[bold]Verdict: {result['verdict'].upper()}[/bold] "
         f"({result['passed']} passed, {result['failed']} failed) "
         f"\\[{result.get('verification_mode', 'unknown')}]")

    if as_json:
        # A37-A43: Include policy info in JSON output
        if _policy_data:
            _prov = _policy_data.get("_policy_provenance", {})
            result["policy_file_hash"] = _prov.get("policy_sha256", "")
            result["policy_schema_version"] = _policy_data.get("schema_version", "")
            _akids = _policy_data.get("allowed_key_ids", [])
            if _akids:
                result["allowed_key_ids"] = _akids
            result["policy_strict_chain"] = _policy_data.get("strict_chain", False)
            # A41: Include policy provenance
            result["policy_provenance"] = {
                "policy_sha256": _prov.get("policy_sha256", ""),
                "policy_path_hash": _prov.get("policy_path_hash", ""),
                "policy_loaded_at": _prov.get("policy_loaded_at", ""),
                "schema_validated": _prov.get("schema_validated", False),
                "schema_warnings": _prov.get("schema_warnings", 0),
            }
            # A40: Include policy warnings
            result["policy_warnings"] = _policy_warnings
        _emit_json(result)

    if _policy_failed > 0:
        raise typer.Exit(1)


@paper_app.command("checkpoint")
def paper_checkpoint(
    log_path: str = typer.Option(..., "--log", "-l", help="Path to anchor log JSONL file"),
    export: Optional[str] = typer.Option(None, "--export", "-e",
                                         help="Export chain head checkpoint to file (A34)"),
    verify_checkpoint: Optional[str] = typer.Option(None, "--verify", "-v",
                                                    help="Verify a checkpoint file against the log (A34)"),
    sign: bool = typer.Option(False, "--sign", help="Sign checkpoint with HMAC-SHA256 (A35)"),
    signature_policy: str = typer.Option("optional", "--signature-policy",
                                         help="Signature policy: required|optional|off (A36)"),
    expected_key_id: str = typer.Option("", "--expected-key-id",
                                        help="Expected signing key ID for policy check (A36)"),
    policy_file: str = typer.Option("", "--policy", help="Path to audit policy file (A37)"),
    expected_policy_hash: str = typer.Option("", "--expected-policy-hash",
                                              help="Expected SHA-256 hash of the policy file (A41)"),
    strict_policy: bool = typer.Option(False, "--strict-policy",
                                        help="Escalate schema warnings to blocking failures (A44)"),
    as_json: bool = typer.Option(False, "--json", help="Print result as JSON (A34)"),
):
    """Export or verify chain head checkpoint (A34->A35->A36->A44).

    A checkpoint captures the current chain head (last entry) and its
    cumulative hash so it can be pushed to external systems or compared
    against a previously exported checkpoint.

    A36: --signature-policy controls whether invalid/missing signatures
    are blocking (required), warning-only (optional), or skipped (off).

    A37: --policy loads a project audit policy file that overrides
    signature_policy, expected_key_id, and other settings.
    """
    init_env()
    _msg = err_console.print if as_json else console.print
    lp = Path(log_path)

    # A37->A44: Load policy file and override CLI flags
    _policy_data: dict[str, Any] = {}
    if policy_file:
        _policy_data = _load_audit_policy(policy_file, expected_hash=expected_policy_hash,
                                           strict_policy=strict_policy)
        _prov = _policy_data.get("_policy_provenance", {})
        _msg(f"[green]Policy loaded[/green]: {_policy_data.get('description', 'unnamed')} "
             f"(schema={_policy_data.get('schema_version', '?')}, "
             f"hash={_prov.get('policy_sha256', '?')[:16]}...)")
        # Override CLI flags from policy
        if "signature_policy" in _policy_data:
            signature_policy = _policy_data["signature_policy"]
        # Override expected_key_id: use first allowed_key_id if policy has list
        _akids = _policy_data.get("allowed_key_ids", [])
        if _akids and not expected_key_id:
            expected_key_id = _akids[0]

    # --- Verify mode ---
    if verify_checkpoint:
        cp_path = Path(verify_checkpoint)
        if not cp_path.exists():
            _msg(f"[red]Checkpoint file not found: {cp_path}[/red]")
            raise typer.Exit(1)
        if not lp.exists():
            _msg(f"[red]Anchor log not found: {lp}[/red]")
            raise typer.Exit(1)
        try:
            cp_data = json.loads(cp_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, ValueError) as _e:
            _msg(f"[red]Invalid checkpoint JSON: {_e}[/red]")
            raise typer.Exit(1)

        # A35->A36: Verify optional signature on checkpoint with policy enforcement
        _cp_sig = cp_data.get("signature", {})
        _cp_sig_algo = _cp_sig.get("algorithm", "none") if isinstance(_cp_sig, dict) else "none"
        _sig_valid = False
        _sig_status = "unsigned"  # A36: signature_status
        _key_id_match = None  # A36: key ID policy check

        if _cp_sig_algo == "HMAC-SHA256":
            import hmac as _hmac
            _key = os.environ.get("AIHUB_SIGNING_KEY", "")
            if _key:
                # Rebuild the unsigned payload and verify
                # A42: exclude policy_provenance from signature (loaded_at varies)
                _unsigned = {k: v for k, v in cp_data.items()
                             if k not in ("signature", "policy_provenance")}
                _payload = json.dumps(_unsigned, sort_keys=True, ensure_ascii=False).encode("utf-8")
                _expected = _hmac.new(_key.encode("utf-8"), _payload, hashlib.sha256).hexdigest()
                _sig_valid = (_expected == _cp_sig.get("signature", ""))
                _sig_status = "signed_valid" if _sig_valid else "signed_invalid"
            else:
                _sig_status = "signed_unverified"  # A36: signed but key unavailable
            _msg(f"  Signature: {'[green]VALID[/green]' if _sig_valid else '[red]INVALID[/red]'} "
                 f"(algorithm={_cp_sig_algo}, key={'set' if _key else 'not set'})")

            # A36->A37: Key ID policy check (supports multiple allowed_key_ids)
            _allowed_kids = _policy_data.get("allowed_key_ids", []) if _policy_data else []
            if expected_key_id or _allowed_kids:
                _cp_key_id = _cp_sig.get("key_id", "")
                # Build check set: CLI expected_key_id + policy allowed_key_ids
                _check_kids: list[str] = []
                if expected_key_id:
                    _check_kids.append(expected_key_id)
                for _kid in _allowed_kids:
                    if _kid not in _check_kids:
                        _check_kids.append(_kid)
                _key_id_match = (_cp_key_id in _check_kids) if _check_kids else None
                _msg(f"  Key ID: {'[green]MATCH[/green]' if _key_id_match else '[red]MISMATCH[/red]'}"
                     f" (allowed={_check_kids}, actual={_cp_key_id or 'none'})")
        elif _cp_sig_algo == "none":
            _sig_status = "unsigned"  # A36
            _msg("  Signature: none (unsigned checkpoint)")

        # A36: Apply signature policy
        _sig_policy = signature_policy.lower()
        _sig_policy_fail = False
        if _sig_policy == "required":
            if _sig_status == "unsigned":
                _sig_status = "signature_required_missing"
                _sig_policy_fail = True
                _msg("[red]Signature policy REQUIRED: checkpoint is unsigned[/red]")
            elif _sig_status == "signed_invalid":
                _sig_policy_fail = True
                _msg("[red]Signature policy REQUIRED: signature is INVALID[/red]")
            elif _sig_status == "signed_unverified":
                _sig_policy_fail = True
                _msg("[red]Signature policy REQUIRED: cannot verify (key unavailable)[/red]")
            if expected_key_id and _key_id_match is False:
                _sig_policy_fail = True
                _msg("[red]Signature policy REQUIRED: key ID mismatch[/red]")
        elif _sig_policy == "optional":
            if _sig_status == "signed_invalid":
                _msg("[yellow]Warning: signature invalid (policy=optional)[/yellow]")
            elif _sig_status == "unsigned":
                _msg("[yellow]Warning: checkpoint unsigned (policy=optional)[/yellow]")
            elif _sig_status == "signed_unverified":
                _msg("[yellow]Warning: signature unverifiable (policy=optional)[/yellow]")
            if expected_key_id and _key_id_match is False:
                _msg("[yellow]Warning: key ID mismatch (policy=optional)[/yellow]")
        # else: off -- skip all signature checks

        # Read current log
        raw = lp.read_text(encoding="utf-8").strip().split("\n")
        raw = [l for l in raw if l.strip()]
        if not raw:
            _msg("[red]Anchor log is empty[/red]")
            raise typer.Exit(1)

        current_head_line = raw[-1]
        current_head_hash = hashlib.sha256(current_head_line.encode("utf-8")).hexdigest()
        current_entry_count = len(raw)
        # A35: Compute chain_full_hash for verification
        _chain_concat = "".join(raw)
        _current_chain_hash = hashlib.sha256(_chain_concat.encode("utf-8")).hexdigest()

        cp_head_hash = cp_data.get("chain_head_hash", "")
        cp_entry_count = cp_data.get("entries_count", 0)
        cp_chain_hash = cp_data.get("chain_full_hash", "")

        # A35: Independent checks
        _head_match = (current_head_hash == cp_head_hash)
        _chain_match = (_current_chain_hash == cp_chain_hash) if cp_chain_hash else True
        _entries_match = (current_entry_count == cp_entry_count) if cp_entry_count else True

        _all_ok = _head_match and _chain_match and _entries_match and not _sig_policy_fail
        _msg(f"[bold]Checkpoint Verification (A36)[/bold]")
        _msg(f"  Checkpoint entries: {cp_entry_count}, Log entries: {current_entry_count}"
             f" -- {'[green]MATCH[/green]' if _entries_match else '[red]MISMATCH[/red]'}")
        _msg(f"  Head hash: {'[green]PASS[/green]' if _head_match else '[red]FAIL[/red]'}")
        _msg(f"  Chain hash: {'[green]PASS[/green]' if _chain_match else '[red]FAIL[/red]'}")
        _msg(f"  Signature policy: {_sig_policy} | status: {_sig_status}"
             f" | policy_pass: {'[green]YES[/green]' if not _sig_policy_fail else '[red]NO[/red]'}")

        if as_json:
            result = {
                "checkpoint_file": str(cp_path),
                "log_path": str(lp),
                "head_hash_match": _head_match,
                "chain_full_hash_match": _chain_match,
                "entries_count_match": _entries_match,
                "signature_valid": _sig_valid if _cp_sig_algo != "none" else None,
                "signature_policy": _sig_policy,
                "signature_status": _sig_status,
                "signature_policy_pass": not _sig_policy_fail,
                "checkpoint_hash": cp_head_hash,
                "current_hash": current_head_hash,
                "checkpoint_chain_hash": cp_chain_hash,
                "current_chain_hash": _current_chain_hash,
                "checkpoint_entries": cp_entry_count,
                "current_entries": current_entry_count,
                "verdict": "passed" if _all_ok else "failed",
            }
            # A36->A37: key ID info
            if expected_key_id:
                result["expected_key_id"] = expected_key_id
                result["key_id_match"] = _key_id_match
            # A37->A43: policy info with provenance (redacted path)
            if _policy_data:
                result["policy_file_hash"] = _policy_data.get("_policy_provenance", {}).get("policy_path_hash", "")
                result["policy_schema_version"] = _policy_data.get("schema_version", "")
                _akids = _policy_data.get("allowed_key_ids", [])
                if _akids:
                    result["allowed_key_ids"] = _akids
                result["policy_provenance"] = _policy_data.get("_policy_provenance", {})
            _emit_json(result)
        if not _all_ok:
            raise typer.Exit(1)
        return

    # --- Export mode ---
    if not lp.exists():
        _msg(f"[red]Anchor log not found: {lp}[/red]")
        raise typer.Exit(1)

    raw = lp.read_text(encoding="utf-8").strip().split("\n")
    raw = [l for l in raw if l.strip()]
    if not raw:
        _msg("[red]Anchor log is empty -- nothing to checkpoint[/red]")
        raise typer.Exit(1)

    head_line = raw[-1]
    head_hash = hashlib.sha256(head_line.encode("utf-8")).hexdigest()

    # Compute cumulative chain hash (hash of all lines concatenated)
    chain_concat = "".join(raw)
    chain_hash = hashlib.sha256(chain_concat.encode("utf-8")).hexdigest()

    try:
        head_entry = json.loads(head_line)
    except json.JSONDecodeError:
        head_entry = {}

    checkpoint = {
        "format_version": "1.1",
        "chain_head_hash": head_hash,
        "chain_full_hash": chain_hash,
        "entries_count": len(raw),
        "head_timestamp": head_entry.get("timestamp", ""),
        "head_bundle_id": head_entry.get("bundle_id", ""),
        "head_run_id": head_entry.get("run_id", ""),
        "exported_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }

    # A35: Optional signing
    if sign:
        _sign_result = _sign_record(checkpoint)
        checkpoint["signature"] = _sign_result
        if _sign_result.get("algorithm") != "none":
            _msg(f"[green]Checkpoint signed[/green] (algorithm={_sign_result['algorithm']})")

    # A42: include policy provenance in checkpoint BEFORE export
    if _policy_data and "_policy_provenance" in _policy_data:
        checkpoint["policy_provenance"] = _policy_data["_policy_provenance"]

    if export:
        out_path = Path(export)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(checkpoint, indent=2, ensure_ascii=False),
                            encoding="utf-8")
        _msg(f"[green]Checkpoint exported to {out_path}[/green]")
        _msg(f"  Entries: {len(raw)}")
        _msg(f"  Head hash: {head_hash}")
        _msg(f"  Chain hash: {chain_hash}")
    else:
        _msg("[bold]Current Chain Head Checkpoint:[/bold]")
        _msg(f"  Entries: {len(raw)}")
        _msg(f"  Head hash: {head_hash}")
        _msg(f"  Chain hash: {chain_hash}")
        _msg(f"  Head timestamp: {head_entry.get('timestamp', 'N/A')}")
        _msg(f"  Head bundle_id: {head_entry.get('bundle_id', 'N/A')}")

    if as_json:
        _emit_json(checkpoint)


@paper_app.command("policy-schema")
def paper_policy_schema(
    output: Optional[str] = typer.Option(None, "--output", "-o",
                                          help="Write schema to file instead of stdout (A42)"),
):
    """Export the audit policy JSON Schema for external tool validation (A42).

    The schema can be used by external JSON Schema validators (e.g., ajv,
    jsonschema, check-jsonschema) to validate policy files independently.
    """
    schema_json = json.dumps(_AUDIT_POLICY_JSON_SCHEMA, indent=2, ensure_ascii=False)
    if output:
        out_path = Path(output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(schema_json, encoding="utf-8")
        console.print(f"[green]Policy schema exported to {out_path}[/green]")
    else:
        console.print(schema_json, markup=False, highlight=False)


def _render_cli_backend_calls(bc: dict) -> str:
    if not bc:
        return "No backend calls recorded."
    lines = ["| Node | Backend | Model | Exit Code |", "|------|---------|-------|-----------|"]
    for node, info in bc.items():
        if isinstance(info, dict):
            lines.append(f"| {node} | {info.get('backend', '?')} | {info.get('model', '?')} | {info.get('exit_code', '?')} |")
    return "\n".join(lines)

def main():
    app()

if __name__ == "__main__":
    main()
