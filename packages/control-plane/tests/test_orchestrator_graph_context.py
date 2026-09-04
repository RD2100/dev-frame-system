"""Tests for the explicit graph-selection orchestrator caller seam."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema.validators import validator_for

from control_plane.graph_context_packet_integration import GraphContextPacketIntegrationError
from control_plane.graph_context_selection import build_graph_context_selection
from control_plane.orchestrator import Orchestrator
from control_plane.project_contract import render_contract_markdown


REPO_ROOT = Path(__file__).resolve().parents[3]


def _graph_slice(project_id: str) -> dict[str, object]:
    return {
        "graph_projection_id": "graph-orchestrator-1",
        "project_id": project_id,
        "selected_node_ids": ["decision-1"],
        "source_snapshot_refs": ["repo://docs/plan.md"],
        "nodes": [
            {
                "id": "decision-1",
                "type": "decision",
                "authority": "human_decided",
                "privacy_class": "public_repo",
                "label": "not copied",
                "source_ref": "decision://decision-1",
                "freshness": "current",
            },
            {
                "id": "evidence-1",
                "type": "evidence",
                "authority": "test_verified",
                "privacy_class": "public_repo",
                "source_ref": "evidence://evidence-1",
                "freshness": "stale",
            },
        ],
        "edges": [
            {
                "id": "edge-cited-1",
                "source": "decision-1",
                "target": "evidence-1",
                "type": "cited",
                "citation_source": "decision-1",
            }
        ],
        "omitted_neighbors": [],
        "omitted_edges": [],
        "privacy_summary": {"redacted_field_count": 1},
        "validation_summary": {"source_valid": True, "bounded": True},
    }


def _selection(project_id: str) -> dict[str, object]:
    return build_graph_context_selection(
        _graph_slice(project_id),
        reader="reviewer",
        decision_needed="review bounded context",
    )


def _orchestrator(tmp_path: Path) -> tuple[Orchestrator, Path, Path]:
    project_root = tmp_path / "project"
    project_root.mkdir()
    contract_path = tmp_path / "project.md"
    contract_path.write_text(
        render_contract_markdown("demo-project", "exercise explicit graph dispatch"),
        encoding="utf-8",
    )
    orchestrator = Orchestrator(runtime_dir=tmp_path / "runtime", repo_root=tmp_path / "repo")
    orchestrator.register(contract_path, project_root)
    return orchestrator, project_root, contract_path


def _validate(relative_path: str, payload: dict[str, object]) -> None:
    schema = json.loads((REPO_ROOT / relative_path).read_text(encoding="utf-8"))
    validator = validator_for(schema)
    validator.check_schema(schema)
    validator(schema).validate(payload)


def test_dispatch_forwards_explicit_graph_selection_to_existing_writer(tmp_path: Path) -> None:
    orchestrator, _project_root, _contract_path = _orchestrator(tmp_path)
    result = orchestrator.dispatch(
        project_id="demo-project",
        requirement="review one bounded change",
        operation="review",
        targets=["allowed.txt"],
        graph_context_selection=_selection("demo-project"),
    )
    assert result.packet is not None
    assert result.packet.graph_context_selection is not None
    packet_dir = Path(result.packet.packet_dir)
    packet_payload = json.loads((packet_dir / "packet.json").read_text(encoding="utf-8"))
    context_payload = json.loads((packet_dir / "context-packet.json").read_text(encoding="utf-8"))
    ledger_payload = json.loads((packet_dir / "context-ledger.json").read_text(encoding="utf-8"))
    _validate("schemas/rdgoal_dispatch_packet.schema.json", packet_payload)
    _validate("schemas/runtime-governance/context-packet.schema.json", context_payload)
    _validate("schemas/runtime-governance/context-ledger.schema.json", ledger_payload)
    assert packet_payload["graph_context_selection"]["project_id"] == "demo-project"
    assert context_payload["domain_refs"]["graph_context_selection"]["graph_projection_id"] == (
        "graph-orchestrator-1"
    )
    assert len(ledger_payload["entries"]) == 3


def test_dispatch_without_selection_preserves_default_packet_shape(tmp_path: Path) -> None:
    orchestrator, _project_root, _contract_path = _orchestrator(tmp_path)
    result = orchestrator.dispatch(
        project_id="demo-project",
        requirement="review one bounded change",
        operation="review",
    )
    assert result.packet is not None
    payload = json.loads((Path(result.packet.packet_dir) / "packet.json").read_text(encoding="utf-8"))
    assert "graph_context_selection" not in payload
    assert result.packet.graph_context_selection is None


def test_invalid_selection_is_rejected_before_guard_or_journal_side_effects(tmp_path: Path) -> None:
    orchestrator, _project_root, _contract_path = _orchestrator(tmp_path)
    runtime_dir = Path(orchestrator.runtime_dir)
    journal_path = runtime_dir / "rdgoal-events.jsonl"
    journal_before = journal_path.read_text(encoding="utf-8")
    selection = _selection("other-project")
    with pytest.raises(GraphContextPacketIntegrationError, match="project mismatch"):
        orchestrator.dispatch(
            project_id="demo-project",
            requirement="delete one obsolete local file",
            operation="delete",
            targets=["obsolete.txt"],
            graph_context_selection=selection,
        )
    assert journal_path.read_text(encoding="utf-8") == journal_before
    assert not (runtime_dir / "rdgoal-outbox").exists()
    assert not (runtime_dir / "demo-project" / "snapshots").exists()
