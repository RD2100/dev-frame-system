"""Runtime event journal for rdgoal.

The journal is local runtime state and is intentionally kept outside the public
repository tree.
"""
from __future__ import annotations

import json
import time
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .backup_guard import default_runtime_dir, is_inside


@dataclass
class JournalEvent:
    event_type: str
    project_id: str
    payload: dict[str, Any]
    timestamp: str = ""
    event_id: str = ""

    def __post_init__(self) -> None:
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()
        if not self.event_id:
            self.event_id = f"{self.project_id}-{int(time.time() * 1000)}-{uuid.uuid4().hex[:6]}"


class RuntimeStore:
    def __init__(self, runtime_dir: str | Path | None = None,
                 repo_root: str | Path | None = None) -> None:
        self.runtime_dir = Path(runtime_dir).resolve() if runtime_dir else default_runtime_dir()
        self.repo_root = Path(repo_root).resolve() if repo_root else None
        self.path = self.runtime_dir / "rdgoal-events.jsonl"

    def append(self, event: JournalEvent) -> str:
        if self.repo_root and is_inside(self.runtime_dir, self.repo_root):
            raise ValueError("Runtime store must not be inside the public repository.")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(asdict(event), ensure_ascii=True) + "\n")
        return event.event_id

    def read_all(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        events: list[dict[str, Any]] = []
        with self.path.open(encoding="utf-8") as handle:
            for line in handle:
                stripped = line.strip()
                if not stripped:
                    continue
                try:
                    events.append(json.loads(stripped))
                except json.JSONDecodeError:
                    continue
        return events
