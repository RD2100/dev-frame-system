"""Read-only canonical RunRecord projections for legacy runtime files."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

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
                artifact_refs=_artifact_refs(path),
                evidence_refs=_team_evidence_refs(result_events),
                worker_results=_team_worker_results(result_events),
                domain_refs={
                    "legacy_adapter": "team_events",
                    "source_run_id": run_id,
                    "event_count": len(events),
                    "event_types": sorted({str(event.get("event_type") or "") for event in events}),
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
        review, diagnostic = _read_yaml_file(review_path)
        legacy_id = run_dir.name
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
    worker_results: list[dict[str, Any]] | None = None,
    failure_refs: list[dict[str, Any]] | None = None,
    domain_refs: dict[str, Any] | None = None,
) -> dict[str, Any]:
    run_token = _safe_token(legacy_id)
    axes = _axes(status, adapter_id=adapter_id, review_refs=review_refs or [], failure_refs=failure_refs or [])
    refs = {
        "adapter_version": ADAPTER_VERSION,
        "source_path": str(source_path),
        "legacy_status": status,
    }
    refs.update(domain_refs or {})
    refs = {key: value for key, value in refs.items() if value is not None}
    return {
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


def _axes(
    status: str,
    *,
    adapter_id: str,
    review_refs: list[dict[str, Any]],
    failure_refs: list[dict[str, Any]],
) -> dict[str, str]:
    normalized = _safe_token(status).replace("_", "-")
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
    if failure_refs:
        return _axis("closed", "blocked", "not_reviewed", "gate_blocked", "blocked", "blocked")
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


def _team_evidence_refs(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    for event in events:
        payload = _as_dict(event.get("payload"))
        report_path = str(payload.get("report_path") or "")
        if report_path:
            refs.append(_evidence_ref(
                f"ev-team-{_safe_token(event.get('event_id') or report_path)}",
                "command_output",
                Path(report_path),
                "outcome",
            ))
    return refs


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
