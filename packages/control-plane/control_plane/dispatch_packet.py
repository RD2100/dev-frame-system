"""File-based dispatch packets for rdgoal worker handoff."""
from __future__ import annotations

import json
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .agent_adapter import SubAgentObjective
from .backup_guard import default_runtime_dir, is_inside
from .decision_engine import Decision
from .project_contract import ProjectContract


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class DispatchPacket:
    packet_id: str
    project_id: str
    project_root: str
    requirement: str
    operation: str
    targets: list[str]
    decision_mode: str
    dispatch_ready: bool
    task_spec: dict[str, Any]
    objective_text: str
    packet_dir: str = ""
    created_at: str = field(default_factory=_utc_now)


@dataclass
class ExecutionReportSummary:
    packet_id: str
    project_id: str
    status: str
    changed_files: list[str] = field(default_factory=list)
    verification: str = ""
    report_path: str = ""
    ingested_at: str = field(default_factory=_utc_now)


class DispatchPacketStore:
    """Persist controller-to-worker packets outside the repository."""

    def __init__(self, runtime_dir: str | Path | None = None,
                 repo_root: str | Path | None = None) -> None:
        self.runtime_dir = Path(runtime_dir).resolve() if runtime_dir else default_runtime_dir()
        self.repo_root = Path(repo_root).resolve() if repo_root else None
        self.outbox = self.runtime_dir / "rdgoal-outbox"
        self.reports = self.runtime_dir / "rdgoal-reports"

    def write_packet(self, *, contract: ProjectContract, project_root: str | Path,
                     requirement: str, operation: str, targets: list[str],
                     decision: Decision, objective: SubAgentObjective,
                     dispatch_ready: bool) -> DispatchPacket:
        self._ensure_runtime_outside_repo()
        packet_id = f"rdgoal-{contract.project_id}-{int(time.time() * 1000)}-{uuid.uuid4().hex[:6]}"
        packet_dir = self.outbox / contract.project_id / packet_id
        packet_dir.mkdir(parents=True, exist_ok=True)
        packet = DispatchPacket(
            packet_id=packet_id,
            project_id=contract.project_id,
            project_root=str(Path(project_root).resolve()),
            requirement=requirement,
            operation=operation,
            targets=targets,
            decision_mode=decision.mode.value,
            dispatch_ready=dispatch_ready,
            task_spec=self._task_spec(
                packet_id=packet_id,
                contract=contract,
                requirement=requirement,
                operation=operation,
                targets=targets,
                decision=decision,
                dispatch_ready=dispatch_ready,
            ),
            objective_text=objective.text,
            packet_dir=str(packet_dir),
        )
        (packet_dir / "packet.json").write_text(
            json.dumps(asdict(packet), indent=2, ensure_ascii=True),
            encoding="utf-8",
        )
        (packet_dir / "TASKSPEC.json").write_text(
            json.dumps(packet.task_spec, indent=2, ensure_ascii=True),
            encoding="utf-8",
        )
        (packet_dir / "TASKSPEC.md").write_text(self._task_spec_markdown(packet), encoding="utf-8")
        return packet

    def load_packet(self, packet_dir: str | Path) -> DispatchPacket:
        data = json.loads((Path(packet_dir) / "packet.json").read_text(encoding="utf-8"))
        return DispatchPacket(**data)

    def ingest_report(self, packet_dir: str | Path, report_path: str | Path) -> ExecutionReportSummary:
        packet = self.load_packet(packet_dir)
        report = Path(report_path)
        text = report.read_text(encoding="utf-8")
        summary = ExecutionReportSummary(
            packet_id=packet.packet_id,
            project_id=packet.project_id,
            status=_extract_status(text),
            changed_files=_extract_changed_files(text),
            verification=_extract_verification(text),
            report_path=str(report.resolve()),
        )
        target_dir = self.reports / packet.project_id / packet.packet_id
        target_dir.mkdir(parents=True, exist_ok=True)
        (target_dir / "execution-summary.json").write_text(
            json.dumps(asdict(summary), indent=2, ensure_ascii=True),
            encoding="utf-8",
        )
        return summary

    def _ensure_runtime_outside_repo(self) -> None:
        if self.repo_root and is_inside(self.runtime_dir, self.repo_root):
            raise ValueError("Dispatch packet runtime dir must stay outside the public repository.")

    def _task_spec(self, *, packet_id: str, contract: ProjectContract, requirement: str,
                   operation: str, targets: list[str], decision: Decision,
                   dispatch_ready: bool) -> dict[str, Any]:
        status = "ready" if dispatch_ready else "deferred"
        return {
            "task_id": packet_id,
            "title": f"rdgoal: {operation}",
            "priority": "P2",
            "status": status,
            "description": requirement,
            "assumptions": [
                "Operate under project-local rdinit/SADP rules.",
                "Controller decisions are recorded in rdgoal runtime state.",
            ],
            "risk_notes": decision.reason,
            "gate_0": {
                "triggered": True,
                "trigger_reason": "rdgoal generated a worker dispatch packet.",
                "inventory_evidence": {
                    "queried_sources": [
                        "docs/agent-runtime/sub-agent-dispatch-protocol.md",
                        "rules/orchestration.md",
                    ],
                    "matched_capabilities": ["SADP", "rdgoal"],
                    "compared_against_request": [operation],
                },
                "rules_checked": ["orch-001", "orch-002", "orch-003", "orch-004", "orch-005"],
                "lessons_checked": [],
                "sufficiency_decision": "existing_partial",
                "decision": "build_delta",
                "delta_justification": "rdgoal routes the existing project workflow through a controller decision.",
            },
            "conflict_registry": {
                "read_set": targets,
                "write_set": targets if dispatch_ready else [],
                "protected_files_touched": any(_is_protected_target(target) for target in targets),
                "conflict_level": "high" if len(targets) > 1 else "low",
            },
        }

    def _task_spec_markdown(self, packet: DispatchPacket) -> str:
        spec = packet.task_spec
        targets = "\n".join(f"- {target}" for target in packet.targets) or "- (none)"
        return (
            f"# TaskSpec: {spec['task_id']}\n\n"
            f"- **Project**: {packet.project_id}\n"
            f"- **Operation**: {packet.operation}\n"
            f"- **Decision Mode**: {packet.decision_mode}\n"
            f"- **Dispatch Ready**: {packet.dispatch_ready}\n"
            f"- **Project Root**: {packet.project_root}\n\n"
            "## Targets\n\n"
            f"{targets}\n\n"
            "## Objective\n\n"
            f"{packet.objective_text}\n\n"
            "## Machine Packet\n\n"
            "See `packet.json` and `TASKSPEC.json` in this directory.\n"
        )


def _is_protected_target(target: str) -> bool:
    normalized = target.replace("\\", "/").lower()
    protected_names = {
        "agents.md",
        "claude.md",
        "capability-inventory.md",
        "sub-agent-dispatch-protocol.md",
        "rules/core.md",
    }
    return any(normalized.endswith(name) for name in protected_names)


def _extract_status(text: str) -> str:
    lowered = text.lower()
    for status in ["pass", "passed", "completed", "blocked", "failed", "fail", "human_required"]:
        if f"status**: {status}" in lowered or f"status: {status}" in lowered:
            return "passed" if status in {"pass", "passed", "completed"} else status
    return "unknown"


def _extract_changed_files(text: str) -> list[str]:
    changed: list[str] = []
    capture = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.lower().startswith("- **changed files**") or stripped.lower().startswith("## changed files"):
            capture = True
            continue
        if capture and (
            stripped.startswith("#")
            or (stripped.startswith("- **") and "changed files" not in stripped.lower())
        ):
            break
        if capture and stripped.startswith("-"):
            changed.append(stripped.lstrip("- ").strip("` "))
    return changed


def _extract_verification(text: str) -> str:
    lowered = text.lower()
    marker = "verification"
    index = lowered.find(marker)
    if index == -1:
        index = lowered.find("evidence")
    if index == -1:
        return ""
    return text[index:index + 1000].strip()
