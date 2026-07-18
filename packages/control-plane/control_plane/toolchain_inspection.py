"""Read-only projection of one governed toolchain run."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .backup_guard import is_inside
from .go_dispatch import load_go_run_result_snapshot
from .run_index import build_run_index


def inspect_toolchain_run(
    runtime_dir: str | Path,
    run_id: str = "latest",
) -> dict[str, Any]:
    """Return toolchain provenance plus canonical governance state."""
    runtime_root = Path(runtime_dir).resolve()
    resolved_run_id = _resolve_toolchain_run_id(runtime_root, run_id)
    result, metadata_hash = load_go_run_result_snapshot(
        runtime_root,
        resolved_run_id,
    )
    if result.go_run_id != resolved_run_id:
        raise ValueError(
            f"go run metadata changed during inspection: {resolved_run_id}"
        )
    toolchain = _validated_toolchain_provenance(result.toolchain, resolved_run_id)

    if len(result.agents) != 1:
        raise ValueError(
            f"toolchain run must have exactly one executor: {resolved_run_id}"
        )
    agent = result.agents[0]
    report_path = Path(agent.report_path).resolve() if agent.report_path else None
    if (
        report_path is None
        or not is_inside(report_path, runtime_root)
        or not report_path.is_file()
    ):
        raise ValueError(f"toolchain report is unavailable: {resolved_run_id}")

    canonical = _canonical_record(
        runtime_root,
        resolved_run_id,
        metadata_hash,
    )
    return {
        "schema_version": 1,
        "run_id": resolved_run_id,
        "project_id": result.project_id,
        "project_root": result.project_root,
        "action": toolchain["action"],
        "manifest_path": toolchain["manifest_path"],
        "approved_manifest_sha256": toolchain["approved_manifest_sha256"],
        "working_directory": toolchain["working_directory"],
        "worker_outcome": agent.worker_status or agent.status or "unknown",
        "report_path": str(report_path),
        "review_state": canonical["review_state"],
        "acceptance_state": canonical["acceptance_state"],
        "canonical_outcome": canonical["outcome"],
        "execution": "explicit_only",
    }


def render_toolchain_inspection(inspection: dict[str, Any]) -> str:
    """Render the bounded inspection projection without adding actions."""
    return "\n".join(
        [
            "DevFrame Toolchain status",
            f"run_id        : {inspection['run_id']}",
            f"project       : {inspection['project_root']}",
            f"action        : {inspection['action']}",
            f"manifest_sha  : {inspection['approved_manifest_sha256']}",
            f"working_dir   : {inspection['working_directory']}",
            f"worker        : {inspection['worker_outcome']}",
            f"review        : {inspection['review_state']}",
            f"acceptance    : {inspection['acceptance_state']}",
            f"report        : {inspection['report_path']}",
        ]
    ) + "\n"


def _resolve_toolchain_run_id(runtime_root: Path, run_id: str) -> str:
    if run_id != "latest":
        directory_run_id = _validated_run_id(run_id)
        path = runtime_root / "go-runs" / directory_run_id / "go-run.json"
        _validate_runtime_containment(path, runtime_root, "go run metadata")
        if not path.is_file():
            raise ValueError(f"go run not found: {directory_run_id}")
        _validated_metadata_run_id(_read_metadata(path), directory_run_id)
        return directory_run_id
    base = runtime_root / "go-runs"
    if not base.exists():
        raise ValueError(f"no toolchain runs found in {runtime_root}")
    candidates = list(base.glob("*/go-run.json"))
    for path in candidates:
        _validate_runtime_containment(path, runtime_root, "go run metadata")
    paths = sorted(
        (path for path in candidates if path.is_file()),
        key=lambda path: (path.stat().st_mtime_ns, path.parent.name),
        reverse=True,
    )
    for path in paths:
        directory_run_id = _validated_run_id(path.parent.name)
        try:
            data = _read_metadata(path)
        except ValueError:
            if directory_run_id.startswith("go-"):
                continue
            raise
        if "toolchain" not in data:
            if directory_run_id.startswith("go-"):
                continue
            _validated_metadata_run_id(data, directory_run_id)
            return directory_run_id
        _validated_metadata_run_id(data, directory_run_id)
        return directory_run_id
    raise ValueError(f"no toolchain runs found in {runtime_root}")


def _validated_run_id(run_id: str) -> str:
    if (
        not run_id
        or run_id in {".", ".."}
        or "/" in run_id
        or "\\" in run_id
        or ":" in run_id
    ):
        raise ValueError(f"toolchain run id is invalid: {run_id}")
    return run_id


def _read_metadata(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"go run metadata is unreadable: {path}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"go run metadata is unreadable: {path}")
    return data


def _validated_metadata_run_id(data: dict[str, Any], directory_run_id: str) -> str:
    metadata_run_id = data.get("go_run_id")
    if (
        not isinstance(metadata_run_id, str)
        or not metadata_run_id.strip()
        or metadata_run_id != directory_run_id
    ):
        raise ValueError(
            "go run metadata run id does not match directory: "
            f"{directory_run_id}"
        )
    return metadata_run_id


def _validate_runtime_containment(path: Path, runtime_root: Path, label: str) -> None:
    if not is_inside(path, runtime_root):
        raise ValueError(f"{label} is outside runtime: {path}")


def _validated_toolchain_provenance(
    value: dict[str, str] | None,
    run_id: str,
) -> dict[str, str]:
    if not isinstance(value, dict):
        raise ValueError(f"go run is not a toolchain run: {run_id}")
    required = {
        "action",
        "approved_manifest_sha256",
        "manifest_path",
        "working_directory",
    }
    if any(
        not isinstance(value.get(key), str) or not value[key].strip()
        for key in required
    ):
        raise ValueError(f"toolchain provenance is incomplete: {run_id}")
    action = str(value["action"])
    digest = str(value["approved_manifest_sha256"])
    if action not in {"build", "test", "lint"}:
        raise ValueError(f"toolchain action is invalid: {run_id}")
    if len(digest) != 64 or any(character not in "0123456789abcdef" for character in digest):
        raise ValueError(f"toolchain manifest digest is invalid: {run_id}")
    return {key: str(value[key]) for key in required}


def _canonical_record(
    runtime_root: Path,
    run_id: str,
    metadata_hash: str,
) -> dict[str, Any]:
    matches = []
    for entry in build_run_index(runtime_root).get("canonical_runs", []):
        provenance = entry.get("provenance")
        sources = provenance.get("sources", []) if isinstance(provenance, dict) else []
        if any(
            isinstance(source, dict)
            and source.get("adapter_id") == "go_run"
            and source.get("legacy_id") == run_id
            for source in sources
        ):
            matches.append(entry)
    if len(matches) != 1 or matches[0].get("adapter_id") != "canonical_run":
        raise ValueError(f"toolchain canonical projection is unavailable: {run_id}")
    sources = [
        source
        for source in matches[0].get("provenance", {}).get("sources", [])
        if isinstance(source, dict)
    ]
    source_ids = {str(source.get("adapter_id") or "") for source in sources}
    if not {"go_run", "team_events"} <= source_ids:
        raise ValueError(f"toolchain canonical projection is unavailable: {run_id}")
    go_sources = [
        source
        for source in sources
        if source.get("adapter_id") == "go_run"
        and source.get("legacy_id") == run_id
    ]
    if len(go_sources) != 1:
        raise ValueError(f"toolchain canonical projection is unavailable: {run_id}")
    if go_sources[0].get("source_hash") != metadata_hash:
        raise ValueError(f"go run metadata changed during inspection: {run_id}")
    record = matches[0].get("record")
    if not isinstance(record, dict):
        raise ValueError(f"toolchain canonical projection is unreadable: {run_id}")
    required = {"outcome", "review_state", "acceptance_state"}
    if any(
        not isinstance(record.get(field), str) or not record[field].strip()
        for field in required
    ):
        raise ValueError(f"toolchain canonical projection is unreadable: {run_id}")
    return record
