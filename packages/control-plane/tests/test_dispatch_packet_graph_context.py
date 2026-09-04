"""File-backed tests for optional graph context dispatch integration."""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
from jsonschema.validators import validator_for

from control_plane.agent_adapter import SubAgentObjective
from control_plane.decision_engine import Decision, DecisionMode
from control_plane.dispatch_packet import DispatchPacketStore
from control_plane.graph_context_packet_integration import (
    GraphContextPacketIntegrationError,
)
from control_plane.project_contract import ProjectContract


REPO_ROOT = Path(__file__).resolve().parents[3]


_SELECTION: dict[str, object] = {
        "context_selection_id": "gcs-dispatch-1",
        "graph_projection_id": "graph-dispatch-1",
        "graph_slice_ref": "graph://projection/graph-dispatch-1",
        "project_id": "demo-project",
        "reader": "reviewer",
        "decision_needed": "review",
        "context_profile": "graph-neighborhood",
        "selected_node_ids": ["decision-1"],
        "candidate_roles": {"decision-1": "selected", "evidence-1": "neighbor"},
        "source_refs": [
            {
                "ref_id": "graph-slice-dispatch-1",
                "kind": "artifact",
                "uri": "graph://projection/graph-dispatch-1",
                "included": True,
                "required": True,
                "freshness_state": "current",
            },
            {
                "ref_id": "graph-node-decision-1",
                "kind": "final_verdict",
                "uri": "decision://decision-1",
                "included": True,
                "required": True,
                "freshness_state": "current",
            },
            {
                "ref_id": "graph-node-evidence-1",
                "kind": "evidence",
                "uri": "evidence://evidence-1",
                "included": True,
                "required": False,
                "freshness_state": "stale",
            },
        ],
        "omitted_required_refs": [],
        "omitted_context": [],
        "forbidden_refs": [],
        "assumption_claims": [
            {
                "edge_id": "edge-inferred-1",
                "source": "decision-1",
                "target": "evidence-1",
                "kind": "inferred",
                "authority": "assumption",
            }
        ],
        "omitted_assumptions": [],
        "freshness": {
            "stale_refs": ["graph-node-evidence-1"],
            "unknown_refs": [],
        },
        "completeness_state": "incomplete",
        "privacy_state": "redacted",
        "candidate_source_summary": {
            "selected_count": 1,
            "neighbor_count": 1,
            "included_candidate_count": 2,
        },
        "selection_rationale": "Bounded graph context for review.",
        "limitations": ["The graph slice is bounded."],
        "authority_boundary": {
            "can_execute": False,
            "can_review": True,
            "can_claim_final_acceptance": False,
            "final_verdict_required": True,
        },
        "domain_refs": {},
}


def _selection(project_id: str) -> dict[str, object]:
    selection = copy.deepcopy(_SELECTION)
    selection["project_id"] = project_id
    return selection


def _write_packet(tmp_path: Path, selection: dict[str, object] | None = None):
    project_root = tmp_path / "project"
    project_root.mkdir()
    runtime_dir = tmp_path / "runtime"
    contract = ProjectContract(project_id="demo-project", goal="exercise graph dispatch")
    objective = SubAgentObjective(
        project_id=contract.project_id,
        project_root=str(project_root.resolve()),
        text="review one bounded change",
        dispatch_ready=True,
    )
    decision = Decision(
        mode=DecisionMode.AUTO_EXECUTE,
        operation="review",
        reason="bounded test",
        dispatch_allowed=True,
    )
    packet = DispatchPacketStore(runtime_dir=runtime_dir).write_packet(
        contract=contract,
        project_root=project_root,
        requirement="review one bounded change",
        operation="review",
        targets=["allowed.txt"],
        decision=decision,
        objective=objective,
        dispatch_ready=True,
        graph_context_selection=selection,
    )
    return DispatchPacketStore(runtime_dir=runtime_dir), project_root, packet


def _schema(relative_path: str):
    schema = json.loads((REPO_ROOT / relative_path).read_text(encoding="utf-8"))
    validator = validator_for(schema)
    validator.check_schema(schema)
    return validator(schema)


def test_graph_selection_is_persisted_and_schema_validated(tmp_path: Path) -> None:
    selection = _selection("demo-project")
    store, _project_root, packet = _write_packet(tmp_path, selection)
    packet_dir = Path(packet.packet_dir)

    persisted = json.loads((packet_dir / "packet.json").read_text(encoding="utf-8"))
    _schema("schemas/rdgoal_dispatch_packet.schema.json").validate(persisted)
    assert persisted["graph_context_selection"]["context_selection_id"] == "gcs-dispatch-1"
    assert "reader" not in persisted["graph_context_selection"]
    context_packet = json.loads((packet_dir / "context-packet.json").read_text(encoding="utf-8"))
    context_ledger = json.loads((packet_dir / "context-ledger.json").read_text(encoding="utf-8"))
    _schema("schemas/runtime-governance/context-packet.schema.json").validate(context_packet)
    _schema("schemas/runtime-governance/context-ledger.schema.json").validate(context_ledger)
    assert "-graph-" in context_packet["context_packet_id"]
    assert context_packet["completeness_state"] == "incomplete"
    assert context_packet["domain_refs"]["graph_context_selection"]["candidate_roles"] == {
        "decision-1": "selected",
        "evidence-1": "neighbor",
    }
    assert len(context_ledger["entries"]) == 3
    amendment = context_ledger["entries"][-1]
    assert amendment["event_type"] == "amendment_recorded"
    assert amendment["superseded_context_packet_id"] != amendment["resulting_context_packet_id"]
    assert amendment["resulting_context_packet_id"] == context_packet["context_packet_id"]

    loaded = store.load_packet(packet_dir)
    assert loaded.graph_context_selection == packet.graph_context_selection


def test_default_packet_keeps_historical_shape_and_context(tmp_path: Path) -> None:
    store, _project_root, packet = _write_packet(tmp_path)
    packet_dir = Path(packet.packet_dir)
    persisted = json.loads((packet_dir / "packet.json").read_text(encoding="utf-8"))
    _schema("schemas/rdgoal_dispatch_packet.schema.json").validate(persisted)
    assert "graph_context_selection" not in persisted
    context_packet = json.loads((packet_dir / "context-packet.json").read_text(encoding="utf-8"))
    context_ledger = json.loads((packet_dir / "context-ledger.json").read_text(encoding="utf-8"))
    _schema("schemas/runtime-governance/context-packet.schema.json").validate(context_packet)
    _schema("schemas/runtime-governance/context-ledger.schema.json").validate(context_ledger)
    assert "graph_context_selection" not in context_packet["domain_refs"]
    assert len(context_ledger["entries"]) == 2
    assert store.load_packet(packet_dir).graph_context_selection is None


def test_graph_context_survives_ensure_and_rebase(tmp_path: Path) -> None:
    selection = _selection("demo-project")
    store, project_root, packet = _write_packet(tmp_path, selection)
    packet_dir = Path(packet.packet_dir)
    ensured = store.ensure_context_artifacts(packet_dir)
    ensured_context = json.loads(Path(ensured.context_packet_path).read_text(encoding="utf-8"))
    assert ensured.graph_context_selection == packet.graph_context_selection
    assert ensured_context["domain_refs"]["graph_context_selection"]["graph_projection_id"] == (
        "graph-dispatch-1"
    )
    new_root = tmp_path / "isolated-project"
    new_root.mkdir()
    rebased = store.rebase_packet(packet_dir, new_root)
    assert Path(rebased.project_root) == new_root.resolve()
    assert rebased.graph_context_selection == packet.graph_context_selection
    rebased_context = json.loads(Path(rebased.context_packet_path).read_text(encoding="utf-8"))
    assert rebased_context["project_id"] == "demo-project"
    assert rebased_context["domain_refs"]["graph_context_selection"]["context_selection_id"] == (
        "gcs-dispatch-1"
    )
    assert Path(packet.project_root) == project_root.resolve()


@pytest.mark.parametrize("mutation", ["project", "unsafe_uri"])
def test_invalid_graph_selection_fails_before_packet_artifacts(tmp_path: Path, mutation: str) -> None:
    selection = _selection("demo-project")
    if mutation == "project":
        selection["project_id"] = "other-project"
    else:
        selection["source_refs"] = copy.deepcopy(selection["source_refs"])
        selection["source_refs"][1]["uri"] = r"C:\secret\token.txt"

    runtime_dir = tmp_path / "runtime"
    contract = ProjectContract(project_id="demo-project", goal="reject unsafe graph input")
    project_root = tmp_path / "project"
    project_root.mkdir()
    objective = SubAgentObjective(
        project_id=contract.project_id,
        project_root=str(project_root.resolve()),
        text="must not write",
        dispatch_ready=True,
    )
    decision = Decision(
        mode=DecisionMode.AUTO_EXECUTE,
        operation="review",
        reason="bounded test",
        dispatch_allowed=True,
    )
    with pytest.raises(GraphContextPacketIntegrationError):
        DispatchPacketStore(runtime_dir=runtime_dir).write_packet(
            contract=contract,
            project_root=project_root,
            requirement="must not write",
            operation="review",
            targets=["allowed.txt"],
            decision=decision,
            objective=objective,
            dispatch_ready=True,
            graph_context_selection=selection,
        )
    assert not (runtime_dir / "rdgoal-outbox").exists()
