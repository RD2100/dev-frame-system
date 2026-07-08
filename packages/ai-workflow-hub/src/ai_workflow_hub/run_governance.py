"""Run governance utilities — audit trail, evidence status, chain-of-custody.

Lightweight governance layer for run evidence verification. Model-agnostic.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .run_store import load_run_file


def _load_chain_evidence(run_dir: Path) -> dict[str, Any] | None:
    chain_path = run_dir / "chain-evidence.json"
    if not chain_path.exists():
        return None
    try:
        payload = json.loads(chain_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"_invalid": "unreadable"}
    return payload if isinstance(payload, dict) else {"_invalid": "non_object"}


def _classify_chain_evidence(payload: dict[str, Any] | None) -> tuple[str, str]:
    if payload is None:
        return "missing", "chain-evidence.json is not present"
    invalid = payload.get("_invalid")
    if invalid:
        return "invalid", f"chain-evidence.json is {invalid}"
    nodes = payload.get("nodes")
    if isinstance(nodes, dict):
        return (
            "ai_workflow_hub_nodes",
            "nodes-style chain evidence is visible but not canonical acceptance evidence",
        )
    if "evidence_files" in payload and "timestamps" in payload:
        return "go_evidence_v1", "go_evidence/devframe-atgo chain evidence shape"
    return "unknown", "chain-evidence.json shape is not recognized"


def _chain_evidence_adapter(
    payload: dict[str, Any] | None,
    state: dict[str, Any] | None,
    run_dir: Path,
) -> dict[str, Any]:
    if payload is None:
        return _blocked_adapter("missing", "chain-evidence.json is not present")
    invalid = payload.get("_invalid")
    if invalid:
        return _blocked_adapter("invalid", f"chain-evidence.json is {invalid}")
    if isinstance(payload.get("nodes"), dict):
        return _nodes_chain_evidence_adapter(payload, state or {}, run_dir)
    if "evidence_files" in payload and "timestamps" in payload:
        diagnostic = _go_evidence_adapter_diagnostic(payload)
        if diagnostic:
            return _blocked_adapter("go_evidence_v1", diagnostic)
        return {
            "source_shape": "go_evidence_v1",
            "normalization_status": "canonical_passthrough",
            "normalized": True,
            "acceptance_candidate": False,
            "reason": "chain evidence is already in the go_evidence/devframe-atgo shape",
            "canonical_schema": "schemas/agent-runtime/chain-evidence.schema.json",
            "normalized_chain_evidence": payload,
        }
    return _blocked_adapter("unknown", "chain-evidence.json shape is not recognized")


def _go_evidence_adapter_diagnostic(payload: dict[str, Any]) -> str:
    evidence_files = payload.get("evidence_files")
    if not isinstance(evidence_files, list) or not evidence_files:
        return "go_evidence_v1 evidence_files must be a non-empty list"
    if not all(isinstance(item, str) and item.strip() for item in evidence_files):
        return "go_evidence_v1 evidence_files must contain non-empty strings"
    timestamps = payload.get("timestamps")
    if not isinstance(timestamps, dict):
        return "go_evidence_v1 timestamps must be a mapping"
    created_at = timestamps.get("created_at")
    if not isinstance(created_at, str) or not created_at.strip():
        return "go_evidence_v1 timestamps.created_at must be present"
    return ""


def _blocked_adapter(source_shape: str, reason: str) -> dict[str, Any]:
    return {
        "source_shape": source_shape,
        "normalization_status": "blocked",
        "normalized": False,
        "acceptance_candidate": False,
        "reason": reason,
        "canonical_schema": "schemas/agent-runtime/chain-evidence.schema.json",
        "normalized_chain_evidence": None,
    }


def _nodes_chain_evidence_adapter(
    payload: dict[str, Any],
    state: dict[str, Any],
    run_dir: Path,
) -> dict[str, Any]:
    nodes = payload.get("nodes")
    if not isinstance(nodes, dict):
        return _blocked_adapter("ai_workflow_hub_nodes", "nodes payload is not a mapping")

    worker_results: list[dict[str, Any]] = []
    evidence_files = [str(run_dir / "chain-evidence.json")]
    for node_id, node in nodes.items():
        if not isinstance(node, dict):
            worker_results.append({"node_id": str(node_id), "status": "unknown"})
            continue
        exit_code = node.get("exit_code")
        if exit_code == 0:
            status = "passed"
        elif isinstance(exit_code, int):
            status = "blocked"
        else:
            status = "unknown"
        worker_results.append(
            {
                "node_id": str(node_id),
                "status": status,
                "backend": str(node.get("backend") or "unknown"),
                "exit_code": exit_code,
            }
        )
        for key in ("stdout_log", "stderr_log", "artifact_path"):
            value = node.get(key)
            if isinstance(value, str) and value.strip():
                evidence_files.append(value)

    seen: set[str] = set()
    evidence_files = [item for item in evidence_files if not (item in seen or seen.add(item))]
    timestamps = payload.get("timestamps") if isinstance(payload.get("timestamps"), dict) else {}
    created_at = (
        state.get("created_at")
        or timestamps.get("created_at")
        or datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    )
    normalized_chain_evidence = {
        "run_id": str(payload.get("run_id") or state.get("run_id") or run_dir.name),
        "executor_id": str(state.get("executor_id") or payload.get("executor_id") or "ai-workflow-hub"),
        "mode": str(state.get("mode") or payload.get("mode") or "unknown"),
        "planner": str(state.get("planner") or payload.get("planner") or "unknown"),
        "task": str(state.get("task") or state.get("task_id") or payload.get("task") or run_dir.name),
        "methodology": {
            "adapter": "ai_workflow_hub_nodes_to_chain_evidence",
            "source_shape": "ai_workflow_hub_nodes",
            "worker_results": worker_results,
        },
        "evidence_files": evidence_files,
        "timestamps": {"created_at": str(created_at)},
    }
    return {
        "source_shape": "ai_workflow_hub_nodes",
        "normalization_status": "normalized",
        "normalized": True,
        "acceptance_candidate": False,
        "reason": "nodes-style chain evidence adapted as a non-authoritative candidate",
        "canonical_schema": "schemas/agent-runtime/chain-evidence.schema.json",
        "normalized_chain_evidence": normalized_chain_evidence,
    }


def summarize_run_governance(run_dir: str, state: dict[str, Any] | None = None) -> dict[str, Any]:
    """Summarize governance state for a run directory.

    Returns a dict with evidence_ok, chain_trusted, run_status, missing_files,
    present_files, final_report_consistent, final_report_status, chain_status,
    and governance metadata.
    """
    rd = Path(run_dir)
    required_files = [
        "state.json", "final-report.md", "safety-report.json",
        "diff.patch", "test-output.md", "review.md", "review.yaml",
    ]

    present_files = []
    missing_files = []
    for f in required_files:
        if (rd / f).exists():
            present_files.append(f)
        else:
            missing_files.append(f)

    evidence_ok = len(missing_files) == 0 or all(
        f in ("review.md", "review.yaml") for f in missing_files
    )

    # Load state for deeper checks
    run_status = "unknown"
    chain_status = "MISSING"
    chain_trusted = False
    final_report_status = "MISSING"
    final_report_consistent = False
    chain_evidence = _load_chain_evidence(rd)
    chain_evidence_shape, chain_evidence_diagnostic = _classify_chain_evidence(chain_evidence)

    s = state if isinstance(state, dict) else None
    state_file = rd / "state.json"
    if s is None and state_file.exists():
        try:
            s = json.loads(state_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            s = None
    if s is not None:
        try:
            run_status = s.get("status", "unknown")
            chain_status = s.get("chain_status", "UNKNOWN")
            chain_trusted = s.get("chain_trusted") is True
            final_report_status = s.get("final_report_status", "MISSING")
            final_report_consistent = s.get("final_report_consistent", False)
        except AttributeError:
            pass
    chain_evidence_adapter = _chain_evidence_adapter(chain_evidence, s, rd)
    if chain_evidence_shape == "missing":
        chain_status = "MISSING_CHAIN_EVIDENCE"
        chain_trusted = False
    elif chain_evidence_shape == "ai_workflow_hub_nodes":
        chain_status = "UNTRUSTED_NODES_STYLE"
        chain_trusted = False
    elif chain_evidence_shape == "invalid":
        chain_status = "INVALID_CHAIN_EVIDENCE"
        chain_trusted = False
    elif chain_evidence_shape == "unknown":
        chain_status = "UNKNOWN_CHAIN_EVIDENCE"
        chain_trusted = False

    return {
        "evidence_ok": evidence_ok,
        "chain_trusted": chain_trusted,
        "chain_status": chain_status,
        "run_status": run_status,
        "missing_files": missing_files,
        "present_files": present_files,
        "final_report_consistent": final_report_consistent,
        "final_report_status": final_report_status,
        "chain_evidence_shape": chain_evidence_shape,
        "chain_evidence_diagnostic": chain_evidence_diagnostic,
        "chain_evidence_adapter": chain_evidence_adapter,
        "governance": {
            "chain_evidence_shape": chain_evidence_shape,
            "chain_evidence_diagnostic": chain_evidence_diagnostic,
            "chain_evidence_adapter": chain_evidence_adapter,
        },
    }


def render_full_governance_cli(governance: dict[str, Any]) -> str:
    """Render a governance summary dict as CLI-formatted text."""
    lines = []
    lines.append("─" * 60)
    lines.append("  RUN GOVERNANCE")

    # Evidence
    evidence_ok = governance.get("evidence_ok", False)
    status_mark = "[OK]" if evidence_ok else "[WARN]"
    lines.append(f"  Evidence  {status_mark}")

    present = governance.get("present_files", [])
    missing = governance.get("missing_files", [])
    if present:
        lines.append(f"    present: {', '.join(present)}")
    if missing:
        lines.append(f"    missing: {', '.join(missing)}")

    # Chain
    chain_trusted = governance.get("chain_trusted", False)
    chain_mark = "[OK]" if chain_trusted else "[WARN]"
    chain_status = governance.get("chain_status", "MISSING")
    lines.append(f"  Chain     {chain_mark}  status={chain_status}")
    chain_shape = governance.get("chain_evidence_shape")
    if chain_shape:
        lines.append(f"    chain-evidence shape: {chain_shape}")
    chain_adapter = governance.get("chain_evidence_adapter")
    if chain_adapter:
        lines.append(f"    chain-evidence adapter: {chain_adapter.get('normalization_status', 'unknown')}")
        lines.append(f"    adapter source: {chain_adapter.get('source_shape', 'unknown')}")

    # Run status
    run_status = governance.get("run_status", "unknown")
    fr_ok = governance.get("final_report_consistent", False)
    fr_mark = "[OK]" if fr_ok else ""
    fr_status = governance.get("final_report_status", "MISSING")
    lines.append(f"  Run       status={run_status}  final-report={fr_status} {fr_mark}")

    lines.append("─" * 60)
    return "\n".join(lines)


def render_full_governance_md(governance: dict[str, Any]) -> str:
    """Render a governance summary dict as Markdown."""
    lines = ["## Run Governance", ""]
    evidence_ok = governance.get("evidence_ok", False)
    lines.append(f"- Evidence: {'[OK]' if evidence_ok else '[WARN]'}")
    for f in governance.get("present_files", []):
        lines.append(f"  - present: {f}")
    for f in governance.get("missing_files", []):
        lines.append(f"  - missing: {f}")
    chain_trusted = governance.get("chain_trusted", False)
    lines.append(f"- Chain: {'[OK]' if chain_trusted else '[WARN]'} status={governance.get('chain_status', 'MISSING')}")
    if governance.get("chain_evidence_shape"):
        lines.append(f"  - chain-evidence shape: {governance.get('chain_evidence_shape')}")
    if governance.get("chain_evidence_diagnostic"):
        lines.append(f"  - diagnostic: {governance.get('chain_evidence_diagnostic')}")
    chain_adapter = governance.get("chain_evidence_adapter")
    if chain_adapter:
        lines.append(f"- Chain adapter: {chain_adapter.get('normalization_status', 'unknown')}")
        lines.append(f"  - adapter source: {chain_adapter.get('source_shape', 'unknown')}")
    lines.append(f"- Run: status={governance.get('run_status', 'unknown')} final-report={governance.get('final_report_status', 'MISSING')}")
    lines.append("")
    return "\n".join(lines)
