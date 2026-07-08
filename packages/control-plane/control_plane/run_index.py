"""Read-only canonical RunRecord projections for legacy runtime files."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml
from jsonschema.validators import validator_for

from .backup_guard import default_runtime_dir
from .team_runtime import TEAM_EVENTS_FILE

ADAPTER_VERSION = "run-index.0.1"
SCHEMA_VERSION = "0.1"


def build_run_index(
    runtime_dir: str | Path | None = None,
    *,
    paper_project_dirs: list[str | Path] | None = None,
) -> dict[str, Any]:
    """Build a read-only index of canonical RunRecord projections.

    The index is intentionally not a writable authority. It adapts legacy files
    in place and keeps adapter provenance outside the schema-compatible record.
    """
    runtime = Path(runtime_dir).resolve() if runtime_dir else default_runtime_dir()
    entries: list[dict[str, Any]] = []
    entries.extend(_rdgoal_entries(runtime))
    entries.extend(_go_run_entries(runtime))
    entries.extend(_team_event_entries(runtime))
    entries.extend(_atgo_entries(runtime))
    entries.extend(_test_run_entries(runtime))
    for project_dir in paper_project_dirs or []:
        entries.extend(_paper_entries(Path(project_dir).resolve()))
    entries.sort(key=lambda item: (
        item["record"]["run_id"],
        item["adapter_id"],
        item["provenance"]["source_path"],
    ))
    return {
        "schema_version": SCHEMA_VERSION,
        "adapter_version": ADAPTER_VERSION,
        "runtime_dir": str(runtime),
        "runs": entries,
    }


def _rdgoal_entries(runtime: Path) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    reports_by_packet: dict[str, dict[str, Any]] = {}
    reports_root = runtime / "rdgoal-reports"
    if reports_root.exists():
        for report_path in sorted(reports_root.glob("*/*/execution-summary.json")):
            report, diagnostic = _read_json_file(report_path)
            if diagnostic:
                entries.append(_failure_entry("rdgoal", report_path.parent.name, report_path, diagnostic))
                continue
            packet_id = str(report.get("packet_id") or report_path.parent.name)
            reports_by_packet[packet_id] = report

    seen_packets: set[str] = set()
    journal_path = runtime / "rdgoal-events.jsonl"
    for item in _read_jsonl_with_diagnostics(journal_path):
        if item.get("diagnostic"):
            entries.append(_failure_entry("rdgoal", item["legacy_id"], journal_path, item["diagnostic"]))
            continue
        event = item["record"]
        if event.get("event_type") != "decision_made":
            continue
        payload = _as_dict(event.get("payload"))
        packet_dir = str(payload.get("packet_dir") or "")
        packet_id = Path(packet_dir).name if packet_dir else _safe_token(str(event.get("event_id") or item["legacy_id"]))
        seen_packets.add(packet_id)
        report = reports_by_packet.get(packet_id)
        source_path = journal_path
        packet_path = Path(packet_dir) / "packet.json" if packet_dir else None
        entries.append(_entry(
            adapter_id="rdgoal",
            source_type="rdgoal_decision",
            source_path=source_path,
            legacy_id=packet_id,
            record=_make_record(
                legacy_id=packet_id,
                project_id=str(event.get("project_id") or payload.get("project_id") or "unknown-project"),
                domain="code",
                profile="rdgoal",
                status=str((report or {}).get("status") or ("queued" if payload.get("dispatch_ready") else "blocked")),
                source_path=source_path,
                adapter_id="rdgoal",
                created_at=str(event.get("timestamp") or _mtime_iso(journal_path)),
                task_id=packet_id,
                artifact_refs=_artifact_refs(source_path, packet_path, packet_dir),
                evidence_refs=_report_evidence_refs(report),
                worker_results=_worker_results(report),
                domain_refs={
                    "legacy_adapter": "rdgoal",
                    "packet_id": packet_id,
                    "event_id": event.get("event_id", ""),
                    "decision_mode": payload.get("decision_mode", ""),
                    "dispatch_ready": bool(payload.get("dispatch_ready", False)),
                    "operation": payload.get("operation", ""),
                },
            ),
        ))

    for packet_id, report in reports_by_packet.items():
        if packet_id in seen_packets:
            continue
        source_path = Path(str(report.get("report_path") or reports_root / packet_id))
        entries.append(_entry(
            adapter_id="rdgoal",
            source_type="rdgoal_report",
            source_path=source_path,
            legacy_id=packet_id,
            record=_make_record(
                legacy_id=packet_id,
                project_id=str(report.get("project_id") or "unknown-project"),
                domain="code",
                profile="rdgoal",
                status=str(report.get("status") or "unknown"),
                source_path=source_path,
                adapter_id="rdgoal",
                created_at=str(report.get("ingested_at") or _mtime_iso(source_path)),
                task_id=packet_id,
                artifact_refs=_artifact_refs(source_path),
                evidence_refs=_report_evidence_refs(report),
                worker_results=_worker_results(report),
                domain_refs={
                    "legacy_adapter": "rdgoal",
                    "packet_id": packet_id,
                    "report_path": report.get("report_path", ""),
                },
            ),
        ))
    return entries


def _go_run_entries(runtime: Path) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for path in sorted((runtime / "go-runs").glob("*/go-run.json")):
        data, diagnostic = _read_json_file(path)
        legacy_id = str(data.get("go_run_id") or path.parent.name) if data else path.parent.name
        if diagnostic:
            entries.append(_failure_entry("go_run", legacy_id, path, diagnostic))
            continue
        agents = data.get("agents") if isinstance(data.get("agents"), list) else []
        evidence_refs = _agent_evidence_refs(agents)
        entries.append(_entry(
            adapter_id="go_run",
            source_type="go_run_metadata",
            source_path=path,
            legacy_id=legacy_id,
            record=_make_record(
                legacy_id=legacy_id,
                project_id=str(data.get("project_id") or "unknown-project"),
                domain="code",
                profile="go",
                status=str(data.get("status") or "unknown"),
                source_path=path,
                adapter_id="go_run",
                created_at=str(data.get("created_at") or _mtime_iso(path)),
                task_id=legacy_id,
                artifact_refs=_artifact_refs(path),
                evidence_refs=evidence_refs,
                worker_results=_go_worker_results(agents, str(data.get("created_at") or _mtime_iso(path))),
                domain_refs={
                    "legacy_adapter": "go_run",
                    "go_run_id": legacy_id,
                    "execute": bool(data.get("execute", False)),
                    "driver": data.get("driver", ""),
                    "model_provider": data.get("model_provider", ""),
                    "agent_count": len(agents),
                },
            ),
        ))
    return entries


def _team_event_entries(runtime: Path) -> list[dict[str, Any]]:
    path = runtime / TEAM_EVENTS_FILE
    events_by_run: dict[str, list[dict[str, Any]]] = {}
    entries: list[dict[str, Any]] = []
    for item in _read_jsonl_with_diagnostics(path):
        if item.get("diagnostic"):
            entries.append(_failure_entry("team_events", item["legacy_id"], path, item["diagnostic"]))
            continue
        event = item["record"]
        run_id = str(event.get("run_id") or "")
        if run_id:
            events_by_run.setdefault(run_id, []).append(event)
    for run_id, events in sorted(events_by_run.items()):
        latest = events[-1]
        result_events = [event for event in events if event.get("event_type") == "task_result"]
        context_refs = _team_context_refs(events)
        worker_agent_ids = _team_worker_agent_ids(result_events)
        review_refs, review_failures = _team_review_refs(events, worker_agent_ids)
        final_verdict_ref, final_failures, limitations, gate_refs = _team_final_verdict_ref(
            events,
            review_refs,
            worker_agent_ids,
            context_refs,
        )
        failure_refs = review_failures + final_failures
        status = _aggregate_team_status(result_events)
        entries.append(_entry(
            adapter_id="team_events",
            source_type="team_event_journal",
            source_path=path,
            legacy_id=run_id,
            record=_make_record(
                legacy_id=run_id,
                project_id=_team_project_id(events),
                domain="code",
                profile="team-runtime",
                status=status,
                source_path=path,
                adapter_id="team_events",
                created_at=str(events[0].get("timestamp") or _mtime_iso(path)),
                updated_at=str(latest.get("timestamp") or _mtime_iso(path)),
                task_id=run_id,
                artifact_refs=_artifact_refs(path) + _team_context_artifact_refs(context_refs),
                evidence_refs=_team_context_evidence_refs(context_refs) + _team_evidence_refs(events),
                review_refs=review_refs,
                gate_refs=gate_refs,
                final_verdict_ref=final_verdict_ref,
                failure_refs=failure_refs,
                limitations=limitations,
                worker_results=_team_worker_results(result_events),
                domain_refs={
                    "legacy_adapter": "team_events",
                    "source_run_id": run_id,
                    "event_count": len(events),
                    "event_types": sorted({str(event.get("event_type") or "") for event in events}),
                    "legacy_context_ref_count": len(context_refs),
                    "legacy_context_ref_types": sorted({ref["ref_type"] for ref in context_refs}),
                    "sealed_context_packet_ref_count": len([
                        ref for ref in context_refs if ref["ref_type"] == "context_packet"
                    ]),
                    "context_ledger_ref_count": len([
                        ref for ref in context_refs if ref["ref_type"] == "context_ledger"
                    ]),
                    "review_ref_count": len(review_refs),
                    "gate_ref_count": len(gate_refs),
                    "final_verdict_ref_present": bool(final_verdict_ref),
                },
            ),
        ))
    return entries


def _atgo_entries(runtime: Path) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    base = runtime / "atgo-runs"
    if not base.exists():
        return entries
    for run_dir in sorted(path for path in base.iterdir() if path.is_dir()):
        review_path = run_dir / "review.yaml"
        legacy_id = run_dir.name
        if not review_path.exists():
            chain_path = run_dir / "chain-evidence.json"
            chain_evidence, diagnostic = _read_json_file(chain_path)
            if diagnostic:
                entries.append(_failure_entry(
                    "atgo_evidence",
                    legacy_id,
                    review_path,
                    f"missing review.yaml and {diagnostic}",
                ))
                continue
            next_commands = _as_dict(chain_evidence.get("next_commands"))
            finalize_command = _as_dict(next_commands.get("finalize"))
            entries.append(_entry(
                adapter_id="atgo_evidence",
                source_type="atgo_prepare",
                source_path=chain_path,
                legacy_id=legacy_id,
                record=_make_record(
                    legacy_id=legacy_id,
                    project_id=str(chain_evidence.get("project_id") or "unknown-project"),
                    domain="review",
                    profile="atgo",
                    status="prepared",
                    source_path=chain_path,
                    adapter_id="atgo_evidence",
                    created_at=str(
                        _as_dict(chain_evidence.get("timestamps")).get("created_at")
                        or _mtime_iso(chain_path)
                    ),
                    task_id=str(chain_evidence.get("task") or legacy_id),
                    artifact_refs=_artifact_refs(chain_path, run_dir),
                    evidence_refs=[
                        _evidence_ref(
                            f"ev-atgo-chain-{_safe_token(legacy_id)}",
                            "other",
                            chain_path,
                            "limitation",
                        )
                    ],
                    limitations=["independent review evidence is not recorded yet"],
                    domain_refs={
                        "legacy_adapter": "atgo_evidence",
                        "go_run_id": legacy_id,
                        "mode": str(chain_evidence.get("mode") or "prepare"),
                        "finalizer_command": finalize_command.get("command", ""),
                        "finalizer_command_args": finalize_command.get("command_args", []),
                        "finalizer_authority": finalize_command.get("authority", ""),
                        "finalizer_creates_acceptance": finalize_command.get(
                            "creates_acceptance",
                            None,
                        ),
                        "finalizer_requires_independent_review": finalize_command.get(
                            "requires_independent_review",
                            None,
                        ),
                        "finalizer_manual": finalize_command.get("manual", None),
                    },
                ),
            ))
            continue
        review, diagnostic = _read_yaml_file(review_path)
        if diagnostic:
            entries.append(_failure_entry("atgo_evidence", legacy_id, review_path, diagnostic))
            continue
        verdict = str(review.get("verdict") or "unknown")
        evidence_refs = [
            _evidence_ref(f"ev-atgo-review-{_safe_token(legacy_id)}", "review", review_path, "review")
        ]
        unsafe_review = _unsafe_atgo_review(review)
        if unsafe_review:
            failure = {
                "failure_id": f"failure-atgo-review-{_safe_token(legacy_id)}",
                "status": "blocked",
                "uri": str(review_path),
            }
            record = _make_record(
                legacy_id=legacy_id,
                project_id=str(review.get("project_id") or "unknown-project"),
                domain="review",
                profile="atgo",
                status="blocked",
                source_path=review_path,
                adapter_id="atgo_evidence",
                created_at=_mtime_iso(review_path),
                task_id=legacy_id,
                artifact_refs=_artifact_refs(review_path, run_dir),
                evidence_refs=evidence_refs,
                failure_refs=[failure],
                domain_refs={
                    "legacy_adapter": "atgo_evidence",
                    "go_run_id": legacy_id,
                    "verdict": verdict,
                    "diagnostic": unsafe_review,
                    "reviewer_role": review.get("reviewer_role", ""),
                    "reviewer_id": review.get("reviewer_id", ""),
                    "executor_id": review.get("executor_id", ""),
                },
            )
            entries.append(_entry(
                adapter_id="atgo_evidence",
                source_type="atgo_review",
                source_path=review_path,
                legacy_id=legacy_id,
                record=record,
            ))
            continue
        review_refs = _review_refs(legacy_id, review_path, verdict, review)
        entries.append(_entry(
            adapter_id="atgo_evidence",
            source_type="atgo_review",
            source_path=review_path,
            legacy_id=legacy_id,
            record=_make_record(
                legacy_id=legacy_id,
                project_id=str(review.get("project_id") or "unknown-project"),
                domain="review",
                profile="atgo",
                status=verdict,
                source_path=review_path,
                adapter_id="atgo_evidence",
                created_at=_mtime_iso(review_path),
                task_id=legacy_id,
                artifact_refs=_artifact_refs(review_path, run_dir),
                evidence_refs=evidence_refs,
                review_refs=review_refs,
                domain_refs={
                    "legacy_adapter": "atgo_evidence",
                    "go_run_id": legacy_id,
                    "verdict": verdict,
                },
            ),
        ))
    return entries


def _unsafe_atgo_review(review: dict[str, Any]) -> str:
    reviewer_role_raw = str(review.get("reviewer_role") or "").strip()
    reviewer_role = _safe_token(reviewer_role_raw)
    reviewer_id = str(review.get("reviewer_id") or "").strip()
    executor_id = str(review.get("executor_id") or "").strip()
    if not reviewer_role_raw:
        return "reviewer_role is missing"
    if not reviewer_id:
        return "reviewer_id is missing"
    if reviewer_role in {"executor", "fixer", "coder", "worker"}:
        return f"reviewer role is not independent: {reviewer_role}"
    if reviewer_id and executor_id and reviewer_id == executor_id:
        return "reviewer_id matches executor_id"
    return ""


def _paper_entries(project_dir: Path) -> list[dict[str, Any]]:
    profile_path = project_dir / "PAPER_PROFILE.yaml"
    state_path = project_dir / "PAPER_STATE.yaml"
    profile, profile_diag = _read_yaml_file(profile_path)
    if profile_diag:
        return [_failure_entry("paper", project_dir.name, profile_path, profile_diag)]
    state, state_diag = _read_yaml_file(state_path)
    paper_id = str(profile.get("paper_id") or state.get("paper_id") or project_dir.name)
    if state_diag:
        return [_failure_entry("paper", paper_id, state_path, state_diag)]
    status = str(state.get("acceptance_status") or state.get("status") or "unknown")
    task_input = project_dir / "paper_task" / "PAPER_TASK_INPUT.yaml"
    evidence_refs = []
    if task_input.exists():
        evidence_refs.append(_evidence_ref(f"ev-paper-task-{_safe_token(paper_id)}", "context_packet", task_input, "outcome"))
    failure_refs = []
    normalized_status = _safe_token(status).replace("_", "-")
    if normalized_status in {"human-required", "needs-human"}:
        failure_refs.append({
            "failure_id": f"failure-paper-human-gate-{_safe_token(paper_id)}",
            "status": "blocked",
            "uri": str(state_path),
        })
    entries = [_entry(
        adapter_id="paper",
        source_type="paper_project",
        source_path=profile_path,
        legacy_id=paper_id,
        record=_make_record(
            legacy_id=f"paper-{paper_id}",
            project_id=paper_id,
            domain="paper",
            profile="rdpaper",
            status=status,
            source_path=profile_path,
            adapter_id="paper",
            created_at=_mtime_iso(profile_path),
            updated_at=_mtime_iso(state_path if state_path.exists() else profile_path),
            task_id=paper_id,
            artifact_refs=_artifact_refs(profile_path, state_path, project_dir / "PAPER_LEDGER.md"),
            evidence_refs=evidence_refs,
            failure_refs=failure_refs,
            domain_refs={
                "legacy_adapter": "paper",
                "paper_id": paper_id,
                "current_stage": state.get("current_stage") or profile.get("current_stage", ""),
                "acceptance_status": state.get("acceptance_status", ""),
                "chain_trusted": state.get("chain_trusted"),
            },
        ),
    )]
    return entries


def _test_run_entries(runtime: Path) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for path in sorted((runtime / "test-runs").glob("*/test-run.json")):
        data, diagnostic = _read_json_file(path)
        legacy_id = str(data.get("test_run_id") or data.get("run_id") or path.parent.name) if data else path.parent.name
        if diagnostic:
            entries.append(_failure_entry("test_run", legacy_id, path, diagnostic))
            continue
        status = str(data.get("status") or data.get("overall_status") or "unknown")
        report_path_text = str(data.get("report_path") or "").strip()
        report_path = Path(report_path_text) if report_path_text else path
        report_missing = _safe_token(status) in {"pass", "passed"} and (
            not report_path_text or not report_path.exists()
        )
        effective_status = "blocked" if report_missing else status
        evidence_refs = []
        if report_path_text and report_path.exists():
            evidence_refs.append(_evidence_ref(f"ev-test-{_safe_token(legacy_id)}", "test_output", report_path, "outcome"))
        failure_refs = []
        if report_missing:
            failure_refs.append({
                "failure_id": f"failure-test-report-{_safe_token(legacy_id)}",
                "status": "blocked",
                "uri": str(report_path),
            })
        entries.append(_entry(
            adapter_id="test_run",
            source_type="test_run_metadata",
            source_path=path,
            legacy_id=legacy_id,
            record=_make_record(
                legacy_id=f"test-{legacy_id}",
                project_id=str(data.get("project_id") or "unknown-project"),
                domain="test",
                profile="test-frame",
                status=effective_status,
                source_path=path,
                adapter_id="test_run",
                created_at=str(data.get("created_at") or _mtime_iso(path)),
                task_id=str(data.get("task_id") or legacy_id),
                artifact_refs=_artifact_refs(path),
                evidence_refs=evidence_refs,
                worker_results=[_worker_result("test-frame", "tester", status, str(data.get("created_at") or _mtime_iso(path)))],
                failure_refs=failure_refs,
                domain_refs={
                    "legacy_adapter": "test_run",
                    "test_run_id": legacy_id,
                    "aggregate_status": status,
                    "diagnostic": "test report is missing for passed aggregate" if report_missing else "",
                    "codeReview": _as_dict(data.get("verdicts")).get("codeReview", ""),
                    "quality_gate_passed": _as_dict(data.get("quality_gate")).get("passed"),
                },
            ),
        ))
    return entries


def _make_record(
    *,
    legacy_id: str,
    project_id: str,
    domain: str,
    profile: str,
    status: str,
    source_path: Path,
    adapter_id: str,
    created_at: str,
    task_id: str,
    updated_at: str | None = None,
    artifact_refs: list[dict[str, Any]] | None = None,
    evidence_refs: list[dict[str, Any]] | None = None,
    review_refs: list[dict[str, Any]] | None = None,
    gate_refs: list[dict[str, Any]] | None = None,
    final_verdict_ref: dict[str, Any] | None = None,
    limitations: list[str] | None = None,
    worker_results: list[dict[str, Any]] | None = None,
    failure_refs: list[dict[str, Any]] | None = None,
    domain_refs: dict[str, Any] | None = None,
) -> dict[str, Any]:
    run_token = _safe_token(legacy_id)
    axes = _axes(
        status,
        adapter_id=adapter_id,
        review_refs=review_refs or [],
        gate_refs=gate_refs or [],
        final_verdict_ref=final_verdict_ref,
        failure_refs=failure_refs or [],
    )
    refs = {
        "adapter_version": ADAPTER_VERSION,
        "source_path": str(source_path),
        "legacy_status": status,
    }
    refs.update(domain_refs or {})
    refs = {key: value for key, value in refs.items() if value is not None}
    record = {
        "schema_version": SCHEMA_VERSION,
        "run_id": f"run-{run_token}",
        "project_id": project_id or "unknown-project",
        "goal_id": f"goal-{_safe_token(project_id or profile)}",
        "task_id": task_id or run_token,
        "attempt_id": f"attempt-{run_token}-1",
        "context_packet_id": f"cp-legacy-{run_token}",
        "context_ledger_id": f"cl-legacy-{run_token}",
        "domain": domain,
        "profile": profile,
        "producer_role": "runtime_adapter",
        "created_at": _date_time(created_at),
        "updated_at": _date_time(updated_at or created_at),
        "phase": axes["phase"],
        "outcome": axes["outcome"],
        "review_state": axes["review_state"],
        "gate_state": axes["gate_state"],
        "acceptance_state": axes["acceptance_state"],
        "projection_state": axes["projection_state"],
        "worker_results": worker_results or [],
        "artifact_refs": artifact_refs or [],
        "evidence_refs": evidence_refs or [],
        "review_refs": review_refs or [],
        "gate_refs": gate_refs or [],
        "failure_refs": failure_refs or [],
        "domain_refs": refs,
    }
    if final_verdict_ref:
        record["final_verdict_ref"] = final_verdict_ref
    if limitations:
        record["limitations"] = limitations
    return record


def _axes(
    status: str,
    *,
    adapter_id: str,
    review_refs: list[dict[str, Any]],
    gate_refs: list[dict[str, Any]],
    final_verdict_ref: dict[str, Any] | None,
    failure_refs: list[dict[str, Any]],
) -> dict[str, str]:
    normalized = _safe_token(status).replace("_", "-")
    if (
        final_verdict_ref
        and final_verdict_ref.get("final_state") == "final_ready"
        and _has_pass_review(review_refs)
        and _has_pass_gate(gate_refs)
    ):
        return _axis("closed", "passed", "review_passed", "gate_passed", "final_ready", "completed")
    if final_verdict_ref and final_verdict_ref.get("final_state") == "blocked":
        return _axis("closed", "blocked", "review_blocked", "gate_blocked", "blocked", "blocked")
    if final_verdict_ref and final_verdict_ref.get("final_state") == "failed":
        return _axis("closed", "failed", "review_failed", "gate_failed", "failed", "failed")
    if failure_refs and adapter_id == "team_events":
        return _axis("closed", "blocked", "not_reviewed", "gate_blocked", "blocked", "blocked")
    if normalized in {"queued", "prepared", "ready", "deferred", "draft", ""}:
        return _axis("prepared", "unknown", "not_reviewed", "not_evaluated", "deferred", "queued")
    if normalized in {"running", "reviewing"}:
        return _axis("running", "unknown", "review_pending", "gate_pending", "review_pending", "running")
    if normalized in {"pass", "passed", "completed", "success", "succeeded", "verified", "accepted"}:
        review_state = "review_passed" if review_refs else "review_pending"
        return _axis("awaiting_review", "passed", review_state, "not_evaluated", "review_pending", "completed")
    if normalized in {"blocked", "hard-stop", "human-required", "needs-human", "insufficient-evidence"}:
        outcome = "human_required" if normalized in {"human-required", "needs-human"} else "blocked"
        projection = "waiting_for_you" if outcome == "human_required" else "blocked"
        review_state = "review_blocked" if adapter_id == "atgo_evidence" else "not_reviewed"
        return _axis("closed", outcome, review_state, "gate_blocked", "blocked", projection)
    if normalized in {"fail", "failed", "failure", "error", "cancelled"}:
        outcome = "cancelled" if normalized == "cancelled" else "failed"
        return _axis("closed", outcome, "review_failed", "gate_failed", "failed", "failed")
    return _axis("closed", "unknown", "not_reviewed", "not_evaluated", "deferred", "unknown")


def _axis(
    phase: str,
    outcome: str,
    review_state: str,
    gate_state: str,
    acceptance_state: str,
    projection_state: str,
) -> dict[str, str]:
    return {
        "phase": phase,
        "outcome": outcome,
        "review_state": review_state,
        "gate_state": gate_state,
        "acceptance_state": acceptance_state,
        "projection_state": projection_state,
    }


def _entry(
    *,
    adapter_id: str,
    source_type: str,
    source_path: Path,
    legacy_id: str,
    record: dict[str, Any],
) -> dict[str, Any]:
    return {
        "adapter_id": adapter_id,
        "source_type": source_type,
        "adapter_version": ADAPTER_VERSION,
        "provenance": {
            "source_path": str(source_path),
            "legacy_id": legacy_id,
            "adapter_version": ADAPTER_VERSION,
            "source_hash": _source_hash(source_path),
        },
        "record": record,
    }


def _failure_entry(adapter_id: str, legacy_id: str, source_path: Path, diagnostic: str) -> dict[str, Any]:
    token = _safe_token(f"{adapter_id}-{legacy_id}")
    failure = {
        "failure_id": f"failure-{token}",
        "status": "blocked",
        "uri": str(source_path),
    }
    record = _make_record(
        legacy_id=token,
        project_id="unknown-project",
        domain="general",
        profile=adapter_id,
        status="blocked",
        source_path=source_path,
        adapter_id=adapter_id,
        created_at=_mtime_iso(source_path),
        task_id=legacy_id or token,
        artifact_refs=_artifact_refs(source_path),
        failure_refs=[failure],
        domain_refs={
            "legacy_adapter": adapter_id,
            "diagnostic": diagnostic,
            "source_path": str(source_path),
        },
    )
    return _entry(
        adapter_id=adapter_id,
        source_type="failure_record",
        source_path=source_path,
        legacy_id=legacy_id,
        record=record,
    )


def _read_json_file(path: Path) -> tuple[dict[str, Any], str]:
    if not path.exists():
        return {}, f"missing JSON file: {path}"
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except OSError as exc:
        return {}, f"unable to read JSON file: {type(exc).__name__}: {exc}"
    except json.JSONDecodeError as exc:
        return {}, f"invalid JSON at line {exc.lineno}, column {exc.colno}: {exc.msg}"
    if not isinstance(data, dict):
        return {}, "JSON root is not an object"
    return data, ""


def _read_yaml_file(path: Path) -> tuple[dict[str, Any], str]:
    if not path.exists():
        return {}, f"missing YAML file: {path}"
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8-sig"))
    except OSError as exc:
        return {}, f"unable to read YAML file: {type(exc).__name__}: {exc}"
    except yaml.YAMLError as exc:
        return {}, f"invalid YAML: {exc}"
    if data is None:
        return {}, ""
    if not isinstance(data, dict):
        return {}, "YAML root is not an object"
    return data, ""


def _read_jsonl_with_diagnostics(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    items: list[dict[str, Any]] = []
    try:
        lines = path.read_text(encoding="utf-8-sig").splitlines()
    except OSError as exc:
        return [{
            "legacy_id": path.name,
            "diagnostic": f"unable to read JSONL file: {type(exc).__name__}: {exc}",
        }]
    for index, line in enumerate(lines, start=1):
        stripped = line.strip()
        if not stripped:
            continue
        try:
            data = json.loads(stripped)
        except json.JSONDecodeError as exc:
            items.append({
                "legacy_id": f"{path.stem}-line-{index}",
                "diagnostic": f"invalid JSONL line {index}, column {exc.colno}: {exc.msg}",
            })
            continue
        if not isinstance(data, dict):
            items.append({
                "legacy_id": f"{path.stem}-line-{index}",
                "diagnostic": f"JSONL line {index} root is not an object",
            })
            continue
        items.append({"legacy_id": f"{path.stem}-line-{index}", "record": data})
    return items


def _artifact_refs(*paths: str | Path) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    for path in paths:
        if not path:
            continue
        candidate = Path(path)
        uri = str(candidate)
        if not uri:
            continue
        refs.append({
            "artifact_id": f"artifact-{_safe_token(uri)}",
            "kind": "other",
            "uri": uri,
        })
    return refs


def _report_evidence_refs(report: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not report:
        return []
    report_path = str(report.get("report_path") or "")
    if not report_path:
        return []
    return [_evidence_ref(
        f"ev-report-{_safe_token(report.get('packet_id') or report_path)}",
        "command_output",
        Path(report_path),
        "outcome",
    )]


def _agent_evidence_refs(agents: list[Any]) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    for agent in agents:
        if not isinstance(agent, dict):
            continue
        report_path = str(agent.get("report_path") or "")
        if report_path:
            refs.append(_evidence_ref(
                f"ev-go-{_safe_token(agent.get('agent_id') or report_path)}",
                "command_output",
                Path(report_path),
                "outcome",
            ))
    return refs


def _team_context_refs(events: list[dict[str, Any]]) -> list[dict[str, str]]:
    refs: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for event in events:
        event_type = str(event.get("event_type") or "")
        if event_type not in {"task_created", "task_claimed"}:
            continue
        payload = _as_dict(event.get("payload"))
        context_refs = payload.get("context_refs") if isinstance(payload.get("context_refs"), list) else []
        for item in context_refs:
            if not isinstance(item, dict):
                continue
            ref_path = str(item.get("ref_path") or "")
            ref_type = str(item.get("ref_type") or "legacy_context")
            if not ref_path or (ref_type, ref_path) in seen:
                continue
            seen.add((ref_type, ref_path))
            refs.append({
                "ref_type": ref_type,
                "ref_path": ref_path,
                "context_id": str(item.get("context_id") or ""),
                "agent_id": str(event.get("agent_id") or ""),
                "event_id": str(event.get("event_id") or ""),
            })
    return refs


def _team_context_artifact_refs(refs: list[dict[str, str]]) -> list[dict[str, Any]]:
    artifacts: list[dict[str, Any]] = []
    for ref in refs:
        artifact = {
            "artifact_id": f"artifact-team-context-{_safe_token(ref['ref_type'])}-{_safe_token(ref['ref_path'])}",
            "kind": _team_context_artifact_kind(ref["ref_type"]),
            "uri": ref["ref_path"],
        }
        content_hash = _source_hash(Path(ref["ref_path"]))
        if content_hash:
            artifact["content_hash"] = content_hash
        artifacts.append(artifact)
    return artifacts


def _team_context_artifact_kind(ref_type: str) -> str:
    token = _safe_token(ref_type)
    if token in {"context_packet", "context-packet"}:
        return "context_packet"
    if token in {"context_ledger", "context-ledger"}:
        return "context_ledger"
    return "other"


def _team_context_evidence_refs(refs: list[dict[str, str]]) -> list[dict[str, Any]]:
    return [
        _evidence_ref(
            (
                f"ev-team-context-{_safe_token(ref['event_id'] or ref['ref_path'])}-"
                f"{_safe_token(ref['ref_type'])}-{_safe_token(ref['ref_path'])}"
            ),
            "context_packet",
            Path(ref["ref_path"]),
            "limitation",
        )
        for ref in refs
        if _safe_token(ref["ref_type"]) != "context_ledger"
    ]


def _team_evidence_refs(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    seen_paths: set[str] = set()
    explicit_paths = {
        str(_as_dict(event.get("payload")).get("ref_path") or "")
        for event in events
        if event.get("event_type") == "evidence_ref"
    }
    for event in events:
        event_type = str(event.get("event_type") or "")
        payload = _as_dict(event.get("payload"))
        if event_type == "evidence_ref":
            ref_path = str(payload.get("ref_path") or "")
            if not ref_path or ref_path in seen_paths:
                continue
            seen_paths.add(ref_path)
            source_event_id = str(payload.get("source_event_id") or "")
            refs.append(_evidence_ref(
                f"ev-team-{_safe_token(source_event_id or event.get('event_id') or ref_path)}",
                _team_evidence_kind(str(payload.get("ref_type") or "")),
                Path(ref_path),
                "outcome",
            ))
            continue
        if event_type == "review_ref":
            ref_path = str(payload.get("ref_path") or "")
            if not ref_path or ref_path in seen_paths:
                continue
            seen_paths.add(ref_path)
            refs.append(_evidence_ref(
                f"ev-team-review-{_safe_token(event.get('event_id') or ref_path)}",
                "review",
                Path(ref_path),
                "review",
            ))
            continue
        if event_type == "final_verdict_ref":
            ref_path = str(payload.get("ref_path") or "")
            if not ref_path or ref_path in seen_paths:
                continue
            seen_paths.add(ref_path)
            refs.append(_evidence_ref(
                f"ev-team-final-verdict-{_safe_token(event.get('event_id') or ref_path)}",
                "final_verdict",
                Path(ref_path),
                "acceptance",
            ))
            continue
        if event_type != "task_result":
            continue
        report_path = str(payload.get("report_path") or "")
        if report_path and report_path not in explicit_paths and report_path not in seen_paths:
            seen_paths.add(report_path)
            refs.append(_evidence_ref(
                f"ev-team-{_safe_token(event.get('event_id') or report_path)}",
                "command_output",
                Path(report_path),
                "outcome",
            ))
    return refs


def _team_evidence_kind(ref_type: str) -> str:
    token = _safe_token(ref_type)
    if token in {"report", "command_output", "command-output", "execution_report", "execution-report"}:
        return "command_output"
    if token in {"test", "test_output", "test-output"}:
        return "test_output"
    if token == "review":
        return "review"
    if token in {"gate", "gate_result", "gate-result"}:
        return "gate_result"
    if token in {"final_verdict", "final-verdict"}:
        return "final_verdict"
    if token in {"context_packet", "context-packet", "packet"}:
        return "context_packet"
    return "other"


def _team_review_refs(
    events: list[dict[str, Any]],
    blocked_reviewer_ids: set[str],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    refs: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    seen: set[str] = set()
    for event in events:
        if event.get("event_type") != "review_ref":
            continue
        payload = _as_dict(event.get("payload"))
        review_id = str(payload.get("review_id") or "")
        reviewer_id = str(payload.get("reviewer_id") or event.get("agent_id") or "")
        reviewer_role = str(payload.get("reviewer_role") or "")
        executor_id = str(payload.get("executor_id") or "")
        verdict = _review_verdict(str(payload.get("verdict") or ""))
        ref_path = str(payload.get("ref_path") or "")
        reviewed_evidence_refs = [
            str(ref) for ref in payload.get("reviewed_evidence_refs", [])
            if str(ref)
        ] if isinstance(payload.get("reviewed_evidence_refs"), list) else []
        diagnostic = _unsafe_team_review(
            review_id=review_id,
            reviewer_id=reviewer_id,
            reviewer_role=reviewer_role,
            executor_id=executor_id,
            verdict=verdict,
            ref_path=ref_path,
            reviewed_evidence_refs=reviewed_evidence_refs,
            blocked_reviewer_ids=blocked_reviewer_ids,
        )
        if diagnostic:
            failures.append(_event_failure_ref("team-review", event, diagnostic, ref_path))
            continue
        if review_id in seen:
            continue
        seen.add(review_id)
        refs.append({
            "review_id": review_id,
            "reviewer_id": reviewer_id,
            "reviewer_role": reviewer_role,
            "verdict": verdict,
            "uri": ref_path,
            "reviewed_evidence_refs": reviewed_evidence_refs,
        })
    return refs, failures


def _unsafe_team_review(
    *,
    review_id: str,
    reviewer_id: str,
    reviewer_role: str,
    executor_id: str,
    verdict: str,
    ref_path: str,
    reviewed_evidence_refs: list[str],
    blocked_reviewer_ids: set[str],
) -> str:
    role_token = _safe_token(reviewer_role)
    if not review_id:
        return "review_id is missing"
    if not reviewer_id:
        return "reviewer_id is missing"
    if not reviewer_role:
        return "reviewer_role is missing"
    if role_token in {"executor", "fixer", "coder", "worker"}:
        return f"reviewer role is not independent: {role_token}"
    if reviewer_id in blocked_reviewer_ids:
        return "reviewer_id matches a worker in the same run"
    if reviewer_id and executor_id and reviewer_id == executor_id:
        return "reviewer_id matches executor_id"
    if verdict not in {"pass", "blocked", "fail", "escalate"}:
        return "review verdict is not allowed"
    if not ref_path:
        return "review ref_path is missing"
    if not reviewed_evidence_refs:
        return "reviewed_evidence_refs is missing"
    return ""


def _gate_refs_from_final_verdict_artifact(
    artifact: dict[str, Any],
    declared_gate_refs: list[str],
    review_ref: str,
    review_evidence_ids: dict[str, str],
) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    seen: set[str] = set()
    declared = {str(ref) for ref in declared_gate_refs if str(ref)}
    gate_summary = artifact.get("gate_summary") if isinstance(artifact.get("gate_summary"), list) else []
    for item in gate_summary:
        if not isinstance(item, dict):
            continue
        gate_id = str(item.get("gate_id") or "")
        result = _gate_result(str(item.get("result") or ""))
        evidence_path = str(item.get("evidence_path") or artifact.get("verdict_id") or "")
        if not gate_id or gate_id not in declared or not result or not evidence_path or gate_id in seen:
            continue
        if result == "pass" and review_ref not in review_evidence_ids:
            continue
        seen.add(gate_id)
        evidence_refs = [review_evidence_ids[review_ref]] if result == "pass" and review_ref in review_evidence_ids else []
        refs.append({
            "gate_id": gate_id,
            "result": result,
            "uri": evidence_path,
            "evidence_refs": evidence_refs,
        })
    return refs


def _team_review_evidence_ids(events: list[dict[str, Any]]) -> dict[str, str]:
    ids: dict[str, str] = {}
    for event in events:
        if event.get("event_type") != "review_ref":
            continue
        payload = _as_dict(event.get("payload"))
        review_id = str(payload.get("review_id") or "")
        if review_id and review_id not in ids:
            ids[review_id] = f"ev-team-review-{_safe_token(event.get('event_id') or payload.get('ref_path') or review_id)}"
    return ids


def _final_ready_context_diagnostic(
    events: list[dict[str, Any]],
    context_refs: list[dict[str, str]],
) -> str:
    success_agents = {
        str(event.get("agent_id") or "")
        for event in events
        if event.get("event_type") == "task_result"
        and _safe_token(_as_dict(event.get("payload")).get("status")) in {
            "pass",
            "passed",
            "completed",
            "success",
            "succeeded",
            "verified",
        }
        and str(event.get("agent_id") or "")
    }
    valid_types_by_agent: dict[str, set[str]] = {}
    diagnostics: list[str] = []
    for ref in context_refs:
        ref_type = _safe_token(ref.get("ref_type"))
        if ref_type not in {"context_packet", "context_ledger"}:
            continue
        agent_id = str(ref.get("agent_id") or "")
        ref_path = Path(str(ref.get("ref_path") or ""))
        diagnostic = (
            _context_packet_diagnostic(ref_path)
            if ref_type == "context_packet"
            else _context_ledger_diagnostic(ref_path)
        )
        if diagnostic:
            diagnostics.append(f"{ref_type} for {agent_id or 'unknown-agent'} is invalid: {diagnostic}")
            continue
        valid_types_by_agent.setdefault(agent_id, set()).add(ref_type)
    agents_to_check = sorted(success_agents)
    if not agents_to_check:
        if diagnostics:
            return diagnostics[0]
        return "successful task_result event is missing"
    for agent_id in agents_to_check:
        missing = sorted({"context_packet", "context_ledger"} - valid_types_by_agent.get(agent_id, set()))
        if missing:
            return f"sealed context refs missing for {agent_id}: {', '.join(missing)}"
    return ""


def _context_packet_diagnostic(path: Path) -> str:
    data, diagnostic = _read_json_file(path)
    if diagnostic:
        return diagnostic
    errors = sorted(
        _schema_validator("schemas/runtime-governance/context-packet.schema.json").iter_errors(data),
        key=lambda error: list(error.path),
    )
    if errors:
        return f"context packet schema invalid: {errors[0].message}"
    if str(data.get("seal_state") or "") != "sealed":
        return "context packet is not sealed"
    return ""


def _context_ledger_diagnostic(path: Path) -> str:
    data, diagnostic = _read_json_file(path)
    if diagnostic:
        return diagnostic
    errors = sorted(
        _schema_validator("schemas/runtime-governance/context-ledger.schema.json").iter_errors(data),
        key=lambda error: list(error.path),
    )
    if errors:
        return f"context ledger schema invalid: {errors[0].message}"
    return ""


def _team_final_verdict_ref(
    events: list[dict[str, Any]],
    review_refs: list[dict[str, Any]],
    blocked_producer_ids: set[str],
    context_refs: list[dict[str, str]],
) -> tuple[dict[str, Any] | None, list[dict[str, Any]], list[str], list[dict[str, Any]]]:
    failures: list[dict[str, Any]] = []
    pass_review_ids = {
        str(ref.get("review_id") or "")
        for ref in review_refs
        if ref.get("verdict") == "pass"
    }
    valid_review_ids = {
        str(ref.get("review_id") or "")
        for ref in review_refs
        if str(ref.get("review_id") or "")
    }
    review_evidence_ids = _team_review_evidence_ids(events)
    for event in events:
        if event.get("event_type") != "final_verdict_ref":
            continue
        payload = _as_dict(event.get("payload"))
        verdict_id = str(payload.get("verdict_id") or "")
        producer_id = str(event.get("agent_id") or "")
        produced_by = str(payload.get("produced_by") or producer_id)
        producer_role = str(payload.get("producer_role") or "")
        final_state = str(payload.get("final_state") or "")
        ref_path = str(payload.get("ref_path") or "")
        review_ref = str(payload.get("review_ref") or "")
        gate_refs_text = [
            str(ref) for ref in payload.get("gate_refs", [])
            if str(ref)
        ] if isinstance(payload.get("gate_refs"), list) else []
        diagnostic = _unsafe_team_final_verdict(
            verdict_id=verdict_id,
            producer_role=producer_role,
            final_state=final_state,
            ref_path=ref_path,
            review_ref=review_ref,
            gate_refs=gate_refs_text,
            producer_id=producer_id,
            produced_by=produced_by,
            blocked_producer_ids=blocked_producer_ids,
            pass_review_ids=pass_review_ids,
            valid_review_ids=valid_review_ids,
        )
        if diagnostic:
            failures.append(_event_failure_ref("team-final-verdict", event, diagnostic, ref_path))
            continue
        artifact, artifact_diagnostic = _validate_final_verdict_artifact(Path(ref_path), payload)
        if artifact_diagnostic:
            failures.append(_event_failure_ref("team-final-verdict", event, artifact_diagnostic, ref_path))
            continue
        context_diagnostic = (
            _final_ready_context_diagnostic(events, context_refs)
            if final_state == "final_ready"
            else ""
        )
        if context_diagnostic:
            failures.append(_event_failure_ref(
                "team-final-verdict",
                event,
                context_diagnostic,
                ref_path,
            ))
            continue
        gate_refs = _gate_refs_from_final_verdict_artifact(
            artifact,
            gate_refs_text,
            review_ref,
            review_evidence_ids,
        )
        pass_gate_ids = {
            str(ref.get("gate_id") or "")
            for ref in gate_refs
            if ref.get("result") == "pass"
        }
        missing_gates = sorted(ref for ref in gate_refs_text if ref not in pass_gate_ids)
        if final_state == "final_ready" and missing_gates:
            failures.append(_event_failure_ref(
                "team-final-verdict",
                event,
                f"final verdict gate_refs are not passing in artifact: {', '.join(missing_gates)}",
                ref_path,
            ))
            continue
        final_ref = {
            "verdict_id": verdict_id,
            "producer_role": producer_role,
            "final_state": final_state,
            "uri": ref_path,
            "review_ref": review_ref,
            "gate_refs": gate_refs_text,
        }
        supersedes = _as_dict(artifact.get("supersedes"))
        if supersedes:
            final_ref["supersedes"] = {
                "verdict_id": str(supersedes.get("verdict_id") or ""),
                "uri": str(supersedes.get("uri") or ""),
                "reason": str(supersedes.get("reason") or ""),
            }
            chain = _final_verdict_supersession_chain(artifact, Path(ref_path))
            if chain:
                final_ref["supersession_chain"] = chain
        return final_ref, [], [str(item) for item in artifact.get("limitations", []) if str(item)] if isinstance(artifact.get("limitations"), list) else [], gate_refs
    return None, failures, [], []


def _unsafe_team_final_verdict(
    *,
    verdict_id: str,
    producer_role: str,
    final_state: str,
    ref_path: str,
    review_ref: str,
    gate_refs: list[str],
    producer_id: str,
    produced_by: str,
    blocked_producer_ids: set[str],
    pass_review_ids: set[str],
    valid_review_ids: set[str],
) -> str:
    role_token = _safe_token(producer_role)
    if not verdict_id:
        return "verdict_id is missing"
    if not verdict_id.startswith("fv-"):
        return "verdict_id must start with fv-"
    if not producer_role:
        return "producer_role is missing"
    if role_token in {"executor", "fixer", "coder", "worker"}:
        return f"producer role is not governance-owned: {role_token}"
    if not produced_by:
        return "produced_by is missing"
    if producer_id in blocked_producer_ids:
        return "final verdict producer matches a worker in the same run"
    if produced_by in blocked_producer_ids:
        return "final verdict produced_by matches a worker in the same run"
    if final_state not in {"final_ready", "accepted_with_limitation", "blocked", "failed", "deferred"}:
        return "final_state is not allowed"
    if not ref_path:
        return "final verdict ref_path is missing"
    if final_state == "final_ready" and review_ref not in pass_review_ids:
        return "final verdict review_ref does not name a passing independent review"
    if final_state != "final_ready" and review_ref not in valid_review_ids:
        return "final verdict review_ref does not name an independent review"
    if not gate_refs:
        return "final verdict gate_refs is missing"
    return ""


def _validate_final_verdict_artifact(path: Path, payload: dict[str, Any]) -> tuple[dict[str, Any], str]:
    data, diagnostic = _read_json_file(path)
    if diagnostic:
        return {}, diagnostic
    if str(data.get("verdict_id") or "") != str(payload.get("verdict_id") or ""):
        return {}, "final verdict artifact verdict_id does not match event"
    if str(data.get("produced_by") or "") != str(payload.get("produced_by") or ""):
        return {}, "final verdict artifact produced_by does not match event"
    if str(data.get("producer_role") or "") != str(payload.get("producer_role") or ""):
        return {}, "final verdict artifact producer_role does not match event"
    if str(data.get("final_state") or "") != str(payload.get("final_state") or ""):
        return {}, "final verdict artifact final_state does not match event"
    errors = sorted(
        _schema_validator("schemas/agent-runtime/final-verdict.schema.json").iter_errors(data),
        key=lambda error: list(error.path),
    )
    if errors:
        return {}, f"final verdict artifact schema invalid: {errors[0].message}"
    return data, ""


def _final_verdict_supersession_chain(
    artifact: dict[str, Any],
    artifact_path: Path,
    *,
    max_depth: int = 5,
) -> list[dict[str, Any]]:
    chain: list[dict[str, Any]] = []
    current = artifact
    current_path = artifact_path
    seen: set[str] = {
        str(artifact_path.resolve()) if artifact_path.exists() else str(artifact_path)
    }
    depth_limited = False
    for depth in range(max_depth):
        supersedes = _as_dict(current.get("supersedes"))
        if not supersedes:
            break
        uri = str(supersedes.get("uri") or "")
        prior_path = _resolve_superseded_verdict_path(current_path, uri)
        prior_key = str(prior_path.resolve()) if prior_path.exists() else str(prior_path)
        if prior_key in seen:
            if chain:
                chain[-1]["resolution_state"] = "cycle"
                chain[-1]["diagnostic"] = "supersession chain cycle detected"
            break
        seen.add(prior_key)
        item = {
            "verdict_id": str(supersedes.get("verdict_id") or ""),
            "uri": uri,
            "reason": str(supersedes.get("reason") or ""),
            "resolved": False,
            "resolution_state": "missing",
            "diagnostic": "missing superseded FinalVerdict artifact",
        }
        chain.append(item)
        prior_artifact, diagnostic = _read_final_verdict_artifact_for_chain(prior_path)
        if diagnostic:
            item["resolution_state"] = "missing" if diagnostic.startswith("missing JSON file:") else "invalid"
            item["diagnostic"] = (
                "missing superseded FinalVerdict artifact"
                if item["resolution_state"] == "missing"
                else "invalid superseded FinalVerdict artifact"
            )
            break
        if str(prior_artifact.get("verdict_id") or "") != item["verdict_id"]:
            item["resolution_state"] = "id_mismatch"
            item["diagnostic"] = "superseded verdict_id does not match artifact"
            break
        item["resolved"] = True
        item["resolution_state"] = "resolved"
        item.pop("diagnostic", None)
        item["final_state"] = str(prior_artifact.get("final_state") or "")
        current = prior_artifact
        current_path = prior_path
        depth_limited = depth == max_depth - 1 and bool(_as_dict(current.get("supersedes")))
    if depth_limited and chain:
        chain[-1]["resolution_state"] = "depth_limited"
        chain[-1]["diagnostic"] = "supersession chain depth limit reached"
    return chain


def _resolve_superseded_verdict_path(current_path: Path, uri: str) -> Path:
    path = Path(uri)
    if path.is_absolute():
        return path
    return current_path.parent / path


def _read_final_verdict_artifact_for_chain(path: Path) -> tuple[dict[str, Any], str]:
    data, diagnostic = _read_json_file(path)
    if diagnostic:
        return {}, diagnostic
    errors = sorted(
        _schema_validator("schemas/agent-runtime/final-verdict.schema.json").iter_errors(data),
        key=lambda error: list(error.path),
    )
    if errors:
        return {}, f"final verdict artifact schema invalid: {errors[0].message}"
    return data, ""


def _schema_validator(schema_path: str):
    schema = json.loads((_repo_root() / schema_path).read_text(encoding="utf-8-sig"))
    validator_class = validator_for(schema)
    validator_class.check_schema(schema)
    return validator_class(schema)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _gate_result(result: str) -> str:
    token = _safe_token(result)
    if token in {"pass", "fail", "blocked", "warning", "skipped"}:
        return token
    return ""


def _has_pass_review(review_refs: list[dict[str, Any]]) -> bool:
    return any(ref.get("verdict") == "pass" for ref in review_refs)


def _has_pass_gate(gate_refs: list[dict[str, Any]]) -> bool:
    return any(ref.get("result") == "pass" for ref in gate_refs)


def _event_failure_ref(prefix: str, event: dict[str, Any], diagnostic: str, uri: str = "") -> dict[str, Any]:
    token = _safe_token(event.get("event_id") or event.get("run_id") or prefix)
    return {
        "failure_id": f"failure-{prefix}-{token}",
        "status": "blocked",
        "uri": uri or str(event.get("event_id") or prefix),
    }


def _evidence_ref(evidence_id: str, kind: str, path: Path, supports: str) -> dict[str, Any]:
    return {
        "evidence_id": evidence_id,
        "kind": kind,
        "uri": str(path),
        "supports": supports,
    }


def _review_refs(legacy_id: str, review_path: Path, verdict: str, review: dict[str, Any]) -> list[dict[str, Any]]:
    mapped = _review_verdict(verdict)
    if not mapped:
        return []
    return [{
        "review_id": f"review-{_safe_token(legacy_id)}",
        "reviewer_id": str(review.get("reviewer_id") or "atgo-reviewer"),
        "reviewer_role": str(review.get("reviewer_role") or "reviewer"),
        "verdict": mapped,
        "uri": str(review_path),
        "reviewed_evidence_refs": [f"ev-atgo-review-{_safe_token(legacy_id)}"],
    }]


def _review_verdict(verdict: str) -> str:
    token = _safe_token(verdict)
    if token in {"pass", "passed", "approved", "accepted", "proceed"}:
        return "pass"
    if token in {"blocked", "stop", "rejected", "denied"}:
        return "blocked"
    if token in {"fail", "failed"}:
        return "fail"
    if token == "escalate":
        return "escalate"
    return ""


def _worker_results(report: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not report:
        return []
    return [_worker_result(
        "rdgoal-worker",
        "worker",
        str(report.get("status") or "unknown"),
        str(report.get("ingested_at") or _mtime_iso(Path(str(report.get("report_path") or "")))),
    )]


def _go_worker_results(agents: list[Any], reported_at: str) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for agent in agents:
        if not isinstance(agent, dict):
            continue
        results.append(_worker_result(
            str(agent.get("agent_id") or "go-agent"),
            "worker",
            str(agent.get("worker_status") or agent.get("status") or "unknown"),
            reported_at,
            artifact_refs=[f"artifact-{_safe_token(agent.get('report_path'))}"] if agent.get("report_path") else [],
        ))
    return results


def _team_worker_results(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for event in events:
        payload = _as_dict(event.get("payload"))
        results.append(_worker_result(
            str(event.get("agent_id") or "team-agent"),
            "worker",
            str(payload.get("status") or "unknown"),
            str(event.get("timestamp") or ""),
        ))
    return results


def _team_worker_agent_ids(events: list[dict[str, Any]]) -> set[str]:
    return {
        str(event.get("agent_id") or "")
        for event in events
        if str(event.get("agent_id") or "")
    }


def _worker_result(
    worker_id: str,
    worker_role: str,
    status: str,
    reported_at: str,
    *,
    artifact_refs: list[str] | None = None,
) -> dict[str, Any]:
    result = {
        "worker_id": worker_id or "unknown-worker",
        "worker_role": worker_role,
        "status": _worker_status(status),
        "reported_at": _date_time(reported_at),
    }
    if artifact_refs:
        result["artifact_refs"] = artifact_refs
    return result


def _worker_status(status: str) -> str:
    token = _safe_token(status)
    if token in {"pass", "passed"}:
        return "passed"
    if token in {"completed", "success", "succeeded", "done"}:
        return "completed"
    if token == "verified":
        return "verified"
    if token in {"blocked", "failed", "error", "cancelled"}:
        return token
    return "unknown"


def _aggregate_team_status(result_events: list[dict[str, Any]]) -> str:
    if not result_events:
        return "running"
    statuses = [
        str(_as_dict(event.get("payload")).get("status") or "unknown")
        for event in result_events
    ]
    tokens = {_safe_token(status) for status in statuses}
    if tokens & {"failed", "fail", "error"}:
        return "failed"
    if "blocked" in tokens:
        return "blocked"
    if tokens <= {"pass", "passed", "completed", "success", "succeeded", "verified"}:
        return "passed"
    return "unknown"


def _team_project_id(events: list[dict[str, Any]]) -> str:
    for event in events:
        project_id = _as_dict(event.get("payload")).get("project_id")
        if project_id:
            return str(project_id)
    return "unknown-project"


def _as_dict(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_token(value: object) -> str:
    text = str(value or "").strip()
    chars = [
        ch if ch.isascii() and (ch.isalnum() or ch in {".", "_", "-"}) else "-"
        for ch in text
    ]
    token = "".join(chars).strip("-._").lower()
    while "--" in token:
        token = token.replace("--", "-")
    return token or "unknown"


def _source_hash(path: Path) -> str:
    try:
        if path.is_file():
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            return f"sha256:{digest}"
    except OSError:
        return ""
    return ""


def _mtime_iso(path: Path) -> str:
    try:
        timestamp = path.stat().st_mtime
    except OSError:
        timestamp = datetime.now(timezone.utc).timestamp()
    return datetime.fromtimestamp(timestamp, timezone.utc).isoformat()


def _date_time(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return datetime.now(timezone.utc).isoformat()
    if text.endswith("Z"):
        return text
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return datetime.now(timezone.utc).isoformat()
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.isoformat()
