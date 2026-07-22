"""Read-only canonical RunRecord projections for legacy runtime files."""
from __future__ import annotations

import hashlib
import json
import os
import sys
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, BinaryIO

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
        "canonical_runs": _canonical_run_entries(entries, runtime),
    }


def _canonical_run_entries(
    entries: list[dict[str, Any]],
    runtime: Path,
) -> list[dict[str, Any]]:
    team_snapshots = _canonical_team_event_snapshots(entries, runtime)
    paired_indexes: set[int] = set()
    candidates: dict[str, dict[str, list[tuple[int, dict[str, Any]]]]] = {}
    for index, entry in enumerate(entries):
        adapter_id = str(entry.get("adapter_id") or "")
        if adapter_id not in {"go_run", "team_events"}:
            continue
        run_id = str(_as_dict(entry.get("record")).get("run_id") or "")
        if not run_id:
            continue
        candidates.setdefault(run_id, {}).setdefault(adapter_id, []).append((index, entry))

    canonical: list[dict[str, Any]] = []
    for run_id in sorted(candidates):
        by_adapter = candidates[run_id]
        if not by_adapter.get("go_run") or not by_adapter.get("team_events"):
            continue
        paired = by_adapter["go_run"] + by_adapter["team_events"]
        paired_indexes.update(index for index, _entry_item in paired)
        canonical.append(_canonical_go_team_entry(
            run_id,
            [entry for _index, entry in paired],
            team_snapshots,
        ))

    for index, entry in enumerate(entries):
        if index in paired_indexes:
            continue
        passthrough = deepcopy(entry)
        passthrough["provenance"] = {
            **deepcopy(_as_dict(entry.get("provenance"))),
            "sources": [_canonical_source(entry)],
        }
        canonical.append(passthrough)

    canonical.sort(key=lambda item: (
        str(_as_dict(item.get("record")).get("run_id") or ""),
        str(item.get("adapter_id") or ""),
        json.dumps(_as_dict(item.get("provenance")), sort_keys=True, ensure_ascii=True),
    ))
    return canonical


def _canonical_go_team_entry(
    run_id: str,
    entries: list[dict[str, Any]],
    team_snapshots: dict[tuple[str, str], tuple[list[dict[str, Any]], str]],
) -> dict[str, Any]:
    sources = sorted((_canonical_source(entry) for entry in entries), key=_stable_json)
    records = [deepcopy(_as_dict(entry.get("record"))) for entry in entries]
    go_records = [
        record for entry, record in zip(entries, records)
        if entry.get("adapter_id") == "go_run"
    ]
    base = deepcopy(sorted(go_records, key=_stable_json)[0])
    diagnostics: list[str] = []

    project_ids = sorted({
        project_id
        for record in records
        if (project_id := str(record.get("project_id") or "").strip())
        and project_id != "unknown-project"
    })
    if len(project_ids) == 1:
        project_id = project_ids[0]
    else:
        project_id = "unknown-project"
        if len(project_ids) > 1:
            diagnostics.append(f"project identity conflict: {', '.join(project_ids)}")
        else:
            diagnostics.append("project identity is missing from all canonical sources")

    base["project_id"] = project_id
    base["goal_id"] = f"goal-{_safe_token(project_id)}"
    base["created_at"] = _earliest_date_time(record.get("created_at") for record in records)
    base["updated_at"] = _latest_date_time(record.get("updated_at") for record in records)

    worker_results, worker_diagnostics = _canonical_worker_results(records)
    base["worker_results"] = worker_results
    diagnostics.extend(worker_diagnostics)
    diagnostics.extend(
        str(_as_dict(record.get("domain_refs")).get("diagnostic") or "")
        for entry, record in zip(entries, records)
        if entry.get("adapter_id") == "team_events"
        and str(_as_dict(record.get("domain_refs")).get("diagnostic") or "")
    )

    for field, key in (
        ("artifact_refs", "artifact_id"),
        ("evidence_refs", "evidence_id"),
        ("review_refs", "review_id"),
        ("gate_refs", "gate_id"),
        ("failure_refs", "failure_id"),
    ):
        merged, conflicts = _merge_record_refs(records, field, key)
        base[field] = merged
        diagnostics.extend(conflicts)
    worker_ids = {
        str(result.get("worker_id") or "")
        for result in base["worker_results"]
        if str(result.get("worker_id") or "")
    }
    for review_ref in base["review_refs"]:
        reviewer_id = str(review_ref.get("reviewer_id") or "")
        if review_ref.get("verdict") == "pass" and reviewer_id in worker_ids:
            diagnostics.append(f"passing reviewer {reviewer_id} matches a worker in the canonical run")

    final_refs = {
        _stable_json(record["final_verdict_ref"]): deepcopy(record["final_verdict_ref"])
        for record in records
        if isinstance(record.get("final_verdict_ref"), dict)
    }
    if len(final_refs) == 1:
        base["final_verdict_ref"] = next(iter(final_refs.values()))
        verdict_path = Path(str(base["final_verdict_ref"].get("uri") or ""))
        verdict_artifact, verdict_diagnostic = _read_json_file(verdict_path)
        if verdict_diagnostic:
            diagnostics.append(
                f"final verdict producer identity cannot be verified: {verdict_diagnostic}"
            )
        else:
            produced_by = str(verdict_artifact.get("produced_by") or "").strip()
            if produced_by in worker_ids:
                diagnostics.append(
                    f"final verdict producer {produced_by} matches a worker in the canonical run"
                )
        event_producer_id, event_diagnostic = _canonical_final_verdict_event_producer(
            entries,
            base["final_verdict_ref"],
            team_snapshots,
        )
        if event_diagnostic:
            diagnostics.append(
                f"final verdict event producer identity cannot be verified: {event_diagnostic}"
            )
        elif event_producer_id in worker_ids:
            diagnostics.append(
                f"final verdict event producer {event_producer_id} matches a worker in the canonical run"
            )
    else:
        base.pop("final_verdict_ref", None)
        if len(final_refs) > 1:
            diagnostics.append("final verdict reference conflict")

    limitations = sorted({
        str(item)
        for record in records
        for item in record.get("limitations", [])
        if isinstance(record.get("limitations"), list) and str(item)
    })
    if limitations:
        base["limitations"] = limitations
    else:
        base.pop("limitations", None)

    source_domain_refs: dict[str, list[dict[str, Any]]] = {}
    for entry, record in zip(entries, records):
        adapter_id = str(entry.get("adapter_id") or "unknown")
        source_domain_refs.setdefault(adapter_id, []).append(deepcopy(_as_dict(record.get("domain_refs"))))
    for adapter_id in source_domain_refs:
        source_domain_refs[adapter_id].sort(key=_stable_json)
    domain_refs: dict[str, Any] = {
        "adapter_version": ADAPTER_VERSION,
        "legacy_adapter": "canonical_run",
        "source_adapters": sorted(source_domain_refs),
        "source_domain_refs": source_domain_refs,
    }

    status, status_diagnostic = _canonical_status(records)
    if status_diagnostic:
        diagnostics.append(status_diagnostic)
    axes = _axes(
        status,
        adapter_id="team_events",
        review_refs=base["review_refs"],
        gate_refs=base["gate_refs"],
        final_verdict_ref=base.get("final_verdict_ref"),
        failure_refs=base["failure_refs"],
    )
    if diagnostics:
        diagnostic = "; ".join(sorted(set(diagnostics)))
        failure_ref = {
            "failure_id": f"failure-canonical-reconcile-{_safe_token(run_id)}",
            "status": "blocked",
            "uri": str(sources[0].get("source_path") or run_id),
        }
        base["failure_refs"] = _merge_unique_refs(base["failure_refs"] + [failure_ref], "failure_id")
        domain_refs["diagnostic"] = diagnostic
        axes = _axis("closed", "blocked", "not_reviewed", "gate_blocked", "blocked", "blocked")
    base.update(axes)
    base["domain_refs"] = domain_refs

    return {
        "adapter_id": "canonical_run",
        "source_type": "canonical_run_projection",
        "adapter_version": ADAPTER_VERSION,
        "provenance": {
            "canonical_run_id": run_id,
            "sources": sources,
        },
        "record": base,
    }


def _canonical_team_event_snapshots(
    entries: list[dict[str, Any]],
    runtime: Path,
) -> dict[tuple[str, str], tuple[list[dict[str, Any]], str]]:
    snapshots: dict[tuple[str, str], tuple[list[dict[str, Any]], str]] = {}
    sources = {
        (
            str(_as_dict(entry.get("provenance")).get("source_path") or ""),
            str(_as_dict(entry.get("provenance")).get("source_hash") or ""),
        )
        for entry in entries
        if entry.get("adapter_id") == "team_events"
    }
    for source_path, expected_hash in sorted(sources):
        if not source_path or not expected_hash:
            snapshots[(source_path, expected_hash)] = ([], "team event source provenance is incomplete")
            continue
        items, actual_hash = _read_runtime_jsonl_snapshot(Path(source_path), runtime)
        if not actual_hash:
            snapshots[(source_path, expected_hash)] = ([], f"team event source cannot be read: {source_path}")
            continue
        if actual_hash != expected_hash:
            snapshots[(source_path, expected_hash)] = (
                [],
                f"team event source changed before producer verification: {source_path}",
            )
            continue
        diagnostic = next((str(item["diagnostic"]) for item in items if item.get("diagnostic")), "")
        snapshots[(source_path, expected_hash)] = (items, diagnostic)
    return snapshots


def _canonical_source(entry: dict[str, Any]) -> dict[str, Any]:
    provenance = _as_dict(entry.get("provenance"))
    return {
        "adapter_id": str(entry.get("adapter_id") or ""),
        "source_type": str(entry.get("source_type") or ""),
        "adapter_version": str(entry.get("adapter_version") or ""),
        "source_path": str(provenance.get("source_path") or ""),
        "legacy_id": str(provenance.get("legacy_id") or ""),
        "source_hash": str(provenance.get("source_hash") or ""),
    }


def _canonical_final_verdict_event_producer(
    entries: list[dict[str, Any]],
    final_ref: dict[str, Any],
    team_snapshots: dict[tuple[str, str], tuple[list[dict[str, Any]], str]],
) -> tuple[str, str]:
    sources = {
        (
            str(_as_dict(entry.get("provenance")).get("source_path") or ""),
            str(_as_dict(entry.get("provenance")).get("legacy_id") or ""),
            str(_as_dict(entry.get("provenance")).get("source_hash") or ""),
        )
        for entry in entries
        if entry.get("adapter_id") == "team_events"
    }
    if not sources:
        return "", "team event source is missing"

    verdict_id = str(final_ref.get("verdict_id") or "")
    verdict_uri = str(final_ref.get("uri") or "")
    matches: list[dict[str, Any]] = []
    for source_path, run_id, expected_hash in sorted(sources):
        if not source_path or not run_id or not expected_hash:
            return "", "team event source provenance is incomplete"
        items, snapshot_diagnostic = team_snapshots.get(
            (source_path, expected_hash),
            ([], "team event source snapshot is missing"),
        )
        if snapshot_diagnostic:
            return "", snapshot_diagnostic
        for item in items:
            if item.get("diagnostic"):
                return "", str(item["diagnostic"])
            event = _as_dict(item.get("record"))
            payload = _as_dict(event.get("payload"))
            if (
                event.get("event_type") == "final_verdict_ref"
                and str(event.get("run_id") or "") == run_id
                and str(payload.get("verdict_id") or "") == verdict_id
                and str(payload.get("ref_path") or "") == verdict_uri
            ):
                matches.append(event)

    if not matches:
        return "", "matching final_verdict_ref event is missing"
    if len(matches) > 1:
        return "", "matching final_verdict_ref event is ambiguous"
    _artifact, artifact_diagnostic = _validate_final_verdict_artifact(
        Path(verdict_uri),
        _as_dict(matches[0].get("payload")),
    )
    if artifact_diagnostic:
        return "", artifact_diagnostic
    producer_id = str(matches[0].get("agent_id") or "").strip()
    if not producer_id:
        return "", "matching final_verdict_ref event producer_id is missing"
    return producer_id, ""


def _canonical_worker_results(records: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[str]]:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for record in records:
        for item in record.get("worker_results", []):
            if not isinstance(item, dict):
                continue
            key = (str(item.get("worker_id") or ""), str(item.get("worker_role") or ""))
            grouped.setdefault(key, []).append(item)

    results: list[dict[str, Any]] = []
    diagnostics: list[str] = []
    status_priority = {
        "verified": 0,
        "passed": 1,
        "succeeded": 2,
        "completed": 3,
        "unknown": 4,
        "cancelled": 5,
        "blocked": 6,
        "error": 7,
        "failed": 8,
    }
    for key in sorted(grouped):
        items = grouped[key]
        statuses = {str(item.get("status") or "unknown") for item in items}
        if len({_canonical_status_category(status) for status in statuses}) > 1:
            diagnostics.append(f"worker result conflict for {key[0] or 'unknown-worker'}")
        selected_status = sorted(statuses, key=lambda value: (status_priority.get(value, 99), value))[0]
        result = {
            "worker_id": key[0] or "unknown-worker",
            "worker_role": key[1] or "worker",
            "status": selected_status,
            "reported_at": _latest_date_time(item.get("reported_at") for item in items),
        }
        artifact_refs = sorted({
            str(ref)
            for item in items
            for ref in item.get("artifact_refs", [])
            if isinstance(item.get("artifact_refs"), list) and str(ref)
        })
        if artifact_refs:
            result["artifact_refs"] = artifact_refs
        results.append(result)
    return results, diagnostics


def _merge_record_refs(
    records: list[dict[str, Any]],
    field: str,
    key: str,
) -> tuple[list[dict[str, Any]], list[str]]:
    grouped: dict[str, dict[str, dict[str, Any]]] = {}
    for record in records:
        for item in record.get(field, []):
            if not isinstance(item, dict):
                continue
            item_key = str(item.get(key) or "")
            grouped.setdefault(item_key, {})[_stable_json(item)] = deepcopy(item)
    merged: list[dict[str, Any]] = []
    diagnostics: list[str] = []
    for item_key in sorted(grouped):
        variants = grouped[item_key]
        if len(variants) > 1:
            diagnostics.append(f"{field} conflict for {item_key or 'missing-id'}")
        merged.append(variants[sorted(variants)[0]])
    return merged, diagnostics


def _merge_unique_refs(items: list[dict[str, Any]], key: str) -> list[dict[str, Any]]:
    by_key = {str(item.get(key) or ""): deepcopy(item) for item in items}
    return [by_key[item_key] for item_key in sorted(by_key)]


def _canonical_status(records: list[dict[str, Any]]) -> tuple[str, str]:
    statuses = {
        _safe_token(_as_dict(record.get("domain_refs")).get("legacy_status")).replace("_", "-")
        for record in records
    }
    categories = {_canonical_status_category(status) for status in statuses}
    diagnostic = (
        f"run status conflict: {', '.join(sorted(statuses))}"
        if len(categories) > 1
        else ""
    )
    representatives = {
        "success": "passed",
        "failure": "failed",
        "blocked": "blocked",
        "human_required": "human-required",
        "cancelled": "cancelled",
        "running": "running",
        "queued": "queued",
        "unknown": "unknown",
    }
    category = next(iter(categories), "unknown")
    return representatives[category], diagnostic


def _canonical_status_category(status: object) -> str:
    token = _safe_token(status).replace("_", "-")
    if token in {"pass", "passed", "completed", "success", "succeeded", "verified", "accepted"}:
        return "success"
    if token in {"failed", "fail", "failure", "error"}:
        return "failure"
    if token in {"blocked", "hard-stop", "insufficient-evidence"}:
        return "blocked"
    if token in {"human-required", "needs-human"}:
        return "human_required"
    if token == "cancelled":
        return "cancelled"
    if token in {"running", "reviewing"}:
        return "running"
    if token in {"queued", "prepared", "ready", "deferred", "draft"}:
        return "queued"
    return "unknown"


def _earliest_date_time(values: Any) -> str:
    return _ordered_date_time(values, reverse=False)


def _latest_date_time(values: Any) -> str:
    return _ordered_date_time(values, reverse=True)


def _ordered_date_time(values: Any, *, reverse: bool) -> str:
    candidates = [str(value) for value in values if str(value or "")]
    if not candidates:
        return _date_time("")

    def key(value: str) -> tuple[datetime, str]:
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            parsed = datetime.min.replace(tzinfo=timezone.utc)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed, value

    return _date_time(sorted(candidates, key=key, reverse=reverse)[0])


def _stable_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


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
        data, diagnostic, source_hash = _read_runtime_json_file(path, runtime)
        legacy_id = str(data.get("go_run_id") or path.parent.name) if data else path.parent.name
        if diagnostic:
            entries.append(_failure_entry(
                "go_run",
                legacy_id,
                path,
                diagnostic,
                source_hash=source_hash,
            ))
            continue
        agents = data.get("agents") if isinstance(data.get("agents"), list) else []
        evidence_refs = _agent_evidence_refs(agents)
        workflow_profile = _as_dict(data.get("workflow_profile"))
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
                    "workflow_profile_id": workflow_profile.get("profile_id", ""),
                    "workflow_profile_fingerprint": workflow_profile.get(
                        "profile_fingerprint", ""
                    ),
                    "workflow_profile_state": workflow_profile.get(
                        "execution_state", ""
                    ),
                },
            ),
            source_hash=source_hash,
        ))
    return entries


def _team_event_entries(runtime: Path) -> list[dict[str, Any]]:
    path = runtime / TEAM_EVENTS_FILE
    events_by_run: dict[str, list[dict[str, Any]]] = {}
    entries: list[dict[str, Any]] = []
    items, source_hash = _read_runtime_jsonl_snapshot(path, runtime)
    for item in items:
        if item.get("diagnostic"):
            entries.append(_failure_entry(
                "team_events",
                item["legacy_id"],
                path,
                item["diagnostic"],
                source_hash=source_hash,
            ))
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
        final_verdict_ref, final_failures, limitations, gate_refs, final_diagnostics = _team_final_verdict_ref(
            events,
            review_refs,
            worker_agent_ids,
            context_refs,
        )
        worker_start_failures, worker_start_diagnostics = _team_worker_start_failures(events)
        failure_refs = review_failures + final_failures + worker_start_failures
        status = "failed" if worker_start_failures else _aggregate_team_status(result_events)
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
                    "worker_start_failure_count": len(worker_start_failures),
                    "diagnostic": (
                        "; ".join(sorted(set(final_diagnostics + worker_start_diagnostics)))
                        if final_diagnostics or worker_start_diagnostics
                        else None
                    ),
                },
            ),
            source_hash=source_hash,
        ))
    return entries


def _team_worker_start_failures(
    events: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[str]]:
    failures: list[dict[str, Any]] = []
    diagnostics: list[str] = []
    for event in events:
        if event.get("event_type") != "workflow_event":
            continue
        payload = _as_dict(event.get("payload"))
        phase = _safe_token(payload.get("phase")).replace("_", "-")
        status = _safe_token(payload.get("status")).replace("_", "-")
        if phase != "worker-start" or status != "failed":
            continue
        diagnostic = str(payload.get("summary") or "").strip()
        if not diagnostic:
            diagnostic = "Worker start batch failed without an actionable diagnostic."
        failures.append(_event_failure_ref("team-worker-start", event, diagnostic))
        diagnostics.append(diagnostic)
    return failures, diagnostics


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
    evidence_refs = _paper_evidence_refs(project_dir, paper_id)
    (
        final_verdict_ref,
        final_verdict_failures,
        final_verdict_limitations,
        review_refs,
        final_verdict_gate_refs,
    ) = _paper_final_verdict_projection(project_dir, paper_id, evidence_refs)
    effective_status = _paper_effective_status(status, state, final_verdict_failures)
    gate_refs = _paper_gate_refs(project_dir, paper_id, state, evidence_refs) + final_verdict_gate_refs
    failure_refs = _paper_failure_refs(project_dir, paper_id, state, effective_status)
    failure_refs.extend(final_verdict_failures)
    limitations = _paper_limitations(project_dir, state, bool(final_verdict_ref)) + final_verdict_limitations
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
            status=effective_status,
            source_path=profile_path,
            adapter_id="paper",
            created_at=_mtime_iso(profile_path),
            updated_at=_mtime_iso(state_path if state_path.exists() else profile_path),
            task_id=paper_id,
            artifact_refs=_artifact_refs(
                profile_path,
                state_path,
                project_dir / "PAPER_LEDGER.md",
                project_dir / "review" / "REVIEW_REPORT.md",
                project_dir / "closure" / "CLOSURE_REPORT.md",
                project_dir / "closure" / "FLOW_OUTCOME.json",
                _paper_final_verdict_path(project_dir) or "",
                project_dir / "evidence" / "ref-paper-review-pack.zip",
            ),
            evidence_refs=evidence_refs,
            review_refs=review_refs,
            gate_refs=gate_refs,
            final_verdict_ref=final_verdict_ref,
            failure_refs=failure_refs,
            limitations=limitations,
            domain_refs={
                "legacy_adapter": "paper",
                "paper_id": paper_id,
                "workflow_type": state.get("workflow_type", ""),
                "current_stage": state.get("current_stage") or profile.get("current_stage", ""),
                "acceptance_status": state.get("acceptance_status", ""),
                "effective_status": effective_status,
                "manifest_status": state.get("manifest_status", ""),
                "evidence_pack_ref": state.get("evidence_pack_ref", ""),
                "final_acceptance": state.get("final_acceptance"),
                "blocking_count": state.get("blocking_count"),
                "non_blocking_count": state.get("non_blocking_count"),
                "human_required": state.get("human_required"),
                "human_gate_decision": state.get("human_gate_decision", ""),
                "human_gate_triggered": state.get("human_gate_triggered"),
                "privacy_attestation": state.get("privacy_attestation"),
                "ledger_issue_count": state.get("ledger_issue_count"),
                "executed_nodes": state.get("executed_nodes", []),
                "chain_trusted": state.get("chain_trusted"),
                "canonical_final_verdict_required": True,
            },
        ),
    )]
    return entries


def _paper_effective_status(
    status: str,
    state: dict[str, Any],
    final_verdict_failures: list[dict[str, Any]],
) -> str:
    if final_verdict_failures:
        return "blocked"
    if _paper_human_gate_open(state):
        return "human_required"
    return status


def _paper_evidence_refs(project_dir: Path, paper_id: str) -> list[dict[str, Any]]:
    token = _safe_token(paper_id)
    refs: list[dict[str, Any]] = []
    candidates = [
        ("canonical-task", "context_packet", project_dir / "TASKSPEC.json", "outcome"),
        ("task", "context_packet", project_dir / "paper_task" / "PAPER_TASK_INPUT.yaml", "outcome"),
        ("privacy", "gate_result", project_dir / "paper_task" / "PRIVACY_ATTESTATION.yaml", "gate"),
        ("paper-pipeline-gate", "gate_result", project_dir / "evidence" / "PAPER_PIPELINE_GATE.json", "gate"),
        ("review", "review", project_dir / "review" / "REVIEW_REPORT.md", "review"),
        ("execution-report", "command_output", project_dir / "execution-report.json", "outcome"),
        ("independent-review", "review", project_dir / "governance" / "INDEPENDENT_REVIEW.json", "review"),
        ("review-gate", "gate_result", project_dir / "governance" / "REVIEW_GATE.json", "gate"),
        ("closure", "command_output", project_dir / "closure" / "CLOSURE_REPORT.md", "outcome"),
        ("flow-outcome", "other", project_dir / "closure" / "FLOW_OUTCOME.json", "outcome"),
        ("evidence-pack", "other", project_dir / "evidence" / "ref-paper-review-pack.zip", "limitation"),
    ]
    final_verdict_path = _paper_final_verdict_path(project_dir)
    if final_verdict_path:
        candidates.append(("final-verdict", "final_verdict", final_verdict_path, "acceptance"))
    for suffix, kind, path, supports in candidates:
        if path.exists():
            refs.append(_evidence_ref(f"ev-paper-{suffix}-{token}", kind, path, supports))
    return refs


def _paper_final_verdict_projection(
    project_dir: Path,
    paper_id: str,
    evidence_refs: list[dict[str, Any]],
) -> tuple[
    dict[str, Any] | None,
    list[dict[str, Any]],
    list[str],
    list[dict[str, Any]],
    list[dict[str, Any]],
]:
    verdict_path = _paper_final_verdict_path(project_dir)
    if not verdict_path:
        return None, [], [], [], []
    token = _safe_token(paper_id)
    artifact, diagnostic = _read_final_verdict_artifact_for_chain(verdict_path)
    if diagnostic:
        return None, [_paper_final_verdict_failure(token, verdict_path, diagnostic)], [], [], []

    final_state = str(artifact.get("final_state") or "")
    review_refs, review_failure = _paper_final_verdict_review_refs(
        artifact,
        final_state,
        token,
        verdict_path,
        evidence_refs,
        project_dir,
    )
    if review_failure:
        return None, [review_failure], [], [], []
    gate_refs, gate_failure = _paper_final_verdict_gate_refs(
        artifact,
        token,
        verdict_path,
        evidence_refs,
        project_dir,
    )
    if gate_failure:
        return None, [gate_failure], [], [], []
    if final_state == "final_ready" and not any(ref.get("result") == "pass" for ref in gate_refs):
        return None, [_paper_final_verdict_failure(
            token,
            verdict_path,
            "paper FinalVerdict final_ready requires at least one passing gate",
        )], [], [], []

    final_ref = _paper_final_verdict_ref(artifact, final_state, verdict_path, review_refs, gate_refs)
    limitations = [str(item) for item in artifact.get("limitations", []) if str(item)] if isinstance(artifact.get("limitations"), list) else []
    return final_ref, [], limitations, review_refs, gate_refs


def _paper_final_verdict_review_refs(
    artifact: dict[str, Any],
    final_state: str,
    token: str,
    verdict_path: Path,
    evidence_refs: list[dict[str, Any]],
    project_dir: Path,
) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    reviewer = _as_dict(artifact.get("reviewer_summary"))
    reviewer_verdict = _review_verdict(str(reviewer.get("verdict") or ""))
    review_path = str(reviewer.get("evidence_path") or "")
    if final_state == "final_ready" and reviewer_verdict != "pass":
        return [], _paper_final_verdict_failure(
            token,
            verdict_path,
            "paper FinalVerdict final_ready requires a passing independent review",
        )
    if not reviewer_verdict or not review_path:
        return [], _paper_final_verdict_failure(
            token,
            verdict_path,
            "paper FinalVerdict reviewer_summary is incomplete",
        )

    review_id = f"review-paper-final-{token}"
    reviewed_evidence_refs = _paper_gate_evidence_refs(review_path, evidence_refs, project_dir)
    if not reviewed_evidence_refs:
        return [], _paper_final_verdict_failure(
            token,
            verdict_path,
            "paper FinalVerdict reviewer_summary evidence_path lacks known evidence",
        )
    return [{
        "review_id": review_id,
        "reviewer_id": str(reviewer.get("reviewer_id") or ""),
        "reviewer_role": "reviewer",
        "verdict": reviewer_verdict,
        "uri": review_path,
        "reviewed_evidence_refs": reviewed_evidence_refs,
    }], None


def _paper_final_verdict_gate_refs(
    artifact: dict[str, Any],
    token: str,
    verdict_path: Path,
    evidence_refs: list[dict[str, Any]],
    project_dir: Path,
) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    gate_refs: list[dict[str, Any]] = []
    for item in artifact.get("gate_summary", []):
        if not isinstance(item, dict):
            continue
        gate_id = str(item.get("gate_id") or "")
        result = _gate_result(str(item.get("result") or ""))
        evidence_path = str(item.get("evidence_path") or verdict_path)
        if not gate_id or not result:
            continue
        evidence_ref_ids = _paper_gate_evidence_refs(evidence_path, evidence_refs, project_dir)
        if result == "pass" and not evidence_ref_ids:
            return [], _paper_final_verdict_failure(
                token,
                verdict_path,
                f"paper FinalVerdict passing gate lacks known evidence: {gate_id}",
            )
        gate_refs.append({
            "gate_id": gate_id,
            "result": result,
            "uri": evidence_path,
            "evidence_refs": evidence_ref_ids,
        })
    if not gate_refs:
        return [], _paper_final_verdict_failure(
            token,
            verdict_path,
            "paper FinalVerdict gate_summary is incomplete",
        )
    return gate_refs, None


def _paper_final_verdict_ref(
    artifact: dict[str, Any],
    final_state: str,
    verdict_path: Path,
    review_refs: list[dict[str, Any]],
    gate_refs: list[dict[str, Any]],
) -> dict[str, Any]:
    final_ref = {
        "verdict_id": str(artifact.get("verdict_id") or ""),
        "producer_role": str(artifact.get("producer_role") or ""),
        "final_state": final_state,
        "uri": str(verdict_path),
        "review_ref": str(review_refs[0].get("review_id") or ""),
        "gate_refs": [str(ref.get("gate_id") or "") for ref in gate_refs],
    }
    supersedes = _as_dict(artifact.get("supersedes"))
    if supersedes:
        final_ref["supersedes"] = {
            "verdict_id": str(supersedes.get("verdict_id") or ""),
            "uri": str(supersedes.get("uri") or ""),
            "reason": str(supersedes.get("reason") or ""),
        }
        chain = _final_verdict_supersession_chain(artifact, verdict_path)
        if chain:
            final_ref["supersession_chain"] = chain
    return final_ref


def _paper_final_verdict_path(project_dir: Path) -> Path | None:
    for candidate in [
        project_dir / "closure" / "FINAL_VERDICT.json",
        project_dir / "closure" / "final-verdict.json",
    ]:
        if candidate.exists():
            return candidate
    return None


def _paper_final_verdict_failure(token: str, verdict_path: Path, diagnostic: str) -> dict[str, Any]:
    del diagnostic
    return {
        "failure_id": f"failure-paper-final-verdict-{token}",
        "status": "blocked",
        "uri": str(verdict_path),
    }


def _paper_gate_evidence_refs(
    evidence_path: str,
    evidence_refs: list[dict[str, Any]],
    project_dir: Path,
) -> list[str]:
    if not evidence_path:
        return []
    candidate = Path(evidence_path)
    if not candidate.is_absolute():
        candidate = project_dir / candidate
    candidate_key = _paper_evidence_path_key(candidate)
    refs: list[str] = []
    for ref in evidence_refs:
        uri = str(ref.get("uri") or "")
        evidence_id = str(ref.get("evidence_id") or "")
        if uri and evidence_id and _paper_evidence_path_key(Path(uri)) == candidate_key:
            refs.append(evidence_id)
    return refs


def _paper_evidence_path_key(path: Path) -> str:
    try:
        return str(path.resolve(strict=False)).casefold()
    except OSError:
        return str(path.absolute()).casefold()


def _paper_gate_refs(
    project_dir: Path,
    paper_id: str,
    state: dict[str, Any],
    evidence_refs: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    token = _safe_token(paper_id)
    refs: list[dict[str, Any]] = []
    evidence_ids = {str(ref.get("evidence_id") or "") for ref in evidence_refs}
    privacy_path = project_dir / "paper_task" / "PRIVACY_ATTESTATION.yaml"
    privacy_evidence_id = f"ev-paper-privacy-{token}"
    if privacy_path.exists() and privacy_evidence_id in evidence_ids:
        refs.append({
            "gate_id": f"gate-paper-privacy-{token}",
            "result": "pass",
            "uri": str(privacy_path),
            "evidence_refs": [privacy_evidence_id],
        })
    if _paper_human_gate_open(state):
        refs.append({
            "gate_id": f"gate-paper-human-{token}",
            "result": "blocked",
            "uri": str(project_dir / "PAPER_STATE.yaml"),
            "evidence_refs": [],
        })
    return refs


def _paper_failure_refs(
    project_dir: Path,
    paper_id: str,
    state: dict[str, Any],
    effective_status: str,
) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    normalized_status = _safe_token(effective_status).replace("_", "-")
    if normalized_status in {"human-required", "needs-human"} or _paper_human_gate_open(state):
        refs.append({
            "failure_id": f"failure-paper-human-gate-{_safe_token(paper_id)}",
            "status": "blocked",
            "uri": str(project_dir / "PAPER_STATE.yaml"),
        })
    return refs


def _paper_limitations(
    project_dir: Path,
    state: dict[str, Any],
    has_final_verdict: bool,
) -> list[str]:
    limitations = [
        "paper adapter is a read-only projection and does not create final acceptance authority",
    ]
    if not (project_dir / "paper_task" / "PRIVACY_ATTESTATION.yaml").exists():
        limitations.append("paper privacy attestation is not recorded as a gate artifact")
    if state.get("final_acceptance") is True and not has_final_verdict:
        limitations.append("paper final_acceptance requires a canonical FinalVerdict before final_ready projection")
    if _paper_human_gate_open(state):
        limitations.append("paper workflow is waiting for a human gate decision")
    return limitations


def _paper_human_gate_open(state: dict[str, Any]) -> bool:
    decision = _safe_token(state.get("human_gate_decision")).replace("_", "-")
    accepted_decisions = {"approved", "accepted", "pass", "passed", "resolved"}
    return bool(state.get("human_required") or state.get("human_gate_triggered")) and decision not in accepted_decisions


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
    if (
        final_verdict_ref
        and final_verdict_ref.get("final_state") == "accepted_with_limitation"
        and _has_pass_review(review_refs)
        and gate_refs
    ):
        gate_state = "gate_limited" if any(ref.get("result") == "warning" for ref in gate_refs) else "gate_passed"
        return _axis(
            "closed",
            "passed",
            "review_passed",
            gate_state,
            "accepted_with_limitation",
            "completed",
        )
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
    source_hash: str | None = None,
) -> dict[str, Any]:
    return {
        "adapter_id": adapter_id,
        "source_type": source_type,
        "adapter_version": ADAPTER_VERSION,
        "provenance": {
            "source_path": str(source_path),
            "legacy_id": legacy_id,
            "adapter_version": ADAPTER_VERSION,
            "source_hash": source_hash if source_hash is not None else _source_hash(source_path),
        },
        "record": record,
    }


def _failure_entry(
    adapter_id: str,
    legacy_id: str,
    source_path: Path,
    diagnostic: str,
    *,
    source_hash: str | None = None,
) -> dict[str, Any]:
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
        source_hash=source_hash,
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


def _read_runtime_json_file(
    path: Path,
    runtime: Path,
) -> tuple[dict[str, Any], str, str]:
    raw, diagnostic = _read_runtime_contained_bytes(path, runtime)
    if raw is None:
        return {}, diagnostic or f"missing JSON file: {path}", ""
    source_hash = f"sha256:{hashlib.sha256(raw).hexdigest()}"
    try:
        data = json.loads(raw.decode("utf-8-sig"))
    except UnicodeDecodeError as exc:
        return {}, f"unable to decode JSON file: {type(exc).__name__}: {exc}", source_hash
    except json.JSONDecodeError as exc:
        return {}, f"invalid JSON at line {exc.lineno}, column {exc.colno}: {exc.msg}", source_hash
    if not isinstance(data, dict):
        return {}, "JSON root is not an object", source_hash
    return data, "", source_hash


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
    return _read_jsonl_snapshot(path)[0]


def _read_jsonl_snapshot(path: Path) -> tuple[list[dict[str, Any]], str]:
    if not path.exists():
        return [], ""
    try:
        raw = path.read_bytes()
    except OSError as exc:
        return [{
            "legacy_id": path.name,
            "diagnostic": f"unable to read JSONL file: {type(exc).__name__}: {exc}",
        }], ""
    source_hash = f"sha256:{hashlib.sha256(raw).hexdigest()}"
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        return [{
            "legacy_id": path.name,
            "diagnostic": f"unable to decode JSONL file: {type(exc).__name__}: {exc}",
        }], source_hash
    return _parse_jsonl_text(path, text), source_hash


def _read_runtime_jsonl_snapshot(
    path: Path,
    runtime: Path,
) -> tuple[list[dict[str, Any]], str]:
    raw, diagnostic = _read_runtime_contained_bytes(path, runtime)
    if raw is None:
        if not diagnostic:
            return [], ""
        return [{
            "legacy_id": path.name,
            "diagnostic": diagnostic,
        }], ""
    source_hash = f"sha256:{hashlib.sha256(raw).hexdigest()}"
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        return [{
            "legacy_id": path.name,
            "diagnostic": f"unable to decode JSONL file: {type(exc).__name__}: {exc}",
        }], source_hash
    return _parse_jsonl_text(path, text), source_hash


def _read_runtime_contained_bytes(
    path: Path,
    runtime: Path,
) -> tuple[bytes | None, str]:
    try:
        handle = path.open("rb")
    except FileNotFoundError:
        return None, ""
    except OSError as exc:
        return None, f"unable to read runtime file: {type(exc).__name__}: {exc}"
    try:
        with handle:
            before = os.fstat(handle.fileno())
            final_path = _final_path_from_handle(handle)
            if not _path_is_within_runtime(final_path, runtime):
                return None, (
                    "runtime containment rejected final handle path outside runtime: "
                    f"{final_path}"
                )
            raw = handle.read()
            after = os.fstat(handle.fileno())
    except OSError as exc:
        return None, f"unable to read runtime file: {type(exc).__name__}: {exc}"
    if _stable_fstat(before) != _stable_fstat(after):
        return None, f"runtime file changed during handle-bound read: {path}"
    return raw, ""


def _final_path_from_handle(handle: BinaryIO) -> Path:
    if os.name == "nt":
        return _windows_final_path_from_handle(handle)
    return _posix_final_path_from_handle(handle, sys.platform)


def _posix_final_path_from_handle(handle: BinaryIO, platform: str) -> Path:
    if platform.startswith("linux"):
        return Path(os.readlink(f"/proc/self/fd/{handle.fileno()}"))
    if platform == "darwin":
        return _darwin_final_path_from_handle(handle)
    raise OSError(f"final handle path resolution is unsupported on {platform}")


def _darwin_final_path_from_handle(handle: BinaryIO) -> Path:
    import fcntl

    buffer_size = 1024
    raw_path = fcntl.fcntl(
        handle.fileno(),
        fcntl.F_GETPATH,
        b"\0" * buffer_size,
    )
    if not isinstance(raw_path, bytes):
        raise OSError("Darwin F_GETPATH returned a non-bytes path")
    terminator = raw_path.find(b"\0")
    if terminator <= 0:
        raise OSError("Darwin F_GETPATH returned an empty or unterminated path")
    return Path(os.fsdecode(raw_path[:terminator]))


def _windows_final_path_from_handle(handle: BinaryIO) -> Path:
    import ctypes
    import msvcrt
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    get_final_path = kernel32.GetFinalPathNameByHandleW
    get_final_path.argtypes = [
        wintypes.HANDLE,
        wintypes.LPWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
    ]
    get_final_path.restype = wintypes.DWORD
    os_handle = msvcrt.get_osfhandle(handle.fileno())
    size = 260
    while True:
        buffer = ctypes.create_unicode_buffer(size)
        length = get_final_path(os_handle, buffer, size, 0)
        if length == 0:
            error = ctypes.get_last_error()
            raise OSError(error, ctypes.FormatError(error))
        if length < size:
            value = buffer.value
            if value.startswith("\\\\?\\UNC\\"):
                value = "\\\\" + value[8:]
            elif value.startswith("\\\\?\\"):
                value = value[4:]
            return Path(value)
        size = length + 1


def _path_is_within_runtime(path: Path, runtime: Path) -> bool:
    try:
        path.resolve(strict=True).relative_to(runtime.resolve(strict=True))
    except (OSError, RuntimeError, ValueError):
        return False
    return True


def _stable_fstat(value: os.stat_result) -> tuple[int, ...]:
    return (
        value.st_dev,
        value.st_ino,
        value.st_mode,
        value.st_nlink,
        value.st_size,
        value.st_mtime_ns,
        value.st_ctime_ns,
    )


def _parse_jsonl_text(path: Path, text: str) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    lines = text.splitlines()
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
) -> tuple[
    dict[str, Any] | None,
    list[dict[str, Any]],
    list[str],
    list[dict[str, Any]],
    list[str],
]:
    failures: list[dict[str, Any]] = []
    diagnostics: list[str] = []
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
            diagnostics.append(diagnostic)
            continue
        artifact, artifact_diagnostic = _validate_final_verdict_artifact(Path(ref_path), payload)
        if artifact_diagnostic:
            failures.append(_event_failure_ref("team-final-verdict", event, artifact_diagnostic, ref_path))
            diagnostics.append(artifact_diagnostic)
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
            diagnostics.append(context_diagnostic)
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
            gate_diagnostic = (
                f"final verdict gate_refs are not passing in artifact: {', '.join(missing_gates)}"
            )
            failures.append(_event_failure_ref(
                "team-final-verdict",
                event,
                gate_diagnostic,
                ref_path,
            ))
            diagnostics.append(gate_diagnostic)
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
        return final_ref, [], [str(item) for item in artifact.get("limitations", []) if str(item)] if isinstance(artifact.get("limitations"), list) else [], gate_refs, []
    return None, failures, [], [], diagnostics


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
    role_token = _safe_token(producer_role).replace("_", "-").replace(".", "-")
    if not verdict_id:
        return "verdict_id is missing"
    if not verdict_id.startswith("fv-"):
        return "verdict_id must start with fv-"
    if not producer_role:
        return "producer_role is missing"
    role_parts = set(role_token.split("-"))
    if (
        role_token in {"executor", "fixer", "coder", "worker", "clientadapter"}
        or "client" in role_parts
    ):
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
    schema_file = _repo_root() / schema_path
    if schema_file.is_file():
        schema = json.loads(schema_file.read_text(encoding="utf-8-sig"))
    elif schema_path == "schemas/agent-runtime/final-verdict.schema.json":
        packaged_schema = Path(__file__).resolve().parent / "final-verdict.schema.json"
        if not packaged_schema.is_file():
            raise FileNotFoundError(f"schema is not packaged: {schema_path}")
        schema = json.loads(packaged_schema.read_text(encoding="utf-8"))
    else:
        raise FileNotFoundError(f"schema is not packaged: {schema_path}")
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
