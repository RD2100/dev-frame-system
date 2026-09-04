"""Tests for the graph-to-context-packet amendment boundary."""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import pytest
from jsonschema.validators import validator_for

from control_plane.graph_context_packet_integration import (
    GraphContextPacketIntegrationError,
    integrate_graph_context_selection,
)


REPO_ROOT = Path(__file__).resolve().parents[3]
STAMP = "2026-08-28T12:00:00+00:00"


def _digest(value: object) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return "sha256:" + hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _packet() -> dict:
    return {
        "schema_version": "0.1",
        "context_packet_id": "cp-task-1",
        "project_id": "project-1",
        "goal_id": "goal-1",
        "task_id": "task-1",
        "domain": "code",
        "profile": "go-dispatch-task-context",
        "producer_role": "coordinator",
        "created_at": STAMP,
        "intent_summary": "Review a bounded change.",
        "intended_use": "execution",
        "immutability": {"immutable": True, "content_hash": "sha256:" + "a" * 64},
        "source_refs": [
            {
                "ref_id": "task-spec",
                "kind": "file",
                "uri": r"D:\runtime\packet\TASKSPEC.json",
                "included": True,
                "required": True,
                "freshness_state": "current",
            }
        ],
        "omitted_required_refs": [],
        "forbidden_refs": [],
        "freshness": {"checked_at": STAMP, "stale_refs": [], "unknown_refs": []},
        "completeness_state": "complete",
        "privacy_state": "redacted",
        "seal_state": "sealed",
        "limitations": ["Execution context only."],
        "constraints": {
            "allowed_actions": ["execute assigned task"],
            "forbidden_actions": ["claim final acceptance"],
            "stop_lines": ["Independent review is required."],
            "authority_boundary": {
                "can_execute": True,
                "can_review": False,
                "can_claim_final_acceptance": False,
                "final_verdict_required": True,
            },
        },
        "domain_refs": {"packet_id": "packet-1"},
    }


def _ledger() -> dict:
    seed = {
        "ledger_entry_id": "cle-task-1-created",
        "entry_index": 0,
        "previous_entry_hash": None,
        "occurred_at": STAMP,
        "actor_id": "coordinator",
        "actor_role": "coordinator",
        "event_type": "packet_created",
        "context_packet_id": "cp-task-1",
        "summary": "Created the task context packet.",
    }
    return {
        "schema_version": "0.1",
        "context_ledger_id": "cl-task-1",
        "project_id": "project-1",
        "goal_id": "goal-1",
        "task_id": "task-1",
        "created_at": STAMP,
        "append_only": True,
        "entries": [{**seed, "entry_hash": _digest(seed)}],
    }


def _selection() -> dict:
    return {
        "context_selection_id": "gcs-selection-1",
        "graph_projection_id": "graph-1",
        "graph_slice_ref": "graph://projection/graph-1",
        "project_id": "project-1",
        "reader": "reviewer",
        "decision_needed": "review",
        "context_profile": "graph-neighborhood",
        "selected_node_ids": ["decision-1"],
        "candidate_roles": {"decision-1": "selected", "evidence-1": "neighbor"},
        "source_refs": [
            {
                "ref_id": "graph-slice-graph-1",
                "kind": "artifact",
                "uri": "graph://projection/graph-1",
                "included": True,
                "required": True,
                "freshness_state": "unknown",
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
        "omitted_required_refs": [
            {
                "ref": "graph-node-private-1",
                "omission_reason": "forbidden_privacy",
                "impact": "human_required",
            }
        ],
        "omitted_context": [
            {
                "ref": "graph-edge-edge-1",
                "omission_reason": "edge_limit",
                "impact": "limited",
            }
        ],
        "forbidden_refs": [
            {"ref": "graph-node-private-1", "reason": "forbidden_privacy"}
        ],
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
        "freshness": {"stale_refs": ["graph-node-evidence-1"], "unknown_refs": ["graph-slice-graph-1"]},
        "completeness_state": "incomplete",
        "privacy_state": "redacted",
        "candidate_source_summary": {
            "selected_count": 1,
            "neighbor_count": 1,
            "included_candidate_count": 2,
        },
        "selection_rationale": "Selected nodes are required candidates.",
        "limitations": ["The graph slice is bounded."],
        "authority_boundary": {
            "can_execute": False,
            "can_review": True,
            "can_claim_final_acceptance": False,
            "final_verdict_required": True,
        },
        "domain_refs": {},
    }


def _result() -> dict:
    return integrate_graph_context_selection(
        _packet(),
        _ledger(),
        _selection(),
        actor_id="coordinator",
        actor_role="coordinator",
        occurred_at=STAMP,
    )


def _schema(path: str):
    schema = json.loads((REPO_ROOT / path).read_text(encoding="utf-8"))
    validator = validator_for(schema)
    validator.check_schema(schema)
    return validator(schema)


def test_graph_selection_creates_valid_immutable_packet_and_ledger_amendment():
    original_packet = _packet()
    original_ledger = _ledger()
    result = integrate_graph_context_selection(
        original_packet,
        original_ledger,
        _selection(),
        actor_id="coordinator",
        actor_role="coordinator",
        occurred_at=STAMP,
    )
    packet = result["context_packet"]
    ledger = result["context_ledger"]

    _schema("schemas/runtime-governance/context-packet.schema.json").validate(packet)
    _schema("schemas/runtime-governance/context-ledger.schema.json").validate(ledger)
    assert packet["context_packet_id"].startswith("cp-")
    assert packet["context_packet_id"] != original_packet["context_packet_id"]
    assert packet["completeness_state"] == "incomplete"
    assert packet["freshness"]["stale_refs"] == ["graph-node-evidence-1"]
    assert packet["freshness"]["unknown_refs"] == ["graph-slice-graph-1"]
    assert packet["domain_refs"]["graph_context_selection"]["assumption_claims"][0]["authority"] == "assumption"
    assert len(ledger["entries"]) == 2
    amendment = ledger["entries"][-1]
    assert amendment["event_type"] == "amendment_recorded"
    assert amendment["superseded_context_packet_id"] == "cp-task-1"
    assert amendment["resulting_context_packet_id"] == packet["context_packet_id"]
    assert original_packet == _packet()
    assert original_ledger == _ledger()


def test_repeated_same_inputs_are_deterministic_and_hashes_verify():
    first = _result()
    second = _result()
    assert first == second
    packet = first["context_packet"]
    packet_seed = copy.deepcopy(packet)
    packet_seed["immutability"] = {"immutable": True, "content_hash": ""}
    assert packet["immutability"]["content_hash"] == _digest(packet_seed)
    amendment = first["context_ledger"]["entries"][-1]
    amendment_seed = {key: value for key, value in amendment.items() if key != "entry_hash"}
    assert amendment["entry_hash"] == _digest(amendment_seed)


def test_replay_is_idempotent_without_a_second_ledger_entry():
    original_packet = _packet()
    original_ledger = _ledger()
    first = integrate_graph_context_selection(
        original_packet,
        original_ledger,
        _selection(),
        actor_id="coordinator",
        actor_role="coordinator",
        occurred_at=STAMP,
    )
    replay = integrate_graph_context_selection(
        original_packet,
        first["context_ledger"],
        _selection(),
        actor_id="coordinator",
        actor_role="coordinator",
        occurred_at=STAMP,
    )
    assert replay == first
    assert len(replay["context_ledger"]["entries"]) == 2


def test_graph_omissions_and_authority_boundary_are_preserved():
    result = _result()
    packet = result["context_packet"]
    assert packet["omitted_required_refs"][0]["impact"] == "human_required"
    assert packet["forbidden_refs"] == [
        {"ref": "graph-node-private-1", "reason": "forbidden_privacy"}
    ]
    assert "treat graph assumptions as source truth" in packet["constraints"]["forbidden_actions"]
    assert packet["constraints"]["authority_boundary"]["can_claim_final_acceptance"] is False


@pytest.mark.parametrize(
    ("which", "message"),
    [
        ("project", "project mismatch"),
        ("unsafe_ref", "unsafe"),
        ("authority", "authority boundary"),
        ("chain", "hash chain"),
        ("replay", "duplicate"),
    ],
)
def test_invalid_inputs_fail_closed(which: str, message: str):
    packet = _packet()
    ledger = _ledger()
    selection = _selection()
    if which == "project":
        selection["project_id"] = "other-project"
    elif which == "unsafe_ref":
        selection["source_refs"][1]["uri"] = r"C:\secret\token.txt"
    elif which == "authority":
        selection["authority_boundary"]["can_execute"] = True
    elif which == "chain":
        ledger["entries"][0]["entry_hash"] = "sha256:" + "b" * 64
    else:
        selection["source_refs"].append(copy.deepcopy(selection["source_refs"][0]))
    with pytest.raises(GraphContextPacketIntegrationError, match=message):
        integrate_graph_context_selection(
            packet,
            ledger,
            selection,
            actor_id="coordinator",
            actor_role="coordinator",
            occurred_at=STAMP,
        )


def test_base_packet_local_paths_are_preserved_but_new_graph_refs_are_strict():
    result = _result()
    refs = {ref["ref_id"]: ref for ref in result["context_packet"]["source_refs"]}
    assert refs["task-spec"]["uri"] == r"D:\runtime\packet\TASKSPEC.json"
    assert refs["graph-slice-graph-1"]["uri"] == "graph://projection/graph-1"


def test_worker_cannot_amend_context_and_unknown_graph_fields_are_rejected():
    with pytest.raises(GraphContextPacketIntegrationError, match="actor role"):
        integrate_graph_context_selection(
            _packet(),
            _ledger(),
            _selection(),
            actor_id="worker-1",
            actor_role="worker",
            occurred_at=STAMP,
        )
    selection = _selection()
    selection["assumption_claims"][0]["raw_label"] = "must not enter packet"
    with pytest.raises(GraphContextPacketIntegrationError, match="unknown fields"):
        integrate_graph_context_selection(
            _packet(),
            _ledger(),
            selection,
            actor_id="coordinator",
            actor_role="coordinator",
            occurred_at=STAMP,
        )


def test_timestamp_must_be_explicitly_validated():
    with pytest.raises(GraphContextPacketIntegrationError, match="date-time"):
        integrate_graph_context_selection(
            _packet(),
            _ledger(),
            _selection(),
            actor_id="coordinator",
            actor_role="coordinator",
            occurred_at="",
        )
    with pytest.raises(GraphContextPacketIntegrationError, match="timezone"):
        integrate_graph_context_selection(
            _packet(),
            _ledger(),
            _selection(),
            actor_id="coordinator",
            actor_role="coordinator",
            occurred_at="2026-08-28T12:00:00",
        )
