"""Workflow orchestration engine (M3, slice 1).

A thin, recorded, role-phased conductor that triggers a collaborative coding
workflow and lets the controller decide the next move. It REUSES the existing
executor (`go_dispatch`) and the M1 team journal (`TeamRuntime`); it adds the
explicit phase loop and a recorded controller verdict. It is not a second
executor and not a model driver (live multi-agent driving is M2/ACP).

Phases:
- plan    (coordinator): prepare the go-run shard plan (no execution).
- execute (executors):   run the prepared agents; task events are recorded by
                         go_dispatch via TeamRuntime.
- review  (reviewer):    derive a verdict from the recorded task results and
                         record it as the controller's decision.

Every phase transition and the final verdict are recorded as real team events,
so the collaboration is durable and inspectable, not synthesized at read time.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from .backup_guard import default_runtime_dir
from .go_dispatch import execute_go_run, run_go_dispatch
from .team_runtime import TeamRuntime

# Controller verdict vocabulary, aligned with decision_engine.DecisionMode.
VERDICT_CONTINUE = "continue"
VERDICT_REVISE = "revise"
VERDICT_STOP = "stop"

_SUCCESS = {"pass", "passed", "completed", "verified"}


@dataclass
class WorkflowPhase:
    name: str
    role: str
    status: str
    summary: str = ""


@dataclass
class WorkflowResult:
    go_run_id: str
    project_id: str
    status: str
    verdict: str
    phases: list[WorkflowPhase] = field(default_factory=list)
    runtime_dir: str = ""
    agent_count: int = 0
    passed_agents: int = 0
    failed_agents: int = 0


class WorkflowEngine:
    """Drive a recorded plan -> execute -> review coding workflow."""

    def __init__(self, runtime_dir: str | Path | None = None) -> None:
        self.runtime_dir = Path(runtime_dir).resolve() if runtime_dir else default_runtime_dir()

    def run_coding_workflow(
        self,
        project_path: str | Path,
        goal: str,
        *,
        agents: int = 2,
        targets: list[str] | None = None,
        worker_command: list[str] | None = None,
        worker: str = "opencode",
        model: str | None = None,
        model_provider: str | None = None,
        opencode_agent: str = "build",
        timeout_seconds: int = 900,
        isolate: bool = False,
        driver: str = "command",
        acp_command: list[str] | None = None,
        on_prepared: Callable[[str], None] | None = None,
    ) -> WorkflowResult:
        if driver not in {"command", "acp"}:
            raise ValueError(f"unknown driver: {driver!r} (expected 'command' or 'acp')")
        team = TeamRuntime(runtime_dir=self.runtime_dir)
        phases: list[WorkflowPhase] = []

        # Phase 1: plan (coordinator) — prepare the shard plan, no execution.
        prepared = run_go_dispatch(
            project_path,
            goal,
            runtime_dir=self.runtime_dir,
            agents=agents,
            targets=targets,
            execute=False,
            worker_command=worker_command,
            worker=worker,
            model=model,
            model_provider=model_provider,
            opencode_agent=opencode_agent,
            timeout_seconds=timeout_seconds,
            isolate=isolate,
            driver=driver,
            acp_command=acp_command,
        )
        go_run_id = prepared.go_run_id
        if on_prepared is not None:
            try:
                on_prepared(go_run_id)
            except Exception:  # noqa: BLE001 - progress linkage must never break the run
                pass
        team.record_workflow_event(
            go_run_id, phase="start", status="started", role="coordinator",
            summary=f"Workflow started for run {go_run_id} (driver={driver}): {goal[:80]}",
        )
        plan_summary = f"Coordinator prepared {len(prepared.agents)} agent task(s) for run {go_run_id}."
        team.record_workflow_event(
            go_run_id, phase="plan", status="completed", role="coordinator",
            summary=plan_summary,
        )
        phases.append(WorkflowPhase("plan", "coordinator", "completed", plan_summary))

        if not prepared.agents:
            verdict = VERDICT_STOP
            team.record_workflow_event(
                go_run_id, phase="review", status=verdict, role="reviewer",
                summary="No agent tasks were prepared; nothing to execute.",
            )
            phases.append(WorkflowPhase("review", "reviewer", verdict, "No tasks prepared."))
            return WorkflowResult(
                go_run_id=go_run_id, project_id=prepared.project_id,
                status="blocked", verdict=verdict, phases=phases,
                runtime_dir=str(self.runtime_dir),
            )

        # Phase 2: execute (executors) — task events recorded inside go_dispatch.
        team.record_workflow_event(
            go_run_id, phase="execute", status="started", role="executor",
            summary=f"Executing {len(prepared.agents)} agent task(s) for run {go_run_id}.",
        )
        executed = execute_go_run(self.runtime_dir, go_run_id, timeout_seconds=timeout_seconds)
        passed = sum(1 for a in executed.agents if (a.worker_status or "").lower() in _SUCCESS)
        failed = sum(1 for a in executed.agents if (a.worker_status or "").lower() in {"failed", "fail", "error"})
        exec_summary = f"Execute phase finished: {passed} passed, {failed} failed of {len(executed.agents)}."
        team.record_workflow_event(
            go_run_id, phase="execute", status="completed", role="executor",
            summary=exec_summary,
        )
        phases.append(WorkflowPhase("execute", "executor", "completed", exec_summary))

        # Phase 3: review (reviewer) — controller verdict from recorded results.
        verdict = _verdict_for(executed.agents)
        review_summary = (
            f"Reviewer verdict for run {go_run_id}: {verdict} "
            f"({passed} passed, {failed} failed of {len(executed.agents)})."
        )
        team.record_workflow_event(
            go_run_id, phase="review", status=verdict, role="reviewer",
            summary=review_summary,
        )
        phases.append(WorkflowPhase("review", "reviewer", verdict, review_summary))

        return WorkflowResult(
            go_run_id=go_run_id,
            project_id=executed.project_id,
            status=executed.status,
            verdict=verdict,
            phases=phases,
            runtime_dir=str(self.runtime_dir),
            agent_count=len(executed.agents),
            passed_agents=passed,
            failed_agents=failed,
        )


def _verdict_for(agents: list[Any]) -> str:
    statuses = [str(getattr(a, "worker_status", "") or "").lower() for a in agents]
    if not statuses:
        return VERDICT_STOP
    if all(status in _SUCCESS for status in statuses):
        return VERDICT_CONTINUE
    if any(status in {"failed", "fail", "error"} for status in statuses):
        return VERDICT_REVISE
    return VERDICT_REVISE


def render_workflow_result_text(result: WorkflowResult) -> str:
    lines = [
        "DevFrame Workflow",
        f"go_run_id : {result.go_run_id}",
        f"project   : {result.project_id}",
        f"status    : {result.status}",
        f"verdict   : {result.verdict}",
        f"agents    : {result.agent_count} ({result.passed_agents} passed, {result.failed_agents} failed)",
        "",
        "Phases",
    ]
    for phase in result.phases:
        lines.append(f"- {phase.name} [{phase.role}] {phase.status}")
        if phase.summary:
            lines.append(f"  {phase.summary}")
    return "\n".join(lines) + "\n"
