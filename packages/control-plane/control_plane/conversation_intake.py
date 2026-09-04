"""Durable human-message intake for DevFrame coordinator conversations."""
from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
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
_MAX_STATUS_FILE_BYTES = 256 * 1024
_MAX_STATUS_RUN_FILES = 200
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


def _assistant_message_id(event_id: str) -> str:
    digest = hashlib.sha256(f"{event_id}\0assistant".encode("utf-8")).hexdigest()
    return f"cam-{digest[:24]}"


def _proposal_id(event_id: str) -> str:
    digest = hashlib.sha256(f"{event_id}\0proposal".encode("utf-8")).hexdigest()
    return f"ctp-{digest[:24]}"


def _new_stable_run_id() -> str:
    return f"g-{secrets.token_hex(8)}"


def _runtime_root(runtime_dir: str | Path | None) -> Path:
    return Path(runtime_dir).resolve() if runtime_dir is not None else default_runtime_dir()


def _redact_status_paths(text: str, project_path: str) -> str:
    redacted = text
    for candidate in {
        project_path,
        project_path.replace("\\", "/"),
        project_path.replace("/", "\\"),
    }:
        if candidate:
            redacted = redacted.replace(candidate, "<project-root>")
    redacted = re.sub(
        r"(?i)\b[a-z]:[\\/][^\s`\"']+",
        "<local-path>",
        redacted,
    )
    redacted = re.sub(
        r"(?<![\w.])/(?:[^/\s`\"']+/)+[^/\s`\"']+",
        "<local-path>",
        redacted,
    )
    return redacted


def _extract_status_paragraph(
    lines: list[str],
    heading: str,
) -> str:
    for index, line in enumerate(lines):
        if line.strip() != heading:
            continue
        paragraph: list[str] = []
        for candidate in lines[index + 1 :]:
            stripped = candidate.strip()
            if not stripped:
                if paragraph:
                    break
                continue
            if stripped.startswith("#"):
                break
            paragraph.append(stripped)
        return " ".join(paragraph)
    return ""


def _extract_current_verdict(lines: list[str]) -> str:
    prefix = "Current verdict:"
    for index, line in enumerate(lines):
        stripped = line.strip()
        if not stripped.startswith(prefix):
            continue
        parts = [stripped[len(prefix) :].strip()]
        for candidate in lines[index + 1 : index + 5]:
            continuation = candidate.strip()
            if not continuation or continuation.startswith("#"):
                break
            parts.append(continuation)
        return " ".join(part for part in parts if part)
    return ""


def _bounded_project_status(
    runtime_dir: str | Path | None,
    *,
    project_id: str,
    project_path: str,
) -> dict[str, str]:
    status: dict[str, str] = {}
    root = Path(project_path).resolve()
    plan_path = (root / "PLAN.md").resolve()
    if root in plan_path.parents and plan_path.is_file():
        try:
            size = plan_path.stat().st_size
            if size <= _MAX_STATUS_FILE_BYTES:
                text = plan_path.read_bytes().decode("utf-8")
                lines = text.splitlines()
                verdict = _extract_current_verdict(lines)
                next_action = _extract_status_paragraph(lines, "## Next Action")
                if verdict:
                    status["verdict"] = _redact_status_paths(verdict, str(root))
                if next_action:
                    status["nextAction"] = _redact_status_paths(
                        next_action,
                        str(root),
                    )
        except (OSError, UnicodeDecodeError):
            pass

    run_counts: dict[str, int] = {}
    run_total = 0
    runs_dir = _runtime_root(runtime_dir) / "cluster-runs"
    if runs_dir.is_dir():
        for path in sorted(runs_dir.glob("g-*.json"), reverse=True)[
            :_MAX_STATUS_RUN_FILES
        ]:
            try:
                if path.stat().st_size > _MAX_STATUS_FILE_BYTES:
                    continue
                run = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError, json.JSONDecodeError):
                continue
            if not isinstance(run, dict):
                continue
            run_project_id = str(run.get("projectId") or "")
            run_project_path = str(run.get("projectPath") or "")
            if run_project_id != project_id and run_project_path != str(root):
                continue
            run_status = str(run.get("status") or "unknown").lower()
            run_counts[run_status] = run_counts.get(run_status, 0) + 1
            run_total += 1
    if run_total:
        counts = ", ".join(
            f"{name}={count}" for name, count in sorted(run_counts.items())
        )
        status["runSummary"] = f"{run_total} recorded ({counts})"
    return status


def _proposals_dir(runtime_dir: str | Path | None) -> Path:
    return _runtime_root(runtime_dir) / "conversation-proposals"


def _proposal_path(runtime_dir: str | Path | None, proposal_id: str) -> Path:
    if not re.fullmatch(r"ctp-[0-9a-f]{24}", proposal_id):
        raise IntakeError("unknown_proposal")
    return _proposals_dir(runtime_dir) / f"{proposal_id}.json"


def _proposal_decision_path(
    runtime_dir: str | Path | None,
    proposal_id: str,
) -> Path:
    return _proposal_path(runtime_dir, proposal_id).with_suffix(".decision.json")


def _proposal_fingerprint(proposal: dict[str, Any]) -> str:
    binding = {
        key: proposal.get(key)
        for key in (
            "proposalId",
            "sourceEventId",
            "sourceTurnId",
            "threadId",
            "threadKind",
            "projectId",
            "projectPath",
            "target",
            "goal",
            "stableRunId",
        )
    }
    encoded = json.dumps(
        binding,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _ensure_semantic_proposal(
    runtime_dir: str | Path | None,
    proposal: dict[str, Any],
) -> dict[str, Any]:
    proposal_id = str(proposal.get("proposalId") or "")
    path = _proposal_path(runtime_dir, proposal_id)
    if _publish_once(path, proposal):
        return proposal
    existing = _read_event(path)
    if (
        existing is None
        or existing.get("fingerprint") != proposal.get("fingerprint")
    ):
        raise IntakeError("proposal_conflict")
    return existing


def get_conversation_proposal(
    runtime_dir: str | Path | None,
    proposal_id: str,
) -> dict[str, Any]:
    proposal = _read_event(_proposal_path(runtime_dir, proposal_id))
    if proposal is None:
        raise IntakeError("unknown_proposal")
    return proposal


def _write_semantic_proposal(
    runtime_dir: str | Path | None,
    proposal: dict[str, Any],
) -> None:
    path = _proposal_path(runtime_dir, str(proposal.get("proposalId") or ""))
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(proposal, handle, indent=2, ensure_ascii=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
    finally:
        temporary_path.unlink(missing_ok=True)


def _transition_semantic_proposal(
    runtime_dir: str | Path | None,
    proposal: dict[str, Any],
    *,
    expected_statuses: set[str],
    status: str,
    **updates: Any,
) -> dict[str, Any]:
    latest = get_conversation_proposal(
        runtime_dir,
        str(proposal.get("proposalId") or ""),
    )
    if latest.get("fingerprint") != proposal.get("fingerprint"):
        raise IntakeError("approval_conflict")
    current_status = str(latest.get("status") or "")
    if current_status == status:
        return latest
    if current_status not in expected_statuses:
        raise IntakeError("approval_conflict")
    changed_at = _now_iso()
    history = [
        dict(item)
        for item in latest.get("stateHistory", [])
        if isinstance(item, dict)
    ]
    history.append({"status": status, "at": changed_at})
    updated = {
        **latest,
        **updates,
        "status": status,
        "stateHistory": history,
        "updatedAt": changed_at,
    }
    _write_semantic_proposal(runtime_dir, updated)
    return updated


def _validate_semantic_proposal_binding(
    runtime_dir: str | Path | None,
    proposal: dict[str, Any],
    paper_project_dirs: list[str | Path] | None = None,
) -> None:
    if proposal.get("fingerprint") != _proposal_fingerprint(proposal):
        raise IntakeError("approval_conflict")
    thread_id = str(proposal.get("threadId") or "")
    event_id = str(proposal.get("sourceEventId") or "")
    if not re.fullmatch(r"ci-[0-9a-f]{24}", event_id):
        raise IntakeError("approval_conflict")
    event = _read_event(_event_path(runtime_dir, thread_id, event_id))
    embedded = event.get("proposal") if isinstance(event, dict) else None
    expected = {
        "proposalId": proposal.get("proposalId"),
        "sourceTurnId": proposal.get("sourceTurnId"),
        "threadId": thread_id,
        "threadKind": proposal.get("threadKind"),
        "projectId": proposal.get("projectId"),
        "projectPath": proposal.get("projectPath"),
        "target": proposal.get("target"),
        "goal": proposal.get("goal"),
        "stableRunId": proposal.get("stableRunId"),
        "fingerprint": proposal.get("fingerprint"),
    }
    if (
        not isinstance(event, dict)
        or not isinstance(embedded, dict)
        or event.get("turnId") != proposal.get("sourceTurnId")
        or event.get("threadId") != thread_id
        or event.get("projectId") != proposal.get("projectId")
        or event.get("message") != proposal.get("goal")
        or any(embedded.get(key) != value for key, value in expected.items())
    ):
        raise IntakeError("approval_conflict")

    from .cluster_run import _resolve_project_reference

    resolved_path, resolved_project_id = _resolve_project_reference(
        runtime_dir,
        str(proposal.get("projectPath") or ""),
        paper_project_dirs=paper_project_dirs,
    )
    if (
        resolved_path != proposal.get("projectPath")
        or resolved_project_id != proposal.get("projectId")
    ):
        raise IntakeError("approval_conflict")


def _approved_response(
    proposal: dict[str, Any],
    *,
    replayed: bool,
) -> dict[str, Any]:
    return {
        "responded": True,
        "decision": "approve",
        "requestId": proposal.get("proposalId"),
        "threadId": proposal.get("threadId"),
        "executed": True,
        "status": "started",
        "runId": proposal.get("stableRunId"),
        "replayed": replayed,
    }


def _recover_approved_proposal(
    runtime_dir: str | Path | None,
    proposal: dict[str, Any],
    decision_claim: dict[str, Any],
    paper_project_dirs: list[str | Path] | None = None,
) -> dict[str, Any]:
    from .cluster_run import (
        _load_run_record,
        _pid_alive,
        start_cluster_run,
    )

    status = str(proposal.get("status") or "")
    stable_run_id = str(proposal.get("stableRunId") or "")
    if status in {"started", "starting"}:
        existing = _load_run_record(runtime_dir, stable_run_id)
        if existing is not None:
            start_cluster_run(
                runtime_dir,
                str(proposal.get("projectPath") or ""),
                str(proposal.get("target") or ""),
                str(proposal.get("goal") or ""),
                stable_run_id=stable_run_id,
                source_proposal_id=str(proposal.get("proposalId") or ""),
                source_turn_id=str(proposal.get("sourceTurnId") or ""),
                paper_project_dirs=paper_project_dirs,
            )
            if status != "started":
                proposal = _transition_semantic_proposal(
                    runtime_dir,
                    proposal,
                    expected_statuses={"starting"},
                    status="started",
                    runId=stable_run_id,
                    resolvedAt=_now_iso(),
                )
            return _approved_response(proposal, replayed=True)
    if status in {"start_failed", "recovery_required"}:
        raise IntakeError(status)
    owner_pid = decision_claim.get("ownerPid")
    if isinstance(owner_pid, int) and _pid_alive(owner_pid):
        raise IntakeError("approval_in_progress")
    if status in {"pending", "approval_claimed", "capability_issued", "starting"}:
        _transition_semantic_proposal(
            runtime_dir,
            proposal,
            expected_statuses={status},
            status="recovery_required",
            recoveryReason=f"stale_{status}",
            resolvedAt=_now_iso(),
        )
        raise IntakeError("recovery_required")
    raise IntakeError("approval_conflict")


def resolve_conversation_proposal(
    runtime_dir: str | Path | None,
    proposal_id: object,
    thread_id: object,
    decision: object,
    *,
    paper_project_dirs: list[str | Path] | None = None,
) -> dict[str, Any]:
    """Resolve one semantic proposal through a create-once decision claim."""
    pid = _validate_text(proposal_id, "proposal_id")
    tid = _validate_text(thread_id, "thread_id")
    normalized_decision = str(decision or "").strip().lower()
    if normalized_decision not in {"approve", "reject"}:
        raise IntakeError("invalid_approval_decision")

    proposal = get_conversation_proposal(runtime_dir, pid)
    if proposal.get("threadId") != tid:
        raise IntakeError("approval_conflict")
    _validate_semantic_proposal_binding(
        runtime_dir,
        proposal,
        paper_project_dirs,
    )
    decision_path = _proposal_decision_path(runtime_dir, pid)
    existing_decision = _read_event(decision_path)
    decision_claim: dict[str, Any]
    if existing_decision is not None:
        if (
            existing_decision.get("decision") != normalized_decision
            or existing_decision.get("threadId") != proposal.get("threadId")
            or existing_decision.get("fingerprint") != proposal.get("fingerprint")
        ):
            raise IntakeError("approval_conflict")
        replayed = True
        decision_claim = existing_decision
    else:
        claimed_at = _now_iso()
        decision_claim = {
            "proposalId": pid,
            "decision": normalized_decision,
            "threadId": proposal.get("threadId"),
            "sourceTurnId": proposal.get("sourceTurnId"),
            "stableRunId": proposal.get("stableRunId"),
            "fingerprint": proposal.get("fingerprint"),
            "ownerPid": os.getpid(),
            "claimedAt": claimed_at,
        }
        replayed = not _publish_once(decision_path, decision_claim)
        if replayed:
            existing_decision = _read_event(decision_path)
            if (
                existing_decision is None
                or existing_decision.get("decision") != normalized_decision
                or existing_decision.get("threadId") != proposal.get("threadId")
                or existing_decision.get("fingerprint") != proposal.get("fingerprint")
            ):
                raise IntakeError("approval_conflict")
            decision_claim = existing_decision

    if normalized_decision == "reject":
        if proposal.get("status") not in {"pending", "rejected"}:
            raise IntakeError("approval_conflict")
        if proposal.get("status") != "rejected":
            proposal = _transition_semantic_proposal(
                runtime_dir,
                proposal,
                expected_statuses={"pending"},
                status="rejected",
                decision="reject",
                resolvedAt=_now_iso(),
            )
        return {
            "responded": True,
            "decision": "reject",
            "requestId": pid,
            "threadId": tid,
            "executed": False,
            "status": "rejected",
            "replayed": replayed,
        }
    if replayed:
        return _recover_approved_proposal(
            runtime_dir,
            get_conversation_proposal(runtime_dir, pid),
            decision_claim,
            paper_project_dirs,
        )

    proposal = _transition_semantic_proposal(
        runtime_dir,
        proposal,
        expected_statuses={"pending"},
        status="approval_claimed",
        approvalClaimedAt=_now_iso(),
        approvalOwnerPid=os.getpid(),
    )
    try:
        from .cluster_run import ClusterRunError, propose_cluster_run, start_cluster_run

        capability = propose_cluster_run(
            runtime_dir,
            DEVFRAME_LOCAL_ENVIRONMENT_ID,
            str(proposal.get("projectPath") or ""),
            str(proposal.get("target") or ""),
            str(proposal.get("goal") or ""),
            proposed_by="rd-code-editor",
            stable_run_id=str(proposal.get("stableRunId") or ""),
            source_proposal_id=pid,
            source_turn_id=str(proposal.get("sourceTurnId") or ""),
            paper_project_dirs=paper_project_dirs,
        )
        if (
            not isinstance(capability, dict)
            or not isinstance(capability.get("proposalId"), str)
            or not str(capability.get("proposalId") or "").startswith("crp-")
            or not isinstance(capability.get("confirmationToken"), str)
            or not str(capability.get("confirmationToken") or "")
            or not isinstance(capability.get("expiresAt"), str)
            or not str(capability.get("expiresAt") or "")
            or capability.get("stableRunId") != proposal.get("stableRunId")
        ):
            raise ValueError("malformed cluster-run capability")
    except Exception as exc:
        proposal = _transition_semantic_proposal(
            runtime_dir,
            proposal,
            expected_statuses={"approval_claimed"},
            status="start_failed",
            failureCode=(
                exc.error_code
                if isinstance(exc, ClusterRunError)
                else "capability_issue_failed"
            ),
            resolvedAt=_now_iso(),
        )
        raise IntakeError("start_failed") from None

    proposal = _transition_semantic_proposal(
        runtime_dir,
        proposal,
        expected_statuses={"approval_claimed"},
        status="capability_issued",
        capabilityId=capability.get("proposalId"),
        capabilityExpiresAt=capability.get("expiresAt"),
    )
    proposal = _transition_semantic_proposal(
        runtime_dir,
        proposal,
        expected_statuses={"capability_issued"},
        status="starting",
        startingAt=_now_iso(),
    )
    try:
        started = start_cluster_run(
            runtime_dir,
            str(proposal.get("projectPath") or ""),
            str(proposal.get("target") or ""),
            str(proposal.get("goal") or ""),
            proposed_by="rd-code-editor",
            environment_id=DEVFRAME_LOCAL_ENVIRONMENT_ID,
            proposal_id=capability.get("proposalId"),
            confirmation_token=capability.get("confirmationToken"),
            decision="execute",
            stable_run_id=str(proposal.get("stableRunId") or ""),
            source_proposal_id=pid,
            source_turn_id=str(proposal.get("sourceTurnId") or ""),
            paper_project_dirs=paper_project_dirs,
        )
        if not isinstance(started, dict):
            raise ValueError("malformed cluster start result")
    except Exception as exc:
        _transition_semantic_proposal(
            runtime_dir,
            proposal,
            expected_statuses={"starting"},
            status="start_failed",
            failureCode=(
                exc.error_code
                if isinstance(exc, ClusterRunError)
                else "cluster_start_failed"
            ),
            resolvedAt=_now_iso(),
        )
        raise IntakeError("start_failed") from None
    if started.get("runId") != proposal.get("stableRunId"):
        _transition_semantic_proposal(
            runtime_dir,
            proposal,
            expected_statuses={"starting"},
            status="start_failed",
            failureCode="stable_run_id_mismatch",
            resolvedAt=_now_iso(),
        )
        raise IntakeError("start_failed")
    proposal = _transition_semantic_proposal(
        runtime_dir,
        proposal,
        expected_statuses={"starting"},
        status="started",
        runId=started.get("runId"),
        resolvedAt=_now_iso(),
    )
    return _approved_response(proposal, replayed=False)


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


def _canonical_global_project_id(
    runtime_dir: str | Path | None,
    paper_project_dirs: list[str | Path] | None,
) -> str:
    try:
        from .visual_state import build_visual_control_plane_state

        state = (
            build_visual_control_plane_state(runtime_dir)
            if paper_project_dirs is None
            else build_visual_control_plane_state(
                runtime_dir,
                paper_project_dirs=paper_project_dirs,
            )
        )
    except Exception as exc:  # noqa: BLE001 - fail closed when binding truth is unavailable
        raise IntakeError("resolution_failed") from exc
    canonical_projects = [
        project
        for project in state.get("projects", [])
        if isinstance(project, dict) and str(project.get("project_id") or "").strip()
    ]
    if len(canonical_projects) != 1:
        raise IntakeError("global_project_binding_unavailable")
    return str(canonical_projects[0].get("project_id") or "").strip()


def _resolve_thread(
    runtime_dir: str | Path | None,
    thread_id: str,
    paper_project_dirs: list[str | Path] | None = None,
) -> tuple[str, str]:
    if thread_id == GLOBAL_COORDINATOR_THREAD_ID:
        return "global_coordinator", ""

    try:
        from .cluster_run import list_cluster_runs

        for run in list_cluster_runs(runtime_dir):
            if str(run.get("runId") or "") == thread_id:
                return "goal_conversation", str(run.get("projectId") or "")

        from .visual_state import build_visual_control_plane_state

        state = (
            build_visual_control_plane_state(runtime_dir)
            if paper_project_dirs is None
            else build_visual_control_plane_state(
                runtime_dir,
                paper_project_dirs=paper_project_dirs,
            )
        )
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
    paper_project_dirs: list[str | Path] | None = None,
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

    thread_kind, bound_project = _resolve_thread(
        runtime_dir,
        tid,
        paper_project_dirs,
    )
    event_id = _event_id(tid, request_id)
    path = _event_path(runtime_dir, tid, event_id)
    existing_event = _read_event(path)
    if (
        isinstance(existing_event, dict)
        and isinstance(existing_event.get("clientProjectFingerprint"), str)
        and existing_event["clientProjectFingerprint"]
        != hashlib.sha256(project.encode("utf-8")).hexdigest()
    ):
        raise IntakeError("intake_conflict")
    if thread_kind == "goal_conversation":
        if not project:
            raise IntakeError("project_id_required_for_goal")
        if project != bound_project:
            raise IntakeError("project_id_mismatch")
    resolved_project_id = project
    resolved_project_path = ""
    if thread_kind == "global_coordinator":
        canonical_project_id = _canonical_global_project_id(
            runtime_dir,
            paper_project_dirs,
        )
        if project != canonical_project_id:
            raise IntakeError("project_id_mismatch")
        from .cluster_run import _resolve_project_reference

        resolved_project_path, resolved_project_id = _resolve_project_reference(
            runtime_dir,
            project,
            paper_project_dirs=paper_project_dirs,
        )
        if (
            not resolved_project_path
            or resolved_project_id != canonical_project_id
        ):
            raise IntakeError("unknown_project")

    assistant_message_id = _assistant_message_id(event_id)
    replayed = True
    with _JOURNAL_LOCK:
        existing = _read_event(path)
        if existing is None:
            from .goal_triage import (
                GOAL_KIND_DEVELOPMENT,
                classify_goal,
                coordinator_conversation_reply,
                is_project_status_request,
            )

            created_at = _now_iso()
            goal_kind = classify_goal(text)
            proposal: dict[str, Any] | None = None
            stored_project_id = resolved_project_id
            if goal_kind == GOAL_KIND_DEVELOPMENT:
                from .cluster_run import _resolve_project_reference

                project_path = resolved_project_path
                proposal_project_id = resolved_project_id
                if not project_path:
                    project_path, proposal_project_id = _resolve_project_reference(
                        runtime_dir,
                        project,
                        paper_project_dirs=paper_project_dirs,
                    )
                if not project_path or not proposal_project_id:
                    raise IntakeError("project_id_required_for_development")
                stored_project_id = proposal_project_id
                proposal_id = _proposal_id(event_id)
                proposal = {
                    "proposalId": proposal_id,
                    "sourceEventId": event_id,
                    "sourceTurnId": request_id,
                    "threadId": tid,
                    "threadKind": thread_kind,
                    "projectId": proposal_project_id,
                    "projectPath": project_path,
                    "target": "coordinator",
                    "goal": text,
                    "stableRunId": _new_stable_run_id(),
                    "status": "pending",
                    "createdAt": created_at,
                    "updatedAt": created_at,
                    "stateHistory": [{"status": "pending", "at": created_at}],
                }
                proposal["fingerprint"] = _proposal_fingerprint(proposal)
                assistant_text = (
                    "已准备一个待审批的开发提案；尚未签发执行能力，也未启动"
                    "工作流、智能体或项目写入。请检查提案后再明确批准或拒绝。"
                )
                turn_status = "proposal_pending"
            else:
                project_status = (
                    _bounded_project_status(
                        runtime_dir,
                        project_id=stored_project_id,
                        project_path=resolved_project_path,
                    )
                    if (
                        is_project_status_request(text)
                        and resolved_project_path
                    )
                    else None
                )
                assistant_text = coordinator_conversation_reply(
                    text,
                    project_id=stored_project_id,
                    project_status=project_status,
                )
                turn_status = "answered"
            proposed = {
                "eventId": event_id,
                "threadId": tid,
                "projectId": stored_project_id,
                "clientProjectFingerprint": hashlib.sha256(
                    project.encode("utf-8")
                ).hexdigest(),
                "clientRequestId": request_id,
                "turnId": request_id,
                "threadKind": thread_kind,
                "message": text,
                "goalKind": goal_kind,
                "status": turn_status,
                "environmentId": DEVFRAME_LOCAL_ENVIRONMENT_ID,
                "createdAt": created_at,
                "userMessage": {
                    "id": request_id,
                    "role": "user",
                    "text": text,
                    "turnId": request_id,
                    "createdAt": created_at,
                    "updatedAt": created_at,
                },
                "assistantMessage": {
                    "id": assistant_message_id,
                    "role": "assistant",
                    "text": assistant_text,
                    "turnId": request_id,
                    "createdAt": created_at,
                    "updatedAt": created_at,
                },
                **(
                    {
                        "proposalId": proposal["proposalId"],
                        "proposal": proposal,
                    }
                    if proposal is not None
                    else {}
                ),
            }
            if _publish_once(path, proposed):
                existing = proposed
                replayed = False
            else:
                existing = _read_event(path)
                if existing is None:
                    raise IntakeError("journal_corrupt")
        expected = {
            "threadId": tid,
            "clientRequestId": request_id,
            "threadKind": thread_kind,
            "message": text,
            "environmentId": DEVFRAME_LOCAL_ENVIRONMENT_ID,
        }
        stored_project_fingerprint = existing.get("clientProjectFingerprint")
        project_conflict = (
            stored_project_fingerprint != hashlib.sha256(project.encode("utf-8")).hexdigest()
            if isinstance(stored_project_fingerprint, str)
            else existing.get("projectId") != project
        )
        if project_conflict or any(
            existing.get(key) != value for key, value in expected.items()
        ):
            raise IntakeError("intake_conflict")
        embedded_proposal = existing.get("proposal")
        if isinstance(embedded_proposal, dict):
            _ensure_semantic_proposal(runtime_dir, embedded_proposal)

    assistant_message = existing.get("assistantMessage")
    if not isinstance(assistant_message, dict):
        raise IntakeError("journal_corrupt")
    return {
        "accepted": True,
        "threadId": tid,
        "projectId": existing.get("projectId", project),
        "eventId": event_id,
        "status": existing.get("status", "accepted"),
        "turnId": existing.get("turnId", request_id),
        "assistantMessageId": assistant_message.get("id", assistant_message_id),
        "replayed": replayed,
        **(
            {"proposalId": existing["proposalId"]}
            if isinstance(existing.get("proposalId"), str)
            else {}
        ),
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
