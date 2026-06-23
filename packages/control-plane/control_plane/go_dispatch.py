"""User-facing /go coding-agent dispatch for DevFrame."""
from __future__ import annotations

import json
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .backup_guard import default_runtime_dir
from .orchestrator import Orchestrator
from .rdgoal import rdgoal
from .worker import CommandWorker, WorkerResult


DEFAULT_GO_MODEL = "stepfun/step-3.7-flash"
DEFAULT_OPENCODE_AGENT = "build"


@dataclass
class GoAgentDispatch:
    agent_id: str
    shard_index: int
    shard_count: int
    targets: list[str]
    target_bytes: int
    packet_dir: str
    task_spec_path: str
    worker_command: list[str]
    status: str = "queued"
    report_path: str = ""
    worker_status: str = ""
    changed_files: list[str] = field(default_factory=list)
    verification: str = ""


@dataclass
class GoDispatchResult:
    go_run_id: str
    project_id: str
    project_root: str
    requirement: str
    runtime_dir: str
    status: str
    execute: bool
    agents: list[GoAgentDispatch] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    metadata_path: str = ""


def run_go_dispatch(
    project_path: str | Path,
    requirement: str,
    *,
    runtime_dir: str | Path | None = None,
    agents: int = 2,
    targets: list[str] | None = None,
    execute: bool = False,
    worker_command: list[str] | None = None,
    model: str = DEFAULT_GO_MODEL,
    opencode_agent: str = DEFAULT_OPENCODE_AGENT,
    timeout_seconds: int = 900,
    apply_rdinit: bool = False,
) -> GoDispatchResult:
    """Create N rdgoal packets and optionally execute their workers in parallel."""

    if agents < 1:
        raise ValueError("agents must be >= 1")
    if agents > 16:
        raise ValueError("agents must be <= 16")

    runtime_root = Path(runtime_dir).resolve() if runtime_dir else default_runtime_dir()
    project_root = Path(project_path).resolve()
    target_shards = split_targets_by_size(project_root, targets or [], agents)
    orchestrator = Orchestrator(runtime_dir=runtime_root)
    dispatches: list[GoAgentDispatch] = []
    project_id = ""

    for index in range(agents):
        shard_targets = target_shards[index]
        shard_bytes = sum(
            estimate_target_bytes(project_root, target)
            for target in shard_targets
        )
        shard_number = index + 1
        shard_requirement = _shard_requirement(requirement, shard_number, agents, shard_targets)
        result = rdgoal(
            orchestrator,
            project_root,
            shard_requirement,
            operation=f"go coding shard {shard_number}/{agents}",
            targets=shard_targets,
            apply_rdinit=apply_rdinit,
        )
        project_id = result.project_id
        packet = result.dispatch.packet
        if packet is None:
            continue
        command = build_go_worker_command(
            worker_command=worker_command,
            model=model,
            opencode_agent=opencode_agent,
            shard_number=shard_number,
            shard_count=agents,
        )
        dispatches.append(GoAgentDispatch(
            agent_id=f"coding-agent-{shard_number}",
            shard_index=shard_number,
            shard_count=agents,
            targets=shard_targets,
            target_bytes=shard_bytes,
            packet_dir=packet.packet_dir,
            task_spec_path=str(Path(packet.packet_dir) / "TASKSPEC.json"),
            worker_command=command,
        ))

    go_run_id = f"go-{project_id or project_root.name}-{int(time.time() * 1000)}-{uuid.uuid4().hex[:6]}"
    result = GoDispatchResult(
        go_run_id=go_run_id,
        project_id=project_id,
        project_root=str(project_root),
        requirement=requirement,
        runtime_dir=str(runtime_root),
        status="queued",
        execute=execute,
        agents=dispatches,
    )

    if execute and dispatches:
        _execute_parallel(result, timeout_seconds=timeout_seconds)

    if not execute:
        result.status = "queued"
    elif all(agent.worker_status in {"pass", "passed", "completed"} for agent in result.agents):
        result.status = "passed"
    elif any(agent.worker_status in {"failed", "fail", "blocked"} for agent in result.agents):
        result.status = "failed"
    else:
        result.status = "blocked"

    result.metadata_path = str(_write_metadata(result))
    return result


def render_go_dispatch_text(result: GoDispatchResult) -> str:
    lines = [
        f"go_run_id    : {result.go_run_id}",
        f"project_id   : {result.project_id}",
        f"project_root : {result.project_root}",
        f"runtime_dir  : {result.runtime_dir}",
        f"status       : {result.status}",
        f"execute      : {result.execute}",
        f"agents       : {len(result.agents)}",
        f"metadata     : {result.metadata_path}",
        "",
        "Agents",
    ]
    for agent in result.agents:
        lines.extend([
            f"- {agent.agent_id} shard={agent.shard_index}/{agent.shard_count} status={agent.status}",
            f"  bytes  : {agent.target_bytes}",
            f"  packet : {agent.packet_dir}",
            f"  task   : {agent.task_spec_path}",
            f"  targets: {', '.join(agent.targets) if agent.targets else '(project scope)'}",
            f"  run    : {_worker_command_preview(result.runtime_dir, agent)}",
        ])
        if agent.report_path:
            lines.append(f"  report : {agent.report_path}")
        if agent.changed_files:
            lines.append(f"  changed: {', '.join(agent.changed_files)}")
        if agent.verification:
            lines.append(f"  evidence: {_summary_line(agent.verification)}")
    lines.extend([
        "",
        f"Dashboard: devframe dashboard serve --runtime-dir {_quote_arg(result.runtime_dir)}",
        f"Actions  : devframe actions --runtime-dir {_quote_arg(result.runtime_dir)}",
    ])
    return "\n".join(lines) + "\n"


def _execute_parallel(result: GoDispatchResult, *, timeout_seconds: int) -> None:
    max_workers = max(1, len(result.agents))
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {
            pool.submit(_run_one_agent, result.runtime_dir, agent, timeout_seconds): agent
            for agent in result.agents
        }
        for future in as_completed(futures):
            agent = futures[future]
            try:
                worker_result = future.result()
                agent.status = "completed"
                agent.worker_status = worker_result.summary.status
                agent.report_path = worker_result.report_path
                agent.changed_files = worker_result.summary.changed_files
                agent.verification = worker_result.summary.verification
            except Exception as exc:  # pragma: no cover - defensive guard
                agent.status = "failed"
                agent.worker_status = "failed"
                agent.report_path = ""
                _write_agent_failure(agent, exc)


def _run_one_agent(runtime_dir: str, agent: GoAgentDispatch, timeout_seconds: int) -> WorkerResult:
    agent.status = "running"
    return CommandWorker(runtime_dir=runtime_dir, timeout_seconds=timeout_seconds).run_packet(
        agent.packet_dir,
        agent.worker_command,
    )


def _write_metadata(result: GoDispatchResult) -> Path:
    runtime_root = Path(result.runtime_dir)
    path = runtime_root / "go-runs" / result.go_run_id / "go-run.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(result), indent=2, ensure_ascii=True), encoding="utf-8")
    return path


def _write_agent_failure(agent: GoAgentDispatch, exc: Exception) -> None:
    path = Path(agent.packet_dir) / "go-agent-error.txt"
    path.write_text(f"{type(exc).__name__}: {exc}\n", encoding="utf-8")


def split_targets_by_size(project_root: str | Path, targets: list[str], agents: int) -> list[list[str]]:
    shards = [[] for _ in range(agents)]
    if not targets:
        return shards

    shard_sizes = [0 for _ in range(agents)]
    weighted_targets = [
        (target, _target_size(Path(project_root).resolve(), target), index)
        for index, target in enumerate(targets)
    ]
    for target, size, _index in sorted(weighted_targets, key=lambda item: (-item[1], item[2])):
        shard_index = min(range(agents), key=lambda index: (shard_sizes[index], len(shards[index]), index))
        shards[shard_index].append(target)
        shard_sizes[shard_index] += size
    return shards


def estimate_target_bytes(project_root: str | Path, target: str) -> int:
    return _target_size(Path(project_root).resolve(), target)


def _target_size(project_root: Path, target: str) -> int:
    path = (project_root / target).resolve()
    try:
        path.relative_to(project_root)
    except ValueError:
        return 0
    if path.is_file():
        return _file_size(path)
    if path.is_dir():
        return sum(_file_size(child) for child in _iter_target_files(path))
    return 0


def _iter_target_files(path: Path):
    for child in path.rglob("*"):
        if ".git" in child.parts:
            continue
        if child.is_file():
            yield child


def _file_size(path: Path) -> int:
    try:
        return path.stat().st_size
    except OSError:
        return 0


def _shard_requirement(requirement: str, shard_number: int, shard_count: int,
                       targets: list[str]) -> str:
    lines = [
        requirement,
        "",
        f"Shard: {shard_number}/{shard_count}",
        "Role: coding execution agent. Implement only the assigned slice, collect verification, and write ExecutionReport.",
    ]
    if targets:
        lines.extend(["Assigned targets:", *[f"- {target}" for target in targets]])
    else:
        lines.append("Assigned targets: project-level discovery and the smallest safe implementation slice.")
    return "\n".join(lines)


def _opencode_command(*, model: str, opencode_agent: str,
                      shard_number: int, shard_count: int) -> list[str]:
    prompt = (
        "Read RDGOAL_TASKSPEC_JSON and RDGOAL_TASKSPEC_MD from the environment. "
        f"You are coding shard {shard_number}/{shard_count}. "
        "Make only the smallest safe project change for this shard, run the relevant verification, "
        "and write a Markdown ExecutionReport to RDGOAL_REPORT_PATH with Status, Changed Files, Evidence, Risks, and Reviewer Index."
    )
    return [
        "opencode",
        "run",
        "-m",
        model,
        "--agent",
        opencode_agent,
        "--format",
        "default",
        prompt,
    ]


def build_go_worker_command(
    *,
    worker_command: list[str] | None,
    model: str,
    opencode_agent: str,
    shard_number: int,
    shard_count: int,
) -> list[str]:
    if worker_command:
        return list(worker_command)
    return _opencode_command(
        model=model,
        opencode_agent=opencode_agent,
        shard_number=shard_number,
        shard_count=shard_count,
    )


def _worker_command_preview(runtime_dir: str, agent: GoAgentDispatch) -> str:
    command = render_command(agent.worker_command)
    return (
        f"rdgoal worker {_quote_arg(agent.packet_dir)} "
        f"--runtime-dir {_quote_arg(runtime_dir)} --command {command}"
    )


def render_command(command: list[str]) -> str:
    return " ".join(_quote_arg(part) for part in command)


def _summary_line(value: str) -> str:
    for line in value.splitlines():
        stripped = line.strip().lstrip("- ").replace("**", "")
        if stripped:
            return stripped
    return ""


def _quote_arg(value: str) -> str:
    text = str(value)
    if not text or any(ch.isspace() for ch in text) or any(ch in text for ch in ['"', "'", "&", "|"]):
        return '"' + text.replace('"', '\\"') + '"'
    return text
