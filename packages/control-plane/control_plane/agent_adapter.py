"""Adapter between rdgoal and the existing per-project rdinit/SADP workflow."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .decision_engine import Decision
from .project_contract import ProjectContract


@dataclass
class SubAgentObjective:
    project_id: str
    project_root: str
    text: str
    dispatch_ready: bool


class SadpAdapter:
    """Build self-contained objectives for the existing project-local workflow."""

    def build_objective(self, *, contract: ProjectContract, project_root: str | Path,
                        requirement: str, decision: Decision) -> SubAgentObjective:
        root = str(Path(project_root).resolve())
        body = (
            f"# SADP Objective for {contract.project_id}\n\n"
            f"Requirement: {requirement.strip()}\n\n"
            f"Controller decision: {decision.mode.value}\n"
            f"Reason: {decision.reason}\n"
            f"Recommended path: {decision.recommended_path or 'Use project-local workflow.'}\n\n"
            "Operate under the existing rdinit/SADP project workflow. Produce an "
            "ExecutionReport with changed files, verification evidence, reviewer "
            "focus, and known gaps. Do not perform external live effects; prepare "
            "drafts instead when instructed.\n"
        )
        return SubAgentObjective(
            project_id=contract.project_id,
            project_root=root,
            text=body,
            dispatch_ready=decision.dispatch_allowed,
        )
