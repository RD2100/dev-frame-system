"""User-facing /go coding-agent dispatch for DevFrame."""
from __future__ import annotations

import hashlib
import json
import sys
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .backup_guard import default_runtime_dir, is_inside
from .execution_plan import plan_write_set_groups
from .dispatch_packet import DispatchPacketStore
from .methodology_dispatch import resolve_methodology, resolve_workflow_profile
from .project_contract import slugify_project_id
from .model_providers import ModelProvider, resolve_model_provider
from .opencode_events import parse_opencode_run_jsonl
from .orchestrator import Orchestrator
from .provider_secret import (
    PROVIDER_SECRET_ENV_NAMES,
    ProviderSecretAttestation,
    ProviderSecretError,
    redact_provider_secret_text,
    resolve_provider_secret,
)
from .rdgoal import rdgoal
from .team_runtime import TeamRuntime
from .worker import CommandWorker, WorkerResult
from .worktree import create_worktree


DEFAULT_GO_MODEL = "stepfun/step-3.7-flash"
DEFAULT_OPENCODE_AGENT = "build"
DEFAULT_GO_WORKER = "opencode"
GO_WORKERS = ("opencode",)
SUCCESS_WORKER_STATUSES = {"pass", "passed", "completed"}
TEAM_MESSAGE_SIDECAR = "team-message.json"
_TEAM_MESSAGE_KINDS = {"handoff", "note", "review-request"}
_MAX_TEAM_MESSAGE_SUMMARY_CHARS = 500


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
    methodology: dict[str, Any] | None = None
    session_id: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    cost: float = 0.0
    tool_calls: list[dict[str, str]] = field(default_factory=list)
    model_provider: str = ""
    isolated: bool = False
    worktree_path: str = ""
    context_packet_path: str = ""
    context_ledger_path: str = ""


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
    methodology: dict[str, Any] | None = None
    model_provider: str = ""
    driver: str = "command"
    toolchain: dict[str, str] | None = None
    workflow_profile: dict[str, Any] | None = None


def _resolve_model_provider_safe(provider_id: object) -> ModelProvider:
    try:
        return resolve_model_provider(provider_id)  # type: ignore[arg-type]
    except Exception:  # noqa: BLE001 - normalize all external selection errors
        resolve_provider_secret(provider_id)
        raise AssertionError("provider resolution unexpectedly succeeded")


def _attest_provider_execution(
    provider_id: str,
    *,
    driver: str,
) -> ProviderSecretAttestation:
    attestation = resolve_provider_secret(provider_id)
    if driver != "command" and attestation.required:
        raise ProviderSecretError(
            "unsupported_secret_boundary",
            provider_id=attestation.provider_id,
            reference=attestation.reference,
            detail="external provider secrets are supported only by the contained command worker",
        )
    return attestation


def _provider_secret_for_prepared_execution(
    result: GoDispatchResult,
) -> ProviderSecretAttestation | None:
    if not result.model_provider:
        return None
    provider = _resolve_model_provider_safe(result.model_provider)
    if provider.live_backend == "deferred":
        raise ValueError(
            f"model provider {provider.provider_id!r} has a deferred live backend; "
            "prepared execution is refused."
        )
    return _attest_provider_execution(
        provider.provider_id,
        driver=result.driver or "command",
    )


def run_go_dispatch(
    project_path: str | Path,
    requirement: str,
    *,
    runtime_dir: str | Path | None = None,
    agents: int = 2,
    targets: list[str] | None = None,
    execute: bool = False,
    worker_command: list[str] | None = None,
    worker: str = DEFAULT_GO_WORKER,
    model: str | None = None,
    model_provider: str | None = None,
    opencode_agent: str = DEFAULT_OPENCODE_AGENT,
    timeout_seconds: int = 900,
    apply_rdinit: bool = False,
    isolate: bool = False,
    driver: str = "command",
    acp_command: list[str] | None = None,
) -> GoDispatchResult:
    """Create N rdgoal packets and optionally execute their workers in parallel."""

    if agents < 1:
        raise ValueError("agents must be >= 1")
    if agents > 16:
        raise ValueError("agents must be <= 16")
    if driver not in {"command", "acp"}:
        raise ValueError(f"unknown driver: {driver!r} (expected 'command' or 'acp')")

    # An explicit custom command with no provider selection is provider-neutral.
    # Default OpenCode dispatch keeps the default provider. This distinction is
    # persisted so a prepared custom command does not later acquire a paid
    # provider contract that the caller never selected.
    custom_executor = worker_command is not None or (
        driver == "acp" and acp_command is not None
    )
    provider = (
        None
        if model_provider is None and custom_executor
        else _resolve_model_provider_safe(model_provider)
    )
    if execute and provider is not None and provider.live_backend == "deferred":
        raise ValueError(
            f"model provider {provider.provider_id!r} has a deferred live backend; "
            "preparing packets is allowed, but --execute is refused so the 'free' "
            "profile cannot silently run the paid default worker. Use a ready "
            "provider (opencode-api or local-ollama) to execute."
        )
    provider_secret = (
        _attest_provider_execution(provider.provider_id, driver=driver)
        if execute and provider is not None
        else None
    )
    effective_model = (
        model if model else ((provider.model or None) if provider else None)
    )
    provider_id = provider.provider_id if provider is not None else ""

    runtime_root = Path(runtime_dir).resolve() if runtime_dir else default_runtime_dir()
    project_root = Path(project_path).resolve()
    target_shards = split_targets_by_size(project_root, targets or [], agents)
    resolved_project_id = slugify_project_id(project_root)
    effective_requirement, methodology = resolve_methodology(
        requirement, runtime_dir=runtime_root, project_id=resolved_project_id
    )
    workflow_profile = resolve_workflow_profile(
        "coding",
        runtime_dir=runtime_root,
        project_id=resolved_project_id,
    )
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
        shard_requirement = _shard_requirement(effective_requirement, shard_number, agents, shard_targets, methodology)
        dispatch_result = rdgoal(
            orchestrator,
            project_root,
            shard_requirement,
            operation=f"go coding shard {shard_number}/{agents}",
            targets=shard_targets,
            apply_rdinit=apply_rdinit,
            work_type="coding",
            workflow_profile=workflow_profile,
        )
        project_id = dispatch_result.project_id
        packet = dispatch_result.dispatch.packet
        if packet is None:
            continue
        command = build_go_worker_command(
            worker_command=worker_command,
            worker=worker,
            model=effective_model,
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
            methodology=methodology,
            model_provider=provider_id,
            isolated=isolate,
            context_packet_path=packet.context_packet_path,
            context_ledger_path=packet.context_ledger_path,
        ))

    go_run_id = f"go-{project_id or project_root.name}-{int(time.time() * 1000)}-{uuid.uuid4().hex[:6]}"
    result = GoDispatchResult(
        go_run_id=go_run_id,
        project_id=project_id,
        project_root=str(project_root),
        requirement=effective_requirement,
        runtime_dir=str(runtime_root),
        status="queued",
        execute=execute,
        agents=dispatches,
        methodology=methodology,
        model_provider=provider_id,
        driver=driver,
        workflow_profile=workflow_profile,
    )

    if execute and dispatches:
        _execute_parallel(result, timeout_seconds=timeout_seconds, acp_command=acp_command,
                          provider_secret=provider_secret)

    if not execute:
        result.status = "queued"
    else:
        result.status = _result_status(result)

    result.metadata_path = str(_write_metadata(result))
    return result


def run_toolchain_dispatch(
    project_path: str | Path,
    manifest_path: str | Path,
    action: str,
    requirement: str,
    *,
    working_directory: str,
    expected_manifest_sha256: str,
    runtime_dir: str | Path,
    execute: bool,
    timeout_seconds: int = 900,
) -> GoDispatchResult:
    """Dispatch one manifest action through the existing command/team path."""
    if timeout_seconds < 1:
        raise ValueError("toolchain timeout must be at least 1 second")
    runtime_root = Path(runtime_dir).resolve()
    project_root = Path(project_path).resolve()
    if is_inside(runtime_root, project_root):
        raise ValueError("toolchain runtime directory must stay outside the project")
    workdir = (project_root / working_directory).resolve()
    if not project_root.is_dir() or not is_inside(workdir, project_root):
        raise ValueError("toolchain working directory must stay inside the project")
    if not workdir.is_dir():
        raise ValueError("toolchain working directory does not exist")

    orchestrator = Orchestrator(runtime_dir=runtime_root, repo_root=project_root)
    dispatch_result = rdgoal(
        orchestrator,
        project_root,
        requirement,
        operation=f"toolchain {action}",
        targets=[working_directory],
        contracts_dir=runtime_root / "contracts",
    )
    packet = dispatch_result.dispatch.packet
    if packet is None:
        raise ValueError("toolchain dispatch did not produce a task packet")

    manifest = Path(manifest_path).resolve()
    go_run_id = f"toolchain-{packet.project_id}-{int(time.time() * 1000)}-{uuid.uuid4().hex[:6]}"
    report_path = Path(packet.packet_dir) / "ExecutionReport.md"
    command = [
        sys.executable,
        "-m",
        "control_plane.toolchain_execution",
        "--manifest",
        str(manifest),
        "--action",
        action,
        "--project",
        str(project_root),
        "--expected-sha256",
        expected_manifest_sha256,
        "--timeout",
        str(timeout_seconds),
        "--report-path",
        str(report_path),
    ]
    agent = GoAgentDispatch(
        agent_id="toolchain-executor",
        shard_index=1,
        shard_count=1,
        targets=[working_directory],
        target_bytes=0,
        packet_dir=packet.packet_dir,
        task_spec_path=str(Path(packet.packet_dir) / "TASKSPEC.json"),
        worker_command=command,
        model_provider="",
    )
    result = GoDispatchResult(
        go_run_id=go_run_id,
        project_id=packet.project_id,
        project_root=str(project_root),
        requirement=requirement,
        runtime_dir=str(runtime_root),
        status="queued",
        execute=execute,
        agents=[agent],
        driver="command",
        toolchain={
            "action": action,
            "approved_manifest_sha256": expected_manifest_sha256,
            "manifest_path": str(manifest),
            "working_directory": str(workdir),
        },
    )
    if execute:
        _execute_parallel(result, timeout_seconds=timeout_seconds + 5)
        result.status = _result_status(result)
    result.metadata_path = str(_write_metadata(result))
    return result


def execute_go_run(
    runtime_dir: str | Path | None = None,
    run_id: str = "latest",
    *,
    timeout_seconds: int = 900,
    rerun_passed: bool = False,
) -> GoDispatchResult:
    """Execute a prepared go-run without creating new rdgoal packets."""

    runtime_root = Path(runtime_dir).resolve() if runtime_dir else default_runtime_dir()
    result = load_go_run_result(runtime_root, run_id)
    result.runtime_dir = str(runtime_root)
    runnable_agents = [
        agent
        for agent in result.agents
        if rerun_passed or agent.worker_status not in SUCCESS_WORKER_STATUSES
    ]
    provider_secret = (
        _provider_secret_for_prepared_execution(result) if runnable_agents else None
    )
    result.execute = True
    if runnable_agents:
        _execute_parallel(result, timeout_seconds=timeout_seconds, agents=runnable_agents,
                          provider_secret=provider_secret)
    result.status = _result_status(result)
    result.metadata_path = str(_write_metadata(result))
    return result


def load_go_run_result(runtime_dir: str | Path, run_id: str = "latest") -> GoDispatchResult:
    runtime_root = Path(runtime_dir).resolve()
    data = _read_go_run_metadata(_resolve_go_run_metadata_path(runtime_root, run_id))
    return _go_result_from_metadata(data, fallback_runtime_dir=runtime_root)


def load_go_run_result_snapshot(
    runtime_dir: str | Path,
    run_id: str = "latest",
) -> tuple[GoDispatchResult, str]:
    """Load one go run and return the hash of the exact parsed bytes."""
    from .run_index import _read_runtime_contained_bytes

    runtime_root = Path(runtime_dir).resolve()
    metadata_path = _resolve_go_run_metadata_path(runtime_root, run_id)
    raw, diagnostic = _read_runtime_contained_bytes(metadata_path, runtime_root)
    if raw is None:
        detail = f": {diagnostic}" if diagnostic else ""
        raise ValueError(f"go run metadata is unreadable: {metadata_path}{detail}")
    data = _parse_go_run_metadata_bytes(raw, metadata_path)
    result = _go_result_from_metadata(data, fallback_runtime_dir=runtime_root)
    return result, f"sha256:{hashlib.sha256(raw).hexdigest()}"


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
        f"requirement  : {result.requirement}",
    ]
    if result.methodology:
        title = str(result.methodology.get("title") or result.methodology.get("skill_id") or "unknown")
        lines.append(f"methodology   : {title}")
    if result.workflow_profile:
        profile_id = str(result.workflow_profile.get("profile_id") or "unknown")
        state = str(result.workflow_profile.get("execution_state") or "unknown")
        lines.append(f"workflow     : {profile_id} ({state})")
    lines.extend([
        "",
        "Agents",
    ])
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
        if agent.isolated and agent.worktree_path:
            lines.append(f"  worktree: {agent.worktree_path}")
        if agent.changed_files:
            lines.append(f"  changed: {', '.join(agent.changed_files)}")
        if agent.verification:
            lines.append(f"  evidence: {_summary_line(agent.verification)}")
    lines.extend([
        "",
        "Next",
        f"Inspect   : {_go_run_status_command(result)}",
        f"Resume    : {_go_run_execute_command(result)}",
        f"Control   : devframe dashboard serve --runtime-dir {_quote_arg(result.runtime_dir)}",
        f"Queue     : devframe actions --runtime-dir {_quote_arg(result.runtime_dir)}",
    ])
    return "\n".join(lines) + "\n"


def _go_run_status_command(result: GoDispatchResult) -> str:
    return (
        f"devframe code status {_quote_arg(result.go_run_id)} "
        f"--runtime-dir {_quote_arg(result.runtime_dir)}"
    )


def _go_run_execute_command(result: GoDispatchResult) -> str:
    return (
        f"devframe code execute {_quote_arg(result.go_run_id)} "
        f"--runtime-dir {_quote_arg(result.runtime_dir)}"
    )


def _execute_parallel(
    result: GoDispatchResult,
    *,
    timeout_seconds: int,
    agents: list[GoAgentDispatch] | None = None,
    acp_command: list[str] | None = None,
    provider_secret: ProviderSecretAttestation | None = None,
) -> None:
    agents_to_run = agents if agents is not None else result.agents
    if not agents_to_run:
        return
    # Executor-agnostic write-set isolation: agents whose targets overlap run
    # serially in one group; non-overlapping groups run in parallel. This makes
    # concurrent execution safe for any worker, not just OpenCode.
    group_indices = plan_write_set_groups([agent.targets for agent in agents_to_run])
    groups = [[agents_to_run[index] for index in indices] for indices in group_indices]
    max_workers = max(1, len(groups))
    # Real team runtime: record team events (Event Log + Message Bus) as durable
    # facts while agents actually run, instead of synthesizing them at read time.
    team = TeamRuntime(runtime_dir=result.runtime_dir)
    driver = result.driver or "command"
    participant_ids = {agent.agent_id for agent in result.agents}
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = [
            pool.submit(_run_group, result.runtime_dir, result.project_root, result.go_run_id,
                        group, timeout_seconds, team, driver, acp_command, participant_ids,
                        provider_secret)
            for group in groups
        ]
        for future in as_completed(futures):
            future.result()


def _run_group(runtime_dir: str, project_root: str, go_run_id: str,
               group: list[GoAgentDispatch], timeout_seconds: int,
               team: TeamRuntime | None = None, driver: str = "command",
               acp_command: list[str] | None = None,
               participant_ids: set[str] | None = None,
               provider_secret: ProviderSecretAttestation | None = None) -> None:
    for agent in group:
        _run_agent_in_place(runtime_dir, project_root, go_run_id, agent, timeout_seconds,
                            team, driver, acp_command, participant_ids, provider_secret)


def _run_agent_in_place(runtime_dir: str, project_root: str, go_run_id: str,
                        agent: GoAgentDispatch, timeout_seconds: int,
                        team: TeamRuntime | None = None, driver: str = "command",
                        acp_command: list[str] | None = None,
                        participant_ids: set[str] | None = None,
                        provider_secret: ProviderSecretAttestation | None = None) -> None:
    try:
        cwd, env_overrides = _resolve_isolation(runtime_dir, project_root, go_run_id, agent)
        _ensure_agent_context_artifacts(runtime_dir, agent)
        if team is not None:
            context_refs = _agent_context_refs(agent)
            team.record_task_created(
                go_run_id, agent.agent_id,
                shard_index=agent.shard_index, shard_count=agent.shard_count,
                targets=agent.targets,
                context_refs=context_refs,
            )
            team.record_task_claimed(go_run_id, agent.agent_id, context_refs=context_refs)
        if driver == "acp":
            worker_result = _run_one_agent_acp(
                runtime_dir, agent, timeout_seconds,
                cwd=cwd or project_root, go_run_id=go_run_id, acp_command=acp_command,
                team=team, env_overrides=env_overrides,
                provider_secret=provider_secret,
            )
        else:
            worker_result = _run_one_agent(runtime_dir, agent, timeout_seconds,
                                           cwd=cwd, env_overrides=env_overrides,
                                           provider_secret=provider_secret)
        agent.status = "completed"
        agent.worker_status = worker_result.summary.status
        agent.report_path = worker_result.report_path
        agent.changed_files = worker_result.summary.changed_files
        agent.verification = worker_result.summary.verification
        _apply_opencode_events(agent)
        if team is not None:
            team.record_result(
                go_run_id, agent.agent_id,
                status=agent.worker_status or "completed",
                report_path=agent.report_path, isolated=agent.isolated,
            )
            _record_worker_message_sidecar(
                team, go_run_id, agent, participant_ids or {agent.agent_id},
            )
    except Exception as exc:  # pragma: no cover - defensive guard
        agent.status = "failed"
        agent.worker_status = "failed"
        agent.report_path = ""
        secrets = (
            provider_secret.redaction_values() if provider_secret is not None else ()
        )
        _write_agent_failure(agent, exc, secrets=secrets)
        if team is not None:
            team.record_result(go_run_id, agent.agent_id, status="failed")


def _resolve_isolation(runtime_dir: str, project_root: str, go_run_id: str,
                       agent: GoAgentDispatch) -> tuple[str | None, dict[str, str] | None]:
    """Create a per-agent worktree when isolation is requested.

    Generic worktree creation lives in `worktree.py`. Two things are isolated:
    1. Working directory: the agent runs with `cwd` set to its own git worktree,
       and the packet is rebased to that worktree so the executor's writes (even
       via absolute paths it reads from the packet) land in the worktree, not the
       shared tree.
    2. Executor state: OpenCode keeps its sqlite session DB under `XDG_DATA_HOME`
       (verified against OpenCode 1.17.9), so each agent gets its own
       `XDG_DATA_HOME` to remove the concurrent `database is locked` failure.
       This is the only executor-specific logic and it stays in the dispatch
       (adapter) layer.

    Returns `(cwd, env_overrides)`. When isolation is not requested or a worktree
    cannot be created, returns `(None, None)` so the worker runs in place (still
    protected by write-set serialization) and `agent.isolated` is corrected to
    `False` (honest, no fake green).
    """
    if not agent.isolated:
        return None, None
    handle = create_worktree(project_root, go_run_id, agent.agent_id, runtime_dir=runtime_dir)
    if handle is None:
        # Isolation was requested but impossible (not a git tree / git missing).
        # Fall back to in-place execution and record the truth.
        agent.isolated = False
        agent.worktree_path = ""
        return None, None
    agent.worktree_path = handle.path
    # Rebase the packet so the agent's project root IS the worktree. Without this
    # the executor follows the absolute root embedded in the packet and edits the
    # shared tree, defeating working-directory isolation.
    DispatchPacketStore(runtime_dir=runtime_dir).rebase_packet(agent.packet_dir, handle.path)
    # Executor-specific: give OpenCode its own state dir (sqlite session DB) so
    # concurrent agents cannot hit `database is locked`.
    env_overrides = {"XDG_DATA_HOME": str(Path(handle.path) / ".opencode-data")}
    return handle.path, env_overrides


def _ensure_agent_context_artifacts(runtime_dir: str, agent: GoAgentDispatch) -> None:
    packet = DispatchPacketStore(runtime_dir=runtime_dir).ensure_context_artifacts(agent.packet_dir)
    agent.context_packet_path = packet.context_packet_path
    agent.context_ledger_path = packet.context_ledger_path


def _record_worker_message_sidecar(team: TeamRuntime, go_run_id: str,
                                   agent: GoAgentDispatch,
                                   participant_ids: set[str]) -> None:
    """Record one bounded, data-only message emitted by the executing agent.

    Worker reports remain free-form Markdown and are deliberately not parsed
    for collaboration data. This sidecar is a narrow controller-owned contract:
    the sender is bound to the current agent and the recipient must already be
    a distinct participant in the same run.
    """
    sidecar_path = Path(agent.packet_dir) / TEAM_MESSAGE_SIDECAR
    if not sidecar_path.is_file():
        return
    try:
        payload = json.loads(sidecar_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return
    if not isinstance(payload, dict) or set(payload) != {"to_agent_id", "kind", "summary"}:
        return
    to_agent_id = payload["to_agent_id"]
    kind = payload["kind"]
    summary = payload["summary"]
    if not all(isinstance(value, str) for value in (to_agent_id, kind, summary)):
        return
    if (
        to_agent_id not in participant_ids
        or to_agent_id == agent.agent_id
        or kind not in _TEAM_MESSAGE_KINDS
        or not summary
        or summary != summary.strip()
        or "\x00" in summary
        or len(summary) > _MAX_TEAM_MESSAGE_SUMMARY_CHARS
    ):
        return
    try:
        team.record_agent_message(
            go_run_id,
            agent.agent_id,
            to_agent_id,
            kind=kind,
            summary=summary,
        )
    except (OSError, ValueError):
        return
    try:
        sidecar_path.unlink()
    except OSError:
        return


def _apply_opencode_events(agent: GoAgentDispatch) -> None:
    """Fill structured OpenCode execution data from the worker JSONL output.

    Reuse-depth L1 -> L2: instead of discarding OpenCode stdout, parse its
    `run --format json` JSONL to surface real session id, token usage, cost, and
    tool calls. Defensive by design; never raises and leaves fields at defaults
    when the worker is not OpenCode or emits nothing parseable.
    """
    if not agent.worker_command:
        return
    if "opencode" not in str(agent.worker_command[0]).lower():
        return
    output_path = Path(agent.packet_dir) / "worker-output.txt"
    if not output_path.exists():
        return
    try:
        text = output_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return
    summary = parse_opencode_run_jsonl(text)
    if summary.is_empty():
        return
    agent.session_id = summary.session_id
    agent.input_tokens = summary.input_tokens
    agent.output_tokens = summary.output_tokens
    agent.total_tokens = summary.total_tokens
    agent.cost = summary.cost
    agent.tool_calls = [{"name": call.name, "target": call.target} for call in summary.tool_calls]


def _run_one_agent(runtime_dir: str, agent: GoAgentDispatch, timeout_seconds: int, *,
                   cwd: str | None = None,
                   env_overrides: dict[str, str] | None = None,
                   provider_secret: ProviderSecretAttestation | None = None) -> WorkerResult:
    agent.status = "running"
    return CommandWorker(runtime_dir=runtime_dir, timeout_seconds=timeout_seconds).run_packet(
        agent.packet_dir,
        agent.worker_command,
        cwd=cwd,
        env_overrides=env_overrides,
        provider_secret=provider_secret,
        strip_provider_secrets=True,
    )


def _agent_context_refs(agent: GoAgentDispatch) -> list[dict[str, str]]:
    refs: list[dict[str, str]] = []
    context_packet_path = str(
        agent.context_packet_path or Path(agent.packet_dir) / "context-packet.json"
    )
    if context_packet_path and Path(context_packet_path).exists():
        refs.append({
            "ref_type": "context_packet",
            "ref_path": context_packet_path,
            "context_id": Path(context_packet_path).stem,
        })
    context_ledger_path = str(
        agent.context_ledger_path or Path(agent.packet_dir) / "context-ledger.json"
    )
    if context_ledger_path and Path(context_ledger_path).exists():
        refs.append({
            "ref_type": "context_ledger",
            "ref_path": context_ledger_path,
            "context_id": Path(context_ledger_path).stem,
        })
    packet_dir = str(agent.packet_dir or "")
    if packet_dir:
        refs.append({
            "ref_type": "legacy_context",
            "ref_path": packet_dir,
            "context_id": Path(packet_dir).name,
        })
    task_spec_path = str(agent.task_spec_path or "")
    if task_spec_path:
        refs.append({
            "ref_type": "legacy_task_spec",
            "ref_path": task_spec_path,
            "context_id": Path(task_spec_path).parent.name,
        })
    return refs


def _run_one_agent_acp(runtime_dir: str, agent: GoAgentDispatch, timeout_seconds: int, *,
                       cwd: str, go_run_id: str,
                       acp_command: list[str] | None = None,
                       team: TeamRuntime | None = None,
                       env_overrides: dict[str, str] | None = None,
                       provider_secret: ProviderSecretAttestation | None = None) -> WorkerResult:
    """Execute one agent through a governed ACP session instead of a CLI worker.

    Drives `GovernedAcpSession` with the packet's objective as the prompt, then
    synthesizes the standard ExecutionReport (status from the session stop reason
    + held count; changed files from `git status` in the cwd) and ingests it
    through the dispatch store so all downstream handling is unchanged.
    """
    from .acp_session import GovernedAcpSession  # local import avoids cycle

    agent.status = "running"
    store = DispatchPacketStore(runtime_dir=runtime_dir)
    packet = store.load_packet(agent.packet_dir)
    prompt_text = packet.objective_text or packet.requirement or "Implement the assigned task."

    session = GovernedAcpSession(
        command=acp_command or ["opencode", "acp"],
        runtime_dir=runtime_dir,
        cwd=cwd,
        team=team,
    )
    acp_env_overrides = dict(env_overrides or {})
    for env_name in PROVIDER_SECRET_ENV_NAMES:
        acp_env_overrides[env_name] = ""
    session_result = session.run(
        prompt_text, run_id=go_run_id, agent_id=agent.agent_id,
        prompt_timeout=float(timeout_seconds), env_overrides=acp_env_overrides or None,
    )
    agent.session_id = session_result.session_id

    changed = _git_changed_files(cwd)
    end_ok = session_result.stop_reason in {"end_turn", "completed", "stop"}
    status = "pass" if end_ok else "failed"
    if session_result.held_high_risk and not changed:
        # Everything was held and nothing changed: report blocked, not pass.
        status = "blocked"

    report_path = Path(agent.packet_dir) / "ExecutionReport.md"
    changed_block = "\n".join(f"- `{path}`" for path in changed) or "- (none)"
    report_path.write_text(
        f"## ExecutionReport: {packet.packet_id}\n\n"
        f"- **Status**: {status}\n"
        "- **Review Status**: draft\n"
        f"- **Summary**: ACP session {session_result.session_id} ended with "
        f"stop_reason={session_result.stop_reason!r}; "
        f"held {session_result.held_high_risk} high-risk request(s).\n"
        "- **Changed Files**:\n"
        f"{changed_block}\n"
        f"- **Evidence**: governed ACP session; {len(session_result.updates)} update(s) streamed.\n"
        "- **Risks**: ACP driver is opt-in; high-risk operations are gate-held.\n",
        encoding="utf-8",
    )
    summary = store.ingest_report(agent.packet_dir, report_path)
    return WorkerResult(packet=packet, report_path=str(report_path), summary=summary)


def _git_changed_files(cwd: str) -> list[str]:
    import subprocess
    try:
        completed = subprocess.run(
            ["git", "-C", cwd, "status", "--porcelain"],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=30, check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return []
    if completed.returncode != 0:
        return []
    files: list[str] = []
    for line in completed.stdout.splitlines():
        entry = line[3:].strip() if len(line) > 3 else line.strip()
        if entry:
            files.append(entry)
    return files


def _result_status(result: GoDispatchResult) -> str:
    if not result.agents:
        return "queued"
    worker_statuses = [agent.worker_status for agent in result.agents]
    if all(status in SUCCESS_WORKER_STATUSES for status in worker_statuses):
        return "passed"
    if any(status in {"failed", "fail"} for status in worker_statuses):
        return "failed"
    if any(status == "blocked" for status in worker_statuses):
        return "blocked"
    return "queued"


def _write_metadata(result: GoDispatchResult) -> Path:
    runtime_root = Path(result.runtime_dir)
    path = runtime_root / "go-runs" / result.go_run_id / "go-run.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = asdict(result)
    if payload.get("toolchain") is None:
        payload.pop("toolchain", None)
    if payload.get("workflow_profile") is None:
        payload.pop("workflow_profile", None)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8")
    return path


def _resolve_go_run_metadata_path(runtime_root: Path, run_id: str) -> Path:
    base = runtime_root / "go-runs"
    if not base.exists():
        raise ValueError(f"no go runs found in {runtime_root}")
    if run_id == "latest":
        paths = [path for path in base.glob("*/go-run.json") if path.is_file()]
        if not paths:
            raise ValueError(f"no go runs found in {runtime_root}")
        runs = [(_read_go_run_metadata(path), path) for path in paths]
        return sorted(runs, key=lambda item: str(item[0].get("created_at", "")))[-1][1]
    path = base / run_id / "go-run.json"
    if not path.exists():
        raise ValueError(f"go run not found: {run_id}")
    return path


def _read_go_run_metadata(path: Path) -> dict[str, Any]:
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise ValueError(f"go run metadata is unreadable: {path}") from exc
    return _parse_go_run_metadata_bytes(raw, path)


def _parse_go_run_metadata_bytes(raw: bytes, path: Path) -> dict[str, Any]:
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"go run metadata is unreadable: {path}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"go run metadata is unreadable: {path}")
    return data


def _go_result_from_metadata(data: dict[str, Any], *, fallback_runtime_dir: Path) -> GoDispatchResult:
    agent_items = data.get("agents", [])
    if not isinstance(agent_items, list) or any(
        not isinstance(agent, dict) for agent in agent_items
    ):
        raise ValueError("go run metadata agents must be a list of objects")
    agents = [
        GoAgentDispatch(
            agent_id=str(agent.get("agent_id", "")),
            shard_index=int(agent.get("shard_index", 0) or 0),
            shard_count=int(agent.get("shard_count", 0) or 0),
            targets=_string_list(agent.get("targets", [])),
            target_bytes=int(agent.get("target_bytes", 0) or 0),
            packet_dir=str(agent.get("packet_dir", "")),
            task_spec_path=str(agent.get("task_spec_path", "")),
            worker_command=_string_list(agent.get("worker_command", [])),
            status=str(agent.get("status", "queued") or "queued"),
            report_path=str(agent.get("report_path", "")),
            worker_status=str(agent.get("worker_status", "")),
            changed_files=_string_list(agent.get("changed_files", [])),
            verification=str(agent.get("verification", "")),
            methodology=agent.get("methodology"),
            session_id=str(agent.get("session_id", "")),
            input_tokens=int(agent.get("input_tokens", 0) or 0),
            output_tokens=int(agent.get("output_tokens", 0) or 0),
            total_tokens=int(agent.get("total_tokens", 0) or 0),
            cost=float(agent.get("cost", 0.0) or 0.0),
            tool_calls=[
                {"name": str(call.get("name", "")), "target": str(call.get("target", ""))}
                for call in (agent.get("tool_calls") or [])
                if isinstance(call, dict)
            ],
            model_provider=str(agent.get("model_provider", "")),
            isolated=bool(agent.get("isolated", False)),
            worktree_path=str(agent.get("worktree_path", "")),
            context_packet_path=str(agent.get("context_packet_path", "")),
            context_ledger_path=str(agent.get("context_ledger_path", "")),
        )
        for agent in agent_items
    ]
    return GoDispatchResult(
        go_run_id=str(data.get("go_run_id", "")),
        project_id=str(data.get("project_id", "")),
        project_root=str(data.get("project_root", "")),
        requirement=str(data.get("requirement", "")),
        runtime_dir=str(data.get("runtime_dir") or fallback_runtime_dir),
        status=str(data.get("status", "queued") or "queued"),
        execute=bool(data.get("execute", False)),
        agents=agents,
        created_at=str(data.get("created_at", "")),
        metadata_path=str(data.get("metadata_path", "")),
        methodology=data.get("methodology"),
        model_provider=str(data.get("model_provider", "")),
        driver=str(data.get("driver", "command") or "command"),
        toolchain=(
            data["toolchain"]
            if isinstance(data.get("toolchain"), dict)
            else None
        ),
        workflow_profile=(
            data["workflow_profile"]
            if isinstance(data.get("workflow_profile"), dict)
            else None
        ),
    )


def _string_list(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value]
    if value:
        return [str(value)]
    return []


def _write_agent_failure(
    agent: GoAgentDispatch,
    exc: Exception,
    *,
    secrets: tuple[str, ...] = (),
) -> None:
    path = Path(agent.packet_dir) / "go-agent-error.txt"
    detail = redact_provider_secret_text(
        f"{type(exc).__name__}: {exc}",
        secrets,
    )
    path.write_text(f"{detail}\n", encoding="utf-8")


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
                       targets: list[str], methodology: dict[str, Any] | None = None) -> str:
    lines: list[str] = []
    if methodology:
        title = str(methodology.get("title") or methodology.get("skill_id") or "unknown")
        lines.extend([f"Methodology: {title}", ""])
        # Hard constraints resolved by deny-overrides (skills + P0 rules). These
        # are non-negotiable executor constraints, not model attention hints.
        constraint_lines: list[str] = []
        if methodology.get("read_only"):
            constraint_lines.append("- READ-ONLY: do not modify files; produce a review/analysis only.")
        if methodology.get("network_enabled") is False:
            constraint_lines.append("- NO NETWORK: network access is denied for this run.")
        if methodology.get("require_red_green_evidence"):
            constraint_lines.append("- REQUIRE RED-GREEN EVIDENCE: include failing-then-passing test evidence.")
        if constraint_lines:
            lines.extend(["Hard constraints (enforced, not optional):", *constraint_lines, ""])
    lines.extend([
        requirement,
        "",
        f"Shard: {shard_number}/{shard_count}",
        "Role: coding execution agent. Implement only the assigned slice, collect verification, and write ExecutionReport.",
    ])
    if targets:
        lines.extend(["Assigned targets:", *[f"- {target}" for target in targets]])
    else:
        lines.append("Assigned targets: project-level discovery and the smallest safe implementation slice.")
    return "\n".join(lines)


def _worker_prompt(shard_number: int, shard_count: int) -> str:
    return (
        "Read RDGOAL_TASKSPEC_JSON and RDGOAL_TASKSPEC_MD from the environment. "
        f"You are coding shard {shard_number}/{shard_count}. "
        "Make only the smallest safe project change for this shard, run the relevant verification, "
        "and write a Markdown ExecutionReport to RDGOAL_REPORT_PATH with Status, Changed Files, Evidence, Risks, and Reviewer Index."
    )


def _opencode_command(*, model: str, opencode_agent: str,
                      shard_number: int, shard_count: int) -> list[str]:
    prompt = _worker_prompt(shard_number, shard_count)
    return [
        "opencode",
        "run",
        "-m",
        model,
        "--dangerously-skip-permissions",
        "--agent",
        opencode_agent,
        "--format",
        "json",
        prompt,
    ]


def build_go_worker_command(
    *,
    worker_command: list[str] | None,
    worker: str,
    model: str,
    opencode_agent: str,
    shard_number: int,
    shard_count: int,
) -> list[str]:
    if worker_command:
        return list(worker_command)
    selected_worker = worker.strip().lower()
    if selected_worker not in GO_WORKERS:
        raise ValueError(f"unknown worker: {worker}")
    resolved_model = model or DEFAULT_GO_MODEL
    return _opencode_command(
        model=resolved_model,
        opencode_agent=opencode_agent,
        shard_number=shard_number,
        shard_count=shard_count,
    )


def describe_go_worker(*, worker_command: list[str] | None,
                       worker: str, model: str,
                       opencode_agent: str) -> str:
    if worker_command:
        return "custom command"
    resolved_model = model or DEFAULT_GO_MODEL
    return f"opencode model={resolved_model} agent={opencode_agent}"


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
