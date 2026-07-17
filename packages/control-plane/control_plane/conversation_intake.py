"""Durable human-message intake for DevFrame coordinator conversations."""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .backup_guard import default_runtime_dir


DEVFRAME_LOCAL_ENVIRONMENT_ID = "devframe-local"
GLOBAL_COORDINATOR_THREAD_ID = "devframe-team-workbench-session"
_MAX_ID_LENGTH = 256
_MAX_MESSAGE_BYTES = 64 * 1024
_JOURNAL_LOCK = threading.RLock()


class IntakeError(Exception):
    """The conversation intake request or journal is invalid."""


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _validate_text(value: object, field: str, *, required: bool = True) -> str:
    text = str(value or "").strip()
    if required and not text:
        raise IntakeError(f"missing_{field}")
    if len(text) > _MAX_ID_LENGTH:
        raise IntakeError(f"invalid_{field}")
    return text


def _thread_dir(runtime_dir: str | Path | None, thread_id: str) -> Path:
    root = Path(runtime_dir).resolve() if runtime_dir is not None else default_runtime_dir()
    storage_key = hashlib.sha256(thread_id.encode("utf-8")).hexdigest()
    return root / "conversation-intakes" / storage_key


def _event_id(thread_id: str, client_request_id: str) -> str:
    digest = hashlib.sha256(f"{thread_id}\0{client_request_id}".encode("utf-8")).hexdigest()
    return f"ci-{digest[:24]}"


def _event_path(runtime_dir: str | Path | None, thread_id: str, event_id: str) -> Path:
    return _thread_dir(runtime_dir, thread_id) / f"{event_id}.json"


def _read_event(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise IntakeError("journal_corrupt") from exc
    if not isinstance(payload, dict):
        raise IntakeError("journal_corrupt")
    return payload


def _publish_once(path: Path, payload: dict[str, Any]) -> bool:
    """Atomically publish a complete event without replacing an existing one."""
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(payload, handle, indent=2, ensure_ascii=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(temporary_path, path)
        except FileExistsError:
            return False
        return True
    finally:
        temporary_path.unlink(missing_ok=True)


def _resolve_thread(runtime_dir: str | Path | None, thread_id: str) -> tuple[str, str]:
    if thread_id == GLOBAL_COORDINATOR_THREAD_ID:
        return "global_coordinator", ""

    try:
        from .cluster_run import list_cluster_runs

        for run in list_cluster_runs(runtime_dir):
            if str(run.get("runId") or "") == thread_id:
                return "goal_conversation", str(run.get("projectId") or "")

        from .visual_state import build_visual_control_plane_state

        state = build_visual_control_plane_state(runtime_dir)
        for session in state.get("sessions", []):
            if not isinstance(session, dict):
                continue
            is_goal_conversation = bool(
                str(session.get("run_id") or "").strip()
                or str(session.get("task_spec_id") or "").strip()
            )
            if str(session.get("session_id") or "") == thread_id and is_goal_conversation:
                return "goal_conversation", str(session.get("project_id") or "")
    except IntakeError:
        raise
    except Exception as exc:  # noqa: BLE001 - resolution failure is a distinct API outcome
        raise IntakeError("resolution_failed") from exc
    raise IntakeError("unknown_thread")


def record_intake(
    runtime_dir: str | Path | None,
    thread_id: object,
    project_id: object,
    client_request_id: object,
    message: object,
    *,
    environment_id: object,
) -> dict[str, Any]:
    """Validate and persist one idempotent human message."""
    tid = _validate_text(thread_id, "thread_id")
    request_id = _validate_text(client_request_id, "client_request_id")
    project = _validate_text(project_id, "project_id", required=False)
    text = str(message or "")
    if not text.strip():
        raise IntakeError("empty_message")
    if len(text.encode("utf-8")) > _MAX_MESSAGE_BYTES:
        raise IntakeError("message_too_large")
    if str(environment_id or "") != DEVFRAME_LOCAL_ENVIRONMENT_ID:
        raise IntakeError("environment_id_missing_or_mismatch")

    thread_kind, bound_project = _resolve_thread(runtime_dir, tid)
    if thread_kind == "goal_conversation":
        if not project:
            raise IntakeError("project_id_required_for_goal")
        if project != bound_project:
            raise IntakeError("project_id_mismatch")

    event_id = _event_id(tid, request_id)
    path = _event_path(runtime_dir, tid, event_id)
    with _JOURNAL_LOCK:
        existing = _read_event(path)
        if existing is None:
            proposed = {
                "eventId": event_id,
                "threadId": tid,
                "projectId": project,
                "clientRequestId": request_id,
                "threadKind": thread_kind,
                "message": text,
                "status": "accepted",
                "environmentId": DEVFRAME_LOCAL_ENVIRONMENT_ID,
                "createdAt": _now_iso(),
            }
            if _publish_once(path, proposed):
                existing = proposed
            else:
                existing = _read_event(path)
                if existing is None:
                    raise IntakeError("journal_corrupt")

    return {
        "accepted": True,
        "threadId": tid,
        "projectId": existing.get("projectId", project),
        "eventId": event_id,
        "status": existing.get("status", "accepted"),
    }


def get_thread_intakes(
    runtime_dir: str | Path | None,
    thread_id: str,
) -> list[dict[str, Any]]:
    directory = _thread_dir(runtime_dir, thread_id)
    if not directory.is_dir():
        return []
    events = [_read_event(path) for path in directory.glob("ci-*.json")]
    return sorted(
        (event for event in events if event is not None),
        key=lambda event: (str(event.get("createdAt") or ""), str(event.get("eventId") or "")),
    )


def build_intake_activities(
    runtime_dir: str | Path | None,
    thread_id: str,
    updated_at: str,
) -> list[dict[str, Any]]:
    return [
        {
            "id": f"{thread_id}-intake-{event.get('eventId', '')}",
            "tone": "info",
            "kind": "devframe.intake.accepted",
            "summary": str(event.get("message") or ""),
            "payload": {
                "eventId": event.get("eventId", ""),
                "threadId": event.get("threadId", ""),
                "projectId": event.get("projectId", ""),
                "threadKind": event.get("threadKind", ""),
                "status": event.get("status", ""),
                "environmentId": event.get("environmentId", ""),
                "createdAt": event.get("createdAt", ""),
                "writePolicy": "read-only",
            },
            "turnId": None,
            "sequence": 0,
            "createdAt": event.get("createdAt", updated_at),
        }
        for event in get_thread_intakes(runtime_dir, thread_id)
    ]
