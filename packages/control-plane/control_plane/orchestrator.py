"""Total-control multi-project orchestrator for rdgoal."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .agent_adapter import SadpAdapter, SubAgentObjective
from .backup_guard import BackupGuard, GuardResult
from .decision_engine import Decision, DecisionEngine, OperationRequest
from .dispatch_packet import DispatchPacket, DispatchPacketStore, ExecutionReportSummary
from .project_contract import ProjectContract, load_contract
from .runtime_store import JournalEvent, RuntimeStore
from .state_machine import validate_transition


@dataclass
class ProjectState:
    contract: ProjectContract
    project_root: str
    status: str = "initialized"
    blocked_reason: str | None = None

    @property
    def project_id(self) -> str:
        return self.contract.project_id


@dataclass
class DispatchResult:
    project_id: str
    operation: str
    decision: Decision
    guard: GuardResult
    objective: SubAgentObjective
    packet: DispatchPacket | None = None

    @property
    def dispatch_ready(self) -> bool:
        return self.guard.allowed and self.objective.dispatch_ready


class Orchestrator:
    """Coordinate several project-local agents under one controller."""

    def __init__(self, runtime_dir: str | Path | None = None,
                 repo_root: str | Path | None = None) -> None:
        self.projects: dict[str, ProjectState] = {}
        self.dispatches: list[DispatchResult] = []
        self.engine = DecisionEngine()
        self.adapter = SadpAdapter()
        self.runtime_dir = runtime_dir
        self.store = RuntimeStore(runtime_dir=runtime_dir, repo_root=repo_root)
        self.packet_store = DispatchPacketStore(runtime_dir=runtime_dir, repo_root=repo_root)
        self.report_summaries: list[ExecutionReportSummary] = []

    def register(self, contract_path: str | Path, project_root: str | Path) -> ProjectState:
        contract = load_contract(contract_path)
        state = ProjectState(contract=contract, project_root=str(Path(project_root).resolve()))
        self.projects[contract.project_id] = state
        self.store.append(JournalEvent(
            event_type="project_registered",
            project_id=contract.project_id,
            payload={"project_root": state.project_root, "priority": contract.priority},
        ))
        return state

    def next_project(self) -> ProjectState | None:
        candidates = [
            project for project in self.projects.values()
            if project.status in {"initialized", "planned", "in_progress"}
        ]
        if not candidates:
            return None
        return sorted(candidates, key=lambda p: (p.contract.priority, p.project_id))[0]

    def set_status(self, project_id: str, next_status: str,
                   reason: str | None = None) -> tuple[bool, str]:
        project = self.projects[project_id]
        ok, message = validate_transition(project.status, next_status)
        if ok:
            project.status = next_status
            project.blocked_reason = reason if next_status == "blocked" else None
            self.store.append(JournalEvent(
                event_type="status_changed",
                project_id=project_id,
                payload={"status": next_status, "reason": reason},
            ))
        return ok, message

    def dispatch(self, *, project_id: str, requirement: str, operation: str,
                 targets: list[str] | None = None, summary: str = "") -> DispatchResult:
        targets = targets or []
        project = self.projects[project_id]
        request = OperationRequest(operation=operation, targets=targets, summary=summary)
        decision = self.engine.decide(project.contract, request)
        guard = BackupGuard(
            project_id=project_id,
            project_root=project.project_root,
            runtime_dir=self.runtime_dir,
        ).guard(decision, targets)
        objective = self.adapter.build_objective(
            contract=project.contract,
            project_root=project.project_root,
            requirement=requirement,
            decision=decision,
        )
        packet = self.packet_store.write_packet(
            contract=project.contract,
            project_root=project.project_root,
            requirement=requirement,
            operation=operation,
            targets=targets,
            decision=decision,
            objective=objective,
            dispatch_ready=guard.allowed and objective.dispatch_ready,
        )
        result = DispatchResult(
            project_id=project_id,
            operation=operation,
            decision=decision,
            guard=guard,
            objective=objective,
            packet=packet,
        )
        self.dispatches.append(result)
        self.store.append(JournalEvent(
            event_type="decision_made",
            project_id=project_id,
            payload={
                "operation": operation,
                "targets": targets,
                "decision_mode": decision.mode.value,
                "dispatch_ready": result.dispatch_ready,
                "reason": decision.reason,
                "snapshot": guard.snapshot.reference if guard.snapshot else None,
                "packet_dir": packet.packet_dir,
            },
        ))
        return result

    def ingest_report(self, packet_dir: str | Path, report_path: str | Path) -> ExecutionReportSummary:
        summary = self.packet_store.ingest_report(packet_dir, report_path)
        self.report_summaries.append(summary)
        self.store.append(JournalEvent(
            event_type="execution_report_ingested",
            project_id=summary.project_id,
            payload={
                "packet_id": summary.packet_id,
                "status": summary.status,
                "report_path": summary.report_path,
                "changed_files": summary.changed_files,
            },
        ))
        return summary

    def build_digest(self) -> dict[str, Any]:
        return {
            "projects": [
                {
                    "project_id": p.project_id,
                    "status": p.status,
                    "priority": p.contract.priority,
                    "autonomy_level": p.contract.autonomy_level,
                    "goal": p.contract.goal,
                    "blocked_reason": p.blocked_reason,
                }
                for p in sorted(self.projects.values(), key=lambda item: (item.contract.priority, item.project_id))
            ],
            "dispatches": [
                {
                    "project_id": d.project_id,
                    "operation": d.operation,
                    "decision_mode": d.decision.mode.value,
                    "dispatch_ready": d.dispatch_ready,
                    "reason": d.decision.reason,
                    "snapshot": d.guard.snapshot.reference if d.guard.snapshot else None,
                    "recommended_path": d.decision.recommended_path,
                    "packet_dir": d.packet.packet_dir if d.packet else "",
                }
                for d in self.dispatches
            ],
            "reports": [
                {
                    "packet_id": report.packet_id,
                    "project_id": report.project_id,
                    "status": report.status,
                    "changed_files": report.changed_files,
                    "report_path": report.report_path,
                }
                for report in self.report_summaries
            ],
        }

    def render_digest_markdown(self) -> str:
        digest = self.build_digest()
        lines = ["# rdgoal Multi-Project Digest", ""]
        lines.append("## Projects")
        if not digest["projects"]:
            lines.append("- none")
        for project in digest["projects"]:
            blocked = f" blocked={project['blocked_reason']}" if project["blocked_reason"] else ""
            lines.append(
                f"- {project['project_id']} [{project['status']}, "
                f"prio {project['priority']}, {project['autonomy_level']}]{blocked}"
            )
        lines.append("")
        lines.append("## Decisions")
        if not digest["dispatches"]:
            lines.append("- none")
        for dispatch in digest["dispatches"]:
            ready = "ready" if dispatch["dispatch_ready"] else "draft/held"
            snapshot = f" snapshot={dispatch['snapshot']}" if dispatch["snapshot"] else ""
            lines.append(
                f"- {dispatch['project_id']}: {dispatch['operation']} -> "
                f"{dispatch['decision_mode']} ({ready}){snapshot}"
            )
            if dispatch["packet_dir"]:
                lines.append(f"  packet: `{dispatch['packet_dir']}`")
        lines.append("")
        lines.append("## Execution reports")
        if not digest["reports"]:
            lines.append("- none")
        for report in digest["reports"]:
            lines.append(
                f"- {report['project_id']}: {report['packet_id']} -> "
                f"{report['status']} ({len(report['changed_files'])} changed file entries)"
            )
        lines.append("")
        return "\n".join(lines)
