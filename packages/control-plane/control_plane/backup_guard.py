"""Rollback snapshots for snapshot-backed rdgoal actions."""
from __future__ import annotations

import json
import os
import shutil
import time
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .decision_engine import Decision, DecisionMode


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def default_runtime_dir() -> Path:
    env = os.environ.get("DEVFRAME_RUNTIME_DIR")
    if env:
        return Path(env).expanduser().resolve()
    return (Path.home() / ".devframe-runtime").resolve()


def is_inside(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


@dataclass
class SnapshotResult:
    ok: bool
    method: str
    reference: str
    detail: str = ""


@dataclass
class GuardResult:
    allowed: bool
    decision_mode: str
    reason: str
    snapshot: SnapshotResult | None = None
    log_entry_id: str | None = None


class BackupGuard:
    """Create file snapshots outside the repository before risky local actions."""

    def __init__(self, project_id: str, project_root: str | Path,
                 runtime_dir: str | Path | None = None) -> None:
        self.project_id = project_id
        self.project_root = Path(project_root).resolve()
        self.runtime_dir = Path(runtime_dir).resolve() if runtime_dir else default_runtime_dir()
        self.project_runtime = self.runtime_dir / project_id
        self.snapshot_dir = self.project_runtime / "snapshots"
        self.log_path = self.project_runtime / "rollback-log.jsonl"

    def guard(self, decision: Decision, targets: list[str]) -> GuardResult:
        if decision.mode == DecisionMode.HARD_STOP:
            return GuardResult(False, decision.mode.value, decision.reason)
        if decision.mode == DecisionMode.DRAFT_ONLY:
            return GuardResult(False, decision.mode.value, decision.reason)
        if not decision.requires_snapshot:
            return GuardResult(True, decision.mode.value, decision.reason)
        if not targets:
            return GuardResult(
                False,
                decision.mode.value,
                "Snapshot-backed actions require at least one explicit target.",
            )

        snapshot = self.create_snapshot(targets)
        if not snapshot.ok:
            return GuardResult(False, decision.mode.value, "Snapshot failed; dispatch blocked.", snapshot)
        entry_id = self.append_log(decision=decision, targets=targets, snapshot=snapshot)
        return GuardResult(True, decision.mode.value, decision.reason, snapshot, entry_id)

    def create_snapshot(self, targets: list[str]) -> SnapshotResult:
        if is_inside(self.runtime_dir, self.project_root):
            return SnapshotResult(False, "none", "", "Runtime dir must stay outside the project repo.")

        stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        destination = self.snapshot_dir / stamp
        try:
            resolved_targets: list[tuple[Path, Path]] = []
            for target in targets:
                source = Path(target)
                if not source.is_absolute():
                    source = self.project_root / source
                resolved = source.resolve()
                relative = resolved.relative_to(self.project_root)
                resolved_targets.append((resolved, relative))

            destination.mkdir(parents=True, exist_ok=True)
            copied = 0
            for source, relative in resolved_targets:
                if not source.exists():
                    continue
                dest = destination / relative
                dest.parent.mkdir(parents=True, exist_ok=True)
                if source.is_dir():
                    shutil.copytree(source, dest, dirs_exist_ok=True)
                else:
                    shutil.copy2(source, dest)
                copied += 1
            return SnapshotResult(True, "file_archive", str(destination), f"archived {copied} target(s)")
        except (OSError, ValueError) as exc:
            return SnapshotResult(False, "file_archive", str(destination), str(exc))

    def append_log(self, *, decision: Decision, targets: list[str],
                   snapshot: SnapshotResult) -> str:
        self.project_runtime.mkdir(parents=True, exist_ok=True)
        entry_id = f"{self.project_id}-{int(time.time() * 1000)}-{uuid.uuid4().hex[:6]}"
        entry: dict[str, Any] = {
            "id": entry_id,
            "project_id": self.project_id,
            "timestamp": utc_now(),
            "operation": decision.operation,
            "decision_mode": decision.mode.value,
            "targets": targets,
            "auto_approved": True,
            "snapshot": asdict(snapshot),
            "reason": decision.reason,
        }
        with self.log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, ensure_ascii=True) + "\n")
        return entry_id

    def read_log(self) -> list[dict[str, Any]]:
        if not self.log_path.exists():
            return []
        with self.log_path.open(encoding="utf-8") as handle:
            return [json.loads(line) for line in handle if line.strip()]
