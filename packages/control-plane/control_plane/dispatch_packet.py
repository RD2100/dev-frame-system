"""File-based dispatch packets for rdgoal worker handoff."""
from __future__ import annotations

import json
import re
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from hashlib import sha256
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
    context_packet_path: str = ""
    context_ledger_path: str = ""
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
        context_packet_path = packet_dir / "context-packet.json"
        context_ledger_path = packet_dir / "context-ledger.json"
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
            context_packet_path=str(context_packet_path),
            context_ledger_path=str(context_ledger_path),
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
        self._write_context_artifacts(packet)
        return packet

    def load_packet(self, packet_dir: str | Path) -> DispatchPacket:
        data = json.loads((Path(packet_dir) / "packet.json").read_text(encoding="utf-8"))
        return DispatchPacket(**data)

    def ensure_context_artifacts(self, packet_dir: str | Path) -> DispatchPacket:
        packet = self.load_packet(packet_dir)
        target_dir = Path(packet_dir)
        packet.packet_dir = str(target_dir)
        packet.context_packet_path = str(target_dir / "context-packet.json")
        packet.context_ledger_path = str(target_dir / "context-ledger.json")
        (target_dir / "packet.json").write_text(
            json.dumps(asdict(packet), indent=2, ensure_ascii=True),
            encoding="utf-8",
        )
        self._write_context_artifacts(packet)
        return packet

    def rebase_packet(self, packet_dir: str | Path, new_project_root: str | Path) -> DispatchPacket:
        """Repoint an existing packet at a new project root and re-render it.

        Used by opt-in worktree isolation: the agent reads its project root from
        the packet (packet.json and TASKSPEC.md), so to keep its writes inside an
        isolated worktree the packet itself must point there, not at the shared
        tree. Rewrites packet.json and TASKSPEC.md in place and returns the
        updated packet. The TASKSPEC.json content is unchanged (it carries no
        absolute root), so it is left as-is.
        """
        packet = self.load_packet(packet_dir)
        packet.project_root = str(Path(new_project_root).resolve())
        target_dir = Path(packet_dir)
        packet.context_packet_path = str(target_dir / "context-packet.json")
        packet.context_ledger_path = str(target_dir / "context-ledger.json")
        (target_dir / "packet.json").write_text(
            json.dumps(asdict(packet), indent=2, ensure_ascii=True),
            encoding="utf-8",
        )
        (target_dir / "TASKSPEC.md").write_text(self._task_spec_markdown(packet), encoding="utf-8")
        self._write_context_artifacts(packet)
        return packet

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
            "security_report": {
                "scan_status": "not_run",
                "new_external_api": False,
                "env_example_placeholders_only": None,
                "real_key_patterns_found": None,
                "staged_diff_secret_scan_run": False,
                "key_rotation_needed": None,
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
            "See `packet.json`, `TASKSPEC.json`, `context-packet.json`, and "
            "`context-ledger.json` in this directory.\n"
        )

    def _write_context_artifacts(self, packet: DispatchPacket) -> None:
        packet_dir = Path(packet.packet_dir)
        context_packet_path = Path(packet.context_packet_path or packet_dir / "context-packet.json")
        context_ledger_path = Path(packet.context_ledger_path or packet_dir / "context-ledger.json")
        context_packet_id = _context_packet_id(packet.packet_id)
        context_ledger_id = _context_ledger_id(packet.packet_id)
        created_at = packet.created_at or _utc_now()
        source_refs = _packet_source_refs(packet)
        constraints = {
            "allowed_actions": [
                "execute assigned task",
                "collect verification evidence",
                "write ExecutionReport",
            ],
            "forbidden_actions": [
                "claim final acceptance",
                "self-approve review",
                "write generated runtime artifacts into the public repository",
            ],
            "stop_lines": [
                "Worker output is execution evidence only.",
                "Independent review and FinalVerdict are required before acceptance.",
            ],
            "authority_boundary": {
                "can_execute": bool(packet.dispatch_ready),
                "can_review": False,
                "can_claim_final_acceptance": False,
                "final_verdict_required": True,
            },
        }
        content_seed = {
            "context_packet_id": context_packet_id,
            "project_id": packet.project_id,
            "task_id": packet.packet_id,
            "requirement": packet.requirement,
            "operation": packet.operation,
            "targets": packet.targets,
            "source_refs": source_refs,
            "constraints": constraints,
        }
        context_packet = {
            "schema_version": "0.1",
            "context_packet_id": context_packet_id,
            "project_id": packet.project_id,
            "goal_id": f"goal-{_safe_context_token(packet.project_id)}",
            "task_id": packet.packet_id,
            "domain": "code",
            "profile": "go-dispatch-task-context",
            "producer_role": "coordinator",
            "created_at": created_at,
            "intent_summary": packet.requirement,
            "intended_use": "execution",
            "immutability": {
                "immutable": True,
                "content_hash": _digest_json(content_seed),
            },
            "source_refs": source_refs,
            "omitted_required_refs": [],
            "forbidden_refs": [
                {
                    "ref": ".devframe-runtime",
                    "reason": "Runtime state stays outside the public repository.",
                }
            ],
            "freshness": {
                "checked_at": created_at,
                "stale_refs": [],
                "unknown_refs": [],
            },
            "completeness_state": "complete" if packet.dispatch_ready else "insufficient_evidence",
            "privacy_state": "redacted",
            "seal_state": "sealed",
            "limitations": [
                "Context packet authorizes execution context only.",
                "It is not review approval and cannot create final acceptance.",
            ],
            "constraints": constraints,
            "domain_refs": {
                "packet_id": packet.packet_id,
                "operation": packet.operation,
                "decision_mode": packet.decision_mode,
                "dispatch_ready": packet.dispatch_ready,
                "target_count": len(packet.targets),
            },
        }
        context_packet_path.write_text(
            json.dumps(context_packet, indent=2, ensure_ascii=True),
            encoding="utf-8",
        )
        context_packet_hash = _file_digest(context_packet_path)
        created_seed = {
            "ledger_entry_id": f"cle-{_safe_context_token(packet.packet_id)}-created",
            "entry_index": 0,
            "previous_entry_hash": None,
            "occurred_at": created_at,
            "actor_id": "rdgoal-dispatch",
            "actor_role": "coordinator",
            "event_type": "packet_created",
            "context_packet_id": context_packet_id,
            "summary": "Created sealed context packet for a go dispatch task.",
            "source_refs": [
                _ledger_source_ref(ref)
                for ref in source_refs
            ],
            "domain_refs": {"packet_id": packet.packet_id},
        }
        created_entry = {
            **created_seed,
            "entry_hash": _digest_json(created_seed),
        }
        dispatched_seed = {
            "ledger_entry_id": f"cle-{_safe_context_token(packet.packet_id)}-dispatched",
            "entry_index": 1,
            "previous_entry_hash": created_entry["entry_hash"],
            "occurred_at": created_at,
            "actor_id": "rdgoal-dispatch",
            "actor_role": "coordinator",
            "event_type": "packet_dispatched",
            "context_packet_id": context_packet_id,
            "summary": "Attached sealed context packet to the worker dispatch packet.",
            "source_refs": [{
                "ref_id": "context-packet",
                "kind": "artifact",
                "uri": str(context_packet_path),
                "content_hash": context_packet_hash,
            }],
            "domain_refs": {"packet_id": packet.packet_id},
        }
        dispatched_entry = {
            **dispatched_seed,
            "entry_hash": _digest_json(dispatched_seed),
        }
        context_ledger = {
            "schema_version": "0.1",
            "context_ledger_id": context_ledger_id,
            "project_id": packet.project_id,
            "goal_id": f"goal-{_safe_context_token(packet.project_id)}",
            "task_id": packet.packet_id,
            "created_at": created_at,
            "append_only": True,
            "entries": [created_entry, dispatched_entry],
        }
        context_ledger_path.write_text(
            json.dumps(context_ledger, indent=2, ensure_ascii=True),
            encoding="utf-8",
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


def _packet_source_refs(packet: DispatchPacket) -> list[dict[str, Any]]:
    packet_dir = Path(packet.packet_dir)
    refs = [
        _source_ref("packet-json", "artifact", packet_dir / "packet.json", required=True),
        _source_ref("taskspec-json", "file", packet_dir / "TASKSPEC.json", required=True),
        _source_ref("taskspec-md", "file", packet_dir / "TASKSPEC.md", required=False),
    ]
    return [ref for ref in refs if ref]


def _source_ref(ref_id: str, kind: str, path: Path, *, required: bool) -> dict[str, Any]:
    ref: dict[str, Any] = {
        "ref_id": ref_id,
        "kind": kind,
        "uri": str(path),
        "included": True,
        "required": required,
        "freshness_state": "current",
        "producer_role": "coordinator",
        "observed_at": _utc_now(),
    }
    content_hash = _file_digest(path)
    if content_hash:
        ref["content_hash"] = content_hash
    return ref


def _ledger_source_ref(ref: dict[str, Any]) -> dict[str, Any]:
    result = {
        "ref_id": str(ref.get("ref_id") or ""),
        "kind": str(ref.get("kind") or "artifact"),
        "uri": str(ref.get("uri") or ""),
    }
    content_hash = str(ref.get("content_hash") or "")
    if content_hash:
        result["content_hash"] = content_hash
    return result


def _context_packet_id(packet_id: str) -> str:
    return f"cp-{_safe_context_token(packet_id)}"


def _context_ledger_id(packet_id: str) -> str:
    return f"cl-{_safe_context_token(packet_id)}"


def _safe_context_token(value: object) -> str:
    token = re.sub(r"[^A-Za-z0-9._-]+", "-", str(value or "").strip())
    return token.strip("-._") or "unknown"


def _digest_json(data: object) -> str:
    payload = json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return "sha256:" + sha256(payload.encode("utf-8")).hexdigest()


def _file_digest(path: Path) -> str:
    try:
        if path.is_file():
            return "sha256:" + sha256(path.read_bytes()).hexdigest()
    except OSError:
        return ""
    return ""


def _extract_status(text: str) -> str:
    capture_next = False
    for line in text.splitlines():
        stripped = line.strip()
        if capture_next:
            if not stripped:
                continue
            status = _normalize_report_status(stripped)
            return status or "unknown"
        status = _normalize_report_status(stripped)
        if status:
            return status
        if _is_report_section_header(stripped, "status"):
            capture_next = True
    return "unknown"


def _extract_changed_files(text: str) -> list[str]:
    changed: list[str] = []
    capture = False
    for line in text.splitlines():
        stripped = line.strip()
        if _is_report_section_header(stripped, "changed files"):
            capture = True
            inline_value = _inline_section_value(stripped)
            if inline_value and not _is_no_changed_files(inline_value):
                changed.append(inline_value.strip("` "))
            continue
        if capture and (
            stripped.startswith("#")
            or (stripped.startswith("- **") and "changed files" not in stripped.lower())
        ):
            break
        if capture and stripped:
            for item in _changed_file_items(stripped):
                if item and not _is_no_changed_files(item):
                    changed.append(item)
    return changed


def _changed_file_items(value: str) -> list[str]:
    candidate = value.lstrip("- ").strip()
    if _is_no_changed_files(candidate):
        return []
    parts = candidate.split("`")
    if len(parts) >= 2 and _looks_like_path(parts[0]):
        return [parts[0].strip()]
    match = re.search(r"`([^`]+)`", candidate)
    if match:
        return [match.group(1).strip()]
    candidate = candidate.strip("` ")
    for separator in (" — ", " – ", " - ", " -> ", " => "):
        if separator in candidate:
            candidate = candidate.split(separator, 1)[0].strip()
            break
    return [candidate]


def _looks_like_path(value: object) -> bool:
    text = str(value or "").strip()
    if not text:
        return False
    name = text.replace("\\", "/").rsplit("/", 1)[-1]
    return "/" in text.replace("\\", "/") or "." in name


def _normalize_report_status(value: str) -> str:
    candidate = _inline_section_value(value) or value
    token = candidate.strip().strip("`* ").lower().split()
    if not token:
        return ""
    status = token[0].strip("`*:,.;")
    if status in {"pass", "passed", "completed", "success", "succeeded"}:
        return "passed"
    if status in {"blocked", "failed", "fail", "human_required"}:
        return status
    return ""


def _is_report_section_header(line: str, section: str) -> bool:
    normalized = line.strip().lstrip("-").lstrip("#").strip()
    normalized = normalized.replace("*", "").strip().lower()
    section = section.lower()
    return normalized == section or normalized.startswith(f"{section}:")


def _inline_section_value(line: str) -> str:
    normalized = line.strip().lstrip("-").lstrip("#").strip()
    normalized = normalized.replace("*", "").strip()
    if ":" not in normalized:
        return ""
    return normalized.split(":", 1)[1].strip()


def _is_no_changed_files(value: str) -> bool:
    normalized = value.strip().strip("` ").lower()
    if normalized.startswith(("none.", "none,", "none;")):
        return True
    if (
        "no project files were modified" in normalized
        or "no project files were changed" in normalized
        or "no files were changed" in normalized
    ):
        return True
    if ":" in normalized:
        label, detail = [part.strip().strip("` ") for part in normalized.split(":", 1)]
        if label in {"project files", "project file changes"} and detail in {"none", "(none)", "no changes", "n/a"}:
            return True
        if label in {"report", "execution report", "artifact", "artifacts"}:
            return True
    return normalized in {"none", "(none)", "unknown", "(unknown)", "no changes", "n/a"}


def _extract_verification(text: str) -> str:
    lowered = text.lower()
    marker = "verification"
    index = lowered.find(marker)
    if index == -1:
        index = lowered.find("evidence")
    if index == -1:
        return ""
    return text[index:index + 1000].strip()
