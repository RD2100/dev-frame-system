"""Real multi-agent team runtime objects (M1, slices 1-2).

Turns the Event Log and Message Bus from values *synthesized at read time* into
real, durable, recorded-at-runtime facts. When agents actually execute, the
controller records team events (task created, claimed, result/handoff) to a
dedicated append-only JSONL journal kept outside the repository, reusing the
same persistence shape and outside-repo safety guard as
`control_plane/runtime_store.py`.

Scope (recon-receipt-team-runtime.md): Event Log + Message Bus + a minimal Task
lifecycle. Agent Registry, Evidence Store, Review Gate, and Conflict Control
stay projected for now and are recorded in the receipt as deferred.

Design: this module is executor-agnostic. It records *what the team did*, not how
any one executor works. The read side (`build_team_runtime_view`) folds recorded
events into the schema shapes already defined for `team_message` / `team_event`.
"""
from __future__ import annotations

import json
import os
import threading
import time
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any

from jsonschema.validators import validator_for

from .backup_guard import default_runtime_dir, is_inside

TEAM_EVENTS_FILE = "team-events.jsonl"
TASK_KIND_EXECUTION = "execution"
TASK_KIND_INDEPENDENT_REVIEW = "independent_review"
ALLOWED_TASK_KINDS = {TASK_KIND_EXECUTION, TASK_KIND_INDEPENDENT_REVIEW}
ALLOWED_REVIEW_VERDICTS = {"pass", "blocked", "fail", "escalate"}
BLOCKED_REVIEW_ROLES = {
    "executor",
    "fixer",
    "coder",
    "worker",
    "controller",
    "coordinator",
    "root",
}
BLOCKED_REVIEWER_IDS = {"controller", "coordinator", "root"}
FINAL_VERDICT_PRODUCER_ID = "go-evidence-finalizer"
FINAL_VERDICT_PRODUCER_ROLE = "governance"
FINAL_STATE_BY_REVIEW_VERDICT = {
    "pass": "final_ready",
    "fail": "failed",
    "blocked": "blocked",
    "escalate": "blocked",
}


@dataclass
class TeamEvent:
    """A recorded team fact. Durable, timestamped, append-only."""

    event_type: str
    run_id: str
    agent_id: str
    payload: dict[str, Any] = field(default_factory=dict)
    timestamp: str = ""
    event_id: str = ""

    def __post_init__(self) -> None:
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()
        if not self.event_id:
            self.event_id = f"{_slug(self.run_id)}-{_slug(self.agent_id)}-{int(time.time() * 1000)}-{uuid.uuid4().hex[:6]}"


@dataclass
class _TeamReviewLivenessState:
    active: dict[str, set[str]] = field(default_factory=dict)
    active_generations: dict[str, int] = field(default_factory=dict)
    pending_pass_reviews: dict[str, str] = field(default_factory=dict)
    explicit_assignment: bool = False
    conflict_events: list[dict[str, Any]] = field(default_factory=list)
    ambiguous_review_id_events: list[dict[str, Any]] = field(
        default_factory=list
    )
    review_generations: dict[str, int] = field(default_factory=dict)
    generation_counter: int = 0
    latest_assignment_generation: int = 0
    latest_review_id: str = ""
    latest_review_verdict: str = ""
    latest_review_generation: int = 0


class TeamRuntime:
    """Append-only recorder for real team events.

    Thread- and process-safe for writers: an internal lock serializes one
    instance and an OS file lock serializes journal transactions across
    independent instances and processes.
    """

    def __init__(self, runtime_dir: str | Path | None = None,
                 repo_root: str | Path | None = None) -> None:
        self.runtime_dir = Path(runtime_dir).resolve() if runtime_dir else default_runtime_dir()
        self.repo_root = Path(repo_root).resolve() if repo_root else None
        self.path = self.runtime_dir / TEAM_EVENTS_FILE
        self._lock = threading.Lock()

    @contextmanager
    def _transaction(self) -> Iterator[None]:
        with self._lock:
            if self.repo_root and is_inside(self.runtime_dir, self.repo_root):
                raise ValueError(
                    "Team runtime journal must not be inside the public repository."
                )
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with _exclusive_file_lock(self.path.with_name(f"{self.path.name}.lock")):
                yield

    def _append(self, event: TeamEvent) -> str:
        with self._transaction():
            self._append_locked(event)
        return event.event_id

    def _append_locked(self, event: TeamEvent) -> None:
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(asdict(event), ensure_ascii=True) + "\n")

    def record_task_created(self, run_id: str, agent_id: str, *,
                            project_id: str = "", shard_index: int = 0,
                            shard_count: int = 0, targets: list[str] | None = None,
                            context_refs: list[dict[str, Any]] | None = None,
                            task_kind: str = TASK_KIND_EXECUTION,
                            agent_role: str = "worker") -> str:
        normalized_kind = _normalize_task_kind(task_kind)
        if normalized_kind not in ALLOWED_TASK_KINDS:
            raise ValueError(f"Unknown task_kind: {task_kind}.")
        event = TeamEvent(
            event_type="task_created",
            run_id=run_id,
            agent_id=agent_id,
            payload={
                "project_id": project_id,
                "shard_index": shard_index,
                "shard_count": shard_count,
                "targets": list(targets or []),
                "context_refs": _normalize_context_refs(context_refs),
                "task_kind": normalized_kind,
                "agent_role": str(agent_role or "worker"),
            },
        )
        if (
            normalized_kind == TASK_KIND_INDEPENDENT_REVIEW
            and not _is_independent_reviewer_identity(agent_id, agent_role)
        ):
            raise ValueError(
                f"Review assignment owner is not independent: {agent_id}/{agent_role}."
            )
        with self._transaction():
            events = _read_team_events(self.path)
            (
                execution_agent_ids,
                reviewer_agent_ids,
                active,
                _explicit,
                _pending,
            ) = _team_ownership_state(events, run_id)
            if normalized_kind == TASK_KIND_INDEPENDENT_REVIEW:
                if agent_id in execution_agent_ids:
                    raise ValueError(
                        f"Reviewer {agent_id} is an execution worker in run {run_id}."
                    )
                if active:
                    reviewer_id = next(iter(active))
                    raise ValueError(
                        f"Run {run_id} already has an active review assignment "
                        f"for reviewer {reviewer_id}."
                    )
            elif agent_id in reviewer_agent_ids:
                reviewer_state = "active reviewer" if agent_id in active else "prior reviewer"
                article = "an" if agent_id in active else "a"
                raise ValueError(
                    f"Agent {agent_id} is {article} {reviewer_state} in run {run_id}."
                )
            self._append_locked(event)
        return event.event_id

    def record_task_claimed(self, run_id: str, agent_id: str,
                            *, context_refs: list[dict[str, Any]] | None = None) -> str:
        event = TeamEvent(
            event_type="task_claimed",
            run_id=run_id,
            agent_id=agent_id,
            payload={"context_refs": _normalize_context_refs(context_refs)},
        )
        with self._transaction():
            targets_by_agent: dict[str, set[str]] = {}
            claimed_agents: set[str] = set()
            for record in _read_team_events(self.path):
                if str(record.get("run_id") or "") != run_id:
                    continue
                recorded_agent_id = str(record.get("agent_id") or "")
                event_type = str(record.get("event_type") or "")
                if event_type == "task_created":
                    payload = record.get("payload")
                    targets = payload.get("targets") if isinstance(payload, dict) else []
                    task_kind = _normalize_task_kind(
                        payload.get("task_kind") if isinstance(payload, dict) else ""
                    )
                    if (
                        task_kind != TASK_KIND_INDEPENDENT_REVIEW
                        and isinstance(targets, list)
                    ):
                        targets_by_agent.setdefault(recorded_agent_id, set()).update(
                            str(target) for target in targets if str(target)
                        )
                elif event_type == "task_claimed":
                    claimed_agents.add(recorded_agent_id)

            targets = targets_by_agent.get(agent_id, set())
            for claimed_agent_id in claimed_agents - {agent_id}:
                overlap = targets & targets_by_agent.get(claimed_agent_id, set())
                if overlap:
                    raise ValueError(
                        f"Targets already claimed in run {run_id}: {', '.join(sorted(overlap))}."
                    )
            self._append_locked(event)
        return event.event_id

    def record_result(self, run_id: str, agent_id: str, *, status: str,
                      report_path: str = "", isolated: bool = False) -> str:
        with self._transaction():
            task_kind = _latest_task_kind(
                _read_team_events(self.path), run_id, agent_id
            )
            event = TeamEvent(
                event_type=(
                    "task_progress"
                    if task_kind == TASK_KIND_INDEPENDENT_REVIEW
                    else "task_result"
                ),
                run_id=run_id,
                agent_id=agent_id,
                payload={
                    "status": status,
                    "report_present": bool(report_path),
                    "report_path": str(report_path or ""),
                    "isolated": bool(isolated),
                },
            )
            self._append_locked(event)
            if report_path:
                self._append_locked(TeamEvent(
                    event_type="evidence_ref",
                    run_id=run_id,
                    agent_id=agent_id,
                    payload={
                        "ref_type": "report",
                        "ref_path": str(report_path),
                        "source_event_id": event.event_id,
                    },
                ))
        return event.event_id

    def record_evidence_ref(self, run_id: str, agent_id: str, *,
                            ref_type: str, ref_path: str,
                            source_event_id: str = "") -> str:
        """Record an explicit artifact/evidence reference produced by an agent."""
        return self._append(TeamEvent(
            event_type="evidence_ref",
            run_id=run_id,
            agent_id=agent_id,
            payload={
                "ref_type": str(ref_type or "artifact"),
                "ref_path": str(ref_path or ""),
                "source_event_id": str(source_event_id or ""),
            },
        ))

    def record_review_ref(self, run_id: str, reviewer_id: str, *,
                          review_id: str, reviewer_role: str, verdict: str,
                          ref_path: str, reviewed_evidence_refs: list[str],
                          executor_id: str = "",
                          reviewed_inputs: list[str] | None = None,
                          source: str = "") -> str:
        """Record an independent review artifact reference."""
        if not str(review_id or ""):
            raise ValueError("Review review_id is required.")
        if not str(reviewer_id or ""):
            raise ValueError("Review reviewer_id is required.")
        role_token = _normalize_role(reviewer_role)
        if not role_token or role_token in BLOCKED_REVIEW_ROLES:
            raise ValueError(f"Reviewer role is not independent: {role_token or 'missing'}.")
        reviewer_token = _normalize_role(reviewer_id)
        if reviewer_token in BLOCKED_REVIEWER_IDS:
            raise ValueError(f"Reviewer identity is not independent: {reviewer_id}.")
        if reviewer_id and executor_id and reviewer_id == executor_id:
            raise ValueError("Reviewer identity is not independent from executor_id.")
        if verdict not in ALLOWED_REVIEW_VERDICTS:
            raise ValueError(f"Review verdict is not canonical: {verdict or 'missing'}.")
        if not str(ref_path or ""):
            raise ValueError("Review ref_path is required.")
        if not any(str(ref) for ref in reviewed_evidence_refs):
            raise ValueError("At least one reviewed evidence reference is required.")
        event = TeamEvent(
            event_type="review_ref",
            run_id=run_id,
            agent_id=reviewer_id,
            payload={
                "review_id": str(review_id or ""),
                "reviewer_id": str(reviewer_id or ""),
                "reviewer_role": str(reviewer_role or ""),
                "executor_id": str(executor_id or ""),
                "verdict": str(verdict or ""),
                "ref_path": str(ref_path or ""),
                "reviewed_evidence_refs": [str(ref) for ref in reviewed_evidence_refs if str(ref)],
                "reviewed_inputs": [str(item) for item in reviewed_inputs or [] if str(item)],
                "source": str(source or ""),
            },
        )
        with self._transaction():
            events = _read_team_events(self.path)
            execution_agent_ids, _reviewers, active, explicit, pending = (
                _team_ownership_state(events, run_id)
            )
            if reviewer_id in execution_agent_ids:
                raise ValueError(
                    f"Reviewer {reviewer_id} is an execution worker in run {run_id}."
            )
            existing_event_id = _matching_review_ref_event_id(events, event)
            if existing_event_id:
                review_liveness = team_review_liveness(events).get(run_id, {})
                review_generations = review_liveness.get("review_generations")
                review_generation = (
                    review_generations.get(str(review_id or ""))
                    if isinstance(review_generations, dict)
                    else None
                )
                if (
                    isinstance(review_generation, int)
                    and review_generation > 0
                    and review_generation
                    == review_liveness.get("latest_assignment_generation")
                    and not review_liveness.get(
                        "ambiguous_review_id_events"
                    )
                ):
                    return existing_event_id
                raise ValueError(
                    f"Review review_id is already bound in run {run_id}: "
                    f"{review_id}."
                )
            if _review_id_is_recorded(events, run_id, str(review_id or "")):
                raise ValueError(
                    f"Review review_id is already bound in run {run_id}: "
                    f"{review_id}."
                )
            if active and reviewer_id not in active:
                raise ValueError(
                    f"Run {run_id} already has an active review assignment."
                )
            if reviewer_id in pending:
                raise ValueError(
                    f"Review {pending[reviewer_id]} is awaiting a final verdict."
                )
            if explicit and reviewer_id not in active:
                raise ValueError(
                    f"Reviewer {reviewer_id} does not own an active review "
                    f"assignment in run {run_id}."
                )
            if not active and not explicit:
                created, claimed = _implicit_review_assignment_events(
                    run_id, reviewer_id, role_token
                )
                self._append_locked(created)
                self._append_locked(claimed)
            self._append_locked(event)
        return event.event_id

    def record_final_verdict_ref(self, run_id: str, producer_id: str, *,
                                 verdict_id: str, producer_role: str,
                                 final_state: str, ref_path: str,
                                 review_ref: str, gate_refs: list[str],
                                 gate_summary: list[dict[str, Any]] | None = None,
                                 limitations: list[str] | None = None,
                                 human_or_governance_reference: str = "") -> str:
        """Record a governance final verdict artifact reference."""
        event = TeamEvent(
            event_type="final_verdict_ref",
            run_id=run_id,
            agent_id=producer_id,
            payload={
                "verdict_id": str(verdict_id or ""),
                "produced_by": str(producer_id or ""),
                "producer_role": str(producer_role or ""),
                "final_state": str(final_state or ""),
                "ref_path": str(ref_path or ""),
                "review_ref": str(review_ref or ""),
                "gate_refs": [str(ref) for ref in gate_refs or [] if str(ref)],
                "gate_summary": _normalize_gate_summary(gate_summary),
                "limitations": [str(item) for item in limitations or [] if str(item)],
                "human_or_governance_reference": str(human_or_governance_reference or ""),
            },
        )
        with self._transaction():
            events = _read_team_events(self.path)
            review_payload, review_diagnostic = _review_payload_for_final_verdict(
                events, run_id, str(review_ref or "")
            )
            diagnostic = review_diagnostic or _final_verdict_diagnostic(
                event, review_payload
            )
            if diagnostic:
                raise ValueError(f"Final verdict {diagnostic}.")
            existing_event_id = _matching_final_verdict_ref_event_id(events, event)
            if existing_event_id:
                return existing_event_id
            reviewer_id = str(review_payload.get("reviewer_id") or "")
            execution, _reviewers, active, _explicit, pending = (
                _team_ownership_state(events, run_id)
            )
            if reviewer_id in execution:
                raise ValueError(
                    "Final verdict reviewer is an execution worker in the same run."
                )
            if str(review_payload.get("verdict") or "") == "pass":
                if (
                    reviewer_id not in active
                    or pending.get(reviewer_id) != str(review_ref or "")
                ):
                    raise ValueError(
                        "Final verdict review_ref does not own a pending pass review."
                    )
            self._append_locked(event)
        return event.event_id

    def record_workflow_event(self, run_id: str, *, phase: str, status: str,
                              role: str = "coordinator", summary: str = "") -> str:
        """Record a workflow phase transition or controller decision.

        Used by the M3 workflow engine to make the multi-phase collaboration a
        real recorded fact (plan -> execute -> review -> verdict), reusing the
        same durable journal as the M1 task events.
        """
        return self._append(TeamEvent(
            event_type="workflow_event",
            run_id=run_id,
            agent_id=role,
            payload={
                "phase": str(phase),
                "status": str(status),
                "role": str(role),
                "summary": str(summary),
            },
        ))

    def record_agent_message(self, run_id: str, from_agent_id: str, to_agent_id: str,
                             *, kind: str, summary: str) -> str:
        """Record an explicit agent-to-agent message as a durable event.

        Unlike the lifecycle projections (task-assign/claim/result) which are
        synthesized from task state transitions, this records a real inter-agent
        communication fact. Fail closed: missing any required field raises
        ``ValueError`` so no partial message is ever persisted.
        """
        for _name, _value in (
            ("from_agent_id", from_agent_id),
            ("to_agent_id", to_agent_id),
            ("kind", kind),
            ("summary", summary),
        ):
            if not str(_value or "").strip():
                raise ValueError(f"record_agent_message requires a non-empty {_name}.")
        return self._append(TeamEvent(
            event_type="agent_message",
            run_id=run_id,
            agent_id=from_agent_id,
            payload={
                "to_agent_id": str(to_agent_id),
                "kind": str(kind),
                "summary": str(summary),
            },
        ))

    def read_all(self) -> list[dict[str, Any]]:
        return _read_team_events(self.path)


@contextmanager
def _exclusive_file_lock(path: Path) -> Iterator[None]:
    with path.open("a+b") as handle:
        handle.seek(0)
        if os.name == "nt":
            import msvcrt

            msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
        else:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            handle.seek(0)
            if os.name == "nt":
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _read_team_events(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    events: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            stripped = line.strip()
            if not stripped:
                continue
            try:
                events.append(json.loads(stripped))
            except json.JSONDecodeError:
                continue
    return events


def _slug(value: object) -> str:
    text = "".join(
        ch if (ch.isalnum() or ch == "-") else "-"
        for ch in str(value or "").strip().lower()
    ).strip("-")
    while "--" in text:
        text = text.replace("--", "-")
    return text or "x"


def _normalize_context_refs(value: list[dict[str, Any]] | None) -> list[dict[str, str]]:
    refs: list[dict[str, str]] = []
    for item in value or []:
        if not isinstance(item, dict):
            continue
        ref_path = str(item.get("ref_path") or "")
        if not ref_path:
            continue
        refs.append({
            "ref_type": str(item.get("ref_type") or "legacy_context"),
            "ref_path": ref_path,
            "context_id": str(item.get("context_id") or ""),
        })
    return refs


def _normalize_task_kind(value: object) -> str:
    token = str(value or TASK_KIND_EXECUTION).strip().lower().replace("-", "_")
    return token or TASK_KIND_EXECUTION


def _normalize_role(value: object) -> str:
    return str(value or "").strip().casefold().replace("-", "_")


def _is_independent_reviewer_identity(reviewer_id: object, reviewer_role: object) -> bool:
    role_token = _normalize_role(reviewer_role)
    reviewer_token = _normalize_role(reviewer_id)
    return (
        bool(role_token)
        and bool(reviewer_token)
        and role_token not in BLOCKED_REVIEW_ROLES
        and reviewer_token not in BLOCKED_REVIEWER_IDS
    )


def team_identity_ownership(
    events: list[dict[str, Any]],
) -> tuple[set[tuple[str, str]], set[tuple[str, str]]]:
    """Return execution and reviewer identities across the complete journal."""
    task_kinds: dict[tuple[str, str], str] = {}
    execution: set[tuple[str, str]] = set()
    reviewers: set[tuple[str, str]] = set()
    for event in events:
        run_id = str(event.get("run_id") or "")
        agent_id = str(event.get("agent_id") or "")
        if not run_id or not agent_id:
            continue
        key = (run_id, agent_id)
        event_type = str(event.get("event_type") or "")
        payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
        if event_type == "task_created":
            task_kind = _normalize_task_kind(payload.get("task_kind"))
            task_kinds[key] = task_kind
            if task_kind != TASK_KIND_INDEPENDENT_REVIEW:
                execution.add(key)
            elif _is_independent_reviewer_identity(
                agent_id, payload.get("agent_role")
            ):
                reviewers.add(key)
        elif (
            event_type == "task_result"
            and task_kinds.get(key, TASK_KIND_EXECUTION)
            != TASK_KIND_INDEPENDENT_REVIEW
        ):
            execution.add(key)
        elif event_type == "review_ref" and _is_terminal_review_ref(
            payload, agent_id
        ):
            reviewers.add(key)
    return execution, reviewers


def _latest_task_kind(events: list[dict[str, Any]], run_id: str, agent_id: str) -> str:
    task_kind = TASK_KIND_EXECUTION
    for event in events:
        if (
            str(event.get("run_id") or "") != run_id
            or str(event.get("agent_id") or "") != agent_id
            or str(event.get("event_type") or "") != "task_created"
        ):
            continue
        payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
        task_kind = _normalize_task_kind(payload.get("task_kind"))
    return task_kind


def _team_ownership_state(
    events: list[dict[str, Any]], run_id: str
) -> tuple[set[str], set[str], dict[str, set[str]], bool, dict[str, str]]:
    execution_keys, reviewer_keys = team_identity_ownership(events)
    execution_agent_ids = {
        agent_id for event_run_id, agent_id in execution_keys if event_run_id == run_id
    }
    reviewer_agent_ids = {
        agent_id for event_run_id, agent_id in reviewer_keys if event_run_id == run_id
    }
    run_events = [
        event for event in events if str(event.get("run_id") or "") == run_id
    ]
    state = _fold_team_review_liveness(run_events, execution_agent_ids)
    return (
        execution_agent_ids,
        reviewer_agent_ids,
        state.active,
        state.explicit_assignment,
        state.pending_pass_reviews,
    )


def _fold_team_review_liveness(
    events: list[dict[str, Any]], execution_agent_ids: set[str]
) -> _TeamReviewLivenessState:
    state = _TeamReviewLivenessState()
    pending_reviewers_by_id: dict[str, str] = {}
    review_payloads_by_id: dict[str, dict[str, Any]] = {}
    for event in events:
        event_type = str(event.get("event_type") or "")
        agent_id = str(event.get("agent_id") or "")
        payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
        if event_type == "task_created":
            task_kind = _normalize_task_kind(payload.get("task_kind"))
            if task_kind == TASK_KIND_INDEPENDENT_REVIEW:
                state.explicit_assignment = True
                if _is_independent_reviewer_identity(
                    agent_id, payload.get("agent_role")
                ) and agent_id not in execution_agent_ids:
                    if state.active:
                        state.conflict_events.append(event)
                        continue
                    _open_review_assignment(
                        state,
                        agent_id,
                        _review_targets(payload.get("targets")),
                    )
        elif event_type == "review_ref" and _is_terminal_review_ref(payload, agent_id):
            reviewer_id = str(payload.get("reviewer_id") or agent_id)
            if reviewer_id in execution_agent_ids:
                continue
            review_id = str(payload.get("review_id") or "")
            existing_payload = review_payloads_by_id.get(review_id)
            if existing_payload is not None:
                existing_generation = state.review_generations.get(review_id, 0)
                active_generation = state.active_generations.get(reviewer_id)
                if (
                    existing_payload == payload
                    and (
                        active_generation is None
                        or active_generation == existing_generation
                    )
                ):
                    continue
                state.ambiguous_review_id_events.append(event)
                continue
            if reviewer_id not in state.active:
                if state.active:
                    state.conflict_events.append(event)
                    continue
                if state.explicit_assignment:
                    continue
                _open_review_assignment(state, reviewer_id, set())
            review_generation = state.active_generations[reviewer_id]
            review_payloads_by_id[review_id] = payload
            state.review_generations[review_id] = review_generation
            state.latest_review_id = review_id
            state.latest_review_verdict = str(payload.get("verdict") or "")
            state.latest_review_generation = review_generation
            if str(payload.get("verdict") or "") == "pass":
                previous_review_id = state.pending_pass_reviews.get(reviewer_id)
                if previous_review_id:
                    pending_reviewers_by_id.pop(previous_review_id, None)
                state.pending_pass_reviews[reviewer_id] = review_id
                pending_reviewers_by_id[review_id] = reviewer_id
            else:
                state.active.pop(reviewer_id, None)
                state.active_generations.pop(reviewer_id, None)
                pending_review_id = state.pending_pass_reviews.pop(reviewer_id, None)
                if pending_review_id:
                    pending_reviewers_by_id.pop(pending_review_id, None)
        elif event_type == "final_verdict_ref":
            review_ref = str(payload.get("review_ref") or "")
            review_payload = review_payloads_by_id.get(review_ref)
            if not review_payload or _final_verdict_diagnostic(event, review_payload):
                continue
            reviewer_id = pending_reviewers_by_id.pop(review_ref, None)
            if reviewer_id:
                state.active.pop(reviewer_id, None)
                state.active_generations.pop(reviewer_id, None)
                state.pending_pass_reviews.pop(reviewer_id, None)
    state.active = {
        reviewer_id: targets
        for reviewer_id, targets in state.active.items()
        if reviewer_id not in execution_agent_ids
    }
    return state


def _open_review_assignment(
    state: _TeamReviewLivenessState,
    reviewer_id: str,
    targets: set[str],
) -> None:
    state.generation_counter += 1
    state.active[reviewer_id] = targets
    state.active_generations[reviewer_id] = state.generation_counter
    state.latest_assignment_generation = state.generation_counter


def team_review_liveness(
    events: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Return one fail-closed review-assignment view per journal run."""
    execution_keys, _reviewer_keys = team_identity_ownership(events)
    execution_by_run: dict[str, set[str]] = {}
    for run_id, agent_id in execution_keys:
        execution_by_run.setdefault(run_id, set()).add(agent_id)
    events_by_run: dict[str, list[dict[str, Any]]] = {}
    for event in events:
        run_id = str(event.get("run_id") or "")
        if run_id:
            events_by_run.setdefault(run_id, []).append(event)
    liveness: dict[str, dict[str, Any]] = {}
    for run_id, run_events in events_by_run.items():
        state = _fold_team_review_liveness(
            run_events, execution_by_run.get(run_id, set())
        )
        liveness[run_id] = {
            "active_reviewer_ids": sorted(state.active),
            "conflict_events": list(state.conflict_events),
            "ambiguous_review_id_events": list(
                state.ambiguous_review_id_events
            ),
            "explicit_assignment": state.explicit_assignment,
            "review_generations": dict(state.review_generations),
            "latest_assignment_generation": state.latest_assignment_generation,
            "latest_review_id": state.latest_review_id,
            "latest_review_verdict": state.latest_review_verdict,
            "latest_review_generation": state.latest_review_generation,
            "pending_pass_reviews": dict(state.pending_pass_reviews),
        }
    return liveness


def team_final_review_liveness_diagnostic(
    review_liveness: dict[str, Any], final_state: str, review_ref: str
) -> str:
    """Explain why a final verdict is stale against the complete journal."""
    review_generations = review_liveness.get("review_generations")
    review_generation = (
        review_generations.get(review_ref)
        if isinstance(review_generations, dict)
        else None
    )
    latest_assignment_generation = review_liveness.get(
        "latest_assignment_generation"
    )
    if (
        isinstance(review_generation, int)
        and review_generation > 0
        and isinstance(latest_assignment_generation, int)
        and latest_assignment_generation > 0
        and review_generation != latest_assignment_generation
    ):
        return "review_ref belongs to a prior review assignment generation"
    active_reviewer_ids = review_liveness.get("active_reviewer_ids")
    if isinstance(active_reviewer_ids, list) and active_reviewer_ids:
        pending_pass_reviews = review_liveness.get("pending_pass_reviews")
        current_pass_owner = (
            len(active_reviewer_ids) == 1
            and isinstance(pending_pass_reviews, dict)
            and str(pending_pass_reviews.get(active_reviewer_ids[0]) or "")
            == review_ref
        )
        if not current_pass_owner:
            return "a newer review assignment remains active"
    latest_review_id = str(review_liveness.get("latest_review_id") or "")
    if latest_review_id and review_ref != latest_review_id:
        return "review_ref does not name the latest effective review"
    latest_review_verdict = str(
        review_liveness.get("latest_review_verdict") or ""
    )
    if final_state == "final_ready" and latest_review_verdict != "pass":
        return "final_ready requires the latest effective review to pass"
    return ""


def _matching_review_ref_event_id(
    events: list[dict[str, Any]], candidate: TeamEvent
) -> str:
    for event in events:
        if (
            str(event.get("event_type") or "") == "review_ref"
            and str(event.get("run_id") or "") == candidate.run_id
            and str(event.get("agent_id") or "") == candidate.agent_id
            and event.get("payload") == candidate.payload
        ):
            return str(event.get("event_id") or "")
    return ""


def _review_id_is_recorded(
    events: list[dict[str, Any]], run_id: str, review_id: str
) -> bool:
    return any(
        str(event.get("event_type") or "") == "review_ref"
        and str(event.get("run_id") or "") == run_id
        and str(
            (
                event.get("payload")
                if isinstance(event.get("payload"), dict)
                else {}
            ).get("review_id")
            or ""
        )
        == review_id
        for event in events
    )


def _matching_final_verdict_ref_event_id(
    events: list[dict[str, Any]], candidate: TeamEvent
) -> str:
    for event in events:
        if (
            str(event.get("event_type") or "") == "final_verdict_ref"
            and str(event.get("run_id") or "") == candidate.run_id
            and str(event.get("agent_id") or "") == candidate.agent_id
            and event.get("payload") == candidate.payload
        ):
            return str(event.get("event_id") or "")
    return ""


def _review_payload_for_final_verdict(
    events: list[dict[str, Any]], run_id: str, review_ref: str
) -> tuple[dict[str, Any], str]:
    if not review_ref:
        return {}, "review_ref is required"
    matches: list[dict[str, Any]] = []
    for event in events:
        if (
            str(event.get("event_type") or "") != "review_ref"
            or str(event.get("run_id") or "") != run_id
        ):
            continue
        payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
        if (
            str(payload.get("review_id") or "") == review_ref
            and _is_terminal_review_ref(payload, str(event.get("agent_id") or ""))
        ):
            matches.append(payload)
    if not matches:
        return {}, "review_ref does not name a canonical review"
    if any(payload != matches[0] for payload in matches[1:]):
        return {}, "review_ref is ambiguous"
    return matches[0], ""


@lru_cache(maxsize=1)
def _final_verdict_validator():
    schema_path = Path(__file__).with_name("final-verdict.schema.json")
    schema = json.loads(schema_path.read_text(encoding="utf-8-sig"))
    validator_class = validator_for(schema)
    validator_class.check_schema(schema)
    return validator_class(schema)


def _read_final_verdict_artifact(path: str) -> tuple[dict[str, Any], str]:
    if not path:
        return {}, "ref_path is required"
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    except (json.JSONDecodeError, OSError):
        return {}, "artifact is not readable canonical JSON"
    if not isinstance(data, dict):
        return {}, "artifact is not a JSON object"
    errors = sorted(
        _final_verdict_validator().iter_errors(data),
        key=lambda error: list(error.path),
    )
    if errors:
        return {}, "artifact schema is invalid"
    return data, ""


def _final_verdict_diagnostic(
    event: TeamEvent | dict[str, Any], review_payload: dict[str, Any]
) -> str:
    if isinstance(event, TeamEvent):
        run_id = event.run_id
        producer_id = event.agent_id
        payload = event.payload
    else:
        run_id = str(event.get("run_id") or "")
        producer_id = str(event.get("agent_id") or "")
        payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
    artifact, artifact_diagnostic = _validated_final_verdict_artifact(
        payload, run_id, producer_id
    )
    if artifact_diagnostic:
        return artifact_diagnostic
    return _final_verdict_review_identity_diagnostic(
        payload, artifact, review_payload
    )


def _validated_final_verdict_artifact(
    payload: dict[str, Any], run_id: str, producer_id: str
) -> tuple[dict[str, Any], str]:
    if producer_id != FINAL_VERDICT_PRODUCER_ID:
        return {}, "producer is not go-evidence-finalizer"
    if str(payload.get("produced_by") or "") != producer_id:
        return {}, "produced_by does not match the canonical producer"
    if str(payload.get("producer_role") or "") != FINAL_VERDICT_PRODUCER_ROLE:
        return {}, "producer_role is not governance"
    verdict_id = str(payload.get("verdict_id") or "")
    if not verdict_id:
        return {}, "verdict_id is required"
    review_ref = str(payload.get("review_ref") or "")
    if not review_ref:
        return {}, "review_ref is required"
    gate_refs = payload.get("gate_refs")
    if not isinstance(gate_refs, list) or not gate_refs or any(
        not str(ref) for ref in gate_refs
    ):
        return {}, "gate_refs is required"
    if len({str(ref) for ref in gate_refs}) != len(gate_refs):
        return {}, "gate_refs must be unique"
    artifact, artifact_diagnostic = _read_final_verdict_artifact(
        str(payload.get("ref_path") or "")
    )
    if artifact_diagnostic:
        return {}, artifact_diagnostic
    for field_name in ("verdict_id", "produced_by", "producer_role", "final_state"):
        if str(artifact.get(field_name) or "") != str(payload.get(field_name) or ""):
            return {}, f"artifact {field_name} does not match the event"
    if artifact.get("gate_summary") != payload.get("gate_summary"):
        return {}, "artifact gate_summary does not match the event"
    if artifact.get("limitations") != payload.get("limitations"):
        return {}, "artifact limitations do not match the event"
    if str(artifact.get("human_or_governance_reference") or "") != str(
        payload.get("human_or_governance_reference") or ""
    ):
        return {}, "artifact governance reference does not match the event"
    if str(payload.get("human_or_governance_reference") or "") != (
        f"go-evidence-finalize:{run_id}"
    ):
        return {}, "governance reference does not match the run"
    return artifact, ""


def _final_verdict_review_identity_diagnostic(
    payload: dict[str, Any],
    artifact: dict[str, Any],
    review_payload: dict[str, Any],
) -> str:
    review_verdict = str(review_payload.get("verdict") or "")
    expected_final_state = FINAL_STATE_BY_REVIEW_VERDICT.get(review_verdict)
    if not expected_final_state:
        return "review verdict is not canonical"
    if str(payload.get("final_state") or "") != expected_final_state:
        return "final_state does not match the review verdict"
    reviewer_id = str(review_payload.get("reviewer_id") or "")
    review_path = str(review_payload.get("ref_path") or "")
    expected_reviewer_summary = {
        "reviewer_id": reviewer_id,
        "verdict": review_verdict,
        "evidence_path": review_path,
    }
    if artifact.get("reviewer_summary") != expected_reviewer_summary:
        return "artifact reviewer_summary does not match the review"
    reviewed_evidence_refs = {
        str(ref)
        for ref in review_payload.get("reviewed_evidence_refs", [])
        if str(ref)
    }
    inputs_reviewed = {
        str(ref) for ref in artifact.get("inputs_reviewed", []) if str(ref)
    }
    if review_path not in inputs_reviewed or not reviewed_evidence_refs <= inputs_reviewed:
        return "artifact inputs_reviewed does not contain the review evidence"
    gate_summary = artifact.get("gate_summary")
    if not isinstance(gate_summary, list) or not gate_summary:
        return "artifact gate_summary is required"
    gate_refs = payload.get("gate_refs")
    if not isinstance(gate_refs, list):
        return "gate_refs is required"
    artifact_gate_ids = [str(item.get("gate_id") or "") for item in gate_summary]
    if artifact_gate_ids != [str(ref) for ref in gate_refs]:
        return "artifact gate identities do not match gate_refs"
    expected_gate_result = {
        "pass": "pass",
        "fail": "fail",
        "blocked": "blocked",
        "escalate": "blocked",
    }[review_verdict]
    if any(
        str(item.get("result") or "") != expected_gate_result
        or str(item.get("evidence_path") or "") != review_path
        for item in gate_summary
    ):
        return "artifact gate evidence does not match the review"
    return ""


def _implicit_review_assignment_events(
    run_id: str, reviewer_id: str, reviewer_role: str
) -> tuple[TeamEvent, TeamEvent]:
    created = TeamEvent(
        event_type="task_created",
        run_id=run_id,
        agent_id=reviewer_id,
        payload={
            "project_id": "",
            "shard_index": 0,
            "shard_count": 0,
            "targets": [],
            "context_refs": [],
            "task_kind": TASK_KIND_INDEPENDENT_REVIEW,
            "agent_role": reviewer_role,
        },
    )
    claimed = TeamEvent(
        event_type="task_claimed",
        run_id=run_id,
        agent_id=reviewer_id,
        payload={"context_refs": []},
    )
    return created, claimed


def _review_targets(value: object) -> set[str]:
    if not isinstance(value, list):
        return set()
    return {str(item) for item in value if str(item)}


def _is_terminal_review_ref(payload: dict[str, Any], agent_id: str = "") -> bool:
    verdict = str(payload.get("verdict") or "")
    reviewer_id = str(payload.get("reviewer_id") or agent_id)
    executor_id = str(payload.get("executor_id") or "")
    role_token = _normalize_role(payload.get("reviewer_role"))
    evidence_refs = payload.get("reviewed_evidence_refs")
    return (
        verdict in ALLOWED_REVIEW_VERDICTS
        and bool(str(payload.get("review_id") or ""))
        and bool(reviewer_id)
        and (not agent_id or reviewer_id == agent_id)
        and _is_independent_reviewer_identity(reviewer_id, role_token)
        and (not executor_id or reviewer_id != executor_id)
        and bool(str(payload.get("ref_path") or ""))
        and isinstance(evidence_refs, list)
        and any(str(ref) for ref in evidence_refs)
    )


def _normalize_gate_summary(value: list[dict[str, Any]] | None) -> list[dict[str, str]]:
    summary: list[dict[str, str]] = []
    for item in value or []:
        if not isinstance(item, dict):
            continue
        gate_id = str(item.get("gate_id") or "")
        result = str(item.get("result") or "")
        if not gate_id or not result:
            continue
        summary.append({
            "gate_id": gate_id,
            "result": result,
            "evidence_path": str(item.get("evidence_path") or ""),
        })
    return summary


def build_team_runtime_view(runtime_dir: str | Path | None = None) -> dict[str, list[dict[str, Any]]]:
    """Fold recorded team events into schema-shaped team objects.

    Returns real, recorded team objects (distinct from the read-time projection),
    using the `team_message`, `team_event`, `team_conflict`, and `team_gate`
    shapes from the visual control plane schema. Slice 1 made message_bus and
    event_log real; slice 2 additionally derives conflict_control (file ownership
    from each task's recorded targets) and review_gates (acceptance facts from
    each recorded task result) from the SAME durable events — no extra recording.
    Empty when no run has recorded events, so callers can extend the projected
    lists without changing default behavior.
    """
    empty = {"message_bus": [], "event_log": [], "conflict_control": [], "review_gates": [],
             "agent_registry": [], "task_board": [], "evidence_store": []}
    if not runtime_dir:
        return empty
    path = Path(runtime_dir) / TEAM_EVENTS_FILE
    records = _read_team_events(path)
    review_liveness_by_run = team_review_liveness(records)
    invalid_review_runs = {
        run_id
        for run_id, state in review_liveness_by_run.items()
        if (
            state.get("conflict_events")
            or state.get("ambiguous_review_id_events")
        )
    }
    message_bus: list[dict[str, Any]] = []
    event_log: list[dict[str, Any]] = []
    conflict_control: list[dict[str, Any]] = []
    review_gates: list[dict[str, Any]] = []
    evidence_store: list[dict[str, Any]] = []
    # Real Agent Registry + Task Board, derived from the SAME recorded events
    # (no extra recording): a task per (run, agent) with a created->claimed->result
    # lifecycle, and an agent per participant with its latest recorded status.
    tasks_by_key: dict[tuple[str, str], dict[str, Any]] = {}
    task_kinds_by_key: dict[tuple[str, str], str] = {}
    active_reviewers: set[tuple[str, str]] = set()
    pass_review_tasks: dict[tuple[str, str], tuple[str, str]] = {}
    review_payloads_by_id: dict[tuple[str, str], dict[str, Any]] = {}
    explicit_review_runs: set[str] = set()
    execution_keys, _reviewer_keys = team_identity_ownership(records)
    execution_agents = {
        (_slug(run_id), _slug(agent_id)) for run_id, agent_id in execution_keys
    }
    agents_by_id: dict[str, dict[str, Any]] = {}
    evidence_keys: set[tuple[str, str]] = set()
    _role_words = {"controller", "coordinator", "reviewer", "planner", "executor"}
    explicit_evidence_keys = {
        (
            _slug(record.get("run_id")),
            str((record.get("payload") if isinstance(record.get("payload"), dict) else {}).get("ref_path") or ""),
        )
        for record in records
        if isinstance(record, dict) and str(record.get("event_type") or "") == "evidence_ref"
    }

    def _record_context_refs(event_id: str, run_id: str, payload: dict[str, Any]) -> None:
        refs = payload.get("context_refs") if isinstance(payload.get("context_refs"), list) else []
        for ref in refs:
            if not isinstance(ref, dict):
                continue
            ref_path = str(ref.get("ref_path") or "")
            if not ref_path or (run_id, ref_path) in evidence_keys:
                continue
            evidence_keys.add((run_id, ref_path))
            ref_type = str(ref.get("ref_type") or "legacy_context")
            evidence_store.append({
                "evidence_id": f"team-context-{event_id}-{_slug(ref_type)}-{_slug(ref_path)}",
                "run_id": run_id,
                "ref_type": ref_type,
                "ref_path": ref_path,
            })

    def _touch_agent(agent: str, status: str, role: str = "") -> None:
        if not agent:
            return
        record = agents_by_id.get(agent)
        if record is None:
            agents_by_id[agent] = {
                "agent_id": agent,
                "role": role or (agent if agent in _role_words else "worker"),
                "binding_id": "",
                "status": status,
                "session_ids": [],
            }
        else:
            record["status"] = status
            if role:
                record["role"] = role

    seen_conflicts: set[tuple[str, str]] = set()
    for record in records:
        if not isinstance(record, dict):
            continue
        event_type = str(record.get("event_type") or "")
        raw_run_id = str(record.get("run_id") or "")
        run_id = _slug(raw_run_id)
        raw_agent_id = str(record.get("agent_id") or "")
        agent_id = _slug(raw_agent_id)
        event_id = _slug(record.get("event_id"))
        payload = record.get("payload") if isinstance(record.get("payload"), dict) else {}
        if not event_id or not run_id:
            continue
        if event_type == "task_created":
            shard_index = payload.get("shard_index", "?")
            shard_count = payload.get("shard_count", "?")
            targets = payload.get("targets") if isinstance(payload.get("targets"), list) else []
            # Real Task Board entry + Agent Registry entry for this task.
            task_key = (run_id, agent_id)
            task_kind = _normalize_task_kind(payload.get("task_kind"))
            agent_role = str(payload.get("agent_role") or "worker")
            task_kinds_by_key[task_key] = task_kind
            if task_kind == TASK_KIND_INDEPENDENT_REVIEW:
                explicit_review_runs.add(run_id)
                if (
                    _is_independent_reviewer_identity(agent_id, agent_role)
                    and task_key not in execution_agents
                ):
                    active_reviewers.add(task_key)
            tasks_by_key[task_key] = {
                "task_id": _slug(f"team-task-{run_id}-{agent_id}"),
                "type": "go-run",
                "project_id": str(payload.get("project_id") or ""),
                "status": "created",
                "agent_ids": [agent_id] if agent_id else [],
                "session_ids": [],
                "target_files": [str(t) for t in targets if str(t)],
            }
            _touch_agent(agent_id, "assigned", agent_role)
            event_log.append({
                "event_id": f"team-{event_id}",
                "kind": "task-created",
                "run_id": run_id,
                "summary": f"Task created for {agent_id} (shard {shard_index}/{shard_count}) in run {run_id}.",
            })
            message_bus.append({
                "message_id": f"team-{event_id}",
                "from_role": "coordinator",
                "to_role": agent_id or "worker",
                "kind": "task-assign",
                "run_id": run_id,
                "summary": f"Coordinator assigned shard {shard_index}/{shard_count} to {agent_id}.",
            })
            # Real Conflict Control: each recorded target is owned by this agent
            # for this run. Deduplicate so re-runs do not double-list a file.
            for target in targets if task_kind == TASK_KIND_EXECUTION else []:
                file_path = str(target)
                key = (run_id, file_path)
                if not file_path or key in seen_conflicts:
                    continue
                seen_conflicts.add(key)
                conflict_control.append({
                    "file_path": file_path,
                    "owner_run_id": run_id,
                    "owner_agent_id": agent_id,
                    "file_kind": "target",
                })
            _record_context_refs(event_id, run_id, payload)
        elif event_type == "task_claimed":
            task = tasks_by_key.get((run_id, agent_id))
            if task is not None:
                task["status"] = "claimed"
            _touch_agent(agent_id, "working")
            event_log.append({
                "event_id": f"team-{event_id}",
                "kind": "task-claimed",
                "run_id": run_id,
                "summary": f"{agent_id} claimed its task in run {run_id}.",
            })
            message_bus.append({
                "message_id": f"team-{event_id}",
                "from_role": agent_id or "worker",
                "to_role": "coordinator",
                "kind": "claim",
                "run_id": run_id,
                "summary": f"{agent_id} -> coordinator: claimed task, working…",
            })
            _record_context_refs(event_id, run_id, payload)
        elif event_type == "task_result":
            execution_agents.add((run_id, agent_id))
            status = str(payload.get("status") or "unknown")
            task = tasks_by_key.get((run_id, agent_id))
            if task is not None:
                task["status"] = _task_status(status)
            _touch_agent(agent_id, _task_status(status))
            event_log.append({
                "event_id": f"team-{event_id}",
                "kind": "task-result",
                "run_id": run_id,
                "summary": f"{agent_id} reported {status} in run {run_id}.",
            })
            message_bus.append({
                "message_id": f"team-{event_id}",
                "from_role": agent_id or "worker",
                "to_role": "coordinator",
                "kind": "result",
                "run_id": run_id,
                "summary": f"{agent_id} -> coordinator: {status}.",
            })
            # Worker task results are execution outcomes only. A successful
            # worker result opens the review gate but cannot pass it.
            review_gates.append({
                "gate_id": f"team-acceptance-{event_id}",
                "kind": "acceptance",
                "status": _review_status(status),
                "reason": _review_reason(agent_id, run_id, status),
                "run_id": run_id,
            })
            # Real Evidence Store: a recorded evidence ref when the result
            # carried a report path.
            report_path = str(payload.get("report_path") or "")
            if report_path and (run_id, report_path) not in explicit_evidence_keys:
                evidence_keys.add((run_id, report_path))
                evidence_store.append({
                    "evidence_id": f"team-evidence-{event_id}",
                    "run_id": run_id,
                    "ref_type": "report",
                    "ref_path": report_path,
                })
        elif event_type == "task_progress":
            task = tasks_by_key.get((run_id, agent_id))
            if task is not None:
                task["status"] = "claimed"
            _touch_agent(agent_id, "working")
            status = str(payload.get("status") or "unknown")
            event_log.append({
                "event_id": f"team-{event_id}",
                "kind": "task-progress",
                "run_id": run_id,
                "summary": f"{agent_id} reported progress {status} in run {run_id}.",
            })
            message_bus.append({
                "message_id": f"team-{event_id}",
                "from_role": agent_id or "reviewer",
                "to_role": "coordinator",
                "kind": "progress",
                "run_id": run_id,
                "summary": f"{agent_id} -> coordinator: progress {status}.",
            })
        elif event_type == "evidence_ref":
            ref_path = str(payload.get("ref_path") or "")
            if ref_path:
                if (run_id, ref_path) not in evidence_keys:
                    evidence_keys.add((run_id, ref_path))
                    source_event_id = str(payload.get("source_event_id") or "")
                    evidence_id = _slug(source_event_id) if source_event_id else event_id
                    evidence_store.append({
                        "evidence_id": f"team-evidence-{evidence_id}",
                        "run_id": run_id,
                        "ref_type": str(payload.get("ref_type") or "artifact"),
                        "ref_path": ref_path,
                    })
                event_log.append({
                    "event_id": f"team-{event_id}",
                    "kind": "evidence-ref",
                    "run_id": run_id,
                    "summary": f"{agent_id} recorded evidence {ref_path} in run {run_id}.",
                })
        elif event_type == "review_ref":
            if raw_run_id in invalid_review_runs:
                continue
            raw_review_id = str(payload.get("review_id") or event_id)
            review_id = _slug(raw_review_id)
            verdict = str(payload.get("verdict") or "unknown")
            ref_path = str(payload.get("ref_path") or "")
            task_key = (run_id, agent_id)
            if (
                not _is_terminal_review_ref(payload, raw_agent_id)
                or task_key in execution_agents
                or (run_id in explicit_review_runs and task_key not in active_reviewers)
            ):
                continue
            review_payloads_by_id[
                (str(record.get("run_id") or ""), raw_review_id)
            ] = payload
            if verdict == "pass":
                pass_review_tasks[(run_id, review_id)] = task_key
            else:
                active_reviewers.discard(task_key)
            if (
                verdict != "pass"
                and task_kinds_by_key.get(task_key) == TASK_KIND_INDEPENDENT_REVIEW
            ):
                review_task = tasks_by_key.get(task_key)
                review_status = _review_task_status(verdict)
                if review_task is not None:
                    review_task["status"] = review_status
                _touch_agent(agent_id, review_status)
            event_log.append({
                "event_id": f"team-{event_id}",
                "kind": "review-ref",
                "run_id": run_id,
                "summary": f"{agent_id} recorded independent review {review_id}: {verdict}.",
            })
            message_bus.append({
                "message_id": f"team-{event_id}",
                "from_role": agent_id or "reviewer",
                "to_role": "coordinator",
                "kind": "review-verdict",
                "run_id": run_id,
                "summary": f"{agent_id} -> coordinator: review {verdict}.",
            })
            if ref_path and (run_id, ref_path) not in evidence_keys:
                evidence_keys.add((run_id, ref_path))
                evidence_store.append({
                    "evidence_id": f"team-review-{event_id}",
                    "run_id": run_id,
                    "ref_type": "review",
                    "ref_path": ref_path,
                })
            review_gates.append({
                "gate_id": f"team-review-{review_id}",
                "kind": "independent-review",
                "status": _review_gate_status(verdict),
                "reason": f"Independent review {review_id} reported {verdict}.",
                "run_id": run_id,
            })
        elif event_type == "final_verdict_ref":
            verdict_id = _slug(payload.get("verdict_id") or event_id)
            final_state = str(payload.get("final_state") or "deferred")
            ref_path = str(payload.get("ref_path") or "")
            raw_review_ref = str(payload.get("review_ref") or "")
            if raw_run_id in invalid_review_runs:
                continue
            review_payload = review_payloads_by_id.get(
                (raw_run_id, raw_review_ref)
            )
            if not review_payload or _final_verdict_diagnostic(record, review_payload):
                continue
            review_ref = _slug(raw_review_ref)
            review_task_key = pass_review_tasks.get((run_id, review_ref))
            if review_task_key is not None:
                active_reviewers.discard(review_task_key)
                review_status = _final_review_task_status(final_state)
                review_task = tasks_by_key.get(review_task_key)
                if review_task is not None:
                    review_task["status"] = review_status
                _touch_agent(review_task_key[1], review_status)
            event_log.append({
                "event_id": f"team-{event_id}",
                "kind": "final-verdict-ref",
                "run_id": run_id,
                "summary": f"{agent_id} recorded final verdict {verdict_id}: {final_state}.",
            })
            message_bus.append({
                "message_id": f"team-{event_id}",
                "from_role": agent_id or "governance",
                "to_role": "team",
                "kind": "final-verdict",
                "run_id": run_id,
                "summary": f"{agent_id} -> team: final verdict {final_state}.",
            })
            if ref_path and (run_id, ref_path) not in evidence_keys:
                evidence_keys.add((run_id, ref_path))
                evidence_store.append({
                    "evidence_id": f"team-final-verdict-{event_id}",
                    "run_id": run_id,
                    "ref_type": "final_verdict",
                    "ref_path": ref_path,
                })
            if not team_final_review_liveness_diagnostic(
                review_liveness_by_run.get(raw_run_id, {}),
                final_state,
                raw_review_ref,
            ):
                review_gates.append({
                    "gate_id": f"team-final-verdict-{verdict_id}",
                    "kind": "final-verdict",
                    "status": _final_verdict_gate_status(final_state),
                    "reason": f"Governance final verdict {verdict_id} reported {final_state}.",
                    "run_id": run_id,
                })
        elif event_type == "workflow_event":
            phase = str(payload.get("phase") or "phase")
            status = str(payload.get("status") or "")
            role = _slug(payload.get("role")) or "coordinator"
            _touch_agent(role, "active")
            summary = str(payload.get("summary") or f"{role} {phase}: {status}")
            event_log.append({
                "event_id": f"team-{event_id}",
                "kind": f"workflow-{_slug(phase)}",
                "run_id": run_id,
                "summary": summary,
            })
            # The controller's final decision is also a message to the team.
            if _slug(phase) in {"review", "decide", "verdict"}:
                message_bus.append({
                    "message_id": f"team-{event_id}",
                    "from_role": role,
                    "to_role": "team",
                    "kind": "workflow-verdict",
                    "run_id": run_id,
                    "summary": summary,
                })
        elif event_type == "agent_message":
            to_agent_id = str(payload.get("to_agent_id") or "")
            msg_kind = str(payload.get("kind") or "")
            msg_summary = str(payload.get("summary") or "")
            message_bus.append({
                "message_id": f"team-{event_id}",
                "from_role": agent_id,
                "to_role": to_agent_id,
                "kind": msg_kind,
                "run_id": run_id,
                "summary": msg_summary,
            })
            event_log.append({
                "event_id": f"team-{event_id}",
                "kind": "agent-message",
                "run_id": run_id,
                "summary": msg_summary,
            })
    for raw_run_id in sorted(invalid_review_runs):
        run_id = _slug(raw_run_id)
        review_gates.append({
            "gate_id": f"team-review-assignment-{run_id}",
            "kind": "independent-review",
            "status": "blocked",
            "reason": (
                "Concurrent assignments or ambiguous review IDs were "
                "recorded."
            ),
            "run_id": run_id,
        })
    return {
        "message_bus": message_bus,
        "event_log": event_log,
        "conflict_control": conflict_control,
        "review_gates": review_gates,
        "agent_registry": list(agents_by_id.values()),
        "task_board": list(tasks_by_key.values()),
        "evidence_store": evidence_store,
    }


def _task_status(status: str) -> str:
    normalized = str(status or "").strip().lower()
    if normalized in {"pass", "passed", "completed", "verified", "done"}:
        return "completed"
    if normalized in {"fail", "failed", "error"}:
        return "failed"
    if normalized in {"blocked"}:
        return "blocked"
    return normalized or "unknown"


def _review_status(status: str) -> str:
    normalized = str(status or "").strip().lower()
    if normalized in {"pass", "passed", "completed", "verified"}:
        return "open"
    if normalized in {"fail", "failed", "error"}:
        return "failed"
    if normalized in {"blocked"}:
        return "blocked"
    return "open"


def _review_gate_status(verdict: str) -> str:
    normalized = str(verdict or "").strip().lower()
    if normalized == "pass":
        return "pass"
    if normalized == "fail":
        return "failed"
    if normalized in {"blocked", "escalate"}:
        return "blocked"
    return "open"


def _review_task_status(verdict: str) -> str:
    normalized = str(verdict or "").strip().lower()
    if normalized == "pass":
        return "completed"
    if normalized == "fail":
        return "failed"
    if normalized in {"blocked", "escalate"}:
        return "blocked"
    return "claimed"


def _final_review_task_status(final_state: str) -> str:
    normalized = str(final_state or "").strip().lower()
    if normalized in {"final_ready", "accepted_with_limitation"}:
        return "completed"
    if normalized == "failed":
        return "failed"
    return "blocked"


def _final_verdict_gate_status(final_state: str) -> str:
    normalized = str(final_state or "").strip().lower()
    if normalized == "final_ready":
        return "pass"
    if normalized == "failed":
        return "failed"
    if normalized == "blocked":
        return "blocked"
    return "open"


def _review_reason(agent_id: str, run_id: str, status: str) -> str:
    normalized = str(status or "").strip().lower()
    if normalized in {"pass", "passed", "completed", "verified"}:
        return (
            f"Recorded worker result for {agent_id} in run {run_id}: {status}; "
            "independent review is still required."
        )
    return f"Recorded result for {agent_id} in run {run_id}: {status}."
