"""Propose, confirm, start, cancel, and track editor cluster runs.

Conversational input is non-executing by default. A development goal starts only
after the client returns a server-issued, exact-binding, expiring, single-use
confirmation with ``decision=execute``. Started work can be cancelled through a
durable marker that propagates to the command worker; cancellation stops work
but never rolls project changes back.

The actual workflow invocation is isolated behind ``_run_cluster_workflow`` so
tests can verify the start/track path without spawning a real, token-spending
run.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import threading
import time
import weakref
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .cluster_control import _slug, is_valid_cluster_target
from .project_contract import slugify_project_id
from .t3_adapter import _workspace_root
from .visual_state import build_visual_control_plane_state


class ClusterRunError(Exception):
    def __init__(
        self,
        message: str,
        *,
        error_code: str = "cluster_run_rejected",
        status_code: int = 400,
    ) -> None:
        super().__init__(message)
        self.error_code = error_code
        self.status_code = status_code


def _normalize_local_path(raw: str) -> str:
    """Normalize a project path coming from the editor (web/Electron).

    The renderer can hand us paths in forms that Python's ``Path`` does not
    resolve on Windows, e.g. ``file:///D:/proj`` or a leading-slash drive path
    ``/D:/proj``. Normal native paths (``D:\\proj`` / ``D:/proj`` / POSIX
    absolute) pass through unchanged.
    """
    text = str(raw or "").strip()
    if not text:
        return ""
    if text.lower().startswith("file://"):
        from urllib.parse import unquote, urlparse

        parsed = urlparse(text)
        text = unquote(parsed.path or "")
    # "/D:/proj" or "/D:\\proj" -> "D:/proj"
    if len(text) >= 3 and text[0] == "/" and text[1].isalpha() and text[2] == ":":
        text = text[1:]
    return text


_ACTIVE_STATUSES = {"running", "started", "cancel_requested"}
_RUN_LOCKS_GUARD = threading.Lock()
_RUN_LOCKS: weakref.WeakValueDictionary[str, Any] = weakref.WeakValueDictionary()


def _run_lock(run_id: str) -> Any:
    rid = _slug(run_id)
    with _RUN_LOCKS_GUARD:
        lock = _RUN_LOCKS.get(rid)
        if lock is None:
            lock = threading.RLock()
            _RUN_LOCKS[rid] = lock
        return lock


def _resolve_project_reference(
    runtime_dir: str | Path | None,
    project_ref: str,
    *,
    paper_project_dirs: list[str | Path] | None = None,
) -> tuple[str, str]:
    """Resolve a client-supplied project reference to (workspace path, project id).

    The editor should eventually send stable project ids, but for backward
    compatibility this helper still accepts local paths. Resolution order:

    1. exact project id from the current control-plane state;
    2. exact workspace root path from the current control-plane state;
    3. raw local path when it points at a real directory.
    """
    raw = str(project_ref or "").strip()
    if not raw:
        return "", ""

    normalized = _normalize_local_path(raw)
    normalized_dir = ""
    if normalized:
        candidate = Path(normalized)
        if candidate.is_dir():
            normalized_dir = str(candidate.resolve())

    try:
        state = (
            build_visual_control_plane_state(runtime_dir)
            if paper_project_dirs is None
            else build_visual_control_plane_state(
                runtime_dir,
                paper_project_dirs=paper_project_dirs,
            )
        )
        for project in state.get("projects", []):
            if not isinstance(project, dict):
                continue
            project_id = str(project.get("project_id") or "").strip()
            workspace_root = _workspace_root(project)
            workspace_root_text = str(Path(workspace_root).resolve()) if workspace_root else ""
            if raw and project_id == raw and workspace_root_text:
                return workspace_root_text, project_id
            if normalized_dir and workspace_root_text and workspace_root_text == normalized_dir:
                return workspace_root_text, project_id or slugify_project_id(workspace_root_text)
    except Exception:  # noqa: BLE001 - advisory lookup only; fall back to path mode
        pass

    if normalized_dir:
        return normalized_dir, slugify_project_id(normalized_dir)
    return "", raw


def _pid_alive(pid: int) -> bool:
    """Best-effort check that a process id is still running (cross-platform)."""
    if not isinstance(pid, int) or pid <= 0:
        return False
    if os.name == "nt":
        import ctypes

        process_query_limited_information = 0x1000
        still_active = 259
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.OpenProcess(process_query_limited_information, False, pid)
        if not handle:
            return False
        try:
            exit_code = ctypes.c_ulong()
            if not kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
                return False
            return exit_code.value == still_active
        finally:
            kernel32.CloseHandle(handle)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def _reconcile_orphaned_run(
    runtime_dir: str | Path | None, record: dict[str, Any]
) -> dict[str, Any]:
    """Mark an active run as interrupted if the process that drove it is gone.

    A cluster run executes in a background thread inside the control-plane
    (dashboard) process. If that process exits before the run finishes — most
    commonly because the editor was relaunched — the thread dies with it and the
    durable record is left stuck at "running" forever. There is no way to resume
    that thread, so on read we honestly downgrade such orphaned runs to
    "interrupted" instead of showing a frozen "running" state.
    """
    run_id = str(record.get("runId") or "")
    status = str(record.get("status") or "").lower()
    if (
        status in _ACTIVE_STATUSES
        and not record.get("finishedAt")
        and _cancellation_marker_path(runtime_dir, run_id).is_file()
        and not (
            isinstance(record.get("ownerPid"), int)
            and _pid_alive(record["ownerPid"])
        )
    ):
        updated = dict(record)
        updated["status"] = "cancelled"
        updated["summary"] = (
            "Run cancelled. Cancellation is not rollback; inspect the project diff "
            "for partial changes."
        )
        updated["finishedAt"] = _now()
        try:
            _write_run_record(runtime_dir, updated)
        except OSError:
            pass
        return updated
    if status not in _ACTIVE_STATUSES or record.get("finishedAt"):
        return record
    owner = record.get("ownerPid")
    if isinstance(owner, int) and _pid_alive(owner):
        return record
    updated = dict(record)
    updated["status"] = "interrupted"
    updated["summary"] = (
        "运行已中断：在完成前控制台进程已停止（例如编辑器被重新启动）。"
        "重新发送该目标即可重新开始。"
    )
    updated["finishedAt"] = _now()
    try:
        _write_run_record(runtime_dir, updated)
    except OSError:
        pass
    return updated


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_run_id() -> str:
    return "g-" + secrets.token_hex(8)


def _new_proposal_id() -> str:
    return "crp-" + secrets.token_hex(8)


def _runs_dir(runtime_dir: str | Path | None) -> Path:
    from .backup_guard import default_runtime_dir

    base = Path(runtime_dir).resolve() if runtime_dir else default_runtime_dir()
    return base / "cluster-runs"


def _proposals_dir(runtime_dir: str | Path | None) -> Path:
    return _runs_dir(runtime_dir).parent / "cluster-run-proposals"


def _cancellations_dir(runtime_dir: str | Path | None) -> Path:
    return _runs_dir(runtime_dir).parent / "cluster-run-cancellations"


def _cancellation_marker_path(
    runtime_dir: str | Path | None,
    run_id: str,
) -> Path:
    return _cancellations_dir(runtime_dir) / f"{_slug(run_id)}.json"


def _atomic_write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.parent / (path.name + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8")
    # Windows: os.replace can transiently fail with a sharing violation while a
    # concurrent reader briefly holds the destination open.
    for attempt in range(5):
        try:
            os.replace(tmp, path)
            return
        except PermissionError:
            if attempt == 4:
                raise
            time.sleep(0.01 * (2**attempt))


def _write_run_record(runtime_dir: str | Path | None, record: dict[str, Any]) -> None:
    run_id = str(record["runId"])
    with _run_lock(run_id):
        path = _runs_dir(runtime_dir) / f"{run_id}.json"
        marker_exists = _cancellation_marker_path(runtime_dir, run_id).is_file()
        existing: dict[str, Any] = {}
        if marker_exists and path.is_file():
            try:
                loaded = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(loaded, dict):
                    existing = loaded
            except (OSError, json.JSONDecodeError):
                existing = {}
        incoming = dict(record)
        existing_status = str(existing.get("status") or "").lower()
        incoming_status = str(incoming.get("status") or "").lower()
        if (
            marker_exists
            and existing_status in {"cancel_requested", "cancelled"}
            and incoming_status not in {"cancel_requested", "cancelled"}
        ):
            incoming["status"] = (
                "cancelled" if incoming.get("finishedAt") else existing_status
            )
            for key in ("cancelRequestedAt", "cancelRequestedBy"):
                if existing.get(key) and not incoming.get(key):
                    incoming[key] = existing[key]
        _atomic_write(path, incoming)


def propose_cluster_run(
    runtime_dir: str | Path | None,
    environment_id: str,
    project_path: str,
    target: str,
    goal: str,
    *,
    proposed_by: str = "rd-code-editor",
    ttl_seconds: int = 300,
    stable_run_id: str | None = None,
    source_proposal_id: str | None = None,
    source_turn_id: str | None = None,
    paper_project_dirs: list[str | Path] | None = None,
) -> dict[str, Any]:
    """Create a bound, expiring execution proposal without starting work."""
    from .conversation_intake import DEVFRAME_LOCAL_ENVIRONMENT_ID

    if not isinstance(environment_id, str) or environment_id != DEVFRAME_LOCAL_ENVIRONMENT_ID:
        raise ClusterRunError("invalid environment id")
    project_ref = project_path.strip() if isinstance(project_path, str) else ""
    text = goal.strip() if isinstance(goal, str) else ""
    tid = _slug(target) if isinstance(target, str) else ""
    path, project_id = _resolve_project_reference(
        runtime_dir,
        project_ref,
        paper_project_dirs=paper_project_dirs,
    )
    if not path:
        raise ClusterRunError("projectId is required")
    if not tid:
        raise ClusterRunError("target is required")
    if not text:
        raise ClusterRunError("goal is required")
    if not is_valid_cluster_target(runtime_dir, tid):
        raise ClusterRunError(f"unknown cluster target: {target}")
    stable_id = str(stable_run_id or "").strip()
    source_proposal = str(source_proposal_id or "").strip()
    source_turn = str(source_turn_id or "").strip()
    if any((stable_id, source_proposal, source_turn)) and not all(
        (stable_id, source_proposal, source_turn)
    ):
        raise ClusterRunError("incomplete stable run binding")
    if stable_id and (
        _slug(stable_id) != stable_id
        or not stable_id.startswith("g-")
        or _slug(source_proposal) != source_proposal
        or not source_proposal.startswith("ctp-")
        or not source_turn
    ):
        raise ClusterRunError("invalid stable run binding")

    now = datetime.now(timezone.utc)
    expires = now + timedelta(seconds=max(0, int(ttl_seconds)))
    proposal_id = _new_proposal_id()
    token = secrets.token_urlsafe(32)
    record = {
        "proposalId": proposal_id,
        "environmentId": environment_id,
        "projectRef": project_ref,
        "projectId": project_id,
        "projectPath": path,
        "target": tid,
        "goal": text,
        "proposedBy": str(proposed_by or "rd-code-editor"),
        "stableRunId": stable_id,
        "sourceProposalId": source_proposal,
        "sourceTurnId": source_turn,
        "tokenHash": hashlib.sha256(token.encode("utf-8")).hexdigest(),
        "createdAt": now.isoformat(),
        "expiresAt": expires.isoformat(),
        "status": "unused",
    }
    _atomic_write(_proposals_dir(runtime_dir) / f"{proposal_id}.json", record)
    return {
        "proposed": True,
        "started": False,
        "proposalId": proposal_id,
        "confirmationToken": token,
        "expiresAt": record["expiresAt"],
        "decisionRequired": "execute",
        **({"stableRunId": stable_id} if stable_id else {}),
        "binding": {
            "environmentId": environment_id,
            "projectId": project_ref,
            "resolvedProjectId": project_id,
            "projectPath": path,
            "target": tid,
            "goal": text,
        },
    }


def _consume_cluster_run_confirmation(
    runtime_dir: str | Path | None,
    *,
    environment_id: Any,
    project_ref: str,
    project_id: str,
    project_path: str,
    target: str,
    goal: str,
    proposal_id: Any,
    confirmation_token: Any,
    decision: Any,
    stable_run_id: str,
    source_proposal_id: str,
    source_turn_id: str,
) -> None:
    from .conversation_intake import DEVFRAME_LOCAL_ENVIRONMENT_ID

    if (
        not isinstance(environment_id, str)
        or environment_id != DEVFRAME_LOCAL_ENVIRONMENT_ID
        or not isinstance(proposal_id, str)
        or not proposal_id.startswith("crp-")
        or not isinstance(confirmation_token, str)
        or not confirmation_token
        or not isinstance(decision, str)
        or decision != "execute"
    ):
        raise ClusterRunError(
            "invalid execution confirmation",
            error_code="invalid_execution_confirmation",
        )

    directory = _proposals_dir(runtime_dir)
    safe_id = _slug(proposal_id)
    if safe_id != proposal_id:
        raise ClusterRunError(
            "execution confirmation rejected",
            error_code="execution_confirmation_rejected",
            status_code=409,
        )
    proposal_path = directory / f"{safe_id}.json"
    claim_path = directory / f"{safe_id}.used"
    if claim_path.exists():
        raise ClusterRunError(
            "execution confirmation already consumed",
            error_code="execution_confirmation_consumed",
            status_code=409,
        )
    try:
        proposal = json.loads(proposal_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        raise ClusterRunError(
            "execution confirmation rejected",
            error_code="execution_confirmation_rejected",
            status_code=409,
        ) from None
    expected = {
        "environmentId": environment_id,
        "projectRef": project_ref,
        "projectId": project_id,
        "projectPath": project_path,
        "target": target,
        "goal": goal,
        "stableRunId": stable_run_id,
        "sourceProposalId": source_proposal_id,
        "sourceTurnId": source_turn_id,
    }
    if any(proposal.get(key) != value for key, value in expected.items()):
        raise ClusterRunError(
            "execution confirmation rejected",
            error_code="execution_confirmation_rejected",
            status_code=409,
        )
    token_hash = hashlib.sha256(confirmation_token.encode("utf-8")).hexdigest()
    if not hmac.compare_digest(str(proposal.get("tokenHash") or ""), token_hash):
        raise ClusterRunError(
            "execution confirmation rejected",
            error_code="execution_confirmation_rejected",
            status_code=409,
        )
    try:
        expires_at = datetime.fromisoformat(str(proposal.get("expiresAt") or ""))
    except ValueError:
        raise ClusterRunError(
            "execution confirmation rejected",
            error_code="execution_confirmation_rejected",
            status_code=409,
        ) from None
    if expires_at.tzinfo is None or datetime.now(timezone.utc) >= expires_at:
        raise ClusterRunError(
            "execution confirmation expired",
            error_code="execution_confirmation_expired",
            status_code=409,
        )

    claim_payload = {
        "proposalId": proposal_id,
        "consumedAt": _now(),
        "decision": "execute",
    }
    try:
        file_descriptor = os.open(
            claim_path,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL,
            0o600,
        )
    except FileExistsError:
        raise ClusterRunError(
            "execution confirmation already consumed",
            error_code="execution_confirmation_consumed",
            status_code=409,
        ) from None
    with os.fdopen(file_descriptor, "w", encoding="utf-8") as handle:
        json.dump(claim_payload, handle, ensure_ascii=True)
        handle.flush()
        os.fsync(handle.fileno())
    proposal["status"] = "consumed"
    proposal["consumedAt"] = claim_payload["consumedAt"]
    _atomic_write(proposal_path, proposal)


def _load_run_record(runtime_dir: str | Path | None, run_id: str) -> dict[str, Any] | None:
    path = _runs_dir(runtime_dir) / f"{_slug(run_id)}.json"
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def list_cluster_runs(runtime_dir: str | Path | None) -> list[dict[str, Any]]:
    """Return all recorded cluster runs, newest first."""
    directory = _runs_dir(runtime_dir)
    if not directory.is_dir():
        return []
    runs: list[dict[str, Any]] = []
    for path in directory.glob("g-*.json"):
        try:
            runs.append(_reconcile_orphaned_run(runtime_dir, json.loads(path.read_text(encoding="utf-8"))))
        except (OSError, json.JSONDecodeError):
            continue
    runs.sort(key=lambda r: str(r.get("startedAt") or ""), reverse=True)
    return runs


def cancel_cluster_run(
    runtime_dir: str | Path | None,
    run_id: str,
    *,
    requested_by: str = "rd-code-editor",
) -> dict[str, Any]:
    """Request cancellation for an active run without rolling project changes back."""
    raw_id = str(run_id or "").strip()
    rid = _slug(raw_id)
    if not rid or rid != raw_id:
        raise ClusterRunError("invalid runId")
    with _run_lock(rid):
        record = _load_run_record(runtime_dir, rid)
        if record is None:
            raise ClusterRunError(
                "cluster run not found",
                error_code="cluster_run_not_found",
                status_code=404,
            )
        status = str(record.get("status") or "").lower()
        if status in {"cancel_requested", "cancelled"}:
            return record
        if status not in {"running", "started"}:
            raise ClusterRunError(
                f"cluster run is already terminal: {status or 'unknown'}",
                error_code="cluster_run_terminal",
                status_code=409,
            )
        go_run_id = str(record.get("goRunId") or "").strip()
        if go_run_id:
            try:
                from .go_dispatch import load_go_run_result

                go_status = str(
                    load_go_run_result(runtime_dir, go_run_id).status or ""
                ).lower()
            except (OSError, ValueError):
                go_status = ""
            if go_status == "cancelled":
                record["status"] = "cancelled"
                record["finishedAt"] = record.get("finishedAt") or _now()
                _write_run_record(runtime_dir, record)
                return record
            if go_status in {"passed", "failed", "blocked", "completed"}:
                raise ClusterRunError(
                    f"cluster run is already terminal: {go_status}",
                    error_code="cluster_run_terminal",
                    status_code=409,
                )
        requested_at = _now()
        requested_by_text = str(requested_by or "rd-code-editor").strip() or "rd-code-editor"
        marker = {
            "runId": rid,
            "status": "cancel_requested",
            "requestedAt": requested_at,
            "requestedBy": requested_by_text,
        }
        _atomic_write(_cancellation_marker_path(runtime_dir, rid), marker)
        record["status"] = "cancel_requested"
        record["cancelRequestedAt"] = requested_at
        record["cancelRequestedBy"] = requested_by_text
        record["summary"] = (
            "Cancellation requested; stopping active workers. Partial project changes "
            "may exist because cancellation is not rollback."
        )
        _write_run_record(runtime_dir, record)
        return record


def delete_cluster_run(runtime_dir: str | Path | None, run_id: str) -> bool:
    """Delete a recorded cluster run by id. Returns True if a record was removed.

    Only the durable run record under ``<runtime>/cluster-runs/`` is removed; the
    run id is slugified (alnum + dash only, so it cannot contain path
    separators) and the resolved path is confirmed to stay inside the runs
    directory before deletion. Deleting a missing run returns False (idempotent).
    """
    rid = _slug(run_id)
    if not rid:
        raise ClusterRunError("runId is required")
    directory = _runs_dir(runtime_dir)
    path = (directory / f"{rid}.json").resolve()
    if directory.resolve() not in path.parents:
        raise ClusterRunError("invalid runId")
    if not path.is_file():
        return False
    try:
        path.unlink()
    except OSError as exc:  # pragma: no cover - filesystem error path
        raise ClusterRunError(f"failed to delete run: {exc}") from exc
    return True


def rename_cluster_run(
    runtime_dir: str | Path | None, run_id: str, goal: str
) -> dict[str, Any]:
    """Rename a recorded run's goal (its human-facing title). Returns the record.

    Only the ``goal`` field is updated; the run id and execution linkage are
    unchanged. Raises :class:`ClusterRunError` when the run is missing or the new
    goal is empty.
    """
    rid = _slug(run_id)
    if not rid:
        raise ClusterRunError("runId is required")
    text = str(goal or "").strip()
    if not text:
        raise ClusterRunError("goal must not be empty")
    record = _load_run_record(runtime_dir, rid)
    if record is None:
        raise ClusterRunError("cluster run not found")
    record["goal"] = text
    _write_run_record(runtime_dir, record)
    return record


def _run_cluster_workflow(
    runtime_dir: str | Path | None,
    project_path: str,
    target: str,
    goal: str,
    run_id: str,
    on_prepared: Any = None,
    cancel_marker: str | Path | None = None,
) -> Any:
    """Real project-coordinator run. Module seam so tests can patch it.

    Runs the recorded plan -> execute -> review workflow and returns the
    ``WorkflowResult``. ``on_prepared(go_run_id)`` fires as soon as the
    coordinator has planned, so the run's events can be located live. This
    executes agents and can spend tokens; it only runs after consuming the
    matching server-issued confirmation.
    """
    from .workflow_engine import WorkflowEngine

    return WorkflowEngine(runtime_dir).run_coding_workflow(
        project_path,
        goal,
        on_prepared=on_prepared,
        cancel_marker=cancel_marker,
    )


def _run_and_record(
    runtime_dir: str | Path | None,
    project_path: str,
    target: str,
    goal: str,
    run_id: str,
) -> None:
    cancel_marker = _cancellation_marker_path(runtime_dir, run_id)

    def _on_prepared(go_run_id: str) -> None:
        rec = _load_run_record(runtime_dir, run_id)
        if rec is None:
            return
        rec["goRunId"] = str(go_run_id)
        rec["status"] = "running"
        rec["summary"] = "Coordinator planned the goal; agents are working…"
        _write_run_record(runtime_dir, rec)

    record = _load_run_record(runtime_dir, run_id) or {
        "runId": run_id, "target": target, "goal": goal, "projectPath": project_path,
    }
    try:
        result = _run_cluster_workflow(
            runtime_dir,
            project_path,
            target,
            goal,
            run_id,
            on_prepared=_on_prepared,
            cancel_marker=cancel_marker,
        )
        record = _load_run_record(runtime_dir, run_id) or record
        record["status"] = str(getattr(result, "status", None) or "completed")
        verdict = getattr(result, "verdict", None)
        passed = getattr(result, "passed_agents", None)
        failed = getattr(result, "failed_agents", None)
        go_run_id = getattr(result, "go_run_id", None)
        if go_run_id:
            record["goRunId"] = str(go_run_id)
        summary_parts = []
        if verdict:
            summary_parts.append(f"verdict={verdict}")
        if isinstance(passed, int) or isinstance(failed, int):
            summary_parts.append(f"{passed or 0} passed, {failed or 0} failed")
        record["summary"] = "; ".join(summary_parts) or "Run finished."
    except Exception as exc:  # noqa: BLE001 - record the failure honestly, never fake green
        record = _load_run_record(runtime_dir, run_id) or record
        record["status"] = "failed"
        record["summary"] = f"Run failed: {exc}"
    if (
        cancel_marker.is_file()
        or str(record.get("status") or "").lower() == "cancel_requested"
    ):
        record["status"] = "cancelled"
        record["summary"] = (
            "Run cancelled. Cancellation is not rollback; inspect the project diff "
            "for partial changes."
        )
    record["finishedAt"] = _now()
    _write_run_record(runtime_dir, record)


def cluster_run_detail(runtime_dir: str | Path | None, run_id: str) -> dict[str, Any]:
    """Return a run's record plus its coordination message timeline.

    The timeline is the team runtime's recorded coordinator<->agent messages for
    this run (and, when there are none yet, the recorded event log). This is the
    "主控 @agent 派任务 / agent -> 主控 结果" stream the goal detail view shows.
    """
    record = _load_run_record(runtime_dir, run_id)
    if record is None:
        raise ClusterRunError("cluster run not found")
    record = _reconcile_orphaned_run(runtime_dir, record)
    messages: list[dict[str, Any]] = []
    answer = str(record.get("coordinatorAnswer") or "")
    if answer:
        messages.append({
            "from": "coordinator",
            "to": "",
            "kind": "answer",
            "text": answer,
        })
    methodology = record.get("methodology") if isinstance(record.get("methodology"), dict) else None
    if methodology:
        constraints = []
        if methodology.get("readOnly"):
            constraints.append("只读")
        if methodology.get("networkEnabled"):
            constraints.append("允许联网")
        if methodology.get("requireRedGreenEvidence"):
            constraints.append("要求红绿证据")
        label = str(methodology.get("label") or methodology.get("id") or "")
        suffix = f"（{', '.join(constraints)}）" if constraints else ""
        messages.append({
            "from": "coordinator",
            "to": "",
            "kind": "methodology",
            "text": f"本次运行采用方法论 {label}{suffix}，将据此约束执行。",
        })
    go_run_id = _slug(record.get("goRunId"))
    if go_run_id:
        try:
            from .team_runtime import build_team_runtime_view

            view = build_team_runtime_view(runtime_dir)
        except Exception:
            view = {}
        bus = [m for m in view.get("message_bus", []) if _slug(m.get("run_id")) == go_run_id]
        for m in bus:
            messages.append({
                "from": str(m.get("from_role") or ""),
                "to": str(m.get("to_role") or ""),
                "kind": str(m.get("kind") or ""),
                "text": str(m.get("summary") or ""),
            })
        if not messages:
            for e in view.get("event_log", []):
                if _slug(e.get("run_id")) != go_run_id:
                    continue
                messages.append({
                    "from": "system",
                    "to": "",
                    "kind": str(e.get("kind") or ""),
                    "text": str(e.get("summary") or ""),
                })
    return {
        "runId": record.get("runId"),
        "goRunId": record.get("goRunId"),
        "target": record.get("target"),
        "goal": record.get("goal"),
        "status": record.get("status"),
        "summary": record.get("summary"),
        "messages": messages,
        "agents": _agent_summaries(runtime_dir, go_run_id),
        **({"methodology": methodology} if methodology else {}),
    }


def _slug_or_empty(value: Any) -> str:
    try:
        return _slug(value)
    except Exception:  # noqa: BLE001
        return ""


def _load_go_agents(runtime_dir: str | Path | None, go_run_id: str) -> list[Any]:
    """Load the underlying go-run's agent dispatch records, or [] if unavailable."""
    if not go_run_id:
        return []
    try:
        from .go_dispatch import load_go_run_result

        result = load_go_run_result(runtime_dir or "", go_run_id)
    except Exception:  # noqa: BLE001 - drill-down is best-effort, never breaks the run view
        return []
    return list(getattr(result, "agents", []) or [])


def _agent_status(agent: Any) -> str:
    return str(
        getattr(agent, "worker_status", "") or getattr(agent, "status", "") or "queued"
    )


def _agent_summaries(runtime_dir: str | Path | None, go_run_id: str) -> list[dict[str, Any]]:
    """Per-agent summary cards for the goal detail view (click to drill in)."""
    agents = _load_go_agents(runtime_dir, go_run_id)
    summaries: list[dict[str, Any]] = []
    for agent in agents:
        changed = list(getattr(agent, "changed_files", []) or [])
        summaries.append({
            "agentId": str(getattr(agent, "agent_id", "") or ""),
            "role": "executor",
            "shardIndex": int(getattr(agent, "shard_index", 0) or 0),
            "shardCount": int(getattr(agent, "shard_count", 0) or 0),
            "status": _agent_status(agent),
            "changedFileCount": len(changed),
            "totalTokens": int(getattr(agent, "total_tokens", 0) or 0),
        })
    return summaries


def cluster_run_agent_detail(
    runtime_dir: str | Path | None, run_id: str, agent_id: str
) -> dict[str, Any]:
    """Return one agent's detailed execution view (the agent drill-down).

    Surfaces what the worker actually did: status, changed files, token/cost
    accounting, tool calls, and the Markdown ExecutionReport it wrote. This is
    the "点进编码agent 看详细思考/执行过程" surface.
    """
    record = _load_run_record(runtime_dir, run_id)
    if record is None:
        raise ClusterRunError("cluster run not found")
    go_run_id = _slug_or_empty(record.get("goRunId"))
    wanted = str(agent_id or "").strip()
    agent = None
    for candidate in _load_go_agents(runtime_dir, go_run_id):
        if str(getattr(candidate, "agent_id", "") or "") == wanted:
            agent = candidate
            break
    if agent is None:
        raise ClusterRunError("agent not found")

    report_markdown = ""
    report_path = str(getattr(agent, "report_path", "") or "")
    if report_path:
        try:
            report_markdown = Path(report_path).read_text(encoding="utf-8")
        except OSError:
            report_markdown = ""

    tool_calls = getattr(agent, "tool_calls", None)
    if not isinstance(tool_calls, list):
        tool_calls = []

    return {
        "runId": record.get("runId"),
        "goRunId": record.get("goRunId"),
        "agentId": str(getattr(agent, "agent_id", "") or ""),
        "role": "executor",
        "shardIndex": int(getattr(agent, "shard_index", 0) or 0),
        "shardCount": int(getattr(agent, "shard_count", 0) or 0),
        "status": _agent_status(agent),
        "changedFiles": list(getattr(agent, "changed_files", []) or []),
        "verification": str(getattr(agent, "verification", "") or ""),
        "sessionId": str(getattr(agent, "session_id", "") or ""),
        "modelProvider": str(getattr(agent, "model_provider", "") or ""),
        "inputTokens": int(getattr(agent, "input_tokens", 0) or 0),
        "outputTokens": int(getattr(agent, "output_tokens", 0) or 0),
        "totalTokens": int(getattr(agent, "total_tokens", 0) or 0),
        "cost": float(getattr(agent, "cost", 0.0) or 0.0),
        "toolCalls": tool_calls,
        "reportMarkdown": report_markdown,
    }


def start_cluster_run(
    runtime_dir: str | Path | None,
    project_path: str,
    target: str,
    goal: str,
    *,
    proposed_by: str = "rd-code-editor",
    environment_id: str | None = None,
    proposal_id: str | None = None,
    confirmation_token: str | None = None,
    decision: str | None = None,
    stable_run_id: str | None = None,
    source_proposal_id: str | None = None,
    source_turn_id: str | None = None,
    paper_project_dirs: list[str | Path] | None = None,
) -> dict[str, Any]:
    """Validate + start a background project-coordinator run. Returns immediately."""
    path, project_id = _resolve_project_reference(
        runtime_dir,
        project_path,
        paper_project_dirs=paper_project_dirs,
    )
    text = str(goal or "").strip()
    tid = _slug(target)
    if not path:
        raise ClusterRunError("projectId is required")
    if not tid:
        raise ClusterRunError("target is required")
    if not text:
        raise ClusterRunError("goal is required")
    if not is_valid_cluster_target(runtime_dir, tid):
        raise ClusterRunError(f"unknown cluster target: {target}")
    stable_id = str(stable_run_id or "").strip()
    source_proposal = str(source_proposal_id or "").strip()
    source_turn = str(source_turn_id or "").strip()
    if any((stable_id, source_proposal, source_turn)) and not all(
        (stable_id, source_proposal, source_turn)
    ):
        raise ClusterRunError(
            "incomplete stable run binding",
            error_code="stable_run_binding_rejected",
            status_code=409,
        )
    if stable_id and (
        _slug(stable_id) != stable_id
        or not stable_id.startswith("g-")
        or _slug(source_proposal) != source_proposal
        or not source_proposal.startswith("ctp-")
        or not source_turn
    ):
        raise ClusterRunError(
            "invalid stable run binding",
            error_code="stable_run_binding_rejected",
            status_code=409,
        )
    run_id = stable_id or _new_run_id()
    if stable_id:
        existing = _load_run_record(runtime_dir, stable_id)
        if existing is not None:
            expected = {
                "runId": stable_id,
                "target": tid,
                "goal": text,
                "projectId": project_id,
                "projectPath": path,
            }
            if any(existing.get(key) != value for key, value in expected.items()):
                raise ClusterRunError(
                    "stable run binding conflict",
                    error_code="stable_run_conflict",
                    status_code=409,
                )
            for key, value in (
                ("sourceProposalId", source_proposal),
                ("sourceTurnId", source_turn),
            ):
                if existing.get(key) not in {None, "", value}:
                    raise ClusterRunError(
                        "stable run source conflict",
                        error_code="stable_run_conflict",
                        status_code=409,
                    )
                existing[key] = value
            _write_run_record(runtime_dir, existing)
            return {
                "started": existing.get("kind") != "conversation",
                "replayed": True,
                "runId": stable_id,
                "target": tid,
                "goal": text,
                "projectId": project_id,
                "projectPath": path,
                "conversationKind": "goal_conversation",
                "coordinatorScope": "project",
                "projectBinding": {
                    "mode": "required",
                    "projectId": project_id,
                    "projectPath": path,
                    "status": "bound",
                },
            }

    # Phase C triage: a conversational goal (e.g. "你好" / "你能做什么") is
    # answered directly by the coordinator — no coding agents, no token spend.
    from .goal_triage import (
        GOAL_KIND_CONVERSATION,
        classify_goal,
        coordinator_conversation_reply,
    )

    confirmation_supplied = any(
        value is not None
        for value in (environment_id, proposal_id, confirmation_token, decision)
    )
    if classify_goal(text) == GOAL_KIND_CONVERSATION and not confirmation_supplied:
        conversation_kind = "global_coordinator" if tid == "coordinator" else "native_chat"
        reply = coordinator_conversation_reply(text)
        record = {
            "runId": run_id,
            "target": tid,
            "goal": text,
            "projectId": project_id,
            "projectPath": path,
            "proposedBy": str(proposed_by or "rd-code-editor"),
            "ownerPid": os.getpid(),
            "kind": "conversation",
            "status": "answered",
            "summary": "主控已直接回复（对话，未派发智能体）。",
            "coordinatorAnswer": reply,
            "startedAt": _now(),
            "finishedAt": _now(),
        }
        _write_run_record(runtime_dir, record)
        return {
            "started": False,
            "runId": run_id,
            "target": tid,
            "goal": text,
            "projectId": project_id,
            "projectPath": path,
            "kind": "conversation",
            "conversationKind": conversation_kind,
            "coordinatorScope": "global" if conversation_kind == "global_coordinator" else "none",
            "projectBinding": {
                "mode": "optional" if conversation_kind == "global_coordinator" else "none",
                "projectId": project_id,
                "projectPath": path,
                "status": "bound",
            },
            "answer": reply,
        }
    if not confirmation_supplied:
        raise ClusterRunError(
            "execution confirmation required",
            error_code="execution_confirmation_required",
            status_code=409,
        )
    project_ref = project_path.strip() if isinstance(project_path, str) else ""
    _consume_cluster_run_confirmation(
        runtime_dir,
        environment_id=environment_id,
        project_ref=project_ref,
        project_id=project_id,
        project_path=path,
        target=tid,
        goal=text,
        proposal_id=proposal_id,
        confirmation_token=confirmation_token,
        decision=decision,
        stable_run_id=stable_id,
        source_proposal_id=source_proposal,
        source_turn_id=source_turn,
    )

    # Resolve the methodology (built-in @trigger or a user-created custom skill)
    # that governs this run, so it is recorded and shown in the detail view.
    # go_dispatch re-resolves the same way (runtime-aware), so the executor
    # packet carries the same constraints.
    methodology_summary: dict[str, Any] | None = None
    try:
        from .methodology_dispatch import resolve_methodology

        _effective, methodology = resolve_methodology(
            text, runtime_dir=runtime_dir, project_id=project_id
        )
        if methodology:
            methodology_summary = {
                "id": str(methodology.get("skill_id") or ""),
                "label": str(methodology.get("display_label") or methodology.get("title") or ""),
                "readOnly": bool(methodology.get("read_only")),
                "networkEnabled": bool(methodology.get("network_enabled")),
                "requireRedGreenEvidence": bool(methodology.get("require_red_green_evidence")),
            }
    except Exception:  # noqa: BLE001 - advisory metadata, never blocks the run
        methodology_summary = None

    record = {
        "runId": run_id,
        "target": tid,
        "goal": text,
        "projectId": project_id,
        "projectPath": path,
        "proposedBy": str(proposed_by or "rd-code-editor"),
        "ownerPid": os.getpid(),
        "status": "running",
        "summary": "Coordinator received the goal; starting…",
        "startedAt": _now(),
        **({"sourceProposalId": source_proposal} if source_proposal else {}),
        **({"sourceTurnId": source_turn} if source_turn else {}),
        **({"methodology": methodology_summary} if methodology_summary else {}),
    }
    _write_run_record(runtime_dir, record)
    thread = threading.Thread(
        target=_run_and_record,
        args=(runtime_dir, path, tid, text, run_id),
        name=f"cluster-run-{run_id}",
        daemon=True,
    )
    thread.start()
    return {
        "started": True,
        "replayed": False,
        "runId": run_id,
        "target": tid,
        "goal": text,
        "projectId": project_id,
        "projectPath": path,
        "conversationKind": "goal_conversation",
        "coordinatorScope": "project",
        "projectBinding": {
            "mode": "required",
            "projectId": project_id,
            "projectPath": path,
            "status": "bound",
        },
    }
