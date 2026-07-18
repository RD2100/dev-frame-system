"""Offline conformance checks for replaceable executor adapters."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .run_index import build_run_index


_CANONICAL_KEYS = (
    "domain",
    "profile",
    "outcome",
    "review_state",
    "gate_state",
    "acceptance_state",
)


def _select_canonical_go_record(
    runtime_dir: str | Path,
    run_id: str | None,
) -> tuple[dict[str, Any] | None, list[str]]:
    index = build_run_index(runtime_dir)
    matches: list[dict[str, Any]] = []
    for entry in index.get("canonical_runs", []):
        sources = entry.get("provenance", {}).get("sources", [])
        adapter_ids = {source.get("adapter_id") for source in sources}
        record = entry.get("record")
        if not isinstance(record, dict):
            continue
        if {"go_run", "team_events"} <= adapter_ids:
            if run_id and record.get("run_id") != run_id:
                continue
            matches.append(entry)
    if len(matches) == 1:
        return matches[0], []
    if not matches:
        suffix = f" for run {run_id!r}" if run_id else ""
        return None, [f"no unique paired canonical go record{suffix}"]
    return None, [
        f"runtime has {len(matches)} matching canonical go records; specify an exact run id"
    ]


def verify_adapter_conformance(
    reference_runtime: str | Path,
    candidate_runtime: str | Path,
    *,
    reference_run_id: str | None = None,
    candidate_run_id: str | None = None,
) -> dict[str, Any]:
    """Compare canonical governance fields without modifying either runtime."""
    errors: list[str] = []
    reference, reference_errors = _select_canonical_go_record(
        reference_runtime, reference_run_id
    )
    candidate, candidate_errors = _select_canonical_go_record(
        candidate_runtime, candidate_run_id
    )
    errors.extend(f"reference: {error}" for error in reference_errors)
    errors.extend(f"candidate: {error}" for error in candidate_errors)

    result: dict[str, Any] = {
        "status": "fail",
        "errors": errors,
        "reference": {"runtime_dir": str(Path(reference_runtime).resolve())},
        "candidate": {"runtime_dir": str(Path(candidate_runtime).resolve())},
        "semantic_keys": list(_CANONICAL_KEYS),
    }
    if reference is None or candidate is None:
        return result

    reference_record = reference["record"]
    candidate_record = candidate["record"]
    reference_semantics = {
        key: reference_record.get(key) for key in _CANONICAL_KEYS
    }
    candidate_semantics = {
        key: candidate_record.get(key) for key in _CANONICAL_KEYS
    }
    result["reference"].update(
        {"run_id": reference_record.get("run_id"), "semantic": reference_semantics}
    )
    result["candidate"].update(
        {"run_id": candidate_record.get("run_id"), "semantic": candidate_semantics}
    )
    for label, record in (("reference", reference_record), ("candidate", candidate_record)):
        if record.get("domain") != "code":
            errors.append(f"{label}: canonical record domain must be code")
        if record.get("profile") != "go":
            errors.append(f"{label}: canonical record profile must be go")
    if reference_semantics != candidate_semantics:
        errors.append("canonical governance fields differ")
    for label, entry in (("reference", reference), ("candidate", candidate)):
        domain_refs = entry["record"].get("domain_refs", {})
        source_domain_refs = domain_refs.get("source_domain_refs", {})
        go_sources = source_domain_refs.get("go_run", [])
        drivers = {
            str(source.get("driver") or "").strip()
            for source in go_sources
            if str(source.get("driver") or "").strip()
        }
        if not drivers:
            errors.append(f"{label}: go_run provenance lacks adapter driver")
        result[label]["drivers"] = sorted(drivers)

    result["status"] = "pass" if not errors else "fail"
    return result
